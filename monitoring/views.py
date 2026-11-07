from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.paginator import Paginator
from django.db.models import Avg, Count, Max, Q
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .evaluation import current_run, start_background_run
from .models import EvaluationRun, QueryLog, TestQuestion


def percentile(sorted_values, pct):
    """Nearest-rank percentile of an already-sorted list (None if empty)."""
    if not sorted_values:
        return None
    rank = max(1, round(pct / 100 * len(sorted_values)))
    return sorted_values[min(rank, len(sorted_values)) - 1]


def performance_stats(queryset):
    target = settings.LATENCY_TARGET_MS
    stats = queryset.aggregate(
        total=Count('id'),
        failures=Count('id', filter=Q(success=False)),
        avg_latency=Avg('latency_ms'),
        max_latency=Max('latency_ms'),
        within_target=Count('id', filter=Q(success=True, latency_ms__lte=target)),
    )
    latencies = sorted(queryset.filter(success=True).values_list('latency_ms', flat=True))
    total = stats['total']
    stats.update(
        target_ms=target,
        goal_percent=settings.LATENCY_GOAL_PERCENT,
        p95_latency=percentile(latencies, 95),
        failure_rate=(100 * stats['failures'] / total) if total else 0,
        # Failed requests count against the target too.
        within_target_percent=(100 * stats['within_target'] / total) if total else None,
    )
    stats['meets_goal'] = (
        stats['within_target_percent'] is not None
        and stats['within_target_percent'] >= settings.LATENCY_GOAL_PERCENT
    )
    return stats


@staff_member_required(login_url='loginaccount')
def dashboard(request):
    since = timezone.now() - timedelta(hours=24)
    logs = QueryLog.objects.all()
    return render(request, 'dashboard.html', {
        'stats': performance_stats(logs),
        'stats_24h': performance_stats(logs.filter(created_at__gte=since)),
        'recent_failures': logs.filter(success=False)[:10],
        'slow_queries': logs.filter(success=True, latency_ms__gt=settings.LATENCY_TARGET_MS)
                            .order_by('-latency_ms')[:10],
    })


@staff_member_required(login_url='loginaccount')
def logs(request):
    paginator = Paginator(QueryLog.objects.select_related('user'), 25)
    page = paginator.get_page(request.GET.get('page'))
    return render(request, 'logs.html', {'page': page, 'target_ms': settings.LATENCY_TARGET_MS})


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
