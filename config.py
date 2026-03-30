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
GEMINI_MODEL = "gemini-2.0-flash"

# Anonymous bot
ANON_BOT_USERNAME = os.getenv("ANON_BOT_USERNAME", "")

# Timing delays (in seconds)
TYPING_DELAY_MIN = _get_float_env("TYPING_DELAY_MIN", 2.0)
TYPING_DELAY_MAX = _get_float_env("TYPING_DELAY_MAX", 8.0)
BUBBLE_DELAY_MIN = _get_float_env("BUBBLE_DELAY_MIN", 0.5)
BUBBLE_DELAY_MAX = _get_float_env("BUBBLE_DELAY_MAX", 1.5)
GENDER_ASK_DELAY = _get_float_env("GENDER_ASK_DELAY", 2.0)

# History management
MAX_HISTORY = _get_int_env("MAX_HISTORY", 20)

# Logging
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()
LOG_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
