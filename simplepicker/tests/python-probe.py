"""Instrument the installed Python picker without changing its files."""
import sys,time
from pathlib import Path
sys.path.insert(0,str(Path.home()/'.local/lib/simplepicker'))
import wayland_ui
original_modules=wayland_ui.modules
patched=False
def modules():
    global patched
    result=original_modules()
    if not patched:
        patched=True
        Gtk,Gdk,GLib,_,_=result
        original_present=Gtk.Window.present
        def present(window):
            original_present(window)
            clock=window.get_frame_clock()
            def first(clock):
                clock.disconnect(first_id)
                print('BENCH first_us='+str(time.monotonic_ns()//1000),file=sys.stderr,flush=True)
                def change():
                    start=time.monotonic_ns()//1000
                    def filtered(clock):
                        clock.disconnect(filter_id)
                        print('BENCH filter_us='+str(time.monotonic_ns()//1000-start),file=sys.stderr,flush=True)
                        GLib.idle_add(lambda:(window.close(),False)[1])
                    filter_id=clock.connect('after-paint',filtered)
                    window.menu_entry.set_text('item 9')
                    return False
                GLib.idle_add(change)
            first_id=clock.connect('after-paint',first)
        Gtk.Window.present=present
    return result
wayland_ui.modules=modules
from main import main
raise SystemExit(main())
