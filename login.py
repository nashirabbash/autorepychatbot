#!/usr/bin/env python3
"""
Interactive login helper for Pyrogram.
This script handles the OTP authentication flow.
"""
import sys
import asyncio

# Fix Python 3.14 event loop issue
original_get_event_loop = asyncio.get_event_loop
def patched_get_event_loop():
    try:
        return original_get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        return loop
asyncio.get_event_loop = patched_get_event_loop

from pyrogram import Client
from config import API_ID, API_HASH

async def login():
    """Interactive login to Telegram account."""
    app = Client("autochatreply", api_id=API_ID, api_hash=API_HASH)
    async with app:
        print("✓ Successfully logged in!")

if __name__ == "__main__":
    try:
        asyncio.run(login())
    except KeyboardInterrupt:
        print("\nLogin cancelled")
        sys.exit(1)
