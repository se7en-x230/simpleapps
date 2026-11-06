from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
m=SourceFileLoader('timer',str(Path(__file__).with_name('simpletimer'))).load_module()
with TemporaryDirectory() as tmp:
    root=Path(tmp)
    t=m.Timers(m.DEFAULTS,root/'state.json',root/'fast/start')
    with patch.object(m.time,'time',return_value=10000):
        t.toggle('countdown');t.toggle('stopwatch');t.toggle('fasting',1)
    with patch.object(m.time,'time',return_value=10030):
        assert t.value('countdown')==270 and t.value('stopwatch')==30
        assert t.value('fasting')==3630
        t.toggle('countdown');t.toggle('stopwatch')
    t=m.Timers(m.DEFAULTS,root/'state.json',root/'fast/start')
    with patch.object(m.time,'time',return_value=11000):
        assert t.value('countdown')==270 and t.value('stopwatch')==30
        t.toggle('countdown');t.toggle('pomodoro')
    with patch.object(m.time,'time',return_value=13000):
        assert set(t.complete())=={'countdown','pomodoro'}
        assert not t.complete()
        t.toggle('pomodoro');assert t.state('pomodoro')['phase']=='Break'
        assert t.value('pomodoro')==300
        t.toggle('fasting');assert t.fast_start() is None
    t.fasting.write_text('9000 lb\n')
    assert t.fast_start()==9000
    t.fasting.unlink();assert t.fast_start() is None
    print('PASS: persistence, pause/resume, overdue alerts once, Pomodoro phases, legacy fasting state')
