from pyrogram import Client, filters
from pyrogram.enums import ChatAction
import asyncio
import random
import logging
import signal
import sys
from datetime import datetime, timezone, timedelta

from config import (
    API_ID, API_HASH, ANON_BOT_USERNAME,
    TYPING_DELAY_MIN, TYPING_DELAY_MAX,
    BUBBLE_DELAY_MIN, BUBBLE_DELAY_MAX,
    GENDER_ASK_DELAY, LOG_LEVEL, LOG_FORMAT
)
from chat_session import ChatSession, State
from gemini_client import generate_reply

# Setup logging (prevent duplicate handlers)
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=getattr(logging, LOG_LEVEL, logging.INFO), format=LOG_FORMAT)
    logger = logging.getLogger(__name__)

# Initialize Pyrogram client
app = Client("autochatreply", api_id=API_ID, api_hash=API_HASH)

# Global session manager
session = ChatSession()


def set_state(new_state: State, reason: str):
    """Centralized state transition with consistent logs."""
    old_state = session.state
    session.state = new_state
    logger.info("State transition: %s -> %s | %s", old_state.value, new_state.value, reason)


def set_state_from(old_state: State, new_state: State, reason: str):
    """State transition logger when state changed outside set_state (e.g. reset)."""
    session.state = new_state
    logger.info("State transition: %s -> %s | %s", old_state.value, new_state.value, reason)


def get_wib_time() -> str:
    """Get current time in WIB (UTC+7) format HH:MM"""
    wib = timezone(timedelta(hours=7))
    now = datetime.now(wib)
    return now.strftime("%H:%M")


async def send_with_delay(
    client: Client,
    chat_id: int,
    text: str,
    delay_min: float = TYPING_DELAY_MIN,
    delay_max: float = TYPING_DELAY_MAX
):
    """
    Send message with typing simulation and random delay.

    Args:
        client: Pyrogram client
        chat_id: Chat ID to send to
        text: Message text
        delay_min: Minimum delay in seconds
        delay_max: Maximum delay in seconds
    """
    try:
        await client.send_chat_action(chat_id, ChatAction.TYPING)
        await asyncio.sleep(random.uniform(delay_min, delay_max))
        await client.send_message(chat_id, text)
        logger.debug("Sent message: %s", text[:80])
    except Exception as e:
        logger.error(f"Failed to send message: {e}")


async def send_bubbles(client: Client, chat_id: int, bubbles: list):
    """
    Send multiple message bubbles with delays between them.

    Args:
        client: Pyrogram client
        chat_id: Chat ID to send to
        bubbles: List of strings, each is one bubble message
    """
    for idx, bubble in enumerate(bubbles, 1):
        logger.debug("Sending bubble %s/%s", idx, len(bubbles))
        await send_with_delay(
            client, chat_id, bubble,
            delay_min=BUBBLE_DELAY_MIN,
            delay_max=BUBBLE_DELAY_MAX
        )


def detect_gender(text: str) -> str | None:
    """
    Detect gender from user response (fuzzy matching).

    Args:
        text: User message

    Returns:
        "female", "male", or None if unclear
    """
    t = text.strip().lower()

    female_keywords = [
        "f", "ce", "cewe", "cewek", "female",
        "pr", "perempuan", "w", "wanita", "girl"
    ]
    male_keywords = [
        "m", "co", "cowo", "cowok", "male",
        "lk", "laki", "pria", "boy", "man"
    ]

    if t in female_keywords:
        return "female"
    if t in male_keywords:
        return "male"

    return None


def is_disconnect_message(text: str) -> bool:
    """
    Check if message indicates chat disconnection.

    Args:
        text: Message text

    Returns:
        True if disconnect detected, False otherwise
    """
    disconnect_keywords = [
        "has disconnected",
        "telah berakhir",
        "partner has left",
        "stranger disconnected",
        "obrolan berakhir",
        "disconnected"
    ]

    text_lower = text.lower()
    return any(kw in text_lower for kw in disconnect_keywords)


def is_welcome_message(text: str) -> bool:
    """
    Check if message is the welcome message from anon bot.

    Args:
        text: Message text

    Returns:
        True if welcome message detected, False otherwise
    """
    return "/search" in text and "/next" in text


@app.on_message(filters.user(ANON_BOT_USERNAME) & filters.text)
async def handle_message(client: Client, message):
    """
    Main message handler for anonymous chat bot.
    Implements state machine for bot workflow.
    """
    global session

    text = message.text
    chat_id = message.chat.id

    logger.debug("[%s] Received: %s", session.state.value, text[:80])

    # STATE: IDLE -> WAITING_MATCH
    if session.state == State.IDLE:
        logger.debug("State is IDLE, skipping message")
        return

    # STATE: WAITING_MATCH
    if session.state == State.WAITING_MATCH:
        if is_welcome_message(text):
            logger.info("Welcome message detected → sending hii")
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "hii")

            await asyncio.sleep(random.uniform(GENDER_ASK_DELAY, GENDER_ASK_DELAY + 1))
            await client.send_message(chat_id, "m f?")

            set_state(State.WAITING_GENDER, "welcome detected and gender prompt sent")
        else:
            logger.debug("Still waiting for welcome/match confirmation")
        return

    # STATE: WAITING_GENDER
    if session.state == State.WAITING_GENDER:
        gender = detect_gender(text)

        if gender == "male":
            logger.info("Male detected → skipping, sending /next")
            old_state = session.state
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/next")
            set_state_from(old_state, State.WAITING_MATCH, "male detected, skipping chat")
            return

        elif gender == "female":
            logger.info("Female detected → starting chat")
            set_state(State.CHATTING, "female detected")
            session.add_message("user", text)

            # Generate reply
            bubbles = generate_reply(session.get_history(), get_wib_time())
            if not bubbles:
                logger.warning("Gemini returned empty bubbles, using fallback")
                bubbles = ["..."]
            for bubble in bubbles:
                session.add_message("model", bubble)

            await send_bubbles(client, chat_id, bubbles)
            return

        logger.info("Gender unclear, waiting another response: %s", text[:80])
        return

    # STATE: CHATTING
    if session.state == State.CHATTING:
        # Check for disconnect
        if is_disconnect_message(text):
            logger.info("Disconnect detected → resetting and sending /next")
            old_state = session.state
            session.reset()
            await asyncio.sleep(random.uniform(1, 3))
            await client.send_message(chat_id, "/next")
            set_state_from(old_state, State.WAITING_MATCH, "disconnect detected")
            return

        # Normal chat flow
        session.add_message("user", text)

        # Generate reply
        bubbles = generate_reply(session.get_history(), get_wib_time())
        if not bubbles:
            logger.warning("Gemini returned empty bubbles, using fallback")
            bubbles = ["..."]
        for bubble in bubbles:
            session.add_message("model", bubble)

        await send_bubbles(client, chat_id, bubbles)
        return


async def shutdown_handler(signum, frame):
    """Handle graceful shutdown on signal."""
    logger.info(f"\n✓ Received signal {signum}, shutting down gracefully...")
    sys.exit(0)


async def main():
    """
    Main entry point - start bot and initialize first match search.
    """
    # Setup signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, shutdown_handler)
    signal.signal(signal.SIGTERM, shutdown_handler)

    async with app:
        logger.info("✓ Bot started!")
        logger.info(f"Bot username: @{ANON_BOT_USERNAME}")
        logger.info(f"API ID: {API_ID}")

        try:
            # Get the anonymous chat bot
            anon_chat = await app.get_chat(ANON_BOT_USERNAME)
            logger.info(f"✓ Found anon bot: {anon_chat.first_name or ANON_BOT_USERNAME}")

            # Send initial /next to start searching
            await app.send_message(anon_chat.id, "/next")
            set_state(State.WAITING_MATCH, "initial startup /next sent")
            logger.info("✓ Sent /next → waiting for match...")

            # Keep bot running indefinitely
            await asyncio.Event().wait()

        except Exception as e:
            logger.error(f"❌ Error: {e}")


if __name__ == "__main__":
    logger.info("=" * 50)
    logger.info("AutoReply ChatBot - Starting...")
    logger.info("=" * 50)

    try:
        app.run(main())
    except KeyboardInterrupt:
        logger.info("\n✓ Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}")
