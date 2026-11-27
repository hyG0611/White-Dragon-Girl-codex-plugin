import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtCore import QSettings
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QComboBox, QDialog, QLineEdit

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import chat_window
import codex_chat


class CodexChatSettingsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['codex-chat-tests', '-platform', 'offscreen'])

    def chat(self, values):
        settings = Mock()
        settings.value.side_effect = lambda key, default=None, **options: values.get(key, default)
        settings.setValue.side_effect = values.__setitem__
        settings.status.return_value = QSettings.NoError
        return self.chat_with_settings(settings)

    def chat_with_settings(self, settings):
        pet = chat_window.PetDialog(None)
        pet.settings = settings
        self.addCleanup(pet.deleteLater)
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        with patch.object(chat_window, 'history_path', return_value=Path(directory.name) / 'chat.json'):
            dialog = chat_window.ChatWindow(pet)
        self.addCleanup(dialog.close)
        return dialog

    def test_selecting_codex_keeps_existing_api_preferences(self):
        values = {'chat_endpoint': 'https://example.test/v1', 'chat_model': 'example-model'}
        dialog = self.chat(values)

        def select_account(settings_dialog):
            provider = next((box for box in settings_dialog.findChildren(QComboBox)
                             if box.findData('codex') >= 0), None)
            self.assertIsNotNone(provider, 'The desktop settings need a signed-in Codex option')
            provider.setCurrentIndex(provider.findData('codex'))
            return QDialog.Accepted

        with patch.object(chat_window.PetDialog, 'exec', select_account):
            dialog.configure()

        self.assertEqual(dialog.backend, 'codex')
        self.assertEqual(values['chat_endpoint'], 'https://example.test/v1')
        self.assertEqual(values['chat_model'], 'example-model')

    @unittest.skipUnless(sys.platform == 'win32', 'Windows user encryption')
    def test_saved_api_key_is_available_when_a_new_window_loads_the_settings(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        filename = Path(directory.name) / 'preferences.ini'
        settings = QSettings(str(filename), QSettings.IniFormat)
        window = self.chat_with_settings(settings)
        fixture_key = 'dsh-restart-test-token'

        def fill(settings_dialog):
            values = {'接口地址': 'https://api.example.test/v1', '模型名称': 'fixture-model',
                      'API Key（可选）': fixture_key}
            for field in settings_dialog.findChildren(QLineEdit):
                field_label = settings_dialog.layout().labelForField(field)
                if field_label and field_label.text() in values:
                    field.setText(values[field_label.text()])
            return QDialog.Accepted

        with patch.object(chat_window.PetDialog, 'exec', fill):
            window.configure()
        window.close()
        settings.sync()
        reloaded = self.chat_with_settings(QSettings(str(filename), QSettings.IniFormat))
        self.assertEqual(reloaded.backend, 'api')
        self.assertEqual(reloaded.endpoint, 'https://api.example.test/v1')
        self.assertEqual(reloaded.model, 'fixture-model')
        self.assertEqual(reloaded.key, fixture_key)
        self.assertNotIn(fixture_key, filename.read_text(encoding='utf8'))

    def run_conversation(self, dialog, account_type):
        arguments = (str(Path(__file__).resolve()), '--codex-fixture', account_type)
        with (patch.object(codex_chat, 'codex_executable', return_value=Path(sys.executable)),
              patch.object(codex_chat, 'SERVER_ARGS', arguments),
              patch.dict(os.environ, {'OPENAI_API_KEY': 'fixture-key', 'CODEX_API_KEY': 'fixture-key'})):
            self.assertTrue(dialog.start_message('你好', quick=True), dialog.status.text())
            for _ in range(250):
                if dialog.pending is None:
                    return
                QTest.qWait(20)
        self.fail('Codex request did not complete')

    def test_quick_chat_uses_the_signed_in_account_without_api_settings(self):
        dialog = self.chat({'chat_backend': 'codex', 'chat_codex_model': 'gpt-6.2-sol'})
        replies = []
        dialog.quick_finished.connect(lambda text, success: replies.append((text, success)))
        self.run_conversation(dialog, 'chatgpt')
        self.assertEqual(replies, [('白龙在线', True)])
        self.assertEqual(dialog.selected_history(), [{'question': '你好', 'answer': '白龙在线'}])

    def test_api_key_login_requires_chatgpt_sign_in_before_sending_the_prompt(self):
        dialog = self.chat({'chat_backend': 'codex'})
        self.run_conversation(dialog, 'apiKey')
        self.assertIn('使用 ChatGPT 账号登录', dialog.status.text())
        self.assertEqual(dialog.selected_history(), [])


def codex_fixture(account_type):
    def send(message):
        print(json.dumps(message), flush=True)

    assert 'OPENAI_API_KEY' not in os.environ and 'CODEX_API_KEY' not in os.environ
    for line in sys.stdin.buffer:
        packet = json.loads(line)
        method, params = packet['method'], packet.get('params', {})
        if method == 'initialized':
            continue
        if method == 'initialize':
            result = {}
        elif method == 'account/read':
            result = {'account': {'type': account_type}}
        elif method == 'thread/start' and account_type == 'chatgpt':
            assert params['ephemeral'] and params['environments'] == [] and params['model'] == 'gpt-6.2-sol'
            result = {'thread': {'id': 'a', 'ephemeral': True}, 'modelProvider': 'openai',
                      'approvalPolicy': 'never', 'sandbox': {'type': 'readOnly'}}
        elif method == 'turn/start' and account_type == 'chatgpt':
            assert params['input'] == [{'type': 'text', 'text': '你好'}]
            send({'id': packet['id'], 'result': {'turn': {'id': 't'}}})
            send({'method': 'item/agentMessage/delta', 'params': {'threadId': 'a', 'turnId': 't', 'delta': '白龙'}})
            send({'method': 'item/completed', 'params': {
                'threadId': 'a', 'turnId': 't', 'item': {'type': 'agentMessage', 'text': '白龙在线'},
            }})
            send({'method': 'turn/completed', 'params': {'threadId': 'a', 'turn': {'id': 't', 'status': 'completed'}}})
            continue
        else:
            raise AssertionError(f'Unexpected request: {method}')
        send({'id': packet['id'], 'result': result})


if __name__ == '__main__' and sys.argv[1:2] == ['--codex-fixture']:
    codex_fixture(sys.argv[2])
