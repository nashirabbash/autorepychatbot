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

# Semaphore: max 1 Gemini request at a time (no artificial delay)
_gemini_semaphore = asyncio.Semaphore(1)


async def call_gemini(history: list, current_time: str) -> list:
    """Call Gemini with stranger's latest message as context. One request at a time."""
    async with _gemini_semaphore:
        return generate_reply(history, current_time)


async def _handle_bubbles(client: Client, chat_id: int, bubbles: list):
    """
    Send bubbles to chat. If Gemini returns [SKIP], send /next instead.
    [SKIP] token means Gemini detected male stranger.
    """
    if not bubbles:
        logger.warning("Gemini returned empty, skipping reply")
        return

    skip = any(b.strip() == "[SKIP]" for b in bubbles)
    real_bubbles = [b for b in bubbles if b.strip() != "[SKIP]"]

    # Send real bubbles first
    if real_bubbles:
        for bubble in real_bubbles:
            session.add_message("model", bubble)
        await send_bubbles(client, chat_id, real_bubbles)

    # If [SKIP] detected, send /next
    if skip:
        logger.info("Gemini detected male → sending /next")
        await asyncio.sleep(random.uniform(1, 2))
        await client.send_message(chat_id, "/next")
        old_state = session.state
        session.last_action = "next"
        session.reset()
        set_state_from(old_state, State.WAITING_MATCH, "male detected by Gemini")

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
    Detect gender from user response (fuzzy matching, handles typos/spaces).

    Args:
        text: User message

    Returns:
        "female", "male", or None if unclear
    """
    import re
    t = text.strip().lower()
    # Remove punctuation and extra spaces
    t_clean = re.sub(r'[^\w\s]', '', t).strip()

    female_keywords = [
        "f", "ce", "cewe", "cewek", "female",
        "pr", "perempuan", "w", "wanita", "girl"
    ]
    male_keywords = [
        "m", "co", "cowo", "cowok", "male",
        "lk", "laki", "pria", "boy", "man"
    ]

    # Exact match
    if t_clean in female_keywords:
        return "female"
    if t_clean in male_keywords:
        return "male"

    # Check word boundaries - any word in message matches keyword
    words = t_clean.split()
    for word in words:
        if word in female_keywords:
            return "female"
        if word in male_keywords:
            return "male"

    return None


def is_disconnect_message(text: str) -> bool:
    """
    Check if partner stopped/left the chat.
    When true, bot should send /search to find new partner.
    Based on chat_bot.md: "Lawan bicara telah meninggalkan" or "Your partner has stopped"
    """
    t = text.lower()
    return any(kw in t for kw in [
        "telah meninggalkan percakapan", "partner has stopped",
        "stopped the chat", "obrolan berakhir",
        "ingin mengobrol dengan orang lain",
        "want to chat with someone else"
    ])


def is_greeting(text: str) -> bool:
    """Check if stranger sends a greeting first."""
    t = text.strip().lower()
    greetings = ["hi", "hii", "hiii", "hey", "halo", "hai", "hello", "helo", "haloo"]
    return any(t.startswith(g) for g in greetings)


def is_feedback_prompt(text: str) -> bool:
    """
    Check if message is feedback prompt from bot.
    If appeared after /next → ignore.
    If appeared after partner stop (before /search) → handle with /search.
    """
    t = text.lower()
    return "feedback tentang pasangan" in t or "leave feedback" in t


def is_gender_question(text: str) -> bool:
    """Check if stranger is asking for gender (ceco, co ce, ce co, etc.)"""
    t = text.strip().lower().replace(" ", "").replace("?", "").replace(".", "")
    variants = ["kmu?", "hbu?", "kmu siapa?", "co ce?", "coce?", "ceco?", "ce co?", "m f?", "mf?", "km?", "km", "u?"]
    return t in variants


def is_system_message(text: str) -> bool:
    """
    Check if message is from system (not a real stranger message).
    Based on chat_bot.md specifications.
    """
    t = text.lower()

    # Searching for partner
    if any(kw in t for kw in ["sedang mencari", "looking for a partner"]):
        return True

    # Partner stopped/disconnected
    if any(kw in t for kw in [
        "telah meninggalkan", "stopped the chat", "partner has stopped",
        "obrolan berakhir", "disconnected"
    ]):
        return True

    # You stopped the chat
    if any(kw in t for kw in [
        "anda telah meninggalkan", "you stopped the chat",
        "searching for a new partner"
    ]):
        return True

    # Feedback prompt
    if "feedback tentang pasangan" in t or "leave feedback" in t:
        return True

    return False


def is_welcome_message(text: str) -> bool:
    """
    Check if message indicates a successful match (partner found).
    Based on chat_bot.md: "Pasangan telah ditemukan!" or "Partner found"
    """
    t = text.lower()
    return ("pasangan telah ditemukan" in t or "partner found" in t) and \
           ("/next" in t or "/search" in t)


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

    # STATE: IDLE → ignore
    if session.state == State.IDLE:
        return

    # Log semua pesan lawan bicara
    logger.info("[%s] Stranger: %s", session.state.value, text[:120])

    # STATE: WAITING_MATCH — only pass real stranger messages to Gemini
    if session.state == State.WAITING_MATCH:
        if is_system_message(text) or is_feedback_prompt(text):
            logger.debug("System/feedback message, ignoring")
            return

        if is_disconnect_message(text):
            logger.info("Disconnect in WAITING_MATCH → /search")
            old_state = session.state
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/search")
            set_state_from(old_state, State.WAITING_MATCH, "disconnect in waiting_match")
            return

        # Welcome message or any real stranger message → hand off to Gemini
        logger.info("Match/stranger detected → passing to Gemini")
        set_state(State.CHATTING, "stranger message received")
        session.add_message("user", text)
        bubbles = await call_gemini(session.get_history(), get_wib_time())
        await _handle_bubbles(client, chat_id, bubbles)
        return

    # STATE: CHATTING — Gemini handles everything including gender detection
    if session.state == State.CHATTING:
        if is_system_message(text) or is_feedback_prompt(text):
            logger.debug("System/feedback message, ignoring")
            return

        if is_disconnect_message(text):
            logger.info("Partner stopped → /search")
            old_state = session.state
            session.last_action = "search"
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/search")
            set_state_from(old_state, State.WAITING_MATCH, "partner disconnected")
            return

        session.add_message("user", text)
        bubbles = await call_gemini(session.get_history(), get_wib_time())
        await _handle_bubbles(client, chat_id, bubbles)
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

        # Warm up Gemini — read and confirm persona before starting
        logger.info("⏳ Loading persona to Gemini...")
        from gemini_client import warm_up_persona, generate_reply as _generate_reply
        global generate_reply
        generate_reply = _generate_reply

        ok = await asyncio.get_event_loop().run_in_executor(None, warm_up_persona)
        if not ok:
            logger.warning("⚠️  Gemini warm-up failed, continuing anyway...")
        else:
            logger.info("✅ Gemini siap — persona dipahami, mulai otomasi Telegram...")

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
