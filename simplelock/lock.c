#include "lock.h"
#include "auth.h"
#include "../simple-common/idle-audio.h"
static GSubprocess *idle_audio;
#include <pwd.h>
#include <security/pam_appl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/resource.h>
#include <errno.h>
#include <signal.h>

GHashTable *backdrops;
char *lock_user;
gboolean auth_busy, lock_visualizer=TRUE;
static char *pam_service;
static char *lock_playing_image,*lock_idle_image,*lock_album_idle_image;
static GtkSessionLockInstance *lock_instance;
static GMainLoop *lock_loop;
static int exit_status=1, ready_fd=-1;
static gboolean acquired;
#include "view.c"

typedef struct {size_t bytes;char password[];} Attempt;
static void attempt_free(gpointer data) {
  Attempt *a=data;size_t n=a->bytes;explicit_bzero(a,n);munlock(a,n);g_free(a);
}
static void feedback(const char *message,gboolean sensitive) {
  for(guint i=0;i<views->len;i++) {
    Dashboard *d=g_ptr_array_index(views,i);if(d->m->closed)continue;
    gtk_label_set_text(GTK_LABEL(d->feedback),message);
    gtk_widget_set_sensitive(d->entry,sensitive);
    if(sensitive)gtk_widget_grab_focus(d->entry);
  }
}
static void auth_worker(GTask *task,gpointer source,gpointer data,GCancellable *cancel) {
  (void)source;(void)cancel;Attempt *a=data;
  int result=authenticate(pam_service,lock_user,a->password);
  explicit_bzero(a->password,a->bytes-sizeof(*a));
  g_task_return_int(task,result);
}
static void auth_ready(GObject *source,GAsyncResult *result,gpointer unused) {
  (void)source;(void)unused;auth_busy=FALSE;
  int status=g_task_propagate_int(G_TASK(result),NULL);
#ifdef SIMPLELOCK_TEST
  g_printerr("TEST auth result %d\n",status);
#endif
  if(status==PAM_SUCCESS && acquired && gtk_session_lock_instance_is_locked(lock_instance)) {
    gtk_session_lock_instance_unlock(lock_instance);
  } else feedback("Could not unlock. Check your password and try again.",TRUE);
}
static void submit(GtkWidget *entry,gpointer data) {
  (void)data;if(auth_busy || !acquired)return;
#ifdef SIMPLELOCK_TEST
  g_printerr("TEST submit\n");
#endif
  const char *text=gtk_editable_get_text(GTK_EDITABLE(entry));
  size_t length=strlen(text);if(!length)return;
  if(length>4096){gtk_editable_set_text(GTK_EDITABLE(entry),"");return;}
  Attempt *a=g_malloc0(sizeof(*a)+length+1);a->bytes=sizeof(*a)+length+1;
  mlock(a,a->bytes);memcpy(a->password,text,length);
  for(guint i=0;i<views->len;i++) {
    Dashboard *d=g_ptr_array_index(views,i);if(!d->m->closed)gtk_editable_set_text(GTK_EDITABLE(d->entry),"");
  }
  auth_busy=TRUE;feedback("Checking password…",FALSE);
  GTask *task=g_task_new(NULL,NULL,auth_ready,NULL);g_task_set_task_data(task,a,attempt_free);
  g_task_run_in_thread(task,auth_worker);g_object_unref(task);
}
static void focus_password(Dashboard *d) {
  /* GtkPasswordEntry selects all on focus; restore the existing insertion point. */
  int position=gtk_editable_get_position(GTK_EDITABLE(d->entry));
  gtk_widget_grab_focus(d->entry);
  gtk_editable_set_position(GTK_EDITABLE(d->entry),position);
}
static gboolean lock_key(GtkEventControllerKey *controller,guint key,guint code,GdkModifierType mods,gpointer data) {
  (void)controller;(void)code;Dashboard *d=data;
  if(auth_busy)return TRUE;
  GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(d->m->window));
  gboolean calendar=focus && (focus==d->calendar || gtk_widget_is_ancestor(focus,d->calendar));
  GdkModifierType modifiers=mods & (GDK_SHIFT_MASK|GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK|GDK_META_MASK);
  if((key==GDK_KEY_Tab || key==GDK_KEY_ISO_Left_Tab) && !(modifiers & ~GDK_SHIFT_MASK)) {
    if(calendar)focus_password(d);else gtk_widget_grab_focus(d->calendar);
#ifdef SIMPLELOCK_TEST
    GtkWidget *target=gtk_window_get_focus(GTK_WINDOW(d->m->window));
    g_printerr("TEST focus %s\n",target && (target==d->calendar || gtk_widget_is_ancestor(target,d->calendar))?"calendar":"password");
#endif
    return TRUE;
  }
  if(key==GDK_KEY_Escape) {
    if(calendar)focus_password(d);
    else gtk_editable_set_text(GTK_EDITABLE(d->entry),"");
    return TRUE;
  }
  /* Calendar input never reaches the password or submits authentication. */
  if(calendar){
    simple_calendar_key(GTK_CALENDAR(d->calendar),key,mods);
#ifdef SIMPLELOCK_TEST
    GDateTime *selected=gtk_calendar_get_date(GTK_CALENDAR(d->calendar));
    char *day=g_date_time_format(selected,"%F");g_printerr("TEST calendar %s\n",day);
    g_free(day);g_date_time_unref(selected);
#endif
    return TRUE;
  }
  if(!focus || (focus!=d->entry && !gtk_widget_is_ancestor(focus,d->entry)))gtk_widget_grab_focus(d->entry);
  return FALSE;
}
static void notify_parent(char status) {
  if(ready_fd>=0){ssize_t result;do{result=write(ready_fd,&status,1);}while(result<0 && errno==EINTR);close(ready_fd);ready_fd=-1;}
}
static void locked(GtkSessionLockInstance *instance,gpointer data) {
  (void)instance;(void)data;acquired=TRUE;notify_parent('1');
  if(!idle_audio)idle_audio=simple_idle_audio_start("lockscreen");
  g_print("Session locked\n");
}
static void failed(GtkSessionLockInstance *instance,gpointer data) {
  (void)instance;(void)data;g_printerr("Could not acquire session lock; no replacement lock was installed.\n");
  notify_parent('0');exit_status=1;g_main_loop_quit(lock_loop);
}
static void unlocked(GtkSessionLockInstance *instance,gpointer data) {
  (void)instance;(void)data;acquired=FALSE;simple_idle_audio_stop(&idle_audio);exit_status=0;g_main_loop_quit(lock_loop);
}
static gboolean read_config(const char *path) {
  pam_service=g_strdup("login");
  lock_playing_image=g_strdup("images/profile.png");lock_idle_image=g_strdup("images/no-playing.png");
  lock_album_idle_image=g_strdup("images/album-idle.png");
  FILE *file=fopen(path,"r");if(!file)return errno==ENOENT;
  char error[256];toml_table_t *root=toml_parse_file(file,error,sizeof error);fclose(file);
  if(!root){g_printerr("Invalid lock.toml: %s\n",error);return FALSE;}
  toml_table_t *section=toml_table_in(root,"lock");
  if(section) {
    toml_datum_t service=toml_string_in(section,"pam_service");
    if(service.ok) {
      gboolean valid=*service.u.s!=0;
      for(char *c=service.u.s;*c;c++)if(!g_ascii_isalnum(*c) && *c!='-' && *c!='_')valid=FALSE;
      if(!valid){g_printerr("Invalid PAM service name\n");free(service.u.s);toml_free(root);return FALSE;}
      g_free(pam_service);pam_service=service.u.s;
    } else if(toml_raw_in(section,"pam_service")){toml_free(root);return FALSE;}
    const char *keys[]={"playing_image","idle_image","album_idle_image"};
    char **images[]={&lock_playing_image,&lock_idle_image,&lock_album_idle_image};
    for(int i=0;i<3;i++) {
      toml_datum_t image=toml_string_in(section,keys[i]);
      if(image.ok){g_free(*images[i]);*images[i]=image.u.s;}
      else if(toml_raw_in(section,keys[i])){toml_free(root);return FALSE;}
    }
    toml_datum_t visualizer=toml_bool_in(section,"visualizer");
    if(visualizer.ok)lock_visualizer=visualizer.u.b;
    else if(toml_raw_in(section,"visualizer")){toml_free(root);return FALSE;}
  }
  toml_free(root);return TRUE;
}

int main(int argc,char **argv) {
  setlocale(LC_ALL,"");
  gboolean daemon=FALSE,check=FALSE;char *cfg=NULL;
  GOptionEntry options[]={
    {"daemonize",'f',0,G_OPTION_ARG_NONE,&daemon,"Return after the compositor confirms the lock",NULL},
    {"config",0,0,G_OPTION_ARG_FILENAME,&cfg,"Lock config TOML","FILE"},
    {"check-config",0,0,G_OPTION_ARG_NONE,&check,"Validate config without locking",NULL},
    {NULL}};
  GOptionContext *context=g_option_context_new("— Simplepicker-style Wayland session locker");
  g_option_context_add_main_entries(context,options,NULL);GError *error=NULL;
  if(!g_option_context_parse(context,&argc,&argv,&error)){g_printerr("%s\n",error->message);return 2;}
  if(argc!=1){g_printerr("Unexpected argument\n");return 2;}
  const char *env_config=g_getenv("SIMPLELOCK_CONFIG");
  config_path=cfg?g_strdup(cfg):env_config?g_strdup(env_config):g_build_filename(g_get_user_config_dir(),"simplelock","config.toml",NULL);
  char *resolved=realpath(config_path,NULL);if(resolved){g_free(config_path);config_path=resolved;}
  if(!read_config(config_path)){g_printerr("Lock configuration invalid\n");return 2;}
#ifndef SIMPLELOCK_TEST
  char *service_path=g_build_filename("/etc/pam.d",pam_service,NULL);
  if(!g_file_test(service_path,G_FILE_TEST_IS_REGULAR)){g_printerr("Missing PAM service: %s\n",service_path);return 2;}g_free(service_path);
#endif
  if(check){g_print("Lock config valid; PAM service: %s\n",pam_service);return 0;}
  struct passwd *pw=getpwuid(getuid());if(!pw || !*pw->pw_name)return 2;lock_user=g_strdup(pw->pw_name);
  struct rlimit no_core={0,0};if(setrlimit(RLIMIT_CORE,&no_core) || prctl(PR_SET_DUMPABLE,0)){perror("Password memory protection");return 2;}
  signal(SIGPIPE,SIG_IGN);
  if(daemon){int pipefd[2];if(pipe2(pipefd,O_CLOEXEC))return 2;pid_t pid=fork();if(pid<0)return 2;
    if(pid){close(pipefd[1]);char byte=0;ssize_t n;do{n=read(pipefd[0],&byte,1);}while(n<0&&errno==EINTR);close(pipefd[0]);return n==1&&byte=='1'?0:1;}
    close(pipefd[0]);ready_fd=pipefd[1];if(setsid()<0)return 2;
    int nullfd=open("/dev/null",O_RDWR);if(nullfd>=0){dup2(nullfd,STDIN_FILENO);dup2(nullfd,STDOUT_FILENO);dup2(nullfd,STDERR_FILENO);if(nullfd>2)close(nullfd);}
  }
  g_setenv("GDK_BACKEND","wayland",TRUE);
  if(!gtk_init_check() || !gtk_session_lock_is_supported()){g_printerr("Wayland session-lock unavailable\n");notify_parent('0');return 2;}
  backdrops=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,g_object_unref);views=g_ptr_array_new();
  load_idle_caption();

  lock_loop=g_main_loop_new(NULL,FALSE);lock_instance=gtk_session_lock_instance_new();
  g_signal_connect(lock_instance,"monitor",G_CALLBACK(monitor_added),NULL);
  g_signal_connect(lock_instance,"locked",G_CALLBACK(locked),NULL);
  g_signal_connect(lock_instance,"failed",G_CALLBACK(failed),NULL);
  g_signal_connect(lock_instance,"unlocked",G_CALLBACK(unlocked),NULL);
  if(gtk_session_lock_instance_lock(lock_instance))g_main_loop_run(lock_loop);
  simple_idle_audio_stop(&idle_audio);
  for(guint i=0;i<views->len;i++) {
    Dashboard *d=g_ptr_array_index(views,i);
    if(!d->m->closed){view_destroy(NULL,d);gtk_window_destroy(GTK_WINDOW(d->m->window));}
    while(d->busy)g_main_context_iteration(NULL,TRUE);
    g_object_unref(d->cancel);g_free(d->art);g_free(d->m);g_free(d);
  }
  g_ptr_array_unref(views);g_hash_table_unref(backdrops);notify_parent('0');return exit_status;
}
