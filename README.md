# t2fand

`t2fand` is a Python 3 daemon for automatic fan-speed control on Linux Macs with
an Apple T2 chip. It reads temperature and fan interfaces, applies the
configured fan policy, and writes fan-control values.

## Prerequisites

- Linux on a T2 Mac with the required sysfs interfaces.
- Python 3 and root access.
- OpenRC. Exact hardware and OpenRC coverage are unknown.

## Install

Install the daemon and OpenRC service definition with:

```sh
#

sudo make install

#
```

To stage files without configuring a live host, set `DESTDIR`:

```sh
#

make DESTDIR="$PWD/pkg" install

#
```

The default paths and modes are `/usr/bin/t2fand` (0700) and
`/etc/init.d/t2fand` (0755). `BINDIR` and `OPENRC_INITDDIR` can override their
directories; `DESTDIR` prefixes both paths.

Installation and staging do not enable or start the daemon.

## Configuration

On first start, when `/etc/t2fand.conf` is absent, the daemon creates one
section per detected fan. Each section requires all four settings:

```ini
[Fan1]
low_temp = 55
high_temp = 75
speed_curve = linear
always_full_speed = false
```

| Setting             | Meaning                                                                     | Default  |
| ------------------- | --------------------------------------------------------------------------- | -------- |
| `low_temp`          | At or below this temperature, use minimum fan speed.                        | `55`     |
| `high_temp`         | At or above this temperature, use maximum fan speed.                        | `75`     |
| `speed_curve`       | Curve used between the thresholds.                                          | `linear` |
| `always_full_speed` | Exact value `true` selects maximum speed regardless of thresholds or curve. | `false`  |

| Curve         | Behavior between the thresholds                                                                              |
| ------------- | ------------------------------------------------------------------------------------------------------------ |
| `linear`      | Changes evenly.                                                                                              |
| `exponential` | Uses the cubic expression `((temp - low_temp) ** 3) / ((high_temp - low_temp) ** 3)` and starts more slowly. |
| `logarithmic` | Uses the logarithmic expression `math.log(temp - low_temp, high_temp - low_temp)` and starts more quickly.   |

- `low_temp`: temperature at or below which the fan uses its minimum speed.
- `high_temp`: temperature at or above which the fan uses its maximum speed.
- `speed_curve`: `linear`, `exponential`, or `logarithmic` interpolation between
  the thresholds. `linear` changes evenly; `exponential` uses the daemon's cubic
  expression and starts more slowly; `logarithmic` uses the daemon's logarithmic
  expression and starts more quickly.
- `always_full_speed`: exact value `true` selects maximum speed regardless of
  the thresholds or curve.

Defaults are `55`, `75`, `linear`, and `false`. The curve illustration is
available as [`Fan Curve.png`](Fan%20Curve.png).

![Fan curve illustration](Fan%20Curve.png)

After changing the configuration, stop and start the service again. The daemon
reads the file at startup and does not reload it live.

## Run with OpenRC

Add the service to the `default` runlevel when it should start with that
runlevel, then manage it with OpenRC:

```sh
#

sudo rc-update add t2fand default
sudo rc-service t2fand start
sudo rc-service t2fand status
sudo rc-service t2fand stop

#
```

The lifecycle description above is static evidence from the checked-in OpenRC
source and OpenRC 0.62.10 directive semantics. Local runlevel, start, stop,
status, and respawn behavior are unknown.

## Expected result

During normal operation, `t2fand` samples temperatures, smooths up to five
samples, calculates each fan's target, and writes a clamped speed about once per
second. OpenRC status reports the service manager's view of the daemon. Runtime
and hardware outcomes are unknown.
