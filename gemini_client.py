from google import genai
from google.genai import types
from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_HISTORY
import logging
import time

logger = logging.getLogger(__name__)

# Load system prompt from persona.txt
try:
    with open("persona.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
    logger.info("✓ Persona loaded from persona.txt")
except FileNotFoundError:
    logger.error("❌ persona.txt not found!")
    SYSTEM_PROMPT = ""

# Initialize Gemini client (uses HTTP, no gRPC)
# Note: google-genai SDK handles timeouts internally; long-running requests
# are retried automatically by the SDK's built-in retry mechanism
client = genai.Client(api_key=GEMINI_API_KEY)


def warm_up_persona() -> bool:
    """
    Ask Gemini to read and confirm understanding of persona before starting.
    Returns True if Gemini confirms, False if failed.
    """
    if not SYSTEM_PROMPT:
        logger.error("❌ Cannot warm up: persona.txt is empty")
        return False

    try:
        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=[types.Content(
                role="user",
                parts=[types.Part(text=(
                    "Baca semua instruksi yang ada di system prompt kamu. "
                    "Kalau sudah paham, konfirmasi dengan menyebutkan: "
                    "1) kamu siapa, 2) angkatan dan asal kota kamu, "
                    "3) gaya chat kamu seperti apa, 4) aturan keras yang harus kamu ikuti. "
                    "Jawab dalam 4-5 kalimat singkat."
                ))]
            )],
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
            ),
        )
        summary = response.text.strip()
        logger.info("✅ Gemini persona confirmed:")
        for line in summary.split("\n"):
            if line.strip():
                logger.info("   %s", line.strip())
        return True

    except Exception as e:
        logger.error("❌ Gemini warm-up failed: %s", e)
        return False


def generate_reply(history: list, current_time: str) -> list[str]:
    """
    Generate a reply using Gemini API with HVM persona.

    Args:
        history: List of dicts with {"role": "user"/"model", "content": "..."}
        current_time: Current time in "HH:MM" format (24-hour, WIB)

    Returns:
        List of strings (each string is one chat bubble)
    """
    try:
        # Limit history to MAX_HISTORY messages
        if len(history) > MAX_HISTORY:
            history = history[-MAX_HISTORY:]

        # Convert to Gemini SDK format
        gemini_contents = []
        for item in history:
            role = "user" if item["role"] == "user" else "model"
            gemini_contents.append(
                types.Content(role=role, parts=[types.Part(text=item["content"])])
            )

        # Inject time context into system instruction, not conversation
        system_with_context = f"{SYSTEM_PROMPT}\n\n[CONTEXT: Waktu sekarang {current_time} WIB.]"

        response = client.models.generate_content(
            model=GEMINI_MODEL,
            contents=gemini_contents,
            config=types.GenerateContentConfig(
                system_instruction=system_with_context,
                automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),  # Disable AFC to prevent deadline conflicts
            ),
        )

        reply_text = response.text
        bubbles = [
            line.strip() for line in reply_text.split("\n")
            if line.strip() and not line.strip().startswith("[CONTEXT:")
        ]

        logger.info(f"✓ Generated {len(bubbles)} bubbles from Gemini")
        return bubbles

    except Exception as e:
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            logger.warning("⚠️  Gemini rate limit hit, skipping reply")
            return []
        # Retry once on connection errors (timeout, server disconnect)
        if any(k in err for k in ["disconnected", "timeout", "Server disconnected", "Connection"]):
            logger.warning("⚠️  Gemini connection error, retrying once... (%s)", err[:60])
            try:
                response = client.models.generate_content(
                    model=GEMINI_MODEL,
                    contents=gemini_contents,
                    config=types.GenerateContentConfig(
                        system_instruction=system_with_context,
                        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
                    ),
                )
                bubbles = [
                    line.strip() for line in response.text.split("\n")
                    if line.strip() and not line.strip().startswith("[CONTEXT:")
                ]
                logger.info(f"✓ Retry successful, {len(bubbles)} bubbles")
                return bubbles
            except Exception as e2:
                logger.error(f"❌ Gemini retry failed: {e2}")
                return []
        logger.error(f"❌ Gemini API error: {e}")
        return []


if __name__ == "__main__":
    test_history = [
        {"role": "user", "content": "hii"},
        {"role": "model", "content": "hii"},
        {"role": "user", "content": "lagi ngapain?"}
    ]

    print("\n=== Testing Gemini Client ===")
    replies = generate_reply(test_history, "21:00")
    print("\nGenerated reply bubbles:")
    for i, bubble in enumerate(replies, 1):
        print(f"{i}. {bubble}")
