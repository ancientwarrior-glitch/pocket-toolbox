from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout
import io
import json
import sqlite3
import sys
import tarfile
import tempfile
import unittest
import urllib.request

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'finance'))
from engine import Finance
from home_board import home_data,render_home,open_home
from board_actions import BoardActions
from finance_forms import render_view
from test_toolbox import app,installer,SOURCE,encrypt_fixture,archive_fixture


class PublicFinanceTests(unittest.TestCase):
    def setUp(self):
        self.crypto_patch=patch.object(app,'encrypt_archive',side_effect=encrypt_fixture);self.crypto_patch.start()
        self.decrypt_patch=patch.object(app,'decrypted_archive',side_effect=archive_fixture);self.decrypt_patch.start()
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.root=self.home/'public';self.root.mkdir()
        self.config=dict(app.DEFAULTS,title='My Desk',project_name='My Candles',currency='USD',downloads_folder=str(self.home/'Downloads'))
        (self.root/'config.json').write_text(json.dumps(self.config));self.app=app.App(self.root)
        self.path=self.app.data/'Finance/finance.sqlite'
        self.f=Finance(self.path,'USD')

    def tearDown(self):
        self.crypto_patch.stop();self.decrypt_patch.stop();self.f.close();self.temp.cleanup()

    def test_custom_paths_names_and_public_reading_format(self):
        self.app.write('reading-log.json',{'History/Book.epub':'Reading','Other.pdf':'Finished'})
        self.app.write('shopping.json',[dict(text='Wax',done=False)])
        data=home_data(self.home,public_root=self.root,config=self.config)
        self.assertEqual(data['reading'],['Book'])
        html=render_home(data,title=self.config['title'],project=self.config['project_name'])
        self.assertIn('My Desk',html);self.assertIn('My Candles',html)
        
        business=render_view(self.path,'business',self.config['project_name'])
        self.assertIn('My Candles',business);

    def test_board_edits_use_public_storage_and_leave_original_alone(self):
        original=self.home/'Workspace/Organizer/shopping.json';original.parent.mkdir(parents=True)
        original.write_text('[{"text":"Original","done":false}]')
        actions=BoardActions(self.home,self.path,public_root=self.root)
        revision=actions.state()['lists']['shopping']['revision']
        actions(dict(action='shopping-add',request_id='public-shopping-test',revision=revision,text='Public'))
        self.assertEqual(self.app.read('shopping.json',[])[0]['text'],'Public')
        self.assertIn('Original',original.read_text())
        self.assertFalse((self.home/'Workspace/Notes').exists())

    def test_old_debt_directions_and_idempotent_import(self):
        self.app.sql('INSERT INTO debts VALUES(1,?,?,?,?)',('Personal','Supplier','I owe',10000))
        self.app.sql('INSERT INTO debts VALUES(2,?,?,?,?)',('Business','Buyer','Owed to me',5000))
        self.app.sql('INSERT INTO entries VALUES(1,?,?,?,?,?,?)',('2026-01-02','Personal','Debt payment','Payment',2500,1))
        before=self.app.dbpath.read_bytes()
        self.f.import_legacy(self.app.dbpath)
        self.f.import_legacy(self.app.dbpath)
        debts=self.f.rows('SELECT direction,total FROM invoices ORDER BY id')
        self.assertEqual([(r['direction'],r['total']) for r in debts],[('Pay',7500),('Receive',5000)])
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),1)
        self.assertEqual(before,self.app.dbpath.read_bytes())

    def test_backup_restore_includes_consistent_finance(self):
        account=self.f.account('Personal','Cash','100','2026-01-01')
        with redirect_stdout(io.StringIO()):archive=self.app.backup()
        with tarfile.open(archive) as inp:self.assertIn('data/Finance/finance.sqlite',inp.getnames())
        self.f.close()
        with sqlite3.connect(self.path) as db:db.execute('UPDATE accounts SET opening=20000')
        with patch('builtins.input',side_effect=['1','RESTORE','']),redirect_stdout(io.StringIO()):self.app.restore()
        self.f=Finance(self.path)
        self.assertEqual(self.f.balance(account),10000)

    def test_older_archive_does_not_mix_with_new_finance(self):
        self.f.close();self.path.unlink()
        with redirect_stdout(io.StringIO()):self.app.backup()
        self.f=Finance(self.path)
        self.f.account('Personal','Cash','100','2026-01-01')
        with patch('builtins.input',side_effect=['1']),redirect_stdout(io.StringIO()),self.assertRaisesRegex(ValueError,'older backup'):
            self.app.restore()

    def test_public_ui_uses_config_and_blank_records(self):
        def check(ui):
            self.assertEqual(ui.f.base,'USD');self.assertEqual(ui.public_root,self.root)
            self.assertEqual(ui.config['project_name'],'My Candles')
            self.assertEqual(ui.f.rows('SELECT * FROM cash'),[])
        with patch('builtins.input',return_value='0'),redirect_stdout(io.StringIO()) as output:
            self.app.finance()
        self.assertIn('My Candles / business board',output.getvalue())
        
        self.assertFalse((self.home/'Workspace').exists())

    def test_installer_ships_engine_and_preserves_finance_records(self):
        target=self.home/'.local/share/pocket-toolbox'
        prefix=self.home/'prefix'
        with patch('builtins.input',side_effect=['','','','']),redirect_stdout(io.StringIO()):installer.install(SOURCE,self.home,prefix)
        path=target/'data/Finance/finance.sqlite'
        f=Finance(path);f.account('Personal','Keep','100','2026-01-01');f.close()
        with redirect_stdout(io.StringIO()):installer.install(SOURCE,self.home,prefix)
        f=Finance(path)
        try:self.assertEqual(f.rows('SELECT name FROM accounts')[0]['name'],'Keep')
        finally:f.close()
        for name in ('engine.py','home_board.py','finance_forms.py'):self.assertTrue((target/'finance'/name).is_file())

    def test_public_three_board_server_saves_only_public_records(self):
        account=self.f.account('Personal','Cash','100','2026-01-01')
        def opener(url):
            for suffix in ('','/finance','/business'):
                with urllib.request.urlopen(url+suffix) as response:
                    text=response.read().decode()
                    
            request=dict(action='cash-add',request_id='public-server-cash',account=account,category=None,amount='10',kind='Expense',day='2026-01-02',description='Public fixture')
            req=urllib.request.Request(url+'/api',data=json.dumps(request).encode(),headers={'Origin':url.rsplit('/',1)[0],'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
        open_home(self.f,home=self.home,public_root=self.root,config=self.config,opener=opener,pause=lambda _:None)
        self.assertEqual(self.f.balance(account),9000)
        self.assertFalse((self.home/'Workspace').exists())


if __name__=='__main__':unittest.main()
