#include "simple-theme.h"
#include "sp.h"
#include <errno.h>
#include <glib-unix.h>
#include <stddef.h>
#include <sys/socket.h>
#include <sys/un.h>
typedef struct {
  Menu *m;
  J *actions;
  GPtrArray *images;
  int fd;
} Power;
static void click(GtkButton *b, gpointer data) {
  Power *p = data;
  menu_finish(p->m, g_object_get_data(G_OBJECT(b), "action"));
}
static gboolean key(GtkEventControllerKey *c, guint k, guint code,
                    GdkModifierType mods, gpointer data) {
  (void)c;
  (void)code;
  Power *p = data;
  if (navigation_match(p->m->navigation, "cancel", k, mods, FALSE) ||
      (k == GDK_KEY_BackSpace && (mods & GDK_SUPER_MASK))) {
    menu_finish(p->m, NULL);
    return TRUE;
  }
  /* Preserve the advertised single-letter power actions (notably h/l).
   * Ctrl+H/J/K/L and arrows navigate without invoking those actions. */
  gboolean action_key = FALSE;
  if (!(mods & (GDK_CONTROL_MASK | GDK_ALT_MASK | GDK_SUPER_MASK))) {
    json_object_object_foreach(p->actions, name, spec) {
      (void)name;
      if (gdk_keyval_to_lower(k) == (guint)g_ascii_tolower(*str(spec, "key")))
        action_key = TRUE;
    }
  }
  if (!action_key) {
    const char *directions[] = {"up", "left", "down", "right"};
    for (int i = 0; i < 4; i++) {
      if (navigation_match(p->m->navigation, directions[i], k, mods, FALSE)) {
        gtk_window_set_focus_visible(GTK_WINDOW(p->m->window), TRUE);
        gtk_widget_child_focus(p->m->panel, i < 2 ? GTK_DIR_TAB_BACKWARD : GTK_DIR_TAB_FORWARD);
        return TRUE;
      }
    }
  }
  if (navigation_match(p->m->navigation, "activate", k, mods, FALSE)) {
    GtkWidget *focus = gtk_window_get_focus(GTK_WINDOW(p->m->window));
    if (GTK_IS_BUTTON(focus)) click(GTK_BUTTON(focus), p);
    return TRUE;
  }
  if (mods & (GDK_CONTROL_MASK | GDK_ALT_MASK | GDK_SUPER_MASK))
    return FALSE;
  json_object_object_foreach(p->actions, name, spec) {
    if (gdk_keyval_to_lower(k) == (guint)g_ascii_tolower(*str(spec, "key"))) {
      menu_finish(p->m, name);
      return TRUE;
    }
  }
  return FALSE;
}
static gboolean closed(GtkWindow *w, gpointer data) {
  (void)w;
  Power *p = data;
  menu_finish(p->m, NULL);
  return TRUE;
}
static void outside(GtkGestureClick *g, int n, double x, double y,
                    gpointer data) {
  (void)g;
  (void)n;
  Power *p = data;
  graphene_rect_t b;
  if (gtk_widget_compute_bounds(p->m->panel, p->m->outer, &b) &&
      !(x >= b.origin.x && x <= b.origin.x + b.size.width && y >= b.origin.y &&
        y <= b.origin.y + b.size.height))
    menu_finish(p->m, NULL);
}
static void resize(GtkWidget *w, GParamSpec *spec, gpointer data) {
  (void)spec;
  Power *p = data;
  int width = gtk_widget_get_width(w), height = gtk_widget_get_height(w);
  if (width < 1 || height < 1)
    return;
  gtk_widget_set_size_request(p->m->panel, MAX(600, (int)(width * .685)),
                              (int)(height * .44));
  for (guint i = 0; i < p->images->len; i++)
    gtk_image_set_pixel_size(
        g_ptr_array_index(p->images, i),
        MAX(32, (int)(width * .685 / MAX(1, p->images->len) * .2)));
}
static gboolean idle_resize(gpointer data) {
  Power *p = data;
  resize(p->m->window, NULL, p);
  return G_SOURCE_REMOVE;
}
static gboolean receive(int fd, GIOCondition cond, gpointer data) {
  (void)cond;
  char b[64];
  if (recv(fd, b, sizeof b, 0) > 0) {
    Power *p = data;
    menu_finish(p->m, NULL);
  }
  return G_SOURCE_CONTINUE;
}
int power_show(void) {
  int fd = socket(AF_UNIX, SOCK_DGRAM | SOCK_NONBLOCK, 0);
  struct sockaddr_un addr = {.sun_family = AF_UNIX};
  snprintf(addr.sun_path + 1, sizeof(addr.sun_path) - 1,
           "simplepicker-native-power-%u-%s", getuid(),
           g_getenv("WAYLAND_DISPLAY") ? g_getenv("WAYLAND_DISPLAY")
                                       : "default");
  socklen_t len =
      offsetof(struct sockaddr_un, sun_path) + 1 + strlen(addr.sun_path + 1);
  if (fd < 0) {
    fail("Cannot create power toggle socket");
    return 2;
  }
  if (bind(fd, (struct sockaddr *)&addr, len)) {
    if (errno == EADDRINUSE) {
      sendto(fd, "close", 5, 0, (struct sockaddr *)&addr, len);
      close(fd);
      return 0;
    }
    close(fd);
    fail("Cannot bind power toggle socket");
    return 2;
  }
  g_setenv("GDK_BACKEND", "wayland", TRUE);
  if (!gtk_init_check()) {
    close(fd);
    fail("A running Wayland session is required");
    return 2;
  }
  J *actions = json_object_new_object();
  {
    json_object_object_foreach(obj(config, "power"), name, spec) {
      if (!yes(spec, "enabled"))
        continue;
      J *a = expand_argv(obj(spec, "command"), NULL);
      if (!strcmp(name, "logout") && !json_object_array_length(a)) {
        json_object_put(a);
        a = logout_argv();
      }
      if (json_object_array_length(a)) {
        J *s = jclone(spec);
        json_object_object_add(s, "command", a);
        json_object_object_add(actions, name, s);
      } else
        json_object_put(a);
    }
  }
  if (!json_object_object_length(actions)) {
    json_object_put(actions);
    close(fd);
    fail("No power actions enabled");
    return 2;
  }
  Menu *m = menu_new("Power", "");
  m->navigation = navigation_load(keys_scope ? keys_scope : "power", keys_override);
  if (last_error) {
    menu_free(m);
    json_object_put(actions);
    close(fd);
    return 2;
  }
  m->loop = g_main_loop_new(NULL, FALSE);
  m->window = gtk_window_new();
  g_object_set_data(G_OBJECT(m->window), "sp-power", m);
  gtk_window_set_title(GTK_WINDOW(m->window), "Simplepicker C — Power");
  gtk_window_set_decorated(GTK_WINDOW(m->window), FALSE);
  gtk_widget_add_css_class(m->window, "simplepicker-power");
  const char *layer = str(obj(config, "ui"), "layer_shell");
  gboolean overlay = strcmp(layer, "off") && gtk_layer_is_supported();
  if (!strcmp(layer, "required") && !overlay) {
    fail("Wayland layer-shell unavailable");
    gtk_window_destroy(GTK_WINDOW(m->window));
    g_main_loop_unref(m->loop);
    menu_free(m);
    json_object_put(actions);
    close(fd);
    return 2;
  }
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
    gtk_window_set_default_size(GTK_WINDOW(m->window), 1100, 600);
  GtkCssProvider *base = gtk_css_provider_new(), *css = gtk_css_provider_new();
  gtk_css_provider_load_from_string(
      base, "window.simplepicker-layer {background:transparent;} "
            ".simplepicker-power button {padding:12px;}");
  GdkDisplay *display = gdk_display_get_default();
  gtk_style_context_add_provider_for_display(
      display, GTK_STYLE_PROVIDER(base),
      GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
  char *theme = theme_path(TRUE);
  {
    simple_theme_load(css, theme);
    gtk_style_context_add_provider_for_display(
        display, GTK_STYLE_PROVIDER(css), GTK_STYLE_PROVIDER_PRIORITY_USER);
  }
  g_free(theme);
  m->outer = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
  gtk_window_set_child(GTK_WINDOW(m->window), m->outer);
  m->panel = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 0);
  gtk_box_set_homogeneous(GTK_BOX(m->panel), TRUE);
  gtk_widget_set_halign(m->panel, GTK_ALIGN_CENTER);
  gtk_widget_set_valign(m->panel, GTK_ALIGN_CENTER);
  gtk_widget_set_vexpand(m->panel, TRUE);
  gtk_box_append(GTK_BOX(m->outer), m->panel);
  Power state = {m, actions, g_ptr_array_new(), fd};
  const char *names[] = {"lock",     "logout",    "suspend",
                         "shutdown", "hibernate", "reboot"};
  const char *icons[] = {
      "system-lock-screen-symbolic",   "system-log-out-symbolic",
      "media-playback-pause-symbolic", "system-shutdown-symbolic",
      "weather-clear-night-symbolic",  "system-reboot-symbolic"};
  json_object_object_foreach(actions, name, spec) {
    GtkWidget *b = gtk_button_new();
    gtk_widget_set_name(b, name);
    GtkWidget *box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 24);
    gtk_widget_set_halign(box, GTK_ALIGN_CENTER);
    gtk_widget_set_valign(box, GTK_ALIGN_CENTER);
    char *ic = *str(spec, "icon") ? icon_path(str(spec, "icon")) : NULL;
    const char *default_icon = "system-shutdown-symbolic";
    for (int i = 0; i < 6; i++)
      if (!strcmp(name, names[i]))
        default_icon = icons[i];
    GtkWidget *image = ic ? (strchr(ic, '/') ? gtk_image_new_from_file(ic)
                                             : gtk_image_new_from_icon_name(ic))
                          : gtk_image_new_from_icon_name(default_icon);
    g_free(ic);
    g_ptr_array_add(state.images, image);
    gtk_box_append(GTK_BOX(box), image);
    char *label =
        g_strdup_printf("%s (%s)", str(spec, "label"), str(spec, "key"));
    gtk_box_append(GTK_BOX(box), gtk_label_new(label));
    gtk_widget_set_tooltip_text(b, label);
    g_free(label);
    gtk_button_set_child(GTK_BUTTON(b), box);
    g_object_set_data_full(G_OBJECT(b), "action", g_strdup(name), g_free);
    g_signal_connect(b, "clicked", G_CALLBACK(click), &state);
    gtk_box_append(GTK_BOX(m->panel), b);
  }
  GtkEventController *keys = gtk_event_controller_key_new();
  gtk_event_controller_set_propagation_phase(keys, GTK_PHASE_CAPTURE);
  g_signal_connect(keys, "key-pressed", G_CALLBACK(key), &state);
  gtk_widget_add_controller(m->window, keys);
  GtkGesture *g = gtk_gesture_click_new();
  gtk_event_controller_set_propagation_phase(GTK_EVENT_CONTROLLER(g),
                                             GTK_PHASE_CAPTURE);
  g_signal_connect(g, "pressed", G_CALLBACK(outside), &state);
  gtk_widget_add_controller(m->outer, GTK_EVENT_CONTROLLER(g));
  g_signal_connect(m->window, "close-request", G_CALLBACK(closed), &state);
  g_signal_connect(m->window, "notify::width", G_CALLBACK(resize), &state);
  g_signal_connect(m->window, "notify::height", G_CALLBACK(resize), &state);
  guint watch = g_unix_fd_add(fd, G_IO_IN, receive, &state);
  gtk_window_present(GTK_WINDOW(m->window));
  gtk_widget_grab_focus(gtk_widget_get_first_child(m->panel));
  guint resize_idle = g_idle_add(idle_resize, &state);
  g_main_loop_run(m->loop);
  if (g_main_context_find_source_by_id(NULL, resize_idle))
    g_source_remove(resize_idle);
  g_source_remove(watch);
  close(fd);
  gtk_style_context_remove_provider_for_display(display,
                                                GTK_STYLE_PROVIDER(css));
  gtk_style_context_remove_provider_for_display(display,
                                                GTK_STYLE_PROVIDER(base));
  g_object_unref(css);
  g_object_unref(base);
  g_main_loop_unref(m->loop);
  if (m->result) {
    char *s =
        run_text(jclone(obj(obj(actions, m->result), "command")), NULL, 10);
    g_free(s);
  }
  g_ptr_array_unref(state.images);
  json_object_put(actions);
  menu_free(m);
  return last_error ? 2 : 0;
}
