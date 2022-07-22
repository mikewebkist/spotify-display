#!/usr/bin/env python3

from statistics import mean
from hsluv import hsluv_to_rgb, hpluv_to_rgb
import math
import asyncio
import colorsys
import pychromecast
import configparser
from datetime import datetime
import spotipy
from random import random
import logging
import time
import sys
import os
from io import BytesIO
import os.path
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops, ImageFilter, ImageOps, ImageStat
import urllib
import urllib3
import requests
import http
import socket
import weather as weatherimport
import music as musicimport

config = configparser.ConfigParser()
basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

if len(sys.argv) > 1:
    configfile = sys.argv[1]
else:
    configfile = "%s/local.config" % basepath

config.read(configfile)

try:
    devices = config["chromecast"]["devices"].split(", ")
except KeyError:
    devices = False

image_cache = "%s/imagecache" % (basepath)
weather = False
music = False
frame = False

def getFont(fontconfig):
    path, size = fontconfig.split(",")
    return ImageFont.truetype(path, int(size))

ttfFont = getFont(config["fonts"]["regular"])
ttfFontSm = getFont(config["fonts"]["small"])
ttfFontLg = getFont(config["fonts"]["large"])
ttfFontTime = getFont(config["fonts"]["time"])
weatherFont = getFont(config["openweathermap"]["font"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hpluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hpluv_to_rgb([h, s , v]))

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

class Frame:
    def __init__(self):
        self.options = RGBMatrixOptions()
        self.options.brightness = int(config["matrix"]["brightness"])
        self.options.hardware_mapping = "adafruit-hat-pwm"
        self.options.rows = int(config["matrix"]["height"])
        self.options.cols = int(config["matrix"]["width"])

        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols
        self.height = self.options.rows
    
    def gamma(value):
        if weather.night():
            return round(pow(value / 255.0, 0.85) * 200.0)
        else:
            return round(pow(value / 255.0, 0.85) * 200.0)

    def swap(self, canvas):
        self.offscreen_canvas.SetImage(Image.eval(canvas, Frame.gamma), 0, 0)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

async def main():
    while True:
        # We have a playing track.
        if music.nowplaying():
            is_new_song = music.new_song()

            # Fade in new album covers
            if music.new_album():
                print("%s: now playing album: %s" % ("Chromecast" if music.chromecast_songinfo else "Spotify", music.nowplaying()["album"]))
                for x in range(127):
                    frame.swap(ImageEnhance.Brightness(music.canvas()).enhance(x * 2 / 255.0).convert('RGB'))
                await asyncio.sleep(0)

            if is_new_song:
                print("%s: now playing song: %s" % ("Chromecast" if music.chromecast_songinfo else "Spotify", music.nowplaying()["track"]))

            # Build the song info once per cycle. Could just cache it on album change, but meh.
            txtImg = music.get_text()

            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                for x in range(txtImg.width + 10 + frame.width):
                    bg = music.canvas()
                    bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    await asyncio.sleep(0.0125)
                await asyncio.sleep(1.0)
            else:
                bg = music.canvas()
                bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))

        # Nothing is playing
        else:
            frame.swap(weather.image().convert('RGB'))

        await asyncio.sleep(0)

async def update_weather():
    while True:
        delay = weather._update()
        await asyncio.sleep(delay)

async def update_chromecast():
    while True:
        delay = music.get_playing_chromecast()
        await asyncio.sleep(delay)

async def update_spotify():
    while True:
        delay = music.get_playing_spotify()
        await asyncio.sleep(delay)

async def metamain():
    await asyncio.gather(
        update_weather(),
        update_chromecast(),
        update_spotify(),
        main()
    )

frame = Frame()
weather = weatherimport.Weather(api_key=config["openweathermap"]["api_key"], 
                                image_cache=image_cache, 
                                fontSm=ttfFontSm, fontLg=ttfFontLg, fontTime=ttfFontTime, font=ttfFont)
music = musicimport.Music(devices=devices, spotify_secret=config["spotify"]["spotify_secret"], 
                                            spotify_id=config["spotify"]["spotify_id"],
                                            spotify_user=config["spotify"]["username"],
                                            weather=weather,
                                            image_cache=image_cache, font=ttfFont)

asyncio.run(metamain())