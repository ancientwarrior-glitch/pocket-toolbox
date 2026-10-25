"""Bounded local CSV/XLSX cash importer. Preview is read-only; commit is atomic."""
from pathlib import Path
from datetime import datetime,timedelta
from decimal import Decimal,InvalidOperation
from collections import Counter
import csv
import hashlib
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET
from engine import money
from pocket_security import private_dir,private_file

MAX_ROWS=10000
MAX_BYTES=16*1024*1024
NS={'s':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}

def xml(data):
    if b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():raise ValueError('XML declarations/entities are not accepted.')
    try:return ET.fromstring(data)
    except ET.ParseError as e:raise ValueError('Invalid spreadsheet XML.') from e

def workbook(path):
    if Path(path).stat().st_size>MAX_BYTES:raise ValueError('File exceeds 16 MiB limit.')
    try:
        with zipfile.ZipFile(path) as z:
            entries=z.infolist()
            if len(entries)>2000 or sum(i.file_size for i in entries)>32*1024*1024:raise ValueError('Expanded workbook is too large.')
            if len({i.filename for i in entries})!=len(entries):raise ValueError('Duplicate workbook ZIP members.')
            for i in entries:
                if i.filename.endswith('.xml'):xml(z.read(i))
            book=xml(z.read('xl/workbook.xml'));rels=xml(z.read('xl/_rels/workbook.xml.rels'))
            targets={r.get('Id'):r.get('Target') for r in rels if r.get('TargetMode')!='External'}
            sheets=[]
            for s in book.findall('s:sheets/s:sheet',NS):
                target=targets.get(s.get('{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id'),'')
                target=target.lstrip('/') if target.startswith('/') else 'xl/'+target
                if not re.fullmatch(r'xl/worksheets/[^/]+\.xml',target):raise ValueError('Unsupported worksheet location.')
                sheets.append((s.get('name','Sheet'),target))
            prop=book.find('s:workbookPr',NS)
            return sheets, bool(prop is not None and prop.get('date1904') in ('1','true'))
    except (zipfile.BadZipFile,KeyError) as e:raise ValueError('Not a supported XLSX workbook.') from e

def _read_table(path,sheet=None,delimiter=',',encoding='utf-8-sig',header_row=1):
    path=Path(path).expanduser()
    if path.stat().st_size>MAX_BYTES:raise ValueError('File exceeds 16 MiB limit.')
    if not 1<=header_row<=100:raise ValueError('Header row must be between 1 and 100.')
    epoch=False
    if path.suffix.lower()=='.xlsx':
        sheets,epoch=workbook(path)
        if sheet is None:sheet=sheets[0][1] if sheets else ''
        if sheet not in [s[1] for s in sheets]:raise ValueError('Choose a listed worksheet.')
        with zipfile.ZipFile(path) as z:
            shared=[]
            if 'xl/sharedStrings.xml' in z.namelist():
                shared=[''.join(n.itertext()) for n in xml(z.read('xl/sharedStrings.xml')).findall('s:si',NS)]
            rows=[];last=0
            for row in xml(z.read(sheet)).findall('s:sheetData/s:row',NS):
                number=int(row.get('r',str(last+1)))
                if number<=last or number>MAX_ROWS+100:raise ValueError('Unsupported row order or worksheet exceeds 10000 data rows.')
                while len(rows)<number:rows.append([])
                cells=rows[number-1]
                for c in row.findall('s:c',NS):
                    ref=c.get('r','');match=re.fullmatch(r'([A-Z]{1,3})[0-9]+',ref)
                    if not match:raise ValueError('Unsupported cell reference.')
                    col=0
                    for ch in match[1]:col=col*26+ord(ch)-64
                    if col>256:raise ValueError('Worksheets support at most 256 columns.')
                    while len(cells)<col:cells.append('')
                    if c.find('s:f',NS) is not None:
                        value='[FORMULA: paste values first]'
                    else:
                        v=c.find('s:v',NS);value=v.text or '' if v is not None else ''
                        if c.get('t')=='s':
                            index=int(value)
                            if not 0<=index<len(shared):raise ValueError('Invalid shared string reference.')
                            value=shared[index]
                        elif c.get('t')=='inlineStr':value=''.join(c.find('s:is',NS).itertext())
                        elif c.get('t')=='e':value='[CELL ERROR]'
                    cells[col-1]=value
                last=number
    elif path.suffix.lower() in ('.csv','.tsv','.txt'):
        try:
            text=path.read_text(encoding=encoding)
            rows=[]
            for row in csv.reader(io.StringIO(text),delimiter=delimiter,strict=True):
                rows.append(row)
                if len(rows)>MAX_ROWS+100 or len(row)>256:raise ValueError('Limit: 10000 data rows and 256 columns.')
        except (UnicodeError,csv.Error) as e:raise ValueError('Could not decode CSV; check encoding and delimiter.') from e
    else:raise ValueError('Use CSV, TSV or XLSX. Save old .xls files as CSV or XLSX first.')
    if len(rows)<header_row:raise ValueError('Header row is missing.')
    headers=[str(s).strip() for s in rows[header_row-1]]
    if not headers or not any(headers):raise ValueError('Header row is empty.')
    if any(len(s)>4000 or any(ord(c)<32 or ord(c)==127 for c in s) for s in headers):raise ValueError('Header contains control characters or excessive text.')
    records=[]
    for number,row in enumerate(rows[header_row:],header_row+1):
        if not any(str(s).strip() for s in row):continue
        if len(records)>=MAX_ROWS:raise ValueError('Limit: 10000 data rows.')
        if len(row)>len(headers) and any(str(s).strip() for s in row[len(headers):]):raise ValueError(f'Row {number}: more values than headers.')
        if any(len(str(s))>4000 for s in row):raise ValueError(f'Row {number}: a cell exceeds 4000 characters.')
        if any(any(ord(c)<32 or ord(c)==127 for c in str(s)) for s in row):raise ValueError(f'Row {number}: control characters are not accepted.')
        records.append((number,[str(s).strip() for s in row]+['']*max(0,len(headers)-len(row))))
    return headers,records,epoch

def read_table(path,sheet=None,delimiter=',',encoding='utf-8-sig',header_row=1):
    try:return _read_table(path,sheet,delimiter,encoding,header_row)
    except (KeyError,IndexError,TypeError,AttributeError,zipfile.BadZipFile,RuntimeError) as error:
        raise ValueError('Malformed or unsupported spreadsheet. Export its data as CSV and try again.') from error

def amount(text,decimal_mark='.',cents=False):
    text=str(text).strip()
    negative=text.startswith('(') and text.endswith(')')
    if negative:text=text[1:-1]
    grouping=',' if decimal_mark=='.' else '.'
    pattern=r'[+-]?(?:[0-9]+|[0-9]{1,3}(?:'+re.escape(grouping)+r'[0-9]{3})+)(?:'+re.escape(decimal_mark)+r'[0-9]+)?'
    if not re.fullmatch(pattern,text):raise ValueError('Invalid amount; check decimal/grouping format. Currency symbols are not accepted.')
    n=Decimal(text.replace(grouping,'').replace(decimal_mark,'.'))
    if negative:
        if n<0:raise ValueError('Ambiguous negative amount.')
        n=-n
    if cents:
        if n!=n.to_integral_value():raise ValueError('Cents must be whole numbers.')
        n=n/100
    return money(n,True)

def parse_date(text,fmt,epoch=False):
    try:
        if fmt=='excel':
            n=Decimal(text)
            if not n.is_finite() or n<0 or n>100000 or n!=int(n):raise ValueError('Use a whole Excel date serial.')
            if not epoch and n==60:raise ValueError('Excel serial 60 is not a real date.')
            base=datetime(1904,1,1) if epoch else datetime(1899,12,31)
            return (base+timedelta(days=int(n)-(1 if not epoch and n>60 else 0))).date().isoformat()
        return datetime.strptime(text,{'ymd':'%Y-%m-%d','dmy':'%d/%m/%Y','mdy':'%m/%d/%Y'}[fmt]).date().isoformat()
    except (ValueError,InvalidOperation,KeyError,OverflowError) as e:raise ValueError('Invalid date for selected date format.') from e

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,ensure_ascii=False).encode()).hexdigest()

def cash_snapshot(f):
    result=hashlib.sha256()
    for row in f.db.execute('SELECT * FROM cash ORDER BY id'):
        result.update(digest(dict(row)).encode())
    return result.hexdigest()

def preview(f,table,account,source,mapping,mode='signed',date_format='ymd',decimal_mark='.',cents=False):
    headers,records,epoch=table
    if not source.strip():raise ValueError('A stable source label is required.')
    acct=f.one('accounts',account)
    identity='cash-table:'+digest([account,source.strip()])
    result={'source':identity,'account':account,'rows':[],'errors':[],'source_label':source.strip()}
    counts=Counter();ids=set()
    signatures={(r['day'],r['delta'],r['description']) for r in f.db.execute('SELECT day,delta,description FROM cash WHERE account=? AND void=0',(account,))}
    def cell(row,name,required=False):
        index=mapping.get(name)
        if index is None:
            if required:raise ValueError(f'Map the {name} column.')
            return ''
        if not isinstance(index,int) or not 0<=index<len(headers):raise ValueError('Invalid column mapping.')
        value=row[index]
        if value.startswith('[FORMULA:') or value=='[CELL ERROR]':raise ValueError('Mapped cell contains a formula/error. Paste calculated values into a copy first.')
        return value
    if mode not in ('signed','expense','income','split'):raise ValueError('Unknown amount mode.')
    for number,row in records:
        try:
            at=parse_date(cell(row,'date',True),date_format,epoch)
            if at<acct['start']:raise ValueError('Date predates account opening. Review the account opening date/balance.')
            description=cell(row,'description',True)
            if not description:raise ValueError('Description is empty.')
            if mode=='split':
                debit=amount(cell(row,'debit') or '0',decimal_mark,cents)
                credit=amount(cell(row,'credit') or '0',decimal_mark,cents)
                if debit<0 or credit<0 or debit and credit:raise ValueError('Use one positive debit or credit per row.')
                delta=credit-debit
            else:
                delta=amount(cell(row,'amount',True),decimal_mark,cents)
                if mode in ('expense','income'):
                    if delta<0:raise ValueError('Income/expense-only mode requires positive amounts.')
                    if mode=='expense':delta=-delta
            if not delta:raise ValueError('Amount is zero.')
            kind='Income' if delta>0 else 'Expense'
            explicit=cell(row,'kind')
            allowed={'income':'Income','expense':'Expense','ingreso':'Income','gasto':'Expense'}
            if explicit and allowed.get(explicit.lower())!=kind:raise ValueError('Type conflicts or is unsupported. Transfers/trades/invoice payments need their dedicated tools.')
            currency=cell(row,'currency')
            if currency and currency.casefold()!=f.base.casefold():raise ValueError('Currency differs from the Finance base currency; no automatic conversion.')
            cat=cell(row,'category')
            values={'day':at,'delta':delta,'description':description,'category':cat,'kind':kind}
            hashed=digest(values);external=cell(row,'id')
            if external:
                key='id:'+external
                if key in ids:raise ValueError('Duplicate source ID within file.')
                ids.add(key)
            else:
                counts[hashed]+=1;key=f'row:{hashed}:{counts[hashed]}'
            old=f.db.execute('SELECT digest FROM imports WHERE source=? AND key=?',(identity,key)).fetchone()
            if old and old[0]!=hashed:raise ValueError('Previously imported ID has changed. Correct the existing record instead.')
            possible=(at,delta,description) in signatures
            result['rows'].append(dict(values,line=number,key=key,digest=hashed,status='Imported already' if old else 'Possible duplicate' if possible else 'New'))
        except (ValueError,InvalidOperation,IndexError) as e:result['errors'].append(f'Row {number}: {e}')
    result['snapshot']=cash_snapshot(f)
    return result

def commit(f,plan,backup_folder,include_possible=()):
    if plan['errors']:raise ValueError('Fix all invalid rows before importing.')
    include=set(include_possible)
    if not include<={r['line'] for r in plan['rows'] if r['status']=='Possible duplicate'}:raise ValueError('Invalid duplicate override.')
    selected=[r for r in plan['rows'] if r['status']=='New' or r['line'] in include]
    if not selected:return {'imported':0,'skipped':len(plan['rows']),'backup':None}
    folder=private_dir(backup_folder);backup=private_file(f.backup(folder))
    imported=0
    with f.transaction('cash table import',{'source':plan['source_label'],'account':plan['account'],'rows':len(selected)}):
        if plan['snapshot']!=cash_snapshot(f):raise ValueError('Cash records changed after preview. Preview again.')
        account=f.one('accounts',plan['account'])
        for r in selected:
            old=f.db.execute('SELECT digest FROM imports WHERE source=? AND key=?',(plan['source'],r['key'])).fetchone()
            if old:
                if old[0]!=r['digest']:raise ValueError('Previously imported ID changed.')
                continue
            category=f.category(account['scope'],r['category'],r['kind']) if r['category'] else None
            f._cash(plan['account'],r['delta'],r['kind'],r['description'],r['day'],category)
            f.db.execute('INSERT INTO imports VALUES(?,?,?)',(plan['source'],r['key'],r['digest']));imported+=1
    return {'imported':imported,'skipped':len(plan['rows'])-imported,'backup':str(backup)}
