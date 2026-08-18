import os

import pytest

from hanzidraw.ime.learn import Learn


def test_unseen_pick_has_no_bonus(tmp_path):
    learn = Learn(tmp_path / "learn.json")
    assert learn.bonus("bei", "北") == 0.0


def test_recording_a_pick_raises_its_bonus(tmp_path):
    learn = Learn(tmp_path / "learn.json")
    learn.record("bei", "背")
    assert learn.bonus("bei", "背") > 0.0
    assert learn.bonus("bei", "北") == 0.0


def test_more_picks_beat_fewer_picks(tmp_path):
    learn = Learn(tmp_path / "learn.json")
    learn.record("bei", "背")
    learn.record("bei", "背")
    learn.record("bei", "北")
    assert learn.bonus("bei", "背") > learn.bonus("bei", "北")


def test_recency_breaks_a_tie_toward_the_latest_pick(tmp_path):
    learn = Learn(tmp_path / "learn.json")
    learn.record("bei", "北")
    learn.record("bei", "背")
    assert learn.bonus("bei", "背") > learn.bonus("bei", "北")


def test_weights_survive_a_save_and_reload(tmp_path):
    path = tmp_path / "learn.json"
    first = Learn(path)
    first.record("bei", "背")
    first.save()
    assert Learn(path).bonus("bei", "背") > 0.0


def test_disabled_learn_never_records_or_bonuses(tmp_path):
    learn = Learn(tmp_path / "learn.json", enabled=False)
    learn.record("bei", "背")
    learn.save()
    assert learn.bonus("bei", "背") == 0.0
    assert not (tmp_path / "learn.json").exists()


def test_corrupt_file_is_ignored(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text("{not json", encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_reset_clears_everything(tmp_path):
    learn = Learn(tmp_path / "learn.json")
    learn.record("bei", "背")
    learn.reset()
    assert learn.bonus("bei", "背") == 0.0


def test_wrong_shaped_json_list_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text("[1, 2, 3]", encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_wrong_shaped_json_string_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text('"just a string"', encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_wrong_shaped_json_number_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text("42", encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_dict_with_non_list_values_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text('{"key": "not a list"}', encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_dict_with_non_numeric_values_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text('{"key": ["not", "numeric"]}', encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_dict_with_null_in_value_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text('{"key": [1, null]}', encoding="utf-8")
    assert Learn(path).bonus("bei", "背") == 0.0


def test_unreadable_file_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.write_text("dummy", encoding="utf-8")
    # Skip test if running as root, where chmod 000 does not deny reads
    if os.geteuid() == 0:
        pytest.skip("Running as root, chmod 000 does not deny reads")
    try:
        path.chmod(0o000)
        assert Learn(path).bonus("bei", "背") == 0.0
    finally:
        path.chmod(0o644)


def test_directory_where_file_should_be_loads_empty(tmp_path):
    path = tmp_path / "learn.json"
    path.mkdir()
    assert Learn(path).bonus("bei", "背") == 0.0


def test_partially_valid_file_keeps_good_drops_bad(tmp_path):
    path = tmp_path / "learn.json"
    import json

    # Create a file with one good entry and several bad ones
    data = {
        '["bei", "背"]': [1.0, 1.0],  # good
        '["feng", "风"]': "not a list",  # bad value type
        '["bad"]': [2.0, 2.0],  # bad value length
        '["pan", "潘"]': [3.0, 3.0],  # good
    }
    path.write_text(json.dumps(data), encoding="utf-8")
    learn = Learn(path)
    # Good entries should load, bad ones should be dropped
    assert learn.bonus("bei", "背") > 0.0
    assert learn.bonus("pan", "潘") > 0.0
    # Bad entries should not load
    assert learn.bonus("feng", "风") == 0.0


def test_tab_collision_is_fixed(tmp_path):
    path = tmp_path / "learn.json"
    first = Learn(path)
    # These two used to collide with tab-based encoding: "a\tb\tc" vs "a\tb\tc"
    first.record("a\tb", "c")
    first.record("a", "b\tc")
    first.save()

    # Reload and verify they are distinct entries with independent counts
    second = Learn(path)
    bonus_1 = second.bonus("a\tb", "c")
    bonus_2 = second.bonus("a", "b\tc")
    assert bonus_1 > 0.0
    assert bonus_2 > 0.0
    # They are distinct entries, so verify they appear in the file as separate keys
    import json

    with open(path) as f:
        data = json.load(f)
    # Should have exactly 2 entries, not 1 (which would indicate collision)
    assert len(data) == 2
    assert '["a\\tb", "c"]' in data
    assert '["a", "b\\tc"]' in data
