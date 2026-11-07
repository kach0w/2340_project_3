from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Q
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from .evaluation import current_run, start_background_run
from .models import EvaluationRun, QueryLog, TestQuestion


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
    running = current_run()
    latest = EvaluationRun.objects.exclude(status=EvaluationRun.STATUS_RUNNING).first()
    return render(request, 'evaluation.html', {
        'test_questions': TestQuestion.objects.all(),
        'running': running,
        'latest': latest,
        'results': latest.results.select_related('test_question').order_by('id') if latest else [],
        'past_runs': EvaluationRun.objects.exclude(status=EvaluationRun.STATUS_RUNNING)[:10],
    })


@staff_member_required(login_url='loginaccount')
@require_POST
def run_eval(request):
    _, started = start_background_run()
    if started:
        messages.info(request, 'Evaluation started. This page updates automatically.')
    else:
        messages.warning(request, 'An evaluation is already running.')
    return redirect('monitoring.evaluation')
