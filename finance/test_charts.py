from pathlib import Path
import tempfile
import unittest
import urllib.request
import urllib.error
from datetime import date
from unittest.mock import patch
from engine import Finance
from charts import dashboard_data,render,serve

class ChartTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.f=Finance(Path(self.temp.name)/'finance.sqlite')
    def tearDown(self):self.f.close();self.temp.cleanup()
    def test_empty_data_has_real_empty_states(self):
        data=dashboard_data(self.f)
        self.assertEqual(data['accounts'],[]);self.assertEqual(data['cash'],[]);self.assertEqual(len(data['months']),1)
        html=render(data);self.assertIn('No cash movements',html);self.assertNotIn('__DATA__',html)
    def test_opening_balance_and_voided_expense(self):
        account=self.f.account('Personal','Cash','100','2026-01-01')
        expense=self.f.cash_entry(account,'10','Expense','Food','2026-01-01');self.f.correct_cash(expense,void=True)
        data=dashboard_data(self.f)
        self.assertEqual(data['balances'][str(account)][0],10000);self.assertEqual(data['cash'],[])
    def test_missing_portfolio_price_stays_null(self):
        p=self.f.position('Personal','Wallet','Trading','BTC');self.f.acquire(p,'1','100',at=str(date.today()))
        data=dashboard_data(self.f);self.assertIsNone(data['portfolios'][0]['values'][-1])
    def test_data_cannot_close_script(self):
        data=dashboard_data(self.f);data['currency']='</script><script>alert(1)</script>'
        html=render(data)
        self.assertNotIn('</script><script>alert(1)',html);self.assertIn('\\u003c/script',html)
    def test_server_is_local_and_only_exposes_random_route(self):
        def open_url(url):
            self.assertTrue(url.startswith('http://127.0.0.1:'))
            with urllib.request.urlopen(url) as response:self.assertEqual(response.read(),b'<html>test</html>')
            wrong=url.rsplit('/',1)[0]+'/config.json'
            with self.assertRaises(urllib.error.HTTPError):urllib.request.urlopen(wrong)
        serve('<html>test</html>',opener=open_url,pause=lambda text:None)

if __name__=='__main__':unittest.main()
