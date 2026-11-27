"""Standalone model chat with local text history and optional screenshot input."""
from base64 import b64encode
import json
from pathlib import Path
import sys

from PySide6.QtCore import QByteArray, QBuffer, QEvent, QIODevice, QSaveFile, QStandardPaths, QTimer, Qt, Signal
from PySide6.QtGui import QPixmap, QTextCursor
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDialogButtonBox, QFormLayout, QHBoxLayout, QLabel,
    QLineEdit, QMessageBox, QPlainTextEdit, QPushButton, QVBoxLayout,
)

from chat_api import ChatRequest, completions_url
from chat_memory import edit_memory, memory_context
from chat_preferences import load_key, read_preferences, save_key, save_preferences
from chat_tools import chat_tool
from codex_chat import CodexChatRequest
from dialogs import prompt_reminder, reminder_summary
from pet_window import PetDialog, keep_in_front, warn
from speech import ReplySpeech
from voice_input import VoiceInput


def image_part(image):
    if max(image.width(), image.height()) > 1600:
        image = image.scaled(1600, 1600, Qt.KeepAspectRatio, Qt.SmoothTransformation)
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.WriteOnly)
    if not image.save(buffer, 'PNG') or data.size() > 8_000_000:
        raise ValueError('截图无法编码，请选择更小的区域。')
    return {'type': 'image_url', 'image_url': {'url': 'data:image/png;base64,' + b64encode(bytes(data)).decode('ascii')}}


HISTORY_LIMIT = 4 * 1024 * 1024
TOOL_STATUS = {
    'weather': ('成都天气', '正在查询成都天气…'),
    'quota': ('Codex 额度', '正在查询 Codex 额度…'),
    'todo': ('待办提醒', '请确认待办提醒…'),
}


def history_path():
    directory = QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)
    return Path(directory) / 'DSHDragon' / 'chat-history.json'


def load_sessions(path):
    try:
        with path.open('rb') as stream:
            saved = json.loads(stream.read(HISTORY_LIMIT))
    except (OSError, ValueError):
        return []
    if not isinstance(saved, list):
        return []
    sessions = []
    for history in saved[:20]:
        if isinstance(history, list):
            turns = [turn for turn in history[-50:] if isinstance(turn, dict)
                     and all(isinstance(turn.get(key), str) for key in ('question', 'answer'))]
            if turns:
                sessions.append(turns)
    return sessions


class ChatWindow(PetDialog):
    quick_finished = Signal(str, bool, bool)

    def __init__(self, pet):
        super().__init__(pet, Qt.Window)
        self.pet = pet
        self.settings = pet.settings
        self.setWindowTitle('桌宠对话')
        self.resize(650, 540)
        self.history_path = history_path()
        self.sessions = load_sessions(self.history_path)
        self.preferences = read_preferences(self.settings)
        self.key = load_key(self.preferences['protected_key'], self.endpoint)
        self.pending = None
        self.quick_pending = False
        self.tool_ticket = None
        self.image = None
        self.request = ChatRequest(self)
        self.codex_request = CodexChatRequest(self)
        for request in (self.request, self.codex_request):
            request.delta.connect(self.append)
            request.completed.connect(self.complete)
            request.failed.connect(self.fail)
            request.cancelled.connect(lambda: self.fail('已停止回复。'))
        self.speech = ReplySpeech(self)
        self.speech.failed.connect(self.set_status)

        layout = QVBoxLayout(self)
        toolbar = QHBoxLayout()
        self.selector = QComboBox()
        toolbar.addWidget(self.selector, 1)
        self.new_button = QPushButton('新对话')
        self.new_button.clicked.connect(self.new_session)
        toolbar.addWidget(self.new_button)
        self.delete_button = QPushButton('删除对话')
        self.delete_button.clicked.connect(self.delete_session)
        toolbar.addWidget(self.delete_button)
        self.settings_button = QPushButton('模型设置')
        self.settings_button.clicked.connect(self.configure)
        toolbar.addWidget(self.settings_button)
        layout.addLayout(toolbar)

        self.history = QPlainTextEdit()
        self.history.setReadOnly(True)
        self.history.document().setMaximumBlockCount(5000)
        layout.addWidget(self.history, 1)
        memory = QPushButton('白龙记忆')
        memory.clicked.connect(lambda: edit_memory(self, self.settings))
        toolbar.addWidget(memory)
        remember = QPushButton('记住选中内容')
        remember.setEnabled(False)
        self.history.copyAvailable.connect(remember.setEnabled)
        remember.clicked.connect(lambda: edit_memory(self, self.settings, self.history.textCursor().selectedText()))
        toolbar.addWidget(remember)
        self.attachment = QLabel()
        self.attachment.setAlignment(Qt.AlignCenter)
        self.attachment.hide()
        layout.addWidget(self.attachment)
        self.remove_attachment = QPushButton('移除截图')
        self.remove_attachment.clicked.connect(self.clear_attachment)
        self.remove_attachment.hide()
        layout.addWidget(self.remove_attachment)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText('输入消息后点击发送')
        self.input.setMaximumHeight(110)
        layout.addWidget(self.input)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        controls = QHBoxLayout()
        self.read_aloud = QCheckBox('朗读回复')
        self.read_aloud.setChecked(self.settings.value('chat_read_aloud', False, type=bool))
        self.read_aloud.toggled.connect(self.set_read_aloud)
        controls.addWidget(self.read_aloud)
        controls.addStretch()
        self.cancel_button = QPushButton('停止')
        self.cancel_button.clicked.connect(self.stop)
        controls.addWidget(self.cancel_button)
        self.send_button = QPushButton('发送')
        self.send_button.clicked.connect(self.send)
        controls.addWidget(self.send_button)
        layout.addLayout(controls)

        self.selector.currentIndexChanged.connect(self.render_history)
        self.reload_sessions(0 if self.sessions else -1)
        self.set_busy(False)

    @property
    def endpoint(self):
        return self.preferences['endpoint']

    @property
    def model(self):
        return self.preferences['model']

    @property
    def backend(self):
        return self.preferences['backend']

    @property
    def codex_model(self):
        return self.preferences['codex_model']

    def configure(self):
        dialog = PetDialog(self)
        dialog.setWindowTitle('模型设置')
        dialog.setMinimumWidth(460)
        form = QFormLayout(dialog)
        source = QComboBox()
        source.addItem('本机 Codex 账号', 'codex')
        source.addItem('自定义 API', 'api')
        source.setCurrentIndex(0 if self.backend == 'codex' else 1)
        codex_model = QLineEdit(self.codex_model)
        codex_model.setPlaceholderText('留空使用 Codex 默认模型')
        endpoint = QLineEdit(self.endpoint)
        endpoint.setPlaceholderText('https://api.example.com/v1')
        model = QLineEdit(self.model)
        key = QLineEdit(self.key)
        key.setEchoMode(QLineEdit.Password)
        endpoint.textEdited.connect(lambda _text: key.clear())
        description = QLabel()
        description.setTextFormat(Qt.PlainText)
        description.setWordWrap(True)
        form.addRow('对话来源', source)
        form.addRow(description)
        form.addRow('Codex 模型（可选）', codex_model)
        form.addRow('接口地址', endpoint)
        form.addRow('模型名称', model)
        form.addRow('API Key（可选）', key)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)

        def update_fields():
            use_codex = source.currentData() == 'codex'
            if use_codex:
                description.setText('沿用本机已登录的 Codex 账号和额度，无需填写 API Key。')
            elif self.preferences['protected_key'] and not self.key:
                description.setText('保存的 API Key 无法解锁，请重新输入并保存。')
            else:
                description.setText('API Key 由 Windows 加密保存。清空后保存可移除密钥。')
            form.setRowVisible(codex_model, use_codex)
            for field in (endpoint, model, key):
                form.setRowVisible(field, not use_codex)
            dialog.adjustSize()

        source.currentIndexChanged.connect(update_fields)
        update_fields()
        while dialog.exec():
            backend = source.currentData()
            preferences = dict(self.preferences, backend=backend)
            api_key = self.key
            try:
                if backend == 'codex':
                    preferences['codex_model'] = codex_model.text().strip()
                else:
                    address, name = endpoint.text().strip(), model.text().strip()
                    completions_url(address)
                    if not name:
                        raise ValueError('请填写模型名称。')
                    api_key = key.text().strip()
                    preferences.update(endpoint=address, model=name, protected_key=save_key(api_key, address))
                save_preferences(self.settings, preferences)
            except (OSError, ValueError) as error:
                warn(dialog, '模型设置', str(error))
                continue
            self.preferences, self.key = preferences, api_key
            return

    def set_status(self, text):
        self.status.setText(text)

    def set_read_aloud(self, enabled):
        self.settings.setValue('chat_read_aloud', enabled)
        self.cancel_button.setEnabled(self.pending is not None or enabled)
        if not enabled:
            self.speech.stop()

    def reload_sessions(self, index):
        self.selector.blockSignals(True)
        self.selector.clear()
        self.selector.addItem('未保存的新对话', -1)
        for number, session in enumerate(self.sessions):
            name = ' '.join(session[0]['question'].split())[:34]
            self.selector.addItem(name, number)
        self.selector.setCurrentIndex(index + 1)
        self.selector.blockSignals(False)
        self.render_history()

    def selected_history(self):
        index = self.selector.currentData()
        return self.sessions[index] if isinstance(index, int) and index >= 0 else []

    def save(self):
        payload = json.dumps(self.sessions, ensure_ascii=False).encode('utf-8')
        # Keep the active conversation and trim older conversations first.
        while len(payload) >= HISTORY_LIMIT:
            if len(self.sessions) > 1:
                self.sessions.pop()
            else:
                del self.sessions[0][0]
            payload = json.dumps(self.sessions, ensure_ascii=False).encode('utf-8')
        try:
            self.history_path.parent.mkdir(parents=True, exist_ok=True)
        except OSError:
            return False
        file = QSaveFile(str(self.history_path))
        if not file.open(QIODevice.WriteOnly):
            return False
        if file.write(payload) != len(payload):
            file.cancelWriting()
            return False
        return file.commit()

    def render_history(self):
        self.history.setPlainText('\n\n'.join(f'你：{turn["question"]}\n桌宠：{turn["answer"]}'
                                             for turn in self.selected_history()))
        self.history.moveCursor(QTextCursor.End)
        self.delete_button.setEnabled(bool(self.selected_history()) and self.pending is None)

    def new_session(self):
        self.clear_attachment()
        self.input.clear()
        self.selector.setCurrentIndex(0)
        self.set_status('')

    def delete_session(self):
        index = self.selector.currentData()
        if not isinstance(index, int) or index < 0:
            return
        prompt = QMessageBox(QMessageBox.Question, '删除对话', '删除当前本地对话记录？',
                             QMessageBox.Yes | QMessageBox.No, self)
        prompt.setDefaultButton(QMessageBox.No)
        if keep_in_front(prompt).exec() != QMessageBox.Yes:
            return
        del self.sessions[index]
        saved = self.save()
        self.new_session()
        self.reload_sessions(-1)
        if not saved:
            self.set_status('无法写入本地记录，关闭插件后删除可能无法保留。')

    def attach(self, image):
        if self.pending is not None:
            return False
        self.image = image
        self.attachment.setPixmap(QPixmap.fromImage(image).scaled(360, 130, Qt.KeepAspectRatio,
                                                                  Qt.SmoothTransformation))
        self.attachment.show()
        self.remove_attachment.show()
        self.set_status('截图已就绪。发送后会把预览图片提交给所配置的模型。')
        return True

    def clear_attachment(self):
        self.image = None
        self.attachment.clear()
        self.attachment.hide()
        self.remove_attachment.hide()

    def set_busy(self, busy):
        for widget in (self.selector, self.new_button, self.settings_button, self.input,
                       self.send_button, self.remove_attachment):
            widget.setEnabled(not busy)
        self.delete_button.setEnabled(not busy and bool(self.selected_history()))
        self.cancel_button.setEnabled(busy or self.read_aloud.isChecked())

    def send(self):
        self.start_message(self.input.toPlainText())

    def start_message(self, question, quick=False):
        question = question.strip()
        image = None if quick else self.image
        if self.pending is not None:
            return False
        if not question and image is None:
            return False
        if len(question) > 4000:
            self.set_status('每条问题最多 4000 字。')
            return False
        tool = chat_tool(question) if image is None else None
        if tool is not None:
            ticket = self.tool_ticket = object()
            self.begin_reply(question, quick, TOOL_STATUS[tool.kind][1])
            QTimer.singleShot(0, self, lambda: self.run_tool(ticket, tool))
            return True
        question = question or '请说明截图中的内容。'
        use_codex = self.backend == 'codex'
        messages = memory_context(self.settings)
        for turn in [item for item in self.selected_history() if not item.get('local')][-6:]:
            messages.extend([{'role': 'user', 'content': turn['question'][:4000]},
                             {'role': 'assistant', 'content': turn['answer'][:5000]}])
        try:
            content = question
            if image is not None:
                content = [{'type': 'text', 'text': question}, image_part(image)]
            messages.append({'role': 'user', 'content': content})
            if use_codex:
                self.codex_request.start(self.codex_model, messages)
            else:
                self.request.start(self.endpoint, self.model, self.key, messages)
        except (RuntimeError, ValueError) as error:
            self.set_status(str(error))
            return False
        self.begin_reply(question, quick, '正在等待 Codex 回复…' if use_codex else '正在等待模型回复…')
        return True

    def begin_reply(self, question, quick, status):
        self.speech.stop()
        self.pending = question
        self.quick_pending = quick
        self.set_busy(True)
        self.set_status(status)
        self.append(f'\n\n你：{question}\n桌宠：')

    def run_tool(self, ticket, tool):
        if self.tool_ticket is not ticket:
            return

        def reply(text, animations=()):
            if self.tool_ticket is not ticket:
                return
            self.tool_ticket = None
            quick = self.quick_pending
            important = tool.kind in ('todo', 'quota')
            if animations:
                self.pet.play_reaction(animations)
            self.complete(text, local=True, important=important)
            if not quick:
                self.pet.notify(TOOL_STATUS[tool.kind][0], text, duration=20_000,
                                open_chat=True, important=important)

        if tool.kind == 'weather':
            self.pet.widgets.request_weather(city='成都', callback=reply)
        elif tool.kind == 'quota':
            self.pet.widgets.request_quota(callback=reply)
        else:
            if len(tool.sentence) > 150:
                reply('请缩短待办指令。提醒事项最多 100 个字。')
                return
            todo = prompt_reminder(self if self.isVisible() else self.pet, tool.sentence, tool.repeat)
            if self.tool_ticket is not ticket:
                return
            if todo is None:
                reply('已取消添加待办。')
                return
            self.pet.todos.append(todo)
            if not self.pet.save_todos():
                self.pet.todos.pop()
                self.pet.save_todos()
                reply('待办保存失败，请检查本机设置的写入权限后再试。')
                return
            reply('已添加待办。\n' + reminder_summary(todo))

    def append(self, text):
        self.history.moveCursor(QTextCursor.End)
        self.history.insertPlainText(text)
        self.history.ensureCursorVisible()

    def complete(self, answer, *, local=False, important=False):
        history = self.selected_history()
        self.sessions[:] = [history] + [session for session in self.sessions if session is not history][:19]
        turn = {'question': self.pending, 'answer': answer}
        if local:
            turn['local'] = True
        history.append(turn)
        del history[:-50]
        saved = self.save()
        self.pending = None
        quick, self.quick_pending = self.quick_pending, False
        if not quick:
            self.clear_attachment()
            self.input.clear()
        self.reload_sessions(0)
        self.set_busy(False)
        self.set_status('' if saved else '回复已收到，但本地历史写入失败。')
        if quick:
            self.quick_finished.emit(answer, True, important)
        if self.read_aloud.isChecked():
            self.speech.speak(answer)

    def fail(self, message):
        self.pending = None
        quick, self.quick_pending = self.quick_pending, False
        self.render_history()
        self.set_busy(False)
        self.set_status(message)
        if quick:
            self.quick_finished.emit(message, False, False)

    def stop(self):
        if self.tool_ticket is not None:
            self.tool_ticket = None
            self.fail('已停止。')
        self.request.cancel()
        self.codex_request.cancel()
        self.speech.stop()

    def done(self, result):
        self.stop()
        self.clear_attachment()
        super().done(result)


class QuickChat(PetDialog):
    def __init__(self, pet, chat):
        super().__init__(pet, Qt.Window | Qt.WindowStaysOnTopHint)
        self.pet = pet
        self.chat = chat
        self.sent_text = ''
        self.voice_mode = None
        self.setWindowTitle('白龙快捷对话')
        self.setMinimumWidth(380)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setMaxLength(4000)
        self.input.setPlaceholderText('输入消息，按 Enter 发送')
        self.input.returnPressed.connect(self.send)
        row.addWidget(self.input)
        self.voice = VoiceInput(self)
        if sys.platform == 'win32':
            talk = QPushButton('按住说话（F9）')
            talk.setAutoDefault(False)
            talk.setFocusPolicy(Qt.NoFocus)
            talk.pressed.connect(lambda: self.start_voice('mouse'))
            talk.released.connect(lambda: self.stop_voice('mouse'))
            row.addWidget(talk)
            self.record_button = QPushButton('开始录音')
            self.record_button.setAutoDefault(False)
            self.record_button.clicked.connect(self.toggle_recording)
            row.addWidget(self.record_button)
            self.voice.state_changed.connect(self.update_voice_button)
            self.installEventFilter(self)
            self.input.installEventFilter(self)
        full = QPushButton('完整对话')
        full.setAutoDefault(False)
        full.clicked.connect(self.open_full)
        row.addWidget(full)
        layout.addLayout(row)
        self.status = QLabel()
        self.status.setTextFormat(Qt.PlainText)
        self.status.setWordWrap(True)
        self.status.setMinimumHeight(self.status.fontMetrics().height() * 2)
        layout.addWidget(self.status)
        self.voice.status.connect(self.status.setText)
        self.voice.recognized.connect(self.input.insert)
        QApplication.instance().aboutToQuit.connect(self.voice.cancel)
        chat.quick_finished.connect(self.finish)

    def eventFilter(self, watched, event):
        kind = event.type()
        if kind in (QEvent.KeyPress, QEvent.KeyRelease) and event.key() == Qt.Key_F9:
            if not event.isAutoRepeat():
                if kind == QEvent.KeyPress:
                    self.start_voice('keyboard')
                else:
                    self.stop_voice('keyboard')
            return True
        if watched is self and kind == QEvent.WindowDeactivate and self.voice.state in ('opening', 'recording'):
            self.voice.cancel('快捷对话失去焦点，录音已取消。')
        return super().eventFilter(watched, event)

    def start_voice(self, mode):
        if not self.voice.busy:
            self.voice_mode = mode
            self.voice.press()

    def stop_voice(self, mode):
        if self.voice_mode == mode:
            self.voice.release()

    def toggle_recording(self):
        if self.voice_mode == 'click':
            self.stop_voice('click')
        else:
            self.start_voice('click')

    def update_voice_button(self, state):
        if state == 'idle':
            self.voice_mode = None
        can_stop = self.voice_mode == 'click' and state in ('opening', 'recording')
        self.record_button.setText('停止录音' if can_stop else '开始录音')
        self.record_button.setEnabled(state == 'idle' or can_stop)

    def hideEvent(self, event):
        self.voice.cancel()
        super().hideEvent(event)

    def present(self):
        if not self.voice.busy:
            self.status.setText('正在等待当前回复…' if self.chat.pending is not None else '')
        self.adjustSize()
        self.show()
        self.raise_()
        self.activateWindow()
        self.input.setFocus()

    def open_full(self):
        self.hide()
        self.pet.open_chat()

    def send(self):
        if self.voice.busy or not self.input.text().strip():
            return
        if self.chat.pending is not None:
            self.status.setText('正在等待当前回复…')
        elif self.chat.start_message(self.input.text(), quick=True):
            self.sent_text = self.input.text()
            self.hide()
            self.pet.say(self.chat.status.text(), transient=True)
        else:
            self.status.setText(self.chat.status.text())

    def finish(self, text, success, important=False):
        if success:
            if self.input.text() == self.sent_text:
                self.input.clear()
            summary = text if important else ' '.join(text.split())
            if not important and len(summary) > 76:
                summary = summary[:76] + '…'
            self.pet.notify('白龙对话', summary + '\n点气泡查看完整回复', 20000,
                            open_chat=True, important=important)
        else:
            self.pet.notify('白龙对话', text)
        self.sent_text = ''
        if not self.voice.busy:
            self.status.setText('' if success else text)
