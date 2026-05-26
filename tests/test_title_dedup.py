import pytest
from briefing.scheduler.jobs import _is_title_duplicate

def test_is_title_duplicate_exact_match():
    assert _is_title_duplicate("Apple announces new iPhone", ["Apple announces new iPhone", "Other news"], 0.85)

def test_is_title_duplicate_similar():
    assert _is_title_duplicate("Apple announces a new iPhone!", ["Apple announces new iPhone"], 0.85)

def test_is_title_duplicate_different():
    assert not _is_title_duplicate("Google announces new Pixel", ["Apple announces new iPhone"], 0.85)

def test_is_title_duplicate_empty_existing():
    assert not _is_title_duplicate("New news", [], 0.85)
