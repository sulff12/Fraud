from django.urls import path

from .views import alerts_list_view, cases_list_view, import_transactions_view, transaction_list_view

app_name = 'transactions'

urlpatterns = [
    path('import/', import_transactions_view, name='import'),
    path('', transaction_list_view, name='list'),
    path('alerts/', alerts_list_view, name='alerts'),
    path('cases/', cases_list_view, name='cases'),
]
