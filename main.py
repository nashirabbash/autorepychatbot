import sys
import asyncio

# CRITICAL: Fix Python 3.14 + Pyrogram compatibility
# Pyrogram calls asyncio.get_event_loop() at module import time
# This fails in Python 3.14 if no event loop exists in the thread
original_get_event_loop = asyncio.get_event_loop
def patched_get_event_loop():
    try:
        return original_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
asyncio.get_event_loop = patched_get_event_loop

import random
import logging
import signal
from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatAction

from config import (
    API_ID, API_HASH, ANON_BOT_USERNAMES,
    TYPING_DELAY_MIN, TYPING_DELAY_MAX,
    BUBBLE_DELAY_MIN, BUBBLE_DELAY_MAX,
    LOG_LEVEL, LOG_FORMAT
)
from chat_session import ChatSession, State

# Lazy import for gemini_client (avoid gRPC import issues)
generate_reply = None

# Rate limiter: max 1 Gemini request at a time, min 4s between requests
_gemini_semaphore = asyncio.Semaphore(1)
_gemini_last_call = 0.0
_GEMINI_MIN_INTERVAL = 2.0  # seconds between requests


async def call_gemini(history: list, current_time: str) -> list:
    """Wrapper around generate_reply with rate limiting."""
    global _gemini_last_call
    async with _gemini_semaphore:
        now = asyncio.get_event_loop().time()
        wait = _GEMINI_MIN_INTERVAL - (now - _gemini_last_call)
        if wait > 0:
            await asyncio.sleep(wait)
        result = generate_reply(history, current_time)
        _gemini_last_call = asyncio.get_event_loop().time()
        return result

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


@app.on_message(filters.text)
async def handle_message(client: Client, message):
    """
    Main message handler for anonymous chat bot.
    Implements state machine for bot workflow.
    Supports multiple anonymous chat bots.
    """
    global session, generate_reply

    # Lazy import to avoid gRPC issues during module loading
    if generate_reply is None:
        from gemini_client import generate_reply as _generate_reply
        generate_reply = _generate_reply

    # Check if message is from one of the allowed anon bots
    sender = message.from_user.username if message.from_user else None
    if not ANON_BOT_USERNAMES or sender not in ANON_BOT_USERNAMES:
        return

    # Track which bot this conversation is with
    session.current_bot = sender

    text = message.text
    chat_id = message.chat.id

    logger.debug("[%s] Received from @%s: %s", session.state.value, sender, text[:80])

    # STATE: IDLE -> WAITING_MATCH
    if session.state == State.IDLE:
        logger.debug("State is IDLE, skipping message")
        return

    # STATE: WAITING_MATCH → match detected, ask gender
    if session.state == State.WAITING_MATCH:
        if not is_welcome_message(text):
            logger.debug("Not a welcome message yet, ignoring")
            return

        logger.info("Match found → asking gender")
        await asyncio.sleep(random.uniform(1, 2))
        await client.send_message(chat_id, "co ce?")
        set_state(State.WAITING_GENDER, "match detected, gender prompt sent")
        return

    # STATE: WAITING_GENDER → route based on gender
    if session.state == State.WAITING_GENDER:
        gender = detect_gender(text)

        if gender == "male":
            logger.info("Male → skipping, sending /next")
            old_state = session.state
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/next")
            set_state_from(old_state, State.WAITING_MATCH, "male detected")
            return

        if gender == "female":
            logger.info("Female → starting chat")
            set_state(State.CHATTING, "female confirmed")
            bubbles = await call_gemini(session.get_history(), get_wib_time())
            if bubbles:
                for bubble in bubbles:
                    session.add_message("model", bubble)
                await send_bubbles(client, chat_id, bubbles)
            return

        # Gender unclear → keep waiting
        logger.debug("Gender unclear: %s", text)
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

        bubbles = await call_gemini(session.get_history(), get_wib_time())
        if bubbles:
            for bubble in bubbles:
                session.add_message("model", bubble)
            await send_bubbles(client, chat_id, bubbles)
        else:
            logger.warning("Gemini returned empty, skipping reply")
        return


def shutdown_handler(signum, frame):
    """Handle graceful shutdown on signal."""
    logger.info(f"\n✓ Received signal {signum}, shutting down gracefully...")
    raise KeyboardInterrupt()


async def main():
    """
    Main entry point - start bot and initialize first match search.
    """
    loop = asyncio.get_event_loop()

    # Setup signal handlers for graceful shutdown
    def handle_signal(signum):
        logger.info(f"\n✓ Received signal {signum}, shutting down gracefully...")
        loop.stop()

    loop.add_signal_handler(signal.SIGINT, handle_signal, signal.SIGINT)
    loop.add_signal_handler(signal.SIGTERM, handle_signal, signal.SIGTERM)

    async with app:
        logger.info("✓ Bot started!")
        logger.info(f"Connected bots: {', '.join(f'@{b}' for b in ANON_BOT_USERNAMES)}")
        logger.info(f"API ID: {API_ID}")

        try:
            # Send initial /next to all anonymous chat bots to start searching
            for idx, bot_username in enumerate(ANON_BOT_USERNAMES, 1):
                try:
                    # Add delay between sending /next to different bots
                    if idx > 1:
                        await asyncio.sleep(random.uniform(1, 2))

                    anon_chat = await app.get_chat(bot_username)
                    await app.send_message(anon_chat.id, "/next")
                    logger.info(f"✓ Sent /next to @{bot_username}")
                except Exception as e:
                    logger.warning(f"Failed to send /next to @{bot_username}: {e}")

            set_state(State.WAITING_MATCH, "initial startup /next sent to all bots")
            logger.info("✓ Initialized with all bots → waiting for matches...")

            # Keep bot running indefinitely
            try:
                await asyncio.Event().wait()
            except asyncio.CancelledError:
                logger.info("✓ Bot stopped by user")
                raise

        except KeyboardInterrupt:
            logger.info("✓ Bot stopped by user")
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
