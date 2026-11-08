import pandas as pd
import matplotlib.pyplot as plt

df = pd.read_csv('data/transactions_prepared_paysim_200k.csv')
counts = df['fraud_label'].value_counts().sort_index()

plt.figure(figsize=(8, 5))
ax = counts.plot(kind='bar')
plt.title('fraud_label белгісі бойынша транзакциялардың үлестірімі')
plt.xlabel('fraud_label')
plt.ylabel('Транзакциялар саны')
plt.xticks(rotation=0)

for i, v in enumerate(counts):
    ax.text(i, v + max(counts)*0.01, str(v), ha='center')

plt.tight_layout()
plt.savefig('data/fraud_label_distribution.png', dpi=300)
plt.show()