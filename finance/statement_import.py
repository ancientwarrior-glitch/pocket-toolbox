"""Prepared local statements: explicit cash roles plus durable source/review records.

Unknown opening balances and historical debt balances are never inferred. Crypto
observations do not create positions, cost basis or trading profit.
"""
from pathlib import Path
import json
from engine import day, money, STATEMENT_SCHEMA
from cash_import import digest
from pocket_security import private_dir, private_file

KINDS={'Income','Expense','Capital','DebtPayment','Advance','Reimbursement','Investment','Review'}
TABLE=STATEMENT_SCHEMA

def text(value,label,limit=4000):
    if not isinstance(value,str) or not value.strip() or len(value)>limit or any(ord(c)<32 or ord(c)==127 for c in value):
        raise ValueError('Invalid '+label)
    return value

def load(path):
    path=Path(path)
    if path.stat().st_size>16*1024*1024:raise ValueError('Statement exceeds 16 MiB.')
    def unique(pairs):
        result={}
        for k,v in pairs:
            if k in result:raise ValueError('Duplicate JSON key.')
            result[k]=v
        return result
    try:data=json.loads(path.read_text(encoding='utf-8-sig'),object_pairs_hook=unique)
    except (UnicodeError,json.JSONDecodeError,RecursionError) as e:raise ValueError('Invalid statement JSON.') from e
    validate(data)
    return data

def validate(data):
    if not isinstance(data,dict) or set(data)-{'format','source','currency','notes','events'} or data.get('format')!='pocket-statement-v1':raise ValueError('Unsupported prepared statement format.')
    text(data.get('source'),'source',200);text(data.get('currency'),'currency',12)
    if 'notes' in data:text(data['notes'],'notes',16000)
    rows=data.get('events')
    if not isinstance(rows,list) or not 1<=len(rows)<=10000:raise ValueError('Use 1–10000 statement events.')
    encoded=json.dumps(data,ensure_ascii=False,allow_nan=False)
    if any(ord(c)<32 or ord(c)==127 for c in encoded):raise ValueError('Control characters are not accepted.')
    def safe(value):
        if isinstance(value,str) and any(ord(c)<32 or ord(c)==127 for c in value):raise ValueError('Control characters are not accepted.')
        if isinstance(value,dict):
            for k,v in value.items():safe(k);safe(v)
        elif isinstance(value,list):
            for v in value:safe(v)
    safe(data)
    ids=set();groups={}
    for r in rows:
        if not isinstance(r,dict) or set(r)-{'id','date','description','scope','kind','amount','category','party','group','note','evidence'}:raise ValueError('Unsupported statement event fields.')
        key=text(r.get('id'),'event ID',250)
        if key in ids:raise ValueError('Duplicate event ID.')
        ids.add(key);day(r.get('date'));text(r.get('date'),'date',10)
        text(r.get('description'),'description');text(r.get('note','No additional note'),'note',16000)
        if r.get('scope') not in ('Personal','Business') or r.get('kind') not in KINDS:raise ValueError('Unsupported event role/scope.')
        for field in ('category','party','group'):
            if field in r:text(r[field],field,250)
        if 'evidence' in r:
            if not isinstance(r['evidence'],dict) or len(json.dumps(r['evidence']))>16000:raise ValueError('Evidence must be a bounded object.')
        if r['kind']!='Review':
            if not isinstance(r.get('amount'),str):raise ValueError('Cash amount must be a decimal string.')
            n=money(r['amount'],True)
            if not n:raise ValueError('Zero cash movement.')
            if r['kind'] in ('Income','Capital','Reimbursement') and n<0 or r['kind'] in ('Expense','DebtPayment','Advance') and n>0:raise ValueError('Cash sign conflicts with role.')
        if r['kind'] in ('Advance','Reimbursement'):
            group=text(r.get('group'),'advance/reimbursement group',250)
            groups.setdefault(group,[]).append(r)
    for group,rs in groups.items():
        advances=[r for r in rs if r['kind']=='Advance'];repaid=[r for r in rs if r['kind']=='Reimbursement']
        if len(advances)!=1 or not repaid:raise ValueError('A group needs one advance and its reimbursement(s).')
        a=advances[0]
        if any(r['scope']!=a['scope'] or r['date']<a['date'] for r in repaid) or sum(money(r['amount'],True) for r in repaid)>-money(a['amount'],True):raise ValueError('Invalid reimbursement group.')
    return data

def existing(f):
    if not f.rows("SELECT name FROM sqlite_master WHERE type='table' AND name='statement_events'"):return {}
    return {(r['source'],r['event_id']):r for r in f.rows('SELECT * FROM statement_events')}

def snapshot(f):
    # Include accounts, invoices, receipts and review data, not just cash.
    return digest(list(f.db.iterdump()))

def preview(f,data):
    validate(data)
    if data['currency']!=f.base:raise ValueError('Statement currency must match Finance base currency. No automatic FX conversion.')
    old=existing(f);rows=[]
    for r in data['events']:
        receipt=old.get((data['source'],r['id']))
        if receipt and receipt['digest']!=digest(r):raise ValueError('An imported event ID has changed: '+r['id'])
        if not receipt and r['kind']!='Review' and f.rows('SELECT id FROM cash WHERE day=? AND delta=? AND description=? AND void=0',(r['date'],money(r['amount'],True),r['description'])):
            raise ValueError('Possible existing cash duplicate: '+r['id']+'. Reconcile before importing this statement.')
        rows.append({'event':r,'status':'Already imported' if receipt else ('Review only' if r['kind']=='Review' else 'Post cash')})
    # Partial linked groups are unsafe (e.g. a hand-edited subset of an older import).
    for group in {r.get('group') for r in data['events'] if r['kind'] in ('Advance','Reimbursement')}:
        states={row['status']=='Already imported' for row in rows if row['event'].get('group')==group}
        if len(states)>1:raise ValueError('Partially imported reimbursement group requires reconciliation.')
    return {'data':json.loads(json.dumps(data)),'rows':rows,'snapshot':snapshot(f)}

def commit(f,plan,folder):
    fresh=preview(f,plan['data'])
    if fresh['snapshot']!=plan['snapshot']:raise ValueError('Finance changed. Run a fresh preview.')
    pending=[row['event'] for row in fresh['rows'] if row['status']!='Already imported']
    if not pending:return {'imported':0,'posted':0,'review':0,'backup':None}
    private_dir(folder);backup=f.backup(folder);private_file(backup)
    accounts={};advances={};posted=review=0
    with f.transaction('prepared statement import',{'source':plan['data']['source'],'events':len(pending)}):
        if snapshot(f)!=plan['snapshot']:raise ValueError('Finance changed. Run a fresh preview.')
        f.db.execute(TABLE)
        for r in sorted(pending,key=lambda r:(r['date'],0 if r['kind']=='Advance' else 1,r['id'])):
            kind=r['kind'];cash=None;status='Review only'
            if kind!='Review':
                scope=r['scope']
                if scope not in accounts:
                    name=plan['data']['source']+' — historical — opening balance unknown'
                    acct=f.rows('SELECT * FROM accounts WHERE scope=? AND name=?',(scope,name))
                    start=min(x['date'] for x in plan['data']['events'] if x['scope']==scope and x['kind']!='Review')
                    accounts[scope]=acct[0]['id'] if acct else f.account(scope,name,'0',start)
                acct=accounts[scope];n=money(r['amount'],True);cat=None
                if kind in ('Income','Expense') and r.get('category'):cat=f.category(scope,r['category'],kind)
                note=r['description'];ref='statement:'+digest([plan['data']['source'],r['id']])
                if kind=='Reimbursement':
                    inv=advances[r['group']];before=f.db.execute('SELECT COALESCE(MAX(id),0) FROM cash').fetchone()[0]
                    f._pay(inv,acct,n,r['date'])
                    cash=f.db.execute('SELECT id FROM cash WHERE id>? ORDER BY id DESC',(before,)).fetchone()[0]
                    f.db.execute("UPDATE cash SET kind='Reimbursement' WHERE id=?",(cash,))
                else:
                    cash=f._cash(acct,n,kind,note,r['date'],cat,ref)
                    if kind=='Advance':
                        advances[r['group']]=f._invoice(scope,'Receive','Loan',r.get('party','Historical advance'),note,-n,r['date'])
                    elif kind=='Capital':
                        inv=f._invoice(scope,'Receive','Capital',r.get('party','Historical contributor'),note,n,r['date'])
                        f.db.execute('INSERT INTO payments VALUES(NULL,?,?,?)',(inv,cash,n))
                status='Posted; historical debt balance unknown' if kind=='DebtPayment' else ('Posted; crypto basis/quantity review' if kind=='Investment' else 'Posted')
                posted+=1
            else:review+=1
            f.db.execute('INSERT INTO statement_events VALUES(?,?,?,?,?,?)',(plan['data']['source'],r['id'],digest(r),json.dumps(r,ensure_ascii=False),cash,status))
    return {'imported':len(pending),'posted':posted,'review':review,'backup':str(backup)}

def review_records(f):
    return sorted(existing(f).values(),key=lambda r:(json.loads(r['record'])['date'],r['event_id']))

def run(ui,path):
    data=load(path);plan=preview(ui.f,data)
    print('\nPREPARED STATEMENT:',data['source'],'|',data['currency'])
    print('Historical accounts have UNKNOWN opening balances. They do not establish available cash.')
    print('Funding is not sales; historical debt payments do not infer a remaining debt balance.')
    print('Crypto observations do not establish holdings, cost basis or profit.')
    print(data.get('notes',''))
    for i,row in enumerate(plan['rows'],1):
        r=row['event'];print(f"{r['date']} | {r['scope']} | {r['kind']} | {r.get('amount','—')} | {r['description']} | {row['status']}")
        if i%20==0 and i<len(plan['rows']):
            if input('Enter: next page | q: cancel: ').strip().lower()=='q':return
    if input('Type IMPORT to save these events, or Enter to cancel: ').strip()!='IMPORT':return
    result=commit(ui.f,plan,ui.root/'Backups')
    print('Saved:',result['imported'],'| Cash posted:',result['posted'],'| Review only:',result['review'])
    if result['backup']:print('Pre-import private snapshot:',result['backup'])
    print('Use R in the import menu to read saved source/review events. Keep this prepared file.')
    ui.pause()
