#include "sp.h"
#include <poll.h>
static J *read_message(void) {
  struct pollfd fd = {STDIN_FILENO, POLLIN, 0};
  if (poll(&fd, 1, 30000) <= 0) {
    fail("Menu script did not respond within 30 seconds");
    return NULL;
  }
  char *line = NULL;
  size_t n = 0;
  ssize_t len = getline(&line, &n, stdin);
  if (len < 0) {
    free(line);
    fail("Menu script disconnected");
    return NULL;
  }
  J *j = parse_json(line);
  free(line);
  return j;
}
static void send_message(J *j) {
  puts(json_object_to_json_string_ext(j, JSON_C_TO_STRING_PLAIN));
  fflush(stdout);
  json_object_put(j);
}
static J *request(Menu *m, const char *event, Row *r, const char *action) {
  J *q = json_object_new_object();
  setstr(q, "event", event);
  setstr(q, "query", m->query ? m->query : "");
  if (r)
    setstr(q, "id", r->id);
  if (action)
    setstr(q, "action", action);
  send_message(q);
  J *response = read_message();
  if (!response || *str(response, "error")) {
    if (response)
      fail("Menu script: %s", str(response, "error"));
    menu_finish(m, NULL);
  }
  return response;
}
static void bridge_search(Menu *m, const char *q) {
  (void)q;
  J *response = request(m, "search", NULL, NULL);
  if (response && obj(response, "result")) {
    menu_finish(m, str(response, "result"));
    json_object_put(response);
    return;
  }
  rows_clear(m);
  J *rows = obj(response, "rows");
  for (size_t i = 0; rows && i < json_object_array_length(rows); i++) {
    J *r = json_object_array_get_idx(rows, i);
    Row *row = row_new(str(r, "id"), str(r, "label"), str(r, "subtitle"),
                       *str(r, "icon") ? str(r, "icon") : NULL);
    if (*str(r, "gicon"))
      row->gicon = g_icon_new_for_string(str(r, "gicon"), NULL);
    if (*str(r, "font"))
      row->font = g_strdup(str(r, "font"));
    g_ptr_array_add(m->rows, row);
  }
  if (response)
    json_object_put(response);
}
static gboolean bridge_action(Menu *m, Row *r, const char *a) {
  J *response = request(m, "activate", r, a);
  if (!response)
    return FALSE;
  gboolean keep = yes(response, "keep");
  if (obj(response, "query"))
    gtk_editable_set_text(GTK_EDITABLE(m->entry), str(response, "query"));
  if (obj(response, "result")) {
    menu_finish(m, str(response, "result"));
    keep = FALSE;
  } else if (yes(response, "close")) {
    menu_finish(m, NULL);
    keep = FALSE;
  }
  json_object_put(response);
  return keep;
}
static void bridge_preview(Menu *m, Row *r) {
  J *response = request(m, "preview", r, NULL);
  if (response) {
    if (obj(response, "text"))
      menu_set_text_preview(m, str(response, "text"));
    else if (obj(response, "image")) {
      gsize n;
      guchar *b = g_base64_decode(str(response, "image"), &n);
      GBytes *bytes = g_bytes_new_take(b, n);
      menu_set_image_preview(m, bytes);
      g_bytes_unref(bytes);
    }
    json_object_put(response);
  }
}
int bridge_main(
    void) { /* Unbuffered input keeps poll() consistent with getline(). */
  setvbuf(stdin, NULL, _IONBF, 0);
  J *init = read_message();
  if (!init)
    return 2;
  Menu *m = menu_new(str(init, "title"), str(init, "prompt"));
  m->keys_path = *str(init,"keys") ? str(init,"keys") : NULL;
  m->key_scope = *str(init,"key_scope") ? str(init,"key_scope") : NULL;
  m->input = yes(init, "input_only");
  m->password = yes(init, "password");
  m->width = num(init, "width") ? num(init, "width") : 600;
  m->height = num(init, "height") ? num(init, "height") : 570;
  m->icon_size = num(init, "icon_size") ? num(init, "icon_size") : 24;
  m->selected = MAX(0, num(init, "selected_row"));
  m->initial = str(init, "initial");
  m->icon = *str(init, "icon") ? str(init, "icon") : "view-list-symbolic";
  m->theme = *str(init, "theme") ? str(init, "theme") : NULL;
  m->sample = *str(init, "sample") ? str(init, "sample") : NULL;
  m->font_rows = yes(init, "font_rows");
  m->previews = yes(init, "previews");
  if (m->previews)
    m->preview = bridge_preview;
  m->search = bridge_search;
  m->activate = bridge_action;
  J *shortcuts = obj(init, "shortcuts");
  if (shortcuts) {
    json_object_object_foreach(shortcuts, k, v) { menu_shortcut(m, k, js(v)); }
  }
  menu_show(m);
  J *out = json_object_new_object();
  setstr(out, "event", "closed");
  if (m->result)
    setstr(out, "result", m->result);
  if (last_error)
    setstr(out, "error", last_error);
  send_message(out);
  menu_free(m);
  json_object_put(init);
  return last_error ? 2 : 0;
}
