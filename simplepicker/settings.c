#include "sp.h"
static J *table_json(toml_table_t *);
static J *array_json(toml_array_t *a) {
  J *j = json_object_new_array();
  for (int i = 0; i < toml_array_nelem(a); i++) {
    toml_datum_t v;
    toml_table_t *t = toml_table_at(a, i);
    toml_array_t *b = toml_array_at(a, i);
    if (t)
      json_object_array_add(j, table_json(t));
    else if (b)
      json_object_array_add(j, array_json(b));
    else if ((v = toml_string_at(a, i)).ok) {
      json_object_array_add(j, json_object_new_string(v.u.s));
      free(v.u.s);
    } else if ((v = toml_bool_at(a, i)).ok)
      json_object_array_add(j, json_object_new_boolean(v.u.b));
    else if ((v = toml_int_at(a, i)).ok)
      json_object_array_add(j, json_object_new_int64(v.u.i));
    else {
      fail("Unsupported TOML array value");
      json_object_put(j);
      return NULL;
    }
  }
  return j;
}
static J *table_json(toml_table_t *t) {
  J *j = json_object_new_object();
  const char *k;
  for (int i = 0; (k = toml_key_in(t, i)); i++) {
    toml_datum_t v;
    toml_table_t *b = toml_table_in(t, k);
    toml_array_t *a = toml_array_in(t, k);
    J *value = NULL;
    if (b)
      value = table_json(b);
    else if (a)
      value = array_json(a);
    else if ((v = toml_string_in(t, k)).ok) {
      value = json_object_new_string(v.u.s);
      free(v.u.s);
    } else if ((v = toml_bool_in(t, k)).ok)
      value = json_object_new_boolean(v.u.b);
    else if ((v = toml_int_in(t, k)).ok)
      value = json_object_new_int64(v.u.i);
    else
      fail("Unsupported setting: %s", k);
    if (!value) {
      json_object_put(j);
      return NULL;
    }
    json_object_object_add(j, k, value);
  }
  return j;
}
static gboolean merge(J *base, J *incoming, const char *prefix) {
  if (!json_object_is_type(incoming, json_type_object)) {
    fail("%s must be a table", prefix);
    return FALSE;
  }
  json_object_object_foreach(incoming, k, v) {
    J *b = obj(base, k);
    char *n = g_strdup_printf("%s%s", prefix, k);
    if (!b) {
      fail("Unknown setting: %s", n);
      g_free(n);
      return FALSE;
    }
    if (json_object_get_type(b) != json_object_get_type(v)) {
      fail("Invalid type: %s", n);
      g_free(n);
      return FALSE;
    }
    if (json_object_is_type(b, json_type_object)) {
      char *p = g_strconcat(n, ".", NULL);
      gboolean ok = merge(b, v, p);
      g_free(p);
      if (!ok) {
        g_free(n);
        return FALSE;
      }
    } else if (json_object_is_type(b, json_type_array)) {
      for (size_t i = 0; i < json_object_array_length(v); i++) {
        J *x = json_object_array_get_idx(v, i);
        if (!json_object_is_type(x, json_type_string) ||
            strlen(js(x)) != (size_t)json_object_get_string_len(x) ||
            (!i && !*js(x))) {
          fail("%s must be an argv array", n);
          g_free(n);
          return FALSE;
        }
      }
      json_object_object_add(base, k, jclone(v));
    } else {
      if (json_object_is_type(v, json_type_string) &&
          strlen(js(v)) != (size_t)json_object_get_string_len(v)) {
        fail("NUL in setting %s", n);
        g_free(n);
        return FALSE;
      }
      json_object_object_add(base, k, jclone(v));
    }
    g_free(n);
  }
  return TRUE;
}
char *icon_path(const char *value) {
  char *p = expand(value, NULL);
  if (strchr(p, '/') || value[0] == '~' || value[0] == '$' || value[0] == '.') {
    if (!g_path_is_absolute(p)) {
      char *d = g_path_get_dirname(config_path), *f = path_join(d, p);
      g_free(d);
      g_free(p);
      p = f;
    }
    if (!g_file_test(p, G_FILE_TEST_IS_REGULAR)) {
      fail("Icon not found: %s", p);
      g_free(p);
      return NULL;
    }
  }
  return p;
}
gboolean load_config(const char *override) {
  if (config)
    json_object_put(config);
  char *d = path_join(asset_dir, "defaults.json");
  config = read_json(d, NULL);
  g_free(d);
  if (!config)
    return FALSE;
  g_free(config_path);
  const char *env = g_getenv("SIMPLEPICKER_CONFIG");
  config_path = override ? expand(override, NULL)
                : env ? expand(env, NULL)
                      : g_build_filename(g_get_user_config_dir(),
                                         "simplepicker", "config.toml", NULL);
  FILE *f = fopen(config_path, "r");
  if (!f) {
    if (override || env || g_file_test(config_path, G_FILE_TEST_EXISTS)) {
      fail("Cannot read config: %s", config_path);
      return FALSE;
    }
  } else {
    char err[256];
    toml_table_t *t = toml_parse_file(f, err, sizeof err);
    fclose(f);
    if (!t) {
      fail("Config: %s", err);
      return FALSE;
    }
    J *j = table_json(t);
    toml_free(t);
    if (!j)
      return FALSE;
    gboolean ok = merge(config, j, "");
    json_object_put(j);
    if (!ok)
      return FALSE;
  }
  const char *b = str(obj(config, "desktop"), "backend"),
             *layer = str(obj(config, "ui"), "layer_shell"),
             *hypr = str(obj(config, "desktop"), "hyprland_dispatch");
  if (strcmp(b, "auto") && strcmp(b, "mango") && strcmp(b, "sway") &&
      strcmp(b, "hyprland") && strcmp(b, "custom") && strcmp(b, "generic")) {
    fail("Invalid desktop.backend");
    return FALSE;
  }
  if (strcmp(layer, "auto") && strcmp(layer, "off") &&
      strcmp(layer, "required")) {
    fail("Invalid ui.layer_shell");
    return FALSE;
  }
  if (strcmp(hypr, "legacy") && strcmp(hypr, "lua")) {
    fail("Invalid hyprland_dispatch");
    return FALSE;
  }
  gint64 idle=json_object_get_int64(obj(obj(config,"screensaver"),"idle_seconds"));
  if(idle<10 || idle>86400){fail("screensaver.idle_seconds must be between 10 and 86400");return FALSE;}
  J *clip=obj(config,"clipboard");
  gint64 cw=json_object_get_int64(obj(clip,"width")),ch=json_object_get_int64(obj(clip,"height"));
  if(cw<320 || cw>2400 || ch<200 || ch>1600 || !*str(clip,"title")) {fail("Invalid clipboard title or dimensions");return FALSE;}
  gboolean keys[128] = {0};
  json_object_object_foreach(obj(config, "power"), name, a) {
    const char *ic = str(a, "icon");
    if (*ic) {
      char *p = icon_path(ic);
      if (!p)
        return FALSE;
      g_free(p);
    }
    if (!yes(a, "enabled"))
      continue;
    const char *k = str(a, "key");
    unsigned char c = g_ascii_tolower(*k);
    if (strlen(k) != 1 || !g_ascii_isalnum(c) || keys[c]) {
      fail("power.%s.key must be unique ASCII letter/digit", name);
      return FALSE;
    }
    keys[c] = TRUE;
    if (!*str(a, "label")) {
      fail("Empty power label");
      return FALSE;
    }
  }
  return TRUE;
}
char *theme_path(gboolean power) {
  const char *over =
      theme_override ? theme_override : g_getenv("SIMPLEPICKER_THEME");
  char *p = over ? expand(over, NULL)
                 : g_build_filename(g_get_user_config_dir(), "simplepicker",
                                    power ? "power/style.css" : "style.css", NULL);
  if(power && !over && !g_file_test(p,G_FILE_TEST_IS_REGULAR)) {
    g_free(p);p=g_build_filename(g_get_user_config_dir(),"simplepicker","power.css",NULL);
  }
  if(!over&&!g_file_test(p,G_FILE_TEST_IS_REGULAR)) {
    g_free(p);p=g_build_filename(g_get_user_data_dir(),"simplepicker",power?"power.css":"style.css",NULL);
  }
  if (!g_file_test(p, G_FILE_TEST_IS_REGULAR)) {
    if (over)
      fail("Theme not found: %s", p);
    g_free(p);
    return NULL;
  }
  return p;
}
