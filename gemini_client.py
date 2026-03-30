import google.generativeai as genai
from config import GEMINI_API_KEY, GEMINI_MODEL, MAX_HISTORY
import logging

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load system prompt from persona.txt
try:
    with open("persona.txt", "r", encoding="utf-8") as f:
        SYSTEM_PROMPT = f.read()
    logger.info("✓ Persona loaded from persona.txt")
except FileNotFoundError:
    logger.error("❌ persona.txt not found!")
    SYSTEM_PROMPT = ""

# Configure Gemini API
genai.configure(api_key=GEMINI_API_KEY)


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

        # Add time context to the last user message
        if history and history[-1]["role"] == "user":
            history_with_context = history.copy()
            last_msg = history_with_context[-1]
            last_msg["content"] = f"{last_msg['content']}\n\n[CONTEXT: Waktu sekarang {current_time} WIB.]"
        else:
            history_with_context = history

        # Convert to Gemini format
        gemini_history = []
        for item in history_with_context:
            gemini_history.append({
                "role": item["role"],
                "parts": [{"text": item["content"]}]
            })

        # Create model and start chat
        model = genai.GenerativeModel(
            model_name=GEMINI_MODEL,
            system_instruction=SYSTEM_PROMPT
        )

        chat = model.start_chat(history=gemini_history[:-1] if gemini_history else [])

        # Send the last message
        last_message = gemini_history[-1]["parts"][0]["text"] if gemini_history else "hii"
        response = chat.send_message(last_message)

        # Parse response into chat bubbles
        reply_text = response.text
        bubbles = [line.strip() for line in reply_text.split("\n") if line.strip()]

        logger.info(f"✓ Generated {len(bubbles)} bubbles from Gemini")
        return bubbles

    except Exception as e:
        logger.error(f"❌ Gemini API error: {e}")
        return ["..."]


if __name__ == "__main__":
    # Test
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
