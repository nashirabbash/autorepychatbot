import os
from dotenv import load_dotenv


def _get_int_env(name: str, default: int) -> int:
    """Parse int env safely with fallback default."""
    raw = os.getenv(name, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def _get_float_env(name: str, default: float) -> float:
    """Parse float env safely with fallback default."""
    raw = os.getenv(name, str(default))
    try:
        return float(raw)
    except (TypeError, ValueError):
        return default

# Load environment variables from .env file
load_dotenv()

# Telegram credentials
API_ID = _get_int_env("API_ID", 0)
API_HASH = os.getenv("API_HASH", "")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Multiple anonymous bots (comma-separated string converted to list)
import logging
_config_logger = logging.getLogger(__name__)
_raw = os.getenv("ANON_BOT_USERNAMES", "")
ANON_BOT_USERNAMES = [u.strip() for u in _raw.split(",") if u.strip()]

if not ANON_BOT_USERNAMES:
    _config_logger.warning("⚠️  ANON_BOT_USERNAMES not configured — bot will ignore all messages")

# Timing delays (in seconds)
TYPING_DELAY_MIN = _get_float_env("TYPING_DELAY_MIN", 1.0)
TYPING_DELAY_MAX = _get_float_env("TYPING_DELAY_MAX", 3.0)
BUBBLE_DELAY_MIN = _get_float_env("BUBBLE_DELAY_MIN", 0.5)
BUBBLE_DELAY_MAX = _get_float_env("BUBBLE_DELAY_MAX", 1.0)
GENDER_ASK_DELAY = _get_float_env("GENDER_ASK_DELAY", 2.0)

# History management
MAX_HISTORY = _get_int_env("MAX_HISTORY", 20)

# Rate limiting (to avoid hitting Gemini API quotas)
# Delay before sending Gemini request after receiving message
GEMINI_REQUEST_DELAY_MIN = _get_float_env("GEMINI_REQUEST_DELAY_MIN", 0.5)
GEMINI_REQUEST_DELAY_MAX = _get_float_env("GEMINI_REQUEST_DELAY_MAX", 1.5)
# Min delay between consecutive Gemini requests (even if messages come fast)
GEMINI_MIN_REQUEST_INTERVAL = _get_float_env("GEMINI_MIN_REQUEST_INTERVAL", 3.0)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
