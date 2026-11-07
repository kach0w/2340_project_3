"""Run known test questions through the RAG pipeline and score them (story 9).

Built for the Gemini free tier (~5 requests/min per model):
  1. Calls are paced (settings.EVAL_SECONDS_BETWEEN_CALLS) so we don't hit 429s.
  2. All answers are graded in ONE batched judge call (n + 1 calls, not 2n).
  3. Runs in a background thread when started from the website.
  4. Uses a fail-fast client (short timeout, no retries) so an overloaded model
     costs seconds, not minutes, before falling back to the next one.
"""
import json
import logging
import re
import threading
import time
from datetime import timedelta

from django.conf import settings
from django.db import close_old_connections, connection
from django.utils import timezone

from chat.rag import answer_question, generate, get_client

from .models import EvaluationResult, EvaluationRun, TestQuestion

logger = logging.getLogger(__name__)

PASS_THRESHOLD = 0.6

JUDGE_SYSTEM = 'You are a strict grader. Reply with only JSON.'
JUDGE_PROMPT = """Grade each chatbot answer against its expected answer.
Score each from 0.0 to 1.0 (1.0 = fully correct, 0.0 = wrong/missing).
Return ONLY a JSON array of numbers, one per item, in order. Example: [1.0, 0.5, 0.0]

{items}"""


def eval_client():
    return get_client(timeout_ms=settings.EVAL_TIMEOUT_MS, attempts=settings.EVAL_ATTEMPTS)


class Pacer:
    """Waits so consecutive LLM calls are at least `interval` seconds apart."""

    def __init__(self, interval):
        self.interval = interval
        self._last = None

    def wait(self):
        if self._last is not None:
            remaining = self.interval - (time.monotonic() - self._last)
            if remaining > 0:
                time.sleep(remaining)
        self._last = time.monotonic()


# ---------- scoring ----------

def keyword_score(tq, answer):
    keywords = tq.keyword_list()
    if not keywords:
        return 0.0
    answer_lower = answer.lower()
    return sum(k in answer_lower for k in keywords) / len(keywords)


def parse_scores(text, n):
    """Pull a list of n floats out of the judge's reply, or None."""
    m = re.search(r'\[.*?\]', text or '', re.S)
    if not m:
        return None
    try:
        scores = [min(max(float(x), 0.0), 1.0) for x in json.loads(m.group())]
    except (ValueError, TypeError):
        return None
    return scores if len(scores) == n else None


def judge_batch(pairs, client=None):
    """Grade [(test_question, answer), ...] in one LLM call. Returns list of scores or None."""
    if not pairs:
        return []
    items = '\n\n'.join(
        f'Item {i}:\nQuestion: {tq.question}\nExpected: {tq.expected_answer}\nChatbot answer: {ans}'
        for i, (tq, ans) in enumerate(pairs, 1)
    )
    try:
        text = generate(JUDGE_SYSTEM, JUDGE_PROMPT.format(items=items), client=client)
    except Exception as e:
        logger.warning('LLM judge failed, falling back to keywords: %s', e)
        return None
    scores = parse_scores(text, len(pairs))
    if scores is None:
        logger.warning('Could not parse judge reply, falling back to keywords: %r', (text or '')[:200])
    return scores


def score_all(pairs, client=None):
    """LLM-judge questions that have an expected answer; keyword-score the rest."""
    scores = [keyword_score(tq, ans) for tq, ans in pairs]
    to_judge = [i for i, (tq, _) in enumerate(pairs) if tq.expected_answer]
    judged = judge_batch([pairs[i] for i in to_judge], client=client)
    if judged:
        for i, s in zip(to_judge, judged):
            scores[i] = s
    return scores


# ---------- running ----------

def run_evaluation(run=None, on_progress=None):
    """Answer every test question, grade them in one batch, save results.

    `on_progress(message)` is called as it goes. Returns the EvaluationRun.
    """
    run = run or EvaluationRun.objects.create()
    client = eval_client()
    pacer = Pacer(settings.EVAL_SECONDS_BETWEEN_CALLS)

    def progress(msg):
        run.progress = msg
        run.save(update_fields=['progress', 'updated_at'])
        if on_progress:
            on_progress(msg)

    try:
        questions = list(TestQuestion.objects.all())
        run.total = len(questions)
        run.save(update_fields=['total'])

        answered = []
        for i, tq in enumerate(questions, 1):
            progress(f'Answering {i}/{len(questions)}')
            pacer.wait()
            result = answer_question(tq.question, client=client)
            answered.append((tq, result))

        progress('Grading answers')
        if any(tq.expected_answer for tq, _ in answered):
            pacer.wait()
        scores = score_all([(tq, r['answer']) for tq, r in answered], client=client)

        for (tq, result), score in zip(answered, scores):
            EvaluationResult.objects.create(
                run=run,
                test_question=tq,
                actual_answer=result['answer'],
                score=score,
                passed=score >= PASS_THRESHOLD,
                latency_ms=result['latency_ms'],
            )
        run.passed = sum(s >= PASS_THRESHOLD for s in scores)
        run.status = EvaluationRun.STATUS_DONE
        run.progress = f'{run.passed}/{run.total} passed'
    except Exception as e:
        logger.exception('Evaluation run failed')
        run.status = EvaluationRun.STATUS_FAILED
        run.error_message = str(e)
        run.progress = 'Failed'
    run.finished_at = timezone.now()
    run.save()
    if on_progress:
        on_progress(run.progress)
    return run


def current_run():
    """The run in progress, if any. A run with no progress for a few minutes (its thread died) is marked failed."""
    run = EvaluationRun.objects.filter(status=EvaluationRun.STATUS_RUNNING).first()
    if run and run.updated_at < timezone.now() - timedelta(minutes=EvaluationRun.STALE_AFTER_MINUTES):
        run.status = EvaluationRun.STATUS_FAILED
        run.error_message = 'Run stopped making progress (server restarted or reloaded?). Try again.'
        run.finished_at = timezone.now()
        run.save()
        return None
    return run


_start_lock = threading.Lock()


def start_background_run():
    """Start a run in a background thread. Returns (run, started); never starts a second one."""
    with _start_lock:
        existing = current_run()
        if existing:
            return existing, False
        run = EvaluationRun.objects.create()

    def target():
        close_old_connections()
        try:
            run_evaluation(run)
        finally:
            connection.close()

    threading.Thread(target=target, daemon=True, name=f'eval-run-{run.pk}').start()
    return run, True
