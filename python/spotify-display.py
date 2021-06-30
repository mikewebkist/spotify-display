#!/usr/bin/env python3

import spotipy
from random import random
import logging
import time
import sys
import os
import os.path
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops
import urllib
import requests

username = "mikewebkist"

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

image_cache = "%s/imagecache" % (basepath)

ttfFont = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 10)
ttfFontSm = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 7)

if len(sys.argv) > 1:
    username = sys.argv[1]

logging.basicConfig(filename='/tmp/spotify-matrix.log',level=logging.INFO)
logger = logging.getLogger(__name__)

class Frame:
    def __init__(self):
        self.options = RGBMatrixOptions()
        self.options.brightness = 75
        self.options.hardware_mapping = "adafruit-hat-pwm"
        self.options.rows = 32
        self.options.cols = 64
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

def rawImage(url):
    # We're going to save the processed image instead of the raw one.
    m = url.rsplit('/', 1)
    image = None
    processed = "%s/%s.png" % (image_cache, m[-1])
    if os.path.isfile(processed):
        image = Image.open(processed)
    else:
        logger.info("Getting %s" % url)
        with urllib.request.urlopen(url) as rawimage:
            image = Image.open(rawimage)
            image = image.resize((32, 32), resample=Image.LANCZOS)
            image.save(processed, "PNG")

    return image

def processedImage(url):
    image = rawImage(url)
    image = ImageEnhance.Color(image).enhance(0.5)
    image = ImageEnhance.Brightness(image).enhance(0.85)
    return image

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
    api = "https://api.openweathermap.org/data/2.5/onecall?lat=39.9623348&lon=-75.1927043&appid=%s" % (os.environ["OPENWEATHER_API"])

    def __init__(self):
        self.nextupdate = 0
        self._update()
    
    def _update(self):
        if time.time() < self.nextupdate:
            return False

        try:
            r = urllib.request.urlopen(Weather.api)
        except http.client.RemoteDisconnected as err:
            logger.error("Problem getting weather")
            logger.error(err)
            time.sleep(30)
            return self.nextupdate - time.time()

        self._payload = simplejson.loads(r.read())
        self._now = self._payload["current"]
        if time.localtime()[3] <= 5:      
            self.nextupdate = time.time() + (60 * 30) # Five minutes
        else:
            self.nextupdate = time.time() + (60 * 5) # Five minutes
        
    def night(self):
        if self._now["dt"] > (self._now["sunset"] + 1080) or self._now["dt"] < (self._now["sunrise"] - 1080):
            return True
        else:
            return False

    def icon(self):
        if self.night():
            phase = ((round(self._payload["daily"][0]["moon_phase"] * 8) + 11))
            moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (image_cache, phase))
            return moonImage.resize((30, 30), resample=Image.LANCZOS)
        else:
            icon = self._now["weather"][0]["icon"]
            url = "http://openweathermap.org/img/wn/%s.png" % (icon)
            filename = "%s/%s.png" % (image_cache, icon)
            if not os.path.isfile(filename):
                logger.info("Getting %s" % url)
                urllib.request.urlretrieve(url, filename)

            iconImage = Image.open(filename)
            iconImage = iconImage.crop((4, 4, 46, 46))
            return iconImage.resize((30, 30), resample=Image.LANCZOS)

    def hour(self, hour):
        return self._payload["hourly"][hour]

    def temp(self):
        return ktof(self._payload["current"]["temp"])

    def humidity(self):
        return self._payload["current"]["humidity"]

    def wind_speed(self):
        return self._payload["current"]["wind_speed"] * 2.237

    def pressure(self):
        return self._payload["current"]["pressure"] * 0.0295301

    def image(self):
        self._update()

        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        
        if self.night():
            skyColor = (0, 0, 0)
        else:
            skyColor = (128, 128, 255)

        draw.rectangle([(32,0),  (64, 32)], fill=(skyColor + (255 ,)))

        for x in range(24):
            hour = self.hour(x+1)
            t = time.localtime(hour["dt"])
            if t[3] == 0:
                draw.line([(26, x+4), (28, x+4)], fill=(64, 64, 64))
            if t[3] in [6, 18]:
                draw.line([(27, x+4), (29, x+4)], fill=(64, 64, 64))
            if t[3] == 12:
                draw.line([(28, x+4), (30, x+4)], fill=(64, 64, 64))

            diff = hour["temp"] - self.hour(x)["temp"]
            if diff > 1.0:
                draw.point((28, x+4), fill=(128, 64, 32))
            elif diff < -1.0:
                draw.point((28, x+4), fill=(32, 32, 128))
            else:
                draw.point((28, x+4), fill=(32, 32, 32))

        iconImage = self.icon()
        canvas.paste(iconImage, (33, 1), mask=iconImage)

        tempString = "%.0f°" % (self.temp())
        humidityString = "%.0f%%" % (self.humidity())
        windString = "%.0f mph" % (self.wind_speed())
        pressureString = "%.1f\"" % (self.pressure())

        txtImg = getTextImage([
                            (tempString, (1, -2), ttfFont, (192, 192, 128)),
                            (humidityString, (1, 7), ttfFont, (128, 192, 128)),
                            (windString, (1, 17), ttfFontSm, (128, 192, 192)),
                            (pressureString, (1, 24), ttfFontSm, (128, 128, 128))
                            ],
                            textColor)

        return Image.alpha_composite(canvas, txtImg).convert('RGB')

class Music:
    def __init__(self):
        self._spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                        client_secret=os.environ["SPOTIFY_SECRET"],
                                        cache_handler=CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, username)),
                                        redirect_uri="http://localhost:8080/callback",
                                        show_dialog=True,
                                        open_browser=False,
                                        scope="user-library-read,user-read-playback-state"))
        user = self._spotify.current_user()
        logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))
        self.nextupdate = 0
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
        except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as err:
            logger.error("Problem getting current_user_playing_track")
            logger.error(err)
            time.sleep(10)
            return self.nextupdate - time.time()

        if not self.nowplaying():
            if time.localtime()[3] <= 5:
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
            self.artist = ", ".join(map(lambda x: x["name"], self._nowplaying["item"]["artists"]))
            self.album_id = self._nowplaying["item"]["album"]["id"]
            self.track_id = self._nowplaying["item"]["id"]        
        return self.nextupdate - time.time()

def main():
    frame = Frame()
    weather = Weather()
    music = Music()

    lastSong = ""
    lastAlbum = ""
    firstRunThisSong = True
    firstRunThisAlbum = True

    while True:
        music._update()

        # We have a playing track.
        if music.nowplaying():
            nowPlaying = music._nowplaying
            if lastAlbum != music.album_id:
                lastAlbum = music.album_id
                firstRunThisAlbum = True
            else:
                firstRunThisAlbum = False

            if lastSong != music.track_id:
                logger.info(u'%s - %s' % (music.track, music.artist))
                lastSong = music.track_id
                firstRunThisSong = True
            else:
                firstRunThisSong = False

            try:
                image = processedImage(nowPlaying["item"]["album"]["images"][-1]["url"])
            except:
                image = processedImage(sp.artist(nowPlaying["item"]["artists"][0]["id"])["images"][0]["url"])

            if firstRunThisAlbum:
                canvas = Image.new('RGB', (64, 32), (0, 0, 0))
                for x in range(127):
                    imageDim = ImageEnhance.Brightness(image).enhance(x * 2 / 255.0)
                    canvas.paste(imageDim, (32, 0))
                    frame.swap(canvas)
                time.sleep(0.5)

            # Length of the longest line of text, in pixels.
            length = max(ttfFont.getsize(music.track)[0], ttfFont.getsize(music.artist)[0])

            # If either line of text is longer than the display, scroll
            if length >= frame.width:
                for x in range(length + frame.width + 10):
                    canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                    canvas.paste(image, (32, 0))
                    txtImg = getTextImage([
                            (music.track, (frame.width - x, 10)),
                            (music.artist, (frame.width - x, 20))
                        ], textColor)


                    frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))
                    time.sleep(0.025)

                time.sleep(1.25)

            # If all the text fits, don't scroll.
            else:
                if firstRunThisSong:
                    for x in range(127):
                        # Add an alpha channel to the color for fading in
                        textColorFade = textColor + (x * 2,)
                        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                        canvas.paste(image, (32, 0))

                        txtImg = getTextImage([(music.track, (0, 10)), (music.artist, (0, 20))], textColorFade)

                        frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))
                canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                canvas.paste(image, (32, 0))

                txtImg = getTextImage([(music.track, (0, 10)), (music.artist, (0, 20))], textColor)

                frame.swap(Image.alpha_composite(canvas, txtImg).convert('RGB'))
                time.sleep(2.0)

        # Nothing is playing
        else:
            if lastSong != "nothing playing":
                logger.info("Nothing playing...")
                lastSong = "nothing playing"

            weatherImage = weather.image()
            frame.swap(weatherImage.convert('RGB'))
            time.sleep(10)

main()
