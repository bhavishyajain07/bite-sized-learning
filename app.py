import streamlit as st
from datetime import datetime

from build_course import (
    build_course,
    list_courses,
    load_course,
    load_progress,
    save_progress,
)

st.set_page_config(
    page_title="Bite Sized Learning",
    page_icon="📘",
    layout="centered",
)


# ---------- Lesson renderer (reused) ----------
def render_lesson(item: dict, slug: str, progress: dict, *, allow_complete: bool) -> None:
    day = item["day"]
    concept = item["concept"]
    lesson = item["lesson"]

    st.markdown(f"### Day {day}: {lesson['title']}")
    st.caption(f"Concept: **{concept['name']}** · Difficulty: *{concept['difficulty']}*")

    st.markdown("#### 📖 Explanation")
    st.write(lesson["explanation"])

    st.markdown("#### 💡 Example")
    st.info(lesson["example"])

    st.markdown("#### ❓ Questions")
    for i, q in enumerate(lesson["questions"], start=1):
        with st.expander(f"Q{i} ({q['type']}): {q['question']}"):
            st.success(q["answer"])

    if allow_complete:
        st.markdown("---")
        st.markdown("#### How well did you grasp this lesson?")
        col1, col2, col3 = st.columns(3)
        rating = None
        if col1.button("😕 Still confused", key=f"confused_{slug}_{day}"):
            rating = "again"
        if col2.button("🙂 Got it", key=f"good_{slug}_{day}"):
            rating = "good"
        if col3.button("😎 Easy", key=f"easy_{slug}_{day}"):
            rating = "easy"

        if rating:
            progress["ratings"][str(day)] = {
                "rating": rating,
                "rated_at": datetime.now().isoformat(timespec="seconds"),
            }
            if day not in progress["completed"]:
                progress["completed"].append(day)
            if day == progress["current_day"]:
                progress["current_day"] = day + 1
            save_progress(slug, progress)
            st.success(f"Lesson {day} marked complete. See you tomorrow!")
            st.rerun()


# ---------- Pages ----------
def page_create_course() -> None:
    st.title("➕ Create a New Course")
    st.caption("Paste any article URL and we'll turn it into a multi-day course.")

    name = st.text_input("Course name", placeholder="e.g. Transformer Architectures")
    url = st.text_input(
        "Article URL",
        placeholder="https://en.wikipedia.org/wiki/...",
    )

    if st.button("🚀 Generate Course", type="primary", disabled=not (name and url)):
        status = st.empty()
        bar = st.progress(0.0)

        def cb(msg: str, frac: float) -> None:
            status.write(msg)
            bar.progress(min(max(frac, 0.0), 1.0))

        try:
            slug = build_course(url, name, progress_callback=cb)
            st.success(f"Course '{name}' created! Switch to it from the sidebar.")
            st.session_state["active_slug"] = slug
            st.rerun()
        except Exception as e:
            st.error(f"Something went wrong: {e}")


def page_today(course: dict, progress: dict, slug: str) -> None:
    st.title(f"📘 {course['name']}")
    st.caption("Today's Lesson")

    total = len(course["lessons"])
    current_day = progress["current_day"]

    if current_day > total:
        st.balloons()
        st.success(f"🎉 You've completed all {total} lessons in this course!")
        return

    item = next(x for x in course["lessons"] if x["day"] == current_day)
    st.progress(current_day / total, text=f"Day {current_day} of {total}")
    render_lesson(item, slug, progress, allow_complete=True)


def page_all_lessons(course: dict, progress: dict, slug: str) -> None:
    st.title(f"📚 All Lessons — {course['name']}")
    st.caption(f"Source: {course['source_url']}")

    completed = set(progress["completed"])
    titles = [
        f"{'✅' if item['day'] in completed else '⬜'} "
        f"Day {item['day']}: {item['lesson']['title']}"
        for item in course["lessons"]
    ]
    selected = st.radio("Pick a lesson to view:", titles, index=0)
    selected_day = int(selected.split("Day ")[1].split(":")[0])
    item = next(x for x in course["lessons"] if x["day"] == selected_day)

    st.markdown("---")
    render_lesson(item, slug, progress, allow_complete=False)


def page_progress(course: dict, progress: dict, slug: str) -> None:
    st.title(f"📊 Progress — {course['name']}")

    total = len(course["lessons"])
    done = len(progress["completed"])
    st.metric("Lessons completed", f"{done} / {total}")
    st.progress(done / total if total else 0.0)

    ratings = [v["rating"] for v in progress["ratings"].values()]
    col1, col2, col3 = st.columns(3)
    col1.metric("😕 Still confused", ratings.count("again"))
    col2.metric("🙂 Got it", ratings.count("good"))
    col3.metric("😎 Easy", ratings.count("easy"))

    st.markdown("---")
    if st.button("🔄 Reset progress for this course"):
        save_progress(slug, {"current_day": 1, "completed": [], "ratings": {}})
        st.success("Progress reset.")
        st.rerun()


# ---------- Main ----------
def main() -> None:
    st.sidebar.title("📘 Bite Sized Learning")

    courses = list_courses()

    # Course switcher in sidebar
    if courses:
        names = [c["name"] for c in courses]
        slugs = [c["slug"] for c in courses]

        # Pick a default
        default_slug = st.session_state.get("active_slug", slugs[0])
        default_idx = slugs.index(default_slug) if default_slug in slugs else 0

        selected_name = st.sidebar.selectbox(
            "My Courses",
            names,
            index=default_idx,
        )
        active_slug = slugs[names.index(selected_name)]
        st.session_state["active_slug"] = active_slug
    else:
        st.sidebar.info("No courses yet. Create your first one!")
        active_slug = None

    st.sidebar.markdown("---")

    # Page selection
    page_options = ["➕ New Course"]
    if active_slug:
        page_options = [
            "Today's Lesson",
            "All Lessons",
            "Progress",
            "➕ New Course",
        ]
    page = st.sidebar.radio("Navigate", page_options)

    if page == "➕ New Course" or active_slug is None:
        page_create_course()
        return

    # Load the active course
    course = load_course(active_slug)
    progress = load_progress(active_slug)
    st.sidebar.caption(f"Created: {course['created_at']}")
    st.sidebar.caption(f"Source:\n{course['source_url']}")

    if page == "Today's Lesson":
        page_today(course, progress, active_slug)
    elif page == "All Lessons":
        page_all_lessons(course, progress, active_slug)
    elif page == "Progress":
        page_progress(course, progress, active_slug)


if __name__ == "__main__":
    main()