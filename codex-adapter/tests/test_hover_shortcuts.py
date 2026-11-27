from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QColor, QEnterEvent, QPainter, QPixmap, QTransform
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
from hover_shortcuts import HoverShortcuts


class HoverShortcutsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['hover-shortcuts-test', '-platform', 'offscreen'])

    def setUp(self):
        self.pet = QWidget(None, Qt.Tool | Qt.FramelessWindowHint)
        self.pet.resize(480, 320)
        area = self.pet.screen().availableGeometry()
        self.pet.move(area.right() - 320, area.top() + 8)
        self.pet.owner = SimpleNamespace(open_quick_chat=Mock(), edit_todos=Mock(),
                                         widgets=SimpleNamespace(request_quota=Mock()))
        self.pet.offset = None
        self.pet.pause_walk = Mock()
        self.pet.sprite_transform = lambda: QTransform.fromTranslate(240, 185)
        self.pet.pixmap = QPixmap(480, 270)
        self.pet.pixmap.fill(Qt.transparent)
        with QPainter(self.pet.pixmap) as painter:
            painter.fillRect(32, 32, 400, 200, QColor(210, 200, 235, 8))
            painter.fillRect(168, 80, 144, 100, QColor('#cec3f2'))
        self.bar = HoverShortcuts(self.pet)
        self.bar.dismiss()
        self.pet.show()
        self.addCleanup(self.pet.close)
        self.cursor = self.pet.mapToGlobal(QPoint(240, 180))
        cursor_patch = patch('hover_shortcuts.QCursor', SimpleNamespace(pos=lambda: self.cursor))
        cursor_patch.start()
        self.addCleanup(cursor_patch.stop)

    def enter(self, widget):
        widget.setAttribute(Qt.WA_UnderMouse, True)
        point = QPointF(widget.mapFromGlobal(self.cursor))
        QApplication.sendEvent(widget, QEnterEvent(point, point, QPointF(self.cursor)))

    def show_bar(self):
        self.enter(self.pet)
        self.assertTrue(self.bar.reveal_timer.isActive())
        self.bar.reveal_timer.stop()
        self.bar.reveal()
        self.assertTrue(self.bar.isVisible())

    def test_hover_handoff_and_screen_edge(self):
        self.show_bar()
        self.assertEqual(self.bar.body, QRect(168, 130, 144, 100).translated(self.pet.mapToGlobal(QPoint())))
        self.assertTrue(self.pet.screen().availableGeometry().contains(self.bar.geometry()))
        self.assertLess(self.bar.geometry().right(), self.bar.body.left())
        self.pet.setAttribute(Qt.WA_UnderMouse, False)
        QApplication.sendEvent(self.pet, QEvent(QEvent.Leave))
        self.assertTrue(self.bar.isVisible())
        self.assertTrue(self.bar.dismiss_timer.isActive())
        self.cursor = self.bar.geometry().center()
        self.enter(self.bar)
        self.assertFalse(self.bar.dismiss_timer.isActive())
        self.bar.setAttribute(Qt.WA_UnderMouse, False)
        self.cursor = QPoint(0, 0)
        self.bar.dismiss_if_outside()
        self.assertTrue(self.bar.isHidden())

    def test_empty_pixels_and_click_through_do_not_reveal(self):
        self.cursor = self.pet.mapToGlobal(QPoint(40, 180))
        self.enter(self.pet)
        self.bar.reveal()
        self.assertTrue(self.bar.isHidden())
        self.pet.setWindowFlag(Qt.WindowTransparentForInput)
        self.pet.show()
        self.cursor = self.pet.mapToGlobal(QPoint(240, 180))
        self.enter(self.pet)
        self.assertFalse(self.bar.reveal_timer.isActive())
        self.bar.reveal()
        self.assertTrue(self.bar.isHidden())

    def test_buttons_route_from_a_second_pet_and_dismiss_the_bar(self):
        for name, callback, arguments in (
            ('chat', self.pet.owner.open_quick_chat, {}),
            ('todos', self.pet.owner.edit_todos, {}),
            ('quota', self.pet.owner.widgets.request_quota, {'target': self.pet}),
        ):
            self.show_bar()
            QTest.mouseClick(self.bar.buttons[name], Qt.LeftButton)
            callback.assert_called_once_with(**arguments)
            self.assertTrue(self.bar.isHidden())
