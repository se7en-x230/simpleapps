"""Exercise real GTK color inheritance, transient dialogs and explicit exceptions."""
import os
import sys
import tempfile
from pathlib import Path
root=Path(__file__).resolve().parents[1]
config=tempfile.TemporaryDirectory(prefix='simple-theme-check-')
os.environ['XDG_CONFIG_HOME']=config.name
folder=Path(config.name)/'simple';folder.mkdir()
(folder/'theme.css').write_text('@define-color simple_action_bg #ff9900;\n@define-color simple_action_fg #123456;\n')
(folder/'overrides.css').write_text('window.simple-app button.test-exception label { color: #abcdef; }')
sys.path.insert(0,str(root))
from simple_ui import attach
from gi.repository import Gtk, Gdk, GLib
app=Gtk.Application(application_id='org.simpleapps.ThemeCheck');passed=[]
def activate(app):
 win=Gtk.ApplicationWindow(application=app);attach(win)
 box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL);win.set_child(box)
 action=Gtk.Button(label='Action');box.append(action)
 exception=Gtk.Button(label='Exception');exception.add_css_class('test-exception');box.append(exception)
 tabs=Gtk.Box();tabs.add_css_class('simple-tabs');box.append(tabs)
 tab=Gtk.ToggleButton(label='Tab');tabs.append(tab)
 key=Gtk.Button(label='Key');key.add_css_class('keycap');box.append(key)
 # Reproduce app CSS that explicitly colors labels, as Simplemail used to do.
 css=Gtk.CssProvider();css.load_from_string('.simplemail label:not(.heading) { color: white; }')
 Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),css,802)
 dialog=Gtk.Window(transient_for=win);dialog.add_css_class('simplemail')
 nested=Gtk.Button(label='Attachment.pdf');dialog.set_child(nested)
 win.present();dialog.present()
 def color(widget):
  c=widget.get_style_context().get_color();return tuple(round(v*255) for v in (c.red,c.green,c.blue))
 def check():
  try:
   assert dialog.has_css_class('simple-app')
   for b in (action,nested):assert color(b.get_child())==(18,52,86),color(b.get_child())
   assert color(exception.get_child())==(171,205,239)
   for b in (tab,key):assert color(b.get_child())==(228,222,210),color(b.get_child())
   tab.set_active(True)
   assert color(tab.get_child())==(18,52,86)
   action.set_state_flags(Gtk.StateFlags.PRELIGHT,False)
   assert color(action.get_child())==(18,52,86)
   passed.append(True)
  finally:dialog.destroy();win.destroy();app.quit()
  return False
 GLib.timeout_add(250,check)
app.connect('activate',activate);app.run([])
assert passed
print('PASS shared action text, hover, tabs, keycaps, transient dialog inheritance and explicit override')
