#include "sp.h"
char *keys_override;
const char *keys_scope;
static const char defaults[] =
  "[navigation]\nup=Up,k,<Control>k\ndown=Down,j,<Control>j\n"
  "left=Left,h,<Control>h\nright=Right,l,<Control>l\n"
  "activate=Return,KP_Enter\ncancel=Escape\n"
  "page_up=Page_Up,<Control>u\npage_down=Page_Down,<Control>d\n"
  "[interaction]\nvim_navigation=true\n";
static gboolean merge_keys(GKeyFile *dest, const char *path, gboolean required) {
  if (!g_file_test(path, G_FILE_TEST_IS_REGULAR) && !required) return TRUE;
  GKeyFile *src = g_key_file_new();
  GError *error = NULL;
  if (!g_key_file_load_from_file(src, path, G_KEY_FILE_NONE, &error)) {
    fail("Key bindings: %s: %s", path, error->message);
    g_error_free(error);g_key_file_unref(src);return FALSE;
  }
  gsize count;
  char **names = g_key_file_get_keys(src, "navigation", &count, NULL);
  for (gsize i=0; names && i<count; i++) {
    if (!g_key_file_has_key(dest,"navigation",names[i],NULL)) {
      fail("Unknown navigation action: %s",names[i]);break;
    }
    char *value = g_key_file_get_string(src,"navigation",names[i],NULL);
    char **parts = g_strsplit(value,",",-1);
    for (int j=0;parts[j];j++) {
      char *binding = g_strstrip(parts[j]);
      guint key;GdkModifierType mods;
      if (*binding && !gtk_accelerator_parse(binding,&key,&mods))
        fail("Invalid navigation key: %s",binding);
    }
    g_strfreev(parts);
    g_key_file_set_string(dest,"navigation",names[i],value);
    g_free(value);
  }
  const char *interaction[]={"vim_navigation","start_in_search","escape_closes"};
  for(guint i=0;i<G_N_ELEMENTS(interaction);i++)if(g_key_file_has_key(src,"interaction",interaction[i],NULL)) {
    GError *error=NULL;gboolean enabled=g_key_file_get_boolean(src,"interaction",interaction[i],&error);
    if(error){fail("Key bindings: %s: %s",path,error->message);g_error_free(error);}
    else g_key_file_set_boolean(dest,"interaction",interaction[i],enabled);
  }
  g_strfreev(names);g_key_file_unref(src);return !last_error;
}
GKeyFile *navigation_load(const char *scope, const char *override) {
  GKeyFile *keys=g_key_file_new();
  g_key_file_load_from_data(keys,defaults,-1,G_KEY_FILE_NONE,NULL);
  const char *root=g_get_user_config_dir();
  char *path=g_build_filename(root,"simple","keys.ini",NULL);
  merge_keys(keys,path,FALSE);g_free(path);
  path=g_build_filename(root,"simplepicker","keys.ini",NULL);
  merge_keys(keys,path,FALSE);g_free(path);
  if (scope && *scope) {
    path=g_build_filename(root,"simplepicker",scope,"keys.ini",NULL);
    merge_keys(keys,path,FALSE);g_free(path);
  }
  if (override && *override) {
    path=expand(override,NULL);merge_keys(keys,path,TRUE);g_free(path);
  }
  return keys;
}
gboolean navigation_match(GKeyFile *keys,const char *action,guint key,GdkModifierType mods,gboolean editing) {
  if (!keys) return FALSE;
  mods &= GDK_SHIFT_MASK|GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK|GDK_META_MASK;
  if (editing && !(mods & (GDK_CONTROL_MASK|GDK_ALT_MASK|GDK_SUPER_MASK|GDK_META_MASK)) &&
      (gdk_keyval_to_unicode(key)>=32 || key==GDK_KEY_Left || key==GDK_KEY_Right || key==GDK_KEY_Home || key==GDK_KEY_End)) return FALSE;
  char *value=g_key_file_get_string(keys,"navigation",action,NULL);
  char **parts=g_strsplit(value ? value : "",",",-1);
  gboolean found=FALSE;
  for (int i=0;parts[i];i++) {
    guint wanted;GdkModifierType mask;
    if (gtk_accelerator_parse(g_strstrip(parts[i]),&wanted,&mask) &&
        gdk_keyval_to_lower(key)==gdk_keyval_to_lower(wanted) && mods==mask) {found=TRUE;break;}
  }
  g_strfreev(parts);g_free(value);return found;
}

char *navigation_label(GKeyFile *keys,const char *action) {
  char *value=g_key_file_get_string(keys,"navigation",action,NULL);
  char **parts=g_strsplit(value ? value : "",",",-1);
  char *label=g_strdup("Disabled");
  for (int i=0;parts[i];i++) {
    guint key;GdkModifierType mods;
    if (gtk_accelerator_parse(g_strstrip(parts[i]),&key,&mods)) {
      g_free(label);label=gtk_accelerator_get_label(key,mods);
    }
  }
  g_strfreev(parts);g_free(value);return label;
}
