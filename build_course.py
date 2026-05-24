import os
import re
import json
import ssl
import time
import urllib.request
import trafilatura
from collections.abc import Callable
from datetime import datetime
from dotenv import load_dotenv
from google import genai

ssl._create_default_https_context = ssl._create_unverified_context


load_dotenv()  # for local development


def _get_api_key() -> str:
    """
    Get the Gemini API key from either:
    1. Streamlit secrets (when deployed to Streamlit Cloud)
    2. A .env file / environment variable (for local development)
    """
    # Try Streamlit secrets first — only available when running under Streamlit
    try:
        import streamlit as st
        if "GEMINI_API_KEY" in st.secrets:
            return st.secrets["GEMINI_API_KEY"]
    except Exception:
        pass  # Not running in Streamlit, or no secrets file — fall through

    # Fall back to environment variable (loaded from .env locally)
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        raise RuntimeError(
            "GEMINI_API_KEY not found. Set it in .env (local) or "
            "in Streamlit Cloud's secrets (deployed)."
        )
    return key


client = genai.Client(api_key=_get_api_key())
COURSES_DIR = "courses"


# ---------- Fetch ----------
def fetch_article_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        },
    )
    with urllib.request.urlopen(req) as response:
        html = response.read().decode("utf-8", errors="ignore")
    text = trafilatura.extract(html)
    if text is None:
        raise RuntimeError(
            "Could not extract article text. The site may be blocking scrapers "
            "or use heavy JavaScript. Try a different URL."
        )
    return text


def _extract_json(raw: str) -> str:
    """
    Extract a JSON value (array or object) from an LLM response that may
    include markdown fences, leading/trailing prose, or other noise.
    """
    raw = raw.strip()

    # 1. Strip markdown code fences if present
    if raw.startswith("```"):
        # Drop the first fence line (e.g. ```json)
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        # Drop trailing fence
        if "```" in raw:
            raw = raw.rsplit("```", 1)[0]
        raw = raw.strip()

    # 2. Find the JSON value: array [...] or object {...}
    # We locate the first opening bracket and find its matching close
    # by tracking depth — this handles nested braces correctly.
    start = -1
    open_char = ""
    close_char = ""
    for i, ch in enumerate(raw):
        if ch == "[":
            start, open_char, close_char = i, "[", "]"
            break
        if ch == "{":
            start, open_char, close_char = i, "{", "}"
            break
    if start == -1:
        raise ValueError("No JSON array or object found in LLM response.")

    depth = 0
    in_string = False
    escape = False
    end = -1
    for i in range(start, len(raw)):
        ch = raw[i]
        if escape:
            escape = False
            continue
        if ch == "\\":
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == open_char:
            depth += 1
        elif ch == close_char:
            depth -= 1
            if depth == 0:
                end = i
                break

    if end == -1:
        raise ValueError("Unterminated JSON value in LLM response.")

    return raw[start:end + 1]


# ---------- Concept extraction ----------
CONCEPT_PROMPT = """You are an expert curriculum designer building a "bite-sized learning" course for busy professionals.

Extract the ATOMIC CONCEPTS from the source content below.

Rules:
- ONE teachable idea per concept (5-10 min lesson size)
- Meaningful on its own, not a vocabulary word
- Not the whole topic, not a tiny definition
- Aim for 5 to 8 concepts total — quality over quantity

For each concept return:
- name: short concept name
- definition: one-sentence definition
- difficulty: "beginner", "intermediate", or "advanced"
- prerequisites: a list of OTHER concept names from your own list that should be learned first (use [] if none). Use the EXACT same spelling as the names you produce.

CRITICAL: Your entire response must be a single valid JSON array starting with [ and ending with ]. Do NOT include any text before or after the array. Do NOT wrap it in markdown code fences. Do NOT add explanations or comments.

--- SOURCE CONTENT ---
{source_text}
--- END SOURCE CONTENT ---
"""


def extract_concepts(source_text: str) -> list[dict]:
    prompt = CONCEPT_PROMPT.format(source_text=source_text)
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    try:
        return json.loads(_extract_json(response.text))
    except (json.JSONDecodeError, ValueError) as e:
        # Save the raw output so we can inspect what went wrong
        with open("last_failed_response.txt", "w") as f:
            f.write(response.text)
        raise RuntimeError(
            f"Failed to parse Gemini response as JSON: {e}. "
            f"Raw output saved to last_failed_response.txt"
        ) from e


# ---------- Pedagogical sort ----------
def sort_by_prerequisites(concepts: list[dict]) -> list[dict]:
    name_to_concept = {c["name"]: c for c in concepts}
    valid_names = set(name_to_concept.keys())
    for c in concepts:
        c["prerequisites"] = [p for p in c["prerequisites"] if p in valid_names]

    ordered = []
    placed = set()
    remaining = list(concepts)
    while remaining:
        progress = False
        for c in remaining[:]:
            if all(p in placed for p in c["prerequisites"]):
                ordered.append(c)
                placed.add(c["name"])
                remaining.remove(c)
                progress = True
        if not progress:
            ordered.extend(remaining)
            break
    return ordered


# ---------- Lesson generation ----------
LESSON_PROMPT = """You are an expert teacher creating a single bite-sized lesson for a busy professional.

Target learner: smart adult, comfortable thinking, but NEW to this specific topic.
Tone: clear, friendly, like a senior colleague explaining over coffee. No fluff, no condescension, no "in this lesson we will..." filler.

The concept to teach:
- Name: {concept_name}
- Definition: {concept_definition}
- Difficulty: {concept_difficulty}

Use the source content below as the factual ground truth. Do not invent facts that are not supported by it or by widely accepted general knowledge.

Produce a lesson with this exact JSON structure:

{{
  "title": "A short, specific lesson title (max 8 words)",
  "explanation": "200-300 words explaining the concept in plain language. Use concrete language. Build intuition before formalism.",
  "example": "One concrete worked example (2-5 sentences) showing the concept in action. Use real numbers or scenarios where possible.",
  "questions": [
    {{"question": "...", "answer": "...", "type": "recall"}},
    {{"question": "...", "answer": "...", "type": "application"}},
    {{"question": "...", "answer": "...", "type": "reasoning"}}
  ]
}}

CRITICAL: Your entire response must be a single valid JSON array starting with [ and ending with ]. Do NOT include any text before or after the array. Do NOT wrap it in markdown code fences. Do NOT add explanations or comments.

--- SOURCE CONTENT ---
{source_text}
--- END SOURCE CONTENT ---
"""


def generate_lesson(concept: dict, source_text: str) -> dict:
    prompt = LESSON_PROMPT.format(
        concept_name=concept["name"],
        concept_definition=concept["definition"],
        concept_difficulty=concept["difficulty"],
        source_text=source_text,
    )
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )
    return json.loads(_extract_json(response.text))


# ---------- Slug helper ----------
def slugify(name: str) -> str:
    """Turn 'Machine Learning 101!' into 'machine-learning-101'."""
    s = name.lower().strip()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    s = s.strip("-")
    return s or "course"


# ---------- Build course (callable, with optional progress callback) ----------
def build_course(
    url: str,
    course_name: str,
    progress_callback: Callable[[str, float], None] | None = None,
) -> str:
    """
    Build a course and save it. Returns the slug (folder name).
    progress_callback(message, fraction) is called at each step (fraction 0.0-1.0).
    """

    def report(msg: str, frac: float) -> None:
        if progress_callback:
            progress_callback(msg, frac)

    slug = slugify(course_name)
    course_dir = os.path.join(COURSES_DIR, slug)
    os.makedirs(course_dir, exist_ok=True)

    report("Fetching article…", 0.05)
    article = fetch_article_text(url)[:8000]

    report("Extracting concepts…", 0.20)
    concepts = extract_concepts(article)

    report(f"Found {len(concepts)} concepts. Sorting…", 0.30)
    ordered = sort_by_prerequisites(concepts)

    lessons = []
    n = len(ordered)
    for i, concept in enumerate(ordered, start=1):
        frac = 0.30 + 0.65 * (i - 1) / n
        report(f"Generating lesson {i}/{n}: {concept['name']}", frac)
        lesson = generate_lesson(concept, article)
        lessons.append({"day": i, "concept": concept, "lesson": lesson})
        time.sleep(2)  # rate-limit friendly

    course = {
        "name": course_name,
        "slug": slug,
        "source_url": url,
        "created_at": datetime.now().isoformat(timespec="seconds"),
        "concept_count": len(ordered),
        "lessons": lessons,
    }

    with open(os.path.join(course_dir, "course.json"), "w") as f:
        json.dump(course, f, indent=2)

    # Initialize empty progress
    with open(os.path.join(course_dir, "progress.json"), "w") as f:
        json.dump({"current_day": 1, "completed": [], "ratings": {}}, f, indent=2)

    report("✅ Course ready!", 1.0)
    return slug


# ---------- Helpers used by the app ----------
def list_courses() -> list[dict]:
    """Return a list of {name, slug, lesson_count} for every existing course."""
    if not os.path.exists(COURSES_DIR):
        return []
    out = []
    for slug in sorted(os.listdir(COURSES_DIR)):
        course_path = os.path.join(COURSES_DIR, slug, "course.json")
        if os.path.exists(course_path):
            with open(course_path) as f:
                course = json.load(f)
            out.append(
                {
                    "name": course.get("name", slug),
                    "slug": slug,
                    "lesson_count": len(course.get("lessons", [])),
                    "created_at": course.get("created_at", ""),
                }
            )
    return out


def load_course(slug: str) -> dict:
    with open(os.path.join(COURSES_DIR, slug, "course.json")) as f:
        course = json.load(f)
    course.setdefault("slug", slug)
    course.setdefault("name", slug.replace("-", " ").title())
    return course


def load_progress(slug: str) -> dict:
    path = os.path.join(COURSES_DIR, slug, "progress.json")
    if not os.path.exists(path):
        return {"current_day": 1, "completed": [], "ratings": {}}
    with open(path) as f:
        return json.load(f)


def save_progress(slug: str, progress: dict) -> None:
    path = os.path.join(COURSES_DIR, slug, "progress.json")
    with open(path, "w") as f:
        json.dump(progress, f, indent=2)


# ---------- CLI for backward compatibility ----------
if __name__ == "__main__":
    URL = "https://en.wikipedia.org/wiki/Machine_learning"
    NAME = "Machine Learning"
    slug = build_course(
        URL, NAME, progress_callback=lambda m, f: print(f"[{f:.0%}] {m}")
    )
    print(f"Saved to courses/{slug}/")
