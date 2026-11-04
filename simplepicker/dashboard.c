#include "simple-theme.h"
#include "../simple-common/daylight-art.h"
#include "../simple-common/calendar.h"
#include "../simple-common/phone-network.h"
#include "../simple-common/system-info.h"
#include "../simple-common/music-layout.h"
#include "media.h"
#include "sp.h"
#include "../simple-common/idle-audio.h"
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

/* One in-memory desktop capture, rendered with GTK's GPU blur. No image files. */
typedef struct { GtkWidget parent; GdkTexture *texture; } DashBackdrop;
typedef GtkWidgetClass DashBackdropClass;
G_DEFINE_TYPE(DashBackdrop,dash_backdrop,GTK_TYPE_WIDGET)
static void backdrop_snapshot(GtkWidget *widget,GtkSnapshot *snapshot) {
  DashBackdrop *self=(DashBackdrop*)widget;
  float w=gtk_widget_get_width(widget),h=gtk_widget_get_height(widget);
  graphene_rect_t bounds=GRAPHENE_RECT_INIT(-24,-24,w+48,h+48);
  if(self->texture){gtk_snapshot_push_blur(snapshot,11);gtk_snapshot_append_texture(snapshot,self->texture,&bounds);gtk_snapshot_pop(snapshot);}
  GdkRGBA shade={.08,.08,.08,self->texture?.32:1.0};
  bounds=GRAPHENE_RECT_INIT(0,0,w,h);gtk_snapshot_append_color(snapshot,&shade,&bounds);
}
static void backdrop_dispose(GObject *object) {
  g_clear_object(&((DashBackdrop*)object)->texture);
  G_OBJECT_CLASS(dash_backdrop_parent_class)->dispose(object);
}
static void dash_backdrop_class_init(DashBackdropClass *klass) {
  GTK_WIDGET_CLASS(klass)->snapshot=backdrop_snapshot;
  G_OBJECT_CLASS(klass)->dispose=backdrop_dispose;
}
static void dash_backdrop_init(DashBackdrop *self) {
  gtk_widget_set_hexpand(GTK_WIDGET(self),TRUE);gtk_widget_set_vexpand(GTK_WIDGET(self),TRUE);
}
static GtkWidget *backdrop_new(GdkMonitor *monitor) {
  DashBackdrop *self=g_object_new(dash_backdrop_get_type(),NULL);
  char *grim=g_find_program_in_path("grim");
  const char *output=monitor?gdk_monitor_get_connector(monitor):NULL;
  if(grim){
    J *args=output?argv_json(grim,"-o",output,"-s","0.5","-l","0","-",NULL):argv_json(grim,"-s","0.5","-l","0","-",NULL);
    GBytes *bytes=run_bytes(args,NULL,2);
    if(!bytes)g_clear_pointer(&last_error,g_free);
    if(bytes){self->texture=gdk_texture_new_from_bytes(bytes,NULL);g_bytes_unref(bytes);}
    g_free(grim);
  }
  return GTK_WIDGET(self);
}
static gboolean fade_in(GtkWidget *widget,GdkFrameClock *clock,gpointer data) {
  (void)clock;gint64 *start=data;gint64 now=g_get_monotonic_time();
  if(!*start)*start=now;
  double progress=MIN(1.0,(now-*start)/450000.0);
  gtk_widget_set_opacity(widget,progress*(2.0-progress));
  return progress<1.0;
}

static char *module_asset(const char *module,const char *name,const char *legacy) {
  char *dir=g_path_get_dirname(config_path);
  char *base=g_path_get_basename(dir);
  char *root=!strcmp(base,"lock")?g_path_get_dirname(dir):g_strdup(dir);
  char *path=g_build_filename(root,module,name,NULL);
  if(!g_file_test(path,G_FILE_TEST_IS_REGULAR)){g_free(path);path=g_build_filename(dir,legacy,NULL);}
  g_free(root);g_free(base);g_free(dir);return path;
}
static char *idle_title,*idle_subtitle;
static void load_idle_caption(void) {
  g_free(idle_title);g_free(idle_subtitle);
  idle_title=g_strdup("Ānāpānasati, mindfulness of breathing");idle_subtitle=g_strdup("No system can imprison a mind that has learned to observe without attachment.");
  char *path=module_asset("dashboard","idle.toml","dashboard-idle.toml");
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
  gboolean art_changed;
} Snapshot;
typedef struct {
  Menu *m;
  GtkWidget *calendar;
  GtkWidget *title, *artist, *album, *status, *picture, *placeholder, *metadata;
  GtkWidget *clock, *date, *network, *memory, *disk, *battery, *visualizer, *visualizer_accent;
  GtkWidget *phone;
  GtkWidget *idle_quote;
  GtkWidget *desktop, *terminal, *init, *uptime;
  SimplePhoneHistory phone_history;
  SimpleMusicLayout layout;
  SimpleDaylightArt daylight_art;
  GPid cava_pid;
  int cava_fd;
  guint cava_watch;
  char *cava_config;
  guint8 bars[128], pending[128];
  gsize pending_size;
  GCancellable *cancel;
  char *art;
  gboolean busy, fullscreen;
  gint64 opened;
  double pointer_x,pointer_y;
  gboolean pointer_known;
} Dashboard;
static void dashboard_fit(Dashboard *d) {
  if(d->fullscreen)return;
  int width=0,height=0,oldw=-1,oldh=-1;
  gtk_widget_measure(d->m->outer,GTK_ORIENTATION_HORIZONTAL,-1,&width,NULL,NULL,NULL);
  gtk_widget_measure(d->m->outer,GTK_ORIENTATION_VERTICAL,width,&height,NULL,NULL,NULL);
  gtk_widget_get_size_request(d->m->window,&oldw,&oldh);
  width=MAX(width,oldw);height=MAX(height,oldh);
  gtk_widget_set_size_request(d->m->window,width,height);
  if(!gtk_widget_get_mapped(d->m->window))
    gtk_window_set_default_size(GTK_WINDOW(d->m->window),MAX(880,width),MAX(700,height));
}

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
static int art_resolution=480;
static GdkPixbuf *art_load(const char *uri, GCancellable *cancel) {
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
        if (meta && rank==2 && rank>best) {
          best=rank;
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
  s->art_changed=g_strcmp0(s->art_key,data)!=0;
  if (s->art_changed) s->pix=art_load(s->art,cancel);
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
    simple_music_layout(&d->layout,playing);
    dashboard_fit(d);
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
  simple_daylight_art_update(&d->daylight_art);
  if (!d->busy) {
    d->busy=TRUE;
    GTask *task=g_task_new(NULL,d->cancel,ready,d);
    g_task_set_task_data(task,g_strdup(d->art),g_free);
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
  int config_fd=g_file_open_tmp("simplepicker-cava-XXXXXX",&d->cava_config,NULL);
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
static gboolean key(GtkEventControllerKey *c,guint k,guint code,GdkModifierType mods,gpointer data) {
  (void)c;(void)code;Dashboard *d=data;
  if(d->fullscreen || k==GDK_KEY_Escape || (k==GDK_KEY_q && !(mods&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))) || (((gdk_keyval_to_lower(k)==GDK_KEY_m && (mods&GDK_CONTROL_MASK)) || (gdk_keyval_to_lower(k)==GDK_KEY_u && (mods&GDK_SHIFT_MASK))) && (mods&GDK_SUPER_MASK))) {
    menu_finish(d->m,NULL);return TRUE;
  }
  if(d->calendar && simple_calendar_key(GTK_CALENDAR(d->calendar),k,mods)) {
    return TRUE;
  }
  /* Do not let GTK's built-in arrows bypass a remapped or disabled action. */
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(d->m->window));
  if(focus && d->calendar && (focus==d->calendar || gtk_widget_is_ancestor(focus,d->calendar)) &&
     k!=GDK_KEY_Tab && k!=GDK_KEY_ISO_Left_Tab)return TRUE;
  return FALSE;
}
static gboolean closed(GtkWindow *w,gpointer data) {(void)w;menu_finish(((Dashboard*)data)->m,NULL);return TRUE;}
static void outside(GtkGestureClick *g,int n,double x,double y,gpointer data) {
  (void)g;(void)n;Dashboard *d=data;graphene_rect_t b;
  if(d->fullscreen){menu_finish(d->m,NULL);return;}
  if(gtk_widget_compute_bounds(d->m->panel,d->m->outer,&b) && !graphene_rect_contains_point(&b,&GRAPHENE_POINT_INIT(x,y))) menu_finish(d->m,NULL);
}
static void pointer_enter(GtkEventControllerMotion *controller,double x,double y,gpointer data) {
  (void)controller;Dashboard *d=data;
  d->pointer_x=x;d->pointer_y=y;d->pointer_known=TRUE;
}
static void motion(GtkEventControllerMotion *controller,double x,double y,gpointer data) {
  (void)controller;Dashboard *d=data;
  gboolean moved=d->pointer_known && ((x-d->pointer_x)*(x-d->pointer_x)+(y-d->pointer_y)*(y-d->pointer_y)>9.0);
  if(!d->pointer_known || g_get_monotonic_time()-d->opened<=700000) {
    d->pointer_x=x;d->pointer_y=y;d->pointer_known=TRUE;return;
  }
  if(d->fullscreen && !d->m->closed && moved){menu_finish(d->m,NULL);}
}
static gboolean receive(int fd,GIOCondition cond,gpointer data) {
  (void)cond;char buf[32];if(recv(fd,buf,sizeof buf,0)>0){menu_finish(((Dashboard*)data)->m,NULL);}return G_SOURCE_CONTINUE;
}
static gboolean bench_close(gpointer data) {menu_finish(((Dashboard*)data)->m,NULL);return G_SOURCE_REMOVE;}
int dashboard_show(gboolean fullscreen,gboolean stop_only) {
  load_idle_caption();
  art_resolution=fullscreen?800:480;
  int fd=socket(AF_UNIX,SOCK_DGRAM|SOCK_NONBLOCK,0);
  struct sockaddr_un addr={.sun_family=AF_UNIX};
  snprintf(addr.sun_path+1,sizeof(addr.sun_path)-1,"simplepicker-%s-%u-%s",fullscreen?"screensaver":"dashboard",getuid(),g_getenv("WAYLAND_DISPLAY")?g_getenv("WAYLAND_DISPLAY"):"default");
  socklen_t length=offsetof(struct sockaddr_un,sun_path)+1+strlen(addr.sun_path+1);
  if(fd<0)return 2;
  if(stop_only){sendto(fd,"close",5,0,(struct sockaddr*)&addr,length);close(fd);return 0;}
  if(bind(fd,(struct sockaddr*)&addr,length)) {
    if(errno==EADDRINUSE){if(!fullscreen)sendto(fd,"close",5,0,(struct sockaddr*)&addr,length);close(fd);return 0;}
    close(fd);return 2;
  }
  g_setenv("GDK_BACKEND","wayland",TRUE);
  if(!gtk_init_check()){close(fd);return 2;}
  Menu *m=menu_new("Dashboard","");m->loop=g_main_loop_new(NULL,FALSE);m->window=gtk_window_new();
  Dashboard d={.m=m,.cancel=g_cancellable_new(),.cava_fd=-1,.fullscreen=fullscreen,.opened=g_get_monotonic_time()};
  gtk_window_set_title(GTK_WINDOW(m->window),"Simplepicker — Dashboard");
  gtk_window_set_decorated(GTK_WINDOW(m->window),FALSE);
  gtk_widget_add_css_class(m->window,"simplepicker");gtk_widget_add_css_class(m->window,"dashboard");
  if(fullscreen){gtk_widget_add_css_class(m->window,"screensaver");gtk_widget_set_cursor_from_name(m->window,"none");}
  const char *layer=str(obj(config,"ui"),"layer_shell");
  gboolean overlay=fullscreen && strcmp(layer,"off") && gtk_layer_is_supported();
  if(fullscreen && !strcmp(layer,"required") && !overlay){gtk_window_destroy(GTK_WINDOW(m->window));g_main_loop_unref(m->loop);menu_free(m);g_object_unref(d.cancel);close(fd);fail("Wayland layer-shell unavailable");return 2;}
  if(overlay){
    gtk_layer_init_for_window(GTK_WINDOW(m->window));gtk_layer_set_namespace(GTK_WINDOW(m->window),fullscreen?"simplepicker-screensaver":"simplepicker-dashboard");
    gtk_layer_set_layer(GTK_WINDOW(m->window),GTK_LAYER_SHELL_LAYER_OVERLAY);
    gtk_layer_set_keyboard_mode(GTK_WINDOW(m->window),GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
    for(int e=0;e<GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER;e++)gtk_layer_set_anchor(GTK_WINDOW(m->window),e,TRUE);
    gtk_layer_set_exclusive_zone(GTK_WINDOW(m->window),-1);
  }else if(fullscreen)gtk_window_fullscreen(GTK_WINDOW(m->window));else gtk_window_set_default_size(GTK_WINDOW(m->window),880,700);
  GdkDisplay *display=gdk_display_get_default();GtkCssProvider *base=gtk_css_provider_new(),*css=gtk_css_provider_new(),*custom=gtk_css_provider_new();
  gtk_css_provider_load_from_string(base,
    "window.dashboard {background:transparent;} .dashboard-panel {background:@theme_bg_color;color:@theme_fg_color;border-radius:20px;padding:26px;}"
    ".dashboard .dash-title {font-size:23px;font-weight:bold;} .dashboard .dash-clock {font-size:20px;font-weight:bold;}"
    ".dashboard .dash-muted {opacity:.7;} .dashboard .dash-status {font-size:11px;opacity:.65;}"
    ".dashboard .dash-art {background:alpha(@theme_fg_color,.06);border-radius:14px;}"
    ".dashboard .dash-calendar {background:alpha(@theme_fg_color,.035);border-radius:12px;} .dashboard calendar {padding:10px;} .dashboard calendar grid label {padding:6px;}"
    ".dashboard calendar header {padding-bottom:10px;} .dashboard calendar button {padding:4px;}"
    ".dashboard calendar .today {font-weight:bold;} .dashboard calendar label:selected {background:@theme_selected_bg_color;color:@theme_selected_fg_color;border-radius:6px;}"
    ".dashboard .dash-info {font-size:13px;} .dashboard .dash-key {font-size:12px;opacity:.6;}"
    ".dashboard .dash-value {font-size:13px;} .dashboard .dash-system {background:alpha(@theme_fg_color,.035);border-radius:12px;padding:14px;}"
    ".dashboard .dash-visualizer {color:@theme_selected_bg_color;margin-top:8px;} .dashboard .dash-visualizer-high {color:@theme_selected_bg_color;} .dashboard .dash-monk {border-radius:12px;} "
    ".dashboard separator {background:alpha(@theme_fg_color,.15);min-height:1px;}"
    "window.dashboard.screensaver {background:transparent;} .screensaver .dashboard-panel {background:transparent;border:0;box-shadow:none;border-radius:0;}"
    ".screensaver .dash-clock {font-size:24px;} .screensaver .dash-title {font-size:28px;}");
  gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(base),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  char *theme=theme_path(FALSE);{simple_theme_load(css,theme);gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER);}g_free(theme);
  char *path=module_asset("dashboard","style.css","dashboard.css");
  if(g_file_test(path,G_FILE_TEST_IS_REGULAR)){simple_theme_load(custom,path);gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(custom),GTK_STYLE_PROVIDER_PRIORITY_USER+2);}g_free(path);
  m->outer=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
  GdkMonitor *monitor=NULL;
  if(fullscreen){
    GListModel *monitors=gdk_display_get_monitors(display);monitor=g_list_model_get_item(monitors,0);
    if(overlay && monitor)gtk_layer_set_monitor(GTK_WINDOW(m->window),monitor);
    GtkWidget *stage=gtk_overlay_new();gtk_window_set_child(GTK_WINDOW(m->window),stage);
    gtk_overlay_set_child(GTK_OVERLAY(stage),backdrop_new(monitor));
    gtk_overlay_add_overlay(GTK_OVERLAY(stage),m->outer);
    gtk_widget_set_hexpand(m->outer,TRUE);gtk_widget_set_vexpand(m->outer,TRUE);
    gtk_widget_set_opacity(stage,0);
    gtk_widget_add_tick_callback(stage,fade_in,g_new0(gint64,1),g_free);
  }else gtk_window_set_child(GTK_WINDOW(m->window),m->outer);
  m->panel=gtk_grid_new();gtk_grid_set_column_spacing(GTK_GRID(m->panel),30);gtk_widget_add_css_class(m->panel,"box-wrapper");gtk_widget_add_css_class(m->panel,"dashboard-panel");
  gtk_widget_set_halign(m->panel,GTK_ALIGN_CENTER);gtk_widget_set_valign(m->panel,GTK_ALIGN_CENTER);gtk_widget_set_vexpand(m->panel,TRUE);gtk_box_append(GTK_BOX(m->outer),m->panel);
  GtkWidget *music=gtk_box_new(GTK_ORIENTATION_VERTICAL,10),*side=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);
  int art_size=480;
  if(fullscreen && monitor){GdkRectangle geometry;gdk_monitor_get_geometry(monitor,&geometry);
    art_size=CLAMP(geometry.height-350,380,740);}
  g_clear_object(&monitor);
  if(fullscreen)art_resolution=art_size;
  gtk_widget_set_size_request(music,art_size,-1);gtk_widget_set_size_request(side,fullscreen?560:450,-1);
  if(fullscreen)gtk_grid_set_row_spacing(GTK_GRID(m->panel),12);
  gtk_grid_attach(GTK_GRID(m->panel),music,0,0,1,1);gtk_grid_attach(GTK_GRID(m->panel),side,1,0,1,1);
  d.status=label(idle_title,"dash-status");if(fullscreen)gtk_widget_add_css_class(d.status,"dash-status-card");gtk_box_append(GTK_BOX(music),d.status);
  PangoAttrList *heading_attrs=pango_attr_list_new();
  pango_attr_list_insert(heading_attrs,pango_attr_size_new_absolute(14*PANGO_SCALE));
  pango_attr_list_insert(heading_attrs,pango_attr_weight_new(PANGO_WEIGHT_SEMIBOLD));
  gtk_label_set_attributes(GTK_LABEL(d.status),heading_attrs);
  gtk_label_set_wrap(GTK_LABEL(d.status),TRUE);
  gtk_label_set_xalign(GTK_LABEL(d.status),0.5);
  gtk_label_set_justify(GTK_LABEL(d.status),GTK_JUSTIFY_CENTER);
  gtk_label_set_ellipsize(GTK_LABEL(d.status),PANGO_ELLIPSIZE_NONE);
  d.idle_quote=label(idle_title,"dash-idle-quote");
  gtk_label_set_attributes(GTK_LABEL(d.idle_quote),heading_attrs);pango_attr_list_unref(heading_attrs);
  gtk_label_set_wrap(GTK_LABEL(d.idle_quote),TRUE);
  gtk_label_set_xalign(GTK_LABEL(d.idle_quote),0.5);
  gtk_label_set_justify(GTK_LABEL(d.idle_quote),GTK_JUSTIFY_CENTER);
  gtk_label_set_ellipsize(GTK_LABEL(d.idle_quote),PANGO_ELLIPSIZE_NONE);
  gtk_widget_set_vexpand(d.idle_quote,TRUE);gtk_widget_set_valign(d.idle_quote,GTK_ALIGN_CENTER);
  GtkWidget *art=gtk_overlay_new();gtk_widget_add_css_class(art,"dash-art");gtk_widget_set_size_request(art,art_size,art_size);gtk_widget_set_overflow(art,GTK_OVERFLOW_HIDDEN);
  d.picture=gtk_picture_new();gtk_picture_set_can_shrink(GTK_PICTURE(d.picture),TRUE);gtk_picture_set_content_fit(GTK_PICTURE(d.picture),GTK_CONTENT_FIT_CONTAIN);gtk_overlay_set_child(GTK_OVERLAY(art),d.picture);
  char *idle_image=module_asset("dashboard","images/album-idle.png","dashboard-idle.png");
  if(g_file_test(idle_image,G_FILE_TEST_IS_REGULAR)) {
    d.placeholder=gtk_picture_new_for_filename(idle_image);
    gtk_picture_set_can_shrink(GTK_PICTURE(d.placeholder),TRUE);
    gtk_picture_set_content_fit(GTK_PICTURE(d.placeholder),GTK_CONTENT_FIT_COVER);
  }else{
    d.placeholder=gtk_image_new_from_icon_name("audio-x-generic-symbolic");gtk_image_set_pixel_size(GTK_IMAGE(d.placeholder),80);
  }
  g_free(idle_image);
  gtk_overlay_add_overlay(GTK_OVERLAY(art),d.placeholder);
  GtkWidget *art_card=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
  gtk_widget_add_css_class(art_card,"dash-system");gtk_widget_add_css_class(art_card,"dash-album-card");
  gtk_box_append(GTK_BOX(art_card),art);gtk_box_append(GTK_BOX(music),art_card);
  if(fullscreen){gtk_widget_set_vexpand(art_card,TRUE);gtk_widget_set_vexpand(art,TRUE);}
  d.title=label(idle_title,"dash-title");d.artist=label(idle_subtitle,NULL);d.album=label("","dash-muted");
  gtk_label_set_wrap(GTK_LABEL(d.title),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d.title),PANGO_ELLIPSIZE_END);
  PangoAttrList *artist_attrs=pango_attr_list_new();
  pango_attr_list_insert(artist_attrs,pango_attr_weight_new(PANGO_WEIGHT_BOLD));
  gtk_label_set_attributes(GTK_LABEL(d.artist),artist_attrs);pango_attr_list_unref(artist_attrs);
  GtkWidget *metadata=gtk_box_new(GTK_ORIENTATION_VERTICAL,6);d.metadata=metadata;
  gtk_widget_add_css_class(metadata,"dash-system");gtk_widget_add_css_class(metadata,"dash-metadata");
  gtk_box_append(GTK_BOX(metadata),d.artist);gtk_box_append(GTK_BOX(metadata),d.album);gtk_box_append(GTK_BOX(metadata),d.title);
  gtk_box_append(GTK_BOX(metadata),d.idle_quote);
  gtk_widget_set_size_request(metadata,-1,fullscreen?116:76);
  gtk_box_append(GTK_BOX(music),metadata);
  d.visualizer_accent=gtk_label_new("");gtk_widget_add_css_class(d.visualizer_accent,"dash-visualizer-high");
  gtk_widget_set_visible(d.visualizer_accent,FALSE);gtk_box_append(GTK_BOX(music),d.visualizer_accent);
  d.visualizer=gtk_drawing_area_new();gtk_widget_add_css_class(d.visualizer,"dash-visualizer");
  gtk_widget_set_size_request(d.visualizer,-1,58);
  gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(d.visualizer),cava_draw,&d,NULL);
  gtk_widget_set_size_request(d.visualizer,-1,fullscreen?72:58);
  gtk_grid_attach(GTK_GRID(m->panel),d.visualizer,0,1,2,1);
  gtk_grid_set_row_spacing(GTK_GRID(m->panel),12);
  GtkWidget *time_card=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,14);gtk_widget_add_css_class(time_card,"dash-system");gtk_widget_add_css_class(time_card,"dash-time");
  d.clock=label("","dash-clock");d.date=label("","dash-muted");gtk_box_append(GTK_BOX(time_card),d.clock);gtk_box_append(GTK_BOX(time_card),d.date);gtk_box_append(GTK_BOX(side),time_card);
  PangoAttrList *clock_attrs=pango_attr_list_new();
  pango_attr_list_insert(clock_attrs,pango_attr_weight_new(PANGO_WEIGHT_BOLD));
  pango_attr_list_insert(clock_attrs,pango_attr_scale_new(1.5));
  gtk_label_set_attributes(GTK_LABEL(d.clock),clock_attrs);pango_attr_list_unref(clock_attrs);
  gtk_widget_set_valign(d.date,GTK_ALIGN_CENTER);
  gtk_label_set_wrap(GTK_LABEL(d.date),FALSE);
  GtkWidget *calendar_row=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,16);
  GtkWidget *calendar=gtk_calendar_new();d.calendar=calendar;gtk_widget_add_css_class(calendar,"dash-calendar");gtk_widget_set_hexpand(calendar,TRUE);
  gtk_box_append(GTK_BOX(calendar_row),calendar);
  char *monk_path=module_asset("dashboard","images/monk.png","dashboard.png");
  {
    GtkWidget *monk=gtk_picture_new();d.daylight_art.picture=GTK_PICTURE(monk);
    GdkPixbuf *pix=gdk_pixbuf_new_from_file_at_scale(monk_path,fullscreen?210:180,fullscreen?290:250,TRUE,NULL);
    if(pix) {
      GBytes *bytes=gdk_pixbuf_read_pixel_bytes(pix);
      GdkTexture *texture=GDK_TEXTURE(gdk_memory_texture_new(gdk_pixbuf_get_width(pix),gdk_pixbuf_get_height(pix),
        gdk_pixbuf_get_has_alpha(pix)?GDK_MEMORY_R8G8B8A8:GDK_MEMORY_R8G8B8,bytes,gdk_pixbuf_get_rowstride(pix)));
      gtk_picture_set_paintable(GTK_PICTURE(monk),GDK_PAINTABLE(texture));
      g_object_unref(texture);g_bytes_unref(bytes);g_object_unref(pix);
    }
    simple_daylight_art_update(&d.daylight_art);
    gtk_picture_set_can_shrink(GTK_PICTURE(monk),TRUE);
    gtk_picture_set_content_fit(GTK_PICTURE(monk),GTK_CONTENT_FIT_COVER);
    gtk_widget_set_size_request(monk,fullscreen?210:180,-1);gtk_widget_set_valign(monk,GTK_ALIGN_FILL);
    gtk_widget_add_css_class(monk,"dash-monk");gtk_widget_set_overflow(monk,GTK_OVERFLOW_HIDDEN);
    gtk_box_append(GTK_BOX(calendar_row),monk);
  }
  g_free(monk_path);gtk_box_append(GTK_BOX(side),calendar_row);
  gtk_box_append(GTK_BOX(side),simple_calendar_details(GTK_CALENDAR(calendar)));
  if(!fullscreen)simple_calendar_navigation(GTK_CALENDAR(calendar),"simplepicker","dashboard");
  GtkWidget *network_panel=gtk_box_new(GTK_ORIENTATION_VERTICAL,8);
  gtk_widget_add_css_class(network_panel,"dash-system");gtk_widget_add_css_class(network_panel,"dash-network");
  gtk_box_append(GTK_BOX(network_panel),label("NETWORK & PHONE","dash-key"));
  d.network=label("Checking connection…","dash-info");gtk_box_append(GTK_BOX(network_panel),d.network);
  d.phone=label("Phone · checking…","dash-info");gtk_box_append(GTK_BOX(network_panel),d.phone);
  gtk_label_set_wrap(GTK_LABEL(d.network),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d.network),PANGO_ELLIPSIZE_END);
  gtk_label_set_wrap(GTK_LABEL(d.phone),FALSE);gtk_label_set_ellipsize(GTK_LABEL(d.phone),PANGO_ELLIPSIZE_END);
  gtk_box_append(GTK_BOX(side),network_panel);
  GtkWidget *grid=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(grid),8);gtk_grid_set_column_spacing(GTK_GRID(grid),18);
  gtk_widget_add_css_class(grid,"dash-system");
  char *os=g_get_os_info(G_OS_INFO_KEY_NAME);struct utsname uts;uname(&uts);
  char *system=g_strdup_printf("%s (%s) — %s",os?os:"Linux",g_get_host_name(),uts.release);
  GtkWidget *system_label=info_row(grid,0,"SYSTEM",system);
  gtk_label_set_wrap(GTK_LABEL(system_label),TRUE);gtk_label_set_ellipsize(GTK_LABEL(system_label),PANGO_ELLIPSIZE_NONE);
  gtk_widget_set_tooltip_text(system_label,system);g_free(system);g_free(os);
  d.init=info_row(grid,1,"INIT SYSTEM","Checking…");
  d.desktop=info_row(grid,2,"DESKTOP","Checking…");
  d.uptime=info_row(grid,3,"UPTIME","");
  d.terminal=info_row(grid,4,"TERM","Checking…");
  char *cpuinfo=NULL,*cpu=NULL;
  if(g_file_get_contents("/proc/cpuinfo",&cpuinfo,NULL,NULL)) {
    char **lines=g_strsplit(cpuinfo,"\n",-1);
    for(int i=0;lines[i] && !cpu;i++)if(g_str_has_prefix(lines[i],"model name")) {
      char *colon=strchr(lines[i],':');if(colon)cpu=g_strdup(g_strstrip(colon+1));
    }
    g_strfreev(lines);g_free(cpuinfo);
  }
  info_row(grid,5,"CPU",cpu?cpu:"Unknown");g_free(cpu);
  d.memory=info_row(grid,6,"MEM","");
  d.disk=info_row(grid,7,"HOME DISK","");d.battery=info_row(grid,8,"POWER","");
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
    clock_tick(&d);

    int side_height=0,status_height=0;
    gtk_widget_measure(side,GTK_ORIENTATION_VERTICAL,560,NULL,&side_height,NULL,NULL);
    gtk_widget_measure(d.status,GTK_ORIENTATION_VERTICAL,-1,NULL,&status_height,NULL,NULL);
    art_size=MAX(art_size,side_height-status_height-10-24);
    gtk_widget_set_size_request(art,art_size,art_size);
    gtk_widget_set_size_request(music,art_size+24,-1);
    art_resolution=art_size;
  }
  GtkWidget *headline=label(idle_subtitle,"dash-headline");
  PangoAttrList *headline_attrs=pango_attr_list_copy(gtk_label_get_attributes(GTK_LABEL(d.status)));
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
  d.layout=(SimpleMusicLayout){.grid=m->panel,.music=music,.side=side,.art=art,
    .art_card=art_card,.metadata=metadata,.visualizer=d.visualizer,.status=d.status,
    .headline=headline_card,.fullscreen=fullscreen,.idle_size=art_size,.metadata_columns=2};
  GtkWidget *hint=label(fullscreen?"Move the mouse or press a key to return":"Esc · close","dash-status");
  if(fullscreen){gtk_widget_set_halign(hint,GTK_ALIGN_END);gtk_grid_attach(GTK_GRID(m->panel),hint,0,2,2,1);}
  else {
    gtk_widget_set_halign(hint,GTK_ALIGN_END);
    gtk_widget_set_margin_top(hint,8);
    gtk_grid_attach(GTK_GRID(m->panel),hint,0,2,2,1);
  }
  GtkEventController *keys=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(keys,GTK_PHASE_CAPTURE);g_signal_connect(keys,"key-pressed",G_CALLBACK(key),&d);gtk_widget_add_controller(m->window,keys);
  if(fullscreen){GtkEventController *moves=gtk_event_controller_motion_new();
    g_signal_connect(moves,"enter",G_CALLBACK(pointer_enter),&d);g_signal_connect(moves,"motion",G_CALLBACK(motion),&d);gtk_widget_add_controller(m->window,moves);}
  GtkGesture *gesture=gtk_gesture_click_new();if(fullscreen)gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(gesture),GTK_PHASE_CAPTURE);g_signal_connect(gesture,"pressed",G_CALLBACK(outside),&d);gtk_widget_add_controller(m->outer,GTK_EVENT_CONTROLLER(gesture));
  g_signal_connect(m->window,"close-request",G_CALLBACK(closed),&d);
  guint watch=g_unix_fd_add(fd,G_IO_IN,receive,&d),timer=g_timeout_add_seconds(2,refresh,&d),clock_timer=g_timeout_add_seconds(10,clock_tick,&d);
  clock_tick(&d);refresh(&d);cava_start(&d);d.opened=g_get_monotonic_time();
  dashboard_fit(&d);
  gtk_window_present(GTK_WINDOW(m->window));
  if(!fullscreen && d.calendar)gtk_widget_grab_focus(d.calendar);
  guint bench=sp_benchmark?g_timeout_add(500,bench_close,&d):0;
  GSubprocess *idle_audio=sp_benchmark?NULL:simple_idle_audio_start("dashboard");
  g_main_loop_run(m->loop);
  simple_idle_audio_stop(&idle_audio);
  cava_stop(&d);
  g_source_remove(watch);g_source_remove(timer);g_source_remove(clock_timer);
  if(bench && g_main_context_find_source_by_id(NULL,bench))g_source_remove(bench);
  g_cancellable_cancel(d.cancel);while(d.busy)g_main_context_iteration(NULL,TRUE);
  simple_daylight_art_clear(&d.daylight_art);
  close(fd);g_object_unref(d.cancel);g_free(d.art);
  gtk_style_context_remove_provider_for_display(display,GTK_STYLE_PROVIDER(base));gtk_style_context_remove_provider_for_display(display,GTK_STYLE_PROVIDER(css));gtk_style_context_remove_provider_for_display(display,GTK_STYLE_PROVIDER(custom));
  g_object_unref(base);g_object_unref(css);g_object_unref(custom);g_main_loop_unref(m->loop);menu_free(m);return 0;
}
