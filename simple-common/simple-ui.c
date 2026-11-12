#define _GNU_SOURCE
#include "simple-ui.h"

#include <dlfcn.h>

/* Apply shared presentation when widgets appear, including asynchronously
   populated detail panes. No polling or per-window background work. */
static GtkWidget *label_button(GtkWidget *label) {
    for(GtkWidget *w=gtk_widget_get_parent(label);w;w=gtk_widget_get_parent(w)) {
        if(GTK_IS_BUTTON(w))return gtk_widget_has_css_class(w,"keycap")?NULL:w;
        if(GTK_IS_WINDOW(w))break;
    }
    return NULL;
}
static void shortcut_label(GObject *object,GParamSpec *spec,gpointer unused) {
    (void)spec;(void)unused;
    GtkLabel *label=GTK_LABEL(object);GtkWidget *button=label_button(GTK_WIDGET(label));
    if(!button)return;
    const char *text=gtk_label_get_text(label),*key=strrchr(text,'['),*start=NULL;
    if(key&&key>text&&text[strlen(text)-1]==']')start=key;
    if(!start) {
        key=g_strrstr(text," · ");
        if(key) {
            const char *tail=key+strlen(" · ");
            if(g_utf8_strlen(tail,-1)==1||strstr(tail,"Ctrl")||strstr(tail,"Alt")||
               strstr(tail,"Shift")||!strcmp(tail,"Enter")||!strcmp(tail,"Esc")||!strcmp(tail,"Space"))start=tail;
        }
    }
    PangoAttrList *base=g_object_get_data(object,"simple-shortcut-base");
    PangoAttrList *attrs=base?pango_attr_list_copy(base):pango_attr_list_new();
    if(start) {
        gboolean tab=FALSE;
        for(GtkWidget *w=gtk_widget_get_parent(button);w&&!GTK_IS_WINDOW(w);w=gtk_widget_get_parent(w))
            if(gtk_widget_has_css_class(w,"simple-tabs")){tab=TRUE;break;}
        GdkRGBA color;
        const char *name=tab&&!(gtk_widget_get_state_flags(button)&GTK_STATE_FLAG_CHECKED)?"simple_muted":"simple_shortcut";
        G_GNUC_BEGIN_IGNORE_DEPRECATIONS
        gboolean found=gtk_style_context_lookup_color(gtk_widget_get_style_context(button),name,&color);
        G_GNUC_END_IGNORE_DEPRECATIONS
        if(!found)gdk_rgba_parse(&color,"#51483d");
        PangoAttribute *attr=pango_attr_foreground_new(color.red*65535,color.green*65535,color.blue*65535);
        attr->start_index=start-text;attr->end_index=strlen(text);pango_attr_list_change(attrs,attr);
    }
    gtk_label_set_attributes(label,attrs);pango_attr_list_unref(attrs);
}
static void shortcut_state(GtkWidget *button,GtkStateFlags previous,gpointer label) {
    (void)button;(void)previous;shortcut_label(G_OBJECT(label),NULL,NULL);
}
static gboolean shared_widget_mapped(GSignalInvocationHint *hint,guint count,const GValue *values,gpointer unused) {
    (void)hint;(void)count;(void)unused;
    GtkWidget *widget=g_value_get_object(values);GtkRoot *root=gtk_widget_get_root(widget);
    if(!root||!gtk_widget_has_css_class(GTK_WIDGET(root),"simple-app"))return TRUE;
    GtkWidget *parent=gtk_widget_get_parent(widget);
    const char *css_name=gtk_widget_get_css_name(widget);
    gboolean paned_content=parent&&GTK_IS_PANED(parent)&&!GTK_IS_SEPARATOR(widget)&&g_strcmp0(css_name,"separator");
    if(GTK_IS_SCROLLED_WINDOW(widget)||paned_content) {
        gboolean framed=gtk_widget_has_css_class(widget,"card");
        for(GtkWidget *w=parent;w&&!GTK_IS_WINDOW(w);w=gtk_widget_get_parent(w))
            if(gtk_widget_has_css_class(w,"card")||gtk_widget_has_css_class(w,"pane")||GTK_IS_POPOVER(w))framed=TRUE;
        if(!framed)gtk_widget_add_css_class(widget,"pane");
    }
    if(GTK_IS_LABEL(widget)&&label_button(widget)) {
        if(!g_object_get_data(G_OBJECT(widget),"simple-shortcut-watched")) {
            PangoAttrList *base=gtk_label_get_attributes(GTK_LABEL(widget));
            if(base)g_object_set_data_full(G_OBJECT(widget),"simple-shortcut-base",pango_attr_list_copy(base),(GDestroyNotify)pango_attr_list_unref);
            g_object_set_data(G_OBJECT(widget),"simple-shortcut-watched",GINT_TO_POINTER(1));
            g_signal_connect(widget,"notify::label",G_CALLBACK(shortcut_label),NULL);
            g_signal_connect_object(label_button(widget),"state-flags-changed",G_CALLBACK(shortcut_state),widget,0);
        }
        shortcut_label(G_OBJECT(widget),NULL,NULL);
    }
    return TRUE;
}
static void load_theme_files(GtkCssProvider *provider, const char *path) {
    GdkDisplay *display=gdk_display_get_default();
    GtkCssProvider *shared=g_object_get_data(G_OBJECT(display),"simple-shared-theme");
    if(!shared) {
        shared=gtk_css_provider_new();
        gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(shared),GTK_STYLE_PROVIDER_PRIORITY_USER-1);
        g_object_set_data_full(G_OBJECT(display),"simple-shared-theme",shared,g_object_unref);
    }
    char *base=g_build_filename(g_get_user_config_dir(),"simple","aliases.css",NULL);
    if(!g_file_test(base,G_FILE_TEST_IS_REGULAR)) {
        g_free(base);base=g_build_filename(g_get_user_config_dir(),"simple","theme.css",NULL);
    }
    if(!g_file_test(base,G_FILE_TEST_IS_REGULAR)) {
        g_free(base);base=g_build_filename(g_get_user_data_dir(),"simple","aliases.css",NULL);
    }
    if(g_file_test(base,G_FILE_TEST_IS_REGULAR)) gtk_css_provider_load_from_path(shared,base);
    else gtk_css_provider_load_from_string(shared,"");
    g_free(base);
    if(path && g_file_test(path,G_FILE_TEST_IS_REGULAR)) gtk_css_provider_load_from_path(provider,path);
    else gtk_css_provider_load_from_string(provider,"");
}

/* Search state belongs to the window. Widgets are held weakly, never retained. */
typedef struct {
    GWeakRef search, navigation;
    GKeyFile *keys;
    char *app;
    SimpleUISearchCallback callback;
    gpointer data;
    gboolean escape_closes;
} SearchBinding;
static gboolean interaction(const char *app,const char *key,gboolean fallback) {
    const char *scopes[]={"simple",app&&g_str_has_prefix(app,"simplepicker/")?"simplepicker":NULL,app};
    for(guint i=0;i<G_N_ELEMENTS(scopes);i++) {
        if(!scopes[i]||g_path_is_absolute(scopes[i])||strstr(scopes[i],".."))continue;
        char *path=g_build_filename(g_get_user_config_dir(),scopes[i],"keys.ini",NULL);
        GKeyFile *file=g_key_file_new();GError *error=NULL;
        if(g_key_file_load_from_file(file,path,0,NULL)&&g_key_file_has_key(file,"interaction",key,NULL)) {
            gboolean value=g_key_file_get_boolean(file,"interaction",key,&error);
            if(!error)fallback=value;
            else g_warning("%s: %s",path,error->message);
        }
        g_clear_error(&error);g_key_file_unref(file);g_free(path);
    }
    return fallback;
}
static void search_free(gpointer data) {
    SearchBinding *b=data;g_weak_ref_clear(&b->search);g_weak_ref_clear(&b->navigation);g_free(b->app);if(b->keys)g_key_file_unref(b->keys);g_free(b);
}
void simple_ui_bind_search(GtkWindow *window,GtkWidget *search,GtkWidget *navigation,
                          const char *app,SimpleUISearchCallback callback,gpointer data) {
    g_return_if_fail(GTK_IS_EDITABLE(search));
    SearchBinding *b=g_new0(SearchBinding,1);
    g_weak_ref_init(&b->search,search);g_weak_ref_init(&b->navigation,navigation);
    b->app=g_strdup(app);b->callback=callback;b->data=data;
    b->escape_closes=interaction(app,"escape_closes",FALSE);
    g_object_set_data_full(G_OBJECT(window),"simple-ui-search",b,search_free);
}
void simple_ui_search_keys(GtkWindow *window,GKeyFile *keys) {
    SearchBinding *b=g_object_get_data(G_OBJECT(window),"simple-ui-search");if(!b)return;
    if(b->keys)g_key_file_unref(b->keys);
    b->keys=g_key_file_ref(keys);
    if(g_key_file_has_key(keys,"interaction","escape_closes",NULL))b->escape_closes=g_key_file_get_boolean(keys,"interaction","escape_closes",NULL);
}
static gboolean search_matches(SearchBinding *b,const char *action,guint key,GdkModifierType state) {
    if(!b->keys)return simple_ui_key_matches(b->app,action,key,state);
    char *value=g_key_file_get_string(b->keys,"navigation",action,NULL);
    if(!value)return simple_ui_key_matches(b->app,action,key,state);
    char **parts=g_strsplit(value,",",-1);gboolean matched=FALSE;
    for(guint i=0;parts[i];i++) {
        guint wanted;GdkModifierType mods;
        if(gtk_accelerator_parse(g_strstrip(parts[i]),&wanted,&mods)&&gdk_keyval_to_lower(key)==gdk_keyval_to_lower(wanted)&&(state&gtk_accelerator_get_default_mod_mask())==mods)matched=TRUE;
    }
    g_strfreev(parts);g_free(value);return matched;
}
static void search_action(SearchBinding *b,SimpleUISearchAction action) {if(b->callback)b->callback(action,b->data);}
static void search_mode(SearchBinding *b,GtkWidget *entry,GtkWidget *nav,gboolean searching,gboolean clear) {
    if(clear)gtk_editable_set_text(GTK_EDITABLE(entry),"");
    gtk_widget_set_visible(entry,searching);
    gtk_editable_set_editable(GTK_EDITABLE(entry),searching);
    search_action(b,searching?SIMPLE_UI_SEARCH_FOCUS:SIMPLE_UI_SEARCH_NAVIGATE);
    /* Callbacks may update their own widgets, but the framework owns focus. */
    gtk_widget_set_visible(entry,searching);
    gtk_widget_grab_focus(searching?entry:nav);
}
void simple_ui_search_set(GtkWindow *window,gboolean searching) {
    SearchBinding *b=g_object_get_data(G_OBJECT(window),"simple-ui-search");if(!b)return;
    GtkWidget *entry=g_weak_ref_get(&b->search),*nav=g_weak_ref_get(&b->navigation);
    if(entry&&nav)search_mode(b,entry,nav,searching,!searching);
    g_clear_object(&entry);g_clear_object(&nav);
}
void simple_ui_search_start(GtkWindow *window,gboolean fallback) {
    SearchBinding *b=g_object_get_data(G_OBJECT(window),"simple-ui-search");if(!b)return;
    gboolean searching=interaction(b->app,"start_in_search",fallback);
    if(b->keys&&g_key_file_has_key(b->keys,"interaction","start_in_search",NULL))searching=g_key_file_get_boolean(b->keys,"interaction","start_in_search",NULL);
    GtkWidget *entry=g_weak_ref_get(&b->search),*nav=g_weak_ref_get(&b->navigation);
    if(entry&&nav)search_mode(b,entry,nav,searching,FALSE);
    g_clear_object(&entry);g_clear_object(&nav);
}
static int search_control(GtkWindow *window,guint key,GdkModifierType state) {
    SearchBinding *b=g_object_get_data(G_OBJECT(window),"simple-ui-search");if(!b)return -1;
    GtkWidget *entry=g_weak_ref_get(&b->search),*nav=g_weak_ref_get(&b->navigation);
    if(!entry||!nav){g_clear_object(&entry);g_clear_object(&nav);return -1;}
    GtkWidget *focus=gtk_window_get_focus(window);
    gboolean entry_focus=focus&&(focus==entry||gtk_widget_is_ancestor(focus,entry));
    gboolean typing=entry_focus&&gtk_editable_get_editable(GTK_EDITABLE(entry));
    gboolean in_nav=focus&&(focus==nav||gtk_widget_is_ancestor(focus,nav));
    int result=-1;
    /* Never reinterpret compose/editor, location, password, or filename input. */
    if((!gtk_widget_get_mapped(entry)&&!gtk_widget_get_mapped(nav))||(!entry_focus&&simple_ui_editing(window)))goto done;
    GdkModifierType mods=state&gtk_accelerator_get_default_mod_mask();
    if(search_matches(b,"cancel",key,state)) {
        if(gtk_widget_get_visible(entry)&&!b->escape_closes) {
            search_mode(b,entry,nav,FALSE,TRUE);
        } else gtk_window_close(window);
        result=1;
    } else if(mods==GDK_CONTROL_MASK&&(key==GDK_KEY_Return||key==GDK_KEY_KP_Enter)) {
        search_mode(b,entry,nav,FALSE,FALSE);result=1;
    } else if((typing||in_nav||entry_focus)&&search_matches(b,"activate",key,state)) {
        search_action(b,SIMPLE_UI_SEARCH_ACTIVATE);result=1;
    } else if((typing?(mods!=0||key==GDK_KEY_Up||key==GDK_KEY_Down):(in_nav||entry_focus))&&
              (search_matches(b,"down",key,state)||search_matches(b,"up",key,state))) {
        search_action(b,search_matches(b,"down",key,state)?SIMPLE_UI_SEARCH_DOWN:SIMPLE_UI_SEARCH_UP);
        focus=gtk_window_get_focus(window);
        if(typing)gtk_widget_grab_focus(entry);
        else if(!focus||(focus!=nav&&!gtk_widget_is_ancestor(focus,nav)))
            gtk_widget_grab_focus(nav);
        result=1;
    } else if(!typing&&(in_nav||entry_focus)&&!mods&&key==GDK_KEY_q) {
        gtk_window_close(window);result=1;
    } else if(!typing&&!mods&&key==GDK_KEY_slash) {
        search_mode(b,entry,nav,TRUE,FALSE);result=1;
    }
done:
    g_object_unref(entry);g_object_unref(nav);return result;
}

unsigned simple_ui_abi_version(void) { return 1; }
void simple_ui_free(void *memory) { g_free(memory); }
void simple_ui_init(void) {
    GdkDisplay *display=gdk_display_get_default();
    g_return_if_fail(display!=NULL);
    if(g_object_get_data(G_OBJECT(display),"simple-ui-v1"))return;
    g_signal_add_emission_hook(g_signal_lookup("map",GTK_TYPE_WIDGET),0,shared_widget_mapped,NULL,NULL);
    GtkCssProvider *css=gtk_css_provider_new();
    load_theme_files(css,NULL);
    Dl_info location;
    char *dir=NULL;
    if(dladdr((void *)simple_ui_init,&location))dir=g_path_get_dirname(location.dli_fname);
    char *path=dir?g_build_filename(dir,"framework.css",NULL):NULL;
    char *palette=dir?g_build_filename(dir,"palette.css",NULL):NULL;
    if(palette && g_file_test(palette,G_FILE_TEST_IS_REGULAR)) {
        GtkCssProvider *defaults=gtk_css_provider_new();
        gtk_css_provider_load_from_path(defaults,palette);
        gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(defaults),GTK_STYLE_PROVIDER_PRIORITY_APPLICATION);
        g_object_unref(defaults);
    }
    g_free(palette);
    if(path && g_file_test(path,G_FILE_TEST_IS_REGULAR))gtk_css_provider_load_from_path(css,path);
    else g_warning("Simple UI stylesheet missing beside the library: %s",path?path:"unknown location");
    gtk_style_context_add_provider_for_display(display,GTK_STYLE_PROVIDER(css),GTK_STYLE_PROVIDER_PRIORITY_USER+4);
    g_object_set_data_full(G_OBJECT(display),"simple-ui-v1",css,g_object_unref);
    g_free(path);g_free(dir);
}
void simple_ui_window(GtkWindow *window) {
    simple_ui_init();
    gtk_widget_add_css_class(GTK_WIDGET(window),"simple-app");
    if(GTK_IS_APPLICATION_WINDOW(window)) {
        GtkApplication *app=gtk_window_get_application(window);
        const char *id=app?g_application_get_application_id(G_APPLICATION(app)):NULL;
        if(id)g_object_set_data_full(G_OBJECT(window),"simple-ui-app",g_ascii_strdown(strrchr(id,'.')?strrchr(id,'.')+1:id,-1),g_free);
    }
}
gboolean simple_ui_editing(GtkWindow *window) {
    for(GtkWidget *w=gtk_window_get_focus(window);w;w=gtk_widget_get_parent(w))
        if(GTK_IS_EDITABLE(w)||GTK_IS_TEXT_VIEW(w))return TRUE;
    return FALSE;
}
int simple_ui_control_key(GtkWindow *window,guint key,GdkModifierType state) {
    int search=search_control(window,key,state);if(search>=0)return search;
    if(key==GDK_KEY_Tab||key==GDK_KEY_ISO_Left_Tab)return 0;
    if(simple_ui_editing(window))return 0;
    if((state&gtk_accelerator_get_default_mod_mask())==GDK_CONTROL_MASK) {
        const char *app=g_object_get_data(G_OBJECT(window),"simple-ui-app");
        if(simple_ui_key_matches(app,"down",key,state)||simple_ui_key_matches(app,"up",key,state)) {
            gtk_widget_child_focus(GTK_WIDGET(window),simple_ui_key_matches(app,"down",key,state)?GTK_DIR_TAB_FORWARD:GTK_DIR_TAB_BACKWARD);return 1;
        }
    }
    if(state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))return -1;
    switch(key) {
    case GDK_KEY_Return:case GDK_KEY_KP_Enter:case GDK_KEY_space:
    case GDK_KEY_Left:case GDK_KEY_Right:case GDK_KEY_Up:case GDK_KEY_Down:
    case GDK_KEY_Home:case GDK_KEY_End:case GDK_KEY_Page_Up:case GDK_KEY_Page_Down:break;
    default:return -1;
    }
    for(GtkWidget *w=gtk_window_get_focus(window);w;w=gtk_widget_get_parent(w)) {
        if(GTK_IS_BUTTON(w)||GTK_IS_CHECK_BUTTON(w)||GTK_IS_SWITCH(w)||GTK_IS_DROP_DOWN(w)||GTK_IS_RANGE(w)) {
            if((key==GDK_KEY_Return||key==GDK_KEY_KP_Enter)&&(GTK_IS_BUTTON(w)||GTK_IS_CHECK_BUTTON(w))) {
                gtk_widget_activate(w);return 1;
            }
            return 0;
        }
    }
    return -1;
}
static char *binding(const char *app,const char *action) {
    /* UI-thread cache: no filesystem work while navigating after first lookup. */
    static GHashTable *cache;
    if(!cache)cache=g_hash_table_new_full(g_str_hash,g_str_equal,g_free,g_free);
    char *cache_key=g_strdup_printf("%s:%s",app?app:"",action);
    const char *cached=g_hash_table_lookup(cache,cache_key);
    if(cached){g_free(cache_key);return g_strdup(cached);}
    const char *names[]={"up","down","left","right","activate","cancel","page_up","page_down"};
    const char *defaults[]={"Up,k,<Control>k","Down,j,<Control>j","Left,h,<Control>h","Right,l,<Control>l","Return,KP_Enter","Escape","Page_Up,<Control>u","Page_Down,<Control>d"};
    char *value=g_strdup("");
    for(unsigned i=0;i<G_N_ELEMENTS(names);i++)if(!strcmp(action,names[i])){g_free(value);value=g_strdup(defaults[i]);break;}
    const char *scopes[]={"simple",app&&g_str_has_prefix(app,"simplepicker/")?"simplepicker":NULL,app};
    for(unsigned i=0;i<G_N_ELEMENTS(scopes);i++) {
        if(!scopes[i]||g_path_is_absolute(scopes[i])||strstr(scopes[i],".."))continue;
        char *path=g_build_filename(g_get_user_config_dir(),scopes[i],"keys.ini",NULL);
        GKeyFile *file=g_key_file_new();
        if(g_key_file_load_from_file(file,path,G_KEY_FILE_NONE,NULL)) {
            char *configured=g_key_file_get_string(file,"navigation",action,NULL);
            if(configured){g_free(value);value=configured;}
        }
        g_key_file_unref(file);g_free(path);
    }
    g_hash_table_insert(cache,cache_key,g_strdup(value));
    return value;
}
gboolean simple_ui_key_matches(const char *app,const char *action,guint key,GdkModifierType state) {
    char *value=binding(app,action);char **parts=g_strsplit(value,",",-1);gboolean found=FALSE;
    for(unsigned i=0;parts[i];i++) {
        guint wanted;GdkModifierType mods;
        if(gtk_accelerator_parse(g_strstrip(parts[i]),&wanted,&mods)&&gdk_keyval_to_lower(key)==gdk_keyval_to_lower(wanted)&&(state&gtk_accelerator_get_default_mod_mask())==mods)found=TRUE;
    }
    g_strfreev(parts);g_free(value);return found;
}
char *simple_ui_key_label(const char *app,const char *action) {
    char *value=binding(app,action);char **parts=g_strsplit(value,",",-1);char *result=g_strdup("Disabled");
    for(unsigned i=0;parts[i];i++) {
        guint key;GdkModifierType mods;
        if(gtk_accelerator_parse(g_strstrip(parts[i]),&key,&mods)) {
            g_free(result);result=gtk_accelerator_get_label(key,mods);break;
        }
    }
    g_strfreev(parts);g_free(value);return result;
}

void simple_ui_theme_load(GtkCssProvider *provider,const char *path) {
    simple_ui_init();
    load_theme_files(provider,path);
}
int simple_ui_legacy_control_key(GtkWindow *window,guint key,GdkModifierType state) {
    int search=search_control(window,key,state);if(search>=0)return search;
    /* Legacy apps handle Enter/Escape within their own editors after this guard. */
    if(key==GDK_KEY_Tab||key==GDK_KEY_ISO_Left_Tab)return 0;
    if(simple_ui_editing(window))return -1;
    return simple_ui_control_key(window,key,state);
}
