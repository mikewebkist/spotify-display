import os
import sys
import configparser

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
