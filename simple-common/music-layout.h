#ifndef SIMPLE_MUSIC_LAYOUT_H
#define SIMPLE_MUSIC_LAYOUT_H
#include <gtk/gtk.h>
typedef struct {
  GtkWidget *grid,*music,*side,*art,*art_card,*metadata,*visualizer,*status,*headline;
  gboolean fullscreen,playing,initialized;
  int idle_size,metadata_columns,playing_size;
} SimpleMusicLayout;
static inline void simple_music_move(GtkWidget *widget,GtkWidget *parent,int row,int columns) {
  GtkWidget *old=gtk_widget_get_parent(widget);
  if(old==parent)return;
  g_object_ref(widget);
  if(GTK_IS_BOX(old))gtk_box_remove(GTK_BOX(old),widget);
  else if(GTK_IS_GRID(old))gtk_grid_remove(GTK_GRID(old),widget);
  if(GTK_IS_BOX(parent))gtk_box_append(GTK_BOX(parent),widget);
  else gtk_grid_attach(GTK_GRID(parent),widget,0,row,columns,1);
  g_object_unref(widget);
}
/* Both playback states use the same header, two columns and full-width Cava. */
static inline void simple_music_layout(SimpleMusicLayout *l,gboolean playing) {
  if(l->initialized && l->playing==playing)return;
  l->initialized=TRUE;l->playing=playing;
  gtk_widget_set_visible(l->headline,TRUE);
  gtk_widget_set_visible(l->status,FALSE);
  simple_music_move(l->metadata,l->music,0,1);
  simple_music_move(l->visualizer,l->grid,1,2);
  gtk_widget_set_vexpand(l->art,FALSE);gtk_widget_set_vexpand(l->art_card,FALSE);
  gtk_widget_set_vexpand(l->visualizer,FALSE);
  int width=0,height=0,metadata=0;
  gtk_widget_measure(l->side,GTK_ORIENTATION_HORIZONTAL,-1,NULL,&width,NULL,NULL);
  gtk_widget_measure(l->side,GTK_ORIENTATION_VERTICAL,width,NULL,&height,NULL,NULL);
  gtk_widget_measure(l->metadata,GTK_ORIENTATION_VERTICAL,width,NULL,&metadata,NULL,NULL);
  /* Align the artwork plus its caption card with the system column. */
  int size=MAX(180,height-metadata-24-10);
  l->playing_size=size;
  gtk_widget_set_size_request(l->art,size,size);
  gtk_widget_set_size_request(l->music,size+24,-1);
}
#endif
