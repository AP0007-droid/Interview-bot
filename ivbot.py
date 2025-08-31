import sqlite3
import argparse
from difflib import SequenceMatcher
import subprocess
import json

DB_FILE = "interviews.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            answer TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS responses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            candidate TEXT NOT NULL,
            question_id INTEGER,
            response TEXT,
            FOREIGN KEY(question_id) REFERENCES questions(id)
        )
    """)
    conn.commit()
    conn.close()

def is_answer_correct(response, correct_answer, threshold=0.6):
    ratio = SequenceMatcher(None, response.lower(), correct_answer.lower()).ratio()
    return ratio >= threshold

def generate_new_questions_ollama(n=5):
    """
    Use Ollama to generate n new interview questions.
    Assumes Ollama CLI is installed (ollama run ...).
    """
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
        print("Ollama output parsing failed, falling back to empty list:", e)
        return []

def ensure_questions(num_needed):
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM questions")
    count = cur.fetchone()[0]
    
    if count < num_needed:
        to_add = num_needed - count
        new_qs = generate_new_questions_ollama(to_add)
        if new_qs:
            cur.executemany("INSERT INTO questions (question, answer) VALUES (?, ?)", new_qs)
            conn.commit()
            print(f"Added {len(new_qs)} new questions from Ollama.")
    conn.close()

def run_interview(candidate, num_questions):
    ensure_questions(num_questions)
    conn = sqlite3.connect(DB_FILE)
    cur = conn.cursor()

    cur.execute("SELECT * FROM questions ORDER BY RANDOM() LIMIT ?", (num_questions,))
    questions = cur.fetchall()

    print(f"Starting interview for {candidate}...\n")

    responses = []
    asked_questions = []
    correct_count = 0

    for qid, text, ans in questions:
        print(text)
        response = input("> ")

        if response.strip().lower() in ["quit", "exit", "stop", ""]:
            print("\nInterview ended early by candidate.\n")
            break

        responses.append((candidate, qid, response))
        asked_questions.append((text, ans, response))

        if is_answer_correct(response, ans):
            correct_count += 1

    if responses:
        cur.executemany("INSERT INTO responses (candidate, question_id, response) VALUES (?, ?, ?)", responses)
        conn.commit()

    print("\n--- Interview Finished ---")
    print(f"Score: {correct_count} / {len(asked_questions)} correct\n")

    print("Correct Answers for review:")
    for q_text, q_ans, user_resp in asked_questions:
        print(f"Q: {q_text}\nYour Answer: {user_resp}\nExpected: {q_ans}\n")

    conn.close()

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate", help="Candidate name")
    parser.add_argument("--num-questions", type=int, help="Number of questions (5–10)")
    args = parser.parse_args()

    candidate = args.candidate or input("Enter candidate name: ").strip()
    num_questions = args.num_questions or int(input("How many questions (5–10)? ").strip())

    if num_questions < 5 or num_questions > 10:
        print("Number of questions must be between 5 and 10.")
        return

    init_db()
    run_interview(candidate, num_questions)


if __name__ == "__main__":
    main()
