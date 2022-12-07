import spotipy
import re
from spotipy.oauth2 import SpotifyOAuth
from spotipy.cache_handler import CacheFileHandler
import simplejson
import os
import sys
import logging
import configparser
from plexapi.server import PlexServer
from plexapi.myplex import MyPlexDevice
import plexapi
import time


config = configparser.ConfigParser()
basepath = os.path.dirname(sys.argv[0])
if basepath == "":
    basepath = "."

if len(sys.argv) > 1:
    configfile = sys.argv[1]
else:
    configfile = "%s/local.config" % basepath

config.read(configfile)

spotify_cache = CacheFileHandler(cache_path="%s/tokens/likes-%s" % (basepath, config["spotify"]["username"]))
spotify = spotipy.Spotify(auth_manager=SpotifyOAuth(
                                client_id=config["spotify"]["spotify_id"],
                                client_secret=config["spotify"]["spotify_secret"],
                                cache_handler=spotify_cache,
                                redirect_uri="http://localhost:8080/callback",
                                show_dialog=True,
                                open_browser=False,
                                scope="user-library-read,user-read-playback-state,playlist-modify-public,playlist-modify-private"))
user = spotify.current_user()
# print("Now Playing for %s [%s]" % (user["display_name"], user["id"]))
playlist_name = f"Liked {time.strftime('%Y-%m-%d')}"
spotify_playlist = spotify.user_playlist_create(user["id"], playlist_name, public=False)
spotify_playlist_id = spotify_playlist["id"]

plex = PlexServer(config["plex"]["base"], config["plex"]["token"])
music = plex.library.section("Music")
plex_playlist = None

def compare(string1, string2):
    if string1 and string2:
        return normalize_string(string1) == normalize_string(string2)
    else:
        return False

def normalize_track(title):
    return re.sub(r' - (\d+ )?Remaster(ed)?( \d+)?', '', title).strip()

def normalize_string(title):
    return re.sub(r'[^a-z0-9 ]', '', title.lower().removeprefix("the ").strip())

albums = {}
saved = spotify.current_user_saved_tracks(limit=50)
while True:
    for track in saved["items"]:
        print("<%s> - <%s>" % (track["track"]["artists"][0]["name"], track["track"]["name"]))

        for plex_track in music.searchTracks(title=normalize_track(track["track"]["name"])):
            spotify_artist = track["track"]["artists"][0]["name"]

            if plex_track.artist().title == spotify_artist:
                print("  exact artist match: %s" % plex_track.artist().title)
            elif plex_track.originalTitle == spotify_artist:
                print("  exact OT artist match: %s" % plex_track.originalTitle)
            elif compare(plex_track.artist().title, spotify_artist):
                print("  fuzzy artist match: %s" % plex_track.artist().title)
            elif compare(plex_track.originalTitle, spotify_artist):
                print("  fuzzy OT artist match: %s" % plex_track.originalTitle)
            else:
                print("  no artist match: %s" % plex_track.artist().title)
                continue

            if track["track"]["name"] == plex_track.title:
                print("  exact track match: %s" % plex_track.title)
            elif compare(normalize_track(track["track"]["name"]), plex_track.title):
                print("  fuzzy track match: %s" % plex_track.title)
            else:
                print("  no track match: %s" % plex_track.title)
                continue

            if plex_track.userRating:
                print(f"    already liked: {plex_track.userRating}")
            elif plex_playlist is None:
                print(f"    creating and adding to Plex playlist")
                plex_playlist = music.createPlaylist(playlist_name, items=[plex_track])
            else:
                print(f"    adding to playlist")
                plex_playlist.addItems(plex_track)
            break
        else:
            print("  no good match on Plex. Adding to Spotify playlist")

            album_ref = "%s - %s" % (track["track"]["artists"][0]["name"], track["track"]["album"]["name"])
            if album_ref not in albums:
                albums[album_ref] = 1
            else:
                albums[album_ref] += 1
            spotify.user_playlist_add_tracks(user["id"], spotify_playlist_id, [track["track"]["uri"]])
    
    if saved["next"]:
        saved = spotify.next(saved)
    else:
        break

print("Albums not found on Plex:")
for album, count in albums.items():
    print("%d\t%s" % (count, album))
