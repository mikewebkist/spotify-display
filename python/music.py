import pychromecast
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
import os
import sys
import logging
import PIL
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops, ImageFilter, ImageOps, ImageStat
import urllib
import requests
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexDevice
import plexapi
import random
from config import config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

image_cache = "%s/imagecache" % (basepath)

class Track:
    def __init__(self, track="", album="", artist="", art=""):
        self.track = track
        self.album = album
        self.artist = artist
        self.album_id = "%s/%s" % (album, artist)
        self.art_url = art
        self.is_live = False
        self.track_id = "%s/%s" % (self.track, self.artist)

    @property
    def timeleft(self):
        return self.duration - self.progress

    def recheck_in(self):
        if self.timeleft < 0:
            return 30.0
        if self.progress < 15.0:
            return 1.0
        elif self.timeleft > 30.0:
            return 30.0
        elif self.timeleft > 5.0:
            return self.timeleft
        else:
            return 1.0

    def get_image(self):
        print(self.__class__.__name__)
        if not self.art_url:
            url = random.choice([
                "https://japan-is-an-island.webkist.com/tumblr_files/tumblr_obmagdfqtB1vcet60o1_1280.jpg",
                "https://japan-is-an-island.webkist.com/tumblr_files/tumblr_objebnzagl1vcet60o1_1280.jpg",
                "https://www.webkist.com/assets/photography/flickr/small/five-ties_443920236_o.jpg",
                "https://www.webkist.com/assets/photography/flickr/small/trees--snow_436704156_o.jpg"])
        else:
            url = self.art_url

        m = url.rsplit('/', 1)
        processed = "%s/%s-%s.png" % (image_cache, self.__class__.__name__, m[-1])
        if os.path.exists(processed):
            image = Image.open(processed)
        else:
            with urllib.request.urlopen(url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(64,64), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")
        return image

    @property
    def image(self):
        image = self.get_image()

        avg = sum(ImageStat.Stat(image).sum) / sum(ImageStat.Stat(image).count)
        max = 200.0
        if avg > max:
            logger.info(f"Image too bright for the matrix: {avg:.0f}")
            image = ImageEnhance.Brightness(image).enhance(max / avg)

        if config["frame"].height < 64:
            cover = Image.new('RGBA', (64, 32), (0,0,0))
            cover.paste(image.resize((config["frame"].height, config["frame"].height), Image.LANCZOS), (64 - config["frame"].height,0))
            image = cover.convert('RGBA')

        image = ImageEnhance.Color(image).enhance(0.75)
        self.albumArtCached = image.convert('RGBA')
        return image

class PlexTrack(Track):
    def __init__(self, item, client):
        self.item = item
        self.client = client
        self.is_live = False
        self.track = item.title
        self.album = item.album().title
        self.artist = item.originalTitle or item.artist().title
        self.album_id = item.parentRatingKey
        self.track_id = item.ratingKey
        self.duration = client.timeline.duration / 1000.0
        self.progress = client.timeline.time / 1000.0


    def get_image(self):
        processed = "%s/%s-%s.png" % (image_cache, self.__class__.__name__, self.album_id)
        if os.path.exists(processed):
            image = Image.open(processed)
        else:
            url = config["config"]["plex"]["base"] + self.item.parentThumb
            path = plexapi.utils.download(url, config["config"]["plex"]["token"], filename=str(self.album_id), savepath="/tmp")
            try:
                image = Image.open(path)
            except PIL.UnidentifiedImageError as err:
                return super().get_image()

            image = ImageOps.pad(image, size=(64,64), centering=(1,0))
            image.save(processed, "PNG")
            os.remove(path)
        return image

class CastTrack(Track):
    def __init__(self, cast, meta):
        self.cast = cast
        self.meta = meta
        self.plex_track = None
        self.track = meta["title"] if "title" in meta else ""
        self.album = meta["albumName"] if "albumName" in meta else ""
        self.artist = meta["artist"] if "artist" in meta else meta["subtitle"] if "subtitle" in meta else ""
        self.album_id = "%s/%s" % (self.album, self.artist)
        self.duration = cast.media_controller.status.duration
        self.progress = cast.media_controller.status.adjusted_current_time
        self.track_id = "%s/%s" % (self.track, self.artist)
        if cast.media_controller.status.images:
            print(cast.media_controller.status.images[0])
            self.art_url = cast.media_controller.status.images[0].url

        if cast.media_controller.status.media_custom_data.get("providerIdentifier") == "com.plexapp.plugins.library":
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
            return self.duration - self.progress

    def get_image(self):
        if self.plex_track:
            return self.plex_track.get_image()
        else:
            return super().get_image()

class SpotifyTrack(Track):
    def __init__(self, meta):
        self.meta = meta
        self.track = meta["item"]["name"]
        self.album = meta["item"]["album"]["name"]
        self.artist = ", ".join(map(lambda x: x["name"], meta["item"]["artists"]))
        self.album_id = meta["item"]["album"]["id"]
        self.art_url = meta["item"]["album"]["images"][0]["url"]
        self.duration = meta["item"]["duration_ms"] / 1000.0
        self.progress = meta["progress_ms"] / 1000.0

    @property
    def track_id(self):
        return self.meta["item"]["id"]

class Music:
    def __init__(self, devices=None, font=None, image_cache=""):
        self.font = font
        
        self.plex = PlexServer(config["config"]["plex"]["base"], config["config"]["plex"]["token"])
        self.plex_devices = config["config"]["plex"]["devices"].split(", ")

        self.chromecasts = None
        try:
            devices=config["config"]["chromecast"]["devices"].split(", ")
            self.chromecasts, self.browser = pychromecast.get_listed_chromecasts(friendly_names=devices)
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
        logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))

        self.last_album_id = ""
        self.last_track_id = ""
        self.albumArtCached = None
        self.songinfo = None

    def nowplaying(self):
        return self.songinfo

    def get_playing_plex(self):
        if self.songinfo and type(self.songinfo) != PlexTrack:
            return self.songinfo.recheck_in() + 1.0

        logger.info(f"Checking Plex for {self.plex_devices}")
        try:
            for client in self.plex.clients():
                logger.info(f"checking client {client.title}")
                if client.title not in self.plex_devices:
                    logger.info(f"Unknown client {client.title}")
                    continue
                print(client)
                if not client.isPlayingMedia(includePaused=False):
                    logger.info(f"Client {client.title} not playing")
                    continue
                item = self.plex.fetchItem(client.timeline.key)
                self.songinfo = PlexTrack(item=item, client=client)
                return self.songinfo.recheck_in()

        except (AttributeError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as err:
            logger.error(f"Plex server error: {err}")
            return 30.0

        self.songinfo = None
        return 20.0

    def get_playing_spotify(self):
        if self.songinfo and type(self.songinfo) != SpotifyTrack:
            return self.songinfo.recheck_in() + 1.0

        logger.info("Checking Spotify")
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
            self.songinfo = SpotifyTrack(meta)
            return self.songinfo.recheck_in()
        else:
            self.songinfo = None
            return 60.0
            
    def get_playing_chromecast(self):
        if self.songinfo and type(self.songinfo) != CastTrack:
            return self.songinfo.recheck_in() + 1.0

        logger.info("Checking chromecast devices")
        for cast in self.chromecasts:
            cast.wait()
            if cast.media_controller.status.player_is_playing:
                meta = cast.media_controller.status.media_metadata
                self.songinfo = CastTrack(cast=cast, meta=meta)

                return self.songinfo.recheck_in()
        else:
            self.songinfo = None
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

        if config["weather"].steamy() or config["weather"].icy():
            txtImg = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
            draw = ImageDraw.Draw(txtImg)
            draw.fontmode = None
            draw.text((0, -2), config["weather"].feelslike(), (128, 128, 128), font=self.font)
            canvas.alpha_composite(txtImg)

        return canvas

    def layout_text(self, lines):
        height = 0
        width = 0
        for line in lines:
            wh = self.font.getsize(line)
            width = max(width, wh[0])
            height = height + wh[1]

        txtImg = Image.new('RGBA', (width + 2, height + 1), (255, 255, 255, 0))
        draw = ImageDraw.Draw(txtImg)
        # draw.fontmode = "1"
        y_pos = 0
        for line in lines:
            draw.text((2, y_pos + 1), line, (0,0,0), font=self.font)
            draw.text((1, y_pos), line, (255, 255, 255), font=self.font)
            y_pos = y_pos + self.font.getsize(line)[1]
        return txtImg
