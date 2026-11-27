from ctypes import addressof, wintypes
from pathlib import Path
import struct
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QByteArray, QEvent, QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import chat_window
from pet import GlobalHotkey
import voice_input


@unittest.skipUnless(sys.platform == 'win32', 'Windows voice input')
class VoiceInputTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['voice-tests', '-platform', 'offscreen'])

    def wait_for(self, condition):
        for _ in range(160):
            if condition():
                return
            QTest.qWait(10)
        self.fail('Voice input did not reach the expected state')

    def test_global_recording_key_stops_when_a_modifier_is_released(self):
        events = []
        hotkey = GlobalHotkey(3, 'Ctrl+Alt+F9', lambda: events.append('press') or True,
                              on_release=lambda: events.append('release'))
        keys_down = {0x11, 0x12, 0x78}
        hotkey.user32 = SimpleNamespace(RegisterHotKey=lambda *args: True,
                                       UnregisterHotKey=lambda *args: True,
                                       GetAsyncKeyState=lambda key: 0x8000 if key in keys_down else 0)
        self.assertTrue(hotkey.enable())
        self.addCleanup(hotkey.disable)

        event = wintypes.MSG()
        event.message = 0x0312
        event.wParam = 3
        handled, _ = hotkey.nativeEventFilter(QByteArray(b'windows_generic_MSG'), addressof(event))
        self.assertTrue(handled)
        self.wait_for(lambda: events == ['press'])
        keys_down.remove(0x12)
        self.wait_for(lambda: events == ['press', 'release'])
        hotkey.trigger()
        self.assertEqual(events, ['press', 'release'])

    def test_selected_microphone_is_resolved_again_at_capture_time(self):
        def microphone(key, index):
            return voice_input.InputDevice(key, '测试麦克风', index)

        with patch.object(voice_input, 'input_devices', return_value=[
                microphone('usb-headset', 2), microphone('builtin', 0)]):
            self.assertEqual(voice_input.input_index(None, 'usb-headset'), 2)
            self.assertEqual(voice_input.input_index(None, ''), 0xFFFFFFFF)
            with self.assertRaisesRegex(RuntimeError, '未连接'):
                voice_input.input_index(None, 'removed')

    def test_quick_chat_keeps_capture_outside_focus_and_prepares_an_editable_draft(self):
        owner = QWidget()
        owner.role = '雏龙娘'
        values = {}
        owner.settings = SimpleNamespace(
            value=values.get, setValue=values.__setitem__, sync=lambda: None,
            status=lambda: QSettings.NoError,
        )
        chat = SimpleNamespace(pending=None, quick_finished=Mock(),
                               start_message=Mock(return_value=False), status=Mock())
        chat.status.text.return_value = ''
        clip = struct.pack('<h', 10_000) * (voice_input.RATE // 3)
        mic = SimpleNamespace(prepare=lambda: None, start=lambda: None,
                              read=lambda: clip, stop=lambda: b'')

        with (patch.object(chat_window, 'input_devices', return_value=[
                  voice_input.InputDevice('usb-headset', '测试麦克风', 2)]),
              patch.object(voice_input, 'Microphone', return_value=mic) as open_mic):
            quick = chat_window.QuickChat(owner, chat)
            self.addCleanup(owner.deleteLater)
            self.addCleanup(quick.close)
            quick.present()
            quick.microphone.setCurrentIndex(quick.microphone.findData('usb-headset'))
            self.assertEqual(values['voice_input_device'], 'usb-headset')

            self.assertTrue(quick.start_voice('global'))
            self.wait_for(lambda: quick.level.value() > 0)
            open_mic.assert_called_once_with('usb-headset')
            QApplication.sendEvent(quick, QEvent(QEvent.WindowDeactivate))
            self.assertEqual(quick.voice.state, 'recording')
            with patch.object(quick.voice, 'transcribe') as transcribe:
                quick.stop_voice('global')
                self.wait_for(lambda: transcribe.called)
                self.assertTrue(transcribe.call_args.args[0].startswith(b'RIFF'))
            self.assertEqual(quick.level.value(), 0)

        quick.voice.recognized.emit('测试草稿')
        self.assertEqual(quick.input.text(), '测试草稿')
        self.assertFalse(chat.start_message.called)
        quick.input.setText('修改过的草稿')
        quick.send()
        chat.start_message.assert_called_once_with('修改过的草稿', quick=True)
