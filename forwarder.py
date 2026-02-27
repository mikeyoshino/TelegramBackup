import asyncio
import os
import re
import sys
import json
from telethon import TelegramClient
from telethon.tl.types import InputChannel

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ==============================================================================
# CONFIGURATION
# ==============================================================================
API_ID = '34796078'
API_HASH = 'b28bafb4abe937cff6ea973970421d96'

# --- SOURCE SETTINGS ---
# The channel to copy messages FROM
SOURCE_CHANNEL = 'https://t.me/c/2298649486'
SOURCE_TOPIC_ID = 49114       # Set to topic ID if source is a forum topic (None for all)
START_FROM_MESSAGE_ID = 1     # Start from this message ID (1 = from the beginning)

# --- DESTINATION SETTINGS ---
# The channel to copy messages TO
DEST_CHANNEL = 'https://t.me/c/3863897481'
DEST_TOPIC_ID = 7             # Set to topic ID if destination is a forum topic (None for general)

# --- FORWARD SETTINGS ---
# How many messages to forward in one batch (Telegram allows up to 100 at once)
BATCH_SIZE = 50

# Delay between each batch (seconds) to avoid flood errors
BATCH_DELAY = 3.0

# File to track which messages have already been forwarded (resume support)
PROGRESS_FILE = 'forwarder_progress.json'

# ==============================================================================

def get_peer_id(link):
    link = str(link).strip()
    match_tme = re.search(r't\.me/c/(\d+)(?:/(\d+)(?:/(\d+))?)?', link)
    if match_tme:
        channel_id = int(f"-100{match_tme.group(1)}")
        first_num = int(match_tme.group(2)) if match_tme.group(2) else None
        second_num = int(match_tme.group(3)) if match_tme.group(3) else None
        if second_num:
            return (channel_id, first_num, second_num)
        elif first_num:
            return (channel_id, None, first_num)
        return (channel_id, None, None)

    match_web = re.search(r'web\.telegram\.org.*#(-?\d+)', link)
    if match_web:
        channel_id = int(match_web.group(1))
        if channel_id < 0 and not str(channel_id).startswith('-100'):
            channel_id = int(f"-100{abs(channel_id)}")
        return (channel_id, None, None)

    if re.match(r'^-?\d+$', link):
        channel_id = int(link)
        if channel_id < 0 and not str(channel_id).startswith('-100'):
            channel_id = int(f"-100{abs(channel_id)}")
        return (channel_id, None, None)

    return (link, None, None)


def load_progress():
    """Load the set of already-forwarded message IDs from disk."""
    if os.path.exists(PROGRESS_FILE):
        with open(PROGRESS_FILE, 'r') as f:
            data = json.load(f)
            return set(data.get('forwarded_ids', []))
    return set()


def save_progress(forwarded_ids):
    """Save the set of forwarded message IDs to disk."""
    with open(PROGRESS_FILE, 'w') as f:
        json.dump({'forwarded_ids': list(forwarded_ids)}, f)


async def main():
    print("=" * 60)
    print("Telegram Message Forwarder")
    print("=" * 60)
    print("Connecting to Telegram...")

    client = TelegramClient(
        'my_session',
        API_ID,
        API_HASH,
        connection_retries=5,
        retry_delay=1,
        auto_reconnect=True,
        timeout=30
    )

    await client.start()
    print("Connected!\n")

    # Resolve source channel
    src_target, src_topic, src_start_msg = get_peer_id(SOURCE_CHANNEL)
    if SOURCE_TOPIC_ID:
        src_topic = SOURCE_TOPIC_ID
    if START_FROM_MESSAGE_ID:
        src_start_msg = START_FROM_MESSAGE_ID

    print(f"Resolving source channel: {src_target}...")
    try:
        src_entity = await client.get_entity(src_target)
        print(f"[SOURCE] {src_entity.title} (ID: {src_entity.id})")
    except Exception as e:
        print(f"[ERROR] Could not find source channel: {e}")
        await client.disconnect()
        return

    # Resolve destination channel
    dst_target, dst_topic, _ = get_peer_id(DEST_CHANNEL)
    if DEST_TOPIC_ID:
        dst_topic = DEST_TOPIC_ID

    print(f"Resolving destination channel: {dst_target}...")
    try:
        dst_entity = await client.get_entity(dst_target)
        print(f"[DEST]   {dst_entity.title} (ID: {dst_entity.id})")
    except Exception as e:
        print(f"[ERROR] Could not find destination channel: {e}")
        await client.disconnect()
        return

    # Load progress (resume support)
    forwarded_ids = load_progress()
    print(f"\n[RESUME] Already forwarded: {len(forwarded_ids)} messages")
    if src_start_msg:
        print(f"[CONFIG] Starting from message ID: {src_start_msg}")
    if src_topic:
        print(f"[CONFIG] Source topic ID: {src_topic}")
    if dst_topic:
        print(f"[CONFIG] Destination topic ID: {dst_topic}")
    print("-" * 60)

    # Collect messages to forward
    iter_params = {'reverse': True}
    if src_start_msg:
        iter_params['min_id'] = src_start_msg - 1
    if src_topic:
        iter_params['reply_to'] = src_topic

    total_forwarded = 0
    batch = []

    async def flush_batch():
        """Forward the current batch of messages."""
        nonlocal total_forwarded

        if not batch:
            return

        msg_ids = [m.id for m in batch]
        print(f"[FORWARD] Forwarding batch of {len(msg_ids)} messages (IDs: {msg_ids[0]}–{msg_ids[-1]})...")

        try:
            await client.forward_messages(
                entity=dst_entity,
                messages=msg_ids,
                from_peer=src_entity,
                drop_author=False,  # Keep original author info
                # reply_to=dst_topic  # Uncomment if you want to forward into a topic
            )
            for m in batch:
                forwarded_ids.add(m.id)
            total_forwarded += len(batch)
            save_progress(forwarded_ids)
            print(f"  ✓ Batch forwarded! Total so far: {total_forwarded}")
            await asyncio.sleep(BATCH_DELAY)
        except Exception as e:
            err = str(e)
            if '429' in err or 'flood' in err.lower():
                print(f"  ⚠️ FLOOD WAIT - Pausing 30s...")
                await asyncio.sleep(30)
                # Retry
                try:
                    await client.forward_messages(
                        entity=dst_entity,
                        messages=msg_ids,
                        from_peer=src_entity,
                        drop_author=False,
                    )
                    for m in batch:
                        forwarded_ids.add(m.id)
                    total_forwarded += len(batch)
                    save_progress(forwarded_ids)
                    print(f"  ✓ Batch forwarded after retry! Total: {total_forwarded}")
                except Exception as e2:
                    print(f"  ✗ Batch failed even after retry: {e2}")
            else:
                print(f"  ✗ Batch failed: {e}")

        batch.clear()

    print("Scanning messages...")
    total_scanned = 0

    async for message in client.iter_messages(src_entity, **iter_params):
        total_scanned += 1

        # Skip already-forwarded messages
        if message.id in forwarded_ids:
            continue

        # Skip empty/service messages
        if not message.text and not message.media:
            continue

        batch.append(message)

        if len(batch) >= BATCH_SIZE:
            await flush_batch()

    # Forward any remaining messages in the last partial batch
    await flush_batch()

    print("-" * 60)
    print(f"\n[DONE] Forwarded {total_forwarded} messages ({total_scanned} total scanned)")
    print(f"Progress saved to: {PROGRESS_FILE}")
    await client.disconnect()


if __name__ == '__main__':
    asyncio.run(main())
