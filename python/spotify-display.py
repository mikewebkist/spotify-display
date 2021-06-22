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

font = graphics.Font()
font.LoadFont("%s/font.bdf" % (basepath))

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
        logger.debug("Getting %s" % url)
        urllib.request.urlretrieve(url, filename)

    image = Image.open(filename)
    # Art looks slightly better with more contrast and a litte darker
    image = ImageEnhance.Contrast(image).enhance(1.5)
    image = ImageEnhance.Brightness(image).enhance(gamma(172) / 255.0)
    image = image.resize((32, 32), resample=Image.LANCZOS)

    return image

# ttfFont = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 10)
ttfFont = ImageFont.truetype("/usr/share/fonts/truetype/piboto/Piboto-Regular.ttf", 10)
textColor = (gamma(192), gamma(192), gamma(192))

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
            artistName = nowPlaying["item"]["artists"][0]["name"]
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
                for x in range(length + options.cols):
                    canvas = Image.new('RGB', (64, 32), (0, 0, 0))
                    canvas.paste(image, (32, 0))
                    draw = ImageDraw.Draw(canvas)
                    draw.text((options.cols - x, 10), trackName, textColor, font=ttfFont)
                    draw.text((options.cols - x, 20), artistName, textColor,  font=ttfFont)
                    offscreen_canvas.SetImage(canvas, 0, 0)
                    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                    time.sleep(0.025)

                time.sleep(1.5)

            # If all the text fits, don't scroll.
            else:
                if firstRunThisSong:
                    for x in range(127):
                        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
                        canvas.paste(image, (32, 0))

                        txt = Image.new('RGBA', canvas.size, (255, 255, 255, 0))
                        draw = ImageDraw.Draw(txt)
                        textColorFade = (gamma(192), gamma(192), gamma(192), x * 2)
                        draw.text((0, 10), trackName, fill=textColorFade, font=ttfFont)
                        draw.text((0, 20), artistName, fill=textColorFade, font=ttfFont)
                        offscreen_canvas.SetImage(Image.alpha_composite(canvas, txt).convert('RGB'), 0, 0)
                        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

                canvas = Image.new('RGB', (64, 32), (0, 0, 0))
                canvas.paste(image, (32, 0))
                draw = ImageDraw.Draw(canvas)
                draw.text((0, 10), trackName, textColor, font=ttfFont)
                draw.text((0, 20), artistName, textColor,  font=ttfFont)
                offscreen_canvas.SetImage(canvas, 0, 0)
                offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

                time.sleep(2.0)

        # Nothing is playing
        else:
            if lastSong != "nothing playing":
                logger.info("Nothing playing...")
                lastSong = "nothing playing"

            offscreen_canvas.Clear()
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
            time.sleep(1.0)

main()
