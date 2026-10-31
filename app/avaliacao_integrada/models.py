import datetime
import inspect
import json
import logging
import math
import sys
from typing import Any, TypedDict

from django.conf import settings
from django.contrib.auth.models import AnonymousUser, Group
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import MultipleObjectsReturned, ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import F, Q, QuerySet, UniqueConstraint, Value
from django.db.models.aggregates import Max
from django.db.models.fields.json import KeyTextTransform
from django.db.models.functions import Cast, Coalesce, Replace
from django.db.models.signals import m2m_changed
from django.utils.encoding import force_bytes, force_str
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode

import djtools.middleware.threadlocals as tl
from avaliacao_integrada.exceptions import AvaliacaoDataCleanupError
from comum.models import Ano, Ocupacao, User
from contratos.models import MaoDeObra
from djtools.db import models
from djtools.forms.widgets import CheckboxSelectMultiplePlus
from djtools.utils import retira_acentos, send_mail
from documento_eletronico.models import DocumentoTexto
from edu.models import (
    Aluno,
    CursoCampus,
    Diario,
    FormaIngresso,
    MatriculaDiario,
    MatriculaPeriodo,
    Modalidade,
    ProfessorDiario,
    SituacaoMatricula,
    Turma,
)
from estagios.models import PraticaProfissional
from rh.managers import ServidorQueryset
from rh.models import AreaVinculacao, Servidor, Setor, Situacao, UnidadeOrganizacional

logger = logging.getLogger(__name__)


class ProcessarResult(TypedDict):
    percentual: int  # percentual ignorando automáticos e opcionais
    percentual_geral: int  # percentual considerando todos os indicadores aplicáveis
    finalizado: bool  # status após o processamento


# Definindo um tipo para os Sociedade Civil
SociedadeCivilQuerySet = QuerySet[Aluno] | QuerySet[MaoDeObra]
# Definindo um tipo para os respondentes
RespondenteQuerySet = ServidorQueryset[Servidor] | QuerySet[Aluno] | QuerySet[MaoDeObra]


def tl_get_user():
    try:
        user = tl.get_user()
        if isinstance(user, AnonymousUser):
            return None
        return user
    except Exception:
        return None


def obter_ordem(modelo, **filtro):
    qs = modelo.objects.all()
    if filtro:
        qs = modelo.objects.filter(**filtro)
    qs_aggregate = qs.aggregate(Max('ordem'))
    return (qs_aggregate.get('ordem__max', 0) or 0) + 1


class Eixo(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')
    texto_ajuda = models.TextField('Texto de Ajuda', blank=True, null=True)
    ordem = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = 'Eixo'
        verbose_name_plural = 'Eixos'
        ordering = ('ordem',)

    def __str__(self):
        return self.descricao

    def save(self, *args, **kwargs):
        if not self.ordem:
            self.ordem = obter_ordem(self.__class__)
        super().save(*args, **kwargs)


class Dimensao(models.ModelPlus):
    eixo = models.ForeignKeyPlus(Eixo, verbose_name='Eixo', on_delete=models.PROTECT)
    descricao = models.CharFieldPlus('Descrição')
    texto_ajuda = models.TextField('Texto de Ajuda', blank=True, null=True)
    ordem = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = 'Dimensão'
        verbose_name_plural = 'Dimensões'
        ordering = ('eixo', 'ordem')

    def __str__(self):
        return self.descricao

    def save(self, *args, **kwargs):
        if not self.ordem:
            self.ordem = obter_ordem(self.__class__, eixo=self.eixo)
        super().save(*args, **kwargs)


class Macroprocesso(models.ModelPlus):
    dimensao = models.ForeignKeyPlus(Dimensao, verbose_name='Dimensão', on_delete=models.PROTECT)
    descricao = models.CharFieldPlus('Descrição')
    texto_ajuda = models.TextField('Texto de Ajuda', blank=True, null=True)
    ordem = models.IntegerField(blank=True, null=True)

    class Meta:
        verbose_name = 'Macroprocesso'
        verbose_name_plural = 'Macroprocessos'
        ordering = ('dimensao__eixo', 'dimensao', 'ordem')

    def __str__(self):
        return self.descricao

    def save(self, *args, **kwargs):
        if not self.ordem:
            self.ordem = obter_ordem(self.__class__, dimensao=self.dimensao)
        super().save(*args, **kwargs)


class TipoAvaliacao(models.ModelPlus):
    AVALIACAO_PLANEJAMENTO_PDI = 10

    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Avaliação'
        verbose_name_plural = 'Tipos de Avaliação'
        ordering = ('descricao',)

    def __str__(self):
        return self.descricao


class Segmento(models.ModelPlus):
    CPA_CENTRAL = 1
    CPA_CAMPUS = 2
    GESTOR = 3
    DOCENTE = 6
    TECNICO = 4
    ETEP = 5
    ESTUDANTE = 7
    DESLIGADO = 8
    ALUNO_EGRESSO = 9
    PAIS = 10
    EMPRESA_PRESTADORA_SERVICO = 11
    OUTRO_SOCIEDADE_CIVIL = 12
    PROFISSIONAL_PRESTADOR_SERVICO = 13
    SUPERVISOR_ESTAGIO = 14

    TIPO_RESPONDENTE_EXTERNO_CHOICE = [
        [PAIS, 'Pais e/ou Responsável'],
        [ALUNO_EGRESSO, 'Aluno Egresso'],
        [EMPRESA_PRESTADORA_SERVICO, 'Empresa Prestadora de Serviço'],
        [PROFISSIONAL_PRESTADOR_SERVICO, 'Profissional Prestador de Serviço'],
        [SUPERVISOR_ESTAGIO, 'Supervisor de Estágio'],
        [OUTRO_SOCIEDADE_CIVIL, 'Demais segmentos da sociedade civil'],
        # [DESLIGADO, 'Evadidos/Jubilados']
    ]

    TIPO_PUBLICO_INTERNO = 'PI'
    TIPO_SOCIEDADE_CIVIL = 'PE'
    TIPO_CHOICES = [[TIPO_PUBLICO_INTERNO, 'Público Interno'], [TIPO_SOCIEDADE_CIVIL, 'Sociedade Civil (Público Externo)']]

    SERVIDORES = [GESTOR, DOCENTE, TECNICO, ETEP, CPA_CENTRAL, CPA_CAMPUS]
    ALUNOS = [ESTUDANTE, ALUNO_EGRESSO]
    SOCIEDADE_CIVIL = [
        PAIS,
        ALUNO_EGRESSO,
        EMPRESA_PRESTADORA_SERVICO,
        PROFISSIONAL_PRESTADOR_SERVICO,
        SUPERVISOR_ESTAGIO,
        OUTRO_SOCIEDADE_CIVIL,
        DESLIGADO,
    ]

    LISTA_EMAIL = SERVIDORES + ALUNOS + SOCIEDADE_CIVIL

    descricao = models.CharFieldPlus('Descrição')
    tipo = models.CharField(choices=TIPO_CHOICES, max_length=2)

    class Meta:
        verbose_name = 'Segmento Respondente'
        verbose_name_plural = 'Segmentos Respondentes'
        ordering = ('id',)

    def __str__(self):
        return self.descricao

    @classmethod
    def get_segmento_externo_display(cls, tipo: int) -> str:
        return dict(Segmento.TIPO_RESPONDENTE_EXTERNO_CHOICE).get(tipo)


class EscalaLikert(models.ModelPlus):
    ESCALA_PADRAO = 5
    nome = models.CharField(max_length=100)
    ativo = models.BooleanField('Ativo', default=True)
    # opcoes = models.ManyToManyFieldPlus('EscalaLikertNivel', verbose_name='Opções de resposta')

    class Meta:
        verbose_name = 'Escala Likert'
        verbose_name_plural = 'Escalas Likert'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/avaliacao_integrada/escalalikert/{self.pk:d}/'

    def em_uso(self):
        return Indicador.objects.filter(escala=self).exists()

    def get_niveis(self):
        return self.niveis_escala.all()

    def get_choice(self):
        choice = []
        for nivel in self.get_niveis():
            choice.append((f'{nivel.id}___{nivel.nivel}', str(nivel)))
        return choice


class NivelEscalaLikert(models.ModelPlus):
    CRITERIO_CONCORDO = 'A'
    CRITERIO_CONCORDO_PARCIALMENTE = 'B'
    CRITERIO_DISCORDO_PARCIALMENTE = 'C'
    CRITERIO_DISCORDO = 'D'
    CRITERIO_DESCONHECO = 'E'
    CRITERIO_NAO_SE_APLICA = '-'

    TIPO_CRITERIO_CHOICES = [
        [CRITERIO_CONCORDO, CRITERIO_CONCORDO],  # 'Concordo'
        [CRITERIO_CONCORDO_PARCIALMENTE, CRITERIO_CONCORDO_PARCIALMENTE],  # 'Concordo Parcialmente'
        [CRITERIO_DISCORDO_PARCIALMENTE, CRITERIO_DISCORDO_PARCIALMENTE],  # 'Discordo Parcialmente'
        [CRITERIO_DISCORDO, CRITERIO_DISCORDO],  # 'Discordo'
        [CRITERIO_DESCONHECO, CRITERIO_DESCONHECO],  # 'Desconheço'
        [CRITERIO_NAO_SE_APLICA, 'Não se aplica'],
    ]
    escala = models.ForeignKey(EscalaLikert, on_delete=models.CASCADE, related_name='niveis_escala')
    nivel = models.IntegerFieldPlus('Nível')
    descricao = models.CharFieldPlus('Descrição', max_length=50)
    emoji = models.CharFieldPlus('Emoji', max_length=10, null=True, blank=True)
    tipo_criterio = models.CharField('Critério Padronização Gráficos', choices=TIPO_CRITERIO_CHOICES, max_length=1)

    class Meta:
        verbose_name = 'Nível da escala Likert'
        verbose_name_plural = 'Níveis da escala Likert'

    def __str__(self):
        if self.emoji:
            return f'{self.emoji} {self.descricao}'
        return self.descricao


class Indicador(models.ModelPlus):
    TEXTO_CURTO = 1
    TEXTO_LONGO = 2
    NUMERO_INTEIRO = 3
    NUMERO_DECIMAL = 4
    UNICA_ESCOLHA = 5
    MULTIPLA_ESCOLHA = 6
    CONJUNTO_VARIAVEIS = 7
    ESCALA_LIKERT = 99

    TIPO_CHOICES = [
        [TEXTO_CURTO, 'Texto Curto'],
        [TEXTO_LONGO, 'Texto Longo'],
        [NUMERO_INTEIRO, 'Número Inteiro'],
        [NUMERO_DECIMAL, 'Número Decimal'],
        [UNICA_ESCOLHA, 'Única Escolha'],
        [MULTIPLA_ESCOLHA, 'Múltipla Escolha'],
        [CONJUNTO_VARIAVEIS, 'Conjunto de Variáveis'],
        [ESCALA_LIKERT, 'Escala Likert'],
    ]

    INDICADORES_AUTOCALCULADOS = {
        'Unidade de vinculação': 'get_unidade_vinculacao',
        'Modalidade de vinculação': 'get_modalidade_vinculacao',
        'Curso de vinculação': 'get_curso_vinculacao',
        'Ano de ingresso': 'get_ano_ingresso_curso',
        'Forma de ingresso': 'get_forma_ingresso_curso',
        'Série/Período no curso': 'get_serie_periodo_curso',
        'Área de atuação': 'get_area_atuacao_servidor',
        'Cargo': 'get_cargo_servidor',
        'Função': 'get_funcao_servidor',
        'Regime de trabalho - servidor': 'get_regime_trabalho_servidor',
        'Tipo de contrato': 'get_forma_contratacao_servidor',
        'Data de nascimento': 'get_data_nascimento',
        'Tipo de ação afirmativa': 'get_tipo_acao_afirmativa',
    }

    # Dados gerais
    macroprocesso = models.ForeignKeyPlus(Macroprocesso, verbose_name='Macroprocessos', on_delete=models.PROTECT)
    nome = models.CharFieldPlus('Denominação do Indicador', width=500)
    aspecto = models.CharFieldPlus('Critério de Análise', width=500)
    texto_ajuda = models.TextField('Texto de Ajuda', blank=True, null=True)
    subsidio_para = models.ManyToManyFieldPlus(TipoAvaliacao, verbose_name='Subsídio p/ Avaliações')
    anos_referencia = models.ManyToManyField(Ano, verbose_name='Anos de Referência')
    ordem = models.IntegerField(blank=True, null=True)
    em_uso = models.BooleanField('Em uso', default=True)
    tipo = models.IntegerField(choices=[[0, 'Qualitativo'], [1, 'Quantitativo']], default=0)
    automatico = models.BooleanField('Autocalculado', default=False)
    obrigatorio = models.BooleanField('Resposta Obrigatória', default=True)
    gestor_responde_como_docente = models.BooleanField('Gestor responde também como Docente', default=False)

    # Detalhamento
    segmentos = models.ManyToManyFieldPlus(Segmento, verbose_name='Segmentos Respondentes')
    areas_vinculacao = models.ManyToManyFieldPlus(AreaVinculacao, verbose_name='Áreas')
    modalidades = models.ManyToManyFieldPlus(Modalidade, verbose_name='Modalidades')
    periodo_curso = models.IntegerField(
        'Período Mínimo',
        help_text='Período mínimo do estudante no curso',
        choices=[[1, 1], [2, 2], [3, 3], [4, 4], [5, 5], [6, 6], [7, 7], [8, 8]],
        default=1,
    )

    uos = models.ManyToManyFieldPlus(UnidadeOrganizacional, verbose_name='Campi')

    # Unidades relacionadas
    envolve_reitoria = models.BooleanField('Reitoria', default=True)
    envolve_campus_ead = models.BooleanField('Campus EAD', default=True)
    envolve_campus_produtivos = models.BooleanField('Campus com Unidade Produtiva', default=True)
    envolve_campus_nao_produtivos = models.BooleanField('Campus sem Unidade Produtiva', default=True)

    # Tipo
    tipo_resposta = models.IntegerField(choices=TIPO_CHOICES, verbose_name='Tipo')
    valor_minimo = models.IntegerField('Valor Mínimo', null=True, blank=True)
    valor_maximo = models.IntegerField('Valor Máximo', null=True, blank=True)
    formula = models.CharFieldPlus('Fórmula', null=True, blank=True)

    escala = models.ForeignKey(EscalaLikert, verbose_name='Escala Likert', null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        verbose_name = 'Indicador'
        verbose_name_plural = 'Indicadores'
        ordering = ('macroprocesso__dimensao__eixo__ordem', 'macroprocesso__dimensao__ordem', 'macroprocesso__ordem', 'ordem')
        permissions = (('pode_replicar_indicador', 'Pode replicar indicador de outra avaliação'),)

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/avaliacao_integrada/indicador/{self.pk}/'

    def get_form_field(self, respondente=None, objeto=None):
        from djtools import forms as fields

        lista = []
        if self.tipo_resposta == Indicador.CONJUNTO_VARIAVEIS:
            for variavel in self.variavel_set.all():
                lista.append(variavel.get_form_field(respondente, objeto))
        else:
            if self.escala:
                field = fields.ChoiceField(label=self.aspecto, required=False, choices=self.escala.get_choice(), widget=fields.RadioSelect())
            elif self.tipo_resposta == Indicador.TEXTO_CURTO:
                field = fields.CharField(label=self.aspecto, required=False)
            elif self.tipo_resposta == Indicador.TEXTO_LONGO:
                field = fields.CharField(label=self.aspecto, required=False, widget=fields.Textarea())
            elif self.tipo_resposta == Indicador.NUMERO_INTEIRO:
                field = fields.IntegerField(label=self.aspecto, required=self.obrigatorio, min_value=self.valor_minimo, max_value=self.valor_maximo)
            elif self.tipo_resposta == Indicador.NUMERO_DECIMAL:
                field = fields.DecimalField(label=self.aspecto, required=False)
            elif self.tipo_resposta == Indicador.UNICA_ESCOLHA:
                choices = [[x, x] for x in self.opcaoresposta_set.all()]
                field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices, widget=fields.RadioSelect())
            elif self.tipo_resposta == Indicador.MULTIPLA_ESCOLHA:
                choices = [[x, x] for x in self.opcaoresposta_set.all()]
                field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
            if self.nome in Indicador.INDICADORES_AUTOCALCULADOS:
                if (
                    self.nome
                    not in [
                        'Unidade de vinculação',
                        'Modalidade de vinculação',
                        'Curso de vinculação',
                        'Data de nascimento',
                        'Ano de ingresso',
                        'Forma de ingresso',
                    ]
                    or not respondente
                ):
                    if respondente:
                        field.initial = getattr(respondente, Indicador.INDICADORES_AUTOCALCULADOS[self.nome])()
                    field.widget.attrs['readonly'] = True
                else:
                    # Unidade de Vinculação
                    if self.nome == 'Unidade de vinculação' and respondente.segmento_id in [
                        Segmento.PAIS,
                        Segmento.DESLIGADO,
                        Segmento.OUTRO_SOCIEDADE_CIVIL,
                    ]:
                        choices = [[x, x] for x in UnidadeOrganizacional.objects.suap().all()]
                        field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices)
                    elif self.nome == 'Unidade de vinculação' and respondente.segmento_id == Segmento.EMPRESA_PRESTADORA_SERVICO:
                        choices = [[x, x] for x in UnidadeOrganizacional.objects.suap().all()]
                        field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
                    elif self.nome == 'Unidade de vinculação' and respondente.segmento_id == Segmento.ESTUDANTE:
                        field.initial = respondente.get_unidade_diretoria_aluno()
                        field.widget.attrs['readonly'] = True
                    elif self.nome == 'Unidade de vinculação' and respondente.segmento_id in Segmento.SERVIDORES:
                        field.initial = respondente.get_unidade_atuacao_servidor()
                        field.widget.attrs['readonly'] = True

                    # Modalidade de Vinculação
                    if self.nome == 'Modalidade de vinculação' and respondente.segmento_id in [Segmento.PAIS, Segmento.DESLIGADO]:
                        if respondente.segmento_id == Segmento.PAIS:
                            choices = [[x, x] for x in Modalidade.objects.filter(descricao='Técnico Integrado')]
                        else:
                            choices = [
                                [x, x]
                                for x in Modalidade.objects.exclude(
                                    descricao__in=[
                                        'FIC',
                                        'Proeja FIC Fundamental',
                                        'Aperfeiçoamento',
                                        'Doutorado',
                                        'Especialização',
                                        'Engenharia',
                                        'Mestrado',
                                    ]
                                )
                            ]
                        field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices)
                    elif self.nome == 'Modalidade de vinculação' and respondente.segmento_id == Segmento.EMPRESA_PRESTADORA_SERVICO:
                        choices = [
                            [x, x]
                            for x in Modalidade.objects.exclude(
                                descricao__in=[
                                    'FIC',
                                    'Proeja FIC Fundamental',
                                    'Aperfeiçoamento',
                                    'Doutorado',
                                    'Especialização',
                                    'Engenharia',
                                    'Mestrado',
                                ]
                            )
                        ]
                        field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
                    elif self.nome == 'Modalidade de vinculação' and respondente.segmento_id in Segmento.ALUNOS:
                        field.initial = respondente.get_modalidade_vinculacao()
                        field.widget.attrs['readonly'] = True
                    elif self.nome == 'Modalidade de vinculação' and respondente.segmento_id not in [
                        Segmento.PAIS,
                        Segmento.DESLIGADO,
                        Segmento.OUTRO_SOCIEDADE_CIVIL,
                        Segmento.EMPRESA_PRESTADORA_SERVICO,
                        Segmento.ESTUDANTE,
                    ]:
                        choices = [
                            [x, x]
                            for x in Modalidade.objects.filter(cursocampus__ativo=True, cursocampus__diretoria__setor__uo=respondente.uo).distinct()
                        ]
                        field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
                        field.initial = (
                            Modalidade.objects.filter(cursocampus__ativo=True, cursocampus__diretoria__setor__uo=respondente.uo)
                            .distinct()
                            .values_list('descricao', flat=True)
                        )

                    # Curso de Vinculação
                    if self.nome == 'Curso de vinculação' and respondente.segmento_id in [Segmento.PAIS, Segmento.DESLIGADO]:
                        if respondente.segmento_id == Segmento.PAIS:
                            choices = [
                                [x.descricao_historico, x.descricao_historico]
                                for x in CursoCampus.objects.filter(ativo=True, modalidade__descricao='Técnico Integrado')
                                .order_by('descricao_historico')
                                .distinct()
                            ]
                        else:
                            # choices = [[x.descricao_historico, x.descricao_historico] for x in CursoCampus.objects.filter(ativo=True)]
                            choices = [
                                [x.descricao_historico, x.descricao_historico]
                                for x in CursoCampus.objects.filter(ativo=True)
                                .exclude(
                                    modalidade__descricao__in=[
                                        'FIC',
                                        'Proeja FIC Fundamental',
                                        'Aperfeiçoamento',
                                        'Doutorado',
                                        'Especialização',
                                        'Engenharia',
                                        'Mestrado',
                                    ]
                                )
                                .order_by('descricao_historico')
                                .distinct()
                            ]
                        field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices)
                    elif self.nome == 'Curso de vinculação' and respondente.segmento_id == Segmento.EMPRESA_PRESTADORA_SERVICO:
                        choices = [
                            [x.descricao_historico, x.descricao_historico]
                            for x in CursoCampus.objects.filter(ativo=True)
                            .exclude(
                                modalidade__descricao__in=[
                                    'FIC',
                                    'Proeja FIC Fundamental',
                                    'Aperfeiçoamento',
                                    'Doutorado',
                                    'Especialização',
                                    'Engenharia',
                                    'Mestrado',
                                ]
                            )
                            .order_by('descricao_historico')
                            .distinct()
                        ]
                        field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
                    elif self.nome == 'Curso de vinculação' and respondente.segmento_id == Segmento.ESTUDANTE:
                        field.initial = respondente.get_curso_vinculacao()
                        field.widget.attrs['readonly'] = True
                    elif self.nome == 'Curso de vinculação' and respondente.segmento_id not in [
                        Segmento.PAIS,
                        Segmento.DESLIGADO,
                        Segmento.OUTRO_SOCIEDADE_CIVIL,
                        Segmento.EMPRESA_PRESTADORA_SERVICO,
                        Segmento.ESTUDANTE,
                    ]:
                        choices = [
                            [x.descricao_historico, x.descricao_historico]
                            for x in CursoCampus.objects.filter(diretoria__setor__uo=respondente.uo, ativo=True)
                            .order_by('descricao_historico')
                            .distinct()
                        ]
                        field = fields.MultipleChoiceField(label=self.aspecto, required=False, choices=choices, widget=CheckboxSelectMultiplePlus())
                        field.initial = (
                            CursoCampus.objects.filter(diretoria__setor__uo=respondente.uo, ativo=True)
                            .order_by('descricao_historico')
                            .distinct()
                            .values_list('descricao_historico', flat=True)
                        )

                    # Data de Nascimento
                    if self.nome == 'Data de nascimento':
                        field = fields.DateFieldPlus(label=self.aspecto, required=False)
                        if respondente.segmento_id not in [
                            Segmento.PAIS,
                            Segmento.DESLIGADO,
                            Segmento.OUTRO_SOCIEDADE_CIVIL,
                            Segmento.EMPRESA_PRESTADORA_SERVICO,
                        ]:
                            field.initial = getattr(respondente, Indicador.INDICADORES_AUTOCALCULADOS[self.nome])()
                            field.widget.attrs['readonly'] = True

                    # Ano de Ingresso
                    if self.nome == 'Ano de ingresso' and respondente.segmento_id == Segmento.ESTUDANTE:
                        field.initial = respondente.get_ano_ingresso_curso()
                        field.widget.attrs['readonly'] = True
                    elif self.nome == 'Ano de ingresso' and respondente.segmento_id != Segmento.ESTUDANTE:
                        choices = [[x.ano, x.ano] for x in Ano.objects.all()]
                        field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices)

                    # Forma de Ingresso
                    if self.nome == 'Forma de ingresso' and respondente.segmento_id == Segmento.ESTUDANTE:
                        field.initial = respondente.get_forma_ingresso_curso()
                        field.widget.attrs['readonly'] = True
                    elif self.nome == 'Forma de ingresso' and respondente.segmento_id != Segmento.ESTUDANTE:
                        choices = [[x.descricao, x.descricao] for x in FormaIngresso.objects.all()]
                        field = fields.ChoiceField(label=self.aspecto, required=False, choices=choices)
            field.name = Resposta.to_identificador(self.id, respondente and respondente.id or 'field', 0, objeto)
            lista.append(field)
        return lista

    def save(self, *args, **kwargs):
        if not self.ordem:
            self.ordem = obter_ordem(self.__class__, macroprocesso=self.macroprocesso)
        super().save(*args, **kwargs)

    def filtrar_respondentes(self, respondentes):
        pass


class Iterador(models.ModelPlus):
    CURSO = 'edu.CursoCampus'
    MODALIDADE = 'edu.Modalidade'
    PROFESSOR = 'edu.Professor'
    TURMA = 'edu.Turma'

    OBJETOS_CHOICES = [[CURSO, 'Curso'], [MODALIDADE, 'Modalidade'], [PROFESSOR, 'Professor'], [TURMA, 'Turma']]

    indicador = models.ForeignKeyPlus(Indicador, verbose_name='Indicador', on_delete=models.CASCADE)
    segmento = models.ForeignKeyPlus(Segmento, verbose_name='Segmento', on_delete=models.CASCADE)
    objeto = models.CharFieldPlus(choices=OBJETOS_CHOICES)

    class Meta:
        verbose_name = 'Iterador'
        verbose_name_plural = 'Iteradores'
        ordering = ('id',)

    def __str__(self):
        return f'{self.pk}'


class Variavel(models.ModelPlus):
    TIPO_CHOICES = [[Indicador.NUMERO_INTEIRO, 'Número Inteiro'], [Indicador.NUMERO_DECIMAL, 'Número Decimal']]

    indicador = models.ForeignKeyPlus(Indicador, verbose_name='Indicador', on_delete=models.PROTECT)
    sigla = models.CharFieldPlus('Sigla')
    nome = models.CharFieldPlus('Nome')
    tipo = models.IntegerField(choices=TIPO_CHOICES)
    valor_minimo = models.IntegerField('Valor Mínimo', null=True, blank=True)
    valor_maximo = models.IntegerField('Valor Máximo', null=True, blank=True)

    class Meta:
        verbose_name = 'Variável'
        verbose_name_plural = 'Variáveis'
        ordering = ('id',)

    def __str__(self):
        return self.sigla

    def get_form_field(self, respondente=None, objeto=None):
        from djtools.forms import fields

        # O rótulo é o nome da variável: `aspecto` é campo de `Indicador`, não de `Variavel`,
        # e derrubava a montagem do questionário no tipo "Conjunto de Variáveis".
        if self.tipo == Indicador.NUMERO_INTEIRO:
            field = fields.IntegerField(
                label=self.nome, required=self.indicador.obrigatorio, min_value=self.indicador.valor_minimo, max_value=self.indicador.valor_maximo
            )
        elif self.tipo == Indicador.NUMERO_DECIMAL:
            field = fields.DecimalField(label=self.nome, required=self.indicador.obrigatorio)

        field.name = Resposta.to_identificador(self.indicador.id, respondente.id, self.id, objeto)
        return field


class OpcaoResposta(models.ModelPlus):
    indicador = models.ForeignKeyPlus(Indicador, verbose_name='Indicador', on_delete=models.CASCADE)
    descricao = models.CharFieldPlus('Descrição')

    def __str__(self):
        return self.descricao

    class Meta:
        verbose_name = 'Opção de Resposta'
        verbose_name_plural = 'Opções de Resposta'
        ordering = ('id',)


class ComissaoCPA(models.ModelPlus):
    CPA_CENTRAL = 1
    CPA_LOCAL = 2

    TIPO_CHOICES = [
        [CPA_CENTRAL, 'CPA Central'],
        [CPA_LOCAL, 'CPA Local'],
    ]
    nome = models.CharField(max_length=100)
    tipo = models.IntegerField('Tipo', choices=TIPO_CHOICES)
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor Associado', on_delete=models.PROTECT)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', on_delete=models.PROTECT)
    data_portaria = models.DateField(verbose_name='Data da Portaria')
    documento_portaria = models.ForeignKeyPlus(DocumentoTexto, verbose_name='Documento da portaria', null=True, blank=True, on_delete=models.PROTECT)
    vinculos_membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros', blank=True)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Comissão CPA'
        verbose_name_plural = 'Comissões CPA'

        constraints = [
            UniqueConstraint(name='unique_cpa_central_ativa', fields=['tipo', 'ativo', 'uo'], condition=models.Q(ativo=True)),
        ]

    def __str__(self):
        return f'{self.nome} (Setor associado {self.setor})'

    def clean(self):
        comissao_cpa_central_existe = False
        comissao_cpa_local_existe = False

        if self.tipo == ComissaoCPA.CPA_CENTRAL and self.ativo:
            comissao_cpa_central_existe = ComissaoCPA.objects.filter(tipo=ComissaoCPA.CPA_CENTRAL, ativo=True).exclude(id=self.pk).exists()
        elif self.ativo:
            comissao_cpa_local_existe = (
                ComissaoCPA.objects.filter(tipo=ComissaoCPA.CPA_LOCAL, ativo=True, setor__uo=self.setor.uo).exclude(id=self.pk).exists()
            )

        if comissao_cpa_central_existe:
            raise ValidationError('Comissão CPA Central já existe. Para adicionar uma nova, deve-se antes desativar a anterior')
        elif comissao_cpa_local_existe:
            raise ValidationError(
                f'Comissão CPA Local para o campus {self.setor.uo.sigla} - {self.setor.uo.nome} já existe. Para adicionar uma nova, deve-se antes desativar a anterior'
            )

        return super().clean()

    def save(self, *args, **kwargs):
        self.uo = self.setor.uo
        super().save(*args, **kwargs)

    @transaction.atomic
    def delete(self):
        pk_set = set(self.vinculos_membros.values_list('id', flat=True))
        self.membros_atualizar_grupos_de_usuarios(instance=self, action='post_remove', pk_set=pk_set)
        super().delete()

    @classmethod
    def membros_atualizar_grupos_de_usuarios(cls, instance, action, pk_set):
        if instance.tipo == instance.CPA_CENTRAL:
            grupo = Group.objects.get(name='cpa_central')
        else:
            grupo = Group.objects.get(name='cpa_campus')

        for id_vinculo in pk_set:
            usuario = User.objects.filter(vinculo__id=id_vinculo)[0]
            if instance.ativo and action == 'post_add':
                usuario.groups.add(grupo)
            if (not instance.ativo and action == 'post_add') or action == 'post_remove':
                usuario_existe_em_outra_comissao_cpa_ativa = (
                    ComissaoCPA.objects.filter(tipo=instance.tipo, ativo=True, vinculos_membros__user=usuario).exclude(id=instance.id).exists()
                )
                if not usuario_existe_em_outra_comissao_cpa_ativa:
                    usuario.groups.remove(grupo)

    def get_membros(self):
        string = ''
        for membro in self.vinculos_membros.all().order_by('pessoa__nome'):
            string = string + '<p>' + membro.pessoa.nome + '</p>'

        return string


def adiciona_ou_remover_membros_no_grupo(sender, instance, action, pk_set, **kwargs):
    ComissaoCPA.membros_atualizar_grupos_de_usuarios(instance, action, pk_set)


m2m_changed.connect(adiciona_ou_remover_membros_no_grupo, sender=ComissaoCPA.vinculos_membros.through)


class Avaliacao(models.ModelPlus):
    # Dados gerais
    tipos = models.ManyToManyField(TipoAvaliacao, verbose_name='Tipo')
    ano = models.ForeignKeyPlus(Ano, verbose_name='Ano de Referência', on_delete=models.PROTECT)
    periodo = models.IntegerField('Período Letivo', choices=[[1, 1], [2, 2]], null=True, blank=True)

    nome = models.CharFieldPlus('Nome')

    descricao = models.TextField('Descrição')
    texto_instrucoes_servidores = models.TextField(
        'Texto com Instruções', null=True, blank=True, help_text='Texto "cabeçalho" com instruções para o público servidores.'
    )
    texto_instrucoes_alunos = models.TextField(
        'Texto com Instruções', null=True, blank=True, help_text='Texto "cabeçalho" com instruções para o público alunos.'
    )
    texto_instrucoes_sociedade_civil = models.TextField(
        'Texto com Instruções', null=True, blank=True, help_text='Texto "cabeçalho" com instruções para o público sociedade civil.'
    )

    data_inicio = models.DateField(verbose_name='Data de Início')
    data_termino = models.DateField(verbose_name='Data de Término')

    # Detalhamento
    areas_vinculacao = models.ManyToManyFieldPlus(AreaVinculacao, verbose_name='Áreas de Vinculação')
    segmentos = models.ManyToManyFieldPlus(Segmento, verbose_name='Segmentos Respondentes')

    modalidades = models.ManyToManyFieldPlus(Modalidade, verbose_name='Modalidades', related_name='avaliacao_modalidades')
    uos = models.ManyToManyFieldPlus(UnidadeOrganizacional, verbose_name='Campi')

    respondente_prestador_ocupacoes = models.ManyToManyFieldPlus(
        Ocupacao,
        verbose_name='Ocupações do prestador participante da pesquisa',
        help_text='Indique as ocupações dos profissionais prestadores de serviço são são o público-alvo desta pesquisa.',
    )

    respondentes_pais_modalidades = models.ManyToManyFieldPlus(
        Modalidade,
        verbose_name='Modalidades dos cursos participantes da pesquisa',
        help_text='Indique os cursos aos quais pertencem os alunos cujos pais e/ou responsáveis são o público-alvo desta pesquisa.',
    )

    # Unidades relacionadas
    envolve_reitoria = models.BooleanField('Reitoria', default=True)
    envolve_campus_ead = models.BooleanField('Campus EAD', default=True)
    envolve_campus_produtivos = models.BooleanField('Campus com Unidade Produtiva', default=True)
    envolve_campus_nao_produtivos = models.BooleanField('Campus sem Unidade Produtiva', default=True)

    # Token utilizado na Avaliação Externa (Pais, Empresas, Sociedade Civil e Desligados)
    # TODO: campo em desuso (24.09.2024), mantindo por hora por questões de compatibilidade com dados históricos.
    token = models.CharFieldPlus('Token de Acesso', null=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cadastrado_por = models.CurrentUserField(related_name='avaliacao_cadastrado_por')

    class Meta:
        verbose_name = 'Avaliação'
        verbose_name_plural = 'Avaliações'
        ordering = ('id',)
        permissions = (
            ('pode_gerar_publico_alvo', 'Pode gerar público-alvo sem exclusão'),
            ('pode_reprocessar_publico_alvo_com_exclusao', 'Pode gerar público-alvo com exclusão'),
            ('pode_ver_relatorios', 'Pode visualizar relatórios da avaliação'),
            ('pode_exportar_respostas', 'Pode exportar respostas da avaliação'),
            ('pode_ver_relatorio_indicadores', 'Pode visualizar relatório de indicadores'),
            ('pode_visualizar_questionario_terceiros', 'Pode visualizar questionário de terceiros'),
            ('pode_enviar_email_lembrete', 'Pode enviar email de convites para o público da avaliação'),
            ('pode_ver_dados_identificaveis', 'Pode ver dados identificáveis dos respondentes'),
            ('pode_replicar_indicador', 'Pode replicar indicador de outra avaliação'),
            ('pode_ver_quadro_resumo', 'Pode ver quadro resumo de indicadores'),
        )

    def __str__(self):
        return self.nome

    def pode_ver_quadro_resumo(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_ver_quadro_resumo'))

    def pode_visualizar_questionario_terceiros(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_visualizar_questionario_terceiros'))

    def pode_ver_dados_identificaveis(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_ver_dados_identificaveis'))

    def pode_enviar_email_lembrete(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_enviar_email_lembrete'))

    def pode_gerar_publico_alvo(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_gerar_publico_alvo'))

    def pode_reprocessar_publico_alvo_com_exclusao(self, user: User = None) -> bool:
        if not user:
            user = tl_get_user()
        return bool(user.has_perm('avaliacao_integrada.pode_reprocessar_publico_alvo_com_exclusao'))

    def obter_respondentes(self, identificacao: str, segmento_pk: int | None = None, field_name: str | None = None) -> QuerySet[Respondente]:
        """
        Filtra os respondentes desta avaliação em que a identificação fornecida existe em um dos seguintes campos:
        - `dados_usuario_externo__matricula`
        - `dados_usuario_externo__cpf`
        - `user__username`
        - `user__email`

        Parâmetros:
        - identificacao (str): A identificação a ser usada na filtragem, como matrícula, CPF, e-mail ou username.
        - segmento_pk (int, opcional): O ID do segmento para filtrar respondentes pertencentes a um segmento específico.
        - field_name (str, opcional): O nome do campo nos dados de usuário externo a ser usado para filtrar a identificação.

        Retorna:
        - QuerySet: Um QuerySet filtrado de objetos `Respondente` correspondentes à avaliação atual.

        Regras de filtragem:
        1. Se `segmento_pk` for fornecido, os respondentes são filtrados por segmento.
        2. Se `field_name` for fornecido, a função aplica o filtro baseado no campo especificado nos dados do usuário externo.
        3. Se `field_name` não for fornecido, a função verifica se a identificação corresponde a um dos campos predefinidos:
            - dados_usuario_externo__matricula
            - dados_usuario_externo__cpf
            - dados_usuario_externo__email
            - user__username
            - user__email
        """

        # Filtra os respondentes da avaliação atual
        respondentes_qs = Respondente.objects.filter(avaliacao=self)

        # Filtra por segmento se segmento_pk for fornecido
        if segmento_pk:
            respondentes_qs = respondentes_qs.filter(segmento=segmento_pk)

        # Aplica filtro com base no field_name, se fornecido
        if field_name:
            filter_criteria = {field_name: identificacao}
            respondentes_qs = respondentes_qs.filter(**filter_criteria)

            logger.debug(f'> identificacao: {identificacao}, segmento_pk: {segmento_pk}, field_name: {field_name}')
            if logger.getEffectiveLevel() == logging.DEBUG:
                respondentes = respondentes_qs.values_list('id', flat=True)
                logger.debug(f'> Respondentes, total: {respondentes_qs.count()}, ids: {list(respondentes)}')

            return respondentes_qs

        # Aplica filtro padrão baseado em vários campos se field_name não for fornecido
        return respondentes_qs.filter(
            Q(dados_usuario_externo__matricula=identificacao)
            | Q(dados_usuario_externo__cpf=identificacao)
            | Q(dados_usuario_externo__email=identificacao)
            | Q(user__username=identificacao)
            | Q(user__email=identificacao)
        )

    def obter_respondentes_sociedade_civil(self, dados: dict) -> QuerySet[Respondente]:
        respondente_id = dados.get('respondente_id')
        if respondente_id:
            return self.obter_respondentes(identificacao=respondente_id, segmento_pk=None, field_name='id')

        respondente_qs_filter_email = Respondente.objects.none()

        email = dados.get('dados_usuario_externo', {}).get('email')
        if email:
            respondente_qs_filter_email = self.obter_respondentes(identificacao=email, segmento_pk=None, field_name='dados_usuario_externo__email')

        fields_names = ('matricula', 'cpf', 'cnpj', 'email')
        for field_name in fields_names:
            field_value = dados.get('dados_usuario_externo', {}).get(field_name)
            if field_value:
                qs = self.obter_respondentes(identificacao=field_value, segmento_pk=None, field_name=f'dados_usuario_externo__{field_name}')
                respondentes_qs = qs | respondente_qs_filter_email
                return respondentes_qs
        return Respondente.objects.none()

    def get_segmentos_choices(self, tipo):
        choices = []
        for id, descricao in self.segmentos.filter(tipo=tipo).values_list('id', 'descricao'):
            choices.append((id, descricao))
        return choices

    def possui_segmento_sociedade_civil(self):
        return self.segmentos.filter(id__in=Segmento.SOCIEDADE_CIVIL).exists()

    def obter_servidores_sem_areas_vinculacao(self) -> ServidorQueryset:
        """
        Retornaos servidores de setores sem áreas de vinculação associadas.
        """
        if not self.areas_vinculacao.exists():
            return None

        qs_servidores = Servidor.objects.ativos()
        qs_servidores = qs_servidores.filter(setor__areas_vinculacao__isnull=True, eh_tecnico_administrativo=True)
        qs_servidores = qs_servidores.exclude(situacao__codigo__in=[Situacao.ATIVO_EM_OUTRO_ORGAO, Situacao.CEDIDO_REQUISITADO])

        vl_servidores = qs_servidores.values(
            'pessoa_fisica__nome',
            'matricula',
            'eh_tecnico_administrativo',
            'eh_docente',
            'setor__id',
            'setor__sigla',
            'setor__nome',
            'setor__uo__nome',
        )
        return vl_servidores

    def __logging_servidor_matricula(self, qs_servidores: ServidorQueryset[Servidor], mensagem: str) -> None:
        args = sys.argv
        if '--matriculas' not in args:
            return
        matriculas = args[args.index('--matriculas') + 1 :]

        frame = inspect.currentframe().f_back

        if logger.getEffectiveLevel() == logging.DEBUG:
            msm_logger = f'{frame.f_lineno} {frame.f_code.co_name:36}]'
            for matricula in matriculas:
                if qs_servidores.filter(matricula=matricula).exists():
                    logger.debug(f'{msm_logger} [{matricula} SIM] - {mensagem}')
                else:
                    logger.debug(f'{msm_logger} [{matricula} NÃO] - {mensagem}:')

    def _obter_publicoalvo_alunos(self) -> QuerySet[Aluno]:
        logger.debug(f'>> Obtendo alunos, filtro: ativos cujo ano_letivo__ano__lte={self.ano.ano}')
        alunos = Aluno.ativos.filter(ano_letivo__ano__lte=self.ano.ano)

        if self.uos.exists():
            if logger.getEffectiveLevel() == logging.DEBUG:
                uols = list(self.uos.values_list('id', flat=True))
                logger.debug(f'>> Obtendo alunos, filtro: curso_campus__diretoria__setor__uo__in={uols}')
            alunos = alunos.filter(curso_campus__diretoria__setor__uo__in=self.uos.values_list('id', flat=True))

        if self.modalidades.exists():
            if logger.getEffectiveLevel() == logging.DEBUG:
                modalidades = list(self.modalidades.values_list('id', flat=True))
                logger.debug(f'>> Obtendo alunos, filtro: curso_campus__modalidade__in={modalidades}')
            alunos = alunos.filter(curso_campus__modalidade__in=self.modalidades.values_list('id', flat=True))

        if not self.envolve_reitoria:
            logger.debug(
                f'>> Obtendo alunos, filtro: flag envolve_reitoria -> curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_REITORIA}'
            )
            alunos = alunos.exclude(curso_campus__diretoria__setor__uo__tipo=UnidadeOrganizacional.TIPO_REITORIA)
        if not self.envolve_campus_ead:
            logger.debug(
                f'>> Obtendo alunos, filtro: flag envolve_campus_ead -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_EAD}'
            )
            alunos = alunos.exclude(curso_campus__diretoria__setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_EAD)
        if not self.envolve_campus_produtivos:
            logger.debug(
                f'>> Obtendo alunos, filtro: flag envolve_campus_produtivos -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO}'
            )
            alunos = alunos.exclude(curso_campus__diretoria__setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO)
        if not self.envolve_campus_nao_produtivos:
            logger.debug(
                f'>> Obtendo alunos, filtro: flag envolve_campus_nao_produtivos -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO}'
            )
            alunos = alunos.exclude(curso_campus__diretoria__setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO)
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo alunos, total obtido: {alunos.count()}')

        return alunos

    def _obter_publicoalvo_servidores(self) -> ServidorQueryset[Servidor]:
        logger.debug('>> Obtendo servidores, filtro: ativos')
        servidores = Servidor.objects.ativos()

        logger.debug('>> Obtendo servidores, filtro: técnico administrativos ou docentes')
        servidores = servidores.filter(eh_tecnico_administrativo=True) | servidores.filter(eh_docente=True)

        logger.debug('>> Obtendo servidores, filtro: exclui os servidores onde a situação é ATIVO_EM_OUTRO_ORGAO ou CEDIDO_REQUISITADO')
        servidores = servidores.exclude(situacao__codigo__in=[Situacao.ATIVO_EM_OUTRO_ORGAO, Situacao.CEDIDO_REQUISITADO])

        if self.areas_vinculacao.exists():
            if logger.getEffectiveLevel() == logging.DEBUG:
                areas_ids = list(self.areas_vinculacao.values_list('id', flat=True))
                logger.debug(f'>> Obtendo servidores, filtro: setor__areas_vinculacao__in={areas_ids}')
            servidores = servidores.filter(
                setor__areas_vinculacao__in=self.areas_vinculacao.values_list('id', flat=True), eh_tecnico_administrativo=True
            ) | servidores.filter(eh_docente=True)
            self.__logging_servidor_matricula(servidores, 'if self.areas_vinculacao.exists()')

        if self.uos.exists():
            if logger.getEffectiveLevel() == logging.DEBUG:
                uos_ids = list(self.uos.values_list('id', flat=True))
                logger.debug(f'>> Obtendo servidores, filtro: setor__uo__in={uos_ids}')
            servidores = servidores.filter(setor__uo__in=self.uos.values_list('id', flat=True))
            self.__logging_servidor_matricula(servidores, 'if self.uos.exists()')

        if not self.envolve_reitoria:
            logger.debug(
                f'>> Obtendo servidores, filtro: flag envolve_reitoria -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_REITORIA}'
            )
            servidores = servidores.exclude(setor__uo__tipo=UnidadeOrganizacional.TIPO_REITORIA)
            self.__logging_servidor_matricula(servidores, 'if not self.envolve_reitoria')

        if not self.envolve_campus_ead:
            logger.debug(
                f'>> Obtendo servidores, filtro: flag envolve_campus_ead -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_EAD}'
            )
            servidores = servidores.exclude(setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_EAD)
            self.__logging_servidor_matricula(servidores, 'if not self.envolve_campus_ead')

        if not self.envolve_campus_produtivos:
            logger.debug(
                f'>> Obtendo servidores, filtro: flag envolve_campus_produtivos -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO}'
            )
            servidores = servidores.exclude(setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO)
            self.__logging_servidor_matricula(servidores, 'if not self.envolve_campus_produtivos')

        if not self.envolve_campus_nao_produtivos:
            logger.debug(
                f'>> Obtendo servidores, filtro: flag envolve_campus_nao_produtivos -> '
                f'curso_campus__diretoria__setor__uo__tipo={UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO}'
            )
            servidores = servidores.exclude(setor__uo__tipo=UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO)
            self.__logging_servidor_matricula(servidores, 'if not self.envolve_campus_nao_produtivos')

        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo servidores, total obtido: {servidores.values("id").distinct().count()}')

        return servidores

    def _obter_publicoalvo_sociedade_civil(self) -> dict[int, SociedadeCivilQuerySet]:
        logger.debug('>> Obtendo sociedade civil')
        queries = {}

        # Público-alvo Pais e/ou responsáveis
        # Filtrar os alunos para obter os responsáveis
        logger.debug(f'>> Obtendo sociedade civil público-alvo Pais, filtro: alunos ativos cujo ano_letivo__ano__lte={self.ano.ano}')

        modalidades_ids = self.respondentes_pais_modalidades.values_list('id', flat=True)
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Pais, filtro: curso_campus__modalidade__in={modalidades_ids}')

        # Baseado em edu.forms.relatorios.RelatorioForm.processar
        qs = MatriculaPeriodo.objects.exclude(aluno__participanteturmaminicurso__turma__gerar_matricula=False)
        qs = qs.filter(aluno__curso_campus__modalidade__id__in=modalidades_ids)
        qs = qs.filter(aluno__curso_campus__ativo=True, matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO)

        qs_alunos_ids = qs.order_by('aluno__id').values_list('aluno__id', flat=True).distinct()
        alunos_qs = Aluno.objects.filter(id__in=qs_alunos_ids)

        queries[Segmento.PAIS] = alunos_qs
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Pais, total obtido: {alunos_qs.count()}')

        # Público-alvo Alunos Egresso
        # Todos os alunos com o atributo "situacao__ativo" definido como "falso" e cuja "situação da matrícula" esteja
        # entre ("CONCLUIDO", "EGRESSO" ou "FORMADO") e ano de conclusão
        CONCLUINTES = (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.EGRESSO, SituacaoMatricula.FORMADO)
        anos = Ano.obter_ultimos_n_anos(2).values_list('ano', flat=True)

        logger.debug(
            f'>> Obtendo sociedade civil público-alvo Aluno Egresso, filtro: '
            f'alunos inativos, cuja situação da matrícula consta as situações (CONCLUIDO, EGRESSO, FORMADO) '
            f'e ano de conclusão consta os anos ({list(anos)})'
        )

        alunos_egresso_qs = Aluno.objects.filter(situacao__ativo=False, situacao_id__in=CONCLUINTES, ano_conclusao__in=list(anos))
        queries[Segmento.ALUNO_EGRESSO] = alunos_egresso_qs
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Aluno Egresso, total obtido: {alunos_egresso_qs.count()}')

        if logger.getEffectiveLevel() == logging.DEBUG:
            ocupacoes_ids = list(self.respondente_prestador_ocupacoes.values_list('id', flat=True))
            logger.debug(
                f'>> Obtendo sociedade civil público-alvo Prestadores de serviço (terceirizados), filtro: '
                f'ativos, cpf NÃO é nulo (pessoa_fisica__cpf__isnull=False) e '
                f'ocupacaoprestador__ocupacao__in={ocupacoes_ids}'
            )

        # Público-alvo Prestadores de servico (terceirizados)
        # Todos os prestadores de serviços ativos (atributo ativo=True) que possuam CPF e tenham uma ocupação
        # e setor associado.
        prestadores_qs = MaoDeObra.objects.filter(desligamento__isnull=True, prestador_servico__pessoa_fisica__cpf__isnull=False)
        queries[Segmento.PROFISSIONAL_PRESTADOR_SERVICO] = prestadores_qs
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Prestadores de serviço (terceirizados), total obtido: {prestadores_qs.count()}')

        # Público-alvo empresas prestadoras de serviço
        empresas_qs = MaoDeObra.objects.filter(
            contrato__concluido=False, contrato__cancelado=False, contrato__vinculo_contratado__pessoa__pessoajuridica__ativo=True
        )
        queries[Segmento.EMPRESA_PRESTADORA_SERVICO] = empresas_qs
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Empresas prestadoras de serviços, total obtido: {empresas_qs.count()}')

        # Público-alvo Supervisor de Estágio
        # Obtém as informações referentes às práticas profissionais de estágios em andamento
        qs_supervisores_estagios = PraticaProfissional.objects.filter(
            tipo=PraticaProfissional.TIPO_ESTAGIO, data_fim__isnull=True, data_prevista_fim__gte=datetime.date.today()
        )
        queries[Segmento.SUPERVISOR_ESTAGIO] = qs_supervisores_estagios
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'>> Obtendo sociedade civil público-alvo Supervisores de Estágios, total obtido: {qs_supervisores_estagios.count()}')

        return queries

    def _filtrar_respondentes_por_segmento(
        self,
        segmento: Segmento,
        respondentes_servidores: ServidorQueryset[Servidor],
        respondentes_alunos: QuerySet[Aluno],
        respondentes_sociedade_civil: dict[int, SociedadeCivilQuerySet],
    ) -> dict[int, list[dict[str, str | int | None]]]:
        """
        Retorna os respondentes aptos para responder a avaliação relativo ao segmento informado.
        Respondentes é uma lista de dupla com os ids de usuário e unidade organizacional
        """

        logger.debug(f'>> Filtrar respondente pelo segmento {segmento.descricao}...')

        publico_alvo: dict[int, list[dict[str, str | int | None]]] = {}

        servidores_qs = respondentes_servidores
        alunos_qs = respondentes_alunos

        self.__logging_servidor_matricula(servidores_qs, '[INICIO]')

        # Gestores, Docentes e Técnicos Administrativos e ETEP
        if segmento.pk in [Segmento.GESTOR, Segmento.DOCENTE, Segmento.TECNICO, Segmento.ETEP]:
            logger.debug('>> Filtrar respondente [servidores] por segmento, filtro: segmento for um dos (GESTOR, DOCENTE, TECNICO, ETEP)')
            if segmento.pk == Segmento.GESTOR:
                logger.debug(
                    '>> Filtrar respondente [servidores], segmento [GESTOR], filtro: '
                    'servidorfuncaohistorico__funcao__excluido=False e '
                    'servidorfuncaohistorico__data_fim_funcao__isnull=True'
                )
                servidores_qs = servidores_qs.filter(
                    servidorfuncaohistorico__funcao__excluido=False, servidorfuncaohistorico__data_fim_funcao__isnull=True
                )
                self.__logging_servidor_matricula(servidores_qs, 'if segmento.pk == Segmento.GESTOR')

            elif segmento.pk == Segmento.DOCENTE:
                logger.debug('>> Filtrar respondente [servidores], segmento [DOCENTE], filtro: servidores docente')
                servidores_qs = servidores_qs.filter(eh_docente=True)
                self.__logging_servidor_matricula(servidores_qs, 'elif segmento.pk == Segmento.DOCENTE')

            elif segmento.pk == Segmento.TECNICO:
                # Cargos que fazem parte do segmento ETEP
                cargo_emprego_codigos = ('701079', '701058', '701060')
                areas_vinculacao_ensino = AreaVinculacao.objects.filter(descricao__unaccent__icontains='ensino')
                logger.debug(
                    '>> Filtrar respondente [servidores], segmento [TECNICO], filtro: '
                    'servidores técnicos administrativos, '
                    'exclui aqueles que possuem cargo emprego que fazem parte do segmento ETEP '
                    ' - PEDAGOGO-AREA (PCIFE) - 701058, '
                    ' - PSICOLOGO-AREA (PCIFE) - 701060, '
                    ' - TECNICO EM ASSUNTOS EDUCACIONAIS (PCIFE) - 701079 '
                    'exclui os setores onde áreas de vinculação estão relacionadas com a palavra "ensino"'
                )
                servidores_qs = servidores_qs.filter(eh_tecnico_administrativo=True).exclude(
                    cargo_emprego__codigo__in=cargo_emprego_codigos, setor__areas_vinculacao__in=areas_vinculacao_ensino
                )
                self.__logging_servidor_matricula(servidores_qs, 'elif segmento.pk == Segmento.TECNICO')

            elif segmento.pk == Segmento.ETEP:
                logger.debug(
                    '>> Filtrar respondente [servidores], segmento [ETEP], filtro: '
                    'aqueles que possuem cargo emprego que fazem parte do segmento ETEP '
                    ' - PEDAGOGO-AREA (PCIFE) - 701058, '
                    ' - PSICOLOGO-AREA (PCIFE) - 701060, '
                    ' - TECNICO EM ASSUNTOS EDUCACIONAIS (PCIFE) - 701079 '
                    'setores onde áreas de vinculação estão relacionadas com a palavra "ensino"'
                )

                servidores_qs = servidores_qs.filter(
                    cargo_emprego__codigo__in=['701079', '701058', '701060'],
                    setor__areas_vinculacao__in=AreaVinculacao.objects.filter(descricao__unaccent__icontains='ensino'),
                )
                self.__logging_servidor_matricula(servidores_qs, 'elif segmento.pk == Segmento.ETEP')

            servidores_qs_values = Respondente.obter_dados_publico_alvo(segmento.pk, qs=servidores_qs)
            publico_alvo[segmento.pk] = servidores_qs_values
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(f'>> Filtrar respondente [servidores], segmento [{segmento.pk}], total obtido: {servidores_qs_values.count()}')

        # Alunos Ativos
        elif segmento.pk == Segmento.ESTUDANTE:
            logger.debug('>> Filtrar respondente [alunos], segmento [ESTUDANTE]')
            alunos_qs_values = Respondente.obter_dados_publico_alvo(segmento.pk, qs=alunos_qs)
            publico_alvo[segmento.pk] = alunos_qs_values
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(f'>> Filtrar respondente [alunos], segmento [ESTUDANTE], total obtido: {alunos_qs_values.count()}')

        elif segmento.pk in Segmento.SOCIEDADE_CIVIL:
            logger.debug('>> Filtrar respondente [sociedade civil]')
            if respondentes_sociedade_civil.get(segmento.pk):
                any_qs = respondentes_sociedade_civil[segmento.pk]
                any_qs_values = Respondente.obter_dados_publico_alvo(segmento.pk, qs=any_qs)
                publico_alvo[segmento.pk] = any_qs_values

                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(f'>> Filtrar respondente [sociedade civil], segmento [{segmento.pk}], total obtido: {any_qs_values.count()}')
            else:
                logger.debug(f'>> Filtrar respondente [sociedade civil], segmento {segmento.pk} sem registros.')

        # Membros da CPA
        elif segmento.pk in (Segmento.CPA_CENTRAL, Segmento.CPA_CAMPUS):
            tipo_parse = {Segmento.CPA_CENTRAL: ComissaoCPA.CPA_CENTRAL, Segmento.CPA_CAMPUS: ComissaoCPA.CPA_LOCAL}
            tipo = tipo_parse[segmento.pk]
            comissaocpa_qs = ComissaoCPA.objects.filter(ativo=True, tipo=tipo)
            publico_alvo[segmento.pk] = Respondente.obter_dados_publico_alvo(segmento.pk, qs=comissaocpa_qs)
            if logger.getEffectiveLevel() == logging.DEBUG:
                total = comissaocpa_qs.values('vinculos_membros').count()
                logger.debug(f'>> Filtrar respondente [membros da CPA], segmento [segmento.pk], total obtido: {total}')

        return publico_alvo

    @transaction.atomic
    def _gerar_respondentes_segmento(
        self,
        publico_alvo_dados: list[dict[str, str | int | None]],
        segmento: Segmento,
        total_respondentes: int,
        contador_respondentes: int,
        task=None,
    ):
        for dados_respondente in publico_alvo_dados:
            contador_respondentes += 1

            user_id = dados_respondente.pop('user_id')
            uo_id = dados_respondente.pop('uo_id')

            # Público alvo está relacionado ao menos com uma UnidadeOrganizacional.
            # Público alvo sociedade civil "pais/responsáveis" e
            # "empresas prestadoras de serviços" não possuem usuário.
            if uo_id:
                percent_progress_respondentes = (contador_respondentes / total_respondentes) * 100.0

                logger.debug(f'>... [{percent_progress_respondentes:.2f}%]  Registrando respondente {contador_respondentes} de {total_respondentes}.')

                dados = {
                    'avaliacao': self,
                    'user_id': user_id,
                    'uo_id': uo_id,
                    'segmento': segmento,
                }
                dados_usuario_externo = None
                if segmento.pk in Segmento.SOCIEDADE_CIVIL:
                    dados_usuario_externo = dados_respondente

                try:
                    # Se user_id, os dados "dados_usuario_externo" não farão parte da busca e serão utilizados
                    # somente se o objeto respondente precisar ser criado.
                    # Se o user_id for None, então "dados_usuario_externo" passa a fazer parte da busca também.

                    if user_id:
                        _, created = Respondente.objects.get_or_create(**dados, defaults={'dados_usuario_externo': dados_usuario_externo})
                    else:
                        dados['dados_usuario_externo'] = dados_usuario_externo
                        _, created = Respondente.objects.get_or_create(**dados)

                    logger.debug(f'>... Registrado respondente (created={created}), parâmetros: {dados}')
                except MultipleObjectsReturned:
                    logger.debug('Detectado respondente em duplicidade. Iniciando tratamento...')

                    qs = Respondente.objects.filter(**dados).order_by('-finalizado', 'id')

                    # Verifica se existe avaliaçãoes (respondente) em duplicidade
                    # Se sim, preserva a primeira avaliação e exlui as demais.
                    respondente_id, finalizado = qs.values_list('id', 'finalizado')[0]
                    logger.debug(f'Mantendo respondente, id: {respondente_id}, finalizado: {finalizado}')

                    for respondente_id, finalizado in qs.values_list('id', 'finalizado')[1:]:
                        logger.debug(f'Excluindo resposta do respondente de id: {respondente_id}')
                        Resposta.objects.filter(respondente_id=respondente_id).delete()
                        logger.debug(f'excluindo respondente de id: {respondente_id}, finalizado: {finalizado}')
                        Respondente.objects.filter(id=respondente_id).delete()

                # Imprime a cada 1% completo. O passo tem piso 1: abaixo de cem respondentes
                # `total_respondentes // 100` é zero e a divisão estourava.
                passo = max(1, total_respondentes // 100)
                if contador_respondentes:
                    resto_divisao = contador_respondentes % passo
                    if resto_divisao == 0:
                        if task:
                            logger.debug(f'Atualiza taks - Progresso: {math.ceil(percent_progress_respondentes)}%')
                            task.start_progress(total_respondentes)
        return contador_respondentes

    def gerar_respondentes(self, excluir: bool = False, task=None) -> None:
        logger.debug(f'> Gerar respondentes, [argumento excluir={excluir}] ...')
        # servidores_qs = self._obter_publicoalvo_servidores()
        # alunos = self._obter_publicoalvo_alunos()
        # sociedade_civil: Dict[int, SociedadeCivilQuerySet] = self._obter_publicoalvo_sociedade_civil()

        publico_alvo = self.obter_publicoalvo()

        total_respondentes = 0
        total_segmentos = 0
        for lista_dados in publico_alvo.values():
            total_segmentos += 1
            total_respondentes += len(lista_dados)

        if task:
            task.start_progress(total_respondentes)

        try:
            with transaction.atomic():
                # Etapa 1: Exclui respondentes sem respostas
                logger.debug(f'Excluindo os respondentes da avaliação {self.id} que não têm respostas.')
                respondentes_sem_respostas_removidos = Respondente.objects.filter(avaliacao=self, resposta__isnull=True).delete()
                logger.debug(f'Total de respondentes sem respostas removidos: {respondentes_sem_respostas_removidos}')

                if excluir:
                    # Etapa 2: Se 'excluir' for True, remove todas as respostas
                    logger.debug(f'Excluindo todas as respostas relacionadas à avaliação {self.id}.')
                    respostas_removidas, _ = Resposta.objects.filter(respondente__avaliacao=self).delete()
                    logger.debug(f'Total de respostas removidas: {respostas_removidas}')

                    # Etapa 3: E, por fim, remove todos os respondentes restantes
                    logger.debug(f'Excluindo todos os respondentes restantes da avaliação {self.id}.')
                    respondentes_removidos = Respondente.objects.filter(avaliacao=self).delete()
                    logger.debug(f'Total de respondentes removidos: {respondentes_removidos}')

        except Exception as exc:
            # Registra stack trace e re-sinaliza como erro de domínio mais específico.
            logger.warning(
                'Falha na limpeza de dados da avaliação %s. A operação de limpeza será abortada.',
                self.id,
            )

            raise AvaliacaoDataCleanupError(
                f'Não foi possível apagar os respondentes aptos e suas repostas para a avaliação {self.nome} antes da (re)geração dos respondentes.'
            ) from exc

        logger.debug(f'> Gerando {total_respondentes} respondentes aptos para {total_segmentos} segmentos')

        contador_respondentes = 0
        contador_segmentos = 0
        for segmento_id, lista_dados in publico_alvo.items():
            contador_segmentos += 1

            segmento = Segmento.objects.get(pk=segmento_id)
            logger.debug(f'>. Processando segmento {segmento} ...')

            percent_progress_segmentos = (contador_segmentos / total_segmentos) * 100.0
            logger.debug(
                f'>.[{percent_progress_segmentos:.2f}%] '
                f'Processando segmento {contador_segmentos} de {total_segmentos}:'
                f' {len(lista_dados)} respondentes.'
            )

            contador_respondentes = self._gerar_respondentes_segmento(lista_dados, segmento, total_respondentes, contador_respondentes, task)

        logger.debug('>> Enviando e-mails para os respondentes...,')
        self.enviar_emails(criacao=True)

        logger.debug('> [FIM] do reprocessamento.')

    def obter_publicoalvo(self) -> dict[int, list[dict[str, str | int | None]]]:
        """
        Retorna os respondentes aptos para responder a avaliação.
        Respondentes é uma lista de dupla com os ids de usuário e unidade organizacional
        """
        servidores = self._obter_publicoalvo_servidores()
        alunos = self._obter_publicoalvo_alunos()
        sociedade_civil: dict[int, SociedadeCivilQuerySet] = self._obter_publicoalvo_sociedade_civil()

        publico_alvo = {}
        # publico_alvo: Dict[int,List[Dict[str, Optional[str | int]]]]

        for segmento in self.segmentos.all():
            publico_alvo.update(self._filtrar_respondentes_por_segmento(segmento, servidores, alunos, sociedade_civil))

            if publico_alvo.get(segmento.pk):
                total_respondentes = len(publico_alvo[segmento.pk])
                logger.debug(f'> Total respondente para o segmento {segmento}: {total_respondentes}')
            else:
                logger.debug(f'> Não há público-alvo para o segmento {segmento}')

        return publico_alvo

    def enviar_emails(self, criacao=False, titulo: str | None = None, mensagem_html: str | None = None) -> int:
        # Aplica o filtro base
        # Apenas respondentes não finalizados e que pertençam aos segmentos que exigem email
        respondentes = Respondente.objects.filter(avaliacao=self, finalizado=False, segmento__pk__in=Segmento.LISTA_EMAIL)

        # Aplica o filtro para os emails válidos
        respondentes = respondentes.filter(Respondente.get_email_filter())

        # Uso do Coalesce para definir o campo 'email' corretamente
        respondentes = respondentes.annotate(email=Respondente.get_email_coalesce())

        assunto_criacao = f'{self.nome}'
        conteudo_criacao = f'{self.descricao}'

        assunto_inicio = f'{self.nome}'
        conteudo_inicio = f"""
            Caro(a) respondente, até o dia {self.data_termino} está disponível o formulário do(a) da {self.nome}.

            Para participar, acesse o SUAP com sua matrícula e senha e clique no link disponível em “Fique Atento!”.
            É possível, a qualquer momento, clicar no botão "Salvar", disponível no final do formulário, e retomar o preenchimento posteriormente, até o prazo final.

            Lembre-se: Ao terminar o preenchimento, clique no botão "Enviar Respostas" para que sua resposta seja registrada.

            A sua participação é muito importante para a instituição!
        """

        assunto_lembrete = f'{self.nome}'
        conteudo_lembrete = f"""
            Caro(a) respondente, você ainda não concluiu o preenchimento da {self.nome}, que está disponível até {self.data_termino}.

            Para participar, acesse o SUAP com sua matrícula e senha e clique no link disponível em “Fique Atento!”.
            É possível, a qualquer momento, clicar no botão "Salvar", disponível no final do formulário, e retomar o preenchimento posteriormente, até o prazo final.

            Lembre-se: Ao terminar o preenchimento, clique no botão "Enviar Respostas" para que sua resposta seja registrada.

            Vamos lá! Participe! O prazo está acabando!
        """

        assunto_ultimo = f'{self.nome}'
        conteudo_ultimo = f"""
            Caro(a) respondente, hoje é o último dia para você concluir o preenchimento da {self.nome}.

            Para participar, acesse o SUAP com sua matrícula e senha e clique no link disponível em “Fique Atento!”.
            É possível, a qualquer momento, clicar no botão "Salvar", disponível no final do formulário, e retomar o preenchimento posteriormente, até o prazo final.

            Lembre-se: Ao terminar o preenchimento, clique no botão "Enviar Respostas" para que sua resposta seja registrada.

            Vamos lá! Dê a sua contribuição nesse processo!
        """
        tempo_total = (self.data_termino - self.data_inicio).days
        hoje = datetime.date.today()
        enviar_email = False
        assunto = ''
        conteudo = ''
        if criacao:
            enviar_email = True
            assunto = assunto_criacao
            conteudo = conteudo_criacao
        elif hoje == self.data_inicio:
            enviar_email = True
            assunto = assunto_inicio
            conteudo = conteudo_inicio
        # `date.replace(day=...)` estoura `ValueError` quando a soma passa do fim do mês;
        # o deslocamento tem de ser por `timedelta`.
        elif hoje + datetime.timedelta(days=int(tempo_total * 0.75)) == self.data_termino:
            enviar_email = True
            assunto = assunto_lembrete
            conteudo = conteudo_lembrete
        elif hoje + datetime.timedelta(days=1) == self.data_termino:
            enviar_email = True
            assunto = assunto_ultimo
            conteudo = conteudo_ultimo

        # Se não houver “gatilho temporal” e também não veio mensagem customizada, nada a enviar
        if not enviar_email and not mensagem_html:
            logger.debug('>> Condições de envio não atendidas; nada a enviar.')
            raise ValueError('Condições de envio não atendidas; nada a enviar.')

        # Se vierem overrides, usam-se eles; senão usa-se o assunto/conteúdo calculados
        assunto_final = (titulo or assunto or f'{self.nome}').strip()
        corpo_final = mensagem_html or conteudo

        if not corpo_final:
            logger.debug('>> Sem conteúdo montado; nada a enviar.')
            raise ValueError('Sem conteúdo montado; nada a enviar.')

        if enviar_email:
            emails_qs = respondentes.filter(email__contains='@').values_list('email', flat=True)
            emails = set()
            for email in emails_qs:
                try:
                    email = email.replace(' ', '').replace(',', '.').lower()
                    email = retira_acentos(email)
                    validate_email(email)
                    emails.add(email)
                except ValidationError:
                    logger.debug(f'Email inválido: {email}".')

            total = len(emails)
            if total == 0:
                logger.debug('>> Nenhum destinatário elegível encontrado.')
                return 0

            logger.debug(f'>> Preparado envio de e-mails (assunto "{assunto}") para {total} respondente(s).')
            # Envio em HTML via djtools (gera o HTML final com template interno)
            # Observação: o wrapper ignora o parâmetro `html=` e monta o HTML a partir de `mensagem`.
            send_mail(
                assunto_final,
                corpo_final,
                # conteúdo que será encapsulado pelo template HTML padrão
                settings.DEFAULT_FROM_EMAIL,
                list(emails),
                fail_silently=True,
                # no djtools, com True, o envio roda em thread (não bloqueia a view)
                is_notification=False,
                # attachments=..., files=..., bcc=... (se necessário no futuro)
            )

            return total

        # Mensagem customizada fora de qualquer gatilho temporal: nada é enviado, mas a
        # função é anotada `-> int` e o chamador compara com zero. Cair fora daqui devolvia
        # None e estourava `TypeError` na tela de envio de lembrete.
        return 0

    def get_absolute_url(self):
        return f'/avaliacao_integrada/avaliacao/{self.pk}/'

    def is_vigente(self):
        """Verifica se a avaliação atual (self) está entre as vigentes"""
        return self.vigentes().filter(id=self.id)

    @classmethod
    def vigentes(cls) -> QuerySet[Avaliacao]:
        """Retorna as avaliações vigentes, ou seja, ativas no momento"""
        hoje = datetime.date.today()
        qs = cls.objects.filter(data_inicio__lte=hoje, data_termino__gte=hoje)
        return qs

    @classmethod
    def gerar_token(cls, avaliacao_id: int, dados: dict | None = None) -> str:
        if dados is None:
            dados = {}
        dados['avaliacao_id'] = avaliacao_id
        return urlsafe_base64_encode(force_bytes(json.dumps(dados)))

    @classmethod
    def obter_dados(cls, token: str) -> dict:
        try:
            dados = force_str(urlsafe_base64_decode(token))
            return json.loads(dados)
        except Exception:
            return {}


class Respondente(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus(Avaliacao, verbose_name='Avaliação', on_delete=models.PROTECT)
    user = models.ForeignKeyPlus(User, verbose_name='Usuário', null=True, on_delete=models.PROTECT)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus', null=True, on_delete=models.PROTECT)
    segmento = models.ForeignKeyPlus(Segmento, verbose_name='Segmento', on_delete=models.PROTECT)
    finalizado = models.BooleanField('Questionário Finalizado', default=False)

    dados_usuario_externo = models.JSONField(null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cadastrado_por = models.CurrentUserField(default=tl_get_user, related_name='respondente_cadastrado_por')

    percentual_resposta = models.PositiveSmallIntegerField('Percentual de resposta', default=0, help_text='Valor entre 0 e 100.')

    class Meta:
        verbose_name = 'Respondente'
        verbose_name_plural = 'Respondentes'
        ordering = ('id',)
        # Declarado aqui (e não só no RunSQL da migration 0009) para que o índice também exista em
        # bancos criados pelo `create_db`, que monta o schema a partir dos models.
        indexes = [models.Index(KeyTextTransform('email', 'dados_usuario_externo'), name='idx_respondente_email')]

    def __str__(self):
        return f'Respondente segmento: {self.segmento}, user: {self.identificacao}'

    @property
    def nome(self):
        if self.user:
            return self.user
        elif self.dados_usuario_externo:
            if self.dados_usuario_externo.get('pj_nome'):
                pj_nome = self.dados_usuario_externo['pj_nome']
                nome_representante_legal = self.dados_usuario_externo['pf_nome']
                if nome_representante_legal:
                    return f'{pj_nome} ({nome_representante_legal})'
                return pj_nome
            elif self.dados_usuario_externo.get('pf_nome'):
                pf_nome = self.dados_usuario_externo['pf_nome']
                parentesco = self.dados_usuario_externo.get('parentesco_responsavel')
                if parentesco:
                    return f'{pf_nome} ({parentesco})'
                return pf_nome
        return '-'

    @property
    def identificacao(self):
        if self.dados_usuario_externo:
            if self.segmento.pk == Segmento.PAIS:
                return self.dados_usuario_externo.get('matricula')
            elif self.segmento.pk in (Segmento.ALUNO_EGRESSO, Segmento.PROFISSIONAL_PRESTADOR_SERVICO):
                return self.dados_usuario_externo.get('cpf')
            elif self.segmento.pk == Segmento.EMPRESA_PRESTADORA_SERVICO:
                return self.dados_usuario_externo.get('cnpj')
            else:
                return self.dados_usuario_externo.get('email')
        elif self.user:
            return self.user.username
        return '-'

    # --- Cálculo do percentual ---

    def get_percentual_respondido(self, excluir_automatico=False, ignorar_opcionais=False):
        """
        Calcula e retorna o percentual de indicadores respondidos pelo respondente.

        O cálculo parte do conjunto de indicadores aplicáveis ao respondente,
        obtido por `Respondente.get_indicadores(...)`, e divide a quantidade de
        respostas válidas registradas em `Resposta` (isto é, com `valor` não nulo
        e não vazio) pelo total de indicadores considerados, convertendo o
        resultado para um inteiro no intervalo [0, 100].

        Parâmetros:
            excluir_automatico (bool): Se True, remove do cômputo (numerador e
                denominador) os indicadores de preenchimento automático
                (`indicador.automatico=True`).
            ignorar_opcionais (bool): Se True, considera apenas indicadores
                obrigatórios (`indicador.obrigatorio=True`) tanto no numerador
                quanto no denominador.

        Retorno:
            int: Percentual inteiro de respostas válidas no intervalo [0, 100].
                 Retorna 0 quando não houver indicadores aplicáveis.

        Regras e observações:
            - Respostas válidas: `valor IS NOT NULL` e `valor != ''`.
            - O denominador é `get_indicadores(...).count()` após aplicar os filtros
              definidos pelos parâmetros.
            - O resultado é truncado (conversão para `int`) e limitado a 100 com `min(100, ...)`.

        Ver também:
            get_percentual_realmente_respondido: atalho que calcula o percentual
            excluindo indicadores automáticos e opcionais.
        """
        total_perguntas = self.__class__.get_indicadores(
            self.avaliacao, self.segmento, self.uo, self.user, excluir_automatico=excluir_automatico, ignorar_opcionais=ignorar_opcionais
        ).count()
        if not total_perguntas:
            return 0
        qs_respondido = Resposta.objects.filter(respondente=self).exclude(valor='').filter(valor__isnull=False)
        if excluir_automatico:
            qs_respondido = qs_respondido.filter(indicador__automatico=False)
        if ignorar_opcionais:
            qs_respondido = qs_respondido.filter(indicador__obrigatorio=True)
        resultado = int(qs_respondido.count() * 100 / total_perguntas)
        return min(100, resultado)

    def get_percentual_realmente_respondido(self):
        """
        Retorna o percentual de itens efetivamente respondidos pelo respondente.

        Este método calcula o percentual considerando apenas os indicadores
        que exigem resposta do usuário, isto é, **exclui**:
          - indicadores de cálculo automático (automatico=True); e
          - indicadores opcionais (obrigatorio=False).

        Internamente, delega o cálculo para `get_percentual_respondido(...)`,
        com os parâmetros `excluir_automatico=True` e `ignorar_opcionais=True`.

        Returns:
            int: Percentual inteiro no intervalo [0, 100] representando a
            proporção de respostas válidas (não vazias e não nulas) sobre o
            total de indicadores aplicáveis ao respondente, após as exclusões
            descritas acima.

        See Also:
            get_percentual_respondido: Versão geral do cálculo, permitindo
            incluir/excluir indicadores automáticos e opcionais.
        """
        return self.get_percentual_respondido(excluir_automatico=True, ignorar_opcionais=True)

    def atualizar_percentual_resposta(
        self,
        excluir_automatico: bool = True,
        ignorar_opcionais: bool = True,
        commit: bool = True,
    ) -> int:
        """
        Recalcula o percentual de resposta usando as funções existentes.
        Por padrão, utiliza o 'percentual realmente respondido'
        (exclui automáticos e opcionais).
        """
        if excluir_automatico and ignorar_opcionais:
            percentual = self.get_percentual_realmente_respondido()
        else:
            percentual = self.get_percentual_respondido(
                excluir_automatico=excluir_automatico,
                ignorar_opcionais=ignorar_opcionais,
            )

        # Garante o intervalo [0, 100]
        percentual = max(0, min(100, int(percentual)))

        if percentual != self.percentual_resposta:
            self.percentual_resposta = percentual
            if commit:
                self.save(update_fields=['percentual_resposta', 'atualizado_em'])
        return percentual

    @classmethod
    def get_email_coalesce(cls):
        """
        Retorna uma expressão SQL para obter o email de um respondente, priorizando o campo 'dados_usuario_externo__email'
        e, se este não estiver disponível, utilizando o 'user__email'.

        O campo 'dados_usuario_externo__email' é um campo JSON, então o método 'Replace' remove as aspas duplas que podem
        estar presentes. A expressão utiliza 'Coalesce' para escolher o primeiro valor não-nulo entre o email externo e
        o email do usuário.

        Returns:
            Coalesce: Expressão SQL para recuperar o email sem aspas duplas.
        """
        return Coalesce(
            Replace(Cast('dados_usuario_externo__email', models.CharField()), models.Value('"'), models.Value('')),
            'user__email',
            output_field=models.EmailField(),
        )

    @classmethod
    def get_email_filter(cls):
        """
        Gera uma expressão `Q` para filtrar registros que possuem email válido.

        Verifica se o campo `dados_usuario_externo__email` ou `user__email`
        possuem valores não nulos e não vazios.

        Returns:
            Q: expressão para filtrar registros com email válido.
        """
        return Q(dados_usuario_externo__email__isnull=False) & ~Q(dados_usuario_externo__email='') | Q(user__email__isnull=False) & ~Q(user__email='')

    @classmethod
    def obter_dados_publico_alvo(
        cls, tipo_respondente: int, dados_form: dict | None = None, qs: QuerySet = None
    ) -> list[dict[str, str | int | None]]:
        def obter_publico_alvo(qs: QuerySet, segmento_id: int) -> list[dict[str, str | int | None]]:
            logger.debug(f'>>> Obtendo dados do públic alvo, modelo {qs.model}')
            values_list = ['uo_id', 'user_id', 'pf_nome', 'cpf', 'matricula', 'email', 'cnpj']

            qs = qs.annotate(cnpj=Value(None, output_field=models.CharField()))

            if segmento_id in Segmento.SERVIDORES:
                if qs.model == ComissaoCPA:
                    qs = (
                        qs.annotate(
                            user_id=F('vinculos_membros__user'),
                            pf_nome=F('vinculos_membros__pessoa__pessoafisica__nome'),
                            cpf=F('vinculos_membros__pessoa__pessoafisica__cpf'),
                            matricula=F('vinculos_membros__user__username'),
                            email=F('vinculos_membros__email_pessoal'),
                        )
                        .order_by('matricula')
                        .distinct('matricula')
                    )
                else:
                    # Modelo Servidor
                    qs = (
                        qs.annotate(
                            uo_id=F('setor__uo'),
                            user_id=F('vinculos__user'),
                            pf_nome=F('pessoa_fisica__nome'),
                            cpf=F('pessoa_fisica__cpf'),
                            email=F('vinculos__email_pessoal'),
                        )
                        .order_by('matricula')
                        .distinct('matricula')
                    )

            elif qs.model == Aluno:
                # segmento_id in (Segmento.ESTUDANTE, Segmento.ALUNO_EGRESSO, Segmento.PAIS):
                qs = qs.annotate(
                    uo_id=F('curso_campus__diretoria__setor__uo'),
                    user_id=F('vinculos__user'),
                    pf_nome=F('pessoa_fisica__nome'),
                    cpf=F('pessoa_fisica__cpf'),
                    email=F('vinculos__email_pessoal'),
                )

                if segmento_id == Segmento.ESTUDANTE:
                    qs = qs.order_by('matricula').distinct('matricula')
                elif segmento_id == Segmento.ALUNO_EGRESSO:
                    qs = qs.order_by('cpf').distinct('cpf')
                elif segmento_id == Segmento.PAIS:
                    qs = (
                        qs.annotate(
                            uo_id=F('curso_campus__diretoria__setor__uo'),
                            user_id=Value(None, output_field=models.IntegerField()),
                            pf_nome=Coalesce('responsavel', 'nome_mae', 'nome_pai', output_field=models.CharField()),
                            cpf=F('cpf_responsavel'),
                            email=Coalesce('email_responsavel', 'vinculos__email_pessoal', output_field=models.CharField()),
                        )
                        .order_by('matricula')
                        .distinct('matricula')
                    )

                    values_list.append('parentesco_responsavel')
                    # <<Aluno>>.get_chave_responsavel

            elif segmento_id == Segmento.PROFISSIONAL_PRESTADOR_SERVICO:
                # Modelo MaoDeObra
                qs = (
                    qs.annotate(
                        uo_id=F('campus'),
                        user_id=F('prestador_servico__vinculos__user'),
                        pf_nome=F('prestador_servico__pessoa_fisica__nome'),
                        cpf=F('prestador_servico__pessoa_fisica__cpf'),
                        matricula=F('prestador_servico__matricula'),
                        email=F('prestador_servico__vinculos__email_pessoal'),
                    )
                    .order_by('cpf')
                    .distinct('cpf')
                )

            elif segmento_id == Segmento.EMPRESA_PRESTADORA_SERVICO:
                # Modelo MaoDeObra
                qs = (
                    qs.annotate(
                        uo_id=F('contrato__campus_gerenciador'),
                        user_id=Value(None, output_field=models.IntegerField()),
                        matricula=Value(None, output_field=models.CharField()),
                        pf_nome=F('contrato__vinculo_contratado__pessoa__pessoajuridica__nome_representante_legal'),
                        pj_nome=F('contrato__vinculo_contratado__pessoa__nome'),
                        cpf=Value(None, output_field=models.CharField()),
                        email=Value(None, output_field=models.CharField()),
                        cnpj=F('contrato__vinculo_contratado__pessoa__pessoajuridica__cnpj'),
                    )
                    .order_by('cnpj')
                    .distinct('cnpj')
                )
                values_list.append('pj_nome')

            elif segmento_id == Segmento.SUPERVISOR_ESTAGIO:
                # Modelo PraticaProfissional
                qs = (
                    qs.annotate(
                        uo_id=F('aluno__curso_campus__diretoria__setor__uo'),
                        user_id=Value(None, output_field=models.IntegerField()),
                        matricula=Value(None, output_field=models.CharField()),
                        pf_nome=F('nome_supervisor'),
                        cpf=F('supervisor__pessoa__pessoafisica__cpf'),
                        email=F('email_supervisor'),
                    )
                    .order_by('email')
                    .distinct('email')
                )

            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(f'>>> dados obtidos, total {qs.values(*values_list).count()}')
            return qs.values(*values_list)

        if (dados_form and qs) or (dados_form is None and qs is None):
            raise ValueError('Deve informar ao menos "dados_form" ou "qs".')

        lista_dados = []
        if qs is not None:
            lista_dados = obter_publico_alvo(qs, tipo_respondente)

        if dados_form:
            dados_usuario_externo = {
                'tipo_respondente': int(tipo_respondente),
                'email': dados_form.get('email'),
                'matricula': dados_form.get('matricula'),
                'cpf': dados_form.get('cpf'),
                'cnpj': dados_form.get('cnpj'),
            }
            # Processa os dados com base no tipo de respondente
            if tipo_respondente == Segmento.PAIS:
                if not dados_usuario_externo['matricula']:
                    raise ValidationError('Matrícula é obrigatória para o perfil Pais e/ou Responsável.')
            elif tipo_respondente in [Segmento.PROFISSIONAL_PRESTADOR_SERVICO, Segmento.ALUNO_EGRESSO]:
                if not dados_usuario_externo['cpf']:
                    raise ValidationError('CPF é obrigatório para esse tipo de respondente.')
            elif tipo_respondente == Segmento.EMPRESA_PRESTADORA_SERVICO:
                if not dados_usuario_externo['cnpj']:
                    raise ValidationError('CNPJ é obrigatório para o perfil Empresa Prestadora de Serviço.')
            elif tipo_respondente == Segmento.SUPERVISOR_ESTAGIO:
                if not dados_usuario_externo['email']:
                    raise ValidationError('E-mail é obrigatório para o pefil Supervisor de Estágios.')

            lista_dados = [dados_usuario_externo]

        return lista_dados

    @classmethod
    def get_modalidades_relacionadas(cls, avaliacao, segmento, uo):
        """
        Obtem as modalidades dos cursos conforme o tipo de segmento dos respondentes.
        """
        if segmento.id in [Segmento.CPA_CENTRAL, *Segmento.SOCIEDADE_CIVIL]:
            logger.debug('> Obtem modalidades, filtros: Todas, quando segmento é CPA Central ou sociedade cívil ')
            return Modalidade.objects.all()
        elif segmento.id in Segmento.SERVIDORES:
            curso_campos_modalidades_ids = CursoCampus.objects.filter(diretoria__setor__uo=uo, ativo=True).values_list('modalidade__pk', flat=True)

            avaliacao_modalidades_ids = avaliacao.modalidades.values_list('id', flat=True)

            modalidades = Modalidade.objects.filter(id__in=curso_campos_modalidades_ids).filter(id__in=avaliacao_modalidades_ids)

            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(
                    f'> Obtem modalidades, filtros: aquelas definidas na avaliação '
                    f'e também as definidas no setor da diretoria que são {list(curso_campos_modalidades_ids)}'
                )
            return modalidades
        logger.debug('> Obtem modalidades, critérios não atendido, retorna NENHUMA.')
        return Modalidade.objects.none()

    # Professores e Alunos (ativos e egressos)
    @classmethod
    def get_cursos_relacionados(cls, segmento, uo, user):
        if segmento.id in [Segmento.CPA_CAMPUS, Segmento.DOCENTE]:
            return CursoCampus.objects.filter(diretoria__setor__uo=uo, ativo=True)
        elif segmento.id in ([*Segmento.ALUNOS, Segmento.ETEP]):
            return CursoCampus.objects.filter(aluno__matricula=user.username)
        return CursoCampus.objects.none()

    # Professores e Alunos (ativos)
    @classmethod
    def get_turmas_relacionadas(cls, avaliacao, segmento, user):
        qs = Diario.objects.none()

        if segmento.id == Segmento.DOCENTE:
            qs = Diario.objects.filter(professordiario__professor__vinculo__user__username=user.username, ano_letivo=avaliacao.ano)
        elif segmento.id == Segmento.ESTUDANTE:
            qs = Diario.objects.filter(matriculadiario__matricula_periodo__aluno__matricula=user.username, ano_letivo=avaliacao.ano)

        if avaliacao.periodo:
            qs.filter(periodo_letivo=avaliacao.periodo)

        return qs

    # Alunos (ativos)
    @classmethod
    def get_professores_relacionados(cls, avaliacao, segmento, user):
        qs = Turma.objects.none()

        if segmento.id in Segmento.ALUNOS:
            qs = ProfessorDiario.objects.filter(
                diario__ano_letivo=avaliacao.ano, diario__matriculadiario__matricula_periodo__aluno__matricula=user.username
            )

        if avaliacao.periodo:
            qs.filter(diario__periodo_letivo=avaliacao.periodo)

        return qs

    def _get_aluno(self):
        if not self.user:
            return None
        eh_aluno = self.user.eh_aluno() if callable(getattr(self.user, 'eh_aluno', None)) else getattr(self.user, 'eh_aluno', False)
        if eh_aluno:
            rel = self.user.get_relacionamento()
            if rel:
                return rel
        profile = self.user.get_profile()
        return profile.aluno_set.first() if profile else None

    # Métodos para recuperar o valor dos campos autocalculados.
    def get_unidade_diretoria_aluno(self):
        aluno = self._get_aluno()
        if (
            aluno
            and aluno.curso_campus
            and aluno.curso_campus.diretoria
            and aluno.curso_campus.diretoria.setor
            and aluno.curso_campus.diretoria.setor.uo
        ):
            return aluno.curso_campus.diretoria.setor.uo.nome
        return self.uo.nome

    def get_modalidade_vinculacao(self):
        aluno = self._get_aluno()
        return aluno.curso_campus.modalidade.descricao if aluno and aluno.curso_campus and aluno.curso_campus.modalidade else ''

    def get_curso_vinculacao(self):
        aluno = self._get_aluno()
        return aluno.curso_campus.descricao_historico if aluno and aluno.curso_campus else ''

    def get_ano_ingresso_curso(self):
        aluno = self._get_aluno()
        return aluno.ano_letivo.ano if aluno and aluno.ano_letivo else None

    def get_forma_ingresso_curso(self):
        aluno = self._get_aluno()
        return aluno.forma_ingresso.descricao if aluno and aluno.forma_ingresso else ''

    def get_serie_periodo_curso(self):
        aluno = self._get_aluno()
        return aluno.periodo_atual if aluno else None

    def get_cargo_servidor(self):
        return self.user.get_relacionamento().cargo_emprego.nome

    def get_unidade_atuacao_servidor(self):
        return self.uo.nome

    def get_area_atuacao_servidor(self):
        return self.user.get_relacionamento().setor.areas_vinculacao.all()[0].descricao

    def get_regime_trabalho_servidor(self):
        return self.user.get_relacionamento().jornada_trabalho.nome

    def get_forma_contratacao_servidor(self):
        return self.user.get_relacionamento().situacao.nome

    def get_data_nascimento(self):
        return self.user.get_profile().nascimento_data.strftime('%d/%m/%Y')

    def get_tipo_acao_afirmativa(self):
        aluno = self._get_aluno()
        return aluno.get_cota_mec_display() if aluno else ''

    def get_funcao_servidor(self):
        return self.user.get_relacionamento().funcao_display

    @classmethod
    def get_indicadores(cls, avaliacao, segmento, uo, user, excluir_automatico=False, ignorar_opcionais=False):
        # filtrando indicadores ativos

        indicadores = Indicador.objects.filter(em_uso=True, anos_referencia__in=[avaliacao.ano])
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'> Obtem indicadores, filtros: em_uso={True}, anos_referencia__in={[avaliacao.ano]}. Total obtidos: {indicadores.count()}')
        if excluir_automatico:
            indicadores = indicadores.filter(automatico=False)
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'> Obtem indicadores, filtros: exclui os autocalculado (automatico=False). Total obtidos: {indicadores.count()}')
        if ignorar_opcionais:
            indicadores = indicadores.filter(obrigatorio=True)
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'> Obtem indicadores, filtros: resposta obrigatória. Total obtidos: {indicadores.count()}')

        if uo:
            if uo.tipo_id == UnidadeOrganizacional.TIPO_REITORIA:
                indicadores = indicadores.filter(envolve_reitoria=True)
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(f'> Obtem indicadores, filtros: envolve reitoria. Total obtidos: {indicadores.count()}')
            elif uo.tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_EAD:
                indicadores = indicadores.filter(envolve_campus_ead=True)
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(f'> Obtem indicadores, filtros: envolve campus EAD. Total obtidos: {indicadores.count()}')
            elif uo.tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_NAO_PRODUTIVO:
                indicadores = indicadores.filter(envolve_campus_nao_produtivos=True)
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(f'> Obtem indicadores, filtros: envolve campus sem unidade produtora. Total obtidos: {indicadores.count()}')
            elif uo.tipo_id == UnidadeOrganizacional.TIPO_CAMPUS_PRODUTIVO:
                indicadores = indicadores.filter(envolve_campus_produtivos=True)
                if logger.getEffectiveLevel() == logging.DEBUG:
                    logger.debug(f'> Obtem indicadores, filtros: envolve campus com unidade produtora. Total obtidos: {indicadores.count()}')

            indicadores = indicadores.filter(Q(uos=uo) | Q(uos__isnull=True)).distinct()
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(f'> Obtem indicadores, filtros: unidades relacionadas com {uo} Total obtidos: {indicadores.count()}')
        else:
            indicadores = indicadores.filter(uos__isnull=True)
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(f'> Obtem indicadores, filtros: ignora unidades relacionadas. Total obtidos: {indicadores.count()}')

        # filtrando indicadores por segmento do respondente
        indicadores = indicadores.filter(segmentos__id=segmento.pk)
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'> Obtem indicadores, filtros: segmento = {segmento.descricao}. Total obtidos: {indicadores.count()}')

        # filtrando indicadores por area do respondente
        if segmento.id in Segmento.SERVIDORES:
            servidor = Servidor.objects.get(matricula=user.username)
            areas_vinculacao_ids = []
            if servidor.setor:
                areas_vinculacao_ids = servidor.setor.areas_vinculacao.values_list('pk', flat=True)

            indicadores = indicadores.filter(Q(areas_vinculacao__isnull=True) | Q(areas_vinculacao__in=areas_vinculacao_ids))

            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(
                    f'> Obtem indicadores, filtros aplicado quando segmento é SERVIDORES: '
                    f'indicadores onde as áres de vinculação do setor {servidor.setor} são {list(areas_vinculacao_ids)}, '
                    f'OU indicadores com áreas de vinculação vazia.'
                    f'Total obtidos: {indicadores.count()}'
                )

        # filtrando indicadores pela modalidade dos cursos
        if avaliacao.modalidades.exists():
            modalidades_ids = avaliacao.modalidades.values_list('id', flat=True)
            indicadores = indicadores.filter(Q(modalidades__in=modalidades_ids) | Q(modalidades__isnull=True))
            if logger.getEffectiveLevel() == logging.DEBUG:
                logger.debug(
                    f'> Obtem indicadores, filtros: '
                    f'indicadores onde as modalidades na avaliação são {modalidades_ids}, '
                    f'OU indicadores com modalidades vazia.'
                    f'Total obtidos: {indicadores.count()}'
                )

            # filtrando indicadores pelo período de referência do aluno
            if segmento.id == Segmento.ESTUDANTE:
                aluno = Aluno.ativos.filter(matricula=user.username).first()
                if aluno:
                    if aluno.periodo_atual:
                        indicadores = indicadores.exclude(periodo_curso__gt=aluno.periodo_atual)
                    else:
                        indicadores = indicadores.exclude(periodo_curso__gt=0)

                    if logger.getEffectiveLevel() == logging.DEBUG:
                        logger.debug(
                            f'> Obtem indicadores, filtros aplicado quando segmento é ESTUDANTE: '
                            f'remove os indicadores maiores que o período do curso "{aluno.periodo_atual}" '
                            f'do aluno de matrícula {user.username}. '
                            f'Isso significa que o aluno só verá indicadores menores ou igual ao seu período atual.'
                            f'Total obtidos: {indicadores.count()}'
                        )
                else:
                    indicadores = indicadores.exclude(periodo_curso__gt=0)

        indicadores = indicadores.distinct()
        if logger.getEffectiveLevel() == logging.DEBUG:
            logger.debug(f'> Agrupa os indicadores semelhantes (distinct)Total obtidos: {indicadores.count()}')

        return indicadores

    def possui_area_vinculacao(self) -> bool:
        """
        Retorna True se ao menos uma das áreas de vinculação do setor do respondente
        estiver presente nas áreas de vinculação da avaliação.
        """
        if not self.user:
            return False

        if not self.avaliacao.areas_vinculacao.exists():
            return False

        vinculo = getattr(self.user, 'vinculo', None)
        if not vinculo:
            return False

        setor = getattr(vinculo, 'setor', None)
        if not setor:
            return False

        avaliacao_av_ids = self.avaliacao.areas_vinculacao.values_list('id', flat=True)
        return setor.areas_vinculacao.filter(id__in=avaliacao_av_ids).exists()

    @staticmethod
    def apply_filters(
        respondentes: QuerySet[Respondente],
        segmentos: QuerySet[Segmento] | None = None,
        areas_vinculacao: QuerySet[AreaVinculacao] | None = None,
        uos: QuerySet[UnidadeOrganizacional] | None = None,
        modalidades: QuerySet[Modalidade] | None = None,
        cursos: QuerySet[CursoCampus] | None = None,
    ) -> QuerySet[Respondente]:
        """
        Aplica filtros opcionais sobre um `QuerySet[Respondente]` e retorna um
        novo queryset sem duplicidades.

        Regras de filtragem:
            - `segmentos`: mantém respondentes cujo `segmento` está no queryset informado.
            - `areas_vinculacao`: mantém respondentes cuja área de vinculação do setor do vínculo do usuário
              (`user__vinculo__setor__areas_vinculacao`) está no queryset informado.
            - `uos`: mantém respondentes cuja `uo` está no queryset informado.
            - `modalidades`: mantém respondentes cujos vínculos acadêmicos possuem modalidade
              (`...aluno_set__curso_campus__modalidade`) presente no queryset informado.
            - `cursos`: mantém respondentes cujos vínculos acadêmicos possuem curso/campus
              (`...aluno_set__curso_campus`) presente no queryset informado.

        Observações:
            - Cada filtro somente é aplicado quando o queryset correspondente é fornecido
              **e** possui elementos (`.exists()`), evitando junções desnecessárias.
            - O retorno aplica `.distinct()` para eliminar duplicidades decorrentes das junções.

        Parâmetros:
            respondentes: `QuerySet[Respondente]` base a ser filtrado.
            segmentos: `QuerySet[Segmento]` opcional.
            areas_vinculacao: `QuerySet[AreaVinculacao]` opcional.
            uos: `QuerySet[UnidadeOrganizacional]` opcional.
            modalidades: `QuerySet[Modalidade]` opcional.
            cursos: `QuerySet[CursoCampus]` opcional.

        Retorno:
            `QuerySet[Respondente]`: queryset filtrado e sem duplicidades.
        """
        if segmentos is not None and segmentos.exists():
            respondentes = respondentes.filter(segmento__in=segmentos)

        if areas_vinculacao is not None and areas_vinculacao.exists():
            respondentes = respondentes.filter(user__vinculo__setor__areas_vinculacao__in=areas_vinculacao.values_list('id', flat=True))

        if uos is not None and uos.exists():
            respondentes = respondentes.filter(uo__in=uos.values_list('id', flat=True))

        if modalidades is not None and modalidades.exists():
            respondentes = respondentes.filter(
                user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__modalidade__in=modalidades.values_list('id', flat=True)
            )

        if cursos is not None and cursos.exists():
            respondentes = respondentes.filter(user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__in=cursos.values_list('id', flat=True))

        return respondentes.distinct()


class Resposta(models.ModelPlus):
    VALOR_DESCONHECO = 0
    VALOR_NAO_SE_APLICA = 9
    NAO_RESPONDERAM = 'Não responderam'

    indicador = models.ForeignKeyPlus(Indicador, verbose_name='Indicador', on_delete=models.PROTECT)
    respondente = models.ForeignKeyPlus(Respondente, verbose_name='Respondente', on_delete=models.PROTECT)
    variavel = models.ForeignKeyPlus(Variavel, verbose_name='Variável', null=True, blank=True, on_delete=models.PROTECT)
    content_type = models.ForeignKeyPlus(ContentType, verbose_name='Content Type', null=True, blank=True, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField(verbose_name='', null=True, blank=True)
    objeto = GenericForeignKey('content_type', 'object_id')
    identificador = models.CharFieldPlus('Identificador')
    valor = models.TextField()

    nivel_escala = models.ForeignKey(NivelEscalaLikert, null=True, blank=True, on_delete=models.PROTECT)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)
    cadastrado_por = models.CurrentUserField(default=tl_get_user, related_name='resposta_cadastrado_por')

    class Meta:
        verbose_name = 'Resposta'
        verbose_name_plural = 'Resposta'
        ordering = ('id',)

    @staticmethod
    def to_identificador(indicador_id, respondente_id, variavel_id, object):
        content_type = object and ContentType.objects.get(model=object.__class__.__name__.lower()) or None
        return f'{indicador_id}::{respondente_id}::{variavel_id and variavel_id or 0}::{content_type and content_type.pk or 0}::{object and object.id or 0}'

    @staticmethod
    @transaction.atomic
    def processar(respondente: Respondente, dados: dict[str, Any], finalizar: bool = False) -> ProcessarResult:
        """
        Processa e persiste as respostas do *respondente* a partir de *dados*,
        opcionalmente finalizando o questionário.

        O método remove previamente as respostas existentes do respondente e cria
        novos registros de `Resposta` com base nos identificadores recebidos.
        Ao término, calcula e retorna dois percentuais de avanço:

          - `percentual`: percentual efetivamente respondido, **desconsiderando**
            indicadores automáticos e opcionais (equivalente a
            `get_percentual_realmente_respondido()`).

          - `percentual_geral`: percentual considerando **todos** os indicadores
            aplicáveis (equivalente a `get_percentual_respondido()` sem filtros).

        Parâmetros:
            respondente (Respondente): Instância do respondente cujo questionário
                está sendo processado.
            dados (dict): Mapeamento `{identificador: valor}` onde o identificador
                segue o padrão `"indicador_id::respondente_id::variavel_id::content_type_id::object_id"`.
                O `valor` pode ser string simples, tupla/lista (será normalizado com
                `'::'.join(...)`) ou valor contendo marcador de Likert no formato
                `"nivel_escala_id___nivel"`.
            finalizar (bool, opcional): Quando True, marca o respondente como
                `finalizado` ao término do processamento. Padrão: False.

        Retorno:
            ProcessarResult: Dicionário tipado contendo:
                - `percentual` (int): percentual ignorando automáticos e opcionais.
                - `finalizado` (bool): status após o processamento.

        Exceções:
            ValidationError: Quando o identificador de nível de escala Likert não
                existir na base.

        Observações:
            - Respostas com `valor` nulo ou vazio não são contabilizadas no
              numerador dos percentuais.
            - A operação é atômica: em caso de falha, nenhuma alteração parcial
              permanece no banco.
        """
        Resposta.objects.filter(respondente=respondente).delete()
        for identificador, valor in dados.items():
            if '::' in identificador:
                indicador_id, respondente_id, variavel_id, content_type_id, object_id = identificador.split('::')

                if valor is not None:
                    if isinstance(valor, list | tuple):
                        if len(valor) == 1:
                            valor.append('')
                        valor = '::'.join(valor)

                    nivel_escala_id = None
                    if '___' in valor:
                        nivel_escala_id, nivel_escala_nivel = valor.split('___')
                        valor = str(nivel_escala_nivel)
                        try:
                            nivel_escala_id = int(nivel_escala_id)
                        except ValueError:
                            raise ValidationError('Erro inesperado! Identificador do nível de escala inválido.')
                        if not NivelEscalaLikert.objects.filter(id=nivel_escala_id).exists():
                            raise ValidationError(
                                'Erro inesperado! Identificador do nível de escala Likert não encontrado. '
                                'Entre em contato com a equipe de suporte técnico.'
                            )

                    Resposta.objects.create(
                        indicador_id=int(indicador_id),
                        respondente_id=int(respondente_id),
                        variavel_id=int(variavel_id) or None,
                        content_type_id=int(content_type_id) or None,
                        object_id=int(object_id) or None,
                        identificador=identificador,
                        nivel_escala_id=nivel_escala_id,
                        valor=str(valor),
                    )
        if finalizar:
            respondente.finalizado = True
            # registra apenas campos alterados
            respondente.save(update_fields=['finalizado', 'atualizado_em'])

        # Persistido, e não `commit=False`: é este campo que a tela inicial ("Fique atento!")
        # e o filtro "Respondido 100% mas não enviados" leem depois.
        percentual = respondente.atualizar_percentual_resposta()

        return {
            'percentual': percentual,
            'finalizado': bool(respondente.finalizado),
        }

    @staticmethod
    def get(
        respostas: QuerySet[Resposta],
        segmentos: QuerySet[Segmento] | None = None,
        areas_vinculacao: QuerySet[AreaVinculacao] | None = None,
        uos: QuerySet[UnidadeOrganizacional] | None = None,
        modalidades: QuerySet[Modalidade] | None = None,
        cursos: QuerySet[CursoCampus] | None = None,
    ) -> QuerySet[Resposta]:
        """
        Aplica filtros opcionais sobre um queryset de respostas e retorna um
        novo queryset de `Resposta` ordenado por `respondente` e sem duplicidades.

        Os filtros são aplicados somente quando o queryset correspondente é
        fornecido e possui elementos (`.exists()`), evitando junções e cláusulas
        desnecessárias.

        Parâmetros:
            respostas (QuerySet[Resposta]): QuerySet base a ser filtrado.
            segmentos (QuerySet[Segmento] | None): Filtra pelas instâncias de
                `Segmento` associadas ao respondente.
            areas_vinculacao (QuerySet[AreaVinculacao] | None): Filtra pelas
                áreas de vinculação do setor do vínculo do usuário respondente.
            uos (QuerySet[UnidadeOrganizacional] | None): Filtra pelas unidades
                organizacionais (campi) do respondente.
            modalidades (QuerySet[Modalidade] | None): Filtra pelas modalidades
                dos cursos relacionados ao respondente.
            cursos (QuerySet[CursoCampus] | None): Filtra pelos cursos (curso/campus)
                relacionados ao respondente.

        Retorno:
            QuerySet[Resposta]: QuerySet filtrado, ordenado por `respondente` e
            com `distinct()` aplicado.

        Observações:
            - Quando um filtro é informado, utiliza-se `values_list(..., flat=True)`
              para restringir a cláusula `IN` aos identificadores relevantes.
            - A ordenação é feita por `respondente`, e `distinct()` garante a
              eliminação de duplicidades decorrentes das junções.
        """
        if segmentos is not None and segmentos.exists():
            respostas = respostas.filter(respondente__segmento__in=segmentos)

        if areas_vinculacao is not None and areas_vinculacao.exists():
            respostas = respostas.filter(respondente__user__vinculo__setor__areas_vinculacao__in=areas_vinculacao.values_list('id', flat=True))

        if uos is not None and uos.exists():
            respostas = respostas.filter(respondente__uo__in=uos.values_list('id', flat=True))

        if modalidades is not None and modalidades.exists():
            respostas = respostas.filter(
                respondente__user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__modalidade__in=modalidades.values_list('id', flat=True)
            )

        if cursos is not None and cursos.exists():
            respostas = respostas.filter(
                respondente__user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__in=cursos.values_list('id', flat=True)
            )

        return respostas.order_by('respondente').distinct()
