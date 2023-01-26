import http
import urllib
import simplejson
import time
from PIL import Image, ImageEnhance, ImageDraw, ImageFont
from hsluv import hsluv_to_rgb
from colorsys import rgb_to_hsv, hsv_to_rgb
import os
from config import config
import logging
from skyfield.api import load, N,W, wgs84
from pytz import timezone
from datetime import datetime

logger = logging.getLogger(__name__)

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

def temp_color(temp):
    temp = ktof(temp)
    if temp < 25:
        return (57,81,127)
    elif temp < 30:
        return (47,71,117)
    elif temp < 35:
        return (38,67,111)
    elif temp < 40:
        return (37,79,119)
    elif temp < 45:
        return (39,91,128)
    elif temp < 50:
        return (39,103,138)
    elif temp < 55:
        return (40,117,147)
    elif temp < 60:
        return (67,129,144)
    elif temp < 70:
        return (155,153,106)
    elif temp < 90:
        return (175,91,60)
    else:
        return (139,23,60)

class Weather:
    api_url = "https://api.openweathermap.org/data/3.0/onecall?lat=39.9623348&lon=-75.1927043&appid="
    
    def __init__(self, api_key=None, image_cache=""):
        self.api_key = api_key
        self.image_cache = image_cache
        self.p_canvas = None
        self.w_canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
    
    def font(self, size):
        return ImageFont.truetype(config["config"]["fonts"]["weather"], size)

    def _update(self):
        try:
            r = urllib.request.urlopen(self.api_url + self.api_key)
        except (http.client.RemoteDisconnected, urllib.error.URLError) as err:
            logger.error("Problem getting weather :%s" % err)
            return 30

        self._payload = simplejson.loads(r.read())
        self._now = self._payload["current"]
        self.p_canvas = self.planets()
        
        if self.hour(0)["pop"] > 0.0:
            return 60 * 5
        elif time.localtime()[3] <= 5:
            return 60 * 60
        else:
            return 60 * 15

    def _update_summary(self):
        self.w_canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
        
        # Weather summary is always displayed
        self.w_canvas.alpha_composite(self.weather_summary(), (0, 0))
        self.w_canvas.alpha_composite(self.icon(), (32, 0))

    @property
    def night(self):
        return time.time() > self._now["sunset"] or time.time() < self._now["sunrise"]

    def temp_color(self):
        if self.steamy() or self.icy():
            return temp_color(ktof(self._payload["current"]["feels_like"]))
        else:
            return temp_color(ktof(self._payload["current"]["temp"]))
        
    def icon(self):
        iconBox = Image.new('RGBA', (32, 32), (0, 0, 0))

        if self.night:
            phase = (round(self._payload["daily"][0]["moon_phase"] * 8) % 8) + 11
            moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (self.image_cache, phase)).resize((20,20))
            moonDim = ImageEnhance.Brightness(moonImage).enhance(0.75)
            iconBox.alpha_composite(moonDim, dest=(6, 6))

        else:
            url = "http://openweathermap.org/img/wn/%s.png" % (self._now["weather"][0]["icon"])
            filename = "%s/weather-%s.png" % (self.image_cache, self._now["weather"][0]["icon"])
            if not os.path.isfile(filename):
                logger.warn("Getting %s" % url)
                urllib.request.urlretrieve(url, filename)

            iconImage = Image.open(filename)
            iconImage = iconImage.crop((3, 3, 45, 45)).resize((32, 32))
            iconBox.alpha_composite(iconImage, dest=(0, 0))

        return iconBox

    def hour(self, hour):
        return self._payload["hourly"][hour]

    def temp(self):
        return "%.0f°" % ktof(self._payload["current"]["temp"])

    # If the "feels_like" temp is over 80 it's probably steamy outside
    def steamy(self):
        return ktof(self._payload["current"]["feels_like"]) > 85

    def icy(self):
        return ktof(self._payload["current"]["feels_like"]) < 33

    def feelslike(self):
        if self.steamy() or self.icy():
            return "~%.0f°" % ktof(self._payload["current"]["feels_like"])
        else:
            return self.temp()

    def humidity(self):
        return "%.0f%%" % self._payload["current"]["humidity"]

    def wind_speed(self):
        return "%.0f mph" % (self._payload["current"]["wind_speed"] * 2.237)

    def pressure(self):
        return "%.1f\"" % (self._payload["current"]["pressure"] * 0.0295301)

    def weather_summary(self):
        canvas = Image.new('RGBA', (64, 32), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.fontmode = "1"

        h, s, v = rgb_to_hsv(*map(lambda x: x / 255.0, self.temp_color()))
        fg_color = tuple(map(lambda x: int(x*255.0), hsv_to_rgb(h, s, (v + 0.25) % 1.0)))
        bg_color = tuple(map(lambda x: int(x*255.0), hsv_to_rgb(h, s, (v - 0.25) % 1.0)))

        draw.text((0,1), self.temp(), fill=fg_color, font=self.font(13), stroke_width=2, stroke_fill=bg_color)
        text = self.humidity() + "\n" + self.wind_speed() + "\n" + self.pressure()
        draw.multiline_text((1, 13), text, fill=(128, 128, 128), font=self.font(8), spacing=0)
        
        for x in range(24):
            t = time.localtime(self.hour(x+1)["dt"])
            if t[3] % 6 == 0:
                draw.line([(29, x+4), (31, x+4)], fill=hsluv2rgb(128.0,0.0,25.0))

            draw.point((30, x+4), fill=temp_color(self.hour(x)["temp"]))

            try:
                if self.hour(x)["rain"]['1h'] > 0.0:
                    draw.point((31, x+4), fill=hsluv2rgb(231.0, 100.0, 50.0))
            except KeyError:
                pass

        # A little indicator of rain in the next hour. Each pixel represents two minutes.
        for m in range(32):
            try: # one time the payload didn't include minutely data...
                rain = self._payload["minutely"][2 * m]["precipitation"] + self._payload["minutely"][2 * m + 1]["precipitation"]
                if rain > 0.0:
                    draw.point((m, 0), fill=hsluv2rgb(231.0, 100.0, 50.0))
                else:
                    draw.point((m, 0), fill=hsluv2rgb(231.0, 0.0, 10.0))

            except (KeyError, IndexError):
                pass

        return canvas

    def planets(self):
        ts = load.timescale()
        utc = timezone('US/Eastern')

        # Load the JPL ephemeris DE421 (covers 1900-2050).
        planets = load('de421.bsp')
        earth = planets['earth']
        philly = earth + wgs84.latlon(39.9623348 * N, 75.1927043 * W, elevation_m=10.59)

        # Supersampling at 2x
        canvas = Image.new('RGBA', (256, 64), (0, 0, 32))
        draw = ImageDraw.Draw(canvas)
        # draw.fontmode = None

        draw.text((2+0,   0), "N", (255,255,255), font=self.font(14))
        draw.text((2+64,  0), "E", (255,255,255), font=self.font(14))
        draw.text((2+128, 0), "S", (255,255,255), font=self.font(14))
        draw.text((2+192, 0), "W", (255,255,255), font=self.font(14))

        draw.line((0,   0, 0,   64), fill=(255,255,255))
        draw.line((64,  0, 64,  64), fill=(255,255,255))
        draw.line((128, 0, 128, 64), fill=(255,255,255))
        draw.line((192, 0, 192, 64), fill=(255,255,255))

        plot_planets = [ 
            ("venus", (32,32,128), 1), 
            ("mars", (128,32,32), 1), 
            ("jupiter barycenter", (128,64,32), 3), 
            ("saturn barycenter", (32,128,32), 3),
            ("moon", (128,128,128), 6), 
            ]

        for planet_name, color, size in plot_planets:
            t = ts.now()
            astrometric = philly.at(t).observe(planets[planet_name])
            alt, az, distance = astrometric.apparent().altaz()

            if alt.degrees > 0.0:
                x = int(az.degrees / 360.0 * 256)
                y = int(64 - (alt.degrees / 80.0 * 64))
                if planet_name == "moon":
                    phase = (((round(self._payload["daily"][0]["moon_phase"] * 8) % 8) + 11))
                    moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (self.image_cache, phase)).resize((12,12))
                    moonDim = ImageEnhance.Brightness(moonImage).enhance(0.75)
                    canvas.alpha_composite(moonDim, dest=(x-6, y-6))
                else:
                    if planet_name == "saturn barycenter":
                        draw.ellipse((x-3*size, y-1, x+3*size, y+1), fill=(128,128,128))

                    draw.line((x - 2 * size, y, x + 2 * size, y), fill=color, width=1)
                    draw.ellipse((x-size, y-size, x+size, y+size), fill=color)

        # return canvas.resize((128, 32), resample=Image.ANTIALIAS)
        p_canvas = Image.new('RGBA', (512, 64), (0, 0, 0))
        p_canvas.alpha_composite(canvas, dest=(0,0))
        p_canvas.alpha_composite(canvas, dest=(256,0))

        return p_canvas

    def extreme(self):
        txtImg = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        if not config["frame"].square:
            icon = self.icon().resize((16,16))
            txtImg.alpha_composite(icon, dest=(14,0))
        draw = ImageDraw.Draw(txtImg)
        draw.fontmode = "1"
        draw.text((2, 0), self.feelslike(), self.temp_color(), font=self.font(9))
        return txtImg
