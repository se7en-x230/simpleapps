/* Exercise the actual runner, including bounded reads and process groups. */
#include "../panel-modules.c"
#include <stdio.h>
static void spin(int milliseconds) {
    gint64 end=g_get_monotonic_time()+milliseconds*1000;
    while(g_get_monotonic_time()<end) {
        while(g_main_context_iteration(NULL,FALSE)) {}
        g_usleep(1000);
    }
}
int main(int argc,char **argv) {
    gtk_init();
    GKeyFile *file=g_key_file_new();GError *error=NULL;
    g_assert_true(g_key_file_load_from_file(file,argv[1],0,&error));
    g_assert_true(panel_modules_load(file,argv[1],&error));
    GtkWidget *sections[]={gtk_box_new(0,0),gtk_box_new(0,0),gtk_box_new(0,0)};
    const char *names[]={"clock"};GtkWidget *widgets[]={gtk_label_new("clock")};
    panel_modules_layout(sections,names,widgets,1,FALSE,NULL);
    g_assert_true(gtk_widget_get_first_child(sections[0])==widgets[0]);
    g_assert_true(gtk_widget_get_next_sibling(widgets[0])==custom("ok")->label);
    g_assert_null(custom("disabled")->label);
    panel_modules_start();spin(500);
    g_assert_cmpstr(gtk_label_get_text(GTK_LABEL(custom("ok")->label)),==,"hello");
    g_assert_cmpstr(gtk_widget_get_tooltip_text(custom("ok")->label),==,"Tooltip");
    g_assert_nonnull(strstr(gtk_widget_get_tooltip_text(custom("failure")->label),"failed"));
    g_assert_nonnull(strstr(gtk_widget_get_tooltip_text(custom("flood")->label),"failed"));
    /* A second poll cannot start while the first is still running. */
    Run *first=custom("slow")->run;g_assert_nonnull(first);
    refresh(custom("slow"));g_assert_true(custom("slow")->run==first);
    spin(2000);
    g_assert_nonnull(strstr(gtk_widget_get_tooltip_text(custom("timeout")->label),"timed out"));
    g_assert_null(custom("timeout")->run);
    g_assert_nonnull(custom("slow")->run);
    panel_modules_stop();spin(300);
    for(guint i=0;i<module_count;i++)g_assert_null(modules[i].run);
    g_print("PASS module order, output/tooltip, failure, output cap, timeout, non-overlap, disabled module, shutdown\n");
    return 0;
}
