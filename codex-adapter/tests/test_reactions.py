from pathlib import Path
import json
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import pet as runtime


class ReactionTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['reaction-tests', '-platform', 'offscreen'])

    def setUp(self):
        settings = Mock()
        settings.value.side_effect = lambda name, default=None, **_: (
            False if name in ('auto', 'quick_chat_hotkey') else default
        )
        pool = Mock()
        pool.acquire.return_value = SimpleNamespace(read=lambda: None, finished=False)
        with (patch.object(runtime, 'QSettings', return_value=settings),
              patch.object(runtime, 'ClipPool', return_value=pool),
              patch.object(runtime, 'QLocalServer', return_value=Mock()),
              patch.object(runtime, 'local_roles', return_value=runtime.ROOT / 'unused-test-roles'),
              patch.object(runtime.Pet, 'create_tray')):
            self.pet = runtime.Pet()
        self.pet.tray = None
        self.addCleanup(self.pet.deleteLater)
        self.addCleanup(self.pet.close)
        self.addCleanup(self.pet.widgets.closed.set)
        self.pet.show()

    def load_actions(self, *names):
        actions = {name: Path(name + '.mp4') for name in (self.pet.idle, *names)}
        with patch.object(runtime, 'role_actions', return_value=(actions, self.pet.idle)):
            self.pet.switch_role(self.pet.role)

    def receive(self, command, **arguments):
        socket = Mock()
        socket.readLine.return_value = json.dumps({'command': command, **arguments}).encode()
        self.pet.receive(socket)
        return json.loads(socket.write.call_args.args[0])

    def await_quota(self, quota):
        with patch.dict(sys.modules, {'codex_quota': quota}):
            self.pet.widgets.request_quota()
            for _ in range(100):
                if not self.pet.widgets.quota_poll.isActive():
                    return
                QTest.qWait(10)
        self.fail('Quota result did not reach the desktop pet')

    def test_context_uses_the_assets_available_to_the_current_role(self):
        for thinking, working, attention in (
            ('深度思考碎碎念', '写代码', '东张西望'),
            ('工作状态-思考冒泡', '工作状态-忙碌点按', '工作状态-原地踱步张望'),
        ):
            with self.subTest(thinking=thinking):
                self.load_actions(thinking, working, attention)
                self.assertEqual(self.receive('activity', activity='thinking')['animation'], thinking)
                self.assertEqual(self.receive('activity', activity='working')['animation'], working)
                self.assertEqual(self.receive('activity', activity='attention')['animation'], attention)
                self.assertEqual(self.receive('activity', activity='idle')['animation'], self.pet.idle)

    def test_repeated_work_hint_does_not_restart_a_finished_reaction(self):
        self.load_actions('写代码')
        self.assertEqual(self.receive('activity', activity='working', session_id='a')['animation'], '写代码')
        self.pet.play(self.pet.idle)
        self.assertEqual(self.receive('activity', activity='working', session_id='b')['animation'], self.pet.idle)

    def test_line_and_animation_continue_across_work_updates(self):
        self.load_actions('写代码', '点击回应-元气挥手')
        self.receive('activity', activity='working')
        result = self.receive('say', text='你好！', animation='点击回应-元气挥手')
        self.assertEqual(result['animation'], '点击回应-元气挥手')
        self.assertEqual(self.pet.message, '你好！')
        self.receive('activity', activity='working')
        self.assertEqual(self.pet.message, '你好！')
        result = self.receive('activity', activity='idle')
        self.assertEqual(result['animation'], '点击回应-元气挥手')
        self.assertEqual(self.pet.message, '你好！')

    def test_quota_reacts_to_the_window_with_the_least_remaining_usage(self):
        self.load_actions('余额-分文不剩', '余额-钱袋满溢')
        quota = SimpleNamespace(
            fetch=lambda **_: [
                {'label': '5 小时', 'used_percent': 12, 'resets_at': None},
                {'label': '一周', 'used_percent': 100, 'resets_at': None},
            ],
            format_usage=lambda _: 'Codex 剩余额度\n5 小时：88.0%\n一周：0.0%',
        )
        self.await_quota(quota)
        self.assertEqual(self.pet.current, '余额-分文不剩')
        self.assertIn('一周：0.0%', self.pet.message)

    def test_quota_error_shows_a_message_without_changing_the_animation(self):
        self.load_actions('余额-分文不剩', '余额-钱袋满溢')
        quota = SimpleNamespace(fetch=Mock(side_effect=RuntimeError('查询超时，请重试。')))
        self.await_quota(quota)
        self.assertEqual(self.pet.current, self.pet.idle)
        self.assertIn('查询超时', self.pet.message)
