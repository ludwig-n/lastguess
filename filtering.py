import re

# Broadest alternatives first
JUNK_TAGS_CORE = r'''
(
[^()[\]\/-]*re-?master.*|
[^()[\]\/-]+\smix\s\d{4}|
(?:f(ea)?t\.|with|vs\.)\s.+|
live(?:\s.+)?|
(?:re-?)?recorded(?:\s.+)?|
(?:(?:album|single)\sversion)|
(?:(?:mono|stereo)(?:\sversion)?)|
original(?:[^()[\]\/-]*version.*)?|
(?:\d{4}|ultimate|(?:new\s)?(?:mono|stereo)|special)\smix|
explicit|
clean|
b-side|
bonus\strack|
parody\sof\s.+|
from\s".+".*
)
'''

# " (Junk Tag)" or " [Junk Tag]" or " - Junk Tag" or " / Junk Tag"
JUNK_TAGS_FULL = r'\s(\({0}\)|\[{0}\]|-\s{0}|\/\s{0}).*$'.format(JUNK_TAGS_CORE)

TITLE_JUNK_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE | re.VERBOSE), x[1]) for x in [
    (JUNK_TAGS_FULL, ''),
]]

ARTIST_JUNK_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE), x[1]) for x in [
    # Unlike the one in JUNK_TAGS_CORE, also allows "X feat. Y"
    (r'\s[([]?(f(ea)?t\.|with|vs\.)\s.+$', ''),
]]

GENIUS_CYRILLIC_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE), x[1]) for x in [
    # Кириллическое название (Latin Translation)
    (r'(.*[\u0400-\u04ff].*)\s\([^\u0400-\u04ff]+\)$', r'\1'),
]]

GENIUS_ARTIST_ALIAS_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE), x[1]) for x in [
    # When Genius has a wacky name for the artist
    (r'^Queen & David Bowie$', r'Queen'),
    (r'^Freddie Mercury and Montserrat Caballé$', r'Freddie Mercury'),
    (r'^Paul McCartney & Wings$', r'Wings'),
    (r'^Silk Sonic$', r'Bruno Mars'),
    (r'^Ariana Grande & Doja Cat$', r'Ariana Grande'),
    (r'^Young Stoner Life & Young Thug$', r'Young Stoner Life'),
]]

BRACKET_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE), x[1]) for x in [
    # Remove (these) and [these] brackets with their contents
    # 2x to allow one level of nesting
    (r'\([^()]*\)|\[[^[\]]\]]', ''),
]] * 2

CLEANUP_FILTERS = [(re.compile(x[0], flags=re.IGNORECASE), x[1]) for x in [
    # Remove leading and trailing spaces/dashes/slashes
    (r'^[\s/-]+|[\s/-]+$', ''),
    # Collapse multiple spaces in a row
    (r'\s+', r' '),
]]

def apply_filters(s, filters):
    for pattern, replacement in filters:
        s = pattern.sub(replacement, s)
    return s

if __name__ == '__main__':
    # Test main regex
    print(JUNK_TAGS_FULL.replace('\n', ''))
