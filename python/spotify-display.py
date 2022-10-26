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
import requests
import http
import socket
import weather as weatherimport
import music as musicimport
from config import config

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

def getFont(fontconfig):
    path, size = fontconfig.split(",")
    return ImageFont.truetype(path, int(size))

ttfFont = getFont(config["config"]["fonts"]["regular"])
ttfFontSm = getFont(config["config"]["fonts"]["small"])
ttfFontLg = getFont(config["config"]["fonts"]["large"])
ttfFontTime = getFont(config["config"]["fonts"]["time"])
weatherFont = getFont(config["config"]["openweathermap"]["font"])

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

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

        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols
        self.height = self.options.rows
    
    def swap(self, canvas):
        if config["weather"].night():
            self.offscreen_canvas.SetImage(ImageEnhance.Brightness(canvas).enhance(0.5), 0, 0)
        else:
            self.offscreen_canvas.SetImage(canvas, 0, 0)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

async def main():
    weather = config["weather"]
    music = config["music"]
    frame = config["frame"]
    txtImg = None
    
    while True:
        # We have a playing track.
        if music.nowplaying():
            if music.new_song():
                logger.info("now playing song: %s" % (music.nowplaying().track))
                txtImg = music.get_text()

            # Fade in new album covers
            if music.new_album():
                logger.info("now playing album: %s - %s" % (music.nowplaying().artist, music.nowplaying().album))
                for x in range(127):
                    frame.swap(ImageEnhance.Brightness(music.canvas()).enhance(x * 2 / 255.0).convert('RGB'))
                await asyncio.sleep(0)

            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                for x in range(txtImg.width + 10 + frame.width):
                    bg = music.canvas()
                    bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - 2 - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    await asyncio.sleep(0.0125)
                await asyncio.sleep(1.0)
            else:
                bg = music.canvas()
                bg.alpha_composite(txtImg, dest=(0, frame.height - 2 - txtImg.height))
                frame.swap(bg.convert('RGB'))

        # Nothing is playing
        else:
            frame.swap(weather.image().convert('RGB'))

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

async def update_spotify():
    while True:
        delay = config["music"].get_playing_spotify()
        await asyncio.sleep(delay)

async def metamain():
    await asyncio.gather(
        update_weather(),
        update_plex(),
        update_chromecast(),
        update_spotify(),
        main()
    )

config["frame"] = Frame()
config["weather"] = weatherimport.Weather(api_key=config["config"]["openweathermap"]["api_key"], 
                                image_cache=image_cache, 
                                fontSm=ttfFontSm, fontLg=ttfFontLg, fontTime=ttfFontTime, font=ttfFont)
config["music"] = musicimport.Music(devices=devices, 
                            image_cache=image_cache, font=ttfFont)

asyncio.run(metamain())
