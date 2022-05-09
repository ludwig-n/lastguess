import bs4
import requests

import comparing
import filtering
import settings

def search(query):
    res = requests.get('https://api.genius.com/search',
                       params={'access_token': settings.GENIUS_API_TOKEN, 'q': query}).json()

    return [x['result'] for x in res['response']['hits']]

def get_lyrics(song):
    res = requests.get(song['url']).content.decode('utf-8')[2:-1]

    paragraphs = bs4.BeautifulSoup(res, 'lxml').find_all(attrs={'data-lyrics-container': 'true'})
    for par in paragraphs:
        for br in par.find_all('br'):
            br.replace_with('\n')
    return '\n'.join([par.text for par in paragraphs])

def get_lyrics_by_name(title, artist, try_junk_filters=True, debug_mode=False):
    """Returns a string containing the lyrics, or None if the song wasn't found on Genius,
    or an empty string if the song was found but the lyrics couldn't be scraped."""
    if debug_mode:
        print('Looking for  {} - {}'.format(artist, title))

    results = search(title + ' ' + artist)[:3]
    for x in results:
        if (comparing.similar_simplified(title, x['title']) or
            comparing.similar_simplified(title, filtering.apply_filters(x['title'],
                                                                        filtering.GENIUS_CYRILLIC_FILTERS))) and \
           (comparing.similar_simplified(artist, x['primary_artist']['name']) or
            comparing.similar_simplified(artist, filtering.apply_filters(x['primary_artist']['name'],
                                                                         filtering.GENIUS_ARTIST_ALIAS_FILTERS +
                                                                         filtering.GENIUS_CYRILLIC_FILTERS))):
            if debug_mode:
                print('Matched with {} - {}'.format(x['primary_artist']['name'], x['title']))
            return get_lyrics(x)

    if try_junk_filters:
        new_title = filtering.apply_filters(title, filtering.TITLE_JUNK_FILTERS)
        new_artist = filtering.apply_filters(artist, filtering.ARTIST_JUNK_FILTERS)
        if new_title != title or new_artist != artist:
            return get_lyrics_by_name(new_title, new_artist, try_junk_filters=False, debug_mode=debug_mode)

    return None
