from pathlib import Path
import json
import tempfile
import unittest
import urllib.request
import urllib.error
from engine import Finance
from board_actions import BoardActions
from charts import serve
from home_board import open_home


class BoardActionTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.home=Path(self.temp.name)
        self.path=self.home/'Workspace/Finance/finance.sqlite'
        self.f=Finance(self.path)
        self.account=self.f.account('Personal','Cash','100','2026-01-01')
        self.category=self.f.category('Personal','Food','Expense')
        self.actions=BoardActions(self.home,self.path)

    def tearDown(self):self.f.close();self.temp.cleanup()

    def request(self,action,**values):
        return dict(action=action,request_id='request-0000000000001',**values)

    def test_shopping_round_trip_backup_and_metadata_preserved(self):
        folder=self.home/'Workspace/Organizer';folder.mkdir(parents=True)
        path=folder/'shopping.json';raw=b'[{"text":"Soap", "done":false, "extra":"keep"}]';path.write_bytes(raw)
        state=self.actions.state()['lists']['shopping']
        self.actions(self.request('shopping-check',revision=state['revision'],index=0,done=True))
        self.assertEqual(json.loads(path.read_bytes()),[dict(text='Soap',done=True,extra='keep')])
        self.assertEqual(next((folder/'Board-Backups').iterdir()).read_bytes(),raw)

    def test_stale_tab_cannot_overwrite_new_terminal_changes(self):
        state=self.actions.state()['lists']['shopping']
        path=self.home/'Workspace/Organizer/shopping.json';path.parent.mkdir(parents=True)
        path.write_text('[{"text":"Added elsewhere","done":false}]')
        with self.assertRaisesRegex(ValueError,'changed'):
            self.actions(self.request('shopping-add',revision=state['revision'],text='Old tab'))
        self.assertIn('Added elsewhere',path.read_text())

    def test_corrupt_file_never_replaced(self):
        path=self.home/'Workspace/Organizer/shopping.json';path.parent.mkdir(parents=True);path.write_text('bad json')
        with self.assertRaises(ValueError):
            self.actions(self.request('shopping-add',revision='x',text='Soap'))
        self.assertEqual(path.read_text(),'bad json')

    def test_add_retry_does_not_duplicate(self):
        state=self.actions.state()['lists']['shopping']
        request=self.request('shopping-add',revision=state['revision'],text='Soap')
        self.actions(request);self.actions(request)
        self.assertEqual(len(self.actions.state()['lists']['shopping']['rows']),1)
        with self.assertRaises(ValueError):self.actions(dict(request,text='Other'))

    def test_upload_changes_only_status(self):
        path=self.home/'Workspace/Organizer/uploads.json';path.parent.mkdir(parents=True)
        path.write_text(json.dumps([dict(title='Soap',status='To upload',url='https://example.test',path='/keep/video.mp4')]))
        revision=self.actions.state()['lists']['uploads']['revision']
        self.actions(self.request('upload-status',revision=revision,index=0,status='Published'))
        row=json.loads(path.read_text())[0]
        self.assertEqual(row,dict(title='Soap',status='Published',url='https://example.test',path='/keep/video.mp4'))

    def test_note_is_new_file_and_retry_safe(self):
        request=self.request('note-add',text='My note')
        self.actions(request);BoardActions(self.home,self.path)(request)
        files=list((self.home/'Workspace/Notes').glob('*.txt'))
        self.assertEqual(len(files),1);self.assertEqual(files[0].read_text(),'My note\n')

    def test_cash_uses_engine_and_retry_survives_new_server(self):
        request=self.request('cash-add',account=self.account,category=self.category,amount='12.50',kind='Expense',day='2026-01-02',description='Food')
        self.actions(request);BoardActions(self.home,self.path)(request)
        self.assertEqual(self.f.balance(self.account),8750)
        row=self.f.rows('SELECT * FROM cash')[0]
        self.assertIsNone(row['ref'])  # still correctable through the normal cash editor
        self.f.correct_cash(row['id'],void=True)
        self.assertEqual(self.f.balance(self.account),10000)

    def test_invalid_cash_rolls_back_and_can_be_fixed(self):
        wrong=self.f.category('Business','Supplies','Expense')
        request=self.request('cash-add',account=self.account,category=wrong,amount='10',kind='Expense',day='2026-01-02',description='Food')
        with self.assertRaises(ValueError):self.actions(request)
        self.assertEqual(self.f.rows('SELECT * FROM cash'),[])
        self.assertEqual(self.f.rows('SELECT * FROM imports'),[])
        self.actions(dict(request,category=self.category))
        self.assertEqual(self.f.balance(self.account),9000)

    def test_http_actions_need_same_origin_and_json(self):
        calls=[]
        def opener(url):
            origin=url.rsplit('/',1)[0]
            body=json.dumps({'test':True}).encode()
            for headers,path,status in [({'Content-Type':'application/json'},url+'/api',403),
                                        ({'Origin':'https://evil.test','Content-Type':'application/json'},url+'/api',403),
                                        ({'Origin':origin,'Content-Type':'text/plain'},url+'/api',415),
                                        ({'Origin':origin,'Content-Type':'application/json'},url+'/wrong',404)]:
                request=urllib.request.Request(path,data=body,headers=headers)
                with self.assertRaises(urllib.error.HTTPError) as error:urllib.request.urlopen(request)
                self.assertEqual(error.exception.code,status)
            request=urllib.request.Request(url+'/api',data=body,headers={'Origin':origin,'Content-Type':'application/json'})
            with urllib.request.urlopen(request) as response:self.assertTrue(json.load(response)['ok'])
        serve('test',opener=opener,pause=lambda _:None,api=lambda request:calls.append(request) or {'ok':True})
        self.assertEqual(calls,[{'test':True}])

    def test_home_server_refreshes_graphs_after_cash_entry(self):
        def opener(url):
            origin=url.rsplit('/',1)[0]
            with urllib.request.urlopen(url) as response:self.assertIn(b'Update your records',response.read())
            request=self.request('cash-add',account=self.account,category=self.category,amount='10',kind='Expense',day='2026-01-02',description='Board refresh fixture')
            req=urllib.request.Request(url+'/api',data=json.dumps(request).encode(),headers={'Origin':origin,'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
            with urllib.request.urlopen(url+'/finance') as response:self.assertIn(b'Board refresh fixture',response.read())
        open_home(self.f,home=self.home,opener=opener,pause=lambda _:None)


if __name__=='__main__':unittest.main()
