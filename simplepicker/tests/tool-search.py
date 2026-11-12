#!/usr/bin/env python3
import importlib.util
from pathlib import Path
import sys
import tempfile
import types
import unicodedata
from unittest.mock import patch
root=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('simplepicker_api',root/'python/simplepicker_api.py')
api=importlib.util.module_from_spec(spec);spec.loader.exec_module(api)
normalize=lambda text: ''.join(c for c in unicodedata.normalize('NFKD',text.casefold()) if not unicodedata.combining(c))
ui=types.SimpleNamespace(normalize=normalize)
config='''title="System"
[[tools]]
id="wallpaper"
name="Wallpaper"
group="System controls"
command=["do-not-run"]
[[tools]]
id="display"
name="Displays"
group="System controls"
command=["do-not-run"]
[[tools]]
id="health"
name="Health reports"
handler="health"
'''
with tempfile.TemporaryDirectory() as directory:
    path=Path(directory)/'tools.toml';path.write_text(config)
    tools=api.ToolMenu(path,handlers={'health':lambda:None})
    def root_menu(search,**options):
        assert search('')==['group:System controls','tool:health','navigation:back']
        assert search('  ')==search('')
        assert search('wall')==['tool:wallpaper']
        assert search('WÁLL')==['tool:wallpaper']
        assert search('system wall')==['tool:wallpaper']
        assert search('missing')==[]
        assert options['subtitles']['tool:wallpaper']=='System controls'
        assert options['labels']['tool:wallpaper']=='Wallpaper'
        return 'tool:wallpaper'
    ui.show_menu=root_menu
    with patch.dict(sys.modules,ui=ui),patch.object(tools,'invoke',return_value=True) as invoke:
        tools.run()
        invoke.assert_called_once_with(tools.tools['wallpaper'])
    def submenu(search,**options):
        assert search('')==['tool:wallpaper','tool:display','navigation:back']
        assert search('wall')==['tool:wallpaper']
        return api.BACK
    ui.show_menu=submenu
    with patch.dict(sys.modules,ui=ui):assert tools._level('System controls') is False
    # Ordinary menus retain the same filtering and blank-query behavior.
    def ordinary(search,**options):
        assert search('')==['one','two'];assert search('second')==['two']
        return 'two'
    ui.show_menu=ordinary
    with patch.dict(sys.modules,ui=ui):assert api.Menu().choose({'one':'First','two':'Second'})=='two'
print('PASS root submenu search, category context, direct invocation, Unicode, blank-query categories, normal submenu navigation')
