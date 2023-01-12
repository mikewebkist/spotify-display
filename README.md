# spotify-display

# Hardware:

* Raspberry Pi (3 or 4 work best)
* Adafruit [RGB Matrix Bonnet](https://www.adafruit.com/product/3211) for Raspberry Pi
* LED matrix supported by [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix) – I like the [2mm pitch 64x64](https://www.adafruit.com/product/5362) from Adafruit
* LED matrix [power supply](https://www.adafruit.com/product/1466) which can also power the Pi via the bonnet.

# Software:
* I run using [pyenv](https://github.com/pyenv/pyenv) because updating the system Python is death sentence. 
* [rpi-rgb-led-matrix](https://github.com/hzeller/rpi-rgb-led-matrix): Get the demo working before anything else.

sudo ./demo --led-no-hardware-pulse --led-gpio-mapping=adafruit-hat-pwm --led-rows=32 --led-cols=64 -D7
