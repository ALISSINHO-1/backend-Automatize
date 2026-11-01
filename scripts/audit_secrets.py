"""Report filenames only; never prints candidate credentials or matches."""
from pathlib import Path
import re
import subprocess

from dotenv import dotenv_values


def main():
    root = Path(__file__).resolve().parents[1]
    environment_files = [p for p in root.glob(".env*") if p.name != ".env.example" and p.is_file()]
    secrets = []
    for path in environment_files:
        for name, value in dotenv_values(path).items():
            if value and len(value) >= 12 and any(key in name.upper() for key in ("PASSWORD", "SECRET", "KEY", "DATABASE_URL")):
                secrets.append(value)
    tracked = set(filter(None, subprocess.check_output(["git", "ls-files", "-z"], cwd=root).decode().split("\0")))
    paths = set(filter(None, subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root,
    ).decode().split("\0")))
    findings = {str(p.relative_to(root)) for p in environment_files if dotenv_values(p)}
    exposed = set()
    for name in paths:
        path = root / name
        if not path.is_file() or path.stat().st_size > 5_000_000:
            continue
        try:
            content = path.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        if any(value in content for value in secrets) or re.search(r"eyJ[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}\.[A-Za-z0-9_-]{16,}", content):
            findings.add(name)
            if name in tracked:
                exposed.add(name)
    for name in sorted(findings):
        print(f"segredo potencial encontrado em arquivo {name}")
    print(f"Arquivos versionados com correspondencia potencial: {len(exposed)}")
    print(f"Bytecode versionado: {sum(name.endswith('.pyc') or '__pycache__' in name for name in tracked)}")
    return 1 if exposed else 0


if __name__ == "__main__":
    raise SystemExit(main())
