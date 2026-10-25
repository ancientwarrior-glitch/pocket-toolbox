import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from decimal import Decimal
from engine import Finance, money, units, quantity_in

class FinanceTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(); self.root=Path(self.temp.name)
        self.f=Finance(self.root/'finance.sqlite')
        self.personal=self.f.account('Personal','Cash','1000','2020-01-01')
        self.business=self.f.account('Business','Cash','1000','2020-01-01')
    def tearDown(self): self.f.close(); self.temp.cleanup()
    def stock_setup(self):
        self.material=self.f.item('Raw material','Material','g'); self.product=self.f.item('Bar','Product','each')
        self.f.receive_stock(self.material,'1000','100',at='2026-01-01',account=self.business,paid='100')
        self.f.produce('Batch',self.product,'10',[(self.material,'500')],labor='20',overhead='10',at='2026-01-02')
    def test_decimal_validation(self):
        self.assertEqual(money('0.29'),29); self.assertEqual(units('0.000000000000000001'),Decimal('1e-18'))
        for invalid in ['NaN','Infinity','-1','1,000','0.001']:
            with self.subTest(invalid=invalid),self.assertRaises(ValueError): money(invalid)
    def test_account_balances_and_transfer_not_income(self):
        c=self.f.category('Personal','Food','Expense')
        self.f.cash_entry(self.personal,'12.50','Expense','Food','2026-01-01',c)
        self.f.transfer(self.personal,self.business,'100',fee='2',at='2026-01-02')
        self.assertEqual(self.f.balance(self.personal),88550); self.assertEqual(self.f.balance(self.business),110000)
        self.assertEqual(self.f.balance(self.personal,'2019-01-01'),None)
    def test_transfer_rollback_if_target_predates_opening(self):
        newer=self.f.account('Personal','New','0','2026-02-01')
        with self.assertRaises(ValueError): self.f.transfer(self.personal,newer,'10',at='2026-01-01')
        self.assertEqual(self.f.balance(self.personal),100000)
    def test_category_scope_and_direction(self):
        c=self.f.category('Business','Sales','Income')
        with self.assertRaises(ValueError): self.f.cash_entry(self.personal,'1','Income','Wrong',category=c)
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),0)
    def test_month_and_year_carry(self):
        self.f.cash_entry(self.personal,'100','Income','Income','2025-12-31')
        self.f.cash_entry(self.personal,'25','Expense','Expense','2026-01-01')
        self.assertEqual(self.f.balance(self.personal,'2025-12-31'),110000)
        self.assertEqual(self.f.balance(self.personal,'2026-01-01'),107500)
    def test_budget_actual(self):
        c=self.f.category('Personal','Food','Expense'); self.f.set_budget('2026-01',c,'100')
        self.f.cash_entry(self.personal,'25','Expense','Food','2026-01-01',c)
        row=self.f.budget_report('2026-01','Personal')[0]
        self.assertEqual(row['remaining'],7500)
    def test_reconciliation_audited(self):
        self.assertEqual(self.f.reconcile(self.personal,'990',at='2026-01-01'),-1000)
        self.assertEqual(self.f.balance(self.personal),99000)
        self.assertTrue(self.f.rows("SELECT * FROM audit WHERE event='reconciliation'"))
    def test_reconciliation_before_account_opening_rejected(self):
        with self.assertRaises(ValueError):self.f.reconcile(self.personal,'100',at='2019-01-01')
    def test_readable_report_export_uses_units_not_cents(self):
        self.f.cash_entry(self.personal,'12.50','Expense','Food','2026-01-01')
        path=self.f.export_cash_report('Personal','2026-01-01','2026-01-31',self.root/'exports')
        with path.open(encoding='utf-8-sig',newline='') as source:rows=list(csv.DictReader(source))
        self.assertEqual(rows[0]['Money out'],'12.50');self.assertEqual(rows[0]['Currency'],'MXN')
    def test_partial_invoice_payments(self):
        inv=self.f.invoice('Personal','Pay','Loan','Person','Debt','100',at='2026-01-01')
        self.f.pay(inv,self.personal,'30',at='2026-01-01')
        self.assertEqual(self.f.outstanding(inv),7000)
        with self.assertRaises(ValueError): self.f.pay(inv,self.personal,'71',at='2026-01-01')
        self.assertEqual(self.f.balance(self.personal),97000)
    def test_stock_purchase_and_cash_only_once(self):
        m=self.f.item('Material','Material','g')
        inv=self.f.receive_stock(m,'1000','100',account=self.business,paid='25',at='2026-01-01')
        self.f.pay(inv,self.business,'75',at='2026-01-02')
        self.assertEqual(self.f.balance(self.business),90000); self.assertEqual(self.f.stock(m),(Decimal(1000),10000))
    def test_batch_cost_frozen(self):
        self.stock_setup(); self.f.receive_stock(self.material,'1000','400',at='2026-01-03')
        batch=self.f.rows('SELECT * FROM batches')[0]
        self.assertEqual(batch['materials'],5000); self.assertEqual(self.f.stock(self.product),(Decimal(10),8000))
    def test_insufficient_production_rolls_back(self):
        self.stock_setup(); before=self.f.stock(self.material)
        with self.assertRaises(ValueError): self.f.produce('Bad',self.product,'1',[(self.material,'10000')],at='2026-01-03')
        self.assertEqual(self.f.stock(self.material),before); self.assertEqual(len(self.f.rows('SELECT * FROM batches')),1)
    def test_estimate_can_plan_more_than_stock(self):
        self.stock_setup();costs,total,unit=self.f.estimate([(self.material,'2000')],'20')
        self.assertEqual(total,20000)
        with self.assertRaises(ValueError):self.f.produce('Not enough',self.product,'20',[(self.material,'2000')],at='2026-01-03')
    def test_sale_credit_profit_and_payment_separate(self):
        self.stock_setup(); inv=self.f.sell(self.product,'2','40',at='2026-01-03',account=self.business,paid='10')
        self.assertEqual(self.f.outstanding(inv),3000)
        result=self.f.business_result('2026-01-01','2026-01-31')
        self.assertEqual(result['tracked_result'],2400); self.assertEqual(result['cogs'],1600)
        self.f.pay(inv,self.business,'30',at='2026-01-04')
        self.assertEqual(self.f.business_result('2026-01-01','2026-01-31')['tracked_result'],2400)
    def test_sale_return_refunds_and_restocks(self):
        self.stock_setup(); inv=self.f.sell(self.product,'2','40',at='2026-01-03',account=self.business,paid='40')
        self.f.void_invoice(inv,'Return',at='2026-01-04')
        self.assertEqual(self.f.stock(self.product),(Decimal(10),8000)); self.assertEqual(self.f.balance(self.business),90000)
        self.assertEqual(self.f.business_result('2026-01-01','2026-01-31')['tracked_result'],0)
    def test_consumed_receipt_cannot_be_voided(self):
        self.stock_setup()
        with self.assertRaises(ValueError): self.f.void_invoice(1,'Wrong receipt',at='2026-01-04')
    def test_inventory_loss_no_cash(self):
        self.stock_setup(); before=self.f.balance(self.business)
        self.f.loss(self.product,'1','Damaged',at='2026-01-03')
        self.assertEqual(self.f.balance(self.business),before)
        self.assertEqual(self.f.business_result('2026-01-01','2026-01-31')['losses'],800)
    def test_plans_do_not_move_cash(self):
        plan=self.f.plan('Personal','Goal','1000','2027-01-01','50'); self.f.allocate(plan,'100')
        self.assertEqual(self.f.balance(self.personal),100000)
        self.assertEqual(self.f.projection('100','10',2,'0'),Decimal('120.00'))
    def test_spot_partial_exit_cost_and_fees(self):
        p=self.f.position('Personal','Wallet','Trading','BTC')
        self.f.acquire(p,'2','100',fee='2',at='2026-01-01')
        gain=self.f.dispose(p,'1','80',fee='1',at='2026-01-02')
        self.assertEqual(gain,2800); self.assertEqual(self.f.holding(p),(Decimal(1),5100))
    def test_crypto_transfer_preserves_basis(self):
        a=self.f.position('Personal','A','Long-term','XMR'); b=self.f.position('Personal','B','Long-term','XMR')
        self.f.acquire(a,'10','100',at='2026-01-01'); self.f.transfer_holding(a,b,'4',fee_quantity='1',at='2026-01-02')
        self.assertEqual(self.f.holding(a),(Decimal(5),5000)); self.assertEqual(self.f.holding(b),(Decimal(4),4000))
        result=self.f.portfolio('Personal','Long-term','2026-01-03')
        self.assertEqual(result['realized'],-1000); self.assertIsNone(result['value'])
    def test_third_asset_fee(self):
        a=self.f.position('Personal','A','Trading','BTC'); b=self.f.position('Personal','A','Trading','BNB')
        self.f.acquire(a,'1','100',at='2026-01-01'); self.f.acquire(b,'2','10',at='2026-01-01')
        self.f.dispose(a,'1','150',fee='6',fee_position=b,fee_quantity='1',at='2026-01-02')
        self.assertEqual(self.f.holding(b),(Decimal(1),500))
        self.assertEqual(self.f.portfolio('Personal','Trading','2026-01-02')['realized'],4500)
    def test_swap(self):
        a=self.f.position('Personal','A','Trading','BTC'); b=self.f.position('Personal','A','Trading','USDT')
        self.f.acquire(a,'1','100',at='2026-01-01'); self.f.swap(a,b,'1','150','150',at='2026-01-02')
        self.assertEqual(self.f.holding(a),(Decimal(0),0)); self.assertEqual(self.f.holding(b),(Decimal(150),15000))
        self.assertEqual(self.f.portfolio('Personal','Trading','2026-01-02')['realized'],5000)
    def test_cross_portfolio_reclassification_no_gain(self):
        a=self.f.position('Personal','A','Trading','BTC');b=self.f.position('Personal','A','Long-term','BTC')
        self.f.acquire(a,'2','100',at='2026-01-01');self.f.transfer_holding(a,b,'1',at='2026-01-02')
        self.assertEqual(self.f.holding(a),(Decimal(1),5000));self.assertEqual(self.f.holding(b),(Decimal(1),5000))
        self.assertEqual(self.f.portfolio('Personal','Trading','2026-01-02')['realized'],0)
        self.assertEqual(self.f.portfolio('Personal','Trading','2026-01-02')['net_contributions'],5000)
        self.assertEqual(self.f.portfolio('Personal','Long-term','2026-01-02')['net_contributions'],5000)
    def test_swap_external_fee_debited_once(self):
        a=self.f.position('Personal','A','Trading','BTC');b=self.f.position('Personal','A','Trading','USDT')
        self.f.acquire(a,'1','100',at='2026-01-01');self.f.swap(a,b,'1','150','150','2',at='2026-01-02',fee_account=self.personal)
        self.assertEqual(self.f.balance(self.personal),99800);self.assertEqual(self.f.holding(b),(Decimal(150),15200))
    def test_timestamped_valuation(self):
        p=self.f.position('Personal','A','Holding','BTC'); self.f.acquire(p,'1','100',at='2026-01-01')
        self.f.price('BTC','10',at='2026-01-01',quote='USD',fx='20'); self.f.price('BTC','300',at='2026-02-01')
        self.assertEqual(self.f.portfolio('Personal','Holding','2026-01-31')['value'],20000)
        self.assertEqual(self.f.portfolio('Personal','Holding','2026-02-01')['value'],30000)
    def test_no_negative_holdings(self):
        p=self.f.position('Personal','A','Trading','BTC'); self.f.acquire(p,'1','100',at='2026-01-01')
        with self.assertRaises(ValueError): self.f.dispose(p,'2','200',at='2026-01-02')
        self.assertEqual(self.f.holding(p),(Decimal(1),10000))
    def test_trade_plan(self):
        result=self.f.trade_plan('Personal','Trading','BTC','Long','2','100','90','120','Test')
        self.assertEqual(Decimal(result['ratio']),2)
        with self.assertRaises(ValueError): self.f.trade_plan('Personal','Trading','BTC','Long','2','100','110','120')
    def test_linear_contract(self):
        c=self.f.contract('Personal','Exchange','Linear','Long','2','100','50',fee='1')
        self.assertEqual(self.f.close_contract(c,'110',fee='1',funding='-2'),1600)
        with self.assertRaises(ValueError): self.f.close_contract(c,'110')
    def test_export_backup(self):
        export=self.f.export(self.root/'exports'); self.assertTrue((export/'cash.csv').exists())
        backup=self.f.backup(self.root/'backups'); db=sqlite3.connect(backup)
        self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok'); db.close()

    def test_unit_conversions(self):
        self.assertEqual(quantity_in('2.5 kg','g'),2500)
        self.assertEqual(quantity_in('0.5 l','ml'),500)
        with self.assertRaises(ValueError):quantity_in('2 kg','ml')
    def test_opening_stock_does_not_repeat_cash(self):
        item=self.f.item('Existing','Material','g'); self.f.opening_stock(item,'100','12',at='2026-01-01')
        self.assertEqual(self.f.stock(item),(Decimal(100),1200))
        self.assertEqual(self.f.balance(self.business),100000)
        self.assertFalse(self.f.rows('SELECT * FROM invoices'))
        with self.assertRaises(ValueError):self.f.opening_stock(item,'100','12',at='2026-01-01')
    def test_cash_correction_and_void_audit(self):
        ident=self.f.cash_entry(self.personal,'10','Expense','Wrong','2026-01-01')
        self.f.correct_cash(ident,value='12',description='Correct')
        self.assertEqual(self.f.balance(self.personal),98800)
        self.f.correct_cash(ident,void=True); self.assertEqual(self.f.balance(self.personal),100000)
        self.assertEqual(len(self.f.rows("SELECT * FROM audit WHERE event='cash correction'")),2)
    def test_linked_payment_cannot_be_directly_edited(self):
        inv=self.f.invoice('Personal','Pay','Loan','P','Debt','10',at='2026-01-01');self.f.pay(inv,self.personal,'5',at='2026-01-01')
        ident=self.f.rows('SELECT id FROM cash')[0][0]
        with self.assertRaises(ValueError):self.f.correct_cash(ident,value='2')
    def test_returns_do_not_erase_earlier_period(self):
        self.stock_setup();inv=self.f.sell(self.product,'2','40',at='2026-01-03',account=self.business,paid='40')
        self.f.void_invoice(inv,'Later return',at='2026-02-01')
        self.assertEqual(self.f.business_result('2026-01-01','2026-01-31')['tracked_result'],2400)
        self.assertEqual(self.f.business_result('2026-02-01','2026-02-28')['tracked_result'],-2400)
    def test_partial_paid_sale_return_and_refund(self):
        self.stock_setup();inv=self.f.sell(self.product,'4','80',at='2026-01-03',account=self.business,paid='80')
        self.f.return_goods(inv,'1','20','One returned',at='2026-02-01')
        self.assertEqual(self.f.invoice_balance(inv),-2000)
        self.assertEqual(self.f.stock(self.product),(Decimal(7),5600))
        self.f.refund(inv,self.business,'10',at='2026-02-02');self.assertEqual(self.f.invoice_balance(inv),-1000)
        self.f.refund(inv,self.business,'10',at='2026-02-03');self.assertEqual(self.f.invoice_balance(inv),0)
        self.assertEqual(self.f.business_result('2026-01-01','2026-01-31')['tracked_result'],4800)
        self.assertEqual(self.f.business_result('2026-02-01','2026-02-28')['tracked_result'],-1200)
    def test_partial_credit_sale_return_reduces_receivable(self):
        self.stock_setup();inv=self.f.sell(self.product,'4','80',at='2026-01-03',account=self.business,paid='20')
        self.f.return_goods(inv,'1','20','Returned',at='2026-01-04')
        self.assertEqual(self.f.outstanding(inv),4000)
        with self.assertRaises(ValueError):self.f.refund(inv,self.business,'1',at='2026-01-04')
    def test_partial_return_cannot_exceed_quantity(self):
        self.stock_setup();inv=self.f.sell(self.product,'2','40',at='2026-01-03')
        with self.assertRaises(ValueError):self.f.return_goods(inv,'3','40','Too many',at='2026-01-04')
        self.assertFalse(self.f.rows('SELECT * FROM credits'))
    def test_supplier_return_after_partial_use(self):
        self.stock_setup();self.f.return_goods(1,'100','10','Supplier return',at='2026-01-03')
        self.assertEqual(self.f.stock(self.material),(Decimal(400),4000))
        self.assertEqual(self.f.invoice_balance(1),-1000)
        self.f.refund(1,self.business,'10',at='2026-01-04');self.assertEqual(self.f.invoice_balance(1),0)
    def test_refund_reduces_category_actual(self):
        cat=self.f.category('Personal','Supplies','Expense');inv=self.f.invoice('Personal','Pay','Expense','Shop','Bill','50',at='2026-01-01',category=cat)
        self.f.pay(inv,self.personal,'50',at='2026-01-01');self.f.void_invoice(inv,'Cancelled',at='2026-01-02')
        self.assertEqual(self.f.budget_report('2026-01','Personal')[0]['actual'],0)
    def test_profit_share_requires_explicit_basis_and_no_duplicate(self):
        inv=self.f.profit_share('Partner','2026-01-01','2026-01-31','1000','5')
        self.assertEqual(self.f.outstanding(inv),5000)
        with self.assertRaises(sqlite3.IntegrityError):self.f.profit_share('Partner','2026-01-01','2026-01-31','1000','5')
        self.assertEqual(len(self.f.rows('SELECT * FROM invoices')),1)
    def test_finance_restore(self):
        backup=self.f.backup(self.root/'backups');self.f.cash_entry(self.personal,'10','Expense','Later')
        previous=self.f.restore(backup,self.root/'backups')
        self.assertTrue(previous.exists());self.assertEqual(self.f.balance(self.personal),100000)
    def test_invalid_restore_leaves_current_data(self):
        bad=self.root/'bad.sqlite';db=sqlite3.connect(bad);db.execute('CREATE TABLE fake(x)');db.close()
        with self.assertRaises(ValueError):self.f.restore(bad,self.root/'backups')
        self.assertEqual(self.f.balance(self.personal),100000)
    def test_legacy_import_idempotent_and_source_unchanged(self):
        original=self.root/'old.sqlite';db=sqlite3.connect(original)
        db.executescript('CREATE TABLE entries(id INTEGER PRIMARY KEY,date TEXT,scope TEXT,kind TEXT,description TEXT,cents INTEGER,debt INTEGER);CREATE TABLE debts(id INTEGER PRIMARY KEY,scope TEXT,person TEXT,direction TEXT,cents INTEGER);')
        db.execute('INSERT INTO entries VALUES(1,?,?,?,?,?,NULL)',('2026-01-01','Personal','Income','Example',1000))
        db.execute('INSERT INTO debts VALUES(1,?,?,?,?)',('Personal','Person','Owe',5000));db.commit();db.close()
        purchase=self.root/'purchases.csv'
        with purchase.open('w',newline='') as out:
            writer=csv.writer(out);writer.writerow(['Date','Item','Quantity','Total MXN','Note']);writer.writerow(['2026-01-01','Example','1 g','5',''])
        before=original.read_bytes();first=self.f.import_legacy(original,purchase);second=self.f.import_legacy(original,purchase)
        self.assertEqual(first,dict(entries=1,debts=1,purchases=1,skipped=0))
        self.assertEqual(second,dict(entries=0,debts=0,purchases=0,skipped=0))
        self.assertEqual(original.read_bytes(),before)
        self.assertEqual(len(self.f.rows('SELECT * FROM cash')),2)

    def write_trades(self,rows):
        path=self.root/'trades.csv'
        with path.open('w',newline='') as output:
            writer=csv.writer(output);writer.writerow(['source','id','date','event','scope','wallet','portfolio','asset','quantity','total_base','fee_base']);writer.writerows(rows)
        return path
    def test_trade_csv_idempotent(self):
        path=self.write_trades([['example','1','2026-01-01','Buy','Personal','A','Trading','BTC','1','100','1'],['example','2','2026-01-02','Sell','Personal','A','Trading','BTC','0.5','80','1']])
        self.assertEqual(self.f.import_trades(path),dict(imported=2,duplicates_skipped=0))
        self.assertEqual(self.f.import_trades(path),dict(imported=0,duplicates_skipped=2))
        self.assertEqual(self.f.rows('SELECT COUNT(*) FROM investment_events')[0][0],2)
    def test_trade_csv_all_or_nothing(self):
        path=self.write_trades([['example','1','2026-01-01','Buy','Personal','A','Trading','BTC','1','100','0'],['example','2','2026-01-02','Sell','Personal','A','Trading','BTC','2','200','0']])
        with self.assertRaises(ValueError):self.f.import_trades(path)
        self.assertFalse(self.f.rows('SELECT * FROM positions'));self.assertFalse(self.f.rows('SELECT * FROM imports'))

if __name__=='__main__': unittest.main()
