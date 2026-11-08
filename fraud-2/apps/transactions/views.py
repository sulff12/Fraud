from __future__ import annotations

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import redirect, render

from .forms import TransactionImportForm
from .models import Alert, Case, Transaction, UploadBatch
from .services import get_risk_thresholds, import_transactions_from_csv


@login_required
@permission_required('transactions.can_import_transactions', raise_exception=True)
def import_transactions_view(request):
    bundled_dataset = settings.BASE_DIR / 'data' / 'transactions_prepared_paysim_200k.csv'

    if request.method == 'POST' and request.POST.get('action') == 'import_bundled_dataset':
        if not bundled_dataset.exists():
            messages.error(request, f'Bundled dataset not found: {bundled_dataset}')
            return redirect('transactions:import')

        try:
            with bundled_dataset.open('rb') as fh:
                batch, rows = import_transactions_from_csv(
                    fh,
                    filename=bundled_dataset.name,
                    created_by=request.user,
                )
            messages.success(request, f'Imported {rows} rows from bundled dataset {batch.original_filename}.')
            return redirect('transactions:list')
        except Exception as exc:
            messages.error(request, f'Bundled import failed: {exc}')
            return redirect('transactions:import')

    if request.method == 'POST':
        form = TransactionImportForm(request.POST, request.FILES)
        if form.is_valid():
            uploaded_file = form.cleaned_data['file']
            try:
                batch, rows = import_transactions_from_csv(
                    uploaded_file,
                    filename=uploaded_file.name,
                    created_by=request.user,
                )
                messages.success(request, f'Imported {rows} rows from {batch.original_filename}.')
                return redirect('transactions:list')
            except Exception as exc:
                messages.error(request, f'Import failed: {exc}')
    else:
        form = TransactionImportForm()

    recent_batches = UploadBatch.objects.order_by('-created_at')[:10]
    return render(
        request,
        'transactions/import.html',
        {
            'form': form,
            'recent_batches': recent_batches,
            'bundled_dataset_exists': bundled_dataset.exists(),
            'bundled_dataset_name': bundled_dataset.name,
        },
    )


@login_required
@permission_required('transactions.view_transaction', raise_exception=True)
def transaction_list_view(request):
    queryset = Transaction.objects.select_related('upload_batch').order_by('-timestamp', '-id')

    risk = (request.GET.get('risk') or '').strip().lower()
    search = (request.GET.get('q') or '').strip()
    scored = (request.GET.get('scored') or '').strip().lower()
    operation_type = (request.GET.get('operation_type') or '').strip()

    thresholds = get_risk_thresholds()

    if risk in {'clear', 'low', 'medium', 'high', 'unscored'}:
        if risk == 'high':
            queryset = queryset.filter(fraud_probability__gte=thresholds['high'])
        elif risk == 'medium':
            queryset = queryset.filter(
                fraud_probability__gte=thresholds['medium'],
                fraud_probability__lt=thresholds['high'],
            )
        elif risk == 'low':
            queryset = queryset.filter(
                fraud_probability__gte=thresholds['low'],
                fraud_probability__lt=thresholds['medium'],
            )
        elif risk == 'clear':
            queryset = queryset.filter(fraud_probability__lt=thresholds['low'])
        elif risk == 'unscored':
            queryset = queryset.filter(fraud_probability__isnull=True)

    if scored == 'yes':
        queryset = queryset.filter(fraud_probability__isnull=False)
    elif scored == 'no':
        queryset = queryset.filter(fraud_probability__isnull=True)

    if search:
        if search.isdigit():
            queryset = queryset.filter(
                Q(id=int(search)) | Q(operation_type__icontains=search)
            )
        else:
            queryset = queryset.filter(operation_type__icontains=search)

    if operation_type:
        queryset = queryset.filter(operation_type__iexact=operation_type)

    paginator = Paginator(queryset, 50)
    page = paginator.get_page(request.GET.get('page'))

    querydict = request.GET.copy()
    querydict.pop('page', None)
    pagination_query = querydict.urlencode()

    operation_types = list(
        Transaction.objects.exclude(operation_type__isnull=True)
        .exclude(operation_type__exact='')
        .order_by('operation_type')
        .values_list('operation_type', flat=True)
        .distinct()
    )

    risk_counts = {
        'high': Transaction.objects.filter(fraud_probability__gte=thresholds['high']).count(),
        'medium': Transaction.objects.filter(
            fraud_probability__gte=thresholds['medium'],
            fraud_probability__lt=thresholds['high'],
        ).count(),
        'low': Transaction.objects.filter(
            fraud_probability__gte=thresholds['low'],
            fraud_probability__lt=thresholds['medium'],
        ).count(),
        'clear': Transaction.objects.filter(fraud_probability__lt=thresholds['low']).count(),
        'unscored': Transaction.objects.filter(fraud_probability__isnull=True).count(),
    }

    context = {
        'page': page,
        'filters': {
            'risk': risk,
            'q': search,
            'scored': scored,
            'operation_type': operation_type,
        },
        'risk_counts': risk_counts,
        'thresholds': thresholds,
        'operation_types': operation_types,
        'pagination_query': pagination_query,
        'current_count': paginator.count,
    }
    return render(request, 'transactions/list.html', context)


@login_required
@permission_required('transactions.view_alert', raise_exception=True)
def alerts_list_view(request):
    severity = (request.GET.get('severity') or '').strip().lower()
    status = (request.GET.get('status') or '').strip().lower()

    queryset = Alert.objects.select_related('transaction').order_by('-created_at')
    if severity in {'low', 'medium', 'high'}:
        queryset = queryset.filter(severity=severity)
    if status in {'open', 'reviewing', 'closed'}:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 50)
    page = paginator.get_page(request.GET.get('page'))

    querydict = request.GET.copy()
    querydict.pop('page', None)
    pagination_query = querydict.urlencode()

    return render(
        request,
        'transactions/alerts.html',
        {
            'page': page,
            'filters': {
                'severity': severity,
                'status': status,
            },
            'pagination_query': pagination_query,
            'totals': {
                'open': Alert.objects.filter(status='open').count(),
                'reviewing': Alert.objects.filter(status='reviewing').count(),
                'closed': Alert.objects.filter(status='closed').count(),
            },
        },
    )


@login_required
@permission_required('transactions.view_case', raise_exception=True)
def cases_list_view(request):
    priority = (request.GET.get('priority') or '').strip().lower()
    status = (request.GET.get('status') or '').strip().lower()

    queryset = Case.objects.select_related('transaction').order_by('-created_at')
    if priority in {'medium', 'high'}:
        queryset = queryset.filter(priority=priority)
    if status in {'open', 'investigating', 'closed'}:
        queryset = queryset.filter(status=status)

    paginator = Paginator(queryset, 50)
    page = paginator.get_page(request.GET.get('page'))

    querydict = request.GET.copy()
    querydict.pop('page', None)
    pagination_query = querydict.urlencode()

    return render(
        request,
        'transactions/cases.html',
        {
            'page': page,
            'filters': {
                'priority': priority,
                'status': status,
            },
            'pagination_query': pagination_query,
            'totals': {
                'open': Case.objects.filter(status='open').count(),
                'investigating': Case.objects.filter(status='investigating').count(),
                'closed': Case.objects.filter(status='closed').count(),
            },
        },
    )