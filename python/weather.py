import http
import urllib
import simplejson
from datetime import datetime
import time
from PIL import Image, ImageEnhance, ImageDraw, ImageOps, ImageFont
from hsluv import hsluv_to_rgb, hpluv_to_rgb
import os
from config import config
import logging
from skyfield.api import load, N,S,E,W, wgs84
from pytz import timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

def layout_text(lines):
    height = 0
    width = 0
    for text, color, font in lines:
        wh = font.getsize(text)
        width = max(width, wh[0])
        height = height + wh[1]

    txtImg = Image.new('RGBA', (width + 1, height + 1), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txtImg)
    draw.fontmode = "1"
    y_pos = -2
    for text, color, font in lines:
        draw.text((1, y_pos + 1), text, (0,0,0), font=font)
        draw.text((0, y_pos),     text, color,   font=font)
        y_pos = y_pos + font.getsize(text)[1]
        if config["frame"].height < 64:
            y_pos = y_pos -1
    return txtImg
    
class Weather:
    api_url = "https://api.openweathermap.org/data/3.0/onecall?lat=39.9623348&lon=-75.1927043&appid="
    
    def __init__(self, api_key=None, image_cache=""):
        self.api_key = api_key
        self.image_cache = image_cache
    
    def font(self, size):
        return ImageFont.truetype(config["config"]["fonts"]["weather"], size)

    def _update(self):
        try:
            r = urllib.request.urlopen(self.api_url + self.api_key)
        except (http.client.RemoteDisconnected, urllib.error.URLError) as err:
            logger.error("Problem getting weather")
            logger.error(err)
            return 30

        self._payload = simplejson.loads(r.read())
        self._now = self._payload["current"]
        
        if self.hour(0)["pop"] > 0.0:
            return 60 * 5
        elif time.localtime()[3] <= 5:
            return 60 * 60
        else:
            return 60 * 15

    @property
    def night(self):
        return time.time() > self._now["sunset"] or time.time() < self._now["sunrise"]

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
                logger.info("Getting %s" % url)
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
        return ktof(self._payload["current"]["feels_like"]) > 90

    def icy(self):
        return ktof(self._payload["current"]["feels_like"]) < 32

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
        
        for x in range(24):
            t = time.localtime(self.hour(x+1)["dt"])
            if t[3] % 6 == 0:
                draw.line([(29, x+4), (31, x+4)], fill=hsluv2rgb(128.0,0.0,25.0))

            diff = self.hour(x)["temp"] - self.hour(0)["temp"]
            if diff > 1.0:
                draw.point((30, x+4), fill=hsluv2rgb(12.2, 100.0, 25.0))
            elif diff < -1.0:
                draw.point((30, x+4), fill=hsluv2rgb(231.0, 100.0, 25.0))
            else:
                draw.point((30, x+4), fill=hsluv2rgb(128.0, 0.0, 25.0))
            try:
                if self.hour(x)["rain"]['1h'] > 0.0:
                    draw.point((31, x+4), fill=hsluv2rgb(231.0, 100.0, 50.0))
                else:
                    draw.point((31, x+4), fill=hsluv2rgb(231.0, 0.0, 25.0))
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

        txtImg = layout_text([ (self.temp(),       hsluv2rgb(69.0, 75.0, 75.0),  self.font(12)),
                                (self.humidity(),   hsluv2rgb(139.9, 75.0, 50.0), self.font(7)),
                                (self.wind_speed(), hsluv2rgb(183.8, 75.0, 50.0), self.font(7)),
                                (self.pressure(),   hsluv2rgb(128.0, 0.0, 50.0),  self.font(7)) ])

        canvas.alpha_composite(txtImg, dest=(0, 1))

        return canvas

    def planets(self):
        ts = load.timescale()
        utc = timezone('US/Eastern')

        # Load the JPL ephemeris DE421 (covers 1900-2050).
        planets = load('de421.bsp')
        earth = planets['earth']
        philly = earth + wgs84.latlon(39.9623348 * N, 75.1927043 * W, elevation_m=10.59)

        # Supersampling at 2x
        canvas = Image.new('RGBA', (128, 64), (0, 0, 0))
        draw = ImageDraw.Draw(canvas)
        draw.line((32, 0, 32, 64), fill=(4,4,4))
        draw.line((64, 0, 64, 64), fill=(4,4,4))
        draw.line((96, 0, 96, 64), fill=(4,4,4))
        # draw.rectangle((0, 28, 64, 32), fill=(8,32,8))
        plot_planets = [ 
            ("moon", (128,128,128), 6), 
            ("mercury", (16,16,16), 1), 
            ("venus", (32,32,128), 2), 
            ("mars", (128,4,4), 2), 
            ("jupiter barycenter", (128,64,4), 3), 
            ("saturn barycenter", (128,128,4), 3)
            ]

        for planet_name, color, size in plot_planets:
            # this is going to be all sorts of messed up after midnight
            lines = []
            for t_local in range(self._payload["daily"][0]["sunset"], self._payload["daily"][1]["sunrise"], 60 * 60):
                dt_local = utc.localize(datetime.fromtimestamp(t_local))
                t = ts.from_datetime(dt_local)

                astrometric = philly.at(t).observe(planets[planet_name])
                alt, az, distance = astrometric.apparent().altaz()
                if alt.degrees > 0.0:
                    x = int(az.degrees * 128 / 360)
                    y = int(56 - (alt.degrees * 56 / 90))
                    lines.append((x, y))
            draw.line(lines, fill=(64,64,64), joint="curve")

        for planet_name, color, size in plot_planets:
            t = ts.now()
            astrometric = philly.at(t).observe(planets[planet_name])
            alt, az, distance = astrometric.apparent().altaz()

            if alt.degrees > 0.0:
                x = int(az.degrees * 128 / 360)
                y = int(56 - (alt.degrees * 56 / 90))
        
                if planet_name == "moon":
                    phase = (((round(self._payload["daily"][0]["moon_phase"] * 8) % 8) + 11))
                    moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (self.image_cache, phase)).resize((12,12))
                    moonDim = ImageEnhance.Brightness(moonImage).enhance(0.75)
                    canvas.alpha_composite(moonDim, dest=(x-6, y-6))
                else:
                    draw.ellipse((x-size, y-size, x+size, y+size), fill=color)

        return canvas.resize((64, 32), resample=Image.ANTIALIAS)

    def extreme(self):
        txtImg = Image.new('RGBA', (32, 32), (0, 0, 0, 0))
        if config["frame"].height < 64:
            icon = self.icon().resize((16,16))
            txtImg.paste(icon, (14,0))
        draw = ImageDraw.Draw(txtImg)
        draw.fontmode = None
        draw.text((2, 0), self.feelslike(), (255, 255, 255), font=self.font(7))
        return txtImg