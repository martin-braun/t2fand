# t2fand — Product Contract

## Contract status and document roles

This document is the contract truth for the local t2fand fork. `documented`
means supported by checked-in source or configuration; it does not mean
runtime-tested. `unknown` means local evidence is insufficient. This revision
records the delivered OpenRC-only static implementation. The systemd unit is
absent and the checkout contains only the OpenRC service definition; package,
staged-install, and runtime behavior are not claimed.

`SPEC.md` owns contract truth. The recorder synchronizes `CONTEXT.md` after
implementation. `README.md` is project documentation. `AGENTS.md` owns
onboarding, ownership, routing, safety, and protected-surface rules.

## Problem

`t2fand` is a Python daemon for automatic fan-speed control on Macs with an
Apple T2 chip running Linux. Its service integration must have one supported
service manager, one defined service artifact, and one deterministic install
path. The supported manager is OpenRC. Thermal safety, hardware coverage, and
runtime lifecycle success are `unknown`.

## Goals

- Preserve the daemon's existing behavior and interfaces.
- Make the checked-in `t2fand.initd` the sole service-manager definition and
  OpenRC the sole supported service manager.
- Install and package exactly the daemon and OpenRC artifact, with stable staged
  paths and modes.
- Run the already-foreground daemon under `supervise-daemon` with unlimited
  all-exit respawn, a constant two-second delay, and explicit-stop suppression.
- Retire dual-init selection and systemd-authoritative requirements without
  erasing their historical contract evidence.

## Users and roles

| Role                        | Need                                                 | Status                                            |
| --------------------------- | ---------------------------------------------------- | ------------------------------------------------- |
| Linux user of a T2 Mac      | Automatic temperature-driven fan control             | documented daemon scope; hardware outcome unknown |
| Root/system administrator   | Install, configure, and operate the OpenRC service   | current workflow; execution unknown               |
| Arch Linux package consumer | Install the executable and OpenRC service definition | current static payload; package build unknown     |
| Package maintainer          | Build and release the Arch package                   | documented workflow; execution unknown            |

Supported hardware beyond the script's T2-oriented sysfs paths, distribution
coverage beyond the declared Arch package, and non-root operation are `unknown`.

## Scope

### In scope

- Existing Python 3 executable `t2fand` and its current daemon behavior.
- Existing root `t2fand.initd`, retained unchanged as the sole service
  definition.
- OpenRC-only administrator, Makefile, staged-install, and Arch package
  workflows.
- The delivered source omits `t2fand.service`, systemd Makefile paths/selection,
  and systemd package payload.
- Static inspection of service source, payload, paths, modes, and install rules.
- Existing GitHub Actions package workflow, except that its package output is
  expected to contain the OpenRC-only payload.

### Out of scope

- Changes to daemon algorithm, configuration schema, signal cleanup, or hardware
  behavior.
- Service or hardware execution, host writes, service enablement, and CI
  execution for this contract update.
- README/CONTEXT synchronization; the recorder handles `CONTEXT.md` after this
  contract truth.
- CI/source pinning, action upgrades, package rename, remote maintenance, GUI,
  network API, or unrelated files.
- Guessing an Arch OpenRC runtime dependency.

## Terminology

| Term              | Definition                                                          | Status                                   |
| ----------------- | ------------------------------------------------------------------- | ---------------------------------------- |
| T2 Mac            | Hardware targeted by the project description and fan sysfs path     | documented; exact model set unknown      |
| OpenRC artifact   | Root `t2fand.initd`, installed as `/etc/init.d/t2fand`              | current sole source artifact             |
| daemon PID        | PID written by `t2fand` to `/run/t2fand.pid`                        | documented implementation                |
| foreground daemon | `/usr/bin/t2fand` process not backgrounded by the wrapper           | current static integration invariant     |
| all-exit respawn  | Respawn after every child exit, including status 0                  | current static OpenRC policy             |
| explicit stop     | Administrator-requested OpenRC stop using the declared retry policy | current static contract; runtime unknown |

## Stable requirements

Requirement IDs are stable. A changed contract receives a new ID; prior meaning
is retained below as superseded history.

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                | Status                                         | Acceptance evidence                                                            |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ---------------------------------------------- | ------------------------------------------------------------------------------ |
| `REQ-001` | Refuse startup when effective UID is not zero and print `T2 Fan Daemon must be run as root`.                                                                                                                                                                                                                                                                                                                                               | documented daemon implementation               | `t2fand:102-105`; execution unverified                                         |
| `REQ-002` | Accept any existing path matched by the initial T2 fan glob; if none exists, print `Fan not found` and exit 1. This does not prove later direct `fan*_input` discovery finds a fan.                                                                                                                                                                                                                                                        | documented daemon implementation               | `t2fand:107-117`; execution unverified                                         |
| `REQ-003` | Require an existing CPU-glob path and `get_cpu_temp() != -1`; otherwise print `CPU temperature sensor not found` and exit 1. Textual `0` is skipped; parsed `-1` °C collides with the sentinel.                                                                                                                                                                                                                                            | documented daemon implementation               | `t2fand:75-84,119-132`; execution unverified                                   |
| `REQ-004` | Use `/run/t2fand.pid`, reject a PID with an existing `/proc/<pid>`, and remove a stale PID file before continuing.                                                                                                                                                                                                                                                                                                                         | documented daemon implementation               | `t2fand:13-14,140-150`; identity and execution unverified                      |
| `REQ-005` | Discover direct `fan*_input` children of the first matched fan directory and construct one `Fan` per input. Discovery may yield `fanCount == 0`; startup then continues with no controlled fans.                                                                                                                                                                                                                                           | documented daemon implementation               | `t2fand:152-155`; hardware coverage unverified                                 |
| `REQ-006` | Read integer fan limits and input, clamp requested speed to the limits, and write the integer to the fan output. The main loop does not call `get_speed`.                                                                                                                                                                                                                                                                                  | documented daemon implementation               | `t2fand:20-35,250-251`; sysfs behavior untested                                |
| `REQ-007` | Write `1` to each manual file before control and attempt `0` for each fan during SIGTERM/SIGINT cleanup.                                                                                                                                                                                                                                                                                                                                   | documented daemon implementation               | `t2fand:37-41,231-233`; hardware behavior untested                             |
| `REQ-008` | If `/etc/t2fand.conf` is absent, generate `Fan1` through `FanN` with `55`, `75`, `linear`, and `false` defaults.                                                                                                                                                                                                                                                                                                                           | documented daemon implementation               | `t2fand:173-185`; execution unverified                                         |
| `REQ-009` | Require four options in every detected fan section and accept only `linear`, `exponential`, or `logarithmic`; invalid or missing configuration prints an error and exits 1. Numeric conversion failures are not explicitly handled.                                                                                                                                                                                                        | documented daemon implementation               | `t2fand:187-228`; edge cases unverified                                        |
| `REQ-010` | Exact `always_full_speed == "true"` selects maximum speed; otherwise apply the existing ordered thresholds and curve rules.                                                                                                                                                                                                                                                                                                                | documented daemon implementation               | `t2fand:43-72`; execution and math untested                                    |
| `REQ-011` | Preserve the existing linear, cubic exponential, and `math.log` logarithmic expressions.                                                                                                                                                                                                                                                                                                                                                   | documented daemon implementation               | `t2fand:50-72`; numerical results untested                                     |
| `REQ-012` | Select CPU, or the greater CPU/GPU value when GPU is marked available; retain at most five samples, round the mean to two decimals, update every fan, and sleep one second per loop. Post-startup CPU `-1` is not revalidated.                                                                                                                                                                                                             | documented daemon implementation               | `t2fand:235-253`; timing and hardware untested                                 |
| `REQ-013` | Handled SIGTERM/SIGINT prints `T2 Fan Daemon is shutting down...`, sequentially attempts manual-mode disable for every fan, attempts PID removal, and exits. Prior fan mode is not restored.                                                                                                                                                                                                                                               | documented daemon implementation               | `t2fand:158-171`; signal and hardware behavior untested                        |
| `REQ-014` | Historical systemd unit contract: `Type=simple`, `/usr/bin/t2fand`, `PIDFile=/run/t2fand.pid`, `Restart=always`, `RestartSec=2`, and installability for `default.target`.                                                                                                                                                                                                                                                                  | **superseded by `REQ-023`**                    | Prior `t2fand.service:1-12`; retained historical evidence                      |
| `REQ-015` | Historical systemd-only `make install`: copy `t2fand` to `/usr/bin` and the unit to `/usr/lib/systemd/system`, modes 0700/0644, no compilation.                                                                                                                                                                                                                                                                                            | **superseded by `REQ-024`**                    | Prior Makefile; retained historical evidence                                   |
| `REQ-016` | Historical package contract: package metadata named `t2fand-openrc` while packaging the executable and systemd unit only.                                                                                                                                                                                                                                                                                                                  | **superseded by `REQ-025`**                    | Prior PKGBUILD; retained historical evidence                                   |
| `REQ-017` | The package workflow retains its checked-in push/PR triggers, `ubuntu-latest`, checkout step, marker gates, package artifact upload, and release configuration. Actual CI, tags, actions, and remote behavior remain `unknown`.                                                                                                                                                                                                            | documented workflow configuration              | `.github/workflows/build.yml:1-62`; execution unverified                       |
| `REQ-018` | Retain root `t2fand.initd` with `#!/sbin/openrc-run`, `command=/usr/bin/t2fand`, `supervisor="supervise-daemon"`, `respawn_delay="2"`, `respawn_max="0"`, `supervise_daemon_args="--respawn-delay-step 0"`, and `retry="SIGTERM/5"`. It must not set `pidfile` or background/daemonization variables.                                                                                                                                      | current static source; runtime unknown         | `t2fand.initd:1-9`; source inspection                                          |
| `REQ-019` | Historical selector contract: `INIT_SYSTEM` accepts `auto`, `systemd`, or `openrc`, with fail-closed marker detection and selected service installation.                                                                                                                                                                                                                                                                                   | **superseded by `REQ-024`**                    | Prior Makefile; retained historical evidence                                   |
| `REQ-020` | Historical package contract: package name `t2fand-openrc`, version `1.2.0-1`, and direct installation of the executable plus both service definitions.                                                                                                                                                                                                                                                                                     | **superseded by `REQ-025`**                    | Prior PKGBUILD; retained historical evidence                                   |
| `REQ-021` | Historical systemd-authoritative contract: unchanged systemd unit was authority and OpenRC was only its equivalent; both wrapped the foreground daemon.                                                                                                                                                                                                                                                                                    | **superseded by `REQ-023` and `REQ-026`**      | Prior unit and OpenRC inspection; retained historical evidence                 |
| `REQ-022` | Historical dual-manager lifecycle contract: both integrations respawned all exits with no cap and a two-second delay; explicit stop was not to respawn.                                                                                                                                                                                                                                                                                    | **superseded by `REQ-026`**                    | Prior integration inspection; runtime unverified                               |
| `REQ-023` | OpenRC is the sole supported service manager and `t2fand.initd` is the sole service-manager definition. `t2fand.service` is deleted; no systemd artifact, systemd workflow, or dual-manager operation is supported.                                                                                                                                                                                                                        | current static implementation                  | `t2fand.service` absent; `t2fand.initd` sole definition; source inspection     |
| `REQ-024` | `make install` is unconditional OpenRC installation with no `INIT_SYSTEM`, selector, auto-detection, `PREFIX`, or systemd directory. It must honor `DESTDIR`, overridable `BINDIR` defaulting to `/usr/bin`, and overridable `OPENRC_INITDDIR` defaulting to `/etc/init.d`; perform no compilation; install only `t2fand` mode 0700 and `t2fand.initd` as `t2fand` mode 0755.                                                              | current static implementation                  | `Makefile:1-9`; staged result unknown                                          |
| `REQ-025` | PKGBUILD must retain `pkgname=t2fand`, retain current package identity and metadata unless separately authorized, bump `pkgrel` from 1 to 2, and package exactly `/usr/bin/t2fand` mode 0700 and `/etc/init.d/t2fand` mode 0755. It must not create or package a systemd directory or unit and must not add or claim an Arch OpenRC runtime dependency.                                                                                    | current static implementation                  | `PKGBUILD:2-20`; package build unknown                                         |
| `REQ-026` | OpenRC must run `/usr/bin/t2fand` as the already-foreground daemon through `supervise-daemon`; the daemon owns `/run/t2fand.pid`, and the supervisor must keep separate state. Every child exit, including status 0, must respawn with unlimited count and an exact constant two-second delay. `retry="SIGTERM/5"` and explicit stop must terminate supervision without respawn.                                                           | current static implementation; runtime unknown | `t2fand.initd:1-9` and daemon source semantics; no lifecycle execution claimed |
| `REQ-027` | The OpenRC wrapper must declare no `pidfile`, background/daemonization setting, or network dependency. Installation must not start, stop, restart, enable, disable, reload, or daemon-reload any service manager.                                                                                                                                                                                                                          | current static safety/install invariant        | `t2fand.initd:1-9`, `Makefile:1-9`; no host action claimed                     |
| `REQ-028` | The supported operator service workflow is OpenRC only: use `rc-service t2fand` with start, stop, restart, or status, with optional `rc-update add t2fand default`; installation uses `make install` or `makepkg`. The Python daemon remains a foreground executable invoked by the OpenRC script as `/usr/bin/t2fand`; source-level direct execution remains an executable/process fact, not a second supported service-manager workflow. | current static workflow contract               | OpenRC-only source/workflow inspection; execution unknown                      |

## Runtime rules

### Daemon behavior

The daemon rules remain unchanged by this contract: root startup, T2 fan and
CPU/GPU discovery, PID-file handling, configuration generation/validation,
manual-mode control, five-sample smoothing, curve calculation, one-second
polling, and handled signal cleanup follow `REQ-001`–`REQ-013`. The daemon's
hardware and failure consequences remain `unknown`.

### OpenRC supervision

The sole service definition invokes the existing foreground command with
`supervise-daemon`. The wrapper must not background or daemonize it, set a
`pidfile`, or replace `/run/t2fand.pid`; that PID file belongs to the daemon and
supervisor state is separate. `respawn_delay=2` and `--respawn-delay-step 0`
define a constant two-second delay. `respawn_max=0` defines unlimited respawn.
All child exits, including status 0, are respawnable. `retry="SIGTERM/5"` is the
explicit stop contract: an administrator stop must end supervision and must not
enter respawn. These are current static integration claims; local OpenRC
lifecycle behavior is unknown.

## Interfaces

| ID       | Interface                   | Contract                                                                                                                                                  | Status                                                       |
| -------- | --------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------ |
| `IF-001` | CLI/process                 | Invoke `t2fand` directly; no command-line arguments or foreground option is documented.                                                                   | daemon interface; argument behavior unknown                  |
| `IF-002` | INI file                    | `/etc/t2fand.conf` contains `Fan1` through `FanN` and four required keys per detected fan.                                                                | documented; read at startup                                  |
| `IF-003` | Linux sysfs fan API         | Read `<base>_max`, `<base>_min`, `<base>_input`; write `<base>_output` and `<base>_manual`.                                                               | documented; device compatibility unknown                     |
| `IF-004` | Linux sysfs temperature API | Read the existing CPU/GPU paths and millidegree text; textual `0` is skipped.                                                                             | documented; GPU support unknown                              |
| `IF-005` | PID file                    | `/run/t2fand.pid` stores the decimal daemon PID; live `/proc/<pid>` rejects startup and missing `/proc/<pid>` permits stale removal.                      | daemon-owned; identity locking absent                        |
| `IF-006` | POSIX signals               | SIGTERM and SIGINT invoke sequential cleanup, PID removal attempt, and process exit.                                                                      | documented; failure paths unknown                            |
| `IF-007` | systemd unit                | Historical interface: `Type=simple`, `Restart=always`, `RestartSec=2`, `ExecStart=/usr/bin/t2fand`, `PIDFile=/run/t2fand.pid`, `WantedBy=default.target`. | **superseded by `IF-017`**                                   |
| `IF-008` | Make target                 | Historical selector interface accepting `INIT_SYSTEM` and systemd/OpenRC directory overrides.                                                             | **superseded by `IF-014`**                                   |
| `IF-009` | Arch package                | Historical package interface installing the executable and both service definitions.                                                                      | **superseded by `IF-015`**                                   |
| `IF-010` | GitHub Actions              | Push/PR package workflow with its checked-in gates and artifact/release configuration.                                                                    | retained; execution unknown                                  |
| `IF-011` | OpenRC init script          | Root `t2fand.initd` is installed as `/etc/init.d/t2fand` and supervises `/usr/bin/t2fand`.                                                                | current static sole service interface; runtime unknown       |
| `IF-012` | Service-manager selection   | Historical `INIT_SYSTEM=auto` and explicit systemd/openrc selector.                                                                                       | **superseded by `IF-014` and `IF-017`**                      |
| `IF-013` | Supervisor state boundary   | Historical dual-manager boundary in which the daemon owned `/run/t2fand.pid` and OpenRC omitted `pidfile`.                                                | PID portion retained by `IF-016`; systemd portion superseded |
| `IF-014` | Make target                 | `make install` accepts `DESTDIR`, `BINDIR`, and `OPENRC_INITDDIR` only for unconditional OpenRC staged installation.                                      | current static implementation; staged result unknown         |
| `IF-015` | Arch package                | `makepkg` must produce the unchanged-name package with exactly the executable and OpenRC init script payload.                                             | current static implementation; build unknown                 |
| `IF-016` | PID/supervisor boundary     | The daemon owns `/run/t2fand.pid`; OpenRC supervisor state is separate and no wrapper `pidfile` is allowed.                                               | current static implementation; runtime unknown               |
| `IF-017` | Service-manager boundary    | OpenRC is the only supported manager and `/etc/init.d/t2fand` is the only service artifact.                                                               | current static implementation                                |

## Runtime state and filesystem paths

| State/path                              | Meaning and ownership                                                                                                | Status                                                          |
| --------------------------------------- | -------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------- |
| `/etc/t2fand.conf`                      | Persistent administrator configuration; generated only when absent and read at startup.                              | documented; exact mode unknown                                  |
| `/run/t2fand.pid`                       | Decimal PID written by the daemon after startup checks; stale removal and handled-signal removal follow daemon code. | daemon-owned; cleanup limitations unknown                       |
| OpenRC supervisor state                 | State for the supervised foreground child; must not claim the daemon PID file.                                       | current static integration; exact manager paths/runtime unknown |
| `/etc/init.d/t2fand`                    | Installed copy of the sole checked-in OpenRC definition.                                                             | current static payload; staged result unknown                   |
| `/usr/bin/t2fand`                       | Installed executable invoked by OpenRC.                                                                              | current static payload; staged result unknown                   |
| Fan sysfs files                         | Kernel/device state read and written by the daemon.                                                                  | hardware runtime unknown                                        |
| In-memory `temps`, `fans`, `fanConfigs` | Process-lifetime samples, fan objects, and policies.                                                                 | documented daemon state                                         |

The delivered source contains no systemd unit or systemd install/package path.
Their absence from package or staged output remains an acceptance condition;
package and staged-install results are unknown.

## Workflows

The following workflows are current static implementation contracts. Execution,
staged installation, package creation, and runtime behavior remain unknown.

### Product operation

1. Install the executable and OpenRC definition through the unconditional OpenRC
   path.
2. Configure `/etc/t2fand.conf` as needed.
3. Use OpenRC to start, stop, restart, or inspect `t2fand`.
4. The manager supervises the existing foreground daemon; daemon startup,
   polling, and signal cleanup remain governed by `REQ-001`–`REQ-013`.

No systemd start, enable, status, restart, migration, or dual-manager product
workflow remains supported.

### Configuration workflow

The first run generates 55 °C low, 75 °C high, linear, and no full-speed
override for each detected fan. An administrator may edit the INI file. All four
keys are required per detected fan and configuration is read only at startup.
Live reload is not implemented; reload behavior is `unknown`.

### Installation workflow

The delivered Makefile has only the `.PHONY` `install` target, performs no
compilation, and has no daemon prerequisite. It copies only:

- `t2fand` to `$(DESTDIR)$(BINDIR)/t2fand` with mode 0700;
- `t2fand.initd` to `$(DESTDIR)$(OPENRC_INITDDIR)/t2fand` with mode 0755.

The Makefile uses `DESTDIR` for all copies. The source performs no start, stop,
restart, enable, disable, reload, or daemon-reload action and makes no host
service state change.

### Package workflow

The delivered `PKGBUILD` retains `pkgname=t2fand`, current
version/target/license and declared existing dependencies unless separately
authorized, sets `pkgrel` to 2, and directly installs exactly the two target
files. It does not call a service selector, create a systemd directory, package
a systemd unit, or add/claim an OpenRC runtime dependency. Local evidence does
not name Arch's OpenRC runtime dependency; it is `unknown`.

### Administrator service workflow

The supported manager workflow is OpenRC:

```text
rc-update add t2fand default       # optional enablement
rc-service t2fand start
rc-service t2fand status
rc-service t2fand stop
rc-service t2fand restart
```

The commands are current workflow contract examples, not executed validation.
The OpenRC dependency set is unknown; no network dependency is permitted.

### Lifecycle, recovery, and release

Every child exit, including status 0, is recovered by unlimited respawn after
the constant two-second delay. Explicit stop suppresses respawn. SIGTERM and
SIGINT cleanup remains daemon-owned. Stale PID handling is the documented
recovery path; crash, SIGKILL, power-loss, cleanup failure, and hardware
recovery outcomes are `unknown`.

The existing GitHub Actions push/PR package and release workflow remains in
scope. CI, package build, release, tag, action, and remote-source outcomes are
`unknown`; no CI or source-pinning change is part of this contract.

## Constraints and invariants

- Root privilege remains required by the daemon; normal installation targets
  absolute system directories.
- Daemon behavior, configuration, hardware paths, and existing package name are
  unchanged unless a separate contract authorizes a change.
- OpenRC is the only supported service manager and `t2fand.initd` is the only
  service definition/payload.
- The OpenRC command is the already-foreground daemon. No `pidfile`,
  background/daemonization setting, or network dependency is allowed.
- `/run/t2fand.pid` is daemon-owned; supervisor state is separate.
- OpenRC respawns all child exits, with unlimited count and an exact constant
  two-second delay; explicit stop suppresses respawn.
- `make install` is unconditional OpenRC installation, honors only the stated
  staging/directory variables, and performs no service actions.
- Package payload is exactly `/usr/bin/t2fand` mode 0700 and
  `/etc/init.d/t2fand` mode 0755. The systemd payload is absent.
- `pkgname` remains `t2fand`; no package rename is authorized. Arch OpenRC
  runtime dependency is `unknown`.
- No hardware execution, service execution, host write, package build,
  staged-install, or CI result is implied by this static source contract.

## Security, safety, and trust boundaries

The daemon is root-owned and can write `/run/t2fand.pid`, create
`/etc/t2fand.conf` on first run, and write fan sysfs controls. Configuration and
sysfs ownership/permission hardening are `unknown`. The PID check does not
authenticate identity or provide atomic locking.

The OpenRC wrapper shares the daemon's root and hardware boundary. It must not
background the daemon, claim its PID file, or introduce a network dependency. No
authentication, encryption, secret store, network listener, or new trust
boundary is defined. No secret is recorded or handled by this change.

Installation is staged with `DESTDIR` for acceptance inspection and must not
perform service actions or host writes outside the requested destination. No
service or hardware execution is authorized for this task.

## Observability

| Signal/evidence                      | Meaning                                   | Status                                        |
| ------------------------------------ | ----------------------------------------- | --------------------------------------------- |
| `T2 Fan Daemon must be run as root`  | Non-root startup rejection                | documented daemon behavior; execution unknown |
| `Fan not found` / CPU diagnostic     | Startup sensor/path failure               | documented daemon behavior; execution unknown |
| `T2 Fan Daemon is already running`   | Existing `/proc/<pid>` for PID-file value | documented; not an authenticated health check |
| `T2 Fan Daemon is shutting down...`  | Handled cleanup began                     | documented; cleanup outcome unknown           |
| `/run/t2fand.pid`                    | Daemon liveness hint                      | daemon-owned; not health/auth evidence        |
| OpenRC service status                | Supervised-state status                   | current static interface; runtime unknown     |
| OpenRC respawn                       | Recovery attempt after any child exit     | current static policy; runtime unknown        |
| OpenRC explicit stop                 | Stop path with no respawn                 | current static policy; runtime unknown        |
| Package payload/path/mode inspection | Static packaging evidence                 | required acceptance; not run                  |

No structured logs, metrics, tracing, health endpoint, alerting, or audit record
is defined. Service stdout capture is environment-dependent and `unknown`.

## Compatibility and packaging

- Package contract: Arch `x86_64`, name `t2fand`, current version `1.2.0`, and
  `pkgrel=2` after the requested bump; GPL3.
- Existing declared dependencies remain `linux-t2` and `python`, with `git` as
  the existing build dependency. An Arch OpenRC runtime dependency is `unknown`
  and must not be guessed or added from this contract.
- Static payload contract is exactly `/usr/bin/t2fand` mode 0700 and
  `/etc/init.d/t2fand` mode 0755.
- Compatibility requires Python 3, Linux sysfs, root, and OpenRC. Exact Python,
  kernel, `linux-t2`, OpenRC, Mac-model, and distribution matrices are
  `unknown`.
- The unpinned remote Git source and `sha256sums=('SKIP')` remain; provenance,
  reproducibility, and local/package source equivalence are `unknown`.
- No migration, rollback, backup, upgrade-safety, or fail-safe procedure is
  defined; existence and outcomes are `unknown`.

## Validation and acceptance

No product, service, hardware, package-build, staged-install, or CI check was
run for this contract revision. Current static implementation truth is limited
to the inspected source files; do not claim runtime, package, or staged results.

### Current static acceptance

Delivered-source inspection covers:

1. `t2fand.initd` source identity and unchanged established directives,
   including foreground `supervise-daemon`, no `pidfile`, no background or
   daemonization setting, and no network dependency.
2. `t2fand.service` absence and absence of any systemd install/package path.
3. Makefile absence of `INIT_SYSTEM`, systemd variables, `PREFIX`, and marker
   detection; unconditional `DESTDIR`/`BINDIR`/`OPENRC_INITDDIR` paths, exact
   source payload, and modes 0700/0755; no service actions.
4. PKGBUILD name `t2fand`, incremented `pkgrel`, exactly two install payloads,
   no systemd directory/unit, and no claimed OpenRC runtime dependency.
5. Source-level daemon PID ownership and OpenRC separation of supervisor state.
6. Exact respawn policy: all exits including 0, unlimited count, constant two
   seconds, and explicit-stop/no-respawn contract.

These are static acceptance requirements only. Safe staged inspection may use
`DESTDIR`; no host or service state may be changed. Staged, package, runtime,
and hardware results remain unknown.

### Retired and pending validation

The historical dry-run Makefile parse checks for `INIT_SYSTEM=systemd`,
`openrc`, and `auto` are superseded and are not current OpenRC-only validation.
They did not execute selector branches, invalid-selector handling, `sh -n`,
DESTDIR staging, package build, OpenRC syntax checks, lifecycle checks, or
hardware checks. No result from them proves this target.

Runtime acceptance is pending and must not be performed in this task. If later
authorized, it must separately cover OpenRC start, stop, restart, status,
status-0 and unexpected exits, unlimited respawn, constant two-second delay,
explicit-stop suppression, SIGTERM cleanup, daemon PID ownership, and hardware
boundaries. No verified test command, test suite, fixture, build result, package
artifact, or compatibility matrix exists locally.

`dprint.json` has no ordinary-Markdown association for `SPEC.md`; a formatter
run is not product validation.

## Decisions

- `DEC-001` (**superseded by `DEC-007`):** systemd and its unchanged unit were
  behavioral authority; OpenRC was the closest equivalent.
- `DEC-002` (retained): the daemon stays foreground and owns `/run/t2fand.pid`;
  supervisor state is separate and OpenRC `pidfile` is forbidden.
- `DEC-003` (retained and narrowed to OpenRC): use `supervise-daemon`, unlimited
  all-exit respawn, constant two-second delay, `retry="SIGTERM/5"`, and no
  background variables; explicit stop does not respawn.
- `DEC-004` (**superseded by `DEC-008`):** `INIT_SYSTEM=auto` was the default
  and failed closed on ambiguous runtime markers.
- `DEC-005` (**superseded by `DEC-009`):** package name was `t2fand-openrc` and
  both service definitions shipped.
- `DEC-006` (**superseded by `DEC-010`):** the prior reconciliation treated
  static OpenRC implementation as present and made no staged/package/runtime
  claim; its synchronization claim remains historical evidence only.
- `DEC-007` (current static implementation): OpenRC is the sole supported
  service manager; the retained `t2fand.initd` is the sole service definition
  and payload. The delivered source has no systemd unit.
- `DEC-008` (current static implementation): Makefile installation is
  unconditional OpenRC staging through `DESTDIR`, `BINDIR`, and
  `OPENRC_INITDDIR`, with no service actions.
- `DEC-009` (current static implementation): retain package name `t2fand`, set
  `pkgrel` to 2, and ship exactly the executable and OpenRC init script; do not
  guess an Arch OpenRC dependency.
- `DEC-010`: this is a current static implementation contract. The recorder owns
  later `CONTEXT.md` synchronization; no package, staged-install, or runtime
  outcome is claimed now.

## Cumulative change history

| ID      | State/change                                                                                                                                                                         | Rationale and transition                                                                                                                         |
| ------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------ |
| `H-001` | **Superseded historical baseline:** systemd was the only checked-in service integration; OpenRC metadata was contradictory and unsupported.                                          | Preserved as historical local evidence.                                                                                                          |
| `H-002` | **Superseded pre-implementation transition:** the 2026-08-27 reconciliation added an OpenRC contract, Makefile selection/staging, and both package service definitions.              | Preserved as the prior contract transition; it superseded only the older install/package requirements at that time.                              |
| `H-003` | **Superseded dual-init implementation state:** the checked-in `t2fand.initd`, selector Makefile, systemd unit, and both-definition PKGBUILD were present; systemd was authoritative. | Source inspection did not prove staged installation, package artifacts, OpenRC syntax/lifecycle, hardware, or runtime success.                   |
| `H-004` | **Current static implementation:** OpenRC-only support, retained unchanged `t2fand.initd`, unconditional OpenRC install, and exact two-file package payload.                         | Delivered source supersedes the dual-init/systemd-authoritative state; package, staged-install, runtime, and hardware validation remain unknown. |

## Open questions

| ID      | Question                                                                                                                | Resolution/status                                                                                                                  |
| ------- | ----------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `Q-001` | Which T2 Mac models, kernels, and distributions are supported?                                                          | unknown                                                                                                                            |
| `Q-002` | Is the GPU availability check intended to glob DRM hwmon paths rather than call `Path.exists()` on a literal wildcard?  | unknown                                                                                                                            |
| `Q-003` | Is OpenRC support intended, and where is its definition and validation?                                                 | Superseded question: OpenRC-only support is implemented in source; package, staged-install, and runtime validation remain unknown. |
| `Q-004` | Which exact remote Git revision and checksum should PKGBUILD use?                                                       | unknown; out of scope                                                                                                              |
| `Q-005` | What numeric ranges and threshold relationships are valid?                                                              | unknown; daemon scope unchanged                                                                                                    |
| `Q-006` | What fail-safe action is required after SIGKILL, crash, I/O failure, or power loss?                                     | unknown; daemon scope unchanged                                                                                                    |
| `Q-007` | Should configuration reload without restart be supported?                                                               | unknown                                                                                                                            |
| `Q-008` | What authorized test command, hardware fixture, and acceptance thresholds validate runtime and package behavior?        | No verified local test command exists.                                                                                             |
| `Q-009` | Should releases include only package files while the workflow also lists `*.zip`?                                       | unknown; existing workflow scope unchanged                                                                                         |
| `Q-010` | Should the retired systemd unit or target be restored?                                                                  | No; systemd is out of scope under `DEC-007`.                                                                                       |
| `Q-011` | Is `github.event.head_commit.message` populated for pull-request events?                                                | unknown; existing workflow scope unchanged                                                                                         |
| `Q-012` | Does any workflow or remote release behavior create a Git tag after the local `Create Tag` step?                        | unknown; remote behavior out of scope                                                                                              |
| `Q-013` | Which active runtime markers should the old `INIT_SYSTEM=auto` selector use?                                            | Superseded by unconditional OpenRC installation.                                                                                   |
| `Q-014` | Which OpenRC dependency declarations are justified by local filesystem, `/run`, sysfs, or hardware readiness?           | unknown; no network dependency permitted.                                                                                          |
| `Q-015` | Do OpenRC lifecycle, explicit-stop, unlimited-respawn, and exact-delay behaviors match the contract on supported hosts? | unknown; runtime validation pending and out of scope for this task.                                                                |
| `Q-016` | What Arch package dependency provides OpenRC at runtime?                                                                | unknown; no local authoritative evidence; do not add or claim one.                                                                 |
| `Q-017` | Does this implementation preserve the exact two-file package payload and requested `pkgrel` bump?                       | Delivered PKGBUILD statically shows the exact two-file payload and `pkgrel=2`; package build remains unknown.                      |
