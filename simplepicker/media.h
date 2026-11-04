#pragma once
#include <glib.h>
/* MPRIS contentCreated carries the media release date. Do not invent a year
 * for streams or players that omit it. Keep all Simple media labels in order. */
static inline char *simple_media_string(GVariant *meta,const char *key) {
  const char *value="";g_variant_lookup(meta,key,"&s",&value);return g_strdup(value);
}
static inline char *simple_media_year(GVariant *meta) {
  char *date=simple_media_string(meta,"xesam:contentCreated");g_strstrip(date);
  gboolean valid=strlen(date)>=4;
  for(int i=0;valid && i<4;i++)valid=g_ascii_isdigit(date[i]);
  if(valid && date[4] && g_ascii_isdigit(date[4]))valid=FALSE;
  char *year=valid?g_strndup(date,4):g_strdup("");g_free(date);return year;
}
static inline void simple_media_append(GString *out,const char *text) {
  if(text && *text){if(out->len)g_string_append(out," · ");g_string_append(out,text);}
}
static inline char *simple_media_album(GVariant *meta) {
  char *year=simple_media_year(meta),*album=simple_media_string(meta,"xesam:album");
  GString *out=g_string_new(NULL);simple_media_append(out,year);simple_media_append(out,album);
  g_free(year);g_free(album);return g_string_free(out,FALSE);
}
static inline char *simple_media_line(GVariant *meta) {
  char **artists=NULL;g_variant_lookup(meta,"xesam:artist","^as",&artists);
  char *artist=artists?g_strjoinv(", ",artists):g_strdup("");g_strfreev(artists);
  char *album=simple_media_album(meta),*title=simple_media_string(meta,"xesam:title");
  GString *out=g_string_new(NULL);simple_media_append(out,artist);simple_media_append(out,album);simple_media_append(out,title);
  g_free(artist);g_free(album);g_free(title);return g_string_free(out,FALSE);
}
