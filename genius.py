import bs4
import requests

import comparing
import filters
import settings


def search(query):
    res = requests.get('https://api.genius.com/search', {'access_token': settings.GENIUS_API_TOKEN, 'q': query}).json()
    return [hit['result'] for hit in res['response']['hits']]


def get_lyrics(song):
    res = requests.get(song['url']).content.decode('utf-8')[2:-1]
    paragraphs = bs4.BeautifulSoup(res, 'lxml').find_all(attrs={'data-lyrics-container': 'true'})
    for par in paragraphs:
        for br in par.find_all('br'):
            br.replace_with('\n')
    return '\n'.join(par.text for par in paragraphs)


def get_lyrics_by_name(title, artist, try_junk_filters=True, debug_mode=False):
    """
    Returns a string containing the lyrics, or None if the song wasn't found on Genius,
    or an empty string if the song was found but the lyrics couldn't be scraped.
    """
    if debug_mode:
        print(f'Looking for  {artist} - {title}')

    results = search(f'{title} {artist}')[:3]
    for result in results:
        gen_title = result['title']
        gen_artist = result['primary_artist']['name']

        title_matches = comparing.similar_simplified(title, gen_title)
        if not title_matches:
            gen_title_alt = filters.apply(gen_title, filters.GENIUS_CYRILLIC)
            title_matches = comparing.similar_simplified(title, gen_title_alt)

        artist_matches = comparing.similar_simplified(artist, gen_artist)
        if not artist_matches:
            gen_artist_alt = filters.apply(gen_artist, filters.GENIUS_ARTIST_ALIAS + filters.GENIUS_CYRILLIC)
            artist_matches = comparing.similar_simplified(title, gen_artist_alt)

        if title_matches and artist_matches:
            if debug_mode:
                print(f'Matched with {gen_artist} - {gen_title}')
            return get_lyrics(result)

    if try_junk_filters:
        new_title = filters.apply(title, filters.TITLE_JUNK)
        new_artist = filters.apply(artist, filters.ARTIST_JUNK)
        if new_title != title or new_artist != artist:
            return get_lyrics_by_name(new_title, new_artist, try_junk_filters=False, debug_mode=debug_mode)

    return None
