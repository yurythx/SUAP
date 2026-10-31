import copy
import datetime
import html
import importlib
import re
from collections.abc import Iterable

import itertools
import unicodedata
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models import OuterRef, Subquery, Q, Case, When, Value, Max, Count
from django.db.models.aggregates import Sum
from django.template import Context, Template
from django.template.defaultfilters import pluralize
from django.urls import reverse
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe

from comum.models import Configuracao, Vinculo
from djtools.db import models, transaction
from djtools.db.models import FileFieldPlus
from djtools.templatetags.filters import in_group, format_
from djtools.utils import normalizar_nome_proprio, render_to_string, get_datetime_now, send_notification
from djtools.utils.response import substituir_marcadores
from edu.models import PERIODO_LETIVO_CHOICES, AtoRegulatorioCurso, Diretoria, LogModel, CursoCampus
from pafc.managers import ModeloPAFCManager
from pafc.templatetags.pafc_tags import normalizar_formatacao
from pafc.utils import modulo_documento_eletronico_esta_ativo, eh_diretor_academico
from patrimonio.models import Inventario
from ppc.models import ProjetoPedagogicoCurso, PlanoDisciplina, MatrizPPC, PlanoDisciplinaPPC
from ppc.utils import extrair_bibliografias_da_secao
from rh.models import Setor, Servidor


class ModeloPAFC(LogModel):
    MARCADOR_QUEBRA_PAGINA = 'quebra_de_pagina'
    MARCADOR_CAMPUS = 'campus'
    MARCADOR_ENDERECO_CAMPUS = 'endereco_do_campus'
    MARCADOR_NOME_CURSO = 'nome_curso'
    MARCADOR_RESOLUCAO_PPC_CRIACAO = 'resolucao_ppc_criacao'
    MARCADOR_TOTAL_VAGAS_ANUAIS = 'total_vagas_anuais'
    MARCADOR_PERIODO_INICIO_OFERTA = 'periodo_inicio_oferta'
    MARCADOR_NOME_COORDENADOR = 'nome_coordenador'
    MARCADOR_MATRICULA_COORDENADOR = 'matricula_coordenador'
    MARCADOR_TECNICOS_ADMINISTRATIVOS = 'tecnicos_administrativos'
    MARCADOR_DOCENTES = 'docentes'
    MARCADOR_LABORATORIOS = 'laboratorios'
    MARCADOR_MATRIZES = 'matrizes'
    MARCADOR_BIBLIOGRAFIA_BASICA = 'bibliografia_basica'
    MARCADOR_BIBLIOGRAFIA_COMPLEMENTAR = 'bibliografia_complementar'
    MARCADOR_POLOS = 'polos'
    MARCADOR_TUTORES = 'tutores'
    MARCADOR_PDTECS_TOPICOS_ESPECIFICOS = 'pdtecs_topicos_especificos'

    VERSAO_PRESENCIAL = 10
    VERSAO_SEMIPRESENCIAL = 20
    VERSAO_EAD = 30

    VERSAO_CHOICES = (
        (VERSAO_PRESENCIAL, 'Presencial'),
        (VERSAO_SEMIPRESENCIAL, 'Presencial com carga horária EaD'),
        (VERSAO_EAD, 'EaD'),
    )

    descricao = models.CharFieldPlus('Descrição')
    data_criacao = models.DateFieldPlus('Data de Criação', auto_now_add=True)
    tipo_oferta = models.ForeignKeyPlus('edu.Modalidade', verbose_name='Tipo de Oferta')
    versao_modelo = models.PositiveIntegerFieldPlus('Versão do Modelo', choices=VERSAO_CHOICES, default=VERSAO_PRESENCIAL)
    ativo = models.BooleanField('Ativo', default=True)

    objects = ModeloPAFCManager()

    class Meta:
        verbose_name = 'Modelo de PAFC'
        verbose_name_plural = 'Modelos de PAFCs'

    def get_absolute_url(self):
        return f'/pafc/modelo_pafc/{self.id}/'

    def clean(self):
        if ModeloPAFC.objects.ativos().filter(tipo_oferta_id=self.tipo_oferta_id, versao_modelo=self.versao_modelo).exclude(id=self.pk).exists():
            raise ValidationError(
                f'Já existe um modelo de PAFC ativo para a versão {self.get_versao_modelo_display().lower()} da modalidade "{self.tipo_oferta}".'
            )
        return super().clean()

    @transaction.atomic
    def replicar(self, descricao, tipo_oferta, versao_modelo):
        replicado = ModeloPAFC()
        replicado.descricao = descricao
        replicado.tipo_oferta = tipo_oferta
        replicado.versao_modelo = versao_modelo
        replicado.save()

        for secao in self.secao_set.all():
            secao_replicada = copy.copy(secao)
            secao_replicada.id = None
            secao_replicada.modelo_pafc = replicado
            secao_replicada.save()
            for conteudo in secao.conteudo_set.all():
                conteudo_replicado = copy.copy(conteudo)
                conteudo_replicado.id = None
                conteudo_replicado.secao = secao_replicada
                conteudo_replicado.save()

        return replicado

    def get_secoes(self):
        return self.secao_set.order_by('ordem_exibicao')

    @classmethod
    def get_marcadores(cls):
        return {
            cls.MARCADOR_QUEBRA_PAGINA: 'Insere uma quebra de página.',
            cls.MARCADOR_CAMPUS: 'Insere o nome do campus.',
            cls.MARCADOR_ENDERECO_CAMPUS: 'Insere o endereço do campus.',
            cls.MARCADOR_NOME_CURSO: 'Insere o nome do curso.',
            cls.MARCADOR_RESOLUCAO_PPC_CRIACAO: 'Insere a descrição da resolução que aprovou o PPC.',
            cls.MARCADOR_TOTAL_VAGAS_ANUAIS: 'Insere o total de vagas a serem ofertadas anualmente pelo curso.',
            cls.MARCADOR_PERIODO_INICIO_OFERTA: 'Insere o período de início das ofertas de vagas para o curso (ex.: 2024.1).',
            cls.MARCADOR_NOME_COORDENADOR: 'Insere o nome do coordenador do curso.',
            cls.MARCADOR_MATRICULA_COORDENADOR: 'Insere a matrícula do coordenador do curso.',
            cls.MARCADOR_TECNICOS_ADMINISTRATIVOS: 'Insere o quadro de técnicos administrativos do PAFC.',
            cls.MARCADOR_DOCENTES: 'Insere o quadro de docentes do PAFC, incluindo disciplinas associadas a eles.',
            cls.MARCADOR_LABORATORIOS: 'Insere os laboratórios adicionados ao PAFC, incluindo lista de equipamentos '
            'associados, de acordo com o módulo de Patrimônio.',
            cls.MARCADOR_MATRIZES: 'Insere o quadro de matrizes que o curso disponibilizará.',
            cls.MARCADOR_BIBLIOGRAFIA_BASICA: 'Insere o acervo da bibliografia básica disponível no campus.',
            cls.MARCADOR_BIBLIOGRAFIA_COMPLEMENTAR: 'Insere o acervo da bibliografia complementar disponível no campus.',
            cls.MARCADOR_POLOS: 'Insere a relação de polos EaD disponíveis para oferta do curso.',
            cls.MARCADOR_TUTORES: 'Insere a relação de tutores/mediadores disponíveis para oferta EaD do curso.',
            cls.MARCADOR_PDTECS_TOPICOS_ESPECIFICOS: 'Insere os planos das disciplinas do tipo Tópico Específico.',
        }

    @staticmethod
    def identificar_marcadores_invalidos(texto, remover_tags_html=True):
        regex_marcadores = r'\{\{[^\{\}]+\}\}'
        marcadores_invalidos = set()
        for marcador in re.findall(regex_marcadores, texto):
            marcador_sem_tags_html = html.unescape(re.sub(r'<[^>]+>', '', marcador).strip())
            nome_marcador = re.sub(r'\{{2}\s*|\s*}{2}', '', marcador_sem_tags_html)
            if nome_marcador not in ModeloPAFC.get_marcadores():
                if remover_tags_html:
                    marcadores_invalidos.add(marcador_sem_tags_html)
                else:
                    marcadores_invalidos.add(marcador)
        return marcadores_invalidos

    def possui_ch_ead(self):
        return self.eh_versao_semipresencial() or self.eh_versao_totalmente_ead()

    def eh_versao_semipresencial(self):
        return self.versao_modelo == ModeloPAFC.VERSAO_SEMIPRESENCIAL

    def eh_versao_totalmente_ead(self):
        return self.versao_modelo == ModeloPAFC.VERSAO_EAD


class Secao(LogModel):
    titulo = models.CharFieldPlus('Título')
    ordem_exibicao = models.PositiveIntegerFieldPlus('Ordem de Exibição', default=1, min_value=1)
    modelo_pafc = models.ForeignKeyPlus('pafc.ModeloPAFC', verbose_name='Modelo de PAFC')
    subsecao = models.BooleanField(
        'É subseção',
        default=False,
        help_text='Marque esta opção caso este item deva ser exibido como uma subseção da primeira seção imediatamente acima não marcada como subseção.',
    )

    class Meta:
        verbose_name = 'Seção'
        verbose_name_plural = 'Seções'
        ordering = [
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        Secao.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        Secao.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    def clean(self):
        # if PAFC.objects.filter(modelo_pafc_id=self.modelo_pafc_id, situacao=PAFC.FINALIZADO).exists():
        #     raise ValidationError('Não é possível alterar a seção de um modelo com PAFC finalizado.')
        return super().clean()

    def get_conteudos(self):
        return self.conteudo_set.order_by('ordem_exibicao')

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(secao, delete=False):
        secoes = Secao.objects.filter(modelo_pafc_id=secao.modelo_pafc_id)
        if delete:
            for seq, item in enumerate(secoes.exclude(id=secao.pk), start=1):
                if item.ordem_exibicao != seq:
                    Secao.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = secao.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > secoes.count():
                atualizacao_ordem_exibicao = secoes.count()
            nova_ordem = list(secoes.exclude(id=secao.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, secao)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    Secao.objects.filter(id=item.id).update(ordem_exibicao=seq)


class Conteudo(LogModel):
    secao = models.ForeignKeyPlus('pafc.Secao', verbose_name='Seção')
    texto = models.TextField('Texto', null=True, blank=True)
    ordem_exibicao = models.PositiveIntegerField('Ordem de Exibição')
    editavel = models.BooleanField('Editável', default=True)
    orientacao_preenchimento = models.TextField(
        'Orientação de Preenchimento',
        null=True,
        blank=True,
        help_text='Orientação de como o usuário deve preencher esse conteúdo na elaboração do PAFC.',
    )

    class Meta:
        verbose_name = 'Conteúdo'
        verbose_name_plural = 'Conteúdos'
        ordering = [
            'secao__ordem_exibicao',
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        self.texto = Conteudo.normalizar_conteudo(self.texto)
        result = super().save(*args, **kwargs)
        Conteudo.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        Conteudo.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    def clean(self):
        # if PAFC.objects.filter(modelo_pafc_id=self.secao.modelo_pafc.id, situacao=PAFC.FINALIZADO).exists():
        #     raise ValidationError('Não é possível alterar a conteúdo de um modelo com PAFC finalizado.')
        return super().clean()

    @cached_property
    def quebra_pagina_html(self):
        return Template('<div class="page-break"></div>').render(Context())

    @staticmethod
    def normalizar_conteudo(texto):
        texto = html.unescape(texto)

        # detecta eventuais tags html dentro de marcador e as coloca para fora das chaves
        marcador_sujo = r'\{{2}\s*(<[^>]+>)?\s*(\w+)\s*([^\}]*)\}{2}'

        def remover_html_interno_do_marcador(match):
            html_inicio = match.group(1) or ''
            marcador = match.group(2)
            html_final = match.group(3) or ''

            return html_inicio + '{{ ' + marcador + ' }}' + html_final

        texto = re.sub(marcador_sujo, remover_html_interno_do_marcador, texto)

        return texto

    def get_texto(self):
        if not self.texto and self.editavel:
            return '[Preenchido no PAFC]'
        texto = normalizar_formatacao(self.texto)
        contexto = {marcador: '{{ ' + marcador + ' }}' for marcador in self.secao.modelo_pafc.get_marcadores()}
        contexto.update(
            {ModeloPAFC.MARCADOR_QUEBRA_PAGINA: self.quebra_pagina_html},
        )
        return substituir_marcadores(texto, contexto)

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(conteudo, delete=False):
        conteudos = Conteudo.objects.filter(secao_id=conteudo.secao_id)
        if delete:
            for seq, item in enumerate(conteudos.exclude(id=conteudo.pk), start=1):
                if item.ordem_exibicao != seq:
                    Conteudo.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = conteudo.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > conteudos.count():
                atualizacao_ordem_exibicao = conteudos.count()
            nova_ordem = list(conteudos.exclude(id=conteudo.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, conteudo)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    Conteudo.objects.filter(id=item.id).update(ordem_exibicao=seq)


class MapeamentoVersaoPAFCModalidades(LogModel):
    versao_modelo = models.PositiveIntegerFieldPlus(
        'Versão de PAFC', choices=ModeloPAFC.VERSAO_CHOICES, default=ModeloPAFC.VERSAO_PRESENCIAL, unique=True
    )
    modalidades_de_ensino = models.ManyToManyFieldPlus(
        'edu.NaturezaParticipacao',
        verbose_name='Modalidades de ensino',
        related_name='versoes_pafc_mapeadas',
        help_text='Escolha as modalidades de ensino compatíveis com a versão de PAFC escolhida.',
    )

    class Meta:
        verbose_name = 'Mapeamento de modalidades de ensino'
        verbose_name_plural = 'Mapeamentos de modalidades de ensino'


class PAFC(LogModel):
    EM_SOLICITACAO = 1
    AGUARDANDO_PORTARIA = 3
    EM_ELABORACAO = 4
    EM_ANALISE_PRELIMINAR = 12
    AGUARDANDO_REVISAO_TECNICA = 5
    AGUARDANDO_VALIDACAO = 6
    EM_ANALISE_PROREITORIA = 11
    AGUARDANDO_APROVACAO_CAMARA = 7
    AGUARDANDO_APROVACAO_CONSEPEX = 8
    AGUARDANDO_APROVACAO_CONSUP = 9
    APROVADO = 10
    REPROVADO = 95
    FINALIZADO = 99
    ARQUIVADO = 100
    SITUACAO_CHOICES = [
        [EM_SOLICITACAO, 'Em solicitação'],
        [AGUARDANDO_PORTARIA, 'Emissão de Portaria de Comissão'],
        [EM_ELABORACAO, 'Em elaboração'],
        [EM_ANALISE_PRELIMINAR, 'Em análise preliminar'],
        [AGUARDANDO_REVISAO_TECNICA, 'Em revisão técnica'],
        [AGUARDANDO_VALIDACAO, 'Em validação'],
        [EM_ANALISE_PROREITORIA, 'Em análise da Pró-Reitoria'],
        [AGUARDANDO_APROVACAO_CAMARA, 'Em análise da Câmara'],
        [AGUARDANDO_APROVACAO_CONSEPEX, 'Em análise do CONSEPEX'],
        [AGUARDANDO_APROVACAO_CONSUP, 'Em análise do CONSUP'],
        [APROVADO, 'Aprovado'],
        [REPROVADO, 'Reprovado'],
        [FINALIZADO, 'Finalizado'],
        [ARQUIVADO, 'Arquivado'],
    ]

    SITUACOES_TERMINAIS = [
        REPROVADO,
        FINALIZADO,
        ARQUIVADO,
    ]

    DECISAO_APROVAR = '1'
    DECISAO_APROVAR_RESSALVA = '2'
    DECISAO_SOLICITAR_CORRECAO = '3'
    DECISAO_REPROVAR = '4'

    DECISAO_CHOICES = [
        [DECISAO_APROVAR, 'Aprovar'],
        # desabilitando temporariamente a aprovação com ressalva
        # [DECISAO_APROVAR_RESSALVA, 'Aprovar com ressalva'],
        [DECISAO_SOLICITAR_CORRECAO, 'Solicitar correção'],
        [DECISAO_REPROVAR, 'Reprovar'],
    ]

    DECISAO_INFO_CHOICES = [
        [DECISAO_APROVAR, 'O PAFC avançará para a próxima etapa.'],
        [DECISAO_APROVAR_RESSALVA, 'O PAFC retornará para a etapa de elaboração e, após conclusão da validação, NÃO voltará para esta etapa.'],
        [DECISAO_SOLICITAR_CORRECAO, 'O PAFC retornará para a etapa de elaboração e, após conclusão da validação, voltará para análise desta etapa.'],
        [DECISAO_REPROVAR, 'O PAFC será finalizado com a situação Reprovado.'],
    ]

    # Dados gerais
    nome_curso = models.CharFieldPlus('Nome do Curso')
    modelo = models.ForeignKeyPlus(ModeloPAFC, verbose_name='Modelo')
    ppc = models.ForeignKeyPlus('ppc.ProjetoPedagogicoCurso', verbose_name='PPC', null=True, blank=False)
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor')
    situacao = models.IntegerField(verbose_name='Situação', choices=SITUACAO_CHOICES, default=EM_SOLICITACAO)

    # Dados do curso
    numero_vagas_curso = models.PositiveIntegerFieldPlus('Total de vagas ofertadas anualmente', null=True, blank=False)
    ano_letivo_primeira_oferta = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano letivo da primeira oferta', null=True, blank=True)
    periodo_letivo_primeira_oferta = models.PositiveIntegerField(
        'Período letivo da primeira oferta', choices=PERIODO_LETIVO_CHOICES, null=True, blank=True
    )
    curso_ja_ofertado_campus = models.BooleanField('Curso já ofertado no campus?', default=False)
    curso = models.ForeignKeyPlus('edu.CursoCampus', verbose_name='Curso', blank=True, null=True)
    previsto_pdi = models.BooleanField('Curso previsto no PDI?', default=False)
    justificativa_ausencia_pdi = models.TextField(
        'Justificativa de Ausência no PDI', null=True, blank=True, help_text='Obrigatório caso o PAFC não esteja previsto no PDI.'
    )

    # gestão
    reitor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Reitor', related_name='pafcs_reitor')
    pro_reitor_ensino = models.ForeignKeyPlus('rh.Servidor', verbose_name='Pro-Reitor de Ensino', related_name='pafcs_proen')
    pro_reitor_pesquisa = models.ForeignKeyPlus('rh.Servidor', verbose_name='Pro-Reitor de Pesquisa', related_name='pafcs_propi', null=True)
    pro_reitor_extensao = models.ForeignKeyPlus('rh.Servidor', verbose_name='Pro-Reitor de Extensão', related_name='pafcs_proex', null=True)
    diretor_geral = models.ForeignKeyPlus('rh.Servidor', verbose_name='Diretor Geral', related_name='pafcs_dg')
    diretor_academico = models.ForeignKeyPlus('rh.Servidor', verbose_name='Diretor Acadêmico', related_name='pafcs_da')
    coordenador_pesquisa = models.ForeignKeyPlus('rh.Servidor', verbose_name='Coordenador de Pesquisa', related_name='pafcs_coord_pesq', null=True)
    coordenador_extensao = models.ForeignKeyPlus('rh.Servidor', verbose_name='Coordenador de Extensão', related_name='pafcs_coord_ext', null=True)
    coordenador_curso = models.ForeignKeyPlus('rh.Servidor', verbose_name='Coordenador do Curso', related_name='pafcs_coord', null=True)

    # documentos
    ata_reuniao_codiac = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto',
        verbose_name='Ata da reunião do CODIAC',
        null=True,
        blank=True,
        help_text='Obrigatória nos casos de primeira oferta do curso no campus: Incluir ata da reunião do CODIAC que '
        'ratifica a solicitação de autorização de funcionamento do curso.',
    )
    portaria_comissao_elaboracao_vigente = models.ForeignKeyPlus(
        'pafc.DocumentoHibrido',
        verbose_name='Portaria da Comissão de Elaboração',
        related_name='pafcs_como_portaria_comissao_elaboracao',
        null=True,
        on_delete=models.SET_NULL,
    )

    relatorio_analise_preliminar = models.FileFieldPlus(
        verbose_name='Relatório da Análise Preliminar', upload_to='pafc/relatorios_analise_preliminar/', null=True, blank=True
    )
    data_upload_relatorio_analise_preliminar = models.DateTimeFieldPlus('Data do upload do Relatório da Análise Preliminar', null=True, blank=True)
    relatorio_analise_preliminar_cadastrado_por = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Cadastrador da Relatório da Análise Preliminar',
        null=True,
        blank=True,
        related_name='cadastradores_rel_ap_pafc',
    )

    ficha_revisao_tecnica = models.FileFieldPlus(
        verbose_name='Ficha da Revisão Técnica', upload_to='pafc/fichas_revisao_tecnica/', null=True, blank=True
    )
    data_upload_ficha_revisao_tecnica = models.DateTimeFieldPlus('Data do upload da Ficha da Revisão Técnica', null=True, blank=True)
    ficha_revisao_tecnica_cadastrada_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Cadastrador da Ficha de Revisão Técnica', null=True, blank=True, related_name='cadastradores_ficha_revtec_pafc'
    )

    comprovante_aprovacao_pomc = models.ForeignKeyPlus(
        'pafc.DocumentoHibrido',
        verbose_name='Comprovante de aprovação do POMC',
        related_name='pafcs_como_comprovante_aprovacao_pomc',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )
    cadastrador_comprovante_aprovacao_pomc = models.ForeignKeyPlus(
        'comum.Vinculo',
        verbose_name='Cadastrador do comprovante de aprovação do POMC',
        null=True,
        blank=True,
        related_name='cadastradores_comprovante_aprovpomc_pafc',
        on_delete=models.SET_NULL,
    )
    data_cadastro_comprovante_aprovacao_pomc = models.DateTimeFieldPlus('Data de cadastro do comprovante de aprovação do POMC', null=True, blank=True)

    # infraestrutura
    tecnicos_administrativos = models.ManyToManyFieldPlus(
        'rh.Servidor', verbose_name='Técnicos Administrativos', blank=True, related_name='pafcs_tae'
    )
    justificativa_indisponibilidade_tecnicos_administrativos = models.TextField(
        'Justificativa de indisponibilidade de Técnicos Administrativos', null=True, blank=True
    )
    salas = models.ManyToManyFieldPlus('comum.Sala', verbose_name='Laboratórios', blank=True, related_name='pafcs')
    justificativa_indisponibilidade_laboratorios = models.TextField('Justificativa de indisponibilidade de Laboratórios', null=True, blank=True)

    # EaD
    qtd_prevista_tutores = models.PositiveIntegerFieldPlus('Quantidade prevista de tutores/mediadores', null=True)
    justificativa_indisponibilidade_tutores = models.TextField(
        verbose_name='Justificativa de indisponibilidade de tutores/mediadores',
        null=True,
        blank=True,
        help_text='Obrigatória se o curso não previr tutores/mediadores ou a lista de tutores/mediadores não atingir a quantidade prevista.',
    )

    # proreitoria
    proreitoria = models.ForeignKeyPlus(
        'ppc.ProReitoria',
        verbose_name='Pró-Reitoria',
        null=True,
        blank=False,
        help_text='Informe a Pró-Reitoria que irá continuar a análise deste PAFC.',
    )
    reprovado_proreitoria = models.BooleanField(
        'Reprovado', default=False, help_text='Marque esta opção para reprovar o PAFC. Ele será reprovado após finalização do parecer emitido.'
    )
    ad_referendum = models.BooleanField('Ad Referendum', default=False, help_text='Sugere que a tramitação nos conselhos seja Ad Referendum.')
    pular_camara = models.BooleanField(
        'Avançar para CONSEPEX',
        default=False,
        help_text='Caso esta opção seja marcada, o sistema irá pular a análise da câmara e avançará diretamente para a análise do CONSEPEX.',
    )

    # camara
    camara = models.ForeignKeyPlus(
        'ppc.Camara', verbose_name='Câmara', null=True, blank=True, help_text='Informe a Câmara que irá continuar a análise deste PAFC.'
    )
    data_convocacao_camara = models.DateFieldPlus('Data da reunião', null=True, blank=True)
    decisao_camara = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)

    # consepex
    data_convocacao_consepex = models.DateFieldPlus('Data da reunião', null=True, blank=True)
    decisao_consepex = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)
    justificativa_decisao_consepex = models.TextField('Justificativa da decisão do Consepex', null=True, blank=False)
    consepex_inexistente = models.BooleanField(
        'CONSEPEX não instituído',
        default=False,
        help_text='Marque esta opção caso o CONSEPEX da instituição não esteja formado no momento da análise deste PAFC.',
    )

    # consup
    data_convocacao_consup = models.DateFieldPlus('Data da reunião', null=True, blank=False)
    decisao_consup = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=False, choices=DECISAO_CHOICES)
    justificativa_decisao_consup = models.TextField('Justificativa da decisão do Consup', null=True, blank=False)

    # aprovação
    data_aprovacao = models.DateFieldPlus('Data da aprovação no CONSUP', null=True, blank=True)

    # colaboradores (pessoal que contribuiu, mas não pertence nem à comissão de elaboração, nem às equipes de revisores)
    colaboradores = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Colaboradores', blank=True, related_name='pafcs_colaborador')

    # registra, para trâmites de adequação, a data em que o curso foi atualizado
    data_atualizacao_curso = models.DateTimeFieldPlus('Data da atualização do curso', null=True, blank=True)

    class Meta:
        verbose_name = 'PAFC'
        verbose_name_plural = 'PAFCs'

    def __str__(self):
        return f'{self.id} - {self.nome_curso} ({normalizar_nome_proprio(self.setor.uo.nome)})'

    def save(self, *args, **kwargs):
        pk = self.pk
        if pk is None:
            vinculo_diac = self.diretor_academico.get_vinculo()
            diac = Diretoria.objects.filter(
                Q(tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA), Q(diretor_academico=vinculo_diac) | Q(diretor_academico_exercicio=vinculo_diac)
            ).first()
            self.setor = diac.setor
        self.nome_curso = self.ppc.nome_curso
        if self.curso:
            self.ano_letivo_primeira_oferta = self.curso.ano_letivo
            self.periodo_letivo_primeira_oferta = self.curso.periodo_letivo
        super().save(*args, **kwargs)
        if pk is None:
            MovimentacaoPAFC.registrar_movimentacao(None, self)

    def get_absolute_url(self):
        return f'/pafc/pafc/{self.id}/'

    @cached_property
    def diretoria(self):
        return Diretoria.objects.filter(tipo=Diretoria.TIPO_DIRETORIA_ACADEMICA, setor=self.setor).first()

    # ---------------------------------------
    # CONSULTAS RELATIVAS A DADOS DO PAFC
    # ---------------------------------------
    def is_pafc_criacao(self):
        return not self.curso_ja_ofertado_campus

    def is_pafc_adequacao(self):
        return not self.is_pafc_criacao()

    def get_tipo_tramitacao(self):
        return 'Criação' if self.is_pafc_criacao() else 'Adequação'

    def aprovacao_eh_no_consup(self):
        return self.is_pafc_criacao() or self.consepex_inexistente

    def get_modalidade(self):
        return self.ppc.modelo_ppc.modalidade

    def get_secoes(self):
        return self.secaopafc_set.order_by('ordem_exibicao')

    def get_conteudos(self):
        return ConteudoPAFC.objects.filter(secao__pafc=self).order_by('secao__ordem_exibicao', 'ordem_exibicao')

    def get_nome_campus_normalizado(self):
        return normalizar_nome_proprio(self.setor.uo.nome)

    def get_endereco_campus_normalizado(self):
        campus = self.setor.uo
        return f'{campus.endereco}, CEP {campus.cep}, {normalizar_nome_proprio(campus.municipio.nome)} ({campus.municipio.uf})'

    def get_texto_inicio_oferta(self):
        return f'{self.ano_letivo_primeira_oferta}.{self.periodo_letivo_primeira_oferta}' if self.ano_letivo_primeira_oferta else '-'

    def get_texto_resolucao_ppc_criacao(self):
        doc_ad_referendum, doc_final = self.ppc.get_documentos_aprovadores()

        if doc_final:
            doc = doc_final.get_documento()
            data_aprovacao = self.ppc.data_convocacao_consup if self.ppc.possui_aprovacao_consup() else self.ppc.data_convocacao_consepex
            if data_aprovacao:
                descricao_ato = f'{doc} de {data_aprovacao.strftime("%d/%m/%Y")}'
            else:
                descricao_ato = f'{doc}'
        else:
            tipo_documento = 'resolução' if self.ppc.possui_aprovacao_consup() else 'deliberação'
            descricao_ato = f'[{tipo_documento} a emitir]'

        if doc_ad_referendum:
            doc = doc_ad_referendum.get_documento()
            descricao_ato = f'{doc} de {doc.get_data_finalizacao().strftime("%d/%m/%Y")} Ad Referendum, homologada pela {descricao_ato}'

        adequado_por = ''
        if self.ppc.is_tramite_criacao() or not self.ppc.resolucao_criacao:
            ato_aprovacao = descricao_ato
        else:
            ato_aprovacao = self.ppc.resolucao_criacao
            adequado_por = f', e adequado pela {descricao_ato}'

        return f'{ato_aprovacao}{adequado_por}'

    def get_documentos_aprovadores(self):
        """
        Retorna uma tupla com os documentos que aprovaram o PAFC, no formato (<documento ad referendum>, <documento final>).
        """
        tipo_documento_aprovador = DocumentoHibrido.RESOLUCAO if self.aprovacao_eh_no_consup() else DocumentoHibrido.DELIBERACAO

        documentos_aprovadores = self.documentos_emitidos.order_by('-data_emissao').filter(
            documento__tipo=tipo_documento_aprovador,
            documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO,
            decisao__in=[PAFC.DECISAO_APROVAR, PAFC.DECISAO_APROVAR_RESSALVA],
        )
        doc_ad_referendum = documentos_aprovadores.filter(ad_referendum=True).first()
        doc_final = documentos_aprovadores.filter(ad_referendum=False).first()

        return doc_ad_referendum, doc_final

    def get_texto_aprovacoes(self):
        tipo_documento_aprovador = 'resolução' if self.aprovacao_eh_no_consup() else 'deliberação'

        doc_aprovador_ad_referendum, doc_aprovador_final = self.get_documentos_aprovadores()
        # Documento emitido em tramitação normal
        if doc_aprovador_final:
            doc = doc_aprovador_final.get_documento()
            data_aprovacao = self.data_convocacao_consup if self.aprovacao_eh_no_consup() else self.data_convocacao_consepex
            descricao_doc_aprovador_final = f'{doc}, de {data_aprovacao.strftime("%d/%m/%Y")}'
        else:
            descricao_doc_aprovador_final = f'[{tipo_documento_aprovador} a emitir]'

        # Obtendo descrição do documento emitido em tramitação ad referendum, se houver
        descricao_doc_aprovador_ad_referendum = ''
        if doc_aprovador_ad_referendum:
            doc = doc_aprovador_ad_referendum.get_documento()
            descricao_doc_aprovador_ad_referendum = (
                f'{doc}, de {doc.get_data_finalizacao().strftime("%d/%m/%Y")}, Ad Referendum, homologada pela {descricao_doc_aprovador_final}'
            )

        if self.is_pafc_criacao():
            aprovacao = descricao_doc_aprovador_ad_referendum or descricao_doc_aprovador_final
            adequacao = ''
        else:
            ato = AtoRegulatorioCurso.objects.filter(curso=self.curso, tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO, ad_referendum=False).first()
            aprovacao = (
                f'{ato.tipo_documento.upper()} N° {ato.get_numero_com_orgao()}, de {ato.data.strftime("%d/%m/%Y")}'
                if ato
                else '[ato regulatório não cadastrado]'
            )
            adequacao = descricao_doc_aprovador_ad_referendum or descricao_doc_aprovador_final

        return f'Projeto aprovado pela {aprovacao}{f", e adequado pela {adequacao}" if adequacao else ""}.'

    def get_documentos_para_emissao(self, user):
        documentos = []

        if self.pode_emitir_portaria_comissao_elaboracao(user) and self.pode_ter_portaria_comissao_elaboracao_emitida():
            documentos.append('Portaria da Comissão de Elaboração')

        if self.pode_emitir_parecer_validacao(user) or self.pode_emitir_parecer_proreitoria(user) or self.pode_emitir_parecer_camara(user):
            documentos.append('Parecer')

        deliberacao_regular, deliberacao_ad_referendum, deliberacao_homologacao = self.pode_emitir_deliberacao(user)
        if deliberacao_regular:
            documentos.append('Deliberação')
        if deliberacao_ad_referendum:
            documentos.append('Deliberação Ad Referendum')
        if deliberacao_homologacao:
            documentos.append('Deliberação de homologação')

        resolucao_regular, resolucao_ad_referendum, resolucao_homologacao = self.pode_emitir_resolucao(user)
        if resolucao_regular:
            documentos.append('Resolução')
        if resolucao_ad_referendum:
            documentos.append('Resolução Ad Referendum')
        if resolucao_homologacao:
            documentos.append('Resolução de homologação')

        if self.pode_emitir_despacho_consepex(user):
            documentos.append('Despacho')

        return documentos

    @cached_property
    def is_servidores_definidos(self):
        return (
            self.coordenador_curso is not None
            and (self.tecnicos_administrativos.exists() or self.justificativa_indisponibilidade_tecnicos_administrativos)
            and self.disciplinas.exists()
            and not self.existe_disciplina_sem_docente()
            and not ComentarioGeralPAFC.pafc_possui_comentario_geral(self, resolvido=False, escopo=ComentarioGeralPAFC.ESCOPO_SERVIDORES)
        )

    @cached_property
    def is_instalacoes_definidas(self):
        return (self.salas.exists() or self.justificativa_indisponibilidade_laboratorios) and not ComentarioGeralPAFC.pafc_possui_comentario_geral(
            self, resolvido=False, escopo=ComentarioGeralPAFC.ESCOPO_INSTALACOES
        )

    def requer_cadastro_de_tutores(self):
        return self.modelo.possui_ch_ead()

    def requer_cadastro_de_polos(self):
        return self.modelo.eh_versao_totalmente_ead()

    @cached_property
    def pendencias_cadastro_tutores(self):
        pendencias = []
        qtd_tutores = self.tutores_ead.count()
        if self.qtd_prevista_tutores is None:
            pendencias.append('A quantidade prevista de tutores/mediadores não foi informada.')
        else:
            if qtd_tutores > self.qtd_prevista_tutores:
                pendencias.append('A quantidade de tutores/mediadores excede a quantidade prevista.')
            if self.qtd_prevista_tutores == 0 and not self.justificativa_indisponibilidade_tutores:
                pendencias.append('A quantidade prevista é nula, mas não foi informada uma justificativa.')
            if qtd_tutores < self.qtd_prevista_tutores and not self.justificativa_indisponibilidade_tutores:
                pendencias.append('A quantidade de tutores/mediadores é inferior à quantidade prevista. Justifique ou cadastre mais pessoas.')
        return pendencias

    @cached_property
    def is_tutores_definidos(self):
        return not self.requer_cadastro_de_tutores() or not self.pendencias_cadastro_tutores

    @cached_property
    def polo_ead_sede(self):
        return self.polos_ead.filter(tipo=PoloEadPAFC.TIPO_SEDE).first()

    @cached_property
    def vagas_ofertadas_pelos_polos_ead(self):
        return self.polos_ead.aggregate(Sum('vagas_ofertadas'))['vagas_ofertadas__sum'] or 0

    @cached_property
    def pendencias_no_cadastro_de_polos_ead(self):
        pendencias = []
        if not self.polo_ead_sede:
            pendencias.append('Unidade sede não informada.')
        if self.vagas_ofertadas_pelos_polos_ead != self.numero_vagas_curso:
            pendencias.append('A soma de vagas dos polos não corresponde ao total de vagas do curso.')
        return pendencias

    @cached_property
    def is_infraestrutura_ead_definida(self):
        return (
            self.is_tutores_definidos
            and not (self.requer_cadastro_de_polos() and self.pendencias_no_cadastro_de_polos_ead)
            and not ComentarioGeralPAFC.pafc_possui_comentario_geral(self, resolvido=False, escopo=ComentarioGeralPAFC.ESCOPO_INFRAESTRUTURA_EAD)
        )

    @cached_property
    def is_matrizes_definidas(self):
        return self.matrizpafc_set.exists() and not ComentarioGeralPAFC.pafc_possui_comentario_geral(
            self, resolvido=False, escopo=ComentarioGeralPAFC.ESCOPO_MATRIZES
        )

    @cached_property
    def is_pomc_definido(self):
        return (
            not self.pomc_eh_obrigatorio
            and not self.implementa_pomc
            or (
                self.implementa_pomc
                and self.comprovante_aprovacao_pomc is not None
                and not self.get_planos_disciplina_pomc()
                .filter(plano_disciplina_modificado__situacao=PlanoDisciplinaModificado.EM_ELABORACAO)
                .exists()
                and not RevisaoPlanoDisciplinaModificado.possui_revisoes_nao_resolvidas(self)
            )
        )

    @cached_property
    def existem_matrizes_para_vincular(self):
        return self.matrizpafc_set.count() < self.ppc.matrizppc_set.filter(situacao_matriz=MatrizPPC.MATRIZ_APROVADA).count()

    def get_planos_disciplina_ppc(self):
        """
        Retorna a queryset dos planos de disciplina do PPC (PlanoDisciplinaPPC) considerando apenas as matrizes vinculadas ao PAFC.
        """
        return PlanoDisciplinaPPC.objects.filter(matriz_ppc__in=self.matrizpafc_set.values_list('matriz_ppc', flat=True))

    @cached_property
    def nomes_dos_topicos_especificos(self):
        return set(
            self.get_planos_disciplina_ppc()
            .filter(plano_disciplina__topico_especifico=True)
            .values_list('plano_disciplina__nome_disciplina', flat=True)
        )

    def get_bibliografias_dos_topicos_especificos(self):
        regex_nomes_topicos_especificos = r'(^|\|)(' + r'|'.join(self.nomes_dos_topicos_especificos) + r')(\||$)'
        return self.bibliografiapafc_set.filter(disciplinas__iregex=regex_nomes_topicos_especificos)

    def get_planos_disciplina_pomc(self):
        return PlanoDisciplinaPOMC.objects.filter(plano_disciplina_modificado__pafc=self)

    def get_plano_disciplina_pomc(self, id_componente, id_matriz):
        result = None
        if id_componente and id_matriz:
            result = (
                self.get_planos_disciplina_pomc()
                .filter(
                    plano_disciplina_ppc__matriz_ppc__matriz_id=id_matriz,
                    plano_disciplina_modificado__plano_referencia__componente_id=id_componente,
                )
                .first()
            )
        return result

    @cached_property
    def is_bibliografia_definida(self):
        return (
            self.bibliografiapafc_set.exists()
            and BibliografiaPAFC.quantitativos_foram_informados(self)
            and not ComentarioGeralPAFC.pafc_possui_comentario_geral(self, resolvido=False, escopo=ComentarioGeralPAFC.ESCOPO_BIBLIOGRAFIA)
        )

    def existe_disciplina_sem_docente(self, considerar_justificativa_indisponibilidade=True):
        qs = self.disciplinas.filter(docentes=None)
        if considerar_justificativa_indisponibilidade:
            qs = qs.filter(justificativa_indisponibilidade_docentes__isnull=True)
        return qs.exists()

    def get_pendencias(self, user=None):
        result = []
        grupos = []

        is_elaborador = self.is_elaborador(user)
        is_revisor = self.is_revisor_tecnico(user)
        is_validador = self.is_validador(user)
        tem_permissao_edicao = self.tem_permissao_edicao(user)

        is_proreitor = user and self.proreitoria and user.get_vinculo().setor_id == self.proreitoria.setor_id
        is_coordenador_camara = self.is_coordenador_camara(user)
        is_secretario_camara = self.is_secretario_camara(user)
        is_presidente_conselho = ProjetoPedagogicoCurso.is_presidente_conselho(user)
        is_secretario_conselho = ProjetoPedagogicoCurso.is_secretario_conselho(user)
        is_diretor_academico = self.is_diretor_academico(user)

        # PENDÊNCIAS DA SOLICITAÇÃO
        if self.em_etapas_de_solicitacao():
            # comissão de elaboração
            if not self.membrocomissaopafc_set.exists():
                result.append(('Cadastro da comissão de elaboração.', 'equipe#comissao_elaboracao'))

            # portaria da comissão de elaboração
            if self.portaria_comissao_elaboracao_vigente is None:
                url = None
                if self.situacao == PAFC.EM_SOLICITACAO:
                    if is_diretor_academico and self.pode_ter_portaria_comissao_elaboracao_solicitada():
                        url = f'{reverse("pafc", args=(self.pk,))}?acao=solicitar_portaria_comissao_elaboracao'
                    result.append(('Solicitação da portaria da comissão de elaboração.', url))
                else:
                    if self.pode_emitir_portaria_comissao_elaboracao(user) and self.pode_ter_portaria_comissao_elaboracao_emitida():
                        url = f'{reverse("pafc", args=(self.pk,))}?tab=documentos'
                    result.append(('Emissão da portaria da comissão de elaboração.', url))
            elif not self.portaria_comissao_elaboracao_vigente.estah_finalizado():
                result.append(('Finalização da portaria da comissão de elaboração.', self.portaria_comissao_elaboracao_vigente.get_url_documento()))

        if result:
            grupos.append(('Pendências da solicitação', result))
            result = []

        # PENDÊNCIAS DA EQUIPE
        if self.em_etapas_de_solicitacao() or self.em_elaboracao() or self.em_revisao_tecnica() or self.em_validacao():
            # revisores
            if not self.revisortecnicopafc_set.exists():
                result.append(('Cadastro dos revisores técnicos.', 'equipe#revisores_tecnicos'))
            if not self.validadorpafc_set.exists():
                result.append(('Cadastro dos validadores.', 'equipe#validadores'))

        if result:
            grupos.append(('Pendências da equipe', result))
            result = []

        # PENDÊNCIAS DA ELABORAÇÃO
        if self.em_elaboracao() and (is_elaborador or tem_permissao_edicao):
            # servidores
            if self.coordenador_curso is None:
                result.append(('Definição do coordenador de curso.', 'servidores#abas'))
            if not self.tecnicos_administrativos.exists() and not self.justificativa_indisponibilidade_tecnicos_administrativos:
                result.append(('Definição dos servidores técnico-administrativos.', 'servidores#abas'))
            if self.existe_disciplina_sem_docente():
                for disciplina in self.disciplinas.all():
                    if not disciplina.docentes.exists():
                        result.append(
                            (
                                f'Informar docentes  para a disciplina "{disciplina.plano_disciplina.nome_disciplina}".',
                                f'servidores#disciplina_{disciplina.id}',
                            )
                        )

            if ComentarioGeralPAFC.pafc_possui_comentario_geral(self, escopo=ComentarioGeralPAFC.ESCOPO_SERVIDORES, resolvido=False):
                result.append(('Resolver observações da revisão/validação na aba "Servidores".', 'servidores#abas'))

            # instalações
            if not self.salas.exists() and not self.justificativa_indisponibilidade_laboratorios:
                result.append(('Definição dos laboratorios para a execução do curso.', 'instalacoes#abas'))
            if ComentarioGeralPAFC.pafc_possui_comentario_geral(self, escopo=ComentarioGeralPAFC.ESCOPO_INSTALACOES, resolvido=False):
                result.append(('Resolver observações da revisão/validação na aba "Instalações e Equipamentos".', 'instalacoes#abas'))
            # infraestrutura ead
            if self.modelo.possui_ch_ead():
                if self.requer_cadastro_de_polos() and self.pendencias_no_cadastro_de_polos_ead:
                    result.append(('Definição dos polos EaD.', 'infraestrutura_ead#polos'))
                if not self.is_tutores_definidos:
                    result.append(('Definição dos tutores/mediadores EaD.', 'infraestrutura_ead#tutores'))
                if ComentarioGeralPAFC.pafc_possui_comentario_geral(self, escopo=ComentarioGeralPAFC.ESCOPO_INFRAESTRUTURA_EAD, resolvido=False):
                    result.append(('Resolver observações da revisão/validação na aba "Infraestrutura EaD".', 'infraestrutura_ead#abas'))
            # matrizes
            if not self.matrizpafc_set.exists():
                result.append(('Definição das matrizes do curso.', 'matrizes#abas'))
            if not self.is_pomc_definido:
                result.append((f'Concluir elaboração do POMC{" (obrigatório para este PAFC)" if self.pomc_eh_obrigatorio else ""}.', 'matrizes#pomc'))
            if self.implementa_pomc:
                if self.comprovante_aprovacao_pomc is None:
                    result.append(('Cadastrar comprovante de aprovação do POMC.', 'matrizes#pomc'))
                planos_em_elaboracao = self.planos_disciplina_modificados.filter(situacao=PlanoDisciplinaModificado.EM_ELABORACAO)
                for plano in planos_em_elaboracao:
                    result.append((f'Concluir elaboração do {plano}.', 'matrizes#pomc'))
            elif self.pomc_eh_obrigatorio:
                result.append(('Implementar POMC (obrigatório para o curso).', 'matrizes#pomc'))
            if ComentarioGeralPAFC.pafc_possui_comentario_geral(self, escopo=ComentarioGeralPAFC.ESCOPO_MATRIZES, resolvido=False):
                result.append(('Resolver observações da revisão/validação na aba "Matrizes".', 'matrizes#abas'))
            # bibliografia
            if not self.is_bibliografia_definida or not BibliografiaPAFC.quantitativos_foram_informados(
                self, tipo_bibliografia=BibliografiaPAFC.BIBLIOGRAFIA_BASICA
            ):
                result.append(('Definição dos quantitativos da bibliografia básica.', 'bibliografia#basica'))
            if not self.is_bibliografia_definida or not BibliografiaPAFC.quantitativos_foram_informados(
                self, tipo_bibliografia=BibliografiaPAFC.BIBLIOGRAFIA_COMPLEMENTAR
            ):
                result.append(('Definição dos quantitativos da bibliografia complementar.', 'bibliografia#complementar'))
            if ComentarioGeralPAFC.pafc_possui_comentario_geral(self, escopo=ComentarioGeralPAFC.ESCOPO_BIBLIOGRAFIA, resolvido=False):
                result.append(('Resolver observações da revisão/validação na aba "Bibliografia".', 'bibliografia#abas'))
            # conteúdo
            for secao in self.get_secoes():
                possui_conteudos_elaboraveis = secao.conteudopafc_set.filter(
                    editavel=True, situacao__in=[ConteudoPAFC.DISPONIVEL_PARA_EDICAO, ConteudoPAFC.EM_EDICAO]
                ).exists()
                veio_da_revisao = ComentarioRevisao.secao_possui_revisao(secao=secao, tipos=ComentarioRevisao.REVISAO_TECNICA)
                veio_da_validacao = ComentarioRevisao.secao_possui_revisao(secao=secao, tipos=ComentarioRevisao.VALIDACAO)
                if possui_conteudos_elaboraveis:
                    if veio_da_revisao:
                        result.append((f'Existe conteúdo da seção "{secao.titulo}" que não foi enviado para revisão.', f'conteudo#secao_{secao.id}'))
                    elif veio_da_validacao:
                        result.append(
                            (f'Existe conteúdo da seção "{secao.titulo}" que não foi enviado para validação.', f'conteudo#secao_{secao.id}')
                        )
                    else:
                        result.append(
                            (f'Existe conteúdo da seção "{secao.titulo}" que não foi enviado para revisão técnica.', f'conteudo#secao_{secao.id}')
                        )
                if ComentarioRevisao.secao_possui_revisao(secao, resolvido=False):
                    result.append((f'Resolver observações da revisão/validação em conteúdo da seção "{secao.titulo}".', f'conteudo#secao_{secao.id}'))

        if self.pode_ser_editado() and tem_permissao_edicao:
            if not self.numero_vagas_curso:
                result.append(('Editar dados do curso para informar número de vagas.', 'dados_gerais#dados_curso'))
            if self.is_pafc_criacao() and not self.ano_letivo_primeira_oferta:
                result.append(('Editar dados do curso para informar período letivo da primeira oferta.', 'dados_gerais#dados_curso'))

        if result:
            grupos.append(('Pendências da elaboração', result))
            result = []

        # PENDÊNCIAS DA REVISÃO
        # análise preliminar
        if self.em_analise_preliminar() and is_validador:
            if not self.relatorio_analise_preliminar:
                result.append(('O Relatório da Análise Preliminar não foi anexado ainda.', 'documentos#abas'))
            if not self.possui_comentarios_analise_preliminar:
                result.append(('O PAFC precisa ser enviado para revisão.', 'conteudo#abas'))
            if self.implementa_pomc:
                planos_em_analise_preliminar = self.planos_disciplina_modificados.filter(situacao=PlanoDisciplinaModificado.EM_ANALISE_PRELIMINAR)
                for plano in planos_em_analise_preliminar:
                    result.append((f'Concluir análise preliminar do {plano} (opcional).', 'matrizes#pomc'))

        # revisão técnica
        if self.em_revisao_tecnica() and is_revisor:
            for secao in self.get_secoes():
                if secao.conteudopafc_set.filter(editavel=True, situacao__in=[ConteudoPAFC.PRONTO_PARA_REVISAR, ConteudoPAFC.EM_REVISAO]).exists():
                    result.append((f'Existe conteúdo da seção "{secao.titulo}" pendente de revisão técnica.', f'conteudo#secao_{secao.id}'))
            if self.implementa_pomc:
                planos_em_revisao = self.planos_disciplina_modificados.filter(situacao=PlanoDisciplinaModificado.EM_REVISAO_TECNICA)
                for plano in planos_em_revisao:
                    result.append((f'Concluir revisão do {plano}.', 'matrizes#pomc'))
            if not self.ficha_revisao_tecnica:
                result.append(('A Ficha de Revisão Técnica não foi anexada ainda.', 'documentos#abas'))
            if not ConteudoPAFC.objects.filter(secao__pafc=self, editavel=True).exclude(situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR).exists():
                result.append(('O PAFC precisa ser enviado para validação.', 'conteudo#abas'))

        # validação
        if self.em_validacao() and is_validador:
            for secao in self.get_secoes():
                if secao.conteudopafc_set.filter(editavel=True, situacao__in=[ConteudoPAFC.PRONTO_PARA_VALIDAR, ConteudoPAFC.EM_VALIDACAO]).exists():
                    result.append((f'Existe conteúdo da seção "{secao.titulo}" pendente de validação.', f'conteudo#secao_{secao.id}'))
            if self.implementa_pomc:
                planos_em_validacao = self.planos_disciplina_modificados.filter(situacao=PlanoDisciplinaModificado.EM_VALIDACAO)
                for plano in planos_em_validacao:
                    result.append((f'Concluir validação do {plano}.', 'matrizes#pomc'))
            if not self.parecer_validacao_ja_foi_emitido:
                result.append(('Emitir parecer da validação.', ''))
            else:
                result.append(('Finalizar parecer da validação.', 'documentos#abas'))

        if result:
            grupos.append(('Pendências da revisão', result))
            result = []

        # PENDÊNCIAS DA PRÓ-REITORIA
        if self.situacao == PAFC.EM_ANALISE_PROREITORIA and is_proreitor:
            qs_documentos = self.documentos_emitidos.filter(situacao_pafc=self.situacao)
            if not qs_documentos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists():
                result.append(('Emitir parecer da Pró-Reitoria.', ''))
            else:
                result.append(('Finalizar parecer da Pró-Reitoria.', 'documentos#abas'))

        if result:
            grupos.append(('Pendências da Pró-Reitoria', result))
            result = []

        # PENDÊNCIAS DA CÂMARA
        if self.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA and is_coordenador_camara or is_secretario_camara:
            if not self.data_convocacao_camara:
                result.append(('Definir data da reunião Câmara.', 'camara#abas'))
            qs_documentos = self.documentos_emitidos.filter(situacao_pafc=self.situacao)
            if not qs_documentos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists():
                result.append(('Emitir parecer da Câmara.', ''))
            else:
                result.append(('Finalizar parecer da Câmara.', 'documentos#abas'))

        if result:
            grupos.append(('Pendências da Câmara', result))
            result = []

        # PENDÊNCIAS DOS CONSELHOS
        if is_presidente_conselho or is_secretario_conselho:
            # CONSEPEX
            if self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                if not self.data_convocacao_consepex and not self.consepex_inexistente:
                    result.append(('Definir data da reunião do CONSEPEX.', 'consepex#abas'))
                qs_documentos = self.documentos_emitidos.filter(situacao_pafc=self.situacao)
                if not qs_documentos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists():
                    label = 'Emitir despacho do CONSEPEX.' if self.consepex_inexistente else 'Emitir deliberação do CONSEPEX.'
                    result.append((label, ''))
                else:
                    result.append(('Finalizar documento do CONSEPEX.', 'documentos#abas'))

            if result:
                grupos.append(('Pendências do CONSEPEX', result))
                result = []

            # CONSUP
            if self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP:
                if not self.data_convocacao_consup:
                    result.append(('Definir data da reunião do CONSUP.', 'consup#abas'))
                qs_documentos = self.documentos_emitidos.filter(situacao_pafc=self.situacao)
                if not qs_documentos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists():
                    result.append(('Emitir resolução do CONSUP.', ''))
                else:
                    result.append(('Finalizar documento do CONSUP.', 'documentos#abas'))

            if result:
                grupos.append(('Pendências do CONSUP', result))
                result = []

        # FINALIZAÇÃO DO PAFC
        if self.situacao == PAFC.APROVADO:
            # HOMOLOGAÇÃO DAS DELIBERAÇÕES E RESOLUÇÕES AD REFERENDUM
            qs_docs_finalizados = self.documentos_emitidos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO)

            qs_deliberacoes = qs_docs_finalizados.filter(documento__tipo=DocumentoHibrido.DELIBERACAO)
            if qs_deliberacoes.filter(ad_referendum=True).exists() and not qs_deliberacoes.filter(ad_referendum=False).exists():
                result.append(('Emitir deliberação de homologação.', ''))

            qs_resolucao = qs_docs_finalizados.filter(documento__tipo=DocumentoHibrido.RESOLUCAO)
            if qs_resolucao.filter(ad_referendum=True).exists() and not qs_resolucao.filter(ad_referendum=False).exists():
                result.append(('Emitir resolução de homologação.', ''))

            # CRIAÇÃO/ATUALIZAÇÃO DO CURSO
            if self.pode_criar_curso(user) and self.pode_ter_curso_criado():
                result.append(('Confirmar criação do curso.', ''))
            elif self.pode_atualizar_curso(user) and self.pode_ter_curso_atualizado():
                result.append(('Confirmar atualização do curso.', ''))

        if result:
            grupos.append(('Pendências para finalização do PAFC', result))

        return grupos

    def get_progresso(self):
        # Remove situações que devem ser tratadas como internas a outras
        # Ex: AGUARDANDO_PORTARIA passa a ficar dentro de INICIADO
        etapas = list(filter(lambda situacao: situacao[0] not in [PAFC.AGUARDANDO_PORTARIA, PAFC.ARQUIVADO, PAFC.REPROVADO], PAFC.SITUACAO_CHOICES))
        SITUACOES_INICIADO = [PAFC.EM_SOLICITACAO, PAFC.AGUARDANDO_PORTARIA]
        SITUACOES_FINALIZADO = [PAFC.ARQUIVADO, PAFC.REPROVADO, PAFC.FINALIZADO]

        progresso = []
        for situacao, descricao in etapas:
            if situacao == PAFC.EM_SOLICITACAO:
                progresso.append((descricao, self.situacao in SITUACOES_INICIADO))
                continue
            if situacao == PAFC.FINALIZADO:
                progresso.append((descricao, self.situacao in SITUACOES_FINALIZADO))
                continue
            if situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP and self.is_pafc_adequacao():
                continue
            progresso.append((descricao, self.situacao == situacao))
        return progresso

    @cached_property
    def percentual_elaboracao(self):
        qs_conteudos_editaveis = ConteudoPAFC.objects.filter(secao__pafc=self, editavel=True)
        total = qs_conteudos_editaveis.count()
        parcial = qs_conteudos_editaveis.exclude(situacao__in=[ConteudoPAFC.DISPONIVEL_PARA_EDICAO, ConteudoPAFC.EM_EDICAO]).count()
        return int(parcial * 100 / total) if total else 0

    @cached_property
    def is_elaboracao_concluida(self):
        return (
            self.percentual_elaboracao == 100
            and self.ano_letivo_primeira_oferta
            and self.periodo_letivo_primeira_oferta
            and self.numero_vagas_curso
            and self.is_servidores_definidos
            and self.is_instalacoes_definidas
            and self.is_matrizes_definidas
            and self.is_bibliografia_definida
            and self.is_infraestrutura_ead_definida
            and self.is_pomc_definido
            and not self.ha_plano_de_disciplina_em_situacao_pendente()
            # comentários das revisões foram resolvidos
            and not self.possui_comentarios_nao_resolvidos_analise_preliminar
            and not self.possui_comentarios_nao_resolvidos_revisao_tecnica
            and not self.possui_comentarios_nao_resolvidos_validacao
        )

    @cached_property
    def is_analise_preliminar_concluida(self):
        return (
            self.relatorio_analise_preliminar
            and not self.ha_plano_de_disciplina_em_situacao_pendente()
            and not self.possui_comentarios_analise_preliminar
        )

    @cached_property
    def percentual_revisao_tecnica(self):
        qs_conteudos_editaveis = ConteudoPAFC.objects.filter(secao__pafc=self, editavel=True)
        total = qs_conteudos_editaveis.count()
        parcial = qs_conteudos_editaveis.exclude(situacao__in=[ConteudoPAFC.PRONTO_PARA_REVISAR, ConteudoPAFC.EM_REVISAO]).count()
        return int(parcial * 100 / total) if total else 0

    @cached_property
    def is_revisao_tecnica_concluida(self):
        return (
            self.ficha_revisao_tecnica
            and self.percentual_revisao_tecnica == 100
            and not self.ha_plano_de_disciplina_em_situacao_pendente()
            and not self.possui_comentarios_revisao_tecnica
        )

    @cached_property
    def percentual_validacao(self):
        qs_conteudos_editaveis = ConteudoPAFC.objects.filter(secao__pafc=self, editavel=True)
        total = qs_conteudos_editaveis.count()
        parcial = qs_conteudos_editaveis.exclude(situacao__in=[ConteudoPAFC.PRONTO_PARA_VALIDAR, ConteudoPAFC.EM_VALIDACAO]).count()
        return int(parcial * 100 / total) if total else 0

    @cached_property
    def parecer_validacao_ja_foi_emitido(self):
        return self.documentos_emitidos.filter(
            situacao_pafc=PAFC.AGUARDANDO_VALIDACAO, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO
        ).exists()

    def parecer_proreitoria_ja_foi_emitido(self):
        return self.documentos_emitidos.filter(
            situacao_pafc=PAFC.EM_ANALISE_PROREITORIA, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO
        ).exists()

    def parecer_camara_ja_foi_emitido(self):
        return self.documentos_emitidos.filter(
            situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CAMARA, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO
        ).exists()

    def retornou_da_camara_ou_conselhos(self):
        return bool(self.decisao_camara or self.decisao_consepex or self.decisao_consup)

    def ha_plano_de_disciplina_em_situacao_pendente(self):
        if self.em_analise_preliminar():
            # na etapa de análise preliminar, não será obrigatório avaliar os planos de disciplina
            return False
        situacao_pendente = PlanoDisciplinaModificado.get_situacao_inicial_correspondente(self.situacao)
        return self.planos_disciplina_modificados.filter(situacao=situacao_pendente).exists()

    def possui_comentarios_na_situacao(self, situacao, resolvidos=None):
        mapeamento_de_tipos = {
            PAFC.EM_ANALISE_PRELIMINAR: (
                ComentarioRevisao.ANALISE_PRELIMINAR,
                ComentarioGeralPAFC.ANALISE_PRELIMINAR,
                RevisaoPlanoDisciplinaModificado.ANALISE_PRELIMINAR,
            ),
            PAFC.AGUARDANDO_REVISAO_TECNICA: (
                ComentarioRevisao.REVISAO_TECNICA,
                ComentarioGeralPAFC.REVISAO_TECNICA,
                RevisaoPlanoDisciplinaModificado.REVISAO_TECNICA,
            ),
            PAFC.AGUARDANDO_VALIDACAO: (ComentarioRevisao.VALIDACAO, ComentarioGeralPAFC.VALIDACAO, RevisaoPlanoDisciplinaModificado.VALIDACAO),
        }

        tipo_comentario_conteudo, tipo_comentario_geral, tipo_revisao_plano_disciplina = mapeamento_de_tipos.get(situacao, (None, None, None))
        return (
            ComentarioRevisao.pafc_possui_revisao(self, tipos=tipo_comentario_conteudo, resolvido=resolvidos)
            or ComentarioGeralPAFC.pafc_possui_comentario_geral(self, tipos=tipo_comentario_geral, resolvido=resolvidos)
            or RevisaoPlanoDisciplinaModificado.possui_revisoes(self, tipos=tipo_revisao_plano_disciplina, resolvidas=resolvidos)
        )

    @cached_property
    def possui_comentarios_analise_preliminar(self):
        return self.possui_comentarios_na_situacao(PAFC.EM_ANALISE_PRELIMINAR)

    @cached_property
    def possui_comentarios_nao_resolvidos_analise_preliminar(self):
        return self.possui_comentarios_na_situacao(PAFC.EM_ANALISE_PRELIMINAR, resolvidos=False)

    @cached_property
    def possui_comentarios_revisao_tecnica(self):
        return self.possui_comentarios_na_situacao(PAFC.AGUARDANDO_REVISAO_TECNICA)

    @cached_property
    def possui_comentarios_nao_resolvidos_revisao_tecnica(self):
        return self.possui_comentarios_na_situacao(PAFC.AGUARDANDO_REVISAO_TECNICA, resolvidos=False)

    @cached_property
    def possui_comentarios_validacao(self):
        return self.possui_comentarios_na_situacao(PAFC.AGUARDANDO_VALIDACAO)

    @cached_property
    def possui_comentarios_nao_resolvidos_validacao(self):
        return self.possui_comentarios_na_situacao(PAFC.AGUARDANDO_VALIDACAO, resolvidos=False)

    def em_etapas_de_solicitacao(self):
        return self.situacao in [PAFC.EM_SOLICITACAO, PAFC.AGUARDANDO_PORTARIA]

    def situacao_eh_anterior_a_validacao(self):
        return self.situacao in [
            PAFC.EM_SOLICITACAO,
            PAFC.AGUARDANDO_PORTARIA,
            PAFC.EM_ELABORACAO,
            PAFC.EM_ANALISE_PRELIMINAR,
            PAFC.AGUARDANDO_REVISAO_TECNICA,
        ]

    def situacao_eh_anterior_a_aprovacao_camara(self):
        return self.situacao in [
            PAFC.EM_SOLICITACAO,
            PAFC.AGUARDANDO_PORTARIA,
            PAFC.EM_ELABORACAO,
            PAFC.EM_ANALISE_PRELIMINAR,
            PAFC.AGUARDANDO_REVISAO_TECNICA,
            PAFC.AGUARDANDO_VALIDACAO,
            PAFC.EM_ANALISE_PROREITORIA,
        ]

    def em_elaboracao(self):
        return self.situacao == PAFC.EM_ELABORACAO

    def em_analise_preliminar(self):
        return self.situacao == PAFC.EM_ANALISE_PRELIMINAR

    def em_revisao_tecnica(self):
        return self.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA

    def em_validacao(self):
        return self.situacao == PAFC.AGUARDANDO_VALIDACAO

    def em_aprovacao_camara(self):
        return self.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA

    def em_aprovacao_conselhos(self):
        return self.situacao in [PAFC.AGUARDANDO_APROVACAO_CONSEPEX, PAFC.AGUARDANDO_APROVACAO_CONSUP]

    def is_aprovado(self):
        return self.situacao == PAFC.APROVADO

    def is_finalizado(self):
        return self.situacao == PAFC.FINALIZADO

    def pessoa_eh_do_mesmo_campus(self, pessoa):
        campi_pafc = {self.setor.uo_id, self.setor.uo.equivalente_id}
        setores_pessoa = set()
        if isinstance(pessoa, Servidor):
            setores_pessoa = {pessoa.setor, pessoa.setor_lotacao, pessoa.setor_exercicio}
        elif isinstance(pessoa, Vinculo):
            setores_pessoa = {pessoa.setor}
        campi_pessoa = {setor.uo_id for setor in setores_pessoa if setor is not None} | {
            setor.uo.equivalente_id for setor in setores_pessoa if setor is not None
        }

        campi_pafc.discard(None)
        campi_pessoa.discard(None)
        return len(campi_pafc.intersection(campi_pessoa)) > 0

    def laboratorio_eh_do_mesmo_campus(self, sala):
        campi_pafc = {self.setor.uo_id, self.setor.uo.equivalente_id}
        campi_sala = {sala.predio.uo_id, sala.predio.uo.equivalente_id}

        campi_pafc.discard(None)
        campi_sala.discard(None)
        return len(campi_pafc.intersection(campi_sala)) > 0

    @property
    def deliberacoes_finalizadas(self):
        return self.documentos_emitidos.filter(
            documento__tipo=DocumentoHibrido.DELIBERACAO,
            documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO,
        ).order_by('-data_emissao')

    @property
    def resolucoes_finalizadas(self):
        return self.documentos_emitidos.filter(
            documento__tipo=DocumentoHibrido.RESOLUCAO,
            documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO,
        ).order_by('-data_emissao')

    # --------------------------------------------------------
    # CONSULTAS RELATIVAS AO VINCULO ENTRE USUÁRIOS E O PAFC
    # --------------------------------------------------------
    def is_diretor_geral(self, user):
        return (
            self.setor is not None
            and user.has_group_cached('Diretor Geral')
            and Diretoria.objects.filter(setor__uo=self.setor.uo).filter(Q(diretor_geral__user=user) | Q(diretor_geral_exercicio__user=user)).exists()
        )

    def is_diretor_academico(self, user):
        return self.diretoria and eh_diretor_academico(user, self.diretoria)

    def is_elaborador(self, user):
        return self.membrocomissaopafc_set.filter(servidor=user.get_vinculo().id_relacionamento).exists()

    def is_elaborador_coordenador(self, user):
        return self.membrocomissaopafc_set.filter(
            servidor=user.get_vinculo().id_relacionamento, funcao=MembroComissaoPAFC.FUNCAO_COORDENADOR
        ).exists()

    def is_revisor_tecnico(self, user, is_coordenador=None):
        qs_revisor = self.revisortecnicopafc_set.filter(servidor=user.get_vinculo().id_relacionamento)
        if is_coordenador is not None:
            funcao = RevisorTecnicoPAFC.FUNCAO_COORDENADOR if is_coordenador else RevisorTecnicoPAFC.FUNCAO_MEMBRO
            qs_revisor = qs_revisor.filter(funcao=funcao)
        return qs_revisor.exists()

    def is_validador(self, user, is_coordenador=None):
        qs_revisor = self.validadorpafc_set.filter(servidor=user.get_vinculo().id_relacionamento)
        if is_coordenador is not None:
            funcao = ValidadorPAFC.FUNCAO_COORDENADOR if is_coordenador else ValidadorPAFC.FUNCAO_MEMBRO
            qs_revisor = qs_revisor.filter(funcao=funcao)
        return qs_revisor.exists()

    def is_secretario_camara(self, user):
        return self.camara and self.camara.secretario and self.camara.secretario.matricula == user.username

    def is_coordenador_camara(self, user):
        return self.camara and self.camara.coordenador and self.camara.coordenador.matricula == user.username

    @cached_property
    def pomc_eh_obrigatorio(self):
        if self.pode_ter_pomc_implementado:
            return self.is_pafc_criacao() or self.is_pafc_adequacao() and self.curso.ultimo_pafc_com_pomc is None
        return False

    @cached_property
    def implementa_pomc(self):
        return self.get_planos_disciplina_pomc().exists()

    @cached_property
    def pomc_do_curso_completou_ciclo(self):
        """
        Verifica se já se cumpriu um ciclo desde a última alteração do POMC do curso.
        Entende-se por ciclo a duração necessária para o curso ser realizado totalmente.
        """
        if self.is_pafc_criacao():
            return True
        pafcs_do_curso = self.curso.pafc_set.filter(situacao__in=[PAFC.APROVADO, PAFC.FINALIZADO]).exclude(pk=self.pk).order_by('-data_aprovacao')
        for pafc in pafcs_do_curso:
            if pafc.implementa_pomc:
                qtd_maxima_periodos = pafc.matrizpafc_set.aggregate(max_periodos=Max('matriz_ppc__quantidade_periodos')).get('max_periodos')
                periodicidade = pafc.ppc.periodicidade
                if periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
                    meses_por_periodo = 6
                elif periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
                    meses_por_periodo = 12
                else:
                    # Periodicidade livre, por enquanto, não requer conclusão do ciclo. Logo, integralização mínima = 0 meses.
                    meses_por_periodo = 0
                duracao_meses = qtd_maxima_periodos * meses_por_periodo
                if get_datetime_now().date() < pafc.data_aprovacao + relativedelta(months=duracao_meses):
                    return False
        return True

    @cached_property
    def resumo_trabalho_necessario_para_elaborar_pomc(self):
        """
        Detalha o trabalho previsto para a Comissão de Elaboração caso se opte por incluir a atualização do POMC no PAFC.
        """
        resumo = [('Ata da Reunião do Colegiado', ['Anexar ata da Reunião do Colegiado do Curso que aprovou a elaboração do POMC'])]

        nomes_pdtecs = sorted(
            set(
                PlanoDisciplinaPPC.objects.prefetch_related('plano_disciplina')
                .filter(matriz_ppc__ppc=self.ppc, plano_disciplina__topico_especifico=True)
                .values_list('plano_disciplina__nome_disciplina', flat=True)
            )
        )
        if nomes_pdtecs:
            resumo.append(('PDTECs (Planos de Disciplinas Técnicas Específicas)', [f'Elaborar plano da disciplina "{pd}"' for pd in nomes_pdtecs]))
        return resumo

    @cached_property
    def impacto_remocao_pomc(self):
        itens_que_serao_removidos = []

        if self.comprovante_aprovacao_pomc:
            itens_que_serao_removidos.append(self.comprovante_aprovacao_pomc)

        itens_que_serao_removidos.extend(self.planos_disciplina_modificados.all())
        return itens_que_serao_removidos

    # ------------------------------------------------------
    # VERIFICAÇÕES RELATIVAS A MUDANÇAS NO ESTADO DO PAFC
    # ------------------------------------------------------
    def pode_ser_editado(self):
        return self.situacao_eh_anterior_a_validacao() or self.em_validacao()

    def pode_ser_arquivado(self):
        if self.situacao == PAFC.AGUARDANDO_PORTARIA and self.portaria_comissao_elaboracao_vigente:
            return True
        return self.situacao not in [PAFC.EM_SOLICITACAO, PAFC.AGUARDANDO_PORTARIA, PAFC.FINALIZADO, PAFC.ARQUIVADO]

    def pode_ser_excluido(self):
        if self.situacao == PAFC.AGUARDANDO_PORTARIA and not self.portaria_comissao_elaboracao_vigente:
            return True
        return self.situacao == PAFC.EM_SOLICITACAO

    def pode_ser_enviado_para_analise_preliminar(self):
        return (
            self.situacao == PAFC.EM_ELABORACAO
            and self.is_elaboracao_concluida
            # não veio de etapas posteriores
            and not self.possui_comentarios_revisao_tecnica
            and not self.possui_comentarios_validacao
            # não veio da câmara ou conselhos
            and not self.retornou_da_camara_ou_conselhos()
        )

    def pode_ser_enviado_para_revisao_tecnica(self):
        return (
            self.situacao == PAFC.EM_ANALISE_PRELIMINAR
            and self.is_analise_preliminar_concluida
            or (
                self.situacao == PAFC.EM_ELABORACAO
                and self.is_elaboracao_concluida
                # possui comentários da revisão
                and (self.possui_comentarios_revisao_tecnica or self.retornou_da_camara_ou_conselhos())
            )
        )

    def pode_ser_enviado_para_validacao(self):
        return (
            self.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.is_revisao_tecnica_concluida
            or (
                self.situacao == PAFC.EM_ELABORACAO
                and self.is_elaboracao_concluida
                # tem comentários da validação
                and self.possui_comentarios_validacao
            )
        )

    @cached_property
    def pode_ser_devolvido_para_elaboracao(self):
        qs_revisoes_tecnicas_incompletas = ConteudoPAFC.objects.filter(editavel=True, secao__pafc=self, secao__data_revisao_tecnica__isnull=True)
        qs_validacoes_incompletas = ConteudoPAFC.objects.filter(editavel=True, secao__pafc=self, secao__data_validacao__isnull=True)
        return (
            self.em_analise_preliminar()
            and self.possui_comentarios_analise_preliminar
            or (self.em_revisao_tecnica() and self.possui_comentarios_revisao_tecnica and not qs_revisoes_tecnicas_incompletas.exists())
            or (self.em_validacao() and self.possui_comentarios_validacao and not qs_validacoes_incompletas.exists())
        )

    def pode_ter_comissao_editada(self):
        return self.situacao <= PAFC.EM_ELABORACAO

    def pode_ter_colaboradores_editados(self):
        return self.situacao_eh_anterior_a_aprovacao_camara()

    def pode_ter_equipe_revisao_tecnica_editada(self):
        return self.situacao_eh_anterior_a_aprovacao_camara()

    def pode_ter_equipe_validacao_editada(self):
        return self.situacao_eh_anterior_a_aprovacao_camara()

    def pode_ser_elaborado(self):
        return self.situacao == PAFC.EM_ELABORACAO

    def pode_ter_portaria_comissao_elaboracao_emitida(self):
        return self.situacao == PAFC.AGUARDANDO_PORTARIA and not self.portaria_comissao_elaboracao_vigente

    def pode_ter_portaria_comissao_elaboracao_solicitada(self):
        return self.situacao == PAFC.EM_SOLICITACAO and not self.portaria_comissao_elaboracao_vigente and self.membrocomissaopafc_set.exists()

    @cached_property
    def pode_ter_pomc_implementado(self):
        """
        Verifica se o POMC pode ser implementado no PAFC.
        Nessa verificação, leva-se em consideração o critério de conclusão do ciclo do curso e se há elementos passíveis de
        ajuste pelo campus, como a presença de PDTECs nas matrizes do PPC.
        """
        atende_criterio_dos_ciclos = self.is_pafc_criacao() or self.pomc_do_curso_completou_ciclo
        return (
            atende_criterio_dos_ciclos
            and PlanoDisciplina.objects.filter(planodisciplinappc__matriz_ppc__ppc=self.ppc, topico_especifico=True).exists()
        )

    def bibliografia_pode_ser_importada_do_ppc(self):
        return not self.ppc.get_planos_disciplina().exclude(situacao=PlanoDisciplina.APROVADO).exists()

    def pode_emitir_aprovacoes_conselhos(self):
        return self.ppc.situacao in [ProjetoPedagogicoCurso.APROVADO, ProjetoPedagogicoCurso.FINALIZADO]

    def pode_ter_curso_criado(self):
        qs_decisoes_finalizadas = self.documentos_emitidos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO)
        return (
            self.situacao == PAFC.APROVADO
            and self.is_pafc_criacao()
            and not self.curso
            and qs_decisoes_finalizadas.filter(
                documento__tipo=DocumentoHibrido.DELIBERACAO, situacao_pafc__in=[PAFC.AGUARDANDO_APROVACAO_CONSEPEX, PAFC.APROVADO]
            ).exists()
            and qs_decisoes_finalizadas.filter(
                documento__tipo=DocumentoHibrido.RESOLUCAO, situacao_pafc__in=[PAFC.AGUARDANDO_APROVACAO_CONSUP, PAFC.APROVADO]
            ).exists()
        )

    def pode_ter_curso_atualizado(self):
        qs_decisoes_finalizadas = self.documentos_emitidos.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO)
        return (
            self.situacao == PAFC.APROVADO
            and self.is_pafc_adequacao()
            and not self.data_atualizacao_curso
            and qs_decisoes_finalizadas.filter(
                documento__tipo=DocumentoHibrido.DELIBERACAO, situacao_pafc__in=[PAFC.AGUARDANDO_APROVACAO_CONSEPEX, PAFC.APROVADO]
            ).exists()
        )

    def pode_ser_finalizado(self):
        if self.situacao != PAFC.APROVADO or not self.ppc.is_finalizado():
            return False

        _, ato_aprovador = self.get_documentos_aprovadores()
        if ato_aprovador is None:
            return False

        if self.is_pafc_adequacao():
            return self.data_atualizacao_curso is not None
        else:
            deliberacao_homologadora_foi_cadastrada = self.consepex_inexistente or self.deliberacoes_finalizadas.filter(ad_referendum=False).exists()
            return self.curso is not None and deliberacao_homologadora_foi_cadastrada

    # ---------------------------------------------------
    # VERIFICAÇÕES RELATIVAS A PERMISSÕES DE USUÁRIOS
    # ---------------------------------------------------
    def tem_permissao_administrador(self, user):
        return user.has_group_cached(['Administrador Acadêmico', 'Administrador de PAFC'])

    def tem_permissao_edicao(self, user):
        """
        Verifica se o usuário pode editar o conteúdo das seções.
        """
        if self.pode_editar(user):
            return True
        elif self.em_elaboracao():
            return self.membrocomissaopafc_set.filter(
                servidor=user.get_vinculo().id_relacionamento, permissao=MembroComissaoPAFC.PERMISSAO_EDICAO
            ).exists()
        elif self.em_revisao_tecnica():
            return self.revisortecnicopafc_set.filter(
                servidor=user.get_vinculo().id_relacionamento, permissao=RevisorTecnicoPAFC.PERMISSAO_EDICAO
            ).exists()
        elif self.em_analise_preliminar() or self.em_validacao():
            return self.validadorpafc_set.filter(servidor=user.get_vinculo().id_relacionamento, permissao=ValidadorPAFC.PERMISSAO_EDICAO).exists()
        return False

    def pode_editar(self, user):
        return self.tem_permissao_administrador(user) or self.is_diretor_academico(user)

    def pode_elaborar(self, user):
        return self.is_elaborador(user) and self.tem_permissao_edicao(user) or self.tem_permissao_administrador(user)

    def pode_arquivar(self, user):
        return self.pode_editar(user)

    def pode_excluir(self, user):
        return self.pode_editar(user)

    def pode_solicitar_portaria_comissao_elaboracao(self, user):
        return self.is_diretor_academico(user)

    def pode_emitir_portaria_comissao_elaboracao(self, user):
        return self.is_diretor_geral(user)

    def pode_emitir_documento(self, user, documento):
        documentos = self.get_documentos_para_emissao(user)
        return documento in documentos

    def pode_emitir_parecer_validacao(self, user):
        return (
            self.situacao == PAFC.AGUARDANDO_VALIDACAO
            and self.is_validador(user)
            and self.percentual_validacao == 100
            and not self.ha_plano_de_disciplina_em_situacao_pendente()
            and not self.possui_comentarios_validacao
            and not self.parecer_validacao_ja_foi_emitido
        )

    def pode_emitir_parecer_proreitoria(self, user):
        return (
            self.situacao == PAFC.EM_ANALISE_PROREITORIA
            and user.get_vinculo().setor_id == self.proreitoria.setor_id
            and not self.parecer_proreitoria_ja_foi_emitido()
        )

    def pode_emitir_parecer_camara(self, user):
        return (
            self.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA
            and self.data_convocacao_camara
            and datetime.date.today() >= self.data_convocacao_camara
            and (self.is_coordenador_camara(user) or self.is_secretario_camara(user))
            and not self.parecer_camara_ja_foi_emitido()
        )

    def pode_solicitar_correcao_nos_conselhos(self, user):
        return (
            self.em_aprovacao_conselhos()
            and (ProjetoPedagogicoCurso.is_secretario_conselho(user) or ProjetoPedagogicoCurso.is_presidente_conselho(user))
            and not self.documentos_emitidos.select_related('documento')
            .filter(documento__tipo=DocumentoHibrido.ATA, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO, situacao_pafc=self.situacao)
            .exists()
        )

    def pode_solicitar_tramitacao_ad_referendum(self, user):
        estah_no_consepex = self.situacao == self.AGUARDANDO_APROVACAO_CONSEPEX
        estah_no_consup = self.situacao == self.AGUARDANDO_APROVACAO_CONSUP
        reuniao_consepex_nao_ocorreu = self.data_convocacao_consepex is None or self.data_convocacao_consepex > get_datetime_now().date()
        reuniao_consup_nao_ocorreu = self.data_convocacao_consup is None or self.data_convocacao_consup > get_datetime_now().date()
        return (
            (estah_no_consepex and reuniao_consepex_nao_ocorreu or estah_no_consup and reuniao_consup_nao_ocorreu)
            and self.pode_emitir_aprovacoes_conselhos()
            and ProjetoPedagogicoCurso.is_secretario_conselho(user)
            and not self.solicitacoes_tramitacao_ad_referendum.filter(situacao_pafc=self.situacao)
        )

    def pode_emitir_deliberacao(self, user):
        pode_regular = False
        pode_ad_referendum = False
        pode_homologacao = False

        if self.consepex_inexistente:
            return False, False, False

        eh_presidente = ProjetoPedagogicoCurso.is_presidente_conselho(user)
        eh_secretario = ProjetoPedagogicoCurso.is_secretario_conselho(user)

        if self.pode_emitir_aprovacoes_conselhos() and (eh_presidente or eh_secretario):
            qs_documentos_emitidos = self.documentos_emitidos.filter(documento__tipo=DocumentoHibrido.DELIBERACAO)
            reuniao_realizada = self.data_convocacao_consepex and datetime.date.today() >= self.data_convocacao_consepex
            if self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                pode_regular = (
                    reuniao_realizada
                    and self.decisao_consepex is None
                    and not qs_documentos_emitidos.filter(ad_referendum=True, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists()
                )
                pode_ad_referendum = (
                    self.decisao_consepex is None
                    and not qs_documentos_emitidos.filter(ad_referendum=True).exists()
                    and (eh_presidente or self.solicitacoes_tramitacao_ad_referendum.filter(situacao_pafc=self.situacao, deferida=True).exists())
                )
            else:
                deliberacao_foi_homologada = qs_documentos_emitidos.filter(ad_referendum=False).exists()
                pode_homologacao = (
                    reuniao_realizada
                    and not deliberacao_foi_homologada
                    and qs_documentos_emitidos.filter(ad_referendum=True, documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO).exists()
                )

        return pode_regular, pode_ad_referendum, pode_homologacao

    def pode_emitir_resolucao(self, user):
        pode_regular = False
        pode_ad_referendum = False
        pode_homologacao = False

        eh_presidente = ProjetoPedagogicoCurso.is_presidente_conselho(user)
        eh_secretario = ProjetoPedagogicoCurso.is_secretario_conselho(user)

        if self.pode_emitir_aprovacoes_conselhos() and (self.is_pafc_criacao() or self.consepex_inexistente) and (eh_presidente or eh_secretario):
            qs_documentos_emitidos = self.documentos_emitidos.filter(documento__tipo=DocumentoHibrido.RESOLUCAO)
            reuniao_realizada = self.data_convocacao_consup and datetime.date.today() >= self.data_convocacao_consup
            if self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP:
                pode_regular = (
                    reuniao_realizada
                    and self.decisao_consup is None
                    and not qs_documentos_emitidos.filter(ad_referendum=True, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO).exists()
                )
                pode_ad_referendum = (
                    self.decisao_consup is None
                    and not qs_documentos_emitidos.filter(ad_referendum=True).exists()
                    and (eh_presidente or self.solicitacoes_tramitacao_ad_referendum.filter(situacao_pafc=self.situacao, deferida=True).exists())
                )
            else:
                resolucao_foi_homologada = qs_documentos_emitidos.filter(ad_referendum=False).exists()
                pode_homologacao = (
                    reuniao_realizada
                    and not resolucao_foi_homologada
                    and qs_documentos_emitidos.filter(ad_referendum=True, documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO)
                )

        return pode_regular, pode_ad_referendum, pode_homologacao

    def pode_marcar_tudo_como_revisado(self, user):
        return (
            self.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and (
                self.decisao_camara in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
                or self.decisao_consepex in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
                or self.decisao_consup in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
            )
            and (self.is_revisor_tecnico(user) or self.is_validador(user))
            and self.percentual_revisao_tecnica < 100
        )

    def pode_enviar_para_validacao(self, user):
        return self.tem_permissao_edicao(user) and (
            self.is_elaborador(user)
            or self.is_revisor_tecnico(user)
            or self.is_validador(user)
            and (
                self.decisao_camara in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
                or self.decisao_consepex in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
                or self.decisao_consup in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
            )
        )

    def pode_alterar_elaboradores(self, user):
        return self.pode_editar(user) or self.is_elaborador_coordenador(user)

    def pode_alterar_colaboradores(self, user):
        return self.tem_permissao_edicao(user)

    def pode_alterar_revisores(self, user):
        return user.is_superuser or user.has_group_cached(['Administrador de PAFC', 'Operador Sistêmico PAFC'])

    def pode_alterar_revisores_tecnicos(self, user):
        return self.pode_alterar_revisores(user) or self.is_revisor_tecnico(user, is_coordenador=True)

    def pode_alterar_validadores(self, user):
        return self.pode_alterar_revisores(user) or self.is_validador(user, is_coordenador=True)

    def pode_convocar_camara(self, user):
        return (
            self.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA
            and self.decisao_camara is None
            and (self.is_secretario_camara(user) or self.is_coordenador_camara(user))
        )

    def pode_convocar_consepex(self, user):
        result = False
        if self.decisao_consepex is None and ProjetoPedagogicoCurso.is_secretario_conselho(user):
            if self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                if self.consepex_inexistente:
                    despacho_existe = self.documentos_emitidos.filter(
                        situacao_pafc=self.situacao,
                        documento__tipo=DocumentoHibrido.DESPACHO,
                        documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
                    ).exists()
                    result = not despacho_existe
                else:
                    result = True
            # Se em situação posterior e for ad referendum
            elif self.ad_referendum:
                deliberacao_ad_referendum_existe = self.documentos_emitidos.filter(
                    ad_referendum=True, documento__tipo=DocumentoHibrido.DELIBERACAO, documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO
                ).exists()
                result = deliberacao_ad_referendum_existe
        return result

    def pode_convocar_consup(self, user):
        result = False
        if (
            (self.is_pafc_criacao() or self.consepex_inexistente)
            and self.decisao_consup is None
            and ProjetoPedagogicoCurso.is_secretario_conselho(user)
        ):
            if (
                self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP
                or self.ad_referendum
                and self.documentos_emitidos.filter(
                    ad_referendum=True, documento__tipo=DocumentoHibrido.RESOLUCAO, documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO
                ).exists()
            ):
                result = True
        return result

    def pode_emitir_despacho_consepex(self, user):
        if self.consepex_inexistente and self.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
            doc_criado = self.documentos_emitidos.filter(
                situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX,
                documento__tipo=DocumentoHibrido.DESPACHO,
                documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO,
            ).exists()
            return not doc_criado and (ProjetoPedagogicoCurso.is_presidente_conselho(user) or ProjetoPedagogicoCurso.is_secretario_conselho(user))
        return False

    def pode_criar_curso(self, user):
        return self.is_pafc_criacao() and user.has_perm('edu.add_cursocampus')

    def pode_atualizar_curso(self, user):
        return self.is_pafc_adequacao() and user.has_perm('edu.change_cursocampus')

    def pode_finalizar(self, user):
        return user.has_perm('pafc.change_pafc')

    # ---------------------------------------------------
    # AÇÕES SOBRE O CADASTRO DO PAFC
    # ---------------------------------------------------
    @transaction.atomic
    def enviar_para_analise_preliminar(self, user):
        self.comentarios_gerais.filter(tipo_revisao=ComentarioGeralPAFC.ANALISE_PRELIMINAR, revisao_finalizada=False).update(revisao_finalizada=True)
        qs_comentarios_conteudos = ComentarioRevisao.objects.filter(
            conteudo__secao__pafc=self, tipo_revisao=ComentarioRevisao.ANALISE_PRELIMINAR, revisao_finalizada=False
        )
        ids_conteudos = set(qs_comentarios_conteudos.values_list('conteudo__id', flat=True))
        qs_comentarios_conteudos.update(revisao_finalizada=True)
        ConteudoPAFC.objects.filter(pk__in=ids_conteudos).update(situacao=ConteudoPAFC.PRONTO_PARA_REVISAR)
        PlanoDisciplinaModificado.processar_envio_do_pafc_para_revisao(self, PAFC.EM_ANALISE_PRELIMINAR)
        self.situacao = PAFC.EM_ANALISE_PRELIMINAR
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    @transaction.atomic
    def enviar_para_revisao_tecnica(self, user):
        self.comentarios_gerais.filter(tipo_revisao=ComentarioGeralPAFC.REVISAO_TECNICA, revisao_finalizada=False).update(revisao_finalizada=True)
        qs_comentarios_conteudos = ComentarioRevisao.objects.filter(
            conteudo__secao__pafc=self, tipo_revisao=ComentarioRevisao.REVISAO_TECNICA, revisao_finalizada=False
        )
        ids_conteudos = set(qs_comentarios_conteudos.values_list('conteudo__id', flat=True))
        qs_comentarios_conteudos.update(revisao_finalizada=True)
        ConteudoPAFC.objects.filter(pk__in=ids_conteudos).update(situacao=ConteudoPAFC.PRONTO_PARA_REVISAR)
        PlanoDisciplinaModificado.processar_envio_do_pafc_para_revisao(self, PAFC.AGUARDANDO_REVISAO_TECNICA)
        self.situacao = PAFC.AGUARDANDO_REVISAO_TECNICA
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    @transaction.atomic
    def enviar_para_validacao(self, user):
        self.comentarios_gerais.filter(tipo_revisao=ComentarioGeralPAFC.VALIDACAO, revisao_finalizada=False).update(revisao_finalizada=True)
        qs_comentarios_conteudos = ComentarioRevisao.objects.filter(
            conteudo__secao__pafc=self, tipo_revisao=ComentarioRevisao.VALIDACAO, revisao_finalizada=False
        )
        ids_conteudos = set(qs_comentarios_conteudos.values_list('conteudo_id', flat=True))
        qs_comentarios_conteudos.update(revisao_finalizada=True)
        ConteudoPAFC.objects.filter(pk__in=ids_conteudos).update(situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR)
        PlanoDisciplinaModificado.processar_envio_do_pafc_para_revisao(self, PAFC.AGUARDANDO_VALIDACAO)
        self.situacao = PAFC.AGUARDANDO_VALIDACAO
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    @transaction.atomic
    def marcar_todas_as_secoes_como_revisadas(self, user):
        for secao in self.get_secoes():
            if secao.pode_ter_revisao_tecnica_iniciada():
                secao.marcar_como_revisada(user)

    @transaction.atomic
    def marcar_todas_as_secoes_como_validadas(self, user):
        for secao in self.get_secoes():
            if secao.pode_ter_validacao_iniciada():
                secao.marcar_como_validada(user)

    def enviar_para_analise_proreitoria(self, user):
        self.situacao = PAFC.EM_ANALISE_PROREITORIA
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    def enviar_para_aprovacao_camara(self, user):
        self.situacao = PAFC.AGUARDANDO_APROVACAO_CAMARA
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    @transaction.atomic
    def devolver_para_elaboracao(self, user):
        qs_conteudos_pendentes = ConteudoPAFC.objects.filter(
            pk__in=ComentarioRevisao.objects.filter(conteudo__secao__pafc=self, revisao_finalizada=False)
            .values_list('conteudo__pk', flat=True)
            .distinct()
        )
        nova_situacao = ConteudoPAFC.PRONTO_PARA_REVISAR
        if self.em_validacao():
            nova_situacao = ConteudoPAFC.PRONTO_PARA_VALIDAR

        qs_conteudos_pendentes.update(situacao=nova_situacao)
        PlanoDisciplinaModificado.processar_devolucao_do_pafc_para_elaboracao(self)
        self.situacao = PAFC.EM_ELABORACAO
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self, 'Devolvido para elaboração.')

    @transaction.atomic
    def devolver_para_elaboracao_apartir_da_camara_ou_conselhos(self, situacao_origem, decisao_motivo):
        """
        Reconfigura PAFC para elaboração após aprovação com ressalva na Câmara ou nos Conselhos.
        """
        ConteudoPAFC.objects.filter(secao__pafc=self, editavel=True, situacao=ConteudoPAFC.APROVADO).update(situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR)
        PlanoDisciplinaModificado.processar_devolucao_do_pafc_para_elaboracao(self)
        self.situacao = PAFC.EM_ELABORACAO
        self.save()

        MovimentacaoPAFC.registrar_movimentacao(
            None, self, f'Retornado para elaboração após decisão "{decisao_motivo}" na etapa "{situacao_origem}".'
        )

    def popular_disciplinas(self):
        for id_plano_disciplina in self.ppc.get_planos_disciplina().only('id').values_list('id', flat=True):
            DisciplinaPAFC.objects.get_or_create(pafc=self, plano_disciplina_id=id_plano_disciplina)

    def remover_bibliografias_sem_disciplina(self):
        return self.bibliografiapafc_set.filter(disciplinas='').delete()

    def incorporar_bibliografia_do_plano_disciplina(self, plano_disciplina_modificado):
        titulos_secoes_bibliografia = ('Bibliografia Básica', 'Bibliografia Complementar')

        # Verificando bibliografias já cadastradas para a disciplina em questão.
        # O campo disciplinas possui o formato <disciplina 1>|<disciplinas 2>|...|<disciplina N>
        regex_nome_disciplina = r'(^|\|)' + plano_disciplina_modificado.nome_disciplina + r'(\||$)'
        ids_bibliografias_vinculadas_ao_plano_inicialmente = set(
            self.get_bibliografias_dos_topicos_especificos()
            .only('id', 'disciplinas', 'pafc_id')
            .order_by('id')
            .filter(disciplinas__iregex=regex_nome_disciplina)
            .values_list('id', flat=True)
        )

        qtd_criadas = 0
        qtd_atualizadas = 0
        ids_bibliografias_criadas_ou_atualizadas = set()
        bibliografias_a_remover_disciplina = []

        qs_secoes = plano_disciplina_modificado.get_secoes()
        if not qs_secoes.exists() and plano_disciplina_modificado.possui_versao_ead:
            qs_secoes = plano_disciplina_modificado.get_secoes_ead()

        for secao in qs_secoes.filter(modelo_secao__titulo__in=titulos_secoes_bibliografia):
            tipo = (
                BibliografiaPAFC.BIBLIOGRAFIA_BASICA
                if secao.modelo_secao.titulo == 'Bibliografia Básica'
                else BibliografiaPAFC.BIBLIOGRAFIA_COMPLEMENTAR
            )
            quantidade_ideal = 5

            for bibliografia in extrair_bibliografias_da_secao(secao.texto):
                criada, atualizada, obj = BibliografiaPAFC.criar_ou_atualizar_dados_bibliograficos(
                    self, tipo, bibliografia, [plano_disciplina_modificado.nome_disciplina], quantidade_ideal
                )
                ids_bibliografias_criadas_ou_atualizadas.add(obj.pk)
                if criada:
                    qtd_criadas += 1
                if atualizada:
                    qtd_atualizadas += 1

        ids_bibliografias_desvinculadas_do_plano = ids_bibliografias_vinculadas_ao_plano_inicialmente - ids_bibliografias_criadas_ou_atualizadas
        for bibliografia in (
            self.bibliografiapafc_set.only('id', 'disciplinas', 'pafc_id').order_by('id').filter(pk__in=ids_bibliografias_desvinculadas_do_plano)
        ):
            bibliografia.remover_disciplina(plano_disciplina_modificado.nome_disciplina, salvar=False)
            bibliografias_a_remover_disciplina.append(bibliografia)

        if ids_bibliografias_desvinculadas_do_plano:
            BibliografiaPAFC.objects.bulk_update(bibliografias_a_remover_disciplina, ['disciplinas'])

        qtd_removidas, _ = self.remover_bibliografias_sem_disciplina()

        return qtd_criadas, qtd_atualizadas, qtd_removidas

    def importar_bibliografia_do_pomc_anterior(self, task=None):
        """
        Consulta a seção de bibliografia dos `PlanoDisciplinaModificado`s do último POMC implementado pelo curso e a importa.

        Se a Comissão de Elaboração optar por implementar o POMC após essa importação, os dados preenchidos no POMC
        atual sobrescrevem os dados importados anteriormente.

        Ao tentar executar a importação com uma implementação do POMC em andamento, o método não faz nada.
        """
        total_criadas, total_atualizadas, total_removidas = 0, 0, 0
        if self.pode_ter_pomc_implementado and not self.pomc_eh_obrigatorio and not self.implementa_pomc:
            iterator = task.iterate if task else iter
            for pdm_do_ultimo_pomc in iterator(self.curso.ultimo_pafc_com_pomc.planos_disciplina_modificados.all()):
                criadas, atualizadas, removidas = self.incorporar_bibliografia_do_plano_disciplina(pdm_do_ultimo_pomc)
                total_criadas += criadas
                total_atualizadas += atualizadas
                total_removidas += removidas
        return total_criadas, total_atualizadas, total_removidas

    def importar_bibliografia_do_ppc(self, task=None):
        """
        Processa a bibliografia do PPC e cria os registros do tipo `BibliografiaPAFC` (se ainda não existirem).
        A estratégia para a obtenção dos dados é a seguinte:
            - Se a bibliografia tiver sido processada no PPC (atributo `ProjetoPedagogicoCurso.bibliografia_html` está preenchido),
              apenas extrai os dados do HTML.
            - Se não, usa o método `ppc.utils.processar_bibliografia` para obter os dados estruturados.
        Em seguida, processa os dados para criar (ou atualizar) os registros de bibliografia no banco de dados.

        Importante: o processamento ignora planos de disciplinas do tipo tópico específico, uma vez que sua bibliografia
        será definida na implementação do POMC.

        Formatos esperados:
        1. Quando usar o atributo `ProjetoPedagogicoCurso.bibliografia_html`, um HTML no formato:
        <table [estilos]>
            <thead> ... </thead>
            <tbody>
                <tr>
                    <td>[descrição da obra]</td>
                    <td>[lista de disciplinas, separadas por <br>]</td>
                    <td>[quantidade de exemplares]</td>
                </tr>
                <tr>[...]</tr> (repete estrutura anterior)
                [...]
            </tbody>
        </table>

        2. Quando usar o método `ppc.utils.processar_bibliografia`, um dicionário no formato:
        {
            '<tipo de bibliografia>': {
                'chave': {
                    'texto_original': <descrição da obra bibliográfica> (str),
                    'disciplinas': <lista de disciplinas> (list[str]),
                    'qtd_exemplares': <int>,
                },
                [...]
            },
            [...]
        }
        """
        from ppc.utils import processar_bibliografia

        funcao_iterador = iter if task is None else task.iterate
        total_novos_registros = 0
        total_registros_atualizados = 0
        ids_bibliografias_criadas_ou_atualizadas = set()
        ids_bibliografias_topicos_especificos = set(self.get_bibliografias_dos_topicos_especificos().values_list('pk', flat=True))

        def limpar_disciplinas(disciplinas_raw: list[str]):
            """Limpa descrição das disciplinas, que geralmente vêm no formato '- Nome da disciplina<br>'."""
            return [re.sub(r'^-\s*|<br>', '', d).strip() for d in disciplinas_raw]

        def _criar_ou_atualizar_item_bibliografico(pafc, tipo, descricao, disciplinas_raw, quantidade_exemplares: int):
            """Processa um item da bibliografia individualmente."""
            disciplinas = set(limpar_disciplinas(disciplinas_raw))
            disciplinas = disciplinas - self.nomes_dos_topicos_especificos
            if not disciplinas:
                criado = False
                atualizado = False
            else:
                criado, atualizado, obj = BibliografiaPAFC.criar_ou_atualizar_dados_bibliograficos(
                    pafc, tipo, descricao, disciplinas, quantidade_exemplares
                )
                ids_bibliografias_criadas_ou_atualizadas.add(obj.id)
            return criado, atualizado

        def processar_itens_bibliograficos_dict(itens_bibliograficos: list[dict], tipo):
            """
            Processa os itens da bibliografia organizados em uma lista de dicts.
            Esperam-se elementos no formato:
            {
                'texto_original': <descrição da obra bibliográfica> (str),
                'disciplinas': <lista de disciplinas> (list[str]),
                'qtd_exemplares': <int>,
            }
            """
            qtd_criados, qtd_atualizados = 0, 0
            for item in funcao_iterador(itens_bibliograficos):
                descricao = item['texto_original'].strip()
                disciplinas_raw = item['disciplinas']
                qtd_exemplares = item['qtd_exemplares']

                criado, atualizado = _criar_ou_atualizar_item_bibliografico(self, tipo, descricao, disciplinas_raw, int(qtd_exemplares or 0))
                if criado:
                    qtd_criados += 1
                if atualizado:
                    qtd_atualizados += 1
            return qtd_criados, qtd_atualizados

        bibliografias = processar_bibliografia(self.ppc, formatar_resposta_em_html=False)
        bibliografia_basica = bibliografias.get('Bibliografia Básica', [])
        bibliografia_complementar = bibliografias.get('Bibliografia Complementar', [])

        if task:
            task.count(bibliografia_basica, bibliografia_complementar)

        if bibliografia_basica:
            criados, atualizados = processar_itens_bibliograficos_dict(bibliografia_basica.values(), BibliografiaPAFC.BIBLIOGRAFIA_BASICA)
            total_novos_registros += criados
            total_registros_atualizados += atualizados
        if bibliografia_complementar:
            criados, atualizados = processar_itens_bibliograficos_dict(bibliografia_complementar.values(), BibliografiaPAFC.BIBLIOGRAFIA_COMPLEMENTAR)
            total_novos_registros += criados
            total_registros_atualizados += atualizados

        total_registros_removidos, _ = self.bibliografiapafc_set.exclude(
            pk__in=ids_bibliografias_criadas_ou_atualizadas.union(ids_bibliografias_topicos_especificos)
        ).delete()

        return total_novos_registros, total_registros_atualizados, total_registros_removidos

    @transaction.atomic
    def sincronizar_planos_disciplina_entre_ppc_e_pomc(self, user, forcar_sincronia=False):
        """
        Sincroniza o mapeamento dos planos de disciplina do POMC com o PPC com base nas matrizes vinculadas ao PAFC.
        Adiciona os planos de matrizes vinculadas ao PAFC e exclui planos de matrizes removidas.
        """
        if self.implementa_pomc or forcar_sincronia:
            ids_planosdisciplinappc_vinculados_ao_pafc = set(
                self.get_planos_disciplina_ppc().filter(plano_disciplina__topico_especifico=True).values_list('pk', flat=True)
            )

            ids_planodisciplinappc_existentes_no_pomc = set(self.get_planos_disciplina_pomc().values_list('plano_disciplina_ppc_id', flat=True))
            ids_planos_a_adicionar = set(ids_planosdisciplinappc_vinculados_ao_pafc - ids_planodisciplinappc_existentes_no_pomc)
            ids_planos_a_remover = set(ids_planodisciplinappc_existentes_no_pomc - ids_planosdisciplinappc_vinculados_ao_pafc)

            # Excluindo planos de disciplina do POMC de matrizes removidas
            PlanoDisciplinaPOMC.objects.filter(plano_disciplina_modificado__pafc=self, plano_disciplina_ppc__in=ids_planos_a_remover).delete()

            # Criando os planos de disciplina do POMC de matrizes adicionadas
            for plano_ppc in PlanoDisciplinaPPC.objects.filter(pk__in=ids_planos_a_adicionar):
                plano_disciplina = plano_ppc.plano_disciplina
                pd_modificado, pd_foi_criado = PlanoDisciplinaModificado.get_or_create(
                    pafc=self,
                    plano_referencia=plano_disciplina,
                )
                if pd_foi_criado:
                    pd_modificado.ementa = plano_disciplina.ementa
                    pd_modificado.save()

                deve_popular_versao_ead = plano_ppc.qtd_aulas_ead > 0 and plano_disciplina.possui_versao_ead()
                if pd_foi_criado or deve_popular_versao_ead and not pd_modificado.possui_versao_ead or not pd_modificado.secoes_programa.exists():
                    qs_secoes = plano_disciplina.get_secoes_ead() if deve_popular_versao_ead else plano_disciplina.get_secoes()
                    SecaoProgramaPlanoDisciplinaModificado.objects.bulk_create(
                        [
                            SecaoProgramaPlanoDisciplinaModificado(
                                plano_disciplina=pd_modificado,
                                modelo_secao=secao.modelo_secao_plano_disciplina,
                                texto=secao.texto,
                                versao_ead=secao.versao_ead,
                            )
                            for secao in qs_secoes
                        ]
                    )

                PlanoDisciplinaPOMC.objects.create(
                    plano_disciplina_ppc=plano_ppc,
                    plano_disciplina_modificado=pd_modificado,
                )

            # Assegurando que não haverá PlanoDisciplinaModificado "órfão", i.e., desvinculado de qualquer PlanoDisciplinaPOMC.
            # Isso dificilmente acontecerá, mas pode ocorrer em casos de PPCs cujas matrizes são formadas por conjuntos diferentes de disciplinas.
            PlanoDisciplinaModificado.objects.filter(pafc=self, planos_disciplina_pomc__isnull=True).delete()

            # Registrando a movimentação.
            qtd_novos = len(ids_planos_a_adicionar)
            qtd_removidos = len(ids_planos_a_remover)
            detalhes = f'{qtd_novos} adicionado{pluralize(qtd_novos)}, {qtd_removidos} removido{pluralize(qtd_removidos)}'
            MovimentacaoPAFC.registrar_movimentacao(user, self, f'Planos de disciplinas do PPC sincronizados com o POMC do PAFC ({detalhes}).')

    @transaction.atomic
    def remover_comprovante_aprovacao_pomc(self, user, registrar_movimentacao=True):
        if self.comprovante_aprovacao_pomc:
            self.comprovante_aprovacao_pomc.delete()
            self.comprovante_aprovacao_pomc = None
            self.cadastrador_comprovante_aprovacao_pomc = None
            self.data_cadastro_comprovante_aprovacao_pomc = None
            self.save()
            if registrar_movimentacao:
                MovimentacaoPAFC.registrar_movimentacao(user, self, 'Removida a Ata da Reunião do Colegiado que aprovou o POMC.')

    @transaction.atomic
    def remover_pomc(self, user):
        self.remover_comprovante_aprovacao_pomc(user, registrar_movimentacao=False)
        self.planos_disciplina_modificados.filter().delete()
        MovimentacaoPAFC.registrar_movimentacao(user, self, 'Dados do POMC removidos.')

    def gerar_conteudo(self):
        if not self.secaopafc_set.exists():
            for secao in self.modelo.secao_set.all():
                secaopafc = SecaoPAFC.objects.create(
                    pafc=self,
                    titulo=secao.titulo,
                    ordem_exibicao=secao.ordem_exibicao,
                    subsecao=secao.subsecao,
                )
                for conteudo in secao.conteudo_set.all():
                    ConteudoPAFC.objects.create(
                        secao=secaopafc,
                        texto=conteudo.texto,
                        ordem_exibicao=conteudo.ordem_exibicao,
                        editavel=conteudo.editavel,
                        orientacao_preenchimento=conteudo.orientacao_preenchimento,
                    )

    def arquivar(self, user):
        self.situacao = PAFC.ARQUIVADO
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    def registrar_ato_regulatorio(self, tipo_do_ato, documento: DocumentoHibrido, data_referencia=None, ad_referendum=False, ato_homologador=None):
        if not data_referencia:
            data_referencia = self.data_aprovacao

        from edu.models import AtoRegulatorioCurso

        qs_atos_registrados = AtoRegulatorioCurso.objects.filter(
            Q(tipo=tipo_do_ato, data__year=data_referencia.year), Q(curso__isnull=False, curso=self.curso) | Q(id_pafc__isnull=False, id_pafc=self.id)
        )
        # Gera o ato apenas se ele não tiver sido cadastrado no curso ainda
        if ato_existente := qs_atos_registrados.filter(ad_referendum=ad_referendum).last():
            if ato_existente.id_pafc is None:
                ato_existente.id_pafc = self.id
                ato_existente.save()
            return ato_existente
        else:
            if tipo_do_ato == AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS:
                ato_criado = AtoRegulatorioCurso.gerar_ato_alteracao_vagas_pafc(
                    self.curso_id, self.numero_vagas_curso, documento.id_documento_eletronico, self.id
                )
            else:
                ato_criado = AtoRegulatorioCurso.gerar_ato_pafc(
                    self.curso_id, self.is_pafc_adequacao(), self.numero_vagas_curso, documento.id_documento_eletronico, self.id
                )

            # Registrando ato homologador (se houver) do ato ad referendum recém criado.
            if ad_referendum and ato_homologador:
                ato_criado.ad_referendum = ad_referendum
                ato_criado.ato_homologador = ato_homologador
                ato_criado.save()
            elif not ad_referendum:
                # Registrando o ato como homologador de ato ad referendum existente.
                if ato_a_homologar := qs_atos_registrados.filter(ad_referendum=True).last():
                    ato_a_homologar.ato_homologador = ato_criado
                    ato_a_homologar.save()

            return ato_criado

    def criar_curso(self, user):
        if self.is_pafc_criacao() and not self.curso:
            curso_criado_no_ppc = self.ppc.matrizppc_set.first().cursos.filter(diretoria__setor=self.setor).first()
            if curso_criado_no_ppc:
                curso = curso_criado_no_ppc
            else:
                diretoria = Diretoria.objects.get(setor=self.setor)
                matrizes_deste_pafc = self.matrizpafc_set.values_list('matriz_ppc_id', flat=True)
                primeira_matriz = self.ppc.matrizppc_set.filter(pk__in=matrizes_deste_pafc).first()
                curso = primeira_matriz.criar_curso(diretoria)
                for matriz_ppc in self.ppc.matrizppc_set.filter(pk__in=matrizes_deste_pafc).exclude(pk=primeira_matriz.pk):
                    matriz_ppc.criar_matrizcurso(curso)

            curso.resolucao_criacao = self.get_texto_resolucao_ppc_criacao()
            curso.data_funcionamento = self.data_aprovacao

            curso.coordenador = self.coordenador_curso.get_vinculo()
            curso.ano_letivo = self.ano_letivo_primeira_oferta
            curso.periodo_letivo = self.periodo_letivo_primeira_oferta
            curso.quantidade_vagas = self.numero_vagas_curso

            curso.save()

            self.curso = curso
            self.save()
            MovimentacaoPAFC.registrar_movimentacao(user, self, 'Curso criado.')

    def atualizar_curso(self, user):
        self.curso.descricao = self.nome_curso
        self.curso.descricao_historico = self.ppc.nome_diploma_historico
        self.curso.coordenador = self.coordenador_curso.get_vinculo()
        mudou_qtd_vags = self.curso.quantidade_vagas != self.numero_vagas_curso
        self.curso.quantidade_vagas = self.numero_vagas_curso
        if not self.curso.data_funcionamento:
            ato = AtoRegulatorioCurso.objects.filter(
                curso=self.curso,
                tipo=AtoRegulatorioCurso.TIPO_AUTORIZACAO,
                ad_referendum=False,
            ).first()

            self.curso.data_funcionamento = ato.data if ato else None

        matrizes_deste_pafc = self.matrizpafc_set.values_list('matriz_ppc_id', flat=True)
        for matriz_ppc in self.ppc.matrizppc_set.filter(pk__in=matrizes_deste_pafc):
            if not self.curso.matrizes.filter(pk=matriz_ppc.matriz.pk).exists():
                matriz_ppc.criar_matrizcurso(self.curso)

        self.curso.save()

        self.data_atualizacao_curso = get_datetime_now()
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self, 'Curso atualizado.')

        # Gerando ato regulatório relativo à alteração de número de vagas
        if mudou_qtd_vags:
            doc_aprovacao_ad_referendum, doc_homologador = self.get_documentos_aprovadores()

            ato_homologador = None
            if doc_homologador:
                ato_homologador = self.registrar_ato_regulatorio(
                    tipo_do_ato=AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS,
                    documento=doc_homologador.documento,
                    data_referencia=doc_homologador.data_emissao,
                )

            if doc_aprovacao_ad_referendum:
                self.registrar_ato_regulatorio(
                    tipo_do_ato=AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS,
                    documento=doc_aprovacao_ad_referendum.documento,
                    data_referencia=doc_aprovacao_ad_referendum.data_emissao,
                    ad_referendum=True,
                    ato_homologador=ato_homologador,
                )

            MovimentacaoPAFC.registrar_movimentacao(user, self, 'Ato regulatório relativo à alteração de vagas registrado.')

    @transaction.atomic
    def finalizar(self, user):
        from edu.models import AtoRegulatorioCurso

        # Registrando atos regulatórios do curso
        documento_ad_referendum, documento_homologador = self.get_documentos_aprovadores()

        # Ato homologando a mudança na quantidade de vagas aprovada ad referendum, se for o caso.
        qs_atos_alteracao_de_vagas = AtoRegulatorioCurso.objects.filter(
            id_pafc=self.id,
            tipo=AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS,
        )
        ato_ad_referendum_alteracao_vagas = qs_atos_alteracao_de_vagas.filter(ad_referendum=True).first()
        ato_homologador_alteracao_vagas = qs_atos_alteracao_de_vagas.filter(ad_referendum=False).first()
        if ato_ad_referendum_alteracao_vagas and not ato_homologador_alteracao_vagas:
            ato_homologador_alteracao_vagas = self.registrar_ato_regulatorio(
                tipo_do_ato=AtoRegulatorioCurso.TIPO_ALTERACAO_VAGAS,
                documento=documento_homologador.documento,
                data_referencia=documento_homologador.data_emissao,
            )
            ato_ad_referendum_alteracao_vagas.ato_homologador = ato_homologador_alteracao_vagas
            ato_ad_referendum_alteracao_vagas.save()

        # Ato de autorização de funcionamento ou adequação
        tipo_ato_de_autorizacao = AtoRegulatorioCurso.TIPO_AUTORIZACAO if self.is_pafc_criacao() else AtoRegulatorioCurso.TIPO_ADEQUACAO_PAFC
        ato_homologador = self.registrar_ato_regulatorio(
            tipo_do_ato=tipo_ato_de_autorizacao,
            documento=documento_homologador.documento,
            data_referencia=documento_homologador.data_emissao,
        )

        if documento_ad_referendum:
            self.registrar_ato_regulatorio(
                tipo_do_ato=tipo_ato_de_autorizacao,
                documento=documento_ad_referendum.documento,
                data_referencia=documento_ad_referendum.data_emissao,
                ad_referendum=True,
                ato_homologador=ato_homologador,
            )

        MovimentacaoPAFC.registrar_movimentacao(user, self, 'Ato(s) regulatório(s) do curso registrado(s).')

        # Finalizando PAFC
        self.situacao = PAFC.FINALIZADO
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self)

    def solicitar_portaria_comissao_elaboracao(self, user):
        self.situacao = PAFC.AGUARDANDO_PORTARIA
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self, descricao='Portaria solicitada.')

    @transaction.atomic
    def atualizar_situacoes(self):
        DocumentoEmitidoPAFC.atualizar_situacoes(self)

        if self.em_elaboracao():
            if not self.ppc.possui_matrizppc_sem_aprovacao():
                if not self.disciplinas.exists():
                    self.popular_disciplinas()
                if not self.matrizpafc_set.exists() and self.ppc.matrizppc_set.count() == 1:
                    matriz = MatrizPAFC.objects.create(
                        pafc=self,
                        matriz_ppc=self.ppc.matrizppc_set.first(),
                    )
                    MovimentacaoPAFC.registrar_movimentacao(None, self, f'Matriz "{matriz}" vinculada automaticamente ao PAFC.')

            # Importação automática da bibliografia
            if not self.bibliografiapafc_set.exists() and self.bibliografia_pode_ser_importada_do_ppc():
                qtd_criadas, _, _ = self.importar_bibliografia_do_ppc()
                qtd_importadas_do_ultimo_pomc, _, _ = self.importar_bibliografia_do_pomc_anterior()
                total_criadas = qtd_criadas + qtd_importadas_do_ultimo_pomc
                if total_criadas:
                    MovimentacaoPAFC.registrar_movimentacao(
                        None,
                        self,
                        f'Bibliografia atualizada automaticamente. {total_criadas} registro{pluralize(total_criadas)} criado{pluralize(total_criadas)}.',
                    )

        self.refresh_from_db()

    # --------------------------------------------------------------------------
    # MÉTODOS AUXILIARES PARA GERAÇÃO DE CONTEÚDO DINÂMICO EM TEMPLATES
    # --------------------------------------------------------------------------
    def get_comissao_elaboracao_html(self):
        return render_to_string(
            'quadros/quadro_comissao_elaboracao.html',
            {
                'coordenador': self.membrocomissaopafc_set.filter(funcao=MembroComissaoPAFC.FUNCAO_COORDENADOR)
                .only('servidor__matricula', 'servidor__pessoa_fisica__nome')
                .first(),
                'membros': self.membrocomissaopafc_set.filter(funcao=MembroComissaoPAFC.FUNCAO_MEMBRO)
                .select_related('servidor', 'servidor__pessoa_fisica')
                .only('servidor__matricula', 'servidor__pessoa_fisica__nome'),
            },
        )

    @cached_property
    def quadro_tecnicos_administrativos_html(self):
        return render_to_string(
            'quadros/quadro_tecnicos_administrativos.html',
            {
                'tecnicos_administrativos': list(
                    self.tecnicos_administrativos.select_related(
                        'pessoa_fisica',
                        'situacao',
                        'jornada_trabalho',
                        'cargo_emprego_area',
                        'cargo_classe',
                    )
                    .only('matricula', 'pessoa_fisica__nome', 'situacao__nome', 'jornada_trabalho', 'cargo_emprego_area', 'cargo_classe')
                    .all()
                ),
                'justificativa_indisponibilidade': self.justificativa_indisponibilidade_tecnicos_administrativos,
            },
        )

    @cached_property
    def quadro_docentes_html(self):
        return render_to_string(
            'quadros/quadro_docentes.html',
            {
                'disciplinas': self.disciplinas.prefetch_related(
                    'plano_disciplina',
                    'docentes',
                    'docentes__pessoa_fisica',
                    'docentes__situacao',
                    'docentes__jornada_trabalho',
                )
                .only(
                    'plano_disciplina__nome_disciplina',
                    'docentes__pessoa_fisica__nome',
                    'docentes__matricula',
                    'docentes__situacao',
                    'docentes__jornada_trabalho',
                    'docentes__titulacao',
                    'justificativa_indisponibilidade_docentes',
                )
                .all(),
            },
        )

    @cached_property
    def quadro_laboratorios_html(self):
        campos_laboratorios = ['id', 'nome', 'area_util', 'capacidade', 'descricao']
        laboratorios = list(self.salas.only(*campos_laboratorios).order_by('nome').values(*campos_laboratorios))
        for lab in laboratorios:
            lab['equipamentos'] = Inventario.ativos.filter(sala_id=lab.get('id')).order_by('descricao').values('descricao').annotate(qtde=Count('id'))
        return render_to_string(
            'quadros/quadro_laboratorios.html',
            {'laboratorios': laboratorios, 'justificativa_indisponibilidade': self.justificativa_indisponibilidade_laboratorios},
        )

    @cached_property
    def quadro_matrizes_html(self):
        return render_to_string(
            'quadros/quadro_matrizes.html',
            {
                'matrizes': self.matrizpafc_set.prefetch_related(
                    'matriz_ppc',
                )
                .only(
                    'matriz_ppc__nome',
                    'matriz_ppc__quantidade_periodos',
                )
                .all(),
            },
        )

    @cached_property
    def quadro_bibliografia_basica_html(self):
        return self.get_quadro_bibliografia_html(BibliografiaPAFC.BIBLIOGRAFIA_BASICA)

    @cached_property
    def quadro_bibliografia_complementar_html(self):
        return self.get_quadro_bibliografia_html(BibliografiaPAFC.BIBLIOGRAFIA_COMPLEMENTAR)

    def get_quadro_bibliografia_html(self, tipo):
        bibliografias_por_disciplina = {}
        qs_bibliografias = self.bibliografiapafc_set.filter(
            tipo_bibliografia=tipo,
        ).only(
            'descricao',
            'disciplinas',
            'quantidade_no_campus',
            'observacao',
            'detalhes_observacao',
        )
        for bibliografia in qs_bibliografias:
            for disciplina in bibliografia.get_disciplinas_como_lista():
                if disciplina not in bibliografias_por_disciplina:
                    bibliografias_por_disciplina[disciplina] = []
                bibliografias_por_disciplina[disciplina].append(bibliografia)

        return render_to_string(
            'quadros/quadro_bibliografia.html',
            {
                'bibliografias_por_disciplina': dict(sorted(bibliografias_por_disciplina.items())),
            },
        )

    @cached_property
    def quadro_polos_html(self):
        return render_to_string(
            'quadros/quadro_polos.html',
            {
                'polos': self.polos_ead.all(),
            },
        )

    @cached_property
    def quadro_tutores_html(self):
        return render_to_string(
            'quadros/quadro_tutores.html',
            {
                'tutores': self.tutores_ead.select_related(
                    'vinculo__pessoa',
                    'vinculo__user',
                )
                .order_by('vinculo__pessoa__nome')
                .all(),
                'justificativa_indisponibilidade': self.justificativa_indisponibilidade_tutores,
            },
        )

    @cached_property
    def topicos_especificos_html(self):
        qs = self.get_planos_disciplina_pomc().values_list('plano_disciplina_modificado_id', flat=True)
        ids_regular = qs.filter(plano_disciplina_ppc__qtd_aulas_ead=0)
        ids_ead = qs.exclude(plano_disciplina_ppc__qtd_aulas_ead=0)
        return render_to_string(
            'planodisciplinamodificado_pdf.html',
            {
                'planos_regulares': PlanoDisciplinaModificado.objects.filter(id__in=ids_regular).order_by('plano_referencia__nome_disciplina'),
                'planos_ead': PlanoDisciplinaModificado.objects.filter(id__in=ids_ead).order_by('plano_referencia__nome_disciplina'),
                'nome_curso': self.curso.descricao if self.curso else self.ppc.nome_curso,
            },
        )


class DocumentoHibrido(LogModel):
    ATA = '1'
    DELIBERACAO = '2'
    PARECER = '3'
    PORTARIA = '4'
    RESOLUCAO = '5'
    DESPACHO = '6'
    OUTRO = '99'
    TIPO_DOCUMENTO_CHOICES = [
        [ATA, 'Ata'],
        [DELIBERACAO, 'Deliberação'],
        [PARECER, 'Parecer'],
        [PORTARIA, 'Portaria'],
        [RESOLUCAO, 'Resolução'],
        [DESPACHO, 'Despacho'],
        [OUTRO, 'Outro'],
    ]

    DOCUMENTO_CRIADO = '1'
    DOCUMENTO_FINALIZADO = '2'
    DOCUMENTO_CANCELADO = '3'
    DOCUMENTO_REMOVIDO = '4'
    SITUACAO_DOCUMENTO_CHOICES = [
        [DOCUMENTO_CRIADO, 'Criado'],
        [DOCUMENTO_FINALIZADO, 'Finalizado'],
        [DOCUMENTO_CANCELADO, 'Cancelado'],
        [DOCUMENTO_REMOVIDO, 'Removido'],
    ]

    tipo = models.CharFieldPlus(verbose_name='Tipo de documento', null=False, blank=False, choices=TIPO_DOCUMENTO_CHOICES)
    situacao = models.CharFieldPlus(
        verbose_name='Situação do documento', null=False, blank=False, choices=SITUACAO_DOCUMENTO_CHOICES, default=DOCUMENTO_CRIADO
    )

    # para uso com Documento Eletrônico
    id_documento_eletronico = models.PositiveIntegerFieldPlus('Id do documento eletrônico', null=True, blank=True)

    # para uso com arquivo comum (quando o módulo de Documento Eletrônico não for usado)
    arquivo = models.FileFieldPlus(upload_to='pafc/documentos_pafc/', verbose_name='Arquivo')
    identificador_arquivo = models.CharFieldPlus(
        'Identificador do Documento', max_length=100, blank=True, null=True, help_text='Exemplo: Ofício Nº XX/XXXX - PROEN/RE/IFRN'
    )
    assunto_arquivo = models.UnaccentField('Assunto', db_index=True, blank=True, null=True)

    class Meta:
        verbose_name = 'Documento'
        verbose_name_plural = 'Documentos'

    def __str__(self):
        tipo_documento = 'referência a documento eletrônico' if self.usa_documento_eletronico() else 'arquivo anexado'
        return f'{self.get_identificador_documento()} ({tipo_documento})'

    def usa_documento_eletronico(self):
        return self.id_documento_eletronico is not None

    @cached_property
    def documento_concreto(self):
        if self.usa_documento_eletronico():
            if modulo_documento_eletronico_esta_ativo():
                DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
                return DocumentoTexto.objects.filter(pk=self.id_documento_eletronico).first()
            return None
        return self.arquivo

    def documento_existe(self):
        return bool(self.documento_concreto)

    def estah_finalizado(self):
        documento = self.documento_concreto
        if self.usa_documento_eletronico():
            return documento is not None and documento.estah_finalizado
        return bool(documento)

    def estah_cancelado(self):
        if self.usa_documento_eletronico():
            documento = self.documento_concreto
            return documento is not None and documento.estah_cancelado
        else:
            return False

    def foi_removido(self):
        documento = self.documento_concreto
        if self.usa_documento_eletronico():
            return documento is None
        else:
            return not documento

    def get_identificador_documento(self):
        documento = self.documento_concreto
        if hasattr(documento, 'identificador'):
            return documento.identificador
        return self.identificador_arquivo

    def get_assunto_documento(self):
        documento = self.documento_concreto
        if hasattr(documento, 'assunto'):
            return documento.assunto
        return self.assunto_arquivo

    def get_url_documento(self):
        documento = self.documento_concreto
        if hasattr(documento, 'get_absolute_url'):
            return documento.get_absolute_url()
        return self.arquivo.url


class DocumentoEmitidoPAFC(LogModel):
    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', related_name='documentos_emitidos', null=False, blank=False)
    documento = models.ForeignKeyPlus('pafc.DocumentoHibrido', null=False, blank=False)
    situacao_pafc = models.IntegerFieldPlus(
        verbose_name='Situação do PAFC', null=False, blank=False, choices=PAFC.SITUACAO_CHOICES, help_text='Situação do PAFC na emissão do documento.'
    )
    ad_referendum = models.BooleanField('Ad Referendum', default=False)
    reprovacao = models.BooleanField('Reprovação do PAFC', default=False)
    emissor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Emissor', null=False, blank=False)
    data_emissao = models.DateTimeFieldPlus('Data da emissão', null=False, blank=False)
    decisao = models.CharFieldPlus(verbose_name='Decisão', null=True, blank=True, choices=PAFC.DECISAO_CHOICES)

    class Meta:
        verbose_name = 'Documento do PAFC'
        verbose_name_plural = 'Documentos do PAFC'

    def get_documento(self):
        return self.documento.documento_concreto

    def can_delete(self, user=None):
        return bool(user and (user.has_perm('pafc.delete_documentoemitidopafc') or user.get_relacionamento() == self.emissor))

    def get_url_documento(self):
        return self.documento.get_url_documento()

    @staticmethod
    def computar_metadados_documento(pafc: PAFC, tipo_documento: str):
        tipo = None
        assunto = tipo_documento
        ad_referendum = False
        decisao = None
        reprovado = False

        if tipo_documento == 'Portaria da Comissão de Elaboração':
            tipo = DocumentoHibrido.PORTARIA
            # Portaria da Comissão de Elaboração
            if pafc.situacao == PAFC.AGUARDANDO_PORTARIA:
                assunto = f'Portaria de Designação da Comissão de Elaboração de PAFC do {pafc.nome_curso}'

        elif tipo_documento == 'Parecer':
            tipo = DocumentoHibrido.PARECER
            # Parecer da etapa de Validação
            if pafc.situacao == PAFC.AGUARDANDO_VALIDACAO:
                decisao = PAFC.DECISAO_APROVAR
                assunto = f'{tipo_documento} da etapa de Validação do PAFC do {pafc.nome_curso}'
            # Parecer da análise da Pró-Reitoria
            elif pafc.situacao == PAFC.EM_ANALISE_PROREITORIA:
                reprovado = pafc.reprovado_proreitoria
                decisao = PAFC.DECISAO_REPROVAR if reprovado else PAFC.DECISAO_APROVAR
                assunto = f'{tipo_documento} da Pró-Reitoria sobre o PAFC do {pafc.nome_curso}'
            # Parecer da análise da Câmara
            elif pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA:
                decisao = pafc.decisao_camara
                reprovado = decisao == PAFC.DECISAO_REPROVAR
                assunto = f'{tipo_documento} da Câmara sobre o PAFC do {pafc.nome_curso}'

        elif tipo_documento == 'Ata':
            tipo = DocumentoHibrido.ATA
            # Ata da reunião quando os conselhos solicitam correção
            if pafc.em_aprovacao_conselhos():
                decisao = PAFC.DECISAO_SOLICITAR_CORRECAO
                conselho = 'CONSEPEX' if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX else 'CONSUP'
                assunto = f'Ata da reunião do {conselho} que solicitou correção do PAFC do {pafc.nome_curso}'

        elif tipo_documento == 'Despacho':
            tipo = DocumentoHibrido.DESPACHO
            decisao = PAFC.DECISAO_APROVAR
            assunto = 'Despacho'

        elif tipo_documento in ['Deliberação', 'Deliberação Ad Referendum', 'Deliberação de homologação']:
            tipo = DocumentoHibrido.DELIBERACAO
            if tipo_documento == 'Deliberação Ad Referendum':
                ad_referendum = True
            decisao = pafc.decisao_consepex
            reprovado = decisao == PAFC.DECISAO_REPROVAR
            assunto = f'{tipo_documento} do CONSEPEX sobre o PAFC do {pafc.nome_curso}'

        elif tipo_documento in ['Resolução', 'Resolução Ad Referendum', 'Resolução de homologação']:
            tipo = DocumentoHibrido.RESOLUCAO
            if tipo_documento == 'Resolução Ad Referendum':
                ad_referendum = True
            decisao = pafc.decisao_consup
            reprovado = decisao == PAFC.DECISAO_REPROVAR
            assunto = f'{tipo_documento} do CONSUP sobre o PAFC do {pafc.nome_curso}'

        return tipo, assunto, ad_referendum, decisao, reprovado

    @staticmethod
    def emitir_documento(pafc, user, tipo_documento):
        if not modulo_documento_eletronico_esta_ativo():
            raise ModuleNotFoundError('Módulo de Documento Eletrônico não instalado.')

        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        ModeloDocumento = apps.get_model('documento_eletronico', 'ModeloDocumento')

        doc_models = importlib.import_module('documento_eletronico.models')
        doc_utils = importlib.import_module('documento_eletronico.utils')

        tipo, assunto, ad_referendum, decisao, reprovado = DocumentoEmitidoPAFC.computar_metadados_documento(pafc, tipo_documento)
        setor_dono = user.get_vinculo().setor

        if pafc.em_aprovacao_conselhos():
            if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                conselho = 'Consepex'
                ID_CONSEPEX_IFRN = 1880
                id_setor = Configuracao.get_valor_por_chave('pafc', 'setor_consepex') or ID_CONSEPEX_IFRN
            else:
                conselho = 'Consup'
                ID_CONSUP_IFRN = 1881
                id_setor = Configuracao.get_valor_por_chave('pafc', 'setor_consup') or ID_CONSUP_IFRN

            if not doc_utils.get_setores_compartilhados(user, doc_models.NivelPermissao.EDITAR).filter(id=id_setor).exists():
                raise ValidationError(
                    f'Você não tem permissão para criar documentos do {conselho}. Verifique suas permissões no menu Documentos/Processos > Minhas Permissões.'
                )
            setor_dono = Setor.objects.suap_ativos().get(pk=id_setor)

        variaveis_basicas = {
            'campus': pafc.get_nome_campus_normalizado(),
            'campus_maiusculas': pafc.get_nome_campus_normalizado().upper(),
            'nome_curso': pafc.nome_curso,
            'nome_curso_maiusculas': pafc.nome_curso.upper(),
        }
        variaveis_especificas = {}

        if tipo_documento == 'Portaria da Comissão de Elaboração':
            if pafc.situacao == PAFC.AGUARDANDO_PORTARIA:
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_portaria_comissao_elaboracao') or 'Portaria Simples'
                variaveis_especificas.update(
                    {
                        'tipo_tramitacao': pafc.get_tipo_tramitacao().lower(),
                        'tabela_comissao_elaboracao': pafc.get_comissao_elaboracao_html(),
                    }
                )
            else:
                raise ValidationError(f'A situação {pafc.get_situacao_display()} não permite emissão de portaria.')
        elif tipo_documento == 'Parecer':
            if pafc.situacao == PAFC.AGUARDANDO_VALIDACAO:
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_parecer_validacao') or 'Parecer simples'
            elif pafc.situacao == PAFC.EM_ANALISE_PROREITORIA:
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_parecer_proreitoria') or 'Parecer simples'
            elif pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA:
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_parecer_camara') or 'Parecer simples'
            else:
                raise ValidationError(f'A situação {pafc.get_situacao_display()} não permite emissão de parecer.')
        elif tipo_documento == 'Ata':
            if pafc.em_aprovacao_conselhos():
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_ata_conselho') or 'Ata simples'
            else:
                raise ValidationError(f'A situação {pafc.get_situacao_display()} não permite emissão de ata.')
        elif tipo_documento == 'Despacho':
            if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_despacho_consepex') or 'Despacho Simples'
            else:
                raise ValidationError(f'A situação {pafc.get_situacao_display()} não permite emissão de despacho.')
        elif tipo_documento in ['Deliberação', 'Deliberação Ad Referendum', 'Deliberação de homologação']:
            nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_deliberacao') or 'Deliberação CONSEPEX - Submissão ao Consup'
        elif tipo_documento in ['Resolução', 'Resolução Ad Referendum', 'Resolução de homologação']:
            nome_modelo = Configuracao.get_valor_por_chave('pafc', 'nome_modelo_resolucao') or 'Resolução simples'
        else:
            raise ValidationError(f'Tipo de documento ({tipo_documento}) inválido.')

        try:
            modelo = ModeloDocumento.objects.get(nome=nome_modelo)
        except ModeloDocumento.DoesNotExist:
            raise ValueError(f'Modelo de documento "{nome_modelo}" não cadastrado.')

        variaveis = doc_utils.get_variaveis(
            documento_identificador='',
            estagio_processamento_variavel=doc_utils.EstagioProcessamentoVariavel.CRIACAO_DOCUMENTO,
            usuario=user,
            setor_dono=setor_dono,
        )
        variaveis.update(variaveis_basicas)
        variaveis.update(variaveis_especificas)

        with transaction.atomic():
            documento_eletronico = DocumentoTexto.adicionar_documento_texto(
                usuario=user,
                modelo=modelo,
                assunto=assunto,
                nivel_acesso=DocumentoTexto.NIVEL_ACESSO_PUBLICO,
                variaveis=variaveis,
                setor_dono=setor_dono,
            )

            doc_emitido = DocumentoEmitidoPAFC()
            doc_emitido.documento = DocumentoHibrido.objects.create(tipo=tipo, id_documento_eletronico=documento_eletronico.id)
            doc_emitido.pafc = pafc
            doc_emitido.situacao_pafc = pafc.situacao
            doc_emitido.ad_referendum = ad_referendum
            doc_emitido.reprovacao = reprovado
            doc_emitido.emissor = user.get_relacionamento()
            doc_emitido.data_emissao = documento_eletronico.data_criacao
            doc_emitido.decisao = decisao
            doc_emitido.save()

        MovimentacaoPAFC.registrar_movimentacao(user, pafc, f'{doc_emitido.documento.get_tipo_display()} emitido(a).')

        return doc_emitido

    @staticmethod
    def vincular_documento(pafc, user, tipo_documento, documento, assunto_documento=None, identificador_documento=None):
        tipo, assunto, ad_referendum, decisao, reprovado = DocumentoEmitidoPAFC.computar_metadados_documento(pafc, tipo_documento)

        doc_hibrido = DocumentoHibrido(tipo=tipo)
        doc_emitido = DocumentoEmitidoPAFC()

        if isinstance(documento, FileFieldPlus):
            doc_hibrido.arquivo = documento
            doc_hibrido.assunto_arquivo = assunto_documento or assunto
            doc_hibrido.identificador_arquivo = identificador_documento
            if identificador_documento is None:
                raise ValueError('Identificador do documento não informado.')
            with transaction.atomic():
                doc_hibrido.save()

        elif modulo_documento_eletronico_esta_ativo():
            DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
            if not isinstance(documento, DocumentoTexto):
                raise ValueError(f'{documento} não é um Documento Eletrônico válido.')

            if documento.id is None or not DocumentoTexto.objects.filter(pk=documento.id).exists():
                raise ValueError(f'O documento ({documento}) não existe na base de dados.')

            doc_hibrido.id_documento_eletronico = documento.id

            with transaction.atomic():
                doc_hibrido.save()

                doc_emitido.documento = doc_hibrido
                doc_emitido.pafc = pafc
                doc_emitido.situacao_pafc = pafc.situacao
                doc_emitido.ad_referendum = ad_referendum
                doc_emitido.reprovacao = reprovado
                doc_emitido.emissor = documento.usuario_criacao.get_relacionamento()
                doc_emitido.data_emissao = documento.data_criacao
                doc_emitido.decisao = decisao
                doc_emitido.save()

            MovimentacaoPAFC.registrar_movimentacao(user, pafc, f'{doc_emitido.documento.get_tipo_display()} vinculado(a) ao PAFC.')
        else:
            raise ValueError(f'Documento inválido: {documento}.')

        return doc_emitido

    @staticmethod
    def atualizar_situacoes(pafc):
        qs = pafc.documentos_emitidos

        # verificando alterações em documentos finalizados
        for doc_pafc_finalizado in qs.filter(documento__situacao=DocumentoHibrido.DOCUMENTO_FINALIZADO):
            removido = False
            cancelado = False
            if doc_pafc_finalizado.documento.foi_removido():
                removido = True
                doc_pafc_finalizado.documento.id_documento_eletronico = None
                doc_pafc_finalizado.documento.situacao = DocumentoHibrido.DOCUMENTO_REMOVIDO
                doc_pafc_finalizado.documento.save()
            elif doc_pafc_finalizado.documento.estah_cancelado():
                cancelado = True
                doc_pafc_finalizado.documento.situacao = DocumentoHibrido.DOCUMENTO_CANCELADO
                doc_pafc_finalizado.documento.save()
            if removido or cancelado:
                # se documento da portaria foi removido ou cancelado, zerar campo `portaria_comissao_elaboracao_vigente`
                if doc_pafc_finalizado.documento.tipo == DocumentoHibrido.PORTARIA and doc_pafc_finalizado.situacao_pafc == PAFC.AGUARDANDO_PORTARIA:
                    pafc.portaria_comissao_elaboracao_vigente = None
                MovimentacaoPAFC.registrar_movimentacao(
                    None, pafc, f'{doc_pafc_finalizado.documento.get_tipo_display()} {"removido(a)" if removido else "cancelado(a)"}.'
                )

        if pafc.portaria_comissao_elaboracao_vigente is None and pafc.situacao > PAFC.AGUARDANDO_PORTARIA:
            pafc.situacao = PAFC.EM_SOLICITACAO
            pafc.save()

        # documentos não finalizados da fase atual
        for doc_pafc in qs.filter(situacao_pafc=pafc.situacao, documento__situacao=DocumentoHibrido.DOCUMENTO_CRIADO):
            if doc_pafc.documento.foi_removido():
                # documento removido: registrar remoção
                doc_pafc.documento.id_documento_eletronico = None
                doc_pafc.documento.situacao = DocumentoHibrido.DOCUMENTO_REMOVIDO
                doc_pafc.documento.save()
            elif doc_pafc.documento.estah_cancelado():
                # documento eletrônico cancelado: registrar cancelamento
                doc_pafc.documento.situacao = DocumentoHibrido.DOCUMENTO_CANCELADO
                doc_pafc.documento.save()
            elif isinstance(doc_pafc.get_documento(), FileFieldPlus) or doc_pafc.documento.estah_finalizado():
                # documento finalizado: calcular nova situação do PAFC
                doc_pafc.documento.situacao = DocumentoHibrido.DOCUMENTO_FINALIZADO
                doc_pafc.documento.save()
                MovimentacaoPAFC.registrar_movimentacao(None, pafc, f'{doc_pafc.documento.get_tipo_display()} finalizado(a).')
                tipo_documento = doc_pafc.documento.tipo

                if doc_pafc.situacao_pafc == PAFC.AGUARDANDO_PORTARIA and tipo_documento == DocumentoHibrido.PORTARIA:
                    pafc.situacao = PAFC.EM_ELABORACAO
                    pafc.portaria_comissao_elaboracao_vigente = doc_pafc.documento
                    pafc.save()
                    pafc.gerar_conteudo()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)

                elif doc_pafc.situacao_pafc == PAFC.AGUARDANDO_VALIDACAO and tipo_documento == DocumentoHibrido.PARECER:
                    # tratar aprovação com ressalva / solicitação de correção do CONSUP
                    if pafc.decisao_consup == PAFC.DECISAO_APROVAR_RESSALVA:
                        pafc.situacao = PAFC.APROVADO
                    elif pafc.decisao_consup == PAFC.DECISAO_SOLICITAR_CORRECAO:
                        pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSUP
                    # tratar aprovação com ressalva / solicitação de correção do CONSEPEX
                    elif pafc.decisao_consepex == PAFC.DECISAO_APROVAR_RESSALVA:
                        if pafc.is_pafc_criacao():
                            pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSUP
                        else:
                            pafc.situacao = PAFC.APROVADO
                    elif pafc.decisao_consepex == PAFC.DECISAO_SOLICITAR_CORRECAO or pafc.decisao_camara == PAFC.DECISAO_APROVAR_RESSALVA:
                        pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSEPEX
                    elif pafc.decisao_camara == PAFC.DECISAO_SOLICITAR_CORRECAO:
                        pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CAMARA
                    # fluxo normal
                    else:
                        pafc.situacao = PAFC.EM_ANALISE_PROREITORIA

                    if pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CAMARA:
                        pafc.data_convocacao_camara = None
                        pafc.decisao_camara = None
                    elif pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSEPEX:
                        pafc.data_convocacao_consepex = None
                        pafc.decisao_consepex = None
                        pafc.justificativa_decisao_consepex = None
                        pafc.consepex_inexistente = False
                    elif pafc.situacao == PAFC.AGUARDANDO_APROVACAO_CONSUP:
                        pafc.data_convocacao_consup = None
                        pafc.decisao_consup = None
                        pafc.justificativa_decisao_consup = None

                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                elif doc_pafc.situacao_pafc == PAFC.EM_ANALISE_PROREITORIA and tipo_documento == DocumentoHibrido.PARECER:
                    if pafc.reprovado_proreitoria:
                        pafc.situacao = PAFC.REPROVADO
                        pafc.camara = None
                    else:
                        if pafc.camara is None:
                            raise ValidationError('Nenhuma Câmara foi associada para analisar este PAFC.')
                        if pafc.ad_referendum and pafc.pular_camara:
                            pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSEPEX
                        else:
                            pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CAMARA
                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                    # TODO: notificar

                elif doc_pafc.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CAMARA and tipo_documento == DocumentoHibrido.PARECER:
                    if doc_pafc.decisao == PAFC.DECISAO_APROVAR:
                        pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSEPEX
                    elif doc_pafc.decisao in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]:
                        pafc.devolver_para_elaboracao_apartir_da_camara_ou_conselhos(
                            situacao_origem=doc_pafc.get_situacao_pafc_display(), decisao_motivo=doc_pafc.get_decisao_display()
                        )
                    elif doc_pafc.decisao == PAFC.DECISAO_REPROVAR:
                        pafc.situacao = PAFC.REPROVADO
                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                    # TODO: notificar

                elif doc_pafc.situacao_pafc in [PAFC.AGUARDANDO_APROVACAO_CONSEPEX, PAFC.APROVADO] and tipo_documento == DocumentoHibrido.DELIBERACAO:
                    if doc_pafc.decisao == PAFC.DECISAO_APROVAR:
                        if pafc.is_pafc_criacao():
                            pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSUP
                        else:
                            pafc.situacao = PAFC.APROVADO
                            if pafc.data_aprovacao is None:
                                pafc.data_aprovacao = doc_pafc.data_emissao
                    elif doc_pafc.decisao in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]:
                        if pafc.is_pafc_adequacao() and doc_pafc.decisao == PAFC.DECISAO_APROVAR_RESSALVA:
                            if pafc.data_aprovacao is None:
                                pafc.data_aprovacao = doc_pafc.data_emissao
                        pafc.devolver_para_elaboracao_apartir_da_camara_ou_conselhos(
                            situacao_origem=doc_pafc.get_situacao_pafc_display(), decisao_motivo=doc_pafc.get_decisao_display()
                        )
                    elif doc_pafc.decisao == PAFC.DECISAO_REPROVAR:
                        if pafc.is_pafc_criacao():
                            pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSUP
                        else:
                            pafc.situacao = PAFC.REPROVADO
                    if doc_pafc.ad_referendum:
                        pafc.decisao_consepex = None
                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                    # TODO: notificar

                elif (
                    doc_pafc.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CONSEPEX
                    and tipo_documento == DocumentoHibrido.DESPACHO
                    and pafc.consepex_inexistente
                ):
                    pafc.situacao = PAFC.AGUARDANDO_APROVACAO_CONSUP
                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                    # TODO: notificar

                elif doc_pafc.situacao_pafc in [PAFC.AGUARDANDO_APROVACAO_CONSUP, PAFC.APROVADO] and tipo_documento == DocumentoHibrido.RESOLUCAO:
                    if doc_pafc.decisao == PAFC.DECISAO_APROVAR:
                        pafc.situacao = PAFC.APROVADO
                        if pafc.data_aprovacao is None:
                            pafc.data_aprovacao = doc_pafc.data_emissao
                    elif doc_pafc.decisao in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]:
                        if pafc.is_pafc_criacao() and doc_pafc.decisao == PAFC.DECISAO_APROVAR_RESSALVA:
                            if pafc.data_aprovacao is None:
                                pafc.data_aprovacao = doc_pafc.data_emissao
                        pafc.devolver_para_elaboracao_apartir_da_camara_ou_conselhos(
                            situacao_origem=doc_pafc.get_situacao_pafc_display(), decisao_motivo=doc_pafc.get_decisao_display()
                        )
                    elif doc_pafc.decisao == PAFC.DECISAO_REPROVAR:
                        pafc.situacao = PAFC.REPROVADO
                    if doc_pafc.ad_referendum:
                        pafc.decisao_consup = None
                    pafc.save()
                    MovimentacaoPAFC.registrar_movimentacao(None, pafc)
                    # TODO: notificar


class MembroComissaoPAFC(LogModel):
    FUNCAO_COORDENADOR = '1'
    FUNCAO_MEMBRO = '2'
    FUNCAO_CHOICES = [
        [FUNCAO_COORDENADOR, 'Coordenador'],
        [FUNCAO_MEMBRO, 'Membro'],
    ]

    PERMISSAO_LEITURA = '1'
    PERMISSAO_EDICAO = '2'
    PERMISSAO_CHOICES = [
        [PERMISSAO_LEITURA, 'Leitura'],
        [PERMISSAO_EDICAO, 'Edição'],
    ]

    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    funcao = models.CharFieldPlus(verbose_name='Função', null=False, blank=False, choices=FUNCAO_CHOICES, default=FUNCAO_MEMBRO)
    permissao = models.CharFieldPlus(verbose_name='Permissão', null=False, blank=False, choices=PERMISSAO_CHOICES, default=PERMISSAO_LEITURA)

    class Meta:
        verbose_name = 'Membro de Comissão'
        verbose_name_plural = 'Membros de Comissão'
        ordering = ['funcao', 'servidor__pessoa_fisica__nome']

    def __str__(self):
        return f'{self.servidor}'

    def save(self, *args, **kwargs):
        if self.funcao == MembroComissaoPAFC.FUNCAO_COORDENADOR:
            self.permissao = MembroComissaoPAFC.PERMISSAO_EDICAO
        super().save(*args, **kwargs)


class RevisorTecnicoPAFC(LogModel):
    FUNCAO_COORDENADOR = '1'
    FUNCAO_MEMBRO = '2'
    FUNCAO_CHOICES = [
        [FUNCAO_COORDENADOR, 'Coordenador'],
        [FUNCAO_MEMBRO, 'Membro'],
    ]

    PERMISSAO_LEITURA = '1'
    PERMISSAO_EDICAO = '2'
    PERMISSAO_CHOICES = [
        [PERMISSAO_LEITURA, 'Leitura'],
        [PERMISSAO_EDICAO, 'Edição'],
    ]

    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    funcao = models.CharFieldPlus(verbose_name='Função', null=False, blank=False, choices=FUNCAO_CHOICES, default=FUNCAO_MEMBRO)
    permissao = models.CharFieldPlus(verbose_name='Permissão', null=False, blank=False, choices=PERMISSAO_CHOICES, default=PERMISSAO_LEITURA)

    class Meta:
        verbose_name = 'Revisor Técnico'
        verbose_name_plural = 'Revisores Técnicos'
        ordering = ['funcao', 'servidor__pessoa_fisica__nome']

    def __str__(self):
        return f'{self.servidor}'

    def save(self, *args, **kwargs):
        if self.funcao == RevisorTecnicoPAFC.FUNCAO_COORDENADOR:
            self.permissao = RevisorTecnicoPAFC.PERMISSAO_EDICAO
        super().save(*args, **kwargs)


class ValidadorPAFC(LogModel):
    FUNCAO_COORDENADOR = '1'
    FUNCAO_MEMBRO = '2'
    FUNCAO_CHOICES = [
        [FUNCAO_COORDENADOR, 'Coordenador'],
        [FUNCAO_MEMBRO, 'Membro'],
    ]

    PERMISSAO_LEITURA = '1'
    PERMISSAO_EDICAO = '2'
    PERMISSAO_CHOICES = [
        [PERMISSAO_LEITURA, 'Leitura'],
        [PERMISSAO_EDICAO, 'Edição'],
    ]

    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC')
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    funcao = models.CharFieldPlus(verbose_name='Função', null=False, blank=False, choices=FUNCAO_CHOICES, default=FUNCAO_MEMBRO)
    permissao = models.CharFieldPlus(verbose_name='Permissão', null=False, blank=False, choices=PERMISSAO_CHOICES, default=PERMISSAO_LEITURA)

    class Meta:
        verbose_name = 'Validador'
        verbose_name_plural = 'Validadores'
        ordering = ['funcao', 'servidor__pessoa_fisica__nome']

    def __str__(self):
        return f'{self.servidor}'

    def save(self, *args, **kwargs):
        if self.funcao == ValidadorPAFC.FUNCAO_COORDENADOR:
            self.permissao = ValidadorPAFC.PERMISSAO_EDICAO
        super().save(*args, **kwargs)


class MatrizPAFC(LogModel):
    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC')
    matriz_ppc = models.ForeignKeyPlus('ppc.MatrizPPC', verbose_name='Matriz do PPC')

    class Meta:
        verbose_name = 'Matriz'
        verbose_name_plural = 'Matrizes'
        unique_together = ('pafc', 'matriz_ppc')
        ordering = ['pafc', 'matriz_ppc__nome']

    def __str__(self):
        return f'{self.matriz_ppc.nome}'

    def pode_excluir(self, user):
        if not self.pafc.pode_ser_elaborado() and self.pafc.ppc.matrizppc_set.count() > 1:
            return False
        return self.pafc.is_elaborador(user) and self.pafc.tem_permissao_edicao(user) or self.pafc.tem_permissao_administrador(user)


class SecaoPAFC(LogModel):
    titulo = models.CharFieldPlus('Título')
    ordem_exibicao = models.PositiveIntegerFieldPlus('Ordem de Exibição', default=1, min_value=1)
    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC')
    subsecao = models.BooleanField(
        'É subseção',
        default=False,
        editable=False,
        help_text='Marque esta opção caso este item deva ser exibido como uma subseção da primeira seção imediatamente acima não marcada como subseção.',
    )

    editor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Editor', null=True, blank=True, related_name='secoes_pafc_em_edicao')
    revisor_tecnico = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Revisor Técnico', null=True, blank=True, related_name='secoes_pafc_em_revisao_tecnica'
    )
    validador = models.ForeignKeyPlus('rh.Servidor', verbose_name='Validador', null=True, blank=True, related_name='secoes_pafc_em_validacao')

    data_conclusao_edicao = models.DateTimeFieldPlus(verbose_name='Data da Conclusão da Edição', null=True, blank=True)
    data_revisao_tecnica = models.DateTimeFieldPlus(verbose_name='Data da Revisão Técnica', null=True, blank=True)
    data_validacao = models.DateTimeFieldPlus(verbose_name='Data da Validação', null=True, blank=True)

    class Meta:
        verbose_name = 'Seção'
        verbose_name_plural = 'Seções'
        ordering = [
            'ordem_exibicao',
        ]

    def get_conteudos(self):
        return self.conteudopafc_set.order_by('ordem_exibicao')

    def save(self, *args, **kwargs):
        result = super().save(*args, **kwargs)
        SecaoPAFC.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        SecaoPAFC.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    def pode_ter_edicao_iniciada(self):
        return (
            self.pafc.situacao == PAFC.EM_ELABORACAO
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.DISPONIVEL_PARA_EDICAO).exists()
        )

    def pode_ter_edicao_liberada(self):
        return self.pafc.situacao == PAFC.EM_ELABORACAO and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_EDICAO).exists()

    def pode_ter_edicao_concluida(self):
        return self.pafc.situacao == PAFC.EM_ELABORACAO and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_EDICAO).exists()

    def pode_cancelar_conclusao_edicao(self):
        return (
            self.pafc.situacao == PAFC.EM_ELABORACAO
            and self.data_conclusao_edicao
            and self.conteudopafc_set.filter(
                editavel=True, situacao__in=[ConteudoPAFC.PRONTO_PARA_REVISAR, ConteudoPAFC.PRONTO_PARA_VALIDAR]
            ).exists()
        )

    @transaction.atomic
    def iniciar_edicao(self, user):
        self.editor = user.get_relacionamento()
        self.data_conclusao_edicao = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.DISPONIVEL_PARA_EDICAO).update(situacao=ConteudoPAFC.EM_EDICAO)

    @transaction.atomic
    def liberar_edicao(self, user):
        self.editor = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_EDICAO).update(situacao=ConteudoPAFC.DISPONIVEL_PARA_EDICAO)

    @transaction.atomic
    def concluir_edicao(self, user):
        veio_da_camara_ou_conselhos = any(
            decisao in [PAFC.DECISAO_APROVAR_RESSALVA, PAFC.DECISAO_SOLICITAR_CORRECAO]
            for decisao in (self.pafc.decisao_camara, self.pafc.decisao_consepex, self.pafc.decisao_consup)
        )
        if veio_da_camara_ou_conselhos or ComentarioRevisao.secao_possui_revisao(self, tipos=ComentarioRevisao.VALIDACAO):
            nova_situacao = ConteudoPAFC.PRONTO_PARA_VALIDAR
        else:
            nova_situacao = ConteudoPAFC.PRONTO_PARA_REVISAR
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_EDICAO).update(situacao=nova_situacao)
        self.data_conclusao_edicao = get_datetime_now()
        self.save()

    @transaction.atomic
    def cancelar_conclusao_edicao(self, user):
        self.conteudopafc_set.filter(editavel=True, situacao__in=[ConteudoPAFC.PRONTO_PARA_REVISAR, ConteudoPAFC.PRONTO_PARA_VALIDAR]).update(
            situacao=ConteudoPAFC.EM_EDICAO
        )
        self.data_conclusao_edicao = None
        self.save()

    def pode_ter_revisao_tecnica_iniciada(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_REVISAR).exists()
        )

    def pode_ter_revisao_tecnica_liberada(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_REVISAO).exists()
        )

    def pode_ter_revisao_tecnica_concluida(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_REVISAO).exists()
        )

    def pode_cancelar_conclusao_revisao_tecnica(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.data_revisao_tecnica
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR).exists()
        )

    @transaction.atomic
    def iniciar_revisao_tecnica(self, user):
        self.revisor_tecnico = user.get_relacionamento()
        self.data_revisao_tecnica = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_REVISAR).update(situacao=ConteudoPAFC.EM_REVISAO)

    @transaction.atomic
    def liberar_revisao_tecnica(self, user):
        self.revisor_tecnico = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_REVISAO).update(situacao=ConteudoPAFC.PRONTO_PARA_REVISAR)

    @transaction.atomic
    def concluir_revisao_tecnica(self, user):
        self.data_revisao_tecnica = get_datetime_now()
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_REVISAO).update(situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR)

    @transaction.atomic
    def marcar_como_revisada(self, user):
        self.iniciar_revisao_tecnica(user)
        self.concluir_revisao_tecnica(user)

    @transaction.atomic
    def cancelar_conclusao_revisao_tecnica(self, user):
        self.data_revisao_tecnica = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR).update(situacao=ConteudoPAFC.EM_REVISAO)

    def pode_ter_validacao_iniciada(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_VALIDACAO
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR).exists()
        )

    def pode_ter_validacao_liberada(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_VALIDACAO
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_VALIDACAO).exists()
        )

    def pode_ter_validacao_concluida(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_VALIDACAO
            and self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_VALIDACAO).exists()
        )

    def pode_cancelar_conclusao_validacao(self):
        return (
            self.pafc.situacao == PAFC.AGUARDANDO_VALIDACAO
            and self.data_validacao
            and not self.conteudopafc_set.filter(editavel=True).exclude(situacao=ConteudoPAFC.APROVADO).exists()
            and not self.pafc.parecer_validacao_ja_foi_emitido
        )

    @transaction.atomic
    def iniciar_validacao(self, user):
        self.validador = user.get_relacionamento()
        self.data_validacao = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR).update(situacao=ConteudoPAFC.EM_VALIDACAO)

    @transaction.atomic
    def liberar_validacao(self, user):
        self.validador = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_VALIDACAO).update(situacao=ConteudoPAFC.PRONTO_PARA_VALIDAR)

    @transaction.atomic
    def concluir_validacao(self, user):
        self.data_validacao = get_datetime_now()
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.EM_VALIDACAO).update(situacao=ConteudoPAFC.APROVADO)

    @transaction.atomic
    def marcar_como_validada(self, user):
        self.iniciar_validacao(user)
        self.concluir_validacao(user)

    @transaction.atomic
    def cancelar_conclusao_validacao(self, user):
        self.data_validacao = None
        self.save()
        self.conteudopafc_set.filter(editavel=True, situacao=ConteudoPAFC.APROVADO).update(situacao=ConteudoPAFC.EM_VALIDACAO)

    def possui_conteudo_editavel(self):
        return self.conteudopafc_set.filter(editavel=True).exists()

    def is_secao_bibliografia(self):
        return 'BIBLIOGRAFIA' in self.titulo.upper()

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(secao, delete=False):
        secoes = SecaoPAFC.objects.filter(pafc_id=secao.pafc_id)
        if delete:
            for seq, item in enumerate(secoes.exclude(id=secao.pk), start=1):
                if item.ordem_exibicao != seq:
                    SecaoPAFC.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = secao.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > secoes.count():
                atualizacao_ordem_exibicao = secoes.count()
            nova_ordem = list(secoes.exclude(id=secao.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, secao)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    SecaoPAFC.objects.filter(id=item.id).update(ordem_exibicao=seq)


class ConteudoPAFC(LogModel):
    DISPONIVEL_PARA_EDICAO = 1
    EM_EDICAO = 2
    PRONTO_PARA_REVISAR = 3
    EM_REVISAO = 4
    PRONTO_PARA_VALIDAR = 6
    EM_VALIDACAO = 7
    APROVADO = 9

    SITUACAO_CHOICES = [
        (DISPONIVEL_PARA_EDICAO, 'Disponível para edição'),
        (EM_EDICAO, 'Em edição'),
        (PRONTO_PARA_REVISAR, 'Pronto para revisar'),
        (EM_REVISAO, 'Em revisão'),
        (PRONTO_PARA_VALIDAR, 'Pronto para validar'),
        (EM_VALIDACAO, 'Em validação'),
        (APROVADO, 'Validado'),
    ]

    secao = models.ForeignKeyPlus(SecaoPAFC, verbose_name='Seção')
    texto = models.TextField('Texto', null=True, blank=True)
    ordem_exibicao = models.PositiveIntegerField('Ordem de Exibição')
    editavel = models.BooleanField('Editável', default=True)
    orientacao_preenchimento = models.TextField(
        'Orientação de Preenchimento',
        null=True,
        blank=True,
        help_text='Orientação de como o usuário deve preencher esse conteúdo na elaboração do PAFC.',
    )
    situacao = models.IntegerFieldPlus(verbose_name='Situacao', blank=False, choices=SITUACAO_CHOICES, default=DISPONIVEL_PARA_EDICAO)

    class Meta:
        verbose_name = 'Conteúdo'
        verbose_name_plural = 'Conteúdos'
        ordering = [
            'secao__ordem_exibicao',
            'ordem_exibicao',
        ]

    def save(self, *args, **kwargs):
        self.texto = Conteudo.normalizar_conteudo(self.texto)
        result = super().save(*args, **kwargs)
        ConteudoPAFC.recalcular_ordem(self)
        return result

    def delete(self, *args, **kwargs):
        ConteudoPAFC.recalcular_ordem(self, delete=True)
        return super().delete(*args, **kwargs)

    def em_situacao_espera(self):
        situacao_pafc = self.secao.pafc.situacao
        return (
            situacao_pafc == PAFC.EM_ELABORACAO
            and self.situacao == ConteudoPAFC.DISPONIVEL_PARA_EDICAO
            or situacao_pafc == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.situacao == ConteudoPAFC.PRONTO_PARA_REVISAR
            or situacao_pafc == PAFC.AGUARDANDO_VALIDACAO
            and self.situacao == ConteudoPAFC.PRONTO_PARA_VALIDAR
        )

    def em_situacao_concluido(self):
        situacao_pafc = self.secao.pafc.situacao
        return (
            self.situacao == ConteudoPAFC.APROVADO
            or situacao_pafc == PAFC.EM_ELABORACAO
            and self.situacao in [ConteudoPAFC.PRONTO_PARA_REVISAR, ConteudoPAFC.PRONTO_PARA_VALIDAR]
            or situacao_pafc == PAFC.AGUARDANDO_REVISAO_TECNICA
            and self.situacao == ConteudoPAFC.PRONTO_PARA_VALIDAR
        )

    def get_marcadores_invalidos(self):
        return ModeloPAFC.identificar_marcadores_invalidos(self.texto)

    @cached_property
    def requer_correcao_analise_preliminar(self):
        return self.comentarios_revisao.filter(tipo_revisao=ComentarioRevisao.ANALISE_PRELIMINAR, resolvido=False).exists()

    @cached_property
    def requer_correcao_revisao_tecnica(self):
        return self.comentarios_revisao.filter(tipo_revisao=ComentarioRevisao.REVISAO_TECNICA, resolvido=False).exists()

    @cached_property
    def requer_correcao_validacao(self):
        return self.comentarios_revisao.filter(tipo_revisao=ComentarioRevisao.VALIDACAO, resolvido=False).exists()

    @cached_property
    def requer_correcao(self):
        return self.requer_correcao_analise_preliminar or self.requer_correcao_revisao_tecnica or self.requer_correcao_validacao

    @cached_property
    def quebra_pagina_html(self):
        return Template('<div class="page-break"></div>').render(Context())

    def get_texto(self):
        texto = normalizar_formatacao(self.texto)

        for marcador in ModeloPAFC.identificar_marcadores_invalidos(texto, remover_tags_html=False):
            marcador_sem_chaves = re.sub(r'\{{2}\s*|\s*}{2}', '', marcador)
            texto = texto.replace(marcador, marcador_sem_chaves)

        contexto = {
            ModeloPAFC.MARCADOR_QUEBRA_PAGINA: self.quebra_pagina_html,
            ModeloPAFC.MARCADOR_CAMPUS: self.secao.pafc.get_nome_campus_normalizado(),
            ModeloPAFC.MARCADOR_ENDERECO_CAMPUS: f'{self.secao.pafc.setor.uo.endereco} - {self.secao.pafc.setor.uo.municipio}',
            ModeloPAFC.MARCADOR_NOME_CURSO: self.secao.pafc.nome_curso,
            ModeloPAFC.MARCADOR_RESOLUCAO_PPC_CRIACAO: self.secao.pafc.get_texto_resolucao_ppc_criacao(),
            ModeloPAFC.MARCADOR_TOTAL_VAGAS_ANUAIS: self.secao.pafc.numero_vagas_curso or '-',
            ModeloPAFC.MARCADOR_PERIODO_INICIO_OFERTA: self.secao.pafc.get_texto_inicio_oferta(),
            ModeloPAFC.MARCADOR_NOME_COORDENADOR: self.secao.pafc.coordenador_curso.pessoa_fisica.nome if self.secao.pafc.coordenador_curso else '-',
            ModeloPAFC.MARCADOR_MATRICULA_COORDENADOR: self.secao.pafc.coordenador_curso.matricula if self.secao.pafc.coordenador_curso else '-',
            ModeloPAFC.MARCADOR_TECNICOS_ADMINISTRATIVOS: self.secao.pafc.quadro_tecnicos_administrativos_html,
            ModeloPAFC.MARCADOR_DOCENTES: self.secao.pafc.quadro_docentes_html,
            ModeloPAFC.MARCADOR_LABORATORIOS: self.secao.pafc.quadro_laboratorios_html,
            ModeloPAFC.MARCADOR_MATRIZES: self.secao.pafc.quadro_matrizes_html,
            ModeloPAFC.MARCADOR_BIBLIOGRAFIA_BASICA: self.secao.pafc.quadro_bibliografia_basica_html,
            ModeloPAFC.MARCADOR_BIBLIOGRAFIA_COMPLEMENTAR: self.secao.pafc.quadro_bibliografia_complementar_html,
            ModeloPAFC.MARCADOR_POLOS: self.secao.pafc.quadro_polos_html,
            ModeloPAFC.MARCADOR_TUTORES: self.secao.pafc.quadro_tutores_html,
            ModeloPAFC.MARCADOR_PDTECS_TOPICOS_ESPECIFICOS: self.secao.pafc.topicos_especificos_html,
        }

        return substituir_marcadores(texto, contexto)

    def pode_ser_editado(self):
        return self.editavel and (
            self.situacao in [ConteudoPAFC.EM_EDICAO, ConteudoPAFC.EM_REVISAO, ConteudoPAFC.EM_VALIDACAO] or self.secao.pafc.em_analise_preliminar()
        )

    def pode_receber_observacao_analise_preliminar(self):
        return self.editavel and self.secao.pafc.situacao == PAFC.EM_ANALISE_PRELIMINAR

    def pode_receber_observacao_tecnica(self):
        return self.editavel and self.situacao == ConteudoPAFC.EM_REVISAO

    def pode_receber_observacao_final(self):
        return self.editavel and self.situacao == ConteudoPAFC.EM_VALIDACAO

    @staticmethod
    @transaction.atomic
    def recalcular_ordem(conteudo, delete=False):
        conteudos = ConteudoPAFC.objects.filter(secao_id=conteudo.secao_id)
        if delete:
            for seq, item in enumerate(conteudos.exclude(id=conteudo.pk), start=1):
                if item.ordem_exibicao != seq:
                    ConteudoPAFC.objects.filter(id=item.id).update(ordem_exibicao=seq)
        else:
            atualizacao_ordem_exibicao = conteudo.ordem_exibicao
            if atualizacao_ordem_exibicao < 1:
                atualizacao_ordem_exibicao = 1
            elif atualizacao_ordem_exibicao > conteudos.count():
                atualizacao_ordem_exibicao = conteudos.count()
            nova_ordem = list(conteudos.exclude(id=conteudo.id))
            nova_ordem.insert(atualizacao_ordem_exibicao - 1, conteudo)
            for seq, item in enumerate(nova_ordem, start=1):
                if item.ordem_exibicao != seq:
                    ConteudoPAFC.objects.filter(id=item.id).update(ordem_exibicao=seq)


class ComentarioRevisao(LogModel):
    ANALISE_PRELIMINAR = 3
    REVISAO_TECNICA = 1
    VALIDACAO = 2
    TIPO_REVISAO_CHOICES = [
        (ANALISE_PRELIMINAR, 'Análise Preliminar'),
        (REVISAO_TECNICA, 'Revisão Técnica'),
        (VALIDACAO, 'Validação'),
    ]

    conteudo = models.ForeignKeyPlus(ConteudoPAFC, related_name='comentarios_revisao')
    comentario = models.TextField('Comentário')
    tipo_revisao = models.IntegerFieldPlus(verbose_name='Tipo da revisão', choices=TIPO_REVISAO_CHOICES, default=ANALISE_PRELIMINAR)
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=True, blank=True, related_name='revisoes_feitas')
    data = models.DateTimeFieldPlus('Data/Hora', auto_now_add=True)

    resolvido = models.BooleanField('Resolvido', default=False)
    resolvido_por = models.ForeignKeyPlus('rh.Servidor', verbose_name='Resolvido por', null=True, blank=True, related_name='revisoes_resolvidas')
    data_resolucao = models.DateTimeFieldPlus('Data da resolução', null=True, blank=True)

    revisao_finalizada = models.BooleanField('Revisão finalizada', default=False)

    class Meta:
        verbose_name = 'Comentário da revisão'
        verbose_name_plural = 'Comentários da revisão'

    @staticmethod
    def pafc_possui_revisao(pafc, tipos=None, resolvido=None):
        qs_comentarios = ComentarioRevisao.objects.filter(conteudo__secao__pafc=pafc, revisao_finalizada=False)
        if tipos:
            if not isinstance(tipos, Iterable):
                tipos = [tipos]
            qs_comentarios = qs_comentarios.filter(tipo_revisao__in=tipos)
        if resolvido is not None:
            qs_comentarios = qs_comentarios.filter(resolvido=resolvido)
        return qs_comentarios.exists()

    @staticmethod
    def secao_possui_revisao(secao, tipos=None, resolvido=None):
        qs_comentarios = ComentarioRevisao.objects.filter(conteudo__secao=secao, revisao_finalizada=False)
        if tipos:
            if not isinstance(tipos, Iterable):
                tipos = [tipos]
            qs_comentarios = qs_comentarios.filter(tipo_revisao__in=tipos)
        if resolvido is not None:
            qs_comentarios = qs_comentarios.filter(resolvido=resolvido)
        return qs_comentarios.exists()


class ComentarioGeralPAFC(LogModel):
    ANALISE_PRELIMINAR = 3
    REVISAO_TECNICA = 1
    VALIDACAO = 2
    TIPO_REVISAO_CHOICES = [
        (ANALISE_PRELIMINAR, 'Análise Preliminar'),
        (REVISAO_TECNICA, 'Revisão Técnica'),
        (VALIDACAO, 'Validação'),
    ]

    ESCOPO_SERVIDORES = 1
    ESCOPO_INSTALACOES = 2
    ESCOPO_MATRIZES = 3
    ESCOPO_BIBLIOGRAFIA = 4
    ESCOPO_INFRAESTRUTURA_EAD = 5
    ESCOPO_CHOICES = [
        (ESCOPO_SERVIDORES, 'Servidores'),
        (ESCOPO_INSTALACOES, 'Instalações e Equipamentos'),
        (ESCOPO_MATRIZES, 'Matrizes'),
        (ESCOPO_BIBLIOGRAFIA, 'Bibliografia'),
        (ESCOPO_INFRAESTRUTURA_EAD, 'Infraestrutura EaD'),
    ]

    pafc = models.ForeignKeyPlus('pafc.PAFC', related_name='comentarios_gerais')
    comentario = models.TextField('Comentário')
    tipo_revisao = models.IntegerFieldPlus(verbose_name='Tipo da revisão', choices=TIPO_REVISAO_CHOICES, default=ANALISE_PRELIMINAR)
    escopo = models.IntegerFieldPlus(verbose_name='Escopo', choices=ESCOPO_CHOICES, default=ESCOPO_SERVIDORES)
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', null=True, blank=True, related_name='revisoes_gerais_feitas')
    data = models.DateTimeFieldPlus('Data/Hora', auto_now_add=True)

    resolvido = models.BooleanField('Resolvido', default=False)
    resolvido_por = models.ForeignKeyPlus(
        'rh.Servidor', verbose_name='Resolvido por', null=True, blank=True, related_name='revisoes_gerais_resolvidas'
    )
    data_resolucao = models.DateTimeFieldPlus('Data da resolução', null=True, blank=True)

    revisao_finalizada = models.BooleanField('Revisão finalizada', default=False)

    class Meta:
        verbose_name = 'Comentário da revisão'
        verbose_name_plural = 'Comentários da revisão'
        ordering = ('data',)

    @staticmethod
    def pafc_possui_comentario_geral(pafc, tipos=None, resolvido=None, escopo=None):
        qs_comentarios = pafc.comentarios_gerais.filter(revisao_finalizada=False)
        if tipos:
            if not isinstance(tipos, Iterable):
                tipos = [tipos]
            qs_comentarios = qs_comentarios.filter(tipo_revisao__in=tipos)
        if resolvido is not None:
            qs_comentarios = qs_comentarios.filter(resolvido=resolvido)
        if escopo in [escopo[0] for escopo in ComentarioGeralPAFC.ESCOPO_CHOICES]:
            qs_comentarios = qs_comentarios.filter(escopo=escopo)
        return qs_comentarios.exists()


class DisciplinaPAFC(LogModel):
    pafc = models.ForeignKeyPlus(PAFC, verbose_name='PAFC', related_name='disciplinas', null=False, blank=False)
    plano_disciplina = models.ForeignKeyPlus('ppc.PlanoDisciplina', verbose_name='Disciplina', null=False, blank=False)
    docentes = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Docentes', blank=True)
    justificativa_indisponibilidade_docentes = models.TextField(verbose_name='Justificativa de indisponibilidade de docentes', null=True, blank=True)

    class Meta:
        verbose_name = 'Disciplina do PAFC'
        verbose_name_plural = 'Disciplinas do PAFC'
        ordering = ['plano_disciplina__nome_disciplina']

    def __str__(self):
        return f'{self.plano_disciplina.nome_disciplina} - {self.plano_disciplina.ch_disciplina}h'


class InfraestruturaExternaPAFC(LogModel):
    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', related_name='infraestruturas_externas')
    campus = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name='Campus')
    comprovante_disponibilidade = models.ForeignKeyPlus(
        'pafc.DocumentoHibrido',
        verbose_name='Comprovante de disponibilidade',
        help_text='Documento que oficializa a disponibilização da infraestrutura do campus para uso pelo curso.',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
    )

    class Meta:
        verbose_name = 'Infraestrutura Externa do PAFC'
        verbose_name_plural = 'Infraestruturas Externas do PAFC'
        unique_together = ('pafc', 'campus')

    @cached_property
    def laboratorios(self):
        return self.pafc.salas.filter(Q(predio__uo=self.campus) | Q(predio__uo__equivalente=self.campus))

    @staticmethod
    def processar_mudancas_na_infraestrutura(pafc):
        campus_do_pafc = pafc.setor.uo

        ids_campi_vinculados_ao_pafc = set(
            pafc.salas.exclude(Q(predio__uo=campus_do_pafc) | Q(predio__uo__equivalente=campus_do_pafc)).values_list('predio__uo', flat=True)
        )

        ids_campi_mapeados_atualmente = {
            id_campus
            for id_campus in itertools.chain(*InfraestruturaExternaPAFC.objects.filter(pafc=pafc).values_list('campus', 'campus__equivalente'))
            if id_campus is not None
        }

        ids_novas_vinculacoes = ids_campi_vinculados_ao_pafc - ids_campi_mapeados_atualmente
        ids_campi_desvinculados = ids_campi_mapeados_atualmente - ids_campi_vinculados_ao_pafc

        # Criando novos mapeamentos de infraestrutura externa para os campi recém-adicionados ao PAFC
        InfraestruturaExternaPAFC.objects.bulk_create(
            [InfraestruturaExternaPAFC(pafc=pafc, campus_id=id_campus) for id_campus in ids_novas_vinculacoes]
        )

        # Removendo vinculação a campi que foram desvinculados do PAFC
        pafc.infraestruturas_externas.filter(campus_id__in=ids_campi_desvinculados).delete()


class PoloEadPAFC(LogModel):
    TIPO_SEDE = 1
    TIPO_OFERTA = 2
    TIPO_CHOICES = (
        (TIPO_SEDE, 'Unidade sede'),
        (TIPO_OFERTA, 'Polo de oferta'),
    )

    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', related_name='polos_ead')
    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo')
    tipo = models.PositiveSmallIntegerField('Tipo', choices=TIPO_CHOICES, default=TIPO_SEDE)
    vagas_ofertadas = models.PositiveIntegerFieldPlus(verbose_name='Vagas ofertadas', default=0)

    class Meta:
        verbose_name = 'Polo EaD'
        verbose_name_plural = 'Polos EaD'
        unique_together = ('pafc', 'polo')
        ordering = ['pafc', 'tipo', 'polo__descricao']

    def __str__(self):
        return f'{self.polo} - ({self.get_tipo_display()})'


class TutorMediadorEadPAFC(LogModel):
    MEDIADOR_PEDAGOGICO = 1
    TUTOR = 2
    TUTOR_E_MEDIADOR_PEDAGOGICO = 3
    CATEGORIA_CHOICES = (
        (MEDIADOR_PEDAGOGICO, 'Mediador pedagógico'),
        (TUTOR, 'Tutor'),
        (TUTOR_E_MEDIADOR_PEDAGOGICO, 'Tutor/Mediador pedagógico'),
    )
    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', related_name='tutores_ead')
    vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Vínculo')
    categoria = models.PositiveSmallIntegerField('Categoria', choices=CATEGORIA_CHOICES, default=MEDIADOR_PEDAGOGICO)

    class Meta:
        verbose_name = 'Tutor/mediador'
        verbose_name_plural = 'Tutores/mediadores'
        unique_together = ('pafc', 'vinculo')
        ordering = ('pafc', 'vinculo__pessoa__nome')

    def __str__(self):
        return f'{self.vinculo.pessoa} ({self.get_categoria_display()})'


class MovimentacaoPAFC(LogModel):
    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', null=False, blank=False)
    data = models.DateTimeFieldPlus('Data', auto_now_add=True)
    usuario = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Usuário', null=True, blank=False)
    situacao = models.CharFieldPlus(verbose_name='Situação', null=False, blank=False, choices=PAFC.SITUACAO_CHOICES)
    descricao = models.CharFieldPlus(verbose_name='Descrição', null=True, blank=True, default=None, max_length=255)
    eh_nova_situacao = models.BooleanField('Nova situação', default=False)

    class Meta:
        verbose_name = 'Movimentação de PAFC'
        verbose_name_plural = 'Movimentações de PAFC'

    def get_situacao_display(self):
        for situacao in PAFC.SITUACAO_CHOICES:
            if situacao[0] == int(self.situacao):
                return mark_safe(situacao[1])
        return mark_safe(PAFC.SITUACAO_CHOICES[0][1])

    @staticmethod
    def registrar_movimentacao(user, pafc, descricao: str | None = None):
        ultima_movimentacao = MovimentacaoPAFC.objects.filter(pafc=pafc).order_by('-data').first()
        eh_nova_situacao = ultima_movimentacao is None or ultima_movimentacao.situacao != str(pafc.situacao)
        if descricao is not None and len(descricao) > 255:
            descricao = f'{descricao[:250]}[...]'
        MovimentacaoPAFC.objects.create(
            pafc=pafc,
            usuario=user and user.get_vinculo(),
            situacao=pafc.situacao,
            descricao=descricao,
            eh_nova_situacao=eh_nova_situacao,
        )


class BibliografiaPAFC(LogModel):
    BIBLIOGRAFIA_BASICA = 1
    BIBLIOGRAFIA_COMPLEMENTAR = 2

    TIPO_BIBLIOGRAFIA_CHOICES = [
        (BIBLIOGRAFIA_BASICA, 'Bibliografia Básica'),
        (BIBLIOGRAFIA_COMPLEMENTAR, 'Bibliografia Complementar'),
    ]

    OBSERVACAO_A_ADQUIRIR = 1
    OBSERVACAO_EM_AQUISICAO = 2
    OBSERVACAO_RECURSO_DIGITAL = 3
    OBSERVACAO_OUTRA = 4

    OBSERVACAO_CHOICES = [
        (OBSERVACAO_A_ADQUIRIR, 'A adquirir'),
        (OBSERVACAO_EM_AQUISICAO, 'Em aquisição'),
        (OBSERVACAO_RECURSO_DIGITAL, 'Recurso digital disponível na Internet'),
        (OBSERVACAO_OUTRA, 'Outra (especificar)'),
    ]

    pafc = models.ForeignKeyPlus('pafc.PAFC', null=False, blank=False)
    tipo_bibliografia = models.PositiveIntegerFieldPlus('Tipo de bibliografia', choices=TIPO_BIBLIOGRAFIA_CHOICES)
    descricao = models.TextField('Descrição')
    chave_comparacao_descricao = models.TextField('Chave de comparação da descrição', editable=False)
    disciplinas = models.TextField('Disciplinas')
    quantidade_ideal = models.PositiveIntegerFieldPlus('Quantidade ideal', default=0)
    quantidade_no_campus = models.PositiveIntegerFieldPlus('Quantidade no campus', default=0)
    observacao = models.IntegerFieldPlus('Observação', choices=OBSERVACAO_CHOICES, null=True, blank=True)
    detalhes_observacao = models.CharFieldPlus('Detalhes da observação', null=True, blank=True)

    class Meta:
        verbose_name = 'Bibliografia do PAFC'
        verbose_name_plural = 'Bibliografias do PAFC'
        ordering = ['tipo_bibliografia', 'chave_comparacao_descricao']
        unique_together = ('pafc', 'tipo_bibliografia', 'chave_comparacao_descricao')

    def save(self, *args, **kwargs):
        self.descricao = re.sub(r'\s+', ' ', self.descricao).strip()
        self.chave_comparacao_descricao = BibliografiaPAFC.gerar_chave_comparacao_descricao(self.descricao)
        super().save(*args, **kwargs)

    def get_disciplinas_como_lista(self):
        return sorted(self.disciplinas.split('|')) if self.disciplinas.strip() else []

    def get_texto_quantitativo(self):
        observacao = self.get_observacao_display() if self.observacao != BibliografiaPAFC.OBSERVACAO_OUTRA else self.detalhes_observacao
        if observacao and self.quantidade_no_campus:
            return f'{self.quantidade_no_campus} - {observacao}'
        else:
            return self.quantidade_no_campus or observacao

    def remover_disciplina(self, disciplina: str, salvar=True):
        nova_lista_disciplinas = [d for d in self.get_disciplinas_como_lista() if d != disciplina]
        self.disciplinas = '|'.join(nova_lista_disciplinas)
        if salvar:
            self.save()

    def quantitativo_valido(self):
        return (
            self.quantidade_no_campus > 0
            or self.observacao
            in [
                BibliografiaPAFC.OBSERVACAO_A_ADQUIRIR,
                BibliografiaPAFC.OBSERVACAO_EM_AQUISICAO,
                BibliografiaPAFC.OBSERVACAO_RECURSO_DIGITAL,
            ]
            or self.observacao == BibliografiaPAFC.OBSERVACAO_OUTRA
            and self.detalhes_observacao
        )

    @staticmethod
    def quantitativos_foram_informados(pafc, tipo_bibliografia=None):
        qs_bibliografia = pafc.bibliografiapafc_set
        if tipo_bibliografia:
            qs_bibliografia = qs_bibliografia.filter(tipo_bibliografia=tipo_bibliografia)

        qs_bibliografia = qs_bibliografia.exclude(
            Q(quantidade_no_campus__gt=0)
            | Q(
                observacao__in=[
                    BibliografiaPAFC.OBSERVACAO_A_ADQUIRIR,
                    BibliografiaPAFC.OBSERVACAO_EM_AQUISICAO,
                    BibliografiaPAFC.OBSERVACAO_RECURSO_DIGITAL,
                ]
            )
            | Q(observacao=BibliografiaPAFC.OBSERVACAO_OUTRA, detalhes_observacao__isnull=False)
        )

        return not qs_bibliografia.exists()

    @staticmethod
    def gerar_chave_comparacao_descricao(descricao):
        if not descricao:
            return ''

        # Faz normalização unicode, incluindo decomposição de letras acentuadas ("é", p.ex., torna-se "e+acento").
        descricao = unicodedata.normalize('NFKD', descricao)

        # Remove acentuação
        descricao = ''.join(c for c in unicodedata.normalize('NFD', descricao) if unicodedata.category(c) != 'Mn')

        # Converte para minúsculas
        descricao = descricao.lower()

        # Remove pontuação e caracteres especiais
        descricao = re.sub(r'[^a-zA-Z0-9 ]', '', descricao)

        # Corrige espaços repetidos
        descricao = re.sub(r'\s+', ' ', descricao).strip()

        return descricao

    @classmethod
    def criar_ou_atualizar_dados_bibliograficos(cls, pafc: PAFC, tipo: int, descricao: str, lista_disciplinas: Iterable[str], quantidade_ideal: int):
        if tipo not in [t[0] for t in cls.TIPO_BIBLIOGRAFIA_CHOICES]:
            raise ValueError(f'Tipo de bibliografia inválido: {tipo}')
        criada = False
        atualizada = False

        descricao = re.sub(r'\s+', ' ', descricao).strip()
        chave_comparacao_descricao = cls.gerar_chave_comparacao_descricao(descricao)

        bibliografia = BibliografiaPAFC.objects.filter(
            pafc=pafc, tipo_bibliografia=tipo, chave_comparacao_descricao=chave_comparacao_descricao
        ).first()
        if bibliografia is None:
            bibliografia = BibliografiaPAFC(pafc=pafc, tipo_bibliografia=tipo)
            criada = True
        bibliografia.descricao = descricao

        valor_anterior_disciplinas = bibliografia.disciplinas
        for disciplina in lista_disciplinas:
            if disciplina not in bibliografia.get_disciplinas_como_lista():
                bibliografia.disciplinas = '|'.join(sorted([disciplina, *bibliografia.get_disciplinas_como_lista()]))
        if not criada and valor_anterior_disciplinas != bibliografia.disciplinas:
            atualizada = True

        bibliografia.quantidade_ideal = quantidade_ideal
        bibliografia.save()

        return criada, atualizada, bibliografia


class SolicitacaoTramitacaoAdReferendumPAFC(LogModel):
    pafc = models.ForeignKeyPlus('pafc.PAFC', verbose_name='PAFC', related_name='solicitacoes_tramitacao_ad_referendum')
    situacao_pafc = models.PositiveIntegerFieldPlus('Situação do PAFC', choices=PAFC.SITUACAO_CHOICES)
    justificativa = models.TextField('Justificativa')
    solicitante = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Solicitante', related_name='solicitacoesadreferendumpafc_como_solicitante')
    data_solicitacao = models.DateTimeFieldPlus('Data da solicitação', auto_now_add=True, editable=False)
    atendente = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Atendente', null=True, related_name='solicitacoesadreferendumpafc_como_atendente'
    )
    data_atendimento = models.DateTimeFieldPlus('Data de atendimento', null=True)
    deferida = models.BooleanFieldPlus('Deferida', null=True)
    motivo_indeferimento = models.TextField('Motivo do indeferimento', null=True, blank=False)

    class Meta:
        verbose_name = 'Solicitação de Tramitação Ad Referendum'
        verbose_name_plural = 'Solicitações de Tramitação Ad Referendum'
        ordering = ('-data_solicitacao',)

    def __str__(self):
        return f'Solicitação de Tramitação Ad Referendum #{self.id} (PAFC {self.pafc_id})'

    def get_absolute_url(self):
        return reverse('visualizar_solicitacaotramitacaoadreferendumpafc', args=(self.pk,))

    @property
    def situacao(self):
        if self.deferida is None:
            return 'Aguardando avaliação'
        return 'Deferida' if self.deferida else 'Indeferida'

    @staticmethod
    def usuario_pode_visualizar(user, obj=None):
        return (
            ProjetoPedagogicoCurso.is_presidente_conselho(user)
            or ProjetoPedagogicoCurso.is_secretario_conselho(user)
            or in_group(user, 'Administrador Acadêmico, Administrador de PAFC, Operador Sistêmico PAFC')
            or obj is not None
            and user.get_vinculo() in (obj.solicitante, obj.atendente)
        )

    def usuario_pode_avaliar(self, user):
        motivo_negativa = None
        if self.deferida is not None:
            motivo_negativa = 'solicitação já foi avaliada'
        if not ProjetoPedagogicoCurso.is_presidente_conselho(user):
            motivo_negativa = 'usuário não possui as permissões necessárias'
        return motivo_negativa is None, motivo_negativa

    @cached_property
    def sumario_de_documentos(self):
        situacoes_relevantes = [
            PAFC.AGUARDANDO_VALIDACAO,
            PAFC.EM_ANALISE_PROREITORIA,
            PAFC.AGUARDANDO_APROVACAO_CAMARA,
        ]
        if self.situacao_pafc == PAFC.AGUARDANDO_APROVACAO_CONSUP:
            situacoes_relevantes.append(PAFC.AGUARDANDO_APROVACAO_CONSEPEX)

        return list(
            self.pafc.documentos_emitidos.prefetch_related('documento')
            .filter(
                situacao_pafc__in=situacoes_relevantes,
                data_emissao=Subquery(
                    self.pafc.documentos_emitidos.filter(situacao_pafc=OuterRef('situacao_pafc'))
                    .order_by('-data_emissao')
                    .values_list('data_emissao', flat=True)[:1]
                ),
            )
            .annotate(
                descricao=Case(
                    When(situacao_pafc=PAFC.AGUARDANDO_VALIDACAO, then=Value('Parecer da Validação')),
                    When(situacao_pafc=PAFC.EM_ANALISE_PROREITORIA, then=Value('Parecer da Pró-Reitoria')),
                    When(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CAMARA, then=Value('Parecer da Câmara')),
                    When(
                        Q(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX, documento__tipo=DocumentoHibrido.ATA),
                        then=Value('Ata da reunião do Consepex'),
                    ),
                    When(
                        Q(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX, documento__tipo=DocumentoHibrido.DELIBERACAO),
                        then=Value('Deliberação do Consepex'),
                    ),
                ),
                ordem=Case(
                    When(situacao_pafc=PAFC.AGUARDANDO_VALIDACAO, then=Value('1')),
                    When(situacao_pafc=PAFC.EM_ANALISE_PROREITORIA, then=Value('2')),
                    When(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CAMARA, then=Value('3')),
                    When(situacao_pafc=PAFC.AGUARDANDO_APROVACAO_CONSEPEX, then=Value('4')),
                ),
            )
            .order_by('ordem')
            .distinct()
        )

    def resolver_solicitacao(self, atendente, deferir, motivo_indeferimento=None):
        if self.deferida is not None:
            raise ValueError('A solicitação já foi avaliada.')
        if not deferir and not motivo_indeferimento:
            raise ValueError('O motivo do indeferimento não foi informado.')
        self.deferida = deferir
        self.motivo_indeferimento = motivo_indeferimento
        self.atendente = atendente
        self.data_atendimento = get_datetime_now()
        self.save()
        self.notificar_solicitante_sobre_atendimento()

    def notificar_solicitante_sobre_atendimento(self):
        if self.deferida is not None:
            url_pafc = f'{settings.SITE_URL}{self.pafc.get_absolute_url()}'
            url_solicitacao = f'{settings.SITE_URL}{self.get_absolute_url()}'
            titulo = '[SUAP] PAFC: Solicitação de tramitação Ad Referendum analisada'
            mensagem = f"""<h1>Solicitação de tramitação Ad Referendum analisada</h1>
                <p>Prezado(a) {self.solicitante.nome},</p>
                <p>Informamos que sua solicitação de tramitação Ad Referendum para o <a href="{url_pafc}">PAFC {self.pafc}</a>,
                   que estava sob análise, foi <strong>{self.situacao.upper()}</strong>.</p>
                {f'<p>O indeferimento se deu pelo seguinte motivo:</p> <blockquote>{self.motivo_indeferimento}</blockquote>' if self.motivo_indeferimento else ''}
                <p>O atendimento foi realizado por {self.atendente.nome} em {format_(self.data_atendimento)}.</p>
                <p class="more-info">Para mais informações, acesse: <a href="{url_solicitacao}">{url_solicitacao}</a>.</p>"""
            vinculos = [self.solicitante]
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)


class PlanoDisciplinaModificado(LogModel):
    EM_ELABORACAO = 10
    ELABORACAO_CONCLUIDA = 20
    EM_ANALISE_PRELIMINAR = 30
    ANALISE_PRELIMINAR_CONCLUIDA = 40
    EM_REVISAO_TECNICA = 50
    REVISAO_TECNICA_CONCLUIDA = 60
    EM_VALIDACAO = 70
    VALIDADO = 80

    SITUACAO_CHOICES = [
        (EM_ELABORACAO, 'Em elaboração'),
        (ELABORACAO_CONCLUIDA, 'Elaboração concluída'),
        (EM_ANALISE_PRELIMINAR, 'Em análise preliminar'),
        (ANALISE_PRELIMINAR_CONCLUIDA, 'Análise preliminar concluída'),
        (EM_REVISAO_TECNICA, 'Em revisão técnica'),
        (REVISAO_TECNICA_CONCLUIDA, 'Revisão técnica concluída'),
        (EM_VALIDACAO, 'Em validação'),
        (VALIDADO, 'Validado'),
    ]

    pafc = models.ForeignKeyPlus('pafc.PAFC', related_name='planos_disciplina_modificados')
    plano_referencia = models.ForeignKeyPlus('ppc.PlanoDisciplina', related_name='versoes_em_pomcs')
    ementa = models.TextField('Ementa')
    edicao_ementa_concluida = models.BooleanField('Edição da ementa concluída', default=False)

    situacao = models.PositiveSmallIntegerField('Situação', choices=SITUACAO_CHOICES, default=EM_ELABORACAO)

    class Meta:
        verbose_name = 'Plano de Disciplina'
        verbose_name_plural = 'Planos de Disciplina'

    def __str__(self):
        return f'Plano da disciplina {self.nome_disciplina}'

    def get_absolute_url(self):
        return reverse('visualizar_planodisciplina_pafc', kwargs={'pk': self.pk})

    @property
    def nome_disciplina(self):
        return self.plano_referencia.nome_disciplina

    @property
    def curso(self):
        return self.pafc.curso

    def em_elaboracao(self):
        return self.situacao == self.EM_ELABORACAO

    @cached_property
    def progresso_elaboracao(self):
        parcial, total = self.secoes_programa.aggregate(
            qtd_concluidas=Count(Case(When(edicao_concluida=True, then=1))) + Value(1 if self.edicao_ementa_concluida else 0),
            total=Count('id') + Value(1),
        ).values()
        return f'{parcial}/{total}'

    def elaborado(self):
        return self.em_situacao_conclusiva

    def em_analise_preliminar(self):
        return self.situacao == self.EM_ANALISE_PRELIMINAR

    def em_revisao_tecnica(self):
        return self.situacao == self.EM_REVISAO_TECNICA

    def em_validacao(self):
        return self.situacao == self.EM_VALIDACAO

    @property
    def em_situacao_conclusiva(self):
        return self.situacao in [
            PlanoDisciplinaModificado.ELABORACAO_CONCLUIDA,
            PlanoDisciplinaModificado.ANALISE_PRELIMINAR_CONCLUIDA,
            PlanoDisciplinaModificado.REVISAO_TECNICA_CONCLUIDA,
            PlanoDisciplinaModificado.VALIDADO,
        ]

    def get_secoes(self):
        return self.secoes_programa.filter(versao_ead=False)

    def get_secoes_ead(self):
        return self.secoes_programa.filter(versao_ead=True)

    @cached_property
    def possui_versao_ead(self):
        return self.secoes_programa.filter(versao_ead=True).exists()

    @cached_property
    def possui_pendencias_da_elaboracao(self):
        return not self.edicao_ementa_concluida or self.secoes_programa.filter(edicao_concluida=False).exists() or self.possui_revisoes_nao_resolvidas

    @cached_property
    def possui_revisoes_nao_resolvidas(self):
        return RevisaoPlanoDisciplinaModificado.possui_revisoes_nao_resolvidas(self.pafc, self)

    @cached_property
    def possui_comentarios_da_revisao_tecnica(self):
        return RevisaoPlanoDisciplinaModificado.possui_revisoes_nao_resolvidas(
            self.pafc, self, tipos=RevisaoPlanoDisciplinaModificado.REVISAO_TECNICA
        )

    @cached_property
    def possui_comentarios_da_validacao(self):
        return RevisaoPlanoDisciplinaModificado.possui_revisoes_nao_resolvidas(self.pafc, self, tipos=RevisaoPlanoDisciplinaModificado.VALIDACAO)

    def get_secoes_impressao(self, versao_ead=False):
        if versao_ead and self.possui_versao_ead:
            return self.get_secoes_ead()
        return self.get_secoes()

    def pode_elaborar(self, user):
        return self.pafc.pode_ser_elaborado() and self.pafc.pode_elaborar(user)

    def pode_revisar(self, user):
        return (
            self.pafc.is_revisor_tecnico(user)
            and self.pafc.em_revisao_tecnica()
            or self.pafc.is_validador(user)
            and (self.pafc.em_analise_preliminar() or self.pafc.em_validacao())
        )

    def elaboracao_pode_ser_concluida(self):
        return (
            self.pafc.pode_ser_elaborado() and self.situacao == PlanoDisciplinaModificado.EM_ELABORACAO and not self.possui_pendencias_da_elaboracao
        )

    def elaboracao_pode_ser_retomada(self):
        return self.pafc.pode_ser_elaborado() and self.em_situacao_conclusiva

    def pode_receber_revisao(self):
        if not (self.em_analise_preliminar() or self.em_revisao_tecnica() or self.em_validacao()):
            return False

        return self.situacao == self.get_situacao_inicial_correspondente(self.pafc.situacao)

    @classmethod
    def revisao_pode_ser_realizada_em_massa(cls, pafc: PAFC):
        if not (pafc.em_analise_preliminar() or pafc.em_validacao()):
            return False
        return cls.objects.filter(situacao=cls.get_situacao_inicial_correspondente(pafc.situacao)).exists()

    def revisao_pode_ser_concluida(self):
        return self.pode_receber_revisao()

    def revisao_pode_ser_retomada(self):
        return (
            self.pafc.em_analise_preliminar()
            and self.situacao == PlanoDisciplinaModificado.ANALISE_PRELIMINAR_CONCLUIDA
            or self.pafc.em_revisao_tecnica()
            and self.situacao == PlanoDisciplinaModificado.REVISAO_TECNICA_CONCLUIDA
            or self.pafc.em_validacao()
            and self.situacao == PlanoDisciplinaModificado.VALIDADO
        )

    @transaction.atomic
    def concluir_elaboracao(self, user):
        self.situacao = PlanoDisciplinaModificado.ELABORACAO_CONCLUIDA
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self.pafc, f'Elaboração do plano de disciplina "{self.nome_disciplina}" concluída.')

        # Atualizando bibliografia com dados preenchidos no plano de disciplina
        criadas, atualizadas, removidas = self.pafc.incorporar_bibliografia_do_plano_disciplina(self)
        resumo = (
            f'{criadas} registros criado{pluralize(criadas)}, '
            f'{atualizadas} atualizado{pluralize(atualizadas)}, '
            f'{removidas} removido{pluralize(removidas)}'
        )
        MovimentacaoPAFC.registrar_movimentacao(user, self.pafc, f'Bibliografia atualizada com dados do {self} ({resumo}).')

    @transaction.atomic
    def retomar_elaboracao(self, user):
        self.situacao = PlanoDisciplinaModificado.EM_ELABORACAO
        self.save()
        MovimentacaoPAFC.registrar_movimentacao(user, self.pafc, f'Elaboração retomada para o plano de disciplina "{self.nome_disciplina}".')

    @transaction.atomic
    def concluir_revisao(self, user):
        if self.pafc.situacao in [PAFC.EM_ANALISE_PRELIMINAR, PAFC.AGUARDANDO_REVISAO_TECNICA, PAFC.AGUARDANDO_VALIDACAO]:
            self.situacao = PlanoDisciplinaModificado.get_situacao_terminal_correspondente(self.pafc.situacao)
            self.save()
            MovimentacaoPAFC.registrar_movimentacao(user, self.pafc, f'Revisão do plano de disciplina "{self.nome_disciplina}" concluída.')

    @classmethod
    def concluir_revisao_em_massa(cls, pafc, user):
        if pafc.situacao in [PAFC.EM_ANALISE_PRELIMINAR, PAFC.AGUARDANDO_REVISAO_TECNICA, PAFC.AGUARDANDO_VALIDACAO]:
            situacao_correspondente = cls.get_situacao_inicial_correspondente(pafc.situacao)
            with transaction.atomic():
                for plano in pafc.planos_disciplina_modificados.filter(situacao=situacao_correspondente):
                    if plano.pode_revisar(user) and plano.revisao_pode_ser_concluida():
                        plano.concluir_revisao(user)

    @transaction.atomic
    def retomar_revisao(self, user):
        if self.pafc.situacao in [PAFC.EM_ANALISE_PRELIMINAR, PAFC.AGUARDANDO_REVISAO_TECNICA, PAFC.AGUARDANDO_VALIDACAO]:
            self.situacao = PlanoDisciplinaModificado.get_situacao_inicial_correspondente(self.pafc.situacao)
            self.save()
            MovimentacaoPAFC.registrar_movimentacao(user, self.pafc, f'Revisão retomada para o plano de disciplina "{self.nome_disciplina}".')

    @classmethod
    def get_situacao_inicial_correspondente(cls, situacao_pafc):
        return {
            PAFC.EM_ELABORACAO: cls.EM_ELABORACAO,
            PAFC.EM_ANALISE_PRELIMINAR: cls.EM_ANALISE_PRELIMINAR,
            PAFC.AGUARDANDO_REVISAO_TECNICA: cls.EM_REVISAO_TECNICA,
            PAFC.AGUARDANDO_VALIDACAO: cls.EM_VALIDACAO,
        }.get(situacao_pafc)

    @classmethod
    def get_situacao_terminal_correspondente(cls, situacao_pafc):
        return {
            PAFC.EM_ELABORACAO: cls.ELABORACAO_CONCLUIDA,
            PAFC.EM_ANALISE_PRELIMINAR: cls.ANALISE_PRELIMINAR_CONCLUIDA,
            PAFC.AGUARDANDO_REVISAO_TECNICA: cls.REVISAO_TECNICA_CONCLUIDA,
            PAFC.AGUARDANDO_VALIDACAO: cls.VALIDADO,
        }.get(situacao_pafc)

    @classmethod
    def processar_envio_do_pafc_para_revisao(cls, pafc, situacao_destino_pafc):
        tipo_revisao = RevisaoPlanoDisciplinaModificado.get_tipo_de_revisao_correspondente(pafc.situacao)
        ids_das_revisoes_e_planos_disciplina = list(
            RevisaoPlanoDisciplinaModificado.get_revisoes(pafc, tipos=tipo_revisao).values_list('id', 'plano_disciplina_id')
        )
        if ids_das_revisoes_e_planos_disciplina:
            ids_revisoes = {id_revisao for id_revisao, _ in ids_das_revisoes_e_planos_disciplina}
            id_planos = {id_plano for _, id_plano in ids_das_revisoes_e_planos_disciplina}
            RevisaoPlanoDisciplinaModificado.objects.filter(pk__in=ids_revisoes).update(revisao_finalizada=True)
            nova_situacao_dos_planos_revisados = cls.get_situacao_terminal_correspondente(situacao_destino_pafc)

            pafc.planos_disciplina_modificados.filter(pk__in=id_planos).update(situacao=nova_situacao_dos_planos_revisados)

        # Atualiza situações do fluxo padrão
        situacoes_dos_planos_a_atualizar = [cls.get_situacao_terminal_correspondente(pafc.situacao)]
        # A análise preliminar dos planos é opcional,
        # então planos em situação inicial e terminal da análise preliminar serão enviados para revisão.
        if pafc.em_analise_preliminar():
            situacoes_dos_planos_a_atualizar.append(cls.get_situacao_inicial_correspondente(pafc.situacao))
        nova_situacao_dos_planos = cls.get_situacao_inicial_correspondente(situacao_destino_pafc)

        pafc.planos_disciplina_modificados.filter(situacao__in=situacoes_dos_planos_a_atualizar).update(situacao=nova_situacao_dos_planos)

    @classmethod
    def processar_devolucao_do_pafc_para_elaboracao(cls, pafc):
        # Devolução das etapas de revisão
        if pafc.em_analise_preliminar() or pafc.em_revisao_tecnica() or pafc.em_validacao():
            nova_situacao_dos_planos = cls.get_situacao_terminal_correspondente(pafc.situacao)

            tipo_revisao = RevisaoPlanoDisciplinaModificado.get_tipo_de_revisao_correspondente(pafc.situacao)
            ids_planos = RevisaoPlanoDisciplinaModificado.get_revisoes(pafc, tipos=tipo_revisao, resolvidas=False).values_list(
                'plano_disciplina_id', flat=True
            )
            pafc.planos_disciplina_modificados.filter(id__in=ids_planos).update(situacao=nova_situacao_dos_planos)

        # Devolução da Câmara ou dos Conselhos
        elif pafc.em_aprovacao_camara() or pafc.em_aprovacao_conselhos():
            # Nada a fazer por enquanto
            pass


class SecaoProgramaPlanoDisciplinaModificado(LogModel):
    plano_disciplina = models.ForeignKeyPlus('pafc.PlanoDisciplinaModificado', related_name='secoes_programa')
    modelo_secao = models.ForeignKeyPlus('ppc.ModeloSecaoPlanoDisciplina')
    texto = models.TextField('Texto', default='', blank=False)
    versao_ead = models.BooleanFieldPlus('Versão EAD')

    edicao_concluida = models.BooleanField('Edição concluída', default=False)

    class Meta:
        verbose_name = 'Seção de Plano de Disciplina'
        verbose_name_plural = 'Seções de Plano de Disciplina'
        unique_together = ('plano_disciplina', 'modelo_secao', 'versao_ead')
        ordering = ('modelo_secao__ordem_exibicao',)

    @property
    def titulo(self):
        return self.modelo_secao.titulo

    @property
    def ordem_exibicao(self):
        return self.modelo_secao.ordem_exibicao


class PlanoDisciplinaPOMC(LogModel):
    plano_disciplina_ppc = models.ForeignKeyPlus('ppc.PlanoDisciplinaPPC', related_name='versoes_em_pomcs')
    plano_disciplina_modificado = models.ForeignKeyPlus('pafc.PlanoDisciplinaModificado', related_name='planos_disciplina_pomc')

    class Meta:
        verbose_name = 'Plano de Disciplina do POMC'
        verbose_name_plural = 'Planos de Disciplina do POMC'

    def __str__(self):
        return f'Plano da disciplina {self.plano_disciplina_modificado.nome_disciplina}'

    def clean(self):
        super().clean()
        if self.plano_disciplina_ppc.plano_disciplina != self.plano_disciplina_modificado.plano_referencia:
            raise ValidationError('Correspondência incorreta entre Plano de Disciplina do PPC e Plano de Disciplina do POMC')

    def get_absolute_url(self):
        return reverse('visualizar_planodisciplinapomc', kwargs={'pk': self.pk})

    def get_secoes_plano_disciplina_impressao(self):
        versao_ead = self.plano_disciplina_ppc.qtd_aulas_ead > 0
        return self.plano_disciplina_modificado.get_secoes_impressao(versao_ead)


class RevisaoPlanoDisciplinaModificado(LogModel):
    ANALISE_PRELIMINAR = 1
    REVISAO_TECNICA = 5
    VALIDACAO = 10
    TIPO_REVISAO_CHOICES = [
        (ANALISE_PRELIMINAR, 'Análise Preliminar'),
        (REVISAO_TECNICA, 'Revisão Técnica'),
        (VALIDACAO, 'Validação'),
    ]

    plano_disciplina = models.ForeignKeyPlus(PlanoDisciplinaModificado, related_name='revisoes')
    comentario = models.TextField('Comentário')
    tipo_revisao = models.IntegerFieldPlus(verbose_name='Tipo da revisão', choices=TIPO_REVISAO_CHOICES, default=ANALISE_PRELIMINAR)
    revisor = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Servidor', null=True, blank=True, related_name='revisoes_planos_disciplina_pafc')
    data = models.DateTimeFieldPlus('Data/Hora', auto_now_add=True)

    resolvida = models.BooleanField('Resolvida', default=False)
    resolvida_por = models.ForeignKeyPlus(
        'comum.Vinculo', verbose_name='Resolvida por', null=True, blank=True, related_name='revisoes_resolvidas_planos_disciplina_pafc'
    )
    data_resolucao = models.DateTimeFieldPlus('Data da resolução', null=True, blank=True)

    revisao_finalizada = models.BooleanField('Revisão finalizada', default=False)

    class Meta:
        verbose_name = 'Revisão de plano de disciplina'
        verbose_name_plural = 'Revisões de plano de disciplina'

    def can_delete(self, user):
        return not self.resolvida and self.revisor == user.get_vinculo() and self.plano_disciplina.pode_receber_revisao()

    def pode_resolver(self, user):
        return not self.resolvida and self.plano_disciplina.pode_elaborar(user)

    @classmethod
    def get_tipo_de_revisao_correspondente(cls, situacao_pafc):
        return {
            PAFC.EM_ANALISE_PRELIMINAR: cls.ANALISE_PRELIMINAR,
            PAFC.AGUARDANDO_REVISAO_TECNICA: cls.REVISAO_TECNICA,
            PAFC.AGUARDANDO_VALIDACAO: cls.VALIDACAO,
        }.get(situacao_pafc)

    @classmethod
    def get_revisoes(cls, pafc, planos_disciplinas=None, tipos=None, resolvidas=None):
        qs_revisoes = cls.objects.filter(plano_disciplina__pafc=pafc, revisao_finalizada=False)
        if planos_disciplinas:
            if not isinstance(planos_disciplinas, Iterable):
                planos_disciplinas = [planos_disciplinas]
            qs_revisoes = qs_revisoes.filter(plano_disciplina__in=planos_disciplinas)
        if tipos:
            if not isinstance(tipos, Iterable):
                tipos = [tipos]
            qs_revisoes = qs_revisoes.filter(tipo_revisao__in=tipos)
        if resolvidas is not None:
            qs_revisoes = qs_revisoes.filter(resolvida=resolvidas)
        return qs_revisoes

    @classmethod
    def possui_revisoes(cls, pafc, planos_disciplinas=None, tipos=None, resolvidas=None):
        return cls.get_revisoes(pafc, resolvidas=resolvidas, planos_disciplinas=planos_disciplinas, tipos=tipos).exists()

    @classmethod
    def possui_revisoes_nao_resolvidas(cls, pafc, planos_disciplinas=None, tipos=None):
        return cls.possui_revisoes(pafc, resolvidas=False, planos_disciplinas=planos_disciplinas, tipos=tipos)
