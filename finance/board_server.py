"""Short-lived loopback-only board server with constrained, same-origin writes."""
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
import base64
import hashlib
import json
import re
import secrets
import shutil
import subprocess
import threading
import time

IDLE_SECONDS=15*60
MAX_SECONDS=60*60


def protect_page(html,root,seconds):
    guard=r'''<style>#session-notice{padding:10px 16px;background:#24334b;color:#eef4ff;font:13px system-ui,sans-serif}#session-lock{font:inherit;padding:8px 12px;margin-left:12px;background:#162037;color:white;border:1px solid #afc9ff;border-radius:7px}</style>
<div id="session-notice" role="status">Private session: expires after 15 minutes without loading/saving, or 1 hour total. Leaving this tab hidden for 60 seconds locks it. Unsaved forms are discarded. <button id="session-lock" type="button">Lock now</button></div>
<script>(()=>{'use strict';let deadline=Date.now()+__SECONDS__*1000,hiddenAt=null,locked=false;const root=__ROOT__;
function lock(){if(locked)return;locked=true;document.body.replaceChildren();setTimeout(()=>location.replace('about:blank'),100);fetch(root+'/lock',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}',keepalive:true}).catch(()=>{});}
function check(){if(Date.now()>=deadline||hiddenAt!==null&&Date.now()-hiddenAt>=60000)lock()}
document.getElementById('session-lock').addEventListener('click',lock);
document.addEventListener('visibilitychange',()=>{if(document.hidden){hiddenAt=Date.now();setTimeout(check,60100)}else{check();hiddenAt=null}});
window.addEventListener('pageshow',e=>{if(e.persisted)lock();else check()});setInterval(check,1000);
setInterval(()=>{if(!locked)fetch(root+'/status',{cache:'no-store'}).then(r=>{if(!r.ok)lock()}).catch(lock)},10000);
})();</script>'''.replace('__SECONDS__',str(max(0,seconds))).replace('__ROOT__',json.dumps(root))
    markup,script=guard.split('<script>',1)
    html=html.replace('<body>','<body>'+markup,1).replace('</body>','<script>'+script+'</body>',1)
    def hashes(tag):
        return ["'sha256-"+base64.b64encode(hashlib.sha256(s.encode()).digest()).decode()+"'" for s in re.findall(r'<'+tag+r'\b[^>]*>([\s\S]*?)</'+tag+'>',html)]
    csp="default-src 'none'; script-src "+' '.join(hashes('script'))+"; style-src "+' '.join(hashes('style'))+"; connect-src 'self'; img-src 'none'; font-src 'none'; object-src 'none'; base-uri 'none'; form-action 'none'; frame-ancestors 'none'"
    return html.encode('utf-8'),csp


def serve(html,opener=None,pause=input,pages=None,api=None,idle_seconds=IDLE_SECONDS,max_seconds=MAX_SECONDS):
    if not 0<idle_seconds<=IDLE_SECONDS or not 0<max_seconds<=MAX_SECONDS:raise ValueError('Invalid session duration.')
    token='/'+secrets.token_urlsafe(24);routes={token:html}
    for name,page in (pages or {}).items():
        if not name or any(c not in 'abcdefghijklmnopqrstuvwxyz-' for c in name):raise ValueError('Invalid page name.')
        routes[token+'/'+name]=page
    started=time.monotonic();last=[started];expired=threading.Event();stop=threading.Event();state_lock=threading.Lock()
    def remaining(touch=False):
        with state_lock:
            now=time.monotonic()
            if now-started>=max_seconds or now-last[0]>=idle_seconds:expired.set()
            if expired.is_set():return 0
            if touch:last[0]=now
            return min(max_seconds-(now-started),idle_seconds-(now-last[0]))
    class Handler(BaseHTTPRequestHandler):
        server_version="PocketBoard";sys_version=""
        def origin(self):return f'http://127.0.0.1:{self.server.server_port}'
        def valid(self,write=False):
            if self.headers.get('Host')!=self.origin()[7:] or self.headers.get('Sec-Fetch-Site')=='cross-site':return False
            value=self.headers.get('Origin')
            return value==self.origin() if write else value in (None,self.origin())
        def headers_for(self,mime,csp="default-src 'none'; frame-ancestors 'none'"):
            for key,value in [('Content-Type',mime),('Cache-Control','no-store, max-age=0'),('Pragma','no-cache'),('Referrer-Policy','no-referrer'),('X-Content-Type-Options','nosniff'),('X-Frame-Options','DENY'),('Cross-Origin-Opener-Policy','same-origin'),('Cross-Origin-Resource-Policy','same-origin'),('X-DNS-Prefetch-Control','off'),('Permissions-Policy','camera=(), microphone=(), geolocation=(), usb=(), payment=()'),('Content-Security-Policy',csp)]:self.send_header(key,value)
        def fail(self,status,message):
            payload=json.dumps({'ok':False,'message':message}).encode();self.send_response(status)
            self.headers_for('application/json');self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_GET(self):
            if not self.valid():self.fail(403,'Forbidden.');return
            if self.path==token+'/status':
                seconds=remaining()
                if not seconds:self.fail(410,'Session expired.');return
                payload=json.dumps({'ok':True,'remaining':seconds}).encode();self.send_response(200);self.headers_for('application/json')
                self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload);return
            if self.path not in routes:self.fail(404,'Not found.');return
            if not remaining(touch=True):self.fail(410,'Session expired. Reopen the board in Termux.');return
            try:
                page=routes[self.path];page=page() if callable(page) else page
                payload,csp=protect_page(page,token,remaining())
            except Exception:self.fail(500,'Could not load board. Reopen it in Termux.');return
            self.send_response(200);self.headers_for('text/html; charset=utf-8',csp)
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def do_POST(self):
            if not self.valid(write=True):self.fail(403,'Forbidden.');return
            if self.path not in (token+'/api',token+'/lock') or self.path.endswith('/api') and api is None:self.fail(404,'Not found.');return
            if not remaining():self.fail(410,'Session expired. Reopen it in Termux.');return
            if self.headers.get('Content-Type','').split(';')[0]!='application/json':self.fail(415,'Use JSON.');return
            if self.headers.get('Transfer-Encoding'):self.fail(400,'Unsupported request encoding.');return
            try:
                size=int(self.headers.get('Content-Length','0'))
                if not 0<size<=65536:raise ValueError('Request is too large or empty.')
                body=self.rfile.read(size)
                if len(body)!=size:raise ValueError('Incomplete request.')
                request=json.loads(body)
                if not isinstance(request,dict):raise ValueError('Invalid request.')
                if self.path==token+'/lock':expired.set();result={'ok':True}
                else:
                    if not remaining(touch=True):self.fail(410,'Session expired.');return
                    result=api(request)
            except (ValueError,KeyError,TypeError) as error:self.fail(400,str(error));return
            except Exception:self.fail(500,'Could not save. Check records in Termux before retrying.');return
            payload=json.dumps(result).encode();self.send_response(200);self.headers_for('application/json')
            self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*args):pass
    class Server(ThreadingHTTPServer):
        daemon_threads=True
        def get_request(self):
            sock,address=super().get_request();sock.settimeout(5);return sock,address
        def process_request(self,request,address):
            if not slots.acquire(blocking=False):request.close();return
            try:super().process_request(request,address)
            except BaseException:slots.release();raise
        def process_request_thread(self,request,address):
            try:super().process_request_thread(request,address)
            finally:slots.release()
    slots=threading.BoundedSemaphore(8);server=Server(('127.0.0.1',0),Handler)
    worker=threading.Thread(target=lambda:server.serve_forever(poll_interval=.1),daemon=True);worker.start()
    def monitor():
        while not stop.wait(.1):
            if not remaining():server.shutdown();server.server_close();return
    watcher=threading.Thread(target=monitor,daemon=True);watcher.start()
    url=f'http://127.0.0.1:{server.server_port}{token}'
    try:
        print('Open this private local dashboard:\n'+url)
        if opener:opener(url)
        elif shutil.which('termux-open'):subprocess.run(['termux-open',url],check=False)
        print('Session expires automatically. Keep this screen open; press Enter here to close it now.')
        pause('\nReturn here and press Enter when finished. ')
    finally:
        expired.set();stop.set();server.shutdown();server.server_close();worker.join(timeout=2);watcher.join(timeout=2)
