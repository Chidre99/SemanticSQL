import sys
from pathlib import Path

# Add backend/ to sys.path so `import app.*` works in tests when pytest is
# invoked from the repo root or from backend/.
BACKEND = Path(__file__).resolve().parents[1]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))
