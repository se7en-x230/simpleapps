#!/usr/bin/env python3
"""Import selected FairEmail accounts without changing existing Simplemail accounts.
Format reference: https://github.com/M66B/FairEmail/blob/master/app/src/main/java/eu/faircode/email/FragmentOptionsBackup.java
"""
import argparse,hashlib,json,os,threading
from pathlib import Path
import simplemail as mail

def read_backup(path,password):
    data=Path(path).read_bytes()
    if len(data)>16*1024*1024: raise ValueError('Backup is too large to be a settings export.')
    try:
        if data.lstrip().startswith(b'{'):
            parsed=json.loads(data)
        else:
            if not password: raise ValueError('Enter the FairEmail backup export password.')
            from cryptography.hazmat.primitives.ciphers import Cipher,algorithms,modes
            from cryptography.hazmat.primitives.padding import PKCS7
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM
            if data.startswith(b'___FairEmail___'):
                if data[15]!=1: raise ValueError('Unsupported backup version.')
                salt,iv,ciphertext=data[16:32],data[32:44],data[44:]
                key=hashlib.pbkdf2_hmac('sha512',password.encode(),salt,120000,32)
                plain=AESGCM(key).decrypt(iv,ciphertext,None)
            else:
                salt,iv,ciphertext=data[:16],data[16:32],data[32:]
                key=hashlib.pbkdf2_hmac('sha1',password.encode(),salt,65536,32)
                decryptor=Cipher(algorithms.AES(key),modes.CBC(iv)).decryptor()
                padded=decryptor.update(ciphertext)+decryptor.finalize()
                unpad=PKCS7(128).unpadder();plain=unpad.update(padded)+unpad.finalize()
            parsed=json.loads(plain)
    except ImportError: raise ValueError('Install python-cryptography to read encrypted FairEmail exports.') from None
    except Exception: raise ValueError('Cannot unlock the backup. Check its export password and file.') from None
    if not isinstance(parsed,dict) or not isinstance(parsed.get('accounts'),list):
        raise ValueError('This is not a FairEmail account-settings export.')
    return parsed

def security(entity):
    mode=entity.get('encryption',1 if entity.get('starttls') else 0)
    if mode not in (0,1): raise ValueError('Unencrypted server settings are not supported.')
    return ('ssl','starttls')[mode]

def candidates(data,domains):
    found=[]; notes=[]
    domains={d.lower() for d in domains}
    for item in data['accounts']:
        identities=item.get('identities') or []
        identities=sorted(identities,key=lambda ident:not ident.get('primary',False))
        selected=next((ident for ident in identities if str(ident.get('email','')).rsplit('@',1)[-1].lower() in domains),None)
        if selected is None: continue
        address=selected['email']; label=address
        try:
            if item.get('protocol',1 if item.get('pop') else 0)!=0: raise ValueError('POP account; IMAP is required.')
            if item.get('auth_type',1)!=1 or selected.get('auth_type',1)!=1:
                raise ValueError('Uses app-specific sign-in; enter an app password in Simplemail setup.')
            secret=item.get('password')
            if not isinstance(secret,str) or not secret: raise ValueError('No mailbox password in this backup.')
            if selected.get('password')!=secret: raise ValueError('Different incoming and outgoing passwords; manual setup is required.')
            folders={folder.get('type'):folder.get('name') for folder in item.get('folders',[]) if folder.get('name')}
            colour=item.get('color')
            account=dict(username=address,name=item.get('name') or address,display_name=selected.get('name') or address,
                         imap_host=item['host'],imap_port=item['port'],imap_username=item['user'],imap_security=security(item),
                         smtp_host=selected['host'],smtp_port=selected['port'],smtp_username=selected['user'],smtp_security=security(selected),
                         sent_folder=folders.get('Sent','Sent'),trash_folder=folders.get('Trash','Trash'),
                         color=f'#{colour & 0xffffff:06x}' if isinstance(colour,int) else mail.ACCOUNT_COLORS[len(found)%len(mail.ACCOUNT_COLORS)])
            found.append((mail.setup_account(account),secret))
        except (KeyError,TypeError,ValueError) as error:
            # Do not include arbitrary malformed backup values or credentials.
            notes.append(label+': '+(str(error) if isinstance(error,ValueError) else 'Incomplete account settings.'))
    return found,notes

def import_accounts(data,domains,progress=lambda text:None,cancelled=lambda:False):
    raw,current=mail.setup_config();existing={a['username'].casefold() for a in mail.setup_accounts(current)}
    planned,notes=candidates(data,domains);updates={};next_raw=raw;results=[]
    for account,secret in planned:
        address=account['username']
        if address.casefold() in existing:
            results.append(address+': already configured; kept unchanged.');continue
        if cancelled(): return ['Import cancelled. Nothing saved.']
        progress('Checking '+address+'…')
        try:
            mail.verify_account(account,secret)
            next_raw=mail.account_config_text(next_raw,account)
            updates[address]=secret;existing.add(address.casefold());results.append(address+': checked and ready.')
        except Exception as error:
            results.append(address+': not imported — '+str(error).replace(secret,'[redacted]'))
    if cancelled(): return ['Import cancelled. Nothing saved.']
    if updates:
        mail.commit_setup_config(raw,next_raw,updates)
        results=[r.replace(': checked and ready.',': imported; SMTP and IMAP verified.') for r in results]
    if not planned and not notes:notes=['No accounts matching the selected domains were found.']
    return results+notes

def gui(backup,domains,report=None):
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk,Gio,GLib,Gdk
    mail.desktop_environment()
    app=Gtk.Application(application_id='com.go7.Simplemail.Setup',flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activate(application):
        window=Gtk.ApplicationWindow(application=application,title='Simplemail · Import FairEmail')
        window.set_default_size(680,500)
        box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
        for method in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'):getattr(box,method)(18)
        window.set_child(box)
        box.append(Gtk.Label(label='Import '+', '.join(domains),xalign=0,wrap=True))
        box.append(Gtk.Label(label='Existing accounts and the invoice sender are preserved. Connections are checked before saving; no email is sent.',xalign=0,wrap=True))
        path=Gtk.Entry(text=str(backup));box.append(Gtk.Label(label='FairEmail backup file',xalign=0));box.append(path)
        box.append(Gtk.Label(label='Backup export password',xalign=0))
        password=Gtk.PasswordEntry(show_peek_icon=True);box.append(password)
        button=Gtk.Button(label='Check and import');box.append(button)
        status=Gtk.Label(label='Enter the password used when exporting the FairEmail backup.',wrap=True,xalign=0,selectable=True);box.append(status)
        close=Gtk.Button(label='Close');close.connect('clicked',lambda _:window.close());box.append(close)
        stopped=threading.Event();busy=False
        def closed(*_):stopped.set();return False
        window.connect('close-request',closed)
        def report_status(value):
            if report:
                report.parent.mkdir(parents=True,exist_ok=True)
                fd=os.open(report,os.O_CREAT|os.O_TRUNC|os.O_WRONLY,0o600)
                with os.fdopen(fd,'w') as f:json.dump(value,f)
        def progress(text):
            def update():
                if not stopped.is_set():status.set_text(text)
                return False
            GLib.idle_add(update)
        def start(_):
            nonlocal busy
            if busy:return
            busy=True;secret=password.get_text();filename=path.get_text()
            for widget in (path,password,button):widget.set_sensitive(False)
            status.set_text('Unlocking backup…');report_status({'status':'working'})
            def worker():
                try:
                    data=read_backup(filename,secret)
                    result=import_accounts(data,domains,progress,stopped.is_set)
                    outcome={'status':'finished','results':result};message='\n'.join(result)
                except Exception as error:
                    message=str(error).replace(secret,'[redacted]') if secret else str(error)
                    outcome={'status':'error','message':message}
                report_status(outcome)
                def done():
                    nonlocal busy
                    busy=False
                    if stopped.is_set():return False
                    for widget in (path,password,button):widget.set_sensitive(True)
                    status.set_text(message);password.set_text('')
                    return False
                GLib.idle_add(done)
            threading.Thread(target=worker,daemon=True).start()
        button.connect('clicked',start);password.connect('activate',start)
        keys=Gtk.EventControllerKey()
        def key(_,value,code,modifiers):
            if value==Gdk.KEY_Escape:window.close();return True
            return False
        keys.connect('key-pressed',key);window.add_controller(keys)
        report_status({'status':'waiting-for-backup-password'})
        window.present();password.grab_focus()
    app.connect('activate',activate)
    return app.run([])

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup',type=Path)
    parser.add_argument('--only',nargs='+',default=['blinkenshell.org','disroot.org'])
    parser.add_argument('--report',type=Path)
    args=parser.parse_args()
    backup=args.backup
    if backup is None:
        backup=Path(os.environ['SIMPLEMAIL_IMPORT_DIR']).expanduser() if os.environ.get('SIMPLEMAIL_IMPORT_DIR') else Path.home()
    import sys
    command=[sys.executable,str(Path(__file__).with_name('native-launch.py')),'--import-backup',str(backup),'--import-domains',','.join(args.only)]
    if args.report:command+=['--import-report',str(args.report)]
    os.execv(sys.executable,command)
if __name__=='__main__':raise SystemExit(main())
