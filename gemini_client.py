from openai import AsyncOpenAI
from config import GROQ_API_KEY, GROQ_MODEL, MAX_HISTORY
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

# Simple response cache to avoid duplicate API calls
_response_cache = {}
_cache_max_size = 100  # Limit cache size to prevent memory bloat

# Load system prompt from persona.txt and workflow.txt
try:
    with open("persona.txt", "r", encoding="utf-8") as f:
        PERSONA = f.read()
    logger.info("✓ Persona loaded from persona.txt")
except FileNotFoundError:
    logger.error("❌ persona.txt not found!")
    PERSONA = ""

try:
    with open("workflow.txt", "r", encoding="utf-8") as f:
        WORKFLOW = f.read()
    logger.info("✓ Workflow loaded from workflow.txt")
except FileNotFoundError:
    logger.error("❌ workflow.txt not found!")
    WORKFLOW = ""

# Combine persona and workflow as system instruction
SYSTEM_PROMPT = PERSONA + "\n\n---\n\n" + WORKFLOW

# Initialize Groq client (OpenAI-compatible) with built-in retries
client = AsyncOpenAI(api_key=GROQ_API_KEY, base_url="https://api.groq.com/openai/v1", max_retries=2)


async def warm_up_persona() -> bool:
    """
    Ask Gemini to read and confirm understanding of persona before starting.
    Returns True if Gemini confirms, False if failed.
    """
    if not SYSTEM_PROMPT:
        logger.error("❌ Cannot warm up: persona.txt is empty")
        return False

    try:
        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": (
                    "Baca semua instruksi yang ada di system prompt kamu. "
                    "Kalau sudah paham, konfirmasi dengan menyebutkan: "
                    "1) kamu siapa, 2) angkatan dan asal kota kamu, "
                    "3) gaya chat kamu seperti apa, 4) aturan keras yang harus kamu ikuti. "
                    "Jawab dalam 4-5 kalimat singkat."
                )}
            ],
            max_tokens=250,
            temperature=0.7
        )
        summary = response.choices[0].message.content.strip()
        logger.info("✅ Groq persona confirmed:")
        for line in summary.split("\n"):
            if line.strip():
                logger.info("   %s", line.strip())
        return True

    except Exception as e:
        logger.error("❌ Groq warm-up failed: %s", e)
        return False


async def generate_reply(history: list, current_time: str, session_state: str = "CHATTING") -> list[str]:
    """
    Generate a reply using Groq API with HVM persona.

    Args:
        history: List of dicts with {"role": "user"/"model", "content": "..."}
        current_time: Current time in "HH:MM" format (24-hour, WIB)
        session_state: Current session state ("WAITING_MATCH" or "CHATTING") for cache isolation

    Returns:
        List of strings (each string is one chat bubble)
    """
    # CACHE KEY FIX: Disable cache during WAITING_MATCH to prevent cross-conversation pollution
    # During gender detection phase, responses must be unique per conversation, not reused across different chats
    if session_state == "WAITING_MATCH":
        logger.debug("⚠️  Cache disabled during WAITING_MATCH phase (gender detection)")
        cache_key = None
    else:
        # Generate cache key based on last user message + time of day + session state
        # Include session state to further isolate cache entries
        last_user_msg = next((msg["content"] for msg in reversed(history) if msg["role"] == "user"), "")
        hour = current_time.split(":")[0]
        cache_key = hashlib.md5(f"{last_user_msg}|{hour}|{session_state}".encode()).hexdigest()

    # Return cached response if available (and not disabled)
    if cache_key and cache_key in _response_cache:
        logger.info(f"✓ Using cached response for: {last_user_msg[:50]}")
        return _response_cache[cache_key]

    try:
        # Limit history to MAX_HISTORY messages
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        # Convert to OpenAI chat format
        messages = [{"role": "system", "content": f"{SYSTEM_PROMPT}\n\n[CONTEXT: Waktu sekarang {current_time} WIB.]"}]
        for item in history:
            role = "user" if item["role"] == "user" else "assistant"
            messages.append({"role": role, "content": item["content"]})

        response = await client.chat.completions.create(
            model=GROQ_MODEL,
            messages=messages,
            max_tokens=250,
            temperature=0.7
        )

        reply_text = response.choices[0].message.content
        raw_bubbles = [line.strip() for line in reply_text.split("\n") if line.strip()]

        bubbles = []
        for b in raw_bubbles:
            # Lewati indikator waktu
            if b.startswith("[CONTEXT:"):
                continue

            # Kalau bubble bentuknya aneh seperti [Bubbles] atau [Kamu baru saja...], buang!
            # (Kecuali token valid [SKIP] dan [START_CHAT])
            if b.startswith("[") and b.endswith("]") and b not in ["[SKIP]", "[START_CHAT]"]:
                logger.warning(f"⚠️ Memblokir halusinasi AI: {b}")
                continue

            bubbles.append(b)

        # SAFETY CHECK: Detect conflicting control tokens
        has_skip = any(b == "[SKIP]" for b in bubbles)
        has_start_chat = any(b == "[START_CHAT]" for b in bubbles)
        if has_skip and has_start_chat:
            logger.error("❌ CRITICAL: Both [SKIP] and [START_CHAT] tokens in same response! This should never happen.")
            logger.error(f"   Bubbles: {bubbles}")
            logger.error("   → Prioritizing [SKIP], removing [START_CHAT]")
            bubbles = [b for b in bubbles if b != "[START_CHAT]"]

        # Cache the response (only if cache is enabled for this state)
        if cache_key:
            if len(_response_cache) >= _cache_max_size:
                # Remove oldest entry if cache is full (simple FIFO)
                _response_cache.pop(next(iter(_response_cache)))
            _response_cache[cache_key] = bubbles

        logger.info(f"✓ Generated {len(bubbles)} bubbles from Groq")
        return bubbles

    except Exception as e:
        err = str(e).lower()
        if "rate limit" in err or "429" in err:
            logger.warning("⚠️  Groq rate limit hit, skipping reply")
            return []
        logger.error(f"❌ Groq API error: {e}")
        return []


if __name__ == "__main__":
    import asyncio

    test_history = [
        {"role": "user", "content": "hii"},
        {"role": "model", "content": "hii"},
        {"role": "user", "content": "lagi ngapain?"}
    ]

    print("\n=== Testing Groq Client ===")
    replies = asyncio.run(generate_reply(test_history, "21:00"))
    print("\nGenerated reply bubbles:")
    for i, bubble in enumerate(replies, 1):
        print(f"{i}. {bubble}")
