#ifndef SIMPLE_THEME_LOADER_H
#define SIMPLE_THEME_LOADER_H
#include <gtk/gtk.h>
/* Shared defaults always load, even when the optional app stylesheet is absent. */
static inline void simple_theme_load(GtkCssProvider *provider, const char *path) {
    GdkDisplay *display=gdk_display_get_default();
    GtkCssProvider *shared=g_object_get_data(G_OBJECT(display),"simple-shared-theme");
    if(!shared) {
        shared=gtk_css_provider_new();
        gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(shared),GTK_STYLE_PROVIDER_PRIORITY_USER-1);
        g_object_set_data_full(G_OBJECT(display),"simple-shared-theme",shared,g_object_unref);
    }
    char *base=g_build_filename(g_get_user_config_dir(),"simple","aliases.css",NULL);
    if(!g_file_test(base,G_FILE_TEST_IS_REGULAR)) {
        g_free(base);base=g_build_filename(g_get_user_config_dir(),"simple","theme.css",NULL);
    }
    if(!g_file_test(base,G_FILE_TEST_IS_REGULAR)) {
        g_free(base);base=g_build_filename(g_get_user_data_dir(),"simple","aliases.css",NULL);
    }
    if(g_file_test(base,G_FILE_TEST_IS_REGULAR)) gtk_css_provider_load_from_path(shared,base);
    else gtk_css_provider_load_from_string(shared,"");
    g_free(base);
    if(path && g_file_test(path,G_FILE_TEST_IS_REGULAR)) gtk_css_provider_load_from_path(provider,path);
    else gtk_css_provider_load_from_string(provider,"");
}
#endif
