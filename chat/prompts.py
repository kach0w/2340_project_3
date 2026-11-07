"""Runtime prompt selection based on question intent (story 8).

The intent is detected per question and a matching template is picked
programmatically -- no single hardcoded prompt.
"""
import re

INTENT_FACTUAL = 'factual'
INTENT_EXPLANATION = 'explanation'
INTENT_PROCEDURAL = 'procedural'
INTENT_CREATIVE = 'creative'

# TODO: tune these for your disaster domain / persona
INTENT_PATTERNS = [
    (INTENT_PROCEDURAL, r'\b(how (do|can|should) i|steps?|what should i do|prepare|checklist)\b'),
    # Checked after procedural, so "how do I ..." stays procedural while
    # "how do tornadoes form?" is an explanation.
    (INTENT_EXPLANATION, r'\b(why|explain|how (does|do|did|is|are|can)|what causes|difference between)\b'),
    (INTENT_CREATIVE, r'\b(write|draft|create|generate|compose|plan for)\b'),
]

SYSTEM_PROMPT = (
    'You are DisasterBot, an assistant that answers ONLY using the provided context. '
    'If the context does not contain the answer, say you do not know. '
    'Cite sources by their [number].'
)

PROMPT_TEMPLATES = {
    INTENT_FACTUAL: (
        'Answer the question concisely with the specific facts from the context.\n\n'
        'Context:\n{context}\n\nQuestion: {question}\nAnswer:'
    ),
    INTENT_EXPLANATION: (
        'Explain the answer clearly, covering causes and reasoning, using only the context.\n\n'
        'Context:\n{context}\n\nQuestion: {question}\nExplanation:'
    ),
    INTENT_PROCEDURAL: (
        'Give a numbered, step-by-step answer based only on the context. Put safety-critical steps first.\n\n'
        'Context:\n{context}\n\nQuestion: {question}\nSteps:'
    ),
    INTENT_CREATIVE: (
        'Using the context as your factual basis, produce the requested content. '
        'Do not invent facts beyond the context.\n\n'
        'Context:\n{context}\n\nRequest: {question}\nResponse:'
    ),
}


def classify_intent(question):
    # TODO: optionally replace with an LLM/classifier-based intent detector
    q = question.lower()
    for intent, pattern in INTENT_PATTERNS:
        if re.search(pattern, q):
            return intent
    return INTENT_FACTUAL


def build_prompt(question, chunks):
    intent = classify_intent(question)
    context = '\n\n'.join(f'[{i + 1}] {c.content}' for i, c in enumerate(chunks))
    prompt = PROMPT_TEMPLATES[intent].format(context=context, question=question)
    return intent, SYSTEM_PROMPT, prompt
