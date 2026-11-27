"""Show a small, non-activating toolbar beside the hovered desktop pet."""
import numpy as np
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, QRectF, QSize, Qt, QTimer
from PySide6.QtGui import QColor, QCursor, QIcon, QImage, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QToolButton, QVBoxLayout, QWidget


VISIBLE_ALPHA = 32


def toolbar_position(body, size, area):
    gap = 8
    right_room = area.right() - body.right()
    left_room = body.left() - area.left()
    if right_room >= size.width() + gap or right_room >= left_room:
        x = body.right() + 1 + gap
    else:
        x = body.left() - size.width() - gap
    y = body.center().y() - size.height() // 2
    return QPoint(max(area.left(), min(x, area.right() + 1 - size.width())),
                  max(area.top(), min(y, area.bottom() + 1 - size.height())))


def shortcut_icon(kind):
    image = QPixmap(32, 32)
    image.setDevicePixelRatio(2)
    image.fill(Qt.transparent)
    with QPainter(image) as painter:
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(QPen(QColor('#7258a3'), 1.35, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin))
        if kind == 'chat':
            path = QPainterPath(QPointF(4, 2.5))
            path.lineTo(12, 2.5)
            path.quadTo(14, 2.5, 14, 4.5)
            path.lineTo(14, 9)
            path.quadTo(14, 11, 12, 11)
            path.lineTo(7, 11)
            path.lineTo(3.5, 13.5)
            path.lineTo(3.5, 11)
            path.quadTo(2, 11, 2, 9)
            path.lineTo(2, 4.5)
            path.quadTo(2, 2.5, 4, 2.5)
            painter.drawPath(path)
            painter.drawLine(QPointF(5, 6.6), QPointF(11, 6.6))
        elif kind == 'todos':
            painter.drawRoundedRect(QRectF(2.5, 2, 11, 12), 2, 2)
            painter.drawLine(QPointF(5.2, 8), QPointF(7.2, 10))
            painter.drawLine(QPointF(7.2, 10), QPointF(10.8, 6))
        else:
            painter.drawRoundedRect(QRectF(1.8, 3, 12.4, 10), 2, 2)
            painter.drawLine(QPointF(2.2, 6.5), QPointF(13.8, 6.5))
            painter.drawLine(QPointF(4.8, 10), QPointF(7.2, 10))
    return QIcon(image)


class HoverShortcuts(QWidget):
    def __init__(self, pet):
        super().__init__(pet, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus)
        self.pet = pet
        self.body = QRect()
        self.setWindowTitle('桌宠快捷栏')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setStyleSheet('''
            QToolButton {
                color: #3d2e53;
                background: transparent;
                border: 1px solid transparent;
                border-radius: 7px;
                padding: 0 5px;
                font-size: 13px;
            }
            QToolButton:hover { background-color: #eee4fa; border-color: #e3d4f2; }
            QToolButton:pressed { background-color: #decdf2; }
        ''')
        layout = QVBoxLayout(self)
        layout.setContentsMargins(5, 5, 5, 5)
        layout.setSpacing(1)
        self.buttons = {}
        for name, label in (('chat', '对话'), ('todos', '待办'), ('quota', '查额度')):
            button = QToolButton(self)
            button.setText(label)
            button.setIcon(shortcut_icon(name))
            button.setIconSize(QSize(16, 16))
            button.setToolButtonStyle(Qt.ToolButtonTextBesideIcon)
            button.setFixedSize(80, 30)
            button.setFocusPolicy(Qt.NoFocus)
            button.setCursor(Qt.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, action=name: self.activate(action))
            layout.addWidget(button)
            self.buttons[name] = button
        self.setFixedSize(layout.sizeHint())
        self.reveal_timer = QTimer(self)
        self.reveal_timer.setSingleShot(True)
        self.reveal_timer.setInterval(170)
        self.reveal_timer.timeout.connect(self.reveal)
        self.dismiss_timer = QTimer(self)
        self.dismiss_timer.setSingleShot(True)
        self.dismiss_timer.setInterval(320)
        self.dismiss_timer.timeout.connect(self.dismiss_if_outside)
        pet.setMouseTracking(True)
        pet.installEventFilter(self)

    def paintEvent(self, event):
        with QPainter(self) as painter:
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setBrush(QColor('#fcf8ff'))
            painter.setPen(QColor('#c8b6e1'))
            painter.drawRoundedRect(QRectF(self.rect()).adjusted(.5, .5, -.5, -.5), 12, 12)

    def available(self):
        host = self.pet.owner or self.pet
        return (self.pet.isVisible() and self.pet.offset is None
                and not self.pet.windowFlags() & Qt.WindowTransparentForInput
                and QApplication.mouseButtons() == Qt.NoButton
                and not QApplication.activePopupWidget() and not QApplication.activeModalWidget()
                and not getattr(host, 'selecting_screenshot', False))

    def reveal(self):
        frame = self.pet.pixmap
        if (getattr(self.pet, 'bubble_hovered', False)
                or not self.available() or not self.pet.underMouse() or frame.isNull()):
            return
        transform = self.pet.sprite_transform()
        transform.translate(-240, -135)
        transform.scale(480 / frame.width(), 270 / frame.height())
        inverse, invertible = transform.inverted()
        point = inverse.map(QPointF(self.pet.mapFromGlobal(QCursor.pos()))).toPoint() if invertible else QPoint(-1, -1)
        if not frame.rect().contains(point):
            return
        # VP9 can leave faint alpha in the background. Apply the same cutoff to the hit and the bounds.
        image = frame.toImage().convertToFormat(QImage.Format_Alpha8)
        alpha = np.frombuffer(image.constBits(), dtype=np.uint8).reshape(image.height(), image.bytesPerLine())
        if alpha[point.y(), point.x()] < VISIBLE_ALPHA:
            return
        visible = alpha[:, :image.width()] >= VISIBLE_ALPHA
        columns = np.flatnonzero(visible.any(axis=0))
        rows = np.flatnonzero(visible.any(axis=1))
        bounds = QRect(QPoint(int(columns[0]), int(rows[0])), QPoint(int(columns[-1]), int(rows[-1])))
        self.body = transform.mapRect(QRectF(bounds)).toAlignedRect().translated(self.pet.mapToGlobal(QPoint()))
        screen = QApplication.screenAt(self.body.center()) or self.pet.screen()
        self.move(toolbar_position(self.body, self.size(), screen.availableGeometry()))
        self.pet.pause_walk()
        self.show()

    def dismiss(self):
        self.reveal_timer.stop()
        self.dismiss_timer.stop()
        self.hide()

    def dismiss_if_outside(self):
        if not self.underMouse() and not (self.pet.underMouse() and self.body.contains(QCursor.pos())):
            self.dismiss()

    def enterEvent(self, event):
        self.dismiss_timer.stop()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self.dismiss_timer.start()
        super().leaveEvent(event)

    def eventFilter(self, watched, event):
        if watched is self.pet:
            kind = event.type()
            if kind in (QEvent.Enter, QEvent.MouseMove):
                if self.isVisible():
                    if self.body.contains(QCursor.pos()):
                        self.dismiss_timer.stop()
                    elif not self.dismiss_timer.isActive():
                        self.dismiss_timer.start()
                elif not self.reveal_timer.isActive() and self.available():
                    self.reveal_timer.start()
            elif kind == QEvent.Leave:
                self.reveal_timer.stop()
                if self.isVisible():
                    self.dismiss_timer.start()
            elif kind in (QEvent.Hide, QEvent.Move, QEvent.Resize, QEvent.MouseButtonPress, QEvent.ContextMenu):
                self.dismiss()
        return False

    def activate(self, action):
        self.dismiss()
        host = self.pet.owner or self.pet
        if action == 'chat':
            host.open_quick_chat()
        elif action == 'todos':
            host.edit_todos()
        else:
            host.widgets.request_quota(target=self.pet)
