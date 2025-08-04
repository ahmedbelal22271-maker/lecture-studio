# whisper_offline.py
# This file defines how to run Whisper locally to transcribe Arabic lecture recordings.
# It uses subprocess to call the Whisper CLI tool directly, handles file output reading,
# and now includes a terminal-based progress bar to inform the user about progress.

import subprocess  # Used to run the Whisper command-line tool as a separate process
import os          # Used to check if output files exist
from tqdm import tqdm  # tqdm is used to display a progress bar in the terminal

def transcribe_audio(audio_path):
    """
    This function takes the path to an audio (.mp3) file and transcribes it using Whisper.
    
    It performs transcription only (no translation) and returns:
        - The Arabic transcript as plain text.
        - A placeholder for English transcript (currently unused but left for consistency).
        - A JSON string with metadata (e.g., timestamps) if Whisper outputs it.
    
    We use only one call to Whisper to save time and avoid redundancy.
    """

    # These are the names of the output files we expect Whisper to produce.
    # These filenames are determined by how Whisper saves output automatically.
    ar_txt = "transcript_ar.txt"     # Main transcript (Arabic, plain text)
    ar_json = "transcript_ar.json"   # Optional metadata (timestamps, segments, etc.)

    # We simulate a 2-step progress bar to give the user feedback in terminal.
    # Step 1 = transcribing with Whisper
    # Step 2 = loading the transcript from disk
    with tqdm(total=2, desc="[WHISPER] Transcription", bar_format="{l_bar}{bar} {n_fmt}/{total_fmt}") as pbar:

        # This is the command that gets passed to the system to run Whisper.
        # It includes:
        # - the model size
        # - language (Arabic)
        # - no translation (transcribe only)
        # - thread control for better CPU heat management
        transcribe_cmd = [
            "whisper", audio_path,
            "--model", "medium",         # Medium model balances speed and quality
            "--language", "Arabic",      # Arabic input, so Whisper doesn’t waste time detecting
            "--task", "transcribe",      # We want Arabic as-is, not translated to English
            "--output_format", "txt",    # We want a .txt transcript only
            "--output_dir", ".",         # Save output in current directory (for simplicity)
            "--fp16", "False",           # Disable float16 to avoid GPU compatibility issues
            "--threads", "3"             # Use only 3 threads to prevent CPU overheating
        ]

        # Actually run the command above.
        # If Whisper fails for any reason (e.g., bad audio file), we show an error.
        try:
            subprocess.run(transcribe_cmd, check=True)
            pbar.update(1)  # 1/2 progress: Whisper has finished
        except subprocess.CalledProcessError as e:
            # If Whisper throws an error, print it clearly and crash the function
            print("[WHISPER] Error occurred during transcription.")
            raise RuntimeError("Whisper failed to transcribe") from e

        # After transcription, we now load the transcript from disk
        pbar.set_description("[WHISPER] Loading Output")

        # Read the Arabic transcript as a string.
        # This file must exist; if it doesn't, it means Whisper didn’t generate it.
        try:
            with open(ar_txt, "r", encoding="utf-8") as f:
                transcript_ar = f.read()
        except FileNotFoundError:
            raise RuntimeError("Arabic transcript not found after transcription.")

        # Try to read the JSON metadata if available.
        # If it doesn’t exist, we just use a dummy empty JSON string.
        if os.path.exists(ar_json):
            with open(ar_json, "r", encoding="utf-8") as f:
                transcript_json = f.read()
        else:
            transcript_json = "{}"

        pbar.update(1)  # 2/2 progress: Files have been loaded

    # Return:
    # - Arabic transcript string (the actual content)
    # - Empty string for English (not used here)
    # - JSON metadata (may be empty)
    return transcript_ar, "", transcript_json
