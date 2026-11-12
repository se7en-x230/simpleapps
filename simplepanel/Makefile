CC ?= cc
PKGS = gtk4-layer-shell-0 gtk4 gio-unix-2.0 json-c libpulse-mainloop-glib
CFLAGS ?= -O2
CFLAGS += -std=c11 -Wall -Wextra -Werror -Wno-unused-parameter
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
LDLIBS += $(shell pkg-config --libs $(PKGS)) -lm
all: simplepanel
simplepanel: panel.c system-dashboard.c dashboard-settings.c dashboard-settings.h panel-modules.c panel-modules.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $(filter %.c,$^) -o $@ $(LDLIBS)
check: simplepanel
	./simplepanel --check
	python3 check-config.py
	python3 tests/check-modules.py
.PHONY: all check

simplepanel: media.h

simplepanel: simple-theme.h

simplepanel: phone-charge.h

simplepanel: phone-charge-cache.h

simplepanel: ../simple-common/phone-charge.h ../simple-common/phone-charge-cache.h

simplepanel: ../simple-common/simple-paths.h

simplepanel: ../simple-common/simple-theme.h

SIMPLE_UI_TARGETS = simplepanel
include ../simple-common/framework.mk
