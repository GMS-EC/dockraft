import os
import sys
from pathlib import Path

# Ensure project root is in sys.path across all test runs and CI runners
ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

# Provide a default test ADMIN_PASSWORD so fail-closed auth works for authenticated TestClient suites
os.environ.setdefault("ADMIN_PASSWORD", "test-admin-password")
