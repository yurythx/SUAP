from __future__ import annotations

import hashlib
import io
import logging
import tempfile
from collections import Counter, defaultdict
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import qrcode
from django.apps import apps
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count, DateTimeField, Exists, ExpressionWrapper, F, OuterRef, Q, Value
from django.db.models.aggregates import Sum
from django.db.models.functions import Coalesce

from comum.models import Configuracao as Config
from comum.models import User, Vinculo
from comum.utils import get_uo
from djtools.db import models
from djtools.templatetags.filters import format_daterange, format_datetime, format_iterable, in_group
from djtools.utils import check_pdf, gerar_documento_impressao, somar_dias, text_extraction, text_similarity
from eventos.decorators import registra_atualizado_por
from eventos.enums import (
    EtapaPeriodoSubmissao,
    FormaParticipacaoEvento,
    Nacionalidade,
    Recomendacao,
    ResultadoAvaliacao,
    SituacaoConvite,
    SituacaoSubmissao,
    TipoLimitePorTexto,
    TipoPergunta,
    TipoQuestionario,
    TipoSubmissao,
)
from eventos.utils import Notificar
from rh.models import Servidor, Setor, UnidadeOrganizacional

# Constantes para tipos de participação
TIPO_PARTICIPACAO_ORGANIZADOR = 'Organizador'
TIPO_PARTICIPACAO_MONITOR = 'Monitor'
TIPO_PARTICIPACAO_AVALIADOR = 'Avaliador de trabalho'


class Natureza(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)

    class Meta:
        verbose_name = 'Natureza de Eventos'
        verbose_name_plural = 'Naturezas de Eventos'

    def __str__(self):
        return self.descricao


class Dimensao(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)
    publico_alvo_requerido = models.ManyToManyField(
        'PublicoAlvoEvento',
        verbose_name='Público Alvo',
        blank=True,
        help_text='Informe apenas se o público alvo for obrigatório para cadastro do evento.',
    )
    grupos_avaliadores_locais = models.ManyToManyFieldPlus('auth.Group', verbose_name='Grupos Avaliadores Locais', related_name='s1', blank=True)
    grupos_avaliadores_sistemicos = models.ManyToManyFieldPlus(
        'auth.Group', verbose_name='Grupos Avaliadores Sistêmicos', related_name='s2', blank=True
    )

    class Meta:
        verbose_name = 'Dimensão'
        verbose_name_plural = 'Dimensões'

    def __str__(self):
        return self.descricao

    @classmethod
    def is_avaliador_sistemico(cls, user):
        grupos_avaliadores_sistemicos = cls.objects.values_list('grupos_avaliadores_sistemicos', flat=True)
        return user.groups.filter(pk__in=grupos_avaliadores_sistemicos).exists()

    @classmethod
    def is_avaliador_local(cls, user):
        grupos_avaliadores_locais = cls.objects.values_list('grupos_avaliadores_locais', flat=True)
        return user.groups.filter(pk__in=grupos_avaliadores_locais).exists()


class TipoEvento(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)

    class Meta:
        verbose_name = 'Tipo de Eventos'
        verbose_name_plural = 'Tipos de Eventos'

    def __str__(self):
        return self.descricao


class PorteEvento(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    detalhamento = models.TextField(verbose_name='Detalhamento')

    class Meta:
        verbose_name = 'Porte'
        verbose_name_plural = 'Portes'

    def __str__(self):
        return self.descricao


class SubtipoEvento(models.ModelPlus):
    tipo = models.ForeignKeyPlus(TipoEvento, verbose_name='Tipo')
    nome = models.CharField('Nome', max_length=50)
    detalhamento = models.TextField('Descrição')
    multiplas_atividades = models.BooleanField('Múltiplas Atividades', default=False)

    class Meta:
        verbose_name = 'Subtipo de Eventos'
        verbose_name_plural = 'Subtipos de Eventos'

    def __str__(self):
        return self.nome


class ClassificacaoEvento(models.ModelPlus):
    descricao = models.CharField('Descrição', max_length=50)
    detalhamento = models.TextField('Detalhamento', null=True, blank=True)

    class Meta:
        verbose_name = 'Classificação de Eventos'
        verbose_name_plural = 'Classificações de Eventos'

    def __str__(self):
        return self.descricao


class EspacialidadesManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset()


class EspacialidadesAtivasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativa=True)


class Espacialidade(models.ModelPlus):
    objects = EspacialidadesManager()
    ativas = EspacialidadesAtivasManager()

    descricao = models.CharField('Descrição', max_length=50)
    ativa = models.BooleanField('Ativa?', default=True)
    ambiente_virtual = models.BooleanField('Ambiente Virtual?', default=False)

    class Meta:
        verbose_name = 'Espacialidade'
        verbose_name_plural = 'Espacialidades'

    def __str__(self):
        return self.descricao


class PublicoAlvoEvento(models.ModelPlus):
    ESTUDANTES = 1
    SERVIDORES = 2
    PAIS_E_RESPONSAVEIS = 3
    PUBLICO_EXTERNO = 4
    EMPRESARIOS = 5
    GESTORES = 6
    TERCEIRIZADOS = 7
    ESTAGIARIOS = 8
    BOLSISTAS = 9

    descricao = models.CharField('Descrição', max_length=50)
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Público Alvo de Eventos'
        verbose_name_plural = 'Públicos Alvo de Eventos'

    def __str__(self):
        return self.descricao

    @classmethod
    def valores_validos(cls):
        return [
            cls.ESTUDANTES,
            cls.SERVIDORES,
            cls.PAIS_E_RESPONSAVEIS,
            cls.PUBLICO_EXTERNO,
            cls.EMPRESARIOS,
            cls.GESTORES,
            cls.TERCEIRIZADOS,
            cls.ESTAGIARIOS,
            cls.BOLSISTAS,
        ]


class ParticipanteQuerySet(models.QuerySet):
    def com_avaliacao_realizada(self):
        respostas_avaliacao = RespostaParticipante.objects.filter(
            participante=OuterRef('pk'),
            pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
        )
        return self.annotate(avaliacao_realizada=Exists(respostas_avaliacao))


class AreaTematica(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    ativa = models.BooleanField(verbose_name='Ativa', default=True)
    evento = models.ForeignKeyPlus(
        'eventos.Evento',
        verbose_name='Evento',
        on_delete=models.CASCADE,
        related_name='evento_areas_tematicas',
        null=True,
        blank=True,
        help_text='Ao informar um evento, a área termática ficará disponível apenas para este evento.',
    )

    class Meta:
        verbose_name = 'Área temática'
        verbose_name_plural = 'Áreas temáticas'

    def __str__(self):
        return f'{self.titulo}'

    def clean(self):
        super().clean()
        # Verifica se já existe uma área temática com o mesmo título
        # para o mesmo evento (se evento for definido) ou globalmente (se evento for nulo).
        query = AreaTematica.objects.filter(titulo=self.titulo)
        if self.evento:
            query = query.filter(evento=self.evento)
        else:
            query = query.filter(evento__isnull=True)

        if self.pk:  # Exclui a própria instância em caso de edição
            query = query.exclude(pk=self.pk)

        if query.exists():
            if self.evento:
                raise ValidationError({'titulo': 'Já existe uma área temática com este título para este evento.'})
            else:
                raise ValidationError({'titulo': 'Já existe uma área temática com este título.'})


class TipoModalidade(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    ativa = models.BooleanField(verbose_name='Ativa', default=True)
    evento = models.ForeignKeyPlus(
        'eventos.Evento',
        verbose_name='Evento',
        on_delete=models.CASCADE,
        related_name='tipos_modalidade',
        null=True,
        blank=True,
        help_text='Ao informar um evento, o tipo de modalidade ficará disponível apenas para este evento.',
    )

    class Meta:
        verbose_name = 'Tipo de Modalidade'
        verbose_name_plural = 'Tipos de Modalidade'

    def __str__(self):
        return f'{self.titulo}'


@registra_atualizado_por
class Modalidade(models.ModelPlus):
    tipo = models.ForeignKeyPlus('eventos.TipoModalidade', verbose_name='Tipo de Modalidade')
    evento = models.ForeignKeyPlus('eventos.Evento', verbose_name='Evento')
    tipo_submissao = models.CharFieldPlus('Tipo de submissão', max_length=3, choices=TipoSubmissao.choices)
    limite_submissoes = models.PositiveSmallIntegerField('Quantidade limite de submissões de trabalhos')
    regras_submissao = models.FileFieldPlus(
        upload_to='eventos/regras_submissao/',
        null=True,
        blank=True,
        verbose_name='Regras de submissão',
        filetypes=['pdf'],
        help_text='Arquivo do tipo .pdf, contendo regras de submissão dos trabalhos.',
    )
    regras_avaliacao = models.FileFieldPlus(
        upload_to='eventos/regras_avaliacao/',
        null=True,
        blank=True,
        verbose_name='Regras de avaliação',
        filetypes=['pdf'],
        help_text='Arquivo do tipo .pdf, contendo regras de avaliação dos trabalhos.',
    )
    tipo_limite_por_texto = models.CharFieldPlus(
        'Limitar texto por quantidade de', max_length=1, null=True, blank=True, choices=TipoLimitePorTexto.choices
    )
    limite_por_texto = models.PositiveSmallIntegerField('Quantidade limite de palavras/caracteres nos trabalhos', null=True, blank=True)
    tipo_arquivos_permitidos = models.ManyToManyField('comum.TipoArquivo')
    ultima_atualizacao_por = models.CurrentUserField(null=True, blank=True)
    ultima_atualizacao_em = models.DateTimeFieldPlus(auto_now=True, null=True, blank=True)
    template = models.FileFieldPlus(
        upload_to='eventos/templates_submissao/',
        null=True,
        blank=True,
        verbose_name='Template para submissão',
        filetypes=['docx', 'pdf', 'ppt', 'canva'],
        help_text='Arquivo do tipo .docx, .pdf, .ppt ou .canva contendo o template para submissão dos trabalhos.',
    )

    class Meta:
        verbose_name = 'Modalidade'
        verbose_name_plural = 'Modalidades'

    def __str__(self):
        return f'{self.pk} - {self.tipo.titulo}'

    def extensoes_permitidas(self):
        if self.tipo_arquivos_permitidos.exists():
            extensoes_permitidas = self.tipo_arquivos_permitidos.all().values_list('extensoes', flat=True)
            return [ext.strip().lower() for extensao in extensoes_permitidas for ext in extensao.split(',')]

    def get_tipo_submissao_formatado(self):
        conteudo = []
        conteudo.append(self.get_tipo_submissao_display())
        if self.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO and self.limite_por_texto:
            conteudo.append(f' (Limite de {self.limite_por_texto} {self.get_tipo_limite_por_texto_display()})')
        else:
            if self.tipo_arquivos_permitidos.exists():
                arquivos_permitidos = self.tipo_arquivos_permitidos.all().values_list('nome', flat=True)
                arquivos_permitidos = ', '.join(list(arquivos_permitidos))
                conteudo.append(f' ({arquivos_permitidos})')
        return ''.join(conteudo)

    @property
    def areas_tematicas(self):
        area_tematica_ids = self.areatematicamodalidade_set.values_list('area_tematica', flat=True)
        return AreaTematica.objects.filter(pk__in=area_tematica_ids)

    def limite_submissoes_atingido(self):
        qtd_submissoes = Submissao.objects.filter(modalidade=self).count()
        return qtd_submissoes >= self.limite_submissoes

    def eh_submissao_por_texto(self):
        return self.tipo_submissao == TipoSubmissao.TIPO_SUBMISSAO_TEXTO


class AreaTematicaModalidade(models.ModelPlus):
    area_tematica = models.ForeignKeyPlus('eventos.AreaTematica', verbose_name='Área temática')
    modalidade = models.ForeignKeyPlus('eventos.Modalidade', on_delete=models.CASCADE)
    limite_aprovados = models.PositiveIntegerField(verbose_name='Limite de aprovados', null=True, blank=True)

    class Meta:
        verbose_name = 'Área temática da modalidade'
        verbose_name_plural = 'Áreas temáticas da modalidade'
        unique_together = ('area_tematica', 'modalidade')

    def __str__(self):
        return f'{self.modalidade.tipo.titulo} - {self.area_tematica.titulo}'


@registra_atualizado_por
class Configuracao(models.ModelPlus):
    submissao_limite_autores = models.PositiveSmallIntegerField(verbose_name='Quantidade limite de autores')
    submissao_limite_trabalhos_pessoa = models.PositiveSmallIntegerField(verbose_name='Quantidade limite de submissões de trabalhos por pessoa')
    avaliacao_nota_aprovacao = models.PositiveSmallIntegerField(verbose_name='Nota mínima para aprovação')
    limite_avaliadores = models.PositiveSmallIntegerField(verbose_name='Quantidade limite de avaliadores por trabalho')
    ultima_atualizacao_por = models.CurrentUserField(null=True, blank=True)
    ultima_atualizacao_em = models.DateTimeFieldPlus(auto_now=True, null=True, blank=True)
    notificar_resultados_automaticamente = models.BooleanField(
        verbose_name='Notificar autores automaticamente após avaliação?',
        help_text='O sistema deve notificar resultados automaticamente aos autores após fim do período de avaliação?',
        default=False,
    )
    notificacao_realizada_em = models.DateTimeField(verbose_name='Data e hora da notificação de resultados', null=True, blank=True)
    notificacao_realizada_por = models.ForeignKeyPlus(
        settings.AUTH_USER_MODEL, verbose_name='Notificação realizada por', related_name='notificacao_realizada_por', null=True, blank=True
    )
    notificacao_realizada_automaticamente = models.BooleanField(verbose_name='Notificação realizada automaticamente', default=False)

    class Meta:
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'

    def __str__(self):
        return f'Configuração do evento {self.evento.nome}'

    def get_notificacao_realizada_por(self):
        return self.notificacao_realizada_por or 'Sistema'

    def registrar_notificacao(self, user=None, automatica=False):
        """
        Registra a data e quem realizou a notificação (usuário ou sistema).

        :param user: Usuário que realizou a notificação (None se foi automática).
        :param automatica: Define se a notificação foi feita automaticamente pelo sistema.
        """
        self.notificacao_realizada_em = datetime.today()
        self.notificacao_realizada_por = user
        self.notificacao_realizada_automaticamente = automatica
        self.save(update_fields=['notificacao_realizada_em', 'notificacao_realizada_por', 'notificacao_realizada_automaticamente'])


@registra_atualizado_por
class AvaliadorModalidade(models.ModelPlus):
    avaliador = models.ForeignKeyPlus('eventos.Participante', verbose_name='Participante')
    modalidade = models.ForeignKeyPlus('eventos.Modalidade', verbose_name='Modalidade')
    areas_tematicas = models.ManyToManyFieldPlus(AreaTematica, verbose_name='Áreas temáticas')
    ultima_atualizacao_por = models.CurrentUserField(null=True, blank=True)
    ultima_atualizacao_em = models.DateTimeFieldPlus(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Avaliador da modalidade'
        verbose_name_plural = 'Avaliadores da modalidade'
        unique_together = ('avaliador', 'modalidade')
        ordering = ('modalidade', 'avaliador')

    def __str__(self):
        return f'{self.avaliador} ({self.modalidade} - {self.areas_tematicas})'


class CriterioAvaliacao(models.ModelPlus):
    modalidade = models.ForeignKeyPlus('eventos.Modalidade', verbose_name='Modalidade')
    descricao = models.TextField('Descrição')
    nota_minima = models.DecimalFieldPlus(verbose_name='Nota mínima da avaliação')
    nota_maxima = models.DecimalFieldPlus(verbose_name='Nota máxima da avaliação')
    ordem_desempate = models.IntegerField(
        'Ordem para Desempate', null=True, help_text='Ordem 1 indica que o critério será o primeiro a ser considerado para desempate.'
    )
    etapa = models.CharFieldPlus(
        verbose_name='Etapa da avaliação',
        choices=EtapaPeriodoSubmissao.avaliacoes_choices,
        max_length=3,
        help_text='Critério aplicável somente a esta etapa de avaliação.',
        default=EtapaPeriodoSubmissao.AVALIACAO,
    )

    class Meta:
        verbose_name = 'Critério de avaliação'
        verbose_name_plural = 'Critérios de avaliação'
        ordering = ['modalidade', 'etapa', 'ordem_desempate']

    def __str__(self):
        return self.descricao

    def possui_itens_avaliados(self):
        return self.itemavaliacao_set.exists()

    def clean(self):
        if self.nota_minima and not (0 <= self.nota_minima <= 100):
            raise ValidationError({'nota_minima': 'A nota mínima da avaliação deve estar entre 0 e 100.'})
        if self.nota_maxima and not (0 <= self.nota_maxima <= 100):
            raise ValidationError({'nota_maxima': 'A nota máxima da avaliação deve estar entre 0 e 100.'})


class AvaliacaoSubmissaoQuerySet(models.QuerySet):
    def avaliados(self):
        return self.filter(recomendacao__isnull=False)


class AvaliacaoSubmissao(models.ModelPlus):
    avaliador_modalidade = models.ForeignKeyPlus('eventos.AvaliadorModalidade', verbose_name='Avaliador da Modalidade')
    versao = models.ForeignKeyPlus('eventos.VersaoSubmissao', related_name='pareceres', on_delete=models.CASCADE, null=True, blank=True)
    nota = models.DecimalFieldPlus(verbose_name='Nota da avaliação', null=True, blank=True)
    data_hora_nota = models.DateTimeField(verbose_name='Data/Hora da nota', null=True, blank=True)
    observacao = models.TextField('Observação', blank=True, help_text='Este texto do avaliador será enviado aos autores.')
    observacao_interna = models.TextField(
        'Observação interna', blank=True, null=True, help_text='Este texto do avaliador enviado aos coordenadores do evento.'
    )
    recomendacao = models.SmallIntegerField(
        verbose_name='Recomendação',
        choices=Recomendacao.choices,
        null=True,
        blank=True,
        help_text='Recomendação final do avaliador com base na análise dos critérios.',
    )

    objects = AvaliacaoSubmissaoQuerySet.as_manager()

    class Meta:
        verbose_name = 'Avaliação da submissão'
        verbose_name_plural = 'Avaliações da submissão'
        ordering = ('versao', 'avaliador_modalidade')

    def __str__(self):
        return f'{self.avaliador_modalidade} ({self.versao.submissao} - {self.nota})'

    @property
    def estah_avaliado(self):
        return self.nota or self.nota == 0.0


class ItemAvaliacao(models.ModelPlus):
    avaliacao = models.ForeignKeyPlus('eventos.AvaliacaoSubmissao', verbose_name='Avaliação')
    criterio_avaliacao = models.ForeignKeyPlus('eventos.CriterioAvaliacao', verbose_name='Critério', on_delete=models.CASCADE)
    nota = models.DecimalFieldPlus(verbose_name='Nota da avaliação')
    data_hora_nota = models.DateTimeField(verbose_name='Data/Hora da nota', auto_now_add=True)

    def __str__(self):
        return f'Item da Avaliação: {self.avaliacao}'


class Submissao(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    modalidade = models.ForeignKeyPlus('eventos.Modalidade', verbose_name='Modalidade')
    area_tematica = models.ForeignKeyPlus('eventos.AreaTematica', verbose_name='Área Temática')
    arquivo = models.FileFieldPlus(upload_to='eventos/submissao/', null=True, blank=True, verbose_name='Arquivo')
    texto = models.TextField('Texto', null=True, blank=True)
    # autores = models.ManyToManyFieldPlus('eventos.Participante', verbose_name='Participantes', blank=True)
    data_hora = models.DateTimeField(auto_now_add=True, verbose_name='Data/Hora de Submissão')
    link_video = models.CharFieldPlus(
        verbose_name='Link para o vídeo', null=True, blank=True, help_text='Somente serão permitidas URLs para Youtube e Vimeo.'
    )
    nota_final = models.DecimalFieldPlus(verbose_name='Nota da avaliação', null=True, blank=True)
    resultado_avaliacao = models.CharFieldPlus('Resultado da Avaliação', max_length=3, null=True, blank=True, choices=ResultadoAvaliacao.choices)
    data_hora_exclusao_arquivo = models.DateTimeField(verbose_name='Data/Hora de exclusão do arquivo', null=True, blank=True)
    situacao = models.CharFieldPlus('Situação da submissão', max_length=5, choices=SituacaoSubmissao.choices, default=SituacaoSubmissao.SUBMETIDO)
    conteudo_extraido = models.TextField(
        'Conteúdo extraído do arquivo',
        null=True,
        blank=True,
        help_text='Texto extraído automaticamente do arquivo PDF/DOCX para análise de duplicidade.',
    )
    processamento_extracao = models.JSONField(
        'Resultado do processamento de extração',
        null=True,
        blank=True,
        default=list,
        help_text='Lista de registros em JSON com informações sobre os processos de extração (sucesso/erro, mensagens, traceback, timestamps).',
    )
    motivo_remocao = models.TextField(
        'Motivo da remoção', null=True, blank=True, help_text='Justificativa para remoção da submissão por duplicidade.'
    )

    class Meta:
        verbose_name = 'Submissão'
        verbose_name_plural = 'Submissões'
        ordering = ('modalidade', 'area_tematica', 'titulo')

    def __str__(self):
        return f'{self.titulo} ({self.modalidade} - {self.area_tematica})'

    def save(self, *args, **kwargs):
        retorno = super().save(*args, **kwargs)
        if not self.versoes.exists():
            VersaoSubmissao.objects.create(submissao=self, numero=1, arquivo=self.arquivo, texto=self.texto, etiqueta='Versão Inicial')
        return retorno

    def get_avaliador_modalidade(self):
        ultima_versao = self.versoes.first()
        return [parecer.avaliador_modalidade for parecer in ultima_versao.pareceres.all()] if ultima_versao else []

    def possui_avaliacao_pendente(self):
        ultima_versao = self.versoes.first()
        if not ultima_versao:
            return False
        pareceres = ultima_versao.pareceres.all()
        total = pareceres.count()
        avaliadas = pareceres.filter(nota__isnull=False).count()
        return total != avaliadas

    def get_ultimos_avaliadores(self):
        ultima_versao = self.versoes.first()
        if not ultima_versao:
            return []
        return ultima_versao.pareceres.all()

    @property
    def media_notas(self):
        versao_submissao = self.get_ultima_versao()
        avaliadores = AvaliacaoSubmissao.objects.filter(versao=versao_submissao).count()
        notas = AvaliacaoSubmissao.objects.filter(versao=versao_submissao, nota__isnull=False).values_list('nota', flat=True)
        total_notas = len(notas)
        if total_notas == 0:
            return None
        return sum(notas) / avaliadores

    @classmethod
    def listar_resultado(cls, area_tematica_modalidade, aprovados=True):
        filtro_base = {
            'modalidade_id': area_tematica_modalidade.modalidade_id,
            'area_tematica_id': area_tematica_modalidade.area_tematica_id,
        }

        if aprovados:
            filtro_base['resultado_avaliacao'] = ResultadoAvaliacao.APROVADO
            queryset = cls.objects.filter(**filtro_base).values('id', 'titulo', 'nota_final').order_by('-nota_final')
        else:
            queryset = (
                cls.objects.filter(**filtro_base)
                .exclude(resultado_avaliacao=ResultadoAvaliacao.APROVADO)
                .values('id', 'titulo', 'nota_final')
                .order_by('-nota_final')
            )

        criterios_desempate = CriterioAvaliacao.objects.filter(modalidade_id=area_tematica_modalidade.modalidade_id).order_by('ordem_desempate')
        submissoes = []
        for submissao in queryset:
            submissao_obj = cls.objects.get(id=submissao['id'])
            ultima_versao = submissao_obj.versoes.first()

            autores = [
                f'{autor_submissao.participante.nome} ({autor_submissao.get_tipo_autor_display()})'
                for autor_submissao in submissao_obj.autores_relacionados.all()
            ]

            submissao_dict = {
                'id': submissao['id'],
                'titulo': submissao['titulo'],
                'autores': autores,
                'nota_final': submissao['nota_final'],
            }
            for criterio in criterios_desempate:
                soma_notas_criterio = ItemAvaliacao.objects.filter(avaliacao__versao=ultima_versao, criterio_avaliacao=criterio).aggregate(
                    Sum('nota')
                )['nota__sum']
                submissao_dict[criterio.ordem_desempate] = soma_notas_criterio

            submissoes.append(submissao_dict)

        criterios = ['nota_final', *list(criterios_desempate.values_list('ordem_desempate', flat=True))]

        def chave_de_ordenacao(dicionario):
            return tuple(Decimal(dicionario.get(criterio, 0) or 0) for criterio in criterios)

        submissoes = sorted(submissoes, key=chave_de_ordenacao, reverse=True)
        # `limite_aprovados` é anulável; o `None > 0` estourava `TypeError` (500) para uma
        # área/modalidade sem limite definido.
        limite = area_tematica_modalidade.limite_aprovados or 0
        if limite > 0:
            submissoes = submissoes[:limite]

        return submissoes

    def estah_aguardando_nova_versao(self):
        """
        Verifica se a submissão está aguardando uma nova versão.
        """
        return self.situacao == SituacaoSubmissao.CORRECOES_SOLICITADAS and self.modalidade.evento.estah_em_periodo_de_correcoes()

    @classmethod
    @transaction.atomic
    def notificar_resultado_avaliacao(cls, evento, area_tematica_modalidade_ids=None, notificar_todos=False):
        """
        Método para notificar os autores sobre o resultado da avaliação.

        :param evento: Instância do evento ao qual as submissões pertencem.
        :param area_tematica_modalidade_ids: Lista de IDs das áreas temáticas a serem notificadas (usado apenas na view).
        :param notificar_todos: Se True, também notifica os trabalhos reprovados (usado apenas na view).
        """

        if area_tematica_modalidade_ids:
            areas_tematicas = AreaTematicaModalidade.objects.filter(pk__in=area_tematica_modalidade_ids)
        else:
            areas_tematicas = AreaTematicaModalidade.objects.filter(modalidade__evento=evento)

        notificou = 0

        for area_tematica_modalidade in areas_tematicas:
            # Notifica os trabalhos aprovados
            submissoes_aprovadas = cls.listar_resultado(area_tematica_modalidade, True)
            for item in submissoes_aprovadas:
                submissao = cls.objects.get(id=item['id'])
                Notificar.trabalhos_aprovados(submissao)
                for participante in submissao.autores:
                    autor_novo = participante.cria_autor_de_trabalho()
                    if autor_novo.id != participante.id:
                        # Substitui o autor antigo pelo novo na submissão
                        AutorSubmissao.objects.filter(submissao=submissao, participante=participante).update(participante=autor_novo)
                notificou += 1

            if notificar_todos:
                submissoes_reprovadas = cls.listar_resultado(area_tematica_modalidade, False)
                for item in submissoes_reprovadas:
                    submissao = cls.objects.get(id=item['id'])
                    Notificar.trabalhos_reprovados(submissao)
                    notificou += 1

        return notificou

    @property
    def autores(self):
        """
        Retorna a lista de participantes autores dessa submissão.
        """
        return [autor.participante for autor in self.autores_relacionados.all()]

    def get_ultima_versao(self):
        """
        Retorna a última versão da submissão.
        """
        return self.versoes.order_by('-id').first()

    def get_autor_correspondente(self):
        """
        Retorna o autor correspondente da submissão.
        """
        autor = self.autores_relacionados.filter(autor_correspondente=True).first()
        return autor.participante if autor else None

    def extrair_conteudo_arquivo(self):
        """
        Extrai o conteúdo textual de arquivos PDF ou DOCX da primeira versão da submissão.
        Armazena o texto extraído no campo conteudo_extraido.

        Returns:
            str: Texto extraído ou None se não houver arquivo ou erro na extração
        """
        primeira_versao = self.versoes.filter(numero=1).first()
        if not primeira_versao or not primeira_versao.arquivo:
            return None

        resultado = {
            'timestamp': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'status': None,
            'mensagens': [],
            'exception': None,
            'extracted_chars': 0,
        }
        try:
            conteudo = text_extraction.extrair_texto_documento(arquivo=primeira_versao.arquivo, normalizar=True)

            if conteudo:
                self.conteudo_extraido = conteudo
                self.save(update_fields=['conteudo_extraido'])
                resultado['status'] = 'sucesso'
                resultado['mensagens'].append('Conteúdo extraído com sucesso')
                resultado['extracted_chars'] = len(conteudo)
                # Acumula logs em lista
                if not isinstance(self.processamento_extracao, list):
                    self.processamento_extracao = []
                self.processamento_extracao.append(resultado)
                self.save(update_fields=['processamento_extracao'])
                return self.conteudo_extraido

            # Nenhum conteúdo extraído (vazio)
            resultado['status'] = 'vazio'
            resultado['mensagens'].append('Nenhum conteúdo extraído (resultado vazio)')
            # Acumula logs em lista
            if not isinstance(self.processamento_extracao, list):
                self.processamento_extracao = []
            self.processamento_extracao.append(resultado)
            self.save(update_fields=['processamento_extracao'])
            return None

        except Exception as e:
            import traceback

            tb = traceback.format_exc()
            resultado['status'] = 'erro'
            resultado['exception'] = {'msg': str(e), 'traceback': tb}
            resultado['mensagens'].append(f'Erro ao extrair conteúdo: {e!s}')
            # Persiste o resultado para diagnóstico
            try:
                # Acumula logs em lista
                if not isinstance(self.processamento_extracao, list):
                    self.processamento_extracao = []
                self.processamento_extracao.append(resultado)
                self.save(update_fields=['processamento_extracao'])
            except Exception:
                # Se falhar ao salvar, apenas logamos (não re-raise)
                logging.getLogger(__name__).exception('Falha ao persistir processamento_extracao para submissão %s', self.id)

            # Também loga para os logs padrão
            logging.getLogger(__name__).error('Erro ao extrair conteúdo da submissão %s: %s', self.id, str(e), exc_info=True)

        return None

    def calcular_similaridade_titulo(self, outra_submissao):
        """
        Calcula a similaridade entre títulos usando SequenceMatcher.

        Returns:
            float: Valor entre 0 e 1 indicando similaridade
        """
        return text_similarity.calcular_similaridade_strings(self.titulo, outra_submissao.titulo, case_sensitive=False)

    def calcular_similaridade_conteudo(self, outra_submissao):
        """
        Calcula a similaridade entre conteúdos usando TF-IDF e similaridade de cosseno.

        Args:
            outra_submissao: Outra instância de Submissao para comparar

        Returns:
            float: Valor entre 0 e 1 indicando similaridade
        """
        return text_similarity.calcular_similaridade_textos(self.conteudo_extraido, outra_submissao.conteudo_extraido, metodo='tfidf')

    def pode_restaurar(self):
        """
        Verifica se a submissão removida por duplicidade pode ser restaurada.
        """
        return self.situacao == SituacaoSubmissao.REMOVIDO_DUPLICIDADE


class VersaoSubmissao(models.ModelPlus):
    submissao = models.ForeignKeyPlus('eventos.Submissao', related_name='versoes', on_delete=models.CASCADE)
    numero = models.PositiveSmallIntegerField('Número da versão')
    arquivo = models.FileFieldPlus(upload_to='eventos/submissao/versoes/', null=True, blank=True, verbose_name='Arquivo')
    texto = models.TextField('Texto', null=True, blank=True)
    comentario = models.TextField('Comentário do autor', null=True, blank=True)
    enviado_em = models.DateTimeFieldPlus('Data de envio', auto_now_add=True)
    etiqueta = models.CharField('Etiqueta da versão', max_length=100, null=True, blank=True)

    class Meta:
        verbose_name = 'Versão da submissão'
        verbose_name_plural = 'Versões da submissão'
        ordering = ('submissao', '-numero')

    def __str__(self):
        return f'{self.submissao} - Versão {self.numero}'

    def calcular_decisao_final(self):
        """
        Retorna a decisão final com base na soma das recomendações:
        +1 (Aceitar), 0 (Corrigir), -1 (Rejeitar).
        """
        pareceres = self.pareceres.filter(recomendacao__isnull=False)
        total_pontos = sum([p.recomendacao for p in pareceres])
        if total_pontos >= 1:
            return ResultadoAvaliacao.APROVADO
        return ResultadoAvaliacao.REPROVADO

    def tem_versao_nova(self):
        """
        Verifica se existe uma versão nova da submissão.
        """
        return self.submissao.versoes.filter(numero__gt=self.numero).exists()

    def pode_visualizar_pareceres(self):
        """
        Verifica se o usuário pode visualizar os pareceres.
        """
        return self.submissao.modalidade.evento.estah_em_periodo_de_correcoes() or self.submissao.modalidade.evento.pode_divulgar_resultado_final()


@registra_atualizado_por
class FluxoSubmissao(models.ModelPlus):
    evento = models.ForeignKeyPlus('eventos.Evento', on_delete=models.CASCADE, related_name='fluxos_submissao')
    etapa = models.CharFieldPlus('Etapa do período', max_length=3, choices=EtapaPeriodoSubmissao.choices, default=EtapaPeriodoSubmissao.SUBMISSAO)
    data_inicio = models.DateFieldPlus('Data inicial')
    data_fim = models.DateFieldPlus('Data final', null=True, blank=True)
    ultima_atualizacao_por = models.CurrentUserField(null=True, blank=True)
    ultima_atualizacao_em = models.DateTimeFieldPlus(auto_now=True, null=True, blank=True)

    class Meta:
        verbose_name = 'Fluxo de submissão'
        verbose_name_plural = 'Fluxos de submissão'
        ordering = ('data_inicio', 'data_fim')

    def __str__(self):
        return f'{self.evento} - {self.get_etapa_display()} ({format_daterange(self.data_inicio, self.data_fim)})'

    def get_periodo(self):
        if self.etapa == EtapaPeriodoSubmissao.RESULTADO_FINAL:
            return f'{self.data_inicio.strftime("%d/%m/%Y")}'
        return f'{format_daterange(self.data_inicio, self.data_fim)}'

    def pode_editar_ou_remover(self):
        """
        Verifica se o usuário pode editar o fluxo de submissão, com base na data atual, ou seja, para editar a data de fim deve ser maior ou igual que hoje.
        """
        return self.data_fim is None or self.data_fim >= datetime.today().date()


class AutorSubmissao(models.Model):
    """
    Representa a relação entre uma submissão e seus autores, armazenando o tipo de autor.
    """

    AUTOR = 'autor'
    ORIENTADOR = 'orientador'
    COORIENTADOR = 'coorientador'

    TIPOS_AUTOR = [
        (AUTOR, 'Autor'),
        (ORIENTADOR, 'Orientador'),
        (COORIENTADOR, 'Coorientador'),
    ]

    submissao = models.ForeignKey('eventos.Submissao', on_delete=models.CASCADE, related_name='autores_relacionados')
    participante = models.ForeignKey('eventos.Participante', on_delete=models.CASCADE, verbose_name='Participante')
    tipo_autor = models.CharField('Tipo de Autor', max_length=20, choices=TIPOS_AUTOR, default=AUTOR)
    autor_correspondente = models.BooleanField(
        'Autor correspondente',
        default=False,
        help_text='Marque este campo caso o autor seja o responsável pela comunicação com os avaliadores.',
    )

    class Meta:
        unique_together = ('submissao', 'participante')

    def __str__(self):
        texto = f'{self.participante.nome} - {self.get_tipo_autor_display()}'
        if self.autor_correspondente:
            texto += ' *'
        return texto


class Pergunta(models.ModelPlus):
    evento = models.ForeignKeyPlus('eventos.Evento', on_delete=models.CASCADE)
    ordem = models.IntegerField()
    titulo = models.TextField(verbose_name='Título da pergunta')
    tipo_pergunta = models.CharFieldPlus(
        verbose_name='Tipo da pergunta', max_length=5, choices=TipoPergunta.choices, default=TipoPergunta.SUBJETIVA_LONGA
    )
    tipo_questionario = models.CharFieldPlus(
        verbose_name='Tipo de questionário',
        max_length=4,
        choices=TipoQuestionario.choices,
        default=TipoQuestionario.INSCRICAO,
    )
    obrigatoria = models.BooleanField(verbose_name='Obrigatória', default=False)
    numerico = models.BooleanField(
        'Campo Numérico',
        blank=True,
        default=False,
        help_text='Marque este campo caso a resposta deva ser apenas numérica, em caso de pergunta subjetiva.',
    )

    class Meta:
        verbose_name = 'Pergunta'
        verbose_name_plural = 'Perguntas'
        ordering = ('ordem', 'id')

    def __str__(self):
        return self.titulo

    def eh_objetiva_ou_multipla_escolha(self):
        return self.tipo_pergunta in [TipoPergunta.OBJETIVA, TipoPergunta.MULTIPLA_ESCOLHA, TipoPergunta.ESCALA]


class OpcaoResposta(models.ModelPlus):
    evento = models.ForeignKeyPlus('eventos.Evento', on_delete=models.CASCADE)
    pergunta = models.ForeignKeyPlus('eventos.Pergunta', on_delete=models.CASCADE, null=True, blank=True)
    ordem = models.IntegerField()
    texto = models.TextField()

    class Meta:
        verbose_name_plural = 'Opção de resposta'
        verbose_name = 'Opções de resposta'
        ordering = ('ordem',)

    def __str__(self):
        return self.texto


class RespostaParticipante(models.ModelPlus):
    participante = models.ForeignKeyPlus('eventos.Participante', on_delete=models.CASCADE)
    opcao_resposta = models.ForeignKeyPlus('eventos.OpcaoResposta', on_delete=models.CASCADE, null=True, blank=True)
    pergunta = models.ForeignKeyPlus('eventos.Pergunta', on_delete=models.CASCADE, null=True, blank=True)
    resposta_texto = models.TextField(verbose_name='Resposta em texto', null=True, blank=True)
    resposta_numero = models.IntegerField(verbose_name='Resposta em número', null=True, blank=True)

    class Meta:
        verbose_name_plural = 'Resposta do participante'
        verbose_name = 'Respostas do participante'

    def __str__(self):
        return f'{self.participante.nome}'

    def get_respostas(self):
        if self.pergunta.tipo_pergunta in (TipoPergunta.OBJETIVA, TipoPergunta.ESCALA):
            return self.opcao_resposta.texto
        elif self.pergunta.tipo_pergunta == TipoPergunta.MULTIPLA_ESCOLHA:
            respostas = RespostaParticipante.objects.filter(participante=self.participante, pergunta=self.pergunta).values_list(
                'opcao_resposta__texto'
            )
            return ', '.join(resposta[0] for resposta in respostas)
        elif self.pergunta.numerico:
            return self.resposta_numero
        else:
            return self.resposta_texto


@registra_atualizado_por
class Evento(models.ModelPlus):
    nome = models.CharFieldPlus('Título do Evento', max_length=255, db_index=True, validate_caracter=True)
    apresentacao = models.TextField('Apresentação', help_text='Espaço para que sejam falados os objetivos principais etc.')
    imagem = models.ImageFieldPlus('Imagem', blank=True, null=True, help_text='Logotipo ou algo que ilustre o evento')
    local = models.CharFieldPlus(validate_caracter=True)
    data_inicio = models.DateFieldPlus('Data de Início')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    data_fim = models.DateFieldPlus('Data de Fim', null=True, blank=False)
    hora_fim = models.TimeFieldPlus('Hora de Fim', null=True, blank=False)
    data_inicio_inscricoes = models.DateFieldPlus('Início das Inscrições', null=True)
    hora_inicio_inscricoes = models.TimeFieldPlus('Hora de Início das Inscrições', null=True, blank=True)
    data_fim_inscricoes = models.DateFieldPlus('Fim das Inscrições', null=True)
    hora_fim_inscricoes = models.TimeFieldPlus('Hora de Fim das Inscrições', null=True, blank=True)
    carga_horaria_str = models.CharField('Carga Horária do Evento', null=True, blank=True, max_length=255, help_text='Carga Horária total do evento')
    carga_horaria = models.IntegerField(verbose_name='Carga Horária em segundos', null=True)
    coordenador = models.ForeignKeyPlus(Servidor, verbose_name='Coordenador', null=True, blank=True)
    campus = models.ForeignKeyPlus(
        UnidadeOrganizacional, verbose_name='Local de realização', related_name='campus_responsavel', on_delete=models.CASCADE
    )
    setor = models.ForeignKeyPlus(Setor, verbose_name='Setor do Coordenador', null=True, blank=True, on_delete=models.CASCADE)
    natureza = models.ManyToManyField(Natureza, verbose_name='Natureza')
    dimensoes = models.ManyToManyField(Dimensao, verbose_name='Dimensões')
    classificacao = models.ForeignKeyPlus(ClassificacaoEvento, verbose_name='Localização', null=True, blank=True, on_delete=models.CASCADE)
    espacialidades = models.ManyToManyField(Espacialidade, verbose_name='Espacialidades', related_name='espacialidades')
    porte = models.ForeignKeyPlus(PorteEvento, verbose_name='Porte', null=True)
    tipo = models.ForeignKeyPlus(TipoEvento, verbose_name='Tipo', null=True, on_delete=models.CASCADE)
    subtipo = models.ForeignKeyPlus(SubtipoEvento, verbose_name='Subtipo', null=True)
    servidores_envolvidos = models.PositiveIntegerField('Quantidade de Servidores Envolvidos na Organização', null=True, blank=True)
    qtd_participantes = models.PositiveIntegerField('Quantidade de Participantes', null=True, blank=True)
    publico_alvo = models.ManyToManyField(PublicoAlvoEvento, verbose_name='Público Alvo', blank=True)
    recursos = models.DecimalFieldPlus(
        'Recursos Envolvidos', null=True, blank=True, help_text='Valor em R$ do total de recurso público destinado a realização do evento'
    )
    site = models.CharFieldPlus(null=True, blank=True, verbose_name='Site', help_text='URL da página do evento')
    gera_certificado = models.BooleanField(
        'Gera Certificado?',
        blank=True,
        help_text='Marque essa opção caso deseje que certificados sejam emitidos e enviados por e-mail para os participantes após a realização do evento.',
    )
    exigir_avaliacao_para_certificado = models.BooleanField(
        'Exigir avaliação para certificado?',
        default=False,
        help_text='Marque essa opção caso deseje condicionar a emissão do certificado ao preenchimento da avaliação pós-evento.',
    )
    submetido = models.BooleanField('Submetido?', default=True)
    deferido = models.BooleanField('Deferido?', null=True)
    motivo_indeferimento = models.TextField('Motivo do Indeferimento', null=True)
    data_emissao_certificado = models.DateTimeField(null=True, blank=True, verbose_name='Data de Emissão do Certificado')
    ativo = models.BooleanField('Ativo?', default=False)
    finalizado = models.BooleanField('Finalizado?', default=False)
    cancelado = models.BooleanField('Cancelado?', default=False)

    ultima_atualizacao_por = models.CurrentUserField()
    ultima_atualizacao_em = models.DateTimeFieldPlus(auto_now=True)

    areas_tematicas = models.ManyToManyFieldPlus(AreaTematica, verbose_name='Áreas temáticas', related_name='eventos', blank=True)

    inscricao_publica = models.BooleanField(
        verbose_name='Inscrição Online',
        default=False,
        help_text='Marque essa opção caso deseje que as inscrições sejam realizadas pelos próprios participantes através do link "Realizar Inscrição em Evento" na tela de login do SUAP.',
    )

    registrar_presenca_online = models.BooleanField(
        verbose_name='Registrar Presença Online',
        default=False,
        help_text='Marque essa opção caso deseje que os próprios inscritos possam registrar presença através de um e-mail enviado pelo coordenador/organizador.',
    )

    configuracao = models.OneToOneFieldPlus('eventos.Configuracao', null=True, blank=True, verbose_name='Configuração')
    confirmacao_automatica_inscricao = models.BooleanField(
        'Confirmação automática de inscrição?',
        default=False,
        help_text='Marque essa opção caso deseje que as inscrições realizadas não precisem de uma confirmação de inscrição do organizador.',
    )
    utilizar_qr_code = models.BooleanField(
        'Utilizar QR Code?',
        default=False,
        help_text='Marque essa opção caso deseje encaminhar QR Code por participantes para confirmações de presença em seu evento.',
    )
    termo_aceite_condicoes = models.TextField('Termo de aceite e condições do evento', null=True, blank=True)
    capacitacao = models.BooleanField('É um evento de capacitação?', default=False, help_text='Marque essa opção caso o evento seja uma capacitação.')
    possui_cunho_social = models.BooleanField(
        'Possui cunho social?',
        default=False,
        help_text='Que visa dar resposta a uma ou mais questões sociais, de caráter humanitário, normalmente através de ações beneficentes.',
    )
    gerencia_pagina_institucional = models.BooleanField(
        'Deseja gerenciar uma página no Portal Institucional sobre esse evento?',
        default=False,
        help_text='Marque essa opção caso deseje que o evento tenha uma página institucional gerenciada pelo organizador.',
    )

    # Campos desnormalizados para otimização de performance
    possui_modalidades = models.BooleanField(
        'Possui modalidades cadastradas',
        default=False,
        editable=False,
        help_text='Campo calculado automaticamente. Indica se o evento possui modalidades.',
    )
    possui_configuracao_criterios_completa = models.BooleanField(
        'Possui configuração de critérios completa',
        default=False,
        editable=False,
        help_text='Campo calculado automaticamente. Indica se todos os critérios de avaliação estão configurados.',
    )
    possui_tipo_avaliador = models.BooleanField(
        'Possui tipo participante avaliador',
        default=False,
        editable=False,
        help_text='Campo calculado automaticamente. Indica se há tipo de participante avaliador.',
    )

    class Meta:
        verbose_name = 'Evento'
        verbose_name_plural = 'Eventos'

    def __str__(self):
        return self.nome

    def get_absolute_url(self):
        return f'/eventos/evento/{self.id}/'

    def save(self, *args, **kwargs):
        if self.data_fim is None:
            self.data_fim = self.data_inicio

        super().save(*args, **kwargs)

    def recalcular_flags_configuracao(self):
        """
        Recalcula e atualiza os campos desnormalizados de configuração.
        Deve ser chamado quando modalidades, critérios ou tipos de participante mudarem.
        """
        from django.db.models import Prefetch

        # 1. Verificar se possui modalidades
        self.possui_modalidades = self.modalidade_set.exists()

        # 2. Verificar se possui tipo participante avaliador
        self.possui_tipo_avaliador = self.tipos_participante.filter(tipo_participacao__descricao=TIPO_PARTICIPACAO_AVALIADOR).exists()

        # 3. Verificar configuração de critérios (versão otimizada)
        configurou = True
        if self.possui_modalidades:
            # Prefetch de critérios para evitar N+1
            modalidades = self.modalidade_set.prefetch_related(Prefetch('criterioavaliacao_set', queryset=CriterioAvaliacao.objects.all())).all()

            # Verificar se alguma modalidade não tem critérios
            tem_modalidade_sem_criterio = any(not modalidade.criterioavaliacao_set.all() for modalidade in modalidades)
            if tem_modalidade_sem_criterio:
                configurou = False
            else:
                # Verificar se existe critério para cada etapa de avaliação
                etapas_avaliacao = [choice[0] for choice in EtapaPeriodoSubmissao.avaliacoes_choices]
                etapas_fluxo = self.fluxos_submissao.filter(etapa__in=etapas_avaliacao).values_list('etapa', flat=True).distinct()

                # Criar dicionário de critérios por etapa
                criterios_por_etapa = set()
                for modalidade in modalidades:
                    for criterio in modalidade.criterioavaliacao_set.all():
                        criterios_por_etapa.add(criterio.etapa)

                # Verificar se todas as etapas têm critérios
                for etapa in etapas_fluxo:
                    if etapa not in criterios_por_etapa:
                        configurou = False
                        break
        else:
            configurou = False

        self.possui_configuracao_criterios_completa = configurou

        # Salvar apenas os campos calculados
        self.save(update_fields=['possui_modalidades', 'possui_configuracao_criterios_completa', 'possui_tipo_avaliador'])

    def _estah_em_periodo(self, etapas):
        """
        Método auxiliar para verificar se o evento está em período específico.

        Args:
            etapas: Lista de etapas ou etapa única para verificar

        Returns:
            bool: True se estiver no período especificado
        """
        hoje = date.today()
        if isinstance(etapas, list | tuple):
            etapas_set = set(etapas)
            return any(
                f.etapa in etapas_set and f.data_inicio <= hoje and f.data_fim is not None and f.data_fim >= hoje for f in self.fluxos_submissao.all()
            )
        else:
            return any(
                f.etapa == etapas and f.data_inicio <= hoje and f.data_fim is not None and f.data_fim >= hoje for f in self.fluxos_submissao.all()
            )

    def estah_em_periodo_submissao(self) -> bool:
        return self.get_situacao_por_periodo() != 'Finalizado' and self._estah_em_periodo(EtapaPeriodoSubmissao.SUBMISSAO)

    def estah_em_periodo_avaliacao(self):
        return self._estah_em_periodo(
            [EtapaPeriodoSubmissao.AVALIACAO, EtapaPeriodoSubmissao.REAVALIACAO, EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL]
        )

    def estah_em_periodo_avaliacao_remota(self):
        return self._estah_em_periodo([EtapaPeriodoSubmissao.AVALIACAO, EtapaPeriodoSubmissao.REAVALIACAO])

    def estah_em_periodo_avaliacao_presencial(self):
        return self._estah_em_periodo([EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL])

    def estah_em_periodo_realizacao(self):
        hoje = date.today()
        if self.hora_inicio and self.hora_fim:
            agora = datetime.now()
            data_hora_inicio = datetime.combine(self.data_inicio, self.hora_inicio)
            data_hora_fim = datetime.combine(self.data_fim, self.hora_fim)
            return data_hora_inicio <= agora <= data_hora_fim
        return self.data_inicio <= hoje <= self.data_fim

    def estah_em_periodo_de_correcoes(self):
        return self._estah_em_periodo(EtapaPeriodoSubmissao.CORRECOES)

    def estah_em_periodo_inscricao(self) -> bool:
        if self.get_situacao_por_periodo() == 'Finalizado':
            return False

        hoje = date.today()
        if self.data_inicio_inscricoes and self.data_fim_inscricoes:
            if self.hora_inicio_inscricoes and self.hora_fim_inscricoes:
                agora = datetime.now()
                data_hora_inicio_inscricoes = datetime.combine(self.data_inicio_inscricoes, self.hora_inicio_inscricoes)
                data_hora_fim_inscricoes = datetime.combine(self.data_fim_inscricoes, self.hora_fim_inscricoes)
                return data_hora_inicio_inscricoes <= agora <= data_hora_fim_inscricoes
            return self.data_inicio_inscricoes <= hoje <= self.data_fim_inscricoes
        return True

    def pode_divulgar_resultado_final(self):
        """
        Verifica se o resultado final pode ser divulgado.

        Este método verifica se há algum fluxo de submissão associado à instância atual
        cuja etapa seja "RESULTADO_FINAL" e cuja data de início seja menor ou igual à data de hoje.

        Returns:
            bool: Retorna True se existir pelo menos um fluxo de submissão que atenda aos critérios,
            caso contrário, retorna False.
        """
        hoje = date.today()
        return self.fluxos_submissao.filter(etapa__in=[EtapaPeriodoSubmissao.RESULTADO_FINAL], data_inicio__lte=hoje).exists()

    def pode_processar_avaliacoes(self):
        """
        Verifica se é possível processar as avaliações do evento.

        Retorna True se o evento estiver em período de correções e
        não houver um log de processamento para o fluxo atual.
        """
        if not self.estah_em_periodo_de_correcoes():
            return False

        fluxo_atual = self.get_fluxo_atual()
        existe_log_processamento = LogProcessamentoSubmissao.objects.filter(evento=self, fluxo_submissao=fluxo_atual).exists()

        return not existe_log_processamento

    def pode_processar_resultados_finais(self):
        """
        Verifica se é possível processar os resultados finais do evento.

        Retorna True se o evento estiver em período de correções e
        não houver um log de processamento para o fluxo atual.
        """
        if not self.pode_divulgar_resultado_final():
            return False

        fluxo_resultado_final = self.fluxos_submissao.filter(etapa__in=[EtapaPeriodoSubmissao.RESULTADO_FINAL]).order_by('-data_inicio').first()
        existe_log_processamento = LogProcessamentoSubmissao.objects.filter(evento=self, fluxo_submissao=fluxo_resultado_final).exists()

        return not existe_log_processamento

    def pode_processar_resultados_para_avaliacao_presencial(self):
        """
        Verifica se o fluxo atual do evento é de avaliação presencial.

        Retorna True se o fluxo atual for de avaliação presencial, caso contrário, retorna False.
        """
        fluxo_atual = self.get_fluxo_atual()
        retorno = fluxo_atual and fluxo_atual.etapa == EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL
        if retorno:
            fluxo_resultado_final = (
                self.fluxos_submissao.filter(etapa__in=[EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL]).order_by('-data_inicio').first()
            )
            existe_log_processamento = LogProcessamentoSubmissao.objects.filter(evento=self, fluxo_submissao=fluxo_resultado_final).exists()

            return not existe_log_processamento
        else:
            return False

    def pode_convidar_avaliador(self):
        """
        Verifica se é possível convidar um avaliador com base nos fluxos de submissão.

        Este método verifica se existem fluxos de submissão associados à instância atual
        que estão em uma das etapas de avaliação (AVALIACAO, REAVALIACAO ou AVALIACAO_PRESENCIAL)
        e cuja data de término ainda não passou.

        Returns:
            bool: Retorna True se houver pelo menos um fluxo de submissão que atenda aos critérios,
            caso contrário, retorna False.
        """
        hoje = date.today()
        return self.fluxos_submissao.filter(
            etapa__in=[EtapaPeriodoSubmissao.AVALIACAO, EtapaPeriodoSubmissao.REAVALIACAO, EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL],
            data_fim__gte=hoje,
        ).exists()

    def get_quantitativo_de_participantes_por_forma_de_participacao(self):
        """
        Retorna uma lista de dicionários com a descrição e quantidade de participantes por forma de participação.
        Inclui a opção 'Não informado' para registros com valor nulo.
        """
        mapeamento = {
            FormaParticipacaoEvento.PRESENCIAL: 'Participação presencial',
            FormaParticipacaoEvento.ONLINE: 'Participação online',
            None: 'Forma de participação não informada',
        }

        # Query otimizada com GROUP BY e COUNT
        resultados = self.participantes.values('forma_participacao').annotate(quantidade=Count('pk'))

        # Construir lista de resultados formatados
        return [{'descricao': mapeamento.get(item['forma_participacao'], 'Desconhecido'), 'quantidade': item['quantidade']} for item in resultados]

    @classmethod
    def get_inscricoes_abertas(cls):
        agora = datetime.today()
        eventos = cls.objects.filter(inscricao_publica=True, ativo=True, deferido=True)
        eventos_entre_datas = eventos.filter(data_inicio_inscricoes__lt=agora, data_fim_inscricoes__gt=agora)
        eventos_data_hora_inicio = eventos.filter(
            Q(data_inicio_inscricoes=agora), Q(hora_inicio_inscricoes__isnull=True) | Q(hora_inicio_inscricoes__lte=agora)
        )
        eventos_data_hora_fim = eventos.filter(Q(data_fim_inscricoes=agora), Q(hora_fim_inscricoes__isnull=True) | Q(hora_fim_inscricoes__gte=agora))
        eventos = eventos_entre_datas | eventos_data_hora_inicio | eventos_data_hora_fim
        return eventos.order_by('data_inicio', 'nome')

    @classmethod
    def get_submissoes_abertas(cls):
        agora = datetime.today()
        return (
            cls.objects.filter(
                inscricao_publica=True,
                ativo=True,
                deferido=True,
                configuracao__evento__fluxos_submissao__etapa=EtapaPeriodoSubmissao.SUBMISSAO,
                configuracao__evento__fluxos_submissao__data_inicio__lte=agora,
                configuracao__evento__fluxos_submissao__data_fim__gte=agora,
            )
            .order_by('data_inicio', 'nome')
            .distinct()
        )

    @classmethod
    def get_avaliacoes_abertas(cls):
        agora = datetime.today()
        return (
            cls.objects.filter(
                inscricao_publica=True,
                ativo=True,
                deferido=True,
                configuracao__evento__fluxos_submissao__etapa__in=[
                    EtapaPeriodoSubmissao.AVALIACAO,
                    EtapaPeriodoSubmissao.REAVALIACAO,
                    EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL,
                ],
                configuracao__evento__fluxos_submissao__data_inicio__lte=agora,
                configuracao__evento__fluxos_submissao__data_fim__gte=agora,
            )
            .order_by('data_inicio', 'nome')
            .distinct()
        )

    def pode_inscrever(self):
        if not (self.ativo and self.deferido):
            return False, 'Evento inativo ou cancelado. Você não pode se inscrever nesse evento.'
        if not self.estah_em_periodo_inscricao():
            return False, 'Evento fora do período de inscrição.'
        if not self.tem_vagas_disponiveis():
            return False, 'Todas as vagas já foram preenchidas para este evento.'
        if not self.get_tipo_participacoes_area_publica().exists():
            return False, 'Inscrições não disponíveis na área pública do Suap.'
        return True, ''

    def get_tipo_participacoes_area_publica(self):
        data_hora_agora = datetime.now()
        return self.tipos_participante.annotate(
            inicio_inscricao=ExpressionWrapper(
                F('data_inicio_inscricoes') + Coalesce(F('hora_inicio_inscricoes'), Value(time(0, 0, 0))), output_field=DateTimeField()
            ),
            fim_inscricao=ExpressionWrapper(
                F('data_fim_inscricoes') + Coalesce(F('hora_fim_inscricoes'), Value(time(23, 59, 59))), output_field=DateTimeField()
            ),
        ).filter(permite_inscricao_direta=True, inicio_inscricao__lte=data_hora_agora, fim_inscricao__gte=data_hora_agora)

    def participante_pode_se_inscrever_area_publica(self, brasileiro, documento):
        tipo_participacoes = self.get_tipo_participacoes_area_publica().values_list('tipo_participacao__id', flat=True)
        if tipo_participacoes.exists():
            if brasileiro:
                inscricoes = Participante.objects.filter(evento=self, cpf=documento, tipo__tipo_participacao__id__in=tipo_participacoes)
            else:
                inscricoes = Participante.objects.filter(evento=self, passaporte=documento, tipo__tipo_participacao__id__in=tipo_participacoes)
            if tipo_participacoes.count() > inscricoes.count():
                return True
        return False

    def estah_realizado(self):
        hoje = date.today()
        if self.data_fim:
            if self.hora_fim:
                agora = datetime.now()
                data_hora_fim = datetime.combine(self.data_fim, self.hora_fim)
                return agora > data_hora_fim
            else:
                return hoje > self.data_fim
        elif hoje > self.data_inicio:
            return True
        return False

    def get_periodo_evento(self):
        if self.data_fim:
            if self.data_fim == self.data_inicio:
                if self.hora_fim:
                    periodo = f'{self.data_inicio.strftime("%d/%m/%Y")} das {self.hora_inicio.strftime("%H:%M")} às {self.hora_fim.strftime("%H:%M")}'
                else:
                    periodo = f'{self.data_inicio.strftime("%d/%m/%Y")} a partir das {self.hora_inicio.strftime("%H:%M")}'
            else:
                if self.hora_fim:
                    periodo = f'{self.data_inicio.strftime("%d/%m/%Y")} às {self.hora_inicio.strftime("%H:%M")} até {self.data_fim.strftime("%d/%m/%Y")} às {self.hora_fim.strftime("%H:%M")}'
                else:
                    periodo = (
                        f'{self.data_inicio.strftime("%d/%m/%Y")} às {self.hora_inicio.strftime("%H:%M")} até {self.data_fim.strftime("%d/%m/%Y")}'
                    )
        else:
            periodo = f'{self.data_inicio.strftime("%d/%m/%Y")} às {self.hora_inicio.strftime("%H:%M")}'
        return periodo

    def get_periodo_inscricao(self):
        """Retorna o período de inscrição formatado, evitando erro caso algum campo seja None."""
        if not self.data_inicio_inscricoes:
            return None

        data_inicio = self.data_inicio_inscricoes.strftime('%d/%m/%Y')
        data_fim = self.data_fim_inscricoes.strftime('%d/%m/%Y') if self.data_fim_inscricoes else None
        hora_inicio = self.hora_inicio_inscricoes.strftime('%H:%M') if self.hora_inicio_inscricoes else None
        hora_fim = self.hora_fim_inscricoes.strftime('%H:%M') if self.hora_fim_inscricoes else None

        if data_fim:
            if not hora_inicio or not hora_fim:
                return f'{data_inicio} até {data_fim}'
            if self.data_fim_inscricoes == self.data_inicio_inscricoes:
                return f'{data_inicio} das {hora_inicio} às {hora_fim}'
            return f'{data_inicio} às {hora_inicio} até {data_fim} às {hora_fim}'

        if hora_inicio:
            return f'{data_inicio} às {hora_inicio}'

        return data_inicio

    def _get_periodo_formatado(self, etapa):
        periodos = [f for f in self.fluxos_submissao.all() if f.etapa == etapa]
        resultados = []
        for periodo in periodos:
            data_inicio = periodo.data_inicio.strftime('%d/%m/%Y') if periodo.data_inicio else None
            data_fim = periodo.data_fim.strftime('%d/%m/%Y') if periodo.data_fim else None
            if data_inicio and data_fim:
                resultados.append(f'{data_inicio} até {data_fim}')
            elif data_inicio:
                resultados.append(f'{data_inicio}')
        if resultados:
            return ' / '.join(resultados)
        return None

    def get_periodo_submissao_formatado(self):
        return self._get_periodo_formatado(EtapaPeriodoSubmissao.SUBMISSAO)

    def get_periodo_avaliacao_formatado(self):
        return self._get_periodo_formatado(EtapaPeriodoSubmissao.AVALIACAO)

    def get_periodo_por_etapa(self, etapa):
        """
        Retorna o período (data_inicio e data_fim) para uma etapa específica do fluxo de submissão.

        Args:
            etapa: Etapa do fluxo (ex: EtapaPeriodoSubmissao.SUBMISSAO ou EtapaPeriodoSubmissao.AVALIACAO)

        Returns:
            dict: Dicionário com 'data_inicio' e 'data_fim' ou None se não houver fluxos para a etapa
        """
        fluxos = [f for f in self.fluxos_submissao.all() if f.etapa == etapa]
        if not fluxos:
            return None

        # Pega o primeiro e último fluxo para determinar o período completo
        primeiro_fluxo = min(fluxos, key=lambda f: f.data_inicio)
        ultimo_fluxo = max(fluxos, key=lambda f: f.data_fim or date.min)

        return {
            'data_inicio': primeiro_fluxo.data_inicio,
            'data_fim': ultimo_fluxo.data_fim,
        }

    def get_periodo_inscricao_detalhado(self):
        """
        Retorna um dicionário com os períodos de inscrição por TipoParticipante que permite inscrição direta.
        Se não houver nenhum TipoParticipante com inscrição direta, retorna None.
        """
        tipos_com_inscricao_direta = self.tipos_participante.filter(permite_inscricao_direta=True)
        if not tipos_com_inscricao_direta.exists():
            return None

        periodos = {}
        for tipo in tipos_com_inscricao_direta:
            data_inicio = tipo.data_inicio_inscricoes.strftime('%d/%m/%Y') if tipo.data_inicio_inscricoes else None
            data_fim = tipo.data_fim_inscricoes.strftime('%d/%m/%Y') if tipo.data_fim_inscricoes else None
            hora_inicio = tipo.hora_inicio_inscricoes.strftime('%H:%M') if tipo.hora_inicio_inscricoes else None
            hora_fim = tipo.hora_fim_inscricoes.strftime('%H:%M') if tipo.hora_fim_inscricoes else None

            if not data_inicio:
                # Usar as datas do evento se não houver datas específicas para o tipo de participante
                data_inicio_evento = self.data_inicio.strftime('%d/%m/%Y') if self.data_inicio else None
                data_fim_evento = self.data_fim.strftime('%d/%m/%Y') if self.data_fim else None

                if data_inicio_evento and data_fim_evento:
                    if self.data_inicio == self.data_fim:
                        periodo = f'{data_inicio_evento}'
                    else:
                        periodo = f'{data_inicio_evento} até {data_fim_evento}'
                elif data_inicio_evento:
                    periodo = data_inicio_evento
                else:
                    periodo = None
            elif data_fim:
                if not hora_inicio or not hora_fim:
                    periodo = f'{data_inicio} até {data_fim}'
                elif tipo.data_fim_inscricoes == tipo.data_inicio_inscricoes:
                    periodo = f'{data_inicio} das {hora_inicio} às {hora_fim}'
                else:
                    periodo = f'{data_inicio} às {hora_inicio} até {data_fim} às {hora_fim}'
            else:
                periodo = f'{data_inicio} às {hora_inicio}' if hora_inicio else data_inicio

            periodos[tipo.tipo_participacao.descricao] = periodo

        return periodos

    def get_carga_horaria(self):
        return Participante.segundos_para_tempo(self.carga_horaria)

    def get_participacoes_inconsistentes(self):
        return self.participantes.filter(tipo__isnull=True)

    def get_programacao(self):
        """
        Retorna a programação do evento agrupada por dia.
        Otimizado para evitar N+1 queries usando agrupamento em Python.
        """
        from collections import defaultdict

        programacao = []
        if self.data_inicio and self.data_fim:
            if self.data_fim >= self.data_inicio:
                # Agrupa atividades por dia em Python (usa cache do prefetch_related)
                atividades_por_dia = defaultdict(list)
                for atividade in self.atividadeevento_set.all():
                    if atividade.data:
                        atividades_por_dia[atividade.data].append(atividade)

                # Itera sobre os dias do evento
                dia = self.data_inicio
                while dia <= self.data_fim:
                    if dia in atividades_por_dia:
                        # Ordena por hora em Python (sem query adicional)
                        atividades_ordenadas = sorted(atividades_por_dia[dia], key=lambda x: x.hora or time(0, 0, 0))
                        programacao.append((dia, atividades_ordenadas))
                    dia = somar_dias(dia, 1)
        return programacao

    def get_situacao(self):
        situacao = 'Aguardando avaliação'
        if self.cancelado:
            situacao = 'Cancelado'
        elif self.finalizado:
            situacao = 'Finalizado'
        elif self.submetido and self.deferido is None:
            situacao = 'Submetido'
        elif self.ativo:
            if self.deferido:
                situacao = 'Deferido'
            else:
                situacao = 'Ativo'
        elif not self.ativo:
            if not self.submetido and not self.deferido:
                situacao = 'Devolvido'
            elif self.deferido:
                situacao = 'Inativo'
            elif not self.deferido:
                situacao = 'Indeferido'

        return situacao

    def get_situacao_por_periodo(self) -> str:
        """
        Retorna a situação do evento baseada no período (datas).

        Returns:
            str: 'Em andamento', 'Em breve' ou 'Finalizado'
        """
        hoje = date.today()

        if self.data_inicio and self.data_fim:
            if self.data_inicio <= hoje <= self.data_fim:
                return 'Em andamento'
            elif self.data_inicio > hoje:
                return 'Em breve'
            elif self.data_fim < hoje:
                return 'Finalizado'
        elif self.data_inicio:
            # Se só tem data_inicio
            if self.data_inicio == hoje:
                return 'Em andamento'
            elif self.data_inicio > hoje:
                return 'Em breve'
            return 'Finalizado'

        return 'Sem data definida'

    def get_url_inscricao(self):
        return f'/eventos/inscricao/1/{self.pk}/'

    def get_url_inscricao_completa(self):
        return f'{settings.SITE_URL}/eventos/inscricao/1/{self.pk}/'

    def get_url_submissao(self):
        return f'/eventos/submissao/{self.pk}/submeter_trabalho/1/'

    def pode_avaliar(self, user: User) -> bool:
        grupos_avaliadores_sistemicos = self.dimensoes.values_list('grupos_avaliadores_sistemicos', flat=True)
        is_avaliador_sistemico = user.groups.filter(pk__in=grupos_avaliadores_sistemicos).exists()
        if is_avaliador_sistemico:
            return True

        grupos_avaliadores_locais = self.dimensoes.values_list('grupos_avaliadores_locais', flat=True)
        is_avaliador_local = user.groups.filter(pk__in=grupos_avaliadores_locais).exists()
        return is_avaliador_local and self.campus == get_uo(user)

    def possui_tipo_participante_avaliador(self):
        return self.tipos_participante.filter(tipo_participacao__descricao=TIPO_PARTICIPACAO_AVALIADOR).exists()

    def possui_modalidades_sem_avaliadores(self):
        tem_modalidades_sem_avaliador = Modalidade.objects.filter(evento_id=self.id).exclude(
            Exists(AvaliadorModalidade.objects.filter(modalidade=OuterRef('pk')))
        )
        return tem_modalidades_sem_avaliador.exists()

    def pode_finalizar(self, user):
        return self.pode_gerenciar(user) and self.ativo and self.submetido and self.deferido and not self.finalizado and self.estah_realizado()

    def eh_organizador(self, user):
        return Participante.objects.filter(
            evento=self.pk, tipo__tipo_participacao__descricao=TIPO_PARTICIPACAO_ORGANIZADOR, cpf=user.get_vinculo().pessoa.pessoafisica.cpf
        ).exists()

    def pode_confirmar_presenca(self, user):
        return (
            user.is_authenticated
            and user.get_vinculo()
            and Participante.objects.filter(
                evento=self.pk, tipo__tipo_participacao__descricao=TIPO_PARTICIPACAO_MONITOR, cpf=user.get_vinculo().pessoa.pessoafisica.cpf
            ).exists()
        )

    def eh_coordenador(self, user):
        return self.coordenador == user.get_relacionamento()

    def pode_gerenciar(self, user):
        if not user.is_authenticated:
            return False
        if in_group(user, 'Coordenador de Comunicação Sistêmico'):
            return True
        if in_group(user, 'Coordenador de Comunicação') and self.campus == get_uo(user):
            return True
        if self.deferido is False:  # Impede que um evento indeferido possa ser editado pelo responsavel
            return False
        return self.eh_coordenador(user) or self.eh_organizador(user)

    def pode_enviar_certificado(self):
        return (self.subtipo and self.subtipo.multiplas_atividades) or self.carga_horaria

    def certificado_bloqueado_por_falta_de_avaliacao_configurada(self):
        return self.exigir_avaliacao_para_certificado and not self.get_perguntas_avaliacao().exists()

    def registrar_data_emissao_certificado(self):
        if self.data_emissao_certificado:
            return
        self.data_emissao_certificado = datetime.now()
        if self.data_fim and self.data_emissao_certificado.date() < self.data_fim:
            self.data_emissao_certificado = datetime.combine(self.data_fim, self.hora_fim or time.min)
        self.save(update_fields=['data_emissao_certificado'])

    def emitir_certificados_automaticamente(self):
        if not self.gera_certificado or not self.estah_realizado():
            return 0

        participantes = self.participantes.filter(codigo_geracao_certificado__isnull=True).select_related('tipo', 'tipo__tipo_participacao')
        if self.exigir_avaliacao_para_certificado:
            participantes = participantes.com_avaliacao_realizada()
        emitidos = 0

        for participante in participantes:
            if participante.esta_apto_para_certificado():
                participante.emitir_certificado()
                Notificar.enviar_certificado_evento(participante)
                participante.marcar_certificado_como_enviado()
                emitidos += 1

        return emitidos

    def tem_vagas_disponiveis(self):
        tipo_participacao = TipoParticipacao.objects.get(descricao='Participante')
        tipo_participante = TipoParticipante.objects.filter(evento=self, tipo_participacao=tipo_participacao).first()
        if not tipo_participante:
            return False
        qtd_disponiveis_tipo_participante = tipo_participante.get_qtd_vagas_disponiveis()
        if qtd_disponiveis_tipo_participante is not None:
            return qtd_disponiveis_tipo_participante > 0

        if qtd_disponiveis_tipo_participante is None and not self.atividadeevento_set.exists():
            return True

        for atividadeevento in self.atividadeevento_set.all():
            qtd_disponiveis = atividadeevento.get_qtd_vagas_disponiveis()
            if qtd_disponiveis is None:
                return True
            else:
                if qtd_disponiveis > 0:
                    return True
        return False

    def opcoes_gerais_de_resposta(self):
        return OpcaoResposta.objects.filter(evento=self, pergunta__isnull=True)

    def get_perguntas_por_tipo(self, tipo_questionario=TipoQuestionario.INSCRICAO):
        return self.pergunta_set.filter(tipo_questionario=tipo_questionario)

    def get_perguntas_inscricao(self):
        return self.get_perguntas_por_tipo(TipoQuestionario.INSCRICAO)

    def get_perguntas_avaliacao(self):
        return self.get_perguntas_por_tipo(TipoQuestionario.AVALIACAO)

    def perguntas_corretamente_configuradas(self, tipo_questionario=TipoQuestionario.INSCRICAO):
        perguntas = self.get_perguntas_por_tipo(tipo_questionario)
        if perguntas.exists():
            opcoes_resposta_geral = OpcaoResposta.objects.filter(evento=self, pergunta__isnull=True).count()
            if opcoes_resposta_geral >= 2:
                return True
            else:
                perguntas_objetivas = Pergunta.objects.filter(
                    evento=self,
                    tipo_questionario=tipo_questionario,
                    tipo_pergunta__in=[TipoPergunta.OBJETIVA, TipoPergunta.MULTIPLA_ESCOLHA, TipoPergunta.ESCALA],
                )
                perguntas_subjetivas = Pergunta.objects.filter(evento=self, tipo_questionario=tipo_questionario).exclude(
                    tipo_pergunta__in=[TipoPergunta.OBJETIVA, TipoPergunta.MULTIPLA_ESCOLHA, TipoPergunta.ESCALA]
                )
                total_perguntas_objetivas = perguntas_objetivas.count()
                total_perguntas_com_opcao_resposta = perguntas_objetivas.annotate(num_opcoes=Count('opcaoresposta')).filter(num_opcoes__gte=2).count()
                if (total_perguntas_objetivas > 0 and total_perguntas_objetivas == total_perguntas_com_opcao_resposta) or (
                    perguntas.count() == perguntas_subjetivas.count()
                ):
                    return True
        return False

    def perguntas_respondidas(self, tipo_questionario=TipoQuestionario.INSCRICAO):
        resultados = []

        for pergunta in self.get_perguntas_por_tipo(tipo_questionario):
            resultado = {
                'pergunta': pergunta.titulo,
                'tipo_pergunta': pergunta.tipo_pergunta,
                'get_tipo_pergunta_display': pergunta.get_tipo_pergunta_display(),
            }

            if pergunta.tipo_pergunta in (TipoPergunta.SUBJETIVA_LONGA, TipoPergunta.SUBJETIVA_CURTA):
                respostas = RespostaParticipante.objects.filter(pergunta=pergunta)
                resultado['respostas'] = [resposta.resposta_texto or resposta.resposta_numero for resposta in respostas]
            else:  # TipoPergunta.OBJETIVA ou TipoPergunta.MULTIPLA_ESCOLHA
                opcoes_resposta = OpcaoResposta.objects.filter(pergunta=pergunta)
                if opcoes_resposta.count() < 2:
                    opcoes_resposta = OpcaoResposta.objects.filter(evento=self, pergunta__isnull=True)

                opcao_resultados = {}
                for opcao in opcoes_resposta:
                    quantitativo = RespostaParticipante.objects.filter(pergunta=pergunta, opcao_resposta=opcao).count()
                    opcao_resultados[opcao.texto] = quantitativo
                resultado['opcoes_resposta'] = opcao_resultados
            resultados.append(resultado)
        return resultados

    def tem_respostas(self, tipo_questionario=TipoQuestionario.INSCRICAO):
        return RespostaParticipante.objects.filter(
            participante__evento_id=self.id,
            pergunta__tipo_questionario=tipo_questionario,
        ).exists()

    @transaction.atomic
    def submeter(self, user):
        self.submetido = True
        self.deferido = None
        self.ativo = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Submeteu o evento', user=user)

    @transaction.atomic
    def deferir(self, user):
        self.deferido = True
        self.ativo = True
        self.finalizado = False
        self.motivo_indeferimento = ''
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Deferiu o evento', user=user)

    @transaction.atomic
    def indeferir(self, motivo_indeferimento, user):
        self.motivo_indeferimento = motivo_indeferimento
        self.deferido = False
        self.ativo = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Indeferiu o evento', user=user)

    @transaction.atomic
    def ativar(self, justificativa, user):
        self.ativo = True
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao=f'Ativou o evento alegando: {justificativa}', user=user)

    @transaction.atomic
    def suspender(self, justificativa, user):
        self.ativo = False
        self.finalizado = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao=f'Suspendeu o evento alegando: {justificativa}', user=user)

    @transaction.atomic
    def cancelar_avaliacao(self, user):
        self.deferido = None
        self.ativo = False
        self.finalizado = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Cancelou a avaliação do evento', user=user)

    @transaction.atomic
    def devolver(self, justificativa, user):
        self.submetido = False
        self.ativo = False
        self.finalizado = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao=f'Devolveu o evento alegando: {justificativa}', user=user)

    @transaction.atomic
    def finalizar(self, user):
        self.finalizado = True
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Finalizou o evento', user=user)

    @transaction.atomic
    def cancelar(self, user):
        self.cancelado = True
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Cancelou o evento', user=user)

    @transaction.atomic
    def desfazer_cancelamento(self, user):
        self.cancelado = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Desfez cancelamento do evento', user=user)

    @transaction.atomic
    def desfazer_finalizacao(self, user):
        self.finalizado = False
        self.save()
        HistoricoEvento.objects.create(evento=self, descricao='Desfez finalização do evento', user=user)

    def finalizar_automaticamente(self):
        self.finalizado = True
        self.save()

    def get_fluxo_atual(self):
        fluxo_atual = self.fluxos_submissao.filter(data_inicio__lte=date.today(), data_fim__gte=date.today()).first()
        if not fluxo_atual:
            fluxo_atual = self.fluxos_submissao.filter(etapa=EtapaPeriodoSubmissao.RESULTADO_FINAL, data_inicio__lte=date.today()).first()
        return fluxo_atual

    def get_proximo_fluxo(self):
        return self.fluxos_submissao.filter(data_inicio__gt=date.today()).order_by('data_inicio').first()

    def get_recomendacoes_disponiveis(self):
        hoje = date.today()
        fase_atual = self.get_fluxo_atual()
        correcoes = self.fluxos_submissao.filter(etapa__in=[EtapaPeriodoSubmissao.CORRECOES], data_inicio__gte=hoje).exclude(
            pk=fase_atual.pk if fase_atual else None
        )

        if fase_atual and fase_atual.etapa == EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL:
            return None
        elif correcoes.exists():
            return Recomendacao.todas
        else:
            return Recomendacao.aceita_ou_rejeitar

    def possui_avaliacao_pendente(self):
        return (
            AvaliacaoSubmissao.objects.filter(versao__submissao__modalidade__evento=self, nota__isnull=True)
            .exclude(versao__submissao__situacao=SituacaoSubmissao.REMOVIDO_DUPLICIDADE)
            .exists()
        )

    def possui_area_tematica_pendente(self):
        """
        Verifica se cada área temática do evento possui vínculo com pelo menos uma modalidade.
        """
        qs = AreaTematicaModalidade.objects.filter(modalidade__evento=self)
        if qs.exists():
            return not all(qs.filter(area_tematica=area_tematica).exists() for area_tematica in self.areas_tematicas.all())
        else:
            return True

    def possui_fluxo_minimo_submissao(self):
        """
        Verifica se o evento possui pelo menos os três seguintes fluxos vinculados:
        EtapaPeriodoSubmissao.SUBMISSAO, EtapaPeriodoSubmissao.AVALIACAO, EtapaPeriodoSubmissao.CORRECOES, EtapaPeriodoSubmissao.RESULTADO_FINAL.
        """
        etapas_necessarias = [
            EtapaPeriodoSubmissao.SUBMISSAO,
            EtapaPeriodoSubmissao.AVALIACAO,
            EtapaPeriodoSubmissao.RESULTADO_FINAL,
        ]
        return self.fluxos_submissao.filter(etapa__in=etapas_necessarias).values_list('etapa', flat=True).distinct().count() == len(
            etapas_necessarias
        )

    def cria_log_processamento(self, mensagem, fluxo_submissao=None, usuario=None):
        LogProcessamentoSubmissao.objects.create(evento=self, mensagem=mensagem, fluxo_submissao=fluxo_submissao, executado_por=usuario)

    def processar_avaliacoes(self, fluxo=None, usuario=None):
        """
        Processa as avaliações de submissões de um evento.

        Este método avalia os pareceres da versão mais recente de cada submissão e atualiza o estado das submissões com base nos resultados das avaliações. As submissões podem ser aprovadas, rejeitadas ou ter correções solicitadas.

        Parâmetros:
            fluxo (opcional): Objeto representando o fluxo atual do evento, utilizado para registrar logs e etiquetas.
            usuario (opcional): Usuário responsável pela ação, utilizado para registro de logs.

        Funcionamento:
            - Se houver avaliações pendentes, o processamento é interrompido e uma mensagem de erro é retornada.
            - Para cada submissão:
                - Se todos os pareceres forem positivos, a submissão é aprovada.
                - Se todos os pareceres forem negativos, a submissão é rejeitada.
                - Se houver pareceres pendentes ou mistos, são solicitadas correções:
                    - Uma nova versão da submissão é criada.
                    - Os avaliadores são clonados para a nova versão, com notas zeradas.
                    - A submissão é marcada como "correções solicitadas".
            - Ao final, retorna uma mensagem resumindo o resultado do processamento e o status da operação.

        Retorna:
            tuple: Uma tupla contendo uma mensagem de resumo (str) e o status da operação ('success' ou 'error').

            - Submissões aprovadas: todos os pareceres positivos.
            - Submissões rejeitadas: todos os pareceres negativos.
            - Submissões com correções solicitadas: pareceres pendentes ou mistos.
        """

        if self.possui_avaliacao_pendente():
            mensagem = 'Existem avaliações pendentes. Finalize-as antes de processar.'
            self.cria_log_processamento(f'Erro ao processar avaliações: {mensagem}', usuario)
            return mensagem, 'error'

        versoes_para_correcoes = []
        submissoes_aprovadas = []
        submissoes_rejeitadas = []

        for submissao in Submissao.objects.filter(modalidade__evento=self):
            ultima_versao = submissao.get_ultima_versao()
            pareceres = ultima_versao.pareceres.avaliados()
            recomendacoes = list(pareceres.values_list('recomendacao', flat=True))

            contagem = Counter(recomendacoes)
            total = len(recomendacoes)

            if contagem.get(1, 0) == total:  # verifica se todos os pareceres são positivos
                submissao.resultado_avaliacao = ResultadoAvaliacao.APROVADO
                submissao.situacao = SituacaoSubmissao.AVALIADO
                submissao.save(update_fields=['resultado_avaliacao', 'situacao'])
                submissoes_aprovadas.append(submissao)
                continue

            if contagem.get(-1, 0) == total:  # Verifica se todos os pareceres são negativos
                submissao.resultado_avaliacao = ResultadoAvaliacao.REPROVADO
                submissao.situacao = SituacaoSubmissao.AVALIADO
                submissao.save(update_fields=['resultado_avaliacao', 'situacao'])
                submissoes_rejeitadas.append(submissao)
                continue

            if contagem.get(0, 0) == total or contagem.get(0, 0) >= 1:  # Verifica se há pareceres pendentes ou mistos
                versoes_para_correcoes.append(ultima_versao)

                Notificar.solicitacao_correcoes(ultima_versao)
                etiqueta = 'Versão criada durante o processamento de avaliações'
                if fluxo:
                    etiqueta += f' - Fluxo: {fluxo.get_etapa_display()}'
                # Criar nova versão da submissão
                nova_versao = VersaoSubmissao.objects.create(submissao=submissao, numero=ultima_versao.numero + 1, etiqueta=etiqueta)

                # Clonar avaliadores com notas zeradas
                for avaliacao in pareceres:
                    AvaliacaoSubmissao.objects.create(
                        avaliador_modalidade=avaliacao.avaliador_modalidade,
                        versao=nova_versao,
                    )

                submissao.resultado_avaliacao = ResultadoAvaliacao.PENDENTE
                submissao.situacao = SituacaoSubmissao.CORRECOES_SOLICITADAS
                submissao.arquivo = None
                submissao.save(update_fields=['situacao', 'resultado_avaliacao'])

        mensagem = f'{len(submissoes_aprovadas)} aprovados, {len(submissoes_rejeitadas)} rejeitados e {len(versoes_para_correcoes)} com correções solicitadas.'
        fluxo = fluxo or self.get_fluxo_atual()
        self.cria_log_processamento('Processamento de avaliações concluído.', fluxo, usuario)
        return mensagem, 'success'

    def processar_resultados_para_avaliacao_presencial(self, fluxo=None, usuario=None):
        if self.possui_avaliacao_pendente():
            mensagem = 'Existem avaliações pendentes. Finalize-as antes de processar.'
            self.cria_log_processamento(f'Erro ao processar resultados para avaliação presencial: {mensagem}', usuario)
            return mensagem, 'error'

        submissoes_processadas = 0
        fluxo_atual = self.get_fluxo_atual()

        if fluxo_atual and fluxo_atual.etapa == EtapaPeriodoSubmissao.AVALIACAO_PRESENCIAL:
            # Se houver avaliação presencial, prepara novas versões para aprovados
            for submissao in Submissao.objects.filter(
                modalidade__evento=self, resultado_avaliacao=ResultadoAvaliacao.APROVADO, situacao=SituacaoSubmissao.AVALIADO
            ):
                ultima_versao = submissao.versoes.order_by('-id').first()
                etiqueta = 'Versão criada durante o processamento para avaliação presencial'
                nova_versao = VersaoSubmissao.objects.create(
                    submissao=submissao,
                    numero=ultima_versao.numero + 1,
                    arquivo=ultima_versao.arquivo,
                    etiqueta=etiqueta,
                )
                for avaliacao in ultima_versao.pareceres.all():
                    AvaliacaoSubmissao.objects.create(
                        avaliador_modalidade=avaliacao.avaliador_modalidade,
                        versao=nova_versao,
                        recomendacao=Recomendacao.ACEITAR,
                    )
                submissao.situacao = SituacaoSubmissao.AGUARDANDO_AVALIACAO_PRESENCIAL
                submissao.save(update_fields=['situacao'])
                Notificar.trabalho_aprovado_para_avaliacao_presencial(submissao)
                submissoes_processadas += 1
                for participante in submissao.autores:
                    autor_novo = participante.cria_autor_de_trabalho()
                    if autor_novo.id != participante.id:
                        # Substitui o autor antigo pelo novo na submissão
                        AutorSubmissao.objects.filter(submissao=submissao, participante=participante).update(participante=autor_novo)

        mensagem = f'{submissoes_processadas} submissões preparadas para avaliação presencial.'
        fluxo = fluxo or self.get_fluxo_atual()
        self.cria_log_processamento(mensagem, fluxo, usuario)
        return mensagem, 'success'

    def detectar_duplicatas(self):
        """
        Detecta submissões duplicadas comparando conteúdos dentro da mesma modalidade/área temática.
        Uma submissão é considerada duplicata se a similaridade de conteúdo for >= 85%.
        A similaridade de título é calculada apenas para fins informativos.

        IMPORTANTE: Retorna TODAS as submissões similares, incluindo as já removidas,
        para que o coordenador tenha visão completa. A submissão "original" pode estar
        removida se o coordenador decidiu manter uma versão posterior.

        Returns:
            list: Lista de dicionários com grupos de duplicatas:
                [
                    {
                        'submissoes': [  # Lista com TODAS as submissões similares
                            {
                                'submissao': Submissao,
                                'similaridade_titulo': float,  # Com relação à primeira
                                'similaridade_conteudo': float,  # Com relação à primeira
                                'is_primeira': bool,  # Primeira submetida (referência)
                                'removida': bool,  # Se está removida
                            }
                        ],
                        'modalidade': Modalidade,
                        'area_tematica': AreaTematica,
                    }
                ]
        """
        THRESHOLD_CONTEUDO = 0.85  # 85% de similaridade no conteúdo

        # Agrupa submissões por modalidade e área temática
        submissoes_por_grupo = defaultdict(list)

        # Busca TODAS as submissões (incluindo removidas)
        submissoes = (
            Submissao.objects.filter(modalidade__evento=self, conteudo_extraido__isnull=False)
            .select_related('modalidade', 'modalidade__tipo', 'area_tematica')
            .prefetch_related('autores_relacionados__participante')
            .order_by('data_hora')
        )

        for submissao in submissoes:
            chave = (submissao.modalidade_id, submissao.area_tematica_id)
            submissoes_por_grupo[chave].append(submissao)

        grupos_duplicados = []

        # Analisa cada grupo de modalidade/área temática
        for lista_submissoes in submissoes_por_grupo.values():
            if len(lista_submissoes) < 2:
                continue

            analisadas = set()
            modalidade = lista_submissoes[0].modalidade
            area_tematica = lista_submissoes[0].area_tematica

            for i, submissao_referencia in enumerate(lista_submissoes):
                if submissao_referencia.id in analisadas:
                    continue

                # Lista para agrupar submissões similares
                grupo_similar = []

                # Adiciona a submissão de referência (primeira do grupo)
                grupo_similar.append(
                    {
                        'submissao': submissao_referencia,
                        'similaridade_titulo': 100.0,  # Consigo mesma
                        'similaridade_conteudo': 100.0,  # Consigo mesma
                        'is_primeira': True,
                        'removida': submissao_referencia.situacao == SituacaoSubmissao.REMOVIDO_DUPLICIDADE,
                    }
                )

                # Compara com as demais
                for submissao_comparar in lista_submissoes[i + 1 :]:
                    if submissao_comparar.id in analisadas:
                        continue

                    # Extrai conteúdo se ainda não foi extraído
                    if not submissao_referencia.conteudo_extraido:
                        submissao_referencia.extrair_conteudo_arquivo()
                    if not submissao_comparar.conteudo_extraido:
                        submissao_comparar.extrair_conteudo_arquivo()

                    # Calcula similaridades
                    similaridade_titulo = submissao_referencia.calcular_similaridade_titulo(submissao_comparar)
                    similaridade_conteudo = submissao_referencia.calcular_similaridade_conteudo(submissao_comparar)

                    # Se atingir o threshold, adiciona ao grupo
                    if similaridade_conteudo >= THRESHOLD_CONTEUDO:
                        sim_titulo_pct = round(similaridade_titulo * 100, 2)
                        sim_conteudo_pct = round(similaridade_conteudo * 100, 2)

                        grupo_similar.append(
                            {
                                'submissao': submissao_comparar,
                                'similaridade_titulo': sim_titulo_pct,
                                'similaridade_conteudo': sim_conteudo_pct,
                                'is_primeira': False,
                                'removida': submissao_comparar.situacao == SituacaoSubmissao.REMOVIDO_DUPLICIDADE,
                            }
                        )
                        analisadas.add(submissao_comparar.id)

                # Se encontrou pelo menos uma duplicata, adiciona o grupo
                if len(grupo_similar) > 1:
                    grupos_duplicados.append(
                        {
                            'submissoes': grupo_similar,
                            'modalidade': modalidade,
                            'area_tematica': area_tematica,
                        }
                    )
                    analisadas.add(submissao_referencia.id)

        return grupos_duplicados

    def processar_resultados_finais(self, fluxo=None, usuario=None):
        """
        Processa as avaliações de um evento, mas não irá permitir correções das submissões.
        Este método verifica se todas as avaliações pendentes foram concluídas antes de processar os resultados finais.
        Ele percorre todas as submissões do evento que ainda não possuem um resultado final (aprovado ou reprovado), calcula a decisão final
        com base na última versão da submissão e atualiza o status da submissão para "avaliado".
        Diferença do método anterior:
            Enquanto o método `processar_avaliacoes` lida com a análise inicial das submissões, determinando
            se elas devem ser aprovadas, rejeitadas ou se precisam de correções, este método foca na consolidação
            dos resultados finais. Ele processa apenas as submissões pendentes de decisão final, garantindo que
            todas as avaliações tenham sido concluídas e atualizando o status das submissões para refletir a
            conclusão do processo de avaliação.
        """
        if self.possui_avaliacao_pendente():
            mensagem = 'Existem avaliações pendentes. Finalize-as antes de processar.'
            self.cria_log_processamento(f'Erro ao processar resultados finais: {mensagem}', usuario)
            return mensagem, 'error'

        submissoes_processadas = 0
        # Consolidação final normal
        for submissao in Submissao.objects.filter(modalidade__evento=self).exclude(
            resultado_avaliacao__in=[ResultadoAvaliacao.APROVADO, ResultadoAvaliacao.REPROVADO]
        ):
            ultima_versao = submissao.versoes.order_by('-id').first()
            submissao.resultado_avaliacao = ultima_versao.calcular_decisao_final()
            submissao.situacao = SituacaoSubmissao.AVALIADO
            submissao.save(update_fields=['resultado_avaliacao', 'situacao'])
            submissoes_processadas += 1

        if submissoes_processadas == 0:
            mensagem = 'Processamento realizado com sucesso. Nenhuma submissão foi processada nesta etapa, pois não havia pendências.'
        else:
            mensagem = f'Processamento realizado com sucesso. {submissoes_processadas} submissões processadas.'

        fluxo = fluxo or self.get_fluxo_atual()
        self.cria_log_processamento(mensagem, fluxo, usuario)
        return mensagem, 'success'

    def configurou_criterios_avaliacao(self):
        """
        Verifica se os critérios de avaliação estão configurados corretamente para o evento.

        Returns:
            tuple: (configurou: bool, alerta_criterio_faltante: str|None, alerta_criterios_desbalanceados: str|None)
        """
        modalidades = self.modalidade_set.all()
        tem_modalidades = modalidades.exists()
        configurou = True
        alerta_criterio_faltante = None
        alerta_criterios_desbalanceados = None

        if (not tem_modalidades) or (tem_modalidades and modalidades.filter(criterioavaliacao__isnull=True).exists()):
            configurou = False
        else:
            # Deve verificar se existe pelo menos um critério de avaliação configurado para cada uma das etapas (fluxo de submissão), do tipo EtapaPeriodoSubmissao.avaliacao_choices
            etapas_avaliacao = [choice[0] for choice in EtapaPeriodoSubmissao.avaliacoes_choices]
            etapas_fluxo = self.fluxos_submissao.filter(etapa__in=etapas_avaliacao).values_list('etapa', flat=True).distinct()
            etapas_faltantes = []
            for etapa in etapas_fluxo:
                if not modalidades.filter(criterioavaliacao__etapa=etapa).exists():
                    configurou = False
                    etapa_nome = dict(EtapaPeriodoSubmissao.choices).get(etapa, etapa)
                    etapas_faltantes.append(etapa_nome)

            if etapas_faltantes:
                if len(etapas_faltantes) == 1:
                    alerta_criterio_faltante = f'Nenhum critério de avaliação configurado para a etapa "{etapas_faltantes[0]}".'
                else:
                    etapas_texto = '", "'.join(etapas_faltantes)
                    alerta_criterio_faltante = f'Nenhum critério de avaliação configurado para as etapas "{etapas_texto}".'

            # Verificar balanceamento das notas máximas entre as etapas
            criterios_desbalanceados = False
            if configurou and len(etapas_fluxo) > 1:
                # Calcular soma das notas máximas por etapa para cada modalidade
                somas_por_modalidade_etapa = {}
                for modalidade in modalidades:
                    for etapa in etapas_fluxo:
                        criterios = CriterioAvaliacao.objects.filter(modalidade=modalidade, etapa=etapa)
                        if criterios.exists():
                            soma_maxima = sum(criterio.nota_maxima for criterio in criterios)
                            somas_por_modalidade_etapa[(modalidade.id, etapa)] = soma_maxima

                # Verificar se há desbalanceamento entre etapas para cada modalidade
                modalidades_desbalanceadas = []
                for modalidade in modalidades:
                    somas_etapas = []
                    etapas_com_criterios = []
                    for etapa in etapas_fluxo:
                        chave = (modalidade.id, etapa)
                        if chave in somas_por_modalidade_etapa:
                            somas_etapas.append(somas_por_modalidade_etapa[chave])
                            etapas_com_criterios.append(etapa)

                    # Se há mais de uma etapa com critérios e as somas são diferentes
                    if len(set(somas_etapas)) > 1 and len(somas_etapas) > 1:
                        criterios_desbalanceados = True
                        etapas_nomes = [dict(EtapaPeriodoSubmissao.choices).get(etapa, etapa) for etapa in etapas_com_criterios]
                        modalidades_desbalanceadas.append(f'{modalidade.tipo.titulo} ({", ".join(etapas_nomes)})')

                if criterios_desbalanceados:
                    configurou = False
                    if len(modalidades_desbalanceadas) == 1:
                        alerta_criterios_desbalanceados = (
                            f'A soma das notas máximas dos critérios de avaliação está desbalanceada na modalidade: {modalidades_desbalanceadas[0]}.'
                        )
                    else:
                        modalidades_texto = '; '.join(modalidades_desbalanceadas)
                        alerta_criterios_desbalanceados = (
                            f'A soma das notas máximas dos critérios de avaliação está desbalanceada nas modalidades: {modalidades_texto}.'
                        )

        return configurou, alerta_criterio_faltante, alerta_criterios_desbalanceados

    def atingiu_configuracoes_minimas_para_submissao_trabalhos(self):
        """
        Verifica se o evento atingiu as configurações mínimas necessárias para permitir a submissão de trabalhos.

        Retorna True se todas as seguintes condições forem atendidas:
        - O evento possui uma configuração definida
        - O evento possui pelo menos uma modalidade cadastrada
        - Os critérios de avaliação foram configurados
        - O evento possui pelo menos um tipo de participante avaliador
        - O evento possui fluxo mínimo de submissão
        - O evento possui áreas temáticas vinculadas
        - Todas as áreas temáticas estão vinculadas a pelo menos uma modalidade

        Returns:
            bool: True se todas as configurações mínimas foram atingidas, False caso contrário.
        """

        # Verificação 1: Configuração básica
        if not self.configuracao:
            return False

        # Verificação 2: Tipo participante avaliador
        if not self.possui_tipo_avaliador:
            return False

        # Verificação 3: Fluxo mínimo de submissão
        if not self.possui_fluxo_minimo_submissao():
            return False

        # Verificação 4: Áreas temáticas vinculadas ao evento
        if not self.areas_tematicas.exists():
            return False

        # Verificação 5: Modalidades
        if not self.possui_modalidades:
            return False

        # Verificação 6: Critérios de avaliação configurados
        # Confia no campo desnormalizado mantido pelos signals
        if not self.possui_configuracao_criterios_completa:
            return False

        # Verificação 7: Todas as áreas temáticas vinculadas a modalidades
        return not self.possui_area_tematica_pendente()


class HistoricoEvento(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento)
    data = models.DateTimeField(auto_now_add=True, verbose_name='Data')
    user = models.ForeignKeyPlus(settings.AUTH_USER_MODEL, verbose_name='Usuário')
    descricao = models.TextField(verbose_name='Descrição')

    class Meta:
        verbose_name = 'Histórico de Evento'
        verbose_name_plural = 'Históricos de Evento'

    def __str__(self):
        return self.descricao


class TipoParticipacao(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', validate_caracter=True)
    modelo_certificado_padrao = models.FileFieldPlus(
        upload_to='eventos/modelo_certificado/',
        null=True,
        blank=True,
        verbose_name='Modelo de Certificado Padrão',
        filetypes=['docx'],
        help_text='O arquivo de modelo deve ser um arquivo .docx contendo as marcações #INSTITUICAO#, '
        '#NOMEDOPARTICIPANTE#, #TIPODOPARTICIPANTE#, #TIPOPARTICIPACAO#, #PARTICIPANTE#, #CPF#, '
        '#NOMEDOEVENTO#, #EVENTO#, #ATIVIDADES#, #ATIVIDADESCONFIRMADAS#, #ATIVIDADESDETALHADAS#, #TOTALDETRABALHOSAVALIADOS#, '
        '#TRABALHOSAVALIADOS#, #TOTALDETRABALHOSAPROVADOS#, #TRABALHOSAPROVADOS#, #LOCAL#, #CAMPUS#, #CARGAHORARIA#, #CARGAHORARIAATIVIDADESCONFIRMADAS#, '
        '#DATAINICIALADATAFINAL#, #PERIODOREALIZACAO#, #SETORRESPONSAVEL#, #CIDADE#, #UF#, #DATAEMISSAO#, '
        '#DATA#, #CODIGOVERIFICADOR#.',
    )
    ch_organizacao = models.BooleanField('Carga Horária de Organização', help_text='Adicional de 20% da carga horária total do evento', default=False)
    permite_inscricao_direta = models.BooleanField('Permitir inscrições diretas para esse tipo de participação?', default=True)

    class Meta:
        verbose_name = 'Tipo de Participação'
        verbose_name_plural = 'Tipos de Participações'
        ordering = ('descricao',)

    def get_modelo_certificado_padrao(self):
        modelo_certificado_padrao = self.modelo_certificado_padrao
        if not modelo_certificado_padrao:
            modelo_certificado_padrao = (
                TipoParticipacao.objects.filter(modelo_certificado_padrao__isnull=False)
                .exclude(modelo_certificado_padrao='')
                .latest('id')
                .modelo_certificado_padrao
            )
        return modelo_certificado_padrao


class TipoParticipante(models.ModelPlus):
    SEARCH_FIELDS = ['tipo_participacao__descricao']
    evento = models.ForeignKeyPlus(Evento, related_name='tipos_participante')
    tipo_participacao = models.ForeignKeyPlus(TipoParticipacao, related_name='tipos_participante', verbose_name='Tipo de Participação')
    limite_inscricoes = models.IntegerField(verbose_name='Limite de Inscrições', null=True, blank=True)
    modelo_certificado = models.FileFieldPlus(
        upload_to='eventos/modelo_certificado/',
        null=True,
        blank=True,
        verbose_name='Modelo de Certificado',
        filetypes=['docx'],
        help_text='O arquivo de modelo deve ser um arquivo .docx contendo as marcações #INSTITUICAO#, '
        '#NOMEDOPARTICIPANTE#, #TIPODOPARTICIPANTE#, #TIPOPARTICIPACAO#, #PARTICIPANTE#, #CPF#, '
        '#NOMEDOEVENTO#, #EVENTO#, #ATIVIDADES#, #ATIVIDADESCONFIRMADAS#, #ATIVIDADESDETALHADAS#, #TOTALDETRABALHOSAVALIADOS#, #TRABALHOSAVALIADOS#, '
        '#TOTALDETRABALHOSAPROVADOS#, #TRABALHOSAPROVADOS#, #LOCAL#, #CAMPUS#, #CARGAHORARIA#, #CARGAHORARIAATIVIDADESCONFIRMADAS#, '
        '#DATAINICIALADATAFINAL#, #PERIODOREALIZACAO#, #SETORRESPONSAVEL#, #CIDADE#, #UF#, #DATAEMISSAO#, '
        '#DATA#, #CODIGOVERIFICADOR#. Não preencher caso deseje utilizar o modelo padrão.',
    )
    permite_inscricao_direta = models.BooleanField('Permitir inscrições diretas para esse tipo de participante?', default=False)
    data_inicio_inscricoes = models.DateFieldPlus('Início das Inscrições', null=True)
    hora_inicio_inscricoes = models.TimeFieldPlus('Hora de Início das Inscrições', null=True, blank=True)
    data_fim_inscricoes = models.DateFieldPlus('Fim das Inscrições', null=True)
    hora_fim_inscricoes = models.TimeFieldPlus('Hora de Fim das Inscrições', null=True, blank=True)
    exibir_participantes_inscricao = models.BooleanField(
        'Exibir Participantes na Inscrição',
        default=False,
        help_text='Marque este campo caso deseje exibir a lista de participantes já inscritos nas atividades na página de inscrição.',
    )

    class Meta:
        verbose_name = 'Tipo de Participante'
        verbose_name_plural = 'Tipos de Participante'

    def clean(self):
        if not hasattr(self, 'tipo_participacao'):
            raise ValidationError('Selecione um Tipo de Participação.')

        # Verificar se o evento já possui esse tipo_participacao
        if self.evento_id and self.evento.tipos_participante.filter(tipo_participacao=self.tipo_participacao).exclude(id=self.pk).exists():
            raise ValidationError(f'Já existe um tipo de participação ({self.tipo_participacao.descricao}) cadastrado neste evento.')

        try:
            data = self.modelo_certificado.read()
            self.modelo_certificado.seek(0)
        except Exception:
            data = b''

        try:
            dicionario = {
                '#INSTITUICAO#': 'IFRN',
                '#NOMEDOPARTICIPANTE#': 'Teste',
                '#TIPODOPARTICIPANTE#': 'Teste',
                '#TIPOPARTICIPACAO#': 'Organizador',
                '#PARTICIPANTE#': 'Teste',
                '#CPF#': '000.000.000-00',
                '#NOMEDOEVENTO#': 'Teste',
                '#EVENTO#': 'Teste',
                '#ATIVIDADES#': 'Organizador',
                '#ATIVIDADESDETALHADAS#': 'Teste',
                '#ATIVIDADESCONFIRMADAS#': 'Atividade 1, Atividade 2',
                '#TOTALDETRABALHOSAVALIADOS#': '2',
                '#TRABALHOSAVALIADOS#': 'Trabalho 1, Trabalho 2',
                '#TOTALDETRABALHOSAPROVADOS#': '2',
                '#TRABALHOSAPROVADOS#': 'Trabalho 1, Trabalho 2',
                '#LOCAL#': 'Auditório',
                '#CAMPUS#': 'TESTE',
                '#CARGAHORARIA#': '20h',
                '#CARGAHORARIAATIVIDADESCONFIRMADAS#': '20h',
                '#DATAINICIALADATAFINAL#': '01/01/2020 a 31/12/2020',
                '#PERIODOREALIZACAO#': 'periodo_realizacao',
                '#SETORRESPONSAVEL#': 'pelo setor TESTE',
                '#CIDADE#': 'Natal',
                '#UF#': 'RN',
                '#DATAEMISSAO#': '01/01/2020',
                '#DATA#': '31/12/2020',
                '#CODIGOVERIFICADOR#': 'Documento emitido pelo SUAP. Comprove sua autenticidade em ',
            }

            if data:
                arquivo = gerar_documento_impressao(dicionario, io.BytesIO(data))
                with open(arquivo, 'rb') as f:
                    pdf = f.read()
                success = check_pdf(io.BytesIO(pdf))
                if not success:
                    raise ValidationError('PDF inválido.')
        except Exception as e:
            if settings.DEBUG:
                raise e
            raise ValidationError(str(e))

    def __str__(self):
        if self.limite_inscricoes:
            return f'{self.tipo_participacao.descricao} - Limite de inscrições: {self.limite_inscricoes}'
        else:
            return self.tipo_participacao.descricao

    def get_periodo_inscricao(self):
        if self.data_inicio_inscricoes and self.data_fim_inscricoes:
            return f'{self.data_inicio_inscricoes.strftime("%d/%m/%Y")} a {self.data_fim_inscricoes.strftime("%d/%m/%Y")}'
        return ''

    def get_modelo_certificado(self):
        return self.modelo_certificado or self.tipo_participacao.get_modelo_certificado_padrao()

    def get_inscritos(self):
        return self.evento.participantes.filter(tipo__tipo_participacao=self.tipo_participacao)

    def get_qtd_vagas_disponiveis(self):
        if self.limite_inscricoes is None:
            return None
        qtd = self.limite_inscricoes - self.get_inscritos().count()
        return max(0, qtd)

    def eh_avaliador_ou_convidado_ou_participante(self):
        return self.tipo_participacao.descricao.lower() in ['avaliador de trabalho', 'convidado', 'participante']

    def eh_avaliador_de_trabalho(self):
        return self.tipo_participacao.descricao.lower() == 'avaliador de trabalho'

    def eh_convidado(self):
        return self.tipo_participacao.descricao.lower() == 'convidado'

    def eh_participante(self):
        return self.tipo_participacao.descricao.lower() == 'participante'

    def tem_participantes_vinculados(self):
        return self.get_inscritos().exists()

    def eh_organizador(self):
        return self.tipo_participacao.descricao.lower() == TIPO_PARTICIPACAO_ORGANIZADOR.lower()


class TipoAtividade(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição', validate_caracter=True)

    class Meta:
        verbose_name = 'Tipo de Atividade'
        verbose_name_plural = 'Tipos de Atividade'

    def __str__(self):
        return self.descricao


class Internacionalizacao(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento')
    idioma = models.CharFieldPlus('Idioma', max_length=5, choices=settings.LANGUAGES)
    titulo = models.CharFieldPlus(verbose_name='Título', validate_caracter=True)
    apresentacao = models.TextField('Apresentação', help_text='Espaço para que sejam falados os objetivos principais etc.')
    local = models.CharFieldPlus(validate_caracter=True)

    class Meta:
        verbose_name = 'Internacionalização'
        verbose_name_plural = 'Internacionalizações'
        unique_together = ('evento', 'idioma')

    def __str__(self):
        return f'{self.titulo} ({self.idioma})'


class AtividadeEvento(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento')
    tipo = models.ForeignKeyPlus(TipoAtividade, verbose_name='Tipo de Atividade')
    descricao = models.CharFieldPlus(verbose_name='Título', validate_caracter=True)
    ch = models.IntegerField(verbose_name='Carga Horária em segundos')
    data = models.DateFieldPlus('Data de início', null=True, blank=True)
    hora = models.TimeFieldPlus('Hora de início', null=True, blank=True)
    limite_inscricoes = models.IntegerField(verbose_name='Limite de Inscrições', null=True, blank=True)
    modelo_certificado = models.FileFieldPlus(
        upload_to='eventos/modelo_certificado_atividade/',
        null=True,
        blank=True,
        verbose_name='Modelo de Certificado',
        filetypes=['doc'],
        help_text='O arquivo de modelo deve ser uma arquivo .docx contendo as marcações #EVENTO#, #PARTICIPANTE#, #CPF#, #CAMPUS#, #CIDADE#, #UF#, #DATA#, #CODIGOVERIFICADOR#, #TIPOATIVIDADE#, #ATIVIDADE#, #CHATIVIDADE#. Não preencher caso deseje utilizar o modelo padrão.',
    )
    # Participantes inscritos e com presença confirmada
    participantes = models.ManyToManyFieldPlus('eventos.Participante', verbose_name='Participantes', blank=True)
    data_fim = models.DateFieldPlus('Data de fim', null=True, blank=False)
    hora_fim = models.TimeFieldPlus('Hora de fim', null=True, blank=False)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def __str__(self):
        return f'{self.descricao} ({self.tipo} de {self.get_ch()}h)'

    def get_detalhes_da_atividade(self):
        retorno = f'{self.descricao} - {self.tipo} - {self.get_ch()}h'
        if self.data and self.data_fim:
            retorno += f' - período: {self.data.strftime("%d/%m/%Y")} a {self.data_fim.strftime("%d/%m/%Y")}'
        elif self.data:
            retorno += f' - em {self.data.strftime("%d/%m/%Y")}'
        return retorno

    def get_participantes_exibiveis(self):
        return self.evento.participantes.filter(atividades=self).exclude(tipo__exibir_participantes_inscricao=False)

    def get_inscritos(self):
        return self.evento.participantes.filter(atividades=self)

    def get_qtd_vagas_disponiveis(self):
        if self.limite_inscricoes is None:
            return None
        qtd = self.limite_inscricoes - self.get_inscritos().count()
        return max(0, qtd)

    def get_ch(self):
        return Participante.segundos_para_tempo(self.ch)

    def get_periodo(self):
        if self.data and self.hora and self.data_fim and self.hora_fim:
            if self.data != self.data_fim:
                return f'{self.data.strftime("%d/%m/%Y")} às {self.hora.strftime("%H:%M")} até {self.data_fim.strftime("%d/%m/%Y")} às {self.hora_fim.strftime("%H:%M")}'
            else:
                return f'{self.data.strftime("%d/%m/%Y")} das {self.hora.strftime("%H:%M")} às {self.hora_fim.strftime("%H:%M")}'
        elif self.data and self.hora:
            return f'{self.data.strftime("%d/%m/%Y")} às {self.hora.strftime("%H:%M")}'
        elif self.data and self.data_fim:
            if self.data != self.data_fim:
                return f'{self.data.strftime("%d/%m/%Y")} até {self.data_fim.strftime("%d/%m/%Y")}'
            else:
                return f'{self.data.strftime("%d/%m/%Y")}'
        elif self.data:
            return f'{self.data.strftime("%d/%m/%Y")}'
        return None


class Participante(models.ModelPlus):
    objects = ParticipanteQuerySet.as_manager()

    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento', related_name='participantes')
    nome = models.CharFieldPlus(verbose_name='Nome', validate_caracter=True)
    cpf = models.BrCpfField(verbose_name='CPF', null=True)
    nacionalidade = models.IntegerField('Nacionalidade', choices=Nacionalidade.choices, blank=True, null=True)
    pais_origem = models.ForeignKeyPlus('comum.Pais', verbose_name='País de Origem', null=True, on_delete=models.CASCADE)  # para estrangeiro
    passaporte = models.CharFieldPlus(max_length=12, verbose_name='Nº do Passaporte', blank=True, null=True)
    tipo = models.ForeignKeyPlus(TipoParticipante, verbose_name='Tipo', related_name='participantes', null=True)
    publico_alvo = models.ForeignKeyPlus(PublicoAlvoEvento, verbose_name='Perfil', null=True)
    email = models.EmailField(verbose_name='E-mail')
    telefone = models.BrTelefoneField(verbose_name='Telefone', null=True, blank=True, max_length=15)
    data_cadastro = models.DateTimeField(auto_now_add=True, verbose_name='Data do Cadastro')
    inscricao_validada = models.BooleanField(verbose_name='Inscrição Validada', default=True)
    presenca_confirmada = models.BooleanField(verbose_name='Presença Confirmada', default=False)
    certificado_enviado = models.BooleanField(verbose_name='Certificado Enviado', default=False)
    codigo_geracao_certificado = models.CharFieldPlus(max_length=16, null=True, verbose_name='Código de Validação')
    carga_horaria = models.CharField(
        'Carga Horária',
        null=True,
        blank=True,
        max_length=25,
        help_text='Carga Horária de participação no evento. Se não for preenchida, a carga horária do evento será utilizada.',
    )
    ch_extensao = models.IntegerField(
        verbose_name='Carga Horária de Extensão', null=True, blank=True, help_text='Carga horária total destinada a atividade curricular de extensão'
    )

    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo', null=True, blank=True)
    # Atividades que o participante se inscreveu
    atividades = models.ManyToManyFieldPlus(AtividadeEvento, verbose_name='Atividades', blank=True)
    forma_participacao = models.PositiveSmallIntegerField(
        verbose_name='Forma de Participação no Evento', null=True, blank=True, choices=FormaParticipacaoEvento.choices
    )
    situacao_convite = models.CharFieldPlus('Situação do convite', max_length=3, null=True, blank=True, choices=SituacaoConvite.choices)
    foto = models.ImageFieldPlus(verbose_name='Foto', upload_to='eventos/foto_participante/', null=True, blank=True)
    curriculo = models.TextField('Currículo', null=True, blank=True)
    chave_acesso = models.CharFieldPlus(verbose_name='Chave de acesso', null=True, blank=True)

    class Meta:
        verbose_name = 'Participação em Evento'
        verbose_name_plural = 'Participações em Evento'

    def get_qtd_avaliacoes_pendentes(self):
        """
        Retorna a quantidade de avaliações pendentes para este participante.
        """
        return AvaliacaoSubmissao.objects.filter(avaliador_modalidade__avaliador=self, data_hora_nota__isnull=True).count()

    def get_nome_curto(self):
        nomes = self.nome.split()
        if len(nomes) > 2:
            primeiro_nome = nomes[0]
            ultimo_nome = nomes[-1]
            return f'{primeiro_nome} {ultimo_nome}'
        return self.nome

    def get_documento_identificacao(self):
        if self.passaporte:
            return {'tipo_documento': 'Passaporte', 'numero_documento': self.passaporte}
        else:
            return {'tipo_documento': 'CPF', 'numero_documento': self.cpf}

    def gerar_qr_code(self):
        url = f'{settings.SITE_URL}/eventos/exibir_informacoes_participante/{self.id}/'
        qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=10, border=4)
        qr.add_data(url)
        qr.make(fit=True)
        qr_img = qr.make_image(fill_color='black', back_color='white')
        temp_qr_file = tempfile.NamedTemporaryFile(delete=True, suffix='.png')
        qr_img.save(temp_qr_file, format='png')
        return temp_qr_file

    def get_modelo_certificado(self):
        if self.tipo:
            return self.tipo.get_modelo_certificado()

    def respondeu_avaliacao_evento(self):
        if hasattr(self, 'avaliacao_realizada'):
            return self.avaliacao_realizada
        return RespostaParticipante.objects.filter(
            participante=self,
            pergunta__tipo_questionario=TipoQuestionario.AVALIACAO,
        ).exists()

    def certificado_esta_disponivel(self):
        if not self.evento.gera_certificado:
            return False
        if not self.evento.estah_realizado():
            return False
        if not self.presenca_confirmada:
            return False
        return not (self.evento.exigir_avaliacao_para_certificado and not self.respondeu_avaliacao_evento())

    def esta_apto_para_certificado(self):
        return self.certificado_esta_disponivel() and not self.codigo_geracao_certificado

    def emitir_certificado(self, marcar_como_enviado=False):
        if not self.certificado_esta_disponivel():
            return False

        self.evento.registrar_data_emissao_certificado()
        update_fields = []
        if not self.codigo_geracao_certificado:
            self.codigo_geracao_certificado = hashlib.sha1(
                f'{self.nome}{self.email}{self.evento_id}{self.data_cadastro}{settings.SECRET_KEY}'.encode()
            ).hexdigest()[0:16]
            update_fields.append('codigo_geracao_certificado')
        if marcar_como_enviado:
            self.certificado_enviado = True
            update_fields.append('certificado_enviado')
        if update_fields:
            self.save(update_fields=update_fields)
        return True

    def marcar_certificado_como_enviado(self):
        if self.certificado_enviado:
            return
        self.certificado_enviado = True
        self.save(update_fields=['certificado_enviado'])

    def eh_avaliador_sem_modalidade_vinculada(self):
        return not self.avaliadormodalidade_set.filter(areas_tematicas__isnull=False).exists()

    def get_situacao_convite_class(self):
        if (not self.situacao_convite) or (self.situacao_convite in [SituacaoConvite.NAO_ENVIADO, SituacaoConvite.RECUSADO]):
            return 'error'
        elif self.situacao_convite == SituacaoConvite.ENVIADO:
            return 'alert'
        else:
            return 'success'

    def convite_aceito(self):
        return self.situacao_convite and self.situacao_convite == SituacaoConvite.ACEITO

    def get_url_download_certificado(self, atividade_id=None):
        result = f'{settings.SITE_URL}/eventos/baixar_certificado/{self.evento.pk}/'
        if self.codigo_geracao_certificado:
            result = f'{settings.SITE_URL}/eventos/download/{self.codigo_geracao_certificado}/'
            if atividade_id:
                result += f'{atividade_id}/'
        return result

    def get_trabalhos_avaliados(self):
        """Função para retornar os trabalhos avaliados pelo participante, com base nos modelos: AvaliacaoSubmissao e AvaliadorModalidade"""
        avaliacoes = AvaliacaoSubmissao.objects.filter(avaliador_modalidade__avaliador_id=self.pk, nota__isnull=False).distinct()
        return Submissao.objects.filter(versoes__pareceres__in=avaliacoes).distinct()

    def get_trabalhos_aprovados(self):
        """Função para retornar os trabalhos aprovados do participante, com base no modelo: Submissao"""
        return Submissao.objects.filter(autores_relacionados__participante__in=[self.pk], resultado_avaliacao=ResultadoAvaliacao.APROVADO)

    def get_dados_certificado(self, atividade_id=None):
        if self.evento.data_fim and self.evento.data_inicio != self.evento.data_fim:
            periodo_realizacao = f'no período de {format_daterange(self.evento.data_inicio, self.evento.data_fim)}'
        else:
            periodo_realizacao = f'em {format_datetime(self.evento.data_inicio)}'

        atividades_id = atividade_id and [atividade_id] or None
        atividades_confirmadas_participante = self.get_atividades(atividades_id, confirmadas=True)
        atividades_participante_em_detalhes = [atividade.get_detalhes_da_atividade() for atividade in atividades_confirmadas_participante]

        if self.tipo.tipo_participacao.descricao.lower() != 'participante':
            tipo_participacao = f'como {self.tipo.tipo_participacao.descricao.lower()}'
        else:
            tipo_participacao = ''

        trabalhos_avaliados = []
        trabalhos_aprovados = []
        if self.pk:
            for submissao in self.get_trabalhos_avaliados():
                trabalhos_avaliados.append(submissao.titulo)
            for submissao in self.get_trabalhos_aprovados():
                trabalhos_aprovados.append(submissao.titulo)

        total_trabalhos_avaliados = len(trabalhos_avaliados)
        total_trabalhos_aprovados = len(trabalhos_aprovados)

        dicionario = {
            '#INSTITUICAO#': str(Config.get_valor_por_chave('comum', 'instituicao')),
            '#NOMEDOPARTICIPANTE#': self.nome,
            '#TIPODOPARTICIPANTE#': self.tipo.tipo_participacao.descricao,
            '#TIPOPARTICIPACAO#': tipo_participacao,
            '#PARTICIPANTE#': self.nome,
            '#CPF#': self.cpf,
            '#NOMEDOEVENTO#': self.evento.nome,
            '#EVENTO#': self.evento.nome,
            '#ATIVIDADES#': format_iterable(atividades_confirmadas_participante),
            '#ATIVIDADESCONFIRMADAS#': format_iterable(atividades_confirmadas_participante),
            '#ATIVIDADESDETALHADAS#': format_iterable(atividades_participante_em_detalhes),
            '#TRABALHOSAVALIADOS#': format_iterable(trabalhos_avaliados),
            '#TOTALDETRABALHOSAVALIADOS#': total_trabalhos_avaliados,
            '#TRABALHOSAPROVADOS#': format_iterable(trabalhos_aprovados),
            '#TOTALDETRABALHOSAPROVADOS#': total_trabalhos_aprovados,
            '#LOCAL#': str(self.evento.local),
            '#CAMPUS#': str(self.evento.campus),
            '#CARGAHORARIA#': self.get_ch_total(atividades_confirmadas_participante),
            '#CARGAHORARIAATIVIDADESCONFIRMADAS#': self.get_ch_total(atividades_confirmadas_participante),
            '#DATAINICIALADATAFINAL#': format_daterange(self.evento.data_inicio, self.evento.data_fim),
            '#PERIODOREALIZACAO#': periodo_realizacao,
            '#SETORRESPONSAVEL#': self.evento.setor and f'pelo setor {self.evento.setor}' or '',
            '#CIDADE#': self.evento.campus.municipio.nome,
            '#UF#': self.evento.campus.municipio.uf,
            '#DATAEMISSAO#': format_datetime(self.evento.data_fim),
            '#DATA#': format_datetime(date.today()),
            '#CODIGOVERIFICADOR#': f'Documento emitido pelo SUAP. Comprove sua autenticidade em {self.get_url_download_certificado(atividade_id)}',
        }
        return dicionario

    def save(self, *args, **kwargs):
        insert = not self.pk
        if insert and (self.tipo and self.tipo.eh_avaliador_de_trabalho() or self.tipo.eh_convidado()):
            self.situacao_convite = SituacaoConvite.NAO_ENVIADO
        super().save(*args, **kwargs)
        self.registrar_ch_extensao()

    def registrar_ch_extensao(self):
        aluno = self.get_aluno_extensao()
        if aluno:
            self.vinculo = aluno.get_vinculo()
            is_organizador = self.tipo.tipo_participacao.descricao == TIPO_PARTICIPACAO_ORGANIZADOR
            is_monitor = (
                self.tipo.tipo_participacao.descricao == 'Palestrante'
                and self.evento.subtipo.nome == 'Minicursos'
                and self.evento.subtipo.tipo.descricao == 'Científico/tecnológico'
            )
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            self.ch_extensao = 0
            if self.presenca_confirmada and (is_organizador or is_monitor):
                self.ch_extensao = round((sum(self.atividades.values_list('ch', flat=True)) or self.evento.carga_horaria or 0) * 1.0 / 3600)
            super().save()
            descricao = f'{self.evento.nome} [{TIPO_PARTICIPACAO_ORGANIZADOR if is_organizador else TIPO_PARTICIPACAO_MONITOR}]'
            ch_curricular = self.ch_extensao * 100 if settings.COMPONENTE_CH_DECIMAL else self.ch_extensao
            AtividadeCurricularExtensao.registrar(aluno, type(self), self.pk, ch_curricular, descricao, self.presenca_confirmada or False)

    def is_aluno_extensao(self):
        return self.get_aluno_extensao() is not None

    def get_aluno_extensao(self) -> Any | None:
        if 'edu' in settings.INSTALLED_APPS and self.evento.dimensoes.filter(descricao='Extensão').exists():
            Aluno = apps.get_model('edu', 'Aluno')
            SituacaoMatricula = apps.get_model('edu', 'SituacaoMatricula')
            situacoes_ativas = (SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL)

            if self.vinculo_id and self.vinculo.eh_aluno():
                return Aluno.objects.filter(
                    pk=self.vinculo.id_relacionamento,
                    matriz__ch_atividades_extensao__gt=0,
                    situacao__in=situacoes_ativas,
                ).first()

            if not self.vinculo_id and self.cpf:
                return (
                    Aluno.objects.filter(
                        pessoa_fisica__cpf=self.cpf,
                        matriz__ch_atividades_extensao__gt=0,
                        situacao__in=situacoes_ativas,
                    )
                    .order_by('-ano_letivo__ano', '-periodo_letivo')
                    .first()
                )
        return None

    def delete(self, *args, **kwargs):
        aluno = self.get_aluno_extensao()
        if aluno:
            AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
            AtividadeCurricularExtensao.registrar(aluno, type(self), self.pk, 0, None)
        super().delete(*args, **kwargs)

    def checar_vinculo(self):
        if self.cpf is None:
            raise ValidationError('CPF não informado ou inválido.')
        self.vinculo = None
        if self.publico_alvo and self.publico_alvo.id in (
            PublicoAlvoEvento.ESTUDANTES,
            PublicoAlvoEvento.SERVIDORES,
            PublicoAlvoEvento.GESTORES,
            PublicoAlvoEvento.TERCEIRIZADOS,
            PublicoAlvoEvento.ESTAGIARIOS,
        ):
            for vinculo in Vinculo.objects.filter(pessoa__pessoafisica__cpf=self.cpf, ativo=True):
                if self.publico_alvo.id == PublicoAlvoEvento.ESTUDANTES and vinculo.eh_aluno():
                    self.vinculo = vinculo
                    break
                if self.publico_alvo.id == PublicoAlvoEvento.SERVIDORES and vinculo.eh_servidor():
                    self.vinculo = vinculo
                    break
                if self.publico_alvo.id == PublicoAlvoEvento.GESTORES and vinculo.eh_servidor():
                    if vinculo.relacionamento.historico_funcao().filter(data_fim_funcao__isnull=True).exists():
                        self.vinculo = vinculo
                        break
                if self.publico_alvo.id == PublicoAlvoEvento.TERCEIRIZADOS and vinculo.eh_prestador():
                    self.vinculo = vinculo
                    break
                if self.publico_alvo.id == PublicoAlvoEvento.ESTAGIARIOS and vinculo.eh_servidor():
                    self.vinculo = vinculo
                    break
            if not self.vinculo:
                raise ValidationError(f'Nenhum vículo de "{self.publico_alvo}" localizado para o CPF: {self.cpf}.')

    def checar_publico_alvo(self):
        if self.vinculo.eh_aluno():
            self.publico_alvo_id = PublicoAlvoEvento.ESTUDANTES
        elif self.vinculo.eh_servidor() and self.vinculo.relacionamento.eh_estagiario:
            self.publico_alvo_id = PublicoAlvoEvento.ESTAGIARIOS
        elif self.vinculo.eh_servidor() and self.vinculo.relacionamento.historico_funcao().filter(data_fim_funcao__isnull=True).exists():
            self.publico_alvo_id = PublicoAlvoEvento.GESTORES
        elif self.vinculo.eh_servidor():
            self.publico_alvo_id = PublicoAlvoEvento.SERVIDORES
        elif self.vinculo.eh_prestador():
            self.publico_alvo_id = PublicoAlvoEvento.TERCEIRIZADOS

    def get_ch_inscrita(self):
        # Otimização: usa valor pré-calculado se disponível (annotation ch_atividades_soma)
        if hasattr(self, 'ch_atividades_soma'):
            if self.evento.subtipo and self.evento.subtipo.multiplas_atividades:
                ch = self.ch_atividades_soma or 0
                ch = Participante.segundos_para_tempo(ch)
            else:
                ch = self.evento.carga_horaria
            if ch is None:
                return self.carga_horaria or 0
            return ch

        # Fallback: cálculo tradicional (mais lento)
        if self.evento.subtipo and self.evento.subtipo.multiplas_atividades:
            ch = self.atividades.aggregate(ch=Sum('ch')).get('ch') or 0
            ch = Participante.segundos_para_tempo(ch)
        else:
            ch = self.evento.carga_horaria
        if ch is None:
            return self.carga_horaria or 0
        return ch

    def get_ch_total(self, atividades=None):
        ch = 0
        if not atividades and self.tipo.tipo_participacao.ch_organizacao:
            if self.evento.carga_horaria:
                ch = int(self.evento.carga_horaria)
            else:
                atividades = self.evento.atividadeevento_set.all()
                ch = atividades.aggregate(ch=Sum('ch')).get('ch') or 0
            ch = ch * 1.2
        else:
            if self.evento.subtipo and self.evento.subtipo.multiplas_atividades:
                ch = self.get_atividades(atividades=atividades).aggregate(ch=Sum('ch')).get('ch') or 0
            else:
                ch = self.carga_horaria or self.evento.carga_horaria
        return Participante.segundos_para_tempo(ch)

    def get_atividades(self, atividades=None, confirmadas=None):
        qs = self.atividades.all()
        if atividades:
            qs = qs.filter(id__in=atividades)
        if confirmadas is True:
            qs = qs.filter(participantes__id=self.id)
        return qs

    @staticmethod
    def segundos_para_tempo(segundos=0):
        if segundos:
            try:
                segundos = int(segundos)
            except Exception:
                return '-'
            if segundos >= 0:
                minutos, segundos = divmod(segundos, 60)
                horas, minutos = divmod(minutos, 60)
                return f'{horas:.0f}:{minutos:02.0f}'
        return '-'

    @staticmethod
    def tempo_para_segundos(tempo):
        if tempo and tempo != '-':
            hora, minuto = tempo.split(':')
            return int(hora) * 60 * 60 + int(minuto) * 60
        return 0

    def cria_autor_de_trabalho(self):
        """
        Cria um novo participante do tipo "Autor de Trabalho" a partir do participante atual.
        Retorna:
            Participante: Um novo participante do tipo "Autor de Trabalho" ou o participante atual
            se o tipo de participação não existir ou se já existir um participante do tipo "Autor de Trabalho" com o mesmo email no evento.
        """
        tipo_participacao = TipoParticipacao.objects.filter(descricao='Autor de trabalho').first()
        if not tipo_participacao:
            return self

        tipo_participante, _ = TipoParticipante.objects.get_or_create(tipo_participacao=tipo_participacao, evento=self.evento)

        autor, _ = Participante.objects.get_or_create(
            evento=self.evento,
            tipo=tipo_participante,
            email=self.email,
            cpf=self.cpf,
            defaults={
                'nome': self.nome,
                'nacionalidade': self.nacionalidade,
                'pais_origem': self.pais_origem,
                'passaporte': self.passaporte,
                'publico_alvo': self.publico_alvo,
                'telefone': self.telefone,
                'inscricao_validada': True,
                'presenca_confirmada': True,
                'codigo_geracao_certificado': self.codigo_geracao_certificado,
                'carga_horaria': self.carga_horaria,
                'ch_extensao': self.ch_extensao,
                'vinculo': self.vinculo,
                'forma_participacao': self.forma_participacao,
                'situacao_convite': self.situacao_convite,
                'foto': self.foto,
                'curriculo': self.curriculo,
                'chave_acesso': self.chave_acesso,
            },
        )
        return autor


class FotoEvento(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento')
    imagem = models.ImageFieldPlus(verbose_name='Imagem', upload_to='fotos_eventos')
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Foto de Evento'
        verbose_name_plural = 'Fotos de Evento'

    def __str__(self):
        return self.descricao


class VideoEvento(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento')
    video = models.URLField(verbose_name='Vídeo', help_text='Informe a URL do vídeo.')
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Vídeo de Evento'
        verbose_name_plural = 'Vídeos de Evento'

    def __str__(self):
        return self.video


class AnexoEvento(models.ModelPlus):
    evento = models.ForeignKeyPlus(Evento, verbose_name='Evento')
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='anexos_eventos')
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True)

    class Meta:
        verbose_name = 'Anexo de Evento'
        verbose_name_plural = 'Anexos de Evento'

    def __str__(self):
        return self.descricao


class Banner(models.ModelPlus):
    INICIO = 'Início'
    TIPO_CHOICES = ((INICIO, INICIO),)
    titulo = models.CharFieldPlus('Título', max_length=1000)
    imagem = models.FileFieldPlus('Imagem', upload_to='eventos/banner', max_length=255)
    tipo = models.CharFieldPlus('Tipo', max_length=100, choices=TIPO_CHOICES, default=INICIO)
    link = models.CharFieldPlus('Link', max_length=1000, null=True, blank=True)
    data_inicio = models.DateTimeField('Início da Publicação')
    data_termino = models.DateTimeField('Término da Publicação')

    class Meta:
        verbose_name = 'Banner'
        verbose_name_plural = 'Banners'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        cache.delete('_cache_index_quadros_banners')


class TipoAtendimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Tipo de Atendimento'
        verbose_name_plural = 'Tipos de Atendimentos'

    def __str__(self):
        return self.descricao


class MotivoAtendimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Motivo de Atendimento'
        verbose_name_plural = 'Motivos de Atendimentos'

    def __str__(self):
        return self.descricao


class AssuntoAtendimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Assunto de Atendimento'
        verbose_name_plural = 'Assuntos de Atendimentos'

    def __str__(self):
        return self.descricao


class PublicoAtendimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Público de Atendimento'
        verbose_name_plural = 'Públicos de Atendimentos'

    def __str__(self):
        return self.descricao


class SituacaoAtendimento(models.ModelPlus):
    descricao = models.CharFieldPlus('Descrição')

    class Meta:
        verbose_name = 'Situação de Atendimento'
        verbose_name_plural = 'Situações de Atendimentos'

    def __str__(self):
        return self.descricao


class AtendimentoPublico(models.ModelPlus):
    campus = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name='Campus')
    tipo = models.ForeignKeyPlus(TipoAtendimento)
    motivo = models.ForeignKeyPlus(MotivoAtendimento)
    assunto = models.ForeignKeyPlus(AssuntoAtendimento)
    publico = models.ForeignKeyPlus(PublicoAtendimento, verbose_name='Público')
    situacao = models.ForeignKeyPlus(SituacaoAtendimento, verbose_name='Situação')
    data_cadastro = models.DateTimeField('Data/Hora do Cadastro', auto_now_add=True)

    class Meta:
        verbose_name = 'Atendimento ao Público'
        verbose_name_plural = 'Atendimentos ao Público'


class LogProcessamentoSubmissao(models.Model):
    evento = models.ForeignKey('Evento', on_delete=models.CASCADE)
    mensagem = models.TextField('Mensagem', help_text='Mensagem de log do processamento da submissão')
    fluxo_submissao = models.ForeignKey('FluxoSubmissao', on_delete=models.CASCADE, null=True)
    data_hora = models.DateTimeField(auto_now_add=True)
    executado_por = models.ForeignKeyPlus(User, verbose_name='Executado Por', null=True, blank=True)

    class Meta:
        verbose_name = 'Log de Processamento de Submissão'
        verbose_name_plural = 'Logs de Processamento de Submissão'
        ordering = ['evento', '-data_hora']
        unique_together = ('evento', 'fluxo_submissao', 'data_hora')

    def __str__(self):
        return f'{self.evento} - {self.fluxo_submissao} ({self.data_hora})'

    def get_executado_por(self):
        if self.executado_por:
            return self.executado_por.get_profile().nome_usual
        return 'Sistema'

    get_executado_por.short_description = 'Executado Por'
