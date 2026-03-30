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
client = genai.Client(api_key=GEMINI_API_KEY)


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
        else:
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
