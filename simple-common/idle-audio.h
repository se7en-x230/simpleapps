#ifndef SIMPLE_IDLE_AUDIO_H
#define SIMPLE_IDLE_AUDIO_H
#include <gio/gio.h>
#include <signal.h>
#include <unistd.h>

/* Optional audio is isolated from the UI/authentication process. */
static GSubprocess *simple_idle_audio_start(const char *owner) {
  char *helper=g_build_filename(g_get_user_config_dir(),"simple","idle-audio.py",NULL);
  GSubprocess *child=NULL;
  if(g_file_test(helper,G_FILE_TEST_IS_REGULAR)) {
    char pid[32];g_snprintf(pid,sizeof pid,"%ld",(long)getpid());
    child=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_SILENCE|G_SUBPROCESS_FLAGS_STDERR_SILENCE,
                          NULL,"python3",helper,"--parent",pid,"--owner",owner,NULL);
  }
  g_free(helper);return child;
}
static void simple_idle_audio_stop(GSubprocess **child) {
  if(!*child)return;
  g_subprocess_send_signal(*child,SIGTERM);
  g_clear_object(child);
}
#endif
