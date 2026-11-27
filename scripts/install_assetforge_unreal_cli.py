"""Use the same project checks and transaction as the Windows installation assistant."""

import argparse
from pathlib import Path
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("project", type=Path)
    parser.add_argument("engine_root", type=Path)
    parser.add_argument("--source", action="store_true", help="Install the project plugin from source.")
    parser.add_argument("--check-only", action="store_true", help="Check compatibility without writing.")
    args = parser.parse_args(argv)

    plugin = Path(__file__).resolve().parent.parent / "Payload" / "Unreal"
    runtime = plugin / "Source" / "AssetForge" / "Content" / "Python"
    if not (runtime / "asset_forge" / "unreal" / "distribution_installer.py").is_file():
        parser.error("Extract the entire release ZIP before running the script.")
    sys.path.insert(0, str(runtime))
    from asset_forge.unreal.distribution_installer import install, plan_install

    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8", errors="backslashreplace")
    run = plan_install if args.check_only else install
    result = run(args.project, plugin, args.engine_root, source=args.source)
    print(result["message"])
    if result.get("backup_dir"):
        print("Backup:", result["backup_dir"])
    return 0 if result["status"] in ("ready", "success") else 1


if __name__ == "__main__":
    raise SystemExit(main())
