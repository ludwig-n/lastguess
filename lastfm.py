import requests

import settings

import json

def get_top_tracks(user, count, period):
    try:
        res = requests.get('http://ws.audioscrobbler.com/2.0',
                           headers={'Connection': 'close'},
                           params={'method': 'user.gettoptracks', 'format': 'json',
                                   'user': user, 'limit': count, 'period': period,
                                   'api_key': settings.LASTFM_API_KEY}).json()
    except (requests.exceptions.ProxyError, requests.exceptions.SSLError, json.decoder.JSONDecodeError):
        return None, -1

    if 'error' in res:
        return None, res['error']

    return [(x['name'], x['artist']['name']) for x in res['toptracks']['track']]
