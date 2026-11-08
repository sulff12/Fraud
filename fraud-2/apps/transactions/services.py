from __future__ import annotations

from decimal import Decimal

import pandas as pd
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone

from .models import Alert, Case, Transaction, UploadBatch

NORMALIZED_COLUMNS = [
    'timestamp',
    'amount',
    'operation_type',
    'sender_balance_before',
    'sender_balance_after',
    'receiver_balance_before',
    'receiver_balance_after',
    'balance_diff_sender',
    'balance_diff_receiver',
    'amount_to_balance_ratio',
    'fraud_label',
]


def _decimal_or_none(value):
    if pd.isna(value):
        return None
    return Decimal(str(round(float(value), 2)))


def get_risk_thresholds() -> dict[str, float]:
    high = float(getattr(settings, 'RISK_HIGH_THRESHOLD', 0.90))
    medium = float(getattr(settings, 'RISK_MEDIUM_THRESHOLD', 0.75))
    low = float(getattr(settings, 'RISK_LOW_THRESHOLD', 0.50))
    if not (0 <= low <= medium <= high <= 1):
        return {'low': 0.50, 'medium': 0.75, 'high': 0.90}
    return {'low': low, 'medium': medium, 'high': high}


def assign_risk(probability: float | None) -> str:
    thresholds = get_risk_thresholds()
    if probability is None:
        return 'unscored'
    if probability >= thresholds['high']:
        return 'high'
    if probability >= thresholds['medium']:
        return 'medium'
    if probability >= thresholds['low']:
        return 'low'
    return 'clear'


def compute_rule_flags(record: dict) -> list[str]:
    flags: list[str] = []
    amount = float(record.get('amount') or 0)
    sender_before = float(record.get('sender_balance_before') or 0)
    sender_after = float(record.get('sender_balance_after') or 0)
    receiver_before = float(record.get('receiver_balance_before') or 0)
    receiver_after = float(record.get('receiver_balance_after') or 0)

    if amount >= 200_000:
        flags.append('large_amount')
    if sender_before > 0 and amount >= sender_before * 0.90:
        flags.append('drains_sender_balance')
    if sender_before > 0 and abs((sender_before - sender_after) - amount) > max(1.0, amount * 0.10):
        flags.append('sender_balance_mismatch')
    if receiver_after < receiver_before:
        flags.append('receiver_balance_mismatch')
    return flags


def normalize_transactions_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    rename_map = {
        'type': 'operation_type',
        'oldbalanceOrg': 'sender_balance_before',
        'newbalanceOrg': 'sender_balance_after',
        'newbalanceOrig': 'sender_balance_after',
        'oldbalanceDest': 'receiver_balance_before',
        'newbalanceDest': 'receiver_balance_after',
        'isFraud': 'fraud_label',
    }
    df = df.rename(columns=rename_map).copy()

    if 'timestamp' not in df.columns:
        if 'step' in df.columns:
            df['timestamp'] = pd.to_datetime(df['step'], unit='h', origin='unix')
        else:
            raise ValueError("CSV must contain either 'timestamp' or 'step'.")
    else:
        df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')

    required = [
        'timestamp',
        'amount',
        'operation_type',
        'sender_balance_before',
        'sender_balance_after',
        'receiver_balance_before',
        'receiver_balance_after',
    ]
    missing = [column for column in required if column not in df.columns]
    if missing:
        raise ValueError(f'Missing required columns: {missing}')

    numeric_columns = [
        'amount',
        'sender_balance_before',
        'sender_balance_after',
        'receiver_balance_before',
        'receiver_balance_after',
    ]
    for column in numeric_columns:
        df[column] = pd.to_numeric(df[column], errors='coerce').fillna(0.0)

    if 'balance_diff_sender' not in df.columns:
        df['balance_diff_sender'] = df['sender_balance_before'] - df['sender_balance_after']
    if 'balance_diff_receiver' not in df.columns:
        df['balance_diff_receiver'] = df['receiver_balance_after'] - df['receiver_balance_before']
    if 'amount_to_balance_ratio' not in df.columns:
        df['amount_to_balance_ratio'] = df['amount'] / (df['sender_balance_before'] + 1.0)

    df['operation_type'] = df['operation_type'].astype(str).str.strip().replace({'': 'unknown'}).fillna('unknown')
    if 'fraud_label' in df.columns:
        df['fraud_label'] = pd.to_numeric(df['fraud_label'], errors='coerce').fillna(0).astype(int)
    else:
        df['fraud_label'] = None

    return df[NORMALIZED_COLUMNS].copy()


@db_transaction.atomic
def import_transactions_from_csv(file_obj, filename: str, created_by=None, chunk_size: int = 5000) -> tuple[UploadBatch, int]:
    upload_batch = UploadBatch.objects.create(original_filename=filename, created_by=created_by, rows_imported=0)
    total_rows = 0

    for chunk in pd.read_csv(file_obj, chunksize=chunk_size):
        normalized = normalize_transactions_dataframe(chunk)
        objects = []
        for row in normalized.to_dict('records'):
            timestamp = row['timestamp'].to_pydatetime()
            if timezone.is_naive(timestamp):
                timestamp = timezone.make_aware(timestamp, timezone.get_current_timezone())
            objects.append(
                Transaction(
                    timestamp=timestamp,
                    amount=_decimal_or_none(row['amount']) or Decimal('0.00'),
                    operation_type=str(row['operation_type'])[:32],
                    sender_balance_before=_decimal_or_none(row['sender_balance_before']),
                    sender_balance_after=_decimal_or_none(row['sender_balance_after']),
                    receiver_balance_before=_decimal_or_none(row['receiver_balance_before']),
                    receiver_balance_after=_decimal_or_none(row['receiver_balance_after']),
                    balance_diff_sender=_decimal_or_none(row['balance_diff_sender']),
                    balance_diff_receiver=_decimal_or_none(row['balance_diff_receiver']),
                    amount_to_balance_ratio=None if pd.isna(row['amount_to_balance_ratio']) else float(row['amount_to_balance_ratio']),
                    fraud_label=None if pd.isna(row['fraud_label']) else bool(int(row['fraud_label'])),
                    upload_batch=upload_batch,
                )
            )
        Transaction.objects.bulk_create(objects, batch_size=chunk_size)
        total_rows += len(objects)

    upload_batch.rows_imported = total_rows
    upload_batch.save(update_fields=['rows_imported'])
    return upload_batch, total_rows


def sync_alerts_and_cases(scored_rows: list[dict], close_resolved: bool = False) -> dict:
    suspicious_rows: list[dict] = []
    all_row_ids: list[int] = []
    for row in scored_rows:
        all_row_ids.append(int(row['id']))
        flags = compute_rule_flags(row)
        risk = assign_risk(row.get('fraud_probability'))
        if risk in {'low', 'medium', 'high'} or flags:
            suspicious_rows.append({**row, 'flags': flags, 'risk': risk})

    transaction_ids = [row['id'] for row in suspicious_rows]
    existing_alerts = {item.transaction_id: item for item in Alert.objects.filter(transaction_id__in=all_row_ids)}
    existing_cases = {item.transaction_id: item for item in Case.objects.filter(transaction_id__in=all_row_ids)}

    alerts_to_create = []
    alerts_to_update = []
    cases_to_create = []
    cases_to_update = []

    for row in suspicious_rows:
        severity = (
            'high'
            if row['risk'] == 'high' or 'sender_balance_mismatch' in row['flags']
            else 'medium'
            if row['risk'] == 'medium' or len(row['flags']) >= 2
            else 'low'
        )
        reason_parts = [f"model_probability={row.get('fraud_probability', 0):.4f}"]
        if row['flags']:
            reason_parts.append('rules=' + ', '.join(row['flags']))
        reason = '; '.join(reason_parts)

        existing_alert = existing_alerts.get(row['id'])
        if existing_alert:
            existing_alert.severity = severity
            existing_alert.reason = reason
            if severity == 'low' and existing_alert.status == 'closed':
                existing_alert.status = 'open'
            elif severity in {'medium', 'high'} and existing_alert.status == 'closed':
                existing_alert.status = 'reviewing'
            alerts_to_update.append(existing_alert)
        else:
            alerts_to_create.append(Alert(transaction_id=row['id'], severity=severity, reason=reason, status='open'))

        if severity in {'medium', 'high'}:
            summary = f"Probability={row.get('fraud_probability', 0):.4f}. Flags: {', '.join(row['flags']) if row['flags'] else 'none'}"
            existing_case = existing_cases.get(row['id'])
            if existing_case:
                existing_case.priority = severity
                existing_case.summary = summary
                if existing_case.status == 'closed':
                    existing_case.status = 'investigating'
                cases_to_update.append(existing_case)
            else:
                cases_to_create.append(
                    Case(
                        transaction_id=row['id'],
                        title=f'Review transaction #{row["id"]}',
                        priority=severity,
                        summary=summary,
                        status='open',
                    )
                )

    if close_resolved and all_row_ids:
        suspicious_set = set(transaction_ids)
        for tx_id, existing_alert in existing_alerts.items():
            if tx_id not in suspicious_set and existing_alert.status != 'closed':
                existing_alert.status = 'closed'
                existing_alert.reason = f'{existing_alert.reason}; resolved_after_rescore=1'
                alerts_to_update.append(existing_alert)
        for tx_id, existing_case in existing_cases.items():
            if tx_id not in suspicious_set and existing_case.status != 'closed':
                existing_case.status = 'closed'
                existing_case.summary = f'{existing_case.summary} | resolved_after_rescore=1'
                cases_to_update.append(existing_case)

    if alerts_to_create:
        Alert.objects.bulk_create(alerts_to_create, batch_size=1000)
    if alerts_to_update:
        Alert.objects.bulk_update(alerts_to_update, ['severity', 'reason', 'status', 'updated_at'], batch_size=1000)
    if cases_to_create:
        Case.objects.bulk_create(cases_to_create, batch_size=1000)
    if cases_to_update:
        Case.objects.bulk_update(cases_to_update, ['priority', 'summary', 'status', 'updated_at'], batch_size=1000)

    return {
        'alerts_created': len(alerts_to_create),
        'alerts_updated': len(alerts_to_update),
        'cases_created': len(cases_to_create),
        'cases_updated': len(cases_to_update),
    }
