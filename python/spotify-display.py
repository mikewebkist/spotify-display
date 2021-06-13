import spotipy
import logging
import time
import os
import os.path
from spotipy.oauth2 import SpotifyOAuth
import simplejson
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageEnhance
import urllib

logging.basicConfig(level=logging.WARNING)


logger = logging.getLogger(__name__)

def getImage(url):
    m = url.rsplit('/', 1)
    filename = "imagecache/%s" % m[-1]
    if not os.path.isfile(filename):
        logger.debug("Getting %s" % url)
        urllib.urlretrieve(url, filename)

    image = Image.open(filename)
    image.thumbnail((32, 32), Image.NEAREST)
    return image

# --led-no-hardware-pulse=1 --led-cols=64 --led-rows=32 --led-gpio-mapping=adafruit-hat

options = RGBMatrixOptions()
options.hardware_mapping = "adafruit-hat"
options.rows = 32
options.cols = 64
options.disable_hardware_pulsing = True

font = graphics.Font()
font.LoadFont("font.bdf")
textColor = graphics.Color(128, 128, 128)
red = 0
green = 0
blue = 0

def main():
    matrix = RGBMatrix(options=options)
    offscreen_canvas = matrix.CreateFrameCanvas()

    logging.warning("testing...")
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                                   client_secret=os.environ["SPOTIFY_SECRET"],
                                                   redirect_uri="http://localhost:8080/callback",
                                                   show_dialog=True,
                                                   open_browser=False,
                                                   scope="user-library-read,user-read-playback-state"))

    print("I think it's logged in...")
    user = sp.current_user()
    print("Now Playing for %s [%s]\n" % (user["display_name"], user["id"]))

    # Default pause between iterations is 10 seconds
    not_playing_wait = 1.0
    while True:
        try:
            np = sp.current_user_playing_track()
        except:
            print("Problem caught...")
            print(simplejson.dumps(np))
            time.sleep(30)
            continue

        if np and np["is_playing"]:
            not_playing_wait = 1.0

            line1 = np["item"]["name"]
            line2 = np["item"]["album"]["name"]
            line3 = np["item"]["artists"][0]["name"]
            print("%s - %s" % (line1, line3))

            # Default delay is 10% of the remaining song length
            ms_remain = np["item"]["duration_ms"] - np["progress_ms"]
            if ms_remain < 20000.0:
                ms_pause = ms_remain
            else:
                ms_pause = np["item"]["duration_ms"] / 10.0

            print("  %d of %d. Pause for %0.2f secs." % (ms_remain, np["item"]["duration_ms"], ms_pause / 1000))

            # Art looks slightly better with more contrast and a litte darker
            image = getImage(np["item"]["album"]["images"][1]["url"])
            image = ImageEnhance.Contrast(image).enhance(1.25)
            image = ImageEnhance.Brightness(image).enhance(0.3)
            image.show()

            # Length of the longest line of text, in pixels.
            length = max(graphics.DrawText(offscreen_canvas, font, 0, 20, textColor, line1),
                         graphics.DrawText(offscreen_canvas, font, 0, 30, textColor, line3))

            # If either line of text is longer than the display, scroll
            if length > options.cols:
                # Set speed to scroll text fully in 5 seconds
                # timing = 5.0 / (length + options.cols)
                doneAt = time.time() * 1000.0 + ms_pause

                timing = 0.02
                print("%4.f" % (time.time()))
                # timing = ms_pause / 1000.0 / (length + options.cols)

                while (time.time() * 1000.0 < doneAt):
                    for x in range(length + options.cols):
                        offscreen_canvas.Fill(red, green, blue)
                        offscreen_canvas.SetImage(image.convert('RGB'), 32, 0)

                        graphics.DrawText(offscreen_canvas, font, options.cols - x, 20, textColor, line1)
                        graphics.DrawText(offscreen_canvas, font, options.cols - x, 30, textColor, line3)

                        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                        time.sleep(timing)
                    time.sleep(1.5)

            # If all the text fits, don't scroll.
            else:
                offscreen_canvas.Fill(red, green, blue)
                offscreen_canvas.SetImage(image.convert('RGB'), 32, 0)

                graphics.DrawText(offscreen_canvas, font, 0, 20, textColor, line1)
                graphics.DrawText(offscreen_canvas, font, 0, 30, textColor, line3)

                offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
                time.sleep(ms_pause / 1000.0)

            # time.sleep(ms_pause / 1000.0)

        # Nothing is playing
        else:
            offscreen_canvas.Clear()
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

            print("Nothing playing...Sleep for %0.2f secs" % (not_playing_wait))
            time.sleep(not_playing_wait)

            not_playing_wait *= 2
            if not_playing_wait > 360.0:
                not_playing_wait = 360.0

main()
