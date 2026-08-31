# t2fand — Product Contract

## Contract status and document roles

This document is the contract truth for the local t2fand fork. `documented`
means supported by checked-in source, configuration, or test definitions; it
does not mean runtime-tested or shipped. This SPEC defines the checked-in
SMC/t2fand control-mode contract, including legacy-mode migration, passive SMC
monitoring, retained t2fand fail-high behavior, observability, CLI overrides,
conf.d payload, forwarding, benchmark prerequisite and formatting, and
packaging. The checked-in daemon, configuration-generation path, tests, operator
documentation, and CONTEXT record the global control-mode rename. Runtime,
hardware, service, package, staged-install, and test execution remain separate
and `unknown` until verified.

`SPEC.md` owns contract truth. The recorder synchronizes `CONTEXT.md` after
implementation. `README.md` is concise human onboarding; exhaustive contract and
implementation detail stays in `SPEC.md` and `CONTEXT.md`. `AGENTS.md` owns
onboarding, ownership, routing, safety, and protected-surface rules.

Correction status: `REQ-075`–`REQ-077`, `IF-031`–`IF-032`, `DEC-029`–`DEC-031`,
and `H-019` below are the authoritative checked-in correction. The global
control-mode rename in `REQ-078`–`REQ-080`, `IF-033`, `DEC-032`, and `H-020` is
authoritative checked-in contract and implementation evidence. The benchmark
prerequisite in `REQ-081`, `IF-034`, `DEC-033`, and `H-021` is also
authoritative checked-in contract and implementation evidence. The checked-in
daemon, configuration-generation path, benchmark, tests, operator documentation,
and CONTEXT use the renamed global tokens, corrected conf.d contract, and
benchmark prerequisite; these checked-in definitions do not claim shipped
release, runtime, hardware, service, package, staged installation, or
test-execution success.

## Problem and goals

`t2fand` is a Python daemon for fan monitoring and optional daemon-owned
fan-speed control on Macs with an Apple T2 chip running Linux. It must consider
every exposed Linux hwmon temperature, select SMC only for newly generated
configs, retain t2fand fail-high control, and remain one supported OpenRC
service.

Goals:

- retain Python, the extensionless `t2fand` executable, and its installed path;
- keep one-second sampling, at most five valid normal samples, fractional
  Celsius, and the existing linear, cubic exponential, and logarithmic curves;
- rediscover and reopen sysfs paths every cycle; never retain open sysfs
  handles;
- make CPU input mandatory for t2fand control while treating GPU input as
  optional with explicit missing/recovery transitions in both modes;
- make control-mode, configuration, sensor, and fan-control failure behavior
  explicit;
- provide flushed direct output, compact per-cycle telemetry, and full `-v`
  telemetry;
- keep OpenRC as the only supported service manager and retain the daemon/init
  service boundary while adding the declared conf.d payload;
- add bounded, backed-off OpenRC crash recovery and util-linux logger routing;
- expose validated runtime path and recovery-policy overrides;
- timestamp t2fanbench messages with local wall-clock time;
- maintain fake-fixture tests and updated operator documentation for the
  revision.

## Users, scope, and non-goals

| Role                      | Need                                                        | Status                                        |
| ------------------------- | ----------------------------------------------------------- | --------------------------------------------- |
| Linux user of a T2 Mac    | SMC fan monitoring or t2fand temperature-driven fan control | unreleased contract; hardware outcome unknown |
| Root/system administrator | Configure and operate the OpenRC service                    | checked-in workflow; execution unknown        |
| Arch package consumer     | Install the daemon and OpenRC definition                    | checked-in package definition; build unknown  |
| Maintainer                | Test, package, and document the revision                    | checked-in definitions; execution unknown     |

In scope: the Python daemon, global hwmon discovery, configuration and fail-safe
behavior, direct output, compact and verbose telemetry, validated CLI overrides,
best-effort cleanup, `t2fand.initd`, `t2fand.confd`, unconditional OpenRC
installation, Arch metadata, benchmark output, a standard library `unittest`
suite, a project-native test target, and affected documentation and package
descriptions.

Out of scope: alternate init systems, service selectors, systemd artifacts,
package rename beyond the declared conf.d addition, GUI, network API/dependency,
adaptive scheduling, persistent sysfs handles, Rust implementation, remote
maintenance, secrets, unrelated files, a 250 RPM/s ramp-down, a ramp limit, PID
control, arbitrary smoothing or hysteresis, automatic SMC-to-t2fand fallback,
ML, external work, and a package/version decision unless necessary.

## Terminology

| Term                | Definition                                                                                                                                                                                                      |
| ------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| valid temperature   | One successful, non-faulted hwmon input parse; zero/ambient values are valid for non-CPU sensors, while non-positive CPU readings do not satisfy t2fand-mode CPU availability                                   |
| required CPU        | The discovered CPU/coretemp channel set required for t2fand control; at least one selected channel must be usable and positive, while sibling non-positive readings do not invalidate it                        |
| GPU-missing         | No temperature input below any exact numeric DRM card is present in the current topology                                                                                                                        |
| control temperature | Highest valid temperature in the current cycle                                                                                                                                                                  |
| sensor fail-safe    | T2fand-mode state that bypasses smoothing and attempts maximum fan speed because required thermal input is unsafe                                                                                               |
| config-failsafe     | T2fand-mode state that bypasses curves and attempts maximum fan speed because a detected FanN policy is invalid; INI load, read, and parse failures are startup errors, not this state                          |
| control-error       | Fatal loss of required control authority, including failed SMC ownership-loss escalation                                                                                                                        |
| target RPM          | In t2fand mode, requested fan output after policy and clamping; in SMC mode, the observed current `fan*_output` value. It is `unknown` only when the read fails, and in SMC it is not a userspace curve target. |
| actual RPM          | One diagnostic tachometer read, or `unknown` when it cannot be read or parsed                                                                                                                                   |
| SMC mode            | Monitoring mode in which Apple SMC owns the fans, fan manual control is released (`fan*_manual=0`), and normal fan output is not commanded                                                                      |
| t2fand mode         | Global curve-control mode in which the daemon owns fan control and applies FanN policies; this is the only current control mode besides SMC                                                                     |
| legacy manual mode  | Historical name for the former global curve-control mode; `manual` is not a valid current `[General] control_mode` value                                                                                        |
| ownership loss      | SMC inability to verify or maintain a discovered fan's `fan*_manual=0` state                                                                                                                                    |
| daemon PID          | PID written by t2fand to `/run/t2fand.pid`; supervisor state is separate                                                                                                                                        |

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
| `REQ-024` | `make install` is unconditional OpenRC installation, honors `DESTDIR`, `BINDIR=/usr/bin`, `OPENRC_INITDDIR=/etc/init.d`, performs no compilation, and installs only daemon 0700/init 0755.                                                                                                                                                                                                                                                                    | superseded by `REQ-075`; historical two-file install evidence only          |
| `REQ-025` | Package name is `t2fand`; package payload is daemon 0700 and OpenRC init 0755; no systemd payload or guessed OpenRC dependency.                                                                                                                                                                                                                                                                                                                               | superseded/narrowed by `REQ-050`; payload portion superseded by `REQ-069`   |
| `REQ-026` | OpenRC runs the foreground daemon, daemon owns `/run/t2fand.pid`, and every exit respawns unlimited after exactly two seconds; explicit stop suppresses respawn.                                                                                                                                                                                                                                                                                              | superseded by bounded `REQ-043`; retained PID/foreground portions           |
| `REQ-027` | No OpenRC pidfile/backgrounding/network dependency; installation performs no service state changes.                                                                                                                                                                                                                                                                                                                                                           | retained by `REQ-043`, `REQ-044`                                            |
| `REQ-028` | Supported operator workflow is OpenRC `rc-service` with optional `rc-update`; direct Python execution is not a second manager workflow.                                                                                                                                                                                                                                                                                                                       | retained by `REQ-043`                                                       |
| `REQ-033` | CPU remains mandatory: no usable CPU reading, non-positive CPU reading, malformed CPU data, or inaccessible required CPU input enters sensor fail-safe immediately. At least one usable system temperature is required. Valid non-CPU low/ambient readings are accepted. Any discovered non-CPU read/parse/fault failure enters sensor fail-safe for that cycle; an absent source is not itself a fault. Select the highest valid reading across all sources. | superseded by `REQ-048`; stricter non-positive-CPU rule retained as history |

### Revised requirements

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | Acceptance evidence                                                                                                   |
| --------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------- |
| `REQ-029` | Keep root-required, foreground, single-process Python execution. Put orchestration in import-safe `main(argv=None)` under the normal main guard. Importing for tests must not exit, check root, install signals, touch real sysfs, `/etc`, or `/run`. Use snake_case names, named state/config objects, focused discovery/parse/select/control/telemetry/cleanup functions, precise exceptions, module and useful API docstrings.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in source; runtime unverified                                                                                 |
| `REQ-030` | Preserve one-second sampling, at most five valid normal samples, fractional Celsius, existing curves, ordinary smoothing, and immediate maximum on any fail-safe or valid configured full speed. Re-scan and reopen sysfs paths each cycle; retain no open sysfs handles.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                 | checked-in source and test definitions; execution unverified                                                          |
| `REQ-031` | Each cycle enumerate `/sys/class/hwmon/hwmon*/temp*_input`, existing CPU/coretemp paths, and `device/hwmon/hwmon*/temp*_input` below every DRM entry whose basename exactly matches `^card\d+$`. Exclude connector names such as `card0-DP-1`. Union candidates and deduplicate by resolved path.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in source and fake-sysfs test definitions; runtime unknown                                                    |
| `REQ-032` | Read each selected input exactly once per cycle and parse signed integer millidegrees Celsius. Read optional `name`, `tempN_label`, DRM identity, and path fallback to derive a stable human label. Optional labels never gate operation. A present fault flag reporting a fault makes that sensor unavailable for the cycle. No `-1`, fabricated high value, or other numeric sentinel represents failure; failed readings are `unknown`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                | checked-in source and fake-sysfs test definitions; execution unverified                                               |
| `REQ-034` | GPU is optional. GPU sensors are those resolved below exact numeric DRM cards. If none are present, continue with other valid sources and emit one warning on transition into `gpu-missing`; emit one recovery notice when GPU temperatures reappear. Do not repeat unchanged warnings every second; verbose telemetry continues to show `gpu_temps=missing`. Sensors/cards may appear or disappear across cycles.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | checked-in source and topology test definitions; execution unverified                                                 |
| `REQ-035` | Externally report at least these modes: `curve`, `configured-full`, `config-failsafe`, `sensor-failsafe`, `control-error`, and `shutting-down`. `curve` is valid automatic policy; `configured-full` is valid `always_full_speed=true`; fail-safe modes command maximum; `control-error` is fatal; shutdown is the common cleanup state. State and reason transitions are reported.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | checked-in source and test definitions; execution unverified                                                          |
| `REQ-036` | Sensor/config fail-safe bypasses smoothing and immediately attempts every fan's known maximum. Sensor fail-safe stays alive and retries discovery once per second while control remains available. Return to normal policy only after five consecutive cycles in which all required inputs are valid; reset the count on any invalid cycle, clear old history, then collect the five new maxima before normal smoothing. Configuration is read once at startup; config-failsafe persists until restart after repair.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in source and recovery test definitions; execution unverified                                                 |
| `REQ-037` | Configuration keeps four options and generated defaults: `low_temp=55`, `high_temp=75`, `speed_curve=linear`, `always_full_speed=false`. Validate every detected fan before normal curves. Reject missing sections/options, unreadable or malformed INI, malformed/non-finite thresholds, invalid curves, `low_temp >= high_temp`, and Boolean text other than case-insensitive `true`/`false` after INI whitespace handling. Any defect globally selects config-failsafe, commands every fan maximum, prints the exact section/key or file problem, and never silently edits/normalizes administrator config. A valid `true` selects `configured-full`, not an error. Config-generation failure takes the same safe path when maxima are available.                                                                                                                                                                                                                                                                                                                                                                                                                                                      | superseded by `REQ-067`; prior config-failsafe semantics retained as historical evidence                              |
| `REQ-038` | Require at least one complete controllable fan. Read usable integer min/max limits, require a usable maximum, clamp every requested output to the reported range, enable hardware manual control before normal control, and write outputs by reopening sysfs paths. No fan, unreadable maximum, inability to enable hardware manual control, inability to write maximum, or equivalent loss of control authority is fatal. Before fatal exit, attempt maximum on every still-controllable fan, perform cleanup, and exit nonzero for OpenRC recovery.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                     | superseded by `REQ-049`; retained historical evidence                                                                 |
| `REQ-039` | Preserve threshold behavior: at/below low uses minimum, at/above high uses maximum, and intermediate values use the existing linear, cubic `exponential`, or `math.log` `logarithmic` expressions. Validate or guard calculations so they cannot raise or produce non-finite control output; unsafe policy follows config-failsafe. `always_full_speed=true` takes precedence.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | checked-in source and curve test definitions; execution unverified                                                    |
| `REQ-040` | Use `argparse` with `-v`/`--verbose`; unknown arguments fail clearly before hardware mutation. Use direct `print()` output, explicit stdout/stderr, formatted strings, and `flush=True`; do not use Python logging, direct syslog APIs, or spawn logger from Python. Default output includes startup/shutdown summaries, warnings/errors, fail-safe, GPU-missing, and recovery transitions, plus the compact per-cycle record defined by `REQ-068`. Verbose output emits the full flushed record defined by `REQ-068` once per second.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | checked-in source and CLI/output test definitions; execution unverified                                               |
| `REQ-041` | Every verbose record includes every discovered sensor label and value or `unknown`, `gpu_temps=missing` when applicable, highest current valid temperature, rolling mean only during normal smoothing, mode/status/reason, and each fan's low/high, curve, configured full-speed value, `target_rpm`, and `actual_rpm` or `unknown`. Actual RPM is diagnostic. In t2fand mode, a failed read never suppresses the target and forces all controllable fans maximum for safety; in SMC mode it only degrades monitoring as specified by `REQ-062`. Repeated default errors print on state/reason change and at most once per 60-second reminder interval.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | implementation target; execution unverified                                                                           |
| `REQ-042` | SIGINT/SIGTERM handlers only request shutdown; they perform no file I/O. After t2fand control begins, one outer `try/finally` owns cleanup. Fatal paths independently attempt maximum for every fan first, independently disable hardware manual control for every fan next, and always attempt PID removal. Preserve and print the original failure and cleanup failures; fatal exit is nonzero. Cleanup is best effort and cannot run after SIGKILL, power loss, kernel panic, interpreter/native abort, or unavailable hardware write authority. Malformed PID files produce a clear diagnostic and safe stale-file recovery, not an unhandled parse exception.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | implementation target; execution unverified                                                                           |
| `REQ-043` | OpenRC remains sole supported manager and `t2fand.initd` sole service artifact. It runs `/usr/bin/t2fand` foreground through `supervise-daemon`, does not set `pidfile`, background, daemonization, or network dependencies, and keeps daemon ownership of `/run/t2fand.pid`. Use normal local-filesystem dependency ordering and soft `logger` use. Preserve a two-second base respawn delay, but bound crash loops to five respawns in a 60-second window and use a two-second respawn-delay step for backoff. Every child exit is eligible within that bound; explicit `rc-service ... stop` suppresses respawn. Selected directives and their supported OpenRC semantics must be documented and statically checked.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                   | checked-in init definition and static test definitions; OpenRC runtime unknown                                        |
| `REQ-044` | Route OpenRC stdout through `output_logger="/usr/bin/logger -t t2fand -p daemon.info"` and stderr through `error_logger="/usr/bin/logger -t t2fand -p daemon.err"`. Make daemon arguments configurable without editing the init script: source normal `/etc/conf.d/t2fand` value `t2fand_args` into `command_args`, default empty, so `t2fand_args="--verbose"` is supported. Add direct `util-linux` runtime dependency. Do not require a particular syslog daemon; logger submits to the administrator-selected receiver.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | checked-in init/package definitions and static test definitions; logger delivery unknown                              |
| `REQ-045` | Prior install/package contract: keep `make install` unconditional OpenRC-only, with no compilation or service action, honor `DESTDIR`, overridable `BINDIR` default `/usr/bin`, and `OPENRC_INITDDIR` default `/etc/init.d`; install only daemon 0700 and init script 0755. Keep package name `t2fand`, retain `linux-t2`, `python`, and `git`, add `util-linux`, and package exactly `/usr/bin/t2fand` and `/etc/init.d/t2fand`; the prior release was `1.2.0-3`. No alternate artifact or payload is allowed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | superseded by `REQ-050`; historical release/install contract retained                                                 |
| `REQ-046` | Add a standard-library `unittest` suite using temporary fake sysfs/config/run trees and mocks. Add and document project-native `make test`; tests require neither root, real `/sys`, fan hardware, OpenRC, nor a syslog daemon.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | checked-in test source and target; `make test` outcome unverified (not run)                                           |
| `REQ-047` | Prior documentation-placement contract: rewrite affected operator documentation to place the full safety, discovery, smoothing, configuration, fail-safe, mode, telemetry, OpenRC, logger, cleanup, testing, and cautious manual-check contract in the README. Never instruct deletion of live sysfs nodes or obstruction of real cooling sensors. Remove stale CPU/card0-only or unsupported-manager claims from current docs.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | superseded by `REQ-051`; historical documentation requirement retained                                                |
| `REQ-048` | CPU remains mandatory, but CPU availability is satisfied when at least one selected CPU/coretemp channel is successfully read, fault-free, parsed, and positive. A non-positive CPU reading is a valid reading that does not satisfy availability; it does not invalidate a positive sibling channel. If no selected CPU channel is usable and positive, enter sensor fail-safe immediately. Any discovered selected sensor input read/parse/fault failure, including a CPU channel, enters sensor fail-safe for that cycle even when another CPU channel is positive. At least one usable system temperature is required. Valid non-CPU low/ambient readings are accepted; an absent source is not itself a fault. Select the highest valid reading across all sources, with failures `unknown` and no fabricated temperatures or numeric sentinels.                                                                                                                                                                                                                                                                                                                                                     | checked-in source and fake-sysfs test definitions; execution unverified                                               |
| `REQ-049` | Require at least one discovered fan and require every discovered, resolved-path-deduplicated fan candidate to be complete and controllable. The discovered set is the union of T2 and class-hwmon fan candidates, deduplicated by resolved base path; one complete fan does not mask another candidate with an unreadable/incomplete limit or invalid range. Each candidate must provide usable integer minimum and maximum limits with minimum no greater than maximum. No fan, any unreadable fan maximum, any incomplete/invalid discovered fan, inability to enable manual mode, inability to write a required maximum, or equivalent loss of control authority is fatal `control-error`; no candidate may be silently ignored or used as an alternate. Clamp each requested output to that fan's reported range and reopen sysfs paths for operations. For every fatal-control path, independently attempt each discovered fan's known maximum, record a missing maximum as a failed attempt, continue after per-fan failures, then independently attempt manual-mode disable for each fan and attempt PID removal; preserve the original and cleanup failures and exit nonzero for OpenRC recovery. | historical fan-candidate source; source-selection portion superseded by `REQ-052`; safety portions retained           |
| `REQ-050` | Keep `make install` unconditional OpenRC-only, with no compilation or service action, honor `DESTDIR`, overridable `BINDIR` default `/usr/bin`, and `OPENRC_INITDDIR` default `/etc/init.d`; install exactly daemon `/usr/bin/t2fand` mode 0700 and init script `/etc/init.d/t2fand` mode 0755. Keep package name `t2fand`, Arch `x86_64` and GPL3 metadata, release `2.0.0-1` (`pkgver=2.0.0`, `pkgrel=1`), dependencies `linux-t2`, `python`, and `util-linux`, and `git` as a build dependency. Package exactly those two files; no alternate artifact, service definition, selector, or payload is allowed.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                           | historical install/release baseline; exact two-file installation and package/release portions superseded by `REQ-075` |
| `REQ-051` | Keep README as concise operator onboarding. It must retain pointers for operator actions, safety, configuration, OpenRC operation, observability, and project-native testing, while exhaustive limits, implementation behavior, fail-safe semantics, modes, telemetry fields, and design truth remain owned by `SPEC.md` and `CONTEXT.md`. Summaries must not weaken or redefine the safety/product requirements in this contract, and documentation must not instruct deletion of live sysfs nodes, obstruction of cooling sensors, or unsupported service-manager workflows.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | documentation review remains required; current conformance and runtime outcomes unverified                            |
| `REQ-052` | Discover fan candidates only from the T2 layout below `devices/*/*/*/*/APP0001:00/fan*`; do not union class-hwmon fan candidates. Expand matched fan directories to `fan*_input`, resolve and deduplicate fan base paths, require every discovered candidate to have usable integer minimum/maximum limits with minimum no greater than maximum, and retain the fatal all-candidate control-authority and independent cleanup rules of `REQ-049`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in `t2fand` source; execution and hardware outcomes unverified                                                |
| `REQ-053` | Read `/kernel/debug/vgaswitcheroo/switch` when available and recognize a `DIS` entry whose power state is `Off`; for its reported PCI address, skip only temperature candidates whose resolved path contains that address. Do not disable general hwmon or DRM discovery when the switch file is absent/unreadable, and retain failed readings as `unknown` under the normal sensor fail-safe rules.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in `t2fand` source; hardware topology and runtime outcomes unverified                                         |
| `REQ-054` | Keep local-source Arch packaging: `PKGBUILD` sources the checked-in `t2fand`, `t2fand.initd`, and `Makefile`, and its `package()` delegates staging to `make DESTDIR="$pkgdir" install`. The Makefile remains unconditional OpenRC-only, performs no compilation or service action, honors `DESTDIR`, overridable `BINDIR` default `/usr/bin`, and `OPENRC_INITDDIR` default `/etc/init.d`, and installs exactly the daemon mode 0700 and init script mode 0755.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | superseded by `REQ-075`; historical two-file packaging evidence only                                                  |
| `REQ-055` | README/operator documentation identifies the Artix Linux and OpenRC package workflow, local checkout installation/staging, exact installed paths and modes, optional service enablement, configuration, safety, logging, and project-native testing without replacing the exhaustive contract owned by `SPEC.md`.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in README; documentation review and operator outcomes unverified                                              |
| `REQ-056` | `opencode.json` is not a product, daemon, package, or release input. The local file is ignored by `.gitignore` and must not be shipped or used to define the t2fand contract; removal from ignored local state is outside this SPEC-only edit.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | checked-in `.gitignore`, `PKGBUILD`, and Makefile; repository tracking state is unverified                            |
| `REQ-057` | Ignore generated build and release artifacts, including Arch package/source staging paths, Python build/distribution paths, archives, logs, signatures, and zip outputs, through the checked-in `.gitignore`; ignored artifacts are not product payload or contract evidence.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                             | checked-in `.gitignore`; artifact-generation outcome unverified                                                       |
| `REQ-058` | Set the Arch package release to `2.0.1-1` (`pkgver=2.0.1`, `pkgrel=1`) while retaining package name `t2fand`, Arch `x86_64`, GPL3 metadata, dependencies `linux-t2`, `python`, `util-linux`, build dependency `git`, and the exact two-file OpenRC payload.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               | superseded by `REQ-075`; historical `2.0.1-1` release/two-file evidence only                                          |

### Current global control-mode requirements

These requirements define the checked-in global rename. They supersede the
historical control-mode rows `REQ-059`–`REQ-067` below. `manual` remains valid
only in retained historical evidence and for the hardware `fan*_manual` sysfs
terminology; it is not a current global configuration token.

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Acceptance evidence                                                                                                                    |
| --------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------------------- |
| `REQ-078` | Configuration has one global `[General]` section when a config is generated or explicitly supplies global control. The only valid global `control_mode` values are exactly `smc` and `t2fand`. `manual`, `auto`, `smc_auto`, and any other alias or value are invalid and produce a pre-control startup error with no automatic fallback. A generated/default config uses `smc`. An existing config without `[General]` infers `t2fand`, emits exactly one warning for that startup, and is never rewritten. | checked-in daemon/configuration-generation source and unittest definitions; runtime, config execution, and test execution unknown      |
| `REQ-079` | In `smc`, Apple SMC owns the fans: the daemon observes fan and sensor state, releases and maintains `fan*_manual=0`, and does not ordinarily apply FanN policies or write `fan*_output`. In `t2fand`, the daemon owns fan control and applies FanN policies, including the existing curve, configured-full, config-failsafe, sensor-failsafe, and control-error behavior. Hardware `fan*_manual` naming and `smc-auto`/`smc-degraded` statuses are unchanged.                                                | checked-in daemon source, README, CONTEXT, and unittest definitions; runtime, hardware, and test execution unknown                     |
| `REQ-080` | The checked-in implementation synchronizes the global rename across runtime parsing/state, generated and documented configuration, operator documentation, contract/context records, and tests. No current surface may present `manual` as an accepted global value or define `auto`/`smc_auto` as a mode. Historical references must be explicitly labeled historical and must not be used as acceptance evidence for current configuration.                                                                | checked-in daemon/configuration-generation source, README, SPEC, CONTEXT, and unittest definitions; runtime and test execution unknown |

### Benchmark prerequisite requirement

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Acceptance evidence                                                                                        |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `REQ-081` | Before any benchmark side effect, `t2fanbench.py` must use the standard-library `shutil.which("stress-ng")` PATH lookup. The lookup must precede cache-directory creation, benchmark or logger output, baseline sleep, and every subprocess launch. If unavailable, write exactly `error: stress-ng is required but was not found in PATH` to stderr, return exit status `1`, and produce no traceback, installation attempt, logger invocation, benchmark output, sleep, or subprocess launch. If available, retain the existing benchmark sequence, local English timestamps, logger side effect, and unchanged `stress-ng` child output. Do not expand the contract to install `stress-ng`, alter logger behavior, or interpret/expand nonzero `stress-ng` results. | checked-in benchmark source and behavior-focused fake test definitions; runtime and test execution unknown |

### Historical control-mode requirements

The following rows are retained historical evidence of the superseded SMC/manual
contract. They supersede the mode-independent fail-high and verbose-only
assumptions in `REQ-030`, `REQ-036`–`REQ-042`, and `REQ-048`; those rows remain
retained historical evidence. They are not current configuration requirements.

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                    | Acceptance evidence                                                        |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------- |
| `REQ-059` | Historical configuration contract: one global `[General]` section with `control_mode` set to exactly `smc` or `manual`; generated files used `smc`, and an existing file without `[General]` inferred `manual` with one warning and no rewrite. A missing, invalid, or unreadable mode selection was reported before hardware mutation; no automatic SMC-to-manual fallback was allowed.                                                                                                                                                                                                                                                                                                                                                                       | historical fake-sysfs/config evidence; superseded by `REQ-078`             |
| `REQ-060` | Historical mode-resolution contract: resolve the global mode before fan-policy behavior; SMC ignored FanN defects, while global `manual` retained FanN validation, `config-failsafe`, and configuration immutability.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                          | historical mode/config evidence; superseded by `REQ-079`                   |
| `REQ-061` | In `smc`, release every discovered fan by writing `fan*_manual=0`, verify the resulting state, and re-verify/maintain `fan*_manual=0` during operation. SMC normally never writes `fan*_output`; a maximum write is permitted only for ownership-loss escalation. If release or verification cannot be completed, first attempt `fan*_manual=0`; if that fails, attempt each known maximum independently, report cleanup failures, enter fatal `control-error`, and exit nonzero.                                                                                                                                                                                                                                                                              | fake-sysfs ownership tests; execution unverified                           |
| `REQ-062` | In `smc`, monitor without takeover: rediscover/read sensors and fan telemetry each one-second cycle, retain failed readings as `unknown`, and continue monitoring when any thermal or tachometer sensor fails. Sensor failure does not enter sensor-failsafe, write `fan*_output`, enable manual mode, or otherwise take over. Preserve global hwmon discovery, exact numeric DRM-card discovery, T2-only fan discovery, and powered-off dGPU filtering.                                                                                                                                                                                                                                                                                                       | fake-sysfs monitoring/failure/topology tests; execution unverified         |
| `REQ-063` | In `manual`, preserve the existing curve formulas, one-second sampling, five-sample smoothing/recovery, manual enable, fail-high sensor/config behavior, actual-RPM fail-high behavior, output clamping, and fatal maximum-control handling. Clean shutdown attempts `fan*_manual=0` independently for every fan. SMC does not enable manual mode or use manual-mode curves.                                                                                                                                                                                                                                                                                                                                                                                   | fake-sysfs manual-regression tests; execution unverified                   |
| `REQ-064` | In `smc`, default output emits one flushed compact telemetry record per second. Each record contains all discovered sensor labels with values or `unknown`, highest temperature or `unknown`, dGPU/topology state including powered-off filtering, every fan's `manual` state, `target_rpm`, and `actual_rpm` or `unknown`. SMC `target_rpm` is the observed current `fan*_output` value; it is `unknown` only when reading that output fails, and it is not a userspace curve target. Manual mode retains one-second telemetry only under `--verbose` and includes the existing manual policy/target fields.                                                                                                                                                  | superseded by `REQ-068`; historical evidence only                          |
| `REQ-065` | Add fake-sysfs-testable coverage for generated SMC configuration, legacy-manual inference warning, both modes' fan-manual transitions, SMC no-output behavior, SMC sensor degradation without takeover, ownership-loss escalation, clean shutdown release, telemetry fields/default cadence, manual fail-high regression, T2-only fan discovery, and powered-off dGPU filtering.                                                                                                                                                                                                                                                                                                                                                                               | standard-library unittest definitions; execution unverified                |
| `REQ-066` | Historical mode-reporting contract: report the selected global mode as `smc` or `manual` and preserve the former manual submodes (`curve`, `configured-full`, `config-failsafe`, `sensor-failsafe`, `control-error`, and `shutting-down`) only where applicable. SMC sensor degradation was not `sensor-failsafe`; SMC ownership-loss failure was fatal `control-error`.                                                                                                                                                                                                                                                                                                                                                                                       | historical mode-state evidence; superseded by `REQ-078`–`REQ-079`          |
| `REQ-067` | Configuration outcome is mode-independent at startup and mode-specific for FanN policy defects. Failure to generate an absent config, or failure to read or parse an existing INI, is reported as `StartupError` before fan control or fan mutation; it does not command maxima or enter `config-failsafe`, and an existing administrator file is not silently edited or normalized. A parseable invalid `[General].control_mode` is likewise a pre-control startup error with no automatic SMC-to-manual fallback. A malformed or otherwise invalid FanN policy remains a global persistent `config-failsafe` that commands every known maximum in manual mode, while SMC emits a dormant warning and neither enters `config-failsafe` nor writes fan output. | checked-in source and configuration test definitions; execution unverified |

### Checked-in observability, override, benchmark, and payload requirements

These stable requirements record the user-authorized transition now present in
checked-in source and project files. `REQ-069` and `REQ-072` retain the prior
seven-default and six-forwarding payload as historical requirements; those
semantics are superseded by `REQ-075` and `REQ-076`. The other current rows
supersede only the conflicting portions named in each row; unchanged prior
requirements remain applicable. Runtime, hardware, service, package,
staged-install, and test execution remain unverified.

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                      | Acceptance evidence                                                                                                        |
| --------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| `REQ-068` | Emit exactly one flushed telemetry record per one-second control cycle in both `t2fand` and `smc`. Without `-v`/`--verbose`, the record is compact and contains only the hottest eligible sensor identity as `highest=<sensor-label>`, its numeric value as `highest_temp=<value>`, and `actual_rpm` for every discovered fan. With `-v`/`--verbose`, emit the existing full telemetry record in both modes, retaining its complete sensor, topology, state, reason, policy, target, and actual-RPM fields but using the distinct `highest` and `highest_temp` meanings. No mode, including `smc`, implies verbose output. Faulted, unavailable, and skipped sensors cannot be hottest; no valid hottest sensor and unavailable RPM values use the established `unknown` representation. Equal valid maxima select the first reading in existing discovery order. Warnings, transitions, degraded reminders, and errors are independent of telemetry verbosity. This supersedes the default-cadence, verbose-only, and highest-field-semantics portions of `REQ-040`, `REQ-041`, and `REQ-064`.                                  | checked-in daemon source and telemetry test definitions; runtime and test execution unknown                                |
| `REQ-069` | Historical superseded requirement: add `t2fand.confd` as a packaged `/etc/conf.d/t2fand` file with mode `0644`. Its active defaults were `t2fand_config_path="/etc/t2fand.conf"`, `t2fand_pid_path="/run/t2fand.pid"`, `t2fand_sysfs_path="/sys"`, `t2fand_sensor_recovery_cycles="5"`, `t2fand_sample_limit="5"`, `t2fand_error_reminder_seconds="60"`, and `t2fand_args=""`; concise comments explained each setting and optional arguments such as `--verbose`. It added `OPENRC_CONFDIR` with default `/etc/conf.d` to `make install`, staged this file without starting or enabling services, added it to local `PKGBUILD` sources and `backup=()`, and preserved administrator changes. The package payload was exactly daemon `/usr/bin/t2fand` mode `0700`, init `/etc/init.d/t2fand` mode `0755`, and conf.d `/etc/conf.d/t2fand` mode `0644`; package identity and metadata were retained at release `2.0.1-2`. This superseded the exact-two-file and non-payload conf.d portions of `REQ-050`, `REQ-054`, `REQ-058`, `IF-015`, `IF-018`, and `IF-020`; its seven active conf.d defaults are superseded by `REQ-075`. | historical checked-in transition; conf.d semantics superseded by `REQ-075`; staging, package, and runtime outcomes unknown |
| `REQ-070` | Make every message printed by `t2fanbench.py`'s `log()` use exactly `MMM DD HH:mm:ss [t2fanbench] MESSAGE`, with local wall-clock time, English three-letter month names independent of process locale, zero-padded day/time fields, no leading blank line or `===` decoration, and flushed output. Preserve the existing `logger` side effect and do not alter `stress-ng` child output.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                        | checked-in benchmark source and static test definition; runtime unverified                                                 |
| `REQ-071` | Keep `-v`/`--verbose` and add `-c`/`--config-path` (filesystem path, default `/etc/t2fand.conf`), `-p`/`--pid-path` (filesystem path, default `/run/t2fand.pid`), `-s`/`--sysfs-path` (filesystem path, default `/sys`), `-r`/`--sensor-recovery-cycles` (positive integer, default `5`), `-l`/`--sample-limit` (positive integer, default `5`), and `-e`/`--error-reminder-seconds` (positive finite float, default `60.0`). Help shows defaults and concise semantics. Argparse rejects zero, negative, nonnumeric, NaN, and infinite numeric values before root checks or filesystem mutation; unknown arguments retain the same ordering guarantee. Path values reach the existing config, PID, fan-discovery, and sensor-discovery helpers; policy values reach runtime state/functions without mutating module globals; the parsed PID path is used for cleanup on every exit path. Import-safe `main(argv=None)` remains required.                                                                                                                                                                                        | checked-in source and CLI/wiring/failure-order test definitions; runtime unverified                                        |
| `REQ-072` | Historical superseded requirement: on every OpenRC start, forward conf.d values through their corresponding long options in this order: `--config-path`, `--pid-path`, `--sysfs-path`, `--sensor-recovery-cycles`, `--sample-limit`, and `--error-reminder-seconds`; append `t2fand_args` last. Empty `t2fand_args` was valid; nonempty values, including `--verbose`, retained final repeated-option behavior under argparse. It kept daemon ownership of the PID lifecycle and did not add an OpenRC `pidfile`. It used the established OpenRC `command_args` mechanism and tested its exact generated argument string. Safe whitespace quoting for that mechanism was not established, so conf.d path values could not contain whitespace; this limitation was to be documented rather than claiming unsupported quoting. Its six-option forwarding semantics are superseded by `REQ-076`.                                                                                                                                                                                                                                    | historical checked-in transition; forwarding semantics superseded by `REQ-076`; OpenRC runtime and execution unknown       |
| `REQ-073` | Extend the standard-library fake-sysfs/config/run-tree test contract to cover compact default telemetry in both modes, full telemetry only with `-v`, deterministic hottest-sensor selection and `unknown` cases, all option defaults and consumers, pre-mutation numeric validation, custom path/PID cleanup, non-global recovery settings, three-file staging and modes, package source/backup preservation, exact optional `t2fand_args` forwarding with absent/empty/nonempty arguments, benchmark formatting under a non-English locale without real sleeping or stress execution, and regression coverage for warnings, rate limiting, fail-safe behavior, signals, and daemon-owned PID state. Test execution remains unverified.                                                                                                                                                                                                                                                                                                                                                                                         | checked-in unittest/static definitions; execution unverified                                                               |
| `REQ-074` | Affected operator-facing documentation is updated together: README onboarding covers compact/default versus verbose telemetry, all new CLI options and defaults, `/etc/conf.d/t2fand`, package installation and administrator overrides, and benchmark timestamp format; `t2fand.confd` carries concise setting comments; CLI help exposes the same option contract. Documentation remains subordinate to this SPEC and must not claim unsupported quoting, service actions, runtime, or package outcomes.                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                       | checked-in README, conf.d, and CLI-source definitions; documentation/runtime outcomes unverified                           |

### Correction requirements

These stable requirements are the authoritative checked-in correction to the
conf.d and OpenRC forwarding portions of historical `REQ-069`, `REQ-072`,
`REQ-073`, and `REQ-074`. They do not change the daemon CLI contract in
`REQ-071`/`DEC-025`.

ID reconciliation: the correction request names `REQ-070` and `DEC-025` as
conflicting conf.d/forwarding requirements. In the checked-in SPEC, `REQ-070` is
benchmark formatting and `DEC-025` is the retained six-option daemon CLI
contract; neither requires seven conf.d assignments. The actual conflicting
checked-in IDs are `REQ-069`, `REQ-072`, `IF-028`, `IF-029`, `DEC-026`, and the
conf.d/forwarding portion of `H-018`. This request/reference mismatch remains
unresolved; the requested correction is applied to the actual conflicts.

| ID        | Requirement                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                  | Acceptance evidence                                                                                                       |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- |
| `REQ-075` | Ship `/etc/conf.d/t2fand` with exactly one active assignment, `t2fand_args=""`; no removed `t2fand_*` default may remain active or commented. Comments may state that `t2fand` owns defaults, optional overrides pass through `t2fand_args`, `t2fand --help` is authoritative, and examples may include `--verbose` or `--sensor-recovery-cycles 10`. Preserve the conf.d payload, destination, mode `0644`, `OPENRC_CONFDIR`, Makefile installation, local `PKGBUILD` source, `backup=('etc/conf.d/t2fand')`, package identity/metadata, and administrator changes. An absent or empty conf.d file is valid. The daemon parser and its defaults remain authoritative; no daemon CLI option, validation, path routing, telemetry, or runtime behavior is removed or changed. | checked-in conf.d, Makefile, package, README, and static test definitions; staging, package, and runtime outcomes unknown |
| `REQ-076` | On every OpenRC start, set exactly `command_args="${t2fand_args:-}"`; do not construct or forward the six dedicated conf.d options. Retain daemon ownership of `/run/t2fand.pid`, omit an OpenRC `pidfile`, preserve current logger routing and supervision/install behavior, and accept absent, empty, or nonempty `t2fand_args`.                                                                                                                                                                                                                                                                                                                                                                                                                                           | checked-in init definition and static test definitions; OpenRC runtime unknown                                            |
| `REQ-077` | The checked-in tests and operator documentation prove the one-variable conf.d contract, exact `command_args` forwarding, absent/empty/nonempty validity, unchanged daemon CLI options/defaults/validation, unchanged package payload/mode/backup/install behavior, and preserved CLI/runtime behavior. These definitions are implementation evidence; test execution, runtime, staging, OpenRC, and package outcomes remain unknown.                                                                                                                                                                                                                                                                                                                                         | checked-in unittest/static and README definitions; execution, runtime, staging, OpenRC, and package outcomes unknown      |

## Runtime rules

### Startup

The daemon parses and validates CLI arguments before root checks or filesystem
mutation, then handles PID state, discovers T2-only fans below `APP0001:00`, and
requires every discovered candidate to be complete and controllable. The
`REQ-071` overrides route the selected config, PID, sysfs, recovery-cycle,
sample-limit, and reminder values to their runtime consumers. It then generates
configuration only when absent, resolves `[General] control_mode` under
`REQ-078`, installs signal-request handlers, and enters the outer lifecycle
`try/finally`. A legacy config without `[General]` selects t2fand and emits
exactly one warning. In SMC mode it releases and verifies `fan*_manual=0`; in
t2fand mode it enables daemon fan control. A fan-discovery or control-authority
defect is `control-error`; a complete fan does not mask another discovered
incomplete fan. Fan-policy defects are fail-safe only in t2fand mode. Failure to
generate an absent config or read/parse an existing INI is `StartupError` before
fan control or fan mutation and does not command maximum output. An invalid
`[General].control_mode` follows the same pre-control path. SMC mode does not
protect by taking over fan output.

### Sampling and states

Each one-second cycle rediscoveries sensors, reads each selected input once,
records unknown failures without numeric sentinels, and selects the maximum
valid temperature. When vgaswitcheroo exposes a `DIS:Off` dGPU PCI address,
matching resolved temperature candidates are skipped before reading. Both modes
emit the compact default or full `-v` telemetry defined by `REQ-068`; SMC does
not imply verbose output. SMC mode continues monitoring with degraded values
when inputs fail and never enters fail-high takeover. T2fand mode retains the
existing CPU availability, sensor-failsafe, recovery, smoothing, and
configured-full rules. The `smc-auto` and `smc-degraded` status names remain
stable; they are not global `control_mode` values.

In SMC mode, failed sensor readings, including CPU and tachometer readings, are
reported as `unknown`; sensor failure alone does not command maximum or become a
fatal control error. GPU absence is a topology state, not by itself a failure.
Any inability to release or verify `fan*_manual=0` follows ownership loss
escalation. T2fand mode retains the existing fail-high and FanN configuration
fail-safe behavior that persists until restart; INI load/read/parse failures are
startup errors instead.

### Curves and fan output

Every t2fand-mode target is clamped to each fan's reported integer min/max
before writing. T2fand-mode curves retain the existing formulas and threshold
ordering. SMC reads and verifies hardware manual state, but does not normally
write fan output. Fan output, t2fand-mode writes, limits, manual-state
verification, and tachometer reads reopen sysfs paths as needed; no persistent
file object is retained. Actual RPM read failure reports `actual_rpm=unknown`;
it fails high in t2fand mode and only degrades monitoring in SMC mode.

### Cleanup

Signal handlers set a shutdown request. The normal lifecycle observes it,
reports `shutting-down`, and runs common cleanup. T2fand cleanup first attempts
maximum output on fatal paths, then attempts `fan*_manual=0` independently, and
then attempts PID removal regardless of earlier errors. SMC clean shutdown
releases `fan*_manual=0`; a failed release follows ownership-loss escalation.
Cleanup failures are reported alongside the original failure. No cleanup claim
covers SIGKILL, power loss, kernel panic, interpreter/native abort, or hardware
that no longer accepts writes.

## Interfaces

The checked-in control-mode revision and rename add the interfaces below. They
supersede only the conflicting portions named by their replacement requirements
while retaining earlier rows as historical evidence. `IF-002` FanN requirements
and `IF-003` output/manual writes apply according to `smc`/`t2fand` mode as
specified by `IF-033` and `IF-023`.

| ID       | Interface                                    | Contract                                                                                                                                                                                                                                                                                                                                                                                                                                                                                            | Status                                                                                                                            |
| -------- | -------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| `IF-001` | CLI/process                                  | Foreground `t2fand`; `-v`/`--verbose`; unknown arguments fail before mutation.                                                                                                                                                                                                                                                                                                                                                                                                                      | checked-in source; runtime unverified                                                                                             |
| `IF-002` | INI file                                     | `/etc/t2fand.conf`; optional global `[General]`; `Fan1`…`FanN`; four FanN keys; generated defaults; startup-only read; mode-specific FanN policy use.                                                                                                                                                                                                                                                                                                                                               | checked-in source; config runtime unknown                                                                                         |
| `IF-003` | Linux fan sysfs                              | Discover and deduplicate T2-only fan candidates below `APP0001:00`; read usable integer `<base>_max` and `<base>_min` with minimum no greater than maximum; write `<base>_output` and `<base>_manual`; reopen paths. Any incomplete candidate or loss of maximum-control authority is fatal.                                                                                                                                                                                                        | checked-in source; hardware unknown                                                                                               |
| `IF-004` | Linux temperature sysfs                      | Global hwmon plus coretemp and exact numeric DRM-card ancestry; signed millidegrees; optional labels/fault metadata; in t2fand mode at least one usable positive selected CPU channel is required and selected input or fault read/parse failure is fail-safe; in SMC mode failures are `unknown` degraded monitoring without takeover.                                                                                                                                                             | implementation target; hardware/runtime unknown                                                                                   |
| `IF-005` | PID file                                     | Daemon-owned `/run/t2fand.pid`; decimal PID; malformed/stale handling per `REQ-042`; no supervisor reuse.                                                                                                                                                                                                                                                                                                                                                                                           | checked-in source and test definitions; runtime unverified                                                                        |
| `IF-006` | POSIX signals                                | SIGINT/SIGTERM request common cleanup only.                                                                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in source and test definitions; runtime unverified                                                                        |
| `IF-022` | Historical control-mode configuration        | Historical superseded global `[General] control_mode` interface with former values `smc` or `manual`, including generated SMC and legacy-manual inference. FanN policies were control inputs only in the former manual mode.                                                                                                                                                                                                                                                                        | historical; superseded by `IF-033`                                                                                                |
| `IF-023` | SMC fan ownership                            | SMC writes, verifies, and maintains each discovered `<base>_manual` at `0`; it normally does not write `<base>_output`. Ownership loss attempts release, then known maxima, then fatal `control-error` if release cannot be restored.                                                                                                                                                                                                                                                               | checked-in source and fake-sysfs test definitions; hardware/runtime unverified                                                    |
| `IF-024` | Mode telemetry                               | SMC emits flushed telemetry by default once per second with all sensors, highest value, dGPU/topology state, manual state, target, and actual RPM; failed values are `unknown`. Manual retains the same record under `--verbose`.                                                                                                                                                                                                                                                                   | superseded by `IF-026`; historical evidence only                                                                                  |
| `IF-025` | Configuration outcome                        | Absent-config generation failure, existing INI read/parse failure, and invalid `[General].control_mode` produce `StartupError` before fan mutation with an exact diagnostic and no maximum command. Invalid FanN policy produces t2fand `config-failsafe`/maximum behavior, but only a warning and dormant policy defect in SMC.                                                                                                                                                                    | implementation target; runtime unverified                                                                                         |
| `IF-026` | Telemetry records                            | Both modes emit one record per one-second cycle. Default records are compact: `highest` is the hottest eligible sensor label, `highest_temp` its value, and every fan contributes `actual_rpm`; `-v` selects the full record. No mode implies verbose; invalid hottest candidates are excluded and ties use discovery order. This supersedes `IF-024`.                                                                                                                                              | checked-in source and telemetry test definitions; runtime unverified                                                              |
| `IF-027` | CLI runtime overrides                        | `-v`/`--verbose`, `-c`/`--config-path`, `-p`/`--pid-path`, `-s`/`--sysfs-path`, `-r`/`--sensor-recovery-cycles`, `-l`/`--sample-limit`, and `-e`/`--error-reminder-seconds` expose the `REQ-071` types/defaults and reach their consumers before mutation.                                                                                                                                                                                                                                          | checked-in source and CLI test definitions; runtime unverified                                                                    |
| `IF-028` | OpenRC conf.d payload                        | `t2fand.confd` stages as `/etc/conf.d/t2fand` mode `0644`, with the seven declared defaults and administrator-preserving package backup metadata. The exact runtime payload is daemon, init, and conf.d files.                                                                                                                                                                                                                                                                                      | historical; conf.d contents superseded by `IF-031`; payload retained                                                              |
| `IF-029` | OpenRC argument forwarding                   | The init script constructs the ordered six-option long-argument vector from `IF-028` and appends `t2fand_args` last through `command_args`; empty arguments are valid, and no supervisor `pidfile` is introduced. Path values with whitespace are disallowed pending safe quoting verification.                                                                                                                                                                                                     | historical; forwarding superseded by `IF-032`                                                                                     |
| `IF-030` | Benchmark log output                         | `t2fanbench.py` printed log lines use local, locale-independent English `MMM DD HH:mm:ss [t2fanbench] MESSAGE` formatting, with flushed output and preserved logger side effect.                                                                                                                                                                                                                                                                                                                    | checked-in benchmark source and static test definition; runtime unverified                                                        |
| `IF-031` | OpenRC optional-argument conf.d payload      | `/etc/conf.d/t2fand` is the packaged third payload, mode `0644`, and contains only optional `t2fand_args`; daemon defaults and typed option definitions remain in `t2fand`. The file is preserved by package backup metadata and may be absent or empty.                                                                                                                                                                                                                                            | checked-in conf.d, Makefile, package, README, and static test definitions; staging, package, and runtime unknown                  |
| `IF-032` | OpenRC optional-argument forwarding          | `/etc/init.d/t2fand` sets `command_args="${t2fand_args:-}"` and forwards no dedicated conf.d defaults. Empty and nonempty argument strings are valid; daemon PID ownership, logger routing, and the no-`pidfile` boundary remain unchanged.                                                                                                                                                                                                                                                         | checked-in init definition and static test definitions; OpenRC runtime unknown                                                    |
| `IF-033` | Global control-mode configuration            | `/etc/t2fand.conf` accepts exactly `control_mode=smc` or `control_mode=t2fand` in global `[General]`. Generated/default configuration selects `smc`; an existing config without `[General]` infers `t2fand`, warns exactly once, and is not rewritten. `manual`, `auto`, `smc_auto`, and other aliases are rejected. FanN policies apply only in t2fand; SMC observes without ordinary FanN/output control. Hardware `fan*_manual`, `smc-auto`, and `smc-degraded` names/statuses remain unchanged. | checked-in daemon/configuration source, README, CONTEXT, and unittest definitions; runtime, config, and test execution unverified |
| `IF-034` | Benchmark prerequisite and failure interface | `t2fanbench.py` performs `shutil.which("stress-ng")` before cache creation, benchmark/logger output, baseline sleep, or subprocess launch. A missing executable emits exactly `error: stress-ng is required but was not found in PATH` on stderr and returns `1` without traceback or any listed side effect. An available executable preserves the existing benchmark, local-English timestamp, logger, and child-output interfaces.                                                               | checked-in benchmark source and behavior-focused fake test definitions; runtime and test execution unknown                        |
| `IF-007` | Historical systemd unit                      | `Type=simple`, restart, PIDFile, and default-target interface from the prior unit.                                                                                                                                                                                                                                                                                                                                                                                                                  | superseded historical interface                                                                                                   |
| `IF-008` | Historical Make selector                     | `INIT_SYSTEM` and systemd/OpenRC selector interface.                                                                                                                                                                                                                                                                                                                                                                                                                                                | superseded historical interface                                                                                                   |
| `IF-009` | Historical Arch package                      | Prior package installed executable and both service definitions.                                                                                                                                                                                                                                                                                                                                                                                                                                    | superseded historical interface                                                                                                   |
| `IF-010` | GitHub Actions                               | Existing push/PR package workflow and gates.                                                                                                                                                                                                                                                                                                                                                                                                                                                        | retained; execution unknown                                                                                                       |
| `IF-011` | OpenRC init script                           | `/etc/init.d/t2fand`, `/usr/bin/t2fand`, foreground `supervise-daemon`, directives in `REQ-043`, logger routing in `REQ-044`.                                                                                                                                                                                                                                                                                                                                                                       | checked-in init definition and static test definitions; OpenRC runtime unknown                                                    |
| `IF-012` | Historical service selector                  | `INIT_SYSTEM=auto` and explicit systemd/OpenRC selection.                                                                                                                                                                                                                                                                                                                                                                                                                                           | superseded by OpenRC-only `IF-017`                                                                                                |
| `IF-013` | Historical PID/supervisor boundary           | Daemon PID ownership and OpenRC omission of `pidfile`.                                                                                                                                                                                                                                                                                                                                                                                                                                              | retained/narrowed by `IF-016`                                                                                                     |
| `IF-014` | Make install                                 | `DESTDIR`, `BINDIR`, `OPENRC_INITDDIR`, and `OPENRC_CONFDIR` unconditional OpenRC staging only; stages daemon 0700, init 0755, and conf.d 0644.                                                                                                                                                                                                                                                                                                                                                     | checked-in Makefile; staging unverified                                                                                           |
| `IF-015` | Arch package                                 | Unchanged package name; exactly daemon/init payload plus declared dependencies.                                                                                                                                                                                                                                                                                                                                                                                                                     | superseded by `REQ-075`/`IF-031`; historical two-file package evidence only                                                       |
| `IF-016` | PID/supervisor boundary                      | Daemon owns `/run/t2fand.pid`; supervisor state is separate; wrapper `pidfile` forbidden.                                                                                                                                                                                                                                                                                                                                                                                                           | retained by `REQ-043`                                                                                                             |
| `IF-017` | Service-manager boundary                     | OpenRC only; `/etc/init.d/t2fand` only service artifact.                                                                                                                                                                                                                                                                                                                                                                                                                                            | checked-in source/package definitions; runtime unknown                                                                            |
| `IF-018` | OpenRC argument configuration                | `/etc/conf.d/t2fand`, optional `t2fand_args`, passed as `command_args`; the conf.d file is the shipped third package payload.                                                                                                                                                                                                                                                                                                                                                                       | historical; forwarding/content superseded by `IF-031`/`IF-032`                                                                    |
| `IF-019` | OpenRC logger transport                      | `/usr/bin/logger` from util-linux; stdout `daemon.info`, stderr `daemon.err`, tag `t2fand`.                                                                                                                                                                                                                                                                                                                                                                                                         | checked-in init/package definitions and static test definitions; logger delivery unknown                                          |
| `IF-020` | Local package staging                        | `PKGBUILD` supplies local daemon/init/Makefile sources and calls `make DESTDIR="$pkgdir" install`; Makefile stages the exact two-file OpenRC payload.                                                                                                                                                                                                                                                                                                                                               | historical; payload content superseded by `REQ-075`/`IF-031`                                                                      |
| `IF-021` | vgaswitcheroo filtering                      | `/kernel/debug/vgaswitcheroo/switch` may identify one `DIS:Off` dGPU PCI address; matching resolved temperature candidates are excluded, while unavailable switch state leaves general discovery enabled.                                                                                                                                                                                                                                                                                           | checked-in source; hardware/runtime unknown                                                                                       |

## Runtime state and paths

| State/path                 | Meaning and ownership                                                                                                                                                                             |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `/etc/t2fand.conf`         | Administrator policy; generated only when absent with `[General] control_mode=smc`; legacy files without `[General]` infer t2fand and warn exactly once; never normalized; read once per start.   |
| `/etc/conf.d/t2fand`       | Packaged OpenRC administrator configuration, mode 0644, preserved by package backup metadata; declares only optional `t2fand_args`; daemon defaults remain in `t2fand`.                           |
| `/run/t2fand.pid`          | Decimal daemon PID; daemon-owned; stale cleanup per contract; not authenticated locking.                                                                                                          |
| OpenRC supervisor state    | Separate manager state; must not claim daemon PID.                                                                                                                                                |
| `/etc/init.d/t2fand`       | Installed sole OpenRC definition, mode 0755.                                                                                                                                                      |
| `/usr/bin/t2fand`          | Installed extensionless Python executable, mode 0700.                                                                                                                                             |
| Fan sysfs files            | Kernel/device boundary; reopened for each operation. SMC maintains `<base>_manual=0` while Apple SMC owns the fans; t2fand owns daemon control and output.                                        |
| Hwmon temperature files    | Per-cycle discovered/read inputs; aliases deduplicated by resolved path.                                                                                                                          |
| vgaswitcheroo switch       | Optional power-topology input used only for `DIS:Off` dGPU sensor filtering.                                                                                                                      |
| `temps` history            | In-memory maximum temperatures; at most five valid normal/recovery samples; cleared on sensor recovery.                                                                                           |
| Mode/reason/topology state | In-memory externally reported state; transitions are logged, repeated reasons are rate-limited by default. Both modes emit compact telemetry each second by default; `-v` selects full telemetry. |

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

The init script sources the packaged `/etc/conf.d/t2fand` value and sets
`command_args="${t2fand_args:-}"`. It does not duplicate or forward daemon
defaults. Empty, absent, and nonempty `t2fand_args` remain valid. The daemon
parser and `t2fand --help` own the CLI options and defaults.

## Installation and package contract

`make install` has no selector, compilation, service action, or alternate init
branch. It honors `DESTDIR`, `BINDIR`, `OPENRC_INITDDIR`, and `OPENRC_CONFDIR`,
and installs the three files and modes in `REQ-075`. `PKGBUILD` supplies local
`t2fand`, `t2fand.initd`, `t2fand.confd`, and `Makefile` sources and delegates
to `make DESTDIR="$pkgdir"
install`. The Arch package is named `t2fand` at
target release `2.0.1-2`, retains its checked-in metadata, retains `linux-t2`,
`python`, and `git`, and includes `util-linux` for `/usr/bin/logger`. The
package payload is exactly the daemon, OpenRC init script, and conf.d file.
`backup=()` preserves `/etc/conf.d/t2fand`. No package rename, systemd
directory, unit, post-install service action, or guessed syslog daemon
dependency is allowed.

## Workflows

### Configuration

First start generates `[General] control_mode=smc` and one default section per
detected fan. Administrators may select `smc` or `t2fand`; the four FanN options
are used only by t2fand mode. An existing file without `[General]` infers t2fand
mode, emits exactly one warning, and is not rewritten. The file is read once at
startup; repair requires a restart. Failure to generate an absent file or read
or parse an existing INI is a pre-control `StartupError`, with no maximum
command or fan mutation. Invalid FanN config requests maximum only in t2fand
mode. SMC mode reports such FanN defects as dormant warnings and does not
globally fail-safe or take over.

### Configuration examples

Valid generated/default selection:

```ini
[General]
control_mode=smc
```

Valid daemon-owned selection:

```ini
[General]
control_mode=t2fand
```

An existing file with FanN sections but no `[General]` uses t2fand, warns
exactly once, and remains unchanged. `control_mode=manual`, `auto`, `smc_auto`,
or any alias is invalid; it is not a migration alias.

### Service and logs

Install without starting or enabling any service. Configure the packaged
`/etc/conf.d/t2fand` optional argument override, including
`t2fand_args="--verbose"`, then use OpenRC commands. Daemon defaults and typed
options remain authoritative in `t2fand` and `t2fand --help`. Read routed output
through the local syslog facility (`/var/log/messages`, `/var/log/daemon.log`,
`logread`, or another administrator-selected location). Persisted logs require a
running receiver; exact destination is unknown.

### Recovery

In SMC mode, Apple SMC owns the fans; sensor input failures remain alive as
degraded monitoring and do not take over fan output. Loss of `fan*_manual=0`
ownership attempts release, then maximum, then exits nonzero if release cannot
be restored. In t2fand mode, sensor failures and invalid FanN policies remain
alive at maximum and retry as specified; configuration load/read/parse failures
exit through pre-control `StartupError` instead; control authority failures exit
nonzero for bounded OpenRC supervision. Configuration recovery requires restart.
Cleanup is best effort. No hardware, OpenRC, package, or syslog execution is
claimed in this task.

## Constraints, safety, and trust boundaries

- Root and Linux sysfs remain required; exact hardware/model/kernel/distribution
  support is unknown.
- Every valid discovered temperature can influence control; the hottest value is
  selected. CPU is mandatory through at least one usable positive selected
  channel; non-positive CPU siblings do not invalidate it. GPU is optional. Fan
  discovery is T2-only below `APP0001:00`; this restriction does not remove
  global hwmon temperature discovery.
- In t2fand mode, any discovered selected sensor input or fault read/parse
  failure, including a CPU channel, enters sensor fail-safe; absence alone is
  not a fault. In SMC mode, the same failures are `unknown` degraded monitoring
  and do not take over fan output.
- T2fand-mode fail-safe is a control state, not a fabricated temperature, and
  bypasses smoothing. SMC mode has no sensor fail-high takeover.
- All discovered fans share global safety decisions; one invalid FanN policy or
  incomplete fan does not permit another fan to remain on an untrusted curve,
  and a complete fan does not mask it.
- INI generation, read, and parse failures are startup errors before fan control
  or fan mutation; they do not enter t2fand config-failsafe or command maxima.
- Known maxima and writable controls are required for t2fand recoverable safe
  control and SMC ownership-loss escalation; every discovered fan must be
  complete, and inability to command maximum during escalation is fatal.
- `/run/t2fand.pid` is daemon-owned. The PID existence check is not identity
  authentication or atomic locking.
- No secrets, network listener, encryption, direct syslog API, Python logging
  framework, persistent sysfs handle, or remote source claim is introduced.
- Cleanup cannot guarantee fan state after abrupt power/kernel/interpreter or
  hardware failure.
- OpenRC is sole service integration; package payload is exactly the daemon,
  init, and conf.d files defined by `REQ-075`.
- When readable, vgaswitcheroo `DIS:Off` entries identify a PCI address whose
  matching resolved dGPU temperature candidates are skipped; absent or
  unreadable switch state does not disable general sensor discovery.

## Observability

Default output is flushed and contains startup/shutdown summaries, warnings,
errors, topology/state transitions, exact config problems, mode, and failure
reasons. Both modes additionally emit one compact record each second by default,
containing only `highest` as the hottest eligible sensor label, `highest_temp`
as its value, and every fan's `actual_rpm`. `-v`/`--verbose` selects the
complete record in either mode, including all sensor labels and values/unknown
states, dGPU/topology state, per-fan manual state, observed current
`fan*_output` as `target_rpm`, and `actual_rpm`; SMC `target_rpm` is `unknown`
only when reading `fan*_output` fails and is not a userspace curve target.
Hottest-sensor ties use discovery order; unavailable hottest and RPM values are
`unknown`. Logger routing is service-level transport only. No metrics, tracing,
health endpoint, or audit store is defined.

## Compatibility and dependencies

Compatibility requires Python 3, Linux hwmon/sysfs, root, and OpenRC. Arch
target remains `x86_64`; package identity is `t2fand`, GPL3, target release
`2.0.1-2` (`pkgver=2.0.1`, `pkgrel=2`). Runtime dependencies are `linux-t2`,
`python`, and `util-linux`; `git` remains a build dependency. No specific syslog
daemon is required. The local package-source list and skipped checksums are
static metadata; build and artifact provenance outcomes remain unknown.

## Validation and acceptance

No test execution, hardware access, root execution, OpenRC lifecycle,
staged-install, package build, or syslog delivery is claimed here. Checked-in
source, configuration-generation logic, benchmark source, operator
documentation, CONTEXT, and fake-sysfs unittest definitions evidence the current
`REQ-078`–`REQ-080` rename and the benchmark prerequisite in
`REQ-081`/`IF-034`/`DEC-033`/`H-021`, alongside the other existing surfaces.
They establish source/static definitions and test-definition presence only; they
do not establish runtime behavior or any hardware, service, package, staging, or
syslog outcome. The `make test` outcome remains unverified because it was not
run.

Prior-revision runtime and integration acceptance remains historical evidence;
its first four checks retain the prior mode-independent fail-high,
FanN-global-failsafe, and verbose-only clauses only as history. Checks 5–8 cover
the checked-in control-mode, telemetry, and safety test definitions, while
current rename acceptance is defined by `REQ-078`–`REQ-080`. The checked-in
transition in `REQ-068`–`REQ-074`, excluding the historical conf.d/forwarding
semantics of `REQ-069` and `REQ-072`, is authoritative for changed telemetry,
package, CLI, benchmark-formatting, test, and documentation behavior. The
benchmark prerequisite and its validation definition are current in `REQ-081`,
`IF-034`, `DEC-033`, and `H-021`. Execution remains unverified:

1. `make test` using standard-library unittest fake sysfs/config/run trees and
   mocks, covering T2-only fan discovery, global hwmon sensor inputs,
   CPU/GPU/Wi-Fi/storage/arbitrary channels, numeric DRM versus connectors,
   alias deduplication, one read per cycle, hottest selection,
   GPU-missing/recovery transitions, mixed CPU channels with a positive and
   non-positive sibling, all sensor/CPU/fault/parse failures including a
   positive CPU plus another failed channel, immediate maximum, five-cycle
   recovery and history reset, one-second/five-sample smoothing, all curves,
   every FanN policy defect plus config-generation-I/O, unreadable-config,
   malformed-INI, and invalid-mode startup paths, valid configured-full
   distinction, no fan, unreadable/incomplete/invalid-limit fan,
   complete-plus-incomplete fan-set rejection, daemon-control enable failure,
   maximum-write failure, fatal maximum attempts for every discovered fan,
   independent cleanup, both signals, malformed/stale PID, verbose fields, RPM
   naming, and default error rate limiting.
2. Historical static checks for import safety, exact modes/paths, unconditional
   OpenRC install, T2-only fan discovery, vgaswitcheroo `DIS:Off` dGPU
   filtering, local package sources and `make DESTDIR` staging, prior package
   release `2.0.1-1`, prior exact two-file package payload, `util-linux`,
   configurable args, logger directives, local-filesystem/soft-logger
   dependencies, PID-path separation, bounded/backed-off directives, and absence
   of alternate init artifacts/selectors/payloads.
3. Documentation review proving README onboarding is concise while retaining
   operator-action, safety, configuration, OpenRC, observability, and testing
   pointers; `SPEC.md` and `CONTEXT.md` retain exhaustive contract and
   implementation detail. Package descriptions, install instructions, and
   service comments must not contradict that ownership or the safety contract.
4. Static review of Artix/OpenRC README coverage, ignored opencode/build
   surfaces, unrelated edits, stale CPU/card0-only claims, secrets, shell
   portability, modes, and readability.

5. Checked-in fake-sysfs/config test definitions define exactly
   `[General] control_mode=smc|t2fand`, generated-SMC versus legacy-t2fand
   resolution and exactly one warning, rejection of `manual`, `auto`,
   `smc_auto`, and other aliases, SMC `fan*_manual=0` release, verification, and
   per-cycle maintenance. They must prove SMC never ordinarily applies FanN
   policies or writes `fan*_output`. They must also define pre-control
   `StartupError` for config generation/read/parse/mode failures without fan
   mutation or maximum command, and dormant SMC warnings for malformed FanN
   policy. These definitions evidence implementation; runtime and test execution
   remain unverified.
6. Checked-in fake-sysfs test definitions define compact telemetry emitted by
   default every second in both modes, full telemetry under `-v`, hottest
   label/value fields, dGPU/topology state, hardware manual state, target, and
   actual RPM; failed thermal/tachometer reads remain `unknown` and do not
   trigger SMC takeover. They must define ownership-loss release, maximum
   escalation, fatal status, and clean-shutdown release.
7. Checked-in tests retain t2fand-mode regression coverage for existing curves,
   smoothing, FanN-policy config-failsafe, sensor-failsafe, actual-RPM
   fail-high, maximum attempts, cleanup, T2-only fan discovery, and powered-off
   dGPU filtering. No tests or behavior for the listed non-goals are in scope.

8. Checked-in telemetry test definitions prove compact telemetry once per cycle
   in both modes by default, full telemetry only with `-v`, distinct hottest
   label/value fields, skipped/faulted/no-valid/tied sensor handling, and
   independent warnings and transitions.
9. Current CLI tests must prove every CLI short/long option, defaults, help
   text, runtime consumers, pre-mutation numeric rejection, custom path/PID
   cleanup, and supplied recovery, sample, and reminder values without global
   mutation.
10. Current static/package tests must prove `OPENRC_CONFDIR`, the three staged
    files and modes, local conf.d source, exactly one active `t2fand_args`
    assignment, `backup=()`, release `2.0.1-2`, and no service action.
11. Current init tests must prove the exact `command_args="${t2fand_args:-}"`
    assignment, absence of dedicated forwarding, empty/absent/nonempty
    `t2fand_args`, and daemon PID ownership.
12. Current benchmark tests must prove the standard-library PATH lookup for
    `stress-ng` occurs before cache creation, benchmark/logger output, baseline
    sleep, or any subprocess launch. The unavailable-path fake test must prove
    exact stderr `error: stress-ng is required but was not found in PATH`, exit
    status `1`, no traceback, and no installation, logger, output, sleep,
    workload, timer, or subprocess side effect. The available-path fake test
    must preserve the existing benchmark sequence. Behavior-focused fakes must
    use no workloads or timers. Tests must also prove exact timestamp/tag output
    under a non-English locale while keeping logger and child-output behavior
    unchanged. Runtime and test execution remain unknown.
13. Current documentation review must prove the affected operator surfaces
    describe the renamed global modes, new telemetry, options, conf.d/package
    workflow, overrides, benchmark format, and the `stress-ng` PATH prerequisite
    with its exact unavailable-path error/no-side-effect contract without
    contradicting this contract.

Checked-in source and test definitions must be labeled separately from
unavailable hardware, OpenRC, syslog, package, and service-runtime evidence. No
README example, source inspection, test-definition presence, or formatter run
proves runtime behavior. `dprint fmt --no-gitignore SPEC.md` is formatting only;
this file is not associated with ordinary Markdown by the current `dprint.json`.

The checked-in source and package definitions provide evidence for the current
`2.0.1-2` package handoff; the prior `2.0.1-1` handoff remains historical
evidence. The checked-in static package validation checks that the local-source
`PKGBUILD` delegates staging through `make DESTDIR="$pkgdir" install`, that the
Makefile stages the three `REQ-075` files and modes, and that the target package
release is `2.0.1-2` with no alternate selector or service payload. Test
execution remains unknown. The default fake fixture creates a T2 fan at
`devices/a/b/c/d/APP0001:00`, so this static fan-discovery definition aligns
with `REQ-052`. No test pass or implementation-runtime claim is made from those
definitions.

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
- `DEC-007` (retained; payload portion superseded by `DEC-024`): OpenRC is the
  sole supported service manager; `t2fand.initd` is the sole service definition;
  no systemd unit.
- `DEC-008` (retained): Make installation is unconditional OpenRC staging
  through `DESTDIR`, `BINDIR`, `OPENRC_INITDDIR`, and `OPENRC_CONFDIR`, with no
  service actions; the current payload is the daemon, init, and conf.d files
  defined by `REQ-075`.
- `DEC-009` (**narrowed by `DEC-013` and `DEC-024`):** retain package name
  `t2fand` and daemon/init payload boundary; do not guess an OpenRC or syslog
  daemon dependency.
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
  maximums independently for all discovered fans before independent hardware
  manual-control and PID cleanup.
- `DEC-016` (settled; checked-in source; hardware/runtime unknown): fan
  discovery is T2-only below `APP0001:00`; global hwmon remains a
  temperature-sensor source, not a fan-candidate source.
- `DEC-017` (settled; checked-in source; hardware/runtime unknown):
  vgaswitcheroo `DIS:Off` filtering is scoped to matching resolved dGPU PCI
  ancestry and does not become a blanket sensor exclusion when switch state is
  unavailable.
- `DEC-018` (historical; payload portion superseded by `DEC-024`; checked-in
  package metadata; build/runtime unknown): the 2.0.1 package uses local source
  files, delegates staging through Makefile `DESTDIR`, documents Artix/OpenRC
  operation, ignores opencode and generated artifacts, and retains the exact
  two-file payload.
- `DEC-019` (historical; superseded by `DEC-032`; checked-in source and
  fake-sysfs test definitions; runtime unknown): control was globally selected
  by `[General] control_mode=smc|manual`; generated configs selected SMC, while
  existing configs without `[General]` preserved legacy manual behavior with one
  warning and no rewrite.
- `DEC-020` (settled; checked-in source and fake-sysfs test definitions;
  hardware and runtime unknown): SMC is monitor-only. It releases, verifies, and
  maintains every `fan*_manual=0`, normally never writes `fan*_output`, and
  degrades on sensor failure without takeover.
- `DEC-021` (settled; checked-in source and fake-sysfs test definitions; runtime
  unknown): t2fand mode retains existing curves and fail-high behavior. SMC
  ownership loss attempts hardware manual release, then known maximum output,
  then fatal `control-error`; clean shutdown releases hardware manual control.
- `DEC-022` (settled; checked-in source and configuration test definitions;
  runtime unknown): configuration load/generation failures are pre-control
  startup errors with no fan mutation or maximum command. Invalid FanN policy
  remains t2fand config-failsafe, while SMC only warns and remains passive.
- `DEC-023` (settled; checked-in source and test definitions; runtime
  unverified): both control modes emit compact telemetry every cycle by default;
  only `-v` selects the full record. SMC mode never implies verbose, and
  hottest-sensor identity is separate from hottest-sensor value.
- `DEC-024` (settled; checked-in package definitions; staging, build, and
  runtime unknown): ship the administrator conf.d file as the third exact
  package payload, preserve it with `backup=()`, and set the package release to
  `2.0.1-2`.
- `DEC-025` (settled; checked-in source and test definitions; runtime
  unverified): expose six validated runtime overrides, parse them before root or
  filesystem mutation, and thread them through runtime consumers without
  changing module globals.
- `DEC-026` (historical; superseded by `DEC-030`; checked-in init and static
  test definitions): forward conf.d defaults as six ordered long options and
  append `t2fand_args`; retain daemon PID ownership, and disallow whitespace in
  forwarded paths until safe quoting is verified.
- `DEC-027` (settled; checked-in benchmark source and test definition; runtime
  unverified): benchmark printed messages use locale-independent English local
  timestamps while preserving logger and child-process side effects.
- `DEC-028` (settled; checked-in tests and documentation; execution unverified):
  acceptance covers the new telemetry, CLI, conf.d, forwarding, benchmark,
  package, regression, and operator-documentation contract without claiming test
  execution.
- `DEC-029` (authoritative checked-in correction; checked-in source/config,
  documentation, and test-definition evidence; runtime and execution unknown):
  daemon parser defaults and typed runtime options remain the sole authority.
  The packaged conf.d surface exposes only optional `t2fand_args`; `DEC-025` is
  retained and does not require those options to be duplicated in conf.d.
- `DEC-030` (authoritative checked-in correction; checked-in init/config and
  static test-definition evidence; OpenRC runtime unknown): OpenRC passes only
  `command_args="${t2fand_args:-}"`. The six dedicated conf.d forwarding options
  and their whitespace-path limitation are superseded; PID ownership, logger
  routing, supervision, and install boundaries remain unchanged.
- `DEC-031` (authoritative checked-in correction; checked-in package, source,
  documentation, and test-definition evidence; runtime, staging, package,
  OpenRC, and test execution unknown): package payload, mode, backup, Makefile
  install, absent/empty conf.d validity, and unchanged daemon CLI/runtime
  behavior are acceptance invariants. The checked-in tests and documentation
  implement the correction; they do not establish execution or package outcome.
- `DEC-032` (authoritative; checked-in source, operator documentation, CONTEXT,
  and test definitions; runtime and test execution unverified): the global
  control-mode rename replaces `manual` with `t2fand`. Only `smc` and `t2fand`
  are valid global values; `manual`, `auto`, `smc_auto`, and aliases are
  rejected. Generated configs default to SMC, while existing configs without
  `[General]` infer t2fand, warn exactly once, and remain unchanged. Apple SMC
  owns fans in SMC; t2fand owns fan control and applies FanN policies. Hardware
  `fan*_manual` terminology and `smc-auto`/`smc-degraded` statuses are
  preserved.
- `DEC-033` (authoritative checked-in benchmark decision; checked-in source and
  behavior-focused fake test definitions; runtime and test execution unknown):
  gate `t2fanbench.py` with the standard-library PATH lookup
  `shutil.which("stress-ng")` before cache creation, benchmark/logger output,
  baseline sleep, or subprocess launch. Missing `stress-ng` returns `1` with
  exactly the specified stderr and no traceback or side effect; available
  `stress-ng` retains the existing benchmark, local-English timestamps, logger,
  and child-output behavior. Installation, logger, and nonzero-result handling
  are not expanded.

## Cumulative change history

Rows in this history labeled current checked-in describe superseded repository
artifacts, not the current contract. The current control-mode truth is
`REQ-078`–`REQ-080`, `IF-033`, and `DEC-032`.

### Historical transition summary

- `H-001`–`H-004`: superseded systemd, dual-manager, and exact two-file
  service/package baselines; OpenRC-only support became the retained direction.
- `H-005`–`H-009`: proposed and checked-in global hwmon, CPU safety, fan-set
  safety, and evidence corrections; no runtime result was claimed.
- `H-010`–`H-013`: preserved release/install and documentation reconciliations,
  ending in the local 2.0.1 handoff with static evidence only.
- `H-014`–`H-015`: preserved the prior proposed and checked-in SMC/manual
  control-mode transition; those global tokens are superseded by `H-020`.
- `H-016`–`H-019`: preserved package-validation, configuration-outcome,
  telemetry/package, and conf.d/forwarding corrections; `H-019` records the
  checked-in conf.d/forwarding implementation evidence. Runtime, OpenRC,
  package, staging, and test execution remain unknown.
- `H-020`: authoritative checked-in rename to `smc`/`t2fand`, with legacy
  inference, rejection of old aliases, preserved hardware terminology, and
  checked-in runtime, configuration-generation, documentation, CONTEXT, and
  test-definition evidence. Runtime and test execution remain unverified.
- `H-021`: authoritative checked-in benchmark prerequisite: `stress-ng` is
  resolved through the standard-library PATH lookup before benchmark side
  effects; the missing-path error/status and no-side-effect behavior are
  defined, while the existing available-path sequence and output behavior are
  preserved. Runtime and test execution remain unverified.

<!-- The detailed historical rows below are retained as archival evidence. -->

| ID | State/change | Rationale and transition |
| -- | ------------ | ------------------------ |

| `H-001` | Superseded historical baseline: systemd was the only checked-in
service integration; OpenRC metadata was contradictory and unsupported. |
Preserved historical local evidence. | | `H-002` | Superseded pre-implementation
transition: 2026-08-27 reconciliation added OpenRC contract, Makefile
selection/staging, and both package service definitions. | Preserved prior
contract transition. | | `H-003` | Superseded dual-init implementation state:
init script, selector Makefile, systemd unit, and both-definition package were
present; systemd was authoritative. | Static inspection did not prove
staged/package/OpenRC/hardware/runtime success. | | `H-004` | Superseded
baseline: OpenRC-only support, retained init script, unconditional OpenRC
install, and exact two-file payload. | Preserved as the prior service/package
direction before the later handoff. | | `H-005` | Proposed pre-implementation
transition: global hwmon hottest-source control, CPU-required safety, explicit
modes, config fail-safe, cleanup hardening, verbose telemetry, fake tests,
logger routing, configurable arguments, util-linux, and bounded OpenRC recovery.
| User-authorized revision; no shipped behavior or runtime result is claimed. |
| `H-006` | Current checked-in implementation transition: daemon
`main(argv=None)`, verbose output, signal-request cleanup, global thermal
fail-safe source, OpenRC configurable arguments/logger/bounded recovery,
util-linux package metadata, and fake-sysfs test definitions are present. |
Source, service, package, and test definitions are evidence of checked-in
content only; no runtime, hardware, service, package, staging, or syslog result
is claimed. | | `H-007` | Current checked-in CPU-channel reconciliation: one
usable positive selected CPU channel satisfies CPU availability; non-positive
CPU siblings do not invalidate it, while any discovered sensor input or fault
read/parse failure remains fail-safe. | Corrects the stricter non-positive-CPU
statement retained as superseded `REQ-033`; source and test definitions are
evidence only, with no runtime result claimed. | | `H-008` | Contract
reconciliation: fan control requires every discovered,
resolved-path-deduplicated candidate to be complete and controllable; at least
one complete fan is not sufficient when another candidate is incomplete. |
Resolves the `REQ-038`/checked-in `discover_fans` mismatch with the smallest
safety-preserving global rule; source enforcement and partial targeted fan
coverage are present, exhaustive execution remains unverified. | | `H-009` |
Evidence correction: the `DEC-015` and `H-008` fan-coverage notes now record
partial targeted coverage for incomplete fan sets and fatal cleanup attempts. |
Corrects stale “targeted test coverage is not present” wording without claiming
test execution or complete coverage. | | `H-010` | Superseded release/install
reconciliation: the prior contract identified package release `1.2.0-3`; the
then-current checked-in package metadata identified intentional release
`2.0.0-1`. | Preserved prior release evidence; `H-013` records the 2.0.1
transition. | | `H-011` | Documentation ownership reconciliation: README is
concise operator onboarding; exhaustive contract and implementation/design
detail remain in `SPEC.md` and `CONTEXT.md`. | Preserves the safety/product
requirements while changing only detail placement; no shipped documentation or
runtime outcome is claimed. | | `H-012` | Current checked-in post-control
exception handling converts unexpected ordinary exceptions after manual control
starts into fatal `control-error` cleanup; pre-control and `BaseException` paths
remain outside that conversion. | Preserved from the verified source transition;
runtime outcomes remain unknown. | | `H-013` | 2.0.1 handoff reconciliation:
T2-only fan discovery, vgaswitcheroo `DIS:Off` dGPU filtering, local-source
Makefile package staging, Artix/OpenRC documentation, ignored opencode/build
artifacts, and release `2.0.1-1`. | Source/configuration files verify the
contract surfaces; stale unexecuted package assertions, package build, staging,
hardware, service, and release outcomes remain unverified. | | `H-014` | Prior
proposed pre-implementation control-mode transition: global SMC/manual
selection, generated-SMC and legacy-manual config compatibility, SMC
manual-state ownership without normal output writes, degraded monitoring,
default telemetry, ownership-loss escalation, clean release, and retained manual
curves/fail-high behavior. | Preserved historical contract stage; superseded by
the checked-in implementation evidence in `H-015`. Hardware and runtime outcomes
remain unverified. | | `H-015` | Superseded checked-in control-mode
implementation transition: daemon source and fake-sysfs test definitions
implement global SMC/manual selection, generated-SMC and legacy-manual
compatibility, passive SMC monitoring/default telemetry, ownership maintenance
and escalation, clean release, and retained manual curves/fail-high behavior. |
Source and test definitions verify checked-in content only; the global mode
tokens are superseded by `DEC-032`; hardware, runtime, service, and test
execution outcomes remain unknown. | | `H-016` | Historical package-validation
correction: the intended static package check was Makefile-authoritative,
requiring `PKGBUILD` delegation through `make DESTDIR="$pkgdir" install`, exact
two-file payload and modes defined by the Makefile, and release `2.0.1-1`. |
Preserves the prior `2.0.1-1` two-file validation record; superseded by
`REQ-075`/`H-018`, and checked-in definitions and validation intent do not prove
test execution, staging, package build, or release outcome. | | `H-017` |
Current configuration-outcome reconciliation: absent-config generation failure
and existing INI read/parse failure are pre-control `StartupError` paths with no
fan mutation or maximum command; malformed FanN policy remains t2fand
config-failsafe and is only a dormant warning in SMC. | Corrects the superseded
`REQ-037` file-level fail-safe wording using checked-in source and test
definitions; test execution, runtime, and hardware outcomes remain unknown. | |
`H-018` | Historical checked-in user-authorized transition: compact telemetry is
emitted every cycle by default in both modes, full telemetry is selected only by
`-v`, six validated CLI overrides are wired, `t2fanbench` messages are
timestamped, and `/etc/conf.d/t2fand` is a preserved third package payload with
ordered OpenRC forwarding. Its conf.d/forwarding portion is superseded by
`H-019`. | Explicitly supersedes the conflicting default-SMC-full-telemetry and
exact-two-file/non-payload clauses in `REQ-040`, `REQ-041`, `REQ-050`,
`REQ-054`, `REQ-058`, `REQ-064`, `IF-015`, `IF-018`, `IF-020`, and `IF-024`;
checked-in source, configuration, package, benchmark, documentation, and test
definitions confirm the current retained content and the historical
conf.d/forwarding content. Test execution, staging, package build, service,
hardware, and runtime outcomes remain unknown. | | `H-019` | Implemented
checked-in correction: remove duplicated daemon defaults from the shipped conf.d
surface, retain only `t2fand_args`, and restore init forwarding as
`command_args="${t2fand_args:-}"`. Preserve the third package payload and all
daemon CLI/runtime behavior. | Checked-in conf.d, init, package, README,
CONTEXT, and unittest definitions provide implementation evidence. The
conf.d/forwarding portions of `H-018` are superseded; staging, package, OpenRC,
runtime, and test-execution outcomes remain unknown. | | `H-020` | Current
checked-in global control-mode rename: replace the global `manual` token with
`t2fand`; retain generated/default `smc`, infer t2fand for existing configs
without `[General]` with exactly one warning and no rewrite, reject
`auto`/`smc_auto`/aliases, preserve SMC observation and t2fand FanN ownership,
and retain hardware `fan*_manual` plus `smc-auto`/`smc-degraded` terminology. |
Checked-in daemon/configuration-generation source, README, CONTEXT, and unittest
definitions provide synchronized surface evidence through `REQ-078`–`REQ-080`,
`IF-033`, and `DEC-032`; runtime, hardware, service, and test execution outcomes
remain unknown. | | `H-021` | Current checked-in benchmark prerequisite: resolve
`stress-ng` through the standard-library PATH lookup before cache creation,
benchmark/logger output, baseline sleep, or subprocess launch; preserve the
available-path benchmark and output behavior, and define exact missing-path
stderr/status with no traceback or side effects. | Checked-in benchmark source
and behavior-focused fake test definitions provide implementation evidence;
runtime and test execution remain unknown. | -->

## Open questions and unknowns

| ID      | Question/status                                                                                                                                                                                                                                                                                                                                                                                                                                                                                                               |
| ------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `Q-001` | Exact T2 Mac models, kernels, and distributions supported: unknown.                                                                                                                                                                                                                                                                                                                                                                                                                                                           |
| `Q-002` | Whether current hardware exposes all contracted hwmon/DRM paths: unknown; fake fixtures are required.                                                                                                                                                                                                                                                                                                                                                                                                                         |
| `Q-003` | OpenRC support and definition location: OpenRC-only direction and the checked-in `t2fand.initd` definition are settled; directives/runtime remain unverified.                                                                                                                                                                                                                                                                                                                                                                 |
| `Q-004` | Historical remote Git revision/checksum: unknown and out of scope; the current `PKGBUILD` source list is local.                                                                                                                                                                                                                                                                                                                                                                                                               |
| `Q-005` | Valid numeric threshold ranges beyond finite `low_temp < high_temp`: unknown; no universal temperature range is invented.                                                                                                                                                                                                                                                                                                                                                                                                     |
| `Q-006` | Abrupt-failure hardware state: cleanup is best effort and outcome remains unknown.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `Q-007` | Live configuration reload: not supported; restart is required.                                                                                                                                                                                                                                                                                                                                                                                                                                                                |
| `Q-008` | Authorized runtime fixture/hardware thresholds: no execution in this task; later project-native evidence required.                                                                                                                                                                                                                                                                                                                                                                                                            |
| `Q-009` | Existing workflow release `*.zip` behavior: unknown; unrelated workflow remains unchanged.                                                                                                                                                                                                                                                                                                                                                                                                                                    |
| `Q-010` | Restore systemd: no; prohibited by OpenRC-only contract.                                                                                                                                                                                                                                                                                                                                                                                                                                                                      |
| `Q-011` | Pull-request `head_commit.message` behavior: unknown; existing workflow unchanged.                                                                                                                                                                                                                                                                                                                                                                                                                                            |
| `Q-012` | Remote tag/release behavior: unknown and out of scope.                                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `Q-013` | Old selector markers: superseded by unconditional OpenRC installation.                                                                                                                                                                                                                                                                                                                                                                                                                                                        |
| `Q-014` | OpenRC version support for local filesystem, soft logger, bounded respawn, and backoff directives: definitions are checked in; version/runtime support remains unknown and must not silently degrade.                                                                                                                                                                                                                                                                                                                         |
| `Q-015` | OpenRC lifecycle, explicit stop, bounded respawn, delay, and logger delivery on supported hosts: unknown.                                                                                                                                                                                                                                                                                                                                                                                                                     |
| `Q-016` | Arch OpenRC runtime provider: no hard OpenRC dependency is guessed; `util-linux` is explicitly required for logger.                                                                                                                                                                                                                                                                                                                                                                                                           |
| `Q-017` | Prior exact package/staged result for local-source release `2.0.1-1`: unknown; the target is superseded by `REQ-075`/`REQ-058` transition to `2.0.1-2`.                                                                                                                                                                                                                                                                                                                                                                       |
| `Q-018` | Hardware cleanup after power loss, SIGKILL, kernel panic, native abort, or failed sysfs write: inherently not guaranteed; runtime result unknown.                                                                                                                                                                                                                                                                                                                                                                             |
| `Q-019` | Prior package static validation intended the historical `2.0.1-1` release, Makefile-delegated `DESTDIR` staging, exact two-file payload, and static package assertions; whether that historical validation completed successfully remains unknown. Historical checked-in tests defined fake-sysfs SMC/manual coverage; current checked-in tests reject global `manual` and cover only global `smc`/`t2fand`. Whether current tests execute successfully remains unknown; no test execution or `make test` success is claimed. |
| `Q-020` | Historical unknown: whether the established OpenRC `command_args` mechanism could safely forward conf.d path values containing whitespace. The path-forwarding contract is superseded by `REQ-076`; exact `2.0.1-2` staging/package output and all new runtime/test outcomes remain unknown.                                                                                                                                                                                                                                  |
| `Q-021` | Whether the checked-in `t2fand.confd`, `t2fand.initd`, README, CONTEXT, and tests operate consistently with `REQ-075`–`REQ-077`: implementation evidence is present; OpenRC, package/staging, runtime, and test-execution outcomes remain unknown.                                                                                                                                                                                                                                                                            |
| `Q-022` | Whether the checked-in runtime parsing/state, generated configuration, operator documentation, CONTEXT, and tests for `REQ-078`–`REQ-080`/`IF-033` produce the specified behavior and pass when executed is unknown; static source, documentation, CONTEXT, and test definitions are present and synchronized.                                                                                                                                                                                                                |
