import spotipy
import time
import os
from spotipy.oauth2 import SpotifyOAuth
import simplejson
from rgbmatrix import RGBMatrix, RGBMatrixOptions, graphics

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
textColor = graphics.Color(64, 0, 0)
red = 0
green = 0
blue = 0

pos = offscreen_canvas.width

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
        print("%s" % np["item"]["album"]["images"][2]["url"])
    else:
        line1 = "Nothing"
        line2 = ""
        line3 = "playing..."

    length = max(graphics.DrawText(offscreen_canvas, font, pos, 15, textColor, line1),
                 graphics.DrawText(offscreen_canvas, font, pos, 25, textColor, line3))

    if length > pos:
        # If the text is wider than the view, scroll it.
        while pos + length > 0:
            offscreen_canvas.Clear()
            offscreen_canvas.Fill(red, green, blue)

            graphics.DrawText(offscreen_canvas, font, pos, 15, textColor, line1)
            graphics.DrawText(offscreen_canvas, font, pos, 25, textColor, line3)

            pos -= 1
            time.sleep(0.07)
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

    else:
        # If all the text fits, don't scroll.
        offscreen_canvas.Clear()
        offscreen_canvas.Fill(red, green, blue)

        graphics.DrawText(offscreen_canvas, font, 2, 15, textColor, line1)
        graphics.DrawText(offscreen_canvas, font, 2, 25, textColor, line3)

        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
        time.sleep(5)

    pos = offscreen_canvas.width
