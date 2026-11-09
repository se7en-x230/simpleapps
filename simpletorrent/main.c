#include "../simple-common/simple-keyboard.h"
#include <gtk/gtk.h>
#include <curl/curl.h>
#include <json-c/json.h>
#include "../simple-common/simple-theme.h"

typedef struct { int id; gint64 added; GtkWidget *row,*name,*info,*mark,*bar; gboolean marked, completion_armed; } Row;
static GtkWidget *win,*list,*search,*status_label;
static GPtrArray *rows;
static GKeyFile *keys;
static gboolean busy,closed;
static char *endpoint;
static char session[512];
static json_object *field(json_object *o,const char *k){json_object *v=NULL;json_object_object_get_ex(o,k,&v);return v;}
static const char *str(json_object *o,const char *k){const char *s=json_object_get_string(field(o,k));return s?s:"";}
static double num(json_object *o,const char *k){return json_object_get_double(field(o,k));}
static size_t body_cb(char *p,size_t a,size_t b,void *d){g_string_append_len(d,p,a*b);return a*b;}
static size_t header_cb(char *p,size_t a,size_t b,void *d){
    size_t n=a*b; const char *prefix="X-Transmission-Session-Id:";
    if(n>strlen(prefix)&&!g_ascii_strncasecmp(p,prefix,strlen(prefix))){
        char *v=g_strndup(p+strlen(prefix),n-strlen(prefix));g_strstrip(v);g_strlcpy(session,v,sizeof session);g_free(v);
    }return n;
}
/* Called only by one worker at a time. Never block GTK on RPC. */
static json_object *rpc(const char *payload,GError **error){
    for(int attempt=0;attempt<2;attempt++){
        CURL *c=curl_easy_init();GString *b=g_string_new(NULL);
        struct curl_slist *h=curl_slist_append(NULL,"Content-Type: application/json");
        char *sid=g_strdup_printf("X-Transmission-Session-Id: %s",session);h=curl_slist_append(h,sid);g_free(sid);
        curl_easy_setopt(c,CURLOPT_URL,endpoint);curl_easy_setopt(c,CURLOPT_NOPROXY,"*");
        curl_easy_setopt(c,CURLOPT_POSTFIELDS,payload);curl_easy_setopt(c,CURLOPT_HTTPHEADER,h);
        curl_easy_setopt(c,CURLOPT_WRITEFUNCTION,body_cb);curl_easy_setopt(c,CURLOPT_WRITEDATA,b);
        curl_easy_setopt(c,CURLOPT_HEADERFUNCTION,header_cb);curl_easy_setopt(c,CURLOPT_CONNECTTIMEOUT,2L);
        curl_easy_setopt(c,CURLOPT_TIMEOUT,8L);curl_easy_setopt(c,CURLOPT_NOSIGNAL,1L);
        CURLcode rc=curl_easy_perform(c);long code=0;curl_easy_getinfo(c,CURLINFO_RESPONSE_CODE,&code);
        curl_easy_cleanup(c);curl_slist_free_all(h);
        if(code==409&&attempt==0){g_string_free(b,TRUE);continue;}
        json_object *o=rc==CURLE_OK&&code==200?json_tokener_parse(b->str):NULL;g_string_free(b,TRUE);
        if(!o||strcmp(str(o,"result"),"success")){
            g_set_error(error,G_IO_ERROR,G_IO_ERROR_FAILED,"%s",o?str(o,"result"):code==401?"Transmission requires authentication.":"Cannot reach Transmission. Check that the daemon is running.");
            if(o)json_object_put(o);
            return NULL;
        }return o;
    }return NULL;
}
static const char *get_request="{\"method\":\"torrent-get\",\"arguments\":{\"fields\":[\"leftUntilDone\",\"metadataPercentComplete\",\"sizeWhenDone\",\"error\",\"addedDate\",\"id\",\"name\",\"status\",\"percentDone\",\"rateDownload\",\"rateUpload\",\"totalSize\",\"errorString\"]}}";
static void json_free(gpointer p){if(p)json_object_put(p);}
static void worker(GTask *task,gpointer source,gpointer data,GCancellable *cancel){
    GError *e=NULL;json_object *o=rpc(data,&e);
    if(o&&strcmp(data,get_request)){json_object_put(o);o=rpc(get_request,&e);}
    if(e)g_task_return_error(task,e);else g_task_return_pointer(task,o,json_free);
}
static void notice(const char *text){gtk_label_set_text(GTK_LABEL(status_label),text);}
static Row *current(void){GtkListBoxRow *r=gtk_list_box_get_selected_row(GTK_LIST_BOX(list));return r?g_object_get_data(G_OBJECT(r),"row"):NULL;}
static void row_mark(Row *r){gtk_label_set_text(GTK_LABEL(r->mark),r->marked?"●":"○");}
static gboolean filter(GtkListBoxRow *r,gpointer data){
    Row *item=g_object_get_data(G_OBJECT(r),"row");if(!item)return TRUE;
    char *a=g_utf8_casefold(gtk_label_get_text(GTK_LABEL(item->name)),-1),*b=g_utf8_casefold(gtk_editable_get_text(GTK_EDITABLE(search)),-1);
    gboolean visible=strstr(a,b)!=NULL;g_free(a);g_free(b);return visible;
}
static void changed(GtkEditable *e,gpointer d){gtk_list_box_invalidate_filter(GTK_LIST_BOX(list));}
static GtkWidget *label(const char *text,const char *css){GtkWidget *w=gtk_label_new(text);gtk_label_set_xalign(GTK_LABEL(w),0);if(css)gtk_widget_add_css_class(w,css);return w;}
static Row *lookup(int id){for(guint i=0;i<rows->len;i++){Row *r=g_ptr_array_index(rows,i);if(r->id==id)return r;}return NULL;}
static gint newest_first(GtkListBoxRow *a,GtkListBoxRow *b,gpointer unused){
    Row *x=g_object_get_data(G_OBJECT(a),"row"),*y=g_object_get_data(G_OBJECT(b),"row");
    if(x->added!=y->added)return x->added>y->added?-1:1;
    return (x->id<y->id)-(x->id>y->id);
}
/* Completion concerns selected download files, not the seeding ratio goal. */
static gboolean download_complete(json_object *t){
    int state=num(t,"status");
    return field(t,"leftUntilDone") && num(t,"metadataPercentComplete")>=1 &&
        num(t,"sizeWhenDone")>0 && json_object_get_int64(field(t,"leftUntilDone"))==0 &&
        num(t,"percentDone")>=1 && state!=1 && state!=2 && num(t,"error")!=3;
}
static gboolean completion_transition(Row *r,json_object *t){
    int state=num(t,"status");
    if(num(t,"metadataPercentComplete")>=1 && num(t,"leftUntilDone")>0 && state!=1 && state!=2)
        r->completion_armed=TRUE;
    if(download_complete(t)&&r->completion_armed){r->completion_armed=FALSE;return TRUE;}
    return FALSE;
}
static void notification_done(GObject *source,GAsyncResult *result,gpointer unused){
    GError *e=NULL;GVariant *reply=g_dbus_connection_call_finish(G_DBUS_CONNECTION(source),result,&e);
    if(reply)g_variant_unref(reply);
    if(e){g_warning("Completion notification: %s",e->message);g_error_free(e);}
}
static void notification_bus(GObject *source,GAsyncResult *result,gpointer data){
    char *name=data;GError *e=NULL;GDBusConnection *bus=g_bus_get_finish(result,&e);
    if(bus){
        GVariantBuilder actions,hints;g_variant_builder_init(&actions,G_VARIANT_TYPE("as"));g_variant_builder_init(&hints,G_VARIANT_TYPE("a{sv}"));
        char *escaped=g_markup_escape_text(name,-1);
        g_dbus_connection_call(bus,"org.freedesktop.Notifications","/org/freedesktop/Notifications","org.freedesktop.Notifications","Notify",
            g_variant_new("(susssasa{sv}i)","SimpleTorrent",0u,"folder-download","Download complete",escaped,&actions,&hints,-1),
            G_VARIANT_TYPE("(u)"),G_DBUS_CALL_FLAGS_NONE,5000,NULL,notification_done,NULL);
        g_free(escaped);g_object_unref(bus);
    }else{g_warning("Completion notification: %s",e->message);g_clear_error(&e);}
    g_free(name);
}
static void notify_complete(const char *name){
    /* The daemon hook also works with this window closed; avoid duplicate toasts. */
    char *path=g_build_filename(g_get_user_config_dir(),"transmission-daemon","settings.json",NULL);
    json_object *settings=json_object_from_file(path);g_free(path);
    gboolean daemon_notifies=FALSE;
    if(settings){
        const char *hook=str(settings,"script-torrent-done-filename");
        char *base=g_path_get_basename(hook);
        daemon_notifies=json_object_get_boolean(field(settings,"script-torrent-done-enabled")) &&
            !strcmp(base,"transmission-notify-finished") && g_file_test(hook,G_FILE_TEST_IS_EXECUTABLE);
        g_free(base);json_object_put(settings);
    }
    if(!daemon_notifies)g_bus_get(G_BUS_TYPE_SESSION,NULL,notification_bus,g_strdup(name));
}
static void render(json_object *o){
    json_object *ts=field(field(o,"arguments"),"torrents");if(!ts||!json_object_is_type(ts,json_type_array))return;
    GHashTable *seen=g_hash_table_new(g_direct_hash,g_direct_equal);int active=0;double dl=0,ul=0;
    for(size_t i=0;i<json_object_array_length(ts);i++){
        json_object *t=json_object_array_get_idx(ts,i);int id=num(t,"id"),state=num(t,"status");
        g_hash_table_add(seen,GINT_TO_POINTER(id));Row *r=lookup(id);
        if(!r){
            r=g_new0(Row,1);r->id=id;r->added=json_object_get_int64(field(t,"addedDate"));r->row=gtk_list_box_row_new();g_object_set_data(G_OBJECT(r->row),"row",r);
            GtkWidget *h=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,12),*v=gtk_box_new(GTK_ORIENTATION_VERTICAL,5);
            r->mark=label("○",NULL);r->name=label("",NULL);r->info=label("","muted");r->bar=gtk_progress_bar_new();
            gtk_label_set_ellipsize(GTK_LABEL(r->name),PANGO_ELLIPSIZE_END);gtk_label_set_ellipsize(GTK_LABEL(r->info),PANGO_ELLIPSIZE_END);
            gtk_widget_set_hexpand(v,TRUE);gtk_box_append(GTK_BOX(v),r->name);gtk_box_append(GTK_BOX(v),r->info);gtk_box_append(GTK_BOX(v),r->bar);
            gtk_box_append(GTK_BOX(h),r->mark);gtk_box_append(GTK_BOX(h),v);gtk_list_box_row_set_child(GTK_LIST_BOX_ROW(r->row),h);
            g_ptr_array_add(rows,r);gtk_list_box_append(GTK_LIST_BOX(list),r->row);
        }
        r->added=json_object_get_int64(field(t,"addedDate"));
        gboolean complete=download_complete(t);
        if(completion_transition(r,t))notify_complete(str(t,"name"));
        double pct=complete?1:MIN(CLAMP(num(t,"percentDone"),0,1),.999);const char *states[]={"Paused","Queued check","Checking","Queued download","Downloading","Queued seed","Seeding"};
        const char *s=state>=0&&state<=6?states[state]:"Unknown";
        if(state==0&&complete)s="Finished · paused";
        if(num(t,"metadataPercentComplete")<1)s="Fetching metadata";
        if(complete&&num(t,"sizeWhenDone")<num(t,"totalSize"))s="Selected files finished";
        char *size=g_format_size(num(t,"sizeWhenDone")),*down=g_format_size(num(t,"rateDownload")),*up=g_format_size(num(t,"rateUpload"));
        char *info=g_strdup_printf("%s   ·   %.1f%%   ·   %s   ·   ↓ %s/s   ↑ %s/s%s%s",s,pct*100,size,down,up,*str(t,"errorString")?"   ·   ":"",str(t,"errorString"));
        gtk_label_set_text(GTK_LABEL(r->name),str(t,"name"));gtk_label_set_text(GTK_LABEL(r->info),info);gtk_widget_set_tooltip_text(r->row,info);
        gtk_progress_bar_set_fraction(GTK_PROGRESS_BAR(r->bar),CLAMP(pct,0,1));
        if(state==4||state==6)gtk_widget_add_css_class(r->row,"running");else gtk_widget_remove_css_class(r->row,"running");
        if(complete)gtk_widget_add_css_class(r->bar,"complete");else gtk_widget_remove_css_class(r->bar,"complete");
        active+=state==4||state==6;dl+=num(t,"rateDownload");ul+=num(t,"rateUpload");g_free(size);g_free(down);g_free(up);g_free(info);
    }
    for(gint i=(gint)rows->len-1;i>=0;i--){Row *r=g_ptr_array_index(rows,i);if(!g_hash_table_contains(seen,GINT_TO_POINTER(r->id))){gtk_list_box_remove(GTK_LIST_BOX(list),r->row);g_ptr_array_remove_index(rows,i);}}
    g_hash_table_destroy(seen);gtk_list_box_invalidate_sort(GTK_LIST_BOX(list));gtk_list_box_invalidate_filter(GTK_LIST_BOX(list));
    if(!current()&&rows->len)gtk_list_box_select_row(GTK_LIST_BOX(list),gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),0));
    char *d=g_format_size(dl),*u=g_format_size(ul),*msg=g_strdup_printf("%u torrents · %d running    ↓ %s/s    ↑ %s/s",rows->len,active,d,u);notice(msg);g_free(d);g_free(u);g_free(msg);
}
static void done(GObject *source,GAsyncResult *result,gpointer data){GError *e=NULL;json_object *o=g_task_propagate_pointer(G_TASK(result),&e);busy=FALSE;if(!closed){if(e)notice(e->message);else if(o)render(o);}g_clear_error(&e);if(o)json_object_put(o);}
static void request(const char *payload){if(busy){notice("Updating — try again in a moment.");return;}busy=TRUE;GTask *t=g_task_new(NULL,NULL,done,NULL);g_task_set_task_data(t,g_strdup(payload),g_free);g_task_run_in_thread(t,worker);g_object_unref(t);}
static gboolean poll(gpointer d){if(closed)return G_SOURCE_REMOVE;if(!busy)request(get_request);return G_SOURCE_CONTINUE;}
static json_object *targets(void){json_object *ids=json_object_new_array();for(guint i=0;i<rows->len;i++){Row *r=g_ptr_array_index(rows,i);if(r->marked)json_object_array_add(ids,json_object_new_int(r->id));}if(!json_object_array_length(ids)&&current())json_object_array_add(ids,json_object_new_int(current()->id));return ids;}
static char *command(const char *method,json_object *args){json_object *o=json_object_new_object();json_object_object_add(o,"method",json_object_new_string(method));json_object_object_add(o,"arguments",args);char *p=g_strdup(json_object_to_json_string(o));json_object_put(o);return p;}
static void remove_answer(GObject *source,GAsyncResult *result,gpointer data){GError *e=NULL;int n=gtk_alert_dialog_choose_finish(GTK_ALERT_DIALOG(source),result,&e);if(!e&&n==1&&!closed)request(data);g_clear_error(&e);g_free(data);}
static char *remove_command(json_object *ids,gboolean delete_files){
    json_object *args=json_object_new_object();json_object_object_add(args,"ids",ids);
    json_object_object_add(args,"delete-local-data",json_object_new_boolean(delete_files));
    return command("torrent-remove",args);
}
static void action(GtkButton *b,gpointer method){
    if(busy){notice("Updating — try again in a moment.");return;}
    json_object *ids=targets();size_t count=json_object_array_length(ids);if(!count){json_object_put(ids);return;}
    gboolean deleting=!strcmp(method,"delete-files");
    if(deleting||!strcmp(method,"torrent-remove")){
        char *p=remove_command(ids,deleting);
        GtkAlertDialog *d=gtk_alert_dialog_new(deleting?"Delete %zu torrent%s and their files?":"Remove %zu torrent%s?",count,count==1?"":"s");
        gtk_alert_dialog_set_detail(d,deleting?"Downloaded files will be deleted from your drive. This cannot be undone here.":"Downloaded files will be kept. This stops sharing these torrents.");
        const char *buttons[]={"Cancel",deleting?"Delete files":"Remove torrent",NULL};
        gtk_alert_dialog_set_buttons(d,buttons);gtk_alert_dialog_set_cancel_button(d,0);gtk_alert_dialog_set_default_button(d,0);gtk_alert_dialog_choose(d,GTK_WINDOW(win),NULL,remove_answer,p);g_object_unref(d);
    }else{
        json_object *args=json_object_new_object();json_object_object_add(args,"ids",ids);
        char *p=command(method,args);request(p);g_free(p);
    }
}
static void add_value(const char *value){
    if(!*value)return;
    json_object *a=json_object_new_object();
    if(g_str_has_prefix(value,"magnet:")||g_str_has_prefix(value,"https://")||g_str_has_prefix(value,"http://"))json_object_object_add(a,"filename",json_object_new_string(value));
    else{
        char *path=g_str_has_prefix(value,"file://")?g_filename_from_uri(value,NULL,NULL):g_strdup(value),*bytes=NULL;gsize n=0;GError *e=NULL;
        if(!path||!g_file_get_contents(path,&bytes,&n,&e)){notice(e?e->message:"Invalid path");g_clear_error(&e);g_free(path);json_object_put(a);return;}
        g_free(path);if(n>16*1024*1024){notice("Torrent metadata is too large (maximum 16 MB).");g_free(bytes);json_object_put(a);return;}
        char *base=g_base64_encode((guchar*)bytes,n);g_free(bytes);json_object_object_add(a,"metainfo",json_object_new_string(base));g_free(base);
    }
    char *p=command("torrent-add",a);request(p);g_free(p);
}
static void add_response(GtkDialog *d,int response,gpointer entry){if(response==GTK_RESPONSE_ACCEPT)add_value(gtk_editable_get_text(GTK_EDITABLE(entry)));gtk_window_destroy(GTK_WINDOW(d));}
static void add_enter(GtkEntry *e,gpointer d){gtk_dialog_response(GTK_DIALOG(d),GTK_RESPONSE_ACCEPT);}
static void add_dialog(GtkButton *b,gpointer unused){
    GtkWidget *d=gtk_dialog_new_with_buttons("Add torrent",GTK_WINDOW(win),GTK_DIALOG_MODAL,"Cancel",GTK_RESPONSE_CANCEL,"Add",GTK_RESPONSE_ACCEPT,NULL);
    gtk_widget_add_css_class(d,"simpletorrent");GtkWidget *e=gtk_entry_new();gtk_entry_set_placeholder_text(GTK_ENTRY(e),"Magnet link, torrent URL or .torrent file path");gtk_widget_set_size_request(e,480,-1);
    gtk_box_append(GTK_BOX(gtk_dialog_get_content_area(GTK_DIALOG(d))),e);g_signal_connect(d,"response",G_CALLBACK(add_response),e);g_signal_connect(e,"activate",G_CALLBACK(add_enter),d);gtk_window_present(GTK_WINDOW(d));gtk_widget_grab_focus(e);
}
static void file_chosen(GObject *source,GAsyncResult *result,gpointer d){GError *e=NULL;GFile *file=gtk_file_dialog_open_finish(GTK_FILE_DIALOG(source),result,&e);if(file){char *path=g_file_get_path(file);if(path&&!closed)add_value(path);g_free(path);g_object_unref(file);}g_clear_error(&e);}
static void browse(GtkButton *b,gpointer d){GtkFileDialog *f=gtk_file_dialog_new();gtk_file_dialog_set_title(f,"Add .torrent file");gtk_file_dialog_open(f,GTK_WINDOW(win),NULL,file_chosen,NULL);g_object_unref(f);}
static void move(int delta){Row *r=current();int i=r?gtk_list_box_row_get_index(GTK_LIST_BOX_ROW(r->row)):(delta>0?-1:(int)rows->len);for(i+=delta;i>=0&&i<(int)rows->len;i+=delta){GtkListBoxRow *next=gtk_list_box_get_row_at_index(GTK_LIST_BOX(list),i);if(gtk_widget_get_child_visible(GTK_WIDGET(next))){gtk_list_box_select_row(GTK_LIST_BOX(list),next);gtk_widget_grab_focus(GTK_WIDGET(next));break;}}}
static gboolean matches(guint key,GdkModifierType mods,const char *group,const char *name,const char *fallback){char *value=g_key_file_get_string(keys,group,name,NULL);char **parts=g_strsplit(value?value:fallback,",",-1);gboolean found=FALSE;for(int i=0;parts[i];i++){guint k;GdkModifierType m;if(gtk_accelerator_parse(g_strstrip(parts[i]),&k,&m)&&gdk_keyval_to_lower(key)==k&&(mods&gtk_accelerator_get_default_mod_mask())==m)found=TRUE;}g_strfreev(parts);g_free(value);return found;}
static gboolean keypress(GtkEventControllerKey *c,guint key,guint code,GdkModifierType mods,gpointer d){

    int control_result=simple_control_key(GTK_WINDOW(win),key,mods);
    if(control_result>=0)return control_result;
    GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(win));
    if(focus&&(GTK_IS_EDITABLE(focus)||GTK_IS_TEXT(focus))){if(key==GDK_KEY_Escape){gtk_editable_set_text(GTK_EDITABLE(search),"");gtk_widget_set_visible(search,FALSE);if(current())gtk_widget_grab_focus(current()->row);else gtk_widget_grab_focus(list);return TRUE;}return FALSE;}
    if(matches(key,mods,"navigation","down","j,Down"))move(1);
    else if(matches(key,mods,"navigation","up","k,Up"))move(-1);
    else if(key==GDK_KEY_g){gtk_list_box_unselect_all(GTK_LIST_BOX(list));move(1);}
    else if(key==GDK_KEY_G){gtk_list_box_unselect_all(GTK_LIST_BOX(list));move(-1);}
    else if(matches(key,mods,"torrent","select","space")){Row *r=current();if(r){r->marked=!r->marked;row_mark(r);move(1);}}
    else if(matches(key,mods,"torrent","clear_selection","u")){for(guint i=0;i<rows->len;i++){Row *r=g_ptr_array_index(rows,i);r->marked=FALSE;row_mark(r);}}
    else if(matches(key,mods,"torrent","add","a"))add_dialog(NULL,NULL);
    else if(matches(key,mods,"torrent","delete","x"))action(NULL,"delete-files");
    else if(matches(key,mods,"torrent","remove","<Shift>x"))action(NULL,"torrent-remove");
    else if(matches(key,mods,"torrent","pause","p"))action(NULL,"torrent-stop");
    else if(matches(key,mods,"torrent","resume","s"))action(NULL,"torrent-start");
    else if(key==GDK_KEY_slash){gtk_widget_set_visible(search,TRUE);gtk_widget_grab_focus(search);}
    else if(key==GDK_KEY_q||matches(key,mods,"navigation","cancel","Escape"))gtk_window_close(GTK_WINDOW(win));
    else return FALSE;
    return TRUE;
}
static gboolean closing(GtkWindow *w,gpointer d){closed=TRUE;return FALSE;}
static void activated(GtkListBox *l,GtkListBoxRow *row,gpointer d){Row *r=g_object_get_data(G_OBJECT(row),"row");r->marked=!r->marked;row_mark(r);}
static void button(GtkWidget *box,const char *text,GCallback cb,gpointer arg){GtkWidget *b=gtk_button_new_with_label(text);gtk_box_append(GTK_BOX(box),b);g_signal_connect(b,"clicked",cb,arg);}
static void activate(GtkApplication *app,gpointer data){
    if(win){gtk_window_present(GTK_WINDOW(win));return;}
    win=gtk_application_window_new(app);gtk_widget_add_css_class(win,"simpletorrent");gtk_window_set_title(GTK_WINDOW(win),"SimpleTorrent");gtk_window_set_default_size(GTK_WINDOW(win),900,530);
    GtkCssProvider *p=gtk_css_provider_new();simple_theme_load(p,NULL);gtk_css_provider_load_from_string(p,
        "window.simpletorrent {background:@simple_bg;color:@simple_fg;} .simpletorrent label {color:@simple_fg;}"
        ".simpletorrent .heading {color:@simple_panel_accent;font-weight:bold;font-size:1.2em;} .simpletorrent .muted {color:mix(@simple_fg,@simple_muted,.35);font-size:.9em;}"
        ".simpletorrent button,.simpletorrent entry {background:@simple_button;color:@simple_fg;border:1px solid @simple_border;border-radius:8px;padding:7px;}"
        ".simpletorrent button:hover {background:@simple_hover;} .simpletorrent list {background:@simple_bg;} .simpletorrent row {padding:10px;border-bottom:1px solid @simple_border;}"
        ".simpletorrent row:nth-child(even) {background:@simple_surface;} .simpletorrent row:selected {background:@simple_accent;} .simpletorrent row:selected label {color:@simple_on_accent;}"
        ".simpletorrent progressbar trough {background:@simple_button;background-image:none;border:0;box-shadow:none;margin:0;padding:0;min-width:0;min-height:3px;} .simpletorrent progressbar progress {background:@simple_calendar_moon;background-image:none;border:0;box-shadow:none;margin:0;padding:0;min-width:0;min-height:3px;}"
        ".simpletorrent progressbar.complete progress {background:@simple_muted;} .simpletorrent .running progressbar progress {background:@simple_calendar_moon;}");
    gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(p),GTK_STYLE_PROVIDER_PRIORITY_USER);g_object_unref(p);
    char *css=g_build_filename(g_get_user_config_dir(),"simpletorrent","style.css",NULL);if(g_file_test(css,G_FILE_TEST_EXISTS)){p=gtk_css_provider_new();gtk_css_provider_load_from_path(p,css);gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(p),GTK_STYLE_PROVIDER_PRIORITY_USER+1);g_object_unref(p);}g_free(css);
    GtkWidget *root=gtk_box_new(GTK_ORIENTATION_VERTICAL,12),*top=gtk_box_new(GTK_ORIENTATION_HORIZONTAL,8);gtk_widget_set_margin_start(root,16);gtk_widget_set_margin_end(root,16);gtk_widget_set_margin_top(root,16);gtk_widget_set_margin_bottom(root,12);gtk_window_set_child(GTK_WINDOW(win),root);
    GtkWidget *title=label("SimpleTorrent","heading");gtk_widget_set_hexpand(title,TRUE);gtk_box_append(GTK_BOX(top),title);
    button(top,"+ Add · a",G_CALLBACK(add_dialog),NULL);button(top,"File…",G_CALLBACK(browse),NULL);button(top,"Start · s",G_CALLBACK(action),"torrent-start");button(top,"Pause · p",G_CALLBACK(action),"torrent-stop");button(top,"Delete · x",G_CALLBACK(action),"delete-files");gtk_box_append(GTK_BOX(root),top);
    search=gtk_search_entry_new();gtk_widget_set_visible(search,FALSE);gtk_widget_set_tooltip_text(search,"Search torrents · /");gtk_box_append(GTK_BOX(root),search);g_signal_connect(search,"changed",G_CALLBACK(changed),NULL);
    status_label=label("Connecting to Transmission…","muted");gtk_box_append(GTK_BOX(root),status_label);
    list=gtk_list_box_new();gtk_list_box_set_selection_mode(GTK_LIST_BOX(list),GTK_SELECTION_SINGLE);gtk_list_box_set_filter_func(GTK_LIST_BOX(list),filter,NULL,NULL);gtk_list_box_set_sort_func(GTK_LIST_BOX(list),newest_first,NULL,NULL);g_signal_connect(list,"row-activated",G_CALLBACK(activated),NULL);
    GtkWidget *scroll=gtk_scrolled_window_new();gtk_widget_set_vexpand(scroll,TRUE);gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(scroll),GTK_POLICY_NEVER,GTK_POLICY_AUTOMATIC);gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(scroll),list);gtk_box_append(GTK_BOX(root),scroll);
    gtk_box_append(GTK_BOX(root),label("j/k move · Space mark · u unmark all · a add · s start · p pause · x delete files · X remove only · / search · q close","muted"));
    GtkEventController *controller=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(controller,GTK_PHASE_CAPTURE);g_signal_connect(controller,"key-pressed",G_CALLBACK(keypress),NULL);gtk_widget_add_controller(win,controller);g_signal_connect(win,"close-request",G_CALLBACK(closing),NULL);
    gtk_window_present(GTK_WINDOW(win));gtk_widget_grab_focus(list);request(get_request);g_timeout_add_seconds(3,poll,NULL);
}
int main(int argc,char **argv){
    if(argc>1&&!strcmp(argv[1],"--help")){g_print("SimpleTorrent — Transmission frontend\nConfiguration: ~/.config/simpletorrent/{config.ini,keys.ini,style.css}\n");return 0;}
    curl_global_init(CURL_GLOBAL_DEFAULT);rows=g_ptr_array_new_with_free_func(g_free);keys=g_key_file_new();
    const char *dirs[]={"simple","simpletorrent"};for(int i=0;i<2;i++){char *path=g_build_filename(g_get_user_config_dir(),dirs[i],"keys.ini",NULL);GKeyFile *k=g_key_file_new();if(g_key_file_load_from_file(k,path,G_KEY_FILE_NONE,NULL)){gsize ng;char **groups=g_key_file_get_groups(k,&ng);for(gsize j=0;j<ng;j++){gsize nk;char **names=g_key_file_get_keys(k,groups[j],&nk,NULL);for(gsize n=0;n<nk;n++){char *v=g_key_file_get_value(k,groups[j],names[n],NULL);g_key_file_set_value(keys,groups[j],names[n],v);g_free(v);}g_strfreev(names);}g_strfreev(groups);}g_key_file_unref(k);g_free(path);}
    int port=9091;char *path=g_build_filename(g_get_user_config_dir(),"transmission-daemon","settings.json",NULL);json_object *settings=json_object_from_file(path);g_free(path);char *rpc_path=g_strdup(settings&&*str(settings,"rpc-url")?str(settings,"rpc-url"):"/transmission/");if(settings&&num(settings,"rpc-port")>0)port=num(settings,"rpc-port");if(settings)json_object_put(settings);
    endpoint=g_strdup_printf("http://127.0.0.1:%d%srpc",port,rpc_path);g_free(rpc_path);
    GKeyFile *cfg=g_key_file_new();path=g_build_filename(g_get_user_config_dir(),"simpletorrent","config.ini",NULL);if(g_key_file_load_from_file(cfg,path,G_KEY_FILE_NONE,NULL)){char *url=g_key_file_get_string(cfg,"transmission","url",NULL);if(url&&*url){g_free(endpoint);endpoint=url;}else g_free(url);}g_free(path);g_key_file_unref(cfg);
    GtkApplication *app=gtk_application_new("com.go7.SimpleTorrent",G_APPLICATION_DEFAULT_FLAGS);g_signal_connect(app,"activate",G_CALLBACK(activate),NULL);int result=g_application_run(G_APPLICATION(app),argc,argv);closed=TRUE;g_object_unref(app);return result;
}
