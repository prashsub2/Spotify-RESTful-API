from flask import Flask, jsonify, request, url_for, abort, g, render_template
from models import db, User
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import relationship, sessionmaker, scoped_session
from sqlalchemy import create_engine
import spotipy
import sys
import pprint
from flask_httpauth import HTTPBasicAuth
import json
from flask_sqlalchemy import SQLAlchemy
import tempfile
import os.path

#NEW IMPORTS
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
from flask import make_response
import requests

auth = HTTPBasicAuth()
app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///test.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)
db.create_all()

def test():
    h = httplib2.Http()
    headers = {"Content-type":"application/x-www-form-urlencoded",
    "Authorization":"Basic OGQ1MjcyZjlmMDBmNGE0NGJmZmIyZTNjYjEzYzVmM2E6MzhmMTgwYzRhMWVkNGFjMzhmYmI1OGQ3M2JkOGEzNGI="}
    uri = "https://accounts.spotify.com/api/token?grant_type=refresh_token&refresh_token=AQD3xUeQOkG6Hayr6pY1oc1vPAWqiqLKfF0mq_Fl-BMOaAI7UHBXjde42Oez_Di0ntVvTwfSRcpWjyrpcUbtEAUwIRA0CFeOuMrWHhYGSBmvmB6h6x6M3s77DpRxYxpLOZg"
    resp,content = h.request(uri, "POST",  headers = headers)
    content = content.decode("utf-8")
    content = json.loads(content)
    return content['access_token']

token = test()
sp = spotipy.Spotify(auth = token)

@app.route('/')
def helpMessage():
    return "Please try and access an useful endpoint"



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

@app.route('/clientOAuth')
def start():
    return render_template('clientOAuth.html')

@app.route('/oauth', methods = ['POST'])
def login():
    #STEP 1 - Parse the auth code
    authcode = '4/25uDaJMoyfGSgm5RIwmht9zMv3mDCl9QOTmThQEtH2M'
    print("Step 1 - Complete, received auth code %s" % authcode)
    if len(authcode)>0:
        #STEP 2 - Exchange for a token
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

        # # Verify that the access token is used for the intended user.
        # gplus_id = credentials.id_token['sub']
        # if result['user_id'] != gplus_id:
        #     response = make_response(json.dumps("Token's user ID doesn't match given user ID."), 401)
        #     response.headers['Content-Type'] = 'application/json'
        #     return response

        # # Verify that the access token is valid for this app.
        # if result['issued_to'] != CLIENT_ID:
        #     response = make_response(json.dumps("Token's client ID does not match app's."), 401)
        #     response.headers['Content-Type'] = 'application/json'
        #     return response

        # stored_credentials = login_session.get('credentials')
        # stored_gplus_id = login_session.get('gplus_id')
        # if stored_credentials is not None and gplus_id == stored_gplus_id:
        #     response = make_response(json.dumps('Current user is already connected.'), 200)
        #     response.headers['Content-Type'] = 'application/json'
        #     return response
        print ("Step 2 Complete! Access Token : %s " % credentials.access_token)

        #STEP 3 - Find User or make a new one

        #Get user info
        h = httplib2.Http()
        userinfo_url =  "https://www.googleapis.com/oauth2/v1/userinfo"
        params = {'access_token': credentials.access_token, 'alt':'json'}
        answer = requests.get(userinfo_url, params=params)

        data = answer.json()

        name = data['name']
        picture = data['picture']
        email = data['email']



        #see if user exists, if it doesn't make a new one
        user = db.session.query(User).filter_by(email=email).first()
        if not user:
            user = User(username = name, picture = picture, email = email)
            db.session.add(user)
            db.session.commit()



        #STEP 4 - Make token
        token = user.generate_auth_token(600)



        #STEP 5 - Send back token to the client
        return jsonify({'token': token.decode('ascii')})

        #return jsonify({'token': token.decode('ascii'), 'duration': 600})
    else:
        return 'Unrecoginized Provider'

@app.route('/getArtistName/<uri>')
@auth.login_required
def displayArtist(uri):
    result = sp.artist(uri)
    artist = result['name']
    return jsonify(name = artist)

@app.route('/getRelatedArtists/<query>')
@auth.login_required
def displayRelatedArtists(query):

    result = sp.search(query, type = 'artist')
    uri = result['artists']['items'][0]['uri']
    secondResult = sp.artist_related_artists(uri)
    relatedArtistsList = secondResult['artists']
    artistList = [{}]
    for artist in relatedArtistsList:
        artistList.append({'artist':artist['name'], 'genre':artist['genres'][0]})
    artistList.pop(0)
    return jsonify(artistList)

@app.route('/getAlbums/<query>')
@auth.login_required
def displayAlbums(query):
    result = sp.search(query, type = 'artist')
    uri = result['artists']['items'][0]['uri']
    secondResult = sp.artist_albums(uri, 'album')
    itemsList = secondResult['items']
    artistsList = []
    albumList = [{}]
    for album in itemsList:
        for artist in album['artists']:
            artistsList.append(artist['name'])
        albumList.append({'name' : album['name'], 'artists' : artistsList})
        artistsList = []
    albumList.pop(0)
    return jsonify(albumList)

@app.route('/getAudio/<query>')
@auth.login_required
def getAudioAnalysis(query):
    result = sp.search(query, type = 'track')
    uri = result['tracks']['items'][0]['uri']
    secondResult = sp.audio_analysis(uri)
    return jsonify(secondResult)


if __name__ == '__main__':
    app.run(port=5000, threaded = True)
