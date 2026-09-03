.PHONY: install test

DESTDIR ?=
BINDIR ?= /usr/bin
OPENRC_INITDDIR ?= /etc/init.d
OPENRC_CONFDIR ?= /etc/conf.d

install:
	install -D -m 0700 "t2fand" "$(DESTDIR)$(BINDIR)/t2fand"
	install -D -m 0755 "t2fand.initd" "$(DESTDIR)$(OPENRC_INITDDIR)/t2fand"
	install -D -m 0644 "t2fand.confd" "$(DESTDIR)$(OPENRC_CONFDIR)/t2fand"

test:
	python3 -m unittest discover -s tests -p 'test_*.py'
