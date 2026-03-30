# AutoReply ChatBot

Automated Telegram anonymous chat bot that uses Google Gemini AI to reply with a **High Value Man (HVM)** persona. Fully autonomous, handles multiple anonymous chat bots simultaneously.

## Features

✨ **Smart Automation**
- Automatic reply to anonymous chat strangers using Gemini AI
- HVM persona with dual personality (Tukang Ledek + Cowok Dewasa)
- Gender detection and routing (skip males, chat with females)
- Message batching (1-minute polling) for natural conversation flow

🚀 **Performance & Reliability**
- Multi-bot support (7+ bots simultaneously)
- Rate limiting & response caching to avoid API quota exhaustion
- Automatic retry on connection errors
- Graceful error handling with informative logging

⚙️ **Flexible Configuration**
- Fully configurable via `.env`
- Tunable delays, timeouts, and polling intervals
- Custom persona system prompt
- Adjustable response limits

## How It Works

### Chat Flow

```
1. Bot sends /next → waits for match
2. Match found → enters CHATTING mode
3. Send opening message (1 bubble: topik seru)
4. Wait 1 minute, buffer all stranger messages
5. After 1 minute → batch send to Gemini
6. Gemini generates reply (max 2 bubbles)
7. Send reply & repeat from step 4
```

### Key Features

**Gender Detection**: Gemini detects stranger gender and outputs `[SKIP]` token if male → bot sends `/next`

**Message Batching**: All messages received during 1-minute window are combined into single Gemini request for better context

**Rate Limiting**:
- Minimum 3-second interval between API calls
- Response caching (cache by message + hour of day)
- Random 0.5-1.5s delay before each request

**Persona**: Custom system prompt from `persona.txt` injected with time context (WIB timezone)

## Setup

### Prerequisites

- Python 3.10+
- Telegram account (for Pyrogram userbot)
- Google Gemini API key
- One or more anonymous chat bot usernames

### Installation

1. **Clone repository**
```bash
git clone https://github.com/nashirabbash/autorepychatbot.git
cd autorepychatbot
```

2. **Create `.env` file**
```bash
cp .env.example .env
```

3. **Fill `.env` with credentials**
```bash
# From https://my.telegram.org
API_ID=your_telegram_api_id
API_HASH=your_api_hash

# From https://aistudio.google.com
GEMINI_API_KEY=your_gemini_api_key

# Anonymous chat bot usernames (comma-separated)
ANON_BOT_USERNAMES=unairanonymouschat_bot,chatbot,uifess_bot

# Optional tuning
CHAT_POLLING_INTERVAL=60
MAX_BUBBLES_PER_REPLY=2
GEMINI_REQUEST_DELAY_MIN=0.5
GEMINI_REQUEST_DELAY_MAX=1.5
GEMINI_MIN_REQUEST_INTERVAL=3.0
```

4. **Install dependencies**
```bash
pip install -r requirements.txt
```

5. **Run the bot**
```bash
./run.sh
```

On first run, Telegram will ask for OTP (one-time password) - this is normal and required for Pyrogram to login to your account.

## Configuration

All settings configurable via environment variables in `.env`:

### Timing

| Variable | Default | Description |
|----------|---------|-------------|
| `CHAT_POLLING_INTERVAL` | 60 | Seconds between message batches |
| `MAX_BUBBLES_PER_REPLY` | 2 | Max chat bubbles per reply |
| `TYPING_DELAY_MIN` | 1.0 | Min typing simulation delay (sec) |
| `TYPING_DELAY_MAX` | 3.0 | Max typing simulation delay (sec) |
| `BUBBLE_DELAY_MIN` | 0.5 | Min delay between bubbles (sec) |
| `BUBBLE_DELAY_MAX` | 1.0 | Max delay between bubbles (sec) |

### Rate Limiting

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_REQUEST_DELAY_MIN` | 0.5 | Min delay before Gemini request (sec) |
| `GEMINI_REQUEST_DELAY_MAX` | 1.5 | Max delay before Gemini request (sec) |
| `GEMINI_MIN_REQUEST_INTERVAL` | 3.0 | Min interval between consecutive requests (sec) |

### API & Persona

| Variable | Default | Description |
|----------|---------|-------------|
| `GEMINI_API_KEY` | - | Google Gemini API key (required) |
| `GEMINI_MODEL` | `gemini-2.5-flash` | Gemini model to use |
| `MAX_HISTORY` | 20 | Max conversation history messages |
| `LOG_LEVEL` | `INFO` | Logging level (DEBUG, INFO, WARNING, ERROR) |

## File Structure

```
autochatreply/
├── main.py              # Pyrogram client + state machine + message handler
├── gemini_client.py     # Gemini API wrapper with caching
├── chat_session.py      # Session management & conversation history
├── config.py            # Configuration loading from .env
├── persona.txt          # System prompt for HVM persona
├── .env                 # Credentials (create from .env.example)
├── .env.example         # Environment template
├── requirements.txt     # Python dependencies
├── run.sh               # Startup script
└── README.md            # This file
```

## Architecture

### State Machine

```
IDLE
  ↓
WAITING_MATCH (sent /next, waiting for match)
  ├─ Match found → CHATTING
  └─ Disconnect → /search → WAITING_MATCH

CHATTING (in conversation with stranger)
  ├─ Message received → buffer for 1 minute
  ├─ After 1 minute → batch send to Gemini
  ├─ Gemini reply → send bubbles
  ├─ [SKIP] token (male detected) → /next → WAITING_MATCH
  └─ Disconnect message → /search → WAITING_MATCH
```

### Components

**main.py**
- Pyrogram event handler for incoming messages
- State machine logic
- Message filtering and routing
- Bubble sending with typing simulation

**gemini_client.py**
- Gemini API wrapper
- Response caching (message + hour → cached reply)
- Automatic retry on connection errors
- Time context injection (WIB timezone)

**chat_session.py**
- Conversation history management
- Message batching buffer
- Timestamps for rate limiting
- Session state tracking

**config.py**
- Environment variable parsing
- Safe int/float conversion with defaults
- Multi-bot configuration

## Persona System

The bot's personality is defined in `persona.txt`. It includes:

- **Identity**: Age, batch year, hometown, Instagram
- **Personality**: Tukang Ledek + Cowok Dewasa (teasing joker + mature guy)
- **Chat style**: Casual Indonesian, emoji usage, investment talk
- **Opening flow**: Gender detection, conversation routing
- **[SKIP] protocol**: Output `[SKIP]` when male detected

Customize by editing `persona.txt` before running the bot.

## Logging

Logs show detailed information about bot operation:

```
2026-03-31 00:00:02,219 | INFO | __main__ | Match/stranger detected → entering CHATTING mode
2026-03-31 00:00:06,739 | INFO | gemini_client | ✓ Generated 2 bubbles from Gemini
2026-03-31 00:00:16,787 | INFO | __main__ | ⏱️  Processing 2 buffered messages from stranger
```

Control verbosity with `LOG_LEVEL=DEBUG` for detailed debugging.

## Troubleshooting

### "Gemini warm-up failed"
- Check `GEMINI_API_KEY` in `.env`
- Verify API key is valid and has quota remaining
- Check internet connection

### "Bot didn't send /next"
- Check if bot username in `ANON_BOT_USERNAMES` is correct
- Verify Telegram account has permission to chat with that bot
- Check logs for state transitions

### "Server disconnected" errors
- Normal for long user response times (bot waits up to 20 minutes)
- SDK automatically retries - no action needed

### High rate limiting
- Reduce `MAX_BUBBLES_PER_REPLY`
- Increase `GEMINI_MIN_REQUEST_INTERVAL`
- Increase `CHAT_POLLING_INTERVAL`

## Performance Tips

1. **Reduce API calls**:
   - Increase `CHAT_POLLING_INTERVAL` (batch more messages)
   - Enable caching (automatic)

2. **Make responses more natural**:
   - Decrease `BUBBLE_DELAY_MIN/MAX` for faster typing
   - Adjust `MAX_BUBBLES_PER_REPLY` to 1 for shorter responses

3. **Handle more conversations**:
   - Add more bots to `ANON_BOT_USERNAMES`
   - Use `GEMINI_REQUEST_DELAY_MIN/MAX` to spread requests

## Error Handling

The bot gracefully handles:
- Network timeouts (automatic retry)
- API rate limiting (silent skip)
- Missing persona file (continues without persona)
- Partner disconnection (sends `/search`)
- Malformed messages (ignored)

All errors are logged but don't crash the bot.

## Development

### Testing

```bash
# Test gemini_client
python3 gemini_client.py

# Test chat_session
python3 chat_session.py
```

### Running locally

```bash
# With custom polling interval
CHAT_POLLING_INTERVAL=30 LOG_LEVEL=DEBUG ./run.sh
```

### Modifying persona

Edit `persona.txt` and restart the bot. Gemini will read the new persona on startup (warm-up phase).

## License

This project is for educational and experimental purposes.

## Author

Created for autonomous Telegram anonymous chat automation with AI persona.

---

**Last Updated**: 2026-03-31
**Version**: 1.0
**Status**: Production-ready
