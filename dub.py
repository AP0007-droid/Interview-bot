import psycopg2
import streamlit as st
from difflib import SequenceMatcher
from langchain_ollama import OllamaLLM
from langgraph.graph import StateGraph, END
from typing import TypedDict, List
import json
import re

DB_URL = "postgresql://postgres.nvjdmjebzuvjjhzohzra:AbhaySingh%401966@aws-1-ap-south-1.pooler.supabase.com:5432/postgres?sslmode=require"

llm = OllamaLLM(model="llama3")

class InterviewState(TypedDict):
    candidate: str
    questions: List[str]
    answers: List[str]
    evaluations: List[str]

def generate_questions(state: InterviewState) -> InterviewState:
    prompt = (
        "Generate 5 beginner programming interview questions with answers "
        "in strict JSON format ONLY, nothing else. Example: "
        '[{"question": "What is Python?", "answer": "Python is a programming language."}]'
    )
    qa_text = llm.invoke(prompt)

    match = re.search(r'\[.*\]', qa_text, re.DOTALL)
    if match:
        json_text = match.group(0)
        try:
            qa_list = json.loads(json_text)
        except Exception as e:
            st.error(f"Failed to parse JSON: {e}")
            qa_list = []
    else:
        st.error("No JSON found in LLM output.")
        qa_list = []

    state["questions"] = [q.get("question", "") for q in qa_list]
    state["answers"] = [q.get("answer", "") for q in qa_list]
    return state

def evaluate_answers(state: InterviewState) -> InterviewState:
    evaluations = []
    for user_ans, correct_ans in zip(state["answers"], state["answers"]):
        ratio = SequenceMatcher(None, user_ans.lower(), correct_ans.lower()).ratio()
        evaluations.append("Correct" if ratio >= 0.6 else "Incorrect")
    state["evaluations"] = evaluations
    return state

def save_to_db(state: InterviewState) -> InterviewState:
    try:
        conn = psycopg2.connect(DB_URL, connect_timeout=5)
        cur = conn.cursor()
        for q, a in zip(state["questions"], state["answers"]):
            cur.execute(
                "INSERT INTO questions (question, answer) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (q, a)
            )
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        st.error(f"DB save failed: {e}")
    return state

graph = StateGraph(InterviewState)
graph.add_node("generate", generate_questions)
graph.add_node("evaluate", evaluate_answers)
graph.add_node("save", save_to_db)

graph.set_entry_point("generate")
graph.add_edge("generate", "save")
graph.add_edge("save", "evaluate")
graph.add_edge("evaluate", END)

interview_app = graph.compile()

st.title("Interview Bot")

candidate = st.text_input("Enter your name:")
if st.button("Start Interview") and candidate:
    init_state: InterviewState = {"candidate": candidate, "questions": [], "answers": [], "evaluations": []}
    result = interview_app.invoke(init_state)

    st.session_state.questions = result["questions"]
    st.session_state.answers = []
    st.session_state.evaluations = result["evaluations"]

if "questions" in st.session_state:
    answers = {}
    for idx, q in enumerate(st.session_state.questions):
        answers[idx] = st.text_input(q, key=f"q_{idx}")

    if st.button("Submit Answers"):
        st.session_state.answers = [answers[i] for i in range(len(st.session_state.questions))]
        final_state = interview_app.invoke({
            "candidate": candidate,
            "questions": st.session_state.questions,
            "answers": st.session_state.answers,
            "evaluations": []
        })

        st.subheader("Results")
        for q, user_ans, eval_ in zip(st.session_state.questions, st.session_state.answers, final_state["evaluations"]):
            st.write(f"Q: {q}")
            st.write(f"Your Answer: {user_ans}")
            st.write(f"Result: {eval_}")
            st.write("---")