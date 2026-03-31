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
import time
from datetime import datetime, timezone, timedelta

from pyrogram import Client, filters
from pyrogram.enums import ChatAction

from config import (
    API_ID, API_HASH, ANON_BOT_USERNAMES,
    TYPING_DELAY_MIN, TYPING_DELAY_MAX,
    BUBBLE_DELAY_MIN, BUBBLE_DELAY_MAX,
    GEMINI_REQUEST_DELAY_MIN, GEMINI_REQUEST_DELAY_MAX,
    GEMINI_MIN_REQUEST_INTERVAL,
    CHAT_POLLING_INTERVAL, MAX_BUBBLES_PER_REPLY,
    LOG_LEVEL, LOG_FORMAT
)
from chat_session import ChatSession, State

# Lazy import for gemini_client (avoid gRPC import issues)
generate_reply = None

# Semaphore: max 1 Gemini request at a time (no artificial delay)
_gemini_semaphore = asyncio.Semaphore(1)


async def call_gemini(history: list, current_time: str, session_state: str = "CHATTING") -> list:
    """Call Gemini with stranger's latest message as context. One request at a time."""
    async with _gemini_semaphore:
        # Rate limiting: ensure minimum interval between Gemini requests
        now = time.time()
        time_since_last = now - session.last_gemini_request_time
        if time_since_last < GEMINI_MIN_REQUEST_INTERVAL:
            wait_time = GEMINI_MIN_REQUEST_INTERVAL - time_since_last
            logger.debug(f"⏱️  Rate limiting: waiting {wait_time:.1f}s before next Gemini request")
            await asyncio.sleep(wait_time)

        # Add random delay before request to avoid thundering herd
        await asyncio.sleep(random.uniform(GEMINI_REQUEST_DELAY_MIN, GEMINI_REQUEST_DELAY_MAX))

        session.last_gemini_request_time = time.time()
        return generate_reply(history, current_time, session_state)


async def _handle_bubbles(client: Client, chat_id: int, bubbles: list):
    """
    Send bubbles to chat. If Gemini returns [SKIP], send /next instead.
    [SKIP] token means Gemini detected male stranger.
    Limit bubbles to MAX_BUBBLES_PER_REPLY to keep responses short.
    """
    if not bubbles:
        logger.warning("Gemini returned empty, skipping reply")
        return

    # Limit bubbles to max allowed per reply
    bubbles = bubbles[:MAX_BUBBLES_PER_REPLY]

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


def is_feedback_prompt(text: str) -> bool:
    """
    Check if message is feedback prompt from bot.
    If appeared after /next → ignore.
    If appeared after partner stop (before /search) → handle with /search.
    """
    t = text.lower()
    return "feedback tentang pasangan" in t or "leave feedback" in t


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

    # STATE: WAITING_MATCH — AI handles greeting and gender detection via Gemini, no pooling
    if session.state == State.WAITING_MATCH:
        # Check disconnect FIRST before other system message checks
        if is_disconnect_message(text):
            logger.info("Disconnect in WAITING_MATCH → /search")
            old_state = session.state
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/search")
            set_state_from(old_state, State.WAITING_MATCH, "disconnect in waiting_match")
            return

        if is_system_message(text) or is_feedback_prompt(text):
            logger.debug("System/feedback message, ignoring")
            return

        # All messages in WAITING_MATCH → pass to Gemini (no pooling, instant response)
        # This includes welcome message, greeting responses, and gender answers
        session.add_message("user", text)
        bubbles = await call_gemini(session.get_history(), get_wib_time(), "WAITING_MATCH")

        # Parse control tokens
        skip = any(b.strip() == "[SKIP]" for b in bubbles)
        start_chat = any(b.strip() == "[START_CHAT]" for b in bubbles)
        real_bubbles = [b for b in bubbles if b.strip() not in ("[SKIP]", "[START_CHAT]")]

        if skip:
            logger.info("♂️  Male detected by AI → sending /next")
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/next")
            old_state = session.state
            session.last_action = "next"
            session.reset()
            set_state_from(old_state, State.WAITING_MATCH, "male detected by AI")
            return

        if real_bubbles:
            logger.info(f"↳ Sending {len(real_bubbles)} bubbles from Gemini")
            for bubble in real_bubbles:
                session.add_message("model", bubble)
            await send_bubbles(client, chat_id, real_bubbles)

        if start_chat:
            logger.info("♀️  Female confirmed by AI → activating pooling and transitioning to CHATTING")
            set_state(State.CHATTING, "gender confirmed by AI, pooling activated")
            session.last_message_batch_time = time.time()
            session.pending_messages = []
            logger.info(f"✓ Pooling activated. Will batch messages for {CHAT_POLLING_INTERVAL}s")
            return

    # STATE: CHATTING — Buffer messages and process in batches every CHAT_POLLING_INTERVAL
    if session.state == State.CHATTING:
        # Check disconnect FIRST before other system message checks
        if is_disconnect_message(text):
            logger.info("Partner stopped → /search")
            old_state = session.state
            session.last_action = "search"
            session.reset()
            await asyncio.sleep(random.uniform(1, 2))
            await client.send_message(chat_id, "/search")
            set_state_from(old_state, State.WAITING_MATCH, "partner disconnected")
            return

        if is_system_message(text) or is_feedback_prompt(text):
            logger.debug("System/feedback message, ignoring")
            return

        # Buffer this message and add to pending
        session.pending_messages.append(text)
        logger.debug(f"Buffered message ({len(session.pending_messages)} pending): {text[:60]}")

        # Check if enough time has passed since last batch
        now = time.time()
        time_since_last_batch = now - session.last_message_batch_time

        if time_since_last_batch >= CHAT_POLLING_INTERVAL:
            # Process all pending messages as one batch
            if session.pending_messages:
                logger.info(f"⏱️  Processing {len(session.pending_messages)} buffered messages from stranger")
                # Combine all pending messages into conversation history
                for pending_text in session.pending_messages:
                    session.add_message("user", pending_text)
                session.pending_messages = []

                # Send to Gemini once with all messages
                bubbles = await call_gemini(session.get_history(), get_wib_time())
                await _handle_bubbles(client, chat_id, bubbles)
                session.last_message_batch_time = now
        else:
            wait_time = CHAT_POLLING_INTERVAL - time_since_last_batch
            logger.debug(f"⏳ Next batch in {wait_time:.0f}s ({len(session.pending_messages)} messages buffered)")

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
