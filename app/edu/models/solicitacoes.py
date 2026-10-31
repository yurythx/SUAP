import datetime

from django.conf import settings

from djtools.db import models
from djtools.utils import send_notification, somar_dias
from edu.managers import SolicitacaoProrrogacaoEtapaManager, SolicitacaoRelancamentoEtapaManager, SolicitacaoUsuarioManager
from edu.models.diarios import Diario
from edu.models.logs import LogModel


class SolicitacaoUsuario(LogModel):
    solicitante = models.CurrentUserField(verbose_name='Solicitante', related_name='solicitacao_solicitante_set')
    data_solicitacao = models.DateTimeFieldPlus(null=True, auto_now_add=True, verbose_name='Data da Solicitação')
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus', on_delete=models.CASCADE)
    descricao = models.TextField(verbose_name='Descrição')

    avaliador = models.ForeignKeyPlus('comum.User', verbose_name='Avaliador', null=True, related_name='solicitacao_avaliador_set')
    data_avaliacao = models.DateTimeFieldPlus(null=True)

    atendida = models.BooleanField(verbose_name='Atendida', default=False)
    razao_indeferimento = models.TextField(null=True, verbose_name='Razão do Indeferimento')

    objects = models.Manager()
    locals = SolicitacaoUsuarioManager()

    class Meta:
        verbose_name = 'Solicitação de Usuário'
        verbose_name_plural = 'Solicitações de Usuários'
        ordering = ('data_solicitacao',)

    def atender(self, avaliador, aluno=None):
        self.data_avaliacao = datetime.datetime.now()
        self.avaliador = avaliador
        self.atendida = True
        self.save()
        if not aluno:
            self.enviar_email(avaliador)

    def rejeitar(self, avaliador, razao_indeferimento, aluno=None):
        self.data_avaliacao = datetime.datetime.now()
        self.avaliador = avaliador
        self.atendida = False
        self.razao_indeferimento = razao_indeferimento
        self.save()
        if not aluno:
            self.enviar_email(avaliador)

    def enviar_email(self, avaliador):
        if not self.solicitante:
            return
        titulo = f'[SUAP] Situação da Solicitação Usuário de Número {self.pk}.'
        if self.atendida:
            texto = self.get_texto_deferimento(avaliador)
            texto += self.get_texto_dados_solicitacao()
        else:
            texto = (
                '<dl>'
                f'<dt>A solicitação de número {self.pk} foi indeferida por {avaliador} devido ao seguinte motivo:</dt>'
                f'<dd>{self.razao_indeferimento}.</dd>'
                '</dl>'
            )

        return send_notification(
            titulo, texto, settings.DEFAULT_FROM_EMAIL, [self.solicitante.get_vinculo()], categoria='Situação da Solicitação Usuário'
        )

    def get_absolute_url(self):
        return f'/edu/solicitacaousuario/{self.pk:d}/'

    def get_texto_deferimento(self, avaliador):
        return f'A solicitação de número {self.pk} foi deferida por {avaliador}.'

    def get_texto_dados_solicitacao(self):
        texto = f"""

            Dados da Solicitação:

            Data: {self.data_solicitacao}
            Solicitante: {self.solicitante}
            Descrição: {self.descricao}
        """
        return texto

    def sub_instance(self):
        child = self
        objetos_relacionados = [f for f in self._meta.get_fields() if (f.one_to_many or f.one_to_one) and f.auto_created]
        for r in objetos_relacionados:
            try:
                if r.field.name == 'solicitacaousuario_ptr':
                    child = getattr(self, r.get_accessor_name())
            except Exception:
                pass
        return child

    def sub_instance_title(self):
        return self.sub_instance()._meta.verbose_name

    sub_instance_title.short_description = 'Tipo de Solicitação'


class SolicitacaoRelancamentoEtapa(SolicitacaoUsuario):
    etapa = models.IntegerField()
    professor_diario = models.ForeignKeyPlus('edu.ProfessorDiario')
    motivo = models.TextField('Motivo', null=True)

    objects = models.Manager()
    locals = SolicitacaoRelancamentoEtapaManager()

    class Meta:
        verbose_name = 'Solicitação de Relançamento de Etapa'
        verbose_name_plural = 'Solicitações de Relançamento de Etapa'

    def get_diario(self):
        return self.professor_diario.diario

    def __str__(self):
        return f'Relançamento da etapa {self.etapa} do diário {self.professor_diario.diario} por {self.solicitante}'

    def save(self, *args, **kwargs):
        self.descricao = str(self)
        self.uo = self.professor_diario.diario.turma.curso_campus.diretoria.setor.uo
        self.diretoria = self.professor_diario.diario.turma.curso_campus.diretoria
        super().save(*args, **kwargs)

    def atender(self, avaliador, aluno=None, nova_data=None):
        super().atender(avaliador, aluno)
        diario = self.professor_diario.diario
        setattr(diario, f'posse_etapa_{self.etapa}', Diario.POSSE_PROFESSOR)
        diario.save()
        if not nova_data and self.precisa_prorrogar_posse():
            nova_data = somar_dias(datetime.date.today(), 3)
        if nova_data:
            setattr(self.professor_diario, f'data_fim_etapa_{self.get_etapa_formatada()}', nova_data)
        self.professor_diario.save()

    def get_diretoria(self):
        return self.professor_diario.diario.turma.curso_campus.diretoria

    def get_etapa_formatada(self):
        if self.etapa == 5:
            return 'final'
        else:
            return f'{self.etapa}'

    def precisa_prorrogar_posse(self):
        fim_posse = getattr(self.professor_diario, f'data_fim_etapa_{self.get_etapa_formatada()}')
        if fim_posse:
            return fim_posse <= datetime.date.today()
        else:
            return True


class SolicitacaoProrrogacaoEtapa(SolicitacaoUsuario):
    etapa = models.IntegerField()
    professor_diario = models.ForeignKeyPlus('edu.ProfessorDiario')
    motivo = models.TextField('Motivo', null=True)

    objects = models.Manager()
    locals = SolicitacaoProrrogacaoEtapaManager()

    class Meta:
        verbose_name = 'Solicitação de Prorrogação de Etapa'
        verbose_name_plural = 'Solicitações de Prorrogação de Etapa'

    def get_diario(self):
        return self.professor_diario.diario

    def __str__(self):
        return f'Solicitação de prorrogação da etapa {self.etapa} do diário {self.professor_diario.diario} por {self.solicitante}'

    def get_data_prorrogacao(self):
        return getattr(self.professor_diario, f'data_fim_etapa_{self.etapa}', None)

    def save(self, *args, **kwargs):
        self.descricao = str(self)
        self.uo = self.professor_diario.diario.turma.curso_campus.diretoria.setor.uo
        self.diretoria = self.professor_diario.diario.turma.curso_campus.diretoria
        super().save(*args, **kwargs)

    def atender(self, avaliador, aluno=None, nova_data=None):
        super().atender(avaliador, aluno)
        if not nova_data:
            nova_data = somar_dias(datetime.date.today(), 3)

        setattr(self.professor_diario, f'data_fim_etapa_{self.get_etapa_formatada()}', nova_data)
        self.professor_diario.save()

    def get_texto_deferimento(self, avaliador):
        return f'A solicitação de número {self.pk} foi deferida por {avaliador}. O novo prazo pala lançamento das notas ou entrega da etapa expira em três dias.'

    def get_diretoria(self):
        return self.professor_diario.diario.turma.curso_campus.diretoria

    def get_etapa_formatada(self):
        if self.etapa == 5:
            return 'final'
        else:
            return f'{self.etapa}'
