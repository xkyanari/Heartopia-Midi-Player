"""Build the player from one snapshot; record the version after frozen checks."""
import argparse
from datetime import datetime
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS = ["pyinstaller==6.22.3", "pyinstaller-hooks-contrib==2026.7"]


def sha256(path):
    with Path(path).open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def version(path):
    return re.search(r'^APP_VERSION = "v([\d.]+)"$', path.read_text(encoding="utf-8"), re.M)[1]


def run(args, cwd, logfile, env=None):
    with logfile.open("w", encoding="utf-8") as log:
        subprocess.run([str(arg) for arg in args], cwd=cwd, env=env, stdout=log,
                       stderr=subprocess.STDOUT, check=True)


def build():
    if sys.platform != "win32" or sys.version_info[:2] != (3, 12):
        raise SystemExit("Build with 64-bit Windows Python 3.12.")
    directory = ROOT / "build" / datetime.now().strftime("release-%Y%m%d-%H%M%S")
    snapshot = directory / "snapshot"
    snapshot.mkdir(parents=True)
    # Explicit source allowlist: never copy local settings, songs, venvs
    # or a stale dist directory into the release snapshot.
    sources = [p for p in ROOT.iterdir() if p.is_file() and
               (p.suffix in (".py", ".spec", ".md") or p.name.startswith("requirements")
                or p.name == "version_info.txt")]
    for folder in ("tests", "tools"):
        sources.extend(p for p in (ROOT / folder).rglob("*.py") if "__pycache__" not in p.parts)
    for source in sources:
        destination = snapshot / source.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    hashes = {str(p.relative_to(snapshot)): sha256(p) for p in snapshot.rglob("*") if p.is_file()}
    previous = version(snapshot / "app_config.py")
    major, minor, patch = map(int, previous.split("."))
    following = f"{major}.{minor}.{patch + 1}"
    report = {"previous_version": previous, "version": following, "source_hashes": hashes, "artifacts": {}}
    report_path = directory / "release.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Release snapshot: {directory}", flush=True)
    checkout = directory / "source"
    shutil.copytree(snapshot, checkout)
    assert all(sha256(checkout / name) == digest for name, digest in hashes.items())
    environment = directory / "venv"
    venv.EnvBuilder(with_pip=True).create(environment)
    python = environment / "Scripts/python.exe"
    print("Installing clean build environment", flush=True)
    run([python, "-m", "pip", "install", "-r", checkout / "requirements.txt", *BUILD_TOOLS], checkout,
        directory / "install.log")
    run([python, "-m", "pip", "freeze"], checkout, directory / "freeze.txt")
    print(f"Building {following}", flush=True)
    run([python, "-m", "PyInstaller", "--clean", "--noconfirm", "main-current.spec"], checkout,
        directory / "build.log")
    assert version(checkout / "app_config.py") == following
    output = checkout / "dist" / f"main-{following}.exe"
    destination = ROOT / "dist" / output.name
    destination.parent.mkdir(exist_ok=True)
    # Review artifacts can be replaced by a later build of the same release.
    shutil.copy2(output, destination)
    report["artifacts"]["player"] = {"path": str(destination), "bytes": destination.stat().st_size,
                                    "sha256": sha256(destination), "source": str(checkout)}
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"{destination.stat().st_size:,} bytes", flush=True)
    print(f"Frozen-check the artifact, then record once: {sys.executable} tools/build_release.py record {report_path}", flush=True)


def record(report_path):
    report = json.loads(report_path.read_text(encoding="utf-8"))
    if set(report["artifacts"]) != {"player"}:
        raise SystemExit("The artifact must be built before recording a release.")
    for artifact in report["artifacts"].values():
        if sha256(artifact["path"]) != artifact["sha256"]:
            raise SystemExit("An artifact differs from the release manifest.")
    config = ROOT / "app_config.py"
    if version(config) != report["previous_version"]:
        raise SystemExit("Workspace version changed or this release was already recorded.")
    config.write_text(config.read_text(encoding="utf-8").replace(
        f'APP_VERSION = "v{report["previous_version"]}"', f'APP_VERSION = "v{report["version"]}"', 1), encoding="utf-8")
    shutil.copy2(Path(report["artifacts"]["player"]["source"]) / "version_info.txt", ROOT / "version_info.txt")
    report["recorded"] = True
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(f"Recorded v{report['version']} once in workspace config and Windows metadata.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=("build", "record"))
    parser.add_argument("manifest", nargs="?", type=Path)
    args = parser.parse_args()
    if args.action == "build":
        build()
    elif args.manifest:
        record(args.manifest)
    else:
        parser.error("record requires a release.json path")
