#!/usr/bin/env python3

from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageEnhance, ImageFont, ImageDraw
import numpy

w=64
h=64
options = RGBMatrixOptions()
options.brightness = 100
options.hardware_mapping = "adafruit-hat-pwm"
options.rows = 64
options.cols = 64

matrix = RGBMatrix(options=options)
offscreen_canvas = matrix.CreateFrameCanvas()

def conway():
    global offscreen_canvas
    global matrix

    pixels = numpy.zeros((w, h), dtype=numpy.uint8)
    for i in range(w):
        for j in range(h):
            if numpy.random.randint(0, 2) == 1:
                pixels[i][j] = 255

    while True:
        canvas = Image.frombytes("L", (w, h), pixels.tobytes())
        print((canvas.width, canvas.height))
        offscreen_canvas.SetImage(canvas.convert("RGB"))
        offscreen_canvas = matrix.SwapOnVSync(offscreen_canvas)

        new_pixels = numpy.zeros((w, h), dtype=numpy.uint8)
        for i in range(w):
            for j in range(h):
                neighbors = 0
                for x in range(-1, 2):
                    for y in range(-1, 2):
                        if x == 0 and y == 0:
                            continue
                        if pixels[(i + x) % w][(j + y) % h]:
                            neighbors += 1
                if pixels[i][j]:
                    if neighbors == 2:
                        new_pixels[i][j] = 128
                    elif neighbors == 3:
                        new_pixels[i][j] = 128
                    # if neighbors == 2 or neighbors == 3:
                    #     new_pixels[i][j] = 255
                else:
                    if neighbors == 3:
                        new_pixels[i][j] = 64
        pixels = new_pixels

conway()