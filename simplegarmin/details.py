"""Display mappings for Garmin's daily summaries; missing readings stay missing."""
from client import number, duration


def obj(value):
    return value if isinstance(value, dict) else {}


def details(data):
    s = obj(data.get('summary'))
    sleep = obj(data.get('sleep'))
    sleep = obj(sleep.get('dailySleepDTO', sleep))
    hrv = obj(obj(data.get('hrv')).get('hrvSummary'))
    def n(key, unit='', source=None):
        return number((s if source is None else source).get(key), unit)
    def d(key, source=None):
        return duration((s if source is None else source).get(key))
    status = hrv.get('status')
    status = status.replace('_', ' ').title() if status and status not in ('NONE', 'INVALID') else '—'
    return {
        'Heart': [
            ('Resting heart rate', n('restingHeartRate', ' bpm')),
            ('7-day resting average', n('lastSevenDaysAvgRestingHeartRate', ' bpm')),
            ('Daily minimum', n('minHeartRate', ' bpm')),
            ('Daily maximum', n('maxHeartRate', ' bpm')),
            ('Average during sleep', n('avgHeartRate', ' bpm', sleep)),
            ('Overnight HRV', n('lastNightAvg', ' ms', hrv)),
            ('7-day HRV average', n('weeklyAvg', ' ms', hrv)),
            ('Garmin HRV status', status)],
        'Recovery': [
            ('Latest Body Battery', n('bodyBatteryMostRecentValue', ' / 100')),
            ('At wake-up', n('bodyBatteryAtWakeTime', ' / 100')),
            ('Daily highest', n('bodyBatteryHighestValue', ' / 100')),
            ('Daily lowest', n('bodyBatteryLowestValue', ' / 100')),
            ('Charged today', n('bodyBatteryChargedValue', ' points')),
            ('Drained today', n('bodyBatteryDrainedValue', ' points')),
            ('Overnight HRV', n('lastNightAvg', ' ms', hrv)),
            ('Garmin HRV status', status)],
        'Sleep': [
            ('Total sleep', d('sleepTimeSeconds', sleep)),
            ('Sleep score', number(obj(obj(sleep.get('sleepScores')).get('overall')).get('value'), ' / 100')),
            ('Deep sleep', d('deepSleepSeconds', sleep)),
            ('Light sleep', d('lightSleepSeconds', sleep)),
            ('REM sleep', d('remSleepSeconds', sleep)),
            ('Awake time', d('awakeSleepSeconds', sleep)),
            ('Naps', d('napTimeSeconds', sleep)),
            ('Average sleep stress', n('avgSleepStress', ' / 100', sleep))],
        'Stress': [
            ('Daily average', n('averageStressLevel', ' / 100')),
            ('Daily maximum', n('maxStressLevel', ' / 100')),
            ('Rest', d('restStressDuration')),
            ('Low stress', d('lowStressDuration')),
            ('Medium stress', d('mediumStressDuration')),
            ('High stress', d('highStressDuration')),
            ('Activity time', d('activityStressDuration')),
            ('Unclassified time', d('uncategorizedStressDuration'))],
        'Breathing': [
            ('Average awake respiration', n('avgWakingRespirationValue', ' br/min')),
            ('Average sleep respiration', n('averageRespirationValue', ' br/min', sleep)),
            ('Lowest respiration', n('lowestRespirationValue', ' br/min')),
            ('Highest respiration', n('highestRespirationValue', ' br/min')),
            ('Average blood oxygen', n('averageSpo2', '%')),
            ('Lowest blood oxygen', n('lowestSpo2', '%')),
            ('Average sleep oxygen', n('averageSpO2Value', '%', sleep)),
            ('Lowest sleep oxygen', n('lowestSpO2Value', '%', sleep))]
    }

NOTES = {
    'Heart': 'Heart rate in beats/minute · HRV in milliseconds. Garmin calculates HRV status against your personal baseline.',
    'Recovery': 'Body Battery is Garmin’s energy estimate (0–100). Charged and drained show accumulated points for the selected day.',
    'Sleep': 'Sleep belongs to the selected wake-up date. Awake time is separate from total sleep; naps are shown separately.',
    'Stress': 'Garmin stress scores run from 0–100. Activity and unclassified time are shown separately from measured stress.',
    'Breathing': 'Respiration is breaths/minute. Oxygen is SpO₂ percentage. Readings depend on device support and enabled tracking.'
}
