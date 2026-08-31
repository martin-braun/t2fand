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
chip. It selects global `smc` or `t2fand` control at startup. SMC releases
`fan*_manual` control and observes the exposed hwmon and fan inputs. T2fand mode
selects the hottest valid temperature and writes clamped targets through
reopened Linux sysfs paths.

This control-mode revision establishes an observation baseline for later
MacBookPro16,1 SMC characterization. It makes no claim that Apple's internal fan
algorithm was reconstructed.

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
- Configuration has global `[General] control_mode=smc|t2fand`. Generated files
  select `smc`; an existing file without `[General]` infers `t2fand`, emits
  exactly one warning, and is not rewritten. `manual`, `auto`, `smc_auto`, and
  aliases are rejected. FanN policy is used only in t2fand mode.
- Fan discovery uses only T2 candidates below `devices/*/*/*/*/APP0001:00/fan*`;
  it expands `fan*_input`, deduplicates resolved base paths, and requires every
  discovered candidate to be complete and controllable. Class-hwmon temperature
  paths remain sensor inputs, not fan candidates.
- It re-discovers and reopens fan and temperature paths each cycle, reads each
  deduplicated temperature input once, labels optional metadata, and selects the
  hottest valid value. When readable, a vgaswitcheroo `DIS:Off` dGPU PCI address
  excludes only matching resolved temperature paths. CPU availability requires
  one selected, fault-free, parsed, positive CPU channel; a non-positive sibling
  does not cancel it. In t2fand mode, any selected input read/parse/fault
  failure, including CPU, enters recoverable sensor-failsafe while fan control
  survives. In SMC mode, thermal and tachometer failures remain `unknown` and
  degrade monitoring without takeover. GPU inputs below exact numeric DRM cards
  are optional and report missing/recovery transitions.
- T2fand control samples once per second, keeps at most five valid maxima by
  default, and uses their mean rounded to two decimals. T2fand sensor/config
  fail-safe modes bypass smoothing and attempt every known maximum. Valid
  `configured-full` policies also bypass normal smoothing. Sensor recovery needs
  five consecutive valid cycles by default and resets prior history. Both modes
  emit one flushed compact telemetry record per second by default; it contains
  the hottest eligible sensor label/value and each fan's actual RPM. `-v`
  selects the full record in either mode. No mode implies verbose output.
- Configuration is generated only when absent, validated globally once at
  startup, and read from `/etc/t2fand.conf`. Fan policies are ignored for SMC;
  malformed FanN policy is warned but does not select `config-failsafe` there.
  Apple SMC owns fan control in SMC; t2fand owns control and applies FanN
  policies automatically in t2fand mode. T2fand invalid policy remains
  `config-failsafe` until restart; an unsafe runtime policy calculation latches
  the same mode until restart. Valid `always_full_speed=true` is
  `configured-full`.
- SIGTERM and SIGINT only request shutdown. SMC startup and each cycle release,
  verify, and maintain `fan*_manual=0`; clean shutdown leaves SMC control.
  T2fand cleanup attempts maximum on fatal paths, disables daemon control
  independently per fan, and removes the daemon PID file when owned. Cleanup
  failures are reported. After control starts, an unexpected ordinary
  `Exception` is converted to fatal control handling; pre-control unexpected
  exceptions and `BaseException` remain outside this conversion.
- `t2fand.initd` is the sole root OpenRC definition for the foreground daemon.
- `Makefile` unconditionally installs the OpenRC definition and conf.d file,
  stages with `DESTDIR`, and applies modes 0700/0755/0644 to the daemon, init,
  and conf.d files.
- `PKGBUILD` names local `t2fand`, `t2fand.initd`, `t2fand.confd`, and
  `Makefile` sources and delegates package staging to
  `make DESTDIR="$pkgdir" install`. It ships the three-file payload, preserves
  `etc/conf.d/t2fand` through `backup=()`, and has `pkgname=t2fand`, release
  `2.0.1-2` (`pkgver=2.0.1`, `pkgrel=2`), and `util-linux` for
  `/usr/bin/logger`.
- `_parser()` exposes `-v`/`--verbose`, path overrides `-c`/`--config-path`,
  `-p`/`--pid-path`, and `-s`/`--sysfs-path`, plus positive numeric overrides
  `-r`/`--sensor-recovery-cycles`, `-l`/`--sample-limit`, and
  `-e`/`--error-reminder-seconds`. Defaults are `/etc/t2fand.conf`,
  `/run/t2fand.pid`, `/sys`, `5`, `5`, and `60.0`; numeric argparse validation
  rejects zero, negative, nonnumeric, NaN, and infinite values before the root
  check. Runtime settings are passed per process; module defaults are unchanged.
- `t2fanbench.py` formats every `log()` print as local wall-clock
  `MMM DD HH:mm:ss [t2fanbench] MESSAGE`, using an explicit English month table,
  zero-padded day/time fields, and flushed output without a leading blank line
  or `===` decoration. It retains the `logger` subprocess side effect and does
  not alter `stress-ng` child output.
- Before those benchmark side effects, `t2fanbench.py` uses standard-library
  `shutil.which("stress-ng")` to check PATH availability. If unavailable, it
  writes exactly `error: stress-ng is required but was not found in PATH` to
  stderr and returns status `1`, without traceback, cache creation, benchmark or
  logger output, sleep, or subprocess launch. Its available-path sequence
  remains unchanged. These facts remain source/test-definition evidence;
  execution is unverified.
- `.gitignore` ignores local `opencode.json` and generated build/release paths;
  `opencode.json` is not a product or package input. No removal of ignored local
  state is claimed.
- `tests/test_t2fand.py` is a standard-library unittest suite using temporary
  fake sysfs/config trees and mocks. Definitions cover generated SMC config,
  legacy-config inference, SMC release/maintenance and degradation, compact
  default/full verbose telemetry, deterministic hottest selection and unknown
  values, CLI defaults/consumers/pre-mutation validation, custom PID cleanup,
  ownership escalation, shutdown release, and t2fand regressions. Integration
  definitions cover the one-variable conf.d override, three-file staging/modes,
  package source/backup preservation, benchmark timestamp formatting, and the
  benchmark prerequisite ordering/failure path. The benchmark implementation
  uses an explicit English month table for locale independence. Its execution
  remains unverified. `make test` is the project-native target and remains
  unexecuted.
- No systemd unit or systemd payload is present.
- `.github/workflows/build.yml` provides package build, artifact, and release
  automation.
- README/CONTEXT synchronization follows REQ-051 and REQ-074: README is concise
  operator onboarding for prerequisites, installation, both control modes, the
  conf.d override, compact/full telemetry, CLI options, benchmark timestamps,
  the stress-ng PATH prerequisite, OpenRC operation, safety, and project-native
  testing. Exhaustive contract and implementation truth remain here and in
  `SPEC.md`.

These are source/configuration facts. Test execution, runtime, hardware,
privileged install, staged output, package-build, release, syslog delivery, and
CI success are not verified.

### Gaps and open status

- `make test` and a local unittest suite are present, but this documentation
  sync does not claim test execution or passing results.
- OpenRC operation is unverified. Its checked-in definition and directive values
  are static evidence, not a runtime claim.
- `PKGBUILD` uses checked-in local source names with `sha256sums=('SKIP')`;
  package provenance and build output remain `unknown`.
- Configuration reload, schema migration, rollback, and fan-topology migration
  are not defined.
- Outcomes after pre-control unexpected exceptions remain `unknown`; those
  exceptions are not converted to fatal control handling. `BaseException`,
  SIGKILL, power loss, kernel panic, interpreter/native abort, and hardware or
  OpenRC runtime outcomes remain `unknown` beyond the checked-in paths.
- The exact syslog receiver, destination, and persistence result are unknown;
  util-linux `logger` is only the declared service transport.
- SMC ownership behavior, telemetry values, Linux sensor/tachometer degradation,
  and clean shutdown on target hardware are unverified. MacBookPro16,1 SMC
  characterization is future work; Apple's internal algorithm is not claimed to
  be reconstructed.

## 3. Architecture

### Components and boundaries

1. The `t2fand` process performs privilege checks, discovery, configuration,
   mode-specific control, telemetry, and signal-request cleanup.
2. `Fan` wraps one sysfs fan base path. Discovery reads integer `_max` and
   `_min`; control clamps and reopens `_output`; t2fand mode reopens `_manual`.
   Tachometer reads reopen `_input` and are diagnostic.
3. Fan discovery scans only the T2 `APP0001:00` layout and deduplicates resolved
   fan bases. Sensor discovery separately unions global hwmon, coretemp, and
   `device/hwmon` below exact numeric DRM cards. A readable vgaswitcheroo
   `DIS:Off` PCI address filters matching resolved temperature candidates only.
   Resolved aliases are deduplicated; each selected input is read once per
   cycle. Optional names, labels, and fault flags enrich labels/classification
   without optional labels gating operation.
4. `configparser` reads the selected config path (default `/etc/t2fand.conf`)
   once at startup. It resolves global `control_mode`; one validated four-value
   policy is stored for each detected fan. Fan policy defects are relevant to
   t2fand mode only. Invalid t2fand policy is a global config fail-safe when
   maximum control remains available.
5. Controller state keeps normal and recovery histories, mode/reason, GPU
   topology, shutdown request, error reminder timing, and per-process runtime
   settings in memory.
6. OpenRC, `make install`, the Arch recipe, and GitHub Actions are integration
   surfaces around the script. They do not add a second controller.

### Discovery and control/data flow

Startup checks effective UID, handles the selected PID path (default
`/run/t2fand.pid`), discovers every T2-only deduplicated fan candidate and
requires all candidates to be complete and controllable, generates or validates
`/etc/t2fand.conf`, resolves the global mode, installs signal-request handlers,
writes the PID, and enters the outer lifecycle cleanup route. SMC releases and
verifies `fan*_manual=0`; t2fand enables daemon control. Fan-policy defects are
fail-safe only in t2fand mode. In SMC, release or maintenance loss attempts
release, then known maxima, then fatal `control-error` if ownership cannot be
restored. After control starts, an unexpected ordinary `Exception` is converted
to fatal handling; its diagnostic, cleanup, and nonzero exit remain separate
from runtime evidence.

Each one-second cycle re-discovers temperature inputs, reads each resolved path
once, parses signed integer millidegrees Celsius, treats faulted/failed values
as `unknown`, and selects the highest valid value. A readable vgaswitcheroo
`DIS:Off` dGPU PCI address excludes matching resolved paths before reading;
unavailable switch state leaves general discovery enabled. SMC maintains each
fan's `fan*_manual=0`, reads fan manual/target/actual observations, and emits
compact telemetry by default. Thermal or tachometer failure only degrades SMC
monitoring. T2fand mode requires a positive CPU channel; selected failures enter
recoverable sensor-failsafe, bypass history, command known maxima, and retry.
T2fand normal history uses the configured per-process sample limit, five by
default; the configured recovery-cycle count is also five by default.

In t2fand mode, each fan policy converts the rolling mean to a clamped integer
output using the legacy linear, cubic exponential, or logarithmic expression. A
valid configured full-speed policy bypasses normal smoothing. Actual RPM failure
reports `unknown` and fails high in t2fand mode; it degrades SMC monitoring
without output takeover. SMC `target_rpm` is an observed current output value,
not a daemon command. The loop sleeps one second. All sysfs operations reopen
their paths; no file handle is retained.

This is a single process with direct local file I/O. No queue, watcher, network
listener, logging framework, or separate worker is defined; telemetry is direct
flushed key-value output. Both modes emit compact telemetry by default; `-v` or
`--verbose` selects the full record. Compact records contain only hottest
eligible sensor identity/value and per-fan actual RPM. Full records retain
sensor, topology, state, reason, policy, target, and actual-RPM fields. No mode
implies verbose output.

Reported global modes are `smc` and `t2fand`. T2fand submodes are `curve`,
`configured-full`, `config-failsafe`, `sensor-failsafe`, `control-error`, and
`shutting-down`; SMC degradation is not `sensor-failsafe`. Mode, reason, and GPU
topology changes are emitted on transition; repeated default problems are
rate-limited with a 60-second reminder interval. Every mode emits one record per
one-second cycle. The default compact record contains only the hottest eligible
sensor label/value and each fan's `actual_rpm`, with `unknown` for no valid
hottest sensor or unavailable RPM. `--verbose` records in both modes add sensor,
topology, state, reason, policy, target, and actual-RPM fields; t2fand records
add the curve policy and rolling mean when applicable. SMC never implies verbose
output.

## 4. Interfaces

### Process and runtime paths

| Interface              | Local contract                                                                                                                                                                                                                                                                                                                                                                    |
| ---------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Executable             | `/usr/bin/t2fand` is the foreground daemon invoked by OpenRC. `-v`/`--verbose` selects full telemetry; without it both modes emit compact telemetry once per second. Unknown arguments fail before hardware mutation. Direct invocation is not a second service-manager workflow.                                                                                                 |
| PID file               | `/run/t2fand.pid` stores the daemon's decimal PID. A live `/proc/<pid>` path rejects startup; malformed or stale state is diagnosed and removed when possible. Identity locking and atomicity are not implemented.                                                                                                                                                                |
| Config file            | `/etc/t2fand.conf`, generated only when absent, resolved for global `control_mode`, validated at startup, and read once. Generated files select SMC; files without `[General]` infer t2fand with one warning and no rewrite.                                                                                                                                                      |
| CLI overrides          | `-c`/`--config-path`, `-p`/`--pid-path`, and `-s`/`--sysfs-path` default to `/etc/t2fand.conf`, `/run/t2fand.pid`, and `/sys`; `-r`/`--sensor-recovery-cycles`, `-l`/`--sample-limit`, and `-e`/`--error-reminder-seconds` default to `5`, `5`, and `60.0`. The numeric types are positive integer, positive integer, and positive finite float.                                  |
| Benchmark output       | `t2fanbench.py` `log()` prints local, locale-independent English `MMM DD HH:mm:ss [t2fanbench] MESSAGE` lines with flushed output, no leading blank/`===` decoration, and preserved `logger` side effect.                                                                                                                                                                         |
| Benchmark prerequisite | Before cache creation, benchmark/logger output, baseline sleep, or subprocess launch, `t2fanbench.py` checks `shutil.which("stress-ng")`. Missing `stress-ng` produces exactly `error: stress-ng is required but was not found in PATH` on stderr and status `1`, with no traceback or listed side effect. Available-path benchmark sequencing and child output remain unchanged. |
| Fan sysfs              | Read integer `<base>_max`, `<base>_min`, tachometer `<base>_input`, manual state, and observed target; SMC maintains `<base>_manual=0` and normally does not write `<base>_output`; t2fand writes clamped `<base>_output`.                                                                                                                                                        |
| Temperature sysfs      | Union global hwmon, coretemp, and exact numeric DRM-card descendants; parse signed integer millidegree-Celsius text. A matching vgaswitcheroo `DIS:Off` dGPU path is skipped. Failed values are `unknown`; aliases deduplicate by resolved path.                                                                                                                                  |
| Signals                | SIGTERM and SIGINT only request common cleanup. After t2fand control starts, an unexpected ordinary `Exception` becomes fatal `control-error` handling; pre-control unexpected exceptions and `BaseException` are outside this conversion. Other abrupt termination paths cannot guarantee cleanup.                                                                               |

### Configuration schema

There is one global `[General]` section and one section `Fan1` through `FanN`
per detected fan. `General.control_mode` is exactly `smc` or `t2fand`. Generated
files select `smc`; an existing file without `General` infers `t2fand`, warns
exactly once, and remains unchanged. `manual`, `auto`, `smc_auto`, and aliases
are invalid. Every detected fan section must contain:

```ini
[Fan1]
low_temp = 55
high_temp = 75
speed_curve = linear
always_full_speed = false
```

The generated FanN defaults are `55`, `75`, `linear`, and `false`. FanN policy
is validated and used only in t2fand mode. `speed_curve` must be `linear`,
`exponential`, or `logarithmic`. `always_full_speed` accepts only
case-insensitive `true` or `false` after INI whitespace handling. Thresholds
must be finite and satisfy `low_temp < high_temp`; malformed INI or invalid mode
fails startup, while missing or invalid FanN policy produces global
`config-failsafe` only in t2fand mode. The file is not rewritten on validation
failure.

### Service integrations

`t2fand.initd` is the sole checked-in service definition. It opens with
`#!/sbin/openrc-run`, sets `command=/usr/bin/t2fand`, reads
`/etc/conf.d/t2fand`, sets `command_args="${t2fand_args:-}"`, and uses
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

`t2fand.confd` declares only `t2fand_args=""`. Its comments state that `t2fand`
owns defaults and options, optional overrides pass through `t2fand_args`, and
`t2fand --help` is authoritative.

### Curve and fan behavior

- Validated t2fand configuration requires finite thresholds with `low_temp`
  strictly lower than `high_temp`; equal or inverted thresholds enter global
  `config-failsafe`. SMC does not use FanN policy.
- Between thresholds, `linear` interpolates linearly, `exponential` uses the
  script's cubic expression, and `logarithmic` uses its `math.log` expression.
- At or below `low_temp`, use the fan minimum; at or above `high_temp`, use the
  fan maximum. A valid `always_full_speed=true` policy takes precedence over
  thresholds and selects `configured-full`; `false` selects curve control.
- Requested output is clamped to each fan's integer min/max before `_output`.
- Invalid or missing t2fand FanN policy fields, invalid curves, or Boolean text
  other than case-insensitive `true`/`false` after INI whitespace handling enter
  global `config-failsafe` in t2fand mode, while remaining a dormant warning in
  SMC. Malformed or unreadable INI raises `StartupError` before control begins,
  with no fan mutation.
- Unsafe t2fand curve calculation follows and latches `config-failsafe` until
  restart. T2fand actual-RPM failure reports `actual_rpm=unknown`, commands
  every controllable fan maximum, and enters `sensor-failsafe` without starting
  sensor recovery. SMC actual-RPM failure reports `unknown` and only degrades
  monitoring. SMC `target_rpm` is an observed current output value, not a daemon
  command.

## 5. Workflows

### Startup and operation

1. Parse CLI arguments. Positive numeric validation and unknown-argument failure
   occur before the root check or filesystem mutation.
2. Start `t2fand` through the installed OpenRC service, or use a foreground
   invocation for an authorized local check.
3. Require root, prepare the selected PID path, discover every deduplicated fan
   candidate, require all candidates to be complete and controllable, and
   generate the selected config path only when absent.
4. Resolve `[General] control_mode`. A missing section infers t2fand, warns
   exactly once, and leaves the file unchanged. Validate FanN policy only for
   t2fand mode; SMC ignores those policy defects.
5. Install SIGTERM/SIGINT request handlers, write the daemon PID, release and
   verify SMC ownership or enable t2fand mode, and enter the outer lifecycle.
6. Re-discover sensors each second. SMC maintains `fan*_manual=0` and emits
   compact telemetry without normal output writes. T2fand applies policy from
   the hottest valid reading or fails high. Both modes emit compact telemetry by
   default; `--verbose` selects full telemetry.

Configuration is read once at startup. No live reload is implemented.

### Benchmark operation

`t2fanbench.py` first checks `shutil.which("stress-ng")`. The check precedes
cache creation, benchmark/logger output, baseline sleep, and every subprocess
launch. Missing `stress-ng` emits the exact stderr error, returns `1`, and has
no traceback or listed side effect. An available executable proceeds through the
existing benchmark sequence; benchmark execution remains unverified.

### Shutdown and recovery

Handled SIGTERM/SIGINT only set the shutdown request. After control starts, the
normal lifecycle reports `shutting-down`, then releases t2fand control per fan
and removes the owned PID. SMC clean shutdown leaves `fan*_manual=0`. An
unexpected ordinary `Exception` after control starts is converted to fatal
`control-error` handling; maximum escalation, per-fan release, and PID cleanup
remain independent. Cleanup failures are reported, exit is nonzero, and no
normal stopped summary is emitted. Pre-control unexpected exceptions and
`BaseException` remain outside this handling. Cleanup is best effort and is not
guaranteed after SIGKILL, power loss, kernel panic, interpreter/native abort,
hardware failure, or unavailable write authority.

OpenRC routes the foreground streams through util-linux logger. Its static
directives describe bounded respawn and backoff; local lifecycle and logger
delivery remain unknown.

### Local installation

The `Makefile` declares only `.PHONY: install test` and performs no compilation.
Its `install` target is unconditional OpenRC installation:

- `DESTDIR` prefixes all installed paths;
- `BINDIR` defaults to `/usr/bin` and is overridable;
- `OPENRC_INITDDIR` defaults to `/etc/init.d` and is overridable;
- `OPENRC_CONFDIR` defaults to `/etc/conf.d` and is overridable;
- `t2fand` installs with mode 0700;
- `t2fand.initd` installs as `t2fand` with mode 0755;
- `t2fand.confd` installs as `t2fand` with mode 0644.

Its `test` target runs `python3 -m unittest discover -s tests -p 'test_*.py'`.

Installation performs no service action and does not enable or start the daemon.
Staged output, host writes, and service state are unknown.

### Package and release

`PKGBUILD` declares package `t2fand` release `2.0.1-2` (`pkgver=2.0.1`,
`pkgrel=2`), target `x86_64`, GPL3, dependencies `linux-t2`, `python`, and
`util-linux`, and build dependency `git`. Its local source list is `t2fand`,
`t2fand.initd`, `t2fand.confd`, and `Makefile`; no `build()` function is defined
and `package()` runs `make DESTDIR="$pkgdir" install`.
`backup=('etc/conf.d/t2fand')` preserves administrator edits. The Makefile
stages only `/usr/bin/t2fand` mode 0700, `/etc/init.d/t2fand` mode 0755, and
`/etc/conf.d/t2fand` mode 0644. It creates no systemd directory or payload.
Package build output and checksum/provenance results are unknown.

### Administrator service workflow

OpenRC is the sole supported manager. Optionally add `t2fand` to the `default`
runlevel with `rc-update`, then use `rc-service` for start, status, stop, or
restart. `/etc/conf.d/t2fand` provides the sole supported OpenRC override,
`t2fand_args`; daemon defaults remain in `t2fand`. The init script sets
`command_args="${t2fand_args:-}"`. These commands and lifecycle semantics are
static source evidence; local runlevel, service execution, and log persistence
are unknown.

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

An existing config without `[General]` is a supported legacy config state: the
daemon warns exactly once, does not rewrite the file, and infers t2fand mode.
Adding `[General] control_mode=smc` or `t2fand` is an administrator change;
restart is required because configuration is read once. No approval or release
rollback procedure is defined. README intentionally omits the former local
configuration backup/restore step from manual-check guidance. Prior
manager-switching guidance is superseded; external procedures are `unknown`.

## 6. Constraints and invariants

- The script must run with effective UID zero. Installation writes absolute
  system paths and normally also needs privilege.
- At least one discovered fan is required, and every resolved-path-deduplicated
  fan candidate must be complete and controllable. Every selected temperature is
  parsed from signed millidegree text; failed values are `unknown`, not numeric
  sentinels. T2fand mode requires a usable positive CPU reading and enters
  recoverable sensor fail-safe on selected input failure; SMC degrades
  monitoring instead and never takes over for telemetry failure.
- T2fand fan output stays within each fan's reported min/max before writing. SMC
  maintains each fan's `fan*_manual=0` and does not normally write fan output.
- After t2fand control starts, an unexpected ordinary `Exception` is fatal
  `control-error`; maximum attempts, per-fan `fan*_manual` cleanup, and
  owned-PID removal remain independent, and exit is nonzero. Pre-control
  unexpected exceptions and `BaseException` are outside this conversion.
- One policy section is required for each fan found at startup in t2fand mode;
  SMC does not use FanN policy.
- T2fand control retains no more than the configured valid hottest samples
  (default five), polls once per second, bypasses history in fail-safe modes,
  and requires the configured valid recovery cycles (default five) before normal
  smoothing. Both modes emit one compact default telemetry record per cycle;
  `-v` selects the full record.
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
- `PKGBUILD` names checked-in local sources, uses `sha256sums=('SKIP')`, and
  marks `/etc/conf.d/t2fand` for backup. Reproducibility, package provenance,
  and build output remain `unknown`.
- CLI paths and policy values are process-local. Argparse validates positive
  integer recovery/sample values and positive finite reminder seconds before
  root checks or filesystem mutation; the selected PID path is used for cleanup.
- `t2fanbench.py` resolves `stress-ng` through the standard library before any
  cache, output, sleep, or subprocess side effect; missing availability returns
  status `1` with the exact stderr error and no traceback.
- OpenRC `command_args` consumes only `t2fand_args`. Absent, empty, and nonempty
  values are valid; daemon defaults and option validation remain in `t2fand`.
- `opencode.json` is ignored local state, not a product, daemon, package, or
  release input. Generated package/source staging, Python build/distribution,
  archive, log, signature, and zip paths are ignored and are not product payload
  or contract evidence.
- `make test` is the documented project-native test target. Test execution and
  packaging CI are not product-runtime validation and are not claimed here.

## 7. Security

The daemon is a root process with authority to write the selected PID path
(default `/run/t2fand.pid`), create the selected config path (default
`/etc/t2fand.conf`) on first run, and write fan sysfs controls below the
selected root (default `/sys`). The local administrator controls configuration.
Ownership and permission hardening for config and sysfs are `unknown`.

There is no documented authentication, authorization layer, encryption, secret
store, or network listener. The local administrator controls configuration;
malformed t2fand policy is globally fail-safe when maximum control remains
available. SMC does not take over for FanN policy or telemetry failure. The
daemon uses direct flushed output and service-level logger routing, not Python
logging or direct syslog APIs.

The PID check tests only whether `/proc/<pid>` exists. It does not authenticate
process identity or provide atomic locking, so collisions and races are
possible. T2fand control disable is attempted on the common cleanup route; SMC
release is maintained during operation and clean shutdown; prior state is not
recorded, and abrupt-failure outcomes are `unknown`.

Package/release trust crosses the Git checkout action, the Arch container image,
the keyserver-imported GPG key, GitHub Actions, and local package sources with
skipped checksums. These are declared dependencies or metadata, not locally
verified guarantees. The current `PKGBUILD` declares no remote source. The
workflow passes `GITHUB_TOKEN` to its release action; no secret value is
recorded here.

Do not add secrets, treat remote metadata as proof, or treat README examples as
runtime-safety evidence.

## 8. Validation

### Evidence available

The current evidence is static inspection of `t2fand`, `README.md`, `Makefile`,
`PKGBUILD`, `t2fand.initd`, `tests/test_t2fand.py`, `.gitignore`, and
`.github/workflows/build.yml`, summarized in `SPEC.md`. It verifies source
expressions, SMC/t2fand mode handling, legacy migration, SMC ownership and
telemetry paths, T2-only fan discovery, vgaswitcheroo filtering, fake-fixture
test definitions, local package staging, release metadata, ignored artifact
paths, unconditional OpenRC install rules, logger/package declarations, and
benchmark prerequisite ordering/failure definitions, and integration settings;
it does not verify execution.

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
3. Confirm unconditional `DESTDIR`/`BINDIR`/`OPENRC_INITDDIR`/`OPENRC_CONFDIR`
   installation, exact three-file source payload, and modes 0700/0755/0644 in
   `Makefile`.
4. Confirm `PKGBUILD` uses `pkgname=t2fand`, local `t2fand`, `t2fand.initd`,
   `t2fand.confd`, and `Makefile` sources, `pkgver=2.0.1`, `pkgrel=2`, backup
   metadata, and `make DESTDIR` staging; confirm the exact daemon, OpenRC init,
   and conf.d payload, `util-linux`, and no selected syslog daemon.
5. Confirm daemon ownership of `/run/t2fand.pid` and separate OpenRC supervisor
   state.
6. Confirm SMC/t2fand configuration and legacy inference warning, SMC release
   and maintenance of `fan*_manual=0`, no normal SMC output writes, degraded SMC
   sensor/tachometer monitoring, compact default/full verbose telemetry and
   field meaning, deterministic hottest selection, `unknown` values,
   ownership-loss escalation, clean shutdown release, t2fand fail-high and
   recovery, T2-only fan discovery, global hwmon/CPU/DRM sensor discovery,
   vgaswitcheroo `DIS:Off` filtering, numeric DRM filtering, deduplication,
   one-read cycles, rate-limited errors, all CLI defaults/consumers and
   pre-mutation numeric validation, post-control ordinary-`Exception` fatal
   conversion, and independent cleanup from source/tests. Confirm absent-CPU,
   config-generation-I/O, and partial-discovered-fan fixture definitions;
   partial fan authority/control loss is fatal.
7. Confirm five respawns per 60 seconds, two-second base/incremental delay,
   explicit-stop suppression, and logger directives from source evidence.
8. Confirm exact OpenRC `command_args="${t2fand_args:-}"` handling for absent,
   empty, and nonempty `t2fand_args`, daemon PID ownership, and benchmark
   timestamp formatting with preserved logger side effect from source/tests.
9. Confirm `.gitignore` covers `opencode.json` and generated build/release
   artifacts; neither ignored local state nor generated artifacts is product
   evidence.
10. Confirm `t2fanbench.py` performs the standard-library `stress-ng` PATH
    lookup before cache creation, benchmark/logger output, baseline sleep, and
    subprocess launch. Confirm the unavailable-path fake definition asserts the
    exact stderr error, status `1`, no traceback, and no cache, output, logger,
    sleep, or subprocess side effect; confirm available-path sequencing remains
    intact. Execution remains unknown.

Staged installation, package build, runtime, hardware, OpenRC lifecycle, and
syslog results remain unknown. No README snippet or lifecycle command was
executed.

The unexecuted static test
`test_package_has_exact_openrc_payload_and_no_alternate_selector` targets the
current `2.0.1-2` release and is intended to assert Makefile-based staging
through `make DESTDIR="$pkgdir" install`, matching the local-source `PKGBUILD`.
The default fake fixture now creates a T2 fan at `devices/a/b/c/d/APP0001:00`,
matching current T2-only discovery. No test pass or runtime claim is made from
these definitions.

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
  candidate, or loss of maximum write authority is fatal. In t2fand mode,
  selected sensor failures, including unusable or absent CPU input, and config
  failures with writable maxima remain alive at maximum; failed actual RPM reads
  also fail high. SMC telemetry failure remains degraded monitoring.
- A live PID path blocks startup; malformed or stale PID state is diagnosed and
  removed when possible. Identity locking and atomicity remain unimplemented.
- Missing/invalid t2fand FanN policy, non-finite or unordered thresholds,
  invalid curves, and non-Boolean values enter global `config-failsafe` in
  t2fand mode and remain a dormant warning in SMC. Malformed or unreadable INI
  raises `StartupError` before control and fan mutation. Unsafe t2fand curve
  calculation follows the same path. Repair requires restart; SMC does not use
  FanN policy.
- Missing or failed selected inputs, including CPU inputs, trigger recoverable
  sensor fail-safe in t2fand mode when maximum control survives; missing GPU
  topology alone does not. Five valid cycles are required for t2fand sensor
  recovery. In SMC, thermal and tachometer failures remain degraded monitoring
  and do not trigger takeover. Local hardware disappearance and recovery are
  untested.
- SMC ownership release/maintenance, t2fand-mode writes, actual RPM reads,
  partial writes, and abrupt termination have only source-level behavior;
  target-host outcomes remain unknown.
- After t2fand control starts, an unexpected ordinary `Exception` is converted
  to fatal `control-error` handling with the original critical diagnostic,
  independent maximum attempts, independent fan/PID cleanup, nonzero exit, and
  no normal stopped summary. Pre-control unexpected exceptions are re-raised;
  `BaseException` is not caught. Runtime outcomes remain unknown.
- OpenRC directives describe bounded respawn/backoff and logger routing, but
  local lifecycle, directive support, receiver delivery, and persistence are
  untested.
- Missing `stress-ng` is a benchmark precondition failure: the checked-in path
  returns status `1` with exact stderr and no cache, output, sleep, logger, or
  subprocess side effect. Runtime behavior remains unverified.
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
- The former two-file OpenRC payload boundary is superseded by the current
  three-file daemon/init/conf.d payload. `util-linux` remains explicitly
  required for `/usr/bin/logger`; no syslog daemon is selected.
- Compact telemetry is the default in both modes; `-v` selects the full record,
  and SMC does not imply verbose output. The prior default-SMC-full and
  manual-verbose-only behavior is superseded history.
- The six runtime overrides are process-local. OpenRC consumes only
  `t2fand_args`; daemon defaults and option validation remain in `t2fand`.
- Benchmark `log()` output uses explicit local, English-month timestamp
  formatting and flushes each printed line while retaining the logger side
  effect.
- Gate benchmark startup on standard-library PATH resolution of `stress-ng`;
  preserve the existing available-path sequence and child output, and keep the
  missing-path failure side-effect free.
- Treat package provenance, checksum assurance, and build output as `unknown`
  because local package sources use skipped checksums and no package build was
  run.
- Record `make test` as the project-native command without claiming execution or
  passing results.

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

- `H-010` (superseded release reconciliation): checked-in `PKGBUILD` then
  declared intentional release `2.0.0-1` (`pkgver=2.0.0`, `pkgrel=1`). The prior
  `1.2.0-3` package fact remains superseded history; payload, dependency, and
  metadata outcomes remain unverified.
- `H-011` (current documentation ownership transition): REQ-051 makes README
  concise operator onboarding for actions, safety, configuration, OpenRC,
  observability, and testing. Exhaustive limits, modes, telemetry, fail-safe
  behavior, and implementation truth remain owned by `SPEC.md` and this file.
  The prior full-contract README placement remains superseded history.
- `H-012` (historical post-control exception correction): after former manual
  control starts, the source converts an unexpected ordinary `Exception` to
  fatal `control-error` handling, preserves its critical diagnostic,
  independently attempts known maxima and fan/PID cleanup, exits nonzero, and
  omits the normal stopped summary. Pre-control unexpected exceptions and
  `BaseException` remain outside this conversion; runtime outcomes remain
  unverified.
- `H-014` (superseded proposed control-mode transition): the contract proposed
  global SMC/manual selection, generated-SMC and legacy-manual compatibility,
  passive SMC monitoring, default telemetry, ownership escalation, clean
  release, and retained manual curves/fail-high behavior. It remains history.
- `H-015` (superseded checked-in control-mode implementation): source and fake-
  sysfs test definitions implement SMC/manual selection, the legacy warning, SMC
  ownership maintenance and degraded monitoring, default telemetry, ownership
  escalation, shutdown release, and manual behavior. Hardware, runtime, and test
  execution remain unverified.
- `H-016` (current package-validation correction): the intended static package
  check is Makefile-authoritative, requiring `PKGBUILD` delegation through
  `make DESTDIR="$pkgdir" install`, the exact two-file payload and modes defined
  by the Makefile, and release `2.0.1-1`. This corrects stale direct-install/
  `2.0.0` wording; checked-in definitions and validation intent do not prove
  test execution, staging, package build, or release outcome.
- `H-017` (historical configuration-outcome reconciliation): absent-config
  generation failure and existing INI read/parse failure are pre-control
  `StartupError` paths with no fan mutation or maximum command; malformed FanN
  former-manual policy remains `config-failsafe` and is only a dormant warning
  in SMC. Checked-in source and test definitions support this; test execution,
  runtime, and hardware outcomes remain unknown.
- `H-018` (historical pre-correction observability, override, package, and
  benchmark implementation): source and test definitions implemented compact
  telemetry by default in both modes, full telemetry only with `-v`, six
  process-local CLI overrides with pre-mutation validation, timestamped
  benchmark `log()` output, and the then-current ordered OpenRC forwarding with
  final `t2fand_args`, plus the preserved three-file package payload at release
  `2.0.1-2`. `H-019` supersedes only that seven-assignment conf.d and six-option
  forwarding surface; the telemetry, CLI, benchmark, and package facts remain
  historical evidence. Test execution, staging, package build, service
  lifecycle, and runtime outcomes remain unverified.
- `H-019` (sole current checked-in conf.d behavior): `t2fand.confd` has only the
  active `t2fand_args=""` assignment, and `t2fand.initd` sets
  `command_args="${t2fand_args:-}"` without duplicating daemon defaults. This
  supersedes the historical seven-assignment conf.d and six-option forwarding
  surface; daemon CLI options and defaults remain unchanged. Runtime outcomes
  remain unverified.

### 2.0.1 handoff transition

- Fan selection moved from the retained 2.0.0 union of T2 and class-hwmon fan
  candidates to T2-only `APP0001:00` candidates. Reason: keep fan-control
  authority within the T2 fan layout while retaining global hwmon as a
  temperature-sensor source. `_fan_candidates()` and `discover_fans()` verify
  the path, expansion, deduplication, and all-candidate checks.
- Readable vgaswitcheroo `DIS:Off` dGPU entries now filter only matching
  resolved temperature paths. Reason: exclude an explicitly powered-off dGPU
  without disabling other hwmon/DRM discovery. `_off_dgpu_pci()` and
  `discover_sensors()` verify this boundary; absent/unreadable switch state
  remains non-fatal.
- Arch packaging now names checked-in `t2fand`, `t2fand.initd`, and `Makefile`
  sources, then delegates staging through `make DESTDIR="$pkgdir" install`.
  Reason: keep package staging on the local exact two-file OpenRC payload.
  `PKGBUILD` and `Makefile` verify the static path, mode, and delegation
  definitions; package/staging results remain unknown.
- README now documents the Artix Linux/OpenRC package workflow and local
  checkout staging as concise operator onboarding. This verifies documentation
  placement and scope only; no install or service result is claimed.
- `opencode.json` is ignored local state, not a product input. `.gitignore` also
  ignores generated package/source staging, Python build/distribution, archive,
  log, signature, and zip paths. No ignored-state removal or artifact generation
  is claimed.
- The package release moved from the historical 2.0.0 state to `2.0.1-1`
  (`pkgver=2.0.1`, `pkgrel=1`), with name, metadata, dependencies, and exact
  two-file payload retained. `PKGBUILD` verifies the declaration; build and
  release outcomes remain unknown.

### 2.0.1-2 implementation transition

- Runtime observability changed from the prior default SMC full record and
  manual verbose-only record to one compact record per second in both modes.
  Compact output contains only hottest eligible sensor identity/value and each
  fan's actual RPM; `-v` selects the full record. SMC does not imply verbose.
- CLI parsing now carries config, PID, sysfs, sensor-recovery, sample-limit, and
  error-reminder values into existing consumers without changing module
  defaults. Positive numeric validation occurs before root checks or filesystem
  mutation; the selected PID path is used on cleanup.
- `t2fanbench.py` now prints local wall-clock English `MMM DD HH:mm:ss`
  timestamps with zero-padded day/time fields, the `[t2fanbench]` tag, flushed
  output, and preserved logger submission.
- Before `H-019`, the 2.0.1-2 OpenRC configuration declared seven active
  defaults. Its then-current init script forwarded the six non-argument values
  in order and appended `t2fand_args` last; path values containing whitespace
  remained unsupported. `H-019` superseded that conf.d/forwarding surface. The
  package recipe and Makefile still carried and staged `/etc/conf.d/t2fand` mode
  0644, preserved it via `backup=()`, and declared release `2.0.1-2` alongside
  daemon/init modes 0700/0755.
- These are checked-in source/configuration and test-definition facts. Test
  execution, staging, package build, OpenRC lifecycle, benchmark runtime, and
  hardware outcomes remain unknown.

### Benchmark prerequisite transition

- `H-021` (current benchmark prerequisite correction): `t2fanbench.py` now uses
  standard-library `shutil.which("stress-ng")` before cache creation,
  benchmark/logger output, baseline sleep, or subprocess launch. Missing
  `stress-ng` writes the exact required stderr message, returns status `1`, and
  produces no traceback or listed side effect. Available-path sequencing,
  timestamps, logger side effect, and child output remain unchanged. Source and
  fake-test definitions are checked-in evidence; runtime and test execution
  remain unknown.

### Global control-mode rename transition

- The checked-in daemon and test definitions now accept only global `smc` and
  `t2fand`. Generated configs select `smc`; configs without `[General]` infer
  `t2fand`, warn exactly once, and remain unchanged. `manual`, `auto`,
  `smc_auto`, and aliases are rejected. SMC observes under Apple SMC ownership;
  t2fand owns control and applies FanN policies. Hardware `fan*_manual` and
  `smc-auto`/`smc-degraded` terminology remains unchanged. Static source/test
  evidence is present; execution remains unverified.

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

README now provides concise operator onboarding under REQ-051 and REQ-074:
prerequisites, installation and staging paths, both control modes,
generated/legacy configuration, the conf.d override, CLI options, compact/full
telemetry, benchmark prerequisite and timestamp semantics, OpenRC operation,
safety limits, and the project-native test target. It is operator guidance, not
runtime evidence. No monitoring, upgrade cadence, hardware test routine, or
ownership handoff is defined. Re-check package source pinning, checksum policy,
local staging, OpenRC runtime behavior, logger receiver configuration, benchmark
execution, and CI execution before relying on a release artifact.

## 11. Agent rules

`AGENTS.md` owns routing, onboarding, edit boundaries, safety rules, and
protected surfaces. This file owns deeper t2fand implementation context. Never
edit `SPEC.md` as part of a context sync; if local evidence contradicts its
contract, stop and report the exact mismatch for reconciliation.

Do not run README snippets. Do not research remote sources or perform remote
maintenance. Preserve unrelated working-tree changes. Keep unsupported behavior
and unexecuted claims explicitly `unknown`.

## 12. Current summary

Current source shape: a root-required foreground Python daemon resolves global
`smc` or `t2fand` control. Generated configs select SMC; legacy configs without
`[General]` infer t2fand, warn exactly once, and remain unchanged. `manual`,
`auto`, `smc_auto`, and aliases are rejected. Fan discovery is T2-only below
`APP0001:00`; every discovered, resolved-path-deduplicated candidate must be
complete and controllable, and partial authority/control loss is fatal. Global
hwmon, CPU, and exact numeric DRM-card temperatures are re-discovered each
cycle; readable vgaswitcheroo `DIS:Off` dGPU entries filter matching paths only.
Both modes emit one compact default telemetry record per second; `-v` selects
the full record and SMC does not imply verbose. Compact output reports hottest
eligible sensor identity/value and each fan's actual RPM; full output retains
sensor, topology, state, reason, policy, target, and actual-RPM fields. SMC
releases and maintains `fan*_manual=0`, normally never writes fan output, and
degrades on Linux thermal/tachometer failure without takeover. Its `target_rpm`
is an observed current output value, not a daemon command. T2fand mode retains
hottest-temperature control, curves, configurable sample/recovery settings
(defaults five/five), fail-high behavior, and shutdown cleanup. The CLI has six
validated runtime overrides in addition to `-v`; the selected PID path is used
for cleanup. OpenRC is the sole service integration; `t2fand.initd` supervises
the foreground daemon, which owns the PID path. The Makefile and PKGBUILD
provide the exact three-file payload with installed modes 0700/0755/0644;
`PKGBUILD` uses local sources, backup preservation, and release `2.0.1-2`.
`t2fanbench.py` prints flushed local English-month timestamps and retains logger
submission. It requires `stress-ng` on PATH and checks that prerequisite before
benchmark side effects; missing availability returns status `1` with exact
stderr and no traceback or listed side effect. `opencode.json` and generated
artifacts are ignored, util-linux supports service logger routing, and no
systemd payload exists.

Static source/test inspection is complete for the revised local surfaces;
control-mode, migration, SMC ownership/telemetry/degradation, compact/full
telemetry, CLI validation and wiring, package/conf.d override, benchmark
formatting, benchmark prerequisite ordering/failure fixtures, shutdown, and
t2fand-regression fixtures are present. `make test` was not executed in this
sync. Not verified: hardware behavior, MacBookPro16,1 characterization,
compatibility coverage, test pass/fail, build/release success, staged
installation, package build, OpenRC lifecycle, directive support, syslog
delivery/persistence, benchmark execution, package provenance, and checksum
assurance.
