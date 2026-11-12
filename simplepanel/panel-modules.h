#pragma once
#include <gtk/gtk.h>
/* Configuration and subprocess modules; no desktop protocol or market logic. */
gboolean panel_modules_load(GKeyFile *config, const char *path, GError **error);
const char *panel_environment(void);
gboolean panel_module_enabled(const char *name);
void panel_modules_layout(GtkWidget **sections, const char **names, GtkWidget **widgets, gsize count, gboolean demo, GCallback default_click);
void panel_modules_start(void);
void panel_modules_stop(void);
