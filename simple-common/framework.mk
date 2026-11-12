# Include after defining SIMPLE_UI_TARGETS. Keep this file in simple-common.
SIMPLE_UI_DIR := $(abspath $(dir $(lastword $(MAKEFILE_LIST))))
LDLIBS += -L$(SIMPLE_UI_DIR) -lsimple-ui -Wl,-rpath,'$$ORIGIN/../lib/simple-common:$$ORIGIN/../simple-common:$$ORIGIN/../../simple-common'
$(SIMPLE_UI_TARGETS): $(SIMPLE_UI_DIR)/libsimple-ui.so
$(SIMPLE_UI_DIR)/libsimple-ui.so: $(SIMPLE_UI_DIR)/simple-ui.c $(SIMPLE_UI_DIR)/simple-ui.h
	$(MAKE) -C $(SIMPLE_UI_DIR)

PREFIX ?= $(HOME)/.local
.PHONY: simple-ui-install
install: simple-ui-install
simple-ui-install:
	$(MAKE) -C $(SIMPLE_UI_DIR) install PREFIX="$(PREFIX)" DESTDIR="$(DESTDIR)"
