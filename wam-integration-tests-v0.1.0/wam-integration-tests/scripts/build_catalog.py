#!/usr/bin/env python3
"""Render the static case catalog without executing or importing test targets."""
import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    rows = []
    for group in ("tests", "scenarios"):
        for path in sorted((ROOT / group).glob("*.py")):
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                if not isinstance(node, ast.FunctionDef): continue
                for d in node.decorator_list:
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "case":
                        profile, ident, description = [ast.literal_eval(x) for x in d.args]
                        rows.append((profile, ident, description, path.relative_to(ROOT).as_posix()))
    if len({r[1] for r in rows}) != len(rows): raise ValueError("Duplicate case ID")
    text = "# Test catalog\n\nStatic descriptions corresponding to public report IDs.\n\n"
    text += "`selftest` uses local synthetic RPC servers and filesystem fixtures. "
    text += "`regtest` runs actual WAM nodes and bundled applications; PAY-011 and WT-004–005 "
    text += "also inject synthetic faults. WT-003 is a stronger criterion than the legacy stable-hash design.\n\n"
    for profile in ("selftest", "regtest"):
        text += f"## {profile}\n\n| ID | Criterion | Source |\n|---|---|---|\n"
        for pr, ident, desc, path in sorted(rows):
            if pr == profile: text += f"| {ident} | {desc} | `{path}` |\n"
        text += "\n"
    (ROOT / "docs" / "TEST_CATALOG.md").write_text(text, encoding="utf-8")
    print(f"Catalog: {len(rows)} cases")


if __name__ == "__main__": main()
