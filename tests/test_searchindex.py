"""File-index search (§11.2, row 44): semantic-name matching over a whole tree.

The acceptance case is the owner's own: "play me kaba" must find the song
whether it is named ``kaba.mp3``, ``Kaba by Kapeke.m4a``, or lied inside a
folder of a hundred unrelated files — and a song the PC does not have must
resolve to nothing, not to a fabricated path.
"""

from __future__ import annotations

import pathlib

from beanie.searchindex import FileIndex, parse_query


def _tree(root: pathlib.Path) -> pathlib.Path:
    files = {
        "Music/kaba.mp3": "x",
        "Music/misc/Kaba by Kapeke.m4a": "x",
        "Music/misc/burna - last last.mp3": "x",
        "Downloads/ka_bba.live.mpg": "x",              # near-spelling of "kaba", video
        "Downloads/report.pdf": "x",
        "Documents/kabana notes.txt": "x",             # shares a prefix, is not the song
        "Documents/notes on kabaka.txt": "x",
        "Pictures/team photo.jpg": "x",
        "Pictures/kaba cover.png": "x",
    }
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return root


def test_finds_the_song_regardless_of_naming(tmp_path):
    index = FileIndex(roots=[_tree(tmp_path)])
    index.build()
    results = index.search("kaba song")
    assert results
    names = {pathlib.Path(m.path).name for m in results}
    assert "kaba.mp3" in names
    assert "Kaba by Kapeke.m4a" in names
    # kind hint "song" → audio only: the video and the notes stay out
    assert all(pathlib.Path(m.path).suffix.lstrip(".") in ("mp3", "m4a") for m in results)


def test_kind_hints_filter_by_media_class(tmp_path):
    index = FileIndex(roots=[_tree(tmp_path)])
    index.build()
    # kind hint "video" → only video files: the near-named mpg lands, the png stays out
    assert {pathlib.Path(m.path).name for m in index.search("kaba video")} == {"ka_bba.live.mpg"}
    photos = index.search("kaba picture")
    assert [pathlib.Path(m.path).name for m in photos] == ["kaba cover.png"]
    parsed = parse_query("play the kaba song")
    assert parsed.kind == "audio" and "kaba" in parsed.terms and "song" not in parsed.terms


def test_near_spelling_still_lands(tmp_path):
    index = FileIndex(roots=[_tree(tmp_path)])
    index.build()
    results = index.search("kabba video")
    assert results and pathlib.Path(results[0].path).name == "ka_bba.live.mpg"
    assert "near spelling" in results[0].why


def test_missing_files_resolve_to_nothing_never_a_fabrication(tmp_path):
    index = FileIndex(roots=[_tree(tmp_path)])
    index.build()
    assert index.search("zickzack neverheard") == []
    # "kaba notes" must *not* secretly return the song: notes and txt remain top
    results = index.search("kaba notes")
    assert results and all("notes" in pathlib.Path(m.path).name or "kabana" in pathlib.Path(m.path).name
                           for m in results)


def test_scores_rank_the_plain_name_first(tmp_path):
    index = FileIndex(roots=[_tree(tmp_path)])
    index.build()
    results = index.search("kaba")
    assert results[0].score >= results[-1].score
    assert pathlib.Path(results[0].path).name == "kaba.mp3"


def test_incremental_refresh_picks_up_changes_and_prunes_ghosts(tmp_path):
    root = _tree(tmp_path)
    index = FileIndex(roots=[root], state_file=tmp_path / "state" / "index.json")
    first = index.build()
    assert first["indexed"] == 9  # _tree stages nine files
    second = index.build()
    assert second["changed"] == 0  # nothing changed → nothing rescanned

    (root / "Music" / "kaba.mp3").write_text("changed")
    (root / "Downloads" / "report.pdf").unlink()
    third = index.build()
    assert third["changed"] == 1 and third["pruned"] == 1
    assert index.search("report pdf") == []

    # persistence: a fresh index over the same state file knows the same files
    reloaded = FileIndex(roots=[root], state_file=tmp_path / "state" / "index.json")
    assert reloaded.count() == index.count()
    assert {m.path for m in reloaded.search("kaba")} == {m.path for m in index.search("kaba")}


def test_hidden_and_system_directories_are_never_indexed(tmp_path):
    (tmp_path / ".cache" / "secret").mkdir(parents=True)
    (tmp_path / ".cache" / "secret" / "kaba.mp3").write_text("x")
    (tmp_path / "Program Files").mkdir()
    (tmp_path / "Program Files" / "kaba.m4a").write_text("x")
    (tmp_path / "visible").mkdir()
    (tmp_path / "visible" / "kaba.mp3").write_text("x")
    index = FileIndex(roots=[tmp_path])
    index.build()
    assert [m.path for m in index.search("kaba")] == [str(tmp_path / "visible" / "kaba.mp3")]
