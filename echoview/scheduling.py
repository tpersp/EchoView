"""Daily wall-clock playback selection; no jobs, media access or config writes."""
from datetime import datetime
import re

MAX_SLOTS = 48


def normalize_schedule(entries):
    if not isinstance(entries, list) or not 1 <= len(entries) <= MAX_SLOTS:
        raise ValueError('Add between 1 and 48 schedule slots.')
    result, times = [], set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError('Invalid schedule slot.')
        start = entry.get('time', '')
        if not isinstance(start, str) or not re.fullmatch(r'(?:[01][0-9]|2[0-3]):[0-5][0-9]', start):
            raise ValueError('Choose a valid start time for every slot.')
        if start in times:
            raise ValueError(f'Two schedule slots start at {start}. Choose different times.')
        times.add(start)
        media = entry.get('media', 'images')
        if media not in ('images', 'videos'):
            raise ValueError('Choose images/GIFs or videos for each slot.')
        folders = entry.get('folders')
        if not isinstance(folders, list) or not 1 <= len(folders) <= 256:
            raise ValueError(f'Choose at least one folder for the {start} slot (up to 256).')
        for folder in folders:
            if (not isinstance(folder, str) or not folder or len(folder) > 255
                    or folder in ('.', '..') or folder.startswith('_')
                    or '/' in folder or '\\' in folder or any(ord(c) < 32 for c in folder)):
                raise ValueError(f'Invalid folder in the {start} slot.')
        name = entry.get('name', '')
        if not isinstance(name, str) or len(name) > 40 or any(ord(c) < 32 for c in name):
            raise ValueError('Slot names must be at most 40 characters.')
        shuffle = entry.get('shuffle', False)
        if not isinstance(shuffle, bool):
            raise ValueError('Invalid schedule shuffle setting.')
        result.append(dict(time=start, name=name.strip(), media=media,
                           folders=list(dict.fromkeys(folders)), shuffle=shuffle))
    return sorted(result, key=lambda slot: slot['time'])


def select_slot(entries, now=None):
    """Select from normalized entries, carrying yesterday's last slot overnight."""
    if not entries:
        return None
    now = now or datetime.now()
    clock = now.strftime('%H:%M')
    return next((slot for slot in reversed(entries) if slot['time'] <= clock), entries[-1])


def effective_settings(display, entries, now=None):
    """Resolve to existing image/video modes without changing the saved display."""
    effective = dict(display)
    slot = select_slot(entries, now)
    if slot is None:
        effective['mode'] = 'schedule_empty'
        return effective, None
    if slot['media'] == 'images':
        effective.update(mode='mixed', mixed_folders=list(slot['folders']), shuffle_mode=slot['shuffle'])
    else:
        effective.update(mode='videos', video_category=slot['folders'][0], specific_video='', shuffle_videos=slot['shuffle'],
                         _scheduled_folders=list(slot['folders']))
    key = (slot['time'], slot['media'], tuple(slot['folders']), slot['shuffle'])
    return effective, key


def device_clock():
    now = datetime.now().astimezone()
    return {'iso': now.isoformat(), 'time': now.strftime('%H:%M:%S'),
            'zone': now.tzname(), 'offset': now.strftime('%z'),
            'seconds': now.hour * 3600 + now.minute * 60 + now.second}
