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

from knowledge.embeddings import embed_text, cosine_similarity

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


def retrieve(question, top_k=None, zip_code=None):
  """Return the top-k most relevant chunks.

  Custom story 2: when the user has set a ZIP code, alerts tagged for other
  areas are skipped, so only local alerts + general guidance can be used.

  Use compatible embeddings when available, otherwise fall back to keywords.
  """

  top_k = top_k or settings.RAG_TOP_K

  # Get active chunks that apply to the user's location.
  eligible = [
      chunk
      for chunk in Chunk.objects.filter(
          document__is_active=True
      ).select_related("document")
      if chunk.document.applies_to(zip_code)
  ]

  if not eligible:
      return []

  # Generate the question's embedding.
  query_vector = None

  if any(chunk.embedding for chunk in eligible):
      try:
          query_vector = embed_text(
              question,
              "RETRIEVAL_QUERY"
          )
      except Exception:
          logger.exception("Query embedding failed")


  # A missing embedding must not disable semantic search for other chunks.
  compatible = [
      chunk for chunk in eligible
      if query_vector and chunk.embedding
      and len(chunk.embedding) == len(query_vector)
  ]

  scored = []
  if compatible:
      for chunk in compatible:
          score = cosine_similarity(
              query_vector,
              chunk.embedding
          )
          scored.append((score, chunk))

  else:
      # Fallback to the existing keyword retrieval.
      q_tokens = _tokens(question)

      for chunk in eligible:
          score = len(q_tokens & _tokens(chunk.content))

          if score > 0:
              scored.append((score, chunk))


  # Sort from highest score to lowest.
  scored.sort(
      key=lambda item: item[0],
      reverse=True
  )

  # Return only the top K chunks.
  return [chunk for _, chunk in scored[:top_k]]



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

_CITATION = re.compile(r'\[([\d,\s]+)\]')
EXCERPT_CHARS = 220


def _cited_numbers(answer):
  """Numbers the LLM cited in its answer, e.g. [2] or [1, 3] -> {1, 2, 3}."""
  cited = set()
  for group in _CITATION.findall(answer or ''):
    cited.update(int(n) for n in re.findall(r'\d+', group))
  return cited


def _excerpt(text, limit=EXCERPT_CHARS):
  text = ' '.join(text.split())
  if len(text) <= limit:
    return text
  return text[:limit].rsplit(' ', 1)[0] + '\u2026'


def build_sources(chunks, answer=''):
  """Numbered passages, in the same order as the [n] labels in the prompt (story 4)."""
  cited = _cited_numbers(answer)
  return [
      {
          'number': i,
          'document_id': c.document_id,
          'title': c.document.title,
          'url': c.document.source_url,
          'areas': c.document.area_list(),
          'excerpt': _excerpt(c.content),
          'cited': i in cited,
      }
      for i, c in enumerate(chunks, start=1)
  ]


def group_sources(passages):
  """Group passages under their document, in order of first appearance."""
  groups = {}
  for p in passages:
    group = groups.setdefault(
        p['document_id'],
        {'id': p['document_id'], 'title': p['title'], 'url': p['url'],
         'areas': p.get('areas', []), 'passages': []},
    )
    group['passages'].append(p)
  return list(groups.values())

def answer_question(question, user=None, client=None, zip_code=None):
  start = time.perf_counter()
  log = QueryLog(
      question=question, user=user if user and user.is_authenticated else None
  )
  chunks, intent, answer = [], '', ''
  try:
    chunks = retrieve(question, zip_code=zip_code)
    intent, system_prompt, prompt = build_prompt(question, chunks, zip_code=zip_code)
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

  # Don't show sources next to an error message.
  passages = build_sources(chunks, answer) if log.success else []

  return {
      'answer': answer,
      'intent': intent,
      'chunks': chunks,
      'sources': group_sources(passages),
      'has_citations': any(p['cited'] for p in passages),
      'latency_ms': log.latency_ms,
      'success': log.success,
      'zip_code': zip_code,
  }