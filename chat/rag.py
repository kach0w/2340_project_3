"""Core RAG pipeline: retrieve -> build prompt -> generate -> log."""
import functools
import logging
import re
import time

import httpx
from django.conf import settings
from google import genai
from google.genai import errors as genai_errors
from knowledge.models import Chunk
from monitoring.models import QueryLog

from .prompts import build_prompt

logger = logging.getLogger(__name__)

@functools.cache
def get_client(timeout_ms=30_000, attempts=3):
  """Create the Gemini client on first use, so the app can start without a key.

  Timeout is in milliseconds; retries cover temporary 503/429 responses.
  One cached client per (timeout_ms, attempts) combo.
  """
  return genai.Client(
      api_key=settings.GOOGLE_API_KEY,
      http_options=genai.types.HttpOptions(
          timeout=timeout_ms,
          retry_options=genai.types.HttpRetryOptions(attempts=attempts),
      ),
  )


_WORD = re.compile(r'[a-z0-9]+')
STOPWORDS = {
    'the', 'a', 'an', 'is', 'are', 'of', 'to', 'in', 'and', 'or',
    'for', 'on', 'what', 'how', 'i', 'do',
}


def _tokens(text):
  return {w for w in _WORD.findall(text.lower()) if w not in STOPWORDS}


def retrieve(question, top_k=None):
  """Return the top-k most relevant chunks.

  TODO: replace keyword overlap with embedding similarity search.
  """
  top_k = top_k or settings.RAG_TOP_K
  q_tokens = _tokens(question)
  scored = []
  for chunk in Chunk.objects.filter(document__is_active=True).select_related(
      'document'
  ):
    score = len(q_tokens & _tokens(chunk.content))
    if score:
      scored.append((score, chunk))
  scored.sort(key=lambda s: s[0], reverse=True)
  return [c for _, c in scored[:top_k]]


def generate(system_prompt, prompt, client=None):
  """Call Gemini, falling back to the next model if one is overloaded/out of quota.

  Pass a custom `client` (e.g. a fail-fast one) to override timeouts/retries.
  """
  client = client or get_client()
  last_error = None
  for model in settings.GEMINI_MODELS:
    try:
      response = client.models.generate_content(
          model=model,
          contents=prompt,
          config=genai.types.GenerateContentConfig(
              system_instruction=system_prompt,
          ),
      )
      return response.text or 'The model returned an empty response.'
    except (genai_errors.ServerError, genai_errors.ClientError, httpx.TimeoutException) as e:
      logger.warning('Model %s failed (%s), trying next', model, getattr(e, 'code', 'timeout'))
      last_error = e
  raise last_error


def answer_question(question, user=None, client=None):
  start = time.perf_counter()
  log = QueryLog(
      question=question, user=user if user and user.is_authenticated else None
  )
  chunks, intent, answer = [], '', ''
  try:
    chunks = retrieve(question)
    intent, system_prompt, prompt = build_prompt(question, chunks)
    if chunks:
      answer = generate(system_prompt, prompt, client=client)
    else:
      answer = "I couldn't find anything in the knowledge base about that."
  except Exception as e:
    logger.exception('answer_question failed')
    log.success = False
    log.error_message = str(e)
    answer = 'Sorry, something went wrong answering your question.'

  log.answer = answer
  log.intent = intent
  log.latency_ms = int((time.perf_counter() - start) * 1000)
  log.save()

  documents = list({c.document for c in chunks})
  log.sources.set(documents)

  return {
      'answer': answer,
      'intent': intent,
      'chunks': chunks,
      'sources': documents,
      'latency_ms': log.latency_ms,
      'success': log.success,
  }