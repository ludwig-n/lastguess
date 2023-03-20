import logging.config
import random
import sqlite3
import threading

import flask

import comparing
import filtering
import genius
import lastfm
import settings

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

class Question:
    def __init__(self, line, title, artist, next_line):
        self.line = line

        self.titles = [title]
        for filter_list in (filtering.TITLE_JUNK_FILTERS, filtering.BRACKET_FILTERS):
            alt = filtering.apply_filters(self.titles[-1], filter_list)
            if alt != self.titles[-1]:
                self.titles.append(filtering.apply_filters(alt, filtering.CLEANUP_FILTERS))

        self.artists = [artist]
        for filter_list in (filtering.ARTIST_JUNK_FILTERS, filtering.BRACKET_FILTERS):
            alt = filtering.apply_filters(self.artists[-1], filter_list)
            if alt != self.artists[-1]:
                self.artists.append(filtering.apply_filters(alt, filtering.CLEANUP_FILTERS))

        self.next_line = next_line

track_enumerator_lock = threading.Lock()
questions_lock = threading.Lock()

def load_questions(track_enumerator, questions, max_total_tries=150):
    name = threading.current_thread().name
    while True:
        with questions_lock:
            if len(questions) >= 10:
                logging.info(f'{name} done (no more questions needed)')
                return

        with track_enumerator_lock:
            try:
                index, track = next(track_enumerator)
            except StopIteration:
                logging.warning(f'{name} exiting (out of tracks)')
                return
        if index >= max_total_tries:
            logging.warning(f'{name} exiting (exceeded {max_total_tries} total tries)')
            return

        lyrics = genius.get_lyrics_by_name(track.title, track.artist)
        
        with questions_lock:
            if len(questions) >= 10:
                logging.info(f'{name} done (no more questions needed)')
                return

        logging_prefix = f'{name}, track {index + 1} ({track.artist} - {track.title}):'

        if lyrics is None:
            logging.warning(f'{logging_prefix} couldn\'t find track on genius')
            continue
        elif not lyrics:
            logging.warning(f'{logging_prefix} found track on genius but couldn\'t scrape lyrics')
            continue

        lines = lyrics.split('\n')
        simplified_lines = [comparing.simplify(x) for x in lines]

        usable = [True] * len(lines)
        duplicate = [False] * len(lines)

        for i in range(len(lines)):
            if not simplified_lines[i] or '[' in lines[i]:
                usable[i] = False
                continue
            for j in range(i):
                if usable[j] and comparing.similar(simplified_lines[i][:len(simplified_lines[j])],
                                                   simplified_lines[j][:len(simplified_lines[i])]):
                    duplicate[i] = True
                    duplicate[j] = True
                    break

        valid_pairs = []
        for i in range(len(lines) - 1):
            if usable[i] and \
                    usable[i + 1] and \
                    not duplicate[i] and \
                    15 <= len(simplified_lines[i]) <= 50 and \
                    15 <= len(simplified_lines[i + 1]) <= 50 and \
                    '(' not in lines[i] and \
                    '(' not in lines[i + 1]:
                valid_pairs.append((lines[i], lines[i + 1]))

        if valid_pairs:
            line, next_line = random.choice(valid_pairs)
            with questions_lock:
                if len(questions) < 10:
                    questions.append(Question(line, track.title, track.artist, next_line))
                    logging.info(f'{logging_prefix} loaded question successfully')
                if len(questions) >= 10:
                    logging.info(f'{name} done (no more questions needed)')
                    return
        else:
            logging.warning(f'{logging_prefix} loaded lyrics but couldn\'t find a valid pair')

app = flask.Flask(__name__)
app.secret_key = settings.FLASK_SECRET_KEY

def handle_post_request():
    action = flask.request.form.get('action')

    if action == 'start':
        username = flask.request.form.get('username')
        count = flask.request.form.get('count')
        period = flask.request.form.get('period')
        if username is None \
                or count not in ('50', '100', '200', '500', '1000') \
                or period not in ('overall', '7day', '1month', '3month', '6month', '12month'):
            return {'status': 'bad_request'}

        username = username.lower()

        logging.info('loading last.fm tracks')
        try:
            tracks = lastfm.get_top_tracks(username, int(count), period)
        except lastfm.LastFMError as error:
            if error.code == 6:
                return {'status': 'invalid_username'}
            elif error.code == 8:
                logging.error('last.fm returned error code 8')
                return {'status': 'lastfm_down'}
            else:
                raise
        logging.info('loaded last.fm tracks')

        if len(tracks) < 10:
            return {'status': 'not_enough_tracks'}

        db = sqlite3.connect(settings.DB_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()

        cursor.execute('SELECT question.title, question.artist FROM game INNER JOIN question ON game.username = ? '
                       'AND game.id = question.game_id AND game.rounds_completed + 1 >= question.round '
                       'ORDER BY game.time_updated DESC LIMIT ?', (username, int(count) * 3 // 5))
        used_tracks = {(row['title'], row['artist']) for row in cursor.fetchall()}

        if used_tracks:
            primary_tracks = []
            secondary_tracks = []
            for track in tracks:
                if (track.title, track.artist) in used_tracks:
                    secondary_tracks.append(track)
                else:
                    primary_tracks.append(track)

            random.shuffle(primary_tracks)
            random.shuffle(secondary_tracks)
            tracks = primary_tracks + secondary_tracks
        else:
            random.shuffle(tracks)

        track_enumerator = enumerate(tracks)
        questions = []

        logging.info('loading questions')
        threads = [threading.Thread(target=load_questions, args=(track_enumerator, questions),
                                    name=f'Question Loader {i + 1}') for i in range(15)]

        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
            with questions_lock:
                if len(questions) >= 10:
                    break

        with questions_lock:
            if len(questions) < 10:
                logging.error(f'failed to load questions ({username}/{count}/{period})')
                return {'status': 'failed_to_load_questions'}
            elif len(questions) > 10:  # don't think this can actually happen but just in case
                questions = questions[:10]

        logging.info('loaded questions')

        cursor.execute('INSERT INTO game(time_updated, username, count, period, rounds_completed, score) '
                       'VALUES (strftime("%s"), ?, ?, ?, 0, 0)', (username, count, period))
        flask.session['game_id'] = game_id = cursor.lastrowid

        with questions_lock:
            for i, question in enumerate(questions, start=1):
                cursor.execute('INSERT INTO question(game_id, round, line, title, artist, next_line, '
                               'title_pts, artist_pts, next_line_pts) VALUES (?, ?, ?, ?, ?, ?, NULL, NULL, NULL)',
                               (game_id, i, question.line, question.titles[0], question.artists[0], question.next_line))

        db.commit()

        return {'status': 'ok', 'questions': [vars(question) for question in questions]}
    elif action == 'submit_score':
        try:
            round = int(flask.request.form.get('round'))
            title_pts = int(flask.request.form.get('title_pts'))
            artist_pts = int(flask.request.form.get('artist_pts'))
            next_line_pts = int(flask.request.form.get('next_line_pts'))
        except ValueError:
            return {'status': 'bad_request'}
        if not (1 <= round <= 10 and 0 <= title_pts <= 3 and 0 <= artist_pts <= 3 and next_line_pts in (0, 1, 3, 4)):
            return {'status': 'bad_request'}

        game_id = flask.session.get('game_id')
        if game_id is None:
            return {'status': 'game_not_found'}

        db = sqlite3.connect(settings.DB_PATH)
        db.row_factory = sqlite3.Row
        cursor = db.cursor()

        cursor.execute('SELECT score, rounds_completed FROM game WHERE id = ?', (game_id,))
        row = cursor.fetchone()
        if row is None:
            return {'status': 'game_not_found'}

        cursor.execute('UPDATE game SET time_updated = strftime("%s"), rounds_completed = ?, score = ? WHERE id = ?',
                       (row['rounds_completed'] + 1, row['score'] + title_pts + artist_pts + next_line_pts, game_id))
        cursor.execute('UPDATE question SET title_pts = ?, artist_pts = ?, next_line_pts = ? '
                       'WHERE game_id = ? AND round = ?', (title_pts, artist_pts, next_line_pts, game_id, round))
        db.commit()

        return {'status': 'ok'}
    else:
        return {'status': 'bad_request'}

@app.route('/', methods=['GET', 'POST'])
def main():
    if flask.request.method == 'POST':
        logging.info(f'RECEIVED {dict(flask.request.form.items())}')
        try:
            response = handle_post_request()
        except:
            logging.exception('exception while processing post request:')
            response = {'status': 'unknown_error'}
        logging.info(f'RETURNED {response}')
        return response
    else:
        return flask.render_template('app.html')

if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT, threaded=True)
