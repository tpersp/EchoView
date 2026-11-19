from datetime import datetime
import pytest
from echoview.clock_overlay import format_clock


@pytest.mark.parametrize('hour,minute,second,twelve,seconds,expected',[
    (0,0,0,True,True,'12:00:00 AM'),
    (0,5,6,True,False,'12:05 AM'),
    (12,0,0,True,False,'12:00 PM'),
    (13,2,3,True,True,'1:02:03 PM'),
    (23,59,59,True,False,'11:59 PM'),
    (0,5,6,False,True,'00:05:06'),
    (9,5,6,False,False,'09:05'),
    (23,59,59,False,True,'23:59:59'),
])
def test_clock_format(hour,minute,second,twelve,seconds,expected):
    assert format_clock(datetime(2026,1,1,hour,minute,second),
                        {'clock_format':'12' if twelve else '24','clock_show_seconds':seconds})==expected


def test_existing_clock_keeps_24_hour_seconds():
    assert format_clock(datetime(2026,1,1,13,2,3),{})=='13:02:03'
