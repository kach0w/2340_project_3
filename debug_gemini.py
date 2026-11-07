import chat.rag as r
from django.conf import settings

print('rag file:', r.__file__)
print('models:', settings.GEMINI_MODELS)

q = 'What should I do if a flash flood warning is issued?'
ch = r.retrieve(q)
print('chunks:', len(ch))
i, s, p = r.build_prompt(q, ch)
print('intent:', i)
print('PROMPT:', repr(p))

for m in settings.GEMINI_MODELS:
    try:
        resp = r.get_client().models.generate_content(
            model=m,
            contents=p,
            config=r.genai.types.GenerateContentConfig(system_instruction=s),
        )
        print(m, '-> text:', repr(resp.text))
        print('   finish:', [c.finish_reason for c in (resp.candidates or [])])
        print('   feedback:', resp.prompt_feedback)
        print('   usage:', resp.usage_metadata)
    except Exception as e:
        print(m, '-> ERROR:', type(e).__name__, e)
