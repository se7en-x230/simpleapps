#include "lock.h"
#include <stdarg.h>
char *config_path, *last_error;
const char *js(J *j){return j?json_object_get_string(j):"";}
void fail(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  g_free(last_error);
  last_error = g_strdup_vprintf(fmt, ap);
  va_end(ap);
}
J *argv_json(const char *first, ...) {
  J *a = json_object_new_array();
  va_list ap;
  va_start(ap, first);
  for (const char *s = first; s; s = va_arg(ap, const char *))
    json_object_array_add(a, json_object_new_string(s));
  va_end(ap);
  return a;
}
static char **argv_c(J *a) {
  size_t n = a ? json_object_array_length(a) : 0;
  char **v = g_new0(char *, n + 1);
  for (size_t i = 0; i < n; i++)
    v[i] = g_strdup(js(json_object_array_get_idx(a, i)));
  return v;
}
static gboolean timeout_cancel(gpointer p) {
  g_cancellable_cancel(p);
  return G_SOURCE_REMOVE;
}
typedef struct {
  GMainLoop *loop;
  GBytes *out, *err;
  GError *error;
  gboolean ok;
} Wait;
static void communicated(GObject *p, GAsyncResult *r, gpointer data) {
  Wait *w = data;
  w->ok = g_subprocess_communicate_finish(G_SUBPROCESS(p), r, &w->out, &w->err,
                                          &w->error);
  g_main_loop_quit(w->loop);
}
GBytes *run_bytes(J *a, GBytes *input, int timeout) {
  char **argv = argv_c(a);
  if (!argv[0]) {
    fail("Empty command");
    g_strfreev(argv);
    json_object_put(a);
    return NULL;
  }
  GError *e = NULL;
  GSubprocess *p = g_subprocess_newv((const char *const *)argv,
                                     G_SUBPROCESS_FLAGS_STDIN_PIPE |
                                         G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                                         G_SUBPROCESS_FLAGS_STDERR_PIPE,
                                     &e);
  g_strfreev(argv);
  json_object_put(a);
  if (!p) {
    fail("%s", e->message);
    g_clear_error(&e);
    return NULL;
  }
  GCancellable *c = g_cancellable_new();
  Wait w = {.loop = g_main_loop_new(NULL, FALSE)};
  guint timer =
      g_timeout_add_seconds(timeout > 0 ? timeout : 10, timeout_cancel, c);
  GBytes *send = input ? g_bytes_ref(input) : g_bytes_new_static("", 0);
  g_subprocess_communicate_async(p, send, c, communicated, &w);
  g_bytes_unref(send);
  g_main_loop_run(w.loop);
  if (!g_cancellable_is_cancelled(c))
    g_source_remove(timer);
  if (!w.ok || !g_subprocess_get_successful(p)) {
    if (g_cancellable_is_cancelled(c)) {
      g_subprocess_force_exit(p);
      fail("Command timed out");
    } else if (w.error)
      fail("%s", w.error->message);
    else {
      gsize n;
      const char *t = g_bytes_get_data(w.err, &n);
      fail("Command failed: %.*s", (int)MIN(n, 2000), t);
    }
    g_clear_pointer(&w.out, g_bytes_unref);
  }
  g_clear_error(&w.error);
  g_clear_pointer(&w.err, g_bytes_unref);
  g_main_loop_unref(w.loop);
  g_object_unref(c);
  g_object_unref(p);
  return w.out;
}
