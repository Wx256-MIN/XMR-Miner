#!/usr/bin/env python3
import json, os, subprocess, threading, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API="http://127.0.0.1:8080"; ROOT="/dashboard"; CONFIG="/data/config.json"; MINER="/opt/xmrig"
miner_lock=threading.Lock(); miner_process=None

def load_config():
    try:
        with open(CONFIG,encoding="utf-8") as f: return json.load(f)
    except (FileNotFoundError,json.JSONDecodeError): return {}

def save_config(cfg):
    os.makedirs("/data",exist_ok=True); tmp=CONFIG+".tmp"
    with open(tmp,"w",encoding="utf-8") as f: json.dump(cfg,f,indent=2)
    os.chmod(tmp,0o600); os.replace(tmp,CONFIG)

def miner_running(): return miner_process is not None and miner_process.poll() is None

def stop_miner():
    global miner_process
    with miner_lock:
        if miner_process and miner_process.poll() is None:
            miner_process.terminate()
            try: miner_process.wait(timeout=15)
            except subprocess.TimeoutExpired: miner_process.kill(); miner_process.wait(timeout=5)
        miner_process=None

def start_miner():
    global miner_process
    cfg=load_config()
    if not cfg.get("pool") or not cfg.get("wallet"): return False,"Pool URL and wallet address are required"
    stop_miner()
    args=[MINER,"--url="+cfg["pool"],"--user="+cfg["wallet"],"--pass="+cfg.get("worker","umbrel"),
          "--donate-level="+str(cfg.get("donate_level",1)),"--http-host=127.0.0.1","--http-port=8080","--print-time=60"]
    threads=int(cfg.get("threads",0))
    if threads>0: args.append("--threads="+str(threads))
    with miner_lock: miner_process=subprocess.Popen(args,cwd="/data")
    return True,"Mining started"

class Handler(BaseHTTPRequestHandler):
    def send(self,code,ctype,data):
        self.send_response(code); self.send_header("Content-Type",ctype); self.send_header("Cache-Control","no-store"); self.end_headers(); self.wfile.write(data)
    def json_response(self,code,obj): self.send(code,"application/json; charset=utf-8",json.dumps(obj).encode())
    def do_GET(self):
        if self.path in ("/","/index.html"):
            with open(ROOT+"/index.html","rb") as f: self.send(200,"text/html; charset=utf-8",f.read())
            return
        if self.path=="/favicon.svg":
            with open(ROOT+"/favicon.svg","rb") as f: self.send(200,"image/svg+xml",f.read())
            return
        if self.path=="/api/config":
            cfg=load_config(); public=cfg.copy()
            if public.get("wallet"): public["wallet"]=public["wallet"][:8]+"…"+public["wallet"][-6:]
            self.json_response(200,{"configured":bool(cfg.get("pool") and cfg.get("wallet")),"config":public,"running":miner_running()}); return
        if self.path.startswith("/2/") or self.path.startswith("/1/"):
            try:
                with urllib.request.urlopen(API+self.path,timeout=5) as r: data=r.read()
                self.send(200,"application/json",data)
            except Exception as e: self.send(503,"application/json",json.dumps({"error":str(e)}).encode())
            return
        self.send(404,"text/plain; charset=utf-8",b"Not found")
    def do_POST(self):
        if self.path=="/api/stop":
            stop_miner(); self.json_response(200,{"ok":True,"message":"Mining stopped"}); return
        if self.path=="/api/start":
            ok,msg=start_miner(); self.json_response(200 if ok else 400,{"ok":ok,"message":msg}); return
        if self.path!="/api/config": self.send(404,"text/plain; charset=utf-8",b"Not found"); return
        try:
            length=int(self.headers.get("Content-Length","0")); body=json.loads(self.rfile.read(length))
            pool=str(body.get("pool","")).strip(); wallet=str(body.get("wallet","")).strip()
            worker=str(body.get("worker","umbrel")).strip() or "umbrel"; threads=int(body.get("threads",0)); donate=int(body.get("donate_level",1))
            if not pool or not wallet: raise ValueError("Pool URL and wallet address are required")
            if threads<0 or donate<0: raise ValueError("Threads and donation level cannot be negative")
            save_config({"pool":pool,"wallet":wallet,"worker":worker,"threads":threads,"donate_level":donate})
            ok,msg=start_miner(); self.json_response(200 if ok else 500,{"ok":ok,"message":msg})
        except (ValueError,TypeError,json.JSONDecodeError) as e: self.json_response(400,{"ok":False,"message":str(e)})
    def log_message(self,*args): pass

ThreadingHTTPServer(("0.0.0.0",80),Handler).serve_forever()
