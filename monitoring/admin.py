from django.contrib import admin

from .models import EvaluationResult, EvaluationRun, QueryLog, TestQuestion


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'user', 'intent', 'latency_ms', 'success')
    list_filter = ('success', 'intent')


admin.site.register(TestQuestion)
admin.site.register(EvaluationResult)


@admin.register(EvaluationRun)
class EvaluationRunAdmin(admin.ModelAdmin):
    list_display = ('started_at', 'status', 'passed', 'total', 'progress')
