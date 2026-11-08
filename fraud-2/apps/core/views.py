from django.contrib.auth.decorators import login_required
from django.db.models import Avg, Count
from django.db.models.functions import TruncDate
from django.shortcuts import render

from apps.ml.models import ModelArtifact, ModelMetrics, TrainingRun
from apps.transactions.models import Alert, Case, Transaction, UploadBatch
from apps.transactions.services import get_risk_thresholds


@login_required
def dashboard_view(request):
    thresholds = get_risk_thresholds()

    latest_artifact = ModelArtifact.objects.filter(is_active=True).order_by('-created_at').first()
    latest_run = TrainingRun.objects.order_by('-started_at').first()
    recent_metrics = ModelMetrics.objects.order_by('-created_at')[:10]
    recent_alerts = Alert.objects.select_related('transaction').order_by('-created_at')[:8]
    recent_cases = Case.objects.select_related('transaction').order_by('-created_at')[:8]

    scored_qs = Transaction.objects.filter(fraud_probability__isnull=False)

    stats = {
        'transactions_total': Transaction.objects.count(),
        'transactions_scored': scored_qs.count(),
        'alerts_open': Alert.objects.exclude(status='closed').count(),
        'cases_open': Case.objects.exclude(status='closed').count(),
        'uploads_total': UploadBatch.objects.count(),
        'avg_probability': scored_qs.aggregate(v=Avg('fraud_probability'))['v'],
        'high_risk': scored_qs.filter(fraud_probability__gte=thresholds['high']).count(),
        'medium_risk': scored_qs.filter(
            fraud_probability__gte=thresholds['medium'],
            fraud_probability__lt=thresholds['high'],
        ).count(),
        'low_risk': scored_qs.filter(
            fraud_probability__gte=thresholds['low'],
            fraud_probability__lt=thresholds['medium'],
        ).count(),
        'clear_risk': scored_qs.filter(fraud_probability__lt=thresholds['low']).count(),
        'unscored': Transaction.objects.filter(fraud_probability__isnull=True).count(),
    }

    risk_breakdown = {
        'high': stats['high_risk'],
        'medium': stats['medium_risk'],
        'low': stats['low_risk'],
        'clear': stats['clear_risk'],
        'unscored': stats['unscored'],
    }

    # Берём последние 30 дат, затем разворачиваем для нормального порядка слева направо
    tx_by_day_qs = list(
        Transaction.objects
        .exclude(timestamp__isnull=True)
        .annotate(day=TruncDate('timestamp'))
        .values('day')
        .annotate(total=Count('id'))
        .order_by('-day')[:30]
    )
    tx_by_day_qs.reverse()

    operation_qs = list(
        Transaction.objects
        .exclude(operation_type__isnull=True)
        .exclude(operation_type__exact='')
        .values('operation_type')
        .annotate(total=Count('id'))
        .order_by('-total')[:6]
    )

    alert_severity_qs = list(
        Alert.objects
        .exclude(severity__isnull=True)
        .exclude(severity__exact='')
        .values('severity')
        .annotate(total=Count('id'))
    )

    tx_chart = {
        'labels': [item['day'].strftime('%Y-%m-%d') for item in tx_by_day_qs],
        'values': [item['total'] for item in tx_by_day_qs],
    }

    operation_chart = {
        'labels': [item['operation_type'] for item in operation_qs],
        'values': [item['total'] for item in operation_qs],
    }

    risk_chart = {
        'labels': ['High', 'Medium', 'Low', 'Clear', 'Unscored'],
        'values': [
            risk_breakdown['high'],
            risk_breakdown['medium'],
            risk_breakdown['low'],
            risk_breakdown['clear'],
            risk_breakdown['unscored'],
        ],
    }

    severity_order = ['high', 'medium', 'low']
    severity_map = {item['severity']: item['total'] for item in alert_severity_qs}
    alert_chart = {
        'labels': [level.capitalize() for level in severity_order if level in severity_map],
        'values': [severity_map[level] for level in severity_order if level in severity_map],
    }

    return render(
        request,
        'core/dashboard.html',
        {
            'stats': stats,
            'risk_breakdown': risk_breakdown,
            'latest_artifact': latest_artifact,
            'latest_run': latest_run,
            'recent_metrics': recent_metrics,
            'recent_alerts': recent_alerts,
            'recent_cases': recent_cases,
            'thresholds': thresholds,
            'tx_chart': tx_chart,
            'operation_chart': operation_chart,
            'risk_chart': risk_chart,
            'alert_chart': alert_chart,
        },
    )