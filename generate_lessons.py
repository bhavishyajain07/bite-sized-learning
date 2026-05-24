import os
import json
import ssl
import urllib.request
import trafilatura
from dotenv import load_dotenv
from google import genai
ssl._create_default_https_context = ssl._create_unverified_context
load_dotenv()
client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))


# ---------- Reused from Step 3 ----------
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


def _strip_json_fences(raw: str) -> str:
    raw = raw.strip()
    if raw.startswith("```"):
        raw = raw.strip("`")
        if raw.lower().startswith("json"):
            raw = raw[4:]
        raw = raw.strip()
    return raw


CONCEPT_PROMPT = """You are an expert curriculum designer building a "bite-sized learning" course for busy professionals.

Extract the ATOMIC CONCEPTS from the source content below. Rules:
- ONE teachable idea per concept (5-10 min lesson size)
- Meaningful on its own, not a vocabulary word
- Not the whole topic, not a tiny definition

For each concept return: name, one-sentence definition, difficulty (beginner/intermediate/advanced), prerequisites (other concept names from your own list, or []).

Return ONLY a JSON array. No prose, no markdown.

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
    return json.loads(_strip_json_fences(response.text))


# ---------- New: lesson generator ----------
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
    {{
      "question": "An active-recall question that requires thinking, not just looking up a definition.",
      "answer": "A concise answer (1-3 sentences).",
      "type": "recall"
    }},
    {{
      "question": "An application question: ask the learner to apply the concept to a new situation.",
      "answer": "A concise answer.",
      "type": "application"
    }},
    {{
      "question": "A 'why' question that probes deeper understanding or a common misconception.",
      "answer": "A concise answer.",
      "type": "reasoning"
    }}
  ]
}}

Return ONLY the JSON object. No prose, no markdown fences.

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
    return json.loads(_strip_json_fences(response.text))


# ---------- Pretty printer ----------
def print_lesson(lesson: dict) -> None:
    print("\n" + "=" * 60)
    print(f"📘  {lesson['title']}")
    print("=" * 60)
    print("\n📖 EXPLANATION\n")
    print(lesson["explanation"])
    print("\n💡 EXAMPLE\n")
    print(lesson["example"])
    print("\n❓ QUESTIONS\n")
    for i, q in enumerate(lesson["questions"], start=1):
        print(f"Q{i} ({q['type']}): {q['question']}")
        print(f"   ↳ {q['answer']}\n")


# ---------- Main ----------
if __name__ == "__main__":
    URL = "https://en.wikipedia.org/wiki/Machine_learning"

    print(f"Fetching: {URL}")
    article = fetch_article_text(URL)[:8000]

    print("Extracting concepts...")
    concepts = extract_concepts(article)
    print(f"Found {len(concepts)} concepts.\n")

    # Show them and let the user pick which one to turn into a lesson
    for i, c in enumerate(concepts, start=1):
        print(f"  {i}. {c['name']}  [{c['difficulty']}]")

    choice = input("\nPick a concept number to generate a lesson for: ")
    concept = concepts[int(choice) - 1]

    print(f"\n⏳ Generating lesson for: {concept['name']}...")
    lesson = generate_lesson(concept, article)
    print_lesson(lesson)