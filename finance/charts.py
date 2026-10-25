"""Offline SVG dashboard. Serves one random local URL; never binds to the network."""
from datetime import date
from calendar import monthrange
from collections import defaultdict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import secrets
import shutil
import subprocess
import threading

def dashboard_data(finance):
    today=date.today();accounts=[dict(r) for r in finance.rows('SELECT * FROM accounts ORDER BY scope,name')]
    cash=[dict(r) for r in finance.rows('SELECT c.*,a.scope,a.name account_name,k.name category_name,k.kind category_kind FROM cash c JOIN accounts a ON a.id=c.account LEFT JOIN categories k ON k.id=c.category WHERE c.void=0 ORDER BY c.day,c.id')]
    candidates=[r['start'] for r in accounts]+[r['day'] for r in cash]+[r['day'] for r in finance.rows('SELECT day FROM investment_events')]
    earliest=min([s for s in candidates if s<=str(today)]+[str(today)])
    first=date.fromisoformat(earliest).replace(day=1)
    if today.year-first.year>100:first=date(today.year-100,1,1)
    months=[];year,month=first.year,first.month
    while (year,month)<=(today.year,today.month):
        months.append(f'{year:04}-{month:02}')
        year,month=(year+1,1) if month==12 else (year,month+1)
    balances={}
    for account in accounts:
        values=[]
        for key in months:
            year,month=map(int,key.split('-'));end=min(date(year,month,monthrange(year,month)[1]),today)
            values.append(finance.balance(account['id'],str(end)))
        balances[str(account['id'])]=values
    portfolios=[]
    for row in finance.rows('SELECT DISTINCT scope,portfolio FROM positions ORDER BY scope,portfolio'):
        values=[]
        for key in months:
            year,month=map(int,key.split('-'));end=min(date(year,month,monthrange(year,month)[1]),today)
            result=finance.portfolio(row['scope'],row['portfolio'],str(end));values.append(result['value'])
        portfolios.append(dict(scope=row['scope'],name=row['portfolio'],values=values))
    return dict(currency=finance.base,today=str(today),months=months,accounts=accounts,balances=balances,
                cash=cash,portfolios=portfolios,budgets=[dict(r) for r in finance.rows('SELECT b.*,c.name,c.scope,c.kind FROM budgets b JOIN categories c ON c.id=b.category')],
                goals=[dict(r) for r in finance.rows('SELECT * FROM envelopes ORDER BY scope,name')])

def render(data):
    # Escaping '<' prevents user descriptions from closing the inert JSON script.
    serialized=json.dumps(data,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return PAGE.replace('__DATA__',serialized)

def serve(html,opener=None,pause=input,pages=None):
    token='/'+secrets.token_urlsafe(24)
    routes={token:html.encode('utf-8')}
    for name,page in (pages or {}).items():
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz-' for c in name):
            raise ValueError('Invalid dashboard page name.')
        routes[token+'/'+name]=page.encode('utf-8')
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path not in routes:
                self.send_error(404);return
            payload=routes[self.path]
            self.send_response(200)
            self.send_header('Content-Type','text/html; charset=utf-8')
            self.send_header('Cache-Control','no-store')
            self.send_header('X-Content-Type-Options','nosniff')
            self.send_header('Referrer-Policy','no-referrer')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
    url=f'http://127.0.0.1:{server.server_port}{token}'
    try:
        print('Open this local dashboard in your browser:\n'+url)
        if opener:opener(url)
        elif shutil.which('termux-open'):subprocess.run(['termux-open',url],check=False)
        print('Keep this screen open until the browser has loaded. Charts use saved data, not live prices.')
        pause('\nReturn here and press Enter when finished. ')
    finally:server.shutdown();server.server_close();worker.join(timeout=2)

PAGE=r'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pocket Finance · Graphs</title><style>
:root{color-scheme:dark;--bg:#0c141d;--panel:#142130;--line:#2b3b4c;--text:#edf4fa;--muted:#a3b4c5;--green:#72dfbb;--red:#ff9b94;--blue:#80c9ff}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--text);font:16px/1.5 system-ui,sans-serif}main{max-width:1160px;margin:auto;padding:28px 18px 48px}header p{margin:6px 0;color:var(--muted)}h1{font-size:clamp(28px,5vw,42px);letter-spacing:-1px;margin:0}h2{font-size:19px;margin:0 0 4px}small,.muted{color:var(--muted)}.tag{color:var(--green);font-size:13px;letter-spacing:2px;text-transform:uppercase}.controls{display:flex;flex-wrap:wrap;gap:12px;margin:24px 0}label{display:flex;flex:1 1 130px;flex-direction:column;font-size:13px;color:var(--muted);gap:5px}select,button{font:inherit;border:1px solid var(--line);border-radius:9px;background:var(--panel);color:var(--text);padding:11px;min-height:44px}button{cursor:pointer}.cards{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-bottom:16px}.card,section{border:1px solid var(--line);border-radius:16px;background:var(--panel);padding:18px}.card span{display:block;font-size:13px;color:var(--muted)}.card strong{display:block;font-size:clamp(18px,3vw,27px);margin-top:7px;overflow-wrap:anywhere}.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}section.wide{grid-column:1/-1}section p{margin:3px 0 12px;font-size:13px;color:var(--muted)}svg{width:100%;display:block;overflow:visible}.empty{padding:32px 12px;border:1px dashed var(--line);border-radius:10px;color:var(--muted);text-align:center}.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--muted)}.green{color:var(--green)}.red{color:var(--red)}.detail{margin-top:12px;min-height:24px;font-size:14px}.row{margin:18px 0}.row-head{display:flex;justify-content:space-between;gap:12px;overflow-wrap:anywhere}.track{height:11px;background:#26384b;border-radius:8px;overflow:hidden;margin:8px 0}.fill{height:100%;background:var(--green);border-radius:8px}.note{font-size:13px;color:var(--muted);margin-top:22px}footer{margin-top:24px;color:var(--muted);font-size:13px}details{margin-top:12px}table{width:100%;border-collapse:collapse;font-size:13px}td,th{text-align:right;padding:8px 4px;border-bottom:1px solid var(--line)}td:first-child,th:first-child{text-align:left}.table-wrap{overflow:auto}summary{cursor:pointer;padding:8px 0}svg text{font-family:system-ui,sans-serif}svg [tabindex]{cursor:pointer;outline:none}svg [tabindex]:focus{stroke:white;stroke-width:3}@media(max-width:720px){main{padding:22px 12px}.grid{grid-template-columns:1fr}.cards{gap:8px}.card{padding:12px}section{padding:16px}.cards .card strong{font-size:18px}section.wide{grid-column:auto}}
</style></head><body><main><header><div class="tag">Pocket Finance · offline dashboard</div><h1>Your money, in view.</h1><p id="subtitle"></p></header>
<div class="controls"><label>Scope<select id="scope"><option>Personal</option><option>Business</option></select></label><label>Account<select id="account"></select></label><label>Period<select id="range"><option value="3">Last 3 months</option><option value="6">Last 6 months</option><option value="12" selected>Last 12 months</option><option value="all">All saved months</option></select></label></div>
<div class="cards"><div class="card"><span>Recorded cash balance</span><strong id="balance"></strong></div><div class="card"><span>Money in · selected period</span><strong id="incoming" class="green"></strong></div><div class="card"><span>Money out · selected period</span><strong id="outgoing" class="red"></strong></div></div>
<div class="grid"><section><h2>Cash balance over time</h2><p>Month-end snapshots, including opening balances. Tap a point.</p><div id="balance-chart"></div><div class="detail" id="balance-detail"></div></section>
<section><h2>Money in versus money out</h2><p>Transfers, investment movements and balance adjustments are excluded.</p><div class="legend"><span class="green">● Money in</span><span class="red">● Money out</span></div><div id="flow-chart"></div><div class="detail" id="flow-detail"></div></section>
<section><h2>Spending & payments by category</h2><p>Refunds reduce category totals. Debt principal may be included in payments.</p><div id="categories"></div></section>
<section><h2>Portfolio value</h2><p>Monthly holdings valued using saved prices/FX. This is value, not investment return.</p><label>Portfolio<select id="portfolio"></select></label><div id="portfolio-chart"></div><div class="detail" id="portfolio-detail"></div></section>
<section><h2>This month’s expense budgets</h2><p>Planned amounts versus actual categorized payments, net of refunds.</p><div id="budgets"></div></section><section><h2>Savings & reinvestment goals</h2><p>Reserved amounts are planning earmarks; they do not move cash.</p><div id="goals"></div></section></div>
<p class="note" id="warnings"></p><footer>Read-only snapshot. Return to Finance and reopen Graphs after adding records. Your records stay on this device; this dashboard loads no external scripts or prices.</footer></main>
<script type="application/json" id="data">__DATA__</script><script>
'use strict';const D=JSON.parse(document.getElementById('data').textContent),$=id=>document.getElementById(id),NS='http://www.w3.org/2000/svg';
const fmt=n=>n===null?'Unknown':new Intl.NumberFormat(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}).format(n/100)+' '+D.currency;
const short=n=>new Intl.NumberFormat(undefined,{notation:'compact',maximumFractionDigits:1}).format(n/100);
function el(tag,attrs={},text){let e=document.createElementNS(NS,tag);for(let [k,v]of Object.entries(attrs))e.setAttribute(k,v);if(text!==undefined)e.textContent=text;return e}
function empty(id,text){$(id).replaceChildren();let p=document.createElement('div');p.className='empty';p.textContent=text;$(id).append(p)}
function selection(){let scope=$('scope').value,id=$('account').value,count=$('range').value,start=count==='all'?0:Math.max(0,D.months.length-Number(count));return{scope,id,start,months:D.months.slice(start),accounts:D.accounts.filter(a=>a.scope===scope&&(id==='all'||String(a.id)===id))}}
function svgBase(id){$(id).replaceChildren();let s=el('svg',{viewBox:'0 0 520 260',role:'img','aria-label':$(id).parentElement.querySelector('h2').textContent});$(id).append(s);return s}
function line(id,values,labels,detail,color){if(!values.some(v=>v!==null)){empty(id,id==='balance-chart'?'Add a cash account with a known opening balance to see its graph.':'No complete valuation yet. Add a dated price for each held asset.');$(detail).textContent='';return}
 let s=svgBase(id),good=values.filter(v=>v!==null),low=Math.min(0,...good),high=Math.max(0,...good);if(low===high)high=low+100;
 const x=i=>52+(values.length===1?212:i*440/(values.length-1)),y=v=>214-(v-low)*174/(high-low);
 for(let t=0;t<4;t++){let v=low+(high-low)*t/3,yy=y(v);s.append(el('line',{x1:52,x2:492,y1:yy,y2:yy,stroke:'#2b3b4c'}),el('text',{x:44,y:yy+4,fill:'#a3b4c5','font-size':11,'text-anchor':'end'},short(v)))}
 let path='',last=false;values.forEach((v,i)=>{if(v===null){last=false;return}path+=(last?'L':'M')+x(i)+','+y(v)+' ';last=true});s.append(el('path',{d:path,fill:'none',stroke:color,'stroke-width':3,'stroke-linejoin':'round'}));
 values.forEach((v,i)=>{if(v===null)return;let c=el('circle',{cx:x(i),cy:y(v),r:5,fill:color,tabindex:0,'aria-label':labels[i]+': '+fmt(v)});c.append(el('title',{},labels[i]+': '+fmt(v)));let show=()=>$(detail).textContent=labels[i]+' · '+fmt(v);c.addEventListener('click',show);c.addEventListener('focus',show);c.addEventListener('keydown',e=>{if(e.key==='Enter')show()});s.append(c)});
 labels.forEach((v,i)=>{if(i===0||i===labels.length-1||labels.length<=5)s.append(el('text',{x:x(i),y:242,fill:'#a3b4c5','font-size':11,'text-anchor':'middle'},v))});let i=values.findLastIndex(v=>v!==null);$(detail).textContent=labels[i]+' · '+fmt(values[i]);}
function bars(incomes,outcomes,labels){if(!incomes.some(Boolean)&&!outcomes.some(Boolean)){empty('flow-chart','No cash movements in this period yet. Opening balances appear in the balance graph.');$('flow-detail').textContent='';return}
 let s=svgBase('flow-chart'),max=Math.max(...incomes,...outcomes,100),group=440/labels.length,width=Math.min(20,group*.3);for(let t=0;t<4;t++){let v=max*t/3,yy=214-v/max*174;s.append(el('line',{x1:52,x2:492,y1:yy,y2:yy,stroke:'#2b3b4c'}),el('text',{x:44,y:yy+4,fill:'#a3b4c5','font-size':11,'text-anchor':'end'},short(v)))}
 labels.forEach((label,i)=>{let center=52+group*(i+.5);[incomes[i],outcomes[i]].forEach((v,j)=>{let h=v/max*174,r=el('rect',{x:center+(j?2:-width-2),y:214-h,width:width,height:Math.max(h,v?2:0),rx:3,fill:j?'#ff9b94':'#72dfbb',tabindex:0});let text=label+' · In '+fmt(incomes[i])+' · Out '+fmt(outcomes[i]);r.append(el('title',{},text));let show=()=>$('flow-detail').textContent=text;r.addEventListener('click',show);r.addEventListener('focus',show);s.append(r)});if(i===0||i===labels.length-1||labels.length<=5)s.append(el('text',{x:center,y:242,fill:'#a3b4c5','font-size':11,'text-anchor':'middle'},label))});$('flow-detail').textContent='Tap a bar to see its amounts.';}
function progress(id,rows){$(id).replaceChildren();for(let row of rows){let box=document.createElement('div');box.className='row';let head=document.createElement('div');head.className='row-head';let label=document.createElement('span'),value=document.createElement('span');label.textContent=row.name;value.textContent=fmt(row.actual)+' / '+fmt(row.target);head.append(label,value);let track=document.createElement('div');track.className='track';let fill=document.createElement('div');fill.className='fill';fill.style.width=Math.max(0,Math.min(100,row.target?row.actual/row.target*100:0))+'%';if(row.actual>row.target&&row.expense)fill.style.background='#ff9b94';track.append(fill);box.append(head,track);if(row.note){let note=document.createElement('small');note.textContent=row.note;box.append(note)}$(id).append(box)}}
function update(){let v=selection(),ids=new Set(v.accounts.map(a=>a.id)),rows=D.cash.filter(r=>ids.has(r.account)&&r.day<=D.today&&r.day.slice(0,7)>=v.months[0]),operational=rows.filter(r=>!['Transfer','Investment','Adjustment'].includes(r.kind));let known=v.accounts.filter(a=>!a.name.includes('opening balance unknown'));
 let balance=v.months.map((m,i)=>{let vals=known.map(a=>D.balances[a.id][v.start+i]).filter(n=>n!==null);return vals.length?vals.reduce((a,b)=>a+b,0):null});$('balance').textContent=balance.at(-1)===null?'Not established':fmt(balance.at(-1));$('incoming').textContent=fmt(operational.reduce((a,r)=>a+Math.max(0,r.delta),0));$('outgoing').textContent=fmt(operational.reduce((a,r)=>a+Math.max(0,-r.delta),0));line('balance-chart',balance,v.months,'balance-detail','#80c9ff');
 let incomes=v.months.map(m=>operational.filter(r=>r.day.startsWith(m)).reduce((a,r)=>a+Math.max(0,r.delta),0)),outcomes=v.months.map(m=>operational.filter(r=>r.day.startsWith(m)).reduce((a,r)=>a+Math.max(0,-r.delta),0));bars(incomes,outcomes,v.months);
 let categories={};for(let r of operational){if(r.delta<0||r.kind==='Refund'&&r.category_kind==='Expense'){let name=r.category_name||'Uncategorized';categories[name]=(categories[name]||0)-r.delta}}let catrows=Object.entries(categories).filter(([k,n])=>n!==0).sort((a,b)=>b[1]-a[1]);if(!catrows.length)empty('categories','No spending or payments to display yet.');else{let max=Math.max(...catrows.map(r=>Math.abs(r[1])),1);progress('categories',catrows.map(([name,n])=>({name,actual:n,target:max,note:n<0?'Net refund received':''})));for(let head of $('categories').querySelectorAll('.row-head span:last-child'))head.textContent=head.textContent.split(' / ')[0]}
 let month=D.today.slice(0,7),plans=D.budgets.filter(r=>r.scope===v.scope&&r.kind==='Expense'&&r.month===month);if(!plans.length)empty('budgets','Set monthly category plans in Finance → Monthly budgets.');else progress('budgets',plans.map(p=>({name:p.name,target:p.amount,expense:true,actual:D.cash.filter(r=>ids.has(r.account)&&r.category===p.category&&r.day.startsWith(month)&&r.day<=D.today).reduce((a,r)=>a-r.delta,0)})));
 let goals=D.goals.filter(r=>r.scope===v.scope);if(!goals.length)empty('goals','Add a goal in Finance → Savings, investment plans and profit shares.');else progress('goals',goals.map(g=>({name:g.name,target:g.target,actual:g.allocated,note:'Committed '+fmt(g.committed)+' · Due '+g.due})));
 $('warnings').textContent=(v.accounts.length-known.length?'Imported accounts with unknown opening balances are excluded from the balance graph. ':'')+'Cash-flow totals are not profit. Portfolio graphs ignore the cash-account filter and use the selected scope.';updatePortfolio();}
function updatePortfolio(){let v=selection(),available=D.portfolios.filter(p=>p.scope===v.scope),index=$('portfolio').value,p=available[Number(index)];if(!p){empty('portfolio-chart','No portfolio holdings yet. Add positions, holdings and dated prices in Finance.');$('portfolio-detail').textContent='';return}line('portfolio-chart',p.values.slice(v.start),v.months,'portfolio-detail','#c0adff')}
function resetAccounts(){let scope=$('scope').value;$('account').replaceChildren(new Option('All accounts','all'));for(let a of D.accounts.filter(a=>a.scope===scope))$('account').add(new Option(a.name,String(a.id)));$('portfolio').replaceChildren();D.portfolios.filter(p=>p.scope===scope).forEach((p,i)=>$('portfolio').add(new Option(p.name,String(i))));update()}
$('subtitle').textContent='Saved data through '+D.today+' · '+D.currency+' · Tap graph points for exact values';$('scope').addEventListener('change',resetAccounts);$('account').addEventListener('change',update);$('range').addEventListener('change',update);$('portfolio').addEventListener('change',updatePortfolio);resetAccounts();
</script></body></html>'''
