# How to Download from Telegram Topics/Forums

## What are Topics?

Some Telegram channels have **Topics** (also called Forums) - these are like sub-channels or separate discussion threads within the main channel.

## Finding the Topic ID

### Method 1: From the URL

When you open a topic in Telegram, look at the URL:

```
https://t.me/c/2298649486/1/500
                     │        │  │
                     │        │  └─ Message ID (optional)
                     │        └──── Topic ID
                     └─────────────  Channel ID
```

### Method 2: Right-click Menu

1. Right-click on any message in the topic
2. Copy the message link
3. Paste it to see the URL format

## How to Use

### Option 1: Use the URL directly

```python
# Download from Topic 1, starting from message 500
CHANNEL_LINK = 'https://t.me/c/2298649486/1/500'
TOPIC_ID = None  # Auto-detected from URL
```

### Option 2: Set Topic ID manually

```python
# Download everything from Topic 5
CHANNEL_LINK = 'https://t.me/c/2298649486'
TOPIC_ID = 5  # Manually specify topic
```

### Option 3: Download all topics

```python
# Download from entire channel (all topics)
CHANNEL_LINK = 'https://t.me/c/2298649486'
TOPIC_ID = None  # No topic filter
```

## Examples

**Download from Topic 1:**
```python
CHANNEL_LINK = 'https://t.me/c/2298649486/1'
TOPIC_ID = None
```

**Download from Topic 3, starting at message 200:**
```python
CHANNEL_LINK = 'https://t.me/c/2298649486/3/200'
TOPIC_ID = None
```

**Download from Topic 5 (manual):**
```python
CHANNEL_LINK = 'https://t.me/c/2298649486'
TOPIC_ID = 5
```
