#!/usr/bin/env python3
import json, os, urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

API='http://127.0.0.1:8080'
ROOT='/dashboard'

class Handler(BaseHTTPRequestHandler):
    def send(self, code, ctype, data):
        self.send_response(code); self.send_header('Content-Type', ctype); self.send_header('Cache-Control','no-store'); self.end_headers(); self.wfile.write(data)
    def do_GET(self):
        if self.path == '/' or self.path == '/index.html':
            with open(ROOT+'/index.html','rb') as f: self.send(200,'text/html; charset=utf-8',f.read()); return
        if self.path.startswith('/2/') or self.path.startswith('/1/'):
            try:
                with urllib.request.urlopen(API+self.path, timeout=5) as r: data=r.read()
                self.send(200,'application/json',data)
            except Exception as e: self.send(503,'application/json',json.dumps({'error':str(e)}).encode())
            return
        self.send(404,'text/plain; charset=utf-8',b'Not found')
    def log_message(self, *args): pass

ThreadingHTTPServer(('0.0.0.0',80), Handler).serve_forever()
