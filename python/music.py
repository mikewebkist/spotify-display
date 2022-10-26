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
        self.track_id = "%s/%s" % (track, artist)
        self.art_url = art
        self.is_live = False

    def get_image(self):
        url = random.choice([
            "https://japan-is-an-island.webkist.com/tumblr_files/tumblr_obmagdfqtB1vcet60o1_1280.jpg",
            "https://japan-is-an-island.webkist.com/tumblr_files/tumblr_objebnzagl1vcet60o1_1280.jpg",
            "https://www.webkist.com/assets/photography/flickr/small/five-ties_443920236_o.jpg",
            "https://www.webkist.com/assets/photography/flickr/small/trees--snow_436704156_o.jpg"])

        m = url.rsplit('/', 1)
        processed = "%s/album-%s.png" % (image_cache, m[-1])
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
            image = cover

        image = ImageEnhance.Color(image).enhance(0.75)
        self.albumArtCached = image
        return image

class PlexTrack(Track):
    def __init__(self, item):
        self.item = item
        self.is_live = False
        self.track = item.title
        self.album = item.album().title
        self.artist = item.originalTitle or item.artist().title
        self.album_id = item.parentRatingKey

    def get_image(self):
        processed = "%s/plex%s.png" % (image_cache, self.album_id)
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

        if cast.media_controller.status.media_custom_data.get("providerIdentifier") == "com.plexapp.plugins.library":
            item = config["music"].plex.fetchItem(cast.media_controller.status.media_custom_data["key"])
            self.plex_track = PlexTrack(item=item)
            self.art_url = False
        else:
            self.art_url = meta["images"][1]["url"] if "images" in meta else False

    def get_image(self):
        if not self.art_url:
            if self.plex_track:
                return self.plex_track.get_image()
            else:
                return super().get_image()

        m = self.art_url.rsplit('/', 1)
        processed = "%s/cast%s.png" % (image_cache, m[-1])
        if os.path.exists(processed):
            image = Image.open(processed)
        else:
            with urllib.request.urlopen(self.art_url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(64,64), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")
        return image

class SpotifyTrack(Track):
    def __init__(self, meta):
        self.meta = meta
        self.track = meta["item"]["name"]
        self.album = meta["item"]["album"]["name"]
        self.artist = ", ".join(map(lambda x: x["name"], meta["item"]["artists"]))
        self.album_id = meta["item"]["album"]["id"]
        self.art_url = meta["item"]["album"]["images"][0]["url"]
        self.track_id = meta["item"]["id"]

    def timeleft(self):
        return (self.meta["item"]["duration_ms"] - self.meta["progress_ms"]) / 1000.0
    
    def progress(self):
        return self.meta["progress_ms"] / 1000.0

class Music:
    def __init__(self, devices=None, font=None, image_cache=""):
        self.font = font
        
        self.plex = PlexServer(config["config"]["plex"]["base"], config["config"]["plex"]["token"])
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

        self.lastAlbum = ""
        self.lastSong = ""
        self.albumArtCached = None
        self.chromecast_songinfo = None
        self.spotify_songinfo = None
        self.plex_songinfo = None

    def nowplaying(self):
        if self.chromecast_songinfo:
            return self.chromecast_songinfo
        elif self.plex_songinfo:
            return self.plex_songinfo
        elif self.spotify_songinfo:
            return self.spotify_songinfo
        else:
            return None

    def get_playing_plex(self):
        try:
            for client in self.plex.clients():
                if not client.isPlayingMedia(includePaused=False):
                    continue
                item = self.plex.fetchItem(client.timeline.key)
                obj = PlexTrack(item=item)
                self.plex_songinfo = obj
                return 5.0

        except (AttributeError, requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as err:
            logger.error(f"Plex server error: {err}")
            return 30.0

        self.plex_songinfo = None
        return 20.0

    def get_playing_spotify(self):
        if self.chromecast_songinfo:
            return 60.0

        try:
            meta = self._spotify.current_user_playing_track()
        except (spotipy.exceptions.SpotifyException,
                spotipy.oauth2.SpotifyOauthError) as err:
            logger.error("Spotify error getting current_user_playing_track:")
            logger.error(err)
            self.spotify_songinfo = None
            return 60.0 * 5.0
        except (requests.exceptions.ReadTimeout,
                requests.exceptions.ConnectionError,
                simplejson.errors.JSONDecodeError) as err:
            logger.error("Protocol problem getting current_user_playing_track")
            logger.error(err)
            self.spotify_songinfo = None
            return 60.0

        if meta and meta["is_playing"] and meta["item"]:
            obj = SpotifyTrack(meta)
            self.spotify_songinfo = obj

            timeleft = obj.timeleft()
            if obj.progress() < 15.0:
                return 1.0
            elif timeleft > 30.0:
                return 30.0
            elif timeleft > 5.0:
                return timeleft
            else:
                return 1.0
        else:
            self.spotify_songinfo = None
            return 60.0
            
        # Just in case
        return 60.0

    def get_playing_chromecast(self):
        for cast in self.chromecasts:
            cast.wait()
            if cast.media_controller.status.player_is_playing:
                meta = cast.media_controller.status.media_metadata
                obj = CastTrack(cast=cast, meta=meta)
                self.chromecast_songinfo = obj

                if cast.media_controller.status.stream_type_is_live:
                    return 10.0
                elif cast.media_controller.status.duration:
                    timeleft = round((cast.media_controller.status.duration - cast.media_controller.status.adjusted_current_time))

                    if timeleft > 10.0:
                        return 10.0
                    else:
                        return timeleft
                else:
                    logger.info(cast.media_controller.status)
                    return 2.0
                break
        else:
            self.chromecast_songinfo = None

            if self.spotify_songinfo:
                return 10.0

        return 2.0

    def new_album(self):
        if self.lastAlbum == self.nowplaying().album_id:
            return False
        else:
            self.albumArtCached = None
            self.lastAlbum = self.nowplaying().album_id

            return True

    def new_song(self):
        if self.lastSong == self.nowplaying().track_id:
            return False
        else:
            self.lastSong = self.nowplaying().track_id
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
        draw.fontmode = "1"
        y_pos = 0
        for line in lines:
            draw.text((2, y_pos + 1), line, (0,0,0), font=self.font)
            draw.text((1, y_pos), line, (192, 192, 192), font=self.font)
            y_pos = y_pos + self.font.getsize(line)[1]
        return txtImg

    def get_text(self,textColor=(192,192,192, 255)):
            return self.layout_text([self.nowplaying().track,
                                     self.nowplaying().artist])
