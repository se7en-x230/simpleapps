#ifndef SIMPLEPANEL_PHONE_CHARGE_H
#define SIMPLEPANEL_PHONE_CHARGE_H

#include <string.h>

typedef enum {
    PHONE_CHARGE_NONE, PHONE_CHARGE_LEARNING, PHONE_CHARGE_SLOW,
    PHONE_CHARGE_NORMAL, PHONE_CHARGE_RAPID, PHONE_CHARGE_FULL
} PhoneChargeSpeed;

typedef struct {
    struct { double time; int percent; } samples[64];
    unsigned count;
    double per_minute;
    double observed_seconds;
    PhoneChargeSpeed speed;
} PhoneChargeEstimate;

static inline void phone_charge_reset(PhoneChargeEstimate *e) {
    memset(e,0,sizeof *e);
}

/* Net battery gain, not charger power. Times must be monotonic seconds.
 * Initial estimate after one minute, refined over a ten-minute rolling window.
 * Early classifications are provisional because levels are rounded to integers.
 * Gaps, unplugging, and implausible jumps invalidate the previous estimate. */
static inline PhoneChargeSpeed phone_battery_sample(PhoneChargeEstimate *e,
                                            int percent, double now) {
    if(percent<0||percent>100) {
        phone_charge_reset(e);
        return e->speed;
    }
    if(e->count) {
        unsigned last=e->count-1;
        double gap=now-e->samples[last].time;
        int change=percent-e->samples[last].percent;
        if(gap<=0||gap>120||change>5||change<-5)
            phone_charge_reset(e);
        else if(gap<15)
            return e->speed;
    }
    while(e->count>1&&e->samples[1].time<=now-600) {
        --e->count;
        memmove(e->samples,e->samples+1,e->count*sizeof e->samples[0]);
    }
    if(e->count==64) {
        --e->count;
        memmove(e->samples,e->samples+1,e->count*sizeof e->samples[0]);
    }
    e->samples[e->count].time=now;
    e->samples[e->count++].percent=percent;
    double elapsed=now-e->samples[0].time;
    e->observed_seconds=elapsed;
    int gain=percent-e->samples[0].percent;
    /* One second of tolerance for asynchronous polling/reply jitter. */
    if(elapsed<59)
        return e->speed=PHONE_CHARGE_LEARNING;
    e->per_minute=60.0*gain/elapsed;
    if(e->per_minute<0.3)
        return e->speed=PHONE_CHARGE_SLOW;
    if(e->per_minute>=0.8)
        return e->speed=PHONE_CHARGE_RAPID;
    return e->speed=PHONE_CHARGE_NORMAL;
}

/* Keep the panel's charging-only display behavior unchanged. */
static inline PhoneChargeSpeed phone_charge_sample(PhoneChargeEstimate *e,
                                            int percent, int charging, double now) {
    if(!charging) { phone_charge_reset(e); return e->speed; }
    if(percent==100) { phone_charge_reset(e); return e->speed=PHONE_CHARGE_FULL; }
    return phone_battery_sample(e,percent,now);
}

static inline const char *phone_charge_icon(PhoneChargeSpeed speed) {
    switch(speed) {
        case PHONE_CHARGE_LEARNING: return " ⚡…";
        case PHONE_CHARGE_SLOW: return " ⚡↓";
        case PHONE_CHARGE_NORMAL: return " ⚡";
        case PHONE_CHARGE_RAPID: return " ⚡↑";
        case PHONE_CHARGE_FULL: return " ⚡✓";
        default: return "";
    }
}
#endif
