"""PyInstaller entry point: it needs a script path, so this mirrors recast/__main__.py."""

from recast.app import main

raise SystemExit(main())
