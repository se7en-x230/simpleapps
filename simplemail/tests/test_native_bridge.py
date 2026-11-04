import sys,unittest,tempfile,json,os,uuid,copy
from pathlib import Path
from unittest.mock import patch,Mock
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import bridge as b
class BridgeTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.root=Path(self.tmp.name)
  self.account={'username':'test@example.test','imap_host':'imap.example.test','imap_port':993,'smtp_host':'smtp.example.test','smtp_port':465,'sent_folder':'Sent','trash_folder':'Trash','display_name':'Test','name':'Test'}
  self.cfg=dict(self.account,accounts=[self.account],invoice_account=self.account['username'])
  self.item={'account':self.account['username'],'folder':'INBOX','validity':'12','uid':'3','unread':True}
  for name,value in [('config',lambda:('',self.cfg))]:
   p=patch.object(b,name,value);p.start();self.addCleanup(p.stop)
  p=patch.dict(os.environ,{'XDG_CACHE_HOME':str(self.root/'cache'),'XDG_STATE_HOME':str(self.root/'state')});p.start();self.addCleanup(p.stop)
  p=patch.object(b.m,'password',return_value='test-secret');p.start();self.addCleanup(p.stop)
 def test_json_mailbox_validity_matches_bytes_and_rejects_change(self):
  client=Mock();client.select.return_value=('OK',[b'1']);client.response.return_value=('UIDVALIDITY',[b'12'])
  with patch.object(b.m,'imap_client',return_value=client):
   with b.m.inbox_connection(self.account,'secret','12') as (_,validity,total):
    self.assertEqual(validity,b'12');self.assertEqual(total,1)
   with self.assertRaisesRegex(ValueError,'changed'):
    with b.m.inbox_connection(self.account,'secret','13'):pass
 def test_headers_failure_keeps_previous_cache(self):
  b.save_cache('inbox',{'messages':[self.item],'total':1,'errors':[]})
  with patch.object(b.m,'combined_headers',side_effect=OSError('offline')):
   with self.assertRaises(OSError):b.handle({'op':'list'})
  self.assertEqual(b.cached('inbox',self.cfg)['messages'],[self.item]);self.assertEqual(b.cache_path('inbox').stat().st_mode&0o777,0o600)
 def test_reply_identity_and_account(self):
  msg=dict(subject='Hello',recipient='friend@example.test',sender='Friend',text='Original message')
  with patch.object(b.m,'inbox_message',return_value=msg):r=b.handle({'op':'reply','item':self.item})
  self.assertEqual(r['_reply_source'],b.m.reply_source(self.account,self.item));self.assertEqual(r['account'],self.account['username']);self.assertEqual(r['subject'],'Re: Hello')
 def test_mark_and_partial_trash(self):
  other=dict(self.item,uid='4');b.save_cache('inbox',{'messages':[self.item,other]})
  with patch.object(b.m,'inbox_mark_read') as call:b.handle({'op':'mark','items':[self.item]});call.assert_called_once()
  self.assertFalse(b.cached('inbox',self.cfg)['messages'][0]['unread'])
  with patch.object(b.m,'inbox_trash',side_effect=[None,OSError('offline')]):r=b.handle({'op':'trash','items':[self.item,other]})
  self.assertEqual([e['uid'] for e in r['messages']],['4']);self.assertIn('1 completed',r['message'])
 def test_stable_send_receipt_and_revision_confirmation(self):
  pdf=self.root/'invoice.pdf';pdf.write_bytes(b'%PDF-test');receipt=pdf.with_suffix('.pdf.sent.json')
  d=dict(id=str(uuid.uuid4()),account=self.account['username'],invoice=True,attachment=str(pdf),recipient='friend@example.test',subject='Invoice',body='Hello')
  bases=[]
  def sent(*args,**kw):
   base=kw['record_base'];bases.append(base);base.with_suffix(base.suffix+'.sent.json').write_text(json.dumps({'status':'accepted'}));return 'accepted'
  with patch.object(b.m,'send',side_effect=sent):
   first=b.handle({'op':'send','draft':d});second=b.handle({'op':'send','draft':d})
  self.assertTrue(first['pending']);self.assertEqual(bases[0],bases[1])
  receipt.write_text('{"status":"filed"}')
  with patch.object(b.m,'send') as send:self.assertTrue(b.handle({'op':'send','draft':d})['revision_required']);send.assert_not_called()
  d['revision']=True
  with patch.object(b.m,'send',side_effect=sent):b.handle({'op':'send','draft':d})
  self.assertNotEqual(bases[-1],pdf);self.assertEqual(json.loads(receipt.read_text())['status'],'filed')
 def test_native_send_retry_never_repeats_smtp(self):
  d=dict(id=str(uuid.uuid4()),account=self.account['username'],invoice=False,attachment='',recipient='friend@example.test',subject='Test',body='Hello')
  smtp=Mock();smtp.mail.return_value=(250,b'OK');smtp.rcpt.return_value=(250,b'OK');smtp.data.return_value=(250,b'Queued')
  with patch('pathlib.Path.home',return_value=self.root),patch.object(b.m,'smtp_client',return_value=smtp),patch.object(b.m,'file_sent',side_effect=[OSError('offline'),None]):
   one=b.handle({'op':'send','draft':d});two=b.handle({'op':'send','draft':d});three=b.handle({'op':'send','draft':d})
  self.assertTrue(one['pending']);self.assertTrue(two['complete']);self.assertTrue(three['complete']);smtp.data.assert_called_once()
 def test_pending_legacy_reply_repairs_identity_without_smtp(self):
  receipt=self.root/'pending.json';record={'status':'accepted','reply_source':dict(self.item),'sent_filed':True}
  client=Mock();client.select.return_value=('OK',[b'1']);client.response.return_value=('UIDVALIDITY',[b'12'])
  client.uid.side_effect=[('OK',[None]),('OK',[b'1 (UID 3 FLAGS (\\Seen \\Answered))'])]
  with patch.object(b.m,'imap_client',return_value=client),patch.object(b.m,'smtp_client') as smtp,patch.object(b.m,'file_sent') as sent:
   result=b.m.complete_sent(self.account,'secret',b'raw',record,receipt,self.account)
  self.assertEqual(record['status'],'filed');self.assertTrue(record['reply_marked']);self.assertEqual(record['reply_source']['imap_host'],self.account['imap_host'])
  smtp.assert_not_called();sent.assert_not_called();self.assertIn('saved in Sent',result)
  self.assertEqual(client.uid.call_args_list[-1].args,('FETCH','3','(UID FLAGS)'))
 def test_attachments_do_not_overwrite(self):
  from email.message import EmailMessage
  msg=EmailMessage();msg.set_content('hello');msg.add_attachment(b'example',maintype='application',subtype='octet-stream',filename='file.dat')
  cache=self.root/'cached';cache.write_bytes(b'{}\n'+msg.as_bytes());target=self.root/'output';target.write_text('keep')
  with patch.object(b.m,'inbox_message',return_value={'truncated':False}),patch.object(b.m,'preview_file',return_value=cache):
   with self.assertRaises(FileExistsError):b.handle(dict(op='attachment',item=self.item,index=0,path=str(target)))
  self.assertEqual(target.read_text(),'keep')
 def test_no_remote_image_fetch_in_preview(self):
  msg={'images':[{'name':'remote','url':'https://example.test/image.png'},{'name':'embedded','data':b'png'}],'text':'hello'}
  with patch.object(b.m,'inbox_message',return_value=msg),patch.object(b.m,'image_file') as image:
   r=b.handle({'op':'read','item':self.item});image.assert_not_called();json.dumps(r)
  self.assertTrue(r['images'][0]['remote'])
if __name__=='__main__':unittest.main()
