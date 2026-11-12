#define main app_main
#include "../main.c"
#undef main
static J *plan;
static int step;
static gint64 next_time, preview_deadline;
static gboolean drive(gpointer unused) {
  (void)unused;
  if (!gtk_is_initialized() || g_get_monotonic_time() < next_time) return G_SOURCE_CONTINUE;
  GListModel *windows = gtk_window_get_toplevels();
  if (!g_list_model_get_n_items(windows)) return G_SOURCE_CONTINUE;
  GtkWindow *window = g_list_model_get_item(windows, 0);
  Menu *m = g_object_get_data(G_OBJECT(window), "sp-menu");
  if (!m) m = g_object_get_data(G_OBJECT(window), "sp-power");
  if (!m || !gtk_widget_get_mapped(GTK_WIDGET(window))) {g_object_unref(window);return G_SOURCE_CONTINUE;}
  if ((size_t)step >= json_object_array_length(plan)) {
    g_printerr("TEST: unexpected extra menu\n");exit(90);
  }
  J *operation = json_object_array_get_idx(plan, step++);
  next_time = g_get_monotonic_time() + 250000;
  if (obj(operation,"wait")) next_time = g_get_monotonic_time() + num(operation,"wait")*1000;
  if (obj(operation,"query")) gtk_editable_set_text(GTK_EDITABLE(m->entry), str(operation,"query"));
  if (obj(operation,"max_panel_height") && gtk_widget_get_height(m->panel)>num(operation,"max_panel_height")) {
    g_printerr("TEST: menu panel too tall: %d\n",gtk_widget_get_height(m->panel));exit(96);
  }
  if (obj(operation,"select")) {
    const char *wanted = str(operation,"select");
    gboolean found=FALSE;
    for (GtkWidget *child=gtk_widget_get_first_child(m->list);child;child=gtk_widget_get_next_sibling(child)) {
      Row *r=g_object_get_data(G_OBJECT(child),"row");
      if (!strcmp(r->id,wanted) || !strcmp(r->label,wanted)) {gtk_list_box_select_row(GTK_LIST_BOX(m->list),GTK_LIST_BOX_ROW(child));found=TRUE;break;}
    }
    if (!found) {g_printerr("TEST: row not found: %s\n",wanted);exit(91);}
  }
  if (obj(operation,"expect_preview")) {
    g_assert_true(gtk_widget_has_css_class(m->preview_box,"card"));
    const char *expected=str(operation,"expect_preview");
    if (!gtk_widget_get_visible(m->preview_box)) {
      if(!preview_deadline) preview_deadline=g_get_monotonic_time()+8000000;
      if(g_get_monotonic_time()<preview_deadline){step--;next_time=g_get_monotonic_time()+50000;g_object_unref(window);return G_SOURCE_CONTINUE;}
      g_printerr("TEST: preview hidden after 8 seconds\n");exit(92);
    }
    preview_deadline=0;
    if (!strcmp(expected,"image")) {if(!gtk_picture_get_paintable(GTK_PICTURE(m->picture)))exit(93);}
    else if (!strstr(gtk_label_get_text(GTK_LABEL(m->text)),expected)) {g_printerr("TEST: wrong preview text\n");exit(94);}
  }
  if (yes(operation,"expect_all_visible")) {
    GtkAdjustment *adj=gtk_scrolled_window_get_vadjustment(GTK_SCROLLED_WINDOW(m->scroll));
    if (gtk_adjustment_get_upper(adj)>gtk_adjustment_get_page_size(adj)+1) {
      g_printerr("TEST: engines require scrolling: %f > %f\n",gtk_adjustment_get_upper(adj),gtk_adjustment_get_page_size(adj));exit(96);
    }
  }
  if (obj(operation,"key")) {
    GListModel *controllers=gtk_widget_observe_controllers(GTK_WIDGET(window));
    for(guint i=0;i<g_list_model_get_n_items(controllers);i++){
      GtkEventController *c=g_list_model_get_item(controllers,i);
      if(GTK_IS_EVENT_CONTROLLER_KEY(c)) {gboolean handled=FALSE;g_signal_emit_by_name(c,"key-pressed",gdk_keyval_from_name(str(operation,"key")),0,yes(operation,"ctrl")?GDK_CONTROL_MASK:0,&handled);g_object_unref(c);break;}
      g_object_unref(c);
    }
    g_object_unref(controllers);
  }
  if (yes(operation,"close")) gtk_window_close(window);
  g_object_unref(window);
  return G_SOURCE_CONTINUE;
}
int main(int argc,char **argv){
  const char *path=g_getenv("SP_TEST_PLAN");
  if(!path){g_printerr("SP_TEST_PLAN required\n");return 99;}
  plan=read_json(path,NULL);if(!plan)return 98;
  g_timeout_add(50,drive,NULL);
  int code=app_main(argc,argv);
  if((size_t)step!=json_object_array_length(plan)){g_printerr("TEST: incomplete plan %d/%zu\n",step,json_object_array_length(plan));return 95;}
  return code;
}
