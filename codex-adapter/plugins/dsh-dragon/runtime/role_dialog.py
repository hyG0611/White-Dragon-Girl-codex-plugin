"""Preview and install a local character pack through the desktop pet menu."""
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import BadZipFile

from PySide6.QtCore import QStandardPaths, Qt, QTimer
from PySide6.QtWidgets import (QComboBox, QDialogButtonBox, QFileDialog, QFormLayout, QLabel,
                               QLineEdit, QProgressDialog)

from pet_window import PetDialog, keep_in_front, pick_files, warn
from rolepacks import copy_role, role_actions, validate_name


def local_roles():
    return Path(QStandardPaths.writableLocation(QStandardPaths.GenericDataLocation)) / 'DSHDragon' / 'characters'


class RolePreview(PetDialog):
    def __init__(self, pet, actions, idle, name, taken):
        super().__init__(pet)
        self.setWindowTitle('预览并导入角色')
        self.pool = pet.pool
        self.actions = actions
        self.idle = idle
        self.taken = {item.casefold() for item in taken}
        self.idle_ready = False
        self.key = None
        self.clip = None
        self.last_frame = None
        form = QFormLayout(self)
        self.name = QLineEdit(name)
        self.name.setMaxLength(80)
        form.addRow('角色名称', self.name)
        self.action = QComboBox()
        self.action.addItems([idle, *(item for item in sorted(actions) if item != idle)])
        form.addRow('预览动作', self.action)
        self.picture = QLabel()
        self.picture.setFixedSize(384, 216)
        self.picture.setAlignment(Qt.AlignCenter)
        self.picture.setStyleSheet('background: #292638; border-radius: 8px;')
        form.addRow(self.picture)
        self.status = QLabel()
        self.status.setWordWrap(True)
        form.addRow(self.status)
        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.buttons.button(QDialogButtonBox.Save).setText('导入并切换')
        self.buttons.rejected.connect(self.reject)
        self.buttons.accepted.connect(self.confirm)
        form.addRow(self.buttons)
        self.timer = QTimer(self, interval=16)
        self.timer.timeout.connect(self.tick)
        self.action.currentTextChanged.connect(self.play)
        self.play(idle)

    def play(self, name):
        self.stop_preview()
        self.picture.clear()
        self.last_frame = None
        key = (self.actions[name], 100, None)
        try:
            self.clip = self.pool.acquire(key)
        except (OSError, RuntimeError) as error:
            self.status.setText(str(error))
        else:
            self.key = key
            self.status.setText('正在读取动画…')
            self.timer.start()
        self.buttons.button(QDialogButtonBox.Save).setEnabled(self.idle_ready)

    def tick(self):
        clip = self.clip
        frame = clip.read()
        if frame is not None and frame is not self.last_frame:
            self.last_frame = frame
            if not self.idle_ready and self.action.currentText() == self.idle:
                self.idle_ready = True
                self.buttons.button(QDialogButtonBox.Save).setEnabled(True)
            self.status.clear()
            self.picture.setPixmap(frame.scaled(self.picture.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        if clip.finished:
            if frame is None:
                self.status.setText('这段动画无法解码，请检查素材或 FFmpeg。')
            self.stop_preview()

    def confirm(self):
        try:
            name = validate_name(self.name.text().strip())
            if name.casefold() in self.taken:
                raise ValueError('角色名称已存在，请换个名称。')
        except ValueError as error:
            warn(self, '无法导入角色', str(error))
            return
        if self.idle_ready:
            self.accept()

    def stop_preview(self):
        self.timer.stop()
        if self.clip is not None:
            self.pool.release(self.key)
            if not self.clip.users:
                self.clip.worker.join(timeout=0.5)
            self.key, self.clip = None, None

    def done(self, result):
        self.stop_preview()
        super().done(result)


def import_role(pet, packed):
    if packed:
        selection = pick_files(pet, '选择角色包', 'ZIP 角色包 (*.zip)')
    else:
        selection = pick_files(pet, '选择角色素材文件夹', mode=QFileDialog.Directory)
    if not selection:
        return None
    source = Path(selection[0])
    base = local_roles()
    try:
        base.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix='.import-', dir=base, ignore_cleanup_errors=True) as staging:
            stage = Path(staging)
            progress = QProgressDialog('正在复制角色动画…', '取消', 0, 100, pet)
            keep_in_front(progress)
            progress.setWindowModality(Qt.WindowModal)
            progress.setMinimumDuration(300)
            progress.setAutoClose(False)
            progress.setAutoReset(False)

            def update(done, total):
                progress.setValue(done * 100 // max(1, total))
                return not progress.wasCanceled()

            try:
                copied = copy_role(source, stage, update)
            finally:
                progress.close()
                progress.deleteLater()
            if not copied:
                return None
            actions, idle = role_actions(stage)
            preview = RolePreview(pet, actions, idle, source.stem if packed else source.name, pet.roles)
            try:
                if not preview.exec():
                    return None
                name = preview.name.text().strip()
                stage.rename(base / name)
                return name
            finally:
                preview.deleteLater()
    except (OSError, ValueError, RuntimeError, BadZipFile) as error:
        warn(pet, '无法导入角色', str(error))
        return None
