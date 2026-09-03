# t2fand

> **This version is under active development and should not be installed.**

`t2fand` is a root-required foreground Python 3 daemon for Linux on Apple T2
Macs. It observes fan operation through Apple SMC or applies temperature-driven
curves as the daemon controller. OpenRC is the supported service manager.

## Requirements

- Linux on an Apple T2 Mac with working fan controls and hwmon sensors
- Python 3, OpenRC, root access, and util-linux (`/usr/bin/logger`)

## Install

From a checkout:

```sh
sudo make install
```

This installs `/usr/bin/t2fand` (0700), `/etc/init.d/t2fand` (0755), and
`/etc/conf.d/t2fand` (0644). Installation does not enable or start the service.
`DESTDIR` stages the files; `BINDIR`, `OPENRC_INITDDIR`, and `OPENRC_CONFDIR`
can change their destinations.

On Artix, the package recipe is:

```sh
#

makepkg -si

#
```

It packages the daemon, OpenRC init script, and conf.d file. The package marks
`/etc/conf.d/t2fand` for backup, preserving administrator changes on upgrades.

## Configure

Configuration is read once at startup. Default mode: `smc`. Restart after
changes.

| Mode     | Controller | [FanN] policy         |
| -------- | ---------- | --------------------- |
| `smc`    | Apple SMC  | Not applied           |
| `t2fand` | `t2fand`   | Applied automatically |

In `smc`, Apple SMC makes fan-speed decisions; the daemon only observes and does
not apply the displayed FanN settings. Set `control_mode = t2fand` and restart
to use temperature-driven curves. Only `smc` and `t2fand` are valid global
tokens; `manual`, aliases, `auto`, and `smc_auto` are rejected. An existing
config without `[General]` infers `t2fand`, warns exactly once, and is never
rewritten.

An absent config starts with SMC mode and one policy section per detected fan:

```ini
[General]
control_mode = smc

[Fan1]
low_temp = 55
high_temp = 75
speed_curve = linear
always_full_speed = false
```

Allowed curves are `linear`, `exponential`, and `logarithmic`;
`always_full_speed = true` selects full speed in `t2fand` mode.

The installed `/etc/conf.d/t2fand` provides the sole supported OpenRC override:
`t2fand_args`. The init script passes only this value through `command_args`;
daemon defaults remain in `t2fand`. Set `t2fand_args="--verbose"` to enable full
telemetry.

## CLI overrides

All options are available for direct foreground use and through `t2fand_args`:

| Option                           | Default            | Meaning                                            |
| -------------------------------- | ------------------ | -------------------------------------------------- |
| `-v`, `--verbose`                | off                | Emit full telemetry.                               |
| `-c`, `--config-path`            | `/etc/t2fand.conf` | Configuration file path.                           |
| `-p`, `--pid-path`               | `/run/t2fand.pid`  | Daemon PID file path.                              |
| `-s`, `--sysfs-path`             | `/sys`             | Sysfs root path.                                   |
| `-r`, `--sensor-recovery-cycles` | `5`                | Valid cycles before sensor recovery.               |
| `-l`, `--sample-limit`           | `5`                | Temperature samples retained for smoothing.        |
| `-e`, `--error-reminder-seconds` | `60.0`             | Minimum interval between repeated error reminders. |

`-r` and `-l` require positive integers. `-e` requires a positive finite float.
Zero, negative, nonnumeric, NaN, and infinite numeric values are rejected by
argparse before root checks or filesystem mutation.

## Telemetry and benchmark output

Both `smc` and `t2fand` emit one flushed telemetry record per one-second control
cycle. By default, the compact record contains only `highest=<sensor-label>`,
`highest_temp=<value>`, and `actual_rpm` for every discovered fan. An
unavailable value, or no eligible hottest sensor, is `unknown`. Faulted,
unavailable, and skipped sensors cannot be hottest; equal maxima use discovery
order.

`-v`/`--verbose` selects the full record in either mode: sensor values,
topology, state, reason, policy, target, and actual-RPM fields. SMC mode does
not imply verbose output. Warnings, transitions, degraded reminders, and errors
are independent of telemetry verbosity.

`t2fanbench.py` requires an executable `stress-ng` available on `PATH`. It
checks this before creating its cache, producing benchmark or logger output,
sleeping, or launching subprocesses. If unavailable, it writes exactly
`error: stress-ng is required but was not found in PATH` to stderr and exits
with status `1`, without a traceback or those side effects.

Every message printed by `t2fanbench.py`'s `log()` uses local wall-clock time in
this exact form, with English month names and zero-padded day/time fields:

`MMM DD HH:mm:ss [t2fanbench] MESSAGE`

The lines are flushed, have no leading blank line or `===` decoration, and the
existing `logger` side effect remains. Output from the `stress-ng` child is
unchanged.

## Run with OpenRC

```sh
#

sudo rc-update add t2fand default
sudo rc-service t2fand start

#
```

Enablement is optional. Use `rc-service t2fand status|stop|restart` as needed.
OpenRC routes daemon stdout to logger tag `t2fand` at `daemon.info` and stderr
at `daemon.err`.

T2fand mode fails high to known maximum fan speed when possible. SMC monitors
without taking control for ordinary sensor or tachometer failures. Normal
shutdown releases daemon fan control. Cleanup is not guaranteed after `SIGKILL`,
power loss, kernel failure, or unavailable hardware writes.

## Test

The project-native test target is:

```sh
#

make test

#
```

This guide does not claim test, hardware, service, logger, or package outcomes.
See [SPEC.md](SPEC.md) for the contract and [CONTEXT.md](CONTEXT.md) for
verified implementation truth and history.
