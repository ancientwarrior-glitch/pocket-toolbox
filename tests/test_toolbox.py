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

SOURCE = Path(__file__).resolve().parents[1]
def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    result = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(result)
    return result

app = module('pocket_app', SOURCE / 'src/app.py')
installer = module('pocket_install', SOURCE / 'src/install.py')

class ToolboxTests(unittest.TestCase):
    def setUp(self):
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
        archives = list((self.base/'downloads/Pocket-Toolbox-Backups').glob('*.tar.gz'))
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

if __name__ == '__main__': unittest.main()
