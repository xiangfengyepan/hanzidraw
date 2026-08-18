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
