from django.shortcuts import redirect, render

from .rag import answer_question

HISTORY_KEY = 'chat_history'
MAX_HISTORY = 20


def home(request):
    return render(request, 'home.html')


def about(request):
    return render(request, 'about.html')


def chat(request):
    history = request.session.get(HISTORY_KEY, [])

    if request.method == 'POST':
        question = request.POST.get('question', '').strip()
        if question:
            result = answer_question(question, user=request.user)
            history.append({
                'question': question,
                'answer': result['answer'],
                'intent': result['intent'],
                'sources': result['sources'],
                'has_citations': result['has_citations'],
            })
            request.session[HISTORY_KEY] = history[-MAX_HISTORY:]
        return redirect('chat')

    return render(request, 'chat.html', {'history': history})


def clear_chat(request):
    if request.method == 'POST':
        request.session.pop(HISTORY_KEY, None)
    return redirect('chat')
