"""Evaluate every local audio/reference/prediction pair in a pinned manifest."""

import argparse
import json
from pathlib import Path

from tabber.pairs import evaluate_manifest, inspect_manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--max-shift", type=float, default=5.0)
    parser.add_argument("--step", type=float, default=0.01)
    args = parser.parse_args()
    try:
        _, checked = inspect_manifest(args.manifest)
        protected = {args.manifest.resolve()}
        protected.update(path for _, paths in checked for path in paths.values())
        if args.output.resolve() in protected:
            raise ValueError("Output must not overwrite the manifest or any source asset")
        report = evaluate_manifest(args.manifest, max_shift=args.max_shift, step=args.step)
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    except (OSError, ValueError, TypeError, KeyError) as error:
        parser.exit(1, f"Could not evaluate pairs: {error}\n")
    print(f"Evaluated all {len(report['pairs'])} declared pairs; sources unchanged.")
    print(f"Report: {args.output.resolve()}")


if __name__ == "__main__":
    main()
