#define _GNU_SOURCE
#include "dashboard-settings.h"
#include <math.h>
#include <sys/stat.h>
#include <string.h>
DashboardSettings dashboard_settings;
static GSubprocess *request;
static char *cache_path;
static gint64 last_attempt;
static char *string_setting(GKeyFile *f,const char *group,const char *key,const char *fallback,GError **e) {
    return g_key_file_has_key(f,group,key,NULL)?g_key_file_get_string(f,group,key,e):g_strdup(fallback);
}
static gboolean bool_setting(GKeyFile *f,const char *group,const char *key,gboolean fallback,GError **e) {
    return g_key_file_has_key(f,group,key,NULL)?g_key_file_get_boolean(f,group,key,e):fallback;
}
static gboolean invalid(GError **e,const char *message) {
    g_set_error_literal(e,G_KEY_FILE_ERROR,G_KEY_FILE_ERROR_INVALID_VALUE,message);return FALSE;
}
static gboolean token(const char *s) {
    if(!s||!*s||strlen(s)>100)return FALSE;
    for(;*s;s++)if(!g_ascii_isalnum(*s)&&*s!='-'&&*s!='_')return FALSE;
    return TRUE;
}
static char **list_setting(GKeyFile *f,const char *group,const char *key,const char *fallback,gsize *count,GError **e) {
    char **list;
    if(g_key_file_has_key(f,group,key,NULL))list=g_key_file_get_string_list(f,group,key,count,e);
    else {list=g_strsplit(fallback,";",-1);*count=g_strv_length(list);}
    if(!list)return NULL;
    if(*count<1||*count>SIMPLE_MAX_CARDS){g_strfreev(list);invalid(e,"Lists must contain 1 to 4 entries; use visibility settings to hide a section.");return NULL;}
    for(gsize i=0;i<*count;i++)if(!*g_strstrip(list[i])){g_strfreev(list);invalid(e,"List entries cannot be empty.");return NULL;}
    return list;
}
gboolean dashboard_settings_load(GKeyFile *f,GError **e) {
    DashboardSettings *s=&dashboard_settings;gsize count;
    s->zones=list_setting(f,"dashboard","clock_zones","Asia/Bangkok;Australia/Sydney;Europe/Berlin;America/Los_Angeles",&s->clocks,e);if(!s->zones)return FALSE;
    s->cities=list_setting(f,"dashboard","clock_labels","Koh Tao;Sydney;Berlin;Los Angeles",&count,e);if(!s->cities)return FALSE;
    if(count!=s->clocks)return invalid(e,"dashboard.clock_labels and clock_zones must have equal lengths.");
    s->ids=list_setting(f,"markets","ids","tether-gold;bitcoin",&s->markets,e);if(!s->ids)return FALSE;
    s->labels=list_setting(f,"markets","labels","GOLD · XAUT;BITCOIN · BTC",&count,e);if(!s->labels)return FALSE;
    if(count!=s->markets)return invalid(e,"markets.labels and ids must have equal lengths.");
    s->currency=string_setting(f,"markets","currency","thb",e);if(!s->currency)return FALSE;
    for(char *p=s->currency;*p;p++)*p=g_ascii_tolower(*p);
    if(!token(s->currency))return invalid(e,"markets.currency must be a CoinGecko currency code.");
    for(gsize i=0;i<s->markets;i++)if(!token(s->ids[i]))return invalid(e,"markets.ids must contain CoinGecko IDs, not ticker symbols or URLs.");
    s->currency_label=g_ascii_strup(s->currency,-1);
    s->panel_zone=string_setting(f,"panel","clock_timezone","",e);if(!s->panel_zone)return FALSE;
    s->format=string_setting(f,"dashboard","clock_format","%H:%M\n%a %d %b · %Z",e);if(!s->format)return FALSE;
    for(gsize i=0;i<s->clocks;i++) {
        GTimeZone *z=g_time_zone_new_identifier(s->zones[i]);if(!z)return invalid(e,"Invalid dashboard clock time zone.");g_time_zone_unref(z);
    }
    if(*s->panel_zone){GTimeZone *z=g_time_zone_new_identifier(s->panel_zone);if(!z)return invalid(e,"Invalid panel.clock_timezone.");g_time_zone_unref(z);}
    GDateTime *now=g_date_time_new_now_utc();char *formatted=g_date_time_format(now,s->format);g_date_time_unref(now);
    if(!formatted||!*formatted){g_free(formatted);return invalid(e,"Invalid dashboard.clock_format.");}g_free(formatted);
    s->show_clocks=bool_setting(f,"dashboard","clocks",TRUE,e);if(e&&*e)return FALSE;
    s->show_markets=bool_setting(f,"dashboard","markets",TRUE,e);if(e&&*e)return FALSE;
    s->show_panel_clock=bool_setting(f,"panel","clock",TRUE,e);if(e&&*e)return FALSE;
    s->decimals=g_key_file_has_key(f,"markets","decimals",NULL)?g_key_file_get_integer(f,"markets","decimals",e):0;if(e&&*e)return FALSE;
    if(s->decimals<0||s->decimals>8)return invalid(e,"markets.decimals must be between 0 and 8.");
    char *ids=g_strjoinv(",",s->ids),*key=g_strdup_printf("%s:%s",ids,s->currency),*hash=g_compute_checksum_for_string(G_CHECKSUM_SHA256,key,-1);
    char *filename=g_strconcat(hash,".json",NULL);cache_path=g_build_filename(g_get_user_cache_dir(),"simplepanel","markets",filename,NULL);
    g_free(filename);g_free(hash);g_free(key);g_free(ids);return TRUE;
}
static gboolean numeric(json_object *o) {return o&&(json_object_is_type(o,json_type_double)||json_object_is_type(o,json_type_int))&&isfinite(json_object_get_double(o));}
static gboolean valid_prices(json_object *o) {
    if(!o||!json_object_is_type(o,json_type_object))return FALSE;
    for(gsize i=0;i<dashboard_settings.markets;i++) {
        json_object *coin=NULL,*price=NULL;
        json_object_object_get_ex(o,dashboard_settings.ids[i],&coin);
        if(coin)json_object_object_get_ex(coin,dashboard_settings.currency,&price);
        if(!numeric(price)||json_object_get_double(price)<=0)return FALSE;
    }
    return TRUE;
}
json_object *simple_market_read(void) {return cache_path?json_object_from_file(cache_path):NULL;}
static char *market_text(json_object *prices,int index,gboolean labelled) {
    json_object *coin=NULL,*price=NULL;
    if(prices)json_object_object_get_ex(prices,dashboard_settings.ids[index],&coin);
    if(coin)json_object_object_get_ex(coin,dashboard_settings.currency,&price);
    if(!numeric(price)||json_object_get_double(price)<=0)return g_strdup(labelled?"Price unavailable":"--");
    return labelled?g_strdup_printf("%.*f %s",dashboard_settings.decimals,json_object_get_double(price),dashboard_settings.currency_label):g_strdup_printf("%.*f",dashboard_settings.decimals,json_object_get_double(price));
}
char *simple_market_price(json_object *prices,int index) {return market_text(prices,index,TRUE);}
char *simple_market_number(json_object *prices,int index) {return market_text(prices,index,FALSE);}

static void received(GObject *source,GAsyncResult *result,gpointer data) {
    char *out=NULL;GError *error=NULL;
    if(g_subprocess_communicate_utf8_finish(G_SUBPROCESS(source),result,&out,NULL,&error)&&g_subprocess_get_successful(G_SUBPROCESS(source))) {
        json_object *prices=out?json_tokener_parse(out):NULL;
        if(valid_prices(prices)) {
            char *dir=g_path_get_dirname(cache_path);
            if(!g_mkdir_with_parents(dir,0700))g_file_set_contents(cache_path,out,-1,NULL);
            g_free(dir);
        }
        if(prices)json_object_put(prices);
    }
    g_clear_error(&error);g_free(out);g_clear_object(&request);
}
void simple_market_refresh(void) {
    if(request||!cache_path)return;
    gint64 now=g_get_real_time()/G_USEC_PER_SEC;
    if(last_attempt&&now-last_attempt<300)return;
    struct stat st;
    if(!stat(cache_path,&st)&&now>=st.st_mtime&&now-st.st_mtime<3600) {
        json_object *cached=simple_market_read();gboolean valid=valid_prices(cached);if(cached)json_object_put(cached);if(valid)return;
    }
    last_attempt=now;
    char *ids=g_strjoinv(",",dashboard_settings.ids);
    char *url=g_strdup_printf("https://api.coingecko.com/api/v3/simple/price?ids=%s&vs_currencies=%s&include_24hr_change=true&include_last_updated_at=true",ids,dashboard_settings.currency);
    request=g_subprocess_new(G_SUBPROCESS_FLAGS_STDOUT_PIPE|G_SUBPROCESS_FLAGS_STDERR_SILENCE,NULL,"curl","--fail","--silent","--connect-timeout","2","--max-time","5","--max-filesize","1048576",url,NULL);
    if(request)g_subprocess_communicate_utf8_async(request,NULL,NULL,received,NULL);
    g_free(ids);g_free(url);
}
void simple_market_stop(void) {if(request)g_subprocess_force_exit(request);}
