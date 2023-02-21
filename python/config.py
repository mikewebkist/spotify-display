import os
import sys
import configparser
import suntime
import datetime

# lat: 39.9623348
# lon: -75.1927043
def is_night():
    sun = suntime.Sun(39.9623348, -75.1927043)
    sunrise = sun.get_sunrise_time().timestamp()
    sunset = sun.get_sunset_time().timestamp()
    now = datetime.datetime.utcnow().timestamp()
    return now < sunrise or now > sunset

config = configparser.ConfigParser()
basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

if len(sys.argv) > 1:
    configfile = sys.argv[1]
else:
    configfile = "%s/local.config" % basepath

config.read(configfile)

image_cache = "%s/imagecache" % (basepath)
