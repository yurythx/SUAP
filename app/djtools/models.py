import base64
import json
import math
import random
import uuid
from datetime import datetime, timedelta

from django.conf import settings

from comum.models import Configuracao
from djtools.db import models
from djtools.storages.utils import upload_temporary_file
from djtools.utils import running_tests, send_notification
from suap import celery_app as app


class Task(models.ModelPlus):
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)
    type = models.CharFieldPlus(verbose_name='Tipo')
    user = models.ForeignKeyPlus('comum.User', verbose_name='Usuário', null=True)
    message = models.TextField(verbose_name='Mensagem', null=True)
    file = models.CharFieldPlus(verbose_name='Arquivo', null=True)
    total = models.IntegerField(verbose_name='Total', default=0)
    partial = models.IntegerField(verbose_name='Parcial', default=0)
    error = models.TextField(verbose_name='Erro', null=True)
    start = models.DateTimeFieldPlus(verbose_name='Início', auto_now=True)
    end = models.DateTimeFieldPlus(verbose_name='Fim', null=True)
    notify = models.BooleanField(default=False)
    url = models.CharFieldPlus(verbose_name='URL de Redirecionamento', max_length=5000, default='')
    celery_uuid = models.UUIDField(verbose_name='UUID do Celery', null=True)
    celery_queue = models.CharFieldPlus(verbose_name='Fila do Celery', max_length=100, default='geral')

    objects = models.Manager()

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Tarefa'
        verbose_name_plural = 'Tarefas'

    def get_absolute_url(self):
        return f'/djtools/view_task/{self.pk}/'

    @property
    def percent(self):
        if self.end and not self.error:
            return 100
        progress = math.floor(self.partial * 100 / ((self.total or self.partial or 1) + 1))
        return progress >= 100 and 99 or progress

    def count(self, *iterables):
        for iterable in iterables:
            self.total += len(iterable)
        Task.objects.filter(pk=self.pk).update(total=self.total)

    def start_progress(self, total=100):
        self.total = total
        Task.objects.filter(pk=self.pk).update(total=total)

    def update_progress(self, percent):
        self.partial = percent
        Task.objects.filter(pk=self.pk).update(partial=percent)

    def iterate(self, iterable):
        if not self.total:
            self.total = len(iterable)
            Task.objects.filter(pk=self.pk).update(total=self.total)
        partial = self.partial
        previous_percent = 0
        for i, obj in enumerate(iterable):
            self.partial = partial + i
            each_five_percent = math.floor(self.partial * 20 / self.total)
            if previous_percent < each_five_percent or i == self.total:
                previous_percent = each_five_percent
                Task.objects.filter(pk=self.pk).update(partial=self.partial)
            yield obj

    def finalize(self, message, url='', error=False, file_path=None):
        if not self.url:
            self.url = url
        if error:
            self.error = message
            self.message = f'Ocorreu um <a href="{self.get_absolute_url()}">erro</a> ao processar sua solicitação. Detalhe: {message}'
        else:
            self.partial = self.total
            self.message = message
        if file_path:
            self.file = upload_temporary_file(file_path)
        self.end = datetime.now()
        Task.objects.filter(pk=self.pk).update(
            error=self.error, message=self.message, file=self.file, end=self.end, partial=self.partial, url=self.url
        )
        obj = Task.objects.filter(pk=self.pk).first()
        if obj and obj.notify:
            self.send_notification()

    def send_notification(self):
        titulo = f'[SUAP] Resultado da Execução da Tarefa {self.id}'
        url = f'{settings.SITE_URL}/djtools/view_task/{self.id}/'
        mensagem = f'<h1>Resultado da Execução da Tarefa #{self.id}</h1><b>Tarefa: {self.type}<p>O resultado está disponível no endereço: <a href="{url}">{url}</a>.</p>'
        send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [self.user.get_vinculo()], categoria='Resultado da Execução de Tarefa')

    def __str__(self):
        return f'Tarefa #{self.id}'

    def get_result(self):
        if self.celery_uuid:
            return app.AsyncResult(str(self.celery_uuid))

    def get_celery_queue_items(self):
        if not self.celery_queue:
            return None
        try:
            with app.pool.acquire(block=True) as conn:
                tasks = conn.default_channel.client.lrange(self.celery_queue, 0, -1)

            for task in tasks:
                j = json.loads(task)
                headers = j.get('headers', {'id': None})
                if headers.get('id') != str(self.celery_uuid):
                    continue
                return json.loads(base64.b64decode(j['body']))
        except Exception:
            pass
        return None

    def revoke(self):
        if self.celery_uuid:
            app.control.revoke(self.celery_uuid, terminate=True)
        return True


class TwoFactorAuthenticationCode(models.ModelPlus):
    user = models.CurrentUserField(verbose_name='Usuário')
    email = models.CharFieldPlus(verbose_name='E-mail')
    expires = models.DateTimeFieldPlus()
    code = models.CharFieldPlus(verbose_name='Código', max_length=6)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Código de Autenticação'
        verbose_name_plural = 'Códigos de Autenticação'

    def __str__(self):
        return self.code

    def save(self, *args, **kwargs):
        self.email = self.user.get_vinculo().email_pessoal or ''
        if running_tests():
            self.code = 123456
        else:
            self.code = random.randint(1, 1000001)
        tempo_em_minutos = Configuracao.get_valor_por_chave('djtools', 'tempo_validade_codigo_autenticacao') or 5
        self.expires = datetime.now() + timedelta(minutes=int(tempo_em_minutos))
        super().save(*args, **kwargs)


class EmailEnviadoLog(models.ModelPlus):
    assunto = models.TextField('Título')
    destinatarios = models.TextField('Destinatários')
    data = models.DateTimeFieldPlus(auto_now_add=True)
    conteudo = models.TextField('Conteúdo', null=True, blank=True)

    class Meta:
        verbose_name = 'Email Enviado'
        verbose_name_plural = 'Emails Enviados'

    def __str__(self):
        return f'Email Enviado: {self.destinatarios} - {self.data}'

    class History:
        disabled = True


class PushSubscription(models.Model):
    user = models.ForeignKey('comum.user', verbose_name='Usuário', on_delete=models.CASCADE)
    device = models.CharField(verbose_name='Dispositivo')
    data = models.JSONField(verbose_name='Dados da Inscrição')

    class Meta:
        verbose_name = 'Inscrição de Notificação'
        verbose_name_plural = 'Inscrições de Notificação'

    def notify(self, title, message, url='/'):
        """Envia notificação push para a inscrição do dispositivo.

        Args:
            title: título da notificação.
            message: corpo da mensagem.
            url: URL de redirecionamento ao clicar na notificação.

        Returns:
            bool: ``True`` se a notificação foi enviada com sucesso,
            ``False`` em caso de erro.
        """
        from pywebpush import WebPushException, webpush

        icon = f'{settings.SITE_URL}/static/comum/img/suap.png'
        vapid_private_key = Configuracao.get_valor_por_chave('djtools', 'vapid_private_key')
        try:
            response = webpush(
                subscription_info=self.data,
                data=json.dumps({'title': title, 'message': message, 'url': url, 'icon': icon}),
                vapid_private_key=vapid_private_key,
                vapid_claims={'sub': f'mailto:{settings.ADMINS[0][1]}' if settings.ADMINS else 'mailto:admin@admin.com'},
            )
            return response.status_code == 201
        except WebPushException:
            return False


class MetadadoTabela(models.Model):
    """Metadados de uma tabela do banco, extraídos do model Django correspondente."""

    tabela = models.CharField(verbose_name='Tabela', unique=True)
    app = models.CharField(verbose_name='Aplicação')
    model = models.CharField(verbose_name='Model')
    verbose_name = models.CharField(verbose_name='Nome')
    verbose_name_plural = models.CharField(verbose_name='Nome no plural')
    docstring = models.TextField(verbose_name='Docstring', blank=True)

    class Meta:
        db_table = 'metadados_tabelas'
        verbose_name = 'Metadado de Tabela'
        verbose_name_plural = 'Metadados de Tabelas'


class MetadadoCampo(models.Model):
    """Metadados de uma coluna do banco, extraídos do campo Django correspondente."""

    tabela = models.CharField(verbose_name='Tabela')
    coluna = models.CharField(verbose_name='Coluna')
    app = models.CharField(verbose_name='Aplicação')
    model = models.CharField(verbose_name='Model')
    campo = models.CharField(verbose_name='Campo')
    tipo = models.CharField(verbose_name='Tipo')
    verbose_name = models.CharField(verbose_name='Nome')
    help_text = models.TextField(verbose_name='Texto de ajuda', blank=True)
    default = models.TextField(verbose_name='Valor padrão', null=True)
    default_callable = models.BooleanField(verbose_name='Valor padrão é chamável')
    editable = models.BooleanField(verbose_name='Editável')
    auto_now = models.BooleanField(verbose_name='Atualiza ao salvar')
    auto_now_add = models.BooleanField(verbose_name='Preenche ao criar')
    tabela_relacionada = models.CharField(verbose_name='Tabela relacionada', null=True)
    limit_choices_to = models.TextField(verbose_name='Limite das opções', null=True)
    generic_foreign_key = models.CharField(verbose_name='Chave estrangeira genérica', null=True)

    class Meta:
        db_table = 'metadados_campos'
        verbose_name = 'Metadado de Campo'
        verbose_name_plural = 'Metadados de Campos'
        constraints = [models.UniqueConstraint(fields=['tabela', 'coluna'], name='metadados_campos_tabela_coluna_uniq')]


class MetadadoChoice(models.Model):
    """Opção de um campo com choices, extraída do model Django."""

    tabela = models.CharField(verbose_name='Tabela')
    coluna = models.CharField(verbose_name='Coluna')
    valor = models.TextField(verbose_name='Valor', null=True)
    rotulo = models.TextField(verbose_name='Rótulo')
    ordem = models.PositiveIntegerField(verbose_name='Ordem')
    grupo = models.TextField(verbose_name='Grupo', null=True)

    class Meta:
        db_table = 'metadados_choices'
        verbose_name = 'Metadado de Choice'
        verbose_name_plural = 'Metadados de Choices'
        constraints = [models.UniqueConstraint(fields=['tabela', 'coluna', 'valor'], name='metadados_choices_tabela_coluna_valor_uniq')]


class MetadadoTransicao(models.Model):
    """Transição de estado de um campo com máquina de estados (django-fsm)."""

    tabela = models.CharField(verbose_name='Tabela')
    coluna = models.CharField(verbose_name='Coluna')
    nome = models.CharField(verbose_name='Nome')
    origem = models.CharField(verbose_name='Origem')
    destino = models.CharField(verbose_name='Destino', null=True)

    class Meta:
        db_table = 'metadados_transicoes'
        verbose_name = 'Metadado de Transição'
        verbose_name_plural = 'Metadados de Transições'
        constraints = [
            models.UniqueConstraint(fields=['tabela', 'coluna', 'nome', 'origem'], name='metadados_transicoes_tabela_coluna_nome_origem_uniq')
        ]
