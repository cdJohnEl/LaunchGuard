"""Pytest bootstrap: put backend/ and the repo root on sys.path for direct imports."""
import sys
from pathlib import Path

_BACKEND = Path(__file__).resolve().parent
_ROOT = _BACKEND.parent
for _path in (str(_BACKEND), str(_ROOT)):
    if _path not in sys.path:
        sys.path.insert(0, _path)
