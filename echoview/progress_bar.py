"""A small subpixel progress bar; repaint only its own narrow widget."""
from PySide6.QtCore import Qt, QRectF
from PySide6.QtGui import QColor, QPainter, QPainterPath
from PySide6.QtWidgets import QProgressBar


class SmoothProgressBar(QProgressBar):
    THEMES = {
        'light': ('#f0f0f0', '#a0a0a0', '#cccccc'),
        'dark': ('#333333', '#888888', '#444444'),
        'spotify': ('#121212', '#1db954', '#1db954'),
        'coffee': ('#423828', '#8b4513', '#8b4513'),
        'default': ('#333333', '#888888', '#444444'),
    }

    def __init__(self, parent=None):
        super().__init__(parent)
        self._fraction = 0.0
        self._time_text = ''
        self._bar_visible = True
        self.setValue(0)
        self.setTheme('dark')

    def setTheme(self, theme):
        self._background, self._fill, self._border = map(QColor, self.THEMES.get(theme, self.THEMES['default']))
        self.update()

    def setPlaybackText(self, text, bar_visible=True):
        if (text, bar_visible) != (self._time_text, self._bar_visible):
            self._time_text, self._bar_visible = text, bar_visible
            self.update()

    def setFraction(self, fraction):
        fraction = max(0.0, min(1.0, fraction))
        if fraction == self._fraction:
            return
        self._fraction = fraction
        self.setValue(round(fraction * self.maximum()))  # Accessibility/value API.
        # QProgressBar normally waits for a whole-pixel change before repainting.
        # Repaint fractional movement too, so a slow track doesn't visibly step.
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        outer = QRectF(self.rect())
        if self._time_text:
            width = min(outer.width(), self.fontMetrics().horizontalAdvance(self._time_text) + 12)
            x = outer.right() - width if self._bar_visible else outer.center().x() - width / 2
            text_rect = QRectF(x, outer.y(), width, outer.height())
            painter.setBrush(QColor('#161616'))
            painter.drawRoundedRect(text_rect, 4, 4)
            painter.setPen(QColor('#ffffff'))
            painter.drawText(text_rect, Qt.AlignCenter, self._time_text)
            painter.setPen(Qt.NoPen)
            outer.setRight(text_rect.left() - 8)
            outer.setTop((self.height() - 10) / 2)
            outer.setHeight(10)
        if not self._bar_visible or outer.width() <= 0:
            return
        radius = min(5.0, outer.height() / 2)
        painter.setBrush(self._border)
        painter.drawRoundedRect(outer, radius, radius)
        inner = outer.adjusted(1, 1, -1, -1)
        if inner.width() <= 0 or inner.height() <= 0:
            return
        path = QPainterPath()
        path.addRoundedRect(inner, max(0, radius - 1), max(0, radius - 1))
        painter.fillPath(path, self._background)
        painter.setClipPath(path)
        painter.setBrush(self._fill)
        painter.drawRect(QRectF(inner.x(), inner.y(), inner.width() * self._fraction, inner.height()))
