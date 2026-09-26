from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Keep test databases and media away from the user's real application data.
TEST_DATA_DIR = Path(tempfile.mkdtemp(prefix="kodkon-studio-tests-"))
os.environ["KODKON_DATA_DIR"] = str(TEST_DATA_DIR)
