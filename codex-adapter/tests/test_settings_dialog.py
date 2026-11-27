from pathlib import Path
import sys
import unittest

from PySide6.QtCore import QPoint, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins' / 'dsh-dragon' / 'runtime'))
from dialogs import HotkeyEdit
from pet_window import PetDialog


class SettingsDialogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['settings-dialog-test', '-platform', 'offscreen'])

    def test_dialog_opens_outside_the_pet_and_stays_on_top(self):
        owner = QWidget(None, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)
        owner.resize(320, 220)
        area = owner.screen().availableGeometry()
        owner.move(area.bottomRight() - QPoint(owner.width() - 1, owner.height() - 1))
        owner.show()
        dialog = PetDialog(owner)
        dialog.resize(240, 120)
        try:
            dialog.show()
            self.app.processEvents()
            self.assertTrue(dialog.windowFlags() & Qt.WindowStaysOnTopHint)
            self.assertTrue(area.contains(dialog.frameGeometry()))
            self.assertFalse(dialog.frameGeometry().intersects(owner.frameGeometry()))
        finally:
            dialog.close()
            owner.close()

    def test_hotkey_edit_preserves_display_until_a_complete_chord(self):
        editor = HotkeyEdit('Ctrl+Meta+J')
        recorded = []
        invalid = []
        editor.recorded.connect(recorded.append)
        editor.invalid.connect(lambda: invalid.append(True))

        QTest.keyClick(editor, Qt.Key_Control)
        self.assertEqual(editor.text(), 'Ctrl+Win+J')
        self.assertFalse(recorded or invalid)

        QTest.keyClick(editor, Qt.Key_K)
        self.assertEqual(editor.text(), 'Ctrl+Win+J')
        self.assertEqual(invalid, [True])

        QTest.keyClick(editor, Qt.Key_K, Qt.ControlModifier | Qt.AltModifier)
        self.assertEqual(editor.text(), 'Ctrl+Alt+K')
        self.assertEqual(recorded, ['Ctrl+Alt+K'])

    def test_recording_hotkey_displays_function_key_in_the_saved_chord(self):
        editor = HotkeyEdit('Ctrl+Alt+F9', allow_function_keys=True)
        recorded = []
        invalid = []
        editor.recorded.connect(recorded.append)
        editor.invalid.connect(lambda: invalid.append(True))

        QTest.keyClick(editor, Qt.Key_F12, Qt.ControlModifier | Qt.AltModifier)
        self.assertEqual(editor.text(), 'Ctrl+Alt+F9')
        self.assertEqual(invalid, [True])

        QTest.keyClick(editor, Qt.Key_F8, Qt.ControlModifier | Qt.ShiftModifier)
        self.assertEqual(editor.text(), 'Ctrl+Shift+F8')
        self.assertEqual(recorded, ['Ctrl+Shift+F8'])
