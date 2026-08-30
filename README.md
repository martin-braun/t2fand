# t2fand

`t2fand` is a root-required foreground Python 3 daemon for automatic fan control
on Linux T2 Macs; In this fork, OpenRC is its only supported service manager.

This fork has been overhauled:

- monitor all hwmon temperatures
- add global fail-safe control
- harden config and cleanup
- OpenRC logging and supervision
- add fake-sysfs tests and updated docs

## Requirements

- Linux on an Apple T2 Mac with working fan controls and hwmon sensors
- Python 3, OpenRC, root access, and util-linux (`/usr/bin/logger`)

## Install

From a checkout:

```sh
#

sudo make install

#
```

Or as package under Artix Linux (OpenRC):

```sh
#

makepkg -si
sudo rc-update add t2fand default
sudo rc-service t2fand start

#
```

This installs `/usr/bin/t2fand` with mode `0700` and `/etc/init.d/t2fand` with
mode `0755`. Installation does not enable or start the service. For staging,
`DESTDIR` prefixes both paths; `BINDIR` defaults to `/usr/bin` and
`OPENRC_INITDDIR` to `/etc/init.d`, and all are configurable.

## Configure

On first start, t2fand creates `/etc/t2fand.conf` with one section per detected
fan. Each section uses these four settings and defaults:

```ini
[Fan1]
low_temp = 55
high_temp = 75
speed_curve = linear
always_full_speed = false
```

`low_temp` and `high_temp` define the control range; `speed_curve` is `linear`,
`exponential`, or `logarithmic`; `always_full_speed` can be `true` or `false`.
Configuration is read at startup. Restart after changes. Invalid configuration
selects fail-high maximum control when available.

Here's an image to better explain this:

![Image of fan curve graphs](https://user-images.githubusercontent.com/39993457/233580720-cfdaba12-a2d8-430c-87a2-15209dcfec6d.png)

> (Red: linear, blue: exponential, green: logarithmic)

## Run with OpenRC

```sh
#

sudo rc-update add t2fand default
sudo rc-service t2fand start

#
```

Enablement is optional. Set daemon arguments in `/etc/conf.d/t2fand` without
editing the init script:

```ini
t2fand_args="--verbose"
```

OpenRC sends stdout and stderr through util-linux `logger` to the
administrator-selected syslog receiver. The receiver, destination, and
persistence are host-dependent.

## Safety

The daemon writes fan controls as root. Do not delete live sysfs nodes or
obstruct cooling sensors. Cleanup is best effort and cannot guarantee fan state
after abrupt termination or loss of hardware write authority.

With valid inputs, the service continuously adjusts fan targets. Unsafe
configuration or sensor input attempts maximum fan control when possible; loss
of that control exits for OpenRC recovery.

## Test

Run the project-native test target:

```sh
#

make test

#
```

Tests are defined but unexecuted in this documentation sync. See
[SPEC.md](SPEC.md) for the contract and [CONTEXT.md](CONTEXT.md) for verified
implementation truth and history.

## Use of AI

This version was built by agents on the basis of version 1.2.0.
