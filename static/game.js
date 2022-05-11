let questions;
let round;
let score;
let title_last, artist_last, next_line_last;
let title_done, artist_done, next_line_done;
let title_pts, artist_pts, next_line_pts;

function simplify(s) {
    return s.replace(/[^\p{L}\p{N}]/ug, '').toLowerCase();
}

function similar(s1, s2) {
    return s1 && s2 && (new difflib.SequenceMatcher(null, s1, s2)).ratio() >= 0.8;
}

function similar_simplified(s1, s2, try_shorten_first = false) {
    s1 = simplify(s1);
    s2 = simplify(s2);
    return similar(s1, s2) || (try_shorten_first && s1.length > s2.length && similar(s1.slice(0, s2.length), s2));
}

// mobile keyboard fix (god bless user13442212 from stackoverflow)
let viewport = document.querySelector('meta[name=viewport]');
viewport.setAttribute('content', viewport.content + ', height=' + window.innerHeight);

switch_theme_to(localStorage.getItem('theme'));

$(document).ready(function () {
    let war_fucked = false;
    let game_loaded = false;

    switch_theme_to(localStorage.getItem('theme'));

    $('#start').submit(function (event) {
        event.preventDefault();

        let username = $('#lg-username').val().trim();
        let count = $('#count').val();
        let period = $('#period').val();

        if (!username) {
            show_error('please enter a last.fm username');
            return;
        }

        $('#start').children().prop('disabled', true);
        $('#start-feed').html('&nbsp;');

        let button = $('#start-button');
        button.html('working<span id="d1">.</span><span id="d2">.</span><span id="d3">.</span>');

        let state = 0;
        let interval = setInterval(function () {
            if (state === 0) {
                button.children().css('opacity', 0);
            } else {
                $(`#d${state}`).css('opacity', 1);
            }
            state = (state + 1) % 4;
        }, 500);

        $.post('/', {
            'action': 'start',
            'username': username,
            'count': count,
            'period': period
        }).done(function (res) {
            if (res['status'] === 'ok') {
                questions = res['questions'];
                round = 0;
                score = 0;
                advance_round();
                game_loaded = true;
                if (!war_fucked) {
                    fade_between('#start', '#game');
                }
                clearInterval(interval);
            } else if (res['status'] === 'invalid_username') {
                show_error('invalid last.fm username');
            } else if (res['status'] === 'not_enough_tracks') {
                show_error('not enough tracks scrobbled in this time period');
            } else if (res['status'] === 'failed_to_load_questions') {
                show_error('couldn\'t find enough lyrics to play, try a different song range');
            } else if (res['status'] === 'lastfm_down') {
                show_error('looks like last.fm is down, please try again later');
            } else {
                show_error('something went wrong, please try again');
            }
        });
    });

    $('#game').submit(function (event) {
        event.preventDefault();

        if (title_done && artist_done && next_line_done) {
            return;
        }

        let active = document.activeElement;

        if (!title_done) {
            let guess = $('#lg-title').val().trim();
            if (guess && guess !== title_last) {
                title_last = guess;
                let titles = questions[round - 1]['titles'];
                let verdict;
                if (titles.some((answer, index) => similar_simplified(guess, answer, index > 0))) {
                    verdict = 'correct';
                    title_done = true;
                    score += title_pts;
                } else {
                    verdict = 'incorrect';
                    --title_pts;
                    if (title_pts === 0) {
                        title_done = true;
                    }
                }
                update_box_and_feed($('#lg-title'), $('#title-feed'), title_pts, verdict);
            }
        }

        if (!artist_done) {
            let guess = $('#lg-artist').val().trim();
            if (guess && guess !== artist_last) {
                artist_last = guess;
                let artists = questions[round - 1]['artists'];
                let verdict;
                if (artists.some((answer, index) => similar_simplified(guess, answer, index > 0))) {
                    verdict = 'correct';
                    artist_done = true;
                    score += artist_pts;
                } else {
                    verdict = 'incorrect';
                    --artist_pts;
                    if (artist_pts === 0) {
                        artist_done = true;
                    }
                }
                update_box_and_feed($('#lg-artist'), $('#artist-feed'), artist_pts, verdict);
            }
        }

        if (!next_line_done) {
            let guess = $('#lg-next-line').val().trim();
            if (guess && guess !== next_line_last) {
                next_line_last = guess;
                let answer = questions[round - 1]['next_line'];
                let verdict;
                if (simplify(guess).length < simplify(answer).length - 5) {
                    verdict = 'too short';
                } else if (similar_simplified(guess, answer, true)) {
                    verdict = 'correct';
                    next_line_done = true;
                    score += next_line_pts;
                } else {
                    verdict = 'incorrect';
                    --next_line_pts;
                    if (next_line_pts === 2) {
                        --next_line_pts;
                    } else if (next_line_pts === 0) {
                        next_line_done = true;
                    }
                }
                update_box_and_feed($('#lg-next-line'), $('#next-line-feed'), next_line_pts, verdict);
            }
        }

        $('#score-feed').html(`${score} out of ${round * 10} points so far`);

        if (title_done && artist_done && next_line_done) {
            show_answers();
        } else if (active.disabled) {
            let boxes = ['lg-title', 'lg-artist', 'lg-next-line'];
            let ind = boxes.indexOf(active.id);
            if (ind !== -1) {
                while ([title_done, artist_done, next_line_done][ind]) {
                    ind = (ind + 1) % 3;
                }
                document.getElementById(boxes[ind]).focus();
            }
        }
    });

    $('#give-up-button').click(function () {
        if (title_done && artist_done && next_line_done) {
            if (round === 10) {
                $('#final-score-feed').html(score);
                $('#rank-feed').html([
                    [90, 100, 'indicating Universal Acclaim'],
                    [75, 89, 'indicating Generally Favorable Reviews'],
                    [70, 74, 'indicating Mixed or Average Reviews'],
                    [69, 69, 'Nice.'],
                    [50, 68, 'indicating Mixed or Average Reviews'],
                    [20, 49, 'indicating Generally Unfavorable Reviews'],
                    [0, 19, 'indicating Overwhelming Dislike']
                ].find(tup => (tup[0] <= score) && (score <= tup[1]))[2]);
                fade_between('#game', '#results');
            } else {
                fade_between('#game', '#game', advance_round);
            }
        } else {
            $('#header').focus();
            if (!title_done) {
                title_done = true;
                title_pts = 0;
            }
            if (!artist_done) {
                artist_done = true;
                artist_pts = 0;
            }
            if (!next_line_done) {
                next_line_done = true;
                next_line_pts = 0;
            }
            show_answers();
        }
    });

    $('#play-again-button').click(function () {
        game_loaded = false;

        $('#start').children().prop('disabled', false);
        $('#start-button').html('start game');
        $('#start-feed').html('&nbsp;');
        $('#intro-label').show();

        fade_between('#results', '#start');
    });

    $('#theme-button').click(function () {
        if ($('html').attr('theme') === 'light') {
            switch_theme_to('dark');
        } else {
            switch_theme_to('light');
        }
    });

    $('#fuck-war-link').click(function (event) {
        event.preventDefault();
        war_fucked = true;
        fade_between('#start', '#fuck-war');
    });

    $('#unfuck-war-button').click(function () {
        war_fucked = false;
        if (game_loaded) {
            fade_between('#fuck-war', '#game');
        } else {
            fade_between('#fuck-war', '#start');
        }
    });
});

function show_error(message) {
    $('#start').children().prop('disabled', false);
    $('#start-button').html('start game');
    $('#start-feed').html(message);
    $('#intro-label').hide();
}

function fade_between(from, to, do_between) {
    $(from).css('z-index', -1).fadeOut(750, function () {
        $('#header').focus();
        if (do_between) {
            do_between();
        }
        $(to).stop().fadeIn(750).css('display', 'grid').css('z-index', 1);
    });
}

function advance_round() {
    ++round;
    title_last = artist_last = next_line_last = '';
    title_done = artist_done = next_line_done = false;
    title_pts = artist_pts = 3;
    next_line_pts = 4;

    $('#round').html(`round ${round} of 10`);
    $('#question').html(questions[round - 1]['line']);

    $('#game > input').prop('disabled', false).css('color', 'var(--fg-color)').val('');
    $('.parent-feed').show().css('color', 'var(--sub-color)');
    $('.points-feed').html('3pts');
    $('#next-line-points').html('4pts');
    $('.verdict-feed').hide();

    $('#give-up-button').html('give up');
    $('#submit-button').prop('disabled', false);

    $('#score-feed').html(`${score} out of ${round * 10} points so far`);
}

function update_box_and_feed(box, parent_feed, points, last_result) {
    let points_feed = parent_feed.children('.points-feed');
    let verdict_feed = parent_feed.children('.verdict-feed');
    if (points === 0) {
        box.css('color', 'var(--fail-color-dark)').prop('disabled', true);
        parent_feed.css('color', 'var(--fail-color)');
        points_feed.html('out of tries');
        verdict_feed.hide();
    } else {
        points_feed.html(`${points}pt${points === 1 ? '' : 's'}`)
        verdict_feed.html(`(${last_result})`).fadeIn(150);
        if (last_result === 'correct') {
            box.css('color', 'var(--correct-color-dark)').prop('disabled', true);
            parent_feed.css('color', 'var(--correct-color)');
        } else if (last_result === 'incorrect') {
            parent_feed.css('color', 'var(--fail-color)');
        } else {
            parent_feed.css('color', 'var(--short-color)');
        }
    }
}

function show_answers() {
    $('#lg-title').prop('disabled', true).val(questions[round - 1]['titles'][0]);
    $('#lg-artist').prop('disabled', true).val(questions[round - 1]['artists'][0]);
    $('#lg-next-line').prop('disabled', true).val(questions[round - 1]['next_line']);
    $('#submit-button').prop('disabled', true);

    if (round === 10) {
        $('#give-up-button').html('results');
    } else {
        $('#give-up-button').html('next round');
    }

    $.post('/', {
        'action': 'submit_score',
        'round': round,
        'title_pts': title_pts,
        'artist_pts': artist_pts,
        'next_line_pts': next_line_pts
    });
}

function switch_theme_to(theme) {
    if (theme === 'dark') {
        $('html').attr('theme', 'dark');
        $('#theme-button').html('light theme');
        localStorage.setItem('theme', 'dark');
    } else {
        $('html').attr('theme', 'light');
        $('#theme-button').html('dark theme');
        localStorage.setItem('theme', 'light');
    }
}
