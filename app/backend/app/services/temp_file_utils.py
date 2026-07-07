from __future__ import annotations

import os
from pathlib import Path

from app.services.path_utils import filesystem_path


def remove_file_best_effort(path: str | Path, *, scrub: bool = False) -> bool:
    """Remove a temporary file without letting cleanup mask the primary result."""
    target = Path(path)
    target_path = filesystem_path(target)
    if scrub:
        try:
            if os.path.exists(target_path):
                with open(target_path, "w", encoding="utf-8") as handle:
                    handle.write("")
        except OSError:
            pass
    try:
        os.unlink(target_path)
    except FileNotFoundError:
        return True
    except OSError:
        return False
    return True
