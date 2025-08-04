# mistral_notes.py (Updated with Translation Option + Debug Mode + CLI Progress Bar)

import os
from llama_cpp import Llama
from utils import (
    split_into_chunks,
    score_chunk_for_importance,
    extract_key_summary,
    prepare_contextual_prompt
)
from output_manager import save_notes_markdown
from tqdm import tqdm  # NEW: Progress bar for terminal

# Model configuration
MODEL_PATH = "mistral-7b-instruct-v0.1.Q4_K_M.gguf"
CTX_SIZE = 4096
MAX_TOKENS = 1536

# Load the model once
llm = Llama(model_path=MODEL_PATH, n_ctx=CTX_SIZE)

def generate_notes_from_transcript(
    transcript_text,
    course,
    lecture,
    rerank=True,
    include_exam=True,
    debug=False  # Optional debugging toggle
):
    """
    Processes transcript text into structured academic notes using Mistral LLM.

    Args:
        transcript_text (str): Raw Arabic lecture transcript
        course (str): Course name for saving output
        lecture (str): Lecture title for saving output
        rerank (bool): Whether to sort notes by importance
        include_exam (bool): Include exam alerts and questions
        debug (bool): Enable debug messages during processing

    Returns:
        list: List of note dictionaries with content and scores
    """
    chunks = split_into_chunks(transcript_text)
    notes = []
    summaries = []

    # Wrap loop in tqdm progress bar
    for i, chunk in enumerate(tqdm(chunks, desc="[MISTRAL] Generating Notes", unit="chunk")):
        if debug:
            print(f"[MISTRAL] Processing chunk {i+1}/{len(chunks)}...")

        # Prepare prompt based on current and previous chunk context
        if i == 0:
            prompt = prepare_contextual_prompt(
                chunk,
                previous_chunk=None,
                include_exam=include_exam,
                translate_to_english=True
            )
        else:
            previous_summary = summaries[-1] if summaries else None
            prompt = prepare_contextual_prompt(
                chunk,
                previous_chunk=previous_summary,
                include_exam=include_exam,
                translate_to_english=True
            )

        # Call the local model with the prepared prompt
        output = llm(prompt, max_tokens=MAX_TOKENS)
        result = output["choices"][0].get("text") or output["choices"][0].get("content", "")
        result = result.strip()

        # Score and store the result
        score = score_chunk_for_importance(result)
        notes.append({"index": i+1, "content": result, "score": score})

        # Extract a compact summary for linking to next chunk
        summaries.append(extract_key_summary(result))

    # Sort chunks if re-ranking is enabled
    if rerank:
        notes = sorted(notes, key=lambda n: n["score"], reverse=True)

    # Join all notes and export
    final_output = "\n\n".join([f"## Chunk {n['index']}\n\n{n['content']}" for n in notes])
    save_notes_markdown([(None, n["content"]) for n in notes], course, lecture)

    return notes
