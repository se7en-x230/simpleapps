#include "sp.h"
#include <limits.h>
gboolean sp_benchmark;
static void diagnostics(gboolean doctor) {
  g_print("Config valid: %s\nDesktop backend: %s\n", config_path, backend());
  if (!doctor)
    return;
  const char *helpers[] = {"wl-copy", "wl-paste", "cliphist", "qalc", "file",
                           "fc-list", "xdg-open", "wtype", "ffmpeg", NULL};
  for (int i = 0; helpers[i]; i++) {
    char *p = g_find_program_in_path(helpers[i]);
    g_print("%s: %s\n", helpers[i], p ? "found" : "not on PATH");
    g_free(p);
  }
  g_print("Native C/GTK. No configured commands were run.\n");
}
int main(int argc, char **argv) {
  setlocale(LC_ALL, "");
  char *mode = NULL, *prompt = NULL, *input = NULL, *query = NULL,
       *search = NULL, *cfg = NULL, *icon = NULL;
  int width = 600, height = 570, selected = 0, lines = 0, ignored = 0;
  gboolean dmenu = FALSE, input_only = FALSE, password = FALSE, check = FALSE,
           doctor = FALSE, bridge = FALSE, editor = FALSE, ignore = FALSE;
  const char *names[] = {
      "power",        "apps",          "runner", "websearch", "bookmarks",
      "bookmark-add", "bookmark-edit", "calc",   "clipboard", "windows",
      "symbols",      "fonts", "dashboard", "screensaver", "screensaver-stop", NULL};
  gboolean modes[15] = {0};
  GOptionEntry options[] = {
      {"provider", 'm', 0, G_OPTION_ARG_STRING, &mode, "Built-in mode", "MODE"},
      {"dmenu", 'd', 0, G_OPTION_ARG_NONE, &dmenu, "Read choices from stdin",
       NULL},
      {"input-only", 'I', 0, G_OPTION_ARG_NONE, &input_only, "Free text entry",
       NULL},
      {"password", 'x', 0, G_OPTION_ARG_NONE, &password, "Masked text entry",
       NULL},
      {"prompt", 'p', 0, G_OPTION_ARG_STRING, &prompt, "Entry prompt", "TEXT"},
      {"width", 0, 0, G_OPTION_ARG_INT, &width, "Panel width", "N"},
      {"height", 0, 0, G_OPTION_ARG_INT, &height, "Panel height", "N"},
      {"selected-row", 0, 0, G_OPTION_ARG_INT, &selected,
       "Initial selected row", "N"},
      {"lines", 'l', 0, G_OPTION_ARG_INT, &lines, "Visible lines", "N"},
      {"icon", 0, 0, G_OPTION_ARG_STRING, &icon, "Default theme icon", "NAME"},
      {"theme", 0, 0, G_OPTION_ARG_FILENAME, &theme_override, "CSS override",
       "FILE"},
      {"keys", 0, 0, G_OPTION_ARG_FILENAME, &keys_override, "Navigation override", "FILE"},
      {"query", 0, 0, G_OPTION_ARG_STRING, &query, "Initial query", "TEXT"},
      {"input", 0, 0, G_OPTION_ARG_FILENAME, &input, "Read choices from a file",
       "FILE"},
      {"search", 0, 0, G_OPTION_ARG_STRING, &search,
       "Print matches without GUI", "TEXT"},
      {"config", 0, 0, G_OPTION_ARG_FILENAME, &cfg, "Alternate config", "FILE"},
      {"check-config", 0, 0, G_OPTION_ARG_NONE, &check, "Validate config",
       NULL},
      {"doctor", 0, 0, G_OPTION_ARG_NONE, &doctor, "Check dependencies", NULL},
      {"bridge", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_NONE, &bridge,
       "Script bridge", NULL},
      {"bookmark-editor", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_NONE, &editor,
       "Bookmark editor", NULL},
      {"benchmark", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_NONE, &sp_benchmark,
       "Render and close without actions", NULL},
      {"case-insensitive", 'i', G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_NONE,
       &ignore, NULL, NULL},
      {"compat-H", 'H', G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_NONE, &ignore, NULL,
       NULL},
      {"minwidth", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_INT, &ignored, NULL,
       "N"},
      {"maxwidth", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_INT, &ignored, NULL,
       "N"},
      {"minheight", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_INT, &ignored, NULL,
       "N"},
      {"maxheight", 0, G_OPTION_FLAG_HIDDEN, G_OPTION_ARG_INT, &ignored, NULL,
       "N"},
      {NULL}};
  GOptionEntry mode_options[16] = {0};
  for (int i = 0; names[i]; i++) {
    mode_options[i].long_name = names[i];
    mode_options[i].arg = G_OPTION_ARG_NONE;
    mode_options[i].arg_data = &modes[i];
    mode_options[i].description = names[i];
  }
  GOptionContext *context = g_option_context_new("— native GTK/Wayland picker");
  g_option_context_add_main_entries(context, options, NULL);
  g_option_context_add_main_entries(context, mode_options, NULL);
  GError *e = NULL;
  if (!g_option_context_parse(context, &argc, &argv, &e)) {
    g_printerr("%s\n", e->message);
    g_error_free(e);
    return 2;
  }
  if (argc != 1) {
    g_printerr("Unexpected argument\n");
    return 2;
  }
  for (int i = 0; names[i]; i++)
    if (modes[i]) {
      if (mode) {
        g_printerr("Choose one provider\n");
        return 2;
      }
      mode = g_strdup(names[i]);
    }
  char *exe = g_file_read_link("/proc/self/exe", NULL),
       *dir = g_path_get_dirname(exe ? exe : argv[0]);
  asset_dir = g_getenv("SIMPLEPICKER_ASSETS")
                  ? g_strdup(g_getenv("SIMPLEPICKER_ASSETS"))
                  : path_join(dir, "assets");
  if (!g_file_test(asset_dir, G_FILE_TEST_IS_DIR)) {
    g_free(asset_dir);
    asset_dir = g_build_filename(dir, "..", "share", "simplepicker", NULL);
  }
  if(!g_getenv("SIMPLEPICKER_ASSETS")&&!g_file_test(asset_dir,G_FILE_TEST_IS_DIR)) {
    g_free(asset_dir);asset_dir=g_build_filename(g_get_user_data_dir(),"simplepicker",NULL);
  }
  g_free(dir);
  g_free(exe);
  data_dir =
      g_getenv("SIMPLEPICKER_DATA_DIR")
          ? expand(g_getenv("SIMPLEPICKER_DATA_DIR"), NULL)
          : g_build_filename(g_get_user_data_dir(), "simplepicker", NULL);
  int result = 0;
  if (!load_config(cfg))
    goto error;
  if (theme_override) {
    char *t = theme_path(FALSE);
    g_free(t);
    if (last_error)
      goto error;
  }
  if (check || doctor) {
    GKeyFile *keys=navigation_load(mode,keys_override);
    g_key_file_unref(keys);
    if (last_error) goto error;
    diagnostics(doctor);
    goto done;
  }
  if (bridge) {
    result = bridge_main();
    goto done;
  }
  if (editor) {
    result = bookmark_editor();
    goto done;
  }
  if (mode ||
      (!dmenu && !input_only && !password && !search && isatty(STDIN_FILENO))) {
    const char *name = mode ? mode : "apps";
    if (g_str_has_prefix(name, "menus:"))
      name += 6;
    keys_scope = name;
    result = provider(name);
    goto done;
  }
  Menu *m = menu_new("Simplepicker C", prompt ? prompt : "Search");
  m->input = input_only || password;
  m->password = password;
  m->width = MAX(240, width);
  m->height =
      lines > 0 ? (int)MIN((gint64)lines * 37 + 100, 10000) : MAX(100, height);
  m->selected = MAX(0, selected);
  m->initial = query;
  m->icon = icon ? icon : "view-list-symbolic";
  if (!m->input) {
    FILE *f = input ? fopen(input, "r") : stdin;
    if (!f) {
      fail("Cannot open input file");
      menu_free(m);
      goto error;
    }
    char *line = NULL;
    size_t n = 0;
    ssize_t len;
    while ((len = getline(&line, &n, f)) >= 0) {
      if (memchr(line, 0, len) || !g_utf8_validate(line, len, NULL)) {
        fail("Input must be UTF-8 without NUL");
        break;
      }
      if (len && line[len - 1] == '\n')
        line[--len] = 0;
      if (len && line[len - 1] == '\r')
        line[--len] = 0;
      g_ptr_array_add(m->rows, row_new(line, line, NULL, NULL));
    }
    free(line);
    if (ferror(f))
      fail("Input read failed");
    if (input)
      fclose(f);
  }
  if (last_error) {
    menu_free(m);
    goto error;
  }
  if (search) {
    for (guint i = 0; i < m->rows->len; i++) {
      Row *r = g_ptr_array_index(m->rows, i);
      if (match(r->terms, search))
        puts(r->id);
    }
  } else {
    char *s = menu_show(m);
    if (s)
      puts(s);
    else
      result = 1;
  }
  menu_free(m);
done:
  if (last_error)
    goto error;
  g_option_context_free(context);
  return result;
error:
  g_printerr("simplepicker: %s\n", last_error ? last_error : "Unknown error");
  return 2;
}
