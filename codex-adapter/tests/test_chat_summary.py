import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from PySide6.QtWidgets import QApplication, QDialogButtonBox, QPlainTextEdit, QWidget

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'plugins/dsh-dragon/runtime'))
import chat_window


class ChatSummaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication(['chat-summary-tests', '-platform', 'offscreen'])

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / 'history.json'

    def window(self, backend='api'):
        pet = QWidget()
        pet.settings = Mock()
        pet.settings.value.side_effect = lambda key, default=None, **_: (
            backend if key == 'chat_backend' else default
        )
        self.addCleanup(pet.deleteLater)
        with patch.object(chat_window, 'history_path', return_value=self.path):
            dialog = chat_window.ChatWindow(pet)
        self.addCleanup(dialog.close)
        return dialog

    def finish_turn(self, dialog, question, answer, local=False):
        dialog.begin_reply(question, False, '')
        dialog.complete(answer, local=local)

    def send_and_read_context(self, dialog, question, quick=False):
        request = dialog.codex_request if dialog.backend == 'codex' else dialog.request
        with patch.object(request, 'start') as start:
            self.assertTrue(dialog.start_message(question, quick=quick), dialog.status.text())
            messages = start.call_args.args[-1]
        dialog.fail('测试已结束')
        return messages

    def test_old_decision_and_confirmed_todo_are_used_at_the_next_turn(self):
        dialog = self.window()
        self.finish_turn(dialog, '发布定在周五下午两点。待办：周四把议程发给评审。', '收到。')
        self.finish_turn(dialog, '提醒我周四发议程',
                         '已添加待办。\n事项：发议程\n提醒时间：2030-01-03 09:00:00\n重复：不重复',
                         local=True)
        self.finish_turn(dialog, '查额度', '临时额度值 PRIVATE-QUOTA-FIXTURE', local=True)
        self.finish_turn(dialog, '提醒我测试取消', '已取消添加待办。', local=True)
        for number in range(6):
            self.finish_turn(dialog, f'普通交流 {number}', f'回复 {number}')

        messages = self.send_and_read_context(self.window(), '我们之前定了什么？')
        summary = messages[0]['content']
        self.assertIn('已定事项', summary)
        self.assertIn('周五下午两点', summary)
        self.assertIn('待办', summary)
        self.assertIn('周四把议程发给评审', summary)
        self.assertIn('2030-01-03 09:00:00', summary)
        self.assertNotIn('PRIVATE-QUOTA-FIXTURE', str(messages))
        self.assertNotIn('测试取消', str(messages))
        self.assertEqual([message['content'] for message in messages[1::2]][:6],
                         [f'普通交流 {number}' for number in range(6)])

    def test_edit_loaded_session_summary_survives_restart_and_stays_in_that_session(self):
        legacy = [{'question': '会议定在周日三点。', 'answer': '收到。'}] + [
            {'question': f'交流 {number}', 'answer': f'回复 {number}'} for number in range(6)
        ]
        self.path.write_text(json.dumps([legacy], ensure_ascii=False), encoding='utf-8')
        dialog = self.window()
        edited = '已定事项\n会议改在周一上午九点。\n待办\n准备投影仪。'

        def edit(modal):
            entry = modal.findChild(QPlainTextEdit)
            self.assertIn('周日三点', entry.toPlainText())
            entry.setPlainText(edited)
            modal.findChild(QDialogButtonBox).button(QDialogButtonBox.Save).click()
            return modal.result()

        with patch.object(chat_window.PetDialog, 'exec', edit):
            dialog.summary_button.click()

        restarted = self.window(backend='codex')
        self.finish_turn(restarted, '再问一个问题', '回复完毕。')
        messages = self.send_and_read_context(restarted, '接着安排会议', quick=True)
        self.assertIn('周一上午九点', messages[0]['content'])
        self.assertIn('准备投影仪', messages[0]['content'])
        self.assertNotIn('周日三点', str(messages))

        restarted.new_session()
        self.assertEqual(self.send_and_read_context(restarted, '新对话的第一句', quick=True),
                         [{'role': 'user', 'content': '新对话的第一句'}])

    def test_old_decision_survives_when_raw_turns_are_trimmed(self):
        old_decision = {'question': '活动地点？', 'answer': '### 已定事项\n- 使用河边的 307 号会议室。'}
        turns = [old_decision] + [
            {'question': f'普通话题 {number}', 'answer': '收到。'} for number in range(52)
        ]
        self.path.write_text(json.dumps([turns], ensure_ascii=False), encoding='utf-8')
        window = self.window()
        self.assertEqual(len(window.selected_history()), 50)
        self.assertNotIn(old_decision, window.selected_history())
        self.finish_turn(window, '继续聊天', '好的。')

        messages = self.send_and_read_context(self.window(), '已选的会议室是哪一间？')
        self.assertIn('307 号会议室', messages[0]['content'])
