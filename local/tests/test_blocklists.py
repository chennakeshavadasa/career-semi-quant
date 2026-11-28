"""Content blockers match scripts by file name. EasyPrivacy's generic "/quant.js" rule (Quantcast's
tag) blocked the app's old js/quant.js for uBlock Origin, AdGuard and Brave users, which left the
offer and portfolio models undefined ("SQ.quant is undefined"). Keep every shipped file off the
blocked-name list in data/blocked_script_names.txt."""
from pathlib import Path

WEB = Path(__file__).resolve().parents[1] / "semiquant" / "web"
NAMES = [line.strip() for line in (Path(__file__).parent / "data" / "blocked_script_names.txt").read_text().splitlines()
         if line.strip() and not line.startswith("#")]


def test_list_has_the_rule_that_blocked_the_app():
    assert "quant.js" in NAMES and len(NAMES) > 500


def test_no_shipped_file_matches_a_blocked_script_name():
    # A rule "/name.js" matches any URL that contains it: "name.js", "name.json", "name.js?v=..."
    hits = []
    for f in sorted(WEB.rglob("*")):
        if f.is_file():
            path = "/" + f.relative_to(WEB).as_posix()
            hits += [f"{path} (rule /{n})" for n in NAMES if "/" + n in path]
    assert not hits, "content blockers would block: " + "; ".join(hits)
