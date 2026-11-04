#!/usr/bin/env python3
"""Shared JSON entry point. One process/request isolates each adapter's state."""
import os,sys,json,contextlib,io
from pathlib import Path
try:
 name=sys.argv[1]
 if name not in ('simplecontacts','simplecalendar'):raise ValueError('Unknown organizer')
 sys.path.insert(0,os.environ.get('SIMPLECONTACTS_SOURCE' if name=='simplecontacts' else 'SIMPLECALENDAR_SOURCE',str(Path(__file__).resolve().parent.parent/name)))
 import bridge
 request=json.load(sys.stdin)
 with contextlib.redirect_stdout(io.StringIO()):result=bridge.handle(request)
 print(json.dumps({'ok':True,'data':result},ensure_ascii=False))
except Exception as e:print(json.dumps({'ok':False,'error':str(e)},ensure_ascii=False))
