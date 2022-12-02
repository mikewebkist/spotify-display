#!/usr/bin/env python3

from hsluv import hsluv_to_rgb, hpluv_to_rgb
import math
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
        self.gamma = float(config["config"]["matrix"]["gamma"])

        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols
        self.height = self.options.rows - int(config["config"]["matrix"]["padding_top"])
    
    @property
    def square(self):
        return self.options.cols == self.options.rows

    def swap(self, canvas):
        padding_left = int(config["config"]["matrix"]["padding_left"])
        padding_top = int(config["config"]["matrix"]["padding_top"])
        
        def gamma(value):
            return round(pow(value / 255.0, self.gamma) * 255.0)

        canvas = Image.eval(canvas, gamma)

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

def small_clock():
    timeImg = Image.new('RGBA', (32, 32), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)
    color = brighten(config["weather"].temp_color())
    draw.fontmode = None
    
    t_width, t_height = font(18).getsize(datetime.now().strftime("%I"))
    draw.text((17 - (t_width >> 1), 5 - (t_height >> 1) + 1), datetime.now().strftime("%I"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 4 - (t_height >> 1) + 1), datetime.now().strftime("%I"), color, font=font(18))

    t_width, t_height = font(18).getsize(datetime.now().strftime("%M"))
    draw.text((17 - (t_width >> 1), 20 - (t_height >> 1) + 1), datetime.now().strftime("%M"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 19 - (t_height >> 1) + 1), datetime.now().strftime("%M"), color, font=font(18))

    return timeImg

def clock():
    mytime=datetime.now().strftime("%-I:%M")

    timeImg = Image.new('RGBA', (64, 30), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)

    draw.rectangle([(0,0), (64,32)], fill=config["weather"].temp_color())

    t_width = font(22).getsize(mytime)[0]
    t_height = font(22).getsize(mytime)[1]

    draw.fontmode = None
    draw.text((32 - (t_width >> 1) + 2, 12 - (t_height >> 1) + 2),
            mytime, (0,0,0), font=font(22))
    draw.text((32 - (t_width >> 1), 12 - (t_height >> 1)),
            mytime, brighten(config["weather"].temp_color()), font=font(22))

    return timeImg

async def main():
    weather = config["weather"]
    music = config["music"]
    frame = config["frame"]
    txtImg = None
    
    while True:
        # We have a playing track.
        if music.nowplaying():
            if music.new_song():
                logger.warn("now playing song: %s (%s)" % (music.nowplaying().track, type(music.nowplaying())))
                txtImg = music.layout_text(music.track_text())
                mtvtime = 0.0

            # Fade in new album covers
            if music.new_album():
                logger.warn("now playing album: %s - %s" % (music.nowplaying().artist, music.nowplaying().album))
                for x in range(127):
                    bg = music.canvas()
                    if txtImg.width < frame.width:
                        bg.alpha_composite(txtImg, dest=(0, frame.height - 2 - txtImg.height))
                    frame.swap(ImageEnhance.Brightness(bg).enhance(x * 2 / 255.0).convert('RGB'))
                    time.sleep(0.0125) # Don't release thread until scroll is done

                await asyncio.sleep(0)

            # Only show credits at start and end of playback.
            # if music.nowplaying().timein < 30 or not mtvtime or (music.nowplaying().timeleft < (math.floor(30.0 / mtvtime) * mtvtime) and music.nowplaying().timeleft > mtvtime):
            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                t0 = time.time()
                for x in range(txtImg.width + 10 + frame.width):
                    bg = music.canvas()
                    bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    time.sleep(0.0125) # Don't release thread until scroll is done
                t1 = time.time()
                mtvtime = max(mtvtime, t1 - t0)
                await asyncio.sleep(1.0)
            else:
                bg = music.canvas()
                bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))

        # Nothing is playing
        else:
            canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
            
            # Weather summary is always displayed
            canvas.paste(weather.weather_summary(), (0, 0))
            canvas.paste(weather.icon(), (32, 0))

            # On large screens, show a small clock and the planet paths or a big clock
            if config["frame"].square:
                if weather.night:
                    canvas.alpha_composite(weather.planets(), dest=(0,32))
                    canvas.alpha_composite(small_clock(), dest=(32, 0))
                else:
                    canvas.paste(clock(), (0,34))
            # On small screens, show a small clock over the weather icon
            else:
                canvas.alpha_composite(small_clock(), dest=(32,0))
            
            frame.swap(canvas.convert('RGB'))

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
