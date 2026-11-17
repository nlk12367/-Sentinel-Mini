"""Build a source release, excluding local history, credentials, and caches."""

import argparse
import hashlib
import shutil
import tempfile
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

PROJECT = Path(__file__).resolve().parents[1]
EXCLUDED = {"data", "__pycache__", ".pytest_cache", ".venv", "htmlcov"}
ROOT_FILES = {".gitignore", "app.py", "README.md", "ARCHITECTURE.md", "pyproject.toml", "start.bat"}
EXAMPLE_FILES = {"codex-demo.json", "codex-demo.md"}


def release_files() -> list[Path]:
    """Select declared deliverables; never follow links outside the project."""
    project = PROJECT.resolve()
    selected = []
    for file in sorted(project.rglob("*")):
        relative = file.relative_to(project)
        if EXCLUDED.intersection(relative.parts):
            continue
        if file.is_symlink() or not file.is_file() or not file.resolve().is_relative_to(project):
            continue
        parts = relative.parts
        allowed = len(parts) == 1 and file.name in ROOT_FILES
        if len(parts) > 1:
            allowed = (
                (parts[0] in {"sentinel", "tests", "scripts"} and file.suffix == ".py")
                or (parts[:2] == ("sentinel", "static") and file.suffix in {".html", ".css", ".js"})
                or (len(parts) == 2 and parts[0] == "examples" and file.name in EXAMPLE_FILES)
            )
        if allowed:
            selected.append(file)
    return selected


def build_release(destination: Path) -> int:
    """Publish a checked source archive without overwriting existing files."""
    destination = destination.resolve()
    if destination.suffix.lower() != ".zip":
        raise ValueError("Output must use the .zip extension.")
    if destination.is_relative_to(PROJECT.resolve()):
        raise ValueError("Choose an output outside the project directory.")
    if destination.exists():
        raise FileExistsError(f"Refusing to overwrite existing file: {destination}")
    files = release_files()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".sentinel-release-", dir=destination.parent) as directory:
        temporary = Path(directory) / "release.zip"
        with ZipFile(temporary, "w", ZIP_DEFLATED) as archive:
            for file in files:
                relative = file.relative_to(PROJECT)
                archive.write(file, (Path(PROJECT.name) / relative).as_posix())
        with ZipFile(temporary) as archive:
            if archive.testzip() is not None:
                raise ValueError("ZIP integrity check failed.")
        # Exclusive creation also protects against a file appearing after the
        # initial existence check. Only our temporary directory is cleaned up.
        with temporary.open("rb") as source, destination.open("xb") as output:
            shutil.copyfileobj(source, output)
    return len(files)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=PROJECT.parent / f"{PROJECT.name}-safe.zip")
    parser.add_argument("--list", action="store_true", help="List release contents without writing files.")
    args = parser.parse_args()
    if args.list:
        for file in release_files():
            print(file.relative_to(PROJECT).as_posix())
        return
    destination = args.output.resolve()
    try:
        count = build_release(destination)
    except (OSError, ValueError) as exc:
        parser.exit(1, f"Build failed: {exc}\n")
    digest = hashlib.sha256(destination.read_bytes()).hexdigest()
    print(f"{destination}\nFiles: {count}\nSHA256: {digest}")


if __name__ == "__main__":
    main()
