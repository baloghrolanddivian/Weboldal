"""Explicit maintenance command for rebuilding manufacturing missing indexes."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
PYCODE_ROOT = REPO_ROOT / "pycode"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Rebuild manufacturing missing/red snapshot JSON files from every "
            "persisted production state. This can be very slow and is never run by the web UI."
        )
    )
    parser.add_argument(
        "--operation",
        choices=("all", "pantolo", "front", "korpusz"),
        default="all",
        help="Limit the rebuild to one operation (default: all).",
    )
    parser.add_argument(
        "--runtime-dir",
        type=Path,
        default=REPO_ROOT / "runtime" / "gyartasi-papirok",
        help="Manufacturing runtime directory containing production state.json files.",
    )
    parser.add_argument(
        "--manufacturing-root",
        type=Path,
        help="Optional Gyartasi_papirok source root; otherwise DIVIAN_MANUFACTURING_ROOT/default is used.",
    )
    parser.add_argument(
        "--confirm-extensive-rebuild",
        action="store_true",
        help="Required safety acknowledgement for the potentially expensive full scan.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not args.confirm_extensive_rebuild:
        parser.error(
            "refusing to run without --confirm-extensive-rebuild; "
            "this command can heavily load the server"
        )

    if args.manufacturing_root:
        os.environ["DIVIAN_MANUFACTURING_ROOT"] = str(args.manufacturing_root.resolve())
    sys.path.insert(0, str(PYCODE_ROOT))

    from manufacturing import configure_manufacturing, rebuild_manufacturing_missing_indexes

    runtime_root = args.runtime_dir.resolve()
    configure_manufacturing(runtime_root)
    operations = ("pantolo", "front", "korpusz") if args.operation == "all" else (args.operation,)

    print("WARNING: scanning all production states and relevant historical XML files.", flush=True)
    print(f"Runtime: {runtime_root}", flush=True)
    print(f"Operations: {', '.join(operations)}", flush=True)
    try:
        result = rebuild_manufacturing_missing_indexes(runtime_root, operations, progress=print)
    except KeyboardInterrupt:
        print("Cancelled; existing indexes were left unchanged.", file=sys.stderr, flush=True)
        return 130
    except Exception as exc:
        print(f"FAILED: {exc}", file=sys.stderr, flush=True)
        print("Existing indexes were left unchanged.", file=sys.stderr, flush=True)
        return 1

    print("Rebuild complete.", flush=True)
    print(f"State files scanned: {result['state_files']}", flush=True)
    print(f"Red state keys considered: {result['red_state_keys']}", flush=True)
    for operation, count in result["snapshots"].items():
        print(f"{operation}: {count} indexed red rows", flush=True)
    print(f"Elapsed: {result['elapsed_seconds']} seconds", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
