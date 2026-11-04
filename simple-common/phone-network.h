#ifndef SIMPLE_PHONE_NETWORK_H
#define SIMPLE_PHONE_NETWORK_H
#include <gio/gio.h>
#include <ifaddrs.h>
#include <net/if.h>
#include <arpa/inet.h>
#include <math.h>
#include <string.h>
#include "phone-charge-cache.h"

typedef struct { char *id, *name; int percent; gboolean charging; } SimplePhone;
typedef struct {
  char id[256]; gboolean charging;
  PhoneChargeEstimate estimate,display;
} SimplePhoneHistory;

static inline GVariant *simple_info_call(GDBusConnection *bus,const char *service,
    const char *path,const char *interface,const char *method,GVariant *args,
    const GVariantType *type,GCancellable *cancel) {
  return g_dbus_connection_call_sync(bus,service,path,interface,method,args,type,
      G_DBUS_CALL_FLAGS_NO_AUTO_START,1000,cancel,NULL);
}
static inline GVariant *simple_info_property(GDBusConnection *bus,const char *service,
    const char *path,const char *interface,const char *property,GCancellable *cancel) {
  GVariant *reply=simple_info_call(bus,service,path,"org.freedesktop.DBus.Properties","Get",
      g_variant_new("(ss)",interface,property),G_VARIANT_TYPE("(v)"),cancel),*value=NULL;
  if(reply){g_variant_get(reply,"(v)",&value);g_variant_unref(reply);}return value;
}
static inline char *simple_network_line(GCancellable *cancel) {
  char *device=NULL,*kind=NULL,*result=NULL;
  const char *service="org.freedesktop.NetworkManager";
  GDBusConnection *bus=g_bus_get_sync(G_BUS_TYPE_SYSTEM,cancel,NULL);
  if(bus) {
    GVariant *primary=simple_info_property(bus,service,"/org/freedesktop/NetworkManager",service,"PrimaryConnection",cancel);
    if(primary && g_variant_is_of_type(primary,G_VARIANT_TYPE_OBJECT_PATH)) {
      const char *path=g_variant_get_string(primary,NULL);
      if(strcmp(path,"/")) {
        GVariant *type=simple_info_property(bus,service,path,"org.freedesktop.NetworkManager.Connection.Active","Type",cancel);
        if(type && g_variant_is_of_type(type,G_VARIANT_TYPE_STRING))kind=g_variant_dup_string(type,NULL);
        g_clear_pointer(&type,g_variant_unref);
        GVariant *devices=simple_info_property(bus,service,path,"org.freedesktop.NetworkManager.Connection.Active","Devices",cancel);
        if(devices && g_variant_is_of_type(devices,G_VARIANT_TYPE("ao")) && g_variant_n_children(devices)) {
          GVariant *first=g_variant_get_child_value(devices,0);
          GVariant *name=simple_info_property(bus,service,g_variant_get_string(first,NULL),"org.freedesktop.NetworkManager.Device","Interface",cancel);
          if(name && g_variant_is_of_type(name,G_VARIANT_TYPE_STRING))device=g_variant_dup_string(name,NULL);
          g_clear_pointer(&name,g_variant_unref);g_variant_unref(first);
        }
        g_clear_pointer(&devices,g_variant_unref);
      }
    }
    g_clear_pointer(&primary,g_variant_unref);g_object_unref(bus);
  }
  struct ifaddrs *ifs=NULL;
  if(getifaddrs(&ifs)==0) {
    for(struct ifaddrs *it=ifs;it;it=it->ifa_next) {
      if(!it->ifa_addr || it->ifa_addr->sa_family!=AF_INET || !(it->ifa_flags&IFF_UP) || (it->ifa_flags&IFF_LOOPBACK))continue;
      if(device && strcmp(device,it->ifa_name))continue;
      char ip[INET_ADDRSTRLEN];struct sockaddr_in *addr=(struct sockaddr_in*)it->ifa_addr;
      if(inet_ntop(AF_INET,&addr->sin_addr,ip,sizeof ip)) {
        const char *label=!g_strcmp0(kind,"802-3-ethernet")?"Wired":!g_strcmp0(kind,"802-11-wireless")?"Wi-Fi":"Network";
        result=g_strdup_printf("%s · %s · %s",label,ip,it->ifa_name);break;
      }
    }
    freeifaddrs(ifs);
  }
  g_free(device);g_free(kind);return result?result:g_strdup("Network · no IPv4 connection");
}
static inline SimplePhone simple_phone_read(GCancellable *cancel) {
  SimplePhone p={.percent=-1};
  GDBusConnection *bus=g_bus_get_sync(G_BUS_TYPE_SESSION,cancel,NULL);
  if(!bus)return p;
  const char *service="org.kde.kdeconnect";
  GVariant *reply=simple_info_call(bus,service,"/modules/kdeconnect","org.kde.kdeconnect.daemon","devices",g_variant_new("(bb)",TRUE,TRUE),G_VARIANT_TYPE("(as)"),cancel);
  if(reply) {
    char **devices=NULL;g_variant_get(reply,"(^as)",&devices);
    for(int i=0;devices && devices[i] && p.percent<0;i++) {
      char *base=g_strdup_printf("/modules/kdeconnect/devices/%s",devices[i]);
      char *path=g_strconcat(base,"/battery",NULL);
      GVariant *battery=simple_info_call(bus,service,path,"org.freedesktop.DBus.Properties","GetAll",g_variant_new("(s)","org.kde.kdeconnect.device.battery"),G_VARIANT_TYPE("(a{sv})"),cancel);
      if(battery) {
        GVariant *dict=g_variant_get_child_value(battery,0);gint32 level=-1;gboolean charging=FALSE;
        g_variant_lookup(dict,"charge","i",&level);g_variant_lookup(dict,"isCharging","b",&charging);
        if(level>=0 && level<=100) {
          p.percent=level;p.charging=charging;p.id=g_strdup(devices[i]);
          GVariant *name=simple_info_property(bus,service,base,"org.kde.kdeconnect.device","name",cancel);
          if(name && g_variant_is_of_type(name,G_VARIANT_TYPE_STRING))p.name=g_variant_dup_string(name,NULL);
          g_clear_pointer(&name,g_variant_unref);
        }
        g_variant_unref(dict);g_variant_unref(battery);
      }
      g_free(path);g_free(base);
    }
    g_strfreev(devices);g_variant_unref(reply);
  }
  g_object_unref(bus);return p;
}
static inline void simple_phone_clear(SimplePhone *p) {g_free(p->id);g_free(p->name);}
static inline gboolean simple_phone_rate(SimplePhoneHistory *h,const SimplePhone *p,double now,double *rate) {
  if(p->percent<0 || !p->id) {memset(h,0,sizeof *h);return FALSE;}
  if(strcmp(h->id,p->id) || h->charging!=p->charging) {
    memset(h,0,sizeof *h);g_strlcpy(h->id,p->id,sizeof h->id);h->charging=p->charging;
  }
  PhoneChargeSpeed speed=phone_battery_sample(&h->estimate,p->percent,now);
  if(speed<PHONE_CHARGE_SLOW || speed>PHONE_CHARGE_RAPID)return FALSE;
  *rate=60*h->estimate.per_minute;return TRUE;
}
static inline char *simple_phone_line(SimplePhoneHistory *h,const SimplePhone *p,double now) {
  double rate;simple_phone_rate(h,p,now,&rate);
  h->display=h->estimate;
  if(!p->charging)h->display.speed=PHONE_CHARGE_NONE;
  else if(p->percent==100)h->display.speed=PHONE_CHARGE_FULL;
  /* Use the exact state the panel published, including its learning state. */
  phone_charge_snapshot(&h->display,p->id,p->percent,p->charging);
  return phone_charge_label(p->percent,h->display.speed);
}
#endif
