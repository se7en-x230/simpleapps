#ifndef SIMPLE_DAYLIGHT_ART_H
#define SIMPLE_DAYLIGHT_ART_H
#include <gtk/gtk.h>
#include <glib/gstdio.h>
#include "simple-images.h"
/* Shared calendar-side portrait; the scheduler atomically switches the symlink.
 * Reload only when its target changes, including while a dashboard stays open. */
typedef struct {
    GtkPicture *picture;
    GdkTexture *texture;
    char *target;
    const char *kind; /* idle or profile; defaults to idle */
    gboolean full_image; /* Wide cards crop to their allocation instead of a portrait. */
} SimpleDaylightArt;
static gboolean simple_daylight_art_update(SimpleDaylightArt *art) {
    if(!art->picture)return FALSE;
    char *link=simple_image_resolve(art->kind?art->kind:"idle");
    if(!link){g_clear_object(&art->texture);g_clear_pointer(&art->target,g_free);gtk_picture_set_paintable(art->picture,NULL);return FALSE;}
    GStatBuf file_stat={0};g_stat(link,&file_stat);char *destination=g_file_read_link(link,NULL);char *target=g_strdup_printf("%s:%s:%lld:%lld",link,destination?destination:"",(long long)file_stat.st_mtime,(long long)file_stat.st_size);g_free(destination);
    if(g_strcmp0(target,art->target)!=0 || !art->texture){
        GdkPixbuf *pix=gdk_pixbuf_new_from_file_at_scale(link,-1,600,TRUE,NULL);
        if(!pix){char *fallback=simple_image_default(art->kind?art->kind:"idle");if(fallback)pix=gdk_pixbuf_new_from_file_at_scale(fallback,-1,600,TRUE,NULL);g_free(fallback);}
        if(pix){
            GdkTexture *texture;
            if(art->full_image){
                GBytes *pixels=gdk_pixbuf_read_pixel_bytes(pix);
                texture=gdk_memory_texture_new(gdk_pixbuf_get_width(pix),gdk_pixbuf_get_height(pix),
                    gdk_pixbuf_get_has_alpha(pix)?GDK_MEMORY_R8G8B8A8:GDK_MEMORY_R8G8B8,
                    pixels,gdk_pixbuf_get_rowstride(pix));
                g_bytes_unref(pixels);
            }else{
            /* Crop the wide wallpaper to a fixed portrait so its natural size
             * cannot stretch the dashboard layout. */
            int h=gdk_pixbuf_get_height(pix),w=gdk_pixbuf_get_width(pix);
            int cw=MIN(w,h*180/250),ch=MIN(h,w*250/180);
            GdkPixbuf *crop=gdk_pixbuf_new_subpixbuf(pix,(w-cw)/2,(h-ch)/2,cw,ch);
            GdkPixbuf *small=gdk_pixbuf_scale_simple(crop,180,250,GDK_INTERP_BILINEAR);
            GBytes *bytes=gdk_pixbuf_read_pixel_bytes(small);
            texture=gdk_memory_texture_new(180,250,
                gdk_pixbuf_get_has_alpha(small)?GDK_MEMORY_R8G8B8A8:GDK_MEMORY_R8G8B8,
                bytes,gdk_pixbuf_get_rowstride(small));
            g_bytes_unref(bytes);g_object_unref(small);g_object_unref(crop);
            }
            g_object_unref(pix);
            g_clear_object(&art->texture);art->texture=texture;
            g_free(art->target);art->target=g_strdup(target);
        }
    }
    g_free(link);g_free(target);
    if(!art->texture)return FALSE;
    gtk_picture_set_paintable(art->picture,GDK_PAINTABLE(art->texture));
    return TRUE;
}
static void simple_daylight_art_clear(SimpleDaylightArt *art){
    g_clear_object(&art->texture);g_clear_pointer(&art->target,g_free);art->picture=NULL;
}
#endif
