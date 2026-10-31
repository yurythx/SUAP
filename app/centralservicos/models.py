import pandas as pd
import os.path
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from typing import Any, TypedDict
from django.apps import apps
from django.conf import settings
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator
from django.db import transaction
from django.db.models import Avg, Exists, Max, OuterRef, Q, QuerySet, Subquery
from django.db.models.functions import Coalesce
from django.db.models.signals import m2m_changed, post_delete, post_save
from django.dispatch import receiver
from django.utils.html import format_html
from django_fsm import FSMIntegerField, transition
from model_utils import Choices

from centralservicos.utils import Notificar
from comum.models import AreaAtuacao, Comentario, User, Publico
from djtools.db import models
from patrimonio.models import Inventario
from rh.models import UnidadeOrganizacional

STATUS_ATIVO = 'ativo'
AVALIACAO_RUIM = 1
AVALIACAO_REGULAR = 2
AVALIACAO_BOM = 3
AVALIACAO_OTIMO = 4
AVALIACAO_EXCELENTE = 5

AVALIACAO_CHOICES = [[AVALIACAO_RUIM, '1'], [AVALIACAO_REGULAR, '2'], [AVALIACAO_BOM, '3'], [AVALIACAO_OTIMO, '4'], [AVALIACAO_EXCELENTE, '5']]


class Tag(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=60, unique=True, help_text='Informe um nome para tag')
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')

    class Meta:
        ordering = ['nome']
        verbose_name = 'Tag'
        verbose_name_plural = 'Tags'

    def __str__(self):
        return self.nome


class GestorAreaServico(models.ModelPlus):
    gestor = models.ForeignKeyPlus(
        User,
        related_name='gestorareaservico_set',
        verbose_name='Gestor',
        null=False,
        blank=False,
        help_text='Informe o nome do gestor desta área de serviço.',
    )
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')

    class Meta:
        unique_together = ('gestor', 'area')
        ordering = ['area']
        verbose_name = 'Gestor da Área do Serviço'
        verbose_name_plural = 'Gestores das Áreas dos Serviços'

    def __str__(self):
        return f'{self.gestor} - {self.area.nome}'

    @classmethod
    def minhas_areas(cls, user):
        """Retorna uma lista de Areas em que o usuário é gestor."""
        from comum.models import AreaAtuacao

        if user.groups.filter(name='centralservicos Administrador').exists():
            return AreaAtuacao.objects.all()
        else:
            return AreaAtuacao.objects.filter(id__in=cls.objects.filter(gestor=user).values('area').distinct())


@receiver(post_save, sender=GestorAreaServico, dispatch_uid='adiciona_grupo_gestor_area_servico')
def adiciona_grupo_gestor_area_servico(sender, instance, **kwargs):
    group = Group.objects.get(name='Gestor da Central de Serviços')
    instance.gestor.groups.add(group)


@receiver(post_delete, sender=GestorAreaServico, dispatch_uid='remove_grupo_gestor_area_servico')
def remove_grupo_gestor_area_servico(sender, instance, **kwargs):
    group = Group.objects.get(name='Gestor da Central de Serviços')
    if not GestorAreaServico.objects.filter(gestor=instance.gestor).exists():
        instance.gestor.groups.remove(group)


class CentroAtendimento(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=80, help_text='Informe um nome para o Centro de Atendimento')
    eh_local = models.BooleanField('Centro de Atendimento Local?', default=False)
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        unique_together = ('nome', 'area')
        ordering = ['nome']
        verbose_name = 'Centro de Atendimento'
        verbose_name_plural = 'Centros de Atendimento'

    def __str__(self):
        return f'{self.nome} / Área: {self.area}'

    def clean(self):
        if self.pk and not self.ativo:
            estava_ativo = CentroAtendimento.objects.filter(pk=self.pk, ativo=True).exists()
            if estava_ativo and Servico.objects.filter(centros_atendimento=self, ativo=True).exists():
                raise ValidationError('Não é possível inativar. Existem Serviços ativos vinculados a este Centro de Atendimento.')


class CategoriaServico(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=80, unique=True, help_text='Informe um nome para a categoria de serviço')
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')

    class Meta:
        ordering = ['nome']
        verbose_name = 'Categoria de Serviço'
        verbose_name_plural = 'Categorias de Serviço'

    def __str__(self):
        return self.nome

    def get_grupos_servicos_com_base_conhecimento(self):
        """Retorna os grupos de servicos ativos que possuem base de conhecimento vinculada"""
        return self.gruposervico_set.filter(
            pk__in=BaseConhecimento.objects.filter(ativo=True, servicos__grupo_servico__categorias=self).values('servicos__grupo_servico')
        ).distinct()

    def get_grupos_servicos_com_base_conhecimento_faq(self):
        """Retorna os grupos de servicos ativos que possuem base de conhecimento vinculada do tipo FAQ"""
        return self.gruposervico_set.filter(
            pk__in=BaseConhecimento.objects.filter(
                visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA, servicos__grupo_servico__categorias=self, servicos__interno=False
            )
            .exclude(servicos__interno=True)
            .values('servicos__grupo_servico')
        ).distinct()


class GrupoServico(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=80, unique=True, help_text='Informe um nome para o grupo de serviço')
    detalhamento = models.CharFieldPlus('Descrição', max_length=600, help_text='Informe detalhes do grupo de serviço')
    categorias = models.ManyToManyFieldPlus(CategoriaServico)
    icone = models.CharFieldPlus(
        'Ícone',
        max_length=80,
        blank=True,
        default='list',
        help_text='Informe um ícone para representar este grupo de Serviços. Fonte: https://fontawesome.com/v4.7.0/icons/',
    )

    class Meta:
        ordering = ['nome']
        verbose_name = 'Grupo de Serviço'
        verbose_name_plural = 'Grupos de Serviço'

    def __str__(self):
        return self.nome

    def get_servicos_ativos_com_base_conhecimento_faq(self):
        """Retorna os servicos ativos que possuem base de conhecimento vinculada do tipo FAQ"""
        return Servico.objects.filter(
            ativo=True,
            id__in=BaseConhecimento.objects.filter(
                visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA, servicos__grupo_servico=self, servicos__interno=False
            ).values('servicos'),
        ).distinct()

    def get_bases_conhecimento_faq(self):
        """Retorna as bases de conhecimento do tipo FAQ"""
        return (
            BaseConhecimento.objects.filter(ativo=True)
            .filter(visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA, servicos__grupo_servico=self, servicos__interno=False)
            .distinct()
        )

    def get_bases_conhecimento(self):
        """Retorna as bases de conhecimento ativas"""
        return BaseConhecimento.objects.filter(ativo=True).filter(servicos__grupo_servico=self).distinct()


class ServicoRequerPatrimonioManager(models.Manager):
    """Serviços que requerem que um patrimônio seja informado como parte dos dados de um chamado."""

    def get_queryset(self):
        return super().get_queryset().filter(requer_numero_patrimonio=True)


class Servico(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'texto_ajuda']

    TIPO_REQUISICAO = 'REQ'
    TIPO_INCIDENTE = 'INC'

    TIPO_CHOICES = [[TIPO_REQUISICAO, 'Requisição'], [TIPO_INCIDENTE, 'Incidente']]

    SLA_MANUAL = 1
    SLA_AUTOMATICO = 2
    SLA_CHOICES = [
        [SLA_MANUAL, 'Usar o SLA manual'],
        [SLA_AUTOMATICO, 'Usar o SLA automático (baseado nas estatísticas do serviço)'],
    ]

    ESTATISTICAS_NUM_MIN_CHAMADOS_FECHADOS = 10
    SLA_MANUAL_PADRAO = 24  # Em horas.

    nome = models.CharFieldPlus('Nome', width=450, max_length=120, unique=True)
    tipo = models.CharFieldPlus('Tipo', max_length=3, choices=TIPO_CHOICES, null=False)
    area = models.ForeignKey('comum.AreaAtuacao', verbose_name='Área do Serviço', on_delete=models.CASCADE)
    centros_atendimento = models.ManyToManyFieldPlus(
        CentroAtendimento,
        verbose_name='Centros de Atendimento',
        related_name='servicos_centros_atendimento_set',
        help_text='Informe pelo menos um centro de atendimento responsável pelo atendimento do chamado.',
    )
    grupo_servico = models.ForeignKeyPlus(GrupoServico, verbose_name='Grupo de Serviço', null=False, on_delete=models.CASCADE)
    texto_ajuda = models.TextField('Informações Adicionais', null=True, blank=True)
    texto_modelo = models.TextField('Informações para preenchimento do chamado', null=True, blank=True)
    permite_anexos = models.BooleanField('Permite anexos?', default=False)
    requer_numero_patrimonio = models.BooleanField('Requer número do patrimônio?', default=False)
    permite_abertura_terceiros = models.BooleanField('Permite abertura de chamado por terceiros?', default=False)
    permite_telefone_adicional = models.BooleanField('Permite interessado informar Telefone Adicional?', default=False)
    sla_manual = models.PositiveIntegerField('SLA manual (em horas)', null=True, blank=True)
    sla_utilizado = models.IntegerField('SLA utilizado', default=SLA_AUTOMATICO, choices=SLA_CHOICES)
    ativo = models.BooleanField('Ativo?', default=True)
    publico_direcionado = models.ManyToManyFieldPlus(
        'comum.Publico',
        verbose_name='Público',
        blank=True,
        related_name='servicos_publico_direcionado_set',
        help_text='Caso deseje restringir este serviço a apenas alguns tipos de usuário, selecione um ou mais.',
    )
    interno = models.BooleanField(
        'Interno?', default=False, help_text='Serviços internos estarão disponíveis apenas para Atendentes da Central de Serviço.'
    )
    solicitar_local_atendimento = models.BooleanField(
        'Deve solicitar local de atendimento?',
        default=False,
        help_text='Informe se o usuário deve informar o local de atendimento na abertura do chamado.',
    )
    nao_exibir_artigos = models.BooleanField('Não exibir artigos da base de conhecimento na abertura de chamado para este serviço.', default=False)

    # Estatísticas do serviço.
    qtd_chamados_fechados = models.PositiveIntegerField(
        'Quantidade de chamados fechados',
        default=0,
        editable=False,
    )
    mediana_tempo_resposta = models.FloatField(
        'Mediana para o tempo de resposta do chamado (em segundos)',
        default=0,
        editable=False,
        help_text='É o tempo mediano para iniciar o atendimento do chamado após abertura/reabertura.',
    )
    mediana_tempo_atendimento = models.FloatField(
        'Mediana para o tempo de atendimento do chamado (em segundos)',
        default=0,
        editable=False,
        help_text='É o tempo mediano para resolver o chamado após iniciar o atendimento.',
    )
    sla_automatico = models.FloatField(
        'SLA automático (em segundos)',
        default=0,
        editable=False,
        help_text='É o tempo mediano para iniciar o atendimento e resolver o chamado.',
    )
    estatisticas_pendentes = models.BooleanField(
        'Estatísticas pendentes de atualização',
        default=True,
        editable=False,
    )

    objects = models.Manager()
    requerem_patrimonio = ServicoRequerPatrimonioManager()

    class Meta:
        ordering = ['grupo_servico', 'tipo', 'nome']
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'

    class ServicoEstatisticas(TypedDict):
        qtd_chamados_fechados: int
        mediana_tempo_resposta: float  # Em segundos.
        mediana_tempo_atendimento: float  # Em segundos.
        sla_automatico: float  # Em segundos.

    # Hints for autocomplete rendering: preload area and grupo_servico used in templates
    EXT_COMBO_RELATED = {
        'select_related': ['area', 'grupo_servico'],
        'prefetch_related': [],
    }

    def __str__(self):
        return f'{self.grupo_servico.nome} | {self.nome}'

    @property
    def sla_em_horas(self):
        if self.sla_utilizado == Servico.SLA_MANUAL or not self.sla_automatico:
            # O sla_manual já está em horas.
            return self.sla_manual or Servico.SLA_MANUAL_PADRAO
        # O sla_automatico, baseado nas estatísticas,
        # está em segundos e deve ser convertido para horas.
        return self.sla_automatico / 3600

    def pode_acessar_servico(self, usuario):
        """Verifica se o usuario tem acesso ao serviço para
        fins de abertura de chamados."""
        if not self.publico_direcionado.exists():
            return True
        else:
            tipo_usuario = usuario.get_relacionamento()
            modelo_usuario = type(usuario.get_relacionamento()).__name__
            vinculo = usuario.get_vinculo()
            for publico in self.publico_direcionado.all():
                if (
                    publico.modelo_base == modelo_usuario
                    and publico.get_queryset().filter(pk=tipo_usuario.pk).exists()
                    or publico.modelo_base == publico.BASE_VINCULO
                    and publico.get_queryset_vinculo().filter(pk=vinculo.pk).exists()
                ):
                    return True
        return False

    @classmethod
    def get_content_types_disponiveis(cls):
        """Retorna os seguintes tipos: Servidor, Aluno e PrestadorServico"""
        return ContentType.objects.filter(app_label__in=['comum', 'edu', 'rh']).filter(model__in=['servidor', 'prestadorservico', 'aluno'])

    def get_quantidade_chamados(self):
        return Chamado.objects.only('servico_id').filter(servico_id=self.id).count()

    def get_quantidade_chamados_abertos(self):
        return (
            Chamado.objects.filter(servico=self).exclude(status__in=[StatusChamado.RESOLVIDO, StatusChamado.FECHADO, StatusChamado.CANCELADO]).count()
        )

    def get_centros_atendimento(self, campus_id):
        return (
            self.centros_atendimento.filter(
                models.Q(eh_local=False, grupoatendimento__ativo=True)
                | models.Q(eh_local=True, grupoatendimento__campus_id=campus_id, grupoatendimento__ativo=True),
                ativo=True,
            )
            .order_by('-eh_local', 'nome')
            .distinct()
        )

    def get_campus_disponiveis_para_atendimento(self):
        """Retorna uma lista de Campus (UO) que estejam disponíveis (possuam Grupos de Atendimento ativos) para o servico"""
        ids = GrupoAtendimento.objects.filter(
            centro_atendimento__in=self.centros_atendimento.all(), ativo=True, centro_atendimento__ativo=True
        ).values_list('campus', flat=True)
        return UnidadeOrganizacional.objects.suap().filter(id__in=ids).order_by('sigla')

    def get_bases_de_conhecimento_disponiveis(self, grupo_atendimento):
        return (
            BaseConhecimento.objects.filter(area=self.area, ativo=True)
            .filter(models.Q(grupos_atendimento__isnull=True) | models.Q(grupos_atendimento__in=[grupo_atendimento]))
            .filter(models.Q(servicos__isnull=True) | models.Q(servicos__in=[self]))
        )

    def get_bases_de_conhecimento_disponiveis_para_resolucao(self, grupo_atendimento):
        return (
            BaseConhecimento.objects.filter(area=self.area, ativo=True, necessita_correcao=False, supervisao_pendente=False)
            .filter(models.Q(grupos_atendimento__isnull=True) | models.Q(grupos_atendimento__in=[grupo_atendimento]))
            .filter(models.Q(servicos__isnull=True) | models.Q(servicos__in=[self]))
        )

    def get_bases_conhecimento_faq(self):
        return (
            BaseConhecimento.objects.filter(ativo=True)
            .filter(
                models.Q(servicos__isnull=True, area=self.area, visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA)
                | models.Q(servicos__in=[self], visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA)
            )
            .distinct()
        )

    def tem_bases_conhecimento_publicas(self):
        return (
            BaseConhecimento.objects.filter(ativo=True)
            .filter(
                models.Q(servicos__isnull=True, area=self.area, visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA)
                | models.Q(servicos__in=[self], visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA)
            )
            .exists()
        )

    def get_unico_centro_atendimento(self):
        if self.centros_atendimento.count() == 1:
            return self.centros_atendimento.first()

    def get_ext_combo_template(self):
        return f'<h3 class="mb-0 pb-0">{self.nome} <small>(Área: {self.area.nome})</small></h3>'

    @staticmethod
    def get_servicos_por_areas(areas: list[AreaAtuacao]):
        return Servico.objects.filter(area__in=areas or []).order_by('nome')

    def get_tarefas_cadastradas(self):
        """tarefas relacionadas ao serviço (cadastro prévio)"""
        return Tarefa.get_tarefas_por_servicos([self])

    def pode_editar_servico(self, user):
        return user.has_perm('centralservicos.change_servico')

    @staticmethod
    def get_attrs_estatisticas() -> list[str]:
        # Sem `estatisticas_pendentes`: a marca é de `_reivindicar_estatisticas` (que a limpa) e de
        # `anular_estatisticas`; gravá-la junto apagaria a marca de um fechamento ocorrido durante o recálculo.
        return [
            'qtd_chamados_fechados',
            'mediana_tempo_resposta',
            'mediana_tempo_atendimento',
            'sla_automatico',
        ]

    @staticmethod
    def _processar_chamados(servico: Servico, bloquear_db_obj: bool) -> list[Chamado.ChamadoEstatisticas]:
        """Atualiza as estatísticas pendentes dos chamados do serviço e retorna as dos chamados fechados."""
        chamados = Chamado.get_chamados_por_servico(servico)
        chamados_salvar: list[Chamado] = []
        chamados_salvar_lote = 1800
        chamados_fechados_estatisticas: list[Chamado.ChamadoEstatisticas] = []

        # Usa iterator para otimizar a utilização da memória.
        for chamado in chamados.iterator(chunk_size=5000):
            chamado_tem_novas_estatisticas = chamado.usar_estatisticas_atualizadas(bloquear_db_obj=bloquear_db_obj, salvar=False)
            chamado_estatisticas = chamado.estatisticas
            if chamado_tem_novas_estatisticas:
                chamados_salvar.append(chamado)
            if chamado.estah_fechado():
                chamados_fechados_estatisticas.append(chamado_estatisticas)
            if len(chamados_salvar) == chamados_salvar_lote:
                Chamado.objects.bulk_update(chamados_salvar, Chamado.get_attrs_estatisticas())
                chamados_salvar.clear()

        if len(chamados_salvar) > 0:
            Chamado.objects.bulk_update(chamados_salvar, Chamado.get_attrs_estatisticas())
        return chamados_fechados_estatisticas

    def atualizar_estatisticas(self, bloquear_db_obj: bool = True, salvar: bool = True) -> None:
        """Calcula e atualiza as estatísticas.
        `bloquear_db_obj`: Permite bloquear ou não o objeto a
        nível de banco de dados para fins de gerenciar atualizações
        concorrentes.
        `salvar`: Permite salvar ou não as estatísticas.
        """

        # As Estatísticas serão calculadas para
        # serviços com 10 ou mais chamados
        # fechados.

        with transaction.atomic():
            if bloquear_db_obj:
                # Bloqueia o serviço com select_for_update
                # para fins de gerenciar atualizações concorrentes.
                servico = Servico.objects.select_for_update().get(pk=self.id)
            else:
                servico = self

            estatisticas: Servico.ServicoEstatisticas = {
                'qtd_chamados_fechados': 0,
                'mediana_tempo_resposta': 0.0,
                'mediana_tempo_atendimento': 0.0,
                'sla_automatico': 0.0,
            }

            chamados_fechados_estatisticas = Servico._processar_chamados(servico, bloquear_db_obj)
            chamados_fechados_qtd = len(chamados_fechados_estatisticas)
            estatisticas['qtd_chamados_fechados'] = chamados_fechados_qtd

            if chamados_fechados_qtd >= Servico.ESTATISTICAS_NUM_MIN_CHAMADOS_FECHADOS:
                df_dados = chamados_fechados_estatisticas
                if df_dados:
                    df = pd.DataFrame(df_dados)
                    estatisticas['mediana_tempo_resposta'] = df['total_tempo_resposta'].median()
                    estatisticas['mediana_tempo_atendimento'] = df['total_tempo_atendimento'].median()
                    estatisticas['sla_automatico'] = df['total_tempo_gasto'].median()

            # Atualiza as estatísticas.
            servico.qtd_chamados_fechados = estatisticas['qtd_chamados_fechados']
            servico.mediana_tempo_resposta = estatisticas['mediana_tempo_resposta']
            servico.mediana_tempo_atendimento = estatisticas['mediana_tempo_atendimento']
            servico.sla_automatico = estatisticas['sla_automatico']
            if bloquear_db_obj:
                # Atualiza as estatísticas da instância atual.
                self.qtd_chamados_fechados = servico.qtd_chamados_fechados
                self.mediana_tempo_resposta = servico.mediana_tempo_resposta
                self.mediana_tempo_atendimento = servico.mediana_tempo_atendimento
                self.sla_automatico = servico.sla_automatico

            # Salva as estatísticas (se for o caso). Não toca em `estatisticas_pendentes` (ver get_attrs_estatisticas).
            if salvar:
                servico.save(update_fields=Servico.get_attrs_estatisticas())

    @property
    def estatisticas(self) -> ServicoEstatisticas:
        """Mais um meio de acessar as estatísticas."""
        return {
            'qtd_chamados_fechados': self.qtd_chamados_fechados,
            'mediana_tempo_resposta': self.mediana_tempo_resposta,
            'mediana_tempo_atendimento': self.mediana_tempo_atendimento,
            'sla_automatico': self.sla_automatico,
        }

    def anular_estatisticas(self) -> None:
        """Seta as estatísticas como pendentes; `recalcular_estatisticas_pendentes` as recalcula."""
        # Só grava se ainda não estiver pendente. A trava do recálculo é curta (só a reivindicação, que limpa a marca);
        # o recálculo roda sem trava, então um fechamento durante ele remarca o serviço.
        Servico.objects.filter(pk=self.pk, estatisticas_pendentes=False).update(estatisticas_pendentes=True)
        self.estatisticas_pendentes = True

    @staticmethod
    def _reivindicar_estatisticas(servico_id: int) -> Servico | None:
        """Limpa a marca de pendente numa transação curta e devolve o serviço; None se não estiver pendente
        ou se outra execução (ou requisição) estiver com ele travado."""
        with transaction.atomic():
            # order_by('pk'): o ordering padrão faz JOIN com grupo_servico, que o FOR UPDATE também travaria.
            servico = Servico.objects.select_for_update(skip_locked=True).filter(pk=servico_id, estatisticas_pendentes=True).order_by('pk').first()
            if servico:
                Servico.objects.filter(pk=servico_id).update(estatisticas_pendentes=False)
        return servico

    @staticmethod
    def recalcular_estatisticas_pendentes(servico_id: int) -> bool:
        """Reivindica o serviço pendente e recalcula as estatísticas sem trava; um fechamento durante o
        recálculo volta a marcá-lo. Retorna False se não conseguiu reivindicar. Se o recálculo falhar,
        devolve a marca e repassa a exceção."""
        servico = Servico._reivindicar_estatisticas(servico_id)
        if not servico:
            return False
        try:
            servico.atualizar_estatisticas(bloquear_db_obj=False)
        except Exception:
            Servico.objects.filter(pk=servico_id).update(estatisticas_pendentes=True)
            raise
        return True

    @staticmethod
    def get_servicos(
        apenas_ativos=False,
        apenas_com_centro_atendimento_ativo=False,
        apenas_com_grupo_atendimento_ativo=False,
        apenas_sem_centro_atendimento_ativo=False,
        apenas_sem_grupo_atendimento_ativo=False,
        area_atuacao: AreaAtuacao = None,
        publico_direcionado: models.QuerySet[User] = None,
    ):
        """
        Serviço
            ativo
            interno
            area (AreaAtuacao)
                ativo
            grupo_servico (GrupoServico)
                N categorias (CategoriaServico)
                    area (AreaAtuacao)
            centros_atendimento (CentroAtendimento)
                ativo
                area (AreaAtuacao)
                grupoatendimento_set (GrupoAtendimento)
                    ativo
                    campus
                    responsaveis
                    atendentes
        """

        servicos = Servico.objects.select_related(
            'area',
            'grupo_servico',
        )

        if apenas_com_centro_atendimento_ativo or apenas_sem_centro_atendimento_ativo:
            centros_atendimento_ativos = CentroAtendimento.objects.prefetch_related(
                'servicos_centros_atendimento_set',
            ).filter(
                ativo=True,
                servicos_centros_atendimento_set=models.OuterRef('pk'),
            )
            servicos = servicos.annotate(tem_centro_atendimento_ativo=models.Exists(centros_atendimento_ativos))

        if apenas_com_grupo_atendimento_ativo or apenas_sem_grupo_atendimento_ativo:
            grupos_atendimento_ativos = (
                GrupoAtendimento.objects.select_related(
                    'centro_atendimento',
                )
                .prefetch_related(
                    'centro_atendimento__servicos_centros_atendimento_set',
                )
                .filter(
                    ativo=True,
                    centro_atendimento__ativo=True,
                    centro_atendimento__servicos_centros_atendimento_set=models.OuterRef('pk'),
                )
            )
            servicos = servicos.annotate(tem_grupo_atendimento_ativo=models.Exists(grupos_atendimento_ativos))

        if apenas_ativos:
            servicos = servicos.filter(ativo=True)

        if apenas_com_centro_atendimento_ativo:
            servicos = servicos.filter(tem_centro_atendimento_ativo=True)

        if apenas_com_grupo_atendimento_ativo:
            servicos = servicos.filter(tem_grupo_atendimento_ativo=True)

        if apenas_sem_centro_atendimento_ativo:
            servicos = servicos.filter(tem_centro_atendimento_ativo=False)

        if apenas_sem_grupo_atendimento_ativo:
            servicos = servicos.filter(tem_grupo_atendimento_ativo=False)

        if area_atuacao:
            # Filtra pelo atributo 'area' do caminho
            # Serviço -> Grupo de Serviço -> Categoria de Serviço
            servicos = servicos.prefetch_related(
                'grupo_servico__categorias__area',
            ).filter(grupo_servico__categorias__area=area_atuacao)

        if publico_direcionado is not None:
            servicos = servicos.prefetch_related(
                'publico_direcionado',
            ).filter(Q(publico_direcionado__in=publico_direcionado) | Q(publico_direcionado__isnull=True))

        return servicos.distinct()

    @staticmethod
    def get_servicos_ativos_sem_centro_atendimento_ativo():
        return Servico.get_servicos(apenas_ativos=True, apenas_sem_centro_atendimento_ativo=True)

    @staticmethod
    def get_servicos_ativos_sem_grupo_atendimento_ativo():
        return Servico.get_servicos(apenas_ativos=True, apenas_sem_grupo_atendimento_ativo=True)

    def tem_grupo_atendimento_ativo(self):
        servicos_ativos_com_grupo_atendimento_ativo = Servico.get_servicos(apenas_ativos=True, apenas_com_grupo_atendimento_ativo=True)
        return servicos_ativos_com_grupo_atendimento_ativo.filter(pk=self.id).exists()

    @staticmethod
    def get_servicos_ao_usuario(user: User, area: AreaAtuacao = None):
        """Lista dos serviços que o usuário tem acesso na
        perspectiva de utilizador da central de serviços."""

        servicos = Servico.get_servicos(
            apenas_ativos=True,
            apenas_com_grupo_atendimento_ativo=True,
            area_atuacao=area,
            publico_direcionado=Publico.get_meus_publicos(user),
        )

        # Trata os serviços internos.
        # Serviços internos estarão disponíveis apenas para Atendentes da Central de Serviço.
        meus_grupos_atendimento = GrupoAtendimento.meus_grupos(user, area).filter(ativo=True).distinct()
        if user.has_perm('centralservicos.change_chamado') and meus_grupos_atendimento.exists():
            areas_ids = meus_grupos_atendimento.values_list('centro_atendimento__area__id', flat=True)
            servicos_meus_grupos_atendimento = servicos.filter(
                area__pk__in=areas_ids,
            )
            servicos_outros_grupos_atendimento = servicos.exclude(
                area__pk__in=areas_ids,
            )
            servicos = servicos_meus_grupos_atendimento | servicos_outros_grupos_atendimento.filter(
                # Os serviços internos de outras áreas são omitidos.
                interno=False,
            )
        else:
            # Os serviços internos são omitidos.
            servicos = servicos.filter(interno=False)

        return servicos

    @staticmethod
    def get_servicos_ao_atendente(user: User):
        """Lista dos serviços que o usuário tem acesso na
        perspectiva de atendente ou gestor da central de serviços."""

        servicos = Servico.get_servicos()

        if user.has_group_cached('Atendente da Central de Serviços') and not user.has_group_cached('Gestor da Central de Serviços'):
            areas_ids = GrupoAtendimento.areas_vinculadas_ao_meu_centro_atendimento(user).only('id').values_list('id', flat=True)
        else:
            areas_ids = GestorAreaServico.minhas_areas(user).only('id').values_list('id', flat=True)

        return servicos.filter(grupo_servico__categorias__area__id__in=areas_ids).distinct()


class GrupoAtendimento(models.ModelPlus):
    grupo_atendimento_superior = models.ForeignKeyPlus(
        'centralservicos.GrupoAtendimento', verbose_name='Grupo de Atendimento Superior', null=True, blank=True, on_delete=models.CASCADE
    )
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus')
    centro_atendimento = models.ForeignKeyPlus(CentroAtendimento, verbose_name='Centro de Atendimento', null=False, blank=False)
    nome = models.CharFieldPlus('Nome', max_length=120)
    responsaveis = models.ManyToManyFieldPlus(
        User,
        verbose_name='Responsáveis',
        related_name='responsaveis_set',
        help_text='O responsável pelo grupo de atendimento deve ser um dos atendentes.',
    )
    atendentes = models.ManyToManyFieldPlus(User, related_name='atendentes_set', blank=True, verbose_name='Atendentes Vinculados ao Grupo')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Grupo de Atendimento'
        verbose_name_plural = 'Grupos de Atendimento'

    def __str__(self):
        return f'{self.nome} ({self.centro_atendimento})'

    def clean(self):
        # Não pode existir mais de um grupo de atendimento, no mesmo nível, na mesma UO,
        # no mesmo centro de atendimento
        if not hasattr(self, 'centro_atendimento'):
            raise ValidationError('Nenhum centro de atendimento encontrado.')
        if not hasattr(self, 'campus'):
            raise ValidationError('Nenhum campus encontrado.')
        if (
            GrupoAtendimento.objects.filter(
                grupo_atendimento_superior=self.grupo_atendimento_superior, campus=self.campus, centro_atendimento=self.centro_atendimento
            )
            .exclude(pk=self.id)
            .exists()
        ):
            raise ValidationError('Não pode existir mais de um grupo de atendimento, no mesmo nível, na mesma UO, no mesmo centro de atendimento.')

        if self.pk and not self.ativo:
            estava_ativo = GrupoAtendimento.objects.filter(pk=self.pk, ativo=True).exists()
            if estava_ativo and Servico.objects.filter(centros_atendimento=self.centro_atendimento, ativo=True).exists():
                raise ValidationError(
                    'Não é possível inativar. Existem Serviços ativos vinculados ao Centro de Atendimento deste Grupo de Atendimento.'
                )

    @classmethod
    def get_grupo_primeiro_nivel(cls, uo, centro):
        """Retorna o grupo de primeiro nível
        Para isto, verifica se o centro de atendimento eh_local = True
        Em caso positivo, retorna o grupo de primeiro nivel do campus informado,
        em caso negativo, retorna o grupo de primeiro nivel sem considerar o campus
            (considerando apenas o centro de atendimento)
        """
        queryset = GrupoAtendimento.objects.filter(centro_atendimento=centro, atendentes__isnull=False, ativo=True)
        if centro.eh_local:
            queryset = (
                queryset.filter(campus=uo)
                .annotate(
                    eh_superior_de_outro_grupo_da_mesma_uo=Exists(
                        GrupoAtendimento.objects.filter(grupo_atendimento_superior=OuterRef('pk'), atendentes__isnull=False, campus=uo, ativo=True)
                    )
                )
                .filter(eh_superior_de_outro_grupo_da_mesma_uo=False)
            )
        else:
            grupos = queryset.filter(grupo_atendimento_superior__isnull=False)
            gs_keys = grupos.values_list('grupo_atendimento_superior__id', flat=True)
            queryset = queryset.exclude(pk__in=gs_keys)

        return queryset.first()

    def email_responsaveis(self):
        """Retorna a lista de emails separada por virgula dos responsáveis"""
        return self.responsaveis.exclude(email='').values_list('email', flat=True)

    def pode_editar(self, user):
        return bool(GestorAreaServico.objects.filter(gestor=user, area=self.centro_atendimento.area).exists() or user in self.responsaveis.all())

    def get_vinculos_responsaveis(self):
        responsaveis = []
        if self.responsaveis.exists():
            for responsavel in self.responsaveis.all():
                responsaveis.append(responsavel.get_vinculo())
        return responsaveis

    def pertence_ao_grupo(self, user):
        return GrupoAtendimento.meus_grupos(user).filter(id=self.id).exists()

    def eh_primeiro_nivel(self):
        """Informa se o grupo é de primeiro nível"""
        grupo = GrupoAtendimento.get_grupo_primeiro_nivel(self.campus, self.centro_atendimento)
        return bool(grupo and grupo.id == self.pk)

    def get_grupo_antendimento_inferior(self, chamado):
        """Retorna o grupo de atendimento inferior. Se tiver mais de um,
        irá verificar com base no chamado (quem escalou).
        """
        grupo = None
        nivel_anterior = GrupoAtendimento.objects.filter(grupo_atendimento_superior=self)
        if nivel_anterior.count() == 1:  # Se só existe um grupo de atendimento no nivel inferior, atribui ele
            grupo = nivel_anterior[0]
        elif nivel_anterior.count() > 1:  # Se existe mais de um, obtem o ultimo (inferior) que foi atribuido
            atendimento_atribuicoes = chamado.atendimentoatribuicao_set.filter(grupo_atendimento__in=nivel_anterior).order_by('-atribuido_em')
            if atendimento_atribuicoes.count() >= 1:
                grupo = atendimento_atribuicoes[0].grupo_atendimento
        return grupo

    def atendentes_disponiveis(self, user=None):
        """
        Método responsável por validar se servidores (atendentes) do grupo de atendimento estão disponíveis
        ou afastados por algum motivo.
        """
        if user:
            atendentes = self.atendentes.exclude(id__in=[user.id])
        else:
            atendentes = self.atendentes.all()

        usuarios = []
        hoje = datetime.today()
        if atendentes.exists():
            for atendente in atendentes:
                vinculo = atendente.get_vinculo()
                if vinculo.eh_servidor():
                    afastamento_ou_ferias = vinculo.relacionamento.estah_afastado_ou_de_ferias_ateh(hoje)
                    if not afastamento_ou_ferias:
                        usuarios.append(atendente.id)
                else:
                    usuarios.append(atendente.id)
        return User.objects.filter(id__in=usuarios)

    @classmethod
    def meus_grupos(cls, user, area=None):
        """Retorna uma lista de Grupos que o Usuário é Atendente ou Responsável
        Se informar a área, executa o filtro por area
        """
        qs = cls.objects.filter(models.Q(atendentes=user) | models.Q(responsaveis=user)).distinct()

        if area:
            qs = qs.filter(models.Q(centro_atendimento__area__in=area) if isinstance(area, Iterable) else models.Q(centro_atendimento__area=area))

        return qs

    @classmethod
    def meus_grupos_com_servicos_ou_chamados_ativos(cls, user, area=None):
        """Retorna uma lista de Grupos que o Usuário é Atendente ou Responsável
        Se informar a área, executa o filtro por area
        """
        qs = cls.meus_grupos(user, area).filter(
            models.Q(centro_atendimento__servicos_centros_atendimento_set__ativo=True)
            | models.Q(
                id__in=AtendimentoAtribuicao.objects.filter(chamado_id__in=Chamado.ativos.all().values_list('id', flat=True)).values_list(
                    'grupo_atendimento_id', flat=True
                )
            )
        )

        return qs

    @classmethod
    def areas_vinculadas_ao_meu_centro_atendimento(cls, user):
        from comum.models import AreaAtuacao

        if user.is_superuser or user.groups.filter(name='centralservicos Administrador').exists():
            return AreaAtuacao.objects.all()
        else:
            return AreaAtuacao.objects.filter(id__in=cls.meus_grupos(user).values('centro_atendimento__area'))

    @classmethod
    def get_grupos_por_responsavel(cls, user):
        """Retorna uma lista de Grupos que o Usuário é Responsável
        Se o usuário for superuser, retorna todos os grupos
        """
        if user.is_superuser:
            return cls.objects.all()
        else:
            return cls.objects.filter(models.Q(responsaveis=user))

    @classmethod
    def raiz(cls):
        try:
            return cls.objects.get(grupo_atendimento_superior__isnull=True)
        except cls.MultipleObjectsReturned:
            raise Exception('Existe mais de um Grupo de Atendimento raiz.')
        except cls.DoesNotExist:
            return None


def _sincronizar_grupo_atendente(related_name):
    """
    Função auxiliar para sincronizar o grupo 'Atendente da Central de Serviços'
    com usuários vinculados ao GrupoAtendimento através do related_name especificado.
    """
    group = Group.objects.get(name='Atendente da Central de Serviços')

    # Adiciona o grupo a usuários vinculados que ainda não possuem a permissão
    usuarios_sem_permissao = User.objects.filter(**{f'{related_name}__isnull': False}).exclude(groups=group)
    for user in usuarios_sem_permissao:
        user.groups.add(group)

    # Remove o grupo de usuários que não estão mais vinculados
    # Mantém o grupo se o usuário for atendente OU responsável
    usuarios_com_permissao = User.objects.filter(atendentes_set__isnull=True, responsaveis_set__isnull=True, groups=group)
    for user in usuarios_com_permissao:
        user.groups.remove(group)


def altera_permissao_apos_salvar_atendentes(sender, **kwargs):
    """Sincroniza permissões ao alterar atendentes de um GrupoAtendimento."""
    _sincronizar_grupo_atendente('atendentes_set')


def altera_permissao_apos_salvar_responsaveis(sender, **kwargs):
    """Sincroniza permissões ao alterar responsáveis de um GrupoAtendimento."""
    _sincronizar_grupo_atendente('responsaveis_set')


m2m_changed.connect(altera_permissao_apos_salvar_atendentes, sender=GrupoAtendimento.atendentes.through)
m2m_changed.connect(altera_permissao_apos_salvar_responsaveis, sender=GrupoAtendimento.responsaveis.through)


class BaseConhecimento(models.ModelPlus):
    SEARCH_FIELDS = ['titulo', 'resumo', 'solucao']

    NAO = False
    SIM = True
    SIM_NAO_CHOICES = ((NAO, 'Não'), (SIM, 'Sim'))

    VISIBILIDADE_PUBLICA = 'publica'
    VISIBILIDADE_PRIVADA = 'privada'
    VISIBILIDADE_SIGILOSA = 'sigilosa'

    VISIBILIDADE_CHOICES_TODAS = ((VISIBILIDADE_PUBLICA, 'Pública'), (VISIBILIDADE_PRIVADA, 'Privada'), (VISIBILIDADE_SIGILOSA, 'Sigilosa'))

    VISIBILIDADE_CHOICES_PRIVADA_OU_SIGILOSA = ((VISIBILIDADE_PRIVADA, 'Privada'), (VISIBILIDADE_SIGILOSA, 'Sigilosa'))

    titulo = models.CharFieldPlus('Título', max_length=120, null=False, blank=False)
    resumo = models.TextField('Resumo', null=False, blank=False)
    solucao = models.TextField('Solução', null=True, blank=True)
    tags = models.CharFieldPlus(
        'Tags',
        max_length=80,
        help_text='Separe cada tag com uma vírgula e espaço. Ex.: Ensino, Tecnologia da Informação, Extensão, Internet',
        null=True,
        blank=True,
    )
    atualizado_em = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    grupos_atendimento = models.ManyToManyFieldPlus(
        GrupoAtendimento,
        blank=True,
        verbose_name='Restringir aos Grupos de Atendimento',
        help_text='Não selecione nenhuma opção para exibir esta base de conhecimento em todos os grupos de atendimento.',
    )
    servicos = models.ManyToManyFieldPlus(
        Servico,
        blank=True,
        verbose_name='Restringir aos Serviços',
        help_text='Não selecione nenhuma opção para exibir esta base de conhecimento em todos os serviços.',
        related_name='base_conhecimento_servicos_set',
    )
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')
    necessita_correcao = models.BooleanField(
        'Necessita correção?',
        null=True,
        blank=True,
        default=NAO,
        choices=SIM_NAO_CHOICES,
        help_text='Marque esta opção caso esta base de conhecimento necessite de alguma correção.',
    )
    supervisao_pendente = models.BooleanField(
        'Supervisão pendente?',
        null=True,
        blank=True,
        default=False,
        choices=SIM_NAO_CHOICES,
        help_text='Marque esta opção caso esta base de conhecimento necessite de aprovação por algum supervisor.',
    )
    atualizado_por = models.ForeignKeyPlus(User, related_name='atualizado_por_set', verbose_name='Atualizado Por', null=True)
    visibilidade = models.CharFieldPlus(
        max_length=10,
        default=VISIBILIDADE_PRIVADA,
        choices=VISIBILIDADE_CHOICES_TODAS,
        null=True,
        help_text='<strong>Sigilosa:</strong> restringe os artigos apenas a determinados Grupos de Atendimento;<br /><strong>Privada:</strong> artigos visíveis a todos os atendentes da Central de Serviços;<br /> <strong>Pública:</strong> artigos visíveis a todos os atendentes da Central de Serviços e na área de Perguntas Frequentes.',
    )
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        ordering = ['titulo']
        verbose_name = 'Base de Conhecimento'
        verbose_name_plural = 'Bases de Conhecimento'
        permissions = (
            ('add_active_baseconhecimento', 'Pode adicionar uma base de conhecimento sem necessitar supervisão'),
            ('add_public_baseconhecimento', 'Pode adicionar uma base de conhecimento pública'),
            ('review_baseconhecimento', 'Pode revisar bases de conhecimento'),
            ('pode_unificar_baseconhecimento', 'Pode unificar bases de conhecimento'),
        )

    def __str__(self):
        return self.titulo

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def get_absolute_url(self):
        return f'/centralservicos/baseconhecimento/{self.id}/'

    def get_tags(self):
        tags = []
        if self.tags:
            tags = self.tags.split(', ')
        return tags

    def get_visualizar_base_conhecimento_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    def get_ext_combo_template(self):
        resumo = ''
        tags = ''
        if self.tags:
            tags = f'<p>Tags: {self.tags!s}</p>'
        if self.resumo:
            resumo = f'<p class="disabled">{self.resumo!s}</p>'

        return f"""<h3>{self.titulo}</h3> {tags} {resumo}"""

    def save(self, *args, **kwargs):
        """
        Ao incluir/alterar base de conhecimento, atualiza o campo 'atualizado_em' e 'atualizado_por', caso tenha alterado os camos resumo ou solução.
        """

        if self.atualizado_por and not self.atualizado_por.has_perm('centralservicos.add_active_baseconhecimento'):
            self.supervisao_pendente = True
        retorno = super().save(*args, **kwargs)
        self.__original_resumo = self.resumo
        self.__original_solucao = self.solucao
        if self.supervisao_pendente:
            """ Enviar email apenas a atendentes/responsaveis da area que sejam do grupo Supervisor """
            group = Group.objects.get(name='Supervisor da Base de Conhecimento')
            usuarios = []
            supervisores = group.user_set.all()
            usuarios.extend(list(supervisores))

            atendentes = User.objects.filter(atendentes_set__grupoatendimento__centro_atendimento__area=self.area).distinct()
            usuarios.extend(list(atendentes))

            Notificar.supervisao_pendente_em_base_conhecimento(self, usuarios)
        return retorno

    def estah_disponivel_para_uso(self):
        return not self.necessita_correcao and not self.supervisao_pendente

    def get_media_avaliacoes(self):
        return (
            AvaliaBaseConhecimento.objects.filter(
                base_conhecimento=self, pergunta__ativo=True, pergunta__area=self.area, data__gte=self.atualizado_em
            ).aggregate(Avg('nota'))['nota__avg']
            or 0.0
        )

    @property
    def get_quantidade_utilizacoes(self):
        return HistoricoStatus.objects.filter(status=StatusChamado.get_status_resolvido(), bases_conhecimento__in=[self]).distinct().count()

    @property
    def get_quantidade_avaliacoes(self):
        return AvaliaBaseConhecimento.objects.filter(
            base_conhecimento=self, pergunta__ativo=True, pergunta__area=self.area, data__gte=self.atualizado_em
        ).count()

    @transaction.atomic()
    def marcar_para_correcao(self, texto, user):
        baseconhecimento_content = ContentType.objects.get(app_label='centralservicos', model='baseconhecimento')
        comentario = Comentario()
        comentario.cadastrado_por = user
        comentario.texto = texto
        comentario.content_type = baseconhecimento_content
        comentario.content_object = self
        comentario.object_id = self.pk
        comentario.save()

        BaseConhecimento.objects.filter(id=self.pk).update(necessita_correcao=True)
        if self.atualizado_por:
            Notificar.base_conhecimento_marcada_para_revisao(self, comentario, user)

    def pode_editar_area(self, user):
        # trata o problema relatato no Erro 8898 (https://suap.ifrn.edu.br/erros/erro/8898/)
        # usuário administrador da central de serviços poderá editar a área da base de conhecimento
        return user.groups.filter(name='centralservicos Administrador').exists()


class BaseConhecimentoAnexo(models.ModelPlus):
    base_conhecimento = models.ForeignKeyPlus(BaseConhecimento, verbose_name='Base de Conhecimento', null=False, blank=False)
    anexo = models.FileFieldPlus(
        upload_to='upload/baseconhecimento/anexos/',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv', 'docx', 'doc', 'pdf', 'jpg', 'jpeg', 'png', 'zip', 'txt'])],
        null=False,
        blank=False,
        max_file_size=10485760,
        can_view='can_view_anexo',
    )

    def nome_arquivo(self):
        return os.path.basename(self.anexo.name)

    def can_view_anexo(self, user):
        return user.is_authenticated

    def __str__(self):
        return self.base_conhecimento.titulo

    class Meta:
        ordering = ['anexo']
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'


class PerguntaAvaliacaoBaseConhecimento(models.ModelPlus):
    area = models.ForeignKeyPlus('comum.AreaAtuacao', verbose_name='Área do Serviço')
    titulo = models.CharFieldPlus('Título', max_length=120, help_text='A resposta à pergunta será uma escala de 1 a 5.')
    ativo = models.BooleanField('Ativo?', default=False)

    class Meta:
        ordering = ['area', 'titulo']
        verbose_name = 'Pergunta da Avaliação da Base de Conhecimento'
        verbose_name_plural = 'Perguntas da Avaliação da Base de Conhecimento'

    def __str__(self):
        return f'{self.titulo} ({self.area.nome})'


class AvaliaBaseConhecimento(models.ModelPlus):
    base_conhecimento = models.ForeignKeyPlus(BaseConhecimento, verbose_name='Base de Conhecimento')
    pergunta = models.ForeignKeyPlus(PerguntaAvaliacaoBaseConhecimento, verbose_name='Pergunta', null=True)
    nota = models.PositiveSmallIntegerField('Nota da Avaliação', choices=AVALIACAO_CHOICES)
    data = models.DateTimeField(verbose_name='Data da Avaliação', auto_now=True)
    avaliado_por = models.ForeignKeyPlus(User, related_name='avaliado_por_set', verbose_name='Avaliado Por')

    class Meta:
        unique_together = ('base_conhecimento', 'pergunta', 'avaliado_por')
        ordering = ['base_conhecimento']
        verbose_name = 'Avaliação da Base de Conhecimento'
        verbose_name_plural = 'Avaliações das Bases de Conhecimento'

    def __str__(self):
        return self.base_conhecimento.titulo

    @classmethod
    def get_media_avaliacao(cls, base_conhecimento, pergunta):
        return cls.objects.filter(base_conhecimento=base_conhecimento, pergunta=pergunta).aggregate(Avg('nota'))['nota__avg']


class StatusChamado:
    ABERTO = 1
    EM_ATENDIMENTO = 2
    RESOLVIDO = 3
    FECHADO = 4
    REABERTO = 5
    SUSPENSO = 6
    CANCELADO = 7

    STATUS = Choices(
        (ABERTO, 'aberto', 'Aberto'),
        (EM_ATENDIMENTO, 'atendimento', 'Em atendimento'),
        (RESOLVIDO, 'resolvido', 'Resolvido'),
        (FECHADO, 'fechado', 'Fechado'),
        (REABERTO, 'reaberto', 'Reaberto'),
        (SUSPENSO, 'suspenso', 'Suspenso'),
        (CANCELADO, 'cancelado', 'Cancelado'),
    )

    @classmethod
    def get_action_from_status(cls, argument):
        status_name = StatusChamado.STATUS[argument]
        switcher = {
            'Aberto': 'abrir',
            'Resolvido': 'resolver',
            'Fechado': 'fechar',
            'Suspenso': 'suspender',
            'Cancelado': 'cancelar',
            'Reaberto': 'Reaberto',
        }
        # Get the correct state from switcher dictionary
        return switcher.get(status_name, status_name)

    @classmethod
    def get_status_aberto(cls):
        return StatusChamado.ABERTO

    @classmethod
    def get_status_em_atendimento(cls):
        return StatusChamado.EM_ATENDIMENTO

    @classmethod
    def get_status_resolvido(cls):
        return StatusChamado.RESOLVIDO

    @classmethod
    def get_status_fechado(cls):
        return StatusChamado.FECHADO

    @classmethod
    def get_status_reaberto(cls):
        return StatusChamado.REABERTO

    @classmethod
    def get_status_suspenso(cls):
        return StatusChamado.SUSPENSO

    @classmethod
    def get_status_cancelado(cls):
        return StatusChamado.CANCELADO


class ChamadosAtivosManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .exclude(status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado()))
        )


class ChamadosSLAEstouradoManager(models.Manager):
    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .filter(data_limite_atendimento__lt=datetime.now())
            .exclude(status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado()))
        )


class Chamado(models.ModelPlus):
    MEIO_ABERTURA_TELEFONE = 'telefone'
    MEIO_ABERTURA_EMAIL = 'email'
    MEIO_ABERTURA_PESSOALMENTE = 'pessoalmente'
    MEIO_ABERTURA_WEB = 'web'

    MEIO_ABERTURA_CHOICES = (
        (MEIO_ABERTURA_WEB, 'Interface Web'),
        (MEIO_ABERTURA_TELEFONE, 'Telefone'),
        (MEIO_ABERTURA_EMAIL, 'Email'),
        (MEIO_ABERTURA_PESSOALMENTE, 'Pessoalmente'),
    )

    status = FSMIntegerField(default=StatusChamado.STATUS.aberto, choices=StatusChamado.STATUS, protected=True)
    servico = models.ForeignKeyPlus(Servico, verbose_name='Serviço', null=False, blank=False)
    descricao = models.TextField('Descrição', null=False, blank=False, help_text='Descreva a sua solicitação')
    aberto_em = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    aberto_por = models.ForeignKeyPlus(User, related_name='aberto_por_set', verbose_name='Aberto Por', null=False, blank=False)
    requisitante = models.ForeignKeyPlus(
        User,
        related_name='requisitante_set',
        verbose_name='Requisitante',
        null=False,
        blank=False,
        help_text='Informe o nome de quem está requisitando a abertura do chamado.',
    )
    telefone_adicional = models.BrTelefoneField(
        'Telefone Adicional para Contato',
        blank=True,
        max_length=15,
        help_text='Para agilizar o atendimento, informe um número adicional para contato.',
    )
    interessado = models.ForeignKeyPlus(
        User,
        related_name='interessado_set',
        verbose_name='Interessado',
        null=False,
        blank=False,
        help_text='Caso esteja abrindo o chamado para outra pessoa, informe o nome do interessado.',
    )
    uo_interessado = models.ForeignKeyPlus(
        UnidadeOrganizacional, related_name='uo_interessado_set', verbose_name='Unidade Organizacional do Interessado', null=True
    )
    meio_abertura = models.CharFieldPlus('Meio de Abertura', max_length=20, choices=MEIO_ABERTURA_CHOICES, null=False, blank=False)

    # O atributo 'numero_patrimonio' foi DEPRECIADO na Demanda 1641, mas permanecerá mantendo os dados originais
    # até que haja necessidade de removê-lo. Há o comando "centralservicos_inicializar_patrimonio" usado para
    # inicializar o novo atributo 'patrimonio' a partir dos dados existentes em 'numero_patrimonio'. Este comando
    # funcionará enquanto o atributo 'numero_patrimonio' existir.
    numero_patrimonio = models.CharFieldPlus('Número do Patrimônio', max_length=20, null=True, blank=True)
    patrimonio = models.ForeignKeyPlus(Inventario, verbose_name='Patrimônio', null=True, blank=True)

    autorizado = models.BooleanField('Autorizado?', null=True, blank=True)
    data_limite_atendimento = models.DateTimeField('Data Limite para atendimento do chamado', null=False, blank=False)
    notificacao_enviada = models.BooleanField('Notificação Enviada?', default=False)
    nota_avaliacao = models.PositiveSmallIntegerField('Nota da Avaliação', choices=AVALIACAO_CHOICES, null=True, blank=True)
    comentario_avaliacao = models.TextField('Comentário da Avaliação', null=False, blank=True)
    data_avaliacao = models.DateTimeField(verbose_name='Data da Avaliação', null=True)
    reclassificado = models.PositiveSmallIntegerField(
        'Chamado Reclassificado', null=True, help_text='Número de vezes que o chamado foi reclassificado.'
    )
    outros_interessados = models.ManyToManyFieldPlus(
        User,
        related_name='outros_interessados_set',
        verbose_name='Outros Interessados',
        help_text='Vincule neste chamado outros usuários que desejem acompanhar alterações e comentários deste chamado.',
    )
    fechado_automaticamente = models.BooleanField('Fechado Automaticamente?', null=True, blank=True)
    tags = models.ManyToManyFieldPlus(
        Tag, related_name='tags_set', verbose_name='Tags', help_text='Vincule tags neste chamados para facilitar a identificação do mesmo.'
    )
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True)
    local_atendimento = models.CharFieldPlus('Sala/local de atendimento', max_length=80, null=True, blank=True)
    sla_estourado = models.BooleanField(default=False)

    # Estatísticas do chamado.
    total_tempo_resposta = models.FloatField(
        'Total de tempo de resposta do chamado (em segundos)',
        default=0,
        editable=False,
        help_text="""É o somatório dos tempos entre as
        situações Aberto/Reaberto e Em Atendimento (em segundos).""",
    )
    total_tempo_atendimento = models.FloatField(
        'Total de tempo de atendimento do chamado (em segundos)',
        default=0,
        editable=False,
        help_text="""É o somatório dos tempos entre as
        situações Em Atendimento e Resolvido (em segundos). O tempo entre
        as situações Em Atendimento e Suspenso não é considerado tempo de
        atendimento. O tempo entre as situações Resolvido e Fechado também
        não é considerado tempo de atendimento.""",
    )
    total_tempo_suspensao = models.FloatField(
        'Total de tempo de suspensão do chamado (em segundos)',
        default=0,
        editable=False,
        help_text="""É o somatório dos tempos entre as situações
        Suspenso e Em Atendimento (em segundos).""",
    )
    total_tempo_gasto = models.FloatField(
        'Total de tempo de gasto do chamado (em segundos)',
        default=0,
        editable=False,
        help_text="""É o soma dos totais dos tempos de resposta e
        atendimento (em segundos).""",
    )
    estatisticas_pendentes = models.BooleanField(
        'Estatísticas pendentes de atualização',
        default=True,
        editable=False,
    )

    objects = models.Manager()
    ativos = ChamadosAtivosManager()
    com_sla_estourado = ChamadosSLAEstouradoManager()

    def __str__(self):
        return f'Chamado {self.pk}: {self.servico.nome}'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.centro_atendimento = None

    class Meta:
        ordering = ['-aberto_em']
        verbose_name = 'Chamado'
        verbose_name_plural = 'Chamados'
        permissions = (
            # Permissões relativas a atribuição de chamado
            ('add_atendimentoatribuicao', 'Pode atribuir um chamado'),
            ('add_auto_atribuicao', 'Pode assumir um chamado'),
            ('change_atendimentoatribuicao', 'Pode alterar atribuição de um chamado'),
            ('reclassify_chamado', 'Pode reclassificar um chamado'),
            # Permissões que alterar o status do chamado
            ('solve_chamado', 'Pode resolver um chamado'),
            ('close_chamado', 'Pode fechar um chamado'),
            ('reopen_chamado', 'Pode reabrir um chamado'),
            ('suspend_chamado', 'Pode suspender um chamado'),
            ('cancel_chamado', 'Pode cancelar um chamado'),
            # Permissões para anexos
            ('add_attachement', 'Pode adicionar anexo'),
            ('add_comment', 'Pode adicionar comentário'),
            ('add_internal_note', 'Pode adicionar nota interna'),
            ('add_interested', 'Pode adicionar interessado'),
            ('remove_interested', 'Pode remover interessado'),
            ('list_chamados_usuario', 'Pode listar chamados do usuário'),
            ('list_chamados_suporte', 'Pode listar chamados do suporte'),
            ('pode_ver_indicadores', 'Pode ver indicadores'),
        )

    class ChamadoEstatisticas(TypedDict):
        total_tempo_resposta: float  # Em segundos.
        total_tempo_atendimento: float  # Em segundos.
        total_tempo_suspensao: float  # Em segundos.
        total_tempo_gasto: float  # Em segundos.

    @staticmethod
    def chamados_por_status_e_atores(
        status: int | None = None,
        requisitante_id: int | None = None,
        interessado_id: int | None = None,
        responsavel_atendimento_atual_id: int | None = None,
        atendente_atribuido_atual_id: int | None = None,
    ):
        qs = Chamado.objects.select_related(
            'requisitante',
            'interessado',
        )

        if status:
            qs = qs.filter(models.Q(status=status))

        if requisitante_id:
            qs = qs.filter(models.Q(requisitante_id=requisitante_id))

        if interessado_id:
            qs = qs.filter(models.Q(interessado_id=interessado_id))

        if responsavel_atendimento_atual_id or atendente_atribuido_atual_id:
            atendimentos_do_chamado = (
                AtendimentoAtribuicao.objects.select_related(
                    'grupo_atendimento',
                )
                .filter(
                    chamado=models.OuterRef('pk'),
                )
                .order_by('-atribuido_em')
            )

            if responsavel_atendimento_atual_id:
                # o desempenho desta consulta é um pouco prejudicado devido à necessidade
                # de realizar sub-consultas para verificar se o usuário em questão é responsável
                # pelo grupo de atendimento atual
                qs = qs.annotate(
                    # atendimentos_do_chamado[:1] é o atendimento atual (mais recente)
                    grupo_atendimento_atual_pk=models.Subquery(atendimentos_do_chamado[:1].values('grupo_atendimento__pk')),
                    user_eh_responsavel_pelo_grupo_atendimento_atual=models.Exists(
                        models.Subquery(
                            GrupoAtendimento.objects.prefetch_related('responsaveis').filter(
                                pk=models.OuterRef('grupo_atendimento_atual_pk'), responsaveis__id=responsavel_atendimento_atual_id
                            )
                        )
                    ),
                )

                qs = qs.filter(
                    models.Q(
                        # o usuário é um chefe do atendimento atual (um dos responsáveis pelo grupo de atendimento atual)
                        user_eh_responsavel_pelo_grupo_atendimento_atual=True
                    )
                )

            if atendente_atribuido_atual_id:
                qs = qs.annotate(
                    # atendimentos_do_chamado[:1] é o atendimento atual (mais recente)
                    atribuido_para_pk=models.Subquery(atendimentos_do_chamado[:1].values('atribuido_para__pk')),
                )

                qs = qs.filter(
                    models.Q(
                        # o usuário está atribuído ao atendimento atual
                        atribuido_para_pk=atendente_atribuido_atual_id
                    )
                )

        return qs

    @staticmethod
    def chamados_a_fechar(
        usuario: User,
        como_requisitante: bool = False,
        como_interessado: bool = False,
        como_responsavel_atendimento_atual: bool = False,
        restringe_superuser: bool = True,
    ) -> models.QuerySet[Chamado]:
        """
        Chamados prontos a serem fechados pelo usuário informado.

        Critérios (deduzidos do método models.Chamado.pode_fechar):
            - chamados resolvidos.
            - o usuário é o requisitante.
            - o usuário é o interessado.
            - o usuário é um dos chefes do atendimento atual (um dos responsáveis pelo grupo de atendimento atual).

        Um usuário superuser poderá fechar TODOS os chamados resolvidos.
        """

        qs_resolvidos = Chamado.chamados_por_status_e_atores(status=StatusChamado.get_status_resolvido())

        if usuario.is_superuser and not restringe_superuser:
            return qs_resolvidos
        else:
            qs_como_requisitante = Chamado.objects.none()
            qs_como_interessado = Chamado.objects.none()
            qs_como_responsavel_atendimento_atual = Chamado.objects.none()
            if como_requisitante:
                qs_como_requisitante = Chamado.chamados_por_status_e_atores(requisitante_id=usuario.id)
            if como_interessado:
                qs_como_interessado = Chamado.chamados_por_status_e_atores(interessado_id=usuario.id)
            if como_responsavel_atendimento_atual:
                qs_como_responsavel_atendimento_atual = Chamado.chamados_por_status_e_atores(responsavel_atendimento_atual_id=usuario.id)
            return qs_resolvidos & (qs_como_requisitante | qs_como_interessado | qs_como_responsavel_atendimento_atual)

    @staticmethod
    def chamados_em_andamento_por_servico_e_atribuicao_atual(
        servico: Servico,
        atribuido_a: User,
    ):
        qs_chamados = (
            Chamado.chamados_por_status_e_atores(status=StatusChamado.get_status_em_atendimento(), atendente_atribuido_atual_id=atribuido_a.id)
            .select_related(
                'servico',
            )
            .filter(servico=servico)
        )

        return qs_chamados

    def get_absolute_url(self):
        return f'/centralservicos/chamado/{self.id}/'

    @transaction.atomic()
    def save(self, *args, **kwargs):
        """
        Ao criar um Chamado, cria automaticamente um Chamado Atendimento e um HistoricoStatus
        O detalhe é que o save só é chamado quando está sendo criado um chamado
        """
        insert = not self.pk
        # `aberto_em` é `auto_now_add` e o Django só o preenche no `pre_save`, DEPOIS daqui; a data
        # limite, porém, é calculada agora e soma `timedelta` a `aberto_em`. Sem o fallback, um
        # chamado criado por ORM (fixture, comando, importação) estoura
        # `TypeError: unsupported operand type(s) for +: 'NoneType' and 'datetime.timedelta'`.
        # A tela sempre manda o momento da abertura; o código não.
        self.aberto_em = self.aberto_em or datetime.now()
        self.data_limite_atendimento = self.calcula_data_limite_sem_feriados_fds()
        retorno = super().save(*args, **kwargs)
        if insert:
            atribuicao = AtendimentoAtribuicao()
            atribuicao.chamado = self
            if not self.centro_atendimento:
                raise ValidationError('É necessário informar um centro de atendimento ao abrir o chamado.')

            grupo = GrupoAtendimento.get_grupo_primeiro_nivel(self.campus, self.centro_atendimento)
            if not grupo:
                raise ValidationError(
                    f'Nenhum grupo de atendimento foi cadastrado para a UO ({self.campus}) '
                    f'do servidor Interessado, no centro de atendimento ({self.centro_atendimento}).'
                )

            atribuicao.grupo_atendimento = grupo
            atribuicao.atribuido_em = datetime.today()
            atribuicao.save()

            historico_status = HistoricoStatus()
            historico_status.chamado = self
            historico_status.usuario = self.aberto_por
            historico_status.data_hora = self.aberto_em
            historico_status.status = self.status
            historico_status.save()
        return retorno

    def tem_tags_disponiveis(self, areas):
        return Tag.objects.exclude(id__in=self.tags.all()).filter(area__in=areas).exists()

    def criar_comunicacao(self, usuario, data_hora, observacao):
        if observacao:
            mensagem_automatica = self.fechado_automaticamente or False
            comunicacao = Comunicacao()
            comunicacao.chamado = self
            comunicacao.data_hora = data_hora
            comunicacao.remetente = usuario
            comunicacao.tipo = comunicacao.TIPO_COMENTARIO
            comunicacao.texto = observacao
            comunicacao.mensagem_automatica = mensagem_automatica
            comunicacao.save(suspender_notificacao=True)
            return comunicacao
        return None

    @transaction.atomic()
    def gravar_historico_status(self, usuario, status, data_hora, tempo_atendimento=None, tempo_suspensao=None, tempo_resposta=None, observacao=None):
        historico_status = HistoricoStatus()
        historico_status.chamado = self
        historico_status.usuario = usuario
        historico_status.status = status
        historico_status.data_hora = data_hora
        historico_status.tempo_atendimento = tempo_atendimento
        historico_status.tempo_suspensao = tempo_suspensao
        historico_status.tempo_resposta = tempo_resposta
        historico_status.comunicacao = self.criar_comunicacao(usuario, data_hora, observacao)
        historico_status.save()
        return historico_status

    def get_source_state(
        self,
    ):
        transitions = self.get_available_status_transitions()
        actual = {t.source for t in transitions}
        return actual.pop()

    @transition(
        field=status,
        source=StatusChamado.EM_ATENDIMENTO,
        target=StatusChamado.RESOLVIDO,
        # Nenhuma via (resolução em conjunto, criação de processo) resolve chamado com tarefa pendente (#17792).
        conditions=[lambda instance: not instance.get_tarefas_vinculadas_pendentes().exists()],
        permission=lambda instance, user: instance.eh_atendente(user),
    )
    def resolver_chamado_transition(self, usuario):
        pass

    def resolver_chamado(self, usuario, bases_conhecimento, observacao=None) -> bool:
        """
        Se  target é Resolvido / Suspenso e o anterior em atendimento,
        conta tempo de Atendimento
        """
        self.resolver_chamado_transition(usuario)
        with transaction.atomic():
            self.save()
            agora = datetime.today()
            tempo = agora - self.get_ultimo_historico_status().data_hora
            historico_status = self.gravar_historico_status(
                usuario, StatusChamado.RESOLVIDO, agora, tempo_atendimento=tempo.total_seconds(), observacao=observacao
            )
            historico_status.atualizar_bases_conhecimento(bases_conhecimento)
        #
        Notificar.status_atualizado(self)
        return True

    @transition(field=status, source=StatusChamado.EM_ATENDIMENTO, target=StatusChamado.SUSPENSO)
    def suspender_chamado_transition(
        self,
    ):
        pass

    def suspender_chamado(self, usuario, observacao=None):
        self.suspender_chamado_transition()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.SUSPENSO, datetime.today(), observacao=observacao)

        Notificar.status_atualizado(self)

    @transition(field=status, source=[StatusChamado.RESOLVIDO, StatusChamado.FECHADO], target=StatusChamado.REABERTO)
    def reabrir_chamado_transition(
        self,
    ):
        pass

    @transition(field=status, source=[StatusChamado.EM_ATENDIMENTO], target=StatusChamado.ABERTO)
    def escalar_chamado_transition(
        self,
    ):
        pass

    def escalar_chamado(self, usuario):
        self.escalar_chamado_transition()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.ABERTO, datetime.today())
        Notificar.status_atualizado(self)

    @transition(
        field=status,
        source=[StatusChamado.ABERTO, StatusChamado.REABERTO, StatusChamado.EM_ATENDIMENTO, StatusChamado.SUSPENSO],
        target=StatusChamado.CANCELADO,
    )
    def cancelar_chamado_transition(
        self,
    ):
        pass

    def cancelar_chamado(self, usuario: User, observacao: str | None) -> None:
        self.cancelar_chamado_transition()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.CANCELADO, datetime.today(), observacao=observacao)
            # Tarefa de chamado cancelado perde o objeto: sem isto, ficaria pendente para sempre (#17794).
            for tarefa_pendente in self.get_tarefas_vinculadas_pendentes():
                tarefa_pendente.alterar_tarefa(usuario, tarefa_pendente.responsavel, TarefaChamado.SITUACAO_CANCELADA)

        Notificar.status_atualizado(self)

    def get_available_status_index(
        self,
    ):
        return [s.target for s in self.get_available_status_transitions()]

    def get_available_status_name(
        self,
    ):
        return [
            (StatusChamado.get_action_from_status(s.target), StatusChamado.STATUS[s.target].replace(' ', '_').lower())
            for s in self.get_available_status_transitions()
        ]

    def get_available_status_display_name(
        self,
    ):
        return [StatusChamado.STATUS[s.target] for s in self.get_available_status_transitions()]

    def get_proximos_status(self):
        try:
            # return next(self.get_available_status_transitions()).target
            return sorted(t.target for t in self.get_available_status_transitions())[0]
        except StopIteration:
            return None

    @transition(
        field=status,
        source=[StatusChamado.ABERTO, StatusChamado.REABERTO, StatusChamado.SUSPENSO],
        target=StatusChamado.EM_ATENDIMENTO,
        permission=lambda instance, user: instance.eh_atendente(user),
    )
    def colocar_em_atendimento_transition(self, usuario):
        pass

    def colocar_em_atendimento(self, usuario):
        self.colocar_em_atendimento_transition(usuario)
        agora = datetime.today()
        tempo = agora - self.get_ultimo_historico_status().data_hora
        tempo_resposta = tempo.total_seconds()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.get_status_em_atendimento(), agora, tempo_resposta=tempo_resposta)
        Notificar.status_atualizado(self)

    @transition(field=status, source=[StatusChamado.RESOLVIDO], target=StatusChamado.FECHADO)
    def fechar_chamado_transition(
        self,
    ):
        pass

    def fechar_chamado(self, usuario, nota_avaliacao=None, comentario_avaliacao=None, fechado_automaticamente=None, observacao=None):
        self.fechar_chamado_transition()
        with transaction.atomic():
            if nota_avaliacao:
                self.nota_avaliacao = nota_avaliacao
                self.data_avaliacao = datetime.now()
            if comentario_avaliacao:
                self.comentario_avaliacao = comentario_avaliacao
            self.fechado_automaticamente = fechado_automaticamente
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.FECHADO, datetime.today(), observacao=observacao)
        #
        Notificar.status_atualizado(self)

    """
        Chamada a este método ocorre quando um chamado é reclassificado e muda de Centro/Grupo de Atentimento.
        Neste caso, o chamado estava Em Atendimento e deve ficar Em Aberto no novo Centro/Grupo de Atentimento.

    """

    @transition(field=status, source=[StatusChamado.EM_ATENDIMENTO], target=StatusChamado.ABERTO)
    def colocar_em_aberto_transition(
        self,
    ):
        pass

    def colocar_em_aberto(self, usuario, observacao=None):
        self.colocar_em_aberto_transition()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.ABERTO, datetime.today(), observacao=observacao)
        Notificar.status_atualizado(self)

    def reabrir_chamado(self, usuario, observacao):
        self.reabrir_chamado_transition()
        with transaction.atomic():
            self.save()
            self.gravar_historico_status(usuario, StatusChamado.REABERTO, datetime.today(), observacao=observacao)
        Notificar.status_atualizado(self)

    def escalar_ou_retornar_atendimento(self, operacao, atribuido_por, atribuido_para=None):
        """
        Escala (sobe o nível do atendimento) ou
        Retorna (desce o nível do atendimento)
        Informe escalar=True para subir e escalar=False para descer
        """
        # Obtem a atribuicao mais recente
        atribuicao = self.get_atendimento_atribuicao_atual()
        if operacao == 'escalar':
            grupo = atribuicao.grupo_atendimento.grupo_atendimento_superior
            tipo_justificativa = AtendimentoAtribuicao.TIPO_CHAMADO_ESCALADO
            justificativa_cancelamento = 'Chamado escalado para Nível de Atendimento Superior'
        else:
            grupo = atribuicao.grupo_atendimento.get_grupo_antendimento_inferior(self)
            tipo_justificativa = AtendimentoAtribuicao.TIPO_CHAMADO_RETORNADO
            justificativa_cancelamento = 'Chamado retornado ao Nível de Atendimento Anterior'

        # Atualiza a atribuicao anterior e cria uma nova
        atribuicao.cancelado_em = datetime.today()
        atribuicao.cancelado_por = atribuido_por
        atribuicao.justificativa_cancelamento = justificativa_cancelamento
        atribuicao.tipo_justificativa = tipo_justificativa
        atribuicao.save()

        atribuicao = AtendimentoAtribuicao()
        atribuicao.chamado = self
        atribuicao.grupo_atendimento = grupo
        atribuicao.atribuido_em = datetime.today()
        atribuicao.atribuido_por = atribuido_por
        atribuicao.atribuido_para = atribuido_para
        atribuicao.save()

        if self.status != StatusChamado.get_status_aberto() and self.status != StatusChamado.get_status_reaberto():
            # Altera o status para reaberto.
            self.escalar_chamado(atribuido_por)

    def escalar_atendimento(self, atribuido_por):
        self.escalar_ou_retornar_atendimento('escalar', atribuido_por)
        self.save()

    def retornar_atendimento(self, atribuido_por):
        self.escalar_ou_retornar_atendimento('retornar', atribuido_por)
        self.save()

    def atribuir_atendente(
        self, grupo, atribuido_por, atribuido_para, justificativa_cancelamento='Nova atribuição de chamado', tipo_justificativa=None
    ):
        """
        Verifica se está atribuído a alguem.
        Se estiver: cancela e se auto atribui
        Se não estiver: se auto atribui
        """
        # Obtem a atribuicao mais recente
        atribuicao = self.get_atendimento_atribuicao_atual()
        if atribuicao.atribuido_para:
            # Sim, está atribuido para alguem diferente da nova atribuicao
            if atribuicao.atribuido_para != atribuido_para:
                # Atualiza a atribuicao anterior e cria uma nova
                atribuicao.cancelado_em = datetime.today()
                atribuicao.cancelado_por = atribuido_por
                atribuicao.justificativa_cancelamento = justificativa_cancelamento
                atribuicao.tipo_justificativa = tipo_justificativa or AtendimentoAtribuicao.TIPO_NOVA_ATRIBUICAO
                atribuicao.save()

                atribuicao = AtendimentoAtribuicao()
                atribuicao.chamado = self
                atribuicao.grupo_atendimento = grupo
                atribuicao.atribuido_em = datetime.today()
                atribuicao.atribuido_por = atribuido_por
                atribuicao.atribuido_para = atribuido_para
                atribuicao.save()

        else:
            # Ainda não está atribuido para ninguem
            atribuicao.atribuido_por = atribuido_por
            atribuicao.atribuido_para = atribuido_para
            atribuicao.atribuido_em = datetime.today()
            atribuicao.save()

        if atribuido_por != atribuido_para:
            Notificar.chamado_atribuido(self)

    @transaction.atomic
    def reclassificar(self, servico_novo, campus_novo, centro_atendimento_novo, justificativa, usuario):
        if self.status not in (StatusChamado.get_status_aberto(), StatusChamado.get_status_reaberto(), StatusChamado.get_status_em_atendimento()):
            raise ValidationError('Um chamado só pode ser reclassificado se estiver Aberto ou Em Atendimento.')

        grupo = GrupoAtendimento.get_grupo_primeiro_nivel(campus_novo, centro_atendimento_novo)
        if not grupo:
            raise ValidationError('Não existe Grupo de Atendimento vinculado a este Serviço nesta Unidade Organizacional.')
        # Campus novo sendo atribuído aqui, pois pode mudar se o centro de atendimento não for local
        campus_novo = grupo.campus

        servico_anterior = self.servico
        campus_anterior = self.campus
        centro_atendimento_anterior = self.get_atendimento_atribuicao_atual().grupo_atendimento.centro_atendimento

        self.servico = servico_novo
        self.reclassificado = 1 if not self.reclassificado else self.reclassificado + 1
        self.campus = campus_novo
        self.save()

        comunicacao = Comunicacao()
        comunicacao.chamado = self
        comunicacao.remetente = usuario
        comunicacao.tipo = Comunicacao.TIPO_COMENTARIO
        texto = []
        texto.append(f'<strong>Chamado Reclassificado</strong> (Código Interno: #{servico_anterior.id}-{servico_novo.id})')
        if servico_anterior.id != servico_novo.id:
            texto.append(f'\n Serviço alterado de "{servico_anterior.nome}" para "{servico_novo.nome}".')
        if centro_atendimento_anterior.id != centro_atendimento_novo.id:
            texto.append(f'\n Centro de Atendimento alterado de "{centro_atendimento_anterior.nome}" para "{centro_atendimento_novo.nome}".')
        if campus_anterior.id != campus_novo.id:
            texto.append(f'\n Campus alterado de "{campus_anterior.nome}" para "{campus_novo.nome}".')
        comunicacao.texto = ''.join(texto)
        comunicacao.mensagem_automatica = True
        comunicacao.save()

        comunicacao.pk = None
        comunicacao.texto = justificativa
        comunicacao.mensagem_automatica = False
        comunicacao.save()

        """
        Ao reclassificar um chamado, caso mude o Centro de Atendimento,
        o chamado deverá mudar de status (caso já esteja em atendimento)
        e ser redirecionado para o primeiro nivel do novo centro de atendimento.
        """
        if (centro_atendimento_anterior != centro_atendimento_novo) or (campus_anterior != campus_novo):
            # Atualiza a atribuicao anterior e cria uma nova
            atribuicao = self.get_atendimento_atribuicao_atual()
            atribuicao.cancelado_em = datetime.today()
            atribuicao.cancelado_por = usuario
            atribuicao.justificativa_cancelamento = 'Alteração realizada em decorrência da mudança de Serviço/Centro de Atendimento.'
            atribuicao.save()

            atribuicao = AtendimentoAtribuicao()
            atribuicao.chamado = self
            atribuicao.grupo_atendimento = grupo
            atribuicao.atribuido_em = datetime.today()
            atribuicao.atribuido_por = usuario
            atribuicao.save()

            if self.status != StatusChamado.get_status_aberto() and self.status != StatusChamado.get_status_reaberto():
                self.colocar_em_aberto(usuario)

    @transaction.atomic
    def alterar_status(
        self,
        usuario,
        status_id=None,
        bases_conhecimento=None,
        observacao=None,
        nota_avaliacao=None,
        comentario_avaliacao=None,
        fechado_automaticamente=None,
    ):
        novo_status = status_id or self.get_proximo_status()
        agora = datetime.today()
        tempo_atendimento = None
        tempo_resposta = None
        tempo_suspensao = None
        tempo = agora - self.get_ultimo_historico_status().data_hora

        """ Se o status novo for Resolvido/Suspenso e o anterior em atendimento, conta tempo de Atendimento """
        """ Se o status novo Em Atendimento for e o anterior Suspenso, conta tempo de Suspensão """
        """ Se o status novo for Em Atendimento e o anterior Aberto/Reaberto, conta tempo de resposta """
        if (
            novo_status in (StatusChamado.get_status_resolvido(), StatusChamado.get_status_suspenso())
            and self.status == StatusChamado.get_status_em_atendimento()
        ):
            tempo_atendimento = tempo.total_seconds()
        elif novo_status == StatusChamado.get_status_em_atendimento() and self.status == StatusChamado.get_status_suspenso():
            tempo_suspensao = tempo.total_seconds()
        elif novo_status == StatusChamado.get_status_em_atendimento() and self.status in (
            StatusChamado.get_status_aberto(),
            StatusChamado.get_status_reaberto(),
        ):
            tempo_resposta = tempo.total_seconds()

        bases_conhecimento = bases_conhecimento or BaseConhecimento.objects.none()
        self.status = novo_status

        if nota_avaliacao:
            self.nota_avaliacao = nota_avaliacao
            self.data_avaliacao = datetime.now()
        if comentario_avaliacao:
            self.comentario_avaliacao = comentario_avaliacao
        self.fechado_automaticamente = fechado_automaticamente
        self.save()

        historico_status = HistoricoStatus()
        historico_status.chamado = self
        historico_status.usuario = usuario
        historico_status.data_hora = agora
        historico_status.status_id = self.status

        if tempo_atendimento:
            historico_status.tempo_atendimento = tempo_atendimento
        if tempo_resposta:
            historico_status.tempo_resposta = tempo_resposta
        if tempo_suspensao:
            historico_status.tempo_suspensao = tempo_suspensao

        if observacao:
            comunicacao = Comunicacao()
            comunicacao.chamado = self
            comunicacao.data_hora = historico_status.data_hora
            comunicacao.remetente = usuario
            comunicacao.tipo = comunicacao.TIPO_COMENTARIO
            comunicacao.texto = observacao
            comunicacao.save(suspender_notificacao=True)
            historico_status.comunicacao = comunicacao
        historico_status.save()
        for base in bases_conhecimento:
            historico_status.bases_conhecimento.add(base)

        Notificar.status_atualizado(self)

    @transaction.atomic
    def adicionar_outros_interessados(self, outros_interessados):
        self.outros_interessados.add(*outros_interessados)
        Notificar.adicao_outros_interessados(self, outros_interessados)

    @transaction.atomic
    def adicionar_grupos_interessados(self, grupos_interessados):
        qs = User.objects.none()
        for grupo in grupos_interessados:
            qs = qs | grupo.interessados.all().exclude(id__in=self.outros_interessados.all()).exclude(id=self.interessado.id)
        self.adicionar_outros_interessados(qs.all().distinct())

    def adicionar_tags(self, tags):
        self.tags.add(*tags)

    def get_tempo_resposta(self):
        return timedelta(seconds=self.total_tempo_resposta)

    def get_tempo_atendimento(self):
        return timedelta(seconds=self.total_tempo_atendimento)

    def get_tempo_suspensao(self):
        return timedelta(seconds=self.total_tempo_suspensao)

    def get_tempo_gasto(self):
        return timedelta(seconds=self.total_tempo_gasto)

    def get_sla_em_horas(self):
        """Retorna o tempo do SLA do chamado em função da data
        limite do atendimento já resolvida cuja cálculo foi feito
        em função do SLA do servico deste chamado (ver calcula_data_limite_sem_feriados_fds).
        Calculando a diferença (em horas) entre a data_limite_atendimento e a data de abertura do chamado.
        """
        tempo = self.data_limite_atendimento - self.aberto_em
        return int(tempo.total_seconds() // 3600)

    def get_tempo_gasto_detalhes(self):
        """Retorna uma lista com tempo efetivamente gasto com o atendimento
        É a somatória do período de tempo entre os chamados abertos/reabertos e resolvidos (ou ainda não resolvidos)
        A lista contem os atributos: status, data_inicio, data_fim, tempo_total
        O último registro da lista, contém apenas o tempo total
        """
        tempo = timedelta(seconds=0)
        lista = []
        data_inicio = None
        data_fim = None
        status_inicio = None
        try:
            for historico_status in self.historicostatus_set.all():
                if historico_status.status in (StatusChamado.get_status_aberto(), StatusChamado.get_status_reaberto()):
                    data_inicio = historico_status.data_hora
                    status_inicio = historico_status.status

                elif historico_status.status == StatusChamado.get_status_resolvido():
                    data_fim = historico_status.data_hora
                    status_fim = historico_status.status
                    ultimo_registro = data_fim - data_inicio
                    tempo += ultimo_registro
                    d = {
                        'status_inicio': status_inicio,
                        'data_inicio': data_inicio,
                        'status_fim': status_fim,
                        'data_fim': data_fim,
                        'tempo_total': ultimo_registro,
                    }
                    lista.append(d)
                    data_inicio = None
                    data_fim = None
                    status_inicio = None

            if data_inicio and not data_fim:
                agora = datetime.now()
                ultimo_registro = agora - data_inicio
                tempo += ultimo_registro
                d = {'status_inicio': status_inicio, 'data_inicio': data_inicio, 'tempo_total': ultimo_registro}
                lista.append(d)

            d = {'tempo_total': timedelta(seconds=tempo.total_seconds())}
            lista.append(d)
        except Exception:
            return None

        return lista

    def get_tempo_atendimento_atual(self):
        """Se o chamado estiver Em Atendimento, será o tempo desde
        o início do último atendimento até a data corrente."""

        if self.estah_em_atendimento():
            hist_ultimo_status_atendimento = self.historicostatus_set.filter(status=StatusChamado.EM_ATENDIMENTO).order_by('-data_hora').first()
            if hist_ultimo_status_atendimento:
                agora = datetime.now()
                tempo_atendimento_atual = max(agora - hist_ultimo_status_atendimento.data_hora, timedelta(0)).total_seconds()
        else:
            tempo_atendimento_atual = 0

        return timedelta(seconds=tempo_atendimento_atual)

    def get_tempo_ultrapassado(self):
        """Calcula o tempo ultrapassado do chamado a partir do
        total de tempo de gasto ALÉM do SLA do chamado.
        Considera, como parte do total de tempo gasto, o tempo do
        atendimento atual que ainda pode estar em andamento."""

        sla_chamado_td = timedelta(hours=self.get_sla_em_horas())
        tempo_gasto_td = self.get_tempo_gasto() + self.get_tempo_atendimento_atual()

        return max(tempo_gasto_td - sla_chamado_td, timedelta(seconds=0))

    def get_tempo_total_suspenso(self):
        """
        Calcula o tempo total que o chamado ficou suspenso.
        Considera todos os períodos de suspensão no histórico de status.
        """
        tempo_total = timedelta(seconds=0)
        suspensoes = self.historicostatus_set.filter(status=StatusChamado.SUSPENSO).order_by('data_hora')

        for suspensao in suspensoes:
            # Obtém a próxima mudança de status após a suspensão
            proxima_mudanca = self.historicostatus_set.filter(data_hora__gt=suspensao.data_hora).order_by('data_hora').first()

            if proxima_mudanca and proxima_mudanca.status != StatusChamado.CANCELADO:
                tempo_suspenso = proxima_mudanca.data_hora - suspensao.data_hora
            else:
                tempo_suspenso = datetime.now() - suspensao.data_hora  # Se ainda estiver suspenso

            tempo_total += tempo_suspenso

        return tempo_total

    def calcula_data_limite_sem_feriados_fds(self):
        """
        Retorna a data limite de atendimento do chamado considerando o
        SLA do serviço, finais de semana e feriados.
        """

        data_inicio = self.aberto_em
        sla = self.servico.sla_em_horas
        liberacoes = self.busca_liberacoes(data_inicio)

        # Data de início para após fds ou feriado (se for o caso).
        while data_inicio.weekday() in (5, 6) or data_inicio.date() in liberacoes:
            data_inicio += timedelta(days=1)

        sla_dias = sla // 24
        sla_horas_restantes = sla % 24

        data_limite = data_inicio

        # Data limite para após fds ou feriado.
        while sla_dias > 0:
            data_limite += timedelta(days=1)
            if not (data_limite.weekday() in (5, 6) or data_limite.date() in liberacoes):
                sla_dias -= 1

        # Adiciona a fração restante das horas do SLA.
        data_limite += timedelta(hours=sla_horas_restantes)

        return data_limite

    def busca_liberacoes(self, data_inicio):
        """retorna a lista de dias que não tem expediente"""
        liberacoes = []
        Liberacao = apps.get_model('ponto', 'Liberacao')
        if Liberacao:
            data_fim = data_inicio + timedelta(days=150)

            lista_liberacoes = list(Liberacao.get_liberacoes_calendario_recorrentes(UnidadeOrganizacional.TIPO_REITORIA, data_inicio.year)) + list(
                Liberacao.objects.filter(uo=None, data_inicio__gte=data_inicio, ch_maxima_exigida=0)
            )

            if data_inicio.year != data_fim.year:
                lista_liberacoes = lista_liberacoes + list(Liberacao.get_liberacoes_calendario(UnidadeOrganizacional.TIPO_REITORIA, data_fim.year))

            for liberacao in lista_liberacoes:
                liberacoes.extend(self.transforma_periodo_em_lista_dias(liberacao.data_inicio, liberacao.data_fim))
        return liberacoes

    def transforma_periodo_em_lista_dias(self, data_inicio, data_fim):
        """Retorna a lista de dias entre a data_inicio até data_fim"""
        dias = []
        while data_inicio <= data_fim:
            dias.append(data_inicio)
            data_inicio += timedelta(days=1)
        return dias

    def get_tempo_ate_data_limite(self):
        """Retorna o tempo restante ate atingir a data limite"""
        tempo = self.data_limite_atendimento - datetime.now()
        return timedelta(seconds=tempo.total_seconds())

    def get_tempo_apos_data_limite(self):
        """Retorna o tempo ultrapassado após atingir a data limite"""
        tempo = datetime.now() - self.data_limite_atendimento
        return timedelta(seconds=tempo.total_seconds())

    def get_bases_de_conhecimento_aplicadas(self):
        qs = self.historicostatus_set.filter(status=StatusChamado.get_status_resolvido())
        if qs.exists():
            return qs.order_by('-data_hora')[0].bases_conhecimento.all()

    def get_ultimo_historico_status(self):
        return self.historicostatus_set.order_by('-data_hora')[0]

    def get_atendimento_atribuicao_atual(self):
        return self.atendimentoatribuicao_set.all().first()

    def get_atendimento_atribuicao_anterior(self):
        atendimentos = self.atendimentoatribuicao_set.all()
        if atendimentos.count() > 1:
            return atendimentos[1]

    def get_historicostatus(self):
        return self.historicostatus_set.all().order_by('-data_hora')

    def get_comentarios(self):
        return self.comunicacao_set.filter(tipo=Comunicacao.TIPO_COMENTARIO)

    def get_comentarios_arquivados(self) -> models.QuerySet[Comunicacao]:
        return self.comunicacao_set.filter(tipo=Comunicacao.TIPO_COMENTARIO, escondida_em__isnull=False).order_by('-escondida_em')

    def get_notas_internas(self):
        return self.comunicacao_set.filter(tipo=Comunicacao.TIPO_NOTA_INTERNA).order_by('-data_hora')

    def email_interessados(self):
        emails = []
        if self.interessado.email:
            emails += [self.interessado.email]
        emails += self.outros_interessados.exclude(email='').values_list('email', flat=True)
        return emails

    def get_vinculos_interessados(self):
        interessados = []
        if self.outros_interessados.exists():
            for outro in self.outros_interessados.all():
                interessados.append(outro.get_vinculo())
        interessados.append(self.interessado.get_vinculo())
        return interessados

    def eh_outro_interessado(self, user):
        return self.outros_interessados.filter(username=user.username).exists()

    def get_atendente_do_chamado(self):
        return self.get_atendimento_atribuicao_atual().atribuido_para

    def get_responsaveis_equipe_atendimento(self):
        """Retorna os chefes do Grupo de Atendimento do respectivo Chamado"""
        atendimento = self.get_atendimento_atribuicao_atual()
        if atendimento:
            return atendimento.grupo_atendimento.responsaveis.all()

    def get_atendentes_equipe_atendimento(self):
        """Retorna os atendentes do Grupo de Atendimento do respectivo Chamado"""
        atendimento = self.get_atendimento_atribuicao_atual()
        if atendimento:
            return atendimento.grupo_atendimento.atendentes.all()

    def eh_atendente(self, user):
        atendimento = self.get_atendimento_atribuicao_atual()
        return user.has_perm('centralservicos.change_chamado') and atendimento and atendimento.atribuido_para == user and not atendimento.cancelado_em

    def estah_resolvido(self):
        return self.status == StatusChamado.get_status_resolvido()

    def estah_suspenso(self):
        return self.status == StatusChamado.get_status_suspenso()

    def estah_em_atendimento(self):
        return self.status == StatusChamado.get_status_em_atendimento()

    def estah_fechado(self):
        return self.status == StatusChamado.get_status_fechado()

    def estah_cancelado(self):
        return self.status == StatusChamado.get_status_cancelado()

    def eh_proximo_status_em_atendimento(self):
        return StatusChamado.get_status_em_atendimento() in self.get_available_status_index()

    def pode_escalar(self):
        """Para poder escalar o chamado, o mesmo não pode estar resolvido, nao pode estar fechado
        deve estar atribuído a algum atendente e deve possuit um grupo de atendimento superior
        """
        return bool(
            self.status
            not in (
                StatusChamado.get_status_resolvido(),
                StatusChamado.get_status_fechado(),
                StatusChamado.get_status_cancelado(),
                StatusChamado.get_status_suspenso(),
            )
            and self.get_atendimento_atribuicao_atual()
            and self.get_atendimento_atribuicao_atual().atribuido_para
            and self.get_atendimento_atribuicao_atual().grupo_atendimento.grupo_atendimento_superior
        )

    def pode_atribuir(self):
        return self.status not in (StatusChamado.get_status_resolvido(), StatusChamado.get_status_fechado(), StatusChamado.get_status_cancelado())

    def pode_assumir(self, user):
        atendimento_atribuicao = self.get_atendimento_atribuicao_atual()
        return bool(
            atendimento_atribuicao
            and self.pode_atribuir()
            and atendimento_atribuicao.atribuido_para != user
            and atendimento_atribuicao.grupo_atendimento.pertence_ao_grupo(user)
            and user.has_perm('centralservicos.change_chamado')
        )

    def pode_retornar(self):
        return bool(
            self.status
            not in (
                StatusChamado.get_status_resolvido(),
                StatusChamado.get_status_fechado(),
                StatusChamado.get_status_cancelado(),
                StatusChamado.get_status_suspenso(),
            )
            and self.get_atendimento_atribuicao_atual()
            and self.get_atendimento_atribuicao_atual().grupo_atendimento.get_grupo_antendimento_inferior(self)
        )

    def pode_fechar(self, user):
        """Para poder fechar o chamado, o chamado deverá estar resolvido"""
        """ E o usuário ser super user, chefe do atendimento ou o proprio usuario (pessoa_envolvida) """
        if self.estah_resolvido():
            return bool(
                user.is_superuser
                or user in (self.requisitante, self.interessado)
                or self.get_atendimento_atribuicao_atual().grupo_atendimento.responsaveis.filter(pk=user.pk).exists()
            )
        return False

    def pode_reabrir(self, user):
        """
        Para poder reabrir o chamado, o chamado deverá estar resolvido.

        E o usuário ser super user, chefe do atendimento ou o proprio
        usuario (pessoa_envolvida)
        """
        if self.estah_resolvido():
            return bool(
                user.is_superuser
                or user in (self.requisitante, self.interessado)
                or self.get_atendimento_atribuicao_atual().grupo_atendimento.responsaveis.filter(pk=user.pk).exists()
            )
        return False

    def pode_reclassificar(self, user):
        if self.status in (StatusChamado.get_status_aberto(), StatusChamado.get_status_reaberto(), StatusChamado.get_status_em_atendimento()):
            if user.is_superuser or self.get_responsaveis_equipe_atendimento().filter(pk=user.pk).exists() or self.eh_atendente(user):
                return True
        return False

    def pode_suspender(self, user):
        return self.status == StatusChamado.get_status_em_atendimento() and self.eh_atendente(user)

    def pode_cancelar(self, user):
        if self.status in (
            StatusChamado.get_status_aberto(),
            StatusChamado.get_status_reaberto(),
            StatusChamado.get_status_em_atendimento(),
            StatusChamado.get_status_suspenso(),
        ):
            if user in (self.requisitante, self.interessado) or self.eh_atendente(user) or user.is_superuser:
                return True
        return False

    def pode_criar_processo(self, user: User, ignorar_status=False):
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            return (
                user.has_group('Atendente da Central de Serviços')
                and self.eh_atendente(user)
                and (ignorar_status or self.status == StatusChamado.get_status_em_atendimento())
                and user.has_perm('processo_eletronico.add_processo')
                # criar o processo resolve e fecha o chamado (`views.finalizar_chamado`)
                and not self.get_tarefas_vinculadas_pendentes().exists()
            )
        return False

    TIPO_USUARIO_REQUISITANTE = 'R'
    TIPO_USUARIO_INTERESSADO = 'I'
    TIPO_USUARIO_OUTROS_INTERESSADOS = 'O'
    TIPO_USUARIO_ALGUM_INTERESSE = 'RIO'
    TIPO_USUARIO_CHOICES = [
        [TIPO_USUARIO_REQUISITANTE, 'Requisitante'],
        [TIPO_USUARIO_INTERESSADO, 'Interessado'],
        [TIPO_USUARIO_OUTROS_INTERESSADOS, 'Outro Interessado'],
        [TIPO_USUARIO_ALGUM_INTERESSE, 'Algum Interesse'],
        ['', 'Qualquer'],
    ]

    # As consultas abaixo não usam DISTINCT: nenhum filtro faz JOIN com relação to-many (outros interessados,
    # tags); essas vão por `pk__in`, então cada chamado aparece uma vez e o `count()` é um COUNT(*) simples (#17814).

    @staticmethod
    def _ids_de_outro_interessado(user: User) -> QuerySet:
        return Chamado.outros_interessados.through.objects.filter(user=user).values('chamado')

    @classmethod
    def _ids_de_algum_interesse(cls, user: User) -> QuerySet:
        """Ids dos chamados em que `user` é requisitante, interessado ou outro interessado.

        UNION em vez de OR com JOIN em `outros_interessados`: cada ramo usa o próprio índice."""
        return (
            Chamado.objects.filter(requisitante=user)
            .order_by()
            .values('pk')
            .union(Chamado.objects.filter(interessado=user).order_by().values('pk'), cls._ids_de_outro_interessado(user))
        )

    @classmethod
    def _filtro_tipo_usuario(cls, user: User, tipo_usuario: str | None) -> Q | None:
        if not tipo_usuario or tipo_usuario == Chamado.TIPO_USUARIO_ALGUM_INTERESSE:
            return Q(pk__in=cls._ids_de_algum_interesse(user))
        if tipo_usuario == Chamado.TIPO_USUARIO_OUTROS_INTERESSADOS:
            return Q(pk__in=cls._ids_de_outro_interessado(user))
        return {Chamado.TIPO_USUARIO_REQUISITANTE: Q(requisitante=user), Chamado.TIPO_USUARIO_INTERESSADO: Q(interessado=user)}.get(tipo_usuario)

    @staticmethod
    def _excluir_encerrados(qs: QuerySet) -> QuerySet:
        return qs.exclude(status__in=(StatusChamado.get_status_fechado(), StatusChamado.get_status_resolvido(), StatusChamado.get_status_cancelado()))

    @staticmethod
    def _filtrar_por_abertura(qs: QuerySet, data_inicial: date | None, data_final: date | None) -> QuerySet:
        if data_inicial:
            qs = qs.filter(aberto_em__gte=datetime(data_inicial.year, data_inicial.month, data_inicial.day, 0, 0, 0))
        if data_final:
            qs = qs.filter(aberto_em__lte=datetime(data_final.year, data_final.month, data_final.day, 23, 59, 59))
        return qs

    @classmethod
    def get_chamados_do_usuario(
        cls,
        user: User,
        chamado_id: int | None = None,
        area: AreaAtuacao | None = None,
        data_inicial: date | None = None,
        data_final: date | None = None,
        status: int | str | None = None,
        tipo_usuario: str | None = None,
    ) -> QuerySet:
        """
        data de abertura
            data_inicial = um date
            data_final = um date

        status
            status = um inteiro (StatusChamado.EM_ATENDIMENTO, ...) ou STATUS_ATIVO

        ator
            tipo_usuario = um string (TIPO_USUARIO_REQUISITANTE, ...)
        """
        filtro = cls._filtro_tipo_usuario(user, tipo_usuario)
        if filtro is None:
            return Chamado.objects.none()
        qs = Chamado.objects.filter(filtro)
        if chamado_id:
            return qs.filter(pk=chamado_id)
        if area:
            qs = qs.filter(servico__area=area)
        qs = cls._filtrar_por_abertura(qs, data_inicial, data_final)
        if status == STATUS_ATIVO:
            return cls._excluir_encerrados(qs)
        if status:
            qs = qs.filter(status=status)
        return qs

    ATRIBUIDOS_A_MIM = '1'
    ATRIBUIDOS_A_OUTROS = '2'
    SEM_ATRIBUICAO = '3'
    ATRIBUIDOS_A_MIM_OU_SEM_ATRIBUICAO = '4'
    ATRIBUIDOS = '5'
    ATRIBUICOES_CHOICES = [
        [ATRIBUIDOS_A_MIM, 'Atribuídos a mim'],
        [ATRIBUIDOS_A_OUTROS, 'Atribuídos a outros'],
        [SEM_ATRIBUICAO, 'Sem atribuição'],
        [ATRIBUIDOS_A_MIM_OU_SEM_ATRIBUICAO, 'Atribuídos a mim ou sem atribuição'],
        [ATRIBUIDOS, 'Atribuídos'],
    ]

    @staticmethod
    def _filtro_atribuicao(user: User, atribuicoes: str | None, atendente: User | None) -> Q | None:
        """Filtro das atribuições ativas (não canceladas) conforme `atribuicoes`; None não filtra."""
        if atribuicoes == Chamado.ATRIBUIDOS_A_OUTROS:
            return Q(atribuido_para=atendente) if atendente else Q(atribuido_para__isnull=False) & ~Q(atribuido_para=user)
        return {
            Chamado.ATRIBUIDOS_A_MIM: Q(atribuido_para=user),
            Chamado.SEM_ATRIBUICAO: Q(atribuido_para__isnull=True),
            Chamado.ATRIBUIDOS_A_MIM_OU_SEM_ATRIBUICAO: Q(atribuido_para=user) | Q(atribuido_para__isnull=True),
            Chamado.ATRIBUIDOS: Q(atribuido_para__isnull=False),
        }.get(atribuicoes)

    @classmethod
    def _atendimentos_do_suporte(cls, user: User, **kwargs: Any) -> QuerySet:
        """Atribuições que põem o chamado na fila de `user` (grupos de atendimento, campus e atribuição)."""
        grupo_atendimento = kwargs.get('grupo_atendimento')
        if grupo_atendimento:
            filtro_grupo = (
                Q(grupo_atendimento__in=grupo_atendimento) if isinstance(grupo_atendimento, Iterable) else Q(grupo_atendimento=grupo_atendimento)
            )
            atendimentos = AtendimentoAtribuicao.objects.filter(filtro_grupo, cancelado_em__isnull=True)
        else:
            # Com `considerar_escalados`, também os chamados que já passaram pelos grupos de user (atribuição cancelada).
            atendimentos = AtendimentoAtribuicao.objects.filter(grupo_atendimento__in=GrupoAtendimento.meus_grupos(user, kwargs.get('area')))
            if not kwargs.get('considerar_escalados'):
                atendimentos = atendimentos.filter(cancelado_em__isnull=True)

        uo = kwargs.get('uo')
        if uo:
            atendimentos = atendimentos.filter(
                Q(grupo_atendimento__campus_id__in=uo) if isinstance(uo, Iterable) else Q(grupo_atendimento__campus=uo)
            )

        filtro_atribuicao = cls._filtro_atribuicao(user, kwargs.get('atribuicoes'), kwargs.get('atendente'))
        if filtro_atribuicao is not None:
            atendimentos = atendimentos.filter(filtro_atribuicao, cancelado_em__isnull=True)
        return atendimentos

    @classmethod
    def _filtrar_status_do_suporte(cls, qs: QuerySet, status: list[str] | None, todos_status: bool | None) -> QuerySet:
        if todos_status:
            return qs
        if status:
            return qs.filter(status__in=[int(s) for s in status])
        return cls._excluir_encerrados(qs)

    # Filtros de igualdade do suporte: argumento -> lookup.
    _FILTROS_SIMPLES_DO_SUPORTE = {
        'tipo': 'servico__tipo',
        'servico': 'servico',
        'grupo_servico': 'servico__grupo_servico',
        'aberto_por': 'aberto_por',
        'nota_avaliacao': 'nota_avaliacao',
        'numero_patrimonio': 'patrimonio__numero',
    }

    @classmethod
    def _filtrar_campos_do_suporte(cls, qs: QuerySet, **kwargs: Any) -> QuerySet:
        for argumento, lookup in cls._FILTROS_SIMPLES_DO_SUPORTE.items():
            if kwargs.get(argumento):
                qs = qs.filter(**{lookup: kwargs[argumento]})
        if kwargs.get('sla_estourado'):
            qs = qs.filter(sla_estourado=True)
        interessado = kwargs.get('interessado')
        if interessado:
            qs = qs.filter(pk__in=cls._ids_de_algum_interesse(interessado))
        tags = kwargs.get('tags')
        if tags:
            qs = qs.filter(pk__in=Chamado.tags.through.objects.filter(tag__in=tags).values('chamado'))
        texto_livre = kwargs.get('texto_livre')
        if texto_livre:
            comunicacoes = Comunicacao.objects.filter(texto__icontains=texto_livre)
            qs = qs.filter(
                Q(pk__in=comunicacoes.values('chamado')) | Q(descricao__unaccent__icontains=texto_livre) | Q(numero_patrimonio__icontains=texto_livre)
            )
        return qs

    @classmethod
    def get_chamados_do_suporte(cls, user: User, **kwargs: Any) -> QuerySet:
        """Chamados na fila de atendimento de `user`, anotados com `data_ultima_interacao` e ordenados.

        `kwargs`: chamado_id, grupo_atendimento, area, considerar_escalados, uo, atribuicoes, atendente,
        status (lista), todos_status, tipo, servico, grupo_servico, data_inicial, data_final, aberto_por,
        interessado, texto_livre, nota_avaliacao, tags, sla_estourado, numero_patrimonio, ordenar_por, tipo_ordenacao.
        """
        ordenar_por = f'{kwargs.get("tipo_ordenacao") or ""}{kwargs.get("ordenar_por") or "data_limite_atendimento"}'
        qs = Chamado.annotate_ultima_interacao(Chamado.objects.all())
        if kwargs.get('chamado_id'):
            return qs.filter(pk=kwargs['chamado_id']).order_by(ordenar_por)

        qs = qs.filter(pk__in=cls._atendimentos_do_suporte(user, **kwargs).values('chamado'))
        qs = cls._filtrar_status_do_suporte(qs, kwargs.get('status'), kwargs.get('todos_status'))
        qs = cls._filtrar_por_abertura(qs, kwargs.get('data_inicial'), kwargs.get('data_final'))
        qs = cls._filtrar_campos_do_suporte(qs, **kwargs)
        return qs.order_by(ordenar_por)

    def get_linha_do_tempo(self, ordem_decrescente=True, somente_tipos=None, excluir_tipos=None):
        if excluir_tipos is None:
            excluir_tipos = []
        if somente_tipos is None:
            somente_tipos = ['comentario', 'historicostatus', 'atendimentoatribuicao', 'anexo', 'avaliacao']
        somente_tipos = [tipo for tipo in somente_tipos if tipo not in excluir_tipos]

        lista = []
        if 'comentario' in somente_tipos:
            for comentario in self.get_comentarios():
                lista.append({'tipo': 'comentario', 'ordem': '2', 'data_hora': comentario.data_hora, 'objeto': comentario})
        if 'historicostatus' in somente_tipos:
            for historicostatus in self.get_historicostatus():
                lista.append({'tipo': 'historicostatus', 'ordem': '1', 'data_hora': historicostatus.data_hora, 'objeto': historicostatus})
        if 'atendimentoatribuicao' in somente_tipos:
            for atendimentoatribuicao in self.atendimentoatribuicao_set.order_by('-atribuido_em'):
                lista.append(
                    {'tipo': 'atendimentoatribuicao', 'ordem': '3', 'data_hora': atendimentoatribuicao.atribuido_em, 'objeto': atendimentoatribuicao}
                )
        if 'anexo' in somente_tipos:
            for anexo in self.chamadoanexo_set.order_by('-anexado_em'):
                lista.append({'tipo': 'anexo', 'ordem': '4', 'data_hora': anexo.anexado_em, 'objeto': anexo})
        if 'avaliacao' in somente_tipos and self.data_avaliacao:
            lista.append({'tipo': 'avaliacao', 'ordem': '1', 'data_hora': self.data_avaliacao})

        lista.sort(key=lambda x: (x['data_hora'], x['ordem']), reverse=ordem_decrescente)
        return lista

    @classmethod
    def get_chamados_com_sla_estourado(cls):
        return Chamado.objects.filter(
            data_limite_atendimento__lt=datetime.now(),
            status__in=(StatusChamado.get_status_aberto(), StatusChamado.get_status_em_atendimento(), StatusChamado.get_status_reaberto()),
        ).order_by('data_limite_atendimento')

    def get_visualizar_chamado_url(self):
        return f'{settings.SITE_URL}{self.get_absolute_url()}'

    @classmethod
    def annotate_ultima_interacao(cls, queryset: QuerySet) -> QuerySet:
        """Anota `data_ultima_interacao` (a primeira não nula, nesta ordem: comunicação, histórico, atribuição, anexo).

        Subconsultas correlacionadas em vez de MAX sobre quatro LEFT JOINs: sem GROUP BY nem multiplicação de linhas,
        e o `count()` do queryset descarta a anotação (#17814)."""

        def ultima(model: type[models.Model], campo: str) -> Subquery:
            # order_by() limpa o ordering do Meta, que entraria no GROUP BY e devolveria mais de uma linha.
            return Subquery(model.objects.filter(chamado=OuterRef('pk')).order_by().values('chamado').annotate(ultima=Max(campo)).values('ultima'))

        return queryset.annotate(
            data_ultima_interacao=Coalesce(
                ultima(Comunicacao, 'data_hora'),
                ultima(HistoricoStatus, 'data_hora'),
                ultima(AtendimentoAtribuicao, 'atribuido_em'),
                ultima(ChamadoAnexo, 'anexado_em'),
            )
        )

    def servico_requer_numero_patrimonio(self):
        return self.servico and self.servico.requer_numero_patrimonio

    def pode_editar_patrimonio_relacionado(self, user):
        chamado_em_andamento = not (self.estah_resolvido() or self.estah_cancelado() or self.estah_fechado())
        if self.servico_requer_numero_patrimonio() and chamado_em_andamento:
            user_atendendo = self.eh_atendente(user)
            user_abriu = user == self.aberto_por
            user_requisitou = user == self.requisitante
            return user_atendendo or user_abriu or user_requisitou
        return False

    @staticmethod
    def get_chamados_por_patrimonio(patrimonios: list[Inventario]):
        return Chamado.objects.filter(patrimonio__in=patrimonios)

    def get_tarefas_vinculadas(self):
        """tarefas vinculadas ao chamado"""
        return TarefaChamado.get_tarefas_vinculadas(chamado=self)

    def get_tarefas_vinculadas_info(self, user) -> dict:
        """tarefas vinculadas ao chamado com informações extras"""
        return dict(
            [
                tarefa_vinculada.id,
                {
                    'tarefa_vinculada': tarefa_vinculada,
                    'pode_atualizar_situacao': tarefa_vinculada.pode_atualizar_situacao(user),
                    'pode_visualizar': tarefa_vinculada.pode_visualizar(user),
                },
            ]
            for tarefa_vinculada in self.get_tarefas_vinculadas()
        )

    def get_tarefas_vinculadas_pendentes(self):
        """tarefas vinculadas ao chamado ainda pendentes"""
        return TarefaChamado.get_tarefas_vinculadas(
            chamado=self,
            situacoes=[
                TarefaChamado.SITUACAO_ABERTA,
                TarefaChamado.SITUACAO_EM_ANDAMENTO,
                TarefaChamado.SITUACAO_SUSPENSA,
            ],
        )

    def get_tarefas_vinculadas_por_responsavel(self, user):
        """tarefas vinculadas ao chamado de um usuário responsável"""
        return TarefaChamado.get_tarefas_vinculadas(chamado=self, user_responsavel=user)

    def eh_ou_foi_responsavel_por_tarefa_vinculada(self, user):
        """é ou já foi responsável por alguma tarefa vinculada ao chamado"""
        return TarefaChamadoHistorico.get_historicos_tarefas(chamado=self, user_responsavel=user).exists()

    def admite_tarefa_pendente(self) -> bool:
        """chamado resolvido, fechado ou cancelado não recebe tarefa nova nem volta a ter tarefa pendente"""
        return not (self.estah_resolvido() or self.estah_fechado() or self.estah_cancelado())

    def pode_vincular_tarefas(self, user: User) -> bool:
        return self.eh_atendente(user) and self.admite_tarefa_pendente()

    def get_atendimento_atual(self) -> dict:
        atendente: User = None
        grupo_atendimento: GrupoAtendimento = None
        responsaveis_grupo_atendimento: models.QuerySet[User] = User.objects.none()
        atendentes_grupo_atendimento: models.QuerySet[User] = User.objects.none()
        atribuicao_atual = self.get_atendimento_atribuicao_atual()
        if atribuicao_atual:
            atendente = atribuicao_atual.atribuido_para
            grupo_atendimento = atribuicao_atual.grupo_atendimento
            responsaveis_grupo_atendimento = grupo_atendimento.responsaveis.all()
            atendentes_grupo_atendimento = grupo_atendimento.atendentes.all()
        return {
            'atendente': atendente,
            'grupo_atendimento': grupo_atendimento,
            'responsaveis_grupo_atendimento': responsaveis_grupo_atendimento,
            'atendentes_grupo_atendimento': atendentes_grupo_atendimento,
        }

    def pode_resolver_info(self, user) -> dict:
        """
        resolver e fechar são situações/ações distintas sobre um chamado
        o fluxo é: resolver --> fechar (o chamado deve estar resolvido para poder ser fechado)

        1 - apenas o atendente do chamado
        2 - chamado não pode estar fechado
        3 - não pode haver tarefas vinculadas que estejam pendentes (não canceladas ou não finalizadas)
        """
        eh_atendente = self.eh_atendente(user)
        estah_fechado = self.estah_fechado()
        tem_tarefas_vinculadas_pendentes = self.get_tarefas_vinculadas_pendentes().exists()
        pode_resolver = eh_atendente and not estah_fechado and not tem_tarefas_vinculadas_pendentes
        msg_erro_permissao = []
        if not eh_atendente:
            msg_erro_permissao.append('Você não é o atendente deste chamado.')
        if estah_fechado:
            msg_erro_permissao.append('Este chamado está fechado.')
        if tem_tarefas_vinculadas_pendentes:
            msg_erro_permissao.append('Há tarefas vinculadas ainda pendentes.')
        return {
            'eh_atendente': eh_atendente,
            'estah_fechado': estah_fechado,
            'tem_tarefas_vinculadas_pendentes': tem_tarefas_vinculadas_pendentes,
            'pode_resolver': pode_resolver,
            'msg_erro_permissao': ' '.join(msg_erro_permissao),
        }

    def pessoa_envolvida(self, user):
        return user in (self.requisitante, self.interessado, self.aberto_por) or self.eh_outro_interessado(user)

    # def permite_visualizar(self, user):
    #     """
    #     Apenas Super usuário, Auditores, responsáveis pelo atendimento ou pessoas envolvidas na abertura
    #     do chamado podem visualizar o chamado, além de atendentes vinculados às tarefas do chamado
    #     """
    #     return (
    #         self.pessoa_envolvida(user)
    #         or (
    #             user.has_perm('centralservicos.change_chamado')
    #             and self.atendimentoatribuicao_set.filter(grupo_atendimento__in=user.atendentes_set.all())
    #         )
    #         or user.is_superuser
    #         or user.groups.filter(models.Q(name='centralservicos Administrador') | models.Q(name='Auditor')).exists()
    #         or self.get_tarefas_vinculadas_por_responsavel(user).exists()
    #     )

    def get_permissoes(self, user) -> dict:
        """
        Calcula algumas permissões dependentes entre si de forma centralizada por questões de desempenho.

        Pode visualizar:
            A regra de origem foi extraída de views.visualizar_chamado e
            models.Chamado.permite_visualizar, e ainda está disponível (comentada).

            1-user é super usuário
            2-user é pessoa envolvida na abertura (requisitante, interessado, aberto_por, eh_outro_interessado)
            3-user é responsável pelo atendimento
            4-user é do grupo administrador da central de serviços
            5-user é do grupo auditor
            6-user está vinculado às tarefas do chamado (demanda 1715)

        Pode adicionar comentário:
            A regra de origem foi extraída de views.visualizar_chamado e
            views.__adicionar_comentario_ou_nota_interna, e ainda está disponível (comentada).

            1-user é superuser
            2-user é pessoa envolvida na abertura (requisitante, interessado, aberto_por, eh_outro_interessado)
            3-user é responsável pelo atendimento
            4-user é do grupo administrador da central de serviços
            5-user está vinculado às tarefas do chamado (demanda 1715)
                e chamado está em atendimento ou suspenso

        Pode adicionar nota interna:
            A regra de origem foi extraída de views.__adicionar_comentario_ou_nota_interna
            e ainda está disponível (comentada).

            1-user pode visualizar
                e user é
                    atendente do chamado
                    ou atendente da equipe de atendimento
                    ou responsável pela equipe de atendimento

        Pode adicionar anexo:
            A regra de origem foi extraída de views.adicionar_anexo e tab_anexos.html,
            e ainda está disponível (comentada).

            1-user pode visualizar
                e serviço do chamado permite anexos
                e chamado não resolvido
                e chamado não fechado
                e chamado não cancelado
        """

        user_eh_superuser = user.is_superuser
        user_eh_pessoa_envolvida = self.pessoa_envolvida(user)
        user_eh_responsavel_atendimento = (
            user.has_perm('centralservicos.change_chamado')
            and self.atendimentoatribuicao_set.filter(grupo_atendimento__in=user.atendentes_set.all()).exists()
        )
        user_eh_admin_central = user.groups.filter(name='centralservicos Administrador').exists()
        user_eh_grupo_auditor = user.groups.filter(name='Auditor').exists()
        user_estah_tarefas_chamado = self.get_tarefas_vinculadas_por_responsavel(user).exists()
        user_eh_atendente_chamado = self.eh_atendente(user)
        user_eh_atendente_equipe = user in self.get_atendentes_equipe_atendimento()
        user_eh_responsavel_equipe = user in self.get_responsaveis_equipe_atendimento()

        servico_permite_anexos = self.servico.permite_anexos if self.servico else False

        pode_visualizar = (
            user_eh_superuser
            or user_eh_pessoa_envolvida
            or user_eh_responsavel_atendimento
            or user_eh_admin_central
            or user_eh_grupo_auditor
            or user_estah_tarefas_chamado
        )

        pode_adicionar_comentario = (
            user_eh_superuser or user_eh_pessoa_envolvida or user_eh_responsavel_atendimento or user_eh_admin_central or user_estah_tarefas_chamado
        ) and self.status in [
            StatusChamado.get_status_em_atendimento(),
            StatusChamado.get_status_suspenso(),
        ]

        pode_adicionar_nota_interna = pode_visualizar and (user_eh_atendente_chamado or user_eh_atendente_equipe or user_eh_responsavel_equipe)

        pode_adicionar_anexo = pode_visualizar and (
            servico_permite_anexos
            and self.status not in [StatusChamado.get_status_resolvido(), StatusChamado.get_status_fechado(), StatusChamado.get_status_cancelado()]
        )

        return {
            'pode_visualizar': pode_visualizar,
            'pode_adicionar_comentario': pode_adicionar_comentario,
            'pode_adicionar_nota_interna': pode_adicionar_nota_interna,
            'pode_adicionar_anexo': pode_adicionar_anexo,
        }

    def pode_visualizar(self, user):
        return self.get_permissoes(user)['pode_visualizar']

    def pode_adicionar_comentario(self, user):
        return self.get_permissoes(user)['pode_adicionar_comentario']

    def pode_adicionar_nota_interna(self, user):
        return self.get_permissoes(user)['pode_adicionar_nota_interna']

    def pode_adicionar_anexo(self, user):
        return self.get_permissoes(user)['pode_adicionar_anexo']

    @staticmethod
    def get_chamados_por_servico(servico: Servico, status: list[int] | None = None):
        chamados = (
            Chamado.objects.select_related(
                'servico',
            )
            .prefetch_related(
                'historicostatus_set',
            )
            .filter(servico=servico)
        )
        if status:
            chamados = chamados.filter(status__in=status)
        return chamados

    @staticmethod
    def get_attrs_estatisticas() -> list[str]:
        return [
            'total_tempo_resposta',
            'total_tempo_atendimento',
            'total_tempo_suspensao',
            'total_tempo_gasto',
            'estatisticas_pendentes',
        ]

    def atualizar_estatisticas(self, bloquear_db_obj: bool = True, salvar: bool = True):
        """Calcula e atualiza as estatísticas.
        `bloquear_db_obj`: Permite bloquear ou não o objeto a
        nível de banco de dados para fins de gerenciar atualizações
        concorrentes.
        `salvar`: Permite salvar ou não as estatísticas.
        """

        # O modelo HistoricoStatus possui 3 informações já salvas sobre
        # tempos dos chamados (em segundos):
        # * tempo_atendimento (status de atendimento para resolvido)
        # * tempo_resposta (status de aberto/reaberto para atendimento)
        # * tempo_suspensao (status de suspenso para atendimento)

        with transaction.atomic():
            if bloquear_db_obj:
                # Bloqueia o chamado com select_for_update
                # para fins de gerenciar atualizações concorrentes.
                chamado = Chamado.objects.select_for_update().get(pk=self.id)
            else:
                chamado = self

            estatisticas: Chamado.ChamadoEstatisticas = {
                'total_tempo_resposta': 0.0,
                'total_tempo_atendimento': 0.0,
                'total_tempo_suspensao': 0.0,
                'total_tempo_gasto': 0.0,
            }

            ##
            # Processa o histórico do chamado.

            hist_chamado = chamado.historicostatus_set.all()
            for h in hist_chamado:
                estatisticas['total_tempo_resposta'] += h.tempo_resposta or 0.0
                estatisticas['total_tempo_atendimento'] += h.tempo_atendimento or 0.0
                estatisticas['total_tempo_suspensao'] += h.tempo_suspensao or 0.0

            estatisticas['total_tempo_gasto'] = estatisticas['total_tempo_resposta'] + estatisticas['total_tempo_atendimento']

            # Atualiza as estatísticas.
            chamado.total_tempo_resposta = estatisticas['total_tempo_resposta']
            chamado.total_tempo_atendimento = estatisticas['total_tempo_atendimento']
            chamado.total_tempo_suspensao = estatisticas['total_tempo_suspensao']
            chamado.total_tempo_gasto = estatisticas['total_tempo_gasto']
            chamado.estatisticas_pendentes = False
            if bloquear_db_obj:
                # Atualiza as estatísticas da instância atual.
                self.total_tempo_resposta = chamado.total_tempo_resposta
                self.total_tempo_atendimento = chamado.total_tempo_atendimento
                self.total_tempo_suspensao = chamado.total_tempo_suspensao
                self.total_tempo_gasto = chamado.total_tempo_gasto
                self.estatisticas_pendentes = chamado.estatisticas_pendentes

            # Salva as estatísticas (se for o caso).
            if salvar:
                chamado.save()

    def usar_estatisticas_atualizadas(self, bloquear_db_obj: bool = True, salvar: bool = True) -> bool:
        """Valida as estatísticas atuais. Serão atualizadas se for necessário.

        Se houver necessidade de atualização:
        * `bloquear_db_obj`: Permite bloquear ou não o objeto a
        nível de banco de dados para fins de gerenciar atualizações
        concorrentes.
        * `salvar`: Permite salvar ou não as estatísticas.

        Retorna True se as estatísticas foram atualizadas.
        """
        estatisticas_foram_atualizadas = False
        if self.estatisticas_pendentes:
            self.atualizar_estatisticas(bloquear_db_obj=bloquear_db_obj, salvar=salvar)
            estatisticas_foram_atualizadas = True
        return estatisticas_foram_atualizadas

    @property
    def estatisticas(self) -> ChamadoEstatisticas:
        """Mais um meio de acessar as estatísticas."""
        return {
            'total_tempo_resposta': self.total_tempo_resposta,
            'total_tempo_atendimento': self.total_tempo_atendimento,
            'total_tempo_suspensao': self.total_tempo_suspensao,
            'total_tempo_gasto': self.total_tempo_gasto,
        }

    def anular_estatisticas(self):
        """Seta as estatísticas como pendentes."""
        self.estatisticas_pendentes = True
        self.save()


class HistoricoStatus(models.ModelPlus):
    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    data_hora = models.DateTimeField(auto_now_add=True)
    usuario = models.ForeignKeyPlus(User, verbose_name='Usuário')
    status = models.IntegerField(choices=StatusChamado.STATUS)
    bases_conhecimento = models.ManyToManyFieldPlus(
        BaseConhecimento, related_name='basesconhecimento_set', blank=True, verbose_name='Bases de Conhecimento utilizadas'
    )
    comunicacao = models.OneToOneField('centralservicos.Comunicacao', verbose_name='Comunicação', null=True, on_delete=models.CASCADE)
    tempo_atendimento = models.FloatField(
        'Tempo de Atendimento', null=True, help_text='Tempo de Atendimento entre as situações Em Atendimento e Resolvido.'
    )
    tempo_resposta = models.FloatField('Tempo de Resposta', null=True, help_text='Tempo de Resposta entre as situações Aberto e Em Atendimento.')
    tempo_suspensao = models.FloatField('Tempo de Suspensão', null=True, help_text='Tempo de Suspensão entre as situações Suspenso e Em Atendimento.')

    def aberto(
        self,
    ):
        return self.status == StatusChamado.get_status_aberto() or self.status == StatusChamado.get_status_reaberto()

    def get_tempo_atendimento(self):
        if self.tempo_atendimento:
            return timedelta(seconds=self.tempo_atendimento)

    def get_tempo_resposta(self):
        if self.tempo_resposta:
            return timedelta(seconds=self.tempo_resposta)

    def get_tempo_suspensao(self):
        if self.tempo_suspensao:
            return timedelta(seconds=self.tempo_suspensao)

    def __str__(self):
        return f'{self.pk}: {self.chamado} - {StatusChamado.STATUS[self.status]}'

    class Meta:
        ordering = ['data_hora']
        verbose_name = 'Histórico do Situações'
        verbose_name_plural = 'Históricos do Situações'

    def get_bases_conhecimento(self):
        lista = ['<ul>']
        for base_conhecimento in self.bases_conhecimento.all():
            lista.append(f'<li>{base_conhecimento.titulo}</li>')
        lista.append('</ul>')
        return '\n'.join(lista)

    def atualizar_bases_conhecimento(self, bases_conhecimento=None):
        for base in bases_conhecimento:
            self.bases_conhecimento.add(base)


class ChamadoAnexo(models.ModelPlus):
    descricao = models.CharFieldPlus(
        'Descrição', max_length=80, null=False, blank=False, help_text='Informe uma descrição resumida sobre o arquivo anexado'
    )
    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    anexo = models.FileFieldPlus(
        max_length=255,
        upload_to='upload/chamado/anexos/',
        can_view='can_view_anexo',
        validators=[FileExtensionValidator(allowed_extensions=['xlsx', 'xls', 'csv', 'docx', 'doc', 'pdf', 'jpg', 'jpeg', 'png'])],
    )
    anexado_em = models.DateTimeField(auto_now_add=True, null=False, blank=False)
    anexado_por = models.ForeignKeyPlus(User, verbose_name='Anexado Por', null=False, blank=False)

    def __str__(self):
        return f'Chamado {self.chamado.id} - Anexo ({self.id}): {self.descricao}'

    def can_view_anexo(self, user):
        return user.is_authenticated and (self.chamado.pode_visualizar(user))

    class Meta:
        ordering = ['anexado_em']
        verbose_name = 'Anexo'
        verbose_name_plural = 'Anexos'


class Comunicacao(models.ModelPlus):
    TIPO_COMENTARIO = 'comentario'
    TIPO_NOTA_INTERNA = 'nota_interna'

    TIPO_CHOICES = ((TIPO_COMENTARIO, 'Comentário'), (TIPO_NOTA_INTERNA, 'Nota Interna'))

    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    texto = models.TextField('Texto', null=False, blank=False)
    tipo = models.CharFieldPlus('Tipo', max_length=15, choices=TIPO_CHOICES, null=False, blank=False)
    data_hora = models.DateTimeField(default=datetime.now, null=False, blank=False)
    remetente = models.ForeignKeyPlus(User, verbose_name='Remetente', null=False, blank=False)
    usuarios_citados = models.ManyToManyFieldPlus(User, related_name='usuarios_citados_set', verbose_name='Usuários Citados')
    mensagem_automatica = models.BooleanField('Mensagem Automática?', default=False)
    bases_conhecimento = models.ManyToManyFieldPlus(
        BaseConhecimento,
        related_name='comunicacao_basesconhecimento_set',
        blank=True,
        verbose_name='Bases de Conhecimento',
        help_text='Sugestão de bases de conhecimento para este chamado',
    )
    desconsiderada_em = models.DateTimeField(
        'Desconsiderada Em', null=True, blank=True, help_text='Informe a partir de quando esta comunicação foi desconsiderada.'
    )
    # Nome legado: no domínio atual, `escondida_em` registra quando o comentário foi arquivado pelo autor.
    escondida_em = models.DateTimeField('Escondida Em', null=True, blank=True, help_text='Informe a partir de quando esta comunicação foi escondida.')

    def save(self, *args, **kwargs):
        if not self.pk:
            suspender_notificacao = kwargs.pop('suspender_notificacao', False)
            if suspender_notificacao is False:
                if self.tipo == Comunicacao.TIPO_COMENTARIO:
                    Notificar.comentario(self)
                else:
                    Notificar.nota_interna_ao_atendente(self)
        return super().save(*args, **kwargs)

    def __str__(self):
        return f'Chamado {self.chamado.id} - Comunicação {self.texto}'

    class Meta:
        ordering = ['data_hora']
        verbose_name = 'Comunicação'
        verbose_name_plural = 'Comunicações'


def envia_emails_usuarios_citados(sender, **kwargs):
    instance = kwargs.pop('instance', None)
    action = kwargs.pop('action', None)
    if action == 'post_add':
        Notificar.nota_interna_ao_atendente(instance, citar_outros_usuarios=True)


m2m_changed.connect(envia_emails_usuarios_citados, sender=Comunicacao.usuarios_citados.through)


class Autorizacao(models.ModelPlus):
    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    texto = models.TextField('Texto', null=False, blank=False)
    enviado_em = models.DateTimeField('Enviado em', auto_now_add=True, null=False, blank=False)
    enviado_por = models.ForeignKeyPlus(User, related_name='enviado_por_set', verbose_name='Enviado por', null=True, blank=True)
    enviado_para = models.ForeignKeyPlus(User, related_name='enviado_para_set', verbose_name='Enviado para', null=False, blank=False)
    autorizado_em = models.DateTimeField('Autorizado em', null=True, blank=True)
    autorizado_por = models.ForeignKeyPlus(User, related_name='autorizado_por_set', verbose_name='Autorizado por', null=True, blank=True)

    def __str__(self):
        return f'Chamado {self.chamado.id} - Autorização {self.id}'

    class Meta:
        ordering = ['enviado_em']
        verbose_name = 'Autorização'
        verbose_name_plural = 'Autorizações'


class AtendimentoAtribuicao(models.ModelPlus):
    TIPO_CHAMADO_ESCALADO = 'CHAMADO_ESCALADO'
    TIPO_CHAMADO_RETORNADO = 'CHAMADO_RETORNADO'
    TIPO_NOVA_ATRIBUICAO = 'NOVA_ATRIBUICAO'

    TIPO_CHOICES = (
        (TIPO_CHAMADO_ESCALADO, 'Chamado Escalado'),
        (TIPO_CHAMADO_RETORNADO, 'Chamado Retornado'),
        (TIPO_NOVA_ATRIBUICAO, 'Chamado com Nova Atribuição'),
    )
    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    grupo_atendimento = models.ForeignKeyPlus(GrupoAtendimento, verbose_name='Grupo de Atendimento')
    atribuido_em = models.DateTimeField('Atribuído em', null=True, blank=True)
    atribuido_por = models.ForeignKeyPlus(User, related_name='atribuido_por_set', verbose_name='Atribuído por', null=True, blank=True)
    atribuido_para = models.ForeignKeyPlus(User, related_name='atribuido_para_set', verbose_name='Atribuído para', null=True, blank=True)
    cancelado_em = models.DateTimeField('Cancelado em', null=True, blank=True)
    cancelado_por = models.ForeignKeyPlus(User, related_name='cancelado_por_set', verbose_name='Cancelado por', null=True, blank=True)
    justificativa_cancelamento = models.TextField(verbose_name='Justificativa', null=True, blank=True)
    tipo_justificativa = models.CharFieldPlus('Tipo', max_length=25, choices=TIPO_CHOICES, null=True)

    def __str__(self):
        return f'Chamado {self.chamado.id} - Atendimento {self.id}'

    class Meta:
        ordering = ['-atribuido_em']
        verbose_name = 'Atribuição'
        verbose_name_plural = 'Atribuições'


class Monitoramento(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=100, help_text='Informe um título para este monitoramento.')
    grupos = models.ManyToManyFieldPlus(GrupoAtendimento, verbose_name='Grupo de Atendimento')
    token = models.CharFieldPlus('Token', max_length=32, unique=True, help_text='Token gerado automaticamente pelo sistema.')
    cadastrado_por = models.ForeignKeyPlus(User, related_name='cadastrado_por_set', verbose_name='Cadastrado Por')
    cadastrado_em = models.DateTimeField(auto_now_add=True)
    organizar_por_tipo = models.BooleanField('Organizar por Tipo', default=True)

    def get_absolute_url(self):
        return f'/centralservicos/monitoramento/{self.token}/'

    def __str__(self):
        return f'{self.titulo} - {self.token}'

    class Meta:
        ordering = ['titulo']
        verbose_name = 'Monitoramento'
        verbose_name_plural = 'Monitoramentos'


class RespostaPadrao(models.ModelPlus):
    atendente = models.ForeignKeyPlus(User, related_name='resposta_atendente_set', verbose_name='Atendente')
    status = models.IntegerField(choices=StatusChamado.STATUS, default=StatusChamado.EM_ATENDIMENTO, null=True, blank=True)
    texto = models.TextField('Texto Padrão')

    def __str__(self):
        return f'{self.texto}'

    class Meta:
        ordering = ['texto']
        verbose_name = 'Resposta Padrão'
        verbose_name_plural = 'Respostas Padrão'


class GrupoInteressado(models.ModelPlus):
    titulo = models.CharFieldPlus('Título', max_length=100, help_text='Informe um título para este grupo de interessados.')
    grupo_atendimento = models.ForeignKeyPlus(GrupoAtendimento, verbose_name='Grupo de Atendimento')
    interessados = models.ManyToManyFieldPlus(User, verbose_name='Interessados', related_name='grupointeressados_set')

    def __str__(self):
        return f'{self.titulo}'

    class Meta:
        ordering = ['titulo']
        verbose_name = 'Grupo de Interessados'
        verbose_name_plural = 'Grupos de Interessados'


class Tarefa(models.ModelPlus):
    """Representa o cadastro prévio de uma tarefa da central de serviços."""

    SEARCH_FIELDS = ['servico__nome', 'servico__texto_ajuda', 'titulo', 'descricao']

    EXT_COMBO_RELATED = {
        'select_related': ['servico'],
        'prefetch_related': [],
    }

    servico = models.ForeignKeyPlus(Servico, verbose_name='Serviço')
    titulo = models.CharFieldPlus('Título', max_length=100, help_text='Informe um título para esta tarefa.')
    descricao = models.TextField('Descrição', help_text='Informe uma descrição detalhada para esta tarefa.', null=True, blank=True)

    class Meta:
        verbose_name = 'Cadastro de Tarefa da Central de Serviços'
        verbose_name_plural = 'Cadastros de Tarefas da Central de Serviços'

    def __str__(self):
        return f'{self.titulo}'

    def get_ext_combo_template(self):
        return format_html('<h3 class="mb-0 pb-0">{} <small>{}</small></h3>', self.titulo, self.descricao or 'Nenhuma descrição.')

    @staticmethod
    def get_tarefas_escopo(user):
        user_eh_gestor_central_servicos = user.has_group('Gestor da Central de Serviços')
        user_eh_auditor = user.has_group('Auditor')
        if user_eh_auditor:
            return Tarefa.objects.all().order_by('titulo')
        if user_eh_gestor_central_servicos:
            minhas_areas_como_gestor = GestorAreaServico.minhas_areas(user)
            return Tarefa.get_tarefas_por_areas(minhas_areas_como_gestor)
        return Tarefa.objects.none()

    @staticmethod
    def get_tarefas_por_areas(areas: list[AreaAtuacao]):
        return Tarefa.objects.filter(servico__area__in=areas or []).order_by('titulo')

    @staticmethod
    def get_tarefas_por_servicos(servicos: list[Servico]):
        return Tarefa.objects.filter(servico__in=servicos or []).order_by('titulo')

    @staticmethod
    def pode_visualizar_cadastro_tarefas(user):
        user_eh_gestor_central_servicos = user.has_group('Gestor da Central de Serviços')
        user_eh_auditor = user.has_group('Auditor')
        return user_eh_gestor_central_servicos or user_eh_auditor

    @staticmethod
    def pode_adicionar(user: User):
        return user.has_group('Gestor da Central de Serviços')

    def pode_editar(self, user: User):
        return user.has_group('Gestor da Central de Serviços')

    def pode_excluir(self, user: User):
        return self.pode_editar(user) and not TarefaChamado.objects.filter(tarefa=self).exists()

    def get_historico_vinculacoes_a_chamados(self):
        return (
            TarefaChamado.objects.filter(tarefa=self)
            .annotate(data_hora_vinculacao=models.Min('tarefachamadohistorico__data_hora'))
            .order_by('-data_hora_vinculacao')
        )

    def get_absolute_url(self):
        return f'/centralservicos/visualizar_tarefa/{self.id}/'


class TarefaChamado(models.ModelPlus):
    """Representa uma tarefa da central de serviços vinculada a um chamado."""

    SEARCH_FIELDS = ['tarefa__servico__nome', 'tarefa__servico__texto_ajuda', 'tarefa__titulo', 'tarefa__descricao']

    SITUACAO_ABERTA = 'aberta'
    SITUACAO_EM_ANDAMENTO = 'em_andamento'
    SITUACAO_SUSPENSA = 'suspensa'
    SITUACAO_FINALIZADA = 'finalizada'
    SITUACAO_CANCELADA = 'cancelada'

    SITUACAO_CHOICES = (
        (SITUACAO_ABERTA, 'Aberta'),
        (SITUACAO_EM_ANDAMENTO, 'Em Andamento'),
        (SITUACAO_SUSPENSA, 'Suspensa'),
        (SITUACAO_FINALIZADA, 'Finalizada'),
        (SITUACAO_CANCELADA, 'Cancelada'),
    )

    tarefa = models.ForeignKeyPlus(Tarefa, verbose_name='Tarefa')
    chamado = models.ForeignKeyPlus(Chamado, verbose_name='Chamado')
    responsavel = models.ForeignKeyPlus(User, verbose_name='Responsável')
    situacao = models.CharFieldPlus('Situação', max_length=20, choices=SITUACAO_CHOICES, default=SITUACAO_ABERTA)

    class Meta:
        verbose_name = 'Tarefa da Central de Serviços'
        verbose_name_plural = 'Tarefas da Central de Serviços'

    def __str__(self):
        return f'{self.tarefa} | {self.get_situacao_display()} | {self.responsavel}'

    def get_absolute_url(self):
        return f'/centralservicos/visualizar_tarefa_chamado/{self.id}/'

    @staticmethod
    def get_tarefas_vinculadas(servico=None, chamado=None, user_responsavel=None, situacoes=None):
        """obtém tarefas vinculadas"""
        tarefas = TarefaChamado.objects.all().order_by('-id')
        any_filter = False
        if servico:
            # tarefas vinculadas a um serviço por meio de chamados
            tarefas = tarefas.filter(chamado__servico=servico)
            any_filter = True
        if chamado:
            # tarefas vinculadas a um chamado
            tarefas = tarefas.filter(chamado=chamado)
            any_filter = True
        if user_responsavel:
            # tarefas vinculadas a um responsável
            tarefas = tarefas.filter(responsavel=user_responsavel)
            any_filter = True
        if situacoes:
            # tarefas vinculadas por situações
            tarefas = tarefas.filter(situacao__in=situacoes)
            any_filter = True
        return tarefas if any_filter else TarefaChamado.objects.none()

    @staticmethod
    def pode_visualizar_tarefas_vinculadas(user):
        user_eh_gestor_central_servicos = user.has_group('Gestor da Central de Serviços')
        user_eh_atendente_central_servicos = user.has_group('Atendente da Central de Serviços')
        user_eh_auditor = user.has_group('Auditor')
        eh_ou_foi_responsavel_por_tarefa = TarefaChamadoHistorico.get_historicos_tarefas(user_responsavel=user).exists()
        return user_eh_gestor_central_servicos or user_eh_atendente_central_servicos or user_eh_auditor or eh_ou_foi_responsavel_por_tarefa

    @staticmethod
    def get_tarefas_vinculadas_escopo(user):
        qs = TarefaChamado.objects.all()
        user_eh_gestor_central_servicos = user.has_group('Gestor da Central de Serviços')
        user_eh_auditor = user.has_group('Auditor')
        if user_eh_gestor_central_servicos or user_eh_auditor:
            # o gestor ou aditor tem acesso à todas as tarefas
            return qs
        # por padrão, o usuário tem acesso:
        # 1) às tarefas dos grupos de atendimento nos quais atende
        # 2) às tarefas que é ou foi responsável
        return qs.filter(
            models.Q(chamado__atendimentoatribuicao__grupo_atendimento__in=GrupoAtendimento.meus_grupos(user))
            | models.Q(tarefachamadohistorico__responsavel=user)
        ).distinct()

    @staticmethod
    def get_tarefas_vinculadas_ativas_filtro() -> dict:
        return {
            'situacao__in': [
                TarefaChamado.SITUACAO_ABERTA,
                TarefaChamado.SITUACAO_EM_ANDAMENTO,
                TarefaChamado.SITUACAO_SUSPENSA,
            ]
        }

    @staticmethod
    def get_tarefas_vinculadas_ativas(user):
        return TarefaChamado.get_tarefas_vinculadas(
            user_responsavel=user, situacoes=TarefaChamado.get_tarefas_vinculadas_ativas_filtro().get('situacao__in', [])
        )

    @staticmethod
    def get_tarefas_vinculadas_ativas_por_situacao(user) -> dict:
        tarefas_vinculadas_ativas = TarefaChamado.get_tarefas_vinculadas_ativas(user)
        # {situação: [descrição da situação, queryset de tarefas na situação], ...}
        return {
            situacao: [TarefaChamado(situacao=situacao).get_situacao_display(), tarefas_vinculadas_ativas.filter(situacao=situacao)]
            for situacao in TarefaChamado.get_tarefas_vinculadas_ativas_filtro().get('situacao__in', [])
        }

    def pode_visualizar(self, user: User):
        eh_ou_foi_responsavel_pela_tarefa = (
            user == self.responsavel or TarefaChamadoHistorico.get_historicos_tarefas(tarefa_chamado=self, user_responsavel=user).exists()
        )
        return eh_ou_foi_responsavel_pela_tarefa

    def pode_atualizar_situacao(self, user: User) -> bool:
        """o responsável pela tarefa ou o atendente do chamado (#17794: responsável que saiu do grupo)"""
        return user == self.responsavel or self.chamado.eh_atendente(user)

    def get_historico_alteracoes(self):
        return (
            TarefaChamadoHistorico.objects.select_related(
                'responsavel',
                'tarefa_chamado',
            )
            .filter(tarefa_chamado=self)
            .order_by('-data_hora')
        )

    @staticmethod
    def vincular_tarefa(
        usuario_vinculou: User,
        tarefa: Tarefa,
        chamado: Chamado,
        responsavel: User,
        situacao: str,
    ):
        with transaction.atomic():
            tc = TarefaChamado.objects.create(
                tarefa=tarefa,
                chamado=chamado,
                responsavel=responsavel,
                situacao=situacao,
            )
            TarefaChamadoHistorico.objects.create(
                tarefa_chamado=tc,
                responsavel=responsavel,
                situacao=situacao,
            )
            tc.notificar_alteracao_historico(usuario_vinculou)

    def alterar_tarefa(
        self,
        usuario_alterou: User,
        responsavel: User,
        situacao: str,
    ):
        with transaction.atomic():
            self.responsavel = responsavel
            self.situacao = situacao
            self.save()
            TarefaChamadoHistorico.objects.create(
                tarefa_chamado=self,
                responsavel=responsavel,
                situacao=situacao,
            )
            self.notificar_alteracao_historico(usuario_alterou)

    def notificar_alteracao_historico(self, usuario_alterou: User):
        chamado_permissoes = self.chamado.get_permissoes(usuario_alterou)
        if chamado_permissoes['pode_adicionar_comentario']:
            com = Comunicacao(
                mensagem_automatica=True,
                chamado=self.chamado,
                remetente=usuario_alterou,
                tipo=Comunicacao.TIPO_COMENTARIO,
                texto=f"""Por {usuario_alterou}: tarefa {f'{self.get_situacao_display()}'.lower()} ({self.tarefa.titulo}).
                Responsável: {self.responsavel}.""",
            )
            com.save(suspender_notificacao=True)
            if self.responsavel != usuario_alterou:
                com.usuarios_citados.set([self.responsavel])


class TarefaChamadoHistorico(models.ModelPlus):
    """Representa o histórico de atualizações de uma tarefa interna da central de serviços vinculada a um chamado."""

    tarefa_chamado = models.ForeignKeyPlus(TarefaChamado, verbose_name='Tarefa de Chamado')
    responsavel = models.ForeignKeyPlus(User, verbose_name='Responsável')
    situacao = models.CharFieldPlus('Situação', max_length=20, choices=TarefaChamado.SITUACAO_CHOICES)
    data_hora = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = 'Histórico de Tarefa de Chamado'
        verbose_name_plural = 'Históricos de Tarefas de Chamados'

    @staticmethod
    def get_historicos_tarefas(tarefa_chamado=None, servico=None, chamado=None, user_responsavel=None, situacoes=None):
        """obtém históricos de tarefas"""
        historicos = TarefaChamadoHistorico.objects.all().order_by('-id')
        any_filter = False
        if tarefa_chamado:
            # históricos por tarefa vinculada
            historicos = historicos.filter(tarefa_chamado=tarefa_chamado)
            any_filter = True
        if servico:
            # históricos por serviço
            historicos = historicos.filter(tarefa_chamado__chamado__servico=servico)
            any_filter = True
        if chamado:
            # históricos por chamado
            historicos = historicos.filter(tarefa_chamado__chamado=chamado)
            any_filter = True
        if user_responsavel:
            # históricos por responsável
            historicos = historicos.filter(responsavel=user_responsavel)
            any_filter = True
        if situacoes:
            # históricos por situações
            historicos = historicos.filter(situacao__in=situacoes)
            any_filter = True
        return historicos if any_filter else TarefaChamadoHistorico.objects.none()
