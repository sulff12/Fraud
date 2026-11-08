from __future__ import annotations

from pathlib import Path

import joblib
import pandas as pd
from django.conf import settings
from django.db import transaction as db_transaction
from django.utils import timezone
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingClassifier, RandomForestClassifier
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import average_precision_score, f1_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from apps.transactions.models import Transaction
from apps.transactions.services import sync_alerts_and_cases
from .models import ModelArtifact, ModelMetrics, TrainingRun

FEATURE_COLUMNS = [
    'amount',
    'operation_type',
    'sender_balance_before',
    'sender_balance_after',
    'receiver_balance_before',
    'receiver_balance_after',
    'balance_diff_sender',
    'balance_diff_receiver',
    'amount_to_balance_ratio',
]
NUMERIC_COLUMNS = [column for column in FEATURE_COLUMNS if column != 'operation_type']
CATEGORICAL_COLUMNS = ['operation_type']
MODEL_DIR = Path(settings.MEDIA_ROOT) / 'artifacts'


class TrainingError(Exception):
    pass


def _build_preprocessor() -> ColumnTransformer:
    numeric_transformer = Pipeline(
        steps=[
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler()),
        ]
    )
    categorical_transformer = Pipeline(
        steps=[
            ('imputer', SimpleImputer(strategy='most_frequent')),
            ('onehot', OneHotEncoder(handle_unknown='ignore', sparse_output=False)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ('num', numeric_transformer, NUMERIC_COLUMNS),
            ('cat', categorical_transformer, CATEGORICAL_COLUMNS),
        ]
    ) 


def _candidate_models() -> dict:
    return {
        'logreg_v1': LogisticRegression(max_iter=800, class_weight='balanced', solver='liblinear', random_state=42),
        'random_forest_v1': RandomForestClassifier(
            n_estimators=250,
            max_depth=12,
            min_samples_leaf=4,
            class_weight='balanced_subsample',
            random_state=42,
            n_jobs=-1,
        ),
        'gradient_boost_v1': GradientBoostingClassifier(random_state=42),
    }


def _training_dataframe() -> pd.DataFrame:
    rows = list(Transaction.objects.filter(fraud_label__isnull=False).values('id', *FEATURE_COLUMNS, 'fraud_label'))
    if not rows:
        raise TrainingError('No labeled transactions were found for training.')
    df = pd.DataFrame(rows)
    if df['fraud_label'].nunique() < 2:
        raise TrainingError('Training requires at least two classes in fraud_label.')
    return df


def _pipeline(model) -> Pipeline:
    return Pipeline(steps=[('preprocessor', _build_preprocessor()), ('classifier', model)])


@db_transaction.atomic
def train_models() -> dict:
    df = _training_dataframe()
    run = TrainingRun.objects.create(status='running')

    try:
        X = df[FEATURE_COLUMNS].copy()
        y = df['fraud_label'].astype(int)
        stratify = y if y.nunique() > 1 else None

        X_train, X_test, y_train, y_test = train_test_split(
            X,
            y,
            test_size=0.20,
            random_state=42,
            stratify=stratify,
        )

        MODEL_DIR.mkdir(parents=True, exist_ok=True)
        run_summary = {}
        best_payload = None
        best_metric = -1.0
        best_model_name = ''

        for model_name, estimator in _candidate_models().items():
            pipeline = _pipeline(estimator)
            pipeline.fit(X_train, y_train)
            probabilities = pipeline.predict_proba(X_test)[:, 1]
            predictions = (probabilities >= 0.50).astype(int)

            avg_precision = average_precision_score(y_test, probabilities)
            precision = precision_score(y_test, predictions, zero_division=0)
            recall = recall_score(y_test, predictions, zero_division=0)
            f1 = f1_score(y_test, predictions, zero_division=0)
            roc_auc = roc_auc_score(y_test, probabilities) if y_test.nunique() > 1 else None

            ModelMetrics.objects.create(
                model_name=model_name,
                precision=precision,
                recall=recall,
                f1=f1,
                roc_auc=roc_auc,
                train_rows=len(X_train),
                test_rows=len(X_test),
            )

            run_summary[model_name] = {
                'average_precision': round(float(avg_precision), 6),
                'precision': round(float(precision), 6),
                'recall': round(float(recall), 6),
                'f1': round(float(f1), 6),
                'roc_auc': round(float(roc_auc), 6) if roc_auc is not None else None,
            }

            if avg_precision > best_metric:
                best_metric = float(avg_precision)
                best_model_name = model_name
                best_payload = {
                    'model_name': model_name,
                    'pipeline': pipeline,
                    'trained_at': timezone.now().isoformat(),
                    'feature_columns': FEATURE_COLUMNS,
                    'numeric_columns': NUMERIC_COLUMNS,
                    'categorical_columns': CATEGORICAL_COLUMNS,
                    'metrics': run_summary[model_name],
                }

        artifact_filename = f'{timezone.now().strftime("%Y%m%d_%H%M%S")}_{best_model_name}.joblib'
        artifact_path = MODEL_DIR / artifact_filename
        joblib.dump(best_payload, artifact_path)

        ModelArtifact.objects.filter(is_active=True).update(is_active=False)
        artifact = ModelArtifact.objects.create(
            model_name=best_model_name,
            file_path=str(artifact_path.relative_to(settings.BASE_DIR)),
            is_active=True,
            training_run=run,
        )

        run.status = 'success'
        run.finished_at = timezone.now()
        run.best_model_name = best_model_name
        run.selection_metric = best_metric
        run.summary_json = run_summary
        run.save(update_fields=['status', 'finished_at', 'best_model_name', 'selection_metric', 'summary_json'])

        return {
            'training_run_id': run.id,
            'best_model_name': best_model_name,
            'selection_metric': best_metric,
            'artifact_path': artifact.file_path,
            'metrics': run_summary,
            'train_rows': len(X_train),
            'test_rows': len(X_test),
        }
    except Exception as exc:
        run.status = 'failed'
        run.finished_at = timezone.now()
        run.notes = str(exc)
        run.save(update_fields=['status', 'finished_at', 'notes'])
        raise


def load_active_artifact() -> dict:
    artifact = ModelArtifact.objects.filter(is_active=True).order_by('-created_at').first()
    if not artifact:
        raise TrainingError('No active model artifact found. Run training first.')
    absolute_path = settings.BASE_DIR / artifact.file_path
    payload = joblib.load(absolute_path)
    payload['artifact'] = artifact
    return payload


@db_transaction.atomic
def score_transactions(rescore_all: bool = True, batch_size: int = 5000) -> dict:
    payload = load_active_artifact()
    queryset = Transaction.objects.all().order_by('id') if rescore_all else Transaction.objects.filter(fraud_probability__isnull=True).order_by('id')
    total_rows = queryset.count()
    if total_rows == 0:
        return {
            'scored_rows': 0,
            'alerts_created': 0,
            'alerts_updated': 0,
            'cases_created': 0,
            'cases_updated': 0,
            'artifact': payload['artifact'],
        }

    total_sync = {
        'alerts_created': 0,
        'alerts_updated': 0,
        'cases_created': 0,
        'cases_updated': 0,
    }

    last_pk = 0
    scored_rows = 0

    while True:
        rows = list(queryset.filter(id__gt=last_pk).values('id', *FEATURE_COLUMNS)[:batch_size])
        if not rows:
            break

        df = pd.DataFrame(rows)
        probabilities = payload['pipeline'].predict_proba(df[FEATURE_COLUMNS])[:, 1]
        df['fraud_probability'] = probabilities

        updates = [
            Transaction(id=int(row.id), fraud_probability=float(row.fraud_probability))
            for row in df[['id', 'fraud_probability']].itertuples(index=False)
        ]
        Transaction.objects.bulk_update(updates, ['fraud_probability'], batch_size=batch_size)

        sync_result = sync_alerts_and_cases(df.to_dict('records'), close_resolved=rescore_all)
        for key in total_sync:
            total_sync[key] += sync_result[key]

        scored_rows += len(df)
        last_pk = int(df['id'].max())

    return {
        'scored_rows': scored_rows,
        'artifact': payload['artifact'],
        **total_sync,
    }