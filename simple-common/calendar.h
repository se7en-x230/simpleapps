/* Shared read-only calendar annotations for Simplepicker and Simplelock.
 * Personal events are read from a local cache. Only the unlocked dashboard may launch the editor. */
#ifndef SIMPLE_CALENDAR_H
#define SIMPLE_CALENDAR_H
#include <gtk/gtk.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

typedef struct {
  GKeyFile *config;
  GKeyFile *personal;
  GPtrArray *moons;
  gboolean western, buddhist, full_moon;
} SimpleCalendarData;

static gboolean sc_enabled(GKeyFile *file,const char *key) {
  return !g_key_file_has_key(file,"display",key,NULL) ||
    g_key_file_get_boolean(file,"display",key,NULL);
}
static SimpleCalendarData *sc_data_new(const char *path) {
  SimpleCalendarData *d=g_new0(SimpleCalendarData,1);
  d->config=g_key_file_new();
  d->personal=g_key_file_new();
  char *cache=g_build_filename(g_get_user_cache_dir(),"simple-calendar","events.ini",NULL);
  g_key_file_load_from_file(d->personal,cache,G_KEY_FILE_NONE,NULL);g_free(cache);
  g_key_file_load_from_file(d->config,path,G_KEY_FILE_NONE,NULL);
  d->western=sc_enabled(d->config,"western");
  d->buddhist=sc_enabled(d->config,"buddhist");
  d->full_moon=sc_enabled(d->config,"full_moon");
  d->moons=g_ptr_array_new_with_free_func((GDestroyNotify)g_date_time_unref);
  char **keys=g_key_file_get_keys(d->config,"full-moons",NULL,NULL);
  for(int i=0;keys && keys[i];i++) {
    GDateTime *utc=g_date_time_new_from_iso8601(keys[i],NULL);
    if(utc){g_ptr_array_add(d->moons,g_date_time_to_local(utc));g_date_time_unref(utc);}
  }
  g_strfreev(keys);
  return d;
}
static void sc_data_free(SimpleCalendarData *d) {
  g_key_file_unref(d->personal);g_key_file_unref(d->config);g_ptr_array_unref(d->moons);g_free(d);
}
static GDateTime *sc_easter(int year) {
  /* Gregorian computus (Meeus/Jones/Butcher). */
  int a=year%19,b=year/100,c=year%100,d=b/4,e=b%4,f=(b+8)/25;
  int g=(b-f+1)/3,h=(19*a+b-d-g+15)%30,i=c/4,k=c%4;
  int l=(32+2*e+2*i-h-k)%7,m=(a+11*h+22*l)/451;
  int n=h+l-7*m+114;
  return g_date_time_new_local(year,n/31,n%31+1,12,0,0);
}
static gboolean sc_same_day(GDateTime *a,GDateTime *b) {
  return g_date_time_get_year(a)==g_date_time_get_year(b) &&
    g_date_time_get_day_of_year(a)==g_date_time_get_day_of_year(b);
}
static void sc_append(GString *s,const char *value) {
  if(!value || !*value || !g_utf8_validate(value,-1,NULL))return;
  if(s->len)g_string_append(s," · ");
  g_string_append(s,value);
}
static void sc_value(GString *s,GKeyFile *file,const char *group,const char *key) {
  char *value=g_key_file_get_string(file,group,key,NULL);
  sc_append(s,value);g_free(value);
}
enum { SC_OTHER, SC_CHRISTIAN, SC_BUDDHIST, SC_MOON, SC_KINDS };
static char *sc_day_kind(SimpleCalendarData *data,GDateTime *date,int kind) {
  GString *s=g_string_new(NULL);
  int year=g_date_time_get_year(date);
  if(data->western && (kind==SC_OTHER || kind==SC_CHRISTIAN)) {
    char *key=g_date_time_format(date,"%m-%d");
    gboolean civil=!strcmp(key,"01-01") || !strcmp(key,"12-31");
    if(kind==(civil?SC_OTHER:SC_CHRISTIAN))sc_value(s,data->config,"western-fixed",key);
    g_free(key);
    GDateTime *easter=kind==SC_CHRISTIAN?sc_easter(year):NULL;
    if(easter) {
      char **offsets=g_key_file_get_keys(data->config,"western-easter",NULL,NULL);
      for(int i=0;offsets && offsets[i];i++) {
        char *end=NULL;gint64 n=g_ascii_strtoll(offsets[i],&end,10);
        if(end==offsets[i] || *end || n < -100 || n > 100)continue;
        GDateTime *day=g_date_time_add_days(easter,(int)n);
        if(day && sc_same_day(day,date))sc_value(s,data->config,"western-easter",offsets[i]);
        if(day)g_date_time_unref(day);
      }
      g_strfreev(offsets);g_date_time_unref(easter);
    }
  }
  char *key=g_date_time_format(date,"%F");
  if(data->buddhist && kind==SC_BUDDHIST)sc_value(s,data->config,"buddhist",key);
  if(kind==SC_OTHER) {
    char *extra=g_key_file_get_string(data->config,"extra",key,NULL);
    if(extra && g_str_has_prefix(extra,"Full Moon Party · Koh Phangan")) {
      char *day=g_date_time_format(date,"%d %b %Y");
      char *label=g_strdup_printf("%s · %s",extra,day);
      sc_append(s,label);g_free(label);g_free(day);
    } else sc_append(s,extra);
    g_free(extra);
    sc_value(s,data->personal,"events",key);
  }
  g_free(key);
  if(data->full_moon && kind==SC_MOON)for(guint i=0;i<data->moons->len;i++) {
    GDateTime *moon=g_ptr_array_index(data->moons,i);
    if(sc_same_day(moon,date)) {
      char *value=g_date_time_format(moon,"● Full moon %H:%M");
      sc_append(s,value);g_free(value);
      /* Published party dates can differ from the astronomical full moon.
       * Same-day parties already appear in SC_OTHER. Never infer a date. */
      for(int offset=1;offset<=3;offset++) {
        GDateTime *party=g_date_time_add_days(date,offset);
        char *party_key=g_date_time_format(party,"%F");
        char *event=g_key_file_get_string(data->config,"extra",party_key,NULL);
        gboolean found=event && g_str_has_prefix(event,"Full Moon Party · Koh Phangan");
        if(found) {
          char *day=g_date_time_format(party,"%d %b %Y");
          char *label=g_strdup_printf("%s · %s",event,day);
          sc_append(s,label);g_free(label);g_free(day);
        }
        g_free(event);g_free(party_key);g_date_time_unref(party);
        if(found)break;
      }
    }
  }
  return g_string_free(s,FALSE);
}
static char *sc_day(SimpleCalendarData *data,GDateTime *date) {
  GString *text=g_string_new(NULL);
  for(int kind=0;kind<SC_KINDS;kind++) {
    char *part=sc_day_kind(data,date,kind);sc_append(text,part);g_free(part);
  }
  return g_string_free(text,FALSE);
}
static GDateTime *sc_next_moon(SimpleCalendarData *data,GDateTime *now) {
  GDateTime *next=NULL;
  if(data->full_moon)for(guint i=0;i<data->moons->len;i++) {
    GDateTime *moon=g_ptr_array_index(data->moons,i);
    if(g_date_time_compare(moon,now)>=0 && (!next || g_date_time_compare(moon,next)<0))next=moon;
  }
  return next; /* borrowed */
}

#ifndef SIMPLE_CALENDAR_DATA_ONLY
static void sc_set_date(GtkCalendar *calendar,GDateTime *date) {
#if GTK_CHECK_VERSION(4,20,0)
  gtk_calendar_set_date(calendar,date);
#else
  gtk_calendar_select_day(calendar,date);
#endif
}
typedef struct {
  SimpleCalendarData *data;
  GtkCalendar *calendar;
  GtkWidget *events,*next,*warning,*popup,*hint,*agenda,*sync_status;
  gboolean popup_keyboard;
  GKeyFile *keys;
  guint timer;
  GDateTime *last_day;
  guint kinds[32];
} SimpleCalendar;

/* Calendar navigation shares the family's [navigation] actions. Invalid
 * overrides retain the previous binding, so a typo cannot prevent locking. */
static const char *sc_actions[]={"left","right","up","down","page_up","page_down"};
static const char *sc_defaults[]={"Left,h,<Control>h","Right,l,<Control>l",
  "Up,k,<Control>k","Down,j,<Control>j","Page_Up","Page_Down"};
static void sc_merge_keys(GKeyFile *keys,const char *relative) {
  char *path=g_build_filename(g_get_user_config_dir(),relative,NULL);
  GKeyFile *src=g_key_file_new();
  if(g_key_file_load_from_file(src,path,G_KEY_FILE_NONE,NULL)) {
    for(guint i=0;i<G_N_ELEMENTS(sc_actions);i++) {
      char *value=g_key_file_get_string(src,"navigation",sc_actions[i],NULL);
      if(!value)continue;
      char **parts=g_strsplit(value,",",-1);gboolean valid=TRUE;
      for(int j=0;parts[j];j++) {
        guint key;GdkModifierType mods;char *part=g_strstrip(parts[j]);
        if(*part && !gtk_accelerator_parse(part,&key,&mods))valid=FALSE;
      }
      if(valid)g_key_file_set_string(keys,"navigation",sc_actions[i],value);
      else g_warning("Ignoring invalid calendar binding %s in %s",sc_actions[i],path);
      g_strfreev(parts);g_free(value);
    }
  }
  g_key_file_unref(src);g_free(path);
}
static gboolean sc_key_matches(SimpleCalendar *s,const char *action,guint key,GdkModifierType mods) {
  char *value=g_key_file_get_string(s->keys,"navigation",action,NULL);
  char **parts=g_strsplit(value?value:"",",",-1);gboolean found=FALSE;
  mods &= GDK_SHIFT_MASK|GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK|GDK_META_MASK;
  for(int i=0;parts[i];i++) {
    guint wanted;GdkModifierType mask;
    if(gtk_accelerator_parse(g_strstrip(parts[i]),&wanted,&mask) &&
       gdk_keyval_to_lower(key)==gdk_keyval_to_lower(wanted) && mods==mask){found=TRUE;break;}
  }
  g_strfreev(parts);g_free(value);return found;
}
static void sc_popup_selected(SimpleCalendar *s);
static gboolean simple_calendar_key(GtkCalendar *calendar,guint key,GdkModifierType mods) {
  SimpleCalendar *s=g_object_get_data(G_OBJECT(calendar),"simple-calendar");
  if(!s || !s->keys)return FALSE;
  GDateTime *date=gtk_calendar_get_date(calendar),*next=NULL;
  if(sc_key_matches(s,"left",key,mods))next=g_date_time_add_days(date,-1);
  else if(sc_key_matches(s,"right",key,mods))next=g_date_time_add_days(date,1);
  else if(sc_key_matches(s,"up",key,mods))next=g_date_time_add_days(date,-7);
  else if(sc_key_matches(s,"down",key,mods))next=g_date_time_add_days(date,7);
  else if(sc_key_matches(s,"page_up",key,mods))next=g_date_time_add_months(date,-1);
  else if(sc_key_matches(s,"page_down",key,mods))next=g_date_time_add_months(date,1);
  else if(key==GDK_KEY_Home && !(mods & (GDK_SHIFT_MASK|GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK|GDK_META_MASK)))next=g_date_time_new_now_local();
  else {g_date_time_unref(date);return FALSE;}
  if(next){sc_set_date(calendar,next);sc_popup_selected(s);g_date_time_unref(next);}
  g_date_time_unref(date);return TRUE;
}
static char *sc_key_label(SimpleCalendar *s,const char *action) {
  char *value=g_key_file_get_string(s->keys,"navigation",action,NULL);
  char **parts=g_strsplit(value?value:"",",",-1);char *label=g_strdup("disabled");
  for(int i=0;parts[i];i++) {
    guint key;GdkModifierType mods;
    if(!gtk_accelerator_parse(g_strstrip(parts[i]),&key,&mods))continue;
    if(i==0 || (!mods && gdk_keyval_to_unicode(key)>=32)) {
      g_free(label);label=(!mods && key>=GDK_KEY_a && key<=GDK_KEY_z)?g_strdup_printf("%c",(char)key):gtk_accelerator_get_label(key,mods);
      if(!mods && gdk_keyval_to_unicode(key)>=32)break;
    }
  }
  g_strfreev(parts);g_free(value);return label;
}
static void simple_calendar_navigation(GtkCalendar *calendar,const char *app,const char *module) {
  SimpleCalendar *s=g_object_get_data(G_OBJECT(calendar),"simple-calendar");
  s->keys=g_key_file_new();
  for(guint i=0;i<G_N_ELEMENTS(sc_actions);i++)g_key_file_set_string(s->keys,"navigation",sc_actions[i],sc_defaults[i]);
  sc_merge_keys(s->keys,"simple/keys.ini");
  char *path=g_build_filename(app,"keys.ini",NULL);sc_merge_keys(s->keys,path);g_free(path);
  if(module){path=g_build_filename(app,module,"keys.ini",NULL);sc_merge_keys(s->keys,path);g_free(path);}
  char *labels[G_N_ELEMENTS(sc_actions)];
  for(guint i=0;i<G_N_ELEMENTS(sc_actions);i++)labels[i]=sc_key_label(s,sc_actions[i]);
  char *text=g_strdup_printf("%s/%s/%s/%s · move   %s/%s · month   Home · today",
    labels[0],labels[3],labels[2],labels[1],labels[4],labels[5]);
  GtkWidget *hint=s->hint;gtk_label_set_text(GTK_LABEL(hint),text);gtk_label_set_wrap(GTK_LABEL(hint),TRUE);
  gtk_label_set_xalign(GTK_LABEL(hint),0);gtk_label_set_max_width_chars(GTK_LABEL(hint),1);
  gtk_widget_set_hexpand(hint,TRUE);gtk_widget_add_css_class(hint,"simple-calendar-hint");
  gtk_widget_set_visible(hint,TRUE);
  for(guint i=0;i<G_N_ELEMENTS(sc_actions);i++)g_free(labels[i]);
  g_free(text);
}

static const char *sc_classes[]={"simple-calendar-other","simple-calendar-christian",
  "simple-calendar-buddhist","simple-calendar-moon"};
/* GTK has no non-deprecated named palette lookup; keep it isolated here,
 * as in the lock backdrop renderer. The icon must retain its own color on
 * dates shared with a holiday. Colors remain entirely in the shared CSS. */
G_GNUC_BEGIN_IGNORE_DEPRECATIONS
static char *sc_moon_ink(GtkWidget *widget) {
  GdkRGBA color;gtk_widget_get_color(widget,&color);
  gtk_style_context_lookup_color(gtk_widget_get_style_context(widget),"simple_calendar_moon",&color);
  return g_strdup_printf("#%02x%02x%02x",(int)(color.red*255+.5),(int)(color.green*255+.5),(int)(color.blue*255+.5));
}
G_GNUC_END_IGNORE_DEPRECATIONS
static void sc_color_days(GtkWidget *widget,SimpleCalendar *s) {
  /* GTK exposes day-number and other-month as documented calendar CSS nodes. */
  if(GTK_IS_LABEL(widget) && gtk_widget_has_css_class(widget,"day-number")) {
    char *end=NULL;long day=strtol(gtk_label_get_text(GTK_LABEL(widget)),&end,10);
    gboolean valid=(!*end || !strcmp(end," ●") || !strcmp(end," ●●")) && day>=1 && day<=31;
    guint mask=(valid && !gtk_widget_has_css_class(widget,"other-month"))?s->kinds[day]:0;
    for(int kind=0;kind<SC_KINDS;kind++) {
      if(mask & (1u<<kind))gtk_widget_add_css_class(widget,sc_classes[kind]);
      else gtk_widget_remove_css_class(widget,sc_classes[kind]);
    }
    if(valid) {
      GDateTime *month=gtk_calendar_get_date(s->calendar);
      char *key=g_strdup_printf("%04d-%02d-%02ld",g_date_time_get_year(month),g_date_time_get_month(month),day);
      char *report=g_key_file_get_string(s->data->personal,"markers","report",NULL);
      gboolean is_report=!gtk_widget_has_css_class(widget,"other-month") && report && !strcmp(key,report);
      GString *markup=g_string_new(NULL);g_string_append_printf(markup,"%ld",day);
      if((mask & (1u<<SC_MOON)) || is_report)g_string_append_c(markup,' ');
      if(mask & (1u<<SC_MOON)) {
        char *ink=sc_moon_ink(widget);
        g_string_append_printf(markup,"<span foreground=\"%s\">●</span>",ink);g_free(ink);
      }
      if(is_report)g_string_append(markup,"<span foreground=\"#e66565\">●</span>");
      gtk_label_set_markup(GTK_LABEL(widget),markup->str);
      g_string_free(markup,TRUE);g_free(key);g_free(report);g_date_time_unref(month);
    }
  }
  for(GtkWidget *child=gtk_widget_get_first_child(widget);child;child=gtk_widget_get_next_sibling(child))sc_color_days(child,s);
}
static GtkWidget *sc_day_widget(GtkWidget *widget,int day) {
  if(GTK_IS_LABEL(widget) && gtk_widget_has_css_class(widget,"day-number") &&
     !gtk_widget_has_css_class(widget,"other-month") && atoi(gtk_label_get_text(GTK_LABEL(widget)))==day)return widget;
  for(GtkWidget *child=gtk_widget_get_first_child(widget);child;child=gtk_widget_get_next_sibling(child)) {
    GtkWidget *found=sc_day_widget(child,day);if(found)return found;
  }
  return NULL;
}
static void sc_popup_hide(SimpleCalendar *s) {gtk_widget_set_visible(s->popup,FALSE);}
static void sc_popup_show(SimpleCalendar *s,GDateTime *date,GtkWidget *anchor,gboolean keyboard) {
  (void)anchor;
  for(GtkWidget *child=gtk_widget_get_first_child(s->events);child;child=gtk_widget_get_first_child(s->events))gtk_box_remove(GTK_BOX(s->events),child);
  gboolean any=FALSE;
  for(int kind=0;kind<SC_KINDS;kind++) {
    char *part=sc_day_kind(s->data,date,kind);
    if(*part) {
      GtkWidget *row=gtk_label_new(part);gtk_label_set_xalign(GTK_LABEL(row),0);
      gtk_label_set_wrap(GTK_LABEL(row),TRUE);gtk_label_set_max_width_chars(GTK_LABEL(row),40);
      gtk_widget_add_css_class(row,sc_classes[kind]);gtk_box_append(GTK_BOX(s->events),row);any=TRUE;
    }
    g_free(part);
  }
  if(!any && !gtk_widget_get_visible(s->warning)){sc_popup_hide(s);return;}
  char *title=g_date_time_format(date,"%A, %d %B %Y");GtkWidget *heading=gtk_label_new(title);g_free(title);
  gtk_label_set_xalign(GTK_LABEL(heading),0);gtk_box_prepend(GTK_BOX(s->events),heading);
  s->popup_keyboard=keyboard;
  if(!gtk_widget_get_mapped(GTK_WIDGET(s->calendar)))return;
  gtk_widget_set_visible(s->popup,TRUE);
}
static void sc_popup_selected(SimpleCalendar *s) {
  GDateTime *date=gtk_calendar_get_date(s->calendar);
  GtkWidget *anchor=sc_day_widget(GTK_WIDGET(s->calendar),g_date_time_get_day_of_month(date));
  sc_popup_show(s,date,anchor,TRUE);g_date_time_unref(date);
}
static void sc_motion(GtkEventControllerMotion *controller,double x,double y,gpointer data) {
  (void)controller;SimpleCalendar *s=data;GtkWidget *calendar=GTK_WIDGET(s->calendar);
  GtkWidget *day=gtk_widget_pick(calendar,x,y,GTK_PICK_DEFAULT);
  while(day && day!=calendar && !gtk_widget_has_css_class(day,"day-number"))day=gtk_widget_get_parent(day);
  if(!GTK_IS_LABEL(day) || !gtk_widget_has_css_class(day,"day-number")){sc_popup_hide(s);return;}
  int number=atoi(gtk_label_get_text(GTK_LABEL(day)));if(number<1 || number>31){sc_popup_hide(s);return;}
  GDateTime *selected=gtk_calendar_get_date(s->calendar),*month=g_date_time_ref(selected);
  if(gtk_widget_has_css_class(day,"other-month")) {
    g_date_time_unref(month);month=g_date_time_add_months(selected,number>15?-1:1);
  }
  if(month) {
    GDateTime *date=g_date_time_new_local(g_date_time_get_year(month),g_date_time_get_month(month),number,12,0,0);
    if(date){sc_popup_show(s,date,day,FALSE);g_date_time_unref(date);}
    g_date_time_unref(month);
  }
  g_date_time_unref(selected);
}
static void sc_pointer_leave(GtkEventControllerMotion *controller,gpointer data) {
  (void)controller;SimpleCalendar *s=data;if(!s->popup_keyboard)sc_popup_hide(s);
}
static void sc_focus_enter(GtkEventControllerFocus *controller,gpointer data) {
  (void)controller;sc_popup_selected(data);
}
static void sc_focus_leave(GtkEventControllerFocus *controller,gpointer data) {
  (void)controller;sc_popup_hide(data);
}
static void sc_refresh(SimpleCalendar *s) {
  GKeyFile *personal=g_key_file_new();
  char *cache=g_build_filename(g_get_user_cache_dir(),"simple-calendar","events.ini",NULL);
  if(g_key_file_load_from_file(personal,cache,G_KEY_FILE_NONE,NULL)) {
    g_key_file_unref(s->data->personal);s->data->personal=personal;
  } else g_key_file_unref(personal);
  g_free(cache);
  char *upcoming=g_key_file_get_string(s->data->personal,"status","next",NULL);
  char *alert=g_key_file_get_string(s->data->personal,"status","alert",NULL);
  char *status=g_key_file_get_string(s->data->personal,"status","message",NULL);
  gtk_label_set_text(GTK_LABEL(s->agenda),alert && *alert?alert:upcoming?upcoming:"");
  gtk_widget_set_visible(s->agenda,(alert && *alert) || (upcoming && *upcoming));
  gtk_label_set_text(GTK_LABEL(s->sync_status),status?status:"");
  gtk_widget_set_visible(s->sync_status,status && *status);
  g_free(upcoming);g_free(alert);g_free(status);
  GDateTime *selected=gtk_calendar_get_date(s->calendar);
  int year=g_date_time_get_year(selected),month=g_date_time_get_month(selected);
  memset(s->kinds,0,sizeof s->kinds);
  gtk_calendar_clear_marks(s->calendar);
  for(int day=1;day<=g_date_get_days_in_month(month,year);day++) {
    GDateTime *date=g_date_time_new_local(year,month,day,12,0,0);
    if(!date)continue;
    char *events=sc_day(s->data,date);
    if(*events) {
      gtk_calendar_mark_day(s->calendar,day);
      for(int kind=0;kind<SC_KINDS;kind++) {
        char *part=sc_day_kind(s->data,date,kind);
        if(*part)s->kinds[day]|=1u<<kind;
        g_free(part);
      }

    }
    g_free(events);g_date_time_unref(date);
  }
  sc_color_days(GTK_WIDGET(s->calendar),s);
  GDateTime *now=g_date_time_new_now_local(),*next=sc_next_moon(s->data,now);
  char *next_text=next?g_date_time_format(next,"Next full moon: %d %b · %H:%M"):g_strdup("Full moon dates unavailable");
  gtk_label_set_text(GTK_LABEL(s->next),next_text);
  gtk_widget_set_visible(s->next,s->data->full_moon);
  g_free(next_text);g_date_time_unref(now);
  GString *warning=g_string_new(NULL);
  const char *groups[]={"buddhist","moon"};
  gboolean enabled[]={s->data->buddhist,s->data->full_moon};
  for(int i=0;i<2;i++)if(enabled[i]) {
    char *start=g_strdup_printf("%s_start",groups[i]),*end=g_strdup_printf("%s_end",groups[i]);
    int first=g_key_file_get_integer(s->data->config,"coverage",start,NULL);
    int last=g_key_file_get_integer(s->data->config,"coverage",end,NULL);
    if(year<first || year>last || !first) {
      if(warning->len)g_string_append_c(warning,'\n');
      g_string_append_printf(warning,"%s dates unavailable for %d",i?"Full moon":"Thai Buddhist",year);
    }
    g_free(start);g_free(end);
  }
  gtk_label_set_text(GTK_LABEL(s->warning),warning->str);
  gtk_widget_set_visible(s->warning,warning->len>0);
  g_string_free(warning,TRUE);g_date_time_unref(selected);
}
static void sc_changed(GObject *object,GParamSpec *spec,gpointer data) {
  (void)object;(void)spec;SimpleCalendar *s=data;sc_refresh(s);
  GtkRoot *root=gtk_widget_get_root(GTK_WIDGET(s->calendar));
  GtkWidget *focus=root?gtk_root_get_focus(root):NULL;
  if(focus && (focus==GTK_WIDGET(s->calendar) || gtk_widget_is_ancestor(focus,GTK_WIDGET(s->calendar))))sc_popup_selected(s);
  else sc_popup_hide(s);
}
static gboolean sc_tick(gpointer data) {
  SimpleCalendar *s=data;
  GDateTime *now=g_date_time_new_now_local();
  if(!sc_same_day(now,s->last_day)) {
    GDateTime *selected=gtk_calendar_get_date(s->calendar);
    /* Follow today at midnight unless the user browsed to another date. */
    if(sc_same_day(selected,s->last_day))sc_set_date(s->calendar,now);
    g_date_time_unref(selected);g_date_time_unref(s->last_day);
    s->last_day=g_date_time_ref(now);
  }
  sc_refresh(s);g_date_time_unref(now);return G_SOURCE_CONTINUE;
}
static void sc_free(gpointer data) {
  SimpleCalendar *s=data;
  if(s->timer)g_source_remove(s->timer);
  g_clear_pointer(&s->keys,g_key_file_unref);
  sc_data_free(s->data);g_date_time_unref(s->last_day);
  g_object_unref(s->events);g_object_unref(s->next);g_object_unref(s->warning);
  g_object_unref(s->agenda);g_object_unref(s->sync_status);g_object_unref(s->hint);g_object_unref(s->popup);g_free(s);
}
static GtkWidget *sc_label(GtkWidget *box,const char *style) {
  GtkWidget *label=gtk_label_new(NULL);
  gtk_label_set_xalign(GTK_LABEL(label),0);
  gtk_label_set_wrap(GTK_LABEL(label),TRUE);
  gtk_label_set_wrap_mode(GTK_LABEL(label),PANGO_WRAP_WORD_CHAR);
  gtk_label_set_max_width_chars(GTK_LABEL(label),1);
  gtk_widget_set_hexpand(label,TRUE);
  gtk_widget_add_css_class(label,style);
  gtk_box_append(GTK_BOX(box),label);
  return g_object_ref(label);
}
static GtkWidget *simple_calendar_details(GtkCalendar *calendar) {
  SimpleCalendar *s=g_new0(SimpleCalendar,1);
  char *path=g_build_filename(g_get_user_config_dir(),"simple","calendar.ini",NULL);
  s->data=sc_data_new(path);g_free(path);
  s->calendar=calendar;s->last_day=g_date_time_new_now_local();
  GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,4);
  gtk_widget_add_css_class(box,"simple-calendar-details");
  s->agenda=sc_label(box,"simple-calendar-agenda");
  s->sync_status=sc_label(box,"simple-calendar-hint");
  s->next=sc_label(box,"simple-calendar-next");
  gtk_widget_add_css_class(s->next,"simple-calendar-moon");
  /* Draw inside the existing surface: session-lock compositors reject native
   * popups. Align above the details row, so later cards cannot paint over it.
   * Overlay children never affect layout or receive pointer/keyboard focus. */
  GtkWidget *overlay=gtk_overlay_new();gtk_overlay_set_child(GTK_OVERLAY(overlay),box);
  gtk_widget_set_overflow(overlay,GTK_OVERFLOW_VISIBLE);
  s->popup=gtk_box_new(GTK_ORIENTATION_VERTICAL,5);
  gtk_widget_add_css_class(s->popup,"simple-calendar-popup");
  gtk_widget_set_can_target(s->popup,FALSE);
  gtk_widget_set_halign(s->popup,GTK_ALIGN_FILL);gtk_widget_set_valign(s->popup,GTK_ALIGN_END);
  gtk_overlay_add_overlay(GTK_OVERLAY(overlay),s->popup);
  gtk_overlay_set_measure_overlay(GTK_OVERLAY(overlay),s->popup,FALSE);
  gtk_overlay_set_clip_overlay(GTK_OVERLAY(overlay),s->popup,FALSE);
  g_object_ref(s->popup);gtk_widget_set_visible(s->popup,FALSE);
  GtkWidget *contents=s->popup;
  s->events=gtk_box_new(GTK_ORIENTATION_VERTICAL,3);
  gtk_widget_add_css_class(s->events,"simple-calendar-events");
  gtk_box_append(GTK_BOX(contents),s->events);g_object_ref(s->events);
  s->warning=sc_label(contents,"simple-calendar-warning");
  s->hint=sc_label(contents,"simple-calendar-hint");gtk_widget_set_visible(s->hint,FALSE);
  GtkEventController *motion=gtk_event_controller_motion_new();
  g_signal_connect(motion,"motion",G_CALLBACK(sc_motion),s);
  g_signal_connect(motion,"leave",G_CALLBACK(sc_pointer_leave),s);
  gtk_widget_add_controller(GTK_WIDGET(calendar),motion);
  GtkEventController *focus=gtk_event_controller_focus_new();
  g_signal_connect(focus,"enter",G_CALLBACK(sc_focus_enter),s);
  g_signal_connect(focus,"leave",G_CALLBACK(sc_focus_leave),s);
  gtk_widget_add_controller(GTK_WIDGET(calendar),focus);
  g_object_set_data_full(G_OBJECT(calendar),"simple-calendar",s,sc_free);
#if GTK_CHECK_VERSION(4,20,0)
  g_signal_connect(calendar,"notify::date",G_CALLBACK(sc_changed),s);
#else
  g_signal_connect(calendar,"notify::month",G_CALLBACK(sc_changed),s);
  g_signal_connect(calendar,"notify::year",G_CALLBACK(sc_changed),s);
#endif
  s->timer=g_timeout_add_seconds(15,sc_tick,s);sc_refresh(s);
  return overlay;
}
#endif
#endif
