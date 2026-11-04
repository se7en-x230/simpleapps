PREFIX ?= $(HOME)/.local
DESTDIR ?=
CC ?= cc
CFLAGS ?= -O2 -g
CPPFLAGS += -DCONTACTS=1
CFLAGS += -Wall -Wextra -Wno-deprecated-declarations -Wno-unused-function -Wno-misleading-indentation $(shell pkg-config --cflags gtk4 json-c)
LDLIBS += $(shell pkg-config --libs gtk4 json-c)
all: simplecontacts-native
simplecontacts-native: ../simple-common/organizer.c ../simple-common/simple-paths.h ../simple-common/simple-theme.h
	$(CC) $(CPPFLAGS) $(CFLAGS) -o $@ $< $(LDLIBS)
install: all
	install -Dm755 simplecontacts-native $(DESTDIR)$(PREFIX)/bin/.simplecontacts-native.new
	mv -f $(DESTDIR)$(PREFIX)/bin/.simplecontacts-native.new $(DESTDIR)$(PREFIX)/bin/simplecontacts-native
clean:
	rm -f simplecontacts-native
.PHONY: all install clean

simplecontacts-native: ../simple-common/simple-images.h ../simple-common/daylight-art.h
