import ast
import contextlib
import importlib.util
import io
import re
import sys
import tempfile
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
        self.fan_dir = self.hwmon / "hwmon-fan"
        self.fan_dir.mkdir()
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
        app.mkdir(parents=True)
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

    def cycle(self, now=0):
        with self.capture_output():
            return MODULE.run_cycle(
                [self.fan_object],
                self.config_result,
                self.state,
                self.root,
                now=now,
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

    def test_unreadable_config_enters_global_failsafe(self):
        path = self.root / "config"
        path.mkdir()
        result = MODULE.load_configuration(path, 1)
        self.assertFalse(result.valid)
        self.assertEqual(1, len(result.errors))
        self.assertTrue(
            result.errors[0].startswith(f"{path}: cannot read config: ")
        )

        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(
                [self.fan()], result, state, self.root, now=0
            )
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual((1000,), report.targets)

    def test_config_generation_io_failure_enters_global_failsafe(self):
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
        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(fans, result, state, self.root, now=0)
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual(diagnostic, state.reason)
        self.assertEqual(tuple(fan.maximum for fan in fans), report.targets)
        self.assertEqual(
            [str(fan.maximum) for fan in fans],
            [
                fan.base_path.with_name(f"{fan.name}_output").read_text()
                for fan in fans
            ],
        )

    def test_malformed_ini_enters_global_failsafe(self):
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

        state = MODULE.ControllerState()
        with self.capture_output():
            report = MODULE.run_cycle(fans, result, state, self.root, now=0)
        self.assertEqual("config-failsafe", state.mode)
        self.assertEqual(tuple(fan.maximum for fan in fans), report.targets)
        self.assertEqual(
            [str(fan.maximum) for fan in fans],
            [
                fan.base_path.with_name(f"{fan.name}_output").read_text()
                for fan in fans
            ],
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
            "iwlwifi:temp1=45.0",
            "nvme:Composite=70.0",
            "gpu_temps=present",
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

    def test_manual_enable_failure_is_fatal_and_cleans_up_known_fans(self):
        self.add_t2_fan()
        fans, errors = MODULE.discover_fans(self.root)
        self.assertEqual([], errors)
        first = next(fan for fan in fans if fan.name == "fan1")
        failed = next(fan for fan in fans if fan.name == "fan2")
        failed_manual = failed.base_path.with_name(f"{failed.name}_manual")
        failed_manual.unlink()
        failed_manual.mkdir()

        pid_path = self.root / "run.pid"
        with mock.patch.object(
            MODULE.os, "geteuid", return_value=0
        ), mock.patch.object(
            MODULE, "DEFAULT_PID_PATH", pid_path
        ), mock.patch.object(
            MODULE, "DEFAULT_CONFIG_PATH", self.root / "config"
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

    def test_openrc_supervision_logger_and_arguments_are_static_contract(self):
        initd = (SOURCE.parent / "t2fand.initd").read_text()
        self.assertIn('supervisor="supervise-daemon"', initd)
        self.assertIn('command_args="${t2fand_args:-}"', initd)
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
        self.assertRegex(package, r"(?m)^pkgver=2\.0\.0$")
        self.assertRegex(package, r"(?m)^pkgrel=1$")
        self.assertRegex(
            package, r"(?m)^depends=\('linux-t2' 'python' 'util-linux'\)$"
        )
        self.assertIn('install -Dm700 t2fand "$pkgdir/usr/bin/t2fand"', package)
        self.assertIn(
            'install -Dm755 t2fand.initd "$pkgdir/etc/init.d/t2fand"', package
        )
        self.assertEqual(2, len(re.findall(r"(?m)^\s*install -Dm", package)))
        self.assertNotIn("systemd", package.lower())
        self.assertNotIn("INIT_SYSTEM", package)
        self.assertNotIn("INIT_SYSTEM", makefile)
        self.assertNotIn("systemd", makefile.lower())
        self.assertFalse((SOURCE.parent / "t2fand.service").exists())
        self.assertEqual([], list(SOURCE.parent.glob("*.service")))


if __name__ == "__main__":
    unittest.main()
