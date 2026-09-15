"""Vérifications sans robot ni broker ; exécute le vrai code avec des périphériques simulés."""
import asyncio
import contextlib
import importlib.util
import inspect
import io
import json
import math
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server/control-dashboard/fastapi-dashboard'))


def load(name, relative):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class EndSimulation(BaseException):
    pass


class Robot:
    """Horloge, MQTT et sorties simulés ; la boucle applicative reste inchangée."""
    def __init__(self):
        self.now = 0
        self.loop_delay = 100
        self.obstacle_raw = [65000] * 4
        self.matrix = Mock()
        self.published = []
        self.moves = []
        self.stopped = True
        self.drop_step = False
        self.actions = []
        self.loop_index = 0
        self.timers = {}
        self.motors = types.SimpleNamespace(
            SPACE_BETWEEN_WHEELS=77.5, WHEEL_DIAMETER=33.5,
            DISTANCE_PER_REVOLUTION=33.5 * math.pi / 10,
            repetition_per_second=lambda speed=100: 1.3 * speed / 100,
            motor_stop=self.stop, get_battery_voltage=lambda: 3.8,
        )
        for name in ('move_forward', 'move_backward', 'turn_left', 'turn_right', 'turn_in_place', 'spin_left_wheel_forward', 'spin_left_wheel_backward', 'spin_right_wheel_forward', 'spin_right_wheel_backward'):
            setattr(self.motors, name, lambda *args, name=name: self.move(name, args))
        self.client = types.SimpleNamespace(
            subscribe=lambda *args: None, publish=self.publish, loop=self.loop,
            connect=lambda: self.client.on_connect(self.client, None, None, 0),
            reconnect=lambda: self.client.on_connect(self.client, None, None, 0),
        )

    @property
    def state(self):
        return inspect.getclosurevars(self.client.on_message).nonlocals['state']

    def stop(self):
        self.stopped = True

    def move(self, name, args):
        self.stopped = False
        self.moves.append((name, args))

    def publish(self, topic, payload):
        if self.drop_step and topic.endswith('/step'):
            self.drop_step = False
            raise OSError('Message perdu')
        self.published.append((topic, payload))

    def send(self, suffix, payload):
        self.client.on_message(self.client, 'elio/command/' + suffix, payload)

    def command(self, action='forward', **overrides):
        data = {'session': self.state['session'], 'step_id': self.state['pending_step']['step_id'], 'action': action}
        data.update(overrides)
        return json.dumps(data)

    def loop(self, **kwargs):
        if self.loop_index >= len(self.actions):
            raise EndSimulation()
        action = self.actions[self.loop_index]
        self.loop_index += 1
        if action:
            action(self)
        self.now += self.loop_delay

    def sleep(self, ms):
        self.now += ms

    def every(self, key, period):
        if self.now >= self.timers.get(key, -1):
            self.timers[key] = self.now + period
            return True
        return False

    def run(self, actions):
        self.actions = actions
        hardware = types.ModuleType('programs.hardware')
        hardware.setup_motors = lambda: self.motors
        hardware.setup_matrix = lambda: self.matrix
        hardware.setup_buzzer = lambda: Mock()
        hardware.setup_obstacle_sensors = lambda: types.SimpleNamespace(
            get_obstacle=lambda i:self.obstacle_raw[i]<10000, get_raw=lambda i:self.obstacle_raw[i], thresholds=[10000]*4)
        hardware.setup_line_sensor = lambda _: types.SimpleNamespace(
            lineCmd=types.SimpleNamespace(value=False),
            lineInput=[types.SimpleNamespace(value=10000) for _ in range(5)])
        hardware.sleep_ms, hardware.now_ms, hardware.every_ms = self.sleep, lambda: self.now, self.every
        package = types.ModuleType('programs')
        package.__path__ = [str(ROOT / 'robot/programs')]
        mqtt_package = types.ModuleType('adafruit_minimqtt')
        mqtt_package.__path__ = []
        mqtt = types.ModuleType('adafruit_minimqtt.adafruit_minimqtt')
        mqtt.MQTT = lambda **kwargs: self.client
        modules = {
            'programs': package, 'programs.hardware': hardware,
            'wifi': types.SimpleNamespace(radio=object()),
            'socketpool': types.SimpleNamespace(SocketPool=lambda _: object()),
            'adafruit_minimqtt': mqtt_package,
            'adafruit_minimqtt.adafruit_minimqtt': mqtt,
            'elio': types.SimpleNamespace(WiFiConnectivity=types.SimpleNamespace(connect_and_setup=lambda **kwargs: None)),
        }
        with patch.dict(sys.modules, modules), contextlib.redirect_stdout(io.StringIO()):
            module = load('programs.mqtt_dashboard', 'robot/programs/mqtt_dashboard.py')
            try:
                module.run()
            except EndSimulation:
                pass


class RobotTests(unittest.TestCase):
    def test_manual_eyes_are_sent_on_change_and_other_telemetry_is_not_starved(self):
        robot=Robot();robot.loop_delay=400
        def start(r):r.send('mode','manual');r.send('move','forward')
        def forward(r):r.send('move','forward')
        def right(r):r.send('move','right')
        robot.run([start]+[forward]*7+[right]+[None]*3)
        eyes=[json.loads(p)['pattern'] for t,p in robot.published if t.endswith('/eyes')]
        self.assertIn('arrowUp',eyes);self.assertIn('arrowRight',eyes)
        self.assertEqual(eyes[-1],'emotionNeutral')
        for group in ('battery','obstacles','lines','status'):
            self.assertTrue(any(t.endswith('/'+group) for t,p in robot.published),group)
        self.assertLess(robot.matrix.set_matrix_logo.call_count,10)

    def test_sensor_diagnostics_use_same_values_as_obstacle_flags(self):
        robot=Robot();robot.obstacle_raw=[500,12000,2000,64000]
        robot.run([None]*12)
        packets=[json.loads(p) for t,p in robot.published if t.endswith('/obstacles')]
        self.assertTrue(packets)
        self.assertTrue(packets[-1]['left']);self.assertTrue(packets[-1]['right'])
        self.assertFalse(packets[-1]['front']);self.assertEqual(packets[-1]['raw']['left'],500)
        self.assertEqual(packets[-1]['thresholds']['left'],10000)

    def test_reset_while_moving_stops_and_invalidates_old_command(self):
        previous = {}
        def start(robot):
            previous['command'] = robot.command()
            robot.send('explore_step', previous['command'])
            self.assertFalse(robot.stopped)
        def reset(robot):
            robot.send('reset_map', '1')
            self.assertTrue(robot.stopped)
            self.assertEqual(robot.state['mode'], 'idle')
            self.assertEqual((robot.state['ex_x'], robot.state['ex_y']), (0, 0))
            robot.send('mode', 'exploration')
        def replay(robot):
            robot.send('explore_step', previous['command'])
            self.assertTrue(robot.stopped)
        robot = Robot()
        robot.run([lambda r: r.send('mode', 'exploration'), start, reset, replay])
        self.assertEqual(len(robot.moves), 1)

    def test_lost_step_and_lost_command_retry_same_id(self):
        robot = Robot()
        robot.drop_step = True
        robot.run([lambda r: r.send('mode', 'exploration')] + [None] * 25)
        steps = [json.loads(p) for t, p in robot.published if t.endswith('/step')]
        self.assertGreaterEqual(len(steps), 2)
        self.assertEqual(steps[0], steps[1])
        self.assertTrue(robot.stopped)

    def test_duplicate_command_executes_once_and_completion_is_reported(self):
        previous = {}
        def command(robot):
            previous['payload'] = robot.command()
            previous['id'] = robot.state['pending_step']['step_id']
            robot.send('explore_step', previous['payload'])
            robot.send('explore_step', previous['payload'])
        def replay(robot):
            robot.send('explore_step', previous['payload'])
        robot = Robot()
        robot.run([lambda r: r.send('mode', 'exploration'), command] + [None] * 30 + [replay])
        self.assertEqual(len(robot.moves), 1)
        self.assertEqual(robot.state['ex_y'], 1)
        self.assertEqual(robot.state['pending_step']['completed_id'], previous['id'])
        self.assertTrue(robot.stopped)

    def test_duplicate_exploration_mode_does_not_cancel_active_move(self):
        def duplicate(robot):
            deadline = robot.state['ex_until']
            robot.send('mode', 'exploration')
            self.assertEqual(robot.state['ex_state'], 'moving')
            self.assertEqual(robot.state['ex_until'], deadline)
        Robot().run([lambda r: r.send('mode', 'exploration'),
                     lambda r: r.send('explore_step', r.command()), duplicate])

    def test_disconnect_mid_move_returns_idle_without_fake_completion(self):
        def fail(robot):
            raise OSError('Connexion perdue')
        robot = Robot()
        robot.run([lambda r: r.send('mode', 'exploration'),
                   lambda r: r.send('explore_step', r.command()), fail, None])
        self.assertTrue(robot.stopped)
        self.assertEqual(robot.state['mode'], 'idle')
        self.assertIsNone(robot.state['pending_step'])
        self.assertFalse(robot.state['position_valid'])
        self.assertEqual(robot.state['ex_y'], 0)

    def test_manual_deadman_and_zero_speed(self):
        def manual(robot):
            robot.send('mode', 'manual')
            robot.send('move', 'forward')
        robot = Robot()
        robot.run([manual] + [None] * 10)
        self.assertTrue(robot.stopped)
        self.assertIsNone(robot.state['manual_cmd'])
        self.assertGreater(len(robot.moves), 0)
        zero = Robot()
        zero.run([lambda r: (r.send('mode', 'manual'), r.send('speed', '0'), r.send('move', 'forward')), None])
        self.assertTrue(zero.stopped)
        self.assertEqual(zero.moves, [])

    def test_manual_connection_failure_does_not_resume_stale_command(self):
        def fail(robot):
            raise OSError('Connexion perdue')
        robot = Robot()
        robot.run([lambda r: (r.send('mode', 'manual'), r.send('move', 'forward')), fail, None])
        self.assertTrue(robot.stopped)
        self.assertIsNone(robot.state['manual_cmd'])
        self.assertEqual(robot.state['mode'], 'idle')

    def test_telemetry_error_also_stops_motors(self):
        def fail_telemetry(robot):
            robot.send('mode', 'manual')
            robot.send('move', 'forward')
            def publish(*args):
                raise OSError('Échec publication')
            robot.client.publish = publish
        robot = Robot()
        robot.run([fail_telemetry, None])
        self.assertTrue(robot.stopped)
        self.assertEqual(robot.state['mode'], 'idle')


class FrameworkTests(unittest.TestCase):
    def test_discovery_does_not_import_unused_programs_and_preserves_alias(self):
        registry = load('test_registry', 'robot/programs/registry.py')
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp) / 'programs'
            folder.mkdir()
            (folder / 'unused.py').write_text('raise RuntimeError("Doit rester non importé")\n')
            (folder / 'selected.py').write_text('PROGRAM_NAME = "alias"\ndef run(): return 42\n')
            package = types.ModuleType('programs')
            package.__path__ = [str(folder)]
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                with patch.dict(sys.modules, {'programs': package}):
                    programs = registry.discover_programs()
                    self.assertNotIn('programs.unused', sys.modules)
                    self.assertNotIn('programs.selected', sys.modules)
                    self.assertEqual(programs['alias'](), 42)
            finally:
                os.chdir(cwd)

    def test_main_stops_on_exception_normal_return_and_repl_interrupt(self):
        stop = Mock()
        registry = types.SimpleNamespace(discover_programs=lambda: {'web_server': lambda: None})
        with patch.dict(sys.modules, {'programs.registry': registry, 'programs.hardware': types.SimpleNamespace(emergency_stop=stop)}), patch.dict(os.environ, {'PROGRAM': 'web_server'}), contextlib.redirect_stdout(io.StringIO()):
            main = load('test_main', 'robot/main.py')
            for error in (None, RuntimeError('Crash'), KeyboardInterrupt()):
                stop.reset_mock()
                def run():
                    if error:
                        raise error
                try:
                    main._run_program('test', {'test': run})
                except KeyboardInterrupt:
                    pass
                stop.assert_called_once()

    def test_partial_motor_setup_remains_stoppable_and_setup_is_singleton(self):
        outputs = []
        def pwm(pin):
            if pin == 35:
                raise RuntimeError('Allocation PWM impossible')
            output = types.SimpleNamespace(duty_cycle=0)
            outputs.append(output)
            return output
        board = types.SimpleNamespace(**{f'IO{i}': i for i in (36, 38, 35, 37, 10, 11, 12, 13, 14, 33, 9)})
        board.BATTERY = 'battery'
        elio = types.SimpleNamespace(**{name: Mock() for name in ('Motors', 'Buzzer', 'ObstacleSensor', 'EyesMatrix', 'LineSensor', 'IRRemote')})
        with patch.dict(sys.modules, {'board': board, 'pwmio': types.SimpleNamespace(PWMOut=pwm), 'analogio': types.SimpleNamespace(AnalogIn=Mock()), 'digitalio': Mock(), 'pulseio': Mock(), 'elio': elio}):
            hardware = load('test_hardware', 'robot/programs/hardware.py')
            with self.assertRaises(RuntimeError):
                hardware.setup_motors()
            self.assertTrue(all(o.duty_cycle == 65535 for o in outputs))
            with self.assertRaisesRegex(RuntimeError, 'redémarrer'):
                hardware.setup_motors()
            hardware._motor_outputs.clear()
            with patch.object(sys.modules['pwmio'], 'PWMOut', lambda _: types.SimpleNamespace(duty_cycle=0)):
                self.assertIs(hardware.setup_motors(), hardware.setup_motors())
                self.assertEqual(len(hardware._motor_outputs), 4)

    def test_obstacle_thresholds_are_per_sensor_and_keep_default_behavior(self):
        with patch.dict(sys.modules, {name: Mock() for name in ('wifi', 'mdns', 'adafruit_irremote', 'neopixel')}):
            library=load('obstacle_lib','robot/lib/elio.py')
        inputs=[types.SimpleNamespace(value=12000) for _ in range(4)]
        self.assertFalse(library.ObstacleSensor(inputs).get_obstacle(0))
        sensors=library.ObstacleSensor(inputs,[15000,10000,13000,12000])
        self.assertEqual([sensors.get_obstacle(i) for i in range(4)],[True,False,True,False])
        self.assertEqual(sensors.get_raw(0),12000)
        for invalid in ([1], [0]*4, [65536]*4, [True]*4):
            with self.assertRaises(ValueError):library.ObstacleSensor(inputs,invalid)

    def test_zero_pwm_and_speed_aware_estimate(self):
        with patch.dict(sys.modules, {name: Mock() for name in ('wifi', 'mdns', 'adafruit_irremote', 'neopixel')}):
            library = load('test_elio', 'robot/lib/elio.py')
        self.assertEqual(library.Motors.set_speed(0), 0)
        self.assertEqual(library.Motors.set_speed(-1), 0)
        self.assertLess(library.Motors.set_speed(14), library.Motors.set_speed(16))
        motors = library.Motors(None, None, None, None, types.SimpleNamespace(value=37000))
        self.assertAlmostEqual(motors.repetition_per_second(60), 0.6 * motors.repetition_per_second(), places=4)

    def test_line_calibration_preserves_motion_factors(self):
        with patch.dict(sys.modules, {name: Mock() for name in ('wifi', 'mdns', 'adafruit_irremote', 'neopixel')}):
            library = load('test_elio', 'robot/lib/elio.py')
        with tempfile.TemporaryDirectory() as tmp:
            cwd = Path.cwd()
            try:
                os.chdir(tmp)
                Path('config.json').write_text(json.dumps({'turn_factor': 1.2, 'move_factor': 0.9}))
                library.LineSensor.save_calibration_data(42000)
                self.assertEqual(json.loads(Path('config.json').read_text()),
                                 {'turn_factor': 1.2, 'move_factor': 0.9, 'line_threshold': 42000})
            finally:
                os.chdir(cwd)


class ServerTests(unittest.TestCase):
    def setUp(self):
        self.server = load('dashboard_test', 'server/control-dashboard/fastapi-dashboard/app.py')
        self.published = []
        self.server._publish = lambda t, p: (self.published.append((t, p)) or True)
        self.server._state['mode'] = 'exploration'
        self.server._state['control']['active'] = 'exploration'

    def step(self, step_id=1, session='test-session'):
        return dict(session=session, step_id=step_id, completed_id=None, x=0, y=0,
                    heading=0, action='start', front=False, left=False, right=False)

    def deliver(self, data):
        msg = types.SimpleNamespace(topic='elio/telemetry/step', payload=json.dumps(data).encode())
        with contextlib.redirect_stdout(io.StringIO()):
            self.server._on_message(None, None, msg)

    def test_duplicate_steps_retry_same_command_without_duplicate_log(self):
        self.deliver(self.step())
        self.deliver(self.step())
        self.assertEqual(len(self.published), 2)
        self.assertEqual(self.published[0], self.published[1])
        self.assertEqual(len(self.server._state['steps']), 1)
        self.assertEqual(json.loads(self.published[0][1])['step_id'], 1)

    def test_old_step_is_ignored_and_new_session_resets_history(self):
        self.deliver(self.step(2))
        self.deliver(self.step(1))
        self.assertEqual(len(self.published), 1)
        self.deliver(self.step(1, 'new-session'))
        self.assertEqual(len(self.server._state['steps']), 1)
        self.assertEqual(json.loads(self.published[-1][1])['session'], 'new-session')

    def test_malformed_steps_do_not_plan(self):
        for value in ([], {}, {'session': 'old'}, dict(self.step(), heading=7)):
            self.deliver(value)
        self.assertEqual(self.published, [])

    def test_server_restart_can_answer_retry(self):
        self.deliver(self.step(23))
        self.assertEqual(json.loads(self.published[-1][1])['step_id'], 23)

    def test_delta_contains_only_changes_and_append_handles_history_limit(self):
        old = {'battery_v': 3.8, 'steps': [{'event_id': i} for i in range(1, 1001)]}
        new = {'battery_v': 3.7, 'steps': [{'event_id': i} for i in range(2, 1002)]}
        delta = self.server._state_delta(old, new)
        self.assertEqual(delta['state'], {'battery_v': 3.7})
        self.assertEqual(delta['steps_append'], [{'event_id': 1001}])
        unchanged = self.server._state_delta(new, new)
        self.assertEqual(unchanged, {'type': 'delta', 'state': {}})
        reset = self.server._state_delta(new, {'battery_v': 3.7, 'steps': []})
        self.assertEqual(reset['state'], {'steps': []})

    def test_new_websocket_gets_snapshot_and_does_not_change_mode(self):
        class WS:
            def __init__(self):
                self.messages = []
            async def accept(self):
                pass
            async def send_json(self, data):
                self.messages.append(data)
        async def check():
            a, b = WS(), WS()
            manager = self.server.ConnectionManager()
            await manager.connect(a)
            self.server._state['battery_v'] = 3.7
            await manager.connect(b)
            await manager.broadcast(self.server._snapshot())
            self.assertEqual(a.messages[-1]['state'], {'battery_v': 3.7})
            self.assertEqual(b.messages[0]['type'], 'snapshot')
            self.assertEqual(len(b.messages), 1)
            self.assertEqual(self.server._state['mode'], 'exploration')
        asyncio.run(check())


if __name__ == '__main__':
    unittest.main()
