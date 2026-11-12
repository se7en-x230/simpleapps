PREFIX ?= $(HOME)/.local
CC ?= cc
CFLAGS ?= -O2 -g
CFLAGS += -Wall -Wextra -Werror -fPIC $(shell pkg-config --cflags gtk4)
LDLIBS += $(shell pkg-config --libs gtk4) -ldl
all: libsimple-ui.so
check-deps:
	@pkg-config --print-errors --exists "gtk4 >= 4.12"
libsimple-ui.so: | check-deps
libsimple-ui.so: simple-ui.c simple-ui.h simple-theme.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(LDFLAGS) -shared -Wl,-soname,libsimple-ui.so -o $@ simple-ui.c $(LDLIBS)
install: all
	install -Dm755 libsimple-ui.so $(DESTDIR)$(PREFIX)/lib/simple-common/.libsimple-ui.so.new
	mv -f $(DESTDIR)$(PREFIX)/lib/simple-common/.libsimple-ui.so.new $(DESTDIR)$(PREFIX)/lib/simple-common/libsimple-ui.so
	install -Dm644 simple_keyboard.py $(DESTDIR)$(PREFIX)/lib/simple-common/simple_keyboard.py
	install -Dm644 theme_loader.py $(DESTDIR)$(PREFIX)/lib/simple-common/theme_loader.py
	install -Dm644 simple_ui.py $(DESTDIR)$(PREFIX)/lib/simple-common/simple_ui.py
	install -Dm644 palette.css $(DESTDIR)$(PREFIX)/lib/simple-common/palette.css
	install -Dm644 framework.css $(DESTDIR)$(PREFIX)/lib/simple-common/framework.css
	install -Dm644 simple-ui.h $(DESTDIR)$(PREFIX)/include/simple-ui.h
.PHONY: all install check-deps
