"""Locale-independent clock formatting shared by native overlay callers."""


def format_clock(now, settings):
    twelve = settings.get('clock_format', '24') == '12'
    hour = str(now.hour % 12 or 12) if twelve else f'{now.hour:02d}'
    text = f'{hour}:{now.minute:02d}'
    if settings.get('clock_show_seconds', True):
        text += f':{now.second:02d}'
    if twelve:
        text += ' PM' if now.hour >= 12 else ' AM'
    return text


def separators_visible(now, settings):
    return not settings.get('clock_blink_separators', False) or now.microsecond < 500000
