import difflib


def simplify(s):
    return ''.join(ch.lower() for ch in s if ch.isalnum())


def similar(s1, s2):
    return len(s1) > 0 and len(s2) > 0 and difflib.SequenceMatcher(None, s1, s2).ratio() >= 0.8


def similar_simplified(s1, s2, try_shorten_first=False):
    s1 = simplify(s1)
    s2 = simplify(s2)
    return similar(s1, s2) or (try_shorten_first and len(s1) > len(s2) and similar(s1[:len(s2)], s2))
