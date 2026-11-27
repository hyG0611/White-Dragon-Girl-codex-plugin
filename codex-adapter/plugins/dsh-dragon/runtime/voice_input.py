"""Capture a short Windows microphone clip and transcribe it locally."""
from array import array
from base64 import b64encode
from collections import deque
import ctypes as ct
from dataclasses import dataclass
from io import BytesIO
from math import log10
import os
from pathlib import Path
from queue import Empty, SimpleQueue
import sys
from threading import Event, Thread
from time import monotonic
import wave

from PySide6.QtCore import QObject, QProcess, QTimer, Signal


RATE = 16_000
MAX_SECONDS = 30
PCM_WIDTH = 2
CHUNK_BYTES = RATE * PCM_WIDTH * 40 // 1000
MAX_BYTES = RATE * PCM_WIDTH * MAX_SECONDS
WAVE_MAPPER = 0xFFFFFFFF
WHDR_DONE = 1
DRV_QUERYFUNCTIONINSTANCEID = 0x0811
DRV_QUERYFUNCTIONINSTANCEIDSIZE = 0x0812

TRANSCRIBE = r"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
Add-Type -AssemblyName System.Speech
$engines = [System.Speech.Recognition.SpeechRecognitionEngine]::InstalledRecognizers()
$culture = [Globalization.CultureInfo]::CurrentUICulture.TwoLetterISOLanguageName
$info = $engines | Where-Object { $_.Culture.TwoLetterISOLanguageName -eq $culture } | Select-Object -First 1
if (!$info) { $info = $engines | Select-Object -First 1 }
if (!$info) { exit 3 }
$audio = [IO.MemoryStream]::new([Convert]::FromBase64String([Console]::In.ReadToEnd()))
$engine = [System.Speech.Recognition.SpeechRecognitionEngine]::new($info)
try {
    $engine.LoadGrammar([System.Speech.Recognition.DictationGrammar]::new())
    $engine.SetInputToWaveStream($audio)
    Register-ObjectEvent -InputObject $engine -EventName SpeechRecognized -SourceIdentifier word | Out-Null
    Register-ObjectEvent -InputObject $engine -EventName RecognizeCompleted -SourceIdentifier complete | Out-Null
    $engine.RecognizeAsync([System.Speech.Recognition.RecognizeMode]::Multiple)
    $words = [Collections.Generic.List[string]]::new()
    do {
        $event = Wait-Event -Timeout 18
        if (!$event) { exit 5 }
        Remove-Event -EventIdentifier $event.EventIdentifier
        if ($event.SourceIdentifier -eq 'word') { $words.Add($event.SourceEventArgs.Result.Text) }
    } while ($event.SourceIdentifier -ne 'complete')
    if ($event.SourceEventArgs.Error) { throw $event.SourceEventArgs.Error }
    if (!$words) { exit 4 }
    [Console]::WriteLine(($words -join ' '))
} finally {
    $engine.Dispose()
    $audio.Dispose()
}
"""


class WaveFormat(ct.Structure):
    _pack_ = 1
    _fields_ = [('tag', ct.c_uint16), ('channels', ct.c_uint16), ('rate', ct.c_uint32),
                ('bytes_per_second', ct.c_uint32), ('alignment', ct.c_uint16),
                ('bits', ct.c_uint16), ('extra_size', ct.c_uint16)]


class WaveHeader(ct.Structure):
    _fields_ = [('data', ct.c_void_p), ('length', ct.c_uint32), ('recorded', ct.c_uint32),
                ('user', ct.c_size_t), ('flags', ct.c_uint32), ('loops', ct.c_uint32),
                ('next', ct.c_void_p), ('reserved', ct.c_size_t)]


class WaveInCaps(ct.Structure):
    _fields_ = [('manufacturer', ct.c_uint16), ('product', ct.c_uint16), ('version', ct.c_uint32),
                ('name', ct.c_wchar * 32), ('formats', ct.c_uint32), ('channels', ct.c_uint16),
                ('reserved', ct.c_uint16)]


@dataclass(frozen=True)
class InputDevice:
    key: str
    name: str
    index: int


def input_devices(audio=None):
    if sys.platform != 'win32':
        return []
    audio = audio if audio is not None else ct.WinDLL('winmm')
    audio.waveInGetDevCapsW.argtypes = [ct.c_size_t, ct.POINTER(WaveInCaps), ct.c_uint]
    audio.waveInMessage.argtypes = [ct.c_void_p, ct.c_uint, ct.c_void_p, ct.c_size_t]
    devices = []
    for index in range(audio.waveInGetNumDevs()):
        caps = WaveInCaps()
        if audio.waveInGetDevCapsW(index, ct.byref(caps), ct.sizeof(caps)):
            continue
        size = ct.c_uint32()
        # An endpoint path stays valid when Windows reorders its list of inputs.
        key = f'legacy:{index}:{caps.name}'
        if not audio.waveInMessage(index, DRV_QUERYFUNCTIONINSTANCEIDSIZE, ct.byref(size), 0) and size.value:
            endpoint = ct.create_unicode_buffer(size.value // ct.sizeof(ct.c_wchar))
            result = audio.waveInMessage(index, DRV_QUERYFUNCTIONINSTANCEID, endpoint, size.value)
            if result == 0 and endpoint.value:
                key = endpoint.value
        devices.append(InputDevice(key, caps.name, index))
    return devices


def input_index(audio, key):
    if not key:
        return WAVE_MAPPER
    for device in input_devices(audio):
        if device.key == key:
            return device.index
    raise RuntimeError('已选麦克风未连接，请重新连接或改选输入设备。')


def input_level(clip):
    samples = array('h', clip)
    peak = max(max(samples), -min(samples), 1)
    decibels = 20 * log10(peak / 32_768)
    return max(0, round(100 * (decibels + 55) / 55))


class Microphone:
    def __init__(self, device):
        self.audio = ct.WinDLL('winmm')
        self.audio.waveInOpen.argtypes = [ct.POINTER(ct.c_void_p), ct.c_uint, ct.POINTER(WaveFormat),
                                         ct.c_size_t, ct.c_size_t, ct.c_uint32]
        for name in ('waveInPrepareHeader', 'waveInAddBuffer', 'waveInUnprepareHeader'):
            getattr(self.audio, name).argtypes = [ct.c_void_p, ct.POINTER(WaveHeader), ct.c_uint]
        for name in ('waveInStart', 'waveInReset', 'waveInClose'):
            getattr(self.audio, name).argtypes = [ct.c_void_p]
        self.device = device
        self.handle = ct.c_void_p()
        self.prepared = []
        self.queued = deque()

    def prepare(self):
        fmt = WaveFormat(1, 1, RATE, RATE * PCM_WIDTH, PCM_WIDTH, PCM_WIDTH * 8, 0)
        index = input_index(self.audio, self.device)
        code = self.audio.waveInOpen(ct.byref(self.handle), index, ct.byref(fmt), 0, 0, 0)
        if code:
            raise RuntimeError(f'无法打开麦克风（Windows 错误 {code}）。请检查输入设备和麦克风访问权限。')
        for _ in range(8):
            buffer = ct.create_string_buffer(CHUNK_BYTES)
            header = WaveHeader(ct.addressof(buffer), len(buffer))
            if self.audio.waveInPrepareHeader(self.handle, ct.byref(header), ct.sizeof(header)):
                raise RuntimeError('无法准备录音，请检查麦克风是否被其他应用占用。')
            block = header, buffer
            self.prepared.append(block)
            self.enqueue(block)

    def enqueue(self, block):
        header, _ = block
        header.recorded = 0
        if self.audio.waveInAddBuffer(self.handle, ct.byref(header), ct.sizeof(header)):
            raise RuntimeError('麦克风录音已中断，请检查输入设备后再试。')
        self.queued.append(block)

    def start(self):
        code = self.audio.waveInStart(self.handle)
        if code:
            raise RuntimeError(f'无法开始录音（Windows 错误 {code}）。')

    def read(self):
        clip = bytearray()
        for _ in range(len(self.queued)):
            header, buffer = self.queued[0]
            if not header.flags & WHDR_DONE:
                break
            clip.extend(buffer[:header.recorded])
            self.enqueue(self.queued.popleft())
        return clip

    def stop(self):
        if not self.handle:
            return b''
        self.audio.waveInReset(self.handle)
        tail = b''.join(buffer[:header.recorded] for header, buffer in self.queued)
        for header, _ in self.prepared:
            self.audio.waveInUnprepareHeader(self.handle, ct.byref(header), ct.sizeof(header))
        self.audio.waveInClose(self.handle)
        self.handle = ct.c_void_p()
        self.queued.clear()
        self.prepared.clear()
        return tail


def wav_bytes(pcm):
    buffer = BytesIO()
    with wave.open(buffer, 'wb') as writer:
        writer.setparams((1, PCM_WIDTH, RATE, 0, 'NONE', 'not compressed'))
        writer.writeframes(pcm)
    return buffer.getvalue()


class Capture:
    def __init__(self, device):
        self.device = device
        self.events = SimpleQueue()
        self.stop = Event()
        self.cancel_message = ''
        self.thread = Thread(target=self.record, name='DSH microphone', daemon=True)

    def record(self):
        clip = bytearray()
        try:
            if self.stop.is_set():
                self.events.put(('finished', b''))
                return
            mic = Microphone(self.device)
            try:
                mic.prepare()
                if not self.stop.is_set():
                    mic.start()
                    deadline = monotonic() + MAX_SECONDS
                    self.events.put(('ready', None))
                    while monotonic() < deadline and len(clip) < MAX_BYTES and not self.stop.wait(0.02):
                        chunk = mic.read()
                        if chunk:
                            clip.extend(chunk)
                            self.events.put(('level', input_level(chunk)))
            finally:
                clip.extend(mic.stop())
            self.events.put(('finished', b'' if self.cancel_message else clip[:MAX_BYTES]))
        except (OSError, RuntimeError) as error:
            self.events.put(('error', str(error)))


class VoiceInput(QObject):
    status = Signal(str)
    recognized = Signal(str)
    state_changed = Signal(str)
    level_changed = Signal(int)

    def __init__(self, parent):
        super().__init__(parent)
        self.capture = None
        self.state = 'idle'
        self.payload = b''
        self.cancelled = False
        self.job = QProcess(self)
        self.job.setStandardErrorFile(QProcess.nullDevice())
        self.job.started.connect(self.send_audio)
        self.job.finished.connect(self.finished)
        self.job.errorOccurred.connect(self.process_error)
        self.limit = QTimer(self, singleShot=True)
        self.limit.timeout.connect(self.timeout)
        self.poll = QTimer(self, interval=30)
        self.poll.timeout.connect(self.read_capture)

    @property
    def busy(self):
        return self.capture is not None or self.job.state() != QProcess.NotRunning

    def set_state(self, state, message):
        self.state = state
        self.state_changed.emit(state)
        self.status.emit(message)

    def press(self, device=''):
        if self.busy or sys.platform != 'win32':
            return False
        self.capture = Capture(device)
        self.set_state('opening', '正在打开麦克风…')
        self.capture.thread.start()
        self.poll.start()
        return True

    def release(self):
        if self.capture is None or self.capture.stop.is_set():
            return
        self.capture.stop.set()
        self.set_state('stopping', '正在结束录音…')

    def read_capture(self):
        capture = self.capture
        while capture is not None:
            try:
                event, value = capture.events.get_nowait()
            except Empty:
                return
            if event == 'ready':
                if not capture.stop.is_set():
                    self.set_state('recording', '正在录音，请讲话。')
                continue
            if event == 'level':
                if not capture.stop.is_set():
                    self.level_changed.emit(value)
                continue
            self.capture = None
            self.poll.stop()
            self.level_changed.emit(0)
            if capture.cancel_message:
                self.set_state('idle', capture.cancel_message)
            elif event == 'error':
                self.set_state('idle', value)
            elif len(value) < RATE * PCM_WIDTH // 4:
                self.set_state('idle', '录音太短。请等到「正在录音」再讲话，或点「开始录音」。')
            else:
                self.transcribe(wav_bytes(value))
            return

    def transcribe(self, audio):
        self.payload = b64encode(audio)
        self.cancelled = False
        directory = Path(os.environ.get('SystemRoot', r'C:\Windows'))
        program = directory / 'System32/WindowsPowerShell/v1.0/powershell.exe'
        script = b64encode(TRANSCRIBE.encode('utf-16-le')).decode('ascii')
        self.limit.start(25_000)
        self.set_state('recognizing', '正在本机识别语音…')
        self.job.start(str(program), ['-NoLogo', '-NoProfile', '-NonInteractive', '-WindowStyle', 'Hidden',
                                      '-EncodedCommand', script])

    def send_audio(self):
        self.job.write(self.payload)
        self.payload = b''
        self.job.closeWriteChannel()

    def finished(self, code, _status):
        self.limit.stop()
        text = bytes(self.job.readAllStandardOutput()).decode('utf-8', errors='replace').strip()
        if self.cancelled:
            return
        if code == 0 and text:
            self.recognized.emit(text)
            message = '识别完成，可修改文字后按 Enter 发送。'
        elif code == 3:
            message = 'Windows 未安装本地语音识别语言，请在系统语言设置中安装。'
        elif code == 4:
            message = '没有听清。请看录音时的音量有没有变化，再说一次。'
        elif code == 5:
            message = '本地语音识别超时，请再试一次。'
        else:
            message = '本地语音识别失败，请检查 Windows 语音识别设置。'
        self.set_state('idle', message)

    def process_error(self, error):
        if error == QProcess.FailedToStart and not self.cancelled:
            self.limit.stop()
            self.payload = b''
            self.set_state('idle', '无法启动 Windows 本地语音识别。')

    def timeout(self):
        self.cancel('本地语音识别超时，请再试一次。')

    def cancel(self, message='录音已取消。'):
        self.limit.stop()
        if self.capture is not None:
            self.capture.cancel_message = message
            self.capture.stop.set()
            self.set_state('stopping', message)
        self.payload = b''
        self.cancelled = True
        if self.job.state() != QProcess.NotRunning:
            self.job.kill()
            self.set_state('idle', message)
