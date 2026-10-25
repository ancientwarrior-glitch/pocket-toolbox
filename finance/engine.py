"""Pocket Finance beta. Offline records; integer base-currency cents, Decimal units."""
from pathlib import Path
from datetime import datetime, date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP, localcontext
from contextlib import contextmanager
import csv
import hashlib
import json
import sqlite3
from pocket_security import private_dir,private_file,private_umask

VERSION = '0.2.1-beta'

def decimal(value):
    try: number = Decimal(str(value).strip())
    except InvalidOperation: raise ValueError('Use a decimal number, without commas.')
    if not number.is_finite(): raise ValueError('Number must be finite.')
    return number

def units(value):
    number = decimal(value)
    if number <= 0 or number>Decimal('1e30') or number.as_tuple().exponent < -18: raise ValueError('Quantity must be positive, at most 1e30, with at most 18 decimals.')
    return number

def money(value, signed=False):
    number = decimal(value)
    if not signed and number < 0: raise ValueError('Amount cannot be negative.')
    if number*100 != (number*100).to_integral_value(): raise ValueError('Use at most two decimals for money.')
    cents = int(number*100)
    if abs(cents) > 10**15: raise ValueError('Amount is too large.')
    return cents

def round_cents(value):
    result=int(decimal(value).quantize(Decimal('1'), rounding=ROUND_HALF_UP))
    if abs(result)>10**15:raise ValueError('Calculated monetary amount is too large.')
    return result

def day(value=None):
    text = str(value or date.today())
    if date.fromisoformat(text).isoformat() != text: raise ValueError('Use YYYY-MM-DD.')
    return text

def now(): return datetime.now().astimezone().isoformat(timespec='microseconds')

def portion(total, used, available):
    used, available = decimal(used), decimal(available)
    if used > available or used <= 0: raise ValueError('Insufficient quantity.')
    return total if used == available else round_cents(Decimal(total)*used/available)

def quantity_in(value, unit):
    parts=str(value).strip().split()
    if len(parts)>2 or not parts: raise ValueError('Use a quantity, optionally followed by g, kg, ml, l or each.')
    q=units(parts[0]); suffix=parts[1].lower() if len(parts)==2 else unit
    conversion={('g','g'):1,('kg','g'):1000,('ml','ml'):1,('l','ml'):1000,('each','each'):1}
    if (suffix,unit) not in conversion: raise ValueError('Quantity unit does not match the item.')
    return q*conversion[(suffix,unit)]

class Finance:
    def __init__(self, path, base='MXN'):
        private_umask()
        self.path = Path(path)
        private_dir(self.path.parent);private_file(self.path)
        self.db = sqlite3.connect(self.path)
        self.db.row_factory = sqlite3.Row
        self.db.execute('PRAGMA foreign_keys=ON')
        self.db.executescript('''
        CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,at TEXT,event TEXT,details TEXT);
        CREATE TABLE IF NOT EXISTS accounts(id INTEGER PRIMARY KEY,scope TEXT,name TEXT,opening INTEGER,start TEXT,UNIQUE(scope,name));
        CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY,scope TEXT,name TEXT,kind TEXT,UNIQUE(scope,name,kind));
        CREATE TABLE IF NOT EXISTS cash(id INTEGER PRIMARY KEY,day TEXT,account INTEGER REFERENCES accounts(id),category INTEGER REFERENCES categories(id),delta INTEGER,kind TEXT,description TEXT,ref TEXT,created TEXT,void INTEGER DEFAULT 0);
        CREATE TABLE IF NOT EXISTS budgets(month TEXT,category INTEGER REFERENCES categories(id),amount INTEGER,PRIMARY KEY(month,category));
        CREATE TABLE IF NOT EXISTS envelopes(id INTEGER PRIMARY KEY,scope TEXT,name TEXT,target INTEGER,due TEXT,contribution INTEGER,allocated INTEGER DEFAULT 0,committed INTEGER DEFAULT 0,UNIQUE(scope,name));
        CREATE TABLE IF NOT EXISTS items(id INTEGER PRIMARY KEY,name TEXT,kind TEXT,unit TEXT,UNIQUE(name,kind));
        CREATE TABLE IF NOT EXISTS stock(id INTEGER PRIMARY KEY,day TEXT,item INTEGER REFERENCES items(id),qty TEXT,value INTEGER,reason TEXT,ref TEXT);
        CREATE TABLE IF NOT EXISTS invoices(id INTEGER PRIMARY KEY,day TEXT,scope TEXT,direction TEXT,kind TEXT,party TEXT,description TEXT,total INTEGER,category INTEGER REFERENCES categories(id),void INTEGER DEFAULT 0,void_day TEXT);
        CREATE TABLE IF NOT EXISTS payments(id INTEGER PRIMARY KEY,invoice INTEGER REFERENCES invoices(id),cash INTEGER REFERENCES cash(id),amount INTEGER);
        CREATE TABLE IF NOT EXISTS credits(id INTEGER PRIMARY KEY,day TEXT,invoice INTEGER REFERENCES invoices(id),qty TEXT,total INTEGER,stock_value INTEGER,kind TEXT,reason TEXT);
        CREATE TABLE IF NOT EXISTS batches(id INTEGER PRIMARY KEY,day TEXT,name TEXT,product INTEGER REFERENCES items(id),quantity TEXT,materials INTEGER,labor INTEGER,overhead INTEGER,created TEXT);
        CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY,invoice INTEGER REFERENCES invoices(id),item INTEGER REFERENCES items(id),qty TEXT,cogs INTEGER);
        CREATE TABLE IF NOT EXISTS imports(source TEXT,key TEXT,digest TEXT,PRIMARY KEY(source,key));
        CREATE TABLE IF NOT EXISTS positions(id INTEGER PRIMARY KEY,scope TEXT,wallet TEXT,portfolio TEXT,asset TEXT,UNIQUE(scope,wallet,portfolio,asset));
        CREATE TABLE IF NOT EXISTS holding_moves(id INTEGER PRIMARY KEY,day TEXT,position INTEGER REFERENCES positions(id),qty TEXT,basis INTEGER,event INTEGER);
        CREATE TABLE IF NOT EXISTS investment_events(id INTEGER PRIMARY KEY,day TEXT,scope TEXT,portfolio TEXT,kind TEXT,asset TEXT,qty TEXT,proceeds INTEGER,basis INTEGER,fees INTEGER,gain INTEGER,flow INTEGER,description TEXT,created TEXT);
        CREATE TABLE IF NOT EXISTS prices(asset TEXT,day TEXT,price TEXT,quote TEXT,fx TEXT,PRIMARY KEY(asset,day));
        CREATE TABLE IF NOT EXISTS trade_plans(id INTEGER PRIMARY KEY,at TEXT,scope TEXT,portfolio TEXT,asset TEXT,side TEXT,qty TEXT,entry TEXT,stop TEXT,target TEXT,thesis TEXT,status TEXT,attachment TEXT);
        CREATE TABLE IF NOT EXISTS journal(id INTEGER PRIMARY KEY,at TEXT,topic TEXT,text TEXT,attachment TEXT);
        CREATE TABLE IF NOT EXISTS contracts(id INTEGER PRIMARY KEY,scope TEXT,wallet TEXT,symbol TEXT,side TEXT,qty TEXT,multiplier TEXT,entry TEXT,collateral INTEGER,fees INTEGER,funding INTEGER DEFAULT 0,closed TEXT,exit TEXT,realized INTEGER,notes TEXT);
        CREATE TABLE IF NOT EXISTS distributions(id INTEGER PRIMARY KEY,party TEXT,start TEXT,end TEXT,approved_profit INTEGER,rate TEXT,amount INTEGER,invoice INTEGER REFERENCES invoices(id),UNIQUE(party,start,end));
        ''')
        if 'void' not in [r[1] for r in self.db.execute('PRAGMA table_info(cash)')]:
            self.db.execute('ALTER TABLE cash ADD COLUMN void INTEGER DEFAULT 0')
        if 'void_day' not in [r[1] for r in self.db.execute('PRAGMA table_info(invoices)')]:
            self.db.execute('ALTER TABLE invoices ADD COLUMN void_day TEXT')
        existing = self.db.execute("SELECT value FROM settings WHERE key='base'").fetchone()
        if not existing: self.db.execute('INSERT INTO settings VALUES(?,?)',('base',base))
        self.base = existing[0] if existing else base
        self.db.commit()

    def close(self): self.db.close()
    def rows(self, sql, args=()): return list(self.db.execute(sql,args))
    def one(self, table, ident):
        if table not in {'accounts','categories','items','invoices','envelopes','positions','contracts','trade_plans','batches'}: raise ValueError('Unknown record type.')
        row = self.db.execute('SELECT * FROM '+table+' WHERE id=?',(ident,)).fetchone()
        if row is None: raise ValueError('Record not found.')
        return row

    @contextmanager
    def transaction(self, event, details):
        nested=self.db.in_transaction
        savepoint='finance_nested_'+str(id(details))
        self.db.execute('SAVEPOINT '+savepoint if nested else 'BEGIN IMMEDIATE')
        try:
            yield
            self.db.execute('INSERT INTO audit VALUES(NULL,?,?,?)',(now(),event,json.dumps(details,default=str,ensure_ascii=False)))
            if nested:self.db.execute('RELEASE '+savepoint)
            else:self.db.commit()
        except BaseException:
            if nested:
                self.db.execute('ROLLBACK TO '+savepoint);self.db.execute('RELEASE '+savepoint)
            else:self.db.rollback()
            raise

    def account(self, scope, name, opening='0', start=None):
        self.check_scope(scope)
        if not name.strip(): raise ValueError('Account name is required.')
        value, start = money(opening,True), day(start)
        with self.transaction('account',dict(scope=scope,name=name,opening=value,start=start)):
            return self.db.execute('INSERT INTO accounts VALUES(NULL,?,?,?,?)',(scope,name.strip(),value,start)).lastrowid

    def check_scope(self, scope):
        if scope not in ('Personal','Business'): raise ValueError('Choose Personal or Business.')

    def category(self, scope, name, kind):
        self.check_scope(scope)
        if kind not in ('Income','Expense') or not name.strip(): raise ValueError('Category needs a name and Income/Expense kind.')
        with self.transaction('category',dict(scope=scope,name=name,kind=kind)):
            self.db.execute('INSERT OR IGNORE INTO categories VALUES(NULL,?,?,?)',(scope,name.strip(),kind))
            return self.db.execute('SELECT id FROM categories WHERE scope=? AND name=? AND kind=?',(scope,name.strip(),kind)).fetchone()[0]

    def _cash(self, account, delta, kind, description, at, category=None, ref=None):
        record = self.one('accounts',account)
        at = day(at)
        if at < record['start']: raise ValueError('Payment predates the account opening date.')
        if category:
            cat = self.one('categories',category)
            if cat['scope'] != record['scope']: raise ValueError('Account/category belong to different scopes.')
            if kind!='Refund' and (delta>0) != (cat['kind']=='Income'): raise ValueError('Category direction does not match payment.')
        return self.db.execute('INSERT INTO cash(day,account,category,delta,kind,description,ref,created) VALUES(?,?,?,?,?,?,?,?)',(at,account,category,delta,kind,description,ref,now())).lastrowid

    def cash_entry(self, account, value, direction, description, at=None, category=None):
        cents = money(value)
        if cents<=0 or direction not in ('Income','Expense'): raise ValueError('Choose income/expense and a positive amount.')
        delta = cents if direction=='Income' else -cents
        with self.transaction('cash entry',dict(account=account,delta=delta,description=description)):
            return self._cash(account,delta,direction,description,at,category)

    def transfer(self, source, target, value, at=None, fee='0'):
        if source==target: raise ValueError('Choose two different accounts.')
        cents, charge = money(value), money(fee)
        if cents<=0: raise ValueError('Transfer must be positive.')
        ref = 'transfer:'+now()
        with self.transaction('transfer',dict(source=source,target=target,value=cents,fee=charge)):
            self._cash(source,-cents,'Transfer','Transfer out',at,ref=ref)
            self._cash(target,cents,'Transfer','Transfer in',at,ref=ref)
            if charge: self._cash(source,-charge,'Expense','Transfer fee',at)

    def balance(self, account, through='9999-12-31'):
        row = self.one('accounts',account)
        if through < row['start']: return None
        return row['opening']+self.db.execute('SELECT COALESCE(SUM(delta),0) FROM cash WHERE account=? AND day<=? AND void=0',(account,through)).fetchone()[0]

    def correct_cash(self,ident,value=None,description=None,at=None,category=None,void=False):
        old=self.db.execute('SELECT * FROM cash WHERE id=?',(ident,)).fetchone()
        if old is None or old['void']: raise ValueError('Active cash entry not found.')
        if old['ref'] and not old['ref'].startswith(('legacy-entry:','legacy-purchase:')): raise ValueError('This is a linked event. Reverse or correct the originating invoice, transfer or investment instead.')
        new=dict(old)
        if value is not None:
            cents=money(value)
            if cents<=0: raise ValueError('Use a positive amount.')
            new['delta']=cents if old['delta']>0 else -cents
        if description is not None: new['description']=description
        if at is not None: new['day']=day(at)
        if category is not None:
            cat=self.one('categories',category)
            if cat['scope']!=self.one('accounts',old['account'])['scope'] or (new['delta']>0)!=(cat['kind']=='Income'): raise ValueError('Category mismatch.')
            new['category']=category
        if new['day']<self.one('accounts',old['account'])['start']: raise ValueError('Entry predates account opening.')
        new['void']=int(void)
        with self.transaction('cash correction',dict(before=dict(old),after=new)):
            self.db.execute('UPDATE cash SET day=?,delta=?,description=?,category=?,void=? WHERE id=?',(new['day'],new['delta'],new['description'],new['category'],new['void'],ident))

    def reconcile(self, account, actual, at=None, explanation='Counted balance'):
        at = day(at)
        actual = money(actual,True)
        recorded=self.balance(account,at)
        if recorded is None:raise ValueError('Reconciliation predates account opening.')
        difference = actual-recorded
        if difference:
            with self.transaction('reconciliation',dict(account=account,actual=actual,difference=difference,explanation=explanation)):
                self._cash(account,difference,'Adjustment',explanation,at)
        return difference

    def set_budget(self, month, category, value):
        month = datetime.strptime(month,'%Y-%m').strftime('%Y-%m')
        self.one('categories',category)
        with self.transaction('budget',dict(month=month,category=category,value=value)):
            self.db.execute('INSERT OR REPLACE INTO budgets VALUES(?,?,?)',(month,category,money(value)))

    def budget_report(self, month, scope):
        month = datetime.strptime(month,'%Y-%m').strftime('%Y-%m')
        result=[]
        for cat in self.rows('SELECT * FROM categories WHERE scope=? ORDER BY kind,name',(scope,)):
            planned=self.db.execute('SELECT amount FROM budgets WHERE month=? AND category=?',(month,cat['id'])).fetchone()
            actual=self.db.execute("SELECT COALESCE(SUM(CASE WHEN kind='Refund' THEN -ABS(delta) ELSE ABS(delta) END),0) FROM cash WHERE substr(day,1,7)=? AND category=? AND kind IN ('Income','Expense','Payment','Legacy','Refund') AND void=0",(month,cat['id'])).fetchone()[0]
            result.append(dict(category=cat['name'],kind=cat['kind'],planned=planned[0] if planned else None,actual=actual,remaining=planned[0]-actual if planned else None))
        return result

    def item(self,name,kind,unit):
        if kind not in ('Material','Product') or unit not in ('g','ml','each'): raise ValueError('Use Material/Product and g/ml/each.')
        if not name.strip(): raise ValueError('Item name required.')
        with self.transaction('item',dict(name=name,kind=kind,unit=unit)):
            return self.db.execute('INSERT INTO items VALUES(NULL,?,?,?)',(name.strip(),kind,unit)).lastrowid

    def stock(self,item,through='9999-12-31'):
        self.one('items',item)
        rows=self.rows('SELECT qty,value FROM stock WHERE item=? AND day<=? ORDER BY id',(item,through))
        return sum((decimal(r['qty']) for r in rows),Decimal(0)),sum(r['value'] for r in rows)

    def _stock(self,item,quantity,value,reason,at,ref):
        self.one('items',item)
        at=day(at)
        latest=self.db.execute('SELECT MAX(day) FROM stock WHERE item=?',(item,)).fetchone()[0]
        if latest and at<latest: raise ValueError('Stock events must be recorded in date order for each item.')
        oldq,oldv=self.stock(item)
        if oldq+quantity<0 or oldv+value<0: raise ValueError('Insufficient stock or stock value.')
        self.db.execute('INSERT INTO stock VALUES(NULL,?,?,?,?,?,?)',(at,item,str(quantity),value,reason,ref))

    def _invoice(self,scope,direction,kind,party,description,total,at,category=None):
        self.check_scope(scope)
        if direction not in ('Pay','Receive') or total<=0: raise ValueError('Invoice needs a positive amount and Pay/Receive direction.')
        if category:
            cat=self.one('categories',category)
            if cat['scope']!=scope or cat['kind']!=('Income' if direction=='Receive' else 'Expense'): raise ValueError('Invoice category mismatch.')
        return self.db.execute('INSERT INTO invoices(day,scope,direction,kind,party,description,total,category) VALUES(?,?,?,?,?,?,?,?)',(day(at),scope,direction,kind,party,description,total,category)).lastrowid

    def invoice(self,scope,direction,kind,party,description,total,at=None,category=None):
        if kind not in ('Expense','Loan','Capital','Labor','Equipment'): raise ValueError('Choose a supported invoice kind.')
        with self.transaction('invoice',dict(scope=scope,direction=direction,kind=kind,total=total)):
            return self._invoice(scope,direction,kind,party,description,money(total),at,category)

    def outstanding(self,invoice):
        return max(0,self.invoice_balance(invoice))

    def invoice_balance(self,invoice):
        row=self.one('invoices',invoice)
        if row['void']: return 0
        paid=self.db.execute('SELECT COALESCE(SUM(amount),0) FROM payments WHERE invoice=?',(invoice,)).fetchone()[0]
        credited=self.db.execute('SELECT COALESCE(SUM(total),0) FROM credits WHERE invoice=?',(invoice,)).fetchone()[0]
        return row['total']-paid-credited

    def _pay(self,invoice,account,cents,at):
        inv,acct=self.one('invoices',invoice),self.one('accounts',account)
        if inv['scope']!=acct['scope'] or inv['void']: raise ValueError('Invoice/account mismatch or void invoice.')
        if day(at)<inv['day']: raise ValueError('Payment cannot predate the invoice.')
        if cents<=0 or cents>self.outstanding(invoice): raise ValueError('Payment exceeds outstanding amount.')
        delta=cents if inv['direction']=='Receive' else -cents
        event=self._cash(account,delta,'Payment',inv['description'],at,inv['category'],f'invoice:{invoice}')
        self.db.execute('INSERT INTO payments VALUES(NULL,?,?,?)',(invoice,event,cents))

    def pay(self,invoice,account,value,at=None):
        with self.transaction('payment',dict(invoice=invoice,account=account,value=value)):
            self._pay(invoice,account,money(value),at)

    def return_goods(self,invoice,quantity,credit,reason,at=None):
        inv=self.one('invoices',invoice);quantity,credit=units(quantity),money(credit);at=day(at)
        if inv['void'] or inv['kind'] not in ('Inventory','Sale'):raise ValueError('Choose an active stock purchase or product sale invoice.')
        if at<inv['day']:raise ValueError('Return cannot predate the original invoice.')
        with self.transaction('partial goods return',dict(invoice=invoice,quantity=quantity,credit=credit,reason=reason,at=at)):
            previous=self.rows('SELECT qty,total,stock_value FROM credits WHERE invoice=?',(invoice,))
            returned=sum((decimal(r['qty']) for r in previous),Decimal(0));credited=sum(r['total'] for r in previous)
            if credit>inv['total']-credited:raise ValueError('Credit exceeds the remaining invoice value.')
            if inv['kind']=='Sale':
                sale=self.db.execute('SELECT * FROM sales WHERE invoice=?',(invoice,)).fetchone()
                if not sale:raise ValueError('Linked sale record missing.')
                original_qty=decimal(sale['qty']);remaining_cost=sale['cogs']-sum(r['stock_value'] for r in previous)
                value=portion(remaining_cost,quantity,original_qty-returned);item=sale['item'];delta=quantity;kind='Customer return'
            else:
                receipt=self.db.execute("SELECT * FROM stock WHERE ref=? AND reason='Receipt'",(f'invoice:{invoice}',)).fetchone()
                if not receipt:raise ValueError('Linked stock receipt missing.')
                if quantity>decimal(receipt['qty'])-returned:raise ValueError('Quantity exceeds the original receipt less prior returns.')
                item=receipt['item'];available,current_value=self.stock(item);value=portion(current_value,quantity,available);delta=-quantity;kind='Supplier return'
            ident=self.db.execute('INSERT INTO credits VALUES(NULL,?,?,?,?,?,?,?)',(at,invoice,str(quantity),credit,value,kind,reason)).lastrowid
            self._stock(item,delta,value if delta>0 else -value,kind,at,f'credit:{ident}')
            return ident

    def refund(self,invoice,account,value,at=None):
        inv,acct=self.one('invoices',invoice),self.one('accounts',account)
        value=money(value);at=day(at)
        if inv['void'] or acct['scope']!=inv['scope'] or value<=0 or value>-self.invoice_balance(invoice):raise ValueError('Refund exceeds the recorded credit balance or has a scope mismatch.')
        latest=self.db.execute('SELECT MAX(c.day) FROM payments p JOIN cash c ON c.id=p.cash WHERE p.invoice=?',(invoice,)).fetchone()[0]
        credit_date=self.db.execute('SELECT MAX(day) FROM credits WHERE invoice=?',(invoice,)).fetchone()[0]
        if at<max(latest or inv['day'],credit_date or inv['day']):raise ValueError('Refund cannot predate the recorded payment/return.')
        with self.transaction('refund',dict(invoice=invoice,account=account,value=value,at=at)):
            delta=-value if inv['direction']=='Receive' else value
            event=self._cash(account,delta,'Refund',inv['description'],at,inv['category'],f'refund:{invoice}')
            self.db.execute('INSERT INTO payments VALUES(NULL,?,?,?)',(invoice,event,-value))

    def receive_stock(self,item,quantity,total,party='',at=None,account=None,paid='0'):
        quantity=units(quantity); total=money(total); paid=money(paid)
        if total<=0: raise ValueError('Enter the acquisition cost; zero/unknown cost needs review.')
        with self.transaction('stock received',dict(item=item,quantity=quantity,total=total)):
            inv=self._invoice('Business','Pay','Inventory',party,'Stock: '+self.one('items',item)['name'],total,at)
            self._stock(item,quantity,total,'Receipt',at,f'invoice:{inv}')
            if paid:
                if not account: raise ValueError('Choose the paying account.')
                self._pay(inv,account,paid,at)
            return inv

    def opening_stock(self,item,quantity,value,at=None,note='Existing stock at migration'):
        quantity,value=units(quantity),money(value)
        with self.transaction('opening stock',dict(item=item,quantity=quantity,value=value,note=note)):
            if self.rows('SELECT id FROM stock WHERE item=?',(item,)): raise ValueError('Opening stock must be the first stock event for this item.')
            self._stock(item,quantity,value,'Opening',at,note)

    def restore(self,source,backup_folder):
        source=Path(source).resolve()
        if source==self.path.resolve() or not source.is_file(): raise ValueError('Choose a different existing database backup.')
        check=sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)
        try:
            if check.execute('PRAGMA integrity_check').fetchone()[0]!='ok': raise ValueError('Backup failed its integrity check.')
            for table,columns in [('cash',{'id','day','account','delta','kind','void'}),('accounts',{'id','scope','opening','start'}),('invoices',{'id','direction','total','void'}),('audit',{'id','event','details'})]:
                actual={r[1] for r in check.execute('PRAGMA table_info('+table+')')}
                if not columns.issubset(actual): raise ValueError('Not a compatible Finance database.')
            needed={r[0] for r in self.db.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")}
            present={r[0] for r in check.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if not needed.issubset(present):raise ValueError('Backup schema is older/incomplete. A reviewed migration is required before restoring it.')
            base=check.execute("SELECT value FROM settings WHERE key='base'").fetchone()
            if not base or base[0]!=self.base: raise ValueError('Backup base currency mismatch.')
            previous=self.backup(backup_folder)
            check.backup(self.db)
            self.db.commit()
            return previous
        finally:check.close()

    def estimate(self,ingredients,output,labor='0',overhead='0'):
        merged={}
        for item,q in ingredients: merged[item]=merged.get(item,Decimal(0))+units(q)
        if not merged: raise ValueError('Add at least one material.')
        costs=[]
        for item,q in merged.items():
            if self.one('items',item)['kind']!='Material': raise ValueError('Batch inputs must be materials.')
            available,value=self.stock(item)
            if available>0:
                cost=value if q==available else round_cents(Decimal(value)*q/available)
            else:
                price=self.db.execute("SELECT qty,value FROM stock WHERE item=? AND reason IN ('Receipt','Opening') AND value>0 ORDER BY id DESC LIMIT 1",(item,)).fetchone()
                if not price:raise ValueError('No recorded material cost is available for this estimate.')
                cost=round_cents(Decimal(price['value'])*q/decimal(price['qty']))
            costs.append((item,q,cost))
        total=sum(c[2] for c in costs)+money(labor)+money(overhead)
        return costs,total,Decimal(total)/units(output)/100

    def produce(self,name,product,output,ingredients,labor='0',overhead='0',at=None):
        if self.one('items',product)['kind']!='Product': raise ValueError('Select a finished product.')
        output=units(output)
        with self.transaction('production',dict(name=name,product=product,output=output,ingredients=ingredients,labor=labor,overhead=overhead)):
            costs,total,_=self.estimate(ingredients,output,labor,overhead)
            batch=self.db.execute('INSERT INTO batches VALUES(NULL,?,?,?,?,?,?,?,?)',(day(at),name,product,str(output),sum(c[2] for c in costs),money(labor),money(overhead),now())).lastrowid
            ref=f'batch:{batch}'
            for item,q,cost in costs: self._stock(item,-q,-cost,'Production input',at,ref)
            self._stock(product,output,total,'Production output',at,ref)
            return batch

    def sell(self,item,quantity,total,party='',at=None,account=None,paid='0'):
        quantity,total,paid=units(quantity),money(total),money(paid)
        if self.one('items',item)['kind']!='Product': raise ValueError('Select a finished product.')
        with self.transaction('product sale',dict(item=item,quantity=quantity,total=total,party=party)):
            available,value=self.stock(item)
            cost=portion(value,quantity,available)
            inv=self._invoice('Business','Receive','Sale',party,'Sale: '+self.one('items',item)['name'],total,at)
            self.db.execute('INSERT INTO sales VALUES(NULL,?,?,?,?)',(inv,item,str(quantity),cost))
            self._stock(item,-quantity,-cost,'Sale',at,f'invoice:{inv}')
            if paid:
                if not account: raise ValueError('Choose the receiving account.')
                self._pay(inv,account,paid,at)
            return inv

    def loss(self,item,quantity,reason,at=None):
        quantity=units(quantity)
        with self.transaction('inventory loss',dict(item=item,quantity=quantity,reason=reason)):
            available,value=self.stock(item)
            self._stock(item,-quantity,-portion(value,quantity,available),'Loss',at,reason)

    def void_invoice(self,invoice,reason,at=None):
        inv=self.one('invoices',invoice)
        if inv['void']: raise ValueError('Invoice already void.')
        if self.rows('SELECT id FROM credits WHERE invoice=?',(invoice,)):raise ValueError('This invoice already has partial returns. Return the remaining quantities instead of reversing it again.')
        at=day(at)
        if at<inv['day']: raise ValueError('Reversal cannot predate the original invoice.')
        with self.transaction('invoice reversal',dict(original=dict(inv),reason=reason)):
            moves=self.rows('SELECT * FROM stock WHERE ref=? ORDER BY id',(f'invoice:{invoice}',))
            for move in moves:
                if move['reason']=='Receipt' and self.db.execute('SELECT 1 FROM stock WHERE item=? AND id>? LIMIT 1',(move['item'],move['id'])).fetchone():
                    raise ValueError('This receipt has later stock activity. Record a separately costed supplier return instead of voiding it.')
                self._stock(move['item'],-decimal(move['qty']),-move['value'],'Reversal',at,f'void:{invoice}')
            for payment in self.rows('SELECT c.* FROM payments p JOIN cash c ON c.id=p.cash WHERE p.invoice=?',(invoice,)):
                if at<payment['day']: raise ValueError('Refund cannot predate a payment.')
                self._cash(payment['account'],-payment['delta'],'Refund',reason,at,payment['category'],ref=f'void:{invoice}')
            self.db.execute('UPDATE invoices SET void=1,void_day=? WHERE id=?',(at,invoice))

    def cash_report(self,start,end,scope):
        start,end=day(start),day(end)
        if start>end: raise ValueError('Start is after end.')
        return self.rows('SELECT c.*,a.name,a.scope,k.name category_name FROM cash c JOIN accounts a ON a.id=c.account LEFT JOIN categories k ON k.id=c.category WHERE a.scope=? AND c.day BETWEEN ? AND ? AND c.void=0 ORDER BY c.day,c.id',(scope,start,end))

    def business_result(self,start,end):
        start,end=day(start),day(end)
        def recognized(kind,direction):
            records=self.rows("SELECT * FROM invoices WHERE scope='Business' AND direction=? AND kind=?",(direction,kind))
            return sum((r['total'] if start<=r['day']<=end else 0)-(r['total'] if r['void'] and r['void_day'] and start<=r['void_day']<=end else 0) for r in records)
        revenue=recognized('Sale','Receive')
        cogs=sum((r['cogs'] if start<=r['day']<=end else 0)-(r['cogs'] if r['void'] and r['void_day'] and start<=r['void_day']<=end else 0) for r in self.rows('SELECT s.cogs,i.day,i.void,i.void_day FROM sales s JOIN invoices i ON i.id=s.invoice'))
        customer_returns=self.rows("SELECT * FROM credits WHERE kind='Customer return' AND day BETWEEN ? AND ?",(start,end))
        revenue-=sum(r['total'] for r in customer_returns);cogs-=sum(r['stock_value'] for r in customer_returns)
        supplier_variance=sum(r['total']-r['stock_value'] for r in self.rows("SELECT * FROM credits WHERE kind='Supplier return' AND day BETWEEN ? AND ?",(start,end)))
        invoice_expenses=recognized('Expense','Pay')
        direct_expenses=self.db.execute("SELECT -COALESCE(SUM(c.delta),0) FROM cash c JOIN accounts a ON a.id=c.account WHERE a.scope='Business' AND c.kind='Expense' AND c.void=0 AND c.day BETWEEN ? AND ?",(start,end)).fetchone()[0]
        losses=-self.db.execute("SELECT COALESCE(SUM(value),0) FROM stock WHERE reason='Loss' AND day BETWEEN ? AND ?",(start,end)).fetchone()[0]
        labor=sum(r[0] for r in self.rows("SELECT total FROM invoices WHERE scope='Business' AND kind='Labor' AND void=0 AND day BETWEEN ? AND ?",(start,end)))
        allocated=sum(r[0]+r[1] for r in self.rows('SELECT labor,overhead FROM batches WHERE day BETWEEN ? AND ?',(start,end)))
        legacy=self.db.execute("SELECT COUNT(*) FROM cash c JOIN accounts a ON a.id=c.account WHERE a.scope='Business' AND c.kind='Legacy'",()).fetchone()[0]
        result=revenue-cogs-invoice_expenses-direct_expenses-losses+supplier_variance
        return dict(revenue=revenue,cogs=cogs,operating=invoice_expenses+direct_expenses,losses=losses,supplier_return_variance=supplier_variance,tracked_result=result,labor_paid_or_due=labor,allocated_production_costs=allocated,legacy_unclassified=legacy,
                    note='Tracked result only. Production labor/overhead are included through stock cost as products sell. Reconcile labor/overhead payments against allocations, equipment treatment and unclassified records before distributing net profit.')

    def plan(self,scope,name,target,due,monthly='0'):
        self.check_scope(scope)
        with self.transaction('plan',dict(scope=scope,name=name,target=target,due=due)):
            return self.db.execute('INSERT INTO envelopes VALUES(NULL,?,?,?,?,?,0,0)',(scope,name,money(target),day(due),money(monthly))).lastrowid

    def allocate(self,plan,value,committed=False):
        record=self.one('envelopes',plan)
        cents=money(value,True)
        field='committed' if committed else 'allocated'
        if record[field]+cents<0: raise ValueError('Allocation cannot go below zero.')
        with self.transaction('allocation',dict(plan=plan,value=cents,field=field)):
            self.db.execute('UPDATE envelopes SET '+field+'='+field+'+? WHERE id=?',(cents,plan))

    def profit_share(self,party,start,end,approved_profit,rate):
        start,end=day(start),day(end); approved=money(approved_profit); rate=decimal(rate)
        if start>end or not party.strip() or not 0<=rate<=100: raise ValueError('Invalid period, party or percentage.')
        amount=round_cents(Decimal(approved)*rate/100)
        if not amount: raise ValueError('No positive distribution is due.')
        with self.transaction('approved profit share',dict(party=party,start=start,end=end,approved_profit=approved,rate=rate)):
            inv=self._invoice('Business','Pay','Capital',party,'Approved profit share '+start+' to '+end,amount,end)
            self.db.execute('INSERT INTO distributions VALUES(NULL,?,?,?,?,?,?,?)',(party,start,end,approved,str(rate),amount,inv))
            return inv

    def projection(self,initial,contribution,months,annual_rate):
        if not isinstance(months,int) or not 0<=months<=1200: raise ValueError('Use 0–1200 months.')
        principal=decimal(initial); contribution=decimal(contribution); rate=decimal(annual_rate)/1200
        if principal<0 or contribution<0 or rate<=-1: raise ValueError('Invalid scenario inputs.')
        for _ in range(months): principal=principal*(1+rate)+contribution
        return principal.quantize(Decimal('.01'),rounding=ROUND_HALF_UP)

    def position(self,scope,wallet,portfolio,asset):
        self.check_scope(scope)
        if not all(str(v).strip() for v in (wallet,portfolio,asset)): raise ValueError('Wallet, portfolio and asset required.')
        asset=asset.upper().strip()
        with self.transaction('position',dict(scope=scope,wallet=wallet,portfolio=portfolio,asset=asset)):
            self.db.execute('INSERT OR IGNORE INTO positions VALUES(NULL,?,?,?,?)',(scope,wallet,portfolio,asset))
            return self.db.execute('SELECT id FROM positions WHERE scope=? AND wallet=? AND portfolio=? AND asset=?',(scope,wallet,portfolio,asset)).fetchone()[0]

    def holding(self,position,through='9999-12-31'):
        self.one('positions',position)
        rows=self.rows('SELECT qty,basis FROM holding_moves WHERE position=? AND day<=?',(position,through))
        return sum((decimal(r['qty']) for r in rows),Decimal(0)),sum(r['basis'] for r in rows)

    def _holding(self,position,quantity,basis,at,event):
        at=day(at)
        last=self.db.execute('SELECT MAX(day) FROM holding_moves WHERE position=?',(position,)).fetchone()[0]
        if last and at<last: raise ValueError('Record holding events in date order for this position.')
        oldq,oldb=self.holding(position)
        if oldq+quantity<0 or oldb+basis<0: raise ValueError('Insufficient holdings or cost basis.')
        self.db.execute('INSERT INTO holding_moves VALUES(NULL,?,?,?,?,?)',(at,position,str(quantity),basis,event))

    def _investment(self,pos,kind,qty,proceeds,basis,fees,gain,flow,description,at):
        p=self.one('positions',pos)
        return self.db.execute('INSERT INTO investment_events VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?,?)',(day(at),p['scope'],p['portfolio'],kind,p['asset'],str(qty),proceeds,basis,fees,gain,flow,description,now())).lastrowid

    def acquire(self,position,quantity,basis,kind='Buy',account=None,at=None,description='',fee='0'):
        quantity,value,fee=units(quantity),money(basis),money(fee)
        value+=fee
        if kind not in ('Buy','Opening','Reward'): raise ValueError('Use Buy, Opening or Reward.')
        with self.transaction('acquire',dict(position=position,quantity=quantity,value=value,kind=kind)):
            event=self._investment(position,kind,quantity,0,value,fee,0,value if kind!='Reward' else 0,description,at)
            self._holding(position,quantity,value,at,event)
            if account:
                if self.one('accounts',account)['scope']!=self.one('positions',position)['scope']: raise ValueError('Scope mismatch.')
                if kind!='Buy': raise ValueError('Only a Buy can debit a cash account.')
                self._cash(account,-value,'Investment','Investment acquisition',at,ref=f'investment:{event}')
            return event

    def dispose(self,position,quantity,proceeds,fee='0',account=None,at=None,fee_position=None,fee_quantity=None):
        quantity,proceeds,fee=units(quantity),money(proceeds),money(fee)
        if fee>proceeds: raise ValueError('Fee exceeds proceeds.')
        with self.transaction('dispose',dict(position=position,quantity=quantity,proceeds=proceeds,fee=fee,fee_position=fee_position,fee_quantity=fee_quantity)):
            oldq,oldb=self.holding(position); basis=portion(oldb,quantity,oldq)
            same_fee_q=units(fee_quantity) if fee_position==position and fee_quantity else Decimal(0)
            if same_fee_q and quantity+same_fee_q>oldq: raise ValueError('Insufficient holdings for sale and fee.')
            gain=proceeds-basis-fee
            event=self._investment(position,'Sell',quantity,proceeds,basis,fee,gain,-(proceeds-fee if fee_position is None else proceeds),'',at)
            self._holding(position,-quantity,-basis,at,event)
            if fee_position is not None:
                if not fee_quantity: raise ValueError('Enter the fee asset quantity.')
                fp=self.one('positions',fee_position); pos=self.one('positions',position)
                if (fp['scope'],fp['portfolio'])!=(pos['scope'],pos['portfolio']): raise ValueError('Fee holding must belong to the same scope/portfolio.')
                fq=units(fee_quantity); available,cost=self.holding(fee_position); fb=portion(cost,fq,available)
                fe=self._investment(fee_position,'Fee disposal',fq,fee,fb,0,fee-fb,0,'Fee paid in another asset',at)
                self._holding(fee_position,-fq,-fb,at,fe)
            if account:
                if self.one('accounts',account)['scope']!=self.one('positions',position)['scope']: raise ValueError('Scope mismatch.')
                self._cash(account,proceeds-fee if fee_position is None else proceeds,'Investment','Investment sale proceeds',at,ref=f'investment:{event}')
            return gain

    def swap(self,source,target,quantity,received,value,fee='0',at=None,fee_account=None):
        quantity,received,value,fee=units(quantity),units(received),money(value),money(fee)
        a,b=self.one('positions',source),self.one('positions',target)
        if source==target or (a['scope'],a['portfolio'])!=(b['scope'],b['portfolio']): raise ValueError('Swap positions must differ and share scope/portfolio.')
        with self.transaction('swap',dict(source=source,target=target,quantity=quantity,received=received,value=value,fee=fee)):
            oldq,oldb=self.holding(source); basis=portion(oldb,quantity,oldq)
            event=self._investment(source,'Swap',quantity,value,basis,0,value-basis,0,'Acquired '+b['asset'],at)
            self._holding(source,-quantity,-basis,at,event)
            event2=self._investment(target,'Swap in',received,0,value+fee,fee,0,fee,'Fee included in acquired basis; record its payment separately if paid outside portfolio.',at)
            self._holding(target,received,value+fee,at,event2)
            if fee and fee_account:
                if self.one('accounts',fee_account)['scope']!=a['scope']:raise ValueError('Fee account scope mismatch.')
                self._cash(fee_account,-fee,'Investment','External swap fee',at,ref=f'investment:{event2}')

    def transfer_holding(self,source,target,quantity,fee_quantity='0',at=None):
        quantity=units(quantity); fee=decimal(fee_quantity)
        if fee<0: raise ValueError('Fee cannot be negative.')
        a,b=self.one('positions',source),self.one('positions',target)
        if source==target or (a['scope'],a['asset'])!=(b['scope'],b['asset']): raise ValueError('Transfer must keep the same asset and scope.')
        with self.transaction('holding transfer',dict(source=source,target=target,quantity=quantity,fee=fee)):
            oldq,oldb=self.holding(source); total_basis=portion(oldb,quantity+fee,oldq)
            moved_basis=portion(total_basis,quantity,quantity+fee)
            reclassify=a['portfolio']!=b['portfolio']
            event=self._investment(source,'Transfer',quantity,0,0,total_basis-moved_basis,-(total_basis-moved_basis),-moved_basis if reclassify else 0,'Network fee valued at disposed cost basis; cross-portfolio flows at carried cost, not a market-equity return calculation',at)
            self._holding(source,-(quantity+fee),-total_basis,at,event)
            target_event=self._investment(target,'Reclassification',quantity,0,0,0,0,moved_basis,'Transferred portfolio allocation at carried cost basis',at) if reclassify else event
            self._holding(target,quantity,moved_basis,at,target_event)

    def price(self,asset,price,at=None,quote=None,fx='1'):
        price,fx=decimal(price),decimal(fx)
        if price<0 or fx<=0: raise ValueError('Invalid price or exchange rate.')
        quote=quote or self.base
        if quote==self.base and fx!=1: raise ValueError('Base-currency prices use exchange rate 1.')
        with self.transaction('price',dict(asset=asset,price=price,quote=quote,fx=fx,at=at)):
            self.db.execute('INSERT OR REPLACE INTO prices VALUES(?,?,?,?,?)',(asset.upper(),day(at),str(price),quote,str(fx)))

    def portfolio(self,scope,portfolio,at=None):
        at=day(at); rows=[]
        for pos in self.rows('SELECT * FROM positions WHERE scope=? AND portfolio=?',(scope,portfolio)):
            q,b=self.holding(pos['id'],at)
            if not q: continue
            price=self.db.execute('SELECT * FROM prices WHERE asset=? AND day<=? ORDER BY day DESC LIMIT 1',(pos['asset'],at)).fetchone()
            value=round_cents(q*decimal(price['price'])*decimal(price['fx'])*100) if price else None
            rows.append(dict(position=pos['id'],wallet=pos['wallet'],asset=pos['asset'],quantity=str(q),basis=b,value=value,unrealized=value-b if value is not None else None,price_date=price['day'] if price else None))
        events=self.rows('SELECT * FROM investment_events WHERE scope=? AND portfolio=? AND day<=? ORDER BY day,id',(scope,portfolio,at))
        realized=sum(e['gain'] for e in events)
        exits=[e['gain'] for e in events if e['kind'] in ('Sell','Swap')]
        wins=[v for v in exits if v>0]; losses=[v for v in exits if v<0]
        peak=curve=drawdown=0
        for event in events:
            curve+=event['gain']; peak=max(peak,curve); drawdown=max(drawdown,peak-curve)
        complete=all(r['value'] is not None for r in rows)
        return dict(positions=rows,valuation_complete=complete,value=sum(r['value'] or 0 for r in rows) if complete else None,realized=realized,
                    exit_events=len(exits),win_rate=str(Decimal(len(wins))*100/len(exits)) if exits else None,
                    average_win=sum(wins)//len(wins) if wins else None,average_loss=sum(losses)//len(losses) if losses else None,
                    expectancy=sum(exits)//len(exits) if exits else None,fees=sum(e['fees'] for e in events),realized_curve_drawdown=drawdown,
                    reward_income=sum(e['basis'] for e in events if e['kind']=='Reward'),net_contributions=sum(e['flow'] for e in events),note='Moving weighted-average cost basis per position. Exit-event statistics include partial exits, not complete round-trip trades. Drawdown is on the realized-result curve, not market equity. External deposits/withdrawals are flows, not trading gains. Missing prices stay unknown.')

    def trade_plan(self,scope,portfolio,asset,side,quantity,entry,stop,target,thesis='',attachment=''):
        self.check_scope(scope)
        q,e,s,t=units(quantity),units(entry),units(stop),units(target)
        if side not in ('Long','Short') or not (s<e<t if side=='Long' else t<e<s): raise ValueError('Stop/target are on the wrong sides of entry.')
        risk=q*abs(e-s); reward=q*abs(t-e)
        with self.transaction('trade plan',dict(scope=scope,portfolio=portfolio,asset=asset,side=side,quantity=q,entry=e,stop=s,target=t,thesis=thesis)):
            ident=self.db.execute('INSERT INTO trade_plans VALUES(NULL,?,?,?,?,?,?,?,?,?,?,?,?)',(now(),scope,portfolio,asset.upper(),side,str(q),str(e),str(s),str(t),thesis,'Planned',attachment)).lastrowid
        return dict(id=ident,risk=str(risk),reward=str(reward),ratio=str(reward/risk))

    def contract(self,scope,wallet,symbol,side,quantity,entry,collateral,multiplier='1',fee='0',notes=''):
        self.check_scope(scope)
        if side not in ('Long','Short'): raise ValueError('Choose Long/Short.')
        q,e,m=units(quantity),units(entry),units(multiplier)
        with self.transaction('linear contract',dict(scope=scope,wallet=wallet,symbol=symbol,side=side,quantity=q,entry=e,collateral=collateral,multiplier=m,fee=fee)):
            return self.db.execute('INSERT INTO contracts VALUES(NULL,?,?,?,?,?,?,?,?,?,0,NULL,NULL,NULL,?)',(scope,wallet,symbol,side,str(q),str(m),str(e),money(collateral),money(fee),notes)).lastrowid

    def close_contract(self,ident,exit_price,fee='0',funding='0',at=None):
        record=self.one('contracts',ident)
        if record['closed']: raise ValueError('Contract already closed.')
        exit_price=units(exit_price)
        gross=decimal(record['qty'])*decimal(record['multiplier'])*(exit_price-decimal(record['entry']))*(1 if record['side']=='Long' else -1)
        result=round_cents(gross*100)-record['fees']-money(fee)+money(funding,True)
        with self.transaction('close linear contract',dict(id=ident,exit_price=exit_price,fee=fee,funding=funding,at=at)):
            self.db.execute('UPDATE contracts SET closed=?,exit=?,fees=fees+?,funding=?,realized=? WHERE id=?',(day(at),str(exit_price),money(fee),money(funding,True),result,ident))
        return result

    def import_legacy(self,dbpath,csvpath=None):
        """One-time snapshot; imported source rows are never re-read as new money."""
        source=Path(dbpath); summary=dict(entries=0,debts=0,purchases=0,skipped=0)
        external=None
        if source.exists():
            external=sqlite3.connect(source.resolve().as_uri()+'?mode=ro',uri=True); external.row_factory=sqlite3.Row
        try:
            with self.transaction('legacy import',dict(database=str(source),csv=str(csvpath))):
                def already(kind,key,text):
                    digest=hashlib.sha256(text.encode()).hexdigest()
                    found=self.db.execute('SELECT digest FROM imports WHERE source=? AND key=?',(kind,str(key))).fetchone()
                    if found:
                        if found[0]!=digest: raise ValueError('Previously imported source changed. Review it instead of importing twice.')
                        return True
                    self.db.execute('INSERT INTO imports VALUES(?,?,?)',(kind,str(key),digest)); return False
                def acct(scope,at):
                    name='Imported records — opening balance unknown'
                    row=self.db.execute('SELECT id,start FROM accounts WHERE scope=? AND name=?',(scope,name)).fetchone()
                    if row:
                        if at<row['start']: self.db.execute('UPDATE accounts SET start=? WHERE id=?',(at,row['id']))
                        return row['id']
                    return self.db.execute('INSERT INTO accounts VALUES(NULL,?,?,0,?)',(scope,name,at)).lastrowid
                if external:
                    for row in external.execute('SELECT * FROM entries ORDER BY id'):
                        raw=json.dumps(dict(row),sort_keys=True)
                        if already('legacy-entry',row['id'],raw): continue
                        self.check_scope(row['scope']); at=day(row['date'][:10]); cents=int(row['cents'])
                        if cents<=0: raise ValueError('Invalid legacy amount.')
                        sign=1 if row['kind'] in ('Income','Sale','Debt collected') else -1
                        self._cash(acct(row['scope'],at),cents*sign,'Legacy',row['description'],at,ref='legacy-entry:'+str(row['id']))
                        summary['entries']+=1
                    for row in external.execute('SELECT * FROM debts ORDER BY id'):
                        raw=json.dumps(dict(row),sort_keys=True)
                        if already('legacy-debt',row['id'],raw): continue
                        paid=external.execute('SELECT COALESCE(SUM(cents),0) FROM entries WHERE debt=?',(row['id'],)).fetchone()[0]
                        remaining=int(row['cents'])-paid
                        if remaining<0: raise ValueError('Legacy debt is overpaid.')
                        if remaining:
                            if row['direction'] not in ('Owe','Owed','I owe','Owed to me'):raise ValueError('Unknown legacy debt direction.')
                            self._invoice(row['scope'],'Pay' if row['direction'] in ('Owe','I owe') else 'Receive','Loan',row['person'],'Imported outstanding debt',remaining,str(date.today()))
                        summary['debts']+=1
                path=Path(csvpath) if csvpath else None
                if path and path.exists():
                    with path.open(newline='') as inp:
                        for index,row in enumerate(csv.DictReader(inp),2):
                            raw=json.dumps(row,sort_keys=True)
                            if already('legacy-purchase',index,raw): continue
                            at=day(row['Date'][:10]); cents=money(row['Total MXN'])
                            if cents<=0: raise ValueError(f'Invalid purchase on CSV line {index}.')
                            self._cash(acct('Business',at),-cents,'Legacy',row['Item']+' '+row.get('Quantity',''),at,ref='legacy-purchase:'+str(index))
                            summary['purchases']+=1
            return summary
        finally:
            if external: external.close()

    def backup(self,folder):
        folder=Path(folder); folder.mkdir(parents=True,exist_ok=True)
        path=folder/('finance-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.sqlite')
        target=sqlite3.connect(path)
        try: self.db.backup(target)
        finally: target.close()
        return path

    def import_trades(self,path):
        required={'source','id','date','event','scope','wallet','portfolio','asset','quantity','total_base','fee_base'}
        with Path(path).open(newline='',encoding='utf-8-sig') as source:
            reader=csv.DictReader(source)
            if not required.issubset(set(reader.fieldnames or [])):raise ValueError('CSV does not match the documented normalized trade template.')
            records=list(reader)
        count=skipped=0
        with self.transaction('trade CSV import',dict(path=str(path),rows=len(records))):
            for row in records:
                if not row['id'].strip() or not row['source'].strip():raise ValueError('Every CSV row needs a stable source and external ID.')
                kind=row['event'].strip()
                if kind not in ('Buy','Sell','Opening','Reward'):raise ValueError('CSV events supported: Buy, Sell, Opening, Reward. Swaps/transfers use the linked event menus.')
                identity='trade-csv:'+row['source'].strip();key=row['id'].strip()
                digest=hashlib.sha256(json.dumps({k:row[k] for k in sorted(required)},sort_keys=True).encode()).hexdigest()
                old=self.db.execute('SELECT digest FROM imports WHERE source=? AND key=?',(identity,key)).fetchone()
                if old:
                    if old[0]!=digest:raise ValueError('An already imported trade ID has different contents. Review it instead of duplicating it.')
                    skipped+=1;continue
                pos=self.position(row['scope'],row['wallet'],row['portfolio'],row['asset'])
                if kind=='Sell':self.dispose(pos,row['quantity'],row['total_base'],row['fee_base'] or '0',at=row['date'])
                else:self.acquire(pos,row['quantity'],row['total_base'],kind,at=row['date'],fee=row['fee_base'] or '0')
                self.db.execute('INSERT INTO imports VALUES(?,?,?)',(identity,key,digest));count+=1
        return dict(imported=count,duplicates_skipped=skipped)

    def export(self,folder):
        folder=Path(folder)/('finance-export-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        folder.mkdir(parents=True)
        tables=['accounts','categories','cash','budgets','envelopes','items','stock','invoices','payments','credits','batches','sales','positions','holding_moves','investment_events','prices','trade_plans','contracts','distributions','journal','audit']
        for table in tables:
            cursor=self.db.execute('SELECT * FROM '+table)
            with (folder/(table+'.csv')).open('w',newline='',encoding='utf-8-sig') as out:
                writer=csv.writer(out); writer.writerow([d[0] for d in cursor.description]); writer.writerows(cursor)
        return folder

    def export_cash_report(self,scope,start,end,folder):
        rows=self.cash_report(start,end,scope)
        folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
        path=folder/('cash-report-'+scope+'-'+datetime.now().strftime('%Y%m%d-%H%M%S-%f')+'.csv')
        with path.open('w',newline='',encoding='utf-8-sig') as output:
            writer=csv.writer(output);writer.writerow(['Date','Scope','Account','Type','Category','Description','Money in','Money out','Currency'])
            for row in rows:
                value=f'{Decimal(abs(row["delta"]))/100:.2f}'
                writer.writerow([row['day'],scope,row['name'],row['kind'],row['category_name'] or '',row['description'],value if row['delta']>0 else '',value if row['delta']<0 else '',self.base])
        return path
