from __future__ import annotations

from pathlib import Path

import pandas as pd

INPUT_PATH = Path('data/paysim.csv')
OUTPUT_PATH = Path('data/transactions_prepared.csv')
CHUNK_SIZE = 100_000


def transform_chunk(df: pd.DataFrame) -> pd.DataFrame:
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
        df['timestamp'] = pd.to_datetime(df['step'], unit='h', origin='unix')

    df['balance_diff_sender'] = df['sender_balance_before'] - df['sender_balance_after']
    df['balance_diff_receiver'] = df['receiver_balance_after'] - df['receiver_balance_before']
    df['amount_to_balance_ratio'] = df['amount'] / (df['sender_balance_before'] + 1.0)
    df['fraud_label'] = pd.to_numeric(df.get('fraud_label', 0), errors='coerce').fillna(0).astype(int)

    return df[[
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
    ]]


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f'File not found: {INPUT_PATH}')

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    first_chunk = True
    total_rows = 0
    for chunk in pd.read_csv(INPUT_PATH, chunksize=CHUNK_SIZE):
        prepared = transform_chunk(chunk)
        prepared.to_csv(OUTPUT_PATH, mode='w' if first_chunk else 'a', index=False, header=first_chunk)
        total_rows += len(prepared)
        first_chunk = False
        print(f'Processed {total_rows} rows...')
    print(f'OK: saved {total_rows} rows to {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
