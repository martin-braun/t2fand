# CONTEXT.md — t2fand implementation context

This file records verified local project truth behind the code-derived contract
in `SPEC.md`. `README.md` remains the short human use guide. `AGENTS.md` owns
agent routing and protected-surface rules. Source inspection is not runtime
evidence; unknown claims stay marked `unknown`.

<!-- SECTION MAP BEGIN -->

- `1. Project identity`: purpose, scope, owners, users, supported targets, and
  explicit non-goals.
- `2. Current state`: shipped behavior, active work, known gaps, and status.
- `3. Architecture`: components, boundaries, data flow, dependencies, and
  reasons for the chosen structure.
- `4. Interfaces`: public and internal APIs, files, protocols, inputs, outputs,
  compatibility rules, and ownership.
- `5. Workflows`: development, configuration, operation, deployment, release,
  migration, recovery, and approval paths.
- `6. Constraints and invariants`: safety laws, supported limits, immutability,
  ordering, portability, and protected surfaces.
- `7. Security`: secrets, trust boundaries, permissions, threat controls, and
  prohibited handling.
- `8. Validation`: required checks, test levels, health signals, fixtures, and
  evidence of success.
- `9. Known failures and decisions`: failure modes, diagnostics, settled
  decisions, superseded paths, and anti-regression memory.
- `10. Maintenance`: monitoring, upgrades, backups, repair, ownership, and
  documentation-sync triggers.
- `11. Agent rules`: routing, edit boundaries, tool rules, and escalation.
- `12. Current summary`: concise verified snapshot and open unknowns.

<!-- SECTION MAP END -->

## 1. Project identity

`t2fand` is a foreground Python 3 daemon for Linux on Macs with an Apple T2
chip. Each cycle it discovers the exposed hwmon temperature inputs, requires a
usable CPU input, selects the hottest valid system reading, and writes a target
for every controllable fan through reopened Linux sysfs paths.

The repository user roles are:

- T2 Mac Linux user: automatic temperature-driven fan control.
- Root administrator: install, configure, and supervise the daemon.
- Arch package consumer: install the declared package files.
- Maintainer: build and release the Arch package; the package metadata names
  Martin Braun.

The evidenced target is the T2-oriented Linux sysfs layout in `t2fand`,
including global hwmon, coretemp, and hwmon paths below exact numeric DRM cards.
The declared package target is Arch Linux `x86_64`. Exact Mac model, kernel,
distribution, Python, `linux-t2`, hardware coverage, and OpenRC coverage are
`unknown`.

Non-goals and non-claims: no GUI, network API, or remote-source maintenance is
defined. OpenRC is the sole supported service manager and `t2fand.initd` is the
sole service definition. Broader hardware support, non-root use, thermal-event
prevention, acoustic improvement, and every-model compatibility are `unknown`.

## 2. Current state

### Present implementation

- `t2fand` is an executable Python script with no compilation step. It is
  import-safe and runs in the foreground through `main()`.
- Fan discovery unions T2 and class-hwmon candidates, deduplicates resolved base
  paths, and requires every discovered candidate to be complete and
  controllable; one complete fan does not mask an incomplete candidate.
- It re-discovers and reopens fan and temperature paths each cycle, reads each
  deduplicated temperature input once, labels optional metadata, and selects the
  hottest valid value. CPU availability requires one selected, fault-free,
  parsed, positive CPU channel; a non-positive sibling does not cancel it. Any
  selected input read/parse/fault failure, including CPU, enters recoverable
  sensor-failsafe while fan control survives. GPU inputs below exact numeric DRM
  cards are optional and report missing/recovery transitions.
- Normal control samples once per second, keeps at most five valid maxima, and
  uses their mean rounded to two decimals. Sensor and config fail-safe modes
  bypass smoothing and attempt every known maximum. Valid `configured-full`
  policies also bypass normal smoothing and do not report a rolling mean. Sensor
  recovery needs five consecutive valid cycles and resets prior history.
- Configuration is generated only when absent, validated globally once at
  startup, and read from `/etc/t2fand.conf`. Invalid policy remains
  `config-failsafe` until restart; an unsafe runtime policy calculation latches
  the same mode until restart. Valid `always_full_speed=true` is
  `configured-full`.
- SIGTERM and SIGINT only request shutdown. The common cleanup attempts maximum
  on fatal paths, disables manual mode independently per fan, and removes the
  daemon PID file when owned. Cleanup failures are reported. After manual
  control starts, an unexpected ordinary `Exception` is converted to fatal
  control handling: the original diagnostic is emitted as critical, known maxima
  are attempted independently for every fan, fan and owned-PID cleanup proceeds
  independently, exit is nonzero, and the normal stopped summary is omitted.
  Pre-control unexpected exceptions are not converted; `BaseException` paths
  remain outside this handling.
- `t2fand.initd` is the sole root OpenRC definition for the foreground daemon.
- `Makefile` unconditionally installs the OpenRC definition, stages with
  `DESTDIR`, and applies the declared executable/service modes.
- `PKGBUILD` directly ships only the executable and OpenRC definition, with
  `pkgname=t2fand`, release `2.0.0-1` (`pkgver=2.0.0`, `pkgrel=1`), and
  `util-linux` for `/usr/bin/logger`.
- `tests/test_t2fand.py` is a standard-library unittest suite using temporary
  fake sysfs/config trees and mocks. Definitions include absent-CPU,
  config-generation-I/O, and partial-discovered-fan fixtures. `make test` is the
  project-native target and remains unexecuted.
- No systemd unit or systemd payload is present.
- `.github/workflows/build.yml` provides package build, artifact, and release
  automation.
- README/CONTEXT synchronization follows REQ-051: README is concise operator
  onboarding; exhaustive contract and implementation truth remain here and in
  `SPEC.md`.

These are source/configuration facts. Test execution, runtime, hardware,
privileged install, staged output, package-build, release, syslog delivery, and
CI success are not verified.

### Gaps and open status

- `make test` and a local unittest suite are present, but this documentation
  sync does not claim test execution or passing results.
- OpenRC operation is unverified. Its checked-in definition and directive values
  are static evidence, not a runtime claim.
- The package fetches an unpinned remote Git source with `sha256sums=('SKIP')`;
  equivalence with this local checkout is `unknown`.
- Configuration reload, schema migration, rollback, and fan-topology migration
  are not defined.
- Outcomes after pre-control unexpected exceptions remain `unknown`; those
  exceptions are not converted to fatal control handling. `BaseException`,
  SIGKILL, power loss, kernel panic, interpreter/native abort, and hardware or
  OpenRC runtime outcomes remain `unknown` beyond the checked-in paths.
- The exact syslog receiver, destination, and persistence result are unknown;
  util-linux `logger` is only the declared service transport.

## 3. Architecture

### Components and boundaries

1. The `t2fand` process performs privilege checks, discovery, configuration,
   control, telemetry, and signal-request cleanup.
2. `Fan` wraps one sysfs fan base path. Discovery reads integer `_max` and
   `_min`; control clamps and reopens `_output`; manual mode reopens `_manual`.
   Tachometer reads reopen `_input` and are diagnostic.
3. Sensor discovery unions global hwmon, coretemp, and `device/hwmon` below
   exact numeric DRM cards. Resolved aliases are deduplicated; each selected
   input is read once per cycle. Optional names, labels, and fault flags enrich
   labels/classification without optional labels gating operation.
4. `configparser` reads `/etc/t2fand.conf` once at startup. One validated
   four-value policy is stored for each discovered fan. Invalid policy is a
   global config fail-safe when maximum control remains available.
5. Controller state keeps normal and recovery histories, mode/reason, GPU
   topology, shutdown request, and error reminder timing in memory.
6. OpenRC, `make install`, the Arch recipe, and GitHub Actions are integration
   surfaces around the script. They do not add a second controller.

### Discovery and control/data flow

Startup checks effective UID, handles `/run/t2fand.pid`, discovers every
deduplicated fan candidate and requires all candidates to be complete and
controllable, generates or validates `/etc/t2fand.conf`, installs signal-request
handlers, writes the PID, enables manual mode, and enters the outer lifecycle
cleanup route. A config defect does not terminate before fan protection when
known maxima are available. After manual control starts, an unexpected ordinary
`Exception` is converted to fatal `control-error` handling; its original
diagnostic is emitted as critical, then maximum attempts, per-fan manual
cleanup, and owned-PID removal proceed independently. The process exits nonzero
and emits no normal stopped summary. Pre-control unexpected exceptions are not
converted, and `BaseException` is outside this handling.

Each one-second cycle re-discovers temperature inputs, reads each resolved path
once, parses signed integer millidegrees Celsius, treats faulted/failed values
as `unknown`, and selects the highest valid value. CPU is required and must be
positive. Any selected read, parse, or fault failure, including CPU, enters
recoverable sensor-failsafe while maximum fan control survives; absent CPU also
enters that mode. Absent GPU topology is not itself a failure. Normal history
contains at most five valid maxima. Fail-safe bypasses history, commands known
maxima, and retries. Five consecutive fully valid recovery cycles replace old
history; curve smoothing resumes on the following normal cycle.

Each fan policy converts the rolling mean to a clamped integer output using the
legacy linear, cubic exponential, or logarithmic expression. A valid configured
full-speed policy bypasses normal smoothing and omits the rolling mean. Any
actual RPM read failure reports `unknown`, omits the rolling mean, commands
every controllable fan maximum, and does not itself start sensor recovery. The
loop sleeps one second. All sysfs operations reopen their paths; no file handle
is retained.

This is a single process with direct local file I/O. No queue, watcher, network
listener, logging framework, or separate worker is defined; verbose telemetry is
direct flushed key-value output.

Reported modes are `curve` (normal policy), `configured-full` (valid
`always_full_speed=true`), `config-failsafe` (unsafe global policy),
`sensor-failsafe` (unsafe thermal or actual-RPM input; thermal recovery
retries), `control-error` (fatal loss of maximum control), and `shutting-down`
(common cleanup). Mode, reason, and GPU topology changes are emitted on
transition; repeated default problems are rate-limited with a 60-second reminder
interval. Verbose output adds one flushed record per second with every sensor
label/value or `unknown`, `gpu_temps`, highest temperature, rolling mean only
during normal smoothing, and each fan's low/high/curve/full-speed policy,
`target_rpm`, and `actual_rpm` or `unknown`. Configured-full and
RPM-telemetry-failure records omit the rolling mean.

## 4. Interfaces

### Process and runtime paths

| Interface         | Local contract                                                                                                                                                                                                                                                                                      |
| ----------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Executable        | `/usr/bin/t2fand` is the foreground daemon invoked by OpenRC. `-v`/`--verbose` enables one flushed telemetry record per second; unknown arguments fail before hardware mutation. Direct invocation is not a second service-manager workflow.                                                        |
| PID file          | `/run/t2fand.pid` stores the daemon's decimal PID. A live `/proc/<pid>` path rejects startup; malformed or stale state is diagnosed and removed when possible. Identity locking and atomicity are not implemented.                                                                                  |
| Config file       | `/etc/t2fand.conf`, generated only when absent, validated globally, and read once at startup. Invalid administrator content is not normalized.                                                                                                                                                      |
| Fan sysfs         | Read integer `<base>_max`, `<base>_min`, and tachometer `<base>_input`; write `<base>_output` and `<base>_manual`, reopening each path.                                                                                                                                                             |
| Temperature sysfs | Union global hwmon, coretemp, and exact numeric DRM-card descendants; parse signed integer millidegree-Celsius text. Failed values are `unknown`; aliases deduplicate by resolved path.                                                                                                             |
| Signals           | SIGTERM and SIGINT only request common cleanup. After manual control starts, an unexpected ordinary `Exception` becomes fatal `control-error` handling; pre-control unexpected exceptions and `BaseException` are outside this conversion. Other abrupt termination paths cannot guarantee cleanup. |

### Configuration schema

There is one section `Fan1` through `FanN` per detected fan. Every detected fan
section must contain:

```ini
[Fan1]
low_temp = 55
high_temp = 75
speed_curve = linear
always_full_speed = false
```

The generated defaults are `55`, `75`, `linear`, and `false`. `speed_curve` must
be `linear`, `exponential`, or `logarithmic`. `always_full_speed` accepts only
case-insensitive `true` or `false` after INI whitespace handling. Thresholds
must be finite and satisfy `low_temp < high_temp`; malformed INI and every
missing or invalid fan policy produce global `config-failsafe`. The file is not
rewritten on validation failure.

### Service integrations

`t2fand.initd` is the sole checked-in service definition. It opens with
`#!/sbin/openrc-run`, sets `command=/usr/bin/t2fand`, reads optional
`/etc/conf.d/t2fand` `t2fand_args` into `command_args`, and uses
`supervisor="supervise-daemon"`. It sets `respawn_delay="2"`, `respawn_max="5"`,
`respawn_period="60"`, `supervise_daemon_args="--respawn-delay-step 2"`, and
`retry="SIGTERM/5"`. It declares `need localmount` and soft `use logger`; it
sets no network, background, daemonization, or supervisor `pidfile` setting. Its
output and error logger commands use util-linux `/usr/bin/logger` with `t2fand`
and `daemon.info`/`daemon.err`.

The daemon stays foreground and owns `/run/t2fand.pid`; OpenRC supervisor state
is separate and must not replace it. The checked-in directives describe a
two-second base delay, five respawns per 60-second window, two-second
incremental backoff, eligibility for child exits within the bound, and
explicit-stop suppression. These are static source evidence; local lifecycle
execution and exact directive support are unknown. No systemd artifact or
payload is present.

### Curve and fan behavior

- Validated configuration requires finite thresholds with `low_temp` strictly
  lower than `high_temp`; equal or inverted thresholds enter global
  `config-failsafe`.
- Between thresholds, `linear` interpolates linearly, `exponential` uses the
  script's cubic expression, and `logarithmic` uses its `math.log` expression.
- At or below `low_temp`, use the fan minimum; at or above `high_temp`, use the
  fan maximum. A valid `always_full_speed=true` policy takes precedence over
  thresholds and selects `configured-full`; `false` selects curve control.
- Requested output is clamped to each fan's integer min/max before `_output`.
- Invalid or missing policy fields, malformed INI, invalid curves, or Boolean
  text other than case-insensitive `true`/`false` after INI whitespace handling
  also enter global `config-failsafe`, command every known maximum, and persist
  until restart without rewriting administrator configuration.
- Unsafe curve calculation follows and latches `config-failsafe` until restart.
  Each cycle calls `read_actual_rpm()` for every fan, reopening its `_input`
  path. Successful values feed verbose telemetry. A failed read reports
  `actual_rpm=unknown`, omits the rolling mean, commands every controllable fan
  maximum, and enters `sensor-failsafe` without starting sensor recovery.

## 5. Workflows

### Startup and operation

1. Start `t2fand` through the installed OpenRC service, or use a foreground
   invocation for an authorized local check.
2. Require root, prepare `/run/t2fand.pid`, discover every deduplicated fan
   candidate, require all candidates to be complete and controllable, and
   generate `/etc/t2fand.conf` only when absent.
3. Validate every detected fan policy. A defect is reported and enters global
   `config-failsafe` after manual mode begins when known maxima are available;
   it does not silently normalize the file.
4. Install SIGTERM/SIGINT request handlers, write the daemon PID, enable manual
   mode, and enter the outer `try/finally` lifecycle.
5. Re-discover sensors each second, control all fans from the hottest valid
   reading or fail high, emit optional verbose telemetry, and reopen sysfs paths
   for each operation.

Configuration is read once at startup. No live reload is implemented.

### Shutdown and recovery

Handled SIGTERM/SIGINT only set the shutdown request. After control starts, the
normal lifecycle reports `shutting-down`, then attempts manual-mode disable per
fan and owned-PID removal. An unexpected ordinary `Exception` after manual
control starts is converted to fatal `control-error` handling: its original
diagnostic is emitted as critical, maximum output is attempted independently on
every fan, manual mode is disabled independently per fan, and owned-PID removal
is attempted. Cleanup failures are reported, exit is nonzero, and no normal
stopped summary is emitted. Pre-control unexpected exceptions are not converted;
`BaseException` is outside this handling. No prior manual state is recorded or
restored. Cleanup is best effort and is not guaranteed after SIGKILL, power
loss, kernel panic, interpreter/native abort, hardware failure, or unavailable
write authority.

OpenRC routes the foreground streams through util-linux logger. Its static
directives describe bounded respawn and backoff; local lifecycle and logger
delivery remain unknown.

### Local installation

The `Makefile` declares only `.PHONY: install test` and performs no compilation.
Its `install` target is unconditional OpenRC installation:

- `DESTDIR` prefixes all installed paths;
- `BINDIR` defaults to `/usr/bin` and is overridable;
- `OPENRC_INITDDIR` defaults to `/etc/init.d` and is overridable;
- `t2fand` installs with mode 0700;
- `t2fand.initd` installs as `t2fand` with mode 0755.

Its `test` target runs `python3 -m unittest discover -s tests -p 'test_*.py'`.

Installation performs no service action and does not enable or start the daemon.
Staged output, host writes, and service state are unknown.

### Package and release

`PKGBUILD` declares package `t2fand` release `2.0.0-1` (`pkgver=2.0.0`,
`pkgrel=1`), target `x86_64`, GPL3, dependencies `linux-t2`, `python`, and
`util-linux`, and build dependency `git`. Its `build()` function does nothing.
Its `package()` function directly installs only `/usr/bin/t2fand` mode 0700 and
`/etc/init.d/t2fand` mode 0755. It creates no systemd directory or payload.
Package build output and the exact remote source result are unknown.

### Administrator service workflow

OpenRC is the sole supported manager. Optionally add `t2fand` to the `default`
runlevel with `rc-update`, then use `rc-service` for start, status, stop, or
restart. `/etc/conf.d/t2fand` may set `t2fand_args`, including `--verbose`.
These commands and lifecycle semantics are static source evidence; local
runlevel, service execution, and log persistence are unknown.

### Lifecycle mapping

| Lifecycle     | OpenRC                                                          |
| ------------- | --------------------------------------------------------------- |
| Start         | `rc-service t2fand start`                                       |
| Stop          | `rc-service t2fand stop`                                        |
| Status        | `rc-service t2fand status`                                      |
| Restart       | `rc-service t2fand restart`                                     |
| Exit recovery | Five respawns per 60 seconds, two-second base/incremental delay |
| Enablement    | `rc-update add t2fand default`                                  |

OpenRC runs `/usr/bin/t2fand` as the foreground daemon. Its respawn, delay,
detachment, backoff, and explicit-stop semantics are static source/directive
evidence; all local manager lifecycle results are unknown.

`output_logger` submits stdout at `daemon.info` and `error_logger` submits
stderr at `daemon.err`, both tagged `t2fand`, to the administrator-selected
syslog receiver. A running receiver is required for persisted logs; its
destination is unknown.

The workflow triggers on push and pull request in `ubuntu-latest`. Checkout is a
separate unconditional `actions/checkout@v3` step. Build, checksum printing, and
package upload each require absence of `[no build]`. Tag creation and release
additionally require absence of `[no rel]`; they also require absence of
`[no build]`. `[draft]` and `[prerel]` set release flags. Pull-request
commit-marker behavior is `unknown`: the workflow uses
`github.event.head_commit.message`, but local evidence does not establish its
pull-request value. The step named `Create Tag` only sources `PKGBUILD`, emits
`pkgver` as an output, and prints `pkgver` and `pkgrel`; it does not execute a
tag command. Actual tag creation and remote release-action behavior are
`unknown`. Workflow execution is `unknown`. The release file list also names
`*.zip`, while no zip creation step is shown.

### Migration and rollback

No migration, approval, or release rollback procedure is defined. README defines
concise operator onboarding under REQ-051 and intentionally omits the former
local configuration backup/restore step from manual-check guidance. Exhaustive
configuration and recovery truth remains in `SPEC.md` and this file. Prior
manager-switching guidance is superseded; external procedures are `unknown`.

## 6. Constraints and invariants

- The script must run with effective UID zero. Installation writes absolute
  system paths and normally also needs privilege.
- At least one discovered fan is required, and every resolved-path-deduplicated
  fan candidate must be complete and controllable. A usable positive CPU reading
  is required for normal control. Every selected temperature is parsed from
  signed millidegree text; failed values are `unknown`, not numeric sentinels.
  Any selected input failure, including CPU, enters recoverable sensor fail-safe
  while control survives; absent GPU topology does not.
- Fan output stays within each fan's reported min/max before writing.
- After manual control starts, an unexpected ordinary `Exception` is fatal
  `control-error`; maximum attempts, per-fan manual cleanup, and owned-PID
  removal remain independent, and exit is nonzero. Pre-control unexpected
  exceptions and `BaseException` are outside this conversion.
- One policy section is required for each fan found at startup.
- The controller retains no more than five valid hottest samples, polls once per
  second, bypasses history in fail-safe modes, and requires five valid recovery
  cycles before normal smoothing.
- Runtime state is local: config persists; PID and temperature/policy objects
  are process/runtime state; sysfs state belongs to the kernel/device boundary.
- Temperature topology and fan sysfs paths are re-discovered/reopened as
  specified; no open sysfs handle is retained.
- OpenRC is the only supported service manager and `t2fand.initd` is the only
  service definition.
- The daemon owns `/run/t2fand.pid`. OpenRC omits `pidfile`; supervisor state is
  separate.
- OpenRC controls are `supervisor="supervise-daemon"`, `respawn_delay="2"`,
  `respawn_max="5"`, `respawn_period="60"`,
  `supervise_daemon_args="--respawn-delay-step 2"`, and `retry="SIGTERM/5"`.
  `need localmount` and soft `use logger` are present; no network, background,
  daemonization, or supervisor `pidfile` setting is present.
- The PKGBUILD source has no revision pin and uses `sha256sums=('SKIP')`.
  Reproducibility, provenance, and local/package equivalence remain `unknown`.
- `make test` is the documented project-native test target. Test execution and
  packaging CI are not product-runtime validation and are not claimed here.

## 7. Security

The daemon is a root process with authority to write `/run/t2fand.pid`, create
`/etc/t2fand.conf` on first run, and write fan sysfs controls. The local
administrator controls configuration. Ownership and permission hardening for
config and sysfs are `unknown`.

There is no documented authentication, authorization layer, encryption, secret
store, or network listener. The local administrator controls configuration;
malformed policy is globally fail-safe when maximum control remains available.
The daemon uses direct flushed output and service-level logger routing, not
Python logging or direct syslog APIs.

The PID check tests only whether `/proc/<pid>` exists. It does not authenticate
process identity or provide atomic locking, so collisions and races are
possible. Manual-mode disable is attempted on the common cleanup route; prior
state is not recorded, and abrupt-failure outcomes are `unknown`.

Package/release trust crosses the Git checkout action, the Arch container image,
the keyserver-imported GPG key, GitHub Actions, and the unpinned Git source in
`PKGBUILD`. These are declared dependencies, not locally verified guarantees.
The workflow passes `GITHUB_TOKEN` to its release action; no secret value is
recorded here.

Do not add secrets, treat remote metadata as proof, or treat README examples as
runtime-safety evidence.

## 8. Validation

### Evidence available

The current evidence is static inspection of `t2fand`, `README.md`, `Makefile`,
`PKGBUILD`, `t2fand.initd`, `tests/test_t2fand.py`, and
`.github/workflows/build.yml`, summarized in `SPEC.md`. It verifies source
expressions, fake-fixture test definitions, artifact paths/modes, unconditional
OpenRC install rules, logger/package declarations, and integration settings; it
does not verify execution.

The project-native test command is `make test`; it is present and was not
executed in this documentation sync. No passing test result, hardware fixture
run, build result, package artifact, service run, release run, syslog delivery,
or compatibility matrix is claimed.

Current static validation target:

1. Confirm `t2fand.initd` is the sole service source, with foreground
   `supervise-daemon`, no `pidfile`, no background/daemonization setting, local
   filesystem ordering, soft logger use, configurable args, and no network
   dependency.
2. Confirm `t2fand.service` and all systemd install/package paths are absent.
3. Confirm unconditional `DESTDIR`/`BINDIR`/`OPENRC_INITDDIR` installation,
   exact source payload, and modes 0700/0755 in `Makefile`.
4. Confirm `PKGBUILD` uses `pkgname=t2fand`, `pkgver=2.0.0`, `pkgrel=1`, exactly
   the daemon and OpenRC init payload, `util-linux`, and no selected syslog
   daemon.
5. Confirm daemon ownership of `/run/t2fand.pid` and separate OpenRC supervisor
   state.
6. Confirm global hwmon/CPU/DRM discovery, numeric DRM filtering, deduplication,
   one-read cycles, hottest selection, recoverable sensor fail-safe for selected
   failures including CPU, five-cycle recovery, configured-full mean bypass, RPM
   fail-high without rolling mean or new sensor recovery, rate-limited default
   errors, verbose fields, post-control ordinary-`Exception` fatal conversion,
   and independent fatal cleanup from source/tests. Confirm absent-CPU,
   config-generation-I/O, and partial-discovered-fan fixture definitions;
   partial fan authority/control loss is fatal.
7. Confirm five respawns per 60 seconds, two-second base/incremental delay,
   explicit-stop suppression, and logger directives from source evidence.

Staged installation, package build, runtime, hardware, OpenRC lifecycle, and
syslog results remain unknown. No README snippet or lifecycle command was
executed.

### Retired and pending validation

Old `INIT_SYSTEM` selector and auto-detection checks are superseded. They are
not OpenRC-only validation. Runtime lifecycle, package build, staged output,
OpenRC syntax-tool, and hardware checks remain unverified.

### Runtime signals

The script defines diagnostics for non-root startup, fan/control failure,
duplicate/stale PID state, configuration generation/validation, sensor/GPU
transitions, modes, verbose telemetry, and handled shutdown. `/run/t2fand.pid`
is only a liveness hint, not an authenticated health check. No metrics, tracing,
endpoint, alerting, or audit store is defined. Service stdout/stderr transport
and persistence are receiver-dependent and `unknown`.

Source/test inspection covers the revised daemon, OpenRC, install, package, and
documentation surfaces in `SPEC.md`; it is not a passing test result. Runtime
fan safety, signal cleanup under real failure, PID races, hardware support,
package provenance, service operation, staged installation, package build,
syslog delivery, and CI execution remain `unknown` or pending.

The repository's `dprint.json` associates Markdown only with `*.md.jinja`.
Ordinary `.md` files, including this file, are not associated; formatting this
file must not be represented as a successful dprint Markdown check.

## 9. Known failures and decisions

### Known failure modes

- Non-root startup, no discovered fan, any incomplete/invalid deduplicated fan
  candidate, or loss of maximum write authority is fatal. Selected sensor
  failures, including unusable or absent CPU input, and config failures with
  writable maxima remain alive at maximum; failed actual RPM reads also fail
  high.
- A live PID path blocks startup; malformed or stale PID state is diagnosed and
  removed when possible. Identity locking and atomicity remain unimplemented.
- Missing/invalid policy, malformed INI, non-finite or unordered thresholds,
  invalid curves, and non-Boolean values enter global config fail-safe. Unsafe
  curve calculation follows the same path. Repair requires restart.
- Missing or failed selected inputs, including CPU inputs, trigger recoverable
  sensor fail-safe when maximum control survives; missing GPU topology alone
  does not. Five valid cycles are required for sensor recovery; local hardware
  disappearance and recovery are untested. Failed actual RPM reads fail high
  without initiating sensor recovery.
- Fan writes, manual-mode writes, actual RPM reads, partial writes, and abrupt
  termination have only source-level behavior; target-host outcomes remain
  unknown.
- After manual control starts, an unexpected ordinary `Exception` is converted
  to fatal `control-error` handling with the original critical diagnostic,
  independent maximum attempts, independent fan/PID cleanup, nonzero exit, and
  no normal stopped summary. Pre-control unexpected exceptions are re-raised;
  `BaseException` is not caught. Runtime outcomes remain unknown.
- OpenRC directives describe bounded respawn/backoff and logger routing, but
  local lifecycle, directive support, receiver delivery, and persistence are
  untested.
- The release workflow lists zip files without a shown zip-producing step.

### Settled decisions

- Treat local source and checked-in integration files as implementation
  evidence; label execution separately.
- Treat OpenRC as the sole supported manager and `t2fand.initd` as the sole
  service definition. Its 0.62.10 source/directive semantics are static
  evidence; local lifecycle remains unknown.
- Preserve the historical systemd-authoritative and dual-manager states as
  superseded; do not rewrite them as current behavior.
- Keep the foreground daemon and `/run/t2fand.pid` ownership separate from
  OpenRC supervisor state.
- Keep OpenRC as the only manager and the two-file payload boundary.
  `util-linux` is explicitly required for `/usr/bin/logger`; no syslog daemon is
  selected.
- Treat package provenance and local/package equivalence as `unknown` because
  the source is unpinned and checksum verification is skipped.
- Record `make test` as the project-native command without claiming execution or
  passing results.
- Keep implementation fixes, packaging changes, CI changes, and SPEC changes
  outside this documentation sync.

### Service integration transition

- `H-001` (superseded): the prior checked-in state had only the systemd unit;
  `Makefile` installed only systemd, and `PKGBUILD` named `t2fand-openrc` while
  shipping only the executable and systemd unit. OpenRC was unsupported and
  metadata was contradictory. This remains historical evidence.
- `H-002` (superseded pre-implementation transition): the 2026-08-27 contract
  reconciliation added the OpenRC contract, Makefile selection/staging, and both
  package service definitions. It superseded REQ-015 and REQ-016 only; REQ-014
  and the systemd unit remained unchanged. This remains the prior contract
  transition.
- `H-003` (superseded dual-init implementation state): the checked-in
  `t2fand.initd`, selector Makefile, systemd unit, and both-definition PKGBUILD
  were present; systemd was authoritative. Static evidence did not claim staged
  installation, package artifacts, OpenRC syntax/lifecycle, hardware, or other
  runtime success.
- `H-004` (superseded static implementation): `t2fand.service` was deleted;
  `t2fand.initd` is the sole service definition. `Makefile` installation is
  unconditional OpenRC through `DESTDIR`, overridable `BINDIR` (default
  `/usr/bin`), and overridable `OPENRC_INITDDIR` (default `/etc/init.d`), with
  source modes 0700/0755. `PKGBUILD` retains `pkgname=t2fand`, sets `pkgrel=2`,
  and installs only the daemon and init script. No systemd payload exists; the
  OpenRC dependency is unknown. This was the pre-fail-safe daemon behavior and
  remains historical evidence only.
- `H-005` (superseded implementation transition): the daemon then performed
  global hwmon/CPU/exact-numeric-DRM discovery, hottest selection, explicit GPU
  topology transitions, global config/sensor fail-safe control, five-cycle
  recovery, verbose telemetry, and independent cleanup. The init script now has
  bounded/backed-off respawn, configurable arguments, local-filesystem and soft
  logger dependencies, and util-linux logger routing. At that historical point,
  `PKGBUILD` was `1.2.0-3`; that release fact is superseded by `H-010`. The
  two-file OpenRC payload boundary remains unchanged.
- `H-006` (evidence boundary): source and test-file inspection verifies the
  revised static surfaces and the `make test` target. Tests were not executed;
  hardware, OpenRC lifecycle, logger delivery/persistence, staged install,
  package build, and CI remain unverified.
- `H-007` (final correction sync): source and test definitions now record five
  consecutive valid sensor-recovery cycles, RPM-failure maximum targets without
  a rolling mean or new sensor recovery, configured-full mean bypass, default
  error rate limiting, and fatal cleanup/static integration coverage. These are
  static definitions only; tests and runtime/integration outcomes remain
  unverified.
- `H-008` (current cleanup/reporting correction): pre-control fatal exits do not
  emit the normal stopped summary; cleanup remains conditional on owned runtime
  state while fatal maximum attempts remain independent. Source and test
  definitions are static evidence only; execution remains unverified.
- `H-009` (current safety/test-definition correction): every discovered,
  resolved-path-deduplicated fan candidate must be controllable; partial fan
  authority/control loss is fatal. Selected sensor failures, including CPU,
  remain recoverable sensor-failsafe when control survives. Absent-CPU,
  config-generation-I/O, and partial-fan fake fixtures are present; `make test`
  remains unexecuted.

- `H-010` (current release reconciliation): checked-in `PKGBUILD` now declares
  intentional release `2.0.0-1` (`pkgver=2.0.0`, `pkgrel=1`). The prior
  `1.2.0-3` package fact remains superseded history; payload, dependency, and
  metadata outcomes remain unverified.
- `H-011` (current documentation ownership transition): REQ-051 makes README
  concise operator onboarding for actions, safety, configuration, OpenRC,
  observability, and testing. Exhaustive limits, modes, telemetry, fail-safe
  behavior, and implementation truth remain owned by `SPEC.md` and this file.
  The prior full-contract README placement remains superseded history.
- `H-012` (current post-control exception correction): after manual control
  starts, the source converts an unexpected ordinary `Exception` to fatal
  `control-error` handling, preserves its critical diagnostic, independently
  attempts known maxima and fan/PID cleanup, exits nonzero, and omits the normal
  stopped summary. Pre-control unexpected exceptions and `BaseException` remain
  outside this conversion; runtime outcomes remain unverified.

### Superseded daemon behavior

The pre-revision implementation facts are retained here as superseded history:

- Fan discovery used the first T2 fan glob match and direct `fan*_input`
  children; it read fan limits/input, clamped requested output, toggled manual
  mode, and could continue with zero fans.
- CPU discovery used a coretemp `temp1_input` glob and a `-1` sentinel; textual
  zero was skipped. GPU discovery used a literal `card0` path and only changed
  CPU/GPU source selection.
- Each cycle selected CPU or CPU/GPU maximum, appended the selected value to a
  five-entry mean, applied the three curves, and wrote clamped fan output.
  Topology was not re-discovered during operation and sysfs handles were not
  explicitly bounded by the current contract.
- Missing required config sections or an invalid curve exited startup; Boolean,
  threshold-order, conversion, and math failures were not explicitly handled.
  The generated four-key defaults were `55`, `75`, `linear`, and `false`, and
  only exact `always_full_speed=true` selected maximum.
- The old PID path rejected a live `/proc/<pid>` and removed a stale PID, but
  malformed PID text could escape parsing; identity locking and atomicity were
  absent.
- SIGTERM/SIGINT cleanup sequentially disabled manual mode and removed the PID;
  one cleanup error could prevent later cleanup. Abrupt-failure behavior was
  unknown.
- The prior init directives used unlimited all-exit respawn, a constant
  two-second delay, and no logger routing; the prior package was `1.2.0-2`
  without `util-linux`.

### Superseded template state

The previous CONTEXT was a Copier/Lithon scaffold describing reviewer-created
`.agents/prompts/` drafts, prompt synthesis, and agent dispatch rules. That was
unrelated template documentation, not t2fand runtime behavior. It is superseded
by this code-derived context. The repository may still contain those template
files; their presence does not expand the daemon's implementation scope.

## 10. Maintenance

Maintain the path, option, signal, service, install, package, and workflow facts
in this file when verified local implementation changes. Update the human guide
only when operator-facing setup or behavior changes. Reconcile contract changes
through the `SPEC.md` owner before synchronizing this context.

README now provides concise operator onboarding under REQ-051: prerequisites,
installation and staging paths, four-key configuration, OpenRC operation, logger
routing, safety limits, and the project-native test target. It is operator
guidance, not runtime evidence. No monitoring, upgrade cadence, hardware test
routine, or ownership handoff is defined. Re-check package source pinning,
checksum policy, OpenRC runtime behavior, logger receiver configuration, and CI
execution before relying on a release artifact.

## 11. Agent rules

`AGENTS.md` owns routing, onboarding, edit boundaries, safety rules, and
protected surfaces. This file owns deeper t2fand implementation context. Never
edit `SPEC.md` as part of a context sync; if local evidence contradicts its
contract, stop and report the exact mismatch for reconciliation.

Do not run README snippets. Do not research remote sources or perform remote
maintenance. Preserve unrelated working-tree changes. Keep unsupported behavior
and unexecuted claims explicitly `unknown`.

## 12. Current summary

Current source shape: a root-required foreground Python daemon discovers global
hwmon, CPU, and exact numeric DRM-card temperatures, requires one usable
positive CPU channel for normal control, and enters recoverable sensor-failsafe
on any selected sensor read/parse/fault failure, including CPU, when fan control
survives. It selects the hottest valid input and applies global fail-safe
decisions to all controllable fans. Every discovered, resolved-path-deduplicated
fan candidate must be complete and controllable; partial authority/control loss
is fatal. Normal control samples once per second over at most five valid maxima;
sensor recovery requires five valid cycles. Configured-full and RPM telemetry
failure omit the rolling mean; RPM failure commands maximum without starting
sensor recovery. It reports explicit modes, verbose target/actual RPM telemetry,
rate-limited default errors, and best-effort signal/fatal cleanup. After manual
control starts, an unexpected ordinary `Exception` is converted to fatal
`control-error` handling with independent maximum attempts and fan/PID cleanup,
nonzero exit, and no normal stopped summary; pre-control unexpected exceptions
and `BaseException` remain outside this conversion. OpenRC is the sole service
integration; `t2fand.initd` supervises the foreground daemon, which owns
`/run/t2fand.pid`. The Makefile and PKGBUILD provide the exact daemon/init
payload with source modes 0700/0755; `pkgname=t2fand` and release `2.0.0-1`;
util-linux supports service logger routing. No systemd payload exists.

Static source/test inspection is complete for the revised local surfaces;
absent-CPU, config-generation-I/O, and partial-fan fake fixtures are present,
and `make test` is present but was not executed in this sync. Not verified:
hardware behavior, compatibility coverage, test pass/fail, build/release
success, staged installation, package build, OpenRC lifecycle, directive
support, syslog delivery/persistence, and equivalence between the unpinned
`PKGBUILD` source and this checkout.
