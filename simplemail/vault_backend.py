import os
"""Simplemail access to the unlocked KeePassXC Applications group; no prompts."""
from contextlib import contextmanager
from pathlib import Path
import subprocess

MARKER=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/credential-backend'
SERVICE='org.freedesktop.secrets'
IFACE='org.freedesktop.Secret'
BASE='/org/freedesktop/secrets'
ERROR='Unlock your Local passwords vault in KeePassXC, then retry. No legacy password was used.'
def enabled():
    return MARKER.exists() and MARKER.read_text().strip()=='keepassxc'

@contextmanager
def connection():
    import dbus
    from dbus.mainloop.glib import DBusGMainLoop
    DBusGMainLoop(set_as_default=True)
    session=None
    try:
        bus=dbus.SessionBus()
        owner=bus.get_name_owner(SERVICE)
        daemon=dbus.Interface(bus.get_object('org.freedesktop.DBus','/org/freedesktop/DBus'),'org.freedesktop.DBus')
        pid=int(daemon.GetConnectionUnixProcessID(owner))
        name=subprocess.check_output(['ps','-p',str(pid),'-o','comm='],text=True).strip()
        if name!='keepassxc':raise ValueError('KeePassXC is not the active Secret Service provider.')
        svc=dbus.Interface(bus.get_object(owner,BASE),IFACE+'.Service')
        _,session=svc.OpenSession('plain',dbus.String('',variant_level=1))
        yield dbus,bus,owner,svc,session
    except dbus.DBusException:
        raise ValueError(ERROR) from None
    finally:
        if session:
            try:dbus.Interface(bus.get_object(owner,session),IFACE+'.Session').Close()
            except dbus.DBusException:pass

def collection(db,bus,owner,svc):
    props=db.Interface(bus.get_object(owner,BASE),'org.freedesktop.DBus.Properties')
    candidates=[]
    for path in props.Get(IFACE+'.Service','Collections'):
        p=db.Interface(bus.get_object(owner,path),'org.freedesktop.DBus.Properties')
        if str(p.Get(IFACE+'.Collection','Label'))=='Local passwords':
            if bool(p.Get(IFACE+'.Collection','Locked')):raise ValueError(ERROR)
            candidates.append(path)
    if len(candidates)!=1:raise ValueError('Open the Local passwords vault and expose its Applications group in KeePassXC.')
    return db.Interface(bus.get_object(owner,candidates[0]),IFACE+'.Collection'),str(candidates[0])

def load():
    with connection() as (db,bus,owner,svc,session):
        _,root=collection(db,bus,owner,svc)
        unlocked,locked=svc.SearchItems({'application':'simplemail'})
        if any(str(x).startswith(root+'/') for x in locked):raise ValueError(ERROR)
        accounts={}
        for path in unlocked:
            if not str(path).startswith(root+'/'):continue
            obj=bus.get_object(owner,path);props=db.Interface(obj,'org.freedesktop.DBus.Properties')
            attrs=props.Get(IFACE+'.Item','Attributes');user=str(attrs.get('account',''))
            if not user:continue
            secret=bytes(db.Interface(obj,IFACE+'.Item').GetSecret(session)[2]).decode()
            if user in accounts and accounts[user]!=secret:raise ValueError('Conflicting Simplemail entries in KeePassXC; resolve the duplicate account before continuing.')
            accounts[user]=secret
        return accounts

def store(updates,overwrite=True):
    if any(not isinstance(k,str) or not isinstance(v,str) or not v for k,v in updates.items()):raise ValueError('Mailbox passwords cannot be empty.')
    with connection() as (db,bus,owner,svc,session):
        coll,root=collection(db,bus,owner,svc)
        for user,secret in updates.items():
            unlocked,locked=svc.SearchItems({'application':'simplemail','account':user})
            if any(str(x).startswith(root+'/') for x in locked):raise ValueError(ERROR)
            paths=[p for p in unlocked if str(p).startswith(root+'/')]
            value=db.Struct((db.ObjectPath(session),db.ByteArray(b''),db.ByteArray(secret.encode()),'text/plain; charset=utf8'),signature='oayays')
            if paths:
                if overwrite:
                    for path in paths:db.Interface(bus.get_object(owner,path),IFACE+'.Item').SetSecret(value)
            else:
                props={IFACE+'.Item.Label':'Simplemail — '+user,IFACE+'.Item.Attributes':db.Dictionary({'application':'simplemail','account':user,'UserName':user},signature='ss')}
                _,prompt=coll.CreateItem(props,value,True)
                complete_prompt(db,bus,owner,prompt)


def complete_prompt(db,bus,owner,path):
    if str(path)=='/':return None
    from gi.repository import GLib
    loop=GLib.MainLoop();result=[]
    obj=db.Interface(bus.get_object(owner,path),IFACE+'.Prompt')
    def completed(dismissed,value):
        result.append((bool(dismissed),value));loop.quit()
    match=obj.connect_to_signal('Completed',completed)
    timer=GLib.timeout_add_seconds(60,lambda:(loop.quit(),False)[1])
    try:
        obj.Prompt('')
        if not result:loop.run()
        if not result or result[0][0]:raise ValueError('KeePassXC did not complete the credential save.')
        return result[0][1]
    finally:
        if result:GLib.source_remove(timer)
        match.remove()
