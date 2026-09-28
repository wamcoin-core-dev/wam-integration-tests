"""Create config.json once, without storing credentials."""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    target = ROOT / "config.json"
    config = json.loads((ROOT / "config.example.json").read_text(encoding="utf-8"))
    try:
        with target.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(config, indent=2) + "\n")
        target.chmod(0o600)
    except FileExistsError:
        print("config.json already exists; it was not changed.")
        return 0
    print("Created config.json in demo mode. See docs/SETUP.md for node configuration.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
