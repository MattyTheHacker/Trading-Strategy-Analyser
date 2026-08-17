"""The archive merge: the layer that stops a moving-window export from erasing history."""

import pytest

from nqbt import archive, ingest

BASE = [
    "20240308 213000;18000.25;18002.00;17999.50;18001.00;120",
    "20240308 213100;18001.00;18003.25;18000.75;18002.50;98",
    "20240308 213200;18002.50;18004.00;18001.25;18001.75;143",
]


def write(path, lines):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def dirs(tmp_path):
    manual, addon, arch = tmp_path / "minute", tmp_path / "addon", tmp_path / "archive"
    for d in (manual, addon):
        d.mkdir()
    return manual, addon, arch


def archived(arch):
    return (arch / "MNQ 03-24.Last.txt").read_text(encoding="utf-8").splitlines()


def test_union_of_two_sources_keeps_what_is_unique_to_each(dirs) -> None:
    manual, addon, arch = dirs
    # The real shape of the problem: the manual export holds a contract's final sessions,
    # the AddOn holds earlier history the manual export never had. Neither is a superset.
    early = "20240308 212800;17998.00;17999.00;17997.50;17998.50;60"
    late = "20240308 213300;18001.75;18002.50;18000.00;18000.25;77"
    write(manual / "MNQ 03-24.Last.txt", [*BASE, late])
    write(addon / "MNQ 03-24.Last.txt", [early, *BASE])

    result = archive.build_archive([manual, addon], arch)[0]
    assert result.bars == 5
    lines = archived(arch)
    assert lines[0] == early
    assert lines[-1] == late
    assert lines == sorted(lines), "archive must be in timestamp order"


def test_a_contract_missing_from_every_source_is_left_untouched(dirs) -> None:
    manual, addon, arch = dirs
    write(manual / "MNQ 03-24.Last.txt", BASE)
    archive.build_archive([manual, addon], arch)

    # Exactly what an expired contract becomes: the provider stops serving it, so it
    # vanishes from the sources. It must not vanish from the archive.
    (manual / "MNQ 03-24.Last.txt").unlink()
    archive.build_archive([manual, addon], arch)
    assert len(archived(arch)) == 3


def test_a_shrinking_source_cannot_shrink_the_archive(dirs) -> None:
    manual, addon, arch = dirs
    write(manual / "MNQ 03-24.Last.txt", BASE)
    archive.build_archive([manual, addon], arch)

    write(manual / "MNQ 03-24.Last.txt", BASE[:1])  # provider dropped the tail
    result = archive.build_archive([manual, addon], arch)[0]
    assert result.bars == 3
    assert len(archived(arch)) == 3


def test_the_newest_bar_of_a_source_may_insert_but_never_overwrite(dirs) -> None:
    manual, addon, arch = dirs
    # A bar caught mid-formation: a real manual export showed 294 contracts of an eventual
    # 890, with a high and close that had not happened yet.
    complete = "20240308 213300;18001.75;18010.00;17995.00;18008.25;890"
    partial = "20240308 213300;18001.75;18002.50;18001.00;18002.00;294"

    write(addon / "MNQ 03-24.Last.txt", [*BASE, complete])
    archive.build_archive([manual, addon], arch)

    write(manual / "MNQ 03-24.Last.txt", [*BASE, partial])
    result = archive.build_archive([manual, addon], arch)[0]
    assert archived(arch)[-1] == complete, "partial bar overwrote a complete one"
    assert result.revised == 0


def test_a_revised_bar_that_is_not_the_newest_does_overwrite(dirs) -> None:
    manual, addon, arch = dirs
    write(manual / "MNQ 03-24.Last.txt", BASE)
    archive.build_archive([manual, addon], arch)

    revised = "20240308 213100;18001.00;18003.25;18000.75;18002.50;101"
    write(addon / "MNQ 03-24.Last.txt", [BASE[0], revised, BASE[2]])
    result = archive.build_archive([manual, addon], arch)[0]
    assert result.revised == 1
    assert archived(arch)[1] == revised


def test_later_sources_win_a_disagreement(dirs) -> None:
    manual, addon, arch = dirs
    # Both hold the same bar with different values, and neither is its file's newest.
    theirs = "20240308 213100;18001.00;18003.25;18000.75;18002.50;77"
    write(manual / "MNQ 03-24.Last.txt", BASE)
    write(addon / "MNQ 03-24.Last.txt", [BASE[0], theirs, BASE[2]])
    archive.build_archive([manual, addon], arch)
    assert archived(arch)[1] == theirs


def test_rerunning_an_unchanged_merge_is_byte_identical(dirs) -> None:
    manual, addon, arch = dirs
    write(manual / "MNQ 03-24.Last.txt", BASE)
    archive.build_archive([manual, addon], arch)
    first = (arch / "MNQ 03-24.Last.txt").read_bytes()

    result = archive.build_archive([manual, addon], arch)[0]
    # Byte-identical output is what lets ingestion's content hash say "up-to-date" instead
    # of reparsing millions of bars on every run.
    assert (arch / "MNQ 03-24.Last.txt").read_bytes() == first
    assert (result.added, result.revised) == (0, 0)


def test_sources_that_disagree_do_not_report_churn_on_a_repeat_merge(dirs) -> None:
    manual, addon, arch = dirs
    # The sources hold different volumes for the same bar, so every merge has the earlier
    # source overwrite and the later one overwrite back. Counting those intermediate
    # writes made an idempotent merge report 11 contracts "changed" against real data.
    theirs = "20240308 213100;18001.00;18003.25;18000.75;18002.50;77"
    write(manual / "MNQ 03-24.Last.txt", BASE)
    write(addon / "MNQ 03-24.Last.txt", [BASE[0], theirs, BASE[2]])

    archive.build_archive([manual, addon], arch)
    before = (arch / "MNQ 03-24.Last.txt").read_bytes()

    result = archive.build_archive([manual, addon], arch)[0]
    assert (result.added, result.revised) == (0, 0)
    assert (arch / "MNQ 03-24.Last.txt").read_bytes() == before


def test_prices_are_passed_through_as_text(dirs) -> None:
    manual, addon, arch = dirs
    # Parsing to float and formatting back is a needless chance to change a value.
    odd = "20240308 213400;18000.10;18000.70;17999.30;18000.30;7"
    write(manual / "MNQ 03-24.Last.txt", [*BASE, odd])
    archive.build_archive([manual, addon], arch)
    assert odd in archived(arch)


def test_half_written_final_line_is_skipped_not_fatal(dirs) -> None:
    manual, addon, arch = dirs
    path = manual / "MNQ 03-24.Last.txt"
    write(path, BASE)
    path.write_text(path.read_text() + "20240308 2133", encoding="utf-8")

    result = archive.build_archive([manual, addon], arch)[0]
    assert result.bars == 3


def test_root_filter_only_touches_matching_contracts(dirs) -> None:
    manual, addon, arch = dirs
    write(manual / "MNQ 03-24.Last.txt", BASE)
    write(manual / "NQ 03-24.Last.txt", BASE)
    results = archive.build_archive([manual, addon], arch, root="NQ")
    assert [r.contract for r in results] == ["NQ 03-24"]
    assert not (arch / "MNQ 03-24.Last.txt").exists()


def test_ingest_reads_the_archive_and_sees_both_sources(dirs, tmp_path) -> None:
    manual, addon, arch = dirs
    early = "20240308 212800;17998.00;17999.00;17997.50;17998.50;60"
    write(manual / "MNQ 03-24.Last.txt", BASE)
    write(addon / "MNQ 03-24.Last.txt", [early, *BASE])

    merges, results = ingest.ingest_all(
        sources=[manual, addon],
        archive_dir=arch,
        cache_dir=tmp_path / "cache",
    )
    assert len(merges) == 1
    assert merges[0].bars == 4
    assert results[0].rows_total == 4
