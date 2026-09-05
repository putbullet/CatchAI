"""Tests for Catch's read-only filename search."""

from pathlib import Path

from tools.files import search_files


def _paths(results: list[dict[str, str]]) -> set[str]:
    return {result["path"] for result in results}


def test_search_is_case_insensitive_and_matches_multiple_words(tmp_path: Path) -> None:
    expected = tmp_path / "Cybersecurity Report.PDF"
    expected.write_text("data", encoding="utf-8")
    (tmp_path / "unrelated.txt").write_text("data", encoding="utf-8")

    results = search_files("CYBER security report", [tmp_path])

    assert _paths(results) == {str(expected.resolve())}
    assert results[0]["extension"] == ".PDF"


def test_search_matches_extension_and_unicode_names(tmp_path: Path) -> None:
    expected = tmp_path / "Résumé Sécurité.docx"
    expected.write_text("data", encoding="utf-8")

    results = search_files("resume securite docx", [tmp_path])

    assert _paths(results) == {str(expected.resolve())}


def test_empty_or_missing_queries_return_no_results(tmp_path: Path) -> None:
    (tmp_path / "report.pdf").touch()

    assert search_files("", [tmp_path]) == []
    assert search_files("nonexistent_file_xyz", [tmp_path]) == []


def test_directories_are_not_returned_and_duplicate_roots_are_deduplicated(tmp_path: Path) -> None:
    nested = tmp_path / "nested"
    nested.mkdir()
    expected = nested / "report.pdf"
    expected.touch()

    results = search_files("report", [tmp_path, nested])

    assert _paths(results) == {str(expected.resolve())}
    assert all(Path(result["path"]).is_file() for result in results)
