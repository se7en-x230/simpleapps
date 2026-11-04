#ifndef SIMPLE_IMAGES_H
#define SIMPLE_IMAGES_H
#include <glib.h>
#include <json-c/json.h>
static inline char *simple_image_existing(char *path){if(path&&g_file_test(path,G_FILE_TEST_IS_REGULAR))return path;g_free(path);return NULL;}
static inline char *simple_image_default(const char *kind) {
 const char *name=!g_strcmp0(kind,"profile")?"default-avatar.png":"default-idle.png";char *path=NULL;
 const char *override=g_getenv("SIMPLE_IMAGES_DIR");if(override)path=simple_image_existing(g_build_filename(override,name,NULL));
 if(!path)path=simple_image_existing(g_build_filename(g_get_user_data_dir(),"simple/images",name,NULL));
 const char *const *roots=g_get_system_data_dirs();for(int i=0;!path&&roots[i];i++)path=simple_image_existing(g_build_filename(roots[i],"simple/images",name,NULL));
 return path;
}
static inline char *simple_image_resolve(const char *kind) {
 char *root=g_build_filename(g_get_user_config_dir(),"simple",NULL),*file=g_build_filename(root,"images.ini",NULL);
 GKeyFile *config=g_key_file_new();g_key_file_load_from_file(config,file,G_KEY_FILE_NONE,NULL);g_free(file);
 char *selected=g_key_file_get_string(config,"images",kind,NULL),*path=NULL;
 if(selected&&*selected){path=simple_image_existing(g_str_has_prefix(selected,"~/")?g_build_filename(g_get_home_dir(),selected+2,NULL):g_path_is_absolute(selected)?g_strdup(selected):g_build_filename(root,selected,NULL));}g_free(selected);
 GError *error=NULL;gboolean follow=g_key_file_get_boolean(config,"images","use_wallpaper",&error);if(error){follow=TRUE;g_clear_error(&error);}g_key_file_unref(config);g_free(root);
 if(!path&&!g_strcmp0(kind,"idle")&&follow) {
  path=simple_image_existing(g_build_filename(g_get_user_data_dir(),"simplewallpaper/current",NULL));
  char *legacy=g_build_filename(g_get_user_config_dir(),"wallpaper/config.json",NULL);json_object *obj=json_object_from_file(legacy),*mode=NULL;g_free(legacy);
  gboolean daylight=obj&&json_object_object_get_ex(obj,"mode",&mode)&&!g_strcmp0(json_object_get_string(mode),"daylight");if(obj)json_object_put(obj);
  if(!path)path=simple_image_existing(g_build_filename(g_get_user_data_dir(),"wallpaper",daylight?"daylight-current.png":"current.png",NULL));
  if(!path)path=simple_image_existing(g_build_filename(g_get_user_data_dir(),"wallpaper",daylight?"current.png":"daylight-current.png",NULL));
 }
 return path?path:simple_image_default(kind);
}
#endif
