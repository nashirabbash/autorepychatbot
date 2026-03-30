"""
Workaround for Python 3.14 + Pyrogram compatibility issue.
Must be imported BEFORE any other modules that use asyncio.
"""
import sys
import asyncio

# Python 3.14 removed get_event_loop() auto-creation
# This restores backward compatibility for Pyrogram
if sys.version_info >= (3, 10):
    asyncio.set_event_loop(asyncio.new_event_loop())
