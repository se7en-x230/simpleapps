#include "sp.h"
#include <errno.h>
#include <stdarg.h>
char *asset_dir, *config_path, *data_dir, *theme_override, *last_error;
J *config;
J *obj(J *j, const char *k) {
  J *v = NULL;
  if (j && json_object_is_type(j, json_type_object))
    json_object_object_get_ex(j, k, &v);
  return v;
}
const char *js(J *j) { return j ? json_object_get_string(j) : ""; }
const char *str(J *j, const char *k) { return js(obj(j, k)); }
int num(J *j, const char *k) { return json_object_get_int(obj(j, k)); }
gboolean yes(J *j, const char *k) { return json_object_get_boolean(obj(j, k)); }
void setstr(J *j, const char *k, const char *v) {
  json_object_object_add(j, k, json_object_new_string(v ? v : ""));
}
void setint(J *j, const char *k, int v) {
  json_object_object_add(j, k, json_object_new_int(v));
}
J *jclone(J *j) {
  return j ? json_tokener_parse(json_object_to_json_string(j)) : NULL;
}
void fail(const char *fmt, ...) {
  va_list ap;
  va_start(ap, fmt);
  g_free(last_error);
  last_error = g_strdup_vprintf(fmt, ap);
  va_end(ap);
}
J *parse_json(const char *text) {
  struct json_tokener *t = json_tokener_new();
  J *j = json_tokener_parse_ex(t, text, strlen(text));
  if (json_tokener_get_error(t) != json_tokener_success) {
    fail("Invalid JSON: %s",
         json_tokener_error_desc(json_tokener_get_error(t)));
    if (j)
      json_object_put(j);
    j = NULL;
  }
  json_tokener_free(t);
  return j;
}
J *read_json(const char *path, const char *fallback) {
  char *text = NULL;
  GError *e = NULL;
  if (!g_file_get_contents(path, &text, NULL, &e)) {
    if (g_error_matches(e, G_FILE_ERROR, G_FILE_ERROR_NOENT) && fallback) {
      g_clear_error(&e);
      return parse_json(fallback);
    }
    fail("%s: %s", path, e->message);
    g_clear_error(&e);
    return NULL;
  }
  J *j = parse_json(text);
  g_free(text);
  return j;
}
gboolean write_json(const char *path, J *j) {
  char *dir = g_path_get_dirname(path);
  g_mkdir_with_parents(dir, 0700);
  g_free(dir);
  GError *e = NULL;
  gboolean ok = g_file_set_contents_full(
      path, json_object_to_json_string_ext(j, JSON_C_TO_STRING_PRETTY), -1,
      G_FILE_SET_CONTENTS_CONSISTENT | G_FILE_SET_CONTENTS_DURABLE, 0600, &e);
  if (!ok) {
    fail("%s", e->message);
    g_clear_error(&e);
  } else if (chmod(path, 0600)) {
    fail("Cannot restrict permissions on %s: %s", path, g_strerror(errno));
    ok = FALSE;
  }
  return ok;
}
char *path_join(const char *a, const char *b) {
  return g_build_filename(a, b, NULL);
}
char *norm(const char *s) {
  char *f = g_utf8_casefold(s ? s : "", -1),
       *d = g_utf8_normalize(f, -1, G_NORMALIZE_NFKD);
  GString *out = g_string_new(NULL);
  if (d)
    for (char *p = d; *p; p = g_utf8_next_char(p)) {
      gunichar c = g_utf8_get_char(p);
      if (!g_unichar_combining_class(c))
        g_string_append_unichar(out, g_unichar_isspace(c) ? ' ' : c);
    }
  g_free(f);
  g_free(d);
  return g_string_free(out, FALSE);
}
gboolean match(const char *normalized, const char *query) {
  char *q = norm(query);
  char **parts = g_strsplit(q, " ", -1);
  gboolean ok = TRUE;
  for (int i = 0; parts[i]; i++)
    if (*parts[i] && !strstr(normalized, parts[i])) {
      ok = FALSE;
      break;
    }
  g_strfreev(parts);
  g_free(q);
  return ok;
}
char *expand(const char *s, J *values) {
  GString *out = g_string_new(NULL);
  if (s[0] == '~' && (s[1] == '/' || !s[1])) {
    g_string_append(out, g_get_home_dir());
    s++;
  }
  while (*s) {
    if (*s == '$') {
      const char *start = s++;
      gboolean brace = *s == '{';
      if (brace)
        s++;
      const char *b = s;
      while (g_ascii_isalnum(*s) || *s == '_')
        s++;
      if (s > b && (!brace || *s == '}')) {
        char *k = g_strndup(b, s - b);
        const char *v = g_getenv(k);
        if (v)
          g_string_append(out, v);
        else
          g_string_append_len(out, start, s - start + (brace ? 1 : 0));
        g_free(k);
        if (brace)
          s++;
      } else
        g_string_append_len(out, start, s - start);
    } else
      g_string_append_c(out, *s++);
  }
  char *env = g_string_free(out, FALSE);
  out = g_string_new(NULL);
  s = env;
  while (*s) {
    if (*s == '{' && strchr(s, '}')) {
      const char *end = strchr(s, '}');
      char *k = g_strndup(s + 1, end - s - 1);
      J *v = obj(values, k);
      g_free(k);
      if (v) {
        g_string_append(out, js(v));
        s = end + 1;
        continue;
      }
    }
    g_string_append_c(out, *s++);
  }
  g_free(env);
  return g_string_free(out, FALSE);
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
J *expand_argv(J *a, J *v) {
  J *out = json_object_new_array();
  for (size_t i = 0; a && i < json_object_array_length(a); i++) {
    char *s = expand(js(json_object_array_get_idx(a, i)), v);
    json_object_array_add(out, json_object_new_string(s));
    g_free(s);
  }
  return out;
}
J *command_argv(const char *k, J *v) {
  J *a = expand_argv(obj(obj(config, "commands"), k), v);
  if (!json_object_array_length(a))
    fail("commands.%s is disabled", k);
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
char *run_text(J *a, const char *input, int timeout) {
  GBytes *b = input ? g_bytes_new(input, strlen(input)) : NULL;
  GBytes *out = run_bytes(a, b, timeout);
  g_clear_pointer(&b, g_bytes_unref);
  if (!out)
    return NULL;
  gsize n;
  const char *s = g_bytes_get_data(out, &n);
  char *text = n ? g_utf8_make_valid(s, n) : g_strdup("");
  g_bytes_unref(out);
  return text;
}
gboolean spawn(J *a) {
  char **v = argv_c(a);
  GError *e = NULL;
  gboolean ok =
      v[0] && g_spawn_async(NULL, v, NULL,
                            G_SPAWN_SEARCH_PATH | G_SPAWN_STDOUT_TO_DEV_NULL |
                                G_SPAWN_STDERR_TO_DEV_NULL,
                            NULL, NULL, NULL, &e);
  if (!ok)
    fail("%s", e ? e->message : "Empty command");
  g_clear_error(&e);
  g_strfreev(v);
  json_object_put(a);
  return ok;
}
gboolean copy_bytes(GBytes *b, const char *mime) {
  J *a = command_argv("copy", NULL);
  if (mime) {
    json_object_array_add(a, json_object_new_string("--type"));
    json_object_array_add(a, json_object_new_string(mime));
  }
  GBytes *out = run_bytes(a, b, 5);
  gboolean ok = out != NULL;
  g_clear_pointer(&out, g_bytes_unref);
  return ok;
}
gboolean copy_text(const char *s) {
  GBytes *b = g_bytes_new(s, strlen(s));
  gboolean ok = copy_bytes(b, NULL);
  g_bytes_unref(b);
  return ok;
}
char *data_path(const char *n) {
  /* Bookmark data belongs to Simplebookmarks; retain old installations and
     explicit Picker data directories until they are migrated. */
  if (g_str_has_prefix(n, "bookmark") && !g_getenv("SIMPLEPICKER_DATA_DIR")) {
    char *dir = g_build_filename(g_get_user_data_dir(), "simplebookmarks", NULL);
    char *current = path_join(dir, "bookmarks.json");
    char *legacy = path_join(data_dir, "bookmarks.json");
    gboolean use_new = g_file_test(current, G_FILE_TEST_EXISTS) || !g_file_test(legacy, G_FILE_TEST_EXISTS);
    char *result = path_join(use_new ? dir : data_dir, n);
    g_free(dir);g_free(current);g_free(legacy);
    return result;
  }
  return path_join(data_dir, n);
}
J *history(const char *n, const char *f) {
  char *p = data_path(n);
  J *j = read_json(p, f);
  g_free(p);
  if (j && !json_object_is_type(j, f && *f == '[' ? json_type_array
                                                  : json_type_object)) {
    fail("Invalid data format: %s", n);
    json_object_put(j);
    return NULL;
  }
  return j;
}
gboolean save_data(const char *n, J *j) {
  char *p = data_path(n);
  gboolean ok = write_json(p, j);
  g_free(p);
  return ok;
}
int data_lock(const char *n) {
  g_mkdir_with_parents(data_dir, 0700);
  char *p = data_path(n);
  char *dir = g_path_get_dirname(p);
  g_mkdir_with_parents(dir, 0700);
  g_free(dir);
  FILE *f = fopen(p, "a");
  g_free(p);
  if (!f) {
    fail("Cannot open data lock");
    return -1;
  }
  int fd = dup(fileno(f));
  fclose(f);
  if (flock(fd, LOCK_EX)) {
    close(fd);
    fail("Cannot lock data");
    return -1;
  }
  return fd;
}
int history_count(J *j, const char *k) {
  J *v = obj(j, k);
  return v && json_object_is_type(v, json_type_int)
             ? MAX(0, json_object_get_int(v))
             : 0;
}
void history_add(const char *n, const char *k) {
  char *stem = g_strdup(n);
  if (g_str_has_suffix(stem, ".json"))
    stem[strlen(stem) - 5] = 0;
  char *lock = g_strdup_printf("%s.lock", stem);
  g_free(stem);
  int fd = data_lock(lock);
  g_free(lock);
  if (fd < 0)
    return;
  J *j = history(n, "{}");
  if (j && json_object_is_type(j, json_type_object)) {
    setint(j, k, MIN(history_count(j, k), G_MAXINT - 1) + 1);
    save_data(n, j);
  }
  if (j)
    json_object_put(j);
  close(fd);
}
