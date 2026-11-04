#!/usr/bin/env python3
import sys as _theme_sys
from pathlib import Path as _ThemePath
_theme_sys.path.insert(0,str(_ThemePath(__file__).resolve().parent.parent/'simple-common'))
from theme_loader import load_css as _load_simple_css
"""Simplemail: keyboard-driven composer and inbox with background mail checks. SMTP acceptance and IMAP filing are separate steps."""
import argparse, datetime, email.policy, email.utils, fcntl, hashlib, imaplib, json, os
from pathlib import Path
import mimetypes, unicodedata
import re, shlex, shutil, smtplib, ssl, stat, subprocess, sys, tempfile, threading, tomllib, uuid
from contextlib import contextmanager
from concurrent.futures import ThreadPoolExecutor
from email.message import EmailMessage
from email.parser import BytesParser
from html.parser import HTMLParser
from html import escape
from urllib.parse import urlsplit, parse_qs, unquote
from urllib.request import Request, urlopen

CONFIG = Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplemail/config.toml'
KEY_FILE = Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/credentials.key'
import vault_backend

def desktop_environment():
    # SSH may omit session variables. Use the logged-in compositor's bus,
    # never guess /run/user/UID/bus on desktops using dbus-run-session.
    keys=('DBUS_SESSION_BUS_ADDRESS','XDG_RUNTIME_DIR','WAYLAND_DISPLAY','DISPLAY','MANGO_INSTANCE_SIGNATURE')
    if os.environ.get('DBUS_SESSION_BUS_ADDRESS') and (os.environ.get('WAYLAND_DISPLAY') or os.environ.get('DISPLAY')):return os.environ.copy()
    if not shutil.which('pgrep'):return os.environ.copy()
    for name in ('mango','sway','Hyprland','kwin_wayland','gnome-shell','kitty'):
        result=subprocess.run(['pgrep','-u',str(os.getuid()),'-x',name],capture_output=True,text=True)
        for pid in result.stdout.split():
            try:
                for item in Path('/proc/'+pid+'/environ').read_bytes().split(b'\0'):
                    key,sep,value=item.partition(b'=')
                    if key.decode() in keys and not os.environ.get(key.decode()): os.environ[key.decode()]=value.decode()
            except (OSError,UnicodeError): pass
    return os.environ.copy()

def settings():
    with CONFIG.open('rb') as stream: return account_settings(tomllib.load(stream))

ACCOUNT_COLORS = ('#d8a657','#7daea3','#a9b665','#d3869b','#89b4fa')

def account_settings(raw):
    entries=raw.get('accounts',[raw])
    if not isinstance(entries,list) or not entries: raise ValueError('Configure at least one [[accounts]] entry.')
    accounts=[]; seen=set()
    for index,entry in enumerate(entries):
        if not isinstance(entry,dict): raise ValueError('Each account must be a TOML table.')
        account=dict(entry)
        for field in ('username','imap_host','smtp_host','sent_folder'):
            if not isinstance(account.get(field),str) or not account[field].strip():
                raise ValueError('Missing '+field+' in mail account '+str(index+1))
        username=account['username']
        if username.casefold() in seen: raise ValueError('Duplicate mail account: '+username)
        seen.add(username.casefold())
        for field,default in (('imap_port',993),('smtp_port',465)):
            account.setdefault(field,default)
            if type(account[field]) is not int or not 1<=account[field]<=65535: raise ValueError('Invalid '+field+' for '+username)
        for protocol in ('imap','smtp'):
            security=account.get(protocol+'_security','ssl')
            if security not in ('ssl','starttls'): raise ValueError('Security must be ssl or starttls: '+username)
            login=account.get(protocol+'_username',username)
            if not isinstance(login,str) or any(c in login for c in ('\r','\n')): raise ValueError('Invalid login username: '+username)
        account.setdefault('display_name',username)
        account.setdefault('name',account['display_name'])
        account.setdefault('color',ACCOUNT_COLORS[index%len(ACCOUNT_COLORS)])
        if not isinstance(account['color'],str) or not re.fullmatch(r'#[0-9a-fA-F]{6}',account['color']):
            raise ValueError('Account color must be #RRGGBB: '+username)
        if any(not isinstance(account[key],str) or not account[key].strip() for key in ('name','display_name')):
            raise ValueError('Account name and display_name must be nonempty text: '+username)
        accounts.append(account)
    default=raw.get('default_account',accounts[0]['username'])
    chosen=next((a for a in accounts if a['username']==default),None)
    if chosen is None: raise ValueError('default_account must match an account username.')
    invoice=raw.get('invoice_account',default)
    if not any(a['username']==invoice for a in accounts): raise ValueError('invoice_account must match an account username.')
    return dict(chosen,accounts=accounts,invoice_account=invoice)

def configured_accounts(cfg):
    return cfg['accounts'] if 'accounts' in cfg else [cfg]

def message_account(cfg,item):
    username=item.get('account',cfg['username'])
    for account in configured_accounts(cfg):
        if account['username']==username: return account
    raise ValueError('Mail account is no longer configured: '+str(username))

def account_label(account):
    return account.get('name',account.get('display_name',account['username']))+' <'+account['username']+'>'

def message_time(item):
    try:
        date=email.utils.parsedate_to_datetime(item.get('date',''))
        if date.tzinfo is None: date=date.replace(tzinfo=datetime.timezone.utc)
        return date.timestamp()
    except (ValueError,TypeError,OverflowError,IndexError): return 0

def combined_headers(cfg,observer=None,folder="inbox"):
    accounts=configured_accounts(cfg)
    messages=[]; total=0; errors=[]; successes=0
    if folder not in ('inbox','sent','trash'):raise ValueError('Unknown mail view.')
    def fetch(account):
        return inbox_headers(account,password(account)) if folder=='inbox' else inbox_headers(account,password(account),account['sent_folder'] if folder=='sent' else trash_folder(account))
    with ThreadPoolExecutor(max_workers=min(3,len(accounts))) as pool:
        pending=[pool.submit(fetch,account) for account in accounts]
        for account,future in zip(accounts,pending):
            try: headers,count=future.result()
            except Exception as exc:
                errors.append(account_label(account)+': '+str(exc)); continue
            successes+=1; total+=count
            if observer is not None and folder=='inbox': observer(account,headers)
            messages.extend(dict(item,account=account['username']) for item in headers)
    if not successes: raise ValueError('\n'.join(errors))
    messages.sort(key=lambda item:(message_time(item),int(item['uid'])),reverse=True)
    return messages[:INBOX_LIMIT],total,errors

MAIL_CHECK_SECONDS = 300

class NewMailNotifications:
    """Only UID positions are persisted; each machine tracks its own notifications."""
    def __init__(self, path=None):
        self.path=path or Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/new-mail.json'
        self.lock=threading.Lock()
        try:
            data=json.loads(self.path.read_text())
            self.positions=data if isinstance(data,dict) else {}
        except (OSError,ValueError): self.positions={}

    def observe(self,account,messages):
        key=hashlib.sha256((account['imap_host']+'\0'+str(account.get('imap_port',993))+'\0'+account['username']).encode()).hexdigest()
        with self.lock:
            previous=self.positions.get(key)
            if not isinstance(previous,dict) or not isinstance(previous.get('uid'),int): previous=None
            if messages:
                validity=messages[0]['validity']
                if isinstance(validity,bytes): validity=validity.decode('ascii',errors='replace')
                matching=previous is not None and previous.get('validity') in (None,validity)
                seen=previous['uid'] if matching else 0
                fresh=[m for m in messages if matching and int(m['uid'])>seen and m['unread']]
                self.positions[key]=dict(validity=validity,uid=max(seen,max(int(m['uid']) for m in messages)))
            else:
                fresh=[]
                if previous is None: self.positions[key]=dict(validity=None,uid=0)
            try:
                self.path.parent.mkdir(parents=True,exist_ok=True)
                save(self.path,self.positions)
            except OSError as exc: print('Simplemail: could not save notification position: '+str(exc),file=sys.stderr)
            if fresh and shutil.which('notify-send'):
                body='\n'.join(escape(m['sender']+' — '+m['subject']) for m in fresh[:3])
                if len(fresh)>3: body+=f'\n…and {len(fresh)-3} more'
                title=f"{len(fresh)} new {'message' if len(fresh)==1 else 'messages'} · {account.get('name',account['username'])}"
                try: subprocess.run(['notify-send','-a','Simplemail','-i','mail-unread','--',title,body],timeout=5,check=False)
                except (OSError,subprocess.TimeoutExpired): pass

def password_file():
    return CONFIG.parent/'passwords.json'

def read_private(path):
    try: fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    except FileNotFoundError: raise
    except OSError: raise ValueError('Cannot open the Simplemail credentials file.') from None
    with os.fdopen(fd,'rb') as stream:
        info=os.fstat(stream.fileno())
        if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or info.st_mode & 0o077:
            raise ValueError('Simplemail credentials must be a private regular file owned by you (chmod 600).')
        data=stream.read(1024*1024+1)
        if len(data)>1024*1024: raise ValueError('Simplemail credentials file is too large.')
        return data

def password_key(create=False):
    from cryptography.fernet import Fernet
    try: key=read_private(KEY_FILE).strip()
    except FileNotFoundError:
        if not create: raise ValueError('Simplemail encryption key is missing. Restore it from another machine or an encrypted Newinstall recovery backup.') from None
        KEY_FILE.parent.mkdir(mode=0o700,parents=True,exist_ok=True); KEY_FILE.parent.chmod(0o700)
        key=Fernet.generate_key()
        try: fd=os.open(KEY_FILE,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        except FileExistsError: return password_key()
        with os.fdopen(fd,'wb') as stream:
            stream.write(key+b'\n'); stream.flush(); os.fsync(stream.fileno())
        directory=os.open(KEY_FILE.parent,os.O_RDONLY|os.O_DIRECTORY)
        try: os.fsync(directory)
        finally: os.close(directory)
    try: Fernet(key)
    except (ValueError,TypeError): raise ValueError('Invalid Simplemail encryption key; restore its backup.') from None
    return key

def validate_passwords(data):
    if not isinstance(data,dict) or data.get('version')!=1 or not isinstance(data.get('accounts'),dict):
        raise ValueError('Invalid Simplemail password file format.')
    accounts=data['accounts']
    if any(not isinstance(user,str) or not isinstance(secret,str) or not secret for user,secret in accounts.items()):
        raise ValueError('Invalid account entry in Simplemail password file.')
    return accounts

def encode_passwords(accounts,create_key=False):
    from cryptography.fernet import Fernet
    data={'version':1,'accounts':accounts}; validate_passwords(data)
    encrypted=Fernet(password_key(create=create_key)).encrypt(json.dumps(data).encode())
    return json.dumps({'version':2,'encryption':'fernet','ciphertext':encrypted.decode()},indent=2)+'\n'

def saved_passwords():
    if vault_backend.enabled(): return vault_backend.load()
    from cryptography.fernet import Fernet, InvalidToken
    try: raw=read_private(password_file())
    except FileNotFoundError: return {}
    try: data=json.loads(raw)
    except (ValueError,UnicodeError): raise ValueError('Invalid Simplemail password file; restore its backup.') from None
    if isinstance(data,dict) and data.get('version')==1:
        raise ValueError('Simplemail passwords need encryption. Run simplemail --encrypt-passwords once.')
    if not isinstance(data,dict) or data.get('version')!=2 or data.get('encryption')!='fernet' or not isinstance(data.get('ciphertext'),str):
        raise ValueError('Invalid Simplemail encrypted password file format.')
    key=password_key()
    try: clear=Fernet(key).decrypt(data['ciphertext'].encode()); decoded=json.loads(clear)
    except (InvalidToken,ValueError,UnicodeError):
        raise ValueError('Cannot decrypt Simplemail passwords: wrong key or damaged file. No passwords were changed.') from None
    return validate_passwords(decoded)

def encrypt_passwords():
    if vault_backend.enabled(): return 0
    """Explicit one-time conversion. No plaintext backup or temporary file."""
    from cryptography.fernet import Fernet
    folder=CONFIG.parent; folder.mkdir(mode=0o700,parents=True,exist_ok=True); folder.chmod(0o700)
    fd=os.open(folder/'.passwords.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        try: original=read_private(password_file())
        except FileNotFoundError: return 0
        try: data=json.loads(original)
        except (ValueError,UnicodeError): raise ValueError('Invalid Simplemail password file; migration stopped.') from None
        if isinstance(data,dict) and data.get('version')==2:
            saved_passwords(); return 0
        accounts=validate_passwords(data)
        encrypted=encode_passwords(accounts,create_key=True)
        assert validate_passwords(json.loads(Fernet(password_key()).decrypt(json.loads(encrypted)['ciphertext'].encode())))==accounts
        fd,temporary=tempfile.mkstemp(prefix='.passwords-',dir=folder)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(encrypted); stream.flush(); os.fsync(stream.fileno())
            if read_private(password_file())!=original: raise ValueError('Passwords changed during migration; retry.')
            os.replace(temporary,password_file())
            directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally: Path(temporary).unlink(missing_ok=True)
    print('Simplemail passwords encrypted; automatic local unlocking ready.')
    return 0

def store_passwords(updates,overwrite=True):
    if vault_backend.enabled(): return vault_backend.store(updates,overwrite)
    if any(not isinstance(user,str) or not isinstance(secret,str) or not secret for user,secret in updates.items()):
        raise ValueError('Enter the actual mailbox password; it cannot be empty.')
    folder=CONFIG.parent
    folder.mkdir(mode=0o700,parents=True,exist_ok=True); folder.chmod(0o700)
    fd=os.open(folder/'.passwords.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        accounts=saved_passwords()
        for user,secret in updates.items():
            if overwrite or user not in accounts: accounts[user]=secret
        encrypted=encode_passwords(accounts,create_key=not password_file().exists())
        fd,temporary=tempfile.mkstemp(prefix='.passwords-',dir=folder)
        try:
            with os.fdopen(fd,'w') as stream:
                stream.write(encrypted)
                stream.flush(); os.fsync(stream.fileno())
            os.replace(temporary,password_file())
            directory=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(directory)
            finally: os.close(directory)
        finally: Path(temporary).unlink(missing_ok=True)

def password(cfg):
    secret=saved_passwords().get(cfg['username'])
    if secret: return secret
    raise ValueError('Password missing for '+cfg['username']+'. Save it once with simplemail --setup on the desktop, then sync.')

def keyring_passwords(accounts):
    # One-time migration only. Never unlock or prompt; unrelated secrets stay put.
    import dbus
    bus=dbus.SessionBus()
    service=dbus.Interface(bus.get_object('org.freedesktop.secrets','/org/freedesktop/secrets'),'org.freedesktop.Secret.Service')
    _,session=service.OpenSession('plain',dbus.String('',variant_level=1))
    found={}
    try:
        for account in accounts:
            for application in ('simplemail','invoice-mail'):
                unlocked,_=service.SearchItems({'application':application,'account':account['username']})
                if not unlocked: continue
                item=dbus.Interface(bus.get_object('org.freedesktop.secrets',unlocked[0]),'org.freedesktop.Secret.Item')
                secret=bytes(item.GetSecret(session)[2]).decode('utf-8')
                if secret: found[account['username']]=secret; break
    finally:
        dbus.Interface(bus.get_object('org.freedesktop.secrets',session),'org.freedesktop.Secret.Session').Close()
    return found

def migrate_keyring(cfg):
    if vault_backend.enabled(): return 0
    saved=saved_passwords()
    missing=[a for a in configured_accounts(cfg) if a['username'] not in saved]
    if not missing: print('Simplemail: portable passwords ready.'); return 0
    try: found=keyring_passwords(missing)
    except Exception:
        print('Simplemail: old keyring unavailable; no unlock prompt was opened.'); found={}
    if found: store_passwords(found,overwrite=False)
    saved=saved_passwords()
    missing=[a['username'] for a in configured_accounts(cfg) if a['username'] not in saved]
    if missing:
        print('Simplemail PENDING: save these mailbox passwords once on the desktop, then sync: '+', '.join(missing)); return 2
    print('Simplemail: saved mailbox passwords migrated to the private portable file.'); return 0

def save(path, value):
    temporary = path.with_name(path.name+'.tmp')
    fd=os.open(temporary,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as stream:
        json.dump(value,stream,indent=2); stream.write('\n'); stream.flush(); os.fsync(stream.fileno())
    os.replace(temporary,path)

def login_username(cfg,protocol):
    return cfg.get(protocol+'_username') or cfg['username']

def imap_client(cfg,secret):
    security=cfg.get('imap_security','ssl')
    if security=='ssl':
        client=imaplib.IMAP4_SSL(cfg['imap_host'],cfg['imap_port'],ssl_context=ssl.create_default_context(),timeout=30)
    elif security=='starttls':
        client=imaplib.IMAP4(cfg['imap_host'],cfg['imap_port'],timeout=30)
        try: client.starttls(ssl_context=ssl.create_default_context())
        except BaseException: client.shutdown(); raise
    else: raise ValueError('Unsupported IMAP security mode.')
    try: client.login(login_username(cfg,'imap'),secret)
    except BaseException: client.shutdown(); raise
    return client

def smtp_client(cfg):
    security=cfg.get('smtp_security','ssl')
    if security=='ssl':
        return smtplib.SMTP_SSL(cfg['smtp_host'],cfg['smtp_port'],timeout=30,context=ssl.create_default_context())
    if security!='starttls': raise ValueError('Unsupported SMTP security mode.')
    client=smtplib.SMTP(cfg['smtp_host'],cfg['smtp_port'],timeout=30)
    try:
        client.ehlo(); client.starttls(context=ssl.create_default_context()); client.ehlo()
    except BaseException: client.close(); raise
    return client

def mailbox(cfg, secret):
    client=imap_client(cfg,secret)
    try:
        typ,_=client.select('"'+cfg['sent_folder']+'"',readonly=True)
        if typ!='OK': raise ValueError('Configured Sent folder is unavailable.')
        return client
    except BaseException:
        client.shutdown(); raise

def verify_account(cfg,secret):
    """Verify sending credentials and read-only Sent access; never send mail."""
    try:
        with smtp_client(cfg) as client:
            client.login(login_username(cfg,'smtp'),secret)
    except Exception as error:
        raise ValueError('SMTP login failed: '+str(error).replace(secret,'[redacted]')) from None
    try:
        client=mailbox(cfg,secret); client.logout()
    except Exception as error:
        raise ValueError('IMAP check failed: '+str(error).replace(secret,'[redacted]')) from None

def file_sent(cfg, secret, raw, record):
    client=mailbox(cfg,secret)
    try:
        typ,data=client.uid('SEARCH',None,'HEADER','Message-ID',record['message_id'])
        if typ!='OK': raise ValueError('Cannot check Sent folder for an existing copy.')
        if not data[0]:
            typ,_=client.append('"'+cfg['sent_folder']+'"','\\Seen',imaplib.Time2Internaldate(datetime.datetime.now().astimezone()),raw)
            if typ!='OK': raise ValueError('Bluehost did not save the Sent copy.')
    finally: client.logout()

def reply_source(account,item):
    if item.get('folder','INBOX')!='INBOX':raise ValueError('Reply from the Inbox view.')
    validity=item['validity'].decode('ascii') if isinstance(item['validity'],bytes) else str(item['validity'])
    uid=str(item['uid'])
    if not re.fullmatch(r'[1-9][0-9]*',uid) or not re.fullmatch(r'[1-9][0-9]*',validity):
        raise ValueError('Invalid original message identity. Refresh the inbox.')
    return dict(account=account['username'],imap_host=account['imap_host'],imap_port=account.get('imap_port',993),
                uid=uid,validity=validity)

def mark_reply_answered(cfg,secret,source):
    if (source['account'],source['imap_host'],source['imap_port'])!=(cfg['username'],cfg['imap_host'],cfg.get('imap_port',993)):
        raise ValueError('Original reply mailbox no longer matches this account.')
    if not re.fullmatch(r'[1-9][0-9]*',str(source['uid'])) or not re.fullmatch(r'[1-9][0-9]*',str(source['validity'])):
        raise ValueError('Invalid original message identity.')
    with inbox_connection(cfg,secret,source['validity'].encode('ascii'),writable=True) as (client,_,__):
        typ,data=client.uid('STORE',source['uid'],'+FLAGS',r'(\Seen \Answered)')
        if typ!='OK':raise ValueError('Server could not mark the original message read and replied.')
        # A successful STORE may omit unchanged flags. Verify server state explicitly.
        typ,data=client.uid('FETCH',source['uid'],'(UID FLAGS)')
        confirmed=False
        for item in data or []:
            raw=item[0] if isinstance(item,tuple) else item
            if not isinstance(raw,bytes):continue
            uid=re.search(rb'\bUID (\d+)',raw)
            flags=imaplib.ParseFlags(raw)
            if uid and uid[1].decode()==source['uid'] and b'\\Seen' in flags and b'\\Answered' in flags:confirmed=True
        if typ!='OK' or not confirmed:
            raise ValueError('Could not confirm the original message as read and replied. It may have moved; refresh the inbox.')

def complete_sent(cfg,secret,raw,record,receipt,reply_cfg=None):
    # SMTP has already accepted this message. Neither retry path sends it again.
    errors=[]
    source=record.get('reply_source')
    if source and not record.get('reply_marked'):
        try:
            account=reply_cfg or cfg
            if 'imap_host' not in source or 'imap_port' not in source:
                # Repair references saved by the native composer before canonical identities.
                if source.get('account')!=account['username']:
                    raise ValueError('Original reply account no longer matches. Select the original account.')
                source=reply_source(account,source)
                record['reply_source']=source;save(receipt,record)
            reply_secret=secret if account['username']==cfg['username'] else password(account)
            mark_reply_answered(account,reply_secret,source)
            record['reply_marked']=True;save(receipt,record)
        except Exception as error:errors.append('Original message flags pending: '+str(error))
    if not record.get('sent_filed'):
        try:
            file_sent(cfg,secret,raw,record)
            record['sent_filed']=True;save(receipt,record)
        except Exception as error:errors.append('Sent copy pending: '+str(error))
    if errors:
        return 'Email already sent. '+ '\n'.join(errors)+'\nRetry sync updates flags/the Sent copy only; it never sends another email.'
    record['status']='filed';save(receipt,record)
    return 'Email sent and saved in Sent.'+(' Original marked read and replied.' if source else '')

def send(pdf, recipient, subject, body, cfg, secret, attachments=None, record_base=None, invoice=None, reply_to=None, reply_cfg=None):
    pdf=Path(pdf).resolve() if pdf else None
    if invoice is None: invoice=bool(pdf)  # Preserve the accounting command-line/API contract.
    if '\n' in recipient or '\r' in recipient or '\n' in subject or '\r' in subject: raise ValueError('Invalid mail header.')
    addresses=[]
    for item in recipient.split(','):
        item=item.strip()
        address=email.utils.parseaddr(item)[1]
        if not address or item!=address or address.count('@')!=1 or any(c.isspace() for c in address) or not all(address.split('@')):
            raise ValueError('Enter plain email addresses separated by commas.')
        if address not in addresses: addresses.append(address)
    recipient_header=', '.join(addresses)
    paths=[Path(value).resolve() for value in (attachments or ([pdf] if pdf else []))]
    blobs=[value.read_bytes() for value in paths]
    if invoice and any(not value.startswith(b'%PDF-') for value in blobs): raise ValueError('Accounting invoices require PDF attachments.')
    data=blobs[0] if blobs else b''
    base=record_base or (pdf if invoice else None) or Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/outbox'/str(uuid.uuid4())
    base=Path(base);base.parent.mkdir(parents=True,exist_ok=True)
    receipt=base.with_suffix(base.suffix+'.sent.json'); eml=base.with_suffix(base.suffix+'.sent.eml')
    lock=base.with_suffix(base.suffix+'.mail.lock')
    fd=os.open(lock,os.O_RDWR|os.O_CREAT,0o600)
    with os.fdopen(fd,'w') as stream:
        fcntl.flock(stream,fcntl.LOCK_EX|fcntl.LOCK_NB)
        if receipt.exists():
            record=json.loads(receipt.read_text())
            if record['status']=='filed': return 'Already sent and saved in Sent. No second email sent.'
            if record['status']=='accepted':
                raw=eml.read_bytes()
                original=record.get('account') or email.utils.parseaddr(str(BytesParser(policy=email.policy.default).parsebytes(raw,headersonly=True).get('From','')))[1]
                if original!=cfg['username'] or record.get('imap_host',cfg.get('imap_host'))!=cfg.get('imap_host'):
                    raise ValueError('This email was already sent from '+original+'. Select that account to save its Sent copy.')
                return complete_sent(cfg,secret,raw,record,receipt,reply_cfg)
            raise ValueError('An earlier send has an uncertain result. Check Sent and Bluehost delivery logs before sending again. Receipt: '+str(receipt))
        message=EmailMessage(policy=email.policy.SMTP)
        message['From']=email.utils.formataddr((cfg['display_name'],cfg['username']))
        message['To']=recipient_header; message['Subject']=subject
        message['Date']=email.utils.formatdate(localtime=True)
        message['Message-ID']=email.utils.make_msgid(domain=cfg['username'].split('@')[1])
        message.set_content(body)
        for attachment,blob in zip(paths,blobs):
            content_type,encoding=mimetypes.guess_type(attachment.name)
            if not content_type or encoding: content_type='application/octet-stream'
            maintype,subtype=content_type.split('/',1)
            message.add_attachment(blob,maintype=maintype,subtype=subtype,filename=attachment.name)
        raw=message.as_bytes()
        record={'status':'prepared','recipient':recipient_header,'subject':subject,'invoice':pdf.name if pdf and invoice else None,'pdf_sha256':hashlib.sha256(data).hexdigest() if pdf and invoice else None,'message_id':message['Message-ID'],'attachments':[{'path':str(p),'sha256':hashlib.sha256(b).hexdigest()} for p,b in zip(paths,blobs)]}
        record.update(account=cfg['username'],imap_host=cfg.get('imap_host'))
        if reply_to:record['reply_source']=dict(reply_to)
        # Connect and authenticate before publishing an attempt record.
        client=smtp_client(cfg)
        try:
            client.login(login_username(cfg,'smtp'),secret)
            # A durable original message enables filing without a resend.
            with eml.open('xb') as output: os.chmod(eml,0o600); output.write(raw); output.flush(); os.fsync(output.fileno())
            record['status']='submitting'; save(receipt,record)
            code,response=client.mail(cfg['username'])
            if code!=250: raise ValueError('SMTP rejected the sender: '+str(code))
            for address in addresses:
                code,response=client.rcpt(address)
                if code not in (250,251): raise ValueError('SMTP rejected recipient '+address+': '+str(code))
            code,response=client.data(raw)
            if code!=250: raise ValueError('SMTP rejected the message: '+str(code))
            record.update(status='accepted',accepted_at=datetime.datetime.now(datetime.timezone.utc).isoformat(),smtp_response=response.decode(errors='replace'))
            save(receipt,record)
        finally:
            client.close()
        return complete_sent(cfg,secret,raw,record,receipt,reply_cfg)

def check(cfg):
    import gi
    gi.require_version('Gtk','4.0')
    missing=[]
    for account in configured_accounts(cfg):
        try: password(account)
        except ValueError: missing.append(account['username'])
    if missing:
        print(('Simplemail PENDING: unlock KeePassXC and check saved mail accounts: ' if vault_backend.enabled() else 'Simplemail PENDING: save passwords on the desktop with simplemail --setup, then sync: ')+', '.join(missing)); return 2
    print('Simplemail: GTK and shared KeePassXC credentials ready.' if vault_backend.enabled() else 'Simplemail: GTK and portable account passwords ready.'); return 0

INBOX_LIMIT = 50
MESSAGE_LIMIT = 2 * 1024 * 1024
TEXT_LIMIT = 100000
MEDIA_LIMIT = 20 * 1024 * 1024
CACHE_LOCK = threading.Lock()

def cache_folder(name):
    folder=Path(os.environ.get('XDG_CACHE_HOME') or Path.home()/'.cache')/'simplemail'/name
    folder.mkdir(parents=True,exist_ok=True,mode=0o700); folder.chmod(0o700)
    return folder

def cache_write(folder,name,data):
    path=folder/name
    with CACHE_LOCK:
        fd,temporary=tempfile.mkstemp(dir=folder,prefix='.cache-')
        try:
            with os.fdopen(fd,'wb') as output: output.write(data)
            os.replace(temporary,path)
        finally: Path(temporary).unlink(missing_ok=True)
        # Each cache is capped at 32 MiB and 128 files, oldest used first.
        files=sorted((p for p in folder.iterdir() if p.is_file() and not p.name.startswith('.')),key=lambda p:p.stat().st_mtime,reverse=True)
        size=0
        for index,cached in enumerate(files):
            size+=cached.stat().st_size
            if cached!=path and (index>=128 or size>32*1024*1024): cached.unlink(missing_ok=True)
    return path

def preview_file(cfg,item,limit):
    identity=(cfg['imap_host'],cfg['imap_port'],cfg['username'],str(item['validity']),item['uid'],limit)
    if item.get('folder','INBOX')!='INBOX':identity+=(item['folder'],)
    key=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
    return cache_folder('previews')/(key+'.preview')

def prefetch_items(messages):
    unread=[item for item in messages if item['unread']]
    return unread+[item for item in messages if not item['unread']][:5]

def web_url(value):
    if not value or any(ord(c)<32 for c in value): return False
    try: return urlsplit(value).scheme.lower() in ('http','https') and bool(urlsplit(value).hostname)
    except ValueError: return False

def image_extension(data):
    if data.startswith(b'\x89PNG\r\n\x1a\n'): return '.png'
    if data.startswith(b'\xff\xd8\xff'): return '.jpg'
    if data.startswith((b'GIF87a',b'GIF89a')): return '.gif'
    if data[:4]==b'RIFF' and data[8:12]==b'WEBP': return '.webp'
    if data.startswith(b'BM'): return '.bmp'
    if data.startswith((b'II\x2a\x00',b'MM\x00\x2a')): return '.tiff'
    raise ValueError('This image format is not supported for preview.')

def image_file(item):
    data=item.get('data')
    if data is None:
        url=item.get('url','')
        if not web_url(url): raise ValueError('Not a web image address.')
        request=Request(url,headers={'User-Agent':'Simplemail/1.0'})
        with urlopen(request,timeout=15,context=ssl.create_default_context()) as response:
            if not web_url(response.geturl()): raise ValueError('Image redirect is not a web address.')
            data=response.read(MEDIA_LIMIT+1)
    if len(data)>MEDIA_LIMIT: raise ValueError('Image exceeds the 20 MiB limit.')
    suffix=image_extension(data)
    return cache_write(cache_folder('images'),hashlib.sha256(data).hexdigest()+suffix,data)

def image_thumbnail(path):
    import gi
    gi.require_version('GdkPixbuf','2.0')
    from gi.repository import GdkPixbuf
    info,width,height=GdkPixbuf.Pixbuf.get_file_info(str(path))
    if not info or width*height>40000000: raise ValueError('Image cannot be previewed or exceeds 40 megapixels.')
    return GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path),min(600,width),min(260,height),True)

def open_default(target):
    from gi.repository import Gio,Gdk
    uri=target.as_uri() if isinstance(target,Path) else target
    if not isinstance(target,Path) and not web_url(uri): raise ValueError('Not a web address.')
    # A desktop launch context carries the user activation token, so Mango
    # follows the default browser to its tag when a link is opened.
    display=Gdk.Display.get_default() if not isinstance(target,Path) else None
    context=display.get_app_launch_context() if display else None
    Gio.AppInfo.launch_default_for_uri(uri,context)

@contextmanager
def inbox_connection(cfg, secret, validity=None, writable=False, folder="INBOX"):
    if not isinstance(folder,str) or not folder or any(c in folder for c in '\r\n\x00'):raise ValueError('Invalid mailbox name.')
    target='INBOX' if folder=='INBOX' else '"'+folder.replace('\\','\\\\').replace('"','\\"')+'"'
    client=imap_client(cfg,secret)
    try:
        typ,data=client.select(target,readonly=not writable)
        if typ!='OK': raise ValueError('Cannot open mailbox: '+folder)
        values=client.response('UIDVALIDITY')[1]
        current=values[0] if values else None
        if not current: raise ValueError('Server did not identify the Inbox. Refresh and try again.')
        if isinstance(validity,str): validity=validity.encode('ascii')
        if validity is not None and current!=validity:
            raise ValueError('Inbox changed on the server. Refresh before opening this message.')
        yield client,current,int(data[0])
    finally:
        # LOGOUT does not expunge messages, unlike CLOSE on a writable mailbox.
        try: client.logout()
        except (OSError,imaplib.IMAP4.error): client.shutdown()

def inbox_headers(cfg, secret, folder='INBOX'):
    connection=inbox_connection(cfg,secret) if folder=='INBOX' else inbox_connection(cfg,secret,folder=folder)
    with connection as (client,validity,total):
        if not total: return [],0
        start=max(1,total-INBOX_LIMIT+1)
        typ,data=client.fetch(f'{start}:{total}',
            '(UID FLAGS RFC822.SIZE BODY.PEEK[HEADER.FIELDS (FROM TO SUBJECT DATE REPLY-TO)])')
        if typ!='OK': raise ValueError('Could not load inbox headers.')
        messages=[]
        for item in data:
            if not isinstance(item,tuple): continue
            meta,raw=item
            uid=re.search(rb'\bUID (\d+)',meta)
            if not uid: raise ValueError('Server returned a message without a UID.')
            header=BytesParser(policy=email.policy.default).parsebytes(raw,headersonly=True)
            messages.append(dict(uid=uid[1].decode(),validity=validity,folder=folder,
                sender='To: '+str(header.get('To','Unknown recipient')) if folder==cfg.get('sent_folder') else str(header.get('From','Unknown sender')),
                subject=str(header.get('Subject','(No subject)')),
                date=str(header.get('Date','')),unread=b'\\Seen' not in imaplib.ParseFlags(meta),
                answered=b'\\Answered' in imaplib.ParseFlags(meta)))
        return sorted(messages,key=lambda m:int(m['uid']),reverse=True),total

class MailText(HTMLParser):
    """Readable HTML-to-text preview, without a browser engine or remote requests."""
    VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
    BLOCK={'p','div','section','article','header','footer','main','aside','address','figure','figcaption','dl','dt','dd'}
    HEADINGS={'h1','h2','h3','h4','h5','h6'}
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts=[];self.hidden=[];self.links=[];self.urls=[];self.images=[]
        self.lists=[];self.tables=[];self.quote=0;self.pre=0

    def newline(self,count=1):
        while self.parts and not self.parts[-1].strip(' \t'):self.parts.pop()
        if not self.parts:return
        self.parts[-1]=self.parts[-1].rstrip(' \t')
        tail=''.join(self.parts[-3:]);existing=len(tail)-len(tail.rstrip('\n'))
        if existing<count:self.parts.append('\n'*(count-existing))

    def write(self,text,preserve=False):
        text=text.replace('\xa0',' ').replace('\u200b','').replace('\ufeff','').replace('\u00ad','')
        if not preserve:text=re.sub(r'\s+',' ',text)
        if not self.parts or self.parts[-1].endswith(('\n',' ','\t')):
            if not preserve:text=text.lstrip()
        if not text:return
        if self.quote and (not self.parts or self.parts[-1].endswith('\n')):self.parts.append('> '*self.quote)
        self.parts.append(text)

    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs);style=attrs.get('style') or ''
        hidden=tag in ('script','style','head','template','noscript') or 'hidden' in attrs or bool(
            re.search(r'(?:^|;)\s*(?:display\s*:\s*none|visibility\s*:\s*hidden|mso-hide\s*:\s*all)\b',style,re.I))
        if self.hidden or hidden:
            if tag not in self.VOID:self.hidden.append(tag)
            return
        if tag in self.HEADINGS or tag in ('p','section','article','blockquote','pre','ul','ol','table'):
            self.newline(2)
        elif tag in self.BLOCK or tag in ('br','li','tr'):self.newline()
        if tag=='blockquote':self.quote+=1
        elif tag=='pre':self.pre+=1
        elif tag in ('ul','ol'):
            try:start=int(attrs.get('start',1))
            except (TypeError,ValueError):start=1
            self.lists.append([tag,start])
        elif tag=='li':
            if self.lists and self.lists[-1][0]=='ol':
                marker=str(self.lists[-1][1])+'. ';self.lists[-1][1]+=1
            else:marker='• '
            self.write('  '*max(0,len(self.lists)-1)+marker,preserve=True)
        elif tag=='table':self.tables.append(0)
        elif tag=='tr':
            if self.tables:self.tables[-1]=0
        elif tag in ('td','th'):
            if self.tables:
                if self.tables[-1]:self.write(' | ',preserve=True)
                self.tables[-1]+=1
        elif tag=='hr':self.newline(2);self.write('────────');self.newline(2)
        elif tag=='a':
            target=(attrs.get('href') or '').strip()
            if web_url(target) and target not in self.urls and len(self.urls)<100:self.urls.append(target)
            self.links.append((target,len(self.parts)))
        elif tag=='img':
            target=(attrs.get('src') or '').strip();alt=re.sub(r'\s+',' ',attrs.get('alt') or '').strip()
            tiny=any(re.fullmatch(r'[01](?:px)?',str(attrs.get(k,'')).strip()) for k in ('width','height'))
            if tiny:return
            if web_url(target) and len(self.images)<32:self.images.append(dict(name=alt or 'Remote image',url=target))
            if alt:self.write('[Image: '+alt+']')

    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs)
        if tag not in self.VOID:self.handle_endtag(tag)

    def handle_endtag(self,tag):
        if self.hidden:
            if tag in self.hidden:
                index=len(self.hidden)-1-self.hidden[::-1].index(tag);del self.hidden[index:]
            return
        if tag=='a' and self.links:
            target,start=self.links.pop();label=''.join(self.parts[start:]).strip()
            if target in self.urls:
                if not label:self.write(urlsplit(target).netloc or 'Link')
                elif len(label)>90 and web_url(label):
                    del self.parts[start:];self.write(urlsplit(label).netloc+' / …')
                self.write(' ['+str(self.urls.index(target)+1)+']')
            elif target.startswith('mailto:') and not label:self.write(target[7:].split('?')[0])
        elif tag in ('ul','ol'):
            if self.lists:self.lists.pop()
            self.newline(1 if self.lists else 2)
        elif tag=='blockquote':self.quote=max(0,self.quote-1);self.newline(2)
        elif tag=='pre':self.pre=max(0,self.pre-1);self.newline(2)
        elif tag=='table':
            if self.tables:self.tables.pop()
            self.newline(2)
        elif tag in self.HEADINGS or tag in ('p','section','article'):self.newline(2)
        elif tag in self.BLOCK or tag in ('li','tr'):self.newline()

    def handle_data(self,data):
        if not self.hidden:self.write(data,preserve=bool(self.pre))

    def text(self):
        # Keep preformatted indentation while removing HTML source whitespace.
        return re.sub(r'\n[ \t]*\n(?:[ \t]*\n)+','\n\n',''.join(self.parts)).strip()


def readable_message(raw, truncated=False):
    message=BytesParser(policy=email.policy.default).parsebytes(raw)
    part=message.get_body(preferencelist=('html','plain'))
    links=[]; images=[]; html_body=None
    html=message.get_body(preferencelist=('html',))
    if html is not None:
        payload=html.get_payload(decode=True) or b''
        try: html_text=payload.decode(html.get_content_charset() or 'utf-8',errors='replace')
        except LookupError: html_text=payload.decode('utf-8',errors='replace')
        parser=MailText(); parser.feed(html_text); parser.close()
        links=parser.urls; images=parser.images; html_body=parser.text()
    text='No readable text body in this message.'
    if part is not None:
        payload=part.get_payload(decode=True) or b''
        try: text=payload.decode(part.get_content_charset() or 'utf-8',errors='replace')
        except LookupError: text=payload.decode('utf-8',errors='replace')
        if part.get_content_type()=='text/html':text=html_body or ''
    if not text.strip():
        plain=message.get_body(preferencelist=('plain',))
        if plain is not None:
            payload=plain.get_payload(decode=True) or b''
            try:text=payload.decode(plain.get_content_charset() or 'utf-8',errors='replace')
            except LookupError:text=payload.decode('utf-8',errors='replace')
        if not text.strip():text='No readable text body in this message. Press i to inspect images.'
    attachments=[str(p.get_filename() or p.get_content_type())
                 for p in message.iter_attachments()]
    links=list(dict.fromkeys(links+[u.rstrip('.,;:!?)]}') for u in re.findall(r'https?://[^\s<>"\x00]+',text) if web_url(u)]))[:100]
    if not truncated:
        for part in message.walk():
            if part.get_content_maintype()=='image':
                data=part.get_payload(decode=True) or b''
                try: image_extension(data)
                except ValueError: continue
                images.append(dict(name=str(part.get_filename() or 'Embedded image'),data=data))
                if len(images)>=32: break
    notes=[]
    if html_body is not None and text==html_body and links:notes.append('HTML text preview · [number] links: press o · Images: press i')
    if attachments: notes.append('Attachments: '+', '.join(attachments))
    if truncated: notes.append('Large message: incomplete preview; press i to load images from messages up to 20 MiB.')
    if len(text)>TEXT_LIMIT: notes.append('Long message: text preview shortened.')
    return dict(sender=str(message.get('From','')),to=str(message.get('To','')),subject=str(message.get('Subject','(No subject)')),
        date=str(message.get('Date','')),recipient=email.utils.parseaddr(str(message.get('Reply-To') or message.get('From','')))[1],
        text=text[:TEXT_LIMIT].replace('\x00',''),notes='\n'.join(notes),links=links,images=images[:32],truncated=truncated)

def inbox_message(cfg, secret, item, limit=MESSAGE_LIMIT, parse=True):
    cached=None
    try:
        cached=preview_file(cfg,item,limit)
        if cached.stat().st_size<=limit+100:
            header,_,raw=cached.read_bytes().partition(b'\n')
            truncated=json.loads(header)['truncated']
            if not isinstance(truncated,bool): raise ValueError('Invalid cache metadata')
            cached.touch()
            return readable_message(raw,truncated) if parse else None
    except (OSError,ValueError,KeyError,TypeError): pass
    connection=inbox_connection(cfg,secret,item['validity']) if item.get('folder','INBOX')=='INBOX' else inbox_connection(cfg,secret,item['validity'],folder=item['folder'])
    with connection as (client,_,__):
        typ,data=client.uid('FETCH',item['uid'],f'(UID RFC822.SIZE BODY.PEEK[]<0.{limit}>)')
        if typ!='OK': raise ValueError('Could not load this message.')
        for entry in data:
            if not isinstance(entry,tuple): continue
            meta,raw=entry
            uid=re.search(rb'\bUID (\d+)',meta)
            if not uid or uid[1].decode()!=item['uid']: continue
            size=re.search(rb'RFC822.SIZE (\d+)',meta)
            truncated=bool(size and int(size[1])>len(raw))
            try:
                if cached is not None: cache_write(cached.parent,cached.name,json.dumps({'truncated':truncated}).encode()+b'\n'+raw)
            except OSError: pass
            return readable_message(raw,truncated) if parse else None
        raise ValueError('This message is no longer available. Refresh the inbox.')

def inbox_mark_read(cfg, secret, item):
    if item.get('folder','INBOX')!='INBOX':raise ValueError('Mark mail from the Inbox view.')
    with inbox_connection(cfg,secret,item['validity'],writable=True) as (client,_,__):
        typ,data=client.uid('STORE',item['uid'],'+FLAGS','(\\Seen)')
        if typ!='OK' or not any(data): raise ValueError('Could not mark this message as read. Refresh the inbox.')

def inbox_trash_many(cfg, secret, items):
    if not items:return
    if any(item.get('folder','INBOX')!='INBOX' or item['validity']!=items[0]['validity'] for item in items):
        raise ValueError('Move messages from the same Inbox only.')
    folder=trash_folder(cfg)
    target='"'+folder.replace('\\','\\\\').replace('"','\\"')+'"'
    with inbox_connection(cfg,secret,items[0]['validity'],writable=True) as (client,_,__):
        typ,data=client.capability()
        if typ!='OK' or b'MOVE' not in b' '.join(data).upper().split():
            raise ValueError('This server does not support moving mail to Trash.')
        # Keep one authenticated connection; acknowledge each UID separately.
        for item in items:
            typ,_=client.uid('MOVE',item['uid'],target)
            if typ!='OK':raise ValueError('Could not move this message to Trash. Refresh before retrying.')
            yield item

def inbox_trash(cfg, secret, item):
    for _ in inbox_trash_many(cfg,secret,[item]):pass

def trash_folder(cfg):
    folder=cfg.get('trash_folder','')
    if not isinstance(folder,str) or not folder or folder.casefold() in ('inbox',cfg.get('sent_folder','').casefold()) or any(c in folder for c in '\r\n\x00'):
        raise ValueError('Configure a separate trash_folder for '+account_label(cfg)+'.')
    return folder

def mailbox_uids(client):
    typ,data=client.uid('SEARCH',None,'ALL')
    if typ!='OK' or not data or not isinstance(data[0],bytes):raise ValueError('Cannot list Trash messages.')
    uids=data[0].decode('ascii').split()
    if any(not re.fullmatch(r'[1-9][0-9]*',uid) for uid in uids):raise ValueError('Invalid Trash message identity.')
    return sorted(set(uids),key=int)

def require_uid_expunge(client):
    typ,data=client.capability()
    capabilities=b' '.join(data or []).upper().split()
    if typ!='OK' or not any(cap in capabilities for cap in (b'UIDPLUS',b'IMAP4REV2')):
        raise ValueError('This server cannot empty only the confirmed messages (UID EXPUNGE required).')

def prepare_empty_trash(cfg):
    def inspect(account):
        folder=trash_folder(account)
        with inbox_connection(account,password(account),folder=folder) as (client,validity,_):
            require_uid_expunge(client)
            return dict(account=account,folder=folder,validity=validity,uids=mailbox_uids(client))
    with ThreadPoolExecutor(max_workers=min(3,len(configured_accounts(cfg)))) as pool:
        return list(pool.map(inspect,configured_accounts(cfg)))

def empty_trash_account(target):
    cfg=target['account'];folder=trash_folder(cfg)
    if folder!=target['folder']:raise ValueError('Trash folder changed. Review it again.')
    uids=target['uids']
    if any(not isinstance(uid,str) or not re.fullmatch(r'[1-9][0-9]*',uid) for uid in uids):raise ValueError('Invalid confirmed message identity.')
    if not uids:return 0
    with inbox_connection(cfg,password(cfg),target['validity'],writable=True,folder=folder) as (client,_,__):
        require_uid_expunge(client)
        current=set(mailbox_uids(client));selected=[uid for uid in uids if uid in current]
        for offset in range(0,len(selected),200):
            sequence=','.join(selected[offset:offset+200])
            typ,_=client.uid('STORE',sequence,'+FLAGS.SILENT',r'(\Deleted)')
            if typ!='OK':raise ValueError('Could not mark the confirmed Trash messages for deletion.')
            typ,_=client.uid('EXPUNGE',sequence)
            if typ!='OK':raise ValueError('Could not permanently remove the confirmed Trash messages. Refresh before retrying.')
        remaining=set(mailbox_uids(client))
        if remaining.intersection(selected):raise ValueError('Some confirmed Trash messages remain. Refresh before retrying.')
        return len(selected)

def empty_trash_plan(plan):
    removed=0;errors=[]
    for target in plan:
        try:removed+=empty_trash_account(target)
        except Exception as error:errors.append(account_label(target['account'])+': '+str(error))
    return removed,errors

def restore_trash(cfg,secret,item):
    folder=trash_folder(cfg)
    if item.get('folder')!=folder:raise ValueError('Restore messages from the configured Trash folder only.')
    if not re.fullmatch(r'[1-9][0-9]*',str(item['uid'])):raise ValueError('Invalid message identity.')
    with inbox_connection(cfg,secret,item['validity'],writable=True,folder=folder) as (client,_,__):
        typ,data=client.capability()
        if typ!='OK' or b'MOVE' not in b' '.join(data or []).upper().split():raise ValueError('This server cannot move messages back to Inbox.')
        typ,_=client.uid('MOVE',item['uid'],'INBOX')
        if typ!='OK':raise ValueError('Could not restore this message to Inbox.')


def reply_draft(message,account=None):
    subject=message['subject']
    if not subject.lower().startswith('re:'): subject='Re: '+subject
    quote='\n'.join('> '+line for line in message['text'][:12000].splitlines())
    return dict(recipient=message['recipient'],subject=subject,
        body='\n\nKind regards,\n'+(account.get('display_name',account['username']) if account else 'Dive Point')+'\n\n'+message['sender']+' wrote:\n'+quote,
        **({'account':account['username']} if account else {}))

def search_text(text):
    return ''.join(c for c in unicodedata.normalize('NFKD',text.casefold())
                   if not unicodedata.combining(c))

def fuzzy_match(query,text):
    # Every word must match in order within the text; words may be rearranged.
    # This is a local header filter, with no index, service or mail-body downloads.
    text=search_text(text)
    for word in search_text(query).split():
        position=0
        for char in word:
            position=text.find(char,position)
            if position<0: return False
            position+=1
    return True

def inbox_view(window,cfg,compose):
    from gi.repository import Gtk,GLib,Gdk,Pango
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    for method in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'): getattr(box,method)(14)
    toolbar=Gtk.Box(spacing=8); box.append(toolbar)
    accounts=configured_accounts(cfg)
    title=Gtk.Label(label='Inbox · '+(str(len(accounts))+' accounts' if len(accounts)>1 else cfg['username']),xalign=0,hexpand=True);toolbar.append(title)
    folder_button=Gtk.Button(label='Sent · s');folder_button.set_tooltip_text('Switch between Inbox and Sent');toolbar.append(folder_button)
    trash_view=Gtk.Button(label='Trash · t');toolbar.append(trash_view)
    refresh=Gtk.Button(label='Refresh'); compose_button=Gtk.Button(label='Compose · n')
    toolbar.append(refresh); toolbar.append(compose_button)
    account_button=Gtk.Button(label='Accounts · a'); account_button.set_name('mail-accounts')
    account_button.connect('clicked',lambda _:open_account_setup()); toolbar.append(account_button)
    confirmation=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8,visible=False);confirmation.set_name('trash-confirmation');box.append(confirmation)
    warning=Gtk.Label(xalign=0,wrap=True);confirmation.append(warning)
    confirm_actions=Gtk.Box(spacing=8);confirmation.append(confirm_actions)
    cancel_empty=Gtk.Button(label='Cancel · n / Esc');cancel_empty.set_name('cancel-empty-trash');confirm_actions.append(cancel_empty)
    confirm_empty=Gtk.Button(label='Permanently empty Trash · y');confirm_empty.set_name('empty-trash-confirm');confirm_empty.add_css_class('destructive-action');confirm_actions.append(confirm_empty)
    search_bar=Gtk.Box(spacing=8,visible=False); box.append(search_bar)
    search=Gtk.SearchEntry(hexpand=True,placeholder_text='Search loaded mail · subject, sender, account, date')
    search.set_tooltip_text('/ search · Enter results · ↑/↓ choose · Ctrl+U clear · Esc hide')
    matches=Gtk.Label(xalign=1)
    search_bar.append(search); search_bar.append(matches)
    account_errors=Gtk.Label(xalign=0,wrap=True,selectable=True,visible=False); box.append(account_errors)
    split=Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL,vexpand=True); split.set_position(330); box.append(split)
    listing=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    listing.add_css_class('simplemail-inbox')
    # Distinguish unread subjects by bold gold text; highlight selection separately.
    selection_css=Gtk.CssProvider()
    css=''
    for index,account in enumerate(accounts):
        color=account.get('color',ACCOUNT_COLORS[index%len(ACCOUNT_COLORS)])
        if not re.fullmatch(r'#[0-9a-fA-F]{6}',color): color=ACCOUNT_COLORS[0]
        css+=f'.simplemail-inbox .simplemail-account-{index} {{ background-color: {color}; }}\n'
    selection_css.load_from_data(css.encode())
    # gtk-4.0/gtk.css imports a theme at USER priority, which hid our previous outline.
    # Override it only for these Simplemail classes.
    Gtk.StyleContext.add_provider_for_display(window.get_display(),selection_css,Gtk.STYLE_PROVIDER_PRIORITY_USER+1)
    empty=Gtk.Label(label='No messages loaded.'); listing.set_placeholder(empty)
    listing.set_filter_func(lambda row:row.matches)
    left=Gtk.ScrolledWindow(min_content_width=260); left.set_child(listing); split.set_start_child(left)
    right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); right.set_margin_start(12); split.set_end_child(right)
    heading=Gtk.Label(label='Select a message',xalign=0,wrap=True,selectable=True)
    right.append(heading)
    actions=Gtk.Box(spacing=8); right.append(actions)
    reply=Gtk.Button(label='Reply',sensitive=False); mark=Gtk.Button(label='Mark as read',sensitive=False)
    trash=Gtk.Button(label='Trash · x',sensitive=False)
    urls=Gtk.Button(label='URLs · o',sensitive=False); images=Gtk.Button(label='Images · i',sensitive=False)
    actions.append(reply); actions.append(mark); actions.append(trash); actions.append(urls); actions.append(images)
    restore=Gtk.Button(label='Restore · u',visible=False);actions.append(restore)
    empty_trash=Gtk.Button(label='Empty Trash · Shift+E',visible=False);actions.append(empty_trash)
    body=Gtk.TextView(editable=False,cursor_visible=False,accepts_tab=False,wrap_mode=Gtk.WrapMode.WORD_CHAR)
    scroll=Gtk.ScrolledWindow(vexpand=True); scroll.set_child(body)
    reader=Gtk.Stack(vexpand=True); reader.add_named(scroll,'message'); right.append(reader)
    media=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8)
    resources=Gtk.ListBox(selection_mode=Gtk.SelectionMode.SINGLE)
    resource_scroll=Gtk.ScrolledWindow(min_content_height=100,vexpand=True)
    resource_scroll.set_child(resources); media.append(resource_scroll)
    picture=Gtk.Picture(can_shrink=True,height_request=180); media.append(picture); picture.set_visible(False)
    detail=Gtk.Label(xalign=0,wrap=True,selectable=True); media.append(detail)
    resource_actions=Gtk.Box(spacing=8); media.append(resource_actions)
    resource_back=Gtk.Button(label='Inbox · h'); resource_open=Gtk.Button(label='Open · Enter',sensitive=False)
    resource_actions.append(resource_back); resource_actions.append(resource_open)
    resource_hints=Gtk.Label(xalign=0); media.append(resource_hints)
    reader.add_named(media,'resources')
    status=Gtk.Label(xalign=0,wrap=True); box.append(status)
    hints=Gtk.Label(label='s Inbox/Sent · t Trash · / search · j/k · l/Enter · h back · Esc hide · o URLs · i images · r reply · n compose · R refresh · Space select · x trash',xalign=0,wrap=False,ellipsize=Pango.EllipsizeMode.END)
    hints.set_tooltip_text('s switches Inbox/Sent · t Trash · u restore from Trash · Shift+E empty Trash (confirmation) · / fuzzy search loaded mail · Enter results · Ctrl+U clears search · j/k preview or scroll · l/Enter read · h back · Esc hide · o URLs · i images · gg/G first/last · Ctrl+d/u half page · Tab next control · r reply · n compose · Shift+R refresh · m mark read · Space toggle selection in list · x trash selected/current · Esc clear selection')
    hints.add_css_class('dim-label'); box.append(hints)
    state={'trash_plan':None,'folder':'inbox','closed':False,'busy':False,'row':None,'message':None,
           'generation':0,'timer':None,'pending':None,'fetching':False,'g':False,
           'media_mode':None,'image_loading':False,'image_row':None,'image_pending':None,'image_open':None,'media_serial':0,
           'prefetch':[],'prefetching':False,'prefetch_timer':None,
           'checking':False,'poll_timer':None,'revision':0,'marked':set(),'d':False,'d_held':False}
    notices=NewMailNotifications()
    def cancel_preview():
        state['generation']+=1; state['pending']=None
        if state['timer'] is not None:
            GLib.source_remove(state['timer']); state['timer']=None
    def close(*_):
        if state['closed']: return False
        Gtk.StyleContext.remove_provider_for_display(window.get_display(),selection_css)
        state['closed']=True; state['prefetch']=[]; cancel_preview()
        if state['poll_timer'] is not None: GLib.source_remove(state['poll_timer']); state['poll_timer']=None
        if state['prefetch_timer'] is not None: GLib.source_remove(state['prefetch_timer']); state['prefetch_timer']=None
        return False
    close_handler=window.connect('close-request',close)
    def dispose():
        close(); window.disconnect(close_handler)
    box.dispose=dispose
    box.can_reload=lambda:not state['busy'] and not confirmation.get_visible()
    def sensitive(busy):
        state['busy']=busy
        cancel_empty.set_sensitive(not busy);confirm_empty.set_sensitive(not busy)
        locked=busy or confirmation.get_visible()
        for widget in (folder_button,trash_view,refresh,listing,search,compose_button,account_button):widget.set_sensitive(not locked)
        reply.set_sensitive(state['folder']=='inbox' and not locked and bool(state['message'] and state['message']['recipient']))
        mark.set_sensitive(state['folder']=='inbox' and not locked and bool(state['message'] and state['row'] and state['row'].item['unread']))
        trash.set_sensitive(state['folder']=='inbox' and not locked and state['row'] is not None)
        restore.set_sensitive(state['folder']=='trash' and not locked and state['row'] is not None)
        empty_trash.set_sensitive(state['folder']=='trash' and not locked)
        urls.set_sensitive(not locked and bool(state['message'] and state['message'].get('links')))
        images.set_sensitive(not locked and bool(state['message'] and (state['message'].get('images') or state['message'].get('truncated'))))
    def clear_resources():
        state.update(media_mode=None,image_pending=None,image_open=None,media_serial=state['media_serial']+1)
        reader.set_visible_child_name('message'); picture.set_paintable(None)
        while resources.get_row_at_index(0): resources.remove(resources.get_row_at_index(0))
        resource_open.set_sensitive(False)
    def resources_back(*_):
        clear_resources(); focus_list()
    def selected_resource(_,row):
        state.update(media_serial=state['media_serial']+1,image_pending=None,image_open=None)
        picture.set_paintable(None); picture.set_visible(state['media_mode']=='images')
        resource_open.set_sensitive(row is not None)
        if row is None: detail.set_text(''); return
        item=row.item
        if state['media_mode']=='links': detail.set_text(item); return
        detail.set_text(item.get('url') or item['name'])
        if item.get('data') is not None or item.get('path'):
            state['image_pending']=row; load_image()
        else: detail.set_text((item.get('url') or item['name'])+'\nRemote image — i/Enter loads it in your viewer.')
    def load_image():
        if state['closed'] or state['image_loading'] or state['image_pending'] is None: return
        row=state['image_pending']; token=(state['generation'],state['media_serial'])
        state.update(image_pending=None,image_loading=True,image_row=row)
        detail.set_text('Loading image…')
        def run():
            try:
                path=row.item.get('path')
                if path is None or not path.exists(): path=image_file(row.item)
                else: path.touch()
                thumbnail=image_thumbnail(path); error=None
            except Exception as exc: path=None; thumbnail=None; error=str(exc)
            def finish():
                state['image_loading']=False
                if state['closed']: return False
                if token==(state['generation'],state['media_serial']) and row is resources.get_selected_row():
                    if error: detail.set_text(error)
                    else:
                        row.item['path']=path
                        picture.set_paintable(Gdk.Texture.new_for_pixbuf(thumbnail))
                        detail.set_text(row.item.get('url') or row.item['name'])
                        if state['image_open'] is row:
                            try: open_default(path)
                            except Exception as exc: detail.set_text(str(exc))
                    state['image_open']=None
                load_image(); return False
            GLib.idle_add(finish)
        threading.Thread(target=run,daemon=True).start()
    def open_resource(*_):
        row=resources.get_selected_row()
        if row is None: return
        if state['media_mode']=='links':
            try: open_default(row.item)
            except Exception as exc: detail.set_text(str(exc))
        else:
            state['image_open']=row
            if state['image_loading'] and state['image_row'] is row: return
            state['image_pending']=row; load_image()
    def show_resources(mode):
        if state['busy'] or not state['message']: return
        if state['media_mode']==mode:
            open_resource(); return
        if mode=='images' and state['message'].get('truncated') and not state['message'].get('media_loaded'):
            item=state['row'].item
            def loaded_media(message):
                message['media_loaded']=True; state['message']=message
                sensitive(False); show_resources(mode)
            work('Loading images (up to 20 MiB)…',lambda:inbox_message(message_account(cfg,item),password(message_account(cfg,item)),item,MEDIA_LIMIT),loaded_media)
            return
        clear_resources(); state['media_mode']=mode
        shortcut='o' if mode=='links' else 'i'
        resource_open.set_label('Open · '+shortcut+'/Enter')
        resource_hints.set_text('j/k choose · '+shortcut+'/Enter open · h inbox · Esc hide · l message')
        items=state['message'].get(mode,[])
        for number,item in enumerate(items,1):
            row=Gtk.ListBoxRow(); row.item=item
            label=Gtk.Label(label=f'[{number}] '+item if mode=='links' else item['name'],xalign=0,ellipsize=Pango.EllipsizeMode.END)
            for margin in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'): getattr(label,margin)(6)
            row.set_child(label); resources.append(row)
        reader.set_visible_child_name('resources')
        resources.select_row(resources.get_row_at_index(0)); resources.grab_focus()
        if not items:
            detail.set_text('Message exceeds 20 MiB; embedded images are unavailable.' if state['message'].get('truncated') else 'No '+mode+' in this message.')
    resources.connect('row-selected',selected_resource)
    resources.connect('row-activated',lambda *_:open_resource())
    resource_open.connect('clicked',open_resource); resource_back.connect('clicked',resources_back)
    urls.connect('clicked',lambda _:show_resources('links')); images.connect('clicked',lambda _:show_resources('images'))
    def work(label,operation,done):
        state['revision']+=1
        sensitive(True); status.set_text(label)
        def run():
            try: result=operation(); error=None
            except Exception as exc: result=None; error=str(exc)
            def finish():
                if state['closed']: return False
                if error: status.set_text(error)
                else: done(result)
                sensitive(False); fetch_preview(); return False
            GLib.idle_add(finish)
        threading.Thread(target=run,daemon=True).start()
    def row_title(row):
        message_state='unread' if row.item['unread'] else 'replied' if row.item.get('answered') else 'read'
        for name in ('unread','read','replied'):
            row.remove_css_class('simplemail-'+name)
        row.add_css_class('simplemail-'+message_state)
        row.title.set_text(('● ' if row.item['unread'] else '')+('↩ ' if row.item.get('answered') else '')+row.item['subject'])
        row.title.set_tooltip_text('Unread · replied' if row.item['unread'] and row.item.get('answered') else message_state.title())
    def prefetch():
        state['prefetch_timer']=None
        if state['closed'] or state['prefetching'] or not state['prefetch']: return False
        if state['fetching'] or state['busy']:
            state['prefetch_timer']=GLib.timeout_add(500,prefetch); return False
        while state['prefetch']:
            try: cached=preview_file(message_account(cfg,state['prefetch'][0]),state['prefetch'][0],MESSAGE_LIMIT).is_file()
            except (OSError,KeyError): state['prefetch']=[]; return False
            if not cached: break
            state['prefetch'].pop(0)
        if not state['prefetch']: return False
        item=state['prefetch'].pop(0); state['prefetching']=True
        def run():
            failed=False
            try: inbox_message(message_account(cfg,item),password(message_account(cfg,item)),item,parse=False)
            except Exception: failed=True
            def finish():
                state['prefetching']=False
                if state['closed']: return False
                if failed: state['prefetch']=[pending for pending in state['prefetch'] if pending.get('account')!=item.get('account')]
                if state['prefetch_timer'] is None and state['prefetch']:
                    state['prefetch_timer']=GLib.timeout_add(300,prefetch)
                return False
            GLib.idle_add(finish)
        threading.Thread(target=run,daemon=True).start()
        return False
    listing_rows=[]
    def identity(item):
        return (item.get('account'),item.get('folder','INBOX'),item['validity'],item['uid'])
    def update_marks():
        for row in listing_rows:
            active=identity(row.item) in state['marked']
            if row.batch_mark.get_active()!=active:row.batch_mark.set_active(active)
        count=len(state['marked'])
        trash.set_label(f'Trash {count} · x' if count else 'Trash · x')
        match_count()
    def toggle_mark(row):
        if state['busy'] or state['folder']!='inbox':return
        key=identity(row.item)
        if row.batch_mark.get_active():state['marked'].add(key)
        else:state['marked'].discard(key)
        update_marks()
    def visible_rows():
        return [row for row in listing_rows if row.matches]
    def match_count():
        count=len(visible_rows()); matches.set_text(f'{count}/{len(listing_rows)} loaded'+(f' · {len(state["marked"])} selected' if state['marked'] else ''))
        empty.set_text('No matching messages.' if search.get_text().strip() else 'No messages loaded.')
    def filter_changed(*_):
        query=search.get_text()
        for row in listing_rows: row.matches=fuzzy_match(query,row.search_text)
        state['marked'].intersection_update(identity(row.item) for row in visible_rows())
        update_marks()
        listing.invalidate_filter()
        current=listing.get_selected_row()
        if current is None or not current.matches:
            listing.select_row(next(iter(visible_rows()),None))
        match_count()
    search.connect('search-changed',filter_changed)
    def start_search():
        clear_resources(); search_bar.set_visible(True); search.grab_focus(); search.select_region(0,-1)
    def loaded(result,retain=False):
        messages,total,errors=result
        old=state['row'].item if retain and state['row'] else None
        if not retain:state['marked'].clear()
        state['marked'].intersection_update(identity(item) for item in messages)
        wanted=identity(old) if old else None
        old_message=state['message']
        list_had_focus=focused(listing)
        listing.handler_block_by_func(selected)
        account_errors.set_text('Unavailable accounts · '+' | '.join(errors)); account_errors.set_visible(bool(errors))
        while listing.get_first_child(): listing.remove(listing.get_first_child())
        listing_rows.clear()
        for item in messages:
            row=Gtk.ListBoxRow(); row.item=item
            content=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=3)
            for method in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'): getattr(content,method)(8)
            row.title=Gtk.Label(xalign=0,ellipsize=Pango.EllipsizeMode.END,max_width_chars=34); row_title(row)
            row.title.add_css_class('simplemail-subject'); row.title.set_hexpand(True)
            subject_line=Gtk.Box(spacing=6)
            row.batch_mark=Gtk.CheckButton(visible=state['folder']=='inbox')
            row.batch_mark.set_tooltip_text('Select message · Space')
            row.batch_mark.set_active(identity(item) in state['marked'])
            row.batch_mark.connect('toggled',lambda _,r=row:toggle_mark(r))
            subject_line.append(row.batch_mark)
            account=message_account(cfg,item)
            index=next(i for i,a in enumerate(accounts) if a['username']==account['username'])
            marker=Gtk.Box(); marker.add_css_class('simplemail-account-bar'); marker.add_css_class('simplemail-account-'+str(index))
            marker.set_tooltip_text(account_label(account)); row.set_tooltip_text(account_label(account))
            subject_line.append(marker); subject_line.append(row.title); content.append(subject_line)
            for field in ('sender','date'):
                label=Gtk.Label(label=item[field],xalign=0,ellipsize=Pango.EllipsizeMode.END,max_width_chars=34)
                label.add_css_class('dim-label')
                if field=='sender':label.add_css_class('simplemail-sender')
                content.append(label)
            row.search_text=' '.join((item['subject'],item['sender'],item['date'],account_label(account)))
            row.matches=fuzzy_match(search.get_text(),row.search_text)
            row.set_child(content); listing_rows.append(row); listing.append(row)
        update_marks()
        chosen=next((row for row in visible_rows() if identity(row.item)==wanted),None)
        if chosen is None: chosen=next(iter(visible_rows()),None)
        listing.select_row(chosen)
        listing.handler_unblock_by_func(selected)
        if chosen is not None and identity(chosen.item)==wanted:
            state.update(row=chosen,message=old_message)
            chosen.add_css_class('simplemail-selected')
            if old_message is None: selected(listing,chosen)
        else:
            state['row']=None
            selected(listing,chosen)
        listing.set_sensitive(True)
        if box.get_root() and not focused(search) and (not retain or list_had_focus):
            (chosen or listing).grab_focus()
        if not retain or state['message'] is None:
            status.set_text(f'{state["folder"].title()} · Latest {len(messages)} of {total} messages · '+('● gold bold: unread · white bold: read · ↩ normal: replied' if state['folder']=='inbox' else 'Trash · u restores · Shift+E empties after confirmation' if state['folder']=='trash' else 'Saved Sent copies · recipient shown below subject'))
        state['prefetch']=prefetch_items(messages)
        if state['prefetch_timer'] is None: state['prefetch_timer']=GLib.timeout_add(750,prefetch)
    def view_headers():
        return combined_headers(cfg,notices.observe) if state['folder']=='inbox' else combined_headers(cfg,folder=state['folder'])
    def reload(*_):
        state['prefetch']=[];state['marked'].clear();state['d']=False
        state.update(row=None,message=None); listing.unselect_all()
        heading.set_text('Select a message'); body.get_buffer().set_text('')
        account_errors.set_visible(False)
        work('Loading '+state['folder']+'…',view_headers,loaded)
    def switch_folder(*_,target=None):
        if state['busy'] or confirmation.get_visible():return
        state['folder']=target or ('inbox' if state['folder']=='sent' else 'sent')
        state['revision']+=1;cancel_preview();clear_resources()
        search.set_text('');search_bar.set_visible(False)
        title.set_text(state['folder'].title()+' · '+(str(len(accounts))+' accounts' if len(accounts)>1 else cfg['username']))
        folder_button.set_label('Inbox · s' if state['folder']=='sent' else 'Sent · s')
        trash_view.set_label('Inbox · t' if state['folder']=='trash' else 'Trash · t')
        for widget in (reply,mark,trash):widget.set_visible(state['folder']!='trash')
        restore.set_visible(state['folder']=='trash');empty_trash.set_visible(state['folder']=='trash')
        reload()
    folder_button.connect('clicked',switch_folder)
    trash_view.connect('clicked',lambda *_:switch_folder(target='inbox' if state['folder']=='trash' else 'trash'))
    def cancel_empty_trash(*_):
        if state['busy']:return
        confirmation.set_visible(False);state['trash_plan']=None;sensitive(False);focus_list()
    def escape_confirmation():
        state['d']=False
        if confirmation.get_visible():cancel_empty_trash();return True
        if state['marked']:
            state['marked'].clear();update_marks();return True
        return False
    box.handle_escape=escape_confirmation
    def request_empty(*_):
        if state['busy'] or state['folder']!='trash' or confirmation.get_visible():return
        def ready(plan):
            count=sum(len(target['uids']) for target in plan)
            if not count:status.set_text('Trash is already empty in all accounts.');return
            state['trash_plan']=plan
            warning.set_text('Permanently delete '+str(count)+' messages from Trash across these accounts? This cannot be undone.\n'+
                '\n'.join(account_label(target['account'])+' · '+target['folder']+': '+str(len(target['uids'])) for target in plan)+
                '\nThis includes all Trash messages, not just the latest 50 or search results. y confirms; n / Esc cancels.')
            confirmation.set_visible(True);GLib.idle_add(lambda:(cancel_empty.grab_focus(),False)[1])
        work('Counting Trash messages…',lambda:prepare_empty_trash(cfg),ready)
    def confirm_empty_trash(*_):
        if state['busy'] or not confirmation.get_visible() or state['trash_plan'] is None:return
        plan=state['trash_plan'];state['trash_plan']=None
        def run():
            removed,errors=empty_trash_plan(plan)
            try:rows=view_headers()
            except Exception as error:rows=None;errors.append('Refresh failed: '+str(error))
            return removed,errors,rows
        def done(result):
            removed,errors,rows=result;confirmation.set_visible(False)
            if rows is not None:loaded(rows)
            status.set_text(str(removed)+' messages permanently removed from Trash.'+('\n'+'\n'.join(errors) if errors else ''))
            focus_list()
        work('Emptying confirmed Trash messages…',run,done)
    empty_trash.connect('clicked',request_empty)
    cancel_empty.connect('clicked',cancel_empty_trash);confirm_empty.connect('clicked',confirm_empty_trash)
    def background_check():
        if state['closed']: return False
        if state['busy'] or state['checking'] or confirmation.get_visible(): return True
        state['checking']=True
        revision=state['revision'];folder=state['folder']
        def run():
            try:
                result=combined_headers(cfg,notices.observe)
                if folder!='inbox':result=combined_headers(cfg,folder=folder)
                error=None
            except Exception as exc: result=None; error=str(exc)
            def finish():
                state['checking']=False
                if state['closed']: return False
                if not state['busy'] and not confirmation.get_visible() and revision==state['revision']:
                    if error:
                        account_errors.set_text('Automatic mail check failed · '+error)
                        account_errors.set_visible(True)
                    else:
                        loaded(result,retain=True)
                        sensitive(False); fetch_preview()
                return False
            GLib.idle_add(finish)
        threading.Thread(target=run,daemon=True).start()
        return True
    def reply_sent(source):
        if not source or state['folder']!='inbox':return
        state['revision']+=1
        for row in listing_rows:
            account=message_account(cfg,row.item)
            if reply_source(account,row.item)==source:
                row.item.update(unread=False,answered=True);row_title(row)
        sensitive(False)
    box.reply_sent=reply_sent
    box.check_mail=background_check
    def selected(_,row):
        state['d']=False
        if state['row'] is not None: state['row'].remove_css_class('simplemail-selected')
        if row is not None: row.add_css_class('simplemail-selected')
        cancel_preview()
        clear_resources()
        state.update(row=row,message=None)
        body.get_buffer().set_text('')
        heading.set_text(row.item['subject']+'\n'+row.item['sender']+'\n'+account_label(message_account(cfg,row.item)) if row else 'Select a message')
        reply.set_sensitive(False); mark.set_sensitive(False); urls.set_sensitive(False); images.set_sensitive(False)
        trash.set_sensitive(state['folder']=='inbox' and not state['busy'] and row is not None)
        if row:
            status.set_text('Loading preview…')
            try: cached=preview_file(message_account(cfg,row.item),row.item,MESSAGE_LIMIT).is_file()
            except (OSError,KeyError): cached=False
            state['timer']=GLib.idle_add(queue_preview) if cached else GLib.timeout_add(180,queue_preview)
    def queue_preview():
        state['timer']=None
        if state['row'] is not None:
            state['pending']=(state['row'],state['generation'])
            fetch_preview()
        return False
    def fetch_preview():
        if state['closed'] or state['busy'] or state['fetching'] or not state['pending']: return
        row,generation=state['pending']; state.update(pending=None,fetching=True)
        def run():
            try: message=inbox_message(message_account(cfg,row.item),password(message_account(cfg,row.item)),row.item); error=None
            except Exception as exc: message=None; error=str(exc)
            def finish():
                state['fetching']=False
                if state['closed']: return False
                if generation==state['generation'] and row is state['row'] and not state['busy']:
                    if error: status.set_text(error+' · Press l or Enter to retry')
                    else:
                        state['message']=message
                        heading.set_text(message['subject']+'\n'+message['sender']+('\nTo: '+message.get('to','') if state['folder']=='sent' else '')+'\n'+message['date']+' · '+account_label(message_account(cfg,row.item)))
                        body.get_buffer().set_text(message['text'])
                        scroll.get_vadjustment().set_value(0)
                        status.set_text(message['notes'] or 'Read-only preview · h returns to the inbox list · Esc hides mail')
                    sensitive(False)
                fetch_preview(); return False
            GLib.idle_add(finish)
        threading.Thread(target=run,daemon=True).start()
    def focus_list():
        if box.get_root(): (listing.get_selected_row() or listing).grab_focus()
    box.focus_list=focus_list
    def focused(widget):
        focus=window.get_focus()
        while focus:
            if focus is widget: return True
            focus=focus.get_parent()
        return False
    def opened(_,row):
        if row is None or state['busy']: return
        if row is not listing.get_selected_row(): listing.select_row(row)
        body.grab_focus()
        if state['message'] is None and not state['fetching'] and state['timer'] is None:
            status.set_text('Loading preview…'); queue_preview()
    def marked(_):
        row=state['row']
        def done(_): row.item['unread']=False; row_title(row); status.set_text('Marked as read.')
        work('Marking as read…',lambda:inbox_mark_read(message_account(cfg,row.item),password(message_account(cfg,row.item)),row.item),done)
    def trashed(_):
        row=state['row']
        if row is None or state['busy'] or state['folder']!='inbox':return
        targets=[r for r in visible_rows() if identity(r.item) in state['marked']] if state['marked'] else [row]
        if not targets:return
        cancel_preview();state['d']=False
        index=visible_rows().index(row)
        def progress(count):
            if not state['closed']:
                trash.set_label(f'Moving {count}/{len(targets)}…')
                status.set_text(f'Moving to Trash: {count}/{len(targets)} confirmed. Waiting for mail server…')
            return False
        def operation():
            completed=[];error=None;groups={}
            for target in targets:
                account=message_account(cfg,target.item)
                groups.setdefault((account['username'],target.item['validity']),[]).append(target)
            for group in groups.values():
                try:
                    account=message_account(cfg,group[0].item)
                    rows={id(r.item):r for r in group}
                    for item in inbox_trash_many(account,password(account),[r.item for r in group]):
                        completed.append(rows[id(item)])
                        GLib.idle_add(progress,len(completed))
                except Exception as exc:
                    error=str(exc);break
            return completed,error
        def done(result):
            completed,error=result
            listing.handler_block_by_func(selected)
            for target in completed:
                state['marked'].discard(identity(target.item))
                listing_rows.remove(target);listing.remove(target)
            remaining=visible_rows()
            next_row=row if row in remaining else remaining[min(index,len(remaining)-1)] if remaining else None
            listing.select_row(next_row);listing.handler_unblock_by_func(selected)
            selected(listing,next_row);update_marks()
            GLib.idle_add(lambda:(focus_list(),False)[1])
            text=f'Moved {len(completed)} message'+('' if len(completed)==1 else 's')+' to Trash.'
            if error:text+=' Stopped: '+error+' Remaining selections kept; refresh before retrying if server status is uncertain.'
            status.set_text(text)
        progress(0)
        work(f'Moving {len(targets)} messages to Trash…',operation,done)
    def restored(*_):
        row=state['row']
        if state['busy'] or state['folder']!='trash' or row is None:return
        def done(_):
            listing_rows.remove(row);listing.remove(row);match_count()
            remaining=visible_rows();listing.select_row(remaining[0] if remaining else None)
            status.set_text('Restored to Inbox.');focus_list()
        work('Restoring message…',lambda:restore_trash(message_account(cfg,row.item),password(message_account(cfg,row.item)),row.item),done)
    restore.connect('clicked',restored)
    def replying(*_):
        if state['folder']!='inbox':return
        row=listing.get_selected_row()
        if state['busy'] or row is None or row is not state['row'] or not state['message'] or not state['message']['recipient']: return
        account=message_account(cfg,row.item)
        draft=reply_draft(state['message'],account)
        draft['_reply_source']=reply_source(account,row.item)
        # Keep an unsent reply associated with its actual mailbox and message,
        # including when different accounts happen to use the same IMAP UID.
        identity=(account['imap_host'],account['imap_port'],account['username'],str(row.item['validity']),row.item['uid'])
        draft['_reply_id']=hashlib.sha256(json.dumps(identity).encode()).hexdigest()
        compose(draft)
    listing.connect('row-selected',selected); listing.connect('row-activated',opened)
    refresh.connect('clicked',reload)
    compose_button.connect('clicked',lambda _:compose()); reply.connect('clicked',replying)
    mark.connect('clicked',marked)
    trash.connect('clicked',trashed)
    keys=Gtk.EventControllerKey()
    def move_selection(offset,focus=True):
        available=visible_rows()
        if not available: return
        current=listing.get_selected_row()
        index=available.index(current) if current in available else 0
        row=available[max(0,min(index+offset,len(available)-1))]
        listing.select_row(row)
        if focus: row.grab_focus()
    def scroll_by(distance):
        adjustment=scroll.get_vadjustment()
        adjustment.set_value(max(adjustment.get_lower(),min(adjustment.get_value()+distance,
            adjustment.get_upper()-adjustment.get_page_size())))
    def key_pressed(_,keyval,keycode,modifiers):
        modifiers=modifiers & Gtk.accelerator_get_default_mod_mask()
        if keyval==Gdk.KEY_x and not modifiers and state.get('x_held'):return True
        previous_g=state['g']; state['g']=False
        if confirmation.get_visible():
            if not modifiers and keyval==Gdk.KEY_y:confirm_empty_trash();return True
            if not modifiers and keyval in (Gdk.KEY_n,Gdk.KEY_Escape):cancel_empty_trash();return True
            return keyval not in (Gdk.KEY_Tab,Gdk.KEY_ISO_Left_Tab,Gdk.KEY_Return,Gdk.KEY_KP_Enter,Gdk.KEY_space)
        if focused(search):
            if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter):
                filter_changed(); focus_list()
                if not search.get_text(): search_bar.set_visible(False)
                return True
            if modifiers==Gdk.ModifierType.CONTROL_MASK and keyval==Gdk.KEY_u:
                search.set_text(''); filter_changed(); return True
            if keyval in (Gdk.KEY_Down,Gdk.KEY_Up) or (modifiers==Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_j,Gdk.KEY_k)):
                filter_changed(); move_selection(1 if keyval in (Gdk.KEY_Down,Gdk.KEY_j) else -1,focus=False); return True
            return False
        if keyval==Gdk.KEY_t and modifiers==0:
            switch_folder(target='inbox' if state['folder']=='trash' else 'trash');return True
        if state['folder']=='trash':
            if keyval==Gdk.KEY_u and modifiers==0:restored();return True
            if keyval==Gdk.KEY_E and modifiers==Gdk.ModifierType.SHIFT_MASK:request_empty();return True
        if keyval==Gdk.KEY_s and modifiers==0:
            switch_folder();return True
        if keyval==Gdk.KEY_slash and modifiers in (0,Gdk.ModifierType.SHIFT_MASK):
            if not state['busy']: start_search()
            return True
        if state['media_mode'] is not None:
            if keyval==Gdk.KEY_h: resources_back(); return True
            if keyval==Gdk.KEY_l and modifiers==0:
                clear_resources(); body.grab_focus(); return True
            if focused(media):
                if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and focused(resources): open_resource(); return True
                current=resources.get_selected_row(); index=current.get_index() if current else 0
                if keyval in (Gdk.KEY_j,Gdk.KEY_k,Gdk.KEY_Down,Gdk.KEY_Up,Gdk.KEY_g,Gdk.KEY_G):
                    if keyval==Gdk.KEY_g and not previous_g: state['g']=True; return True
                    target=0 if keyval==Gdk.KEY_g else 100 if keyval==Gdk.KEY_G else max(0,index+(1 if keyval in (Gdk.KEY_j,Gdk.KEY_Down) else -1))
                    row=resources.get_row_at_index(target)
                    while row is None and target: target-=1; row=resources.get_row_at_index(target)
                    if row: resources.select_row(row); row.grab_focus()
                    return True
                if modifiers==Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_d,Gdk.KEY_u):
                    adjustment=resource_scroll.get_vadjustment()
                    adjustment.set_value(max(0,min(adjustment.get_value()+(1 if keyval==Gdk.KEY_d else -1)*adjustment.get_page_size()/2,adjustment.get_upper()-adjustment.get_page_size())))
                    return True
        if modifiers==Gdk.ModifierType.CONTROL_MASK and keyval in (Gdk.KEY_d,Gdk.KEY_u):
            direction=1 if keyval==Gdk.KEY_d else -1
            if focused(body): scroll_by(direction*scroll.get_vadjustment().get_page_size()/2)
            elif not state['busy']:
                row=listing.get_selected_row()
                if row: move_selection(direction*max(1,int(left.get_vadjustment().get_page_size()/max(1,row.get_height())/2)))
            return True
        if modifiers not in (0,Gdk.ModifierType.SHIFT_MASK): return False
        if keyval==Gdk.KEY_h: focus_list(); return True
        if keyval==Gdk.KEY_n: compose(); return True
        if keyval==Gdk.KEY_a and modifiers==0: open_account_setup(); return True
        if state['busy']: return keyval in (Gdk.KEY_x,Gdk.KEY_space,Gdk.KEY_Delete,Gdk.KEY_KP_Delete)
        if keyval in (Gdk.KEY_o,Gdk.KEY_i): show_resources('links' if keyval==Gdk.KEY_o else 'images'); return True
        if keyval in (Gdk.KEY_g,Gdk.KEY_G):
            if keyval==Gdk.KEY_g and not previous_g: state['g']=True; return True
            if focused(body):
                adjustment=scroll.get_vadjustment()
                adjustment.set_value(adjustment.get_lower() if keyval==Gdk.KEY_g else max(adjustment.get_lower(),adjustment.get_upper()-adjustment.get_page_size()))
            else: move_selection(-INBOX_LIMIT if keyval==Gdk.KEY_g else INBOX_LIMIT)
            return True
        if keyval==Gdk.KEY_Escape and not modifiers and state['marked']:
            state['marked'].clear();update_marks();return True
        if keyval==Gdk.KEY_space and not modifiers and focused(listing) and state['folder']=='inbox':
            row=listing.get_selected_row()
            if row:row.batch_mark.set_active(not row.batch_mark.get_active());move_selection(1)
            return True
        if keyval==Gdk.KEY_x and not modifiers and (focused(listing) or focused(body)):
            if not state.get('x_held'):
                state['x_held']=True
                if trash.get_sensitive():trashed(trash)
            return True
        if keyval in (Gdk.KEY_Delete,Gdk.KEY_KP_Delete):return True
        if focused(body) and keyval in (Gdk.KEY_j,Gdk.KEY_k,Gdk.KEY_Down,Gdk.KEY_Up,Gdk.KEY_Page_Down,Gdk.KEY_Page_Up,Gdk.KEY_space,Gdk.KEY_Home,Gdk.KEY_End):
            adjustment=scroll.get_vadjustment()
            if keyval==Gdk.KEY_Home: value=adjustment.get_lower()
            elif keyval==Gdk.KEY_End: value=adjustment.get_upper()-adjustment.get_page_size()
            else:
                page=keyval in (Gdk.KEY_Page_Down,Gdk.KEY_Page_Up,Gdk.KEY_space)
                backwards=keyval in (Gdk.KEY_k,Gdk.KEY_Up,Gdk.KEY_Page_Up) or (keyval==Gdk.KEY_space and modifiers)
                value=adjustment.get_value()+(-1 if backwards else 1)*(adjustment.get_page_size()*0.9 if page else 40)
            adjustment.set_value(max(adjustment.get_lower(),min(value,adjustment.get_upper()-adjustment.get_page_size())))
            return True
        if keyval in (Gdk.KEY_j,Gdk.KEY_k) or (focused(listing) and keyval in (Gdk.KEY_Down,Gdk.KEY_Up)):
            move_selection(1 if keyval in (Gdk.KEY_j,Gdk.KEY_Down) else -1)
            return True
        if keyval==Gdk.KEY_l or (keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and (focused(listing) or focused(body))):
            opened(listing,listing.get_selected_row()); return True
        if keyval==Gdk.KEY_R: reload(); return True
        if keyval==Gdk.KEY_r:
            if reply.get_sensitive(): replying()
            return True
        if keyval==Gdk.KEY_m and mark.get_sensitive(): marked(mark); return True
        return False
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    def key_released(_,keyval,keycode,modifiers):
        if keyval==Gdk.KEY_x:state['x_held']=False
    keys.connect('key-released',key_released)
    keys.connect('key-pressed',key_pressed); box.add_controller(keys)
    state['poll_timer']=GLib.timeout_add_seconds(MAIL_CHECK_SECONDS,background_check)
    return box,reload,compose_button

def edit_body(text):
    editor=shlex.split(os.environ.get('VISUAL') or os.environ.get('EDITOR') or 'nvim')
    if not editor or not shutil.which(editor[0]) or not shutil.which('simple-open'):
        raise ValueError('Install simple-open and your editor (default: nvim) to edit externally.')
    folder=Path(tempfile.mkdtemp(prefix='simplemail-'))
    path=folder/'message.txt'; path.write_text(text,encoding='utf-8'); path.chmod(0o600)
    try:
        result=subprocess.run(['simple-open','terminal',*editor,str(path)])
        if result.returncode: raise ValueError(f'Editor exited with status {result.returncode}')
        edited=path.read_text(encoding='utf-8')
    except Exception as exc:
        raise ValueError(f'{exc}. Inline draft kept; editor file is at {path}') from exc
    shutil.rmtree(folder)
    return edited

class ComposeInsertEscape:
    """Match the user's Neovim insert-mode jk mapping (timeoutlen=400)."""
    def __init__(self,body,normal):
        from gi.repository import GLib
        self.GLib=GLib;self.buffer=body.get_buffer();self.normal=normal
        self.source=None;self.marks=None;self.deadline=0

    def take(self):
        if self.source is not None:self.GLib.source_remove(self.source);self.source=None
        if self.marks is None:return None
        marks=self.marks;self.marks=None
        start,end=(self.buffer.get_iter_at_mark(mark).get_offset() for mark in marks)
        for mark in marks:self.buffer.delete_mark(mark)
        return start,end

    def flush(self):
        span=self.take()
        if span is None:return
        start,end=span
        self.buffer.begin_user_action()
        try:
            self.buffer.delete(self.buffer.get_iter_at_offset(start),self.buffer.get_iter_at_offset(end))
            point=self.buffer.get_iter_at_offset(start);self.buffer.insert(point,'j');self.buffer.place_cursor(point)
        finally:self.buffer.end_user_action()

    def key(self,char):
        if self.marks is not None:
            if char=='k' and self.GLib.get_monotonic_time()<=self.deadline:
                self.take();self.normal();return True
            self.flush()
        if char!='j':return False
        bounds=self.buffer.get_selection_bounds()
        if not bounds:
            point=self.buffer.get_iter_at_mark(self.buffer.get_insert());bounds=(point,point)
        self.marks=(self.buffer.create_mark(None,bounds[0],True),self.buffer.create_mark(None,bounds[1],False))
        self.deadline=self.GLib.get_monotonic_time()+400000
        def expired():
            self.source=None;self.flush();return False
        self.source=self.GLib.timeout_add(400,expired)
        return True


class ComposeVim:
    """Small normal-mode editing layer for the inline message body."""
    def __init__(self,body,insert):
        self.body=body; self.buffer=body.get_buffer(); self.insert=insert
        self.pending=''; self.register=''; self.linewise=False; self.search_query=''
        self.buffer.set_enable_undo(True); self.buffer.set_max_undo_levels(100)

    def reset(self): self.pending=''

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(),self.buffer.get_end_iter(),True)

    def position(self): return self.buffer.get_iter_at_mark(self.buffer.get_insert()).get_offset()

    def move(self,offset):
        self.buffer.place_cursor(self.buffer.get_iter_at_offset(max(0,min(len(self.text()),offset))))
        self.body.scroll_mark_onscreen(self.buffer.get_insert())

    @staticmethod
    def kind(char): return 0 if char.isspace() else 1 if char.isalnum() or char=='_' else 2

    def bounds(self,text,pos):
        start=text.rfind('\n',0,pos)+1; end=text.find('\n',pos)
        return start,len(text) if end<0 else end

    def motion(self,key,text,pos):
        start,end=self.bounds(text,pos); size=len(text)
        if key=='h': return max(start,pos-1)
        if key=='l': return min(max(start,end-1),pos+1)
        if key=='0': return start
        if key=='^': return start+len(text[start:end])-len(text[start:end].lstrip())
        if key=='$': return max(start,end-1)
        if key=='G':
            start=text.rfind('\n')+1
            return start+len(text[start:])-len(text[start:].lstrip())
        if key=='w':
            if pos<size:
                kind=self.kind(text[pos])
                while pos<size and self.kind(text[pos])==kind:pos+=1
            while pos<size and text[pos].isspace():pos+=1
            return pos
        if key=='b':
            pos=max(0,pos-1)
            while pos>0 and text[pos].isspace():pos-=1
            if pos<size:
                kind=self.kind(text[pos])
                while pos>0 and self.kind(text[pos-1])==kind:pos-=1
            return pos
        if key=='e':
            pos=min(size,pos+1)
            while pos<size and text[pos].isspace():pos+=1
            if pos<size:
                kind=self.kind(text[pos])
                while pos+1<size and self.kind(text[pos+1])==kind:pos+=1
            return pos
        return None

    def replace(self,start,end,value=''):
        self.buffer.begin_user_action()
        try:
            self.buffer.delete(self.buffer.get_iter_at_offset(start),self.buffer.get_iter_at_offset(end))
            self.buffer.insert(self.buffer.get_iter_at_offset(start),value)
        finally:self.buffer.end_user_action()
        self.move(start)

    def edit_range(self,op,start,end,linewise=False):
        text=self.text(); self.register=text[start:end]; self.linewise=linewise
        if linewise and not self.register.endswith('\n'):self.register+='\n'
        if op=='y':return
        delete_start=start
        if linewise and op=='d' and end==len(text) and start>0 and (not text.endswith('\n') or start==end):
            delete_start-=1
        self.replace(delete_start,end)
        if op=='c':self.insert()

    def scroll(self,fraction):
        parent=self.body.get_parent()
        adjustment=parent.get_vadjustment()
        delta=adjustment.get_page_size()*fraction
        adjustment.set_value(max(adjustment.get_lower(),min(
            adjustment.get_upper()-adjustment.get_page_size(),adjustment.get_value()+delta)))

    def search(self,query=None,backward=False):
        if query:self.search_query=query
        if not self.search_query:return False
        flags=0 if any(c.isupper() for c in self.search_query) else re.IGNORECASE
        matches=list(re.finditer(re.escape(self.search_query),self.text(),flags))
        if not matches:return False
        pos=self.position()
        if backward:match=next((m for m in reversed(matches) if m.start()<pos),matches[-1])
        else:match=next((m for m in matches if m.start()>pos),matches[0])
        self.buffer.select_range(self.buffer.get_iter_at_offset(match.start()),self.buffer.get_iter_at_offset(match.end()))
        self.body.scroll_mark_onscreen(self.buffer.get_insert())
        return True

    def key(self,key):
        text=self.text(); pos=self.position(); start,end=self.bounds(text,pos)
        pending=self.pending; self.pending=''
        if pending=='g':
            if key=='g':self.move(0)
            return True
        if pending=='r':
            if len(key)==1 and key.isprintable() and pos<end:self.replace(pos,pos+1,key)
            return True
        if pending in ('c','d','y'):
            if key==pending:
                self.edit_range(pending,start,end if pending=='c' else min(len(text),end+1),pending!='c')
            elif key in ('w','e','b','0','^','$'):
                if pending=='c' and key=='w' and pos<len(text) and not text[pos].isspace():
                    target=pos+1
                    while target<len(text) and self.kind(text[target])==self.kind(text[pos]):target+=1
                else:
                    target=self.motion(key,text,pos)
                    if key in ('e','$') and target<len(text):target+=1
                    # dw at a line's last word leaves the following line intact.
                    if key=='w' and pos<end and target>end:target=end
                self.edit_range(pending,min(pos,target),max(pos,target))
            return True
        if key in ('g','c','d','y','r'):
            self.pending=key;return True
        target=self.motion(key,text,pos)
        if target is not None:self.move(target);return True
        if key in ('i','a','A','I'):
            if key=='a':self.move(min(end,pos+1))
            elif key=='A':self.move(end)
            elif key=='I':self.move(self.motion('^',text,pos))
            self.insert();return True
        if key in ('o','O'):
            point=end if key=='o' else start
            self.replace(point,point,'\n');self.move(point+1 if key=='o' else point)
            self.insert();return True
        if key in ('x','X','D','C'):
            left=max(start,pos-1) if key=='X' else pos
            right=pos if key=='X' else end if key in ('D','C') else min(end,pos+1)
            self.edit_range('c' if key=='C' else 'd',left,right);return True
        if key in ('p','P'):
            if not self.register:return True
            if self.linewise:
                if key=='P':point=start;value=self.register;cursor=point
                elif end<len(text):point=end+1;value=self.register;cursor=point
                else:point=end;value='\n'+self.register.rstrip('\n');cursor=point+1
            else:
                point=pos if key=='P' else min(end,pos+1)
                value=self.register;cursor=point+max(0,len(value)-1)
            self.replace(point,point,value);self.move(cursor);return True
        if key=='u':
            if self.buffer.get_can_undo():self.buffer.undo();self.body.scroll_mark_onscreen(self.buffer.get_insert())
            return True
        return False


def compose_view(window,cfg,initial,draft,on_back,on_discard,on_sent,set_busy):
    from gi.repository import Gtk,GLib,Gdk
    attachments=draft.get('attachments',[])
    compose_record=Path(os.environ.get('XDG_STATE_HOME',Path.home()/'.local/state'))/'simplemail/outbox'/str(uuid.uuid4())
    revision_base=None
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    for method in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'): getattr(box,method)(18)
    accounts=configured_accounts(cfg)
    source=draft.get('_reply_source')
    box.reply_source=source
    reply_account=message_account(cfg,source) if source else None
    invoice=bool(initial or attachments)
    current=message_account(cfg,{'account':cfg.get('invoice_account',cfg['username'])} if invoice else draft)
    sender_line=Gtk.Box(spacing=8); sender_line.append(Gtk.Label(label='From:',xalign=0))
    sender=Gtk.DropDown.new_from_strings([account_label(account) for account in accounts])
    sender.set_selected(next(i for i,a in enumerate(accounts) if a['username']==current['username']))
    sender.set_sensitive(not invoice)
    sender.set_tooltip_text('Fixed accounting sender' if invoice else 'Sending account · Tab to select, then Space and arrow keys')
    sender.set_hexpand(True); sender_line.append(sender); box.append(sender_line)
    status=Gtk.Label(wrap=True,xalign=0,selectable=True)
    inbox=Gtk.Button(label='Inbox · Esc')
    inbox.connect('clicked',lambda _:on_back())
    toolbar=Gtk.Box(spacing=8); toolbar.append(inbox)
    discard=Gtk.Button(label='Discard draft'); discard.connect('clicked',lambda _:on_discard())
    edit=Gtk.Button(label='Edit in editor · Ctrl+e')
    toolbar.append(discard); toolbar.append(edit); box.append(toolbar)
    path=Gtk.Entry(placeholder_text='Attachment path (optional)',text=initial); box.append(path)
    if attachments:
        path.set_editable(False)
        box.append(Gtk.Label(label='Attachments: '+', '.join(Path(p).name for p in attachments),wrap=True,xalign=0))
    choose=Gtk.Button(label='Attach file… · Ctrl+o'); box.append(choose)
    def pick(_):
        dialog=Gtk.FileChooserNative(title='Choose attachment',transient_for=window,action=Gtk.FileChooserAction.OPEN)
        filt=Gtk.FileFilter(); filt.set_name('All files'); filt.add_pattern('*'); dialog.add_filter(filt)
        def response(d,r):
            if r==Gtk.ResponseType.ACCEPT:
                selected=d.get_file()
                if selected and selected.get_path(): path.set_text(selected.get_path())
            d.destroy()
        dialog.connect('response',response); dialog.show()
    choose.connect('clicked',pick)
    if attachments: choose.set_sensitive(False)
    recipient=Gtk.Entry(placeholder_text='Recipient email addresses, separated by commas',text=draft.get('recipient','')); box.append(recipient)
    subject=Gtk.Entry(placeholder_text='Subject',text=draft.get('subject','Invoice — '+Path(initial).stem if initial else '')); box.append(subject)
    def initial_body(account):
        return ('Hello,\n\nPlease find your invoice attached.\n\nKind regards,\n' if initial else 'Hello,\n\n\n\nKind regards,\n')+account.get('display_name',account['username'])
    body=Gtk.TextView(accepts_tab=False,wrap_mode=Gtk.WrapMode.WORD_CHAR); body.get_buffer().set_text(draft.get('body',initial_body(current)))
    buffer=body.get_buffer(); buffer.place_cursor(buffer.get_start_iter())
    mode={'name':'normal'}
    hint=Gtk.Label(xalign=0)
    command=Gtk.Entry(placeholder_text=':x sends · / searches the draft')
    command.set_visible(False)
    def set_mode(name,focus=False):
        insert_escape.flush()
        if mode['name']=='insert' and name=='normal':
            pos=vim.position();text=vim.text();start,_=vim.bounds(text,pos)
            vim.move(max(start,pos-1))
        mode['name']=name
        vim.reset()
        body.set_editable(name=='insert')
        hint.set_text('INSERT · jk normal · Esc inbox · Ctrl+e editor' if name=='insert' else
                      'NORMAL · hjkl/wbe · i/a · / search · :x send · Esc inbox')
        if focus: body.grab_focus()
    def escape():
        if not button.get_sensitive(): return True
        command.set_visible(False); command.set_text(''); set_mode('normal')
        on_back()
        return True
    vim=ComposeVim(body,lambda:set_mode('insert',True))
    insert_escape=ComposeInsertEscape(body,lambda:set_mode('normal',True))
    focus_keys=Gtk.EventControllerFocus()
    focus_keys.connect('leave',lambda *_:(insert_escape.flush(),vim.reset()))
    body.add_controller(focus_keys)
    box.handle_escape=escape
    def focus_compose():
        if invoice or draft.get('_reply_id'): set_mode('normal',True)
        else: recipient.grab_focus()
    box.focus_compose=focus_compose
    # Clicking the message body enables ordinary mouse-based editing.
    mouse=Gtk.GestureClick.new(); mouse.set_button(1)
    mouse.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    mouse.connect('pressed',lambda *_:set_mode('insert') if body.get_sensitive() else None)
    body.add_controller(mouse)
    set_mode('normal')
    previous={'account':current}
    def sender_changed(*_):
        buffer=body.get_buffer(); text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
        account=accounts[sender.get_selected()]
        if text==initial_body(previous['account']): buffer.set_text(initial_body(account))
        previous['account']=account
    sender.connect('notify::selected',sender_changed)
    scroll=Gtk.ScrolledWindow(vexpand=True,min_content_height=130); scroll.set_child(body); box.append(scroll)
    box.append(hint); box.append(command)
    button=Gtk.Button(label='Send mail · Ctrl+Shift+Enter'); box.append(button)
    def editing(_):
        insert_escape.flush()
        buffer=body.get_buffer(); text=buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False)
        button.set_sensitive(False); set_busy(True); status.set_text('Editing externally — save and quit the editor to return.')
        for control in (sender,inbox,discard,edit,path,choose,recipient,subject,body): control.set_sensitive(False)
        def work():
            try: edited=edit_body(text); error=None
            except Exception as exc: edited=None; error=str(exc)
            def done():
                if error: status.set_text(error)
                else: buffer.set_text(edited); status.set_text('Editor text loaded. Review before sending.')
                button.set_sensitive(True); set_busy(False)
                for control in (sender,inbox,discard,edit,path,recipient,subject,body): control.set_sensitive(True)
                sender.set_sensitive(not invoice)
                choose.set_sensitive(not attachments)
                window.present(); set_mode('normal',True)
                return False
            GLib.idle_add(done)
        threading.Thread(target=work,daemon=True).start()
    edit.connect('clicked',editing)
    def clicked(_):
        nonlocal revision_base
        if not button.get_sensitive():return
        insert_escape.flush()
        base=revision_base or (Path(path.get_text()).resolve() if invoice and path.get_text() else compose_record)
        receipt=base.with_suffix(base.suffix+'.sent.json')
        try:
            already_filed=invoice and receipt.exists() and json.loads(receipt.read_text()).get('status')=='filed'
        except (OSError,ValueError) as error:
            status.set_text(str(error));return
        if already_filed:
            # Confirm a new delivery, never remove or overwrite the earlier receipt.
            dialog=Gtk.MessageDialog(transient_for=window,modal=True,
                message_type=Gtk.MessageType.QUESTION,buttons=Gtk.ButtonsType.NONE,
                text='Send revised invoice?',
                secondary_text='An earlier invoice with this filename was already sent. Send the current PDF and draft as a new email? The original send record will be kept.')
            dialog.add_button('Cancel',Gtk.ResponseType.CANCEL)
            dialog.add_button('Send revised invoice',Gtk.ResponseType.ACCEPT)
            dialog.set_default_response(Gtk.ResponseType.CANCEL)
            button.set_sensitive(False);set_busy(True)
            def confirmed(d,response):
                nonlocal revision_base
                d.destroy();button.set_sensitive(True);set_busy(False)
                if response==Gtk.ResponseType.ACCEPT:
                    original=Path(path.get_text()).resolve()
                    revision_base=original.with_name(original.name+'.revision-'+str(uuid.uuid4()))
                    clicked(None)
            dialog.connect('response',confirmed);dialog.present()
            return
        account=current if invoice else accounts[sender.get_selected()]
        buffer=body.get_buffer(); values=(path.get_text(),recipient.get_text().strip(),subject.get_text(),buffer.get_text(buffer.get_start_iter(),buffer.get_end_iter(),False))
        button.set_sensitive(False); set_busy(True); status.set_text('Sending…')
        for control in (sender,inbox,discard,edit,path,choose,recipient,subject,body): control.set_sensitive(False)
        def work():
            completed=False;sent_pending=False
            try:
                result=send(*values,account,password(account),attachments=attachments,record_base=base,invoice=invoice,reply_to=source,reply_cfg=reply_account)
                receipt=base.with_suffix(base.suffix+'.sent.json')
                send_status=json.loads(receipt.read_text()).get('status')
                completed=send_status=='filed';sent_pending=send_status=='accepted'
            except Exception as error: result=str(error)
            def done():
                status.set_text(result); button.set_sensitive(True); set_busy(False)
                button.set_label('Retry sync · Ctrl+Shift+Enter' if sent_pending else 'Send mail · Ctrl+Shift+Enter')
                for control in (sender,inbox,discard,edit,path,recipient,subject,body): control.set_sensitive(True)
                sender.set_sensitive(not invoice)
                choose.set_sensitive(not attachments)
                if completed:
                    if shutil.which('notify-send'): subprocess.Popen(['notify-send','Simplemail',result])
                    on_sent()
            GLib.idle_add(done)
        threading.Thread(target=work,daemon=True).start()
    button.connect('clicked',clicked)
    def command_entered(entry):
        value=entry.get_text().strip()
        if value.startswith('/'):
            entry.set_visible(False); entry.set_text(''); set_mode('normal',True)
            status.set_text('Match · n next · N previous' if vim.search(value[1:]) else 'Text not found in this draft.')
        elif value==':x':
            if not button.get_sensitive(): return
            entry.set_visible(False); entry.set_text(''); set_mode('normal',True)
            clicked(button)
        else: status.set_text('Unknown command. Use :x to send, /text to search, or Esc for the inbox.')
    command.connect('activate',command_entered)
    keys=Gtk.EventControllerKey()
    def key_pressed(controller,keyval,keycode,state):
        modifiers=state & Gtk.accelerator_get_default_mod_mask()
        if keyval==Gdk.KEY_Escape and not modifiers: return escape()
        if command.get_visible() and keyval==Gdk.KEY_bracketleft and modifiers==Gdk.ModifierType.CONTROL_MASK:
            command.set_visible(False); command.set_text(''); set_mode('normal',True); return True
        focus=window.get_focus()
        in_body=focus is body or (focus is not None and focus.is_ancestor(body))
        if in_body and button.get_sensitive():
            if mode['name']=='insert':
                char=chr(Gdk.keyval_to_unicode(keyval)) if not modifiers and Gdk.keyval_to_unicode(keyval) else ''
                if insert_escape.key(char):return True
            if keyval==Gdk.KEY_bracketleft and modifiers==Gdk.ModifierType.CONTROL_MASK:
                set_mode('normal',True); return True
            if keyval==Gdk.KEY_v and modifiers==Gdk.ModifierType.CONTROL_MASK:
                set_mode('insert'); return False
            if mode['name']=='normal' and modifiers==Gdk.ModifierType.CONTROL_MASK:
                vim.reset()
                if keyval in (Gdk.KEY_d,Gdk.KEY_u,Gdk.KEY_f,Gdk.KEY_b):
                    vim.scroll({Gdk.KEY_d:.5,Gdk.KEY_u:-.5,Gdk.KEY_f:1,Gdk.KEY_b:-1}[keyval]);return True
                if keyval==Gdk.KEY_r:
                    if buffer.get_can_redo():buffer.redo();body.scroll_mark_onscreen(buffer.get_insert())
                    return True
            if mode['name']=='normal' and modifiers in (Gdk.ModifierType(0),Gdk.ModifierType.SHIFT_MASK):
                char=Gdk.keyval_to_unicode(keyval)
                if vim.pending and char:
                    vim.key(chr(char));return True
                if keyval in (Gdk.KEY_j,Gdk.KEY_k) and not modifiers:
                    vim.reset()
                    adjustment=scroll.get_vadjustment()
                    step=max(adjustment.get_step_increment(),20)
                    adjustment.set_value(max(adjustment.get_lower(),min(
                        adjustment.get_upper()-adjustment.get_page_size(),
                        adjustment.get_value()+(step if keyval==Gdk.KEY_j else -step))))
                    return True
                if keyval in (Gdk.KEY_colon,Gdk.KEY_semicolon,Gdk.KEY_slash):
                    vim.reset()
                    command.set_text('/' if keyval==Gdk.KEY_slash else ':'); command.set_visible(True); command.grab_focus(); command.set_position(-1)
                    return True
                if keyval in (Gdk.KEY_n,Gdk.KEY_N):
                    vim.reset()
                    status.set_text('Match · n next · N previous' if vim.search(backward=keyval==Gdk.KEY_N) else 'Text not found. Use / to search the draft.')
                    return True
                char=Gdk.keyval_to_unicode(keyval)
                if char and vim.key(chr(char)):return True
                vim.reset()
                # Normal mode never inserts printable characters into the draft.
                if Gdk.keyval_to_unicode(keyval): return True

        if keyval==Gdk.KEY_o and modifiers==Gdk.ModifierType.CONTROL_MASK:
            if choose.get_sensitive(): pick(choose)
            return True
        if keyval==Gdk.KEY_e and modifiers==Gdk.ModifierType.CONTROL_MASK:
            if button.get_sensitive(): editing(edit)
            return True
        if keyval in (Gdk.KEY_Return,Gdk.KEY_KP_Enter) and modifiers==(Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.SHIFT_MASK):
            if button.get_sensitive(): clicked(button)
            return True
        return False
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed',key_pressed); box.add_controller(keys)
    box.append(status)
    return box,recipient,status

def open_account_setup():
    return subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--setup'])

SETUP_FIELDS=('name','display_name','username','imap_host','imap_port','smtp_host','smtp_port','sent_folder','trash_folder','color','imap_username','smtp_username','imap_security','smtp_security')

def setup_config():
    try: raw=CONFIG.read_text()
    except FileNotFoundError: return '',{'accounts':[]}
    data=tomllib.loads(raw)
    if setup_accounts(data): account_settings(data)
    return raw,data

def setup_accounts(data):
    return data.get('accounts',[data] if data else [])

def setup_account(values):
    account={key:(value.strip() if isinstance(value,str) else value) for key,value in values.items() if key in SETUP_FIELDS}
    address=account.get('username','')
    if not re.fullmatch(r'[^\s<>@]+@[^\s<>@]+\.[^\s<>@]+',address):
        raise ValueError('Enter a complete email address.')
    account['name']=account.get('name') or address
    account['display_name']=account.get('display_name') or address
    for key in ('imap_port','smtp_port'):
        try: account[key]=int(account[key])
        except (KeyError,TypeError,ValueError): raise ValueError('Enter a valid '+key.replace('_',' ')+'.') from None
    for key in ('imap_host','smtp_host'):
        if not account.get(key) or any(c.isspace() for c in account[key]) or '://' in account[key] or '/' in account[key]:
            raise ValueError('Enter a server hostname in '+key.replace('_',' ')+', without a URL prefix.')
    if account['smtp_port']==587 and account.get('smtp_security','ssl')!='starttls':
        raise ValueError('Select STARTTLS for SMTP port 587.')
    for key in ('sent_folder','trash_folder'):
        if any(c in account.get(key,'') for c in ('\r','\n','"')):
            raise ValueError('Invalid '+key.replace('_',' ')+'.')
    return configured_accounts(account_settings({'accounts':[account]}))[0]

def toml_value(value):
    if isinstance(value,str): return json.dumps(value,ensure_ascii=False)
    if isinstance(value,bool): return 'true' if value else 'false'
    if isinstance(value,(int,float)): return repr(value)
    if isinstance(value,(datetime.datetime,datetime.date,datetime.time)): return value.isoformat()
    if isinstance(value,list): return '['+', '.join(toml_value(v) for v in value)+']'
    if isinstance(value,dict): return '{'+', '.join(json.dumps(k)+ ' = '+toml_value(v) for k,v in value.items())+'}'
    raise ValueError('Unsupported config value; edit config.toml manually.')

def account_config_text(raw,account,original=None):
    data=tomllib.loads(raw) if raw.strip() else {'accounts':[]}
    entries=setup_accounts(data)
    index=next((i for i,a in enumerate(entries) if a.get('username')==original),None) if original else None
    if original and index is None: raise ValueError('This account was removed. Reopen setup.')
    if any(i!=index and a.get('username','').casefold()==account['username'].casefold() for i,a in enumerate(entries)):
        raise ValueError('This email address already exists. Select its account to edit it.')
    if original and account['username']!=original:
        raise ValueError('Add a new account to use a different email address.')
    updated=dict(entries[index],**account) if index is not None else dict(account)
    updated.pop('accounts',None)
    fields='\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in updated.items())+'\n'
    expected=dict(data)
    expected['accounts']=[dict(a) for a in entries]
    if index is None: expected['accounts'].append(updated)
    else: expected['accounts'][index]=updated
    blocks=list(re.finditer(r'^\s*\[\[accounts\]\][ \t]*(?:#[^\n]*)?$',raw,re.M))
    if 'accounts' in data and blocks and len(blocks)==len(entries):
        if index is None: result=raw.rstrip()+'\n\n[[accounts]]\n'+fields
        else:
            begin=blocks[index].start(); end=blocks[index+1].start() if index+1<len(blocks) else len(raw)
            result=raw[:begin]+'\n[[accounts]]\n'+fields+'\n'+raw[end:]
    else:
        # Convert a legacy single-account config once; retain all account options.
        globals_={k:v for k,v in data.items() if k!='accounts'} if 'accounts' in data else {k:v for k,v in data.items() if k in ('default_account','invoice_account')}
        expected=dict(globals_,accounts=expected['accounts'])
        for a in expected['accounts']:
            for key in globals_: a.pop(key,None)
        result='\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in globals_.items())+'\n'
        for a in expected['accounts']:
            result+='\n[[accounts]]\n'+'\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in a.items())+'\n'
    parsed=tomllib.loads(result)
    if parsed!=expected: raise ValueError('Config has a custom table layout. No changes saved; edit config.toml manually.')
    account_settings(parsed)
    return result

def commit_setup_config(expected_raw,new_config,password_changes):
    """Update both private files under the same lock used by password-only setup."""
    folder=CONFIG.parent; folder.mkdir(parents=True,exist_ok=True,mode=0o700); folder.chmod(0o700)
    fd=os.open(folder/'.passwords.lock',os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    temporary=[]
    def staged(text):
        fd,path=tempfile.mkstemp(prefix='.passwords-',dir=folder); temporary.append(path)
        with os.fdopen(fd,'w') as stream:
            stream.write(text); stream.flush(); os.fsync(stream.fileno())
        return path
    with os.fdopen(fd,'w') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        current=CONFIG.read_text() if CONFIG.exists() else ''
        if current!=expected_raw: raise ValueError('Config changed. Reopen setup to keep those changes.')
        if vault_backend.enabled():
            # Account removal does not erase its saved login from the shared vault.
            changes={user:secret for user,secret in password_changes.items() if secret is not None}
            old=vault_backend.load()
            config_tmp=staged(new_config)
            try:
                vault_backend.store(changes)
                try: os.replace(config_tmp,CONFIG)
                except BaseException:
                    vault_backend.store({user:old[user] for user in changes if user in old})
                    raise
            finally:
                for path in temporary: Path(path).unlink(missing_ok=True)
            return new_config
        accounts=saved_passwords(); old_exists=password_file().exists()
        old_passwords=read_private(password_file()).decode() if old_exists else ''
        for username,secret in password_changes.items():
            if secret is None: accounts.pop(username,None)
            elif not secret: raise ValueError('Enter a password first.')
            else: accounts[username]=secret
        try:
            config_tmp=staged(new_config)
            password_tmp=staged(encode_passwords(accounts,create_key=not old_exists))
            rollback_tmp=staged(old_passwords)
            os.replace(password_tmp,password_file())
            try: os.replace(config_tmp,CONFIG)
            except BaseException:
                if old_exists: os.replace(rollback_tmp,password_file())
                else: password_file().unlink(missing_ok=True)
                raise
            fd=os.open(folder,os.O_RDONLY|os.O_DIRECTORY)
            try: os.fsync(fd)
            finally: os.close(fd)
        finally:
            for path in temporary: Path(path).unlink(missing_ok=True)
    return new_config

def save_setup_account(account,secret,original,expected_raw):
    new_config=account_config_text(expected_raw,account,original)
    return commit_setup_config(expected_raw,new_config,{account['username']:secret})

def remove_setup_account(original,replacement,expected_raw):
    data=tomllib.loads(expected_raw); accounts=setup_accounts(data)
    if not any(a['username']==original for a in accounts): raise ValueError('Account no longer exists. Reopen setup.')
    remaining=[a for a in accounts if a['username']!=original]
    default=data.get('default_account',accounts[0]['username'])
    invoice=data.get('invoice_account',default)
    if remaining and original in (default,invoice) and not any(a['username']==replacement for a in remaining):
        raise ValueError('Choose a replacement sender before removing this account.')
    globals_={k:v for k,v in data.items() if k!='accounts'} if 'accounts' in data else {}
    for key,value in (('default_account',default),('invoice_account',invoice)):
        if not remaining: globals_.pop(key,None)
        elif value==original: globals_[key]=replacement
        elif key in data: globals_[key]=value
    result='\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in globals_.items())+'\n'
    if not remaining: result+='accounts = []\n'
    for account in remaining:
        result+='\n[[accounts]]\n'+'\n'.join(json.dumps(k)+' = '+toml_value(v) for k,v in account.items())+'\n'
    parsed=tomllib.loads(result)
    if remaining: account_settings(parsed)
    return commit_setup_config(expected_raw,result,{original:None})

def setup_view(cfg,on_back,back_label='Done'):
    from gi.repository import Gtk,GLib,Gdk
    raw,data=setup_config(); accounts=setup_accounts(data)
    box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10)
    for method in ('set_margin_top','set_margin_bottom','set_margin_start','set_margin_end'): getattr(box,method)(18)
    selector=Gtk.DropDown.new_from_strings([account_label(a) for a in accounts]+['＋ Add account'])
    selector.set_name('setup-account'); selector.set_hexpand(True)
    account_actions=Gtk.Box(spacing=8); account_actions.append(selector)
    edit=Gtk.Button(label='Edit account'); edit.set_name('setup-edit'); account_actions.append(edit)
    add=Gtk.Button(label='Add account'); add.set_name('setup-add'); account_actions.append(add); box.append(account_actions)
    grid=Gtk.Grid(column_spacing=10,row_spacing=8); box.append(grid)
    fields={}
    def field(parent,row,key,label,default='',column=0,span=1):
        parent.attach(Gtk.Label(label=label,xalign=0),column,row,1,1)
        entry=Gtk.Entry(text=str(default),hexpand=True); entry.set_name('setup-'+key)
        parent.attach(entry,column+1,row,span,1); fields[key]=entry
        return entry
    field(grid,0,'username','Email',span=3)
    field(grid,1,'name','Account name',span=3)
    field(grid,2,'imap_host','IMAP server')
    field(grid,2,'imap_port','Port',993,column=2).set_width_chars(5)
    field(grid,3,'smtp_host','SMTP server')
    field(grid,3,'smtp_port','Port',465,column=2).set_width_chars(5)
    field(grid,4,'color','Account colour').set_width_chars(8)
    colour=Gtk.ColorDialogButton(dialog=Gtk.ColorDialog(title='Account colour',with_alpha=False))
    colour.set_name('setup-colour-picker'); colour.set_tooltip_text('Choose the inbox marker colour')
    grid.attach(colour,2,4,2,1)
    syncing_colour=False
    def colour_text_changed(widget):
        nonlocal syncing_colour
        if syncing_colour: return
        rgba=Gdk.RGBA()
        if re.fullmatch(r'#[0-9a-fA-F]{6}',widget.get_text()) and rgba.parse(widget.get_text()):
            syncing_colour=True; colour.set_rgba(rgba); syncing_colour=False
    def colour_chosen(*_):
        nonlocal syncing_colour
        if syncing_colour: return
        rgba=colour.get_rgba()
        syncing_colour=True
        fields['color'].set_text('#'+''.join(f'{round(v*255):02x}' for v in (rgba.red,rgba.green,rgba.blue)))
        syncing_colour=False
    fields['color'].connect('changed',colour_text_changed)
    colour.connect('notify::rgba',colour_chosen)
    security={}
    for row,protocol in enumerate(('imap','smtp'),5):
        grid.attach(Gtk.Label(label=protocol.upper()+' security',xalign=0),0,row,1,1)
        selector_security=Gtk.DropDown.new_from_strings(['SSL/TLS','STARTTLS'])
        selector_security.set_name('setup-'+protocol+'_security'); grid.attach(selector_security,1,row,3,1); security[protocol]=selector_security
    box.append(Gtk.Label(label='Encrypted connections only · Gmail settings fill in automatically.',xalign=0,wrap=True))
    advanced=Gtk.Expander(label='More settings · login usernames, sender and folders')
    detail=Gtk.Grid(column_spacing=10,row_spacing=8)
    for row,(key,label) in enumerate((('display_name','Sender name'),('sent_folder','Sent folder'),('trash_folder','Trash folder'),('imap_username','IMAP login username'),('smtp_username','SMTP login username'))):
        widget=field(detail,row,key,label)
        if key.endswith('_username'): widget.set_placeholder_text('Blank uses your email address')
    advanced.set_child(detail); box.append(advanced)
    box.append(Gtk.Label(label='Password / app password',xalign=0))
    entry=Gtk.PasswordEntry(show_peek_icon=True); entry.set_name('setup-password'); box.append(entry)
    actions=Gtk.Box(spacing=10)
    button=Gtk.Button(label='Check and save'); button.set_name('setup-save'); button.add_css_class('suggested-action'); actions.append(button)
    remove=Gtk.Button(label='Remove account'); remove.set_name('setup-remove'); actions.append(remove)
    back=Gtk.Button(label=back_label); back.connect('clicked',lambda _:on_back()); actions.append(back); box.append(actions)
    importer=Gtk.Button(label='Import FairEmail backup…')
    importer.connect('clicked',lambda _:subprocess.Popen([sys.executable,str(Path(__file__).with_name('fairemail_import.py'))]))
    box.append(importer)
    status=Gtk.Label(wrap=True,xalign=0); status.set_name('setup-status'); box.append(status)
    confirmation=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8); confirmation.set_visible(False); box.append(confirmation)
    warning=Gtk.Label(wrap=True,xalign=0); confirmation.append(warning)
    replacement=Gtk.DropDown(); replacement.set_name('setup-replacement'); confirmation.append(replacement)
    confirm_actions=Gtk.Box(spacing=10); confirmation.append(confirm_actions)
    confirm_remove=Gtk.Button(label='Confirm removal'); confirm_remove.set_name('setup-confirm-remove'); confirm_remove.add_css_class('destructive-action'); confirm_actions.append(confirm_remove)
    cancel_remove=Gtk.Button(label='Cancel'); confirm_actions.append(cancel_remove)
    busy=False; loading=False; original=None; preset={}; replacements=[]
    def email_changed(*_):
        nonlocal preset
        if loading or original: return
        domain=fields['username'].get_text().strip().rsplit('@',1)[-1].lower()
        values=({'imap_host':'imap.gmail.com','smtp_host':'smtp.gmail.com','sent_folder':'[Gmail]/Sent Mail','trash_folder':'[Gmail]/Trash'}
                if domain in ('gmail.com','googlemail.com') else {'imap_host':'','smtp_host':'','sent_folder':'Sent','trash_folder':'Trash'})
        for key,value in values.items():
            current=fields[key].get_text()
            if not current or current==preset.get(key): fields[key].set_text(value)
        preset=values
    fields['username'].connect('changed',email_changed)
    def selected(*_):
        nonlocal original,loading,preset
        if loading: return
        loading=True
        index=selector.get_selected(); account=accounts[index] if index<len(accounts) else {}
        original=account.get('username')
        remove.set_sensitive(bool(original)); edit.set_sensitive(bool(original)); confirmation.set_visible(False)
        defaults={'username':'','name':'','display_name':'','imap_host':'','smtp_host':'','imap_port':993,'smtp_port':465,'imap_username':'','smtp_username':'',
                  'sent_folder':'Sent','trash_folder':'Trash','color':ACCOUNT_COLORS[len(accounts)%len(ACCOUNT_COLORS)]}
        for key,widget in fields.items(): widget.set_text(str(account.get(key,defaults[key])))
        for protocol,widget in security.items(): widget.set_selected(1 if account.get(protocol+'_security')=='starttls' else 0)
        fields['username'].set_editable(not original)
        entry.set_text(''); entry.set_property('placeholder-text','Leave blank to keep saved password' if original else 'Enter app password or mailbox password')
        status.set_text('Check and save verifies the connection without sending an email.')
        preset={'imap_host':'','smtp_host':'','sent_folder':'Sent','trash_folder':'Trash'}
        loading=False
    def edit_account(_):
        if original:
            status.set_text('Edit this account, then Check and save. Leave the password blank to keep it.')
            fields['name'].grab_focus()
    def add_account(_):
        selector.set_selected(len(accounts)); fields['username'].grab_focus()
    edit.connect('clicked',edit_account); add.connect('clicked',add_account)
    selector.connect('notify::selected',selected)
    try: saved=saved_passwords()
    except ValueError: saved={}
    selector.set_selected(next((i for i,a in enumerate(accounts) if a['username'] not in saved),len(accounts)))
    selected()
    def store(_):
        nonlocal busy,raw,data,accounts,original,loading
        if busy: return
        try:
            values={key:widget.get_text() for key,widget in fields.items()}
            values.update({protocol+'_security':('ssl','starttls')[widget.get_selected()] for protocol,widget in security.items()})
            account=setup_account(values)
            account_config_text(raw,account,original)
            secret=entry.get_text() or (saved_passwords().get(original,'') if original else '')
            if account['imap_host']=='imap.gmail.com': secret=secret.replace(' ','')
            if not secret.strip(): raise ValueError('Enter the mailbox password or app password first.')
        except Exception as error:
            status.set_text(str(error)); return
        confirmation.set_visible(False)
        busy=True
        for widget in (selector,grid,advanced,entry,button,remove,edit,add,importer): widget.set_sensitive(False)
        button.set_label('Checking…'); status.set_text('Checking SMTP login and IMAP Sent folder…')
        def done(error):
            nonlocal busy,raw,data,accounts,original,loading
            busy=False
            window=box.get_root()
            if window is None or not window.get_visible(): return False
            for widget in (selector,grid,advanced,entry,button,remove,edit,add,importer): widget.set_sensitive(True)
            button.set_label('Check and save'); remove.set_sensitive(bool(original)); edit.set_sensitive(bool(original))
            if error:
                status.set_text('Not saved. '+error); entry.grab_focus(); return False
            try:
                raw=save_setup_account(account,secret,original,raw)
                data=tomllib.loads(raw); accounts=setup_accounts(data)
                loading=True
                selector.set_model(Gtk.StringList.new([account_label(a) for a in accounts]+['＋ Add account']))
                selector.set_selected(next(i for i,a in enumerate(accounts) if a['username']==account['username']))
                loading=False; selected()
                status.set_text('Account saved. SMTP and IMAP verified; no email sent. Newinit will copy the settings and password on the next sync.')
            except Exception as failure:
                status.set_text('Server check passed, but saving failed: '+str(failure).replace(secret,'[redacted]'))
            return False
        def check_server():
            try: verify_account(account,secret); error=None
            except Exception as failure: error=str(failure).replace(secret,'[redacted]')
            GLib.idle_add(done,error)
        threading.Thread(target=check_server,daemon=True).start()
    def ask_remove(_):
        nonlocal replacements
        if busy or not original: return
        replacements=[a for a in accounts if a['username']!=original]
        default=data.get('default_account',accounts[0]['username'])
        invoice=data.get('invoice_account',default)
        needs_replacement=bool(replacements) and original in (default,invoice)
        replacement.set_model(Gtk.StringList.new([account_label(a) for a in replacements]))
        replacement.set_selected(0); replacement.set_visible(needs_replacement)
        text='Remove '+original+' and its saved password from Simplemail? Emails on the server will stay untouched.'
        if needs_replacement:
            roles=[]
            if original==default: roles.append('default sender')
            if original==invoice: roles.append('invoice sender')
            text+=' Choose the replacement '+ ' and '.join(roles)+':'
        elif not replacements: text+=' This is the last account; you can add another here later.'
        warning.set_text(text); confirmation.set_visible(True); cancel_remove.grab_focus()
    def do_remove(_):
        nonlocal raw,data,accounts,loading
        if busy or not original or not confirmation.get_visible(): return
        try:
            target=replacements[replacement.get_selected()]['username'] if replacements else None
            raw=remove_setup_account(original,target,raw)
            data=tomllib.loads(raw); accounts=setup_accounts(data)
            loading=True
            selector.set_model(Gtk.StringList.new([account_label(a) for a in accounts]+['＋ Add account']))
            selector.set_selected(len(accounts)); loading=False; selected()
            status.set_text('Account and saved password removed. Server emails were not changed.')
        except Exception as error: status.set_text('Not removed. '+str(error))
    remove.connect('clicked',ask_remove)
    confirm_remove.connect('clicked',do_remove)
    cancel_remove.connect('clicked',lambda _:confirmation.set_visible(False))
    button.connect('clicked',store)
    entry.connect('activate',store)
    for widget in fields.values(): widget.connect('activate',store)
    def focus(*_):
        (entry if original else fields['username']).grab_focus()
    box.connect('map',focus)
    return box

def install_theme(window):
    from gi.repository import Gtk, Gio, GLib
    window.add_css_class('simplemail')
    root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))
    path=root/'simplemail/style.css'
    provider=Gtk.CssProvider()
    _load_simple_css(provider,str(path))
    Gtk.StyleContext.add_provider_for_display(window.get_display(),provider,Gtk.STYLE_PROVIDER_PRIORITY_USER+2)
    # Watch the directory so atomic editor saves also refresh an open draft safely.
    monitor=Gio.File.new_for_path(str(root/'simple')).monitor_directory(Gio.FileMonitorFlags.NONE,None)
    pending=[None]
    def reload():
        pending[0]=None
        _load_simple_css(provider,str(path))
        return False
    def changed(*_):
        if pending[0] is not None: GLib.source_remove(pending[0])
        pending[0]=GLib.timeout_add(250,reload)
    monitor.connect('changed',changed)
    window._simple_theme=(provider,monitor)
    def cleanup(*_):
        if sys.is_finalizing(): return
        monitor.cancel()
        if pending[0] is not None: GLib.source_remove(pending[0]);pending[0]=None
        Gtk.StyleContext.remove_provider_for_display(window.get_display(),provider)
    window.connect('destroy',cleanup)

def setup_gui(cfg):
    # Password setup must work while the mail scratchpad is hidden and must
    # use freshly read accounts without disturbing an existing compose draft.
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk,Gio,Gdk
    app=Gtk.Application(application_id='com.go7.Simplemail.Setup',flags=Gio.ApplicationFlags.NON_UNIQUE)
    def activate(application):
        window=Gtk.ApplicationWindow(application=application,title='Simplemail · Account setup')
        install_theme(window)
        window.set_default_size(640,520)
        scroll=Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(setup_view(cfg,window.close,back_label='Done')); window.set_child(scroll)
        keys=Gtk.EventControllerKey()
        def pressed(_,keyval,keycode,modifiers):
            if keyval==Gdk.KEY_Escape:
                window.close(); return True
            return False
        keys.connect('key-pressed',pressed); window.add_controller(keys)
        window.present()
    app.connect('activate',activate)
    return app.run([sys.argv[0]])

def install_window_keys(window):
    from gi.repository import Gtk,Gdk
    keys=Gtk.EventControllerKey()
    def pressed(_,keyval,keycode,modifiers):
        if keyval==Gdk.KEY_Escape and not (modifiers & Gtk.accelerator_get_default_mod_mask()):
            child=window.get_child()
            if child is not None and hasattr(child,'handle_escape'):
                if child.handle_escape():return True
            # Keep the application window, drafts and mail-check timer alive.
            # Mango's named scratchpad shortcut restores this minimized window.
            window.minimize()
            return True
        return False
    keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    keys.connect('key-pressed',pressed); window.add_controller(keys)

def launch_foreground(app_id='com.go7.Simplemail'):
    # Separate from the single-instance GTK owner: a new CLI request can also
    # raise an older, already-running instance without restarting its drafts.
    helper=Path(__file__).with_name('mail_foreground.py')
    subprocess.Popen([sys.executable,str(helper),app_id],stdout=subprocess.DEVNULL,
                     start_new_session=True)

def gui(cfg,initial='',setup=False,draft=None,background=False):
    if setup: return setup_gui(cfg)
    import gi
    gi.require_version('Gtk','4.0')
    from gi.repository import Gtk,Gio,GLib
    from mail_foreground import capture_origin,restore_origin
    origin=capture_origin() if initial else None
    # One running application/window. Later invocations forward drafts to it.
    app=Gtk.Application(application_id='com.go7.Simplemail',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
    state={'window':None,'draft':None,'draft_key':None,'drafts':{},'sending':False,'inbox':None,'loaded':False,'config_timer':None,'monitor':None}
    def set_busy(value): state['sending']=value
    def show_inbox():
        if state['sending']: return
        if not configured_accounts(cfg):
            empty=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12)
            empty.append(Gtk.Label(label='No mail accounts configured.'))
            add=Gtk.Button(label='Add account'); add.connect('clicked',lambda _:subprocess.Popen([sys.executable,str(Path(__file__).resolve()),'--setup']))
            empty.append(add); state['window'].set_child(empty); return
        if state['inbox'] is None:
            state['inbox'],state['reload'],state['compose_button']=inbox_view(state['window'],cfg,compose)
        state['compose_button'].set_label('Resume draft · n' if state['draft'] else 'Compose · n')
        state['window'].set_child(state['inbox'])
        state['inbox'].focus_list()
        if not state['loaded']:
            state['loaded']=True; state['reload']()
    def select_draft(key):
        state['draft_key']=key
        state['draft'],state['recipient'],state['draft_status']=state['drafts'].get(key,(None,None,None))
    def discard():
        state['drafts'].pop(state['draft_key'],None)
        select_draft(next(reversed(state['drafts']),None))
        show_inbox()
    def sent():
        exported=getattr(state['draft'],'exported',False)
        origin=getattr(state['draft'],'return_origin',None)
        if state['inbox'] is not None:state['inbox'].reply_sent(state['draft'].reply_source)
        discard()
        if state['inbox'] is not None:state['inbox'].check_mail()
        if exported:
            state['window'].minimize()
            GLib.timeout_add(150,restore_origin,origin)
    def setup_done():
        state['loaded']=False; show_inbox()
    def compose(values=None,pdf='',origin=None):
        if state['sending']: return
        if values and values.get('_reply_id'):
            key=('reply',values['_reply_id'])
        elif values or pdf:
            key=('external',hashlib.sha256(json.dumps([pdf,values or {}],sort_keys=True).encode()).hexdigest())
        else:
            key=state['draft_key'] if state['draft_key'] in state['drafts'] else ('new',)
        # Retain drafts in this session, but never substitute one message's
        # draft when the user explicitly replies to another selected message.
        entry=state['drafts'].pop(key,None)
        if entry is None:
            entry=compose_view(
                state['window'],cfg,pdf,values or {},show_inbox,discard,sent,set_busy)
        if pdf:
            entry[0].exported=True
            if origin is not None:entry[0].return_origin=origin
        state['drafts'][key]=entry
        select_draft(key)
        state['window'].set_child(state['draft']); state['draft'].focus_compose()
    def refresh_config():
        nonlocal cfg
        if state['drafts'] or state['sending'] or (state['inbox'] is not None and not state['inbox'].can_reload()):
            return True
        state['config_timer']=None
        try:
            _,data=setup_config()
            updated=account_settings(data) if setup_accounts(data) else {'accounts':[]}
        except (OSError,ValueError): return False
        if updated==cfg:
            if state['inbox'] is not None: state['reload']()
            return False
        if state['inbox'] is not None: state['inbox'].dispose()
        cfg=updated; state['inbox']=None; state['loaded']=False
        show_inbox()
        return False
    def config_changed(monitor,file,other,event):
        if any(f and f.get_basename()==CONFIG.name for f in (file,other)) and state['config_timer'] is None:
            state['config_timer']=GLib.timeout_add(300,refresh_config)
    def stop_monitor(*_):
        if state['config_timer'] is not None: GLib.source_remove(state['config_timer']); state['config_timer']=None
        if state['monitor'] is not None: state['monitor'].cancel()
    def command_line(application,command):
        request=json.loads(command.get_arguments()[1])
        if state['window'] is None:
            state['window']=Gtk.ApplicationWindow(application=application,title='Simplemail')
            install_theme(state['window'])
            state['window'].set_default_size(980,620)
            install_window_keys(state['window'])
            state['window'].connect('close-request',lambda *_:state['sending'])
            show_inbox()
            state['monitor']=Gio.File.new_for_path(str(CONFIG.parent)).monitor_directory(Gio.FileMonitorFlags.NONE,None)
            state['monitor'].connect('changed',config_changed)
        if request['setup']:
            if state['draft'] or state['sending']:
                if state['draft']: state['draft_status'].set_text('Finish or discard this draft before opening password setup.')
            else: state['window'].set_child(setup_view(cfg,setup_done))
        elif request['initial'] or request['draft']:
            compose(request['draft'],request['initial'],request.get('origin'))
        elif state['window'].get_child() is None:
            show_inbox()
        # Keep the initial window unmapped while inbox polling runs. A later
        # normal invocation (including Mango's toggle) presents this same window.
        if not request.get('background') or request['setup'] or request['initial'] or request['draft']:
            state['window'].present()
            if request['initial'] or request['draft']:
                GLib.timeout_add(150,lambda:(launch_foreground(),False)[1])
        return 0
    app.connect('command-line',command_line)
    app.connect('shutdown',stop_monitor)
    return app.run([sys.argv[0],json.dumps(dict(initial=initial,setup=setup,draft=draft or {},background=background,origin=origin))])

def main():
    desktop_environment()
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--background',action='store_true',help='Start mail checks without showing the window')
    parser.add_argument('--inbox',action='store_true',help='Open mail (the inbox is the default view)')
    parser.add_argument('--encrypt-passwords',action='store_true',help='Encrypt an existing plaintext password file once; no login prompt')
    parser.add_argument('--migrate-keyring',action='store_true',help='Copy missing mailbox passwords from an already unlocked legacy keyring; never prompt')
    parser.add_argument('--draft-dir',type=Path); parser.add_argument('pdf',nargs='?',default=''); parser.add_argument('--setup',action='store_true',help='Add or edit an account, verify its connection, and save settings and password'); parser.add_argument('--check',action='store_true'); parser.add_argument('--check-server',action='store_true')
    args=parser.parse_args()
    if args.encrypt_passwords: return encrypt_passwords()
    if args.setup: return setup_gui(None)
    _,data=setup_config()
    if not setup_accounts(data):
        if args.check or args.check_server or args.migrate_keyring:
            print('Simplemail: no accounts configured; use simplemail --setup to add one.'); return 0
        if args.background: return 0
        return setup_gui(None)
    cfg=settings()
    if args.migrate_keyring: return migrate_keyring(cfg)
    if args.check: return check(cfg)
    if args.check_server:
        failed=False
        for account in configured_accounts(cfg):
            try:
                secret=password(account)
                verify_account(account,secret)
                print(account['username']+': SMTP login and Sent folder verified. No email sent.')
            except Exception as error: failed=True; print(account['username']+': '+str(error))
        return 1 if failed else 0
    draft={}
    if args.pdf.startswith('mailto:'):
        uri=urlsplit(args.pdf); query=parse_qs(uri.query)
        draft={'recipient':unquote(uri.path),'subject':query.get('subject',['Invoice'])[0],'body':query.get('body',[''])[0]}
        args.pdf=''
    if args.draft_dir:
        folder=args.draft_dir
        draft={key:(folder/(key+'.txt')).read_text(encoding='utf-8') for key in ('recipient','subject','body')}
        draft['attachments']=(folder/'attachments.txt').read_text(encoding='utf-8').splitlines()
        if not draft['attachments']: raise ValueError('Draft has no attachments.')
        args.pdf=draft['attachments'][0]
    result=gui(cfg,args.pdf,args.setup,draft,background=args.background)
    if result==0 and (args.pdf or draft):launch_foreground()
    return result
if __name__=='__main__':
    if not any(arg in sys.argv for arg in ('--encrypt-passwords','--migrate-keyring','--check','--check-server')):
        os.execv(sys.executable,[sys.executable,str(Path(__file__).with_name('native-launch.py')),*sys.argv[1:]])
    try: sys.exit(main())
    except Exception as error: print(str(error),file=sys.stderr); sys.exit(1)
