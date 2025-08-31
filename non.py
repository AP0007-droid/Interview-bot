import psycopg2
import streamlit as st
from difflib import SequenceMatcher
import subprocess
import json
import random
from langgraph.graph import StateGraph, END

try:
    from typing import TypedDict, List, Tuple, NotRequired
except ImportError:
    from typing import TypedDict, List, Tuple
    from typing_extensions import NotRequired

DB_URL = "postgresql://postgres.nvjdmjebzuvjjhzohzra:AbhaySingh%401966@aws-1-ap-south-1.pooler.supabase.com:5432/postgres"

def init_db():
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            question TEXT NOT NULL,
            answer TEXT NOT NULL
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id SERIAL PRIMARY KEY,
            candidate TEXT NOT NULL,
            question_id INT,
            response TEXT,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS reports (
            id SERIAL PRIMARY KEY,
            candidate TEXT NOT NULL,
            score INT,
            total INT,
            report TEXT
        )
    """)
    conn.commit()
    cur.close()
    conn.close()

def is_answer_correct(response, correct_answer, threshold=0.6):
    ratio = SequenceMatcher(None, response.lower(), correct_answer.lower()).ratio()
    return ratio >= threshold

def generate_new_questions_ollama(n=5):
    prompt = (
        f"Generate {n} simple programming interview questions and their short answers "
        f"in JSON list format. Example: [{{'q':'What is Python?','a':'A programming language'}}]"
    )
    result = subprocess.run(
        ["ollama", "run", "llama3"],
        input=prompt,
        text=True,
        capture_output=True
    )
    try:
        data = json.loads(result.stdout)
        return [(item["q"], item["a"]) for item in data]
    except Exception as e:
        st.warning(f"Ollama output parsing failed: {e}")
        return []

def ensure_questions(num_needed: int):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    row = cur.fetchone()
    count = row[0] if row else 0
    if count < num_needed:
        to_add = num_needed - count
        new_qs = generate_new_questions_ollama(to_add)
        if new_qs:
            cur.executemany("INSERT INTO questions (question, answer) VALUES (%s, %s)", new_qs)
            conn.commit()
            st.info(f"Added {len(new_qs)} new questions from Ollama.")
    cur.close()
    conn.close()

def get_random_questions(num_questions: int):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions")
    all_qs = cur.fetchall()
    cur.close()
    conn.close()
    return random.sample(all_qs, min(num_questions, len(all_qs)))

class InterviewState(TypedDict):
    candidate: str
    num_questions: int

    questions: List[Tuple[int, str, str]]

    responses: List[Tuple[str, int, str]]
    correct_count: int
    feedback: NotRequired[str]

def start_interview(state: InterviewState) -> InterviewState:
    ensure_questions(state["num_questions"])
    qs = get_random_questions(state["num_questions"])
    return {
        **state,
        "questions": qs,
        "responses": [],
        "correct_count": 0,
    }

def finish_interview(state: InterviewState) -> InterviewState:
    correct = state["correct_count"]
    total = len(state["questions"])
    if correct == total:
        feedback = "Excellent work!"
    elif correct >= total // 2:
        feedback = "Good attempt, but review some basics."
    else:
        feedback = "Needs improvement."

    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    if state["responses"]:
        cur.executemany(
            "INSERT INTO responses (candidate, question_id, response) VALUES (%s, %s, %s)",
            state["responses"]
        )
        conn.commit()
    cur.execute(
        "INSERT INTO reports (candidate, score, total, report) VALUES (%s, %s, %s, %s)",
        (state["candidate"], correct, total, feedback)
    )
    conn.commit()
    cur.close()
    conn.close()

    return {**state, "feedback": feedback}

builder = StateGraph(InterviewState)
builder.add_node("start", start_interview)
builder.add_node("finish", finish_interview)
builder.set_entry_point("start")
builder.add_edge("start", "finish")
builder.add_edge("finish", END)
graph = builder.compile()

st.title("Interview Bot")
init_db()

if "interview_started" not in st.session_state:
    st.session_state.interview_started = False
    st.session_state.questions = []
    st.session_state.responses = []
    st.session_state.correct_count = 0
    st.session_state.candidate = ""

candidate = st.text_input("Enter your name:", value=st.session_state.candidate)
num_questions = st.number_input("Number of questions (5-10)", min_value=5, max_value=10, value=5, step=1)

if st.button("Start Interview") and candidate:
    st.session_state.candidate = candidate
    init_state: InterviewState = {
        "candidate": candidate,
        "num_questions": int(num_questions),
        "questions": [],
        "responses": [],
        "correct_count": 0,
    }
    result = graph.invoke(init_state)
    st.session_state.questions = result["questions"]
    st.session_state.responses = []
    st.session_state.correct_count = 0
    st.session_state.interview_started = True

if st.session_state.interview_started:
    for qid, text, ans in st.session_state.questions:
        user_resp = st.text_input(f"{text}", key=f"q_{qid}")
        if user_resp and qid not in [r[1] for r in st.session_state.responses]:
            st.session_state.responses.append((st.session_state.candidate, qid, user_resp))
            if is_answer_correct(user_resp, ans):
                st.session_state.correct_count += 1

    if len(st.session_state.responses) == len(st.session_state.questions):
        final_state: InterviewState = {
            "candidate": st.session_state.candidate,
            "num_questions": len(st.session_state.questions),
            "questions": st.session_state.questions,
            "responses": st.session_state.responses,
            "correct_count": st.session_state.correct_count,
        }
        finished = graph.invoke(final_state)
        st.subheader("Interview Finished")
        st.write(f"Score: {st.session_state.correct_count} / {len(st.session_state.questions)} correct")
        st.write(f"Feedback: {finished['feedback']}")

        for q_text, q_ans, user_resp in [(q[1], q[2], r[2]) for q, r in zip(st.session_state.questions, st.session_state.responses)]:
            st.write(f"Q: {q_text}")
            st.write(f"Your Answer: {user_resp}")
            st.write(f"Expected: {q_ans}")
            st.write("---")
