import requests

import settings

class Track:
    def __init__(self, title, artist):
        self.title = title
        self.artist = artist

class LastFMError(Exception):
    def __init__(self, code):
        self.code = code
    def __str__(self):
        return f'last.fm error with code {self.code}'

def get_top_tracks(user, count, period):
    res = requests.get('http://ws.audioscrobbler.com/2.0',
                       headers={'Connection': 'close'},
                       params={'method': 'user.gettoptracks', 'format': 'json',
                               'user': user, 'limit': count, 'period': period,
                               'api_key': settings.LASTFM_API_KEY}).json()
    if 'error' in res:
        raise LastFMError(res['error'])
    else:
        return [Track(x['name'], x['artist']['name']) for x in res['toptracks']['track']]
