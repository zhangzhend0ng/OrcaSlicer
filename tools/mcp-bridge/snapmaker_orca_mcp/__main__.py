"""Entry point: python -m snapmaker_orca_mcp [--exe PATH] [--log-level LEVEL]."""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import mcp.server.stdio as mcp_stdio

from .config import BridgeConfig
from .errors import BridgeError
from .server import ToolRegistry, build_server, default_handlers, load_schema


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="snapmaker-orca-mcp")
    ap.add_argument("--exe", help="Path to snapmaker-orca executable")
    ap.add_argument(
        "--backends",
        default="cli",
        help="Comma list of enabled backends: cli,session (session=M1+)",
    )
    ap.add_argument("--log-level", default="WARNING")
    args = ap.parse_args(argv)

    logging.basicConfig(
        stream=sys.stderr,
        level=getattr(logging, args.log_level.upper(), logging.WARNING),
        format="%(name)s %(levelname)s %(message)s",
    )

    backends = [b.strip() for b in args.backends.split(",") if b.strip()]
    config = BridgeConfig(exe_path=args.exe)
    schema = load_schema()
    handlers = default_handlers(config, backends)
    registry = ToolRegistry(schema, handlers, backends)
    server = build_server(registry)

    async def _run() -> None:
        async with mcp_stdio.stdio_server() as (read, write):
            await server.run(
                read, write, server.create_initialization_options()
            )

    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        return 0
    except BrokenPipeError:
        return 0
    except BridgeError as exc:
        print(f"snapmaker-orca-mcp: fatal: [{exc.code}] {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
