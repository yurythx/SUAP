from datetime import datetime
from comum.models import User
from rh.models import UnidadeOrganizacional
from djtools import tasks as djtools_tasks
from djtools.db import models
from djtools.storages import upload_temporary_file
from edu.models.logs import LogModel
from edu.models.alunos import Aluno


class MensagemResponsavel(LogModel):
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True, blank=True)
    remetente = models.ForeignKeyPlus(User, verbose_name='Remetente')
    destinatarios = models.ManyToManyFieldPlus(Aluno, verbose_name='Destinatários')
    assunto = models.CharFieldPlus('Assunto')
    conteudo = models.TextField('Conteúdo')
    anexo = models.FileFieldPlus(upload_to='edu/mensagem/', null=True, blank=True, verbose_name='Anexo')
    data_envio = models.DateTimeField(auto_now=True)

    pode_interagir = models.BooleanField(
        verbose_name='Pode interagir?',
        default=False,
        help_text='Marque essa opção caso o responsável possa interagir enviando um comentário ou questionamento.',
    )

    class Meta:
        verbose_name = 'Mensagem para Responsável de Aluno'
        verbose_name_plural = 'Mensagens para Responsável de Aluno'
        ordering = ('-data_envio',)

    def existe_registro_leitura(self, user):
        return RegistroLeituraResponsavel.objects.filter(destinatario=user.get_vinculo().relacionamento, mensagem=self).exists()

    def get_absolute_url(self):
        return f'/edu/mensagemresponsavel/{self.pk}/'

    def save(self, *args, **kwargs):
        if self.uo_id is None:
            self.uo_id = self.remetente.get_vinculo().setor.uo_id
        return super().save(*args, **kwargs)

    def enviar_emails(self, qs_alunos, anexo=None, copia_para_remetente=True):
        emails = list(qs_alunos.exclude(email_responsavel='').exclude(email_responsavel__isnull=True).values_list('email_responsavel', flat=True))
        if copia_para_remetente:
            # email/email_secundario migraram de PessoaFisica para o Vinculo (papel do remetente).
            vinculo = self.remetente.get_vinculo()
            for email in (vinculo.email_notificacao, vinculo.email_pessoal) if vinculo else ():
                if email and email not in emails:
                    emails.append(email)
        files = []
        if anexo:
            file_path = upload_temporary_file(anexo)
            files.append(file_path)
        return djtools_tasks.enviar_emails_responsavel(
            self.pk, self.assunto, self.conteudo, emails, f'/edu/mensagemresponsavel/{self.pk}/', files=files
        )

    def registrar_leitura(self, aluno, meio, data_leitura):
        registro_leitura = self.registroleituraresponsavel_set.filter(destinatario=aluno).first()
        if registro_leitura is None:
            return RegistroLeituraResponsavel.objects.create(mensagem=self, destinatario=aluno, meio_leitura=meio, data_leitura=data_leitura)
        registro_leitura.data_leitura = datetime.now()
        registro_leitura.meio_leitura = meio
        registro_leitura.save()
        return registro_leitura

    def get_registro_leitura(self, user):
        if not hasattr(self, '_registro_leitura'):
            registro_leitura = self.registroleituraresponsavel_set.filter(destinatario__matricula=user.username).first()
            self._registro_leitura = registro_leitura
        return self._registro_leitura

    def get_data_leitura(self, user):
        registro_leitura = self.get_registro_leitura(user)
        return registro_leitura.data_leitura if registro_leitura else None

    def get_pergunta(self, user):
        registro_leitura = self.get_registro_leitura(user)
        return registro_leitura.pergunta if registro_leitura else None

    def get_data_pergunta(self, user):
        registro_leitura = self.get_registro_leitura(user)
        return registro_leitura.data_pergunta if registro_leitura else None

    def get_resposta(self, user):
        registro_leitura = self.get_registro_leitura(user)
        return registro_leitura.resposta if registro_leitura else None

    def get_data_resposta(self, user):
        registro_leitura = self.get_registro_leitura(user)
        return registro_leitura.data_resposta if registro_leitura else None


class RegistroLeituraResponsavel(models.ModelPlus):
    mensagem = models.ForeignKeyPlus(MensagemResponsavel, verbose_name='Mensagem')
    destinatario = models.ForeignKeyPlus(Aluno, verbose_name='Destinatário')
    data_leitura = models.DateTimeField(verbose_name='Data da Leitura', auto_now=True)
    meio_leitura = models.CharField(
        verbose_name='Meio da Leitura', null=True, blank=True, choices=[['E-mail', 'E-mail'], ['Aplicativo', 'Aplicativo'], ['SUAP', 'SUAP']]
    )

    pergunta = models.TextField('Pergunta', null=True, blank=True)
    data_pergunta = models.DateTimeField('Data da Pergunta', null=True, blank=True)

    resposta = models.TextField('Resposta', null=True, blank=True)
    data_resposta = models.DateTimeField('Data da Resposta', null=True, blank=True)
    responsavel_resposta = models.ForeignKeyPlus(User, null=True, blank=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Registro de Leitura de Mensagem de Responsável'
        verbose_name_plural = 'Registros de Leitura de Mensagem de Responsável'

    def perguntar(self, pergunta):
        if self.pergunta is None:
            self.pergunta = pergunta
            self.data_pergunta = datetime.now()
            self.save()

    def responder(self, resposta, user):
        if self.resposta is None:
            self.resposta = resposta
            self.data_resposta = datetime.now()
            self.responsavel_resposta = user
            self.save()
