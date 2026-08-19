# hanzidraw

A desktop app that works like the Windows Chinese IME, except it never inserts
text: you type pinyin, pick a candidate from a Windows-style bar, and the
character is **drawn** stroke by stroke in canonical order on a canvas (or
into another application's window, via synthetic mouse input, or straight to
an image file).

It exists because a companion project — the Keychron Q1 HE custom firmware in
`KeychronQMK` (`users/xiangfeng`) — bakes its own pinyin IME and stroke
dictionary into flash. That firmware is capped at 276 characters in about
56 KB of the ~87 KB available. hanzidraw has no such ceiling (7,743 drawable
characters, ~9,500 with stroke data upstream), and it also generates the
firmware's own dictionary file, so the keyboard's 276-character set can be
refreshed from the same pipeline instead of edited by hand.

## What this is not

- **Not a system input method.** It does not register with Windows TSF or
  Linux IBus/Fcitx, and it never inserts text into another application.
  Composition only happens while the hanzidraw window itself has focus — there
  is no global keyboard hook and no elevated permissions.
- **Not handwriting recognition.** Input is pinyin only; the app draws
  characters, it does not read them.
- The `mouse` output backend *does* act on another application, but only by
  moving and clicking the pointer to trace strokes — it is a drawing robot,
  not a text-insertion path.

## Install

### The scripted way

Two installers do the whole job — install `uv` (which supplies the right Python),
install the app with both extras, put the character database in place, and verify
the result. Both are idempotent, so re-running them is safe.

```bash
./install.sh                     # Linux / macOS
./install.sh --db hanzidraw.sqlite.gz   # import a prebuilt database instead of downloading
./install.sh --help              # --no-data, --no-extras, --yes
```

```powershell
.\install.ps1                    # Windows
.\install.ps1 -Db .\hanzidraw.sqlite.gz -Yes
Get-Help .\install.ps1 -Full     # -NoData, -NoExtras, -Yes, -Python
```

On Linux the script also checks for `libxcb-cursor0`, a system library Qt needs at
runtime: without it the window does not open, and Qt reports that as a wall of
plugin text rather than a usable message.

### By hand

Requires Python 3.11+, and **3.12 for the GUI** — PySide6 has no wheels for 3.13+
yet, so a newer interpreter installs cleanly and then cannot open a window.

```bash
uv tool install --python 3.12 .          # or: pipx install .
```

That installs the `hanzidraw` command with no GUI support. Two optional
extras add capability:

```bash
uv tool install ".[gui]"          # the drawing window (PySide6) and PNG output
uv tool install ".[mouse]"        # the mouse output backend (pynput)
uv tool install ".[gui,mouse]"    # both
```

Without `gui`, `hanzidraw run` prints a clear message and exits rather than
crashing. Without `mouse`, selecting `output.backend = "mouse"` is not fatal:
the window says so in its status bar and draws to its own canvas instead.
`hanzidraw draw` and `hanzidraw export-firmware` need neither extra — they
only need the character database (see below), and `draw -o out.svg` works
with the base install. `draw -o out.png` needs `gui`, because PNG rasterising
goes through Qt.

A `hanzidraw.spec` PyInstaller spec is included for building a Windows
executable with no separate Python install:

```bash
pyinstaller hanzidraw.spec
```

The character database is deliberately **not** bundled into that executable —
it is built on first run, same as any other install (see below).

## Building the character database: `hanzidraw fetch-data`

hanzidraw does not vendor its data. `hanzidraw fetch-data` downloads a handful
of open datasets (~40 MB total) into the user data directory and builds a
SQLite database there:

```bash
hanzidraw fetch-data
```

Sources fetched, all licensed for this use (details and attribution in
`NOTICE`):

| Source | Provides | Size |
|---|---|---|
| Make Me a Hanzi `graphics.txt` | stroke medians (the drawing) and typographic outlines | 30 MB |
| hanziDB `hanziDB.csv` | frequency rank, pinyin readings, stroke count | 544 KB |
| CC-CEDICT `cedict.txt.gz` | word/phrase pinyin keys, plus extra character readings | 3.8 MB |
| rime-essay `essay.txt` (optional) | word frequencies used to rank phrase candidates | 5.7 MB |

A measured build produces:

- **7,743** drawable characters, **8,310** readings, **108,202** phrases
- schema version **3**
- database size **20,525,056 bytes** (~20.5 MB). SQLite page packing varies
  slightly between rebuilds — a few kilobytes either way is normal and not a content
  difference; the row counts above are the figures that matter.

Everything the build drops is counted and printed rather than silently
discarded: 2,154 characters were skipped for having no stroke data, 686
phrases were dropped because a constituent character was undrawable, 100
duplicate `hanziDB` rows and 928 duplicate phrase rows were skipped. A
character is only ever offered as a candidate if hanzidraw can draw it; a
phrase is only kept if every character in it is drawable, so you never get a
half-drawn word.

567 of the 8,310 readings were not in `hanziDB` at all — they were harvested
from CC-CEDICT's single-character entries. This is what makes **heteronyms**
work: a character with more than one reading is typable under any of them.
For example:

| Character | Readings |
|---|---|
| 行 | *hang*, *xing*, *heng* |
| 长 | *chang*, *zhang* |
| 都 | *dou*, *du* |
| 叶 | *ye*, *xie* |

Other `fetch-data` flags:

- `--rebuild` — rebuild even if a database already exists (the default is to
  do nothing and say so, so re-running the command is always safe).
- `--refetch` — re-download the raw sources even if already cached on disk.
- `--medians-only` — skip storing typographic outlines, for a smaller
  database. `glyph.style = "outline"` then falls back to brush strokes with a
  message rather than failing (see Rendering below).
- `--raw-dir PATH`, `--db PATH` — override where the downloads and the built
  database go; mainly useful for testing.

The app refuses to start with a plain-language error, not a traceback, if the
database is missing (`run 'hanzidraw fetch-data' first`) or was built by an
incompatible version (`run 'hanzidraw fetch-data --rebuild'`).

### Provenance, and what a rebuild is safe against

Each source's SHA-256 is recorded in the database's `meta` table on the first
build, together with a `build_date`. On a rebuild the digests are compared and
every source that has changed upstream is named, with both short digests — a
note, not a failure, because these files are served from moving `master`
branches and genuinely do change. A cached download that no longer decompresses
is re-downloaded rather than fed to the build.

A rebuild is also safe against failing: the new database is built to a
temporary file next to the old one and swapped into place only once it is
complete, so a corrupt download costs you a message rather than the 20-minute
database you already had.

## Using the IME

Run `hanzidraw` (or `hanzidraw run`) to open the drawing window. Composition
only responds to keys while that window has focus.

### Candidate ranking

Candidates are ranked by **how much of what you typed they consume** — the
same principle every real IME uses:

1. **Full match** — the reading is exactly what you typed. Typing `feng`
   puts 风 here; typing `beijing` puts 北京 and 背景 here.
2. **Prediction** — the reading is longer than what you typed. Typing
   `beijing` puts 北京市 here.
3. **Partial** — the candidate consumes fewer syllables than you typed.
   Typing `beijing` puts the single character 北 here.

So typing `feng` gives 风 封 丰 … in that order, and typing `beijing` gives
北京 背景 first, then 北京市 as a prediction — not the other way around.

Within a tier, phrases come before single characters, then heavier corpus
weight, then text, for determinism.

### Learning

Picking a candidate that was not already first promotes it — permanently,
stored in a small per-user JSON file (`ime.learn`, on by default). After
committing 沣 once for `feng`, it moves from position 17 to position 1 and
stays there. This is what turns rare name characters into a single keystroke
after the first use.

### Key bindings (Windows-IME-like)

| Key | Action |
|---|---|
| `a`-`z` | append to preedit, refresh candidates |
| `'` | force a syllable boundary (e.g. `xi'an` vs `xian`) |
| `1`-`9` | commit the nth candidate on the current page |
| Space / Enter | commit the highlighted candidate |
| Left / Right / Tab | move the highlight |
| `-` `=` / PageUp PageDown | previous / next candidate page |
| Backspace | delete the last preedit letter |
| Esc | cancel the composition |
| F2 | toggle `sheet` / `single` canvas mode |
| Ctrl+Z / Ctrl+L | undo the last glyph / clear the sheet |
| Ctrl+S | export the sheet |
| Ctrl+. (or Esc) | abort an in-progress mouse draw (the `MS_STOP` equivalent) |
| Ctrl+R | replay the current glyph (`single` mode) |
| Ctrl+] / Ctrl+[ | step one stroke forward / back (`single` mode) |

The abort keys (Ctrl+. and Esc) are the one binding that also works while
another application has focus, and only for the duration of a `mouse` draw —
see Output backends below.

**Platform note:** Ctrl+. is confirmed working as an abort key on Linux. On
Windows it is expected to be unreliable — the Win32 backend typically reports
that key combination with `char=None` and only a virtual-key code, which the
current match does not handle — and this has not yet been verified on real
Windows hardware. Until it is, **Esc is the reliable abort key on Windows.**

## Configuration

TOML file, hot-reloaded on save:

- Linux: `~/.config/hanzidraw/config.toml` (or `$XDG_CONFIG_HOME/hanzidraw/config.toml`)
- Windows: `%APPDATA%\hanzidraw\config.toml`

`--config PATH` overrides the location for any command. A bad value is
replaced by its default and reported in the status bar rather than crashing
the app; unknown keys are a warning, not an error.

Hot reload distinguishes two kinds of change:

- A **paint-time** change (colour, stroke width, background, grid, style,
  animation speed) applies immediately and **keeps what you have already
  drawn** on the sheet.
- A **layout** change (`glyph.size_px`, `canvas.columns`, `canvas.advance`,
  `canvas.wrap`) changes the geometry the sheet is built from, so the sheet is
  cleared and the status bar says why: `canvas cleared: layout settings
  changed`.

The sheet itself is `canvas.columns * canvas.advance * glyph.size_px` pixels
wide (1656 px at the stock defaults: 6 * 1.15 * 240), and the window **scrolls**
rather than reflowing or clipping whenever it is narrower than that -- so a
horizontal scrollbar on a stock-sized window is expected, not a bug.

Full annotated example, including the animation-speed knob:

```toml
[glyph]
style = "brush"               # brush (constant-width strokes, what the
                               # firmware draws) | outline (the real
                               # typographic contour, swelling and tapering)
size_px = 240
stroke_width_px = 14
color = "#111111"              # one colour: "#rgb", "#rrggbb", or one of
                               # these 20 names: aqua, black, blue, cyan,
                               # fuchsia, gray, green, grey, lime, magenta,
                               # maroon, navy, olive, orange, purple, red,
                               # silver, teal, white, yellow. Anything else
                               # (e.g. "hotpink") is a config error -- use
                               # a hex value instead.
outline_color = "#cccccc"      # colour of the not-yet-drawn ghost outline
show_pending_outline = true    # ghost of the full character while it draws
stroke_numbers = false         # number each stroke at its start, in
                               # canvas mode "single" only

[glyph.animation]
enabled = true
stroke_ms = 380                 # default: writing 沣潘叶祥 (7+15+5+10=37
gap_ms = 90                     # strokes, 33 within-character gaps between
                                 # them) takes 37*380 + 33*90 = 17.0s.
                                 #
                                 # For a snappier feel, drop both:
                                 #   stroke_ms = 180
                                 #   gap_ms = 40
                                 # brings the same four characters to about 8s
                                 # (37*180 + 33*40 = 8.0s).
easing = "ease_out"             # linear | ease_in | ease_out | ease_in_out

[canvas]
mode = "sheet"                  # sheet (wraps, keeps history) | single
                                 # (one glyph, replayable) -- F2 toggles
background = "#fdfdf7"
grid = "tian"                   # none | tian | mi | cross
grid_color = "#e5ded0"
columns = 6                     # a LAYOUT setting: changing it clears the sheet
advance = 1.15                  # multiple of size_px; also a layout setting
wrap = true                     # also a layout setting
always_on_top = false

[ime]
page_size = 9
phrases = true
learn = true                    # promote picks you actually make (see above)
max_candidates = 200

[output]
backend = "canvas"              # canvas | mouse | image

[output.mouse]
scale = 1.0
step_delay_ms = 4
button = "left"
clamp_to_screen = true

[output.image]
dir = "~/Pictures/hanzidraw"    # where Ctrl+S writes sheet.png

[theme]
preset = "ink"                  # ink | neon | chalk | none
                                 # a preset only *supplies defaults*: any key
                                 # you set explicitly above still wins.
```

## Output backends

Three ways for a committed glyph to actually appear, chosen with
`output.backend`:

- **`canvas`** (default) — draws into hanzidraw's own window with Qt. Always
  available, supports both `sheet` and `single` canvas modes, undo, replay,
  and the practice grid.
- **`image`** — headless: renders a whole batch of characters to one SVG or PNG
  file. This is what `hanzidraw draw` uses (below), and what the test suite uses
  to assert on rendered geometry. It is a command-line backend, not a per
  keystroke one: selecting it while the window is open reports that in the
  status bar and draws to the canvas, because a window has nowhere sensible to
  put a file per committed character. Use `Ctrl+S` to export what is on the
  sheet.
- **`mouse`** — draws into whatever application currently has focus by moving
  the real pointer, pressing the button for the duration of each stroke, and
  releasing between strokes, mirroring the firmware's own draw engine. Needs
  the `mouse` extra (`pynput`). Refuses to draw into a cell that hanzidraw's
  own window overlaps, because the one thing a synthetic drag must not do is
  land on our own UI.

  **Known limitation, left for a future session:** the mouse backend draws
  each glyph at an **absolute** canvas position, not relative to wherever the
  pointer currently sits — unlike the firmware, which starts drawing at the
  cursor and advances a carriage from there. It was built this way because
  real pointer behaviour against a live paint application could not be
  verified in this project's headless build environment. This is the first
  thing to revisit before relying on the `mouse` backend day to day.

  Because a synthetic pointer that will not stop is hostile, every mouse draw
  has **three independent** ways to abort: the Ctrl+. key — or Esc, accepted as
  a second panic key — via a temporary, narrowly-scoped listener that exists
  only while a draw is in progress;
  a hard per-glyph deadline, and detecting that the real pointer moved away
  from where hanzidraw last put it (you grabbed the mouse). Whichever one
  fires, the mouse button is released on every exit path — no draw can leave
  the button stuck down.

## Rendering styles

Two styles, drawn from the same stroke data, both animated with the same
per-stroke timing:

- **`brush`** — medians drawn as round-capped, constant-width polylines. This
  is the shape the Keychron firmware traces, and the only style the `mouse`
  backend can physically produce (a pointer can only trace a path, not fill a
  shape).
- **`outline`** — the real typographic contour: the character's actual
  swelling-and-tapering brush shape, revealed as filled paths rather than
  polylines. Needs a database built without `--medians-only`; falls back to
  `brush` with a message if outline data is missing.

## `hanzidraw draw` — render to a file, no window needed

```bash
hanzidraw draw 沣潘叶祥 -o out.svg
hanzidraw draw 沣潘叶祥 -o out.png     # needs the gui extra
```

The output suffix chooses the format, so it has to be `.svg` or `.png`;
anything else is a validation error rather than an SVG under a misleading name.

Reads the same `config.toml` as the GUI (`--config PATH` to override, `--db
PATH` for a non-default database), and the same `--size`, `--color`,
`--columns` overrides. Cells are laid out by the same sheet the window uses, so
`canvas.columns`, `canvas.advance` and `canvas.wrap` mean the same thing here. Reports which characters have no stroke data instead
of drawing a blank box, and reports file-write failures (permission denied,
parent path is not a directory, etc.) as a message rather than a traceback.

## `hanzidraw export-firmware` — regenerate the keyboard's dictionary

```bash
hanzidraw export-firmware --budget-kb 80 --must 沣潘叶祥 --per-initial 12 \
    -o hanzi_data.c
```

Selects must-have characters first — so 沣, 潘, 叶, 祥 stay candidate 1 for
their syllables on the keyboard — then fills the remaining budget by
`hanziDB` frequency rank, optionally capped per pinyin initial (`--per-initial
12` above), stopping at the byte budget (`--budget-kb`). Emission matches the
firmware's existing format exactly (`x[]`, `y[]`, `len[]`, `hanzi_table[]`,
`hanzi_count`), with per-character byte cost measured from the emitted arrays
rather than assumed.

A real run against this database:

```
276 characters, 55.6 KB
budget 80.0 KB, headroom 24.4 KB
```

**Drift caveat, documented rather than hidden:** the exported stroke arrays
are *structurally* identical to the dictionary currently in the firmware —
same stroke counts, same number of points per stroke, for all four name
characters. But 321 of 366 individual coordinate values differ by 1–2 units,
and that mismatch is identical under both integer-rounding modes the exporter
supports. That rules out a rounding bug; it means upstream Make Me a Hanzi has
refined its stroke medians since the firmware's dictionary was generated.
The test suite's golden comparison (`tests/firmware/test_emit_c.py`) is marked
`xfail` for exactly this reason — it is expected to fail, and doing so is the
proof that the transform itself is correct while the upstream data has moved
under it. **A freshly exported `hanzi_data.c` is therefore equivalent to, but
not byte-identical to, what currently ships on the keyboard.**

Other flags: `--header PATH` also writes a `.h` file; `--limit N` caps the
total character count independently of the byte budget; `--db PATH` selects a
non-default database.

## Sources and licence

hanzidraw bundles no third-party data — everything it draws comes from open
datasets downloaded by `hanzidraw fetch-data` at first run. Full attribution,
licences, and source URLs for Make Me a Hanzi, hanziDB, CC-CEDICT, and
rime-essay are in [`NOTICE`](NOTICE).
