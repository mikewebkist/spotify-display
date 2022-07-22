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

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

image_cache = "%s/imagecache" % (basepath)

class Music:
    def __init__(self, devices=None, spotify_id=None, spotify_secret=None, spotify_user=None,
                        font=None, image_cache="", weather=None):

        self.font = font
        self.weather = weather                
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

    def nowplaying(self):
        if self.chromecast_songinfo:
            return self.chromecast_songinfo
        elif self.spotify_songinfo:
            return self.spotify_songinfo
        else:
            return None

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
                obj = {
                        "chromecast_playing": True,
                        "track": meta["title"] if "title" in meta else "",
                        "album": meta["albumName"] if "albumName" in meta else "",
                        "artist": meta["artist"] if "artist" in meta else meta["subtitle"] if "subtitle" in meta else "",
                        "albumArtist": meta["albumArtist"] if "albumArtist" in meta else "",
                        "album_art_url": meta["images"][0]["url"] if "images" in meta else False,
                        "artist_art_url": False,
                        }
                obj["album_id"] = "%s/%s" % (obj["album"], obj["artist"]),
                obj["track_id"] = "%s/%s/%s" % (obj["track"], obj["album"], obj["artist"]),
                obj["is_live"]  = cast.media_controller.status.stream_type_is_live

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
                    print(cast.media_controller.status)
                    return 2.0
                break
        else:
            self.chromecast_songinfo = None

            if self.spotify_songinfo:
                return 10.0

        return 2.0

    def new_album(self):
        if self.lastAlbum == self.nowplaying()["album_id"]:
            return False
        else:
            self.albumArtCached = None
            self.lastAlbum = self.nowplaying()["album_id"]
            if self.nowplaying()["album_art_url"]:
                self.albumArt = self.nowplaying()["album_art_url"]
            else:
                # print("Searching for artist=%s, album=%s" % (self.nowplaying()['albumArtist'], self.nowplaying()['album']))
                results = self._spotify.search(q='artist:' + self.nowplaying()["albumArtist"] + ' album:' + self.nowplaying()["album"], type='album')
                try:
                    print("Album search result: %s by %s" % (results["albums"]["items"][0]["name"], results["albums"]["items"][0]["artists"][0]["name"]))
                    self.albumArt = results["albums"]["items"][0]["images"][-1]["url"]
                    self.nowplaying()["album_art_url"] = self.albumArt
                except IndexError:
                    self.albumArt = None
                if not self.albumArt:
                    results = self._spotify.search(q='artist:' + self.nowplaying()["artist"], type='artist')
                    try:
                        print("Artist search result: %s" % results["artists"]["items"][0]["name"])
                        self.albumArt = results["artists"]["items"][0]["images"][-1]["url"]
                        self.nowplaying()["album_art_url"] = self.albumArt
                    except IndexError:
                        self.albumArt = None
            return True

    def new_song(self):
        if self.lastSong == self.nowplaying()["track_id"]:
            return False
        else:
            self.lastSong = self.nowplaying()["track_id"]
            return True

    def album_image(self):
        if self.albumArtCached:
            return self.albumArtCached

        if self.albumArt:
            url = self.albumArt
        else: # if we don't have any art, show the weather icon
            return self.weather.icon()

        m = url.rsplit('/', 1)
        processed = "%s/album-%s.png" % (image_cache, m[-1])

        # We're going to save the processed image instead of the raw one.

        if os.path.isfile(processed):
            image = Image.open(processed)
        else:
            logger.info("Getting %s" % url)
            with urllib.request.urlopen(url) as rawimage:
                image = ImageOps.pad(Image.open(rawimage), size=(64,64), method=Image.LANCZOS, centering=(1,0))
                image.save(processed, "PNG")

        brightness = max(ImageStat.Stat(image).mean)
        if brightness > 160:
            print(f"Album art too bright for the matrix: {brightness:.0f}")
            image = ImageEnhance.Brightness(image).enhance(160.0 / brightness)
        
        if self.weather.night():
            image = ImageEnhance.Brightness(image).enhance(0.5)

        self.albumArtCached = image
        return image

    def canvas(self):
        canvas = Image.new('RGBA', (64, 64), (0,0,0))
        canvas.paste(self.album_image(), (0, 0))

        if self.weather.steamy() or self.weather.icy():
            txtImg = Image.new('RGBA', (64, 64), (255, 255, 255, 0))
            draw = ImageDraw.Draw(txtImg)
            draw.fontmode = None
            draw.text((0, -2), self.weather.feelslike(), (128, 128, 128), font=self.font)
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
            return self.layout_text([self.nowplaying()["track"],
                                     self.nowplaying()["album"],
                                     self.nowplaying()["artist"]])
        else:
            return self.layout_text([self.nowplaying()["track"],
                                     self.nowplaying()["artist"]])
