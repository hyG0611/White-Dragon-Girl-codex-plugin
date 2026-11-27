"""Draw the DSH pet's speech as a cloud in its 480 × 320 canvas."""
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QLinearGradient, QPainterPath, QPen, QTextLayout, QTextOption, QTransform


BUBBLE_SIZE_RANGE = (60, 150)


@dataclass(frozen=True)
class BubbleMessage:
    text: str
    duration: int = 0
    open_chat: bool = False
    important: bool = False
    activity: bool = False


def cloud_outline(width, bottom):
    left = (480 - width) / 2

    def x(fraction):
        return left + width * fraction

    path = QPainterPath(QPointF(x(.095), 20))
    path.cubicTo(x(.11), 8, x(.235), 3, x(.319), 11)
    path.cubicTo(x(.352), 2, x(.501), -2, x(.561), 10)
    path.cubicTo(x(.615), 3, x(.726), 6, x(.769), 16)
    path.cubicTo(x(.856), 10, x(.954), 17, x(.949), 29)
    path.cubicTo(x(1.013), 32, x(1.004), bottom - 9, x(.95), bottom - 5)
    path.cubicTo(x(.933), bottom + 6, x(.835), bottom + 9, x(.767), bottom + 1)
    path.cubicTo(x(.714), bottom + 9, x(.625), bottom + 10, x(.554), bottom + 3)
    path.cubicTo(x(.501), bottom + 12, x(.38), bottom + 10, x(.324), bottom + 2)
    path.cubicTo(x(.261), bottom + 10, x(.159), bottom + 7, x(.125), bottom - 1)
    path.cubicTo(x(.05), bottom + 2, x(.005), bottom - 8, x(.018), bottom - 15)
    path.cubicTo(x(-.023), bottom - 25, x(.01), 20, x(.095), 20)
    path.closeSubpath()
    return path


class CloudBubble:
    def __init__(self, message, font, size=100):
        self.font = font
        self.size = size
        scale = size / 100
        horizontal_padding = 60 * scale
        line_width = min(352 * scale, 440 - horizontal_padding)
        text_bottom = min(280, 319 - 40 * scale)
        # QTextLayout honors explicit line breaks and wraps long unbroken words.
        text = message.replace('\r\n', '\n').replace('\r', '\n').replace('\n', '\u2028')
        self.text = QTextLayout(text, font)
        option = QTextOption()
        option.setWrapMode(QTextOption.WrapAtWordBoundaryOrAnywhere)
        self.text.setTextOption(option)
        self.lines = []
        self.ellipsis = None
        y, width = 26 * scale, 0
        self.text.beginLayout()
        while (line := self.text.createLine()).isValid():
            line.setLineWidth(line_width)
            if y + line.height() > text_bottom:
                if self.lines:
                    last_line = self.lines.pop()
                    self.ellipsis = QRectF(208, last_line.y(), 64, last_line.height())
                break
            advance = line.naturalTextWidth()
            line.setPosition(QPointF((480 - advance) / 2, y))
            self.lines.append(line)
            width = max(width, advance)
            y += line.height() + 1
        self.text.endLayout()
        outline = cloud_outline(max(148 * scale, width + horizontal_padding), y / scale + 8)
        self.body = QTransform.fromScale(1, scale).map(outline)
        self.edge = self.body.boundingRect()
        bottom = self.edge.bottom()
        self.tail = QPainterPath()
        self.tail.addEllipse(QPointF(240 + 12 * scale, bottom + 8 * scale), 5 * scale, 4.5 * scale)
        self.tail.addEllipse(QPointF(240, bottom + 17 * scale), 3 * scale, 2.7 * scale)

    def contains(self, point):
        return self.body.contains(point) or self.tail.contains(point)

    def draw(self, painter):
        painter.save()
        gradient = QLinearGradient(0, self.edge.top(), 0, self.edge.bottom())
        gradient.setColorAt(0, QColor('#fffefe'))
        gradient.setColorAt(.58, QColor('#faf7ff'))
        gradient.setColorAt(1, QColor('#eee7fa'))
        painter.fillPath(self.body.translated(0, 2.5), QColor(78, 57, 120, 38))
        painter.setPen(QPen(QColor('#b6a4d6'), 1.5))
        painter.setBrush(gradient)
        painter.drawPath(self.body)
        painter.setBrush(QColor('#f7f1ff'))
        painter.drawPath(self.tail)
        painter.setPen(QColor('#352a4e'))
        for line in self.lines:
            line.draw(painter, QPointF(0, 0))
        if self.ellipsis is not None:
            painter.setFont(self.font)
            painter.drawText(self.ellipsis, Qt.AlignCenter, '…')
        painter.restore()
