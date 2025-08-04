# utils.py

import re

def split_into_chunks(transcript_text, max_chunk_size=1800):
    words = transcript_text.split()
    chunks = []
    current_chunk = []

    for word in words:
        current_chunk.append(word)
        if len(current_chunk) >= max_chunk_size:
            chunks.append(" ".join(current_chunk))
            current_chunk = []

    if current_chunk:
        chunks.append(" ".join(current_chunk))

    return chunks

def extract_key_summary(note_text, max_bullets=3):
    """
    Extract a short bullet-point summary from Key Takeaways section
    """
    pattern = r"(?<=### \*\*Key Takeaways\*\*)([\s\S]+?)(?=(###|$))"
    match = re.search(pattern, note_text)
    if not match:
        return ""

    raw = match.group(1)
    bullets = re.findall(r"[-\*]\s+(.+)", raw)
    summary = bullets[:max_bullets]
    return "\n".join(f"- {b}" for b in summary)

def score_chunk_for_importance(note_text):
    """
    Score each chunk based on how many Exam Alerts, Definitions, and Questions it includes
    """
    score = 0
    score += note_text.count("🎯") * 3
    score += note_text.count("📘") * 2
    score += note_text.count("📝") * 3
    score += note_text.count("- ")      # Key Takeaways
    return score

def prepare_contextual_prompt(chunk, context=None):
    base_instruction = f"""
[INST] <<SYS>>
You are an academic assistant helping university students prepare for exams.

Your job is to read lecture transcripts and generate organized academic notes in Markdown format.

Return your response in the following sections:
- 🎯 Exam Alerts
- 🧠 Key Takeaways
- 📘 Definitions & Terms
- 🔍 Inferred Importance
- 📝 Potential Exam Questions

Only return content from the transcript. Do not explain Markdown itself.
<</SYS>>
"""
    if context:
        base_instruction += f"\nHere is some important context from earlier in the lecture or previous lectures:\n---\n{context}\n---\n"

    base_instruction += f"\nLecture Transcript:\n{chunk}\n\nGenerate the academic notes now.\n[/INST]"
    return base_instruction.strip()
