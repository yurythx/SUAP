from django.db.models import Exists, OuterRef

from comum.models import User
from djtools import tasks as djtools_tasks
from djtools.db import models
from djtools.storages import upload_temporary_file
from edu.models.logs import LogModel


class Mensagem(LogModel):
    remetente = models.ForeignKeyPlus('comum.User', verbose_name='Remetente', related_name='remetente_set')
    destinatarios = models.ManyToManyFieldPlus(User, verbose_name='Destinatários', related_name='destinatarios_set')
    assunto = models.CharFieldPlus('Assunto')
    conteudo = models.TextField('Conteúdo')
    anexo = models.FileFieldPlus(upload_to='edu/mensagem/', null=True, blank=True, verbose_name='Anexo')
    data_envio = models.DateTimeField(auto_now=True)
    via_suap = models.BooleanField('Via SUAP', default=True)
    via_email = models.BooleanField('Via E-mail', default=False)

    class Meta:
        verbose_name = 'Mensagem'
        verbose_name_plural = 'Mensagens'
        ordering = ('-data_envio',)

    def existe_registro_leitura(self, user):
        return RegistroLeitura.objects.filter(destinatario__pk=user.pk, mensagem=self).exists()

    def get_absolute_url(self):
        return f'/edu/mensagem/{self.pk}/'

    def enviar_emails(self, qs_alunos, anexo=None, coordenadores=None, diretores=None, copia_para_remetente=True):
        if coordenadores is None:
            coordenadores = []
        if diretores is None:
            diretores = []
        emails = list(qs_alunos.exclude(vinculos__email_pessoal='').values_list('vinculos__email_pessoal', flat=True).distinct())
        if copia_para_remetente:
            remetente_vinculo = self.remetente.get_vinculo()
            if remetente_vinculo and remetente_vinculo.email_notificacao:
                emails.append(remetente_vinculo.email_notificacao)
        for coordenador in coordenadores:
            v = coordenador.get_vinculo()
            if v and v.email_notificacao:
                emails.append(v.email_notificacao)
        for diretor in diretores:
            v = diretor.get_vinculo()
            if v and v.email_notificacao:
                emails.append(v.email_notificacao)
        files = []
        if anexo:
            file_path = upload_temporary_file(anexo)
            files.append(file_path)
        return djtools_tasks.enviar_emails(self.assunto, self.conteudo, list(set(emails)), '/edu/enviar_mensagem/', files=files)


class RegistroLeitura(models.ModelPlus):
    mensagem = models.ForeignKeyPlus('edu.Mensagem', verbose_name='Mensagem')
    destinatario = models.ForeignKeyPlus('comum.User', verbose_name='Destinatário')
    data_leitura = models.DateTimeField(auto_now=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Registro de Leitura'
        verbose_name_plural = 'Registros de Leituras'


class RegistroExclusao(models.ModelPlus):
    mensagem = models.ForeignKeyPlus('edu.Mensagem', verbose_name='Mensagem')
    destinatario = models.ForeignKeyPlus('comum.User', verbose_name='Destinatário')
    data_exclusao = models.DateTimeField(auto_now=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Registro de Exclusão'
        verbose_name_plural = 'Registros de Exclusões'


class MensagemEntrada(Mensagem):
    class Meta:
        proxy = True
        verbose_name = 'Mensagem Recebida'
        verbose_name_plural = 'Mensagens Recebidas'

    @classmethod
    def qs_mensagem(cls, user):
        registro_leitura = RegistroLeitura.objects.filter(destinatario__pk=user.pk, mensagem=OuterRef('pk'))

        registro_exclusao = RegistroExclusao.objects.filter(destinatario__pk=user.pk, mensagem=OuterRef('pk'))

        mensagens = MensagemEntrada.objects.annotate(
            registro_leitura=Exists(registro_leitura),
            registro_exclusao=Exists(registro_exclusao),
        )

        return mensagens

    @classmethod
    def mensagens_nao_lidas(cls, user):
        mensagens = (
            cls.qs_mensagem(user=user)
            .filter(
                destinatarios=user,
                registro_leitura=False,
                registro_exclusao=False,
            )
            .exclude(remetente_id=user.id)
        )

        return mensagens.distinct().order_by('-data_envio')

    @classmethod
    def mensagens_lidas(cls, user):
        mensagens = (
            cls.qs_mensagem(user=user)
            .filter(
                destinatarios=user,
                registro_leitura=True,
                registro_exclusao=False,
            )
            .exclude(
                remetente_id=user.id,
            )
        )

        return mensagens.distinct().order_by('-data_envio')

    @classmethod
    def mensagens_todas(cls, user):
        mensagens = (
            cls.qs_mensagem(user=user)
            .filter(
                destinatarios=user,
                registro_exclusao=False,
            )
            .exclude(
                remetente_id=user.id,
            )
        )

        return mensagens.order_by('-data_envio')

    @classmethod
    def mensagens_lixeira(cls, user):
        mensagens = (
            cls.qs_mensagem(user=user)
            .filter(
                destinatarios=user,
                registro_exclusao=True,
            )
            .exclude(
                remetente_id=user.id,
            )
        )

        return mensagens.order_by('-data_envio')


class MensagemSaida(Mensagem):
    def get_quantidade_destinatarios(self):
        return self.destinatarios.count()

    get_quantidade_destinatarios.short_description = 'Quantidade de Destinatários'

    def get_quantidade_leitura(self):
        return RegistroLeitura.objects.filter(mensagem=self).count()

    get_quantidade_leitura.short_description = 'Quantidade de Leitura'

    class Meta:
        proxy = True
        verbose_name = 'Mensagem Enviada'
        verbose_name_plural = 'Mensagens Enviadas'
