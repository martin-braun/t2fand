import ast
import contextlib
import importlib.util
import io
import locale
import re
import shlex
import sys
import tempfile
import types
import unittest
from importlib.machinery import SourceFileLoader
from pathlib import Path
from unittest import mock


SOURCE = Path(__file__).parents[1] / "t2fand"
LOADER = SourceFileLoader("t2fand_test_subject", str(SOURCE))
SPEC = importlib.util.spec_from_loader(LOADER.name, LOADER)
MODULE = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = MODULE
LOADER.exec_module(MODULE)

BENCHMARK_SOURCE = SOURCE.parent / "t2fanbench.py"
BENCHMARK_LOADER = SourceFileLoader(
    "t2fanbench_test_subject", str(BENCHMARK_SOURCE)
)
BENCHMARK_SPEC = importlib.util.spec_from_loader(
    BENCHMARK_LOADER.name, BENCHMARK_LOADER
)
BENCHMARK = importlib.util.module_from_spec(BENCHMARK_SPEC)
sys.modules[BENCHMARK_SPEC.name] = BENCHMARK
BENCHMARK_LOADER.exec_module(BENCHMARK)


class FakeSysfs(unittest.TestCase):
    def setUp(self):
        self.stdout_capture = io.StringIO()
        self.stderr_capture = io.StringIO()
        self.output_redirects = contextlib.ExitStack()
        self.output_redirects.enter_context(
            contextlib.redirect_stdout(self.stdout_capture)
        )
        self.output_redirects.enter_context(
            contextlib.redirect_stderr(self.stderr_capture)
        )
        self.addCleanup(self._check_captured_output)

        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.hwmon = self.root / "class/hwmon"
        self.hwmon.mkdir(parents=True)
        self.fan_dir = self.root / "devices/a/b/c/d/APP0001:00"
        self.fan_dir.mkdir(parents=True)
        self._write(self.fan_dir / "fan1_min", "100")
        self._write(self.fan_dir / "fan1_max", "1000")
        self._write(self.fan_dir / "fan1_input", "400")
        self._write(self.fan_dir / "fan1_output", "0")
        self._write(self.fan_dir / "fan1_manual", "0")
        self.cpu = self.hwmon / "hwmon-cpu"
        self.cpu.mkdir()
        self._sensor(self.cpu, "cpu", 60000, "Package id 0")
        coretemp = self.root / "devices/platform/coretemp.0/hwmon"
        coretemp.mkdir(parents=True)
        (coretemp / "hwmon-cpu").symlink_to(self.cpu, target_is_directory=True)
        self.wifi = self.hwmon / "hwmon-wifi"
        self.wifi.mkdir()
        self._sensor(self.wifi, "iwlwifi", 45000, "temp1")
        self.storage = self.hwmon / "hwmon-storage"
        self.storage.mkdir()
        self._sensor(self.storage, "nvme", 70000, "Composite")
        self.drm = self.root / "class/drm/card0/device/hwmon"
        self.drm.mkdir(parents=True)
        gpu = self.root / "gpu-hwmon"
        gpu.mkdir()
        self._sensor(gpu, "amdgpu", 65000, "edge")
        (self.drm / "hwmon-gpu").symlink_to(gpu, target_is_directory=True)
        connector = (
            self.root / "class/drm/card0-DP-1/device/hwmon/hwmon-connector"
        )
        connector.mkdir(parents=True)
        self._sensor(connector, "connector", 99000, "edge")

    def tearDown(self):
        self.tempdir.cleanup()

    def _check_captured_output(self):
        self.output_redirects.close()
        leaks = []
        for name, capture in (
            ("stdout", self.stdout_capture),
            ("stderr", self.stderr_capture),
        ):
            content = capture.getvalue()
            if content:
                leaks.append(f"{name}: {content!r}")
        if leaks:
            self.fail("uncaptured output: " + "; ".join(leaks))

    @contextlib.contextmanager
    def capture_output(self):
        stdout = io.StringIO()
        stderr = io.StringIO()
        with contextlib.redirect_stdout(stdout), contextlib.redirect_stderr(
            stderr
        ):
            yield stdout, stderr

    def _write(self, path, value):
        path.write_text(str(value))

    def _sensor(self, directory, name, value, label):
        self._write(directory / "name", name)
        self._write(directory / "temp1_input", value)
        self._write(directory / "temp1_label", label)

    def set_cpu(self, value):
        self._write(self.cpu / "temp1_input", value)

    def add_t2_fan(self, name="fan2"):
        app = self.root / "devices/a/b/c/d/APP0001:00"
        app.mkdir(parents=True, exist_ok=True)
        self._write(app / f"{name}_min", "200")
        self._write(app / f"{name}_max", "1200")
        self._write(app / f"{name}_input", "500")
        self._write(app / f"{name}_output", "0")
        self._write(app / f"{name}_manual", "0")

    def fan(self):
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        self.assertEqual(1, len(fans))
        return fans[0]

    def config(self, **values):
        policy = MODULE.FanConfig(
            values.get("low", 55),
            values.get("high", 75),
            values.get("curve", "linear"),
            values.get("full", False),
        )
        return MODULE.ConfigResult([policy])


class DiscoveryTests(FakeSysfs):
    def test_global_sources_numeric_drm_and_connector_filter(self):
        snapshot = MODULE.discover_sensors(self.root)
        labels = {reading.label for reading in snapshot.readings}
        self.assertTrue(any("cpu:Package id 0" == label for label in labels))
        self.assertTrue(any("iwlwifi:temp1" == label for label in labels))
        self.assertTrue(any("nvme:Composite" == label for label in labels))
        self.assertTrue(any("amdgpu:edge" == label for label in labels))
        self.assertFalse(any("connector" in label for label in labels))
        self.assertEqual(70.0, snapshot.highest)

    def test_resolved_alias_is_read_and_reported_once(self):
        snapshot = MODULE.discover_sensors(self.root)
        cpu_readings = [
            reading for reading in snapshot.readings if reading.is_cpu
        ]
        self.assertEqual(1, len(cpu_readings))
        self.assertEqual(
            1,
            sum(
                "Package id 0" in reading.label for reading in snapshot.readings
            ),
        )

    def test_cpu_channels_need_one_positive_value_but_any_failure_is_global(
        self,
    ):
        self._write(self.cpu / "temp2_input", "0")
        self._write(self.cpu / "temp2_label", "Core 0")
        snapshot = MODULE.discover_sensors(self.root)
        self.assertEqual(
            [0.0, 60.0],
            sorted(
                reading.value for reading in snapshot.readings if reading.is_cpu
            ),
        )
        self.assertTrue(snapshot.cpu_valid)
        self.assertTrue(snapshot.valid)

        self._write(self.cpu / "temp2_input", "bad")
        snapshot = MODULE.discover_sensors(self.root)
        self.assertFalse(snapshot.valid)
        self.assertIn("temperature unavailable", snapshot.reason)
        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
        self.assertEqual("sensor-failsafe", state.mode)
        self.assertEqual((1000,), report.targets)

    def test_app0001_t2_fan_is_discovered(self):
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        self.assertEqual({"fan1", "fan2"}, {fan.name for fan in fans})

    def test_partial_discovered_fan_set_is_fatal_control_error(self):
        self.add_t2_fan()
        t2_fan = self.root / "devices/a/b/c/d/APP0001:00/fan2_max"
        self._write(t2_fan, "bad")
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual({"fan1", "fan2"}, {fan.name for fan in fans})
        self.assertEqual(
            [
                "fan2_max: unusable fan limit: invalid literal for int() with base 10: 'bad'",
                "no complete controllable fan set",
            ],
            errors,
        )

        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", self.root / "run.pid"
        ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
            MODULE, "discover_fans", return_value=(fans, errors)
        ):
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])

        fatal = "; ".join(errors)
        self.assertEqual(1, result)
        self.assertIn(f"mode=control-error reason={fatal}", stdout.getvalue())
        self.assertIn(f"critical: {fatal}", stderr.getvalue())
        fan1 = next(fan for fan in fans if fan.name == "fan1")
        self.assertEqual(
            "1000", fan1.base_path.with_name("fan1_output").read_text()
        )

    def test_no_discovered_fan_is_fatal_without_hardware(self):
        for path in self.fan_dir.iterdir():
            path.unlink()
        self.fan_dir.rmdir()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], fans)
        self.assertEqual(["no controllable fans discovered"], errors)

        pid_path = self.root / "run.pid"
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
            MODULE, "discover_fans", return_value=(fans, errors)
        ):
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])

        self.assertEqual(1, result)
        self.assertIn(
            "mode=control-error reason=no controllable fans discovered",
            stdout.getvalue(),
        )
        self.assertIn(
            "critical: no controllable fans discovered", stderr.getvalue()
        )
        self.assertFalse(pid_path.exists())

    def test_each_input_is_read_once_per_cycle(self):
        cpu_path = self.cpu / "temp1_input"
        wifi_path = self.wifi / "temp2_input"
        self._write(wifi_path, "46000")
        original = Path.read_text
        expected_paths = (cpu_path.resolve(), wifi_path.resolve())
        counts = dict.fromkeys(expected_paths, 0)

        def counted(path, *args, **kwargs):
            resolved = path.resolve()
            if resolved in counts:
                counts[resolved] += 1
            return original(path, *args, **kwargs)

        fan = self.fan()
        with mock.patch.object(Path, "read_text", counted):
            with self.capture_output():
                MODULE.run_cycle(
                    [fan],
                    self.config(),
                    MODULE.ControllerState(),
                    self.root,
                    now=0,
                )
        self.assertEqual({path: 1 for path in expected_paths}, counts)

    def test_gpu_missing_and_recovery_are_transitions(self):
        gpu_link = self.drm / "hwmon-gpu"
        gpu_link.unlink()
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=1
            )
            gpu_link.symlink_to(
                self.root / "gpu-hwmon", target_is_directory=True
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=2
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=3
            )
        self.assertEqual("", stderr.getvalue())
        text = stdout.getvalue()
        self.assertEqual(1, text.count("warning: gpu-missing"))
        self.assertEqual(1, text.count("GPU temperatures recovered"))


class SafetyTests(FakeSysfs):
    def setUp(self):
        super().setUp()
        self.fan_object = self.fan()
        self.config_result = self.config()

    def cycle(self, now=0, settings=None):
        with self.capture_output():
            return MODULE.run_cycle(
                [self.fan_object],
                self.config_result,
                self.state,
                self.root,
                now=now,
                settings=settings,
            )

    def test_cpu_missing_nonpositive_and_malformed_fail_high_immediately(self):
        self.state = MODULE.ControllerState()
        for value in ("0", "-1", "not-temperature"):
            self.set_cpu(value)
            report = self.cycle()
            self.assertEqual("sensor-failsafe", self.state.mode)
            self.assertEqual((1000,), report.targets)

    def test_absent_cpu_topology_enters_recoverable_sensor_failsafe(self):
        cpu_link = self.root / "devices/platform/coretemp.0/hwmon/hwmon-cpu"
        cpu_link.unlink()
        self.cpu.rename(self.root / "cpu-removed")
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        config = MODULE.ConfigResult(
            [self.config_result.policies[0]] * len(fans)
        )

        self.state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                fans, config, self.state, self.root, now=0
            )
        self.assertFalse(report.snapshot.cpu_valid)
        self.assertEqual(
            "required CPU temperature is missing, invalid, or unavailable",
            report.snapshot.reason,
        )
        self.assertEqual("sensor-failsafe", self.state.mode)
        self.assertTrue(self.state.recovery_active)
        self.assertEqual((1000, 1200), report.targets)
        self.assertEqual(
            [str(fan.maximum) for fan in fans],
            [
                fan.base_path.with_name(f"{fan.name}_output").read_text()
                for fan in fans
            ],
        )

    def test_non_cpu_error_and_fault_fail_high_but_cpu_is_kept(self):
        self.state = MODULE.ControllerState()
        self._write(self.wifi / "temp1_input", "bad")
        self.assertEqual((1000,), self.cycle().targets)
        self._write(self.wifi / "temp1_input", "45000")
        self._write(self.storage / "temp1_fault", "1")
        self.assertEqual((1000,), self.cycle(1).targets)

    def test_ambient_non_cpu_value_is_valid_and_hottest_wins(self):
        self.state = MODULE.ControllerState()
        self._write(self.storage / "temp1_input", "0")
        report = self.cycle()
        self.assertTrue(report.snapshot.valid)
        self.assertEqual(65.0, report.snapshot.highest)

    def test_sensor_recovery_requires_five_cycles_and_resets_history(self):
        self.state = MODULE.ControllerState(history=[99.0])
        self.set_cpu("bad")
        self.cycle()
        self.set_cpu("40000")
        for index in range(5):
            report = self.cycle(index + 1)
            self.assertEqual((1000,), report.targets)
        self.assertFalse(self.state.recovery_active)
        self.assertEqual([70.0] * 5, self.state.history)
        report = self.cycle(6)
        self.assertEqual(70.0, report.rolling_mean)

    def test_runtime_overrides_change_recovery_sample_and_reminder_behavior(
        self,
    ):
        settings = MODULE.RuntimeSettings(2, 2, 1.5)
        self.state = MODULE.ControllerState()
        self.set_cpu("bad")
        self.cycle(0, settings=settings)

        for now, cpu_value in ((1, "70000"), (2, "60000"), (3, "50000")):
            self.set_cpu(cpu_value)
            for sensor in (self.wifi, self.storage, self.root / "gpu-hwmon"):
                self._write(sensor / "temp1_input", "40000")
            report = self.cycle(now, settings=settings)

        self.assertFalse(self.state.recovery_active)
        self.assertEqual(2, self.state.recovery_cycles)
        self.assertEqual([60.0, 50.0], self.state.history)
        self.assertEqual(55.0, report.rolling_mean)
        self.assertEqual(2, self.state.sensor_recovery_cycles)
        self.assertEqual(2, self.state.sample_limit)

        reminder_state = MODULE.ControllerState()
        self.set_cpu("bad")
        with self.capture_output() as (stdout, stderr):
            for now in (0, 0.5, 1.5):
                MODULE.run_cycle(
                    [self.fan_object],
                    self.config_result,
                    reminder_state,
                    self.root,
                    now=now,
                    settings=settings,
                )
        self.assertEqual(
            1, stdout.getvalue().count("warning: mode=sensor-failsafe")
        )
        self.assertEqual("", stderr.getvalue())

    def test_interrupted_sensor_recovery_restarts_at_zero(self):
        self.state = MODULE.ControllerState(history=[99.0])
        self.set_cpu("bad")
        self.cycle(0)
        self.set_cpu("40000")
        for now in range(1, 4):
            self.cycle(now)
        self.assertEqual(3, self.state.recovery_cycles)
        self.assertEqual([70.0] * 3, self.state.recovery_history)

        self.set_cpu("bad")
        self.cycle(4)
        self.assertTrue(self.state.recovery_active)
        self.assertEqual(0, self.state.recovery_cycles)
        self.assertEqual([], self.state.history)
        self.assertEqual([], self.state.recovery_history)

        self.set_cpu("40000")
        for now in range(5, 10):
            self.cycle(now)
        self.assertFalse(self.state.recovery_active)
        self.assertEqual([70.0] * 5, self.state.history)
        self.assertEqual(70.0, self.cycle(10).rolling_mean)

    def test_actual_rpm_failure_fails_high_without_sensor_recovery(self):
        self.state = MODULE.ControllerState()
        self._write(self.storage / "temp1_input", "60000")
        self._write(
            self.fan_object.base_path.with_name(
                f"{self.fan_object.name}_input"
            ),
            "bad",
        )
        report = self.cycle()
        self.assertEqual((1000,), report.targets)
        self.assertEqual((None,), report.actual_rpm)
        self.assertIsNone(report.rolling_mean)
        self.assertFalse(self.state.recovery_active)
        self.assertEqual("sensor-failsafe", self.state.mode)

    def test_fatal_maximum_write_is_reported(self):
        self.state = MODULE.ControllerState()
        output = self.fan_object.base_path.with_name(
            f"{self.fan_object.name}_output"
        )
        output.unlink()
        output.mkdir()
        with self.assertRaises(MODULE.FatalControlError):
            self.cycle()


class CurveAndConfigTests(FakeSysfs):
    def test_thresholds_and_all_legacy_curves(self):
        fan = MODULE.Fan(self.root / "fan", 100, 1000)
        for curve, expected in (
            ("linear", 550),
            ("exponential", 212),
            ("logarithmic", 791),
        ):
            policy = MODULE.FanConfig(55, 75, curve, False)
            self.assertEqual(100, MODULE.calculate_target(fan, policy, 55))
            self.assertEqual(1000, MODULE.calculate_target(fan, policy, 75))
            self.assertEqual(expected, MODULE.calculate_target(fan, policy, 65))

    def test_config_generation_defaults_and_case_insensitive_boolean(self):
        path = self.root / "etc/t2fand.conf"
        path.parent.mkdir()
        result = MODULE.load_configuration(path, 1)
        self.assertTrue(result.valid)
        self.assertEqual(
            (55, 75, "linear", False),
            (
                result.policies[0].low_temp,
                result.policies[0].high_temp,
                result.policies[0].speed_curve,
                result.policies[0].always_full_speed,
            ),
        )
        text = path.read_text().replace("false", " TrUe ")
        path.write_text(text)
        self.assertTrue(
            MODULE.load_configuration(path, 1).policies[0].always_full_speed
        )

    def assert_config_defect(self, contents, expected):
        path = self.root / "config"
        path.write_text(contents)
        original = path.read_text()
        result = MODULE.load_configuration(path, 1)
        self.assertFalse(result.valid)
        self.assertEqual([expected], result.errors)
        self.assertEqual(original, path.read_text())

        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], result, state, self.root, now=0
            )
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual((1000,), report.targets)

    def test_config_defects_select_global_failsafe_with_precise_diagnostics(
        self,
    ):
        cases = (
            (
                "[Fan2]\n",
                "Fan1 section is missing",
            ),
            (
                "[Fan1]\nhigh_temp=75\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.low_temp is missing",
            ),
            (
                "[Fan1]\nlow_temp=55\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.high_temp is missing",
            ),
            (
                "[Fan1]\nlow_temp=55\nhigh_temp=75\nalways_full_speed=false\n",
                "Fan1.speed_curve is missing",
            ),
            (
                "[Fan1]\nlow_temp=55\nhigh_temp=75\nspeed_curve=linear\n",
                "Fan1.always_full_speed is missing",
            ),
            (
                "[Fan1]\nlow_temp=bad\nhigh_temp=75\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.low_temp is malformed",
            ),
            (
                "[Fan1]\nlow_temp=nan\nhigh_temp=75\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.low_temp must be finite",
            ),
            (
                "[Fan1]\nlow_temp=55\nhigh_temp=inf\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.high_temp must be finite",
            ),
            (
                "[Fan1]\nlow_temp=75\nhigh_temp=55\nspeed_curve=linear\nalways_full_speed=false\n",
                "Fan1.low_temp must be lower than high_temp",
            ),
            (
                "[Fan1]\nlow_temp=55\nhigh_temp=75\nspeed_curve=bad\nalways_full_speed=false\n",
                "Fan1.speed_curve is invalid",
            ),
            (
                "[Fan1]\nlow_temp=55\nhigh_temp=75\nspeed_curve=linear\nalways_full_speed=maybe\n",
                "Fan1.always_full_speed must be true or false",
            ),
        )
        for contents, expected in cases:
            with self.subTest(expected=expected):
                self.assert_config_defect(contents, expected)

    def test_unreadable_config_is_startup_error(self):
        path = self.root / "config"
        path.mkdir()
        result = MODULE.load_configuration(path, 1)
        self.assertFalse(result.valid)
        self.assertEqual(1, len(result.errors))
        self.assertTrue(
            result.errors[0].startswith(f"{path}: cannot read config: ")
        )

        with self.assertRaises(MODULE.StartupError):
            MODULE.run_cycle(
                [self.fan()], result, MODULE.ControllerState(), self.root, now=0
            )

    def test_config_generation_io_failure_is_startup_error(self):
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        path = self.root / "config"
        diagnostic = f"{path}: cannot generate config: read-only filesystem"
        with mock.patch.object(
            Path, "open", side_effect=OSError("read-only filesystem")
        ):
            result = MODULE.load_configuration(path, len(fans))

        self.assertFalse(result.valid)
        self.assertEqual([diagnostic], result.errors)
        with self.assertRaises(MODULE.StartupError):
            MODULE.run_cycle(
                fans, result, MODULE.ControllerState(), self.root, now=0
            )

    def test_malformed_ini_is_startup_error(self):
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        path = self.root / "config"
        contents = "[Fan1\nlow_temp=55\n"
        path.write_text(contents)
        result = MODULE.load_configuration(path, len(fans))
        self.assertFalse(result.valid)
        self.assertEqual(1, len(result.errors))
        self.assertTrue(
            result.errors[0].startswith(f"{path}: cannot read config: ")
        )

        with self.assertRaises(MODULE.StartupError):
            MODULE.run_cycle(
                fans, result, MODULE.ControllerState(), self.root, now=0
            )

    def test_runtime_calculation_failure_persists_config_failsafe(self):
        policy = MODULE.FanConfig(55, 56, "logarithmic", False)
        config = MODULE.ConfigResult([policy])
        for sensor in (self.cpu, self.storage, self.root / "gpu-hwmon"):
            self._write(sensor / "temp1_input", "55500")
        self._write(self.wifi / "temp1_input", "55500")
        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], config, state, self.root, now=0
            )
        self.assertTrue(state.config_failsafe)
        self.assertEqual("config-failsafe", state.mode)
        self.assertIn("unsafe fan policy calculation", state.reason)
        self.assertEqual((1000,), report.targets)

        for sensor in (self.cpu, self.storage):
            self._write(sensor / "temp1_input", "40000")
        self._write(self.wifi / "temp1_input", "40000")
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], config, state, self.root, now=1
            )
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual((1000,), report.targets)

    def test_config_failsafe_is_global_and_configured_full_is_distinct(self):
        fan = self.fan()
        invalid = MODULE.ConfigResult(
            [None], ["Fan1.always_full_speed must be true or false"]
        )
        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle([fan], invalid, state, self.root, now=0)
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual((1000,), report.targets)
        state = MODULE.ControllerState()
        full = self.config(full=True)
        with self.capture_output():
            report = MODULE.run_cycle([fan], full, state, self.root, now=0)
        self.assertEqual("configured-full", state.mode)
        self.assertEqual((1000,), report.targets)
        self.assertIsNone(report.rolling_mean)


class ControlModeTests(FakeSysfs):
    def smc_config(self, policy=None):
        return MODULE.ConfigResult(
            [policy], general=MODULE.GeneralConfig("smc")
        )

    def test_generated_config_selects_smc_and_general_is_first(self):
        path = self.root / "etc/t2fand.conf"
        path.parent.mkdir()
        result = MODULE.load_configuration(path, 1)
        self.assertEqual("smc", result.control_mode)
        self.assertTrue(result.valid)
        self.assertTrue(path.read_text().startswith("[General]\n"))
        self.assertIn("control_mode = smc", path.read_text())
        self.assertIn("[Fan1]", path.read_text())

    def test_legacy_config_selects_t2fand_and_warns_without_rewrite(self):
        path = self.root / "legacy.conf"
        contents = (
            "[Fan1]\nlow_temp=55\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
        )
        path.write_text(contents)
        result = MODULE.load_configuration(path, 1)
        self.assertEqual("t2fand", result.control_mode)
        self.assertEqual(
            ["legacy configuration without [General]; using t2fand mode"],
            result.warnings,
        )
        self.assertEqual(contents, path.read_text())

    def test_explicit_smc_releases_verifies_and_never_writes_output(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_manual").write_text("1")
        fan.base_path.with_name("fan1_output").write_text("321")
        MODULE.release_smc_ownership([fan])
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )
        report = self.cycle_smc()
        self.assertEqual((0,), report.manual)
        self.assertEqual((321,), report.targets)
        self.assertEqual(
            "321", fan.base_path.with_name("fan1_output").read_text()
        )

    def test_smc_startup_releases_manual_before_running(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_manual").write_text("1")
        fan.base_path.with_name("fan1_output").write_text("321")
        path = self.root / "config"
        path.write_text(
            "[General]\ncontrol_mode=smc\n[Fan1]\n"
            "low_temp=bad\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
        )
        pid_path = self.root / "run.pid"

        def stop_loop(*args, **kwargs):
            del args, kwargs

        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(
            MODULE, "DEFAULT_CONFIG_PATH", path
        ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
            MODULE, "discover_fans", return_value=([fan], [])
        ), mock.patch.object(
            MODULE, "install_signal_handlers"
        ), mock.patch.object(MODULE, "run_loop", side_effect=stop_loop):
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])
        self.assertEqual(0, result)
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )
        self.assertEqual(
            "321", fan.base_path.with_name("fan1_output").read_text()
        )
        self.assertIn(
            "configuration warning: Fan1.low_temp is malformed",
            stderr.getvalue(),
        )
        self.assertIn("stopped:", stdout.getvalue())

    def cycle_smc(self, state=None, now=0):
        state = state or MODULE.ControllerState()
        with self.capture_output():
            return MODULE.run_cycle(
                [self.fan()], self.smc_config(), state, self.root, now=now
            )

    def test_smc_sensor_failure_degrades_without_takeover(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_output").write_text("321")
        self.set_cpu("bad")
        state = MODULE.ControllerState()
        report = self.cycle_smc(state)
        self.assertEqual("smc", state.mode)
        self.assertEqual("smc-degraded", state.control_status)
        self.assertEqual((0,), report.manual)
        self.assertEqual(
            "321", fan.base_path.with_name("fan1_output").read_text()
        )

    def test_powered_dgpu_failure_degrades_smc_without_output_takeover(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_output").write_text("321")
        self._write(self.root / "gpu-hwmon/temp1_input", "bad")
        state = MODULE.ControllerState()
        report = self.cycle_smc(state)
        self.assertEqual("smc-degraded", state.control_status)
        self.assertIsNone(
            next(
                reading.value
                for reading in report.snapshot.readings
                if reading.is_gpu
            ),
        )
        with self.capture_output() as (stdout, stderr):
            MODULE.emit_verbose(report, [fan], self.smc_config(), state)
        self.assertIn("amdgpu:edge=unknown", stdout.getvalue())
        self.assertIn("sensor_status=degraded", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(
            "321", fan.base_path.with_name("fan1_output").read_text()
        )

    def test_smc_reports_observational_target_and_telemetry_without_verbose(
        self,
    ):
        fan = self.fan()
        fan.base_path.with_name("fan1_output").write_text("321")
        state = MODULE.ControllerState()
        sleeps = []

        def sleeper(seconds):
            sleeps.append(seconds)
            state.shutdown_requested = True

        with self.capture_output() as (stdout, stderr):
            MODULE.run_loop(
                [fan], self.smc_config(), state, self.root, sleeper=sleeper
            )
        text = stdout.getvalue()
        self.assertEqual([1], sleeps)
        self.assertIn(
            "telemetry highest=nvme:Composite highest_temp=70.0", text
        )
        self.assertIn("fan1 actual_rpm=400", text)
        self.assertNotIn("control_mode=smc", text)
        self.assertEqual("", stderr.getvalue())

    def test_smc_verbose_flag_emits_full_telemetry(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_output").write_text("321")
        state = MODULE.ControllerState()
        verbose = MODULE._parser().parse_args(["-v"]).verbose

        def sleeper(seconds):
            del seconds
            state.shutdown_requested = True

        with self.capture_output() as (stdout, stderr):
            MODULE.run_loop(
                [fan],
                self.smc_config(),
                state,
                self.root,
                verbose=verbose,
                sleeper=sleeper,
            )

        text = stdout.getvalue()
        self.assertIn("control_mode=smc", text)
        self.assertIn("sensors=", text)
        self.assertIn("fan1 manual=0 target_rpm=321 actual_rpm=400", text)
        self.assertNotIn("low_temp=", text)
        self.assertNotIn("rolling_mean=", text)
        self.assertEqual("", stderr.getvalue())

    def test_t2fand_default_output_is_compact_and_verbose_output_is_full(self):
        fan = self.fan()
        state = MODULE.ControllerState()
        sleeps = []

        def sleeper(seconds):
            sleeps.append(seconds)
            state.shutdown_requested = True

        with self.capture_output() as (stdout, stderr):
            MODULE.run_loop(
                [fan], self.config(), state, self.root, sleeper=sleeper
            )
        compact = stdout.getvalue()
        self.assertEqual([1], sleeps)
        self.assertIn("highest=nvme:Composite highest_temp=70.0", compact)
        self.assertIn("fan1 actual_rpm=400", compact)
        self.assertNotIn("sensors=", compact)
        self.assertEqual("", stderr.getvalue())

        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            MODULE.run_loop(
                [fan],
                self.config(),
                state,
                self.root,
                verbose=True,
                sleeper=lambda seconds: setattr(
                    state, "shutdown_requested", True
                ),
            )
        self.assertIn("sensors=", stdout.getvalue())
        self.assertIn("highest=nvme:Composite", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_hottest_sensor_label_is_first_on_equal_valid_values(self):
        for sensor in (
            self.cpu,
            self.wifi,
            self.storage,
            self.root / "gpu-hwmon",
        ):
            self._write(sensor / "temp1_input", "60000")
        snapshot = MODULE.discover_sensors(self.root)
        self.assertEqual("cpu:Package id 0", snapshot.highest_label)
        self.assertEqual(60.0, snapshot.highest)

    def test_no_valid_hottest_is_unknown_in_compact_telemetry(self):
        for sensor in (
            self.cpu,
            self.wifi,
            self.storage,
            self.root / "gpu-hwmon",
        ):
            self._write(sensor / "temp1_input", "bad")
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            report = MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
            MODULE.emit_compact(report, [self.fan()])
        telemetry = next(
            line
            for line in stdout.getvalue().splitlines()
            if line.startswith("telemetry ")
        )
        self.assertEqual(
            "telemetry highest=unknown highest_temp=unknown fan1 actual_rpm=400",
            telemetry,
        )
        self.assertIsNone(report.snapshot.highest)
        self.assertEqual("", stderr.getvalue())

    def test_faulted_and_skipped_sensors_are_excluded_from_hottest(self):
        self._write(self.storage / "temp1_input", "90000")
        self._write(self.storage / "temp1_fault", "1")
        gpu_link = self.drm / "hwmon-gpu"
        gpu_link.unlink()
        gpu = self.root / "pci/0000:01:00.0/gpu-hwmon"
        gpu.mkdir(parents=True)
        self._sensor(gpu, "amdgpu", 100000, "edge")
        gpu_link.symlink_to(gpu, target_is_directory=True)
        switch = self.root / "kernel/debug/vgaswitcheroo/switch"
        switch.parent.mkdir(parents=True)
        switch.write_text("1:DIS:0000:Off:0000:01:00.0\n")

        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            report = MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
            MODULE.emit_compact(report, [self.fan()])

        self.assertEqual("cpu:Package id 0", report.snapshot.highest_label)
        self.assertEqual(60.0, report.snapshot.highest)
        self.assertTrue(
            any(
                reading.error
                and "fault" in reading.error
                and reading.value is None
                for reading in report.snapshot.readings
            )
        )
        self.assertTrue(
            any(
                reading.error == "dGPU powered off; skipped"
                for reading in report.snapshot.readings
            )
        )
        self.assertIn(
            "telemetry highest=cpu:Package id 0 highest_temp=60.0",
            stdout.getvalue(),
        )
        self.assertEqual("", stderr.getvalue())

    def test_compact_output_reports_unknown_rpm(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_input").write_text("bad")
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            report = MODULE.run_cycle(
                [fan], self.config(), state, self.root, now=0
            )
            MODULE.emit_compact(report, [fan])
        self.assertIn(
            "highest=nvme:Composite highest_temp=70.0", stdout.getvalue()
        )
        self.assertIn("fan1 actual_rpm=unknown", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_smc_healthy_state_stays_quiet_but_degraded_reminders_remain(self):
        fan = self.fan()
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            MODULE.run_cycle([fan], self.smc_config(), state, self.root, now=0)
            self.assertEqual("smc-auto", state.control_status)
            MODULE.run_cycle([fan], self.smc_config(), state, self.root, now=61)
            self.assertEqual("smc-auto", state.control_status)

            self.set_cpu("bad")
            MODULE.run_cycle([fan], self.smc_config(), state, self.root, now=62)
            MODULE.run_cycle(
                [fan], self.smc_config(), state, self.root, now=122
            )

        self.assertEqual("smc-degraded", state.control_status)
        self.assertEqual("", stderr.getvalue())
        text = stdout.getvalue()
        self.assertNotIn("warning: mode=smc reason=SMC monitoring", text)
        self.assertEqual(1, text.count("warning: mode=smc"))

    def test_smc_restores_unexpected_manual_takeover(self):
        fan = self.fan()
        fan.base_path.with_name("fan1_manual").write_text("1")
        state = MODULE.ControllerState()
        with self.capture_output() as (_, stderr):
            MODULE.run_cycle([fan], self.smc_config(), state, self.root, now=0)
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )
        self.assertIn("unexpected manual=1", stderr.getvalue())

    def test_smc_recovers_from_unreadable_or_malformed_manual_read(self):
        fan = self.fan()
        manual = fan.base_path.with_name("fan1_manual")
        output = fan.base_path.with_name("fan1_output")
        for failure in (OSError("unreadable"), ValueError("malformed")):
            with self.subTest(failure=type(failure).__name__):
                manual.write_text("1")
                output.write_text("321")
                state = MODULE.ControllerState()
                with mock.patch.object(
                    fan, "read_manual", side_effect=[failure, 0]
                ), self.capture_output() as (_, stderr):
                    report = MODULE.run_cycle(
                        [fan], self.smc_config(), state, self.root, now=0
                    )
                self.assertEqual("smc", state.mode)
                self.assertEqual("smc-auto", state.control_status)
                self.assertEqual((0,), report.manual)
                self.assertEqual("0", manual.read_text())
                self.assertEqual("321", output.read_text())
                self.assertIn("restoring SMC ownership", stderr.getvalue())

    def test_smc_failed_restore_escalates_maximum_and_control_error(self):
        fan = self.fan()
        manual = fan.base_path.with_name("fan1_manual")
        manual.unlink()
        manual.mkdir()
        state = MODULE.ControllerState()
        with self.assertRaises(MODULE.FatalControlError):
            self.cycle_smc(state)
        self.assertEqual("control-error", state.mode)
        self.assertEqual(
            "1000", fan.base_path.with_name("fan1_output").read_text()
        )
        self.assertNotEqual("smc-auto", state.control_status)

    def test_dgpu_off_skips_matching_sensor_and_reports_state(self):
        gpu_link = self.drm / "hwmon-gpu"
        gpu_link.unlink()
        gpu = self.root / "pci/0000:01:00.0/gpu-hwmon"
        gpu.mkdir(parents=True)
        self._sensor(gpu, "amdgpu", 65000, "edge")
        gpu_link.symlink_to(gpu, target_is_directory=True)
        igpu = self.root / "igpu-hwmon"
        igpu.mkdir()
        self._sensor(igpu, "i915", 50000, "Package")
        igpu_link = self.root / "class/drm/card1/device/hwmon/hwmon-igpu"
        igpu_link.parent.mkdir(parents=True)
        igpu_link.symlink_to(igpu, target_is_directory=True)
        switch = self.root / "kernel/debug/vgaswitcheroo/switch"
        switch.parent.mkdir(parents=True)
        switch.write_text("1:DIS:0000:On:0000:01:00.0\n")
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            MODULE.run_cycle(
                [self.fan()], self.smc_config(), state, self.root, now=0
            )
            switch.write_text("1:DIS:0000:Off:0000:01:00.0\n")
            report = MODULE.run_cycle(
                [self.fan()], self.smc_config(), state, self.root, now=1
            )
        snapshot = report.snapshot
        gpu_reading = next(
            reading
            for reading in snapshot.readings
            if reading.error == "dGPU powered off; skipped"
        )
        self.assertEqual("dGPU powered off; skipped", gpu_reading.error)
        self.assertEqual("off", snapshot.dgpu_state)
        self.assertTrue(snapshot.gpu_present)
        self.assertTrue(
            any(
                reading.label == "i915:Package" and reading.value == 50.0
                for reading in snapshot.readings
            )
        )
        self.assertTrue(snapshot.valid)
        self.assertTrue(state.gpu_present)
        self.assertNotIn("gpu-missing", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_smc_tachometer_failure_degrades_without_takeover(self):
        fan = self.fan()
        output = fan.base_path.with_name("fan1_output")
        output.write_text("321")
        self._write(fan.base_path.with_name("fan1_input"), "bad")
        state = MODULE.ControllerState()
        report = self.cycle_smc(state)
        self.assertEqual("smc-degraded", state.control_status)
        self.assertEqual((None,), report.actual_rpm)
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )
        self.assertEqual("321", output.read_text())
        with self.capture_output() as (stdout, stderr):
            MODULE.emit_verbose(report, [fan], self.smc_config(), state)
        self.assertIn("sensor_status=degraded", stdout.getvalue())
        self.assertEqual("", stderr.getvalue())

    def test_malformed_smc_policy_warns_but_t2fand_mode_fails_high(self):
        path = self.root / "config"
        path.write_text(
            "[General]\ncontrol_mode=smc\n[Fan1]\n"
            "low_temp=bad\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
        )
        result = MODULE.load_configuration(path, 1)
        self.assertTrue(result.valid)
        self.assertIn("Fan1.low_temp is malformed", result.warnings)
        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], result, state, self.root, now=0
            )
        self.assertEqual((0,), report.manual)
        self.assertEqual(
            "0", self.fan().base_path.with_name("fan1_output").read_text()
        )
        path.write_text(
            "[General]\ncontrol_mode=t2fand\n[Fan1]\n"
            "low_temp=bad\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
        )
        t2fand_result = MODULE.load_configuration(path, 1)
        self.assertFalse(t2fand_result.valid)
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()],
                t2fand_result,
                MODULE.ControllerState(),
                self.root,
                now=1,
            )
        self.assertEqual((1000,), report.targets)

    def test_clean_shutdown_release_works_in_both_modes(self):
        fan = self.fan()
        fan.enable_manual()
        MODULE.cleanup_fans([fan])
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )
        fan.base_path.with_name("fan1_manual").write_text("1")
        MODULE.cleanup_fans([fan])
        self.assertEqual(
            "0", fan.base_path.with_name("fan1_manual").read_text()
        )

    def test_verbose_flag_remains_accepted(self):
        parser = MODULE._parser()
        self.assertTrue(parser.parse_args(["--verbose"]).verbose)
        self.assertIn("emit full telemetry", parser.format_help())
        self.assertNotIn(
            "one telemetry record per second", parser.format_help()
        )

    def test_cli_defaults_and_runtime_values_are_local(self):
        args = MODULE._parser().parse_args([])
        self.assertEqual(MODULE.DEFAULT_CONFIG_PATH, args.config_path)
        self.assertEqual(MODULE.DEFAULT_PID_PATH, args.pid_path)
        self.assertEqual(MODULE.DEFAULT_SYSFS_ROOT, args.sysfs_path)
        self.assertEqual(5, args.sensor_recovery_cycles)
        self.assertEqual(5, args.sample_limit)
        self.assertEqual(60.0, args.error_reminder_seconds)

        state = MODULE.ControllerState()
        with self.capture_output():
            MODULE.run_cycle(
                [self.fan()],
                self.config(),
                state,
                self.root,
                now=0,
                settings=MODULE.RuntimeSettings(2, 2, 1.5),
            )
        self.assertEqual(2, state.sensor_recovery_cycles)
        self.assertEqual(2, state.sample_limit)
        self.assertEqual(1.5, state.error_reminder_seconds)
        self.assertEqual(5, MODULE.SENSOR_RECOVERY_CYCLES)
        self.assertEqual(5, MODULE.SAMPLE_LIMIT)
        self.assertEqual(60.0, MODULE.ERROR_REMINDER_SECONDS)

    def test_cli_short_forms_match_long_forms_and_help_defaults(self):
        parser = MODULE._parser()
        options = (
            (
                "-c",
                "--config-path",
                "custom.conf",
                "config_path",
                Path("custom.conf"),
                "/etc/t2fand.conf",
            ),
            (
                "-p",
                "--pid-path",
                "custom.pid",
                "pid_path",
                Path("custom.pid"),
                "/run/t2fand.pid",
            ),
            ("-s", "--sysfs-path", "sys", "sysfs_path", Path("sys"), "/sys"),
            (
                "-r",
                "--sensor-recovery-cycles",
                "7",
                "sensor_recovery_cycles",
                7,
                "5",
            ),
            ("-l", "--sample-limit", "9", "sample_limit", 9, "5"),
            (
                "-e",
                "--error-reminder-seconds",
                "2.5",
                "error_reminder_seconds",
                2.5,
                "60.0",
            ),
        )
        with self.capture_output() as (stdout, stderr):
            with self.assertRaises(SystemExit) as exit_info:
                parser.parse_args(["--help"])
        self.assertEqual(0, exit_info.exception.code)
        self.assertEqual("", stderr.getvalue())
        help_text = stdout.getvalue()
        for short, long, value, dest, expected, default in options:
            with self.subTest(option=short):
                short_args = parser.parse_args([short, value])
                long_args = parser.parse_args([long, value])
                self.assertEqual(vars(long_args), vars(short_args))
                self.assertEqual(expected, getattr(short_args, dest))
                self.assertIn(short, help_text)
                self.assertIn(long, help_text)
                self.assertIn(f"(default: {default})", help_text)

    def test_cli_numeric_validation_precedes_root_check(self):
        for option, value in (
            ("--sensor-recovery-cycles", "0"),
            ("--sample-limit", "-1"),
            ("--sensor-recovery-cycles", "not-an-int"),
            ("--error-reminder-seconds", "0"),
            ("--error-reminder-seconds", "-0.5"),
            ("--error-reminder-seconds", "not-a-float"),
            ("--error-reminder-seconds", "nan"),
            ("--error-reminder-seconds", "inf"),
        ):
            with self.subTest(option=option, value=value), mock.patch.object(
                MODULE.os, "geteuid"
            ) as geteuid:
                with self.capture_output():
                    with self.assertRaises(SystemExit):
                        MODULE.main([option, value])
            geteuid.assert_not_called()

    def test_main_consumes_custom_paths_and_cleans_custom_pid(self):
        pid_path = self.root / "run/custom.pid"
        config_path = self.root / "etc/custom.conf"
        settings = MODULE.ConfigResult([self.config().policies[0]])
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "prepare_pid"
        ) as prepare_pid, mock.patch.object(
            MODULE, "discover_fans", return_value=([self.fan()], [])
        ) as discover_fans, mock.patch.object(
            MODULE, "load_configuration", return_value=settings
        ) as load_configuration, mock.patch.object(
            MODULE, "install_signal_handlers"
        ), mock.patch.object(
            MODULE, "write_pid"
        ) as write_pid, mock.patch.object(
            MODULE, "run_loop"
        ) as run_loop, mock.patch.object(MODULE, "remove_pid") as remove_pid:
            with self.capture_output():
                result = MODULE.main(
                    [
                        "--config-path",
                        str(config_path),
                        "--pid-path",
                        str(pid_path),
                        "--sysfs-path",
                        str(self.root),
                        "--sensor-recovery-cycles",
                        "2",
                        "--sample-limit",
                        "3",
                        "--error-reminder-seconds",
                        "4.5",
                    ]
                )
        self.assertEqual(0, result)
        prepare_pid.assert_called_once_with(pid_path)
        discover_fans.assert_called_once_with(self.root)
        load_configuration.assert_called_once_with(config_path, 1)
        write_pid.assert_called_once_with(pid_path)
        remove_pid.assert_called_once_with(pid_path)
        run_settings = run_loop.call_args.kwargs["settings"]
        self.assertEqual(MODULE.RuntimeSettings(2, 3, 4.5), run_settings)

    def test_invalid_general_mode_is_startup_control_error_without_mutation(
        self,
    ):
        fan = self.fan()
        cases = (
            (
                "manual",
                "[General]\ncontrol_mode=manual\n",
                "must be smc or t2fand",
            ),
            ("auto", "[General]\ncontrol_mode=auto\n", "must be smc or t2fand"),
            (
                "smc_auto",
                "[General]\ncontrol_mode=smc_auto\n",
                "must be smc or t2fand",
            ),
            ("SMC", "[General]\ncontrol_mode=SMC\n", "must be smc or t2fand"),
            ("missing", "[General]\n", "is missing"),
            (
                "arbitrary",
                "[General]\ncontrol_mode=invalid\n",
                "must be smc or t2fand",
            ),
        )
        for value, contents, expected in cases:
            with self.subTest(value=value):
                path = self.root / "config"
                path.write_text(contents)
                with mock.patch.object(
                    MODULE.os, "geteuid", return_value=0
                ), mock.patch.object(
                    MODULE, "DEFAULT_PID_PATH", self.root / "run.pid"
                ), mock.patch.object(
                    MODULE, "DEFAULT_CONFIG_PATH", path
                ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
                    MODULE, "discover_fans", return_value=([fan], [])
                ):
                    with self.capture_output() as (stdout, stderr):
                        result = MODULE.main([])
                self.assertEqual(1, result)
                self.assertIn("control-error", stdout.getvalue())
                self.assertIn(
                    f"General.control_mode {expected}", stderr.getvalue()
                )
                if value != "missing":
                    self.assertNotIn(value, stderr.getvalue())
                self.assertEqual(
                    "0", fan.base_path.with_name("fan1_manual").read_text()
                )
                self.assertEqual(
                    "0", fan.base_path.with_name("fan1_output").read_text()
                )


class OutputAndLifecycleTests(FakeSysfs):
    def test_emit_routes_and_flushes_output(self):
        with self.capture_output() as (stdout, stderr):
            MODULE.emit("ordinary")
            MODULE.emit("error", error=True)
        self.assertEqual("ordinary\n", stdout.getvalue())
        self.assertEqual("error\n", stderr.getvalue())

        explicit = mock.Mock(wraps=io.StringIO())
        MODULE.emit("explicit", stream=explicit)
        self.assertEqual("explicit\n", explicit._mock_wraps.getvalue())
        explicit.flush.assert_called_once_with()

    def test_mode_transitions_rate_limit_and_quiet_repeats(self):
        state = MODULE.ControllerState()
        with self.capture_output() as (stdout, stderr):
            MODULE._set_mode(state, "sensor-failsafe", "sensor error", 0)
            MODULE._set_mode(state, "sensor-failsafe", "sensor error", 1)
            MODULE._set_mode(state, "sensor-failsafe", "sensor error", 60)
            MODULE._set_mode(state, "curve", "normal temperature control", 61)
            MODULE._set_mode(state, "curve", "normal temperature control", 120)
            MODULE._set_mode(
                state, "configured-full", "always_full_speed=true", 121
            )
            MODULE._set_mode(
                state, "configured-full", "always_full_speed=true", 180
            )
        text = stdout.getvalue()
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(3, text.count("mode transition:"))
        self.assertEqual(1, text.count("warning: mode=sensor-failsafe"))
        self.assertNotIn("warning: mode=curve", text)
        self.assertNotIn("warning: mode=configured-full", text)

    def test_verbose_record_has_all_sensor_policy_and_rpm_fields(self):
        fan = self.fan()
        state = MODULE.ControllerState()
        config = self.config()
        with self.capture_output() as (_, cycle_stderr):
            report = MODULE.run_cycle([fan], config, state, self.root, now=0)
        self.assertEqual("", cycle_stderr.getvalue())
        with self.capture_output() as (output, stderr):
            MODULE.emit_verbose(report, [fan], config, state)
        self.assertEqual("", stderr.getvalue())
        text = output.getvalue()
        for field in (
            "control_mode=t2fand",
            "iwlwifi:temp1=45.0",
            "nvme:Composite=70.0",
            "gpu_temps=present",
            "highest=nvme:Composite",
            "highest_temp=70.0",
            "rolling_mean=70.0",
            "mode=curve",
            "low_temp=55",
            "high_temp=75",
            "curve=linear",
            "always_full_speed=false",
            "target_rpm=775",
            "actual_rpm=400",
        ):
            self.assertIn(field, text)

    def test_recovery_reason_is_stable_in_default_output(self):
        self.set_cpu("bad")
        state = MODULE.ControllerState()
        with self.capture_output() as (_, stderr):
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
        self.assertEqual("", stderr.getvalue())
        self.set_cpu("40000")
        with self.capture_output() as (output, stderr):
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=1
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=2
            )
        self.assertEqual("", stderr.getvalue())
        text = output.getvalue()
        self.assertEqual(1, text.count("mode transition: mode=sensor-failsafe"))
        self.assertEqual("waiting for valid sensor recovery", state.reason)

    def test_verbose_recovery_includes_cycle_count(self):
        self.set_cpu("bad")
        state = MODULE.ControllerState()
        with self.capture_output() as (_, stderr):
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
        self.assertEqual("", stderr.getvalue())
        self.set_cpu("40000")
        with self.capture_output() as (_, stderr):
            report = MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=1
            )
        self.assertEqual("", stderr.getvalue())
        with self.capture_output() as (output, stderr):
            MODULE.emit_verbose(report, [self.fan()], self.config(), state)
        self.assertEqual("", stderr.getvalue())
        self.assertIn("recovery_cycles=1/5", output.getvalue())

    def test_default_persistent_errors_are_rate_limited(self):
        self.set_cpu("bad")
        state = MODULE.ControllerState()
        with self.capture_output() as (output, stderr):
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=0
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=1
            )
            MODULE.run_cycle(
                [self.fan()], self.config(), state, self.root, now=60
            )
        self.assertEqual("", stderr.getvalue())
        self.assertEqual(
            1, output.getvalue().count("mode transition: mode=sensor-failsafe")
        )
        self.assertEqual(
            1, output.getvalue().count("warning: mode=sensor-failsafe")
        )

    def test_run_loop_sleeps_one_second_and_history_never_exceeds_five(self):
        fan = self.fan()
        state = MODULE.ControllerState()
        sleeps = []

        def sleeper(seconds):
            sleeps.append(seconds)
            state.shutdown_requested = True

        with self.capture_output() as (_, stderr):
            MODULE.run_loop(
                [fan],
                self.config(),
                state,
                self.root,
                sleeper=sleeper,
                clock=lambda: 0,
            )
        self.assertEqual("", stderr.getvalue())
        self.assertEqual([1], sleeps)
        self.assertLessEqual(len(state.history), 5)
        self.assertEqual("shutting-down", state.mode)

    def test_signal_handlers_only_request_shutdown(self):
        state = MODULE.ControllerState()
        handlers = {}
        with mock.patch.object(
            MODULE.signal,
            "signal",
            side_effect=lambda sig, handler: handlers.__setitem__(sig, handler),
        ):
            MODULE.install_signal_handlers(state)
        handlers[MODULE.signal.SIGINT](MODULE.signal.SIGINT, None)
        self.assertTrue(state.shutdown_requested)
        state.shutdown_requested = False
        handlers[MODULE.signal.SIGTERM](MODULE.signal.SIGTERM, None)
        self.assertTrue(state.shutdown_requested)

    def test_cleanup_attempts_all_fans_after_one_failure(self):
        first = mock.Mock(name="fan1")
        second = mock.Mock(name="fan2")
        first.name = "fan1"
        second.name = "fan2"
        first.disable_manual.side_effect = OSError("first")
        self.assertEqual(1, len(MODULE.cleanup_fans([first, second])))
        first.disable_manual.assert_called_once()
        second.disable_manual.assert_called_once()

    def test_main_fatal_path_reports_and_cleans_up_independently(self):
        first = mock.Mock(name="fan1", maximum=1000)
        second = mock.Mock(name="fan2", maximum=2000)
        first.name = "fan1"
        second.name = "fan2"
        first.set_speed.side_effect = OSError("fan1 output")
        second.set_speed.side_effect = OSError("fan2 output")
        first.disable_manual.side_effect = OSError("fan1 manual")
        config = MODULE.ConfigResult(
            [
                MODULE.FanConfig(55, 75, "linear", False),
                MODULE.FanConfig(55, 75, "linear", False),
            ]
        )
        pid_path = self.root / "run.pid"
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
            MODULE, "discover_fans", return_value=([first, second], [])
        ), mock.patch.object(
            MODULE, "load_configuration", return_value=config
        ), mock.patch.object(
            MODULE, "install_signal_handlers"
        ), mock.patch.object(MODULE, "write_pid"), mock.patch.object(
            MODULE,
            "run_loop",
            side_effect=MODULE.FatalControlError("maximum control lost"),
        ), mock.patch.object(MODULE, "remove_pid") as remove_pid:
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])

        self.assertEqual(1, result)
        self.assertIn("mode=control-error", stdout.getvalue())
        self.assertIn("critical: maximum control lost", stderr.getvalue())
        first.set_speed.assert_called_once_with(1000)
        second.set_speed.assert_called_once_with(2000)
        first.disable_manual.assert_called_once()
        second.disable_manual.assert_called_once()
        remove_pid.assert_called_once_with(pid_path)

    def test_main_unexpected_exception_after_control_starts_is_fatal(self):
        events = []

        class FakeFan:
            def __init__(
                self, name, maximum, max_error=None, cleanup_error=None
            ):
                self.name = name
                self.maximum = maximum
                self.max_error = max_error
                self.cleanup_error = cleanup_error

            def enable_manual(self):
                events.append(f"{self.name}:enable")

            def set_speed(self, speed):
                events.append(f"{self.name}:maximum={speed}")
                if self.max_error is not None:
                    raise self.max_error

            def disable_manual(self):
                events.append(f"{self.name}:cleanup")
                if self.cleanup_error is not None:
                    raise self.cleanup_error

        first = FakeFan(
            "fan1", 1000, OSError("fan1 maximum"), OSError("fan1 manual")
        )
        second = FakeFan("fan2", 2000)
        config = MODULE.ConfigResult(
            [
                MODULE.FanConfig(55, 75, "linear", False),
                MODULE.FanConfig(55, 75, "linear", False),
            ]
        )
        pid_path = self.root / "run.pid"
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(MODULE, "prepare_pid"), mock.patch.object(
            MODULE, "discover_fans", return_value=([first, second], [])
        ), mock.patch.object(
            MODULE, "load_configuration", return_value=config
        ), mock.patch.object(
            MODULE, "install_signal_handlers"
        ), mock.patch.object(
            MODULE,
            "run_loop",
            side_effect=RuntimeError("unexpected control failure"),
        ), mock.patch.object(
            MODULE, "remove_pid", wraps=MODULE.remove_pid
        ) as remove_pid:
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])

        self.assertEqual(1, result)
        self.assertIn("critical: unexpected control failure", stderr.getvalue())
        self.assertNotIn("stopped:", stdout.getvalue())
        self.assertEqual(
            [
                "fan1:enable",
                "fan2:enable",
                "fan1:maximum=1000",
                "fan2:maximum=2000",
                "fan1:cleanup",
                "fan2:cleanup",
            ],
            events,
        )
        self.assertIn(
            "fan1: maximum write failed: fan1 maximum", stderr.getvalue()
        )
        self.assertIn(
            "fan1: manual-mode cleanup failed: fan1 manual", stderr.getvalue()
        )
        remove_pid.assert_called_once_with(pid_path)
        self.assertFalse(pid_path.exists())

    def test_t2fand_enable_failure_is_fatal_and_cleans_up_known_fans(self):
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        first = next(fan for fan in fans if fan.name == "fan1")
        failed = next(fan for fan in fans if fan.name == "fan2")
        failed_manual = failed.base_path.with_name(f"{failed.name}_manual")
        failed_manual.unlink()
        failed_manual.mkdir()

        pid_path = self.root / "run.pid"
        config_path = self.root / "config"
        config_path.write_text(
            "[General]\ncontrol_mode=t2fand\n"
            "[Fan1]\nlow_temp=55\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
            "[Fan2]\nlow_temp=55\nhigh_temp=75\n"
            "speed_curve=linear\nalways_full_speed=false\n"
        )
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(
            MODULE, "DEFAULT_CONFIG_PATH", config_path
        ), mock.patch.object(
            MODULE, "discover_fans", return_value=(fans, errors)
        ), mock.patch.object(MODULE, "install_signal_handlers"):
            with self.capture_output() as (stdout, stderr):
                result = MODULE.main([])

        failure = f"{failed.name}: cannot enable manual mode:"
        self.assertEqual(1, result)
        self.assertIn(f"mode=control-error reason={failure}", stdout.getvalue())
        self.assertIn(f"critical: {failure}", stderr.getvalue())
        self.assertIn(
            f"{failed.name}: manual-mode cleanup failed:", stderr.getvalue()
        )
        self.assertEqual(
            "1000", first.base_path.with_name("fan1_output").read_text()
        )
        self.assertEqual(
            "1200", failed.base_path.with_name("fan2_output").read_text()
        )
        self.assertEqual(
            "0", first.base_path.with_name("fan1_manual").read_text()
        )
        self.assertTrue(failed_manual.is_dir())
        self.assertFalse(pid_path.exists())

    def test_pre_control_exits_do_not_report_normal_shutdown(self):
        with mock.patch.object(MODULE.os, "geteuid", return_value=1000):
            with self.capture_output() as (_, stderr):
                self.assertEqual(1, MODULE.main([]))
        self.assertNotIn("stopped:", _.getvalue())

        with self.capture_output() as (stdout, _):
            with self.assertRaises(SystemExit):
                MODULE.main(["--invalid"])
        self.assertNotIn("stopped:", stdout.getvalue())

    def test_pid_malformed_and_stale_files_are_removed_but_live_is_rejected(
        self,
    ):
        pid = self.root / "run.pid"
        proc = self.root / "proc"
        proc.mkdir()
        pid.write_text("not-a-pid")
        with self.capture_output() as (stdout, stderr):
            MODULE.prepare_pid(pid, proc)
        self.assertFalse(pid.exists())
        pid.write_text("123")
        with self.capture_output() as (stale_stdout, stale_stderr):
            MODULE.prepare_pid(pid, proc)
        self.assertFalse(pid.exists())
        self.assertEqual("", stdout.getvalue() + stale_stdout.getvalue())
        self.assertIn("warning: malformed PID file", stderr.getvalue())
        self.assertIn(
            "warning: removing stale PID file", stale_stderr.getvalue()
        )
        pid.write_text("123")
        (proc / "123").mkdir()
        with self.capture_output() as (live_stdout, live_stderr):
            with self.assertRaises(MODULE.StartupError) as error:
                MODULE.prepare_pid(pid, proc)
        self.assertEqual("", live_stdout.getvalue() + live_stderr.getvalue())
        self.assertIn("already running (PID 123)", str(error.exception))


class StaticContractTests(unittest.TestCase):
    def test_benchmark_log_uses_local_english_timestamp_and_logger(self):
        benchmark = BENCHMARK_SOURCE
        tree = ast.parse(benchmark.read_text())
        log_node = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "log"
        )
        previous_locale = locale.setlocale(locale.LC_TIME)
        selected_locale = None
        for candidate in ("fr_FR.UTF-8", "de_DE.UTF-8", "es_ES.UTF-8"):
            try:
                locale.setlocale(locale.LC_TIME, candidate)
            except locale.Error:
                continue
            selected_locale = candidate
            break
        if selected_locale is None:
            self.skipTest("no non-English LC_TIME locale is installed")
        try:
            clock = mock.Mock()
            clock.localtime.return_value = types.SimpleNamespace(
                tm_mon=9, tm_mday=3, tm_hour=4, tm_min=5, tm_sec=6
            )
            clock.strftime.side_effect = AssertionError(
                "benchmark log must not use locale-sensitive formatting"
            )
            logger = mock.Mock()
            namespace = {
                "time": clock,
                "subprocess": types.SimpleNamespace(run=logger),
            }
            exec(
                compile(ast.Module([log_node], []), str(benchmark), "exec"),
                namespace,
            )
            output = io.StringIO()
            with contextlib.redirect_stdout(output):
                namespace["log"]("MESSAGE")
            self.assertEqual(
                "Sep 03 04:05:06 [t2fanbench] MESSAGE\n", output.getvalue()
            )
            logger.assert_called_once_with(
                ["logger", "-t", "t2fanbench", "MESSAGE"], check=False
            )
            clock.strftime.assert_not_called()
        finally:
            locale.setlocale(locale.LC_TIME, previous_locale)

    def test_benchmark_requires_stress_ng_before_side_effects(self):
        with tempfile.TemporaryDirectory() as tempdir:
            cache = Path(tempdir) / "cache"
            with mock.patch.object(
                BENCHMARK.shutil, "which", return_value=None
            ) as which, mock.patch.object(
                BENCHMARK, "TEMP_PATH", cache
            ), mock.patch.object(BENCHMARK, "log") as log, mock.patch.object(
                BENCHMARK, "run"
            ) as run, mock.patch.object(
                BENCHMARK, "cooldown"
            ) as cooldown, mock.patch.object(
                BENCHMARK.time, "sleep"
            ) as sleep, mock.patch.object(
                BENCHMARK.subprocess, "run"
            ) as subprocess_run:
                stdout = io.StringIO()
                stderr = io.StringIO()
                with contextlib.redirect_stdout(
                    stdout
                ), contextlib.redirect_stderr(stderr):
                    result = BENCHMARK.main()
            cache_created = cache.exists()

        self.assertEqual(1, result)
        self.assertEqual(
            "error: stress-ng is required but was not found in PATH\n",
            stderr.getvalue(),
        )
        self.assertEqual("", stdout.getvalue())
        self.assertFalse(cache_created)
        which.assert_called_once_with("stress-ng")
        log.assert_not_called()
        run.assert_not_called()
        cooldown.assert_not_called()
        sleep.assert_not_called()
        subprocess_run.assert_not_called()

    def test_benchmark_present_path_starts_without_real_workloads_or_timers(
        self,
    ):
        with tempfile.TemporaryDirectory() as tempdir:
            cache = Path(tempdir) / "cache"
            with mock.patch.object(
                BENCHMARK.shutil, "which", return_value="/usr/bin/stress-ng"
            ) as which, mock.patch.object(
                BENCHMARK, "TEMP_PATH", cache
            ), mock.patch.object(BENCHMARK, "benchmark") as benchmark:
                result = BENCHMARK.main()
            cache_created = cache.is_dir()

        self.assertEqual(0, result)
        self.assertTrue(cache_created)
        which.assert_called_once_with("stress-ng")
        benchmark.assert_called_once_with()

    def test_import_safety_cli_guard_and_named_state(self):
        tree = ast.parse(SOURCE.read_text())
        source = SOURCE.read_text()
        self.assertIn("def main(argv", source)
        self.assertIn('if __name__ == "__main__":', source)
        self.assertNotIn("exit(", source)
        self.assertIn("class ControllerState", source)
        self.assertIn("argparse", source)
        module_signal_calls = [
            node
            for statement in tree.body
            if not isinstance(
                statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
            )
            for node in ast.walk(statement)
            if isinstance(node, ast.Call)
            and isinstance(node.func, ast.Attribute)
            and isinstance(node.func.value, ast.Name)
            and node.func.value.id == "signal"
            and node.func.attr == "signal"
        ]
        self.assertEqual([], module_signal_calls)
        self.assertNotRegex(
            source, r"^\s*Path\([^\n]+\)\.read_text", re.MULTILINE
        )

    def test_makefile_has_project_native_test_target(self):
        makefile = (SOURCE.parent / "Makefile").read_text()
        self.assertIn(".PHONY: install test", makefile)
        self.assertRegex(
            makefile, r"(?m)^test:\n\tpython3 -m unittest discover"
        )

    def test_confd_has_only_optional_args_assignment_and_install_mode(self):
        confd = (SOURCE.parent / "t2fand.confd").read_text()
        assignments = re.findall(r"(?m)^([A-Za-z_][A-Za-z0-9_]*)=", confd)
        self.assertEqual(["t2fand_args"], assignments)
        self.assertIn('t2fand_args=""', confd)
        self.assertIn("t2fand owns daemon defaults and options", confd)
        self.assertIn("t2fand_args provides optional overrides", confd)
        self.assertIn("t2fand --help is authoritative", confd)
        self.assertIn(
            'Example: t2fand_args="--verbose --sensor-recovery-cycles 10"',
            confd,
        )
        for removed in (
            "t2fand_config_path",
            "t2fand_pid_path",
            "t2fand_sysfs_path",
            "t2fand_sensor_recovery_cycles",
            "t2fand_sample_limit",
            "t2fand_error_reminder_seconds",
        ):
            self.assertNotIn(removed, confd)
        makefile = (SOURCE.parent / "Makefile").read_text()
        self.assertIn("OPENRC_CONFDIR ?= /etc/conf.d", makefile)

    def test_openrc_optional_args_are_static_and_ordered(self):
        initd = (SOURCE.parent / "t2fand.initd").read_text()
        command_args = re.search(r'(?m)^command_args="([^"]*)"$', initd).group(
            1
        )
        self.assertEqual(1, initd.count("command_args="))
        self.assertEqual("${t2fand_args:-}", command_args)
        for configured, expected in (
            (None, []),
            ("", []),
            ("--verbose", ["--verbose"]),
            (
                "--verbose --sensor-recovery-cycles 10",
                ["--verbose", "--sensor-recovery-cycles", "10"],
            ),
            (
                "--sensor-recovery-cycles 10 --verbose",
                ["--sensor-recovery-cycles", "10", "--verbose"],
            ),
        ):
            with self.subTest(configured=configured):
                environment = (
                    {} if configured is None else {"t2fand_args": configured}
                )
                expanded = command_args.replace(
                    "${t2fand_args:-}",
                    environment.get("t2fand_args") or "",
                )
                self.assertEqual(expected, shlex.split(expanded))
        for removed in (
            "--config-path",
            "--pid-path",
            "--sysfs-path",
            "--sensor-recovery-cycles",
            "--sample-limit",
            "--error-reminder-seconds",
            "t2fand_config_path",
            "t2fand_pid_path",
            "t2fand_sysfs_path",
            "t2fand_sensor_recovery_cycles",
            "t2fand_sample_limit",
            "t2fand_error_reminder_seconds",
        ):
            self.assertNotIn(removed, initd)
        self.assertIn('supervisor="supervise-daemon"', initd)
        self.assertIn(
            'output_logger="/usr/bin/logger -t t2fand -p daemon.info"', initd
        )
        self.assertIn(
            'error_logger="/usr/bin/logger -t t2fand -p daemon.err"', initd
        )
        for directive in (
            'respawn_delay="2"',
            'respawn_max="5"',
            'respawn_period="60"',
            'supervise_daemon_args="--respawn-delay-step 2"',
            'retry="SIGTERM/5"',
            "need localmount",
            "use logger",
        ):
            self.assertIn(directive, initd)
        self.assertNotIn("pidfile", initd)
        self.assertNotIn("INIT_SYSTEM", initd)
        self.assertNotRegex(initd, r"(?m)^\s*pidfile\s*=")
        self.assertNotRegex(
            initd,
            r"(?m)^\s*(background|command_background|daemon|daemonize|network)\s*=",
        )

    def test_package_has_exact_openrc_payload_and_no_alternate_selector(self):
        package = (SOURCE.parent / "PKGBUILD").read_text()
        makefile = (SOURCE.parent / "Makefile").read_text()
        self.assertIn("pkgname=t2fand", package)
        self.assertRegex(package, r"(?m)^pkgver=2\.0\.1$")
        self.assertRegex(package, r"(?m)^pkgrel=2$")
        self.assertRegex(
            package, r"(?m)^depends=\('linux-t2' 'python' 'util-linux'\)$"
        )
        self.assertRegex(
            package,
            r"(?m)^source=\('t2fand' 't2fand\.initd' 't2fand\.confd' 'Makefile'\)$",
        )
        self.assertIn("backup=('etc/conf.d/t2fand')", package)
        self.assertIn('make DESTDIR="$pkgdir" install', package)
        self.assertIn(
            'install -D -m 0700 "t2fand" "$(DESTDIR)$(BINDIR)/t2fand"',
            makefile,
        )
        self.assertIn(
            'install -D -m 0755 "t2fand.initd" "$(DESTDIR)$(OPENRC_INITDDIR)/t2fand"',
            makefile,
        )
        self.assertIn("OPENRC_CONFDIR ?= /etc/conf.d", makefile)
        self.assertIn(
            'install -D -m 0644 "t2fand.confd" "$(DESTDIR)$(OPENRC_CONFDIR)/t2fand"',
            makefile,
        )
        self.assertEqual(3, len(re.findall(r"(?m)^\s*install -D -m", makefile)))
        self.assertNotIn("systemd", package.lower())
        self.assertNotIn("INIT_SYSTEM", package)
        self.assertNotIn("INIT_SYSTEM", makefile)
        self.assertNotIn("systemd", makefile.lower())
        self.assertFalse((SOURCE.parent / "t2fand.service").exists())
        self.assertEqual([], list(SOURCE.parent.glob("*.service")))


if __name__ == "__main__":
    unittest.main()
