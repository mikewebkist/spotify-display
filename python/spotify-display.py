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
options.chain_length = 1
options.parallel = 1
options.row_address_type = 0
options.multiplexing = 0
options.pwm_bits = 11
options.brightness = 100
options.pwm_lsb_nanoseconds = 130
options.led_rgb_sequence = "RGB"
options.pixel_mapper_config = ""
options.panel_type = ""
options.disable_hardware_pulsing = True

matrix = RGBMatrix(options=options)

offscreen_canvas = matrix.CreateFrameCanvas()
font = graphics.Font()
font.LoadFont("Commodore_ruby_12.bdf")
textColor = graphics.Color(255, 255, 255)
pos = offscreen_canvas.width

while True:
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                                   client_secret=os.environ["SPOTIFY_SECRET"],
                                                   redirect_uri="http://localhost:8080/callback",
                                                   scope="user-library-read,user-read-playback-state"))

    user = sp.current_user()
    print("Now Playing for %s [%s]\n" % (user["display_name"], user["id"]))

    np = sp.current_user_playing_track()

    if np["is_playing"]:
        print("\n%s\n%s\n%s\n" % (np["item"]["album"]["name"], np["item"]["name"], np["item"]["artists"][0]["name"] ))

    while pos > 0:
        offscreen_canvas.Clear()
        len = graphics.DrawText(offscreen_canvas, font, pos, 10, textColor, np["item"]["name"])
        pos -= 1
        time.sleep(0.05)
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

    pos = offscreen_canvas.width

# print(json.dumps(np))
