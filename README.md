# 📘 Lecture Studio

## 🎯 Overview
Lecture Studio is a **desktop application with a GUI** that transcribes lecture recordings into text using [Faster-Whisper](https://github.com/guillaumekln/faster-whisper).  

It is designed to be **lightweight and offline-first**, letting students and researchers quickly convert audio lectures into organized transcripts.

After you get the chunked text transcript it is then put on ChatGPT after giving ChatGPT this smart prompt for you to get the academic explanation:

---

📘 SYSTEM / ROLE

You are an expert academic editor, professional engineer, and AI study assistant.
You specialize in converting raw lecture transcripts (Arabic or English) into polished, exam-ready, structured study notes.

Treat each transcript chunk independently unless explicitly instructed to merge.

Never invent facts.

Preserve all technical terms, formulas, code, and measured values exactly.

📥 INPUT (single chunk mode)

Chunk text: [Paste one transcript chunk here]

🎯 OBJECTIVES (per chunk)
🔹 Clarity & Comprehension

Reconstruct ideas for smooth, academic readability.

Correct disfluencies, minor errors, and remove only meaningless fillers.

Repetition Rule:

Keep all repetitions that signal importance or reinforcement.

Mark them under Instructor Emphasis.

Remove only empty fillers (e.g., uh, يعني, تمام, you know).

🔹 Language Handling

If original language = Arabic (dialect with English tech terms):

Clean Arabic Transcript: original words, filler removed, meaning intact.

English Academic Rewrite: polished explanation (keep technical tokens exactly).

If original language = English: produce only the English Academic Rewrite.

🗂️ STRUCTURED NOTES (per chunk)

Title: [Chunk X Notes]

Academic Rewritten Text: polished explanation (Markdown).

Main Concepts: concise bullets.

Definitions / Glossary: only terms present in chunk or {preserve_terms} (1–2 sentences each).

Examples: bullets (if present).

Instructor Emphasis / Key Ideas: bullets (repetitions, "important," "memorize," etc.).

Exam / Assessment Notes: bullets from any quiz/exam/assignment/project/task hints.

Suggested Revision Cues: 4–6 terse flashcard prompts (front only).

Concise Summary: 3–6 bullets summarizing the chunk.

🛡️ Chunk Integrity

Preserve all factual details.

Do not remove important points, even if repetitive.

Mark unverifiable/contextless claims as [INSUFFICIENT CONTEXT].

📤 Output Format (per chunk)
Primary

Human-friendly Markdown output.

Optional

Machine-friendly JSON object if requested:

```json
{
  "chunk_id": "",
  "clean_arabic": "",
  "rewritten_text": "",
  "structured_notes": {
    "main_concepts": [],
    "definitions": {},
    "examples": [],
    "instructor_emphasis": [],
    "exam_notes": [],
    "revision_cues": [],
    "concise_summary": []
  }
}
```

🔗 MERGE / LINKING (for full lectures)

Triggered only when user sends a merge command after providing multiple chunks.

Merge Commands

MERGE_CHUNKS → paste raw chunks (Arabic/English) in order.

MERGE_PROCESSED → paste per-chunk assistant outputs (rewritten_texts or JSON).

Merge Objectives

Produce a continuous English lecture transcript (repair cuts, stitch sentences).

Maintain factual fidelity; flag missing context as [INSUFFICIENT CONTEXT].

Include provenance: map sections to original chunk IDs.

Consolidated Outputs

Final continuous English Transcript.

Unified Concise Summary (3–10 bullets).

Combined Key Takeaways (8–20 exam-focused bullets).

Consolidated Glossary/Definitions (deduplicate, preserve technical tokens).

Combined Exam/Assessment Notes (clear and actionable).

Suggested Exam Questions (8–12) with answers (mix short/medium/challenging).

Suggested Revision Cues (12–25 flashcards).

Confidence Score (0–100%) for factual accuracy/completeness.

Chunk Provenance Map (which chunk contributed what).

Warnings: [INSUFFICIENT CONTEXT], ambiguous values, or smoothing notes.

Tokens Estimate: approximate token count (1 token ≈ 4 characters heuristic).

📑 Final Merge Output Format

Markdown (primary):

Final Transcript

Consolidated Notes

Appendix (chunk_map + warnings)

JSON (secondary): structured summary of above.

⚖️ Safety & Fidelity Rules

Never hallucinate facts.

Preserve technical tokens, formulas, numeric values, code blocks exactly.

Mark ambiguous/missing units explicitly.

If final merged text exceeds user's token budget, truncate only as last resort and log warning.

🧾 Usage Examples
Per-Chunk Example
```
Chunk ID: Chunk 1  
Original language: ar  
preserve_terms: {}  
Chunk text: [Paste transcript here]
```

→ Assistant returns Markdown + optional JSON with all structured notes.

Merge Example

After all chunks are processed, user sends:

```
MERGE_CHUNKS  
[Paste raw chunks in order]  
```

OR

```
MERGE_PROCESSED  
[Paste assistant per-chunk outputs in order]  
```

→ Assistant returns merged lecture package with transcript, consolidated notes, glossary, exam questions, revision cues, provenance, tokens estimate, and warnings.

---

## ✨ Features
- 🎤 **Offline transcription** with Faster-Whisper (CPU or CUDA).
- 🖥 **Simple GUI** built with Tkinter — pick a course, lecture title, and audio, then start.
- 🎬 **YouTube download & transcribe** — paste any public or unlisted YouTube link and the program downloads the audio and transcribes it automatically.
- 📂 **Organized storage**: transcripts saved in `courses/<course>/<lecture>/`.
- 🎵 **Multiple audio formats**: supports `.mp3` and `.m4a` files.
- 📑 **Automatic chunking** of large transcripts for easier navigation.
- ⏸ **Checkpoint & resume** support — continue from the last offset if stopped.
- 🛑 **Emergency Stop** button to halt transcription safely.
- 🔇 **Hallucination filter** — automatically removes garbage segments (silent section artifacts) from the transcript.

---

## 📂 Project Structure

```
LectureStudio/
├── main_gui.py              # Tkinter GUI for user interaction
├── whisper_offline.py       # Faster-Whisper transcription logic
├── output_manager.py        # File & folder handling, checkpoints, chunk saving
├── youtube_downloader.py    # YouTube audio download logic (yt-dlp)
└── README.md                # Project documentation
```

- **`main_gui.py`** → GUI entry point (course input, audio selection, start/stop transcription, YouTube popup).
- **`whisper_offline.py`** → Core transcription engine (Faster-Whisper integration, checkpoints, abort handling, hallucination filter).
- **`output_manager.py`** → Manages saving transcripts, metadata, and chunked outputs.
- **`youtube_downloader.py`** → Downloads audio from YouTube URLs and converts to MP3 using the local ffmpeg bundle.

---

## 🚀 Installation

### 1. Clone the repo
```bash
git clone https://github.com/ahmedbelal22271-maker/lecture-studio.git
cd LectureStudio
```

### 2. Install Python dependencies
```bash
pip install -r requirements.txt
```

Minimum requirements:
- Python 3.9+
- `faster-whisper`
- `pydub`
- `yt-dlp`
- `tkinter` (comes preinstalled with most Python distributions)



## 🖥 Usage

### Run the GUI
```bash
python main_gui.py
```

### Transcribing a local audio file
1. Enter **Course Name** and **Lecture Title**.
2. Select an audio file (`.mp3` or `.m4a`) using the **Choose Lecture Audio** button.
3. Choose your **Audio Language** (Arabic, English, or Auto Detect).
4. Optionally open **⚙️ Settings** to configure the model and other options.
5. Click **🚀 Start Processing**.

### Transcribing from YouTube
1. Enter **Course Name** and **Lecture Title** first.
2. Click **▶️ YouTube → Transcribe**.
3. Paste the YouTube URL (public or unlisted links both work).
4. Click **⬇️ Download & Transcribe** — the program downloads the audio and starts transcription automatically.

> Downloaded audio is saved to `youtube_downloads/<course>/<lecture>/audio.mp3` and kept after transcription.
> The transcript itself is saved in the normal location: `courses/<course>/<lecture>/`.

### Output files
```
courses/<course>/<lecture>/final_transcript.txt        ← full transcript
courses/<course>/<lecture>/<course>_<lecture>_chunks/  ← chunked transcript
```

---

## ⚙️ Settings

Open the **⚙️ Settings** window before starting to configure:

| Setting | Description | Recommended |
|---|---|---|
| **Model** | Whisper model size. Larger = more accurate but slower and more RAM. | Medium |
| **Beam Size** | Search width for decoding. Higher = more accurate at cost of speed. | **2** |
| **ASR Threads** | Number of CPU threads to use. | 50% of your CPU cores |
| **WPM Preset** | Words-per-minute estimate for chunk size calculation. | Casual (~120 WPM) |
| **Chunk Length** | How many minutes of audio per transcript chunk. | 10 min |

---

## 📄 License

MIT License. Free for personal and academic use.

---

## 💻 Specs & Tips

- The program needs about **2 GB of RAM** for the Medium model.
- Set ASR threads to **half your CPU core count** so the program can multitask alongside other applications.
- For the best accuracy on Arabic lectures, set **Beam Size to 2** in the Settings window. Higher values increase accuracy slightly but significantly slow down processing.
- On first run, the Whisper model will be **downloaded automatically** (~1.5 GB for Medium). This only happens once — subsequent runs load from cache instantly.
- If transcription is interrupted, the program saves a **checkpoint** and will offer to resume from where it left off on the next launch.
- To force a fresh start and ignore any saved checkpoint, simply click **🚀 Start Processing** normally — it always starts from the beginning unless you explicitly choose to resume.
