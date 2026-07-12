"""CLI entry point.

Examples:
  python -m shorts_agent.main run --dry-run            # full pipeline, no upload
  python -m shorts_agent.main run --dry-run --no-llm   # force the built-in sample script
"""
from __future__ import annotations

import argparse
import logging
import os
import sys

from .config import load_config
from .pipeline import run_pipeline


def _load_dotenv(path: str = ".env") -> None:
    """Minimal .env loader (no extra dependency). Existing env vars win."""
    if not os.path.exists(path):
        return
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            os.environ.setdefault(key.strip(), val.strip().strip('"').strip("'"))


def _setup_logging() -> None:
    # Windows consoles default to cp1252; force UTF-8 so emojis don't crash output.
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)-7s %(name)-22s %(message)s",
        datefmt="%H:%M:%S",
    )


def main(argv=None) -> int:
    _load_dotenv()
    _setup_logging()
    parser = argparse.ArgumentParser(prog="shorts_agent")
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="Generate a Short end-to-end.")
    run.add_argument("--dry-run", action="store_true", default=True,
                     help="Render but do not upload (default in Fase 0).")
    run.add_argument("--upload", dest="dry_run", action="store_false",
                     help="Attempt upload (Fase 1 only; not implemented yet).")
    run.add_argument("--no-llm", action="store_true",
                     help="Skip the LLM and use the built-in sample script.")
    run.add_argument("--fresh", action="store_true",
                     help="Ignore the asset cache and regenerate images/voice.")

    sub.add_parser("check", help="Pre-flight: verify environment/config before going live.")
    sub.add_parser("stats", help="Refresh YouTube analytics and print the channel report.")

    args = parser.parse_args(argv)
    if args.command == "run":
        cfg = load_config()
        project = run_pipeline(cfg, dry_run=args.dry_run, use_llm=not args.no_llm,
                               fresh=args.fresh)
        print(f"\n[DONE] {project.output_path}")
        return 0
    if args.command == "check":
        from .infra.preflight import run_checks
        return 0 if run_checks(load_config()) else 1
    if args.command == "stats":
        from .infra.analytics import run_stats
        return run_stats(load_config())
    return 1


if __name__ == "__main__":
    sys.exit(main())
