"""
youtube_downloader.py
---------------------
Handles all YouTube download logic for Lecture Studio.

Folder structure created:
    youtube_downloads/
        <course>/
            <lecture>/
                audio.m4a

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
    progress_callback=None,   # callable(str) → updates GUI status label
) -> str:
    """
    Download the audio track of a YouTube video (public or unlisted) as M4A.

    Parameters
    ----------
    url               : Full YouTube URL (regular, short, or unlisted)
    course            : Course name  — used as the parent folder
    lecture           : Lecture title — used as the sub-folder
    progress_callback : Optional callable that receives progress strings for the GUI

    Returns
    -------
    str  : Absolute path to the downloaded audio.m4a file

    Raises
    ------
    RuntimeError  : If yt-dlp is not installed
    RuntimeError  : If the download fails for any reason
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

    # yt-dlp writes <outtmpl>.m4a (or remuxes to m4a via postprocessor)
    output_template = os.path.join(folder, "audio")  # yt-dlp appends extension
    final_path      = os.path.join(folder, "audio.mp3")

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

            # Format bytes nicely
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
            progress_callback("✅ Download complete. Processing audio...")

        elif status == "error":
            progress_callback("❌ Download error — see console for details.")

    ydl_opts = {
        # Best audio-only stream, prefer m4a/aac container
        "format":           "bestaudio/best",
        "outtmpl":          output_template,
        # Remux to m4a if not already in that container (no re-encoding)
        "postprocessors": [{
            "key":            "FFmpegExtractAudio",
            "preferredcodec": "mp3",
        }],
        "progress_hooks":   [_yt_progress_hook],
        "quiet":            True,   # suppress yt-dlp console spam
        "no_warnings":      True,
        # Retry settings for unstable connections
        "retries":          5,
        "fragment_retries": 5,
        "socket_timeout":   30,
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            ydl.download([url])
    except yt_dlp.utils.DownloadError as exc:
        raise RuntimeError(f"YouTube download failed:\n{exc}") from exc
    except Exception as exc:
        raise RuntimeError(f"Unexpected error during download:\n{exc}") from exc

    if not os.path.isfile(final_path):
        # yt-dlp sometimes writes .webm or other formats when m4a isn't available;
        # look for any audio file in the folder as a fallback.
        candidates = [
            f for f in os.listdir(folder)
            if f.startswith("audio") and not f.endswith(".part")
        ]
        if candidates:
            final_path = os.path.join(folder, candidates[0])
        else:
            raise RuntimeError(
                "Download appeared to succeed but no audio file was found.\n"
                f"Looked in: {folder}"
            )

    return final_path