from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .models import ModelArtifact, ModelMetrics, TrainingRun
from .services import score_transactions, train_models


@login_required
def train_view(request):
    result = None
    if request.method == 'POST':
        try:
            result = train_models()
            messages.success(request, f"Training finished. Best model: {result['best_model_name']}")
        except Exception as exc:
            messages.error(request, f'Training failed: {exc}')

    return render(
        request,
        'ml/train.html',
        {
            'result': result,
            'latest_artifact': ModelArtifact.objects.filter(is_active=True).order_by('-created_at').first(),
            'latest_run': TrainingRun.objects.order_by('-started_at').first(),
            'metrics': ModelMetrics.objects.order_by('-created_at')[:20],
        },
    )


@login_required
def score_view(request):
    result = None
    if request.method == 'POST':
        try:
            rescore_all = request.POST.get('rescore_all') == 'on'
            result = score_transactions(rescore_all=rescore_all)
            messages.success(request, f"Scored {result['scored_rows']} transactions.")
        except Exception as exc:
            messages.error(request, f'Scoring failed: {exc}')

    return render(
        request,
        'ml/score.html',
        {
            'result': result,
            'latest_artifact': ModelArtifact.objects.filter(is_active=True).order_by('-created_at').first(),
        },
    )
