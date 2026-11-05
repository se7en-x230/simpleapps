#define _GNU_SOURCE
#include "../simple-common/simple-paths.h"
#include "simple-theme.h"
#include <gtk/gtk.h>
#include "media.h"
#include "dashboard-settings.h"
#include "phone-charge.h"
#include "phone-charge-cache.h"
#include <gtk4-layer-shell.h>
#include <gio/gunixsocketaddress.h>
#include <glib-unix.h>
#include <json-c/json.h>
#include <pulse/pulseaudio.h>
#include <pulse/glib-mainloop.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <sys/stat.h>
typedef struct  {
    GSocketConnection *connection;
    GDataInputStream *input;
    const char *command;
    gboolean pending;
}
Feed;
static GtkApplication *app;
static GtkWidget *window,*tags,*title_label,*media_label,*music,*clock_label,*net_label,*volume_label,*invest_label,*battery_label,*phone_label,*visualizer,*osd_window,*osd_label,*osd_revealer,*osd_meter,*osd_icon;
static GDBusConnection *bus;
static GCancellable *cancel;
static GKeyFile *config;
static char *config_path;
static GTimeZone *panel_timezone;
static char *monitor_name,*clock_format,*interface_name,*selected_player,*sink_name,*cava_path;
static gboolean preview,preview_layer,demo,stopping,media_busy,phone_busy,invest_busy,enable_cava=TRUE,enable_invest=TRUE,enable_phone=TRUE,enable_osd;
static int duration,height=32,volume=-1,edge_margin=10,top_margin=6;
static double background_opacity=.55;
static gboolean muted;
static guint osd_timer,invest_timeout;
static GSubprocess *cava_process,*invest_process;
static GDataInputStream *cava_input;
static PhoneChargeEstimate phone_estimate;
static char *phone_device;
static double bars[9];
static pa_glib_mainloop *pulse_loop;
static pa_context *pulse;
static Feed feeds[2]= {
    {
        .command="watch all-tags\n"
    }, {
        .command="watch focusing-client\n"
    }
};

static void set_text(GtkWidget *w,const char *s) {
    if(!w)return;
    char *valid=g_utf8_make_valid(s?s:"",-1);
    if(g_strcmp0(gtk_label_get_text(GTK_LABEL(w)),valid)) {
        gtk_label_set_text(GTK_LABEL(w),valid);
        gtk_widget_set_tooltip_text(w,valid);
    }
    g_free(valid);
}
static char *setting(const char *key,const char *fallback) {
    char *s=g_key_file_get_string(config,"panel",key,NULL);
    return s?s:g_strdup(fallback);
}
static gboolean flag(const char *key,gboolean fallback) {
    GError *e=NULL;
    gboolean b=g_key_file_get_boolean(config,"panel",key,&e);
    if(e) {
        g_clear_error(&e);
        return fallback;
    }
    return b;
}
static json_object *field(json_object *o,const char *name) {
    json_object *v=NULL;
    if(o)json_object_object_get_ex(o,name,&v);
    return v;
}
static const char *strfield(json_object *o,const char *name) {
    json_object *v=field(o,name);
    return v?json_object_get_string(v):"";
}
static gboolean stop_app(gpointer unused) {
    stopping=TRUE;
    simple_market_stop();
    g_cancellable_cancel(cancel);
    if(cava_process)g_subprocess_force_exit(cava_process);
    if(invest_process)g_subprocess_force_exit(invest_process);
    g_application_quit(G_APPLICATION(app));
    return G_SOURCE_REMOVE;
}
static char *socket_path(void) {
    const char *s=g_getenv("MANGO_INSTANCE_SIGNATURE");
    if(s&&g_file_test(s,G_FILE_TEST_EXISTS))return g_strdup(s);
    const char *dir=g_get_user_runtime_dir();
    GDir *d=g_dir_open(dir,0,NULL);
    char *found=NULL;
    const char *name;
    int count=0;
    if(d) {
        while((name=g_dir_read_name(d))) {
            if(g_str_has_prefix(name,"mango-")&&g_str_has_suffix(name,".sock")) {
                g_free(found);
                found=g_build_filename(dir,name,NULL);
                count++;
            }
        }
        g_dir_close(d);
    }
    if(count!=1)g_clear_pointer(&found,g_free);
    return found;
}
static void tag_enter(GtkEventControllerMotion *motion,double x,double y,gpointer data) {
    gtk_widget_add_css_class(GTK_WIDGET(data),"hovered");
}
static void tag_leave(GtkEventControllerMotion *motion,gpointer data) {
    gtk_widget_remove_css_class(GTK_WIDGET(data),"hovered");
}
typedef struct {
    char *command;
    GSocketConnection *connection;
} ClickCommand;
static void command_reply(GObject *source,GAsyncResult *result,gpointer data) {
    ClickCommand *request=data;
    GError *error=NULL;
    GBytes *reply=g_input_stream_read_bytes_finish(G_INPUT_STREAM(source),result,&error);
    if(!reply) {
        g_warning("Tag switch response failed: %s",error->message);
        g_clear_error(&error);
    } else g_bytes_unref(reply);
    g_object_unref(request->connection);
    g_free(request->command);
    g_free(request);
}
static void command_done(GObject *source,GAsyncResult *result,gpointer data) {
    ClickCommand *request=data;
    GError *error=NULL;
    if(!g_output_stream_write_all_finish(G_OUTPUT_STREAM(source),result,NULL,&error)) {
        g_warning("Tag switch failed: %s",error->message);
        g_clear_error(&error);
    } else {
        g_input_stream_read_bytes_async(g_io_stream_get_input_stream(G_IO_STREAM(request->connection)),
            1024,G_PRIORITY_DEFAULT,cancel,command_reply,request);
        return;
    }
    g_object_unref(request->connection);
    g_free(request->command);
    g_free(request);
}
static void command_connected(GObject *source,GAsyncResult *result,gpointer data) {
    ClickCommand *request=data;
    GError *error=NULL;
    request->connection=g_socket_client_connect_finish(G_SOCKET_CLIENT(source),result,&error);
    if(!request->connection) {
        g_warning("Tag switch failed: %s",error->message);
        g_clear_error(&error);
        g_free(request->command);
        g_free(request);
        return;
    }
    g_output_stream_write_all_async(g_io_stream_get_output_stream(G_IO_STREAM(request->connection)),
        request->command,strlen(request->command),G_PRIORITY_DEFAULT,cancel,command_done,request);
}
static void tag_clicked(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    GtkWidget *tag=GTK_WIDGET(data);
    if(demo||gtk_widget_has_css_class(tag,"active"))return;
    char *path=socket_path();
    if(!path)return;
    int index=GPOINTER_TO_INT(g_object_get_data(G_OBJECT(tag),"tag-index"));
    ClickCommand *request=g_new0(ClickCommand,1);
    request->command=g_strdup_printf("dispatch viewcrossmon,%d,%s\n",index,monitor_name);
    GSocketClient *client=g_socket_client_new();
    g_socket_client_set_timeout(client,2);
    GSocketAddress *address=g_unix_socket_address_new(path);
    g_socket_client_connect_async(client,G_SOCKET_CONNECTABLE(address),cancel,command_connected,request);
    g_object_unref(address);
    g_object_unref(client);
    g_free(path);
}
static void system_clicked(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    if(demo)return;
    char *binary=g_file_read_link("/proc/self/exe",NULL);
    if(!binary)return;
    /* Atomic upgrades unlink the running executable. /proc keeps its old
     * pathname with this suffix; launch the replacement at the original path. */
    if(g_str_has_suffix(binary," (deleted)"))
        binary[strlen(binary)-strlen(" (deleted)")]='\0';
    char *argv[]={binary,"--system-dashboard","--config",config_path,NULL};
    GError *error=NULL;
    if(!g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("System dashboard failed: %s",error->message);g_clear_error(&error);
    }
    g_free(binary);
}
static void adjust_volume(const char *action) {
    if(demo)return;
    char *up[]={"wpctl","set-volume","-l","1.0","@DEFAULT_AUDIO_SINK@","5%+",NULL};
    char *down[]={"wpctl","set-volume","@DEFAULT_AUDIO_SINK@","5%-",NULL};
    char *mute[]={"wpctl","set-mute","@DEFAULT_AUDIO_SINK@","toggle",NULL};
    char **args=!strcmp(action,"up")?up:!strcmp(action,"down")?down:mute;
    GError *error=NULL;
    if(!g_spawn_async(NULL,args,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("Volume control failed: %s",error->message);g_clear_error(&error);
    }
}
static gboolean volume_scroll(GtkEventControllerScroll *controller,double dx,double dy,gpointer data) {
    if(dy)adjust_volume(dy<0?"up":"down");
    return TRUE;
}
static void volume_middle(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    gtk_gesture_set_state(GTK_GESTURE(gesture),GTK_EVENT_SEQUENCE_CLAIMED);
    adjust_volume("mute");
}
static void volume_open(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    gtk_gesture_set_state(GTK_GESTURE(gesture),GTK_EVENT_SEQUENCE_CLAIMED);
    if(demo)return;
    gboolean bluetooth=GPOINTER_TO_INT(data);
    char *helper=simple_control(bluetooth?"simple-network":"simple-sound",bluetooth?"simplepicker/network/scripts/simple-network":"simplepicker/sound/scripts/simple-sound");
    char *argv[]={helper,bluetooth?"bt":NULL,NULL};
    GError *error=NULL;
    if(!g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("Audio controls failed: %s",error->message);g_clear_error(&error);
    }
    g_free(helper);
}
static void music_clicked(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    if(demo)return;
    char *argv[]={"simplepicker","--dashboard",NULL};
    GError *error=NULL;
    if(!g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("Dashboard failed: %s",error->message);
        g_clear_error(&error);
    }
}
static void calendar_clicked(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    gtk_gesture_set_state(GTK_GESTURE(gesture),GTK_EVENT_SEQUENCE_CLAIMED);
    if(demo)return;
    char *command=setting("calendar_command","simple-calendar");
    char **argv=NULL;GError *error=NULL;
    if(!g_shell_parse_argv(command,NULL,&argv,&error)){g_warning("Calendar command: %s",error->message);g_clear_error(&error);g_free(command);return;}
    g_free(command);
    if(!g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("SimpleCalendar failed: %s",error->message);g_clear_error(&error);
    }
    g_strfreev(argv);
}
static void clickable(GtkWidget *widget,GCallback callback) {
    GtkGesture *click=gtk_gesture_click_new();
    gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(click),GDK_BUTTON_PRIMARY);
    g_signal_connect(click,"released",callback,widget);
    gtk_widget_add_controller(widget,GTK_EVENT_CONTROLLER(click));
    gtk_widget_set_cursor_from_name(widget,"pointer");
}
static void update_tags(json_object *root) {
    json_object *all=field(root,"all_tags");
    if(!all||!json_object_is_type(all,json_type_array))return;
    json_object *chosen=NULL;
    for(size_t i=0;i<json_object_array_length(all);i++) {
        json_object *m=json_object_array_get_idx(all,i);
        if(!strcmp(strfield(m,"monitor"),monitor_name)) {
            chosen=m;
            break;
        }
    }
    if(!chosen)return;
    json_object *list=field(chosen,"tags");
    if(!list)return;
    /* Keep the widgets alive across IPC updates so pointer hover is stable. */
    GList *remaining=NULL;
    for(GtkWidget *child=gtk_widget_get_first_child(tags);child;child=gtk_widget_get_next_sibling(child))
        remaining=g_list_prepend(remaining,child);
    GtkWidget *previous=NULL;
    for(size_t i=0;i<json_object_array_length(list);i++) {
        json_object *t=json_object_array_get_idx(list,i);
        int index=json_object_get_int(field(t,"index"));
        gboolean active=json_object_get_boolean(field(t,"is_active")),urgent=json_object_get_boolean(field(t,"is_urgent"));
        if(!active&&!urgent&&!json_object_get_int(field(t,"client_count")))continue;
        char s[16];
        g_snprintf(s,sizeof s,"%d",index);
        GtkWidget *b=NULL;
        for(GList *item=remaining;item;item=item->next) {
            if(GPOINTER_TO_INT(g_object_get_data(G_OBJECT(item->data),"tag-index"))==index) {
                b=item->data;
                break;
            }
        }
        if(b)remaining=g_list_remove(remaining,b);
        else {
            b=gtk_label_new(s);
            gtk_widget_set_valign(b,GTK_ALIGN_CENTER);
            gtk_label_set_single_line_mode(GTK_LABEL(b),TRUE);
            g_object_set_data(G_OBJECT(b),"tag-index",GINT_TO_POINTER(index));
            gtk_widget_add_css_class(b,"tag");
            clickable(b,G_CALLBACK(tag_clicked));
            GtkEventController *motion=gtk_event_controller_motion_new();
            g_signal_connect(motion,"enter",G_CALLBACK(tag_enter),b);
            g_signal_connect(motion,"leave",G_CALLBACK(tag_leave),b);
            gtk_widget_add_controller(b,motion);
            gtk_box_append(GTK_BOX(tags),b);
        }
        if(active)gtk_widget_add_css_class(b,"active");
        else gtk_widget_remove_css_class(b,"active");
        if(urgent)gtk_widget_add_css_class(b,"urgent");
        else gtk_widget_remove_css_class(b,"urgent");
        if(gtk_widget_get_prev_sibling(b)!=previous)
            gtk_box_reorder_child_after(GTK_BOX(tags),b,previous);
        previous=b;
    }
    for(GList *item=remaining;item;item=item->next)gtk_box_remove(GTK_BOX(tags),item->data);
    g_list_free(remaining);
}
static void update_title(json_object *root) {
    const char *t=strfield(root,"title"),*a=strfield(root,"appid");
    char *s=g_strdup_printf("%s%s%s",a&&*a?a:"",a&&*a&&t&&*t?" · ":"",t?t:"");
    set_text(title_label,s);
    g_free(s);
}
static void feed_read(Feed *f);
static void feed_line(GObject *source,GAsyncResult *result,gpointer data) {
    Feed *f=data;
    GError *e=NULL;
    gsize len;
    char *line=g_data_input_stream_read_line_finish(G_DATA_INPUT_STREAM(source),result,&len,&e);
    if(line) {
        if(len<1024*1024) {
            json_object *o=json_tokener_parse(line);
            if(o) {
                if(f==&feeds[0])update_tags(o);
                else update_title(o);
                json_object_put(o);
            }
        }
        g_free(line);
        if(!stopping)feed_read(f);
    }
    else {
        g_clear_object(&f->input);
        g_clear_object(&f->connection);
        if(f==&feeds[1])set_text(title_label,"Mango disconnected");
    }
    g_clear_error(&e);
}
static void feed_read(Feed *f) {
    g_data_input_stream_read_line_async(f->input,G_PRIORITY_DEFAULT,cancel,feed_line,f);
}
static void feed_connected(GObject *source,GAsyncResult *result,gpointer data) {
    Feed *f=data;
    GError *e=NULL;
    f->pending=FALSE;
    f->connection=g_socket_client_connect_finish(G_SOCKET_CLIENT(source),result,&e);
    if(f->connection) {
        g_socket_set_timeout(g_socket_connection_get_socket(f->connection),0);
        if(g_output_stream_write_all(g_io_stream_get_output_stream(G_IO_STREAM(f->connection)),f->command,strlen(f->command),NULL,cancel,&e)) {
            f->input=g_data_input_stream_new(g_io_stream_get_input_stream(G_IO_STREAM(f->connection)));
            feed_read(f);
        }
        else g_clear_object(&f->connection);
    }
    g_clear_error(&e);
}
static gboolean connect_feeds(gpointer unused) {
    if(stopping)return G_SOURCE_REMOVE;
    char *path=socket_path();
    if(!path)return G_SOURCE_CONTINUE;
    for(int i=0;i<2;i++) {
        Feed *f=&feeds[i];
        if(f->connection||f->pending)continue;
        f->pending=TRUE;
        GSocketClient *c=g_socket_client_new();
        g_socket_client_set_timeout(c,2);
        GSocketAddress *addr=g_unix_socket_address_new(path);
        g_socket_client_connect_async(c,G_SOCKET_CONNECTABLE(addr),cancel,feed_connected,f);
        g_object_unref(addr);
        g_object_unref(c);
    }
    g_free(path);
    return G_SOURCE_CONTINUE;
}
static guint64 read_counter(const char *iface,const char *name) {
    char *path=g_strdup_printf("/sys/class/net/%s/statistics/%s",iface,name),*s=NULL;
    guint64 v=0;
    if(g_file_get_contents(path,&s,NULL,NULL))v=g_ascii_strtoull(s,NULL,10);
    g_free(s);
    g_free(path);
    return v;
}
static char *default_interface(void) {
    if(interface_name&&*interface_name)return g_strdup(interface_name);
    FILE *f=fopen("/proc/net/route","r");
    if(!f)return NULL;
    char line[512],name[64],dest[32];
    unsigned flags,metric,best=UINT_MAX;
    char *chosen=NULL;
    while(fgets(line,sizeof line,f)) {
        if(sscanf(line,"%63s %31s %*s %x %*u %*u %u",name,dest,&flags,&metric)==4&&!strcmp(dest,"00000000")&&(flags&1)&&metric<best) {
            g_free(chosen);
            chosen=g_strdup(name);
            best=metric;
        }
    }
    fclose(f);
    return chosen;
}
static void rate_text(double bytes,char *out,size_t size) {
    const char *unit="B/s";
    if(bytes>=1024) {
        bytes/=1024;
        unit="KiB/s";
    }
    if(bytes>=1024) {
        bytes/=1024;
        unit="MiB/s";
    }
    g_snprintf(out,size,"%.1f %s",bytes,unit);
}
static gboolean tick(gpointer unused) {
    GDateTime *now=g_date_time_new_now(panel_timezone);
    char *text=g_date_time_format(now,clock_format);
    set_text(clock_label,text);
    g_free(text);
    g_date_time_unref(now);
    if(demo)return G_SOURCE_CONTINUE;
    if(enable_invest&&!g_getenv("SIMPLEPANEL_INVEST_COMMAND")) {
        simple_market_refresh();json_object *prices=simple_market_read();GString *summary=g_string_new(NULL);
        for(gsize i=0;i<dashboard_settings.markets;i++){char *price=simple_market_number(prices,i);g_string_append_printf(summary,"%s%s",i?" ":"",price);g_free(price);}
        set_text(invest_label,summary->str);g_string_free(summary,TRUE);if(prices)json_object_put(prices);
    }
    static char *last_iface;
    static guint64 rx,tx;
    static gint64 last;
    char *iface=default_interface();
    gint64 time=g_get_monotonic_time();
    if(iface) {
        guint64 nr=read_counter(iface,"rx_bytes"),nt=read_counter(iface,"tx_bytes");
        char r[32]="—",t[32]="—";
        if(last&&g_strcmp0(iface,last_iface)==0&&nr>=rx&&nt>=tx) {
            double seconds=(time-last)/1000000.;
            rate_text((nr-rx)/seconds,r,sizeof r);
            rate_text((nt-tx)/seconds,t,sizeof t);
        }
        text=g_strdup_printf("↓ %s  ↑ %s",r,t);
        set_text(net_label,text);
        gtk_widget_set_tooltip_text(net_label,iface);
        g_free(text);
        rx=nr;
        tx=nt;
        last=time;
        g_free(last_iface);
        last_iface=g_strdup(iface);
    }
    else {
        set_text(net_label,"Network offline");
        last=0;
    }
    g_free(iface);
    return G_SOURCE_CONTINUE;
}
static unsigned media_pending;
static int media_score;
static char *media_best,*media_player;
static void media_result(GObject *source,GAsyncResult *result,gpointer data) {
    char *name=data;
    GError *e=NULL;
    GVariant *reply=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
    if(reply) {
        GVariant *dict=g_variant_get_child_value(reply,0),*metadata=g_variant_lookup_value(dict,"Metadata",G_VARIANT_TYPE_VARDICT);
        const char *status="Stopped",*title="";
        g_variant_lookup(dict,"PlaybackStatus","&s",&status);
        char *artists=NULL;
        if(metadata) {
            g_variant_lookup(metadata,"xesam:title","&s",&title);
            GVariant *v=g_variant_lookup_value(metadata,"xesam:artist",G_VARIANT_TYPE_STRING_ARRAY);
            if(v) {
                gchar **a=g_variant_dup_strv(v,NULL);
                artists=g_strjoinv(", ",a);
                g_strfreev(a);
                g_variant_unref(v);
            }
        }
        int score=!strcmp(status,"Playing")?3:!strcmp(status,"Paused")?2:0;
        if(*title&&score>media_score) {
            media_score=score;
            g_free(media_best);
            char *line=simple_media_line(metadata);
            media_best=g_strdup_printf("%s %s",score==3?"▶":"Ⅱ",line);g_free(line);
            g_free(media_player);
            media_player=g_strdup(name);
        }
        g_free(artists);
        if(metadata)g_variant_unref(metadata);
        g_variant_unref(dict);
        g_variant_unref(reply);
    }
    g_clear_error(&e);
    g_free(name);
    if(--media_pending==0) {
        set_text(media_label,media_best?media_best:"");
        gtk_widget_set_visible(music,media_score==3);
        g_free(selected_player);
        selected_player=g_strdup(media_player);
        media_busy=FALSE;
    }
}
static void media_names(GObject *source,GAsyncResult *result,gpointer data) {
    GError *e=NULL;
    GVariant *reply=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
    g_clear_pointer(&media_best,g_free);
    g_clear_pointer(&media_player,g_free);
    media_score=0;
    media_pending=0;
    if(reply) {
        gchar **names;
        g_variant_get(reply,"(^as)",&names);
        for(int i=0;names[i];i++)if(g_str_has_prefix(names[i],"org.mpris.MediaPlayer2.")) {
            media_pending++;
            g_dbus_connection_call(bus,names[i],"/org/mpris/MediaPlayer2","org.freedesktop.DBus.Properties","GetAll",g_variant_new("(s)","org.mpris.MediaPlayer2.Player"),G_VARIANT_TYPE("(a{sv})"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1500,cancel,media_result,g_strdup(names[i]));
        }
        g_strfreev(names);
        g_variant_unref(reply);
    }
    g_clear_error(&e);
    if(!media_pending) {
        media_busy=FALSE;
        set_text(media_label,"");
        gtk_widget_set_visible(music,FALSE);
        g_clear_pointer(&selected_player,g_free);
    }
}
static gboolean media_update(gpointer unused) {
    if(bus&&!media_busy&&!stopping) {
        media_busy=TRUE;
        g_dbus_connection_call(bus,"org.freedesktop.DBus","/org/freedesktop/DBus","org.freedesktop.DBus","ListNames",NULL,G_VARIANT_TYPE("(as)"),G_DBUS_CALL_FLAGS_NONE,1500,cancel,media_names,NULL);
    }
    return G_SOURCE_CONTINUE;
}
static void media_signal(GDBusConnection *c,const char *sender,const char *path,const char *iface,const char *signal,GVariant *params,gpointer data) {
    GVariant *changed=g_variant_get_child_value(params,1);
    GVariant *metadata=g_variant_lookup_value(changed,"Metadata",NULL),*status=g_variant_lookup_value(changed,"PlaybackStatus",NULL);
    if(metadata||status)media_update(NULL);
    if(metadata)g_variant_unref(metadata);
    if(status)g_variant_unref(status);
    g_variant_unref(changed);
}
/* Re-scan so removable batteries appear/disappear without a panel restart. */
static char *power_value(const char *base,const char *key) {
    char *path=g_build_filename(base,key,NULL),*value=NULL;
    g_file_get_contents(path,&value,NULL,NULL);
    g_free(path);
    if(value)g_strstrip(value);
    return value;
}
static gboolean battery_update(gpointer unused) {
    GDir *dir=g_dir_open("/sys/class/power_supply",0,NULL);
    GString *text=g_string_new(NULL),*details=g_string_new(NULL);
    const char *name;
    while(dir&&(name=g_dir_read_name(dir))) {
        char *base=g_build_filename("/sys/class/power_supply",name,NULL);
        char *type=power_value(base,"type"),*scope=power_value(base,"scope"),*present=power_value(base,"present");
        if(!g_strcmp0(type,"Battery")&&g_strcmp0(scope,"Device")&&g_strcmp0(present,"0")) {
            char *capacity=power_value(base,"capacity"),*status=power_value(base,"status"),*end=NULL;
            long percent=capacity?strtol(capacity,&end,10):-1;
            if(capacity&&end!=capacity&&!*end&&percent>=0&&percent<=100) {
                const char *state=!g_strcmp0(status,"Charging")?" ⚡":"";
                g_string_append_printf(text,"%sBat %ld%%%s",text->len?" · ":"",percent,state);
                g_string_append_printf(details,"%s%s: %ld%% · %s",details->len?"\n":"",name,percent,status?status:"Unknown");
            }
            g_free(capacity);g_free(status);
        }
        g_free(base);g_free(type);g_free(scope);g_free(present);
    }
    if(dir)g_dir_close(dir);
    set_text(battery_label,text->str);
    gtk_widget_set_tooltip_text(battery_label,details->str);
    gtk_widget_set_visible(battery_label,text->len>0);
    g_string_free(text,TRUE);g_string_free(details,TRUE);
    return G_SOURCE_CONTINUE;
}
static void phone_battery(GObject *source,GAsyncResult *result,gpointer data) {
    GError *e=NULL;
    GVariant *r=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
    if(r) {
        GVariant *d=g_variant_get_child_value(r,0);
        gint32 charge=-1;
        gboolean charging=FALSE;
        g_variant_lookup(d,"charge","i",&charge);
        g_variant_lookup(d,"isCharging","b",&charging);
        if(charge>=0&&charge<=100) {
            PhoneChargeSpeed speed=phone_charge_sample(&phone_estimate,charge,charging,
                                                       g_get_monotonic_time()/1000000.0);
            phone_charge_publish(&phone_estimate,phone_device,charge,charging);
            char *s=phone_charge_label(charge,speed);
            set_text(phone_label,s);
            g_free(s);
            char *tip=phone_charge_tooltip(charge,charging,&phone_estimate);
            gtk_widget_set_tooltip_text(phone_label,tip);
            g_free(tip);
        }
        else {
            phone_charge_reset(&phone_estimate);
        phone_charge_publish(&phone_estimate,phone_device,-1,FALSE);
            set_text(phone_label,"Phone —");
        }
        g_variant_unref(d);
        g_variant_unref(r);
    }
    else {
        phone_charge_reset(&phone_estimate);
        phone_charge_publish(&phone_estimate,phone_device,-1,FALSE);
        set_text(phone_label,"Phone unavailable");
    }
    phone_busy=FALSE;
    g_clear_error(&e);
}
static void phone_devices(GObject *source,GAsyncResult *result,gpointer data) {
    GError *e=NULL;
    GVariant *r=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
    gboolean requested=FALSE;
    if(r) {
        gchar **devices;
        g_variant_get(r,"(^as)",&devices);
        if(devices[0]) {
            if(g_strcmp0(phone_device,devices[0])) {
                phone_charge_reset(&phone_estimate);
        phone_charge_publish(&phone_estimate,phone_device,-1,FALSE);
                g_free(phone_device);
                phone_device=g_strdup(devices[0]);
            }
            char *path=g_strdup_printf("/modules/kdeconnect/devices/%s/battery",devices[0]);
            g_dbus_connection_call(bus,"org.kde.kdeconnect",path,"org.freedesktop.DBus.Properties","GetAll",g_variant_new("(s)","org.kde.kdeconnect.device.battery"),G_VARIANT_TYPE("(a{sv})"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1500,cancel,phone_battery,NULL);
            g_free(path);
            requested=TRUE;
        }
        g_strfreev(devices);
        g_variant_unref(r);
    }
    g_clear_error(&e);
    if(!requested) {
        phone_charge_reset(&phone_estimate);
        phone_charge_publish(&phone_estimate,phone_device,-1,FALSE);
        phone_busy=FALSE;
        set_text(phone_label,"Phone offline");
    }
}
static gboolean phone_update(gpointer unused) {
    if(bus&&enable_phone&&!phone_busy&&!stopping) {
        phone_busy=TRUE;
        g_dbus_connection_call(bus,"org.kde.kdeconnect","/modules/kdeconnect","org.kde.kdeconnect.daemon","devices",g_variant_new("(bb)",TRUE,TRUE),G_VARIANT_TYPE("(as)"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1500,cancel,phone_devices,NULL);
    }
    return G_SOURCE_CONTINUE;
}
static void bus_ready(GObject *source,GAsyncResult *result,gpointer data) {
    GError *e=NULL;
    bus=g_bus_get_finish(result,&e);
    if(bus) {
        g_dbus_connection_signal_subscribe(bus,NULL,"org.freedesktop.DBus.Properties","PropertiesChanged","/org/mpris/MediaPlayer2",NULL,G_DBUS_SIGNAL_FLAGS_NONE,media_signal,NULL,NULL);
        media_update(NULL);
        phone_update(NULL);
    }
    g_clear_error(&e);
}
static gboolean hide_osd(gpointer unused) {
    if(osd_revealer)gtk_revealer_set_reveal_child(GTK_REVEALER(osd_revealer),FALSE);
    osd_timer=0;
    return G_SOURCE_REMOVE;
}
static void osd_revealed(GObject *object,GParamSpec *pspec,gpointer unused) {
    GtkRevealer *r=GTK_REVEALER(object);
    if(!gtk_revealer_get_reveal_child(r)&&!gtk_revealer_get_child_revealed(r))
        gtk_widget_set_visible(osd_window,FALSE);
}
static gboolean reveal_osd(gpointer unused) {
    gtk_revealer_set_reveal_child(GTK_REVEALER(osd_revealer),TRUE);
    return G_SOURCE_REMOVE;
}
static void update_osd_icon(int value,gboolean mute) {
    int level=((CLAMP(value,0,100)+2)/5)*5;
    char *name=mute?g_strdup("muted-speaker.svg"):g_strdup_printf("vol-%d.svg",level);
    char *path=g_build_filename(g_get_user_data_dir(),"notification-icons","vol",name,NULL);
    if(g_file_test(path,G_FILE_TEST_IS_REGULAR))
        gtk_image_set_from_file(GTK_IMAGE(osd_icon),path);
    else
        gtk_image_set_from_icon_name(GTK_IMAGE(osd_icon),mute?"audio-volume-muted-symbolic":"audio-volume-high-symbolic");
    g_free(path);
    g_free(name);
}
static void display_volume(int value,gboolean mute) {
    gboolean changed=volume>=0&&(volume!=value||muted!=mute);
    volume=value;
    muted=mute;
    char *s=g_strdup_printf(mute?"Volume muted":"Vol %d%%",value);
    set_text(volume_label,s);
    gtk_widget_set_tooltip_text(volume_label,"Left-click: Sound · Right-click: Bluetooth · Scroll: volume ±5% · Middle-click: mute");
    if(changed&&enable_osd&&!preview&&osd_window) {
        char *percent=g_strdup_printf(mute?"Muted":"%d%%",value);
        set_text(osd_label,percent);
        g_free(percent);
        gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(osd_meter),mute?0:CLAMP(value/100.,0.,1.));
        update_osd_icon(value,mute);
        GtkWidget *card=gtk_revealer_get_child(GTK_REVEALER(osd_revealer));
        if(mute)gtk_widget_add_css_class(card,"muted");
        else gtk_widget_remove_css_class(card,"muted");
        if(!gtk_widget_get_visible(osd_window)) {
            gtk_window_present(GTK_WINDOW(osd_window));
            g_idle_add(reveal_osd,NULL);
        }
        else gtk_revealer_set_reveal_child(GTK_REVEALER(osd_revealer),TRUE);
        if(osd_timer)g_source_remove(osd_timer);
        osd_timer=g_timeout_add(1500,hide_osd,NULL);
    }
    g_free(s);
}
static void sink_info(pa_context *c,const pa_sink_info *i,int end,void *data) {
    if(i&&!end)display_volume((int)lround(pa_cvolume_avg(&i->volume)*100.0/PA_VOLUME_NORM),i->mute);
}
static void server_info(pa_context *c,const pa_server_info *i,void *data) {
    if(!i)return;
    g_free(sink_name);
    sink_name=g_strdup(i->default_sink_name);
    if(sink_name) {
        pa_operation *o=pa_context_get_sink_info_by_name(c,sink_name,sink_info,NULL);
        if(o)pa_operation_unref(o);
    }
}
static void pulse_event(pa_context *c,pa_subscription_event_type_t t,uint32_t idx,void *data) {
    pa_operation *o=pa_context_get_server_info(c,server_info,NULL);
    if(o)pa_operation_unref(o);
}
static void pulse_state(pa_context *c,void *data) {
    if(pa_context_get_state(c)==PA_CONTEXT_READY) {
        pa_context_set_subscribe_callback(c,pulse_event,NULL);
        pa_operation *o=pa_context_subscribe(c,PA_SUBSCRIPTION_MASK_SINK|PA_SUBSCRIPTION_MASK_SERVER,NULL,NULL);
        if(o)pa_operation_unref(o);
        o=pa_context_get_server_info(c,server_info,NULL);
        if(o)pa_operation_unref(o);
    }
    else if(pa_context_get_state(c)==PA_CONTEXT_FAILED) {
        volume=-1;
        set_text(volume_label,"Audio offline");
    }
}
static gboolean connect_pulse(gpointer unused) {
    if(stopping)return G_SOURCE_REMOVE;
    if(pulse&&PA_CONTEXT_IS_GOOD(pa_context_get_state(pulse)))return G_SOURCE_CONTINUE;
    if(pulse) {
        pa_context_disconnect(pulse);
        pa_context_unref(pulse);
    }
    pulse=pa_context_new(pa_glib_mainloop_get_api(pulse_loop),"Simplepanel");
    pa_context_set_state_callback(pulse,pulse_state,NULL);
    pa_context_connect(pulse,NULL,PA_CONTEXT_NOAUTOSPAWN,NULL);
    return G_SOURCE_CONTINUE;
}
static gboolean kill_invest(gpointer unused) {
    invest_timeout=0;
    if(invest_process)g_subprocess_force_exit(invest_process);
    return G_SOURCE_REMOVE;
}
static void invest_result(GObject *source,GAsyncResult *result,gpointer unused) {
    char *out=NULL,*err=NULL;
    GError *e=NULL;
    gboolean ok=g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source),result,&out,&err,&e);
    if(invest_timeout) {
        g_source_remove(invest_timeout);
        invest_timeout=0;
    }
    if(ok&&g_subprocess_get_successful(G_SUBPROCESS(source))&&out&&*out) {
        g_strstrip(out);
        for(char *p=out;*p;p++)if(*p=='\n'||*p=='\r')*p=' ';
        set_text(invest_label,out);
    }
    else set_text(invest_label,"Invest unavailable");
    g_free(out);
    g_free(err);
    g_clear_error(&e);
    g_clear_object(&invest_process);
    invest_busy=FALSE;
}
static gboolean invest_update(gpointer unused) {
    if(!enable_invest||invest_busy||stopping||!g_getenv("SIMPLEPANEL_INVEST_COMMAND"))return G_SOURCE_CONTINUE;
    char *script=g_getenv("SIMPLEPANEL_INVEST_COMMAND")?g_strdup(g_getenv("SIMPLEPANEL_INVEST_COMMAND")):simple_control("simple-invest","mango/scripts/invest.sh");
    GError *e=NULL;
    invest_process=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_PIPE,&e,script,NULL);
    g_free(script);
    if(invest_process) {
        invest_busy=TRUE;
        invest_timeout=g_timeout_add_seconds(10,kill_invest,NULL);
        g_subprocess_communicate_utf8_async(invest_process,NULL,cancel,invest_result,NULL);
    }
    else set_text(invest_label,"Invest unavailable");
    g_clear_error(&e);
    return G_SOURCE_CONTINUE;
}
/* GTK4 has no replacement for named palette lookup yet. Keep the
   compatibility API isolated here; failed lookups fall back to widget text. */
G_GNUC_BEGIN_IGNORE_DEPRECATIONS
static void theme_color(GtkWidget *widget,const char *name,GdkRGBA *color) {
    gtk_widget_get_color(widget,color);
    gtk_style_context_lookup_color(gtk_widget_get_style_context(widget),name,color);
}
G_GNUC_END_IGNORE_DEPRECATIONS
static void theme_changed(GFileMonitor *monitor,GFile *file,GFile *other,GFileMonitorEvent event,gpointer data) {
    char *path=g_build_filename(g_get_user_config_dir(),"simplepanel","style.css",NULL);
    simple_theme_load(GTK_CSS_PROVIDER(data),path);g_free(path);
}
static void draw_bars(GtkDrawingArea *area,cairo_t *cr,int width,int h,gpointer unused) {
    GdkRGBA color;
    theme_color(GTK_WIDGET(area),"simple_visualizer",&color);
    gdk_cairo_set_source_rgba(cr,&color);
    double step=width/9.;
    for(int i=0;i<9;i++) {
        double bar=MAX(1.,bars[i]*(h-4));
        cairo_rectangle(cr,i*step+1,h-2-bar,MAX(1.,step-3),bar);
    }
    cairo_fill(cr);
}
static void cava_line(GObject *source,GAsyncResult *result,gpointer unused) {
    GError *e=NULL;
    gsize len;
    char *line=g_data_input_stream_read_line_finish(G_DATA_INPUT_STREAM(source),result,&len,&e);
    if(line) {
        char **parts=g_strsplit(line,";",10);
        for(int i=0;i<9&&parts[i];i++)bars[i]=CLAMP(g_ascii_strtod(parts[i],NULL)/100.,0.,1.);
        g_strfreev(parts);
        g_free(line);
        gtk_widget_queue_draw(visualizer);
        if(!stopping)g_data_input_stream_read_line_async(cava_input,G_PRIORITY_DEFAULT,cancel,cava_line,NULL);
    }
    else {
        memset(bars,0,sizeof bars);
        gtk_widget_queue_draw(visualizer);
        g_clear_object(&cava_input);
        if(cava_process) {
            g_subprocess_force_exit(cava_process);
            g_clear_object(&cava_process);
        }
    }
    g_clear_error(&e);
}
static gboolean start_cava(gpointer unused) {
    if(!enable_cava||cava_process||stopping)return G_SOURCE_CONTINUE;
    GError *e=NULL;
    cava_process=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_SILENCE,&e,"cava","-p",cava_path,NULL);
    if(cava_process) {
        cava_input=g_data_input_stream_new(g_subprocess_get_stdout_pipe(cava_process));
        g_data_input_stream_read_line_async(cava_input,G_PRIORITY_DEFAULT,cancel,cava_line,NULL);
    }
    g_clear_error(&e);
    return G_SOURCE_CONTINUE;
}
static GtkWidget *label(const char *initial,int max) {
    GtkWidget *w=gtk_label_new(initial);
    gtk_widget_set_valign(w,GTK_ALIGN_CENTER);
    gtk_label_set_single_line_mode(GTK_LABEL(w),TRUE);
    gtk_label_set_ellipsize(GTK_LABEL(w),PANGO_ELLIPSIZE_END);
    gtk_label_set_max_width_chars(GTK_LABEL(w),max);
    return w;
}
static GtkWidget *box(int spacing) {
    GtkWidget *w=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,spacing);
    gtk_widget_set_valign(w,GTK_ALIGN_FILL);
    return w;
}
static gboolean key_pressed(GtkEventControllerKey *c,guint key,guint code,GdkModifierType mods,gpointer data) {
    if(preview&&(key==GDK_KEY_Escape||key==GDK_KEY_q)) {
        stop_app(NULL);
        return TRUE;
    }
    return FALSE;
}
static void apply_monitor(GtkWindow *w,GdkMonitor *m) {
    gtk_layer_init_for_window(w);
    gtk_layer_set_namespace(w,"simplepanel");
    gtk_layer_set_layer(w,GTK_LAYER_SHELL_LAYER_TOP);
    gtk_layer_set_monitor(w,m);
    gtk_layer_set_keyboard_mode(w,GTK_LAYER_SHELL_KEYBOARD_MODE_NONE);
}
static void activate(GtkApplication *application,gpointer unused) {
    GdkDisplay *display=gdk_display_get_default();
    if(!display) {
        g_printerr("Simplepanel needs a Wayland display.\n");
        stop_app(NULL);
        return;
    }
    GListModel *monitors=gdk_display_get_monitors(display);
    GdkMonitor *monitor=NULL;
    for(guint i=0;i<g_list_model_get_n_items(monitors);i++) {
        GdkMonitor *m=g_list_model_get_item(monitors,i);
        if(!*monitor_name||!g_strcmp0(monitor_name,gdk_monitor_get_connector(m))) {
            monitor=m;
            break;
        }
        g_object_unref(m);
    }
    if(!monitor) {
        g_printerr("Configured monitor is not available.\n");
        stop_app(NULL);
        return;
    }
    if(!*monitor_name) {
        g_free(monitor_name);
        monitor_name=g_strdup(gdk_monitor_get_connector(monitor));
    }
    window=gtk_application_window_new(application);
    gtk_window_set_title(GTK_WINDOW(window),"Simplepanel preview");
    gtk_widget_add_css_class(window,"simplepanel");
    gtk_window_set_default_size(GTK_WINDOW(window),preview?1400:1,height);
    /* Layer-shell must accept the compositor's full-width allocation. */
    gtk_window_set_resizable(GTK_WINDOW(window),!preview||preview_layer);
    if(!preview||preview_layer) {
        if(!gtk_layer_is_supported()) {
            g_printerr("Layer-shell is unavailable; use --preview.\n");
            g_object_unref(monitor);
            stop_app(NULL);
            return;
        }
        apply_monitor(GTK_WINDOW(window),monitor);
        gtk_layer_set_anchor(GTK_WINDOW(window),preview_layer?GTK_LAYER_SHELL_EDGE_BOTTOM:GTK_LAYER_SHELL_EDGE_TOP,TRUE);
        gtk_layer_set_anchor(GTK_WINDOW(window),GTK_LAYER_SHELL_EDGE_LEFT,TRUE);
        gtk_layer_set_anchor(GTK_WINDOW(window),GTK_LAYER_SHELL_EDGE_RIGHT,TRUE);
        gtk_layer_set_margin(GTK_WINDOW(window),preview_layer?GTK_LAYER_SHELL_EDGE_BOTTOM:GTK_LAYER_SHELL_EDGE_TOP,top_margin);
        gtk_layer_set_margin(GTK_WINDOW(window),GTK_LAYER_SHELL_EDGE_LEFT,edge_margin);
        gtk_layer_set_margin(GTK_WINDOW(window),GTK_LAYER_SHELL_EDGE_RIGHT,edge_margin);
        if(!preview_layer)gtk_layer_auto_exclusive_zone_enable(GTK_WINDOW(window));
    }
    GtkWidget *layout=gtk_center_box_new(),*left=box(12),*center=box(16),*right=box(14);
    gtk_widget_add_css_class(layout,"panel");
    gtk_widget_add_css_class(left,"panel-section");
    gtk_widget_add_css_class(center,"panel-section");
    gtk_widget_add_css_class(right,"panel-section");
    gtk_widget_set_valign(layout,GTK_ALIGN_CENTER);
    gtk_widget_set_size_request(layout,-1,height);
    gtk_window_set_child(GTK_WINDOW(window),layout);
    gtk_center_box_set_start_widget(GTK_CENTER_BOX(layout),left);
    gtk_center_box_set_center_widget(GTK_CENTER_BOX(layout),center);
    gtk_center_box_set_end_widget(GTK_CENTER_BOX(layout),right);
    tags=box(2);
    title_label=label("Mango…",28);
    gtk_box_append(GTK_BOX(left),tags);
    gtk_box_append(GTK_BOX(left),title_label);
    visualizer=gtk_drawing_area_new();
    gtk_widget_set_size_request(visualizer,90,height-4);
    gtk_widget_set_valign(visualizer,GTK_ALIGN_CENTER);
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(visualizer),draw_bars,NULL,NULL);
    gtk_widget_set_visible(visualizer,enable_cava);
    media_label=label("",32);
    clock_label=label("",20);
    music=box(16);
    gtk_widget_set_visible(music,demo);
    gtk_widget_add_css_class(music,"music");
    clickable(music,G_CALLBACK(music_clicked));
    clickable(clock_label,G_CALLBACK(calendar_clicked));
    gtk_widget_set_tooltip_text(clock_label,"Open SimpleCalendar · add, edit and remove events");
    GtkEventController *music_motion=gtk_event_controller_motion_new();
    g_signal_connect(music_motion,"enter",G_CALLBACK(tag_enter),music);
    g_signal_connect(music_motion,"leave",G_CALLBACK(tag_leave),music);
    gtk_widget_add_controller(music,music_motion);
    gtk_widget_set_tooltip_text(music,"Open media dashboard (Super+Ctrl+N)");
    gtk_box_append(GTK_BOX(music),visualizer);
    gtk_box_append(GTK_BOX(music),media_label);
    gtk_box_append(GTK_BOX(center),music);
    gtk_box_append(GTK_BOX(center),clock_label);
    gtk_widget_set_visible(clock_label,dashboard_settings.show_panel_clock);
    net_label=label("Network…",28);
    volume_label=label("Audio…",15);
    gtk_widget_set_tooltip_text(volume_label,"Left-click: Sound · Right-click: Bluetooth · Scroll: volume ±5% · Middle-click: mute");
    for(guint button=GDK_BUTTON_PRIMARY;button<=GDK_BUTTON_SECONDARY;button+=2) {
        GtkGesture *open=gtk_gesture_click_new();
        gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(open),button);
        g_signal_connect(open,"pressed",G_CALLBACK(volume_open),GINT_TO_POINTER(button==GDK_BUTTON_SECONDARY));
        gtk_widget_add_controller(volume_label,GTK_EVENT_CONTROLLER(open));
    }
    GtkEventController *volume_wheel=gtk_event_controller_scroll_new(GTK_EVENT_CONTROLLER_SCROLL_VERTICAL|GTK_EVENT_CONTROLLER_SCROLL_DISCRETE);
    g_signal_connect(volume_wheel,"scroll",G_CALLBACK(volume_scroll),NULL);
    gtk_widget_add_controller(volume_label,volume_wheel);
    GtkGesture *volume_click=gtk_gesture_click_new();
    gtk_gesture_single_set_button(GTK_GESTURE_SINGLE(volume_click),GDK_BUTTON_MIDDLE);
    g_signal_connect(volume_click,"pressed",G_CALLBACK(volume_middle),NULL);
    gtk_widget_add_controller(volume_label,GTK_EVENT_CONTROLLER(volume_click));
    invest_label=label("Invest…",24);
    clickable(right,G_CALLBACK(system_clicked));
    gtk_widget_set_tooltip_text(right,"System information dashboard");
    gtk_widget_set_tooltip_text(invest_label,"World clock & system dashboard");
    battery_label=label("",30);
    gtk_widget_set_visible(battery_label,FALSE);
    phone_label=label("Phone…",18);
    gtk_box_append(GTK_BOX(right),net_label);
    gtk_box_append(GTK_BOX(right),volume_label);
    gtk_box_append(GTK_BOX(right),invest_label);
    gtk_box_append(GTK_BOX(right),battery_label);
    gtk_box_append(GTK_BOX(right),phone_label);
    gtk_widget_set_visible(invest_label,enable_invest);
    gtk_widget_set_visible(phone_label,enable_phone);
    GtkCssProvider *provider=gtk_css_provider_new();
    char opacity[G_ASCII_DTOSTR_BUF_SIZE];
    g_ascii_dtostr(opacity,sizeof opacity,background_opacity);
    char *style_path=g_build_filename(g_get_user_config_dir(),"simplepanel","style.css",NULL);
    simple_theme_load(provider,style_path);
    gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(provider),GTK_STYLE_PROVIDER_PRIORITY_USER+1);
    g_free(style_path);
    char *theme_dir=g_build_filename(g_get_user_config_dir(),"simple",NULL);
    GFile *theme_file=g_file_new_for_path(theme_dir);g_free(theme_dir);
    GFileMonitor *theme_monitor=g_file_monitor_directory(theme_file,G_FILE_MONITOR_NONE,NULL,NULL);g_object_unref(theme_file);
    if(theme_monitor){g_signal_connect(theme_monitor,"changed",G_CALLBACK(theme_changed),provider);g_object_set_data_full(G_OBJECT(window),"theme-monitor",theme_monitor,g_object_unref);}
    g_object_set_data_full(G_OBJECT(window),"theme-provider",provider,g_object_unref);
    provider=gtk_css_provider_new();
    char *styled=g_strdup_printf("window.simplepanel {background:transparent;box-shadow:none;} .panel {padding:0;} .panel .panel-section {background:alpha(@simple_bg,%s);border-radius:9px;padding:0 12px;} .panel label {padding-top:0;padding-bottom:0;} .panel .panel-section + .panel-section {margin-left:10px;}",opacity);
    gtk_css_provider_load_from_string(provider,styled);
    g_free(styled);
    gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(provider),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION+1);
    g_object_unref(provider);
    GtkEventController *keys=gtk_event_controller_key_new();
    g_signal_connect(keys,"key-pressed",G_CALLBACK(key_pressed),NULL);
    gtk_widget_add_controller(window,keys);
    if(enable_osd&&!preview) {
        osd_window=gtk_application_window_new(application);
        gtk_widget_add_css_class(osd_window,"simplepanel-osd");
        apply_monitor(GTK_WINDOW(osd_window),monitor);
        gtk_layer_set_namespace(GTK_WINDOW(osd_window),"simplepanel-osd");
        gtk_layer_set_exclusive_zone(GTK_WINDOW(osd_window),0);
        gtk_layer_set_layer(GTK_WINDOW(osd_window),GTK_LAYER_SHELL_LAYER_OVERLAY);
        gtk_layer_set_anchor(GTK_WINDOW(osd_window),GTK_LAYER_SHELL_EDGE_RIGHT,TRUE);
        gtk_layer_set_margin(GTK_WINDOW(osd_window),GTK_LAYER_SHELL_EDGE_RIGHT,10);
        GtkWidget *card=gtk_box_new(GTK_ORIENTATION_VERTICAL,14);
        gtk_widget_add_css_class(card,"volume-osd-card");
        osd_icon=gtk_image_new_from_icon_name("audio-volume-high-symbolic");
        gtk_image_set_pixel_size(GTK_IMAGE(osd_icon),64);
        osd_meter=gtk_progress_bar_new();
        gtk_orientable_set_orientation(GTK_ORIENTABLE(osd_meter),GTK_ORIENTATION_VERTICAL);
        gtk_progress_bar_set_inverted(GTK_PROGRESS_BAR(osd_meter),TRUE);
        gtk_widget_set_size_request(osd_meter,-1,150);
        gtk_widget_set_halign(osd_meter,GTK_ALIGN_CENTER);
        osd_label=label("100%",6);
        gtk_widget_set_size_request(osd_label,42,-1);
        gtk_box_append(GTK_BOX(card),osd_icon);
        gtk_box_append(GTK_BOX(card),osd_meter);
        gtk_box_append(GTK_BOX(card),osd_label);
        osd_revealer=gtk_revealer_new();
        gtk_revealer_set_transition_type(GTK_REVEALER(osd_revealer),GTK_REVEALER_TRANSITION_TYPE_CROSSFADE);
        gtk_revealer_set_transition_duration(GTK_REVEALER(osd_revealer),180);
        gtk_revealer_set_child(GTK_REVEALER(osd_revealer),card);
        g_signal_connect(osd_revealer,"notify::child-revealed",G_CALLBACK(osd_revealed),NULL);
        gtk_window_set_child(GTK_WINDOW(osd_window),osd_revealer);
    }
    g_object_unref(monitor);
    gtk_window_present(GTK_WINDOW(window));
    tick(NULL);
    g_timeout_add_seconds(1,tick,NULL);
    if(demo) {
        json_object *o=json_tokener_parse("{\"all_tags\":[{\"monitor\":\"demo\",\"tags\":[{\"index\":1,\"client_count\":1},{\"index\":2,\"is_active\":true},{\"index\":8,\"client_count\":1}]}]}");
        g_free(monitor_name);
        monitor_name=g_strdup("demo");
        update_tags(o);
        json_object_put(o);
        set_text(title_label,"kitty · Yazi");
        set_text(media_label,"▶ Artist — Now playing");
        set_text(net_label,"↓ 128 KiB/s  ↑ 12 KiB/s");
        display_volume(45,FALSE);
        set_text(invest_label,"145000 3200000");
        set_text(phone_label,"Phone 82% ⚡↑");
        for(int i=0;i<9;i++)bars[i]=.2+.075*i;
        gtk_widget_queue_draw(visualizer);
    }
    else {
        battery_update(NULL);
        g_timeout_add_seconds(15,battery_update,NULL);
        connect_feeds(NULL);
        g_timeout_add_seconds(5,connect_feeds,NULL);
        pulse_loop=pa_glib_mainloop_new(NULL);
        connect_pulse(NULL);
        g_timeout_add_seconds(5,connect_pulse,NULL);
        g_bus_get(G_BUS_TYPE_SESSION,cancel,bus_ready,NULL);
        g_timeout_add_seconds(5,media_update,NULL);
        g_timeout_add_seconds(30,phone_update,NULL);
        invest_update(NULL);
        g_timeout_add_seconds(3600,invest_update,NULL);
        char *dir=g_build_filename(g_get_user_runtime_dir(),"simplepanel",NULL);
        g_mkdir_with_parents(dir,0700);
        cava_path=g_build_filename(dir,"cava.conf",NULL);
        g_free(dir);
        g_file_set_contents(cava_path,"[general]\nbars=9\nframerate=12\n[input]\nmethod=pulse\nsource=auto\n[output]\nchannels=mono\nmethod=raw\nraw_target=/dev/stdout\ndata_format=ascii\nascii_max_range=100\nbar_delimiter=59\nframe_delimiter=10\n",-1,NULL);
        start_cava(NULL);
        g_timeout_add_seconds(30,start_cava,NULL);
    }
    if(duration>0)g_timeout_add_seconds(duration,stop_app,NULL);
}
int system_dashboard_main(int duration);
int main(int argc,char **argv) {
    char *path=NULL;
    gboolean check=FALSE,system_dashboard=FALSE;
    GOptionEntry options[]= {
        {"system-dashboard",0,0,G_OPTION_ARG_NONE,&system_dashboard,"World clock and system information",NULL},
        {
            "preview-layer",0,0,G_OPTION_ARG_NONE,&preview_layer,"Temporary bottom bar, no reserved space",NULL
        }, {
            "preview",0,0,G_OPTION_ARG_NONE,&preview,"Normal window; keep the current panel",NULL
        }, {
            "demo",0,0,G_OPTION_ARG_NONE,&demo,"Sample data with no service/network access",NULL
        }, {
            "check",0,0,G_OPTION_ARG_NONE,&check,"Validate config and test parsers without a display",NULL
        }, {
            "config",0,0,G_OPTION_ARG_FILENAME,&path,"Configuration file","PATH"
        }, {
            "duration",0,0,G_OPTION_ARG_INT,&duration,"Exit after N seconds","N"
        }, {
            NULL
        }
    };
    GOptionContext *context=g_option_context_new("— small fixed-layout Mango panel");
    g_option_context_add_main_entries(context,options,NULL);
    GError *error=NULL;
    if(!g_option_context_parse(context,&argc,&argv,&error)) {
        g_printerr("%s\n",error->message);
        return 2;
    }
    g_option_context_free(context);

    config=g_key_file_new();
    if(!path)path=g_build_filename(g_get_user_config_dir(),"simplepanel/config.ini",NULL);
    if(g_file_test(path,G_FILE_TEST_EXISTS)&&!g_key_file_load_from_file(config,path,G_KEY_FILE_NONE,&error)) {
        g_printerr("%s\n",error->message);
        return 2;
    }
    config_path=g_canonicalize_filename(path,NULL);
    if(!dashboard_settings_load(config,&error)){g_printerr("Invalid config: %s\n",error->message);g_clear_error(&error);return 2;}
    panel_timezone=*dashboard_settings.panel_zone?g_time_zone_new_identifier(dashboard_settings.panel_zone):g_time_zone_new_local();
    monitor_name=setting("monitor","");
    clock_format=setting("clock_format","%a %d  %H:%M");
    interface_name=setting("interface","");
    enable_cava=flag("cava",TRUE);
    enable_invest=flag("invest",TRUE);
    enable_phone=flag("phone",TRUE);
    enable_osd=flag("volume_osd",FALSE);
    if(g_key_file_has_key(config,"panel","height",NULL))height=g_key_file_get_integer(config,"panel","height",NULL);
    if(g_key_file_has_key(config,"panel","top_margin",NULL))top_margin=g_key_file_get_integer(config,"panel","top_margin",NULL);
    if(g_key_file_has_key(config,"panel","edge_margin",NULL))edge_margin=g_key_file_get_integer(config,"panel","edge_margin",NULL);
    if(g_key_file_has_key(config,"panel","background_opacity",NULL))background_opacity=g_key_file_get_double(config,"panel","background_opacity",NULL);
    if(height<24||height>80||edge_margin<0||edge_margin>200||top_margin<0||top_margin>200||!isfinite(background_opacity)||background_opacity<0||background_opacity>1||strchr(interface_name,'/')) {
        g_printerr("Invalid height, margin, opacity or network interface.\n");
        return 2;
    }
    if(check) {
        GDateTime *now=g_date_time_new_now(panel_timezone);
        char *s=g_date_time_format(now,clock_format);
        if(!s)return 2;
        g_free(s);
        g_date_time_unref(now);
        char rate[32];
        rate_text(2048,rate,sizeof rate);
        g_assert_cmpstr(rate,==,"2.0 KiB/s");
        json_object *o=json_tokener_parse("{\"title\":\"test\"}");
        g_assert_cmpstr(strfield(o,"title"),==,"test");
        json_object_put(o);
        g_print("Config and parser checks passed. GTK/layer-shell/Pulse/GIO linked; no services contacted.\n");
        return 0;
    }
    if(system_dashboard)return system_dashboard_main(duration);
    if(demo||preview_layer) {
        preview=TRUE;
    }
    g_setenv("GSK_RENDERER","cairo",FALSE);
    cancel=g_cancellable_new();
    app=gtk_application_new("com.go7.Simplepanel",G_APPLICATION_NON_UNIQUE);
    g_signal_connect(app,"activate",G_CALLBACK(activate),NULL);
    g_unix_signal_add(SIGTERM,stop_app,NULL);
    g_unix_signal_add(SIGINT,stop_app,NULL);
    int code=g_application_run(G_APPLICATION(app),0,NULL);
    stopping=TRUE;
    simple_market_stop();
    g_cancellable_cancel(cancel);
    if(cava_process) {
        g_subprocess_force_exit(cava_process);
        g_subprocess_wait(cava_process,NULL,NULL);
    }
    if(invest_process) {
        g_subprocess_force_exit(invest_process);
        g_subprocess_wait(invest_process,NULL,NULL);
    }
    if(pulse) {
        pa_context_disconnect(pulse);
        pa_context_unref(pulse);
    }
    if(pulse_loop)pa_glib_mainloop_free(pulse_loop);
    g_object_unref(app);
    return code;
}
