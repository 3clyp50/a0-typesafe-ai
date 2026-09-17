"""Install the official SDK and skill; preserve shared packages and user edits."""

import hashlib
from importlib import metadata
import json
from pathlib import Path
import subprocess
import sys

from helpers import files


ROOT = Path(__file__).resolve().parent
RECORD = ROOT / ".skill-install.json"


def install():
    requirement = (ROOT / "requirements.txt").read_text().strip()
    package, version = requirement.split("==")
    try:
        installed = metadata.version(package)
    except metadata.PackageNotFoundError:
        installed = None
    if installed != version:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "--disable-pip-version-check", requirement],
            check=True,
        )

    target = Path(files.get_abs_path("usr/skills/typesafe-ai"))
    target.mkdir(parents=True, exist_ok=True)
    owned = json.loads(RECORD.read_text()) if RECORD.exists() else {}
    for source in (ROOT / "resources/typesafe-ai").iterdir():
        destination = target / source.name
        if not destination.exists() or (
            source.name in owned
            and hashlib.sha256(destination.read_bytes()).hexdigest() == owned[source.name]
        ):
            content = source.read_bytes()
            destination.write_bytes(content)
            owned[source.name] = hashlib.sha256(content).hexdigest()
    RECORD.write_text(json.dumps(owned))


def uninstall():
    target = Path(files.get_abs_path("usr/skills/typesafe-ai"))
    owned = json.loads(RECORD.read_text()) if RECORD.exists() else {}
    for name, digest in owned.items():
        if name not in {"SKILL.md", "LICENSE"}:
            continue
        path = target / name
        if path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == digest:
            path.unlink()
    if target.is_dir() and not any(target.iterdir()):
        target.rmdir()
    RECORD.unlink(missing_ok=True)


def save_plugin_config(settings, **kwargs):
    from usr.plugins.typesafe_ai.helpers.jev import validate_config

    validate_config(settings)
    return settings
