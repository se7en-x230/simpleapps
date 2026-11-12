#define _GNU_SOURCE
#include "panel-modules.h"
#include <signal.h>
#include <unistd.h>
#include <string.h>
#include <stdlib.h>

#define MODULE_LIMIT 32
#define OUTPUT_LIMIT 4096

typedef struct Custom Custom;
typedef struct {
    Custom *owner;
    GSubprocess *process;
    GString *output;
    guint timeout;
    pid_t group;
    gboolean read_done, wait_done, failed, click;
} Run;
struct Custom {
    char *name, *command, *click;
    int interval, timeout, width;
    GtkWidget *label;
    guint timer;
    Run *run, *action;
};
static Custom modules[MODULE_LIMIT];
static guint module_count;
static char **layout[3], *environment, *config_file;
static gboolean stopping;
static const char *builtins[]={"workspaces","window-title","music","clock","network","volume","battery","phone",NULL};

static gboolean invalid(GError **error,const char *message,const char *name) {
    g_set_error(error,G_KEY_FILE_ERROR,G_KEY_FILE_ERROR_INVALID_VALUE,"%s: %s",name,message);
    return FALSE;
}
static Custom *custom(const char *name) {
    for(guint i=0;i<module_count;i++)if(!strcmp(modules[i].name,name))return &modules[i];
    return NULL;
}
static gboolean builtin(const char *name) {
    return g_strv_contains(builtins,name);
}
static gboolean valid_name(const char *name) {
    if(!*name||strlen(name)>48)return FALSE;
    for(const char *p=name;*p;p++)if(!g_ascii_isalnum(*p)&&*p!='-'&&*p!='_')return FALSE;
    return TRUE;
}
static int number(GKeyFile *file,const char *group,const char *key,int fallback,int max,GError **error) {
    if(!g_key_file_has_key(file,group,key,NULL))return fallback;
    GError *local=NULL;
    int n=g_key_file_get_integer(file,group,key,&local);
    if(local||n<1||n>max) {
        g_clear_error(&local);invalid(error,"expected a positive integer within the documented limit",group);return -1;
    }
    return n;
}
gboolean panel_modules_load(GKeyFile *file,const char *path,GError **error) {
    config_file=g_strdup(path);
    environment=g_key_file_get_string(file,"panel","environment",NULL);
    if(!environment)environment=g_strdup("auto");
    const char *choices[]={"auto","mango","hyprland","sway","generic",NULL};
    if(!g_strv_contains(choices,environment))return invalid(error,"use auto, mango, hyprland, sway or generic","panel.environment");
    if(!strcmp(environment,"auto")) {
        char *desktop=g_ascii_strdown(g_getenv("XDG_CURRENT_DESKTOP")?g_getenv("XDG_CURRENT_DESKTOP"):"",-1);
        const char *detected=g_getenv("MANGO_INSTANCE_SIGNATURE")||strstr(desktop,"mango")?"mango":
            g_getenv("HYPRLAND_INSTANCE_SIGNATURE")||strstr(desktop,"hyprland")?"hyprland":
            g_getenv("SWAYSOCK")||strstr(desktop,"sway")?"sway":"generic";
        g_free(environment);environment=g_strdup(detected);g_free(desktop);
    }
    gsize count=0;char **groups=g_key_file_get_groups(file,&count);
    for(gsize i=0;i<count;i++) {
        if(!g_str_has_prefix(groups[i],"custom."))continue;
        const char *name=groups[i]+7;
        if(module_count==MODULE_LIMIT||!valid_name(name)||builtin(name)) {
            g_strfreev(groups);return invalid(error,"invalid/reserved name or more than 32 modules","custom module");
        }
        Custom *m=&modules[module_count++];m->name=g_strdup(name);
        m->command=g_key_file_get_string(file,groups[i],"command",NULL);
        m->click=g_key_file_get_string(file,groups[i],"on_click",NULL);
        if(!m->command||!*g_strstrip(m->command)) {invalid(error,"command is required",name);g_strfreev(groups);return FALSE;}
        m->interval=number(file,groups[i],"interval",60,86400,error);
        if(m->interval<0){g_strfreev(groups);return FALSE;}
        m->timeout=number(file,groups[i],"timeout",5,300,error);
        if(m->timeout<0){g_strfreev(groups);return FALSE;}
        m->width=number(file,groups[i],"max_chars",24,200,error);
        if(m->width<0){g_strfreev(groups);return FALSE;}
    }
    g_strfreev(groups);
    /* Old personal configs still work, but investment is now a subprocess module. */
    gboolean legacy=g_key_file_get_boolean(file,"panel","invest",NULL);
    if(legacy&&!custom("invest")) {
        if(module_count==MODULE_LIMIT)return invalid(error,"no room for legacy invest module","panel.invest");
        Custom *m=&modules[module_count++];m->name=g_strdup("invest");
        const char *override=g_getenv("SIMPLEPANEL_INVEST_COMMAND");
        m->command=override?g_shell_quote(override):g_strdup("simplepanel --market-summary");
        m->interval=3600;m->timeout=10;m->width=24;
    }
    const char *defaults[]={"workspaces;window-title;","music;clock;",legacy?"network;volume;invest;battery;phone;":"network;volume;battery;phone;"};
    const char *sections[]={"left","center","right"};
    GHashTable *seen=g_hash_table_new(g_str_hash,g_str_equal);
    for(int i=0;i<3;i++) {
        char *value=g_key_file_get_string(file,"layout",sections[i],NULL);
        layout[i]=g_strsplit(value?value:defaults[i],";",-1);g_free(value);
        for(char **p=layout[i];*p;p++) {
            g_strstrip(*p);if(!**p)continue;
            if((!builtin(*p)&&!custom(*p))||g_hash_table_contains(seen,*p)) {
                invalid(error,"unknown or duplicate module",*p);g_hash_table_unref(seen);return FALSE;
            }
            g_hash_table_add(seen,*p);
        }
    }
    g_hash_table_unref(seen);return TRUE;
}
const char *panel_environment(void) {return environment;}
gboolean panel_module_enabled(const char *name) {
    for(int i=0;i<3;i++)if(g_strv_contains((const char * const *)layout[i],name))return TRUE;
    return FALSE;
}
static void kill_run(Run *r) {
    if(r->group>0)kill(-r->group,SIGKILL);
    if(!r->wait_done)g_subprocess_force_exit(r->process);
    r->failed=TRUE;
}
static gboolean timed_out(gpointer data) {
    Run *r=data;r->timeout=0;kill_run(r);return G_SOURCE_REMOVE;
}
static void finish(Run *r) {
    if(!r->read_done||!r->wait_done)return;
    if(r->timeout)g_source_remove(r->timeout);
    Custom *m=r->owner;
    if(!stopping&&!r->click) {
        if(!r->failed) {
            char *valid=g_utf8_make_valid(r->output->str,r->output->len);
            char *tip=strchr(valid,'\n');if(tip)*tip++='\0';
            gtk_label_set_text(GTK_LABEL(m->label),g_strstrip(valid));
            gtk_widget_set_tooltip_text(m->label,tip&&*tip?g_strstrip(tip):valid);g_free(valid);
        } else gtk_widget_set_tooltip_text(m->label,"Module failed, exceeded 4096 bytes, or timed out; keeping last value.");
    }
    if(r->click)m->action=NULL;else m->run=NULL;
    g_object_unref(r->process);g_string_free(r->output,TRUE);g_free(r);
}
static void waited(GObject *source,GAsyncResult *result,gpointer data) {
    Run *r=data;
    if(!g_subprocess_wait_check_finish(G_SUBPROCESS(source),result,NULL))r->failed=TRUE;
    r->wait_done=TRUE;finish(r);
}
static void read_output(GObject *source,GAsyncResult *result,gpointer data) {
    Run *r=data;GBytes *bytes=g_input_stream_read_bytes_finish(G_INPUT_STREAM(source),result,NULL);
    gsize length=bytes?g_bytes_get_size(bytes):0;
    if(!bytes)r->failed=TRUE;
    if(length&&r->output->len+length<=OUTPUT_LIMIT) {
        g_string_append_len(r->output,g_bytes_get_data(bytes,NULL),length);
        g_input_stream_read_bytes_async(G_INPUT_STREAM(source),512,G_PRIORITY_DEFAULT,NULL,read_output,r);
    } else {
        if(length)kill_run(r);
        r->read_done=TRUE;
    }
    if(bytes)g_bytes_unref(bytes);
    finish(r);
}
static void child_group(gpointer unused) {setsid();}
static void launch(Custom *m,gboolean click) {
    if(stopping||(click?m->action:m->run))return;
    GSubprocessLauncher *launcher=g_subprocess_launcher_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_SILENCE);
    g_subprocess_launcher_set_child_setup(launcher,child_group,NULL,NULL);
    g_subprocess_launcher_setenv(launcher,"SIMPLEPANEL_CONFIG",config_file,TRUE);
    g_subprocess_launcher_setenv(launcher,"SIMPLEPANEL_ENVIRONMENT",environment,TRUE);
    GError *error=NULL;
    GSubprocess *process=g_subprocess_launcher_spawn(launcher,&error,"/bin/sh","-c",click?m->click:m->command,NULL);
    g_object_unref(launcher);
    if(!process) {gtk_widget_set_tooltip_text(m->label,error->message);g_clear_error(&error);return;}
    Run *r=g_new0(Run,1);r->owner=m;r->click=click;r->process=process;r->output=g_string_new(NULL);
    r->group=(pid_t)g_ascii_strtoll(g_subprocess_get_identifier(process),NULL,10);
    if(click)m->action=r;else m->run=r;
    r->timeout=g_timeout_add_seconds(m->timeout,timed_out,r);
    g_input_stream_read_bytes_async(g_subprocess_get_stdout_pipe(process),512,G_PRIORITY_DEFAULT,NULL,read_output,r);
    g_subprocess_wait_check_async(process,NULL,waited,r);
}
static gboolean refresh(gpointer data) {launch(data,FALSE);return G_SOURCE_CONTINUE;}
static void clicked(GtkGestureClick *gesture,int n,double x,double y,gpointer data) {
    gtk_gesture_set_state(GTK_GESTURE(gesture),GTK_EVENT_SEQUENCE_CLAIMED);launch(data,TRUE);
}
void panel_modules_layout(GtkWidget **sections,const char **names,GtkWidget **widgets,gsize count,gboolean demo,GCallback default_click) {
    for(gsize i=0;i<count;i++)g_object_ref_sink(widgets[i]);
    for(int section=0;section<3;section++)for(char **p=layout[section];*p;p++) {
        if(!**p)continue;
        Custom *m=custom(*p);
        if(m) {
            m->label=gtk_label_new(demo?m->name:"…");
            gtk_label_set_max_width_chars(GTK_LABEL(m->label),m->width);
            gtk_label_set_ellipsize(GTK_LABEL(m->label),PANGO_ELLIPSIZE_END);
            gtk_widget_add_css_class(m->label,"custom-module");gtk_widget_add_css_class(m->label,m->name);
            if(m->click&&!demo) {
                GtkGesture *gesture=gtk_gesture_click_new();
                g_signal_connect(gesture,"pressed",G_CALLBACK(clicked),m);gtk_widget_add_controller(m->label,GTK_EVENT_CONTROLLER(gesture));
            }
            if(!m->click&&!demo&&default_click) {
                GtkGesture *gesture=gtk_gesture_click_new();
                g_signal_connect(gesture,"pressed",default_click,NULL);gtk_widget_add_controller(m->label,GTK_EVENT_CONTROLLER(gesture));
            }
            gtk_box_append(GTK_BOX(sections[section]),m->label);
        } else for(gsize i=0;i<count;i++)if(!strcmp(*p,names[i])) {
            if(strcmp(environment,"mango")&&(!strcmp(*p,"workspaces")||!strcmp(*p,"window-title")))break;
            gtk_box_append(GTK_BOX(sections[section]),widgets[i]);break;
        }
    }
    for(int i=0;i<3;i++)gtk_widget_set_visible(sections[i],gtk_widget_get_first_child(sections[i])!=NULL);
    /* Keep omitted builtins alive: their callbacks may still hold widget pointers. */
}
void panel_modules_start(void) {
    for(guint i=0;i<module_count;i++)if(modules[i].label) {
        refresh(&modules[i]);modules[i].timer=g_timeout_add_seconds(modules[i].interval,refresh,&modules[i]);
    }
}
void panel_modules_stop(void) {
    stopping=TRUE;
    for(guint i=0;i<module_count;i++) {
        Custom *m=&modules[i];if(m->timer){g_source_remove(m->timer);m->timer=0;}
        if(m->run)kill_run(m->run);
        if(m->action)kill_run(m->action);
    }
}
