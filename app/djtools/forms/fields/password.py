from django import forms
from django.contrib import auth
from django.core.cache import cache

from djtools.utils import tl


class TokenInput(forms.widgets.TextInput):
    template_name = 'widgets/token.html'

    def get_context(self, name, value, attrs):
        from comum.models import APIExterna

        context = super().get_context(name, value, attrs)
        context['notifica_habilitado'] = APIExterna.NOTIFICA_GOVBR.ativo
        return context


class PasswordField(forms.CharField):
    widget = TokenInput

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pode_assinar_com_gov_br = False
        self.request = None

    def reload(self):
        self.request = tl.get_request()
        self.pode_assinar_com_gov_br = self.request and self.request.user.is_authenticated and self.request.session.get('autenticou_com_govbr', False)
        if not self.pode_assinar_com_gov_br:
            self.widget = forms.widgets.PasswordInput()
            self.label = 'Senha para confirmação'
        else:
            self.label = 'Código de Verificação para confirmação'
            self.widget = TokenInput()

    def clean(self, value):
        cleaned_data = super().clean(value)
        self.reload()
        if self.request and self.required:
            if not self.pode_assinar_com_gov_br:
                try:
                    if value and not auth.authenticate(self.request, username=self.request.user.username, password=value):
                        raise forms.ValidationError('A senha não confere com a do usuário logado.')
                    return
                except Exception as e:
                    raise forms.ValidationError(str(e) or 'Erro ao tentar realizar a autenticação.')
            if not cache.get(f'password_check_{self.request.user.get_vinculo().id}', None):
                raise forms.ValidationError('Código de Verificação Expirou. Você precisa gerar um novo Código de Verificação!')
            elif not value:
                raise forms.ValidationError('Por favor preencha o Código de Verificação!')
            elif str(value) != str(cache.get(f'password_check_{self.request.user.get_vinculo().id}')):
                raise forms.ValidationError('Código de Verificação não confere!')
            else:
                cache.delete(f'password_check_{self.request.user.get_vinculo().id}')
        return cleaned_data
