import copy,json,sqlite3,unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from engine import Finance
from statement_import import preview,commit,load,review_records

class StatementImportTests(unittest.TestCase):
    def setUp(self):
        self.tmp=TemporaryDirectory();self.root=Path(self.tmp.name);self.f=Finance(self.root/'finance.sqlite')
        self.data={'format':'pocket-statement-v1','source':'test-provider','currency':'MXN','events':[
            self.event('w','Income','100'),self.event('e','Expense','-12'),
            self.event('c','Capital','75','Business'),self.event('d','DebtPayment','-20'),
            dict(self.event('a','Advance','-10'),group='gas',party='Example'),
            dict(self.event('r','Reimbursement','10'),group='gas',date='2026-02-02'),
            self.event('i','Investment','-5'),dict(self.event('v','Review',None),evidence={'asset':'LTC','quantity':'0.01'})]}
    def event(self,key,kind,amount,scope='Personal'):
        e={'id':key,'date':'2026-02-01','scope':scope,'kind':kind,'description':'Example '+key}
        if amount is not None:e['amount']=amount
        return e
    def tearDown(self):self.f.close();self.tmp.cleanup()
    def save(self,data=None):return commit(self.f,preview(self.f,data or self.data),self.root/'Backups')
    def test_preview_readonly_commit_roles_and_repeat(self):
        before=list(self.f.db.iterdump());p=preview(self.f,self.data)
        self.assertEqual(before,list(self.f.db.iterdump()))
        result=commit(self.f,p,self.root/'Backups');self.assertEqual((result['posted'],result['review']),(7,1))
        self.assertEqual(Path(result['backup']).stat().st_mode&0o777,0o600)
        db=sqlite3.connect(result['backup']);self.assertEqual(db.execute('SELECT COUNT(*) FROM cash').fetchone()[0],0);db.close()
        self.assertEqual(len(review_records(self.f)),8)
        self.assertEqual({r['kind'] for r in self.f.rows('SELECT * FROM cash')},{'Income','Expense','Capital','DebtPayment','Advance','Reimbursement','Investment'})
        invs=self.f.rows('SELECT * FROM invoices');self.assertEqual(len(invs),2)
        self.assertTrue(all(self.f.outstanding(r['id'])==0 for r in invs))
        self.assertFalse(any(r['kind']=='Expense' for r in invs))
        self.assertEqual(self.save()['imported'],0)
        self.assertEqual(len(self.f.rows('SELECT * FROM accounts')),2)
    def test_changed_id_and_duplicate_block(self):
        self.save();d=copy.deepcopy(self.data);d['events'][0]['amount']='101'
        with self.assertRaises(ValueError):preview(self.f,d)
        d=copy.deepcopy(self.data);d['source']='other'
        with self.assertRaises(ValueError):preview(self.f,d)
    def test_stale_account_change_blocks(self):
        p=preview(self.f,self.data);self.f.account('Personal','Other','0','2020-01-01')
        with self.assertRaises(ValueError):commit(self.f,p,self.root/'Backups')
        self.assertEqual(len(review_records(self.f)),0)
    def test_atomic_rollback_after_cash_and_invoice(self):
        with patch.object(self.f,'_invoice',side_effect=ValueError('failure')):
            with self.assertRaises(ValueError):self.save()
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),0)
        self.assertEqual(len(self.f.rows('SELECT * FROM accounts')),0)
        self.assertEqual(len(review_records(self.f)),0)
    def test_validation_and_bounds(self):
        for edit in [lambda d:d['events'][0].update(amount='-1'),lambda d:d['events'][0].update(amount='NaN'),lambda d:d['events'][0].update(date=None),lambda d:d.update(currency='USD'),lambda d:d['events'][5].update(amount='11'),lambda d:d['events'][5].update(date='2020-01-01'),lambda d:d['events'][0].update(kind='transfer'),lambda d:d['events'][0].update(description='bad\x1b[31m'),lambda d:d['events'][-1].update(evidence={'escape':'\x1b'})]:
            d=copy.deepcopy(self.data);edit(d)
            with self.assertRaises((ValueError,TypeError)):preview(self.f,d)
    def test_partial_group_rejected(self):
        self.save();d=copy.deepcopy(self.data);d['events'][5]['id']='new-repayment'
        with self.assertRaises(ValueError):preview(self.f,d)
    def test_json_duplicate_keys_rejected(self):
        path=self.root/'bad.json';path.write_text('{"format":"x","format":"pocket-statement-v1"}')
        with self.assertRaises(ValueError):load(path)
    def test_restore_before_import_and_export(self):
        result=self.save()
        export=self.f.export(self.root/'Exports')
        self.assertTrue((export/'statement_events.csv').exists())
        self.f.restore(result['backup'],self.root/'RestoreBackups')
        self.assertEqual(len(review_records(self.f)),0)
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),0)
    def test_restore_older_additive_schema(self):
        old=self.f.backup(self.root/'Older')
        db=sqlite3.connect(old);db.execute('DROP TABLE statement_events');db.commit();db.close()
        self.save();self.f.restore(old,self.root/'RestoreBackups')
        self.assertEqual(len(review_records(self.f)),0)
    def test_capital_reversal_does_not_become_expense(self):
        self.save();inv=self.f.rows("SELECT * FROM invoices WHERE kind='Capital'")[0]
        self.f.void_invoice(inv['id'],'Correct funding','2026-02-03')
        amounts=[r['delta'] for r in self.f.rows("SELECT * FROM cash WHERE kind='Capital'")]
        self.assertEqual(sum(amounts),0)
        self.assertEqual(self.f.business_result('2026-02-01','2026-02-28')['revenue'],0)
    def test_edit_ordinary_statement_expense(self):
        self.save();row=self.f.rows("SELECT * FROM cash WHERE kind='Expense'")[0]
        self.f.correct_cash(row['id'],description='Corrected')
        self.assertEqual(self.f.rows('SELECT description FROM cash WHERE id=?',(row['id'],))[0][0],'Corrected')
        row=self.f.rows("SELECT * FROM cash WHERE kind='Capital'")[0]
        with self.assertRaises(ValueError):self.f.correct_cash(row['id'],void=True)

if __name__=='__main__':unittest.main()
