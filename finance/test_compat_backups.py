from pathlib import Path
from unittest.mock import Mock,patch
from contextlib import redirect_stdout
import io
import unittest
import secure_compat as compat
from install_security import patch_main,MARKER

class CompatBackupTests(unittest.TestCase):
    def setUp(self):
        self.ui=Mock();self.path=Path('/tmp/toolbox-private-example.tar.gz.age')
    def test_verify_does_not_restore(self):
        with patch.object(compat,'verify_archive',return_value=True) as check,patch.object(compat,'restore_bundle') as restore,redirect_stdout(io.StringIO()):
            self.assertTrue(compat.verify(self.ui,self.path))
        check.assert_called_once_with(self.path);restore.assert_not_called()
    def test_failed_verify_blocks_share(self):
        with patch.object(compat,'verify',return_value=False),patch.object(compat.subprocess,'run') as run:
            self.assertFalse(compat.share(self.ui,self.path))
        run.assert_not_called()
    def test_verified_share_uses_android_chooser(self):
        with patch.object(compat,'verify',return_value=True),patch.object(compat.shutil,'which',return_value='/bin/termux-open'),patch.object(compat.subprocess,'run',return_value=Mock(returncode=0)) as run,redirect_stdout(io.StringIO()):
            self.assertTrue(compat.share(self.ui,self.path))
        run.assert_called_once_with(['termux-open','--send','--chooser','--content-type','application/octet-stream',str(self.path)],check=False)
    def test_missing_share_command_shows_file(self):
        out=io.StringIO()
        with patch.object(compat,'verify',return_value=True),patch.object(compat.shutil,'which',return_value=None),redirect_stdout(out):
            self.assertFalse(compat.share(self.ui,self.path))
        self.assertIn(str(self.path),out.getvalue())
    def test_submenu_returns_without_creating(self):
        out=io.StringIO()
        with patch('builtins.input',return_value='0'),patch.object(compat,'backup_bundle') as create,redirect_stdout(out):compat.backup(self.ui)
        create.assert_not_called()
        for word in ['Create','Verify','Share','Show backup folder','Restore']:self.assertIn(word,out.getvalue())
    def test_create_can_verify_new_backup(self):
        with patch.object(compat,'roots',return_value={}),patch.object(compat,'backup_bundle',return_value=self.path),patch.object(compat,'verify') as verify,patch('builtins.input',return_value='v'),redirect_stdout(io.StringIO()):compat.create(self.ui)
        verify.assert_called_once_with(self.ui,self.path)
    def test_installer_upgrades_existing_menu_label(self):
        text=MARKER+"\nactions.extend([('Encrypted full toolbox backup',self.secure_backup),('Restore encrypted full toolbox backup',self.secure_restore)])\n"
        changed=patch_main(text)
        self.assertIn('Encrypted backups: create, verify and share',changed)
        self.assertEqual(changed.count('actions.extend'),1)
        self.assertEqual(patch_main(changed),changed)

if __name__=='__main__':unittest.main()
