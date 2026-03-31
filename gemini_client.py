from openai import AsyncOpenAI
from config import GROQ_API_KEY, GROQ_MODEL, MAX_HISTORY
import logging
import time
import hashlib

logger = logging.getLogger(__name__)

# Chatbot settings

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


async def generate_reply(history: list, current_time: str) -> list[str]:
    """
    Generate a reply using Groq API with HVM persona.

    Args:
        history: List of dicts with {"role": "user"/"model", "content": "..."}
        current_time: Current time in "HH:MM" format (24-hour, WIB)

    Returns:
        List of strings (each string is one chat bubble)
    """
    # CACHE DISABLED: 
    # Respond dynamic based on conversation history (fixing Issue #22)
    cache_key = None

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

            b_lower = b.lower()
            # Blokir format kurung penuh (seperti [Format Pesan], [Bubbles], atau teks sistem)
            if b.startswith("[") and b.endswith("]") and b_lower not in ["[skip]", "[start_chat]"]:
                logger.warning(f"⚠️ Memblokir halusinasi AI (kurung): {b}")
                continue

            # Blokir secara hardcoded jika mengandung kata kunci halusinasi yang persis
            if "[bubbles]" in b_lower or "[format pesan]" in b_lower or "menemukan pasangan" in b_lower or "pasangan telah ditemukan" in b_lower:
                logger.warning(f"⚠️ Memblokir halusinasi AI spesifik: {b}")
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

        # logger.debug("Cache is now disabled (Issue #22)")

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
