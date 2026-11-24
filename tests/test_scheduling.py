from copy import deepcopy
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

import pytest

from echoview import scheduling, presets


def daily():
    return scheduling.normalize_schedule([
        {'time': '18:00', 'name': 'Evening', 'folders': ['Evening, calm'], 'media': 'videos'},
        {'time': '06:00', 'name': 'Morning', 'folders': ['Morning', 'Photos'], 'shuffle': True},
        {'time': '14:00', 'name': 'Afternoon', 'folders': ['Day']},
    ])


@pytest.mark.parametrize('clock,expected', [
    ('00:00:00', '18:00'), ('05:59:59', '18:00'), ('06:00:00', '06:00'),
    ('13:59:59', '06:00'), ('14:00:00', '14:00'), ('17:59:59', '14:00'),
    ('18:00:00', '18:00'), ('23:59:59', '18:00'),
])
def test_exact_boundaries_and_overnight_carry(clock, expected):
    now = datetime.fromisoformat('2026-11-18T' + clock)
    assert scheduling.select_slot(daily(), now)['time'] == expected


def test_normalization_is_pure_sorted_and_preserves_comma_names():
    entries = [{'time': '18:00', 'folders': ['Trips, 2026', 'Photos', 'Photos']},
               {'time': '06:00', 'folders': ['Morning']}]
    before = deepcopy(entries)
    result = scheduling.normalize_schedule(entries)
    assert entries == before
    assert [entry['time'] for entry in result] == ['06:00', '18:00']
    assert result[1]['folders'] == ['Trips, 2026', 'Photos']


@pytest.mark.parametrize('entries', [None, {}, [], [None],
    [{'time': '24:00', 'folders': ['Photos']}],
    [{'time': '6:00', 'folders': ['Photos']}],
    [{'time': '06:60', 'folders': ['Photos']}],
    [{'time': '06:00', 'folders': []}],
    [{'time': '06:00', 'folders': ['../private']}],
    [{'time': '06:00', 'folders': ['/private']}],
    [{'time': '06:00', 'folders': ['_ignored']}],
    [{'time': '06:00', 'folders': [1]}],
    [{'time': '06:00', 'folders': ['Photos'], 'media': 'web_page'}],
    [{'time': '06:00', 'folders': ['Photos'], 'shuffle': 1}],
    [{'time': '06:00', 'folders': ['Photos'], 'name': 'x' * 41}],
    [{'time': '06:00', 'folders': ['Photos']}] * 2,
    [{'time': '06:00', 'folders': ['Photos']}] * 49,
])
def test_invalid_schedules_are_rejected(entries):
    with pytest.raises(ValueError):
        scheduling.normalize_schedule(entries)


def test_effective_settings_do_not_change_saved_config_or_output_preferences():
    saved = {'mode': 'scheduled', 'schedule': daily(), 'safe_area': {'left': 5},
             'video_volume': 30, 'video_mute': True, 'specific_video': 'old.mp4',
             'video_category': '_old', 'output_mode': '1920x1080@60'}
    before = deepcopy(saved)
    morning, morning_key = scheduling.effective_settings(saved, daily(), datetime(2026, 11, 18, 7))
    evening, evening_key = scheduling.effective_settings(saved, daily(), datetime(2026, 11, 18, 19))
    assert saved == before
    assert morning['mode'] == 'mixed' and morning['mixed_folders'] == ['Morning', 'Photos']
    assert morning['shuffle_mode'] is True
    assert evening['mode'] == 'videos' and evening['_scheduled_folders'] == ['Evening, calm']
    assert evening['specific_video'] == '' and evening['video_category'] == 'Evening, calm'
    assert evening['safe_area'] == {'left': 5} and evening['video_volume'] == 30
    assert morning_key != evening_key


def test_single_slot_is_active_all_day_and_does_not_reset_at_midnight():
    entries = scheduling.normalize_schedule([{'time': '14:00', 'folders': ['Day']}])
    display = {'mode': 'scheduled'}
    _, first = scheduling.effective_settings(display, entries, datetime(2026, 11, 18, 23, 59))
    _, second = scheduling.effective_settings(display, entries, datetime(2026, 11, 19, 0, 0))
    assert first == second
    assert scheduling.select_slot(entries, datetime(2026, 11, 18, 6))['time'] == '14:00'


def test_reboot_and_clock_jumps_use_current_slot_not_missed_jobs():
    entries = daily()
    for hour, expected in [(19, '18:00'), (7, '06:00'), (16, '14:00'), (1, '18:00')]:
        assert scheduling.select_slot(entries, datetime(2026, 11, 18, hour))['time'] == expected


def test_dst_spring_gap_and_repeated_autumn_hour_follow_local_clock():
    zone = ZoneInfo('Europe/Copenhagen')
    entries = scheduling.normalize_schedule([{'time': '01:00', 'folders': ['Night']},
                                              {'time': '02:30', 'folders': ['Day']}])
    before_gap = datetime(2026, 3, 29, 0, 59, tzinfo=timezone.utc).astimezone(zone)
    after_gap = datetime(2026, 3, 29, 1, 0, tzinfo=timezone.utc).astimezone(zone)
    assert scheduling.select_slot(entries, before_gap)['time'] == '01:00'
    assert scheduling.select_slot(entries, after_gap)['time'] == '02:30'
    for utc_hour in (0, 1):
        repeated = datetime(2026, 10, 25, utc_hour, 45, tzinfo=timezone.utc).astimezone(zone)
        assert repeated.hour == 2
        assert scheduling.select_slot(entries, repeated)['time'] == '02:30'


def test_empty_runtime_schedule_has_safe_mode_without_media_selection():
    result, key = scheduling.effective_settings({'mode': 'scheduled'}, [])
    assert result['mode'] == 'schedule_empty' and key is None


def test_display_presets_capture_and_restore_schedules():
    cfg = {'displays': {'HDMI-1': {'mode': 'scheduled', 'schedule': daily(), 'safe_area': {'left': 5}}}}
    preset = presets.snapshot(cfg)
    cfg['displays']['HDMI-1'].update(mode='calibration', schedule=[], safe_area={'left': 10})
    result = presets.restore(cfg, preset)
    assert result['displays']['HDMI-1']['mode'] == 'scheduled'
    assert result['displays']['HDMI-1']['schedule'] == daily()
    assert result['displays']['HDMI-1']['safe_area'] == {'left': 10}
