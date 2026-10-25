"""Guided local cash import for both public and original toolbox menus."""
from pathlib import Path
from decimal import Decimal
from cash_import import read_table,workbook,preview,commit

def numbers(text,valid):
    if not text.strip():return set()
    try:chosen={int(n.strip()) for n in text.split(',')}
    except ValueError:raise ValueError('Use comma-separated row numbers.')
    if not chosen<=set(valid):raise ValueError('Choose only listed row numbers.')
    return chosen

def run(ui):
    ui.heading('IMPORT RECORDS — CSV / XLSX / PREPARED JSON')
    print('CSV/XLSX: income/expenses. Prepared JSON: cash roles and saved review events. Local only.')
    print('For CSV/XLSX, exclude transfers, investments, stock and linked invoice payments; use their dedicated tools.')
    print('Import each movement once. Opening balance must be BEFORE imported movements.')
    downloads=Path(getattr(ui,'downloads',Path.home()/'storage/downloads'))
    files=sorted((p for p in downloads.iterdir() if p.is_file() and p.suffix.lower() in ('.csv','.tsv','.xlsx','.json')),key=lambda p:p.stat().st_mtime,reverse=True)[:50] if downloads.is_dir() else []
    for i,p in enumerate(files,1):print(f'{i:>3}  {p.name}')
    answer=input('\nFile number, full path, R for saved events, or Enter to cancel: ').strip()
    if not answer:return
    if answer.lower()=='r':
        import json
        from statement_import import review_records
        rows=review_records(ui.f)
        if not rows:print('No prepared statement events saved yet.')
        for i,row in enumerate(rows,1):
            print(row['status'], '|', json.dumps(json.loads(row['record']),ensure_ascii=False))
            if i%10==0 and i<len(rows):
                if input('Enter: next page | q: stop: ').strip().lower()=='q':break
        ui.pause();return
    if answer.isdigit():
        if not 1<=int(answer)<=len(files):raise ValueError('Choose a listed file number.')
        path=files[int(answer)-1]
    else:path=Path(answer.strip('"\'')).expanduser()
    if path.suffix.lower()=='.json':
        from statement_import import run as statement_run
        statement_run(ui,path);return
    sheet=None;delimiter=',';encoding='utf-8-sig'
    if path.suffix.lower()=='.xlsx':
        selected=ui.choose(workbook(path)[0],lambda r:r[0])
        if selected is None:return
        sheet=selected[1]
    else:
        selected=ui.choose([('Comma',','),('Semicolon',';'),('Tab','\t'),('Pipe','|')],lambda r:r[0])
        if selected is None:return
        delimiter=selected[1]
        encoding=ui.choose(['utf-8-sig','cp1252'])
        if encoding is None:return
    header=int(input('Header row number (Enter: 1): ').strip() or '1')
    table=read_table(path,sheet,delimiter,encoding,header)
    headers,records,_=table
    if not records:raise ValueError('No data rows found.')
    print('\nCOLUMNS AND FIRST THREE DATA ROWS')
    for i,h in enumerate(headers,1):
        samples=' | '.join(row[i-1] for _,row in records[:3])
        print(f'{i:>3}  {h or "(blank header)"}: {samples}')
    mapping={}
    def column(key,label,required=False):
        value=input(label+(' column number: ' if required else ' column number (Enter: unused): ')).strip()
        if not value:
            if required:raise ValueError('Required mapping missing. Cancelled without saving.')
            return
        if not value.isdigit() or not 1<=int(value)<=len(headers):raise ValueError('Choose a listed column.')
        mapping[key]=int(value)-1
    column('date','Date',True);column('description','Description',True)
    mode=ui.choose(['signed','split','expense','income'],lambda s:{'signed':'Signed amount: positive income, negative expense','split':'Separate debit (money out) / credit (money in)','expense':'Positive amounts, all expenses','income':'Positive amounts, all income'}[s])
    if not mode:return
    if mode=='split':column('debit','Debit / money out',True);column('credit','Credit / money in',True)
    else:column('amount','Amount',True)
    column('category','Category name');column('id','Stable transaction ID');column('currency','Currency');column('kind','Type (Income/Expense or Ingreso/Gasto only)')
    fmt=ui.choose(['ymd','dmy','mdy','excel'],lambda s:{'ymd':'YYYY-MM-DD','dmy':'DD/MM/YYYY','mdy':'MM/DD/YYYY','excel':'Excel date serial (e.g. 46320)'}[s])
    mark=ui.choose(['.',','],lambda s:'Decimal '+s+' | example '+('1,234.56' if s=='.' else '1.234,56'))
    units=ui.choose(['major','cents'],lambda s:'Normal currency units (123.45)' if s=='major' else 'Whole cents (12345 means 123.45)')
    if not fmt or not mark or not units:return
    account=ui.account()
    if account is None:return
    print('Use the SAME source label for future files from this account/provider, even if the filename changes.')
    source=ui.required('Source label (example: my-cash-spreadsheet): ')
    if 'id' not in mapping:print('No source IDs: exact repeated rows can be recognized; edited rows may look new. Review carefully.')
    print('Exclude source row numbers for transfers, totals, trades or linked payments. Example: 5,8,12.')
    excluded=numbers(input('Rows to exclude (Enter: none): '),[n for n,_ in records])
    table=(headers,[(n,r) for n,r in records if n not in excluded],table[2])
    plan=preview(ui.f,table,account['id'],source,mapping,mode,fmt,mark,units=='cents')
    if plan['errors']:
        print('\nNOTHING SAVED. Fix these rows or exclude them on the next attempt:')
        for e in plan['errors']:print(e)
        ui.pause();return
    print(f'\nPREVIEW | {account["scope"]} / {account["name"]} | {ui.f.base} | Source: {source}')
    print('Source row | date | amount | type | category | description | status')
    for i,r in enumerate(plan['rows'],1):
        print(f'{r["line"]} | {r["day"]} | {Decimal(r["delta"])/100:.2f} | {r["kind"]} | {r["category"] or "Uncategorized"} | {r["description"]} | {r["status"]}')
        if i%20==0 and i<len(plan['rows']):
            if input('Enter: next preview page | q: cancel: ').strip().lower()=='q':return
    existing={(r['name'],r['kind']) for r in ui.f.rows('SELECT name,kind FROM categories WHERE scope=?',(account['scope'],))}
    newcats=sorted({(r['category'],r['kind']) for r in plan['rows'] if r['category'] and (r['category'],r['kind']) not in existing and r['status']!='Imported already'})
    if newcats:print('Category names to create if selected:',', '.join(f'{n} ({k})' for n,k in newcats))
    suspects=[r['line'] for r in plan['rows'] if r['status']=='Possible duplicate']
    include=set()
    if suspects:
        print('Possible duplicates match an existing account/date/amount/description. They are SKIPPED by default.')
        include=numbers(input('Only if these are genuinely separate movements, enter their row numbers to include: '),suspects)
    selected=[r for r in plan['rows'] if r['status']=='New' or r['line'] in include]
    print(f'\nWill import {len(selected)}; skip {len(plan["rows"])-len(selected)}; excluded {len(excluded)}.')
    print('Income:',ui.money(sum(r['delta'] for r in selected if r['delta']>0)))
    print('Expenses:',ui.money(-sum(r['delta'] for r in selected if r['delta']<0)))
    print('Verify dates, signs, account and opening balance. This records CASH, not inventory, invoices or trading positions.')
    if not selected:return
    if input('Type IMPORT to save, or Enter to cancel: ').strip()!='IMPORT':
        print('Cancelled. Nothing saved.');return
    result=commit(ui.f,plan,ui.root/'Backups',include)
    print('Imported:',result['imported'],'| Skipped:',result['skipped'])
    print('Private pre-import Finance snapshot:',result['backup'])
    ui.pause()
