"""Contrats moteur, arbitrage des modes et boucle neuronale — sans déplacement réel."""
import asyncio
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import types
import unittest

import numpy as np
import scipy.sparse as sp

from test_regressions import ROOT, Robot, load
from fly_brain import FlyBrain


class FlyRobotTests(unittest.TestCase):
    def command(self, robot, **overrides):
        pending = robot.state['fly_pending']
        return json.dumps({'session': pending['session'], 'frame': pending['frame'], 'left': 30, 'right': 25, **overrides})

    def test_fly_command_expiry_and_duplicate_do_not_restart_wheels(self):
        old = {}
        def drive(robot):
            old['payload'] = self.command(robot)
            robot.send('fly_drive', old['payload'])
        def replay(robot):
            robot.send('fly_drive', old['payload'])
        robot = Robot()
        robot.run([lambda r: r.send('mode','fly'), drive] + [None]*7 + [replay, None])
        self.assertGreater(len(robot.moves), 0)
        self.assertTrue(robot.stopped)
        self.assertEqual(robot.state['fly_wheels'], (0,0))

    def test_old_session_and_excessive_pwm_are_rejected(self):
        def invalid(robot):
            robot.send('fly_drive', self.command(robot, session='old'))
            robot.send('fly_drive', self.command(robot, left=100))
            robot.send('fly_drive', self.command(robot, frame=True))
        robot=Robot();robot.run([lambda r:r.send('mode','fly'),invalid,None])
        self.assertEqual(robot.moves,[])

    def test_mode_change_cancels_neural_movement(self):
        robot=Robot()
        robot.run([lambda r:r.send('mode','fly'),lambda r:r.send('fly_drive',self.command(r)),lambda r:r.send('mode','manual'),None])
        self.assertTrue(robot.stopped)
        self.assertEqual(robot.state['mode'],'manual')
        self.assertIsNone(robot.state['fly_pending'])

    def test_network_failure_stops_robot_and_preserves_error_after_reconnection(self):
        def failure(robot):
            raise OSError('Lecture MQTT interrompue')
        robot=Robot()
        robot.run([lambda r:r.send('mode','fly'),
                   lambda r:r.send('fly_drive',self.command(r)),failure]+[None]*15)
        self.assertTrue(robot.stopped)
        self.assertEqual(robot.state['mode'],'idle')
        self.assertIsNone(robot.state['fly_pending'])
        statuses=[json.loads(p) for t,p in robot.published if t.endswith('/status')]
        fault=statuses[-1]['last_error']
        self.assertEqual(fault['stage'],'mqtt_loop')
        self.assertIn('Lecture MQTT interrompue',fault['message'])


class BrainTests(unittest.TestCase):
    def fixture(self):
        # Petit réseau exclusivement destiné aux tests de contrats.
        brain=FlyBrain('/missing');brain.np=np
        brain.weight=sp.csr_matrix(([1.,1.],([2,3],[0,1])),shape=(4,4),dtype=np.float32)
        brain.groups={'vision_L':np.array([0]),'vision_R':np.array([1]),'motor_L':np.array([2]),'motor_R':np.array([3])}
        brain.x=np.zeros(4,np.float32);brain.state['status']='ready'
        return brain

    def test_rest_without_input_and_delayed_motor_response(self):
        brain=self.fixture();empty=dict(left=False,right=False,front=False,back=False)
        self.assertEqual(brain.tick(empty)['left'],0)
        left=dict(empty,left=True)
        self.assertEqual(brain.tick(left)['speed'],0)
        result=brain.tick(left)
        self.assertGreater(result['speed'],0)
        self.assertGreater(result['motor_L'],result['motor_R'])
        self.assertTrue(all(abs(result[k])<=45 for k in ('left','right')))

    def test_front_guard_keeps_turn_but_removes_translation(self):
        brain=self.fixture();brain.tick(dict(left=True,right=False,front=False,back=False))
        result=brain.tick(dict(left=False,right=False,front=True,back=False))
        self.assertTrue(result['guard'])
        self.assertEqual(result['left']+result['right'],0)

    def test_missing_data_never_loads_synthetic_model(self):
        with tempfile.TemporaryDirectory() as tmp:
            brain=FlyBrain(tmp)
            self.assertEqual(brain.load()['status'],'error')
            self.assertIsNone(brain.weight)
            with self.assertRaises(RuntimeError):brain.tick({})

    def test_reset_clears_activity(self):
        brain=self.fixture();brain.tick(dict(left=True,right=False,front=False,back=False));brain.reset()
        self.assertTrue(np.all(brain.x==0));self.assertEqual(brain.state['steps'],0)
        self.assertEqual(brain.state['vision_L'],0)
        self.assertFalse(brain.state['guard'])

    def test_activity_contains_real_values_and_probe_does_not_change_live_state(self):
        brain=self.fixture();sensors=dict(left=True,right=False,front=False,back=False)
        initial=brain.x.copy();state=brain.snapshot()
        frames=brain.probe(sensors,steps=8)
        np.testing.assert_array_equal(brain.x,initial)
        self.assertEqual(brain.snapshot(),state)
        self.assertEqual(len(frames),8)
        self.assertGreater(frames[-1]['active_count'],0)
        self.assertAlmostEqual(frames[0]['sensory']['L'][0]['value'],float(.3*np.tanh(4)),places=5)
        self.assertGreater(frames[-1]['motor_neurons'][0]['value'],0)
        brain.tick(sensors);brain.reset()
        self.assertEqual(brain.snapshot()['active_count'],0)
        self.assertEqual(brain.snapshot()['top_neurons'],[])


class ControlTests(unittest.TestCase):
    def setUp(self):
        self.app=load('control_tests','server/control-dashboard/fastapi-dashboard/app.py')
        self.messages=[]
        self.app._publish=lambda topic,payload:(self.messages.append((topic,payload)) or True)
        self.app._state.update(connected=True,last_seen_mono=time.monotonic(),mode='exploration')
        self.app._state['control'].update(active='exploration',revision=4)

    def test_missing_and_interrupted_observations_have_distinct_diagnostics(self):
        a=self.app
        a.time=types.SimpleNamespace(monotonic=lambda:100.0)
        async def check(observation, expected):
            a._state.update(mode='fly',connected=True,last_seen_mono=100.0,
                            control_changed=90.0,fly_seen=98.4,fly_observation=observation)
            a._state['control'].update(active='fly')
            task=asyncio.create_task(a._control_loop())
            try:
                await asyncio.sleep(.08)
                self.assertEqual(a._state['control']['paused'],'fly')
                self.assertIn(expected,a._state['control']['reason'])
                self.assertFalse(any(t.endswith('/fly_drive') for t,p in self.messages))
            finally:
                task.cancel()
                try:await task
                except asyncio.CancelledError:pass
        asyncio.run(check(None,'aucune observation'))
        asyncio.run(check({'session':'x','frame':17},'dernière trame : 17'))

    def test_start_fly_resets_observation_diagnostics(self):
        a=self.app
        a._state.update(fly_seen=12.0,fly_received=8,fly_sent=7,fly_expired=1)
        a._set_active('fly')
        for key in ('fly_seen','fly_received','fly_sent','fly_expired'):
            self.assertEqual(a._state[key],0)

    def test_manual_requires_confirmation_then_pauses_without_moving(self):
        a=self.app
        with self.assertRaises(a.HTTPException) as error:
            asyncio.run(a.cmd_move(a.MoveCmd(direction='forward',revision=4)))
        self.assertTrue(error.exception.detail['confirmation_required'])
        self.assertEqual(self.messages,[])
        asyncio.run(a.takeover(a.TakeoverCmd(revision=4)))
        self.assertEqual(a._state['control']['paused'],'exploration')
        self.assertEqual(a._state['control']['active'],'manual')
        self.assertEqual(self.messages,[('elio/command/mode','manual')])

    def test_stale_confirmation_and_old_manual_request_are_rejected(self):
        a=self.app
        with self.assertRaises(a.HTTPException):asyncio.run(a.takeover(a.TakeoverCmd(revision=3)))
        asyncio.run(a.stop())
        with self.assertRaises(a.HTTPException):asyncio.run(a.cmd_move(a.MoveCmd(direction='forward',revision=4)))
        self.assertNotIn(('elio/command/move','forward'),self.messages)

    def test_start_autonomy_disables_manual_and_pause_preserves_history(self):
        a=self.app;a._state['control']['active']='manual';a._state['steps'].append({'x':2})
        asyncio.run(a.autonomy(a.AutonomyCmd(mode='exploration',action='start')))
        self.assertEqual(a._state['control']['active'],'exploration')
        asyncio.run(a.autonomy(a.AutonomyCmd(mode='exploration',action='pause')))
        self.assertEqual(a._state['control']['paused'],'exploration')
        self.assertEqual(len(a._state['steps']),1)

    def test_fly_requires_loaded_model_and_compatible_robot(self):
        a=self.app
        with self.assertRaises(a.HTTPException):asyncio.run(a.autonomy(a.AutonomyCmd(mode='fly',action='start')))
        a.brain.state['status']='ready'
        with self.assertRaises(a.HTTPException):asyncio.run(a.autonomy(a.AutonomyCmd(mode='fly',action='start')))
        a._state['status']['protocol']=2
        asyncio.run(a.autonomy(a.AutonomyCmd(mode='fly',action='start')))
        self.assertEqual(a._state['control']['active'],'fly')

    def test_calculation_finishing_after_pause_cannot_send_a_drive_command(self):
        a=self.app;entered=threading.Event();resume=threading.Event()
        def calculate(sensors):
            entered.set();resume.wait(2);return {'left':30,'right':30}
        a.brain.tick=calculate
        a._state.update(mode='fly',control_changed=time.monotonic(),fly_seen=time.monotonic(),fly_observation={'session':'x','frame':1})
        a._state['control']['active']='fly'
        async def scenario():
            task=asyncio.create_task(a._control_loop())
            try:
                self.assertTrue(await asyncio.to_thread(entered.wait,1))
                await a.stop()
                resume.set()
                await asyncio.sleep(.1)
                self.assertFalse(any(t.endswith('/fly_drive') for t,p in self.messages))
            finally:
                resume.set();task.cancel()
                try:await task
                except asyncio.CancelledError:pass
        asyncio.run(scenario())

    def test_pages_protocol_and_probe_never_publish_motor_commands(self):
        a=self.app
        self.assertEqual(a._snapshot()['protocol'],3)
        self.assertIn('data-page="fly"',asyncio.run(a.fly_page()))
        self.assertIn('data-page="control"',asyncio.run(a.root()))
        a.brain.state['status']='ready'
        a.brain.probe=lambda sensors:[{'steps':1,'left':30,'right':30}]
        result=asyncio.run(a.probe_fly(a.ProbeCmd(stimulus='left')))
        self.assertEqual(result['source'],'simulation')
        self.assertEqual(self.messages,[])
        a._state['control']['active']='fly'
        with self.assertRaises(a.HTTPException):asyncio.run(a.probe_fly(a.ProbeCmd(stimulus='front')))

    def test_failed_publish_does_not_activate_a_mode(self):
        a=self.app;a._publish=lambda *args:False;a._state['control']['active']='idle'
        with self.assertRaises(a.HTTPException):asyncio.run(a.autonomy(a.AutonomyCmd(mode='exploration',action='start')))
        self.assertEqual(a._state['control']['active'],'idle')


if __name__=='__main__':unittest.main()
