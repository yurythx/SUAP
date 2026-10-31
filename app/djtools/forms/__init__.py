# ruff: noqa: F403
import datetime
from typing import Any

from django import forms
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group, Permission
from django.forms import *
from django.utils import timezone

from djtools.forms.fields import *
from djtools.forms.fields import DateFieldPlus, FileFieldPlus, ModelChoiceFieldPlus
from djtools.forms.utils import *
from djtools.forms.widgets import *
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import get_opensearch_query_access_logs, get_opensearch_query_email_logs, get_opensearch_query_history

from .base import *
from .base import FormPlus

# Forms específicos do djtools


class AtribuirPermissaoForm(FormPlus):
    usuarios = forms.CharField(
        label='Usuários', required=True, widget=forms.Textarea(), help_text='Lista de username separada por ; ou , ou quebra de linha'
    )
    grupos = forms.ModelMultipleChoiceField(Group.objects.all(), widget=AutocompleteWidget(multiple=True), required=False)
    permissoes = forms.ModelMultipleChoiceField(
        Permission.objects.all(), widget=AutocompleteWidget(multiple=True), label='Permissões', required=False
    )


class NotificacaoGrupoForm(FormPlus):
    titulo = forms.CharField(label='Título', required=True, initial='Mensagem para Grupo')
    remetente = forms.CharField(label='E-mail', required=True, help_text='E-mail do remetente', initial=settings.DEFAULT_FROM_EMAIL)
    texto = forms.CharField(
        widget=forms.Textarea({'rows': 10, 'cols': 80}),
        required=True,
        label='Mensagem',
        help_text='Pode conter quebras de linha, porém não deve conter tags HTML.',
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if not self.request.user.is_superuser:
            v = self.request.user.get_vinculo()
            self.fields['remetente'].initial = v.email_notificacao if v else ''
            self.fields['remetente'].widget.attrs['readonly'] = True
            self.fields['remetente'].widget.attrs['disabled'] = True


class ConfiguracaoForm(FormPlus):
    vapid_private_key = forms.CharField(label='Chave privada VAPID para envio de Web Push Notification', required=False)
    vapid_public_key = forms.CharField(label='Chave pública VAPID para envio de Web Push Notification', required=False)

    opensearch_host = forms.CharField(label='Host do OpenSearch', required=False, help_text='Exemplo: opensearch.ifrn.local')
    opensearch_port = forms.IntegerField(label='Porta do OpenSearch', required=False, initial=9200)
    opensearch_user = forms.CharField(label='Usuário do OpenSearch', required=False, help_text='Exemplo: admin')
    opensearch_password = forms.CharField(label='Senha do OpenSearch', required=False)
    opensearch_timeout = forms.IntegerField(label='Timeout do OpenSearch', required=False, initial=30)
    opensearch_history_index = forms.CharField(label='Índice do History do OpenSearch', required=False, initial='history*')
    opensearch_access_logs_index = forms.CharField(label='Índice dos Logs de Acesso do OpenSearch', required=False, initial='access-log*')
    opensearch_email_index = forms.CharField(label='Índice do Envio de Emails do OpenSearch', required=False, initial='email*')

    tempo_validade_codigo_autenticacao = forms.IntegerField(label='Tempo em minutos que token two factor expira', required=False, initial=5)
    cadastrar_municipio_ao_consultar_cep = forms.BooleanField(
        label='Cadastrar município ao consultar CEP',
        required=False,
        help_text='Marque essa opção se deseja que os municípios relacionadas aos CEPs preenchidos nos formulários de endereço sejam cadastrados automaticamente caso não constem na base de dados.',
    )


class TwoFactorAuthenticationForm(forms.Form):
    code = forms.IntegerField(required=True, label='Código')

    SUBMIT_LABEL = 'Autenticar'

    def __init__(self, *args, request=None, **kwargs):
        self.request = request
        super().__init__(*args, **kwargs)
        # mascarando o e-mail secundário (x******y@email.com)
        email = list(request.user.get_vinculo().email_pessoal or '')
        if '@' in email:
            for i in range(1, email.index('@') - 1):
                email[i] = '*'
            email = ''.join(email)
        self.fields['code'].help_text = f'Informe o código de autenticação com 6 dígitos enviado para "{email}".'

    def clean_code(self):
        from djtools.forms import ReCaptchaField
        from djtools.models import TwoFactorAuthenticationCode

        qs = TwoFactorAuthenticationCode.objects.filter(user=self.request.user, expires__gte=datetime.datetime.now(), code=self.cleaned_data['code'])
        if qs.exists():
            return self.cleaned_data['code']
        else:
            # sinalizando na seção que o código foi informado errado para que o recaptcha seja exibido
            self.request.session['2fa'] = 0
            self.request.session.save()
            self.fields['recaptcha'] = ReCaptchaField(label='')
            raise forms.ValidationError('Código de autenticação inválido')


class RestaurarArquivosMediaForm(FormPlus):
    arquivo = FileFieldPlus(help_text='Lista de arquivos separadas por linha', filetypes=['txt'], required=True)

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        try:
            self.arquivos = [line.decode().strip() for line in arquivo.readlines() if line.decode().strip()]
        except Exception:
            raise forms.ValidationError('Formato do arquivo inválido')
        return arquivo


class HistoryForm(FormPlus):
    METHOD = 'GET'
    CADASTRO = 'created'
    EDICAO = 'updated'
    EXCLUSAO = 'deleted'

    TIPO_CHOICES = [['', '-----------'], [CADASTRO, 'Cadastro'], [EDICAO, 'Edição'], [EXCLUSAO, 'Exclusão']]

    user = ModelChoiceFieldPlus(None, label='Usuário', required=False)
    data_inicio = DateFieldPlus(label='Data de Início', required=False)
    data_fim = DateFieldPlus(label='Data de Fim', required=False)

    acao = forms.ChoiceField(label='Ação', choices=TIPO_CHOICES, required=False)
    modelo = forms.CharField(label='Modelo', help_text='Exemplo: rh.servidor', required=False)
    ref = forms.IntegerField(label='Referência', required=False)
    exibir_relacionamentos = forms.BooleanField(label='Exibir Relacionamentos', required=False, initial=False)
    campos_alterados = forms.CharField(label='Campos Alterados', required=False, help_text='Exemplo: nome,cpf')
    valores_alterados = forms.CharField(label='Valores Alterados', required=False, help_text='Exemplo: 12345678900,12345678901')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        from comum.models import User

        self.fields['user'].queryset = User.objects.all()

    def gerar_descricao(self, source, user):
        match source['status']:
            case 'deleted':
                acao = 'excluiu'
            case 'created':
                acao = 'criou'
            case _:
                acao = 'atualizou'
        try:
            modelo = apps.get_model(source['model'])._meta.verbose_name
        except Exception:
            modelo = source['model']
        if user:
            usuario = 'usuário'
        else:
            usuario = 'sistema'
        descricao = f'O {usuario} {acao} {modelo} #{source["pk"]}'
        return descricao

    def clean_modelo(self) -> dict[str, Any]:
        modelo = 'modelo' in self.cleaned_data and self.cleaned_data['modelo'] or None
        try:
            if modelo:
                apps.get_model(modelo)
        except Exception:
            raise forms.ValidationError('Modelo inválido')
        return modelo

    def clean_ref(self) -> int:
        ref = 'ref' in self.cleaned_data and self.cleaned_data['ref'] or None
        modelo = 'modelo' in self.cleaned_data and self.cleaned_data['modelo'] or None
        if ref and not modelo:
            raise forms.ValidationError('Para filtrar pela referência, o campo "Modelo" deve ser preenchido.')
        return ref

    def clean_exibir_relacionamentos(self) -> bool:
        exibir_relacionamentos = 'exibir_relacionamentos' in self.cleaned_data and self.cleaned_data['exibir_relacionamentos'] or None
        if exibir_relacionamentos and (not self.cleaned_data.get('ref') or not self.cleaned_data.get('modelo')):
            raise forms.ValidationError('Para exibir relacionamentos, os campos "Referência" e "Modelo" devem ser preenchidos.')
        return exibir_relacionamentos

    def processar(self, page):
        import pytz

        from comum.models import User

        tz = pytz.timezone(settings.TIME_ZONE)

        user = 'user' in self.cleaned_data and self.cleaned_data['user'] or None
        data_inicio = 'data_inicio' in self.cleaned_data and self.cleaned_data['data_inicio'] or None
        data_fim = 'data_fim' in self.cleaned_data and self.cleaned_data['data_fim'] or None

        acao = 'acao' in self.cleaned_data and self.cleaned_data['acao'] or None
        modelo = 'modelo' in self.cleaned_data and self.cleaned_data['modelo'] or None
        ref = 'ref' in self.cleaned_data and self.cleaned_data['ref'] or None
        exibir_relacionamentos = 'exibir_relacionamentos' in self.cleaned_data and self.cleaned_data['exibir_relacionamentos'] or None
        campos_alterados = 'campos_alterados' in self.cleaned_data and self.cleaned_data['campos_alterados'] or None
        valores_alterados = 'valores_alterados' in self.cleaned_data and self.cleaned_data['valores_alterados'] or None

        queries = []
        sort = [{'request.last_update': 'desc'}]

        if user:
            queries.append(f'(request.author.username:"{user.username}")')
        if data_inicio:
            queries.append(f'(request.last_update:[{data_inicio} TO *])')
        if data_fim:
            queries.append(f'(request.last_update:[* TO {data_fim}])')
        if acao:
            queries.append(f'(status:{acao})')
        if campos_alterados:
            campos = ' OR '.join([f'"{campo.strip()}"' for campo in campos_alterados.split(',')])
            queries.append(f'(diff.field:{campos})')
        if valores_alterados:
            valores = ' OR '.join([f'"{valor.strip()}"' for valor in valores_alterados.split(',')])
            queries.append(f'(diff.new_value:({valores}) OR diff.old_value:({valores}))')
        if modelo:
            if ref:
                obj = apps.get_model(modelo).objects.filter(pk=ref).first()
                if obj and exibir_relacionamentos:
                    queries.append(f'(pk:{ref} AND model:{modelo}) OR (diff.new_value:"{obj}") OR (diff.old_value:"{obj}")')
                else:
                    queries.append(f'(pk:{ref})')
                    queries.append(f'(model:{modelo})')
            else:
                queries.append(f'(model:{modelo})')
        query = {'query_string': {'query': ' AND '.join(queries)}}
        response = get_opensearch_query_history(query, page=page - 1, sort=sort, size=100)
        logs = response['hits']['hits'][:]
        for hits in logs:
            if 'request' in hits['_source']:
                hits['user'] = User.objects.filter(username=hits['_source']['request']['author']['username']).first()
                hits['id'] = hits['_id']
                hits['dt'] = tz.fromutc(datetime.datetime.fromisoformat(hits['_source']['request']['last_update']))
                hits['descricao'] = self.gerar_descricao(hits['_source'], hits['user'])
        return logs


class AccessLogForm(FormPlus):
    METHOD = 'GET'
    GET = 'GET'
    POST = 'POST'
    DELETE = 'DELETE'
    HEAD = 'HEAD'
    PUT = 'PUT'
    PATCH = 'PATCH'
    OPTIONS = 'OPTIONS'

    TIPO_CHOICES = [['', '-----------'], [GET, GET], [POST, POST], [DELETE, DELETE], [HEAD, HEAD], [PUT, PUT], [PATCH, PATCH], [OPTIONS, OPTIONS]]

    user = ModelChoiceFieldPlus(None, label='Usuário', required=False)
    data_inicio = DateFieldPlus(label='Data de Início', required=False)
    data_fim = DateFieldPlus(label='Data de Fim', required=False)

    metodo = forms.ChoiceField(label='Método', choices=TIPO_CHOICES, required=False)
    path = forms.CharField(label='Caminho', required=False, help_text='Exemplo: /api/v1/servidores/')
    status = forms.IntegerField(label='Status', required=False, help_text='Exemplo: 200')
    ip_address = forms.GenericIPAddressField(label='IP', required=False, help_text='Exemplo: 0.0.0.0')
    servidor = forms.CharField(label='Servidor', required=False, help_text='Exemplo: servidor.ifrn.local')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        from comum.models import User

        self.fields['user'].queryset = User.objects.all()

    def processar(self, page):
        from comum.models import User

        user = 'user' in self.cleaned_data and self.cleaned_data['user'] or None
        data_inicio = 'data_inicio' in self.cleaned_data and self.cleaned_data['data_inicio'] or None
        data_fim = 'data_fim' in self.cleaned_data and self.cleaned_data['data_fim'] or None

        metodo = 'metodo' in self.cleaned_data and self.cleaned_data['metodo'] or None
        path = 'path' in self.cleaned_data and self.cleaned_data['path'] or None
        status = 'status' in self.cleaned_data and self.cleaned_data['status'] or None
        ip_address = 'ip_address' in self.cleaned_data and self.cleaned_data['ip_address'] or None
        servidor = 'servidor' in self.cleaned_data and self.cleaned_data['servidor'] or None

        queries = []
        sort = [{'@timestamp': {'order': 'desc', 'unmapped_type': 'long'}}]

        if user:
            queries.append(f'(user:"{user.username}")')
        if data_inicio:
            queries.append(f'(@timestamp:[{data_inicio} TO *])')
        if data_fim:
            queries.append(f'(@timestamp:[* TO {data_fim}])')
        if metodo:
            queries.append(f'(method:"{metodo}")')
        if path:
            queries.append(f'(path:"{path}")')
        if status:
            queries.append(f'(status_code:{status})')
        if ip_address:
            queries.append(f'(ip_address:"{ip_address}")')
        if servidor:
            queries.append(f'(server:"{servidor}")')
        query = {'query_string': {'query': ' AND '.join(queries)}}
        response = get_opensearch_query_access_logs(query, page=page - 1, sort=sort, size=100)
        logs = response['hits']['hits'][:]
        for hits in logs:
            hits['user'] = User.objects.filter(username=hits['_source']['user']).first()
            hits['id'] = hits['_id']
            hits['dt'] = timezone.make_aware(timezone.make_naive(datetime.datetime.fromisoformat(hits['_source']['@timestamp'])))
            hits['method'] = hits['_source']['method']
            hits['path'] = hits['_source']['path']
            hits['status'] = hits['_source']['status_code']
            hits['ip_address'] = hits['_source']['ip_address']
            hits['servidor'] = hits['_source']['server']
        return logs


class EmailLogForm(FormPlus):
    METHOD = 'GET'

    data_inicio = DateFieldPlus(label='Data de Início', required=False)
    data_fim = DateFieldPlus(label='Data de Fim', required=False)

    email = forms.CharField(label='Email', required=False)
    assunto = forms.CharField(label='Assunto', required=False)
    servidor = forms.CharField(label='Servidor', required=False, help_text='Exemplo: servidor.ifrn.local')

    def processar(self, page):
        data_inicio = 'data_inicio' in self.cleaned_data and self.cleaned_data['data_inicio'] or None
        data_fim = 'data_fim' in self.cleaned_data and self.cleaned_data['data_fim'] or None
        email = 'email' in self.cleaned_data and self.cleaned_data['email'] or None
        assunto = 'assunto' in self.cleaned_data and self.cleaned_data['assunto'] or None
        servidor = 'servidor' in self.cleaned_data and self.cleaned_data['servidor'] or None

        queries = []
        sort = [{'@timestamp': {'order': 'desc', 'unmapped_type': 'long'}}]

        if data_inicio:
            queries.append(f'(@timestamp:[{data_inicio} TO *])')
        if data_fim:
            queries.append(f'(@timestamp:[* TO {data_fim}])')
        if email:
            queries.append(f'(to:"{email}")')
        if assunto:
            queries.append(f'(subject:"{assunto}")')
        if servidor:
            queries.append(f'(server:"{servidor}")')
        query = {'query_string': {'query': ' AND '.join(queries)}}
        response = get_opensearch_query_email_logs(query, page=page - 1, sort=sort, size=100)
        logs = response['hits']['hits'][:]
        for hits in logs:
            hits['id'] = hits['_id']
            hits['dt'] = timezone.make_aware(timezone.make_naive(datetime.datetime.fromisoformat(hits['_source']['@timestamp'])))
            hits['email'] = hits['_source']['to']
            hits['subject'] = hits['_source']['subject']
            hits['server'] = hits['_source']['server']
        return logs


# Formulário usado pela página de diagnóstico de autocompletes em djtools
class AutocompleteDiagnosticsForm(FormPlus):
    """Formulário simples para filtrar a página de diagnóstico de autocompletes.

    Campos:
        - app: select com apps instalados (ou vazio para todos)
        - declared: tri-state (todos / apenas com EXT_COMBO_RELATED / sem EXT_COMBO_RELATED)
        - limit: número de objetos amostrados por modelo
    """

    APP_DEFAULT_CHOICES = [('', 'Todos')]

    # choices will be populated in __init__ to reflect installed apps
    app = forms.ChoiceField(label='Aplicação', required=False)
    only_special = forms.BooleanField(label='Apenas modelos especiais', required=False)
    DECLARED_CHOICES = [
        ('all', 'Todos'),
        ('declared', 'Apenas com EXT_COMBO_RELATED'),
        ('not_declared', 'Sem EXT_COMBO_RELATED'),
    ]
    declared = forms.ChoiceField(label='EXT_COMBO_RELATED', required=False, choices=DECLARED_CHOICES, initial='all')
    limit = forms.IntegerField(
        label='Limite por modelo', required=False, initial=1, help_text='Quantidade de objetos amostrados por modelo (padrão: 1)'
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            from django.apps import apps as django_apps

            apps = django_apps.get_app_configs()
            choices = [('', 'Todos')]
            # present apps sorted by verbose name
            app_choices = sorted([(a.label, getattr(a, 'verbose_name', a.label)) for a in apps], key=lambda x: x[1].lower())
            choices.extend(app_choices)
            self.fields['app'].choices = choices
        except Exception:
            # fallback to empty select
            self.fields['app'].choices = [('', 'Todos')]
