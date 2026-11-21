"""Small artwork palettes and cached static backgrounds; no network work."""
import math
import re

MODES = ('black', 'artwork', 'gradient', 'blurred')
FALLBACK = ('#263449', '#171f2c')


def extract_palette(image):
    from PIL import Image
    image.draft('RGB', (48, 48))
    image.thumbnail((48, 48))
    rgba = image.convert('RGBA')
    rgb = Image.new('RGB', rgba.size, 'black')
    rgb.paste(rgba, mask=rgba.getchannel('A'))
    quantized = rgb.quantize(colors=8, method=Image.Quantize.MEDIANCUT)
    palette = quantized.getpalette()
    counted = sorted(((count, tuple(palette[index*3:index*3+3])) for count,index in quantized.getcolors()), reverse=True)
    candidates = [(count, colour) for count,colour in counted if count >= rgb.width*rgb.height*.05]
    vivid = [(count,colour) for count,colour in candidates if max(colour)-min(colour)>=30 and max(colour)>=40]
    choices = vivid or candidates or counted
    first = choices[0][1]
    others = [(count,colour) for count,colour in choices if math.dist(first,colour)>=50]
    second = max(others, key=lambda item: math.dist(first,item[1])*math.sqrt(item[0]))[1] if others else tuple(round(c*.6) for c in first)
    return tuple('#'+''.join(f'{c:02x}' for c in colour) for colour in (first,second))


def background_colours(options, palette):
    supplied = palette if isinstance(palette,(tuple,list)) else ()
    valid = [c for c in supplied if isinstance(c,str) and re.fullmatch(r'#[0-9a-fA-F]{6}',c)]
    if not valid:
        valid = list(FALLBACK)
    first, second = valid[0], valid[1] if len(valid)>1 else valid[0]
    try:
        dim = max(0,min(95,int(options.get('spotify_background_dim',65))))
    except (ValueError,TypeError):
        dim = 65
    def shade(colour):
        return '#'+''.join(f'{round(int(colour[i:i+2],16)*(100-dim)/100):02x}' for i in (1,3,5))
    colours = (shade(first),shade(second))
    return colours if options.get('spotify_background_mode')=='gradient' else (colours[0],colours[0])


def background_style(options, palette):
    mode = options.get('spotify_background_mode','black')
    if mode not in ('artwork','gradient'):
        return '#000000'
    first,second = background_colours(options,palette)
    if mode=='artwork':
        return first
    return f'qlineargradient(x1:0,y1:0,x2:1,y2:0,stop:0 {first},stop:1 {second})'


def foreground_colour(options, palette):
    if not options.get('spotify_negative_font',True):
        return options.get('spotify_font_color','#FFFFFF')
    if options.get('spotify_background_mode','black') not in ('artwork','gradient'):
        return '#edf2f7'
    def luminance(colour):
        components = [int(colour[i:i+2],16)/255 for i in (1,3,5)]
        values = [c/12.92 if c<=.04045 else ((c+.055)/1.055)**2.4 for c in components]
        return sum(c*w for c,w in zip(values,(.2126,.7152,.0722)))
    levels = [luminance(c) for c in background_colours(options,palette)]
    light = min((1.05)/(level+.05) for level in levels)
    dark_level = luminance('#101620')
    dark = min((level+.05)/(dark_level+.05) for level in levels)
    return '#101620' if dark>light else '#edf2f7'


class BlurredArtwork:
    """One tiny blurred cover and one display-sized image per visible layout."""
    def __init__(self):
        self.source_key = self.output_key = None
        self.image = self.output = None

    def get(self, pixmap, dim, size):
        from PIL import Image, ImageFilter, ImageEnhance
        from PySide6.QtCore import Qt, QRectF
        from PySide6.QtGui import QImage, QPixmap, QPainter
        if pixmap is None or pixmap.isNull() or size.isEmpty():
            self.source_key = self.output_key = self.image = self.output = None
            return QPixmap()
        try:
            dim = max(0, min(95, int(dim)))
        except (ValueError, TypeError):
            dim = 65
        key = (pixmap.cacheKey(), dim)
        if key != self.source_key:
            # All image processing is bounded to 96x96, never full-screen blur.
            small = pixmap.scaled(96,96,Qt.KeepAspectRatio,Qt.SmoothTransformation).toImage().convertToFormat(QImage.Format_RGBA8888)
            image = Image.frombytes('RGBA',(small.width(),small.height()),bytes(small.constBits()),'raw','RGBA',small.bytesPerLine())
            rgb = Image.new('RGB',image.size,'black')
            rgb.paste(image,mask=image.getchannel('A'))
            rgb = ImageEnhance.Brightness(rgb.filter(ImageFilter.GaussianBlur(8))).enhance((100-dim)/100)
            data = rgb.tobytes()
            self.image = QPixmap.fromImage(QImage(data,rgb.width,rgb.height,rgb.width*3,QImage.Format_RGB888).copy())
            self.source_key, self.output_key = key, None
        output_key = (key,size.width(),size.height())
        if output_key != self.output_key:
            # Crop the small source before upscaling, bounding memory even for
            # unusual cover aspect ratios and portrait screens.
            width, height = self.image.width(), self.image.height()
            factor = max(size.width()/width,size.height()/height)
            crop_w, crop_h = size.width()/factor,size.height()/factor
            self.output = QPixmap(size)
            self.output.fill(Qt.black)
            painter = QPainter(self.output)
            painter.setRenderHint(QPainter.SmoothPixmapTransform)
            painter.drawPixmap(QRectF(0,0,size.width(),size.height()),self.image,
                               QRectF((width-crop_w)/2,(height-crop_h)/2,crop_w,crop_h))
            painter.end()
            self.output_key = output_key
        return self.output
