# Fraud Control Center

Пересобранный Django-проект для дипломного антифрод-приложения с PostgreSQL/pgAdmin, подготовленным датасетом PaySim 200k, обучением моделей, пакетным скорингом, алертами и кейсами.

## Что в этой версии исправлено
- подключена нормальная пользовательская авторизация через `/accounts/login/`
- добавлен цельный интерфейс: дашборд, импорт, транзакции, алерты, кейсы, train, score
- список транзакций теперь фильтруется по `high / medium / low / clear / unscored`, `operation_type` и статусу скоринга
- обучение запускает `LogisticRegression`, `RandomForest`, `GradientBoosting` и сохраняет лучшую модель по `average precision`
- скоринг идёт пакетно, а не грузит всю таблицу в память одним куском
- после полного скоринга алерты и кейсы синхронизируются повторно, включая закрытие resolved записей
- в проект вложен готовый файл `data/transactions_prepared_paysim_200k.csv`
- есть кнопка импорта встроенного PaySim прямо из интерфейса

## Структура
- `/` — дашборд
- `/accounts/login/` — вход
- `/transactions/import/` — импорт CSV или встроенного PaySim 200k
- `/transactions/` — список транзакций с фильтрами
- `/transactions/alerts/` — алерты с фильтрами
- `/transactions/cases/` — кейсы с фильтрами
- `/ml/train/` — обучение моделей
- `/ml/score/` — скоринг активной моделью
- `/admin/` — Django admin

## Быстрый старт на Windows + pgAdmin
1. В pgAdmin создай БД `fraud_db` или используй уже существующую чистую БД.
2. Скопируй `.env.example` в `.env` и укажи свой пароль PostgreSQL.
3. Создай окружение и установи зависимости:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

Если PowerShell блокирует запуск скриптов:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\.venv\Scripts\Activate.ps1
```

4. Прогони миграции и создай пользователя:

```powershell
python manage.py migrate
python manage.py createsuperuser
```

5. Запусти сервер:

```powershell
python manage.py runserver
```

## Быстрый путь с готовым PaySim
После входа открой `/transactions/import/` и нажми **«Импортировать PaySim 200k»**.

Либо из консоли:

```powershell
python manage.py import_transactions --file data\transactions_prepared_paysim_200k.csv
python manage.py train_model
python manage.py score_transactions
python manage.py runserver
```

## Переменные `.env`
- `DB_ENGINE=postgres` для PostgreSQL через pgAdmin
- `DB_ENGINE=sqlite` для локального быстрого smoke test
- `RISK_LOW_THRESHOLD`, `RISK_MEDIUM_THRESHOLD`, `RISK_HIGH_THRESHOLD` — пороги риска

Если после скоринга нет `medium`, это не обязательно баг. Часто модель реально даёт распределение без середины для выбранных порогов. Тогда скорректируй `.env` и перезапусти **полный** скоринг.
