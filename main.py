from flask import Flask, jsonify, request, url_for, abort, g, render_template
from models import db, User
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from sqlalchemy import create_engine
import spotipy
import spotipy.util as util
import urllib
import sys
import pprint
from flask_httpauth import HTTPBasicAuth
import json
from flask_sqlalchemy import SQLAlchemy
import tempfile
import os.path
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
from flask import make_response
import requests

os.environ['SPOTIPY_CLIENT_ID'] = spotify.get_client_id()
os.environ['SPOTIPY_CLIENT_SECRET'] = spotify.get_client_secret()
os.environ['SPOTIPY_REDIRECT_URI'] = spotify.get_redirect_uri()
auth = HTTPBasicAuth()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
db.create_all()

#Refreshes my personal Spotify access token so that I am able to successfully use the different endpoints
def refresh_access_token():
    h = httplib2.Http()
    headers = {"Content-type":"application/x-www-form-urlencoded",
    "Authorization":"Basic OGQ1MjcyZjlmMDBmNGE0NGJmZmIyZTNjYjEzYzVmM2E6MzhmMTgwYzRhMWVkNGFjMzhmYmI1OGQ3M2JkOGEzNGI="}
    uri = "https://accounts.spotify.com/api/token?grant_type=refresh_token&refresh_token=AQD3xUeQOkG6Hayr6pY1oc1vPAWqiqLKfF0mq_Fl-BMOaAI7UHBXjde42Oez_Di0ntVvTwfSRcpWjyrpcUbtEAUwIRA0CFeOuMrWHhYGSBmvmB6h6x6M3s77DpRxYxpLOZg"
    resp,content = h.request(uri, "POST",  headers = headers)
    content = content.decode("utf-8")
    content = json.loads(content)
    return content['access_token']

token = refresh_access_token()
sp = spotipy.Spotify(auth = token)

#Prompt to use a more helpful endpoint
@app.route('/')
def help_message():
    return "Please try and access an useful endpoint"

#Verifies token provided by the user
@auth.verify_password
def verify_password(username_or_token, password):
    #Try to see if it's a token first
    user_id = User.verify_auth_token(username_or_token)
    if user_id:
        user = db.session.query(User).filter_by(id = user_id).one()
    else:
        user = db.session.query(User).filter_by(username = username_or_token).first()
        if not user or not user.verify_password(password):
            return False
    g.user = user
    return True

#Takes user to the sign in page
@app.route('/clientOAuth')
def start():
    return render_template('clientOAuth.html')

#Returns token that user can use to access protected resources
@app.route('/oauth/<path:authcode>', methods = ['POST'])
def login(authcode):
        try:
            # Upgrade the authorization code into a credentials object
            oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
            oauth_flow.redirect_uri = 'postmessage'
            credentials = oauth_flow.step2_exchange(authcode)
        except FlowExchangeError:
            response = make_response(json.dumps('Failed to upgrade the authorization code.'), 401)
            response.headers['Content-Type'] = 'application/json'
            return response

        # Check that the access token is valid.
        access_token = credentials.access_token
        url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s' % access_token)
        h = httplib2.Http()
        result = json.loads(h.request(url, 'GET')[1])
        # If there was an error in the access token info, abort.
        if result.get('error') is not None:
            response = make_response(json.dumps(result.get('error')), 500)
            response.headers['Content-Type'] = 'application/json'
        print ("Step 2 Complete! Access Token : %s " % credentials.access_token)

        h = httplib2.Http()
        userinfo_url =  "https://www.googleapis.com/oauth2/v1/userinfo"
        params = {'access_token': credentials.access_token, 'alt':'json'}
        answer = requests.get(userinfo_url, params=params)

        data = answer.json()

        name = data['name']
        picture = data['picture']
        email = data['email']

        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            user = User(username = name, picture = picture, email = email)
            db.session.add(user)
            db.session.commit()

        token = user.generate_auth_token(600)
        return jsonify({'token': token.decode('ascii')})

#Gets information on artist passed into the method as the name variable
@app.route('/getArtistInfo/<name>')
def displayArtist(name):
    result = sp.search(name, type = 'artist')
    uri = result['artists']['items'][0]['uri']
    artist = sp.artist(uri)
    popularity = artist['popularity']
    genre_list = artist['genres']
    top_tracks = sp.artist_top_tracks(uri)
    song_list = []
    cnt = 0
    for song in top_tracks['tracks']:
        song_list.append(song['name'])
        cnt+=1
        if cnt == 5:
            break
    return jsonify({'popularity' : popularity, 'genre_list' : genre_list, 'top_songs' : song_list })

#Gets related artists of the artist passed into the method as the query variable
@app.route('/getRelatedArtists/<query>')
def display_related_artists(query):
    result = sp.search(query, type = 'artist')
    uri = result['artists']['items'][0]['uri']
    second_result = sp.artist_related_artists(uri)
    related_artists_list = second_result['artists']
    artist_list = [{}]
    for artist in related_artists_list:
        artist_list.append({'artist':artist['name'], 'genre':artist['genres'][0]})
    artist_list.pop(0)
    return jsonify(artist_list)

#Gets top albums of the artist passed into the method as the query variable
@app.route('/getAlbums/<query>')
@auth.login_required
def display_albums(query):
    result = sp.search(query, type = 'artist')
    uri = result['artists']['items'][0]['uri']
    second_result = sp.artist_albums(uri, 'album')
    items_list = second_result['items']
    artists_list = []
    album_list = [{}]
    for album in items_list:
        for artist in album['artists']:
            artists_list.append(artist['name'])
        album_list.append({'name' : album['name'], 'artists' : artists_list})
        artists_list = []
    album_list.pop(0)
    return jsonify(album_list)

#Gets audio information on song name passed int as the query variabel
@app.route('/getAudio/<query>')
@auth.login_required
def get_audio_analysis(query):
    result = sp.search(query, type = 'track')
    uri = result['tracks']['items'][0]['uri']
    second_result = sp.audio_analysis(uri)
    return jsonify(second_result)

#Gets information on the current user
@app.route('/getCurrentUser')
def get_user():
    result = sp.current_user()
    user_name = result['display_name']
    followers = result['followers']['total']
    picture = result['images'][0]['url']
    uri = result['uri']
    return jsonify({'user_name: ' : user_name, 'followers: ' : followers, 'picture: ' : picture, 'uri: ' : uri})

#Creates playliist based on playlist_name
@app.route('/addPlaylist/<playlist_name>', methods=['POST'])
def add_playlist(playlist_name):
    uri = sp.current_user()['uri']
    index = uri.index("user:")
    ID = uri[index+5:]
    scope = 'playlist-modify-public'
    token_new = util.prompt_for_user_token(ID, scope)
    sp_new = spotipy.Spotify(auth=token_new)
    result = sp_new.user_playlist_create(ID,playlist_name, public =True)
    return "Successfully created a playlist named %s" % (playlist_name)

#Adds or deletes songs in a playlist based on the request. playlist_id must be an id and song_list must be a list
#of song names.
@app.route('/alterSongsInPlaylist/<playlist_id>/<song_list>', methods=['POST','DELETE'])
def alter_songs_in_playlist(playlist_id,song_list ):
    uri = sp.current_user()['uri']
    index = uri.index("user:")
    ID = uri[index+5:]
    if request.method == 'POST':
        if "," not in song_list:
            result = sp.search(song_list, type= 'track')
            track_uri = result['tracks']['items'][0]['uri']
            track_uri_list =[track_uri]
            results = sp.user_playlist_add_tracks(ID, playlist_id, track_uri_list)
            return "Successfully added %s" % song_list
        else:
            list_of_songs = song_list.split(",")
            list_of_track_uris=[]
            for song in list_of_songs:
                result = sp.search(song, type= 'track')
                track_uri = result['tracks']['items'][0]['uri']
                list_of_track_uris.append(track_uri)
            results = sp.user_playlist_add_tracks(ID, playlist_id, list_of_track_uris)
            return "Successfully added songs to playlist"
    if request.method == 'DELETE':
        if "," not in song_list:
            result = sp.search(song_list, type= 'track')
            track_uri = result['tracks']['items'][0]['uri']
            track_uri_list =[track_uri]
            results = sp.user_playlist_remove_all_occurrences_of_tracks(ID, playlist_id, track_uri_list)
            return "Successfully deleted %s" % song_list
        else:
            list_of_songs = song_list.split(",")
            list_of_track_uris=[]
            for song in list_of_songs:
                result = sp.search(song, type= 'track')
                track_uri = result['tracks']['items'][0]['uri']
                list_of_track_uris.append(track_uri)
            results = sp.user_playlist_remove_all_occurrences_of_tracks(ID, playlist_id, list_of_track_uris)
            return "Successfully deleted songs from playlist"

#On a put request, the method will update the playist with the given name. On a delete request, it will delete the
#playlist.playlist_id must be an id and new_name can be any string.
@app.route('/updatePlaylist/<playlist_id>/<new_name>', methods=['PUT', "DELETE"])
def update_playlist(playlist_id,new_name ):
    uri = sp.current_user()['uri']
    index = uri.index("user:")
    ID = uri[index+5:]
    if request.method == 'PUT':
        sp.user_playlist_change_details(ID, playlist_id, name = new_name)
        return "Successfully updated name of playlist to %s" % new_name
    if request.method == 'DELETE':
        sp.user_playlist_unfollow(ID, playlist_id)
        return "Successfully deleted playlist"

#Returns a boolean based on whether or not the song is in the playlist_id.
#Both playlist_id and song_id must be ids provided by Spotify
@app.route('/isSongInPlaylist/<playlist_id>/<song_id>')
def is_song_in_playlist(playlist_id, song_id):
    uri = sp.current_user()['uri']
    index = uri.index("user:")
    ID = uri[index+5:]
    result = sp.user_playlist_tracks(ID, playlist_id)
    track_list= result['items']
    track_list_uri = []
    for track in track_list:
        track_list_uri.append(track['track']['uri'])
    for uri in track_list_uri:
        if song_id in uri:
            return jsonify({'is_in_playlist': True})
    return jsonify({'is_in_playlist': False})



if __name__ == '__main__':
    app.run(port=5000, threaded = True)
