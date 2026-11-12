#include "../simple-common/simple-keyboard.h"
#include <gtk/gtk.h>
#include <json-c/json.h>
#include "../simple-common/simple-theme.h"
#include "visualizer.h"
#include "../simple-common/song-progress.h"

static GtkWidget *window,*search,*list,*heading,*message,*track,*artist,*pause_button,*shuffle,*ordered,*refresh;
static GtkWidget *cover,*cover_stack,*album,*browser,*now,*wallpaper,*song_progress;
static GtkWidget *source_buttons[3],*favourite_button,*live_label,*stream_play;
static const char *source_names[]={"local","radio","youtube"};
static guint source_index;
static char *source_folders[3],*source_queries[3];
static char *current_track,*wallpaper_stamp,*rendered_query;
static gboolean pending_play,pending_ordered,browsing,gprefix;
static void play_selected(gboolean ordered_mode);
static GSubprocess *bridge;
static GDataInputStream *reader;
static char *folder,*assets;
static guint query_timer,serial;
static gboolean loading;

static const char *str(json_object *obj,const char *key) {
    json_object *value=NULL;
    return json_object_object_get_ex(obj,key,&value)?json_object_get_string(value):"";
}
static gboolean boolean(json_object *obj,const char *key) {
    json_object *value=NULL;
    return json_object_object_get_ex(obj,key,&value)&&json_object_get_boolean(value);
}
static void send(json_object *data) {
    if(bridge) {
        const char *text=json_object_to_json_string_ext(data,JSON_C_TO_STRING_PLAIN);
        char *line=g_strconcat(text,"\n",NULL);GError *error=NULL;
        if(!g_output_stream_write_all(g_subprocess_get_stdin_pipe(bridge),line,strlen(line),NULL,NULL,&error)) {
            gtk_label_set_text(GTK_LABEL(message),error->message);g_clear_error(&error);
        }
        g_free(line);
    }
    json_object_put(data);
}
static json_object *request(const char *action) {
    json_object *data=json_object_new_object();json_object_object_add(data,"action",json_object_new_string(action));json_object_object_add(data,"source",json_object_new_string(source_names[source_index]));return data;
}
static void browse(void) {
    json_object *data=request("browse");
    json_object_object_add(data,"id",json_object_new_int(++serial));
    json_object_object_add(data,"path",json_object_new_string(folder?folder:""));
    json_object_object_add(data,"query",json_object_new_string(gtk_editable_get_text(GTK_EDITABLE(search))));send(data);
}
static gboolean query(gpointer unused) {(void)unused;query_timer=0;browse();return G_SOURCE_REMOVE;}
static void searched(GtkSearchEntry *entry,gpointer unused) {
    (void)entry;(void)unused;pending_play=FALSE;serial++;if(query_timer)g_source_remove(query_timer);query_timer=g_timeout_add(source_index?650:75,query,NULL);
}
static void open_folder(const char *path) {
    g_free(folder);folder=g_strdup(path);gtk_editable_set_text(GTK_EDITABLE(search),"");browse();
}
static void activated(GtkListBox *box,GtkListBoxRow *row,gpointer unused) {
    (void)box;(void)unused;const char *path=g_object_get_data(G_OBJECT(row),"path");if(path){if(source_index)play_selected(TRUE);else open_folder(path);}
}
static void back(GtkButton *button,gpointer unused) {
    (void)button;(void)unused;if(source_index){gtk_editable_set_text(GTK_EDITABLE(search),"");browse();return;}char *parent=g_strdup(folder?folder:"");char *slash=strrchr(parent,'/');
    if(slash)*slash=0;else *parent=0;open_folder(parent);g_free(parent);
}
static void show_order(const char *mode) {
    if(strcmp(mode,"shuffle")&&strcmp(mode,"ordered"))return;
    gboolean in_order=!strcmp(mode,"ordered");
    gtk_widget_remove_css_class(in_order?shuffle:ordered,"primary");
    gtk_widget_add_css_class(in_order?ordered:shuffle,"primary");
}
static void play(GtkButton *button,gpointer mode) {
    (void)button;if(source_index){play_selected(TRUE);return;}if(loading)return;json_object *data=request("play");
    json_object_object_add(data,"path",json_object_new_string(folder?folder:""));
    json_object_object_add(data,"order",json_object_new_string(mode));send(data);
}
static void control(GtkButton *button,gpointer command) {
    (void)button;json_object *data=request("control");json_object_object_add(data,"command",json_object_new_string(command));send(data);
    send(request("status"));
}
static void rescan(GtkButton *button,gpointer unused) {(void)button;(void)unused;if(source_index)browse();else send(request("refresh"));}
static GtkWidget *label(const char *text,const char *css) {
    GtkWidget *widget=gtk_label_new(text);gtk_label_set_xalign(GTK_LABEL(widget),0);
    gtk_label_set_ellipsize(GTK_LABEL(widget),PANGO_ELLIPSIZE_END);
    if(css)gtk_widget_add_css_class(widget,css);
    return widget;
}
static GtkWidget *icon_button(const char *icon,const char *tip,GCallback callback,gpointer data) {
    GtkWidget *button=gtk_button_new_from_icon_name(icon);gtk_widget_set_tooltip_text(button,tip);
    gtk_accessible_update_property(GTK_ACCESSIBLE(button),GTK_ACCESSIBLE_PROPERTY_LABEL,tip,-1);
    g_signal_connect(button,"clicked",callback,data);return button;
}
static void show_library(gboolean visible) {
    browsing=visible;
    gtk_widget_grab_focus(visible?list:pause_button);
}
static void play_selected(gboolean ordered_mode) {
    if(loading)return;
    if(g_strcmp0(rendered_query,gtk_editable_get_text(GTK_EDITABLE(search)))) {
        pending_play=source_index==0;pending_ordered=ordered_mode;if(query_timer){g_source_remove(query_timer);query_timer=0;}browse();return;
    }
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));
    const char *path=row?g_object_get_data(G_OBJECT(row),"path"):NULL;
    if(!path)return;
    json_object *data=request("play");json_object_object_add(data,"path",json_object_new_string(path));
    json_object_object_add(data,"order",json_object_new_string(ordered_mode?"ordered":"shuffle"));send(data);
}
static void choose_source(GtkButton *button,gpointer value) {
    if(button&&!gtk_toggle_button_get_active(GTK_TOGGLE_BUTTON(button)))return;
    guint next=GPOINTER_TO_UINT(value);if(next==source_index)return;
    g_free(source_folders[source_index]);source_folders[source_index]=g_strdup(folder?folder:"");
    g_free(source_queries[source_index]);source_queries[source_index]=g_strdup(gtk_editable_get_text(GTK_EDITABLE(search)));
    source_index=next;pending_play=FALSE;gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(list),next==0);
    GtkWidget *child;while((child=gtk_widget_get_first_child(list)))gtk_list_box_remove(GTK_LIST_BOX(list),child);
    g_free(folder);folder=g_strdup(source_folders[next]?source_folders[next]:"");
    gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(source_buttons[next]),TRUE);
    gtk_widget_set_visible(shuffle,!next);gtk_widget_set_visible(ordered,!next);gtk_widget_set_visible(favourite_button,next!=0);gtk_widget_set_visible(stream_play,next!=0);
    const char *hints[]={"Search artists, albums…","Search stations or paste a stream URL…","Search YouTube or paste a link…"};
    g_object_set(search,"placeholder-text",hints[next],NULL);
    gtk_editable_set_text(GTK_EDITABLE(search),source_queries[next]?source_queries[next]:"");
    gtk_widget_set_visible(search,TRUE);
    if(query_timer){g_source_remove(query_timer);query_timer=0;}
    gtk_label_set_text(GTK_LABEL(message),next?"Enter play · f favourite · / search":"Enter shuffle · Shift+Enter ordered · Ctrl+J/K selects");
    g_clear_pointer(&rendered_query,g_free);browse();simple_ui_search_start(GTK_WINDOW(window),FALSE);
}
static void favourite(GtkButton *button,gpointer unused) {
    (void)button;(void)unused;if(!source_index)return;
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));
    const char *path=row?g_object_get_data(G_OBJECT(row),"path"):NULL;if(!path)return;
    json_object *data=request("favourite");json_object_object_add(data,"path",json_object_new_string(path));send(data);
}
static void move_selection(int direction,gboolean keep_search) {
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));
    int index=row?gtk_list_box_row_get_index(row):-1;
    row=gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),MAX(0,index+direction));
    if(row){gtk_list_box_select_row(GTK_LIST_BOX(list),row);gtk_widget_grab_focus(GTK_WIDGET(row));}
    if(keep_search)gtk_widget_grab_focus(search);
}
static void rows(json_object *data) {
    json_object *id=NULL;json_object_object_get_ex(data,"id",&id);if((guint)json_object_get_int(id)!=serial)return;
    g_free(rendered_query);rendered_query=g_strdup(gtk_editable_get_text(GTK_EDITABLE(search)));
    GtkWidget *child;while((child=gtk_widget_get_first_child(list)))gtk_list_box_remove(GTK_LIST_BOX(list),child);

    json_object *items=NULL;json_object_object_get_ex(data,"rows",&items);
    size_t count=json_object_array_length(items);
    for(size_t i=0;i<count;i++) {
        json_object *item=json_object_array_get_idx(items,i);
        GtkWidget *row=gtk_list_box_row_new(),*box=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12),*texts=gtk_box_new(GTK_ORIENTATION_VERTICAL,3);
        const char *name=str(item,"icon");GtkWidget *icon;
        if(*name) {
            char *filename=g_strdup_printf("%s/icons/%s-symbolic.svg",assets,name);
            GFile *file=g_file_new_for_path(filename);GIcon *gicon=g_file_icon_new(file);
            icon=gtk_image_new_from_gicon(gicon);g_object_unref(gicon);g_object_unref(file);g_free(filename);
        } else icon=gtk_image_new_from_icon_name(source_index?"network-transmit-receive-symbolic":"folder-music-symbolic");
        gtk_image_set_pixel_size(GTK_IMAGE(icon),24);gtk_widget_add_css_class(icon,"genre-icon");
        gtk_widget_add_css_class(box,"music-row");gtk_widget_set_hexpand(texts,TRUE);
        gtk_box_append(GTK_BOX(texts),label(str(item,"title"),"row-title"));
        gtk_box_append(GTK_BOX(texts),label(str(item,"subtitle"),"row-detail"));
        gtk_box_append(GTK_BOX(box),icon);gtk_box_append(GTK_BOX(box),texts);
        GtkWidget *chevron=gtk_image_new_from_icon_name("go-next-symbolic");gtk_widget_add_css_class(chevron,"chevron");gtk_box_append(GTK_BOX(box),chevron);
        gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(row),box);
        g_object_set_data_full(G_OBJECT(row),"path",g_strdup(str(item,"path")),g_free);gtk_list_box_append(GTK_LIST_BOX(list),row);
    }
    if(count)gtk_list_box_select_row(GTK_LIST_BOX(list),gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),0));
    if(!count) {
        GtkWidget *empty=label(source_index?str(data,"message"):(*gtk_editable_get_text(GTK_EDITABLE(search))?"No matching folders":str(data,"message")),"empty");
        gtk_label_set_wrap(GTK_LABEL(empty),TRUE);gtk_list_box_append(GTK_LIST_BOX(list),empty);
    }
    if(source_index)gtk_label_set_text(GTK_LABEL(message),count?"Enter play · f favourite · / search":"/ search · Ctrl+R retry");
    if(pending_play){pending_play=FALSE;play_selected(pending_ordered);}
}
static gboolean load_picture(GtkWidget *picture,const char *file) {
    if(!file||!*file)return FALSE;
    GError *error=NULL;GdkTexture *texture=gdk_texture_new_from_filename(file,&error);
    if(!texture){g_clear_error(&error);return FALSE;}
    gtk_picture_set_paintable(GTK_PICTURE(picture),GDK_PAINTABLE(texture));g_object_unref(texture);return TRUE;
}
static void show_art(const char *file) {
    gboolean loaded=load_picture(cover,file);
    if(!loaded)gtk_picture_set_paintable(GTK_PICTURE(cover),NULL);
    gtk_stack_set_visible_child_name(GTK_STACK(cover_stack),loaded?"cover":"empty");
}
static void received(GObject *source,GAsyncResult *result,gpointer unused) {
    (void)unused;GError *error=NULL;gsize length=0;
    char *line=g_data_input_stream_read_line_finish(G_DATA_INPUT_STREAM(source),result,&length,&error);
    if(!line) {
        if(window)gtk_label_set_text(GTK_LABEL(message),error?error->message:"Music helper stopped. Close and reopen Simpleplayer.");
        g_clear_error(&error);return;
    }
    json_object *data=json_tokener_parse(line);g_free(line);
    if(data) {
        const char *event=str(data,"event");
        if(!strcmp(event,"rows"))rows(data);
        else if(!strcmp(event,"searching")){json_object *id=NULL;json_object_object_get_ex(data,"id",&id);if((guint)json_object_get_int(id)==serial)gtk_label_set_text(GTK_LABEL(message),str(data,"message"));}
        else if(!strcmp(event,"saved")){gtk_label_set_text(GTK_LABEL(message),str(data,"message"));if(!*gtk_editable_get_text(GTK_EDITABLE(search)))browse();}
        else if(!strcmp(event,"refreshed")){browse();gtk_label_set_text(GTK_LABEL(message),"Library refreshed");}
        else if(!strcmp(event,"error")||!strcmp(event,"notice")) {
            gtk_label_set_text(GTK_LABEL(message),str(data,"message"));
            if(!strcmp(event,"notice")){show_order(str(data,"order"));show_library(FALSE);}
        } else if(!strcmp(event,"wallpaper")) {
            if(g_strcmp0(wallpaper_stamp,str(data,"stamp"))){
                g_free(wallpaper_stamp);wallpaper_stamp=g_strdup(str(data,"stamp"));
                const char *file=str(data,"file");if(!load_picture(wallpaper,file))load_picture(wallpaper,str(data,"fallback"));
            }
        }
        else if(!strcmp(event,"busy")) {
            loading=boolean(data,"busy");gtk_widget_set_sensitive(shuffle,!loading);gtk_widget_set_sensitive(ordered,!loading);gtk_widget_set_sensitive(refresh,!loading);
            if(loading)gtk_label_set_text(GTK_LABEL(message),str(data,"message"));
        } else if(!strcmp(event,"art")) {
            if(!g_strcmp0(current_track,str(data,"path"))) {
                const char *file=str(data,"file");
                show_art(file);
            }
        } else if(!strcmp(event,"status")) {
            show_order(str(data,"order"));
            gtk_widget_set_visible(live_label,boolean(data,"playing")&&boolean(data,"live"));
            json_object *pos=NULL,*length=NULL;json_object_object_get_ex(data,"position",&pos);json_object_object_get_ex(data,"duration",&length);simple_song_progress_update(song_progress,pos?json_object_get_double(pos):-1,length?json_object_get_double(length):0,boolean(data,"playing")&&!boolean(data,"live"));
            if(g_strcmp0(current_track,str(data,"path"))) {
                g_free(current_track);current_track=g_strdup(str(data,"path"));
                gtk_picture_set_paintable(GTK_PICTURE(cover),NULL);
                gtk_stack_set_visible_child_name(GTK_STACK(cover_stack),"empty");
            }
            const char *date=str(data,"year"),*record=str(data,"album");
            char *record_line=g_strdup_printf("%s%s%s",date,*date&&*record?" · ":"",record);
            gtk_label_set_text(GTK_LABEL(album),record_line);gtk_widget_set_tooltip_text(album,record_line);g_free(record_line);
            gtk_label_set_text(GTK_LABEL(track),str(data,"title"));gtk_label_set_text(GTK_LABEL(artist),str(data,"artist"));
            gboolean paused=!boolean(data,"playing")||boolean(data,"paused");
            gtk_button_set_icon_name(GTK_BUTTON(pause_button),paused?"media-playback-start-symbolic":"media-playback-pause-symbolic");
            gtk_widget_set_tooltip_text(pause_button,paused?"Resume":"Pause");
        }
        json_object_put(data);
    }
    g_data_input_stream_read_line_async(reader,G_PRIORITY_DEFAULT,NULL,received,NULL);
}
static gboolean poll_status(gpointer unused) {(void)unused;send(request("status"));return G_SOURCE_CONTINUE;}
static void search_action(SimpleUISearchAction action,gpointer unused) {
    (void)unused;
    if(action==SIMPLE_UI_SEARCH_DOWN||action==SIMPLE_UI_SEARCH_UP)move_selection(action==SIMPLE_UI_SEARCH_DOWN?1:-1,TRUE);
    else if(action==SIMPLE_UI_SEARCH_ACTIVATE)play_selected(FALSE);
    else if(action==SIMPLE_UI_SEARCH_NAVIGATE)show_library(TRUE);
    else if(action==SIMPLE_UI_SEARCH_FOCUS)gtk_widget_set_visible(search,TRUE);
}
static gboolean keys(GtkEventControllerKey *controller,guint key,guint code,GdkModifierType state,gpointer unused) {
    (void)controller;(void)code;(void)unused;

    int control_result=simple_control_key(GTK_WINDOW(window),key,state);
    if(control_result>=0)return control_result;
    gboolean after_g=gprefix;gprefix=FALSE;
    if(key==GDK_KEY_g&&(state&GDK_SHIFT_MASK))key=GDK_KEY_G;
    GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(window));
    gboolean typing=focus&&(focus==search||gtk_widget_is_ancestor(focus,search));
    if((state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))==GDK_CONTROL_MASK&&(key==GDK_KEY_h||key==GDK_KEY_l)){choose_source(NULL,GUINT_TO_POINTER((source_index+(key==GDK_KEY_l?1:2))%3));return TRUE;}
    if((state&GDK_CONTROL_MASK)&&key==GDK_KEY_r){rescan(NULL,NULL);return TRUE;}
    if(key==GDK_KEY_Escape) {
        gtk_window_close(GTK_WINDOW(window));
        return TRUE;
    }
    if(gtk_widget_get_visible(browser)) {
        if((state&GDK_CONTROL_MASK)&&(key==GDK_KEY_j||key==GDK_KEY_k)){
            move_selection(key==GDK_KEY_j?1:-1,typing);return TRUE;
        }
        if(key==GDK_KEY_Return||key==GDK_KEY_KP_Enter){play_selected((state&GDK_SHIFT_MASK)!=0);return TRUE;}
    }
    if(typing)return FALSE;
    if(key>=GDK_KEY_1&&key<=GDK_KEY_3){choose_source(NULL,GUINT_TO_POINTER(key-GDK_KEY_1));return TRUE;}
    if(key==GDK_KEY_f&&source_index){favourite(NULL,NULL);return TRUE;}
    if(!(state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))) {
        if(after_g&&key==GDK_KEY_h){open_folder("");gtk_widget_grab_focus(list);return TRUE;}
        if(key==GDK_KEY_g){
            if(after_g){GtkListBoxRow *first=gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),0);if(first){gtk_list_box_select_row(GTK_LIST_BOX(list),first);gtk_widget_grab_focus(GTK_WIDGET(first));}}
            else gprefix=TRUE;
            return TRUE;
        }
    }
    if(key==GDK_KEY_slash){show_library(TRUE);gtk_widget_set_visible(search,TRUE);gtk_widget_grab_focus(search);return TRUE;}
    if(key==GDK_KEY_space){control(NULL,"pause");return TRUE;}
    if(key==GDK_KEY_n){control(NULL,"next");return TRUE;}
    if(key==GDK_KEY_p){control(NULL,"previous");return TRUE;}
    if(key==GDK_KEY_q&&!(state&(GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK))){gtk_window_close(GTK_WINDOW(window));return TRUE;}
    if(!gtk_widget_get_visible(browser))return FALSE;
    if(key==GDK_KEY_h||((state&GDK_ALT_MASK)&&key==GDK_KEY_Left)){back(NULL,NULL);return TRUE;}
    GtkListBoxRow *row=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));
    if(key==GDK_KEY_j||key==GDK_KEY_k||key==GDK_KEY_G){
        int index=row?gtk_list_box_row_get_index(row):-1;
        if(key==GDK_KEY_G){index=0;while(gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),index+1))index++;}
        else index=MAX(0,index+(key==GDK_KEY_j?1:-1));
        row=gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),index);
        if(row){gtk_list_box_select_row(GTK_LIST_BOX(list),row);gtk_widget_grab_focus(GTK_WIDGET(row));}return TRUE;
    }
    if(key==GDK_KEY_l){if(row&&!source_index)activated(GTK_LIST_BOX(list),row,NULL);return TRUE;}
    if(key==GDK_KEY_s){play(NULL,"shuffle");return TRUE;}
    if(key==GDK_KEY_o){play(NULL,"ordered");return TRUE;}
    return FALSE;
}
static void activate(GtkApplication *app,gpointer unused) {
    (void)unused;if(window){gtk_window_present(GTK_WINDOW(window));return;}
    window=gtk_application_window_new(app);simple_ui_window(GTK_WINDOW(window));gtk_window_set_title(GTK_WINDOW(window),"Simpleplayer");gtk_window_set_default_size(GTK_WINDOW(window),1280,730);
    gtk_widget_add_css_class(window,"simpleplayer");
    GtkCssProvider *provider=gtk_css_provider_new();char *css=g_build_filename(assets,"app.css",NULL);simple_theme_load(provider,css);g_free(css);
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(provider),GTK_STYLE_PROVIDER_PRIORITY_USER);g_object_unref(provider);
    GtkWidget *layout=gtk_box_new(GTK_ORIENTATION_VERTICAL,16);gtk_widget_add_css_class(layout,"player-layout");gtk_window_set_child(GTK_WINDOW(window),layout);
    GtkWidget *header=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,10),*titles=gtk_box_new(GTK_ORIENTATION_VERTICAL,3);
    gtk_widget_set_hexpand(titles,TRUE);
    heading=label("Simpleplayer","title");gtk_box_append(GTK_BOX(titles),heading);gtk_box_append(GTK_BOX(header),titles);
    refresh=icon_button("view-refresh-symbolic","Refresh library · Ctrl+R",G_CALLBACK(rescan),NULL);gtk_box_append(GTK_BOX(header),refresh);gtk_box_append(GTK_BOX(layout),header);
    GtkWidget *body=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,24);browser=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);
    gtk_widget_set_size_request(browser,320,-1);gtk_widget_add_css_class(browser,"library-card");gtk_widget_add_css_class(browser,"card");gtk_widget_set_valign(browser,GTK_ALIGN_FILL);
    gtk_widget_set_hexpand(browser,FALSE);gtk_widget_set_vexpand(body,TRUE);
    gtk_box_append(GTK_BOX(layout),body);
    GtkWidget *sources=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,4);const char *source_labels[]={"Local","Radio","YouTube"};
    gtk_widget_add_css_class(sources,"simple-tabs");
    for(guint i=0;i<3;i++){source_buttons[i]=gtk_toggle_button_new_with_label(source_labels[i]);if(i)gtk_toggle_button_set_group(GTK_TOGGLE_BUTTON(source_buttons[i]),GTK_TOGGLE_BUTTON(source_buttons[0]));gtk_widget_set_hexpand(source_buttons[i],TRUE);g_signal_connect(source_buttons[i],"toggled",G_CALLBACK(choose_source),GUINT_TO_POINTER(i));gtk_box_append(GTK_BOX(sources),source_buttons[i]);}
    gtk_toggle_button_set_active(GTK_TOGGLE_BUTTON(source_buttons[0]),TRUE);gtk_box_insert_child_after(GTK_BOX(layout),sources,header);
    search=gtk_search_entry_new();gtk_widget_set_visible(search,FALSE);g_object_set(search,"placeholder-text","Search artists, albums…",NULL);g_signal_connect(search,"changed",G_CALLBACK(searched),NULL);gtk_box_append(GTK_BOX(browser),search);
    GtkWidget *actions=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8);
    shuffle=gtk_button_new_with_label("Shuffle");gtk_widget_add_css_class(shuffle,"primary");g_signal_connect(shuffle,"clicked",G_CALLBACK(play),"shuffle");
    ordered=gtk_button_new_with_label("In order");g_signal_connect(ordered,"clicked",G_CALLBACK(play),"ordered");
    gtk_box_append(GTK_BOX(actions),shuffle);gtk_box_append(GTK_BOX(actions),ordered);stream_play=gtk_button_new_with_label("Play");g_signal_connect(stream_play,"clicked",G_CALLBACK(play),"ordered");gtk_box_append(GTK_BOX(actions),stream_play);gtk_widget_set_visible(stream_play,FALSE);favourite_button=gtk_button_new_with_label("Toggle favourite · f");g_signal_connect(favourite_button,"clicked",G_CALLBACK(favourite),NULL);gtk_box_append(GTK_BOX(actions),favourite_button);gtk_widget_set_visible(favourite_button,FALSE);gtk_box_append(GTK_BOX(browser),actions);
    GtkWidget *scroll=gtk_scrolled_window_new();gtk_widget_set_vexpand(scroll,TRUE);gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),GTK_POLICY_NEVER,GTK_POLICY_AUTOMATIC);
    list=gtk_list_box_new();gtk_list_box_set_activate_on_single_click(GTK_LIST_BOX(list),TRUE);g_signal_connect(list,"row-activated",G_CALLBACK(activated),NULL);gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll),list);gtk_box_append(GTK_BOX(browser),scroll);
    message=label("Enter shuffle · Shift+Enter ordered · Ctrl+J/K selects","message");gtk_box_append(GTK_BOX(browser),message);
    now=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,24);gtk_widget_add_css_class(now,"now-playing");gtk_widget_add_css_class(now,"card");
    gtk_widget_set_hexpand(now,TRUE);gtk_widget_set_valign(now,GTK_ALIGN_FILL);
    GtkWidget *details=gtk_box_new(GTK_ORIENTATION_VERTICAL,14);gtk_widget_set_hexpand(details,TRUE);gtk_widget_set_size_request(details,200,-1);gtk_widget_set_valign(details,GTK_ALIGN_FILL);gtk_widget_add_css_class(details,"track-details");
    GtkWidget *caption=label("NOW PLAYING","eyebrow");gtk_label_set_xalign(GTK_LABEL(caption),.5);gtk_box_append(GTK_BOX(details),caption);
    cover_stack=gtk_stack_new();gtk_widget_set_size_request(cover_stack,460,460);gtk_widget_add_css_class(cover_stack,"album-art");gtk_widget_set_hexpand(cover_stack,FALSE);
    cover=gtk_picture_new();gtk_picture_set_content_fit(GTK_PICTURE(cover),GTK_CONTENT_FIT_CONTAIN);gtk_picture_set_can_shrink(GTK_PICTURE(cover),TRUE);
    gtk_stack_add_named(GTK_STACK(cover_stack),cover,"cover");
    wallpaper=gtk_picture_new();gtk_picture_set_content_fit(GTK_PICTURE(wallpaper),GTK_CONTENT_FIT_COVER);gtk_picture_set_can_shrink(GTK_PICTURE(wallpaper),TRUE);
    gtk_stack_add_named(GTK_STACK(cover_stack),wallpaper,"empty");gtk_stack_set_visible_child_name(GTK_STACK(cover_stack),"empty");gtk_box_append(GTK_BOX(now),cover_stack);
    track=label("Ready when you are","track-title");artist=label("Choose music from your library","artist-name");
    album=label("","album-name");
    gtk_label_set_xalign(GTK_LABEL(artist),.5);gtk_label_set_xalign(GTK_LABEL(album),.5);gtk_label_set_xalign(GTK_LABEL(track),.5);
    GtkWidget *song_info=gtk_box_new(GTK_ORIENTATION_VERTICAL,12);gtk_widget_set_vexpand(song_info,TRUE);gtk_widget_set_valign(song_info,GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(song_info),artist);gtk_box_append(GTK_BOX(song_info),album);gtk_box_append(GTK_BOX(song_info),track);gtk_box_append(GTK_BOX(details),song_info);
    live_label=label("LIVE","eyebrow");gtk_label_set_xalign(GTK_LABEL(live_label),.5);gtk_widget_set_visible(live_label,FALSE);gtk_box_append(GTK_BOX(details),live_label);
    song_progress=simple_song_progress_new();gtk_box_append(GTK_BOX(details),song_progress);
    GtkWidget *controls=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8);gtk_widget_set_halign(controls,GTK_ALIGN_CENTER);
    gtk_box_append(GTK_BOX(controls),icon_button("media-skip-backward-symbolic","Previous track",G_CALLBACK(control),"previous"));
    pause_button=icon_button("media-playback-start-symbolic","Pause / resume",G_CALLBACK(control),"pause");gtk_widget_add_css_class(pause_button,"primary");gtk_box_append(GTK_BOX(controls),pause_button);
    gtk_box_append(GTK_BOX(controls),icon_button("media-skip-forward-symbolic","Next track",G_CALLBACK(control),"next"));
    gtk_box_append(GTK_BOX(controls),icon_button("media-playback-stop-symbolic","Stop",G_CALLBACK(control),"stop"));gtk_box_append(GTK_BOX(details),controls);gtk_box_append(GTK_BOX(now),details);gtk_box_append(GTK_BOX(body),now);gtk_box_append(GTK_BOX(body),browser);
    visualizer=gtk_drawing_area_new();gtk_widget_set_size_request(visualizer,-1,64);gtk_widget_add_css_class(visualizer,"visualizer");
    gtk_drawing_area_set_draw_func(GTK_DRAWING_AREA(visualizer),cava_draw,NULL,NULL);gtk_box_append(GTK_BOX(layout),visualizer);
    if(g_strcmp0(g_getenv("SIMPLEPLAYER_VISUALIZER"),"0")) cava_start();
    else gtk_widget_set_visible(visualizer,FALSE);
    gtk_box_append(GTK_BOX(layout),label("Ctrl+H/L source · 1/2/3 Local/Radio/YouTube · Ctrl+R rescan/refresh · / search · Space pause · gg/G first/last · gh home","message"));
    GtkEventController *key=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(key,GTK_PHASE_CAPTURE);g_signal_connect(key,"key-pressed",G_CALLBACK(keys),NULL);gtk_widget_add_controller(window,key);
    char *helper=g_build_filename(assets,"bridge.py",NULL);GError *error=NULL;
    bridge=g_subprocess_new(G_SUBPROCESS_FLAGS_STDIN_PIPE|G_SUBPROCESS_FLAGS_STDOUT_PIPE,&error,"python3",helper,NULL);g_free(helper);
    if(bridge) {
        reader=g_data_input_stream_new(g_subprocess_get_stdout_pipe(bridge));g_data_input_stream_read_line_async(reader,G_PRIORITY_DEFAULT,NULL,received,NULL);browse();poll_status(NULL);g_timeout_add_seconds(1,poll_status,NULL);
    } else {gtk_label_set_text(GTK_LABEL(message),error->message);g_clear_error(&error);}
    gtk_widget_set_visible(search,TRUE);
    simple_ui_bind_search(GTK_WINDOW(window),search,list,"simpleplayer",search_action,NULL);
    gtk_window_present(GTK_WINDOW(window));simple_ui_search_start(GTK_WINDOW(window),FALSE);
}
int main(int argc,char **argv) {
    if(argc>1&&!strcmp(argv[1],"--help")){g_print("Simpleplayer — music library and mpv controls. / search, Ctrl+R refresh, Ctrl+J/K selects, Ctrl+Enter navigation, Esc closes; h / Alt+Left goes back.\n");return 0;}
    const char *override=g_getenv("SIMPLEPLAYER_ASSETS");
    assets=override?g_strdup(override):g_build_filename(g_get_user_data_dir(),"simpleplayer",NULL);
    char *probe=g_build_filename(assets,"bridge.py",NULL);
    if(!override&&!g_file_test(probe,G_FILE_TEST_IS_REGULAR)) {
        g_free(assets);assets=g_build_filename(g_get_user_config_dir(),"simpleplayer",NULL);
    }
    g_free(probe);
    if(argc==2&&(!strcmp(argv[1],"--check-config")||!strcmp(argv[1],"--refresh-library"))) {
        char *script=g_build_filename(assets,"playback.sh",NULL);
        execlp("bash","bash",script,argv[1],NULL);g_printerr("Cannot start playback helper\n");return 1;
    }
    if(!g_getenv("SIMPLEPLAYER_VISUALIZER")) {
        char *script=g_build_filename(assets,"scripts","simpleplayer-config.py",NULL);
        if(!g_file_test(script,G_FILE_TEST_IS_REGULAR)) {
            g_free(script);script=g_build_filename(g_get_user_config_dir(),"simplepicker","music","scripts","simpleplayer-config.py",NULL);
        }
        char *args[]={"python3",script,"--visualizer",NULL},*value=NULL;int code=0;
        if(g_spawn_sync(NULL,args,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,&value,NULL,&code,NULL)&&code==0&&value) {
            g_strstrip(value);if(!strcmp(value,"0"))g_setenv("SIMPLEPLAYER_VISUALIZER","0",FALSE);
        }
        g_free(value);g_free(script);
    }
    GtkApplication *app=gtk_application_new("com.go7.Simpleplayer",G_APPLICATION_DEFAULT_FLAGS);g_signal_connect(app,"activate",G_CALLBACK(activate),NULL);
    int status=g_application_run(G_APPLICATION(app),argc,argv);
    cava_stop();
    if(bridge)g_subprocess_force_exit(bridge);
    g_object_unref(app);g_free(folder);g_free(assets);return status;
}
