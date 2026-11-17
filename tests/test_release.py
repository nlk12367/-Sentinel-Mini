"""Release assembly must preserve existing files and exclude undeclared data."""

from pathlib import Path
from zipfile import ZipFile

import pytest

from scripts import build_release


@pytest.fixture
def project(tmp_path, monkeypatch):
    root = tmp_path / "project"
    root.mkdir()
    monkeypatch.setattr(build_release, "PROJECT", root)
    return root


def write(root: Path, name: str, content: str = "fixture") -> Path:
    file = root / name
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")
    return file


def test_release_includes_only_declared_deliverables(project):
    included = [
        "app.py",
        "README.md",
        "sentinel/core.py",
        "sentinel/static/app.js",
        "tests/test_example.py",
        "scripts/build_release.py",
        "examples/codex-demo.json",
    ]
    excluded = [
        "data/history.json",
        "data/runs.sqlite3",
        ".env",
        "credentials.toml",
        "private-notes.md",
        "examples/private.json",
        "sentinel/config.json",
        "sentinel/__pycache__/private.py",
        ".venv/lib/private.py",
    ]
    for name in included + excluded:
        write(project, name)
    output = project.parent / "release.zip"
    assert build_release.build_release(output) == len(included)
    with ZipFile(output) as archive:
        assert archive.testzip() is None
        assert set(archive.namelist()) == {f"project/{name}" for name in included}
    assert all((project / name).read_text() == "fixture" for name in included + excluded)


def test_existing_archive_is_preserved(project):
    output = write(project.parent, "existing.zip", "keep-original")
    with pytest.raises(FileExistsError):
        build_release.build_release(output)
    assert output.read_text() == "keep-original"


@pytest.mark.parametrize("inside,suffix", [(False, ".py"), (True, ".zip")])
def test_invalid_output_is_rejected_before_writing(project, inside, suffix):
    output = (project if inside else project.parent) / f"output{suffix}"
    with pytest.raises(ValueError):
        build_release.build_release(output)
    assert not output.exists()


def test_list_mode_only_reads_declared_files(project, monkeypatch, capsys):
    write(project, "README.md")
    monkeypatch.setattr("sys.argv", ["build_release.py", "--list"])
    before = set(project.parent.rglob("*"))
    build_release.main()
    assert capsys.readouterr().out.strip() == "README.md"
    assert set(project.parent.rglob("*")) == before
