#!/usr/bin/env python3

from hsluv import hsluv_to_rgb, hpluv_to_rgb
import asyncio
import configparser
from datetime import datetime
import logging
import time
import sys
import os
import os.path
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageEnhance, ImageFont, ImageDraw
import weather as weatherimport
import music as musicimport
from music import TrackError
from config import config
from colorsys import rgb_to_hsv, hsv_to_rgb

config["config"] = configparser.ConfigParser()
basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

if len(sys.argv) > 1:
    configfile = sys.argv[1]
else:
    configfile = "%s/local.config" % basepath

config["config"].read(configfile)

try:
    devices = config["config"]["chromecast"]["devices"].split(", ")
except KeyError:
    devices = False

image_cache = "%s/imagecache" % (basepath)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

  
def font(size):
    return ImageFont.truetype(config["config"]["fonts"]["time"], size)

def hpluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hpluv_to_rgb([h, s , v]))

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

class Frame:
    def __init__(self):
        self.options = RGBMatrixOptions()
        self.options.brightness = int(config["config"]["matrix"]["brightness"])
        self.options.hardware_mapping = "adafruit-hat-pwm"
        self.options.rows = int(config["config"]["matrix"]["height"])
        self.options.cols = int(config["config"]["matrix"]["width"])
        self.gamma = lambda value : round(pow(value / 255.0, float(config["config"]["matrix"]["gamma"])) * 255.0)
        
        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols - int(config["config"]["matrix"]["padding_left"])
        self.height = self.options.rows - int(config["config"]["matrix"]["padding_top"])
    
    @property
    def square(self):
        return self.options.cols == self.options.rows

    def swap(self, canvas):
        padding_left = int(config["config"]["matrix"]["padding_left"])
        padding_top = int(config["config"]["matrix"]["padding_top"])

        canvas = Image.eval(canvas, self.gamma)

        if config["weather"].night:
            canvas = ImageEnhance.Brightness(canvas).enhance(0.5)

        self.offscreen_canvas.SetImage(canvas, padding_left, padding_top)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

def brighten(rgb):
    r, g, b = rgb
    h, s, v = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    v = min(1.0, v * 1.5)
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def getsize(bbox):
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])

def small_clock():
    timeImg = Image.new('RGBA', (32, 32), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)
    color = brighten(config["weather"].temp_color())
    draw.fontmode = None
    
    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%I")))
    draw.text((17 - (t_width >> 1), 5 - (t_height >> 1) + 1), datetime.now().strftime("%I"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 4 - (t_height >> 1) + 1), datetime.now().strftime("%I"), color, font=font(18))

    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%M")))
    draw.text((17 - (t_width >> 1), 20 - (t_height >> 1) + 1), datetime.now().strftime("%M"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 19 - (t_height >> 1) + 1), datetime.now().strftime("%M"), color, font=font(18))

    return timeImg

def clock():
    mytime=datetime.now().strftime("%-I:%M")

    timeImg = Image.new('RGBA', (64, 30), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)

    draw.rectangle([(0,0), (64,30)], fill=config["weather"].temp_color())

    t_width = getsize(font(22).getbbox(mytime))[0]
    t_height = getsize(font(22).getbbox(mytime))[1]

    draw.fontmode = None
    draw.text((32 - (t_width >> 1) + 2, 10 - (t_height >> 1) + 2),
            mytime, (0,0,0), font=font(22))
    draw.text((32 - (t_width >> 1), 10 - (t_height >> 1)),
            mytime, brighten(config["weather"].temp_color()), font=font(22))

    return timeImg

async def main():
    weather = config["weather"]
    music = config["music"]
    frame = config["frame"]
    txtImg = None
    canvas = None
    t=0
    while True:
        # We have a playing track.
        if music.nowplaying():
            
            if music.new_song():
                logger.warning("now playing song: %s (%s)" % (music.nowplaying().track, type(music.nowplaying())))
                txtImg = music.layout_text()

            # Fade in new album covers
            if music.new_album():
                try:
                    canvas = music.canvas()
                except TrackError as err:
                    logger.warning(err)
                    canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
                    canvas.paste(weather.weather_summary(), (0, 0))
                    canvas.paste(weather.icon(), (32, 0))
                    
                    
                logger.warning("now playing album: %s - %s" % (music.nowplaying().artist, music.nowplaying().album))
                for x in range(127):
                    bg = canvas.copy()
                    if txtImg.width < frame.width:
                        bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                    frame.swap(ImageEnhance.Brightness(bg).enhance(x * 2 / 255.0).convert('RGB'))
                    time.sleep(0.01) # Don't release thread until scroll is done

                await asyncio.sleep(0)

            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                for x in range(txtImg.width + 10 + frame.width):
                    bg = canvas.copy()
                    bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    time.sleep(0.01) # Don't release thread until scroll is done
                await asyncio.sleep(1.0)
            else:
                bg = canvas.copy()
                bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))

        # Nothing is playing
        else:
            weather_canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
            
            # Weather summary is always displayed
            weather_canvas.paste(weather.weather_summary(), (0, 0))
            weather_canvas.paste(weather.icon(), (32, 0))

            # On large screens, show a small clock and the planet paths or a big clock
            if config["frame"].square:
                if weather.night:
                    # t = int((time.time() % 300) * 128 / 300)
                    t = t + 1
                    p_canvas = weather.p_canvas.crop((t, 0, t + 128, 64)).resize((64, 32), resample=Image.Resampling.BILINEAR)
                    weather_canvas.alpha_composite(p_canvas, dest=(0,32))
                    
                    weather_canvas.alpha_composite(small_clock(), dest=(32, 0))
                else:
                    weather_canvas.paste(clock(), (0,34))
            # On small screens, show a small clock over the weather icon
            else:
                weather_canvas.alpha_composite(small_clock(), dest=(32,0))
                # t = t + 1
                # p_canvas = weather.p_canvas.crop((t, 0, t + 128, 64)).resize((64, 32), resample=Image.Resampling.BILINEAR)
                # weather_canvas.alpha_composite(p_canvas, dest=(0,0))
            
            frame.swap(weather_canvas.convert('RGB'))

        await asyncio.sleep(0)

async def update_weather():
    while True:
        delay = config["weather"]._update()
        await asyncio.sleep(delay)

async def update_chromecast():
    while True:
        delay = config["music"].get_playing_chromecast()
        await asyncio.sleep(delay)

async def update_plex():
    while True:
        delay = config["music"].get_playing_plex()
        await asyncio.sleep(delay)

async def update_heos():
    while True:
        delay = config["music"].get_playing_heos()
        await asyncio.sleep(delay)

async def update_spotify():
    while True:
        delay = config["music"].get_playing_spotify()
        await asyncio.sleep(delay)

async def metamain():
    await asyncio.gather(
        update_weather(),
        update_plex(),
        update_spotify(),
        update_chromecast(),
        update_heos(),
        main()
    )

config["frame"] = Frame()
config["weather"] = weatherimport.Weather(api_key=config["config"]["openweathermap"]["api_key"], image_cache=image_cache)
config["music"] = musicimport.Music(devices=devices, image_cache=image_cache)

asyncio.run(metamain())
