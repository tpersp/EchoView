from PIL import Image, ImageDraw
import pytest

from echoview.spotify_background import extract_palette, background_colours, background_style, foreground_colour


def test_dominant_palette_uses_main_and_distinct_secondary_colour():
    image=Image.new('RGB',(100,100),'red')
    ImageDraw.Draw(image).rectangle((70,0,100,100),fill='blue')
    first,second=extract_palette(image)
    assert first=='#ff0000' and second=='#0000ff'


def test_tiny_accents_and_transparent_pixels_do_not_dominate():
    image=Image.new('RGB',(100,100),'white')
    ImageDraw.Draw(image).rectangle((0,0,5,5),fill='red')
    assert extract_palette(image)[0]=='#ffffff'
    assert extract_palette(Image.new('RGBA',(10,10),(255,0,0,0)))==('#000000','#000000')


@pytest.mark.parametrize('dim,expected', [(0,'#ff0000'),(50,'#800000'),(95,'#0d0000')])
def test_dimming_and_static_styles(dim,expected):
    options={'spotify_background_mode':'artwork','spotify_background_dim':dim}
    assert background_style(options,('#ff0000','#0000ff'))==expected
    assert background_colours(options,('#ff0000','#0000ff'))==(expected,expected)
    options['spotify_background_mode']='gradient'
    style=background_style(options,('#ff0000','#0000ff'))
    assert 'qlineargradient' in style and expected in style


def test_black_default_missing_art_and_invalid_palettes_are_safe():
    assert background_style({},())=='#000000'
    options={'spotify_background_mode':'gradient','spotify_background_dim':65}
    assert background_style(options,())==background_style(options,['not-css','red; background:evil'])


def test_card_automatic_text_contrast_and_manual_colour():
    options={'spotify_background_mode':'artwork','spotify_background_dim':0}
    assert foreground_colour(options,('#ffffff',))=='#101620'
    options['spotify_background_dim']=65
    assert foreground_colour(options,('#ffffff',))=='#edf2f7'
    options.update(spotify_negative_font=False,spotify_font_color='#123456')
    assert foreground_colour(options,())=='#123456'
