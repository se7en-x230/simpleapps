#pragma once
#define _GNU_SOURCE
#include "vendor/toml.h"
#include <gio/gdesktopappinfo.h>
#include <gtk/gtk.h>
#include <gtk4-layer-shell.h>
#include <json-c/json.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/file.h>
#include <sys/stat.h>
#include <unistd.h>
typedef struct json_object J;
extern char *asset_dir, *config_path, *data_dir, *theme_override, *last_error;
extern J *config;
extern gboolean sp_benchmark;
extern char *keys_override;
extern const char *keys_scope;
char *navigation_label(GKeyFile *, const char *);
GKeyFile *navigation_load(const char *, const char *);
gboolean navigation_match(GKeyFile *, const char *, guint, GdkModifierType, gboolean);
J *obj(J *, const char *);
const char *str(J *, const char *);
const char *js(J *);
int num(J *, const char *);
gboolean yes(J *, const char *);
J *read_json(const char *, const char *);
gboolean write_json(const char *, J *);
J *parse_json(const char *);
void setstr(J *, const char *, const char *);
void setint(J *, const char *, int);
J *jclone(J *);
void fail(const char *, ...) G_GNUC_PRINTF(1, 2);
char *norm(const char *);
gboolean match(const char *, const char *);
char *expand(const char *, J *);
char *path_join(const char *, const char *);
J *argv_json(const char *, ...);
J *command_argv(const char *, J *);
J *expand_argv(J *, J *);
GBytes *run_bytes(J *, GBytes *, int);
char *run_text(J *, const char *, int);
gboolean spawn(J *);
gboolean copy_bytes(GBytes *, const char *);
gboolean copy_text(const char *);
gboolean load_config(const char *);
char *icon_path(const char *);
char *theme_path(gboolean);
void history_add(const char *, const char *);
int history_count(J *, const char *);
char *data_path(const char *);
J *history(const char *, const char *);
gboolean save_data(const char *, J *);
int data_lock(const char *);
const char *backend(void);
gboolean supports(const char *);
J *windows_list(void);
J *desktop_current(void);
gboolean desktop_action(const char *, J *, J *);
J *logout_argv(void);
void open_url(const char *);
typedef struct Row {
  char *id, *label, *sub, *terms, *icon, *font;
  GIcon *gicon;
  gpointer data;
  GDestroyNotify destroy;
  int rank, quality;
} Row;
typedef struct Menu Menu;
struct Menu {
  const char *title, *prompt, *icon, *theme, *initial, *sample;
  const char *keys_path, *key_scope;
  GKeyFile *navigation;
  gboolean (*navigate)(Menu *, const char *);
  int width, height, selected, icon_size;
  gboolean input, password, previews, font_rows, bridge, closed, benchmark,
      busy;
  gboolean vim_navigation, vim_search;
  gint64 vim_pending_g;
  gboolean cache_previews;
  GHashTable *preview_cache;
  GQueue *preview_recent;
  GPtrArray *rows;
  J *shortcuts;
  char *result, *action, *query;
  gpointer userdata;
  void (*search)(Menu *, const char *);
  gboolean (*activate)(Menu *, Row *, const char *);
  void (*preview)(Menu *, Row *);
  GtkWidget *window, *outer, *panel, *entry, *list, *scroll, *empty,
      *preview_box, *picture, *text;
  GMainLoop *loop;
  GCancellable *preview_cancel;
  guint preview_timer;
  gulong frame_handler;
};
Menu *menu_new(const char *, const char *);
void menu_free(Menu *);
Row *row_new(const char *, const char *, const char *, const char *);
void row_free(gpointer);
void rows_clear(Menu *);
void menu_shortcut(Menu *, const char *, const char *);
char *menu_show(Menu *);
void menu_refresh(Menu *);
void menu_finish(Menu *, const char *);
void menu_set_text_preview(Menu *, const char *);
void menu_set_image_preview(Menu *, GBytes *);
void menu_preview_process(Menu *, J *, GBytes *, gboolean);
Row *menu_selected(Menu *);
Row *menu_find(Menu *, const char *);
void menu_query(Menu *, const char *);
int provider(const char *);
int power_show(void);
int bridge_main(void);
int bookmark_editor(void);

int dashboard_show(gboolean fullscreen, gboolean stop_only);
