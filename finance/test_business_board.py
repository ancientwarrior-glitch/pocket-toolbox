from datetime import date
from pathlib import Path
import tempfile
import unittest

from engine import Finance
from business_board import board_data, render_board


class BusinessBoardTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.f = Finance(Path(self.temp.name) / 'finance.sqlite')
        self.account = self.f.account('Business', 'Cash', '1000', '2026-01-01')

    def tearDown(self):
        self.f.close()
        self.temp.cleanup()

    def stock_setup(self):
        self.raw = self.f.item('Lard', 'Material', 'g')
        self.product = self.f.item('Soap', 'Product', 'each')
        self.f.receive_stock(self.raw, '1000', '100', at='2026-01-01')
        self.f.produce('First batch', self.product, '10', [(self.raw, '500')], labor='20', overhead='10', at='2026-01-02')

    def test_blank_board_does_not_invent_records(self):
        data = board_data(self.f, date(2026, 1, 31))
        self.assertEqual(data['items'], [])
        self.assertEqual(data['batches'], [])
        self.assertEqual(data['bills'], [])
        self.assertEqual(len(data['months']), 12)
        self.assertTrue(all(m['revenue'] == m['cogs'] == 0 for m in data['months']))

    def test_stock_batch_costs_and_age(self):
        self.stock_setup()
        data = board_data(self.f, date(2026, 1, 31))
        stock = {i['name']: i for i in data['items']}
        self.assertEqual(stock['Lard']['quantity'], '500')
        self.assertEqual(stock['Soap']['value'], 8000)
        batch = data['batches'][0]
        self.assertEqual(batch['age'], 29)
        self.assertEqual(batch['cost'], 8000)
        self.assertEqual(batch['unit_cost'], '8')

    def test_credit_sale_partial_payment_and_later_return(self):
        self.stock_setup()
        sale = self.f.sell(self.product, '2', '40', party='Customer', at='2026-01-03', account=self.account, paid='10')
        self.f.return_goods(sale, '1', '20', 'Returned', at='2026-02-01')
        jan = board_data(self.f, date(2026, 1, 31))
        self.assertEqual(jan['months'][-1]['revenue'], 4000)
        self.assertEqual(jan['months'][-1]['cogs'], 1600)
        self.assertEqual(next(b for b in jan['bills'] if b['id'] == sale)['balance'], 3000)
        feb = board_data(self.f, date(2026, 2, 28))
        self.assertEqual(feb['months'][-1]['revenue'], -2000)
        self.assertEqual(feb['months'][-1]['cogs'], -800)
        self.assertEqual(next(b for b in feb['bills'] if b['id'] == sale)['balance'], 1000)

    def test_refund_credit_and_future_payment_are_not_lost(self):
        self.stock_setup()
        sale = self.f.sell(self.product, '2', '40', at='2026-01-03', account=self.account, paid='40')
        self.f.return_goods(sale, '1', '20', 'Returned', at='2026-01-04')
        self.f.refund(sale, self.account, '20', at='2026-02-01')
        jan = board_data(self.f, date(2026, 1, 31))
        self.assertEqual(next(b for b in jan['bills'] if b['id'] == sale)['balance'], -2000)
        feb = board_data(self.f, date(2026, 2, 28))
        self.assertFalse(any(b['id'] == sale for b in feb['bills']))

    def test_future_records_are_excluded_and_voided_bill_closes_on_date(self):
        item = self.f.item('Bottles', 'Material', 'each')
        self.f.receive_stock(item, '12', '120', at='2026-02-01')
        bill = self.f.invoice('Business', 'Pay', 'Expense', 'Supplier', 'Test', '10', at='2026-01-02')
        self.f.void_invoice(bill, 'Cancel', at='2026-02-01')
        jan = board_data(self.f, date(2026, 1, 31))
        self.assertEqual(jan['items'][0]['quantity'], '0')
        self.assertEqual([b['id'] for b in jan['bills']], [bill])
        self.assertFalse(any(b['id'] == bill for b in board_data(self.f, date(2026, 2, 28))['bills']))

    def test_names_cannot_inject_markup(self):
        self.f.item('</script><img src=x onerror=alert(1)>', 'Material', 'g')
        html = render_board(board_data(self.f))
        self.assertNotIn('</script><img', html)
        self.assertIn('\\u003c/script', html)
        self.assertNotIn('__DATA__', html)


if __name__ == '__main__':
    unittest.main()
