import subprocess  # Allows us to run external programs like Whisper
import os           # File checking and filesystem operations
from tqdm import tqdm  # tqdm is used to display a progress bar in the terminal

# Global variable to keep track of Whisper's process
whisper_proc = None

# Global flag to interrupt long processing (Mistral later)
abort_flag = False

LANGUAGE_CODE_MAP = {
    "Arabic": "ar",
    "English": "en"
}

def transcribe_audio(audio_path, lang_mode="Arabic"):
    """
    Runs Whisper from the command line to transcribe an MP3 file.

    Args:
        audio_path (str): Path to the input audio file.
        lang_mode (str): Either "Arabic" or "English".

    Returns:
        tuple: (transcript_text, english_placeholder, metadata_json)
    """
    global whisper_proc

    ar_txt = "transcript.txt"
    ar_json = "transcript.json"
    whisper_lang = LANGUAGE_CODE_MAP.get(lang_mode, "ar")

    with tqdm(total=2, desc="[WHISPER] Transcription", bar_format="{l_bar}{bar} {n_fmt}/{total_fmt}") as pbar:
        transcribe_cmd = [
            "whisper", audio_path,
            "--model", "medium",
            "--language", whisper_lang,
            "--task", "transcribe",
            "--output_format", "txt",
            "--output_dir", ".",
            "--fp16", "False",
            "--threads", "3"
        ]

        try:
            whisper_proc = subprocess.Popen(transcribe_cmd)
            whisper_proc.wait()
            pbar.update(1)
        except Exception as e:
            raise RuntimeError("Whisper failed to run") from e

        pbar.set_description("[WHISPER] Loading Output")

        if not os.path.exists(ar_txt):
            raise RuntimeError("Transcript file not found. Whisper may have failed.")

        with open(ar_txt, "r", encoding="utf-8") as f:
            transcript_ar = f.read()

        if os.path.exists(ar_json):
            with open(ar_json, "r", encoding="utf-8") as f:
                transcript_json = f.read()
        else:
            transcript_json = "{}"

        pbar.update(1)

    return transcript_ar, "", transcript_json

def kill_whisper():
    """
    Stops Whisper process if it's still running. Called during emergency shutdown.
    """
    global whisper_proc
    if whisper_proc and whisper_proc.poll() is None:
        whisper_proc.terminate()

def set_abort_flag():
    """
    Signals other parts of the app (like Mistral processing) to stop early.
    """
    global abort_flag
    abort_flag = True

def should_abort():
    """
    Check whether an abort was requested. Called periodically in long loops.
    """
    return abort_flag
