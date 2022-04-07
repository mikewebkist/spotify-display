#!/usr/bin/env python3

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
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops, ImageFilter, ImageOps
import urllib
import urllib3
import requests
import http
import socket

config = configparser.ConfigParser()
basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

if len(sys.argv) > 1:
    configfile = sys.argv[1]
else:
    configfile = "%s/local.config" % basepath

config.read(configfile)
username = config["spotify"]["username"]
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

    # r = urllib.request.urlopen(url)
    # return ImageFont.truetype(BytesIO(r.read()), size)

ttfFont = getFont(config["fonts"]["regular"])
ttfFontSm = getFont(config["fonts"]["small"])
ttfFontLg = getFont(config["fonts"]["large"])
ttfFontTime = getFont(config["fonts"]["time"])

weatherFont = ImageFont.truetype("%s/weathericons-regular-webfont.ttf" % basepath, 20)

logging.basicConfig(filename='/tmp/spotify-matrix.log',level=logging.INFO)
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
            return value
            # return round(pow(value / 255.0, 1.0) * 255.0)
        else:
            return round(pow(value / 255.0, 1.25) * 255.0)

    def swap(self, canvas):
        canvas = Image.eval(canvas, Frame.gamma)
        self.offscreen_canvas.SetImage(canvas, 0, 0)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

def getTextImage(texts, textColor=(192,192,192), fontmode="1", dropshadow=(1,1)):
    txtImg = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
    draw = ImageDraw.Draw(txtImg)
    draw.fontmode = fontmode
    for text, position, *font in texts:
        if font:
            lineFont = font[0]
            lineColor = font[1]
        else:
            lineFont = ttfFont
            lineColor = textColor
        (x, y) = position
        if dropshadow:
            draw.text((x + dropshadow[0], y + dropshadow[1]), text, (0,0,0), font=lineFont)
        draw.text((x, y), text, lineColor,   font=lineFont)
    return txtImg

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

class Weather:
    api = "https://api.openweathermap.org/data/2.5/onecall?lat=39.9623348&lon=-75.1927043&appid=%s" % (config["openweathermap"]["api_key"])

    def __init__(self):
        pass
    
    def _update(self):
        try:
            r = urllib.request.urlopen(Weather.api)
        except (http.client.RemoteDisconnected, urllib3.exceptions.ProtocolError, urllib.error.URLError) as err:
            logger.error("Problem getting weather")
            logger.error(err)
            return 30

        self._payload = simplejson.loads(r.read())
        self._lastupdate= datetime.now().timestamp()
        self._now = self._payload["current"]

        # Update every 30 minutes overnight to save API calls
        if time.localtime()[3] <= 5:
            return 60 * 30
        else:
            return 60 * 10

    def night(self):
        if self._now["dt"] > (self._now["sunset"] + 1080) or self._now["dt"] < (self._now["sunrise"] - 1080):
            return True
        else:
            return False

    def icon(self):
        if self.night():
            skyColor = (0, 0, 0)
        else:
            clouds = self.clouds() / 100.0
            # skyColor = (0, 0, 32)
            skyColor = (int(clouds * 16), int(clouds * 16), 16)
            skyColor = (0, 0, 0)

        iconBox = Image.new('RGBA', (32, 32), skyColor)

        if self.night():
            phase = (((round(self._payload["daily"][0]["moon_phase"] * 8) % 8)  + 11))
            moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (image_cache, phase)).resize((20,20))
            moonDim = ImageOps.expand(ImageEnhance.Brightness(moonImage).enhance(0.75), border=4, fill=(0,0,0,0))
            iconBox.alpha_composite(moonDim, dest=(2, -2))

        else:
            url = "http://openweathermap.org/img/wn/%s.png" % (self._now["weather"][0]["icon"])
            filename = "%s/weather-%s.png" % (image_cache, self._now["weather"][0]["icon"])
            if not os.path.isfile(filename):
                logger.info("Getting %s" % url)
                urllib.request.urlretrieve(url, filename)

            iconImage = Image.open(filename)
            iconImage = iconImage.crop((3, 3, 45, 45)).resize((32, 32))
            iconBox.alpha_composite(iconImage, dest=(0, -6))

        return iconBox

    def hour(self, hour):
        return self._payload["hourly"][hour]

    def temp(self):
        return "%.0f°" % ktof(self._payload["current"]["temp"])

    # If the "feels_like" temp is over 80 it's probably steamy outside
    def steamy(self):
        return ktof(self._payload["current"]["feels_like"]) > 90

    def icy(self):
        return ktof(self._payload["current"]["feels_like"]) < 32

    def feelslike(self):
        if self.steamy() or self.icy():
            return "~%.0f°" % ktof(self._payload["current"]["feels_like"])
        else:
            return self.temp()

    def humidity(self):
        return "%.0f%%" % self._payload["current"]["humidity"]

    def clouds(self):
        return self._now["clouds"]

    def wind_speed(self):
        return "%.0f mph" % (self._payload["current"]["wind_speed"] * 2.237)

    # The screen is actually too low-res for this to look good
    def wind_dir(self):
        d = self._now["wind_deg"] - 45
        if d < 0:
            d = d + 360.0

        wind_dirs = ["N", "E", "S", "W"]
        return wind_dirs[int(d / 90)]

    def pressure(self):
        return "%.1f\"" % (self._payload["current"]["pressure"] * 0.0295301)

    def image(self):
        canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        for x in range(24):
            t = time.localtime(self.hour(x+1)["dt"])
            if t[3] == 0:
                draw.line([(28, x+4), (30, x+4)], fill=hsluv2rgb(128.0,0.0,25.0))
            if t[3] in [6, 18]:
                draw.line([(29, x+4), (31, x+4)], fill=hsluv2rgb(128.0,0.0,25.0))
            if t[3] == 12:
                draw.line([(30, x+4), (32, x+4)], fill=hsluv2rgb(128.0,0.0,25.0))

            diff = self.hour(x)["temp"] - self.hour(0)["temp"]
            if diff > 1.0:
                draw.point((30, x+4), fill=hsluv2rgb(17.5, 100.0, 25.0))
            elif diff < -1.0:
                draw.point((30, x+4), fill=hsluv2rgb(231.0, 100.0, 25.0))
            else:
                draw.point((30, x+4), fill=hsluv2rgb(128.0, 0.0, 25.0))
            try:
                if self.hour(x)["rain"]['1h'] > 0.0:
                    draw.point((31, x+4), fill=hsluv2rgb(255.0, 100.0, 50.0))
            except KeyError:
                pass

        iconImage = self.icon()
        # We're replaceing the entire right side of
        # the image, so no need for alpha blending
        canvas.paste(iconImage, (32, 6))

        # A little indicator of rain in the next hour. Each pixel represents two minutes.
        for m in range(32):
            try: # one time the payload didn't include minutely data...
                rain = self._payload["minutely"][2 * m]["precipitation"] + self._payload["minutely"][2 * m + 1]["precipitation"]
                if rain > 0.0:
                    draw.point((m, 0), fill=hsluv2rgb(255.0, 100.0, 50.0))
            except (KeyError, IndexError):
                pass

        mytime=datetime.now().strftime("%-I:%M")

        txtImg = getTextImage([
                            (self.temp(),       (0, -1), ttfFontLg, hsluv2rgb(69.0, 75.0, 75.0)),
                            (self.humidity(),   (0, 11), ttfFontSm, hsluv2rgb(139.9, 75.0, 50.0)),
                            (self.wind_speed(), (0, 17), ttfFontSm, hsluv2rgb(183.8, 75.0, 50.0)),
                            (self.pressure(),   (0, 23), ttfFontSm, hsluv2rgb(128.0, 0.0, 50.0)),
                            ],
                            dropshadow=None)

        def hsv2rgb(h,s,v):
            return tuple(int(i * 256) for i in hpluv_to_rgb([h * 360.0, s * 100.0 , v * 100.0]))
            # return tuple(int(i * 256) for i in colorsys.hsv_to_rgb(h,s,v))

        ts = datetime.now().timestamp()

        cycle_time = 120.0

        draw.rectangle([(2,40), (61,61)], fill=hsv2rgb((ts % cycle_time) / cycle_time, 1.0, 0.25))

        t_width = ttfFontTime.getsize(mytime)[0]
        t_height = ttfFontTime.getsize(mytime)[1]

        x_shadow = 2.0 * math.cos(math.radians((ts) % 360.0))
        y_shadow = 2.0 * math.sin(math.radians((ts) % 360.0))

        timeImg = getTextImage([ (
                             mytime,
                             (34.0 - (t_width / 2) + 1, 49.0 - (t_height / 2) + 1),
                             ttfFontTime,
                             hsv2rgb((ts % cycle_time) / cycle_time, 1.0, 0.10),
                             ) ],
                            fontmode=None, dropshadow=None)
        canvas = Image.alpha_composite(canvas, timeImg)

        timeImg = getTextImage([ (
                             mytime,
                             (32 - (t_width >> 1), 47 - (t_height >> 1)),
                             ttfFontTime,
                             hsv2rgb((ts % cycle_time) / cycle_time, 0.5, 0.75),
                             ) ],
                            fontmode=None, dropshadow=None)

        canvas = Image.alpha_composite(canvas, timeImg)

        return Image.alpha_composite(canvas, txtImg).convert('RGB')

class Music:
    def __init__(self):
        if devices:
            chromecasts, self.browser = pychromecast.get_chromecasts()
            self.chromecasts = []
            # This keeps everything in config file order
            if chromecasts:
                for name in devices:
                    try:
                        self.chromecasts.append(chromecasts[list(map(lambda x: x.name, chromecasts)).index(name)])
                    except ValueError:
                        pass

        self._spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=config["spotify"]["spotify_id"],
                                        client_secret=config["spotify"]["spotify_secret"],
                                        cache_handler=CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, username)),
                                        redirect_uri="http://localhost:8080/callback",
                                        show_dialog=True,
                                        open_browser=False,
                                        scope="user-library-read,user-read-playback-state"))
        user = self._spotify.current_user()
        logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))

        self.lastAlbum = ""
        self.lastSong = ""
        self.chromecast_songinfo = None
        self.spotify_songinfo = None

    def nowplaying(self):
        if self.chromecast_songinfo:
            return self.chromecast_songinfo
        elif self.spotify_songinfo:
            return self.spotify_songinfo
        else:
            return None

    def get_playing_spotify(self):
        if self.chromecast_songinfo:
            return 60.0

        try:
            meta = self._spotify.current_user_playing_track()
            if meta and meta["is_playing"] and meta["item"]:
                obj = {
                        "spotify_playing": True,
                        "track": meta["item"]["name"],
                        "album": meta["item"]["album"]["name"],
                        "artist": ", ".join(map(lambda x: x["name"], meta["item"]["artists"])),
                        "album_art_url": meta["item"]["album"]["images"][0]["url"],
                        "artist_art_url": False,
                        "spotify_duration": meta["item"]["duration_ms"],
                        "spotify_progress": meta["progress_ms"],
                        "spotify_meta": meta,
                        }

                obj["album_id"] = "%s/%s" % (obj["album"], obj["artist"]),
                obj["track_id"] = "%s/%s/%s" % (obj["track"], obj["album"], obj["artist"]),

                self.spotify_songinfo = obj
                timeleft = round((obj["spotify_duration"] - obj["spotify_progress"]) / 1000.0) 
                if (obj["spotify_progress"] / 1000.0) < 60.0:
                    return (obj["spotify_progress"] / 1000.0)
                if timeleft > 120.0:
                    return 60.0
                elif timeleft > 5.0:
                    return timeleft
                else:
                    return 5.0
            else:
                self.spotify_songinfo = None
                return 60.0

        except (spotipy.exceptions.SpotifyException,
                spotipy.oauth2.SpotifyOauthError) as err:
            logger.error("Spotify error getting current_user_playing_track:")
            logger.error(err)
            self.spotify_songinfo = None
            return 60.0 * 5.0

        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                simplejson.errors.JSONDecodeError) as err:
            logger.error("Protocol problem getting current_user_playing_track")
            logger.error(err)
            self.spotify_songinfo = None
            return 60.0

        # Just in case
        return 60.0

    def get_playing_chromecast(self):
        for cast in self.chromecasts:
            # print("Before: %.3f" % time.perf_counter())
            cast.wait()
            if cast.media_controller.status.player_is_playing:
                meta = cast.media_controller.status.media_metadata
                obj = {
                        "chromecast_playing": True,
                        "track": meta["title"],
                        "album": meta["albumName"] if "albumName" in meta else "",
                        "artist": meta["artist"] if "artist" in meta else meta["subtitle"] if "subtitle" in meta else "",
                        "album_art_url": meta["images"][0]["url"] if "images" in meta else False,
                        "artist_art_url": False,
                        }
                obj["album_id"] = "%s/%s" % (obj["album"], obj["artist"]),
                obj["track_id"] = "%s/%s/%s" % (obj["track"], obj["album"], obj["artist"]),
                obj["is_live"]  = cast.media_controller.status.stream_type_is_live

                self.chromecast_songinfo = obj

                if cast.media_controller.status.stream_type_is_live:
                    return 10.0
                elif cast.media_controller.status.duration:
                    timeleft = round((cast.media_controller.status.duration - cast.media_controller.status.adjusted_current_time))

                    if timeleft > 10.0:
                        return 10.0
                    else:
                        return timeleft
                else:
                    print(cast.media_controller.status)
                    return 2.0
                break
        else:
            self.chromecast_songinfo = None

        return 2.0

    def new_album(self):
        if self.lastAlbum == self.nowplaying()["album_id"]:
            return False
        else:
            self.lastAlbum = self.nowplaying()["album_id"]
            return True

    def new_song(self):
        if self.lastSong == self.nowplaying()["track_id"]:
            return False
        else:
            self.lastSong = self.nowplaying()["track_id"]
            return True

    def album_art(self):
        try:
            return self.nowplaying()["album_art_url"]
        except IndexError:
            return None

    def artist_art(self):
        if self.nowplaying()["is_live"]:
            return None

        results = self._spotify.search(q='artist:' + self.nowplaying()["artist"], type='artist')
        try:
            return results["artists"]["items"][0]["images"][-1]["url"]
        except IndexError:
            return None

    def album_image(self):
        if self.album_art():
            url = self.album_art()
        elif self.artist_art():
            url = self.artist_art()
        else: # if we don't have any art, show the weather icon
            return weather.icon()

        m = url.rsplit('/', 1)
        processed = "%s/album-%s.png" % (image_cache, m[-1])

        # We're going to save the processed image instead of the raw one.

        if os.path.isfile(processed):
            image = Image.open(processed)
        else:
            logger.info("Getting %s" % url)
            with urllib.request.urlopen(url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(64,64), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")

        if weather.night():
            image = ImageEnhance.Brightness(image).enhance(0.75)

        if frame.height < 64:
            cover = Image.new('RGBA', (64, 64), (0,0,0))
            cover.paste(image.resize((frame.height, frame.height), Image.LANCZOS), (64 - frame.height, 0))
            return cover
        else:
            return image

    def canvas(self):
        canvas = Image.new('RGBA', (64, 64), (0,0,0))
        canvas.paste(self.album_image(), (0, 0))

        if weather.steamy():
            canvas.alpha_composite(getTextImage([(weather.feelslike(), (0, -2), ttfFont, (128, 128, 64)),]))
        elif weather.icy():
            canvas.alpha_composite(getTextImage([(weather.feelslike(), (0, -2), ttfFont, (128, 148, 196)),]))

        return canvas

    def get_text_length(self):
        if self.album_art() == None:
            return max(ttfFont.getsize(self.nowplaying()["track"])[0], ttfFont.getsize(self.nowplaying()["album"])[0], ttfFont.getsize(self.nowplaying()["artist"])[0])
        else:
            return max(ttfFont.getsize(self.nowplaying()["track"])[0], ttfFont.getsize(self.nowplaying()["artist"])[0])

    def layout_text(self, lines):
        height = 0
        width = 0
        for line in lines:
            wh = ttfFont.getsize(line)
            width = max(width, wh[0])
            height = height + wh[1]

        txtImg = Image.new('RGBA', (width + 1, height + 1), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txtImg)
        draw.fontmode = "1"
        y_pos = 0
        for line in lines:
            draw.text((1, y_pos + 1), line, (0,0,0), font=ttfFont)
            draw.text((0, y_pos), line, (192, 192, 192), font=ttfFont)
            y_pos = y_pos + ttfFont.getsize(line)[1]
        return txtImg

    def get_text(self,textColor=(192,192,192, 255)):
        if self.album_art() == None:
            return self.layout_text([self.nowplaying()["track"],
                                     self.nowplaying()["album"],
                                     self.nowplaying()["artist"]])
        else:
            return self.layout_text([self.nowplaying()["track"],
                                     self.nowplaying()["artist"]])

def main():
    # We have a playing track.
    if music.nowplaying():
        try:
            canvas = music.canvas()

            is_new_song = music.new_song()

            # Fade in new album covers
            if music.new_album():
                print("%s: now playing album: %s" % ("chromecast" if music.chromecast_songinfo else "spotify", music.nowplaying()["album"]))
                for x in range(127):
                    frame.swap(ImageEnhance.Brightness(canvas).enhance(x * 2 / 255.0).convert('RGB'))

            if is_new_song:
                print("%s: now playing song: %s" % ("chromecast" if music.chromecast_songinfo else "spotify", music.nowplaying()["track"]))

            # Length of the longest line of text, in pixels.

            txtImg = music.get_text()

            if is_new_song or txtImg.width >= frame.width:
                for x in range(127):
                    bg = canvas.copy()
                    fg = ImageEnhance.Brightness(txtImg).enhance(x * 2 / 256.0)
                    bg.alpha_composite(fg, dest=(0, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))

            time.sleep(1.0)

            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                for x in range(txtImg.width + 10):
                    bg = canvas.copy()
                    bg.alpha_composite(txtImg, dest=(0 - x, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    time.sleep(0.0125)
                time.sleep(1.0)
            else:
                bg = canvas.copy()
                bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))

        except AttributeError as err:
            # This is because if you pause while the text is scrolling, it crashes. :(
            print(err)

    # Nothing is playing
    else:
        frame.swap(weather.image().convert('RGB'))
    return 0

async def update_weather():
    while True:
        delay = weather._update()
        await asyncio.sleep(delay)

async def update_chromecast():
    while True:
        delay = music.get_playing_chromecast()
        # print(f"chromecast {delay:.1f}secs")
        await asyncio.sleep(delay)

async def update_spotify():
    while True:
        delay = music.get_playing_spotify()
        # print(f"spotify {delay:.1f}secs")
        await asyncio.sleep(delay)

async def update_main():
    while True:
        delay = main()
        await asyncio.sleep(delay)

async def metamain():
    L = await asyncio.gather(
        update_weather(),
        update_chromecast(),
        update_spotify(),
        update_main()
    )
    print(L)

weather = Weather()
frame = Frame()
music = Music()

asyncio.run(metamain())
