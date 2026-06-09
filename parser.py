"""
Parsers for AI-900 mock test files.

Supported formats:
  - DOCX tutor edition (paragraphs + answer tables)
  - PDF explanation files (Correct Answer: X) ...)
"""

import re
from pathlib import Path


# ── DOCX tutor parser ─────────────────────────────────────────────────────────

def parse_tutor_docx(path: Path) -> list[dict]:
    from docx import Document
    from docx.oxml.ns import qn

    doc = Document(path)
    body = doc.element.body

    questions = []
    current: dict | None = None

    def _cell_text(tbl_el) -> str:
        return "".join(
            n.text or ""
            for n in tbl_el.iter()
            if n.tag.endswith("}t")
        ).strip()

    for child in body:
        tag = child.tag.split("}")[-1]

        if tag == "p":
            text = "".join(
                n.text or "" for n in child.iter() if n.tag.endswith("}t")
            ).strip()
            if not text:
                continue

            # New question block
            if re.match(r"^Q\d+\s", text):
                if current and _is_complete(current):
                    questions.append(current)
                current = {"question": "", "option_a": "", "option_b": "",
                           "option_c": "", "option_d": "", "correct_answer": ""}
                continue

            if current is None:
                continue

            # English question text
            if text.startswith("EN  ") or text.startswith("EN\t"):
                current["question"] = text[3:].strip()
                continue

            # Options
            m = re.match(r"^([A-D])\)\s*(.*)", text, re.DOTALL)
            if m:
                letter = m.group(1)
                value = m.group(2).strip()
                current[f"option_{letter.lower()}"] = value
                continue

        elif tag == "tbl":
            if current is None:
                continue
            cell = _cell_text(child)
            # "Answer  X — ..."
            m = re.match(r"Answer\s+([A-D])\b", cell)
            if m:
                current["correct_answer"] = m.group(1)

    # Last question
    if current and _is_complete(current):
        questions.append(current)

    return questions


def _is_complete(q: dict) -> bool:
    return bool(
        q.get("question")
        and q.get("option_a")
        and q.get("option_b")
        and q.get("correct_answer")
    )


# ── PDF explanation parser ────────────────────────────────────────────────────

def parse_explanation_pdf(path: Path) -> list[dict]:
    import pdfplumber

    lines = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            if text:
                lines.extend(text.splitlines())

    questions = []
    current: dict | None = None
    collecting_question = False
    question_buf: list[str] = []

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # "Question N" header
        if re.match(r"^Question\s+\d+$", line):
            if current and _is_complete(current):
                questions.append(current)
            current = {"question": "", "option_a": "", "option_b": "",
                       "option_c": "", "option_d": "", "correct_answer": ""}
            collecting_question = False
            question_buf = []
            i += 1
            continue

        if current is None:
            i += 1
            continue

        # "Question: ..." (the actual question text)
        if line.startswith("Question:"):
            collecting_question = True
            question_buf = [line[len("Question:"):].strip()]
            i += 1
            continue

        if collecting_question:
            # Stop collecting when we hit an option or Correct Answer
            if re.match(r"^[A-D]\)", line) or line.startswith("Correct Answer"):
                current["question"] = " ".join(question_buf).strip()
                collecting_question = False
                # Don't increment — reprocess this line
            else:
                question_buf.append(line)
                i += 1
                continue

        # Options A) / B) / C) / D)
        m = re.match(r"^([A-D])\)\s*(.*)", line)
        if m:
            letter = m.group(1)
            value = m.group(2).strip()
            current[f"option_{letter.lower()}"] = value
            i += 1
            continue

        # Correct Answer — skip multi-answer questions
        if line.startswith("Correct Answer:"):
            # e.g. "Correct Answer: B) Presence penalty"
            # multi: "Correct Answer: C) ... and D) ..."
            m = re.match(r"Correct Answer:\s*([A-D])\)", line)
            if m:
                # Single correct answer
                current["correct_answer"] = m.group(1)
            # else: multi-answer → leave correct_answer empty → will be filtered
            i += 1
            continue

        # "Correct Answer: A) Yes" on separate line after wrapping
        if re.match(r"^([A-D])\)\s+", line) and not current.get("correct_answer"):
            pass  # already handled above

        i += 1

    if current and _is_complete(current):
        questions.append(current)

    return questions


# ── Deduplication ─────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    return re.sub(r"\s+", " ", text.lower().strip())


def deduplicate(questions: list[dict]) -> list[dict]:
    seen: set[str] = set()
    unique = []
    for q in questions:
        key = _normalize(q["question"])
        if key not in seen:
            seen.add(key)
            unique.append(q)
    return unique


# ── Public entry point ────────────────────────────────────────────────────────

def parse_file(path: Path) -> list[dict]:
    suffix = path.suffix.lower()
    name = path.name.lower()

    if suffix == ".docx":
        return parse_tutor_docx(path)
    elif suffix == ".pdf":
        return parse_explanation_pdf(path)
    raise ValueError(f"Qo'llab-quvvatlanmaydigan format: {suffix}")
