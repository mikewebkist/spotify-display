import spotipy
import time
import os
import os.path
from spotipy.oauth2 import SpotifyOAuth
import simplejson
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics
from PIL import Image, ImageEnhance
import urllib

def getImage(url):
    m = url.rsplit('/', 1)
    filename = "imagecache/%s" % m[-1]
    if not os.path.isfile(filename):
        print("Getting %s" % url)
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

matrix = RGBMatrix(options=options)

offscreen_canvas = matrix.CreateFrameCanvas()
font = graphics.Font()
font.LoadFont("font.bdf")
textColor = graphics.Color(128, 128, 128)
red = 0
green = 0
blue = 0

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                               client_secret=os.environ["SPOTIFY_SECRET"],
                                               redirect_uri="http://localhost:8080/callback",
                                               scope="user-library-read,user-read-playback-state"))

user = sp.current_user()
print("Now Playing for %s [%s]\n" % (user["display_name"], user["id"]))

while True:
    try:
        np = sp.current_user_playing_track()
    except simplejson.errors.JSONDecodeError:
        print("Problem caught...")
        print(simplejson.dumps(np))
        time.sleep(5)
        continue

    if np and np["is_playing"]:
        line1 = np["item"]["name"]
        line2 = np["item"]["album"]["name"]
        line3 = np["item"]["artists"][0]["name"]
        image = getImage(np["item"]["album"]["images"][1]["url"])
        image = ImageEnhance.Contrast(image).enhance(1.25)
        image = ImageEnhance.Brightness(image).enhance(0.3)
        image.show()

    else:
        line1 = "Nothing"
        line2 = ""
        line3 = "playing..."
        image = getImage("localhost:///cloud.png")

    length = max(graphics.DrawText(offscreen_canvas, font, 0, 20, textColor, line1),
                 graphics.DrawText(offscreen_canvas, font, 0, 30, textColor, line3))

    if length > offscreen_canvas.width:
        # If the text is wider than the view, scroll it.
        pos = offscreen_canvas.width
        timing = 10.0 / (length + offscreen_canvas.width)
        while pos + length > 0:
            offscreen_canvas.Clear()
            offscreen_canvas.Fill(red, green, blue)
            offscreen_canvas.SetImage(image.convert('RGB'), 32, 0)

            graphics.DrawText(offscreen_canvas, font, pos, 20, textColor, line1)
            graphics.DrawText(offscreen_canvas, font, pos, 30, textColor, line3)

            pos -= 1
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
            time.sleep(timing)

    else:
        # If all the text fits, don't scroll.
        offscreen_canvas.Clear()
        offscreen_canvas.Fill(red, green, blue)

        graphics.DrawText(offscreen_canvas, font, 0, 20, textColor, line1)
        graphics.DrawText(offscreen_canvas, font, 0, 30, textColor, line3)

        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
        time.sleep(5)

    pos = offscreen_canvas.width
