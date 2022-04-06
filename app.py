import flask

import comparing
import filtering
import genius
import lastfm
import settings

import logging.config
import random
import sqlite3
import threading
import time

logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'formatter': {
            'format': u'[%(asctime)s] (%(levelname)s/%(name)s): %(message)s'
        }
    },
    'handlers': {
        'info': {
            'class': 'logging.FileHandler',
            'filename': settings.INFO_LOG_PATH,
            'level': 'INFO',
            'formatter': 'formatter',
            'encoding': 'utf-8'
        },
        'error': {
            'class': 'logging.FileHandler',
            'filename': settings.ERROR_LOG_PATH,
            'level': 'ERROR',
            'formatter': 'formatter',
            'encoding': 'utf-8'
        }
    },
    'root': {
        'level': 'INFO',
        'handlers': ['info', 'error']
    }
})

NUM_LOADERS = 15
MAX_NUM_TRIES = 10
RANKS = {
    (90, 100): 'indicating Universal Acclaim',
    (75, 89): 'indicating Generally Favorable Reviews',
    (70, 74): 'indicating Mixed or Average Reviews',
    (69, 69): 'Nice.',
    (50, 68): 'indicating Mixed or Average Reviews',
    (20, 49): 'indicating Generally Unfavorable Reviews',
    (0, 19): 'indicating Overwhelming Dislike'
}

locku = threading.Lock()
lockq = threading.Lock()

class Question:
    def __init__(self, line, title, artist, next_line):
        self.line = line
        self.title = title
        self.artist = artist
        self.next_line = next_line

def load_question(lst, used_tracks, questions, num_tries):
    name = threading.current_thread().name
    for n_try in range(num_tries):
        with lockq:
            if len(questions) >= 10:
                logging.info('{} done (no more questions needed)'.format(name))
                return

        tidx = random.randint(0, len(lst) - 1)
        with locku:
            while tidx in used_tracks:
                tidx = random.randint(0, len(lst) - 1)
            used_tracks.add(tidx)

        lyrics = genius.get_lyrics_by_name(lst[tidx][0], lst[tidx][1])
        with lockq:
            if len(questions) >= 10:
                logging.info('{} done (no more questions needed)'.format(name))
                return

        logging_params = (name, n_try + 1, num_tries, lst[tidx][1], lst[tidx][0])

        if lyrics is None:
            logging.warning('{}, try {}/{}: couldn\'t find song ({} - {})'.format(*logging_params))
            continue
        elif not lyrics:
            logging.warning('{}, try {}/{}: found song but couldn\'t scrape lyrics ({} - {})'.format(*logging_params))
            continue

        lines = lyrics.split('\n')
        slines = [comparing.simplify(x) for x in lines]

        usable = [True] * len(lines)
        duplicate = [False] * len(lines)

        for i in range(len(lines)):
            if not slines[i] or '[' in lines[i]:
                usable[i] = False
                continue
            for j in range(i):
                if usable[j] and comparing.similar(slines[i][:len(slines[j])], slines[j][:len(slines[i])]):
                    duplicate[i] = True
                    duplicate[j] = True
                    break

        valid_pairs = []
        for i in range(len(lines) - 1):
            if not usable[i] or duplicate[i] or not usable[i + 1]:
                continue
            if 15 <= len(slines[i]) <= 50 and \
               15 <= len(slines[i + 1]) <= 50 and \
               '(' not in lines[i] and '(' not in lines[i + 1]:
                valid_pairs.append(i)

        if valid_pairs:
            x = random.choice(valid_pairs)
            with lockq:
                if len(questions) < 10:
                    questions.append(Question(lines[x], lst[tidx][0], lst[tidx][1], lines[x + 1]))
                    logging.info('{}, try {}/{}: loaded question successfully ({} - {})'.format(*logging_params))
                if len(questions) >= 10:
                    logging.info('{} done (no more questions needed)'.format(name))
                    return
        else:
            logging.warning('{}, try {}/{}: loaded lyrics but couldn\'t find a valid pair ({} - {})'
                            .format(*logging_params))

    logging.info('{} done after {} tries'.format(name, num_tries))

def title_decrease(x):
    return {3: 2, 2: 1, 1: 0}[x]

def artist_decrease(x):
    return {3: 2, 2: 1, 1: 0}[x]

def next_line_decrease(x):
    return {4: 3, 3: 1, 1: 0}[x]

def get_rank(x):
    for key in RANKS:
        if key[0] <= x <= key[1]:
            return RANKS[key]

app = flask.Flask(__name__)
app.secret_key = settings.FLASK_SECRET_KEY

def handle_request():
    action = flask.request.form.get('action')

    if action not in ['start', 'get_status', 'get_answers', 'get_score']:
        return {}

    if action != 'start' and 'id' not in flask.session:
        return {'status': 'session_expired'}

    db = sqlite3.connect(settings.DB_PATH)
    db.row_factory = sqlite3.Row

    if action == 'start':
        username = flask.request.form.get('username')
        count = flask.request.form.get('count')
        period = flask.request.form.get('period')

        username = username.strip()
        if not username:
            return {'status': 'invalid_username'}

        logging.info('loading last.fm tracks')
        tracks = lastfm.get_top_tracks(username, int(count), period)
        logging.info('loaded last.fm tracks')

        if tracks and tracks[0] is None:
            if tracks[1] == 6:
                return {'status': 'invalid_username'}
            elif tracks[1] == -1:
                logging.error('unknown error when loading last.fm tracks ({}/{}/{})'.format(username, count, period))
                return {'status': 'unknown_error'}
            else:
                logging.error('last.fm error with code {} ({}/{}/{})'.format(tracks[1], username, count, period))
                return {'status': 'lastfm_error'}
        elif len(tracks) < 50:
            return {'status': 'not_enough_tracks'}

        questions = []
        used_tracks = set()

        logging.info('loading questions')
        threads = [threading.Thread(target=load_question, args=(tracks, used_tracks, questions,
                                    min(MAX_NUM_TRIES, len(tracks) // NUM_LOADERS + int(i < len(tracks) % NUM_LOADERS))),
                                    name='Question Loader {}'.format(i + 1)) for i in range(NUM_LOADERS)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
            with lockq:
                if len(questions) >= 10:
                    break

        with lockq:
            if len(questions) < 10:
                logging.error('failed to load questions ({}/{}/{})'.format(username, count, period))
                return {'status': 'unable_to_load_question'}
            elif len(questions) > 10:  # don't think this can actually happen but just in case
                questions = questions[:10]

        logging.info('loaded questions')

        cursor = db.cursor()
        cursor.execute('INSERT INTO session(timestamp, username, count, period, round, score, '
                       'title_pts, artist_pts, next_line_pts, '
                       'title_done, artist_done, next_line_done, '
                       'title_last, artist_last, next_line_last) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)',
                       (int(time.time()), username, count, period, 0, 0, 3, 3, 4, 0, 0, 0, '', '', ''))
        sid = cursor.lastrowid
        flask.session['id'] = sid

        with lockq:
            for i, question in enumerate(questions):
                cursor.execute('INSERT INTO question(session_id, round_id, line, title, artist, next_line) '
                               'VALUES (?, ?, ?, ?, ?, ?)',
                               (sid, i, question.line, question.title, question.artist, question.next_line))

        db.commit()

        return {'status': 'ok'}
    else:
        sid = flask.session['id']
        cursor = db.cursor()

        cursor.execute('SELECT * FROM session WHERE id = ?', (sid,))
        data = cursor.fetchone()

        if data is None:
            return {'status': 'session_expired'}
        else:
            ses = dict(data)

        cursor.execute('SELECT * FROM question WHERE session_id = ? AND round_id = ?', (sid, ses['round']))
        question = cursor.fetchone()

        ret = {}

        if action == 'get_status':
            title = flask.request.form.get('title')
            artist = flask.request.form.get('artist')
            next_line = flask.request.form.get('next_line')

            if title or artist or next_line:
                title = title.strip()
                artist = artist.strip()
                next_line = next_line.strip()

                if title and title != ses['title_last'] and not ses['title_done']:
                    ses['title_last'] = title
                    answer = question['title']

                    guessed_correctly = comparing.similar_simplified(title, answer)
                    if not guessed_correctly:
                        for flt in [filtering.TITLE_JUNK_FILTERS, filtering.BRACKET_FILTERS]:
                            old_answer, answer = answer, filtering.apply_filters(answer, flt)
                            if old_answer != answer and comparing.similar_simplified(title, answer,
                                                                                     try_shorten_first=True):
                                guessed_correctly = True
                                break

                    if guessed_correctly:
                        ret['title_feedback'] = 'success'
                        ses['title_done'] = True
                        ses['score'] += ses['title_pts']
                    else:
                        ses['title_pts'] = title_decrease(ses['title_pts'])
                        if ses['title_pts'] == 0:
                            ret['title_feedback'] = 'locked'
                            ses['title_done'] = True
                        else:
                            ret['title_feedback'] = 'fail'

                if artist and artist != ses['artist_last'] and not ses['artist_done']:
                    ses['artist_last'] = artist
                    answer = question['artist']

                    guessed_correctly = comparing.similar_simplified(artist, answer)
                    if not guessed_correctly:
                        for flt in [filtering.ARTIST_JUNK_FILTERS, filtering.BRACKET_FILTERS]:
                            old_answer, answer = answer, filtering.apply_filters(answer, flt)
                            if old_answer != answer and comparing.similar_simplified(artist, answer,
                                                                                     try_shorten_first=True):
                                guessed_correctly = True
                                break

                    if guessed_correctly:
                        ret['artist_feedback'] = 'success'
                        ses['artist_done'] = True
                        ses['score'] += ses['artist_pts']
                    else:
                        ses['artist_pts'] = artist_decrease(ses['artist_pts'])
                        if ses['artist_pts'] == 0:
                            ret['artist_feedback'] = 'locked'
                            ses['artist_done'] = True
                        else:
                            ret['artist_feedback'] = 'fail'

                if next_line and next_line != ses['next_line_last'] and not ses['next_line_done']:
                    ses['next_line_last'] = next_line
                    sguess = comparing.simplify(next_line)
                    sline = comparing.simplify(question['next_line'])

                    if len(sguess) < len(sline) - 5:
                        ret['next_line_feedback'] = 'too short'
                    elif comparing.similar_simplified(sguess, sline, try_shorten_first=True):
                        ret['next_line_feedback'] = 'success'
                        ses['next_line_done'] = True
                        ses['score'] += ses['next_line_pts']
                    else:
                        ses['next_line_pts'] = next_line_decrease(ses['next_line_pts'])
                        if ses['next_line_pts'] == 0:
                            ret['next_line_feedback'] = 'locked'
                            ses['next_line_done'] = True
                        else:
                            ret['next_line_feedback'] = 'fail'

            round_ended = int(ses['title_done'] and ses['artist_done'] and ses['next_line_done'])

            ret.update({
                'status': 'ok',
                'round': ses['round'] + 1,
                'question': question['line'],
                'title_pts': ses['title_pts'],
                'artist_pts': ses['artist_pts'],
                'next_line_pts': ses['next_line_pts'],
                'score': ses['score'],
                'max_score': (ses['round'] + 1) * 10,
                'round_ended': round_ended,
                'game_ended': int(round_ended and ses['round'] + 1 == 10),
            })

        elif action == 'get_answers':  # also switches to next round
            ses['round'] += 1
            ses['title_pts'] = 3
            ses['artist_pts'] = 3
            ses['next_line_pts'] = 4
            ses['title_done'] = False
            ses['artist_done'] = False
            ses['next_line_done'] = False
            ses['title_last'] = ''
            ses['artist_last'] = ''
            ses['next_line_last'] = ''

            ret = {
                'status': 'ok',
                'title': question['title'],
                'artist': question['artist'],
                'next_line': question['next_line'],
                'game_ended': int(ses['round'] == 10)
            }

        elif action == 'get_score':
            ret = {
                'status': 'ok',
                'score': ses['score'],
                'rank': get_rank(ses['score'])
            }

        ses['timestamp'] = int(time.time())
        fields = []
        values = []
        for x in ses:
            fields.append('{} = ?'.format(x))
            values.append(ses[x])
        values.append(sid)
        cursor.execute('UPDATE session SET ' + ', '.join(fields) + ' WHERE id = ?', tuple(values))
        db.commit()

        return ret

@app.route('/', methods=['GET', 'POST'])
def main():
    if flask.request.method in ('GET', 'HEAD'):
        return flask.render_template('app.html')
    elif flask.request.method == 'POST':
        logging.info('RECEIVED {}'.format(dict(sorted(flask.request.form.items()))))
        ret = handle_request()
        logging.info('RETURNED {}'.format(dict(sorted(ret.items()))))
        return ret

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT, threaded=True)
