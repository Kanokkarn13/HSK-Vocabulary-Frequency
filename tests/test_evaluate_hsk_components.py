"""Tests for the HSK component-attribution evaluation script."""
import csv

import pytest

from scripts.evaluate_hsk_components import TOKEN_FIELDNAMES, _require, _write_csv, main

WORDLIST_HEADER = "word,level\n"
COUNTS_HEADER = "word,level,exam_id,hsk_level,source_type,count,match_pattern,effective_level,match_type\n"


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_write_csv_emits_header_for_empty_rows(tmp_path):
    # Deriving fieldnames from rows[0] raised IndexError on an empty snapshot.
    path = tmp_path / "nested" / "token_attribution.csv"

    _write_csv(path, [], TOKEN_FIELDNAMES)

    with open(path, encoding="utf-8-sig", newline="") as handle:
        assert next(csv.reader(handle)) == TOKEN_FIELDNAMES


def test_require_reports_the_missing_path_and_a_hint(tmp_path):
    with pytest.raises(SystemExit) as excinfo:
        _require(tmp_path / "absent.csv", "run the ETL pipeline first")

    message = str(excinfo.value)
    assert "absent.csv" in message
    assert "run the ETL pipeline first" in message


def test_main_runs_end_to_end_on_a_tiny_snapshot(tmp_path, monkeypatch, capsys):
    import scripts.evaluate_hsk_components as module

    counts = _write(
        tmp_path / "data/processed/word_counts.csv",
        COUNTS_HEADER
        + "图书馆,3,H1,3,reading,4,,3,direct\n"
        + "图书馆学习,,H1,3,reading,2,,,unmatched\n"
        + "乱码词,,H1,3,reading,1,,,unmatched\n",
    )
    _write(tmp_path / "data/processed/hsk_wordlist.csv", WORDLIST_HEADER + "图书馆,3\n学习,1\n")
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(
        "sys.argv",
        ["evaluate_hsk_components", "--counts", str(counts.relative_to(tmp_path).as_posix())],
    )

    assert main() == 0

    out = capsys.readouterr().out
    assert "Unique raw tokens: 3" in out
    # 图书馆学习 -> 图书馆 + 学习; 乱码词 stays unmatched, 图书馆 was already direct.
    assert "Safely decomposed tokens: 1" in out
    assert "Safely decomposed occurrences: 2" in out

    with open(
        tmp_path / "data/validation/hsk_components/component_frequency.csv",
        encoding="utf-8-sig",
        newline="",
    ) as handle:
        components = {row["word"]: row for row in csv.DictReader(handle)}
    assert components["图书馆"]["occurrences"] == "2"
    assert components["学习"]["levels"] == "1"
