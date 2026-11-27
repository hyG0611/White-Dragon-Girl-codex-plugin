from datetime import datetime
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QTimer
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import chat_window
from widgets import DesktopWidgets


class ChatToolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['chat-tool-tests', '-platform', 'offscreen'])

    def setUp(self):
        pet = self.pet = QWidget()
        pet.settings = Mock()
        pet.settings.value.side_effect = lambda key, default=None, **_: default
        pet.todos = []
        pet.save_todos = Mock(return_value=True)
        pet.notify = Mock()
        pet.play_reaction = Mock()
        pet.widgets = DesktopWidgets(pet)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.addCleanup(pet.deleteLater)
        self.addCleanup(pet.widgets.closed.set)
        with patch.object(chat_window, 'history_path', return_value=Path(directory.name) / 'history.json'):
            self.chat = chat_window.ChatWindow(pet)
        self.addCleanup(self.chat.close)
        self.chat.show()

    def wait_for_reply(self, seconds=4):
        for _ in range(seconds * 50):
            if self.chat.pending is None:
                return
            QTest.qWait(20)
        self.fail('The chat did not receive a local result')

    def test_chat_looks_up_chengdu_without_a_configured_model(self):
        forecast = '成都\n气温 15.2°C，体感 14.8°C\n湿度 60%\n数据时间 2026-11-27 10:00'
        with patch('widgets.current_weather', return_value=forecast) as weather:
            self.assertTrue(self.chat.start_message('帮我查一下成都今天天气'), self.chat.status.text())
            self.wait_for_reply()
        weather.assert_called_once_with('成都')
        self.assertEqual(self.chat.selected_history()[-1]['answer'], forecast)
        self.assertIn(forecast, self.pet.notify.call_args.args)
        self.assertTrue(self.pet.notify.call_args.kwargs['open_chat'])

    def test_quick_chat_shows_the_account_quota_without_a_model_request(self):
        usage = 'Codex 剩余额度\n5 小时：62.0%'
        quota = SimpleNamespace(fetch=lambda **_: [{'used_percent': 38}], format_usage=lambda _: usage)
        reply = []
        self.chat.quick_finished.connect(lambda text, success, important: reply.append((text, success, important)))
        with patch.dict(sys.modules, {'codex_quota': quota}):
            self.assertTrue(self.chat.start_message('我还剩多少 Codex 额度？', quick=True), self.chat.status.text())
            self.wait_for_reply()
        self.assertEqual(reply, [(usage, True, True)])
        self.assertEqual(self.chat.selected_history()[-1]['answer'], usage)

    def test_following_model_message_does_not_include_local_query_data(self):
        usage = 'Codex 剩余额度\n5 小时：62.0%'
        quota = SimpleNamespace(fetch=lambda **_: [{'used_percent': 38}], format_usage=lambda _: usage)
        with patch.dict(sys.modules, {'codex_quota': quota}):
            self.assertTrue(self.chat.start_message('查额度'))
            self.wait_for_reply()
        with patch.object(self.chat.request, 'start') as start:
            question = '解释一下 Codex 额度是什么'
            self.assertTrue(self.chat.start_message(question))
            self.assertEqual(start.call_args.args[3], [{'role': 'user', 'content': question}])
            self.chat.fail('结束测试')

    def test_workday_reminder_is_saved_only_after_confirming_the_preview(self):
        for accept in (False, True):
            with self.subTest(accept=accept):
                question = '工作日九点提醒我喝水'
                self.assertTrue(self.chat.start_message(question, quick=True), self.chat.status.text())
                snapshots = []
                timer = QTimer(self.chat)

                def respond():
                    dialog = self.app.activeModalWidget()
                    if dialog is None:
                        return
                    timer.stop()
                    snapshots.append(len(self.pet.todos))
                    box = dialog.findChild(QDialogButtonBox)
                    save = box.button(QDialogButtonBox.Save) if box is not None else None
                    if accept and save is not None and save.isEnabled():
                        save.click()
                    else:
                        dialog.reject()

                timer.timeout.connect(respond)
                timer.start(40)
                try:
                    self.wait_for_reply()
                finally:
                    timer.stop()
                    timer.deleteLater()
                self.assertEqual(snapshots, [0])
                self.assertEqual(len(self.pet.todos), int(accept))
        todo = self.pet.todos[0]
        self.assertEqual(todo['text'], '喝水')
        self.assertEqual(todo['repeat'], 'weekdays')
        date = datetime.fromtimestamp(todo['due'])
        self.assertLess(date.weekday(), 5)
        self.assertEqual((date.hour, date.minute), (9, 0))
        self.assertIn('已添加', self.chat.selected_history()[-1]['answer'])
