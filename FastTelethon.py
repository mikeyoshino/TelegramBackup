"""
FastTelethon - Parallel file download implementation
Based on: https://github.com/tulir/telethon-session-sqlalchemy
Optimized for faster downloads using parallel connections
"""

import asyncio
import hashlib
import math
import os
from collections import defaultdict
from typing import AsyncGenerator, Optional, Union

from telethon import TelegramClient, utils
from telethon.crypto import AuthKey
from telethon.tl.functions.upload import GetFileRequest
from telethon.tl.types import (
    Document, InputDocumentFileLocation, InputFileLocation,
    InputPhotoFileLocation, Photo, TypeInputFileLocation
)

DEFAULT_PART_SIZE = 1024 * 1024  # 1MB chunks (required by Telegram for large files)
WORKER_COUNT = 16  # Number of parallel connections (increased for Premium speeds)


def get_input_location(file: Union[Document, Photo]) -> TypeInputFileLocation:
    """Convert a Document or Photo to the appropriate InputFileLocation."""
    if isinstance(file, Document):
        return InputDocumentFileLocation(
            id=file.id,
            access_hash=file.access_hash,
            file_reference=file.file_reference,
            thumb_size=""
        )
    elif isinstance(file, Photo):
        return InputPhotoFileLocation(
            id=file.id,
            access_hash=file.access_hash,
            file_reference=file.file_reference,
            thumb_size=file.sizes[-1].type
        )
    raise TypeError(f"Unknown file type {type(file)}")


async def download_file(
    client: TelegramClient,
    file: Union[Document, Photo],
    file_name: str,
    part_size: int = DEFAULT_PART_SIZE,
    workers: int = WORKER_COUNT,
    progress_callback=None
) -> str:
    """
    Download a file using parallel connections for maximum speed.
    
    Args:
        client: The Telegram client
        file: Document or Photo to download
        file_name: Path where to save the file
        part_size: Size of each chunk (default 512KB)
        workers: Number of parallel workers (default 8)
        progress_callback: Optional callback(current, total)
    
    Returns:
        Path to the downloaded file
    """
    size = file.size if hasattr(file, 'size') else 0
    part_count = math.ceil(size / part_size)
    location = get_input_location(file)
    
    # Progress tracking
    downloaded = [0]
    lock = asyncio.Lock()
    
    # Create directory if needed
    os.makedirs(os.path.dirname(os.path.abspath(file_name)), exist_ok=True)
    
    # Pre-allocate file space for faster writing
    with open(file_name, 'wb') as f:
        f.truncate(size)
    
    # Open file for parallel writes using a regular file handle (cross-platform)
    file_obj = open(file_name, 'r+b')
    write_lock = asyncio.Lock()  # Needed because seek+write is not atomic
    
    try:
        async def download_part(part_index: int) -> None:
            """Download a single part of the file."""
            offset = part_index * part_size
            # Always use the full part_size as the limit.
            # Telegram returns fewer bytes for the last chunk automatically.
            # Passing remaining bytes as limit causes "invalid limit" errors.
            limit = part_size
            
            retry_count = 0
            max_retries = 3
            
            while retry_count < max_retries:
                try:
                    result = await client(GetFileRequest(
                        location=location,
                        offset=offset,
                        limit=limit
                    ))
                    
                    # Write at the correct offset (seek+write with lock for thread-safety)
                    async with lock:
                        async with write_lock:
                            file_obj.seek(offset)
                            file_obj.write(result.bytes)
                    
                    # Update progress
                    async with lock:
                        downloaded[0] += len(result.bytes)
                        if progress_callback:
                            progress_callback(downloaded[0], size)
                    
                    break  # Success, exit retry loop
                    
                except Exception as e:
                    retry_count += 1
                    if retry_count >= max_retries:
                        raise
                    await asyncio.sleep(0.5 * retry_count)  # Exponential backoff
        
        # Download all parts in parallel using semaphore to control concurrency
        semaphore = asyncio.Semaphore(workers)
        
        async def sem_download(part_index: int):
            """Worker with semaphore control."""
            async with semaphore:
                await download_part(part_index)
        
        # Create and run all tasks
        tasks = [sem_download(i) for i in range(part_count)]
        await asyncio.gather(*tasks)
        
    finally:
        # Always close the file handle
        file_obj.close()
    
    return file_name
