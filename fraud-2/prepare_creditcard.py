from __future__ import annotations

from pathlib import Path

import pandas as pd

INPUT_PATH = Path('data/creditcard.csv')
OUTPUT_PATH = Path('data/transactions_prepared.csv')


def main() -> None:
    if not INPUT_PATH.exists():
        raise FileNotFoundError(f'File not found: {INPUT_PATH}')

    df = pd.read_csv(INPUT_PATH)
    prepared = pd.DataFrame()
    prepared['timestamp'] = pd.to_datetime(df['Time'], unit='s', origin='unix')
    prepared['amount'] = pd.to_numeric(df['Amount'], errors='coerce').fillna(0.0)
    prepared['operation_type'] = 'card_payment'
    prepared['sender_balance_before'] = 0.0
    prepared['sender_balance_after'] = 0.0
    prepared['receiver_balance_before'] = 0.0
    prepared['receiver_balance_after'] = 0.0
    prepared['balance_diff_sender'] = 0.0
    prepared['balance_diff_receiver'] = 0.0
    prepared['amount_to_balance_ratio'] = prepared['amount']
    prepared['fraud_label'] = pd.to_numeric(df['Class'], errors='coerce').fillna(0).astype(int)

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    prepared.to_csv(OUTPUT_PATH, index=False)
    print(f'OK: saved {prepared.shape[0]} rows to {OUTPUT_PATH}')


if __name__ == '__main__':
    main()
