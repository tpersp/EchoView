"""Render existing viewer pixels without changing its clock or reading media."""


def capture_background(window):
    from PySide6.QtCore import Qt, QPoint, QSize
    from PySide6.QtGui import QImage, QPainter, QRegion
    from PySide6.QtWidgets import QWidget

    if not window.running or not window.isVisible():
        raise ValueError('Display unavailable')
    external = any(proc is not None and proc.poll() is None for proc in
                   (window.current_video_proc, window.external_browser_proc))
    if external:
        screen = window.assigned_screen or window.screen()
        if screen is None:
            raise ValueError('Screen unavailable')
        # No virtual-desktop offsets: Qt uses screen-local coordinates on X11.
        image = screen.grabWindow(0).toImage()
        if image.isNull():
            raise ValueError('Screen capture unavailable')
        image = image.scaled(QSize(640, 640), Qt.KeepAspectRatio, Qt.FastTransformation)
    else:
        width, height = window.main_widget.width(), window.main_widget.height()
        scale = min(1, 640/max(width, height))
        image = QImage(max(1, round(width*scale)), max(1, round(height*scale)), QImage.Format_ARGB32_Premultiplied)
        image.fill(Qt.black)
        painter = QPainter(image)
        try:
            painter.scale(image.width()/width, image.height()/height)
            # Qt's children list follows stacking order. Render everything except
            # the clock, so unsaved browser edits never show a second baked clock.
            for child in window.main_widget.children():
                if not isinstance(child, QWidget) or child is window.clock_label or not child.isVisible():
                    continue
                painter.save()
                try:
                    painter.translate(child.pos())
                    if child is window.hls_video_widget:
                        frame = child.videoSink().videoFrame().toImage()
                        if frame.isNull():
                            raise ValueError('Video frame unavailable')
                        painter.drawImage(child.rect(), frame)
                    else:
                        child.render(painter, QPoint(), QRegion(), QWidget.DrawWindowBackground | QWidget.DrawChildren)
                finally:
                    painter.restore()
        finally:
            painter.end()
    image = image.convertToFormat(QImage.Format_RGBA8888)
    return image.width(), image.height(), bytes(image.constBits())
