"""Artwork-first Spotify layouts; constructed only by the native viewer."""
from PySide6.QtCore import Qt, QRect
from PySide6.QtGui import QFont, QPixmap, QTransform
from PySide6.QtWidgets import QWidget, QLabel
from echoview.displays import fit_dimensions
from echoview.presentation import text_stretch, bounded_int
from echoview.spotify_background import background_style, foreground_colour


class SpotifyCard(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('spotify-card')
        self.setStyleSheet('QWidget#spotify-card { background: #101620; } QLabel { background: transparent; color: #edf2f7; }')
        self.artwork = QLabel(self)
        self.artwork.setAlignment(Qt.AlignCenter)
        self.artwork.setStyleSheet('background: #1c2634; color: #9ba9bc; border-radius: 8px;')
        self.labels = [QLabel(self) for _ in range(4)]
        for label in self.labels:
            label.setWordWrap(True)
            label.setTextFormat(Qt.PlainText)
        self.pixmap = QPixmap()
        self.path = None
        self.rotation = None
        self.scaled_key = None
        self.layout_name = 'album_card'
        self.options = {}
        self.pixel_aspect = 1.0
        self.background_key = None
        self.art_colors = ()

    def set_track(self, path, info, options, pixel_aspect):
        self.options, self.pixel_aspect = options, pixel_aspect
        self.layout_name = options.get('spotify_layout', 'album_card')
        self.art_colors = info.get('art_colors',())
        background = background_style(options,self.art_colors)
        if background != self.background_key:
            self.setStyleSheet('QWidget#spotify-card { background: '+background+'; } QLabel { background: transparent; color: #edf2f7; }')
            self.background_key = background
        rotation = bounded_int(options.get('rotate', 0), 0, -3600, 3600)
        if path != self.path or rotation != self.rotation:
            self.path, self.rotation, self.scaled_key = path, rotation, None
            self.pixmap = QPixmap(path) if path else QPixmap()
            if rotation and not self.pixmap.isNull():
                self.pixmap = self.pixmap.transformed(QTransform().rotate(rotation), Qt.SmoothTransformation)
        for label, name in zip(self.labels, ('song', 'artist', 'album', 'device')):
            text = ('Playing on ' + info['device_name'] if info.get('device_name') else '') if name == 'device' else info.get(name, '')
            label.setText(text if options.get('spotify_show_' + name, name != 'device') else '')
            label.setVisible(bool(label.text()))
        self.arrange()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.arrange()

    def arrange(self):
        if not hasattr(self, 'labels'):
            return
        w, h = self.width(), self.height()
        margin = max(8, min(40, min(w, h) // 15))
        gap = max(8, margin)
        # Reserve the bottom edge for progress and display safe-area insets.
        usable_h = max(1, h - margin * 2 - 25)
        poster = self.layout_name == 'poster' or w * self.pixel_aspect < h * 1.2
        if poster:
            side = max(1, min(int(usable_h * .60), int((w-2*margin)*self.pixel_aspect)))
            art_w = max(1, round(side / self.pixel_aspect))
            self.artwork.setGeometry((w-art_w)//2, margin, art_w, side)
            text_rect = QRect(margin, margin+side+gap, max(1,w-2*margin), max(1,usable_h-side-gap))
        else:
            side = max(1, min(usable_h, int((w-3*margin)*self.pixel_aspect*.48)))
            art_w = max(1, round(side / self.pixel_aspect))
            self.artwork.setGeometry(margin, margin+(usable_h-side)//2, art_w, side)
            text_rect = QRect(margin+art_w+gap, margin, max(1,w-art_w-2*margin-gap), usable_h)
        size = self.artwork.size()
        key = (self.path, size.width(), size.height(), self.pixel_aspect)
        if key != self.scaled_key:
            if self.pixmap.isNull():
                self.artwork.clear()
                self.artwork.setText('Artwork unavailable')
            else:
                width, height = fit_dimensions(self.pixmap.width(), self.pixmap.height(), size.width(), size.height(), self.pixel_aspect)
                self.artwork.setPixmap(self.pixmap.scaled(width, height, Qt.IgnoreAspectRatio, Qt.SmoothTransformation))
            self.scaled_key = key
        base = bounded_int(self.options.get('spotify_font_size', 18), 18, 8, max(8, h//12))
        visible = [label for label in self.labels if label.text()]
        heights = []
        color = foreground_colour(self.options,self.art_colors)
        for index, label in enumerate(self.labels):
            font = QFont(label.font())
            font.setPixelSize(max(8, round(base * (1.8 if index == 0 else 1 if index == 1 else .85 if index == 2 else .75))))
            font.setBold(index == 0)
            font.setStretch(text_stretch(self.pixel_aspect))
            label.setFont(font)
            label.setStyleSheet('color: ' + color + '; background: transparent;')
            label.setAlignment((Qt.AlignHCenter if poster else Qt.AlignLeft) | Qt.AlignVCenter)
            if label in visible:
                heights.append(max(font.pixelSize()+6, label.heightForWidth(text_rect.width())))
        total = sum(heights) + max(0,len(heights)-1)*8
        scale = min(1, text_rect.height()/max(1,total))
        top = text_rect.y() + max(0,round((text_rect.height()-total*scale)/2))
        for label, height in zip(visible, heights):
            label.setGeometry(text_rect.x(), top, text_rect.width(), max(1,round(height*scale)))
            top += round((height+8)*scale)
