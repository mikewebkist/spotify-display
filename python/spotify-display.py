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
    timeImg = Image.new('RGBA', (64, 32), (0,0,0,0))
    draw = ImageDraw.Draw(timeImg)
    color = brighten(weather.temp_color())
    draw.fontmode = "1"
    
    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%I")))
    draw.text((49 - (t_width >> 1), 5 - (t_height >> 1) + 1), datetime.now().strftime("%I"), (0,0,0,192), font=font(17))
    draw.text((48 - (t_width >> 1), 4 - (t_height >> 1) + 1), datetime.now().strftime("%I"), color, font=font(17))

    t_width, t_height = getsize(font(18).getbbox(datetime.now().strftime("%M")))
    draw.text((49 - (t_width >> 1), 20 - (t_height >> 1) + 1), datetime.now().strftime("%M"), (0,0,0,192), font=font(17))
    draw.text((48 - (t_width >> 1), 19 - (t_height >> 1) + 1), datetime.now().strftime("%M"), color, font=font(17))

    return timeImg

def clock():
    mytime=None

    while True:
        now_time = datetime.now().strftime("%-I:%M")
        if now_time != mytime:
            timeImg = Image.new('RGBA', (64, 64), (0,0,0,0))
            mytime = now_time
        else:
            yield timeImg

        draw = ImageDraw.Draw(timeImg)

        t_width = getsize(font(18).getbbox(mytime))[0]
        t_height = getsize(font(18).getbbox(mytime))[1]
        # temp_color = weather.temp_color().append(255)
        temp_color = (128,128,128,255)

        draw.fontmode = None
        draw.rectangle((33 - (t_width >> 1), 48 - (t_height >> 1),
                        33 + (t_width >> 1), 48 + (t_height >> 1)),
                       fill=(0,0,0,0))

        draw.text((32 - (t_width >> 1) + 2, 44 - (t_height >> 1) + 2),
                mytime, (0,0,0,128), font=font(18))
        draw.text((32 - (t_width >> 1), 44 - (t_height >> 1)),
                mytime, temp_color, font=font(18))

        yield timeImg

def mandelbrot(c, max_iter):
    z = c
    for n in range(max_iter):
        if abs(z) > 2:
            return n
        z = z**2 + c

    return 0

def mandelbrot_set(in_xwidth, in_yheight, width, height, max_iter=64):
    xcenter = -0.74797
    ycenter = -0.072500001
    # xcenter = -0.75
    # ycenter = 0.1
    xwidth = in_xwidth
    yheight = in_yheight
    k=0

    image = Image.new('RGBA', (width, height), (0, 0, 0, 255))
    pixels = image.load()

    while True:
        color_shift = int(numpy.random.random() * max_iter)
        colormap = [ hsluv2rgb(((i + color_shift) % max_iter) * 360.0 / max_iter, 55, 20) for i in range(max_iter) ]
        colormap[0] = (0,0,0)
        colormap[-1] = (0,0,0)

        for k in range(75):
            xmin = xcenter - xwidth / 2
            xmax = xcenter + xwidth / 2
            ymin = ycenter - yheight / 2
            ymax = ycenter + yheight / 2

            r1 = numpy.linspace(xmin, xmax, width)
            r2 = numpy.linspace(ymin, ymax, height)
            for i in range(height):
                for j in range(width):
                    c = complex(r1[j], r2[i])
                    color = mandelbrot(c, max_iter)
                    if color == 0:
                        pixels[j, i] = (0,0,0)
                    else:
                        pixels[j, i] = colormap[color]
                    # pixels[j, i] = (color, color, color)

            yield image

            # Zoom in by 10%
            xwidth = xwidth * 0.975
            yheight = yheight * 0.975

            # Randomly move center by 0.1%
            xcenter = xcenter + (numpy.random.random() - 0.5) * 0.001 * xwidth
            ycenter = ycenter + (numpy.random.random() - 0.5) * 0.001 * yheight

        xwidth = in_xwidth
        yheight = in_yheight

def conway(dimensions = (64,64)):
    w, h = dimensions
    gen = 0
    color_cycle = 50
    conway_color = [(0,0,0)] * color_cycle
    for t in range(color_cycle):
        r, g, b = hsluv_to_rgb([t * (360.0 / color_cycle), 50, 40])
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
                bitmap[gen][(z * w + x) * 4]     = 192
                bitmap[gen][(z * w + x) * 4 + 1] = 64
                bitmap[gen][(z * w + x) * 4 + 2] = 64
                bitmap[gen][(z * w + x) * 4 + 3] = 255

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
                    frame.swap(ImageEnhance.Brightness(bg).enhance(x * 2 / 255.0).convert('RGB'))
                    time.sleep(0.01) # Don't release thread until scroll is done

                await asyncio.sleep(0)

            # If either line of text is longer than the display, scroll
            for x in range(txtImg.width + 10 + frame.width):
                bg = canvas.copy()
                bg.alpha_composite(txtImg, dest=(frame.width - x, frame.height - txtImg.height))
                frame.swap(bg.convert('RGB'))
                time.sleep(0.015) # Don't release thread until scroll is done
            time.sleep(1.0)

        # Nothing is playing
        elif weather._now: # because weather updates on a different thread, first run is tricky.
            weather_canvas = weather.w_canvas.copy()
            # On large screens, show a small clock and the planets 
            # or a big clock and conway's game of life if cloudy
            # or daytime
            if frame.square:
                if weather.night:
                    bg = Image.alpha_composite(frame.canvas, next(mandelbrot_gen))
                else:
                    bg = Image.alpha_composite(frame.canvas, next(conway_gen))

                out = Image.alpha_composite(Image.alpha_composite(bg, weather_canvas), next(clock_gen))
                frame.swap(out.convert('RGB'))

            # On small screens, show a small clock over the weather icon
            else:
                out = Image.alpha_composite(Image.alpha_composite(frame.canvas, weather_canvas.crop((0,0,64,32))), small_clock())
                frame.swap(out.convert('RGB'))
            

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
config.frame = frame
weather = weatherimport.Weather()
music = musicimport.Music()
conway_gen = conway((64, 64))
mandelbrot_gen = mandelbrot_set(3, 3, 64, 64)
clock_gen = clock()

# Run all the update code in it's own thread.
# io_thread = threading.Thread(target=lambda: asyncio.run(io_async()))
# io_thread.start()

asyncio.run(io_async())
# asyncio.run(main_async())

# main_thread = threading.Thread(target=lambda: asyncio.run(main_async()))
# main_thread.start()

# main_thread.join()
