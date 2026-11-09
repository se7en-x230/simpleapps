#include "../simple-common/simple-keyboard.h"
#include "simple-theme.h"
#include "sp.h"
/* Session-only clipboard cache. At most eight scaled images/text previews. */
typedef struct {
  char *id, *text;
  GdkTexture *texture;
} CachedPreview;
static void cached_preview_free(gpointer data) {
  CachedPreview *cached = data;
  g_free(cached->id);
  g_free(cached->text);
  g_clear_object(&cached->texture);
  g_free(cached);
}
static void remember_preview(Menu *m, const char *text, GdkTexture *texture) {
  if (!m->cache_previews)
    return;
  Row *row = menu_selected(m);
  if (!row)
    return;
  if (!m->preview_cache) {
    m->preview_cache = g_hash_table_new_full(g_str_hash, g_str_equal, NULL,
                                             cached_preview_free);
    m->preview_recent = g_queue_new();
  }
  CachedPreview *old = g_hash_table_lookup(m->preview_cache, row->id);
  if (old) {
    g_queue_remove(m->preview_recent, old);
    g_hash_table_remove(m->preview_cache, row->id);
  }
  while (g_queue_get_length(m->preview_recent) >= 8) {
    CachedPreview *stale = g_queue_pop_head(m->preview_recent);
    g_hash_table_remove(m->preview_cache, stale->id);
  }
  CachedPreview *cached = g_new0(CachedPreview, 1);
  cached->id = g_strdup(row->id);
  cached->text = g_strdup(text);
  if (texture)
    cached->texture = g_object_ref(texture);
  g_hash_table_insert(m->preview_cache, cached->id, cached);
  g_queue_push_tail(m->preview_recent, cached);
}
static gboolean restore_preview(Menu *m, Row *row) {
  if (!m->cache_previews || !m->preview_cache || !row)
    return FALSE;
  CachedPreview *cached = g_hash_table_lookup(m->preview_cache, row->id);
  if (!cached)
    return FALSE;
  g_queue_remove(m->preview_recent, cached);
  g_queue_push_tail(m->preview_recent, cached);
  gtk_widget_set_visible(m->picture, cached->texture != NULL);
  gtk_widget_set_visible(gtk_widget_get_parent(gtk_widget_get_parent(m->text)),
                         cached->texture == NULL);
  if (cached->texture)
    gtk_picture_set_paintable(GTK_PICTURE(m->picture),
                              GDK_PAINTABLE(cached->texture));
  else
    gtk_label_set_text(GTK_LABEL(m->text), cached->text ? cached->text : "");
  gtk_widget_set_visible(m->preview_box, TRUE);
  return TRUE;
}
Row *row_new(const char *id, const char *label, const char *sub,
             const char *icon) {
  Row *r = g_new0(Row, 1);
  r->id = g_strdup(id);
  r->label = g_strdup(label ? label : id);
  r->sub = g_strdup(sub ? sub : "");
  char *t = g_strconcat(r->label, " ", r->sub, NULL);
  r->terms = norm(t);
  g_free(t);
  r->icon = g_strdup(icon);
  return r;
}
void row_free(gpointer p) {
  Row *r = p;
  g_free(r->id);
  g_free(r->label);
  g_free(r->sub);
  g_free(r->terms);
  g_free(r->icon);
  g_free(r->font);
  g_clear_object(&r->gicon);
  if (r->destroy)
    r->destroy(r->data);
  g_free(r);
}
Menu *menu_new(const char *title, const char *prompt) {
  Menu *m = g_new0(Menu, 1);
  m->benchmark = sp_benchmark;
  m->title = title;
  m->prompt = prompt;
  m->icon = "view-list-symbolic";
  m->width = 600;
  m->height = 570;
  m->icon_size = 24;
  m->rows = g_ptr_array_new_with_free_func(row_free);
  m->shortcuts = json_object_new_object();
  return m;
}
void menu_free(Menu *m) {
  if (m->preview_timer)
    g_source_remove(m->preview_timer);
  if (m->preview_cancel) {
    g_cancellable_cancel(m->preview_cancel);
    g_object_unref(m->preview_cancel);
  }
  if (m->preview_recent)
    g_queue_free(m->preview_recent);
  if (m->preview_cache)
    g_hash_table_unref(m->preview_cache);
  g_ptr_array_unref(m->rows);
  json_object_put(m->shortcuts);
  g_free(m->result);
  g_free(m->action);
  g_free(m->query);
  if (m->navigation) g_key_file_unref(m->navigation);
  g_free(m);
}
void rows_clear(Menu *m) { g_ptr_array_set_size(m->rows, 0); }
void menu_shortcut(Menu *m, const char *k, const char *label) {
  setstr(m->shortcuts, k, label);
}
Row *menu_find(Menu *m, const char *id) {
  for (guint i = 0; i < m->rows->len; i++) {
    Row *r = g_ptr_array_index(m->rows, i);
    if (!strcmp(r->id, id))
      return r;
  }
  return NULL;
}
Row *menu_selected(Menu *m) {
  GtkListBoxRow *r = gtk_list_box_get_selected_row(GTK_LIST_BOX(m->list));
  return r ? g_object_get_data(G_OBJECT(r), "row") : NULL;
}
void menu_finish(Menu *m, const char *id) {
  if (m->closed)
    return;
  m->closed = TRUE;
  m->result = g_strdup(id);
  if (m->preview_timer) {
    g_source_remove(m->preview_timer);
    m->preview_timer = 0;
  }
  if (m->preview_cancel)
    g_cancellable_cancel(m->preview_cancel);
  gtk_window_destroy(GTK_WINDOW(m->window));
  g_main_loop_quit(m->loop);
}
void menu_set_text_preview(Menu *m, const char *text) {
  remember_preview(m, text, NULL);
  gtk_widget_set_visible(m->picture, FALSE);
  gtk_label_set_text(GTK_LABEL(m->text), text ? text : "");
  gtk_widget_set_visible(gtk_widget_get_parent(gtk_widget_get_parent(m->text)),
                         TRUE);
  gtk_widget_set_visible(m->preview_box, TRUE);
}
typedef struct {
  Menu *menu;
  GCancellable *cancel;
} ImageJob;
static void image_worker(GTask *task, gpointer source, gpointer data,
                         GCancellable *cancel) {
  (void)source;
  GBytes *bytes = data;
  GInputStream *stream = g_memory_input_stream_new_from_bytes(bytes);
  GError *error = NULL;
  GdkPixbuf *pix = gdk_pixbuf_new_from_stream_at_scale(stream, 1000, 800, TRUE,
                                                       cancel, &error);
  g_object_unref(stream);
  if (pix)
    g_task_return_pointer(task, pix, g_object_unref);
  else
    g_task_return_error(task, error);
}
static void image_ready(GObject *source, GAsyncResult *result, gpointer data) {
  (void)source;
  ImageJob *job = data;
  GError *error = NULL;
  GdkPixbuf *pix = g_task_propagate_pointer(G_TASK(result), &error);
  if (error && !g_cancellable_is_cancelled(job->cancel))
    g_printerr("Image preview unavailable: %s\n", error->message);
  if (pix && !g_cancellable_is_cancelled(job->cancel)) {
    Menu *m = job->menu;
    GBytes *pixels = gdk_pixbuf_read_pixel_bytes(pix);
    GdkTexture *texture = GDK_TEXTURE(gdk_memory_texture_new(
        gdk_pixbuf_get_width(pix), gdk_pixbuf_get_height(pix),
        gdk_pixbuf_get_has_alpha(pix) ? GDK_MEMORY_R8G8B8A8 : GDK_MEMORY_R8G8B8,
        pixels, gdk_pixbuf_get_rowstride(pix)));
    gtk_picture_set_paintable(GTK_PICTURE(m->picture), GDK_PAINTABLE(texture));
    remember_preview(m, NULL, texture);
    g_object_unref(texture);
    g_bytes_unref(pixels);
    gtk_widget_set_visible(
        gtk_widget_get_parent(gtk_widget_get_parent(m->text)), FALSE);
    gtk_widget_set_visible(m->picture, TRUE);
    gtk_widget_set_visible(m->preview_box, TRUE);
  }
  g_clear_object(&pix);
  g_clear_error(&error);
  g_object_unref(job->cancel);
  g_free(job);
}
void menu_set_image_preview(Menu *m, GBytes *bytes) {
  if (!m->preview_cancel || g_cancellable_is_cancelled(m->preview_cancel)) {
    g_clear_object(&m->preview_cancel);
    m->preview_cancel = g_cancellable_new();
  }
  ImageJob *job = g_new0(ImageJob, 1);
  job->menu = m;
  job->cancel = g_object_ref(m->preview_cancel);
  GTask *task = g_task_new(NULL, m->preview_cancel, image_ready, job);
  g_task_set_task_data(task, g_bytes_ref(bytes), (GDestroyNotify)g_bytes_unref);
  g_task_run_in_thread(task, image_worker);
  g_object_unref(task);
}
typedef struct {
  Menu *m;
  GCancellable *c;
  gboolean image;
  guint timer;
} Preview;
static gboolean preview_timeout(gpointer data) {
  Preview *p = data;
  p->timer = 0;
  g_cancellable_cancel(p->c);
  return G_SOURCE_REMOVE;
}
static void preview_done(GObject *process, GAsyncResult *result,
                         gpointer data) {
  Preview *p = data;
  GBytes *out = NULL, *err = NULL;
  GError *e = NULL;
  gboolean ok = g_subprocess_communicate_finish(G_SUBPROCESS(process), result,
                                                &out, &err, &e);
  if (p->timer)
    g_source_remove(p->timer);
  if (!g_cancellable_is_cancelled(p->c) && ok &&
      g_subprocess_get_successful(G_SUBPROCESS(process))) {
    if (p->image)
      menu_set_image_preview(p->m, out);
    else {
      gsize n;
      const char *s = g_bytes_get_data(out, &n);
      char *t = n ? g_utf8_make_valid(s, MIN(n, 400000)) : g_strdup("");
      if (g_utf8_strlen(t, -1) > 100000)
        *g_utf8_offset_to_pointer(t, 100000) = 0;
      char *preview =
          n > strlen(t)
              ? g_strconcat(
                    t,
                    "\n… Preview truncated; copying keeps the complete text.",
                    NULL)
              : g_strdup(t);
      menu_set_text_preview(p->m, preview);
      g_free(preview);
      g_free(t);
    }
  }
  if (g_cancellable_is_cancelled(p->c))
    g_subprocess_force_exit(G_SUBPROCESS(process));
  g_clear_pointer(&out, g_bytes_unref);
  g_clear_pointer(&err, g_bytes_unref);
  g_clear_error(&e);
  g_object_unref(p->c);
  g_free(p);
}
void menu_preview_process(Menu *m, J *a, GBytes *input, gboolean image) {
  if (m->preview_cancel) {
    g_cancellable_cancel(m->preview_cancel);
    g_object_unref(m->preview_cancel);
  }
  m->preview_cancel = g_cancellable_new();
  size_t n = json_object_array_length(a);
  char **v = g_new0(char *, n + 1);
  for (size_t i = 0; i < n; i++)
    v[i] = g_strdup(js(json_object_array_get_idx(a, i)));
  GError *e = NULL;
  GSubprocess *p = g_subprocess_newv((const char *const *)v,
                                     G_SUBPROCESS_FLAGS_STDIN_PIPE |
                                         G_SUBPROCESS_FLAGS_STDOUT_PIPE |
                                         G_SUBPROCESS_FLAGS_STDERR_PIPE,
                                     &e);
  g_strfreev(v);
  json_object_put(a);
  if (!p) {
    g_clear_error(&e);
    return;
  }
  Preview *job = g_new0(Preview, 1);
  job->m = m;
  job->c = g_object_ref(m->preview_cancel);
  job->image = image;
  job->timer = g_timeout_add_seconds(3, preview_timeout, job);
  g_subprocess_communicate_async(p, input, m->preview_cancel, preview_done,
                                 job);
  g_object_unref(p);
}
static gboolean preview_delayed(gpointer data) {
  Menu *m = data;
  m->preview_timer = 0;
  Row *r = menu_selected(m);
  if (r && m->preview)
    m->preview(m, r);
  return G_SOURCE_REMOVE;
}
static void row_selected(GtkListBox *box, GtkListBoxRow *row, gpointer data) {
  (void)box;
  (void)row;
  Menu *m = data;
  if (m->preview_timer)
    g_source_remove(m->preview_timer);
  m->preview_timer = 0;
  if (m->preview_cancel)
    g_cancellable_cancel(m->preview_cancel);
  gtk_widget_set_visible(m->preview_box, m->previews);
  gtk_picture_set_paintable(GTK_PICTURE(m->picture), NULL);
  gtk_widget_set_visible(m->picture, FALSE);
  gtk_label_set_text(GTK_LABEL(m->text), "");
  gtk_widget_set_visible(gtk_widget_get_parent(gtk_widget_get_parent(m->text)),
                         FALSE);
  Row *selected = row ? g_object_get_data(G_OBJECT(row), "row") : NULL;
  if (restore_preview(m, selected))
    return;
  if (m->preview && row)
    m->preview_timer =
        g_timeout_add(m->cache_previews ? 40 : 100, preview_delayed, m);
}
static GtkWidget *label_new(const char *s, const char *css) {
  GtkWidget *w = gtk_label_new(s);
  gtk_label_set_xalign(GTK_LABEL(w), 0);
  gtk_label_set_ellipsize(GTK_LABEL(w), PANGO_ELLIPSIZE_END);
  gtk_label_set_single_line_mode(GTK_LABEL(w), TRUE);
  gtk_label_set_max_width_chars(GTK_LABEL(w), 1);
  gtk_widget_set_hexpand(w, TRUE);
  gtk_widget_add_css_class(w, css);
  gtk_widget_set_tooltip_text(w, s);
  return w;
}
void menu_refresh(Menu *m) {
  if (m->closed)
    return;
  GtkWidget *child;
  g_signal_handlers_block_by_func(m->list, row_selected, m);
  while ((child = gtk_widget_get_first_child(m->list)))
    gtk_list_box_remove(GTK_LIST_BOX(m->list), child);
  g_signal_handlers_unblock_by_func(m->list, row_selected, m);
  g_free(m->query);
  m->query = g_strdup(gtk_editable_get_text(GTK_EDITABLE(m->entry)));
  if (m->search)
    m->search(m, m->query);
  if (m->closed)
    return;
  guint count = 0;
  for (guint i = 0; !m->input && i < m->rows->len && count < 200; i++) {
    Row *r = g_ptr_array_index(m->rows, i);
    if (!m->search && !match(r->terms, m->query))
      continue;
    GtkWidget *row = gtk_list_box_row_new(),
              *box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
    gtk_widget_add_css_class(box, "item-box");
    GtkWidget *icon =
        r->gicon ? gtk_image_new_from_gicon(r->gicon)
                 : gtk_image_new_from_icon_name(r->icon ? r->icon : m->icon);
    gtk_image_set_pixel_size(GTK_IMAGE(icon), m->icon_size);
    gtk_widget_set_size_request(icon, m->icon_size, m->icon_size);
    gtk_widget_set_valign(icon, GTK_ALIGN_CENTER);
    gtk_widget_set_margin_end(icon, 10);
    gtk_widget_add_css_class(icon, "item-icon");
    gtk_box_append(GTK_BOX(box), icon);
    GtkWidget *text = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_widget_set_hexpand(text, TRUE);
    gtk_widget_set_valign(text, GTK_ALIGN_CENTER);
    GtkWidget *label = label_new(r->label, "item-text");
    gtk_box_append(GTK_BOX(text), label);
    if (m->font_rows) {
      PangoAttrList *a = pango_attr_list_new();
      char *font = g_strconcat(r->font ? r->font : r->label, " 12", NULL);
      PangoFontDescription *d = pango_font_description_from_string(font);
      pango_attr_list_insert(a, pango_attr_font_desc_new(d));
      gtk_label_set_attributes(GTK_LABEL(label), a);
      if (m->sample) {
        GtkWidget *s = label_new(m->sample, "item-text");
        gtk_label_set_attributes(GTK_LABEL(s), a);
        gtk_box_append(GTK_BOX(text), s);
      }
      pango_attr_list_unref(a);
      pango_font_description_free(d);
      g_free(font);
    }
    if (*r->sub)
      gtk_box_append(GTK_BOX(text), label_new(r->sub, "item-subtext"));
    gtk_box_append(GTK_BOX(box), text);
    gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(row), box);
    g_object_set_data(G_OBJECT(row), "row", r);
    gtk_list_box_append(GTK_LIST_BOX(m->list), row);
    count++;
  }
  GtkListBoxRow *row =
      gtk_list_box_get_row_at_index(GTK_LIST_BOX(m->list), m->selected);
  gtk_list_box_select_row(
      GTK_LIST_BOX(m->list),
      row ? row : gtk_list_box_get_row_at_index(GTK_LIST_BOX(m->list), 0));
  gtk_widget_set_visible(m->empty, !m->input && !count);
  gtk_widget_set_visible(m->scroll, !m->input && count);
  gtk_adjustment_set_value(
      gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(m->scroll)), 0);
}
void menu_query(Menu *m, const char *s) {
  if (!strcmp(gtk_editable_get_text(GTK_EDITABLE(m->entry)), s))
    menu_refresh(m);
  else
    gtk_editable_set_text(GTK_EDITABLE(m->entry), s);
  gtk_editable_set_position(GTK_EDITABLE(m->entry), -1);
  gtk_widget_grab_focus(m->entry);
}
static void changed(GtkEditable *e, gpointer data) {
  (void)e;
  menu_refresh(data);
}
static void activate(Menu *m, const char *action) {
  if (m->busy)
    return;
  m->busy = TRUE;
  Row *r = menu_selected(m);
  char *id = g_strdup(r          ? r->id
                      : m->input ? gtk_editable_get_text(GTK_EDITABLE(m->entry))
                                 : NULL);
  g_free(m->action);
  m->action = g_strdup(action);
  if (m->activate) {
    g_signal_handlers_block_by_func(m->entry, changed, m);
    gboolean keep = m->activate(m, r, action);
    g_signal_handlers_unblock_by_func(m->entry, changed, m);
    if (keep && !m->closed) {
      menu_refresh(m);
      gtk_widget_grab_focus(m->entry);
    } else if (!m->closed)
      menu_finish(m, id);
  } else if (id || strcmp(action, "enter"))
    menu_finish(m, id);
  g_free(id);
  m->busy = FALSE;
}
static void entry_activate(GtkEntry *e, gpointer data) {
  (void)e;
  activate(data, "enter");
}
static void row_activate(GtkListBox *b, GtkListBoxRow *r, gpointer data) {
  (void)b;
  (void)r;
  activate(data, "enter");
}
static void move(Menu *m, int delta) {
  GtkListBoxRow *r = gtk_list_box_get_selected_row(GTK_LIST_BOX(m->list));
  GtkWidget *last = gtk_widget_get_last_child(m->list);
  if (!last)
    return;
  int i = r ? gtk_list_box_row_get_index(r) : 0;
  r = gtk_list_box_get_row_at_index(
      GTK_LIST_BOX(m->list),
      CLAMP(i + delta, 0, gtk_list_box_row_get_index(GTK_LIST_BOX_ROW(last))));
  gtk_list_box_select_row(GTK_LIST_BOX(m->list), r);
  graphene_rect_t b;
  if (gtk_widget_compute_bounds(GTK_WIDGET(r), m->list, &b))
    gtk_adjustment_clamp_page(
        gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(m->scroll)),
        b.origin.y, b.origin.y + b.size.height);
}
/* Shared menu navigation mode. Free-text and password prompts remain editable. */
static void vim_search_mode(Menu *m, gboolean search) {
  m->vim_search = search;
  m->vim_pending_g = 0;
  gtk_editable_set_editable(GTK_EDITABLE(m->entry), search);
  gtk_entry_set_placeholder_text(GTK_ENTRY(m->entry), search
      ? (m->escape_closes ? "Search · Ctrl+Enter navigation · Esc close" : "Search · Esc returns to navigation") : "/ Search · j/k Move · h Back · l Open");
  gtk_widget_grab_focus(m->entry);
}
static gboolean key(GtkEventControllerKey *c, guint k, guint code,
                    GdkModifierType mods, gpointer data) {
  (void)c;
  (void)code;
  Menu *m = data;
  if (m->busy) {
    return TRUE;
  }

    int control_result=simple_control_key(GTK_WINDOW(m->window),k,mods);
    if(control_result>=0)return control_result;
  if (m->vim_navigation) {
    gboolean plain = !(mods & (GDK_CONTROL_MASK | GDK_ALT_MASK | GDK_SUPER_MASK | GDK_META_MASK));
    if (m->escape_closes && k == GDK_KEY_Escape) { menu_finish(m, NULL); return TRUE; }
    if (m->escape_closes && (mods & GDK_CONTROL_MASK) && (k == GDK_KEY_Return || k == GDK_KEY_KP_Enter)) { vim_search_mode(m, FALSE); return TRUE; }
    if (m->vim_search && k == GDK_KEY_Escape) {
      vim_search_mode(m, FALSE);
      return TRUE;
    }
    if (!m->vim_search) {
      if (plain && (k == GDK_KEY_slash || k == GDK_KEY_i)) {
        vim_search_mode(m, TRUE);
        return TRUE;
      }
      if (plain && k == GDK_KEY_q) { menu_finish(m, NULL); return TRUE; }
      if (plain && k == GDK_KEY_g) {
        gint64 now = g_get_monotonic_time();
        if (m->vim_pending_g && now - m->vim_pending_g < 2000000) {
          move(m, -G_MAXINT); m->vim_pending_g = 0;
        } else m->vim_pending_g = now;
        return TRUE;
      }
      m->vim_pending_g = 0;
      if (plain && k == GDK_KEY_G) { move(m, 1000000); return TRUE; }
      if (plain && k == GDK_KEY_r && obj(m->shortcuts, "r")) {
        activate(m, "r"); return TRUE;
      }
    }
  }
  char name[2] = {(char)gdk_keyval_to_lower(k), 0};
  if ((mods & GDK_CONTROL_MASK) && k < 128 && obj(m->shortcuts, name)) {
    activate(m, name);
    return TRUE;
  }
  GtkWidget *focus = gtk_window_get_focus(GTK_WINDOW(m->window));
  gboolean editing = m->password || GTK_IS_EDITABLE(focus) || GTK_IS_TEXT_VIEW(focus);
  if (m->vim_navigation && !m->vim_search) editing = FALSE;
  if (navigation_match(m->navigation, "cancel", k, mods, FALSE))
    menu_finish(m, NULL);
  else if (navigation_match(m->navigation, "activate", k, mods, editing))
    activate(m, "enter");
  else if (navigation_match(m->navigation, "down", k, mods, editing))
    move(m, 1);
  else if (navigation_match(m->navigation, "up", k, mods, editing))
    move(m, -1);
  else if (navigation_match(m->navigation, "page_down", k, mods, editing))
    move(m, 10);
  else if (navigation_match(m->navigation, "page_up", k, mods, editing))
    move(m, -10);
  else if (!m->input && !m->password && navigation_match(m->navigation, "left", k, mods, editing)) {
    if (m->navigate) m->navigate(m, "left");
    else if (obj(m->shortcuts,"left")) activate(m,"left");
    else menu_finish(m, NULL);
  } else if (!m->input && !m->password && navigation_match(m->navigation, "right", k, mods, editing)) {
    if (m->navigate) m->navigate(m, "right");
    else activate(m, "enter");
  } else if (k == GDK_KEY_Return || k == GDK_KEY_KP_Enter)
    return TRUE; /* A disabled/remapped activation must not reach GtkEntry. */
  else
    return FALSE;
  return TRUE;
}
static gboolean closed(GtkWindow *w, gpointer data) {
  (void)w;
  menu_finish(data, NULL);
  return TRUE;
}
static void outside(GtkGestureClick *c, int count, double x, double y,
                    gpointer data) {
  (void)c;
  (void)count;
  Menu *m = data;
  graphene_rect_t b;
  if (gtk_widget_compute_bounds(m->panel, m->outer, &b) &&
      !(x >= b.origin.x && x <= b.origin.x + b.size.width && y >= b.origin.y &&
        y <= b.origin.y + b.size.height))
    menu_finish(m, NULL);
}
static void shortcut_clicked(GtkButton *b, gpointer data) {
  activate(data, g_object_get_data(G_OBJECT(b), "key"));
}
static gboolean bench_close(gpointer data) {
  menu_finish(data, NULL);
  return G_SOURCE_REMOVE;
}
static void bench_paint(GdkFrameClock *c, gpointer data) {
  Menu *m = data;
  g_signal_handler_disconnect(c, m->frame_handler);
  g_printerr("BENCH first_us=%" G_GINT64_FORMAT "\n", g_get_monotonic_time());
  g_idle_add(bench_close, m);
}
char *menu_show(Menu *m) {
  g_setenv("GDK_BACKEND", "wayland", TRUE);
  if (!gtk_init_check()) {
    fail("A running Wayland session is required");
    return NULL;
  }
  const char *layer = str(obj(config, "ui"), "layer_shell");
  gboolean overlay = strcmp(layer, "off") && gtk_layer_is_supported();
  if (!strcmp(layer, "required") && !overlay) {
    fail("Wayland layer-shell unavailable");
    return NULL;
  }
  m->navigation = navigation_load(m->key_scope ? m->key_scope : keys_scope,
      m->keys_path ? m->keys_path : keys_override);
  if (last_error) return NULL;
  m->vim_navigation = !m->input && !m->password && g_key_file_get_boolean(m->navigation,"interaction","vim_navigation",NULL);
  m->closed = FALSE;
  m->loop = g_main_loop_new(NULL, FALSE);
  m->window = gtk_window_new();
  g_object_set_data(G_OBJECT(m->window), "sp-menu", m);
  gtk_window_set_title(GTK_WINDOW(m->window),
                       m->title ? m->title : "Simplepicker C");
  gtk_window_set_decorated(GTK_WINDOW(m->window), FALSE);
  gtk_widget_add_css_class(m->window, "simplepicker");
  gtk_widget_add_css_class(m->window, "window");
  if (overlay) {
    gtk_widget_add_css_class(m->window, "simplepicker-layer");
    gtk_layer_init_for_window(GTK_WINDOW(m->window));
    gtk_layer_set_namespace(GTK_WINDOW(m->window), "simplepicker-native-test");
    gtk_layer_set_layer(GTK_WINDOW(m->window), GTK_LAYER_SHELL_LAYER_OVERLAY);
    gtk_layer_set_keyboard_mode(GTK_WINDOW(m->window),
                                GTK_LAYER_SHELL_KEYBOARD_MODE_EXCLUSIVE);
    for (int e = 0; e < GTK_LAYER_SHELL_EDGE_ENTRY_NUMBER; e++)
      gtk_layer_set_anchor(GTK_WINDOW(m->window), e, TRUE);
    gtk_layer_set_exclusive_zone(GTK_WINDOW(m->window), -1);
  } else
    gtk_window_set_default_size(GTK_WINDOW(m->window), m->width + 80,
                                m->height + 80);
  GtkCssProvider *base = gtk_css_provider_new(), *css = gtk_css_provider_new();
  gtk_css_provider_load_from_string(
      base, "window.simplepicker-layer {background:transparent;} .simplepicker "
            ".box-wrapper {padding:20px;} .simplepicker .item-box "
            "{padding:8px;} .simplepicker .simplepicker-brand {opacity:.5;} "
            "window.websearch .websearch-title {color:#f3a40a;font-size:1.35rem;font-weight:bold;}");
  GdkDisplay *display = gdk_display_get_default();
  gtk_style_context_add_provider_for_display(
      display, GTK_STYLE_PROVIDER(base),
      GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  char *theme = m->theme ? expand(m->theme, NULL) : theme_path(FALSE);
  {
    simple_theme_load(css, theme);
    gtk_style_context_add_provider_for_display(
        display, GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_USER);
  }
  g_free(theme);
  m->outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
  gtk_widget_set_hexpand(m->outer, TRUE);
  gtk_widget_set_vexpand(m->outer, TRUE);
  gtk_window_set_child(GTK_WINDOW(m->window), m->outer);
  m->panel = gtk_box_new(GTK_ORIENTATION_VERTICAL, 10);
  gtk_widget_set_halign(m->panel, GTK_ALIGN_CENTER);
  gtk_widget_set_valign(m->panel, GTK_ALIGN_CENTER);
  gtk_widget_set_vexpand(m->panel, TRUE);
  gtk_widget_add_css_class(m->panel, "background");
  gtk_widget_add_css_class(m->panel, "box-wrapper");
  gtk_widget_set_size_request(m->panel, MAX(240, m->width),
                              m->input ? 80 : MAX(100, m->height));
  gtk_widget_set_margin_start(m->panel, 40);
  gtk_widget_set_margin_end(m->panel, 40);
  gtk_widget_set_margin_top(m->panel, 40);
  gtk_widget_set_margin_bottom(m->panel, 40);
  gtk_box_append(GTK_BOX(m->outer), m->panel);
  if (m->heading) {
    GtkWidget *heading=gtk_label_new(m->heading);
    gtk_label_set_xalign(GTK_LABEL(heading),0);
    gtk_widget_add_css_class(heading,"simpleclip-heading");
    gtk_box_append(GTK_BOX(m->panel),heading);
    GtkCssProvider *brand=gtk_css_provider_new();
    gtk_css_provider_load_from_string(brand,".simpleclip-heading {color:@simple_heading;font-size:18px;font-weight:bold;margin-bottom:8px;}");
    gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(brand),GTK_STYLE_PROVIDER_PRIORITY_USER+1);
    g_object_unref(brand);
  }
  GtkWidget *search = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_widget_add_css_class(search, "search-container");
  gtk_widget_set_overflow(search, GTK_OVERFLOW_HIDDEN);
  m->entry = gtk_entry_new();
  gtk_entry_set_placeholder_text(GTK_ENTRY(m->entry),
                                 m->prompt ? m->prompt : "Search");
  gtk_entry_set_visibility(GTK_ENTRY(m->entry), !m->password);
  gtk_widget_set_hexpand(m->entry, TRUE);
  gtk_widget_add_css_class(m->entry, "input");
  GtkWidget *icon =
      gtk_image_new_from_icon_name(m->password ? "dialog-password" : m->icon);
  gtk_image_set_pixel_size(GTK_IMAGE(icon), 22);
  gtk_widget_set_margin_start(icon, 10);
  gtk_widget_set_margin_end(icon, 10);
  gtk_box_append(GTK_BOX(search), icon);
  gtk_box_append(GTK_BOX(search), m->entry);
  gtk_box_append(GTK_BOX(m->panel), search);
  m->list = gtk_list_box_new();
  gtk_list_box_set_selection_mode(GTK_LIST_BOX(m->list), GTK_SELECTION_SINGLE);
  gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(m->list), TRUE);
  gtk_widget_set_focusable(m->list, FALSE);
  gtk_widget_add_css_class(m->list, "list");
  m->scroll = gtk_scrolled_window_new();
  gtk_widget_set_hexpand(m->scroll, TRUE);
  gtk_widget_set_vexpand(m->scroll, TRUE);
  gtk_widget_add_css_class(m->scroll, "scroll");
  gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(m->scroll),
                                 GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(m->scroll), m->list);
  GtkWidget *content = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 10);
  gtk_widget_set_vexpand(content, TRUE);
  gtk_box_append(GTK_BOX(content), m->scroll);
  gtk_box_append(GTK_BOX(m->panel), content);
  m->preview_box = gtk_overlay_new();
  GtkWidget *space = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
  gtk_widget_set_size_request(space, 500, 400);
  gtk_overlay_set_child(GTK_OVERLAY(m->preview_box), space);
  m->picture = gtk_picture_new();
  gtk_picture_set_can_shrink(GTK_PICTURE(m->picture), TRUE);
  gtk_picture_set_content_fit(GTK_PICTURE(m->picture), GTK_CONTENT_FIT_CONTAIN);
  gtk_widget_add_css_class(m->picture, "preview");
  gtk_overlay_add_overlay(GTK_OVERLAY(m->preview_box), m->picture);
  GtkWidget *text_scroll = gtk_scrolled_window_new();
  gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(text_scroll),
                                 GTK_POLICY_NEVER, GTK_POLICY_AUTOMATIC);
  m->text = gtk_label_new("");
  gtk_label_set_xalign(GTK_LABEL(m->text), 0);
  gtk_label_set_yalign(GTK_LABEL(m->text), 0);
  gtk_label_set_selectable(GTK_LABEL(m->text), TRUE);
  gtk_label_set_wrap(GTK_LABEL(m->text), TRUE);
  gtk_label_set_wrap_mode(GTK_LABEL(m->text), PANGO_WRAP_WORD_CHAR);
  gtk_widget_add_css_class(m->text, "item-text");
  gtk_widget_set_margin_start(m->text, 12);
  gtk_widget_set_margin_end(m->text, 12);
  gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(text_scroll), m->text);
  gtk_overlay_add_overlay(GTK_OVERLAY(m->preview_box), text_scroll);
  gtk_widget_set_visible(m->preview_box, m->previews);
  gtk_box_append(GTK_BOX(content), m->preview_box);
  if (m->previews)
    gtk_widget_set_size_request(m->scroll, 500, -1);
  m->empty = gtk_label_new("No Results");
  gtk_widget_add_css_class(m->empty, "empty-label");
  gtk_widget_set_vexpand(m->empty, TRUE);
  gtk_box_append(GTK_BOX(m->panel), m->empty);
  GtkWidget *footer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
  json_object_object_foreach(m->shortcuts, k, v) {
    char *label;
    if (g_key_file_has_key(m->navigation,"navigation",k,NULL)) {
      char *binding=navigation_label(m->navigation,k);
      label=g_strdup_printf("%s · %s",js(v),binding);g_free(binding);
    } else label = g_strdup_printf("%s · Ctrl+%c", js(v), g_ascii_toupper(*k));
    GtkWidget *b = gtk_button_new_with_label(label);
    g_free(label);
    gtk_widget_add_css_class(b, "item-subtext");
    g_object_set_data_full(G_OBJECT(b), "key", g_strdup(k), g_free);
    g_signal_connect(b, "clicked", G_CALLBACK(shortcut_clicked), m);
    gtk_box_append(GTK_BOX(footer), b);
  }
  char *up=navigation_label(m->navigation,"up"), *down=navigation_label(m->navigation,"down");
  char *left=navigation_label(m->navigation,"left"), *right=navigation_label(m->navigation,"right");
  char *enter=navigation_label(m->navigation,"activate");
  char *hint=m->navigate ? g_strdup_printf("%s/%s Move · %s/%s Switch · %s Search",up,down,left,right,enter)
      : g_strdup_printf("%s/%s Move · %s Open",up,down,enter);
  if (m->vim_navigation) {
    g_free(hint);
    hint = g_strdup(m->escape_closes ? "Ctrl+j/k Move · Ctrl+Enter Navigation · Enter Copy · Esc Close" : "j/k Move · h Back · l/Enter Open · gg/G Ends · / Search · q Close");
  }
  GtkWidget *brand = gtk_label_new(hint);
  g_free(hint);g_free(up);g_free(down);g_free(left);g_free(right);g_free(enter);
  gtk_label_set_xalign(GTK_LABEL(brand), 1);
  gtk_widget_set_hexpand(brand, TRUE);
  gtk_widget_add_css_class(brand, "simplepicker-brand");
  gtk_box_append(GTK_BOX(footer), brand);
  gtk_box_append(GTK_BOX(m->panel), footer);
  GtkEventController *keys = gtk_event_controller_key_new();
  gtk_event_controller_set_propagation_phase(keys, GTK_PHASE_CAPTURE);
  g_signal_connect(keys, "key-pressed", G_CALLBACK(key), m);
  gtk_widget_add_controller(m->window, keys);
  GtkGesture *click = gtk_gesture_click_new();
  gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(click),
                                             GTK_PHASE_CAPTURE);
  g_signal_connect(click, "pressed", G_CALLBACK(outside), m);
  gtk_widget_add_controller(m->outer, GTK_EVENT_CONTROLLER(click));
  g_signal_connect(m->entry, "changed", G_CALLBACK(changed), m);
  g_signal_connect(m->entry, "activate", G_CALLBACK(entry_activate), m);
  g_signal_connect(m->list, "row-activated", G_CALLBACK(row_activate), m);
  g_signal_connect(m->list, "row-selected", G_CALLBACK(row_selected), m);
  g_signal_connect(m->window, "close-request", G_CALLBACK(closed), m);
  if (m->initial && *m->initial)
    gtk_editable_set_text(GTK_EDITABLE(m->entry), m->initial);
  else
    menu_refresh(m);
  if (!m->closed) {
    if (m->vim_navigation) vim_search_mode(m, m->start_in_search);
    gtk_window_present(GTK_WINDOW(m->window));
    gtk_widget_grab_focus(m->entry);
    if (m->benchmark)
      m->frame_handler =
          g_signal_connect(gtk_widget_get_frame_clock(m->window), "after-paint",
                           G_CALLBACK(bench_paint), m);
    g_main_loop_run(m->loop);
  }
  gtk_style_context_remove_provider_for_display(display,
                                                GTK_STYLE_PROVIDER(css));
  gtk_style_context_remove_provider_for_display(display,
                                                GTK_STYLE_PROVIDER(base));
  g_object_unref(css);
  g_object_unref(base);
  g_main_loop_unref(m->loop);
  return m->result;
}
