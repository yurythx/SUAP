import sys

from django.conf import settings
from django.db.models.signals import post_save, pre_delete, pre_save
from django.dispatch.dispatcher import receiver

from comum.utils import tl
from djtools.db import models
from djtools.templatetags.filters import format_, format_datetime, format_money
from djtools.utils import normalizar_nome_proprio


class Log(models.ModelPlus):
    CADASTRO = 1
    EDICAO = 2
    EXCLUSAO = 3
    VISUALIZACAO = 4

    TIPO_CHOICES = [[CADASTRO, 'Cadastro'], [EDICAO, 'Edição'], [EXCLUSAO, 'Exclusão'], [VISUALIZACAO, 'Visualização']]

    user = models.ForeignKeyPlus('comum.User', null=True, on_delete=models.SET_NULL)
    aluno = models.ForeignKeyPlus('edu.Aluno', null=True, on_delete=models.SET_NULL)
    diario = models.ForeignKeyPlus('edu.Diario', null=True, on_delete=models.SET_NULL)
    dt = models.DateTimeFieldPlus(auto_now=True)
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    descricao = models.CharFieldPlus()
    app = models.CharFieldPlus()
    modelo = models.CharFieldPlus()
    nome_modelo = models.CharFieldPlus()
    ref = models.IntegerField(db_index=True)
    ref_aluno = models.IntegerField(null=True, db_index=True)
    ref_diario = models.IntegerField(null=True, db_index=True)

    class History:
        disabled = True

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/edu/log/{self.pk:d}/'

    class Meta:
        verbose_name = 'Log'
        verbose_name_plural = 'Logs'

    def set_up(self, user, tipo, instance, descricao):
        self.user = user
        self.tipo = tipo
        self.descricao = descricao
        self.app = instance._meta.app_label
        self.modelo = instance.__class__.__name__
        self.nome_modelo = instance._meta.verbose_name
        self.ref = instance.pk

        self.ref_diario = None
        if hasattr(instance, 'diario') and instance.diario:
            self.ref_diario = instance.diario.pk
        elif hasattr(instance, 'get_diario') and hasattr(instance.get_diario(), 'pk'):
            self.ref_diario = instance.get_diario().pk

        self.ref_aluno = None
        if hasattr(instance, 'aluno'):
            self.ref_aluno = instance.aluno.pk
        elif hasattr(instance, 'get_aluno') and hasattr(instance.get_aluno(), 'pk'):
            self.ref_aluno = instance.get_aluno().pk

        self.save()

    def get_resumo(self):
        alteracoes = []
        if self.tipo == Log.CADASTRO:
            alteracoes.append(f'{self.nome_modelo} cadastrado')
        elif self.tipo == Log.EDICAO:
            registros = self.registrodiferenca_set.all()
            for registro in registros:
                linha = f'Campo {registro.campo} alterado de {registro.valor_anterior} para {registro.valor_atual}'
                alteracoes.append(linha)
        elif self.tipo == Log.EXCLUSAO:
            alteracoes.append(f'{self.nome_modelo} excluído')
        return alteracoes


class RegistroDiferenca(models.ModelPlus):
    log = models.ForeignKeyPlus(Log, null=False)
    valor_anterior = models.TextField()
    valor_atual = models.TextField()
    campo = models.CharFieldPlus(null=False)

    class History:
        disabled = True


class LogModel(models.ModelPlus):
    class Meta:
        abstract = True

    def format(self, value):
        if value in (None, ''):
            return '-'
        elif isinstance(value, bool):
            return value and 'Sim' or 'Não'
        elif value.__class__.__name__ == 'Decimal':
            return format_money(value)
        elif hasattr(value, 'strftime'):
            return format_datetime(value)
        return str(value)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self.__class__, '_if_changed') and 'test_suap' not in sys.argv and 'test' not in sys.argv and settings.USE_EDU_LOG:

            @receiver(pre_save, sender=self.__class__)
            def _if_changed(sender, instance, **kwargs):
                user = tl.get_user()
                user = user and not user.is_anonymous and user or None
                old = instance.__class__.objects.filter(pk=instance.pk).first()
                desc = f'O usuário atualizou {instance._meta.verbose_name} #{instance.pk}'
                instance._inserted = True
                if old:
                    instance._inserted = False
                    log = Log()
                    for field in instance._meta.fields:
                        o1 = getattr(old, field.name)
                        o2 = getattr(instance, field.name)
                        v1 = self.format(o1)
                        v2 = self.format(o2)
                        if ((isinstance(o1, str) or isinstance(o2, str)) or not hasattr(o2, '__iter__')) and v1 != v2:
                            log.set_up(user, Log.EDICAO, instance, desc)
                            if not log.id:
                                log.save()
                            RegistroDiferenca.objects.create(
                                valor_anterior=v1, valor_atual=v2, campo=normalizar_nome_proprio(field.verbose_name), log=log
                            )

            @receiver(post_save, sender=self.__class__)
            def _if_inserted(sender, instance, **kwargs):
                if hasattr(instance, '_inserted') and instance._inserted:
                    user = tl.get_user()
                    user = user and not user.is_anonymous and user or None
                    desc = f'O usuário cadastrou {instance._meta.verbose_name} #{instance.pk}'
                    log = Log()
                    log.set_up(user, Log.CADASTRO, instance, desc)
                    log.save()

            @receiver(pre_delete, sender=self.__class__)
            def _if_deleted(sender, instance, **kwargs):
                user = tl.get_user()
                user = user and not user.is_anonymous and user or None
                desc = f'O usuário excluiu {instance._meta.verbose_name} #{instance.pk}'
                old = instance.__class__.objects.filter(pk=instance.pk).first()
                if old:
                    log = Log()
                    log.set_up(user, Log.EXCLUSAO, instance, desc)
                    log.save()
                    for field in instance._meta.fields:
                        if not isinstance(field, models.FileField):
                            v1 = str(format_(getattr(old, field.name), html=False))
                            RegistroDiferenca.objects.create(
                                valor_anterior=v1, valor_atual='', campo=normalizar_nome_proprio(field.verbose_name), log=log
                            )

            self.__class__._if_changed = _if_changed
            self.__class__._if_inserted = _if_inserted
            self.__class__._if_deleted = _if_deleted
