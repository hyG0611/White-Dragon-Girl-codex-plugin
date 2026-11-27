"""Editors for desktop-pet reminders and context-menu layout."""
from datetime import datetime
from time import time

from PySide6.QtCore import QDateTime, QEvent, Qt, Signal
from PySide6.QtGui import QKeySequence
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDateTimeEdit, QDialogButtonBox, QFormLayout, QHBoxLayout, QLineEdit,
    QListWidget, QListWidgetItem, QLabel, QPushButton, QSpinBox, QVBoxLayout, QWidget,
)
from cloud_bubble import BUBBLE_SIZE_RANGE
from reminders import REPEAT_OPTIONS, can_snooze, next_repeat, parse_reminder, reminder_due, snooze_reminder
from pet_window import PetDialog


def drag_label(text):
    label = QLabel(text)
    label.setCursor(Qt.SizeAllCursor)
    label.setToolTip('按住这里也可以拖动窗口')
    return label


def edit_number(parent, title, label, value, minimum, maximum, step=1):
    dialog = PetDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setMinimumWidth(280)
    form = QFormLayout(dialog)
    field = QSpinBox()
    field.setRange(minimum, maximum)
    field.setSingleStep(step)
    field.setValue(value)
    form.addRow(drag_label(label), field)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    field.setFocus()
    field.selectAll()
    return field.value() if dialog.exec() else None


def display_hotkey(sequence):
    return '+'.join('Win' if key == 'Meta' else key for key in sequence.split('+'))


class HotkeyEdit(QLineEdit):
    recorded = Signal(str)
    invalid = Signal()
    modifiers = (('Ctrl', Qt.ControlModifier), ('Alt', Qt.AltModifier),
                 ('Shift', Qt.ShiftModifier), ('Meta', Qt.MetaModifier))
    modifier_keys = (Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift, Qt.Key_Meta, Qt.Key_AltGr)

    def __init__(self, sequence):
        super().__init__(display_hotkey(sequence))
        self.setReadOnly(True)
        self.setAccessibleName('快捷键组合')

    def event(self, event):
        if event.type() == QEvent.ShortcutOverride and event.key() not in (Qt.Key_Tab, Qt.Key_Backtab):
            if any(event.modifiers() & flag for _, flag in self.modifiers):
                event.accept()
                return True
        return super().event(event)

    def keyPressEvent(self, event):
        key = event.key()
        if key in self.modifier_keys or event.isAutoRepeat():
            event.accept()
            return
        if key in (Qt.Key_Tab, Qt.Key_Backtab) or (
                not event.modifiers() and key in (Qt.Key_Escape, Qt.Key_Return, Qt.Key_Enter)):
            super().keyPressEvent(event)
            return
        parts = [name for name, flag in self.modifiers if event.modifiers() & flag]
        if parts and (Qt.Key_A <= key <= Qt.Key_Z or Qt.Key_0 <= key <= Qt.Key_9):
            sequence = '+'.join([*parts, chr(key)])
            self.setText(display_hotkey(sequence))
            self.recorded.emit(sequence)
        else:
            self.invalid.emit()
        event.accept()


def edit_hotkey(parent, sequence, title='设置全局显隐快捷键', apply=None):
    dialog = PetDialog(parent)
    dialog.setWindowTitle(title)
    layout = QVBoxLayout(dialog)
    layout.addWidget(drag_label('请按住 Ctrl、Alt、Shift 或 Win，再按一个字母或数字。'))
    chosen = sequence.toString(QKeySequence.PortableText)
    edit = HotkeyEdit(chosen)
    layout.addWidget(edit)
    status = QLabel()
    status.setTextFormat(Qt.PlainText)
    status.setWordWrap(True)
    status.setMinimumHeight(status.fontMetrics().height() * 2)
    layout.addWidget(status)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    save = buttons.button(QDialogButtonBox.Save)
    save.setText('保存')
    save.setDefault(True)
    buttons.button(QDialogButtonBox.Cancel).setText('取消')

    def recorded(value):
        nonlocal chosen
        chosen = value
        status.clear()
        save.setEnabled(True)

    def invalid():
        status.setText('请同时按住修饰键和一个字母或数字。')
        save.setEnabled(False)

    def confirm():
        error = apply(chosen) if apply else None
        if error:
            status.setText(error)
            edit.setFocus()
        else:
            dialog.accept()

    edit.recorded.connect(recorded)
    edit.invalid.connect(invalid)
    buttons.accepted.connect(confirm)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    edit.setFocus()
    if dialog.exec():
        return chosen
    return None


def button_row(layout, buttons):
    row = QHBoxLayout()
    for label, callback in buttons:
        button = QPushButton(label)
        button.clicked.connect(callback)
        row.addWidget(button)
    layout.addLayout(row)


def repeat_picker(value=''):
    box = QComboBox()
    for key, label in REPEAT_OPTIONS.items():
        box.addItem(label, key)
    box.setCurrentIndex(max(0, box.findData(value)))
    return box


def reminder_summary(todo):
    due = datetime.fromtimestamp(todo['due']).strftime('%Y-%m-%d %H:%M:%S')
    repeat = REPEAT_OPTIONS[todo.get('repeat', '')]
    return f'事项：{todo["text"]}\n提醒时间：{due}\n重复：{repeat}'


def prompt_reminder(parent, sentence='', mode=''):
    dialog = PetDialog(parent)
    dialog.setWindowTitle('一句话添加提醒')
    dialog.resize(500, 150)
    layout = QVBoxLayout(dialog)
    text = QLineEdit(sentence)
    text.setMaxLength(150)
    text.setPlaceholderText('例如：10分钟后提醒我喝水')
    layout.addWidget(text)
    repeat = repeat_picker(mode)
    form = QFormLayout()
    form.addRow('重复', repeat)
    layout.addLayout(form)
    preview = QLabel()
    preview.setWordWrap(True)
    preview.setTextFormat(Qt.PlainText)
    layout.addWidget(preview)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    save = buttons.button(QDialogButtonBox.Save)
    save.setText('确认添加')
    buttons.button(QDialogButtonBox.Cancel).setText('取消')
    layout.addWidget(buttons)
    todo = None

    def update_preview():
        nonlocal todo
        todo = None
        try:
            if text.text().strip():
                todo = parse_reminder(text.text())
            if todo is None:
                preview.setText('也可以输入「今晚8点提醒我开会」或「明天 09:30 提醒我交报告」。')
            else:
                if repeat.currentData():
                    todo['repeat'] = repeat.currentData()
                    todo['due'] = next_repeat(todo['due'], todo['repeat'], todo['due'] - 1)
                preview.setText(reminder_summary(todo))
        except ValueError as error:
            preview.setText(str(error))
        save.setEnabled(todo is not None)

    def confirm():
        if todo is not None and todo['due'] > time():
            dialog.accept()
        else:
            update_preview()
            if todo is not None:
                preview.setText('上一次预览的时间已过，已重新计算。\n' + preview.text())

    text.textChanged.connect(update_preview)
    repeat.currentIndexChanged.connect(update_preview)
    buttons.accepted.connect(confirm)
    buttons.rejected.connect(dialog.reject)
    update_preview()
    try:
        return todo if dialog.exec() else None
    finally:
        dialog.deleteLater()


def edit_menu(parent, labels, hidden, groups=None):
    dialog = PetDialog(parent)
    dialog.setWindowTitle('配置菜单')
    dialog.resize(380, 480)
    layout = QVBoxLayout(dialog)
    layout.addWidget(QLabel('勾选要显示的条目，拖动调整顺序。选中条目后可设置子菜单。'))
    items = QListWidget()
    items.setDragDropMode(QListWidget.DragDropMode.InternalMove)
    layout.addWidget(items)
    for label in labels:
        item = QListWidgetItem(label, items)
        item.setCheckState(Qt.Unchecked if label in hidden else Qt.Checked)
        item.setData(Qt.UserRole, (groups or {}).get(label, ''))

    group = QLineEdit()
    group.setMaxLength(30)
    group.setPlaceholderText('子菜单名称，留空放在顶层')
    layout.addWidget(group)
    items.currentItemChanged.connect(lambda current, _: group.setText(current.data(Qt.UserRole) if current else ''))

    def set_group(text):
        item = items.currentItem()
        if item:
            item.setData(Qt.UserRole, text.strip())

    group.textEdited.connect(set_group)
    items.setCurrentRow(0)
    preview = QLabel()
    preview.setWordWrap(True)
    preview.setTextFormat(Qt.PlainText)

    def update_preview():
        visible = {}
        for index in range(items.count()):
            item = items.item(index)
            if item.checkState() == Qt.Checked:
                name = item.data(Qt.UserRole)
                if name:
                    visible.setdefault(('group', name), []).append(item.text())
                else:
                    visible[('item', item.text())] = []
        labels = [f'{name}（{"、".join(children)}）' if children else name
                  for (_, name), children in visible.items()]
        preview.setText('菜单顺序：' + (' → '.join(labels) or '无自定义条目'))

    items.itemChanged.connect(update_preview)
    items.model().rowsMoved.connect(update_preview)
    items.model().rowsInserted.connect(update_preview)
    items.model().rowsRemoved.connect(update_preview)
    update_preview()
    layout.addWidget(preview)
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)
    if not dialog.exec():
        return None
    order = [items.item(index) for index in range(items.count())]
    return ([item.text() for item in order],
            [item.text() for item in order if item.checkState() == Qt.Unchecked],
            {item.text(): item.data(Qt.UserRole) for item in order if item.data(Qt.UserRole)})


def edit_settings(pet):
    dialog = PetDialog(pet)
    dialog.setWindowTitle('桌宠设置')
    form = QFormLayout(dialog)
    numbers = {}
    for key, label, current, minimum, maximum in (
        ('opacity', '不透明度（%）', pet.opacity, 20, 100),
        ('speed', '播放速率（%）', pet.speed, 25, 300),
        ('interval', '自动互动间隔（秒）', pet.interval, 5, 3600),
        ('bubble_size', '气泡大小（%）', pet.bubble_size, *BUBBLE_SIZE_RANGE),
        ('bubble_font', '气泡字号（像素）', pet.bubble_font, 10, 24),
    ):
        field = QSpinBox()
        field.setRange(minimum, maximum)
        field.setValue(current)
        form.addRow(label, field)
        numbers[key] = field
    switches = {}
    for key, label, checked in (
        ('auto', '自动互动', pet.auto_enabled),
        ('floor_walk', '沿屏幕底边散步', pet.walk_enabled),
        ('locked', '锁定位置', pet.locked),
        ('click_sound', '点击音效', pet.settings.value('click_sound', False, type=bool)),
        ('self_talk', '随机自言自语', pet.settings.value('self_talk', False, type=bool)),
        ('edge_probe', '边缘探头', pet.settings.value('edge_probe', False, type=bool)),
    ):
        field = QCheckBox()
        field.setChecked(checked)
        form.addRow(label, field)
        switches[key] = field
    buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    form.addRow(buttons)
    if not dialog.exec():
        return None
    return ({key: field.value() for key, field in numbers.items()},
            {key: field.isChecked() for key, field in switches.items()})


class TodoDialog(PetDialog):
    def __init__(self, pet):
        super().__init__(pet)
        self.pet = pet
        self.setWindowTitle('待办提醒')
        self.resize(520, 360)
        layout = QVBoxLayout(self)
        self.items = QListWidget()
        layout.addWidget(self.items)
        button_row(layout, [('添加', self.add), ('一句话添加', self.add_sentence), ('编辑', self.edit),
                            ('删除', self.remove), ('关闭', self.accept)])
        self.snooze_button = QPushButton('10 分钟后再提醒')
        self.snooze_button.clicked.connect(self.snooze)
        layout.addWidget(self.snooze_button)
        self.items.currentRowChanged.connect(self.update_snooze_button)
        self.items.itemDoubleClicked.connect(lambda item: self.edit())
        self.refresh()

    def refresh(self):
        selected = self.selected()
        self.items.clear()
        self.rows = sorted(self.pet.todos, key=lambda todo: (reminder_due(todo) is None, reminder_due(todo) or todo['due']))
        for todo in self.rows:
            pending = reminder_due(todo)
            due = datetime.fromtimestamp(pending if pending is not None else todo['due']).strftime('%Y-%m-%d %H:%M')
            status = REPEAT_OPTIONS.get(todo.get('repeat')) or '待提醒'
            if pending is None:
                status = '已归档'
            elif pending == todo.get('snooze_due'):
                status = '稍后提醒'
            self.items.addItem(f'{status}  {due}  {todo["text"]}')
        if selected is not None:
            for index, todo in enumerate(self.rows):
                if todo is selected:
                    self.items.setCurrentRow(index)
                    break
        self.update_snooze_button()

    def selected(self):
        row = self.items.currentRow()
        return self.rows[row] if row >= 0 else None

    def update_snooze_button(self):
        todo = self.selected()
        self.snooze_button.setEnabled(todo is not None and can_snooze(todo, time()))

    def snooze(self):
        todo = self.selected()
        if todo is not None and snooze_reminder(todo, time()):
            self.pet.save_todos()
        self.update_snooze_button()

    def add(self):
        self.edit_item(None)

    def add_sentence(self):
        todo = prompt_reminder(self)
        if todo is not None:
            self.pet.todos.append(todo)
            self.pet.save_todos()

    def edit(self):
        todo = self.selected()
        if todo is not None:
            self.edit_item(todo)

    def remove(self):
        todo = self.selected()
        if todo is not None:
            self.pet.todos[:] = [item for item in self.pet.todos if item is not todo]
            self.pet.save_todos()

    def edit_item(self, todo):
        dialog = PetDialog(self)
        dialog.setWindowTitle('设置提醒')
        form = QFormLayout(dialog)
        text = QLineEdit(todo['text'] if todo else '')
        text.setMaxLength(100)
        due = int(todo['due']) if todo and not todo.get('archived') else int(time()) + 300
        when = QDateTimeEdit(QDateTime.fromSecsSinceEpoch(due))
        when.setDisplayFormat('yyyy-MM-dd HH:mm')
        when.setCalendarPopup(True)
        lead = QSpinBox()
        lead.setRange(0, 1440)
        lead.setValue(todo.get('lead', 0) if todo else 5)
        lead.setSpecialValueText('关闭')
        repeat = repeat_picker(todo.get('repeat', '') if todo else '')
        starting_repeat = repeat.currentData()
        starts_active = todo is not None and not todo.get('archived')
        form.addRow('事项', text)
        form.addRow('到期时间', when)
        form.addRow('重复', repeat)
        form.addRow('提前提醒（分钟）', lead)
        status = QLabel()
        status.setWordWrap(True)
        form.addRow(status)
        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        save = buttons.button(QDialogButtonBox.Save)
        text.textChanged.connect(lambda value: save.setEnabled(bool(value.strip())))
        save.setEnabled(bool(text.text().strip()))
        def confirm():
            chosen = when.dateTime().toSecsSinceEpoch()
            mode = repeat.currentData()
            next_due = next_repeat(chosen, mode, chosen - 1) if mode else chosen
            if next_due != chosen:
                when.setDateTime(QDateTime.fromSecsSinceEpoch(next_due))
                status.setText('工作日提醒已顺延到周一，请核对时间后保存。')
                return
            dialog.accept()

        buttons.accepted.connect(confirm)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if not dialog.exec():
            return
        updated = {'text': text.text().strip(), 'due': when.dateTime().toSecsSinceEpoch(), 'lead': lead.value()}
        if repeat.currentData():
            updated['repeat'] = repeat.currentData()
        if todo is None:
            self.pet.todos.append(updated)
        else:
            if starts_active and updated['due'] == due and repeat.currentData() == starting_repeat:
                updated['due'] = todo['due']
                for key in ('last_fired', 'snooze_due', 'archived'):
                    if key in todo:
                        updated[key] = todo[key]
                if updated['lead'] == todo.get('lead', 0) and todo.get('warned'):
                    updated['warned'] = True
            todo.clear()
            todo.update(updated)
        self.pet.save_todos()
