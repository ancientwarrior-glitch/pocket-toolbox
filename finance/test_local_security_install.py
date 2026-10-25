from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from contextlib import redirect_stdout
import importlib.util
import io
import os
import shutil
import unittest
from install_security import install,patch_main,patch_shell,MARKER

SOURCE='''from pathlib import Path
from engine import Finance
class UI:
    def __init__(self):
        self.root=Path.home()/"records"/"Finance"
        self.f=Finance(self.root/"finance.sqlite")
    def main(self):
        actions=[("Existing",None)]
        for label,action in actions: print(label)
    def pause(self): pass
if __name__=="__main__": UI().main()
'''

class LocalInstallTests(unittest.TestCase):
    def test_local_patch_is_idempotent_and_preserves_existing_method(self):
        text=patch_main(SOURCE)
        self.assertEqual(text.count(MARKER),1);self.assertEqual(patch_main(text),text)
        self.assertIn('("Existing",None)',text)
        compile(text,'main.py','exec')

    def test_unknown_layout_refused(self):
        with self.assertRaises(ValueError):patch_main('class UI: pass')

    def test_shell_handlers_are_local_and_repeat_safe(self):
        text='case "$choice" in\n  5) old_backup ;;\n  13)\n    old_restore\n    ;;\n  0) exit ;;\nesac\n'
        result=patch_shell(text)
        self.assertIn('secure_compat.py" backup',result);self.assertIn('secure_compat.py" restore',result)
        self.assertEqual(patch_shell(result),result)

    def test_install_reads_only_local_root_and_preserves_records(self):
        with TemporaryDirectory() as temporary:
            home=Path(temporary)/'home';target=home/'bin/pocket-finance';target.mkdir(parents=True)
            (target/'main.py').write_text(SOURCE)
            prefix=Path(temporary)/'prefix';(prefix/'bin').mkdir(parents=True)
            (prefix/'bin/menu').write_text('case "$choice" in\n  5) old_backup ;;\n  0) exit ;;\nesac\n')
            data=home/'records';data.mkdir();note=data/'note.txt';note.write_text('private fixture')
            with patch('pathlib.Path.home',return_value=home),patch.dict(os.environ,{'PREFIX':str(prefix)}),redirect_stdout(io.StringIO()):
                install(Path(__file__).parent,home,prefix)
                install(Path(__file__).parent,home,prefix)
            self.assertEqual(note.read_text(),'private fixture');self.assertEqual(note.stat().st_mode&0o777,0o600)
            self.assertEqual((target/'main.py').read_text().count(MARKER),1)
            self.assertTrue((target/'board_server.py').exists());self.assertTrue((target/'secure_backup.py').exists())
            self.assertTrue((target/'cash_import.py').exists());self.assertTrue((target/'import_ui.py').exists())
            self.assertEqual((target/'main.py').read_text().count('self.import_cash_table'),1)
            self.assertIn('secure_compat.py" backup',(prefix/'bin/menu').read_text())
            self.assertEqual(len(list((data/'Finance/Installer-Backups').glob('security-*'))),2)

if __name__=='__main__':unittest.main()
