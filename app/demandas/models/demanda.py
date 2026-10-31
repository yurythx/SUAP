import urllib
from collections import OrderedDict
from datetime import date, datetime, time, timedelta

from django.conf import settings
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import F, Max, Q
from django.template.defaultfilters import truncatewords
from django.urls import reverse_lazy
from reversion import revisions as reversion
from reversion.models import Version
from sentry_sdk import capture_exception

from comum.models import Configuracao, User
from comum.utils import ferramentas_configuradas, tl
from demandas.utils import Notificar, adicionar_comentario, get_auto_apps_relacionadas
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.middleware.threadlocals import get_user
from djtools.utils import ModelValidation, get_app_suap_display, gitlab, somar_dias_uteis
from rh.pdf import dateToStr


class TipoDemanda:
    MELHORIA = 'Melhoria'
    FUNCIONALIDADE = 'Funcionalidade'

    TIPODEMANDA_CHOICES = ((MELHORIA, 'Melhoria'), (FUNCIONALIDADE, 'Funcionalidade'))


class AreaAtuacaoDemanda(models.ModelPlus):
    SEARCH_FIELDS = ['area__nome']

    area = models.OneToOneFieldPlus('comum.AreaAtuacao', verbose_name='Área')
    demandantes = models.ManyToManyField(User, related_name='demanda_demandantesarea_set', verbose_name='Demandantes')
    demandante_responsavel = models.ForeignKeyPlus(
        User, related_name='demandanteresponsavelarea', verbose_name='Demandante Responsável pela Área', null=True
    )
    tags_relacionadas = models.ManyToManyField('demandas.Tag', verbose_name='Tags relacionadas')
    recebe_sugestoes = models.BooleanField('Recebe sugestões de melhorias?', default=False)
    recebe_sugestoes_publico_aluno = models.BooleanField('Recebe sugestões de melhorias de Alunos?', default=True)
    recebe_sugestoes_publico_servidor = models.BooleanField('Recebe sugestões de melhorias de Servidores?', default=True)
    recebe_sugestoes_publico_prestador_servico = models.BooleanField('Recebe sugestões de melhorias de Prestadores de Serviço?', default=True)

    class Meta:
        verbose_name = 'Área de Atuação'
        verbose_name_plural = 'Áreas de Atuação'

    def save(self, *args, **kwargs):
        self.recebe_sugestoes = (
            self.recebe_sugestoes_publico_aluno or self.recebe_sugestoes_publico_servidor or self.recebe_sugestoes_publico_prestador_servico
        )
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.area}'

    @staticmethod
    def areas_recebem_sugestoes():
        return AreaAtuacaoDemanda.objects.filter(recebe_sugestoes=True).order_by('area__nome')

    def pode_abrir_sugestoes(self, user):
        if user.eh_servidor:
            return self.recebe_sugestoes_publico_servidor
        elif user.eh_aluno:
            return self.recebe_sugestoes_publico_aluno
        return self.recebe_sugestoes_publico_prestador_servico

    @staticmethod
    def areas_pode_abrir_sugestoes(user):
        # TODO: não performático
        return AreaAtuacaoDemanda.objects.filter(
            id__in=[area.id for area in AreaAtuacaoDemanda.areas_recebem_sugestoes() if area.pode_abrir_sugestoes(user)]
        ).order_by('area__nome')

    @property
    def demandantes_por_tags(self):
        """informação usada no contexto de sugestões de melhoria"""
        from .sugestao import TagDemandantes

        result = {}
        for tag in self.tags_relacionadas.all():
            result[tag] = TagDemandantes.get_demandantes(tag)
        return result

    def percentual_sugestoes_avaliadas(self):
        from .sugestao import SugestaoMelhoria

        sugestoes = SugestaoMelhoria.objects.filter(area_atuacao=self)
        total = sugestoes.count()

        if total == 0:
            return 0

        avaliadas = sugestoes.filter(
            situacao__in=[
                SugestaoMelhoria.SITUACAO_DEFERIDA,
                SugestaoMelhoria.SITUACAO_IMPLEMENTADA,
                SugestaoMelhoria.SITUACAO_CANCELADA,
                SugestaoMelhoria.SITUACAO_INDEFERIDA,
            ]
        ).count()

        return round((avaliadas / total) * 100)

    def get_demandantes(self) -> list[User]:
        area_demandantes = list(self.demandantes.all())
        if self.demandante_responsavel:
            area_demandantes.append(self.demandante_responsavel)
        return list(set(area_demandantes))


class AnalistaDesenvolvedor(models.ModelPlus):
    usuario = models.OneToOneFieldPlus(User, related_name='analistadesenvolvedor', verbose_name='Analista/Desenvolvedor', null=False)
    username_gitlab = models.CharFieldPlus(verbose_name='Username Gitlab')
    eh_analista = models.BooleanField('É Analista?', default=True)
    eh_desenvolvedor = models.BooleanField('É Desenvolvedor?', default=True)
    ativo = models.BooleanField('Ativo?', default=True)

    pipeline = models.IntegerField('Pipeline da IDE', null=True, blank=True)
    senha_ide = models.CharFieldPlus('Senha da IDE', null=True, blank=True)

    class Meta:
        verbose_name = 'Analista/Desenvolvedor'
        verbose_name_plural = 'Analistas/Desenvolvedores'

    def __str__(self):
        return f'{self.usuario}'

    def get_absolute_url(self):
        return f'/demandas/analistadesenvolvedor/{self.pk}/'

    def save(self, *args, **kwargs):
        if self.pipeline is None and gitlab.access_token():
            self.pipeline = self.criar_pipeline().get('id')
        super().save(*args, **kwargs)
        grupo_analista = Group.objects.get(name='Analista')
        if self.eh_analista:
            self.usuario.groups.add(grupo_analista)
        else:
            self.usuario.groups.remove(grupo_analista)

    def get_url_issues_em_andamento_projeto(self, projeto, milestone_title=None):
        url = f'{projeto.grupo}/{projeto.nome_projeto}/issues/?scope=all&utf8=✓&state=opened&assignee_username={self.username_gitlab}'
        if milestone_title:
            url = f'{url}&milestone_title={milestone_title}'
        return urllib.parse.urljoin(
            f'{Configuracao.get_valor_por_chave("demandas", "gitlab_url")}',
            url,
        )

    def criar_pipeline(self):
        variables = [
            {'key': 'USERNAME', 'variable_type': 'env_var', 'value': self.usuario.username},
            {'key': 'PASSWORD', 'variable_type': 'env_var', 'value': self.senha_ide},
        ]
        return gitlab.create_pipeline(variables)

    def criar_atualizar_ide(self):
        gitlab.execute_job(self.pipeline, 'deploy-ide')

    def get_log_ide_cricao_atualizacao_ide(self):
        return gitlab.job_log(self.pipeline, 'deploy-ide')

    def excluir_ide(self):
        gitlab.execute_job(self.pipeline, 'undeploy-ide')

    def destruir_ide(self):
        gitlab.execute_job(self.pipeline, 'destroy-ide')
        self.pipeline = None
        self.save()

    def get_senha_ide(self):
        log = gitlab.job_log(self.pipeline, 'deploy-ide')
        tokens = log.split('SENHA: ')
        if len(tokens) > 1:
            return tokens[1][0:6]
        return None


class ProjetoGitlab(models.ModelPlus):
    id_projeto_gitlab = models.PositiveIntegerFieldPlus(verbose_name='ID projeto no gitlab', null=False)
    nome_projeto = models.CharFieldPlus(verbose_name='Nome do projeto')
    grupo = models.CharFieldPlus(verbose_name='Grupo')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Projeto no Gitlab'
        verbose_name_plural = 'Projetos no Gitlab'

    def __str__(self):
        return f'{self.nome_projeto}'


class Situacao:
    ESTADO_ABERTO = 'Solicitada'
    ESTADO_EM_NEGOCIACAO = 'Em negociação'
    ESTADO_EM_ANALISE = 'Em análise'
    ESTADO_APROVADO = 'Aprovada'
    ESTADO_EM_DESENVOLVIMENTO = 'Em desenvolvimento'
    ESTADO_EM_HOMOLOGACAO = 'Em homologação'
    ESTADO_HOMOLOGADA = 'Homologada'
    ESTADO_EM_IMPLANTACAO = 'Em implantação'
    ESTADO_CONCLUIDO = 'Concluída'
    ESTADO_CANCELADO = 'Cancelada'
    ESTADO_SUSPENSO = 'Suspensa'

    INICIAL = [ESTADO_ABERTO]
    TERMINAL = [ESTADO_CONCLUIDO, ESTADO_CANCELADO]

    EM_ANDAMENTO_PRIORIZACAO = [
        ESTADO_EM_NEGOCIACAO,
        ESTADO_EM_ANALISE,
        ESTADO_EM_DESENVOLVIMENTO,
        ESTADO_EM_HOMOLOGACAO,
        ESTADO_HOMOLOGADA,
        ESTADO_EM_IMPLANTACAO,
    ]

    ENCAMINHAMENTOS = {
        ESTADO_ABERTO: [ESTADO_EM_NEGOCIACAO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_EM_NEGOCIACAO: [ESTADO_EM_ANALISE, ESTADO_EM_DESENVOLVIMENTO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_EM_ANALISE: [ESTADO_APROVADO, ESTADO_EM_NEGOCIACAO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_APROVADO: [ESTADO_EM_NEGOCIACAO, ESTADO_EM_DESENVOLVIMENTO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        # Entrar e sair de "Em homologação" para desenvolvimento/homologada é consequência da entrega
        # (EntregaService), nunca transição manual. As saídas manuais cancelam a entrega pendente.
        ESTADO_EM_DESENVOLVIMENTO: [ESTADO_EM_NEGOCIACAO, ESTADO_EM_IMPLANTACAO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_EM_HOMOLOGACAO: [ESTADO_EM_NEGOCIACAO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_HOMOLOGADA: [ESTADO_EM_NEGOCIACAO, ESTADO_EM_IMPLANTACAO, ESTADO_SUSPENSO, ESTADO_CANCELADO],
        ESTADO_EM_IMPLANTACAO: [ESTADO_EM_NEGOCIACAO, ESTADO_SUSPENSO, ESTADO_CONCLUIDO],
        ESTADO_SUSPENSO: [ESTADO_EM_NEGOCIACAO, ESTADO_EM_DESENVOLVIMENTO, ESTADO_CANCELADO],
        ESTADO_CONCLUIDO: [],
        ESTADO_CANCELADO: [],
    }

    ESTADO_CHOICES = [
        [ESTADO_ABERTO, ESTADO_ABERTO],
        [ESTADO_EM_NEGOCIACAO, ESTADO_EM_NEGOCIACAO],
        [ESTADO_EM_ANALISE, ESTADO_EM_ANALISE],
        [ESTADO_APROVADO, ESTADO_APROVADO],
        [ESTADO_EM_DESENVOLVIMENTO, ESTADO_EM_DESENVOLVIMENTO],
        [ESTADO_EM_HOMOLOGACAO, ESTADO_EM_HOMOLOGACAO],
        [ESTADO_HOMOLOGADA, ESTADO_HOMOLOGADA],
        [ESTADO_EM_IMPLANTACAO, ESTADO_EM_IMPLANTACAO],
        [ESTADO_CONCLUIDO, ESTADO_CONCLUIDO],
        [ESTADO_CANCELADO, ESTADO_CANCELADO],
        [ESTADO_SUSPENSO, ESTADO_SUSPENSO],
    ]

    ESTADO_AMIGAVEL = {
        ESTADO_ABERTO: 'Solicitar',
        ESTADO_EM_NEGOCIACAO: 'Negociar',
        ESTADO_EM_ANALISE: 'Analisar',
        ESTADO_APROVADO: 'Aprovar',
        ESTADO_EM_DESENVOLVIMENTO: 'Desenvolver',
        ESTADO_EM_HOMOLOGACAO: 'Homologar',
        ESTADO_HOMOLOGADA: 'Homologada',
        ESTADO_EM_IMPLANTACAO: 'Implantar',
        ESTADO_CONCLUIDO: 'Concluir',
        ESTADO_CANCELADO: 'Cancelar',
        ESTADO_SUSPENSO: 'Suspender',
    }

    ESTADO_FLUXO = OrderedDict()
    ESTADO_FLUXO[ESTADO_ABERTO] = 'Etapa de abertura da demanda (Responsável: Demandante)'
    ESTADO_FLUXO[ESTADO_EM_NEGOCIACAO] = 'Etapa de levantamento de requisitos (Responsável: Analistas)'
    ESTADO_FLUXO[ESTADO_EM_ANALISE] = 'Etapa de análise da consolidação da demanda (Responsável: Demandantes e Interessados)'
    ESTADO_FLUXO[ESTADO_APROVADO] = 'Etapa de aprovação da consolidação da demanda'
    ESTADO_FLUXO[ESTADO_EM_DESENVOLVIMENTO] = 'Etapa de desenvolvimento da demanda (Responsável: Desenvolvedor)'
    ESTADO_FLUXO[ESTADO_EM_HOMOLOGACAO] = 'Etapa de validação da entrega pendente (Responsável: Demandantes)'
    ESTADO_FLUXO[ESTADO_HOMOLOGADA] = 'Etapa em que todo o escopo da demanda foi validado em entregas aprovadas'
    ESTADO_FLUXO[ESTADO_EM_IMPLANTACAO] = 'Etapa de encaminhamento da demanda para implantação (Responsável: Desenvolvedor)'
    ESTADO_FLUXO[ESTADO_CONCLUIDO] = 'Etapa de conclusão da demanda (Responsável: Sistema)'

    @classmethod
    def get_choices(cls, estado=None):
        if estado:
            choices = []

            for choice in cls.ENCAMINHAMENTOS[estado]:
                choices.append([choice, choice])

            return choices

        return cls.ESTADO_CHOICES

    @classmethod
    def get_estados_amigavel(cls, estado):
        estados = []

        for choice in cls.ENCAMINHAMENTOS[estado]:
            estados.append(cls.ESTADO_AMIGAVEL.get(choice, choice))

        return estados

    @classmethod
    def get_etapas_amigavel(cls, estado):
        estados = []

        for choice in cls.ENCAMINHAMENTOS[estado]:
            if choice not in [Situacao.ESTADO_CANCELADO, Situacao.ESTADO_SUSPENSO]:
                estados.append(cls.ESTADO_AMIGAVEL.get(choice, choice))

        return estados

    @classmethod
    def get_situacao_em_amigavel(cls, amigavel):
        """retorna o valor da constante que representa um estado"""
        for estado, valor in list(cls.ESTADO_AMIGAVEL.items()):
            if valor == amigavel:
                return estado
        return None

    @classmethod
    def eh_estado_inicial(cls, estado):
        return estado in cls.INICIAL

    @classmethod
    def eh_estado_terminal(cls, estado):
        return estado in cls.TERMINAL

    @classmethod
    def eh_estado_em_andamento_priorizacao(cls, estado):
        return estado in cls.EM_ANDAMENTO_PRIORIZACAO

    @classmethod
    def eh_estado_com_data_previsao(cls, estado):
        return estado in [cls.ESTADO_EM_ANALISE, cls.ESTADO_EM_DESENVOLVIMENTO, cls.ESTADO_EM_HOMOLOGACAO, cls.ESTADO_EM_IMPLANTACAO]

    @classmethod
    def get_status_dod_interessados(cls):
        return [
            cls.ESTADO_EM_ANALISE,
            cls.ESTADO_APROVADO,
            cls.ESTADO_EM_DESENVOLVIMENTO,
            cls.ESTADO_EM_HOMOLOGACAO,
            cls.ESTADO_HOMOLOGADA,
            cls.ESTADO_EM_IMPLANTACAO,
            cls.ESTADO_CONCLUIDO,
            cls.ESTADO_SUSPENSO,
        ]

    @classmethod
    def eh_estado_possivel(cls, demanda, estado_futuro, usuario: User = None):
        """Determina se é possível o fluxo de 'estado_atual' para 'estado_futuro',
        considerando ou não um usuário qualquer.
        """

        # fluxo padrão (estático)
        fluxo_padrao = cls.ENCAMINHAMENTOS[demanda.situacao]

        if usuario:
            # fluxo conforme usuário (personalizado)
            etapas_amigavel = demanda.get_etapas(usuario)
            fluxo_usuario = [cls.get_situacao_em_amigavel(etapa_amigavel) for etapa_amigavel in etapas_amigavel]
        else:
            fluxo_usuario = []

        # fluxo final
        fluxo = list(set(fluxo_padrao + fluxo_usuario))

        return estado_futuro in fluxo


class Tag(ModelPlus):
    SEARCH_FIELDS = ['nome', 'sigla']

    nome = models.CharFieldPlus('Nome', max_length=200, unique=True)
    sigla = models.CharFieldPlus('Sigla', null=True, blank=True)
    icone = models.CharFieldPlus(
        'Ícone', max_length=80, blank=True, null=True, help_text='Informe um ícone para representar esta Tag. Fonte: https://fontawesome.com/'
    )
    ativa = models.BooleanField('Ativa', default=True)
    apps_relacionadas = models.CharFieldPlus(
        'Apps relacionadas',
        max_length=255,
        null=True,
        blank=True,
        help_text='Referências diretas às apps do SUAP.',
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Módulo'
        verbose_name_plural = 'Módulos'

    def __str__(self):
        return self.nome

    def set_apps_relacionadas(self):
        self.apps_relacionadas = get_auto_apps_relacionadas(self.nome)

    @property
    def apps_relacionadas_as_list(self):
        if not self.apps_relacionadas:
            return []
        return [app for app in self.apps_relacionadas.split(',') if app]

    @property
    def apps_relacionadas_as_list_display(self):
        return [f'{get_app_suap_display(app)}' for app in self.apps_relacionadas_as_list]


class DemandasQueryset(models.QuerySet):
    def ativas(self):
        return self.filter().exclude(situacao__in=[Situacao.ESTADO_CANCELADO, Situacao.ESTADO_CONCLUIDO])

    def inativas(self):
        return self.filter(situacao__in=[Situacao.ESTADO_CANCELADO, Situacao.ESTADO_CONCLUIDO])

    def em_andamento(self):
        return self.filter(
            situacao__in=[
                Situacao.ESTADO_EM_NEGOCIACAO,
                Situacao.ESTADO_APROVADO,
                Situacao.ESTADO_EM_DESENVOLVIMENTO,
                Situacao.ESTADO_HOMOLOGADA,
                Situacao.ESTADO_EM_IMPLANTACAO,
            ]
        )

    def a_atualizar(self):
        qtd = Configuracao.get_valor_por_chave('demandas', 'qtd_demandas_prioritarias_por_area')
        qtd_demandas_prioritarias_por_area = qtd and int(qtd) or 5
        # demandas "Aprovada" que dependem da conclusão de outra demanda (eh_dependente) não entram no alerta
        dependente_aprovada = (
            Q(situacao=Situacao.ESTADO_APROVADO)
            & Q(dependencia__isnull=False)
            & ~Q(dependencia__situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO])
        )
        return self.filter(
            prioridade__lte=qtd_demandas_prioritarias_por_area,
            situacao__in=[
                Situacao.ESTADO_ABERTO,
                Situacao.ESTADO_APROVADO,
                Situacao.ESTADO_HOMOLOGADA,
            ],
        ).exclude(dependente_aprovada)

    def a_acompanhar(self) -> DemandasQueryset:
        # Demandas na etapa "Em desenvolvimento" ou "Em implantação" em atraso (ou seja, que hoje é maior que a data de fim da etapa atual).
        demandas_em_atraso = self.filter(
            situacao__in=[Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_IMPLANTACAO],
            historicosituacao__data_previsao__lt=date.today(),
            historicosituacao__id__in=HistoricoSituacao.objects.filter(demanda_id=F('demanda_id'))
            .values('demanda_id')
            .annotate(max_id=Max('id'))
            .values('max_id'),
        ).distinct()

        # Demanda na etapa "Em análise" ou "Em homologação" que já tenham passado 14 dias após a data fim da etapa atual.
        data_limite = date.today() - timedelta(days=14)
        demandas_analise_homologacao_atraso = self.filter(
            situacao__in=[Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO],
            historicosituacao__data_previsao__lt=data_limite,
            historicosituacao__id__in=HistoricoSituacao.objects.filter(demanda_id=F('demanda_id'))
            .values('demanda_id')
            .annotate(max_id=Max('id'))
            .values('max_id'),
        ).distinct()

        # Demanda na etapa "Homologada" que já tenha passado 4 dias nessa etapa.
        data_limite = date.today() - timedelta(days=4)
        demandas_homologadas_atraso = self.filter(
            situacao=Situacao.ESTADO_HOMOLOGADA,
            historicosituacao__data_hora__date__lt=data_limite,
            historicosituacao__situacao=Situacao.ESTADO_HOMOLOGADA,
            historicosituacao__id__in=HistoricoSituacao.objects.filter(demanda_id=F('demanda_id'), situacao=Situacao.ESTADO_HOMOLOGADA)
            .values('demanda_id')
            .annotate(max_id=Max('id'))
            .values('max_id'),
        ).distinct()

        # Demanda na etapa "Em negociação", não-priorizada, que já tenha passado 21 dias nessa etapa.
        data_limite = date.today() - timedelta(days=21)
        qtd = Configuracao.get_valor_por_chave('demandas', 'qtd_demandas_prioritarias_por_area')
        qtd_demandas_prioritarias_por_area = qtd and int(qtd) or 5
        demandas_negociacao_atraso_baixa_prioridade = self.filter(
            situacao=Situacao.ESTADO_EM_NEGOCIACAO,
            prioridade__gt=qtd_demandas_prioritarias_por_area,
            historicosituacao__data_hora__date__lt=data_limite,
            historicosituacao__situacao=Situacao.ESTADO_EM_NEGOCIACAO,
            historicosituacao__id__in=HistoricoSituacao.objects.filter(demanda_id=F('demanda_id'), situacao=Situacao.ESTADO_EM_NEGOCIACAO)
            .values('demanda_id')
            .annotate(max_id=Max('id'))
            .values('max_id'),
        ).distinct()

        return demandas_em_atraso | demandas_analise_homologacao_atraso | demandas_homologadas_atraso | demandas_negociacao_atraso_baixa_prioridade

    def aguardando_feedback(self):
        filtro_em_analise = Q(situacao__in=[Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO, Situacao.ESTADO_SUSPENSO])
        filtro_modificacao = Q(dod__validacao_revisao_solicitada=True)
        return self.filter(filtro_em_analise | filtro_modificacao).distinct()

    def consolidacao_pendente(self):
        return self.filter(dod__validacao_revisao_solicitada=True)


class DemandasManager(models.Manager):
    def get_queryset(self):
        return DemandasQueryset(self.model, using=self._db)

    def ativas(self):
        return self.get_queryset().ativas()

    def inativas(self):
        return self.get_queryset().inativas()

    def em_andamento(self):
        return self.get_queryset().em_andamento()

    def a_atualizar(self):
        return self.get_queryset().a_atualizar()

    def a_acompanhar(self):
        return self.get_queryset().a_acompanhar()

    def aguardando_feedback(self):
        return self.get_queryset().aguardando_feedback()

    def consolidacao_pendente(self):
        return self.get_queryset().consolidacao_pendente()


@reversion.register()
class Demanda(ModelPlus):
    SEARCH_FIELDS = ['id', 'titulo', 'descricao']
    area = models.ForeignKeyPlus('demandas.AreaAtuacaoDemanda', verbose_name='Área de Atuação', null=True)
    tipo = models.CharFieldPlus('Tipo', choices=TipoDemanda.TIPODEMANDA_CHOICES, default=TipoDemanda.FUNCIONALIDADE)
    titulo = models.CharField('Título da Demanda', max_length=250)
    descricao = models.TextField('Descrição da Demanda', help_text='Evite colocar informações sensiveis nesse campo pois essa descrição é pública.')
    privada = models.BooleanField(
        'Privada?', default=False, help_text='Indique se a demanda deve ser privada nos seus detalhes até a sua finalização.'
    )
    aberto_em = models.DateTimeField('Aberto Em', auto_now_add=True)
    prazo_legal = models.DateField(
        'Prazo Legal',
        help_text='Só preencher esse campo se existir um prazo legal da demanda. ex: Data limite(por lei, ou determinação) para estar em produção.',
        blank=True,
        null=True,
    )
    data_atualizacao = models.DateField('Data da Última Atualização', blank=True, null=True)
    demandantes = models.ManyToManyField(User, related_name='demanda_demandantes_set', verbose_name='Demandantes')
    interessados = models.ManyToManyField(
        User,
        related_name='demanda_interessados_set',
        verbose_name='Interessados',
        help_text='Vincule outros usuários que desejem acompanhar as discussões desta demanda.',
    )
    observadores_pendentes = models.ManyToManyField(User, related_name='demanda_observadores_pendentes_set', verbose_name='Observadores Pendentes')
    observadores = models.ManyToManyField(User, related_name='demanda_observadores_set', verbose_name='Observadores')
    desenvolvedores = models.ManyToManyField(
        User, related_name='demanda_desenvolvedores_set', verbose_name='Desenvolvedores', help_text='Vincule usuários desenvolvedores desta demanda.'
    )
    analistas = models.ManyToManyField(
        User, related_name='demanda_analistas_set', verbose_name='Analista', help_text='Vincule usuários analistas dessa demanda'
    )
    tags = models.ManyToManyField(Tag, related_name='demanda_tags_set', verbose_name='Tags')

    prioridade = models.PositiveIntegerField('Prioridade', null=True, blank=True)
    situacao = models.CharFieldPlus('Etapa', choices=Situacao.ESTADO_CHOICES, default=Situacao.ESTADO_ABERTO)

    especificacao_tecnica = models.TextField(verbose_name='Especificação Técnica', blank=True)

    # Integração com gitlab
    branch = models.CharFieldPlus(
        'Nome da branch',
        null=True,
        blank=True,
        help_text='Ao informar o nome da branch, o SUAP criará o merge request assim que a demanda for homologada.',
    )
    id_merge_request = models.PositiveIntegerField(
        'ID do Merge-Request',
        help_text='Identificador do Merge-request. Exemplo: na url https://gitlab.com/suap/-/merge_requests/25 o número 25 é o identificador.',
        null=True,
        blank=True,
    )
    milestone = models.PositiveIntegerField('ID da Milestone', null=True)
    id_repositorio = models.PositiveIntegerField('ID do Repositório GIT', null=True)

    consolidacao_sempre_visivel = models.BooleanField('Consolidação visível durante todas as etapas?', default=False)

    votos = models.IntegerFieldPlus(verbose_name='Votos', default=0)

    # o desenvolvimento de uma demanda (demanda dependente) depende da conclusão de uma outra demanda (demanda pré-requisito)
    dependencia = models.ForeignKeyPlus('demandas.Demanda', verbose_name='Dependência', blank=True, null=True, on_delete=models.SET_NULL)

    parent = models.ForeignKeyPlus(
        'demandas.Demanda',
        verbose_name='Demanda Pai',
        blank=True,
        null=True,
        on_delete=models.SET_NULL,
        related_name='subdemandas',
        help_text='Preencha apenas se esta for uma sub-demanda de outra demanda.',
    )
    prioridade_interna = models.PositiveIntegerField(
        'Prioridade Interna',
        null=True,
        blank=True,
        help_text='Ordem de prioridade entre as sub-demandas do mesmo pai. Usado apenas quando esta demanda for uma sub-demanda (parent preenchido).',
    )

    objects = DemandasManager()

    class Meta:
        verbose_name = 'Demanda'
        verbose_name_plural = 'Demandas'
        ordering = ['prioridade', 'area']
        permissions = (
            ('atende_demanda', 'Pode atender Demanda'),
            ('pode_relatorio', 'Pode visualizar relatórios'),
            ('visualiza_forca_trabalho', 'Pode visualizar força de trabalho'),
        )

    def __str__(self):
        if self.tem_dod:
            titulo = self.get_dod().descricao
        else:
            titulo = self.titulo
        return f'Demanda {self.pk}: {titulo}'

    @property
    def eh_subdemanda(self) -> bool:
        """True se esta demanda for filha de outra."""
        return self.parent_id is not None

    @property
    def eh_raiz(self) -> bool:
        """True se esta demanda for uma demanda principal (sem pai)."""
        return self.parent_id is None

    @property
    def ancestrais(self) -> list:
        """
        Retorna a lista de demandas ancestrais, do pai direto até a raiz.
        Útil para breadcrumb e validações.
        """
        resultado = []
        atual = self.parent
        visitados = set()
        while atual and atual.pk not in visitados:
            resultado.append(atual)
            visitados.add(atual.pk)
            atual = atual.parent
        return resultado

    # ─── Sub-demandas filhas ───────────────────────────────────────────────────────
    def get_subdemandas(self):
        """QuerySet das sub-demandas diretas, ordenadas por prioridade interna."""
        return self.subdemandas.order_by('prioridade_interna', 'pk')

    def get_subdemandas_ativas(self):
        """Sub-demandas que não estão concluídas nem canceladas."""
        return self.get_subdemandas().exclude(situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO])

    def get_subdemandas_concluidas_ou_canceladas(self):
        return self.get_subdemandas().filter(situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO])

    # ─── Progresso agregado ────────────────────────────────────────────────────────

    @property
    def total_subdemandas(self) -> int:
        return self.subdemandas.count()

    @property
    def subdemandas_encerradas(self) -> int:
        return self.subdemandas.filter(situacao__in=[Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO]).count()

    @property
    def percentual_conclusao(self) -> int:
        """
        Percentual de sub-demandas concluídas ou canceladas em relação ao total.
        Retorna 0 se não houver sub-demandas.
        """
        total = self.total_subdemandas
        if not total:
            return 0
        return round((self.subdemandas_encerradas / total) * 100)

    @property
    def pode_concluir_pai(self) -> bool:
        """
        Regra: a demanda pai só pode ser concluída se não houver
        sub-demandas ainda ativas (pendentes de conclusão ou cancelamento).
        """
        if not self.subdemandas.exists():
            return True
        return not self.get_subdemandas_ativas().exists()

    # ─── Prioridade interna ────────────────────────────────────────────────────────

    @property
    def proxima_prioridade_interna(self) -> int:
        """
        Retorna o próximo valor disponível de prioridade_interna
        entre as sub-demandas deste pai.
        Usado ao criar uma nova sub-demanda sem prioridade explícita.
        """
        ultima = self.subdemandas.filter(prioridade_interna__isnull=False).order_by('-prioridade_interna').first()
        return (ultima.prioridade_interna + 1) if ultima else 1

    @classmethod
    def validar(cls, data=None, instance=None, tipo='demandantes'):
        instance = ModelValidation.instance_for_validation(cls, data, instance)

        # permite apenas demandantes da área de atuação da demanda
        area_demandantes = instance.area.get_demandantes() if instance.area else []
        demanda_demandantes = instance.demandantes
        if area_demandantes and demanda_demandantes:
            diff = set(demanda_demandantes) - set(area_demandantes)
            if diff:
                raise ValidationError(
                    {tipo: f"Os seguintes demandantes não pertencem à área '{instance.area}': {', '.join([str(user) for user in diff])}."}
                )

    @property
    def pode_editar_dependencia(self):
        """contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
        conclusão de uma outra demanda (demanda pré-requisito)"""
        return not self.id or self.situacao in [
            Situacao.ESTADO_ABERTO,
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_SUSPENSO,
        ]

    @property
    def dependencia_demandas_choices(self):
        """contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
        conclusão de uma outra demanda (demanda pré-requisito)"""
        area_atuacao = self.area
        if area_atuacao:
            qs_demandas_ativas_area_atuacao = Demanda.objects.filter(area=area_atuacao).ativas().exclude(id=self.id)
        else:
            qs_demandas_ativas_area_atuacao = Demanda.objects.ativas().exclude(id=self.id)
        return qs_demandas_ativas_area_atuacao

    @property
    def eh_dependente(self):
        """contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
        conclusão de uma outra demanda (demanda pré-requisito)"""
        if self.dependencia is not None:
            return self.dependencia.situacao not in [Situacao.ESTADO_CONCLUIDO, Situacao.ESTADO_CANCELADO]
        return False

    @property
    def demandas_dependentes(self):
        """contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
        conclusão de uma outra demanda (demanda pré-requisito)"""
        return Demanda.objects.filter(dependencia=self)

    @property
    def eh_pre_requisito(self):
        """contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
        conclusão de uma outra demanda (demanda pré-requisito)"""
        return self.demandas_dependentes.exists()

    @property
    def pode_desenvolver(self):
        if self.eh_dependente:
            """ contexto: o desenvolvimento de uma demanda (demanda dependente) depende da
                conclusão de uma outra demanda (demanda pré-requisito)
                etapas desenvolvimento: desenvolvimento > em homologação > homologada > em implantação > concluída """
            return self.dependencia.eh_situacao_terminal()  # compreende as situações concluído e cancelado
        return True

    @staticmethod
    def situacoes_pre_desenvolvimento():
        return [
            Situacao.ESTADO_ABERTO,
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
        ]

    @staticmethod
    def situacoes_pre_desenvolvimento_amigavel():
        return [
            Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_ABERTO],
            Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_EM_NEGOCIACAO],
            Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_EM_ANALISE],
            Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_APROVADO],
        ]

    @classmethod
    @transaction.atomic
    def atualizar_prioridades(self, area, usuario):
        demandas = Demanda.objects.ativas().filter(area=area).order_by('prioridade', 'pk')
        for count, demanda in enumerate(demandas, start=1):
            if demanda.prioridade != count:
                demanda.prioridade = count
                Demanda.criar_historico_prioridade(demanda, usuario, count)
                demanda.save()

        # Demandas Concluídas ou Canceladas devem ter prioridade setada para None
        demandas_inativas = Demanda.objects.inativas().filter(area=area, prioridade__isnull=False)
        for inativa in demandas_inativas:
            Demanda.criar_historico_prioridade(inativa, usuario, None)
        demandas_inativas.update(prioridade=None)

    @classmethod
    def colocar_demanda_em_ultima_prioridade(cls, demanda, usuario):
        area = demanda.area
        area_as_outras_demandas = Demanda.objects.ativas().filter(area=area).exclude(prioridade=None).exclude(pk=demanda.pk)

        if area_as_outras_demandas.exists():
            ultima_prioridade = area_as_outras_demandas.order_by('-prioridade').first().prioridade + 1
        else:
            ultima_prioridade = 1

        demanda.prioridade = ultima_prioridade
        demanda.save()

        # atualiza a prioridade das demandas da área
        Demanda.atualizar_prioridades(area, usuario)

    @classmethod
    def criar_historico_prioridade(self, demanda, usuario, prioridade):
        HistoricoPrioridade.objects.create(demanda=demanda, prioridade=prioridade, usuario=usuario)

    def permite_visualizar(self, user):
        return user.has_perm('demandas.atende_demanda') or user.has_perm('demandas.change_demanda') or user.has_perm('demandas.view_demanda')

    def pode_visualizar_consolidacao(self, user: User) -> bool:
        return (
            self.consolidacao_sempre_visivel
            or user.has_group_cached('Analista')
            or user.has_group_cached('Desenvolvedor')
            or self.ja_foi_aprovada()
            or self.em_analise
        )

    def eh_demandante(self, user):
        return self.demandantes.filter(pk=user.pk).exists()

    def eh_interessado(self, user):
        return self.interessados.filter(pk=user.pk).exists()

    def eh_observador_pendente(self, user):
        return self.observadores_pendentes.filter(pk=user.pk).exists()

    def eh_observador(self, user):
        return self.observadores.filter(pk=user.pk).exists()

    def pode_anexar(self, user):
        return (self.eh_demandante(user) or user.has_perm('demandas.atende_demanda')) and self.situacao in [
            Situacao.ESTADO_ABERTO,
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_SUSPENSO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_HOMOLOGADA,
            Situacao.ESTADO_EM_IMPLANTACAO,
        ]

    def pode_votar(self):
        return self.situacao in [Situacao.ESTADO_ABERTO, Situacao.ESTADO_EM_NEGOCIACAO, Situacao.ESTADO_SUSPENSO] and not self.privada

    def get_prioridade_display(self):
        return str(self.prioridade) if self.prioridade else 'Sem prioridade'

    @property
    def em_negociacao(self):
        return self.situacao == Situacao.ESTADO_EM_NEGOCIACAO

    @property
    def em_analise(self):
        return self.situacao == Situacao.ESTADO_EM_ANALISE

    @property
    def aprovada(self):
        return self.situacao == Situacao.ESTADO_APROVADO

    @property
    def em_desenvolvimento(self):
        return self.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO

    @property
    def em_homologacao(self):
        return self.situacao == Situacao.ESTADO_EM_HOMOLOGACAO

    @property
    def homologada(self):
        return self.situacao == Situacao.ESTADO_HOMOLOGADA

    # ── Entregas ─────────────────────────────────────────────────────────────
    # "Em homologação" = existe uma entrega aguardando o demandante
    # (docs/specs/2026-10-21-demandas-fluxo-entrega-homologacao.md).

    @property
    def entrega_pendente(self):
        from .entrega import StatusEntrega

        return self.entregas.filter(status=StatusEntrega.ENVIADA).first()

    @property
    def ambiente_homologacao_atual(self):
        """Ambiente da entrega pendente ou, sem ela, o da entrega mais recente que tenha um."""
        entrega = self.entrega_pendente or self.entregas.filter(ambiente_homologacao__isnull=False).first()
        return entrega.ambiente_homologacao if entrega else None

    @property
    def recebe_entregas(self) -> bool:
        return self.situacao in (Situacao.ESTADO_EM_DESENVOLVIMENTO, Situacao.ESTADO_EM_HOMOLOGACAO)

    def get_especificacoes_sem_entrega_aprovada(self):
        """Especificações da consolidação ainda não validadas em nenhuma entrega aprovada."""
        from .consolidacao import Especificacao
        from .entrega import StatusEntrega

        aprovadas = Especificacao.objects.filter(dod__demanda=self, entregas__status=StatusEntrega.APROVADA)
        return Especificacao.objects.filter(dod__demanda=self).exclude(pk__in=aprovadas)

    def tem_especificacoes(self) -> bool:
        from .consolidacao import Especificacao

        return Especificacao.objects.filter(dod__demanda=self).exists()

    def pode_validar_entrega(self, user: User, entrega) -> bool:
        """Demandantes (e o demandante responsável da área) validam; quem entregou, nunca."""
        if entrega.cadastrada_por_id == user.pk:
            return False
        return bool(self.eh_demandante(user) or self.eh_demandante_responsavel(user))

    def get_ultima_previsao_da_etapa(self, situacao: str) -> date | None:
        return self.historicosituacao_set.filter(situacao=situacao, data_previsao__isnull=False).values_list('data_previsao', flat=True).first()

    def em_atraso(self):
        ultimo_historico_situacao = self.get_ultimo_historico_situacao()
        return bool(ultimo_historico_situacao and ultimo_historico_situacao.em_atraso)

    @property
    def pode_remover_anexo(self):
        return self.situacao in [Situacao.ESTADO_ABERTO, Situacao.ESTADO_EM_NEGOCIACAO]

    @property
    def tem_dod(self):
        result = False
        if self.dod_set.exists():
            result = self.get_dod().feito
        return result

    def get_dod(self):
        return self.dod_set.first()

    def ja_foi_aprovada(self):
        return self.situacao in [
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_HOMOLOGADA,
            Situacao.ESTADO_EM_IMPLANTACAO,
            Situacao.ESTADO_CONCLUIDO,
        ]

    def nao_foi_homologada(self):
        return self.situacao in [
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
        ]

    def eh_situacao_inicial(self):
        return Situacao.eh_estado_inicial(self.situacao)

    def eh_situacao_terminal(self):
        return Situacao.eh_estado_terminal(self.situacao)

    def eh_situacao_com_data_previsao(self):
        return Situacao.eh_estado_com_data_previsao(self.situacao)

    def get_id_repositorio(self):
        if self.id_repositorio:
            return self.id_repositorio
        return Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')

    def get_situacoes(self):
        return Situacao.get_estados_amigavel(self.situacao)

    def get_etapas(self, usuario: User = None):
        """Fluxo possível a partir do estado atual, considerando ou não um usuário qualquer.
        As etapas retornadas por este método NÃO INCLUEM as situações "Cancelado" e "Suspenso".
        """

        etapas = []
        if not self.pode_desenvolver:
            etapas = [etapa for etapa in etapas if etapa in Demanda.situacoes_pre_desenvolvimento_amigavel()]
        else:
            etapas = Situacao.get_etapas_amigavel(self.situacao)

        # analista de demanda em negociação pode encaminhar demanda para a etapa "solicitada" (estado aberto)
        if self.situacao == Situacao.ESTADO_EM_NEGOCIACAO and usuario and usuario.has_group_cached('Analista'):
            etapas.insert(0, Situacao.ESTADO_AMIGAVEL.get(Situacao.ESTADO_ABERTO, Situacao.ESTADO_ABERTO))

        # "Homologar" é atalho para cadastrar a entrega: a etapa "Em homologação" é consequência dela.
        if usuario and self.pode_enviar_para_homologacao(usuario):
            etapas.insert(0, Situacao.ESTADO_AMIGAVEL[Situacao.ESTADO_EM_HOMOLOGACAO])

        dod = self.get_dod()
        if dod and dod.revisaoespecificacao_set.exists():
            etapas = [item for item in etapas if item not in ('Implantar', 'Homologada')]

        return etapas

    def pode_enviar_para_homologacao(self, usuario: User) -> bool:
        """A equipe envia para homologação (cadastra a entrega) a demanda em desenvolvimento sem entrega pendente."""
        return (
            self.situacao == Situacao.ESTADO_EM_DESENVOLVIMENTO
            and self.pode_desenvolver
            and usuario.has_perm('demandas.atende_demanda')
            and self.entrega_pendente is None
        )

    def get_ultimo_historico_situacao(self):
        return self.historicosituacao_set.first()

    def permite_alterar(self):
        return self.situacao not in Situacao.TERMINAL

    def permite_cancelar(self):
        return self.situacao not in Situacao.TERMINAL

    def get_absolute_url(self):
        return reverse_lazy('demanda_visualizar', kwargs={'demanda_id': self.pk})

    def get_visualizar_demanda_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def tem_historico_revisoes(self):
        return Version.objects.get_for_object(self).exists()

    def gerenciar_issues_gitlab(self):
        from .consolidacao import Especificacao

        if self.situacao == Situacao.ESTADO_EM_HOMOLOGACAO:
            issues = (
                Especificacao.objects.filter(dod__demanda_id=self.id, gitlab_issue_url__isnull=False)
                .values_list('gitlab_issue_url', flat=True)
                .distinct()
            )
            if issues.exists():
                conf = ferramentas_configuradas()
                for issue_url in issues:
                    gitlab_issue_id = issue_url.split('/')[-1]
                    gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
                    gitlab_issue.labels.append(conf['git_label_done'])
                    for label in [conf['git_label_feedback'], conf['git_label_todo'], conf['git_label_doing']]:
                        if label in gitlab_issue.labels:
                            gitlab_issue.labels.remove(label)
                    gitlab_issue.save()
        elif self.situacao in [Situacao.ESTADO_HOMOLOGADA, Situacao.ESTADO_EM_IMPLANTACAO]:
            issues = (
                Especificacao.objects.filter(dod__demanda_id=self.id, gitlab_issue_url__isnull=False)
                .values_list('gitlab_issue_url', flat=True)
                .distinct()
            )
            if issues.exists():
                conf = ferramentas_configuradas()
                for issue_url in issues:
                    gitlab_issue_id = issue_url.split('/')[-1]
                    gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
                    gitlab_issue.labels.append(conf['git_label_done'])
                    for label in [conf['git_label_feedback'], conf['git_label_todo'], conf['git_label_doing']]:
                        if label in gitlab_issue.labels:
                            gitlab_issue.labels.remove(label)
                    if gitlab_issue.state == 'opened':
                        gitlab_issue.state_event = 'close'
                    gitlab_issue.save()
        elif self.situacao == Situacao.ESTADO_EM_NEGOCIACAO:
            issues = (
                Especificacao.objects.filter(dod__demanda_id=self.id, gitlab_issue_url__isnull=False)
                .values_list('gitlab_issue_url', flat=True)
                .distinct()
            )
            if issues.exists():
                conf = ferramentas_configuradas()
                for issue_url in issues:
                    gitlab_issue_id = issue_url.split('/')[-1]
                    gitlab_issue = conf['git'].projects.get(conf['gitlab_suap_id']).issues.get(gitlab_issue_id)
                    gitlab_issue.labels.append(conf['git_label_doing'])
                    for label in [conf['git_label_feedback'], conf['git_label_todo'], conf['git_label_done']]:
                        if label in gitlab_issue.labels:
                            gitlab_issue.labels.remove(label)
                    if gitlab_issue.state == 'closed':
                        gitlab_issue.state_event = 'reopen'
                    gitlab_issue.save()

    @staticmethod
    def branch_existe(branch):
        result = False
        try:
            conf = ferramentas_configuradas()
            conf['git'].projects.get(conf['gitlab_suap_id']).branches.get(branch)
            result = True
        except Exception:
            pass
        return result

    def criar_mergerequest_gitlab(self):
        if self.branch:
            conf = ferramentas_configuradas()
            projeto = conf['git'].projects.get(conf['gitlab_suap_id'])
            try:
                if Demanda.branch_existe(self.branch):
                    merge_requests = projeto.mergerequests.list(source_branch=self.branch, state='opened')
                    mr = None
                    if merge_requests:
                        mr = merge_requests[0]
                        title = mr.title
                        if title.lower().startswith('draft:'):
                            mr.title = title.split(':', 1)[-1].strip()
                            mr.save()
                    else:
                        merge_request_data = {
                            'source_branch': self.branch,
                            'target_branch': 'master',
                            'title': f'[{self.area}] Demanda {self.id}: {self.titulo}',
                            'description': f"""### Descrição\n\n{settings.SITE_URL}{self.get_absolute_url()}\n\n/milestone %"Backlog - Atividades"\n\nChangelog: changed""",
                            'squash': True,
                            'remove_source_branch': True,
                        }
                        analista = AnalistaDesenvolvedor.objects.filter(usuario=self.analistas.first()).first()
                        analista_gitlab = conf['git'].users.list(username=analista.username_gitlab)
                        if analista_gitlab:
                            merge_request_data['assignee_id'] = analista_gitlab[0].id
                        mr = projeto.mergerequests.create(merge_request_data)
                    if mr:
                        self.id_merge_request = mr.encoded_id
                        self.save()
            except Exception as e:
                capture_exception(e)

    @transaction.atomic
    def alterar_situacao(self, usuario, situacao, **kwargs):
        """Muda a etapa da demanda, registra o histórico, comenta e notifica."""
        texto_comentario = kwargs.get('comentario')
        data_previsao = kwargs.get('data_previsao')
        data_conclusao = kwargs.get('data_conclusao')

        self._atualizar_equipe(usuario, kwargs.get('analistas'), kwargs.get('desenvolvedores'), kwargs.get('branch'))

        # Se demanda é concluída ou cancelada, a prioridade é definida como None e a Área tem a sua lista de prioridades atualizadas
        atualizar_prioridade = Situacao.eh_estado_terminal(situacao)
        if atualizar_prioridade:
            self.prioridade = None

        self.situacao = situacao
        implantacao_pelo_sistema = self._aplicar_efeitos_da_etapa(usuario, data_previsao)

        if kwargs.get('id_merge_request'):
            self.id_merge_request = kwargs.get('id_merge_request')
        self.save()

        if atualizar_prioridade:
            Demanda.atualizar_prioridades(self.area, usuario)

        novo_historico = self._registrar_historico_situacao(usuario, data_previsao, data_conclusao)
        if usuario:
            self._comentar_alteracao_situacao(usuario, novo_historico, texto_comentario, kwargs.get('editou_data_previsao'))

        eh_observador = usuario and self.eh_observador(usuario) or False
        Notificar.situacao_alterada(self, texto_comentario, self.em_analise, eh_observador)
        if self.situacao == Situacao.ESTADO_CONCLUIDO:
            self.gerar_atualizacao_demanda()

        try:
            self.gerenciar_issues_gitlab()
        except Exception as e:
            capture_exception(e)

        if implantacao_pelo_sistema:
            data_prevista = somar_dias_uteis(datetime.today(), 10)
            self.alterar_situacao(None, Situacao.ESTADO_EM_IMPLANTACAO, data_previsao=data_prevista)

    def _atualizar_equipe(self, usuario: User | None, analistas, desenvolvedores, branch: str | None) -> None:
        if analistas:
            novos_analistas = set(analistas) - set(self.analistas.all())
            self.analistas.set(analistas)
            Notificar.analistas_vinculados_a_demanda(self, novos_analistas, usuario)

        if desenvolvedores:
            novos_desenvolvedores = set(desenvolvedores) - set(self.desenvolvedores.all())
            self.desenvolvedores.set(desenvolvedores)
            Notificar.desenvolvedores_vinculados_a_demanda(self, novos_desenvolvedores, usuario)

        if branch and Demanda.branch_existe(branch):
            self.branch = branch

    def _aplicar_efeitos_da_etapa(self, usuario: User | None, data_previsao: date | None) -> bool:
        """Efeitos colaterais de entrar na etapa atual. Devolve se a implantação segue pelo sistema."""
        if self.situacao == Situacao.ESTADO_EM_HOMOLOGACAO:
            self._sincronizar_prazo_da_entrega_pendente(data_previsao)
        else:
            self._cancelar_entrega_pendente(usuario)

        if self.situacao == Situacao.ESTADO_HOMOLOGADA and self.branch:
            self.criar_mergerequest_gitlab()
            return bool(self.id_merge_request)
        if self.situacao == Situacao.ESTADO_EM_NEGOCIACAO:
            dod = self.get_dod()
            if dod:
                for item in dod.revisaoespecificacao_set.all():
                    item.aprovar(usuario)
        return False

    def _sincronizar_prazo_da_entrega_pendente(self, data_previsao: date | None) -> None:
        """A previsão da etapa "Em homologação" é o prazo de resposta da entrega: um relógio só."""
        entrega = self.entrega_pendente
        if entrega and data_previsao and entrega.prazo_feedback != data_previsao:
            entrega.prazo_feedback = data_previsao
            entrega.save()

    def _cancelar_entrega_pendente(self, usuario: User | None) -> None:
        """Sair de "Em homologação" por qualquer caminho encerra a entrega que aguardava validação."""
        from .entrega import StatusEntrega

        entrega = self.entrega_pendente
        if entrega:
            entrega.encerrar(StatusEntrega.CANCELADA, usuario, f'Demanda saiu de homologação para "{self.situacao}".')

    def _registrar_historico_situacao(self, usuario: User | None, data_previsao: date | None, data_conclusao: date | None) -> HistoricoSituacao:
        historicosituacao = self.get_ultimo_historico_situacao()
        if historicosituacao and data_conclusao:
            historicosituacao.data_conclusao = data_conclusao
            historicosituacao.save()

        novo_historico = HistoricoSituacao.objects.create(demanda=self, usuario=usuario, situacao=self.situacao, data_previsao=data_previsao)
        Demanda.objects.filter(pk=self.pk).update(data_atualizacao=data_conclusao or novo_historico.data_hora)
        return novo_historico

    def _comentar_alteracao_situacao(
        self, usuario: User, novo_historico: HistoricoSituacao, texto_comentario: str | None, editou_data_previsao: bool | None
    ) -> None:
        situacao = self.situacao
        data_previsao = novo_historico.data_previsao
        if editou_data_previsao:
            mensagem = f'Etapa da demanda alterada para <strong>{situacao}</strong>'
            if data_previsao:
                mensagem += f' com data de previsão para <strong>{format(data_previsao.strftime("%d/%m/%Y"))}</strong>'
            mensagem += '.'
        else:
            comentario_nova_previsao = ''
            if not novo_historico.eh_primeiro_historico_da_etapa and data_previsao:
                comentario_nova_previsao = f'Alteração de data de previsão para <strong>{format(data_previsao.strftime("%d/%m/%Y"))}</strong>.'
            if texto_comentario:
                mensagem = f'Etapa da demanda alterada para <strong>{situacao}</strong>. {comentario_nova_previsao}'
            else:
                mensagem = f'Etapa da demanda alterada para {situacao}. {comentario_nova_previsao}'

        if texto_comentario:
            mensagem = f'{mensagem}\n--\n{texto_comentario}'
        adicionar_comentario(usuario=usuario, mensagem=mensagem, demanda=self)

    def gerar_atualizacao_demanda(self):
        from .atualizacao import Atualizacao

        if self.situacao == Situacao.ESTADO_CONCLUIDO:
            hoje = date.today()
            dod = self.dod_set.first()
            grupos = Group.objects.filter(name__in=dod.grupos_envolvidos_names)

            kwargs = {
                'descricao': dod.descricao,
                'detalhamento': dod.detalhamento,
                'tipo': Atualizacao.FUNCIONALIDADE,
                'data': hoje,
            }

            atualizacao, created = Atualizacao.objects.get_or_create(demanda=self, defaults=kwargs)
            if created:
                atualizacao.grupos.set(grupos)
                responsaveis = User.objects.filter(
                    pk__in=self.desenvolvedores.all().values_list('pk', flat=True) | self.analistas.all().values_list('pk', flat=True)
                )
                atualizacao.responsaveis.set(responsaveis)
                atualizacao.tags.set(self.tags.all())

    def get_anexos(self):
        return self.comentario_set.exclude(anexo__isnull=True).exclude(anexo__exact='').order_by('data_hora')

    def get_vinculos_recebedores_novas_demandas(self):
        vinculos = []
        group = Group.objects.get(name='Recebedor de Demandas')
        usuarios = User.objects.filter(groups=group)
        for usuario in usuarios:
            vinculos.append(usuario.get_vinculo())
        return vinculos

    def get_vinculos_interessados(self):
        vinculos = []
        for demandante in self.demandantes.all():
            vinculos.append(demandante.get_vinculo())

        for interessado in self.interessados.all():
            vinculos.append(interessado.get_vinculo())
        return vinculos

    def get_vinculos_demandantes(self):
        vinculos = []
        for demandante in self.demandantes.all():
            vinculos.append(demandante.get_vinculo())
        return vinculos

    def get_vinculos_observadores(self):
        vinculos = []
        for observador in self.observadores.all():
            vinculos.append(observador.get_vinculo())
        return vinculos

    def get_vinculos_analistas(self):
        vinculos = []
        for analista in self.analistas.all():
            vinculos.append(analista.get_vinculo())
        return vinculos

    def get_vinculos_desenvolvedores(self):
        vinculos = []
        for desenvolvedor in self.desenvolvedores.all():
            vinculos.append(desenvolvedor.get_vinculo())
        return vinculos

    def get_situacao_acompanhamento(self):
        # Utilizada no Relatorio de Acompanhamento de Demandas
        if self.situacao == Situacao.ESTADO_SUSPENSO:
            return f'<span class="status status-error">Suspensa por falta de feedback desde {dateToStr(self.get_ultimo_historico_situacao().data_hora)}</span>'
        elif self.situacao in [
            Situacao.ESTADO_EM_IMPLANTACAO,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_APROVADO,
            Situacao.ESTADO_HOMOLOGADA,
        ]:
            return f'<span class="status status-alert">{self.situacao} desde {dateToStr(self.get_ultimo_historico_situacao().data_hora)}</span>'
        elif self.situacao in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO]:
            return f'<span class="status status-error">{self.situacao} desde {dateToStr(self.get_ultimo_historico_situacao().data_hora)}</span>'
        return '<span class="status status-info">Não iniciada</span>'

    def pode_comentar(self):
        return self.situacao not in Situacao.TERMINAL

    @property
    def qtd_votos(self):
        voto = DemandaVoto.objects.filter(demanda=self)
        return voto.filter(concorda=True).count() - voto.filter(concorda=False).count()

    @property
    def ja_concordou(self):
        usuario = tl.get_user()
        return DemandaVoto.objects.filter(demanda=self, usuario=usuario, concorda=True).exists()

    @property
    def ja_discordou(self):
        usuario = tl.get_user()
        return DemandaVoto.objects.filter(demanda=self, usuario=usuario, concorda=False).exists()

    def quem_concordou(self):
        return DemandaVoto.objects.filter(demanda=self, concorda=True)

    def quem_discordou(self):
        return DemandaVoto.objects.filter(demanda=self, concorda=False)

    def eh_demandante_responsavel(self, user):
        return self.area and user == self.area.demandante_responsavel

    def pode_editar(self, user):
        return self.permite_alterar and (user.has_perm('demandas.atende_demanda') or self.eh_demandante(user) or self.eh_demandante_responsavel(user))

    def pode_revisar_consolidacao(self, user: User) -> bool:
        return (self.em_desenvolvimento or self.em_homologacao) and self.analistas.filter(id=user.id).exists()

    def eh_analista(self, user: User) -> bool:
        return self.analistas.filter(id=user.id).exists()

    def pode_editar_demandantes(self, user):
        # Permite edição de demandantes em demandas não-terminais
        # e também permite superuser editar mesmo após a demanda ser terminal.
        if user and getattr(user, 'is_superuser', False):
            return True

        result = self.situacao not in Situacao.TERMINAL
        if result:
            result = (
                self.eh_demandante_responsavel(user)
                or self.area.demandantes.filter(pk=user.pk).exists()
                or user.has_perm('comum.is_recebedor_de_demandas')
                or user.has_perm('comum.is_coordenador_de_ti_sistêmico')
                or user.has_perm('comum.is_analista')
            )
        return result

    def anexos_atualizar_informacoes(self):
        for anexo in self.anexos_set.all():
            anexo.save_arquivo_informacoes()

    @staticmethod
    def get_demandas_criadas(
        data_inicio: date,
        data_fim: date,
        area: AreaAtuacaoDemanda = None,
        situacao=None,
    ) -> models.QuerySet[Demanda]:
        data_inicio = datetime.combine(data_inicio, time(0, 0, 0))
        data_fim = datetime.combine(data_fim, time(23, 59, 59))
        demandas = Demanda.objects.filter(aberto_em__range=(data_inicio, data_fim))
        if area:
            demandas = demandas.filter(area=area)
        if situacao:
            demandas = demandas.filter(situacao=situacao)
        return demandas

    @staticmethod
    def get_demandas_atualizadas(
        data_inicio: date,
        data_fim: date,
        area: AreaAtuacaoDemanda = None,
        situacao=None,
    ) -> models.QuerySet[Demanda]:
        data_inicio = datetime.combine(data_inicio, time(0, 0, 0))
        data_fim = datetime.combine(data_fim, time(23, 59, 59))
        demandas = Demanda.objects.filter(data_atualizacao__range=(data_inicio, data_fim))
        if area:
            demandas = demandas.filter(area=area)
        if situacao:
            demandas = demandas.filter(situacao=situacao)
        return demandas

    def clean(self):
        super().clean()
        self._validar_parent()

    def _validar_parent(self):
        """
        Garante integridade do vínculo pai → filho:
        - A sub-demanda não pode apontar para si mesma.
        - Não pode haver ciclo na hierarquia (A→B→A).
        - prioridade_interna só faz sentido com parent preenchido.
        - Demanda raiz (sem parent) não pode ter prioridade_interna.
        """
        if not self.parent_id:
            # demanda raiz: prioridade_interna deve estar vazia
            if self.prioridade_interna is not None:
                raise ValidationError({'prioridade_interna': 'Prioridade interna só é aplicável a sub-demandas (demandas com pai).'})
            return

        # auto-referência
        if self.pk and self.parent_id == self.pk:
            raise ValidationError({'parent': 'Uma demanda não pode ser pai de si mesma.'})

        # ciclo na hierarquia
        if self.pk and self._detectar_ciclo():
            raise ValidationError({'parent': 'O vínculo de pai selecionado criaria um ciclo na hierarquia de demandas.'})

    def _detectar_ciclo(self) -> bool:
        """
        Percorre a cadeia de ancestrais do `parent` escolhido e verifica
        se `self` aparece nela (o que configuraria um ciclo).

        Limite de profundidade: 50 níveis (proteção contra loop infinito
        em caso de inconsistência de dados legados).
        """
        visitados = set()
        atual = self.parent

        for _ in range(50):
            if atual is None:
                break
            if atual.pk == self.pk:
                return True
            if atual.pk in visitados:
                break  # ciclo já existente nos dados — para a varredura
            visitados.add(atual.pk)
            atual = atual.parent  # sobe mais um nível

        return False


class DemandaVoto(models.ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    usuario = models.CurrentUserField()
    concorda = models.BooleanField(null=True)
    cadastrado_em = models.DateTimeField('Cadastrado em', auto_now_add=True)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)

        demanda = self.demanda
        demanda.votos = demanda.qtd_votos
        demanda.save()


class NotaInterna(ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, on_delete=models.CASCADE)
    nota = models.TextField('Nota')
    usuario = models.CurrentUserField()
    cadastrado_em = models.DateTimeField('Cadastrado em', auto_now_add=True)

    class Meta:
        verbose_name = 'Nota Interna'
        verbose_name_plural = 'Notas Interna'
        ordering = ['-cadastrado_em']

    def __str__(self):
        return truncatewords(self.nota, 25)

    def save(self, *args, **kwargs):
        insert = not self.pk
        super().save(*args, **kwargs)

        if insert:
            Notificar.nota_interna_criada(self)


class Anexos(ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    arquivo = models.FileFieldPlus(upload_to='upload/demandas/anexos/', null=True, blank=True, can_view='can_view_arquivo')
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', related_name='anexos_usuario_set', on_delete=models.CASCADE)
    arquivo_informacoes = models.FileInformationField()

    class Meta:
        ordering = ['data_hora']
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'

    def can_view_arquivo(self, user):
        return user.is_authenticated and (
            self.demanda.eh_demandante(user)
            or self.demanda.eh_interessado(user)
            or self.demanda.eh_observador(user)
            or self.demanda.permite_visualizar(user)
        )

    def save(self, *args, **kwargs):
        pk = self.pk
        super().save(*args, **kwargs)
        if not pk:
            adicionar_comentario(usuario=get_user(), mensagem='Adicionou um anexo.', demanda=self.demanda)
            self.save_arquivo_informacoes()

    def save_arquivo_informacoes(self):
        if self.arquivo:
            models.FileInformationField.save_file_information(self, 'arquivo', 'arquivo_informacoes')

    def get_arquivo_informacoes(self):
        """Ler as informações do arquivo.
        Se não existir, serão primeiramente salvas."""
        if not self.arquivo_informacoes:
            self.save_arquivo_informacoes()
        return self.arquivo_informacoes


class HistoricoRevisao(ModelPlus):
    AVALIACAO_SOLICITADA = 'Solicitada a validação das alterações na consolidação'
    AVALIACAO_CONCLUIDA = 'Todas as alterações da consolidação foram avaliadas'
    AVALIACOES_CHOICES = (
        (AVALIACAO_SOLICITADA, AVALIACAO_SOLICITADA),
        (AVALIACAO_CONCLUIDA, AVALIACAO_CONCLUIDA),
    )

    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', related_name='historicorevisao_usuarios_set', on_delete=models.CASCADE)
    acao = models.CharFieldPlus('Ação', choices=AVALIACOES_CHOICES)

    class Meta:
        ordering = ['-data_hora']
        verbose_name = 'Histórico de revisão'
        verbose_name_plural = 'Históricos de revisões'


class HistoricoVinculo(ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', related_name='historicovinculo_usuarios_set', on_delete=models.CASCADE)
    acao = models.CharFieldPlus('Ação')

    class Meta:
        ordering = ['-data_hora']
        verbose_name = 'Histórico de vínculação'
        verbose_name_plural = 'Históricos de vinculações'


class HistoricoPrioridade(ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', related_name='historicoprioridade_usuarios_set', on_delete=models.CASCADE)
    prioridade = models.PositiveIntegerFieldPlus(verbose_name='Prioridade', null=True)

    def __str__(self):
        return f'{self.pk}: {self.demanda.titulo} ({self.prioridade})'

    class Meta:
        ordering = ['-data_hora']
        verbose_name = 'Histórico de Prioridades'
        verbose_name_plural = 'Históricos de Prioridades'


class HistoricoSituacao(ModelPlus):
    demanda = models.ForeignKeyPlus(Demanda, verbose_name='Demanda', on_delete=models.CASCADE)
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário', null=True, related_name='historicosituacao_usuarios_set', on_delete=models.CASCADE)
    situacao = models.CharFieldPlus('Situacao', choices=Situacao.ESTADO_CHOICES, null=True)
    data_previsao = models.DateFieldPlus('Data de Previsão', null=True)
    data_conclusao = models.DateFieldPlus('Data de Conclusão', null=True)

    def __str__(self):
        return f'{self.pk}: {self.demanda.titulo} ({self.situacao})'

    class Meta:
        ordering = ['-data_hora']
        verbose_name = 'Histórico das Etapas'
        verbose_name_plural = 'Históricos das Etapas'

    @property
    def em_atraso(self):
        data_conclusao = self.data_conclusao
        data_previsao = self.data_previsao
        if data_conclusao and data_previsao:
            if data_conclusao > data_previsao:
                return True
        elif data_previsao:
            if self.eh_ultimo_historico:
                data_posterior = date.today()
                if data_previsao < data_posterior:
                    return True
            else:
                data_posterior = self.data_historico_posterior.date()
                if data_previsao < data_posterior:
                    return True
        return False

    @property
    def eh_ultimo_historico(self):
        ultimo_historico = HistoricoSituacao.objects.filter(demanda=self.demanda).order_by('-data_hora')[0]
        return self == ultimo_historico

    @property
    def eh_primeiro_historico_da_etapa(self):
        primeiro_historico_da_etapa = (
            HistoricoSituacao.objects.filter(demanda_id=self.demanda_id, situacao=self.situacao).only('id').order_by('data_hora').first()
        )
        return self.id == primeiro_historico_da_etapa.id

    @property
    def data_historico_posterior(self):
        historico_posterior = HistoricoSituacao.objects.filter(demanda=self.demanda, id__gt=self.id).order_by('id')
        if historico_posterior:
            return historico_posterior[0].data_hora
        return None

    @property
    def get_class_situacao(self):
        if self.situacao in ['Aberta', Situacao.ESTADO_ABERTO]:
            return 'info'
        elif self.situacao in [
            Situacao.ESTADO_EM_NEGOCIACAO,
            Situacao.ESTADO_EM_ANALISE,
            Situacao.ESTADO_EM_DESENVOLVIMENTO,
            Situacao.ESTADO_EM_HOMOLOGACAO,
            Situacao.ESTADO_EM_IMPLANTACAO,
        ]:
            return 'warning'
        elif self.situacao in [Situacao.ESTADO_APROVADO, Situacao.ESTADO_HOMOLOGADA, Situacao.ESTADO_CONCLUIDO]:
            return 'success'
        return 'danger'

    @property
    def conclusao(self):
        data_conclusao = self.data_conclusao
        data_previsao = self.data_previsao
        responsaveis = 'desenvolvedores'
        if self.situacao in [Situacao.ESTADO_EM_ANALISE, Situacao.ESTADO_EM_HOMOLOGACAO]:
            responsaveis = 'demandantes'
        if data_conclusao and data_previsao:
            if data_conclusao > data_previsao:
                dias = (data_conclusao - data_previsao).days
                return '<span class="false">Em {}, com atraso de {} dias, por parte dos {}.</span>'.format(
                    date.strftime(data_conclusao, '%d/%m/%Y'), dias, responsaveis
                )
            elif data_conclusao == data_previsao:
                return '<span class="true">Em {}, por parte dos {}.</span>'.format(date.strftime(data_conclusao, '%d/%m/%Y'), responsaveis)
            return '<span class="true">Em {}, antes da previsão, por parte dos {}.</span>'.format(
                date.strftime(data_conclusao, '%d/%m/%Y'), responsaveis
            )
        elif data_conclusao and not data_previsao:
            return date.strftime(data_conclusao, '%d/%m/%Y')
        elif data_previsao:
            if self.eh_ultimo_historico:
                data_posterior = date.today()
                if data_previsao < data_posterior:
                    dias = (data_posterior - data_previsao).days
                    return f'<span class="false">Em atraso de {dias} dias, por parte dos {responsaveis}.</span>'
            else:
                data_posterior = self.data_historico_posterior.date()
                if data_previsao < data_posterior:
                    dias = (data_posterior - data_previsao).days
                    return f'<span class="false">Reprovada com atraso de {dias} dias, por parte dos {responsaveis}.</span>'
        return '-'

    def get_observacoes_historico(self):
        result = []
        if self.data_previsao:
            data_formatada = self.data_previsao.strftime('%d/%m/%Y')
            obs = 'Previsão'
            if not self.eh_primeiro_historico_da_etapa:
                obs = f'{obs} atualizada'
            result.append(f'{obs}: {data_formatada}')

        conclusao = self.conclusao
        if conclusao != '-':
            result.append(f'Conclusão: {conclusao}')
        return result
