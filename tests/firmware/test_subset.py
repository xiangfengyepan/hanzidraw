from hanzidraw.data.store import Store
from hanzidraw.firmware.subset import ROW_BYTES, Entry, firmware_xy, select

MEDIANS = (((-512, 0), (512, 0)), ((0, -512), (0, 512)))


def _store(tmp_path):
    store = Store.create(tmp_path / "db.sqlite")
    rows = [
        ("的", 1, ("de",)),
        ("是", 4, ("shi",)),
        ("沣", 9000, ("feng",)),
        ("潘", 3000, ("pan",)),
        ("大", 40, ("da",)),
        ("打", 300, ("da",)),
    ]
    for ch, rank, readings in rows:
        store.add_char(ord(ch), freq_rank=rank, nstroke=2, medians=MEDIANS, outline=None)
        for reading in readings:
            store.add_reading(reading, ord(ch))
    store.finish()
    return store


def test_firmware_xy_applies_the_scale_and_reports_stroke_lengths():
    xs, ys, lens = firmware_xy(MEDIANS)
    assert xs == [-64, 64, 0, 0]
    assert ys == [0, 0, -64, 64]
    assert lens == [2, 2]


def test_cost_bytes_counts_points_strokes_row_and_pinyin():
    entry = Entry(ord("十"), "shi", [1, 2], [3, 4], [2])
    assert entry.cost_bytes == 4 * 2 + 1 + ROW_BYTES + len("shi") + 1


def test_must_have_characters_come_first_in_order(tmp_path):
    entries = select(_store(tmp_path), must="沣潘")
    assert [chr(e.codepoint) for e in entries][:2] == ["沣", "潘"]


def test_the_rest_are_ordered_by_frequency(tmp_path):
    entries = select(_store(tmp_path), must="")
    assert [chr(e.codepoint) for e in entries][:3] == ["的", "是", "大"]


def test_budget_stops_the_selection_but_never_drops_a_must_have(tmp_path):
    entries = select(_store(tmp_path), must="沣潘", budget_bytes=3 * 40)
    assert [chr(e.codepoint) for e in entries][:2] == ["沣", "潘"]
    assert sum(e.cost_bytes for e in entries) <= 3 * 40 or len(entries) == 2


def test_per_initial_cap_limits_each_pinyin_initial(tmp_path):
    entries = select(_store(tmp_path), must="", per_initial=1)
    initials = [e.pinyin[0] for e in entries]
    assert len(initials) == len(set(initials))


def test_selection_is_deduplicated(tmp_path):
    entries = select(_store(tmp_path), must="沣沣")
    assert len([e for e in entries if chr(e.codepoint) == "沣"]) == 1


def test_select_emits_the_primary_reading_not_an_earlier_alternate(tmp_path):
    """The exporter must not silently promote a CC-CEDICT alternate over the primary.

    "lao" sorts before "le" alphabetically, but "le" is 乐's primary reading;
    the exported Entry must carry "le". Reached through the non-must path
    (all_chars_by_rank), which is the one Task 19's original first_reading-only
    fix would have missed.
    """
    store = Store.create(tmp_path / "db.sqlite")
    store.add_char(ord("乐"), freq_rank=50, nstroke=2, medians=MEDIANS, outline=None)
    store.add_reading("le", ord("乐"), is_primary=True)
    store.add_reading("lao", ord("乐"), is_primary=False)
    store.finish()
    entries = select(store, must="")
    assert entries[0].pinyin == "le"
