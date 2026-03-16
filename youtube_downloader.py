"""
youtube_downloader.py
---------------------
Handles all YouTube download logic for Lecture Studio.

Folder structure created:
    youtube_downloads/
        <course>/
            <lecture>/
                audio.mp3

Works with public AND unlisted videos (any video accessible via a direct link).
Does NOT work with private or members-only videos.

Requires:
    pip install yt-dlp
"""

import os
import re

# ---------------------------------------------------------------------------
# yt-dlp availability check
# ---------------------------------------------------------------------------
try:
    import yt_dlp
    YTDLP_AVAILABLE = True
except ImportError:
    yt_dlp = None
    YTDLP_AVAILABLE = False

# Root folder where all YouTube downloads live, next to the script itself
YOUTUBE_DOWNLOADS_DIR = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "youtube_downloads"
)


def _safe_folder_name(name: str) -> str:
    """Strip characters that are illegal in folder names on Windows/Linux/macOS."""
    name = name.strip()
    name = re.sub(r'[\\/*?:"<>|]', "_", name)
    return name or "untitled"


def _setup_pydub():
    """
    Import pydub and point it at the local ffmpeg bundle if present.
    This is the same logic as in main_gui.py — keeps the conversion using
    our known-good local ffmpeg rather than whatever is on the system PATH.
    """
    from pydub import AudioSegment
    _base    = os.path.dirname(os.path.abspath(__file__))
    _ffmpeg  = os.path.join(_base, "ffmpeg-8.0-essentials_build", "bin", "ffmpeg.exe")
    _ffprobe = os.path.join(_base, "ffmpeg-8.0-essentials_build", "bin", "ffprobe.exe")
    if os.path.isfile(_ffmpeg):
        AudioSegment.converter = _ffmpeg
        AudioSegment.ffmpeg    = _ffmpeg
        AudioSegment.ffprobe   = _ffprobe
    return AudioSegment


def get_download_path(course: str, lecture: str) -> str:
    """
    Return the full path to the audio file that would be saved for this
    course/lecture combination.  The file does not have to exist yet.
    """
    course_safe  = _safe_folder_name(course)
    lecture_safe = _safe_folder_name(lecture)
    folder = os.path.join(YOUTUBE_DOWNLOADS_DIR, course_safe, lecture_safe)
    return os.path.join(folder, "audio.mp3")


def download_youtube_audio(
    url: str,
    course: str,
    lecture: str,
    progress_callback=None,   # callable(str) -> updates GUI status label
) -> str:
    """
    Download the audio track of a YouTube video (public or unlisted) as MP3.

    Strategy
    --------
    1. yt-dlp downloads the raw audio stream with NO re-encoding postprocessor.
       This avoids silent-section corruption that happens when yt-dlp's
       FFmpegExtractAudio uses the system ffmpeg (which may be missing or broken).
    2. We convert the raw download to MP3 ourselves using pydub, which is
       already configured to use the local bundled ffmpeg — giving us a clean,
       reliable conversion every time.

    Parameters
    ----------
    url               : Full YouTube URL (regular, short, or unlisted)
    course            : Course name  — used as the parent folder
    lecture           : Lecture title — used as the sub-folder
    progress_callback : Optional callable that receives progress strings for GUI

    Returns
    -------
    str  : Absolute path to the final audio.mp3 file

    Raises
    ------
    RuntimeError  : If yt-dlp is not installed
    RuntimeError  : If the download or conversion fails
    """

    if not YTDLP_AVAILABLE:
        raise RuntimeError(
            "yt-dlp is not installed.\n"
            "Run:  pip install yt-dlp"
        )

    course_safe  = _safe_folder_name(course)
    lecture_safe = _safe_folder_name(lecture)
    folder       = os.path.join(YOUTUBE_DOWNLOADS_DIR, course_safe, lecture_safe)
    os.makedirs(folder, exist_ok=True)

    # yt-dlp output template — we let it pick the extension from the stream
    raw_template = os.path.join(folder, "audio_raw")
    final_mp3    = os.path.join(folder, "audio.mp3")

    # Remove any leftover partial/raw files from a previous failed attempt
    for fname in os.listdir(folder):
        if fname.startswith("audio_raw"):
            try:
                os.remove(os.path.join(folder, fname))
            except Exception:
                pass

    def _yt_progress_hook(d):
        """Translate yt-dlp progress dict into human-readable GUI strings."""
        if progress_callback is None:
            return
        status = d.get("status", "")
        if status == "downloading":
            downloaded = d.get("downloaded_bytes", 0) or 0
            total      = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            speed      = d.get("speed") or 0
            eta        = d.get("eta")

            def _fmt(b):
                if b >= 1_000_000:
                    return f"{b/1_000_000:.1f} MB"
                elif b >= 1_000:
                    return f"{b/1_000:.0f} KB"
                return f"{b} B"

            if total > 0:
                pct = downloaded / total * 100
                msg = (
                    f"⬇️  Downloading… {pct:.1f}%  "
                    f"({_fmt(downloaded)} / {_fmt(total)})  "
                    f"@ {_fmt(speed)}/s"
                )
                if eta is not None:
                    msg += f"  ETA {eta}s"
            else:
                msg = f"⬇️  Downloading… {_fmt(downloaded)} downloaded"
            progress_callback(msg)

        elif status == "finished":
            progress_callback("✅ Download complete. Converting to MP3...")

        elif status == "error":
            progress_callback("❌ Download error — see console for details.")

    ydl_opts = {
        # Best audio-only stream — download raw, NO postprocessor re-encoding.
        # Conversion is handled below by pydub using the local bundled ffmpeg.
        "format":         "bestaudio/best",
        "outtmpl":        raw_template,   # yt-dlp appends the real extension
        # No postprocessors — we handle conversion ourselves
        "postprocessors": [],
        "progress_hooks": [_yt_progress_hook],
        "quiet":          True,
        "no_warnings":    True,
        # Retry settings for unstable connections
        "retries":        5,
        "fragment_retries": 5,
        "socket_timeout": 30,
    }

    # ── Step 1: Download raw stream ──────────────────────────────────────────
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(f"YouTube download failed:\n{exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unexpected error during download:\n{exc}") from exc

    # Find the raw file yt-dlp just wrote (extension varies: .webm, .m4a, .opus…)
    raw_candidates = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.startswith("audio_raw") and not f.endswith(".part")
    ]
    if not raw_candidates:
        raise RuntimeError(
            "Download appeared to succeed but no raw audio file was found.\n"
            f"Looked in: {folder}"
        )
    raw_path = raw_candidates[0]
    print(f"[INFO] Raw download: {raw_path}")

    # ── Step 2: Convert to MP3 using pydub + local bundled ffmpeg ────────────
    if progress_callback:
        try:
            progress_callback("🔄 Converting to MP3 using local ffmpeg…")
        except Exception:
            pass

    try:
        AudioSegment = _setup_pydub()
        audio = AudioSegment.from_file(raw_path)
        audio.export(final_mp3, format="mp3", bitrate="192k")
        print(f"[INFO] Converted to MP3: {final_mp3}")
    except Exception as exc:
        raise RuntimeError(
            f"Audio conversion to MP3 failed:\n{exc}\n\n"
            "Make sure the local ffmpeg folder is present next to main_gui.py."
        ) from exc
    finally:
        # Clean up the raw download regardless of whether conversion succeeded
        try:
            os.remove(raw_path)
        except Exception:
            pass

    if progress_callback:
        try:
            progress_callback(f"✅ MP3 ready: {final_mp3}")
        except Exception:
            pass

    return final_mp3