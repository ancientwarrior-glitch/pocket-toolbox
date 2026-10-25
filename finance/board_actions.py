"""Small allowlisted board actions; JSON files retain their original formats."""
from contextlib import closing
from pathlib import Path
import hashlib
import json
import os
import re
import tempfile
import threading

from engine import Finance, quantity_in
from pocket_security import no_links,private_dir,private_file


def render_editor(state):
    serialized = json.dumps(state, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    html=EDITOR.replace('__EDITOR_DATA__', serialized)
    return html.replace('Workspace/Notes.','the toolbox data/notes folder.') if state.get('public') else html


EDITOR = r'''<style>
.editor{margin-top:20px}.editor h2{margin-top:0}.editor label{display:block;color:#bdc4d7;font-size:14px;margin:12px 0}.editor input:not([type=checkbox]),.editor textarea,.editor select{display:block;width:100%;background:#111a29;color:#f4f3fc;border:1px solid #52607b;border-radius:8px;padding:12px;margin-top:5px;font:inherit;min-height:46px}.editor textarea{min-height:100px;resize:vertical}.editor button{background:#4d3a78;color:white;border:1px solid #a88add;border-radius:9px;min-height:46px;padding:10px 18px;font:inherit;cursor:pointer;margin:8px 4px 8px 0}.editor button:disabled{opacity:.5;cursor:wait}.editor input[type=checkbox]{width:24px;height:24px;vertical-align:middle;margin-right:12px}.editor .list-item{border-bottom:1px solid #34405a;padding:8px 0;overflow-wrap:anywhere}.editor fieldset{border:0;padding:0;margin:0}.editor details{margin-top:12px}.editor summary{cursor:pointer;padding:12px 0}#save-status{position:sticky;bottom:10px;background:#25304b;border:1px solid #a88add;border-radius:10px;padding:14px;z-index:2;display:none}
</style><div class="editor"><h2>Update your records</h2><p>Changes save to your phone. Keep this Termux session open.</p><div id="edit-errors"></div><div class="grid">
<section><h2>Shopping checklist</h2><div id="shopping-edit"></div><form id="shopping-add"><label>New item<input name="text" maxlength="500" required placeholder="What do you need?"></label><button>Add item</button></form></section>
<section><h2>Upload statuses</h2><p>Updates the tracker only. It does not upload or delete media.</p><div id="uploads-edit"></div></section>
<section><h2>Quick note</h2><form id="note-add"><label>Note<textarea name="text" maxlength="8000" required></textarea></label><button>Save note</button></form><small>Saved as a new board-…txt file in Workspace/Notes.</small></section>
<section><h2>Income or expense</h2><p>For simple cash entries. Stock purchases, sales invoices, debt payments and transfers still belong in their Finance menus; avoid entering the same payment twice.</p><form id="cash-add"><fieldset id="cash-fields"><label>Account<select name="account" id="cash-account" required></select></label><label>Type<select name="kind" id="cash-kind"><option>Expense</option><option>Income</option></select></label><label>Category<select name="category" id="cash-category"></select></label><label>Amount <span id="cash-currency"></span><input name="amount" inputmode="decimal" placeholder="0.00" required maxlength="40"></label><label>Date<input name="day" type="date" required></label><label>Description<input name="description" required maxlength="1000"></label><button>Save cash entry</button></fieldset></form><small id="cash-hint"></small></section>
</div><p><button type="button" id="refresh-board">Refresh board</button></p><p id="save-status" role="status" aria-live="polite"></p></div>
<script type="application/json" id="editor-data">__EDITOR_DATA__</script><script>
(()=>{'use strict';const S=JSON.parse(document.getElementById('editor-data').textContent),$=id=>document.getElementById(id),root=location.pathname.replace(/\/$/,''),status=$('save-status');let busy=false;
function element(tag,text){let e=document.createElement(tag);if(text!==undefined)e.textContent=text;return e}
function message(text){status.style.display='block';status.textContent=text}
function id(){return crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(20)),n=>n.toString(16).padStart(2,'0')).join('')}
async function save(data,holder){if(busy)return;let signature=JSON.stringify(data);if(!holder.pending||holder.pending.signature!==signature)holder.pending={signature,payload:{...data,request_id:id()}};busy=true;document.querySelectorAll('.editor button,.editor input,.editor select,.editor textarea').forEach(e=>e.disabled=true);message('Saving…');try{let response=await fetch(root+'/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(holder.pending.payload)}),result=await response.json();if(!response.ok||!result.ok)throw Error(result.message||'Could not save.');location.reload()}catch(error){message(error.message+' If the session ended, reopen Dashboard in Termux.');busy=false;document.querySelectorAll('.editor button,.editor input,.editor select,.editor textarea').forEach(e=>e.disabled=false);if(!S.accounts.length)$('cash-fields').disabled=true}}
for(let error of S.errors)$('edit-errors').append(element('p',error));
let shopping=S.lists.shopping;if(shopping){for(let row of shopping.rows){let label=element('label'),check=document.createElement('input');label.className='list-item';check.type='checkbox';check.checked=row.done;check.addEventListener('change',()=>save({action:'shopping-check',revision:shopping.revision,index:row.index,done:check.checked},check));label.append(check,document.createTextNode(row.text));$('shopping-edit').append(label)}}else{$('shopping-add').hidden=true}
$('shopping-add').addEventListener('submit',event=>{event.preventDefault();if(shopping)save({action:'shopping-add',revision:shopping.revision,text:new FormData(event.target).get('text')},event.target)});
let uploads=S.lists.uploads;if(uploads){for(let row of uploads.rows){let box=element('form'),label=element('label',row.text),select=element('select');for(let value of new Set(['To upload','Published','Download checked',row.status]))select.add(new Option(value,value));select.value=row.status;label.append(select);let button=element('button','Save status');box.append(label,button);box.className='list-item';box.addEventListener('submit',event=>{event.preventDefault();save({action:'upload-status',revision:uploads.revision,index:row.index,status:select.value},box)});$('uploads-edit').append(box)}if(!uploads.rows.length)$('uploads-edit').append(element('p','No upload records yet. Add videos through Lists and trackers.'))}
$('note-add').addEventListener('submit',event=>{event.preventDefault();save({action:'note-add',text:new FormData(event.target).get('text')},event.target)});
for(let account of S.accounts)$('cash-account').add(new Option(account.scope+' · '+account.name,String(account.id)));
function categories(){let account=S.accounts.find(a=>String(a.id)===$('cash-account').value),kind=$('cash-kind').value;$('cash-category').replaceChildren(new Option('Uncategorized',''));for(let c of S.categories.filter(c=>account&&c.scope===account.scope&&c.kind===kind))$('cash-category').add(new Option(c.name,String(c.id)))}
$('cash-account').addEventListener('change',categories);$('cash-kind').addEventListener('change',categories);categories();$('cash-currency').textContent='· '+S.currency;
const local=new Date(),today=[local.getFullYear(),String(local.getMonth()+1).padStart(2,'0'),String(local.getDate()).padStart(2,'0')].join('-');$('cash-add').elements.day.value=today;
if(!S.accounts.length){$('cash-fields').disabled=true;$('cash-hint').textContent='Create accounts in Finance → 1 first.'}
$('cash-add').addEventListener('submit',event=>{event.preventDefault();let fields=Object.fromEntries(new FormData(event.target));fields.account=Number(fields.account);fields.category=fields.category?Number(fields.category):null;save({action:'cash-add',...fields},event.target)});
$('refresh-board').addEventListener('click',()=>location.reload());
})();</script>'''


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


class BoardActions:
    def __init__(self, home, finance_path,public_root=None):
        self.home = Path(home)
        self.finance_path = Path(finance_path)
        self.organizer = self.home / 'Workspace/Organizer'
        self.public_root=Path(public_root) if public_root else None
        if self.public_root:self.organizer=self.public_root/'data'
        self.lock = threading.RLock()
        self.receipts = {}

    def read_list(self, kind):
        if kind not in ('shopping', 'uploads'):
            raise ValueError('Unknown list.')
        path = self.organizer / (kind + '.json')
        no_links(path)
        raw = path.read_bytes() if path.exists() else b'[]'
        try:
            rows = json.loads(raw)
            if not isinstance(rows, list) or any(not isinstance(r, dict) for r in rows):
                raise ValueError()
            field = 'text' if kind == 'shopping' else 'title'
            if any(not isinstance(r.get(field), str) for r in rows):
                raise ValueError()
        except (ValueError, TypeError):
            raise ValueError('Cannot edit ' + kind + ': unexpected file format. Original file left unchanged.')
        return path, raw, rows

    def state(self):
        with self.lock:
            lists = {}
            errors = []
            for kind in ('shopping', 'uploads'):
                try:
                    _, raw, rows = self.read_list(kind)
                    lists[kind] = dict(revision=digest(raw), rows=[dict(index=i, text=r.get('text', r.get('title')), done=bool(r.get('done')), status=r.get('status', 'To upload')) for i, r in enumerate(rows)])
                except (ValueError, OSError) as error:
                    errors.append(str(error))
            with closing(Finance(self.finance_path)) as finance:
                accounts = [dict(r) for r in finance.rows('SELECT id,scope,name FROM accounts ORDER BY scope,name')]
                categories = [dict(r) for r in finance.rows('SELECT id,scope,name,kind FROM categories ORDER BY scope,kind,name')]
                currency = finance.base
            return dict(lists=lists, errors=errors, accounts=accounts, categories=categories, currency=currency,public=bool(self.public_root))

    @staticmethod
    def text(request, name, limit):
        value = request.get(name)
        if not isinstance(value, str) or not value.strip() or len(value) > limit:
            raise ValueError(f'{name}: enter 1–{limit} characters.')
        return value.strip()

    def save_list(self, kind, request):
        path, raw, rows = self.read_list(kind)
        if request.get('revision') != digest(raw):
            raise ValueError('This list changed. Refresh the board before editing it.')
        action = request['action']
        if action == 'shopping-add':
            rows.append(dict(text=self.text(request, 'text', 500), done=False))
        else:
            index = request.get('index')
            if type(index) is not int or not 0 <= index < len(rows):
                raise ValueError('Item no longer exists. Refresh the board.')
            if action == 'shopping-check':
                if type(request.get('done')) is not bool:
                    raise ValueError('Invalid checklist state.')
                rows[index]['done'] = request['done']
            else:
                status = request.get('status')
                if status not in ('To upload', 'Published', 'Download checked'):
                    raise ValueError('Choose a supported upload status.')
                rows[index]['status'] = status
        private_dir(path.parent)
        backups = self.organizer / 'Board-Backups'
        private_dir(backups)
        if path.exists():
            # Exact previous bytes are retained once per content version.
            backup = backups / (kind + '-' + digest(raw) + '.json')
            no_links(backup)
            if not backup.exists():
                with backup.open('xb') as out:
                    out.write(raw)
        encoded = json.dumps(rows, ensure_ascii=False, indent=2).encode('utf-8')
        fd, name = tempfile.mkstemp(prefix='.board-', dir=path.parent)
        try:
            with os.fdopen(fd, 'wb') as out:
                out.write(encoded); out.flush(); os.fsync(out.fileno())
            current = path.read_bytes() if path.exists() else b'[]'
            if current != raw:
                raise ValueError('This list changed while saving. Refresh the board.')
            os.replace(name, path)
        finally:
            Path(name).unlink(missing_ok=True)

    def cash(self, request, request_id, signature):
        account = request.get('account')
        category = request.get('category')
        if type(account) is not int or category is not None and type(category) is not int:
            raise ValueError('Choose an account and category.')
        description = self.text(request, 'description', 1000)
        value = self.text(request, 'amount', 40)
        at = self.text(request, 'day', 10)
        kind = request.get('kind')
        with closing(Finance(self.finance_path)) as finance:
            with finance.transaction('board cash request', {'request': request_id}):
                old = finance.db.execute('SELECT digest FROM imports WHERE source=? AND key=?', ('board-cash', request_id)).fetchone()
                if old:
                    if old[0] != signature:
                        raise ValueError('Request ID already used for a different entry.')
                    return
                finance.cash_entry(account, value, kind, description, at, category)
                finance.db.execute('INSERT INTO imports VALUES(?,?,?)', ('board-cash', request_id, signature))

    def finance_action(self, request, request_id, signature):
        def text(name, limit=500):return self.text(request,name,limit)
        def ident(name, optional=False):
            value=request.get(name)
            if optional and value is None:return None
            if type(value) is not int or value<=0:raise ValueError('Choose '+name+'.')
            return value
        with closing(Finance(self.finance_path)) as finance:
            with finance.transaction('board finance request', {'request':request_id,'action':request['action']}):
                old=finance.db.execute('SELECT digest FROM imports WHERE source=? AND key=?',('board-finance',request_id)).fetchone()
                if old:
                    if old[0]!=signature:raise ValueError('Request ID already used for a different entry.')
                    return
                action=request['action']
                if action=='budget-set':
                    category=ident('category')
                    if finance.one('categories',category)['kind']!='Expense':raise ValueError('Choose an expense category.')
                    finance.set_budget(text('month',7),category,text('amount',40))
                elif action=='goal-add':
                    finance.plan(text('scope',20),text('name'),text('target',40),text('due',10),text('monthly',40))
                elif action=='goal-allocate':
                    if type(request.get('committed')) is not bool:raise ValueError('Choose reserved or committed.')
                    finance.allocate(ident('goal'),text('amount',40),request['committed'])
                elif action=='item-add':
                    finance.item(text('name'),text('kind',20),text('unit',10))
                elif action=='price-set':
                    finance.price(text('asset',30),text('price',60),at=text('day',10),quote=text('quote',30),fx=text('fx',60))
                elif action in ('stock-opening','stock-receive','product-sale'):
                    item=ident('item');record=finance.one('items',item)
                    quantity=str(quantity_in(text('quantity',60),record['unit']))
                    if action=='stock-opening':
                        finance.opening_stock(item,quantity,text('total',40),at=text('day',10),note=text('description'))
                    else:
                        if record['kind']!=('Product' if action=='product-sale' else 'Material'):
                            raise ValueError('Choose a finished product for a sale or a material for a receipt.')
                        account=ident('account',True)
                        if account and finance.one('accounts',account)['scope']!='Business':raise ValueError('Choose a Business account.')
                        function=finance.sell if action=='product-sale' else finance.receive_stock
                        function(item,quantity,text('total',40),party=text('party'),at=text('day',10),account=account,paid=text('paid',40))
                elif action=='batch-produce':
                    product=ident('product');record=finance.one('items',product)
                    ingredients=request.get('ingredients')
                    if not isinstance(ingredients,list) or not 1<=len(ingredients)<=100:raise ValueError('Add 1–100 materials.')
                    parsed=[]
                    for row in ingredients:
                        if not isinstance(row,dict) or type(row.get('item')) is not int:raise ValueError('Choose a material.')
                        material=finance.one('items',row['item'])
                        value=self.text(row,'quantity',60)
                        parsed.append((row['item'],str(quantity_in(value,material['unit']))))
                    finance.produce(text('name'),product,str(quantity_in(text('quantity',60),record['unit'])),parsed,
                                    labor=text('labor',40),overhead=text('overhead',40),at=text('day',10))
                elif action=='invoice-payment':
                    invoice=ident('invoice');account=ident('account');mode=text('mode',20)
                    if mode not in ('Payment','Refund'):raise ValueError('Choose Payment or Refund.')
                    function=finance.pay if mode=='Payment' else finance.refund
                    function(invoice,account,text('amount',40),at=text('day',10))
                else:raise ValueError('Unknown finance action.')
                finance.db.execute('INSERT INTO imports VALUES(?,?,?)',('board-finance',request_id,signature))

    def __call__(self, request):
        with self.lock:
            request_id = request.get('request_id', '')
            if not isinstance(request_id, str) or not re.fullmatch(r'[a-zA-Z0-9-]{16,80}', request_id):
                raise ValueError('Invalid request ID. Refresh the board.')
            signature = digest(json.dumps(request, sort_keys=True).encode())
            if request_id in self.receipts:
                if self.receipts[request_id] != signature:
                    raise ValueError('Request ID already used for a different action.')
                return dict(ok=True, message='Already saved.')
            action = request.get('action')
            if action in ('shopping-add', 'shopping-check', 'upload-status'):
                self.save_list('uploads' if action == 'upload-status' else 'shopping', request)
            elif action == 'cash-add':
                self.cash(request, request_id, signature)
            elif action in ('budget-set','goal-add','goal-allocate','item-add','price-set','stock-opening','stock-receive','product-sale','batch-produce','invoice-payment'):
                self.finance_action(request,request_id,signature)
            elif action == 'note-add':
                text = self.text(request, 'text', 8000)
                folder = self.public_root/'data/notes' if self.public_root else self.home / 'Workspace/Notes'
                private_dir(folder)
                path = folder / ('board-' + request_id + '.txt')
                no_links(path)
                if path.exists():
                    if path.read_text() != text + '\n':
                        raise ValueError('Request ID already used for a different note.')
                else:
                    with path.open('x', encoding='utf-8') as out:
                        out.write(text + '\n')
            else:
                raise ValueError('Unknown board action.')
            self.receipts[request_id] = signature
            return dict(ok=True, message='Saved.')
