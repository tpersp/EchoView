"""Transient screen labels above native/external players; no playback changes."""
from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QLabel


class IdentificationBadge(QLabel):
    def __init__(self, parent):
        super().__init__(parent, Qt.Tool | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint
                         | Qt.WindowDoesNotAcceptFocus | Qt.WindowTransparentForInput)
        self.setWindowTitle('EchoView display identification')
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setTextFormat(Qt.PlainText)
        self.setAlignment(Qt.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet('background:#101820;color:white;border:3px solid #6ee7ce;'
                           'border-radius:16px;padding:16px;')
        self.timer = QTimer(self)
        self.timer.setSingleShot(True)
        self.timer.timeout.connect(self.hide)

    def show_for(self, screen, name, milliseconds=5000):
        geometry = screen.geometry()
        width = min(520, max(1, geometry.width() - 32))
        height = min(140, max(1, geometry.height() - 32))
        self.setGeometry(geometry.center().x() - width // 2,
                         geometry.center().y() - height // 2, width, height)
        font = QFont('DejaVu Sans')
        font.setPixelSize(max(18, min(44, geometry.height() // 12, geometry.width() // 12)))
        font.setBold(True)
        self.setFont(font)
        self.setText(name)
        self.show()
        self.raise_()
        self.timer.start(milliseconds)

    def dismiss(self):
        self.timer.stop()
        self.hide()
