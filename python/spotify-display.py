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

ttfFont = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 10)
ttfFontSm = ImageFont.truetype("/usr/share/fonts/truetype/ttf-bitstream-vera/Vera.ttf", 7)
username = "mikewebkist"

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

image_cache = "%s/imagecache" % (basepath)

if len(sys.argv) > 1:
    username = sys.argv[1]

logging.basicConfig(filename='/tmp/spotify-matrix.log',level=logging.INFO)
logger = logging.getLogger(__name__)

options = RGBMatrixOptions()
options.brightness = 75
options.hardware_mapping = "adafruit-hat-pwm"
options.rows = 32
options.cols = 64
options.disable_hardware_pulsing = False
options.gpio_slowdown = 3

def gamma_builder(gamma_in):
    def gamma(value):
        return int(pow(value / 255, gamma_in) * 255)
    return gamma

gamma = gamma_builder(1.8)

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
    # Art looks slightly better with more contrast and a litte darker
    image = Image.eval(image, gamma)
    image = ImageEnhance.Color(image).enhance(0.5)
    # image = ImageEnhance.Contrast(image).enhance(0.95)
    image = ImageEnhance.Brightness(image).enhance(0.85)
    return image

def getTextImage(texts, color):
    txtImg = Image.new('RGBA', (options.cols, options.rows), (255, 255, 255, 0))
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

textColor = (gamma(192), gamma(192), gamma(192))
# textColor = (255, 255, 255)

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

def getWeatherImage():
    r = urllib.request.urlopen("https://api.openweathermap.org/data/2.5/onecall?lat=39.9623348&lon=-75.1927043&appid=%s" % (os.environ["OPENWEATHER_API"]))
    payload = simplejson.loads(r.read())
    now = payload["current"]
    icon = now["weather"][0]["icon"]
    logger.info(now["weather"][0]["main"])

    url = "http://openweathermap.org/img/wn/%s.png" % (icon)
    filename = "%s/%s.png" % (image_cache, icon)
    if not os.path.isfile(filename):
        logger.info("Getting %s" % url)
        urllib.request.urlretrieve(url, filename)

    canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Before sunrise
    if now["dt"] < now["sunrise"]:
        if (now["sunrise"] - now["dt"]) < 1080:
            dim = int(1080 - (now["sunrise"] - now["dt"]) / 1080.0 * 255.0)
            skyColor = (192, 128, 192) # Dawn is purple
        else:
            dim = 255
            skyColor = (0, 0, 0)
    # After sunset
    elif now["dt"] > now["sunset"]:
        if (now["dt"] - now["sunset"]) < 1080:
            dim = int(1080 - (now["dt"] - now["sunset"]) / 1080.0 * 255.0)
            skyColor = (255, 192, 128) # Sunset is orange
        else:
            dim = 255
            skyColor = (0, 0, 0)
    # Day
    else:
        dim = 255
        skyColor = (128, 128, 255)

    draw.rectangle([(32,0),  (64, 32)], fill=(skyColor + (dim ,)))

    for x in range(24):
        hour = payload["hourly"][x+1]
        t = time.localtime(hour["dt"])
        if t[3] == 0:
            draw.line([(26, x+4), (28, x+4)], fill=(64, 64, 64))
        if t[3] in [6, 18]:
            draw.line([(27, x+4), (29, x+4)], fill=(64, 64, 64))
        if t[3] == 12:
            draw.line([(28, x+4), (30, x+4)], fill=(64, 64, 64))

        diff = hour["temp"] - payload["hourly"][x]["temp"]
        if diff > 1.0:
            draw.point((28, x+4), fill=(128, 64, 32))
        elif diff < -1.0:
            draw.point((28, x+4), fill=(32, 32, 128))
        else:
            draw.point((28, x+4), fill=(32, 32, 32))

    phase = ((round(payload["daily"][0]["moon_phase"] * 8) + 11))

    if now["dt"] > (now["sunset"] + 1080) or (now["sunrise"] - 1080 ) > now["dt"]:
        iconImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (image_cache, phase))
        iconImage = iconImage.resize((30, 30), resample=Image.LANCZOS)
        iconImage = ImageEnhance.Brightness(iconImage).enhance(0.5)
        canvas.paste(iconImage, (33, 1), mask=iconImage)
    else:
        iconImage = Image.open(filename)
        iconImage = iconImage.resize((40, 40), resample=Image.LANCZOS)
        canvas.paste(iconImage, (28, -3), mask=iconImage)

    tempString = "%.0f°" % (ktof(now["temp"]))
    humidityString = "%.0f%%" % ((now["humidity"]))
    windString = "%.0f mph" % ((now["wind_speed"] * 2.237))
    pressureString = "%.1f\"" % ((now["pressure"] * 0.0295301))

    txtImg = getTextImage([(tempString, (1, -2), ttfFont, (192, 192, 128)),
                           (humidityString, (1, 7), ttfFont, (128, 192, 128)),
                           (windString, (1, 17), ttfFontSm, (128, 192, 192)),
                           (pressureString, (1, 24), ttfFontSm, (128, 128, 128))],
                           textColor)

    return Image.alpha_composite(canvas, txtImg).convert('RGB')

def main():
    matrix = RGBMatrix(options=options)
    cache_handler = CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, username))
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

            try:
                image = processedImage(nowPlaying["item"]["album"]["images"][-1]["url"])
            except:
                image = processedImage(sp.artist(nowPlaying["item"]["artists"][0]["id"])["images"][0]["url"])

            if firstRunThisAlbum:
                canvas = Image.new('RGB', (64, 32), (0, 0, 0))
                for x in range(127):
                    imageDim = ImageEnhance.Brightness(image).enhance(x * 2 / 255.0)
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
                    txtImg = getTextImage([
                            (trackName, (options.cols - x, 10)),
                            (artistName, (options.cols - x, 20))
                        ], textColor)

                    offscreen_canvas.SetImage(Image.alpha_composite(canvas, txtImg).convert('RGB'), 0, 0)
                    offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
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
                # Update every 30 minutes in the middle of the night, otherwise every five mins.
                if time.localtime()[3] <= 5:
                    weatherCooldownUntil = time.time() + 30 * 60.0
                else:
                    weatherCooldownUntil = time.time() + 5 * 60.0
                
            offscreen_canvas.SetImage(weatherImage.convert('RGB'), 0, 0)
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
            time.sleep(1.0)

main()
