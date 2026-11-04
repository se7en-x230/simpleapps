PREFIX ?= $(HOME)/.local
DESTDIR ?=
CC ?= cc
CFLAGS ?= -O2 -g
CPPFLAGS += -DCONTACTS=0
CFLAGS += -Wall -Wextra -Wno-deprecated-declarations -Wno-unused-function -Wno-misleading-indentation $(shell pkg-config --cflags gtk4 json-c)
LDLIBS += $(shell pkg-config --libs gtk4 json-c)
all: simplecalendar-native
simplecalendar-native: ../simple-common/organizer.c ../simple-common/simple-paths.h ../simple-common/simple-theme.h ../simple-common/daylight-art.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< $(LDLIBS)
install: all
	install -Dm755 simplecalendar-native $(DESTDIR)$(PREFIX)/bin/.simplecalendar-native.new
	mv -f $(DESTDIR)$(PREFIX)/bin/.simplecalendar-native.new $(DESTDIR)$(PREFIX)/bin/simplecalendar-native
clean:
	rm -f simplecalendar-native
.PHONY: all install clean

simplecalendar-native: ../simple-common/simple-images.h ../simple-common/daylight-art.h
