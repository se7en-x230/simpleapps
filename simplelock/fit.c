/* Fit the complete card layout within each output, including small/portrait ones.
 * GTK's child transform also maps pointer coordinates into the scaled layout. */
typedef struct {GtkWidget parent;GtkWidget *child;} LockFit;
typedef GtkWidgetClass LockFitClass;
G_DEFINE_TYPE(LockFit,lock_fit,GTK_TYPE_WIDGET)
static void fit_measure(GtkWidget *w,GtkOrientation o,int size,int *min,int *nat,int *minbase,int *natbase) {
  (void)w;(void)o;(void)size;*min=0;*nat=1;*minbase=*natbase=-1;
}
static void fit_allocate(GtkWidget *w,int width,int height,int baseline) {
  (void)baseline;LockFit *fit=(LockFit*)w;int mw,nw,mh,nh;
  gtk_widget_measure(fit->child,GTK_ORIENTATION_HORIZONTAL,-1,&mw,&nw,NULL,NULL);
  gtk_widget_measure(fit->child,GTK_ORIENTATION_VERTICAL,nw,&mh,&nh,NULL,NULL);
  double scale=MIN(1.,MIN((double)width/MAX(1,nw),(double)height/MAX(1,nh)));
#ifdef SIMPLELOCK_TEST
  g_printerr("FIT viewport=%dx%d natural=%dx%d scale=%.4f\n",width,height,nw,nh,scale);
#endif
  graphene_point_t origin=GRAPHENE_POINT_INIT((width-nw*scale)/2.,(height-nh*scale)/2.);
  GskTransform *transform=gsk_transform_translate(NULL,&origin);transform=gsk_transform_scale(transform,scale,scale);
  gtk_widget_allocate(fit->child,nw,nh,-1,transform);
}
static void fit_snapshot(GtkWidget *w,GtkSnapshot *snapshot) {gtk_widget_snapshot_child(w,((LockFit*)w)->child,snapshot);}
static void fit_dispose(GObject *object) {
  LockFit *fit=(LockFit*)object;if(fit->child){gtk_widget_unparent(fit->child);fit->child=NULL;}
  G_OBJECT_CLASS(lock_fit_parent_class)->dispose(object);
}
static void lock_fit_class_init(LockFitClass *klass) {
  klass->measure=fit_measure;klass->size_allocate=fit_allocate;klass->snapshot=fit_snapshot;
  G_OBJECT_CLASS(klass)->dispose=fit_dispose;
}
static void lock_fit_init(LockFit *fit){gtk_widget_set_hexpand(GTK_WIDGET(fit),TRUE);gtk_widget_set_vexpand(GTK_WIDGET(fit),TRUE);}
static GtkWidget *fit_new(GtkWidget *child) {
  LockFit *fit=g_object_new(lock_fit_get_type(),NULL);fit->child=child;gtk_widget_set_parent(child,GTK_WIDGET(fit));return GTK_WIDGET(fit);
}
