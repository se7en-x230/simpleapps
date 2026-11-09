from pathlib import Path
from datetime import date,datetime,timedelta
import sys,subprocess,threading,calendar
import gi
gi.require_version('Gtk','4.0')
from gi.repository import Gtk,Gdk,GLib,Gio
import core,layers,preferences
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/'simple-common'))
from theme_loader import load_css

REMINDERS=[0,15,30,60,1440,10080,14400,40320]

from simple_keyboard import control_key

def children(box):
    w=box.get_first_child()
    while w:
        next_w=w.get_next_sibling();yield w;w=next_w

def label(text,style=None):
    w=Gtk.Label(label=text,xalign=0,wrap=True);w.set_max_width_chars(55)
    if style:w.add_css_class(style)
    return w

def button(text,callback):
    w=Gtk.Button(label=text);w.connect('clicked',callback);return w

def box(vertical=True,spacing=6):return Gtk.Box(orientation=Gtk.Orientation.VERTICAL if vertical else Gtk.Orientation.HORIZONTAL,spacing=spacing)
def margins(w,n=12):
    for p in ('top','bottom','start','end'):getattr(w,'set_margin_'+p)(n)

def run(day):
    class App(Gtk.Application):
        def __init__(self):
            super().__init__(application_id='space.go7.SimpleCalendar',flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
            self.connect('command-line',self.command);self.connect('activate',self.activate)
            self.win=None;self.selected=date.fromisoformat(day);self.busy=False;self.editor=None;self.event_index=0;self.cards=[];self.view_stamp=None;self.prefs=preferences.Preferences();self.theme_stamp=None
        def command(self,app,cmd):
            args=cmd.get_arguments()
            if '--day' in args:
                try:self.selected=date.fromisoformat(args[args.index('--day')+1])
                except (ValueError,IndexError):return 1
            self.activate()
            self.cal.select_day(GLib.DateTime.new_local(self.selected.year,self.selected.month,self.selected.day,12,0,0))
            self.refresh();return 0
        def activate(self,*_):
            if self.win:self.win.present();return
            self.win=Gtk.ApplicationWindow(application=self,title='SimpleCalendar');self.win.set_default_size(self.prefs.number('width',800,700,2000),self.prefs.number('height',520,440,1400))
            self.win.add_css_class('simple-calendar-app')
            self.app_css=Gtk.CssProvider();self.layout_css=Gtk.CssProvider();self.global_css=Gtk.CssProvider()
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.layout_css,802)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.global_css,801)
            Gtk.StyleContext.add_provider_for_display(Gdk.Display.get_default(),self.app_css,803)
            self.reload_theme()
            outer=box();margins(outer);self.win.set_child(outer)
            top=box(False);outer.append(top);title=label('SimpleCalendar','heading');title.set_hexpand(True);top.append(title)
            top.append(button('Today',self.today));top.append(button('Sync',lambda _:self.background(core.sync)))
            top.append(button('Accounts',self.accounts));add=button('+ Event',lambda _:self.edit());add.add_css_class('primary');top.append(add)
            self.status=label('','muted');outer.append(self.status)
            body=box(False,12);body.set_homogeneous(True);body.set_vexpand(True);outer.append(body)
            left=box();body.append(left)
            self.cal=Gtk.Calendar();self.cal.set_valign(Gtk.Align.START);left.append(self.cal)
            self.calendar_size=Gtk.SizeGroup(mode=Gtk.SizeGroupMode.BOTH);self.calendar_size.add_widget(self.cal)
            self.cal.connect('day-selected',self.select)
            for signal in ('next-month','prev-month','next-year','prev-year'):self.cal.connect(signal,lambda *_:self.mark())
            self.legend_label=label('Orange ● full moon · Red ● next report','muted');left.append(self.legend_label)
            self.legend_size=Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL);self.legend_size.add_widget(self.legend_label)
            self.local=Gtk.CheckButton(label='Local holidays, full moons & parties',active=True)
            self.local.connect('toggled',lambda _:self.refresh())
            self.report_button=button('90-day report',lambda _:self.edit(report=True));self.report_button.set_margin_top(12);left.append(self.report_button)
            self.action_size=Gtk.SizeGroup(mode=Gtk.SizeGroupMode.VERTICAL);self.action_size.add_widget(self.report_button)
            right=box();right.set_hexpand(True);body.append(right)
            controls=box(False,12);controls.set_homogeneous(True);outer.insert_child_after(controls,self.status);self.heading=label('','heading');self.heading.set_hexpand(True);controls.append(self.heading)
            self.empty_caption=label('Nothing is scheduled','heading');self.empty_caption.set_hexpand(True);controls.append(self.empty_caption)
            self.agenda_days=self.prefs.number('agenda_days',30,1,90)
            self.mode=Gtk.DropDown.new_from_strings(['Selected day',f'Next {self.agenda_days} days']);top.insert_child_after(self.mode,title)
            self.mode.set_selected(1 if self.prefs.config.get('calendar','view',fallback='day')=='agenda' else 0)
            self.mode.connect('notify::selected',lambda *_:self.refresh())
            scroll=Gtk.ScrolledWindow(vexpand=True,hexpand=True);right.append(scroll);self.list=box();scroll.set_child(self.list)
            outer.append(self.local)
            outer.append(label(self.prefs.legend(),'muted'))
            self.bind_keys(self.win)
            self.win.present();GLib.timeout_add_seconds(self.prefs.number('refresh_seconds',15,5,300),self.tick)
        def bind_keys(self,window,dialog=False):
            controller=Gtk.EventControllerKey();controller.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
            controller.connect('key-pressed',lambda c,key,code,state:self.keys(window,key,state,dialog))
            window.add_controller(controller)
        def keys(self,window,key,state,dialog=False):
            handled = control_key(window, key, state)
            if handled is not None: return handled
            nav=lambda action:self.prefs.matches('navigation',action,key,state)
            action=lambda name:self.prefs.matches('calendar',name,key,state)
            if dialog:
                if nav('cancel'):window.close();return True
                if action('save') and window==self.editor:
                    if self.editor_save.get_sensitive():self.editor_save.emit('clicked')
                    return True
                return False
            focus=window.get_focus();node=focus
            while node:
                if isinstance(node,(Gtk.Editable,Gtk.TextView)):return False
                node=node.get_parent()
            # App actions take precedence, followed by inherited navigation.
            if action('previous_month') or action('next_month') or nav('page_up') or nav('page_down'):
                step=-1 if action('previous_month') or nav('page_up') else 1
                month=self.selected.year*12+self.selected.month-1+step;y,m=divmod(month,12);m+=1
                self.go_date(date(y,m,min(self.selected.day,calendar.monthrange(y,m)[1])));return True
            if action('next_event') or action('previous_event'):
                if self.cards:
                    self.event_index=max(0,min(len(self.cards)-1,self.event_index+(1 if action('next_event') else -1)))
                    self.highlight();self.cards[self.event_index][0].grab_focus()
                return True
            for name,callback in [('edit',lambda:self.open_selected(edit=True)),('new',self.edit),('today',lambda:self.today(None)),
                                  ('agenda',lambda:self.mode.set_selected(1-self.mode.get_selected())),('sync',lambda:self.background(core.sync)),
                                  ('delete',self.delete_selected),('accounts',self.accounts),('help',self.help),('quit',window.close)]:
                if action(name):callback();return True
            for name,offset in [('left',-1),('right',1),('down',7),('up',-7)]:
                if action('day_'+name):self.go_date(self.selected+timedelta(days=offset));return True
            for name,direction in [('left',Gtk.DirectionType.LEFT),('right',Gtk.DirectionType.RIGHT),('up',Gtk.DirectionType.UP),('down',Gtk.DirectionType.DOWN)]:
                if nav(name):window.child_focus(direction);return True
            if nav('activate'):
                if isinstance(focus,(Gtk.Button,Gtk.CheckButton,Gtk.DropDown)):return False
                self.open_selected();return True
            if nav('cancel'):window.close();return True
            return False
        def go_date(self,day):
            self.selected=day;self.event_index=0
            self.cal.select_day(GLib.DateTime.new_local(day.year,day.month,day.day,12,0,0));self.refresh()
        def track_card(self,card,event):
            index=len(self.cards);self.cards.append((card,event));card.set_focusable(True)
            focus_controller=Gtk.EventControllerFocus()
            def focused(*_):self.event_index=index;self.highlight()
            focus_controller.connect('enter',focused);card.add_controller(focus_controller)
            gesture=Gtk.GestureClick()
            def select(*_):self.event_index=index;self.highlight()
            gesture.connect('pressed',select);card.add_controller(gesture)
        def highlight(self):
            self.event_index=min(self.event_index,max(0,len(self.cards)-1))
            for i,(card,_) in enumerate(self.cards):
                if i==self.event_index:card.add_css_class('active-event')
                else:card.remove_css_class('active-event')
        def open_selected(self,edit=False):
            if not self.cards:return
            e=self.cards[self.event_index][1]
            if 'layer' in e:
                w,content=self.dialog('Calendar date');content.append(label(e['day'].strftime('%d %B %Y'),'heading'))
                content.append(label(e['title']));content.append(label(e['layer']+' · local, read-only','muted'))
                content.append(button('Close',lambda _:w.close()));w.present()
            elif edit:
                if e.get('editable',False):self.edit(e)
                else:self.detail(e)
            else:self.detail(e)
        def help(self):
            w,content=self.dialog('Keyboard shortcuts')
            content.append(label('Vim navigation','heading'))
            for section,actions in self.prefs.keys.items():
                for action,keys in actions.items():content.append(label(action.replace('_',' ').title()+' — '+(keys or 'disabled')))
            content.append(label('Navigation inherits simple/keys.ini. Optional overrides: simplecalendar/keys.ini. Text fields retain normal typing.','muted'))
            content.append(button('Close',lambda _:w.close()));w.present()
        def today(self,_):
            self.selected=date.today();self.cal.select_day(GLib.DateTime.new_now_local());self.refresh()
        def select(self,*_):
            d=self.cal.get_date();self.selected=date(d.get_year(),d.get_month(),d.get_day_of_month());self.refresh()
        def mark(self):
            if not hasattr(self,'local'):return
            d=self.cal.get_date();a=date(d.get_year(),d.get_month(),1);b=(a+timedelta(days=32)).replace(day=1)
            rows,_=core.view_events(core.local_dt(a),core.local_dt(b));local=layers.events(a,b) if self.local.get_active() else []
            self.cal.clear_marks()
            for n in range(1,calendar.monthrange(a.year,a.month)[1]+1):
                day=a.replace(day=n)
                if any(core.on_day(e,day) for e in rows) or any(e['day']==day for e in local):self.cal.mark_day(n)
            upcoming=core.next_report(core.read_json('agenda.json',[]))
            report_day=date.fromisoformat(upcoming) if upcoming else None
            report=report_day.day if report_day and a<=report_day<b else None
            self.moon_marks(self.cal,{e['day'].day for e in local if e['layer']=='Full moon'},report)
        def moon_marks(self,widget,days,report=None):
            if isinstance(widget,Gtk.Label) and widget.has_css_class('day-number'):
                number=widget.get_text().split(' ',1)[0]
                if number.isdigit():
                    marked=int(number) in days and not widget.has_css_class('other-month')
                    report_mark=int(number)==report and not widget.has_css_class('other-month')
                    dots=[]
                    if marked:
                        widget.add_css_class('simple-calendar-moon')
                        found,color=widget.get_style_context().lookup_color('simple_calendar_moon')
                        ink=('#%02x%02x%02x' % (round(color.red*255),round(color.green*255),round(color.blue*255))) if found else '#e9a04b'
                        dots.append(f'<span foreground="{ink}">●</span>')
                    else:
                        widget.remove_css_class('simple-calendar-moon')
                    if report_mark:
                        found,color=widget.get_style_context().lookup_color('simple_calendar_report')
                        ink=color.to_string() if found else '#e66565'
                        dots.append(f'<span foreground="{ink}">●</span>')
                    widget.set_markup(number+(' '+''.join(dots) if dots else ''))
            for child in children(widget):self.moon_marks(child,days,report)
        def refresh(self):
            if not hasattr(self,'list'):return
            try:
                a=self.selected;b=a+timedelta(days=self.agenda_days if self.mode.get_selected() else 1)
                rows,errors=core.view_events(core.local_dt(a),core.local_dt(b));local=layers.events(a,b) if self.local.get_active() else []
                self.heading.set_text(a.strftime('%d %B %Y'))
                stamp=repr((a,b,rows,local,self.mode.get_selected(),core.read_json('sync.json',{})))
                if stamp==self.view_stamp:
                    self.mark();return
                self.view_stamp=stamp
                for w in children(self.list):self.list.remove(w)
                count=0;self.cards=[]
                for offset in range((b-a).days):
                    current=a+timedelta(days=offset);daily=[e for e in rows if core.on_day(e,current)];extras=[e for e in local if e['day']==current]
                    if not daily and not extras:continue
                    if self.mode.get_selected():self.list.append(label(current.strftime('%A · %d %B'),'heading'))
                    for e in daily:
                        card=box();card.add_css_class('card');self.list.append(card);self.track_card(card,e)
                        at=datetime.fromisoformat(e['start']);end=datetime.fromisoformat(e['end'])
                        when='All day' if e['all_day'] else at.strftime('%H:%M')+' – '+end.strftime('%H:%M')
                        card.append(label(when+' · '+e['title']))
                        actions=box(False);card.append(actions)
                        meta=label(e['calendar']+(' · repeating' if e['recurring'] else ''),'muted');meta.set_hexpand(True);actions.append(meta)
                        actions.append(button('Details',lambda _,e=e:self.detail(e)))
                        if e.get('editable',False):actions.append(button('Edit',lambda _,e=e:self.edit(e)))
                        count+=1
                    for e in extras:
                        card=box();card.add_css_class('card');self.track_card(card,e);card.append(label(e['title'],'moon' if e['layer']=='Full moon' else 'buddhist' if e['layer']=='Thai Buddhist' else None));card.append(label(e['layer']+' · local, read-only','muted'));self.list.append(card);count+=1
                self.empty_caption.set_visible(not count)
                if not count:
                    empty=box();empty.set_hexpand(True)
                    if not hasattr(self,'empty_picture'):
                        path=Path(__file__).with_name('assets')/'matrix-monk-wide.png'
                        self.empty_picture=Gtk.Picture.new_for_filename(str(path))
                        self.empty_picture.set_content_fit(Gtk.ContentFit.CONTAIN)
                        self.empty_picture.set_can_shrink(True)
                    if hasattr(self,'image_card'):
                        self.calendar_size.remove_widget(self.image_card)
                        self.image_card.remove_overlay(self.empty_picture)
                    self.image_card=Gtk.Overlay();self.image_card.add_css_class('monk-card')
                    self.image_card.set_overflow(Gtk.Overflow.HIDDEN)
                    self.image_card.set_valign(Gtk.Align.START)
                    self.image_card.set_child(box())
                    self.empty_picture.set_halign(Gtk.Align.FILL);self.empty_picture.set_valign(Gtk.Align.FILL)
                    margins(self.empty_picture,12)
                    self.image_card.add_overlay(self.empty_picture)
                    self.calendar_size.add_widget(self.image_card)
                    empty.append(self.image_card)
                    if hasattr(self,'empty_legend_spacer'):self.legend_size.remove_widget(self.empty_legend_spacer)
                    self.empty_legend_spacer=box();self.legend_size.add_widget(self.empty_legend_spacer);empty.append(self.empty_legend_spacer)
                    if hasattr(self,'breath_card'):self.action_size.remove_widget(self.breath_card)
                    reflection=box();reflection.set_margin_top(12);reflection.add_css_class('breath-card');self.breath_card=reflection;self.action_size.add_widget(reflection)
                    text=label('Sit and follow the breath');text.set_halign(Gtk.Align.CENTER)
                    reflection.append(text);empty.append(reflection)
                    self.list.append(empty)
                state=core.read_json('sync.json',{});settings=core.settings()
                text='Local calendar layers · Google / CalDAV not connected' if not settings else 'Changes saved locally · waiting to sync' if state.get('pending') else 'Synced' if state.get('ok') else 'Not synced yet'
                if state.get('last') and state.get('ok'):text+=' · '+datetime.fromisoformat(state['last']).astimezone().strftime('%d %b %H:%M')
                if state.get('error'):text=state['error']
                if errors:text+=' · unreadable calendar files'
                if not self.busy:self.status.set_text(text)
                self.mark();self.highlight()
            except Exception as exc:self.status.set_text(str(exc))
        def reload_theme(self):
            paths=[preferences.ROOT/'simple/theme.css',preferences.ROOT/'simple/aliases.css',preferences.APP/'style.css']
            stamp=tuple(p.stat().st_mtime_ns if p.exists() else None for p in paths)
            if stamp!=self.theme_stamp:
                load_css(self.app_css,preferences.APP/'style.css')
                shared=preferences.ROOT/'simple/aliases.css'
                self.global_css.load_from_path(str(shared if shared.exists() else preferences.ROOT/'simple/theme.css'))
                self.layout_css.load_from_path(str(Path(__file__).with_name('style.css')))
                self.theme_stamp=stamp
        def tick(self):
            self.reload_theme()
            if not self.win.get_visible():return False
            if not self.busy:self.refresh()
            return True
        def dialog(self,title,width=520):
            w=Gtk.Window(title=title,transient_for=self.win,modal=True,default_width=width);w.add_css_class('simple-calendar-app')
            content=box();margins(content);scroll=Gtk.ScrolledWindow(propagate_natural_height=True,max_content_height=620);scroll.set_child(content);w.set_child(scroll)
            self.bind_keys(w,dialog=True)
            return w,content
        def background(self,work,after=None):
            if self.busy:return
            self.busy=True;self.hold();self.status.set_text('Working…')
            def worker():
                try:work();error=None
                except Exception as exc:error=str(exc)
                def done():
                    self.busy=False;self.view_stamp=None;self.refresh()
                    if error:
                        self.status.set_text(error)
                        if self.editor:self.editor_error.set_text(error);self.editor_save.set_sensitive(True)
                    elif after:after()
                    self.release()
                    return False
                GLib.idle_add(done)
            threading.Thread(target=worker,daemon=True).start()
        def edit(self,e=None,report=False):
            if self.busy:return
            if self.editor:self.editor.present();return
            if not core.settings():self.accounts();return
            w,form=self.dialog('90-day immigration report' if report else 'Edit event' if e else 'New event');self.editor=w
            w.connect('close-request',lambda *_:setattr(self,'editor',None) or False)
            def entry(name,value):
                form.append(label(name,'muted'));v=Gtk.Entry(text=value);form.append(v);return v
            base=None
            if report:
                base=entry('Last report / entry date · YYYY-MM-DD',self.selected.isoformat())
                form.append(label('Next date = entered date + 90 days. If your immigration receipt gives a different next date, use that date below.','muted'))
            title=entry('Title',e['title'] if e else '90-day report' if report else '')
            a=datetime.fromisoformat(e['start']) if e else core.local_dt(self.selected).replace(hour=9)
            b=datetime.fromisoformat(e['end']) if e else a+timedelta(hours=1)
            allday=Gtk.CheckButton(label='All day',active=bool(report or (e and e['all_day'])));form.append(allday)
            day=entry('Start date · YYYY-MM-DD',a.date().isoformat());endday=entry('Last date · YYYY-MM-DD',((b-timedelta(days=1)).date() if e and e['all_day'] else b.date()).isoformat())
            start=entry('Start time · HH:MM',a.strftime('%H:%M'));end=entry('End time · HH:MM',b.strftime('%H:%M'))
            def times(*_):
                start.set_sensitive(not allday.get_active());end.set_sensitive(not allday.get_active())
            allday.connect('toggled',times);times()
            notifications=[]
            notification_box=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=6);form.append(notification_box)
            def add_notification_row(minutes):
                row=Gtk.Box(spacing=8);values=list(REMINDERS)
                titles=['At start','15 minutes before','30 minutes before','1 hour before','1 day before','1 week before','10 days before','4 weeks before']
                if minutes not in values:values.append(minutes);titles.append(f'{minutes} minutes before (existing)')
                drop=Gtk.DropDown.new_from_strings(titles);drop.set_selected(values.index(minutes));drop.set_hexpand(True)
                item=(row,drop,values);notifications.append(item);row.append(drop)
                def remove(_):
                    notification_box.remove(row);notifications.remove(item);add_notification_button.set_sensitive(len(notifications)<5)
                row.append(button('Remove',remove));notification_box.append(row);add_notification_button.set_sensitive(len(notifications)<5)
            def add_notification(_):
                if len(notifications)>=5:return
                used={values[drop.get_selected()] for row,drop,values in notifications}
                add_notification_row(next(n for n in [1440,10080,14400,40320,60,30,15,0] if n not in used))
            add_notification_button=button('+ Add notification',add_notification);form.append(add_notification_button)
            if e:
                for at in e['alarms']:add_notification_row(round((a-datetime.fromisoformat(at)).total_seconds()/60))
            else:add_notification_row(1440)
            description=entry('Notes',e['description'] if e else '')
            if report:
                form.append(label('Reminder: one day before (midnight for an all-day event). You can choose a timed event instead.','muted'))
                def calculate(*_):
                    try:
                        due=core.report_due(base.get_text())
                        day.set_text(due);endday.set_text(due)
                        description.set_text('90-day immigration report. Calculated from report / entry date '+base.get_text()+'. Check next appointment date against immigration receipt.')
                        if hasattr(self,'editor_error'):self.editor_error.set_text('')
                    except ValueError:
                        if hasattr(self,'editor_error'):self.editor_error.set_text('Enter a valid report / entry date: YYYY-MM-DD')
                base.connect('changed',calculate)
                calculate()
            self.editor_error=label('');form.append(self.editor_error)
            def save(_):
                if self.busy:return
                if report:
                    try:core.report_due(base.get_text())
                    except ValueError:
                        self.editor_error.set_text('Enter a valid report / entry date: YYYY-MM-DD');return
                values=dict(title=title.get_text(),day=day.get_text(),end_day=endday.get_text(),start=start.get_text(),end=end.get_text(),all_day=allday.get_active(),reminder=[values[drop.get_selected()] for row,drop,values in notifications],description=description.get_text())
                def work():
                    if e:core.update(e,**values)
                    else:
                        calendar_name=core.settings().get('calendar','main')
                        if report:
                            due=date.fromisoformat(values['day'])
                            existing,errors=core.events(core.local_dt(due),core.local_dt(due+timedelta(days=1)))
                            if any(x['calendar']==calendar_name and x['title'].removeprefix('🛂 ').strip()==values['title'].removeprefix('🛂 ').strip() and datetime.fromisoformat(x['start']).date()==due for x in existing):
                                raise ValueError('A report with this title already exists on this date. Edit that event instead.')
                        core.add(calendar=calendar_name,**values)
                    core.sync()
                self.editor_save.set_sensitive(False)
                def done():self.editor=None;w.close()
                self.background(work,done)
            self.editor_save=button('Save changes' if e else 'Add event',save);self.editor_save.add_css_class('primary');form.append(self.editor_save)
            form.append(button('Cancel',lambda _:w.close()));w.present()
        def detail(self,e):
            w,content=self.dialog(e['title']);content.append(label(e['title'],'heading'))
            a=datetime.fromisoformat(e['start']);b=datetime.fromisoformat(e['end'])
            content.append(label(a.strftime('%d %b %Y · %H:%M')+' → '+b.strftime('%d %b %Y · %H:%M') if not e['all_day'] else a.strftime('%d %b %Y')+' · All day'))
            content.append(label(e['description'] or 'No notes.'))
            if not e.get('editable',False):content.append(label('Manage repeating series and invitations in your calendar provider.','muted'))
            else:
                content.append(button('Remove…',lambda _:self.confirm_remove(e,w)))
            content.append(button('Close',lambda _:w.close()));w.present()
        def delete_selected(self):
            if self.busy or not self.cards:return
            e=self.cards[self.event_index][1]
            if not e.get('editable',False):
                self.status.set_text('This date is read-only. Manage repeating events in your calendar provider.');return
            self.confirm_remove(e)
        def confirm_remove(self,e,detail=None):
            confirm,body=self.dialog('Remove event?')
            body.append(label('Remove “'+e['title']+'” from your calendar? This deletion will sync.'))
            cancel=button('Cancel',lambda _:confirm.close());body.append(cancel)
            def yes(_):
                if self.busy:return
                confirm.close()
                if detail:detail.close()
                def work():core.remove(e);core.sync()
                self.background(work)
            body.append(button('Remove event',yes));confirm.present();cancel.grab_focus()
        def accounts(self,*_):
            w,content=self.dialog('Accounts & sync',580);settings=core.settings()
            content.append(label('Accounts & sync','heading'))
            content.append(label('Connected: '+settings['provider'] if settings else 'No account connected. Local moon, party and holiday layers are available.'))
            content.append(label('Google needs a one-time Desktop OAuth client and browser authorization. Your personal calendar is synced; birthdays and Thai holiday subscriptions are not imported automatically.','muted'))
            link=Gtk.LinkButton(uri='https://developers.google.com/workspace/calendar/caldav/v2/guide',label='Google CalDAV setup guide');content.append(link)
            if not settings:
                def connect(_):
                    subprocess.Popen(['simple-open','terminal','simple-calendar','--connect'],start_new_session=True)
                content.append(button('Connect Google / CalDAV',connect))
            content.append(label('Sync runs every five minutes. Local date layers remain separate from Google. Account switching and additional subscriptions will require configuration; existing data is kept.','muted'))
            content.append(button('Sync now',lambda _:self.background(core.sync)))
            log=(core.ROOT/'sync.log').read_text() if (core.ROOT/'sync.log').exists() else 'No sync has run.'
            view=Gtk.TextView(editable=False,wrap_mode=Gtk.WrapMode.WORD_CHAR);view.get_buffer().set_text(log)
            scroll=Gtk.ScrolledWindow(min_content_height=140,max_content_height=220);scroll.set_child(view);content.append(scroll)
            content.append(button('Close',lambda _:w.close()));w.present()
    App().run(['simple-calendar','--day',day])
