#pragma once
#define _GNU_SOURCE
#include "vendor/toml.h"
#include <gio/gio.h>
#include <gtk/gtk.h>
#include <gtk4-session-lock.h>
#include <json-c/json.h>
#include <locale.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
typedef struct json_object J;
typedef struct {GtkWidget *window,*outer,*panel;gboolean closed;} Menu;
extern char *config_path,*last_error;
J *argv_json(const char *, ...);
GBytes *run_bytes(J *,GBytes *,int);
extern GHashTable *backdrops;
extern char *lock_user;
extern gboolean auth_busy,lock_visualizer;
