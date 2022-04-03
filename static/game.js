let zind = 1;
let war_fucked = false;
let game_loaded = false;

// mobile keyboard fix (god bless user13442212 from stackoverflow)
let viewport = document.querySelector("meta[name=viewport]");
viewport.setAttribute("content", viewport.content + ", height=" + window.innerHeight);

// yes this HAS to be done both here and in load()
switch_theme_to(localStorage.getItem('theme') ? localStorage.getItem('theme') : 'light');

function update_game(res, refresh = false) {
    if (res['status'] === 'session_expired') {
        expire_session();
    }

    let tfeed = $("#title-feed")[0];
    let afeed = $("#artist-feed")[0];
    let lfeed = $("#next-line-feed")[0];
    let tbox = $("#lg-title")[0];
    let abox = $("#lg-artist")[0];
    let lbox = $("#lg-next-line")[0];
    let question = $("#question")[0];
    let round = $("#round")[0];
    let pfeed = $("#points-feed")[0];
    let button = $("#give-up-button")[0];

    round.innerHTML = "round " + res['round'] + " of 10";
    question.innerHTML = res['question'];

    if ('title_feedback' in res || refresh) {
        if (res['title_feedback'] === "locked") {
            tfeed.style.color = gprop("--fail-color");
            tfeed.innerHTML = "out of tries";
            tbox.disabled = "true";
            tbox.blur();
            tbox.style.color = gprop("--fail-color-dark");
        } else {
            if (res['title_pts'] === 1) {
                tfeed.innerHTML = "1pt";
            } else {
                tfeed.innerHTML = res['title_pts'] + "pts";
            }

            tfeed.style.color = gprop("--sub-color");

            if (res['title_feedback'] === "success") {
                tfeed.style.color = gprop("--correct-color");
                tfeed.innerHTML += " (correct)";
                tbox.disabled = "true";
                tbox.blur();
                tbox.style.color = gprop("--correct-color-dark");
            } else if (res['title_feedback'] === "fail") {
                tfeed.style.color = gprop("--fail-color");
                tfeed.innerHTML += " (incorrect)";
            }
        }
    }

    if ('artist_feedback' in res || refresh) {
        if (res['artist_feedback'] === "locked") {
            afeed.style.color = gprop("--fail-color");
            afeed.innerHTML = "out of tries";
            abox.disabled = "true";
            abox.blur();
            abox.style.color = gprop("--fail-color-dark");
        } else {
            if (res['artist_pts'] === 1) {
                afeed.innerHTML = "1pt";
            } else {
                afeed.innerHTML = res['artist_pts'] + "pts";
            }

            afeed.style.color = gprop("--sub-color");

            if (res['artist_feedback'] === "success") {
                afeed.style.color = gprop("--correct-color");
                afeed.innerHTML += " (correct)";
                abox.disabled = "true";
                abox.blur();
                abox.style.color = gprop("--correct-color-dark");
            } else if (res['artist_feedback'] === "fail") {
                afeed.style.color = gprop("--fail-color");
                afeed.innerHTML += " (incorrect)";
            }
        }
    }

    if ('next_line_feedback' in res || refresh) {
        if (res['next_line_feedback'] === "locked") {
            lfeed.style.color = gprop("--fail-color");
            lfeed.innerHTML = "out of tries";
            lbox.disabled = "true";
            lbox.blur();
            lbox.style.color = gprop("--fail-color-dark");
        } else {
            if (res['next_line_pts'] === 1) {
                lfeed.innerHTML = "1pt";
            } else {
                lfeed.innerHTML = res['next_line_pts'] + "pts";
            }

            lfeed.style.color = gprop("--sub-color");

            if (res['next_line_feedback'] === "success") {
                lfeed.style.color = gprop("--correct-color");
                lfeed.innerHTML += " (correct)";
                lbox.disabled = "true";
                lbox.blur();
                lbox.style.color = gprop("--correct-color-dark");
            } else if (res['next_line_feedback'] === "fail") {
                lfeed.style.color = gprop("--fail-color");
                lfeed.innerHTML += " (incorrect)";
            } else if (res['next_line_feedback'] === "too short") {
                lfeed.style.color = gprop("--short-color");
                lfeed.innerHTML += " (too short)";
            }
        }
    }

    pfeed.innerHTML = res['score'] + " out of " + res['max_score'] + " points so far";

    button.blur();
}

function start() {
    let username = $("#lg-username")[0];
    let count = $("#count")[0];
    let period = $("#period")[0];
    let button = $("#start-button")[0];

    if (!$.trim(username.value)) {
        set_start_feed("please enter a last.fm username");
        button.blur();
        return;
    }

    $("#start").children().prop("disabled", true);
    username.blur();
    button.blur();
    button.value = "working...";
    $("#start-feed").html("&nbsp;");

    $.post("/", {
        "action": "start",
        "username": username.value,
        "count": count.value,
        "period": period.value
    }).done(function (res) {
        if (res['status'] === 'invalid_username') {
            set_start_feed("invalid last.fm username");
        } else if (res['status'] === 'not_enough_tracks') {
            set_start_feed("user has too few tracks in this time period");
        } else if (res['status'] === 'unable_to_load_question') {
            set_start_feed("couldn't find enough lyrics to play, try a different user or song range");
        } else if (res['status'] === 'lastfm_error') {
            set_start_feed("unknown last.fm error, please try again");
        } else if (res['status'] === 'unknown_error') {
            set_start_feed("unknown error, please try again");
        } else {
            $("#start").fadeOut(1000, function () {
                $.post("/", {"action": "get_status"}).done(function (res) {
                    reset_inputs();
                    update_game(res, true);
                    game_loaded = true;
                    if (!war_fucked) {
                        $("#game").css("z-index", zind++).fadeIn(1000).css("display", "grid");
                    }
                });
            });
        }
    });
}

function guess(e) {
    if (!e) {
        e = window.event;
    }

    if (e.keyCode === 13) {
        $.post("/", {
            "action": "get_status",
            "title": $("#lg-title").val(),
            "artist": $("#lg-artist").val(),
            "next_line": $("#lg-next-line").val()
        }).done(function (res) {
            update_game(res);

            if (res['round_ended']) {
                get_answers();
            } else {
                let seq = ["lg-title", "lg-artist", "lg-next-line", "lg-title"];
                let cur = $("#" + e.target.id);
                while (cur.prop("disabled")) {
                    for (let i = 0; i < 3; ++i) {
                        if (seq[i] === cur[0].id) {
                            cur = $("#" + seq[i + 1]);
                            break;
                        }
                    }
                }

                cur.focus();
            }
        });
    }
}

function get_answers() {
    $.post("/", {"action": "get_answers"}).done(
        function (res) {
            if (res['status'] === 'session_expired') {
                expire_session();
            }

            let tbox = $("#lg-title")[0];
            let abox = $("#lg-artist")[0];
            let lbox = $("#lg-next-line")[0];
            let button = $("#give-up-button")[0];
            let sbutton = $("#submit-button")[0];

            tbox.value = res['title'];
            abox.value = res['artist'];
            lbox.value = res['next_line'];
            tbox.disabled = true;
            abox.disabled = true;
            lbox.disabled = true;
            sbutton.disabled = true;
            button.blur();

            if (res['game_ended']) {
                button.value = "results";
            } else {
                button.value = "next round";
            }
        }
    );
}

function next_round() {
    let button = $("#give-up-button")[0];
    button.disabled = true;
    button.value = "working...";

    $("#game").fadeOut(1000, function () {
        $.post("/", {"action": "get_status"}).done(
            function (res) {
                reset_inputs();
                update_game(res, true);
                $("#game").fadeIn(1000).css("display", "grid");
            }
        );
    });
}

function show_results() {
    $("#game").fadeOut(1000, function () {
        $.post("/", {"action": "get_score"}).done(
            function (res) {
                if (res['status'] === 'session_expired') {
                    expire_session();
                }

                $("#final-score-feed").html(res['score']);
                $("#rank-feed").html(res['rank']);
                $("#give-up-button").blur();

                $("#results").css("z-index", zind++).fadeIn(1000).css("display", "grid");
            });
    });
}

function play_again() {
    game_loaded = false;

    $("#start").children().prop("disabled", false);
    $("#start-button").val("start game");
    $("#start-feed").html("&nbsp;");
    $("#intro-label").show();
    $("#header")[0].focus();

    $("#results").fadeOut(1000, function () {
        $("#start").css("z-index", zind++).fadeIn(1000).css("display", "grid");
    });
}

function give_up_button_click() {
    $("#header")[0].focus();
    let button = $("#give-up-button")[0];
    // god tier coding: decide what the button does based on what it says
    if (button.value === "give up") {
        get_answers();
    } else if (button.value === "next round") {
        next_round();
    } else {
        show_results();
    }
}

function load() {
    switch_theme_to(localStorage.getItem('theme') ? localStorage.getItem('theme') : 'light');
}

function reset_inputs() {
    let tbox = $("#lg-title")[0];
    let abox = $("#lg-artist")[0];
    let lbox = $("#lg-next-line")[0];
    let button = $("#give-up-button")[0];
    let sbutton = $("#submit-button")[0];
    tbox.disabled = false;
    abox.disabled = false;
    lbox.disabled = false;
    tbox.value = "";
    abox.value = "";
    lbox.value = "";
    tbox.style.color = gprop("--fg-color");
    abox.style.color = gprop("--fg-color");
    lbox.style.color = gprop("--fg-color");

    button.disabled = false;
    button.value = "give up";
    sbutton.disabled = false;
}

function submit_button_click() {
    $.post("/", {
        "action": "get_status",
        "title": $("#lg-title").val(),
        "artist": $("#lg-artist").val(),
        "next_line": $("#lg-next-line").val()
    }).done(function (res) {
        $("#submit-button").blur();
        update_game(res);

        if (res['round_ended']) {
            get_answers();
        }
    });
}

function set_start_feed(message) {
    $("#start-feed").html(message);
    $("#intro-label").hide();
    $("#start").children().prop("disabled", false);
    $("#start-button").val("start game");
}

function switch_theme_to(theme) {
    if (theme === 'light') {
        $("#theme-button").val("dark theme");
        document.documentElement.setAttribute('theme', theme);
        localStorage.setItem('theme', theme);
    } else {
        $("#theme-button").val("light theme");
        document.documentElement.setAttribute('theme', theme);
        localStorage.setItem('theme', theme);
    }
}

function switch_theme() {
    let cur = localStorage.getItem('theme') ? localStorage.getItem('theme') : 'light';

    if (cur === "light") {
        switch_theme_to("dark");
    } else {
        switch_theme_to("light");
    }

    $("#theme-button").blur();
}

function expire_session() {
    window.alert("sorry, your session has expired. please start a new game");
    location.reload();
}

function gprop(prop) {
    return "var(" + prop + ")";
}

function fuck_war() {
    war_fucked = true;
    $("#header")[0].focus();
    $("#start").fadeOut(1000, function () {
        $("#fuck-war").css("z-index", zind++).fadeIn(1000).css("display", "grid");
    });
}

function unfuck_war() {
    war_fucked = false;
    $("#header")[0].focus();
    $("#fuck-war").fadeOut(1000, function () {
        if (game_loaded) {
            $("#game").css("z-index", zind++).fadeIn(1000).css("display", "grid");
        } else {
            $("#start").css("z-index", zind++).fadeIn(1000).css("display", "grid");
        }
    });
}