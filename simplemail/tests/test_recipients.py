import importlib.util, sys, tempfile, unittest, json
from pathlib import Path
from unittest.mock import Mock, patch
from email.parser import BytesParser
from email import policy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
source=Path(__file__).with_name('simplemail.py')
if not source.exists(): source=Path(__file__).parent.parent/'simplemail.py'
spec=importlib.util.spec_from_file_location('sender',source)
sender=importlib.util.module_from_spec(spec);spec.loader.exec_module(sender)
class Recipients(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name)/'draft'
        self.cfg=dict(username='sender@example.com',display_name='Sender',smtp_host='example.com',smtp_port=465)
        self.smtp=Mock();self.smtp.mail.return_value=(250,b'OK');self.smtp.rcpt.return_value=(250,b'OK');self.smtp.data.return_value=(250,b'Queued')
        self.p=patch.object(sender,'smtp_client',return_value=self.smtp);self.p.start();self.addCleanup(self.p.stop)
        self.f=patch.object(sender,'file_sent');self.f.start();self.addCleanup(self.f.stop)
    def send(self,to): return sender.send(None,to,'Test','Body',self.cfg,'test',record_base=self.base)
    def test_multiple_and_duplicate_guard(self):
        to='one@example.com, two@example.com,one@example.com'
        self.send(to);self.send(to)
        self.assertEqual([c.args[0] for c in self.smtp.rcpt.call_args_list],['one@example.com','two@example.com'])
        self.smtp.data.assert_called_once()
        msg=BytesParser(policy=policy.default).parsebytes(self.smtp.data.call_args.args[0])
        self.assertEqual(str(msg['To']),'one@example.com, two@example.com')
        self.assertEqual(json.loads(self.base.with_suffix('.sent.json').read_text())['recipient'],'one@example.com, two@example.com')
    def test_invalid_before_connect(self):
        for to in ('a@example.com,','a@example.com,,b@example.com','bad,a@example.com','a@example.com; b@example.com','a@example.com\r\nBcc: b@example.com','@example.com','a@'):
            with self.subTest(to=to),self.assertRaises(ValueError):self.send(to)
        sender.smtp_client.assert_not_called()
    def test_rejection_does_not_deliver_partial_message(self):
        self.smtp.rcpt.side_effect=[(250,b'OK'),(550,b'No')]
        with self.assertRaisesRegex(ValueError,'two@example.com'):self.send('one@example.com,two@example.com')
        self.smtp.data.assert_not_called();self.smtp.close.assert_called_once()
    def test_filing_retry_never_resends(self):
        with patch.object(sender,'file_sent',side_effect=OSError('offline')):self.send('one@example.com,two@example.com')
        self.send('one@example.com,two@example.com')
        self.smtp.data.assert_called_once();self.assertEqual(self.smtp.rcpt.call_count,2)
if __name__=='__main__':unittest.main()
