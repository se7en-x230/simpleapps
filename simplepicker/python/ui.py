"""Compatibility for personal Python tools; all GTK rendering happens in C."""
import base64
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import unicodedata

def normalize(text):
    return ''.join(c for c in unicodedata.normalize('NFKD', text.casefold()) if not unicodedata.combining(c))

def line_search(lines):
    entries = [(line, normalize(line)) for line in lines]
    return lambda query: [line for line, text in entries if all(word in text for word in normalize(query).split())]

def theme_path(override=None, *, kind='menu'):
    selected = override or os.environ.get('SIMPLEPICKER_THEME')
    path = Path(os.path.expandvars(str(selected))).expanduser() if selected else Path(os.environ.get('XDG_CONFIG_HOME', Path.home()/'.config'))/'simplepicker'/('power/style.css' if kind == 'power' else 'style.css')
    if selected and not path.is_file():
        raise ValueError(f'Theme file does not exist: {path}')
    return path if path.is_file() else None

def show_menu(search, *, prompt='Search', title='simplepicker', width=600, height=570,
              actions=(), initial='', input_only=False, password=False, selected_row=0, font_rows=False,
              icons=None, image_preview=None, preview_rows=(), labels=None, subtitles=None, icon_size=24,
              shortcuts=(), on_select=None, default_icon='view-list-symbolic', row_shortcuts=(),
              text_preview=None, font_sample=None, theme=None, keys=None, key_scope=None, auto_accept=False):
    executable = os.environ.get('SIMPLEPICKER_NATIVE', shutil.which('simplepicker-native') or str(Path(__file__).resolve().parent.parent/'simplepicker-native'))
    argv = [executable, '--bridge']
    # A Python tool may already have selected an alternate configuration.
    try:
        import settings
        argv += ['--config', str(settings.path())] if settings.path().is_file() else []
    except ImportError:
        pass
    selected_theme = theme_path(theme)
    values, tokens = {}, {}
    def token(value):
        if value not in tokens:
            key = str(len(values)); tokens[value] = key; values[key] = value
        return tokens[value]
    def special(value):
        key = 'result:' + str(len(values)); values[key] = value; return key
    shortcut_values = {key: value for key, _, value in shortcuts}
    callbacks = {key: callback for key, _, callback in row_shortcuts}
    captions = {key: caption for key, caption, _ in [*shortcuts, *row_shortcuts]}
    preview_rows = set(preview_rows)
    if key_scope is None:
        config_root=Path(os.environ.get('XDG_CONFIG_HOME',Path.home()/'.config'))/'simplepicker'
        try:
            relative=Path(sys.argv[0]).resolve().relative_to(config_root)
            if len(relative.parts)>1:key_scope=relative.parts[0]
        except ValueError:pass
    init = dict(title=title, prompt=prompt, width=width, height=height, input_only=input_only,
                password=password, selected_row=selected_row, initial=initial, icon=default_icon or '',
                icon_size=icon_size, font_rows=font_rows, sample=font_sample or '',
                previews=image_preview is not None or text_preview is not None, shortcuts=captions,
                theme=str(selected_theme) if selected_theme else '',
                keys=str(keys) if keys else '', key_scope=key_scope or '')
    process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)
    def send(data):
        process.stdin.write(json.dumps(data, ensure_ascii=False) + '\n'); process.stdin.flush()
    result = None
    try:
        send(init)
        for line in process.stdout:
            message = json.loads(line)
            event, query = message['event'], message.get('query', '')
            selected = values.get(message.get('id'))
            if event == 'closed':
                if message.get('error'):
                    raise RuntimeError(message['error'])
                result = values.get(message.get('result'))
                break
            if event == 'search':
                paths = [] if input_only or password else [*search(query)[:200], *actions]
                # Opt in only for action menus: never accept the initial/empty search.
                if auto_accept and query.strip() and len(paths) == 1:
                    if on_select is None or not on_select(paths[0]):
                        send({'result': token(paths[0])})
                        continue
                rows = []
                for value in paths:
                    icon = icons.get(value) if icons is not None else None
                    row = dict(id=token(value), label=labels.get(value, value) if labels is not None else value,
                               subtitle=subtitles.get(value, '') if subtitles is not None else '')
                    if isinstance(icon, str): row['icon'] = icon
                    elif icon is not None: row['gicon'] = icon.to_string()
                    if font_rows: row['font'] = value
                    rows.append(row)
                send({'rows': rows})
            elif event == 'preview':
                payload = {}
                try:
                    if selected in preview_rows and image_preview:
                        data = image_preview(selected)
                        if data: payload = {'image': base64.b64encode(data).decode('ascii')}
                    elif text_preview and selected is not None:
                        payload = {'text': text_preview(selected) or ''}
                except Exception:
                    pass
                send(payload)
            elif event == 'activate':
                action = message.get('action', 'enter')
                if action in shortcut_values:
                    send({'result': special(shortcut_values[action])})
                elif action in callbacks:
                    change = callbacks[action](selected, query) or {}
                    if 'result' in change: send({'result': special(change['result'])})
                    elif change.get('close'): send({'close': True})
                    else: send({'keep': True, **({'query': change['query']} if 'query' in change else {})})
                elif input_only or password:
                    send({'result': special(query)})
                elif selected is None:
                    send({'keep': True})
                elif on_select is not None and on_select(selected):
                    send({'keep': True, 'query': ''})
                else:
                    send({'result': token(selected)})
            else:
                raise RuntimeError('Unknown native menu event: ' + event)
        code = process.wait(timeout=5)
        if code not in (0, 1): raise RuntimeError(f'Native menu exited with status {code}')
        return result
    finally:
        if process.poll() is None:
            process.terminate()
            try: process.wait(timeout=3)
            except subprocess.TimeoutExpired: process.kill(); process.wait()
        process.stdin.close(); process.stdout.close()
