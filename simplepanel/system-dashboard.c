#define _GNU_SOURCE
#include "../simple-common/simple-paths.h"
#include "simple-theme.h"
#include "phone-charge-cache.h"
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>
#include <pulse/pulseaudio.h>
#include <pulse/glib-mainloop.h>
#include <sys/statvfs.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <stdio.h>
#include <string.h>
#include <glib-unix.h>
#include <signal.h>
#include <math.h>
#include <pwd.h>
#include <unistd.h>
#include <json-c/json.h>
#include "dashboard-settings.h"

static GtkApplication *application;
static GtkWidget *popup,*clocks[SIMPLE_MAX_CARDS],*cpu,*memory,*disk,*network,*volume,*bluetooth,*battery,*uptime,*phone_label,*market_prices[SIMPLE_MAX_CARDS],*market_trends[SIMPLE_MAX_CARDS];
static GtkWidget *control_cards[9];
static GDBusConnection *bus;
static gboolean phone_busy;
static PhoneChargeEstimate phone_estimate;
static char *phone_device;
static GTimeZone *timezones[SIMPLE_MAX_CARDS];
static GCancellable *cancel;
static pa_glib_mainloop *pulse_loop;
static pa_context *pulse;
static gboolean bluetooth_busy;
static guint timer,bt_timer;
static guint64 previous_total,previous_idle;
static GHashTable *net_previous;
static gint64 net_time;
static char *cpu_model;
/* Histories exist only while the dashboard is open; one sample per second. */
typedef struct {
    GtkWidget *area,*caption;
    double first[60],second[60];
    int count;
    gboolean network,bar;
    double red,green,blue;
} Graph;
static Graph cpu_graph={.red=.96,.green=.78,.blue=.42};
static Graph memory_graph={.bar=TRUE,.red=.57,.green=.77,.blue=.55};
static Graph disk_graph={.bar=TRUE,.red=.69,.green=.61,.blue=.84};
static Graph network_graph={.network=TRUE,.red=.43,.green=.73,.blue=.84};
static void graph_sample(Graph *graph,double first,double second) {
    if(graph->count==60) {
        memmove(graph->first,graph->first+1,59*sizeof(double));
        memmove(graph->second,graph->second+1,59*sizeof(double));
    } else graph->count++;
    graph->first[graph->count-1]=MAX(0,first);graph->second[graph->count-1]=MAX(0,second);
    if(graph->area)gtk_widget_queue_draw(graph->area);
}
/* GTK4 has no replacement for named palette lookup yet. Keep the
   compatibility API isolated here; failed lookups fall back to widget text. */
G_GNUC_BEGIN_IGNORE_DEPRECATIONS
static void theme_color(GtkWidget *widget,const char *name,GdkRGBA *color) {
    gtk_widget_get_color(widget,color);
    gtk_style_context_lookup_color(gtk_widget_get_style_context(widget),name,color);
}
G_GNUC_END_IGNORE_DEPRECATIONS
static void graph_draw(GtkDrawingArea *area,cairo_t *cr,int width,int height,gpointer data) {
    Graph *graph=data;
    GdkRGBA color,fg,upload;
    const char *name=graph==&cpu_graph?"simple_graph_cpu":graph==&memory_graph?"simple_graph_memory":graph==&disk_graph?"simple_graph_disk":"simple_graph_download";
    theme_color(GTK_WIDGET(area),name,&color);
    theme_color(GTK_WIDGET(area),"simple_fg",&fg);
    theme_color(GTK_WIDGET(area),"simple_graph_upload",&upload);
    graph->red=color.red;graph->green=color.green;graph->blue=color.blue;
    double w=MAX(1,width-2),h=MAX(1,height-4);
    if(graph->bar) {
        double value=graph->count?graph->first[graph->count-1]:0;
        cairo_set_source_rgba(cr,fg.red,fg.green,fg.blue,.08);cairo_rectangle(cr,0,2,w,h);cairo_fill(cr);
        cairo_set_source_rgba(cr,graph->red,graph->green,graph->blue,.85);
        cairo_rectangle(cr,0,2,w*CLAMP(value/100.,0,1),h);cairo_fill(cr);return;
    }
    double peak=100;
    if(graph->network) {
        peak=1;
        for(int i=0;i<graph->count;i++)peak=MAX(peak,MAX(graph->first[i],graph->second[i]));
    }
    cairo_set_line_width(cr,1);cairo_set_source_rgba(cr,fg.red,fg.green,fg.blue,.08);
    for(int i=0;i<3;i++){double y=2+h*i/2.;cairo_move_to(cr,0,y);cairo_line_to(cr,w,y);}cairo_stroke(cr);
    if(!graph->count)return;
    for(int series=0;series<(graph->network?2:1);series++) {
        double *samples=series?graph->second:graph->first;
        double r=series?upload.red:graph->red,g=series?upload.green:graph->green,b=series?upload.blue:graph->blue;
        for(int i=0;i<graph->count;i++) {
            double x=1+w*(60-graph->count+i)/59.,y=2+h*(1-CLAMP(samples[i]/peak,0,1));
            if(!i)cairo_move_to(cr,x,y);else cairo_line_to(cr,x,y);
        }
        cairo_set_source_rgba(cr,r,g,b,.95);cairo_set_line_width(cr,2);cairo_stroke(cr);
        if(graph->count==1){cairo_arc(cr,w,2+h*(1-CLAMP(samples[0]/peak,0,1)),2,0,6.283185);cairo_fill(cr);}
    }
}
static void graph_add(GtkWidget *box,Graph *graph,const char *caption) {
    graph->area=gtk_drawing_area_new();gtk_widget_set_size_request(graph->area,-1,graph->bar?10:38);
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(graph->area),graph_draw,graph,NULL);
    gtk_widget_set_hexpand(graph->area,TRUE);gtk_box_append(GTK_BOX(box),graph->area);
    graph->caption=gtk_label_new(caption);gtk_label_set_xalign(GTK_LABEL(graph->caption),0);
    gtk_label_set_wrap(GTK_LABEL(graph->caption),TRUE);gtk_widget_add_css_class(graph->caption,"graph-caption");
    gtk_box_append(GTK_BOX(box),graph->caption);
}
static gboolean quit_dashboard(gpointer data) {g_application_quit(G_APPLICATION(application));return G_SOURCE_REMOVE;}
static gboolean key(GtkEventControllerKey *controller,guint keyval,guint code,GdkModifierType state,gpointer data) {
    if(state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))return FALSE;
    if(keyval==GDK_KEY_Escape||keyval==GDK_KEY_q){quit_dashboard(NULL);return TRUE;}
    int dx=0,dy=0;
    switch(keyval) {
        case GDK_KEY_h: case GDK_KEY_Left: dx=-1;break;
        case GDK_KEY_l: case GDK_KEY_Right: dx=1;break;
        case GDK_KEY_k: case GDK_KEY_Up: dy=-1;break;
        case GDK_KEY_j: case GDK_KEY_Down: dy=1;break;
        default:break;
    }
    GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(popup));int current=-1;
    for(int i=0;i<9;i++)if(control_cards[i]&&focus==control_cards[i])current=i;
    if(keyval==GDK_KEY_Return||keyval==GDK_KEY_KP_Enter||keyval==GDK_KEY_space) {
        if(current<0)return FALSE;
        g_signal_emit_by_name(control_cards[current],"clicked");return TRUE;
    }
    if(!dx&&!dy)return FALSE;
    int next=current,best=G_MAXINT;
    if(current<0)next=3;
    else for(int i=0;i<9;i++) {
        if(!control_cards[i]||i==current)continue;
        const int xs[]={0,2,4,0,3,3},ys[]={0,0,0,1,1,2};
        int x=xs[i]-xs[current],y=ys[i]-ys[current];
        if((dx&&(x*dx<=0||y!=0))||(dy&&y*dy<=0))continue;
        int score=dy?abs(y)*10+abs(x):abs(x);
        if(score<best){best=score;next=i;}
    }
    if(next>=0){gtk_widget_grab_focus(control_cards[next]);gtk_window_set_focus_visible(GTK_WINDOW(popup),TRUE);}
    return TRUE;
}
static GtkWidget *text(const char *value,const char *style) {
    GtkWidget *w=gtk_label_new(value);gtk_label_set_xalign(GTK_LABEL(w),0);
    gtk_label_set_wrap(GTK_LABEL(w),TRUE);gtk_label_set_wrap_mode(GTK_LABEL(w),PANGO_WRAP_WORD_CHAR);
    gtk_widget_add_css_class(w,style);return w;
}
static void set(GtkWidget *w,const char *value) {gtk_label_set_text(GTK_LABEL(w),value);}
static GtkWidget *card(const char *title,GtkWidget **value) {
    GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,6);
    gtk_widget_add_css_class(box,"dash-system");gtk_widget_set_hexpand(box,TRUE);
    gtk_box_append(GTK_BOX(box),text(title,"dash-card-title"));
    *value=text("Reading…","dash-info");gtk_box_append(GTK_BOX(box),*value);
    return box;
}
/* Collect static facts once, asynchronously; the live metrics keep their own timers. */
static GtkWidget *facts[9];
static GSubprocess *fetch_process;
static guint fetch_timeout;
static const char *json_text(json_object *o,const char *name) {
    json_object *v=NULL;return o&&json_object_object_get_ex(o,name,&v)&&v?json_object_get_string(v):"";
}
static void fact_set(int index,const char *value) {
    const char *shown=value&&*value?value:"Unavailable";
    gtk_label_set_text(GTK_LABEL(facts[index]),shown);gtk_widget_set_tooltip_text(facts[index],shown);
}
static gboolean fetch_expired(gpointer unused) {
    fetch_timeout=0;if(fetch_process)g_subprocess_force_exit(fetch_process);return G_SOURCE_REMOVE;
}
static void facts_ready(GObject *source,GAsyncResult *result,gpointer unused) {
    char *out=NULL,*err=NULL;GError *error=NULL;
    gboolean ok=g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source),result,&out,&err,&error);
    if(fetch_timeout){g_source_remove(fetch_timeout);fetch_timeout=0;}
    json_object *root=ok&&out?json_tokener_parse(out):NULL;
    if(root&&json_object_is_type(root,json_type_array))for(size_t i=0;i<json_object_array_length(root);i++) {
        json_object *item=json_object_array_get_idx(root,i),*r=NULL;
        if(!json_object_object_get_ex(item,"result",&r)||!r)continue;
        const char *type=json_text(item,"type");char *value=NULL;int index=-1;
        if(!strcmp(type,"OS")){index=0;value=g_strdup(json_text(r,"prettyName"));}
        else if(!strcmp(type,"Host")){index=1;const char *model=json_text(r,"version");if(!*model)model=json_text(r,"name");value=g_strdup_printf("%s · %s",g_get_host_name(),model);}
        else if(!strcmp(type,"Kernel")){index=2;value=g_strdup_printf("%s · %s",json_text(r,"release"),json_text(r,"architecture"));}
        else if(!strcmp(type,"InitSystem")){index=3;value=g_strdup(json_text(r,"name"));}
        else if(!strcmp(type,"WM")){index=4;value=g_strdup_printf("%s · %s",json_text(r,"prettyName"),json_text(r,"protocolName"));}
        else if(!strcmp(type,"Shell")){index=5;value=g_strdup_printf("%s %s",json_text(r,"prettyName"),json_text(r,"version"));}
        else if(!strcmp(type,"Packages")){index=8;value=g_strdup(json_text(r,"all"));}
        else if((!strcmp(type,"GPU")||!strcmp(type,"Display"))&&json_object_is_type(r,json_type_array)) {
            gboolean gpu=!strcmp(type,"GPU");index=gpu?6:7;GString *lines=g_string_new(NULL);
            for(size_t n=0;n<json_object_array_length(r);n++) {
                json_object *device=json_object_array_get_idx(r,n);if(n)g_string_append(lines," · ");
                if(gpu)g_string_append(lines,json_text(device,"name"));
                else {json_object *output=NULL;json_object_object_get_ex(device,"output",&output);
                    g_string_append_printf(lines,"%s %s×%s",json_text(device,"name"),json_text(output,"width"),json_text(output,"height"));}
            }
            value=g_string_free(lines,FALSE);
        }
        if(index>=0)fact_set(index,value);
        g_free(value);
    }
    if(root)json_object_put(root);
    for(int i=0;i<9;i++)if(!strcmp(gtk_label_get_text(GTK_LABEL(facts[i])),"Reading…"))fact_set(i,NULL);
    g_free(out);g_free(err);g_clear_error(&error);g_clear_object(&fetch_process);
}
static GtkWidget *system_facts(void) {
    GtkWidget *panel=gtk_box_new(GTK_ORIENTATION_VERTICAL,10);gtk_widget_add_css_class(panel,"dash-system");
    gtk_box_append(GTK_BOX(panel),text("SYSTEM","dash-card-title"));
    GtkWidget *grid=gtk_grid_new();gtk_grid_set_row_spacing(GTK_GRID(grid),5);gtk_grid_set_column_spacing(GTK_GRID(grid),16);
    const char *names[]={"OS","Host","Kernel","Init","WM","Shell","GPU","Display","Packages"};
    for(int i=0;i<9;i++) {
        int column=(i/3)*2,row=i%3;
        GtkWidget *name=text(names[i],"dash-key");facts[i]=text("Reading…","dash-info");
        gtk_label_set_wrap(GTK_LABEL(facts[i]),FALSE);gtk_label_set_ellipsize(GTK_LABEL(facts[i]),PANGO_ELLIPSIZE_END);
        gtk_label_set_max_width_chars(GTK_LABEL(facts[i]),25);gtk_widget_set_hexpand(facts[i],TRUE);
        gtk_grid_attach(GTK_GRID(grid),name,column,row,1,1);gtk_grid_attach(GTK_GRID(grid),facts[i],column+1,row,1,1);
    }
    gtk_box_append(GTK_BOX(panel),grid);
    struct passwd *login=getpwuid(getuid());
    if(login&&login->pw_shell){char *shell=g_path_get_basename(login->pw_shell);fact_set(5,shell);g_free(shell);}
    fetch_process=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_PIPE,NULL,
        "fastfetch","--config","none","--structure","OS:Host:Kernel:InitSystem:WM:GPU:Display:Packages","--format","json",NULL);
    if(fetch_process){fetch_timeout=g_timeout_add_seconds(5,fetch_expired,NULL);g_subprocess_communicate_utf8_async(fetch_process,NULL,cancel,facts_ready,NULL);}
    else for(int i=0;i<9;i++)fact_set(i,NULL);
    return panel;
}

static void open_control(GtkButton *button,gpointer data) {
    int which=GPOINTER_TO_INT(data);
    char *helper=simple_control("simple-network","simplepicker/network/scripts/simple-network");
    char *disk_helper=simple_control("simple-disk","simplepicker/disk/scripts/simple-disk");
    char *disk_args[]={disk_helper,NULL};
    char *resource_helper=simple_control(which==0?"simple-cpu":"simple-memory",which==0?"simplepicker/resources/scripts/simple-cpu":"simplepicker/resources/scripts/simple-memory");
    char *resource_args[]={resource_helper,NULL};
    char *network_args[]={helper,NULL};
    char *bluetooth_args[]={helper,"bt",NULL};
    char *audio_helper=simple_control("simple-sound","simplepicker/sound/scripts/simple-sound");
    char *audio_args[]={audio_helper,NULL};
    char **args=which<2?resource_args:which==2?disk_args:which==3?network_args:which==5?bluetooth_args:audio_args;
    GError *error=NULL;
    if(!g_spawn_async(NULL,args,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,&error)) {
        g_warning("System control failed: %s",error->message);g_clear_error(&error);
    }
    g_free(helper);g_free(audio_helper);g_free(disk_helper);g_free(resource_helper);
}
static guint64 counter(const char *iface,const char *which) {
    char *path=g_strdup_printf("/sys/class/net/%s/statistics/%s_bytes",iface,which),*raw=NULL;
    guint64 value=0;if(g_file_get_contents(path,&raw,NULL,NULL))value=g_ascii_strtoull(raw,NULL,10);
    g_free(raw);g_free(path);return value;
}
static void update_network(void) {
    double combined_down=0,combined_up=0;
    gint64 now=g_get_monotonic_time();double elapsed=(now-net_time)/1000000.;
    GString *out=g_string_new(NULL);struct ifaddrs *all=NULL;
    GHashTable *seen=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,NULL);
    if(getifaddrs(&all)==0) {
        for(struct ifaddrs *a=all;a;a=a->ifa_next) {
            if(!a->ifa_addr||!(a->ifa_flags&IFF_UP)||(a->ifa_flags&IFF_LOOPBACK))continue;
            int family=a->ifa_addr->sa_family;
            if(family!=AF_INET&&family!=AF_INET6)continue;
            if(g_hash_table_contains(seen,a->ifa_name))continue;
            if(family==AF_INET6&&IN6_IS_ADDR_LINKLOCAL(&((struct sockaddr_in6*)a->ifa_addr)->sin6_addr))continue;
            g_hash_table_add(seen,g_strdup(a->ifa_name));
            char ip[INET6_ADDRSTRLEN];
            const void *addr=family==AF_INET?(void*)&((struct sockaddr_in*)a->ifa_addr)->sin_addr:(void*)&((struct sockaddr_in6*)a->ifa_addr)->sin6_addr;
            inet_ntop(family,addr,ip,sizeof ip);
            guint64 rx=counter(a->ifa_name,"rx"),tx=counter(a->ifa_name,"tx");
            guint64 *old=g_hash_table_lookup(net_previous,a->ifa_name);
            double down=old&&elapsed>0&&rx>=old[0]?(rx-old[0])/elapsed/1024:0;
            double up=old&&elapsed>0&&tx>=old[1]?(tx-old[1])/elapsed/1024:0;
            combined_down+=down;combined_up+=up;
            if(out->len)g_string_append(out,"\n");
            g_string_append_printf(out,"%s · %s\n↓ %.1f KiB/s   ↑ %.1f KiB/s",a->ifa_name,ip,down,up);
            guint64 *current=g_new(guint64,2);current[0]=rx;current[1]=tx;
            g_hash_table_replace(net_previous,g_strdup(a->ifa_name),current);
        }
        freeifaddrs(all);
    }
    if(net_time)graph_sample(&network_graph,combined_down,combined_up);
    double peak=1;
    for(int i=0;i<network_graph.count;i++)peak=MAX(peak,MAX(network_graph.first[i],network_graph.second[i]));
    char *scale=g_strdup_printf("↓ Download · ↑ Upload · scale %.1f KiB/s\nCombined interfaces · last 60 samples",peak);
    gtk_label_set_text(GTK_LABEL(network_graph.caption),scale);g_free(scale);
    set(network,out->len?out->str:"No active network address");
    g_string_free(out,TRUE);g_hash_table_unref(seen);net_time=now;
}
static gboolean tick(gpointer data) {
    GDateTime *now=g_date_time_new_now_utc();
    for(gsize i=0;i<dashboard_settings.clocks;i++) {
        GDateTime *local=g_date_time_to_timezone(now,timezones[i]);
        char *value=g_date_time_format(local,dashboard_settings.format);set(clocks[i],value);
        g_free(value);g_date_time_unref(local);
    }
    g_date_time_unref(now);
    char *raw=NULL;
    if(g_file_get_contents("/proc/stat",&raw,NULL,NULL)) {
        unsigned long long u=0,n=0,s=0,idle=0,wait=0,irq=0,soft=0,steal=0;
        if(sscanf(raw,"cpu %llu %llu %llu %llu %llu %llu %llu %llu",&u,&n,&s,&idle,&wait,&irq,&soft,&steal)>=4) {
            guint64 total=u+n+s+idle+wait+irq+soft+steal,idle_total=idle+wait;
            double used=previous_total&&total>previous_total?100.*(1.-(double)(idle_total-previous_idle)/(total-previous_total)):0;
            char *value=g_strdup_printf("%.0f%% in use\n%s",used,cpu_model);set(cpu,value);g_free(value);
            if(previous_total)graph_sample(&cpu_graph,used,0);
            previous_total=total;previous_idle=idle_total;
        }
        g_free(raw);raw=NULL;
    }
    if(g_file_get_contents("/proc/meminfo",&raw,NULL,NULL)) {
        guint64 total=0,available=0;char **lines=g_strsplit(raw,"\n",-1);
        for(int i=0;lines[i];i++) {
            if(g_str_has_prefix(lines[i],"MemTotal:"))total=g_ascii_strtoull(lines[i]+9,NULL,10);
            if(g_str_has_prefix(lines[i],"MemAvailable:"))available=g_ascii_strtoull(lines[i]+13,NULL,10);
        }
        char *value=g_strdup_printf("%.1f / %.1f GiB\n%.0f%% in use",(total-MIN(total,available))/1048576.,total/1048576.,total?100.*(total-MIN(total,available))/total:0);
        graph_sample(&memory_graph,total?100.*(total-MIN(total,available))/total:0,0);
        set(memory,value);g_free(value);g_strfreev(lines);g_free(raw);
    }
    GString *storage=g_string_new(NULL);const char *paths[]={"/",g_get_home_dir()};
    for(int i=0;i<2;i++) {
        struct statvfs v;
        if(statvfs(paths[i],&v)==0) {
            double total=(double)v.f_blocks*v.f_frsize/1073741824.,free=(double)v.f_bavail*v.f_frsize/1073741824.;
            if(i==0) {
                double used=v.f_blocks?100.*(v.f_blocks-v.f_bfree)/v.f_blocks:0;
                graph_sample(&disk_graph,used,0);
                char *caption=g_strdup_printf("Root filesystem · %.0f%% used",used);
                gtk_label_set_text(GTK_LABEL(disk_graph.caption),caption);g_free(caption);
            }
            g_string_append_printf(storage,"%s%s: %.1f GiB available / %.1f GiB",i?"\n":"",i?"Home":"Root",free,total);
        }
    }
    set(disk,storage->len?storage->str:"Storage unavailable");g_string_free(storage,TRUE);
    GString *power=g_string_new(NULL);GDir *supplies=g_dir_open("/sys/class/power_supply",0,NULL);const char *name;
    while(supplies&&(name=g_dir_read_name(supplies))) {
        char *base=g_build_filename("/sys/class/power_supply",name,NULL),*type_path=g_build_filename(base,"type",NULL),*type=NULL;
        if(g_file_get_contents(type_path,&type,NULL,NULL)&&g_str_has_prefix(type,"Battery")) {
            char *cap_path=g_build_filename(base,"capacity",NULL),*status_path=g_build_filename(base,"status",NULL),*cap=NULL,*status=NULL;
            if(g_file_get_contents(cap_path,&cap,NULL,NULL)&&g_file_get_contents(status_path,&status,NULL,NULL))
                g_string_append_printf(power,"%s%s · %s%% · %s",power->len?"\n":"",name,g_strstrip(cap),g_strstrip(status));
            g_free(cap_path);g_free(status_path);g_free(cap);g_free(status);
        }
        g_free(base);g_free(type_path);g_free(type);
    }
    if(supplies)g_dir_close(supplies);
    set(battery,power->len?power->str:"No battery reported");g_string_free(power,TRUE);
    raw=NULL;
    if(g_file_get_contents("/proc/uptime",&raw,NULL,NULL)) {
        guint64 seconds=(guint64)g_ascii_strtod(raw,NULL);char *value=g_strdup_printf("%llu days · %llu hours · %llu minutes",(unsigned long long)(seconds/86400),(unsigned long long)(seconds/3600%24),(unsigned long long)(seconds/60%60));
        set(uptime,value);g_free(value);g_free(raw);
    }
    if(dashboard_settings.show_markets) {
        simple_market_refresh();json_object *prices=simple_market_read();
        char *change_key=g_strconcat(dashboard_settings.currency,"_24h_change",NULL);
        for(gsize i=0;i<dashboard_settings.markets;i++) {
            char *value=simple_market_price(prices,i);set(market_prices[i],value);g_free(value);
            json_object *coin=NULL,*change=NULL,*stamp=NULL;
            if(prices)json_object_object_get_ex(prices,dashboard_settings.ids[i],&coin);
            if(coin){json_object_object_get_ex(coin,change_key,&change);json_object_object_get_ex(coin,"last_updated_at",&stamp);}
            gtk_widget_remove_css_class(market_trends[i],"gain");gtk_widget_remove_css_class(market_trends[i],"loss");
            if(change&&(json_object_is_type(change,json_type_double)||json_object_is_type(change,json_type_int))&&isfinite(json_object_get_double(change))) {
                double delta=json_object_get_double(change);value=g_strdup_printf("%+.2f%% · 24h",delta);set(market_trends[i],value);g_free(value);
                gtk_widget_add_css_class(market_trends[i],delta>=0?"gain":"loss");
            }else set(market_trends[i],"24h change unavailable");
            GDateTime *updated=stamp?g_date_time_new_from_unix_local(json_object_get_int64(stamp)):NULL;
            char *date=updated?g_date_time_format(updated,"%d %b %H:%M"):g_strdup("unknown time");
            char *tooltip=g_strdup_printf("Cached CoinGecko quote · updated %s",date);
            gtk_widget_set_tooltip_text(market_prices[i],tooltip);g_free(tooltip);g_free(date);if(updated)g_date_time_unref(updated);
        }
        g_free(change_key);if(prices)json_object_put(prices);
    }
    update_network();return G_SOURCE_CONTINUE;
}
static void bluetooth_result(GObject *source,GAsyncResult *result,gpointer data) {
    GError *error=NULL;GVariant *reply=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&error);
    if(!reply) {if(!g_cancellable_is_cancelled(cancel))set(bluetooth,"Bluetooth unavailable");g_clear_error(&error);bluetooth_busy=FALSE;return;}
    GVariant *objects=g_variant_get_child_value(reply,0);GVariantIter iter;const char *path;GVariant *interfaces;
    guint adapters=0,powered=0;GString *devices=g_string_new(NULL);g_variant_iter_init(&iter,objects);
    while(g_variant_iter_next(&iter,"{&o@a{sa{sv}}}",&path,&interfaces)) {
        GVariant *props=g_variant_lookup_value(interfaces,"org.bluez.Adapter1",G_VARIANT_TYPE("a{sv}"));
        if(props){gboolean on=FALSE;g_variant_lookup(props,"Powered","b",&on);adapters++;powered+=on;g_variant_unref(props);}
        props=g_variant_lookup_value(interfaces,"org.bluez.Device1",G_VARIANT_TYPE("a{sv}"));
        if(props){gboolean connected=FALSE;const char *alias="Device";g_variant_lookup(props,"Connected","b",&connected);g_variant_lookup(props,"Alias","&s",&alias);
            if(connected)g_string_append_printf(devices,"\n%s",alias);
            g_variant_unref(props);}
        g_variant_unref(interfaces);
    }
    char *value=g_strdup_printf("%s%s",!adapters?"No Bluetooth adapter":powered?"Bluetooth on":"Bluetooth off",devices->len?devices->str:"\nNo connected devices");
    set(bluetooth,value);g_free(value);g_string_free(devices,TRUE);g_variant_unref(objects);g_variant_unref(reply);bluetooth_busy=FALSE;
}
static void system_bus(GObject *source,GAsyncResult *result,gpointer data) {
    GError *error=NULL;GDBusConnection *bus=g_bus_get_finish(result,&error);
    if(!bus){bluetooth_busy=FALSE;if(!g_cancellable_is_cancelled(cancel))set(bluetooth,"Bluetooth unavailable");g_clear_error(&error);return;}
    g_dbus_connection_call(bus,"org.bluez","/","org.freedesktop.DBus.ObjectManager","GetManagedObjects",NULL,G_VARIANT_TYPE("(a{oa{sa{sv}}})"),G_DBUS_CALL_FLAGS_NONE,2000,cancel,bluetooth_result,NULL);g_object_unref(bus);
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
            phone_charge_sample(&phone_estimate,charge,charging,g_get_monotonic_time()/1000000.0);
            PhoneChargeEstimate estimate=phone_estimate;
            phone_charge_snapshot(&estimate,phone_device,charge,charging);
            PhoneChargeSpeed speed=estimate.speed;
            const char *state=speed==PHONE_CHARGE_LEARNING?"Charging · estimating speed…"
                :speed==PHONE_CHARGE_SLOW?"Charging · est. slow"
                :speed==PHONE_CHARGE_NORMAL?"Charging · est. normal"
                :speed==PHONE_CHARGE_RAPID?"Charging · est. rapid"
                :speed==PHONE_CHARGE_FULL?"Fully charged":"On battery";
            GString *text=g_string_new(NULL);
            g_string_append_printf(text,"Phone %d%%%s\n%s",charge,phone_charge_icon(speed),state);
            if(speed>=PHONE_CHARGE_SLOW&&speed<=PHONE_CHARGE_RAPID)
                g_string_append_printf(text,"\n%+.2f%%/min%s",estimate.per_minute,
                                       estimate.observed_seconds<300?" · provisional":"");
            set(phone_label,text->str);g_string_free(text,TRUE);
            gtk_widget_set_tooltip_text(phone_label,
                "Charging speed estimated from recent battery levels, not measured charger power.\n"
                "First estimate after about one minute; refines over ten minutes.\n"
                "Phone use and temperature affect the result. Charging usually slows near full.");
        }
        else {phone_charge_reset(&phone_estimate);set(phone_label,"Phone —");}
        g_variant_unref(d);
        g_variant_unref(r);
    }
    else {phone_charge_reset(&phone_estimate);set(phone_label,"Phone unavailable");}
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
                phone_charge_reset(&phone_estimate);g_free(phone_device);phone_device=g_strdup(devices[0]);
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
        phone_busy=FALSE;
        phone_charge_reset(&phone_estimate);
        set(phone_label,"Phone offline");
    }
}
static gboolean phone_update(gpointer unused) {
    if(bus&&!phone_busy) {
        phone_busy=TRUE;
        g_dbus_connection_call(bus,"org.kde.kdeconnect","/modules/kdeconnect","org.kde.kdeconnect.daemon","devices",g_variant_new("(bb)",TRUE,TRUE),G_VARIANT_TYPE("(as)"),G_DBUS_CALL_FLAGS_NO_AUTO_START,1500,cancel,phone_devices,NULL);
    }
    return G_SOURCE_CONTINUE;
}
static void phone_bus_ready(GObject *source,GAsyncResult *result,gpointer data) {
    GError *error=NULL;bus=g_bus_get_finish(result,&error);
    if(bus)phone_update(NULL);else {phone_charge_reset(&phone_estimate);set(phone_label,"Phone unavailable");}
    g_clear_error(&error);
}
static gboolean bluetooth_refresh(gpointer data) {
    phone_update(NULL);
    if(!bluetooth_busy){bluetooth_busy=TRUE;g_bus_get(G_BUS_TYPE_SYSTEM,cancel,system_bus,NULL);}return G_SOURCE_CONTINUE;
}
static void sink_info(pa_context *context,const pa_sink_info *info,int eol,void *data) {
    if(eol||!info)return;
    char *value=g_strdup_printf("%u%% · %s\n%s",(unsigned)(100.*pa_cvolume_avg(&info->volume)/PA_VOLUME_NORM+.5),info->mute?"Muted":"Sound on",info->description?info->description:info->name);
    set(volume,value);g_free(value);
}
static void server_info(pa_context *context,const pa_server_info *info,void *data) {
    if(!info||!info->default_sink_name){set(volume,"No default output");return;}
    pa_operation *op=pa_context_get_sink_info_by_name(context,info->default_sink_name,sink_info,NULL);if(op)pa_operation_unref(op);
}
static void audio_refresh(pa_context *context,pa_subscription_event_type_t event,uint32_t index,void *data) {
    pa_operation *op=pa_context_get_server_info(context,server_info,NULL);if(op)pa_operation_unref(op);
}
static void audio_state(pa_context *context,void *data) {
    if(pa_context_get_state(context)==PA_CONTEXT_READY) {
        pa_context_set_subscribe_callback(context,audio_refresh,NULL);
        pa_operation *op=pa_context_subscribe(context,PA_SUBSCRIPTION_MASK_SINK|PA_SUBSCRIPTION_MASK_SERVER,NULL,NULL);if(op)pa_operation_unref(op);
        audio_refresh(context,0,0,NULL);
    } else if(pa_context_get_state(context)==PA_CONTEXT_FAILED)set(volume,"Audio service unavailable");
}
static void activate_dashboard(GtkApplication *app,gpointer data) {
    if(popup){quit_dashboard(NULL);return;}
    popup=gtk_application_window_new(app);gtk_window_set_title(GTK_WINDOW(popup),"World clock & system");
    gtk_widget_add_css_class(popup,"dashboard");gtk_widget_add_css_class(popup,"system-dashboard");
    /* Ordinary floating window: other applications retain normal input. */
    gtk_window_set_decorated(GTK_WINDOW(popup),FALSE);
    int popup_width=1060,popup_height=900;
    GListModel *outputs=gdk_display_get_monitors(gdk_display_get_default());
    if(g_list_model_get_n_items(outputs)) {
        GdkMonitor *output=g_list_model_get_item(outputs,0);GdkRectangle geometry;
        gdk_monitor_get_geometry(output,&geometry);
        popup_width=MIN(popup_width,MAX(320,geometry.width-64));
        popup_height=MIN(popup_height,MAX(300,geometry.height-80));g_object_unref(output);
    }
    gtk_window_set_default_size(GTK_WINDOW(popup),popup_width,-1);
    GtkWidget *scroll=gtk_scrolled_window_new();gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),GTK_POLICY_NEVER,GTK_POLICY_AUTOMATIC);
    gtk_scrolled_window_set_propagate_natural_height(GTK_SCROLLED_WINDOW(scroll),TRUE);
    gtk_scrolled_window_set_max_content_height(GTK_SCROLLED_WINDOW(scroll),popup_height);
    gtk_window_set_child(GTK_WINDOW(popup),scroll);
    GtkWidget *body=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);gtk_widget_add_css_class(body,"dashboard-panel");gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll),body);
    gtk_box_append(GTK_BOX(body),text("World clock & system","dash-title"));
    gtk_box_append(GTK_BOX(body),system_facts());
    GtkSizeGroup *summary_size=gtk_size_group_new(GTK_SIZE_GROUP_VERTICAL);
    GtkWidget *row=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12);gtk_box_set_homogeneous(GTK_BOX(row),TRUE);
    for(gsize i=0;i<dashboard_settings.clocks;i++){GtkWidget *c=card(dashboard_settings.cities[i],&clocks[i]);gtk_widget_add_css_class(clocks[i],"world-time");gtk_size_group_add_widget(summary_size,c);gtk_box_append(GTK_BOX(row),c);}
    gtk_box_append(GTK_BOX(body),row);
    gtk_widget_set_visible(row,dashboard_settings.show_clocks);
    GtkWidget *market_row=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12);gtk_box_set_homogeneous(GTK_BOX(market_row),TRUE);
    for(gsize i=0;i<dashboard_settings.markets;i++) {
        GtkWidget *c=card(dashboard_settings.labels[i],&market_prices[i]);
        gtk_orientable_set_orientation(GTK_ORIENTABLE(c),GTK_ORIENTATION_HORIZONTAL);
        gtk_widget_add_css_class(c,"market-card");
        market_trends[i]=text("24h change unavailable","dash-info");gtk_box_append(GTK_BOX(c),market_trends[i]);
        gtk_box_append(GTK_BOX(market_row),c);
    }
    gtk_box_append(GTK_BOX(body),market_row);
    gtk_widget_set_visible(market_row,dashboard_settings.show_markets);
    GtkWidget *grid=gtk_grid_new();gtk_grid_set_column_spacing(GTK_GRID(grid),12);gtk_grid_set_row_spacing(GTK_GRID(grid),12);gtk_grid_set_column_homogeneous(GTK_GRID(grid),TRUE);
    GtkWidget **values[]={&cpu,&memory,&disk,&network,&volume,&bluetooth,&battery,&uptime,&phone_label};const char *titles[]={"CPU","MEMORY","DISK","NETWORK","VOLUME","BLUETOOTH","BATTERY","UPTIME","PHONE"};
    for(int i=0;i<9;i++) {
        GtkWidget *c=card(titles[i],values[i]);
        if(i>=6)gtk_size_group_add_widget(summary_size,c);
        if(i==0)graph_add(c,&cpu_graph,"0–100% · last 60 samples");
        if(i==1)graph_add(c,&memory_graph,"Memory in use");
        if(i==2)graph_add(c,&disk_graph,"Root filesystem");
        if(i==3)graph_add(c,&network_graph,"↓ Download · ↑ Upload");
        if(i<6) {
            const char *hint=i==0?"CPU details · Super+Ctrl+C":i==1?"Memory details · Super+Ctrl+E":i==2?"Disk space · Super+Ctrl+D":i==3?"Open network · Super+Ctrl+W":i==4?"Sound devices · Super+Ctrl+S":"Open Bluetooth · Super+Ctrl+B";
            GtkWidget *footer=text(hint,"dash-key");
            gtk_widget_set_vexpand(footer,TRUE);gtk_widget_set_valign(footer,GTK_ALIGN_END);
            gtk_box_append(GTK_BOX(c),footer);
            GtkWidget *button=gtk_button_new();control_cards[i]=button;gtk_button_set_child(GTK_BUTTON(button),c);
            gtk_widget_add_css_class(button,"control-card");gtk_widget_set_cursor_from_name(button,"pointer");
            gtk_widget_set_tooltip_text(button,hint);
            g_signal_connect(button,"clicked",G_CALLBACK(open_control),GINT_TO_POINTER(i));
            c=button;
        }
        if(i<3)gtk_grid_attach(GTK_GRID(grid),c,i*2,0,2,1);
        else if(i==3)gtk_grid_attach(GTK_GRID(grid),c,0,1,3,2);
        else if(i<6)gtk_grid_attach(GTK_GRID(grid),c,3,i-3,3,1);
        else gtk_grid_attach(GTK_GRID(grid),c,(i-6)*2,3,2,1);
    }
    g_object_unref(summary_size);
    gtk_box_append(GTK_BOX(body),grid);gtk_box_append(GTK_BOX(body),text("H J K L / Arrows  Move · Enter / Space  Open · Esc / Q  Close","dash-key"));
    /* Appearance comes from shared defaults; this file is an optional override. */
    char *path=g_build_filename(g_get_user_config_dir(),"simplepanel/dashboard.css",NULL);
    GtkCssProvider *style=gtk_css_provider_new();simple_theme_load(style,path);
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(style),GTK_STYLE_PROVIDER_PRIORITY_USER+2);
    g_object_unref(style);g_free(path);
    GtkEventController *keys=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(keys,GTK_PHASE_CAPTURE);g_signal_connect(keys,"key-pressed",G_CALLBACK(key),NULL);gtk_widget_add_controller(popup,keys);
    g_bus_get(G_BUS_TYPE_SESSION,cancel,phone_bus_ready,NULL);
    tick(NULL);timer=g_timeout_add_seconds(1,tick,NULL);bluetooth_refresh(NULL);bt_timer=g_timeout_add_seconds(10,bluetooth_refresh,NULL);
    pulse_loop=pa_glib_mainloop_new(NULL);pulse=pa_context_new(pa_glib_mainloop_get_api(pulse_loop),"Simplepanel system dashboard");
    pa_context_set_state_callback(pulse,audio_state,NULL);if(pa_context_connect(pulse,NULL,PA_CONTEXT_NOFLAGS,NULL)<0)set(volume,"Audio unavailable");
    gtk_window_present(GTK_WINDOW(popup));
    gtk_widget_grab_focus(control_cards[3]);
}
int system_dashboard_main(int duration) {
    cancel=g_cancellable_new();net_previous=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,g_free);
    cpu_model=g_strdup("CPU");char *raw=NULL;
    if(g_file_get_contents("/proc/cpuinfo",&raw,NULL,NULL)){char **lines=g_strsplit(raw,"\n",-1);for(int i=0;lines[i];i++)if(g_str_has_prefix(lines[i],"model name")){char *colon=strchr(lines[i],':');if(colon){g_free(cpu_model);cpu_model=g_strdup(g_strstrip(colon+1));}break;}g_strfreev(lines);g_free(raw);}
    for(gsize i=0;i<dashboard_settings.clocks;i++)timezones[i]=g_time_zone_new_identifier(dashboard_settings.zones[i]);
    application=gtk_application_new("com.go7.Simplepanel.SystemDashboard",G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect(application,"activate",G_CALLBACK(activate_dashboard),NULL);
    g_unix_signal_add(SIGTERM,quit_dashboard,NULL);g_unix_signal_add(SIGINT,quit_dashboard,NULL);
    if(duration>0)g_timeout_add_seconds(duration,quit_dashboard,NULL);
    int result=g_application_run(G_APPLICATION(application),0,NULL);
    simple_market_stop();
    g_cancellable_cancel(cancel);if(fetch_timeout)g_source_remove(fetch_timeout);
    if(fetch_process){g_subprocess_force_exit(fetch_process);g_clear_object(&fetch_process);}
    if(timer)g_source_remove(timer);
    if(bt_timer)g_source_remove(bt_timer);
    if(pulse){pa_context_disconnect(pulse);pa_context_unref(pulse);}if(pulse_loop)pa_glib_mainloop_free(pulse_loop);
    for(gsize i=0;i<dashboard_settings.clocks;i++)g_time_zone_unref(timezones[i]);
    g_hash_table_unref(net_previous);g_free(cpu_model);g_object_unref(application);g_object_unref(cancel);return result;
}
