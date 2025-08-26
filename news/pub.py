import psycopg2
import streamlit as st
from difflib import SequenceMatcher
import subprocess
import json
import random

DB_URL = "postgresql://postgres:AbhaySingh%401966@db.nvjdmjebzuvjjhzohzra.supabase.co:5432/postgres"

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
    conn.commit()
    cur.close()
    conn.close()

def is_answer_correct(response, correct_answer, threshold=0.6):
    ratio = SequenceMatcher(None, response.lower(), correct_answer.lower()).ratio()
    return ratio >= threshold

def generate_new_questions_ollama(n=5):
    prompt = f"Generate {n} simple programming interview questions and their short answers in JSON list format. Example: [{{'q':'What is Python?','a':'A programming language'}}]"
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

def ensure_questions(num_needed):
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

def get_random_questions(num_questions):
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()
    cur.execute("SELECT * FROM questions")
    all_qs = cur.fetchall()
    cur.close()
    conn.close()
    return random.sample(all_qs, min(num_questions, len(all_qs)))

st.title("Programming Interview Bot")

init_db()

candidate = st.text_input("Enter your name:")

num_questions = st.number_input("Number of questions (5-10)", min_value=5, max_value=10, value=5, step=1)

if st.button("Start Interview") and candidate:
    ensure_questions(num_questions)
    st.session_state.questions = get_random_questions(num_questions)
    st.session_state.candidate = candidate
    st.session_state.started = True

if "started" in st.session_state and st.session_state.started:
    st.subheader(f"Interview for {st.session_state.candidate}")
    answers = {}

    for qid, text, ans in st.session_state.questions:
        answers[qid] = st.text_input(f"{text}", key=f"q_{qid}")

    if st.button("Submit Answers"):
        responses = []
        asked_questions = []
        correct_count = 0

        for qid, text, ans in st.session_state.questions:
            user_resp = answers.get(qid, "")
            responses.append((st.session_state.candidate, qid, user_resp))
            asked_questions.append((text, ans, user_resp))
            if is_answer_correct(user_resp, ans):
                correct_count += 1

        conn = psycopg2.connect(DB_URL)
        cur = conn.cursor()
        cur.executemany(
            "INSERT INTO responses (candidate, question_id, response) VALUES (%s, %s, %s)",
            responses
        )
        conn.commit()
        cur.close()
        conn.close()

        st.subheader("Interview Finished")
        st.write(f"Score: {correct_count} / {len(asked_questions)} correct")
        for q_text, q_ans, user_resp in asked_questions:
            st.write(f"Q: {q_text}")
            st.write(f"Your Answer: {user_resp}")
            st.write(f"Expected: {q_ans}")
            st.write("---")

        st.session_state.started = False
