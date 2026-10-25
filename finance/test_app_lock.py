import base64,json,os,shutil,sqlite3,subprocess,sys,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app_lock
from install_passwords import python_guard,shell_guard,install

class PasswordTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name)
        self.mock=patch.object(Path,'home',return_value=self.home);self.mock.start()
    def tearDown(self):self.mock.stop();self.tmp.cleanup()
    def test_hash_salt_and_password_validation(self):
        password='a test password phrase';a=app_lock.password_record(password);b=app_lock.password_record(password)
        self.assertNotEqual(a,b);self.assertNotIn(password,json.dumps(a));self.assertTrue(app_lock.matches(password,a));self.assertFalse(app_lock.matches('wrong',a))
        with self.assertRaises(ValueError):app_lock.password_record('short')
        with self.assertRaises(ValueError):app_lock.matches(password,{'version':999})
    def test_setup_retry_and_change(self):
        with patch('getpass.getpass',side_effect=['long sample phrase','long sample phrase']):app_lock.authenticate()
        path=app_lock.config_path();self.assertEqual(path.stat().st_mode&0o777,0o600)
        with patch('getpass.getpass',return_value='wrong'):
            with self.assertRaises(ValueError):app_lock.authenticate()
        with patch('getpass.getpass',return_value='long sample phrase'):
            with self.assertRaises(ValueError):app_lock.authenticate() # retry delay
        (app_lock.folder()/'attempts.json').unlink()
        with patch('getpass.getpass',return_value='long sample phrase'):app_lock.authenticate()
    def test_no_state_no_authorization_and_stale_state(self):
        self.assertFalse(app_lock.authorized())
        app_lock.atomic(app_lock.folder()/'active.json',{'sid':os.getsid(0),'controller':os.getpid()})
        self.assertFalse(app_lock.authorized()) # no controller flock
    def test_symlink_settings_fail(self):
        external=self.home/'other';external.write_text('{}')
        app_lock.config_path().symlink_to(external)
        with self.assertRaises(ValueError):app_lock.authenticate()
    def test_python_insertion_future_docstring_and_repeat(self):
        text='#!/usr/bin/python\n"""Example."""\nfrom __future__ import annotations\nprint("hello")\n'
        result=python_guard(text);compile(result,'test.py','exec');self.assertEqual(result,python_guard(result))
        self.assertLess(result.index('from __future__'),result.index(app_lock.MARKER))
    def test_shell_quotes_and_repeat(self):
        result=shell_guard('#!/bin/bash\necho okay\n',self.home/'a b',self.home/'c d')
        self.assertEqual(result,shell_guard(result,self.home,self.home))
        self.assertEqual(subprocess.run(['bash','-n'],input=result,text=True).returncode,0)
    def test_installer_preserves_records_guards_widgets(self):
        prefix=self.home/'prefix';(prefix/'bin').mkdir(parents=True);(prefix/'bin/bash').symlink_to(shutil.which('bash'))
        (prefix/'bin/python').symlink_to(sys.executable)
        (prefix/'bin/menu').write_text('#!/bin/bash\necho Menu\n')
        (self.home/'bin/pocket-finance').mkdir(parents=True);main=self.home/'bin/pocket-finance/main.py';main.write_text('print("Finance")\n')
        board=main.with_name('board_server.py');board.write_text('# Previous board runtime\n')
        widgets=self.home/'.shortcuts';widgets.mkdir();(widgets/'Toolbox').write_text('#!/bin/bash\nmenu\n')
        records=self.home/'Everyday';records.mkdir();private=records/'private.txt';private.write_text('must stay unchanged')
        package=Path(app_lock.__file__).parent
        install(package,self.home,prefix)
        self.assertIn('from app_lock import',board.read_text())
        self.assertIn(app_lock.MARKER,main.read_text());self.assertIn(app_lock.MARKER,(widgets/'Toolbox').read_text())
        self.assertEqual(private.read_text(),'must stay unchanged')
        before=main.read_text();install(package,self.home,prefix);self.assertEqual(before,main.read_text())
    def test_no_interactive_terminal_refuses(self):
        with patch('sys.stdin.isatty',return_value=False):
            with self.assertRaises(ValueError):app_lock.run(['true'])

if __name__=='__main__':unittest.main()

# Real pseudo-terminal tests: exercise hidden input, process groups and reopening.
import pty,select,time
class TerminalPasswordTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.home=Path(self.tmp.name);self.children=[]
        self.helper=self.home/'session.py'
        self.helper.write_text("import sys\nfrom app_lock import run\ntry:run([sys.executable,'-u','-c',sys.argv[1]],idle=float(sys.argv[2]))\nexcept ValueError as e:print(e)\n")
    def tearDown(self):
        for pid,fd in self.children:
            try:os.kill(pid,9)
            except ProcessLookupError:pass
            try:os.waitpid(pid,0)
            except ChildProcessError:pass
            os.close(fd)
        self.tmp.cleanup()
    def start(self,code="from app_lock import authorized;print('AUTHORIZED:',authorized());input('DONE: ')",idle=5):
        pid,fd=pty.fork()
        if pid==0:
            env=dict(os.environ,HOME=str(self.home),PYTHONPATH=str(Path(app_lock.__file__).parent))
            os.execve(sys.executable,[sys.executable,'-u',str(self.helper),code,str(idle)],env)
        self.children.append((pid,fd));return fd
    def expect(self,fd,needle,timeout=5):
        value=b'';end=time.monotonic()+timeout
        while time.monotonic()<end:
            if select.select([fd],[],[],.05)[0]:
                try:chunk=os.read(fd,65536)
                except OSError:break
                if not chunk:break
                value+=chunk
                if needle.encode() in value:return value
        self.fail(f'Missing {needle!r} in {value!r}')
    def setup_password(self,fd):
        self.expect(fd,'New toolbox password');os.write(fd,b'testing a long password\n')
        self.expect(fd,'Repeat toolbox password');os.write(fd,b'testing a long password\n')
        text=self.expect(fd,'DONE:');self.assertIn(b'AUTHORIZED: True',text)
    def test_first_open_close_reopen_requires_password_wrong_stays_closed(self):
        fd=self.start();self.setup_password(fd);os.write(fd,b'\n');self.expect(fd,'Toolbox locked.')
        fd=self.start();self.expect(fd,'Toolbox password:');os.write(fd,b'wrong password\n')
        text=self.expect(fd,'Wrong password');self.assertNotIn(b'AUTHORIZED:',text)
        (self.home/'.config/pocket-toolbox-lock/attempts.json').unlink()
        fd=self.start();self.expect(fd,'Toolbox password:');os.write(fd,b'testing a long password\n');self.expect(fd,'AUTHORIZED: True');os.write(fd,b'\x1d');self.expect(fd,'Toolbox locked.')
    def test_idle_kills_child_and_lock_state_removed(self):
        fd=self.start(idle=.6);self.setup_password(fd);self.expect(fd,'Toolbox locked.')
        self.assertFalse((self.home/'.config/pocket-toolbox-lock/active.json').exists())
    def test_board_style_lock_request_stops_session(self):
        fd=self.start(code="from app_lock import authorized,request_lock;print('AUTHORIZED:',authorized());input('DONE: ');request_lock();input('should be stopped')")
        self.setup_password(fd);os.write(fd,b'\n');self.expect(fd,'Toolbox locked.')

    def test_second_widget_authenticates_then_replaces_old_session(self):
        first=self.start();self.setup_password(first)
        second=self.start();self.expect(second,'Toolbox password:');os.write(second,b'testing a long password\n')
        self.expect(second,'AUTHORIZED: True');self.expect(first,'Toolbox locked.')
        os.write(second,b'\x1d');self.expect(second,'Toolbox locked.')

    def test_killed_controller_does_not_leave_unlocked_child(self):
        code="from app_lock import authorized;from pathlib import Path;import time;print('AUTHORIZED:',authorized());input('DONE: ');time.sleep(1);Path.home().joinpath('should-not-exist').write_text('leaked')"
        fd=self.start(code=code);self.setup_password(fd)
        controller=self.children[-1][0];os.write(fd,b'\n');os.kill(controller,9)
        # Watchdog should close the slave PTY without waiting for the idle limit.
        end=time.monotonic()+3;closed=False
        while time.monotonic()<end:
            if select.select([fd],[],[],.05)[0]:
                try:
                    if not os.read(fd,65536):closed=True;break
                except OSError:closed=True;break
        self.assertTrue(closed)
        self.assertFalse((self.home/'should-not-exist').exists())
