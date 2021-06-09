import spotipy
import os
from spotipy.oauth2 import SpotifyOAuth
import json

sp = spotipy.Spotify(auth_manager=SpotifyOAuth(client_id=os.environ["SPOTIFY_ID"],
                                               client_secret=os.environ["SPOTIFY_SECRET"],
                                               redirect_uri="http://localhost:8080/callback",
                                               scope="user-library-read,user-read-playback-state"))

user = sp.current_user()
print("Now Playing for %s [%s]\n" % (user["display_name"], user["id"]))

np = sp.current_user_playing_track()

if np["is_playing"]:
    print("\n%s\n%s\n%s\n" % (np["item"]["album"]["name"], np["item"]["name"], np["item"]["artists"][0]["name"] ))

# print(json.dumps(np))
