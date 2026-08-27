.PHONY: install

DESTDIR ?=
BINDIR ?= /usr/bin
OPENRC_INITDDIR ?= /etc/init.d

install:
	install -D -m 0700 "t2fand" "$(DESTDIR)$(BINDIR)/t2fand"
	install -D -m 0755 "t2fand.initd" "$(DESTDIR)$(OPENRC_INITDDIR)/t2fand"
