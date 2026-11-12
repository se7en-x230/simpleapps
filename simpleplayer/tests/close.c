#define main player_main
#include "../native.c"
#undef main
static int closes;
static gboolean closed(GtkWindow *w,gpointer data) {(void)w;(void)data;closes++;return TRUE;}
int main(void) {
    gtk_init();
    window=gtk_window_new();
    GtkWidget *root=gtk_box_new(GTK_ORIENTATION_VERTICAL,0);
    gtk_window_set_child(GTK_WINDOW(window),root);
    search=gtk_search_entry_new();list=gtk_list_box_new();browser=list;
    GtkWidget *row=gtk_label_new("album");gtk_list_box_append(GTK_LIST_BOX(list),row);
    gtk_box_append(GTK_BOX(root),search);gtk_box_append(GTK_BOX(root),list);
    g_signal_connect(window,"close-request",G_CALLBACK(closed),NULL);
    simple_ui_bind_search(GTK_WINDOW(window),search,list,"simpleplayer",search_action,NULL);
    gtk_window_present(GTK_WINDOW(window));
    while(g_main_context_iteration(NULL,FALSE)) {}
    folder=g_strdup("Genre/Artist/Album");browsing=TRUE;
    gtk_widget_set_visible(search,FALSE);gtk_widget_grab_focus(list);
    g_assert_true(keys(NULL,GDK_KEY_Escape,0,0,NULL));g_assert_cmpint(closes,==,1);
    g_assert_cmpstr(folder,==,"Genre/Artist/Album");
    g_assert_true(keys(NULL,GDK_KEY_q,0,0,NULL));g_assert_cmpint(closes,==,2);
    gtk_widget_set_visible(search,TRUE);gtk_widget_grab_focus(search);
    gtk_editable_set_text(GTK_EDITABLE(search),"album");
    g_assert_false(keys(NULL,GDK_KEY_q,0,0,NULL));g_assert_cmpint(closes,==,2);
    g_assert_true(keys(NULL,GDK_KEY_Escape,0,0,NULL));g_assert_cmpint(closes,==,3);
    g_assert_cmpstr(gtk_editable_get_text(GTK_EDITABLE(search)),==,"album");
    gtk_widget_set_visible(search,FALSE);gtk_widget_grab_focus(list);
    g_assert_true(keys(NULL,GDK_KEY_h,0,0,NULL));g_assert_cmpint(closes,==,3);
    g_assert_cmpstr(folder,==,"Genre/Artist");
    g_assert_true(keys(NULL,GDK_KEY_Left,0,GDK_ALT_MASK,NULL));
    g_assert_cmpstr(folder,==,"Genre");g_assert_cmpint(closes,==,3);
    browsing=FALSE;
    g_assert_true(keys(NULL,GDK_KEY_Escape,0,0,NULL));g_assert_cmpint(closes,==,4);
    gtk_window_destroy(GTK_WINDOW(window));g_free(folder);
    g_print("PASS: one-press Esc/q close at album depth, search typing, Esc closes directly from search, h/Alt+Left back, playback view close\n");
    return 0;
}
