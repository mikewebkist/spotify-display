package main

import (
	"fmt"
	"log"
	"net/http"

	"golang.org/x/oauth2"

	"github.com/zmb3/spotify"
)

const redirectURI = "http://localhost:8080/callback"
const tokenPath = "/tmp/spotify-display.json"

var token oauth2.Token

var (
	auth  = spotify.NewAuthenticator(redirectURI, spotify.ScopeUserReadPrivate, spotify.ScopeUserReadPlaybackState)
	ch    = make(chan oauth2.Token)
	state = "abc123"
)

func check(e error) {
	if e != nil {
		panic(e)
	}
}

func main() {
	if err := Load(tokenPath, &token); err != nil {
		http.HandleFunc("/callback", completeAuth)
		http.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
			log.Println("Got request for:", r.URL.String())
		})
		go http.ListenAndServe(":8080", nil)

		url := auth.AuthURL(state)
		fmt.Println("Please log in to Spotify by visiting the following page in your browser:", url)

		// wait for auth to complete
		token = <-ch
	}
	client := auth.NewClient(&token)

	// use the client to make calls that require authorization
	user, err := client.CurrentUser()
	check(err)

	fmt.Printf("Now Playing for %s [%s]\n", user.DisplayName, user.ID)
	np, err := client.PlayerCurrentlyPlaying()

	if err != nil {
		fmt.Println(err)
	}

	if np.Playing {
		fmt.Printf("\n%s\n%s\n%s\n", np.Item.Album.Name, np.Item.Name, np.Item.Artists[0].Name)
	} else {
		fmt.Printf("Nothing playing...\n")
	}

	if err := Save(tokenPath, &token); err != nil {
		log.Fatalln(err)
	}
}

func completeAuth(w http.ResponseWriter, r *http.Request) {
	tok, err := auth.Token(state, r)
	if err != nil {
		http.Error(w, "Couldn't get token", http.StatusForbidden)
		log.Fatal(err)
	}
	if st := r.FormValue("state"); st != state {
		http.NotFound(w, r)
		log.Fatalf("State mismatch: %s != %s\n", st, state)
	}
	// use the token to get an authenticated client
	ch <- *tok
}
