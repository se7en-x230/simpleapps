#ifndef SIMPLE_KEYBOARD_H
#define SIMPLE_KEYBOARD_H
#include <gtk/gtk.h>
/* -1: continue app shortcuts; 0: let GTK handle focus/control; 1: activated. */
static inline int simple_control_key(GtkWindow *window,guint key,GdkModifierType state) {
    GdkDisplay *display=gtk_widget_get_display(GTK_WIDGET(window));
    if(!g_object_get_data(G_OBJECT(display),"simple-keyboard-style")) {
        GtkCssProvider *css=gtk_css_provider_new();
        gtk_css_provider_load_from_string(css,"button:focus-visible, checkbutton:focus-visible, switch:focus-visible, dropdown:focus-visible, scale:focus-visible {outline:2px solid #f3a40a;outline-offset:-2px;}");
        gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER+10);
        g_object_set_data_full(G_OBJECT(display),"simple-keyboard-style",css,g_object_unref);
    }
    if(key==GDK_KEY_Tab || key==GDK_KEY_ISO_Left_Tab)return 0;
    if(state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))return -1;
    switch(key) {
    case GDK_KEY_Return:case GDK_KEY_KP_Enter:case GDK_KEY_space:
    case GDK_KEY_Left:case GDK_KEY_Right:case GDK_KEY_Up:case GDK_KEY_Down:
    case GDK_KEY_Home:case GDK_KEY_End:case GDK_KEY_Page_Up:case GDK_KEY_Page_Down:break;
    default:return -1;
    }
    for(GtkWidget *w=gtk_window_get_focus(window);w;w=gtk_widget_get_parent(w)) {
        if(GTK_IS_BUTTON(w)||GTK_IS_CHECK_BUTTON(w)||GTK_IS_SWITCH(w)||GTK_IS_DROP_DOWN(w)||GTK_IS_RANGE(w)||GTK_IS_SPIN_BUTTON(w)) {
            if((key==GDK_KEY_Return||key==GDK_KEY_KP_Enter)&&(GTK_IS_BUTTON(w)||GTK_IS_CHECK_BUTTON(w))) {
                gtk_widget_activate(w);return 1;
            }
            return 0;
        }
    }
    return -1;
}
#endif
