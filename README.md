# 📘 Bite Sized Learning

Turn any article into a multi-day micro-course. Paste a URL, get a sequenced curriculum of 5-10 minute lessons with explanations, worked examples, and active-recall questions. Built for busy professionals who want to learn over morning coffee.

**Live demo:** _coming soon_

## How it works

1. **Fetch & extract** — `trafilatura` pulls clean article text from any URL
2. **Concept extraction** — Gemini identifies the atomic teachable concepts in the source
3. **Pedagogical ordering** — concepts are topologically sorted so prerequisites come first
4. **Lesson generation** — each concept is expanded into a structured lesson (explanation + example + 3 active-recall questions: recall, application, reasoning)
5. **Progress tracking** — per-course progress with self-rated confidence

## Architecture

- **Frontend:** Streamlit (multi-page sidebar app)
- **LLM:** Google Gemini (`gemini-2.5-flash` with automatic fallback to `gemini-2.5-flash-lite` on quota errors)
- **Storage:** Local JSON, one folder per course (`courses/<slug>/course.json` + `progress.json`)
- **Resilience:** Robust JSON extraction from LLM responses (handles markdown fences and trailing prose); model fallback chain

## Tech decisions worth calling out

- **No vector DB yet.** Concept extraction happens in a single LLM pass over the article (~8K char window). For longer sources, the next step is intelligent chunking + RAG-style retrieval at lesson-generation time.
- **Prompt-as-program.** The concept and lesson prompts encode pedagogy (atomic-concept rules, question typing, anti-fluff tone). Most of the engineering lives there.
- **Topological sort** ensures Day N's concept doesn't depend on something the learner hasn't seen yet.

## Run locally

```bash
git clone <this-repo>
cd bite-sized-learning
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
echo 'GEMINI_API_KEY = "your-key-here"' > .streamlit/secrets.toml
streamlit run app.py
```

Get a free Gemini API key at [aistudio.google.com](https://aistudio.google.com).

## Roadmap

- [ ] Spaced repetition (questions you got wrong return on later days)
- [ ] PDF / YouTube / EPUB ingestion
- [ ] Long-article handling via chunking + RAG
- [ ] Evals: faithfulness, coverage, question quality
- [ ] BYOK (bring your own API key) mode for public deployments