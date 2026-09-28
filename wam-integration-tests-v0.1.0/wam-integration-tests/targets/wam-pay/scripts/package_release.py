"""Package only reviewed source files; exclude data, credentials and git metadata."""
import hashlib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = {"README.md", "SECURITY.md", "CONTRIBUTING.md", "CHANGELOG.md", "LICENSE", ".gitignore", "config.example.json"}
DIRS = {"src", "tests", "docs", "scripts", ".github"}
SUFFIXES = {".py", ".md", ".js", ".html", ".css", ".json", ".yml", ".yaml", ".sh", ".ps1"}


def main():
    output = ROOT / "dist" / "wam-pay-v0.1.0.zip"
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(ROOT.rglob("*")):
            if not path.is_file():
                continue
            rel = path.relative_to(ROOT)
            if (len(rel.parts) == 1 and rel.name in TOP) or (
                rel.parts[0] in DIRS and "__pycache__" not in rel.parts and path.suffix in SUFFIXES):
                if path.is_symlink():
                    raise ValueError("Refusing to package symlink")
                info = zipfile.ZipInfo("wam-pay/" + rel.as_posix(), date_time=(2026, 9, 28, 0, 0, 0))
                info.external_attr = 0o100644 << 16
                info.compress_type = zipfile.ZIP_DEFLATED
                archive.writestr(info, path.read_bytes())
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    output.with_suffix(".zip.sha256").write_text(f"{digest}  {output.name}\n", encoding="ascii")
    print(f"{output}\nSHA256 {digest}")


if __name__ == "__main__":
    main()
