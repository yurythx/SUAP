from django import forms

forms.widgets.Textarea.template_name = 'widgets/textarea.html'
forms.widgets.PasswordInput.template_name = 'widgets/password.html'
forms.widgets.TextInput.template_name = 'widgets/input.html'
forms.widgets.Select.template_name = 'widgets/select.html'
forms.widgets.NumberInput.template_name = 'widgets/input.html'
forms.widgets.DateInput.template_name = 'widgets/input.html'
forms.widgets.DateTimeInput.template_name = 'widgets/input.html'
forms.widgets.TimeInput.template_name = 'widgets/input.html'
forms.widgets.CheckboxInput.template_name = 'widgets/checkbox.html'
