#!/usr/bin/env python3
"""Read Simpleplayer's TOML preferences without executing configuration."""
from pathlib import Path
import os
import sys
import tomllib


def configuration():
    explicit = os.environ.get('SIMPLEPLAYER_CONFIG')
    base = Path(os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config'))
    own = base / 'simpleplayer/config.toml'
    legacy = base / 'simplepicker/music/config.toml'
    path = (Path(os.path.expandvars(explicit)).expanduser() if explicit else
            own if own.exists() or not legacy.exists() else legacy)
    try:
        with path.open('rb') as source:
            values = tomllib.load(source)
    except FileNotFoundError:
        if explicit:
            raise ValueError(f'Config file not found: {path}')
        values = {}
    unknown = set(values) - {'music_dir', 'ui', 'visualizer'}
    if unknown:
        raise ValueError(f'Unknown setting in {path}: ' + ', '.join(sorted(unknown)))
    visualizer = values.get('visualizer', True)
    if type(visualizer) is not bool:
        raise ValueError('visualizer must be true or false')
    ui = values.get('ui', {})
    if not isinstance(ui, dict) or set(ui) - {'width', 'height', 'icon_size'}:
        raise ValueError('ui supports width, height, and icon_size')
    limits = {'width': (600, 400, 2000), 'height': (680, 300, 1600), 'icon_size': (28, 16, 64)}
    prefs = {}
    for name, (default, low, high) in limits.items():
        value = ui.get(name, default)
        if type(value) is not int or not low <= value <= high:
            raise ValueError(f'ui.{name} must be an integer from {low} to {high}')
        prefs[name] = value
    return path, values, prefs


def music_directory():
    path, values, _ = configuration()
    configured = values.get('music_dir', '~/Music')
    if not isinstance(configured, str) or not configured.strip():
        raise ValueError(f'music_dir in {path} must be a nonempty string')
    override = os.environ.get('SIMPLEPLAYER_MUSIC_DIR') or os.environ.get('WALKERBEATS_MUSIC_DIR')
    value = override or configured
    if any(char in value for char in '\0\n\r'):
        raise ValueError('Music directory cannot contain NUL or line breaks')
    result = Path(os.path.expandvars(value)).expanduser()
    if not result.is_absolute():
        result = (Path.cwd() if override else path.absolute().parent) / result
    return os.path.normpath(result)


if __name__ == '__main__':
    try:
        if sys.argv[1:]==["--visualizer"]:
            print("1" if configuration()[1].get("visualizer",True) else "0")
        else:
            print(music_directory())
    except (OSError, ValueError) as error:
        print(f'Simpleplayer config: {error}', file=sys.stderr)
        sys.exit(1)
