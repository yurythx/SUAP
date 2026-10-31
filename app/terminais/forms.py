from django import forms


class DigitalForm(forms.Form):
    matricula = forms.CharField(label='Matrícula', max_length=10, required=True)
    template = forms.CharField(label='Template', required=True)
