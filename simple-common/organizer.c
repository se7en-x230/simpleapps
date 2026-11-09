#include "simple-keyboard.h"
#include "simple-paths.h"
/* Native GTK organizers. Python helper owns provider authentication and data sync. */
#include <gtk/gtk.h>
#include <json-c/json.h>
#include <string.h>
#include <stdlib.h>
#include <stdio.h>
#include "simple-theme.h"
#include "daylight-art.h"
#ifndef CONTACTS
#define CONTACTS 0
#endif
#define APPNAME (CONTACTS?"simplecontacts":"simplecalendar")
#define TITLE (CONTACTS?"SimpleContacts":"SimpleCalendar")
#define CLASS (CONTACTS?"simple-contacts-app":"simple-calendar-app")
static gboolean show_report;
typedef struct {
 GtkApplication *app; GtkWindow *win; GtkWidget *status,*search,*list,*detail,*calendar,*events,*heading,*empty_caption,*local,*mode;
 GtkSingleSelection *selection; GtkStringList *strings; GtkSizeGroup *card_size,*legend_size,*action_size;
 GtkWidget *image_card,*legend_space,*breath_card,*report_button,*report_legend;
 SimpleDaylightArt empty_art;
 GKeyFile *config,*global_keys,*keys; char *dir,*helper,*python,*day,*filter,*contact_stamp,*view_stamp;
 json_object *data,*current; GPtrArray *cards; guint event_index; gboolean busy,reload,initial,changing,connected;
 GtkWindow *editor; GtkWidget *editor_error;
} App;
static App a;
static GtkCssProvider *app_css,*override_css;
static void load_styles(void);
static json_object *get(json_object *o,const char *k){json_object *v=NULL;if(o)json_object_object_get_ex(o,k,&v);return v;}
static const char *str(json_object *o,const char *k){json_object *v=get(o,k);return v?json_object_get_string(v):"";}
static gboolean boolean(json_object *o,const char *k){return json_object_get_boolean(get(o,k));}
static void putstr(json_object *o,const char *k,const char *v){json_object_object_add(o,k,json_object_new_string(v?v:""));}
static void putbool(json_object *o,const char *k,gboolean b){json_object_object_add(o,k,json_object_new_boolean(b));}
static void drop_json(gpointer p){json_object_put(p);}
static void own(json_object **dst,json_object *src){if(src)json_object_get(src);if(*dst)json_object_put(*dst);*dst=src;}
static GtkWidget *box(gboolean vertical,int spacing){return gtk_box_new(vertical?GTK_ORIENTATION_VERTICAL:GTK_ORIENTATION_HORIZONTAL,spacing);}
static void append(GtkWidget *b,GtkWidget *w){gtk_box_append(GTK_BOX(b),w);}
static void margin(GtkWidget *w,int n){gtk_widget_set_margin_start(w,n);gtk_widget_set_margin_end(w,n);gtk_widget_set_margin_top(w,n);gtk_widget_set_margin_bottom(w,n);}
static GtkWidget *label(const char *s,const char *css){GtkWidget *w=gtk_label_new(s);gtk_label_set_xalign(GTK_LABEL(w),0);gtk_label_set_wrap(GTK_LABEL(w),TRUE);gtk_label_set_max_width_chars(GTK_LABEL(w),55);if(css)gtk_widget_add_css_class(w,css);return w;}
static GtkWidget *button(const char *text,GCallback cb,gpointer data){GtkWidget *w=gtk_button_new_with_label(text);if(cb)g_signal_connect(w,"clicked",cb,data);return w;}
static void clear(GtkWidget *b){GtkWidget *w;while((w=gtk_widget_get_first_child(b)))gtk_box_remove(GTK_BOX(b),w);}
static GtkWidget *scroll(GtkWidget *child){GtkWidget *w=gtk_scrolled_window_new();gtk_scrolled_window_set_policy(GTK_SCROLLED_WINDOW(w),GTK_POLICY_NEVER,GTK_POLICY_AUTOMATIC);gtk_scrolled_window_set_child(GTK_SCROLLED_WINDOW(w),child);gtk_widget_set_vexpand(w,TRUE);return w;}
static int number(const char *key,int fallback,int low,int high){GError *e=NULL;int n=g_key_file_get_integer(a.config,CONTACTS?"contacts":"calendar",key,&e);if(e){g_clear_error(&e);n=fallback;}return CLAMP(n,low,high);}
static char *path(const char *base,const char *name){return g_build_filename(base,name,NULL);}
static char *today(void){GDateTime *d=g_date_time_new_now_local();char *s=g_date_time_format(d,"%F");g_date_time_unref(d);return s;}
static GDateTime *parseday(const char *s){int y,m,d;char tail;if(sscanf(s,"%d-%d-%d%c",&y,&m,&d,&tail)!=3)return NULL;return g_date_time_new_local(y,m,d,12,0,0);}
static gboolean match(const char *group,const char *key,const char *fallback,guint keyval,GdkModifierType state){
 char *binding=NULL;if(g_key_file_has_key(a.keys,group,key,NULL))binding=g_key_file_get_string(a.keys,group,key,NULL);else if(g_key_file_has_key(a.global_keys,group,key,NULL))binding=g_key_file_get_string(a.global_keys,group,key,NULL);else binding=g_strdup(fallback);
 char **parts=g_strsplit(binding?binding:"",",",-1);gboolean hit=FALSE;
 for(int i=0;parts[i];i++){guint v=0;GdkModifierType mods=0;char *s=g_strstrip(parts[i]);if(!*s||!gtk_accelerator_parse(s,&v,&mods))continue;
  GdkModifierType actual=state&gtk_accelerator_get_default_mod_mask();if(gdk_keyval_to_lower(v)!=v)mods|=GDK_SHIFT_MASK;if(gdk_keyval_to_lower(keyval)!=keyval)actual|=GDK_SHIFT_MASK;
  if(gdk_keyval_to_lower(v)==gdk_keyval_to_lower(keyval)&&actual==mods){hit=TRUE;break;}}
 g_strfreev(parts);g_free(binding);return hit;
}
static void reload_view(void);static void render(json_object *data);static void show_accounts(GtkWidget *,gpointer);static void edit_contact(GtkWidget *,gpointer);static void edit_event(GtkWidget *,gpointer);static void remove_selected(GtkWidget *,gpointer);static void export_contacts(GtkWidget *,gpointer);static void show_details(GtkWidget *,gpointer);
static void close_window(GtkWidget *unused,gpointer w){(void)unused;if(a.editor==w){a.editor=NULL;a.editor_error=NULL;}gtk_window_destroy(GTK_WINDOW(w));}
static gboolean escape_dialog(GtkEventControllerKey *c,guint key,guint code,GdkModifierType state,gpointer w){(void)c;(void)code;if(key==GDK_KEY_Escape){gtk_window_close(GTK_WINDOW(w));return TRUE;}
 if((state&GDK_CONTROL_MASK)&&(key==GDK_KEY_j||key==GDK_KEY_k)){gtk_widget_child_focus(GTK_WIDGET(w),key==GDK_KEY_j?GTK_DIR_TAB_FORWARD:GTK_DIR_TAB_BACKWARD);return TRUE;}
 GtkWidget *focus=gtk_window_get_focus(GTK_WINDOW(w));if((key==GDK_KEY_Return||key==GDK_KEY_KP_Enter)&&GTK_IS_BUTTON(focus)){gtk_widget_activate(focus);return TRUE;}return FALSE;}
static gboolean dialog_focus_key(GtkEventControllerKey *c,guint key,guint code,GdkModifierType state,gpointer w){
 int result=simple_control_key(GTK_WINDOW(w),key,state);if(result>=0)return result;
 if((state&GDK_CONTROL_MASK)&&(key==GDK_KEY_j||key==GDK_KEY_k))return escape_dialog(c,key,code,state,w);
 return FALSE;
}
static GtkWindow *dialog(const char *title,GtkWidget **body){GtkWindow *w=GTK_WINDOW(gtk_window_new());gtk_window_set_title(w,title);gtk_window_set_transient_for(w,a.win);gtk_window_set_modal(w,TRUE);gtk_window_set_destroy_with_parent(w,TRUE);gtk_window_set_default_size(w,480,-1);gtk_widget_add_css_class(GTK_WIDGET(w),CLASS);*body=box(TRUE,8);margin(*body,12);GtkWidget *s=scroll(*body);gtk_scrolled_window_set_propagate_natural_height(GTK_SCROLLED_WINDOW(s),TRUE);gtk_scrolled_window_set_max_content_height(GTK_SCROLLED_WINDOW(s),650);gtk_window_set_child(w,s);GtkEventController *k=gtk_event_controller_key_new();g_signal_connect(k,"key-pressed",G_CALLBACK(escape_dialog),w);gtk_widget_add_controller(GTK_WIDGET(w),k);GtkEventController *nav=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(nav,GTK_PHASE_CAPTURE);g_signal_connect(nav,"key-pressed",G_CALLBACK(dialog_focus_key),w);gtk_widget_add_controller(GTK_WIDGET(w),nav);return w;}
static void status(const char *s){gtk_label_set_text(GTK_LABEL(a.status),s);}
typedef struct {GSubprocess *process;GtkWindow *dialog;GtkWidget *error;char *op,*day;} Job;
static void response(GObject *source,GAsyncResult *result,gpointer data){
 Job *j=data;char *out=NULL,*err=NULL;GError *error=NULL;gboolean done=g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source),result,&out,&err,&error);a.busy=FALSE;
 if(!gtk_widget_get_visible(GTK_WIDGET(a.win))){g_clear_error(&error);g_free(out);g_free(err);g_object_unref(j->process);if(j->dialog)g_object_unref(j->dialog);if(j->error)g_object_unref(j->error);g_free(j->op);g_free(j->day);g_free(j);g_object_unref(a.win);g_application_release(G_APPLICATION(a.app));return;}
 json_object *root=done&&out?json_tokener_parse(out):NULL;gboolean ok=root&&boolean(root,"ok");
 if(!ok){const char *message=root?str(root,"error"):error?error->message:"Sync helper returned no valid response.";status(message);if(j->error)gtk_label_set_text(GTK_LABEL(j->error),message);}
 else {
  json_object *value=get(root,"data");
  if(j->dialog)close_window(NULL,j->dialog);
  if(CONTACTS){if(*str(value,"message"))status(str(value,"message"));else render(value);}
  else if(!strcmp(str(value,"day"),a.day))render(value);else a.reload=TRUE;
 }
 if(j->dialog)g_object_unref(j->dialog);if(j->error)g_object_unref(j->error);if(root)json_object_put(root);g_clear_error(&error);g_free(out);g_free(err);g_object_unref(j->process);g_free(j->op);g_free(j->day);g_free(j);
 gtk_widget_set_sensitive(GTK_WIDGET(a.win),TRUE);
 gboolean again=a.reload;a.reload=FALSE;if(again)reload_view();
 g_object_unref(a.win);g_application_release(G_APPLICATION(a.app));
}
static void request(json_object *r,GtkWindow *w,GtkWidget *error_label){
 if(a.busy){if(!strcmp(str(r,"op"),"list"))a.reload=TRUE;json_object_put(r);return;}
 if(!CONTACTS){putstr(r,"day",a.day);json_object_object_add(r,"days",json_object_new_int(gtk_drop_down_get_selected(GTK_DROP_DOWN(a.mode))?number("agenda_days",30,1,90):1));putbool(r,"local",gtk_check_button_get_active(GTK_CHECK_BUTTON(a.local)));}
 GError *e=NULL;GSubprocess *p=g_subprocess_new(G_SUBPROCESS_FLAGS_STDIN_PIPE|G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_PIPE,&e,a.python,a.helper,APPNAME,NULL);
 if(!p){status(e->message);g_clear_error(&e);json_object_put(r);return;}
 Job *j=g_new0(Job,1);j->process=p;j->op=g_strdup(str(r,"op"));j->day=g_strdup(a.day);j->dialog=w?g_object_ref(w):NULL;j->error=error_label?g_object_ref(error_label):NULL;
 g_object_ref(a.win);a.busy=TRUE;status(!strcmp(j->op,"list")?"Loading local data…":!strcmp(j->op,"connect")?"Approve access in the browser; waiting up to 30 minutes…":"Working…");g_application_hold(G_APPLICATION(a.app));
 g_subprocess_communicate_utf8_async(p,json_object_to_json_string(r),NULL,response,j);json_object_put(r);
}
static json_object *operation(const char *op){json_object *r=json_object_new_object();putstr(r,"op",op);return r;}
static void reload_view(void){request(operation("list"),NULL,NULL);}
static void sync_now(GtkWidget *w,gpointer p){(void)w;(void)p;request(operation("sync"),NULL,NULL);}
static void spawn(const char *program,const char *arg){GError *e=NULL;GSubprocess *p=g_subprocess_new(G_SUBPROCESS_FLAGS_NONE,&e,program,arg,NULL);if(p)g_object_unref(p);else{status(e->message);g_clear_error(&e);}}
static gboolean closed_editor(GtkWindow *w,gpointer unused){(void)unused;if(a.editor==w){a.editor=NULL;a.editor_error=NULL;}return FALSE;}
static void editor_destroyed(GtkWidget *w,gpointer unused){(void)unused;if(a.editor==GTK_WINDOW(w)){a.editor=NULL;a.editor_error=NULL;}}
static void set_editor(GtkWindow *w,GtkWidget *error){a.editor=w;a.editor_error=error;g_signal_connect(w,"close-request",G_CALLBACK(closed_editor),NULL);}
static GtkWidget *entry(GtkWidget *form,const char *title,const char *value){append(form,label(title,"muted"));GtkWidget *e=gtk_entry_new();gtk_editable_set_text(GTK_EDITABLE(e),value?value:"");append(form,e);return e;}
static GtkWidget *textview(GtkWidget *form,const char *title,const char *value){append(form,label(title,"muted"));GtkWidget *v=gtk_text_view_new();gtk_text_view_set_wrap_mode(GTK_TEXT_VIEW(v),GTK_WRAP_WORD_CHAR);gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(v)),value?value:"",-1);gtk_widget_set_size_request(v,-1,62);append(form,v);return v;}
static char *textvalue(GtkWidget *w){if(GTK_IS_TEXT_VIEW(w)){GtkTextBuffer *b=gtk_text_view_get_buffer(GTK_TEXT_VIEW(w));GtkTextIter s,e;gtk_text_buffer_get_bounds(b,&s,&e);return gtk_text_buffer_get_text(b,&s,&e,FALSE);}return g_strdup(gtk_editable_get_text(GTK_EDITABLE(w)));}
static json_object *first(json_object *p,const char *key){json_object *arr=get(p,key);return arr&&json_object_array_length(arr)?json_object_array_get_idx(arr,0):NULL;}
static char *contact_title(json_object *p){json_object *n=first(p,"names");if(*str(n,"displayName"))return g_strdup(str(n,"displayName"));char *v=g_strstrip(g_strdup_printf("%s %s",str(n,"givenName"),str(n,"familyName")));if(*v)return v;g_free(v);const char *extra=str(first(p,"emailAddresses"),"value");if(!*extra)extra=str(first(p,"phoneNumbers"),"value");return g_strdup(*extra?extra:"Unnamed contact");}
static char *joined(json_object *p,const char *field){GString *s=g_string_new(NULL);json_object *arr=get(p,field);for(size_t i=0;arr&&i<json_object_array_length(arr);i++){const char *v=str(json_object_array_get_idx(arr,i),"value");if(*v){if(s->len)g_string_append_c(s,'\n');g_string_append(s,v);}}return g_string_free(s,FALSE);}
static void copy_value(GtkWidget *w,gpointer data){(void)w;gdk_clipboard_set_text(gdk_display_get_clipboard(gdk_display_get_default()),data);}
static void write_email(GtkWidget *w,gpointer data){(void)w;char *escaped=g_uri_escape_string(data,"@",FALSE),*uri=g_strconcat("mailto:",escaped,NULL),*mail=g_strdup("simple-open");char *argv[]={mail,"mail",uri,NULL};g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,NULL);g_free(mail);g_free(uri);g_free(escaped);}
static void details_contact(json_object *p){
 clear(a.detail);own(&a.current,p);if(!p){append(a.detail,label("No contacts match your search.","muted"));return;}
 char *title=contact_title(p);append(a.detail,label(title,"heading"));g_free(title);GtkWidget *actions=box(FALSE,8);append(a.detail,actions);append(actions,button("Edit · e",G_CALLBACK(edit_contact),NULL));append(actions,button("Delete · x",G_CALLBACK(remove_selected),NULL));
 const char *fields[]={"emailAddresses","phoneNumbers","addresses","organizations","birthdays","biographies","urls"};const char *names[]={"Email","Phone","Address","Organization","Birthday","Notes","Website"};
 for(int k=0;k<7;k++){json_object *arr=get(p,fields[k]);if(!arr||!json_object_array_length(arr))continue;append(a.detail,label(names[k],"section"));
  for(size_t i=0;i<json_object_array_length(arr);i++){json_object *item=json_object_array_get_idx(arr,i);char *text=NULL;
   if(k==2)text=g_strdup(str(item,"formattedValue"));else if(k==3)text=g_strdup_printf("%s · %s",str(item,"name"),str(item,"title"));else if(k==4){json_object *d=get(item,"date");text=*str(item,"text")?g_strdup(str(item,"text")):g_strdup_printf("%02d-%02d%s%s",json_object_get_int(get(d,"month")),json_object_get_int(get(d,"day")),*str(d,"year")?" · ":"",str(d,"year"));}else text=g_strdup(str(item,"value"));
   GtkWidget *row=box(FALSE,8),*l=label(text,NULL);gtk_label_set_selectable(GTK_LABEL(l),TRUE);gtk_widget_set_hexpand(l,TRUE);append(row,l);
   if(k<2){GtkWidget *b=button("Copy",G_CALLBACK(copy_value),text);g_object_set_data_full(G_OBJECT(b),"value",g_strdup(text),g_free);g_signal_handlers_disconnect_by_func(b,copy_value,text);g_signal_connect(b,"clicked",G_CALLBACK(copy_value),g_object_get_data(G_OBJECT(b),"value"));append(row,b);}
   if(k==0){GtkWidget *b=button("Write",NULL,NULL);g_object_set_data_full(G_OBJECT(b),"value",g_strdup(text),g_free);g_signal_connect(b,"clicked",G_CALLBACK(write_email),g_object_get_data(G_OBJECT(b),"value"));append(row,b);}append(a.detail,row);g_free(text);
  }
 }
}
static void contact_selected(GObject *selection,GParamSpec *spec,gpointer unused){(void)spec;(void)unused;GtkStringObject *s=gtk_single_selection_get_selected_item(GTK_SINGLE_SELECTION(selection));json_object *p=s?json_tokener_parse(gtk_string_object_get_string(s)):NULL;details_contact(p);if(p)json_object_put(p);}
static void factory_setup(GtkSignalListItemFactory *f,GtkListItem *item,gpointer unused){(void)f;(void)unused;GtkWidget *b=box(TRUE,3);margin(b,8);GtkWidget *n=label("",NULL),*e=label("","muted");gtk_label_set_wrap(GTK_LABEL(n),FALSE);gtk_label_set_ellipsize(GTK_LABEL(n),PANGO_ELLIPSIZE_END);gtk_label_set_max_width_chars(GTK_LABEL(n),30);gtk_label_set_wrap(GTK_LABEL(e),FALSE);gtk_label_set_ellipsize(GTK_LABEL(e),PANGO_ELLIPSIZE_END);gtk_label_set_max_width_chars(GTK_LABEL(e),30);append(b,n);append(b,e);gtk_list_item_set_child(item,b);}
static void factory_bind(GtkSignalListItemFactory *f,GtkListItem *item,gpointer unused){(void)f;(void)unused;GtkStringObject *s=gtk_list_item_get_item(item);json_object *p=json_tokener_parse(gtk_string_object_get_string(s));GtkWidget *b=gtk_list_item_get_child(item),*n=gtk_widget_get_first_child(b),*e=gtk_widget_get_next_sibling(n);char *title=contact_title(p);gtk_label_set_text(GTK_LABEL(n),title);const char *extra=str(first(p,"emailAddresses"),"value");if(!*extra)extra=str(first(p,"phoneNumbers"),"value");gtk_label_set_text(GTK_LABEL(e),extra);gtk_widget_set_visible(e,*extra!=0);g_free(title);if(p)json_object_put(p);}
static gint compare_people(gconstpointer x,gconstpointer y){json_object *p=*(json_object *const*)x,*q=*(json_object *const*)y;char *s=contact_title(p),*t=contact_title(q);int n=g_utf8_collate(s,t);g_free(s);g_free(t);return n;}
static void contacts_model(void){
 json_object *people=get(a.data,"people");const char *query=gtk_editable_get_text(GTK_EDITABLE(a.search));char *fold=g_utf8_casefold(query,-1),*rid=g_strdup(str(a.current,"resourceName"));
 char *stamp=g_strdup_printf("%s\n%s",query,people?json_object_to_json_string(people):"");if(!g_strcmp0(stamp,a.contact_stamp)){g_free(stamp);g_free(fold);g_free(rid);return;}g_free(a.contact_stamp);a.contact_stamp=stamp;
 GPtrArray *sorted=g_ptr_array_new();for(size_t i=0;people&&i<json_object_array_length(people);i++)g_ptr_array_add(sorted,json_object_array_get_idx(people,i));g_ptr_array_sort(sorted,compare_people);
 GtkStringList *model=gtk_string_list_new(NULL);guint chosen=0,index=0;
 for(guint i=0;i<sorted->len;i++){json_object *p=g_ptr_array_index(sorted,i);char *name=contact_title(p),*emails=joined(p,"emailAddresses"),*phones=joined(p,"phoneNumbers"),*all=g_strdup_printf("%s %s %s",name,emails,phones),*lower=g_utf8_casefold(all,-1);
  if(strstr(lower,fold)){gtk_string_list_append(model,json_object_to_json_string(p));if(!strcmp(str(p,"resourceName"),rid))chosen=index;index++;}g_free(name);g_free(emails);g_free(phones);g_free(all);g_free(lower);
 }
 g_signal_handlers_block_by_func(a.selection,contact_selected,NULL);gtk_single_selection_set_model(a.selection,G_LIST_MODEL(model));gtk_single_selection_set_selected(a.selection,index?chosen:GTK_INVALID_LIST_POSITION);g_signal_handlers_unblock_by_func(a.selection,contact_selected,NULL);contact_selected(G_OBJECT(a.selection),NULL,NULL);if(index)gtk_list_view_scroll_to(GTK_LIST_VIEW(a.list),chosen,GTK_LIST_SCROLL_NONE,NULL);g_object_unref(model);g_ptr_array_unref(sorted);g_free(fold);g_free(rid);
}
static void search_changed(GtkSearchEntry *e,gpointer unused){(void)e;(void)unused;contacts_model();}
typedef struct {GtkWindow *win;GtkWidget *error,*save;GtkWidget *fields[5];json_object *original;char *initial[5];} ContactForm;
static const char *contact_keys[]={"given","family","emails","phones","notes"};
static void free_contact_form(gpointer data){ContactForm *f=data;if(f->original)json_object_put(f->original);for(int i=0;i<5;i++)g_free(f->initial[i]);g_free(f);}
static void contact_dirty(GObject *obj,gpointer data){(void)obj;ContactForm *f=data;gboolean dirty=FALSE;for(int i=0;i<5;i++){char *s=textvalue(f->fields[i]);if(g_strcmp0(s,f->initial[i]))dirty=TRUE;g_free(s);}gtk_widget_set_sensitive(f->save,dirty);}
static void save_contact(GtkWidget *unused,gpointer data){(void)unused;ContactForm *f=data;if(a.busy)return;json_object *r=operation("save"),*form=json_object_new_object();for(int i=0;i<5;i++){char *s=textvalue(f->fields[i]);putstr(form,contact_keys[i],s);g_free(s);}json_object_object_add(r,"form",form);if(f->original)json_object_object_add(r,"original",json_object_get(f->original));request(r,f->win,f->error);}
static gboolean contact_save_key(GtkEventControllerKey *controller,guint key,guint code,GdkModifierType state,gpointer data){(void)controller;(void)code;if(match("contacts","save","<Control>s",key,state)){save_contact(NULL,data);return TRUE;}return FALSE;}
static void edit_contact(GtkWidget *unused,gpointer new_contact){(void)unused;if(a.busy)return;if(a.editor){gtk_window_present(a.editor);return;}if(!a.connected){show_accounts(NULL,NULL);return;}
 GtkWidget *body;ContactForm *f=g_new0(ContactForm,1);f->win=dialog(new_contact?"New contact":"Edit contact",&body);if(!new_contact&&a.current)f->original=json_object_get(a.current);
 json_object *n=first(f->original,"names");f->initial[0]=g_strdup(str(n,"givenName"));f->initial[1]=g_strdup(str(n,"familyName"));f->initial[2]=joined(f->original,"emailAddresses");f->initial[3]=joined(f->original,"phoneNumbers");f->initial[4]=g_strdup(str(first(f->original,"biographies"),"value"));
 const char *titles[]={"Given name","Family name","Email addresses · one per line","Phone numbers · one per line","Notes"};for(int i=0;i<5;i++)f->fields[i]=i<2?entry(body,titles[i],f->initial[i]):textview(body,titles[i],f->initial[i]);
 append(body,label("Other fields stay unchanged. Saving requires internet.","muted"));f->error=label("",NULL);append(body,f->error);f->save=button("Save to Google",G_CALLBACK(save_contact),f);gtk_widget_add_css_class(f->save,"primary");append(body,f->save);append(body,button("Cancel",G_CALLBACK(close_window),f->win));
 for(int i=0;i<5;i++)g_signal_connect(i<2?G_OBJECT(f->fields[i]):G_OBJECT(gtk_text_view_get_buffer(GTK_TEXT_VIEW(f->fields[i]))),"changed",G_CALLBACK(contact_dirty),f);
 contact_dirty(NULL,f);g_object_set_data_full(G_OBJECT(f->win),"form",f,free_contact_form);set_editor(f->win,f->error);GtkEventController *k=gtk_event_controller_key_new();g_signal_connect(k,"key-pressed",G_CALLBACK(contact_save_key),f);gtk_widget_add_controller(GTK_WIDGET(f->win),k);gtk_window_present(f->win);
}
static void go_day(const char *day){GDateTime *d=parseday(day);if(!d)return;g_free(a.day);a.day=g_date_time_format(d,"%F");a.changing=TRUE;gtk_calendar_select_day(GTK_CALENDAR(a.calendar),d);a.changing=FALSE;g_date_time_unref(d);a.event_index=0;reload_view();}
static void move_day(int delta,gboolean month){GDateTime *d=parseday(a.day),*next=month?g_date_time_add_months(d,delta):g_date_time_add_days(d,delta);char *s=g_date_time_format(next,"%F");go_day(s);g_free(s);g_date_time_unref(next);g_date_time_unref(d);}
static void today_click(GtkWidget *w,gpointer p){(void)w;(void)p;char *s=today();go_day(s);g_free(s);}
static void calendar_changed(GtkCalendar *c,gpointer unused){(void)unused;if(a.changing)return;GDateTime *d=gtk_calendar_get_date(c);char *s=g_date_time_format(d,"%F");g_date_time_unref(d);if(g_strcmp0(s,a.day)){g_free(a.day);a.day=s;a.event_index=0;reload_view();}else g_free(s);}
static void mode_changed(GObject *o,GParamSpec *s,gpointer p){(void)o;(void)s;(void)p;reload_view();}
static void local_changed(GtkCheckButton *w,gpointer p){(void)w;(void)p;reload_view();}
static gboolean array_has(json_object *arr,int n){for(size_t i=0;arr&&i<json_object_array_length(arr);i++)if(json_object_get_int(json_object_array_get_idx(arr,i))==n)return TRUE;return FALSE;}
static void mark_labels(GtkWidget *widget,json_object *data){
 if(GTK_IS_LABEL(widget)&&gtk_widget_has_css_class(widget,"day-number")){int n=atoi(gtk_label_get_text(GTK_LABEL(widget)));gboolean other=gtk_widget_has_css_class(widget,"other-month");gboolean moon=!other&&array_has(get(data,"moons"),n);char *date=g_strdup_printf("%.8s%02d",a.day,n);gboolean report=show_report&&!other&&!strcmp(date,str(data,"report"));g_free(date);
  char *markup=g_strdup_printf("%d%s%s%s",n,moon||report?" ":"",moon?"<span foreground=\"#e9a04b\">●</span>":"",report?"<span foreground=\"#e66565\">●</span>":"");gtk_label_set_markup(GTK_LABEL(widget),markup);g_free(markup);
 }
 for(GtkWidget *c=gtk_widget_get_first_child(widget);c;c=gtk_widget_get_next_sibling(c))mark_labels(c,data);
}
static void highlight_events(void){for(guint i=0;i<a.cards->len;i++){GtkWidget *w=g_ptr_array_index(a.cards,i);if(i==a.event_index)gtk_widget_add_css_class(w,"active-event");else gtk_widget_remove_css_class(w,"active-event");}json_object *arr=get(a.data,"cards");own(&a.current,arr&&a.event_index<json_object_array_length(arr)?json_object_array_get_idx(arr,a.event_index):NULL);}
static void card_pressed(GtkGestureClick *gesture,int count,double x,double y,gpointer index){(void)gesture;(void)count;(void)x;(void)y;a.event_index=GPOINTER_TO_UINT(index);highlight_events();}
static void card_focus(GtkEventControllerFocus *c,gpointer index){(void)c;a.event_index=GPOINTER_TO_UINT(index);highlight_events();}
static void edit_card(GtkWidget *w,gpointer index){a.event_index=GPOINTER_TO_UINT(index);highlight_events();edit_event(w,NULL);}
static void detail_card(GtkWidget *w,gpointer index){a.event_index=GPOINTER_TO_UINT(index);highlight_events();show_details(w,NULL);}
static void empty_calendar(void){
 GtkWidget *empty=box(TRUE,6);a.image_card=gtk_overlay_new();gtk_widget_add_css_class(a.image_card,"monk-card");gtk_widget_set_overflow(a.image_card,GTK_OVERFLOW_HIDDEN);gtk_widget_set_valign(a.image_card,GTK_ALIGN_START);gtk_overlay_set_child(GTK_OVERLAY(a.image_card),box(TRUE,0));char *image=g_build_filename(a.dir,"assets","matrix-monk-wide.png",NULL);GtkWidget *pic=gtk_picture_new_for_filename(image);g_free(image);a.empty_art.picture=GTK_PICTURE(pic);a.empty_art.full_image=TRUE;simple_daylight_art_update(&a.empty_art);gtk_picture_set_content_fit(GTK_PICTURE(pic),GTK_CONTENT_FIT_COVER);gtk_picture_set_can_shrink(GTK_PICTURE(pic),TRUE);gtk_overlay_add_overlay(GTK_OVERLAY(a.image_card),pic);gtk_size_group_add_widget(a.card_size,a.image_card);append(empty,a.image_card);
 a.legend_space=box(TRUE,0);gtk_size_group_add_widget(a.legend_size,a.legend_space);append(empty,a.legend_space);a.breath_card=box(TRUE,0);gtk_widget_add_css_class(a.breath_card,"breath-card");gtk_widget_set_margin_top(a.breath_card,12);gtk_size_group_add_widget(a.action_size,a.breath_card);GtkWidget *caption=label("Sit and follow the breath",NULL);gtk_widget_set_halign(caption,GTK_ALIGN_CENTER);append(a.breath_card,caption);append(empty,a.breath_card);append(a.events,empty);
}
static void render_calendar(json_object *data){
 status(str(data,"status"));a.connected=boolean(data,"connected");
 GDateTime *d=parseday(a.day);char *title=g_date_time_format(d,"%d %B %Y");gtk_label_set_text(GTK_LABEL(a.heading),title);g_free(title);g_date_time_unref(d);
 gtk_calendar_clear_marks(GTK_CALENDAR(a.calendar));json_object *marks=get(data,"marks");for(size_t i=0;marks&&i<json_object_array_length(marks);i++)gtk_calendar_mark_day(GTK_CALENDAR(a.calendar),json_object_get_int(json_object_array_get_idx(marks,i)));mark_labels(a.calendar,data);
 json_object *cards=get(data,"cards");char *stamp=g_strdup_printf("%s|%s",a.day,cards?json_object_to_json_string(cards):"");if(!g_strcmp0(stamp,a.view_stamp)){g_free(stamp);return;}g_free(a.view_stamp);a.view_stamp=stamp;
 if(a.image_card){simple_daylight_art_clear(&a.empty_art);gtk_size_group_remove_widget(a.card_size,a.image_card);gtk_size_group_remove_widget(a.legend_size,a.legend_space);gtk_size_group_remove_widget(a.action_size,a.breath_card);a.image_card=a.legend_space=a.breath_card=NULL;}
 g_ptr_array_set_size(a.cards,0);clear(a.events);size_t count=cards?json_object_array_length(cards):0;gtk_widget_set_visible(a.empty_caption,count==0);
 char *last=NULL;for(size_t i=0;i<count;i++){json_object *e=json_object_array_get_idx(cards,i);const char *view=str(e,"view_day");if(gtk_drop_down_get_selected(GTK_DROP_DOWN(a.mode))&&g_strcmp0(last,view)){append(a.events,label(view,"heading"));g_free(last);last=g_strdup(view);}
  GtkWidget *card=box(TRUE,6);gtk_widget_add_css_class(card,"card");gtk_widget_set_focusable(card,TRUE);append(a.events,card);g_ptr_array_add(a.cards,card);GtkGesture *g=gtk_gesture_click_new();g_signal_connect(g,"pressed",G_CALLBACK(card_pressed),GUINT_TO_POINTER(i));gtk_widget_add_controller(card,GTK_EVENT_CONTROLLER(g));GtkEventController *f=gtk_event_controller_focus_new();g_signal_connect(f,"enter",G_CALLBACK(card_focus),GUINT_TO_POINTER(i));gtk_widget_add_controller(card,f);
  char *line;if(*str(e,"layer"))line=g_strdup(str(e,"title"));else if(boolean(e,"all_day"))line=g_strdup_printf("All day · %s",str(e,"title"));else line=g_strdup_printf("%.5s – %.5s · %s",strlen(str(e,"start"))>11?str(e,"start")+11:"",strlen(str(e,"end"))>11?str(e,"end")+11:"",str(e,"title"));append(card,label(line,NULL));g_free(line);
  GtkWidget *row=box(FALSE,6),*meta=label(*str(e,"layer")?str(e,"layer"):str(e,"calendar"),"muted");gtk_widget_set_hexpand(meta,TRUE);append(row,meta);append(row,button("Details",G_CALLBACK(detail_card),GUINT_TO_POINTER(i)));if(boolean(e,"editable"))append(row,button("Edit",G_CALLBACK(edit_card),GUINT_TO_POINTER(i)));append(card,row);
 }
 g_free(last);if(!count)empty_calendar();a.event_index=MIN(a.event_index,count?count-1:0);highlight_events();
}
/* Preserve the measured content minimum when async data changes the layout.
 * Floating compositors may otherwise reuse the smaller initial size. */
static void fit_content(void){
 GtkWidget *body=gtk_window_get_child(a.win);int width=0,height=0,oldw=-1,oldh=-1;
 gtk_widget_measure(body,GTK_ORIENTATION_HORIZONTAL,-1,&width,NULL,NULL,NULL);
 gtk_widget_measure(body,GTK_ORIENTATION_VERTICAL,width,&height,NULL,NULL,NULL);
 gtk_widget_get_size_request(GTK_WIDGET(a.win),&oldw,&oldh);
 width=MAX(width,oldw);height=MAX(height,oldh);
 gtk_widget_set_size_request(GTK_WIDGET(a.win),width,height);
 if(!gtk_widget_get_mapped(GTK_WIDGET(a.win))||a.initial)
  gtk_window_set_default_size(a.win,MAX(width,number("width",CONTACTS?850:860,CONTACTS?500:860,2000)),MAX(height,number("height",CONTACTS?560:520,350,1600)));
}
static void render(json_object *data){own(&a.data,data);if(CONTACTS){a.connected=boolean(data,"connected");json_object *people=get(data,"people");char *s=g_strdup_printf("%zu contacts · Local copy%s%s",people?json_object_array_length(people):0,*str(data,"synced")?" · ":"",str(data,"synced"));status(*str(data,"error")?str(data,"error"):a.connected?s:"Connect Google Contacts to download your local copy.");g_free(s);contacts_model();}else render_calendar(data);
 fit_content();
 if(a.initial){a.initial=FALSE;if(CONTACTS&&a.connected&&!g_getenv("SIMPLE_ORGANIZER_SMOKE"))sync_now(NULL,NULL);}
}
typedef struct {GtkWindow *win;GtkWidget *error,*save,*title,*day,*last,*start,*end,*all_day,*reminder,*notification_box,*add_notification,*notes,*base,*repeat,*repeat_interval;GPtrArray *notification_rows;json_object *original;char *initial;gboolean report;} EventForm;
static const char *repeat_values[]={"none","daily","weekly","monthly","yearly"};
static const int reminders[]={0,15,30,60,1440,10080,14400,40320};
static void free_event_form(gpointer p){EventForm *f=p;g_free(f->initial);if(f->original)json_object_put(f->original);if(f->notification_rows)g_ptr_array_free(f->notification_rows,TRUE);g_free(f);}
typedef struct {EventForm *form;GtkWidget *box,*drop;int custom_minutes;} NotificationRow;
static int notification_minutes(NotificationRow *r){guint i=gtk_drop_down_get_selected(GTK_DROP_DOWN(r->drop));return i<G_N_ELEMENTS(reminders)?reminders[i]:r->custom_minutes;}
static int reminder_compare(gconstpointer a,gconstpointer b){int x=*(const int*)a,y=*(const int*)b;return (x>y)-(x<y);}
static char *event_snapshot(EventForm *f){
 json_object *form=json_object_new_object();GtkWidget *widgets[]={f->title,f->day,f->last,f->start,f->end,f->notes,f->base};
 const char *keys[]={"title","day","last","start","end","notes","base"};
 for(int i=0;i<7;i++)if(widgets[i]){char *value=textvalue(widgets[i]);putstr(form,keys[i],value);g_free(value);}
 putbool(form,"all_day",gtk_check_button_get_active(GTK_CHECK_BUTTON(f->all_day)));
 putstr(form,"repeat",repeat_values[gtk_drop_down_get_selected(GTK_DROP_DOWN(f->repeat))]);json_object_object_add(form,"repeat_interval",json_object_new_int(gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(f->repeat_interval))));
 GArray *values=g_array_new(FALSE,FALSE,sizeof(int));for(guint i=0;i<f->notification_rows->len;i++){int n=notification_minutes(g_ptr_array_index(f->notification_rows,i));g_array_append_val(values,n);}g_array_sort(values,reminder_compare);
 json_object *alarms=json_object_new_array();for(guint i=0;i<values->len;i++)json_object_array_add(alarms,json_object_new_int(g_array_index(values,int,i)));g_array_free(values,TRUE);json_object_object_add(form,"alarms",alarms);
 char *result=g_strdup(json_object_to_json_string_ext(form,JSON_C_TO_STRING_PLAIN));json_object_put(form);return result;
}
static void event_dirty(gpointer unused,gpointer data){
 (void)unused;EventForm *f=data;if(!f->initial||!f->save)return;
 char *current=event_snapshot(f),*title=g_strdup(gtk_editable_get_text(GTK_EDITABLE(f->title)));
 gboolean dirty=!f->original||strcmp(current,f->initial)!=0;
 gtk_widget_set_sensitive(f->save,dirty&&*g_strstrip(title));g_free(current);g_free(title);
}
static void notification_changed(GObject *o,GParamSpec *p,gpointer data){(void)o;(void)p;event_dirty(NULL,data);}
static void remove_notification(GtkWidget *button,gpointer data){
 NotificationRow *r=data;EventForm *f=r->form;gtk_box_remove(GTK_BOX(f->notification_box),r->box);g_ptr_array_remove(f->notification_rows,r);gtk_widget_set_sensitive(f->add_notification,f->notification_rows->len<5);event_dirty(NULL,f);
}
static void notification_row(EventForm *f,int minutes){
 const char *options[]={"At start","15 minutes before","30 minutes before","1 hour before","1 day before","1 week before","10 days before","4 weeks before",NULL};
 NotificationRow *r=g_new0(NotificationRow,1);r->form=f;r->custom_minutes=minutes;r->box=box(FALSE,8);
 GtkStringList *model=gtk_string_list_new(options);guint chosen=G_N_ELEMENTS(reminders);
 for(guint i=0;i<G_N_ELEMENTS(reminders);i++)if(reminders[i]==minutes){chosen=i;break;}
 if(chosen==G_N_ELEMENTS(reminders)){char *title=g_strdup_printf("%d minutes before (existing)",minutes);gtk_string_list_append(model,title);g_free(title);}
 r->drop=gtk_drop_down_new(G_LIST_MODEL(model),NULL);gtk_drop_down_set_selected(GTK_DROP_DOWN(r->drop),chosen);gtk_widget_set_hexpand(r->drop,TRUE);
 append(r->box,r->drop);append(r->box,button("Remove",G_CALLBACK(remove_notification),r));append(f->notification_box,r->box);g_ptr_array_add(f->notification_rows,r);
 if(!f->reminder)f->reminder=r->drop;
 gtk_widget_set_sensitive(f->add_notification,f->notification_rows->len<5);
 g_signal_connect(r->drop,"notify::selected",G_CALLBACK(notification_changed),f);event_dirty(NULL,f);
}
static void add_notification(GtkWidget *button,gpointer data){
 EventForm *f=data;if(f->notification_rows->len>=5)return;
 const int preferred[]={1440,10080,14400,40320,60,30,15,0};int minutes=1440;
 for(guint i=0;i<G_N_ELEMENTS(preferred);i++){gboolean used=FALSE;for(guint j=0;j<f->notification_rows->len;j++)if(notification_minutes(g_ptr_array_index(f->notification_rows,j))==preferred[i])used=TRUE;if(!used){minutes=preferred[i];break;}}
 notification_row(f,minutes);
}
static void event_times_changed(GtkCheckButton *b,gpointer data){EventForm *f=data;gboolean active=gtk_check_button_get_active(b);gtk_widget_set_sensitive(f->start,!active);gtk_widget_set_sensitive(f->end,!active);}
static void report_changed(GtkEditable *e,gpointer data){EventForm *f=data;GDateTime *base=parseday(gtk_editable_get_text(e));if(!base){gtk_label_set_text(GTK_LABEL(f->error),"Enter a valid report / entry date: YYYY-MM-DD");return;}GDateTime *due=g_date_time_add_days(base,90);char *day=g_date_time_format(due,"%F"),*note=g_strdup_printf("90-day immigration report. Calculated from report / entry date %s. Check next appointment date against immigration receipt.",gtk_editable_get_text(e));gtk_editable_set_text(GTK_EDITABLE(f->day),day);gtk_editable_set_text(GTK_EDITABLE(f->last),day);gtk_text_buffer_set_text(gtk_text_view_get_buffer(GTK_TEXT_VIEW(f->notes)),note,-1);gtk_label_set_text(GTK_LABEL(f->error),"");g_free(day);g_free(note);g_date_time_unref(due);g_date_time_unref(base);}
static void save_event(GtkWidget *unused,gpointer data){(void)unused;EventForm *f=data;if(a.busy||!gtk_widget_get_sensitive(f->save))return;json_object *r=operation("save"),*form=json_object_new_object();GtkWidget *widgets[]={f->title,f->day,f->last,f->start,f->end,f->notes};const char *keys[]={"title","day","end_day","start","end","description"};for(int i=0;i<6;i++){char *s=textvalue(widgets[i]);putstr(form,keys[i],s);g_free(s);}putbool(form,"all_day",gtk_check_button_get_active(GTK_CHECK_BUTTON(f->all_day)));
 putstr(form,"repeat",repeat_values[gtk_drop_down_get_selected(GTK_DROP_DOWN(f->repeat))]);json_object_object_add(form,"repeat_interval",json_object_new_int(gtk_spin_button_get_value_as_int(GTK_SPIN_BUTTON(f->repeat_interval))));json_object *notifications=json_object_new_array();for(guint i=0;i<f->notification_rows->len;i++)json_object_array_add(notifications,json_object_new_int(notification_minutes(g_ptr_array_index(f->notification_rows,i))));json_object_object_add(form,"reminder",notifications);json_object_object_add(r,"form",form);if(f->original)json_object_object_add(r,"original",json_object_get(f->original));if(f->report){putbool(r,"report",TRUE);putstr(r,"base",gtk_editable_get_text(GTK_EDITABLE(f->base)));}request(r,f->win,f->error);}
static gboolean save_key(GtkEventControllerKey *c,guint key,guint code,GdkModifierType state,gpointer data){(void)c;(void)code;EventForm *f=data;if(match("calendar","save","<Control>s",key,state)){save_event(NULL,f);return TRUE;}if(match("calendar","add_notification","<Control><Shift>n",key,state)){add_notification(NULL,f);return TRUE;}return FALSE;}
static void edit_event(GtkWidget *unused,gpointer mode){(void)unused;if(a.busy)return;if(a.editor){gtk_window_present(a.editor);return;}if(!a.connected){show_accounts(NULL,NULL);return;}guint kind=GPOINTER_TO_UINT(mode);if(kind==0&&(!a.current||!boolean(a.current,"editable"))){if(a.current)show_details(NULL,NULL);return;}
 GtkWidget *body;EventForm *f=g_new0(EventForm,1);f->report=kind==2;f->win=dialog(f->report?"90-day report":kind==1?"New event":"Edit event",&body);if(kind==0)f->original=json_object_get(a.current);
 if(f->report){f->base=entry(body,"Last report / entry date · YYYY-MM-DD",a.day);append(body,label("Date + 90 days. Use your immigration receipt's next date if different.","muted"));}
 f->title=entry(body,"Title",f->original?str(f->original,"title"):f->report?"90-day report":"");gboolean all=f->report||boolean(f->original,"all_day");f->all_day=gtk_check_button_new_with_label("All day");gtk_check_button_set_active(GTK_CHECK_BUTTON(f->all_day),all);append(body,f->all_day);
 const char *start=f->original?str(f->original,"start"):a.day;const char *end=f->original?str(f->original,"end"):a.day;char *day=g_strndup(start,10),*last=g_strndup(end,10);
 if(f->original&&all){GDateTime *b=parseday(last);if(b){GDateTime *before=g_date_time_add_days(b,-1);g_free(last);last=g_date_time_format(before,"%F");g_date_time_unref(before);g_date_time_unref(b);}}
 f->day=entry(body,"Start date · YYYY-MM-DD",day);f->last=entry(body,"Last date · YYYY-MM-DD",last);g_free(day);g_free(last);char *time1=g_strndup(strlen(start)>15?start+11:"09:00",5),*time2=g_strndup(strlen(end)>15?end+11:"10:00",5);f->start=entry(body,"Start time · HH:MM",time1);f->end=entry(body,"End time · HH:MM",time2);g_free(time1);g_free(time2);
 const char *repeat_options[]={"Does not repeat","Daily","Weekly · same weekday","Monthly · same date","Yearly · same date",NULL};
 GtkWidget *repeat_row=box(FALSE,8);f->repeat=gtk_drop_down_new_from_strings(repeat_options);gtk_widget_set_hexpand(f->repeat,TRUE);f->repeat_interval=gtk_spin_button_new_with_range(1,99,1);gtk_spin_button_set_value(GTK_SPIN_BUTTON(f->repeat_interval),1);
 append(repeat_row,f->repeat);append(repeat_row,label("Every", "muted"));append(repeat_row,f->repeat_interval);append(repeat_row,label("period(s)","muted"));append(body,repeat_row);gtk_widget_set_visible(repeat_row,!f->report);
 if(!f->report)append(body,label("Repeats from the start date. Months without that date are skipped. Manage the series in your calendar provider.","muted"));
 g_signal_connect(f->repeat,"notify::selected",G_CALLBACK(notification_changed),f);g_signal_connect(f->repeat_interval,"value-changed",G_CALLBACK(event_dirty),f);
 append(body,label("Notifications", "muted"));f->notification_rows=g_ptr_array_new_with_free_func(g_free);f->notification_box=box(TRUE,6);append(body,f->notification_box);f->add_notification=button("+ Add notification · Ctrl+Shift+N",G_CALLBACK(add_notification),f);append(body,f->add_notification);
 if(f->original){json_object *alarms=get(f->original,"alarms");GDateTime *dt=g_date_time_new_from_iso8601(start,NULL);if(dt&&alarms){for(size_t i=0;i<json_object_array_length(alarms);i++){GDateTime *at=g_date_time_new_from_iso8601(json_object_get_string(json_object_array_get_idx(alarms,i)),NULL);if(at){gint64 minutes=g_date_time_difference(dt,at)/(60*G_TIME_SPAN_SECOND);notification_row(f,(int)minutes);g_date_time_unref(at);}}}if(dt)g_date_time_unref(dt);}else notification_row(f,1440);
 f->notes=textview(body,"Notes",str(f->original,"description"));if(f->report)append(body,label("All-day notifications use midnight as the event start.","muted"));f->error=label("",NULL);append(body,f->error);f->save=button(f->original?"Save changes · Ctrl+S":"Add event · Ctrl+S",G_CALLBACK(save_event),f);gtk_widget_add_css_class(f->save,"primary");GtkWidget *scroller=gtk_window_get_child(f->win);g_object_ref(scroller);gtk_window_set_child(f->win,NULL);
 GtkWidget *layout=box(TRUE,0),*toolbar=box(FALSE,8);margin(toolbar,12);GtkWidget *caption=label(f->original?"Edit event":f->report?"90-day report":"New event","heading");gtk_widget_set_hexpand(caption,TRUE);append(toolbar,caption);append(toolbar,button("Cancel",G_CALLBACK(close_window),f->win));append(toolbar,f->save);append(layout,toolbar);GtkWidget *hint=label("Tab / Shift+Tab or Ctrl+j/k: fields · Space: toggle · Esc: cancel","muted");gtk_widget_set_margin_start(hint,12);gtk_widget_set_margin_bottom(hint,8);append(layout,hint);append(layout,scroller);g_object_unref(scroller);gtk_window_set_child(f->win,layout);
 g_signal_connect(f->all_day,"toggled",G_CALLBACK(event_times_changed),f);event_times_changed(GTK_CHECK_BUTTON(f->all_day),f);if(f->report){g_signal_connect(f->base,"changed",G_CALLBACK(report_changed),f);report_changed(GTK_EDITABLE(f->base),f);}
 f->initial=event_snapshot(f);
 GtkWidget *watched[]={f->title,f->day,f->last,f->start,f->end,f->base};for(guint i=0;i<G_N_ELEMENTS(watched);i++)if(watched[i])g_signal_connect(watched[i],"changed",G_CALLBACK(event_dirty),f);
 g_signal_connect(gtk_text_view_get_buffer(GTK_TEXT_VIEW(f->notes)),"changed",G_CALLBACK(event_dirty),f);g_signal_connect(f->all_day,"toggled",G_CALLBACK(event_dirty),f);event_dirty(NULL,f);
 g_object_set_data_full(G_OBJECT(f->win),"form",f,free_event_form);set_editor(f->win,f->error);GtkEventController *k=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(k,GTK_PHASE_CAPTURE);g_signal_connect(k,"key-pressed",G_CALLBACK(save_key),f);gtk_widget_add_controller(GTK_WIDGET(f->win),k);gtk_window_present(f->win);
}
static void confirm_remove(GtkWidget *w,gpointer data){(void)w;GtkWindow *win=data;json_object *r=operation("remove"),*original=g_object_get_data(G_OBJECT(win),"original");json_object_object_add(r,"original",json_object_get(original));request(r,win,g_object_get_data(G_OBJECT(win),"error"));}
static void remove_selected(GtkWidget *w,gpointer unused){(void)w;(void)unused;if(!a.current||a.busy)return;if(!CONTACTS&&!boolean(a.current,"editable")){status("This event is read-only.");return;}GtkWidget *body;GtkWindow *win=dialog(CONTACTS?"Delete contact?":"Delete event?",&body);char *title=CONTACTS?contact_title(a.current):g_strdup(str(a.current,"title"));append(body,label(title,"heading"));g_free(title);append(body,label("This deletes the selected item from your account after sync.",NULL));GtkWidget *error=label("",NULL);append(body,error);g_object_set_data_full(G_OBJECT(win),"original",json_object_get(a.current),drop_json);g_object_set_data(G_OBJECT(win),"error",error);append(body,button("Delete",G_CALLBACK(confirm_remove),win));append(body,button("Cancel",G_CALLBACK(close_window),win));gtk_window_present(win);}
static void show_details(GtkWidget *w,gpointer unused){(void)w;(void)unused;if(!a.current)return;GtkWidget *body;GtkWindow *win=dialog("Event details",&body);const char *fields[]={"title","start","end","day","description","layer","calendar"};for(int i=0;i<7;i++)if(*str(a.current,fields[i])){GtkWidget *l=label(str(a.current,fields[i]),i==0?"heading":NULL);gtk_label_set_selectable(GTK_LABEL(l),TRUE);append(body,l);}if(!boolean(a.current,"editable"))append(body,label("Read-only event", "muted"));append(body,button("Close",G_CALLBACK(close_window),win));gtk_window_present(win);}
static void do_export(GtkWidget *w,gpointer data){(void)w;GtkWindow *win=data;json_object *r=operation("export");putstr(r,"path",gtk_editable_get_text(g_object_get_data(G_OBJECT(win),"entry")));request(r,win,g_object_get_data(G_OBJECT(win),"error"));}
static void export_contacts(GtkWidget *w,gpointer unused){(void)w;(void)unused;GtkWidget *body;GtkWindow *win=dialog("Export local contacts",&body);char *file=g_build_filename(g_get_home_dir(),"contacts.vcf",NULL);GtkWidget *e=entry(body,"New vCard filename",file),*error=label("",NULL);g_free(file);append(body,error);g_object_set_data(G_OBJECT(win),"entry",e);g_object_set_data(G_OBJECT(win),"error",error);append(body,button("Export",G_CALLBACK(do_export),win));append(body,button("Cancel",G_CALLBACK(close_window),win));gtk_window_present(win);}
static void connect_account(GtkWidget *w,gpointer data){(void)w;GtkWindow *win=data;if(CONTACTS)request(operation("connect"),win,g_object_get_data(G_OBJECT(win),"error"));else{char *argv[]={"simple-open","terminal","simple-calendar","--connect",NULL};g_spawn_async(NULL,argv,NULL,G_SPAWN_SEARCH_PATH,NULL,NULL,NULL,NULL);gtk_window_destroy(win);}}
static void show_accounts(GtkWidget *w,gpointer unused){(void)w;(void)unused;GtkWidget *body;GtkWindow *win=dialog("Accounts",&body);append(body,label(a.connected?"Account connected":"Connect your account","heading"));append(body,label(CONTACTS?"Google Contacts · local copy available offline":"Google Calendar / CalDAV · local copy available offline",NULL));append(body,label("Google sign-in uses the shared browser authentication helper. Calendar and Contacts require their own access permissions.","muted"));GtkWidget *error=label("",NULL);append(body,error);g_object_set_data(G_OBJECT(win),"error",error);append(body,button(a.connected?"Reconnect / configure":"Connect",G_CALLBACK(connect_account),win));if(*str(a.data,"sync_log")){GtkWidget *log=textview(body,"Last sync",str(a.data,"sync_log"));gtk_text_view_set_editable(GTK_TEXT_VIEW(log),FALSE);}
 append(body,button("Close",G_CALLBACK(close_window),win));gtk_window_present(win);}
static void show_help(void){GtkWidget *body;GtkWindow *win=dialog("Keyboard shortcuts",&body);append(body,label(CONTACTS?"j/k: contacts · Ctrl+j/k: results while searching\nEnter: focus results · Tab/Shift+Tab: controls\nh/l: focus · /: search · n: new · e: edit · x: delete\ns: sync · c: accounts · b: export · Esc/q: close":"h/l: day · j/k: week · H/L: month\nJ/K: events · n/Ctrl+N: new · e: edit · x: delete\nt/g/Home: today · a: agenda\ns: sync · c: accounts · Esc/q: close\nEditor: Ctrl+S save · Ctrl+Shift+N add notification\nTab/Shift+Tab or Ctrl+j/k: next/previous field\nSpace: toggle/open · arrows: choose · Enter: button · Esc: cancel",NULL));append(body,button("Close",G_CALLBACK(close_window),win));gtk_window_present(win);}
static void contact_move(int delta,gboolean keep_search) {
 guint count=g_list_model_get_n_items(G_LIST_MODEL(a.selection));
 if(!count)return;
 guint old=gtk_single_selection_get_selected(a.selection);
 int index=old==GTK_INVALID_LIST_POSITION?0:CLAMP((int)old+delta,0,(int)count-1);
 gtk_single_selection_set_selected(a.selection,index);
 gtk_list_view_scroll_to(GTK_LIST_VIEW(a.list),index,keep_search?GTK_LIST_SCROLL_NONE:GTK_LIST_SCROLL_FOCUS,NULL);
}
static gboolean keyboard(GtkEventControllerKey *controller,guint key,guint code,GdkModifierType state,gpointer unused){(void)controller;(void)code;(void)unused;if(key==GDK_KEY_Escape){gtk_window_close(a.win);return TRUE;}if((state&GDK_CONTROL_MASK)&&key==GDK_KEY_n){if(CONTACTS)edit_contact(NULL,GINT_TO_POINTER(1));else edit_event(NULL,GINT_TO_POINTER(1));return TRUE;}if(CONTACTS&&(state&gtk_accelerator_get_default_mod_mask())==GDK_CONTROL_MASK&&(key==GDK_KEY_j||key==GDK_KEY_k)){contact_move(key==GDK_KEY_j?1:-1,TRUE);return TRUE;}GtkWidget *focus=gtk_window_get_focus(a.win);if(CONTACTS&&focus&&a.search&&(focus==a.search||gtk_widget_is_ancestor(focus,a.search))&&(key==GDK_KEY_Return||key==GDK_KEY_KP_Enter)){gtk_widget_grab_focus(a.list);return TRUE;}for(GtkWidget *w=focus;w;w=gtk_widget_get_parent(w))if(GTK_IS_EDITABLE(w)||GTK_IS_TEXT_VIEW(w)){if(key==GDK_KEY_Escape){gtk_widget_grab_focus(CONTACTS?a.list:a.calendar);return TRUE;}return FALSE;}

    int control_result=simple_control_key(a.win,key,state);
    if(control_result>=0)return control_result;
 const char *group=CONTACTS?"contacts":"calendar";
 if(match(group,"quit","q",key,state)){gtk_window_close(a.win);return TRUE;}
 if(match(group,"new","n",key,state)){if(CONTACTS)edit_contact(NULL,GINT_TO_POINTER(1));else edit_event(NULL,GINT_TO_POINTER(1));return TRUE;}
 if(match(group,"edit","e",key,state)){if(CONTACTS)edit_contact(NULL,NULL);else edit_event(NULL,NULL);return TRUE;}
 if(match(group,"delete","x",key,state)){remove_selected(NULL,NULL);return TRUE;}
 if(match(group,"sync","s",key,state)){sync_now(NULL,NULL);return TRUE;}
 if(match(group,"accounts","c",key,state)){show_accounts(NULL,NULL);return TRUE;}
 if(!CONTACTS&&match("navigation","activate","Return,KP_Enter",key,state)&&focus&&gtk_widget_has_css_class(focus,"card")){show_details(NULL,NULL);return TRUE;}
 if(match(group,"help","question",key,state)){show_help();return TRUE;}
 if(CONTACTS){
  if(match(group,"search","slash",key,state)){gtk_widget_grab_focus(a.search);return TRUE;}
  if(match(group,"export","b",key,state)){export_contacts(NULL,NULL);return TRUE;}
  int delta=match("navigation","down","j,Down",key,state)?1:match("navigation","up","k,Up",key,state)?-1:0;
  if(delta){contact_move(delta,FALSE);return TRUE;}
  if(match("navigation","left","h,Left",key,state)){gtk_widget_grab_focus(a.list);return TRUE;}
  if(match("navigation","right","l,Right",key,state)){gtk_widget_child_focus(a.detail,GTK_DIR_TAB_FORWARD);return TRUE;}
 }else{
  const char *keys[]={"day_left","day_right","day_up","day_down","previous_month","next_month"};const char *defs[]={"h,Left","l,Right","k,Up","j,Down","H","L"};int deltas[]={-1,1,-7,7,-1,1};for(int i=0;i<6;i++)if(match(group,keys[i],defs[i],key,state)){move_day(deltas[i],i>=4);return TRUE;}
  if(match(group,"today","t,g,Home",key,state)){today_click(NULL,NULL);return TRUE;}
  if(match(group,"agenda","a",key,state)){gtk_drop_down_set_selected(GTK_DROP_DOWN(a.mode),!gtk_drop_down_get_selected(GTK_DROP_DOWN(a.mode)));return TRUE;}
  int delta=match(group,"next_event","J",key,state)?1:match(group,"previous_event","K",key,state)?-1:0;if(delta){if(a.cards->len){a.event_index=CLAMP((int)a.event_index+delta,0,(int)a.cards->len-1);highlight_events();gtk_widget_grab_focus(g_ptr_array_index(a.cards,a.event_index));}return TRUE;}
 }return FALSE;
}
static void load_keys(GKeyFile *keys,const char *dir,const char *name){char *file=g_build_filename(dir,name,NULL);g_key_file_load_from_file(keys,file,G_KEY_FILE_NONE,NULL);g_free(file);}
static gboolean poll_data(gpointer unused){(void)unused;load_styles();simple_daylight_art_update(&a.empty_art);if(!a.busy&&!a.editor)reload_view();return G_SOURCE_CONTINUE;}
static gboolean smoke_exit(gpointer unused){(void)unused;gtk_window_close(a.win);return G_SOURCE_REMOVE;}
static void load_styles(void){
 if(!app_css){app_css=gtk_css_provider_new();override_css=gtk_css_provider_new();gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(app_css),802);gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(override_css),803);}
 char *style=path(a.dir,"style.css");simple_theme_load(app_css,style);GtkCssProvider *shared=g_object_get_data(G_OBJECT(gdk_display_get_default()),"simple-shared-theme");gtk_style_context_remove_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(shared));gtk_style_context_add_provider_for_display(gdk_display_get_default(),GTK_STYLE_PROVIDER(shared),801);g_free(style);style=g_build_filename(g_get_user_config_dir(),APPNAME,"style.css",NULL);if(g_file_test(style,G_FILE_TEST_IS_REGULAR))gtk_css_provider_load_from_path(override_css,style);else gtk_css_provider_load_from_string(override_css,"");g_free(style);
}
static void activate(GtkApplication *app,gpointer unused){(void)unused;if(a.win){gtk_window_present(a.win);return;}
 const char *root=g_getenv("SIMPLE_ORGANIZER_SOURCE_ROOT");
 a.dir=root?g_build_filename(root,APPNAME,NULL):simple_resource_dir(CONTACTS?"SIMPLECONTACTS_SOURCE":"SIMPLECALENDAR_SOURCE",APPNAME,"bridge.py");
 char *common=g_getenv("SIMPLE_COMMON_DIR")?g_strdup(g_getenv("SIMPLE_COMMON_DIR")):g_build_filename(a.dir,"../simple-common",NULL);
 a.helper=g_build_filename(common,"organizer-helper.py",NULL);g_free(common);
 const char *python=g_getenv("SIMPLE_CALENDAR_PYTHON");a.python=!CONTACTS&&python?g_strdup(python):CONTACTS?g_strdup("python3"):g_build_filename(g_get_user_data_dir(),"simple-calendar-runtime/bin/python",NULL);
 if(!CONTACTS&&!python&&!g_file_test(a.python,G_FILE_TEST_IS_EXECUTABLE)){g_free(a.python);a.python=g_strdup("python3");}
 a.config=g_key_file_new();a.keys=g_key_file_new();a.global_keys=g_key_file_new();char *conf=g_build_filename(g_get_user_config_dir(),APPNAME,NULL),*global=g_build_filename(g_get_user_config_dir(),"simple",NULL);load_keys(a.config,conf,"config.ini");load_keys(a.keys,conf,"keys.ini");load_keys(a.global_keys,global,"keys.ini");
 a.win=GTK_WINDOW(gtk_application_window_new(app));gtk_window_set_title(a.win,TITLE);gtk_window_set_default_size(a.win,number("width",CONTACTS?850:860,CONTACTS?500:860,2000),number("height",CONTACTS?560:520,350,1600));gtk_widget_add_css_class(GTK_WIDGET(a.win),CLASS);
 load_styles();g_free(conf);g_free(global);
 GtkWidget *outer=box(TRUE,10);margin(outer,12);gtk_window_set_child(a.win,outer);GtkWidget *toolbar=box(FALSE,6),*title=label(TITLE,"heading");gtk_widget_set_hexpand(title,TRUE);append(toolbar,title);append(outer,toolbar);
 if(!CONTACTS){const char *modes[]={"Selected day","Next 30 days",NULL};a.mode=gtk_drop_down_new_from_strings(modes);char *view=g_key_file_get_string(a.config,"calendar","view",NULL);if(view&&strcmp(view,"day"))gtk_drop_down_set_selected(GTK_DROP_DOWN(a.mode),1);g_free(view);append(toolbar,a.mode);append(toolbar,button("Today",G_CALLBACK(today_click),NULL));}
 append(toolbar,button("Sync",G_CALLBACK(sync_now),NULL));append(toolbar,button("Accounts",G_CALLBACK(show_accounts),NULL));if(CONTACTS)append(toolbar,button("Export",G_CALLBACK(export_contacts),NULL));GtkWidget *add=button(CONTACTS?"+ Contact":"+ Event",CONTACTS?G_CALLBACK(edit_contact):G_CALLBACK(edit_event),GINT_TO_POINTER(1));gtk_widget_add_css_class(add,"primary");append(toolbar,add);a.status=label("Loading…","muted");append(outer,a.status);
 if(CONTACTS){GtkWidget *columns=box(FALSE,14),*left=box(TRUE,8);gtk_widget_set_size_request(left,270,-1);append(outer,columns);gtk_widget_set_vexpand(columns,TRUE);append(columns,left);a.search=gtk_search_entry_new();g_object_set(a.search,"placeholder-text","Search name, phone or email · /",NULL);append(left,a.search);a.selection=gtk_single_selection_new(NULL);GtkListItemFactory *factory=gtk_signal_list_item_factory_new();g_signal_connect(factory,"setup",G_CALLBACK(factory_setup),NULL);g_signal_connect(factory,"bind",G_CALLBACK(factory_bind),NULL);a.list=gtk_list_view_new(GTK_SELECTION_MODEL(a.selection),factory);gtk_widget_add_css_class(a.list,"contact-list");GtkWidget *viewport=scroll(a.list);gtk_widget_add_css_class(viewport,"contact-list-frame");append(left,viewport);a.detail=box(TRUE,10);GtkWidget *right=scroll(a.detail);gtk_widget_set_hexpand(right,TRUE);append(columns,right);g_signal_connect(a.selection,"notify::selected",G_CALLBACK(contact_selected),NULL);g_signal_connect(a.search,"search-changed",G_CALLBACK(search_changed),NULL);append(outer,label("j/k: contacts · h/l: focus · /: search · n: new · e: edit · x: delete · s: sync · c: accounts · b: export","muted"));
 }else{
  if(!a.day)a.day=today();a.cards=g_ptr_array_new();a.card_size=gtk_size_group_new(GTK_SIZE_GROUP_VERTICAL);a.legend_size=gtk_size_group_new(GTK_SIZE_GROUP_VERTICAL);a.action_size=gtk_size_group_new(GTK_SIZE_GROUP_VERTICAL);
  GtkWidget *head=box(FALSE,12);gtk_box_set_homogeneous(GTK_BOX(head),TRUE);a.heading=label("","heading");a.empty_caption=label("Nothing is scheduled","heading");append(head,a.heading);append(head,a.empty_caption);append(outer,head);
  GtkWidget *columns=box(FALSE,12),*left=box(TRUE,6);gtk_box_set_homogeneous(GTK_BOX(columns),TRUE);append(outer,columns);gtk_widget_set_vexpand(columns,TRUE);append(columns,left);a.calendar=gtk_calendar_new();gtk_widget_set_valign(a.calendar,GTK_ALIGN_START);gtk_size_group_add_widget(a.card_size,a.calendar);append(left,a.calendar);GtkWidget *legend=label(show_report?"Orange ● full moon · Red ● next report":"Orange ● full moon","muted");a.report_legend=legend;gtk_size_group_add_widget(a.legend_size,legend);append(left,legend);a.report_button=button("90-day report",G_CALLBACK(edit_event),GINT_TO_POINTER(2));gtk_widget_set_margin_top(a.report_button,12);gtk_size_group_add_widget(a.action_size,a.report_button);append(left,a.report_button);gtk_widget_set_visible(a.report_button,show_report);a.events=box(TRUE,8);append(columns,scroll(a.events));a.local=gtk_check_button_new_with_label("Local holidays, full moons & parties");gtk_check_button_set_active(GTK_CHECK_BUTTON(a.local),TRUE);append(outer,a.local);append(outer,label("h/j/k/l: day · H/L: month · J/K: events · n/Ctrl+N: new · e: edit · Ctrl+S: save in editor · t: today · ?: keys","muted"));
  GDateTime *d=parseday(a.day);gtk_calendar_select_day(GTK_CALENDAR(a.calendar),d);g_date_time_unref(d);g_signal_connect(a.calendar,"day-selected",G_CALLBACK(calendar_changed),NULL);g_signal_connect(a.calendar,"next-month",G_CALLBACK(calendar_changed),NULL);g_signal_connect(a.calendar,"prev-month",G_CALLBACK(calendar_changed),NULL);g_signal_connect(a.calendar,"next-year",G_CALLBACK(calendar_changed),NULL);g_signal_connect(a.calendar,"prev-year",G_CALLBACK(calendar_changed),NULL);g_signal_connect(a.mode,"notify::selected",G_CALLBACK(mode_changed),NULL);g_signal_connect(a.local,"toggled",G_CALLBACK(local_changed),NULL);
 }
 GtkEventController *keys=gtk_event_controller_key_new();gtk_event_controller_set_propagation_phase(keys,GTK_PHASE_CAPTURE);g_signal_connect(keys,"key-pressed",G_CALLBACK(keyboard),NULL);gtk_widget_add_controller(GTK_WIDGET(a.win),keys);a.initial=TRUE;fit_content();gtk_window_present(a.win);gtk_widget_grab_focus(CONTACTS?a.list:a.calendar);reload_view();g_timeout_add_seconds(number("refresh_seconds",CONTACTS?30:15,5,3600),poll_data,NULL);if(g_getenv("SIMPLE_ORGANIZER_SMOKE"))g_timeout_add_seconds(5,smoke_exit,NULL);
}
static int command_line(GApplication *app,GApplicationCommandLine *command,gpointer unused){(void)unused;int argc;char **argv=g_application_command_line_get_arguments(command,&argc);char *requested=NULL;gboolean requested_report=FALSE;
 for(int i=1;i<argc;i++){if(!strcmp(argv[i],"--day")&&i+1<argc){GDateTime *d=parseday(argv[++i]);if(!d){g_application_command_line_printerr(command,"Invalid date\n");g_strfreev(argv);return 2;}g_free(requested);requested=g_date_time_format(d,"%F");g_date_time_unref(d);}else if(!CONTACTS&&!strcmp(argv[i],"--show-90-day-report")){requested_report=TRUE;}else if(!strcmp(argv[i],"--help")){g_application_command_line_print(command,"%s native GTK frontend%s\n",TITLE,CONTACTS?"":" [--day YYYY-MM-DD] [--show-90-day-report]");g_strfreev(argv);g_free(requested);return 0;}else{g_application_command_line_printerr(command,"Unknown option: %s\n",argv[i]);g_strfreev(argv);g_free(requested);return 2;}}
 show_report=requested_report;
 if(requested&&!a.win){g_free(a.day);a.day=g_strdup(requested);}g_application_activate(app);if(!CONTACTS&&a.report_button){gtk_widget_set_visible(a.report_button,show_report);gtk_label_set_text(GTK_LABEL(a.report_legend),show_report?"Orange ● full moon · Red ● next report":"Orange ● full moon");reload_view();}if(requested&&!CONTACTS)go_day(requested);g_free(requested);g_strfreev(argv);return 0;
}
int main(int argc,char **argv){a.app=gtk_application_new(CONTACTS?"space.go7.SimpleContacts":"space.go7.SimpleCalendar",G_APPLICATION_HANDLES_COMMAND_LINE|(g_getenv("SIMPLE_ORGANIZER_SMOKE")?G_APPLICATION_NON_UNIQUE:0));g_signal_connect(a.app,"activate",G_CALLBACK(activate),NULL);g_signal_connect(a.app,"command-line",G_CALLBACK(command_line),NULL);int result=g_application_run(G_APPLICATION(a.app),argc,argv);simple_daylight_art_clear(&a.empty_art);g_object_unref(a.app);return result;}
