"""Open Parking AI pass-billing connector.

ONE QUESTION: for each stated link (a garage pass <-> an outside-registrar
agreement), on the day given, make monthly billing's register for that
agreement equal the pass's live register -- and say loudly whatever cannot be
made equal.

The connector has no database and imports neither module. It runs the two
console scripts, ``garage-pass`` and ``monthly-billing``, as subprocesses and
reads what they print. See ``doors.py`` for that boundary, ``live.py`` for what
"live on day D" means, ``sync.py`` for the order of the writes and why, and
``docs/CONTRACT.md`` for what is guaranteed.
"""
