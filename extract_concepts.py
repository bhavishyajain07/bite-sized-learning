import os
import ssl
import json
import urllib.request
import trafilatura
from dotenv import load_dotenv
from google import genai

ssl._create_default_https_context = ssl._create_unverified_context

load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ---------- Step A: Fetch and extract clean text from a URL ----------
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
        raise RuntimeError("Could not extract article text.")
    return text


# ---------- Step B: Ask Gemini to find atomic concepts ----------
PROMPT_TEMPLATE = """You are an expert curriculum designer building a "bite-sized learning" course for busy professionals.

Below is the source content for the course. Your job: extract the ATOMIC CONCEPTS that a learner needs to master this topic.

Rules for an atomic concept:
- It is ONE teachable idea — small enough to learn in 5-10 minutes
- It is meaningful on its own, not just a vocabulary word
- It is NOT the whole topic itself (too broad), and NOT a tiny definition (too narrow)
- A learner who masters all the concepts in your list should have a solid grasp of the source material

For each concept, also estimate:
- difficulty: "beginner", "intermediate", or "advanced"
- prerequisites: a list of other concepts (from your own list) that should be learned first. Use [] if none.

Return your answer as a strict JSON array. Each item should look like:
{{
  "name": "Short concept name",
  "definition": "One-sentence definition in plain English",
  "difficulty": "beginner",
  "prerequisites": ["Other concept name"]
}}

Return ONLY the JSON array. No prose, no markdown fences, no explanation.

--- SOURCE CONTENT ---
{source_text}
--- END SOURCE CONTENT ---
"""


def extract_concepts(source_text: str) -> list[dict]:
    prompt = PROMPT_TEMPLATE.format(source_text=source_text)

    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
    )

    raw = response.text.strip()

    # Sometimes models wrap JSON in ```json ... ``` fences. Strip them if present.
    if raw.startswith("```"):
        raw = raw.strip("`")
        # Remove a leading "json" tag if present
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()

    try:
        concepts = json.loads(raw)
    except json.JSONDecodeError as e:
        print("⚠️ Gemini did not return valid JSON. Raw output:")
        print(raw[:1000])
        raise e

    return concepts


# ---------- Step C: Pretty-print results ----------
def print_concepts(concepts: list[dict]) -> None:
    print(f"\n✨ Extracted {len(concepts)} concepts:\n")
    for i, c in enumerate(concepts, start=1):
        prereqs = ", ".join(c["prerequisites"]) if c["prerequisites"] else "none"
        print(f"{i}. {c['name']}  [{c['difficulty']}]")
        print(f"   → {c['definition']}")
        print(f"   prerequisites: {prereqs}\n")


# ---------- Main ----------
if __name__ == "__main__":
    URL = "https://en.wikipedia.org/wiki/Machine_learning"   # change this anytime

    print(f"Fetching: {URL}\n")
    article = fetch_article_text(URL)

    # Keep things small + cheap for the first run
    article = article[:8000]
    print(f"Using first {len(article)} characters of article.\n")

    concepts = extract_concepts(article)
    print_concepts(concepts)