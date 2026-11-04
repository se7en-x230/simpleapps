#ifndef SIMPLE_SYSTEM_INFO_H
#define SIMPLE_SYSTEM_INFO_H
#include <gio/gio.h>
#include <json-c/json.h>
typedef struct { char *desktop,*terminal,*packages,*init; } SimpleSystemInfo;
static inline void simple_system_clear(SimpleSystemInfo *s) {
  g_free(s->desktop);g_free(s->terminal);g_free(s->packages);g_free(s->init);
}
static inline const char *simple_system_string(json_object *o,const char *key) {
  json_object *v=NULL;
  return json_object_object_get_ex(o,key,&v)&&json_object_is_type(v,json_type_string)?json_object_get_string(v):"";
}
/* Called only from the snapshot worker. Cache expensive package enumeration. */
static inline SimpleSystemInfo simple_system_read(GCancellable *cancel) {
  static GMutex mutex;static SimpleSystemInfo cache;static gint64 updated;
  g_mutex_lock(&mutex);
  gint64 now=g_get_monotonic_time();
  if(!updated || now-updated>60000000) {
    GSubprocess *p=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_SILENCE,NULL,
      "fastfetch","--format","json","--structure","DE:WM:Terminal:Packages:InitSystem",NULL);
    char *text=NULL;json_object *root=NULL;
    if(p) {
      if(g_subprocess_communicate_utf8(p,NULL,cancel,&text,NULL,NULL))root=json_tokener_parse(text?text:"");
      else g_subprocess_force_exit(p);
      g_object_unref(p);g_free(text);
    }
    if(root && json_object_is_type(root,json_type_array)) {
      simple_system_clear(&cache);cache=(SimpleSystemInfo){0};
      char *de=NULL,*wm=NULL;
      for(size_t i=0;i<json_object_array_length(root);i++) {
        json_object *module=json_object_array_get_idx(root,i),*r=NULL;
        const char *type=simple_system_string(module,"type");
        if(!json_object_object_get_ex(module,"result",&r))continue;
        const char *pretty=simple_system_string(r,"prettyName");
        if(!strcmp(type,"DE"))de=g_strdup(pretty);
        else if(!strcmp(type,"WM")) {
          const char *protocol=simple_system_string(r,"protocolName");
          wm=g_strdup_printf("%s%s%s",pretty,*protocol?" · ":"",protocol);
        } else if(!strcmp(type,"Terminal")) {
          const char *version=simple_system_string(r,"version");
          if(*pretty)cache.terminal=g_strdup_printf("%s%s%s",pretty,*version?" ":"",version);
        } else if(!strcmp(type,"InitSystem")) {
          const char *name=simple_system_string(r,"name"),*version=simple_system_string(r,"version");
          if(*name)cache.init=g_strdup_printf("%s%s%s",name,*version?" ":"",version);
        } else if(!strcmp(type,"Packages")) {
          GString *counts=g_string_new(NULL);
          json_object_object_foreach(r,key,value) {
            if(strcmp(key,"all") && json_object_is_type(value,json_type_int) && json_object_get_int64(value)>0)
              g_string_append_printf(counts,"%s%lld (%s)",counts->len?" · ":"",(long long)json_object_get_int64(value),key);
          }
          cache.packages=g_string_free(counts,FALSE);
        }
      }
      cache.desktop=g_strdup_printf("%s%s%s",de?de:"",de&&wm?" / ":"",wm?wm:"");
      g_free(de);g_free(wm);
    }
    if(root)json_object_put(root);
    updated=now;
  }
  const char *desktop=g_getenv("XDG_CURRENT_DESKTOP"),*terminal=g_getenv("TERMINAL");
  /* A GUI has no parent terminal: show the configured desktop terminal. */
  char *configured=NULL;
  if(!terminal || !*terminal) {
    static char *selected;static gint64 selected_at;
    if(!selected_at||now-selected_at>60000000) {
      GSubprocess *resolver=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_SILENCE,NULL,"simple-open","--command","terminal",NULL);
      char *raw=NULL;json_object *command=NULL;
      if(resolver){if(g_subprocess_communicate_utf8(resolver,NULL,cancel,&raw,NULL,NULL))command=json_tokener_parse(raw?raw:"");g_object_unref(resolver);}
      g_free(selected);selected=NULL;
      if(command&&json_object_is_type(command,json_type_array)&&json_object_array_length(command)) {
        json_object *first=json_object_array_get_idx(command,0);if(json_object_is_type(first,json_type_string))selected=g_strdup(json_object_get_string(first));
      }
      if(command)json_object_put(command);
      g_free(raw);selected_at=now;
    }
    configured=g_strdup(selected);
    terminal=configured;
  }
  SimpleSystemInfo result={
    g_strdup(cache.desktop&&*cache.desktop?cache.desktop:desktop?desktop:"Unavailable"),
    g_strdup(terminal&&*terminal?terminal:cache.terminal?cache.terminal:"Unavailable"),
    g_strdup(cache.packages&&*cache.packages?cache.packages:"Unavailable"),
    g_strdup(cache.init?cache.init:"Unavailable")};
  g_free(configured);g_mutex_unlock(&mutex);return result;
}
#endif
