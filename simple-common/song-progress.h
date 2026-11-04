#ifndef SIMPLE_SONG_PROGRESS_H
#define SIMPLE_SONG_PROGRESS_H
#include <gtk/gtk.h>
#include <math.h>
static inline char *simple_song_time(double seconds) {
 gint64 n=(gint64)CLAMP(seconds,0,31536000);
 return n>=3600?g_strdup_printf("%lld:%02lld:%02lld",(long long)(n/3600),(long long)(n/60%60),(long long)(n%60)):g_strdup_printf("%lld:%02lld",(long long)(n/60),(long long)(n%60));
}
static inline GtkWidget *simple_song_progress_new(void) {
 GtkWidget *bar=gtk_progress_bar_new();gtk_progress_bar_set_show_text(GTK_PROGRESS_BAR(bar),TRUE);
 gtk_widget_add_css_class(bar,"song-progress");gtk_widget_set_hexpand(bar,TRUE);gtk_widget_set_visible(bar,FALSE);
 GdkDisplay *display=gdk_display_get_default();
 if(!g_object_get_data(G_OBJECT(display),"simple-song-progress-css")) {
  GtkCssProvider *css=gtk_css_provider_new();gtk_css_provider_load_from_string(css,"progressbar.song-progress trough { min-height: 4px; background: @simple_border; box-shadow: none; border: none; border-radius: 3px; } progressbar.song-progress progress { min-height: 4px; background: @simple_accent; box-shadow: none; border: none; border-radius: 3px; } progressbar.song-progress text { color: @simple_muted; font-size: 11px; }");
  gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER+5);g_object_set_data_full(G_OBJECT(display),"simple-song-progress-css",css,g_object_unref);
 }
 return bar;
}
static inline void simple_song_progress_update(GtkWidget *bar,double position,double duration,gboolean active) {
 gboolean valid=active&&isfinite(position)&&isfinite(duration)&&duration>0&&position>=0;
 gtk_widget_set_visible(bar,valid);gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(bar),valid?CLAMP(position/duration,0,1):0);
 if(!valid){gtk_progress_bar_set_text(GTK_PROGRESS_BAR(bar),"");return;}
 char *elapsed=simple_song_time(MIN(position,duration)),*total=simple_song_time(duration),*text=g_strdup_printf("%s / %s",elapsed,total);
 gtk_progress_bar_set_text(GTK_PROGRESS_BAR(bar),text);gtk_widget_set_tooltip_text(bar,text);g_free(elapsed);g_free(total);g_free(text);
}
#endif
