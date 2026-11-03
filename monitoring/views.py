from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .evaluation import run_evaluation
from .models import EvaluationResult, QueryLog, TestQuestion


@staff_member_required(login_url='loginaccount')
def dashboard(request):
    stats = QueryLog.objects.aggregate(
        total=Count('id'),
        failures=Count('id', filter=Q(success=False)),
        avg_latency=Avg('latency_ms'),
        max_latency=Max('latency_ms'),
    )
    recent_failures = QueryLog.objects.filter(success=False)[:10]
    return render(request, 'dashboard.html', {'stats': stats, 'recent_failures': recent_failures})


@staff_member_required(login_url='loginaccount')
def logs(request):
    paginator = Paginator(QueryLog.objects.select_related('user'), 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'logs.html', {'page': page})


@staff_member_required(login_url='loginaccount')
def evaluation(request):
    if request.method == 'POST':
        TestQuestion.objects.create(
            question=request.POST.get('question', ''),
            expected_answer=request.POST.get('expected_answer', ''),
            expected_keywords=request.POST.get('expected_keywords', ''),
        )
        return redirect('monitoring.evaluation')
    return render(request, 'evaluation.html', {
        'test_questions': TestQuestion.objects.all(),
        'results': EvaluationResult.objects.select_related('test_question')[:50],
    })


@staff_member_required(login_url='loginaccount')
@require_POST
def run_eval(request):
    results = run_evaluation()
    passed = sum(r.passed for r in results)
    messages.info(request, f'Evaluation complete: {passed}/{len(results)} passed.')
    return redirect('monitoring.evaluation')
