import spotipy
import time
import os
from spotipy.oauth2 import SpotifyOAuth
import json
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
textColor = graphics.Color(0, 128, 0)
pos = offscreen_canvas.width

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                               client_secret=os.environ["SPOTIFY_SECRET"],
                                               redirect_uri="http://localhost:8080/callback",
                                               scope="user-library-read,user-read-playback-state"))

user = sp.current_user()
print("Now Playing for %s [%s]\n" % (user["display_name"], user["id"]))

while True:
    np = sp.current_user_playing_track()

    if np["is_playing"]:
        line1 = np["item"]["name"]
        line2 = np["item"]["album"]["name"]
        line3 = np["item"]["artists"][0]["name"]
    else:
        line1 = "Nothing"
        line2 = "playing..."
        line3 = ""

    length = max(graphics.DrawText(offscreen_canvas, font, pos, 9, textColor, line1),
                 graphics.DrawText(offscreen_canvas, font, pos, 19, textColor, line2),
                 graphics.DrawText(offscreen_canvas, font, pos, 29, textColor, line3))

    if length > pos:
        print("%d vs %d" % (length, pos))
        while pos + length > 0:
            offscreen_canvas.Clear()

            graphics.DrawText(offscreen_canvas, font, pos, 9, textColor, line1)
            graphics.DrawText(offscreen_canvas, font, pos, 19, textColor, line2)
            graphics.DrawText(offscreen_canvas, font, pos, 29, textColor, line3)

            pos -= 1
            time.sleep(0.07)
            offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
    else:
        print("%d vs %d" % (length, pos))
        offscreen_canvas.Clear()

        graphics.DrawText(offscreen_canvas, font, 2, 9, textColor, line1)
        graphics.DrawText(offscreen_canvas, font, 2, 19, textColor, line2)
        graphics.DrawText(offscreen_canvas, font, 2, 29, textColor, line3)

        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)
        time.sleep(5)

    pos = offscreen_canvas.width
