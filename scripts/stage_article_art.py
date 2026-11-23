"""Stage editorial cover directories and check the references served by Pages."""
from pathlib import Path
import json
import shutil
import sys


def stage(root, destination):
    for folder in ("assets/article-art", "assets/editorial-covers"):
        source = root / folder
        if source.is_dir():
            shutil.copytree(source, destination / folder, dirs_exist_ok=True)

    records = json.loads((root / "data/public-library.json").read_text(encoding="utf-8"))
    for record in records:
        art = record.get("editorial_art") or {}
        if art.get("status") != "ready":
            continue
        paths = [art["src"]]
        if art.get("thumbnail_src"):
            paths.append(art["thumbnail_src"])
        for path in paths:
            if not (destination / path).is_file():
                raise FileNotFoundError(f"Missing published cover asset {path} for {record.get('title')}")


if __name__ == "__main__":
    stage(Path(__file__).resolve().parents[1], Path(sys.argv[1]))
