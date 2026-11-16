"""Place desktop-pet windows on the owner's screen, clear of the owner when possible."""
from PySide6.QtCore import QEvent, QObject, QPoint, QRect, Qt
from PySide6.QtWidgets import QDialog, QFileDialog, QInputDialog, QLineEdit, QMessageBox


class WindowPlacement(QObject):
    def eventFilter(self, window, event):
        if event.type() == QEvent.Show:
            owner = window.parentWidget()
            if owner is not None:
                while owner.parentWidget() is not None:
                    owner = owner.parentWidget()
                anchor = owner.frameGeometry()
                area = owner.screen().availableGeometry()
                size = window.frameGeometry().size()
                x = anchor.center().x() - size.width() // 2
                y = anchor.center().y() - size.height() // 2
                positions = (QPoint(x, anchor.top() - size.height() - 12), QPoint(x, anchor.bottom() + 13),
                             QPoint(anchor.left() - size.width() - 12, y), QPoint(anchor.right() + 13, y))
                clamped = [QPoint(max(area.left(), min(p.x(), area.right() - size.width() + 1)),
                                  max(area.top(), min(p.y(), area.bottom() - size.height() + 1)))
                           for p in positions]

                def overlap(point):
                    shared = QRect(point, size).intersected(anchor)
                    return shared.width() * shared.height()

                window.move(min(clamped, key=overlap))
            window.raise_()
        return False


def keep_in_front(window):
    window.setWindowFlag(Qt.WindowStaysOnTopHint, True)
    window._pet_placement = WindowPlacement(window)
    window.installEventFilter(window._pet_placement)
    return window


class PetDialog(QDialog):
    def __init__(self, parent, flags=Qt.Dialog | Qt.WindowTitleHint | Qt.WindowSystemMenuHint | Qt.WindowCloseButtonHint):
        super().__init__(parent, flags)
        keep_in_front(self)
        self.drag_offset = None

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.drag_offset is not None and event.buttons() & Qt.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_offset)
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.drag_offset = None
        super().mouseReleaseEvent(event)


def pick_files(parent, title, filters='', mode=QFileDialog.ExistingFile):
    dialog = QFileDialog(parent)
    # The native file picker controls its own position. Use Qt's picker here so it stays with the pet.
    dialog.setOption(QFileDialog.DontUseNativeDialog)
    dialog.setWindowTitle(title)
    dialog.setFileMode(mode)
    if mode == QFileDialog.Directory:
        dialog.setOption(QFileDialog.ShowDirsOnly)
    if filters:
        dialog.setNameFilter(filters)
    return dialog.selectedFiles() if keep_in_front(dialog).exec() else []


def edit_text(parent, title, label, value, multiline=False):
    dialog = QInputDialog(parent)
    dialog.setWindowTitle(title)
    dialog.setLabelText(label)
    dialog.setOption(QInputDialog.UsePlainTextEditForTextInput, multiline)
    dialog.setTextEchoMode(QLineEdit.Normal)
    dialog.setTextValue(value)
    return dialog.textValue() if keep_in_front(dialog).exec() else None


def warn(parent, title, message):
    dialog = QMessageBox(QMessageBox.Warning, title, message, QMessageBox.Ok, parent)
    dialog.setTextFormat(Qt.PlainText)
    keep_in_front(dialog).exec()
