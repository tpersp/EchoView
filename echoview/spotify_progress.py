"""Local playback interpolation; this module never contacts Spotify."""


class ProgressTimeline:
    CORRECTION_SECONDS = 2.0
    SEEK_THRESHOLD_MS = 1500

    def __init__(self):
        self.clear()

    def clear(self):
        self.key = None
        self.duration = 0
        self.progress = 0
        self.sample_time = 0
        self.correction = 0
        self.corrected_at = 0

    def position(self, now):
        if self.key is None:
            return 0
        remaining = max(0, 1 - max(0, now - self.corrected_at) / self.CORRECTION_SECONDS)
        position = self.progress + max(0, now - self.sample_time) * 1000 + self.correction * remaining
        return max(0, min(self.duration, position))

    def sample(self, key, progress, duration, sampled_at, now):
        # Reusing a shared cached response must not restart its correction.
        if self.key == key and self.sample_time == sampled_at:
            return
        previous = self.position(now)
        target = progress + max(0, now - sampled_at) * 1000
        delta = previous - target
        smooth = self.key == key and self.duration == duration and abs(delta) <= self.SEEK_THRESHOLD_MS
        self.key, self.duration = key, max(0, duration)
        self.progress, self.sample_time = progress, sampled_at
        self.correction = delta if smooth else 0
        self.corrected_at = now


def format_playback_time(position_ms, duration_ms):
    """Whole seconds from the same local timeline as the progress bar."""
    duration = max(0, int(duration_ms or 0))
    position = max(0, min(duration, int(position_ms or 0)))
    def clock(milliseconds):
        seconds = milliseconds // 1000
        hours, seconds = divmod(seconds, 3600)
        minutes, seconds = divmod(seconds, 60)
        return f'{hours}:{minutes:02}:{seconds:02}' if hours else f'{minutes}:{seconds:02}'
    return f'{clock(position)}/{clock(duration)}' if duration else '0:00/–:––'
