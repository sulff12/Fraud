from django.contrib import admin

from .models import ModelArtifact, ModelMetrics, TrainingRun


@admin.register(TrainingRun)
class TrainingRunAdmin(admin.ModelAdmin):
    list_display = ('id', 'status', 'best_model_name', 'selection_metric', 'started_at', 'finished_at')
    list_filter = ('status',)
    search_fields = ('best_model_name', 'notes')


@admin.register(ModelArtifact)
class ModelArtifactAdmin(admin.ModelAdmin):
    list_display = ('id', 'model_name', 'file_path', 'is_active', 'created_at', 'training_run')
    list_filter = ('is_active', 'model_name')
    search_fields = ('model_name', 'file_path')


@admin.register(ModelMetrics)
class ModelMetricsAdmin(admin.ModelAdmin):
    list_display = ('id', 'model_name', 'precision', 'recall', 'f1', 'roc_auc', 'train_rows', 'test_rows', 'created_at')
    list_filter = ('model_name', 'created_at')
    search_fields = ('model_name',)
