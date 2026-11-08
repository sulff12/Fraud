from __future__ import annotations

from django.db import models


class TrainingRun(models.Model):
    STATUS_CHOICES = [
        ('running', 'Running'),
        ('success', 'Success'),
        ('failed', 'Failed'),
    ]

    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default='running')
    best_model_name = models.CharField(max_length=128, blank=True)
    selection_metric = models.FloatField(null=True, blank=True)
    summary_json = models.JSONField(default=dict, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ['-started_at']
        permissions = [
            ("can_run_training", "Can run model training"),
            ("can_run_scoring", "Can run transaction scoring"),
        ]


class ModelArtifact(models.Model):
    model_name = models.CharField(max_length=128)
    file_path = models.CharField(max_length=512)
    is_active = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    training_run = models.ForeignKey(TrainingRun, on_delete=models.SET_NULL, null=True, blank=True, related_name='artifacts')

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.model_name} -> {self.file_path}'


class ModelMetrics(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    model_name = models.CharField(max_length=128)
    precision = models.FloatField(null=True, blank=True)
    recall = models.FloatField(null=True, blank=True)
    f1 = models.FloatField(null=True, blank=True)
    roc_auc = models.FloatField(null=True, blank=True)
    train_rows = models.PositiveIntegerField(default=0)
    test_rows = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.model_name
