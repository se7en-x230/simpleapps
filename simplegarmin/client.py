"""Small client for Garmin's official Personal API. No account password required."""
import json
import os
from pathlib import Path
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = 'https://personal.connectapi.garmin.com'
KEY_URL = 'https://connect.garmin.com/app/settings/personalApiToken'
CONFIG = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')) / 'simplegarmin'
CACHE = Path(os.environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'simplegarmin'


def read(path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return {}


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, name = tempfile.mkstemp(dir=path.parent)
    try:
        with os.fdopen(fd, 'w') as stream:
            json.dump(data, stream)
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class ApiError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        return None


class Client:
    def __init__(self, key):
        self.key = key
        self.token = None
        self.expires = 0
        self.opener = urllib.request.build_opener(NoRedirect)

    def request(self, path, authorization, method='GET'):
        request = urllib.request.Request(BASE + path, method=method,
            data=b'' if method == 'POST' else None,
            headers={'Authorization': authorization,
                     'Accept': '*/*' if method == 'POST' else 'application/json'})
        try:
            with self.opener.open(request, timeout=15) as response:
                raw = response.read().decode()
            try:
                return json.loads(raw)
            except ValueError:
                return raw.strip()
        except urllib.error.HTTPError as exc:
            if exc.code in (401, 403):
                self.token = None
                raise ApiError('Garmin denied access. Check or replace your API key.') from None
            if exc.code == 429:
                raise ApiError('Garmin rate limit reached. Try again later.') from None
            raise ApiError(f'Garmin returned HTTP {exc.code}. Try again later.') from None
        except (OSError, urllib.error.URLError):
            raise ApiError('Cannot reach Garmin. Check your internet connection.') from None

    def fetch(self, day):
        if not self.token or time.time() >= self.expires:
            data = self.request('/personalapitoken-service/personal-api/personal-api-key/token',
                                'ApiKey ' + self.key, 'POST')
            token = data if isinstance(data, str) else (data.get('access_token') or data.get('accessToken') or data.get('token'))
            if not isinstance(token, str) or not token or any(c.isspace() for c in token):
                raise ApiError('Garmin returned an unexpected token format.')
            self.token, self.expires = token, time.time() + 23 * 3600
        paths = {
            'summary': '/usersummary-service/usersummary/daily?calendarDate=' + day,
            'sleep': '/sleep-service/sleep/dailySleep?date=' + day,
            'activities': '/activitylist-service/activities/search/activities?' + urllib.parse.urlencode(
                {'start': 0, 'limit': 3, 'startDate': day, 'endDate': day, 'sortOrder': 'desc'}),
            'hrv': '/hrv-service/hrv/' + day}
        result, errors = {}, []
        for name, path in paths.items():
            try:
                result[name] = self.request(path, 'Bearer ' + self.token)
            except ApiError as exc:
                errors.append(name.title() + ': ' + str(exc))
                if not self.token:
                    break
        if not result:
            raise ApiError(errors[0])
        result.update(fetched=time.time(), errors=list(dict.fromkeys(errors)))
        return result


def number(value, suffix=''):
    return f'{value:,.0f}{suffix}' if isinstance(value, (float, int)) and value >= 0 else '—'


def duration(seconds):
    if not isinstance(seconds, (float, int)) or seconds < 0:
        return '—'
    minutes = int(seconds) // 60
    return f'{minutes // 60}h {minutes % 60:02d}m'


def metrics(data):
    s, sleep = data.get('summary', {}), data.get('sleep', {})
    s = s if isinstance(s, dict) else {}
    sleep = sleep if isinstance(sleep, dict) else {}
    sleep = sleep.get('dailySleepDTO', sleep)
    score = ((sleep.get('sleepScores') or {}).get('overall') or {}).get('value')
    return [
        ('STEPS', number(s.get('totalSteps')), 'Goal ' + number(s.get('dailyStepGoal'))),
        ('SLEEP', duration(sleep.get('sleepTimeSeconds')), 'Score ' + number(score, ' / 100')),
        ('BODY BATTERY', number(s.get('bodyBatteryMostRecentValue')), 'Latest reading · out of 100'),
        ('RESTING HEART RATE', number(s.get('restingHeartRate'), ' bpm'), 'Daily resting average'),
        ('STRESS', number(s.get('averageStressLevel')), 'Daily average · out of 100'),
        ('ACTIVE CALORIES', number(s.get('activeKilocalories'), ' kcal'), 'Excludes resting calories')]
