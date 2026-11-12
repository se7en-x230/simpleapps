import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
from client import Client, ApiError, metrics, save, duration

class Checks(unittest.TestCase):
    def test_missing_is_not_zero(self):
        self.assertTrue(all(card[1] == '—' for card in metrics({})))
        self.assertEqual(metrics({'summary': {'totalSteps': 0}})[0][1], '0')
        self.assertEqual(metrics({'summary': {'averageStressLevel': -1}})[4][1], '—')

    def test_sleep_and_summary(self):
        cards = metrics({'summary': {'bodyBatteryMostRecentValue': 75},
                         'sleep': {'sleepTimeSeconds': 27000, 'sleepScores': {'overall': {'value': 82}}}})
        self.assertEqual(cards[1][1:], ('7h 30m', 'Score 82 / 100'))
        self.assertEqual(cards[2][1], '75')

    def test_private_storage(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / 'private' / 'key.json'
            save(path, {'key': 'test'})
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)
            self.assertEqual(path.parent.stat().st_mode & 0o777, 0o700)

    def test_token_and_partial_failure(self):
        c = Client('example')
        with patch.object(c, 'request', side_effect=['token', {'totalSteps': 5}, ApiError('Unavailable'), [], {}]) as request:
            data = c.fetch('2026-11-10')
        self.assertEqual(data['summary']['totalSteps'], 5)
        self.assertEqual(data['errors'], ['Sleep: Unavailable'])
        self.assertEqual(request.call_args_list[0].args[1:], ('ApiKey example', 'POST'))
        self.assertEqual(request.call_args_list[1].args[1], 'Bearer token')

    def test_token_request_accepts_plain_text(self):
        from unittest.mock import MagicMock
        c = Client('example')
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'plain.jwt.token'
        with patch.object(c.opener, 'open', return_value=response) as opened:
            self.assertEqual(c.request('/token', 'ApiKey example', 'POST'), 'plain.jwt.token')
        request = opened.call_args.args[0]
        self.assertEqual(request.get_header('Accept'), '*/*')
        self.assertEqual(request.data, b'')

    def test_detail_fields_and_missing_data(self):
        from details import details
        empty = details({})
        self.assertEqual(len(empty), 5)
        self.assertTrue(all(value == '—' for page in empty.values() for _, value in page))
        data = details({'summary': {'averageSpo2': 97, 'lowStressDuration': 3600,
                                   'bodyBatteryChargedValue': 0},
                        'hrv': {'hrvSummary': {'lastNightAvg': 42, 'status': 'BALANCED'}},
                        'sleep': {'deepSleepSeconds': 5400}})
        self.assertEqual(dict(data['Heart'])['Overnight HRV'], '42 ms')
        self.assertEqual(dict(data['Heart'])['Garmin HRV status'], 'Balanced')
        self.assertEqual(dict(data['Sleep'])['Deep sleep'], '1h 30m')
        self.assertEqual(dict(data['Stress'])['Low stress'], '1h 00m')
        self.assertEqual(dict(data['Breathing'])['Average blood oxygen'], '97%')
        self.assertEqual(dict(data['Recovery'])['Charged today'], '0 points')

    def test_bad_token(self):
        with patch.object(Client, 'request', return_value={}):
            with self.assertRaises(ApiError):
                Client('example').fetch('2026-11-10')

if __name__ == '__main__':
    unittest.main()
