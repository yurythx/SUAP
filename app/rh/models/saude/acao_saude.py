from djtools.db import models
from djtools.templatetags.filters import in_group
from djtools.utils import date_to_string, get_datetime_now


class AcaoSaudeAtivaManager(models.Manager):
    def get_queryset(self):
        hoje = get_datetime_now().date()
        return super().get_queryset().filter(periodo_inscricao_inicio__lte=hoje, periodo_inscricao_fim__gte=hoje)


class AcaoSaude(models.ModelPlus):
    SEARCH_FIELDS = ('descricao',)

    descricao = models.CharFieldPlus('Descrição', null=False, blank=False)
    data_inicio = models.DateFieldPlus('Data Início da Ação', null=False, blank=False)
    data_fim = models.DateFieldPlus('Data Final da Ação', null=False, blank=True)
    periodo_inscricao_inicio = models.DateFieldPlus('Data de Início das Inscrições', null=False, blank=False)
    periodo_inscricao_fim = models.DateFieldPlus('Data Fim das Inscrições', null=False, blank=False)
    dias_semanas = models.CharFieldPlus('Dias da Semana', null=True)
    data_cadastro = models.DateTimeField(auto_now=True)

    objects = models.Manager()
    ativas = AcaoSaudeAtivaManager()

    class Meta:
        verbose_name = 'Ação de Saúde'
        verbose_name_plural = 'Ações de Saúde'

    def periodo_acao(self):
        return f'{date_to_string(self.data_inicio)} à {date_to_string(self.data_fim)}'

    def save(self, *args, **kwargs):
        if not self.data_fim:
            self.data_fim = self.data_inicio
        super().save(*args, **kwargs)

    def __str__(self):
        return self.descricao

    def get_absolute_url(self):
        return f'/rh/acao_saude/{self.pk}/'

    def em_periodo_inscricao(self):
        hoje = get_datetime_now().date()
        return self.periodo_inscricao_inicio <= hoje <= self.periodo_inscricao_fim

    def acao_finalizada(self):
        hoje = get_datetime_now().date()
        return self.data_fim < hoje

    def eh_profissional_da_acao(self, servidor):
        return self.agendaatendimentohorario_set.filter(profissional=servidor).exists()

    @staticmethod
    def pode_ver_toda_agenda(user):
        return bool(in_group(user, 'Gestor de Agenda de Saúde') or in_group(user, 'Coordenador de Saúde Sistêmico') or user.is_superuser)
