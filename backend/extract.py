"""DRIFTIQ MVP — Structured knowledge extraction.
Turns a raw lecture transcript into structured notes via the configured LLM.
Now supports professor bookmarks ("mark this moment") and a 3-minute recap.
"""
from typing import List, Dict, Any
from llm import call_llm


SYSTEM_PROMPT = """You are DRIFTIQ, an expert educational content structurer.

You will be given the raw transcript of a classroom lecture. Optionally you will
also be given the timestamps at which the professor tapped a "mark this moment"
button — these are things they wanted flagged as especially important.

Your job is to convert everything into structured lecture notes as a JSON object.

RULES:
- Output ONLY a single JSON object, nothing else.
- Every extracted item must be grounded in something the transcript actually says.
- If the transcript does not contain something, leave that array empty — do NOT invent.
- Keep the phrasing concise and student-friendly.
- Preserve the professor's terminology.
- For each bookmarked timestamp, find the nearby content in the transcript and
  produce a short "highlight" for it.

JSON SCHEMA (return exactly this shape):
{
  "subject": string,                     // best-guess subject / course area
  "topics": [
    { "title": string, "summary": string }
  ],
  "definitions": [
    { "term": string, "definition": string }
  ],
  "formulas": [
    { "name": string, "expression": string, "explanation": string }
  ],
  "examples": [
    { "concept": string, "example": string }
  ],
  "assignments": [
    { "description": string, "due": string }
  ],
  "highlights": [
    { "timestamp": string, "label": string, "content": string }
  ],
  "recap": string,                       // 3-minute recap for a student who missed class
  "key_takeaways": [ string ]
}
"""


def _fmt_ts(seconds: float) -> str:
    """Convert seconds → mm:ss string."""
    s = int(round(seconds))
    return f"{s // 60:02d}:{s % 60:02d}"


def extract_notes(transcript: str, moments: List[Dict[str, Any]] = None) -> dict:
    """Run the LLM on a transcript (+ optional professor bookmarks) → structured notes."""
    moments = moments or []
    bookmarks_block = ""
    if moments:
        bookmarks_block = "\n\n--- PROFESSOR BOOKMARKS (moments they marked as important) ---\n"
        for m in moments:
            ts = _fmt_ts(m.get("t", 0))
            label = m.get("label", "").strip() or "(no label)"
            bookmarks_block += f"- {ts} — {label}\n"

    user_prompt = (
        "Here is the lecture transcript. Extract the structured notes as instructed.\n\n"
        "--- TRANSCRIPT START ---\n"
        f"{transcript}\n"
        "--- TRANSCRIPT END ---"
        f"{bookmarks_block}\n"
    )
    result = call_llm(SYSTEM_PROMPT, user_prompt)
    # Guarantee every expected key exists so the frontend never crashes
    for key, default in [
        ("subject", "Unknown"),
        ("topics", []),
        ("definitions", []),
        ("formulas", []),
        ("examples", []),
        ("assignments", []),
        ("highlights", []),
        ("recap", ""),
        ("key_takeaways", []),
    ]:
        result.setdefault(key, default)
    return result


def notes_to_markdown(notes: dict) -> str:
    """Render structured notes as a Markdown document."""
    md = [f"# {notes.get('subject', 'Lecture')} — Lecture Notes\n"]

    if notes.get("recap"):
        md.append("## 3-Minute Recap (for students who missed class)\n")
        md.append(notes["recap"])
        md.append("")

    if notes.get("highlights"):
        md.append("## ★ Professor Highlights\n")
        for h in notes["highlights"]:
            ts = h.get("timestamp", "")
            label = h.get("label", "")
            content = h.get("content", "")
            md.append(f"- **[{ts}]** {label}: {content}" if label else f"- **[{ts}]** {content}")
        md.append("")

    if notes.get("topics"):
        md.append("## Topics\n")
        for t in notes["topics"]:
            md.append(f"### {t.get('title','')}\n{t.get('summary','')}\n")

    if notes.get("definitions"):
        md.append("## Definitions\n")
        for d in notes["definitions"]:
            md.append(f"- **{d.get('term','')}** — {d.get('definition','')}")
        md.append("")

    if notes.get("formulas"):
        md.append("## Formulas\n")
        for f in notes["formulas"]:
            md.append(f"- **{f.get('name','')}**: `{f.get('expression','')}` — {f.get('explanation','')}")
        md.append("")

    if notes.get("examples"):
        md.append("## Examples\n")
        for e in notes["examples"]:
            md.append(f"- **{e.get('concept','')}** — {e.get('example','')}")
        md.append("")

    if notes.get("assignments"):
        md.append("## Assignments\n")
        for a in notes["assignments"]:
            due = f" (due {a['due']})" if a.get("due") else ""
            md.append(f"- {a.get('description','')}{due}")
        md.append("")

    if notes.get("key_takeaways"):
        md.append("## Key Takeaways\n")
        for k in notes["key_takeaways"]:
            md.append(f"- {k}")
        md.append("")

    return "\n".join(md)
