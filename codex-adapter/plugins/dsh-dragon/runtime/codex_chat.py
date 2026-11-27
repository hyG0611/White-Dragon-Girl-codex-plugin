"""Run desktop conversation turns through the local, signed-in Codex app server."""
from pathlib import Path
import json

from PySide6.QtCore import QDir, QObject, QProcess, QProcessEnvironment, QTemporaryDir, QTimer, Signal


CONFIG = Path(__file__).resolve().parents[1] / 'runtime-config.json'
SERVER_ARGS = (
    'app-server', '--stdio',
    '--disable', 'shell_tool', '--disable', 'hooks', '--disable', 'plugins',
    '--disable', 'multi_agent', '--disable', 'multi_agent_v2', '--disable', 'code_mode',
    '--disable', 'view_image', '--disable', 'image_generation', '--disable', 'goals',
    '-c', 'mcp_servers={}', '-c', 'web_search=disabled',
    '-c', 'memories.use_memories=false', '-c', 'memories.generate_memories=false',
    '-c', 'project_doc_max_bytes=0',
)
SIGN_IN = '请先在本机 Codex 中使用 ChatGPT 账号登录，再返回桌宠。'
CONNECTION_ERROR = '无法连接本机 Codex，请检查 Codex 是否已安装并登录。'
MAX_PACKET = 16 * 1024 * 1024
MAX_TEXT = 48_000


def codex_executable():
    try:
        config = json.loads(CONFIG.read_text(encoding='utf-8-sig'))
        path = Path(config['codex'])
        if path.is_absolute() and path.is_file() and path.name.lower() == 'codex.exe':
            return path
    except (OSError, ValueError, KeyError, TypeError):
        pass
    raise RuntimeError('找不到插件安装时配置的 Codex。请重新运行桌宠安装脚本更新路径。')


def codex_input(messages):
    history = []
    for message in messages[:-1]:
        role = 'assistant' if message['role'] == 'assistant' else 'user'
        kind = 'output_text' if role == 'assistant' else 'input_text'
        history.append({'type': 'message', 'role': role,
                        'content': [{'type': kind, 'text': message['content']}]})
    content = messages[-1]['content']
    if isinstance(content, str):
        return history, [{'type': 'text', 'text': content}]
    return history, [
        {'type': 'text', 'text': part['text']} if part['type'] == 'text'
        else {'type': 'image', 'url': part['image_url']['url']}
        for part in content
    ]


class CodexChatRequest(QObject):
    delta = Signal(str)
    completed = Signal(str)
    failed = Signal(str)
    cancelled = Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.process = None
        self.timeout = QTimer(self)
        self.timeout.setSingleShot(True)
        self.timeout.timeout.connect(lambda: self.end(error='Codex 回复超时，请稍后再试。'))

    def start(self, model, messages):
        if self.process is not None:
            raise RuntimeError('已有 Codex 对话正在进行。')
        executable = codex_executable()
        history, turn_input = codex_input(messages)
        directory = QTemporaryDir(QDir.tempPath() + '/dsh-codex-chat-XXXXXX')
        if not directory.isValid():
            raise RuntimeError('无法创建 Codex 对话的临时目录。')
        self.history, self.turn_input = history, turn_input
        self.model = model.strip()
        self.request_id = 0
        self.method = ''
        self.thread_id = self.turn_id = None
        self.answer = self.streamed = ''
        self.buffer = b''

        process = self.process = QProcess(self)
        process.setWorkingDirectory(directory.path())
        process.setStandardErrorFile(QProcess.nullDevice())
        env = QProcessEnvironment.systemEnvironment()
        for name in ('OPENAI_API_KEY', 'CODEX_API_KEY', 'OPENAI_BASE_URL'):
            env.remove(name)
        process.setProcessEnvironment(env)
        process.setProgram(str(executable))
        process.setArguments(list(SERVER_ARGS))
        process.started.connect(self.initialize)
        process.readyReadStandardOutput.connect(lambda: self.read(process))
        process.errorOccurred.connect(lambda error: self.exited(process))
        process.finished.connect(lambda code, status: self.exited(process))
        process.finished.connect(lambda *_: directory.remove())
        process.finished.connect(process.deleteLater)
        self.timeout.start(90_000)
        QTimer.singleShot(0, process, lambda: process.start() if process is self.process else None)

    def send(self, value):
        data = (json.dumps(value, ensure_ascii=False) + '\n').encode('utf-8')
        if self.process.write(data) != len(data):
            raise RuntimeError(CONNECTION_ERROR)

    def call(self, method, params):
        self.request_id += 1
        self.method = method
        self.send({'id': self.request_id, 'method': method, 'params': params})

    def initialize(self):
        if self.sender() is not self.process:
            return
        try:
            self.call('initialize', {
                'clientInfo': {'name': 'dsh_desktop_pet', 'title': 'DSH 桌宠', 'version': '1.0.0'},
                'capabilities': {'experimentalApi': True},
            })
        except RuntimeError as error:
            self.end(error=str(error))

    def read(self, process):
        data = bytes(process.readAllStandardOutput())
        if process is not self.process:
            return
        frames = (self.buffer + data).split(b'\n')
        self.buffer = frames.pop()
        try:
            if len(self.buffer) > MAX_PACKET:
                raise ValueError
            for frame in frames:
                if not frame.strip():
                    continue
                if len(frame) > MAX_PACKET:
                    raise ValueError
                self.packet(json.loads(frame))
                if process is not self.process:
                    return
        except RuntimeError as error:
            self.end(error=str(error))
        except (TypeError, AttributeError, KeyError, ValueError):
            self.end(error='本机 Codex 返回了无法读取的对话数据。')

    def packet(self, packet):
        method = packet.get('method')
        if 'id' in packet:
            if method:
                self.end(error=SIGN_IN if method == 'account/chatgptAuthTokens/refresh'
                         else 'Codex 要求额外操作，请直接在 Codex 中完成。')
            elif packet['id'] == self.request_id:
                if 'error' in packet:
                    if self.method == 'account/read':
                        self.end(error=SIGN_IN)
                    else:
                        self.end(error='本机 Codex 暂时无法开始对话，请检查登录状态、模型及额度。')
                else:
                    self.response(packet['result'])
            return
        data = packet.get('params', {})
        if self.thread_id is None or data.get('threadId') != self.thread_id:
            return
        if method == 'turn/completed':
            turn = data['turn']
            if self.turn_id and turn['id'] != self.turn_id:
                return
            if turn['status'] == 'completed':
                self.end(result=self.answer or self.streamed)
            elif turn['status'] == 'interrupted':
                self.end()
            else:
                info = (turn.get('error') or {}).get('codexErrorInfo')
                self.end(error='Codex 额度已达上限，请在额度重置后再试。' if info == 'usageLimitExceeded'
                         else 'Codex 回复失败，请检查连接、登录状态和可用额度。')
        elif self.turn_id is None or data.get('turnId') == self.turn_id:
            if method == 'item/agentMessage/delta':
                self.streamed += data['delta']
                if len(self.streamed) > MAX_TEXT:
                    raise RuntimeError('回复超出桌宠可显示的长度。')
                self.delta.emit(data['delta'])
            elif method == 'item/completed':
                item = data['item']
                if item.get('type') == 'agentMessage':
                    self.answer = item['text']
                    if len(self.answer) > MAX_TEXT:
                        raise RuntimeError('回复超出桌宠可显示的长度。')

    def response(self, result):
        if self.method == 'initialize':
            self.send({'method': 'initialized'})
            self.call('account/read', {'refreshToken': False})
        elif self.method == 'account/read':
            if (result.get('account') or {}).get('type') != 'chatgpt':
                self.end(error=SIGN_IN)
                return
            params = {
                'cwd': self.process.workingDirectory(), 'modelProvider': 'openai',
                'ephemeral': True, 'approvalPolicy': 'never', 'sandbox': 'read-only',
                'environments': [],
                'baseInstructions': '你是桌宠的文字对话伙伴。用用户的语言回复最后一条消息。'
                                    '历史和已保存的记忆仅供参考。回复尽量简明，直接输出文字。',
            }
            if self.model:
                params['model'] = self.model
            self.call('thread/start', params)
        elif self.method == 'thread/start':
            thread = result['thread']
            if (not thread.get('ephemeral') or result.get('modelProvider') != 'openai'
                    or result.get('approvalPolicy') != 'never' or result['sandbox']['type'] != 'readOnly'):
                self.end(error='当前 Codex 无法创建独立的桌宠对话，请检查客户端版本。')
                return
            self.thread_id = thread['id']
            if self.history:
                self.call('thread/inject_items', {'threadId': self.thread_id, 'items': self.history})
            else:
                self.begin_turn()
        elif self.method == 'thread/inject_items':
            self.begin_turn()
        elif self.method == 'turn/start':
            self.turn_id = result['turn']['id']

    def begin_turn(self):
        self.call('turn/start', {'threadId': self.thread_id, 'input': self.turn_input,
                                 'environments': [], 'effort': 'low', 'serviceTierForTurn': 'default'})
        self.history = []
        self.turn_input = []

    def exited(self, process):
        if process is self.process:
            self.read(process)
            if process is self.process:
                self.end(error=CONNECTION_ERROR)

    def cancel(self):
        if self.process is None:
            return
        if self.turn_id:
            try:
                self.call('turn/interrupt', {'threadId': self.thread_id, 'turnId': self.turn_id})
            except RuntimeError:
                pass
        self.end()

    def end(self, result=None, error=None):
        process, self.process = self.process, None
        if process is None:
            return
        self.timeout.stop()
        self.thread_id = self.turn_id = None
        self.buffer = b''
        self.history = self.turn_input = []
        self.answer = self.streamed = ''
        if process.state() == QProcess.NotRunning:
            process.deleteLater()
        else:
            process.closeWriteChannel()
            cleanup = QTimer(process)
            cleanup.setSingleShot(True)
            cleanup.timeout.connect(process.kill)
            cleanup.start(500)
        if error:
            self.failed.emit(error)
        elif result is None:
            self.cancelled.emit()
        elif not result.strip():
            self.failed.emit('Codex 没有返回可显示的文字。')
        else:
            self.completed.emit(result)
