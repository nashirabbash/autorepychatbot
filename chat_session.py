from enum import Enum
from config import MAX_HISTORY
import logging
import time

logger = logging.getLogger(__name__)


class State(Enum):
    """Enum untuk state/kondisi bot saat ini"""
    IDLE = "idle"                       # Bot belum mulai apa-apa
    WAITING_MATCH = "waiting_match"     # Bot sudah kirim /next, menunggu match
    WAITING_GENDER = "waiting_gender"   # Bot sudah kirim "hii" dan "m f?", menunggu jawaban
    CHATTING = "chatting"               # Lawan chat sudah konfirmasi perempuan, sedang ngobrol


class ChatSession:
    """Manajer untuk session chat — menyimpan state dan history percakapan"""

    def __init__(self):
        """Inisialisasi session baru"""
        self.state = State.IDLE
        self.history = []
        self.current_bot = None  # Username bot anon yang sedang aktif
        self.last_action = None  # Track last action: "next" atau "search"
        self.last_gemini_request_time = 0  # Track time of last Gemini API call for rate limiting
        self.last_message_batch_time = 0  # Track when we last pulled messages for Gemini
        self.pending_messages = []  # Buffer for messages waiting to be batched
        logger.info("✓ New ChatSession created")

    def add_message(self, role: str, content: str):
        """
        Tambahkan pesan ke history

        Args:
            role: "user" untuk pesan dari lawan chat, "model" untuk pesan dari bot
            content: Isi teks pesan
        """
        message = {"role": role, "content": content, "timestamp": time.time()}
        self.history.append(message)
        logger.debug(f"Added {role} message: {str(content)[:50]}...")

    def get_history(self) -> list:
        """
        Ambil history percakapan (dibatasi MAX_HISTORY pesan terakhir)

        Returns:
            List of dicts dengan struktur {"role": "...", "content": "...", "timestamp": ...}
        """
        return self.history[-MAX_HISTORY:].copy()

    def reset(self):
        """Reset session — clear history dan kembalikan state ke IDLE"""
        self.history = []
        self.state = State.IDLE
        self.current_bot = None
        self.last_gemini_request_time = 0
        self.last_message_batch_time = 0
        self.pending_messages = []
        logger.info("✓ ChatSession reset")


if __name__ == "__main__":
    # Test block
    print("\n=== Testing ChatSession ===\n")

    session = ChatSession()

    # Test 1: Check initial state
    print(f"Test 1 - State awal: {session.state}")
    assert session.state == State.IDLE, "State harus IDLE"
    print("✓ Pass\n")

    # Test 2: Change state and add messages
    print("Test 2 - Ubah state dan tambah pesan:")
    session.state = State.CHATTING
    session.add_message("user", "hii")
    session.add_message("model", "hii balik")
    session.add_message("user", "lagi ngapain?")

    print(f"State sekarang: {session.state}")
    print(f"Jumlah pesan: {len(session.get_history())}")
    assert session.state == State.CHATTING, "State harus CHATTING"
    assert len(session.get_history()) == 3, "Harus ada 3 pesan"
    print("✓ Pass\n")

    # Test 3: Get history
    print("Test 3 - Get history:")
    for i, msg in enumerate(session.get_history(), 1):
        print(f"  {i}. [{msg['role']}] {msg['content']}")
    print("✓ Pass\n")

    # Test 4: Reset
    print("Test 4 - Reset session:")
    session.reset()
    print(f"State setelah reset: {session.state}")
    print(f"History setelah reset: {session.get_history()}")
    assert session.state == State.IDLE, "State harus kembali IDLE"
    assert len(session.get_history()) == 0, "History harus kosong"
    print("✓ Pass\n")

    print("=== All tests passed! ===\n")
