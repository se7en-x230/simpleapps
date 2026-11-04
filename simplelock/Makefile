PREFIX ?= $(HOME)/.local
HELPERDIR ?= $(PREFIX)/share/simplelock/scripts
DESTDIR ?=
CC ?= cc
CFLAGS ?= -O2 -g
PKGS = gtk4 gtk4-layer-shell-0 gio-unix-2.0 json-c pam
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
CFLAGS += -Wall -Wextra -Werror -Wno-missing-field-initializers -ffunction-sections -fdata-sections
LDLIBS += $(shell pkg-config --libs $(PKGS))
LDFLAGS += -Wl,--gc-sections
OBJECTS = lock.o auth.o util.o vendor/toml.o
all: simplelock
simplelock: $(OBJECTS)
	$(CC) $(LDFLAGS) $^ -o $@ $(LDLIBS)
lock.o: lock.c view.c fit.c lock.h lock.h auth.h
$(OBJECTS): lock.h
install: simplelock
	install -Dm755 idle "$(DESTDIR)$(HELPERDIR)/idle"
	install -Dm755 simplelock "$(DESTDIR)$(PREFIX)/bin/simplelock"
	install -Dm644 lock.toml "$(DESTDIR)$(PREFIX)/share/simplelock/lock.toml"
clean:
	rm -f $(OBJECTS) simplelock simplelock-test auth-check
simplelock-test: lock.c auth.c util.c vendor/toml.c view.c fit.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -DSIMPLELOCK_TEST lock.c auth.c util.c vendor/toml.c $(LDFLAGS) $(LDLIBS) -o $@
.PHONY: all install clean

lock.o: media.h

$(OBJECTS): simple-theme.h

lock.o simplelock-test: ../simple-common/calendar.h

lock.o simplelock-test: ../simple-common/phone-network.h

lock.o simplelock-test: ../simple-common/phone-charge.h ../simple-common/phone-charge-cache.h

lock.o simplelock-test: ../simple-common/system-info.h

lock.o simplelock-test: ../simple-common/music-layout.h

lock.o simplelock-test: ../simple-common/idle-audio.h

lock.o simplelock-test: ../simple-common/daylight-art.h

$(OBJECTS): ../simple-common/simple-theme.h

lock.o simplelock-test: ../simple-common/song-progress.h

lock.o: ../simple-common/simple-images.h ../simple-common/daylight-art.h
