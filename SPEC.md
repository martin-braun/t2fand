# t2fand — Product Contract

## Contract status and document roles

This document is the contract truth for the local t2fand fork. `documented`
means supported by checked-in source, configuration, or test definitions; it
does not mean runtime-tested or shipped. The global thermal fail-safe and
complete OpenRC revision now have checked-in daemon, service, package, and
fake-sysfs test definitions. Their runtime, hardware, service, package, and
syslog outcomes remain separate and unknown. Existing source facts remain static
evidence. Hardware, OpenRC lifecycle, package, staged-install, and test
execution are reported separately as `unknown` until verified.

`SPEC.md` owns contract truth. The recorder synchronizes `CONTEXT.md` after
implementation. `README.md` is concise human onboarding; exhaustive contract
and implementation detail stays in `SPEC.md` and `CONTEXT.md`. `AGENTS.md`
owns onboarding, ownership, routing, safety, and protected-surface rules.

## Problem and goals

`t2fand` is a Python daemon for automatic fan-speed control on Macs with an
Apple T2 chip running Linux. It must consider every exposed Linux hwmon
temperature, fail high when thermal input or configuration is unsafe, preserve
ordinary smoothed control, and remain one supported OpenRC service.

Goals:

- retain Python, the extensionless `t2fand` executable, and its installed path;
- keep one-second sampling, at most five valid normal samples, fractional
  Celsius, and the existing linear, cubic exponential, and logarithmic curves;
- rediscover and reopen sysfs paths every cycle; never retain open sysfs
  handles;
- make CPU input mandatory while treating GPU input as optional with explicit
  missing/recovery transitions;
- make configuration, sensor, and fan-control failure behavior explicit;
- provide flushed direct output and compact `--verbose` telemetry;
- keep OpenRC as the only supported service manager and retain the two-file
  runtime payload;
- add bounded, backed-off OpenRC crash recovery and util-linux logger routing;
- maintain fake-fixture tests and updated operator documentation for the
  revision.

## Users, scope, and non-goals

| Role                      | Need                                          | Status                                        |
| ------------------------- | --------------------------------------------- | --------------------------------------------- |
| Linux user of a T2 Mac    | Automatic safe temperature-driven fan control | checked-in contract; hardware outcome unknown |
| Root/system administrator | Configure and operate the OpenRC service      | checked-in workflow; execution unknown        |
| Arch package consumer     | Install the daemon and OpenRC definition      | checked-in package definition; build unknown  |
| Maintainer                | Test, package, and document the revision      | checked-in definitions; execution unknown     |

In scope: the Python daemon, global hwmon discovery, configuration and fail-safe
behavior, direct output, verbose telemetry, best-effort cleanup, `t2fand.initd`,
unconditional OpenRC installation, Arch metadata, a standard library `unittest`
suite, a project-native test target, and affected README, comments, and package
descriptions.

Out of scope: alternate init systems, service selectors, systemd artifacts,
package rename, payload expansion, GUI, network API/dependency, adaptive
scheduling, persistent sysfs handles, Rust implementation, remote maintenance,
secrets, unrelated files.

## Terminology

| Term                | Definition                                                                                                                                                                               |
| ------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| valid temperature   | One successful, non-faulted hwmon input parse; zero/ambient values are valid for non-CPU sensors, while non-positive CPU readings do not satisfy CPU availability                        |
| required CPU        | The discovered CPU/coretemp channel set required for safe operation; at least one selected channel must be usable and positive, while sibling non-positive readings do not invalidate it |
| GPU-missing         | No temperature input below any exact numeric DRM card is present in the current topology                                                                                                 |
| control temperature | Highest valid temperature in the current cycle                                                                                                                                           |
| sensor fail-safe    | Mode that bypasses smoothing and attempts maximum fan speed because required thermal input is unsafe                                                                                     |
| config-failsafe     | Mode that bypasses curves and attempts maximum fan speed because any fan policy is invalid or unreadable                                                                                 |
| control-error       | Fatal loss of the ability to establish or command maximum fan speed                                                                                                                      |
| target RPM          | Requested fan output after policy and clamping; not a tachometer measurement                                                                                                             |
| actual RPM          | One diagnostic tachometer read, or `unknown` when it cannot be read or parsed                                                                                                            |
| daemon PID          | PID written by t2fand to `/run/t2fand.pid`; supervisor state is separate                                                                                                                 |

## Stable requirements

Requirement IDs are stable. A changed contract receives a new ID. Prior
requirements remain below as historical evidence even when superseded.

### Historical requirements retained

| ID        | Prior requirement                                                                                                                                                                                                                                                                                                                                                                                                                                             | Status                                                                      |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| `REQ-001` | Refuse non-root startup and print `T2 Fan Daemon must be run as root`.                                                                                                                                                                                                                                                                                                                                                                                        | historical baseline; retained by `REQ-029`                                  |
| `REQ-002` | Accept any existing path matched by the initial T2 fan glob; otherwise print `Fan not found` and exit 1.                                                                                                                                                                                                                                                                                                                                                      | superseded by `REQ-031`, `REQ-037`                                          |
| `REQ-003` | Require an existing CPU-glob path and `get_cpu_temp() != -1`; print `CPU temperature sensor not found` and exit 1 on failure.                                                                                                                                                                                                                                                                                                                                 | superseded by `REQ-031`, `REQ-033`                                          |
| `REQ-004` | Use `/run/t2fand.pid`, reject a live `/proc/<pid>`, and remove a stale PID file.                                                                                                                                                                                                                                                                                                                                                                              | narrowed/superseded by `REQ-029`, `REQ-042`                                 |
| `REQ-005` | Discover direct `fan*_input` children of the first matched fan directory; zero fans may continue.                                                                                                                                                                                                                                                                                                                                                             | superseded by `REQ-037`                                                     |
| `REQ-006` | Read fan limits/input, clamp requested speed, and write integer output; main loop does not call `get_speed`.                                                                                                                                                                                                                                                                                                                                                  | superseded by `REQ-037`, `REQ-038`, `REQ-040`                               |
| `REQ-007` | Write manual `1` before control and attempt manual `0` during SIGTERM/SIGINT cleanup.                                                                                                                                                                                                                                                                                                                                                                         | superseded by `REQ-042`                                                     |
| `REQ-008` | Generate `Fan1`…`FanN` with `55`, `75`, `linear`, `false` defaults when config is absent.                                                                                                                                                                                                                                                                                                                                                                     | retained by `REQ-036`                                                       |
| `REQ-009` | Require four options and accept `linear`, `exponential`, or `logarithmic`; invalid config printed an error and exited 1.                                                                                                                                                                                                                                                                                                                                      | superseded by `REQ-036`                                                     |
| `REQ-010` | Exact `always_full_speed == "true"` selects maximum; otherwise use ordered thresholds and curves.                                                                                                                                                                                                                                                                                                                                                             | superseded by `REQ-036`, `REQ-039`                                          |
| `REQ-011` | Preserve the linear, cubic exponential, and `math.log` logarithmic expressions.                                                                                                                                                                                                                                                                                                                                                                               | retained by `REQ-039`                                                       |
| `REQ-012` | Select CPU or greater CPU/GPU, retain at most five samples, round mean to two decimals, update every fan, and sleep one second.                                                                                                                                                                                                                                                                                                                               | superseded by `REQ-030`, `REQ-033`, `REQ-034`, `REQ-039`                    |
| `REQ-013` | Handled SIGTERM/SIGINT printed shutdown text, disabled manual mode sequentially, attempted PID removal, and exited.                                                                                                                                                                                                                                                                                                                                           | superseded by `REQ-042`                                                     |
| `REQ-014` | Historical systemd unit: simple foreground command, `/run/t2fand.pid`, always restart, two-second delay, default target.                                                                                                                                                                                                                                                                                                                                      | superseded by `REQ-023`, `REQ-043`                                          |
| `REQ-015` | Historical systemd-only install copied the daemon and systemd unit with modes 0700/0644.                                                                                                                                                                                                                                                                                                                                                                      | superseded by `REQ-024`, `REQ-050`                                          |
| `REQ-016` | Historical package metadata named `t2fand-openrc` while packaging the executable and systemd unit.                                                                                                                                                                                                                                                                                                                                                            | superseded by `REQ-025`, `REQ-050`                                          |
| `REQ-017` | Existing GitHub Actions push/PR workflow retains its triggers, runner, gates, artifact, and release configuration; execution unknown.                                                                                                                                                                                                                                                                                                                         | retained; unrelated to this revision                                        |
| `REQ-018` | Existing OpenRC script invokes `/usr/bin/t2fand` through `supervise-daemon` with two-second delay, unlimited respawn, zero delay step, and `retry="SIGTERM/5"`; no pidfile/backgrounding.                                                                                                                                                                                                                                                                     | superseded by `REQ-043`, `REQ-044`                                          |
| `REQ-019` | Historical `INIT_SYSTEM` selector accepted `auto`, `systemd`, or `openrc` with fail-closed marker detection.                                                                                                                                                                                                                                                                                                                                                  | superseded by `REQ-024`                                                     |
| `REQ-020` | Historical package was `t2fand-openrc`, version `1.2.0-1`, and shipped both service definitions.                                                                                                                                                                                                                                                                                                                                                              | superseded by `REQ-025`, `REQ-050`                                          |
| `REQ-021` | Historical systemd-authoritative contract treated OpenRC as its equivalent; both wrapped the foreground daemon.                                                                                                                                                                                                                                                                                                                                               | superseded by `REQ-023`                                                     |
| `REQ-022` | Historical dual-manager contract respawned every exit without a cap after two seconds and did not respawn on explicit stop.                                                                                                                                                                                                                                                                                                                                   | superseded by `REQ-043`                                                     |
| `REQ-023` | OpenRC is the sole supported manager and `t2fand.initd` the sole service definition; no systemd artifact or workflow.                                                                                                                                                                                                                                                                                                                                         | retained by `REQ-043`, `REQ-050`                                            |
| `REQ-024` | `make install` is unconditional OpenRC installation, honors `DESTDIR`, `BINDIR=/usr/bin`, `OPENRC_INITDDIR=/etc/init.d`, performs no compilation, and installs only daemon 0700/init 0755.                                                                                                                                                                                                                                                                    | retained by `REQ-050`                                                       |
| `REQ-025` | Package name is `t2fand`; package payload is daemon 0700 and OpenRC init 0755; no systemd payload or guessed OpenRC dependency.                                                                                                                                                                                                                                                                                                                               | superseded/narrowed by `REQ-050`                                            |
| `REQ-026` | OpenRC runs the foreground daemon, daemon owns `/run/t2fand.pid`, and every exit respawns unlimited after exactly two seconds; explicit stop suppresses respawn.                                                                                                                                                                                                                                                                                              | superseded by bounded `REQ-043`; retained PID/foreground portions           |
| `REQ-027` | No OpenRC pidfile/backgrounding/network dependency; installation performs no service state changes.                                                                                                                                                                                                                                                                                                                                                           | retained by `REQ-043`, `REQ-044`                                            |
| `REQ-028` | Supported operator workflow is OpenRC `rc-service` with optional `rc-update`; direct Python execution is not a second manager workflow.                                                                                                                                                                                                                                                                                                                       | retained by `REQ-043`                                                       |
| `REQ-033` | CPU remains mandatory: no usable CPU reading, non-positive CPU reading, malformed CPU data, or inaccessible required CPU input enters sensor fail-safe immediately. At least one usable system temperature is required. Valid non-CPU low/ambient readings are accepted. Any discovered non-CPU read/parse/fault failure enters sensor fail-safe for that cycle; an absent source is not itself a fault. Select the highest valid reading across all sources. | superseded by `REQ-048`; stricter non-positive-CPU rule retained as history |

### Revised requirements

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Acceptance evidence                                                                                                                |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------- |
| `REQ-029` | Keep root-required, foreground, single-process Python execution. Put orchestration in import-safe `main(argv=None)` under the normal main guard. Importing for tests must not exit, check root, install signals, touch real sysfs, `/etc`, or `/run`. Use snake_case names, named state/config objects, focused discovery/parse/select/control/telemetry/cleanup functions, precise exceptions, module and useful API docstrings.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in source; runtime unverified                                                                                              |
| `REQ-030` | Preserve one-second sampling, at most five valid normal samples, fractional Celsius, existing curves, ordinary smoothing, and immediate maximum on any fail-safe or valid configured full speed. Re-scan and reopen sysfs paths each cycle; retain no open sysfs handles.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | checked-in source and test definitions; execution unverified                                                                       |
| `REQ-031` | Each cycle enumerate `/sys/class/hwmon/hwmon*/temp*_input`, existing CPU/coretemp paths, and `device/hwmon/hwmon*/temp*_input` below every DRM entry whose basename exactly matches `^card\d+$`. Exclude connector names such as `card0-DP-1`. Union candidates and deduplicate by resolved path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in source and fake-sysfs test definitions; runtime unknown                                                                 |
| `REQ-032` | Read each selected input exactly once per cycle and parse signed integer millidegrees Celsius. Read optional `name`, `tempN_label`, DRM identity, and path fallback to derive a stable human label. Optional labels never gate operation. A present fault flag reporting a fault makes that sensor unavailable for the cycle. No `-1`, fabricated high value, or other numeric sentinel represents failure; failed readings are `unknown`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | checked-in source and fake-sysfs test definitions; execution unverified                                                            |
| `REQ-034` | GPU is optional. GPU sensors are those resolved below exact numeric DRM cards. If none are present, continue with other valid sources and emit one warning on transition into `gpu-missing`; emit one recovery notice when GPU temperatures reappear. Do not repeat unchanged warnings every second; verbose telemetry continues to show `gpu_temps=missing`. Sensors/cards may appear or disappear across cycles.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | checked-in source and topology test definitions; execution unverified                                                              |
| `REQ-035` | Externally report at least these modes: `curve`, `configured-full`, `config-failsafe`, `sensor-failsafe`, `control-error`, and `shutting-down`. `curve` is valid automatic policy; `configured-full` is valid `always_full_speed=true`; fail-safe modes command maximum; `control-error` is fatal; shutdown is the common cleanup state. State and reason transitions are reported.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | checked-in source and test definitions; execution unverified                                                                       |
| `REQ-036` | Sensor/config fail-safe bypasses smoothing and immediately attempts every fan's known maximum. Sensor fail-safe stays alive and retries discovery once per second while control remains available. Return to normal policy only after five consecutive cycles in which all required inputs are valid; reset the count on any invalid cycle, clear old history, then collect the five new maxima before normal smoothing. Configuration is read once at startup; config-failsafe persists until restart after repair.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in source and recovery test definitions; execution unverified                                                              |
| `REQ-037` | Configuration keeps four options and generated defaults: `low_temp=55`, `high_temp=75`, `speed_curve=linear`, `always_full_speed=false`. Validate every detected fan before normal curves. Reject missing sections/options, unreadable or malformed INI, malformed/non-finite thresholds, invalid curves, `low_temp >= high_temp`, and Boolean text other than case-insensitive `true`/`false` after INI whitespace handling. Any defect globally selects config-failsafe, commands every fan maximum, prints the exact section/key or file problem, and never silently edits/normalizes administrator config. A valid `true` selects `configured-full`, not an error. Config-generation failure takes the same safe path when maxima are available.                                                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in source and configuration test definitions; execution unverified                                                         |
| `REQ-038` | Require at least one complete controllable fan. Read usable integer min/max limits, require a usable maximum, clamp every requested output to the reported range, enable manual mode before normal control, and write outputs by reopening sysfs paths. No fan, unreadable maximum, inability to enable manual mode, inability to write maximum, or equivalent loss of control authority is fatal. Before fatal exit, attempt maximum on every still-controllable fan, perform cleanup, and exit nonzero for OpenRC recovery.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | superseded by `REQ-049`; retained historical evidence                                                                              |
| `REQ-039` | Preserve threshold behavior: at/below low uses minimum, at/above high uses maximum, and intermediate values use the existing linear, cubic `exponential`, or `math.log` `logarithmic` expressions. Validate or guard calculations so they cannot raise or produce non-finite control output; unsafe policy follows config-failsafe. `always_full_speed=true` takes precedence.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | checked-in source and curve test definitions; execution unverified                                                                 |
| `REQ-040` | Use `argparse` with `-v`/`--verbose`; unknown arguments fail clearly before hardware mutation. Use direct `print()` output, explicit stdout/stderr, formatted strings, and `flush=True`; do not use Python logging, direct syslog APIs, or spawn logger from Python. Default output includes startup/shutdown summaries, warnings/errors, and fail-safe, GPU-missing, and recovery transitions, but no normal per-second line. Verbose output emits one compact flushed record per second.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | checked-in source and CLI/output test definitions; execution unverified                                                            |
| `REQ-041` | Every verbose record includes every discovered sensor label and value or `unknown`, `gpu_temps=missing` when applicable, highest current valid temperature, rolling mean only during normal smoothing, mode/status/reason, and each fan's low/high, curve, configured full-speed value, `target_rpm`, and `actual_rpm` or `unknown`. Actual RPM is diagnostic; a failed read never suppresses the target and forces all controllable fans maximum for safety. Repeated default errors print on state/reason change and at most once per 60-second reminder interval.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in source and telemetry test definitions; execution unverified                                                             |
| `REQ-042` | SIGINT/SIGTERM handlers only request shutdown; they perform no file I/O. After manual mode begins, one outer `try/finally` owns cleanup. Fatal paths independently attempt maximum for every fan first, independently disable manual mode for every fan next, and always attempt PID removal. Preserve and print the original failure and cleanup failures; fatal exit is nonzero. Cleanup is best effort and cannot run after SIGKILL, power loss, kernel panic, interpreter/native abort, or unavailable hardware write authority. Malformed PID files produce a clear diagnostic and safe stale-file recovery, not an unhandled parse exception.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | checked-in source and cleanup/signal/PID test definitions; execution unverified                                                    |
| `REQ-043` | OpenRC remains sole supported manager and `t2fand.initd` sole service artifact. It runs `/usr/bin/t2fand` foreground through `supervise-daemon`, does not set `pidfile`, background, daemonization, or network dependencies, and keeps daemon ownership of `/run/t2fand.pid`. Use normal local-filesystem dependency ordering and soft `logger` use. Preserve a two-second base respawn delay, but bound crash loops to five respawns in a 60-second window and use a two-second respawn-delay step for backoff. Every child exit is eligible within that bound; explicit `rc-service ... stop` suppresses respawn. Selected directives and their supported OpenRC semantics must be documented and statically checked.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | checked-in init definition and static test definitions; OpenRC runtime unknown                                                     |
| `REQ-044` | Route OpenRC stdout through `output_logger="/usr/bin/logger -t t2fand -p daemon.info"` and stderr through `error_logger="/usr/bin/logger -t t2fand -p daemon.err"`. Make daemon arguments configurable without editing the init script: source normal `/etc/conf.d/t2fand` value `t2fand_args` into `command_args`, default empty, so `t2fand_args="--verbose"` is supported. Add direct `util-linux` runtime dependency. Do not require a particular syslog daemon; logger submits to the administrator-selected receiver.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | checked-in init/package definitions and static test definitions; logger delivery unknown                                           |
| `REQ-045` | Prior install/package contract: keep `make install` unconditional OpenRC-only, with no compilation or service action, honor `DESTDIR`, overridable `BINDIR` default `/usr/bin`, and `OPENRC_INITDDIR` default `/etc/init.d`; install only daemon 0700 and init script 0755. Keep package name `t2fand`, retain `linux-t2`, `python`, and `git`, add `util-linux`, and package exactly `/usr/bin/t2fand` and `/etc/init.d/t2fand`; the prior release was `1.2.0-3`. No alternate artifact or payload is allowed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | superseded by `REQ-050`; historical release/install contract retained         |
| `REQ-046` | Add a standard-library `unittest` suite using temporary fake sysfs/config/run trees and mocks. Add and document project-native `make test`; tests require neither root, real `/sys`, fan hardware, OpenRC, nor a syslog daemon.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | checked-in test source and target; `make test` outcome unverified (not run)                                                        |
| `REQ-047` | Prior documentation-placement contract: rewrite affected operator documentation to place the full safety, discovery, smoothing, configuration, fail-safe, mode, telemetry, OpenRC, logger, cleanup, testing, and cautious manual-check contract in the README. Never instruct deletion of live sysfs nodes or obstruction of real cooling sensors. Remove stale CPU/card0-only or unsupported-manager claims from current docs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | superseded by `REQ-051`; historical documentation requirement retained         |
| `REQ-048` | CPU remains mandatory, but CPU availability is satisfied when at least one selected CPU/coretemp channel is successfully read, fault-free, parsed, and positive. A non-positive CPU reading is a valid reading that does not satisfy availability; it does not invalidate a positive sibling channel. If no selected CPU channel is usable and positive, enter sensor fail-safe immediately. Any discovered selected sensor input read/parse/fault failure, including a CPU channel, enters sensor fail-safe for that cycle even when another CPU channel is positive. At least one usable system temperature is required. Valid non-CPU low/ambient readings are accepted; an absent source is not itself a fault. Select the highest valid reading across all sources, with failures `unknown` and no fabricated temperatures or numeric sentinels.                                                                                                                                                                                                                                                                                                                                                     | checked-in source and fake-sysfs test definitions; execution unverified                                                            |
| `REQ-049` | Require at least one discovered fan and require every discovered, resolved-path-deduplicated fan candidate to be complete and controllable. The discovered set is the union of T2 and class-hwmon fan candidates, deduplicated by resolved base path; one complete fan does not mask another candidate with an unreadable/incomplete limit or invalid range. Each candidate must provide usable integer minimum and maximum limits with minimum no greater than maximum. No fan, any unreadable fan maximum, any incomplete/invalid discovered fan, inability to enable manual mode, inability to write a required maximum, or equivalent loss of control authority is fatal `control-error`; no candidate may be silently ignored or used as an alternate. Clamp each requested output to that fan's reported range and reopen sysfs paths for operations. For every fatal-control path, independently attempt each discovered fan's known maximum, record a missing maximum as a failed attempt, continue after per-fan failures, then independently attempt manual-mode disable for each fan and attempt PID removal; preserve the original and cleanup failures and exit nonzero for OpenRC recovery. | checked-in source enforces all-candidate rejection and targeted partial-fan fixture coverage is present; test execution unverified |
| `REQ-050` | Keep `make install` unconditional OpenRC-only, with no compilation or service action, honor `DESTDIR`, overridable `BINDIR` default `/usr/bin`, and `OPENRC_INITDDIR` default `/etc/init.d`; install exactly daemon `/usr/bin/t2fand` mode 0700 and init script `/etc/init.d/t2fand` mode 0755. Keep package name `t2fand`, Arch `x86_64` and GPL3 metadata, release `2.0.0-1` (`pkgver=2.0.0`, `pkgrel=1`), dependencies `linux-t2`, `python`, and `util-linux`, and `git` as a build dependency. Package exactly those two files; no alternate artifact, service definition, selector, or payload is allowed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in Makefile and PKGBUILD; package build, staging, and installation unknown |
| `REQ-051` | Keep README as concise operator onboarding. It must retain pointers for operator actions, safety, configuration, OpenRC operation, observability, and project-native testing, while exhaustive limits, implementation behavior, fail-safe semantics, modes, telemetry fields, and design truth remain owned by `SPEC.md` and `CONTEXT.md`. Summaries must not weaken or redefine the safety/product requirements in this contract, and documentation must not instruct deletion of live sysfs nodes, obstruction of cooling sensors, or unsupported service-manager workflows.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | documentation review remains required; current conformance and runtime outcomes unverified |

## Runtime rules

### Startup

The daemon validates root, parses CLI arguments, handles PID state, discovers
fans, and requires every discovered candidate to be complete and controllable.
It then generates configuration only when absent, validates all fan policies,
installs signal-request handlers, enables manual mode, and enters the outer
lifecycle `try/finally`. A fan-discovery or control-authority defect is
`control-error`; a complete fan does not mask another discovered incomplete fan.
A configuration defect does not terminate before fan protection. If known maxima
are available, all fans go to maximum and the process remains alive in
`config-failsafe`; loss of fan control authority exits nonzero.

### Sampling and states

Each one-second cycle rediscoveries sensors, reads each selected input once,
records unknown failures without numeric sentinels, and selects the maximum
valid temperature. CPU availability requires at least one usable positive CPU
channel; a non-positive sibling does not invalidate it, but any discovered
sensor input or fault read/parse failure invalidates the cycle. Normal `curve`
control appends only valid selected maxima to the five-sample buffer and uses
its rounded two-decimal mean. Fail-safe control does not append or use the
rolling mean. Five consecutive fully valid required cycles clear the old buffer;
the five recovery maxima become the new normal history before curve smoothing
resumes. A valid always-full policy uses `configured-full` after required sensor
recovery.

Sensor failure with writable maxima is recoverable and remains alive. Failed
sensor readings, including CPU readings, are reported as `unknown`; a positive
CPU sibling does not mask another discovered read/parse/fault failure. GPU
absence is a topology state, not by itself a failure. Any inability to establish
or command maximum is a fatal control error. Configuration fail-safe remains
until restart.

### Curves and fan output

Every target is clamped to each fan's reported integer min/max before writing.
Normal curves retain the existing formulas and threshold ordering. Fan output,
manual-mode writes, limits, and tachometer reads reopen sysfs paths as needed;
no persistent file object is retained. Actual RPM read failure reports
`actual_rpm=unknown` and commands maximum for all controllable fans.

### Cleanup

Signal handlers set a shutdown request. The normal lifecycle observes it,
reports `shutting-down`, and runs common cleanup. Fatal cleanup first attempts
maximum output independently, then attempts manual-mode disable independently,
then attempts PID removal regardless of earlier errors. It reports all cleanup
failures alongside the original failure. No cleanup claim covers SIGKILL, power
loss, kernel panic, interpreter/native abort, or hardware that no longer accepts
writes.

## Interfaces

| ID       | Interface                          | Contract                                                                                                                                                                                                                                                              | Status                                                                                   |
| -------- | ---------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------- |
| `IF-001` | CLI/process                        | Foreground `t2fand`; `-v`/`--verbose`; unknown arguments fail before mutation.                                                                                                                                                                                        | checked-in source; runtime unverified                                                    |
| `IF-002` | INI file                           | `/etc/t2fand.conf`; `Fan1`…`FanN`; four required keys; startup-only read; defaults as `REQ-037`.                                                                                                                                                                      | checked-in source; config runtime unknown                                                |
| `IF-003` | Linux fan sysfs                    | Discover and deduplicate all fan candidates; read usable integer `<base>_max` and `<base>_min` with minimum no greater than maximum; write `<base>_output` and `<base>_manual`; reopen paths. Any incomplete candidate or loss of maximum-control authority is fatal. | checked-in source; hardware unknown                                                      |
| `IF-004` | Linux temperature sysfs            | Global hwmon plus coretemp and exact numeric DRM-card ancestry; signed millidegrees; optional labels/fault metadata; at least one usable positive selected CPU channel required, while any selected input or fault read/parse failure is fail-safe.                   | checked-in source and fake-sysfs test definitions; hardware/runtime unknown              |
| `IF-005` | PID file                           | Daemon-owned `/run/t2fand.pid`; decimal PID; malformed/stale handling per `REQ-042`; no supervisor reuse.                                                                                                                                                             | checked-in source and test definitions; runtime unverified                               |
| `IF-006` | POSIX signals                      | SIGINT/SIGTERM request common cleanup only.                                                                                                                                                                                                                           | checked-in source and test definitions; runtime unverified                               |
| `IF-007` | Historical systemd unit            | `Type=simple`, restart, PIDFile, and default-target interface from the prior unit.                                                                                                                                                                                    | superseded historical interface                                                          |
| `IF-008` | Historical Make selector           | `INIT_SYSTEM` and systemd/OpenRC selector interface.                                                                                                                                                                                                                  | superseded historical interface                                                          |
| `IF-009` | Historical Arch package            | Prior package installed executable and both service definitions.                                                                                                                                                                                                      | superseded historical interface                                                          |
| `IF-010` | GitHub Actions                     | Existing push/PR package workflow and gates.                                                                                                                                                                                                                          | retained; execution unknown                                                              |
| `IF-011` | OpenRC init script                 | `/etc/init.d/t2fand`, `/usr/bin/t2fand`, foreground `supervise-daemon`, directives in `REQ-043`, logger routing in `REQ-044`.                                                                                                                                         | checked-in init definition and static test definitions; OpenRC runtime unknown           |
| `IF-012` | Historical service selector        | `INIT_SYSTEM=auto` and explicit systemd/OpenRC selection.                                                                                                                                                                                                             | superseded by OpenRC-only `IF-017`                                                       |
| `IF-013` | Historical PID/supervisor boundary | Daemon PID ownership and OpenRC omission of `pidfile`.                                                                                                                                                                                                                | retained/narrowed by `IF-016`                                                            |
| `IF-014` | Make install                       | `DESTDIR`, `BINDIR`, and `OPENRC_INITDDIR` unconditional OpenRC staging only.                                                                                                                                                                                         | checked-in Makefile; staging unverified                                                  |
| `IF-015` | Arch package                       | Unchanged package name; exactly daemon/init payload plus declared dependencies.                                                                                                                                                                                       | checked-in package definition; build/staging unknown                                     |
| `IF-016` | PID/supervisor boundary            | Daemon owns `/run/t2fand.pid`; supervisor state is separate; wrapper `pidfile` forbidden.                                                                                                                                                                             | retained by `REQ-043`                                                                    |
| `IF-017` | Service-manager boundary           | OpenRC only; `/etc/init.d/t2fand` only service artifact.                                                                                                                                                                                                              | checked-in source/package definitions; runtime unknown                                   |
| `IF-018` | OpenRC argument configuration      | `/etc/conf.d/t2fand`, optional `t2fand_args`, passed as `command_args`; no shipped third runtime payload file.                                                                                                                                                        | checked-in init definition and static test definitions; runtime unknown                  |
| `IF-019` | OpenRC logger transport            | `/usr/bin/logger` from util-linux; stdout `daemon.info`, stderr `daemon.err`, tag `t2fand`.                                                                                                                                                                           | checked-in init/package definitions and static test definitions; logger delivery unknown |

## Runtime state and paths

| State/path                 | Meaning and ownership                                                                                             |
| -------------------------- | ----------------------------------------------------------------------------------------------------------------- |
| `/etc/t2fand.conf`         | Administrator policy; generated only when absent; never normalized on validation failure; read once per start.    |
| `/etc/conf.d/t2fand`       | Optional OpenRC administrator arguments; `t2fand_args` may enable `--verbose`; not a package payload requirement. |
| `/run/t2fand.pid`          | Decimal daemon PID; daemon-owned; stale cleanup per contract; not authenticated locking.                          |
| OpenRC supervisor state    | Separate manager state; must not claim daemon PID.                                                                |
| `/etc/init.d/t2fand`       | Installed sole OpenRC definition, mode 0755.                                                                      |
| `/usr/bin/t2fand`          | Installed extensionless Python executable, mode 0700.                                                             |
| Fan sysfs files            | Kernel/device boundary; reopened for each operation.                                                              |
| Hwmon temperature files    | Per-cycle discovered/read inputs; aliases deduplicated by resolved path.                                          |
| `temps` history            | In-memory maximum temperatures; at most five valid normal/recovery samples; cleared on sensor recovery.           |
| Mode/reason/topology state | In-memory externally reported state; transitions are logged, repeated reasons are rate-limited by default.        |

## OpenRC supervision and operation

OpenRC is the only supported manager. The supported commands are:

```text
rc-update add t2fand default       # optional enablement
rc-service t2fand start
rc-service t2fand status
rc-service t2fand stop
rc-service t2fand restart
```

The init script must use `#!/sbin/openrc-run`, `command=/usr/bin/t2fand`,
`supervisor="supervise-daemon"`, `respawn_delay="2"`, finite `respawn_max="5"`,
`respawn_period="60"`, and `supervise_daemon_args="--respawn-delay-step 2"`,
plus `retry="SIGTERM/5"`. It must declare local filesystem ordering,
`use logger`, and must define no network dependency, custom service manager,
backgrounding, or supervisor `pidfile`.

These values mean a base two-second delay, incremental two-second crash backoff,
and no more than five automatic respawns in a 60-second crash window. The child
may exit with any status and is eligible while within the bound. Explicit
administrator stop suppresses recovery. OpenRC directive support and exact
lifecycle results are not verified here.

`output_logger` and `error_logger` route direct flushed application streams to
the administrator-selected syslog receiver. The daemon does not invoke `logger`;
no particular syslog daemon or persisted destination is required.

## Installation and package contract

`make install` has no selector, compilation, service action, or alternate init
branch. It honors only `DESTDIR`, `BINDIR`, and `OPENRC_INITDDIR`, and installs
the two files and modes in `REQ-050`. The Arch package is named `t2fand` at
release `2.0.0-1`, retains its checked-in metadata, retains `linux-t2`,
`python`, and `git`, and includes `util-linux` for `/usr/bin/logger`. The
package payload remains exactly the daemon and OpenRC init script. No package
rename, systemd directory, unit, post-install service action, or guessed
syslog daemon dependency is allowed.

## Workflows

### Configuration

First start generates one default section per detected fan. Administrators may
edit the four options. The file is read once at startup; repair requires a
restart. Invalid config globally requests maximum rather than terminating before
fan protection. Config-generation failure follows the same path when fan maxima
are controllable.

### Service and logs

Install without starting or enabling any service. Optionally configure
`/etc/conf.d/t2fand` with `t2fand_args="--verbose"`, then use OpenRC commands.
Read routed output through the local syslog facility (`/var/log/messages`,
`/var/log/daemon.log`, `logread`, or another administrator-selected location).
Persisted logs require a running receiver; exact destination is unknown.

### Recovery

Sensor/config input failures with control authority remain alive at maximum and
retry as specified. Control authority failures exit nonzero for bounded OpenRC
supervision. Configuration recovery requires restart. Cleanup is best effort. No
hardware, OpenRC, package, or syslog execution is claimed in this task.

## Constraints, safety, and trust boundaries

- Root and Linux sysfs remain required; exact hardware/model/kernel/distribution
  support is unknown.
- Every valid discovered temperature can influence control; the hottest value is
  selected. CPU is mandatory through at least one usable positive selected
  channel; non-positive CPU siblings do not invalidate it. GPU is optional.
- Any discovered selected sensor input or fault read/parse failure, including a
  CPU channel, enters sensor fail-safe; absence alone is not a fault.
- Fail-safe is a control state, not a fabricated temperature. Fail-safe and
  configured full speed bypass smoothing.
- All discovered fans share global safety decisions; one invalid policy or
  incomplete fan does not permit another fan to remain on an untrusted curve,
  and a complete fan does not mask it.
- Known maxima and writable controls are required for recoverable safe control;
  every discovered fan must be complete, and inability to command maximum is
  fatal.
- `/run/t2fand.pid` is daemon-owned. The PID existence check is not identity
  authentication or atomic locking.
- No secrets, network listener, encryption, direct syslog API, Python logging
  framework, persistent sysfs handle, or remote source claim is introduced.
- Cleanup cannot guarantee fan state after abrupt power/kernel/interpreter or
  hardware failure.
- OpenRC is sole service integration; package payload is exactly two files.

## Observability

Default output is flushed and contains startup/shutdown summaries, warnings,
errors, topology/state transitions, exact config problems, mode, and failure
reasons. Verbose output adds one record each second with all sensor labels and
values/unknown states, `gpu_temps=missing`, hottest value, smoothing/recovery
state, mode/reason, and per-fan `target_rpm` versus `actual_rpm`. Logger routing
is service-level transport only. No metrics, tracing, health endpoint, or audit
store is defined.

## Compatibility and dependencies

Compatibility requires Python 3, Linux hwmon/sysfs, root, and OpenRC. Arch
target remains `x86_64`; package identity is `t2fand`, GPL3, release `2.0.0-1`
(`pkgver=2.0.0`, `pkgrel=1`). Runtime dependencies are `linux-t2`, `python`,
and `util-linux`; `git` remains a build dependency. No specific syslog daemon
is required. The unpinned remote Git source and skipped checksum remain
existing provenance risks and are not changed here.

## Validation and acceptance

No test execution, hardware access, root execution, OpenRC lifecycle,
staged-install, package build, or syslog delivery is claimed here. Current
checked-in evidence is the daemon source, OpenRC definition, Makefile, PKGBUILD,
and fake-sysfs unittest definitions. It establishes source/static definitions
and test-definition presence only; it does not establish runtime behavior or any
hardware, service, package, staging, or syslog outcome. The `make test` outcome
remains unverified because it was not run.

Runtime and integration acceptance remains required:

1. `make test` using standard-library unittest fake sysfs/config/run trees and
   mocks, covering global hwmon, CPU/GPU/Wi-Fi/storage/arbitrary channels,
   numeric DRM versus connectors, alias deduplication, one read per cycle,
   hottest selection, GPU-missing/recovery transitions, mixed CPU channels with
   a positive and non-positive sibling, all sensor/CPU/fault/parse failures
   including a positive CPU plus another failed channel, immediate maximum,
   five-cycle recovery and history reset, one-second/five-sample smoothing, all
   curves, every config defect, valid configured-full distinction, no fan,
   unreadable/incomplete/invalid-limit fan, complete-plus-incomplete fan-set
   rejection, manual-enable failure, maximum-write failure, fatal maximum
   attempts for every discovered fan, independent cleanup, both signals,
   malformed/stale PID, verbose fields, RPM naming, and default error rate
   limiting.
2. Static checks for import safety, exact modes/paths, unconditional OpenRC
   install, intentional package release `2.0.0-1`, exact two-file package
   payload, `util-linux`, configurable args, logger directives,
   local-filesystem/soft-logger dependencies, PID-path separation,
   bounded/backed-off directives, and absence of alternate init
   artifacts/selectors/payloads.
3. Documentation review proving README onboarding is concise while retaining
   operator-action, safety, configuration, OpenRC, observability, and testing
   pointers; `SPEC.md` and `CONTEXT.md` retain exhaustive contract and
   implementation detail. Package descriptions, install instructions, and
   service comments must not contradict that ownership or the safety contract.
4. Complete diff review for unrelated edits, stale CPU/card0-only claims,
   secrets, shell portability, modes, and readability.

Checked-in source and test definitions must be labeled separately from
unavailable hardware, OpenRC, syslog, package, and service-runtime evidence. No
README example, source inspection, test-definition presence, or formatter run
proves runtime behavior. `dprint fmt --no-gitignore SPEC.md` is formatting only;
this file is not associated with ordinary Markdown by the current `dprint.json`.

## Decisions

- `DEC-001` (**superseded by `DEC-007`):** systemd and its unchanged unit were
  behavioral authority; OpenRC was the closest equivalent.
- `DEC-002` (retained): the daemon stays foreground and owns `/run/t2fand.pid`;
  supervisor state is separate and OpenRC `pidfile` is forbidden.
- `DEC-003` (**narrowed by `DEC-012`):** use `supervise-daemon`, all-exit
  respawn, a two-second delay, `retry="SIGTERM/5"`, and no background variables;
  explicit stop does not respawn. Unlimited respawn is superseded.
- `DEC-004` (**superseded by `DEC-008`):** `INIT_SYSTEM=auto` was the default
  and failed closed on ambiguous markers.
- `DEC-005` (**superseded by `DEC-009`):** package name was `t2fand-openrc` and
  both service definitions shipped.
- `DEC-006` (**superseded by `DEC-010`):** prior reconciliation treated the
  static OpenRC implementation as present and made no staged/package/runtime
  claim; its synchronization claim remains historical evidence.
- `DEC-007` (retained): OpenRC is the sole supported service manager; retained
  `t2fand.initd` is the sole service definition and payload; no systemd unit.
- `DEC-008` (retained): Make installation is unconditional OpenRC staging
  through `DESTDIR`, `BINDIR`, and `OPENRC_INITDDIR`, with no service actions.
- `DEC-009` (**narrowed by `DEC-013`):** retain package name `t2fand` and exact
  daemon/init payload; do not guess an OpenRC or syslog daemon dependency.
- `DEC-010` (retained): prior contract was static implementation truth; the
  recorder owns later `CONTEXT.md` synchronization and no runtime outcome was
  claimed.
- `DEC-011` (retained; checked-in source and fake-sysfs test definitions): every
  hwmon source participates in hottest-temperature selection; CPU is mandatory,
  GPU loss is an explicit recoverable topology state, and failure is represented
  as control mode rather than a sentinel.
- `DEC-012` (retained; checked-in init definition; OpenRC runtime unknown):
  bound OpenRC crash recovery at five respawns per 60 seconds, base delay two
  seconds, and two-second incremental backoff; retain foreground operation,
  daemon PID ownership, and explicit-stop suppression.
- `DEC-013` (retained; checked-in init/package definitions; logger delivery
  unknown): route streams through util-linux `/usr/bin/logger`, make
  `t2fand_args` configurable through `/etc/conf.d/t2fand`, and add the direct
  `util-linux` package dependency without selecting a syslog daemon.
- `DEC-014` (retained; checked-in source and fake-sysfs test definitions): CPU
  safety is channel-set based. One usable positive selected CPU channel is
  sufficient; non-positive siblings do not invalidate it, but any discovered
  sensor input or fault read/parse failure remains an immediate sensor
  fail-safe.
- `DEC-015` (settled; checked-in source and partial targeted fan test coverage;
  test execution unknown): fan safety is candidate-set based. Every discovered,
  deduplicated fan must have usable limits and control authority; one complete
  fan does not mask an incomplete candidate. Fatal handling attempts known
  maximums independently for all discovered fans before independent
  manual-mode and PID cleanup.

## Cumulative change history

| ID      | State/change                                                                                                                                                                                                                                                                      | Rationale and transition                                                                                                                                                                                          |
| ------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `H-001` | Superseded historical baseline: systemd was the only checked-in service integration; OpenRC metadata was contradictory and unsupported.                                                                                                                                           | Preserved historical local evidence.                                                                                                                                                                              |
| `H-002` | Superseded pre-implementation transition: 2026-08-27 reconciliation added OpenRC contract, Makefile selection/staging, and both package service definitions.                                                                                                                      | Preserved prior contract transition.                                                                                                                                                                              |
| `H-003` | Superseded dual-init implementation state: init script, selector Makefile, systemd unit, and both-definition package were present; systemd was authoritative.                                                                                                                     | Static inspection did not prove staged/package/OpenRC/hardware/runtime success.                                                                                                                                   |
| `H-004` | Superseded/current baseline: OpenRC-only support, retained init script, unconditional OpenRC install, and exact two-file payload.                                                                                                                                                 | This revision preserves the direction and adds the global fail-safe contract before implementation.                                                                                                               |
| `H-005` | Proposed pre-implementation transition: global hwmon hottest-source control, CPU-required safety, explicit modes, config fail-safe, cleanup hardening, verbose telemetry, fake tests, logger routing, configurable arguments, util-linux, and bounded OpenRC recovery.            | User-authorized revision; no shipped behavior or runtime result is claimed.                                                                                                                                       |
| `H-006` | Current checked-in implementation transition: daemon `main(argv=None)`, verbose output, signal-request cleanup, global thermal fail-safe source, OpenRC configurable arguments/logger/bounded recovery, util-linux package metadata, and fake-sysfs test definitions are present. | Source, service, package, and test definitions are evidence of checked-in content only; no runtime, hardware, service, package, staging, or syslog result is claimed.                                             |
| `H-007` | Current checked-in CPU-channel reconciliation: one usable positive selected CPU channel satisfies CPU availability; non-positive CPU siblings do not invalidate it, while any discovered sensor input or fault read/parse failure remains fail-safe.                              | Corrects the stricter non-positive-CPU statement retained as superseded `REQ-033`; source and test definitions are evidence only, with no runtime result claimed.                                                 |
| `H-008` | Contract reconciliation: fan control requires every discovered, resolved-path-deduplicated candidate to be complete and controllable; at least one complete fan is not sufficient when another candidate is incomplete.                                                           | Resolves the `REQ-038`/checked-in `discover_fans` mismatch with the smallest safety-preserving global rule; source enforcement and partial targeted fan coverage are present, exhaustive execution remains unverified. |
| `H-009` | Evidence correction: the `DEC-015` and `H-008` fan-coverage notes now record partial targeted coverage for incomplete fan sets and fatal cleanup attempts.                                                                                                                                        | Corrects stale “targeted test coverage is not present” wording without claiming test execution or complete coverage.                                                                                                  |
| `H-010` | Release/install reconciliation: the prior contract identified package release `1.2.0-3`; the current checked-in package metadata identifies intentional release `2.0.0-1`.                                                                                                                    | `PKGBUILD` verifies `pkgver=2.0.0` and `pkgrel=1`; the exact two-file OpenRC payload and `util-linux` dependency remain required.                                                                                       |
| `H-011` | Documentation ownership reconciliation: README is concise operator onboarding; exhaustive contract and implementation/design detail remain in `SPEC.md` and `CONTEXT.md`.                                                                                                                | Preserves the safety/product requirements while changing only detail placement; no shipped documentation or runtime outcome is claimed.                                                                                |

## Open questions and unknowns

| ID      | Question/status                                                                                                                                                                                       |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Q-001` | Exact T2 Mac models, kernels, and distributions supported: unknown.                                                                                                                                   |
| `Q-002` | Whether current hardware exposes all contracted hwmon/DRM paths: unknown; fake fixtures are required.                                                                                                 |
| `Q-003` | OpenRC support and definition location: OpenRC-only direction and the checked-in `t2fand.initd` definition are settled; directives/runtime remain unverified.                                         |
| `Q-004` | Exact remote Git revision/checksum: unknown; out of scope.                                                                                                                                            |
| `Q-005` | Valid numeric threshold ranges beyond finite `low_temp < high_temp`: unknown; no universal temperature range is invented.                                                                             |
| `Q-006` | Abrupt-failure hardware state: cleanup is best effort and outcome remains unknown.                                                                                                                    |
| `Q-007` | Live configuration reload: not supported; restart is required.                                                                                                                                        |
| `Q-008` | Authorized runtime fixture/hardware thresholds: no execution in this task; later project-native evidence required.                                                                                    |
| `Q-009` | Existing workflow release `*.zip` behavior: unknown; unrelated workflow remains unchanged.                                                                                                            |
| `Q-010` | Restore systemd: no; prohibited by OpenRC-only contract.                                                                                                                                              |
| `Q-011` | Pull-request `head_commit.message` behavior: unknown; existing workflow unchanged.                                                                                                                    |
| `Q-012` | Remote tag/release behavior: unknown and out of scope.                                                                                                                                                |
| `Q-013` | Old selector markers: superseded by unconditional OpenRC installation.                                                                                                                                |
| `Q-014` | OpenRC version support for local filesystem, soft logger, bounded respawn, and backoff directives: definitions are checked in; version/runtime support remains unknown and must not silently degrade. |
| `Q-015` | OpenRC lifecycle, explicit stop, bounded respawn, delay, and logger delivery on supported hosts: unknown.                                                                                             |
| `Q-016` | Arch OpenRC runtime provider: no hard OpenRC dependency is guessed; `util-linux` is explicitly required for logger.                                                                                   |
| `Q-017` | Exact package/staged result after the revised dependency and metadata: unknown until later checks.                                                                                                    |
| `Q-018` | Hardware cleanup after power loss, SIGKILL, kernel panic, native abort, or failed sysfs write: inherently not guaranteed; runtime result unknown.                                                     |
