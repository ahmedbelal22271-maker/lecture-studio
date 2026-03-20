import os
import json

QUEUE_CHECKPOINT_FILE = "queue_checkpoint.json"
SETTINGS_CONFIG_FILE = "settings.json"

CTX_SIZE = 4096
TOKENS_PER_WORD = 1.3

WPM_PRESETS = {
    "Casual Lecture (~120 WPM)": 120,
    "Dense Technical Lecture (~180 WPM)": 180
}

def save_settings(settings: dict) -> None:
    """Save user settings to a JSON file."""
    try:
        with open(SETTINGS_CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(settings, f, indent=2)
    except Exception as e:
        print(f"[WARNING] Could not save settings: {e}")

def load_settings() -> dict:
    """Load user settings from a JSON file, falling back to defaults."""
    defaults = {
        "wpm": 120,
        "chunk_minutes": 10,
        "is_fixed_chunk_mode": True,
        "desired_chunks": 10,
        "beam_size": 2,
        "whisper_model_display": "Medium",
        "asr_threads": max(1, min(4, os.cpu_count() or 4)),
        "lazy_youtube_download": True,
        "overwrite_transcripts": False,
        "use_gpu": False
    }
    
    if not os.path.exists(SETTINGS_CONFIG_FILE):
        save_settings(defaults)
        return defaults
        
    try:
        with open(SETTINGS_CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            for k, v in data.items():
                if k == "use_fixed_chunk_count":
                    continue
                if k in defaults:
                    defaults[k] = v
        save_settings(defaults)
    except Exception as e:
        print(f"[WARNING] Could not load settings: {e}")
        save_settings(defaults)
        
    return defaults

def save_queue_checkpoint(queue_items: list) -> None:
    """Save the current queue to disk so it survives a force-close."""
    tmp = QUEUE_CHECKPOINT_FILE + ".tmp"
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(queue_items, f, indent=2, ensure_ascii=False)
        os.replace(tmp, QUEUE_CHECKPOINT_FILE)
    except Exception as e:
        print(f"[WARNING] Could not save queue checkpoint: {e}")

def load_queue_checkpoint() -> list:
    """Load saved queue items from disk. Returns [] if nothing found."""
    if not os.path.exists(QUEUE_CHECKPOINT_FILE):
        return []
    try:
        with open(QUEUE_CHECKPOINT_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data if isinstance(data, list) else []
    except Exception:
        return []

def clear_queue_checkpoint() -> None:
    """Delete the queue checkpoint file."""
    try:
        if os.path.exists(QUEUE_CHECKPOINT_FILE):
            os.remove(QUEUE_CHECKPOINT_FILE)
    except Exception as e:
        print(f"[WARNING] Could not clear queue checkpoint: {e}")

def estimate_tokens(wpm: int, minutes: int) -> int:
    """Estimates the number of tokens based on WPM and chunk minutes."""
    return int(wpm * minutes * TOKENS_PER_WORD)