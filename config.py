import os
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

# Telegram credentials
API_ID = int(os.getenv("API_ID", 0))
API_HASH = os.getenv("API_HASH", "")

# Gemini API
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"

# Anonymous bot
ANON_BOT_USERNAME = os.getenv("ANON_BOT_USERNAME", "")

# Timing delays (in seconds)
TYPING_DELAY_MIN = 2.0
TYPING_DELAY_MAX = 8.0
BUBBLE_DELAY_MIN = 0.5
BUBBLE_DELAY_MAX = 1.5
GENDER_ASK_DELAY = 2.0

# History management
MAX_HISTORY = 20
