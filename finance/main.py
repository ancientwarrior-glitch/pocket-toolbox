#!/usr/bin/env python3
"""Numbered phone UI for the original Pocket Toolbox finance add-on."""
from pathlib import Path
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import argparse
import json
import sqlite3
from engine import Finance, VERSION, quantity_in, decimal

class UI:
    def __init__(self,root=None):
        self.root=Path(root or Path.home()/'Everyday/Finance')
        self.f=Finance(self.root/'finance.sqlite')
    def pause(self): input('\nEnter: return ')
    def heading(self,title):
        print('\033[2J\033[H',end=''); print('\n\033[1;36m'+title+'\033[0m\n')
    def money(self,cents): return f'{Decimal(cents)/100:,.2f} {self.f.base}'
    def choose(self,rows,label=str,optional=False):
        for n,row in enumerate(rows,1): print(f'{n:>3}  {label(row)}')
        if not rows: raise ValueError('No matching records yet. Add them in Setup first.')
        answer=input('\nNumber | Enter: cancel: ').strip()
        if not answer: return None
        if answer.isdigit() and 1<=int(answer)<=len(rows): return rows[int(answer)-1]
        raise ValueError('Choose a listed number.')
    def required(self,text):
        value=input(text).strip()
        if not value: raise ValueError('Cancelled: a value is required.')
        return value
    def scope(self): return self.choose(['Personal','Business'])
    def at(self): return input('Date YYYY-MM-DD (Enter: today): ').strip() or str(date.today())
    def confirm(self): return input('\nSave this record? [y/N]: ').strip().lower()=='y'
    def account(self,scope=None):
        rows=self.f.rows('SELECT * FROM accounts'+(' WHERE scope=?' if scope else '')+' ORDER BY scope,name',(scope,) if scope else ())
        return self.choose(rows,lambda r:f'{r["scope"]} | {r["name"]}')
    def category(self,scope,kind):
        rows=self.f.rows('SELECT * FROM categories WHERE scope=? AND kind=? ORDER BY name',(scope,kind))
        if not rows: print('No categories yet; this entry will be uncategorized.'); return None
        return self.choose(rows,lambda r:r['name'],True)
    def position(self):
        rows=self.f.rows('SELECT * FROM positions ORDER BY scope,portfolio,wallet,asset')
        return self.choose(rows,lambda r:f'{r["scope"]} | {r["portfolio"]} | {r["wallet"]} | {r["asset"]} | {self.f.holding(r["id"])[0]}')
    def item(self,kind=None):
        rows=self.f.rows('SELECT * FROM items'+(' WHERE kind=?' if kind else '')+' ORDER BY name',(kind,) if kind else ())
        return self.choose(rows,lambda r:f'{r["name"]} | {self.f.stock(r["id"])[0]} {r["unit"]} | {self.money(self.f.stock(r["id"])[1])}')
    def quantity(self,item): return quantity_in(self.required(f'Quantity ({item["unit"]}; kg/l accepted where compatible): '),item['unit'])
    def setup(self):
        choice=self.choose(['Add account / opening balance','Add category','View accounts','View categories'])
        if choice=='Add account / opening balance':
            scope=self.scope()
            if not scope:return
            name=self.required('Account name (cash, wallet, etc.): ')
            print('Opening balance is the amount at the START of the opening date. Record later movements once.')
            opening=self.required(f'Opening balance in {self.f.base}: '); start=self.at()
            if self.confirm():self.f.account(scope,name,opening,start)
        elif choice=='Add category':
            scope=self.scope(); kind=self.choose(['Income','Expense']); name=self.required('Category name: ')
            if scope and kind and self.confirm():self.f.category(scope,name,kind)
        elif choice=='View accounts':
            for row in self.f.rows('SELECT * FROM accounts ORDER BY scope,name'):
                print(row['scope'],row['name'],'|',self.money(self.f.balance(row['id'])))
                if 'opening balance unknown' in row['name']:print('  Historical movements only. Do not treat this as available cash.')
            self.pause()
        elif choice=='View categories':
            for row in self.f.rows('SELECT * FROM categories ORDER BY scope,kind,name'):print(dict(row))
            self.pause()
    def cash(self):
        choice=self.choose(['Income or expense','Transfer between accounts','Reconcile a counted balance'])
        if choice=='Income or expense':
            account=self.account()
            if not account:return
            kind=self.choose(['Income','Expense'])
            if not kind:return
            category=self.category(account['scope'],kind)
            value=self.required('Amount: '); description=self.required('Description: '); at=self.at()
            print(account['scope'],account['name'],kind,value,description,at)
            if self.confirm():self.f.cash_entry(account['id'],value,kind,description,at,category['id'] if category else None)
        elif choice=='Transfer between accounts':
            print('FROM'); source=self.account()
            print('TO'); target=self.account()
            if not source or not target:return
            value=self.required('Transfer amount: '); fee=input('Fee (Enter: 0): ').strip() or '0'; at=self.at()
            if self.confirm():self.f.transfer(source['id'],target['id'],value,at,fee)
        elif choice=='Reconcile a counted balance':
            account=self.account()
            if not account:return
            at=self.at();recorded=self.f.balance(account['id'],at)
            if recorded is None:raise ValueError('Date predates account opening.')
            print('Recorded:',self.money(recorded))
            actual=self.required('Amount actually counted: '); explanation=self.required('Reason/note: ')
            if self.confirm():print('Adjustment:',self.money(self.f.reconcile(account['id'],actual,at,explanation)))
    def reports(self):
        scope=self.scope()
        if not scope:return
        start=input('Start date (Enter: January 1 this year): ').strip() or f'{date.today().year}-01-01'
        end=self.at(); rows=self.f.cash_report(start,end,scope)
        operational=[r for r in rows if r['kind'] not in ('Transfer','Investment','Adjustment')]
        print('\nMoney in:',self.money(sum(r['delta'] for r in operational if r['delta']>0)))
        print('Money out:',self.money(-sum(r['delta'] for r in operational if r['delta']<0)))
        print('Transfers, investment movements and reconciliation adjustments are shown separately below.')
        for row in rows:
            print(f'\n#{row["id"]} {row["day"]} | {row["name"]} | {row["kind"]} | {self.money(row["delta"])}')
            print(' ',row['description'],'|',row['category_name'] or 'Uncategorized')
        if scope=='Business':
            result=self.f.business_result(start,end)
            print('\nBUSINESS: recorded sales',self.money(result['revenue']),'| cost of sold stock',self.money(result['cogs']))
            print('Operating costs',self.money(result['operating']),'| losses',self.money(result['losses']))
            print('Tracked result:',self.money(result['tracked_result']))
            print(result['note']); print('Unclassified legacy cash entries:',result['legacy_unclassified'])
        if input('\ne: export this cash report | Enter: back: ').lower()=='e':
            print('Saved:',self.f.export_cash_report(scope,start,end,Path.home()/'storage/downloads/Finance-Reports'));self.pause()
    def budgets(self):
        scope=self.scope()
        if not scope:return
        month=input('Month YYYY-MM (Enter: this month): ').strip() or str(date.today())[:7]
        for row in self.f.budget_report(month,scope):
            planned=self.money(row['planned']) if row['planned'] is not None else 'Not set'
            remaining=self.money(row['remaining']) if row['remaining'] is not None else 'Unknown'
            print(f'\n{row["category"]} ({row["kind"]})\n Planned: {planned}\n Actual: {self.money(row["actual"])}\n Plan minus actual: {remaining}')
        if input('\ns: set a category plan | Enter: back: ').lower()=='s':
            kind=self.choose(['Income','Expense']); category=self.category(scope,kind)
            if category:
                value=self.required('Planned total: ')
                if self.confirm():self.f.set_budget(month,category['id'],value)
    def invoices(self):
        choice=self.choose(['Add debt / bill / receivable','Outstanding balances / record payment','Reverse a whole invoice / return','Partial customer/supplier return','Refund a credit balance'])
        if choice=='Add debt / bill / receivable':
            scope=self.scope(); direction=self.choose(['Pay','Receive'])
            kind=self.choose(['Loan','Expense','Labor','Equipment','Capital'])
            if not scope or not direction or not kind:return
            party=self.required('Person/business: '); description=self.required('Description: ')
            value=self.required('Total outstanding or billed: '); at=self.at()
            category=self.category(scope,'Income' if direction=='Receive' else 'Expense')
            if self.confirm():self.f.invoice(scope,direction,kind,party,description,value,at,category['id'] if category else None)
        elif choice=='Outstanding balances / record payment':
            rows=[r for r in self.f.rows('SELECT * FROM invoices WHERE void=0 ORDER BY day,id') if self.f.outstanding(r['id'])]
            row=self.choose(rows,lambda r:f'#{r["id"]} {r["scope"]} | {r["direction"]} | {r["party"]} | {r["description"]} | {self.money(self.f.outstanding(r["id"]))}')
            if not row:return
            account=self.account(row['scope'])
            if not account:return
            value=self.required('Payment amount: '); at=self.at()
            if self.confirm():self.f.pay(row['id'],account['id'],value,at)
        elif choice=='Reverse a whole invoice / return':
            row=self.choose(self.f.rows('SELECT * FROM invoices WHERE void=0 ORDER BY id DESC LIMIT 50'),lambda r:f'#{r["id"]} {r["description"]} | {self.money(r["total"])}')
            if row:
                reason=self.required('Reason: '); at=self.at()
                print('This reverses the whole invoice, restocks linked sale quantities, and refunds all linked payments to their original accounts.')
                if input('Type REVERSE: ')=='REVERSE':self.f.void_invoice(row['id'],reason,at)
        elif choice=='Partial customer/supplier return':
            row=self.choose(self.f.rows("SELECT * FROM invoices WHERE void=0 AND kind IN ('Inventory','Sale') ORDER BY id DESC"),lambda r:f'#{r["id"]} {r["kind"]} | {r["description"]} | original {self.money(r["total"])}')
            if row:
                quantity=self.required('Quantity returned in the item’s BASE unit: ');credit=self.required('Credit agreed for these returned goods: ');reason=self.required('Reason: ');at=self.at()
                if self.confirm():
                    self.f.return_goods(row['id'],quantity,credit,reason,at)
                    print('Remaining payable/receivable:',self.money(self.f.outstanding(row['id'])))
                    print('Refund due:',self.money(max(0,-self.f.invoice_balance(row['id']))));self.pause()
        elif choice=='Refund a credit balance':
            rows=[r for r in self.f.rows('SELECT * FROM invoices WHERE void=0') if self.f.invoice_balance(r['id'])<0]
            row=self.choose(rows,lambda r:f'#{r["id"]} {r["party"]} | {r["description"]} | credit {self.money(-self.f.invoice_balance(r["id"]))}')
            if row:
                account=self.account(row['scope'])
                if not account:return
                value=self.required('Refund amount: ');at=self.at()
                if self.confirm():self.f.refund(row['id'],account['id'],value,at)
    def inventory(self):
        choice=self.choose(['Add material/product','Receive supplies/stock','Estimate a batch','Record production','Record product sale','Record damaged/lost stock','Stock report','Record opening stock already owned'])
        if choice=='Add material/product':
            name=self.required('Item name: '); kind=self.choose(['Material','Product']); unit=self.choose(['g','ml','each'])
            if kind and unit and self.confirm():self.f.item(name,kind,unit)
        elif choice=='Receive supplies/stock':
            item=self.item()
            if not item:return
            qty=self.quantity(item); total=self.required('Total acquisition cost: '); party=input('Supplier: ').strip(); at=self.at()
            paid=input('Amount paid now (Enter: 0 / pay later): ').strip() or '0'; account=self.account('Business') if decimal(paid)>0 else None
            if decimal(paid)>0 and not account:return
            print('An invoice and stock receipt are linked. Do not enter this purchase a second time in Cash.')
            if self.confirm():self.f.receive_stock(item['id'],qty,total,party,at,account['id'] if account else None,paid)
        elif choice in ('Estimate a batch','Record production'):
            ingredients=[]
            while input('a: add ingredient/packaging | Enter: finished: ').lower()=='a':
                item=self.item('Material')
                if item:ingredients.append((item['id'],self.quantity(item)))
            product=self.item('Product')
            if not product:return
            output=self.quantity(product); labor=input('Labor allocated to this batch (Enter: 0): ').strip() or '0'; overhead=input('Other costs allocated (Enter: 0): ').strip() or '0'
            costs,total,unit=self.f.estimate(ingredients,output,labor,overhead)
            print('Total batch cost:',self.money(total),'| Cost per output unit:',unit,self.f.base)
            print('This allocates production cost; it does not record wage/overhead payments.')
            if choice=='Record production':
                name=self.required('Batch name: '); at=self.at()
                if self.confirm():self.f.produce(name,product['id'],output,ingredients,labor,overhead,at)
            else:self.pause()
        elif choice=='Record product sale':
            item=self.item('Product')
            if not item:return
            qty=self.quantity(item); total=self.required('Total sale price: '); party=input('Customer: ').strip(); at=self.at()
            paid=input('Amount collected now (Enter: 0 / credit sale): ').strip() or '0'; account=self.account('Business') if decimal(paid)>0 else None
            if decimal(paid)>0 and not account:return
            if self.confirm():self.f.sell(item['id'],qty,total,party,at,account['id'] if account else None,paid)
        elif choice=='Record damaged/lost stock':
            item=self.item()
            if item:
                qty=self.quantity(item); reason=self.required('Reason: '); at=self.at()
                if self.confirm():self.f.loss(item['id'],qty,reason,at)
        elif choice=='Stock report':
            for item in self.f.rows('SELECT * FROM items ORDER BY kind,name'):
                qty,value=self.f.stock(item['id']); print(item['kind'],item['name'],'|',qty,item['unit'],'|',self.money(value))
            self.pause()
        elif choice=='Record opening stock already owned':
            item=self.item()
            if item:
                qty=self.quantity(item); value=self.required('Recorded cost of this existing stock (0 if deliberately unknown): '); at=self.at()
                print('No new purchase, debt or cash movement is created. Use only when establishing an item’s starting stock.')
                if self.confirm():self.f.opening_stock(item['id'],qty,value,at)
    def plans(self):
        choice=self.choose(['Add savings/reinvestment goal','View goals / reserve or commit money','Contribution/return scenario','Record approved profit share'])
        if choice=='Add savings/reinvestment goal':
            scope=self.scope(); name=self.required('Goal name: '); target=self.required('Target amount: '); due=self.required('Target date YYYY-MM-DD: '); monthly=input('Planned monthly contribution (Enter: 0): ').strip() or '0'
            if scope and self.confirm():self.f.plan(scope,name,target,due,monthly)
        elif choice=='View goals / reserve or commit money':
            row=self.choose(self.f.rows('SELECT * FROM envelopes ORDER BY scope,name'),lambda r:f'{r["scope"]} | {r["name"]} | target {self.money(r["target"])} | reserved {self.money(r["allocated"])} | committed {self.money(r["committed"])} | due {r["due"]}')
            if row:
                kind=self.choose(['Reserved','Committed']); value=self.required('Amount to ADD (negative releases an allocation): ')
                print('Planning allocation only. This does not move cash or record a purchase.')
                if kind and self.confirm():self.f.allocate(row['id'],value,kind=='Committed')
        elif choice=='Contribution/return scenario':
            initial=self.required('Starting amount: '); monthly=self.required('Monthly contribution: '); months=int(self.required('Number of months: ')); rate=self.required('Assumed annual return % (can be negative): ')
            print('Scenario ending value:',self.f.projection(initial,monthly,months,rate),self.f.base)
            print('Assumption-based projection; contributions occur at month end. Fees/taxes are not modeled.'); self.pause()
        elif choice=='Record approved profit share':
            party=self.required('Recipient: '); start=self.required('Period start YYYY-MM-DD: '); end=self.required('Period end YYYY-MM-DD: ')
            profit=self.required('Net profit YOU have reconciled and approved, after all costs and your pay: '); rate=self.required('Agreed percentage: ')
            print('The tracked-result report is not automatically approved net profit. This creates a distribution payable, not a second business expense.')
            if self.confirm():self.f.profit_share(party,start,end,profit,rate)
    def investments(self):
        choice=self.choose(['Add wallet/asset position','Buy / opening holding / reward','Sell for money leaving the portfolio','Swap assets inside portfolio','Transfer between own wallets','Record dated price','Portfolio and performance'])
        if choice=='Add wallet/asset position':
            scope=self.scope(); wallet=self.required('Wallet/exchange label: '); portfolio=self.required('Portfolio (e.g. Trading or Long-term): '); asset=self.required('Asset symbol: ')
            if scope and self.confirm():self.f.position(scope,wallet,portfolio,asset)
        elif choice=='Buy / opening holding / reward':
            pos=self.position()
            if not pos:return
            kind=self.choose(['Buy','Opening','Reward'])
            if not kind:return
            q=self.required('Net asset quantity received: '); cost=self.required(f'Acquisition value / cost basis in {self.f.base}, BEFORE fee: '); fee=input('Acquisition fee in base currency (Enter: 0): ').strip() or '0'; at=self.at()
            account=None
            if kind=='Buy' and input('Also record the payment from a cash account? [y/N]: ').lower()=='y':
                account=self.account(pos['scope'])
                if not account:return
            if self.confirm():self.f.acquire(pos['id'],q,cost,kind,account['id'] if account else None,at,fee=fee)
        elif choice=='Sell for money leaving the portfolio':
            pos=self.position()
            if not pos:return
            qty=self.required('Quantity sold (excluding any fee quantity): '); proceeds=self.required('Gross proceeds in base currency: '); fee=input('Fee value in base currency (Enter: 0): ').strip() or '0'
            fee_pos=None; fee_qty=None
            if decimal(fee)>0 and input('Fee paid using an asset already tracked in this portfolio? [y/N]: ').lower()=='y':
                fee_pos=self.position()
                if not fee_pos:return
                fee_qty=self.required('Asset quantity paid as fee: ')
            account=None
            if input('Also credit proceeds to a cash account? [y/N]: ').lower()=='y':
                account=self.account(pos['scope'])
                if not account:return
            at=self.at()
            if self.confirm():print('Realized result:',self.money(self.f.dispose(pos['id'],qty,proceeds,fee,account['id'] if account else None,at,fee_pos['id'] if fee_pos else None,fee_qty)))
        elif choice=='Swap assets inside portfolio':
            print('DISPOSED ASSET'); source=self.position(); print('RECEIVED ASSET'); target=self.position()
            if not source or not target:return
            qty=self.required('Quantity disposed: '); received=self.required('Net quantity received: '); value=self.required('Fair value exchanged in base currency: '); fee=input('Additional fee paid OUTSIDE portfolio in base currency (Enter: 0): ').strip() or '0'; at=self.at()
            fee_account=None
            if decimal(fee)>0 and input('Also debit that fee from a cash account? [y/N]: ').lower()=='y':
                fee_account=self.account(source['scope'])
                if not fee_account:return
            if self.confirm():self.f.swap(source['id'],target['id'],qty,received,value,fee,at,fee_account['id'] if fee_account else None)
        elif choice=='Transfer between own wallets':
            print('SOURCE'); source=self.position(); print('DESTINATION'); target=self.position()
            if not source or not target:return
            qty=self.required('Net quantity reaching destination: '); fee=input('Network fee quantity in SAME asset (Enter: 0): ').strip() or '0'; at=self.at()
            if self.confirm():self.f.transfer_holding(source['id'],target['id'],qty,fee,at)
        elif choice=='Record dated price':
            asset=self.required('Asset symbol: '); price=self.required('Price per unit: '); quote=input(f'Quote currency (Enter: {self.f.base}): ').strip() or self.f.base
            fx='1' if quote==self.f.base else self.required(f'{self.f.base} per ONE {quote}: ')
            at=self.at()
            if self.confirm():self.f.price(asset,price,at,quote,fx)
        elif choice=='Portfolio and performance':
            scope=self.scope(); portfolio=self.required('Portfolio name: '); at=self.at()
            if scope:
                result=self.f.portfolio(scope,portfolio,at)
                for row in result['positions']:
                    value=self.money(row['value']) if row['value'] is not None else 'Unknown: add a dated price'
                    gain=self.money(row['unrealized']) if row['unrealized'] is not None else 'Unknown'
                    print(f'\n{row["asset"]} | {row["wallet"]}\n Quantity: {row["quantity"]}\n Cost basis: {self.money(row["basis"])}\n Value: {value}\n Unrealized: {gain}\n Price date: {row["price_date"] or "Missing"}')
                for key in ['value','realized','reward_income','average_win','average_loss','expectancy','fees','realized_curve_drawdown','net_contributions']:
                    print(key.replace('_',' ').title()+':',self.money(result[key]) if result[key] is not None else 'Unknown')
                print('Exit events:',result['exit_events'],'| Win rate:',result['win_rate'] or 'Unknown')
                print(result['note']);self.pause()
    def trading(self):
        choice=self.choose(['Add trade plan','List/update plan status','Trading journal / screenshot reference','Linear futures/margin record','Close linear contract','View contracts'])
        if choice=='Add trade plan':
            scope=self.scope(); portfolio=self.required('Portfolio: '); asset=self.required('Asset: '); side=self.choose(['Long','Short'])
            qty=self.required('Quantity: '); entry=self.required('Planned entry: '); stop=self.required('Stop: '); target=self.required('Target: ')
            thesis=self.required('Thesis, timeframe and entry conditions: '); attachment=input('Screenshot/file path (optional): ').strip()
            if scope and side and self.confirm():print(self.f.trade_plan(scope,portfolio,asset,side,qty,entry,stop,target,thesis,attachment)); self.pause()
        elif choice=='List/update plan status':
            row=self.choose(self.f.rows('SELECT * FROM trade_plans ORDER BY id DESC'),lambda r:f'#{r["id"]} {r["asset"]} {r["side"]} | {r["status"]} | {r["thesis"]}')
            if row:
                status=self.choose(['Planned','Active','Closed','Cancelled'])
                if status and self.confirm():
                    with self.f.transaction('plan status',dict(before=dict(row),after=status)):self.f.db.execute('UPDATE trade_plans SET status=? WHERE id=?',(status,row['id']))
        elif choice=='Trading journal / screenshot reference':
            if input('a: add | Enter: read recent: ').lower()=='a':
                topic=self.required('Trade/asset/topic: '); text=self.required('Entry reason, exit reason, lesson or note: '); path=input('Screenshot path (optional): ').strip()
                if self.confirm():
                    from engine import now
                    with self.f.transaction('journal',dict(topic=topic,text=text,attachment=path)):self.f.db.execute('INSERT INTO journal VALUES(NULL,?,?,?,?)',(now(),topic,text,path))
            else:
                for row in self.f.rows('SELECT * FROM journal ORDER BY id DESC LIMIT 30'):print(dict(row))
                self.pause()
        elif choice=='Linear futures/margin record':
            print('Manual, LINEAR contracts only. Prices/results must be expressed in the base currency. No exchange orders or liquidation calculation.')
            scope=self.scope(); wallet=self.required('Exchange/wallet: '); symbol=self.required('Contract symbol: '); side=self.choose(['Long','Short'])
            qty=self.required('Contract quantity: '); multiplier=self.required('Base-asset units per contract (often 1): '); entry=self.required('Entry price: '); collateral=self.required('Collateral/margin value: '); fee=input('Entry fee (Enter: 0): ').strip() or '0'; notes=input('Leverage, funding, liquidation or other notes: ').strip()
            if scope and side and self.confirm():self.f.contract(scope,wallet,symbol,side,qty,entry,collateral,multiplier,fee,notes)
        elif choice=='Close linear contract':
            row=self.choose(self.f.rows('SELECT * FROM contracts WHERE closed IS NULL ORDER BY id'),lambda r:f'#{r["id"]} {r["symbol"]} {r["side"]} | {r["qty"]} @ {r["entry"]}')
            if row:
                price=self.required('Exit/settlement price: '); fee=input('Exit fee (Enter: 0): ').strip() or '0'; funding=input('Net funding/borrowing adjustment: positive received, negative paid (Enter: 0): ').strip() or '0'; at=self.at()
                if self.confirm():print('Recorded result:',self.money(self.f.close_contract(row['id'],price,fee,funding,at)));self.pause()
        elif choice=='View contracts':
            for row in self.f.rows('SELECT * FROM contracts ORDER BY id DESC'):
                print(f'\n#{row["id"]} {row["symbol"]} | {row["side"]} | {row["qty"]} contracts\n Entry: {row["entry"]} | Exit: {row["exit"] or "Open"}\n Collateral: {self.money(row["collateral"])} | Fees: {self.money(row["fees"])}\n Funding: {self.money(row["funding"])} | Result: {self.money(row["realized"]) if row["realized"] is not None else "Not closed"}')
                print(row['notes'])
            self.pause()
    def corrections(self):
        print('Linked invoices use whole-invoice reversals in Bills/debts. Stock/trade events keep their audit trail; complex amendments require a reviewed migration.')
        rows=self.f.rows("SELECT * FROM cash WHERE void=0 AND (ref IS NULL OR ref LIKE 'legacy-entry:%' OR ref LIKE 'legacy-purchase:%') ORDER BY id DESC LIMIT 50")
        row=self.choose(rows,lambda r:f'#{r["id"]} {r["day"]} {r["description"]} | {self.money(r["delta"])}')
        if not row:return
        action=self.choose(['Correct','Void'])
        if action=='Void':
            if input('Type VOID: ')=='VOID':self.f.correct_cash(row['id'],void=True)
        elif action=='Correct':
            value=input('New absolute amount (Enter: keep): ').strip() or None
            description=input('New description (Enter: keep): ').strip() or None
            at=input('New date YYYY-MM-DD (Enter: keep): ').strip() or None
            category=self.category(self.f.one('accounts',row['account'])['scope'],'Income' if row['delta']>0 else 'Expense')
            if self.confirm():self.f.correct_cash(row['id'],value,description,at,category['id'] if category else None)
    def search(self):
        query=self.required('Search text: ').casefold()
        for table in ['cash','invoices','batches','items','investment_events','trade_plans','journal','audit']:
            for row in self.f.rows('SELECT * FROM '+table+' ORDER BY id DESC'):
                text=json.dumps(dict(row),ensure_ascii=False)
                if query in text.casefold():print('\n'+table+': '+text)
        self.pause()
    def legacy(self):
        root=Path.home()/'Everyday/Jabones-Yayo'
        print('This imports a SNAPSHOT of your original budget database and purchase CSV.')
        print('Original files stay intact. Run this once before making new finance entries.')
        print('Imported accounts have unknown opening balances; their figures show historical movement, not available cash.')
        if input('Type IMPORT: ')=='IMPORT':
            self.f.backup(self.root/'Backups')
            print(self.f.import_legacy(root/'budget.sqlite',root/'purchases.csv'));self.pause()
    def backup(self):print('Saved:',self.f.backup(self.root/'Backups'));self.pause()
    def restore(self):
        path=self.choose(sorted((self.root/'Backups').glob('finance-*.sqlite'),reverse=True),lambda p:p.name)
        if path and input('Type RESTORE to replace current finance records: ')=='RESTORE':
            print('Pre-restore snapshot:',self.f.restore(path,self.root/'Backups'));self.pause()
    def export(self):print('Saved:',self.f.export(Path.home()/'storage/downloads'));self.pause()
    def import_trades(self):
        print('Use the normalized template in finance/trades-template.csv. Exchange-specific exports must be mapped to it first.')
        print('Amounts are in the base currency; fees are base-currency values. Rows require stable source + ID and chronological dates.')
        path=Path(self.required('Full CSV file path: ')).expanduser()
        if self.confirm():print(self.f.import_trades(path));self.pause()
    def graphs(self):
        from charts import dashboard_data,render,serve
        serve(render(dashboard_data(self.f)))
    def help(self):
        print('''FIRST: import old records once, then create actual cash accounts with opening balances.
Personal and Business are separate. Transfers are not income or expenses.
Create categories, then plan budgets for any month/year. Balances do not reset yearly.
Purchases and sales with stock belong in Inventory; payment belongs to the same invoice.
Bills/debts supports partial payments. Never record that payment again in Cash.
Batch quantities use g, ml or each; compatible kg/l input converts automatically.
Historical batch costs are saved. Stock events are entered chronologically per item.
Whole sale returns restore stock/refund payments. Partial returns create credits; refund credit balances separately.
Labor and overhead allocated to batches must be reconciled against actual costs before approving profit.
Profit-share records use your reconciled, approved net profit and agreed percentage.
Goal reserves are planning earmarks; they do not move actual cash.
Spot assets use moving weighted-average basis per wallet/portfolio. All cost/fee values use the base currency.
Sell means proceeds leave the tracked portfolio; swap into USDT/USD positions if proceeds stay inside it.
Wallet transfers preserve basis. Prices and FX rates are dated manual inputs; missing prices are unknown.
Spot statistics are exit-event statistics, including partial exits. They are not full-trade or time-weighted returns.
Contracts are separate manual LINEAR records, not automatic exchange execution or liquidation models.
No tax calculations, exchange API connection, live prices, stop orders or automatic trading are included.
Corrections preserve audit records. Attachments are file references, not copied images.
Main toolbox backups include ~/Everyday/Finance and the installed finance code.
Finance backups here are SQLite snapshots; exports have one CSV per table, monetary fields in CENTS.
Read FINANCE.md in the repository for scope, backups, restore and migration details.''')
        self.pause()
    def main(self):
        actions=[('Setup: accounts and categories',self.setup),('Cash, transfers and reconciliation',self.cash),
                 ('Reports / search by date range',self.reports),('Monthly budgets',self.budgets),
                 ('Bills, debts and partial payments',self.invoices),('Supplies, stock, batches and sales',self.inventory),
                 ('Savings, investment plans and profit shares',self.plans),('Crypto holdings and portfolio',self.investments),
                 ('Trading plans, journal and linear contracts',self.trading),('Search all finance records',self.search),
                 ('Correct/void a cash entry',self.corrections),('Import original records once',self.legacy),
                 ('Back up finance database',self.backup),('Export all tables to CSV',self.export),('Help and limitations',self.help),('Restore a finance snapshot',self.restore),('Import normalized trading CSV',self.import_trades),('Graphs / visual dashboard',self.graphs)]
        while True:
            try:
                self.heading('FINANCE '+VERSION)
                for n,(label,_) in enumerate(actions,1):print(f'{n:>2}  {label}')
                print(' 0  Return')
                choice=input('\nChoose: ').strip()
                if choice=='0':return
                if choice.isdigit() and 1<=int(choice)<=len(actions):actions[int(choice)-1][1]()
            except KeyboardInterrupt:print('\nCancelled.')
            except (ValueError,InvalidOperation,sqlite3.Error,OSError,KeyError) as error:print('\nCould not finish:',error);self.pause()

def main():
    parser=argparse.ArgumentParser(); parser.add_argument('--root');parser.add_argument('--purchase',action='store_true');parser.add_argument('--purchases',action='store_true');parser.add_argument('--correct',action='store_true')
    args=parser.parse_args(); ui=UI(args.root)
    try:
        if args.purchase:ui.inventory()
        elif args.purchases:ui.reports()
        elif args.correct:ui.corrections()
        else:ui.main()
    except (KeyboardInterrupt,EOFError):print('\nClosed.')
    except (ValueError,InvalidOperation,sqlite3.Error,OSError) as error:print('Could not finish:',error)
    finally:ui.f.close()

if __name__=='__main__':main()
