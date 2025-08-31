import psycopg2
import random
import streamlit as st
import json
from typing import TypedDict, List
from langchain_ollama import OllamaLLM
from langgraph.graph import StateGraph, END

DB_URL = "postgresql://postgres.nvjdmjebzuvjjhzohzra:AbhaySingh%401966@aws-1-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"

llm = OllamaLLM(model="llama3")

class InterviewState(TypedDict):
    candidate: str
    questions: List[str]
    correct_answers: List[str]
    user_answers: List[str]
    evaluations: List[str]
    score: int
    total: int
    eligible: bool

def get_db_connection():
    return psycopg2.connect(DB_URL, connect_timeout=5)

def fetch_random_questions(n=10):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT question, answer FROM questions ORDER BY RANDOM() LIMIT %s;", (n,))
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return rows
    except Exception as e:
        st.error(f"DB fetch failed: {e}")
        return []

def save_questions_to_db(qa_list):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        for q in qa_list:
            cur.execute("INSERT INTO questions (question, answer) VALUES (%s,%s) ON CONFLICT DO NOTHING", 
                        (q["question"], q["answer"]))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"DB save failed: {e}")

def save_report(candidate, score, total, eligible):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO reports (candidate, score, total, eligible) VALUES (%s,%s,%s,%s)",
            (candidate, score, total, eligible)
        )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"DB report save failed: {e}")

def generate_questions_with_llm(n=10):
    prompt = f"""
    Generate {n} beginner programming interview questions with answers
    in JSON array format, e.g.:
    [{{"question":"...","answer":"..."}}]
    """
    qa_text = llm.invoke(prompt)

    try:
        qa_list = json.loads(qa_text)
    except Exception:
    
        try:
            qa_text = qa_text.strip().split("[",1)[-1]
            qa_text = "[" + qa_text.split("]",1)[0] + "]"
            qa_list = json.loads(qa_text)
        except Exception:
            st.error("Failed to parse Ollama JSON")
            qa_list = []

    if qa_list:
        save_questions_to_db(qa_list)
    return [(q["question"], q["answer"]) for q in qa_list]

def ask_questions(state: InterviewState) -> InterviewState:
    
    qa_pairs = fetch_random_questions(10)
    if not qa_pairs:
        qa_pairs = generate_questions_with_llm(10)

    state["questions"] = [q for q, _ in qa_pairs]
    state["correct_answers"] = [a for _, a in qa_pairs]
    state["total"] = len(qa_pairs)
    return state

def evaluate(state: InterviewState) -> InterviewState:
    score = 0
    evaluations = []
    for user_ans, correct in zip(state["user_answers"], state["correct_answers"]):
        if user_ans and user_ans.lower() in correct.lower():
            evaluations.append("Correct")
            score += 1
        else:
            evaluations.append("Incorrect")
    state["evaluations"] = evaluations
    state["score"] = score
    state["eligible"] = score >= (0.6 * state["total"])  # 60% pass mark
    save_report(state["candidate"], score, state["total"], state["eligible"])
    return state

graph = StateGraph(InterviewState)
graph.add_node("ask", ask_questions)
graph.add_node("evaluate", evaluate)
graph.set_entry_point("ask")
graph.add_edge("ask", "evaluate")
graph.add_edge("evaluate", END)
interview_app = graph.compile()

st.title("AI Interview Bot")

candidate = st.text_input("Enter your name:")
if st.button("Start Interview") and candidate:
    init_state: InterviewState = {
        "candidate": candidate,
        "questions": [],
        "correct_answers": [],
        "user_answers": [],
        "evaluations": [],
        "score": 0,
        "total": 0,
        "eligible": False
    }
    result = interview_app.invoke(init_state)
    st.session_state.questions = result["questions"]
    st.session_state.correct_answers = result["correct_answers"]
    st.session_state.user_answers = []

if "questions" in st.session_state:
    answers = {}
    for i, q in enumerate(st.session_state.questions):
        answers[i] = st.text_input(q, key=f"q_{i}")

    if st.button("Submit Answers"):
        st.session_state.user_answers = [answers[i] for i in range(len(st.session_state.questions))]
        final_state = interview_app.invoke({
            "candidate": candidate,
            "questions": st.session_state.questions,
            "correct_answers": st.session_state.correct_answers,
            "user_answers": st.session_state.user_answers,
            "evaluations": [],
            "score": 0,
            "total": len(st.session_state.questions),
            "eligible": False
        })

        st.subheader("Results")
        for q, user_ans, correct, eval_ in zip(
            final_state["questions"],
            final_state["user_answers"],
            final_state["correct_answers"],
            final_state["evaluations"]
        ):
            st.write(f"Q: {q}")
            st.write(f"Your Answer: {user_ans}")
            st.write(f"Correct Answer: {correct}")
            st.write(f"Result: {eval_}")
            st.write("---")

        st.success(f"Final Score: {final_state['score']}/{final_state['total']}")
        st.info(f"Eligibility: {'Eligible' if final_state['eligible'] else 'Not Eligible'}")
