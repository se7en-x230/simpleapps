"""Two compact timing lanes. SPDX-License-Identifier: GPL-3.0-or-later"""
from pathlib import Path
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk
from render import FPS


def spans(project):
    position=0
    result=[]
    for frames in project.frames:
        result.append((position/FPS,(position+frames)/FPS))
        position+=frames-project.fade
    return result


class Timeline(Gtk.DrawingArea):
    LEFT=72
    def __init__(self,select,reorder,seek):
        super().__init__();self.set_content_height(132);self.set_hexpand(True)
        self.project=None;self.position=0;self.selected=-1;self.select_item=select;self.reorder_item=reorder;self.seek_to=seek
        self.drag_index=None;self.drag_x=None;self.drag_start=(0,0)
        self.set_draw_func(self.draw)
        drag=Gtk.GestureDrag();drag.set_button(1);drag.connect('drag-begin',self.begin);drag.connect('drag-update',self.drag);drag.connect('drag-end',self.end);self.add_controller(drag)
        self.set_tooltip_text('Images: click to select; drag to reorder. Ruler or music: click/drag to seek. J/K also reorders the selected image.')
    def update(self,project,selected=-1):
        self.project=project;self.selected=selected
        self.position=min(self.position,project.seconds) if project else 0
        self.queue_draw()
    def set_position(self,seconds):self.position=max(0,seconds);self.queue_draw()
    def x(self,seconds):return self.LEFT+seconds/max(.001,self.project.seconds)*(self.get_width()-self.LEFT-10)
    def time(self,x):return max(0,min(self.project.seconds,(x-self.LEFT)/max(1,self.get_width()-self.LEFT-10)*self.project.seconds))
    def index_at(self,x):
        t=self.time(x)
        for i,(start,end) in reversed(list(enumerate(spans(self.project)))):
            if start<=t<=end:return i
        return len(self.project.items)-1
    def begin(self,gesture,x,y):
        if not self.project or x<self.LEFT:return
        self.drag_start=(x,y);self.drag_x=x
        self.drag_index=self.index_at(x) if 28<=y<76 else None
        if self.drag_index is not None:self.select_item(self.drag_index)
        else:self.set_position(self.time(x))
    def drag(self,gesture,dx,dy):
        if self.drag_x is None:return
        self.drag_x=self.drag_start[0]+dx
        if self.drag_index is None:self.set_position(self.time(self.drag_x))
        else:self.queue_draw()
    def end(self,gesture,dx,dy):
        if self.drag_x is None:return
        if self.drag_index is not None:
            if abs(dx)>8:self.reorder_item(self.drag_index,self.index_at(self.drag_start[0]+dx))
        else:self.seek_to(self.time(self.drag_start[0]+dx))
        self.drag_index=None;self.drag_x=None;self.queue_draw()
    def draw(self,widget,cr,width,height):
        fg=self.get_color();accent=Gdk.RGBA();accent.parse('#efa900')
        found,color=self.get_style_context().lookup_color('simple_panel_accent')
        if found:accent=color
        def ink(alpha=1):cr.set_source_rgba(fg.red,fg.green,fg.blue,alpha)
        def tint(alpha=1):cr.set_source_rgba(accent.red,accent.green,accent.blue,alpha)
        def text(x,y,value,size=11):cr.set_font_size(size);cr.move_to(x,y);cr.show_text(value)
        ink(.8);text(0,53,'Images');text(0,106,'Music')
        if not self.project:ink(.5);text(self.LEFT,53,'Add media to see its timing');return
        p=self.project
        for n in range(6):
            t=p.seconds*n/5;x=self.x(t)
            ink(.5);text(min(x,width-45),15,f'{int(t)//60}:{t%60:04.1f}',10)
            ink(.12);cr.rectangle(x,23,1,101);cr.fill()
        for i,((start,end),item) in enumerate(zip(spans(p),p.items)):
            x=self.x(start);w=max(1,self.x(end)-x)
            tint(.24 if i!=self.selected else .55);cr.rectangle(x,30,w,44);cr.fill()
            ink(.8);cr.rectangle(x+.5,30.5,max(0,w-1),43);cr.stroke()
            cr.save();cr.rectangle(x+3,31,max(0,w-6),42);cr.clip()
            ink();text(x+5,47,f'{i+1} · {Path(item.path).name}',11);text(x+5,64,f'{end-start:.1f}s',10);cr.restore()
            if i<len(p.items)-1:
                ink(.23);cr.rectangle(self.x(end-p.fade/FPS),30,max(1,self.x(end)-self.x(end-p.fade/FPS)),44);cr.fill()
        ink(.10);cr.rectangle(self.LEFT,84,width-self.LEFT-10,35);cr.fill()
        if p.music:
            tint(.25);cr.rectangle(self.LEFT,84,width-self.LEFT-10,35);cr.fill()
            duration=(p.music_out if p.music_out is not None else p.music.duration)-p.music_in
            # Repeat boundaries and final fade match the rendered soundtrack.
            t=duration
            while t<p.seconds and duration>0:
                ink(.35);cr.move_to(self.x(t),84);cr.line_to(self.x(t),119);cr.stroke();t+=duration
                if duration/p.seconds*(width-self.LEFT-10)<4:break
            fade=min(2,p.seconds/2);ink(.2);cr.move_to(self.x(p.seconds-fade),84);cr.line_to(self.x(p.seconds),119);cr.line_to(self.x(p.seconds),84);cr.close_path();cr.fill()
            cr.save();cr.rectangle(self.LEFT+4,84,width-self.LEFT-18,35);cr.clip();ink();text(self.LEFT+6,106,f'{Path(p.music.path).name} · In {p.music_in:.2f}s / Out {p.music_in+duration:.2f}s');cr.restore()
        else:ink(.6);text(self.LEFT+6,106,'No music · silent slideshow')
        tint();x=self.x(self.position);cr.set_line_width(2);cr.move_to(x,21);cr.line_to(x,124);cr.stroke();cr.set_line_width(1)
        if self.drag_index is not None and self.drag_x is not None:
            ink();cr.set_line_width(3);cr.move_to(self.drag_x,28);cr.line_to(self.drag_x,77);cr.stroke();cr.set_line_width(1)
