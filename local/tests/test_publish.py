"""Static publishing: file names must match SQ.fileKey in web/js/static.js exactly."""
from semiquant.publish import _round, file_key


def test_file_key_matches_the_browser_scheme():
    assert file_key("/api/ticker/NVDA/overview") == "ticker/NVDA/overview.json"
    assert file_key("/api/ticker/NVDA/chart?range=10Y&ind=sma20,rsi") == "ticker/NVDA/chart__range-10Y.json"
    assert file_key("/api/ticker/%5EGSPC/chart?range=1D") == "ticker/_5EGSPC/chart__range-1D.json"
    assert file_key("/api/ticker/ES%3DF/overview") == "ticker/ES_3DF/overview.json"
    assert file_key("/api/ticker/BRK-B/risk") == "ticker/BRK-B/risk.json"
    assert file_key("/api/market/heatmap?u=us_large") == "market/heatmap__u-us_large.json"
    assert file_key("/api/ticker/NVDA/news?count=40") == "ticker/NVDA/news__count-40.json"


def test_rounding_keeps_six_significant_digits_and_drops_nan():
    assert _round({"a": [1.23456789, float("nan")], "b": 3605147173690.796, "c": 5}) == {
        "a": [1.23457, None], "b": 3605150000000.0, "c": 5}


def test_not_available_answers_are_retried_every_run(tmp_path):
    from semiquant.publish import Publisher, file_key
    pub = Publisher(tmp_path)
    good, empty, unav = "/api/ticker/NVDA/risk", "/api/ticker/NVDA/options", "/api/ticker/NVDA/analysts"
    for path, body in ((good, '{"symbol":"NVDA","vol":0.5}'), (empty, '{"symbol":"NVDA","available":false,"message":"x"}'),
                       (unav, '{"unavailable": true, "message": "x"}')):
        f = pub.data / file_key(path)
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(body)
        pub.index[file_key(path)] = pub.now
    assert not pub.due(good, "slow")
    assert pub.due(empty, "slow")
    assert pub.due(unav, "daily")
