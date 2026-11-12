#ifndef DASHBOARD_SETTINGS_H
#define DASHBOARD_SETTINGS_H
#include <gio/gio.h>
#include <json-c/json.h>
#define SIMPLE_MAX_CARDS 4
typedef struct {
    char **zones,**cities,**ids,**labels;
    gsize clocks,markets;
    char *format,*currency,*currency_label,*panel_zone;
    int decimals;
    gboolean show_clocks,show_markets,show_panel_clock;
} DashboardSettings;
extern DashboardSettings dashboard_settings;
gboolean dashboard_settings_load(GKeyFile *file,GError **error);
void simple_market_refresh(void);
json_object *simple_market_read(void);
char *simple_market_price(json_object *prices,int index);
char *simple_market_number(json_object *prices,int index);
void simple_market_stop(void);
#endif

gboolean simple_market_pending(void);
