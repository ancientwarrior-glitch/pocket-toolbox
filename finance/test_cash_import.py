from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch,Mock
from contextlib import redirect_stdout
import io
import unittest
import zipfile
from engine import Finance
from cash_import import amount,parse_date,preview,commit,read_table,workbook
import import_ui

class CashImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name)
        self.f=Finance(self.root/'finance.sqlite');self.account=self.f.account('Personal','Cash','100','2026-01-01')
        self.mapping={'date':0,'description':1,'amount':2,'category':3,'id':4}
        self.table=(['Date','Description','Amount','Category','ID'],[(2,['2026-02-01','Food','-12.50','Food','a']),(3,['2026-02-02','Pay','100','Work','b'])],False)
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def plan(self,**kw):return preview(self.f,self.table,self.account,'provider',self.mapping,**kw)
    def test_preview_is_read_only_then_commit_repeat_skips(self):
        p=self.plan();self.assertFalse(p['errors']);self.assertEqual(len(self.f.rows('SELECT * FROM cash')),0)
        self.assertEqual(len(self.f.rows('SELECT * FROM categories')),0)
        result=commit(self.f,p,self.root/'Backups')
        self.assertEqual(result['imported'],2);self.assertTrue(Path(result['backup']).is_file())
        self.assertEqual(Path(result['backup']).stat().st_mode&0o777,0o600)
        self.assertEqual(self.f.balance(self.account),18750)
        self.assertEqual(commit(self.f,self.plan(),self.root/'Backups')['imported'],0)
    def test_changed_source_id_blocks_whole_import(self):
        commit(self.f,self.plan(),self.root/'Backups');self.table[1][0][1][2]='-20'
        p=self.plan();self.assertTrue(p['errors'])
        with self.assertRaises(ValueError):commit(self.f,p,self.root/'Backups')
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),2)
    def test_duplicates_across_sources_are_skipped_unless_explicit(self):
        commit(self.f,self.plan(),self.root/'Backups')
        p=preview(self.f,self.table,self.account,'other-provider',self.mapping)
        self.assertTrue(all(r['status']=='Possible duplicate' for r in p['rows']))
        self.assertEqual(commit(self.f,p,self.root/'Backups')['imported'],0)
        self.assertEqual(commit(self.f,p,self.root/'Backups',{2})['imported'],1)
    def test_no_id_repeat_survives_row_reordering(self):
        self.mapping.pop('id');commit(self.f,self.plan(),self.root/'Backups');self.table[1].reverse()
        self.assertTrue(all(r['status']=='Imported already' for r in self.plan()['rows']))
    def test_duplicate_ids_in_one_file_are_errors(self):
        self.table[1][1][1][4]='a';self.assertTrue(self.plan()['errors'])
    def test_preview_stale_cash_blocks_save(self):
        p=self.plan();self.f.cash_entry(self.account,'1','Income','Another entry','2026-02-03')
        with self.assertRaisesRegex(ValueError,'changed after preview'):commit(self.f,p,self.root/'Backups')
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),1)
    def test_atomic_rollback_of_cash_categories_and_import_receipts(self):
        p=self.plan();original=self.f._cash
        def fail(*args,**kw):
            if args[3]=='Pay':raise ValueError('Simulated failure')
            return original(*args,**kw)
        with patch.object(self.f,'_cash',side_effect=fail),self.assertRaises(ValueError):commit(self.f,p,self.root/'Backups')
        for table in ['cash','categories','imports']:self.assertEqual(len(self.f.rows('SELECT * FROM '+table)),0)
    def test_dates_before_opening_and_wrong_currency_rejected(self):
        self.table[1][0][1][0]='2020-01-01';self.assertTrue(self.plan()['errors'])
        self.table[1][0][1][0]='2026-02-01';self.mapping['currency']=3
        self.assertTrue(self.plan()['errors'])
    def test_unsupported_type_rejected(self):
        self.mapping['kind']=3;self.table[1][0][1][3]='Transfer';self.assertTrue(self.plan()['errors'])
    def test_split_debit_credit_and_conflicting_row(self):
        table=(['date','desc','debit','credit'],[(2,['2026-02-01','Food','12.50','']),(3,['2026-02-02','Pay','','100'])],False)
        m={'date':0,'description':1,'debit':2,'credit':3}
        p=preview(self.f,table,self.account,'bank',m,mode='split');self.assertFalse(p['errors']);self.assertEqual(p['rows'][0]['delta'],-1250)
        table[1][0][1][3]='1';self.assertTrue(preview(self.f,table,self.account,'bank',m,mode='split')['errors'])
    def test_number_formats_cents_and_precision(self):
        self.assertEqual(amount('1,234.56'),123456);self.assertEqual(amount('(1.234,56)',','),-123456)
        self.assertEqual(amount('12345',cents=True),12345)
        for value in ['1,23.45','NaN','1e5','$123','0.001']:
            with self.assertRaises(ValueError):amount(value)
        with self.assertRaises(ValueError):amount('1.5',cents=True)
    def test_date_formats_excel_epochs(self):
        self.assertEqual(parse_date('02/03/2026','dmy'),'2026-03-02')
        self.assertEqual(parse_date('02/03/2026','mdy'),'2026-02-03')
        self.assertEqual(parse_date('61','excel'),'1900-03-01')
        self.assertEqual(parse_date('0','excel',True),'1904-01-01')
        with self.assertRaises(ValueError):parse_date('60','excel')
    def test_csv_bom_delimiter_and_header_offset(self):
        p=self.root/'export.csv';p.write_text('Report\nDate;Description;Amount\n2026-02-01;"Food; shop";-12.50\n',encoding='utf-8-sig')
        headers,records,_=read_table(p,delimiter=';',header_row=2)
        self.assertEqual(headers,['Date','Description','Amount']);self.assertEqual(records[0],(3,['2026-02-01','Food; shop','-12.50']))
    def make_xlsx(self,formula=False,entity=False):
        path=self.root/'book.xlsx'
        ns='http://schemas.openxmlformats.org/spreadsheetml/2006/main'
        with zipfile.ZipFile(path,'w') as z:
            z.writestr('xl/workbook.xml',f'<workbook xmlns="{ns}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Log" r:id="r1"/></sheets></workbook>')
            z.writestr('xl/_rels/workbook.xml.rels','<Relationships><Relationship Id="r1" Target="worksheets/sheet1.xml"/></Relationships>')
            z.writestr('xl/sharedStrings.xml',f'<sst xmlns="{ns}"><si><t>Description</t></si><si><t>Food</t></si></sst>')
            z.writestr('xl/worksheets/sheet1.xml',('' if not entity else '<!DOCTYPE foo [<!ENTITY xx "bad">]>')+f'<worksheet xmlns="{ns}"><sheetData><row r="1"><c r="A1" t="inlineStr"><is><t>Date</t></is></c><c r="B1" t="s"><v>0</v></c><c r="C1" t="inlineStr"><is><t>Amount</t></is></c></row><row r="2"><c r="A2"><v>46054</v></c><c r="B2" t="s"><v>1</v></c><c r="C2">'+('<f>1+2</f>' if formula else '')+'<v>-12.5</v></c></row></sheetData></worksheet>')
        return path
    def test_xlsx_shared_inline_and_serial_date(self):
        path=self.make_xlsx();self.assertEqual(workbook(path)[0][0][0],'Log')
        table=read_table(path);p=preview(self.f,table,self.account,'xlsx',{'date':0,'description':1,'amount':2},date_format='excel')
        self.assertFalse(p['errors']);self.assertEqual(p['rows'][0]['delta'],-1250)
    def test_xlsx_formula_and_entities_rejected(self):
        p=preview(self.f,read_table(self.make_xlsx(True)),self.account,'xlsx',{'date':0,'description':1,'amount':2},date_format='excel')
        self.assertTrue(p['errors'])
        with self.assertRaises(ValueError):read_table(self.make_xlsx(entity=True))
    def test_old_excel_and_excess_rows_refused(self):
        p=self.root/'old.xls';p.write_text('not xlsx')
        with self.assertRaises(ValueError):read_table(p)
        p=self.root/'many.csv';p.write_text('a\n'+'b\n'*10001)
        with self.assertRaises(ValueError):read_table(p)
    def ui_fixture(self):
        p=self.root/'cash.csv';p.write_text('date,desc,amount,category,id\n2026-02-01,Food,-12.50,Food,a\n')
        ui=Mock();ui.root=self.root;ui.downloads=self.root;ui.f=self.f;ui.account.return_value=self.f.one('accounts',self.account)
        ui.choose.side_effect=[('Comma',','),'utf-8-sig','signed','ymd','.','major'];ui.required.return_value='provider';ui.money=lambda n:str(n)
        return ui
    def test_ui_cancel_has_no_writes(self):
        ui=self.ui_fixture()
        answers=['1','','1','2','3','4','5','','','','']
        with patch('builtins.input',side_effect=answers),redirect_stdout(io.StringIO()):import_ui.run(ui)
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),0)
        self.assertFalse((self.root/'Backups').exists())
    def test_ui_confirmation_imports_after_preview(self):
        ui=self.ui_fixture()
        answers=['1','','1','2','3','4','5','','','','IMPORT']
        out=io.StringIO()
        with patch('builtins.input',side_effect=answers),redirect_stdout(out):import_ui.run(ui)
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),1)
        self.assertIn('PREVIEW',out.getvalue());self.assertIn('Imported: 1',out.getvalue())

if __name__=='__main__':unittest.main()
