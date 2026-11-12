#!/usr/bin/env python3
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
import sys as _theme_sys
from pathlib import Path as _ThemePath
from theme_loader import load_css as _load_simple_css
"""Card-based Wi-Fi and Bluetooth controls using the established backends."""
import concurrent.futures,json,os,subprocess,sys
from pathlib import Path
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parents[1]/'sound/scripts'))
from panel import box,label,install_navigation,HINT
from navigation import install_dialog_navigation
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib

def backend(mode,action='--status',*args):
    path=HERE/('bluetooth_backend.py' if mode=='bt' else 'network_backend.py')
    result=subprocess.run([sys.executable,str(path),action,*args],capture_output=True,text=True,timeout=110 if action=='--connect' else 40)
    if result.returncode:raise RuntimeError(result.stderr.strip() or 'Device action failed')
    return json.loads(result.stdout) if action=='--status' else None

class Connectivity(Gtk.Application):
    def __init__(self,mode):
        super().__init__(application_id='com.go7.SimpleBluetooth' if mode=='bt' else 'com.go7.SimpleNetwork')
        self.mode=mode;self.window=None;self.closed=False;self.busy=False;self.signature=None;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.connect('activate',self.activate)
    def activate(self,*_):
        if self.window:self.window.present();return
        self.window=Gtk.ApplicationWindow(application=self,title='Bluetooth' if self.mode=='bt' else 'Network');self.window.set_decorated(False);self.window.add_css_class('simple-sound')
        display=Gdk.Display.get_default();rect=display.get_monitors().get_item(0).get_geometry();self.window.set_default_size(min(800,rect.width-64),min(640,rect.height-80))
        css=Gtk.CssProvider();_load_simple_css(css,str(_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/dashboard/info.css'));Gtk.StyleContext.add_provider_for_display(display,css,Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        body=box(spacing=14);body.add_css_class('sound-body');self.window.set_child(body)
        head=box(False);name=label('Bluetooth' if self.mode=='bt' else 'Network','sound-title');name.set_hexpand(True);head.append(name)
        body.append(head)
        toolbar=box(False);self.power=self.button('Power',lambda:self.refresh('--toggle'));toolbar.append(self.power)
        self.scan=self.button('Scan',lambda:self.refresh('--scan'));toolbar.append(self.scan)
        toolbar.append(self.button('Refresh',self.refresh))
        if self.mode=='bt':toolbar.append(self.button('Adapter',self.adapters))
        else:toolbar.append(self.button('Advanced',self.advanced))
        if self.mode=='bt':toolbar.append(self.button('Repair audio',lambda:self.refresh('repair')))
        else:toolbar.append(self.button('Internet info',lambda:self.refresh('internet')))
        body.append(toolbar);self.toolbar=toolbar
        self.status=label('Reading devices…','sound-hint');body.append(self.status)
        self.error=label('','sound-error');self.error.set_visible(False);body.append(self.error)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER,vexpand=True);self.cards=box(spacing=12);scroll.set_child(self.cards);body.append(scroll)
        body.append(label(HINT,'sound-hint'))
        install_navigation(self.window,self.refresh,header=self.power)
        keys=Gtk.EventControllerKey();keys.connect('key-pressed',self.key);self.window.add_controller(keys);self.window.connect('close-request',self.close)
        self.window.present();self.refresh();self.timer=GLib.timeout_add_seconds(4,self.poll)
    def button(self,text,action):
        b=Gtk.Button(label=text);b.connect('clicked',lambda *_:action());return b
    def key(self,controller,key,code,state):
        if self.window._vim_navigation.keys.matches("cancel",key,state):self.window.close();return True
        return False
    def close(self,*_):
        self.closed=True;GLib.source_remove(self.timer);self.pool.shutdown(wait=False,cancel_futures=True);return False
    def poll(self):
        if not self.busy:self.refresh()
        return not self.closed
    def adapters(self):
        win=Gtk.Window(title='Bluetooth adapter',transient_for=self.window,modal=True)
        win.set_default_size(480,240);win.add_css_class('simple-sound')
        body=box(spacing=12);body.add_css_class('sound-body');win.set_child(body)
        body.append(label('Choose Bluetooth adapter','sound-title'))
        body.append(label('Selection is saved for this computer. Use Power to turn the selected adapter on.','sound-hint'))
        items=getattr(self,'data',{}).get('adapters',[])
        def select(address):
            win.close();self.refresh('--select-adapter',address)
        for item in items:
            text=item['name']+' · '+item['address']+(' · selected' if item['selected'] else '')
            button=self.button(text,lambda address=item['address']:select(address))
            button.set_sensitive(not item['selected']);body.append(button)
        if not items:body.append(label('No Bluetooth adapters detected.','sound-hint'))
        body.append(self.button('Close',win.close));install_dialog_navigation(win);win.present()
    def forget(self,device):
        dialog=Gtk.MessageDialog(transient_for=self.window,modal=True,message_type=Gtk.MessageType.QUESTION,
                                 buttons=Gtk.ButtonsType.NONE,text='Forget '+device['name']+'?',
                                 secondary_text='This removes the saved pairing. You will need to pair this device again.')
        dialog.add_button('Cancel',Gtk.ResponseType.CANCEL);dialog.add_button('Forget device',Gtk.ResponseType.ACCEPT)
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        def response(dialog,value):
            dialog.destroy()
            if value==Gtk.ResponseType.ACCEPT:self.refresh('--forget',device['mac'])
        dialog.connect('response',response);install_dialog_navigation(dialog);dialog.present()
    def advanced(self):
        if getattr(self,'advanced_process',None) is not None:return
        try:
            self.advanced_process=subprocess.Popen(['simple-network-advanced',self.mode],start_new_session=True)
        except OSError as error:
            self.error.set_text(str(error));self.error.set_visible(True);return
        GLib.timeout_add(250,self.advanced_finished)
    def advanced_finished(self):
        process=self.advanced_process
        if process.poll() is None:return True
        self.advanced_process=None
        if self.closed:return False
        self.window.present();self.refresh()
        # Explicit compositor focus also works without a Wayland activation token.
        try:
            clients=json.loads(subprocess.check_output(['mmsg','get','all-clients'],text=True,timeout=2))['clients']
            target=next((c for c in clients if c['appid']==self.get_application_id()),None)
            if target:subprocess.run(['mmsg','dispatch','focusid',f"client,{target['id']}"],capture_output=True,timeout=2)
        except (OSError,ValueError,KeyError,subprocess.SubprocessError):pass
        return False
    def refresh(self,action='--status',*args):
        if self.closed:return
        if self.busy:
            if action!='--status':
                self.toolbar.set_sensitive(False);self.cards.set_sensitive(False)
                GLib.timeout_add(100,lambda: self.refresh(action,*args) or False)
            return
        self.busy=True
        if action!='--status':self.toolbar.set_sensitive(False);self.cards.set_sensitive(False);self.status.set_text('Scanning…' if action=='--scan' else 'Working…')
        def work():
            error=None;info=None
            try:
                if action=='repair':
                    repaired=subprocess.run([str('bluetooth-audio-repair')],capture_output=True,text=True,timeout=100)
                    if repaired.returncode:
                        detail=next((line for line in reversed(repaired.stdout.splitlines()) if line.startswith('Repair failed:')),None)
                        raise RuntimeError(detail or repaired.stderr.strip() or 'Bluetooth repair failed without an explanation.')
                elif action=='internet':
                    r=subprocess.run([sys.executable,str(HERE/'internet_status.py')],check=True,capture_output=True,text=True,timeout=25);info=json.loads(r.stdout)
                elif action!='--status':backend(self.mode,action,*args)
            except Exception as e:error=str(e)
            try:return backend(self.mode),error,info
            except Exception as e:return None,error or str(e),info
        f=self.pool.submit(work);f.add_done_callback(lambda f:GLib.idle_add(self.received,f.result()) if not f.cancelled() else None)
    def received(self,result):
        if self.closed:return False
        self.busy=False;self.toolbar.set_sensitive(True);self.cards.set_sensitive(True);data,error,info=result
        self.error.set_visible(bool(error));self.error.set_text(error or '')
        if info:self.show_info(info)
        if data is None:self.status.set_text('Devices unavailable');return False
        self.data=data
        on=data.get('power')=='on';self.power.set_label(('Bluetooth' if self.mode=='bt' else 'Wi-Fi')+(' on' if on else ' off'))
        self.power.set_sensitive(bool(data.get('adapterPath')) if self.mode=='bt' else data.get('wifiAvailable',True));self.scan.set_sensitive(on and self.power.get_sensitive())
        self.status.set_text((data.get('adapterName','Bluetooth') if self.mode=='bt' else 'Wi-Fi and Ethernet')+' · refreshed just now')
        signature=json.dumps(data,sort_keys=True)
        if signature==self.signature:return False
        self.signature=signature
        while self.cards.get_first_child():self.cards.remove(self.cards.get_first_child())
        connected=data.get('connected',[]) if self.mode=='bt' else ([data['connected']] if data.get('connected') else [])
        if self.mode!='bt':connected+= [d for d in data.get('wired',[]) if not any(c['iface']==d['iface'] for c in connected)]
        devices=[(True,d) for d in connected]+[(False,d) for d in data.get('devices' if self.mode=='bt' else 'networks',[])]
        for active,d in devices:
            card=box();card.add_css_class('sound-card');head=box(False)
            icon=Gtk.Image.new_from_icon_name(('audio-headphones-symbolic' if d.get('profile') else 'bluetooth-symbolic') if self.mode=='bt' else ('network-wired-symbolic' if d.get('kind')=='ethernet' else 'network-wireless-symbolic'));icon.add_css_class('sound-icon');head.append(icon)
            name=label(d.get('name',d.get('ssid','Device')));name.set_hexpand(True);head.append(name)
            args=[d['mac']] if self.mode=='bt' else ([d['iface']] if active else [d['ssid'],d['iface']])
            action='--disconnect' if active else '--connect'
            connect=self.button('Disconnect' if active else d.get('action','Connect'),lambda a=action,args=args:self.refresh(a,*args))
            connect.set_sensitive(active or not d.get('blocked',False));head.append(connect);card.append(head)
            parts=['Connected' if active else d.get('action','Available')]
            if self.mode=='bt':
                parts.append(d['mac'])
                parts.extend(name for key,name in [('paired','Paired'),('trusted','Trusted'),('blocked','Blocked')] if d.get(key))
                if d.get('battery','?')!='?':parts.append('Battery '+d['battery']+'%')
                if d.get('profile'):parts.append(d['profile'])
            else:
                parts.extend([d['iface'],d.get('security','')])
                if d.get('kind')!='ethernet':parts.append(str(d.get('signal',0))+'% signal')
                if d.get('ip'):parts.append(d['ip'])
                if d.get('freq'):parts.append(d['freq'])
            card.append(label(' · '.join(parts),'sound-hint'))
            if self.mode=='bt':
                controls=box(False)
                for text,action in [('Untrust' if d.get('trusted') else 'Trust','--untrust' if d.get('trusted') else '--trust'),
                                    ('Unblock' if d.get('blocked') else 'Block','--unblock' if d.get('blocked') else '--block')]:
                    controls.append(self.button(text,lambda a=action,mac=d['mac']:self.refresh(a,mac)))
                controls.append(self.button('Forget device',lambda device=d:self.forget(device)))
                card.append(controls)
            self.cards.append(card)
        if not devices:self.cards.append(label(data.get('error') or ('Scan to discover devices.' if on else 'Turn on the radio to discover devices.'),'sound-hint'))
        return False
    def show_info(self,info):
        from info_panel import InfoWindow
        cards=[{'title':title,'value':str(info.get(key) or 'Unavailable')} for key,title in [('state','Internet'),('ip','Public IP'),('location','Location'),('isp','Provider'),('ping','Latency')]]
        win=InfoWindow(self,'Internet information',cards)
        win.set_transient_for(self.window)
        win.present()

def pairing_prompt(message,confirm):
    app=Gtk.Application(application_id='com.go7.SimplePairing');answer=[None]
    def activate(app):
        win=Gtk.ApplicationWindow(application=app,title='Bluetooth pairing');win.set_decorated(False);win.add_css_class('simple-sound');win.set_default_size(540,230)
        css=Gtk.CssProvider();_load_simple_css(css,str(_Path(_path_os.environ.get('XDG_CONFIG_HOME',_Path.home()/'.config'))/'simplepicker/dashboard/info.css'));Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,Gtk.STYLE_PROVIDER_PRIORITY_USER+3)
        body=box();body.add_css_class('sound-body');win.set_child(body);body.append(label('Bluetooth pairing','sound-title'));body.append(label(message))
        entry=None
        if not confirm:entry=Gtk.Entry();body.append(entry)
        row=box(False)
        def accept(*_):
            value='yes' if confirm else entry.get_text().strip()
            if value:answer[0]=value;win.close()
        cancel=Gtk.Button(label='Cancel');cancel.connect('clicked',lambda *_:win.close());row.append(cancel)
        ok=Gtk.Button(label='Confirm');ok.connect('clicked',accept);row.append(ok);body.append(row)
        if entry:entry.connect('activate',accept)
        install_dialog_navigation(win);win.present()
    app.connect('activate',activate);app.run([])
    if answer[0] is None:return 1
    if not confirm:print(answer[0])
    return 0

if __name__=='__main__':
    if '--pair-prompt' in sys.argv:raise SystemExit(pairing_prompt(sys.argv[sys.argv.index('--pair-prompt')+1],'--confirm' in sys.argv))
    mode='bt' if 'bt' in sys.argv[1:] else 'wifi'
    if '--check' in sys.argv:print(json.dumps(backend(mode)))
    else:raise SystemExit(Connectivity(mode).run([]))
