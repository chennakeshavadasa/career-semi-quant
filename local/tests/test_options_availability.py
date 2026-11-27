"""Options availability: a Yahoo failure must not read as 'no listed options'."""
import pytest

from semiquant.data import cache, yahoo


class _T:
    def __init__(self, options):
        self._o = options

    @property
    def options(self):
        if isinstance(self._o, Exception):
            raise self._o
        return self._o


@pytest.fixture(autouse=True)
def _no_disk(monkeypatch, tmp_path):
    monkeypatch.setattr(yahoo, "_call", lambda fn, *a, **k: fn())
    cache._mem.clear() if hasattr(cache, "_mem") else None
    monkeypatch.setattr(cache, "cached", lambda key, ttl, loader, disk=False, accept=None: loader())


def _setup(monkeypatch, options, qtype="EQUITY", exchange="NasdaqGS"):
    monkeypatch.setattr(yahoo, "_ticker", lambda s: _T(options))
    monkeypatch.setattr(yahoo, "quote", lambda s: {"type": qtype, "exchange": exchange})


def test_us_stock_with_expiries(monkeypatch):
    _setup(monkeypatch, ("2099-01-15", "2000-01-01"))
    assert yahoo.option_expiries("NVDA") == ["2099-01-15"]


def test_empty_answer_for_us_stock_is_a_temporary_failure(monkeypatch):
    _setup(monkeypatch, ())
    with pytest.raises(yahoo.DataError, match="temporarily unavailable"):
        yahoo.option_expiries("NVDA")


def test_request_error_is_a_temporary_failure(monkeypatch):
    _setup(monkeypatch, RuntimeError("429 Too Many Requests"))
    with pytest.raises(yahoo.DataError, match="temporarily unavailable"):
        yahoo.option_expiries("NVDA")


def test_foreign_listing_without_options_is_empty(monkeypatch):
    _setup(monkeypatch, (), exchange="Tokyo")
    assert yahoo.option_expiries("8035.T") == []


def test_otc_adr_without_options_is_empty(monkeypatch):
    _setup(monkeypatch, (), exchange="OTC Markets")
    assert yahoo.option_expiries("RNECY") == []
