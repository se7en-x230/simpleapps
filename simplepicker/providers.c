#include "sp.h"
static int order(gconstpointer aa, gconstpointer bb) {
  Row *a = *(Row *const *)aa, *b = *(Row *const *)bb;
  if (a->quality != b->quality)
    return a->quality - b->quality;
  if (a->rank != b->rank)
    return b->rank - a->rank;
  char *x = g_utf8_casefold(a->label, -1), *y = g_utf8_casefold(b->label, -1);
  int c = strcmp(x, y);
  g_free(x);
  g_free(y);
  return c;
}
static void free_json(gpointer p) { json_object_put(p); }
static char *ask(const char *prompt, const char *initial, const char *icon) {
  Menu *m = menu_new("Simplepicker C", prompt);
  m->input = TRUE;
  m->initial = initial;
  m->icon = icon;
  char *s = g_strdup(menu_show(m));
  menu_free(m);
  return s;
}
static gboolean actions_request(Menu *m, Row *r, const char *a) {
  (void)r;
  return !strcmp(a, "a") && !menu_selected(m);
}
static void apps_search(Menu *m, const char *q) {
  GPtrArray *all = m->userdata;
  rows_clear(m);
  for (guint i = 0; i < all->len; i++) {
    Row *source = g_ptr_array_index(all, i);
    if (!match(source->terms, q))
      continue;
    Row *r = row_new(source->id, source->label, source->sub, NULL);
    r->gicon = source->gicon ? g_object_ref(source->gicon) : NULL;
    r->data = g_object_ref(source->data);
    r->destroy = g_object_unref;
    r->rank = source->rank;
    char *name = norm(g_app_info_get_display_name(r->data));
    r->quality = !match(name, q);
    g_free(name);
    g_ptr_array_add(m->rows, r);
  }
  g_ptr_array_sort(m->rows, order);
}
static int apps(void) {
  Menu *m = menu_new("Applications", "Search applications…");
  m->icon = "application-x-executable";
  GPtrArray *all = g_ptr_array_new_with_free_func(row_free);
  J *h = history("app-history.json", "{}");
  if (!h) {
    menu_free(m);
    g_ptr_array_unref(all);
    return 2;
  }
  GList *apps = g_app_info_get_all();
  for (GList *l = apps; l; l = l->next) {
    GAppInfo *app = l->data;
    if (!g_app_info_should_show(app))
      continue;
    const char *id = g_app_info_get_id(app);
    if (!id)
      id = g_app_info_get_executable(app);
    char *stem = g_strdup(id ? id : "unknown");
    if (g_str_has_suffix(stem, ".desktop"))
      stem[strlen(stem) - 8] = 0;
    char *label =
        g_strdup_printf("%s  [%s]", g_app_info_get_display_name(app), stem);
    g_free(stem);
    GString *sub = g_string_new(NULL), *terms = g_string_new(label);
    g_string_append_printf(
        terms, " %s %s",
        g_app_info_get_description(app) ? g_app_info_get_description(app) : "",
        g_app_info_get_executable(app) ? g_app_info_get_executable(app) : "");
    if (G_IS_DESKTOP_APP_INFO(app)) {
      const char *const *keywords =
          g_desktop_app_info_get_keywords(G_DESKTOP_APP_INFO(app));
      for (int i = 0; keywords && keywords[i]; i++)
        g_string_append_printf(terms, " %s", keywords[i]);
      const char *const *actions =
          g_desktop_app_info_list_actions(G_DESKTOP_APP_INFO(app));
      for (int i = 0; actions && actions[i]; i++) {
        char *n = g_desktop_app_info_get_action_name(G_DESKTOP_APP_INFO(app),
                                                     actions[i]);
        if (i)
          g_string_append(sub, " · ");
        g_string_append(sub, n);
        g_free(n);
      }
    }
    Row *r = row_new(id ? id : label, label, sub->str, NULL);
    g_free(r->terms);
    r->terms = norm(terms->str);
    r->data = g_object_ref(app);
    r->destroy = g_object_unref;
    GIcon *ic = g_app_info_get_icon(app);
    if (ic)
      r->gicon = g_object_ref(ic);
    r->rank = history_count(h, r->id);
    g_ptr_array_add(all, r);
    g_free(label);
    g_string_free(sub, TRUE);
    g_string_free(terms, TRUE);
  }
  g_list_free_full(apps, g_object_unref);
  json_object_put(h);
  m->userdata = all;
  m->search = apps_search;
  m->activate = actions_request;
  menu_shortcut(m, "a", "App actions");
  char *s = menu_show(m);
  Row *r = s ? menu_find(m, s) : NULL;
  if (r) {
    GAppInfo *app = g_object_ref(r->data);
    gboolean launched = FALSE;
    if (!strcmp(m->action ? m->action : "", "a")) {
      Menu *actions = menu_new("App actions", g_app_info_get_display_name(app));
      const char *const *names =
          G_IS_DESKTOP_APP_INFO(app)
              ? g_desktop_app_info_list_actions(G_DESKTOP_APP_INFO(app))
              : NULL;
      for (int i = 0; names && names[i]; i++) {
        char *label = g_desktop_app_info_get_action_name(
            G_DESKTOP_APP_INFO(app), names[i]);
        Row *ar = row_new(names[i], label, NULL, NULL);
        GIcon *ic = g_app_info_get_icon(app);
        if (ic)
          ar->gicon = g_object_ref(ic);
        g_ptr_array_add(actions->rows, ar);
        g_free(label);
      }
      char *a = menu_show(actions);
      if (a) {
        g_desktop_app_info_launch_action(G_DESKTOP_APP_INFO(app), a, NULL);
        launched = TRUE;
      }
      menu_free(actions);
    } else {
      GError *e = NULL;
      launched = g_app_info_launch(app, NULL, NULL, &e);
      if (!launched) {
        fail("%s", e->message);
        g_clear_error(&e);
      }
    }
    if (launched)
      history_add("app-history.json", s);
    g_object_unref(app);
  }
  menu_free(m);
  g_ptr_array_unref(all);
  return last_error ? 2 : 0;
}
static void runner_search(Menu *m, const char *q) {
  GPtrArray *all = m->userdata;
  rows_clear(m);
  if (*q) {
    char *s = g_strconcat("Run: ", q, NULL);
    g_ptr_array_add(m->rows, row_new(s, s, NULL, NULL));
    g_free(s);
  }
  for (guint i = 0; i < all->len; i++) {
    Row *r = g_ptr_array_index(all, i);
    if (match(r->terms, q))
      g_ptr_array_add(m->rows, row_new(r->id, r->label, NULL, NULL));
  }
}
static int runner(void) {
  Menu *m = menu_new("Commands", "Run a command…");
  m->icon = "utilities-terminal";
  char **paths = g_strsplit(g_getenv("PATH") ? g_getenv("PATH") : "", ":", -1);
  GHashTable *seen =
      g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
  for (int i = 0; paths[i]; i++) {
    GDir *d = g_dir_open(*paths[i] ? paths[i] : ".", 0, NULL);
    if (!d)
      continue;
    const char *n;
    while ((n = g_dir_read_name(d))) {
      char *p = path_join(*paths[i] ? paths[i] : ".", n);
      if (g_file_test(p, G_FILE_TEST_IS_REGULAR) && !access(p, X_OK) &&
          !g_hash_table_contains(seen, n)) {
        g_hash_table_add(seen, g_strdup(n));
        g_ptr_array_add(m->rows, row_new(n, n, NULL, NULL));
      }
      g_free(p);
    }
    g_dir_close(d);
  }
  g_strfreev(paths);
  g_hash_table_unref(seen);
  g_ptr_array_sort(m->rows, order);
  GPtrArray *all = m->rows;
  m->rows = g_ptr_array_new_with_free_func(row_free);
  m->userdata = all;
  m->search = runner_search;
  char *s = menu_show(m);
  if (s)
    spawn(argv_json("/bin/sh", "-lc", g_str_has_prefix(s, "Run: ") ? s + 5 : s,
                    NULL));
  menu_free(m);
  g_ptr_array_unref(all);
  return last_error ? 2 : 0;
}
typedef struct {
  J *engines;
  gboolean images;
  GtkWidget *web_button, *image_button, *hint;
} WebSearch;
static gboolean web_image(J *e) {
  return !strcmp(str(e, "type"), "images") ||
         g_strrstr(str(e, "name"), "images") != NULL;
}
static J *web_prefix(WebSearch *state, const char *query, const char **term) {
  *term = query;
  for (size_t i = 0; i < json_object_array_length(state->engines); i++) {
    J *e = json_object_array_get_idx(state->engines, i);
    const char *prefix = str(e, "prefix");
    if (*prefix && g_str_has_prefix(query, prefix) &&
        g_ascii_isspace(query[strlen(prefix)])) {
      *term = query + strlen(prefix);
      while (g_ascii_isspace(**term)) (*term)++;
      return e;
    }
  }
  return NULL;
}
static void web_set_mode(Menu *m, gboolean images) {
  WebSearch *state = m->userdata;
  state->images = images;
  m->selected = 0;
  const char *term;
  if (web_prefix(state, gtk_editable_get_text(GTK_EDITABLE(m->entry)), &term)) {
    char *query = g_strdup(term);
    gtk_editable_set_text(GTK_EDITABLE(m->entry), query);
    g_free(query);
  }
}
static void web_switch(GtkButton *button, gpointer data) {
  Menu *m = data;
  WebSearch *state = m->userdata;
  web_set_mode(m, GTK_WIDGET(button) == state->image_button);
  menu_refresh(m);
  gtk_widget_grab_focus(m->entry);
}
static void web_search_rows(Menu *m, const char *query) {
  WebSearch *state = m->userdata;
  if (!state->hint) {
    gtk_widget_add_css_class(m->window, "websearch");
    GListModel *monitors = gdk_display_get_monitors(gtk_widget_get_display(m->window));
    GdkMonitor *monitor = g_list_model_get_item(monitors, 0);
    if (monitor) {
      GdkRectangle geometry;
      gdk_monitor_get_geometry(monitor, &geometry);
      gtk_widget_set_size_request(m->panel, m->width,
          MIN(m->height, MAX(280, geometry.height - 120)));
      g_object_unref(monitor);
    }
    GtkWidget *header = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    GtkWidget *title = gtk_label_new("Web search");
    gtk_widget_add_css_class(title, "websearch-title");
    gtk_label_set_xalign(GTK_LABEL(title), 0);
    gtk_widget_set_hexpand(title, TRUE);
    gtk_box_append(GTK_BOX(header), title);
    state->web_button = gtk_button_new_with_label("Web");
    state->image_button = gtk_button_new_with_label("Images");
    char *left=navigation_label(m->navigation,"left"), *right=navigation_label(m->navigation,"right");
    gtk_widget_set_tooltip_text(state->web_button,left);
    gtk_widget_set_tooltip_text(state->image_button,right);
    g_free(left);g_free(right);
    gtk_box_append(GTK_BOX(header), state->web_button);
    gtk_box_append(GTK_BOX(header), state->image_button);
    g_signal_connect(state->web_button, "clicked", G_CALLBACK(web_switch), m);
    g_signal_connect(state->image_button, "clicked", G_CALLBACK(web_switch), m);
    state->hint = gtk_label_new("");
    gtk_label_set_xalign(GTK_LABEL(state->hint), 0);
    gtk_widget_add_css_class(state->hint, "websearch-hint");
    gtk_box_insert_child_after(GTK_BOX(m->panel), state->hint,
                              gtk_widget_get_first_child(m->panel));
    gtk_box_prepend(GTK_BOX(m->panel), header);
  }
  const char *term;
  J *prefixed = web_prefix(state, query, &term);
  gboolean images = prefixed ? web_image(prefixed) : state->images;
  gtk_widget_remove_css_class(state->web_button, "suggested-action");
  gtk_widget_remove_css_class(state->image_button, "suggested-action");
  gtk_widget_add_css_class(images ? state->image_button : state->web_button,
                          "suggested-action");
  gtk_entry_set_placeholder_text(GTK_ENTRY(m->entry),
      images ? "Search images…" : "Search the web…");
  gtk_label_set_text(GTK_LABEL(state->hint), prefixed ?
      "Shortcut selected · Enter to search" :
      "Type a query · Choose an engine · Enter to search");
  rows_clear(m);
  for (size_t i = 0; i < json_object_array_length(state->engines); i++) {
    J *e = json_object_array_get_idx(state->engines, i);
    if (prefixed ? e != prefixed : web_image(e) != images) continue;
    char *id = g_strdup_printf("%zu", i);
    char *sub = g_strdup_printf("%s%s", str(e, "prefix"),
                               *str(e, "prefix") ? "  query" : "");
    Row *row = row_new(id, str(e, "name"), sub,
                      images ? "image-x-generic-symbolic" : "web-browser-symbolic");
    row->data = e;
    g_ptr_array_add(m->rows, row);
    g_free(id);
    g_free(sub);
  }
  gtk_label_set_text(GTK_LABEL(m->empty), images ?
      "No image engines configured" : "No web engines configured");
}
static gboolean web_activate(Menu *m, Row *row, const char *action) {
  WebSearch *state = m->userdata;
  (void)action;
  if (!row) return TRUE;
  const char *term;
  J *e = web_prefix(state, gtk_editable_get_text(GTK_EDITABLE(m->entry)), &term);
  if (!e) e = row->data;
  char *query = g_strdup(term);
  g_strstrip(query);
  if (!*query) {
    g_free(query);
    return TRUE;
  }
  char *encoded = g_uri_escape_string(query, NULL, FALSE);
  char **parts = g_strsplit(str(e, "url"), "%TERM%", -1);
  char *url = g_strjoinv(encoded, parts);
  open_url(url);
  g_free(url);
  g_strfreev(parts);
  g_free(encoded);
  g_free(query);
  return FALSE;
}
static gboolean web_navigate(Menu *m, const char *direction) {
  web_set_mode(m, !strcmp(direction,"right"));
  menu_refresh(m);
  gtk_widget_grab_focus(m->entry);
  return TRUE;
}
static int websearch(void) {
  char *p = g_build_filename(g_get_user_config_dir(), "simplepicker",
                             "websearch/engines.json", NULL);
  if (!g_file_test(p, G_FILE_TEST_EXISTS)) {
    g_free(p);
    p = g_build_filename(g_get_user_config_dir(), "simplepicker", "websearch.json", NULL);
  }
  if (!g_file_test(p, G_FILE_TEST_EXISTS)) {
    g_free(p);
    p = path_join(asset_dir, "websearch.json");
  }
  J *engines = read_json(p, NULL);
  g_free(p);
  if (!engines) return 2;
  if (!json_object_is_type(engines, json_type_array)) {
    fail("Web search engines must be a JSON array");
    json_object_put(engines);
    return 2;
  }
  for (size_t i = 0; i < json_object_array_length(engines); i++) {
    J *e = json_object_array_get_idx(engines, i);
    if (!json_object_is_type(e, json_type_object) || !*str(e, "name") ||
        !g_str_has_prefix(str(e, "url"), "https://") ||
        !strstr(str(e, "url"), "%TERM%")) {
      fail("Invalid web search engine at entry %zu", i + 1);
      json_object_put(engines);
      return 2;
    }
  }
  WebSearch state = {.engines = engines};
  Menu *m = menu_new("Web search", "Search the web…");
  m->icon = "web-browser-symbolic";
  m->width = 620;
  size_t web_count = 0, image_count = 0;
  for (size_t i = 0; i < json_object_array_length(engines); i++) {
    if (web_image(json_object_array_get_idx(engines, i))) image_count++;
    else web_count++;
  }
  m->height = 190 + 56 * MIN((size_t)20, MAX(web_count, image_count));
  m->userdata = &state;
  m->search = web_search_rows;
  m->activate = web_activate;
  m->navigate = web_navigate;
  char *css = g_build_filename(g_get_user_config_dir(), "simplepicker", "websearch/style.css", NULL);
  if (g_file_test(css, G_FILE_TEST_IS_REGULAR)) m->theme = css;
  menu_show(m);
  menu_free(m);
  g_free(css);
  json_object_put(engines);
  return last_error ? 2 : 0;
}
static gboolean valid_bookmarks(J *j) {
  if (!j || !json_object_is_type(j, json_type_array)) {
    fail("Bookmarks must be a JSON list");
    return FALSE;
  }
  for (size_t i = 0; i < json_object_array_length(j); i++) {
    J *r = json_object_array_get_idx(j, i);
    char *scheme = g_uri_parse_scheme(str(r, "url"));
    gboolean ok = json_object_is_type(obj(r, "label"), json_type_string) &&
                  json_object_is_type(obj(r, "url"), json_type_string) &&
                  scheme &&
                  (!strcmp(scheme, "http") || !strcmp(scheme, "https") ||
                   !strcmp(scheme, "ftp") || !strcmp(scheme, "file"));
    g_free(scheme);
    if (!ok) {
      fail("Each bookmark needs a label and supported URL");
      return FALSE;
    }
  }
  return TRUE;
}
static void bookmark_edit(void) {
  J *v = json_object_new_object();
  char *script = path_join(asset_dir, "edit-bookmarks");
  setstr(v, "editor", script);
  J *a = command_argv("edit_bookmarks",
                      v); /* Existing configs invoke python3 {editor}; use the
                             native editor entry point. */
  for (size_t i = 0; i + 1 < json_object_array_length(a); i++)
    if (!strcmp(js(json_object_array_get_idx(a, i)), "python3") &&
        !strcmp(js(json_object_array_get_idx(a, i + 1)), script)) {
      json_object_array_del_idx(a, i, 1);
      break;
    }
  spawn(a);
  json_object_put(v);
  g_free(script);
}
static int bookmarks(void) {
  J *records = history("bookmarks.json", "[]"),
    *h = history("bookmark-history.json", "{}");
  if (!records || !h || !valid_bookmarks(records)) {
    if (records)
      json_object_put(records);
    if (h)
      json_object_put(h);
    return 2;
  }
  Menu *m = menu_new("Bookmarks", "Search bookmarks…");
  m->icon = "starred";
  m->icon_size = 32;
  menu_shortcut(m, "e", "Edit bookmarks");
  for (size_t i = 0; i < json_object_array_length(records); i++) {
    J *r = json_object_array_get_idx(records, i);
    char *id = g_strdup_printf("%zu", i);
    Row *row = row_new(id, *str(r, "label") ? str(r, "label") : str(r, "url"),
                       str(r, "url"), NULL);
    row->rank = history_count(h, str(r, "url"));
    g_ptr_array_add(m->rows, row);
    g_free(id);
  }
  g_ptr_array_sort(m->rows, order);
  char *s = menu_show(m);
  if (m->action && !strcmp(m->action, "e"))
    bookmark_edit();
  else if (s) {
    J *r = json_object_array_get_idx(records, atoi(s));
    open_url(str(r, "url"));
    if (!last_error)
      history_add("bookmark-history.json", str(r, "url"));
  }
  menu_free(m);
  json_object_put(records);
  json_object_put(h);
  return last_error ? 2 : 0;
}
static int bookmark_add(void) {
  char *url = run_text(argv_json("wl-paste", "--no-newline", NULL), NULL, 5);
  if (!url)
    return 2;
  g_strstrip(url);
  GError *e = NULL;
  GUri *uri = g_uri_parse(url, G_URI_FLAGS_NONE, &e);
  if (!uri || !g_uri_get_scheme(uri) ||
      (strcmp(g_uri_get_scheme(uri), "http") &&
       strcmp(g_uri_get_scheme(uri), "https"))) {
    fail("Copy an http(s) URL before adding a bookmark");
    g_clear_error(&e);
    if (uri)
      g_uri_unref(uri);
    g_free(url);
    return 2;
  }
  char *label = ask("Bookmark name", g_uri_get_host(uri), "bookmark-new");
  g_uri_unref(uri);
  if (label) {
    int fd = data_lock("bookmarks.lock");
    if (fd >= 0) {
      J *r = history("bookmarks.json", "[]");
      if (valid_bookmarks(r)) {
        gboolean found = FALSE;
        for (size_t i = 0; i < json_object_array_length(r); i++) {
          J *b = json_object_array_get_idx(r, i);
          if (!strcmp(str(b, "url"), url) &&
              !strcmp(str(b, "label"), *label ? label : url))
            found = TRUE;
        }
        if (!found) {
          J *b = json_object_new_object();
          setstr(b, "label", *label ? label : url);
          setstr(b, "url", url);
          json_object_array_add(r, b);
          save_data("bookmarks.json", r);
        }
      }
      if (r)
        json_object_put(r);
      close(fd);
    }
    g_free(label);
  }
  g_free(url);
  return last_error ? 2 : 0;
}
int bookmark_editor(void) {
  J *original = history("bookmarks.json", "[]");
  if (!valid_bookmarks(original)) {
    if (original)
      json_object_put(original);
    return 2;
  }
  char *folder = g_dir_make_tmp("simplepicker-bookmarks-XXXXXX", NULL);
  if (!folder) {
    fail("Cannot create edit directory");
    json_object_put(original);
    return 2;
  }
  char *draft = path_join(folder, "bookmarks.json");
  write_json(draft, original);
  while (!last_error) {
    char *argv[] = {"nvim", draft, NULL};
    int status;
    GError *e = NULL;
    gboolean ok = g_spawn_sync(
        NULL, argv, NULL, G_SPAWN_SEARCH_PATH | G_SPAWN_CHILD_INHERITS_STDIN,
        NULL, NULL, NULL, NULL, &status, &e);
    if (!ok || !g_spawn_check_wait_status(status, NULL)) {
      if (e) {
        fail("%s", e->message);
        g_clear_error(&e);
      }
      break;
    }
    J *edited = read_json(draft, NULL);
    if (!valid_bookmarks(edited)) {
      g_printerr("Not saved: %s\nEnter to fix, or q to discard: ", last_error);
      g_clear_pointer(&last_error, g_free);
      char answer[32];
      if (edited)
        json_object_put(edited);
      if (!fgets(answer, sizeof answer, stdin) || answer[0] == 'q')
        break;
      continue;
    }
    if (json_object_equal(original, edited)) {
      json_object_put(edited);
      break;
    }
    int fd = data_lock("bookmarks.lock");
    if (fd < 0) {
      json_object_put(edited);
      break;
    }
    J *current = history("bookmarks.json", "[]");
    if (current && !json_object_equal(original, current)) {
      save_data("bookmarks-edit-recovery.json", edited);
      g_printerr("Bookmarks changed while editing; draft saved as "
                 "bookmarks-edit-recovery.json.\n");
    } else if (current) {
      save_data("bookmarks.json.bak", original);
      save_data("bookmarks.json", edited);
    }
    if (current)
      json_object_put(current);
    json_object_put(edited);
    close(fd);
    break;
  }
  unlink(draft);
  rmdir(folder);
  g_free(folder);
  g_free(draft);
  json_object_put(original);
  return last_error ? 2 : 0;
}
static void save_calculation(const char *expression, const char *answer) {
  int fd = data_lock("calculator-history.lock");
  if (fd < 0)
    return;
  J *old = history("calculator-history.json", "[]"),
    *out = json_object_new_array(), *r = json_object_new_object();
  setstr(r, "expression", expression);
  setstr(r, "answer", answer);
  json_object_array_add(out, r);
  for (size_t i = 0; old && i < json_object_array_length(old) &&
                     json_object_array_length(out) < 10;
       i++) {
    J *v = json_object_array_get_idx(old, i);
    if (strcmp(str(v, "expression"), expression) &&
        json_object_is_type(obj(v, "answer"), json_type_string))
      json_object_array_add(out, jclone(v));
  }
  if (old) {
    save_data("calculator-history.json", out);
    json_object_put(old);
  }
  json_object_put(out);
  close(fd);
}
static void calc_search(Menu *m, const char *q) {
  rows_clear(m);
  J *h = history("calculator-history.json", "[]");
  if (*q) {
    char *label = g_strconcat("Calculate: ", q, NULL);
    g_ptr_array_add(m->rows, row_new("calculate", label, NULL, NULL));
    g_free(label);
  }
  for (size_t i = 0; h && i < json_object_array_length(h) && i < 10; i++) {
    J *r = json_object_array_get_idx(h, i);
    if (!json_object_is_type(obj(r, "expression"), json_type_string) ||
        !json_object_is_type(obj(r, "answer"), json_type_string))
      continue;
    char *id = g_strdup_printf("history:%zu", i);
    char **parts = g_strsplit(str(r, "answer"), "\n", -1);
    char *label = g_strjoinv(" ", parts);
    Row *row = row_new(id, label, str(r, "expression"), NULL);
    row->data = jclone(r);
    row->destroy = free_json;
    if (match(row->terms, q))
      g_ptr_array_add(m->rows, row);
    else
      row_free(row);
    g_free(id);
    g_free(label);
    g_strfreev(parts);
  }
  if (h)
    json_object_put(h);
}
static gboolean calc_action(Menu *m, Row *r, const char *a) {
  gboolean previous = r && r->data;
  const char *expression = previous ? str(r->data, "expression") : m->query;
  if (!strcmp(a, "e")) {
    gtk_editable_set_text(GTK_EDITABLE(m->entry), expression);
    return TRUE;
  }
  if (!expression || !*expression)
    return TRUE;
  char *expr = g_strdup(expression),
       *answer = previous ? g_strdup(str(r->data, "answer"))
                          : run_text(argv_json("qalc", "-t", "--", expr, NULL),
                                     NULL, 5);
  if (answer) {
    g_strstrip(answer);
    if (*answer) {
      char *text = !strcmp(a, "f") ? g_strdup_printf("%s = %s", expr, answer)
                                   : g_strdup(answer);
      if (copy_text(text))
        save_calculation(expr, answer);
      g_free(text);
    }
    g_free(answer);
  }
  g_free(expr);
  if (last_error) {
    menu_finish(m, NULL);
    return FALSE;
  }
  if (m->closed || !strcmp(a, "f") || previous)
    return FALSE;
  gtk_editable_set_text(GTK_EDITABLE(m->entry), "");
  return TRUE;
}
static int calc(void) {
  Menu *m = menu_new("Calculator", "Calculate… Enter copies; Esc closes");
  m->icon = "accessories-calculator";
  m->search = calc_search;
  m->activate = calc_action;
  menu_shortcut(m, "e", "Edit expression");
  menu_shortcut(m, "f", "Copy full");
  menu_show(m);
  menu_free(m);
  return last_error ? 2 : 0;
}
static gboolean clipboard_image(Row *r) {
  return g_str_has_prefix((const char *)r->data, "[[ binary data ") &&
         g_regex_match_simple(
             "(?i) (png|jpe?g|gif|webp|bmp|tiff?|ico|avif|heic|svg)( "
             "[0-9]+x[0-9]+)? \\]\\]$",
             (const char *)r->data, 0, 0);
}
/* File URIs encode spaces, so the first whitespace-delimited URI is also
 * usable when cliphist flattens a multiple-file selection onto one line. */
static char *clipboard_media_path(Row *r, const char *prefix) {
  const char *text = r->data;
  if (!g_str_has_prefix(text, "file://"))
    return NULL;
  char **parts = g_strsplit_set(text, " \r\n\t", 2);
  char *host = NULL;
  char *path = g_filename_from_uri(parts[0], &host, NULL);
  g_strfreev(parts);
  if (host && *host && g_ascii_strcasecmp(host, "localhost"))
    g_clear_pointer(&path, g_free);
  g_free(host);
  if (!path)
    return NULL;
  char *type = g_content_type_guess(path, NULL, 0, NULL);
  char *mime = g_content_type_get_mime_type(type);
  gboolean video = mime && g_str_has_prefix(mime, prefix);
  g_free(mime);
  g_free(type);
  if (!video)
    g_clear_pointer(&path, g_free);
  return path;
}
static char *clipboard_video_path(Row *r) {
  return clipboard_media_path(r, "video/");
}
static void clip_preview(Menu *m, Row *r) {
  char *image = clipboard_media_path(r, "image/");
  if (image) {
    if (!g_file_test(image, G_FILE_TEST_IS_REGULAR)) {
      menu_set_text_preview(m, "Image file unavailable — it may have been moved or deleted.");
    } else {
      GBytes *empty = g_bytes_new_static("", 0);
      menu_preview_process(m, argv_json("cat", "--", image, NULL), empty, TRUE);
      g_bytes_unref(empty);
    }
    g_free(image);
    return;
  }
  char *video = clipboard_video_path(r);
  if (video) {
    if (!g_file_test(video, G_FILE_TEST_IS_REGULAR)) {
      menu_set_text_preview(m, "Video file unavailable — it may have been moved or deleted.");
    } else {
      char *ffmpeg = g_find_program_in_path("ffmpeg");
      /* Do not cache the fallback while a frame is pending: moving away
       * cancels the decoder, and returning should retry the preview. */
      gboolean cache = m->cache_previews;
      m->cache_previews = FALSE;
      menu_set_text_preview(m, ffmpeg ? "Video preview unavailable." : "Install ffmpeg for video previews.");
      m->cache_previews = cache;
      if (ffmpeg) {
        GBytes *empty = g_bytes_new_static("", 0);
        menu_preview_process(m,
            argv_json(ffmpeg, "-nostdin", "-hide_banner", "-loglevel", "error",
                      "-threads", "1", "-protocol_whitelist", "file", "-i", video,
                      "-map", "0:v:0", "-frames:v", "1", "-vf",
                      "scale=640:360:force_original_aspect_ratio=decrease",
                      "-c:v", "png", "-threads", "1", "-f", "image2pipe", "pipe:1", NULL),
            empty, TRUE);
        g_bytes_unref(empty);
      }
      g_free(ffmpeg);
    }
    g_free(video);
    return;
  }
  if (g_str_has_prefix((const char *)r->data, "[[ binary data ") &&
      !clipboard_image(r)) {
    menu_set_text_preview(m, r->data);
    return;
  }
  GBytes *input = g_bytes_new(r->id, strlen(r->id));
  menu_preview_process(m, argv_json("cliphist", "decode", NULL), input,
                       clipboard_image(r));
  g_bytes_unref(input);
}
static gboolean clip_action(Menu *m, Row *r, const char *a) {
  if (!r)
    return TRUE;
  if (!strcmp(a, "d")) {
    char *s = run_text(argv_json("cliphist", "delete", NULL), r->id, 3);
    if (!s) {
      menu_finish(m, NULL);
      return FALSE;
    }
    g_free(s);
    if (m->preview_cache) {
      gpointer cached = g_hash_table_lookup(m->preview_cache, r->id);
      if (cached)
        g_queue_remove(m->preview_recent, cached);
      g_hash_table_remove(m->preview_cache, r->id);
    }
    for (guint i = 0; i < m->rows->len; i++)
      if (g_ptr_array_index(m->rows, i) == r) {
        g_ptr_array_remove_index(m->rows, i);
        break;
      }
    return TRUE;
  }
  if (!strcmp(a, "p") &&
      g_str_has_prefix((const char *)r->data, "[[ binary data "))
    return TRUE;
  return FALSE;
}
static void paste_plain(GBytes *b) {
  if (!copy_bytes(b, "text/plain;charset=utf-8"))
    return;
  gboolean terminal = FALSE;
  if (supports("list")) {
    J *ws = windows_list();
    for (size_t i = 0; ws && i < json_object_array_length(ws); i++) {
      J *w = json_object_array_get_idx(ws, i);
      if (!yes(w, "focused"))
        continue;
      char *path = g_strdup_printf("/proc/%d/exe", num(w, "pid"));
      char *target = g_file_read_link(path, NULL);
      g_free(path);
      if (target) {
        char *name = g_path_get_basename(target);
        terminal = !strcmp(name, "kitty") || !strcmp(name, "foot") ||
                   !strcmp(name, "alacritty") || !strcmp(name, "wezterm-gui") ||
                   !strcmp(name, "konsole") ||
                   !strcmp(name, "gnome-terminal-server") ||
                   !strcmp(name, "st") || !strcmp(name, "xterm");
        g_free(name);
        g_free(target);
      }
      break;
    }
    if (ws)
      json_object_put(ws);
    g_clear_pointer(&last_error, g_free);
  }
  char *helper = g_find_program_in_path("wtype");
  if (!helper)
    helper = path_join(asset_dir, "wtype");
  J *v = json_object_new_object();
  setstr(v, "wtype", helper);
  char *out =
      run_text(command_argv(terminal ? "paste_terminal" : "paste", v), NULL, 5);
  g_free(out);
  g_free(helper);
  json_object_put(v);
}
/* cliphist retains the payload, not the original MIME offer. Restore local
 * file lists explicitly; MIME sniffing otherwise turns them into plain text. */
static gboolean clipboard_files(GBytes *content) {
  gsize size;
  const char *data = g_bytes_get_data(content, &size);
  if (!size || memchr(data, '\0', size) || !g_utf8_validate(data, size, NULL))
    return FALSE;
  char *text = g_strndup(data, size);
  char **uris = g_uri_list_extract_uris(text);
  gboolean valid = uris[0] != NULL;
  for (int i = 0; valid && uris[i]; i++) {
    char *host = NULL;
    char *path = g_filename_from_uri(uris[i], &host, NULL);
    valid = path && (!host || !*host || !g_ascii_strcasecmp(host, "localhost"));
    g_free(path);
    g_free(host);
  }
  g_strfreev(uris);
  g_free(text);
  return valid;
}
static int clipboard(void) {
  char *s = run_text(argv_json("cliphist", "-preview-width", "4096", "list", NULL), NULL, 5);
  if (!s)
    return 2;
  Menu *m = menu_new("Clipboard", "Clipboard history… Enter copies");
  m->icon = "edit-paste";
  m->previews = TRUE;
  m->preview = clip_preview;
  m->cache_previews = TRUE;
  m->activate = clip_action;
  menu_shortcut(m, "d", "Delete entry");
  if (json_object_array_length(obj(obj(config, "commands"), "paste")))
    menu_shortcut(m, "p", "Paste plain text");
  char **lines = g_strsplit(s, "\n", -1);
  for (int i = 0; lines[i]; i++) {
    if (!*lines[i])
      continue;
    char *tab = strchr(lines[i], '\t');
    const char *text = tab ? tab + 1 : lines[i];
    Row *r = row_new(lines[i], text, NULL, "text-x-generic");
    r->data = g_strdup(text);
    r->destroy = g_free;
    if (clipboard_image(r)) {
      g_free(r->label);
      r->label = g_strdup("Image");
      g_free(r->terms);
      r->terms = norm("Image");
      g_free(r->icon);
      r->icon = g_strdup("image-x-generic");
    } else if (g_str_has_prefix(text, "file://")) {
      char *video = clipboard_video_path(r);
      char *image = clipboard_media_path(r, "image/");
      if (video || image) {
        char *name = g_filename_display_basename(video ? video : image);
        g_strdelimit(name, "\r\n\t", ' ');
        g_free(r->label);
        r->label = g_strconcat(video ? "Video · " : "Image · ", name, NULL);
        char *terms = g_strconcat(video ? "Video " : "Image ", name, " ", text, NULL);
        g_free(r->terms);
        r->terms = norm(terms);
        g_free(terms);
        g_free(r->icon);
        r->icon = g_strdup(video ? "video-x-generic" : "image-x-generic");
        g_free(name);
        g_free(video);
      }
      g_free(image);
    } else if (g_str_has_prefix(text, "http://") ||
               g_str_has_prefix(text, "https://")) {
      g_free(r->icon);
      r->icon = g_strdup("web-browser");
    } /* sub stores original binary metadata; suppress duplicate subtitle in the
         view below. */
    g_ptr_array_add(m->rows, r);
  }
  g_strfreev(lines);
  g_free(s);
  char *selected = menu_show(m);
  if (selected) {
    GBytes *input = g_bytes_new(selected, strlen(selected)),
           *content =
               run_bytes(argv_json("cliphist", "decode", NULL), input, 5);
    g_bytes_unref(input);
    if (content) {
      if (m->action && !strcmp(m->action, "p"))
        paste_plain(content);
      else if (clipboard_files(content))
        copy_bytes(content, "text/uri-list");
      else {
        GBytes *out = run_bytes(
            argv_json("file", "--brief", "--mime-type", "-", NULL), content, 5);
        if (out) {
          gsize n;
          const char *t = g_bytes_get_data(out, &n);
          char *mime = g_strndup(t, n);
          g_strstrip(mime);
          copy_bytes(content, g_str_has_prefix(mime, "image/") ? mime : NULL);
          g_free(mime);
          g_bytes_unref(out);
        }
      }
      g_bytes_unref(content);
    }
  }
  menu_free(m);
  return last_error ? 2 : 0;
}
static int windows(void) {
  J *dest = supports("current") && supports("move") ? desktop_current() : NULL;
  if (last_error)
    return 2;
  J *rows = windows_list();
  if (!rows) {
    if (dest)
      json_object_put(dest);
    return 2;
  }
  Menu *m = menu_new("Windows", "Switch window…");
  m->icon = "preferences-system-windows";
  if (supports("close"))
    menu_shortcut(m, "d", "Close window");
  if (dest)
    menu_shortcut(m, "m", "Move here");
  for (size_t i = 0; i < json_object_array_length(rows); i++) {
    J *w = json_object_array_get_idx(rows, i);
    char *label =
        g_strdup_printf("%s — %s  [%s · %s]", str(w, "app_id"), str(w, "title"),
                        str(w, "workspace"), str(w, "id"));
    char *id = g_strdup_printf("%zu", i);
    g_ptr_array_add(m->rows, row_new(id, label, NULL, NULL));
    g_free(label);
    g_free(id);
  }
  char *s = menu_show(m);
  if (s)
    desktop_action(m->action && !strcmp(m->action, "d")   ? "close"
                   : m->action && !strcmp(m->action, "m") ? "move"
                                                          : "focus",
                   json_object_array_get_idx(rows, atoi(s)), dest);
  menu_free(m);
  json_object_put(rows);
  if (dest)
    json_object_put(dest);
  return last_error ? 2 : 0;
}
static int symbols(void) {
  char *p = path_join(asset_dir, "symbols.json");
  J *j = read_json(p, NULL);
  g_free(p);
  if (!j)
    return 2;
  Menu *m = menu_new("Symbols", "Search symbols and emoji…");
  m->icon = "face-smile";
  for (size_t i = 0; i < json_object_array_length(j); i++) {
    J *a = json_object_array_get_idx(j, i);
    const char *symbol = js(json_object_array_get_idx(a, 0)),
               *name = js(json_object_array_get_idx(a, 1));
    char *s = g_strdup_printf("%s  %s", symbol, name);
    g_ptr_array_add(m->rows, row_new(symbol, s, NULL, NULL));
    g_free(s);
  }
  char *s = menu_show(m);
  if (s)
    copy_text(s);
  menu_free(m);
  json_object_put(j);
  return last_error ? 2 : 0;
}
static int fonts(void) {
  char *text = run_text(argv_json("fc-list", ":", "family", NULL), NULL, 5);
  if (!text)
    return 2;
  GHashTable *seen =
      g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
  char **lines = g_strsplit(text, "\n", -1);
  char *p = data_path("font-preview.txt"), *sample = NULL;
  g_file_get_contents(p, &sample, NULL, NULL);
  if (!sample)
    sample =
        g_strdup("The quick brown fox jumps over the lazy dog. 0123456789");
  gboolean again = TRUE;
  while (again && !last_error) {
    again = FALSE;
    Menu *m = menu_new("Fonts", "Select font name to copy…");
    m->icon = "preferences-desktop-font";
    m->font_rows = TRUE;
    m->sample = sample;
    menu_shortcut(m, "t", "Preview text");
    g_hash_table_remove_all(seen);
    for (int i = 0; lines[i]; i++) {
      char *name = g_strdup(lines[i]), *comma = strchr(name, ',');
      if (comma)
        *comma = 0;
      g_strstrip(name);
      if (*name && !g_hash_table_contains(seen, name)) {
        g_hash_table_add(seen, g_strdup(name));
        g_ptr_array_add(m->rows, row_new(name, name, NULL, NULL));
      }
      g_free(name);
    }
    g_ptr_array_sort(m->rows, order);
    char *s = menu_show(m);
    if (m->action && !strcmp(m->action, "t")) {
      char *edited = ask("Font preview text…", sample, m->icon);
      if (edited) {
        g_free(sample);
        sample = edited;
        g_mkdir_with_parents(data_dir, 0700);
        GError *e = NULL;
        if (!g_file_set_contents_full(
                p, sample, -1, G_FILE_SET_CONTENTS_CONSISTENT, 0600, &e)) {
          fail("%s", e->message);
          g_clear_error(&e);
        }
      }
      again = TRUE;
    } else if (s)
      copy_text(s);
    menu_free(m);
  }
  g_free(p);
  g_free(sample);
  g_hash_table_unref(seen);
  g_strfreev(lines);
  g_free(text);
  return last_error ? 2 : 0;
}
int provider(const char *name) {
  if (!strcmp(name, "apps"))
    return apps();
  if (!strcmp(name, "runner"))
    return runner();
  if (!strcmp(name, "websearch"))
    return websearch();
  if (!strcmp(name, "bookmarks"))
    return bookmarks();
  if (!strcmp(name, "bookmark-add"))
    return bookmark_add();
  if (!strcmp(name, "bookmark-edit")) {
    bookmark_edit();
    return last_error ? 2 : 0;
  }
  if (!strcmp(name, "calc"))
    return calc();
  if (!strcmp(name, "clipboard"))
    return clipboard();
  if (!strcmp(name, "windows"))
    return windows();
  if (!strcmp(name, "symbols"))
    return symbols();
  if (!strcmp(name, "fonts"))
    return fonts();
  if (!strcmp(name, "dashboard"))
    return dashboard_show(FALSE, FALSE);
  if (!strcmp(name, "screensaver"))
    return dashboard_show(TRUE, FALSE);
  if (!strcmp(name, "screensaver-stop"))
    return dashboard_show(TRUE, TRUE);
  if (!strcmp(name, "power"))
    return power_show();
  fail("Unknown provider: %s", name);
  return 2;
}
