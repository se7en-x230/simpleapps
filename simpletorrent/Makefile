PREFIX ?= $(HOME)/.local
DESTDIR ?=
CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -Wall -Wextra -Wno-unused-parameter $(shell pkg-config --cflags gtk4 json-c libcurl)
LDLIBS += $(shell pkg-config --libs gtk4 json-c libcurl)
all: simpletorrent
simpletorrent: main.c ../simple-common/simple-theme.h
	$(CC) $(CFLAGS) -o $@ $< $(LDLIBS)
install: all
	install -Dm755 simpletorrent $(DESTDIR)$(PREFIX)/bin/.simpletorrent.new
	mv -f $(DESTDIR)$(PREFIX)/bin/.simpletorrent.new $(DESTDIR)$(PREFIX)/bin/simpletorrent
clean:
	rm -f simpletorrent
.PHONY: all install clean
