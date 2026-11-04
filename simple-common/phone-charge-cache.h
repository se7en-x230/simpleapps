#ifndef SIMPLEPANEL_PHONE_CHARGE_CACHE_H
#define SIMPLEPANEL_PHONE_CHARGE_CACHE_H
#include <glib.h>
#include "phone-charge.h"

/* Session-local snapshot lets a newly opened dashboard reuse panel readings. */
static inline void phone_charge_publish(const PhoneChargeEstimate *e,
                                        const char *device,int charge,gboolean charging) {
    char *path=g_build_filename(g_get_user_runtime_dir(),"simplepanel-phone-charge",NULL);
    GVariant *v=g_variant_ref_sink(g_variant_new("(sxibidd)",device?device:"",
        g_get_monotonic_time(),charge,charging,(int)e->speed,e->per_minute,e->observed_seconds));
    char *text=g_variant_print(v,TRUE);
    g_file_set_contents(path,text,-1,NULL);
    g_free(text);g_variant_unref(v);g_free(path);
}
static inline gboolean phone_charge_snapshot(PhoneChargeEstimate *e,
                                             const char *device,int charge,gboolean charging) {
    char *path=g_build_filename(g_get_user_runtime_dir(),"simplepanel-phone-charge",NULL),*text=NULL;
    gboolean ok=FALSE;
    if(g_file_get_contents(path,&text,NULL,NULL)) {
        GVariant *v=g_variant_parse(G_VARIANT_TYPE("(sxibidd)"),text,NULL,NULL,NULL);
        if(v) {
            const char *id;gint64 time;int level,speed;gboolean plugged;double rate,observed;
            g_variant_get(v,"(&sxibidd)",&id,&time,&level,&plugged,&speed,&rate,&observed);
            gint64 age=g_get_monotonic_time()-time;
            if(!g_strcmp0(id,device)&&level==charge&&plugged==charging&&age>=0&&age<90000000
               &&speed>=PHONE_CHARGE_NONE&&speed<=PHONE_CHARGE_FULL) {
                e->speed=speed;e->per_minute=rate;e->observed_seconds=observed;ok=TRUE;
            }
            g_variant_unref(v);
        }
    }
    g_free(text);g_free(path);return ok;
}
/* One presentation for the panel, music dashboard and lock screen. */
static inline char *phone_charge_label(int charge,PhoneChargeSpeed speed) {
    return charge<0?g_strdup("Phone · disconnected"):
        g_strdup_printf("Phone %d%%%s",charge,phone_charge_icon(speed));
}
static inline char *phone_charge_tooltip(int charge,gboolean charging,const PhoneChargeEstimate *estimate) {
    if(charge<0)return g_strdup("Phone disconnected");
    PhoneChargeSpeed speed=estimate->speed;
            const char *state=speed==PHONE_CHARGE_LEARNING?"Charging — estimating speed (about 1 minute)"
                :speed==PHONE_CHARGE_SLOW?"Estimated slow charging"
                :speed==PHONE_CHARGE_NORMAL?"Estimated normal charging"
                :speed==PHONE_CHARGE_RAPID?"Estimated rapid charging"
                :speed==PHONE_CHARGE_FULL?"Fully charged":"Not charging";
            GString *tip=g_string_new(NULL);
            g_string_append_printf(tip,"Phone %d%% · %s",charge,state);
            if(speed>=PHONE_CHARGE_SLOW&&speed<=PHONE_CHARGE_RAPID) {
                g_string_append_printf(tip,"\nNet battery change: %+.2f percentage points/min"
                    "\nEstimated from recent battery levels, not measured charger power."
                    "\nPhone use and battery temperature affect the result.",estimate->per_minute);
                if(estimate->observed_seconds<300)
                    g_string_append(tip,"\nProvisional first readings — the icon adjusts as more readings arrive.");
            }
            if(charging&&charge>=80&&charge<100)
                g_string_append(tip,"\nCharging usually slows as the battery fills.");
    return g_string_free(tip,FALSE);
}

#endif
