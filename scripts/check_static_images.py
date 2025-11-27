import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SCAN_FILES = [
    REPO_ROOT / "app.py",
    *REPO_ROOT.glob("templates/**/*.html"),
]

STATIC_PATTERN = re.compile(r"/static/[^\"'\s)]+")


def collect_static_refs():
    refs = set()
    for file_path in SCAN_FILES:
        try:
            text = file_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for match in STATIC_PATTERN.findall(text):
            refs.add(match)
    return sorted(refs)


def main():
    missing = []
    refs = collect_static_refs()
    for ref in refs:
        target = REPO_ROOT / ref.lstrip("/")
        if not target.exists():
            missing.append(ref)
    print(f"Checked {len(refs)} static image references across {len(SCAN_FILES)} files.")
    if missing:
        print("Missing files:")
        for path in missing:
            print(f" - {path}")
    else:
        print("All referenced static assets were found.")


if __name__ == "__main__":
    main()
