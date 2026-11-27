from pathlib import Path
import sys
from time import time
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPointF, Qt, QSettings
from PySide6.QtGui import QMouseEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import pet as runtime


class CloudBubbleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['cloud-bubble-tests', '-platform', 'offscreen'])

    def setUp(self):
        settings = Mock()
        settings.value.side_effect = lambda name, default=None, **_: (
            False if name in ('auto', 'quick_chat_hotkey') else default
        )
        settings.status.return_value = QSettings.NoError
        pool = Mock()
        pool.acquire.return_value = SimpleNamespace(read=lambda: None, finished=False)
        with (patch.object(runtime, 'QSettings', Mock(return_value=settings, NoError=QSettings.NoError)),
              patch.object(runtime, 'ClipPool', return_value=pool),
              patch.object(runtime, 'QLocalServer', return_value=Mock()),
              patch.object(runtime, 'local_roles', return_value=runtime.ROOT / 'unused-cloud-test-roles'),
              patch.object(runtime.Pet, 'create_tray')):
            self.pet = runtime.Pet()
        self.pet.tray = None
        self.pet.show()
        self.addCleanup(self.pet.deleteLater)
        self.addCleanup(self.pet.close)
        self.addCleanup(self.pet.widgets.closed.set)

    def move_pointer(self, point):
        global_point = QPointF(self.pet.mapToGlobal(point.toPoint()))
        event = QMouseEvent(QEvent.MouseMove, point, global_point, Qt.NoButton, Qt.NoButton, Qt.NoModifier)
        QApplication.sendEvent(self.pet, event)

    def test_hover_pauses_expiry_and_leaving_the_cloud_resumes_it(self):
        self.pet.say('请先读完这一条。', duration=250)
        QTest.qWait(120)
        self.move_pointer(self.pet.cloud_bubble().edge.center())
        self.assertFalse(self.pet.bubble_timer.isActive())
        QTest.qWait(280)
        self.assertEqual(self.pet.message, '请先读完这一条。')
        self.move_pointer(QPointF(5, 294))
        self.assertTrue(self.pet.bubble_timer.isActive())
        self.assertLess(self.pet.bubble_timer.remainingTime(), 200)
        QTest.qWait(180)
        self.assertFalse(self.pet.message)

    def test_bubble_size_and_font_size_are_independent(self):
        self.pet.say('你好，白龙。')
        original = self.pet.cloud_bubble()
        self.pet.apply_adjustment('bubble_size', 140)
        larger = self.pet.cloud_bubble()
        self.assertGreater(larger.edge.width(), original.edge.width())
        self.assertEqual(larger.font.pixelSize(), original.font.pixelSize())
        self.pet.apply_adjustment('bubble_font', 20)
        self.assertEqual(self.pet.cloud_bubble().font.pixelSize(), 20)
        self.assertEqual(self.pet.bubble_size, 140)

    def test_due_reminders_and_quota_are_shown_in_order_across_work_updates(self):
        self.pet.refresh_activity(('working', 1), 'working')
        self.pet.todos[:] = [
            {'text': '第一项待办', 'due': int(time()) - 1},
            {'text': '第二项待办', 'due': int(time()) - 1},
        ]
        self.pet.check_todos()
        self.pet.widgets.quota_result.put(('Codex 剩余额度\n5 小时：60.0%', ()))
        self.pet.widgets.accept_quota()
        self.pet.refresh_activity(('attention', 1), 'attention')
        self.assertEqual(self.pet.message, '第一项待办')
        self.pet.clear_message()
        self.pet.refresh_activity(('idle', 0), 'idle')
        self.assertEqual(self.pet.message, '第二项待办')
        self.pet.clear_message()
        self.pet.refresh_activity(('working', 1), 'working')
        self.assertIn('Codex 剩余额度', self.pet.message)
        self.pet.clear_message()
        self.assertFalse(self.pet.message)
