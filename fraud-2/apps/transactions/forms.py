from django import forms


class TransactionImportForm(forms.Form):
    file = forms.FileField(help_text='CSV file with transaction rows')
