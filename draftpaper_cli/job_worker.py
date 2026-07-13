"""Isolated worker entry point for the durable scientific job controller."""

from __future__ import annotations

import argparse

from .jobs import run_job_worker


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--database", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args()
    return run_job_worker(args.database, args.job_id)


if __name__ == "__main__":
    raise SystemExit(main())
