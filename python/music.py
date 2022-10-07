import pychromecast
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
import os
import sys
import logging
from PIL import Image, ImageEnhance, ImageFont, ImageDraw, ImageChops, ImageFilter, ImageOps, ImageStat
import urllib
import requests
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexDevice
import plexapi
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
        self.art = art
        self.is_live = False

    @property
    def art_url(self):
        return "https://www.webkist.com/assets/photography/bermuda2022/holga/holga-102.jpg"

    @property
    def album_id(self):
        return "%s/%s" % (self.album, self.artist)

    @property
    def track_id(self):
        return "%s/%s/%s" % (self.track, self.album, self.artist)

    def get_image(self):
        m = self.art_url.rsplit('/', 1)
        processed = "%s/album-%s.png" % (image_cache, m[-1])
        if os.path.exists(processed):
            image = Image.open(processed)
        else:
            with urllib.request.urlopen(self.art_url) as rawimage:
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

        self.albumArtCached = image
        return image

class PlexTrack(Track):
    def __init__(self, track, album, artist, art, key):
        super().__init__(track, album, artist, art)
        self.key = key

    @property
    def key_id(self):
        m = self.key.rsplit('/', 1)
        return m[-1]

    @property
    def art_url(self):
        return config["config"]["plex"]["base"] + self.art

    def get_image(self):
        processed = "%s/%s" % (image_cache, self.key_id)
        if os.path.exists(processed):
            image = Image.open(processed)
        else:
            path = plexapi.utils.download(self.art_url, config["config"]["plex"]["token"], filename=self.key_id, savepath="/tmp")
            image = Image.open(path)
            image = ImageOps.pad(image, size=(64,64), centering=(1,0))
            image.save(processed, "PNG")
        return image

class Music:
    def __init__(self, devices=None, font=None, image_cache=""):

        spotify_secret=config["config"]["spotify"]["spotify_secret"]
        spotify_id=config["config"]["spotify"]["spotify_id"]
        spotify_user=config["config"]["spotify"]["username"]
        
        self.font = font
        self.plex = PlexServer(config["config"]["plex"]["base"], config["config"]["plex"]["token"])
        if devices:
            chromecasts, self.browser = pychromecast.get_chromecasts()
            self.chromecasts = []
            # This keeps everything in config file order
            if chromecasts:
                for name in devices:
                    try:
                        self.chromecasts.append(chromecasts[list(map(lambda x: x.name, chromecasts)).index(name)])
                    except ValueError:
                        pass

        self._spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=spotify_id,
                                        client_secret=spotify_secret,
                                        cache_handler=CacheFileHandler(cache_path="%s/tokens/%s" % (basepath, spotify_user)),
                                        redirect_uri="http://localhost:8080/callback",
                                        show_dialog=True,
                                        open_browser=False,
                                        scope="user-library-read,user-read-playback-state"))
        user = self._spotify.current_user()
        logger.info("Now Playing for %s [%s]" % (user["display_name"], user["id"]))

        self.lastAlbum = ""
        self.lastSong = ""
        self.albumArt = None
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
                obj = PlexTrack(
                    track = item.title, 
                    album = item.parentTitle, 
                    artist = item.grandparentTitle, 
                    art = item.parentThumb,
                    key = client.timeline.key)
                self.plex_songinfo = obj
                return 5.0

        except (requests.exceptions.ConnectionError, requests.exceptions.ReadTimeout) as err:
            logger.error(f"Plex server error: {err}")
            return 30.0

        self.plex_songinfo = None
        return 20.0

    def get_playing_spotify(self):
        if self.chromecast_songinfo:
            return 60.0

        try:
            meta = self._spotify.current_user_playing_track()
            if meta and meta["is_playing"] and meta["item"]:
                obj = {
                        "spotify_playing": True,
                        "track": meta["item"]["name"],
                        "album": meta["item"]["album"]["name"],
                        "artist": ", ".join(map(lambda x: x["name"], meta["item"]["artists"])),
                        "album_art_url": meta["item"]["album"]["images"][0]["url"],
                        "artist_art_url": False,
                        "spotify_duration": meta["item"]["duration_ms"],
                        "spotify_progress": meta["progress_ms"],
                        "spotify_meta": meta,
                        }

                obj["album_id"] = "%s/%s" % (obj["album"], obj["artist"]),
                obj["track_id"] = "%s/%s/%s" % (obj["track"], obj["album"], obj["artist"]),

                self.spotify_songinfo = obj
                timeleft = round((obj["spotify_duration"] - obj["spotify_progress"]) / 1000.0) 
                if (obj["spotify_progress"] / 1000.0) < 15.0:
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

        # Just in case
        return 60.0

    def get_playing_chromecast(self):
        for cast in self.chromecasts:
            cast.wait()
            if cast.media_controller.status.player_is_playing:
                meta = cast.media_controller.status.media_metadata
                obj = Track(
                    track = meta["title"] if "title" in meta else "",
                    album = meta["albumName"] if "albumName" in meta else "",
                    artist = meta["artist"] if "artist" in meta else meta["subtitle"] if "subtitle" in meta else "",
                    art = meta["images"][0]["url"] if "images" in meta else False)
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

            self.albumArt = self.nowplaying().art_url
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
        if self.albumArt == None:
            return self.layout_text([self.nowplaying().track,
                                     self.nowplaying().album,
                                     self.nowplaying().artist])
        else:
            return self.layout_text([self.nowplaying().track,
                                     self.nowplaying().artist])
