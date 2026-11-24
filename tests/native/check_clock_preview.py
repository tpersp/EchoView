"""Export actual native clock bounds for the browser parity check; no real media."""
import json
import os
from pathlib import Path
import sys
import tempfile
from datetime import datetime
from types import SimpleNamespace
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
with tempfile.TemporaryDirectory(prefix='echoview-clock-metrics-') as directory:
    os.environ['VIEWER_HOME']=os.environ['IMAGE_DIR']=directory
    os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
    from PySide6.QtCore import QRect
    from PySide6.QtWidgets import QApplication
    from echoview import viewer
    app=QApplication([])
    display={'mode':'calibration','safe_area':{'left':5,'right':5,'top':5,'bottom':5}}
    cfg={'displays':{'fixture':display}}
    viewer.load_config=lambda:cfg
    viewer.datetime=SimpleNamespace(now=lambda:datetime(2026,11,21,23,58,59))
    window=viewer.DisplayWindow('fixture',display,app.primaryScreen())
    rows=[]
    for width,height,aspect in ((320,240,'auto'),(1024,600,'auto'),(1920,1080,'auto'),(720,576,'4:3')):
        window.assigned_screen=SimpleNamespace(geometry=lambda w=width,h=height:QRect(0,0,w,h))
        window.disp_cfg['display_aspect']=aspect
        for requested in (8,26,48,150,512):
            for format,seconds in (('24',True),('24',False),('12',True),('12',False)):
                for position in ('top-left','center','bottom-right'):
                    settings=dict(clock_enabled=True,clock_font_size=requested,clock_format=format,
                                  clock_show_seconds=seconds,clock_position=position)
                    display['overlay']=settings
                    window.apply_overlay_settings(cfg);app.processEvents()
                    label=window.clock_label;rect=label.geometry()
                    assert label.font().family()=='DejaVu Sans'
                    assert window.presentation_rect().contains(rect)
                    rows.append(dict(width=width,height=height,aspect=width*window.physical_pixel_aspect()/height,
                                     pixel_aspect=window.physical_pixel_aspect(),safe_area=display['safe_area'],
                                     requested=requested,format=format,seconds=seconds,position=position,
                                     font=label.font().pixelSize(),bounds=[rect.x(),rect.y(),rect.width(),rect.height()]))
    Path('/tmp/echoview-clock-geometry.json').write_text(json.dumps(rows))
    window.close()
    print('Native clock: bundled font, 240 geometric cases, 12/24-hour, optional seconds, narrow-screen fitting and PAL aspect passed.')
