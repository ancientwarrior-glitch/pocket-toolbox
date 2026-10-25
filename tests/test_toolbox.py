from pathlib import Path
from unittest.mock import patch
from decimal import InvalidOperation
import contextlib
import importlib.util
import io
import json
import sqlite3
import tarfile
import tempfile
import unittest
import shutil

SOURCE = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

app = module('pocket_app', SOURCE / 'src/app.py')
installer = module('pocket_install', SOURCE / 'src/install.py')

@contextlib.contextmanager
def archive_fixture(path,root):
    # Archive layout tests isolate cryptography; real age round trips have a separate test.
    yield path

def encrypt_fixture(source,destination):
    shutil.copyfile(source,destination)
    return destination

class ToolboxTests(unittest.TestCase):
    def setUp(self):
        self.crypto_patch=patch.object(app,'encrypt_archive',side_effect=encrypt_fixture);self.crypto_patch.start()
        self.decrypt_patch=patch.object(app,'decrypted_archive',side_effect=archive_fixture);self.decrypt_patch.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.base = Path(self.temporary.name)
        self.root = self.base / 'app'
        self.root.mkdir()
        self.config = dict(app.DEFAULTS, downloads_folder=str(self.base/'downloads'),
                           books_folder=str(self.base/'books'), media_folder=str(self.base/'media'))
        (self.base/'books').mkdir()
        (self.base/'downloads').mkdir()
        (self.root/'config.json').write_text(json.dumps(self.config))
        self.app = app.App(self.root)
        self.output = contextlib.redirect_stdout(io.StringIO())
        self.output.__enter__()

    def tearDown(self):
        self.crypto_patch.stop();self.decrypt_patch.stop()
        self.output.__exit__(None,None,None)
        self.temporary.cleanup()

    def test_money_exact_cents(self):
        self.assertEqual(app.amount('0.29'),29)
        self.assertEqual(app.amount('125.50'),12550)

    def test_bad_amounts_rejected(self):
        for text in ['0','-1','1.001','NaN','Infinity','1,200','abc']:
            with self.subTest(text=text), self.assertRaises((ValueError,InvalidOperation)):
                app.amount(text)

    def test_settings_reject_bad_types_and_feed_injection(self):
        for config in [dict(color='yes'),dict(video_height='360'),dict(feeds=['https://a.test/\nexec:bad']),dict(shortcuts=[]),dict(books_folder='')]:
            with self.subTest(config=config),self.assertRaises(ValueError): app.validate_settings(config)

    def test_purchase_recorded_once_in_shared_ledger(self):
        with patch('builtins.input',side_effect=['2','Lard 1 kg','100.25','','y']):
            self.app.record('Purchase')
        rows = self.app.sql('SELECT scope,kind,cents FROM entries')
        self.assertEqual(rows,[('Business','Purchase',10025)])
        with patch('builtins.input',side_effect=['','n','']): self.app.totals()
        self.assertEqual(self.app.sql('SELECT COUNT(*) FROM entries')[0][0],1)

    def test_debt_payment_changes_cash_and_balance_once(self):
        self.app.sql('INSERT INTO debts VALUES(1,?,?,?,?)',('Personal','Example','I owe',10000))
        with patch('builtins.input',side_effect=['2','1','25','y']): self.app.debts()
        self.assertEqual(self.app.debt_balance(1,10000),7500)
        self.assertEqual(self.app.sql('SELECT kind,cents FROM entries'),[('Debt payment',2500)])

    def test_overpayment_rejected(self):
        self.app.sql('INSERT INTO debts VALUES(1,?,?,?,?)',('Personal','Example','I owe',100))
        with patch('builtins.input',side_effect=['2','1','2']),self.assertRaises(ValueError): self.app.debts()
        self.assertEqual(self.app.sql('SELECT COUNT(*) FROM entries')[0][0],0)

    def test_correction_blocks_overpayment(self):
        self.app.sql('INSERT INTO debts VALUES(1,?,?,?,?)',('Personal','Example','I owe',100))
        self.app.sql('INSERT INTO entries VALUES(1,?,?,?,?,?,1)',('2026-01-01','Personal','Debt payment','Example',50))
        with patch('builtins.input',side_effect=['1','e','','','2']),self.assertRaises(ValueError): self.app.correct()
        self.assertEqual(self.app.sql('SELECT cents FROM entries')[0][0],50)

    def test_note_identity_distinguishes_same_title(self):
        root = self.base/'books'
        self.assertNotEqual(self.app.book_note(root/'A/title.pdf'),self.app.book_note(root/'B/title.pdf'))

    def test_backup_has_records_not_library_media_or_code(self):
        (self.app.data/'notes.txt').write_text('Sample note')
        (self.base/'books/title.pdf').write_bytes(b'book')
        (self.root/'app.py').write_text('code')
        backup = self.app.backup()
        with tarfile.open(backup) as source: names = source.getnames()
        self.assertIn('config.json',names)
        self.assertIn('data/notes.txt',names)
        self.assertIn('data/budget.sqlite',names)
        self.assertNotIn('app.py',names)
        self.assertFalse(any('title.pdf' in n for n in names))

    def test_restore_round_trip_and_pre_restore_snapshot(self):
        note = self.app.data/'notes.txt'
        note.write_text('Before')
        self.app.sql('INSERT INTO entries VALUES(1,?,?,?,?,?,NULL)',('2026-01-01','Personal','Income','Sample',100))
        self.app.backup()
        note.write_text('After')
        self.app.sql('UPDATE entries SET cents=200')
        with patch('builtins.input',side_effect=['1','RESTORE','']): self.app.restore()
        self.assertEqual(note.read_text(),'Before')
        self.assertEqual(self.app.sql('SELECT cents FROM entries')[0][0],100)
        archives = list((self.base/'downloads/Pocket-Toolbox-Backups').glob('*.tar.gz.age'))
        self.assertEqual(len(archives),2)
        snapshots = []
        for path in archives:
            with tarfile.open(path) as source:
                snapshots.append(source.extractfile('data/notes.txt').read())
        self.assertIn(b'After',snapshots)

    def test_restore_rejects_path_traversal_before_write(self):
        self.bad_archive('../../escape.txt',b'bad')
        with patch('builtins.input',side_effect=['1']),self.assertRaises(ValueError): self.app.restore()
        self.assertFalse((self.base/'escape.txt').exists())

    def test_restore_rejects_links(self):
        folder = self.base/'downloads/Pocket-Toolbox-Backups'
        folder.mkdir()
        with tarfile.open(folder/'pocket-bad.tar.gz','w:gz') as out:
            member = tarfile.TarInfo('data/link')
            member.type = tarfile.SYMTYPE
            member.linkname = '/etc/passwd'
            out.addfile(member)
        with patch('builtins.input',side_effect=['1']),self.assertRaises(ValueError): self.app.restore()

    def test_restore_rejects_bad_config_before_write(self):
        self.bad_archive('config.json',b'{"color":"yes"}')
        original = self.app.config_path.read_bytes()
        with patch('builtins.input',side_effect=['1']),self.assertRaises(ValueError): self.app.restore()
        self.assertEqual(self.app.config_path.read_bytes(),original)

    def test_restore_limits_member_size_before_writing(self):
        self.bad_archive('data/oversized.txt',b'fixture payload')
        with patch.object(app,'MAX_MEMBER_BYTES',4),patch('builtins.input',side_effect=['1']),self.assertRaisesRegex(ValueError,'limits'):
            self.app.restore()
        self.assertFalse((self.app.data/'oversized.txt').exists())

    def test_app_rejects_symlinked_private_root(self):
        target=self.base/'target';target.mkdir();link=self.base/'linked';link.symlink_to(target,target_is_directory=True)
        with self.assertRaises(ValueError):app.App(link)

    def test_backup_refuses_files_that_restore_would_reject(self):
        (self.app.data/'large.txt').write_text('fixture payload')
        with patch.object(app,'MAX_MEMBER_BYTES',4),self.assertRaisesRegex(ValueError,'limits'):self.app.backup()
        self.assertEqual(list((self.base/'downloads/Pocket-Toolbox-Backups').glob('*.age')),[])

    def bad_archive(self,name,content):
        folder = self.base/'downloads/Pocket-Toolbox-Backups'
        folder.mkdir(exist_ok=True)
        with tarfile.open(folder/'pocket-bad.tar.gz','w:gz') as out:
            member = tarfile.TarInfo(name)
            member.size = len(content)
            out.addfile(member,io.BytesIO(content))

    def test_installer_preserves_existing_menus_and_settings(self):
        fakehome, prefix = self.base/'fakehome', self.base/'prefix'
        (prefix/'bin').mkdir(parents=True)
        menu = prefix/'bin/menu'
        menu.write_text('existing menu')
        with patch('builtins.input',side_effect=['','','','']): installer.install(SOURCE,fakehome,prefix)
        config = fakehome/'.local/share/pocket-toolbox/config.json'
        config.write_text('{"title":"Keep me"}')
        installer.install(SOURCE,fakehome,prefix)
        self.assertEqual(json.loads(config.read_text())['title'],'Keep me')
        self.assertEqual(menu.read_text(),'existing menu')
        self.assertIn('Pocket Toolbox launcher',(prefix/'bin/pocket').read_text())

    def test_installer_refuses_command_collision(self):
        prefix = self.base/'prefix'
        (prefix/'bin').mkdir(parents=True)
        (prefix/'bin/pocket').write_text('another app')
        with self.assertRaises(RuntimeError): installer.install(SOURCE,self.base/'fakehome',prefix)

    def test_installer_uses_custom_profile_on_fresh_install(self):
        import shutil
        package = self.base/'custom-package'
        shutil.copytree(SOURCE,package,ignore=shutil.ignore_patterns('__pycache__'))
        profile = dict(app.DEFAULTS,title='Custom title',project_name='Custom project')
        (package/'config.json').write_text(json.dumps(profile))
        with patch('builtins.input',side_effect=['','','','']):
            installer.install(package,self.base/'custom-home',self.base/'custom-prefix')
        result = json.loads((self.base/'custom-home/.local/share/pocket-toolbox/config.json').read_text())
        self.assertEqual(result['title'],'Custom title')
        self.assertEqual(result['project_name'],'Custom project')

    def test_blank_library_input_and_exit(self):
        with patch('builtins.input',side_effect=['','q']): self.app.library()

    def test_backup_verification_never_invokes_restore(self):
        path=self.base/'verified.tar.gz.age';path.write_bytes(b'fixture')
        with patch.object(app,'verify_archive',return_value=True) as verify,patch.object(self.app,'restore') as restore:
            self.assertTrue(self.app.verify_backup(path))
            verify.assert_called_once_with(path);restore.assert_not_called()

    def test_share_requires_verification_and_only_hands_off_ciphertext(self):
        path=self.base/'backup.tar.gz.age';path.write_bytes(b'fixture')
        with patch.object(self.app,'verify_backup',return_value=False),patch.object(app.subprocess,'run') as run:
            self.app.share_backup(path);run.assert_not_called()
        with patch.object(self.app,'verify_backup',return_value=True),patch.object(app.shutil,'which',return_value='/fixture/termux-open'),patch.object(app.subprocess,'run') as run:
            run.return_value.returncode=0;self.app.share_backup(path)
            self.assertEqual(run.call_args.args[0],['termux-open','--send','--chooser','--content-type','application/octet-stream',str(path)])

    def test_missing_android_share_shows_file_without_network_action(self):
        path=self.base/'backup.tar.gz.age';path.write_bytes(b'fixture')
        with patch.object(self.app,'verify_backup',return_value=True),patch.object(app.shutil,'which',return_value=None),patch.object(app.subprocess,'run') as run:
            self.app.share_backup(path);run.assert_not_called()

    def test_public_backup_menu_has_discoverable_actions(self):
        with patch.object(self.app,'menu') as menu:self.app.backups()
        names=[label for label,action in menu.call_args.args[1]]
        self.assertEqual(len(names),5)
        self.assertTrue(any('Verify' in name for name in names));self.assertTrue(any('Share' in name for name in names))

    def test_new_backup_offers_verification_before_leaving(self):
        path=self.base/'backup.tar.gz.age'
        with patch.object(self.app,'backup',return_value=path),patch.object(self.app,'verify_backup') as verify,patch('builtins.input',side_effect=['v','']):
            self.app.create_backup();verify.assert_called_once_with(path)

if __name__ == '__main__': unittest.main()
