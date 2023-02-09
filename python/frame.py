from rgbmatrix import RGBMatrix, RGBMatrixOptions
from PIL import Image, ImageEnhance, ImageFont, ImageDraw
import config
import logging
import time

logger = logging.getLogger(__name__)

class Frame:
    def __init__(self):
        self.options = RGBMatrixOptions()
        self.options.brightness = int(config.config["matrix"]["brightness"])
        self.options.hardware_mapping = "adafruit-hat-pwm"
        self.options.rows = int(config.config["matrix"]["height"])
        self.options.cols = int(config.config["matrix"]["width"])
        self.gamma = lambda value : round(pow(value / 255.0, float(config.config["matrix"]["gamma"])) * 255.0)
        
        self.count = 0
        self.t0 = time.time()

        self.matrix = RGBMatrix(options=self.options)
        self.offscreen_canvas = self.matrix.CreateFrameCanvas()
        self.width = self.options.cols - int(config.config["matrix"]["padding_left"])
        self.height = self.options.rows - int(config.config["matrix"]["padding_top"])
    
    @property
    def square(self):
        return self.options.cols == self.options.rows

    def swap(self, canvas):
        self.count += 1
        padding_left = int(config.config["matrix"]["padding_left"])
        padding_top = int(config.config["matrix"]["padding_top"])

        canvas = Image.eval(canvas, self.gamma)

        # if self.config.weather.night:
        #     canvas = ImageEnhance.Brightness(canvas).enhance(0.5)

        self.offscreen_canvas.SetImage(canvas, padding_left, padding_top)
        self.offscreen_canvas = self.matrix.SwapOnVSync(self.offscreen_canvas)

    def fps(self):
        t1 = time.time()
        logger.warning("FPS: %0.2f (%d in %0.2f secs)" % (self.count / (t1 - self.t0), self.count, (t1 - self.t0)))
        self.t0 = t1
        self.count = 0
