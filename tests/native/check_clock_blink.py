"""Verify separator-only painting without glyph movement using real Qt."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont,QColor
from PySide6.QtWidgets import QApplication,QWidget
from echoview.clock_label import ClockLabel
app=QApplication([])
parent=QWidget();parent.resize(400,80);parent.setStyleSheet('background:#304050;')
label=ClockLabel(parent);label.setGeometry(0,0,400,80)
assert label.font().family()=='DejaVu Sans'
font=QFont(label.font());font.setPixelSize(30);label.setFont(font)
label.setAlignment(Qt.AlignLeft|Qt.AlignVCenter)
label.setStyleSheet('color:#ffffff;background:transparent;')
parent.show();app.processEvents()
for difference in (False,True):
    label.useDifference=difference
    for text in ('13:05:09','13:05','1:05 PM','1:05:09 PM'):
        label.setText(text);label.setSeparatorsVisible(True);app.processEvents()
        visible=parent.grab().toImage();geometry=label.geometry()
        label.setSeparatorsVisible(False);app.processEvents();hidden=parent.grab().toImage()
        assert visible!=hidden,(text,difference)
        expected=QColor('#cfbfaf' if difference else '#ffffff').rgba()
        assert any(visible.pixel(x,y)==expected for x in range(300) for y in range(80)),('text color',difference)
        assert label.text()==text and label.geometry()==geometry
        changed={x for x in range(400) for y in range(80) if visible.pixel(x,y)!=hidden.pixel(x,y)}
        allowed=set()
        metrics=label.fontMetrics()
        for index,char in enumerate(text):
            if char==':':
                left=metrics.horizontalAdvance(text[:index]);right=metrics.horizontalAdvance(text[:index+1])
                allowed.update(range(left-2,right+2))
        assert changed and changed.issubset(allowed),(text,difference,sorted(changed-allowed))
parent.close()
print('Native blink passed: only colons change pixels, digits/AM-PM and geometry stay fixed, both color and automatic-contrast modes.')
