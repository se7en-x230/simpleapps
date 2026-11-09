PREFIX ?= $(HOME)/.local
HELPERDIR ?= $(PREFIX)/share/simplepicker/scripts
DESTDIR ?=
PROGRAM ?= simplepicker-native
CC ?= cc
CFLAGS ?= -O2 -g
PKGS = gtk4 gtk4-layer-shell-0 gio-unix-2.0 json-c
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
LDLIBS += $(shell pkg-config --libs $(PKGS))
SOURCES = keys.c main.c util.c settings.c ui.c desktop.c providers.c power.c dashboard.c bridge.c vendor/toml.c
OBJECTS = $(SOURCES:.c=.o)
.PHONY: all clean install uninstall check
all: simplepicker-native
simplepicker-native: $(OBJECTS)
	$(CC) $(LDFLAGS) $^ -o $@ $(LDLIBS)
$(OBJECTS): sp.h
%.o: %.c
	$(CC) $(CPPFLAGS) $(CFLAGS) -Wall -Wextra -Werror -Wno-missing-field-initializers -c $< -o $@
clean:
	rm -f $(OBJECTS) simplepicker-native
install: simplepicker-native
	install -d "$(DESTDIR)$(PREFIX)/lib/simplepicker"
	install -m644 python/*.py "$(DESTDIR)$(PREFIX)/lib/simplepicker/"
	install -d "$(DESTDIR)$(PREFIX)/bin" "$(DESTDIR)$(PREFIX)/share/simplepicker"
	install -m755 simplepicker-native "$(DESTDIR)$(PREFIX)/bin/$(PROGRAM)"
	install -m644 assets/*.json assets/*.txt assets/*LICENSE "$(DESTDIR)$(PREFIX)/share/simplepicker/"
	install -m644 vendor/LICENSE.tomlc99 "$(DESTDIR)$(PREFIX)/share/simplepicker/"
	install -m755 assets/edit-bookmarks assets/wtype "$(DESTDIR)$(PREFIX)/share/simplepicker/"
	install -d "$(DESTDIR)$(HELPERDIR)"
	install -m755 idle "$(DESTDIR)$(HELPERDIR)/idle"
	printf '%s\n' 'Installed $(PROGRAM). Existing config/history and shortcuts were not changed.'
uninstall:
	rm -f "$(DESTDIR)$(PREFIX)/bin/$(PROGRAM)"
	@echo 'Resources and personal data are retained; remove resources manually if no longer used.'
check: simplepicker-native
	python3 tests/check.py
tests/driver: tests/driver.c $(filter-out main.o,$(OBJECTS))
	$(CC) $(CPPFLAGS) $(CFLAGS) -Wall -Wextra -Werror -Wno-missing-field-initializers $^ -o $@ $(LDLIBS)
tests/desktop-check: tests/desktop-check.c util.o settings.o desktop.o vendor/toml.o
	$(CC) $(CPPFLAGS) $(CFLAGS) -Wall -Wextra -Werror $^ -o $@ $(LDLIBS)

dashboard.o: media.h

$(OBJECTS): simple-theme.h

dashboard.o: ../simple-common/calendar.h

dashboard.o: ../simple-common/phone-network.h

dashboard.o: ../simple-common/phone-charge.h ../simple-common/phone-charge-cache.h

dashboard.o: ../simple-common/system-info.h

dashboard.o: ../simple-common/music-layout.h

dashboard.o: ../simple-common/idle-audio.h

dashboard.o: ../simple-common/daylight-art.h

$(OBJECTS): ../simple-common/simple-theme.h

dashboard.o: ../simple-common/simple-images.h ../simple-common/daylight-art.h


ui.o: ../simple-common/simple-keyboard.h
