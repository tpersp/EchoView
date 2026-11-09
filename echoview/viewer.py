#!/usr/bin/env python3
# -*- coding: utf-8 -*-
'''
echoview.py
Shows images in random/mixed/specific/spotify mode on each connected monitor,
and can display an overlay with clock and Spotify track info.
'''

import sys
import os
import random
import time
import threading
import subprocess
import shutil
import signal
import re
from typing import Optional, List
from datetime import datetime
from collections import OrderedDict
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

from echoview.config import APP_VERSION, IMAGE_DIR, LOG_PATH, VIEWER_HOME

from echoview.browser import qt_flags, chromium_flags
from echoview.streaming import (capabilities as stream_capabilities, playback_environment,
                               stream_flags, RetryPolicy, parse_player_event)


def controller_origin():
    value = os.environ.get("ECHOVIEW_CONTROLLER_URL", "http://127.0.0.1:8080").rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.query or parsed.fragment or parsed.path not in ("", "/"):
        return "http://127.0.0.1:8080"
    return value


os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = qt_flags(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS"))

from PySide6.QtCore import Qt, QTimer, Slot, QSize, QRect, QRectF, QUrl, Signal
from PySide6.QtGui import QPixmap, QMovie, QPainter, QImage, QImageReader, QTransform, QFont
from PySide6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QLabel, QProgressBar,
    QGraphicsScene, QGraphicsPixmapItem, QGraphicsBlurEffect
)
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWebEngineCore import QWebEngineSettings
from PySide6.QtWebEngineWidgets import QWebEngineView

from echoview.spotify_client import Playback, shared_poller
from echoview.presentation import (safe_bounds, safe_area_settings, overlay_bounds, text_stretch,
                                   resource_settings, decode_size, trim_image_cache,
                                   player_presentation_flags, bounded_int, runtime_display_settings)
from echoview.displays import (discover_monitors, reconcile_displays, screen_assignments,
                               apply_output_mode, display_pixel_aspect, fit_dimensions, DISPLAY_ASPECTS)
from echoview.utils import (
    load_config,
    save_config,
    log_message,
    get_ip_address,
    is_ignored_folder,
    media_aspect_label,
)
from echoview.embed_utils import (deserialize_embed_metadata, EmbedMetadata, classify_url,
                                  playback_embed_url, parse_youtube_url_details)

def _get_webengine_settings():
    """Return a settings object across Qt versions."""
    if hasattr(QWebEngineSettings, "defaultSettings"):
        return QWebEngineSettings.defaultSettings()
    if hasattr(QWebEngineSettings, "globalSettings"):
        return QWebEngineSettings.globalSettings()
    return None

_settings = _get_webengine_settings()
if _settings:
    _settings.setAttribute(QWebEngineSettings.PlaybackRequiresUserGesture, False)


# --- Custom label for negative (difference) text drawing ---
class NegativeTextLabel(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        # When useDifference is True, the text is drawn using difference mode.
        self.useDifference = False

    def paintEvent(self, event):
        if self.useDifference:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setCompositionMode(QPainter.CompositionMode_Difference)
            painter.setPen(Qt.white)
            painter.setFont(self.font())
            # Combine current alignment with TextWordWrap flag.
            flags = self.alignment() | Qt.TextWordWrap
            painter.drawText(self.rect(), flags, self.text())
        else:
            super().paintEvent(event)


def detect_monitors():
    return discover_monitors()


class DisplayWindow(QMainWindow):
    spotify_result = Signal(int, object)
    stream_event = Signal(int, str)

    def __init__(self, disp_name, disp_cfg, assigned_screen=None):
        super().__init__()
        self.disp_name = disp_name
        self.disp_cfg = disp_cfg
        self.assigned_screen = assigned_screen
        self.running = True
        self.stream_generation = 0
        self.stream_source = None
        self.stream_metadata = None
        self.stream_retry = RetryPolicy()
        self.stream_live = False
        self._hls_active = False
        self._stream_started = False
        self.stream_event.connect(self._on_stream_event, Qt.QueuedConnection)

        # Caching for foreground images
        self.image_cache = OrderedDict()
        self.cache_capacity = 15
        self.cache_budget = 128 * 1024 * 1024
        self.cache_generation = 0
        self.cache_bytes = 0
        self.prefetch_pending = set()
        self.cache_lock = threading.Lock()
        self.preload_count = 1
        self.aspect_cache = {}

        self.last_displayed_path = None
        self.current_pixmap = None
        self.current_movie = None
        self.handling_gif_frames = False
        self.last_scaled_foreground_image = None
        self.current_video_proc = None
        self.stream_process = None
        self.external_browser_proc = None
        self.external_browser_url = None
        self.external_browser_log_thread = None

        # Cached list and index used when spotify mode falls back to
        # displaying local images.  Building the image list for every
        # fallback caused a noticeable pause when switching GIFs because it
        # rescanned the filesystem each time.  Keeping a dedicated list here
        # lets us reuse it across fallback displays and keeps transitions
        # smooth.
        self.fallback_image_list = []
        self.fallback_index = -1

        # Variables for auto-negative sampling (no longer used for difference mode)
        self.current_drawn_image = None
        self.foreground_drawn_rect = None

        # Set window geometry
        if self.assigned_screen:
            self.setScreen(self.assigned_screen)
            self.setGeometry(self.assigned_screen.geometry())
        else:
            screen = self.screen()
            if screen:
                self.setGeometry(screen.geometry())
        self.setWindowFlag(Qt.FramelessWindowHint)

        # Central widget and child labels
        self.main_widget = QWidget(self)
        self.setCentralWidget(self.main_widget)
        self.main_widget.setStyleSheet("background-color: black;")

        # Background label
        self.bg_label = QLabel(self.main_widget)
        self.bg_label.setScaledContents(False)
        self.bg_label.setStyleSheet("background-color: black;")

        # Foreground label for images
        self.foreground_label = QLabel(self.main_widget)
        self.foreground_label.setScaledContents(False)
        self.foreground_label.setAlignment(Qt.AlignCenter)
        self.foreground_label.setStyleSheet("background-color: transparent;")
        self.foreground_label.setWordWrap(True)

        # Overlay label for clock
        self.clock_label = NegativeTextLabel(self.main_widget)
        self.clock_label.setText("00:00:00")
        self.clock_label.setAlignment(Qt.AlignCenter)
        self.clock_label.setStyleSheet("background: transparent;")

        # Spotify info (track details) label
        self.spotify_info = None
        self.spotify_fetch_id = 0
        self.spotify_fetch_pending = None
        self.spotify_result.connect(self.handle_spotify_result, Qt.QueuedConnection)
        self.spotify_info_label = NegativeTextLabel(self.main_widget)
        self.spotify_info_label.setAlignment(Qt.AlignCenter)
        self.spotify_info_label.setStyleSheet("background: transparent;")
        self.spotify_info_label.hide()  # Hidden unless in spotify mode

        # New: Spotify progress bar and timer
        self.spotify_progress_bar = QProgressBar(self.main_widget)
        self.spotify_progress_bar.hide()
        self.spotify_progress_bar.setTextVisible(False)
        self.spotify_progress_bar.setMinimum(0)
        self.spotify_progress_bar.setMaximum(100)
        self.spotify_progress_timer = QTimer(self)
        self.spotify_progress_timer.timeout.connect(self.update_spotify_progress)

        # Web page view for web_page mode
        self.web_view = QWebEngineView(self.main_widget)
        self.web_view.hide()
        self.web_view.loadFinished.connect(self._on_web_load_finished)

        # Dedicated HLS playback components (hidden unless needed)
        self.hls_video_widget = QVideoWidget(self.main_widget)
        self.hls_video_widget.hide()
        self.hls_audio_output = QAudioOutput(self)
        self.hls_audio_output.setVolume(1.0)
        self.hls_player = QMediaPlayer(self)
        self.hls_player.setAudioOutput(self.hls_audio_output)
        self.hls_player.setVideoOutput(self.hls_video_widget)
        self.hls_player.errorOccurred.connect(self._on_hls_error)
        self.hls_player.mediaStatusChanged.connect(self._on_hls_status)
        self.hls_player.playbackStateChanged.connect(self._on_hls_state)
        self.hls_video_widget.videoSink().videoSizeChanged.connect(self.setup_layout)

        # Timers
        self.slideshow_timer = QTimer(self)
        self.slideshow_timer.timeout.connect(self.next_image)
        self.clock_timer = QTimer(self)
        self.clock_timer.timeout.connect(self.update_clock)
        self.clock_timer.start(1000)

        # Timer to poll mpv process state.  In some environments mpv may not
        # terminate cleanly on EOF even with --keep-open=no.  This timer
        # periodically checks whether the spawned mpv process has exited and
        # advances to the next file when appropriate.  It is started on video
        # playback and stopped once the process ends.
        self.mpv_poll_timer = QTimer(self)
        self.mpv_poll_timer.setInterval(1000)  # check once per second
        self.mpv_poll_timer.timeout.connect(self._check_mpv_process)

        self.stream_loading_timer = QTimer(self)
        self.stream_loading_timer.setSingleShot(True)
        self.stream_loading_timer.setInterval(30000)
        self.stream_loading_timer.timeout.connect(self._on_stream_timeout)

        # Construct children before showing, so their initial geometry follows
        # the fullscreen central widget instead of Qt's 100x30 defaults.
        self.showFullScreen()

        # Load config and start
        self.cfg = load_config()
        self.reload_settings()
        self.next_image(force=True)
        QTimer.singleShot(1000, self.setup_layout)

    def setup_layout(self):
        if not self.isVisible():
            return
        if self.assigned_screen:
            self.setGeometry(self.assigned_screen.geometry())
        else:
            screen = self.screen()
            if screen:
                self.setGeometry(screen.geometry())
        rect = self.presentation_rect()
        margin = max(0, min(10, rect.width() // 10, rect.height() // 10))
        self.bg_label.setGeometry(rect)
        self.foreground_label.setGeometry(rect)
        if self.web_view.isVisible():
            self.web_view.setGeometry(rect)
            self.web_view.lower()
        if self.hls_video_widget.isVisible():
            self._layout_hls_video(rect)
            self.hls_video_widget.lower()
        self.bg_label.lower()

        self._correct_label_font(self.spotify_info_label, self.disp_cfg.get("spotify_font_size", 18), rect)
        self._correct_label_font(self.clock_label, getattr(self, "overlay_config", {}).get("clock_font_size", 26), rect)
        info_rect = QRect(rect)
        if self.spotify_progress_bar.isVisible() and rect.height() > 40:
            progress_position = self.disp_cfg.get("spotify_progress_position", "bottom-center")
            if progress_position in ("above_info", "top-center"):
                info_rect.adjust(0, 15, 0, 0)
            else:
                info_rect.adjust(0, 0, 0, -15)
        self._place_overlay_label(self.spotify_info_label, self.disp_cfg.get("spotify_info_position", "bottom-center"), info_rect, full_width=True)
        self._position_spotify_progress_bar(rect, margin)
        if hasattr(self, "overlay_config") and self.clock_label.isVisible():
            self._place_overlay_label(self.clock_label, self.overlay_config.get("clock_position", "bottom-center"), rect)

    def presentation_rect(self):
        rect = self.main_widget.rect()
        x, y, width, height = safe_bounds(rect.width(), rect.height(), self.disp_cfg.get("safe_area", {}))
        return QRect(x, y, width, height)

    def _correct_label_font(self, label, requested, rect):
        font = QFont(label.font())
        font.setPixelSize(bounded_int(requested, 18, 8, max(8, min(512, rect.height() // 4))))
        font.setStretch(text_stretch(self.physical_pixel_aspect()))
        label.setFont(font)
        if label is self.clock_label:
            natural = label.fontMetrics().horizontalAdvance(label.text())
            available = max(1, rect.width() - 20)
            if natural > available:
                font.setPixelSize(max(8, int(font.pixelSize() * available / natural)))
                label.setFont(font)

    def _layout_hls_video(self, rect):
        size = self.hls_video_widget.videoSink().videoSize()
        if size.width() <= 0 or size.height() <= 0:
            self.hls_video_widget.setAspectRatioMode(Qt.KeepAspectRatio)
            self.hls_video_widget.setGeometry(rect)
            return
        width, height = self.calc_fill_size(size.width(), size.height(), rect.width(), rect.height())
        self.hls_video_widget.setAspectRatioMode(Qt.IgnoreAspectRatio)
        self.hls_video_widget.setGeometry(rect.x() + (rect.width() - width) // 2,
                                          rect.y() + (rect.height() - height) // 2,
                                          width, height)

    def _position_spotify_progress_bar(self, rect, margin) -> None:
        if not self.spotify_progress_bar.isVisible():
            return
        ppos = self.disp_cfg.get("spotify_progress_position", "bottom-center")
        height = min(10, max(1, rect.height() - 2 * margin))
        x = rect.x() + margin
        width = max(1, rect.width() - 2 * margin)
        if ppos == "above_info":
            y = self.spotify_info_label.y() - height - 5
        elif ppos == "below_info":
            y = self.spotify_info_label.y() + self.spotify_info_label.height() + 5
        elif ppos == "top-center":
            y = rect.y() + margin
        else:
            y = rect.y() + rect.height() - height - margin
        y = max(rect.y() + margin, min(rect.y() + rect.height() - height - margin, y))
        self.spotify_progress_bar.setGeometry(x, y, width, height)
        self.spotify_progress_bar.raise_()

    def _check_mpv_process(self) -> None:
        proc = self.current_video_proc
        if proc is None:
            return
        try:
            code = proc.poll()
        except OSError:
            code = -1
        if code is None:
            return
        self.stop_current_video()
        if self.current_mode == "videos":
            self.next_image()
        elif self.current_mode == "web_page" and self.stream_source:
            self.stream_loading_timer.stop()
            if code == 0 and (self.stream_metadata.content_type or "").lower() != "live" and not self.stream_live:
                self._show_stream_status("Playback ended.")
            else:
                self._retry_stream()

    def play_next_video(self):
        # Stop any currently running video
        if self.current_video_proc:
            self.stop_current_video()

        # (NEW) Rebuild the list of videos on demand.  This ensures that if the
        # list was emptied or a new category is selected, we always have the
        # latest set of video filenames before attempting to play the next one.
        if not self.image_list:
            self.build_local_image_list()

        # (NEW) If there are still no videos after rebuilding, show a message
        # and return instead of advancing to a non-existent video.
        if not self.image_list:
            self.clear_foreground_label("No videos found")
            return
        path = self.image_list[self.index]
        self.last_displayed_path = path
        if not shutil.which("mpv"):
            self.clear_foreground_label("Video unsupported")
            QTimer.singleShot(2000, self.next_image)
            return
        cmd = self.build_mpv_command(path)
        try:
            proc = subprocess.Popen(cmd)
            self.current_video_proc = proc
        except Exception as e:
            log_message(f"mpv playback error: {e}")
            self.clear_foreground_label("mpv playback error")
            QTimer.singleShot(2000, self.next_image)
            return

        # GUI timer polling avoids callbacks from a dead worker event loop,
        # and an old process can never stop a newer video.
        self.mpv_poll_timer.start()

        self.index += 1
        if self.index >= len(self.image_list):
            self.index = 0

        # If "video_play_to_end" is false, schedule a timeout to stop playback
        # after a maximum number of seconds.  Otherwise rely on mpv's natural
        # termination and our polling timer to detect end-of-file.
        if not self.disp_cfg.get("video_play_to_end", True):
            max_sec = int(self.disp_cfg.get("video_max_seconds", 120))
            QTimer.singleShot(max_sec * 1000, lambda: self.stop_current_video(advance=True) if self.current_video_proc is proc else None)
        else:
            # Start polling mpv's process state.  This is a fallback in case
            # mpv does not emit an EOF exit event; the timer will be stopped
            # automatically once the process has ended.
            try:
                self.mpv_poll_timer.stop()
                self.mpv_poll_timer.start()
            except Exception:
                pass

    def build_mpv_command(self, fullpath):
        cmd = [
            "mpv",
            # Do not load any user/system configuration files.  User configs
            # might set options like --idle=yes or --keep-open that would
            # prevent mpv from exiting on EOF and cause the slideshow to
            # become stuck on a black screen【342559845937801†L2229-L2234】.
            "--no-config",
            "--fs",
            "--no-osd-bar",
            "--really-quiet",
            # Explicitly disable idle mode so mpv terminates when there is no
            # file to play.  Without this, certain configurations can cause
            # mpv to stay open after playback finishes, leading to a black
            # window【342559845937801†L2229-L2234】.
            "--idle=no",
            # Ensure that mpv closes the video window and exits on EOF.  The
            # "no" value resets keep-open even if a config sets it to yes or
            # always【342559845937801†L4768-L4800】.
            "--keep-open=no",
        ]
        screen_index = 0
        try:
            screens = QApplication.screens()
            if self.assigned_screen in screens:
                screen_index = screens.index(self.assigned_screen)
        except Exception:
            pass
        assigned = getattr(self, "assigned_screen", None)
        screen_name = assigned.name() if assigned else ""
        if screen_name:
            cmd += [f"--screen-name={screen_name}", f"--fs-screen-name={screen_name}"]
        else:
            cmd.append(f"--fs-screen={screen_index}")
        aspect = self.disp_cfg.get("display_aspect", "auto")
        if aspect == "auto" and self.disp_name.lower().startswith(("composite", "tv", "vec")):
            aspect = "4:3"
        if aspect in DISPLAY_ASPECTS and aspect != "auto":
            cmd.append(f"--monitoraspect={aspect}")
        cmd += player_presentation_flags(self.disp_cfg)
        if self.disp_cfg.get("video_mute", True):
            cmd += ["--mute=yes", "--volume=0"]
        else:
            vol = int(self.disp_cfg.get("video_volume", 100))
            cmd += ["--mute=no", f"--volume={vol}"]
        cmd += ["--", fullpath]
        return cmd

    def stop_current_video(self, advance: bool = False) -> None:
        """
        Stop the currently running mpv process and optionally advance to the next item.

        This terminates the spawned mpv process (if it is still running), clears
        the `current_video_proc` reference and, when requested via the `advance`
        flag, schedules the next image or video.  We compute the widget geometry
        locally to avoid NameError on undefined variables.
        """
        proc = self.current_video_proc
        if proc and proc.poll() is None:
            try:
                if getattr(self, "stream_process", None) is proc:
                    os.killpg(proc.pid, signal.SIGTERM)
                else:
                    proc.terminate()
                proc.wait(timeout=3)
            except Exception:
                try:
                    if getattr(self, "stream_process", None) is proc:
                        os.killpg(proc.pid, signal.SIGKILL)
                    else:
                        proc.kill()
                except Exception:
                    pass
        self.current_video_proc = None
        self.stream_process = None

        # Stop polling timer if it is running.  Once the process is terminated
        # there is no need to continue polling.
        try:
            self.mpv_poll_timer.stop()
        except Exception:
            pass

        if advance:
            QTimer.singleShot(0, self.next_image)

        # Compute rect and margin locally
        rect = self.main_widget.rect()
        margin = 10

        # Reposition the Spotify progress bar, if visible
        if self.spotify_progress_bar.isVisible():
            rect = self.presentation_rect()
        self._position_spotify_progress_bar(rect, margin)

    def _stop_hls_playback(self) -> None:
        """Stop and hide the dedicated HLS player."""
        self._hls_active = False
        try:
            self.hls_player.stop()
        except Exception:
            pass
        self.hls_video_widget.hide()

    def _play_hls_stream(self, url: str) -> None:
        """Play an HLS stream using the Qt multimedia stack."""
        if not url:
            self._stop_hls_playback()
            return
        self.web_view.hide()
        self.hls_video_widget.show()
        self._hls_active = True
        self.stream_loading_timer.start()
        self.hls_player.setSource(QUrl(url))
        self.hls_audio_output.setMuted(self.disp_cfg.get("youtube_mute", True))
        self.hls_audio_output.setVolume(bounded_int(self.disp_cfg.get("video_volume", 100), 100, 0, 100) / 100)
        if self.disp_cfg.get("youtube_autoplay", True):
            self.hls_player.play()
        else:
            self.hls_player.pause()

    def _play_mpv_stream(self, url: str) -> bool:
        if not url or not shutil.which("mpv"):
            return False
        self._stop_hls_playback()
        self.web_view.hide()
        self.stop_current_video()
        cmd = self.build_mpv_command(url)
        youtube = parse_youtube_url_details(url)["is_youtube"]
        height = self.assigned_screen.geometry().height() if self.assigned_screen else None
        extra = stream_flags(self.disp_cfg, youtube, height, self.stream_metadata.start_seconds)
        cmd = cmd[:-2] + extra + cmd[-2:]
        try:
            proc = subprocess.Popen(cmd, env=playback_environment(), stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL, text=True, bufsize=1, start_new_session=True)
        except OSError:
            log_message("Stream player could not start.")
            return False
        self.current_video_proc = proc
        self.stream_process = proc
        generation = self.stream_generation
        emit = self.stream_event.emit
        self._stream_started = False
        self.stream_loading_timer.start()
        self.mpv_poll_timer.start()

        def read_events():
            try:
                for line in proc.stdout:
                    event = parse_player_event(line)
                    if event:
                        emit(generation, event)
            except (OSError, RuntimeError, ValueError):
                pass
            finally:
                proc.stdout.close()
        threading.Thread(target=read_events, daemon=True).start()
        return True

    def _cancel_stream(self):
        self.stream_generation += 1
        self.stream_source = None
        self.stream_metadata = None
        self._hls_active = False
        self.stream_loading_timer.stop()

    def _start_web_playback(self, raw_url, metadata):
        metadata = metadata or classify_url(raw_url)
        self.stream_source = metadata.original_url or raw_url
        self.stream_metadata = metadata
        self.stream_retry = RetryPolicy()
        self.stream_live = metadata.content_type == "live"
        if self._maybe_launch_external_browser(self.stream_source, metadata):
            return
        self._start_stream_attempt(self.stream_generation)

    def _start_stream_attempt(self, generation):
        if not self.running or self.current_mode != "web_page" or generation != self.stream_generation:
            return
        metadata = self.stream_metadata
        if metadata.embed_type in ("youtube", "hls", "mpv"):
            self._show_stream_status("Loading stream…")
        if metadata.embed_type == "youtube":
            if stream_capabilities(probe_runtime=False)["ready"] and self._play_mpv_stream(self.stream_source):
                return
            log_message("YouTube extraction unavailable; using the embedded player. Check streaming capabilities.")
            self._fallback_stream()
        elif metadata.embed_type == "hls":
            self._play_hls_stream(self.stream_source)
        elif metadata.embed_type == "mpv":
            if not self._play_mpv_stream(self.stream_source):
                self._fallback_stream()
        else:
            self._load_web_url(self.stream_source)

    def _show_stream_status(self, message):
        self._stop_hls_playback()
        self.web_view.hide()
        self.bg_label.clear()
        self.clear_foreground_label(message)

    def _retry_stream(self):
        if not self.running or self.current_mode != "web_page" or not self.stream_source:
            return
        self.stream_loading_timer.stop()
        self._stop_hls_playback()
        self.stop_current_video()
        delay = self.stream_retry.next_delay()
        self.stream_generation += 1  # Invalidates old process events and retries.
        if delay is None:
            self._fallback_stream()
            return
        generation = self.stream_generation
        self._show_stream_status("Stream interrupted; retrying…")
        QTimer.singleShot(delay, lambda: self._start_stream_attempt(generation))

    def _fallback_stream(self):
        self.stream_loading_timer.stop()
        if self.stream_metadata and self.stream_metadata.embed_type == "youtube":
            self._load_youtube_embed(self.stream_metadata)
        else:
            self._show_stream_status("Stream unavailable. Check the connection or refresh the source URL.")

    @Slot(int, str)
    def _on_stream_event(self, generation, event):
        if self.running and self.current_mode == "web_page" and generation == self.stream_generation and event in ("playing", "playing_live"):
            self.stream_live = self.stream_live or event == "playing_live"
            self._stream_started = True
            self.stream_retry.mark_started()
            self.stream_loading_timer.stop()

    def _on_stream_timeout(self):
        self._retry_stream()

    def _on_hls_error(self, *args):
        if self._hls_active:
            self._retry_stream()

    def _on_hls_status(self, status):
        if not self._hls_active:
            return
        if status == QMediaPlayer.MediaStatus.EndOfMedia:
            self.stream_loading_timer.stop()
            if self.hls_player.duration() <= 0:
                self._retry_stream()
            else:
                self._show_stream_status("Playback ended.")
        elif status in (QMediaPlayer.MediaStatus.StalledMedia, QMediaPlayer.MediaStatus.LoadingMedia, QMediaPlayer.MediaStatus.BufferingMedia):
            if not self.stream_loading_timer.isActive():
                self.stream_loading_timer.start()
        elif status in (QMediaPlayer.MediaStatus.LoadedMedia, QMediaPlayer.MediaStatus.BufferedMedia):
            self.stream_loading_timer.stop()

    def _on_hls_state(self, state):
        if self._hls_active and state == QMediaPlayer.PlaybackState.PlayingState:
            self.stream_retry.mark_started()
            self.stream_loading_timer.stop()

    def _on_web_load_finished(self, ok):
        if not ok and self.running and getattr(self, "current_mode", None) == "web_page" and not self.external_browser_proc:
            self._show_stream_status("Page failed to load. Check the URL or select the external browser.")

    def _stop_external_browser(self) -> None:
        proc = self.external_browser_proc
        if not proc:
            return
        if proc.poll() is None:
            try:
                os.killpg(proc.pid, signal.SIGTERM)
                proc.wait(timeout=3)
            except Exception:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except Exception:
                    pass
        self.external_browser_proc = None
        self.external_browser_url = None
        self.external_browser_log_thread = None

    def _find_chromium_binary(self) -> Optional[str]:
        env_bin = os.environ.get("CHROMIUM_BIN")
        if env_bin:
            path = shutil.which(env_bin)
            if path:
                return path
        direct_binary = "/usr/lib/chromium/chromium"
        if os.path.exists(direct_binary) and os.access(direct_binary, os.X_OK):
            return direct_binary
        for candidate in ("chromium", "chromium-browser"):
            path = shutil.which(candidate)
            if path:
                return path
        return None

    def _chromium_user_data_dir(self) -> str:
        parts = [self.disp_name]
        screen = self.assigned_screen or self.screen()
        if screen and hasattr(screen, "name"):
            try:
                parts.append(screen.name())
            except Exception:
                pass
        raw = "-".join([p for p in parts if p])
        safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", raw)
        if not safe:
            safe = f"display-{abs(id(self))}"
        config_home = os.environ.get("XDG_CONFIG_HOME", os.path.expanduser("~/.config"))
        base_dir = os.environ.get(
            "ECHOVIEW_CHROMIUM_CONFIG_DIR",
            os.path.join(config_home, "echoview"),
        )
        return os.path.join(base_dir, f"chromium-{safe}")

    def _chromium_window_flags(self) -> List[str]:
        screen = self.assigned_screen or self.screen()
        if not screen:
            return []
        geom = screen.geometry()
        if geom.width() <= 0 or geom.height() <= 0:
            return []
        x, y, width, height = safe_bounds(geom.width(), geom.height(), self.disp_cfg.get("safe_area", {}))
        return [f"--window-position={geom.x() + x},{geom.y() + y}",
                f"--window-size={width},{height}"]

    def _build_chromium_command(self, url: str) -> Optional[List[str]]:
        binary = self._find_chromium_binary()
        if not binary:
            return None
        user_dir = self._chromium_user_data_dir()
        os.makedirs(user_dir, exist_ok=True)
        cmd = [
            binary,
            "--kiosk",
            "--new-window",
            "--no-first-run",
            "--no-default-browser-check",
            "--autoplay-policy=no-user-gesture-required",
            f"--user-data-dir={user_dir}",
        ]
        cmd += chromium_flags()
        cmd += self._chromium_window_flags()
        cmd.append(url)
        return cmd

    def _ensure_external_browser(self, url: str) -> bool:
        if (
            self.external_browser_proc
            and self.external_browser_proc.poll() is None
            and self.external_browser_url == url
        ):
            return True
        self._stop_external_browser()
        cmd = self._build_chromium_command(url)
        if not cmd:
            log_message("Chromium not found; falling back to Qt WebEngine.")
            return False
        env = os.environ.copy()
        try:
            proc = subprocess.Popen(
                cmd,
                env=env,
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
            )
        except Exception as exc:
            log_message("Chromium failed to launch.")
            self._show_external_browser_error("Chromium failed to start.")
            return False
        self.external_browser_proc = proc
        self.external_browser_url = url
        self._start_external_browser_log_thread(proc)
        self.foreground_label.setText("")
        QTimer.singleShot(800, lambda: self._check_external_browser_start(url))
        return True

    def _maybe_launch_external_browser(self, raw_url: str, metadata: Optional[EmbedMetadata]) -> bool:
        if not self.disp_cfg.get("web_use_external_browser", False):
            self._stop_external_browser()
            return False
        target = raw_url or (metadata.original_url if metadata else "")
        if not target:
            return False
        self._stop_hls_playback()
        self.web_view.hide()
        self.stop_current_video()
        return self._ensure_external_browser(target)

    def _start_external_browser_log_thread(self, proc: subprocess.Popen) -> None:
        if not proc.stderr:
            return

        def worker():
            try:
                for raw in iter(proc.stderr.readline, b""):
                    line = raw.decode(errors="replace").strip()
                    # Drain diagnostics without logging URLs/cookies from pages.
                    if line:
                        pass
            except Exception:
                pass

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        self.external_browser_log_thread = thread

    def _check_external_browser_start(self, url: str) -> None:
        proc = self.external_browser_proc
        if not proc or self.external_browser_url != url:
            return
        if proc.poll() is None:
            return
        log_message(f"Chromium exited early (code={proc.returncode}).")
        self._stop_external_browser()
        self._show_external_browser_error("Chromium failed to start.")

    def _show_external_browser_error(self, message: str) -> None:
        self._stop_hls_playback()
        self.web_view.hide()
        self.stop_current_video()
        self.foreground_label.setText(message)
        self.foreground_label.setAlignment(Qt.AlignCenter)
        font = self.foreground_label.font()
        screen = self.assigned_screen if self.assigned_screen else self.screen()
        height = screen.size().height() if screen else 800
        font.setPointSize(max(24, int(height / 20)))
        font.setStretch(text_stretch(self.physical_pixel_aspect()))
        self.foreground_label.setFont(font)
        self.foreground_label.setStyleSheet("color: white; background-color: black;")
        self.foreground_label.raise_()

    def _load_web_url(self, url: str) -> None:
        """Load a URL (or placeholder) into the embedded browser."""
        self._stop_hls_playback()
        self.foreground_label.clear()
        if url:
            self.web_view.load(QUrl(url))
        else:
            placeholder = (
                "<html><body style='background:#000;color:#fff;"
                "display:flex;align-items:center;justify-content:center;"
                "font-family:sans-serif;'>No URL configured.</body></html>"
            )
            self.web_view.setHtml(placeholder, QUrl("https://echoview.local/placeholder"))
        self.web_view.show()

    def _load_youtube_embed(self, metadata: EmbedMetadata) -> None:
        """Render a YouTube embed using an iframe wrapper with autoplay allowances."""
        self._stop_hls_playback()
        if not (metadata.video_id or metadata.channel_id or metadata.playlist_id):
            self._show_stream_status("Stream unavailable. Select the external browser for this channel URL.")
            return
        # Serve a real HTTP document so the iframe has an actual Referer origin.
        url = controller_origin() + "/player/youtube?" + urlencode({"display": self.disp_name})
        self.foreground_label.clear()
        self.web_view.load(QUrl(url))
        self.web_view.show()
        self.setup_layout()

    def _build_youtube_embed_url(self, metadata: EmbedMetadata) -> str:
        """
        Apply user preferences (autoplay, mute, captions, quality) to the
        canonical YouTube embed URL derived during detection.
        """
        return playback_embed_url(metadata, self.disp_cfg, controller_origin())

    def _place_overlay_label(self, lbl, position: str, container_rect, y_offset: int = 0, full_width: bool = False) -> int:
        margin = min(10, container_rect.width() // 10, container_rect.height() // 10)
        lbl.setWordWrap(True)
        max_width = container_rect.width() - 2 * margin
        width = max(1, max_width if full_width else min(lbl.sizeHint().width(), max_width))
        lbl.setFixedWidth(width)
        height = lbl.heightForWidth(width)
        if height < 0:
            height = lbl.sizeHint().height()
        bounds = overlay_bounds((container_rect.x(), container_rect.y(), container_rect.width(), container_rect.height()),
                                (width, height), position, margin, y_offset)
        align = Qt.AlignLeft if "left" in position else (Qt.AlignRight if "right" in position else Qt.AlignHCenter)
        lbl.setAlignment(align | Qt.AlignVCenter)
        lbl.setFixedSize(bounds[2], bounds[3])
        lbl.move(bounds[0], bounds[1])
        lbl.raise_()
        return bounds[1] + bounds[3] + margin

    def resizeEvent(self, event):
        super().resizeEvent(event)
        # A fullscreen resize can occur before child widgets are constructed.
        if hasattr(self, "main_widget") and hasattr(self, "spotify_info_label"):
            self.setup_layout()
            if getattr(self, "current_mode", None) == "calibration":
                self.show_calibration_pattern()
            elif getattr(self, "current_pixmap", None):
                self.updateForegroundScaled()
            elif getattr(self, "current_movie", None) and not self.handling_gif_frames:
                iw, ih = self.gif_source_size
                width, height = self.calc_fill_size(iw, ih, self.foreground_label.width(), self.foreground_label.height())
                self.current_movie.setScaledSize(QSize(width, height))

    def closeEvent(self, event):
        self.running = False
        self._cancel_stream()
        self.spotify_fetch_id += 1
        self.slideshow_timer.stop()
        self.spotify_progress_timer.stop()
        self._stop_external_browser()
        self._stop_hls_playback()
        self.stop_current_video()
        super().closeEvent(event)

    @Slot()
    def reload_settings(self):
        self._cancel_stream()
        self.spotify_fetch_id += 1
        self.spotify_info = None
        self.spotify_art_path = None
        self.spotify_fallback_due = 0
        self.stop_current_video()
        self.cfg = load_config()
        displays = self.cfg.get("displays", {})
        if self.disp_name in displays:
            self.disp_cfg = runtime_display_settings(self.cfg, displays[self.disp_name])

        over = self.disp_cfg.get("overlay", self.cfg.get("overlay", {}))
        if over.get("clock_enabled", False):
            self.clock_label.show()
        else:
            self.clock_label.hide()

        cfsize = bounded_int(over.get("clock_font_size", 24), 24, 8, 512)
        if over.get("auto_negative_font", False):
            self.clock_label.useDifference = True
            self.clock_label.setStyleSheet("background: transparent;")
            font_clock = QFont(self.clock_label.font())
            font_clock.setPixelSize(cfsize)
            self.clock_label.setFont(font_clock)
        else:
            self.clock_label.useDifference = False
            fcolor = over.get("font_color", "#FFFFFF")
            self.clock_label.setStyleSheet(f"color: {fcolor}; background: transparent;")
        self.overlay_config = over

        gui_cfg = self.cfg.get("gui", {})
        self.resource_options = resource_settings(self.disp_cfg.get("resource_profile", "standard"), self.cfg)
        self.bg_blur_radius = self.resource_options["blur_radius"]
        self.bg_scale_percent = bounded_int(gui_cfg.get("background_scale_percent", 100), 100, 1, 100)
        self.fg_scale_percent = bounded_int(gui_cfg.get("foreground_scale_percent", 100), 100, 1, 100)
        self.cache_capacity = self.resource_options["cache_capacity"]
        self.cache_budget = self.resource_options["cache_budget"]
        self.preload_count = self.resource_options["preload_count"]
        with self.cache_lock:
            self.cache_generation += 1
            self.image_cache.clear()
            self.cache_bytes = 0

        self.current_mode = self.disp_cfg.get("mode", "random_image")
        if self.current_mode != "web_page":
            self._stop_external_browser()
        interval_s = self.disp_cfg.get("image_interval", 60)
        if self.current_mode == "spotify":
            interval_s = 5

        # Reset cached lists and indexes before rebuilding state.
        self.image_list = []
        self.fallback_image_list = []
        self.fallback_index = -1
        # Use -1 so the first next_image call shows the first item instead of skipping it.
        self.index = -1 if self.current_mode != "videos" else 0
        self.last_displayed_path = None

        if self.current_mode in ("random_image", "mixed", "specific_image", "videos"):
            self.build_local_image_list()

        # Stop any existing playback/embeds before reconfiguring.
        self._stop_hls_playback()
        self.web_view.hide()
        self.spotify_progress_bar.hide()
        self.spotify_progress_timer.stop()

        if self.current_mode == "spotify":
            if self.disp_cfg.get("spotify_show_progress", False):
                self.spotify_progress_bar.show()
                upd_int = max(self.resource_options["progress_interval"], bounded_int(self.disp_cfg.get("spotify_progress_update_interval", 200), 200, 50, 5000))
                self.spotify_progress_timer.setInterval(upd_int)
                self.spotify_progress_timer.start()
                theme = self.disp_cfg.get("spotify_progress_theme", "dark")
                if theme == "light":
                    self.spotify_progress_bar.setStyleSheet(
                        "QProgressBar { border: 1px solid #ccc; border-radius: 5px; background-color: #f0f0f0; }"
                        "QProgressBar::chunk { background-color: #a0a0a0; }"
                    )
                elif theme == "dark":
                    self.spotify_progress_bar.setStyleSheet(
                        "QProgressBar { border: 1px solid #444; border-radius: 5px; background-color: #333; }"
                        "QProgressBar::chunk { background-color: #888; }"
                    )
                elif theme == "spotify":
                    self.spotify_progress_bar.setStyleSheet(
                        "QProgressBar { border: 1px solid #1DB954; border-radius: 5px; background-color: #121212; }"
                        "QProgressBar::chunk { background-color: #1DB954; }"
                    )
                elif theme == "coffee":
                    self.spotify_progress_bar.setStyleSheet(
                        "QProgressBar { border: 1px solid #8B4513; border-radius: 5px; background-color: #423828; }"
                        "QProgressBar::chunk { background-color: #8B4513; }"
                    )
                else:
                    self.spotify_progress_bar.setStyleSheet("")
            self.slideshow_timer.setInterval(interval_s * 1000)
            self.slideshow_timer.start()
        elif self.current_mode == "web_page":
            metadata = deserialize_embed_metadata(self.disp_cfg.get("embed_metadata"))
            raw_url = (self.disp_cfg.get("web_url", "") or "").strip()
            self._start_web_playback(raw_url, metadata)
            self.slideshow_timer.stop()
        elif self.current_mode in ("videos", "calibration"):
            self.slideshow_timer.stop()
        else:
            self.slideshow_timer.setInterval(interval_s * 1000)
            self.slideshow_timer.start()

        # Ensure overlay elements are repositioned based on updated settings
        self.setup_layout()

    def build_local_image_list(self):
        mode = self.current_mode
        if mode == "random_image":
            cat = self.disp_cfg.get("image_category", "")
            if is_ignored_folder(cat):
                self.image_list = []
                return
            images = self.gather_images(cat)
            if self.disp_cfg.get("shuffle_mode", False):
                random.shuffle(images)
            self.image_list = self._filter_by_aspect(images)
        elif mode == "mixed":
            folder_list = [
                folder for folder in self.disp_cfg.get("mixed_folders", [])
                if not is_ignored_folder(folder)
            ]
            allimg = []
            for folder in folder_list:
                allimg += self.gather_images(folder)
            if self.disp_cfg.get("shuffle_mode", False):
                random.shuffle(allimg)
            self.image_list = self._filter_by_aspect(allimg)
        elif mode == "specific_image":
            cat = self.disp_cfg.get("image_category", "")
            if is_ignored_folder(cat):
                self.image_list = []
                return
            spec = self.disp_cfg.get("specific_image", "")
            path = os.path.join(IMAGE_DIR, cat, spec)
            if os.path.exists(path):
                self.image_list = [path]
            else:
                log_message(f"Specific image not found: {path}")
                self.image_list = []
            self.image_list = self._filter_by_aspect(self.image_list)
        elif mode == "videos":
            cat = self.disp_cfg.get("video_category", "")
            if is_ignored_folder(cat):
                self.image_list = []
                return
            vids = self.gather_videos(cat)
            if self.disp_cfg.get("shuffle_videos", False):
                random.shuffle(vids)
            self.image_list = self._filter_by_aspect(vids)

    def gather_images(self, category):
        base = os.path.join(IMAGE_DIR, category) if category else IMAGE_DIR
        if is_ignored_folder(base) or is_ignored_folder(category):
            return []
        if not os.path.isdir(base):
            return []
        results = []
        for fname in os.listdir(base):
            lf = fname.lower()
            if lf.endswith((".jpg", ".jpeg", ".png", ".gif")):
                results.append(os.path.join(base, fname))
        results.sort()
        return results

    def gather_videos(self, category):
        base = os.path.join(IMAGE_DIR, category) if category else IMAGE_DIR
        if is_ignored_folder(base) or is_ignored_folder(category):
            return []
        if not os.path.isdir(base):
            return []
        results = []
        for fname in os.listdir(base):
            lf = fname.lower()
            if lf.endswith((".mp4", ".mov", ".avi", ".mkv", ".webm")):
                results.append(os.path.join(base, fname))
        results.sort()
        return results

    def _filter_by_aspect(self, paths):
        """Filter media by the configured aspect bucket (any/square/landscape/portrait)."""
        target = self.disp_cfg.get("aspect_filter", "any")
        if not paths or target in ("", "any", None):
            return paths
        filtered = []
        for p in paths:
            label = self.aspect_cache.get(p)
            if label is None:
                label = media_aspect_label(p)
                self.aspect_cache[p] = label
            if label == target:
                filtered.append(p)
        return filtered

    def load_and_cache_image(self, fullpath):
        # QImageReader/QImage are safe for preloading; QPixmap stays on the GUI.
        policy = self.resource_options
        reader = QImageReader(fullpath)
        reader.setAutoDetectImageFormat(True)
        reader.setAutoTransform(True)
        size = reader.size()
        width, height = decode_size(size.width(), size.height(), policy)
        if width > 0 and height > 0:
            reader.setScaledSize(QSize(width, height))
        image = reader.read()
        gif = fullpath.lower().endswith(".gif")
        return {"type": "gif" if gif else "static", "path": fullpath,
                "first_frame": image, "image": image, "bytes": int(image.sizeInBytes())}

    def get_cached_image(self, fullpath):
        with self.cache_lock:
            generation = self.cache_generation
            if fullpath in self.image_cache:
                self.image_cache.move_to_end(fullpath)
                return self.image_cache[fullpath]
        data = self.load_and_cache_image(fullpath)
        with self.cache_lock:
            if generation == self.cache_generation and data["bytes"]:
                self.image_cache[fullpath] = data
                self.cache_bytes = trim_image_cache(self.image_cache, self.cache_capacity, self.cache_budget)
        return data

    def prefetch_next_image(self):
        if not self.image_list or self.preload_count <= 0:
            return
        total = len(self.image_list)
        for offset in range(1, self.preload_count + 1):
            next_path = self.image_list[(self.index + offset) % total]
            with self.cache_lock:
                if next_path in self.prefetch_pending or len(self.prefetch_pending) >= self.preload_count:
                    continue
                self.prefetch_pending.add(next_path)

            def worker(path=next_path):
                try:
                    self.get_cached_image(path)
                except Exception:
                    pass
                finally:
                    with self.cache_lock:
                        self.prefetch_pending.discard(path)

            threading.Thread(target=worker, daemon=True).start()

    def make_background(self, pixmap):
        """Generate a blurred/scaled background from the given pixmap."""
        return self.make_background_cover(pixmap)

    def next_image(self, force=False):
        if not self.running:
            return

        if self.current_mode == "web_page":
            return
        if self.current_mode == "calibration":
            self.show_calibration_pattern()
            return

        if self.current_mode == "videos":
            self.play_next_video()
            return

        if self.current_mode == "spotify":
            self.start_spotify_fetch()
            return

        if not self.image_list:
            self.clear_foreground_label("No images found")
            return

        if force and self.index < 0:
            self.index = 0
        else:
            self.index = (self.index + 1) % len(self.image_list)
        new_path = self.image_list[self.index]
        self.last_displayed_path = new_path

        self.show_foreground_image(new_path)
        self.prefetch_next_image()
        if self.overlay_config.get("auto_negative_font", False):
            self.clock_label.update()

    def clear_foreground_label(self, message):
        self.current_pixmap = None
        self.current_drawn_image = None
        self.stop_current_video()
        if self.current_movie:
            try:
                self.current_movie.stop()
            except RuntimeError:
                pass
            try:
                self.current_movie.deleteLater()
            except RuntimeError:
                pass
            self.current_movie = None
            self.handling_gif_frames = False
        self.foreground_label.setMovie(None)
        msg = message
        lower_msg = message.lower()
        if "no" in lower_msg and "found" in lower_msg:
            ip = get_ip_address()
            port = os.environ.get("WEB_PORT", "8080")
            msg = f"{message}\nSetup at {ip}:{port}"
        self.foreground_label.setText(msg)
        self.foreground_label.setAlignment(Qt.AlignCenter)
        font = self.foreground_label.font()
        screen = self.assigned_screen if self.assigned_screen else self.screen()
        if screen:
            height = screen.size().height()
        else:
            height = 800
        font.setPointSize(max(24, int(height / 20)))
        font.setStretch(text_stretch(self.physical_pixel_aspect()))
        self.foreground_label.setFont(font)
        self.foreground_label.setStyleSheet("color: white; background-color: transparent;")
        self.spotify_progress_bar.hide()
        self.spotify_progress_timer.stop()

    def show_foreground_image(self, fullpath, is_spotify=False):
        if not os.path.exists(fullpath):
            self.clear_foreground_label("Missing file")
            return

        if self.current_movie:
            try:
                self.current_movie.stop()
            except RuntimeError:
                pass
            try:
                self.current_movie.deleteLater()
            except RuntimeError:
                pass
            self.current_movie = None
            self.handling_gif_frames = False

        data = self.get_cached_image(fullpath)
        if data["image"].isNull():
            self.clear_foreground_label("Image could not be decoded")
            return
        if data["type"] == "gif" and not is_spotify:
            self.current_pixmap = None
            if self.fg_scale_percent == 100 and not self.disp_cfg.get("rotate", 0):
                self.current_movie = QMovie(data["path"])
                ff = data["first_frame"]
                self.gif_source_size = (ff.width(), ff.height())
                bw, bh = self.calc_bounding_for_window(ff)
                if bw > 0 and bh > 0:
                    self.current_movie.setScaledSize(QSize(bw, bh))
                self.foreground_label.setMovie(self.current_movie)
                self.current_movie.start()
                self.handling_gif_frames = False
                if not ff.isNull():
                    pm = QPixmap.fromImage(ff)
                    blurred = self.make_background(pm)
                    self.bg_label.setPixmap(blurred if blurred else QPixmap())
            else:
                self.current_movie = QMovie(data["path"])
                self.handling_gif_frames = True
                ff = data["first_frame"]
                if ff.isNull():
                    self.clear_foreground_label("GIF error")
                    return
                pm = QPixmap.fromImage(ff)
                blurred = self.make_background(pm)
                self.bg_label.setPixmap(blurred if blurred else QPixmap())
                bw, bh = self.calc_bounding_for_window(ff)
                self.gif_bounds = (bw, bh)
                self.current_movie.frameChanged.connect(self.on_gif_frame_changed)
                self.current_movie.start()
        else:
            if data["type"] == "static":
                self.current_pixmap = QPixmap.fromImage(data["image"])
            else:
                self.current_pixmap = QPixmap(fullpath)
            self.handling_gif_frames = False
            self.updateForegroundScaled()
            blurred = self.make_background(self.current_pixmap)
            self.bg_label.setPixmap(blurred if blurred else QPixmap())
        self.spotify_info_label.raise_()

    def on_gif_frame_changed(self, frame_index):
        if not self.current_movie or not self.handling_gif_frames:
            return
        frm_img = self.current_movie.currentImage()
        if frm_img.isNull():
            return
        src_pm = self.apply_rotation_if_any(QPixmap.fromImage(frm_img))
        bounds = self.calc_fill_size(src_pm.width(), src_pm.height(), self.foreground_label.width(), self.foreground_label.height())
        rotated = self.degrade_foreground(src_pm, bounds)
        fw = self.foreground_label.width()
        fh = self.foreground_label.height()
        bw, bh = bounds
        final_img = QImage(fw, fh, QImage.Format_ARGB32)
        final_img.fill(Qt.transparent)
        painter = QPainter(final_img)
        xoff = (fw - bw) // 2
        yoff = (fh - bh) // 2
        painter.drawPixmap(xoff, yoff, rotated)
        painter.end()
        self.foreground_label.setPixmap(QPixmap.fromImage(final_img))
        self.last_scaled_foreground_image = final_img
        if self.overlay_config.get("auto_negative_font", False):
            self.clock_label.update()
        self.spotify_info_label.raise_()

    def calc_bounding_for_window(self, first_frame):
        fw = self.foreground_label.width()
        fh = self.foreground_label.height()
        if fw < 1 or fh < 1:
            return (fw, fh)
        rotated = self.apply_rotation_if_any(QPixmap.fromImage(first_frame))
        iw = rotated.width()
        ih = rotated.height()
        if iw < 1 or ih < 1:
            return (fw, fh)
        return self.calc_fill_size(iw, ih, fw, fh)

    def updateForegroundScaled(self):
        if not self.current_pixmap:
            return
        fw = self.foreground_label.width()
        fh = self.foreground_label.height()
        if fw < 1 or fh < 1:
            return
        source = self.apply_rotation_if_any(self.current_pixmap)
        iw = source.width()
        ih = source.height()
        if iw < 1 or ih < 1:
            return
        bw, bh = self.calc_fill_size(iw, ih, fw, fh)
        rotated = self.degrade_foreground(source, (bw, bh))
        self.current_drawn_image = rotated.toImage()
        final_img = QImage(fw, fh, QImage.Format_ARGB32)
        final_img.fill(Qt.transparent)
        painter = QPainter(final_img)
        rw = rotated.width()
        rh = rotated.height()
        xoff = (fw - rw) // 2
        yoff = (fh - rh) // 2
        painter.drawPixmap(xoff, yoff, rotated)
        painter.end()
        self.foreground_drawn_rect = QRect(xoff, yoff, rw, rh)
        self.foreground_label.setPixmap(QPixmap.fromImage(final_img))
        self.last_scaled_foreground_image = final_img
        if self.overlay_config.get("auto_negative_font", False):
            self.clock_label.update()

    def physical_pixel_aspect(self):
        screen = self.assigned_screen
        if screen:
            geometry = screen.geometry()
            width, height = geometry.width(), geometry.height()
        else:
            width, height = self.width(), self.height()
        return display_pixel_aspect(self.disp_cfg.get("display_aspect", "auto"),
                                    width, height, self.disp_name)

    def calc_fill_size(self, iw, ih, fw, fh):
        return fit_dimensions(iw, ih, fw, fh, self.physical_pixel_aspect())

    def degrade_foreground(self, src_pm, bounding):
        bw, bh = bounding
        if bw < 1 or bh < 1:
            return src_pm
        scaled = src_pm.scaled(bw, bh, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        if self.fg_scale_percent >= 100:
            return scaled
        sf = float(self.fg_scale_percent) / 100.0
        down_w = int(bw * sf)
        down_h = int(bh * sf)
        if down_w < 1 or down_h < 1:
            return scaled
        smaller = scaled.scaled(down_w, down_h, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        final_pm = smaller.scaled(bw, bh, Qt.IgnoreAspectRatio, Qt.FastTransformation)
        return final_pm

    def apply_rotation_if_any(self, pixmap):
        deg = self.disp_cfg.get("rotate", 0)
        if deg == 0:
            return pixmap
        transform = QTransform()
        transform.rotate(deg)
        return pixmap.transformed(transform, Qt.SmoothTransformation)

    def make_background_cover(self, pixmap):
        rect = self.presentation_rect()
        sw, sh = rect.width(), rect.height()
        pw, ph = pixmap.width(), pixmap.height()
        if sw < 1 or sh < 1 or pw < 1 or ph < 1:
            return None
        screen_ratio = float(sw) / float(sh)
        img_ratio = float(pw) / float(ph) / self.physical_pixel_aspect()
        tmode = Qt.FastTransformation
        if img_ratio > screen_ratio:
            new_h = sh
            new_w = int(new_h * img_ratio)
        else:
            new_w = sw
            new_h = int(new_w / img_ratio)
        scaled = pixmap.scaled(new_w, new_h, Qt.IgnoreAspectRatio, tmode)
        xoff = (scaled.width() - sw) // 2
        yoff = (scaled.height() - sh) // 2
        final_cover = scaled.copy(xoff, yoff, sw, sh)
        if self.bg_scale_percent < 100:
            sf = float(self.bg_scale_percent) / 100.0
            down_w = int(sw * sf)
            down_h = int(sh * sf)
            if down_w > 0 and down_h > 0:
                temp_down = final_cover.scaled(down_w, down_h, Qt.IgnoreAspectRatio, tmode)
                blurred = self.blur_pixmap_once(temp_down, self.bg_blur_radius)
                if blurred:
                    final_bg = blurred.scaled(sw, sh, Qt.IgnoreAspectRatio, tmode)
                else:
                    final_bg = temp_down.scaled(sw, sh, Qt.IgnoreAspectRatio, tmode)
            else:
                final_bg = self.blur_pixmap_once(final_cover, self.bg_blur_radius)
        else:
            final_bg = self.blur_pixmap_once(final_cover, self.bg_blur_radius)
        return final_bg

    def blur_pixmap_once(self, pm, radius):
        if radius <= 0:
            return pm
        scene = QGraphicsScene()
        item = QGraphicsPixmapItem(pm)
        blur = QGraphicsBlurEffect()
        blur.setBlurRadius(radius)
        blur.setBlurHints(QGraphicsBlurEffect.PerformanceHint)
        item.setGraphicsEffect(blur)
        scene.addItem(item)
        result = QImage(pm.width(), pm.height(), QImage.Format_ARGB32)
        result.fill(Qt.transparent)
        painter = QPainter(result)
        scene.render(painter, QRectF(0, 0, pm.width(), pm.height()),
                     QRectF(0, 0, pm.width(), pm.height()))
        painter.end()
        return QPixmap.fromImage(result)

    def show_calibration_pattern(self):
        rect = self.presentation_rect()
        width = max(1, round(rect.width() * self.physical_pixel_aspect()))
        height = rect.height()
        image = QImage(width, height, QImage.Format_ARGB32)
        image.fill(Qt.black)
        painter = QPainter(image)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.darkGray)
        for column in range(1, 10):
            x = round(width * column / 10)
            painter.drawLine(x, 0, x, height - 1)
        for row in range(1, 10):
            y = round(height * row / 10)
            painter.drawLine(0, y, width - 1, y)
        # Nominal 75% RGB bars: useful through a PAL encoder, with a
        # separate grayscale ramp for monochrome displays and contrast checks.
        from PySide6.QtGui import QColor
        colours = ((191, 191, 191), (191, 191, 0), (0, 191, 191),
                   (0, 191, 0), (191, 0, 191), (191, 0, 0), (0, 0, 191))
        for row, values in ((0.83, colours),
                            (0.90, tuple((v, v, v) for v in (255, 219, 182, 146, 109, 73, 36, 0)))):
            left, right = round(width * 0.10), round(width * 0.90)
            top, bottom = round(height * row), round(height * (row + 0.04))
            for index, rgb in enumerate(values):
                x1 = left + round((right - left) * index / len(values))
                x2 = left + round((right - left) * (index + 1) / len(values))
                painter.fillRect(QRect(x1, top, x2 - x1, max(1, bottom - top)), QColor(*rgb))
        painter.setPen(Qt.white)
        painter.drawRect(1, 1, max(0, width - 3), max(0, height - 3))
        for inset in (0.05, 0.10):
            x, y = round(width * inset), round(height * inset)
            painter.drawRect(x, y, max(0, width - 2 * x - 1), max(0, height - 2 * y - 1))
        diameter = max(1, round(min(width, height) * 0.6))
        painter.setPen(Qt.green)
        painter.drawEllipse((width - diameter) // 2, (height - diameter) // 2, diameter, diameter)
        font = QFont()
        font.setPixelSize(max(8, min(20, height // 28)))
        painter.setFont(font)
        painter.setPen(Qt.white)
        painter.drawText(QRect(0, height // 12, width, height // 8), Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
                         "EchoView calibration: border, 5%, 10% / circle should be round")
        painter.end()
        if self.current_movie:
            self.current_movie.stop()
            self.current_movie = None
        self.spotify_info_label.hide()
        self.spotify_progress_bar.hide()
        self.spotify_progress_timer.stop()
        self.current_pixmap = QPixmap.fromImage(image)
        self.bg_label.clear()
        self.updateForegroundScaled()

    def update_clock(self):
        now_str = datetime.now().strftime("%H:%M:%S")
        self.clock_label.setText(now_str)


    def render_spotify(self, path):
        if self.spotify_info:
            if path and path != getattr(self, "spotify_art_path", None):
                self.show_foreground_image(path, is_spotify=True)
            elif not path:
                self.bg_label.clear()
                self.clear_foreground_label("Artwork unavailable")
            self.spotify_art_path = path
            self.spotify_info_label.show()
            if self.disp_cfg.get("spotify_show_progress", False):
                self.spotify_progress_bar.show()
                upd_int = max(self.resource_options["progress_interval"], bounded_int(self.disp_cfg.get("spotify_progress_update_interval", 200), 200, 50, 5000))
                self.spotify_progress_timer.setInterval(upd_int)
                if not self.spotify_progress_timer.isActive():
                    self.spotify_progress_timer.start()
            info_parts = []
            if self.disp_cfg.get("spotify_show_song", True) and self.spotify_info and self.spotify_info.get("song"):
                info_parts.append(self.spotify_info["song"])
            if self.disp_cfg.get("spotify_show_artist", True) and self.spotify_info and self.spotify_info.get("artist"):
                info_parts.append(self.spotify_info["artist"])
            if self.disp_cfg.get("spotify_show_album", True) and self.spotify_info and self.spotify_info.get("album"):
                info_parts.append(self.spotify_info["album"])

            pos = self.disp_cfg.get("spotify_info_position", "bottom-center")
            if "left" in pos or "right" in pos:
                text = "\n".join(info_parts)
            else:
                text = " | ".join(info_parts)
            self.spotify_info_label.setText(text)
            font_size = self.disp_cfg.get("spotify_font_size", 18)
            if self.disp_cfg.get("spotify_negative_font", True):
                self.spotify_info_label.useDifference = True
                self.spotify_info_label.setStyleSheet("background: transparent;")
                font = QFont(self.spotify_info_label.font())
                font.setPixelSize(font_size)
                self.spotify_info_label.setFont(font)
            else:
                self.spotify_info_label.useDifference = False
                color = self.disp_cfg.get("spotify_font_color", "#FFFFFF")
                self.spotify_info_label.setStyleSheet(
                    f"color: {color}; background: transparent;"
                )
            self.spotify_info_label.raise_()
            # When Spotify is active we want to poll frequently for changes
            if self.slideshow_timer.interval() != 5000:
                self.slideshow_timer.setInterval(5000)
            self.setup_layout()
        else:
            self.spotify_art_path = None
            self.spotify_info_label.setText("")
            self.spotify_info_label.hide()
            self.spotify_progress_bar.hide()
            self.spotify_progress_timer.stop()
            if time.monotonic() < getattr(self, "spotify_fallback_due", 0):
                return
            fallback_mode = self.disp_cfg.get("fallback_mode", "random_image")
            if fallback_mode in ("random_image", "mixed", "specific_image"):
                if not self.fallback_image_list:
                    image_list_backup = self.image_list
                    mode_backup = self.current_mode
                    self.current_mode = fallback_mode
                    self.build_local_image_list()
                    self.fallback_image_list = self.image_list
                    self.current_mode = mode_backup
                    self.image_list = image_list_backup
                    self.fallback_index = -1
                if not self.fallback_image_list:
                    self.clear_foreground_label("No fallback images found")
                else:
                    self.fallback_index = (self.fallback_index + 1) % len(self.fallback_image_list)
                    new_path = self.fallback_image_list[self.fallback_index]
                    self.last_displayed_path = new_path
                    self.show_foreground_image(new_path)
                    self.spotify_fallback_due = time.monotonic() + max(1, int(self.disp_cfg.get("image_interval", 60)))
                self.spotify_info_label.setText("")
                self.spotify_info_label.hide()
            else:
                self.clear_foreground_label("No Spotify track info")
                self.spotify_info_label.setText("")
                self.spotify_info_label.hide()
        return


    def update_spotify_progress(self):
        if not self.spotify_info:
            self.spotify_progress_bar.setValue(0)
            return
        duration = self.spotify_info.get("duration_ms", 0)
        elapsed = max(0, time.monotonic() - self.spotify_info["fetched_time"]) * 1000
        progress = self.spotify_info.get("progress_ms", 0) + elapsed
        self.spotify_progress_bar.setValue(int(min(100, max(0, progress / duration * 100))) if duration > 0 else 0)

    def start_spotify_fetch(self):
        if self.spotify_fetch_pending is not None:
            return
        self.spotify_fetch_id += 1
        fid = self.spotify_fetch_id
        self.spotify_fetch_pending = fid
        emit = self.spotify_result.emit

        def worker():
            try:
                result = shared_poller().fetch()
            except Exception:
                result = Playback("offline")
            try:
                emit(fid, result)
            except RuntimeError:
                pass  # The Qt receiver was destroyed while the request finished.

        threading.Thread(target=worker, daemon=True).start()

    @Slot(int, object)
    def handle_spotify_result(self, fid, result):
        if fid == self.spotify_fetch_pending:
            self.spotify_fetch_pending = None
        if not self.running or self.current_mode != "spotify" or fid != self.spotify_fetch_id:
            return
        previous_status = getattr(self, "spotify_status", None)
        self.spotify_status = result.status
        if result.status != previous_status:
            log_message(f"Spotify status: {result.status}")
        if result.status == "playing":
            self.spotify_info = {
                "song": result.song, "artist": result.artist, "album": result.album,
                "progress_ms": result.progress_ms, "duration_ms": result.duration_ms,
                "fetched_time": result.fetched_time,
            }
            self.spotify_fallback_due = 0
        else:
            self.spotify_info = None
        self.render_spotify(result.art_path if result.status == "playing" else "")

    def pull_displays_from_remote(self, ip):
        pass  # Placeholder if needed

class EchoViewGUI:
    def __init__(self):
        self.cfg = load_config()
        self.app = QApplication(sys.argv)

        self.windows = []
        self.window_by_connector = {}
        self.mode_attempts = set()
        self.app.screenAdded.connect(self._screen_added)
        self.app.screenRemoved.connect(self._screen_removed)
        for screen in self.app.screens():
            screen.geometryChanged.connect(self._schedule_sync)
        self._sync_screens()

    def _schedule_sync(self, *args):
        QTimer.singleShot(100, self._sync_screens)

    def _screen_added(self, screen):
        screen.geometryChanged.connect(self._schedule_sync)
        self._schedule_sync()

    def _screen_removed(self, screen):
        # Stop playback immediately instead of letting Qt move it to a live output.
        for name, window in list(self.window_by_connector.items()):
            if window.assigned_screen is screen:
                window.close()
                del self.window_by_connector[name]
                self.mode_attempts = {item for item in self.mode_attempts if item[0] != name}
        self.windows = list(self.window_by_connector.values())
        self._schedule_sync()

    def _sync_screens(self):
        self.cfg = load_config()
        inventory = discover_monitors()
        screens = self.app.screens()
        if not inventory:
            # Qt still supplies trustworthy identities when xrandr is unavailable.
            inventory = {screen.name(): {"connected": True, "active": True,
                         "current_mode": f"{screen.geometry().width()}x{screen.geometry().height()}"}
                         for screen in screens if screen.name()}
        if reconcile_displays(self.cfg, inventory):
            save_config(self.cfg)
        assignments = screen_assignments(self.cfg, screens)
        active_names = {name for name, _ in assignments}
        for name in set(self.window_by_connector) - active_names:
            self.window_by_connector.pop(name).close()
        for name, screen in assignments:
            display = self.cfg["displays"][name]
            selection = display.get("output_mode", "auto")
            attempt = (name, selection)
            if selection != "auto" and attempt not in self.mode_attempts:
                self.mode_attempts.add(attempt)
                try:
                    apply_output_mode(name, selection)
                except (ValueError, RuntimeError) as exc:
                    log_message(f"Saved output preference unavailable for {name}: {exc}")
            window = self.window_by_connector.get(name)
            if window and window.assigned_screen is not screen:
                window.close()
                window = None
            if window is None:
                window = DisplayWindow(name, display, screen)
                window.setWindowTitle(name)
                self.window_by_connector[name] = window
                window.show()
            else:
                window.setup_layout()
                window.updateForegroundScaled()
        self.windows = list(self.window_by_connector.values())

    def run(self):
        sys.exit(self.app.exec())


def main():
    try:
        log_message(f"Starting EchoView GUI (v{APP_VERSION}).")
        gui = EchoViewGUI()
        gui.run()
    except Exception as e:
        log_message(f"Exception in main: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
