from django.urls import path

from .views import score_view, train_view

app_name = 'ml'

urlpatterns = [
    path('train/', train_view, name='train'),
    path('score/', score_view, name='score'),
]
