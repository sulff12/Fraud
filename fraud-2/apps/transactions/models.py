from __future__ import annotations

from django.conf import settings
from django.db import models
class UploadBatch(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    original_filename = models.CharField(max_length=255)
    rows_imported = models.PositiveIntegerField(default=0)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transaction_uploads',
    )
    class Meta:
        ordering = ['-created_at']
        permissions = [
            ("can_import_transactions", "Can import transactions"),
        ]
class Transaction(models.Model):
    timestamp = models.DateTimeField(db_index=True)
    amount = models.DecimalField(max_digits=18, decimal_places=2)
    operation_type = models.CharField(max_length=32, db_index=True)
    sender_balance_before = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    sender_balance_after = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    receiver_balance_before = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    receiver_balance_after = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    balance_diff_sender = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    balance_diff_receiver = models.DecimalField(max_digits=18, decimal_places=2, null=True, blank=True)
    amount_to_balance_ratio = models.FloatField(null=True, blank=True)
    fraud_label = models.BooleanField(null=True, blank=True)
    fraud_probability = models.FloatField(null=True, blank=True, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    upload_batch = models.ForeignKey(
        UploadBatch,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='transactions',
    )

    class Meta:
        ordering = ['-timestamp', '-id']
        indexes = [
            models.Index(fields=['timestamp', 'operation_type']),
            models.Index(fields=['fraud_label', 'fraud_probability']),
        ]

    def __str__(self) -> str:
        return f'Transaction #{self.pk} | {self.operation_type} | {self.amount}'

    @property
    def risk_level(self) -> str:
        from .services import assign_risk
        return assign_risk(self.fraud_probability)


class Alert(models.Model):
    SEVERITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('reviewing', 'Reviewing'),
        ('closed', 'Closed'),
    ]

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='alert')
    severity = models.CharField(max_length=10, choices=SEVERITY_CHOICES)
    reason = models.TextField()
    status = models.CharField(max_length=12, choices=STATUS_CHOICES, default='open')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'Alert for tx #{self.transaction_id} ({self.severity})'


class Case(models.Model):
    PRIORITY_CHOICES = [
        ('medium', 'Medium'),
        ('high', 'High'),
    ]
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('investigating', 'Investigating'),
        ('closed', 'Closed'),
    ]

    transaction = models.OneToOneField(Transaction, on_delete=models.CASCADE, related_name='case')
    title = models.CharField(max_length=255)
    priority = models.CharField(max_length=10, choices=PRIORITY_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    summary = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.title
