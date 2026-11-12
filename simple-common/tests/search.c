#include "../simple-ui.h"
#include <glib/gstdio.h>
static int selection,activations,closes;
static GtkWidget *entry,*list;
static void action(SimpleUISearchAction a,gpointer data){(void)data;if(a==SIMPLE_UI_SEARCH_DOWN)selection++;if(a==SIMPLE_UI_SEARCH_UP)selection--;if(a==SIMPLE_UI_SEARCH_ACTIVATE)activations++;}
static gboolean closed(GtkWindow *w,gpointer data){(void)w;(void)data;closes++;return TRUE;}
static gboolean focused(GtkWindow *w,GtkWidget *v){GtkWidget *f=gtk_window_get_focus(w);return f&&(f==v||gtk_widget_is_ancestor(f,v));}
int main(void){
 char *tmp=g_dir_make_tmp("simple-search-XXXXXX",NULL);g_setenv("XDG_CONFIG_HOME",tmp,TRUE);
 gtk_init();GtkWindow *w=GTK_WINDOW(gtk_window_new());GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,0),*editor=gtk_entry_new();entry=gtk_search_entry_new();list=gtk_list_box_new();gtk_list_box_append(GTK_LIST_BOX(list),gtk_label_new("result"));gtk_box_append(GTK_BOX(box),entry);gtk_box_append(GTK_BOX(box),list);gtk_box_append(GTK_BOX(box),editor);gtk_window_set_child(w,box);g_signal_connect(w,"close-request",G_CALLBACK(closed),NULL);
 simple_ui_bind_search(w,entry,list,"test-search",action,NULL);gtk_window_present(w);while(g_main_context_iteration(NULL,FALSE));
 simple_ui_search_start(w,FALSE);g_assert_false(gtk_widget_get_visible(entry));g_assert_true(focused(w,list));
 g_assert_cmpint(simple_ui_control_key(w,GDK_KEY_j,0),==,1);g_assert_cmpint(selection,==,1);g_assert_true(focused(w,list));
 simple_ui_control_key(w,GDK_KEY_slash,0);g_assert_true(gtk_widget_get_visible(entry));g_assert_true(focused(w,entry));
 g_assert_cmpint(simple_ui_control_key(w,GDK_KEY_j,GDK_CONTROL_MASK),==,1);g_assert_cmpint(selection,==,2);g_assert_true(focused(w,entry));
 simple_ui_control_key(w,GDK_KEY_k,GDK_CONTROL_MASK);g_assert_cmpint(selection,==,1);
 g_assert_cmpint(simple_ui_control_key(w,GDK_KEY_q,0),==,0);g_assert_cmpint(closes,==,0);
 simple_ui_control_key(w,GDK_KEY_Return,0);g_assert_cmpint(activations,==,1);
 gtk_editable_set_text(GTK_EDITABLE(entry),"query");simple_ui_control_key(w,GDK_KEY_Escape,0);
 g_assert_cmpint(closes,==,0);g_assert_false(gtk_widget_get_visible(entry));g_assert_true(focused(w,list));g_assert_cmpstr(gtk_editable_get_text(GTK_EDITABLE(entry)),==,"");
 simple_ui_control_key(w,GDK_KEY_Escape,0);g_assert_cmpint(closes,==,1);
 simple_ui_control_key(w,GDK_KEY_slash,0);simple_ui_control_key(w,GDK_KEY_Return,GDK_CONTROL_MASK);g_assert_false(gtk_widget_get_visible(entry));g_assert_true(focused(w,list));
 gtk_widget_grab_focus(editor);g_assert_cmpint(simple_ui_control_key(w,GDK_KEY_j,GDK_CONTROL_MASK),==,0);g_assert_cmpint(selection,==,1);simple_ui_control_key(w,GDK_KEY_Escape,0);g_assert_cmpint(closes,==,1);
 gtk_widget_set_visible(box,FALSE);simple_ui_control_key(w,GDK_KEY_Escape,0);g_assert_cmpint(closes,==,1);gtk_widget_set_visible(box,TRUE);
 char *global=g_build_filename(tmp,"simple",NULL),*app=g_build_filename(tmp,"simplepicker","keyboard",NULL);g_mkdir_with_parents(global,0700);g_mkdir_with_parents(app,0700);char *gp=g_build_filename(global,"keys.ini",NULL),*ap=g_build_filename(app,"keys.ini",NULL);
 g_file_set_contents(gp,"[interaction]\nstart_in_search=false\nescape_closes=false\n",-1,NULL);g_file_set_contents(ap,"[interaction]\nstart_in_search=true\n[navigation]\ndown=<Control>n\n",-1,NULL);
 simple_ui_bind_search(w,entry,list,"simplepicker/keyboard",action,NULL);simple_ui_search_start(w,FALSE);g_assert_true(gtk_widget_get_visible(entry));g_assert_true(focused(w,entry));simple_ui_control_key(w,GDK_KEY_n,GDK_CONTROL_MASK);g_assert_cmpint(selection,==,2);g_assert_true(focused(w,entry));
 simple_ui_control_key(w,GDK_KEY_Escape,0);g_assert_cmpint(closes,==,1);g_assert_false(gtk_widget_get_visible(entry));simple_ui_control_key(w,GDK_KEY_q,0);g_assert_cmpint(closes,==,2);
 g_file_set_contents(ap,"[interaction]\nstart_in_search=true\nescape_closes=true\n",-1,NULL);simple_ui_bind_search(w,entry,list,"simplepicker/keyboard",action,NULL);simple_ui_search_start(w,FALSE);simple_ui_control_key(w,GDK_KEY_Escape,0);g_assert_cmpint(closes,==,3);
 gtk_window_destroy(w);g_unlink(ap);g_unlink(gp);g_rmdir(app);g_rmdir(global);char *parent=g_path_get_dirname(app);g_rmdir(parent);g_free(parent);g_rmdir(tmp);g_free(ap);g_free(gp);g_free(app);g_free(global);g_free(tmp);g_print("PASS hidden default, slash, navigation, two-step Escape, editor/inactive-page safety and app overrides\n");return 0;
}
