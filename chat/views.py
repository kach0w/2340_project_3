from django.contrib import messages
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from knowledge.location import zip_from_location

from .location import get_location, set_location as save_location
from .rag import answer_question
from django.utils.http import url_has_allowed_host_and_scheme

HISTORY_KEY = 'chat_history'
MAX_HISTORY = 50
# code -> name sent to Gemini. English maps to None, so default users get the unchanged prompt.
LANGUAGES = {
    'en': None,
    'es': 'Spanish',
    'zh': 'Chinese',
    'fr': 'French',
}


def home(request):
    return render(request, 'home.html')


def about(request):
    return render(request, 'about.html')


def chat(request):
    history = request.session.get(HISTORY_KEY, [])
    zip_code, location = get_location(request)

    if request.method == 'POST':
        question = request.POST.get('question', '').strip()
        if question:
            result = answer_question(question, user=request.user, zip_code=zip_code, language=LANGUAGES.get(request.session.get('language', 'en')),)
            history.append({
                'question': question,
                'answer': result['answer'],
                'intent': result['intent'],
                'sources': result['sources'],
                'has_citations': result['has_citations'],
                'zip_code': zip_code,
                'location': location,
            })
            request.session[HISTORY_KEY] = history[-MAX_HISTORY:]
        return redirect('chat')

    return render(request, 'chat.html', {
        'history': history,
        'zip_code': zip_code,
        'location': location,
        'editing_location': request.GET.get('change') == 'location',
    })

@require_POST
def set_language(request):
    """Save the chosen answer language in the session."""
    code = request.POST.get('language', 'en')
    if code in LANGUAGES:   # whitelist: this value ends up in the system prompt
        request.session['language'] = code

    next_url = request.POST.get('next', '')
    if url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}):
        return redirect(next_url)
    return redirect('chat')

@require_POST
def set_location(request):
    """Custom story 2: save or clear the address / ZIP used to filter alerts."""
    if 'clear' in request.POST:
        save_location(request, None)
        messages.success(request, 'Location cleared. Showing alerts for all areas.')
        return redirect('chat')

    text = ' '.join(request.POST.get('location', '').split())
    zip_code = zip_from_location(text)
    if not zip_code:
        messages.error(request, 'Enter a 5-digit ZIP code, or an address that includes one '
                                '(e.g. 266 Ferst Dr NW, Atlanta, GA 30332).')
    else:
        save_location(request, zip_code, text)
        messages.success(request, f'Location set to {text} (ZIP {zip_code}). '
                                  'Alerts for other areas will be filtered out.')
    return redirect('chat')


def clear_chat(request):
    if request.method == 'POST':
        request.session.pop(HISTORY_KEY, None)
    return redirect('chat')
