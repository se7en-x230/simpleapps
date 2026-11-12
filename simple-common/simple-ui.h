#ifndef SIMPLE_UI_H
#define SIMPLE_UI_H
#include <gtk/gtk.h>
/* ABI 1. GTK calls must run on the main thread. Widgets are borrowed. */
unsigned simple_ui_abi_version(void);
void simple_ui_init(void);
void simple_ui_theme_load(GtkCssProvider *provider, const char *path);
int simple_ui_legacy_control_key(GtkWindow *window, guint key, GdkModifierType state);
void simple_ui_window(GtkWindow *window);
int simple_ui_control_key(GtkWindow *window, guint key, GdkModifierType state);
gboolean simple_ui_editing(GtkWindow *window);
gboolean simple_ui_key_matches(const char *app, const char *action, guint key, GdkModifierType state);
/* Owned UTF-8 result: release with simple_ui_free(). */
char *simple_ui_key_label(const char *app, const char *action);
void simple_ui_free(void *memory);
/* One search/navigation policy. Apps provide their domain actions only. */
typedef enum { SIMPLE_UI_SEARCH_DOWN=1, SIMPLE_UI_SEARCH_UP, SIMPLE_UI_SEARCH_ACTIVATE,
               SIMPLE_UI_SEARCH_NAVIGATE, SIMPLE_UI_SEARCH_FOCUS } SimpleUISearchAction;
typedef void (*SimpleUISearchCallback)(SimpleUISearchAction action, gpointer data);
void simple_ui_bind_search(GtkWindow *window, GtkWidget *search, GtkWidget *navigation,
                           const char *app, SimpleUISearchCallback callback, gpointer data);
void simple_ui_search_keys(GtkWindow *window, GKeyFile *keys);
void simple_ui_search_set(GtkWindow *window, gboolean searching);
void simple_ui_search_start(GtkWindow *window, gboolean fallback);
#endif
