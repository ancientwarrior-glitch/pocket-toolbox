"""Phone forms for common ledger actions. Calculations stay in engine.py."""
from contextlib import closing
from datetime import date
import json
from engine import Finance


def form_state(finance, mode):
    accounts=[dict(r) for r in finance.rows('SELECT id,scope,name FROM accounts ORDER BY scope,name')]
    categories=[dict(r) for r in finance.rows('SELECT * FROM categories ORDER BY scope,kind,name')]
    items=[]
    for row in finance.rows('SELECT * FROM items ORDER BY kind,name'):
        item=dict(row);item['quantity']=str(finance.stock(row['id'])[0]);items.append(item)
    goals=[dict(r) for r in finance.rows('SELECT * FROM envelopes ORDER BY scope,name')]
    invoices=[]
    for row in finance.rows('SELECT * FROM invoices WHERE void=0 ORDER BY day DESC,id DESC'):
        balance=finance.invoice_balance(row['id'])
        if balance:
            item=dict(row);item['balance']=balance;invoices.append(item)
    return dict(mode=mode,currency=finance.base,today=str(date.today()),accounts=accounts,
                categories=categories,items=items,goals=goals,invoices=invoices)


def render_forms(state):
    encoded=json.dumps(state,ensure_ascii=False).replace('<','\\u003c').replace('>','\\u003e').replace('&','\\u0026')
    return FORMS.replace('__FORM_DATA__',encoded)


def render_view(path, mode):
    from charts import dashboard_data, render
    from business_board import board_data, render_board
    with closing(Finance(path)) as finance:
        html=render(dashboard_data(finance)) if mode=='finance' else render_board(board_data(finance))
        controls=render_forms(form_state(finance,mode))
    return html.replace('</main>',controls+'</main>',1).replace('<footer>Read-only snapshot.', '<footer>Report snapshot. Use the forms below to add records and refresh.').replace('<footer>Read-only Finance snapshot.', '<footer>Finance reports with entry forms below.')


def open_view(finance, mode, home=None, opener=None, pause=input):
    from pathlib import Path
    from board_actions import BoardActions
    from charts import serve
    actions=BoardActions(home or Path.home(),finance.path)
    serve(lambda:render_view(finance.path,mode),opener=opener,pause=pause,api=actions)


FORMS=r'''<style>
.ledger-editor{margin-top:30px;padding-top:24px;border-top:1px solid #52607b}.ledger-editor .forms-grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}.ledger-editor section{margin:0;min-width:0}.ledger-editor label{display:block;margin:14px 0;color:#c3cedd;font-size:14px}.ledger-editor input,.ledger-editor select{display:block;width:100%;background:#101a29;color:#f2f6ff;border:1px solid #52607b;border-radius:8px;padding:11px;min-height:46px;margin-top:5px;font:inherit}.ledger-editor button{background:#384c71;color:white;border:1px solid #a3bbeb;border-radius:9px;padding:11px 18px;font:inherit;min-height:46px;cursor:pointer;margin:8px 5px 8px 0}.ledger-editor button:disabled{opacity:.5}.ledger-editor details>summary{font-size:18px;cursor:pointer;min-height:44px;padding:8px 0}.ledger-editor small{display:block;color:#b2bed3}.ledger-editor .ingredient{border-top:1px solid #52607b;margin-top:12px;padding-top:8px}.ledger-editor #ledger-status{display:none;position:sticky;bottom:12px;background:#26334d;border:1px solid #adcaff;border-radius:10px;padding:14px;z-index:4}.ledger-editor .review{border-left:3px solid #adcaff;padding:12px;white-space:pre-wrap;overflow-wrap:anywhere}#ledger-forms fieldset{border:0;padding:0;margin:0}@media(max-width:700px){.ledger-editor .forms-grid{grid-template-columns:1fr}}
</style><div class="ledger-editor"><h2>Add & update records</h2><p>Amounts use your base currency. Open a form, review the entry, then save. Reports refresh after saving.</p><div class="forms-grid" id="ledger-forms"></div><button type="button" id="ledger-refresh">Refresh saved records</button><p id="ledger-status" role="status" aria-live="polite"></p></div>
<script type="application/json" id="ledger-data">__FORM_DATA__</script><script>
(()=>{'use strict';const D=JSON.parse(document.getElementById('ledger-data').textContent),box=document.getElementById('ledger-forms'),status=document.getElementById('ledger-status');let busy=false;
const currency=D.currency,today=D.today,business=D.accounts.filter(a=>a.scope==='Business'),money=n=>new Intl.NumberFormat(undefined,{minimumFractionDigits:2,maximumFractionDigits:2}).format(n/100)+' '+currency;
function node(tag,text){let n=document.createElement(tag);if(text!==undefined)n.textContent=text;return n}
function message(text){status.style.display='block';status.textContent=text}
function text(name,label,value='',type='text',required=true){return{name,label,value,type,required}}
function select(name,label,options,numeric=false,optional=false){return{name,label,options,numeric,optional,type:'select'}}
const options=(rows,label)=>rows.map(r=>({value:r.id,label:label(r)})),accountOptions=rows=>options(rows,a=>a.scope+' · '+a.name),itemOptions=kind=>options(D.items.filter(i=>!kind||i.kind===kind),i=>i.name+' · '+i.quantity+' '+i.unit+' on hand'),account=()=>select('account','Payment account',accountOptions(business),true,true),date=()=>text('day','Date',today,'date'),amount=(name,label,value='')=>text(name,label+' · '+currency,value),qty=(name='quantity',label='Quantity · g / ml / each; kg / l accepted')=>text(name,label),party=()=>text('party','Customer / supplier / party'),paid=()=>amount('paid','Paid now (0 = on credit)','0');
const specs=[];
if(D.mode==='finance'){
 specs.push({action:'cash-add',title:'Income or expense',note:'Simple cash movements only. Stock invoices, debt payments, transfers and trades belong in their own menus to avoid counting money twice.',fields:[select('account','Account',accountOptions(D.accounts),true),select('kind','Type',[{value:'Expense',label:'Expense'},{value:'Income',label:'Income'}]),select('category','Category',[],true,true),amount('amount','Amount'),date(),text('description','Description')],cash:true});
 specs.push({action:'budget-set',title:'Set a monthly expense budget',note:'This sets or replaces the planned amount for the selected category and month. It does not move cash.',fields:[text('month','Month',today.slice(0,7),'month'),select('category','Expense category',options(D.categories.filter(c=>c.kind==='Expense'),c=>c.scope+' · '+c.name),true),amount('amount','Planned amount')]});
 specs.push({action:'goal-add',title:'Create a savings / reinvestment goal',note:'A planning target, without moving money between accounts.',fields:[select('scope','Scope',[{value:'Personal',label:'Personal'},{value:'Business',label:'Business'}]),text('name','Goal name'),amount('target','Target'),text('due','Target date',today,'date'),amount('monthly','Planned monthly contribution','0')]});
 specs.push({action:'goal-allocate',title:'Reserve money for a goal',note:'Adds to an earmark. It does not move cash. Use a negative amount to reduce the selected earmark.',fields:[select('goal','Goal',options(D.goals,g=>g.scope+' · '+g.name+' · reserved '+money(g.allocated)+' / committed '+money(g.committed)),true),amount('amount','Amount to add / subtract'),select('committed','Earmark type',[{value:'false',label:'Reserved'},{value:'true',label:'Committed'}])]});
 specs.push({action:'price-set',title:'Update a saved asset price',note:'Manual dated valuation, shared by all holdings of this asset. Replaces the saved price for that asset/date. FX means base-currency units per one quote-currency unit; use 1 when the quote is your base currency. This does not place a trade.',fields:[text('asset','Asset ticker, e.g. BTC'),text('price','Price per asset in quote currency'),text('quote','Quote currency',currency),text('fx','Base currency per 1 quote currency','1'),date()]});
}
if(D.mode==='business'){
 specs.push({action:'item-add',title:'Create a material or product',note:'Define an ingredient, packaging item or finished product before adding stock. Choose each for individually counted bottles or bars.',fields:[text('name','Item name'),select('kind','Item type',[{value:'Material',label:'Material / packaging'},{value:'Product',label:'Finished product'}]),select('unit','Base unit',[{value:'g',label:'Grams (g)'},{value:'ml',label:'Millilitres (ml)'},{value:'each',label:'Each'}])]});
 specs.push({action:'stock-opening',title:'Stock you already own',note:'First stock event only. Records existing quantity and cost without a payment. Do not use for a new purchase.',fields:[select('item','Item',itemOptions(),true),qty(),amount('total','Total recorded cost (0 if zero value)','0'),date(),text('description','Opening stock note','Existing stock')]});
 specs.push({action:'stock-receive',title:'Receive a material purchase',note:'Adds stock and a supplier invoice. Paid now creates its linked cash payment; do not enter it again as an expense.',fields:[select('item','Material / packaging',itemOptions('Material'),true),qty(),amount('total','Total purchase cost'),party(),paid(),account(),date()]});
 specs.push({action:'batch-produce',title:'Record a production batch',note:'Consumes materials and adds finished stock with saved material, labor and overhead costs. Enter actual output; this is not a cure/readiness decision.',fields:[text('name','Batch name'),select('product','Finished product',itemOptions('Product'),true),qty('quantity','Output quantity'),amount('labor','Allocated labor cost','0'),amount('overhead','Allocated overhead cost','0'),date()],ingredients:true});
 specs.push({action:'product-sale',title:'Record a product sale',note:'Removes finished stock and creates a sales invoice. Paid now creates the linked collection; do not record it again as cash income.',fields:[select('item','Finished product',itemOptions('Product'),true),qty(),amount('total','Total sale amount'),party(),paid(),account(),date()]});
}
specs.push({action:'invoice-payment',title:'Pay / collect a bill or refund',note:'Payment settles a positive bill balance. Refund settles a credit after a return or overpayment. Both affect the linked invoice and cash account.',fields:[select('invoice','Open bill / credit',options(D.invoices.filter(i=>D.mode!=='business'||i.scope==='Business'),i=>'#'+i.id+' · '+i.scope+' · '+i.party+' · '+i.kind+' · '+(i.balance<0?'credit ':i.direction==='Receive'?'collect ':'pay ')+money(Math.abs(i.balance))),true),select('mode','Movement',[{value:'Payment',label:'Payment / collection'},{value:'Refund',label:'Refund a credit balance'}]),select('account','Cash account',accountOptions(D.mode==='business'?business:D.accounts),true),amount('amount','Amount'),date()],payment:true});
for(const spec of specs){let section=node('section'),details=node('details'),summary=node('summary',spec.title),note=node('p',spec.note),form=node('form'),fields=node('fieldset'),controls={},ingredientRows=[];details.append(summary,note);section.append(details);details.append(form);form.append(fields);box.append(section);
 for(let field of spec.fields){let label=node('label',field.label),input;if(field.type==='select'){input=node('select');if(field.optional)input.add(new Option('None / not paid now',''));for(let o of field.options)input.add(new Option(o.label,String(o.value)));input.required=!field.optional}else{input=node('input');input.type=field.type;input.value=field.value;input.required=field.required;input.maxLength=field.name==='description'?1000:field.name==='name'||field.name==='party'?500:60;if(['amount','total','paid','target','monthly','labor','overhead'].includes(field.name))input.inputMode='decimal'}input.name=field.name;controls[field.name]=input;label.append(input);fields.append(label)}
 function cashCategories(){let a=D.accounts.find(a=>String(a.id)===controls.account.value);controls.category.replaceChildren(new Option('Uncategorized',''));for(let c of D.categories.filter(c=>a&&c.scope===a.scope&&c.kind===controls.kind.value))controls.category.add(new Option(c.name,String(c.id)))}
 if(spec.cash){controls.account.addEventListener('change',cashCategories);controls.kind.addEventListener('change',cashCategories);cashCategories()}
 if(spec.payment){let update=()=>{let invoice=D.invoices.find(i=>String(i.id)===controls.invoice.value),old=controls.account.value;controls.account.replaceChildren();for(let a of D.accounts.filter(a=>invoice&&a.scope===invoice.scope))controls.account.add(new Option(a.name,String(a.id)));if([...controls.account.options].some(o=>o.value===old))controls.account.value=old;if(invoice)controls.mode.value=invoice.balance<0?'Refund':'Payment'};controls.invoice.addEventListener('change',update);update()}
 if(spec.ingredients){let group=node('div'),add=node('button','Add material');add.type='button';fields.append(group,add);function addRow(){let row=node('div'),label=node('label','Material'),item=node('select'),quantity=node('input'),remove=node('button','Remove');row.className='ingredient';item.required=true;for(let option of itemOptions('Material'))item.add(new Option(option.label,String(option.value)));label.append(item);let qlabel=node('label','Quantity consumed · base unit or kg / l');quantity.required=true;quantity.placeholder='e.g. 500 g';qlabel.append(quantity);remove.type='button';let record={row,item,quantity};remove.addEventListener('click',()=>{row.remove();ingredientRows=ingredientRows.filter(r=>r!==record)});row.append(label,qlabel,remove);group.append(row);ingredientRows.push(record)}add.addEventListener('click',addRow);addRow()}
 let review=node('div'),reviewButton=node('button','Review entry'),saveButton=node('button','Save entry'),editButton=node('button','Change details');review.className='review';review.hidden=true;saveButton.type='button';editButton.type='button';saveButton.hidden=editButton.hidden=true;fields.append(reviewButton);form.append(review,saveButton,editButton);let prepared=null,pending=null;
 const data=()=>{let payload={action:spec.action};for(let f of spec.fields){let value=controls[f.name].value;payload[f.name]=f.numeric?(value?Number(value):null):f.name==='committed'?value==='true':value}if(spec.ingredients)payload.ingredients=ingredientRows.map(r=>({item:Number(r.item.value),quantity:r.quantity.value}));return payload};
 form.addEventListener('submit',event=>{event.preventDefault();if(busy)return;if(spec.ingredients&&!ingredientRows.length){message('Add at least one material.');return}prepared=data();let lines=[spec.title];for(let f of spec.fields){let control=controls[f.name];lines.push(f.label+': '+(control.tagName==='SELECT'?control.selectedOptions[0]?.textContent||'None':control.value))}if(spec.ingredients)for(let r of ingredientRows)lines.push('Material: '+(r.item.selectedOptions[0]?.textContent||'')+' · '+r.quantity.value);review.textContent=lines.join('\n');review.hidden=false;fields.disabled=true;saveButton.hidden=editButton.hidden=false;saveButton.focus()});
 editButton.addEventListener('click',()=>{fields.disabled=false;review.hidden=true;saveButton.hidden=editButton.hidden=true;prepared=null});
 saveButton.addEventListener('click',async()=>{if(busy||!prepared)return;let signature=JSON.stringify(prepared);if(!pending||pending.signature!==signature){let request_id=crypto.randomUUID?crypto.randomUUID():Array.from(crypto.getRandomValues(new Uint8Array(20)),n=>n.toString(16).padStart(2,'0')).join('');pending={signature,payload:{...prepared,request_id}}}busy=true;document.querySelectorAll('.ledger-editor button').forEach(b=>b.disabled=true);message('Saving…');let root=location.pathname.replace(/\/$/,'').replace(/\/(finance|business)$/,'');try{let response=await fetch(root+'/api',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(pending.payload)}),result=await response.json();if(!response.ok||!result.ok)throw Error(result.message||'Could not save.');location.reload()}catch(error){message(error.message+' Reopen the board in Termux if the session ended.');busy=false;document.querySelectorAll('.ledger-editor button').forEach(b=>b.disabled=false)}});
}
document.getElementById('ledger-refresh').addEventListener('click',()=>location.reload());
})();</script>'''
