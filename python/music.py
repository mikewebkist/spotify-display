import pychromecast
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
import os
import sys
import logging
import PIL
from PIL import Image, ImageEnhance, ImageDraw, ImageOps, ImageStat, ImageFont
import urllib
import requests
from plexapi.server import PlexServer
import plexapi
import random
from datetime import datetime
from time import time
from config import config
from heospy import HeosPlayer

logger = logging.getLogger(__name__)

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

image_cache = "%s/imagecache" % (basepath)

class TrackError(Exception):
    pass

class Track:
    def __init__(self):
        self.art_url = None
        self.label = None
        self.year = None
        self.checktime = time()
        self._album_id = None
        self._track_id = None
        self.duration = -1
        self.progress = -1

    @property
    def album_id(self):
        return self._album_id or f"{self.album}/{self.artist}"

    @property
    def track_id(self):
        return self._track_id or f"{self.track}/{self.artist}/{self.album}"

    @property
    def data_age(self):
        return time() - self.checktime

    @property
    def timeleft(self):
        if self.duration < 0 or self.progress < 0:
            return -1
        else:
            return self.duration - self.progress - self.data_age

    @property
    def timein(self):
        if self.duration < 0 or self.progress < 0:
            return -1
        else:
            return self.progress + self.data_age

    def recheck_in(self):
        if self.timeleft < 0:
            return 5.0
        elif self.progress < 15.0:
            return 1.0
        elif self.timeleft > 30.0:
            return 5.0
        elif self.timeleft > 5.0:
            return self.timeleft
        else:
            return 1.0

    def get_image(self):
        if not self.art_url:
            raise TrackError(f"No art_url set {self.track} {self}")
        else:
            url = self.art_url

        m = url.rsplit('/', 1)
        processed = "%s/%s-%s.png" % (image_cache, self.__class__.__name__, m[-1])
        try:
            if (time() - os.path.getmtime(processed)) < (7 * 24 * 60 * 60):
                return Image.open(processed)
            else:
                os.remove(processed)
        except OSError:
            pass

        try:
            with urllib.request.urlopen(url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(64,64), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")
                return image
        except urllib.error.URLError as err:
            raise TrackError(f"Can't get image: {err} {self.track} {self}")

    @property
    def image(self):
        image = self.get_image()

        avg = sum(ImageStat.Stat(image).sum) / sum(ImageStat.Stat(image).count)
        max = 250.0
        if avg > max:
            logger.warning(f"Image too bright for the matrix: {avg:.0f}")
            image = ImageEnhance.Brightness(image).enhance(max / avg)

        if not config["frame"].square:
            cover = Image.new('RGBA', (64, 32), (0,0,0))
            cover.paste(image.resize((config["frame"].height, config["frame"].height), Image.LANCZOS), (64 - config["frame"].height,0))
            image = cover.convert('RGBA')

        image = ImageEnhance.Color(image).enhance(0.75)
        self.albumArtCached = image.convert('RGBA')
        return image

class PlexTrack(Track):
    def __init__(self, item, client=None):
        super().__init__()
        if not isinstance(item, plexapi.audio.Audio):
            raise TypeError("item must be a plexapi.audio.Audio object")

        self.track = item.title
        self.album = item.album().title
        self.artist = item.originalTitle or item.artist().title
        self.duration = client.timeline.duration / 1000.0
        self.progress = client.timeline.time / 1000.0
        
        # Plex specific instance variables
        self.item = item
        self.client = client
        self.label = item.album().studio
        self.year = item.album().year
        self._album_id = item.parentRatingKey
        self._track_id = item.ratingKey

    def get_image(self):
        processed = "%s/%s-%s.png" % (image_cache, self.__class__.__name__, self.album_id)
        try:
            if (time() - os.path.getmtime(processed)) < (7 * 24 * 60 * 60):
                return Image.open(processed)
            else:
                os.remove(processed)
        except OSError:
            pass

        art_url = self.item.parentThumb or self.item.grandparentThumb
        if not art_url:
            return super().get_image()
        url = config["config"]["plex"]["base"] + art_url
        path = plexapi.utils.download(url, config["config"]["plex"]["token"], filename=str(self.album_id), savepath="/tmp")
        try:
            image = Image.open(path)
        except PIL.UnidentifiedImageError as err:
            raise TrackError(f"Can't get image: {err} {self.track} {self}")

        image = ImageOps.pad(image, size=(64,64), centering=(1,0))
        if image.mode != "RGB":
            image = image.convert("RGB")
        image.save(processed, "PNG")
        os.remove(path)
        return image

class CastTrack(Track):
    def __init__(self, cast, meta):
        super().__init__()
        self.track = meta["title"] if "title" in meta else ""
        self.album = meta["albumName"] if "albumName" in meta else ""
        self.artist = meta["artist"] if "artist" in meta else meta["subtitle"] if "subtitle" in meta else ""
        self.duration = cast.media_controller.status.duration
        self.progress = cast.media_controller.status.adjusted_current_time

        self.cast = cast
        self.meta = meta
        self.plex_track = None

        if cast.media_controller.status.images:
            self.art_url = cast.media_controller.status.images[0].url
        elif cast.media_controller.status.media_custom_data.get("providerIdentifier") == "com.plexapp.plugins.library":
            item = config["music"].plex.fetchItem(cast.media_controller.status.media_custom_data["key"])
            self.plex_track = PlexTrack(item=item)
            self.art_url = False
        else:
            self.art_url = meta["images"][1]["url"] if "images" in meta else False

    @property
    def timeleft(self):
        if self.cast.media_controller.status.stream_type_is_live:
            return -1
        else:
            return super().timeleft

    def get_image(self):
        if self.plex_track:
            return self.plex_track.get_image()
        else:
            return super().get_image()

class SpotifyTrack(Track):
    def __init__(self, meta):
        super().__init__()
        self.track = meta["item"]["name"]
        self.album = meta["item"]["album"]["name"]
        self.artist = ", ".join(map(lambda x: x["name"], meta["item"]["artists"]))
        self.duration = meta["item"]["duration_ms"] / 1000.0
        self.progress = meta["progress_ms"] / 1000.0

        self.meta = meta
        if meta["item"]["album"]["release_date"]:
            self.year = int(meta["item"]["album"]["release_date"][:4])
        self._album_id = meta["item"]["album"]["id"]
        self._track_id = meta["item"]["id"]
        self.art_url = meta["item"]["album"]["images"][0]["url"]

class HeosTrack(Track):
    def __init__(self, payload):
        super().__init__()
        self.track = payload["song"]
        self.album = payload["album"]
        self.artist = payload["artist"]
        self.payload = payload
        self.art_url = payload["image_url"]

class Music:
    def __init__(self, devices=None, image_cache=""):
        self.plex = PlexServer(config["config"]["plex"]["base"], config["config"]["plex"]["token"])
        self.plex_devices = config["config"]["plex"]["devices"].split(", ")
        logger.warning("Plex: %s" % ", ".join(self.plex_devices))

        self.chromecasts = None
        try:
            devices=config["config"]["chromecast"]["devices"].split(", ")
            self.chromecasts, self.browser = pychromecast.get_listed_chromecasts(friendly_names=devices)
            logger.warning("Chromecast: %s" % ", ".join(map(lambda x: x.name, self.chromecasts)))
        except KeyError:
            pass
        
        spotify_cache = CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, config["config"]["spotify"]["username"]))
        self._spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(
                                        client_id=config["config"]["spotify"]["spotify_id"],
                                        client_secret=config["config"]["spotify"]["spotify_secret"],
                                        cache_handler=spotify_cache,
                                        redirect_uri="http://localhost:8080/callback",
                                        show_dialog=True,
                                        open_browser=False,
                                        scope="user-library-read,user-read-playback-state"))
        user = self._spotify.current_user()
        logger.warning("Spotify: %s [%s]" % (user["display_name"], user["id"]))

        try:
            self.heos = HeosPlayer(config_file="/home/pi/.heospy/config.json")
            logger.warning("HEOS: %s" % self.heos.main_player_name)

        except:
            logging.error("HEOS problem...")

        self.last_album_id = ""
        self.last_track_id = ""
        self.albumArtCached = None
        self.playing = {}
    
    def font(self, size=8):
        return ImageFont.truetype(config["config"]["fonts"]["music"], size)

    def italic(self, size=8):
        return ImageFont.truetype(config["config"]["fonts"]["music_italic"], size)

    def nowplaying(self):
        for type in ["heos", "plex", "cast", "spotify"]:
            if type in self.playing and self.playing[type]:
                return self.playing[type][0][1]
        return None

    def get_playing_plex(self):
        # Reset playing objects
        self.playing["plex"] = []

        try:
            for client in self.plex.clients():
                if client.title not in self.plex_devices:
                    continue
                if not client.isPlayingMedia(includePaused=False):
                    continue
                if client.timeline.address == "music.provider.plex.tv":
                    continue
                try:   
                    item = self.plex.fetchItem(client.timeline.key)
                    self.playing["plex"].append((client.title, PlexTrack(item=item, client=client)))
                except (plexapi.exceptions.NotFound, plexapi.exceptions.BadRequest) as err:
                     logger.error(f"I think we have a Tidal track {err}\n{vars(client.timeline)}")
                     continue    

            if self.playing["plex"]:
                return min(x[1].recheck_in() for x in self.playing["plex"])

        except (TypeError) as err:
            logger.error(f"Plex server TypeError: {err}")
            return 30.0
        except requests.exceptions.ConnectionError as err:
            logger.info(f"Plex server ConnectionError: {err}")
            return 30.0
        except (AttributeError, requests.exceptions.ReadTimeout) as err:
            logger.error(f"Plex server error: {err}")
            return 30.0

        return 20.0

    def get_playing_spotify(self):
        self.playing["spotify"] = []

        try:
            meta = self._spotify.current_user_playing_track()
        except (spotipy.exceptions.SpotifyException,
                spotipy.oauth2.SpotifyOauthError,
                requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                simplejson.errors.JSONDecodeError) as err:
            logger.error("Spotify error getting current_user_playing_track: %s" % err)
            return 60.0

        if meta and meta["is_playing"] and meta["item"]:
            self.playing["spotify"].append(("Spotify", SpotifyTrack(meta)))
            return min(x[1].recheck_in() for x in self.playing["spotify"])
        else:
            return 60.0
            
    def get_playing_chromecast(self):
        self.playing["cast"] = []

        for cast in self.chromecasts:
            cast.wait()
            if cast.media_controller.status.player_is_playing:
                meta = cast.media_controller.status.media_metadata
                try:
                    self.playing["cast"].append((cast, CastTrack(cast, meta)))
                except TypeError as err:
                    logger.warning(f"Plex server TypeError: {err}")
                    return 30

        if self.playing["cast"]:
            return min(x[1].recheck_in() for x in self.playing["cast"])

        return 30

    def get_playing_heos(self):
        self.playing["heos"] = []

        try:
            result = self.heos.cmd("/player/get_play_state", {"pid": "223731818"})
            if result["heos"]["result"] == "success":
                if result["heos_message_parsed"]["state"] == "play":
                    result = self.heos.cmd("/player/get_now_playing_media", {"pid": "223731818"})
                    if result["heos"]["result"] == "success":
                        self.playing["heos"].append(("Heos", HeosTrack(result["payload"])))
                        return min(x[1].recheck_in() for x in self.playing["heos"])
        except (BrokenPipeError, TimeoutError, ConnectionResetError) as err:
            logger.error(err)
            
        return 20.0

    def new_album(self):
        if self.last_album_id == self.nowplaying().album_id:
            return False
        else:
            self.albumArtCached = None
            self.last_album_id = self.nowplaying().album_id

            return True

    def new_song(self):
        if self.last_track_id == self.nowplaying().track_id:
            return False
        else:
            self.last_track_id = self.nowplaying().track_id
            return True

    def album_image(self):
        if not self.albumArtCached:
            self.albumArtCached = self.nowplaying().image

        return self.albumArtCached

    def canvas(self):
        canvas = Image.new('RGBA', (64, 64), (0,0,0))
        canvas.paste(self.album_image(), (0, 0))

        if config["weather"].steamy() or config["weather"].icy() or not config["frame"].square:
            canvas.alpha_composite(config["weather"].extreme())

        return canvas

    def layout_text(self):
        text = self.nowplaying().artist + "\n"
        text += f'"{self.nowplaying().track}"' + "\n"
        if config["frame"].square:
            if self.nowplaying().year:
                text += f'{self.nowplaying().album} ({self.nowplaying().year})'
            else:
                text += self.nowplaying().album

        (l, t, r, b) = ImageDraw.Draw(Image.new('RGBA', (1, 1))).multiline_textbbox((0, -1), text, font=self.font(), spacing=0)

        image = Image.new('RGBA', (r, b + 1), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        draw.multiline_text((1, 1), text, fill=(0,0,0), font=self.font(), spacing=0)
        draw.multiline_text((0, 0), text, fill=(255, 255, 255), font=self.font(), spacing=0)
        return image