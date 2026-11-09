/* Tests the actual native key handler with an in-memory result model. */
#define CONTACTS 1
#define main organizer_program_main
#include "../simple-common/organizer.c"
#undef main
static void pump(void){gint64 end=g_get_monotonic_time()+150000;while(g_get_monotonic_time()<end){while(g_main_context_iteration(NULL,FALSE));g_usleep(1000);}}
int main(void){
 gtk_init();a.win=GTK_WINDOW(gtk_window_new());GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,4);gtk_window_set_child(a.win,box);a.search=gtk_search_entry_new();gtk_box_append(GTK_BOX(box),a.search);
 GtkStringList *model=gtk_string_list_new((const char*[]){"Alpha","Beta","Gamma",NULL});a.selection=gtk_single_selection_new(G_LIST_MODEL(model));a.list=gtk_list_view_new(GTK_SELECTION_MODEL(a.selection),NULL);gtk_box_append(GTK_BOX(box),a.list);gtk_window_present(a.win);pump();gtk_widget_grab_focus(a.search);gtk_editable_set_text(GTK_EDITABLE(a.search),"a");
 GtkWidget *focus=gtk_window_get_focus(a.win);
 g_assert_true(keyboard(NULL,GDK_KEY_j,0,GDK_CONTROL_MASK,NULL));g_assert_cmpuint(gtk_single_selection_get_selected(a.selection),==,1);g_assert_true(gtk_window_get_focus(a.win)==focus);
 keyboard(NULL,GDK_KEY_j,0,GDK_CONTROL_MASK,NULL);keyboard(NULL,GDK_KEY_j,0,GDK_CONTROL_MASK,NULL);g_assert_cmpuint(gtk_single_selection_get_selected(a.selection),==,2);
 keyboard(NULL,GDK_KEY_k,0,GDK_CONTROL_MASK,NULL);g_assert_cmpuint(gtk_single_selection_get_selected(a.selection),==,1);g_assert_cmpstr(gtk_editable_get_text(GTK_EDITABLE(a.search)),==,"a");
 gtk_string_list_splice(model,0,3,NULL);keyboard(NULL,GDK_KEY_j,0,GDK_CONTROL_MASK,NULL);g_assert_cmpuint(gtk_single_selection_get_selected(a.selection),==,GTK_INVALID_LIST_POSITION);
 gtk_window_destroy(a.win);g_print("PASS Contacts: Ctrl+j/k moves results, preserves search text/focus, bounds and empty results\n");return 0;
}
