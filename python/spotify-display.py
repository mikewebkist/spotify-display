#!/usr/bin/env python3

import threading
from hsluv import hsluv_to_rgb, hpluv_to_rgb
import asyncio
from datetime import datetime
import logging
import time
from PIL import Image, ImageEnhance, ImageFont, ImageDraw
import weather as weatherimport
import music as musicimport
import frame as frameimport
from music import TrackError
from colorsys import rgb_to_hsv, hsv_to_rgb
import numpy
import config

# try:
#     devices = config["config"]["chromecast"]["devices"].split(", ")
# except KeyError:
#     devices = False

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)
  
def font(size):
    return ImageFont.truetype(config.config["fonts"]["time"], size)

def hpluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hpluv_to_rgb([h, s , v]))

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

def brighten(rgb):
    r, g, b = rgb
    h, s, v = rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
    v = min(1.0, v * 1.5)
    r, g, b = hsv_to_rgb(h, s, v)
    return (int(r * 255), int(g * 255), int(b * 255))

def getsize(bbox):
    return (bbox[2] - bbox[0], bbox[3] - bbox[1])

def small_clock():
    timeImg = Image.new('RGBA', (32, 32), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)
    color = brighten(weather.temp_color())
    draw.fontmode = None
    
    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%I")))
    draw.text((17 - (t_width >> 1), 5 - (t_height >> 1) + 1), datetime.now().strftime("%I"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 4 - (t_height >> 1) + 1), datetime.now().strftime("%I"), color, font=font(18))

    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%M")))
    draw.text((17 - (t_width >> 1), 20 - (t_height >> 1) + 1), datetime.now().strftime("%M"), (0,0,0), font=font(18))
    draw.text((16 - (t_width >> 1), 19 - (t_height >> 1) + 1), datetime.now().strftime("%M"), color, font=font(18))

    return timeImg

def clock():
    mytime=datetime.now().strftime("%-I:%M")

    timeImg = Image.new('RGBA', (64, 30), (0,0,0,0))

    draw = ImageDraw.Draw(timeImg)
    # draw.rectangle([(0,0), (64,30)], fill=config["weather"].temp_color())

    t_width = getsize(font(16).getbbox(mytime))[0]
    t_height = getsize(font(16).getbbox(mytime))[1]

    draw.fontmode = None
    draw.text((32 - (t_width >> 1) + 2, 10 - (t_height >> 1) + 2),
            mytime, (0,0,0,128), font=font(16))
    draw.text((32 - (t_width >> 1), 10 - (t_height >> 1)),
            mytime, brighten(weather.temp_color()), font=font(16))

    return timeImg

def conway(dimensions = (64,64)):
    w, h = dimensions
    gen = 0
    color_cycle = 50
    conway_color = [(0,0,0)] * color_cycle
    for t in range(color_cycle):
        r, g, b = hsluv_to_rgb([t * (360.0 / color_cycle), 50, 30])
        conway_color[t] = (int(r * 255), int(g * 255), int(b * 255))

    bitmap = [ numpy.zeros((w * h * 4), dtype=numpy.uint8),
               numpy.zeros((w * h * 4), dtype=numpy.uint8) ]

    for x in range(w * h):
        if numpy.random.randint(0, 5) == 1:
            bitmap[gen][x * 4]     = conway_color[int(time.time() - 5) % color_cycle][0]
            bitmap[gen][x * 4 + 1] = conway_color[int(time.time() - 5) % color_cycle][1]
            bitmap[gen][x * 4 + 2] = conway_color[int(time.time() - 5) % color_cycle][2]
            bitmap[gen][x * 4 + 3] = 255

    images = [  Image.frombuffer("RGBA", (w, h), bitmap[0]),
                Image.frombuffer("RGBA", (w, h), bitmap[1]) ]        


    while True:
        red, green, blue = conway_color[int(time.time()) % color_cycle]

        for z in range(w * h):
            z_s = z * 4
            neighbors = 0
            for g in [-1, 1, -w, w, -w-1, -w+1, w-1, w+1]:
                if bitmap[gen][((z + g) % (w * h)) * 4 + 3]:
                    neighbors += 1

            if bitmap[gen][z_s + 3]:
                if neighbors == 2 or neighbors == 3:
                    # Don't change the color if it's already on
                    bitmap[gen^1][z_s]     = bitmap[gen][z_s]
                    bitmap[gen^1][z_s + 1] = bitmap[gen][z_s + 1]
                    bitmap[gen^1][z_s + 2] = bitmap[gen][z_s + 2]
                    bitmap[gen^1][z_s + 3] = 255
                else:
                    bitmap[gen^1][z_s + 3] = 0

            else:
                if neighbors == 3 or neighbors == 6:
                    # Turn on a new cell with the current color
                    bitmap[gen^1][z_s]     = red
                    bitmap[gen^1][z_s + 1] = green
                    bitmap[gen^1][z_s + 2] = blue
                    bitmap[gen^1][z_s + 3] = 255
                else:
                    bitmap[gen^1][z_s + 3] = 0

        gen ^= 1

        if numpy.random.randint(0, 50) == 1:
            z = numpy.random.randint(0, h)
            for x in range(w):
                bitmap[gen][(z * w + x) * 4]     = 128
                bitmap[gen][(z * w + x) * 4 + 1] = 128
                bitmap[gen][(z * w + x) * 4 + 2] = 128
                bitmap[gen][(z * w + x) * 4 + 3] = 255
        # elif numpy.random.randint(0, 50) == 1:
        #     z = numpy.random.randint(0, w)
        #     for y in range(h):
        #         bitmap[gen][(z + y * w) * 4]     = 255
        #         bitmap[gen][(z + y * w) * 4 + 1] = 0
        #         bitmap[gen][(z + y * w) * 4 + 2] = 0
        #         bitmap[gen][(z + y * w) * 4 + 3] = 255

        yield images[gen]        

async def main():
    txtImg = None
    canvas = None

    while True:
        # We have a playing track.
        if music.nowplaying():
            
            if music.new_song():
                logger.warning("now playing song: %s (%s)" % (music.nowplaying().track, type(music.nowplaying())))
                txtImg = music.layout_text()

            # Fade in new album covers
            if music.new_album():
                try:
                    canvas = music.canvas()
                except TrackError as err:
                    logger.warning(err)
                    canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
                    canvas.paste(weather.weather_summary(), (0, 0))
                    canvas.paste(weather.icon(), (32, 0))
                    
                    
                logger.warning("now playing album: %s - %s" % (music.nowplaying().artist, music.nowplaying().album))
                for x in range(127):
                    bg = canvas.copy()
                    if txtImg.width < frame.width:
                        bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                    frame.swap(ImageEnhance.Brightness(bg).enhance(x * 2 / 255.0).convert('RGB'))
                    time.sleep(0.01) # Don't release thread until scroll is done

                await asyncio.sleep(0)

            # If either line of text is longer than the display, scroll
            if txtImg.width >= frame.width:
                for x in range(txtImg.width + 10 + frame.width):
                    bg = canvas.copy()
                    bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - txtImg.height))
                    frame.swap(bg.convert('RGB'))
                    time.sleep(0.01) # Don't release thread until scroll is done
                time.sleep(1.0)
            else:
                bg = canvas.copy()
                bg.alpha_composite(txtImg, dest=(0, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))

        # Nothing is playing
        elif weather._now: # because weather updates on a different thread, first run is tricky.
            weather_canvas = weather.w_canvas.copy()
            # On large screens, show a small clock and the planets 
            # or a big clock and conway's game of life if cloudy
            # or daytime
            if frame.square:
                if weather.night:
                    if int(weather._now["clouds"]) > 10:
                        weather_canvas.alpha_composite(next(conway_gen), (0, 34))
                        weather_canvas.alpha_composite(clock(), dest=(0,34))
                    else:
                        # p_canvas = weather.p_canvas.crop((t, 0, t + 128, 64)).resize((64, 32), resample=Image.Resampling.BILINEAR)
                        weather_canvas.alpha_composite(next(conway_gen), (0, 34))
                        # weather_canvas.alpha_composite(p_canvas, dest=(0,32))
                        weather_canvas.alpha_composite(small_clock(), dest=(32, 0))
                else:
                    weather_canvas.alpha_composite(next(conway_gen), (0, 34))
                    weather_canvas.alpha_composite(clock(), dest=(0,34))
            # On small screens, show a small clock over the weather icon
            else:
                weather_canvas.alpha_composite(small_clock(), dest=(32,0))
            
            frame.swap(weather_canvas.convert('RGB'))

        await asyncio.sleep(0)

async def update_weather():
    while True:
        delay = weather._update()
        await asyncio.sleep(delay)

async def update_weather_summary():
    while True:
        weather._update_summary()
        await asyncio.sleep(60)

async def update_chromecast():
    while True:
        delay = music.get_playing_chromecast()
        await asyncio.sleep(delay)

async def update_plex():
    while True:
        delay = music.get_playing_plex()
        await asyncio.sleep(delay)

async def update_heos():
    while True:
        delay = music.get_playing_heos()
        await asyncio.sleep(delay)

async def update_spotify():
    while True:
        delay = music.get_playing_spotify()
        await asyncio.sleep(delay)

async def fps_display():
    while True:
        frame.fps()
        await asyncio.sleep(60.0)

async def io_async():
    await asyncio.gather(
        update_weather(),
        update_weather_summary(),
        update_plex(),
        update_spotify(),
        update_chromecast(),
        update_heos(),
        main(),
        fps_display()
    )

async def main_async():
    await asyncio.gather(
        main()
    )

frame = frameimport.Frame()
weather = weatherimport.Weather()
music = musicimport.Music()
conway_gen = conway((64, 30))

# Run all the update code in it's own thread.
# io_thread = threading.Thread(target=lambda: asyncio.run(io_async()))
# io_thread.start()

asyncio.run(io_async())
# asyncio.run(main_async())

# main_thread = threading.Thread(target=lambda: asyncio.run(main_async()))
# main_thread.start()

# main_thread.join()
