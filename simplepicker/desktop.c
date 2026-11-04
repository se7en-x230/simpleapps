#include "sp.h"
const char *backend(void) {
  const char *b = str(obj(config, "desktop"), "backend");
  if (strcmp(b, "auto"))
    return b;
  const char *s = g_getenv("XDG_CURRENT_DESKTOP");
  char *lower = g_ascii_strdown(s ? s : "", -1);
  const char *result = "generic";
  if (g_getenv("MANGO_INSTANCE_SIGNATURE") || strstr(lower, "mango"))
    result = "mango";
  else if (g_getenv("HYPRLAND_INSTANCE_SIGNATURE") || strstr(lower, "hyprland"))
    result = "hyprland";
  else if (g_getenv("SWAYSOCK") || strstr(lower, "sway"))
    result = "sway";
  g_free(lower);
  return result;
}
static J *hook(const char *n, J *v) {
  J *a = obj(obj(config, "windows"), n);
  return json_object_array_length(a) ? expand_argv(a, v) : NULL;
}
gboolean supports(const char *n) {
  J *a = obj(obj(config, "windows"), n);
  return json_object_array_length(a) || !strcmp(backend(), "mango") ||
         !strcmp(backend(), "sway") || !strcmp(backend(), "hyprland");
}
static J *run_json(J *a) {
  char *s = run_text(a, NULL, 5);
  if (!s)
    return NULL;
  J *j = parse_json(s);
  g_free(s);
  return j;
}
static char *tags(J *a) {
  GString *s = g_string_new(NULL);
  for (size_t i = 0; a && i < json_object_array_length(a); i++) {
    if (i)
      g_string_append_c(s, '|');
    g_string_append(s, js(json_object_array_get_idx(a, i)));
  }
  return g_string_free(s, FALSE);
}
static void sway_walk(J *node, J *out, const char *workspace,
                      const char *output) {
  if (!strcmp(str(node, "type"), "workspace"))
    workspace = str(node, "name");
  if (!strcmp(str(node, "type"), "output"))
    output = str(node, "name");
  if (obj(node, "app_id")) {
    J *r = jclone(node);
    setstr(r, "title", str(node, "name"));
    setstr(r, "workspace", workspace);
    setstr(r, "output", output);
    json_object_array_add(out, r);
  }
  const char *keys[] = {"nodes", "floating_nodes"};
  for (int k = 0; k < 2; k++) {
    J *a = obj(node, keys[k]);
    for (size_t i = 0; a && i < json_object_array_length(a); i++)
      sway_walk(json_object_array_get_idx(a, i), out, workspace, output);
  }
}
J *windows_list(void) {
  J *a = hook("list", NULL), *raw = NULL, *out = NULL;
  const char *b = backend();
  if (a)
    out = run_json(a);
  else if (!strcmp(b, "mango")) {
    raw = run_json(argv_json("mmsg", "get", "all-clients", NULL));
    if (!raw)
      return NULL;
    out = json_object_new_array();
    a = obj(raw, "clients");
    for (size_t i = 0; a && i < json_object_array_length(a); i++) {
      J *c = json_object_array_get_idx(a, i);
      if (yes(c, "is_swallowedby"))
        continue;
      J *r = jclone(c);
      char *t = tags(obj(c, "tags"));
      setstr(r, "workspace", t);
      g_free(t);
      setstr(r, "app_id", str(c, "appid"));
      setstr(r, "output", str(c, "monitor"));
      json_object_object_add(r, "focused",
                             json_object_new_boolean(yes(c, "is_focused")));
      json_object_object_add(r, "urgent",
                             json_object_new_boolean(yes(c, "is_urgent")));
      json_object_object_add(r, "visible",
                             json_object_new_boolean(yes(c, "is_visible")));
      json_object_array_add(out, r);
    }
  } else if (!strcmp(b, "hyprland")) {
    raw = run_json(argv_json("hyprctl", "-j", "clients", NULL));
    J *active = run_json(argv_json("hyprctl", "-j", "activewindow", NULL));
    if (!raw) {
      if (active)
        json_object_put(active);
      return NULL;
    }
    out = json_object_new_array();
    for (size_t i = 0; i < json_object_array_length(raw); i++) {
      J *c = json_object_array_get_idx(raw, i), *r = jclone(c);
      setstr(r, "id", str(c, "address"));
      setstr(r, "app_id", str(c, "class"));
      setstr(r, "workspace", str(obj(c, "workspace"), "name"));
      setstr(r, "output", str(c, "monitor"));
      json_object_object_add(r, "focused",
                             json_object_new_boolean(!strcmp(
                                 str(c, "address"), str(active, "address"))));
      json_object_array_add(out, r);
    }
    if (active)
      json_object_put(active);
  } else if (!strcmp(b, "sway")) {
    raw = run_json(argv_json("swaymsg", "-r", "-t", "get_tree", NULL));
    if (!raw)
      return NULL;
    out = json_object_new_array();
    sway_walk(raw, out, "", "");
  } else
    fail("Window list unavailable on %s; configure windows.list", b);
  if (raw)
    json_object_put(raw);
  if (!out)
    return NULL;
  if (!json_object_is_type(out, json_type_array)) {
    fail("windows.list must return a JSON array");
    json_object_put(out);
    return NULL;
  }
  GHashTable *seen =
      g_hash_table_new_full(g_str_hash, g_str_equal, g_free, NULL);
  for (size_t i = 0; i < json_object_array_length(out); i++) {
    J *r = json_object_array_get_idx(out, i), *id = obj(r, "id");
    if (!json_object_is_type(r, json_type_object) ||
        (!json_object_is_type(id, json_type_string) &&
         !json_object_is_type(id, json_type_int)) ||
        !*js(id) || g_hash_table_contains(seen, js(id))) {
      fail("Each window needs a nonempty unique string/integer id");
      g_hash_table_unref(seen);
      json_object_put(out);
      return NULL;
    }
    g_hash_table_add(seen, g_strdup(js(id)));
    const char *fields[] = {"title", "app_id", "workspace", "output"};
    for (int k = 0; k < 4; k++) {
      char *v = g_strdup(str(r, fields[k]));
      setstr(r, fields[k], v);
      g_free(v);
    }
  }
  g_hash_table_unref(seen);
  return out;
}
J *desktop_current(void) {
  J *a = hook("current", NULL), *out = NULL, *raw = NULL;
  const char *b = backend();
  if (a)
    out = run_json(a);
  else if (!strcmp(b, "mango")) {
    raw = run_json(argv_json("mmsg", "get", "all-monitors", NULL));
    a = obj(raw, "monitors");
    for (size_t i = 0; a && i < json_object_array_length(a); i++) {
      J *m = json_object_array_get_idx(a, i);
      if (yes(m, "active")) {
        out = json_object_new_object();
        char *t = tags(obj(m, "active_tags"));
        setstr(out, "workspace", t);
        g_free(t);
        setstr(out, "output", str(m, "name"));
        break;
      }
    }
  } else if (!strcmp(b, "hyprland")) {
    raw = run_json(argv_json("hyprctl", "-j", "activeworkspace", NULL));
    if (raw) {
      out = json_object_new_object();
      setstr(out, "workspace", str(raw, "id"));
      setstr(out, "output", str(raw, "monitor"));
    }
  } else if (!strcmp(b, "sway")) {
    raw = run_json(argv_json("swaymsg", "-r", "-t", "get_workspaces", NULL));
    for (size_t i = 0; raw && i < json_object_array_length(raw); i++) {
      J *w = json_object_array_get_idx(raw, i);
      if (yes(w, "focused")) {
        out = json_object_new_object();
        setstr(out, "workspace", str(w, "name"));
        setstr(out, "output", str(w, "output"));
        break;
      }
    }
  }
  if (raw)
    json_object_put(raw);
  if (!out || !*str(out, "workspace")) {
    fail("No valid destination workspace");
    if (out)
      json_object_put(out);
    return NULL;
  }
  return out;
}
static gboolean digits(const char *s, gboolean tags_allowed) {
  if (!*s)
    return FALSE;
  for (; *s; s++)
    if (!g_ascii_isdigit(*s) && !(tags_allowed && *s == '|'))
      return FALSE;
  return TRUE;
}
gboolean desktop_action(const char *action, J *w, J *dest) {
  J *v = jclone(w);
  if (dest) {
    setstr(v, "workspace", str(dest, "workspace"));
    setstr(v, "output", str(dest, "output"));
  }
  J *a = hook(action, v);
  const char *b = backend(), *id = str(w, "id");
  if (!a && !strcmp(b, "mango")) {
    if (!digits(id, FALSE)) {
      fail("Invalid Mango client id");
      goto done;
    }
    char *target = g_strdup_printf("client,%s", id);
    if (!strcmp(action, "focus"))
      a = argv_json("mmsg", "dispatch", "focusid", target, NULL);
    else if (!strcmp(action, "close"))
      a = argv_json("mmsg", "dispatch", "killclient", target, NULL);
    else {
      if (!digits(str(v, "workspace"), TRUE)) {
        fail("Invalid Mango tags");
        g_free(target);
        goto done;
      }
      if (strcmp(str(w, "output"), str(v, "output"))) {
        char *cmd = g_strdup_printf("tagmon,%s,1", str(v, "output"));
        char *s =
            run_text(argv_json("mmsg", "dispatch", cmd, target, NULL), NULL, 5);
        g_free(cmd);
        if (!s) {
          g_free(target);
          goto done;
        }
        g_free(s);
      }
      char *cmd = g_strdup_printf("tag,%s,0", str(v, "workspace"));
      a = argv_json("mmsg", "dispatch", cmd, target, NULL);
      g_free(cmd);
    }
    g_free(target);
  } else if (!a && !strcmp(b, "sway")) {
    if (!digits(id, FALSE)) {
      fail("Invalid Sway client id");
      goto done;
    }
    J *q = json_object_new_string(str(v, "workspace"));
    char *cmd = g_strdup_printf(
        "[con_id=%s] %s%s", id,
        !strcmp(action, "focus")   ? "focus"
        : !strcmp(action, "close") ? "kill"
                                   : "move container to workspace ",
        !strcmp(action, "move") ? json_object_to_json_string(q) : "");
    json_object_put(q);
    J *r = run_json(argv_json("swaymsg", "-r", cmd, NULL));
    g_free(cmd);
    gboolean ok = r && json_object_is_type(r, json_type_array);
    for (size_t i = 0; ok && i < json_object_array_length(r); i++)
      ok = yes(json_object_array_get_idx(r, i), "success");
    if (!ok && !last_error)
      fail("Sway rejected action");
    if (r)
      json_object_put(r);
    json_object_put(v);
    return ok;
  } else if (!a && !strcmp(b, "hyprland")) {
    if (!g_regex_match_simple("^0x[0-9a-fA-F]+$", id, 0, 0) ||
        (!strcmp(action, "move") &&
         !g_regex_match_simple("^-?[0-9]+$", str(v, "workspace"), 0, 0))) {
      fail("Invalid Hyprland target");
      goto done;
    }
    char *selector = g_strconcat("address:", id, NULL);
    if (!strcmp(str(obj(config, "desktop"), "hyprland_dispatch"), "lua")) {
      char *expr = !strcmp(action, "move")
                       ? g_strdup_printf("hl.dsp.window.move({window=\"%s\","
                                         "workspace=\"%s\",follow=false})",
                                         selector, str(v, "workspace"))
                       : g_strdup_printf("%s({window=\"%s\"})",
                                         !strcmp(action, "focus")
                                             ? "hl.dsp.focus"
                                             : "hl.dsp.window.close",
                                         selector);
      a = argv_json("hyprctl", "dispatch", expr, NULL);
      g_free(expr);
    } else {
      char *arg = !strcmp(action, "move")
                      ? g_strdup_printf("%s,%s", str(v, "workspace"), selector)
                      : g_strdup(selector);
      a = argv_json("hyprctl", "dispatch",
                    !strcmp(action, "focus")   ? "focuswindow"
                    : !strcmp(action, "close") ? "closewindow"
                                               : "movetoworkspacesilent",
                    arg, NULL);
      g_free(arg);
    }
    g_free(selector);
  }
  if (a) {
    char *s = run_text(a, NULL, 5);
    json_object_put(v);
    gboolean ok = s != NULL;
    g_free(s);
    return ok;
  }
  if (!last_error)
    fail("Window action unavailable on %s", b);
done:
  json_object_put(v);
  return FALSE;
}
J *logout_argv(void) {
  if (!strcmp(backend(), "mango"))
    return argv_json("mmsg", "dispatch", "quit", NULL);
  if (!strcmp(backend(), "sway"))
    return argv_json("swaymsg", "exit", NULL);
  if (!strcmp(backend(), "hyprland"))
    return argv_json(
        "hyprctl", "dispatch",
        !strcmp(str(obj(config, "desktop"), "hyprland_dispatch"), "lua")
            ? "hl.dsp.exit()"
            : "exit",
        NULL);
  return json_object_new_array();
}
void open_url(const char *url) {
  char *scheme = g_uri_parse_scheme(url);
  if (!scheme || (strcmp(scheme, "http") && strcmp(scheme, "https") &&
                  strcmp(scheme, "ftp") && strcmp(scheme, "file"))) {
    fail("Unsupported URL scheme");
    g_free(scheme);
    return;
  }
  J *v = json_object_new_object();
  setstr(v, "url", url);
  gboolean ok = spawn(command_argv("open_url", v));
  json_object_put(v);
  if (ok && (!strcmp(scheme, "http") || !strcmp(scheme, "https")) &&
      supports("list") && supports("focus")) {
    GAppInfo *app = g_app_info_get_default_for_uri_scheme(scheme);
    if (app) {
      const char *id = g_app_info_get_id(app),
                 *exe = g_app_info_get_executable(app);
      char *base = exe ? g_path_get_basename(exe) : g_strdup("");
      char *stem = g_strdup(id ? id : "");
      if (g_str_has_suffix(stem, ".desktop"))
        stem[strlen(stem) - 8] = 0;
      gint64 deadline = g_get_monotonic_time() + 5000000;
      while (g_get_monotonic_time() < deadline) {
        J *ws = windows_list();
        if (!ws) {
          g_clear_pointer(&last_error, g_free);
          break;
        }
        J *best = NULL;
        int rank = -1;
        for (size_t i = 0; i < json_object_array_length(ws); i++) {
          J *w = json_object_array_get_idx(ws, i);
          const char *appid = str(w, "app_id");
          const char *wm = G_IS_DESKTOP_APP_INFO(app)
                               ? g_desktop_app_info_get_startup_wm_class(
                                     G_DESKTOP_APP_INFO(app))
                               : NULL;
          if (!g_ascii_strcasecmp(appid, stem) ||
              !g_ascii_strcasecmp(appid, base) ||
              (wm && !g_ascii_strcasecmp(appid, wm))) {
            int r = yes(w, "focused") * 4 + yes(w, "urgent") * 2 +
                    yes(w, "visible");
            if (r > rank) {
              rank = r;
              best = w;
            }
          }
        }
        if (best) {
          desktop_action("focus", best, NULL);
          g_clear_pointer(&last_error, g_free);
          json_object_put(ws);
          break;
        }
        json_object_put(ws);
        g_usleep(150000);
      }
      g_free(base);
      g_free(stem);
      g_object_unref(app);
    }
  }
  g_free(scheme);
}
