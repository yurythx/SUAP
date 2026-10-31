from __future__ import annotations

import binascii
import copy
import datetime
import logging
import math
import operator
import os
import re
import tempfile
import uuid
from collections import OrderedDict, defaultdict
from collections.abc import Iterable
from decimal import Decimal
from random import choice

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.core.exceptions import ValidationError
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import F, Max, ProtectedError, Q
from django.db.models.aggregates import Min, Sum
from django.db.models.functions import Upper
from django.db.transaction import atomic
from django.utils.functional import cached_property
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception

from comum.models import Ano, APIExterna, Configuracao, EmailBlockList, User, Vinculo
from comum.utils import tl
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.middleware.threadlocals import get_app_context
from djtools.storages import get_overwrite_storage
from djtools.templatetags.filters import format_iterable
from djtools.thumbs import ImageWithThumbsField
from djtools.utils import (
    diferenca_listas,
    get_ldap_conf,
    insert_space,
    mask_ch_componente,
    mask_nota,
    normalizar_nome_proprio,
    somar_dias,
    sync_ldap_user,
)
from edu import perms
from edu.managers import (
    AlunoLocalManager,
    AlunoManager,
    AlunosAtivosManager,
    AlunosCaracterizadosManager,
    AlunosComMatrizManager,
    AlunosNaoFICManager,
    FiltroUnidadeOrganizacionalManager,
)
from edu.models.atividades import AtividadeCurricularExtensao, AtividadePraticaProfissional
from edu.models.atividades_complementares import ItemConfiguracaoAtividadeComplementar
from edu.models.cadastros_gerais import (
    PERIODO_LETIVO_CHOICES,
    FormaIngresso,
    Modalidade,
    NaturezaParticipacao,
    NivelEnsino,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoAtividadeComplementar,
    TipoNEE,
    Turno,
)
from edu.models.cursos import Componente, ComponenteCurricular, CursoCampus, EstruturaCurso, MatrizCurso
from edu.models.diarios import Aula, Diario, Falta, ItemConfiguracaoAvaliacao
from edu.models.diarios_especiais import CreditoEspecial
from edu.models.diplomas import AssinaturaDigital, AssinaturaEletronica, RegistroEmissaoDiploma
from edu.models.diretorias import Diretoria
from edu.models.enade import ConvocacaoENADE, RegistroConvocacaoENADE
from edu.models.estagio_docente import EstagioDocente
from edu.models.eventos import ColacaoGrau, ParticipanteEvento
from edu.models.historico import (
    RegistroHistorico,
    AproveitamentoEstudo,
    CertificacaoConhecimento,
    FrequenciaPraticaProfissional,
    MatriculaDiario,
    MatriculaDiarioResumida,
    MatriculaPeriodo,
)
from edu.models.logs import LogModel
from edu.models.procedimentos import AproveitamentoComponente, PedidoMatricula, PedidoMatriculaDiario, ProcedimentoMatricula, ProcedimentoReducaoCH
from edu.models.projeto_final import AssinaturaAtaEletronica, ProjetoFinal
from edu.models.turmas import Turma, ParticipanteTurmaMinicurso
from rh.models import AbstractRelacionamento, PessoaInfoComplementar

logger = logging.getLogger(__name__)


class SequencialMatricula(ModelPlus):
    prefixo = models.CharFieldPlus(max_length=255)
    contador = models.PositiveIntegerField()

    @staticmethod
    def proximo_numero(prefixo):
        qs_sequencial = SequencialMatricula.objects.filter(prefixo=prefixo)
        if qs_sequencial.exists():
            sequencial = qs_sequencial[0]
            contador = sequencial.contador
        else:
            sequencial = SequencialMatricula()
            sequencial.prefixo = prefixo
            contador = 1
        sequencial.contador = contador + 1
        sequencial.save()
        numero = f'000000000{contador}'
        matricula = f'{prefixo}{numero[-4:]}'
        if Aluno.objects.filter(matricula=matricula).exists():
            return SequencialMatricula.proximo_numero(prefixo)
        else:
            return matricula


class Observacao(LogModel):
    observacao = models.TextField('Observação da Matrícula')
    aluno = models.ForeignKeyPlus('edu.Aluno', verbose_name='Aluno')
    data = models.DateFieldPlus(verbose_name='Data')
    usuario = models.ForeignKeyPlus('comum.User', verbose_name='Usuário')

    class Meta:
        permissions = (('adm_delete_observacao', 'Pode deletar observações de outros usuários'),)


class Aluno(LogModel, AbstractRelacionamento):
    SEARCH_FIELDS = ['pessoa_fisica__search_fields_optimized', 'matricula']

    EMPTY_CHOICES = [['', '----']]
    PERIODO_LETIVO_CHOICES = PERIODO_LETIVO_CHOICES
    ESTADO_CIVIL_CHOICES = [
        ['Solteiro', 'Solteiro'],
        ['Casado', 'Casado'],
        ['União Estável', 'União Estável'],
        ['Divorciado', 'Divorciado'],
        ['Viúvo', 'Viúvo'],
    ]
    PARENTESCO_CHOICES = [
        ['Pai/Mãe', 'Pai/Mãe'],
        ['Avô/Avó', 'Avô/Avó'],
        ['Tio/Tia', 'Tio/Tia'],
        ['Sobrinho/Sobrinha', 'Sobrinho/Sobrinha'],
        ['Outro', 'Outro'],
    ]
    TIPO_ZONA_RESIDENCIAL_CHOICES = [['1', 'Urbana'], ['2', 'Rural']]
    TIPO_SANGUINEO_CHOICES = [['O-', 'O-'], ['O+', 'O+'], ['A-', 'A-'], ['A+', 'A+'], ['B-', 'B-'], ['B+', 'B+'], ['AB-', 'AB-'], ['AB+', 'AB+']]
    TIPO_NACIONALIDADE_CHOICES = [
        ['Brasileira', 'Brasileira'],
        ['Brasileira - Nascido no exterior ou naturalizado', 'Brasileira - Nascido no exterior ou naturalizado'],
        ['Estrangeira', 'Estrangeira'],
    ]
    TIPO_INSTITUICAO_ORIGEM_CHOICES = [['Pública', 'Pública'], ['Privada', 'Privada']]
    TIPO_CERTIDAO_CHOICES = [['1', 'Nascimento'], ['2', 'Casamento']]
    COTA_SISTEC_CHOICES = [
        ['1', 'Escola Pública'],
        ['2', 'Cor/Raça'],
        ['3', 'Olimpíada'],
        ['4', 'Indígena'],
        ['5', 'Necessidades Especiais'],
        ['6', 'Zona Rural'],
        ['7', 'Quilombola'],
        ['8', 'Assentamento'],
        ['9', 'Não se aplica'],
    ]
    COTA_MEC_CHOICES = [
        ['1', 'Seleção Geral'],
        ['2', 'Oriundo de escola pública, com renda superior a 1,5 S.M. e declarado preto, pardo ou indígena (PPI)'],
        ['3', 'Oriundo de escola pública, com renda superior a 1,5 S.M., não declarado PPI'],
        ['4', 'Oriundo de escola pública, com renda inferior a 1,5 S.M., declarado PPI'],
        ['5', 'Oriundo de escola pública, com renda inferior a 1,5 S.M., não declarado PPI'],
        ['0', 'Não se aplica'],
    ]
    TIPO_ALUNO_CHOICES = [['Regular', 'Regular'], ['Especial', 'Especial']]

    # TODO: demanda1564 apagar constantes
    DEFICIENCIA_VISUAL = '1'
    DEFICIENCIA_VISUAL_TOTAL = '11'
    DEFICIENCIA_VISUAL_MONOCULAR = '111'
    DEFICIENCIA_AUDITIVA = '2'
    DEFICIENCIA_AUDITIVA_TOTAL = '22'
    DEFICIENCIA_AUDITIVA_VISUAL_TOTAL = '222'
    DEFICIENCIA_FISICA = '3'
    DEFICIENCIA_MENTAL = '4'
    DEFICIENCIA_MULTIPLA = '5'
    OUTRAS_CONDICOES = '8'
    TIPO_NECESSIDADE_ESPECIAL_CHOICES = [
        [DEFICIENCIA_VISUAL, 'Baixa Visão'],
        [DEFICIENCIA_VISUAL_MONOCULAR, 'Visão monocular'],
        [DEFICIENCIA_VISUAL_TOTAL, 'Cegueira'],
        [DEFICIENCIA_AUDITIVA, 'Deficiência Auditiva'],
        [DEFICIENCIA_FISICA, 'Deficiência Física'],
        [DEFICIENCIA_MENTAL, 'Deficiência Intelectual'],
        [DEFICIENCIA_MULTIPLA, 'Deficiência Múltipla'],
        [DEFICIENCIA_AUDITIVA_TOTAL, 'Surdez'],
        [DEFICIENCIA_AUDITIVA_VISUAL_TOTAL, 'Surdocegueira'],
    ]

    AUTISMO_INFANTIL = '1'
    SINDROME_ASPERGER = '2'
    SINDROME_DE_RETT = '3'
    TRANSTORNO_DESINTEGRATIVO_DA_INFANCIA = '4'
    TDAH = '5'
    DISLEXIA = '6'
    TIPO_TRANSTORNO_CHOICES = [
        [AUTISMO_INFANTIL, 'Autismo'],
        [SINDROME_ASPERGER, 'Síndrome de Asperger'],
        [SINDROME_DE_RETT, 'Síndrome de Rett'],
        [TRANSTORNO_DESINTEGRATIVO_DA_INFANCIA, 'Transtorno Desintegrativo da Infância'],
        [TDAH, 'Transtorno do Déficit de Atenção com Hiperatividade'],
        [DISLEXIA, 'Dislexia'],
    ]

    MUNICIPAL = '1'
    ESTADUAL = '2'
    PODER_PUBLICO_RESPONSAVEL_TRANSPORTE_CHOICES = [[MUNICIPAL, 'Municipal'], [ESTADUAL, 'Estadual']]

    VANS_WV = '1'
    KOMBI_MICRO_ONIBUS = '2'
    ONIBUS = '3'
    BICICLETA = '4'
    TRACAO_ANIMAL = '5'
    OUTRO_VEICULO_RODOVIARIO = '6'
    AQUAVIARIO_ATE_5 = '7'
    AQUAVIARIO_ENTRE_5_A_15 = '8'
    AQUALVIARIO_ENTRE_15_E_35 = '9'
    AQUAVIARIO_ACIMA_DE_35 = '10'
    TREM = '11'
    TIPO_VEICULO_CHOICES_FOR_FORM = [
        [
            'Rodoviário',
            [
                [VANS_WV, 'Vans/WV'],
                [KOMBI_MICRO_ONIBUS, 'Kombi Micro-Ônibus'],
                [ONIBUS, 'Ônibus'],
                [BICICLETA, 'Bicicleta'],
                [TRACAO_ANIMAL, 'Tração Animal'],
                [OUTRO_VEICULO_RODOVIARIO, 'Outro tipo de veículo rodoviário'],
            ],
        ],
        [
            'Aquaviário',
            [
                [AQUAVIARIO_ATE_5, 'Capacidade de até 5 alunos'],
                [AQUAVIARIO_ENTRE_5_A_15, 'Capacidade entre 5 a 15 alunos'],
                [AQUALVIARIO_ENTRE_15_E_35, 'Capacidade entre 15 e 35 alunos'],
                [AQUAVIARIO_ACIMA_DE_35, 'Capacidade acima de 35 alunos'],
            ],
        ],
        ['Ferroviário', [[TREM, 'Trem/Metrô']]],
    ]

    TIPO_VEICULO_CHOICES = [
        [VANS_WV, 'Vans/WV'],
        [KOMBI_MICRO_ONIBUS, 'Kombi Micro-Ônibus'],
        [ONIBUS, 'Ônibus'],
        [BICICLETA, 'Bicicleta'],
        [TRACAO_ANIMAL, 'Tração Animal'],
        [OUTRO_VEICULO_RODOVIARIO, 'Outro tipo de veículo rodoviário'],
        [AQUAVIARIO_ATE_5, 'Capacidade de até 5 alunos'],
        [AQUAVIARIO_ENTRE_5_A_15, 'Capacidade entre 5 a 15 alunos'],
        [AQUALVIARIO_ENTRE_15_E_35, 'Capacidade entre 15 e 35 alunos'],
        [AQUAVIARIO_ACIMA_DE_35, 'Capacidade acima de 35 alunos'],
        [TREM, 'Trem/Metrô'],
    ]

    # TODO: demanda1564 -> remover
    SUPERDOTADO = '1'
    SUPERDOTACAO_CHOICES = [[SUPERDOTADO, 'Altas habilidades/Superdotação']]

    ORDENAR_HISTORICO_POR_PERIODO_LETIVO = 1
    ORDENAR_HISTORICO_POR_PERIODO_MATRIZ = 2
    ORDENAR_HISTORICO_POR_COMPONENTE = 3

    # Managers
    objects = AlunoManager()
    locals = AlunoLocalManager()
    com_matriz = AlunosComMatrizManager()
    ativos = AlunosAtivosManager()
    caracterizados = AlunosCaracterizadosManager()
    nao_fic = AlunosNaoFICManager()
    locals_uo = FiltroUnidadeOrganizacionalManager('curso_campus__diretoria__setor__uo')
    locals_diretoria = FiltroUnidadeOrganizacionalManager('curso_campus__diretoria')

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    # Fields
    codigo_academico = models.IntegerField(null=True, db_index=True)
    codigo_sgp = models.IntegerField(null=True, db_index=True, blank=True)
    codigo_academico_pf = models.IntegerField('Cód. Acadêmico Pessoa Física', null=True)
    matricula = models.CharFieldPlus('Matrícula', max_length=255, db_index=True)
    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(), use_id_for_name=True, upload_to='alunos', sizes=((75, 100), (150, 200)), null=True, blank=True
    )
    estado_civil = models.CharFieldPlus(choices=ESTADO_CIVIL_CHOICES, null=True)
    numero_dependentes = models.PositiveIntegerFieldPlus('Número de Dependentes', null=True)

    # endereco
    logradouro = models.CharFieldPlus(max_length=255, verbose_name='Logradouro', null=True)
    numero = models.CharFieldPlus(max_length=255, verbose_name='Número', null=True)
    complemento = models.CharFieldPlus(max_length=255, verbose_name='Complemento', null=True, blank=True)
    bairro = models.CharFieldPlus(max_length=255, verbose_name='Bairro', null=True)
    cep = models.CharFieldPlus(max_length=255, verbose_name='CEP', null=True, blank=True)
    cidade = models.ForeignKeyPlus('edu.Cidade', verbose_name='Cidade', null=True)
    tipo_zona_residencial = models.CharFieldPlus(choices=TIPO_ZONA_RESIDENCIAL_CHOICES, verbose_name='Zona Residencial', null=True, blank=False)

    # endereco profissional
    logradouro_profissional = models.CharFieldPlus(max_length=255, verbose_name='Logradouro Profissional', null=True, blank=True)
    numero_profissional = models.CharFieldPlus(max_length=255, verbose_name='Número Profissional', null=True, blank=True)
    complemento_profissional = models.CharFieldPlus(max_length=255, verbose_name='Complemento Profissional', null=True, blank=True)
    bairro_profissional = models.CharFieldPlus(max_length=255, verbose_name='Bairro Profissional', null=True, blank=True)
    cep_profissional = models.CharFieldPlus(max_length=255, verbose_name='CEP Profissional', null=True, blank=True)
    cidade_profissional = models.ForeignKeyPlus(
        'edu.Cidade', verbose_name='Cidade Profissional', null=True, related_name='aluno_cidade_profissional_set'
    )
    tipo_zona_residencial_profissional = models.CharFieldPlus(
        choices=TIPO_ZONA_RESIDENCIAL_CHOICES, verbose_name='Zona Residencial Profissional', null=True, blank=True
    )
    telefone_profissional = models.CharFieldPlus(max_length=255, verbose_name='Telefone Profissional', null=True, blank=True)

    # dados familiares
    nome_pai = models.CharFieldPlus(max_length=255, verbose_name='Nome do Pai', null=True, blank=True)
    estado_civil_pai = models.CharFieldPlus(choices=ESTADO_CIVIL_CHOICES, null=True, blank=True)
    pai_falecido = models.BooleanField(verbose_name='Pai é falecido?', default=False)
    nome_mae = models.CharFieldPlus(max_length=255, verbose_name='Nome da Mãe', null=True, blank=False)
    estado_civil_mae = models.CharFieldPlus(choices=ESTADO_CIVIL_CHOICES, null=True, blank=True)
    mae_falecida = models.BooleanField(verbose_name='Mãe é falecida?', default=False)
    responsavel = models.CharFieldPlus(max_length=255, verbose_name='Nome do Responsável', null=True, blank=True)
    email_responsavel = models.CharFieldPlus(max_length=255, verbose_name='Email do Responsável', null=True, blank=True)
    parentesco_responsavel = models.CharFieldPlus(verbose_name='Parentesco do Responsável', choices=PARENTESCO_CHOICES, null=True, blank=True)
    cpf_responsavel = models.BrCpfField(verbose_name='CPF do Responsável', null=True, blank=True)
    token_responsavel = models.CharFieldPlus(verbose_name='Token de acesso do responsável', null=True, blank=True, max_length=255)
    autorizacao_carteira_estudantil = models.BooleanField(
        verbose_name='Autorização para Emissão da Carteira Estudantil',
        help_text='O aluno autoriza o envio de seus dados pessoais para o Sistema Brasileiro de Educação (SEB) para fins de emissão da carteira de estudante digital de acordo com a Medida Provisória Nº 895, de 6 de setembro de 2019',
        default=False,
    )

    # contato
    telefone_principal = models.CharFieldPlus(max_length=255, verbose_name='Telefone Principal', null=True, blank=True)
    telefone_secundario = models.CharFieldPlus(max_length=255, verbose_name='Telefone Secundário', null=True, blank=True)
    telefone_adicional_1 = models.CharFieldPlus(max_length=255, verbose_name='Telefone do Responsável', null=True, blank=True)
    telefone_adicional_2 = models.CharFieldPlus(max_length=255, verbose_name='Telefone do Responsável', null=True, blank=True)
    facebook = models.URLField('Facebook', blank=True, null=True)
    instagram = models.URLField('Instagram', blank=True, null=True)
    twitter = models.URLField('Twitter', blank=True, null=True)
    linkedin = models.URLField('Linkedin', blank=True, null=True)
    skype = models.CharFieldPlus('Skype', blank=True, null=True)

    # outras informacoes
    tipo_sanguineo = models.CharFieldPlus(max_length=255, verbose_name='Tipo Sanguíneo', null=True, blank=True, choices=TIPO_SANGUINEO_CHOICES)
    nacionalidade = models.CharFieldPlus(max_length=255, verbose_name='Nacionalidade', null=True, choices=TIPO_NACIONALIDADE_CHOICES)
    passaporte = models.CharFieldPlus(max_length=50, verbose_name='Nº do Passaporte', default='')
    pais_origem = models.ForeignKeyPlus('edu.Pais', verbose_name='País de Origem', null=True, blank=True, help_text='Obrigatório para estrangeiros')
    naturalidade = models.ForeignKeyPlus(
        'edu.Cidade',
        verbose_name='Naturalidade',
        null=True,
        blank=True,
        related_name='aluno_naturalidade_set',
        help_text='Cidade em que o aluno nasceu. Obrigatório para brasileiros.',
    )
    estrangeiro_sem_passaporte = models.BooleanField(verbose_name='É estrangeiro sem passaporte', default=False)

    # NEEs
    deficiencias = models.ManyToManyFieldPlus('edu.Deficiencia', verbose_name='Deficiências', blank=True)
    outras_nees = models.ManyToManyFieldPlus('edu.TipoNEE', verbose_name='Outros tipos de NEEs', blank=True)

    # TODO demanda1564 remover campo
    tipo_necessidade_especial = models.CharFieldPlus(
        verbose_name='Tipo de Necessidade Especial', null=True, blank=True, choices=TIPO_NECESSIDADE_ESPECIAL_CHOICES
    )
    # TODO demanda1564 remover campo
    tipo_transtorno = models.CharFieldPlus(verbose_name='Tipo de Transtorno', null=True, blank=True, choices=TIPO_TRANSTORNO_CHOICES)
    # TODO demanda1564 remover campo
    superdotacao = models.CharFieldPlus(verbose_name='Superdotação', null=True, blank=True, choices=SUPERDOTACAO_CHOICES)

    # dados escolares
    nivel_ensino_anterior = models.ForeignKeyPlus('edu.NivelEnsino', null=True, blank=True, on_delete=models.CASCADE)
    tipo_instituicao_origem = models.CharFieldPlus(
        max_length=255, verbose_name='Tipo de Instituição', null=True, choices=TIPO_INSTITUICAO_ORIGEM_CHOICES, blank=True
    )
    nome_instituicao_anterior = models.CharFieldPlus(max_length=255, verbose_name='Nome da Instituição', null=True, blank=True)
    ano_conclusao_estudo_anterior = models.ForeignKeyPlus(
        Ano, verbose_name='Ano de Conclusão', null=True, related_name='aluno_ano_conclusao_set', blank=True, on_delete=models.CASCADE
    )
    habilitacao_pedagogica = models.CharFieldPlus(max_length=255, verbose_name='Habilitação para Curso de Formação Pedagógica', null=True, blank=True)

    # rg
    numero_rg = models.CharFieldPlus(max_length=255, verbose_name='Número do RG', null=True, blank=True)
    uf_emissao_rg = models.ForeignKeyPlus('edu.Estado', verbose_name='Estado Emissor', null=True, blank=True, related_name='aluno_emissor_rg_set')
    orgao_emissao_rg = models.ForeignKeyPlus('edu.OrgaoEmissorRg', verbose_name='Orgão Emissor', null=True, blank=True)
    data_emissao_rg = models.DateFieldPlus(verbose_name='Data de Emissão', null=True, blank=True)

    # titulo_eleitor
    numero_titulo_eleitor = models.CharFieldPlus(max_length=255, verbose_name='Título de Eleitor', null=True, blank=True)
    zona_titulo_eleitor = models.CharFieldPlus(max_length=255, verbose_name='Zona', null=True, blank=True)
    secao = models.CharFieldPlus(max_length=255, verbose_name='Seção', null=True, blank=True)
    data_emissao_titulo_eleitor = models.DateFieldPlus(verbose_name='Data de Emissão', null=True, blank=True)
    uf_emissao_titulo_eleitor = models.ForeignKeyPlus(
        'edu.Estado', verbose_name='Estado Emissor', null=True, blank=True, related_name='aluno_emissor_titulo_eleitor_set', on_delete=models.CASCADE
    )
    # carteira de reservista
    numero_carteira_reservista = models.CharFieldPlus(max_length=255, verbose_name='Número da Carteira de Reservista', null=True, blank=True)
    regiao_carteira_reservista = models.CharFieldPlus(max_length=255, verbose_name='Região', null=True, blank=True)
    serie_carteira_reservista = models.CharFieldPlus(max_length=255, verbose_name='Série', null=True, blank=True)
    estado_emissao_carteira_reservista = models.ForeignKeyPlus(
        'edu.Estado',
        verbose_name='Estado Emissor',
        null=True,
        blank=True,
        related_name='aluno_emissor_carteira_reservista_set',
        on_delete=models.CASCADE,
    )
    ano_carteira_reservista = models.PositiveIntegerField(verbose_name='Ano', null=True, blank=True)
    # certidao_civil
    tipo_certidao = models.CharFieldPlus(max_length=255, verbose_name='Tipo de Certidão', null=True, blank=True, choices=TIPO_CERTIDAO_CHOICES)
    cartorio = models.ForeignKeyPlus('edu.Cartorio', verbose_name='Cartório', null=True, blank=True)
    numero_certidao = models.CharFieldPlus(max_length=255, verbose_name='Número de Termo', null=True, blank=True)
    folha_certidao = models.CharFieldPlus(max_length=255, verbose_name='Folha', null=True, blank=True)
    livro_certidao = models.CharFieldPlus(max_length=255, verbose_name='Livro', null=True, blank=True)
    data_emissao_certidao = models.DateFieldPlus(verbose_name='Data de Emissão', null=True, blank=True)
    matricula_certidao = models.CharFieldPlus(max_length=255, verbose_name='Matrícula', null=True, blank=True)

    # dados da matrícula
    ano_letivo = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano de Ingresso', on_delete=models.CASCADE)
    periodo_letivo = models.PositiveIntegerField(verbose_name='Período de Ingresso', choices=PERIODO_LETIVO_CHOICES)
    data_matricula = models.DateTimeFieldPlus(verbose_name='Data da Matrícula', auto_now_add=True)

    turno = models.ForeignKeyPlus('edu.Turno', verbose_name='Turno', null=True, on_delete=models.CASCADE)
    forma_ingresso = models.ForeignKeyPlus('edu.FormaIngresso', null=True, verbose_name='Forma de Ingresso', on_delete=models.CASCADE)
    convenio_internacional = models.ForeignKeyPlus(
        'convenios.convenio',
        verbose_name='Convênio Internacional',
        null=True,
        blank=True,
        limit_choices_to={'tipo__descricao': 'Relações Internacionais'},
    )
    cota_sistec = models.CharFieldPlus(max_length=255, verbose_name='Cota SISTEC', null=True, choices=COTA_SISTEC_CHOICES, blank=True)
    cota_mec = models.CharFieldPlus(max_length=255, verbose_name='Cota MEC', null=True, choices=COTA_MEC_CHOICES, blank=True)
    possui_convenio = models.BooleanField(verbose_name='Possui Convênio', null=True)
    convenio = models.ForeignKeyPlus('edu.Convenio', null=True, blank=True, verbose_name='Convênio', on_delete=models.CASCADE)
    data_conclusao_intercambio = models.DateFieldPlus(verbose_name='Conclusão do Intercâmbio', null=True, blank=True)
    curso_campus = models.ForeignKeyPlus('edu.CursoCampus', null=True, verbose_name='Curso')
    habilitacao = models.ForeignKeyPlus('edu.Habilitacao', verbose_name='Habilitação', null=True, blank=True)
    matriz = models.ForeignKeyPlus('edu.Matriz', null=True, verbose_name='Matriz')
    situacao = models.ForeignKeyPlus('edu.SituacaoMatricula', verbose_name='Situação', on_delete=models.CASCADE)
    numero_pasta = models.CharFieldPlus(max_length=255, verbose_name='Número da Pasta', null=True, blank=True)
    linha_pesquisa = models.ForeignKeyPlus('edu.LinhaPesquisa', verbose_name='Linha de Pesquisa', null=True, blank=True)
    aluno_especial = models.BooleanField(verbose_name='Aluno Especial?', default=False)

    ira = models.DecimalFieldPlus(verbose_name='I.R.A', default=0, null=True)
    dt_conclusao_curso = models.DateField(null=True, blank=True, verbose_name='Data de Conclusão do Curso')
    data_expedicao_diploma = models.DateField(null=True, blank=True, verbose_name='Data de Expedição do Diploma')
    data_colacao_grau = models.DateField(null=True, blank=True, verbose_name='Data da Colação de Grau')
    ano_let_prev_conclusao = models.IntegerField(null=True, blank=True, verbose_name='Ano Prev. Conclusão')
    ano_conclusao = models.IntegerField(null=True, blank=True, verbose_name='Ano Conclusão')
    renda_per_capita = models.DecimalField(
        null=True,
        max_digits=15,
        decimal_places=2,
        verbose_name='Renda Per Capita',
        help_text='Número de salários mínimos ganhos pelos integrantes da família dividido pelo número de integrantes',
    )

    candidato_vaga = models.ForeignKeyPlus('processo_seletivo.CandidatoVaga', verbose_name='Candidato Vaga', null=True, blank=True)
    periodo_atual = models.IntegerField('Período Atual', null=True, blank=True)

    observacao_historico = models.TextField('Observação para o Histórico', null=True, blank=True)
    observacao_matricula = models.TextField('Observação da Matrícula', null=True, blank=True)

    polo = models.ForeignKeyPlus('edu.Polo', verbose_name='Polo EAD', null=True, blank=True, on_delete=models.CASCADE)

    comp_obrigatorios_pendentes = models.BooleanField(default=False)
    comp_optativos_pendentes = models.BooleanField(default=False)
    comp_eletivos_pendentes = models.BooleanField(default=False)
    pratica_profissional_pendente = models.BooleanField(default=False)
    seminarios_pendentes = models.BooleanField(default=False)
    atividades_complementares_pendentes = models.BooleanField(default=False)
    tcc_pendente = models.BooleanField(default=False)
    enade_pendente = models.BooleanField(default=False)
    colacao_grau_pendente = models.BooleanField(default=False)

    data_integralizacao = models.DateTimeFieldPlus('Data da Integralização', null=True, blank=True)
    ano_letivo_integralizacao = models.ForeignKeyPlus(
        'comum.Ano',
        verbose_name='Ano Letivo da Integralização',
        null=True,
        blank=True,
        related_name='aluno_ano_letivo_integralizacao',
        on_delete=models.CASCADE,
    )
    periodo_letivo_integralizacao = models.PositiveIntegerField(
        verbose_name='Periodo Letivo da Integralização', choices=PERIODO_LETIVO_CHOICES, null=True, blank=True
    )

    email_qacademico = models.EmailField('Email Q-Acadêmico', blank=True)
    alterado_em = models.DateTimeFieldPlus('Data de Alteração', auto_now=True, null=True, blank=True)

    csf = models.BooleanField(verbose_name='Ciência sem Fronteiras', default=False)

    # atividades estudantis
    documentada = models.BooleanField('Documentação Entregue', default=False)
    data_documentacao = models.DateTimeField('Data de Entrega da Documentação', null=True)
    documentacao_invalidada = models.BooleanField('Documentação invalidada', default=False)
    documentacao_invalidada_em = models.DateTimeField('Invalidade em', null=True)
    documentacao_invalidada_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Invalidada por', related_name='documentacao_invalida_por', null=True, on_delete=models.SET_NULL
    )

    # pendencias
    pendencia_tcc = models.BooleanField(verbose_name='Registro de TCC', null=True)
    pendencia_enade = models.BooleanField(verbose_name='Registro do ENADE', null=True)
    pendencia_pratica_profissional = models.BooleanField(verbose_name='Registro de Prática Profissional', null=True)
    pendencia_colacao_grau = models.BooleanField(verbose_name='Colação de Grau', null=True)
    pendencia_ch_atividade_complementar = models.BooleanField(verbose_name='Atividades Complementares', null=True)
    pendencia_ch_tcc = models.BooleanField(verbose_name='Caga-Horária de TCC', null=True)
    pendencia_ch_pratica_profissional = models.BooleanField(verbose_name='Caga-Horária de Prática Profissional', null=True)
    pendencia_ch_atividades_aprofundamento = models.BooleanField(verbose_name='Caga-Horária de Aprofundamento', null=True)
    pendencia_ch_atividades_extensao = models.BooleanField(verbose_name='Caga-Horária de Extensão', null=True)
    pendencia_ch_seminario = models.BooleanField(verbose_name='Caga-Horária de Seminário', null=True)
    pendencia_ch_eletiva = models.BooleanField(verbose_name='Caga-Horária Eletiva', null=True)
    pendencia_ch_optativa = models.BooleanField(verbose_name='Caga-Horária Optativa', null=True)
    pendencia_ch_obrigatoria = models.BooleanField(verbose_name='Caga-Horária Obrigatória', null=True)
    pendencia_ch_pratica_como_componente = models.BooleanField(verbose_name='Carga Horária Prática como Componente Curricular', null=True)
    pendencia_ch_visita_tecnica = models.BooleanField(verbose_name='Carga Horária Visita Técnica/Aula de Campo', null=True)

    # Integralização do Ensino Médio
    integralizou_ensino_medio = models.BooleanField(verbose_name='Integralizou Ensino Médio', default=False)
    obs_integralizacao_ensino_medio = models.TextField(
        verbose_name='Observação da Integralização Ensino Médio',
        null=True,
        help_text='O texto informado será exibido no histórico escolar de conclusão de ensino médio do aluno.',
    )

    # CH de prática como componente curricular e visita/técnica de aulas registradas em diários
    ch_aulas_pcc = models.IntegerField(verbose_name='CH de Aulas de PCC', default=0, help_text='Prática como componente curricular')
    ch_aulas_visita_tecnica = models.IntegerField(verbose_name='CH de Aulas de VT/AC', default=0, help_text='Visita técnica / aula de campo')

    # saúde
    cartao_sus = models.CharFieldPlus('Cartão SUS', null=True, blank=True)

    codigo_educacenso = models.CharFieldPlus('Código EDUCACENSO', null=True, blank=True)

    # SISTEC
    codigo_sistec = models.CharFieldPlus('Código SISTEC', null=True, blank=True)
    data_inicio_ciclo = models.DateFieldPlus(verbose_name='Data de início do ciclo', null=True, blank=True)
    data_prevista_termino_ciclo = models.DateFieldPlus(verbose_name='Data prevista de término do ciclo', null=True, blank=True)

    nis = models.CharFieldPlus('NIS', null=True, help_text='Número de Identificação Social', blank=True)

    poder_publico_responsavel_transporte = models.CharFieldPlus(
        'Poder Público Responsável pelo Transporte Escolar', choices=PODER_PUBLICO_RESPONSAVEL_TRANSPORTE_CHOICES, null=True, blank=True
    )
    tipo_veiculo = models.CharFieldPlus(
        'Tipo de Veículo Utilizado no Transporte Escolar', choices=TIPO_VEICULO_CHOICES_FOR_FORM, null=True, blank=True
    )

    percentual_ch_cumprida = models.DecimalFieldPlus('C.H. Cumprida (%)', null=True)
    ultima_operacao = models.CharFieldPlus('Última operação', null=True, blank=True)

    # Dados de Orientação
    orientador = models.ForeignKeyPlus('edu.Professor', related_name='alunos_orientados', verbose_name='Orientador', null=True, blank=True)
    coorientadores = models.ManyToManyFieldPlus('comum.Vinculo', related_name='alunos_coorientados', verbose_name='Coorientadores', blank=True)
    titulo_projeto_pesquisa = models.CharFieldPlus('Título do Projeto de Pesquisa', null=True, blank=True)

    class Meta:
        ordering = ('pessoa_fisica__nome',)
        verbose_name = 'Aluno'
        verbose_name_plural = 'Alunos'
        # Índice em Meta (e não db_index=True) para a migration poder usar AddIndexConcurrently.
        # O trigram em UPPER(matricula) atende o icontains da matrícula no autocomplete (#17813).
        indexes = [
            models.Index(fields=['codigo_academico_pf'], name='edu_aluno_codigo_acad_pf_idx'),
            GinIndex(OpClass(Upper('matricula'), name='gin_trgm_ops'), name='edu_aluno_matricula_trgm'),
        ]

        permissions = (
            ('emitir_diploma', 'Pode emitir diploma de Aluno'),
            ('emitir_boletim', 'Pode emitir boletim de Aluno'),
            ('emitir_historico', 'Pode emitir histórico de Aluno'),
            ('efetuar_matricula', 'Pode efetuar matricula de Aluno'),
            ('pode_editar_caracterizacao', 'Pode editar caracterização'),
            ('pode_sincronizar_dados', 'Pode sincronizar dados'),
            ('gerar_relatorio', 'Pode gerar relatórios'),
            ('pode_ver_chave_acesso_pais', 'Pode ver chave de acesso dos pais'),
            ('report_dependentes_reprovados', 'Pode gerar relatório de dependentes/reprovados'),
            ('importar_aluno', 'Pode importar aluno de sistemas legados'),
            ('change_foto_aluno', 'Pode editar foto do aluno'),
            ('view_dados_academicos', 'Pode visualizar dados acadêmicos do aluno'),
            ('view_dados_pessoais', 'Pode visualizar dados pessoais do aluno'),
            ('view_dados_caracterizacao_e_academicos', 'Pode visualizar dados da caracterização e acadêmicos'),
            ('pode_editar_orientador_pos', 'Pode editar orientador pós-graduação'),
        )

    EXT_COMBO_RELATED = {
        'select_related': ['pessoa_fisica', 'curso_campus', 'curso_campus__diretoria__setor__uo'],
        'prefetch_related': ['caracterizacao', 'inscricao_set'],
    }

    class Anonymize:
        suppress = []
        cover = []
        default_cover = [
            'get_nome_social_composto',
            'matricula',
            'get_rg',
            'get_nome',
            'pessoa_fisica.nome_social',
            'pessoa_fisica.cpf',
            'pessoa_fisica.genero',
            'get_telefones',
            'codigo_educacenso',
            'codigo_sistec',
            'nome_pai',
            'nome_mae',
            'responsavel',
            'email_responsavel',
            'get_chave_responsavel',
            'get_observacoes',
            'observacao_historico',
            'email_academico',
            'email_pessoal',
            'email_google_classroom',
            'pessoa_fisica.grupo_sanguineo',
            'pessoa_fisica.fator_rh',
            'pessoa_fisica.nome_usual',
        ]
        hash = []
        other = {
            'get_absolute_url': 'get_absolute_url_anonimo',
            'get_endereco': 'get_endereco_anonimo',
            'pessoa_fisica.nascimento_data': 'get_nascimento_anonimo',
            'get_foto_path': 'get_foto_path_anonimo',
        }

    def can_view_data(self, request, field):
        # aguardando definição dos campos para anonimização.
        if request is None:
            return False, 'Este campo foi anonimizado (requisição inválida).'
        if request.path in ('/edu/relatorio/', '/edu/estatistica/'):
            if 'xls_anonimo' in request.GET or 'xls_anonimo' in request.POST:
                return False, 'Este campo foi anonimizado a pedido do usuário.'
            if perms.pode_ver_dados_anonimos_aluno(request.user, self):
                return True, ''
            else:
                if field == 'get_absolute_url' or 'imprimir' in request.POST or 'assinaturas' in request.POST or 'carometros' in request.POST:
                    return False, ''
                return False, 'Este campo foi anonimizado pois você não tem permissão para visualizá-lo.'
        return True, ''

    def get_frequencias_pedemeia(self, ultima_atualizacao=False):
        from edu.models.pedemeia import RequisicaoPeDeMeia

        requisicoes = RequisicaoPeDeMeia.objects.filter(
            aluno=self, tipo__in=(RequisicaoPeDeMeia.FREQUENCIA, RequisicaoPeDeMeia.ATUALIZACAO_FREQUENCIA)
        ).order_by('ano__ano', 'mes')
        if ultima_atualizacao:
            registros = {}
            requisicoes = requisicoes.order_by('ano_id', 'mes', 'tipo').distinct('ano_id', 'mes', 'tipo')
            for obj in requisicoes:
                chave = f'{obj.ano_id}{obj.mes}'
                if chave not in registros:
                    registros[chave] = obj
            return registros.values()
        return requisicoes

    def get_frequencias_pedemeia_ultima_atualizacao(self):
        return self.get_frequencias_pedemeia(ultima_atualizacao=True)

    def get_tipos_documentos_cadastrados(self):
        from edu.models.arquivos import TipoAlunoArquivo

        return TipoAlunoArquivo.objects.filter(pk__in=self.alunoarquivo_set.values_list('tipo', flat=True))

    def clean_fields(self, exclude: Iterable[str] | None = None) -> None:
        errors: dict[str, list[ValidationError]] = {}
        try:
            super().clean_fields(exclude=exclude)
        except ValidationError as e:
            errors = e.update_error_dict(errors)

        exclude_set = set(exclude) if exclude else set()
        if 'numero_rg' not in exclude_set and self.numero_rg:
            padrao_rg = r'^[a-zA-Z0-9]{4,15}$'
            if not re.match(padrao_rg, self.numero_rg):
                errors.setdefault('numero_rg', []).append(
                    ValidationError('O campo "Número do RG" deve ter entre 4 e 15 caracteres e pode conter somente letras e números.')
                )

        if errors:
            raise ValidationError(errors)

    def clean(self) -> None:
        if self.eh_aluno_minicurso() and (self.matriz_id or getattr(self, 'matriz', None)):
            raise ValidationError({'matriz': 'Alunos de curso FIC- (Minicurso) não podem ter matriz curricular informada.'})

    def get_documentos_obrigatorios(self):
        documentos_obrigatorios = []
        if self.curso_campus.modalidade.grupoarquivoobrigatorio_set.exists():
            grupos_arquivos = self.curso_campus.modalidade.grupoarquivoobrigatorio_set.all()
            hoje = datetime.datetime.now().date()
            aluno_arquivos = self.alunoarquivo_set.filter(tipo__isnull=False).filter(validado=True, data_expiracao__gte=hoje)
            for grupo_arquivos in grupos_arquivos:
                tipos_obrigatorios_grupo = grupo_arquivos.tipos.all().distinct()
                for arquivo_aluno in aluno_arquivos:
                    if arquivo_aluno.tipo_id and arquivo_aluno.tipo in tipos_obrigatorios_grupo:
                        if arquivo_aluno not in documentos_obrigatorios:
                            documentos_obrigatorios.append(arquivo_aluno)
                            tipos_obrigatorios_grupo = tipos_obrigatorios_grupo.exclude(id=arquivo_aluno.tipo.id)
                        else:
                            for arquivo_obrigatorio in documentos_obrigatorios:
                                if (
                                    arquivo_obrigatorio.tipo == arquivo_aluno.tipo
                                    and arquivo_aluno.data_hora_upload > arquivo_obrigatorio.data_hora_upload
                                ):
                                    documentos_obrigatorios.append(arquivo_aluno)
                                    tipos_obrigatorios_grupo = tipos_obrigatorios_grupo.exclude(id=arquivo_aluno.tipo.id)
        return documentos_obrigatorios

    @transaction.atomic
    def trocar_periodo_letivo_ingresso(self, novo_ano_letivo, novo_periodo_letivo):
        matricula2 = f'{novo_ano_letivo}{novo_periodo_letivo}{self.matricula[5:]}'
        if self.matricula != matricula2:
            # tentar utilizar o mesmo número da matrícula alterando apenas o período letivo
            if Aluno.objects.filter(matricula=matricula2).exists():
                # obtendo um novo número tendo em vista que já existe um aluno com a nova matrícula associada
                matricula2 = SequencialMatricula.proximo_numero(matricula2[0:10])
            # Se certificando que realmente não existe aluno com a nova matrícula e que o aluno é ingressante
            if Aluno.objects.filter(matricula=matricula2).first() is None and not self.matriculaperiodo_set.exclude(
                ano_letivo=self.ano_letivo, periodo_letivo=self.periodo_letivo
            ):
                self.ano_letivo = novo_ano_letivo
                self.periodo_letivo = novo_periodo_letivo
                user = self.get_user()  # antes de trocar a matrícula, que é o username do usuário
                self.matricula = matricula2
                self.pessoa_fisica.username = matricula2
                user.username = matricula2
                user.save()
                self.pessoa_fisica.save()
                self.save()
                mp = self.get_ultima_matricula_periodo()
                mp.ano_letivo = novo_ano_letivo
                mp.periodo_letivo = novo_periodo_letivo
                mp.save()
                return matricula2
        return None

    def possui_todos_documentos_obrigatorios(self):
        hoje = datetime.datetime.now().date()
        for grupo in self.curso_campus.modalidade.grupoarquivoobrigatorio_set.all().distinct():
            if not self.alunoarquivo_set.filter(validado=True, data_expiracao__gte=hoje).filter(tipo__in=grupo.tipos.all()).exists():
                return False
        return True

    def requer_autenticacao_sistec_para_emissao_diploma(self):
        return self.curso_campus.modalidade_id in (
            Modalidade.INTEGRADO,
            Modalidade.INTEGRADO_EJA,
            Modalidade.FIC_INTEGRADO_EJA,
            Modalidade.CONCOMITANTE,
            Modalidade.SUBSEQUENTE,
        )

    @property
    def papeis(self):
        return self.get_vinculo().papel_set.all()

    @property
    def papeis_ativos(self):
        hoje = datetime.date.today()
        papeis_datas_menores_hoje = self.get_vinculo().papel_set.filter(data_inicio__lte=hoje)
        return papeis_datas_menores_hoje.filter(data_fim__isnull=True) | papeis_datas_menores_hoje.filter(data_fim__gte=hoje)

    @property
    def matriz_curso(self):
        return self.matriz_id and MatrizCurso.objects.get(curso_campus=self.curso_campus_id, matriz=self.matriz_id) or None

    @cached_property
    def setor(self):
        return self.curso_campus.diretoria.setor if self.curso_campus.diretoria_id else None

    def get_observacoes(self):
        return self.observacao_set.all()

    def get_pasta_cra(self):
        registros = self.registroemissaodiploma_set.all()
        pastas = []
        if registros.exists():
            for registro in registros:
                pastas.append(registro.pasta)
        return pastas

    def is_periodo_solicitacao_trancamento_voluntario(self):
        # verifica período de trancamento do calendário acadêmico
        mp = self.get_ultima_matricula_periodo()
        diario = Diario.objects.filter(
            componente_curricular__matriz_id=self.matriz.id,
            matriculadiario__matricula_periodo__aluno_id=self.id,
            ano_letivo_id=mp.ano_letivo.id,
            periodo_letivo=mp.periodo_letivo,
        ).first()
        if diario:
            calendario_academico = diario.calendario_academico
            if calendario_academico.data_fim_trancamento and calendario_academico.data_inicio_trancamento:
                hoje = datetime.date.today()
                if hoje > calendario_academico.data_fim_trancamento or hoje < calendario_academico.data_inicio_trancamento:
                    return False
        return True

    def is_periodo_ingresso_integralizado(self):
        """
        Verifica se o período de ingresso do aluno está integralizado para fins de solicitação de Trancamento Voluntário.

        Legislação (Organização Didática):
        Art. 219. O trancamento voluntário somente será autorizado após a integralização de todos os componentes
        curriculares do primeiro período do curso.
            § 1º. Para os estudantes com admissão por reingresso e transferência, o trancamento voluntário só poderá
               ser concedido quando for integralizado o período em que foi posicionado após a realização do
               aproveitamento dos estudos.
        """
        if not self.matriz:
            return False

        # verifica componentes integralizados
        if self.matriz.estrutura.exige_periodo_ingresso_integralizado:
            periodo_inicial = 1
            for caso_especial in ('reingresso', 'transferência', 'transferencia'):
                if caso_especial in self.forma_ingresso.descricao.lower():
                    matricula_inicial = self.get_matriculas_periodo(orderbyDesc=False).first()
                    periodo_inicial = matricula_inicial and matricula_inicial.periodo_matriz or periodo_inicial
                    break
            ids_componentes_periodo_inicial = set(self.matriz.get_ids_componentes(periodos=[periodo_inicial]))
            ids_componentes_cumpridos = set(self.get_ids_componentes_cumpridos(ids=ids_componentes_periodo_inicial))
            if len(ids_componentes_periodo_inicial - ids_componentes_cumpridos) != 0:
                return False
        return True

    def is_aluno_extensao(self):
        return (
            self.matriz_id
            and self.matriz.ch_atividades_extensao > 0
            and self.situacao_id in (SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL)
        )

    def pode_solicitar_trancamento_voluntario(self):
        return (
            self.matriz
            and self.is_periodo_solicitacao_trancamento_voluntario()
            and self.is_periodo_ingresso_integralizado()
            and not self.is_atingido_limite_trancamento_voluntario()
        )

    def pode_solicitar_atividade_complementar(self, user):
        if user is None or self.matricula != user.username:
            return False

        if self.situacao_id not in [SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL]:
            return False

        if self.curso_campus is None or self.curso_campus.modalidade is None:
            return False

        niveis_ensino_permitidos = [NivelEnsino.GRADUACAO, NivelEnsino.POS_GRADUACAO]
        if Configuracao.get_valor_por_chave('edu', 'permite_medio_adicionar_atividade_complementar'):
            niveis_ensino_permitidos.append(NivelEnsino.MEDIO)

        return self.curso_campus.modalidade.nivel_ensino_id in niveis_ensino_permitidos

    def is_atingido_limite_trancamento_voluntario(self, matricula_periodo=None):
        estrutura = self.matriz.estrutura
        if estrutura and estrutura.qtd_trancamento_voluntario is not None:
            matricula_periodo = matricula_periodo or self.get_ultima_matricula_periodo()
            # plano de retomada de aulas em virtude da pandemia (COVID19)
            if estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO:
                ids_matriculaperiodo_plano_retomada = (
                    self.matriculaperiodo_set.filter(matriculadiario__diario__turma__pertence_ao_plano_retomada=True)
                    .order_by('id')
                    .values_list('id', flat=True)
                    .distinct()
                )
            else:
                ids_matriculaperiodo_plano_retomada = (
                    self.matriculaperiodo_set.filter(turma__pertence_ao_plano_retomada=True).order_by('id').values_list('id', flat=True).distinct()
                )

            if matricula_periodo.pk not in list(ids_matriculaperiodo_plano_retomada):
                qtd_trancamentos = (
                    MatriculaPeriodo.objects.exclude(id__in=ids_matriculaperiodo_plano_retomada)
                    .filter(situacao=SituacaoMatriculaPeriodo.TRANCADA_VOLUNTARIAMENTE, aluno_id=self.id)
                    .count()
                )
                return qtd_trancamentos >= estrutura.qtd_trancamento_voluntario
        return False

    def em_horario_de_aula(self, data, hora):
        if not hasattr(self, '_mp'):
            mp = self.get_matricula_periodo_na_data(data)
            self._mp = mp
        else:
            mp = self._mp
        if mp:
            return mp.em_horario_de_aula(data.weekday() + 1, hora)
        else:
            return False

    def get_mes_ano_processo_seletivo(self):
        meses = ('Janeiro', 'Fevereiro', 'Março', 'Abril', 'Maio', 'Junho', 'Julho', 'Agosto', 'Setembro', 'Outubro', 'Novembro', 'Dezembro')
        mes_ano_processo_seletivo = f'{meses[self.data_matricula.month - 1]} de {self.data_matricula.year}'
        if self.candidato_vaga:
            data_encerramento = self.candidato_vaga.oferta_vaga.oferta_vaga_curso.edital.data_encerramento
            if data_encerramento:
                mes_ano_processo_seletivo = f'{meses[data_encerramento.month - 1]} de {data_encerramento.year}'
        return mes_ano_processo_seletivo

    def get_matricula_periodo_na_data(self, data):
        qs = (
            Diario.objects.filter(
                calendario_academico__data_inicio__lte=data, calendario_academico__data_fim__gte=data, matriculadiario__matricula_periodo__aluno=self
            )
            .values_list('matriculadiario__matricula_periodo', flat=True)
            .order_by('matriculadiario__matricula_periodo')
            .distinct()
        )
        return qs.exists() and MatriculaPeriodo.objects.get(pk=qs[0]) or None

    def get_ch_pendente(self, detalhado=False, ano=None):
        ch_componentes_regulares_obrigatorios_pendente = self.get_ch_componentes_regulares_obrigatorios_pendente(ano=ano)
        ch_componentes_regulares_optativos_pendente = self.get_ch_componentes_regulares_optativos_pendente(ano=ano)
        ch_componentes_eletivos_pendente = self.get_ch_componentes_eletivos_pendente(ano=ano)
        ch_componentes_seminario_pendente = self.get_ch_componentes_seminario_pendente(ano=ano)
        ch_componentes_pratica_como_componente_pendente = self.get_ch_componentes_pratica_como_componente_pendente(ano=ano)
        ch_componentes_visita_tecnica_pendente = self.get_ch_componentes_visita_tecnica_pendente(ano=ano)
        ch_componentes_pratica_profissional_pendente = self.get_ch_componentes_pratica_profissional_pendente(ano=ano)
        ch_atividades_aprofundamento_pendente = self.get_ch_atividade_aprofundamento_pendente(ano=ano)

        # extensão
        ch_extensao_componentes_pendente = self.get_ch_extensao_componentes_pendente(ano=ano)
        ch_extensao_outras_atividades_pendente = self.get_ch_extensao_outras_atividades_pendente(ano=ano)
        ch_extensao_outros_componentes_pendente = self.get_ch_extensao_outros_componentes_pendente(ano=ano)

        ch_componentes_tcc_pendente = self.get_ch_componentes_tcc_pendente(ano=ano)
        ch_atividades_complementares_pendente = self.get_ch_atividades_complementares_pendente(ano=ano)
        ch_atividades_pratica_profissional_pendente = self.get_ch_atividade_pratica_profissional_pendente_total()
        total_ch_pendente = (
            ch_componentes_regulares_obrigatorios_pendente
            + ch_componentes_regulares_optativos_pendente
            + ch_componentes_eletivos_pendente
            + ch_componentes_seminario_pendente
            + ch_componentes_pratica_profissional_pendente
            + ch_atividades_aprofundamento_pendente
            + ch_extensao_componentes_pendente
            + ch_componentes_tcc_pendente
            + ch_atividades_complementares_pendente
            + ch_componentes_pratica_como_componente_pendente
            + ch_componentes_visita_tecnica_pendente
            + ch_atividades_pratica_profissional_pendente
        )
        if not (self.matriz and self.matriz.requer_vinculacao_extensao_diarios):
            total_ch_pendente += ch_extensao_outras_atividades_pendente
        if detalhado:
            return (
                ch_componentes_regulares_obrigatorios_pendente,
                ch_componentes_regulares_optativos_pendente,
                ch_componentes_eletivos_pendente,
                ch_componentes_seminario_pendente,
                ch_componentes_pratica_profissional_pendente,
                ch_atividades_aprofundamento_pendente,
                ch_extensao_componentes_pendente,
                ch_extensao_outras_atividades_pendente,
                ch_extensao_outros_componentes_pendente,
                ch_componentes_tcc_pendente,
                ch_atividades_complementares_pendente,
                ch_componentes_pratica_como_componente_pendente,
                ch_componentes_visita_tecnica_pendente,
                ch_atividades_pratica_profissional_pendente,
                total_ch_pendente,
            )
        else:
            return total_ch_pendente

    def get_ch_componentes_matriz_cursando(self):
        """
        Retorna a carga horária dos componentes da matriz que o aluno está cursando.
        """
        if hasattr(self, '_ch_componentes_matriz_cursando'):
            return self._ch_componentes_matriz_cursando
        ids_matriz = self.matriz.get_ids_componentes()
        result = self.get_componentes_cursando().filter(id__in=ids_matriz).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        self._ch_componentes_matriz_cursando = mask_ch_componente(result)
        return self._ch_componentes_matriz_cursando

    def get_ch_componentes_com_percentual_ch_cumprida(self, matricula_periodo=None, previsao=False):
        ch_cumprida = 0

        # componentes
        ch_componentes_regulares_obrigatorios_cumprida = self.get_ch_componentes_regulares_obrigatorios_cumprida(matricula_periodo)
        ch_componentes_regulares_optativos_cumprida = self.get_ch_componentes_regulares_optativos_cumprida(matricula_periodo)
        ch_componentes_seminario_cumprida = self.get_ch_componentes_seminario_cumprida(matricula_periodo)
        ch_componentes_pratica_profissional_cumprida = self.get_ch_componentes_pratica_profissional_cumprida(matricula_periodo)
        ch_componentes_tcc_cumprida = self.get_ch_componentes_tcc_cumprida(matricula_periodo)
        ch_pratica_como_componente_cumprida = self.get_ch_componentes_pratica_como_componente_cumprida(matricula_periodo=matricula_periodo)
        ch_visita_tecnica_cumprida = self.get_ch_componentes_visita_tecnica_cumprida(matricula_periodo=matricula_periodo)
        ch_componentes_eletivos_cumprida = self.get_ch_componentes_eletivos_cumprida(matricula_periodo=matricula_periodo)

        # atividades
        ch_atividades_complementares_cumprida = self.get_ch_atividades_complementares_cumprida(matricula_periodo=matricula_periodo)
        ch_atividades_aprofundamento_cumprida = self.get_ch_atividade_aprofundamento_cumprida(matricula_periodo)

        # extensão
        ch_extensao_componentes_cumprida = self.get_ch_extensao_componentes_cumprida(matricula_periodo)
        ch_extensao_outras_atividades_cumprida = self.get_ch_extensao_outras_atividades_cumprida(matricula_periodo)
        ch_extensao_outros_componentes_cumprida = self.get_ch_extensao_outros_componentes_cumprida(matricula_periodo)
        # soma apenas a CH de componentes do tipo atividade de extensão e outras atividades. CH em outros componentes já está contabilizada nos calculos anteriores
        ch_atividades_extensao_cumprida = ch_extensao_componentes_cumprida + ch_extensao_outras_atividades_cumprida

        # atividades de prática profissional
        ch_atividades_pratica_profissional_cumprida = self.get_ch_atividade_pratica_profissional_contabilizada()

        ch_cumprida += min(ch_componentes_regulares_obrigatorios_cumprida, self.matriz.ch_componentes_obrigatorios)
        ch_cumprida += min(ch_componentes_regulares_optativos_cumprida, self.matriz.ch_componentes_optativos)
        ch_cumprida += min(ch_componentes_seminario_cumprida, self.matriz.ch_seminarios)
        ch_cumprida += min(ch_componentes_pratica_profissional_cumprida, self.matriz.ch_pratica_profissional)
        ch_cumprida += min(ch_componentes_tcc_cumprida, self.matriz.ch_componentes_tcc)
        ch_cumprida += min(ch_atividades_complementares_cumprida, self.matriz.ch_atividades_complementares)
        ch_cumprida += min(ch_atividades_aprofundamento_cumprida, self.matriz.ch_atividades_aprofundamento)
        ch_cumprida += min(ch_atividades_extensao_cumprida, self.matriz.ch_atividades_extensao)
        ch_cumprida += min(ch_pratica_como_componente_cumprida, self.matriz.ch_pratica_como_componente)
        ch_cumprida += min(ch_visita_tecnica_cumprida, self.matriz.ch_visita_tecnica)
        ch_cumprida += min(ch_componentes_eletivos_cumprida, self.matriz.ch_componentes_eletivos)
        ch_cumprida += ch_atividades_pratica_profissional_cumprida

        if previsao:
            ch_cumprida += self.get_ch_componentes_matriz_cursando()

        ch_total_prevista = self.matriz.get_carga_horaria_total_prevista()

        percentual_ch_cumprida = Decimal(ch_cumprida * 100 / ch_total_prevista).quantize(Decimal('0.00')) if ch_total_prevista else 0

        return (
            ch_componentes_regulares_obrigatorios_cumprida,
            ch_componentes_regulares_optativos_cumprida,
            ch_componentes_seminario_cumprida,
            ch_componentes_pratica_profissional_cumprida,
            ch_componentes_tcc_cumprida,
            ch_atividades_complementares_cumprida,
            ch_atividades_aprofundamento_cumprida,
            ch_extensao_componentes_cumprida,
            ch_extensao_outras_atividades_cumprida,
            ch_extensao_outros_componentes_cumprida,
            ch_pratica_como_componente_cumprida,
            ch_visita_tecnica_cumprida,
            ch_componentes_eletivos_cumprida,
            ch_atividades_pratica_profissional_cumprida,
            percentual_ch_cumprida,
        )

    def get_percentual_carga_horaria_cumprida(self, matricula_periodo=None, previsao=False):
        if not self.matriz:
            return -1
        if previsao and hasattr(self, '_percentual_ch_prevista'):
            return self._percentual_ch_prevista
        _, _, _, _, _, _, _, _, _, _, _, _, _, _, percentual_ch = self.get_ch_componentes_com_percentual_ch_cumprida(matricula_periodo, previsao)
        if previsao:
            self._percentual_ch_prevista = percentual_ch
        return percentual_ch

    def atualizar_percentual_ch_cumprida(self):
        percentual_ch_cumprida = 0
        if self.matriz:
            for mp in self.get_matriculas_periodo(orderbyDesc=False):
                if percentual_ch_cumprida < 100:
                    percentual_ch_cumprida = percentual_ch_cumprida + self.get_percentual_carga_horaria_cumprida(mp)
                if percentual_ch_cumprida > 100:
                    percentual_ch_cumprida = 100
                mp.percentual_ch_cumprida = percentual_ch_cumprida
                mp.save()
            self.percentual_ch_cumprida = self.get_percentual_carga_horaria_cumprida()
            self.save()

    def calcular_frequencia_pe_de_meia(self, ano, mes, imprimir=False, requisicao=None):
        inicio = datetime.date(int(ano), int(mes), 1)
        fim = inicio
        while fim.month == inicio.month:
            fim = somar_dias(fim, 1)
        fim = somar_dias(fim, -1)
        qs_qtd_horas_ofertada = Aula.objects.filter(
            data__gte=inicio,
            data__lte=fim,
            registro_frequencia_confirmado=True,
            professor_diario__diario__matriculadiario__matricula_periodo__aluno=self,
        )
        qtd_horas_ofertada = qs_qtd_horas_ofertada.aggregate(qtd_horas_ofertada=Sum('quantidade'))['qtd_horas_ofertada'] or 0
        qs_qtd_horas_ausentes = Falta.objects.filter(
            contabilizar=True,
            aula__data__gte=inicio,
            aula__data__lte=fim,
            aula__registro_frequencia_confirmado=True,
            matricula_diario__matricula_periodo__aluno=self,
        )
        qtd_horas_ausentes = qs_qtd_horas_ausentes.aggregate(qtd_horas_ausentes=Sum('quantidade'))['qtd_horas_ausentes'] or 0
        qtd_horas_presentes = qtd_horas_ofertada - qtd_horas_ausentes

        frequencias_pratica_profissional = FrequenciaPraticaProfissional.objects.filter(
            matricula_diario__diario__ano_letivo__ano=inicio.year, matricula_diario__matricula_periodo__aluno=self, mes=inicio.month
        )
        for frequencia_pratica_profissional in frequencias_pratica_profissional:
            qtd_horas_ofertada += frequencia_pratica_profissional.ch_esperada
            qtd_horas_presentes += frequencia_pratica_profissional.ch_frequentada
            qtd_horas_ausentes += frequencia_pratica_profissional.ch_esperada - frequencia_pratica_profissional.ch_frequentada

        if imprimir:
            logger.info(
                f'Será enviada a  frequência do aluno {self}, mês {inicio.month}, ano {inicio.year}, qtd_horas_ofertadas {qtd_horas_ofertada}, qtd_horas_presentes {qtd_horas_presentes} ({qtd_horas_ausentes} faltas)'
            )
            logger.info('Aulas:')
            for aula in qs_qtd_horas_ofertada:
                logger.info(f'\t{aula.professor_diario.diario_id} - {aula.data.strftime("%d/%m/%Y")}')
            logger.info('Faltas:')
            for falta in qs_qtd_horas_ausentes:
                logger.info(f'\t{falta.quantidade}: {falta.aula.professor_diario.diario_id} - {falta.aula.data.strftime("%d/%m/%Y")}')
        if requisicao:
            enviado = requisicao.json_retorno or {}
            qtd_horas_ofertada_enviada = enviado.get('qtHorasLetivasOfertadasPeriodo')
            qtd_horas_presentes_enviada = enviado.get('qtHorasLetivasPresentesPeriodo')
            if qtd_horas_ofertada_enviada is None:
                qtd_horas_ofertada_enviada = enviado.get('qt_horas_letivas_ofertadas_periodo')
                qtd_horas_presentes_enviada = enviado.get('qt_horas_letivas_presentes_periodo')
            logger.info(
                '{}\t{}\t{}\t{}\t{}\t{}\t{}'.format(
                    requisicao.id,
                    requisicao.aluno.matricula,
                    'PROCESSADA' if requisicao.processada else 'NAO-PROCESSADA',
                    qtd_horas_ofertada,
                    qtd_horas_ofertada_enviada,
                    qtd_horas_presentes,
                    qtd_horas_presentes_enviada,
                )
            )
            if requisicao.processada and (
                str(qtd_horas_ofertada) != str(qtd_horas_ofertada_enviada) or str(qtd_horas_presentes) != str(qtd_horas_presentes_enviada)
            ):
                logger.info(f'Atualizar frequência da requisição #{requisicao.id}!!!')
            requisicao.aulas.set(qs_qtd_horas_ofertada)
            requisicao.faltas.set(qs_qtd_horas_ausentes)
            requisicao.praticas_profissionais.set(frequencias_pratica_profissional)
        return (
            qtd_horas_ofertada,
            qtd_horas_ausentes,
            qtd_horas_presentes,
            qs_qtd_horas_ofertada,
            qs_qtd_horas_ausentes,
            frequencias_pratica_profissional,
        )

    def get_situacao_sistemica(self):
        academico_nome_sistema = Configuracao.get_valor_por_chave('edu', 'academico_nome_sistema')
        situacao = [1, f'Matriculado no {academico_nome_sistema}']
        if self.matriz:
            if not self.matriculaperiodo_set.exists():
                situacao = [2, f'Migrado parcialmente do {academico_nome_sistema} para o SUAP']
            elif self.data_integralizacao:
                situacao = [2, f'Migrado do {academico_nome_sistema} para o SUAP']
            else:
                situacao = [3, 'Matriculado no SUAP']
        elif self.is_sica():
            situacao = [1, 'Matriculado no SICA']
        else:
            if self.eh_aluno_minicurso():
                situacao = [4, 'Matriculado no SUAP (Minicurso)']
        return situacao

    def get_situacao_componente_display(self, componente_id):
        STATUS_MAP = {
            'Aprovado': 'success',
            'Cursando': 'alert',
            'Prova Final': 'alert',
        }

        situacao = self._get_situacao_componente(componente_id)
        status = STATUS_MAP.get(situacao, 'error')

        return status, situacao

    def _get_situacao_componente(self, componente_id):
        md = (
            MatriculaDiario.objects.filter(matricula_periodo__aluno_id=self.id, diario__componente_curricular__componente_id=componente_id)
            .only('id', 'situacao')
            .order_by('-id')
            .first()
        )
        if md:
            return md.get_situacao_display()
        cc = (
            CertificacaoConhecimento.objects.filter(matricula_periodo__aluno_id=self.id, componente_curricular__componente_id=componente_id)
            .exclude(ausente=True)
            .exists()
        )
        if cc:
            return 'Aprovado'
        ae = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=self.id, componente_curricular__componente_id=componente_id).exists()
        if ae:
            return 'Aprovado'
        ac = AproveitamentoComponente.objects.filter(componente_curricular__componente_id=componente_id, matricula_periodo__aluno_id=self.id).exists()
        if ac:
            return 'Aprovado'
        rh = (
            RegistroHistorico.objects.filter(matricula_periodo__aluno_id=self.id, componente_id=componente_id)
            .only('id', 'situacao')
            .order_by('-id')
            .first()
        )
        if rh:
            return 'Aprovado' if rh.is_componente_integralizado() else 'Pendente'
        return 'Pendente'

    def eh_aluno_minicurso(self) -> bool:
        return bool(self.curso_campus and self.curso_campus.is_minicurso())

    def eh_aluno_minicurso_apto_sistec(self) -> bool:
        return (
            self.eh_aluno_minicurso()
            and self.curso_campus.ch_total is not None
            and self.curso_campus.ch_total >= CursoCampus.CARGA_HORARIA_BASE_MINICURSO
        )

    def eh_aluno_nivel_pos_graduacao(self):
        return self.curso_campus.modalidade.nivel_ensino_id == NivelEnsino.POS_GRADUACAO

    def eh_aluno_migrado_apos_conclusao_curso(self):
        return self.data_integralizacao and self.dt_conclusao_curso and self.dt_conclusao_curso < self.data_integralizacao.date()

    def get_situacao_documentacao(self):
        if self.documentacao_invalidada:
            return mark_safe(f'<span class="status status-error">Invalidada em {self.documentacao_invalidada_em.strftime("%d/%m/%Y")}</span>')
        elif self.documentada:
            if self.is_documentacao_expirada():
                return mark_safe(f'<span class="status status-error">Expirada em {self.get_expiracao_documentacao().strftime("%d/%m/%Y")}</span>')
            else:
                return mark_safe(f'<span class="status status-success">Validada em {self.data_documentacao.strftime("%d/%m/%Y")}</span>')
        elif self.data_documentacao:
            return mark_safe(f'<span class="status status-alert">Último validação em {self.data_documentacao.strftime("%d/%m/%Y")}</span>')
        elif self.documentoinscricaoaluno_set.exists():
            return mark_safe('<span class="status status-alert">Documentação anexada e aguardando análise</span>')
        else:
            return mark_safe('<span class="status status-alert">Documentação não informada</span>')

    def is_documentacao_expirada(self):
        prazo_expiracao = Configuracao.get_valor_por_chave('ae', 'prazo_expiracao_documentacao')
        total_dias = prazo_expiracao and int(prazo_expiracao) or 365
        return self.data_documentacao and self.data_documentacao < somar_dias(datetime.datetime.now(), -total_dias)

    def get_expiracao_documentacao(self):
        if self.data_documentacao:  # IFF: Verificando se data_documentação existe, antes de somá-lo
            prazo_expiracao = Configuracao.get_valor_por_chave('ae', 'prazo_expiracao_documentacao')
            total_dias = prazo_expiracao and int(prazo_expiracao) or 365
            return somar_dias(self.data_documentacao, total_dias)

    def get_chave_responsavel(self):
        if not self.token_responsavel:
            self.token_responsavel = binascii.hexlify(os.urandom(20)).decode().lower()
            self.save()
        return self.token_responsavel[0:5].lower()

    def get_dados_bancarios(self, todas=False):
        if 'ae' in settings.INSTALLED_APPS:
            qs = self.dadosbancarios_set.all()
            if not todas:
                qs = qs.exclude(inscricaopasseestudantil__id__isnull=False)
                qs = qs.exclude(inscricaotrabalho__id__isnull=False)
            return qs
        return []

    def get_dados_bancarios_folha_pagamento(self):
        if self.get_dados_bancarios():
            return self.get_dados_bancarios().order_by('-prioritario_servico_social')[0]
        return ''

    def get_dados_bancarios_banco(self):
        if self.get_dados_bancarios_folha_pagamento():
            banco = self.get_dados_bancarios_folha_pagamento().instituicao
            return banco.codigo
        return ''

    def get_dados_bancarios_numero_agencia(self):
        if self.get_dados_bancarios_folha_pagamento():
            return self.get_dados_bancarios_folha_pagamento().numero_agencia.split('-')[0].replace('/', '').replace('_', '').replace('.', '')
        return ''

    def get_dados_bancarios_numero_conta(self):
        if self.get_dados_bancarios_folha_pagamento():
            return self.get_dados_bancarios_folha_pagamento().numero_conta.replace('-', '').replace('/', '').replace('_', '').replace('.', '')
        return ''

    def get_dados_bancarios_operacao(self):
        if self.get_dados_bancarios_folha_pagamento():
            return self.get_dados_bancarios_folha_pagamento().operacao
        return ''

    def get_participacoes_abertas(self):
        if 'ae' in settings.INSTALLED_APPS:
            Participacao = apps.get_model('ae', 'Participacao')
            participacao_aberta = Participacao.abertas.filter(aluno=self)
            texto = []
            if participacao_aberta.exists():
                for participacao in participacao_aberta:
                    texto.append(participacao.programa.tipo_programa.titulo)
                return format_iterable(texto)
        return '-'

    def is_pcd(self):
        return self.deficiencias.exists()

    def possui_nee(self):
        return self.deficiencias.exists() or self.outras_nees.exists()

    def get_deficiencias_censup(self):
        return set(self.deficiencias.filter(classificacao_censup__isnull=False).values_list('classificacao_censup', flat=True))

    def get_deficiencias_educacenso(self):
        return set(self.deficiencias.filter(classificacao_educacenso__isnull=False).values_list('classificacao_educacenso', flat=True))

    def get_nee_altashabilidades_educacenso(self):
        return [TipoNEE.ALTAS_HABILIDADES] if self.outras_nees.filter(classificacao_educacenso=TipoNEE.ALTAS_HABILIDADES).exists() else []

    def get_nee_altashabilidades_censup(self):
        return [TipoNEE.ALTAS_HABILIDADES] if self.outras_nees.filter(classificacao_censup=TipoNEE.ALTAS_HABILIDADES).exists() else []

    def get_outras_nees_educacenso(self):
        return set(self.outras_nees.exclude(classificacao_educacenso=TipoNEE.ALTAS_HABILIDADES).values_list('classificacao_educacenso', flat=True))

    def get_nee(self):
        return [d.nome for d in self.deficiencias.all()] + [n.nome for n in self.outras_nees.all()]

    def get_cpf(self):
        return self.pessoa_fisica.cpf

    def get_nome(self):
        return self.pessoa_fisica.nome

    def get_nome_social_composto(self):
        if self.pessoa_fisica.nome_social:
            return f'{self.pessoa_fisica.nome_registro} ({self.pessoa_fisica.nome_social})'
        else:
            return self.pessoa_fisica.nome

    def get_componentes_curriculares_por_ids(self, ids_componentes):
        return ComponenteCurricular.objects.filter(matriz=self.matriz, componente_id__in=ids_componentes).order_by('componente_id')

    def get_telefones(self):
        telefones = '-'
        if self.telefone_principal:
            telefones = self.telefone_principal
        if self.telefone_secundario:
            telefones = f'{telefones}, {self.telefone_secundario}'
        if self.telefone_adicional_1:
            telefones = f'{telefones}, {self.telefone_adicional_1}'
        if self.telefone_adicional_2:
            telefones = f'{telefones}, {self.telefone_adicional_2}'
        return telefones

    @staticmethod
    def get_ingressantes_sem_turma(ano_letivo, periodo_letivo, diretoria=None, curso=None):
        ids_diretorias = Diretoria.locals.values_list('id', flat=True)
        ingressantes = Aluno.objects.filter(
            ano_letivo__ano=ano_letivo.ano,
            periodo_letivo=periodo_letivo,
            matriculaperiodo__ano_letivo__ano=ano_letivo.ano,
            matriculaperiodo__periodo_letivo=periodo_letivo,
            matriculaperiodo__turma__isnull=True,
            situacao__id__in=[SituacaoMatricula.MATRICULADO],
            matriculaperiodo__situacao__in=[SituacaoMatriculaPeriodo.MATRICULADO],
            periodo_atual=1,
        ).exclude(forma_ingresso_id__in=[FormaIngresso.TRANSFERENCIA_COMPULSORIA, FormaIngresso.TRANSFERENCIA_FACULTATIVA])

        ingressantes = ingressantes.filter(
            matriz__estrutura__proitec=False, data_integralizacao__isnull=True, matriz__isnull=False, curso_campus__diretoria__id__in=ids_diretorias
        )

        if diretoria:
            ingressantes = ingressantes.filter(curso_campus__diretoria=diretoria)

        if curso:
            ingressantes = ingressantes.filter(curso_campus=curso)

        return ingressantes

    @staticmethod
    def get_alunos_concluidos_dados_incompletos(diretoria_id=None, cursos_id=None):
        ids_diretorias = [diretoria_id] if diretoria_id else list(Diretoria.locals.values_list('id', flat=True))

        ids_matrizes = list(
            MatrizCurso.objects.filter(
                matriz__estrutura__proitec=False, curso_campus__diretoria_id__in=ids_diretorias, curso_campus__ativo=True
            ).values_list('matriz_id', flat=True)
        )

        qs = Aluno.objects.filter(
            Q(
                situacao_id__in=[SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO],
                matriz_id__in=ids_matrizes,
                curso_campus__diretoria_id__in=ids_diretorias,
            ),
            Q(naturalidade_id__isnull=True)
            | Q(pessoa_fisica__nascimento_data__isnull=True)
            | Q(dt_conclusao_curso__isnull=True)
            | Q(Q(numero_rg__isnull=True) | Q(numero_rg=''), ~Q(curso_campus__modalidade_id=Modalidade.FIC)),
        )

        if cursos_id:
            qs = qs.filter(curso_campus_id__in=cursos_id)
        return qs.distinct()

    @staticmethod
    def get_alunos_sem_turma(user_coodernador, ano, periodo, curso_id=None):
        qs = Aluno.locals.filter(
            matriculaperiodo__ano_letivo__ano=ano,
            matriz__isnull=False,
            matriculaperiodo__turma__isnull=True,
            situacao__id__in=[SituacaoMatricula.MATRICULADO],
            matriculaperiodo__situacao__in=[SituacaoMatriculaPeriodo.MATRICULADO],
        )
        qs = qs.filter(curso_campus__coordenador__user=user_coodernador) | qs.filter(curso_campus__coordenador_2__user=user_coodernador)
        qs = qs.filter(curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL) | qs.filter(matriculaperiodo__periodo_letivo=periodo).exclude(
            curso_campus__periodicidade=CursoCampus.PERIODICIDADE_ANUAL
        )
        qs = qs.filter(
            matriz__estrutura__tipo_avaliacao__in=(
                EstruturaCurso.TIPO_AVALIACAO_SERIADO,
                EstruturaCurso.TIPO_AVALIACAO_FIC,
                EstruturaCurso.TIPO_AVALIACAO_MODULAR,
            )
        )
        if curso_id:
            qs = qs.filter(curso_campus_id=curso_id)
        return qs.distinct()

    @staticmethod
    def get_periodos_alunos_sem_turma(user_coodernador, curso_id=None):
        qs = MatriculaPeriodo.objects.filter(
            turma__isnull=True,
            situacao__in=[SituacaoMatriculaPeriodo.MATRICULADO],
            aluno__situacao__id__in=[SituacaoMatricula.MATRICULADO],
            aluno__matriz__isnull=False,
            aluno__matriz__estrutura__tipo_avaliacao__in=(
                EstruturaCurso.TIPO_AVALIACAO_SERIADO,
                EstruturaCurso.TIPO_AVALIACAO_FIC,
                EstruturaCurso.TIPO_AVALIACAO_MODULAR,
            ),
        )
        qs = qs.filter(aluno__curso_campus__coordenador__user=user_coodernador) | qs.filter(aluno__curso_campus__coordenador_2__user=user_coodernador)
        if curso_id:
            qs = qs.filter(aluno__curso_campus_id=curso_id)
        result = []
        for periodo in qs.values('ano_letivo__ano', 'periodo_letivo').distinct():
            result.append([periodo['ano_letivo__ano'], periodo['periodo_letivo']])
        return result

    def is_concluido_com_dados_incompletos(self):
        return (
            self.matriz
            and self.situacao.id in [SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO]
            and (self.naturalidade is None or self.pessoa_fisica.nascimento_data is None)
        )

    def can_change(self, user):
        return user.has_perm('ae.add_demandaalunoatendida') or perms.tem_permissao_realizar_procedimentos(user, self)

    def can_delete(self, user):
        return self.pode_ser_excluido() and perms.realizar_procedimentos_academicos(user, self.curso_campus)

    @atomic()
    def desfazer_migracao(self):
        self.matriz = None
        self.data_integralizacao = None
        self.ano_letivo_integralizacao = None
        self.periodo_letivo_integralizacao = None
        self.save()
        self.atividadecomplementar_set.all().delete()
        self.matriculaperiodo_set.all().update(turma=None)
        RegistroConvocacaoENADE.objects.filter(aluno=self).delete()
        ProjetoFinal.objects.filter(matricula_periodo__aluno=self).delete()
        MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno=self).delete()
        MatriculaDiario.objects.filter(matricula_periodo__aluno=self).delete()
        PedidoMatricula.objects.filter(matricula_periodo__aluno=self).delete()
        ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=self).delete()
        self.desfazer_migracao_qacademico()

    def desfazer_migracao_qacademico(self):
        from edu.q_academico import DAO

        dao = DAO()
        dao.importar_alunos(self.matricula, False)
        dao.importar_matriculas_periodo(self.matricula, False)
        dao.desfazer_situacao_alunos_integralizados_qacademico(self.matricula)

    @atomic()
    def clonar(
        self,
        matriz_curso: MatrizCurso,
        forma_ingresso: FormaIngresso | None = None,
        turno: Turno | None = None,
        data: datetime.date | None = None,
        importar_pasta_documental: bool = False,
        procedimento: ProcedimentoMatricula | None = None,
    ) -> Aluno:
        # guardando dados

        # === ao clonar um aluno, os dados do e-mail devem ser resetados e transferidos para a nova matrícula ===
        email_academico = self.email_academico
        email_google_classroom = self.email_google_classroom
        self.revogar_acesso()
        self.save()

        # ========================================================================================================

        matriculas_periodo = self.matriculaperiodo_set.all()
        data_matricula = self.data_matricula
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        atividades_complementares = self.atividadecomplementar_set.all()
        ultimo_procedimento_matricula = ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=self).order_by('-id')[0]
        # clonando o aluno
        aluno = copy.copy(self)
        aluno.id = None
        aluno.email_academico = email_academico
        aluno.email_google_classroom = email_google_classroom
        aluno.curso_campus = matriz_curso.curso_campus
        aluno.matriz = matriz_curso.matriz
        aluno.ano_letivo = ultima_matricula_periodo.ano_letivo
        aluno.periodo_letivo = ultima_matricula_periodo.periodo_letivo
        prefixo = f'{ultima_matricula_periodo.ano_letivo}{ultima_matricula_periodo.periodo_letivo}{aluno.curso_campus.codigo}'
        aluno.matricula = SequencialMatricula.proximo_numero(prefixo)
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL)
        aluno.codigo_academico = None
        aluno.data_integralizacao = None
        aluno.forma_ingresso = forma_ingresso or self.forma_ingresso
        aluno.turno = turno or self.turno

        aluno.pessoa_fisica = self.pessoa_fisica
        aluno.data_matricula = data or data_matricula
        aluno.uuid = uuid.uuid4()

        if procedimento:
            if procedimento.tipo == ProcedimentoMatricula.TRANSFERENCIA_CURSO:
                Aluno.objects.filter(id=self.id).update(codigo_sistec=None, data_inicio_ciclo=None)
            if procedimento.tipo == ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS:
                aluno.codigo_sistec = None
                aluno.data_inicio_ciclo = None

        aluno.save()

        # salvando no procedimento de matricula a matricula do novo aluno criado
        ultimo_procedimento_matricula.nova_matricula = aluno.matricula
        ultimo_procedimento_matricula.save()

        # clonando as matriculas periodos
        for matricula_periodo in matriculas_periodo:
            nova_matricula_periodo = copy.copy(matricula_periodo)
            nova_matricula_periodo.id = None
            nova_matricula_periodo.aluno = aluno
            nova_matricula_periodo.save()

            # criando os registros do historico
            matricula_periodo.adicionar_registro_historico(nova_matricula_periodo)
            matricula_periodo.adicionar_atividades_pratica_profissional(nova_matricula_periodo)

        # alterando situacao da ultima matricula periodo do novo aluno para MATRICULADO
        ultima_matricula_periodo = aluno.get_ultima_matricula_periodo()
        ultima_matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.EM_ABERTO)
        ultima_matricula_periodo.turma = None
        ultima_matricula_periodo.save()

        # clonando atividades complementares
        for atividade_complementar in atividades_complementares:
            atividade_complementar.id = None
            atividade_complementar.aluno = aluno
            atividade_complementar.save()

        # copiando pasta documental
        if importar_pasta_documental:
            from edu.models import AlunoArquivo

            hoje = datetime.datetime.now().date()
            documentos = self.alunoarquivo_set.filter(validado=True, data_expiracao__gte=hoje)
            for documento in documentos:
                arquivo_aluno = AlunoArquivo()
                arquivo_aluno.tipo_origem_cadastro = documento.tipo_origem_cadastro
                arquivo_aluno.tipo = documento.tipo
                arquivo_aluno.aluno = aluno
                arquivo_aluno.arquivo_unico = documento.arquivo_unico
                arquivo_aluno.nome_original = documento.nome_original
                arquivo_aluno.nome_exibicao = documento.nome_exibicao
                arquivo_aluno.descricao = documento.descricao
                arquivo_aluno.validado = documento.validado
                arquivo_aluno.data_hora_upload = documento.data_hora_upload
                arquivo_aluno.data_hora_criacao_registro = documento.data_hora_criacao_registro

                arquivo_aluno.data_validacao = documento.data_validacao
                arquivo_aluno.responsavel_validacao = documento.responsavel_validacao
                arquivo_aluno.prazo_validade = documento.prazo_validade
                arquivo_aluno.data_expiracao = documento.data_expiracao
                arquivo_aluno.observacao = documento.observacao

                arquivo_aluno.save()

        aluno.atualizar_situacao('Transferência de Curso')

        return aluno

    def get_projetos_integradores(self):
        from edu.models.projeto_integrador import ProjetoIntegrador

        return ProjetoIntegrador.objects.filter(participantes__matricula_periodo__aluno=self).order_by('id')

    def periodos_fechados(self):
        matriculas_periodo_abertos = self.matriculaperiodo_set.filter(
            situacao__pk__in=[SituacaoMatriculaPeriodo.MATRICULADO, SituacaoMatriculaPeriodo.EM_ABERTO]
        )
        return not matriculas_periodo_abertos.exists()

    def possui_historico(self):
        return (self.iniciou_suap() or self.integralizou_suap()) and not self.is_proitec()

    def is_matriculado(self):
        return self.situacao_id == SituacaoMatricula.MATRICULADO

    def is_matricula_vinculo(self):
        return self.situacao.pk == SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL

    def deve_impedir_matricula_vinculo(self):
        """Verifica se o aluno deve ser impedido de realizar matrícula vínculo.

        Aplica quatro regras em ordem: (1) aluno com apenas pendências de
        colação de grau ou ENADE; (2) aluno com apenas TCC ou atividade
        complementar pendente; (3) duas últimas matrículas em período com
        situação matrícula vínculo; (4) aluno sem tempo hábil para concluir
        o curso (jubilamento).

        Returns:
            ``None`` se o aluno pode realizar matrícula vínculo, ou uma
            ``str`` com a mensagem de impedimento.
        """
        # Regra 01: Alunos com apenas colação de grau e/ou ENADE pendente não podem realizar matrícula vínculo
        if not self.possui_pendencia(incluir_colacao_grau=False, incluir_enade=False):
            return 'O aluno está aguardando apenas colação de grau e/ou ENADE'
        # Regra 02: Alunos com apenas TCC e/ou Atividade pendente podem realizar matrícula vínculo
        if not self.possui_pendencia(incluir_colacao_grau=False, incluir_enade=False, incluir_tcc=False, incluir_atividade_complementar=False):
            return None
        # Regra 03: Alunos com as duas últimas matrículas em período com situação matrícula vínculo, não podem realizar matrícula vínculo
        situacoes = set(
            self.matriculaperiodo_set.exclude(pk=self.get_ultima_matricula_periodo().pk).order_by('-id').values_list('situacao_id', flat=True)[0:2]
        )
        if len(situacoes) == 2 and situacoes == {SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL}:
            return 'As duas últimas matrículas em período letivo foram de vínculo institucional'
        # Regra 04: Alunos sem tempo hábil para terminar o curso, não podem realizar matrícula vínculo
        deve_ser_jubilado = self.deve_ser_jubilado()
        if deve_ser_jubilado:
            return deve_ser_jubilado
        return None

    def is_intercambio(self):
        return self.situacao.pk == SituacaoMatricula.INTERCAMBIO

    def is_vaga_migrada(self):
        result = False
        if self.candidato_vaga_id and self.situacao_id in (
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
        ):
            result = self.candidato_vaga.vaga is None
        return result

    def possui_vinculo(self):
        situacao_valida = (
            self.situacao.pk == SituacaoMatricula.INTERCAMBIO
            or self.situacao.pk == SituacaoMatricula.TRANCADO
            or self.situacao.pk == SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE
            or self.situacao.pk == SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL
        )
        if situacao_valida:
            return True
        else:
            return self.situacao.pk == SituacaoMatricula.MATRICULADO and not self.get_ultima_matricula_periodo().is_aberto()

    def pode_emitir_declaracao(self):
        if self.is_proitec():
            return False
        if self.curso_campus.modalidade_id is None:
            return False
        # alunos de Curso FIC anterior a 2018
        if self.curso_campus.modalidade_id == Modalidade.FIC and self.ano_letivo.ano < 2018:
            return False
        return bool(self.matriz or self.eh_aluno_minicurso())

    def pode_estagiar(self, obrigatorio: bool = False, periodo_a_considerar: int | None = None):
        """Verifica se o aluno pode estagiar conforme a resolução nº 25/2019-CONSUP.

        Aplica a regra geral de 50% de integralização ou período mínimo do
        curso (2º período ou o definido pela matriz, o que for maior).
        Quando ``periodo_a_considerar`` não é informado, utiliza o período
        da disciplina mais avançada cursada ou em curso pelo aluno.

        Args:
            obrigatorio: quando ``True``, verifica requisitos de estágio
                obrigatório (matriz deve exigi-lo).
            periodo_a_considerar: período letivo a usar nas comparações;
                calculado automaticamente quando omitido.

        Returns:
            tupla ``(bool, str)`` onde o primeiro elemento indica se o
            estágio é permitido e o segundo contém a justificativa.
        """
        if not self.matriz:
            return False, 'Aluno não tem matriz.'

        if obrigatorio and not self.matriz.exige_estagio:
            return False, 'A matriz curricular do estudante não exige estágio.'

        # Regra Geral: integralização > 50% ou cumpriu requisito de período mínimo.
        percentual_integralizacao = self.get_percentual_carga_horaria_cumprida()

        periodo_minimo_regra_geral = 2
        periodo_minimo_matriz = self.matriz.periodo_minimo_estagio_obrigatorio if obrigatorio else self.matriz.periodo_minimo_estagio_nao_obrigatorio
        periodo_minimo = max(periodo_minimo_regra_geral, periodo_minimo_matriz or 0)

        if not periodo_a_considerar:
            # Obtendo o período mais adiantado do aluno.
            ids_componentes_cumpridos = set(self.get_ids_componentes_cumpridos() + list(self.get_ids_componentes_cursando()))
            periodo_mais_adiantado = (
                ComponenteCurricular.objects.filter(
                    matriz=self.matriz, componente_id__in=ids_componentes_cumpridos, periodo_letivo__isnull=False
                ).aggregate(Max('periodo_letivo'))
            ).get('periodo_letivo__max') or 0
            periodo_a_considerar = periodo_mais_adiantado

        if percentual_integralizacao < 50 and periodo_a_considerar < periodo_minimo:
            return False, (
                f'(1) O aluno precisa ter pelo menos 50% de integralização, mas está {percentual_integralizacao:.0f}% integralizado. '
                f'Alternativamente, (2) o aluno precisa ter cursado ou estar cursando disciplinas do {periodo_minimo}º período ou posterior.'
            )

        return True, ''

    def pode_cadastrar_atividade_modalidadepraticaprofissional(self, modalidade_pp_ppc):
        if modalidade_pp_ppc.periodo_inicial:
            return self.periodo_atual >= modalidade_pp_ppc.periodo_inicial
        return True

    # COLAÇÃO DE GRAU
    def colou_grau(self):
        return self.participacaocolacaograu_set.filter(colacao_grau__deferida=True).exists()

    def get_participacao_colacao_grau(self):
        return self.participacaocolacaograu_set.first()

    def get_data_colacao_grau(self):
        participacao_colacao_grau = self.get_participacao_colacao_grau()
        return participacao_colacao_grau.colacao_grau.data_colacao if participacao_colacao_grau else self.data_colacao_grau

    # ENADE
    def cumpriu_enade(self, data_colacao_grau=None):
        return (
            not self.get_convocacoes_enade().filter(situacao__isnull=True).exists()
            and self.cumpriu_enade_ingressante()
            and self.cumpriu_enade_concluinte(data_colacao_grau=data_colacao_grau)
        )

    def cumpriu_enade_ingressante(self):
        DATA_DISPENSA_INGRESSANTE = datetime.date(2018, 8, 27)
        if (
            self.situacao_id in (SituacaoMatricula.FORMADO, SituacaoMatricula.CONCLUIDO)
            and self.dt_conclusao_curso
            and self.dt_conclusao_curso < DATA_DISPENSA_INGRESSANTE
        ):
            return True
        enade_ingressante = self.get_enade_ingressante()
        return enade_ingressante and enade_ingressante.situacao in [
            RegistroConvocacaoENADE.SITUACAO_PRESENTE,
            RegistroConvocacaoENADE.SITUACAO_DISPENSADO,
        ]

    def cumpriu_enade_concluinte(self, incluir_pratica=True, data_colacao_grau=None):
        """Verifica se o aluno cumpriu a obrigação do ENADE como concluinte.

        Checa se existe convocação para o ENADE teórico como concluinte e
        se a situação é "Presente" ou "Dispensado". Quando há um ENADE
        posterior ao ano da convocação, considera a data de colação de grau
        para determinar se o aluno deveria ter participado.

        Args:
            incluir_pratica: quando ``True``, também verifica o ENADE
                de avaliação prática.
            data_colacao_grau: data de colação de grau para comparar com
                o período de inscrição do próximo ENADE.

        Returns:
            ``True`` se o aluno cumpriu o ENADE concluinte, ``False``
            caso contrário.
        """
        enade_concluinte = self.get_enade_concluinte()
        if enade_concluinte is None or enade_concluinte.convocacao_enade is None:
            return False

        ano_proximo_enade = enade_concluinte.convocacao_enade.ano_letivo.ano + 1
        qs_proximo = ConvocacaoENADE.objects.filter(ano_letivo__ano=ano_proximo_enade, tipo_convocacao=ConvocacaoENADE.AVALIACAO_TEORICA)
        if data_colacao_grau:
            qs_proximo = qs_proximo.exclude(data_inicio_inscricao__gt=data_colacao_grau)
        proximo_enade = qs_proximo.first()

        if proximo_enade:
            colacao = ColacaoGrau.objects.filter(participacaocolacaograu__aluno_id=self.id, deferida=True).only('data_colacao').first()

            # não colou grau e data de hoje é posterior à data de início de inscrição do próximo ENADE
            if colacao is None and proximo_enade.data_inicio_inscricao and datetime.date.today() >= proximo_enade.data_inicio_inscricao:
                return False

            if colacao:
                # aluno colou grau após o início de inscrição do próximo ENADE
                if proximo_enade.data_inicio_inscricao:
                    if colacao.data_colacao >= proximo_enade.data_inicio_inscricao:
                        return False
                else:
                    # se não houver a data de início de inscrição, considerar apenas o ano do ENADE
                    if colacao.data_colacao.year != enade_concluinte.convocacao_enade.ano_letivo.ano:
                        return False

        if incluir_pratica and not self.cumpriu_enade_pratica():
            return False

        return enade_concluinte.situacao in [
            RegistroConvocacaoENADE.SITUACAO_PRESENTE,
            RegistroConvocacaoENADE.SITUACAO_DISPENSADO,
        ]

    def cumpriu_enade_pratica(self):
        enade_pratica = self.get_enade_pratica()
        # não existe obrigação de convocação para ENADE de avaliação prática, mas se o aluno for convocado precisa ter a situação regular.
        return enade_pratica is None or enade_pratica.situacao == RegistroConvocacaoENADE.SITUACAO_PRESENTE

    def get_convocacoes_enade(self, ignorar_ausencia=False):
        qs = RegistroConvocacaoENADE.objects.filter(aluno=self).order_by('tipo_convocacao', 'convocacao_enade__ano_letivo__ano')
        if ignorar_ausencia:
            qs = qs.exclude(situacao=RegistroConvocacaoENADE.SITUACAO_AUSENTE)
        return qs

    def get_convocacoes_enade_diploma(self):
        qs = self.get_convocacoes_enade(ignorar_ausencia=True)
        result = []
        # deve existir somente um ENADE ingressante
        ingressante = qs.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE).first()
        if ingressante:
            result.append(ingressante)

        # último ENADE como concluinte
        concluinte = (
            qs.filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE).order_by('-convocacao_enade__ano_letivo__ano').first()
        )
        if concluinte:
            result.append(concluinte)
        return result

    def get_enade_ingressante(self):
        return self.get_convocacoes_enade().filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_INGRESSANTE).last()

    def get_enade_concluinte(self):
        return self.get_convocacoes_enade().filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE).last()

    def get_enade_pratica(self):
        return self.get_convocacoes_enade().filter(tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE_AP).last()

    def get_pendencias_enade(self):
        result = []
        cumpriu_enade_ingressante = self.cumpriu_enade_ingressante()
        if not cumpriu_enade_ingressante:
            result.append('ENADE de ingressante não-cumprido.')
        if not self.cumpriu_enade_concluinte(incluir_pratica=False):
            result.append('ENADE de concluinte não-cumprido.')
        if not self.cumpriu_enade_pratica():
            result.append('ENADE de avaliação prática com pendência.')
        if cumpriu_enade_ingressante and self.cumpriu_enade_concluinte() and self.get_convocacoes_enade().filter(situacao__isnull=True).exists():
            result.append('Situação não informada em convocação.')
        return result

    def pode_ser_dispensado_enade(self, ignorar_pendencias=False):
        if not self.matriz_id:
            return False
        if not self.curso_campus.exige_enade:
            return False
        # aluno não concluido e todos os demais requisitos cumpridos exceto enade e colação de grau
        if not self.is_concluido() and (ignorar_pendencias or not self.possui_pendencia(incluir_colacao_grau=False, incluir_enade=False)):
            # se não cumpriu ingressante e não existe registro de ingressante
            if not self.cumpriu_enade_ingressante() and self.get_enade_ingressante() is None:
                return True
            # não inclui ENADE de prática pois não tem dispensa
            if not self.cumpriu_enade_concluinte(incluir_pratica=False):
                ultimo_ano = ConvocacaoENADE.get_ano_ultima_avaliacao_teorica()
                # não cumpriu concluinte e não existe registro em convocacao atual
                return (
                    ultimo_ano
                    and not RegistroConvocacaoENADE.objects.filter(
                        aluno_id=self.id,
                        convocacao_enade__ano_letivo__ano=ultimo_ano,
                        tipo_convocacao=RegistroConvocacaoENADE.TIPO_CONVOCACAO_CONCLUINTE,
                    ).exists()
                )
        return False

    # TCC
    def apresentou_tcc(self):
        projeto_final = ProjetoFinal.objects.filter(
            matricula_periodo__aluno=self, situacao=ProjetoFinal.SITUACAO_APROVADO, resultado_data__isnull=False
        ).first()
        if projeto_final:
            return not AssinaturaAtaEletronica.objects.filter(ata__projeto_final=projeto_final, data__isnull=True).exists()
        return False

    def get_projetos_finais(self):
        return ProjetoFinal.objects.filter(matricula_periodo__aluno=self)

    def get_projeto_final_aprovado(self):
        qs = self.get_projetos_finais().filter(situacao=ProjetoFinal.SITUACAO_APROVADO)
        return qs.exists() and qs[0] or None

    def get_projeto_final(self):
        qs = self.get_projetos_finais()
        qs_aprovado = qs.filter(situacao=ProjetoFinal.SITUACAO_APROVADO)
        return qs_aprovado.exists() and qs_aprovado.first() or (qs.exists() and qs.first() or None)

    # ATIVIDADE COMPLEMENTAR
    def get_ultima_atividade_complementar_curricular(self):
        if self.matriz.configuracao_atividade_academica:
            ids = ItemConfiguracaoAtividadeComplementar.objects.filter(configuracao=self.matriz.configuracao_atividade_academica).values_list(
                'tipo__id', flat=True
            )
            qs = self.atividadecomplementar_set.filter(tipo__id__in=ids, deferida=True).order_by('-data_atividade')
            return qs.exists() and qs[0]
        return None

    # DIPLOMA
    def get_registro_emissao_diploma(self):
        return RegistroEmissaoDiploma.objects.filter(aluno=self, cancelado=False).first()

    def get_url_matricula_online(self):
        if self.is_seriado() or self.is_modular():
            return f'/edu/pedido_matricula_seriado/{self.id}/'
        elif self.is_credito():
            return f'/edu/pedido_matricula_credito/{self.id}/'
        else:
            return ''

    def calcular_periodo_referencia(self) -> int | None:
        if not self.matriz_id or not self.matriz or not self.matriz.estrutura:
            return None
        menor_periodo_pendente = None
        estrutura = self.matriz.estrutura
        if self.is_credito():
            ids_componentes_pendentes = self.get_componentes_pendentes().values_list('id', flat=True)
            menor_periodo_pendente = (
                self.matriz.componentecurricular_set.filter(componente_id__in=ids_componentes_pendentes).aggregate(Min('periodo_letivo'))[
                    'periodo_letivo__min'
                ]
                or self.matriz.qtd_periodos_letivos
            )
        elif estrutura.tipo_avaliacao in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]:
            ultima_mp = self.matriculaperiodo_set.order_by('-ano_letivo__ano', '-periodo_letivo').first()
            if ultima_mp:
                menor_periodo_pendente = ultima_mp.periodo_matriz
        return menor_periodo_pendente

    def recalcular_periodo_matriz_periodos_letivos(self, ano_letivo=None, periodo_letivo=None):
        qs = self.get_matriculas_periodo(orderbyDesc=False)
        if ano_letivo and periodo_letivo:
            qs = qs.exclude(ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)

        periodo_atual = 1
        for mp in qs:
            mp.periodo_matriz = periodo_atual
            mp.save()
            periodo_atual = mp.get_proximo_periodo_matriz(periodo_atual)

    def identificar_registros_equivalencia(self, gerar=False):
        registros = []
        for ec in self.matriz.eq1.filter(equivalencia_componente__automatica=True):
            registros.extend(ec.identificar_registros_equivalencia(gerar=gerar, aluno=self))
        for ec in self.matriz.eq2.filter(equivalencia_componente__automatica=True):
            registros.extend(ec.identificar_registros_equivalencia(gerar=gerar, aluno=self))
        return registros

    def verificar_periodo_referencia_em_periodos_letivos(self, corrigir_periodo=None):
        ajustes = []
        mps = list(self.get_matriculas_periodo().values_list('ano_letivo__ano', 'periodo_letivo', 'periodo_matriz', 'situacao', 'pk'))
        mps.reverse()
        periodo_esperado = 1 if self.ano_letivo.ano == mps[0][0] and self.periodo_letivo == mps[0][1] else mps[0][2]
        for ano, periodo_letivo, periodo_matriz, situacao, pk in mps:
            if periodo_matriz != periodo_esperado:
                if corrigir_periodo == pk or corrigir_periodo is True:
                    self.get_matriculas_periodo().filter(pk=pk).update(periodo_matriz=periodo_esperado)
                else:
                    ajustes.append((f'{ano}/{periodo_letivo}', periodo_matriz, periodo_esperado, pk))
            if situacao in (SituacaoMatriculaPeriodo.APROVADO, SituacaoMatriculaPeriodo.DEPENDENCIA):
                periodo_esperado = min(periodo_esperado + 1, self.matriz.qtd_periodos_letivos)
        return ajustes

    def atualizar_periodo_referencia(self):
        periodo = self.calcular_periodo_referencia()
        if periodo is not None:
            self.periodo_atual = periodo
        self.save()

    def is_credito(self):
        return self.matriz and self.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_CREDITO

    def is_seriado(self):
        return self.matriz and self.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_SERIADO

    def is_modular(self):
        return self.matriz and self.matriz.is_regime_modular()

    def is_fic(self):
        return self.matriz and self.matriz.estrutura.tipo_avaliacao == EstruturaCurso.TIPO_AVALIACAO_FIC

    def is_proitec(self):
        return self.matriz and self.matriz.estrutura.proitec

    def is_pronatec(self):
        return self.curso_campus.diretoria.tipo == Diretoria.TIPO_PRONATEC

    def is_sica(self):
        if 'sica' in settings.INSTALLED_APPS:
            return self.historico_set.exists()
        return False

    def is_qacademico(self):
        return self.codigo_academico and not self.matriz_id and not self.is_sica()

    def get_ultima_turma_cursada(self):
        qs = self.matriculaperiodo_set.filter(turma__isnull=False).order_by('-id')
        if qs:
            return qs[0].turma
        return None

    def pode_matricula_online(self):
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        com_vinculo = False
        aberto = False
        matriculado = False
        vinculo = False
        if ultima_matricula_periodo:
            aberto = ultima_matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.EM_ABERTO
            matriculado = ultima_matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.MATRICULADO
            vinculo = ultima_matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL

        if self.situacao_id in [
            SituacaoMatricula.MATRICULADO,
            SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
            SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
            SituacaoMatricula.TRANCADO,
            SituacaoMatricula.INTERCAMBIO,
        ]:
            com_vinculo = True

        return (
            self.matriz
            and com_vinculo
            and (aberto or matriculado or vinculo)
            and self.matriculaperiodo_set.all().count() > 1
            and self.get_configuracao_pedido_matricula_ativa()
        )

    def get_configuracao_pedido_matricula_ativa(self):
        hoje = datetime.date.today()
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()

        # pedidos de matricula indeferidos por cancelamento de configuração
        configuracoes_canceladas = Q(pedidomatricula__pedidomatriculadiario__motivo=PedidoMatriculaDiario.MOTIVO_CANCELADO)

        qs = self.curso_campus.configuracaopedidomatricula_set.filter(
            data_inicio__lte=hoje,
            data_fim__gte=hoje,
            ano_letivo=ultima_matricula_periodo.ano_letivo,
            periodo_letivo=ultima_matricula_periodo.periodo_letivo,
        ).exclude(configuracoes_canceladas)

        # configuração sem restrição de público
        publico_sem_restricao = Q(turmas__isnull=True, diarios__isnull=True, alunos__isnull=True)

        # configuração com restrição de público
        publico_com_restricao = (
            Q(turmas__diario__matriculadiario__matricula_periodo__aluno_id=self.id)
            | Q(diarios__matriculadiario__matricula_periodo__aluno_id=self.id)
            | Q(alunos__id=self.id)
        )

        return qs.filter(publico_sem_restricao | publico_com_restricao).first()

    def get_ch_aproveitada(self):
        ids_componentes_matriz = self.matriz.get_ids_componentes()
        suap = (
            AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=self.id, componente_curricular__componente_id__in=ids_componentes_matriz)
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )
        q_academico = (
            MatriculaDiarioResumida.objects.filter(
                matricula_periodo__aluno_id=self.id,
                situacao=MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                equivalencia_componente__componente_id__in=ids_componentes_matriz,
            )
            .aggregate(Sum('equivalencia_componente__componente__ch_qtd_creditos'))
            .get('equivalencia_componente__componente__ch_qtd_creditos__sum')
            or 0
        )
        return mask_ch_componente(suap) + q_academico

    def get_ch_certificada(self):
        ids_componentes_matriz = self.matriz.get_ids_componentes()
        suap = (
            CertificacaoConhecimento.objects.filter(
                matricula_periodo__aluno_id=self.id, componente_curricular__componente_id__in=ids_componentes_matriz
            )
            .aggregate(Sum('componente_curricular__componente__ch_hora_relogio'))
            .get('componente_curricular__componente__ch_hora_relogio__sum')
            or 0
        )
        q_academico = (
            MatriculaDiarioResumida.objects.filter(
                matricula_periodo__aluno_id=self.id,
                situacao=MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                equivalencia_componente__componente_id__in=ids_componentes_matriz,
            )
            .aggregate(Sum('equivalencia_componente__componente__ch_qtd_creditos'))
            .get('equivalencia_componente__componente__ch_qtd_creditos__sum')
            or 0
        )
        return mask_ch_componente(suap) + q_academico

    def get_ch_certificada_ou_aproveitada(self):
        return self.get_ch_aproveitada() + self.get_ch_certificada()

    def get_percentual_ch_certificada_ou_aproveitada(self):
        return round(self.get_ch_certificada_ou_aproveitada() * 100 / self.matriz.get_ch_certificavel_aproveitavel(), 2)

    def get_creditos_certificados(self):
        ids_componentes_matriz = self.matriz.get_ids_componentes()
        suap = (
            CertificacaoConhecimento.objects.filter(
                matricula_periodo__aluno_id=self.id, componente_curricular__componente_id__in=ids_componentes_matriz
            )
            .aggregate(Sum('componente_curricular__componente__ch_qtd_creditos'))
            .get('componente_curricular__componente__ch_qtd_creditos__sum')
            or 0
        )
        q_academico = (
            MatriculaDiarioResumida.objects.filter(
                matricula_periodo__aluno_id=self.id,
                situacao=MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                equivalencia_componente__componente_id__in=ids_componentes_matriz,
            )
            .aggregate(Sum('equivalencia_componente__componente__ch_qtd_creditos'))
            .get('equivalencia_componente__componente__ch_qtd_creditos__sum')
            or 0
        )
        return suap + q_academico

    def get_creditos_aproveitados(self):
        ids_componentes_matriz = self.matriz.get_ids_componentes()
        suap = (
            AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=self.id, componente_curricular__componente_id__in=ids_componentes_matriz)
            .aggregate(Sum('componente_curricular__componente__ch_qtd_creditos'))
            .get('componente_curricular__componente__ch_qtd_creditos__sum')
            or 0
        )
        q_academico = (
            MatriculaDiarioResumida.objects.filter(
                matricula_periodo__aluno_id=self.id,
                situacao=MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                equivalencia_componente__componente_id__in=ids_componentes_matriz,
            )
            .aggregate(Sum('equivalencia_componente__componente__ch_qtd_creditos'))
            .get('equivalencia_componente__componente__ch_qtd_creditos__sum')
            or 0
        )
        return suap + q_academico

    def get_creditos_certificados_ou_aproveitados(self):
        return self.get_creditos_certificados() + self.get_creditos_aproveitados()

    def get_ultimo_procedimento_matricula(self):
        return ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=self).order_by('-id')[0]

    def revogar_acesso(self):
        msg = ''
        email_academico = self.email_academico
        email_google_classroom = self.email_google_classroom
        self.email_academico = ''
        self.email_google_classroom = ''
        self.save(sync_user=False)
        try:
            conf = get_ldap_conf()
            # Vai retirar do usuário do google classroom e do academico
            aluno_existe_ad = conf.limpar_emails_academico_e_google(self) if conf else False
            if email_academico and aluno_existe_ad:
                EmailBlockList.objects.get_or_create(email=email_academico)
            if email_google_classroom and aluno_existe_ad:
                EmailBlockList.objects.get_or_create(email=email_google_classroom)
        except Exception as e:
            msg = f'{self} - {e}'
            capture_exception(e)
        return msg

    # utilizada apenas no seriado
    def get_turmas_matricula_online(self, turma_indisponiveis_com_motivo=None, restringir_por_convenio=False):
        ids_componentes_cumpridos = self.get_ids_componentes_cumpridos()
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        turma_periodo_atual = ultima_matricula_periodo.turma
        turmas = []
        if turma_periodo_atual:
            # inserindo a turma já salva nos períodos de matrícula anteriores
            turmas.append(turma_periodo_atual)
        else:
            # obtendo as turmas disponvíveis do periodo atual
            turmas = Turma.objects.filter(
                ano_letivo_id=ultima_matricula_periodo.ano_letivo_id,
                periodo_letivo=ultima_matricula_periodo.periodo_letivo,
                curso_campus_id=self.curso_campus_id,
                periodo_matriz=self.periodo_atual,
                matriz_id=self.matriz_id,
            )
            if restringir_por_convenio:
                if self.convenio_id:
                    turmas = turmas.filter(convenio_id=self.convenio_id)
                else:
                    turmas = turmas.filter(convenio__isnull=True)

            # validando a disponibilidade de turmas priorizando as turmas do turno do aluno
            turmas_turno_aluno = turmas.filter(turno=self.turno)
            if turmas_turno_aluno.exists():
                turmas = turmas_turno_aluno

            # removendo turmas que não são do polo do aluno
            if self.polo:
                turmas = turmas.filter(polo=None) | turmas.filter(polo=self.polo)
                turmas = turmas.distinct()

            # removendo turmas incompatíveis com a anterior caso tenha sido informado na configuracao
            configuracao_pedido_matricula_ativa = self.get_configuracao_pedido_matricula_ativa()
            if configuracao_pedido_matricula_ativa:
                if configuracao_pedido_matricula_ativa.impedir_troca_turma:
                    turma_anterior = self.get_turma_periodo_anterior()
                    if turma_anterior:
                        turmas_compativeis = turmas.filter(sequencial=turma_anterior.sequencial)
                        if turmas_compativeis.exists():
                            turmas = turmas_compativeis
                if configuracao_pedido_matricula_ativa.turmas_ofertadas.exists():
                    turmas = turmas.filter(pk__in=configuracao_pedido_matricula_ativa.turmas_ofertadas.values_list('pk', flat=True))

        if turmas:
            # todos os trechos que possuem a verificacao da variável "turma_indisponiveis_com_motivo" se referem ao retorno da lista de componentes pendentes que não
            # estarão disponíveis para o aluno na matrícula online na turma passada
            indisponiveis_com_motivo = []

            # pre requisitos
            # obtendo cc's do periodo atual
            componentes_curriculares_periodo_atual = ComponenteCurricular.objects.filter(
                matriz=self.matriz, periodo_letivo=self.periodo_atual
            ).order_by('componente_id')
            # obtendo ids dos componentes pendentes anterior ao periodo atual
            periodos = list(range(1, self.periodo_atual))
            id_componentes_pedentes = self.get_componentes_pendentes(periodos, True).values_list('id', flat=True)
            id_componentes_disponiveis = []
            for componente_curricular_periodo_atual in componentes_curriculares_periodo_atual:
                # verificando se existe algum pre_requisito pendente
                if not componente_curricular_periodo_atual.pre_requisitos.filter(componente_id__in=id_componentes_pedentes):
                    # adicionando na lista de ids_componentes_disponiveis
                    id_componentes_disponiveis.append(componente_curricular_periodo_atual.componente.id)
                elif turma_indisponiveis_com_motivo:
                    componente_curricular_periodo_atual.motivo = 'Pré-requisito não atendido'
                    indisponiveis_com_motivo.append(componente_curricular_periodo_atual)

            # Criando uma lista diarios para cada turma contendo apenas aqueles cujos componentes possam ser cursados pelo aluno
            for turma in turmas:
                # adicionando os componentes aptativos, ou seja, aqueles sem definição de período na matriz
                id_componentes_optativos = list(
                    turma.diario_set.filter(componente_curricular__periodo_letivo__isnull=True).values_list(
                        'componente_curricular__componente_id', flat=True
                    )
                )
                # correquisitos
                id_componentes_disponiveis_prerequisitos = copy.copy(id_componentes_disponiveis)
                # processando correquisitos com base nos ids após processamento dos pre e em cada turma disponível
                id_componentes_disponiveis_correquisitos = self.get_id_componentes_correquisitos_processados(id_componentes_disponiveis, turma=turma)
                if turma_indisponiveis_com_motivo == turma:
                    ids_indisponiveis = diferenca_listas(id_componentes_disponiveis_prerequisitos, id_componentes_disponiveis_correquisitos)
                    for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                        componente_curricular.motivo = 'Co-requisito não disponível'
                        indisponiveis_com_motivo.append(componente_curricular)

                # diários cujos componentes passaram pelo processsamento do pre e correquisitos
                qs_diarios = turma.diario_set.filter(
                    componente_curricular__componente_id__in=id_componentes_disponiveis_correquisitos + id_componentes_optativos
                )
                if turma_indisponiveis_com_motivo == turma:
                    ids_componentes_disponiveis_diarios = qs_diarios.values_list('componente_curricular__componente_id', flat=True)
                    ids_indisponiveis = diferenca_listas(id_componentes_disponiveis_correquisitos, ids_componentes_disponiveis_diarios)
                    for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                        componente_curricular.motivo = 'Diário não gerado nesta turma'
                        indisponiveis_com_motivo.append(componente_curricular)

                # removendo diários que o aluno já se matriculou em períodos de renovação de matricula anteriores
                ids_componentes_matriculados = ultima_matricula_periodo.get_matriculas_diario().values_list(
                    'diario__componente_curricular__componente_id', flat=True
                )
                qs_diarios = qs_diarios.exclude(componente_curricular__componente_id__in=ids_componentes_matriculados)

                # diarios que possuem horário
                if self.curso_campus.modalidade.pk in [Modalidade.INTEGRADO, Modalidade.SUBSEQUENTE]:
                    # diarios do subsequente nao precisam ter horarios definidos
                    qs_diarios_com_horarios = qs_diarios.filter(pk__gt=0)
                else:
                    qs_diarios_com_horarios = qs_diarios.filter(horarioauladiario__isnull=False)

                tipos_componentes_permitidos_sem_horario = [
                    ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                    ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                    ComponenteCurricular.TIPO_SEMINARIO,
                ]
                if turma_indisponiveis_com_motivo == turma:
                    qs_diarios = qs_diarios.filter(horarioauladiario__isnull=True)
                    qs_diarios = qs_diarios.exclude(
                        componente_curricular__componente_id__in=qs_diarios_com_horarios.values_list(
                            'componente_curricular__componente_id', flat=True
                        )
                    )
                    qs_diarios = qs_diarios.exclude(componente_curricular__tipo__in=tipos_componentes_permitidos_sem_horario)
                    qs_diarios = qs_diarios.exclude(turno__descricao='EAD')
                    ids_indisponiveis = qs_diarios.values_list('componente_curricular__componente_id', flat=True)
                    for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                        componente_curricular.motivo = 'Diário sem horário de aula definido'
                        indisponiveis_com_motivo.append(componente_curricular)
                    return indisponiveis_com_motivo
                else:
                    # diarios que não possuem horário mas são de prática profissional
                    qs_diarios_com_pratica_profissional = qs_diarios.filter(componente_curricular__tipo__in=tipos_componentes_permitidos_sem_horario)
                    # diarios do turno ead
                    qs_diarios_ead = qs_diarios.filter(turno__descricao='EAD')
                    qs_diarios = qs_diarios_com_horarios | qs_diarios_com_pratica_profissional | qs_diarios_ead
                    turma.diarios = qs_diarios.exclude(componente_curricular__componente_id__in=ids_componentes_cumpridos).distinct()
        return turmas

    def pode_ser_matriculado_no_diario(self, diario, ignorar_quebra_requisito=False):
        """Verifica se o aluno pode ser matriculado no diário informado.

        Checa se já existe matrícula ativa no mesmo componente em outro diário,
        se o componente já foi cumprido pelo aluno e, em caso negativo, delega a
        validação a :meth:`pode_cursar_componente_curricular`.

        Args:
            diario: diário no qual se deseja matricular o aluno.
            ignorar_quebra_requisito: quando ``True``, ignora pré e correquisitos.

        Returns:
            tupla ``(pode, mensagem)`` onde ``pode`` é booleano e ``mensagem``
            contém a justificativa em caso de impedimento.
        """
        if MatriculaDiario.objects.filter(
            matricula_periodo__aluno=self,
            diario__ano_letivo_id=diario.ano_letivo_id,
            diario__periodo_letivo=diario.periodo_letivo,
            diario__componente_curricular__componente_id=diario.componente_curricular.componente_id,
            situacao=MatriculaDiario.SITUACAO_CURSANDO,
        ).exists():
            return False, f'O aluno está cursando o componente {diario.componente_curricular.componente} em outro diário.'
        if diario.componente_curricular.componente_id in self.get_ids_componentes_cumpridos():
            return False, f'O aluno já cursou o componente {diario.componente_curricular.componente}.'
        componente_curricular = self.matriz.componentecurricular_set.filter(componente_id=diario.componente_curricular.componente_id).first()
        if componente_curricular:
            return self.pode_cursar_componente_curricular(
                componente_curricular, False, ignorar_prerequisito=ignorar_quebra_requisito, ignorar_corequisito=ignorar_quebra_requisito
            )
        else:
            return self.pode_cursar_componente_curricular(
                diario.componente_curricular, True, ignorar_prerequisito=ignorar_quebra_requisito, ignorar_corequisito=ignorar_quebra_requisito
            )

    def pode_cursar_componente_curricular(self, componente_curricular, outra_matriz=False, ignorar_prerequisito=False, ignorar_corequisito=False):
        ids_componentes_cursando = self.get_ids_componentes_cursando()
        ids_componentes_pagos = self.get_ids_componentes_cumpridos(componente_curricular.get_corequisitos())
        equivalentes = self.get_siglas_componentes_equivalentes_em_curso()

        for co_requisito in componente_curricular.co_requisitos.all():
            if (
                co_requisito.componente.pk not in ids_componentes_cursando
                and co_requisito.componente.pk not in ids_componentes_pagos
                and co_requisito.componente.sigla not in equivalentes
            ):
                if outra_matriz or ignorar_corequisito:
                    return True, 'O aluno quebrará os correquisitos necessários para essa disciplina.'
                return False, 'O aluno não cursou ou não está cursando os correquisitos necessários para essa disciplina.'
        pre_requisitos = componente_curricular.get_pre_requisitos()

        ids_componentes_pagos_global = list(self.get_ids_componentes_cumpridos(pre_requisitos))
        for id_componente_pago in self.get_ids_componentes_extra_curriculares_cumpridos(excluir_equivalencias=False):
            if id_componente_pago in pre_requisitos:
                ids_componentes_pagos_global.append(id_componente_pago)

        if set(pre_requisitos) != set(ids_componentes_pagos_global):
            if outra_matriz or ignorar_prerequisito:
                return True, 'O aluno quebrará os pré-requistos necessários para essa disciplina.'
            return False, 'O aluno não cursou todos os pré-requisitos necessários para essa disciplina.'

        return True, ''

    # utilizada para crédito e pelas dependecias do seriado
    def get_diarios_pendentes_matricula_online(
        self,
        apenas_obrigatorias=False,
        apenas_optativas=False,
        ids_componentes_diarios_obrigatorias=None,
        retorno_indisponiveis_com_motivo=False,
        ignorar_pendencia_horario=False,
        restringir_por_convenio=False,
    ):
        # todos os trechos que possuem a verificacao da variável "retorno_indisponiveis_com_motivo" se referem ao retorno da lista de componentes pendentes que não
        # estarão disponíveis para o aluno na matrícula online
        if ids_componentes_diarios_obrigatorias is None:
            ids_componentes_diarios_obrigatorias = []
        indisponiveis_com_motivo = []

        ultima_matricula_periodo = self.get_ultima_matricula_periodo()

        # calculando a quantidade de períodos para a busca de componentes pendentes do aluno
        periodos = []
        if self.is_seriado() or self.is_modular():
            # no SERIADO e MODULAR serão verificados os componentes anteriores ao periodo atual(DEPENDÊNCIAS)
            periodos = list(range(1, self.periodo_atual))
            if not periodos:
                return []
        if self.is_credito():
            # no CRÉDITO
            # nas obrigatorias
            # se foi definido a qtd_max_periodos_subsequentes na estrutura do curso
            # serão verificados os componentes do periodo atual
            # (menor período dos componentes na matriz do aluno que está pendente) somados ao número máximo de períodos
            # subsquentes que a estrutura do seu curso permite
            # se não, serão de todos os períodos possíveis

            # se for apenas os componentes optativos não existem períodos a serem verificados,
            # serão todos os componentes optativos

            if apenas_obrigatorias and self.matriz.estrutura.qtd_max_periodos_subsequentes:
                periodos = list(range(1, (self.periodo_atual + self.matriz.estrutura.qtd_max_periodos_subsequentes) + 1))

        # obtendo ids dos componentes pendentes segundo regra explicada acima
        ids_componentes_pendentes = []
        for componente in self.get_componentes_pendentes(periodos, apenas_obrigatorias, apenas_optativas):
            ids_componentes_pendentes.append(componente.pk)
        for componente in self.get_componentes_em_diarios_pendentes():
            ids_componentes_pendentes.append(componente.pk)

        # pre requisitos
        # obtendo cc's do periodo atual
        componentes_curriculares_pendentes = ComponenteCurricular.objects.filter(
            matriz=self.matriz, componente_id__in=ids_componentes_pendentes
        ).order_by('componente_id')

        # obtendo todos os componentes pendentes para o caso de apenas_optativas
        if apenas_optativas:
            ids_componentes_pendentes = self.get_componentes_pendentes(periodos).values_list('id', flat=True)

        id_componentes_disponiveis = []
        # percorrendo cc pendentes
        for componente_curricular_pendente in componentes_curriculares_pendentes:
            # verificando se existe algum pre_requisito pendente
            if not componente_curricular_pendente.pre_requisitos.filter(componente_id__in=ids_componentes_pendentes):
                # adicionando na lista de ids_componentes_disponiveis
                id_componentes_disponiveis.append(componente_curricular_pendente.componente.id)
            elif retorno_indisponiveis_com_motivo:
                componente_curricular_pendente.motivo = 'Pré-requisito não atendido'
                indisponiveis_com_motivo.append(componente_curricular_pendente)

        # correquisitos
        id_componentes_disponiveis_prerequisitos = copy.copy(id_componentes_disponiveis)

        # processando correquisitos com base nos ids após processamento dos pre e nos componentes disponíveis obrigatórios
        id_componentes_disponiveis_pos_correquisitos = self.get_id_componentes_correquisitos_processados(
            id_componentes_disponiveis, ids_componentes_diarios_obrigatorias=ids_componentes_diarios_obrigatorias
        )

        if retorno_indisponiveis_com_motivo:
            ids_indisponiveis = diferenca_listas(id_componentes_disponiveis_prerequisitos, id_componentes_disponiveis_pos_correquisitos)
            for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                componente_curricular.motivo = 'Co-requisito não disponível'
                indisponiveis_com_motivo.append(componente_curricular)

        # buscando diários para os componentes diponíveis
        qs_diarios = Diario.objects.filter(
            componente_curricular__componente_id__in=id_componentes_disponiveis_pos_correquisitos,
            turma__ano_letivo=ultima_matricula_periodo.ano_letivo,
            turma__periodo_letivo=ultima_matricula_periodo.periodo_letivo,
            turma__curso_campus__diretoria__setor__uo_id=self.curso_campus.diretoria.setor.uo.id,
        )

        if restringir_por_convenio:
            if self.convenio_id:
                qs_diarios = qs_diarios.filter(turma__convenio_id=self.convenio_id)
            else:
                qs_diarios = qs_diarios.filter(turma__convenio__isnull=True)

        if retorno_indisponiveis_com_motivo:
            ids_componentes_disponiveis_diarios = qs_diarios.values_list('componente_curricular__componente_id', flat=True)
            ids_indisponiveis = diferenca_listas(id_componentes_disponiveis_pos_correquisitos, ids_componentes_disponiveis_diarios)
            for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                componente_curricular.motivo = 'Diário não gerado na diretoria do seu curso'
                indisponiveis_com_motivo.append(componente_curricular)

        # Para o regime seriado e modular, será possível solicitar matrícula em disciplinas equivalentes
        if self.is_seriado() or self.is_modular() or self.is_credito():
            ids_componentes_equivalentes = []
            ids_componentes_nao_ofertados = set(id_componentes_disponiveis_pos_correquisitos) - set(
                qs_diarios.values_list('componente_curricular__componente', flat=True)
            )
            for componente_id in ids_componentes_nao_ofertados:
                ids_componentes_equivalentes.extend(Componente.get_ids_componentes_equivalentes(componente_id, self.matriz_id))
            qs_diarios = qs_diarios | Diario.objects.filter(
                componente_curricular__componente_id__in=ids_componentes_equivalentes,
                turma__ano_letivo=ultima_matricula_periodo.ano_letivo,
                turma__periodo_letivo=ultima_matricula_periodo.periodo_letivo,
                turma__curso_campus__diretoria__setor__uo_id=self.curso_campus.diretoria.setor.uo.id,
            )

        # removendo diários que o aluno já se matriculou em períodos de renovação de matricula anteriores
        ids_componentes_matriculados = ultima_matricula_periodo.get_matriculas_diario().values_list(
            'diario__componente_curricular__componente_id', flat=True
        )
        qs_diarios = qs_diarios.exclude(componente_curricular__componente_id__in=ids_componentes_matriculados)

        # removendo diários de outros cursos caso esteja configurado no pedido de renovação de matrícula
        configuracao_pedido_matricula_ativa = self.get_configuracao_pedido_matricula_ativa()
        if configuracao_pedido_matricula_ativa:
            if configuracao_pedido_matricula_ativa.restringir_por_curso:
                qs_diarios = qs_diarios.filter(turma__curso_campus_id=self.curso_campus_id)
            if configuracao_pedido_matricula_ativa.turmas_ofertadas.exists():
                qs_diarios = qs_diarios.filter(turma__in=configuracao_pedido_matricula_ativa.turmas_ofertadas.values_list('pk', flat=True))
            if configuracao_pedido_matricula_ativa.diarios_ofertados.exists():
                qs_diarios = qs_diarios.filter(pk__in=configuracao_pedido_matricula_ativa.diarios_ofertados.values_list('pk', flat=True))

        # removendo diários que não são do polo do aluno
        if self.polo:
            if retorno_indisponiveis_com_motivo:
                ids_componentes_disponiveis_diarios = qs_diarios.values_list('componente_curricular__componente_id', flat=True)
                ids_componentes_disponiveis_diarios_polo = qs_diarios.filter(turma__polo=self.polo).values_list(
                    'componente_curricular__componente_id', flat=True
                )
                ids_indisponiveis = diferenca_listas(ids_componentes_disponiveis_diarios, ids_componentes_disponiveis_diarios_polo)

                ids_componentes_disponiveis_diarios_sem_polo = qs_diarios.filter(turma__polo=None).values_list(
                    'componente_curricular__componente_id', flat=True
                )
                ids_indisponiveis = diferenca_listas(ids_indisponiveis, ids_componentes_disponiveis_diarios_sem_polo)

                for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                    componente_curricular.motivo = 'Diário não gerado para seu polo'
                    indisponiveis_com_motivo.append(componente_curricular)

            qs_diarios = qs_diarios.filter(turma__polo=self.polo) | qs_diarios.filter(turma__polo=None)
            qs_diarios = qs_diarios.distinct()

        # diarios que possuem horário
        if ignorar_pendencia_horario:
            qs_diarios_com_horarios = qs_diarios.filter(pk__gt=0)
        else:
            qs_diarios_com_horarios = qs_diarios.filter(horarioauladiario__isnull=False)

        tipos_componentes_permitidos_sem_horario = [
            ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
            ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
            ComponenteCurricular.TIPO_SEMINARIO,
        ]
        if retorno_indisponiveis_com_motivo:
            qs_diarios = qs_diarios.filter(horarioauladiario__isnull=True)
            qs_diarios = qs_diarios.exclude(
                componente_curricular__componente_id__in=qs_diarios_com_horarios.values_list('componente_curricular__componente_id', flat=True)
            )
            qs_diarios = qs_diarios.exclude(componente_curricular__tipo__in=tipos_componentes_permitidos_sem_horario)
            qs_diarios = qs_diarios.exclude(turno__descricao='EAD')
            ids_indisponiveis = qs_diarios.values_list('componente_curricular__componente_id', flat=True)
            for componente_curricular in self.get_componentes_curriculares_por_ids(ids_indisponiveis):
                componente_curricular.motivo = 'Diário sem horário de aula definido'
                indisponiveis_com_motivo.append(componente_curricular)
            return indisponiveis_com_motivo
        else:
            # diarios que não possuem horário mas são de prática profissional
            qs_diarios_com_pratica_profissional = qs_diarios.filter(componente_curricular__tipo__in=tipos_componentes_permitidos_sem_horario)
            # diarios do turno ead
            qs_diarios_ead = qs_diarios.filter(turno__descricao='EAD')
            qs_diarios = qs_diarios_com_horarios | qs_diarios_com_pratica_profissional | qs_diarios_ead
            return qs_diarios.distinct().order_by('componente_curricular__periodo_letivo', 'componente_curricular__componente__descricao_historico')

    # função recursiva para o cálculo dos co-requisitos
    def get_id_componentes_correquisitos_processados(
        self, id_componentes_disponiveis_prerequisitos, turma=None, ids_componentes_diarios_obrigatorias=None
    ):
        # obtendo cc da lista de ids_componentes_disponiveis. Na primeira vez, chegou após o processamento dos pre, e depois após processamento dos correquisitos
        if ids_componentes_diarios_obrigatorias is None:
            ids_componentes_diarios_obrigatorias = []
        componentes_curriculares_disponiveis = ComponenteCurricular.objects.filter(
            componente_id__in=id_componentes_disponiveis_prerequisitos, matriz=self.matriz
        )
        # obtendo ids dos componenets cumpridos pelo aluno
        ids_componentes_cumpridos = self.get_ids_componentes_cumpridos()
        ids_componentes_cursando = self.get_ids_componentes_cursando()
        # percorrendo a lista para verificar os correquisitos
        for cc_disponivel in componentes_curriculares_disponiveis:
            # obtendo lista de ids do correquisitos do cc_disponivel
            ids_correquisitos = cc_disponivel.co_requisitos.all().values_list('componente_id', flat=True).order_by('componente_id')
            if ids_correquisitos:
                # percorrendo a lista de correquisitos
                for id_correquisito in ids_correquisitos:
                    remover = False
                    # caso aluno de curso do regime SERIADO
                    if self.is_seriado() or self.is_modular():
                        # ativando flag para remover componente que seus correquisitos que não estejam nos componentes disponíveis
                        # e nem na lista de componentes cumpridos e que não estão sendo cursadas
                        if (
                            id_correquisito not in id_componentes_disponiveis_prerequisitos
                            and id_correquisito not in ids_componentes_cumpridos
                            and id_correquisito not in ids_componentes_cursando
                        ):
                            remover = True
                        else:
                            # ativando flag para remover componente que seus correquisitos não possuam diários com HORÁRIOS DEFINIDOS na turma passada
                            if (
                                turma
                                and not turma.diario_set.filter(
                                    componente_curricular__componente_id=id_correquisito, horarioauladiario__isnull=False
                                ).exists()
                            ):
                                remover = True

                    # caso aluno de curso do regime CREDITO
                    if self.is_credito():
                        # ativando flag para remover componente que seus correquisitos NÃO estejam em id_componentes_disponiveis_prerequisitos ou ids_componentes_diarios_obrigatorias E não foram pagos e que não estão sendo cursadas
                        if (
                            not (
                                id_correquisito in id_componentes_disponiveis_prerequisitos or id_correquisito in ids_componentes_diarios_obrigatorias
                            )
                            and id_correquisito not in ids_componentes_cumpridos
                            and id_correquisito not in ids_componentes_cursando
                        ):
                            remover = True
                        else:
                            # ativando flag para remover componente que seus correquisitos não possuam diários com HORÁRIOS DEFINIDOS
                            qs_diarios = Diario.objects.filter(
                                componente_curricular__componente_id=id_correquisito,
                                turma__ano_letivo=self.get_ultima_matricula_periodo().ano_letivo,
                                turma__periodo_letivo=self.get_ultima_matricula_periodo().periodo_letivo,
                                turma__curso_campus__diretoria=self.curso_campus.diretoria,
                            )

                            qs_diarios = (
                                qs_diarios.filter(horarioauladiario__isnull=False)
                                | qs_diarios.filter(turno__descricao='EAD')
                                | qs_diarios.filter(
                                    componente_curricular__tipo__in=[
                                        ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                                        ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                                        ComponenteCurricular.TIPO_SEMINARIO,
                                    ]
                                )
                            )

                            if self.polo:
                                qs_diarios = qs_diarios.filter(turma__polo=self.polo) | qs_diarios.filter(turma__polo__isnull=True)

                            if not qs_diarios.exists() and id_correquisito not in ids_componentes_cumpridos:
                                remover = True

                    # caso a flag remover seja True e ainda exista id para ser removido de id_componentes_disponiveis_prerequisitos
                    if remover and len(id_componentes_disponiveis_prerequisitos):
                        # removendo id de id_componentes_disponiveis_prerequisitos
                        if cc_disponivel.componente.id in id_componentes_disponiveis_prerequisitos:
                            id_componentes_disponiveis_prerequisitos.remove(cc_disponivel.componente.id)
                        # chamando novamente a função para testar se a remocão dos id do componente não irá influenciar em todas as validações acima
                        self.get_id_componentes_correquisitos_processados(
                            id_componentes_disponiveis_prerequisitos, turma, ids_componentes_diarios_obrigatorias
                        )

        return id_componentes_disponiveis_prerequisitos

    def componentes_nao_disponiveis_matricula_online(self, optativas, turma):
        if self.is_credito():
            if optativas:
                return self.get_diarios_pendentes_matricula_online(apenas_optativas=True, retorno_indisponiveis_com_motivo=True)
            else:
                if self.matriz.estrutura.qtd_max_periodos_subsequentes:
                    periodos = list(range(1, (self.periodo_atual + self.matriz.estrutura.qtd_max_periodos_subsequentes) + 1))
                    componentes_pendentes_ate_qtd_periodos = self.get_componentes_pendentes(periodos=periodos, apenas_obrigatorias=True)
                    componentes_pendentes_pos_qtd_periodos = self.get_componentes_pendentes(apenas_obrigatorias=True).exclude(
                        id__in=componentes_pendentes_ate_qtd_periodos.values_list('id', flat=True)
                    )
                    componentes_nao_disponiveis_motivo = self.get_diarios_pendentes_matricula_online(
                        apenas_obrigatorias=True, retorno_indisponiveis_com_motivo=True
                    )

                    for componente_curricular in ComponenteCurricular.objects.filter(
                        matriz=self.matriz, componente_id__in=componentes_pendentes_pos_qtd_periodos
                    ).order_by('componente_id'):
                        componente_curricular.motivo = 'Quantidade máxima de períodos subsequentes para cursar disciplinas'
                        componentes_nao_disponiveis_motivo.append(componente_curricular)
                else:
                    componentes_nao_disponiveis_motivo = self.get_diarios_pendentes_matricula_online(
                        apenas_obrigatorias=True, retorno_indisponiveis_com_motivo=True
                    )

                return sorted(componentes_nao_disponiveis_motivo, key=operator.methodcaller('get_periodo_letivo'))
        elif self.is_seriado() or self.is_modular():
            if turma:
                return self.get_turmas_matricula_online(turma)
            else:
                componentes_nao_disponiveis_motivo = self.get_diarios_pendentes_matricula_online(
                    apenas_obrigatorias=True, retorno_indisponiveis_com_motivo=True
                )
                return sorted(componentes_nao_disponiveis_motivo, key=operator.methodcaller('get_periodo_letivo'))

    def get_diarios_eletivas_matricula_online(self, restringir_mesmo_curso):
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        qs_diarios = Diario.objects.filter(
            turma__ano_letivo=ultima_matricula_periodo.ano_letivo,
            turma__periodo_letivo=ultima_matricula_periodo.periodo_letivo,
            turma__curso_campus__diretoria=self.curso_campus.diretoria,
        )
        qs_diarios = qs_diarios.filter(turma__curso_campus__modalidade__nivel_ensino=self.curso_campus.modalidade.nivel_ensino)
        qs_diarios = qs_diarios.exclude(componente_curricular__componente__in=self.matriz.get_ids_componentes())

        # diarios que possuem horário
        qs_diarios_com_horarios = qs_diarios.filter(horarioauladiario__isnull=False)

        # diarios que não possuem horário mas são de prática profissional
        qs_diarios_com_pratica_profissional = qs_diarios.filter(
            componente_curricular__tipo__in=[
                ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL,
                ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO,
                ComponenteCurricular.TIPO_SEMINARIO,
            ]
        )

        # diarios do turno ead
        qs_diarios_ead = qs_diarios.filter(turno__descricao='EAD')

        qs_diarios = qs_diarios_com_horarios | qs_diarios_ead | qs_diarios_com_pratica_profissional

        if restringir_mesmo_curso:
            qs_diarios = qs_diarios.filter(turma__curso_campus_id=self.curso_campus_id)

        return qs_diarios.distinct().order_by('componente_curricular__componente')

    def get_diarios_disponiveis_matricular_por_diretoria(
        self, diretoria, outros_componentes=False, outras_matrizes=False, ignorar_futuros=True, componente=None, matriz=False
    ):
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()

        qs_diarios = Diario.objects.filter(
            ano_letivo=ultima_matricula_periodo.ano_letivo,
            periodo_letivo=ultima_matricula_periodo.periodo_letivo,
            turma__curso_campus__diretoria=diretoria,
        )

        # excluindo já matriculados
        qs_diarios = qs_diarios.exclude(
            id__in=MatriculaDiario.objects.filter(matricula_periodo=ultima_matricula_periodo).values_list('diario__pk', flat=True)
        )

        # excluindo os pagos
        qs_diarios = qs_diarios.exclude(componente_curricular__componente__in=self.get_componentes_cumpridos().values_list('id', flat=True))

        # excluindo os cursando no ultimo período
        qs_diarios = qs_diarios.exclude(componente_curricular__componente__in=self.get_componentes_cursando().values_list('id', flat=True))

        qs_diarios = qs_diarios.order_by('componente_curricular__componente__descricao')

        # filtrando apenas do componente especificado, se for o caso
        if componente:
            qs_diarios = qs_diarios.filter(componente_curricular__componente=componente)

        if matriz:
            qs_diarios = qs_diarios.filter(componente_curricular__matriz=matriz)

        if outros_componentes and outras_matrizes:
            qs_diarios = qs_diarios.exclude(componente_curricular__matriz=self.matriz)
        elif outros_componentes:
            componentes = ComponenteCurricular.objects.filter(matriz=self.matriz).values_list('componente_id', flat=True).distinct()
            qs_diarios = qs_diarios.filter(componente_curricular__componente__in=componentes).exclude(componente_curricular__matriz=self.matriz)
        elif outras_matrizes:
            componentes = ComponenteCurricular.objects.filter(matriz=self.matriz).values_list('componente_id', flat=True).distinct()
            qs_diarios = qs_diarios.exclude(componente_curricular__componente__in=componentes)
        else:
            qs_diarios = qs_diarios.filter(componente_curricular__matriz=self.matriz)

        if ignorar_futuros:
            qs_diarios = qs_diarios.filter(componente_curricular__periodo_letivo__lte=self.periodo_atual) | qs_diarios.filter(
                componente_curricular__periodo_letivo__isnull=True
            )
        return qs_diarios.distinct()

    def pode_gerenciar_mobilidade_academica(self, user=None):
        result = False
        if self.matriz and self.matriz.estrutura and self.matriz.estrutura.permite_registro_mobilidade_academica:
            result = not self.is_concluido() and perms.realizar_procedimentos_academicos(user, self.curso_campus)
        return result

    def pode_adicionar_registro_historico(self, user=None):
        tem_matriz_e_estrutura = self.matriz and self.matriz.estrutura
        pode_realizar_procedimentos_academicos = perms.realizar_procedimentos_academicos(user, self.curso_campus)
        permite_insclusao_registros_historico = Configuracao.get_valor_por_chave('edu', 'permite_insclusao_registros_historico')
        return tem_matriz_e_estrutura and permite_insclusao_registros_historico == 'True' and pode_realizar_procedimentos_academicos

    def pode_editar_registro_historico(self, user=None):
        tem_matriz_e_estrutura = self.matriz and self.matriz.estrutura
        pode_realizar_procedimentos_academicos = perms.realizar_procedimentos_academicos(user, self.curso_campus)
        permite_edicao_registros_historico = Configuracao.get_valor_por_chave('edu', 'permite_edicao_registros_historico')
        return tem_matriz_e_estrutura and permite_edicao_registros_historico == 'True' and pode_realizar_procedimentos_academicos

    def pode_excluir_registro_historico(self, user=None):
        return not self.is_concluido() and perms.realizar_procedimentos_academicos(user, self.curso_campus)

    def get_siglas_componentes_equivalentes_em_curso(self):
        # consultando as equivalências dos componetes extra-curriculates que estão sendo cursadas
        qs = (
            MatriculaDiario.objects.filter(matricula_periodo__aluno=self.id)
            .filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
            .exclude(diario__componente_curricular__matriz_id=F('matricula_periodo__aluno__matriz_id'))
        )
        l1 = list(
            qs.filter(
                diario__componente_curricular__componente__eq1__ativa=True,
                diario__componente_curricular__componente__eq1__simples=True,
                diario__componente_curricular__componente__eq1__aprovada=True,
                diario__componente_curricular__componente__eq1__equivalenciacomponentematriz__matriz_origem=F(
                    'diario__componente_curricular__matriz_id'
                ),
                diario__componente_curricular__componente__eq1__equivalenciacomponentematriz__matriz_destino=F('matricula_periodo__aluno__matriz_id'),
            ).values_list('diario__componente_curricular__componente__eq1__equivalentes__sigla', flat=True)
        )
        l2 = list(
            qs.filter(
                diario__componente_curricular__componente__eq2__ativa=True,
                diario__componente_curricular__componente__eq2__simples=True,
                diario__componente_curricular__componente__eq2__aprovada=True,
                diario__componente_curricular__componente__eq2__equivalenciacomponentematriz__matriz_destino=F(
                    'diario__componente_curricular__matriz_id'
                ),
                diario__componente_curricular__componente__eq2__equivalenciacomponentematriz__matriz_origem=F('matricula_periodo__aluno__matriz_id'),
            ).values_list('diario__componente_curricular__componente__eq2__componentes__sigla', flat=True)
        )
        return set(l1 + l2)

    def get_ids_componentes_nao_certificaveis(self):
        pk_nao_certificaveis = list(
            MatriculaDiario.objects.exclude(
                situacao__in=[
                    MatriculaDiario.SITUACAO_CURSANDO,
                    MatriculaDiario.SITUACAO_TRANSFERIDO,
                    MatriculaDiario.SITUACAO_TRANCADO,
                    MatriculaDiario.SITUACAO_CANCELADO,
                ]
            )
            .filter(matricula_periodo__aluno_id=self.id)
            .values_list('diario__componente_curricular__componente_id', flat=True)
        )
        pk_nao_certificaveis.extend(
            list(
                MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno_id=self.id).values_list(
                    'equivalencia_componente__componente_id', flat=True
                )
            )
        )
        pk_nao_certificaveis.extend(
            list(
                AproveitamentoEstudo.objects.filter(matricula_periodo__aluno_id=self.id).values_list(
                    'componente_curricular__componente_id', flat=True
                )
            )
        )
        pk_nao_certificaveis.extend(
            list(
                CertificacaoConhecimento.objects.filter(matricula_periodo__aluno_id=self.id).values_list(
                    'componente_curricular__componente_id', flat=True
                )
            )
        )
        pk_nao_certificaveis.extend(
            self.matriz.componentecurricular_set.filter(
                tipo__in=(ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL, ComponenteCurricular.TIPO_TRABALHO_CONCLUSAO_CURSO)
            ).values_list('componente_id', flat=True)
        )
        return pk_nao_certificaveis

    def get_historico(self, final=False, ordernar_por=1, exibir_optativas=False, eletronico=False):
        """Monta o histórico escolar completo do aluno.

        Agrupa componentes curriculares por categoria (obrigatórias, seminários,
        prática profissional, extensão, visitas técnicas, mobilidade acadêmica e
        extracurriculares), calcula frequências, médias e situação final de cada
        registro. Suporta exportação eletrônica com assinatura digital.

        Args:
            final: quando ``True``, considera apenas registros concluídos.
            ordernar_por: critério de ordenação dos componentes.
            exibir_optativas: se ``True``, inclui componentes optativos no resultado.
            eletronico: quando ``True``, gera dados para histórico eletrônico.

        Returns:
            dicionário estruturado com grupos de componentes, observações e
            metadados do aluno e da instituição.
        """

        frequencia_periodo = {}
        exibe_frequencia_global = self.matriz.estrutura.exibe_frequencia_global

        if self.iniciou_suap() or self.integralizou_suap():
            grupos_componentes = OrderedDict()
            grupos_componentes['Componentes Curriculares'] = []
            if self.matriz.ch_seminarios:
                grupos_componentes['Seminários'] = []
            if self.matriz.ch_pratica_profissional:
                grupos_componentes['Prática Profissional'] = []
            if self.matriz.ch_atividades_extensao:
                grupos_componentes['Atividade de Extensão'] = []
            if self.matriz.ch_pratica_como_componente:
                grupos_componentes['Prática como Componente Curricular'] = []
            if self.matriz.ch_visita_tecnica:
                grupos_componentes['Visita Técnica / Aula da Campo'] = []
            if self.matriz.estrutura.permite_registro_mobilidade_academica:
                grupos_componentes['Mobilidade Acadêmica'] = []
            grupos_componentes['Componentes Extracurriculares'] = []

            observacoes = []
            pk_nao_certificaveis = self.get_ids_componentes_nao_certificaveis()

            ids_componenentes_associados = list(
                self.matriz.componentecurricular_set.filter(componente_curricular_associado__isnull=False).values_list(
                    'componente_curricular_associado__componente', flat=True
                )
            )
            ids_componenentes_associados_pagos = list(
                MatriculaDiarioResumida.objects.filter(
                    matricula_periodo__aluno_id=self.id, equivalencia_componente__componente__in=ids_componenentes_associados
                )
                .exclude(situacao__in=(MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA))
                .values_list('equivalencia_componente__componente', flat=True)
            ) + list(
                MatriculaDiario.objects.filter(
                    matricula_periodo__aluno_id=self.id,
                    situacao=MatriculaDiario.SITUACAO_APROVADO,
                    diario__componente_curricular__componente__in=ids_componenentes_associados,
                ).values_list('diario__componente_curricular__componente', flat=True)
            )

            for pk in ids_componenentes_associados:
                pk_nao_certificaveis.append(pk)

            for pk in ids_componenentes_associados_pagos:
                if pk in ids_componenentes_associados:
                    ids_componenentes_associados.remove(pk)

            qs_componentes_curriculares = self.matriz.componentecurricular_set.select_related('componente').exclude(
                componente_id__in=ids_componenentes_associados
            )
            if ordernar_por == Aluno.ORDENAR_HISTORICO_POR_COMPONENTE:
                qs_componentes_curriculares = qs_componentes_curriculares.order_by('componente__sigla')
            elif ordernar_por == Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ:
                qs_componentes_curriculares = qs_componentes_curriculares.order_by('periodo_letivo')

            equivalentes = self.get_siglas_componentes_equivalentes_em_curso()

            for componente_curricular in qs_componentes_curriculares:
                componentes = componente_curricular.get_grupo_componente_historico(grupos_componentes)
                repetir = True
                componente_cursado = None

                if self.is_proitec() and not MatriculaDiario.objects.filter(matricula_periodo__aluno_id=self.id).exists():
                    aprovado = self.matriculaperiodo_set.filter(situacao__id=SituacaoMatriculaPeriodo.APROVADO).exists()
                    componente = {
                        'pk': componente_curricular.pk,
                        'matricula_diario': None,
                        'matricula_diario_resumida': None,
                        'ano_periodo_letivo': f'{self.ano_letivo}/{self.periodo_letivo}',
                        'periodo_matriz': 1,
                        'sigla_componente': componente_curricular.componente.sigla,
                        'descricao_componente': componente_curricular.componente.descricao_historico,
                        'codigo_turma': None,
                        'codigo_diario': None,
                        'carga_horaria': componente_curricular.componente.get_ch_hora_relogio() or '-',
                        'media_final_disciplina': '-',
                        'percentual_carga_horaria_frequentada': aprovado and 100 or 0,
                        'situacao_display': aprovado and 'Aprovado' or 'Rep. Falta',
                        'situacao_legend': '',
                        'certificavel': False,
                        'cursada': True,
                        'certificada': False,
                        'aproveitada': False,
                    }
                    repetir = False
                    componentes.append(componente)
                for matricula_diario in MatriculaDiario.objects.select_related('diario__componente_curricular__componente').filter(
                    matricula_periodo__aluno_id=self.id, diario__componente_curricular__componente=componente_curricular.componente
                ):
                    professores = []
                    for professor_diario in matricula_diario.diario.professordiario_set.exclude(tipo__descricao='Tutor'):
                        professores.append(
                            (
                                matricula_diario.get_sigla_componente(),
                                matricula_diario.get_descricao_componente(),
                                professor_diario.professor.vinculo.pessoa.nome,
                                professor_diario.professor.get_titulacao(),
                            )
                        )

                    if final and matricula_diario.is_componente_integralizado() or not final:
                        if exibe_frequencia_global:
                            if matricula_diario.matricula_periodo_id not in frequencia_periodo:
                                frequencia_periodo[matricula_diario.matricula_periodo_id] = (
                                    matricula_diario.matricula_periodo.get_percentual_frequencia_periodo()
                                )
                            frequencia = frequencia_periodo[matricula_diario.matricula_periodo_id]
                        else:
                            frequencia = matricula_diario.get_percentual_carga_horaria_frequentada()
                        componente = {
                            'pk': componente_curricular.pk,
                            'matricula_diario': matricula_diario,
                            'matricula_diario_resumida': None,
                            'ano_periodo_letivo': f'{matricula_diario.matricula_periodo.ano_letivo}/{matricula_diario.matricula_periodo.periodo_letivo}',
                            'periodo_matriz': componente_curricular.periodo_letivo,
                            'sigla_componente': matricula_diario.get_sigla_componente(),
                            'descricao_componente': matricula_diario.get_descricao_componente(),
                            'codigo_turma': matricula_diario.get_codigo_turma(),
                            'codigo_diario': matricula_diario.diario.pk,
                            'carga_horaria': matricula_diario.get_carga_horaria() or '-',
                            'media_final_disciplina': matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                            and '-'
                            or matricula_diario.get_media_final_disciplina_exibicao(),
                            'percentual_carga_horaria_frequentada': frequencia
                            if matricula_diario.situacao
                            not in [
                                MatriculaDiario.SITUACAO_CURSANDO,
                                MatriculaDiario.SITUACAO_PROVA_FINAL,
                                MatriculaDiario.SITUACAO_CANCELADO,
                                MatriculaDiario.SITUACAO_TRANCADO,
                                MatriculaDiario.SITUACAO_PENDENTE,
                                MatriculaDiario.SITUACAO_DISPENSADO,
                            ]
                            else None,
                            'situacao_display': matricula_diario.get_situacao_display(),
                            'situacao_legend': '',
                            'certificavel': matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                            and componente_curricular.componente.pk not in pk_nao_certificaveis,
                            'cursada': matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO,
                            'certificada': False,
                            'aproveitada': False,
                            'equivalente': False,
                            'professores': professores,
                            'pertence_ao_plano_retomada': matricula_diario.diario.turma.pertence_ao_plano_retomada,
                        }
                        componentes.append(componente)
                        if repetir:
                            repetir = not (
                                matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO
                                or matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                            )
                        if not componente_cursado and not repetir:
                            componente_cursado = componente
                for matricula_diario in MatriculaDiarioResumida.objects.select_related('equivalencia_componente__componente').filter(
                    matricula_periodo__aluno_id=self.id, equivalencia_componente__componente=componente_curricular.componente
                ):
                    professores = []
                    professores.append(
                        (
                            matricula_diario.get_sigla_componente(),
                            matricula_diario.get_descricao_componente(),
                            matricula_diario.nome_professor,
                            matricula_diario.titularidade_professor,
                        )
                    )

                    if final and matricula_diario.is_componente_integralizado() or not final:
                        if exibe_frequencia_global:
                            if matricula_diario.matricula_periodo_id not in frequencia_periodo:
                                frequencia_periodo[matricula_diario.matricula_periodo_id] = (
                                    matricula_diario.matricula_periodo.get_percentual_frequencia_periodo()
                                )
                            frequencia = frequencia_periodo[matricula_diario.matricula_periodo_id]
                        else:
                            frequencia = matricula_diario.get_percentual_carga_horaria_frequentada()
                        componente = {
                            'pk': componente_curricular.pk,
                            'matricula_diario': None,
                            'matricula_diario_resumida': matricula_diario,
                            'ano_periodo_letivo': f'{matricula_diario.matricula_periodo.ano_letivo}/{matricula_diario.matricula_periodo.periodo_letivo}',
                            'periodo_matriz': componente_curricular.periodo_letivo,
                            'sigla_componente': matricula_diario.get_sigla_componente(),
                            'descricao_componente': matricula_diario.get_descricao_componente(),
                            'codigo_turma': matricula_diario.get_codigo_turma(),
                            'codigo_diario': matricula_diario.get_codigo_diario(),
                            'carga_horaria': matricula_diario.get_carga_horaria() or '-',
                            'media_final_disciplina': matricula_diario.get_media_final_disciplina_exibicao(),
                            'percentual_carga_horaria_frequentada': frequencia,
                            'situacao_display': matricula_diario.get_situacao_display(),
                            'situacao_legend': '',
                            'certificavel': componente_curricular.componente.pk not in pk_nao_certificaveis,
                            'cursada': matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO,
                            'certificada': False,
                            'aproveitada': False,
                            'equivalente': False,
                            'professores': professores,
                        }
                        componentes.append(componente)
                        if repetir:
                            repetir = not (
                                matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO
                                or matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                                or matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO
                                or matricula_diario.situacao == MatriculaDiario.SITUACAO_DISPENSADO
                                or matricula_diario.situacao == MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO
                            )
                        if not componente_cursado and not repetir:
                            componente_cursado = componente
                for certificacao in CertificacaoConhecimento.objects.select_related('componente_curricular__componente').filter(
                    matricula_periodo__aluno_id=self.id, componente_curricular__componente=componente_curricular.componente
                ):
                    if exibe_frequencia_global:
                        if certificacao.matricula_periodo_id not in frequencia_periodo:
                            frequencia_periodo[certificacao.matricula_periodo_id] = certificacao.matricula_periodo.get_percentual_frequencia_periodo()
                        frequencia = frequencia_periodo[certificacao.matricula_periodo_id]
                    else:
                        frequencia = not certificacao.ausente and 100 or None
                    professores = []
                    for professor in certificacao.professores.all():
                        professores.append(
                            (
                                certificacao.componente_curricular.componente.sigla,
                                certificacao.componente_curricular.componente.descricao_historico,
                                professor.vinculo.pessoa.nome,
                                professor.get_titulacao(),
                            )
                        )
                    for servidor in certificacao.servidores.all():
                        professores.append(
                            (
                                certificacao.componente_curricular.componente.sigla,
                                certificacao.componente_curricular.componente.descricao_historico,
                                servidor.pessoa_fisica.nome,
                                servidor.get_titulacao(),
                            )
                        )
                    cursada = certificacao.is_aluno_aprovado()
                    componente = {
                        'pk': componente_curricular.pk,
                        'matricula_diario': None,
                        'matricula_diario_resumida': None,
                        'ano_periodo_letivo': f'{certificacao.matricula_periodo.ano_letivo}/{certificacao.matricula_periodo.periodo_letivo}',
                        'periodo_matriz': certificacao.componente_curricular.periodo_letivo,
                        'sigla_componente': certificacao.componente_curricular.componente.sigla,
                        'descricao_componente': certificacao.componente_curricular.componente.descricao_historico,
                        'codigo_turma': None,
                        'codigo_diario': None,
                        'carga_horaria': certificacao.componente_curricular.componente.get_ch_hora_relogio() or '-',
                        'media_final_disciplina': certificacao.get_media_final_disciplina_exibicao(),
                        'percentual_carga_horaria_frequentada': frequencia,
                        'situacao_display': certificacao.get_situacao_certificacao(),
                        'situacao_legend': '',
                        'certificavel': False,
                        'cursada': cursada,
                        'certificada': certificacao.pk,
                        'aproveitada': False,
                        'equivalente': False,
                        'professores': professores,
                    }
                    if not final or cursada:
                        componentes.append(componente)
                    if repetir:
                        repetir = not cursada
                    if not componente_cursado and not repetir:
                        componente_cursado = componente
                for aproveitamento in AproveitamentoEstudo.objects.select_related('componente_curricular__componente').filter(
                    matricula_periodo__aluno_id=self.id, componente_curricular__componente=componente_curricular.componente
                ):
                    if exibe_frequencia_global:
                        if aproveitamento.matricula_periodo_id not in frequencia_periodo:
                            frequencia_periodo[aproveitamento.matricula_periodo_id] = (
                                aproveitamento.matricula_periodo.get_percentual_frequencia_periodo()
                            )
                        frequencia = frequencia_periodo[aproveitamento.matricula_periodo_id]
                    else:
                        frequencia = aproveitamento.frequencia
                    professores = []
                    for professor in aproveitamento.professores.all():
                        professores.append(
                            (
                                aproveitamento.componente_curricular.componente.sigla,
                                aproveitamento.componente_curricular.componente.descricao_historico,
                                professor.vinculo.pessoa.nome,
                                professor.get_titulacao(),
                            )
                        )
                    for servidor in aproveitamento.servidores.all():
                        professores.append(
                            (
                                aproveitamento.componente_curricular.componente.sigla,
                                aproveitamento.componente_curricular.componente.descricao_historico,
                                servidor.pessoa_fisica.nome,
                                servidor.get_titulacao(),
                            )
                        )
                    componente = {
                        'pk': componente_curricular.pk,
                        'matricula_diario': None,
                        'matricula_diario_resumida': None,
                        'ano_periodo_letivo': f'{aproveitamento.matricula_periodo.ano_letivo}/{aproveitamento.matricula_periodo.periodo_letivo}',
                        'periodo_matriz': aproveitamento.componente_curricular.periodo_letivo,
                        'sigla_componente': aproveitamento.componente_curricular.componente.sigla,
                        'descricao_componente': aproveitamento.componente_curricular.componente.descricao_historico,
                        'codigo_turma': None,
                        'codigo_diario': None,
                        'carga_horaria': aproveitamento.componente_curricular.componente.get_ch_hora_relogio() or '-',
                        'media_final_disciplina': aproveitamento.get_media_final_disciplina_exibicao(),
                        'percentual_carga_horaria_frequentada': frequencia,
                        'situacao_display': 'Aproveit. Disciplina',
                        'situacao_legend': aproveitamento.escola_origem,
                        'certificavel': False,
                        'cursada': True,
                        'certificada': False,
                        'aproveitada': aproveitamento.pk,
                        'equivalente': False,
                        'professores': professores,
                    }
                    componentes.append(componente)
                    if repetir:
                        repetir = False
                    if not componente_cursado and not repetir:
                        componente_cursado = componente
                for aproveitamento in AproveitamentoComponente.objects.select_related('componente_curricular__componente').filter(
                    matricula_periodo__aluno_id=self.id, componente_curricular__componente=componente_curricular.componente
                ):
                    componente = {
                        'pk': componente_curricular.pk,
                        'matricula_diario': None,
                        'matricula_diario_resumida': None,
                        'ano_periodo_letivo': f'{aproveitamento.matricula_periodo.ano_letivo}/{aproveitamento.matricula_periodo.periodo_letivo}',
                        'periodo_matriz': aproveitamento.componente_curricular.periodo_letivo,
                        'sigla_componente': aproveitamento.componente_curricular.componente.sigla,
                        'descricao_componente': aproveitamento.componente_curricular.componente.descricao_historico,
                        'codigo_turma': None,
                        'codigo_diario': None,
                        'carga_horaria': aproveitamento.componente_curricular.componente.get_ch_hora_relogio() or '-',
                        'media_final_disciplina': None,
                        'percentual_carga_horaria_frequentada': None,
                        'situacao_display': 'Cumprida',
                        'situacao_legend': '',
                        'certificavel': False,
                        'cursada': True,
                        'certificada': False,
                        'aproveitada': False,
                        'equivalente': aproveitamento.pk,
                    }
                    componentes.append(componente)
                    if repetir:
                        repetir = False
                    if not componente_cursado and not repetir:
                        componente_cursado = componente
                    observacoes.append(aproveitamento.get_observacao_historico())
                for registro_historico in RegistroHistorico.objects.select_related('componente').filter(
                    matricula_periodo__aluno_id=self.id, componente=componente_curricular.componente
                ):
                    if final and registro_historico.is_componente_integralizado() or not final:
                        if exibe_frequencia_global:
                            if registro_historico.matricula_periodo_id not in frequencia_periodo:
                                frequencia_periodo[registro_historico.matricula_periodo_id] = (
                                    registro_historico.matricula_periodo.get_percentual_frequencia_periodo()
                                )
                            frequencia = frequencia_periodo[registro_historico.matricula_periodo_id]
                        else:
                            frequencia = registro_historico.frequencia
                        cursada = registro_historico.is_componente_integralizado()
                        professores = []
                        for professor, titulacao in registro_historico.get_professores_com_titulacao():
                            professores.append(
                                (
                                    registro_historico.componente.sigla,
                                    registro_historico.componente.descricao_historico,
                                    professor,
                                    titulacao,
                                )
                            )
                        componente = {
                            'pk': componente_curricular.pk,
                            'matricula_diario': None,
                            'matricula_diario_resumida': None,
                            'ano_periodo_letivo': f'{registro_historico.matricula_periodo.ano_letivo}/{registro_historico.matricula_periodo.periodo_letivo}',
                            'periodo_matriz': componente_curricular.periodo_letivo,
                            'sigla_componente': registro_historico.componente.sigla,
                            'descricao_componente': registro_historico.componente.descricao_historico,
                            'codigo_turma': registro_historico.codigo_turma,
                            'codigo_diario': registro_historico.codigo_diario,
                            'carga_horaria': registro_historico.componente.get_ch_hora_relogio() or '-',
                            'media_final_disciplina': registro_historico.get_media_final_disciplina_exibicao(
                                componente_curricular_por_conceito=componente_curricular.avaliacao_por_conceito
                            ),
                            'percentual_carga_horaria_frequentada': frequencia,
                            'situacao_display': registro_historico.get_situacao_display(),
                            'situacao_legend': '',
                            'certificavel': False,
                            'cursada': cursada,
                            'certificada': False,
                            'aproveitada': False,
                            'equivalente': False,
                            'registro_historico': registro_historico,
                            'gerenciavel': componente_curricular.tipo == ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL
                            or Configuracao.get_valor_por_chave('edu', 'permite_edicao_registros_historico') == 'True',
                            'professores': professores,
                        }
                        componentes.append(componente)
                        if repetir:
                            repetir = not cursada
                        if not componente_cursado and not repetir:
                            componente_cursado = componente
                if repetir:
                    if (exibir_optativas or not componente_curricular.optativo) and not self.is_fic():
                        componente = {
                            'pk': componente_curricular.pk,
                            'matricula_diario': None,
                            'matricula_diario_resumida': None,
                            'ano_periodo_letivo': None,
                            'periodo_matriz': componente_curricular.periodo_letivo,
                            'sigla_componente': componente_curricular.componente.sigla,
                            'descricao_componente': componente_curricular.componente.descricao_historico,
                            'codigo_turma': None,
                            'codigo_diario': None,
                            'carga_horaria': componente_curricular.componente.get_ch_hora_relogio() or '-',
                            'media_final_disciplina': None,
                            'percentual_carga_horaria_frequentada': None,
                            'situacao_display': None if componente_curricular.componente.sigla not in equivalentes else 'Cursando Equivalente',
                            'situacao_legend': '',
                            'certificavel': componente_curricular.componente.pk not in pk_nao_certificaveis,
                            'cursada': False,
                            'certificada': False,
                            'aproveitada': False,
                            'equivalente': False,
                        }
                        if componente_curricular.componente_id not in ids_componenentes_associados_pagos:
                            componentes.append(componente)
                        if (
                            componente_curricular.componente_curricular_associado
                            and componente_curricular.componente_curricular_associado.componente.id not in ids_componenentes_associados_pagos
                        ):
                            componentes = componente_curricular.componente_curricular_associado.get_grupo_componente_historico(grupos_componentes)
                            componente_associado = {
                                'pk': componente_curricular.pk,
                                'matricula_diario': None,
                                'matricula_diario_resumida': None,
                                'ano_periodo_letivo': None,
                                'periodo_matriz': componente_curricular.componente_curricular_associado.periodo_letivo,
                                'sigla_componente': componente_curricular.componente_curricular_associado.componente.sigla,
                                'descricao_componente': componente_curricular.componente_curricular_associado.componente.descricao_historico,
                                'codigo_turma': None,
                                'codigo_diario': None,
                                'carga_horaria': componente_curricular.componente_curricular_associado.componente.get_ch_hora_relogio() or '-',
                                'media_final_disciplina': None,
                                'percentual_carga_horaria_frequentada': None,
                                'situacao_display': None,
                                'situacao_legend': '',
                                'certificavel': componente_curricular.componente_curricular_associado.componente.pk not in pk_nao_certificaveis,
                                'cursada': False,
                                'certificada': False,
                                'aproveitada': False,
                                'equivalente': False,
                            }
                            componentes.append(componente_associado)
                else:
                    if (
                        componente_curricular.componente_curricular_associado
                        and componente_curricular.componente_curricular_associado.componente.id not in ids_componenentes_associados_pagos
                    ):
                        componentes = componente_curricular.componente_curricular_associado.get_grupo_componente_historico(grupos_componentes)
                        if componente_cursado:
                            componente_associado = {
                                'pk': componente_curricular.componente_curricular_associado.pk,
                                'matricula_diario': None,
                                'matricula_diario_resumida': None,
                                'ano_periodo_letivo': componente_cursado['ano_periodo_letivo'],
                                'periodo_matriz': componente_curricular.componente_curricular_associado.periodo_letivo,
                                'sigla_componente': componente_curricular.componente_curricular_associado.componente.sigla,
                                'descricao_componente': componente_curricular.componente_curricular_associado.componente.descricao_historico,
                                'codigo_turma': componente_cursado['codigo_turma'],
                                'codigo_diario': componente_cursado['codigo_diario'],
                                'carga_horaria': componente_curricular.componente_curricular_associado.componente.get_ch_hora_relogio() or '-',
                                'media_final_disciplina': componente_cursado['media_final_disciplina'],
                                'percentual_carga_horaria_frequentada': None,
                                'situacao_display': componente_cursado['situacao_display'],
                                'situacao_legend': '',
                                'certificavel': False,
                                'cursada': False,
                                'certificada': False,
                                'aproveitada': False,
                                'equivalente': False,
                            }
                        else:
                            componente_associado = {
                                'pk': componente_curricular.componente_curricular_associado.pk,
                                'matricula_diario': None,
                                'matricula_diario_resumida': None,
                                'ano_periodo_letivo': None,
                                'periodo_matriz': componente_curricular.componente_curricular_associado.periodo_letivo,
                                'sigla_componente': componente_curricular.componente_curricular_associado.componente.sigla,
                                'descricao_componente': componente_curricular.componente_curricular_associado.componente.descricao_historico,
                                'codigo_turma': None,
                                'codigo_diario': None,
                                'carga_horaria': componente_curricular.componente_curricular_associado.componente.get_ch_hora_relogio() or '-',
                                'media_final_disciplina': None,
                                'percentual_carga_horaria_frequentada': None,
                                'situacao_display': None,
                                'situacao_legend': '',
                                'certificavel': componente_curricular.componente_curricular_associado.componente.pk not in pk_nao_certificaveis,
                                'cursada': False,
                                'certificada': False,
                                'aproveitada': False,
                                'equivalente': False,
                            }
                        componentes.append(componente_associado)

            # ADICIONANDO OS COMPONENTES EXTRACURRICULARES VINDAS DO SUAP
            ids_componentes_matriz = qs_componentes_curriculares.values_list('componente_id', flat=True)
            for matricula_diario in (
                MatriculaDiario.objects.select_related('diario__componente_curricular__componente')
                .filter(matricula_periodo__aluno_id=self.id)
                .exclude(diario__componente_curricular__componente_id__in=ids_componentes_matriz)
            ):
                componentes = grupos_componentes['Componentes Extracurriculares']
                if exibe_frequencia_global:
                    if matricula_diario.matricula_periodo_id not in frequencia_periodo:
                        frequencia_periodo[matricula_diario.matricula_periodo_id] = (
                            matricula_diario.matricula_periodo.get_percentual_frequencia_periodo()
                        )
                    frequencia = frequencia_periodo[matricula_diario.matricula_periodo_id]
                else:
                    frequencia = matricula_diario.get_percentual_carga_horaria_frequentada()
                componente = {
                    'pk': None,
                    'matricula_diario': matricula_diario,
                    'ano_periodo_letivo': f'{matricula_diario.matricula_periodo.ano_letivo}/{matricula_diario.matricula_periodo.periodo_letivo}',
                    'periodo_matriz': matricula_diario.diario.componente_curricular.periodo_letivo,
                    'sigla_componente': matricula_diario.get_sigla_componente(),
                    'descricao_componente': matricula_diario.get_descricao_componente(),
                    'codigo_turma': matricula_diario.get_codigo_turma(),
                    'codigo_diario': matricula_diario.diario.pk,
                    'carga_horaria': matricula_diario.get_carga_horaria() or '-',
                    'media_final_disciplina': matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                    and '-'
                    or matricula_diario.get_media_final_disciplina_exibicao(),
                    'percentual_carga_horaria_frequentada': frequencia
                    if matricula_diario.situacao
                    not in [
                        MatriculaDiario.SITUACAO_CURSANDO,
                        MatriculaDiario.SITUACAO_PROVA_FINAL,
                        MatriculaDiario.SITUACAO_CANCELADO,
                        MatriculaDiario.SITUACAO_TRANCADO,
                        MatriculaDiario.SITUACAO_PENDENTE,
                        MatriculaDiario.SITUACAO_DISPENSADO,
                    ]
                    else None,
                    'situacao_display': matricula_diario.get_situacao_display(),
                    'situacao_legend': '',
                    'certificavel': matricula_diario.situacao == MatriculaDiario.SITUACAO_CURSANDO
                    and componente_curricular.componente.pk not in pk_nao_certificaveis,
                    'cursada': matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO,
                    'certificada': False,
                    'aproveitada': False,
                    'equivalente': False,
                }
                if final and matricula_diario.is_componente_integralizado() or not final:
                    componentes.append(componente)

            # ADICIONANDO OS COMPONENTES EXTRACURRICULARES APROVEITADOS
            for aproveitamento in (
                AproveitamentoEstudo.objects.select_related('componente_curricular__componente')
                .filter(matricula_periodo__aluno_id=self.id)
                .exclude(componente_curricular__componente_id__in=ids_componentes_matriz)
            ):
                componentes = grupos_componentes['Componentes Extracurriculares']
                if exibe_frequencia_global:
                    if aproveitamento.matricula_periodo_id not in frequencia_periodo:
                        frequencia_periodo[aproveitamento.matricula_periodo_id] = aproveitamento.matricula_periodo.get_percentual_frequencia_periodo()
                    frequencia = frequencia_periodo[aproveitamento.matricula_periodo_id]
                else:
                    frequencia = aproveitamento.frequencia
                professores = []
                for professor in aproveitamento.professores.all():
                    professores.append(
                        (
                            aproveitamento.componente_curricular.componente.sigla,
                            aproveitamento.componente_curricular.componente.descricao_historico,
                            professor.vinculo.pessoa.nome,
                            professor.get_titulacao(),
                        )
                    )
                for servidor in aproveitamento.servidores.all():
                    professores.append(
                        (
                            aproveitamento.componente_curricular.componente.sigla,
                            aproveitamento.componente_curricular.componente.descricao_historico,
                            servidor.pessoa_fisica.nome,
                            servidor.get_titulacao(),
                        )
                    )
                componente = {
                    'pk': aproveitamento.componente_curricular_id,
                    'matricula_diario': None,
                    'matricula_diario_resumida': None,
                    'ano_periodo_letivo': f'{aproveitamento.matricula_periodo.ano_letivo}/{aproveitamento.matricula_periodo.periodo_letivo}',
                    'periodo_matriz': aproveitamento.componente_curricular.periodo_letivo,
                    'sigla_componente': aproveitamento.componente_curricular.componente.sigla,
                    'descricao_componente': aproveitamento.componente_curricular.componente.descricao_historico,
                    'codigo_turma': None,
                    'codigo_diario': None,
                    'carga_horaria': aproveitamento.componente_curricular.componente.get_ch_hora_relogio() or '-',
                    'media_final_disciplina': aproveitamento.get_media_final_disciplina_exibicao(),
                    'percentual_carga_horaria_frequentada': frequencia,
                    'situacao_display': 'Aproveit. Disciplina',
                    'situacao_legend': aproveitamento.escola_origem,
                    'certificavel': False,
                    'cursada': True,
                    'certificada': False,
                    'aproveitada': aproveitamento.pk,
                    'equivalente': False,
                    'professores': professores,
                }
                componentes.append(componente)

            # ADICIONANDO OS COMPONENTES EXTRACURRICULARES CERTIFICADOS
            for certificacao in (
                CertificacaoConhecimento.objects.select_related('componente_curricular__componente')
                .filter(matricula_periodo__aluno_id=self.id)
                .exclude(componente_curricular__componente_id__in=ids_componentes_matriz)
            ):
                componentes = grupos_componentes['Componentes Extracurriculares']
                if exibe_frequencia_global:
                    if certificacao.matricula_periodo_id not in frequencia_periodo:
                        frequencia_periodo[certificacao.matricula_periodo_id] = certificacao.matricula_periodo.get_percentual_frequencia_periodo()
                    frequencia = frequencia_periodo[certificacao.matricula_periodo_id]
                else:
                    frequencia = not certificacao.ausente and 100 or None
                professores = []
                for professor in certificacao.professores.all():
                    professores.append(
                        (
                            certificacao.componente_curricular.componente.sigla,
                            certificacao.componente_curricular.componente.descricao_historico,
                            professor.vinculo.pessoa.nome,
                            professor.get_titulacao(),
                        )
                    )
                for servidor in certificacao.servidores.all():
                    professores.append(
                        (
                            certificacao.componente_curricular.componente.sigla,
                            certificacao.componente_curricular.componente.descricao_historico,
                            servidor.pessoa_fisica.nome,
                            servidor.get_titulacao(),
                        )
                    )
                cursada = certificacao.is_aluno_aprovado()
                componente = {
                    'pk': certificacao.componente_curricular_id,
                    'matricula_diario': None,
                    'matricula_diario_resumida': None,
                    'ano_periodo_letivo': f'{certificacao.matricula_periodo.ano_letivo}/{certificacao.matricula_periodo.periodo_letivo}',
                    'periodo_matriz': certificacao.componente_curricular.periodo_letivo,
                    'sigla_componente': certificacao.componente_curricular.componente.sigla,
                    'descricao_componente': certificacao.componente_curricular.componente.descricao_historico,
                    'codigo_turma': None,
                    'codigo_diario': None,
                    'carga_horaria': certificacao.componente_curricular.componente.get_ch_hora_relogio() or '-',
                    'media_final_disciplina': certificacao.get_media_final_disciplina_exibicao(),
                    'percentual_carga_horaria_frequentada': frequencia,
                    'situacao_display': certificacao.get_situacao_certificacao(),
                    'situacao_legend': '',
                    'certificavel': False,
                    'cursada': cursada,
                    'certificada': certificacao.pk,
                    'aproveitada': False,
                    'equivalente': False,
                    'professores': professores,
                }
                if not final or cursada:
                    componentes.append(componente)

            # ADICIONANDO OS COMPONENTES EXTRACURRICULARES VINDAS DO Q-ACADÊMICO
            for matricula_diario in (
                MatriculaDiarioResumida.objects.exclude(
                    situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA]
                )
                .select_related('equivalencia_componente')
                .filter(matricula_periodo__aluno_id=self.id)
                .exclude(equivalencia_componente__componente_id__in=ids_componentes_matriz)
            ):
                componentes = grupos_componentes['Componentes Extracurriculares']
                if exibe_frequencia_global:
                    if matricula_diario.matricula_periodo_id not in frequencia_periodo:
                        frequencia_periodo[matricula_diario.matricula_periodo_id] = (
                            matricula_diario.matricula_periodo.get_percentual_frequencia_periodo()
                        )
                    frequencia = frequencia_periodo[matricula_diario.matricula_periodo_id]
                else:
                    frequencia = matricula_diario.get_percentual_carga_horaria_frequentada()
                componente = {
                    'pk': None,
                    'matricula_diario': None,
                    'matricula_diario_resumida': matricula_diario,
                    'ano_periodo_letivo': f'{matricula_diario.matricula_periodo.ano_letivo}/{matricula_diario.matricula_periodo.periodo_letivo}',
                    'periodo_matriz': None,
                    'sigla_componente': matricula_diario.equivalencia_componente.sigla,
                    'descricao_componente': matricula_diario.equivalencia_componente.descricao,
                    'codigo_turma': matricula_diario.get_codigo_turma(),
                    'codigo_diario': matricula_diario.get_codigo_diario(),
                    'carga_horaria': matricula_diario.equivalencia_componente.carga_horaria or '-',
                    'media_final_disciplina': matricula_diario.get_media_final_disciplina_exibicao(),
                    'percentual_carga_horaria_frequentada': frequencia,
                    'situacao_display': matricula_diario.get_situacao_display(),
                    'situacao_legend': '',
                    'certificavel': False,
                    'cursada': matricula_diario.situacao == MatriculaDiario.SITUACAO_APROVADO,
                    'certificada': False,
                    'aproveitada': False,
                    'equivalente': False,
                }
                componentes.append(componente)

            # ADICIONANDO OS COMPONENTES DE MOBILIDADE ACADÊMICA
            if self.matriz.estrutura.permite_registro_mobilidade_academica:
                for registro_historico in (
                    RegistroHistorico.objects.select_related('componente')
                    .filter(matricula_periodo__aluno_id=self.id, mobilidade_academica=True)
                    .exclude(componente_id__in=ids_componentes_matriz)
                ):
                    componentes = grupos_componentes['Mobilidade Acadêmica']
                    if exibe_frequencia_global:
                        if registro_historico.matricula_periodo_id not in frequencia_periodo:
                            frequencia_periodo[registro_historico.matricula_periodo_id] = (
                                registro_historico.matricula_periodo.get_percentual_frequencia_periodo()
                            )
                        frequencia = frequencia_periodo[registro_historico.matricula_periodo_id]
                    else:
                        frequencia = registro_historico.frequencia
                    professores = []
                    for professor, titulacao in registro_historico.get_professores_com_titulacao():
                        professores.append(
                            (
                                registro_historico.componente.sigla,
                                registro_historico.componente.descricao_historico,
                                professor,
                                titulacao,
                            )
                        )
                    componente = {
                        'pk': componente_curricular.pk,
                        'matricula_diario': None,
                        'matricula_diario_resumida': None,
                        'ano_periodo_letivo': f'{registro_historico.matricula_periodo.ano_letivo}/{registro_historico.matricula_periodo.periodo_letivo}',
                        'periodo_matriz': componente_curricular.periodo_letivo,
                        'sigla_componente': registro_historico.componente.sigla,
                        'descricao_componente': registro_historico.componente.descricao_historico,
                        'codigo_turma': registro_historico.codigo_turma,
                        'codigo_diario': registro_historico.codigo_diario,
                        'carga_horaria': registro_historico.componente.get_ch_hora_relogio() or '-',
                        'media_final_disciplina': registro_historico.get_media_final_disciplina_exibicao(
                            componente_curricular_por_conceito=componente_curricular.avaliacao_por_conceito
                        ),
                        'percentual_carga_horaria_frequentada': frequencia,
                        'situacao_display': registro_historico.get_situacao_display(),
                        'situacao_legend': '',
                        'certificavel': False,
                        'cursada': False,
                        'certificada': False,
                        'aproveitada': False,
                        'equivalente': False,
                        'registro_historico': registro_historico,
                        'gerenciavel': True,
                        'professores': professores,
                    }
                    if final and registro_historico.is_componente_integralizado() or not final:
                        componentes.append(componente)

            # ADICIONANDO OS COMPONENTES EXTRACURRICULARES VINDAS DO REGISTRO HISTORICO (TRANSFERENCIA DE CURSO)
            for registro_historico in (
                RegistroHistorico.objects.select_related('componente')
                .filter(matricula_periodo__aluno_id=self.id, mobilidade_academica=False)
                .exclude(componente_id__in=ids_componentes_matriz)
            ):
                componentes = grupos_componentes['Componentes Extracurriculares']
                if exibe_frequencia_global:
                    if registro_historico.matricula_periodo_id not in frequencia_periodo:
                        frequencia_periodo[registro_historico.matricula_periodo_id] = (
                            registro_historico.matricula_periodo.get_percentual_frequencia_periodo()
                        )
                    frequencia = frequencia_periodo[registro_historico.matricula_periodo_id]
                else:
                    frequencia = registro_historico.frequencia
                professores = []
                for professor, titulacao in registro_historico.get_professores_com_titulacao():
                    professores.append(
                        (
                            registro_historico.componente.sigla,
                            registro_historico.componente.descricao_historico,
                            professor,
                            titulacao,
                        )
                    )
                componente = {
                    'pk': None,
                    'matricula_diario': None,
                    'matricula_diario_resumida': None,
                    'ano_periodo_letivo': f'{registro_historico.matricula_periodo.ano_letivo}/{registro_historico.matricula_periodo.periodo_letivo}',
                    'periodo_matriz': None,
                    'sigla_componente': registro_historico.componente.sigla,
                    'descricao_componente': registro_historico.componente.descricao_historico,
                    'codigo_turma': registro_historico.codigo_turma,
                    'codigo_diario': registro_historico.codigo_diario,
                    'carga_horaria': registro_historico.componente.get_ch_hora_relogio() or '-',
                    'media_final_disciplina': registro_historico.get_media_final_disciplina_exibicao(
                        componente_curricular_por_conceito=componente_curricular.avaliacao_por_conceito
                    ),
                    'percentual_carga_horaria_frequentada': frequencia,
                    'situacao_display': registro_historico.get_situacao_display(),
                    'situacao_legend': '',
                    'certificavel': False,
                    'cursada': False,
                    'certificada': False,
                    'aproveitada': False,
                    'equivalente': False,
                    'registro_historico': registro_historico,
                    'gerenciavel': Configuracao.get_valor_por_chave('edu', 'permite_edicao_registros_historico') == 'True',
                    'professores': professores,
                }
                if final and registro_historico.is_componente_integralizado() or not final:
                    componentes.append(componente)

            for grupo in list(grupos_componentes.values()):
                for componente in grupo:
                    componente['sigla_componente'] = insert_space(componente['sigla_componente'], 9)

            if ordernar_por == Aluno.ORDENAR_HISTORICO_POR_PERIODO_LETIVO:
                for grupo in list(grupos_componentes.keys()):
                    grupos_componentes[grupo] = sorted(grupos_componentes[grupo], key=lambda s: s['ano_periodo_letivo'] or '0')

            if ordernar_por == Aluno.ORDENAR_HISTORICO_POR_PERIODO_MATRIZ:
                for grupo in list(grupos_componentes.keys()):
                    grupos_componentes[grupo] = sorted(
                        grupos_componentes[grupo],
                        key=lambda s: (s['periodo_matriz'] or 0, s['sigla_componente'] or '', s['ano_periodo_letivo'] or '0'),
                    )

            uo = self.curso_campus.diretoria.setor.uo
            filiacao = []
            if self.nome_pai:
                filiacao.append(self.nome_pai)
            if self.nome_mae:
                filiacao.append(self.nome_mae)
            filiacao = normalizar_nome_proprio(format_iterable(filiacao))

            if self.observacao_historico:
                observacoes.append(self.observacao_historico)

            historico = {}
            # EXTRA
            historico.update(assinatura_eletronica=eletronico)
            historico.update(is_integralizado_cursando=self.is_integralizado_cursando())
            historico.update(creditos_especiais=self.get_creditos_especiais())
            historico.update(estagios=self.get_estagios_historico().select_related('empresa__pessoa'))
            # CABEÇALHO
            historico.update(
                nome_campus=uo.nome,
                telefone_campus=uo.telefone,
                endereco_campus=uo.endereco,
                municipio_campus=uo.municipio and uo.municipio.nome or '',
                hoje=datetime.date.today(),
                uf_campus=uo.municipio and uo.municipio.uf or None,
                cep_campus=uo.cep,
                cnpj_campus=uo.cnpj,
                codigo_inep=uo.codigo_inep,
                codigo_emec=uo.codigo_emec,
                novo_modelo=datetime.date.today() >= datetime.date(2019, 4, 25),
                credenciamento=Configuracao.get_valor_por_chave('edu', 'credenciamento'),
                recredenciamento=Configuracao.get_valor_por_chave('edu', 'recredenciamento'),
            )
            # DADOS PESSOAIS
            historico.update(
                sexo=self.pessoa_fisica.sexo,
                nome=self.get_nome_social_composto(),
                cpf=self.pessoa_fisica.cpf,
                data_nascimento=self.pessoa_fisica.nascimento_data,
                nacionalidade=self.nacionalidade and self.get_nacionalidade_display() or None,
                naturalidade=self.naturalidade,
            )
            historico.update(professores=[])
            # RG
            historico.update(
                numero_rg=self.numero_rg,
                orgao_emissao_rg=self.orgao_emissao_rg,
                uf_emissao_rg=self.uf_emissao_rg,
                data_emissao_rg=self.data_emissao_rg,
            )
            # FILIAÇÃO
            historico.update(nome_pai=self.nome_pai, nome_mae=self.nome_mae)
            # ENDEREÇO
            historico.update(
                logradouro=self.logradouro, numero=self.numero, complemento=self.complemento, bairro=self.bairro, cidade=self.cidade, cep=self.cep
            )
            # TÍTULO DE ELEITOR
            historico.update(
                numero_titulo_eleitor=self.numero_titulo_eleitor,
                zona_titulo_eleitor=self.zona_titulo_eleitor,
                secao_titulo_eleitor=self.secao,
                uf_emissao_titulo_eleitor=self.uf_emissao_titulo_eleitor,
                data_emissao_titulo_eleitor=self.data_emissao_titulo_eleitor,
            )
            # CARTEIRA RESERVISTA
            historico.update(
                numero_carteira_reservista=self.numero_carteira_reservista,
                regiao_carteira_reservista=self.regiao_carteira_reservista,
                serie_carteira_reservista=self.serie_carteira_reservista,
                uf_emissao_carteira_reservista=self.estado_emissao_carteira_reservista,
                ano_carteira_reservista=self.ano_carteira_reservista,
            )
            # DADOS ACADEMICOS
            historico.update(
                ira=self.get_ira(),
                matricula=self.matricula,
                situacao=self.situacao,
                forma_ingresso=self.forma_ingresso,
                data_matricula=self.data_matricula,
                ano_periodo_ingresso=f'{self.ano_letivo}/{self.periodo_letivo}',
                mes_ano_processo_seletivo=self.get_mes_ano_processo_seletivo(),
                descricao_linha_pesquisa=self.linha_pesquisa and self.linha_pesquisa.descricao,
            )
            # DADOS DO CURSO
            historico.update(
                codigo_emec_curso=self.curso_campus.codigo_emec,
                descricao_curso=self.curso_campus.descricao_historico,
                regime=self.matriz.estrutura.get_tipo_avaliacao_display,
                periodicidade=self.curso_campus.get_periodicidade_display,
                descricao_matriz=self.matriz.descricao,
                reconhecimento_texto=self.curso_campus.get_reconhecimento(),
                resolucao_criacao=self.curso_campus.get_autorizacao(),
            )

            # TCC
            projeto_final = self.get_projeto_final()
            historico.update(
                exige_tcc=self.matriz.exige_tcc,
                apresentou_tcc=projeto_final is not None,
                tipo_projeto=projeto_final and projeto_final.tipo,
                titulo_projeto=projeto_final and projeto_final.titulo,
                data_defesa=projeto_final and projeto_final.resultado_data,
                situacao_projeto=projeto_final and projeto_final.get_situacao_display(),
                nota_projeto=projeto_final and projeto_final.get_nota(),
                is_lancamento_conceito=self.matriz.estrutura.is_lancamento_conceito(),
            )
            # ENADE
            convocacoes = []
            for registro_convocacao_enade in self.get_convocacoes_enade():
                registro = {}
                registro.update(
                    data_prova_enade=registro_convocacao_enade.get_data_prova() or '-',
                    ano_letivo_enade=registro_convocacao_enade.convocacao_enade and registro_convocacao_enade.convocacao_enade.ano_letivo.ano or '-',
                    situacao_enade=registro_convocacao_enade.get_situacao_display,
                    justificativa_enade=registro_convocacao_enade.justificativa_dispensa,
                    tipo_convocacao=registro_convocacao_enade.get_tipo_convocacao_display(),
                )
                convocacoes.append(registro)
            historico.update(
                exige_enade=self.curso_campus.exige_enade,
                foi_convocado_enade=len(convocacoes) > 0,
                convocacoes=convocacoes,
            )
            # ATIVIDADES COMPLEMENTARES
            historico.update(
                exige_accs=self.get_ch_atividades_complementares_esperada() > 0, accs=self.get_atividades_complementares().filter(deferida=True)
            )
            # QUADRO RESUMO
            historico.update(
                ch_componentes_obrigatorios=self.matriz and self.get_ch_componentes_regulares_obrigatorios_esperada() or 0,
                ch_componentes_obrigatorios_cumprida=self.matriz and self.get_ch_componentes_regulares_obrigatorios_cumprida() or 0,
                ch_componentes_optativos=self.matriz and self.get_ch_componentes_regulares_optativos_esperada() or 0,
                ch_componentes_optativos_cumprida=self.matriz and self.get_ch_componentes_regulares_optativos_cumprida() or 0,
                ch_componentes_eletivos=self.matriz and self.get_ch_componentes_eletivos_esperada() or 0,
                ch_componentes_eletivos_cumprida=self.matriz and self.get_ch_componentes_eletivos_cumprida() or 0,
                ch_componentes_seminario=self.matriz and self.get_ch_componentes_seminario_esperada() or 0,
                ch_componentes_seminario_cumprida=self.matriz and self.get_ch_componentes_seminario_cumprida() or 0,
                ch_componentes_pratica_como_componente=self.matriz and self.get_ch_pratica_como_componente_esperada() or 0,
                ch_componentes_pratica_como_componente_cumprida=self.matriz and self.get_ch_componentes_pratica_como_componente_cumprida() or 0,
                ch_componentes_visita_tecnica=self.matriz and self.get_ch_visita_tecnica_esperada() or 0,
                ch_componentes_visita_tecnica_cumprida=self.matriz and self.get_ch_componentes_visita_tecnica_cumprida() or 0,
                ch_atividades_pratica_profissional=self.get_ch_atividade_pratica_profissional_esperada(),
                ch_atividades_pratica_profissional_cumprida=self.get_ch_atividade_pratica_profissional_realizada(),
                ch_componentes_pratica_profissional=self.matriz and self.get_ch_componentes_pratica_profissional_esperada(incluir_atpa=True) or 0,
                ch_componentes_pratica_profissional_cumprida=self.matriz
                and self.get_ch_componentes_pratica_profissional_cumprida(incluir_atpa=True)
                or 0,
                ch_componentes_tcc=self.matriz and self.get_ch_componentes_tcc_esperada() or 0,
                ch_componentes_tcc_cumprida=self.matriz and self.get_ch_componentes_tcc_cumprida() or 0,
                ch_atividades_complementares=self.matriz and self.get_ch_atividades_complementares_esperada() or 0,
                ch_atividades_complementares_cumprida=self.matriz and self.get_ch_atividades_complementares_cumprida() or 0,
                ch_atividades_extensao=self.matriz and self.get_ch_atividades_extensao_esperada() or 0,
                ch_atividades_extensao_cumprida=self.matriz and self.get_ch_atividade_extensao_cumprida() or 0,
                ch_total=self.matriz and self.matriz.get_carga_horaria_total_prevista() or 0,
                ch_total_cumprida=self.matriz and self.get_carga_horaria_total_cumprida() or 0,
            )
            # DIPLOMA
            registro_emissao_diploma = self.get_registro_emissao_diploma()
            historico.update(
                data_conclusao_curso=self.dt_conclusao_curso,
                data_emissao_diploma=self.data_expedicao_diploma,
                data_colacao_grau=self.get_data_colacao_grau(),
                responsavel_emissao_diploma=registro_emissao_diploma and registro_emissao_diploma.emissor or None,
                emitiu_diploma=registro_emissao_diploma is not None,
                livro=registro_emissao_diploma and registro_emissao_diploma.get_livro(),
                folha=registro_emissao_diploma and registro_emissao_diploma.folha,
                numero_registro=registro_emissao_diploma and registro_emissao_diploma.numero_registro,
                data_expedicao=registro_emissao_diploma and registro_emissao_diploma.data_expedicao,
                dirigente_maximo=registro_emissao_diploma and registro_emissao_diploma.dirigente_maximo or None,
            )
            # DIRETORIA
            historico.update(
                diretor_geral_exercicio=self.curso_campus.diretoria.diretor_geral_exercicio
                and str(self.curso_campus.diretoria.diretor_geral_exercicio.relacionamento)
                or '-',
                diretor_academico_exercicio=self.curso_campus.diretoria.diretor_academico_exercicio
                and str(self.curso_campus.diretoria.diretor_academico_exercicio.relacionamento)
                or '-',
            )
            # COMPONENTES
            historico.update(grupos_componentes=grupos_componentes, observacoes=observacoes)
            historico.update(integralizou_ensino_medio=self.integralizou_ensino_medio)
            historico.update(obs_integralizacao_ensino_medio=self.obs_integralizacao_ensino_medio)
            historico.update(final=final)
            return historico

    def get_historico_legado(self, final=True, eletronico=False):
        historico = {}
        if Configuracao.get_valor_por_chave('edu', 'academico_endereco_banco'):
            from edu.q_academico import DAO

            dao = DAO()
            lista_historico_legado = dao.importar_historico_legado_resumo(self)
            q_academico = lista_historico_legado and lista_historico_legado[0] or {}
            grupos_componentes = {}
            grupos_componentes['Disciplinas'] = []
            grupos_componentes['Prática Profissional'] = []
            observacoes = []
            ch_pratica_profissional_total = 0
            ch_pratica_profissional_total_cumprida = 0
            for linha_historico in lista_historico_legado[1:]:
                componente = {
                    'ano_periodo_letivo': linha_historico['ano_periodo_letivo'],
                    'periodo_matriz': linha_historico['periodo'],
                    'sigla_componente': linha_historico['sigla'],
                    'descricao_componente': linha_historico['descricao'],
                    'codigo_turma': linha_historico['turma'],
                    'carga_horaria': linha_historico['carga_horaria'],
                    'carga_horaria_cumprida': linha_historico['carga_horaria_cumprida'],
                    'media_final_disciplina': linha_historico['nota'],
                    'percentual_carga_horaria_frequentada': linha_historico['frequencia'],
                    'situacao_display': linha_historico['situacao'],
                    'aproveitada': 'Aproveit' in linha_historico['situacao'],
                    'certificada': 'Certific' in linha_historico['situacao'],
                    'professores': [
                        [
                            linha_historico['sigla'],
                            linha_historico['descricao'],
                            linha_historico['nome_professor'],
                            linha_historico['titulacao_professor'],
                        ]
                    ],
                }
                if (componente['aproveitada'] or componente['certificada']) and componente['professores']:
                    if not componente['professores'][0][2]:
                        componente['professores'][0][2] = 'Não Informado'
                    if not componente['professores'][0][3]:
                        componente['professores'][0][3] = 'Graduado(a)'
                if linha_historico['is_pratica_profissional']:
                    grupos_componentes['Prática Profissional'].append(componente)
                    ch_pratica_profissional_total += linha_historico['carga_horaria'] or 0
                    ch_pratica_profissional_total_cumprida += linha_historico['carga_horaria_cumprida'] or 0
                else:
                    grupos_componentes['Disciplinas'].append(componente)

                observacao = linha_historico['observacao']
                if observacao:
                    observacao = 'A disciplina {} - {} possui a seguinte observação: {}'.format(
                        linha_historico['sigla'], linha_historico['descricao'], observacao
                    )
                    observacoes.append(observacao)

            grupos_componentes['Disciplinas'] = sorted(grupos_componentes['Disciplinas'], key=lambda k: k['ano_periodo_letivo'])
            grupos_componentes['Prática Profissional'] = sorted(grupos_componentes['Prática Profissional'], key=lambda k: k['ano_periodo_letivo'])

            historico.update(assinatura_eletronica=eletronico)
            historico.update(is_integralizado_cursando=False)
            historico.update(creditos_especiais=[])
            historico.update(estagios=[])
            historico.update(is_lancamento_conceito=False)
            uo = self.curso_campus.diretoria.setor.uo
            historico.update(
                nome_campus=uo.nome,
                telefone_campus=uo.telefone,
                endereco_campus=uo.endereco,
                municipio_campus=uo.municipio and uo.municipio.nome or '',
                hoje=datetime.date.today(),
                uf_campus=uo.municipio and uo.municipio.uf or None,
                cep_campus=uo.cep,
                cnpj_campus=uo.cnpj,
                codigo_inep=uo.codigo_inep,
                codigo_emec=uo.codigo_emec,
                novo_modelo=datetime.date.today() >= datetime.date(2019, 4, 25),
                credenciamento=Configuracao.get_valor_por_chave('edu', 'credenciamento'),
                recredenciamento=Configuracao.get_valor_por_chave('edu', 'recredenciamento'),
            )
            # DADOS PESSOAIS
            historico.update(
                sexo=self.pessoa_fisica.sexo,
                nome=self.get_nome_social_composto(),
                cpf=self.pessoa_fisica.cpf,
                data_nascimento=self.pessoa_fisica.nascimento_data,
                nacionalidade=self.nacionalidade and self.get_nacionalidade_display() or None,
                naturalidade=q_academico.get('naturalidade'),
            )
            # RG
            historico.update(
                numero_rg=self.numero_rg,
                orgao_emissao_rg=self.orgao_emissao_rg,
                uf_emissao_rg=self.uf_emissao_rg,
                data_emissao_rg=self.data_emissao_rg,
            )
            # FILIAÇÃO
            historico.update(nome_pai=self.nome_pai, nome_mae=self.nome_mae)
            # ENDEREÇO
            historico.update(
                logradouro=self.logradouro, numero=self.numero, complemento=self.complemento, bairro=self.bairro, cidade=self.cidade, cep=self.cep
            )
            # TÍTULO DE ELEITOR
            historico.update(
                numero_titulo_eleitor=self.numero_titulo_eleitor,
                zona_titulo_eleitor=self.zona_titulo_eleitor,
                secao_titulo_eleitor=self.secao,
                uf_emissao_titulo_eleitor=self.uf_emissao_titulo_eleitor,
                data_emissao_titulo_eleitor=self.data_emissao_titulo_eleitor,
            )
            # CARTEIRA RESERVISTA
            historico.update(
                numero_carteira_reservista=self.numero_carteira_reservista,
                regiao_carteira_reservista=self.regiao_carteira_reservista,
                serie_carteira_reservista=self.serie_carteira_reservista,
                uf_emissao_carteira_reservista=self.estado_emissao_carteira_reservista,
                ano_carteira_reservista=self.ano_carteira_reservista,
            )
            # DADOS ACADEMICOS
            historico.update(
                ira=self.get_ira(),
                matricula=self.matricula,
                situacao=self.situacao,
                forma_ingresso=q_academico.get('forma_ingresso'),
                data_matricula=self.data_matricula,
                ano_periodo_ingresso=f'{self.ano_letivo}/{self.periodo_letivo}',
                mes_ano_processo_seletivo=None,
                descricao_linha_pesquisa=None,
            )
            # DADOS DO CURSO
            historico.update(
                regime=q_academico.get('regime'),
                periodicidade=q_academico.get('periodicidade'),
                descricao_matriz=q_academico.get('matriz'),
                descricao_curso=q_academico.get('curso'),
                resolucao_criacao=q_academico.get('autorizacao'),
                reconhecimento_texto=q_academico.get('reconhecimento'),
                ead=q_academico.get('ead') == 1,
            )
            # TCC
            historico.update(
                exige_tcc=q_academico.get('projeto_tipo') is not None,
                apresentou_tcc=q_academico.get('projeto_tipo') is not None,
                tipo_projeto=q_academico.get('projeto_tipo'),
                titulo_projeto=q_academico.get('projeto_titulo'),
                data_defesa=q_academico.get('projeto_data_defesa'),
                situacao_projeto=q_academico.get('projeto_situacao'),
                nota_projeto=q_academico.get('projeto_nota'),
            )
            # ENADE
            convocacao = {}
            justificativas_enade = {
                'Estudante habilitado ao ENADE, devido a sua condição de INGRESSANTE': 'Ingressante / Participante',
                'Estudante dispensado de realização do ENADE, em razão do calendário trienal': 'Dispensado, em razão do calendário trienal',
                'Estudante dispensado conforme Art. 6º, § 2º da Portaria Normativa Nº 8, de 14 de março de 2014': 'Dispensado pelo MEC',
                'Estudante dispensado conforme Art. 9º, § 7º da Portaria Normativa Nº 8, de 14 de março de 2014': 'Dispensado pelo MEC',
                'Estudante dispensado conforme Artº 9, § 7º, da Portaria Normativa nº 8 de 14 de março de 2014': 'Dispensado pelo MEC',
                'Estudante dispensado de realização do ENADE, em razão da natureza do curso': 'Dispensado, em razão da natureza do curso',
                'Estudante dispensado de realização do ENADE, por razão de ordem pessoal': 'Dispensado, por razão de ordem pessoal',
                'Estudante não participante do ENADE, por ato da instituição de ensino': 'Dispensado, por ato da instituição de ensino',
                'Estudante não habilitado ao ENADE em razão do calendário do ciclo avaliativo, em razão da pandemia de COVID-19': 'Estudante não habilitado ao ENADE em razão do calendário do ciclo avaliativo',
            }
            situacao_enade = q_academico.get('enade_situacao')
            if situacao_enade == 'Regular':
                situacao_para_diploma_digital = 'Ingressante / Participante'
            else:
                situacao_para_diploma_digital = justificativas_enade.get(
                    q_academico.get('enade_justificativa'), q_academico.get('enade_justificativa')
                )
            convocacao.update(
                situacao_enade=situacao_enade,
                data_ultimo_enade=q_academico.get('enade_data_ultimo'),
                data_prova_enade=q_academico.get('enade_data_prova'),
                ano_letivo_enade=q_academico.get('enade_ano_letivo'),
                justificativa_enade=q_academico.get('enade_justificativa'),
                situacao_para_diploma_digital=situacao_para_diploma_digital,
                tipo_convocacao='Concluinte',
            ) if self.curso_campus.exige_enade else convocacao.update(
                situacao_enade=None,
                data_ultimo_enade=None,
                data_prova_enade=None,
                ano_letivo_enade=getattr(self.dt_conclusao_curso, 'year', None),
                justificativa_enade='Estudante dispensado de realização do ENADE, em razão da natureza do curso',
                situacao_para_diploma_digital='Dispensado, em razão da natureza do curso',
                tipo_convocacao='Concluinte',
            )
            historico.update(
                exige_enade=self.curso_campus.exige_enade,
                foi_convocado_enade=q_academico.get('enade_situacao') is not None,
                convocacoes=[convocacao],
            )
            # DIPLOMA
            registro_emissao_diploma = self.get_registro_emissao_diploma()
            historico.update(
                data_conclusao_curso=self.dt_conclusao_curso,
                data_emissao_diploma=self.data_expedicao_diploma,
                data_colacao_grau=q_academico.get('data_colacao_grau') and q_academico.get('data_colacao_grau').date() or None,
                responsavel_emissao_diploma=registro_emissao_diploma and registro_emissao_diploma.emissor or None,
                emitiu_diploma=registro_emissao_diploma is not None,
                livro=registro_emissao_diploma and registro_emissao_diploma.get_livro(),
                folha=registro_emissao_diploma and registro_emissao_diploma.folha,
                numero_registro=registro_emissao_diploma and registro_emissao_diploma.numero_registro,
                data_expedicao=registro_emissao_diploma and registro_emissao_diploma.data_expedicao,
            )
            # ATIVIDADES COMPLEMENTARES
            accs = q_academico.get('accs')
            ch_accs_total = 0
            if accs:
                for acc in accs:
                    acc['ano_letivo'] = Ano.objects.get(ano=acc['ano_letivo'])
                    ch_accs_total += acc.get('is_curricular') or 0
            historico.update(accs=accs)
            # CARGAS-HORÁRIAS
            realizou_pcc = (q_academico.get('projeto_tipo', '') or '').encode('utf-8') == 'PCC (Projeto de Conclusão de Curso)'
            historico.update(
                grupos_componentes=grupos_componentes,
                ch_componentes_obrigatorios=int(q_academico.get('ch_obrigatoria_prevista', 0)),
                ch_componentes_optativos=int(q_academico.get('ch_optativa_prevista', 0)),
                ch_componentes_eletivos=0,
                ch_componentes_seminario=0,
                ch_componentes_pratica_profissional=int(q_academico.get('ch_estagio_prevista', 0)) or ch_pratica_profissional_total,
                ch_atividades_complementares=int(q_academico.get('ch_complementar_prevista', 0)),
                ch_componentes_tcc=int(q_academico.get('ch_projeto_prevista', 0)),
                ch_total=int(q_academico.get('ch_prevista', 0)),
                ch_componentes_obrigatorios_cumprida=int(q_academico.get('ch_obrigatoria_cumprida', 0)),
                ch_componentes_optativos_cumprida=int(q_academico.get('ch_optativa_cumprida', 0)),
                ch_componentes_eletivos_cumprida=0,
                ch_componentes_seminario_cumprida=0,
                ch_componentes_pratica_profissional_cumprida=int(q_academico.get('ch_estagio_cumprida', 0) + ch_pratica_profissional_total_cumprida),
                ch_atividades_complementares_cumprida=int(q_academico.get('ch_complementar_cumprida', 0)),
                ch_componentes_tcc_cumprida=int(q_academico.get('projeto_ch', 0)),
                ch_total_cumprida=int(q_academico.get('ch_cumprida', 0)),
            )

            if realizou_pcc:
                historico['ch_componentes_tcc_cumprida'] = 0

            if ch_accs_total > historico['ch_atividades_complementares_cumprida']:
                historico['ch_atividades_complementares_cumprida'] = ch_accs_total

            historico['ch_total_cumprida'] = (
                historico['ch_componentes_obrigatorios_cumprida']
                + historico['ch_componentes_optativos_cumprida']
                + historico['ch_componentes_eletivos_cumprida']
                + historico['ch_componentes_seminario_cumprida']
                + historico['ch_componentes_pratica_profissional_cumprida']
                + historico['ch_atividades_complementares_cumprida']
            )
            historico['ch_total'] = (
                historico['ch_componentes_obrigatorios']
                + historico['ch_componentes_optativos']
                + historico['ch_componentes_eletivos']
                + historico['ch_componentes_seminario']
                + historico['ch_componentes_pratica_profissional']
                + historico['ch_atividades_complementares']
                + historico['ch_componentes_tcc']
            )

            # adicionar TCC apenas se previsto na matriz
            if historico['ch_componentes_tcc']:
                historico['ch_total_cumprida'] += historico['ch_componentes_tcc_cumprida']

            # OBSERVAÇÕES
            historico.update(observacoes=observacoes)
            historico.update(integralizou_ensino_medio=self.integralizou_ensino_medio)
            historico.update(obs_integralizacao_ensino_medio=self.obs_integralizacao_ensino_medio)
            historico.update(final=final)
        return historico

    def get_historico_legado_sica(self, final=True, eletronico=False):
        if self.is_sica():
            from sica.models import Historico

            historico_sica = Historico.objects.filter(aluno_id=self.pk).first()
            uo = self.curso_campus.diretoria.setor.uo
            observacoes = []
            if self.observacao_historico:
                observacoes.append(self.observacao_historico)

            grupos_componentes = {}
            grupos_componentes['Disciplinas Curriculares'] = []

            for registro_historico in historico_sica.get_registros_curriculares():
                componentes = grupos_componentes['Disciplinas Curriculares']
                componente = {
                    'pk': registro_historico.componente.pk,
                    'matricula_diario': None,
                    'matricula_diario_resumida': None,
                    'ano_periodo_letivo': f'{registro_historico.ano}/{registro_historico.periodo}',
                    'periodo_matriz': registro_historico.periodo_matriz,
                    'sigla_componente': registro_historico.componente.sigla,
                    'descricao_componente': registro_historico.componente.nome,
                    'codigo_turma': registro_historico.turma,
                    'codigo_diario': '',
                    'carga_horaria': registro_historico.get_carga_horaria() or '-',
                    'media_final_disciplina': registro_historico.get_nota(),
                    'percentual_carga_horaria_frequentada': registro_historico.get_frequencia(),
                    'situacao_display': registro_historico.get_situacao(),
                    'situacao_legend': '',
                    'certificavel': False,
                    'cursada': False,
                    'certificada': False,
                    'aproveitada': False,
                    'equivalente': False,
                }
                componentes.append(componente)

            historico = {}
            historico.update(assinatura_eletronica=eletronico)
            historico.update(legado_sica=True)
            historico.update(is_integralizado_cursando=False)
            historico.update(creditos_especiais=[])
            historico.update(estagios=[])
            historico.update(is_lancamento_conceito=False)
            # CABEÇALHO
            historico.update(
                nome_campus=uo.nome,
                telefone_campus=uo.telefone,
                endereco_campus=uo.endereco,
                municipio_campus=uo.municipio and uo.municipio.nome or '',
                hoje=datetime.date.today(),
                uf_campus=uo.municipio and uo.municipio.uf or None,
                cep_campus=uo.cep,
                cnpj_campus=uo.cnpj,
                codigo_inep=uo.codigo_inep,
                codigo_emec=uo.codigo_emec,
                novo_modelo=datetime.date.today() >= datetime.date(2019, 4, 25),
                credenciamento=Configuracao.get_valor_por_chave('edu', 'credenciamento'),
                recredenciamento=Configuracao.get_valor_por_chave('edu', 'recredenciamento'),
            )
            # DADOS PESSOAIS
            historico.update(
                sexo=self.pessoa_fisica.sexo,
                nome=self.get_nome_social_composto(),
                cpf=self.pessoa_fisica.cpf,
                data_nascimento=self.pessoa_fisica.nascimento_data,
                nacionalidade=self.nacionalidade and self.get_nacionalidade_display() or None,
                naturalidade=self.naturalidade,
            )
            historico.update(professores=[])
            # RG
            historico.update(
                numero_rg=self.numero_rg,
                orgao_emissao_rg=self.orgao_emissao_rg,
                uf_emissao_rg=self.uf_emissao_rg,
                data_emissao_rg=self.data_emissao_rg,
            )
            # FILIAÇÃO
            historico.update(nome_pai=self.nome_pai, nome_mae=self.nome_mae)
            # ENDEREÇO
            historico.update(
                logradouro=self.logradouro, numero=self.numero, complemento=self.complemento, bairro=self.bairro, cidade=self.cidade, cep=self.cep
            )
            # TÍTULO DE ELEITOR
            historico.update(
                numero_titulo_eleitor=self.numero_titulo_eleitor,
                zona_titulo_eleitor=self.zona_titulo_eleitor,
                secao_titulo_eleitor=self.secao,
                uf_emissao_titulo_eleitor=self.uf_emissao_titulo_eleitor,
                data_emissao_titulo_eleitor=self.data_emissao_titulo_eleitor,
            )
            # CARTEIRA RESERVISTA
            historico.update(
                numero_carteira_reservista=self.numero_carteira_reservista,
                regiao_carteira_reservista=self.regiao_carteira_reservista,
                serie_carteira_reservista=self.serie_carteira_reservista,
                uf_emissao_carteira_reservista=self.estado_emissao_carteira_reservista,
                ano_carteira_reservista=self.ano_carteira_reservista,
            )
            # DADOS ACADEMICOS
            historico.update(
                ira=None,
                matricula=self.matricula,
                situacao=self.situacao,
                forma_ingresso='',
                data_matricula='',
                ano_periodo_ingresso=f'{self.ano_letivo}/{self.periodo_letivo}',
                mes_ano_processo_seletivo='',
                descricao_linha_pesquisa=self.linha_pesquisa and self.linha_pesquisa.descricao,
            )
            # DADOS DO CURSO
            historico.update(
                codigo_emec_curso=self.curso_campus.codigo_emec,
                descricao_curso=self.curso_campus.descricao_historico,
                # regime=self.matriz.estrutura.get_tipo_avaliacao_display,
                periodicidade=self.curso_campus.get_periodicidade_display,
                descricao_matriz=historico_sica.matriz.nome,
                reconhecimento_texto=historico_sica.matriz.reconhecimento,
                # resolucao_criacao=self.matriz_curso.get_autorizacao()
            )
            # TCC
            historico.update(
                exige_tcc=False,
                apresentou_tcc=False,
            )
            # ENADE
            historico.update(
                exige_enade=False,
            )
            # DIPLOMA
            registro_emissao_diploma = self.get_registro_emissao_diploma()
            historico.update(
                data_conclusao_curso=self.dt_conclusao_curso,
                data_emissao_diploma=self.data_expedicao_diploma,
                data_colacao_grau=self.get_data_colacao_grau(),
                responsavel_emissao_diploma=registro_emissao_diploma and registro_emissao_diploma.emissor or None,
                emitiu_diploma=registro_emissao_diploma is not None,
                livro=registro_emissao_diploma and registro_emissao_diploma.get_livro(),
                folha=registro_emissao_diploma and registro_emissao_diploma.folha,
                numero_registro=registro_emissao_diploma and registro_emissao_diploma.numero_registro,
                data_expedicao=registro_emissao_diploma and registro_emissao_diploma.data_expedicao,
                dirigente_maximo=registro_emissao_diploma and registro_emissao_diploma.dirigente_maximo or None,
            )
            # DIRETORIA
            historico.update(
                diretor_geral_exercicio=self.curso_campus.diretoria.diretor_geral_exercicio
                and str(self.curso_campus.diretoria.diretor_geral_exercicio.relacionamento)
                or '-',
                diretor_academico_exercicio=self.curso_campus.diretoria.diretor_academico_exercicio
                and str(self.curso_campus.diretoria.diretor_academico_exercicio.relacionamento)
                or '-',
            )
            # COMPONENTES
            historico.update(grupos_componentes=grupos_componentes, observacoes=observacoes)

            # CH
            historico.update(ch_cumprida=historico_sica.get_ch_cumprida() or 0)
            historico.update(ch_geral=historico_sica.get_ch_geral() or 0)
            historico.update(ch_especial=historico_sica.get_ch_especial() or 0)
            historico.update(carga_horaria_estagio=historico_sica.carga_horaria_estagio or 0)

            return historico

    def get_procedimentos_matricula(self):
        return ProcedimentoMatricula.objects.filter(matricula_periodo__aluno_id=self.id).order_by('-data', '-id')

    def get_procedimentos_reducao_ch(self):
        return ProcedimentoReducaoCH.objects.filter(matricula_periodo__aluno_id=self.id).order_by('-data', '-id')

    def get_ch_cumprida(self):
        return max(self.matriz.get_carga_horaria_total_prevista() - self.get_ch_pendente(), 0)

    def is_user(self, request):
        user = self.get_user()
        return request.user and user and request.user.id == user.id

    @property
    def get_texto_condicao_incapacidade_idade(self):
        hoje = datetime.date.today()
        data_para_maioridade = hoje - datetime.timedelta(days=365 * 18)
        data_para_16_anos = hoje - datetime.timedelta(days=365 * 16)
        data_nascimento = self.pessoa_fisica.nascimento_data or datetime.date.today()
        retorno = ''
        if data_nascimento > data_para_maioridade and data_nascimento <= data_para_16_anos:
            retorno = 'O Aluno tem entre 16 e 18 anos e pode figurar como relativamente incapaz a certos atos ou à maneira de os exercer conforme Código Cívil.'
        elif data_nascimento > data_para_16_anos:
            retorno = (
                'O Aluno tem menos de 16 anos e figura como absolutamente incapaz a certos atos ou à maneira de os exercer conforme Código Cívil.'
            )
        return retorno

    @property
    def eh_menor_idade(self):
        hoje = datetime.date.today()
        data_para_maioridade = hoje - datetime.timedelta(days=365 * 18)
        data_nascimento = self.pessoa_fisica.nascimento_data or datetime.date.today()
        return data_nascimento > data_para_maioridade

    def get_ext_combo_template(self):
        out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{self}</dd>']
        img_src = self.get_foto_75x100_url()
        out.append(f'<dt class="visually-hidden">Curso</dt><dd>{self.curso_campus}</dd>')
        app = get_app_context()
        if app in settings.INSTALLED_APPS:
            if hasattr(self, f'get_ext_combo_template_{app}'):
                out += getattr(self, f'get_ext_combo_template_{app}')()
        template = """<div class="person">
            <div class="photo-circle">
                <img src="{}" alt="Foto de {}" />
            </div>
            <dl>{}</dl>
        </div>""".format(img_src, self, ''.join(out))
        return template

    def get_ext_combo_template_ae(self):
        out = []
        if 'ae' in settings.INSTALLED_APPS:
            Caracterizacao = apps.get_model('ae', 'Caracterizacao')
            caracterizacao_existe = Caracterizacao.objects.filter(aluno=self).exists()
            if not caracterizacao_existe:
                out.append('<dt class="visually-hidden">Caracterização</dt><dd class="false">Não realizou caracterização</dd>')
            else:
                out.append('<dt class="visually-hidden">Caracterização</dt><dd class="true">Realizou caracterização</dd>')
            if self.inscricao_set.exists():
                out.append('<dt class="visually-hidden">Inscrição</dt><dd class="true">Inscrito em programa</dd>')
            else:
                out.append('<dt class="visually-hidden">Inscrição</dt><dd class="false">Não inscrito em programa</dd>')
        return out

    def get_ext_combo_template_documento_eletronico(self):
        out = []
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            if self.eh_menor_idade:
                out.append(f'<dt class="visually-hidden">Aluno menor de 18</dt><dd class="false">{self.get_texto_condicao_incapacidade_idade}</dd>')
        return out

    @property
    def username(self):
        user = self.get_user()
        return user.username if user else self.matricula

    @property
    def campus(self):
        return self.curso_campus.diretoria.setor.uo

    def pode_ser_excluido(self):
        if self.eh_aluno_minicurso():
            return True
        qs_notas = MatriculaDiario.objects.filter(matricula_periodo__aluno=self, matricula_periodo__aluno__curso_campus__ativo=True).exclude(
            nota_1=None, nota_2=None, nota_3=None, nota_4=None, nota_final=None
        )
        qs_procedimentos = ProcedimentoMatricula.objects.filter(matricula_periodo__aluno=self)
        return (self.is_matriculado() or self.is_matricula_vinculo()) and self.matriz and not qs_notas.exists() and not qs_procedimentos.exists()

    def possui_certificacao_parcial(self):
        return self.registroemissaodiploma_set.filter(tipo=RegistroEmissaoDiploma.TIPO_CERTIFICACAO_PARCIAL).exclude(cancelado=True).exists()

    def possui_pendencia(
        self, incluir_colacao_grau=True, incluir_enade=True, incluir_atividade_complementar=True, incluir_pratica_profissional=True, incluir_tcc=True
    ):
        return (
            (incluir_tcc and self.pendencia_tcc)
            or (incluir_enade and self.pendencia_enade)
            or (incluir_colacao_grau and self.pendencia_colacao_grau)
            or (incluir_atividade_complementar and self.pendencia_ch_atividade_complementar)
            or (incluir_tcc and self.pendencia_ch_tcc)
            or (incluir_pratica_profissional and (self.pendencia_ch_pratica_profissional or self.pendencia_pratica_profissional))
            or self.pendencia_ch_seminario
            or self.pendencia_ch_eletiva
            or self.pendencia_ch_optativa
            or self.pendencia_ch_obrigatoria
            or self.pendencia_ch_atividades_extensao
        )

    def pode_realizar_colacao_grau(self, ano_letivo, periodo_letivo, data_colacao_grau):
        if not self.curso_campus.exige_colacao_grau:
            return False
        if self.matriculaperiodo_set.filter(
            ano_letivo=ano_letivo, periodo_letivo=periodo_letivo, situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO
        ).exists():
            return False
        if self.matriculaperiodo_set.filter(situacao_id=SituacaoMatriculaPeriodo.MATRICULADO).exists():
            return False

        self.atualizar_pendencias()
        self.save(sync_user=False)
        cumpriu_enade = self.cumpriu_enade(data_colacao_grau=data_colacao_grau) if self.pendencia_enade else True

        return cumpriu_enade and not self.possui_pendencia(incluir_colacao_grau=False, incluir_enade=False)

    def possui_pratica_profissional_pendente(self):
        if self.matriz:
            if self.matriz.get_matrizppc():
                return bool(self.get_pendencias_atividade_pratica_profissional(resumido=True))
            else:
                possui_pratica_profissional_cadastrada = (
                    self.praticaprofissional_set.exists() or self.aprendizagem_set.exists() or self.atividadeprofissionalefetiva_set.exists()
                )

                if self.matriz.exige_estagio and not possui_pratica_profissional_cadastrada:
                    return True

                if possui_pratica_profissional_cadastrada:
                    if self.matriz.exige_estagio:
                        return self.matriz.ch_minima_estagio > self.get_ch_pratica_profissional_concluida()
                    else:
                        return (
                            self.praticaprofissional_set.filter(data_fim__isnull=True).exists()
                            or self.aprendizagem_set.filter(data_encerramento__isnull=True).exists()
                            or self.atividadeprofissionalefetiva_set.filter(encerramento__isnull=True).exists()
                        )
                else:
                    ch_pratica_profissional_esperada = self.matriz.ch_pratica_profissional
                    ch_pratica_profissional_cumprida = self.get_ch_componentes_pratica_profissional_cumprida()
                    return ch_pratica_profissional_cumprida < ch_pratica_profissional_esperada
        return False

    def get_situacao_certificacao_parcial(self, configuracaocertificacaoparcial_id):
        ComponenteCurricularCertificacaoParcial = apps.get_model('edu', 'ComponenteCurricularCertificacaoParcial')
        MatriculaDiario = apps.get_model('edu', 'MatriculaDiario')
        cc_ids = ComponenteCurricularCertificacaoParcial.objects.filter(
            configuracao_certificacao_parcial_id=configuracaocertificacaoparcial_id
        ).values_list('componente_curricular_id', flat=True)
        qs = MatriculaDiario.objects.filter(matricula_periodo__aluno_id=self.id, diario__componente_curricular_id__in=cc_ids)
        if qs.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).exists():
            return 'Em andamento'
        if not qs.exclude(situacao=MatriculaDiario.SITUACAO_APROVADO).exists():
            return 'Concluído'
        return 'Não concluído'

    def get_ch_pratica_profissional_concluida(self):
        ch_pratica = self.praticaprofissional_set.filter(data_fim__isnull=False).aggregate(Sum('ch_final')).get('ch_final__sum') or 0
        ch_aprendizagem = self.aprendizagem_set.filter(data_encerramento__isnull=False).aggregate(Sum('ch_final')).get('ch_final__sum') or 0
        ch_atividade_efetiva = (
            self.atividadeprofissionalefetiva_set.filter(encerramento__isnull=False).aggregate(Sum('ch_final')).get('ch_final__sum') or 0
        )
        return ch_pratica + ch_aprendizagem + ch_atividade_efetiva

    def get_situacao_id(self):
        """Retorna o código da situação acadêmica atual do aluno.

        A lógica considera: matrícula ativa em período letivo, regime FIC/PROITEC,
        pendências de conclusão, matrículas em aberto sem vínculos, colação de grau
        e conclusão. A situação é determinada com base no estado atual dos períodos
        letivos e matrículas em diários do aluno.

        Returns:
            inteiro correspondente à situacao (``SituacaoMatricula``).
        """
        if MatriculaPeriodo.objects.filter(aluno=self, situacao__id=SituacaoMatriculaPeriodo.MATRICULADO).exists():
            return SituacaoMatricula.MATRICULADO

        # Cursos FICs possuem apenas um período letivo e requer, portanto, um tratamentno diferenciado. Exceto para matrizes com estrutura modular.
        if self.curso_campus and self.curso_campus.is_fic() and not self.matriz.is_regime_modular():
            situacoes_periodo = list(self.matriculaperiodo_set.values_list('situacao_id', flat=True))
            if (
                self.is_proitec()
                and len(situacoes_periodo) == 1
                and situacoes_periodo[0] in [SituacaoMatriculaPeriodo.EM_ABERTO, SituacaoMatriculaPeriodo.MATRICULADO]
            ):
                return SituacaoMatricula.MATRICULADO
            else:
                if self.possui_pendencia() or SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA in situacoes_periodo:
                    return SituacaoMatricula.NAO_CONCLUIDO
                else:
                    return SituacaoMatricula.CONCLUIDO
        else:
            # Caso o aluno não possua nenhum período letivo aberto, mas não cumpriu todos os requisitos de conclusão
            if self.possui_pendencia():
                if self.get_ultima_matricula_periodo().situacao == SituacaoMatriculaPeriodo.MATRICULADO:
                    return SituacaoMatricula.MATRICULADO
                else:
                    return self.situacao_id
            else:
                # Caso o aluno possua um matrícula no período com sistuação "Em Aberto", essa matrícula será excluída
                qs_em_aberto = MatriculaPeriodo.objects.filter(aluno=self, situacao__id=SituacaoMatriculaPeriodo.EM_ABERTO)
                if qs_em_aberto.filter(
                    creditoespecial__isnull=True,
                    matriculadiario__isnull=True,
                    matriculadiarioresumida__isnull=True,
                    certificacaoconhecimento__isnull=True,
                    aproveitamentoestudo__isnull=True,
                    projetofinal__isnull=True,
                    aproveitamentocomponente__isnull=True,
                ).exists():
                    qs_em_aberto.delete()
                if qs_em_aberto.exists():
                    return SituacaoMatricula.MATRICULADO
                else:
                    # A situação dos concluintes de cursos que requer colação de graua deve ser "Formado"
                    if self.curso_campus.exige_colacao_grau:
                        return SituacaoMatricula.FORMADO
                    else:
                        return SituacaoMatricula.CONCLUIDO

    def atualizar_pendencias(self):
        if self.matriz_id:
            if self.curso_campus and self.curso_campus.is_fic():
                self.pendencia_ch_obrigatoria = self.get_componentes_pendentes().exists()
            else:
                self.pendencia_tcc = self.matriz.exige_tcc and not self.apresentou_tcc() or False
                self.pendencia_enade = bool(self.curso_campus and self.curso_campus.exige_enade and not self.cumpriu_enade())
                self.pendencia_pratica_profissional = self.possui_pratica_profissional_pendente() or False
                self.pendencia_colacao_grau = bool(self.curso_campus and self.curso_campus.exige_colacao_grau and not self.colou_grau())
                self.pendencia_ch_atividade_complementar = (
                    self.get_ch_atividades_complementares_esperada() and self.get_ch_atividades_complementares_pendente() > 0 or False
                )
                self.pendencia_ch_tcc = self.get_ch_componentes_tcc_esperada() and self.get_ch_componentes_tcc_pendente() > 0 or False
                self.pendencia_ch_pratica_profissional = (
                    self.get_ch_componentes_pratica_profissional_esperada() and self.get_ch_componentes_pratica_profissional_pendente() > 0 or False
                )
                self.pendencia_ch_atividades_aprofundamento = (
                    self.get_ch_atividade_aprofundamento_esperada() and self.get_ch_atividade_aprofundamento_pendente() > 0 or False
                )

                self.pendencia_ch_atividades_extensao = False
                if self.matriz.ch_atividades_extensao:
                    if (
                        self.get_ch_extensao_componentes_pendente()
                        or self.get_ch_extensao_outras_atividades_pendente()
                        or self.get_ch_extensao_outros_componentes_pendente()
                    ):
                        self.pendencia_ch_atividades_extensao = True

                self.pendencia_ch_seminario = (
                    self.get_ch_componentes_seminario_esperada() and self.get_ch_componentes_seminario_pendente() > 0 or False
                )
                self.pendencia_ch_pratica_como_componente = (
                    self.get_ch_pratica_como_componente_esperada() and self.get_ch_componentes_pratica_como_componente_pendente() > 0 or False
                )
                self.pendencia_ch_visita_tecnica = (
                    self.get_ch_visita_tecnica_esperada() and self.get_ch_componentes_visita_tecnica_pendente() > 0 or False
                )
                self.pendencia_ch_eletiva = self.get_ch_componentes_eletivos_pendente() > 0 or False
                self.pendencia_ch_optativa = self.get_ch_componentes_regulares_optativos_pendente() > 0 or False
                self.pendencia_ch_obrigatoria = self.get_ch_componentes_regulares_obrigatorios_pendente() > 0 or False

    def calcular_indice_rendimento(self, parcial=False, matriculaperiodo=None):
        """Calcula o Índice de Rendimento Acadêmico (IRA) do aluno.

        O IRA pode ser calculado como média aritmética das notas finais ou média
        ponderada pela carga horária dos componentes, conforme a configuração da
        estrutura curricular. Alunos PROITEC não possuem IRA calculado.

        Args:
            parcial: quando ``True``, considera matrículas em andamento.
            matriculaperiodo: quando informado, filtra os registros até o período
                letivo especificado.

        Returns:
            valor decimal do IRA quando ``parcial`` é ``True`` ou ``matriculaperiodo``
            é informado; ``None`` caso contrário (o valor é persistido no campo
            ``ira`` do aluno).
        """
        from edu.models import HistoricoSituacaoMatricula, RegistroHistorico

        if self.is_proitec():
            return

        numerador = 0
        denominador = 0

        # Consultando os registros de matrícula em diários
        matriculas_diario = MatriculaDiario.objects.filter(matricula_periodo__aluno=self).exclude(diario__componente_curricular__qtd_avaliacoes=0)

        # exclui as matrículas com situação em aberto se não for parcial
        if not parcial:
            matriculas_diario = matriculas_diario.filter(
                situacao__in=[MatriculaDiario.SITUACAO_APROVADO, MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA]
            ).exclude(matricula_periodo__situacao_id__in=[SituacaoMatriculaPeriodo.MATRICULADO])

        # Consultando os registros de matrícula em diários do Q-Acadêmcio
        matriculas_diario_resumida = MatriculaDiarioResumida.objects.filter(
            media_final_disciplina__isnull=False,
            matricula_periodo__aluno=self,
            situacao__in=[
                MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_REPROVADO,
                MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
            ],
        ).exclude(matricula_periodo__situacao__id__in=[SituacaoMatriculaPeriodo.MATRICULADO])

        # filtra por matrícula período
        if matriculaperiodo is not None:
            matriculas_diario = matriculas_diario.filter(matricula_periodo__ano_letivo__ano__lte=matriculaperiodo.ano_letivo.ano)
            matriculas_diario_resumida = matriculas_diario_resumida.filter(matricula_periodo__ano_letivo__ano__lte=matriculaperiodo.ano_letivo.ano)
            if matriculaperiodo.periodo_letivo == 1:
                matriculas_diario = matriculas_diario.exclude(
                    matricula_periodo__ano_letivo__ano=matriculaperiodo.ano_letivo.ano, matricula_periodo__periodo_letivo=2
                )
                matriculas_diario_resumida = matriculas_diario_resumida.exclude(
                    matricula_periodo__ano_letivo__ano=matriculaperiodo.ano_letivo.ano, matricula_periodo__periodo_letivo=2
                )

        # Consultando as certificações de conhecimento
        certificacoes_conhecimento = CertificacaoConhecimento.objects.filter(matricula_periodo__aluno=self, ausente=False).exclude(
            componente_curricular__qtd_avaliacoes=0
        )
        # Consultando os aproveitamentos de estudo
        aproveitamentos_estudo = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno=self).exclude(componente_curricular__qtd_avaliacoes=0)
        # Consultando os registros de histórico (criados para alunos oriundos de tranferências ou migração)
        registros_historico = RegistroHistorico.objects.filter(
            matricula_periodo__aluno=self,
            situacao__in=[
                MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_REPROVADO,
                MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA,
            ],
        )

        # Média aritimética dos componentes
        if self.matriz and self.matriz.estrutura.ira == EstruturaCurso.IRA_ARITMETICA_NOTAS_FINAIS:
            for matricula_diario in matriculas_diario:
                # plano de retomada de aulas em virtude da pandemia (COVID19)
                if not matricula_diario.deve_ser_ignorada_no_calculo_do_ira():
                    numerador += matricula_diario.get_media_final_disciplina() or 0
            denominador += matriculas_diario.count()
            for matricula_diario_resumida in matriculas_diario_resumida:
                numerador += matricula_diario_resumida.media_final_disciplina or 0
            denominador += matriculas_diario_resumida.count()
            for certificacao_conhecimento in certificacoes_conhecimento:
                numerador += certificacao_conhecimento.nota or 0
            denominador += certificacoes_conhecimento.count()
            for aproveitamento_estudo in aproveitamentos_estudo:
                numerador += aproveitamento_estudo.nota or 0
            denominador += aproveitamentos_estudo.count()
            for registro_historico in registros_historico:
                numerador += registro_historico.media_final_disciplina or 0
            denominador += registros_historico.count()

        # Média ponderada em relação as notas e cargas horárias dos componentes
        else:
            for matricula_diario in matriculas_diario:
                # plano de retomada de aulas em virtude da pandemia (COVID19)
                if not matricula_diario.deve_ser_ignorada_no_calculo_do_ira():
                    if matricula_diario.diario.componente_curricular.componente.ch_hora_relogio:
                        ch_hora_relogio = matricula_diario.diario.componente_curricular.componente.get_ch_hora_relogio()
                        numerador += ch_hora_relogio * (matricula_diario.get_media_final_disciplina() or 0)
                        denominador += ch_hora_relogio
            for matricula_diario_resumida in matriculas_diario_resumida:
                if matricula_diario_resumida.equivalencia_componente.carga_horaria:
                    numerador += matricula_diario_resumida.equivalencia_componente.carga_horaria * (
                        matricula_diario_resumida.media_final_disciplina or 0
                    )
                    denominador += matricula_diario_resumida.equivalencia_componente.carga_horaria
            for certificacao_conhecimento in certificacoes_conhecimento:
                if certificacao_conhecimento.componente_curricular.componente.ch_hora_relogio:
                    ch_hora_relogio = certificacao_conhecimento.componente_curricular.componente.get_ch_hora_relogio()
                    numerador += ch_hora_relogio * (certificacao_conhecimento.nota or 0)
                    denominador += ch_hora_relogio
            for aproveitamento_estudo in aproveitamentos_estudo:
                if aproveitamento_estudo.componente_curricular.componente.ch_hora_relogio:
                    ch_hora_relogio = aproveitamento_estudo.componente_curricular.componente.get_ch_hora_relogio()
                    numerador += ch_hora_relogio * (aproveitamento_estudo.nota or 0)
                    denominador += ch_hora_relogio
            for registro_historico in registros_historico:
                if registro_historico.componente.ch_hora_relogio and registro_historico.media_final_disciplina:
                    ch_hora_relogio = registro_historico.componente.get_ch_hora_relogio()
                    numerador += ch_hora_relogio * (registro_historico.media_final_disciplina or 0)
                    denominador += ch_hora_relogio

        ira = 0
        if denominador:
            ira = Decimal(str(numerador)) / denominador

        if parcial or matriculaperiodo is not None:
            return ira
        else:
            self.ira = ira
            HistoricoSituacaoMatricula.objects.create(aluno=self, situacao=self.situacao, data=datetime.datetime.now())
            self.save()

    def get_ira(self):
        return mask_nota(self.ira)

    def atualizar_situacao_ultimo_periodo(self):
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        if ultima_matricula_periodo.situacao_id == SituacaoMatriculaPeriodo.EM_ABERTO and (
            ultima_matricula_periodo.matriculadiario_set.exists() or ultima_matricula_periodo.turma
        ):
            ultima_matricula_periodo.situacao_id = SituacaoMatriculaPeriodo.MATRICULADO
            ultima_matricula_periodo.save()

    def atualizar_situacao(self, descricao_operacao=None):
        if self.situacao_id in [SituacaoMatricula.MATRICULADO, SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL]:
            self.atualizar_pendencias()

            self.situacao_id = self.get_situacao_id()
            self.ultima_operacao = descricao_operacao
            self.save()

            self.calcular_indice_rendimento()
            self.atualizar_situacao_ultimo_periodo()
            self.atualizar_periodo_referencia()
            self.atualizar_data_conclusao()
            self.atualizar_percentual_ch_cumprida()
            self.calcular_ch_aulas_visita_tecnica()
            self.calcular_ch_aulas_pcc()

    def atualizar_data_conclusao(self):
        from estagios.models import PraticaProfissional

        if self.situacao.pk == SituacaoMatricula.CONCLUIDO or self.situacao.pk == SituacaoMatricula.FORMADO:
            # A data de conclusão é a maior data da última ativiade curricular do aluno

            dt_temp = None
            if self.dt_conclusao_curso:
                dt_temp = self.dt_conclusao_curso
            self.dt_conclusao_curso = None

            # Consultando a data de término do último período do aluno (CalendarioAcademico)
            ultima_matricula_periodo = self.get_ultima_matricula_periodo()
            qs_diarios = ultima_matricula_periodo.matriculadiario_set.exclude(situacao=MatriculaDiario.SITUACAO_CANCELADO)
            matricula_diario = qs_diarios.first()
            if (
                matricula_diario
                and matricula_diario.diario
                and matricula_diario.diario.calendario_academico
                and matricula_diario.diario.calendario_academico.data_fim
            ):
                self.dt_conclusao_curso = matricula_diario.diario.calendario_academico.data_fim
                # se o período-letivo ainda não foi concluído
                if self.dt_conclusao_curso > datetime.date.today():
                    ultimos_diarios = qs_diarios.values_list('diario', flat=True)
                    ultima_aula = (
                        Aula.objects.filter(professor_diario__diario__in=ultimos_diarios, data__lte=datetime.date.today()).order_by('-data').first()
                    )
                    # a data de conclusão é o último dia de aula
                    if ultima_aula:
                        self.dt_conclusao_curso = ultima_aula.data
                    # a data de conclusão é o dia atual
                    else:
                        self.dt_conclusao_curso = datetime.date.today()

            # RegistroConvocacaoENADE
            if self.curso_campus.exige_enade:
                registro_convocacao_enade = self.get_enade_concluinte()
                data_prova_enade = registro_convocacao_enade.get_data_prova() if registro_convocacao_enade else None
                if data_prova_enade:
                    if self.dt_conclusao_curso is None or data_prova_enade > self.dt_conclusao_curso:
                        if data_prova_enade <= datetime.date.today():
                            # alterar apenas caso o aluno tenha comparecido à prova
                            if registro_convocacao_enade.situacao == RegistroConvocacaoENADE.SITUACAO_PRESENTE:
                                self.dt_conclusao_curso = data_prova_enade

            # ProjetoFinal
            if self.matriz.exige_tcc:
                projeto_final = self.get_projeto_final_aprovado()
                if projeto_final and projeto_final.resultado_data:
                    if self.dt_conclusao_curso is None or projeto_final.resultado_data.date() > self.dt_conclusao_curso:
                        self.dt_conclusao_curso = projeto_final.resultado_data.date()

            # AtividadeComplementar
            if self.matriz.configuracao_atividade_academica:
                ultima_atividade_complementar_curricular = self.get_ultima_atividade_complementar_curricular()
                if ultima_atividade_complementar_curricular and ultima_atividade_complementar_curricular.data_atividade:
                    if self.dt_conclusao_curso is None or ultima_atividade_complementar_curricular.data_atividade > self.dt_conclusao_curso:
                        self.dt_conclusao_curso = ultima_atividade_complementar_curricular.data_atividade

            # ParticipacaoColacaoGrau
            if self.curso_campus.exige_colacao_grau:
                participacao_colacao_grau = self.get_participacao_colacao_grau()
                if participacao_colacao_grau and participacao_colacao_grau.colacao_grau.data_colacao:
                    # após 25/04/2019 a data de colação de grau passou a ser desconsiderada como data de conclusão do curso
                    if participacao_colacao_grau.colacao_grau.data_colacao < datetime.date(2019, 4, 25):
                        self.dt_conclusao_curso = participacao_colacao_grau.colacao_grau.data_colacao

            # Estagio
            for pratica_profissional in self.get_estagios_historico(apenas_aprovado=True, motivo_encerramento=PraticaProfissional.MOTIVO_CONCLUSAO):
                if pratica_profissional and pratica_profissional.data_fim:
                    if self.dt_conclusao_curso is None or pratica_profissional.data_fim > self.dt_conclusao_curso:
                        self.dt_conclusao_curso = pratica_profissional.data_fim

            if self.dt_conclusao_curso is None:
                if dt_temp:
                    self.dt_conclusao_curso = dt_temp
                else:
                    self.dt_conclusao_curso = datetime.date.today()

            self.ano_conclusao = self.get_ultima_matricula_periodo().ano_letivo.ano

        else:
            self.dt_conclusao_curso = None
            self.ano_conclusao = None
        self.save()

    def __str__(self):
        return f'{normalizar_nome_proprio(self.get_nome_social_composto())} ({self.matricula})'

    # get_vinculo() herdado de AbstractRelacionamento (prefetch-friendly)

    def get_user(self):
        return User.objects.filter(username=self.matricula).first()

    def eh_estrangeiro_com_passaporte(self) -> bool:
        return self.nacionalidade == 'Estrangeira' and bool(self.passaporte)

    def get_dados_sincronizacao_usuario(self) -> dict[str, bool]:
        eh_estrangeiro = self.eh_estrangeiro_com_passaporte()
        dados = {'eh_aluno': True, 'eh_estrangeiro': eh_estrangeiro}
        if eh_estrangeiro:
            dados.update(is_active=True, is_staff=True)
        return dados

    @transaction.atomic
    def save(self, *args: object, **kwargs: object) -> None:
        sync_user = kwargs.pop('sync_user', True)

        if self.eh_aluno_minicurso() and (self.matriz_id or getattr(self, 'matriz', None)):
            raise ValidationError('Alunos de curso FIC- (Minicurso) não podem ter matriz curricular informada.')

        if not self.ano_let_prev_conclusao:
            self.definir_ano_let_prev_conclusao()

        if self.data_inicio_ciclo is None:
            self.data_inicio_ciclo = self.calcular_data_inicio_ciclo()

        if self.data_prevista_termino_ciclo is None:
            self.data_prevista_termino_ciclo = self.calcular_data_prevista_termino_ciclo()

        eh_novo_registro = self.id is None
        super().save(*args, **kwargs)

        if sync_user:
            # User
            if eh_novo_registro and User.objects.filter(username=self.matricula).exists():
                raise ValidationError(
                    f'Não foi possível realizar a matrícula de {self.pessoa_fisica.nome}, pois o código de matrícula {self.matricula} encontra-se em uso por outro aluno. Repita o procedimento.'
                )
            eh_estrangeiro = self.eh_estrangeiro_com_passaporte()
            User.objects.get_or_create_user(self.matricula, self.pessoa_fisica.cpf or self.pessoa_fisica.passaporte)
            User.objects.filter(username=self.matricula).update(**self.get_dados_sincronizacao_usuario())
            if self.eh_aluno_minicurso() and not self.situacao.ativo and not eh_estrangeiro:
                User.objects.filter(username=self.matricula).update(is_active=False, is_staff=False)

            # Pessoa Física
            self.pessoa_fisica.nome = normalizar_nome_proprio(self.pessoa_fisica.nome)
            self.pessoa_fisica.eh_aluno = True
            # a PF pode ser de vários alunos e de outros papéis: um aluno só marca, nunca desmarca. O passaporte não é
            # copiado: a entrada (obter_ou_criar) já o grava, e a higiene da deduplicação o anula de propósito
            if eh_estrangeiro:
                self.pessoa_fisica.eh_estrangeiro = True
            self.pessoa_fisica.save()

            # Vínculo
            user = self.get_user()
            defaults = {
                'pessoa': self.pessoa_fisica.pessoa_ptr,
                'user': user,
                'ativo': self.situacao.ativo,
                'setor': self.curso_campus.diretoria.setor if self.curso_campus else None,
            }
            tipo_relacionamento = ContentType.objects.get_for_model(self)
            Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
            user.reset_vinculo()
            user.reset_profile()

            # LDAP
            sync_ldap_user(self.matricula)
            if eh_novo_registro:
                user.enviar_email_boas_vindas()

    def calcular_data_inicio_ciclo(self):
        """Calcula a data de início do ciclo acadêmico do aluno.

        A data é determinada com base no tipo de curso: alunos PROITEC usam a
        data da matrícula; alunos de minicurso usam a data de início da turma;
        demais alunos usam a data de início do calendário acadêmico da primeira
        turma ou diário associado.

        Returns:
            ``date`` com a data de início do ciclo ou ``None`` se não for possível
            determinar.
        """
        data_inicio_ciclo = None
        com_estrutura = bool(self.matriz and self.matriz.estrutura)
        eh_proitec = self.is_proitec()
        eh_minicurso = self.eh_aluno_minicurso_apto_sistec()

        if self.data_inicio_ciclo is None and (eh_minicurso or eh_proitec or com_estrutura):
            if eh_proitec:
                data_inicio_ciclo = self.data_matricula
            elif self.id and com_estrutura and not eh_proitec:
                turma = (
                    Turma.objects.filter(matriculaperiodo__aluno_id=self.pk)
                    .select_related('calendario_academico')
                    .only('calendario_academico__data_inicio')
                    .order_by('calendario_academico__data_inicio')
                    .first()
                )
                data_inicio_ciclo = turma and turma.calendario_academico.data_inicio
                if data_inicio_ciclo is None:
                    diario = (
                        Diario.objects.filter(matriculadiario__matricula_periodo__aluno_id=self.pk)
                        .select_related('calendario_academico')
                        .only('calendario_academico__data_inicio')
                        .order_by('calendario_academico__data_inicio')
                        .first()
                    )
                    data_inicio_ciclo = diario and diario.calendario_academico.data_inicio
            elif self.id and eh_minicurso:
                data_inicio_ciclo = (
                    ParticipanteTurmaMinicurso.objects.filter(aluno_id=self.id)
                    .order_by('turma__data_inicio')
                    .values_list('turma__data_inicio', flat=True)
                    .first()
                )
        return data_inicio_ciclo

    def calcular_data_prevista_termino_ciclo(self) -> datetime.date | None:
        """Calcula a data prevista de término do ciclo acadêmico do aluno.

        Para alunos de curso FIC- (Minicurso), retorna a data fim da turma de minicurso.
        Para as demais modalidades, soma à data de início do ciclo a quantidade
        de períodos letivos da matriz considerando a periodicidade do curso.

        Returns:
            ``date`` com a data prevista de término ou ``None`` se não for possível determinar.
        """
        if self.eh_aluno_minicurso_apto_sistec():
            if self.id:
                return (
                    ParticipanteTurmaMinicurso.objects.filter(aluno_id=self.id)
                    .order_by('-turma__data_fim')
                    .values_list('turma__data_fim', flat=True)
                    .first()
                )
            return None

        data_inicio = self.data_inicio_ciclo
        if data_inicio is None:
            data_inicio = self.calcular_data_inicio_ciclo()

        if not data_inicio or not self.matriz or not self.matriz.qtd_periodos_letivos:
            return None

        qtd_periodos = self.matriz.qtd_periodos_letivos
        if self.curso_campus and self.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            return data_inicio + relativedelta(years=qtd_periodos)
        return data_inicio + relativedelta(months=6 * qtd_periodos)

    def definir_ano_let_prev_conclusao(self):
        ano_prev_termino = self.ano_letivo.ano
        qtd_periodos_letivos = self.matriz and self.matriz.qtd_periodos_letivos or 0

        # verificando ano previsto de término de cursos semestrais
        if self.curso_campus and self.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
            count_periodo = int(self.periodo_letivo)
            primeiro = True

            for _ in range(1, qtd_periodos_letivos + 1):
                if count_periodo == 2:
                    count_periodo = 1
                else:
                    if not primeiro:
                        ano_prev_termino += 1
                    count_periodo += 1
                primeiro = False

        # verificando ano previsto de término de cursos anuais
        if self.curso_campus and self.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_ANUAL:
            ano_prev_termino = ano_prev_termino + qtd_periodos_letivos - 1

        self.ano_let_prev_conclusao = ano_prev_termino

    def delete(self, *args, **kwargs):
        self.foto = None
        self.revogar_acesso()
        user = tl.get_user()
        if not user or (self.pode_ser_excluido() and perms.realizar_procedimentos_academicos(user, self.curso_campus)):
            if self.get_user():
                sync_ldap_user(self.matricula)  # sincronizando com o AD para liberar o email acadêmico

                self.pessoa_fisica.save()
                user = User.objects.filter(username=self.matricula).first()
                if user:
                    try:
                        user.delete()
                    except ProtectedError:
                        raise Exception('Este aluno está vinculado a outros módulos e não pode ser excluído.')

            super().delete(*args, **kwargs)
        else:
            raise Exception('Aluno não pode ser excluído.')

    def get_nascimento_anonimo(self):
        return str(self.pessoa_fisica.nascimento_data.year)

    def get_natureza_participacao_id(self):
        natureza_participacao_id = NaturezaParticipacao.PRESENCIAL
        if self.matriz:
            natureza_participacao_id = self.matriz.natureza_participacao_id
        elif self.is_qacademico():
            from edu.q_academico import DAO

            natureza_participacao_id = NaturezaParticipacao.EAD if DAO().is_curso_EAD(self) else NaturezaParticipacao.PRESENCIAL
        return natureza_participacao_id

    def get_endereco(self):
        if self.logradouro:
            lista = []
            if self.logradouro:
                lista.append(self.logradouro)
            if self.numero:
                lista.append(self.numero)
            if self.bairro:
                lista.append(self.bairro)
            if self.cep:
                lista.append(self.cep)
            if self.cidade:
                lista.append(str(self.cidade))
            return ', '.join(lista)
        else:
            return None

    def get_endereco_anonimo(self):
        if self.logradouro:
            lista = []
            if self.bairro:
                lista.append(self.bairro)
            if self.cidade:
                lista.append(str(self.cidade))
            return ', '.join(lista)
        else:
            return None

    def get_rg(self):
        rg = '-'
        if self.numero_rg:
            rg = self.numero_rg
            if self.orgao_emissao_rg:
                rg += f' - {self.orgao_emissao_rg}'
            if self.uf_emissao_rg:
                rg += f'({self.uf_emissao_rg.get_sigla()})'
        return rg

    def get_absolute_url(self):
        return f'/edu/aluno/{self.matricula}/'

    def get_absolute_url_anonimo(self):
        return '/#'

    def pode_emitir_declaracao_matricula(self):
        return self.possui_historico() and self.is_matriculado() and self.pode_emitir_declaracao() and not self.is_ultima_matricula_em_aberto()

    def get_urls_documentos(self):
        """
        Documentos que podem ser emitidos pelo aluno
        """
        lista = []
        if self.pode_emitir_declaracao():
            lista.append(('Declaração de Vínculo', f'/edu/declaracaovinculo_pdf/{self.pk}/'))
        if self.possui_historico():
            if not self.is_concluido():
                lista.append(('Histórico Parcial', f'/edu/emitir_historico_parcial_pdf/{self.pk}/'))
            if self.is_matriculado() and self.pode_emitir_declaracao():
                lista.append(('Declaração de Carga Horária Integralizada', f'/edu/declaracao_ch_cumprida_pdf/{self.pk}/'))
                if not self.is_ultima_matricula_em_aberto():
                    lista.append(('Declaração de Horários de Aula', f'/edu/declaracao_horarios_aula_pdf/{self.pk}/'))
                    lista.append(('Declaração de Matrícula', f'/edu/declaracaomatricula_pdf/{self.pk}/'))
                    lista.append(('Comprovante de Dados Acadêmicos', f'/edu/comprovante_dados_academicos_pdf/{self.pk}'))
        urls_diploma_historico = self.get_url_historico_diploma()
        if urls_diploma_historico:
            url_historico, url_diploma = urls_diploma_historico
            if url_historico and not self.is_proitec():
                lista.append(('Histórico Final', url_historico))
            if url_diploma:
                lista.append(('Diploma', url_diploma))
        for certificado in self.certificadodiploma_set.all():
            lista.append(('Certificado de Conclusão', f'/edu/certificado_diploma_pdf/{certificado.pk}/'))
        return lista

    def get_ch_componentes_cumpridos(self, apenas_curriculares=False, ano=None, incluir_atividades=False):
        ids = apenas_curriculares and self.matriz.get_ids_componentes() or None
        result = (
            Componente.objects.filter(pk__in=self.get_ids_componentes_cumpridos(ids, ano=ano))
            .aggregate(Sum('ch_hora_relogio'))
            .get('ch_hora_relogio__sum')
            or 0
        )
        result = mask_ch_componente(result)
        if incluir_atividades:
            if self.matriz.ch_atividades_aprofundamento:
                result += min(self.get_ch_atividade_aprofundamento_cumprida(), self.matriz.ch_atividades_aprofundamento)
            if self.matriz.ch_atividades_complementares:
                result += min(self.get_ch_atividades_complementares_cumprida(ano=ano), self.matriz.ch_atividades_complementares)
        return result

    def get_ids_componentes_cursando(self):
        if hasattr(self, 'ids_componentes_cursando'):
            return self.ids_componentes_cursando
        self.ids_componentes_cursando = MatriculaDiario.objects.filter(
            matricula_periodo__aluno=self, situacao=MatriculaDiario.SITUACAO_CURSANDO
        ).values_list('diario__componente_curricular__componente_id', flat=True)
        return self.ids_componentes_cursando

    def get_ids_componentes_cumpridos(self, ids=None, ano=None, matricula_periodo=None):
        ids_componentes_curriculares_cumpridos = self._get_ids_componentes_cumpridos_cache(ano=ano, matricula_periodo=matricula_periodo)
        if ids is None:
            return ids_componentes_curriculares_cumpridos
        lista = []
        for i in ids:
            if i in ids_componentes_curriculares_cumpridos:
                lista.append(i)
        return lista

    def _get_ids_componentes_cumpridos_cache(self, ano=None, matricula_periodo=None):
        if not self.matriz_id:
            return []

        cache_key = '_ids_componentes_cumpridos_'
        periodo = None
        if matricula_periodo:
            periodo = matricula_periodo.periodo_letivo
            cache_key = f'{cache_key}{matricula_periodo.ano_letivo.ano}{periodo}'
        elif ano:
            cache_key = f'{cache_key}{ano}'
        if hasattr(self, cache_key):
            return getattr(self, cache_key)

        ids = self.matriz.get_ids_componentes()
        lista = Aluno._coletar_componentes_cumpridos([self], self.matriz, ids, ano, periodo).get(self.id, [])

        for pk, componente_associado_pk in ComponenteCurricular.objects.filter(
            matriz=self.matriz, componente_curricular_associado__isnull=False
        ).values_list('componente_id', 'componente_curricular_associado__componente_id'):
            if pk in lista:
                lista.append(componente_associado_pk)

        setattr(self, cache_key, lista)
        return lista

    @staticmethod
    def _coletar_componentes_cumpridos(alunos: list, matriz, ids_componentes: list, ano: int | None = None, periodo: int | None = None) -> dict:
        """Coleta os componentes cumpridos de vários alunos de uma mesma matriz.

        Returns:
            dict ``{aluno_id: [componente_id, ...]}`` (antes da expansão por componente associado).
        """

        nota_aprovacao_certificacao = matriz.estrutura.media_certificacao_conhecimento or 70
        situacoes = [
            MatriculaDiario.SITUACAO_APROVADO,
            MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
            MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
            MatriculaDiario.SITUACAO_DISPENSADO,
        ]

        md = MatriculaDiario.objects.filter(
            matricula_periodo__aluno__in=alunos,
            situacao=MatriculaDiario.SITUACAO_APROVADO,
            diario__componente_curricular__componente_id__in=ids_componentes,
        )
        mdr = MatriculaDiarioResumida.objects.filter(
            matricula_periodo__aluno__in=alunos, situacao__in=situacoes, equivalencia_componente__componente_id__in=ids_componentes
        )
        cc = CertificacaoConhecimento.objects.filter(
            matricula_periodo__aluno__in=alunos, nota__gte=nota_aprovacao_certificacao, componente_curricular__componente_id__in=ids_componentes
        )
        ae = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno__in=alunos, componente_curricular__componente_id__in=ids_componentes)
        ac = AproveitamentoComponente.objects.filter(matricula_periodo__aluno__in=alunos, componente_curricular__componente_id__in=ids_componentes)
        rh = RegistroHistorico.objects.filter(matricula_periodo__aluno__in=alunos, situacao__in=situacoes, componente_id__in=ids_componentes)

        if ano and periodo:
            md = md.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)
            mdr = mdr.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)
            cc = cc.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)
            ae = ae.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)
            ac = ac.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)
            rh = rh.filter(matricula_periodo__ano_letivo__ano=ano, matricula_periodo__periodo_letivo=periodo)

        elif ano:
            md = md.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            mdr = mdr.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            cc = cc.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            ae = ae.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            ac = ac.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            rh = rh.filter(matricula_periodo__ano_letivo__ano__lte=ano)

        fontes = [
            md.values_list('matricula_periodo__aluno_id', 'diario__componente_curricular__componente_id'),
            mdr.values_list('matricula_periodo__aluno_id', 'equivalencia_componente__componente_id'),
            cc.values_list('matricula_periodo__aluno_id', 'componente_curricular__componente_id'),
            ae.values_list('matricula_periodo__aluno_id', 'componente_curricular__componente_id'),
            ac.values_list('matricula_periodo__aluno_id', 'componente_curricular__componente_id'),
            rh.values_list('matricula_periodo__aluno_id', 'componente_id'),
        ]

        cumpridos: dict = defaultdict(list)
        for fonte in fontes:
            for aluno_id, componente_id in fonte:
                cumpridos[aluno_id].append(componente_id)
        return cumpridos

    @classmethod
    def calcular_componentes_cumpridos_em_lote(cls, alunos) -> None:
        """
        Pré-carrega o cache ``ids_componentes_curriculares_cumpridos`` para uma lista de alunos da mesma matriz.

        O cache não será calculado se houver alunos de matrizes diferentes
        """

        alunos = list(alunos)
        if not alunos:
            return

        if len({a.matriz_id for a in alunos}) > 1:
            return

        matriz = alunos[0].matriz
        ids = list(matriz.get_ids_componentes())
        cumpridos = cls._coletar_componentes_cumpridos(alunos, matriz, ids)

        associados = list(
            ComponenteCurricular.objects.filter(matriz_id=matriz.id, componente_curricular_associado__isnull=False).values_list(
                'componente_id', 'componente_curricular_associado__componente_id'
            )
        )
        cache_key = '_ids_componentes_cumpridos_'
        for aluno in alunos:
            lista = cumpridos.get(aluno.id, [])
            lista_set = set(lista)
            for pk, associado_pk in associados:
                if pk in lista_set:
                    lista.append(associado_pk)
            setattr(aluno, cache_key, lista)

    def get_ids_componentes_extra_curriculares_cumpridos(self, excluir_equivalencias=True, matricula_periodo=None, ano=None):
        """Retorna os IDs dos componentes extracurriculares já cumpridos pelo aluno.

        Consulta matrículas em diários, diários resumidos (Q-Acadêmico),
        certificações de conhecimento, aproveitamentos de estudo e registros de
        histórico, excluindo componentes que pertencem à matriz curricular.
        O resultado é cacheado no atributo ``ids_componentes_extra_curriculares_cumpridos``.

        Args:
            excluir_equivalencias: quando ``True``, remove registros com equivalência.
            matricula_periodo: filtra por período letivo específico.
            ano: filtra por ano letivo (≤).

        Returns:
            lista de inteiros com os IDs dos componentes extracurriculares cumpridos.
        """

        if hasattr(self, 'ids_componentes_extra_curriculares_cumpridos'):
            return self.ids_componentes_extra_curriculares_cumpridos
        if not self.matriz or self.is_proitec():
            return []

        ids_componentes_matriz = self.matriz.get_ids_componentes()

        md = MatriculaDiario.objects.filter(matricula_periodo__aluno=self, situacao=MatriculaDiario.SITUACAO_APROVADO).exclude(
            diario__componente_curricular__componente_id__in=ids_componentes_matriz
        )

        mdr = MatriculaDiarioResumida.objects.filter(
            matricula_periodo__aluno=self,
            situacao__in=[
                MatriculaDiario.SITUACAO_APROVADO,
                MatriculaDiario.SITUACAO_APROVEITAMENTO_ESTUDO,
                MatriculaDiario.SITUACAO_CERTIFICACAO_CONHECIMENTO,
            ],
        ).exclude(equivalencia_componente__componente_id__in=ids_componentes_matriz)
        cc = CertificacaoConhecimento.objects.filter(
            matricula_periodo__aluno=self, nota__gte=self.matriz.estrutura.media_certificacao_conhecimento or 70
        ).exclude(componente_curricular__componente_id__in=ids_componentes_matriz)
        ae = AproveitamentoEstudo.objects.filter(matricula_periodo__aluno=self).exclude(
            componente_curricular__componente_id__in=ids_componentes_matriz
        )
        ac = AproveitamentoComponente.objects.filter(matricula_periodo__aluno=self).exclude(
            componente_curricular__componente_id__in=ids_componentes_matriz
        )
        rh = RegistroHistorico.objects.filter(matricula_periodo__aluno=self).exclude(componente_id__in=ids_componentes_matriz)

        if excluir_equivalencias:
            md = md.exclude(equivalencias_set__isnull=False)
            mdr = mdr.exclude(equivalencias_set__isnull=False)
            rh = rh.exclude(equivalencias_set__isnull=False)

        if ano:
            md = md.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            mdr = mdr.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            cc = cc.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            ae = ae.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            ac = ac.filter(matricula_periodo__ano_letivo__ano__lte=ano)
            rh = rh.filter(matricula_periodo__ano_letivo__ano__lte=ano)

        if matricula_periodo:
            md = md.filter(matricula_periodo=matricula_periodo)
            mdr = mdr.filter(matricula_periodo=matricula_periodo)
            cc = cc.filter(matricula_periodo=matricula_periodo)
            ae = ae.filter(matricula_periodo=matricula_periodo)
            ac = ac.filter(matricula_periodo=matricula_periodo)
            rh = rh.filter(matricula_periodo=matricula_periodo)

        self.ids_componentes_extra_curriculares_cumpridos = (
            list(md.values_list('diario__componente_curricular__componente_id', flat=True))
            + list(mdr.values_list('equivalencia_componente__componente_id', flat=True))
            + list(cc.values_list('componente_curricular__componente_id', flat=True))
            + list(ae.values_list('componente_curricular__componente_id', flat=True))
            + list(ac.values_list('componente_curricular__componente_id', flat=True))
            + list(rh.values_list('componente_id', flat=True))
        )
        return self.ids_componentes_extra_curriculares_cumpridos

    # COMPONENTES

    def get_componentes_cumpridos(self):
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos())

    def get_componentes_cursando(self):
        return Componente.objects.filter(
            componentecurricular__diario__matriculadiario__matricula_periodo__aluno=self,
            componentecurricular__diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
        )

    def get_matriculas_diario_cursando(self):
        qs = MatriculaDiario.objects.filter(matricula_periodo__aluno=self, situacao=MatriculaDiario.SITUACAO_CURSANDO).select_related(
            'diario__componente_curricular__componente_curricular_associado'
        )
        if hasattr(self, 'ano_letivo_referencia'):
            qs = qs.filter(diario__ano_letivo=self.ano_letivo_referencia)
        if hasattr(self, 'periodo_letivo_referencia'):
            qs = qs.filter(diario__periodo_letivo=self.periodo_letivo_referencia)
        return qs

    def get_componentes_pendentes(self, periodos=None, apenas_obrigatorias=False, apenas_optativas=False):
        if periodos is None:
            periodos = []
        ids = self.matriz and self.matriz.get_ids_componentes(periodos, apenas_obrigatorias, apenas_optativas) or []
        return Componente.objects.filter(id__in=ids).exclude(id__in=self.get_ids_componentes_cumpridos(ids))

    def get_componentes_em_diarios_pendentes(self):
        ids = MatriculaDiario.objects.filter(matricula_periodo__aluno=self, situacao=MatriculaDiario.SITUACAO_PENDENTE).values_list(
            'diario__componente_curricular__componente', flat=True
        )
        return Componente.objects.filter(id__in=ids).exclude(id__in=self.get_ids_componentes_cumpridos(ids))

    def get_componentes_obrigatorios_pendentes(self, curriculares=False):
        componentes_pendentes = self.get_componentes_pendentes(apenas_obrigatorias=True)
        if curriculares:
            return (
                self.matriz.componentecurricular_set.filter(componente_id__in=componentes_pendentes.values_list('pk', flat=True))
                .order_by('tipo')
                .order_by('periodo_letivo')
            )
        else:
            return componentes_pendentes

    def get_componentes_em_dependencia(self):
        periodos = list(range(1, self.periodo_atual))
        ids = self.matriz.get_ids_componentes(periodos, True)
        return Componente.objects.filter(id__in=ids).exclude(id__in=self.get_ids_componentes_cumpridos(ids))

    def atingiu_qtd_max_disciplinas(self):
        numero_disciplinas_superior_periodo = self.matriz.estrutura.numero_disciplinas_superior_periodo
        if numero_disciplinas_superior_periodo:
            qtd_componentes_periodo_referencia = self.matriz.componentecurricular_set.filter(periodo_letivo=self.periodo_atual).count()
            if (
                qtd_componentes_periodo_referencia + numero_disciplinas_superior_periodo
                <= self.get_ultima_matricula_periodo().matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO).count()
            ):
                return True
        return False

    def atingiu_ch_max_disciplinas(self, ch_componente):
        ch_maxima_disciplinas = self.matriz.estrutura.ch_maxima_disciplinas
        result = False
        if ch_maxima_disciplinas:
            ch_cursando = (
                self.get_ultima_matricula_periodo()
                .matriculadiario_set.filter(situacao=MatriculaDiario.SITUACAO_CURSANDO)
                .aggregate(qtd=Sum('diario__componente_curricular__componente__ch_hora_relogio'))
                .get('qtd')
                or 0
            )
            result = (mask_ch_componente(ch_cursando) + ch_componente) > ch_maxima_disciplinas
        return result

    # COMPONENTES REGULARES OBRIGATÓRIOS

    def get_componentes_regulares_obrigatorios_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_regulares_obrigatorios()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_componentes_regulares_obrigatorios_pendentes(self):
        id_todos = self.matriz.get_ids_componentes_regulares_obrigatorios()
        id_cumpridos = self.get_ids_componentes_cumpridos(id_todos)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def possui_componente_regular_obrigatorio_pendente(self):
        id_todos = set(self.matriz.get_ids_componentes_regulares_obrigatorios())
        id_cumpridos = set(self.get_ids_componentes_cumpridos(id_todos))
        return not id_todos.issubset(id_cumpridos)

    def get_componentes_curriculares_regulares_obrigatorios_cumpridos(self):
        ids = self.matriz.get_ids_componentes_regulares_obrigatorios()
        return ComponenteCurricular.objects.filter(componente_id__in=self.get_ids_componentes_cumpridos(ids))

    def get_ch_componentes_regulares_obrigatorios_cumprida(self, matricula_periodo=None, ano=None):
        s = (
            self.get_componentes_regulares_obrigatorios_cumpridos(matricula_periodo, ano)
            .aggregate(Sum('ch_hora_relogio'))
            .get('ch_hora_relogio__sum')
            or 0
        )
        return mask_ch_componente(s)

    def get_ch_componentes_regulares_obrigatorios_esperada(self):
        return self.matriz.ch_componentes_obrigatorios

    def get_ch_componentes_regulares_obrigatorios_pendente(self, ano=None):
        ch = self.get_ch_componentes_regulares_obrigatorios_esperada()
        if ch:
            ch = ch - self.get_ch_componentes_regulares_obrigatorios_cumprida(ano=ano)
        return max(0, ch)

    # COMPONENTES REGULARES OPTATIVOS

    def get_componentes_regulares_optativos_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_regulares_optativos()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_componentes_regulares_optativos_nao_cumpridos(self):
        id_todos = self.matriz.get_ids_componentes_regulares_optativos()
        id_cumpridos = self.get_ids_componentes_cumpridos(id_todos)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_curriculares_optativos_cumpridos(self):
        ids = self.matriz.get_ids_componentes_regulares_optativos()
        return ComponenteCurricular.objects.filter(componente_id__in=self.get_ids_componentes_cumpridos(ids))

    def get_ch_componentes_regulares_optativos_cumprida(self, matricula_periodo=None, ano=None):
        ch_horaria_equivalente = 0
        if self.matriz.configuracao_creditos_especiais:
            matriculas_periodo = [matricula_periodo] if matricula_periodo else self.matriculaperiodo_set.all()
            qs_ce = CreditoEspecial.objects.filter(
                matricula_periodo__in=matriculas_periodo,
                item_configuracao_creditos_especiais__configuracao=self.matriz.configuracao_creditos_especiais,
            )
            if ano:
                qs_ce = qs_ce.filter(matricula_periodo__ano_letivo__ano__lte=ano)

            ch_horaria_equivalente = (
                qs_ce.aggregate(Sum('item_configuracao_creditos_especiais__equivalencia_creditos')).get(
                    'item_configuracao_creditos_especiais__equivalencia_creditos__sum'
                )
                or 0
            )

            if ch_horaria_equivalente > self.matriz.configuracao_creditos_especiais.quantidade_maxima_creditos_especiais:
                ch_horaria_equivalente = self.matriz.configuracao_creditos_especiais.quantidade_maxima_creditos_especiais

            ch_horaria_equivalente = (
                ch_horaria_equivalente * 15
                if self.curso_campus.modalidade_id in [Modalidade.MESTRADO, Modalidade.DOUTORADO]
                else ch_horaria_equivalente * 20
            )
        result = (
            self.get_componentes_regulares_optativos_cumpridos(matricula_periodo, ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum')
            or 0
        )
        return mask_ch_componente(result) + ch_horaria_equivalente

    def get_ch_componentes_regulares_optativos_esperada(self):
        return self.matriz.ch_componentes_optativos

    def get_ch_componentes_regulares_optativos_pendente(self, ano=None):
        ch = self.get_ch_componentes_regulares_optativos_esperada()
        if ch:
            ch = ch - self.get_ch_componentes_regulares_optativos_cumprida(ano=ano)
        return max(0, ch)

    def get_ch_componentes_regulares_optativos_cursando(self):
        result = (
            ComponenteCurricular.objects.filter(
                diario__matriculadiario__matricula_periodo__aluno=self,
                diario__matriculadiario__situacao=MatriculaDiario.SITUACAO_CURSANDO,
                optativo=True,
                tipo=ComponenteCurricular.TIPO_REGULAR,
            )
            .aggregate(Sum('componente__ch_hora_relogio'))
            .get('componente__ch_hora_relogio__sum')
            or 0
        )
        return mask_ch_componente(result)

    def completou_ch_componentes_regulares_optativos(self):
        return self.get_ch_componentes_regulares_optativos_pendente() == 0

    # COMPONENTES ELETIVOS

    def get_componentes_eletivos_cumpridos(self, matricula_periodo=None, ano=None):
        return Componente.objects.filter(id__in=self.get_ids_componentes_extra_curriculares_cumpridos(matricula_periodo=matricula_periodo, ano=ano))

    def get_ch_componentes_eletivos_cumprida(self, matricula_periodo=None, ano=None):
        result = (
            self.get_componentes_eletivos_cumpridos(matricula_periodo=matricula_periodo, ano=ano)
            .aggregate(Sum('ch_hora_relogio'))
            .get('ch_hora_relogio__sum')
            or 0
        )
        return mask_ch_componente(result)

    def get_ch_componentes_eletivos_esperada(self):
        return self.matriz.ch_componentes_eletivos

    def get_ch_componentes_eletivos_pendente(self, ano=None):
        ch = self.get_ch_componentes_eletivos_esperada()
        if ch:
            ch = ch - self.get_ch_componentes_eletivos_cumprida(ano=ano)
        return max(0, ch)

    def cursou_componentes_eletivos(self):
        return self.get_ch_componentes_eletivos_pendente() == 0

    def completou_ch_componentes_eletivos(self):
        return self.get_ch_componentes_eletivos_pendente() == 0

    # COMPONENTES DE PRÁTICA COMO COMPONENTE

    def get_diarios_aulas_pcc(self):
        ids = (
            self.matriculaperiodo_set.filter(
                matriculadiario__diario__componente_curricular__ch_pcc__gt=0, matriculadiario__situacao=MatriculaDiario.SITUACAO_APROVADO
            )
            .exclude(matriculadiario__diario__componente_curricular__tipo=ComponenteCurricular.TIPO_PRATICA_COMO_COMPONENTE)
            .values_list('matriculadiario__diario_id', flat=True)
        )
        return Diario.objects.filter(id__in=ids)

    def calcular_ch_aulas_pcc(self):
        if self.matriz and self.matriz.ch_pratica_como_componente:
            self.ch_aulas_pcc = 0
            for diario in self.get_diarios_aulas_pcc():
                self.ch_aulas_pcc += diario.get_carga_horaria_pcc_contabilizada(relogio=True)
            self.save()

    def get_ch_componentes_pratica_como_componente_cumprida(self, matricula_periodo=None, ano=None):
        result = (
            self.get_componentes_pratica_como_componente_cumpridos(matricula_periodo, ano)
            .aggregate(Sum('ch_hora_relogio'))
            .get('ch_hora_relogio__sum')
            or 0
        )
        return self.ch_aulas_pcc + mask_ch_componente(result)

    def get_componentes_pratica_como_componente_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_pratica_como_componente()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_ch_pratica_como_componente_esperada(self):
        return self.matriz.ch_pratica_como_componente

    def get_componentes_pratica_como_componente_nao_cumpridos(self, apenas_obrigatorio=False, ano=None):
        id_todos = self.matriz.get_ids_componentes_pratica_como_componente(apenas_obrigatorio)
        id_cumpridos = self.get_ids_componentes_cumpridos(ids=id_todos, ano=ano)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_pratica_como_componente_pendentes(self, ano=None):
        return self.get_componentes_pratica_como_componente_nao_cumpridos(apenas_obrigatorio=True, ano=ano)

    def get_ch_componentes_pratica_como_componente_pendente(self, ano=None):
        ch_obrigatoria_pendente = (
            self.get_componentes_pratica_como_componente_pendentes(ano=ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        )
        ch_obrigatoria_pendente = mask_ch_componente(ch_obrigatoria_pendente)
        ch_cumprida = self.get_ch_componentes_pratica_como_componente_cumprida(ano=ano)
        # se o aluno cumpriu os componentes obrigatórios, a ch pendente é a diferença da esperada e cumprida
        # senão, deve-se acrescentar a ch obrigatória pendente dessa diferença
        ch = self.get_ch_pratica_como_componente_esperada() - ch_cumprida
        ch = ch > ch_obrigatoria_pendente and ch or ch_obrigatoria_pendente
        return ch > 0 and ch or 0

    # COMPONENTES DE VISITA TÉCNICA / AULA DE CAMPO

    def get_diarios_aulas_visita_tecnica(self):
        ids = self.matriculaperiodo_set.filter(
            matriculadiario__diario__componente_curricular__ch_visita_tecnica__gt=0, matriculadiario__situacao=MatriculaDiario.SITUACAO_APROVADO
        ).values_list('matriculadiario__diario_id', flat=True)
        return Diario.objects.filter(id__in=ids)

    def calcular_ch_aulas_visita_tecnica(self):
        if self.matriz and self.matriz.ch_visita_tecnica:
            self.ch_aulas_visita_tecnica = 0
            for diario in self.get_diarios_aulas_visita_tecnica():
                self.ch_aulas_visita_tecnica += diario.get_carga_horaria_visita_tecnica_contabilizada(relogio=True)
            self.save()

    def get_ch_componentes_visita_tecnica_cumprida(self, matricula_periodo=None, ano=None):
        result = (
            self.get_componentes_visita_tecnica_cumpridos(matricula_periodo, ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        )
        return self.ch_aulas_visita_tecnica + mask_ch_componente(result)

    def get_componentes_visita_tecnica_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_visita_tecnica()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_ch_visita_tecnica_esperada(self):
        return self.matriz.ch_visita_tecnica

    def get_componentes_visita_tecnica_nao_cumpridos(self, apenas_obrigatorio=False, ano=None):
        id_todos = self.matriz.get_ids_componentes_visita_tecnica(apenas_obrigatorio)
        id_cumpridos = self.get_ids_componentes_cumpridos(ids=id_todos, ano=ano)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_visita_tecnica_pendentes(self, ano=None):
        return self.get_componentes_visita_tecnica_nao_cumpridos(apenas_obrigatorio=True, ano=ano)

    def get_ch_componentes_visita_tecnica_pendente(self, ano=None):
        ch_obrigatoria_pendente = (
            self.get_componentes_visita_tecnica_pendentes(ano=ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        )
        ch_obrigatoria_pendente = mask_ch_componente(ch_obrigatoria_pendente)
        ch_cumprida = self.get_ch_componentes_visita_tecnica_cumprida(ano=ano)
        # se o aluno cumpriu os componentes obrigatórios, a ch pendente é a diferença da esperada e cumprida
        # senão, deve-se acrescentar a ch obrigatória pendente dessa diferença
        ch = self.get_ch_visita_tecnica_esperada() - ch_cumprida
        ch = ch > ch_obrigatoria_pendente and ch or ch_obrigatoria_pendente
        return ch > 0 and ch or 0

    # COMPONENTES DE SEMINÁRIO

    def get_componentes_seminario_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_seminario()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_componentes_seminario_nao_cumpridos(self, apenas_obrigatorio=False, ano=None):
        id_todos = self.matriz.get_ids_componentes_seminario(apenas_obrigatorio)
        id_cumpridos = self.get_ids_componentes_cumpridos(ids=id_todos, ano=ano)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_seminario_pendentes(self, ano=None):
        return self.get_componentes_seminario_nao_cumpridos(apenas_obrigatorio=True, ano=ano)

    def get_componentes_curriculares_seminario_cumpridos(self):
        ids = self.matriz.get_ids_componentes_seminario()
        return ComponenteCurricular.objects.filter(componente_id__in=self.get_ids_componentes_cumpridos(ids))

    def get_ch_componentes_seminario_cumprida(self, matricula_periodo=None, ano=None):
        s = self.get_componentes_seminario_cumpridos(matricula_periodo, ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        return mask_ch_componente(s)

    def get_ch_componentes_seminario_esperada(self):
        return self.matriz.ch_seminarios

    def get_ch_componentes_seminario_pendente(self, ano=None):
        ch_obrigatoria_pendente = self.get_componentes_seminario_pendentes(ano=ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        ch_obrigatoria_pendente = mask_ch_componente(ch_obrigatoria_pendente)
        ch_cumprida = self.get_ch_componentes_seminario_cumprida(ano=ano)
        # se o aluno cumpriu os componentes obrigatórios, a ch pendente é a diferença da esperada e cumprida
        # senão, deve-se acrescentar a ch obrigatória pendente dessa diferença
        ch = self.get_ch_componentes_seminario_esperada() - ch_cumprida
        ch = ch > ch_obrigatoria_pendente and ch or ch_obrigatoria_pendente
        return ch > 0 and ch or 0

    def completou_ch_componentes_seminario(self):
        return self.get_ch_componentes_seminario_pendente() == 0

    # COMPONENTES DE PRÁTICA PROFISSIONAL

    def get_componentes_pratica_profissional_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_pratica_profissional()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_componentes_pratica_profissional_nao_cumpridos(self, apenas_obrigatorio=False, ano=None):
        id_todos = self.matriz.get_ids_componentes_pratica_profissional(apenas_obrigatorio)
        id_cumpridos = self.get_ids_componentes_cumpridos(ids=id_todos, ano=ano)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_pratica_profissional_pendentes(self, ano=None):
        return self.get_componentes_pratica_profissional_nao_cumpridos(apenas_obrigatorio=True, ano=ano)

    def get_componentes_curriculares_pratica_profissional_cumpridos(self):
        ids = self.matriz.get_ids_componentes_pratica_profissional()
        return ComponenteCurricular.objects.filter(componente_id__in=self.get_ids_componentes_cumpridos(ids))

    def get_ch_componentes_pratica_profissional_cumprida(self, matricula_periodo=None, incluir_atpa=False, ano=None):
        s = (
            self.get_componentes_pratica_profissional_cumpridos(matricula_periodo, ano=ano)
            .aggregate(Sum('ch_hora_relogio'))
            .get('ch_hora_relogio__sum')
            or 0
        )
        s = mask_ch_componente(s)
        if incluir_atpa:
            s += self.get_ch_atividade_aprofundamento_cumprida(matricula_periodo, ano)
        return s

    def get_ch_componentes_pratica_profissional_esperada(self, incluir_atpa=False):
        ch = self.matriz and self.matriz.ch_pratica_profissional or 0
        if incluir_atpa:
            ch += self.get_ch_atividade_aprofundamento_esperada()
        return ch

    def get_ch_atividade_aprofundamento_esperada(self):
        return self.matriz and self.matriz.ch_atividades_aprofundamento or 0

    def get_ch_extensao_componentes_esperada(self):
        return self.matriz and self.matriz.ch_componentes_extensao or 0

    def get_ch_extensao_outras_atividades_esperada(self):
        result = 0
        if self.matriz and self.matriz.ch_atividades_extensao:
            result = self.matriz.ch_atividades_extensao - self.matriz.ch_componentes_com_extensao - self.matriz.ch_componentes_extensao
        return result

    def get_ch_extensao_outros_componentes_esperada(self):
        return self.matriz and self.matriz.ch_componentes_com_extensao or 0

    def get_ch_atividade_aprofundamento_cumprida(self, matricula_periodo=None, ano=None):
        qs = self.atividadeaprofundamento_set.filter(deferida=True)
        if matricula_periodo:
            qs = qs.filter(ano_letivo=matricula_periodo.ano_letivo, periodo_letivo=matricula_periodo.periodo_letivo)
        if ano:
            qs = qs.filter(ano_letivo__ano__lte=ano)
        return qs.aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

    ## ATIVIDADES DE EXTENSÃO ##

    def get_atividades_extensao(self):
        return (
            AtividadeCurricularExtensao.objects.filter(matricula_periodo__aluno_id=self.id)
            .select_related('substituida', 'matricula_periodo')
            .order_by('matricula_periodo_id')
        )

    def get_ids_atividades_extensao_componentes_por_tipo(self, qs, tipo):
        ids_referencia = qs.filter(tipo_referencia__model=tipo).values_list('id_referencia', flat=True)

        if tipo == 'matriculadiario':
            ids_validos = (
                MatriculaDiario.objects.filter(id__in=ids_referencia)
                .filter(
                    Q(diario__componente_curricular__tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO)
                    | Q(diario__componente_curricular__componente_curricular_associado__tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO)
                )
                .values_list('id', flat=True)
            )
            return qs.filter(tipo_referencia__model=tipo, id_referencia__in=ids_validos).values_list('id', flat=True)

        if tipo == 'registrohistorico':
            return qs.filter(
                tipo_referencia__model='registrohistorico',
                id_referencia__in=RegistroHistorico.objects.filter(
                    id__in=ids_referencia,
                    componente_id__in=self.matriz.componentecurricular_set.filter(tipo=ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO).values_list(
                        'componente_id', flat=True
                    ),
                ).values_list('id', flat=True),
            ).values_list('id', flat=True)

        filtros = {
            'aproveitamentocomponente': {
                'model': AproveitamentoComponente,
                'filter': {'componente_curricular__tipo': ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO},
            },
            'aproveitamentoestudo': {
                'model': AproveitamentoEstudo,
                'filter': {'componente_curricular__tipo': ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO},
            },
            'certificacaoconhecimento': {
                'model': CertificacaoConhecimento,
                'filter': {'componente_curricular__tipo': ComponenteCurricular.TIPO_ATIVIDADE_EXTENSAO},
            },
        }

        config = filtros.get(tipo)
        if not config:
            return []

        ids_validos = config['model'].objects.filter(id__in=ids_referencia, **config['filter']).values_list('id', flat=True)
        return qs.filter(tipo_referencia__model=tipo, id_referencia__in=ids_validos).values_list('id', flat=True)

    def get_ids_atividades_extensao_outros_componentes_por_tipo(self, qs, tipo):
        ids_referencia = qs.filter(tipo_referencia__model=tipo).values_list('id_referencia', flat=True)

        filtros = {
            'aproveitamentocomponente': (AproveitamentoComponente, 'componente_curricular'),
            'aproveitamentoestudo': (AproveitamentoEstudo, 'componente_curricular'),
            'certificacaoconhecimento': (CertificacaoConhecimento, 'componente_curricular'),
            'matriculadiario': (MatriculaDiario, 'diario__componente_curricular'),
        }

        if tipo == 'registrohistorico':
            subquery_componentes = self.matriz.componentecurricular_set.com_extensao().values_list('componente_id', flat=True)

            return qs.filter(
                tipo_referencia__model='registrohistorico',
                id_referencia__in=RegistroHistorico.objects.filter(id__in=ids_referencia, componente_id__in=subquery_componentes).values_list(
                    'id', flat=True
                ),
            ).values_list('id', flat=True)

        config = filtros.get(tipo)
        if not config:
            return qs.none().values_list('id', flat=True)

        model, campo = config

        ids_validos = model.objects.filter(
            ComponenteCurricular.get_filtro_com_extensao(campo),
            id__in=ids_referencia,
        ).values_list('id', flat=True)

        return qs.filter(tipo_referencia__model=tipo, id_referencia__in=ids_validos).values_list('id', flat=True)

    def get_atividades_extensao_matriculadiarioresumida(self):
        return MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno=self, ch_extensao_cumprida__gt=0)

    def get_atividades_extensao_aprovadas(self):
        return self.get_atividades_extensao().filter(aprovada=True, substituida__isnull=True)

    def get_ch_atividade_extensao_cumprida(self):
        if self.matriz_id is None:
            return 0
        total = 0

        qs = (
            self.get_atividades_extensao_aprovadas()
            .select_related('aacc', 'atpa', 'vinculacaoatividadeextensao')
            .only('carga_horaria', 'aacc__carga_horaria', 'atpa__carga_horaria', 'vinculacaoatividadeextensao__carga_horaria')
        )

        total = qs.filter(requer_distribuicao_ch=False).aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

        qs = qs.filter(requer_distribuicao_ch=True)
        if qs.exists():
            for ch in qs.filter(aacc__deferida=True).values_list('aacc__carga_horaria', flat=True):
                total += ch or 0
            for ch in qs.filter(atpa__deferida=True).values_list('atpa__carga_horaria', flat=True):
                total += ch or 0
            for ch in qs.filter(vinculacaoatividadeextensao__homologada=True).values_list('vinculacaoatividadeextensao__carga_horaria', flat=True):
                total += ch or 0

        total += (
            MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno_id=self.id)
            .aggregate(Sum('ch_extensao_cumprida'))
            .get('ch_extensao_cumprida__sum')
            or 0
        )

        return mask_ch_componente(total)

    def get_atividades_extensao_componentes(self, matricula_periodo=None, ano=None):
        qs = self.get_atividades_extensao_aprovadas()
        if matricula_periodo:
            qs = qs.filter(matricula_periodo=matricula_periodo)
        if ano:
            qs = qs.filter(matricula_periodo__ano_letivo__ano__lte=ano)

        tipos = [
            'matriculadiario',
            'aproveitamentocomponente',
            'aproveitamentoestudo',
            'certificacaoconhecimento',
            'registrohistorico',
        ]
        ids = set()
        for tipo in tipos:
            ids.update(self.get_ids_atividades_extensao_componentes_por_tipo(qs, tipo))
        return qs.filter(id__in=ids)

    def get_ch_extensao_componentes_cumprida(self, matricula_periodo=None, ano=None):
        if self.matriz_id is None:
            return 0

        qs = self.get_atividades_extensao_componentes(matricula_periodo, ano)
        total = qs.aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

        return mask_ch_componente(total)

    def get_ch_extensao_outras_atividades_cumprida(self, matricula_periodo=None, ano=None):
        if self.matriz_id is None:
            return 0
        total = 0
        qs = self.get_atividades_extensao_outras_atividades(matricula_periodo, ano)
        if self.matriz and self.matriz.requer_vinculacao_extensao_diarios:
            for ch in qs.filter(aacc__deferida=True).values_list('aacc__carga_horaria', flat=True):
                total += ch or 0
            for ch in qs.filter(atpa__deferida=True).values_list('atpa__carga_horaria', flat=True):
                total += ch or 0
        else:
            total = qs.aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0
            total = mask_ch_componente(total)

        return total

    def get_atividades_extensao_outras_atividades(self, matricula_periodo=None, ano=None):
        qs = self.get_atividades_extensao_aprovadas()
        if matricula_periodo:
            qs = qs.filter(matricula_periodo_id=matricula_periodo.id)
        if ano:
            qs = qs.filter(matricula_periodo__ano_letivo__ano__lte=ano)
        if self.matriz and self.matriz.requer_vinculacao_extensao_diarios:
            qs = qs.filter(Q(aacc__deferida=True) | Q(atpa__deferida=True))
        else:
            qs = qs.exclude(
                tipo_referencia__model__in=[
                    'aproveitamentocomponente',
                    'aproveitamentoestudo',
                    'certificacaoconhecimento',
                    'matriculadiario',
                    'registrohistorico',
                ]
            )
        return qs

    def get_ch_extensao_outros_componentes_cumprida(self, matricula_periodo=None, ano=None):
        if self.matriz_id is None:
            return 0

        total = 0
        qs = self.get_atividades_extensao_outros_componentes(matricula_periodo, ano)
        if self.matriz and self.matriz.requer_vinculacao_extensao_diarios:
            total += (
                qs.filter(requer_distribuicao_ch=True, vinculacaoatividadeextensao__homologada=True)
                .aggregate(Sum('vinculacaoatividadeextensao__carga_horaria'))
                .get('vinculacaoatividadeextensao__carga_horaria__sum')
                or 0
            )

        total += qs.filter(requer_distribuicao_ch=False).aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

        total += (
            MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno=self)
            .aggregate(Sum('ch_extensao_cumprida'))
            .get('ch_extensao_cumprida__sum')
            or 0
        )

        return mask_ch_componente(total)

    def get_atividades_extensao_outros_componentes(self, matricula_periodo=None, ano=None):
        qs = self.get_atividades_extensao_aprovadas()
        ids = set()

        if matricula_periodo:
            qs = qs.filter(matricula_periodo_id=matricula_periodo.id)
        if ano:
            qs = qs.filter(matricula_periodo__ano_letivo__ano__lte=ano)

        # atividades com distribuição de ch em diários com ch_extensao
        ids.update(qs.filter(requer_distribuicao_ch=True, vinculacaoatividadeextensao__homologada=True).values_list('id', flat=True))

        # demais atividades de componentes curriculares com ch_extensao
        tipos = [
            'matriculadiario',
            'aproveitamentocomponente',
            'aproveitamentoestudo',
            'certificacaoconhecimento',
            'registrohistorico',
        ]
        for tipo in tipos:
            ids.update(self.get_ids_atividades_extensao_outros_componentes_por_tipo(qs.filter(requer_distribuicao_ch=False), tipo))

        return qs.filter(id__in=ids)

    def get_percentual_ch_atividade_extensao_cumprida(self):
        result = 100
        if self.matriz.ch_atividades_extensao:
            result = int(self.get_ch_atividade_extensao_cumprida() * 100 / self.matriz.ch_atividades_extensao)
        return min(result, 100)

    def get_ch_atividade_aprofundamento_pendente(self, ano=None):
        ch_esperada = self.get_ch_atividade_aprofundamento_esperada()
        if ch_esperada:
            ch_cumprida = self.get_ch_atividade_aprofundamento_cumprida(ano=ano)
            if ch_cumprida < ch_esperada:
                return ch_esperada - ch_cumprida
        return 0

    def get_ch_extensao_componentes_pendente(self, ano=None):
        ch_esperada = self.get_ch_extensao_componentes_esperada()
        if ch_esperada:
            ch_cumprida = self.get_ch_extensao_componentes_cumprida(ano=ano)
            if ch_cumprida < ch_esperada:
                return ch_esperada - ch_cumprida
        return 0

    def get_ch_extensao_outras_atividades_pendente(self, ano=None):
        ch_esperada = self.get_ch_extensao_outras_atividades_esperada()
        if ch_esperada:
            ch_cumprida = self.get_ch_extensao_outras_atividades_cumprida(ano=ano)
            if ch_cumprida < ch_esperada:
                return ch_esperada - ch_cumprida
        return 0

    def get_ch_extensao_outros_componentes_pendente(self, ano=None):
        ch_esperada = self.get_ch_extensao_outros_componentes_esperada()
        if ch_esperada:
            ch_cumprida = self.get_ch_extensao_outros_componentes_cumprida(ano=ano)
            if ch_cumprida < ch_esperada:
                return ch_esperada - ch_cumprida
        return 0

    def get_ch_componentes_pratica_profissional_pendente(self, ano=None):
        ch_obrigatoria_pendente = (
            self.get_componentes_pratica_profissional_pendentes(ano=ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        )
        ch_obrigatoria_pendente = mask_ch_componente(ch_obrigatoria_pendente)
        ch_cumprida = self.get_ch_componentes_pratica_profissional_cumprida(ano=ano)
        # se o aluno cumpriu os componentes obrigatórios, a ch pendente é a diferença da esperada e cumprida
        # senão, deve-se acrescentar a ch obrigatória pendente dessa diferença
        ch = self.get_ch_componentes_pratica_profissional_esperada() - ch_cumprida
        ch = ch > ch_obrigatoria_pendente and ch or ch_obrigatoria_pendente
        return ch > 0 and ch or 0

    def completou_ch_componentes_pratica_profissional(self):
        return self.get_ch_componentes_pratica_profissional_pendente() == 0

    # COMPONENTES DE TCC

    def get_componentes_tcc_cumpridos(self, matricula_periodo=None, ano=None):
        ids = self.matriz.get_ids_componentes_tcc()
        if not ids:
            return Componente.objects.none()
        return Componente.objects.filter(id__in=self.get_ids_componentes_cumpridos(ids, ano=ano, matricula_periodo=matricula_periodo))

    def get_componentes_tcc_nao_cumpridos(self, apenas_obrigatorio=False, ano=None):
        id_todos = self.matriz.get_ids_componentes_tcc(apenas_obrigatorio)
        id_cumpridos = self.get_ids_componentes_cumpridos(ids=id_todos, ano=ano)
        id_pendentes = []
        for id_componente in id_todos:
            if id_componente not in id_cumpridos:
                id_pendentes.append(id_componente)
        return Componente.objects.filter(id__in=id_pendentes)

    def get_componentes_tcc_pendentes(self, ano=None):
        return self.get_componentes_tcc_nao_cumpridos(apenas_obrigatorio=True, ano=ano)

    def get_componentes_curriculares_tcc_cumpridos(self):
        ids = self.matriz.get_ids_componentes_tcc()
        return ComponenteCurricular.objects.filter(componente_id__in=self.get_ids_componentes_cumpridos(ids))

    def get_ch_componentes_tcc_cumprida(self, matricula_periodo=None, ano=None):
        s = self.get_componentes_tcc_cumpridos(matricula_periodo, ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        return mask_ch_componente(s)

    def get_ch_componentes_tcc_esperada(self):
        return self.matriz and self.matriz.ch_componentes_tcc or 0

    def get_ch_componentes_tcc_pendente(self, ano=None):
        ch_obrigatoria_pendente = self.get_componentes_tcc_pendentes(ano=ano).aggregate(Sum('ch_hora_relogio')).get('ch_hora_relogio__sum') or 0
        ch_obrigatoria_pendente = mask_ch_componente(ch_obrigatoria_pendente)
        ch_cumprida = self.get_ch_componentes_tcc_cumprida(ano=ano)
        # se o aluno cumpriu os componentes obrigatórios, a ch pendente é a diferença da esperada e cumprida
        # senão, deve-se acrescentar a ch obrigatória pendente dessa diferença
        ch = self.get_ch_componentes_tcc_esperada() - ch_cumprida
        ch = ch > ch_obrigatoria_pendente and ch or ch_obrigatoria_pendente
        return ch > 0 and ch or 0

    def completou_ch_componentes_tcc(self):
        return self.get_ch_componentes_tcc_pendente() == 0

    # ATIVIDADES COMPLEMENTARES

    def get_atividades_complementares(self, apenas_curriculares=False):
        qs = self.atividadecomplementar_set.all()
        if apenas_curriculares:
            if self.matriz.configuracao_atividade_academica:
                itens_configuracoes = self.matriz.configuracao_atividade_academica.itemconfiguracaoatividadecomplementar_set.all()
                tipos_curriculares = TipoAtividadeComplementar.objects.filter(id__in=itens_configuracoes.values_list('tipo__id', flat=True))
                qs = qs.filter(tipo__in=tipos_curriculares)
        return qs.order_by('ano_letivo', 'periodo_letivo')

    def get_ch_atividades_complementares_por_tipo(self, incluir_todos=False, tipo=None, apenas_obrigatorias=False, ano=None, matricula_periodo=None):
        tipos_curriculares_cumpridos = []

        if self.matriz and self.matriz.configuracao_atividade_academica:
            if incluir_todos:
                itens_configuracoes = self.matriz.configuracao_atividade_academica.itemconfiguracaoatividadecomplementar_set.all()
            else:
                if tipo:
                    itens_configuracoes = self.matriz.configuracao_atividade_academica.itemconfiguracaoatividadecomplementar_set.filter(pk=tipo.pk)
                else:
                    ids_tipos = set(self.atividadecomplementar_set.values_list('tipo__id', flat=True))
                    itens_configuracoes = self.matriz.configuracao_atividade_academica.itemconfiguracaoatividadecomplementar_set
                    itens_configuracoes = itens_configuracoes.filter(tipo__id__in=ids_tipos) | itens_configuracoes.filter(ch_min_curso__gt=0)

            if apenas_obrigatorias:
                itens_configuracoes = itens_configuracoes.filter(ch_min_curso__gt=0)

            tipos_curriculares = TipoAtividadeComplementar.objects.filter(id__in=itens_configuracoes.values_list('tipo__id', flat=True))
            atividades_complementares = self.atividadecomplementar_set.filter(tipo__in=tipos_curriculares)
            periodos = []
            for ano_referencia, periodo_letivo in self.atividadecomplementar_set.values_list('ano_letivo__ano', 'periodo_letivo').distinct():
                if (
                    not matricula_periodo
                    or ano_referencia < matricula_periodo.ano_letivo.ano
                    or (ano_referencia == matricula_periodo.ano_letivo.ano and periodo_letivo <= matricula_periodo.periodo_letivo)
                ):
                    periodos.append((ano_referencia, periodo_letivo))

            # plano de retomada de aulas em virtude da pandemia (COVID19)
            ignorar_limite_nos_periodos_letivos = [
                (ano, periodo)
                for ano, periodo in Diario.objects.filter(matriculadiario__matricula_periodo__aluno=self, turma__pertence_ao_plano_retomada=True)
                .order_by('turma__ano_letivo__ano', 'turma__periodo_letivo')
                .values_list('turma__ano_letivo__ano', 'turma__periodo_letivo')
                .distinct()
            ]

            for item in itens_configuracoes:
                item.tipo.ch_considerada = 0
                item.tipo.ch_contabilizada = 0
                item.tipo.ch_total_cumprida = 0
                item.tipo.ch_min_curso = item.ch_min_curso
                item.tipo.ch_max_periodo = item.ch_max_periodo
                item.tipo.ch_max_curso = item.ch_max_curso
                item.tipo.percentual_considerar = item.percentual_considerar
                for ano_referencia, periodo_letivo in periodos:
                    qs_atividades = atividades_complementares.filter(ano_letivo__ano=ano_referencia, periodo_letivo=periodo_letivo, tipo=item.tipo)
                    item.ch_periodo_cumprida = 0
                    if ano:
                        qs_atividades = qs_atividades.filter(ano_letivo__ano__lte=ano)
                    for atividade_complementar in qs_atividades:
                        ch = atividade_complementar.carga_horaria
                        item.tipo.ch_total_cumprida += ch
                        if atividade_complementar.deferida:
                            item.ch_periodo_cumprida += ch
                        ignorar_limite_no_periodo = (ano_referencia, periodo_letivo) in ignorar_limite_nos_periodos_letivos
                        if item.ch_max_periodo and item.ch_periodo_cumprida > item.ch_max_periodo and not ignorar_limite_no_periodo:
                            item.ch_periodo_cumprida = item.ch_max_periodo
                    item.tipo.ch_considerada += item.ch_periodo_cumprida
                item.tipo.ch_contabilizada = item.tipo.ch_considerada
                item.tipo.ch_considerada = int(item.tipo.ch_considerada * item.percentual_considerar / 100)
                if item.ch_max_curso and item.tipo.ch_considerada >= item.ch_max_curso and not ignorar_limite_nos_periodos_letivos:
                    item.tipo.ch_considerada = item.ch_max_curso
                item.tipo.ch_por_evento = item.ch_por_evento
                tipos_curriculares_cumpridos.append(item.tipo)

        return tipos_curriculares_cumpridos

    def get_ch_atividades_complementares_esperada(self):
        return self.matriz.ch_atividades_complementares if self.matriz else 0

    def get_ch_atividades_extensao_esperada(self):
        if self.matriz:
            return self.matriz.ch_atividades_extensao
        else:
            return 0

    def get_ch_atividades_complementares_cumprida(self, tipo=None, ano=None, matricula_periodo=None):
        total = 0
        for atividade in self.get_ch_atividades_complementares_por_tipo(tipo=tipo, ano=ano, matricula_periodo=matricula_periodo):
            total += atividade.ch_considerada

        if matricula_periodo:
            tmp_total = total
            if hasattr(self, 'ch_atividades_complementares_cumprida_anterior'):
                total = total - self.ch_atividades_complementares_cumprida_anterior
            self.ch_atividades_complementares_cumprida_anterior = tmp_total

        return total

    def get_ch_atividades_complementares_cadastrada(self):
        return self.atividadecomplementar_set.all().aggregate(Sum('carga_horaria')).get('carga_horaria__sum') or 0

    def get_ch_atividades_complementares_pendente(self, tipo=None, ano=None):
        ch = max(0, self.get_ch_atividades_complementares_esperada() - self.get_ch_atividades_complementares_cumprida(ano=ano))

        if self.matriz and self.matriz.configuracao_atividade_academica:
            itens = self.matriz.configuracao_atividade_academica.itemconfiguracaoatividadecomplementar_set.filter(ch_min_curso__gt=0)
            if itens.exists():
                ch_temp = sum(max(0, tipo.ch_min_curso - self.get_ch_atividades_complementares_cumprida(tipo=tipo, ano=ano)) for tipo in itens)
                ch = max(ch, ch_temp)
        return ch

    def completou_ch_atividades_complementares(self):
        return self.get_ch_atividades_complementares_pendente() == 0

    # CRÉDITOS ESPECIAIS

    def get_creditos_especiais(self):
        return (
            CreditoEspecial.objects.filter(matricula_periodo__aluno_id=self.id)
            .select_related('matricula_periodo', 'matricula_periodo__ano_letivo', 'item_configuracao_creditos_especiais')
            .order_by('matricula_periodo__ano_letivo__ano', 'matricula_periodo__periodo_letivo')
        )

    # CARGA HORARIA TOTAL

    def get_carga_horaria_total_cumprida(self):
        carga_horaria = self.get_ch_componentes_regulares_obrigatorios_cumprida()
        carga_horaria += self.get_ch_componentes_regulares_optativos_cumprida()
        if self.matriz.ch_componentes_eletivos:
            carga_horaria += self.get_ch_componentes_eletivos_cumprida()
        carga_horaria += self.get_ch_componentes_seminario_cumprida()
        carga_horaria += self.get_ch_extensao_componentes_cumprida()
        carga_horaria += self.get_ch_componentes_tcc_cumprida()
        carga_horaria += self.get_ch_componentes_pratica_como_componente_cumprida()
        carga_horaria += self.get_ch_componentes_visita_tecnica_cumprida()
        if not (self.matriz and self.matriz.requer_vinculacao_extensao_diarios):
            carga_horaria += self.get_ch_extensao_outras_atividades_cumprida()

        if self.matriz.get_matrizppc():
            carga_horaria += self.get_ch_atividade_pratica_profissional_contabilizada()
        else:
            carga_horaria += self.get_ch_atividades_complementares_cumprida()
            carga_horaria += self.get_ch_componentes_pratica_profissional_cumprida(incluir_atpa=True)

        return carga_horaria

    def get_carga_horaria_aula_total_cumprida(self, ch=None):
        ch = self.get_carga_horaria_total_cumprida()
        cc = self.matriz.get_componentes_curriculares(apenas_obrigatorio=True).first()
        if cc:
            fator_conversao_hora_aula = cc.componente.get_fator_conversao_hora_aula()
            return round(ch * fator_conversao_hora_aula)
        return None

    def tem_acesso_servicos_microsoft(self):
        from microsoft.models import ConfiguracaoAcessoDreamspark

        return ConfiguracaoAcessoDreamspark.is_liberado(self)

    def get_matriculas_periodo(self, ate_ano_letivo=None, ate_periodo_letivo=None, orderbyDesc=True, excluir_em_aberto=False):
        qs = self.matriculaperiodo_set
        if excluir_em_aberto:
            qs = qs.exclude(situacao_id=SituacaoMatriculaPeriodo.EM_ABERTO)
        if ate_ano_letivo and ate_periodo_letivo:
            if self.curso_campus.periodicidade == CursoCampus.PERIODICIDADE_SEMESTRAL:
                qs = (
                    qs.filter(ano_letivo__ano__lte=ate_ano_letivo.ano)
                    .exclude(ano_letivo__ano=ate_ano_letivo.ano, periodo_letivo=ate_periodo_letivo)
                    .exclude(ano_letivo__ano=ate_ano_letivo.ano, periodo_letivo=2)
                )
            else:
                qs = qs.filter(ano_letivo__ano__lt=ate_ano_letivo.ano)

        if orderbyDesc:
            return qs.order_by('-ano_letivo__ano', '-periodo_letivo')
        else:
            return qs.order_by('ano_letivo__ano', 'periodo_letivo')

    def get_diarios_especiais(self, ate_ano_letivo=None, ate_periodo_letivo=None, orderbyDesc=True):
        qs = self.diarioespecial_set.all()
        if ate_ano_letivo and ate_periodo_letivo:
            qs = qs.filter(ano_letivo__ano__lte=ate_ano_letivo.ano)
            if ate_periodo_letivo == 1:
                qs = qs.exclude(ano_letivo__ano=ate_ano_letivo.ano, periodo_letivo=2)
        if orderbyDesc:
            return qs.order_by('-ano_letivo__ano', '-periodo_letivo')
        else:
            return qs.order_by('ano_letivo__ano', 'periodo_letivo')

    def get_matricula_periodo(self, ano_letivo, periodo_letivo):
        if ano_letivo is None:
            return None
        return self.get_matriculas_periodo().filter(ano_letivo_id=ano_letivo.id, periodo_letivo=periodo_letivo).first()

    def get_periodo_referencia(self):
        if hasattr(self, 'ano_letivo_referencia') and hasattr(self, 'periodo_letivo_referencia'):
            qs = self.matriculaperiodo_set.filter(ano_letivo=self.ano_letivo_referencia, periodo_letivo=self.periodo_letivo_referencia)
            mp = qs[0] if qs.exists() else None
        else:
            mp = self.get_ultima_matricula_periodo()
        return mp

    def get_situacao_periodo_referencia(self):
        mp = self.get_periodo_referencia()
        return mp and mp.situacao or None

    def get_data_ultimo_procedimento_periodo_referencia(self):
        ultimo = self.get_periodo_referencia().procedimentomatricula_set.first()
        return ultimo and ultimo.data or None

    def get_frequencia_periodo_referencia(self):
        mp = self.get_periodo_referencia()
        if mp:
            if mp.matriculadiario_set.exists():
                return mp.get_percentual_carga_horaria_frequentada()
            return 0
        return None

    def get_ultima_matricula_periodo(self, excluir_em_aberto=False):
        return self.get_matriculas_periodo(excluir_em_aberto=excluir_em_aberto).first()

    def get_turma_periodo_anterior(self):
        qs = self.get_matriculas_periodo()
        if qs.exists() and len(qs) > 1:
            matricula_periodo = qs[1]
            return matricula_periodo.turma_id and matricula_periodo.turma or None
        return None

    def get_historico_matricula_periodo_referencia(self):
        try:
            from gestao.models import PeriodoReferencia

            registro = self.historicosituacaomatricula_set.filter(data__lte=PeriodoReferencia.get_data_limite()).order_by('-data')[0]
            return (registro.situacao, registro.data)
        except Exception:
            return None

    def get_inscricao_programa_alimentacao(self):
        from django.core.exceptions import MultipleObjectsReturned

        try:
            if 'ae' in settings.INSTALLED_APPS:
                Programa = apps.get_model('ae', 'Programa')
                return self.inscricao_set.get(programa__tipo_programa__sigla=Programa.TIPO_ALIMENTACAO)
            return None
        except MultipleObjectsReturned:
            return self.inscricao_set.filter(programa__tipo_programa__sigla=Programa.TIPO_ALIMENTACAO).order_by('-data_cadastro')[0]
        except Exception:
            return None

    def get_inscricao_programa_idioma(self):
        from django.core.exceptions import MultipleObjectsReturned

        try:
            if 'ae' in settings.INSTALLED_APPS:
                Programa = apps.get_model('ae', 'Programa')
                return self.inscricao_set.get(programa__tipo_programa__sigla=Programa.TIPO_IDIOMA)
            return None
        except MultipleObjectsReturned:
            return self.inscricao_set.filter(programa__tipo_programa__sigla=Programa.TIPO_IDIOMA).order_by('-data_cadastro')[0]
        except Exception:
            return None

    def get_inscricao_programa_passe(self):
        from django.core.exceptions import MultipleObjectsReturned

        try:
            if 'ae' in settings.INSTALLED_APPS:
                Programa = apps.get_model('ae', 'Programa')
                return self.inscricao_set.get(programa__tipo_programa__sigla=Programa.TIPO_TRANSPORTE)
            return None
        except MultipleObjectsReturned:
            return self.inscricao_set.filter(programa__tipo_programa__sigla=Programa.TIPO_TRANSPORTE).order_by('-data_cadastro')[0]
        except Exception:
            return None

    def get_inscricao_programa_trabalho(self):
        from django.core.exceptions import MultipleObjectsReturned

        try:
            if 'ae' in settings.INSTALLED_APPS:
                Programa = apps.get_model('ae', 'Programa')
                return self.inscricao_set.get(programa__tipo_programa__sigla=Programa.TIPO_TRABALHO)
            return None
        except MultipleObjectsReturned:
            return self.inscricao_set.filter(programa__tipo_programa__sigla=Programa.TIPO_TRABALHO).order_by('-data_cadastro')[0]
        except Exception:
            return None

    def get_inscricoes_ativas(self):
        return self.inscricao_set.filter(ativa=True)

    @staticmethod
    def random(size=20, allowed_chars='abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789'):
        """Returns a randomic string."""
        return ''.join([choice(allowed_chars) for _ in range(size)])

    @staticmethod
    def codificar(s):
        left = Aluno.random(7, '0123456789')
        right = Aluno.random(13, '0123456789')
        s = str(s).encode('utf-8').hex()
        return f'{left}{s}{right}'

    @staticmethod
    def decodificar(s):
        s = s[7:]
        s = s[:-13]
        s = bytes.fromhex(str(s)).decode('utf-8')
        return s

    def get_matricula_codificada(self):
        return Aluno.codificar(self.matricula)

    def get_registros_emissao_diploma(self, tipo=None):
        qs = self.registroemissaodiploma_set.filter(cancelado=False)
        if tipo:
            qs = qs.filter(tipo=tipo)
        return qs.order_by('numero_registro', 'livro', 'folha')

    def get_tipo_diploma(self):
        registro_emissao_diploma = self.registroemissaodiploma_set.filter(cancelado=False).order_by('-id').first()
        return registro_emissao_diploma.get_tipo_diploma() if registro_emissao_diploma else None

    def get_dados_emissao_diploma(self):
        registro_emissao_diploma = self.registroemissaodiploma_set.filter(cancelado=False).order_by('-id').first()
        return registro_emissao_diploma.get_descricao_completa() if registro_emissao_diploma else None

    def get_dados_processo_seletivo(self):
        if self.candidato_vaga:
            return f'{self.candidato_vaga.classificacao}º Lugar | {self.candidato_vaga.oferta_vaga.lista} | {self.candidato_vaga.candidato.edital}'
        return None

    def get_foto_75x100_url(self):
        return self.foto and self.foto.url_75x100 or '/static/comum/img/default.jpg'

    def get_foto_75x100_url_publica(self):
        retorno = self.foto and self.foto.get_url_publica('75x100') or '/static/comum/img/default.jpg'
        return f'{settings.SITE_URL}{retorno}'

    def get_foto_150x200_url(self):
        return self.foto and self.foto.url_150x200 or '/static/comum/img/default.jpg'

    def get_foto_150x200_url_publica(self):
        retorno = self.foto and self.foto.get_url_publica('150x200') or '/static/comum/img/default.jpg'
        return f'{settings.SITE_URL}{retorno}'

    def get_foto_path(self):
        if self.foto and default_storage.exists(self.foto.name):
            tmp = tempfile.NamedTemporaryFile(delete=False)
            with self.foto.open('rb') as f:
                tmp.write(f.read())
            tmp.close()
            return tmp.name
        return self.get_foto_path_anonimo()

    def get_foto_path_anonimo(self):
        return f'{settings.BASE_DIR}/static/comum/img/default.jpg'

    def get_matriculas_periodo_com_diario(self):
        return self.matriculaperiodo_set.all().exclude(matriculadiario=None)

    def integralizou_suap(self):
        return self.matriz and self.matriculaperiodo_set.all().filter(matriculadiarioresumida__isnull=False)

    def iniciou_suap(self):
        return self.matriz and self.matriculaperiodo_set.all().filter(matriculadiarioresumida__isnull=True)

    def is_concluido(self, ignorar_integralizacao_fase_escolar=False):
        return (
            self.situacao_id == SituacaoMatricula.CONCLUIDO
            or self.situacao_id == SituacaoMatricula.FORMADO
            or self.situacao_id == SituacaoMatricula.EGRESSO
            or (self.situacao_id == SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO and not ignorar_integralizacao_fase_escolar)
        )

    def is_integralizado_fase_escolar(self):
        return self.situacao_id == SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO

    def is_integralizado_cursando(self):
        return self.situacao_id == SituacaoMatricula.MATRICULADO and self.integralizou_ensino_medio

    def pode_integralizar_fase_escolar(self):
        result = (
            self.curso_campus.modalidade_id in (Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA)
            and not self.is_integralizado_fase_escolar()
        )
        if result and self.matriz_id:
            result = not self.possui_componente_regular_obrigatorio_pendente()
        return result

    def pode_editar_obs_integralizacao_ensino_medio(self, user):
        if not self.integralizou_ensino_medio:
            return False
        return user.has_perm('comum.is_administrador_academico') and not self.registroemissaodiploma_set.filter(cancelado=False).exists()

    def is_cancelado(self):
        return self.situacao.pk in (
            SituacaoMatricula.CANCELADO,
            SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
            SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
            SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
            SituacaoMatricula.EVASAO,
            SituacaoMatricula.TRANSFERIDO_EXTERNO,
            SituacaoMatricula.JUBILADO,
        )

    def is_ultima_matricula_em_aberto(self):
        return self.get_ultima_matricula_periodo().situacao_id == SituacaoMatriculaPeriodo.EM_ABERTO

    def get_pedidos_matricula(self):
        return PedidoMatricula.objects.filter(matricula_periodo__aluno=self).order_by('id')

    def get_ultimo_registro_emissao_diploma(self):
        qs = self.registroemissaodiploma_set.filter(cancelado=False).order_by('-id')
        if qs:
            return qs[0]
        return None

    def get_dados_siabi(self):
        dados = {}

        diretoria = ''
        polo = ''
        uo = ''

        curso = {'id': self.curso_campus.id, 'descricao': self.curso_campus.descricao, 'modalidade': self.curso_campus.modalidade.descricao}

        if self.curso_campus.diretoria:
            diretoria = {'id': self.curso_campus.diretoria.id, 'descricao': self.curso_campus.diretoria.setor.sigla}

        if self.curso_campus.diretoria:
            uo = {'id': self.curso_campus.diretoria.setor.uo.id, 'descricao': self.curso_campus.diretoria.setor.uo.nome}

        if self.polo:
            polo = {'id': self.polo.id, 'descricao': self.polo.descricao}

        dados.update(
            aluno={
                'id': self.id,
                'matricula': self.matricula,
                'nome': self.pessoa_fisica.nome,
                'logradouro': self.logradouro or '',
                'numero': self.numero or '',
                'complemento': self.complemento or '',
                'cep': self.cep or '',
                'bairro': self.bairro or '',
                'cidade': self.cidade_id and str(self.cidade) or '',
                'telefone_principal': self.telefone_principal or '',
                'telefone_secundario': self.telefone_principal or '',
                'email_academico': self.email_academico or '',
                'email_pessoal': self.email_pessoal or '',
                'curso': curso,
                'diretoria': diretoria,
                'polo': polo,
                'campus': uo,
                'foto': self.foto and self.foto.url or '',
                'sexo': self.pessoa_fisica.sexo,
                'rg': self.numero_rg,
                'data_nascimento': self.pessoa_fisica.nascimento_data and self.pessoa_fisica.nascimento_data.strftime('%d/%m/%Y'),
                'situacao': self.situacao.descricao,
                'lattes': self.pessoa_fisica.lattes,
            }
        )
        return dados

    def get_via_diploma(self):
        return RegistroEmissaoDiploma.objects.filter(aluno=self).filter(cancelado=False).count()

    def get_ofertas_pratica_profissional(self):
        if self.matriz and self.periodo_atual and self.periodo_atual >= (self.matriz.periodo_minimo_estagio_obrigatorio or 0):
            qs = self.curso_campus.ofertapraticaprofissional_set.filter(data_fim__gte=datetime.date.today())
            qs = qs.exclude(a_partir_do_periodo__gt=self.periodo_atual)
            if self.turno_id:
                outros_turnos = Turno.objects.exclude(id=self.turno_id)
                qs = qs.exclude(turno__in=outros_turnos)
            return qs.distinct()
        return self.curso_campus.ofertapraticaprofissional_set.all()[0:0]

    def matriculou_em_pratica_profissional(self):
        return MatriculaDiario.objects.filter(
            matricula_periodo__aluno=self, diario__componente_curricular__tipo=ComponenteCurricular.TIPO_PRATICA_PROFISSIONAL
        ).exists()

    def tem_apoio_social(self):
        if 'ae' in settings.INSTALLED_APPS:
            Participacao = apps.get_model('ae', 'Participacao')
            atendimentos = self.demandaalunoatendida_set.filter(quantidade__gt=0)
            participacoes = Participacao.objects.filter(inscricao__aluno=self)
            mensagem = []
            if participacoes.exists():
                texto_participacao = []
                for participacao in participacoes.all():
                    texto_participacao.append(participacao.programa.tipo_programa.titulo)
                texto_participacao = '; '.join(list(set(texto_participacao)))
                mensagem.append(f'Participa(ou) de programa de assistência estudantil ({texto_participacao})')
            if atendimentos.exists():
                texto_demanda = []
                for demanda in atendimentos.all():
                    texto_demanda.append(demanda.demanda.nome)
                texto_demanda = '; '.join(list(set(texto_demanda)))
                mensagem.append(f'Possui atendimento pelo setor do Serviço Social ({texto_demanda})')
            return mensagem or False
        return False

    def tem_cota(self):
        if not self.forma_ingresso:
            return False
        if 'Renda' in self.forma_ingresso.descricao or 'Seleção Diferenciada' in self.forma_ingresso.descricao:
            return self.forma_ingresso.descricao
        return False

    def tem_atividade_extracurricular(self):
        from estagios.models import PraticaProfissional
        from pesquisa.models import Participacao as ParticipacaoPesquisa
        from projetos.models import Participacao as ParticipacaoExtensao

        mensagem = []
        pesquisa_qs = ParticipacaoPesquisa.objects.filter(
            vinculo_pessoa__id_relacionamento=self.id, vinculo_pessoa__tipo_relacionamento__model='aluno'
        )
        for participacao in pesquisa_qs:
            mensagem.append('{} de projeto de pesquisa'.format(participacao.bolsa_concedida and 'Recebe(u) bolsa' or 'Participa(ou)'))

        extensao_qs = ParticipacaoExtensao.objects.filter(
            vinculo_pessoa__id_relacionamento=self.id, vinculo_pessoa__tipo_relacionamento__model='aluno'
        )
        for participacao in extensao_qs:
            mensagem.append('{} de projeto de extensão'.format(participacao.bolsa_concedida and 'Recebe(u) bolsa' or 'Participa(ou)'))
        if PraticaProfissional.objects.filter(aluno=self, obrigatorio=False).exists():
            mensagem.append(
                f'Participa(ou) de {PraticaProfissional.objects.filter(aluno=self, obrigatorio=False).count()} práticas profissionais não obrigatórias'
            )
        return mensagem or False

    def get_avaliacoes(self, proximas=True):
        itens = (
            ItemConfiguracaoAvaliacao.objects.filter(configuracao_avaliacao__diario__matriculadiario__matricula_periodo__aluno=self)
            .order_by('data')
            .distinct()
        )
        if proximas:
            itens = itens.filter(data__gte=datetime.datetime.now(), data__lte=datetime.datetime.now() + datetime.timedelta(weeks=1))
        return itens

    def get_participacoes_em_minicursos(self):
        return Aluno.objects.filter(pessoa_fisica__cpf=self.pessoa_fisica.cpf, participanteturmaminicurso__isnull=False)

    def get_participacoes_em_eventos(self):
        return ParticipanteEvento.objects.filter(participante__pessoa__pessoafisica__cpf=self.pessoa_fisica.cpf)

    def get_estagios_docentes(self):
        return EstagioDocente.objects.filter(matricula_diario__matricula_periodo__aluno_id=self.id)

    def get_atividade_profissional_efetiva_pendente_relatorio(self):
        from estagios.models import AtividadeProfissionalEfetiva

        return self.atividadeprofissionalefetiva_set.filter(situacao=AtividadeProfissionalEfetiva.EM_ANDAMENTO, relatorio_final_aluno='')

    def get_atividade_profissional_efetiva_reunioes_de_orientacao(self):
        from estagios.models import AtividadeProfissionalEfetiva, OrientacaoAtividadeProfissionalEfetiva

        return OrientacaoAtividadeProfissionalEfetiva.objects.filter(
            data__gte=datetime.date.today(),
            atividade_profissional_efetiva__aluno=self,
            atividade_profissional_efetiva__situacao=AtividadeProfissionalEfetiva.EM_ANDAMENTO,
        )

    def get_estagios_com_avaliacao_pendente(self):
        from estagios.models import PraticaProfissional

        return self.praticaprofissional_set.filter(status=PraticaProfissional.STATUS_AGUARDANDO_AVALIACAO_ESTAGIARIO)

    def get_estagio_com_rel_atividades_pendente(self):
        from estagios.models import PraticaProfissional

        return self.praticaprofissional_set.exclude(
            status__in=[PraticaProfissional.STATUS_APTO_PARA_CONCLUSAO, PraticaProfissional.STATUS_CONCLUIDO, PraticaProfissional.STATUS_RESCINDIDO]
        ).filter(pendente_relatorio_estagiario=True)

    def get_aprendizagem_com_rel_atividades_pendente(self):
        if self.aprendizagem_set.exists():
            aprendizagem = self.aprendizagem_set.all().order_by('-id')[0]
            if aprendizagem.ha_pendencia_relatorio_aprendiz:
                return aprendizagem
            else:
                return None

    def get_estagios_historico(self, apenas_aprovado=False, motivo_encerramento=None):
        from estagios.models import PraticaProfissional

        qs = self.praticaprofissional_set.filter(data_fim__isnull=False)
        if motivo_encerramento:
            qs = qs.filter(movito_encerramento=motivo_encerramento)
        if apenas_aprovado:
            qs = qs.filter(situacao=PraticaProfissional.SITUACAO_APROVADO)
        return qs

    def get_matriculas_anteriores(self):
        if self.nacionalidade:
            if 'Brasileira' in self.nacionalidade or (self.estrangeiro_sem_passaporte or self.pessoa_fisica.cpf):
                return Aluno.objects.filter(pessoa_fisica__cpf=self.pessoa_fisica.cpf).exclude(pk=self.pk)[0:10]
            elif 'Estrangeira' in self.nacionalidade:
                # pelo par passaporte+país da pessoa: o mesmo número de outro país é outra pessoa
                from rh.deduplicacao.entrada import filtro_mesma_pessoa_por_passaporte

                return Aluno.objects.filter(filtro_mesma_pessoa_por_passaporte(self.pessoa_fisica, 'pessoa_fisica__')).exclude(pk=self.pk)[0:10]
        return Aluno.objects.none()

    def get_periodos_contabilizados_para_jubilar(self):
        # plano de retomada de aulas em virtude da pandemia (COVID19)
        ignorar_ids = (
            self.matriculaperiodo_set.filter(matriculadiario__diario__turma__pertence_ao_plano_retomada=True)
            .order_by('id')
            .values_list('id', flat=True)
            .distinct()
        )
        matriculas_periodo = self.matriculaperiodo_set.filter(ano_letivo__ano__gte=self.ano_letivo.ano).exclude(id__in=ignorar_ids)
        if self.periodo_letivo == 2:
            matriculas_periodo = matriculas_periodo.exclude(ano_letivo__ano=self.ano_letivo.ano, periodo_letivo=1)
        return matriculas_periodo.filter(situacao__pk__in=SituacaoMatriculaPeriodo.SITUACOES_CONTABILIZADAS_PARA_JUBILAMENTO)

    def deve_ser_jubilado(self):
        if self.matriz is None:
            return False

        if self.matriz.estrutura.fator_acrescimo_periodo_letivo and self.matriz.estrutura.tipo_avaliacao in [
            EstruturaCurso.TIPO_AVALIACAO_SERIADO,
            EstruturaCurso.TIPO_AVALIACAO_MODULAR,
        ]:
            qtd_periodos_remanescentes_pra_conclusao = self.matriz.qtd_periodos_letivos - self.periodo_atual + 1
            qtd_periodos_futuros_possiveis = (
                math.floor(self.matriz.qtd_periodos_letivos * self.matriz.estrutura.fator_acrescimo_periodo_letivo)
                - self.get_periodos_contabilizados_para_jubilar().count()
            )
            if qtd_periodos_remanescentes_pra_conclusao > qtd_periodos_futuros_possiveis and self.possui_pendencia(incluir_colacao_grau=False):
                return 'Impossibilidade de conclusão do curso em tempo hábil'

        if (
            self.matriz.estrutura.qtd_periodos_conclusao
            and self.get_periodos_contabilizados_para_jubilar().count() >= self.matriz.estrutura.qtd_periodos_conclusao
            and self.situacao.pk == SituacaoMatricula.MATRICULADO
            and self.possui_pendencia(incluir_colacao_grau=False)
        ):
            return 'Quantidade máxima de matrículas em período para conclusão.'
        if (
            self.matriz.estrutura.tipo_avaliacao in [EstruturaCurso.TIPO_AVALIACAO_SERIADO, EstruturaCurso.TIPO_AVALIACAO_MODULAR]
            and self.matriz.estrutura.qtd_max_reprovacoes_periodo
        ):
            if (
                self.matriculaperiodo_set.filter(
                    periodo_matriz=self.periodo_atual,
                    situacao__id__in=[SituacaoMatriculaPeriodo.REPROVADO, SituacaoMatriculaPeriodo.REPROVADO_POR_FALTA],
                ).count()
                >= self.matriz.estrutura.qtd_max_reprovacoes_periodo
            ):
                return 'Quantidade máxima de reprovações no mesmo período letivo.'
        if self.matriz.estrutura.qtd_max_reprovacoes_disciplina:
            matriculas_diario_resumidas = MatriculaDiarioResumida.objects.filter(matricula_periodo__aluno=self)
            matriculas_diario_resumidas = matriculas_diario_resumidas.filter(matricula_periodo__ano_letivo__ano__gte=self.ano_letivo.ano)
            if self.periodo_letivo == 2:
                matriculas_diario_resumidas = matriculas_diario_resumidas.exclude(
                    matricula_periodo__ano_letivo__ano=self.ano_letivo.ano, matricula_periodo__periodo_letivo=1
                )
            matriculas_diario_resumidas = matriculas_diario_resumidas.filter(
                situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA]
            )
            componentes_com_reprovacao = matriculas_diario_resumidas.values_list('equivalencia_componente__componente_id', flat=True)
            matriculas_diario = MatriculaDiario.objects.filter(
                matricula_periodo__aluno=self, situacao__in=[MatriculaDiario.SITUACAO_REPROVADO, MatriculaDiario.SITUACAO_REPROVADO_POR_FALTA]
            )
            componentes_com_reprovacao = set(componentes_com_reprovacao) | set(
                matriculas_diario.values_list('diario__componente_curricular__componente_id', flat=True)
            )
            for componente in componentes_com_reprovacao:
                reprovacoes_suap = matriculas_diario.filter(diario__componente_curricular__componente=componente).count()
                reprovacoes_qacademico = matriculas_diario_resumidas.filter(equivalencia_componente__componente=componente).count()
                if reprovacoes_suap + reprovacoes_qacademico >= self.matriz.estrutura.qtd_max_reprovacoes_disciplina:
                    return 'Quantidade máxima de reprovações em disciplina.'
        return False

    @transaction.atomic
    def jubilar(self, motivo: str, automatico: bool = False) -> None:
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        if self.integralizou_ensino_medio:
            ultima_matricula_periodo.integralizar_ensino_medio('Jubilamento')
            return

        procedimento_matricula = ProcedimentoMatricula()
        procedimento_matricula.tipo = 'Jubilamento'
        procedimento_matricula.situacao_matricula_anterior = self.situacao
        procedimento_matricula.matricula_periodo = ultima_matricula_periodo
        procedimento_matricula.motivo = motivo
        procedimento_matricula.data = datetime.datetime.now()
        procedimento_matricula.save()
        if automatico:
            ProcedimentoMatricula.objects.filter(pk=procedimento_matricula.pk).update(user=None)

        self.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.JUBILADO)
        ultima_matricula_periodo = self.get_ultima_matricula_periodo()
        ultima_matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.JUBILADO)
        ultima_matricula_periodo.save()
        self.save()
        ultima_matricula_periodo.indeferir_requerimentos_automatizados_pendentes(procedimento_matricula)

    def pesquisas_egresso(self):
        from egressos.models import Pesquisa

        pesquisas = Pesquisa.objects.filter(inicio__lte=datetime.date.today(), fim__gte=datetime.date.today(), publicada=True)
        pesquisas = pesquisas.filter(modalidade=self.curso_campus.modalidade) | pesquisas.filter(modalidade__isnull=True)
        pesquisas = pesquisas.filter(conclusao__ano=self.ano_conclusao) | pesquisas.filter(conclusao__isnull=True)
        pesquisas = pesquisas.filter(uo__pk=self.curso_campus.diretoria.setor.uo_id) | pesquisas.filter(uo=None)
        pesquisas = pesquisas.filter(curso_campus=self.curso_campus) | pesquisas.filter(curso_campus__isnull=True)
        return pesquisas

    def get_total_medidas_disciplinares_premiacoes(self, data_inicio, data_fim):
        return '{} / {}'.format(
            self.medidadisciplinar_set.filter(
                Q(data_inicio__lte=data_fim, data_inicio__gte=data_inicio) | Q(data_fim__lte=data_fim, data_fim__gte=data_inicio)
            ).count(),
            self.premiacao_set.filter(data__lte=data_fim, data__gte=data_inicio).count(),
        )

    def get_total_atividades_complementares(self, data_inicio, data_fim):
        return self.atividadecomplementar_set.filter(data_atividade__gte=data_inicio, data_atividade__lte=data_fim).count()

    def get_ira_curso_aluno(self):
        ira = (
            Aluno.objects.filter(curso_campus=self.curso_campus).aggregate(soma=Sum('ira'))['soma']
            / Aluno.objects.filter(curso_campus=self.curso_campus).count()
        )
        return mask_nota(ira)

    def get_url_historico_diploma(self):
        if self.situacao_id in (SituacaoMatricula.CONCLUIDO, SituacaoMatricula.FORMADO, SituacaoMatricula.INTEGRALIZADO_ENSINO_MEDIO):
            assinatura_eletronica = (
                AssinaturaEletronica.objects.filter(registro_emissao_diploma__aluno=self, data_assinatura__isnull=False, data_revogacao__isnull=True)
                .order_by('-id')
                .first()
            )
            if assinatura_eletronica:
                return assinatura_eletronica.get_url_historico(), assinatura_eletronica.get_url_diploma()
            assinatura_digital = (
                AssinaturaDigital.objects.filter(registro_emissao_diploma__aluno=self, concluida=True, data_revogacao__isnull=True)
                .order_by('-id')
                .first()
            )
            if assinatura_digital:
                return assinatura_digital.get_url_historico(), assinatura_digital.get_url_diploma()
        return None

    def get_filtros_nadaconsta_exigido(self, procedimento):
        filtros = {}
        ProcedimentoMatricula = apps.get_model('edu', 'ProcedimentoMatricula')
        if procedimento in [
            ProcedimentoMatricula.INTERCAMBIO,
            ProcedimentoMatricula.TRANCAMENTO_COMPULSORIO,
            ProcedimentoMatricula.TRANCAMENTO_VOLUNTARIO,
        ]:
            filtros['item_configuracao__exigido_trancamento_curso'] = True
        elif procedimento == ProcedimentoMatricula.CANCELAMENTO_VOLUNTARIO:
            filtros['item_configuracao__exigido_cancelamento_curso'] = True
        elif procedimento == ProcedimentoMatricula.TRANSFERENCIA_INTERCAMPUS:
            filtros['item_configuracao__exigido_transferencia_intercampus'] = True
        elif procedimento == ProcedimentoMatricula.TRANSFERENCIA_CURSO:
            filtros['item_configuracao__exigido_transferencia_curso'] = True
        elif procedimento == ProcedimentoMatricula.TRANSFERENCIA_EXTERNA:
            filtros['item_configuracao__exigido_transferencia_externa'] = True
        elif procedimento == 'Emissão de Diploma':
            filtros['item_configuracao__exigido_emissao_diploma'] = True
        return filtros

    def possui_pendencia_nada_consta(self, procedimento):
        filtros = self.get_filtros_nadaconsta_exigido(procedimento)
        # procedimento não exige nada consta
        if len(filtros) == 0:
            return False
        # nova via de diploma ou certificado de integralização do ensino médio não exige nada consta
        if procedimento == 'Emissão de Diploma' and (self.get_via_diploma() > 0 or self.is_integralizado_cursando()):
            return False

        self.checar_registros_nada_consta()

        return (
            self.nadaconsta_set.filter(**filtros).filter(valido=True).exclude(quitado=True).exclude(data_validade__lt=datetime.date.today()).exists()
        )

    def checar_registros_nada_consta(self):
        NadaConsta = apps.get_model('edu', 'NadaConsta')
        ItemConfiguracaoNadaConsta = apps.get_model('edu', 'ItemConfiguracaoNadaConsta')

        # invalida nadaconsta expirado
        self.nadaconsta_set.filter(valido=True, data_validade__lt=datetime.date.today()).update(valido=False)

        itens_nada_consta = ItemConfiguracaoNadaConsta.objects.filter(
            configuracao__modalidades__in=[
                self.curso_campus.modalidade_id,
            ],
            configuracao__uo_id=self.curso_campus.diretoria.setor.uo.id,
        )
        itens_nada_consta = itens_nada_consta.filter(cursos__in=[self.curso_campus]) | itens_nada_consta.filter(cursos__isnull=True)

        ids_itens_nada_consta = list(itens_nada_consta.values_list('id', flat=True))
        # revoga nadaconsta de item avaliado que não faz parte da configuração do aluno
        self.nadaconsta_set.filter(valido=True, data_solicitacao__isnull=False).exclude(item_configuracao_id__in=ids_itens_nada_consta).update(
            valido=False,
            data_revogacao=datetime.datetime.now(),
            justificativa_revogacao='Revogado em razão da alteração da configuração do item de nada consta do curso ou modalidade.',
        )
        # invalida nadaconsta que não faz parte da configuração do aluno
        self.nadaconsta_set.filter(valido=True).exclude(item_configuracao_id__in=ids_itens_nada_consta).update(valido=False)

        # invalida nadaconsta vinculado a curso diferente do curso do aluno
        self.nadaconsta_set.filter(valido=True, item_configuracao__cursos__isnull=False).exclude(
            item_configuracao__cursos__in=[self.curso_campus]
        ).update(valido=False)

        # cria nada consta não solicitado
        for item in itens_nada_consta:
            qs = NadaConsta.objects.filter(item_configuracao_id=item.id, aluno_id=self.id, valido=True)
            if not qs.exists():
                NadaConsta.objects.create(item_configuracao=item, tipo=item.tipo_nada_consta, aluno=self, valido=True)

    def revogar_registros_nada_consta_avaliados(self):
        """
        revoga todos os registros válidos solicitados e avaliados
        """
        self.nadaconsta_set.filter(valido=True, data_solicitacao__isnull=False, quitado__isnull=False).update(
            valido=False,
            data_revogacao=datetime.datetime.now(),
            justificativa_revogacao='Revogado em razão da exclusão de procedimento de matrícula.',
        )

    def solicitar_quitacao_nada_consta(self, item_id=None, procedimento=None, justificativa=None):
        # emissão de nova via não exige nada consta
        if procedimento == 'Emissão de Diploma' and self.get_registros_emissao_diploma(tipo=RegistroEmissaoDiploma.TIPO_CONCLUSAO_CURSO).exists():
            return
        filtros = self.get_filtros_nadaconsta_exigido(procedimento)
        # procedimento não exige nada consta
        if procedimento and len(filtros) == 0:
            return

        self.checar_registros_nada_consta()
        qs = self.nadaconsta_set.filter(valido=True, quitado__isnull=True, data_solicitacao__isnull=True)

        if item_id:
            qs = qs.filter(item_configuracao_id=item_id)
        elif procedimento:
            qs = qs.filter(**filtros)

        for nadaconsta in qs:
            nadaconsta.solicitar(justificativa)

    def pode_gerar_declaracao_nada_consta(self):
        return not self.nadaconsta_set.filter(valido=True).exclude(quitado=True).exists()

    def get_nada_consta_menor_validade(self):
        if self.pode_gerar_declaracao_nada_consta():
            return self.nadaconsta_set.filter(valido=True, quitado=True).order_by('data_validade').first()

    def criar_papel_discente(self):
        if 'rh' in settings.INSTALLED_APPS:
            Papel = apps.get_model('rh', 'Papel')
            ContentType = apps.get_model('contenttypes.ContentType')
            aluno = self.get_vinculo().relacionamento
            if not aluno.papeis_ativos.exists():
                kwargs = {'detalhamento': f'{aluno.matricula} - Discente', 'descricao': f'{aluno.matricula} - Discente', 'data_fim': None}
                _papel_cargo, _criou = Papel.objects.update_or_create(
                    vinculo=aluno.get_vinculo(),
                    tipo_papel=Papel.TIPO_PAPEL_DISCENTE,
                    data_inicio=datetime.datetime.now(),
                    papel_content_type=ContentType.objects.get_for_model(aluno),
                    papel_content_id=aluno.id,
                    defaults=kwargs,
                )

    def get_dados_receita_federal(self):
        api = APIExterna.PESSOAFISICA
        dados_cidadao = []
        obj = PessoaInfoComplementar.get_instance(self.pessoa_fisica, api, force=False)
        if obj:
            dados_cidadao = obj.informacoes
        sucesso = len(dados_cidadao) > 0 and 'mensagem' not in dados_cidadao[0]
        info_pessoafisica_rfb = dados_cidadao[0] if sucesso else None
        if info_pessoafisica_rfb:
            return {
                'Nome': info_pessoafisica_rfb.get('Nome', ''),
                'DataNascimento': info_pessoafisica_rfb.get('DataNascimento', ''),
                'NomeMae': info_pessoafisica_rfb.get('NomeMae', ''),
            }
        else:
            erro = dados_cidadao and dados_cidadao[0] or 'Ocorreu um erro na consulta dos dados do aluno'
            raise Exception(erro)

    def get_codigo_sgp(self):
        dados = (
            self.matriculaperiodo_set.filter(codigo_sgp__isnull=False)
            .values_list('codigo_sgp', 'ano_letivo__ano', 'periodo_letivo')
            .order_by('id')
            .last()
        )
        if dados:
            return '{} ({}/{})'.format(*dados)
        return None

    def get_media_final_periodo_referencia(self):
        mp = self.get_periodo_referencia()
        media_final = mp.get_media_final_periodo() if mp else None
        return media_final

    # Atividade de prática profissional

    def calcular_media_atividade_pratica_profissional(self):
        ids_contabilizadas = AtividadePraticaProfissional.get_ids_atividades_contabilizadas(self)
        if not ids_contabilizadas:
            return None

        atividades = AtividadePraticaProfissional.objects.filter(id__in=ids_contabilizadas).only('nota', 'carga_horaria')

        if atividades.exists():
            soma_ch = sum(d.carga_horaria for d in atividades)
            soma_produtos = sum(d.nota * d.carga_horaria for d in atividades)
            return soma_produtos / soma_ch if soma_ch > 0 else None
        return None

    def get_ch_atividade_pratica_profissional_esperada(self):
        matrizppc = self.matriz.get_matrizppc() if self.matriz else None
        if matrizppc is None:
            return 0
        return matrizppc.ppc.ch_pratica

    def get_ch_atividade_pratica_profissional_realizada(self, modalidade_pratica_profissional_id=None):
        atividades = AtividadePraticaProfissional.objects.filter(matricula_periodo__aluno_id=self.id, situacao=AtividadePraticaProfissional.CONCLUIDA)
        if modalidade_pratica_profissional_id:
            atividades = atividades.filter(modalidade_pratica_profissional_id=modalidade_pratica_profissional_id)
        return atividades.aggregate(Sum('carga_horaria'))['carga_horaria__sum'] or 0

    def get_ch_atividade_pratica_profissional_contabilizada(self, modalidade_pratica_profissional_id=None):
        ids_contabilizadas = AtividadePraticaProfissional.get_ids_atividades_contabilizadas(self, modalidade_pratica_profissional_id)
        total_ch = 0
        if not ids_contabilizadas:
            return total_ch

        matrizppc = self.matriz.get_matrizppc()
        qs_modalidades = matrizppc.get_modalidades_praticaprofissionalppc().only('modalidade_pratica_profissional_id', 'ch_requerida')
        if modalidade_pratica_profissional_id:
            qs_modalidades = qs_modalidades.filter(modalidade_pratica_profissional_id=modalidade_pratica_profissional_id)
        modalidades_com_ch_requerida = {}
        for modalidade in qs_modalidades:
            modalidades_com_ch_requerida[modalidade.modalidade_pratica_profissional_id] = modalidade.ch_requerida

        atividades_com_ch_requerida_por_modalidade = {}
        for atividade in AtividadePraticaProfissional.objects.filter(id__in=ids_contabilizadas).only(
            'modalidade_pratica_profissional_id', 'carga_horaria'
        ):
            modalidade_id = atividade.modalidade_pratica_profissional_id
            ch_requerida = modalidades_com_ch_requerida[modalidade_id]

            if ch_requerida is None or ch_requerida == 0:
                # se modalidade não possui CH requerida, contabiliza a soma de todas as atividades contabilizadas
                total_ch += atividade.carga_horaria
            else:
                # senão agrupa as atividades por modalidade para conabizair a ch por modalidade posteriormente
                if modalidade_id not in atividades_com_ch_requerida_por_modalidade:
                    atividades_com_ch_requerida_por_modalidade[modalidade_id] = []
                atividades_com_ch_requerida_por_modalidade[modalidade_id].append(atividade)

        # ajustando soma ch de atividades sem ch requerida
        if total_ch > 0:
            soma_ch_obrigatoria = matrizppc.get_modalidades_praticaprofissionalppc().aggregate(total=Sum('ch_requerida'))['total'] or 0
            limite_ch_nao_obrigatoria = matrizppc.ppc.ch_pratica - soma_ch_obrigatoria
            total_ch = min(total_ch, limite_ch_nao_obrigatoria)

        for modalidade_id, atividades in atividades_com_ch_requerida_por_modalidade.items():
            ch_requerida = modalidades_com_ch_requerida[modalidade_id]
            ch_acumulada = 0
            for atividade in atividades:
                ch_acumulada += atividade.carga_horaria
            total_ch += min(ch_acumulada, ch_requerida)

        return total_ch

    def get_ch_atividade_pratica_profissional_pendente(self, modalidade_pratica_profissional_id):
        matrizppc = self.matriz.get_matrizppc() if self.matriz else None
        if matrizppc is None:
            return 0

        modalidade = (
            matrizppc.modalidadepraticaprofissionalppc_set.filter(modalidade_pratica_profissional_id=modalidade_pratica_profissional_id)
            .only('ch_requerida')
            .first()
        )
        ch_requerida = modalidade.ch_requerida if modalidade and modalidade.ch_requerida is not None else 0
        if ch_requerida == 0:
            return 0

        ids_contabilizadas = AtividadePraticaProfissional.get_ids_atividades_contabilizadas(self, modalidade_pratica_profissional_id)
        if not ids_contabilizadas:
            return ch_requerida

        ch_contabilizada = AtividadePraticaProfissional.objects.filter(id__in=ids_contabilizadas).aggregate(total=Sum('carga_horaria'))['total'] or 0

        return ch_requerida - ch_contabilizada if ch_requerida > ch_contabilizada else 0

    def get_ch_atividade_pratica_profissional_pendente_total(self):
        matrizppc = self.matriz.get_matrizppc() if self.matriz else None
        if matrizppc and matrizppc.ppc.ch_pratica:
            ch_esperada = matrizppc.ppc.ch_pratica
            ch_cumprida = self.get_ch_atividade_pratica_profissional_contabilizada()
            if ch_cumprida < ch_esperada:
                return ch_esperada - ch_cumprida
        return 0

    def get_pendencias_atividade_pratica_profissional(self, resumido=False):
        pendencias = []
        if self.get_ch_atividade_pratica_profissional_pendente_total() > 0:
            if resumido:
                return ['Não-cumprida']
            pendencias.append('A carga horária exigida de atividades de prática profissional não foi atingida.')

        media_pratica_profissional = self.calcular_media_atividade_pratica_profissional()
        if media_pratica_profissional is not None and media_pratica_profissional < self.matriz.estrutura.media_aprovacao_sem_prova_final:
            if resumido:
                return ['Média insuficiente']
            pendencias.append('A média das atividades de prática profissional não é suficiente para aprovação.')

        qs = AtividadePraticaProfissional.objects.filter(matricula_periodo__aluno_id=self.id)
        if qs.exclude(
            situacao__in=[
                AtividadePraticaProfissional.CONCLUIDA,
                AtividadePraticaProfissional.DESCONSIDERADA,
                AtividadePraticaProfissional.INDEFERIDA,
                AtividadePraticaProfissional.INSUFICIENTE,
            ]
        ).exists():
            if resumido:
                return ['Aguardando conclusão']
            pendencias.append('Existem atividades de prática profissional aguardando conclusão.')
        if qs.filter(situacao=AtividadePraticaProfissional.CONCLUIDA, nota__isnull=True).exists():
            if resumido:
                return ['Aguardando avaliação']
            pendencias.append('Existem atividades de prática profissional concluídas aguardando avaliação.')
        return pendencias

    # Uso de imagem

    def autorizou_uso_imagem(self):
        return self.solicitacaoautorizacaousoimagem_set.filter(autorizado=True, data_revogacao__isnull=True).exists()

    def requer_solicitacao_uso_imagem(self):
        return not self.solicitacaoautorizacaousoimagem_set.exists() or not self.autorizou_uso_imagem()

    def autorizar_uso_imagem(self, user, autorizado):
        if autorizado:
            self.solicitacaoautorizacaousoimagem_set.create(autorizado=True, data_avaliacao=datetime.datetime.now(), usuario_avaliacao=user)
        else:
            if self.autorizou_uso_imagem():
                self.solicitacaoautorizacaousoimagem_set.filter(autorizado=True, data_revogacao__isnull=True).update(
                    data_revogacao=datetime.datetime.now(), usuario_revogacao=user
                )
            elif not self.solicitacaoautorizacaousoimagem_set.filter(autorizado=False, data_revogacao__isnull=True, usuario_avaliacao=user).exists():
                self.solicitacaoautorizacaousoimagem_set.create(autorizado=False, data_avaliacao=datetime.datetime.now(), usuario_avaliacao=user)


class SolicitacaoAutorizacaoUsoImagem(models.Model):
    aluno = models.ForeignKeyPlus(Aluno, verbose_name='Aluno')
    autorizado = models.BooleanField(verbose_name='Autorizado', default=False)
    usuario_avaliacao = models.ForeignKeyPlus(User, verbose_name='Responsável pela Avaliação', null=True)
    data_avaliacao = models.DateTimeFieldPlus(verbose_name='Data da Avaliação')
    data_revogacao = models.DateTimeFieldPlus(verbose_name='Data da Revogação', null=True)
    usuario_revogacao = models.ForeignKeyPlus(User, verbose_name='Responsável pela Revogação', null=True, related_name='saui2')

    class Meta:
        verbose_name = 'Solicitação de Autorização do Uso de Imagem'
        verbose_name_plural = 'Solicitações de Autorização do Uso de Imagem'

    def __str__(self):
        return f'Autorização do Uso de Imagem {self.id}'
