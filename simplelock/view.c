#include "simple-theme.h"
#include "../simple-common/daylight-art.h"
#include "../simple-common/calendar.h"
#include "../simple-common/phone-network.h"
#include "../simple-common/system-info.h"
#include "../simple-common/music-layout.h"
#include "media.h"
#include "../simple-common/song-progress.h"
#include "lock.h"
#include "fit.c"
#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <sys/wait.h>
#include <sys/utsname.h>
#include <glib-unix.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <sys/statvfs.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>

/* GTK4 has no replacement for named palette lookup yet. Keep the
   compatibility API isolated here; failed lookups fall back to widget text. */
G_GNUC_BEGIN_IGNORE_DEPRECATIONS
static void theme_color(GtkWidget *widget,const char *name,GdkRGBA *color) {
    gtk_widget_get_color(widget,color);
    gtk_style_context_lookup_color(gtk_widget_get_style_context(widget),name,color);
}
G_GNUC_END_IGNORE_DEPRECATIONS
/* Static Occult backdrop: charcoal and dark red. */
typedef struct { GtkWidget parent; } DashBackdrop;
typedef GtkWidgetClass DashBackdropClass;
G_DEFINE_TYPE(DashBackdrop,dash_backdrop,GTK_TYPE_WIDGET)
static void backdrop_snapshot(GtkWidget *widget,GtkSnapshot *snapshot) {
  double w=gtk_widget_get_width(widget),h=gtk_widget_get_height(widget);
  if(w<=0 || h<=0)return;
  graphene_rect_t bounds=GRAPHENE_RECT_INIT(0,0,w,h);
  cairo_t *cr=gtk_snapshot_append_cairo(snapshot,&bounds);
  cairo_scale(cr,w,h);
  GdkRGBA top,bottom,accent,warm,fg;
  theme_color(widget,"simple_lock_top",&top);
  theme_color(widget,"simple_lock_bottom",&bottom);
  theme_color(widget,"simple_lock_glow",&accent);
  theme_color(widget,"simple_lock_horizon",&warm);
  theme_color(widget,"simple_fg",&fg);
  cairo_pattern_t *base=cairo_pattern_create_linear(0,0,0,1);
  cairo_pattern_add_color_stop_rgb(base,0,top.red,top.green,top.blue);
  cairo_pattern_add_color_stop_rgb(base,.42,top.red*.82,top.green*.82,top.blue*.82);
  cairo_pattern_add_color_stop_rgb(base,.72,top.red*.5,top.green*.5,top.blue*.5);
  cairo_pattern_add_color_stop_rgb(base,1,bottom.red,bottom.green,bottom.blue);
  cairo_set_source(cr,base);cairo_paint(cr);cairo_pattern_destroy(base);
  /* Equal dark red light on both edges, with a calm center. */
  for(int side=0;side<2;side++) {
    double x=side?.94:.06;
    cairo_pattern_t *glow=cairo_pattern_create_radial(x,.25,0,x,.25,.72);
    cairo_pattern_add_color_stop_rgba(glow,0,accent.red,accent.green,accent.blue,.43);
    cairo_pattern_add_color_stop_rgba(glow,1,accent.red,accent.green,accent.blue,0);
    cairo_set_source(cr,glow);cairo_paint(cr);cairo_pattern_destroy(glow);
  }
  /* Low copper sunset behind the smoky foreground. */
  cairo_pattern_t *horizon=cairo_pattern_create_radial(.5,.50,0,.5,.50,.62);
  cairo_pattern_add_color_stop_rgba(horizon,0,warm.red,warm.green,warm.blue,.28);
  cairo_pattern_add_color_stop_rgba(horizon,.48,warm.red*.7,warm.green*.7,warm.blue*.7,.14);
  cairo_pattern_add_color_stop_rgba(horizon,1,warm.red*.4,warm.green*.4,warm.blue*.4,0);
  cairo_set_source(cr,horizon);cairo_paint(cr);cairo_pattern_destroy(horizon);
  /* Broad, gently uneven water ripples; soft crests roll into shaded troughs. */
  cairo_save(cr);
  cairo_translate(cr,.5,.56);
  cairo_scale(cr,1,w/h);
  for(int ring=0;ring<9;ring++) {
    double r=.075+ring*.088;
    double strength=.85-ring*.055;
    for(int shade=0;shade<2;shade++) {
      double offset=shade?.023:-.019;
      double x=(ring%3-1)*.004,y=offset;
      cairo_move_to(cr,x+r,y);
      cairo_curve_to(cr,x+r,y+r*.57,x+r*.55,y+r*1.015,x,y+r);
      cairo_curve_to(cr,x-r*.57,y+r,x-r*1.012,y+r*.55,x-r,y);
      cairo_curve_to(cr,x-r,y-r*.56,x-r*.54,y-r*.985,x,y-r);
      cairo_curve_to(cr,x+r*.57,y-r,x+r*.995,y-r*.54,x+r,y);
      cairo_close_path(cr);
      cairo_push_group(cr);
      for(int feather=30;feather>=1;feather--) {
        cairo_set_line_width(cr,(14.0+feather*1.2)/w);
        if(shade)cairo_set_source_rgba(cr,bottom.red,bottom.green,bottom.blue,.035);
        else cairo_set_source_rgba(cr,fg.red,fg.green,fg.blue,.045);
        cairo_stroke_preserve(cr);
      }
      cairo_pop_group_to_source(cr);cairo_paint_with_alpha(cr,.162*strength);
      cairo_new_path(cr);
    }
  }
  cairo_restore(cr);
  /* Feathered dark corners give the illuminated ribbons more depth. */
  for(int corner=0;corner<4;corner++) {
    double x=(corner&1)?1:0,y=(corner&2)?1:0;
    cairo_pattern_t *shade=cairo_pattern_create_radial(x,y,0,x,y,.48);
    cairo_pattern_add_color_stop_rgba(shade,0,bottom.red*.1,bottom.green*.1,bottom.blue*.1,.40);
    cairo_pattern_add_color_stop_rgba(shade,.4,bottom.red*.1,bottom.green*.1,bottom.blue*.1,.14);
    cairo_pattern_add_color_stop_rgba(shade,1,bottom.red*.1,bottom.green*.1,bottom.blue*.1,0);
    cairo_set_source(cr,shade);cairo_paint(cr);cairo_pattern_destroy(shade);
  }
  cairo_destroy(cr);
}
static void dash_backdrop_class_init(DashBackdropClass *klass) {
  GTK_WIDGET_CLASS(klass)->snapshot=backdrop_snapshot;
}
static void dash_backdrop_init(DashBackdrop *self) {
  gtk_widget_set_hexpand(GTK_WIDGET(self),TRUE);gtk_widget_set_vexpand(GTK_WIDGET(self),TRUE);
}
static GtkWidget *backdrop_new(GdkMonitor *monitor) {
  (void)monitor;
  return g_object_new(dash_backdrop_get_type(),NULL);
}
static gboolean fade_in(GtkWidget *widget,GdkFrameClock *clock,gpointer data) {
  (void)clock;gint64 *start=data;gint64 now=g_get_monotonic_time();
  if(!*start)*start=now;
  double progress=MIN(1.0,(now-*start)/450000.0);
  gtk_widget_set_opacity(widget,progress*(2.0-progress));
  return progress<1.0;
}

static char *appearance_path(const char *name) {
  char *dir=g_path_get_dirname(config_path);
  char *path=g_build_filename(dir,name,NULL);g_free(dir);return path;
}
static char *artwork_path(const char *name) {
  if(g_str_has_prefix(name,"~/"))return g_build_filename(g_get_home_dir(),name+2,NULL);
  if(g_path_is_absolute(name))return g_strdup(name);
  return appearance_path(name);
}
static char *idle_title,*idle_subtitle;
static void load_idle_caption(void) {
  g_free(idle_title);g_free(idle_subtitle);
  idle_title=g_strdup("Ānāpānasati, mindfulness of breathing");idle_subtitle=g_strdup("No system can imprison a mind that has learned to observe without attachment.");
  char *path=appearance_path("idle.toml");
  FILE *file=fopen(path,"r");g_free(path);if(!file)return;
  char error[256];toml_table_t *root=toml_parse_file(file,error,sizeof error);fclose(file);if(!root)return;
  toml_table_t *table=toml_table_in(root,"idle");
  if(table){toml_datum_t title=toml_string_in(table,"title"),subtitle=toml_string_in(table,"subtitle");
    if(title.ok){g_free(idle_title);idle_title=title.u.s;}
    if(subtitle.ok){g_free(idle_subtitle);idle_subtitle=subtitle.u.s;}}
  toml_free(root);
}
typedef struct {
  char *title, *artist, *album, *status, *art, *art_key, *network;
  SimplePhone phone;
  SimpleSystemInfo system;
  GdkPixbuf *pix;
  gboolean art_changed, playing;
  double position,duration;
} Snapshot;
typedef struct {
  Menu *m;
  GtkWidget *title, *artist, *album, *status, *picture, *placeholder, *mood_art;
  GdkTexture *playing_texture,*idle_texture;
  SimpleDaylightArt daylight_art,idle_art;
  GtkWidget *clock, *date, *network, *memory, *disk, *battery, *visualizer, *visualizer_accent;
  GtkWidget *phone, *metadata, *song_progress;
  GtkWidget *idle_quote;
  GtkWidget *desktop, *terminal, *init, *uptime;
  SimplePhoneHistory phone_history;
  SimpleMusicLayout layout;
  GPid cava_pid;
  int cava_fd;
  guint cava_watch;
  char *cava_config;
  guint8 bars[128], pending[128];
  gsize pending_size;
  GCancellable *cancel;
  char *art;
  gboolean busy, fullscreen;
  int art_resolution;
  GtkWidget *entry,*feedback,*calendar;
  guint timer, clock_timer;
} Dashboard;
static GPtrArray *views;
static void snapshot_free(gpointer ptr) {
  Snapshot *s = ptr;
  simple_phone_clear(&s->phone);
  simple_system_clear(&s->system);
  g_free(s->title); g_free(s->artist); g_free(s->album); g_free(s->status);
  g_free(s->art); g_free(s->art_key); g_free(s->network); g_clear_object(&s->pix); g_free(s);
}
static char *vstring(GVariant *dict, const char *key) {
  const char *v = "";
  if (dict) g_variant_lookup(dict, key, "&s", &v);
  return g_strdup(v);
}
static GVariant *call(GDBusConnection *bus, const char *name, const char *path,
                      const char *iface, const char *method, GVariant *args,
                      const GVariantType *type, GCancellable *cancel) {
  return g_dbus_connection_call_sync(bus, name, path, iface, method, args, type,
                                    G_DBUS_CALL_FLAGS_NONE, 1000, cancel, NULL);
}
typedef struct {char *key;int resolution;} FetchData;
static void fetch_data_free(gpointer p){FetchData *f=p;g_free(f->key);g_free(f);}
static GdkPixbuf *art_load(const char *uri, GCancellable *cancel,int art_resolution) {
  if (!uri || !*uri) return NULL;
  GInputStream *stream = NULL;
  if (g_str_has_prefix(uri, "data:image/") && strlen(uri) < 12 * 1024 * 1024) {
    const char *comma = strchr(uri, ',');
    if (comma && g_strstr_len(uri, comma-uri, ";base64")) {
      gsize size = 0; guchar *data = g_base64_decode(comma+1, &size);
      stream = g_memory_input_stream_new_from_data(data, size, g_free);
    }
  } else if (g_str_has_prefix(uri, "file://") || g_path_is_absolute(uri)) {
    GFile *file = g_path_is_absolute(uri) ? g_file_new_for_path(uri) : g_file_new_for_uri(uri);
    stream = G_INPUT_STREAM(g_file_read(file, cancel, NULL));
    g_object_unref(file);
  } else if (g_str_has_prefix(uri, "https://") || g_str_has_prefix(uri, "http://")) {
    GSubprocess *p = g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE | G_SUBPROCESS_FLAGS_STDERR_SILENCE,
      NULL, "curl", "--fail", "--silent", "--location", "--max-time", "3", "--max-filesize", "8388608", "--", uri, NULL);
    if (p) {
      GBytes *bytes = NULL;
      if (g_subprocess_communicate(p, NULL, cancel, &bytes, NULL, NULL) &&
          g_subprocess_get_successful(p) && bytes)
        stream = g_memory_input_stream_new_from_bytes(bytes);
      if (g_cancellable_is_cancelled(cancel)) g_subprocess_force_exit(p);
      g_clear_pointer(&bytes, g_bytes_unref); g_object_unref(p);
    }
  }
  if (!stream) return NULL;
  GdkPixbuf *pix = gdk_pixbuf_new_from_stream_at_scale(stream, art_resolution, art_resolution, TRUE, cancel, NULL);
  g_object_unref(stream); return pix;
}
static void fetch(GTask *task, gpointer source, gpointer data, GCancellable *cancel) {
  (void)source;
  Snapshot *s = g_new0(Snapshot,1);
  s->title=g_strdup(idle_title); s->artist=g_strdup(idle_subtitle);
  s->album=g_strdup(""); s->status=g_strdup("NOT PLAYING"); s->art=g_strdup("");
  GDBusConnection *bus = g_bus_get_sync(G_BUS_TYPE_SESSION, cancel, NULL);
  if (bus) {
    GVariant *reply = call(bus, "org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus", "ListNames", NULL, G_VARIANT_TYPE("(as)"), cancel);
    if (reply) {
      char **names=NULL; g_variant_get(reply,"(^as)",&names); int best=-1, count=0;
      for (int i=0; names[i] && !g_cancellable_is_cancelled(cancel); i++) {
        if (!g_str_has_prefix(names[i],"org.mpris.MediaPlayer2.") || count++ >= 16) continue;
        GVariant *props=call(bus,names[i],"/org/mpris/MediaPlayer2","org.freedesktop.DBus.Properties","GetAll",
          g_variant_new("(s)","org.mpris.MediaPlayer2.Player"),G_VARIANT_TYPE("(a{sv})"),cancel);
        if (!props) continue;
        GVariant *dict=NULL; g_variant_get(props,"(@a{sv})",&dict);
        char *status=vstring(dict,"PlaybackStatus");
        int rank=!strcmp(status,"Playing")?2:!strcmp(status,"Paused")?1:0;
        GVariant *meta=g_variant_lookup_value(dict,"Metadata",G_VARIANT_TYPE("a{sv}"));
        if (meta && rank>=1 && rank>best) {
          best=rank;s->playing=rank==2;
          gint64 position=0,duration=0;gboolean has_position=g_variant_lookup(dict,"Position","x",&position);g_variant_lookup(meta,"mpris:length","x",&duration);s->position=has_position?position/1000000.0:-1;s->duration=duration/1000000.0;
          g_free(s->title);s->title=vstring(meta,"xesam:title");
          if (!*s->title) {g_free(s->title);s->title=g_strdup("Untitled track");}
          char **artists=NULL;g_variant_lookup(meta,"xesam:artist","^as",&artists);
          g_free(s->artist);s->artist=artists?g_strjoinv(", ",artists):g_strdup("");g_strfreev(artists);
          g_free(s->album);s->album=simple_media_album(meta);
          g_free(s->art);s->art=vstring(meta,"mpris:artUrl");
          g_free(s->status);s->status=g_strdup_printf("%s  ·  %s", *status?status:"Stopped",names[i]+strlen("org.mpris.MediaPlayer2."));
        }
        g_clear_pointer(&meta,g_variant_unref);g_free(status);g_variant_unref(dict);g_variant_unref(props);
      }
      g_strfreev(names);g_variant_unref(reply);
    }
    g_object_unref(bus);
  }
  s->art_key=g_strdup_printf("%s\n%s\n%s",s->art,s->title,s->album);
  s->art_changed=g_strcmp0(s->art_key,((FetchData*)data)->key)!=0;
  if (s->art_changed) s->pix=art_load(s->art,cancel,((FetchData*)data)->resolution);
  s->network=simple_network_line(cancel);
  s->phone=simple_phone_read(cancel);
  s->system=simple_system_read(cancel);
  g_task_return_pointer(task,s,snapshot_free);
}
static void ready(GObject *source, GAsyncResult *result, gpointer data) {
  (void)source; Dashboard *d=data;
  Snapshot *s=g_task_propagate_pointer(G_TASK(result),NULL);
  d->busy=FALSE;
  if (!s) return;
  if (!d->m->closed) {
    d->daylight_art.kind=strcmp(s->status,"NOT PLAYING")?"profile":"idle";
    simple_daylight_art_update(&d->idle_art);
    if(d->mood_art && !simple_daylight_art_update(&d->daylight_art))gtk_picture_set_paintable(GTK_PICTURE(d->mood_art),GDK_PAINTABLE(s->playing?d->playing_texture:d->idle_texture));
    char *title_text=!strcmp(s->status,"NOT PLAYING")?g_strdup(s->title):g_strdup_printf("Song: %s",*s->title?s->title:"—");
    gtk_label_set_text(GTK_LABEL(d->title),title_text);gtk_widget_set_tooltip_text(d->title,title_text);g_free(title_text);
    char *artist_text=!strcmp(s->status,"NOT PLAYING")?g_strdup(s->artist):g_strdup_printf("Artist: %s",*s->artist?s->artist:"—");
    gtk_label_set_text(GTK_LABEL(d->artist),artist_text);gtk_widget_set_tooltip_text(d->artist,artist_text);g_free(artist_text);
    char *album_text=!strcmp(s->status,"NOT PLAYING")?g_strdup(s->album):g_strdup_printf("Album: %s",*s->album?s->album:"—");
    gtk_label_set_text(GTK_LABEL(d->album),album_text);gtk_widget_set_tooltip_text(d->album,album_text);g_free(album_text);
    gboolean playing=strcmp(s->status,"NOT PLAYING")!=0;
    char *heading=g_strdup(playing?idle_subtitle:idle_title);
    gtk_label_set_text(GTK_LABEL(d->status),heading);g_free(heading);
    gtk_widget_set_visible(d->artist,playing);
    gtk_widget_set_visible(d->album,playing);
    gtk_widget_set_visible(d->title,playing);
    gtk_widget_set_visible(d->idle_quote,!playing);
    simple_song_progress_update(d->song_progress,s->position,s->duration,playing);
    simple_music_layout(&d->layout,playing);
    if(s->pix) {
      int width=gdk_pixbuf_get_width(s->pix),height=gdk_pixbuf_get_height(s->pix);
      int limit=d->layout.playing_size;
      if(MAX(width,height)>limit) {
        double scale=(double)limit/MAX(width,height);
        GdkPixbuf *scaled=gdk_pixbuf_scale_simple(s->pix,MAX(1,(int)(width*scale)),MAX(1,(int)(height*scale)),GDK_INTERP_BILINEAR);
        if(scaled){g_object_unref(s->pix);s->pix=scaled;}
      }
    }
    gtk_label_set_text(GTK_LABEL(d->network),s->network);
    char *desktop=g_strdup_printf("%s · %s packages",s->system.desktop,s->system.packages);
    gtk_label_set_text(GTK_LABEL(d->desktop),desktop);gtk_widget_set_tooltip_text(d->desktop,desktop);g_free(desktop);
    gtk_label_set_text(GTK_LABEL(d->terminal),s->system.terminal);
    gtk_label_set_text(GTK_LABEL(d->init),s->system.init);
    char *phone=simple_phone_line(&d->phone_history,&s->phone,g_get_monotonic_time()/1000000.0);
    gtk_label_set_text(GTK_LABEL(d->phone),phone);g_free(phone);
    char *tip=phone_charge_tooltip(s->phone.percent,s->phone.charging,&d->phone_history.display);
    gtk_widget_set_tooltip_text(d->phone,tip);g_free(tip);
    if (s->art_changed) {
      GdkTexture *texture=NULL;
      if(s->pix) {
        GBytes *pixels=gdk_pixbuf_read_pixel_bytes(s->pix);
        texture=GDK_TEXTURE(gdk_memory_texture_new(gdk_pixbuf_get_width(s->pix),gdk_pixbuf_get_height(s->pix),
          gdk_pixbuf_get_has_alpha(s->pix)?GDK_MEMORY_R8G8B8A8:GDK_MEMORY_R8G8B8,pixels,gdk_pixbuf_get_rowstride(s->pix)));
        g_bytes_unref(pixels);
      }
      gtk_picture_set_paintable(GTK_PICTURE(d->picture),texture?GDK_PAINTABLE(texture):NULL);
      gtk_widget_set_visible(d->placeholder,!texture);
      g_clear_object(&texture);g_free(d->art);d->art=g_strdup(s->art_key);
    }
  }
  snapshot_free(s);
}
static gboolean refresh(gpointer data) {
  Dashboard *d=data;
  if (!d->busy) {
    d->busy=TRUE;
    GTask *task=g_task_new(NULL,d->cancel,ready,d);
    FetchData *f=g_new0(FetchData,1);f->key=g_strdup(d->art);f->resolution=d->art_resolution;
    g_task_set_task_data(task,f,fetch_data_free);
    g_task_run_in_thread(task,fetch);g_object_unref(task);
  }
  return G_SOURCE_CONTINUE;
}
static gboolean clock_tick(gpointer data) {
  Dashboard *d=data;GDateTime *now=g_date_time_new_now_local();
  char *clock=g_date_time_format(now,"%H:%M"), *date=g_date_time_format(now,"%A, %e %B");
  gtk_label_set_text(GTK_LABEL(d->clock),clock);gtk_label_set_text(GTK_LABEL(d->date),date);
  g_free(clock);g_free(date);g_date_time_unref(now);
  char *up=NULL;double seconds=0;
  if(g_file_get_contents("/proc/uptime",&up,NULL,NULL))seconds=g_ascii_strtod(up,NULL);
  g_free(up);guint64 minutes=(guint64)seconds/60;
  char *uptime=g_strdup_printf("%"G_GUINT64_FORMAT"d %"G_GUINT64_FORMAT"h %"G_GUINT64_FORMAT"m",
    minutes/1440,(minutes/60)%24,minutes%60);
  gtk_label_set_text(GTK_LABEL(d->uptime),uptime);g_free(uptime);
  struct statvfs fs; char *space=NULL;
  if (!statvfs(g_get_home_dir(),&fs)) {
    char *free_space=g_format_size((guint64)fs.f_bavail*fs.f_frsize);
    space=g_strdup_printf("%s free",free_space);g_free(free_space);
  }
  gtk_label_set_text(GTK_LABEL(d->disk),space?space:"Unavailable");g_free(space);
  char *mem=NULL;guint64 total=0,available=0;
  if(g_file_get_contents("/proc/meminfo",&mem,NULL,NULL)) {
    char **lines=g_strsplit(mem,"\n",-1);
    for(int i=0;lines[i];i++) {
      if(g_str_has_prefix(lines[i],"MemTotal:"))total=g_ascii_strtoull(lines[i]+9,NULL,10);
      if(g_str_has_prefix(lines[i],"MemAvailable:"))available=g_ascii_strtoull(lines[i]+13,NULL,10);
    }
    g_strfreev(lines);g_free(mem);
  }
  char *memory=g_strdup_printf("%.1f / %.1f GiB",(total-MIN(total,available))/1048576.0,total/1048576.0);
  gtk_label_set_text(GTK_LABEL(d->memory),memory);g_free(memory);
  GString *info=g_string_new(NULL);
  GDir *dir=g_dir_open("/sys/class/power_supply",0,NULL);const char *entry;
  while (dir && (entry=g_dir_read_name(dir))) {
    char *path=g_build_filename("/sys/class/power_supply",entry,"type",NULL),*type=NULL;
    g_file_get_contents(path,&type,NULL,NULL);g_free(path);
    if (type && g_str_has_prefix(type,"Battery")) {
      char *capacity=NULL,*status=NULL;
      path=g_build_filename("/sys/class/power_supply",entry,"capacity",NULL);g_file_get_contents(path,&capacity,NULL,NULL);g_free(path);
      path=g_build_filename("/sys/class/power_supply",entry,"status",NULL);g_file_get_contents(path,&status,NULL,NULL);g_free(path);
      if(capacity)g_string_append_printf(info,"%s%s%%  %s",info->len?" · ":"",g_strstrip(capacity),status?g_strstrip(status):"");
      g_free(capacity);g_free(status);
    }
    g_free(type);
  }
  if(dir)g_dir_close(dir);
  gtk_label_set_text(GTK_LABEL(d->battery),info->len?info->str:"AC power");g_string_free(info,TRUE);
  return G_SOURCE_CONTINUE;
}
static GtkWidget *label(const char *text,const char *css) {
  GtkWidget *w=gtk_label_new(text);gtk_label_set_xalign(GTK_LABEL(w),0);
  gtk_label_set_wrap(GTK_LABEL(w),TRUE);gtk_label_set_max_width_chars(GTK_LABEL(w),36);
  if(css)gtk_widget_add_css_class(w,css);
  return w;
}
static GtkWidget *info_row(GtkWidget *grid,int row,const char *name,const char *value) {
  GtkWidget *key=label(name,"dash-key"),*val=label(value,"dash-value");
  gtk_widget_set_valign(key,GTK_ALIGN_START);
  gtk_widget_set_hexpand(val,TRUE);
  gtk_label_set_max_width_chars(GTK_LABEL(val),34);
  gtk_label_set_ellipsize(GTK_LABEL(val),PANGO_ELLIPSIZE_END);
  gtk_label_set_wrap(GTK_LABEL(val),FALSE);
  gtk_grid_attach(GTK_GRID(grid),key,0,row,1,1);gtk_grid_attach(GTK_GRID(grid),val,1,row,1,1);
  return val;
}
static void cava_draw(GtkDrawingArea *area,cairo_t *cr,int width,int height,gpointer data) {
  Dashboard *d=data;GdkRGBA color;
  gtk_widget_get_color(GTK_WIDGET(area),&color);
  GdkRGBA high;gtk_widget_get_color(d->visualizer_accent,&high);
  cairo_pattern_t *gradient=cairo_pattern_create_linear(0,height,0,0);
  cairo_pattern_add_color_stop_rgba(gradient,0,color.red,color.green,color.blue,.85);
  cairo_pattern_add_color_stop_rgba(gradient,1,high.red,high.green,high.blue,1.0);
  cairo_set_source(cr,gradient);
  int count=d->fullscreen?128:64;
  double step=(double)width/count;
  for(int i=0;i<count;i++) {
    double h=MAX(2.0,d->bars[i]/255.0*(height-2));
    cairo_rectangle(cr,i*step,height-h,MAX(1.0,step-1.5),h);cairo_fill(cr);
  }
  cairo_pattern_destroy(gradient);
}
static gboolean cava_read(int fd,GIOCondition cond,gpointer data) {
  Dashboard *d=data;guint8 buf[4096];ssize_t n;
  if(d->m->closed){d->cava_watch=0;return G_SOURCE_REMOVE;}
  while((n=read(fd,buf,sizeof buf))>0) {
    for(ssize_t i=0;i<n;i++) {
      d->pending[d->pending_size++]=buf[i];
      if(d->pending_size==(d->fullscreen?128u:64u)) {memcpy(d->bars,d->pending,d->pending_size);d->pending_size=0;}
    }
  }
  gtk_widget_queue_draw(d->visualizer);
  if(n==0 || (n<0 && errno!=EAGAIN && errno!=EINTR) || (cond&(G_IO_HUP|G_IO_ERR))) {
    d->cava_watch=0;gtk_widget_set_visible(d->visualizer,FALSE);return G_SOURCE_REMOVE;
  }
  return G_SOURCE_CONTINUE;
}
static void cava_start(Dashboard *d) {
  char *program=g_find_program_in_path("cava");
  if(!program){gtk_widget_set_visible(d->visualizer,FALSE);return;}
  int config_fd=g_file_open_tmp("simplelock-cava-XXXXXX",&d->cava_config,NULL);
  if(config_fd<0){g_free(program);gtk_widget_set_visible(d->visualizer,FALSE);return;}
  close(config_fd);
  char *config=g_strdup_printf("[general]\nbars=%d\nframerate=60\nautosens=1\n[input]\nmethod=pulse\nsource=auto\n"
    "[output]\nmethod=raw\nraw_target=/dev/stdout\ndata_format=binary\nbit_format=8bit\nchannels=mono\n",d->fullscreen?128:64);
  char *argv[]={program,"-p",d->cava_config,NULL};
  if(!g_file_set_contents(d->cava_config,config,-1,NULL) ||
     !g_spawn_async_with_pipes(NULL,argv,NULL,G_SPAWN_DO_NOT_REAP_CHILD|G_SPAWN_STDERR_TO_DEV_NULL,
       NULL,NULL,&d->cava_pid,NULL,&d->cava_fd,NULL,NULL)) {
    gtk_widget_set_visible(d->visualizer,FALSE);g_free(config);g_free(program);return;
  }
  g_free(config);
  fcntl(d->cava_fd,F_SETFL,fcntl(d->cava_fd,F_GETFL)|O_NONBLOCK);
  d->cava_watch=g_unix_fd_add(d->cava_fd,G_IO_IN|G_IO_HUP|G_IO_ERR,cava_read,d);
  g_free(program);
}
static void cava_stop(Dashboard *d) {
  if(d->cava_watch)g_source_remove(d->cava_watch);
  if(d->cava_fd>=0)close(d->cava_fd);
  if(d->cava_pid) {
    /* This private child owns no persistent data; reap it without delaying close. */
    kill(d->cava_pid,SIGKILL);
    while(waitpid(d->cava_pid,NULL,0)<0 && errno==EINTR){}
    g_spawn_close_pid(d->cava_pid);
  }
  if(d->cava_config){unlink(d->cava_config);g_free(d->cava_config);}
}

static void submit(GtkWidget *entry,gpointer data);
static gboolean lock_key(GtkEventControllerKey *controller,guint key,guint code,GdkModifierType mods,gpointer data);
static gboolean refuse_close(GtkWindow *w,gpointer data){(void)w;(void)data;return TRUE;}
static void view_destroy(GtkWidget *widget,gpointer data) {
  (void)widget;Dashboard *d=data;
  d->m->closed=TRUE;
  simple_daylight_art_clear(&d->daylight_art);simple_daylight_art_clear(&d->idle_art);
  g_clear_object(&d->playing_texture);g_clear_object(&d->idle_texture);
  if(d->timer){g_source_remove(d->timer);d->timer=0;}
  if(d->clock_timer){g_source_remove(d->clock_timer);d->clock_timer=0;}
  cava_stop(d);d->cava_pid=0;d->cava_watch=0;d->cava_fd=-1;d->cava_config=NULL;
  g_cancellable_cancel(d->cancel);
}
static void monitor_added(GtkSessionLockInstance *instance,GdkMonitor *monitor,gpointer unused) {
  (void)unused;gboolean fullscreen=TRUE;
  Menu *m=g_new0(Menu,1);m->window=gtk_window_new();
  Dashboard *d=g_new0(Dashboard,1);d->m=m;d->fullscreen=TRUE;d->cancel=g_cancellable_new();d->cava_fd=-1;
  g_ptr_array_add(views,d);
  gtk_window_set_title(GTK_WINDOW(m->window),"Simplelock");
  gtk_window_set_decorated(GTK_WINDOW(m->window),FALSE);
  gtk_widget_add_css_class(m->window,"simplepicker");gtk_widget_add_css_class(m->window,"dashboard");
  gtk_widget_add_css_class(m->window,"screensaver");gtk_widget_add_css_class(m->window,"simplelock");
  GdkDisplay *display=gdk_display_get_default();GtkCssProvider *base=gtk_css_provider_new(),*css=gtk_css_provider_new(),*custom=gtk_css_provider_new();
  gtk_css_provider_load_from_string(base,
    "window.dashboard {background:transparent;} .dashboard-panel {background:@theme_bg_color;color:@theme_fg_color;border-radius:20px;padding:26px;}"
    ".dashboard .dash-title {font-size:1.6429rem;font-weight:bold;} .dashboard .dash-clock {font-size:1.4286rem;font-weight:bold;}"
    ".dashboard .dash-muted {opacity:.7;} .dashboard .dash-status {font-size:0.7857rem;opacity:.65;}"
    ".dashboard .dash-art {background:alpha(@theme_fg_color,.06);border-radius:14px;}"
    ".dashboard .dash-calendar {background:alpha(@theme_fg_color,.035);border-radius:12px;} .dashboard calendar {padding:10px;} .dashboard calendar grid label {padding:6px;}"
    ".dashboard calendar header {padding-bottom:10px;} .dashboard calendar button {padding:4px;}"
    ".dashboard calendar .today {font-weight:bold;} .dashboard calendar label:selected {background:@theme_selected_bg_color;color:@theme_selected_fg_color;border-radius:6px;}"
    ".dashboard .dash-info {font-size:0.9286rem;} .dashboard .dash-key {font-size:0.8571rem;opacity:.6;}"
    ".dashboard .dash-value {font-size:0.9286rem;} .dashboard .dash-system {background:alpha(@theme_fg_color,.035);border-radius:12px;padding:14px;}"
    ".dashboard .dash-visualizer {color:@theme_selected_bg_color;margin-top:8px;} .dashboard .dash-visualizer-high {color:@theme_selected_bg_color;} .dashboard .dash-monk {border-radius:12px;} "
    ".dashboard separator {background:alpha(@theme_fg_color,.15);min-height:1px;}"
    "window.dashboard.screensaver {background:transparent;} .screensaver .dashboard-panel {background:transparent;border:0;box-shadow:none;border-radius:0;}"
    ".screensaver .dash-clock {font-size:1.7143rem;} .screensaver .dash-title {font-size:2.0rem;}");
  gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(base),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  char *theme=appearance_path("style.css");if(theme){simple_theme_load(css,theme);gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER);}g_free(theme);
  char *path=appearance_path("dashboard.css");
  if(g_file_test(path,G_FILE_TEST_IS_REGULAR)){simple_theme_load(custom,path);gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(custom),GTK_STYLE_PROVIDER_PRIORITY_USER+2);}g_free(path);
  GtkCssProvider *lock_css=gtk_css_provider_new();
  gtk_css_provider_load_from_string(lock_css,
    "window.simplelock {background:@simple_bg;} .simplelock .lock-password {padding:12px;background:@simple_surface;border-radius:8px;color:@simple_bright;font-size:1.2857rem;min-width:250px;}"
    ".simplelock .lock-card {background:alpha(@simple_surface,.94);border-radius:12px;padding:14px;} .simplelock .lock-feedback {font-size:0.9286rem;color:@simple_attention;}"
    ".simplelock .dash-visualizer {margin:0;} .simplelock .dashboard-panel {padding:16px;}" );
  gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(lock_css),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION+1);
  char *lock_path=appearance_path("lock.css");
  GtkCssProvider *extra=gtk_css_provider_new();
  if(g_file_test(lock_path,G_FILE_TEST_IS_REGULAR)){simple_theme_load(extra,lock_path);gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(extra),GTK_STYLE_PROVIDER_PRIORITY_USER+4);}g_free(lock_path);
  g_object_unref(base);g_object_unref(css);g_object_unref(custom);g_object_unref(lock_css);g_object_unref(extra);
  m->outer=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
  GtkWidget *stage=gtk_overlay_new();gtk_window_set_child(GTK_WINDOW(m->window),stage);
  gtk_overlay_set_child(GTK_OVERLAY(stage),backdrop_new(monitor));gtk_overlay_add_overlay(GTK_OVERLAY(stage),fit_new(m->outer));
  gtk_widget_set_hexpand(m->outer,TRUE);gtk_widget_set_vexpand(m->outer,TRUE);
  gtk_widget_set_opacity(stage,0);gtk_widget_add_tick_callback(stage,fade_in,g_new0(gint64,1),g_free);
  m->panel=gtk_grid_new();gtk_grid_set_column_spacing(GTK_GRID(m->panel),30);gtk_widget_add_css_class(m->panel,"box-wrapper");gtk_widget_add_css_class(m->panel,"dashboard-panel");
  gtk_widget_set_halign(m->panel,GTK_ALIGN_CENTER);gtk_widget_set_valign(m->panel,GTK_ALIGN_CENTER);gtk_widget_set_vexpand(m->panel,TRUE);gtk_box_append(GTK_BOX(m->outer),m->panel);
  GtkWidget *music=gtk_box_new(GTK_ORIENTATION_VERTICAL,10),*side=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);
  int art_size=480;
  if(fullscreen && monitor){GdkRectangle geometry;gdk_monitor_get_geometry(monitor,&geometry);
    art_size=CLAMP(geometry.height-470,220,640);}

  d->art_resolution=art_size;
  gtk_widget_set_size_request(music,art_size,-1);gtk_widget_set_size_request(side,fullscreen?500:450,-1);
  if(fullscreen)gtk_grid_set_row_spacing(GTK_GRID(m->panel),12);
  gtk_grid_attach(GTK_GRID(m->panel),music,0,0,1,1);gtk_grid_attach(GTK_GRID(m->panel),side,1,0,1,1);
  d->status=label(idle_title,"dash-status");if(fullscreen)gtk_widget_add_css_class(d->status,"dash-status-card");gtk_box_append(GTK_BOX(music),d->status);
  PangoAttrList *heading_attrs=pango_attr_list_new();
  pango_attr_list_insert(heading_attrs,pango_attr_size_new_absolute(14*PANGO_SCALE));
  pango_attr_list_insert(heading_attrs,pango_attr_weight_new(PANGO_WEIGHT_SEMIBOLD));
  gtk_label_set_attributes(GTK_LABEL(d->status),heading_attrs);
  gtk_label_set_wrap(GTK_LABEL(d->status),TRUE);
  gtk_label_set_xalign(GTK_LABEL(d->status),0.5);
  gtk_label_set_justify(GTK_LABEL(d->status),GTK_JUSTIFY_CENTER);
  gtk_label_set_ellipsize(GTK_LABEL(d->status),PANGO_ELLIPSIZE_NONE);
  d->idle_quote=label(idle_title,"dash-idle-quote");
  gtk_label_set_attributes(GTK_LABEL(d->idle_quote),heading_attrs);pango_attr_list_unref(heading_attrs);
  gtk_label_set_wrap(GTK_LABEL(d->idle_quote),TRUE);
  gtk_label_set_xalign(GTK_LABEL(d->idle_quote),0.5);
  gtk_label_set_justify(GTK_LABEL(d->idle_quote),GTK_JUSTIFY_CENTER);
  gtk_label_set_ellipsize(GTK_LABEL(d->idle_quote),PANGO_ELLIPSIZE_NONE);
  gtk_widget_set_vexpand(d->idle_quote,TRUE);gtk_widget_set_valign(d->idle_quote,GTK_ALIGN_CENTER);
  GtkWidget *art=gtk_overlay_new();gtk_widget_add_css_class(art,"dash-art");gtk_widget_set_size_request(art,art_size,art_size);gtk_widget_set_overflow(art,GTK_OVERFLOW_HIDDEN);
  d->picture=gtk_picture_new();gtk_picture_set_can_shrink(GTK_PICTURE(d->picture),TRUE);gtk_picture_set_content_fit(GTK_PICTURE(d->picture),GTK_CONTENT_FIT_CONTAIN);/* Cover dimensions must not participate in layout measurement: GtkPicture's
   * height-for-width request otherwise stretches portrait art and shrinks the
   * entire LockFit surface, including text. Both images fill a fixed art frame. */
  gtk_overlay_set_child(GTK_OVERLAY(art),gtk_drawing_area_new());
  gtk_overlay_add_overlay(GTK_OVERLAY(art),d->picture);
  gtk_overlay_set_measure_overlay(GTK_OVERLAY(art),d->picture,FALSE);
  char *idle_image=simple_image_resolve("idle");if(!idle_image)idle_image=artwork_path(lock_album_idle_image);
  if(g_file_test(idle_image,G_FILE_TEST_IS_REGULAR)) {
    d->placeholder=gtk_picture_new_for_filename(idle_image);
    gtk_picture_set_can_shrink(GTK_PICTURE(d->placeholder),TRUE);
    gtk_picture_set_content_fit(GTK_PICTURE(d->placeholder),GTK_CONTENT_FIT_COVER);
    d->idle_art.picture=GTK_PICTURE(d->placeholder);d->idle_art.full_image=TRUE;
  }else{
    d->placeholder=gtk_image_new_from_icon_name("audio-x-generic-symbolic");gtk_image_set_pixel_size(GTK_IMAGE(d->placeholder),80);
  }
  g_free(idle_image);
  gtk_overlay_add_overlay(GTK_OVERLAY(art),d->placeholder);
  GtkWidget *art_card=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
  gtk_widget_add_css_class(art_card,"dash-system");gtk_widget_add_css_class(art_card,"dash-album-card");
  gtk_box_append(GTK_BOX(art_card),art);gtk_box_append(GTK_BOX(music),art_card);
  if(fullscreen){gtk_widget_set_vexpand(art_card,TRUE);gtk_widget_set_vexpand(art,TRUE);}
  d->title=label(idle_title,"dash-title");d->artist=label(idle_subtitle,NULL);d->album=label("","dash-muted");
  for(GtkWidget **w=(GtkWidget*[]){d->title,d->artist,d->album,NULL};*w;w++){gtk_label_set_wrap(GTK_LABEL(*w),FALSE);gtk_label_set_ellipsize(GTK_LABEL(*w),PANGO_ELLIPSIZE_END);gtk_label_set_max_width_chars(GTK_LABEL(*w),65);}
  PangoAttrList *artist_attrs=pango_attr_list_new();
  pango_attr_list_insert(artist_attrs,pango_attr_weight_new(PANGO_WEIGHT_BOLD));
  gtk_label_set_attributes(GTK_LABEL(d->artist),artist_attrs);pango_attr_list_unref(artist_attrs);
  GtkWidget *metadata=gtk_box_new(GTK_ORIENTATION_VERTICAL,6);d->metadata=metadata;
  gtk_widget_add_css_class(metadata,"dash-system");gtk_widget_add_css_class(metadata,"dash-metadata");
  gtk_box_append(GTK_BOX(metadata),d->artist);gtk_box_append(GTK_BOX(metadata),d->album);gtk_box_append(GTK_BOX(metadata),d->title);
  d->song_progress=simple_song_progress_new();gtk_box_append(GTK_BOX(metadata),d->song_progress);
  gtk_box_append(GTK_BOX(metadata),d->idle_quote);
  gtk_widget_set_size_request(metadata,-1,fullscreen?116:76);
  gtk_box_append(GTK_BOX(music),metadata);
  d->visualizer_accent=gtk_label_new("");gtk_widget_add_css_class(d->visualizer_accent,"dash-visualizer-high");
  gtk_widget_set_visible(d->visualizer_accent,FALSE);gtk_box_append(GTK_BOX(music),d->visualizer_accent);
  d->visualizer=gtk_drawing_area_new();gtk_widget_add_css_class(d->visualizer,"dash-visualizer");
  gtk_widget_set_size_request(d->visualizer,-1,58);
  gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(d->visualizer),cava_draw,d,NULL);
  gtk_widget_set_size_request(d->visualizer,-1,fullscreen?72:58);
  gtk_grid_attach(GTK_GRID(m->panel),d->visualizer,0,1,2,1);
  gtk_grid_set_row_spacing(GTK_GRID(m->panel),12);
  GtkWidget *time_card=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,14);gtk_widget_add_css_class(time_card,"dash-system");gtk_widget_add_css_class(time_card,"dash-time");
  d->clock=label("","dash-clock");d->date=label("","dash-muted");gtk_box_append(GTK_BOX(time_card),d->clock);gtk_box_append(GTK_BOX(time_card),d->date);gtk_box_append(GTK_BOX(side),time_card);
  PangoAttrList *clock_attrs=pango_attr_list_new();
  pango_attr_list_insert(clock_attrs,pango_attr_weight_new(PANGO_WEIGHT_BOLD));
  pango_attr_list_insert(clock_attrs,pango_attr_scale_new(1.5));
  gtk_label_set_attributes(GTK_LABEL(d->clock),clock_attrs);pango_attr_list_unref(clock_attrs);
  gtk_widget_set_valign(d->date,GTK_ALIGN_CENTER);
  gtk_label_set_wrap(GTK_LABEL(d->date),FALSE);
  GtkWidget *calendar_row=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,16);
  GtkWidget *calendar=gtk_calendar_new();d->calendar=calendar;gtk_widget_add_css_class(calendar,"dash-calendar");gtk_widget_set_hexpand(calendar,TRUE);
  gtk_box_append(GTK_BOX(calendar_row),calendar);
  d->mood_art=gtk_picture_new();d->daylight_art.picture=GTK_PICTURE(d->mood_art);
  const char *art_names[]={lock_playing_image,lock_idle_image};

  for(int state=0;state<2;state++) {
    char *path=artwork_path(art_names[state]);
    GdkPixbuf *pix=gdk_pixbuf_new_from_file_at_scale(path,180,250,TRUE,NULL);
    g_free(path);
    if(pix) {
      GBytes *bytes=gdk_pixbuf_read_pixel_bytes(pix);
      GdkTexture *texture=GDK_TEXTURE(gdk_memory_texture_new(gdk_pixbuf_get_width(pix),gdk_pixbuf_get_height(pix),
        gdk_pixbuf_get_has_alpha(pix)?GDK_MEMORY_R8G8B8A8:GDK_MEMORY_R8G8B8,bytes,gdk_pixbuf_get_rowstride(pix)));
      g_bytes_unref(bytes);
      if(state)d->idle_texture=texture;else d->playing_texture=texture;
      g_object_unref(pix);
    }

  }
  gtk_picture_set_paintable(GTK_PICTURE(d->mood_art),GDK_PAINTABLE(d->idle_texture));
  simple_daylight_art_update(&d->daylight_art);
  gtk_picture_set_can_shrink(GTK_PICTURE(d->mood_art),TRUE);
  gtk_picture_set_content_fit(GTK_PICTURE(d->mood_art),GTK_CONTENT_FIT_COVER);
  gtk_widget_set_size_request(d->mood_art,180,250);
  gtk_widget_set_valign(d->mood_art,GTK_ALIGN_FILL);
  gtk_widget_add_css_class(d->mood_art,"dash-monk");
  gtk_widget_set_overflow(d->mood_art,GTK_OVERFLOW_HIDDEN);
  gtk_box_append(GTK_BOX(calendar_row),d->mood_art);
  gtk_box_append(GTK_BOX(side),calendar_row);
  gtk_box_append(GTK_BOX(side),simple_calendar_details(GTK_CALENDAR(calendar)));
  simple_calendar_navigation(GTK_CALENDAR(calendar),"simplelock",NULL);
  GtkWidget *network_panel=gtk_box_new(GTK_ORIENTATION_VERTICAL,8);
  gtk_widget_add_css_class(network_panel,"dash-system");gtk_widget_add_css_class(network_panel,"dash-network");
  gtk_box_append(GTK_BOX(network_panel),label("NETWORK & PHONE","dash-key"));
  d->network=label("Checking connection…","dash-info");gtk_box_append(GTK_BOX(network_panel),d->network);
  d->phone=label("Phone · checking…","dash-info");gtk_box_append(GTK_BOX(network_panel),d->phone);
  gtk_label_set_wrap(GTK_LABEL(d->network),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d->network),PANGO_ELLIPSIZE_END);
  gtk_label_set_wrap(GTK_LABEL(d->phone),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d->phone),PANGO_ELLIPSIZE_END);
  gtk_box_append(GTK_BOX(side),network_panel);
  GtkWidget *grid=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(grid),8);gtk_grid_set_column_spacing(GTK_GRID(grid),18);
  gtk_widget_add_css_class(grid,"dash-system");
  char *os=g_get_os_info(G_OS_INFO_KEY_NAME);struct utsname uts;uname(&uts);
  char *system=g_strdup_printf("%s (%s) — %s",os?os:"Linux",g_get_host_name(),uts.release);
  GtkWidget *system_label=info_row(grid,0,"SYSTEM",system);
  gtk_label_set_wrap(GTK_LABEL(system_label),TRUE);gtk_label_set_ellipsize(GTK_LABEL(system_label),PANGO_ELLIPSIZE_NONE);
  gtk_widget_set_tooltip_text(system_label,system);g_free(system);g_free(os);
  d->init=info_row(grid,1,"INIT SYSTEM","Checking…");
  d->desktop=info_row(grid,2,"DESKTOP","Checking…");
  d->uptime=info_row(grid,3,"UPTIME","");
  d->terminal=info_row(grid,4,"TERM","Checking…");
  char *cpuinfo=NULL,*cpu=NULL;
  if(g_file_get_contents("/proc/cpuinfo",&cpuinfo,NULL,NULL)) {
    char **lines=g_strsplit(cpuinfo,"\n",-1);
    for(int i=0;lines[i] && !cpu;i++)if(g_str_has_prefix(lines[i],"model name")) {
      char *colon=strchr(lines[i],':');if(colon)cpu=g_strdup(g_strstrip(colon+1));
    }
    g_strfreev(lines);g_free(cpuinfo);
  }
  info_row(grid,5,"CPU",cpu?cpu:"Unknown");g_free(cpu);
  d->memory=info_row(grid,6,"MEM","");
  d->disk=info_row(grid,7,"HOME DISK","");d->battery=info_row(grid,8,"POWER","");
  gtk_box_append(GTK_BOX(side),grid);
  if(fullscreen){
    gtk_widget_set_vexpand(grid,TRUE);gtk_grid_set_row_homogeneous(GTK_GRID(grid),TRUE);
    for(GtkWidget *child=gtk_widget_get_first_child(grid);child;child=gtk_widget_get_next_sibling(child)) {
      gtk_widget_set_valign(child,GTK_ALIGN_CENTER);gtk_widget_set_vexpand(child,TRUE);
    }
  }
  if(fullscreen){
    /* Match the square cover to the information column, so metadata follows
     * directly below both cards instead of leaving unused space under the art. */
    clock_tick(d);

    int side_height=0,status_height=0,side_width=0;
    gtk_widget_measure(side,GTK_ORIENTATION_HORIZONTAL,-1,NULL,&side_width,NULL,NULL);
    gtk_widget_measure(side,GTK_ORIENTATION_VERTICAL,side_width,NULL,&side_height,NULL,NULL);
    gtk_widget_measure(d->status,GTK_ORIENTATION_VERTICAL,-1,NULL,&status_height,NULL,NULL);
    art_size=MAX(art_size,side_height-status_height-10-24);
    gtk_widget_set_size_request(art,art_size,art_size);
    gtk_widget_set_size_request(music,art_size+24,-1);
    d->art_resolution=art_size;
  }
  GtkWidget *headline=label(idle_subtitle,"dash-headline");
  PangoAttrList *headline_attrs=pango_attr_list_copy(gtk_label_get_attributes(GTK_LABEL(d->status)));
  pango_attr_list_change(headline_attrs,pango_attr_size_new_absolute(16*PANGO_SCALE));
  gtk_label_set_attributes(GTK_LABEL(headline),headline_attrs);pango_attr_list_unref(headline_attrs);
  gtk_label_set_xalign(GTK_LABEL(headline),0.5);gtk_label_set_justify(GTK_LABEL(headline),GTK_JUSTIFY_CENTER);
  GtkWidget *headline_card=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
  gtk_widget_add_css_class(headline_card,"dash-system");gtk_widget_add_css_class(headline_card,"dash-header");
  gtk_widget_set_hexpand(headline,TRUE);
  gtk_widget_set_margin_top(headline,10);gtk_widget_set_margin_bottom(headline,10);
  gtk_widget_set_margin_start(headline,12);gtk_widget_set_margin_end(headline,12);
  gtk_box_append(GTK_BOX(headline_card),headline);
  gtk_grid_attach(GTK_GRID(m->panel),headline_card,0,-1,2,1);
  d->layout=(SimpleMusicLayout){.grid=m->panel,.music=music,.side=side,.art=art,
    .art_card=art_card,.metadata=metadata,.visualizer=d->visualizer,.status=d->status,
    .headline=headline_card,.fullscreen=fullscreen,.idle_size=art_size,.metadata_columns=1};
  /* One compact unlock row; reserve the main area for artwork and information. */
  GtkWidget *auth=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,16);gtk_widget_add_css_class(auth,"lock-card");gtk_widget_add_css_class(auth,"lock-auth");
  gtk_widget_set_vexpand(auth,FALSE);gtk_widget_set_valign(auth,GTK_ALIGN_FILL);
  GtkWidget *auth_info=gtk_box_new(GTK_ORIENTATION_VERTICAL,3);gtk_widget_set_hexpand(auth_info,TRUE);gtk_widget_set_valign(auth_info,GTK_ALIGN_CENTER);
  char *caption=g_strdup_printf("Locked · %s",lock_user);GtkWidget *heading=label(caption,"dash-status");g_free(caption);gtk_box_append(GTK_BOX(auth_info),heading);
  d->feedback=label(auth_busy?"Checking password…":"Enter · unlock   Tab · calendar / password","lock-feedback");
  gtk_label_set_wrap(GTK_LABEL(d->feedback),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d->feedback),PANGO_ELLIPSIZE_END);gtk_label_set_max_width_chars(GTK_LABEL(d->feedback),52);gtk_label_set_width_chars(GTK_LABEL(d->feedback),52);
  gtk_box_append(GTK_BOX(auth_info),d->feedback);gtk_box_append(GTK_BOX(auth),auth_info);
  d->entry=gtk_password_entry_new();gtk_widget_add_css_class(d->entry,"lock-password");
  gtk_password_entry_set_show_peek_icon(GTK_PASSWORD_ENTRY(d->entry),FALSE);
  gtk_widget_set_size_request(d->entry,300,-1);gtk_widget_set_hexpand(d->entry,FALSE);gtk_widget_set_vexpand(d->entry,FALSE);gtk_widget_set_valign(d->entry,GTK_ALIGN_CENTER);gtk_widget_set_sensitive(d->entry,!auth_busy);
  gtk_box_append(GTK_BOX(auth),d->entry);
  gtk_grid_attach(GTK_GRID(m->panel),auth,1,2,1,1);
  g_signal_connect(d->entry,"activate",G_CALLBACK(submit),d);
  GtkEventController *keys=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(keys,GTK_PHASE_CAPTURE);
  g_signal_connect(keys,"key-pressed",G_CALLBACK(lock_key),d);gtk_widget_add_controller(m->window,keys);
  g_signal_connect(m->window,"close-request",G_CALLBACK(refuse_close),d);
  g_signal_connect(m->window,"destroy",G_CALLBACK(view_destroy),d);
  d->timer=g_timeout_add_seconds(2,refresh,d);d->clock_timer=g_timeout_add_seconds(10,clock_tick,d);
  clock_tick(d);refresh(d);if(lock_visualizer)cava_start(d);else gtk_widget_set_visible(d->visualizer,FALSE);
  gtk_widget_grab_focus(d->entry);
  gtk_session_lock_instance_assign_window_to_monitor(instance,GTK_WINDOW(m->window),monitor);
}
