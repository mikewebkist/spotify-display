import http
import math
import urllib
import simplejson
from datetime import datetime
import time
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops, ImageFilter, ImageOps
from hsluv import hsluv_to_rgb, hpluv_to_rgb
import sys
import os
from config import config
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def hpluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hpluv_to_rgb([h, s , v]))

def hsluv2rgb(h,s,v):
    return tuple(int(i * 256) for i in hsluv_to_rgb([h, s , v]))

def ktof(k):
    return (k - 273.15) * 1.8 + 32.0

class Weather:
    api_url = "https://api.openweathermap.org/data/2.5/onecall?lat=39.9623348&lon=-75.1927043&appid="
    
    def __init__(self, api_key=None, font=None, fontSm=None, fontLg=None, fontTime=None, image_cache=""):
        self.api_key = api_key
        self.image_cache = image_cache
        self.font = font
        self.fontSm = fontSm
        self.fontLg = fontLg
        self.fontTime = fontTime
    
    def _update(self):
        try:
            r = urllib.request.urlopen(self.api_url + self.api_key)
        except (http.client.RemoteDisconnected, urllib.error.URLError) as err:
            logger.error("Problem getting weather")
            logger.error(err)
            return 30

        self._payload = simplejson.loads(r.read())
        self._lastupdate= datetime.now().timestamp()
        self._now = self._payload["current"]

        # Update every 30 minutes overnight to save API calls
        if time.localtime()[3] <= 5:
            return 60 * 30
        else:
            return 60 * 10

    def night(self):
        if self._now["dt"] > (self._now["sunset"] + 1080) or self._now["dt"] < (self._now["sunrise"] - 1080):
            return True
        else:
            return False

    def icon(self):
        if self.night():
            skyColor = (0, 0, 0)
        else:
            clouds = self.clouds() / 100.0
            # skyColor = (0, 0, 32)
            skyColor = (int(clouds * 16), int(clouds * 16), 16)
            skyColor = (0, 0, 0)

        iconBox = Image.new('RGBA', (32, 32), skyColor)

        if self.night():
            phase = (((round(self._payload["daily"][0]["moon_phase"] * 8) % 8)  + 11))
            moonImage = Image.open("%s/Emojione_1F3%2.2d.svg.png" % (self.image_cache, phase)).resize((20,20))
            moonDim = ImageOps.expand(ImageEnhance.Brightness(moonImage).enhance(0.75), border=4, fill=(0,0,0,0))
            iconBox.alpha_composite(moonDim, dest=(2, -2))

        else:
            url = "http://openweathermap.org/img/wn/%s.png" % (self._now["weather"][0]["icon"])
            filename = "%s/weather-%s.png" % (self.image_cache, self._now["weather"][0]["icon"])
            if not os.path.isfile(filename):
                logger.info("Getting %s" % url)
                urllib.request.urlretrieve(url, filename)

            iconImage = Image.open(filename)
            iconImage = iconImage.crop((3, 3, 45, 45)).resize((32, 32))
            iconBox.alpha_composite(iconImage, dest=(0, -6))

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

    def clouds(self):
        return self._now["clouds"]

    def wind_speed(self):
        return "%.0f mph" % (self._payload["current"]["wind_speed"] * 2.237)

    # The screen is actually too low-res for this to look good
    def wind_dir(self):
        d = self._now["wind_deg"] - 45
        if d < 0:
            d = d + 360.0

        wind_dirs = ["N", "E", "S", "W"]
        return wind_dirs[int(d / 90)]

    def pressure(self):
        return "%.1f\"" % (self._payload["current"]["pressure"] * 0.0295301)

    def layout_text(self, lines):
        height = 0
        width = 0
        for text, color, font in lines:
            wh = font.getsize(text)
            width = max(width, wh[0])
            height = height + wh[1]

        txtImg = Image.new('RGBA', (width + 1, height + 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(txtImg)
        draw.fontmode = "1"
        y_pos = -1
        for text, color, font in lines:
            draw.text((1, y_pos + 1), text, (0,0,0), font=font)
            draw.text((0, y_pos),     text, color,   font=font)
            y_pos = y_pos + font.getsize(text)[1]
            if config["frame"].height < 64:
                y_pos = y_pos -1
        return txtImg

    def image(self):
        canvas = Image.new('RGBA', (64, 64), (0, 0, 0))
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

        iconImage = self.icon()
        # We're replaceing the entire right side of
        # the image, so no need for alpha blending
        canvas.paste(iconImage, (32, 6))

        # A little indicator of rain in the next hour. Each pixel represents two minutes.
        for m in range(32):
            try: # one time the payload didn't include minutely data...
                rain = self._payload["minutely"][2 * m]["precipitation"] + self._payload["minutely"][2 * m + 1]["precipitation"]
                if rain > 0.0:
                    draw.point((m, 0), fill=hsluv2rgb(231.0, 100.0, 50.0))
            except (KeyError, IndexError):
                pass

        txtImg = self.layout_text([ (self.temp(),       hsluv2rgb(69.0, 75.0, 75.0),  self.fontLg),
                                    (self.humidity(),   hsluv2rgb(139.9, 75.0, 50.0), self.fontSm),
                                    (self.wind_speed(), hsluv2rgb(183.8, 75.0, 50.0), self.fontSm),
                                    (self.pressure(),   hsluv2rgb(128.0, 0.0, 50.0),  self.fontSm) ])

        canvas.alpha_composite(txtImg, dest=(0, 1))

        if config["frame"].height > 32:
            mytime=datetime.now().strftime("%-I:%M")

            ts = datetime.now().timestamp()

            cycle_time = 120.0

            draw.rectangle([(2,40), (61,61)], fill=hpluv2rgb((ts % cycle_time) / cycle_time * 360.0, 100, 25))

            t_width = self.fontTime.getsize(mytime)[0]
            t_height = self.fontTime.getsize(mytime)[1]

            x_shadow = 2.0 * math.cos(math.radians((ts) % 360.0))
            y_shadow = 2.0 * math.sin(math.radians((ts) % 360.0))

            timeImg = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
            draw = ImageDraw.Draw(timeImg)
            draw.fontmode = None
            
            draw.text((32 - (t_width >> 1) + 2, 47 - (t_height >> 1) + 1),
                    mytime, hpluv2rgb((ts % cycle_time) / cycle_time * 360.0, 100, 5), font=self.fontTime)
            draw.text((32 - (t_width >> 1), 47 - (t_height >> 1)),
                    mytime, hpluv2rgb((ts % cycle_time) / cycle_time * 360.0, 50, 75), font=self.fontTime)

            canvas = Image.alpha_composite(canvas, timeImg)

        return canvas.convert('RGB')
