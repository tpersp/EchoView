import sys
import os
import requests
from PySide6.QtWidgets import QApplication, QLabel, QMainWindow
from PySide6.QtCore import QTimer, Qt
from PySide6.QtGui import QGuiApplication, QPixmap, QMovie
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtMultimedia import QMediaPlayer, QAudioOutput
import tempfile
import shutil

class DisplayWindow(QMainWindow):
    def __init__(self, screen=None):
        super().__init__()
        self.setWindowTitle("EchoView Display")
        self.label = QLabel(self)
        self.label.setAlignment(Qt.AlignCenter)
        self.setCentralWidget(self.label)
        self.api_url = os.environ.get("ECHOVIEW_API_URL", "http://localhost:8000")
        self.current_file = None
        self.movie = None
        self.video_widget = None
        self.media_player = None
        self.audio_output = None
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_slide)
        self.timer.start(2000)
        if screen:
            self.setGeometry(screen.geometry())
            self.move(screen.geometry().topLeft())
            self.showFullScreen()
        else:
            self.resize(800, 480)
        self.gif_cache = {}
        self.image_cache = {}  # filename -> QPixmap
        self.video_cache = set()  # set of cached video filenames (local path)
        self.gif_cache_dir = os.path.join(tempfile.gettempdir(), "echoview_gifcache")
        self.image_cache_dir = os.path.join(tempfile.gettempdir(), "echoview_imgcache")
        self.video_cache_dir = os.path.join(tempfile.gettempdir(), "echoview_vidcache")
        os.makedirs(self.gif_cache_dir, exist_ok=True)
        os.makedirs(self.image_cache_dir, exist_ok=True)
        os.makedirs(self.video_cache_dir, exist_ok=True)
        self.preload_gif_count = 3
        self.preload_img_count = 2
        self.preload_vid_count = 2

    def get_gif_cache_path(self, filename):
        return os.path.join(self.gif_cache_dir, filename.replace("/", "_"))

    def get_image_cache_path(self, filename):
        return os.path.join(self.image_cache_dir, filename.replace("/", "_"))

    def get_video_cache_path(self, filename):
        return os.path.join(self.video_cache_dir, filename.replace("/", "_"))

    def preload_next_media(self, current_filename):
        # Preload next N GIFs, images, and videos
        try:
            resp = requests.get(f"{self.api_url}/slideshow", timeout=2)
            state = resp.json()
            files = state.get("files", [])
            if not files or current_filename not in files:
                return
            idx = files.index(current_filename)
            image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
            gif_exts = ['.gif']
            video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv']
            # --- GIFs ---
            keep_gifs = []
            for offset in range(0, self.preload_gif_count+1):
                next_idx = (idx + offset) % len(files)
                f = files[next_idx]
                if f.lower().endswith('.gif'):
                    keep_gifs.append(f)
            for gif in list(self.gif_cache.keys()):
                if gif not in keep_gifs:
                    self.gif_cache[gif].stop()
                    del self.gif_cache[gif]
            for gif in keep_gifs:
                if gif not in self.gif_cache:
                    cache_path = self.get_gif_cache_path(gif)
                    if not os.path.exists(cache_path):
                        url = f"{self.api_url}/media/{gif}"
                        try:
                            r = requests.get(url, timeout=10)
                            r.raise_for_status()
                            with open(cache_path, "wb") as f:
                                f.write(r.content)
                        except Exception:
                            continue
                    try:
                        movie = QMovie(cache_path)
                        self.gif_cache[gif] = movie
                    except Exception:
                        pass
            # --- Images ---
            keep_imgs = []
            for offset in range(0, self.preload_img_count+1):
                next_idx = (idx + offset) % len(files)
                f = files[next_idx]
                if os.path.splitext(f)[1].lower() in image_exts:
                    keep_imgs.append(f)
            for img in list(self.image_cache.keys()):
                if img not in keep_imgs:
                    del self.image_cache[img]
            for img in keep_imgs:
                if img not in self.image_cache:
                    cache_path = self.get_image_cache_path(img)
                    if not os.path.exists(cache_path):
                        url = f"{self.api_url}/media/{img}"
                        try:
                            r = requests.get(url, timeout=10)
                            r.raise_for_status()
                            with open(cache_path, "wb") as f:
                                f.write(r.content)
                        except Exception:
                            continue
                    try:
                        pixmap = QPixmap()
                        pixmap.load(cache_path)
                        self.image_cache[img] = pixmap
                    except Exception:
                        pass
            # --- Videos ---
            keep_vids = []
            for offset in range(0, self.preload_vid_count+1):
                next_idx = (idx + offset) % len(files)
                f = files[next_idx]
                if os.path.splitext(f)[1].lower() in video_exts:
                    keep_vids.append(f)
            for vid in list(self.video_cache):
                if vid not in keep_vids:
                    self.video_cache.remove(vid)
            for vid in keep_vids:
                cache_path = self.get_video_cache_path(vid)
                if not os.path.exists(cache_path):
                    url = f"{self.api_url}/media/{vid}"
                    try:
                        r = requests.get(url, timeout=15)
                        r.raise_for_status()
                        with open(cache_path, "wb") as f:
                            f.write(r.content)
                        self.video_cache.add(vid)
                    except Exception:
                        continue
        except Exception:
            pass

    def update_slide(self):
        try:
            resp = requests.get(f"{self.api_url}/slideshow/current", timeout=2)
            data = resp.json()
            if data.get("spotify"):
                self.show_spotify()
                return
            filename = data.get("filename")
            if filename and filename != self.current_file:
                self.current_file = filename
                self.show_media(filename)
                self.preload_next_media(filename)
        except Exception as e:
            self.label.setText(f"Error: {e}")

    def show_spotify(self):
        try:
            resp = requests.get(f"{self.api_url}/spotify/info", timeout=3)
            info = resp.json()
            if not info.get("playing"):
                self.label.setText("Spotify: Not playing")
                return
            text = f"<b>{info['track']}</b><br>{info['artist']}<br><i>{info['album']}</i>"
            if info.get("album_art"):
                from PySide6.QtGui import QImage
                img_resp = requests.get(info["album_art"], timeout=5)
                img = QImage()
                img.loadFromData(img_resp.content)
                pixmap = QPixmap.fromImage(img)
                self.label.setPixmap(pixmap.scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
                self.label.setText(text)
            else:
                self.label.setText(text)
        except Exception as e:
            self.label.setText(f"Spotify error: {e}")

    def show_media(self, filename):
        # Clean up previous media widgets/players
        if self.video_widget:
            self.video_widget.setParent(None)
            self.video_widget = None
        if self.media_player:
            self.media_player.stop()
            self.media_player = None
        self.audio_output = None
        if self.movie:
            self.label.clear()
            self.movie.stop()
            self.movie = None
        if not filename:
            self.label.setText("No media.")
            return
        url = f"{self.api_url}/media/{filename}"
        ext = os.path.splitext(filename)[1].lower()
        image_exts = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
        gif_exts = ['.gif']
        video_exts = ['.mp4', '.avi', '.mov', '.mkv', '.webm', '.wmv', '.flv']
        if ext in image_exts:
            try:
                # Use preloaded QPixmap if available
                if filename in self.image_cache:
                    pixmap = self.image_cache[filename]
                else:
                    cache_path = self.get_image_cache_path(filename)
                    if not os.path.exists(cache_path):
                        resp = requests.get(url, timeout=10)
                        resp.raise_for_status()
                        with open(cache_path, "wb") as f:
                            f.write(resp.content)
                    pixmap = QPixmap()
                    pixmap.load(cache_path)
                    self.image_cache[filename] = pixmap
                self.label.setPixmap(pixmap.scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
            except Exception as e:
                self.label.setText(f"Image error: {e}")
        elif ext in gif_exts:
            try:
                # Use preloaded QMovie if available
                if filename in self.gif_cache:
                    self.movie = self.gif_cache[filename]
                else:
                    cache_path = self.get_gif_cache_path(filename)
                    if not os.path.exists(cache_path):
                        resp = requests.get(url, timeout=10)
                        resp.raise_for_status()
                        with open(cache_path, "wb") as f:
                            f.write(resp.content)
                    self.movie = QMovie(cache_path)
                    self.gif_cache[filename] = self.movie
                self.label.setMovie(self.movie)
                self.movie.start()
            except Exception as e:
                self.label.setText(f"GIF error: {e}")
        elif ext in video_exts:
            try:
                from PySide6.QtCore import QUrl
                cache_path = self.get_video_cache_path(filename)
                if not os.path.exists(cache_path):
                    resp = requests.get(url, timeout=15)
                    resp.raise_for_status()
                    with open(cache_path, "wb") as f:
                        f.write(resp.content)
                self.video_widget = QVideoWidget(self)
                self.setCentralWidget(self.video_widget)
                self.media_player = QMediaPlayer(self)
                self.audio_output = QAudioOutput(self)
                self.media_player.setAudioOutput(self.audio_output)
                self.media_player.setVideoOutput(self.video_widget)
                self.media_player.setSource(QUrl.fromLocalFile(cache_path))
                self.media_player.play()
            except Exception as e:
                self.setCentralWidget(self.label)
                self.label.setText(f"Video error: {e}")
        else:
            self.label.setText(f"Unsupported file: {filename}")
        if not self.video_widget:
            self.setCentralWidget(self.label)

    def resizeEvent(self, event):
        if self.label.pixmap():
            self.label.setPixmap(self.label.pixmap().scaled(self.label.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation))
        super().resizeEvent(event)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    screens = QGuiApplication.screens()
    windows = []
    for screen in screens:
        win = DisplayWindow(screen)
        win.show()
        windows.append(win)
    sys.exit(app.exec())
