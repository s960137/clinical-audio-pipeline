"""Small, explicit command-line interface; never print raw source exceptions."""

import argparse
import json
import os
import sys

from .demo import run_demo
from .pipeline import run_pipeline


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audio-to-spreadsheet data preparation; no clinical diagnosis")
    commands = parser.add_subparsers(dest="command", required=True)
    demo = commands.add_parser("demo", help="Run an entirely synthetic loopback HTTP demo")
    demo.add_argument("--out", default="demo-output")
    run = commands.add_parser("run", help="Process authorized opaque-ID inputs into a new directory")
    run.add_argument("--visits", required=True)
    run.add_argument("--recordings", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--allow-host", action="append", required=True)
    run.add_argument("--tolerance-seconds", type=float, default=900)
    run.add_argument("--token-env", help="Name of an environment variable containing an authorized API bearer token")
    run.add_argument("--token-origin", help="Exact HTTPS origin authorized to receive the bearer token")
    collect = commands.add_parser("collect", help="Collect an authorized site's manifest using configurable selectors")
    collect.add_argument("--config", required=True)
    collect.add_argument("--out", required=True)
    collect.add_argument("--browser", choices=["edge", "chrome"], default="edge")
    args = parser.parse_args(argv)
    try:
        if args.command == "demo":
            result = run_demo(args.out)
        elif args.command == "collect":
            from .browser import collect_manifest
            result = collect_manifest(args.config, args.out, args.browser)
        else:
            token = os.environ.get(args.token_env) if args.token_env else None
            if args.token_env and not token:
                raise ValueError("Requested token environment variable is absent or empty")
            result = run_pipeline(args.visits, args.recordings, args.out, args.allow_host,
                                  args.tolerance_seconds, token, args.token_origin)
        print(json.dumps(result, indent=2))
        return 0
    except KeyboardInterrupt:
        print("Interrupted; existing inputs and outputs are preserved.", file=sys.stderr)
        return 130
    except Exception as error:
        # Third-party errors can contain URLs, local filenames or response payloads.
        print(f"Pipeline stopped ({type(error).__name__}). Check schema, output path and access configuration. "
              "Raw exception details are intentionally suppressed.", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
