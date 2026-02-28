# Telegram Backup - Downloader / Uploader

A Python script to download media from a Telegram channel/topic and re-upload it to your own Telegram channel.

## Features
- Downloads images, videos, and documents from any Telegram channel/topic.
- Uploads the media to a destination channel with the original message text as the caption.
- Processes in **configurable chunks** (default: 100 albums) so it handles 20,000+ messages without using up your disk.
- Supports albums (multiple media per message) and single media.
- Deletes local files after a successful upload to keep disk usage minimal.
- Cross-platform: works on Windows and Ubuntu/Linux.

## Configuration

Open `downloader.py` and update the settings section at the top:

```python
# --- SOURCE SETTINGS ---
CHANNEL_LINK = 'https://t.me/c/YOUR_SOURCE_CHANNEL'
TOPIC_ID = None  # Set if downloading from a specific topic/forum thread
START_FROM_MESSAGE_ID = 1  # Start from this message ID

# --- DESTINATION SETTINGS ---
UPLOAD_TO_DESTINATION = True
DEST_CHANNEL_LINK = 'https://t.me/c/YOUR_DESTINATION_CHANNEL'
DEST_TOPIC_ID = None  # Set if uploading to a specific topic
DELETE_AFTER_UPLOAD = True  # Clean up local files after upload

# --- CHUNK SETTINGS ---
CHUNK_SIZE = 100  # Download and upload this many albums at a time
```

## Windows

```bat
run.bat
```

## Ubuntu / Linux

**First time only:**
```bash
chmod +x setup.sh run.sh
./setup.sh
```

**Then run:**
```bash
./run.sh
```

## Running in the Background (Ubuntu)

When you close your SSH terminal, any running process will be killed unless you detach it first.

### Option 1: `nohup` (simple)

```bash
nohup ./run.sh > output.log 2>&1 &
echo "Started! PID: $!"
```

- All output is saved to `output.log`
- Watch live progress: `tail -f output.log`
- Find and stop the process:
  ```bash
  ps aux | grep downloader.py
  kill <PID>
  ```
tail -f output.log
### Option 2: `screen` (recommended — reattach anytime)

```bash
# Install if needed
sudo apt install screen

# Start a named session
screen -S telegram

# Run the script normally inside screen
./run.sh

# Detach and leave it running: press Ctrl+A then D

# Reattach later to check progress
screen -r telegram

# List all active sessions
screen -ls
```

---

## Requirements
- Python 3.8+
- A Telegram account with API credentials from [my.telegram.org](https://my.telegram.org)
