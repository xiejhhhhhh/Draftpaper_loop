"""Allow ``python -m draftpaper_cli`` to use the public CLI entry point."""

from .cli import main

if __name__ == "__main__":
    raise SystemExit(main())
