PREFIX ?= $(HOME)/.local
DESTDIR ?=
CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -Wall -Wextra -Wno-misleading-indentation -Wno-deprecated-declarations $(shell pkg-config --cflags gtk4 json-c)
LDLIBS += $(shell pkg-config --libs gtk4 json-c)
all: simplemail-native
simplemail-native: native.c ../simple-common/simple-paths.h ../simple-common/simple-theme.h
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)
install: all
	install -Dm755 simplemail-native $(DESTDIR)$(PREFIX)/bin/.simplemail-native.new
	mv -f $(DESTDIR)$(PREFIX)/bin/.simplemail-native.new $(DESTDIR)$(PREFIX)/bin/simplemail-native
clean:
	rm -f simplemail-native
.PHONY: all install clean

simplemail-native: ../simple-common/simple-keyboard.h
