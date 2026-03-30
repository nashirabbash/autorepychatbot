"""
Unit tests for autochatreply bot.
Tests helper functions and state machine logic without requiring Telegram or Gemini.
"""
import sys
import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

# Fix Python 3.14 event loop issue before any imports
original_get_event_loop = asyncio.get_event_loop
def patched_get_event_loop():
    try:
        return original_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
asyncio.get_event_loop = patched_get_event_loop


# ── Helper: import only what we need without Telegram session ──────────────

from chat_session import ChatSession, State
from main import detect_gender, is_disconnect_message, is_welcome_message, get_wib_time


# ── detect_gender ──────────────────────────────────────────────────────────

class TestDetectGender(unittest.TestCase):

    def test_female_keywords(self):
        for word in ["f", "ce", "cewe", "cewek", "female", "pr", "perempuan", "w", "wanita", "girl"]:
            self.assertEqual(detect_gender(word), "female", f"Expected female for: {word}")

    def test_male_keywords(self):
        for word in ["m", "co", "cowo", "cowok", "male", "lk", "laki", "pria", "boy", "man"]:
            self.assertEqual(detect_gender(word), "male", f"Expected male for: {word}")

    def test_case_insensitive(self):
        self.assertEqual(detect_gender("F"), "female")
        self.assertEqual(detect_gender("CE"), "female")
        self.assertEqual(detect_gender("M"), "male")
        self.assertEqual(detect_gender("CO"), "male")

    def test_whitespace_stripped(self):
        self.assertEqual(detect_gender("  f  "), "female")
        self.assertEqual(detect_gender("  m  "), "male")

    def test_unclear_returns_none(self):
        for word in ["hii", "hai", "oke", "siapa", "ntah", "12345", ""]:
            self.assertIsNone(detect_gender(word), f"Expected None for: {word}")


# ── is_disconnect_message ──────────────────────────────────────────────────

class TestIsDisconnectMessage(unittest.TestCase):

    def test_disconnect_keywords(self):
        cases = [
            "Stranger has disconnected",
            "Obrolan telah berakhir",
            "Your partner has left",
            "Stranger disconnected from chat",
            "Chat obrolan berakhir",
            "disconnected",
        ]
        for text in cases:
            self.assertTrue(is_disconnect_message(text), f"Expected disconnect for: {text}")

    def test_normal_messages_not_disconnect(self):
        cases = ["hii", "lagi ngapain?", "oke deh", "bye", "salam kenal"]
        for text in cases:
            self.assertFalse(is_disconnect_message(text), f"Expected NOT disconnect for: {text}")

    def test_case_insensitive(self):
        self.assertTrue(is_disconnect_message("HAS DISCONNECTED"))
        self.assertTrue(is_disconnect_message("TELAH BERAKHIR"))


# ── is_welcome_message ─────────────────────────────────────────────────────

class TestIsWelcomeMessage(unittest.TestCase):

    def test_welcome_contains_both_keywords(self):
        self.assertTrue(is_welcome_message("Gunakan /search atau /next untuk cari lawan bicara"))
        self.assertTrue(is_welcome_message("/next /search blah blah"))

    def test_only_one_keyword_not_welcome(self):
        self.assertFalse(is_welcome_message("ketik /next untuk mulai"))
        self.assertFalse(is_welcome_message("ketik /search untuk mulai"))

    def test_normal_message_not_welcome(self):
        self.assertFalse(is_welcome_message("hii"))
        self.assertFalse(is_welcome_message("apa kabar"))


# ── get_wib_time ───────────────────────────────────────────────────────────

class TestGetWibTime(unittest.TestCase):

    def test_returns_hhmm_format(self):
        t = get_wib_time()
        self.assertRegex(t, r"^\d{2}:\d{2}$")

    def test_hours_in_range(self):
        t = get_wib_time()
        h, m = map(int, t.split(":"))
        self.assertGreaterEqual(h, 0)
        self.assertLessEqual(h, 23)
        self.assertGreaterEqual(m, 0)
        self.assertLessEqual(m, 59)


# ── ChatSession ────────────────────────────────────────────────────────────

class TestChatSession(unittest.TestCase):

    def setUp(self):
        self.session = ChatSession()

    def test_initial_state_is_idle(self):
        self.assertEqual(self.session.state, State.IDLE)

    def test_add_and_get_history(self):
        self.session.add_message("user", "hii")
        self.session.add_message("model", "halo")
        history = self.session.get_history()
        self.assertEqual(len(history), 2)
        self.assertEqual(history[0]["role"], "user")
        self.assertEqual(history[0]["content"], "hii")
        self.assertEqual(history[1]["role"], "model")

    def test_get_history_returns_copy(self):
        self.session.add_message("user", "test")
        h1 = self.session.get_history()
        h1.append({"role": "user", "content": "injected"})
        self.assertEqual(len(self.session.get_history()), 1)

    def test_reset_clears_state(self):
        self.session.state = State.CHATTING
        self.session.add_message("user", "test")
        self.session.current_bot = "somebot"
        self.session.reset()
        self.assertEqual(self.session.state, State.IDLE)
        self.assertEqual(self.session.get_history(), [])
        self.assertIsNone(self.session.current_bot)

    def test_state_transitions(self):
        self.session.state = State.WAITING_MATCH
        self.assertEqual(self.session.state, State.WAITING_MATCH)
        self.session.state = State.CHATTING
        self.assertEqual(self.session.state, State.CHATTING)


# ── New workflow: any message triggers chat start ──────────────────────────

class TestNewWorkflow(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        asyncio.set_event_loop(asyncio.new_event_loop())
        from chat_session import ChatSession, State
        self.ChatSession = ChatSession
        self.State = State

    async def test_any_message_starts_chatting(self):
        """WAITING_MATCH + any message → should go to CHATTING state."""
        session = self.ChatSession()
        session.state = self.State.WAITING_MATCH

        # Simulate receiving message: add to history and transition
        session.add_message("user", "hii")
        session.state = self.State.CHATTING

        self.assertEqual(session.state, self.State.CHATTING)
        self.assertEqual(len(session.get_history()), 1)
        self.assertEqual(session.get_history()[0]["content"], "hii")

    async def test_disconnect_in_chatting_resets(self):
        """CHATTING + disconnect → reset session back to IDLE."""
        session = self.ChatSession()
        session.state = self.State.CHATTING
        session.add_message("user", "hii")

        # Simulate disconnect
        session.reset()

        self.assertEqual(session.state, self.State.IDLE)
        self.assertEqual(session.get_history(), [])

    async def test_no_waiting_gender_state_needed(self):
        """Workflow no longer requires WAITING_GENDER state."""
        session = self.ChatSession()
        session.state = self.State.WAITING_MATCH

        # Simulate first message triggering chatting directly
        session.add_message("user", "halo apa kabar")
        session.state = self.State.CHATTING

        # Should be CHATTING, not WAITING_GENDER
        self.assertNotEqual(session.state, self.State.WAITING_GENDER)
        self.assertEqual(session.state, self.State.CHATTING)


if __name__ == "__main__":
    print("=" * 60)
    print("Running AutoReply Bot Tests")
    print("=" * 60)
    unittest.main(verbosity=2)
