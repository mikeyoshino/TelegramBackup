import asyncio
import os
import re
import sys
import time
import shutil
from telethon import TelegramClient
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, DocumentAttributeVideo

# Import FastTelethon for parallel downloads
try:
    from FastTelethon import download_file as fast_download
    FAST_DOWNLOAD_AVAILABLE = True
    print("[SPEED BOOST] FastTelethon parallel download enabled!")
except ImportError:
    FAST_DOWNLOAD_AVAILABLE = False
    print("[INFO] Using standard download (slower)")

# Fix UTF-8 encoding for Windows console
if sys.platform == 'win32':
    sys.stdout.reconfigure(encoding='utf-8')

# ==============================================================================
# CONFIGURATION
# ==============================================================================
API_ID = '34796078' 
API_HASH = 'b28bafb4abe937cff6ea973970421d96'

# --- SOURCE SETTINGS ---
CHANNEL_LINK = 'https://t.me/c/2298649486'
TOPIC_ID = 49114
START_FROM_MESSAGE_ID = 1  

# --- DESTINATION SETTINGS ---
UPLOAD_TO_DESTINATION = True
DEST_CHANNEL_LINK = 'https://t.me/c/3863897481' # REPLACE THIS with your destination channel link
DEST_TOPIC_ID = 8780 # Set to topic number if uploading to a specific topic
DELETE_AFTER_UPLOAD = True # Delete downloaded folders after uploading

# --- FILTER OPTIONS ---
DOWNLOAD_IMAGES = True
DOWNLOAD_VIDEOS = True
DOWNLOAD_DOCUMENTS = False  

# Download directory
DOWNLOAD_DIR = 'downloads'

# Limit for testing
GROUP_LIMIT = 100000

# Parallel downloads
PARALLEL_DOWNLOADS = 5

# Parallel uploads - how many groups/albums to upload simultaneously
# Keep this at 3 or lower to avoid Telegram flood errors
PARALLEL_UPLOADS = 5

# --- CHUNK SETTINGS ---
CHUNK_SIZE = 50  # Download and upload this many messages/albums at a time

# Delay between each sequential send in Phase 2 (seconds)
# Helps avoid connection resets when Telegram gets too many rapid requests
UPLOAD_DELAY = 1.5

def get_peer_id(link):
    """
    Attempts to extract channel ID, optional topic ID, and optional message ID from a link.
    Returns tuple: (channel_id, topic_id or None, message_id or None)
    """
    link = str(link).strip()
    
    match_tme = re.search(r't\.me/c/(\d+)(?:/(\d+)(?:/(\d+))?)?', link)
    if match_tme:
        channel_id = int(match_tme.group(1))
        first_num = int(match_tme.group(2)) if match_tme.group(2) else None
        second_num = int(match_tme.group(3)) if match_tme.group(3) else None
        
        channel_id = int(f"-100{channel_id}")
        
        if second_num:
            return (channel_id, first_num, second_num)
        elif first_num:
            return (channel_id, None, first_num)
        else:
            return (channel_id, None, None)
    
    match_web = re.search(r'web\.telegram\.org.*#(-?\d+)', link)
    if match_web:
        try:
            channel_id = int(match_web.group(1))
            if channel_id < 0 and not str(channel_id).startswith('-100'):
                channel_id = int(f"-100{abs(channel_id)}")
            return (channel_id, None, None)
        except ValueError:
            pass

    if re.match(r'^-?\d+$', link):
        channel_id = int(link)
        if channel_id < 0 and not str(channel_id).startswith('-100'):
            channel_id = int(f"-100{abs(channel_id)}")
        return (channel_id, None, None)
        
    return (link, None, None)

async def upload_chunk(client, dest_entity, dest_topic_id, ordered_groups, group_folders, group_captions):
    """
    Handles uploading a chunk of downloaded folders.
    
    2-phase strategy for parallel speed + correct message order:
      Phase 1 (Parallel): Pre-upload all file bytes to Telegram servers simultaneously
      Phase 2 (Sequential): Send messages in correct order using pre-uploaded references
    """
    if not dest_entity:
        return
        
    print("\n" + "="*60)
    print(f"UPLOAD PHASE: Processing chunk of {len(ordered_groups)} items...")
    print("="*60)
    
    # Build list of (group_id, files, caption) to process
    groups_to_upload = []
    for group_id in ordered_groups:
        folder = group_folders[group_id]
        caption = group_captions.get(group_id, "")
        
        if not os.path.exists(folder):
            continue
        files = sorted([os.path.join(folder, f) for f in os.listdir(folder) if os.path.isfile(os.path.join(folder, f))])
        if not files:
            continue
        groups_to_upload.append((group_id, files, caption, folder))
    
    # ---------------------------------------------------------------
    # PHASE 1: Pre-upload all file bytes in parallel
    # ---------------------------------------------------------------
    print(f"\n[PHASE 1] Pre-uploading {len(groups_to_upload)} groups in parallel (PARALLEL_UPLOADS={PARALLEL_UPLOADS})...")
    
    semaphore = asyncio.Semaphore(PARALLEL_UPLOADS)
    # uploaded_refs[group_id] = list of InputFile references
    uploaded_refs = {}
    
    async def pre_upload_group(group_id, files, caption, folder):
        """Pre-upload all files for a group to Telegram's servers (parallel, with retry)."""
        async with semaphore:
            print(f"  [PRE-UPLOAD] Group {group_id} ({len(files)} files)...")
            
            # Refs stored by index to preserve file order
            refs_by_index = {}
            
            async def upload_one(index, filepath):
                size_mb = os.path.getsize(filepath) / (1024 * 1024)
                print(f"    → Uploading {os.path.basename(filepath)} ({size_mb:.1f}MB)...")
                
                start_time = time.time()
                last_update = [0]
                
                def upload_progress(current, total):
                    now = time.time()
                    if now - last_update[0] >= 2.0:
                        elapsed = now - start_time
                        speed = (current / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                        percent = (current / total) * 100 if total > 0 else 0
                        print(f"    ↑ {percent:.0f}% ({current/(1024*1024):.1f}/{size_mb:.1f}MB) @ {speed:.1f} MB/s - {os.path.basename(filepath)}")
                        last_update[0] = now
                
                max_retries = 5
                for attempt in range(max_retries):
                    try:
                        ref = await client.upload_file(filepath, progress_callback=upload_progress)
                        refs_by_index[index] = (ref, filepath)
                        return
                    except Exception as e:
                        err = str(e)
                        is_connection_reset = "104" in err or "connection reset" in err.lower() or "connection" in err.lower()
                        is_flood = "429" in err or "flood" in err.lower()
                        if attempt < max_retries - 1:
                            if is_flood:
                                wait = 30
                            elif is_connection_reset:
                                wait = 5 * (attempt + 1)
                            else:
                                wait = 3
                            print(f"    ⚠️ Upload failed (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait}s...")
                            await asyncio.sleep(wait)
                        else:
                            print(f"    ✗ Upload failed after {max_retries} attempts: {e}")
                            refs_by_index[index] = None
            
            # Upload all files in this group in parallel
            await asyncio.gather(*[upload_one(i, fp) for i, fp in enumerate(files)])
            
            # Check if any file failed
            if any(refs_by_index.get(i) is None for i in range(len(files))):
                uploaded_refs[group_id] = None
                return
            
            # Reassemble in original order
            uploaded_refs[group_id] = [refs_by_index[i] for i in range(len(files))]
            print(f"  [PRE-UPLOAD] ✓ Group {group_id} ready to send!")
    
    tasks = [pre_upload_group(gid, files, caption, folder) for gid, files, caption, folder in groups_to_upload]
    await asyncio.gather(*tasks)
    
    # ---------------------------------------------------------------
    # PHASE 2: Send messages sequentially to preserve order
    # ---------------------------------------------------------------
    print(f"\n[PHASE 2] Sending messages in order...")
    
    for group_id, files, caption, folder in groups_to_upload:
        refs = uploaded_refs.get(group_id)
        if not refs:
            print(f"  [SEND] ✗ Skipping group {group_id} (pre-upload failed)")
            continue
        
        preview = (caption[:50] + "...") if len(caption) > 50 else caption
        print(f"\n  [SEND] Group {group_id} ({len(refs)} files)...")
        if caption:
            print(f"         Caption: '{preview}'")
        
        try:
            file_refs = [r for r, _ in refs]
            await client.send_file(
                entity=dest_entity,
                file=file_refs,
                caption=caption,
                reply_to=dest_topic_id
            )
            print(f"  [SEND] ✓ Sent successfully!")
            await asyncio.sleep(UPLOAD_DELAY)  # Small delay to avoid connection resets
            
            if DELETE_AFTER_UPLOAD:
                try:
                    shutil.rmtree(folder)
                    print(f"  [SEND] ✓ Cleaned up {folder}")
                except Exception as e:
                    print(f"  [SEND] ✗ Could not delete {folder}: {e}")
                    
        except Exception as e:
            print(f"  [SEND] ✗ Failed for group {group_id}: {e}")
            if "429" in str(e) or "flood" in str(e).lower():
                print("  ⚠️ FLOOD ERROR - Pausing 20s...")
                await asyncio.sleep(20)
            elif "timeout" in str(e).lower():
                print("  ⚠️ TIMEOUT - Pausing 5s...")
                await asyncio.sleep(5)
                
    print("\n[CHUNK COMPLETE] Upload phase finished for current batch.")


async def main():
    print("Connecting to Telegram...")
    
    client = TelegramClient(
        'my_session', 
        API_ID, 
        API_HASH,
        connection_retries=5,
        retry_delay=1,
        auto_reconnect=True,
        timeout=30,
        request_retries=3
    )
    
    await client.start()
    print("Connected with optimized settings!")
    
    try:
        # Resolve source
        target, topic_id, start_msg_id = get_peer_id(CHANNEL_LINK)
        if TOPIC_ID:
            topic_id = TOPIC_ID
        if START_FROM_MESSAGE_ID:
            start_msg_id = START_FROM_MESSAGE_ID
        
        entity = None
        print(f"Resolving channel: {target}...")
        try:
            entity = await client.get_entity(target)
        except ValueError:
            if isinstance(target, int):
                try:
                    new_target = int(f"-100{abs(target)}")
                    print(f"Retrying with ID: {new_target}")
                    entity = await client.get_entity(new_target)
                except ValueError:
                    pass

        if not entity:
            print("\n[ERROR] COULD NOT FIND THE CHANNEL AUTOMATICALLY.")
            return

        print(f"[SUCCESS] Found Channel: {entity.title} (ID: {entity.id})")
        
        # Resolve destination
        dest_entity = None
        dest_topic_id = DEST_TOPIC_ID
        if UPLOAD_TO_DESTINATION and DEST_CHANNEL_LINK:
            dest_target, d_topic_id, _ = get_peer_id(DEST_CHANNEL_LINK)
            if not dest_topic_id and d_topic_id:
                dest_topic_id = d_topic_id
                
            print(f"Resolving destination channel: {dest_target}...")
            try:
                dest_entity = await client.get_entity(dest_target)
                print(f"[SUCCESS] Found Destination Channel: {dest_entity.title}")
            except Exception as e:
                print(f"[ERROR] Could not find destination channel. Ensure you are a member. ({e})")
                return
        
        if not os.path.exists(DOWNLOAD_DIR):
            os.makedirs(DOWNLOAD_DIR)
            
        print(f"Processing in chunks of {CHUNK_SIZE}")
        print("-" * 60)

        total_download_count = 0
        total_size_downloaded = 0
        
        iter_params = {'reverse': True}
        if start_msg_id:
            iter_params['min_id'] = start_msg_id - 1
        if topic_id:
            iter_params['reply_to'] = topic_id

        # State tracking for the current chunk
        messages_to_download = []
        unique_message_groups = set()
        ordered_groups = []
        group_folders = {}
        group_captions = {}
        seen_items_per_group = {}
        total_groups_processed = 0
        
        # Worker setup
        download_queue = asyncio.Queue()
        download_lock = asyncio.Lock()
        
        async def download_worker(worker_id):
            nonlocal total_download_count, total_size_downloaded
            while True:
                try:
                    item = await asyncio.wait_for(download_queue.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    break
                
                message, media_type, file_size, folder_name = item
                try:
                    async with download_lock:
                        if not os.path.exists(folder_name):
                            os.makedirs(folder_name)
                    
                    size_mb = file_size / (1024 * 1024) if file_size > 0 else 0
                    print(f"  [{worker_id}] {media_type} ({size_mb:.1f}MB) - Starting...")
                    
                    last_update = [0]
                    start_time = time.time()
                    
                    start_time = time.time()
                    
                    def progress_callback(current, total):
                        now = time.time()
                        if now - last_update[0] >= 2.0:
                            elapsed = now - start_time
                            speed = (current / (1024 * 1024)) / elapsed if elapsed > 0 else 0
                            percent = (current / total) * 100 if total > 0 else 0
                            mb_current = current / (1024 * 1024)
                            mb_total = total / (1024 * 1024)
                            print(f"  [{worker_id}] {percent:.0f}% ({mb_current:.1f}/{mb_total:.1f}MB) @ {speed:.1f} MB/s")
                            last_update[0] = now
                    
                    max_retries = 5
                    path = None
                    for attempt in range(max_retries):
                        try:
                            # Only use FastTelethon for files over 5MB
                            # Small files use the standard downloader which has no invalid limit issues
                            use_fast = (
                                FAST_DOWNLOAD_AVAILABLE
                                and isinstance(message.media, MessageMediaDocument)
                                and file_size > 5 * 1024 * 1024  # >5MB
                            )
                            if use_fast:
                                doc = message.media.document
                                original_filename = None
                                if hasattr(doc, 'attributes'):
                                    from telethon.tl.types import DocumentAttributeFilename
                                    for attr in doc.attributes:
                                        if isinstance(attr, DocumentAttributeFilename):
                                            original_filename = attr.file_name
                                            break
                                if not original_filename:
                                    mime = getattr(doc, 'mime_type', '')
                                    ext_map = {'video/mp4': '.mp4', 'image/jpeg': '.jpg', 'image/png': '.png', 'audio/mpeg': '.mp3', 'application/pdf': '.pdf'}
                                    file_ext = ext_map.get(mime, '.bin')
                                    original_filename = f"{message.id}{file_ext}"
                                
                                filepath = os.path.join(folder_name, original_filename)
                                path = await fast_download(client, message.media.document, filepath, workers=8, progress_callback=progress_callback)
                            else:
                                path = await client.download_media(message, file=folder_name, progress_callback=progress_callback)
                            break  # success - exit retry loop
                        except Exception as e:
                            err = str(e)
                            is_reset = "104" in err or "64" in err or "connection" in err.lower() or "reset" in err.lower()
                            is_flood = "429" in err or "flood" in err.lower()
                            if attempt < max_retries - 1:
                                if is_flood:
                                    wait = 30
                                elif is_reset:
                                    wait = 10 * (attempt + 1)  # 10s, 20s, 30s, 40s
                                else:
                                    wait = 5
                                print(f"  [{worker_id}] ⚠️ Error (attempt {attempt+1}/{max_retries}): {e} — retrying in {wait}s...")
                                await asyncio.sleep(wait)
                            else:
                                print(f"  [{worker_id}] ✗ FAILED after {max_retries} attempts: {e}")
                    
                    if path:
                        print(f"  [{worker_id}] ✓ {os.path.basename(path)} - DONE!")
                        async with download_lock:
                            total_size_downloaded += file_size
                            total_download_count += 1
                        await asyncio.sleep(1.0)
                    else:
                        print(f"  [{worker_id}] ✗ FAILED (no path returned)")
                except Exception as e:
                    if "429" in str(e) or "flood" in str(e).lower():
                        await asyncio.sleep(10)
                    else:
                        await asyncio.sleep(2)
                finally:
                    download_queue.task_done()

        async def process_current_chunk():
            """Executes download and upload for the current accumulated chunk."""
            if not messages_to_download:
                return

            print(f"\n--- Processing chunk of {len(ordered_groups)} message groups ---")
            
            # Queue downloads
            for item in messages_to_download:
                await download_queue.put(item)
            
            # Start workers
            workers = [asyncio.create_task(download_worker(f"W{i+1}")) for i in range(PARALLEL_DOWNLOADS)]
            await download_queue.join()
            for worker in workers:
                worker.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

            # Upload phase
            if UPLOAD_TO_DESTINATION and dest_entity:
                await upload_chunk(client, dest_entity, dest_topic_id, ordered_groups, group_folders, group_captions)
                
            # Clear chunk state
            messages_to_download.clear()
            unique_message_groups.clear()
            ordered_groups.clear()
            group_folders.clear()
            group_captions.clear()
            seen_items_per_group.clear()

        # Iterate over all messages
        async for message in client.iter_messages(entity, **iter_params):
            if message.media:
                should_download = False
                media_type = ""
                file_size = 0
                
                if isinstance(message.media, MessageMediaPhoto) and DOWNLOAD_IMAGES:
                    should_download = True
                    media_type = "Image"
                    if hasattr(message.media, 'photo') and hasattr(message.media.photo, 'sizes'):
                        file_size = max(getattr(s, 'size', 0) for s in message.media.photo.sizes)

                elif isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    file_size = getattr(doc, 'size', 0)
                    mime = getattr(doc, 'mime_type', '')
                    
                    if DOWNLOAD_VIDEOS and hasattr(doc, 'attributes'):
                        for attr in doc.attributes:
                            if isinstance(attr, DocumentAttributeVideo):
                                should_download = True
                                media_type = "Video"
                                break
                    
                    if DOWNLOAD_IMAGES and not should_download and mime.startswith('image/'):
                        should_download = True
                        media_type = "Image"
                    
                    if DOWNLOAD_DOCUMENTS and not should_download:
                        should_download = True
                        media_type = f"File ({mime})"
                
                if should_download:
                    message_group_id = message.grouped_id if message.grouped_id else message.id
                    is_new_group = message_group_id not in unique_message_groups
                    
                    if is_new_group and GROUP_LIMIT and total_groups_processed >= GROUP_LIMIT:
                        print(f"\n✓ Reached limit of {GROUP_LIMIT} messages/albums!")
                        break
                        
                    # Process the complete chunk BEFORE adding the new group's items
                    if is_new_group and len(unique_message_groups) >= CHUNK_SIZE:
                        await process_current_chunk()
                        is_new_group = True
                        
                    if is_new_group:
                        unique_message_groups.add(message_group_id)
                        ordered_groups.append(message_group_id)
                        
                        folder_name = os.path.join(DOWNLOAD_DIR, f"message_{message.id}")
                        group_folders[message_group_id] = folder_name
                        seen_items_per_group[message_group_id] = 1
                        total_groups_processed += 1
                        print(f"\n[NEW {media_type}] Message/Album ID {message_group_id} -> Folder: {folder_name} (Total: {total_groups_processed})")
                    else:
                        seen_items_per_group[message_group_id] += 1
                        folder_name = group_folders[message_group_id]
                        print(f"  → Found item {seen_items_per_group[message_group_id]} for ID {message_group_id}")
                        
                    if message.text:
                        if message_group_id not in group_captions:
                            group_captions[message_group_id] = message.text
                        else:
                            if message.text not in group_captions[message_group_id]:
                                group_captions[message_group_id] += f"\n{message.text}"
                                
                    messages_to_download.append((message, media_type, file_size, folder_name))

        # Process any remaining messages in the final, partial chunk
        if messages_to_download:
            await process_current_chunk()

        print("-" * 60)
        print("\n[ALL TASKS COMPLETED]")
            
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        print("\nCleaning up...")
        await client.disconnect()
        print("Done!")

if __name__ == '__main__':
    asyncio.run(main())
