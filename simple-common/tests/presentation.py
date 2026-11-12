"""Shared appearance applies to initial and dynamically mapped GTK controls."""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from simple_ui import attach
from gi.repository import Gtk,GLib
app=Gtk.Application(application_id='org.simpleapps.PresentationTest');passed=[]
def activate(app):
 win=Gtk.ApplicationWindow(application=app,title='Shared appearance check');attach(win);win.set_default_size(760,420)
 root=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=12);root.add_css_class('root');win.set_child(root)
 title=Gtk.Label(label='Simpleapps',xalign=0);title.add_css_class('title');root.append(title)
 tabs=Gtk.Box(spacing=5);tabs.add_css_class('simple-tabs');root.append(tabs)
 tab=Gtk.ToggleButton(label='Keyboard [1]');other=Gtk.ToggleButton(label='Layout [2]');other.set_group(tab);tabs.append(tab);tabs.append(other);tab.set_active(True)
 split=Gtk.Paned();root.append(split);split.set_vexpand(True)
 listing=Gtk.ListBox();left=Gtk.ScrolledWindow();left.set_child(listing);split.set_start_child(left)
 for name in ['First row','Second row','Third row']:listing.append(Gtk.Label(label=name,xalign=0))
 listing.select_row(listing.get_row_at_index(1))
 right=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=8);split.set_end_child(right)
 view=Gtk.TextView(editable=False);view.get_buffer().set_text('Details use the same card surface.');scroll=Gtk.ScrolledWindow();scroll.set_child(view);right.append(scroll)
 button=Gtk.Button(label='Save [Ctrl+S]');root.append(button)
 win.present()
 def check():
  try:
   snapshot=Gtk.Snapshot();Gtk.WidgetPaintable.new(win).snapshot(snapshot,win.get_width(),win.get_height())
   win.get_renderer().render_texture(snapshot.to_node(),None).save_to_png('/tmp/simpleapps-presentation.png')
   assert left.has_css_class('pane') and right.has_css_class('pane')
   label=button.get_child();assert 'foreground' in label.get_attributes().to_string()
   button.set_label('Done');assert 'foreground' not in button.get_child().get_attributes().to_string()
   button.set_label('Save · Ctrl+S');assert 'foreground' in button.get_child().get_attributes().to_string()
   before=tab.get_child().get_attributes().to_string();other.set_active(True)
   assert before!=tab.get_child().get_attributes().to_string()
   new=Gtk.Button(label='New · n');root.append(new)
   assert 'foreground' in new.get_child().get_attributes().to_string()
   passed.append(True)
  finally:win.destroy();app.quit()
  return False
 GLib.timeout_add(300,check)
app.connect('activate',activate);app.run([]);assert passed
print('PASS shared pane cards, shortcut colors, changed captions, tab state and dynamic actions')
