from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.main import app, create_app
from app.api.dependencies import get_document_service, get_rate_limiter

__all__ = [
    "app",
    "create_app",
    "get_document_service",
    "get_rate_limiter",
]
