import logging.config
import random
import sqlite3
import threading

import flask

import comparing
import filters
import genius
import lastfm
import settings


logging.config.dictConfig({
    'version': 1,
    'formatters': {
        'formatter': {
            'format': '[%(asctime)s] %(name)s %(levelname)s in %(threadName)s: %(message)s'
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
        for filter_list in [filters.TITLE_JUNK, filters.BRACKETS]:
            alt_title = filters.apply(self.titles[-1], filter_list)
            if alt_title != self.titles[-1]:
                self.titles.append(filters.apply(alt_title, filters.CLEANUP))

        self.artists = [artist]
        for filter_list in [filters.ARTIST_JUNK, filters.BRACKETS]:
            alt_artist = filters.apply(self.artists[-1], filter_list)
            if alt_artist != self.artists[-1]:
                self.artists.append(filters.apply(alt_artist, filters.CLEANUP))

        self.next_line = next_line


def load_questions(tracks, questions, tracks_lock, questions_lock):
    while True:
        with questions_lock:
            if len(questions) >= 10:
                logging.info('done (no more questions needed)')
                return

        try:
            with tracks_lock:
                track = next(tracks)
        except StopIteration:
            logging.warning('exiting (out of tracks)')
            return

        lyrics = genius.get_lyrics_by_name(track.title, track.artist)

        with questions_lock:
            if len(questions) >= 10:
                logging.info('done (no more questions needed)')
                return

        if lyrics is None:
            logging.warning(f'{track}: couldn\'t find track on genius')
            continue
        elif not lyrics:
            logging.warning(f'{track}: found track on genius but couldn\'t scrape lyrics')
            continue

        lines = lyrics.split('\n')
        simplified_lines = [comparing.simplify(line) for line in lines]
        is_lyric = [
            len(simple_line) > 0 and '[' not in line
            for line, simple_line in zip(lines, simplified_lines)
        ]

        duplicate = [False] * len(lines)
        for i in range(len(lines)):
            if not is_lyric[i]:
                continue
            for j in range(i):
                min_len = min(len(simplified_lines[i]), len(simplified_lines[j]))
                if is_lyric[j] and comparing.similar(simplified_lines[i][:min_len], simplified_lines[j][:min_len]):
                    duplicate[i] = True
                    duplicate[j] = True
                    break

        playable = [
            is_lyr and 15 <= len(simple_line) <= 50 and '(' not in line
            for line, simple_line, is_lyr in zip(lines, simplified_lines, is_lyric)
        ]

        valid_pairs = [
            (lines[i], lines[i + 1])
            for i in range(len(lines) - 1)
            if playable[i] and playable[i + 1] and not duplicate[i]
        ]

        if valid_pairs:
            line, next_line = random.choice(valid_pairs)
            with questions_lock:
                if len(questions) < 10:
                    questions.append(Question(line, track.title, track.artist, next_line))
                    logging.info(f'{track}: loaded question successfully')
                if len(questions) >= 10:
                    logging.info('done (no more questions needed)')
                    return
        else:
            logging.warning(f'{track}: loaded lyrics but couldn\'t find a valid pair')


app = flask.Flask(__name__)
app.secret_key = settings.FLASK_SECRET_KEY


def handle_post_request():
    action = flask.request.form.get('action')

    if action == 'start':
        username = flask.request.form.get('username')
        count = flask.request.form.get('count')
        period = flask.request.form.get('period')
        if username is None \
                or count not in ['50', '100', '200', '500', '1000'] \
                or period not in ['overall', '7day', '1month', '3month', '6month', '12month']:
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
            unplayed_tracks = []
            played_tracks = []
            for track in tracks:
                if (track.title, track.artist) in used_tracks:
                    played_tracks.append(track)
                else:
                    unplayed_tracks.append(track)
            random.shuffle(unplayed_tracks)
            random.shuffle(played_tracks)
            tracks = unplayed_tracks[:140] + played_tracks[:10]
        else:
            random.shuffle(tracks)
            tracks = tracks[:150]

        tracks_iter = iter(tracks)
        questions = []
        tracks_lock = threading.Lock()
        questions_lock = threading.Lock()
        name = threading.current_thread().name

        logging.info('loading questions')
        threads = [
            threading.Thread(
                target=load_questions,
                args=(tracks_iter, questions, tracks_lock, questions_lock),
                name=f'{name}/Loader-{i + 1}'
            )
            for i in range(15)
        ]

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
            questions_data = [vars(question) for question in questions]

        db.commit()
        return {'status': 'ok', 'questions': questions_data}
    elif action == 'submit_score':
        try:
            round = int(flask.request.form.get('round'))
            title_pts = int(flask.request.form.get('title_pts'))
            artist_pts = int(flask.request.form.get('artist_pts'))
            next_line_pts = int(flask.request.form.get('next_line_pts'))
        except ValueError:
            return {'status': 'bad_request'}
        if not (1 <= round <= 10 and 0 <= title_pts <= 3 and 0 <= artist_pts <= 3 and next_line_pts in [0, 1, 3, 4]):
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
        logging.info(f'received {dict(flask.request.form.items())}')
        try:
            response = handle_post_request()
        except:
            logging.exception('exception while processing post request:')
            response = {'status': 'unknown_error'}
        logging.info(f'returned {response}')
        return response
    else:
        return flask.render_template('app.html')


if __name__ == '__main__':
    app.run(host=settings.HOST, port=settings.PORT, threaded=True)
