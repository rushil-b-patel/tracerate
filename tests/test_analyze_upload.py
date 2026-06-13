import pytest

from tracerate.verdict import analyze


# --- analyze: upload not-tested vs measured-zero distinction -----------------

def test_analyze_upload_none_does_not_emit_low_upload():
    # upload_mbps=None means "not measured" (e.g. --quick mode);
    # it must NOT produce a "Low upload" issue.
    got = analyze({"download_mbps": 50, "upload_mbps": None})
    assert not any("Low upload" in s for s in got["issues"])


def test_analyze_upload_zero_still_emits_low_upload():
    # Regression guard: a measured 0.0 upload IS a real failure and
    # must still be flagged.
    got = analyze({"download_mbps": 50, "upload_mbps": 0.0})
    assert "Low upload: 0.0 Mbps" in got["issues"]


def test_analyze_upload_five_emits_low_upload():
    got = analyze({"download_mbps": 50, "upload_mbps": 5.0})
    assert "Low upload: 5.0 Mbps" in got["issues"]


def test_analyze_upload_fifty_does_not_emit_low_upload():
    got = analyze({"download_mbps": 50, "upload_mbps": 50.0})
    assert not any("Low upload" in s for s in got["issues"])
