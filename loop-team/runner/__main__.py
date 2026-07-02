"""runner/__main__.py — CLI entry point for python -m runner."""
import argparse
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="python -m runner",
        description="loop-team runner: dispatch roles and run write→verify→fix loops.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Usage examples:
  python -m runner --help
  python -m runner dispatch --role coder --context "Write a hello-world function"
  python -m runner run --brief path/to/brief.md

Configuration:
  Config file: ~/.loop-team-config
  Keys: base_dir, provider, default_model, role.<name>.provider, role.<name>.model

See USAGE.md for full documentation.
""",
    )

    subparsers = parser.add_subparsers(dest="command", metavar="COMMAND")

    # dispatch subcommand
    dispatch_parser = subparsers.add_parser(
        "dispatch",
        help="Dispatch a single role with a context string.",
    )
    dispatch_parser.add_argument(
        "--role", required=True,
        help="Role name to dispatch (e.g. coder, verifier, researcher).",
    )
    dispatch_parser.add_argument(
        "--context", required=True,
        help="Context/brief string to pass to the role.",
    )
    dispatch_parser.add_argument(
        "--config", default=None,
        help="Path to config file (default: ~/.loop-team-config).",
    )

    # run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run the full write→verify→fix loop with a brief.",
    )
    run_parser.add_argument(
        "--brief", required=True,
        help="Path to brief file or inline brief string.",
    )
    run_parser.add_argument(
        "--config", default=None,
        help="Path to config file (default: ~/.loop-team-config).",
    )
    run_parser.add_argument(
        "--run-dir", default=None,
        help="Directory to write trace.jsonl/checkpoint.json/run_log.md. "
             "Default: ./runs/<timestamp>-runner. Pass --no-trace to disable.",
    )
    run_parser.add_argument(
        "--no-trace", action="store_true",
        help="Disable run tracing (no run_dir is created).",
    )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)

    from runner import LoopTeam  # noqa: PLC0415

    if args.command == "dispatch":
        team = LoopTeam(config_path=args.config)
        result = team.dispatch_role(args.role, args.context)
        print(result)

    elif args.command == "run":
        import pathlib  # noqa: PLC0415
        brief_path = pathlib.Path(args.brief)
        if brief_path.exists():
            brief = brief_path.read_text()
        else:
            brief = args.brief

        run_dir = None
        if not args.no_trace:
            if args.run_dir:
                run_dir = args.run_dir
            else:
                import datetime  # noqa: PLC0415
                ts = datetime.datetime.now().strftime("%Y-%m-%d_%H%M%S")
                run_dir = str(pathlib.Path.cwd() / "runs" / f"{ts}-runner")

        team = LoopTeam(config_path=args.config)
        result = team.run(brief, run_dir=run_dir)
        print(f"success={result.success} iterations={result.iterations}")
        if run_dir:
            print(f"trace: {run_dir}/trace.jsonl  ·  "
                  f"view: python3 loop-team/harness/dashboard.py")
        sys.exit(0 if result.success else 1)


if __name__ == "__main__":
    main()
