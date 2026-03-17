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
    Uses the same local ffmpeg that works reliably for local file conversion.
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
    course_safe  = _safe_folder_name(course)
    lecture_safe = _safe_folder_name(lecture)
    folder = os.path.join(YOUTUBE_DOWNLOADS_DIR, course_safe, lecture_safe)
    return os.path.join(folder, "audio.mp3")


def _unique_audio_filename(folder: str) -> str:
    """
    Return a filename like audio.mp3, audio_1.mp3, audio_2.mp3 ...
    that does not yet exist in folder.
    This prevents queue downloads for the same course/lecture from
    overwriting each other before the first one is transcribed.
    """
    candidate = os.path.join(folder, "audio.mp3")
    if not os.path.exists(candidate):
        return candidate
    i = 1
    while True:
        candidate = os.path.join(folder, f"audio_{i}.mp3")
        if not os.path.exists(candidate):
            return candidate
        i += 1


def _find_raw_file(folder: str) -> str:
    """Return the path of the raw downloaded file in folder, or raise."""
    candidates = [
        os.path.join(folder, f)
        for f in os.listdir(folder)
        if f.startswith("raw_") and not f.endswith(".part")
    ]
    if not candidates:
        raise RuntimeError(
            "Download appeared to succeed but no raw file was found.\n"
            f"Looked in: {folder}"
        )
    return candidates[0]


def download_youtube_audio(
    url: str,
    course: str,
    lecture: str,
    progress_callback=None,
) -> str:
    """
    Download audio from a YouTube video (public or unlisted) and save as MP3.

    Download strategy — tried in order until one succeeds:

    Attempt 1 — Progressive MP4  (most reliable, no fragmentation)
        Format: best[ext=mp4][vcodec!=none][acodec!=none]
        A single non-DASH file with both video and audio already muxed.
        YouTube always has at least one of these (usually 360p or 480p).
        Audio is perfectly synced — no gaps, no silent sections.
        We then extract and convert the audio track using pydub + local ffmpeg.

    Attempt 2 — Any MP4  (fallback)
        Format: best[ext=mp4]/mp4
        Catches edge cases where attempt 1 format string is not matched.

    Attempt 3 — Any format  (last resort)
        Format: best
        For videos with no MP4 available at all.

    In all cases: NO yt-dlp postprocessors — conversion is done by pydub
    using the local bundled ffmpeg to guarantee audio quality.
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

    final_mp3 = _unique_audio_filename(folder)

    # Clean up any leftover raw files from previous failed attempts
    for fname in os.listdir(folder):
        if fname.startswith("raw_"):
            try:
                os.remove(os.path.join(folder, fname))
            except Exception:
                pass

    raw_template = os.path.join(folder, "raw_%(id)s.%(ext)s")

    def _yt_progress_hook(d):
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
                msg = (f"⬇️  Downloading… {pct:.1f}%  "
                       f"({_fmt(downloaded)} / {_fmt(total)})  "
                       f"@ {_fmt(speed)}/s")
                if eta is not None:
                    msg += f"  ETA {eta}s"
            else:
                msg = f"⬇️  Downloading… {_fmt(downloaded)} downloaded"
            progress_callback(msg)
        elif status == "finished":
            progress_callback("✅ Download complete. Converting to MP3…")
        elif status == "error":
            progress_callback("❌ Download error — see console for details.")

    # Format selector priority list — progressive MP4 first
    FORMAT_ATTEMPTS = [
        # 1st choice: progressive MP4 — single file, no fragmentation, guaranteed sync
        "best[ext=mp4][vcodec!=none][acodec!=none]",
        # 2nd choice: any MP4
        "best[ext=mp4]/mp4",
        # 3rd choice: anything available
        "best",
    ]

    raw_path = None
    last_error = None

    for fmt in FORMAT_ATTEMPTS:
        # Clean up before each attempt
        for fname in os.listdir(folder):
            if fname.startswith("raw_"):
                try:
                    os.remove(os.path.join(folder, fname))
                except Exception:
                    pass

        ydl_opts = {
            "format":           fmt,
            "outtmpl":          raw_template,
            "postprocessors":   [],          # no re-encoding by yt-dlp
            "progress_hooks":   [_yt_progress_hook],
            "quiet":            True,
            "no_warnings":      True,
            "retries":          5,
            "fragment_retries": 10,          # more retries for fragmented streams
            "socket_timeout":   30,
        }

        try:
            print(f"[INFO] Trying format: {fmt}")
            if progress_callback:
                try:
                    label = "progressive MP4" if "vcodec" in fmt else ("MP4" if "mp4" in fmt else "best available")
                    progress_callback(f"⬇️  Connecting… (trying {label} format)")
                except Exception:
                    pass

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                ydl.download([url])

            raw_path = _find_raw_file(folder)
            print(f"[INFO] Downloaded: {raw_path}")
            break  # success — stop trying formats

        except Exception as exc:
            last_error = exc
            print(f"[WARNING] Format {fmt!r} failed: {exc}")
            continue

    if raw_path is None:
        raise RuntimeError(
            f"All download format attempts failed.\n"
            f"Last error: {last_error}"
        )

    # ── Convert to MP3 using pydub + local bundled ffmpeg ────────────────────
    if progress_callback:
        try:
            progress_callback("🔄 Extracting and converting audio to MP3…")
        except Exception:
            pass

    try:
        AudioSegment = _setup_pydub()
        print(f"[INFO] Converting {raw_path} → {final_mp3}")
        audio = AudioSegment.from_file(raw_path)
        audio.export(final_mp3, format="mp3", bitrate="192k")
        print(f"[INFO] MP3 saved: {final_mp3}")
    except Exception as exc:
        raise RuntimeError(
            f"Audio conversion to MP3 failed:\n{exc}\n\n"
            "Make sure the ffmpeg-8.0-essentials_build folder is next to main_gui.py."
        ) from exc
    finally:
        try:
            os.remove(raw_path)
        except Exception:
            pass

    if progress_callback:
        try:
            progress_callback(f"✅ Done! MP3 ready: {final_mp3}")
        except Exception:
            pass


    return final_mp3