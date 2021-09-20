#!/usr/bin/env python3

import configparser
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
image_cache = "%s/imagecache" % (basepath)
weather = False
music = False

def getFont(fontconfig):
    path, size = fontconfig.split(",")
    return ImageFont.truetype(path, int(size))

    # r = urllib.request.urlopen(url)
    # return ImageFont.truetype(BytesIO(r.read()), size)

ttfFont = getFont(config["fonts"]["regular"])
ttfFontSm = getFont(config["fonts"]["small"])
ttfFontLg = getFont(config["fonts"]["large"])

weatherFont = ImageFont.truetype("%s/weathericons-regular-webfont.ttf" % basepath, 20)

# logging.basicConfig(filename='/tmp/spotify-matrix.log',level=logging.INFO)
logger = logging.getLogger(__name__)

class Frame:
    def __init__(self):
        self.options = RGBMatrixOptions()
        self.options.brightness = int(config["matrix"]["brightness"])
        self.options.hardware_mapping = "adafruit-hat-pwm"
        self.options.rows = int(config["matrix"]["height"])
        self.options.cols = int(config["matrix"]["width"])
        self.options.disable_hardware_pulsing = False
        self.options.gpio_slowdown = 3

        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols
        self.height = self.options.rows
    
    def gamma(value):
        return round(pow(value / 255.0, 1.8) * 255.0)

    def swap(self, canvas):
        canvas = Image.eval(canvas, Frame.gamma)
        self.offscreen_canvas.SetImage(canvas, 0, 0)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

def getTextImage(texts, color):
    txtImg = Image.new('RGBA', (64, 32), (255, 255, 255, 0))
    draw = ImageDraw.Draw(txtImg)
    for text, position, *font in texts:
        if font:
            lineFont = font[0]
            lineColor = font[1]
        else:
            lineFont = ttfFont
            lineColor = color
        (x, y) = position
        draw.fontmode = "1"
        draw.text((x - 1, y + 1), text, (0,0,0), font=lineFont)
        draw.text((x,     y    ), text, lineColor,   font=lineFont)
    return txtImg

textColor = (192, 192, 192)

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

class Weather:
    api = "https://api.openweathermap.org/data/2.5/onecall?lat=39.9623348&lon=-75.1927043&appid=%s" % (config["openweathermap"]["api_key"])

    def __init__(self):
        self.nextupdate = 0
        self._update()
    
    def _update(self):
        if time.time() < self.nextupdate:
            return False

        try:
            r = urllib.request.urlopen(Weather.api)
        except (http.client.RemoteDisconnected, urllib3.exceptions.ProtocolError, urllib.error.URLError) as err:
            logger.error("Problem getting weather")
            logger.error(err)
            time.sleep(30)
            return self.nextupdate - time.time()

        self._payload = simplejson.loads(r.read())
        self._now = self._payload["current"]

        # Update every 30 minutes overnight to save API calls
        if time.localtime()[3] <= 5:      
            self.nextupdate = time.time() + (60 * 30)
        else:
            self.nextupdate = time.time() + (60 * 5)
        
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
            skyColor = (32, 32, 32)
            # skyColor = (128 + int(clouds * 64), 128 + int(clouds * 64), 255 - int(clouds * 64))

        iconBox = Image.new('RGBA', (32, 32), skyColor)

        if self.night():
            phase = (((round(self._payload["daily"][0]["moon_phase"] * 8) % 8)  + 11))
            moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (image_cache, phase)).resize((24,24))
            moonDim = ImageOps.expand(ImageEnhance.Brightness(moonImage).enhance(0.75), border=4, fill=(0,0,0,0))
            iconBox.alpha_composite(moonDim)

        else:
            url = "http://openweathermap.org/img/wn/%s.png" % (self._now["weather"][0]["icon"])
            filename = "%s/weather-%s.png" % (image_cache, self._now["weather"][0]["icon"])
            if not os.path.isfile(filename):
                logger.info("Getting %s" % url)
                urllib.request.urlretrieve(url, filename)

            iconImage = Image.open(filename)
            iconImage = iconImage.crop((3, 3, 45, 45)).resize((30, 30))
            iconBox.alpha_composite(iconImage)

        return iconBox

    def hour(self, hour):
        return self._payload["hourly"][hour]

    def temp(self):
        return "%.0f°" % ktof(self._payload["current"]["temp"])

    # If the "feels_like" temp is over 80 it's probably steamy outside
    def steamy(self):
        return ktof(self._payload["current"]["feels_like"]) > 90

    def feelslike(self):
        if self.steamy():
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
        self._update()

        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        for x in range(24):
            t = time.localtime(self.hour(x+1)["dt"])
            if t[3] == 0:
                draw.line([(26, x+4), (28, x+4)], fill=(64, 64, 64))
            if t[3] in [6, 18]:
                draw.line([(27, x+4), (29, x+4)], fill=(64, 64, 64))
            if t[3] == 12:
                draw.line([(28, x+4), (30, x+4)], fill=(64, 64, 64))

            diff = self.hour(x+1)["temp"] - self.hour(x)["temp"]
            if diff > 1.0:
                draw.point((28, x+4), fill=(192, 128, 32))
            elif diff < -1.0:
                draw.point((28, x+4), fill=(64, 64, 255))
            else:
                draw.point((28, x+4), fill=(64, 64, 64))

        iconImage = self.icon()
        # We're replaceing the entire right side of
        # the image, so no need for alpha blending
        canvas.paste(iconImage, (32, 0))

        # A little indicator of rain in the next hour. Each pixel represents two minutes.
        for m in range(30):
            try: # one time the payload didn't include minutely data...
                rain = self._payload["minutely"][2 * m]["precipitation"] + self._payload["minutely"][2 * m + 1]["precipitation"]
                if rain > 0:
                    draw.point((m + 1, 1), fill=(128,128,255))
                else:
                    draw.point((m + 1, 1), fill=(32,32,32))
            except (KeyError, IndexError):
                draw.point((m + 1, 1), fill=(32, 0, 0))

        txtImg = getTextImage([
                            (self.temp(),       (1, 0), ttfFontLg,  (192, 192, 128)),
                            (self.humidity(),   (1, 12), ttfFontSm, (128, 192, 128)),
                            (self.wind_speed(), (1, 18), ttfFontSm, (128, 192, 192)),
                            (self.pressure(),   (1, 24), ttfFontSm, (128, 128, 128)),
                            ],
                            textColor)

        return Image.alpha_composite(canvas, txtImg).convert('RGB')

class Music:
    def __init__(self):
        self._spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=config["spotify"]["spotify_id"],
                                        client_secret=config["spotify"]["spotify_secret"],
                                        cache_handler=CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, username)),
                                        redirect_uri="http://localhost:8080/callback",
                                        show_dialog=True,
                                        open_browser=False,
                                        scope="user-library-read,user-read-playback-state"))
        user = self._spotify.current_user()
        logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))
        self.nextupdate = 0
        self.lastAlbum = ""
        self.lastSong = ""
        self._nowplaying = False

        self._update()

    def timeleft(self):
        return round((self._nowplaying["item"]["duration_ms"] - self._nowplaying["progress_ms"]) / 1000.0)

    def nowplaying(self):
        if self._nowplaying and self._nowplaying["is_playing"] and self._nowplaying["item"]:
            return True
        else:
            return False

    def _update(self):
        if time.time() < self.nextupdate:
            return self.nextupdate - time.time()

        try:
            self._nowplaying = self._spotify.current_user_playing_track()
        except (spotipy.exceptions.SpotifyException,
                spotipy.oauth2.SpotifyOauthError) as err:
            logger.error("Spotify error getting current_user_playing_track:")
            logger.error(err)

            self.nextupdate = time.time() + 60 * 5 # cooloff for 5 minutes
            self._nowplaying = False
            return False

        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                simplejson.errors.JSONDecodeError) as err:
            logger.error("Protocol problem getting current_user_playing_track")
            logger.error(err)

            self.nextupdate = time.time() + 60 # cooloff for 60 seconds
            self._nowplaying = False
            return False

        if not self.nowplaying():
            if time.localtime()[3] <= 7:
                self.nextupdate = time.time() + (5 * 60) # check in 5 minutes
            else:
                self.nextupdate = time.time() + 30 # check in 30 seconds
            return False
        elif self.timeleft() > 30:
            self.nextupdate = time.time() + 10
        else:
            self.nextupdate = time.time() + self.timeleft()

        if self.nowplaying():
            self.track = self._nowplaying["item"]["name"]
            self.album = self._nowplaying["item"]["album"]["name"]
            self.artist = ", ".join(map(lambda x: x["name"], self._nowplaying["item"]["artists"]))
            self.album_id = self._nowplaying["item"]["album"]["id"]
            self.track_id = self._nowplaying["item"]["id"]        

            if self.lastSong != self.track_id:
                self.album_art_url = self.album_art()
                self.artist_art_url = self.artist_art()

        return self.nextupdate - time.time()

    def new_album(self):
        if self.lastAlbum == self.album_id:
            return False
        else:
            self.lastAlbum = self.album_id
            return True

    def new_song(self):
        if self.lastSong == self.track_id:
            return False
        else:
            self.lastSong = self.track_id
            return True

    def artists(self):
        return tuple(map(lambda x: x["name"], self._nowplaying["item"]["artists"]))

    def is_local(self):
        return self._nowplaying["item"]["uri"].startswith("spotify:local:")

    def album_art(self):
        try:
            return self._nowplaying["item"]["album"]["images"][-1]["url"]
        except IndexError:
            return None

    def artist_art(self):
        results = self._spotify.search(q='artist:' + self.artists()[0], type='artist')
        try:
            return results["artists"]["items"][0]["images"][-1]["url"]
        except IndexError:
            return None

    def album_image(self):
        if self.album_art_url:
            url = self.album_art_url
        else:
            url = self.artist_art_url
        m = url.rsplit('/', 1)
        processed = "%s/spotify-%s.png" % (image_cache, m[-1])

        # We're going to save the processed image instead of the raw one.

        if os.path.isfile(processed):
            image = Image.open(processed)
        else:
            logger.info("Getting %s" % url)
            with urllib.request.urlopen(url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(32, 32), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")

        image = ImageEnhance.Color(image).enhance(0.5)
        image = ImageEnhance.Brightness(image).enhance(0.85)
        return image

    def canvas(self):
        canvas = Image.new('RGBA', (64, 32), (0,0,0))
        canvas.paste(self.album_image(), (32, 0))
        if weather.steamy():
            canvas.alpha_composite(getTextImage([(weather.feelslike(), (0, -2), ttfFont, (128, 128, 64)),], textColor))
        else:
            canvas.alpha_composite(getTextImage([(weather.feelslike(), (0, -2), ttfFont, (128, 128, 128)),], textColor))
        return canvas

    def get_text_length(self):
        if self.album_art_url == None:
            return max(ttfFont.getsize(self.track)[0], ttfFont.getsize(self.album)[0], ttfFont.getsize(self.artist)[0])
        else:
            return max(ttfFont.getsize(self.track)[0], ttfFont.getsize(self.artist)[0])

    def get_text(self, x, y, textColor):
        if self.album_art_url == None:
            return getTextImage([
                (self.track, (x, y - 10)),
                (self.album, (x, y)),
                (self.artist, (x, y + 10))
                ], textColor)
        else:
            return getTextImage([
                (self.track, (x, y)),
                (self.artist, (x, y + 10))
                ], textColor)

def main():
    global weather

    frame = Frame()
    weather = Weather()
    music = Music()

    while True:
        music._update()
        weather._update()

        # We have a playing track.
        if music.nowplaying():
            canvas = music.canvas()

            if music.new_album():
                for x in range(127):
                    frame.swap(ImageEnhance.Brightness(canvas).enhance(x * 2 / 255.0).convert('RGB'))
                time.sleep(0.5)


            # Length of the longest line of text, in pixels.
            length = music.get_text_length()

            # If either line of text is longer than the display, scroll
            if length >= frame.width:
                for x in range(length + frame.width + 10):
                    txtImg = music.get_text(frame.width - x, 10, textColor)
                    frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))
                    time.sleep(0.025)

                time.sleep(1.25)

            # If all the text fits, don't scroll.
            else:
                if music.new_song():
                    for x in range(127):
                        # Add an alpha channel to the color for fading in
                        textColorFade = textColor + (x * 2,)
                        txtImg = music.get_text(0, 10, textColorFade)
                        frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))

                txtImg = music.get_text(0, 10, textColor)
                frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))
                time.sleep(2.0)

        # Nothing is playing
        else:
            frame.swap(weather.image().convert('RGB'))
            time.sleep(10)

main()
