from pathlib import Path
import base64
import hashlib
import json
import os
import re
import select
import shutil
import sys
import tempfile
import time
import unittest
import urllib.request
import urllib.error
from unittest.mock import patch

from board_server import protect_page,serve
from pocket_security import private_dir,harden_tree,encrypt_archive,decrypted_archive


class SecurityTests(unittest.TestCase):
    def test_permissions_and_symlink_refusal(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary)/'records';root.mkdir();(root/'secret.txt').write_text('fixture')
            root.chmod(0o755);(root/'secret.txt').chmod(0o644);harden_tree(root)
            self.assertEqual(root.stat().st_mode&0o777,0o700)
            self.assertEqual((root/'secret.txt').stat().st_mode&0o777,0o600)
            (root/'link').symlink_to(root/'secret.txt')
            with self.assertRaises(ValueError):harden_tree(root)

    def test_csp_hashes_match_scripts_and_styles(self):
        page='<html><body><style>body{color:red}</style><script>console.log("fixture")</script></body></html>'
        payload,csp=protect_page(page,'/test-session',900)
        for tag in ['script','style']:
            for body in re.findall(r'<'+tag+r'\b[^>]*>([\s\S]*?)</'+tag+'>',payload.decode()):
                value=base64.b64encode(hashlib.sha256(body.encode()).digest()).decode()
                self.assertIn("'sha256-"+value+"'",csp)
        self.assertIn("frame-ancestors 'none'",csp)
        self.assertNotIn("'unsafe-inline'",csp);self.assertNotIn("'unsafe-eval'",csp)
        self.assertIn('about:blank',payload.decode())

    def test_idle_expiry_stops_api(self):
        calls=[]
        def opener(url):
            time.sleep(.3)
            request=urllib.request.Request(url+'/api',data=b'{}',headers={'Origin':url.rsplit('/',1)[0],'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(request,timeout=1) as response:self.fail('Expired session accepted a save')
            except (urllib.error.URLError,ConnectionError,OSError):pass
        serve('<html><body>Fixture</body></html>',opener=opener,pause=lambda _:None,api=lambda body:calls.append(body),idle_seconds=.1,max_seconds=1)
        self.assertEqual(calls,[])

    def test_absolute_expiry_is_not_reset_by_loads(self):
        calls=[]
        def opener(url):
            for _ in range(2):
                with urllib.request.urlopen(url) as response:self.assertEqual(response.headers['X-Frame-Options'],'DENY')
                time.sleep(.08)
            time.sleep(.15)
            try:urllib.request.urlopen(url,timeout=1);self.fail('Absolute expiry bypassed')
            except (urllib.error.URLError,ConnectionError,OSError):pass
        serve('<html><body>Fixture</body></html>',opener=opener,pause=lambda _:None,idle_seconds=1,max_seconds=.22)

    def test_lock_and_cross_site_get(self):
        def opener(url):
            bad=urllib.request.Request(url,headers={'Sec-Fetch-Site':'cross-site'})
            with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(bad)
            self.assertEqual(error.exception.code,403)
            request=urllib.request.Request(url+'/lock',data=b'{}',headers={'Origin':url.rsplit('/',1)[0],'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:self.assertTrue(json.load(response)['ok'])
            try:urllib.request.urlopen(url,timeout=1);self.fail('Locked session accepted a page')
            except (urllib.error.URLError,ConnectionError,OSError):pass
        serve('<html><body>Fixture</body></html>',opener=opener,pause=lambda _:None)

    def test_status_checks_do_not_keep_session_alive(self):
        def opener(url):
            for _ in range(2):
                with urllib.request.urlopen(url+'/status') as response:self.assertTrue(json.load(response)['ok'])
                time.sleep(.08)
            time.sleep(.12)
            try:urllib.request.urlopen(url+'/status',timeout=1);self.fail('Status polling extended the session')
            except (urllib.error.URLError,ConnectionError,OSError):pass
        serve('<html><body>Fixture</body></html>',opener=opener,pause=lambda _:None,idle_seconds=.2,max_seconds=1)

    def test_missing_age_does_not_export_plaintext(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'plain';source.write_bytes(b'private fixture');target=root/'backup.age'
            with patch('pocket_security.shutil.which',return_value=None),self.assertRaises(ValueError):encrypt_archive(source,target)
            self.assertFalse(target.exists())

    def test_encryption_failure_cleans_partial_file(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);source=root/'plain';source.write_bytes(b'fixture');target=root/'backup.age'
            with patch('pocket_security.shutil.which',return_value='/fixture/age'),patch('pocket_security.subprocess.run') as run:
                run.return_value.returncode=1
                with self.assertRaises(ValueError):encrypt_archive(source,target)
            self.assertEqual(list(root.iterdir()),[source])

    @unittest.skipUnless(shutil.which('age') and os.name=='posix','real age CLI + PTY required')
    def test_real_age_round_trip_wrong_password_and_tampering(self):
        import pty
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);(root/'plain').write_bytes(b'private fixture: no user records')
            module=str(Path(__file__).parent)
            code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from pocket_security import encrypt_archive,decrypted_archive;r=Path(sys.argv[2]);encrypt_archive(r/"plain",r/"backup.age");\nwith decrypted_archive(r/"backup.age",r) as p: assert p.read_bytes()==(r/"plain").read_bytes()'
            def terminal(program,password):
                pid,fd=pty.fork()
                if pid==0:os.execv(sys.executable,[sys.executable,'-c',program,module,str(root)])
                output=b'';sent=0;deadline=time.monotonic()+45;status=None
                try:
                    while time.monotonic()<deadline:
                        if select.select([fd],[],[],.1)[0]:
                            try:chunk=os.read(fd,4096)
                            except OSError:chunk=b''
                            if not chunk:
                                _,status=os.waitpid(pid,0);break
                            output+=chunk
                            prompts=len(re.findall(rb'(?:Enter|Confirm|Repeat) passphrase[^:]*:',output,re.I))
                            while sent<prompts:os.write(fd,password+b'\n');sent+=1
                        result=os.waitpid(pid,os.WNOHANG)
                        if result[0]:status=result[1];break
                    if status is None:
                        result=os.waitpid(pid,os.WNOHANG)
                        if result[0]:status=result[1]
                        else:os.kill(pid,9);os.waitpid(pid,0);raise AssertionError('age PTY timed out')
                    return os.waitstatus_to_exitcode(status),output
                finally:os.close(fd)
            fixture_pass=b'only-a-test-fixture-long-passphrase'
            result,output=terminal(code,fixture_pass)
            self.assertEqual(result,0,output.decode(errors='replace'))
            self.assertNotIn((root/'plain').read_bytes(),(root/'backup.age').read_bytes())
            bad_code='import sys;from pathlib import Path;sys.path.insert(0,sys.argv[1]);from pocket_security import decrypted_archive;r=Path(sys.argv[2]);\nwith decrypted_archive(r/"backup.age",r) as p: print("UNEXPECTED_SUCCESS")'
            result,output=terminal(bad_code,b'wrong-test-fixture-passphrase')
            self.assertNotEqual(result,0);self.assertNotIn(b'UNEXPECTED_SUCCESS',output)
            raw=bytearray((root/'backup.age').read_bytes());raw[-1]^=1;(root/'backup.age').write_bytes(raw)
            result,output=terminal(bad_code,fixture_pass)
            self.assertNotEqual(result,0);self.assertNotIn(b'UNEXPECTED_SUCCESS',output)
            self.assertEqual(list(root.glob('.restore-*')),[])


if __name__=='__main__':unittest.main()
