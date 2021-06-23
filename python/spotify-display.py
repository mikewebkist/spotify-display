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

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

username = "mikewebkist"

if len(sys.argv) > 1:
    username = sys.argv[1]

logging.basicConfig(filename='/tmp/spotify-matrix.log',level=logging.INFO)

logger = logging.getLogger(__name__)

options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat-pwm"
options.rows = 32
options.cols = 64
options.disable_hardware_pulsing = False
options.gpio_slowdown = 3

ttfFont = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 10)
# ttfFont = ImageFont.truetype("/home/pi/Downloads/Geneva Regular.ttf", 10)

cache_handler = CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, username))
image_cache = "%s/imagecache" % (basepath)

def gamma(value):
    gamma = 2.8
    max_in = 255
    max_out = 255
    return int(pow(value / max_in, gamma) * max_out)

def getImage(url):
    m = url.rsplit('/', 1)
    filename = "%s/%s" % (image_cache, m[-1])
    if not os.path.isfile(filename):
        logger.info("Getting %s" % url)
        urllib.request.urlretrieve(url, filename)

    image = Image.open(filename)
    # Art looks slightly better with more contrast and a litte darker
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = ImageEnhance.Brightness(image).enhance(gamma(172) / 255.0)
    image = image.resize((32, 32), resample=Image.LANCZOS)
    return image

def getTextImage(texts, color):
    txtImg = Image.new('RGBA', (options.cols, options.rows), (255, 255, 255, 0))
    draw = ImageDraw.Draw(txtImg)
    draw.fontmode = "1"
    for text, position in texts:
        (x, y) = position
        # Drop shadow
        draw.text((x - 1, y + 1), text, (0,0,0), font=ttfFont)
        draw.text((x,     y), text, color,   font=ttfFont)
    return txtImg

textColor = (gamma(192), gamma(192), gamma(192))

def getWeatherImage():
    r = urllib.request.urlopen("http://api.openweathermap.org/data/2.5/weather?id=4560349&appid=%s" % (os.environ["OPENWEATHER_API"]))
    payload = simplejson.loads(r.read())
    icon = payload["weather"][0]["icon"]
    logger.info(payload["weather"][0]["main"])

    url = "http://openweathermap.org/img/wn/%s@2x.png" % (icon)
    filename = "%s/%s" % (image_cache, icon)
    if not os.path.isfile(filename):
        logger.info("Getting %s" % url)
        urllib.request.urlretrieve(url, filename)

    canvas = Image.new('RGBA', (64, 32), (0, 0, 0))

    iconImage = Image.open(filename)
    iconImage = iconImage.resize((50, 50), resample=Image.BICUBIC)
    iconImage = ImageEnhance.Brightness(iconImage).enhance(gamma(192) / 255.0)
    canvas.paste(iconImage, (19, -9))

    tempString = "%.0f F" % ((payload["main"]["temp"] - 273.15) * 1.8 + 32)
    txtImg = getTextImage([(tempString, (5, 10))], textColor)
    return Image.alpha_composite(canvas, txtImg).convert('RGB')

def main():
    matrix = RGBMatrix(options=options)
    offscreen_canvas = matrix.CreateFrameCanvas()


    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                                   client_secret=os.environ["SPOTIFY_SECRET"],
                                                   cache_handler=cache_handler,
                                                   redirect_uri="http://localhost:8080/callback",
                                                   show_dialog=True,
                                                   open_browser=False,
                                                   scope="user-library-read,user-read-playback-state"))

    user = sp.current_user()
    logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))

    weatherImage = None
    weatherCooldownUntil = time.time()
    cooldownUntil = time.time() * 1000.0
    nowPlaying = None
    lastSong = ""
    lastAlbum = ""
    firstRunThisSong = True
    firstRunThisAlbum = True

    while True:

        if (time.time() * 1000.0) > cooldownUntil:
            # Try getting the current track.
            try:
                nowPlaying = sp.current_user_playing_track()
                if nowPlaying and nowPlaying["is_playing"] and nowPlaying["item"]:
                    # For the first 30 seconds of the song, check every 3 seconds.
                    if nowPlaying["progress_ms"] < (30.0 * 1000):
                        cooldownUntil = (time.time() + 3) * 1000.0
                    # At the end of the song, try to time it close.
                    elif (nowPlaying["item"]["duration_ms"] - nowPlaying["progress_ms"]) < (30.0 * 1000.0):
                        cooldownUntil = (time.time() * 1000.0) + (nowPlaying["item"]["duration_ms"] - nowPlaying["progress_ms"])
                    # Otherwise, try every 10 seconds while playing.
                    else:
                        cooldownUntil = (time.time() * 1000.0) + (10.0 * 1000.0)
                else:
                    cooldownUntil = (time.time() + 30) * 1000.0

            except (requests.exceptions.ReadTimeout, requests.exceptions.ConnectionError) as err:
                logger.error("Problem getting current_user_playing_track")
                logger.error(err)
                time.sleep(30)
                continue
        else:
            logger.debug("not checking the track for %0.2f secs" % ((cooldownUntil - time.time() * 1000.0) / 1000.0))

        # We have a playing track.
        if nowPlaying and nowPlaying["is_playing"] and nowPlaying["item"]:
            trackName = nowPlaying["item"]["name"]
            artistName = ", ".join(map(lambda x: x["name"], nowPlaying["item"]["artists"]))
            if lastAlbum != nowPlaying["item"]["album"]["id"]:
                lastAlbum = nowPlaying["item"]["album"]["id"]
                firstRunThisAlbum = True
            else:
                firstRunThisAlbum = False

            if lastSong != nowPlaying["item"]["id"]:
                logger.info(u'%s - %s' % (trackName, artistName))
                lastSong = nowPlaying["item"]["id"]
                firstRunThisSong = True
            else:
                firstRunThisSong = False

            image = getImage(nowPlaying["item"]["album"]["images"][1]["url"])

            if firstRunThisAlbum:
                canvas = Image.new('RGB', (64, 32), (0, 0, 0))
                for x in range(127):
                    imageDim = ImageEnhance.Brightness(image).enhance(gamma(x * 2) / 255.0)
                    canvas.paste(imageDim, (32, 0))
                    offscreen_canvas.SetImage(canvas, 0, 0)
                    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                time.sleep(0.5)

            # Length of the longest line of text, in pixels.
            length = max(ttfFont.getsize(trackName)[0], ttfFont.getsize(artistName)[0])

            # If either line of text is longer than the display, scroll
            if length >= options.cols:
                for x in range(length + options.cols + 10):
                    canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                    canvas.paste(image, (32, 0))
                    txtImg = getTextImage([(trackName, (options.cols - x, 10)),
                                           (artistName, (options.cols - x, 20))], textColor)

                    offscreen_canvas.SetImage(Image.alpha_composite(canvas, txtImg).convert('RGB'), 0, 0)
                    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                    time.sleep(0.025)

                time.sleep(1.25)

            # If all the text fits, don't scroll.
            else:
                if firstRunThisSong:
                    for x in range(127):
                        textColorFade = (gamma(192), gamma(192), gamma(192), x * 2)
                        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                        canvas.paste(image, (32, 0))

                        txtImg = getTextImage([(trackName, (0, 10)), (artistName, (0, 20))], textColorFade)

                        offscreen_canvas.SetImage(Image.alpha_composite(canvas, txtImg).convert('RGB'), 0, 0)
                        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

                        # offscreen_canvas.SetImage(ImageChops.logical_xor(canvas, txt).convert('RGB'), 0, 0)
                canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                canvas.paste(image, (32, 0))

                txtImg = getTextImage([(trackName, (0, 10)), (artistName, (0, 20))], textColor)

                offscreen_canvas.SetImage(Image.alpha_composite(canvas, txtImg).convert('RGB'), 0, 0)
                offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

                time.sleep(2.0)

        # Nothing is playing
        else:
            if lastSong != "nothing playing":
                logger.info("Nothing playing...")
                lastSong = "nothing playing"

            if weatherImage == None or weatherCooldownUntil < time.time():
                logger.info("%d %d" % (weatherCooldownUntil, time.time()))
                weatherImage = getWeatherImage()
                weatherCooldownUntil = time.time() + 5 * 60.0
                
            offscreen_canvas.SetImage(weatherImage.convert('RGB'), 0, 0)
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
            time.sleep(1.0)

main()
