from django.contrib import admin

from .models import Alert, Case, Transaction, UploadBatch


@admin.register(UploadBatch)
class UploadBatchAdmin(admin.ModelAdmin):
    list_display = ('id', 'original_filename', 'rows_imported', 'created_at', 'created_by')
    search_fields = ('original_filename',)
    list_filter = ('created_at',)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ('id', 'timestamp', 'operation_type', 'amount', 'fraud_label', 'fraud_probability', 'upload_batch')
    list_filter = ('operation_type', 'fraud_label')
    search_fields = ('id', 'operation_type')
    autocomplete_fields = ('upload_batch',)


@admin.register(Alert)
class AlertAdmin(admin.ModelAdmin):
    list_display = ('id', 'transaction', 'severity', 'status', 'created_at')
    list_filter = ('severity', 'status')
    search_fields = ('transaction__id', 'reason')


@admin.register(Case)
class CaseAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'transaction', 'priority', 'status', 'created_at')
    list_filter = ('priority', 'status')
    search_fields = ('title', 'transaction__id', 'summary')
