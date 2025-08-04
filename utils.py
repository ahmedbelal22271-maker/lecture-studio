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

def prepare_contextual_prompt(chunk, previous_chunk=None, include_exam=True, translate_to_english=False):
    system_header = "You are an academic assistant."

    if translate_to_english:
        system_header += (
            " Translate the following Arabic lecture chunk into English academic notes."
            " Preserve technical English terms such as 'NumPy', 'Pandas', 'model', etc."
        )
    else:
        system_header += " Generate structured Markdown notes from a university lecture transcript."

    section_instructions = [
        "### 🧠 Key Takeaways",
        "### 📘 Definitions & Terms",
        "### 🔍 Inferred Importance"
    ]

    if include_exam:
        section_instructions += [
            "### 🎯 Exam Alerts",
            "### 📝 Potential Exam Questions"
        ]

    context_instruction = ""
    if previous_chunk:
        context_instruction = f"\n\nContext from previous segment:\n{previous_chunk.strip()}"

    prompt = f"""[INST] <<SYS>>
{system_header}
<</SYS>>

--- Transcript Chunk Start ---
{chunk.strip()}
--- End ---
{context_instruction}

{chr(10).join(section_instructions)}
[/INST]
"""
    return prompt
