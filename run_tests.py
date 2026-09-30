from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
raise SystemExit(subprocess.call([sys.executable, "-m", "pytest", "-q"], cwd=ROOT))
