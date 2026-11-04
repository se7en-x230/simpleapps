"""Opt-in adapter injection, used only by run-tool."""
import os
if os.environ.get('SIMPLEPICKER_NATIVE_ADAPTER') == '1':
    import ui
