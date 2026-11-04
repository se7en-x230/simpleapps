"""Shared Vim navigation for dashboard detail/control windows."""
import os as _path_os, sys as _path_sys
from pathlib import Path as _Path
_roots=[_Path(__file__).resolve().parents[3],_Path(_path_os.environ.get('XDG_DATA_HOME',_Path.home()/'.local/share')),_Path.home()/'.local/src']
if _path_os.environ.get('SIMPLE_SOURCE_ROOT'):_roots.insert(0,_Path(_path_os.environ['SIMPLE_SOURCE_ROOT']))
for _root in reversed(_roots):
    for _name in ('simplepicker/python','simple-common'):
        if (_root/_name).is_dir():_path_sys.path.insert(0,str(_root/_name))
from pathlib import Path
import sys
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib
from keybindings import KeyBindings

HINT = KeyBindings().hint() + ' · gg/G First/last · yy Copy · r Refresh'


def descendants(widget):
    child=widget.get_first_child()
    while child:
        yield child
        yield from descendants(child)
        child=child.get_next_sibling()


class Navigation:
    def __init__(self,window,refresh=None,header=None):
        self.keys=KeyBindings()
        self.window,self.refresh=window,refresh
        self.header=header
        self.index=0;self.pending=None;self.stamp=0
        keys=Gtk.EventControllerKey();keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect('key-pressed',self.key);window.add_controller(keys)

    def cards(self):
        return [w for w in descendants(self.window) if w.has_css_class('sound-card') and w.get_mapped()]

    def current(self,cards):
        focus=self.window.get_focus()
        for i,card in enumerate(cards):
            if focus==card or (focus and focus.is_ancestor(card)):return i
        return min(self.index,max(0,len(cards)-1))

    def select(self,index,focus=True):
        cards=self.cards()
        if not cards:return
        self.index=max(0,min(index,len(cards)-1))
        for i,card in enumerate(cards):
            if i==self.index:card.add_css_class('info-selected')
            else:card.remove_css_class('info-selected')
        card=cards[self.index];card.set_focusable(True)
        if focus:card.grab_focus()

    def header_controls(self):
        cards=self.cards();controls=[]
        for widget in descendants(self.window):
            if not (widget.get_mapped() and widget.get_sensitive() and isinstance(widget,(Gtk.Button,Gtk.DropDown,Gtk.Scale))):continue
            if any(widget==c or widget.is_ancestor(c) for c in cards):continue
            if any(widget.is_ancestor(c) for c in controls):continue
            controls.append(widget)
        actions=[c for c in controls if not (isinstance(c,Gtk.Button) and (c.get_icon_name()=='window-close-symbolic' or c.get_label()=='Close'))]
        return actions or controls

    def move_horizontal(self,delta):
        controls=self.header_controls();focus=self.window.get_focus()
        index=next((i for i,c in enumerate(controls) if focus==c or (focus and focus.is_ancestor(c))),None)
        if index is not None:
            self.window.set_focus_visible(True)
            controls[max(0,min(index+delta,len(controls)-1))].grab_focus()
            return
        self.window.child_focus(Gtk.DirectionType.TAB_FORWARD if delta>0 else Gtk.DirectionType.TAB_BACKWARD)
        self.select(self.current(self.cards()),focus=False)

    def move_vertical(self,delta):
        cards=self.cards();controls=self.header_controls();focus=self.window.get_focus()
        inside=bool(focus and any(focus==c or focus.is_ancestor(c) for c in cards))
        if inside:
            index=self.current(cards)
            if index==0 and delta<0 and controls:target=controls[-1]
            else:self.select(index+delta);return
        else:
            index=next((i for i,c in enumerate(controls) if focus==c or (focus and focus.is_ancestor(c))),-1)
            if index+delta>=len(controls) or (index<0 and delta>0):self.select(0);return
            if not controls:return
            target=controls[max(0,index+delta)]
        for card in cards:card.remove_css_class('info-selected')
        self.window.set_focus_visible(True);target.grab_focus()

    def focus_header(self):
        cards = self.cards()
        self.index = 0
        for card in cards: card.remove_css_class('info-selected')
        self.window.set_focus_visible(True)
        if self.header and self.header.get_mapped() and self.header.get_sensitive():
            self.header.grab_focus()
            return
        for widget in descendants(self.window):
            if (widget.get_mapped() and widget.get_sensitive()
                    and isinstance(widget, (Gtk.Button, Gtk.DropDown, Gtk.Scale))
                    and not any(widget == card or widget.is_ancestor(card) for card in cards)):
                widget.grab_focus()
                return

    def copy(self,all_cards=False):
        cards=self.cards()
        if not cards:return
        if not all_cards:cards=[cards[self.current(cards)]]
        values=[]
        for card in cards:
            text=[]
            for widget in descendants(card):
                if not widget.get_mapped():continue
                if isinstance(widget,Gtk.Label) and not isinstance(widget.get_parent(),Gtk.Button):
                    value=widget.get_text().strip()
                    if value and value not in text:text.append(value)
                elif isinstance(widget,Gtk.Scale):text.append(f'{widget.get_value():g}%')
            values.append('\n'.join(text))
        from simplepicker_api import copy_text
        copy_text('\n\n'.join(values),title=self.window.get_title())

    def key(self,controller,key,code,state):
        if self.keys.matches("cancel",key,state):self.window.close();return True
        focus=self.window.get_focus()
        editing=isinstance(focus,(Gtk.Entry,Gtk.TextView,Gtk.Editable))
        for action,move,delta in [('down',self.move_vertical,1),('up',self.move_vertical,-1),('left',self.move_horizontal,-1),('right',self.move_horizontal,1)]:
            if self.keys.matches(action,key,state,editing):move(delta);return True
        if editing:return False
        if self.keys.matches("page_down",key,state):self.select(self.current(self.cards())+5);return True
        if self.keys.matches("page_up",key,state):self.select(self.current(self.cards())-5);return True
        if state&(Gdk.ModifierType.CONTROL_MASK|Gdk.ModifierType.ALT_MASK|Gdk.ModifierType.SUPER_MASK):
            self.pending=None;return False
        now=GLib.get_monotonic_time();previous=self.pending if now-self.stamp<2000000 else None;self.pending=None
        cards=self.cards();current=self.current(cards)
        if key==Gdk.KEY_g:
            if previous==key:self.select(0)
            else:self.pending,self.stamp=key,now
            return True
        if key==Gdk.KEY_G:self.select(len(cards)-1);return True
        if key==Gdk.KEY_y:
            if previous==key:self.copy()
            else:self.pending,self.stamp=key,now
            return True
        if key==Gdk.KEY_Y:self.copy(all_cards=True);return True
        if key==Gdk.KEY_r and self.refresh:self.refresh();return True
        if key==Gdk.KEY_q:self.window.close();return True
        if (self.keys.matches("activate",key,state) or key==Gdk.KEY_space) and focus in cards:
            for widget in descendants(focus):
                if widget.get_mapped() and widget.get_sensitive() and isinstance(widget,(Gtk.Button,Gtk.Scale,Gtk.DropDown)):
                    widget.grab_focus();return True
        return False


def install_navigation(window,refresh=None,header=None):
    window._vim_navigation=Navigation(window,refresh,header)
    return window._vim_navigation


def install_dialog_navigation(window):
    """Use shared navigation for small dialogs, including editable inputs."""
    bindings = KeyBindings('network')
    def key(controller, keyval, code, state):
        if bindings.matches('cancel', keyval, state):
            window.close()
            return True
        focus = window.get_focus()
        editing = isinstance(focus, (Gtk.Editable, Gtk.TextView))
        for action, direction in (('up', Gtk.DirectionType.TAB_BACKWARD),
                                  ('left', Gtk.DirectionType.TAB_BACKWARD),
                                  ('down', Gtk.DirectionType.TAB_FORWARD),
                                  ('right', Gtk.DirectionType.TAB_FORWARD)):
            if bindings.matches(action, keyval, state, editing):
                window.set_focus_visible(True)
                window.child_focus(direction)
                return True
        if bindings.matches('activate', keyval, state, editing) and isinstance(focus, Gtk.Button):
            focus.emit('clicked')
            return True
        return False
    controller = Gtk.EventControllerKey()
    controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
    controller.connect('key-pressed', key)
    window.add_controller(controller)
    return controller
