CC ?= cc
CFLAGS ?= -O2 -Wall -Wextra
PKGS = gtk4 json-c
CPPFLAGS += $(shell pkg-config --cflags $(PKGS))
LDLIBS += $(shell pkg-config --libs $(PKGS))
.PHONY: all check install clean
all: simpleplayer-native
simpleplayer-native: native.c visualizer.h ../simple-common/song-progress.h ../simple-common/simple-theme.h
	$(CC) $(CPPFLAGS) $(CFLAGS) native.c -o $@ $(LDLIBS)
check: all
	python3 check.py
	python3 tests/streams.py
	bash -n playback.sh
	./simpleplayer-native --help
install: check
	python3 install.py
clean:
	rm -f simpleplayer-native

simpleplayer-native: ../simple-common/simple-keyboard.h

SIMPLE_UI_TARGETS = simpleplayer-native
include ../simple-common/framework.mk
