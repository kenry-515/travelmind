"""pytest 公共夹具：让 tests/ 能直接 import app.*（从 backend/ 根运行）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
