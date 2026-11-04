#ifndef SIMPLE_PATHS_H
#define SIMPLE_PATHS_H
#include <glib.h>
static inline char *simple_resource_dir(const char *override,const char *app,const char *marker) {
 const char *value=g_getenv(override);if(value&&*value)return g_strdup(value);
 char *exe=g_file_read_link("/proc/self/exe",NULL),*dir=exe?g_path_get_dirname(exe):g_get_current_dir();g_free(exe);
 char *paths[]={g_strdup(dir),g_build_filename(dir,"../share",app,NULL),g_build_filename(g_get_user_data_dir(),app,NULL),g_build_filename(dir,"../src",app,NULL),g_build_filename(g_get_home_dir(),".local/src",app,NULL)};
 char *result=NULL;for(guint i=0;i<G_N_ELEMENTS(paths);i++){char *p=g_build_filename(paths[i],marker,NULL);if(!result&&g_file_test(p,G_FILE_TEST_IS_REGULAR))result=g_canonicalize_filename(paths[i],NULL);g_free(p);}
 if(!result){result=g_strdup(paths[2]);}
 for(guint i=0;i<G_N_ELEMENTS(paths);i++){g_free(paths[i]);}
 g_free(dir);return result;
}
/* Public command first; old user scripts remain a compatibility fallback. */
static inline char *simple_control(const char *name,const char *legacy) {
 char *found=g_find_program_in_path(name);if(found)return found;
 return g_build_filename(g_get_user_config_dir(),legacy,NULL);
}
#endif
