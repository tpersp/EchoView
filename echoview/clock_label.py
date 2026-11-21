"""Clock text with separators that can disappear without changing its layout."""
from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import Qt, QPointF
from PySide6.QtGui import QColor, QPainter, QTextLayout, QTextOption, QTextCharFormat, QFontDatabase, QFont
from PySide6.QtWidgets import QLabel


@lru_cache(maxsize=1)
def clock_font_family():
    path=Path(__file__).parent/'web/static/fonts/DejaVuSans.ttf'
    identifier=QFontDatabase.addApplicationFont(str(path))
    families=QFontDatabase.applicationFontFamilies(identifier) if identifier>=0 else []
    return families[0] if families else 'DejaVu Sans'


class ClockLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        font=self.font()
        font.setFamily(clock_font_family())
        font.setHintingPreference(QFont.PreferNoHinting)
        font.setBold(False)
        font.setItalic(False)
        self.setFont(font)
        self.useDifference = False
        self.separators_visible = True

    def setSeparatorsVisible(self, visible):
        if self.separators_visible != visible:
            self.separators_visible = visible
            self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)
        if self.useDifference:
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
        painter.setPen(Qt.white if self.useDifference else self.palette().color(self.foregroundRole()))
        layout = QTextLayout(self.text(), self.font())
        option = QTextOption()
        option.setAlignment(self.alignment())
        option.setWrapMode(QTextOption.NoWrap)
        layout.setTextOption(option)
        if not self.separators_visible:
            hidden = QTextCharFormat()
            hidden.setForeground(QColor('transparent'))
            ranges = []
            for index, char in enumerate(self.text()):
                if char == ':':
                    item = QTextLayout.FormatRange()
                    item.start, item.length, item.format = index, 1, hidden
                    ranges.append(item)
            layout.setFormats(ranges)
        layout.beginLayout()
        line = layout.createLine()
        if line.isValid():
            line.setLineWidth(self.width())
        layout.endLayout()
        if line.isValid():
            layout.draw(painter, QPointF(0, (self.height()-line.height())/2))
