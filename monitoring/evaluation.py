"""Run known test questions through the RAG pipeline and score them (story 9)."""
from chat.rag import answer_question

from .models import EvaluationResult, TestQuestion

PASS_THRESHOLD = 0.6


def score_answer(test_question, answer):
    # TODO: swap for a better metric (semantic similarity, LLM-as-judge, ...)
    keywords = test_question.keyword_list()
    if not keywords:
        return 0.0
    answer_lower = answer.lower()
    return sum(1 for k in keywords if k in answer_lower) / len(keywords)


def run_evaluation():
    results = []
    for tq in TestQuestion.objects.all():
        result = answer_question(tq.question)
        score = score_answer(tq, result['answer'])
        results.append(EvaluationResult.objects.create(
            test_question=tq,
            actual_answer=result['answer'],
            score=score,
            passed=score >= PASS_THRESHOLD,
            latency_ms=result['latency_ms'],
        ))
    return results
