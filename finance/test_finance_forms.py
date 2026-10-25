from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import json
import unittest
import urllib.request
import urllib.error

from engine import Finance
from board_actions import BoardActions
from finance_forms import form_state,render_view,open_view


class FinanceFormTests(unittest.TestCase):
    def setUp(self):
        self.temp=TemporaryDirectory();self.home=Path(self.temp.name)
        self.f=Finance(self.home/'Workspace/Finance/finance.sqlite')
        self.account=self.f.account('Business','Cash','1000','2026-01-01')
        self.personal=self.f.account('Personal','Cash','1000','2026-01-01')
        self.material=self.f.item('Lard','Material','g')
        self.product=self.f.item('Soap','Product','each')
        self.actions=BoardActions(self.home,self.f.path);self.sequence=0

    def tearDown(self):self.f.close();self.temp.cleanup()

    def submit(self,action,**fields):
        self.sequence+=1
        request=dict(action=action,request_id=f'form-test-request-{self.sequence:04}',**fields)
        self.actions(request)
        return request

    def stock(self):
        self.submit('stock-receive',item=self.material,quantity='1 kg',total='100',party='Supplier',account=self.account,paid='100',day='2026-01-02')

    def produce(self,quantity='10'):
        return self.submit('batch-produce',name='Soap batch',product=self.product,quantity=quantity,
                           ingredients=[dict(item=self.material,quantity='500 g')],labor='20',overhead='10',day='2026-01-03')

    def test_receipt_production_sale_and_payment_share_ledger(self):
        self.stock();self.produce()
        request=self.submit('product-sale',item=self.product,quantity='2',total='40',party='Buyer',paid='10',account=self.account,day='2026-01-04')
        BoardActions(self.home,self.f.path)(request)
        self.assertEqual(str(self.f.stock(self.material)[0]),'500')
        self.assertEqual(self.f.stock(self.product),(8,6400))
        invoice=self.f.rows("SELECT * FROM invoices WHERE kind='Sale'")[0]['id']
        self.assertEqual(self.f.invoice_balance(invoice),3000)
        self.submit('invoice-payment',invoice=invoice,account=self.account,mode='Payment',amount='30',day='2026-01-05')
        self.assertEqual(self.f.invoice_balance(invoice),0)
        self.assertEqual(self.f.balance(self.account),94000)
        self.assertEqual(len(self.f.rows('SELECT * FROM sales')),1)

    def test_short_stock_rolls_back_batch_and_receipt(self):
        self.stock()
        with self.assertRaises(ValueError):
            self.submit('batch-produce',name='Too much',product=self.product,quantity='10',ingredients=[dict(item=self.material,quantity='2 kg')],labor='0',overhead='0',day='2026-01-03')
        self.assertEqual(len(self.f.rows('SELECT * FROM batches')),0)
        self.assertEqual(self.f.stock(self.product),(0,0))
        self.assertEqual(len(self.f.rows('SELECT * FROM imports')),1)

    def test_invalid_paid_amount_rolls_back_sale_and_stock(self):
        self.stock();self.produce()
        with self.assertRaises(ValueError):
            self.submit('product-sale',item=self.product,quantity='2',total='40',party='Buyer',paid='50',account=self.account,day='2026-01-04')
        self.assertEqual(self.f.stock(self.product),(10,8000))
        self.assertEqual(len(self.f.rows('SELECT * FROM sales')),0)

    def test_material_purchase_cannot_use_personal_cash(self):
        with self.assertRaisesRegex(ValueError,'Business account'):
            self.submit('stock-receive',item=self.material,quantity='1 kg',total='100',party='Supplier',paid='100',account=self.personal,day='2026-01-02')
        self.assertEqual(self.f.stock(self.material),(0,0))

    def test_opening_stock_does_not_create_payment_and_rejects_repeat(self):
        request=self.submit('stock-opening',item=self.material,quantity='500 g',total='50',description='Already owned',day='2026-01-02')
        BoardActions(self.home,self.f.path)(request)
        self.assertEqual(self.f.stock(self.material),(500,5000))
        self.assertEqual(self.f.rows('SELECT * FROM cash'),[])
        with self.assertRaises(ValueError):
            self.submit('stock-opening',item=self.material,quantity='500',total='50',description='Duplicate opening',day='2026-01-02')

    def test_refund_uses_existing_credit(self):
        self.stock();self.produce()
        sale=self.f.sell(self.product,'2','40',at='2026-01-04',account=self.account,paid='40')
        self.f.return_goods(sale,'1','20','Returned',at='2026-01-05')
        request=self.submit('invoice-payment',invoice=sale,account=self.account,mode='Refund',amount='20',day='2026-01-06')
        BoardActions(self.home,self.f.path)(request)
        self.assertEqual(self.f.invoice_balance(sale),0)
        self.assertEqual(self.f.balance(self.account),92000)

    def test_budget_and_goal_planning_do_not_move_cash(self):
        category=self.f.category('Personal','Food','Expense')
        self.submit('budget-set',category=category,month='2026-01',amount='200')
        request=self.submit('goal-add',scope='Business',name='Molds',target='1000',monthly='100',due='2026-12-01')
        BoardActions(self.home,self.f.path)(request)
        goal=self.f.rows('SELECT * FROM envelopes')[0]['id']
        self.submit('goal-allocate',goal=goal,amount='50',committed=False)
        self.assertEqual(self.f.one('envelopes',goal)['allocated'],5000)
        self.assertEqual(self.f.balance(self.account),100000)
        self.assertEqual(self.f.budget_report('2026-01','Personal')[0]['planned'],20000)

    def test_budget_requires_expense_category(self):
        category=self.f.category('Personal','Wages','Income')
        with self.assertRaisesRegex(ValueError,'expense category'):
            self.submit('budget-set',category=category,month='2026-01',amount='200')
        self.assertEqual(self.f.rows('SELECT * FROM budgets'),[])

    def test_item_creation_and_invalid_id_types(self):
        request=self.submit('item-add',name='Bottles',kind='Material',unit='each')
        BoardActions(self.home,self.f.path)(request)
        self.assertEqual(len(self.f.rows("SELECT * FROM items WHERE name='Bottles'")),1)
        with self.assertRaises(ValueError):
            self.submit('stock-opening',item=True,quantity='10',total='0',description='Invalid',day='2026-01-02')

    def test_manual_price_updates_valuation_without_moving_cash(self):
        position=self.f.position('Personal','Wallet','Long term','BTC')
        self.f.acquire(position,'0.01','100',at='2026-01-02')
        request=self.submit('price-set',asset='BTC',price='100',quote='USD',fx='20',day='2026-01-03')
        BoardActions(self.home,self.f.path)(request)
        self.assertEqual(self.f.portfolio('Personal','Long term','2026-01-03')['value'],2000)
        self.assertEqual(self.f.balance(self.personal),100000)

    def test_forms_escape_labels_and_both_views_have_forms(self):
        self.f.item('</script><img src=x>','Material','g')
        for mode in ('finance','business'):
            html=render_view(self.f.path,mode)
            self.assertIn('Review entry',html)
            self.assertNotIn('__FORM_DATA__',html)
            self.assertNotIn('</script><img',html)
            self.assertIn('\\u003c/script',html)

    def test_standalone_business_board_accepts_same_local_actions(self):
        def opener(url):
            with urllib.request.urlopen(url) as response:self.assertIn(b'Add & update records',response.read())
            request=dict(action='item-add',name='New material',kind='Material',unit='each',request_id='standalone-form-test')
            req=urllib.request.Request(url+'/api',data=json.dumps(request).encode(),headers={'Origin':url.rsplit('/',1)[0],'Content-Type':'application/json'})
            with urllib.request.urlopen(req) as response:self.assertTrue(json.load(response)['ok'])
            with urllib.request.urlopen(url) as response:self.assertIn(b'New material',response.read())
        open_view(self.f,'business',home=self.home,opener=opener,pause=lambda _:None)


if __name__=='__main__':unittest.main()
