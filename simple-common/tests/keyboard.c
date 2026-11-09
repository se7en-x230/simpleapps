#include "../simple-keyboard.h"
static int clicks;
static void clicked(GtkButton *b,gpointer p){(void)b;(void)p;clicks++;}
static void pump(void){gint64 end=g_get_monotonic_time()+400000;while(g_get_monotonic_time()<end){while(g_main_context_iteration(NULL,FALSE));g_usleep(1000);}}
int main(void){
 gtk_init();GtkWindow *win=GTK_WINDOW(gtk_window_new());GtkWidget *box=gtk_box_new(GTK_ORIENTATION_VERTICAL,8),*button=gtk_button_new_with_label("Action"),*check=gtk_check_button_new_with_label("Toggle"),*scale=gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL,0,100,1),*entry=gtk_entry_new();
 gtk_window_set_child(win,box);gtk_box_append(GTK_BOX(box),button);gtk_box_append(GTK_BOX(box),check);gtk_box_append(GTK_BOX(box),scale);gtk_box_append(GTK_BOX(box),entry);g_signal_connect(button,"clicked",G_CALLBACK(clicked),NULL);gtk_window_present(win);pump();
 gtk_widget_grab_focus(button);g_assert_cmpint(simple_control_key(win,GDK_KEY_Return,0),==,1);pump();g_assert_cmpint(clicks,==,1);
 g_assert_cmpint(simple_control_key(win,GDK_KEY_space,0),==,0);g_assert_cmpint(simple_control_key(win,GDK_KEY_Tab,0),==,0);g_assert_cmpint(simple_control_key(win,GDK_KEY_ISO_Left_Tab,GDK_SHIFT_MASK),==,0);
 gtk_widget_grab_focus(check);g_assert_cmpint(simple_control_key(win,GDK_KEY_Return,0),==,1);pump();g_assert_true(gtk_check_button_get_active(GTK_CHECK_BUTTON(check)));
 gtk_widget_grab_focus(scale);g_assert_cmpint(simple_control_key(win,GDK_KEY_Right,0),==,0);
 gtk_widget_grab_focus(entry);g_assert_cmpint(simple_control_key(win,GDK_KEY_Return,0),==,-1);
 gtk_window_destroy(win);g_print("PASS native GTK focus, activation, checkbox, slider, entry and Tab routing\n");return 0;
}
