"""Read-only business board built from the Finance ledger."""
from calendar import monthrange
from datetime import date
from decimal import Decimal
import json


def board_data(finance, today=None):
    today = today or date.today()
    end = today.isoformat()
    items = []
    for row in finance.rows('SELECT * FROM items ORDER BY kind,name'):
        item = dict(row)
        quantity, value = finance.stock(item['id'], end)
        item.update(quantity=str(quantity), value=value)
        items.append(item)
    batches = []
    for row in finance.rows('SELECT b.*,i.name product_name,i.unit FROM batches b JOIN items i ON i.id=b.product WHERE b.day<=? ORDER BY b.day DESC,b.id DESC', (end,)):
        batch = dict(row)
        batch['age'] = (today - date.fromisoformat(batch['day'])).days
        batch['cost'] = batch['materials'] + batch['labor'] + batch['overhead']
        # Keep decimal quantities as text until display; monetary totals remain cents.
        batch['unit_cost'] = str(Decimal(batch['cost']) / Decimal(batch['quantity']) / 100)
        batches.append(batch)
    bills = []
    for row in finance.rows("SELECT * FROM invoices WHERE scope='Business' AND day<=? ORDER BY day,id", (end,)):
        bill = dict(row)
        if bill['void'] and bill['void_day'] and bill['void_day'] <= end:
            continue
        paid = finance.db.execute('SELECT COALESCE(SUM(p.amount),0) FROM payments p JOIN cash c ON c.id=p.cash WHERE p.invoice=? AND c.day<=? AND c.void=0', (bill['id'], end)).fetchone()[0]
        credited = finance.db.execute('SELECT COALESCE(SUM(total),0) FROM credits WHERE invoice=? AND day<=?', (bill['id'], end)).fetchone()[0]
        bill['balance'] = bill['total'] - paid - credited
        if bill['balance']:
            bills.append(bill)
    months = []
    for offset in range(11, -1, -1):
        number = today.year * 12 + today.month - 1 - offset
        year, index = divmod(number, 12)
        month = index + 1
        start = f'{year:04}-{month:02}-01'
        finish = min(date(year, month, monthrange(year, month)[1]), today).isoformat()
        result = finance.business_result(start, finish)
        months.append(dict(month=start[:7], **result))
    return dict(today=end, currency=finance.base, items=items, batches=batches,
                bills=bills, months=months)


def render_board(data):
    serialized = json.dumps(data, ensure_ascii=False).replace('<', '\\u003c').replace('>', '\\u003e').replace('&', '\\u0026')
    return PAGE.replace('__DATA__', serialized)


PAGE = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Jabones Yayo · Business board</title>
<style>
:root{color-scheme:dark;--bg:#101a18;--panel:#192824;--line:#32483f;--muted:#adc3b8;--mint:#99e2b1;--amber:#ffce83;--red:#ffaaa1}*{box-sizing:border-box}body{margin:0;background:var(--bg);color:#eff7f1;font:16px/1.5 system-ui,sans-serif}main{max-width:1100px;margin:auto;padding:28px 16px 48px}h1{font-size:clamp(28px,6vw,44px);margin:3px 0 8px;letter-spacing:-1px}h2{font-size:20px;margin:0 0 8px}p{color:var(--muted);margin:6px 0 16px}.tag{color:var(--mint);text-transform:uppercase;letter-spacing:2px;font-size:12px}.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:24px 0}.card,section{background:var(--panel);border:1px solid var(--line);border-radius:16px;padding:18px}.card span{display:block;font-size:13px;color:var(--muted)}.card strong{display:block;margin-top:7px;font-size:23px;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.wide{grid-column:1/-1}.controls{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}label{color:var(--muted);font-size:13px;display:flex;flex-direction:column;gap:5px;flex:1}input,select{background:#101a18;color:#eff7f1;border:1px solid var(--line);border-radius:8px;padding:11px;font:inherit;min-height:44px}.scroll{overflow:auto}table{width:100%;border-collapse:collapse;font-size:14px;min-width:400px}th,td{padding:12px 8px;border-bottom:1px solid var(--line);text-align:right;vertical-align:top}th:first-child,td:first-child{text-align:left}small{display:block;color:var(--muted);font-size:12px}.badge{color:var(--amber)}.empty{padding:24px 12px;border:1px dashed var(--line);border-radius:10px;color:var(--muted)}.batch{border-bottom:1px solid var(--line);padding:15px 0}.batch-head{display:flex;justify-content:space-between;gap:12px}.track{background:#30493d;height:9px;border-radius:8px;overflow:hidden;margin:9px 0}.fill{background:var(--mint);height:100%}.legend{font-size:13px;color:var(--muted)}svg{display:block;width:100%;height:auto}svg [tabindex]{cursor:pointer}svg [tabindex]:focus{outline:2px solid white}.detail{min-height:28px;font-size:14px}footer{font-size:13px;color:var(--muted);margin-top:24px}@media(max-width:700px){.cards{grid-template-columns:1fr 1fr}.grid{grid-template-columns:1fr}.wide{grid-column:auto}.card strong{font-size:20px}main{padding:20px 12px}section{padding:16px}}
</style></head><body><main><header><div class="tag">Pocket Finance · business board</div><h1>Jabones Yayo</h1><p id="snapshot"></p></header>
<div class="cards"><div class="card"><span>Stock at recorded cost</span><strong id="stock-value"></strong></div><div class="card"><span>Net sales · this month</span><strong id="sales"></strong></div><div class="card"><span>Business amounts to collect</span><strong id="collect"></strong></div><div class="card"><span>Business amounts to pay</span><strong id="pay"></strong></div></div>
<div class="grid"><section class="wide"><h2>Sales & cost of goods sold</h2><p>Last 12 months. Net sales include credit sales and dated returns/reversals; they are not cash collected.</p><div class="legend">Green: net sales · Amber: cost of goods sold</div><div id="sales-chart"></div><div class="detail" id="sales-detail"></div></section>
<section class="wide"><h2>Supplies & finished stock</h2><p>Quantities stay in their own units. Stock value is recorded cost, not a selling-price estimate.</p><div class="controls"><label>Find an item<input id="search" type="search" placeholder="Lard, bottles, soap…"></label><label>Show<select id="kind"><option value="all">All stock</option><option>Material</option><option>Product</option><option value="empty">Out of stock</option></select></label></div><div id="inventory" class="scroll"></div></section>
<section><h2>Production & batch ages</h2><p>Ages are days since production. A date or filled bar does not establish that soap is cured or ready for use.</p><label>Planning age marker · days<input id="age-marker" type="number" min="1" max="3650" value="42"></label><small>Display aid only, not a product-specific cure rule. Changes last for this page session.</small><div id="batches"></div></section>
<section><h2>Open bills & credits</h2><p>Includes sales, supplier bills, loans and capital obligations. No due dates are recorded, so these are not marked overdue.</p><div id="bills"></div></section></div>
<footer>Read-only Finance snapshot. Add or correct stock, batches, sales and payments through Finance → 6 / 5. Existing batch notes in the older Jabones menu are separate and are not imported here. Reopen this board to refresh. No external scripts or uploads.</footer></main>
<script type="application/json" id="data">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id);
const money=n=>new Intl.NumberFormat(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}).format(n/100)+' '+D.currency;
const num=n=>new Intl.NumberFormat(undefined,{maximumFractionDigits:6}).format(Number(n));
function node(tag,text,cls){let n=document.createElement(tag);if(text!==undefined)n.textContent=text;if(cls)n.className=cls;return n}
function empty(id,text){$(id).replaceChildren(node('div',text,'empty'))}
function table(id,headers,rows){if(!rows.length){empty(id,'No matching records yet.');return}let t=node('table'),head=node('tr');headers.forEach(h=>head.append(node('th',h)));let thead=node('thead');thead.append(head);t.append(thead);let body=node('tbody');for(let cells of rows){let tr=node('tr');for(let cell of cells){let td=node('td');if(cell instanceof Node)td.append(cell);else td.textContent=cell;tr.append(td)}body.append(tr)}t.append(body);$(id).replaceChildren(t)}
function inventory(){let q=$('search').value.toLocaleLowerCase(),kind=$('kind').value,items=D.items.filter(i=>i.name.toLocaleLowerCase().includes(q)&&(kind==='all'||kind==='empty'&&Number(i.quantity)===0||i.kind===kind));table('inventory',['Item','On hand','Recorded cost'],items.map(i=>{let name=node('span',i.name);name.append(node('small',i.kind+(Number(i.quantity)===0?' · Out of stock':'')));return[name,num(i.quantity)+' '+i.unit,money(i.value)]}))}
function batches(){if(!D.batches.length){empty('batches','No Finance production batches yet. Add one through Supplies, stock, batches and sales.');return}let marker=Math.min(3650,Math.max(1,Number($('age-marker').value)||42));$('batches').replaceChildren();for(let b of D.batches){let box=node('div',undefined,'batch'),head=node('div',undefined,'batch-head');head.append(node('strong',b.name),node('span',b.age+' days','badge'));box.append(head,node('small',b.product_name+' · '+b.day+' · '+num(b.quantity)+' '+b.unit));let track=node('div',undefined,'track'),fill=node('div',undefined,'fill');fill.style.width=Math.min(100,b.age/marker*100)+'%';track.append(fill);box.append(track,node('small','Batch cost '+money(b.cost)+' · '+money(Number(b.unit_cost)*100)+' / '+b.unit),node('small','Materials '+money(b.materials)+' · Labor '+money(b.labor)+' · Overhead '+money(b.overhead)));$('batches').append(box)}}
function bills(){if(!D.bills.length){empty('bills','No open business bills or credits recorded.');return}$('bills').replaceChildren();for(let b of D.bills){let credit=b.balance<0,label=credit?(b.direction==='Receive'?'Refund owed to customer':'Supplier/party credit to recover'):(b.direction==='Receive'?'To collect':'To pay');let box=node('div',undefined,'batch'),head=node('div',undefined,'batch-head');head.append(node('strong',b.party||'Unnamed party'),node('span',money(Math.abs(b.balance)),'badge'));box.append(head,node('small',label+' · '+b.kind+' · '+b.day),node('div',b.description));$('bills').append(box)}}
function graph(){if(!D.months.some(m=>m.revenue||m.cogs)){empty('sales-chart','No sales or cost-of-goods activity in these 12 months yet.');return}const NS='http://www.w3.org/2000/svg';function svg(tag,attrs,text){let n=document.createElementNS(NS,tag);for(let[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n}let s=svg('svg',{viewBox:'0 0 700 270',role:'img','aria-label':'Monthly net sales and cost of goods sold'}),vals=D.months.flatMap(m=>[m.revenue,m.cogs]),low=Math.min(0,...vals),high=Math.max(100,...vals),y=v=>220-(v-low)/(high-low)*180;for(let j=0;j<4;j++){let v=low+(high-low)*j/3,yy=y(v);s.append(svg('line',{x1:65,x2:685,y1:yy,y2:yy,stroke:'#32483f'}),svg('text',{x:58,y:yy+4,fill:'#adc3b8','font-size':11,'text-anchor':'end'},num(v/100)))}s.append(svg('line',{x1:65,x2:685,y1:y(0),y2:y(0),stroke:'#adc3b8'}));D.months.forEach((m,i)=>{let x=65+(i+.5)*620/12;[m.revenue,m.cogs].forEach((v,j)=>{let bar=svg('rect',{x:x+(j?2:-17),y:Math.min(y(v),y(0)),width:15,height:Math.abs(y(v)-y(0)),rx:2,fill:j?'#ffce83':'#99e2b1',tabindex:0,'aria-label':m.month+' '+(j?'COGS ':'Net sales ')+money(v)}),text=m.month+' · Net sales '+money(m.revenue)+' · COGS '+money(m.cogs);bar.append(svg('title',{},text));let show=()=>$('sales-detail').textContent=text;bar.addEventListener('click',show);bar.addEventListener('focus',show);s.append(bar)});if(i%3===0||i===11)s.append(svg('text',{x,y:250,fill:'#adc3b8','font-size':11,'text-anchor':'middle'},m.month))});$('sales-chart').replaceChildren(s);$('sales-detail').textContent='Tap a bar for exact amounts · '+D.currency}
$('snapshot').textContent='Saved records through '+D.today+' · '+D.currency;$('stock-value').textContent=money(D.items.reduce((n,i)=>n+i.value,0));$('sales').textContent=money(D.months.at(-1).revenue);$('collect').textContent=money(D.bills.reduce((n,b)=>n+(b.direction==='Receive'?Math.max(0,b.balance):Math.max(0,-b.balance)),0));$('pay').textContent=money(D.bills.reduce((n,b)=>n+(b.direction==='Pay'?Math.max(0,b.balance):Math.max(0,-b.balance)),0));$('search').addEventListener('input',inventory);$('kind').addEventListener('change',inventory);$('age-marker').addEventListener('input',batches);inventory();batches();bills();graph();
</script></body></html>'''
