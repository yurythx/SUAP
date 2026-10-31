import datetime
import decimal
import operator
import os
from datetime import timedelta
from decimal import Decimal
from functools import reduce
from uuid import uuid4

from dateutil.relativedelta import relativedelta
from django import forms
from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.fields import ArrayField
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q, Subquery, Sum
from django.urls import reverse_lazy
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe

from comum.utils import get_setor, tl
from djtools.db import models
from djtools.templatetags.filters import format_datetime, format_time, status
from djtools.templatetags.filters.utils import format_hours
from djtools.utils import ha_choque_de_periodo
from pgd.utils import (
    calcula_complexidade_ajustada,
    get_ch_servidor_periodo,
    get_data_fim_pgd1,
    get_datetime_now,
    gv,
    obter_compensacoes_especificas_compesaveis_rit,
    obter_dados_horas_ponto_servidor,
    setores_que_sou_chefe_hoje,
)
from pit_rit.utils import PontoDocente

# from comum.models import User
from ponto.models import SaldoExterno
from rh.models import Funcao, Servidor, Setor, Situacao, UnidadeOrganizacional


class ChoiceArrayField(ArrayField):
    def formfield(self, **kwargs):
        defaults = {'form_class': forms.MultipleChoiceField, 'widget': forms.CheckboxSelectMultiplePlus, 'choices': self.base_field.choices}
        defaults.update(kwargs)
        return super(ArrayField, self).formfield(**defaults)

    def to_python(self, value):
        value = super().to_python(value)
        if isinstance(value, list):
            return [self.base_field.to_python(val) for val in value]
        return value


# ====================================================
# REGISTROS DE AÇÃO
# ====================================================


class RegistroAcaoPGD(models.ModelPlus):
    user = models.CurrentUserField(editable=False)
    data = models.DateTimeFieldPlus('Data', auto_now_add=True, editable=False)
    ip = models.GenericIPAddressField(verbose_name='IP', editable=False)
    observacao = models.TextField(editable=False)

    class Meta:
        ordering = ('-data',)
        abstract = True

    def __str__(self):
        return self.observacao

    @classmethod
    def registrar_acao(cls, pts, tipo_acao, user, ip, observacao=''):
        user = user if not user.is_anonymous else None
        cls.objects.create(tipo=tipo_acao, pts=pts, ip=ip, observacao=observacao, user=user)


class RegistroAcaoPTS(RegistroAcaoPGD):
    TIPO_CRIACAO = 1
    TIPO_EDITOU_VIGENCIA = 2
    TIPO_DOCUMENTACAO = 3
    TIPO_PUBLICADO = 4
    TIPO_DESPUBLICADO = 5
    TIPO_CANCELADO = 6
    TIPO_ATIVIDADE_VINCULADA = 7
    TIPO_ATIVIDADE_REMOVIDA = 8
    TIPO_ATIVIDADE_ATIVADA = 9
    TIPO_ATIVIDADE_DESATIVADA = 10
    TIPO_ALTEROU_AUXILIARES = 11

    TIPO_CHOICES = (
        (TIPO_CRIACAO, 'Criação'),
        (TIPO_EDITOU_VIGENCIA, 'Editou Vigência'),
        (TIPO_DOCUMENTACAO, 'Editou Documentação'),
        (TIPO_PUBLICADO, 'Publicado'),
        (TIPO_DESPUBLICADO, 'Despublicado'),
        (TIPO_CANCELADO, 'Cancelado'),
        (TIPO_ATIVIDADE_VINCULADA, 'Atividade vinculada'),
        (TIPO_ATIVIDADE_REMOVIDA, 'Atividade removida'),
        (TIPO_ATIVIDADE_ATIVADA, 'Atividade ativada'),
        (TIPO_ATIVIDADE_DESATIVADA, 'Atividade desativada'),
        (TIPO_ALTEROU_AUXILIARES, 'Alterou Equipe de Auxiliares '),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    pts = models.ForeignKeyPlus('pgd.PlanoTrabalhoSetorial', editable=False, null=True)


# A class RegistroAcaoSolicitacaoAdesaoServidor está logo depois da class SolicitacaoAdesaoServidor
# A class RegistroAcaoPlanoIndividualTrabalho está logo depois da class PlanoIndividualTrabalho


# ====================================================
# CADASTROS BÁSICOS
# ====================================================


class ModalidadeExecucaoAtividade:
    # Valores permitidos para a modalidade_execucao:
    # 1 - Presencial
    # 2 - Semipresencial
    # 3 - Teletrabalho

    MODALIDADE_PRESENCIAL = 1
    MODALIDADE_SEMIPRESENCIAL = 2
    MODALIDADE_TELETRABALHO = 3

    MODALIDADES_CHOICES = (
        (MODALIDADE_PRESENCIAL, 'Presencial'),
        (MODALIDADE_SEMIPRESENCIAL, 'Semipresencial'),
        (MODALIDADE_TELETRABALHO, 'Teletrabalho'),
    )

    @staticmethod
    def get_default():
        return [ModalidadeExecucaoAtividade.MODALIDADE_PRESENCIAL]

    @staticmethod
    def get_modalidades_display(modalidades):
        strs = []

        for m in ModalidadeExecucaoAtividade.MODALIDADES_CHOICES:
            if m[0] in modalidades:
                strs.append(m[1])

        return ' / '.join(strs)


class TematicaAtividade(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    administradores = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Administradores da Temática', blank=True)
    setor = models.ForeignKeyPlus('rh.Setor', null=True, blank=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Temática'
        verbose_name_plural = 'Temáticas'
        ordering = ('titulo',)

    def __str__(self):
        if not self.ativo:
            return f'{self.titulo} - (Inativo)'
        return f'{self.titulo}'

    def clean(self):
        is_insert = not self.id
        if not is_insert:
            # Só desativa se a Subtemática, Serviço e Atividade estirem inativas
            atual = TematicaAtividade.objects.get(id=self.id)
            if atual.ativo and not self.ativo:
                if SubtematicaAtividade.objects.filter(tematica_id=self.id, ativo=True).exists():
                    raise ValidationError('Impossível desativar se existem macroprocessos ativos vinculados.')

    @property
    def get_atividades(self):
        return self.atividade_set.all().order_by('titulo')

    @property
    def get_atividades_ativo(self):
        return self.get_atividades.filter(ativo=True)

    @staticmethod
    def eh_administrador_de_tematica(user):
        return TematicaAtividade.objects.filter(ativo=True, administradores__user=user).exists()

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente

    @staticmethod
    def sincronizar_permissoes_administradores_tematica():
        administradores = set()
        for tematica in TematicaAtividade.objects.filter(ativo=True):
            for adm in tematica.administradores.all():
                administradores.add(adm.user)

        grupo = Group.objects.get(name='Administrador de Temática de Atividade')
        estao_no_grupo = grupo.user_set.all()

        # Adicionar os administradores no grupo
        for administrador in administradores:
            if administrador not in estao_no_grupo:
                administrador.groups.add(grupo)

        # Remove do grupo os que nao sao mais administradores
        for estah_no_grupo in estao_no_grupo:
            if estah_no_grupo not in administradores:
                estah_no_grupo.groups.remove(grupo)

    @staticmethod
    def sincronizar_permissoes_administradores_tematica_administrador(vinculo):
        grupo = Group.objects.get(name='Administrador de Temática de Atividade')

        # Se eh administrador de alguma tematica
        # Se nao for tira do grupo
        if TematicaAtividade.objects.filter(ativo=True, administradores__in=[vinculo]).exists():
            vinculo.user.groups.add(grupo)
        else:
            vinculo.user.groups.remove(grupo)


class SubtematicaAtividade(models.ModelPlus):
    tematica = models.ForeignKeyPlus('pgd.TematicaAtividade', verbose_name='Temática')
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Macroprocesso'
        verbose_name_plural = 'Macroprocessos'
        ordering = ('titulo',)

    def __str__(self):
        if not self.ativo:
            return f'{self.tematica} -> {self.titulo} - (Inativo)'
        return f'{self.tematica} -> {self.titulo}'

    def clean(self):
        is_insert = not self.id
        if not is_insert:
            # Só desativa se a Subtemática, Serviço e Atividade estirem inativos
            atual = SubtematicaAtividade.objects.get(id=self.id)
            if atual.ativo and not self.ativo:
                if ServicoAtividade.objects.filter(subtematica_id=self.id, ativo=True).exists():
                    raise ValidationError('Impossível desativar se existem serviços inativos vinculados.')

    @property
    def get_atividades(self):
        # return Atividade.objects.filter(tematica=self).order_by('titulo')
        return self.atividade_set.all().order_by('titulo')

    @property
    def get_atividades_ativo(self):
        return self.get_atividades.filter(ativo=True)

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class ServicoAtividade(models.ModelPlus):
    subtematica = models.ForeignKeyPlus('pgd.SubtematicaAtividade', verbose_name='Macroprocesso')
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Serviço'
        verbose_name_plural = 'Serviços'
        ordering = ('titulo',)

    def __str__(self):
        if not self.ativo:
            return f'{self.subtematica} -> {self.titulo} - (Inativo)'
        return f'{self.subtematica} -> {self.titulo}'

    def clean(self):
        is_insert = not self.id
        if not is_insert:
            # Só desativa se a Subtemática, Serviço e Atividade estirem inativas
            atual = ServicoAtividade.objects.get(id=self.id)
            if atual.ativo and not self.ativo:
                if Atividade.objects.filter(servico_id=self.id, ativo=True).exists():
                    raise ValidationError('Impossível desativar se existem atividades inativas vinculadas.')

    @property
    def get_atividades(self):
        # return Atividade.objects.filter(tematica=self).order_by('titulo')
        return self.atividade_set.all().order_by('titulo')

    @property
    def get_atividades_ativo(self):
        return self.get_atividades.filter(ativo=True)

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class FaixaComplexidade(models.ModelPlus):
    complexidade = models.CharFieldPlus(verbose_name='Complexidade')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Faixa de Complexidade'
        verbose_name_plural = 'Faixas de Complexidade'
        unique_together = ('complexidade',)
        ordering = ('complexidade',)

    def __str__(self):
        if not self.ativo:
            return f'{self.complexidade} - (Inativo)'
        return f'{self.complexidade}'

    @transaction.atomic
    def save(self, *args, **kargs):
        is_insert = not self.id

        super().save(*args, **kargs)

        # Cadastra ComplexidadeAtividade para essa nova FaixaComplexidade
        if is_insert:
            atividades = Atividade.objects.all()
            for atividade in atividades:
                ComplexidadeAtividade.objects.get_or_create(atividade=atividade, faixa_complexidade=self)

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class AtividadeManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(situacao_cadastro=Atividade.CADASTRADO, original__isnull=True)

    def solicitacoes(self):
        # return super().get_queryset().filter(Q(situacao_cadastro__in=[Atividade.SOLICITADO, Atividade.SOLICITACAO_INDEFERIDA, Atividade.SOLICITACAO_PENDENTE_ENVIO]) | Q(situacao_cadastro=Atividade.CADASTRADO, original__isnull=False))
        return super().get_queryset().filter(solicitado_por__isnull=False)

    def todos(self):
        return super().get_queryset()


class Atividade(models.ModelPlus):
    tematica = models.ForeignKeyPlus('pgd.TematicaAtividade', verbose_name='Temática')
    subtematica = models.ForeignKeyPlus('pgd.SubtematicaAtividade', verbose_name='Macroprocesso', null=True, blank=True)
    servico = models.ForeignKeyPlus('pgd.ServicoAtividade', verbose_name='Serviço', null=True, blank=True)

    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)

    """
    Para cada atividade

    Temática --< subtematica --<  servico | Atividade         | Entregas                              | I    II  III  IV	V   VI  VII VIII IX  X  XI XII
    PRODES   --      xx      --     yy    | Acompanhamento de | Atendimento de demandas via           | 0,5	1	2	4	6	8	12	16	20	24	32	40 pontos/horas
                                                                demandas síncronas   telefone/whats
                                                                ou chamadas de vídeo
    """
    faixas_complexidade = models.ManyToManyFieldPlus(FaixaComplexidade, through='pgd.ComplexidadeAtividade')

    ganho_produtividade = models.DecimalFieldPlus(verbose_name='Ganho de Produtividade %', default=0)

    pode_ser_teletrabalho = models.BooleanField(verbose_name='Pode ser executada na modalidade Teletrabalho?', default=False)

    # - O campo ativo servirá apenas para gerenciar a solicitação de cadastro de uma nova atividade
    # - Toda ativiade CADASTRADA fica como True
    #   - Lembrando que quando se solicita e depois defere ela também ficará como True
    # - Toda ativiade SOLICITADA fica como False
    ativo = models.BooleanField(
        verbose_name='Ativo?', default=False, help_text='Se estiver Inativa não estará mais disponível para ser utilizada.', editable=False
    )
    # Para saber se atividade está ativa ou não deve-se observar a data de efeitos de inativação
    data_inativacao_efeitos_a_partir_de = models.DateFieldPlus('Inativação com efeitos a partir de', blank=True, null=True)

    original = models.ForeignKeyPlus('self', null=True, blank=True, verbose_name='Atividade Original')
    CADASTRADO = 1  # Se a atividade já estiver cadastrada definitavamente
    SOLICITADO = 2
    SOLICITACAO_PENDENTE_ENVIO = 3
    SOLICITACAO_INDEFERIDA = 4
    SITUACAO_ATIVIDADE_CHOICES = [
        [CADASTRADO, 'Cadastrado'],
        [SOLICITADO, 'Solicitado'],
        [SOLICITACAO_PENDENTE_ENVIO, 'Pendente de Envio'],
        [SOLICITACAO_INDEFERIDA, 'Solicitação Indeferida'],
    ]
    situacao_cadastro = models.PositiveIntegerField('Situação', choices=SITUACAO_ATIVIDADE_CHOICES, editable=False, null=True, blank=True)
    solicitado_por = models.ForeignKeyPlus('comum.User', null=True, blank=True, editable=False, related_name='atividade_solicitado_por')
    justificativa_solicitacao = models.TextField(verbose_name='Justificativa da Solicitação', null=True, blank=True)
    justificativa_indeferimento = models.TextField(verbose_name='Justificativa do Indeferimento', null=True, blank=True)

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'
        ordering = ('titulo',)
        permissions = (
            ('pode_visualizar_qta', 'Pode visualizar QTA'),
            ('pode_admin_qta', 'Pode admin QTA'),
        )

    objects = AtividadeManager()

    def __str__(self):
        hierarquia = None
        if self.servico:
            hierarquia = str(self.servico)
        elif self.subtematica:
            hierarquia = str(self.subtematica)
        else:
            hierarquia = str(self.tematica)
        return f'{hierarquia} -> {self.titulo}'

    def hierarquia(self):
        hierarquia = None
        if self.servico:
            hierarquia = str(self.servico)
        elif self.subtematica:
            hierarquia = str(self.subtematica)
        else:
            hierarquia = str(self.tematica)
        return hierarquia

    def hierarquia_atividade(self):
        return f'{self.hierarquia()} -> {self.titulo}'

    def get_entregas(self):
        return self.atividadeentrega_set.all()

    @property
    def estah_ativa(self):
        # O campo ativo servirá apenas para gerenciar a solicitação de cadastro de uma nova atividade
        # - ativo
        # Para saber se atividade está ativa ou não deve-se observar a data de efeitos de inativação
        # - data_inativacao_efeitos_a_partir_de
        hoje = get_datetime_now().date()
        return not (self.ativo and self.data_inativacao_efeitos_a_partir_de and hoje >= self.data_inativacao_efeitos_a_partir_de)

    @staticmethod
    def get_atividades_ativas():
        hoje = get_datetime_now().date()
        atividades = Atividade.objects.filter(Q(data_inativacao_efeitos_a_partir_de__isnull=True) | Q(data_inativacao_efeitos_a_partir_de__gt=hoje))
        atividades = atividades.filter(ativo=True)
        return atividades

    @staticmethod
    def get_atividades_inativas():
        hoje = get_datetime_now().date()
        atividades = Atividade.objects.filter(data_inativacao_efeitos_a_partir_de__lte=hoje)
        atividades = atividades.filter(situacao_cadastro=Atividade.CADASTRADO)
        return atividades

    @property
    def estah_cadastrada(self):
        return self.situacao_cadastro == Atividade.CADASTRADO

    @property
    def estah_solicitada(self):
        return self.situacao_cadastro == Atividade.SOLICITADO

    @property
    def esta_indeferida(self):
        return self.situacao_cadastro == Atividade.SOLICITACAO_INDEFERIDA

    @property
    def esta_pendente_envio(self):
        return self.situacao_cadastro == Atividade.SOLICITACAO_PENDENTE_ENVIO

    @property
    def tipo_solicitacao(self):
        if self.solicitado_por:
            if self.original:
                return 'Alteração'
            return 'Cadastro'
        return None

    @property
    def descricao_entregas(self):
        if self.atividadeentrega_set.exists():
            strs = []
            for m in self.atividadeentrega_set.filter(ativo=True):
                strs.append(f'{m.titulo}')
            return '; '.join(strs)
        else:
            return False

    def get_titulo(self):
        if not self.ativo:
            return f'{self.titulo} (Inativo)'
        return f'{self.titulo}'

    def clean(self):
        is_insert = not self.id

        subtematica = self.subtematica
        servico = self.servico
        if servico:
            self.subtematica = servico.subtematica
            self.tematica = servico.subtematica.tematica
        elif subtematica:
            self.tematica = subtematica.tematica

        if is_insert:
            if self.tematica and not self.tematica.ativo:
                raise ValidationError('Impossível criar atividade para uma temática que não esteja ativa.')
            if self.subtematica and not self.subtematica.ativo:
                raise ValidationError('Impossível criar atividade para uma subtemática que não esteja ativa.')
            if self.servico and not self.servico.ativo:
                raise ValidationError('Impossível criar atividade para um serviço que não esteja ativo.')
        else:
            if self.ativo and (not self.tematica.ativo):
                raise ValidationError('Impossível ativar se a temática estiver desativada.')
            if self.ativo and (self.subtematica and not self.subtematica.ativo):
                raise ValidationError('Impossível ativar se o Macroprocesso estiver desativada.')
            if self.ativo and (self.servico and not self.servico.ativo):
                raise ValidationError('Impossível ativar se o serviço estiver desativado.')

            # Só ativa se tiver com ao menos uma entrega cadastrada e ativa
            if self.ativo and not AtividadeEntrega.objects.filter(atividade=self, ativo=True).exists():
                raise ValidationError('Impossível ativar sem ter ao menos uma entrega ativa já cadastrada anteriormente.')

            # Só desativa se nao tiver ativa em algum PTS
            # if not self.ativo and PlanoTrabalhoSetorialAtividades.objects.filter(atividade=self, ativo=True).exists():
            #    raise ValidationError('Impossível desativar uma atividade vinculada e ativa em algum PTS.')

        # Só cadastra se existem faixas de complexidades cadastradas
        if not FaixaComplexidade.objects.filter(ativo=True).exists():
            raise ValidationError('Impossível cadastrar sem que existam faixas de complexidade cadastradas.')

    @transaction.atomic
    def save(self, *args, **kargs):
        is_insert = not self.id

        super().save(*args, **kargs)

        # Cadastra as ComplexidadeAtividade para a nova atividade
        if is_insert:
            tempo_complexidades = {
                'I': 0.5,
                'II': 1,
                'III': 2,
                'IV': 4,
                'V': 6,
                'VI': 8,
                'VII': 12,
                'VIII': 16,
                'IX': 20,
                'X': 24,
                'XI': 32,
                'XII': 40,
            }
            faixas = FaixaComplexidade.objects.all().order_by('id')
            for faixa in faixas:
                tempo_complexidade = tempo_complexidades.get(faixa.complexidade)
                ComplexidadeAtividade.objects.get_or_create(
                    atividade=self, faixa_complexidade=faixa, tempo_execucao_remoto=tempo_complexidade, tempo_execucao_presencial=tempo_complexidade
                )

    @property
    def get_complexidades(self):
        # return ComplexidadeAtividade.objects.filter(atividade=self).order_by('faixa_complexidade__titulo')
        return self.complexidadeatividade_set.filter(atividade=self).order_by('tempo_execucao_remoto')

    @property
    def get_complexidades_ativo(self):
        return self.get_complexidades.filter(faixa_complexidade__ativo=True)

    @property
    def get_complexidades_ativo_com_tempo(self):
        return self.get_complexidades_ativo.filter(Q(tempo_execucao_remoto__gt=0) | Q(tempo_execucao_presencial__gt=0))

    @staticmethod
    def pode_cadastrar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_como_adm_tematica = TematicaAtividade.eh_administrador_de_tematica(user)

        """
        # Regra retirada até que redefina
        eh_chefe_setor_alguma_tematica = False
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        if setores:
            # Se for chefe de setor deve ser chefe de ao menos uma temática
            lista_tematicas_setor = TematicaAtividade.objects.filter(setor__isnull=False, ativo=True).values_list('setor__sigla', flat=True)
            for setor in setores:
                if setor.sigla in list(lista_tematicas_setor):
                    eh_chefe_setor_alguma_tematica = True
                    break
        """
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_como_adm_tematica

    @staticmethod
    def pode_solicitar_cadastro_alteracao(user):
        # Se usuario puder apenas solicitar cadastro (nao pode efetivamente cadastrar)
        pode_cadastrar = Atividade.pode_cadastrar(user)
        if pode_cadastrar:
            return False
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento()).exists()
        return bool(setores)

    def pode_solicitar_alteracao_desta_atividade(self, user):
        # Se usuario solicitar alteracao para esta atividade
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(user)
        if not pode_solicitar_cadastro_alteracao:
            return False
        return bool(self.estah_cadastrada and self.ativo)

    def pode_submeter_alteracao_desta_atividade(self, user):
        # Se usuario pode submeter uma solicitacao alteracao para esta atividade
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(user)
        if not pode_solicitar_cadastro_alteracao:
            return False
        return bool(self.esta_pendente_envio and self.solicitado_por == user and self.existe_diferenca(self.original))

    def pode_remover_solicitacao_cadastro_alteracao(self, user):
        # Se usuario pode remover uma solicitacao de cadastro/alteração de atividade
        pode_solicitar_cadastro_alteracao = Atividade.pode_solicitar_cadastro_alteracao(user)
        if not pode_solicitar_cadastro_alteracao:
            return False
        return self.solicitado_por == user

    def pode_analisar_solicitacoes_cadastro_alteracao(self, user):
        pode_visualizar_quadro = user.has_perm('pgd.view_atividade')
        if not pode_visualizar_quadro:
            return False

        if self.estah_cadastrada or self.esta_indeferida:
            return False

        estah_em_gestao_pgd = user.has_group_cached('Gestão PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        if estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente:
            return True

        estah_como_adm_tematica_desta_atividade = self.tematica.administradores.filter(id=user.get_vinculo().id).exists()
        return bool(estah_como_adm_tematica_desta_atividade)

    def pode_alterar(self, user):
        # Se a atividade já estiver cadastrada definitavamente OU se for uma solicitacao de cadastro/ateracao já submetida
        if self.situacao_cadastro in [Atividade.CADASTRADO, Atividade.SOLICITADO]:
            # So altera se estiver ativa
            if not self.estah_ativa:
                return False
            estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
            estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
            estah_como_adm_tematica_desta_atividade = self.tematica.administradores.filter(id=user.get_vinculo().id).exists()
            return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_como_adm_tematica_desta_atividade
        # Se atividade é uma solitacao de alteracao que ainda nao foi submetida
        if self.situacao_cadastro == Atividade.SOLICITACAO_PENDENTE_ENVIO:
            return self.solicitado_por == user

        return False

    def existe_diferenca_na_atividade(self, outra_atividade):
        # Compara tudo de uma atividade para saber se existe diferenca ou nao entre elas

        # Atividade
        fields_atividades = ['tematica_id', 'subtematica_id', 'servico_id', 'titulo', 'ganho_produtividade', 'pode_ser_teletrabalho']
        return any(getattr(self, field) != getattr(outra_atividade, field) for field in fields_atividades)

    def existe_diferenca_nas_entregas(self, outra_atividade):
        # Compara tudo de uma atividade para saber se existe diferenca ou nao entre elas

        # AtividadeEntrega
        entregas_desta = AtividadeEntrega.objects.filter(atividade=self)
        entregas_outra_atividade = AtividadeEntrega.objects.filter(atividade=outra_atividade)
        if entregas_desta.count() != entregas_outra_atividade.count():
            return True
        if entregas_desta.filter(ativo=True).count() != entregas_outra_atividade.filter(ativo=True).count():
            return True
        for entrega_outra_atividade in entregas_outra_atividade:
            entrega_outra_atividade_titulo = entrega_outra_atividade.titulo.replace(' ', '')
            encontrou = False
            for entrega_desta in entregas_desta:
                entrega_desta_titulo = entrega_desta.titulo.replace(' ', '')
                if entrega_desta_titulo == entrega_outra_atividade_titulo:
                    encontrou = True
                    break
            if not encontrou:
                return True

        return False

    def existe_diferenca_nas_complexidades(self, outra_atividade):
        # Compara tudo de uma atividade para saber se existe diferenca ou nao entre elas

        # ComplexidadeAtividade
        complexidades_desta = ComplexidadeAtividade.objects.filter(atividade=self)
        complexidades_outra_atividade = ComplexidadeAtividade.objects.filter(atividade=outra_atividade)
        for complexidade_desta in complexidades_desta:
            complexidade_outra_atividade = complexidades_outra_atividade.filter(faixa_complexidade=complexidade_desta.faixa_complexidade)[0]
            if (
                complexidade_desta.tempo_execucao_remoto != complexidade_outra_atividade.tempo_execucao_remoto
                and complexidade_desta.tempo_execucao_presencial != complexidade_outra_atividade.tempo_execucao_presencial
            ):
                return True

        return False

    def existe_diferenca(self, outra_atividade):
        # Compara tudo de uma atividade para saber se existe diferenca ou nao entre elas

        # Atividade
        if self.existe_diferenca_na_atividade(outra_atividade):
            return True

        # AtividadeEntrega
        if self.existe_diferenca_nas_entregas(outra_atividade):
            return True

        # ComplexidadeAtividade
        return bool(self.existe_diferenca_nas_complexidades(outra_atividade))

    def substituir_esta_atividade_por_outra_atividade(self, outra_atividade):
        # Substitui todos os dados desta atividade pelos dados da outra_atividade
        # Utilizado quando se deferi uma solicitação de alteracao de atividade

        # Atividade
        if self.existe_diferenca_na_atividade(outra_atividade):
            fields_atividades = ['tematica_id', 'subtematica_id', 'servico_id', 'titulo', 'ganho_produtividade', 'pode_ser_teletrabalho']
            for field in fields_atividades:
                setattr(self, field, getattr(outra_atividade, field))
            self.save()

    @staticmethod
    def eh_apenas_administrador_tematica(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_como_adm_tematica = TematicaAtividade.eh_administrador_de_tematica(user)

        eh_chefe_setor = False
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        if setores:
            eh_chefe_setor = True

        if not estah_em_gestao_pgd and not estah_em_comissao_sistemica_vigente and not eh_chefe_setor:
            return estah_como_adm_tematica
        return False

    @staticmethod
    def eh_apenas_chefe_setor(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_como_adm_tematica = TematicaAtividade.eh_administrador_de_tematica(user)

        eh_chefe_setor = False
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        if setores:
            eh_chefe_setor = True

        if not estah_em_gestao_pgd and not estah_em_comissao_sistemica_vigente and not estah_como_adm_tematica:
            if eh_chefe_setor:
                return True

        return False

    # Usado no quadro_atividades -- pode visualizar o quadro de atividades
    @staticmethod
    def pode_visualizar(user):
        # estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        # estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        # estah_como_adm_tematica = TematicaAtividade.eh_administrador_de_tematica(user)
        pode_visualizar_quadro = user.has_perm('pgd.view_atividade')

        # return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_como_adm_tematica or pode_visualizar_quadro
        return pode_visualizar_quadro

    def pode_visualizar_esta_atividade(self, user):
        """
        pode_visualizar_quadro = user.has_perm('pgd.view_atividade')
        if self.ativo and pode_visualizar_quadro:
            return True

        estah_em_gestao_pgd = user.has_group_cached('Gestão PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_como_adm_tematica_desta_atividade = self.tematica.administradores.filter(id=user.get_vinculo().id).exists()

        # Regra retirada até que redefina
        eh_chefe_setor_tematica = False
        if self.tematica.setor:
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            if setores and (self.tematica.setor in setores):
                eh_chefe_setor_tematica = True

        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_como_adm_tematica_desta_atividade
        """

        return user.has_perm('pgd.view_atividade')

    """
    @staticmethod
    def pode_visualizar_no_admin(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_como_adm_tematica = TematicaAtividade.eh_administrador_de_tematica(user)

        eh_chefe_setor = False
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        if setores and user.get_relacionamento().setor in setores:
            eh_chefe_setor = True

        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_como_adm_tematica or eh_chefe_setor
    """


class AtividadeEntrega(models.ModelPlus):
    SEARCH_FIELDS = ['titulo']

    atividade = models.ForeignKeyPlus(Atividade)
    titulo = models.CharFieldPlus(verbose_name='Título')
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Entrega da Atividade'
        verbose_name_plural = 'Entregas da Atividade'
        ordering = ('titulo',)

    def __str__(self):
        # Ficou assim para que não eja exibido no FormtSet do cadastro do admin
        return self.titulo

    def pode_apagar_uma_atividade_entrega(self):
        # Implementar regra
        # - Nao apaga entrega de uma atividade que se essa entrega estiver vinculada a um RIT
        return True

    @staticmethod
    def pode_apagar_atividades_entrega(ids_atividade_entrega):
        # - Nao apaga se atividade for ficar apenas com essa entrega ativa
        at_e = AtividadeEntrega.objects.get(id=ids_atividade_entrega[0])
        existe_outra_ativa = AtividadeEntrega.objects.filter(atividade=at_e.atividade, ativo=True).exclude(id__in=ids_atividade_entrega).exists()
        return existe_outra_ativa


class ComplexidadeAtividade(models.ModelPlus):
    atividade = models.ForeignKeyPlus(Atividade)
    faixa_complexidade = models.ForeignKeyPlus(FaixaComplexidade, verbose_name='Faixa de Complexidade')

    tempo_execucao_remoto = models.DecimalFieldPlus(verbose_name='Tempo de Execução no Teletrabalho', help_text='Em horas', default=0)
    tempo_execucao_presencial = models.DecimalFieldPlus(verbose_name='Tempo de Execução no Presencial', help_text='Em horas', default=0)

    class Meta:
        verbose_name = 'Complexidade da Atividade'
        verbose_name_plural = 'Complexidades da Atividade'
        unique_together = ('atividade', 'faixa_complexidade')
        ordering = ('id',)

    def __str__(self):
        # Ficou assim para que não eja exibido no FormtSet do cadastro do admin
        return ''


class AtividadeSolicitacoes(Atividade):
    class Meta:
        verbose_name = 'Analisar Solicitação de Atividade (Cadastro e Alteração)'
        verbose_name_plural = 'Analisar Solicitações de Atividade (Cadastro e Alteração)'
        proxy = True


class SetorHabilitacao(models.ModelPlus):
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor')

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Habilitação')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Habilitação', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Setor Habilitado no Programa de Gestão'
        verbose_name_plural = 'Setores Habilitados no Programa de Gestão'

    def __str__(self):
        return str(self.setor)

    def clean(self):
        is_insert = not self.id

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos no mesmo setor
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = SetorHabilitacao.objects.filter(setor=self.setor).exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos')

        # Se for colocar data fim na habilitacao do setor,
        #   ela nao pode ter ter um data fim menor que a maior data fim de um pts nao cancelado
        if self.data_fim and PlanoTrabalhoSetorial.objects.filter(cancelado=False, data_fim__gt=self.data_fim).exists():
            raise ValidationError(
                'A data fim da habilitação deve ser maior ou igual a data fim de todos os Planos de Trabalho Setoriais não cancelados.'
            )

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        return SetorHabilitacao.objects.filter(data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False) | SetorHabilitacao.objects.filter(
            data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False
        )

    @staticmethod
    def eh_setor_vigente(setor):
        return SetorHabilitacao.get_vigentes().filter(setor=setor).exists()

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class ComissaoPGD(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros')
    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Comissão PGD'
        verbose_name_plural = 'Comissões PGD'
        permissions = (('gestao_pgd', 'Gestão PGD'),)

    def __str__(self):
        if self.data_fim:
            return f'Comissão PGD - {self.titulo} - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Comissão PGD - {self.titulo} - vigente a partir de {format_datetime(self.data_inicio)}'

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        ComissaoPGD.sincronizar_permissoes_comissao()

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        qs_ativas = ComissaoPGD.objects.filter(data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False) | ComissaoPGD.objects.filter(
            data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False
        )
        return qs_ativas

    @staticmethod
    def get_vigentes_por_user(user, sistemica=False):
        return ComissaoPGD.get_vigentes().filter(eh_sistemica=sistemica, membros__user=user).exists()

    @staticmethod
    def sincronizar_permissoes_comissao():
        comissoes_vigentes = ComissaoPGD.get_vigentes()
        membros_comissao_sistemica = set()
        membros_comissao_nao_sistemica = set()
        usuarios_grupo_comissao_sistemica = set()
        usuarios_grupo_comissao_nao_sistemica = set()
        grupo_sistemico = Group.objects.get(name='Comissão Sistêmica PGD')
        grupo_local = Group.objects.get(name='Comissão Local PGD')

        if comissoes_vigentes.exists():
            # SE TEM ALGUMA COMISSÃO VIGENTE

            # Todos que fazem parte de comissoes vigentes - Sistemica
            for comissao_vigente in comissoes_vigentes.filter(eh_sistemica=True):
                for memb in comissao_vigente.membros.all():
                    membros_comissao_sistemica.add(memb.user)

            # Todos que fazem parte de comissoes vigentes - Não Sistemica
            for comissao_vigente in comissoes_vigentes.filter(eh_sistemica=False):
                for memb in comissao_vigente.membros.all():
                    membros_comissao_nao_sistemica.add(memb.user)

            # Todos os que estao no grupo - Comissão Sistêmica PGD
            usuarios_grupo_comissao_sistemica = grupo_sistemico.user_set.all()

            # Todos os que estao no grupo - Comissão Local PGD (Não Sistemica)
            usuarios_grupo_comissao_nao_sistemica = grupo_local.user_set.all()

            # Adicionar os membros no grupo - Sistemica e Não Sistemica
            for membro in membros_comissao_sistemica:
                membro.groups.add(grupo_sistemico)
            for membro in membros_comissao_nao_sistemica:
                membro.groups.add(grupo_local)

            # Remove do grupo os que nao sao mais membros - Sistemica e Não Sistemica
            for estah_no_grupo in usuarios_grupo_comissao_sistemica:
                if estah_no_grupo not in membros_comissao_sistemica:
                    estah_no_grupo.groups.remove(grupo_sistemico)
            for estah_no_grupo in usuarios_grupo_comissao_nao_sistemica:
                if estah_no_grupo not in membros_comissao_nao_sistemica:
                    estah_no_grupo.groups.remove(grupo_local)
        else:
            # SE NÃO TEM COMISSÃO VIGENTE

            membros_comissao = set()
            for comissao in ComissaoPGD.objects.all():
                for memb in comissao.membros.all():
                    membros_comissao.add(memb.user)
            for memb in membros_comissao:
                memb.groups.remove(grupo_sistemico)
            for memb in membros_comissao:
                memb.groups.remove(grupo_local)

    @staticmethod
    def sincronizar_permissoes_comissao_membro(user):
        grupo_sistemico = Group.objects.get(name='Comissão Sistêmica PGD')
        grupo_local = Group.objects.get(name='Comissão Local PGD')

        # Comissoes vigentes que o usuário eh membro
        comissoes_vigentes_sistemica = ComissaoPGD.get_vigentes_por_user(user, sistemica=True)
        comissoes_vigentes_nao_sistemica = ComissaoPGD.get_vigentes_por_user(user, sistemica=False)

        # Se estiver em alguma comissao vigente adiciona no grupo
        # Se não estiver remove
        if comissoes_vigentes_sistemica:
            user.groups.add(grupo_sistemico)
        else:
            user.groups.remove(grupo_sistemico)
        if comissoes_vigentes_nao_sistemica:
            user.groups.add(grupo_local)
        else:
            user.groups.remove(grupo_local)

    @staticmethod
    def get_campis_comissoes_locais_vigentes_user(vinculo):
        # Retorna os campis vinculados a comissões não sistêmicas (locais) vigentes de um vinculo (user.vinculo)
        comissoes = ComissaoPGD.get_vigentes().filter(eh_sistemica=False, membros__user=vinculo.user)
        campis_ids = set()
        for comissao in comissoes:
            campis_ids.update(comissao.campus_abragencia.values_list('id', flat=True))
        return UnidadeOrganizacional.objects.filter(id__in=campis_ids)


class JustificativaDesligamentoPgd(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo?', default=True)
    servidor = models.BooleanField('Disponível para o Servidor?', default=True)
    chefe = models.BooleanField('Disponível para o Chefe?', default=True)
    qtd_dias_punicao = models.PositiveIntegerField(
        verbose_name='Quantidade de dias que o servidor não pode solicitar nova adesão após um desligamento', default=0
    )

    class Meta:
        verbose_name = 'Justificativa para Desligamento do PGD'
        verbose_name_plural = 'Justificativas para Desligamento do PGD'
        ordering = ('titulo',)

    def __str__(self):
        if not self.ativo:
            return f'{self.titulo} - (Inativo)'
        return f'{self.titulo}'

    @staticmethod
    def get_justificativas_servidor():
        return JustificativaDesligamentoPgd.objects.filter(ativo=True, servidor=True)

    @staticmethod
    def get_justificativas_chefe():
        return JustificativaDesligamentoPgd.objects.filter(ativo=True, chefe=True)

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


# ====================================================
# PTS
# ====================================================


class ConfiguracaoOrientacaoPlanoSetorial(models.ModelPlus):
    orientacao = models.TextField('Orientações')

    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Orientação sobre Plano de Trabalho Setorial'
        verbose_name_plural = 'Orientações sobre Plano de Trabalho Setorial'

    def __str__(self):
        if self.data_fim:
            return f'Orientação sobre Plano de Trabalho Setorial vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Orientação sobre Plano de Trabalho Setorial vigente a partir de {format_datetime(self.data_inicio)}'

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        return ConfiguracaoOrientacaoPlanoSetorial.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | ConfiguracaoOrientacaoPlanoSetorial.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)

    @staticmethod
    def get_vigentes_sistemico():
        vigentes = ConfiguracaoOrientacaoPlanoSetorial.get_vigentes()
        return vigentes.filter(eh_sistemica=True)

    @staticmethod
    def get_vigentes_nao_sistemico(campus):
        vigentes = ConfiguracaoOrientacaoPlanoSetorial.get_vigentes()
        return vigentes.filter(eh_sistemica=False, campus_abragencia__in=[campus])

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente


class PlanoTrabalhoSetorial(models.ModelPlus):
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor')
    atividades = models.ManyToManyFieldPlus('pgd.Atividade', verbose_name='Atividades', through='pgd.PlanoTrabalhoSetorialAtividades')
    auxiliares = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Auxiliares do Chefe no Preenchimento do Plano', blank=True)
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial do Plano')
    data_fim = models.DateFieldPlus(verbose_name='Data Final do Plano', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)
    publicado = models.BooleanField('Publicado e Aprovado', default=False)

    # Documentação do PTS
    doc_horario_funcionamento_setor = models.CharFieldPlus('Horário de funcionamento semanal do setor', null=True, blank=True)
    doc_escala_trabalho_setor = models.TextField('Escala de trabalho presencial', null=True, blank=True)
    doc_regras_planejamento_setor = models.TextField('Periodicidade e os horários de planejamento do setor', null=True, blank=True)
    doc_infraestrutura_minima = models.TextField('Infraestrutura física, material e tecnológica mínima necessária', null=True, blank=True)
    doc_cohecimento_tecnico = models.TextField('Conhecimento técnico necessário', null=True, blank=True)

    class Meta:
        verbose_name = 'Plano de Trabalho Setorial'
        verbose_name_plural = 'Planos de Trabalho Setorial'
        ordering = ('setor',)

    def __str__(self):
        if self.data_fim:
            return f'Plano de Trabalho Setorial {self.setor} vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Plano de Trabalho Setorial {self.setor} vigente a partir de {format_datetime(self.data_inicio)}'

    def get_absolute_url(self):
        return reverse_lazy('visualizar_plano_trabalho_setorial', kwargs={'pts_id': self.pk})

    def clean(self):
        is_insert = not self.id

        # Verifica se tem algum setor associado
        if not hasattr(self, 'setor') or not self.setor:
            raise ValidationError('Nenhum setor escolhido.')

        # Valida se o setor está habilitado
        if not SetorHabilitacao.eh_setor_vigente(self.setor):
            raise ValidationError('Este Setor não está habilitado para o Programa de Gestão e Desempenho.')

        # Valida se existe orientacao sistemica cadastrada
        if not ConfiguracaoOrientacaoPlanoSetorial.get_vigentes_sistemico().exists():
            raise ValidationError('A Gestão do PGD deve cadastrar a Orientação Sistêmica sobre Plano de Trabalho Setorial.')

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A Data Inicial deve ser menor ou igual a Data Final.')

        # Não permite choque entre periodos no mesmo setor
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = PlanoTrabalhoSetorial.objects.filter(setor=self.setor).exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos')

        # Se a habilitacao do Setor tiver data fim entao o PTS tambem deve ter data fim
        habilitacao = SetorHabilitacao.get_vigentes().filter(setor=self.setor).first()
        if habilitacao.data_fim and not self.data_fim:
            raise ValidationError('Este Plano deve ter Data Fim considerando a data fim da habilitação do Setor.')

        # Não pode ter vigência de PTS fora do período de habilitação setor
        if self.data_inicio and not self.estah_alinhado_com_habilitacao_setor():
            raise ValidationError('Este Plano está com período de vigência divergente do período de habilitação do Setor.')

    @admin.display(boolean=True)
    def estah_alinhado_com_habilitacao_setor(self):
        # Retorna se o plano está vigente em relação a habilitação do setor
        # - Se não tiver dentro do período de habilitação então o PTS não está vigente
        # Habilitacao 01/08/2022 a 30/08/2022
        # PTS         07/07/2022 a 29/08/2022
        # -> Retorna False pq este foi PTS cadastrado com inicio antes do periodo de habilitacao vigente do setor
        habilitacao = SetorHabilitacao.get_vigentes().filter(setor=self.setor).only('data_inicio', 'data_fim').first()
        if not habilitacao:
            return False
        periodo_habilitacao = (
            (habilitacao.data_inicio, habilitacao.data_fim) if habilitacao.data_fim else (habilitacao.data_inicio, datetime.date.today())
        )
        periodo_vigencia_pts = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
        # Se o pts inicia na mesma data ou depois do inicio da habilitacao
        if not (periodo_vigencia_pts[0] >= periodo_habilitacao[0]):
            return False
        # Se o pts finaliza na mesma data ou antes do fim da habilitacao
        return periodo_vigencia_pts[1] <= periodo_habilitacao[1]

    estah_alinhado_com_habilitacao_setor.short_description = 'Está com período alinhado com a habilitação do setor'

    # Vigente: Não Cancelado, Período Ativo, Pts tem vigência dentro da vigência da habilitação do setor
    # -------------------------------------
    @admin.display(boolean=True)
    def estah_vigente(self):
        if self.cancelado:
            return False

        hoje = datetime.date.today()

        if self.data_inicio > hoje:
            return False

        if self.data_fim and self.data_fim < hoje:
            return False

        return self.estah_alinhado_com_habilitacao_setor()

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_pts_dos_setores(setores):
        return PlanoTrabalhoSetorial.objects.filter(setor__in=setores)

    # Lista os PTSs vigentes
    # -------------------------------------
    @staticmethod
    def get_pts_vigentes():
        planos_setoriais = PlanoTrabalhoSetorial.objects.all().select_related('setor')
        vigentes_ids = []
        for pts in planos_setoriais:
            if pts.estah_vigente():
                vigentes_ids.append(pts.id)
        return PlanoTrabalhoSetorial.objects.filter(id__in=vigentes_ids)

    # Retorna o PTS vigente de um setor
    # -------------------------------------
    @staticmethod
    def get_pts_vigente_do_setor(setor):
        planos_setoriais = PlanoTrabalhoSetorial.objects.filter(setor=setor)
        vigente = None
        for pts in planos_setoriais:
            if pts.estah_vigente():
                vigente = pts
                break
        return vigente

    # Retorna o PTS vigente de um setor
    # -------------------------------------
    @staticmethod
    def get_pts_vigente_publicado_do_setor(setor):
        planos_setoriais = PlanoTrabalhoSetorial.objects.filter(setor=setor)
        vigente_publicado = None
        for pts in planos_setoriais:
            if pts.estah_vigente_publicado():
                vigente_publicado = pts
                break
        return vigente_publicado

    # Retorna se um PTS estah vigentes E publicados
    # ------------------
    def estah_vigente_publicado(self):
        return self.estah_vigente() and self.publicado

    # Lista os PTSs vigentes E publicados
    # ------------------
    @staticmethod
    def get_pts_vigentes_publicado():
        planos_setoriais = PlanoTrabalhoSetorial.get_pts_vigentes()
        planos_setoriais = planos_setoriais.filter(publicado=True)
        return planos_setoriais

    # Pega o PTS vigente E publicado para um SETOR especifico
    # ------------------
    @staticmethod
    def get_pts_vigente_publicado_setor(setor):
        planos_setoriais = PlanoTrabalhoSetorial.get_pts_vigente_publicado_do_setor(setor)
        return planos_setoriais

    # Retorna se o PTS estah apto
    # - Em Setor com habilitacao vigente E
    # - Estah vigente e Publicado
    # ------------------
    def estah_apto(self):
        eh_setor_vigente = SetorHabilitacao.eh_setor_vigente(self.setor)
        return self.estah_vigente_publicado() and eh_setor_vigente

    # Retorna o PTS apto de um Setor
    # - Eh um PTS Vigente e Publicado E
    # - Eh de um Setor com habilitacao vigente
    # ------------------
    @staticmethod
    def get_pts_apto(setor):
        pts = PlanoTrabalhoSetorial.get_pts_vigente_publicado_do_setor(setor=setor)
        if pts:
            eh_setor_vigente = SetorHabilitacao.eh_setor_vigente(pts.setor)
            if eh_setor_vigente:
                return pts
        return None

    # Retorna os PTSs aptos de um Setor
    # - Eh um PTS apto
    # ------------------
    @staticmethod
    def get_pts_aptos_dos_setores(setores):
        ids_psts_aptos = []
        for setor in setores:
            pts_apto = PlanoTrabalhoSetorial.get_pts_apto(setor)
            if pts_apto:
                ids_psts_aptos.append(pts_apto.id)

        if ids_psts_aptos:
            return PlanoTrabalhoSetorial.objects.filter(id__in=ids_psts_aptos)

        return PlanoTrabalhoSetorial.objects.none()

    def get_pts_aptos_dos_setores2(setores):
        def get_pts_vigente_publicado_do_setor(setor):
            lista = []
            planos_setoriais = PlanoTrabalhoSetorial.objects.filter(setor=setor)
            for pts in planos_setoriais:
                # Considera PTS publicados e não cancelados — inclui PTS encerrados
                if pts.publicado and not pts.cancelado:
                    lista.append(pts.id)
            return PlanoTrabalhoSetorial.objects.filter(id__in=lista)

        def get_pts_apto(setor):
            ptss = get_pts_vigente_publicado_do_setor(setor=setor)
            if ptss:
                eh_setor_vigente = SetorHabilitacao.eh_setor_vigente(ptss.first().setor)
                if eh_setor_vigente:
                    return ptss
            return None

        ids_psts_aptos = []
        for setor in setores:
            ptss_apto = get_pts_apto(setor)
            if ptss_apto:
                for p in ptss_apto:
                    ids_psts_aptos.append(p.id)

        if ids_psts_aptos:
            return PlanoTrabalhoSetorial.objects.filter(id__in=ids_psts_aptos)

        return PlanoTrabalhoSetorial.objects.none()

    # Retorna os PTSs aptos de um Servidor
    # ------------------

    @staticmethod
    def get_pts_apto_do_servidor(adesao_pgd):
        # Um PTS apto do servidor é aquele que
        # - Eh um PTS deferido do servidor de uma adesao
        # - Eh um PTS apto
        lista_ids_pts = []
        sols_deferidas = SolicitacaoAdesaoPtsServidor.get_deferidas(adesao_pgd)
        if sols_deferidas:
            for sol_deferida in sols_deferidas:
                if sol_deferida.plano_trabalho_setorial.estah_apto():
                    lista_ids_pts.append(sol_deferida.plano_trabalho_setorial.id)
            return PlanoTrabalhoSetorial.objects.filter(id__in=lista_ids_pts)
        return PlanoTrabalhoSetorial.objects.none()

    @staticmethod
    def get_pts_ativo_do_servidor(adesao_pgd):
        # Um PTS ativo do servidor de uma adesao é aquele que
        # - Eh um PTS vigente do servidor
        # - O PTS deve estar apto
        lista_ids_pts = []
        sols = SolicitacaoAdesaoPtsServidor.get_vigentes(adesao_pgd)
        if not sols:
            return None
        for sol in sols:
            if sol.plano_trabalho_setorial.estah_apto():
                lista_ids_pts.append(sol.plano_trabalho_setorial.id)
        return PlanoTrabalhoSetorial.objects.filter(id__in=lista_ids_pts)

    @staticmethod
    def pode_cadastrar(user):
        return user.has_perm('pgd.add_planotrabalhosetorial') and setores_que_sou_chefe_hoje(user.get_relacionamento()).exists()

    def pode_visualizar(self, user):
        if user.has_perm('pgd.view_planotrabalhosetorial'):
            if self.publicado:
                return True
            else:
                eh_auxiliar = self.auxiliares.filter(id=user.get_vinculo().id).exists()
                if eh_auxiliar:
                    return True

                estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
                estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
                estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD') and ComissaoPGD.get_vigentes_por_user(
                    user, sistemica=False
                )
                eh_chefe = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
                eh_meu_setor = self.setor == get_setor(user)

                if estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente or eh_chefe or eh_meu_setor:
                    return True
        return False

    def pode_editar(self, user):
        eh_auxiliar = self.auxiliares.filter(id=user.get_vinculo().id).exists()
        if eh_auxiliar:
            return True

        eh_chefe = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        return user.has_perm('pgd.change_planotrabalhosetorial') and (eh_auxiliar or eh_chefe)

    def pode_editar_vigencia(self, user):
        return not self.cancelado and self.pode_editar(user)

    def pode_editar_documentacao(self, user):
        return not self.cancelado and not self.publicado and self.pode_editar(user)

    def pode_editar_auxiliares(self, user):
        return not self.cancelado and not self.publicado and self.pode_editar(user)

    def pode_publicar(self, user):
        servidor = user.get_relacionamento()

        # Tenho que ser chefe desse setor mas não posso ser chefe direto
        # sou_chefe_direto = setores_que_sou_chefe_direto_hoje(servidor)
        # sou_chefe = setores_que_sou_chefe_hoje(servidor)
        # regra_chefia_setor = self.setor not in sou_chefe_direto and self.setor in sou_chefe
        sou_chefe = setores_que_sou_chefe_hoje(servidor)
        regra_chefia_setor = False
        if sou_chefe:
            regra_chefia_setor = self.setor in sou_chefe

        # Regras das documentacoes
        doc_horario_funcionamento_setor = self.doc_horario_funcionamento_setor
        doc_escala_trabalho_setor = None
        if self.doc_escala_trabalho_setor:
            doc_escala_trabalho_setor = strip_tags(self.doc_escala_trabalho_setor.strip().replace('&nbsp;', ''))
        #
        doc_regras_planejamento_setor = None
        if self.doc_regras_planejamento_setor:
            doc_regras_planejamento_setor = strip_tags(self.doc_regras_planejamento_setor.strip().replace('&nbsp;', ''))
        #
        doc_regras_planejamento_setor = None
        if self.doc_regras_planejamento_setor:
            doc_regras_planejamento_setor = strip_tags(self.doc_regras_planejamento_setor.strip().replace('&nbsp;', ''))
        #
        doc_infraestrutura_minima = None
        if self.doc_infraestrutura_minima:
            doc_infraestrutura_minima = strip_tags(self.doc_infraestrutura_minima.strip().replace('&nbsp;', ''))
        #
        doc_cohecimento_tecnico = None
        if self.doc_cohecimento_tecnico:
            doc_cohecimento_tecnico = strip_tags(self.doc_cohecimento_tecnico.strip().replace('&nbsp;', ''))

        doc_horario_funcionamento_setor = doc_horario_funcionamento_setor != '' and doc_horario_funcionamento_setor is not None
        doc_escala_trabalho_setor = doc_escala_trabalho_setor != '' and doc_escala_trabalho_setor is not None
        doc_regras_planejamento_setor = doc_regras_planejamento_setor != '' and doc_regras_planejamento_setor is not None
        doc_infraestrutura_minima = doc_infraestrutura_minima != '' and doc_infraestrutura_minima is not None
        doc_cohecimento_tecnico = doc_cohecimento_tecnico != '' and doc_cohecimento_tecnico is not None

        regra_se_possui_documentacao = (
            doc_horario_funcionamento_setor
            and doc_escala_trabalho_setor
            and doc_regras_planejamento_setor
            and doc_infraestrutura_minima
            and doc_cohecimento_tecnico
        )

        # Vigencia e publicado
        # Publicado para permitir que se publique um PTS sem estar vigente
        # regras_vigencia_status = self.estah_vigente() and not self.cancelado and not self.publicado
        regras_vigencia_status = not self.cancelado and not self.publicado

        # Atividades
        regra_se_possui_atividade_ativa = PlanoTrabalhoSetorialAtividades.objects.filter(plano_trabalho_setorial=self, ativo=True).exists()

        # Se setor continua habilitado
        eh_setor_vigente = SetorHabilitacao.eh_setor_vigente(self.setor)

        return (
            user.has_perm('pgd.change_planotrabalhosetorial')
            and regra_chefia_setor
            and regra_se_possui_documentacao
            and regras_vigencia_status
            and regra_se_possui_atividade_ativa
            and eh_setor_vigente
        )

    def pode_despublicar(self, user):
        regras_basicas = user.has_perm('pgd.change_planotrabalhosetorial') and self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        return not self.cancelado and self.publicado and regras_basicas

    def pode_cancelar(self, user):
        eh_chefe = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        existe_adesao_relacionada = SolicitacaoAdesaoPtsServidor.objects.filter(plano_trabalho_setorial=self).exists()
        return user.has_perm('pgd.change_planotrabalhosetorial') and not self.cancelado and eh_chefe and not existe_adesao_relacionada

    def pode_receber_solicitacao_adesao(self):
        eh_setor_vigente = SetorHabilitacao.eh_setor_vigente(self.setor)
        return self.estah_vigente() and self.publicado and eh_setor_vigente

    def pode_vincular_atividades(self, user):
        return not self.cancelado and not self.publicado and self.pode_editar(user)

    def get_atividades(self):
        return self.planotrabalhosetorialatividades_set.all().order_by(
            'atividade__tematica__titulo', 'atividade__subtematica__titulo', 'atividade__servico__titulo', 'atividade__titulo'
        )

    def get_atividades_ativas(self):
        return self.planotrabalhosetorialatividades_set.filter(ativo=True).order_by(
            'atividade__tematica__titulo', 'atividade__subtematica__titulo', 'atividade__servico__titulo', 'atividade__titulo'
        )

    def get_atividades_para_adicionar(self):
        # Atividades que podem ser adicionadas ao PTS

        querys = []

        atividades = Atividade.get_atividades_ativas()

        # Adiciona as que tiverem vinculadas a temática sem setor
        querys.append(Q(tematica__setor__isnull=True))

        # - Adiciona as vinculadas a setor que seja igual a algum (o primeiro setor superior correspondente)
        # setor superior ao do plano
        hierarquia_setores_pts = self.setor.get_caminho().copy()
        hierarquia_setores_pts.reverse()
        lista_tematicas_setor = TematicaAtividade.objects.filter(setor__isnull=False, ativo=True).values_list('setor__sigla', flat=True)
        for hierarquia in hierarquia_setores_pts:
            if hierarquia.sigla in list(lista_tematicas_setor):
                querys.append(Q(tematica__setor=hierarquia))
                break

        # Exclui atividades já vinculadas
        atividades_ja_vinculados = self.planotrabalhosetorialatividades_set.filter(ativo=True)

        # Monta query final
        atividades = atividades.filter(reduce(operator.or_, querys))
        atividades = atividades.exclude(id__in=atividades_ja_vinculados.values_list('atividade__id', flat=True))

        return atividades

    def sincrononiza_inativacao_atividades(self):
        # Inativa no PTS as atividades que estao inativas no QTA
        # ---------------------------------

        # Atividades do PTS
        atividades_pts = PlanoTrabalhoSetorialAtividades.objects.filter(plano_trabalho_setorial=self)
        ids_atividades_vinculadas = atividades_pts.values_list('atividade_id', flat=True)

        # Atividades inativas no QTA
        ids_atividades_inativas = Atividade.get_atividades_inativas().filter(id__in=ids_atividades_vinculadas).values_list('id', flat=True)

        # Inativa no PTS
        atividades_pts.filter(atividade_id__in=ids_atividades_inativas).update(ativo=False)

        return None


class PlanoTrabalhoSetorialSelecionar(PlanoTrabalhoSetorial):
    class Meta:
        verbose_name = 'Plano de Trabalho Setorial'
        verbose_name_plural = 'Planos de Trabalho Setorial'
        proxy = True


class PlanoTrabalhoSetorialAtividades(models.ModelPlus):
    SEARCH_FIELDS = ['atividade__titulo', 'atividade__tematica__titulo', 'atividade__subtematica__titulo', 'atividade__servico__titulo']

    plano_trabalho_setorial = models.ForeignKeyPlus('pgd.PlanoTrabalhoSetorial', verbose_name='Plano de Trabalho Setorial')
    atividade = models.ForeignKeyPlus('pgd.Atividade', verbose_name='Atividade')

    # modalidades_execucao = ChoiceArrayField(verbose_name='Regimes de Execução', default=ModalidadeExecucaoAtividade.get_default, base_field=models.PositiveIntegerField(choices=ModalidadeExecucaoAtividade.MODALIDADES_CHOICES))

    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        verbose_name = 'Atividade do Plano de Trabalho Setorial'
        verbose_name_plural = 'Atividades do Plano de Trabalho Setorial'
        # unique_together = ('plano_trabalho_setorial', 'atividade')
        ordering = ('atividade',)

    def __str__(self):
        return str(self.atividade)

    def pode_remover_atividade(self, user=None):
        if user and not self.plano_trabalho_setorial.pode_editar(user):
            return False

        tem_planejamento_vinculado = RelatorioIndividualTrabalhoAtividade.objects.filter(atividade_pts=self).exists()
        if tem_planejamento_vinculado:
            return False

        return not self.plano_trabalho_setorial.cancelado and not self.plano_trabalho_setorial.publicado

    def pode_ativar_atividade(self, user=None):
        if not self.atividade.estah_ativa:
            return False

        # ADD que nao pode desativar se tiver qualquer plano individual relacionado que esteja ativo
        if user and not self.plano_trabalho_setorial.pode_editar(user):
            return False

        outra_igual_ativa = (
            PlanoTrabalhoSetorialAtividades.objects.filter(plano_trabalho_setorial=self.plano_trabalho_setorial, atividade_id=self.atividade.id)
            .exclude(id=self.id)
            .exists()
        )

        return not self.ativo and not outra_igual_ativa and not self.plano_trabalho_setorial.cancelado and not self.plano_trabalho_setorial.publicado

    def pode_desativar_atividade(self, user=None):
        if not self.atividade.estah_ativa:
            return False
        if user and not self.plano_trabalho_setorial.pode_editar(user):
            return False
        return self.ativo and not self.plano_trabalho_setorial.cancelado and not self.plano_trabalho_setorial.publicado

    # def get_modalidades_display(self):
    #    return ModalidadeExecucaoAtividade.get_modalidades_display(self.modalidades_execucao)

    @staticmethod
    def get_atividades_ativas():
        return PlanoTrabalhoSetorialAtividades.objects.filter(ativo=True)


# ====================================================
# ADESÃO PGD
# ====================================================


class DocumentoAdesaoServidor(models.ModelPlus):
    descricao = models.TextField(verbose_name='Descrição')
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Documento de Regras relacionadas à Adesão do Servidor ao PGD'
        verbose_name_plural = 'Documentos de Regras relacionadas à Adesão do Servidor ao PGD'

    def __str__(self):
        if self.data_fim:
            return f'Documento de Regras relacionadas à Adesão do Servidor - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Documento de Regras Relacionadas à Adesão do Servidor - vigente a partir de {format_datetime(self.data_inicio)}'

    def clean(self):
        is_insert = not self.id

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos no mesmo setor
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = DocumentoAdesaoServidor.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos')

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigente():
        hoje = datetime.date.today()
        ativas = DocumentoAdesaoServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | DocumentoAdesaoServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)
        return ativas[0] if ativas else None

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class CategoriaServidor:
    CATEGORIA_DOCENTE = 1
    CATEGORIA_TECNICO_ADMINISTRATIVO = 2
    CHOICES_CATEGORIA = [[CATEGORIA_DOCENTE, 'Docente'], [CATEGORIA_TECNICO_ADMINISTRATIVO, 'Técnico-Administrativo']]

    @staticmethod
    def get_default():
        return [CategoriaServidor.CATEGORIA_TECNICO_ADMINISTRATIVO]

    @staticmethod
    def get_categorias_display(categorias):
        strs = []
        for m in CategoriaServidor.CHOICES_CATEGORIA:
            if m[0] in categorias:
                strs.append(m[1])
        return ' / '.join(strs)


class ConfiguracaoPerfilServidor(models.ModelPlus):
    PERFIL_TAE = 1
    PERFIL_DOCENTE = 2
    PERFIL_TAE_OU_DOCENTE = 3
    PERFIL_CHOICES = [
        [PERFIL_TAE, 'Técnico Administrativo'],
        [PERFIL_DOCENTE, 'Docente'],
        [PERFIL_TAE_OU_DOCENTE, 'Técnico Administrativo ou Docente'],
    ]

    categoria = models.PositiveIntegerField(verbose_name='Categorias', choices=PERFIL_CHOICES, default=PERFIL_TAE)
    situacoes = models.ManyToManyFieldPlus('rh.Situacao', verbose_name='Situações')
    deve_ter_funcao = models.BooleanField('Deve ter obrigatoriamente Função', default=False)
    funcoes = models.ManyToManyFieldPlus('rh.Funcao', verbose_name='Funções', blank=True)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Configuração de Perfil de Servidor para Adesão ao PGD'
        verbose_name_plural = 'Configurações de Perfil de Servidor para Adesão ao PGD'

    def __str__(self):
        if self.data_fim:
            return (
                f'Configuração de Perfil de Servidor para Adesão - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
            )
        return f'Configuração de Perfil de Servidor para Adesão - vigente a partir de {format_datetime(self.data_inicio)}'

    def clean(self):
        is_insert = not self.id

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos/categorias
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = ConfiguracaoPerfilServidor.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.id)

            if self.categoria == self.PERFIL_TAE:
                ja_salvos = ja_salvos.filter(Q(categoria=self.PERFIL_TAE) | Q(categoria=self.PERFIL_TAE_OU_DOCENTE))
            elif self.categoria == self.PERFIL_DOCENTE:
                ja_salvos = ja_salvos.filter(Q(categoria=self.PERFIL_DOCENTE) | Q(categoria=self.PERFIL_TAE_OU_DOCENTE))

            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos e/ou Categorias.')

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes(categoria=None):
        hoje = datetime.date.today()
        ativas = ConfiguracaoPerfilServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | ConfiguracaoPerfilServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)

        if categoria == ConfiguracaoPerfilServidor.PERFIL_TAE:
            ativas = ativas.filter(Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE))
        elif categoria == ConfiguracaoPerfilServidor.PERFIL_DOCENTE:
            ativas = ativas.filter(
                Q(categoria=ConfiguracaoPerfilServidor.PERFIL_DOCENTE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE)
            )

        return ativas

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente

    @staticmethod
    def checa_perfil_servidor(servidor):
        vigentes = ConfiguracaoPerfilServidor.get_vigentes()
        vigentes_taes = vigentes.filter(
            Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE)
        )
        vigentes_docentes = vigentes.filter(
            Q(categoria=ConfiguracaoPerfilServidor.PERFIL_DOCENTE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE)
        )
        vigentes_estagiarios = vigentes_taes.filter(situacoes__in=Situacao.situacoes_siape_estagiarios())

        # Estagiario
        # -----------------------------------
        if servidor.eh_estagiario:
            return vigentes_estagiarios.exists()

        # Obtem perfil vigente para TAE ou DOCENTE
        # -----------------------------------
        perfil_servidor = None
        if servidor.eh_tecnico_administrativo:
            if not vigentes_taes.exists():
                return False
            perfil_servidor = vigentes_taes[0]
        elif servidor.eh_docente:
            if not vigentes_docentes.exists():
                return False
            perfil_servidor = vigentes_docentes[0]
        else:
            return False

        # Verifica Situacao do servidor
        # -----------------------------------
        if perfil_servidor.situacoes:
            if servidor.situacao.codigo not in perfil_servidor.situacoes.values_list('codigo', flat=True):
                return False

        # Virifica funcoes do servidor
        # -----------------------------------
        servidor_tem_funcao_ativa = perfil_servidor.funcoes.exists() and servidor.historico_funcao_ativa
        # Se fo obrigatorio ter funcao e o servidor nao tiver já diz que nao pode
        if perfil_servidor.deve_ter_funcao and not servidor_tem_funcao_ativa:
            return False
        # Se o servidor tem a funcao do perfil
        if servidor_tem_funcao_ativa:
            funcoes_servidor = servidor.historico_funcao_ativa.values_list('funcao__codigo', flat=True)
            funcoes_perfil = perfil_servidor.funcoes.values_list('codigo', flat=True)
            tem_funcao_do_perfil = False
            for funcao_servidor in funcoes_servidor:
                if funcao_servidor in funcoes_perfil:
                    tem_funcao_do_perfil = True
            if not tem_funcao_do_perfil:
                return False

        return True


class SolicitacaoAdesaoServidor(models.ModelPlus):
    # Adesão ao PGD
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    documento_adesao = models.ForeignKeyPlus('pgd.DocumentoAdesaoServidor', verbose_name='Servidor')

    # CONTATO PGD
    telefone = models.BrTelefoneField(verbose_name='Telefone para Contato PGD', null=True, blank=True, max_length=15)
    PREFERENCIA_CONTATO_LIGACAO = 1
    PREFERENCIA_CONTATO_WHATS = 2
    PREFERENCIA_CONTATO_TEAMS = 3
    PREFERENCIA_CONTATO_EMAIL = 4
    PREFERENCIA_CONTATO_CHOICES = [
        [PREFERENCIA_CONTATO_LIGACAO, 'Ligação'],
        [PREFERENCIA_CONTATO_WHATS, 'WhatsApp'],
        [PREFERENCIA_CONTATO_TEAMS, 'Teams Institucional'],
        [PREFERENCIA_CONTATO_EMAIL, 'Email Institucional'],
    ]
    preferencia_contato = models.PositiveIntegerField(
        'Preferência de contato', null=True, choices=PREFERENCIA_CONTATO_CHOICES, default=PREFERENCIA_CONTATO_LIGACAO
    )

    # Outros dados
    SOLICITADO = 1
    CANCELADO_PELO_SERVIDOR = 2
    CANCELADO_PELO_AVALIADOR = 3
    DEFERIDO = 4
    INDEFERIDO = 5
    SITUACAO_SOLICITACAO_ADESAO_CHOICES = [
        [SOLICITADO, 'Solicitado e aguardando análise'],
        [CANCELADO_PELO_SERVIDOR, 'Cancelado pelo Servidor'],
        [CANCELADO_PELO_AVALIADOR, 'Cancelado pelo Avaliador'],
        [DEFERIDO, 'Deferido'],
        [INDEFERIDO, 'Indeferido'],
    ]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_SOLICITACAO_ADESAO_CHOICES)

    data_desligamento_efeitos_a_partir_de = models.DateFieldPlus('Desligamento com efeitos a partir de', null=True)
    data_desligamento_carencia_ate = models.DateFieldPlus('Desligamento com carência até', null=True)
    data_pode_solicitar_nova_adesao = models.DateFieldPlus('A partir desta data já pode solicitar nova adesão', null=True)

    class Meta:
        verbose_name = 'Adesão do Servidor ao PGD'
        verbose_name_plural = 'Adesões do Servidor ao PGD'
        permissions = (
            ('pode_gerenciar_solicitacaoadesaoservidor', 'Pode gerenciar as solicitações de adesão ao PGD'),
            ('pode_cadastrar_desligamento_pgd', 'Pode cadastrar desligamento de PGD'),
        )

    def __str__(self):
        if self.estah_deferida:
            data_inicio = format_datetime(self.get_data_inicio_adesao())
            data_fim = self.get_data_final_adesao_com_sem_desligamento()
            if data_fim:
                data_fim = format_datetime(self.get_data_final_adesao_com_sem_desligamento())
                return f'Adesão do Servidor {self.servidor} ao PGD de {data_inicio} até {data_fim}'
            return f'Adesão do Servidor {self.servidor} ao PGD de {data_inicio} até Atualidade'

        return f'Solicitação de Adesão do Servidor {self.servidor} ao PGD'

    def get_verbose_simples(self):
        if self.estah_deferida:
            data_inicio = format_datetime(self.get_data_inicio_adesao())
            data_fim = self.get_data_final_adesao_com_sem_desligamento()
            if not data_fim:
                return f'A partir de {data_inicio}'
            data_fim = format_datetime(self.get_data_final_adesao_com_sem_desligamento())
            return f'De {data_inicio} até {data_fim}'
        data = format_datetime(self.get_data_situacao_atual())
        return f'Solicitação de Adesão ao PGD {data}'

    def get_ultima_adesao_deferida(self):
        r = (
            RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao__servidor=self.servidor, solicitacao__situacao=self.DEFERIDO)
            .order_by('-id')
            .last()
        )
        if r:
            return r.solicitacao
        return None

    get_ultima_adesao_deferida.short_description = 'Data/Hora da Situação Atual'

    def get_ultima_adesao(self):
        r = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao__servidor=self.servidor).order_by('-id').last()
        if r:
            return r.solicitacao
        return None

    get_ultima_adesao.short_description = 'Data/Hora da Situação Atual'

    def get_data_situacao_atual(self):
        if self.situacao:
            r = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao=self).order_by('-id')
            if r:
                return r.last().data
        return None

    get_data_situacao_atual.short_description = 'Data/Hora da Situação Atual'

    def get_data_inicio_adesao(self):
        if self.situacao == self.DEFERIDO:
            return self.get_data_situacao_atual()
        return None

    def get_data_final_adesao(self):
        df = get_datetime_now().date()
        if self.situacao == self.DEFERIDO:
            if self.tem_desligamento_cadastrado:
                df = self.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)
        return df

    def get_data_final_adesao_com_sem_desligamento(self):
        df = None
        if self.situacao == self.DEFERIDO:
            if self.tem_desligamento_cadastrado:
                df = self.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)
        return df

    def get_adesoes_pts(self):
        return SolicitacaoAdesaoPtsServidor.objects.filter(adesao=self)

    def get_rits(self):
        return RelatorioIndividualTrabalho.get_rits_por_adesao_servidor(self)

    def get_contato_preferencia(self):
        if self.preferencia_contato == self.PREFERENCIA_CONTATO_LIGACAO:
            return mark_safe(f'{self.telefone} (Preferencialmente Ligação)')
        elif self.preferencia_contato == self.PREFERENCIA_CONTATO_WHATS:
            return mark_safe(f'{self.telefone} {self.link_whats}')
        elif self.preferencia_contato == self.PREFERENCIA_CONTATO_EMAIL:
            return mark_safe(
                f'{self.telefone} <a href="mailto:{self.servidor.email_institucional}" class="btn"><span class="fa fa-envelope" aria-hidden="true"></span> (Preferencialmente E-mail institucional</a>'
            )
        else:
            return mark_safe(f'{self.telefone} ({self.get_preferencia_contato_display()})')

    @property
    def link_whats(self):
        if self.preferencia_contato == self.PREFERENCIA_CONTATO_WHATS:
            telefone_limpo = self.telefone.replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
            return mark_safe(
                f'<a href="https://wa.me/55{telefone_limpo}" class="btn"><span class="fab fa-whatsapp" aria-hidden="true"></span> Preferencialmente WhatsApp</a></li>'
            )
        return None

    # -----------------------
    # Cadastro
    # -----------------------

    @staticmethod
    def pode_solicitar(user, retornar_lista_erros=False):
        erros = []

        servidor = user.get_relacionamento()

        perfil_servidor = None
        if servidor.eh_tecnico_administrativo:
            perfil_servidor = ConfiguracaoPerfilServidor.get_vigentes(ConfiguracaoPerfilServidor.PERFIL_TAE)
        elif servidor.eh_docente:
            perfil_servidor = ConfiguracaoPerfilServidor.get_vigentes(ConfiguracaoPerfilServidor.PERFIL_DOCENTE)

        if not DocumentoAdesaoServidor.get_vigente():
            if retornar_lista_erros:
                erros.append('Os documentos relacionados a Solicitação de Adesão ao PGD ainda não foram cadastrados pela Gestão.')
            else:
                return False, None

        if not perfil_servidor:
            if retornar_lista_erros:
                erros.append('O perfil dos Servidores aptos Solicitar de Adesão ao PGD ainda não foi cadastrado pela Gestão.')
            else:
                return False, None

        # Perfil do servidor
        if not ConfiguracaoPerfilServidor.checa_perfil_servidor(servidor):
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD o seu cadastro funcional deve ser condizente com as regras do PGD.')
            else:
                return False, None

        # Nao pode se existe outra Solicitacao
        # - nas seguintes situacoes
        #   - que ainda esta aderido
        #   - que nao esta mais aderido mas a data de "efeitos a partir de"
        #   ainda não passou em relacao a data de que está solicitando nova adesao ao PGD
        situacoes = [SolicitacaoAdesaoServidor.SOLICITADO]
        if SolicitacaoAdesaoServidor.objects.filter(servidor=servidor, situacao__in=situacoes).exists():
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD você não deve ter Solicitações "Solicitado e aguardando análise".')
            else:
                return False, None

        # Nao pode ter uma adesao vigente
        # Se o servidor estiver em período carência em algum desligamento NÃO IMPEDE DE SOLICITAR NOVA ADESÃO
        if SolicitacaoAdesaoServidor.get_vigentes(user):
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD você não deve ter solicitação vigente.')
            else:
                return False, None

        # Nega solicitacao adesao caso o servidor tenha ALGUM IMPEDIMENTO/PUNIÇÃO DE PRAZO para nova adesao
        # - se a ultima adesao dele tiver data_pode_solicitar_nova_adesao ele so pode fazer nova solicitacao apos essa data
        ultima_adesao = SolicitacaoAdesaoServidor.get_deferidas(user).order_by('-id').first()
        if ultima_adesao and ultima_adesao.data_pode_solicitar_nova_adesao:
            carencia_nova_adesao_ate = ultima_adesao.data_pode_solicitar_nova_adesao
            if get_datetime_now().date() <= carencia_nova_adesao_ate:
                if retornar_lista_erros:
                    erros.append('Impossível solicitar nova adesão. Observe o desligamento da sua última adesão.')
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    def pode_visualizar(self, user):
        quem_solicitou = self.servidor == user.get_relacionamento()
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(user.get_relacionamento()).filter(pk=self.servidor.setor_id).exists()
        return user.has_perm('pgd.view_solicitacaoadesaoservidor') and (
            quem_solicitou or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente or estah_em_gestao_pgd or eh_chefe_do_servidor
        )

    def pode_cancelar_servidor(self, user):
        quem_solicitou = self.servidor == user.get_relacionamento()
        return user.has_perm('pgd.change_solicitacaoadesaoservidor') and self.situacao == self.SOLICITADO and quem_solicitou

    def pode_cancelar_avaliador(self, user):
        estah_em_comissao_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(user.get_relacionamento()).filter(pk=self.servidor.setor_id).exists()
        quem_solicitou = self.servidor == user.get_relacionamento()
        return (
            user.has_perm('pgd.change_solicitacaoadesaoservidor')
            and self.situacao == self.SOLICITADO
            and not quem_solicitou
            and (estah_em_comissao_vigente or estah_em_gestao_pgd or eh_chefe_do_servidor)
        )

    def pode_avaliar(self, user):
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(user.get_relacionamento()).filter(pk=self.servidor.setor_id).exists()
        quem_solicitou = self.servidor == user.get_relacionamento()
        return (
            user.has_perm('pgd.change_solicitacaoadesaoservidor') and self.situacao == self.SOLICITADO and eh_chefe_do_servidor and not quem_solicitou
        )

    def pode_editar_telefone_pgd(self, user):
        quem_solicitou = self.servidor == user.get_relacionamento()
        return (
            user.has_perm('pgd.change_solicitacaoadesaoservidor')
            and self.situacao in [self.SOLICITADO, self.DEFERIDO]
            and quem_solicitou
            and self.estah_vigente
        )

    # -----------------------
    # Vigente
    # -----------------------

    @property
    def estah_deferida(self):
        # Deferida + Independente de ter desligamento ou nao
        return self.situacao == SolicitacaoAdesaoServidor.DEFERIDO

    @staticmethod
    def get_deferidas(user):
        return SolicitacaoAdesaoServidor.objects.filter(servidor=user.get_relacionamento(), situacao=SolicitacaoAdesaoServidor.DEFERIDO)

    @property
    def estah_vigente(self):
        # Vigente
        # - Deferida
        # - Nao esta desligado efetivamente
        if self.estah_deferida:
            return not self.estah_desligado
        return None

    @property
    def estah_vigente_e_na_carencia(self):
        # Vigente
        # - Deferida
        # - Nao esta desligado efetivamente OU se esta deve ta na carencia
        if self.estah_deferida:
            if self.estah_desligado:
                return self.estah_desligado_mas_ainda_na_carencia
            return True
        return None

    @staticmethod
    def get_vigentes(user):
        # Mesma regra do estah_vigente
        return SolicitacaoAdesaoServidor.get_vigentes_servidor(user.get_relacionamento())

    @staticmethod
    def get_vigentes_servidor(servidor):
        # Mesma regra do estah_vigsuaente
        sols_adesao_pgd_deferido = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor).order_by('id')
        ids = []
        for sol_adesao_pgd in sols_adesao_pgd_deferido:
            if sol_adesao_pgd.estah_vigente:
                ids.append(sol_adesao_pgd.id)
        if ids:
            return SolicitacaoAdesaoServidor.objects.filter(id__in=ids).order_by('id')
        return SolicitacaoAdesaoServidor.objects.none()

    @staticmethod
    def get_vigentes_e_na_carencia(user):
        # Mesma regra do estah_vigente_e_na_carencia
        sols_adesao_pgd_deferido = SolicitacaoAdesaoServidor.objects.filter(servidor=user.get_relacionamento()).order_by('id')
        ids = []
        for sol_adesao_pgd in sols_adesao_pgd_deferido:
            if sol_adesao_pgd.estah_vigente_e_na_carencia:
                ids.append(sol_adesao_pgd.id)
        if ids:
            return SolicitacaoAdesaoServidor.objects.filter(id__in=ids).order_by('id')
        return None

    @staticmethod
    def get_servidores_com_adesao_vigente():
        # Utiliza as mesmas regras de
        # - def estah_vigente(self)

        # Pega as adesoes vigentes
        servidores_vinculados = Servidor.objects.vinculados()
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO, servidor__in=servidores_vinculados)
        ids_adesoes_vigentes = []
        for adesao in adesoes:
            if adesao.estah_vigente:
                ids_adesoes_vigentes.append(adesao.id)

        # Servidores das adesoes
        ids_servidores = SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_vigentes).values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def get_adesoes_vigentes():
        # Utiliza as mesmas regras de
        # - def estah_vigente(self)

        # Pega as adesoes vigentes
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        ids_adesoes_vigentes = []
        for adesao in adesoes:
            if adesao.estah_vigente:
                ids_adesoes_vigentes.append(adesao.id)

        # Adesoes
        return SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_vigentes)

    @staticmethod
    def get_servidores_com_adesao_vigente_e_na_carencia():
        # Utiliza as mesmas regras de
        # - def estah_vigente_e_na_carencia(self)

        # Pega as adesoes vigentes e na carencia
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        ids_adesoes_vigentes = []
        for adesao in adesoes:
            if adesao.estah_vigente_e_na_carencia:
                ids_adesoes_vigentes.append(adesao.id)

        # Servidores das adesoes
        ids_servidores = SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_vigentes).values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def estah_no_pgd_neste_dia(servidor, data):
        # Diz se o servidor está no PGD em um determinado dia
        # - Deve ser utilizado apenas pelo ponto no relatório de frequencia
        adesoes = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor, situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        data_fim_pgd1 = get_data_fim_pgd1()
        for adesao in adesoes:
            # data_inicio = adesao.get_data_inicio_adesao().date()
            data_inicio = None
            primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(adesao)
            if primeiro_pit_adesao:
                data_inicio = primeiro_pit_adesao.get_data_inicial()
            data_final = adesao.get_data_final_adesao()
            if data_fim_pgd1 and data_final and data_final > data_fim_pgd1:
                data_final = data_fim_pgd1
            if data_inicio and data_final and (data >= data_inicio and data <= data_final):
                return True
        return False

    @staticmethod
    def periodos_estah_no_pgd(servidor):
        # - Deve ser utilizado apenas pelo ponto no relatório de frequencia
        periodos = []
        adesoes = (
            SolicitacaoAdesaoServidor.objects.select_related(
                'servidor',
            )
            .defer('documento_adesao')
            .filter(servidor=servidor, situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        )

        data_fim_pgd1 = get_data_fim_pgd1()

        for adesao in adesoes:
            # data_inicio = None
            # primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(adesao)
            # if primeiro_pit_adesao:
            #    data_inicio = primeiro_pit_adesao.get_data_inicial()

            data_inicio = adesao.primeiro_dia_pgd_nessa_adesao()
            data_final = adesao.get_data_final_adesao()
            if data_fim_pgd1 and data_final and data_final > data_fim_pgd1:
                data_final = data_fim_pgd1
            if data_inicio and data_final:
                periodos.append((data_inicio, data_final))
        return periodos

    @staticmethod
    def estah_no_pgd_hoje(servidor):
        # Diz se o servidor está no PGD HOJE
        data = get_datetime_now().date()
        adesoes = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())
        data_fim_pgd1 = get_data_fim_pgd1()
        for adesao in adesoes:
            data_inicio = None
            primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(adesao)
            if primeiro_pit_adesao:
                data_inicio = primeiro_pit_adesao.get_data_inicial()
            data_final = adesao.get_data_final_adesao()
            if data_fim_pgd1 and data_final and data_final > data_fim_pgd1:
                data_final = data_fim_pgd1
            if data_inicio and data_final and (data >= data_inicio and data <= data_final):
                return True, adesao
        return False, None

    def primeiro_dia_pgd_nessa_adesao(self):
        data_inicio = None
        primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(self)
        if primeiro_pit_adesao:
            data_inicio = primeiro_pit_adesao.get_data_inicial()
        return data_inicio

    def primeiro_dia_pgd_nessa_adesao2(self):
        data_inicio = self.get_data_inicio_adesao()
        primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(self)
        if primeiro_pit_adesao:
            data_inicio = primeiro_pit_adesao.get_data_inicial()
        return data_inicio

    def ultimo_dia_pgd_nessa_adesao(self):
        if self.tem_desligamento_cadastrado:
            return self.data_desligamento_efeitos_a_partir_de
        return None

    # -----------------------
    # Desligamento
    # -----------------------

    @property
    def tem_desligamento_cadastrado(self):
        return bool(self.data_desligamento_efeitos_a_partir_de)

    @property
    def estah_desligado(self):
        # Estah desligado se a adesao
        # - Estiver Deferida
        # - Tem desligamento cadastrado
        # - Esta desligado efetivamente quando a partir da
        #   "data_desligamento_efeitos_a_partir_de" (NAO CONSIDERA CARENCIA)
        #   - Se a data "data_desligamento_efeitos_a_partir_de" eh 10/12/2022 entao no dia 10/12/2022 o servidor ja esta desligado
        #     oficialmente.
        #   - Não considera o NAO CONSIDERA CARENCIA
        if self.estah_deferida:
            return self.tem_desligamento_cadastrado and (get_datetime_now().date() >= self.data_desligamento_efeitos_a_partir_de)
        return None

    @property
    def estah_desligado_mas_ainda_na_carencia(self):
        # Se esta DESLIGADO efetivamete mas AINDA ESTA NO PERIODO DE CARENCIA
        if self.estah_desligado:
            if self.data_desligamento_carencia_ate:
                return get_datetime_now().date() <= self.data_desligamento_carencia_ate
            return False
        return None

    @property
    def estah_desligado_mas_fora_da_carencia(self):
        # Se esta DESLIGADO efetivamete mas ja ESTA FORA DO PERIODO DE CARENCIA
        if self.estah_desligado:
            return get_datetime_now().date() > self.data_desligamento_carencia_ate
        return False

    @property
    def get_carencia_ate(self):
        if self.data_desligamento_efeitos_a_partir_de:
            if self.data_desligamento_carencia_ate:
                return self.data_desligamento_carencia_ate
            # carencia_ate = (self.data_desligamento_efeitos_a_partir_de + relativedelta(days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESA_VIGENTE))
            # return carencia_ate
        return False

    @staticmethod
    def get_servidores_com_adesao_deferida():
        # Utiliza as mesmas regras dos metodos/propriedades
        # - def get_deferidas(self)

        # Pega apenas as adesoes deferidas
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)

        # Servidores com adesao deferida
        ids_servidores = adesoes.values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def get_servidores_desligados():
        # Utiliza as mesmas regras dos metodos/propriedades
        # - def estah_desligado(self)

        # Pega apenas as adesoes que esta com desligamento efetivo
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        ids_adesoes_desligadas = []
        for adesao in adesoes:
            if adesao.estah_desligado:
                ids_adesoes_desligadas.append(adesao.id)

        # Servidores desligados
        ids_servidores = SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_desligadas).values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)


class RegistroAcaoSolicitacaoAdesaoServidor(RegistroAcaoPGD):
    TIPO_SOLICITADO = SolicitacaoAdesaoServidor.SOLICITADO
    TIPO_CANCELADO_PELO_SERVIDOR = SolicitacaoAdesaoServidor.CANCELADO_PELO_SERVIDOR
    TIPO_CANCELADO_PELO_AVALIADOR = SolicitacaoAdesaoServidor.CANCELADO_PELO_AVALIADOR
    TIPO_DEFERIDO = SolicitacaoAdesaoServidor.DEFERIDO
    TIPO_INDEFERIDO = SolicitacaoAdesaoServidor.INDEFERIDO
    TIPO_DESLIGAMENTO = 6
    TIPO_DESLIGAMENTO_CANCELADO = 7

    TIPO_CHOICES = (
        (TIPO_SOLICITADO, SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_SOLICITADO - 1][1]),
        (TIPO_CANCELADO_PELO_SERVIDOR, SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_SERVIDOR - 1][1]),
        (TIPO_CANCELADO_PELO_AVALIADOR, SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_AVALIADOR - 1][1]),
        (TIPO_DEFERIDO, SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_DEFERIDO - 1][1]),
        (TIPO_INDEFERIDO, SolicitacaoAdesaoServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_INDEFERIDO - 1][1]),
        (TIPO_DESLIGAMENTO, 'Desligamento cadastrado'),
        (TIPO_DESLIGAMENTO_CANCELADO, 'Desligamento Cancelado'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    solicitacao = models.ForeignKeyPlus('pgd.SolicitacaoAdesaoServidor', editable=False, null=True)


class ParticipantesPgd(SolicitacaoAdesaoServidor):
    class Meta:
        verbose_name = 'Participante PGD'
        verbose_name_plural = 'Participantes PGD'
        proxy = True


class DesligamentoPgdServidor(models.ModelPlus):
    # Solicitacoes de desligamento do PGD

    adesao = models.ForeignKeyPlus('pgd.SolicitacaoAdesaoServidor', verbose_name='Adesão')
    justificativa = models.ForeignKeyPlus('pgd.JustificativaDesligamentoPgd', verbose_name='Justificativa')
    observacao = models.TextField('Observações')

    data_desligamento_efeitos_a_partir_de = models.DateFieldPlus('Desligamento com efeitos a partir de', null=True)
    data_pode_solicitar_nova_adesao = models.DateFieldPlus('A partir desta data já pode solicitar nova adesão', null=True)

    data_cadastro = models.DateTimeFieldPlus('Data do cadastro', auto_now_add=True, editable=False)
    usuario_cadastro = models.CurrentUserField(editable=False, related_name='desligamento_usuario_cadastro')

    data_cancelamento = models.DateFieldPlus('Desligamento cancelado', null=True)

    class Meta:
        verbose_name = 'Desligamento do PGD'
        verbose_name_plural = 'Desligamentos do PGD'

    def __str__(self):
        return f'Desligamento PGD do Servidor {self.adesao.servidor} do PGD {self.adesao.get_data_situacao_atual()}'

    @staticmethod
    def perfil_user_estah_cadastrando(user, adesao):
        # User: quem esta cadastrando o Desligamento

        # Qual tipo de user que esta cadastrando
        # - servidor da adesao
        # - chefe

        servidor_cadastro_desligamento = user.get_relacionamento()
        servidor_desligamento = adesao.servidor
        eh_servidor_da_adesao = servidor_desligamento == servidor_cadastro_desligamento
        if eh_servidor_da_adesao:
            return 'servidor'

        eh_chefe_do_servidor = False
        setores_chefe = setores_que_sou_chefe_hoje(servidor_cadastro_desligamento)
        if setores_chefe:
            eh_chefe_do_servidor = setores_chefe.filter(pk=servidor_desligamento.setor_id).exists()
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        if eh_chefe_do_servidor or estah_em_comissao_sistemica_vigente or estah_em_gestao_pgd:
            return 'chefe'

        return None

    @staticmethod
    def user_pode_cadastrar(user, adesao, retornar_lista_erros=False):
        # User: quem esta cadastrando o Desligamento
        # adesao.servidor: Adesao do Servidor que sera Desligado

        erros = []

        # Se o user pode cadastrar esse desligamento
        perfil_user_estah_cadastrando = DesligamentoPgdServidor.perfil_user_estah_cadastrando(user, adesao)
        if not perfil_user_estah_cadastrando:
            if retornar_lista_erros:
                erros.append(
                    'Para cadastrar o desligamento você deve ser chefe do servidor vinculado a adesão que se deseja cadastrar o desligamento ou o próprio servidor da vinculado a adesão que deseja cadastrar o desligamento.'
                )
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_iniciar_cadastro(user, adesao, retornar_lista_erros=False):
        # User: quem esta cadastrando o Desligamento
        # adesao.servidor: Adesao do Servidor que sera Desligado

        erros = []

        # Valida se pode iniciar o cadastro
        # -------------------------------------
        if not user.has_perm('pgd.pode_cadastrar_desligamento_pgd'):
            if retornar_lista_erros:
                erros.append('Você não tem permissão para iniciar cadastro de desligamento de PGD.')
            else:
                return False, None

        # Quem estah cadastrando tem que ser o servidor da adesao
        # OU Se for chefe deve ser o chefe do servidor da adesao
        user_pode_cadastrar, user_pode_cadastrar_erros = DesligamentoPgdServidor.user_pode_cadastrar(user, adesao, retornar_lista_erros=False)
        if not user_pode_cadastrar:
            if retornar_lista_erros:
                erros += user_pode_cadastrar_erros
            else:
                return False, None

        # A adesao tem que estar vigente
        if not adesao.estah_vigente:
            if retornar_lista_erros:
                erros.append('A adesão deve estar vigente.')
            else:
                return False, None

        # Nao pode cadastrar se tiver outra cadastrada
        # - Nao pode se tiver outra cadastrada sem ter desligamento
        if DesligamentoPgdServidor.objects.filter(adesao=adesao, data_cancelamento__isnull=True).exists():
            if retornar_lista_erros:
                erros.append('Não pode desligamento com outra cadastrada.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_cadastrar(user, adesao, retornar_lista_erros=False, data_desligamento_efeitos_a_partir_de=None):
        # User: quem esta cadastrando o Desligamento
        # adesao.servidor: Adesao do Servidor que sera Desligado

        erros = []

        # Valida se pode iniciar o cadastro
        # -------------------------------------
        if not user.has_perm('pgd.pode_cadastrar_desligamento_pgd'):
            if retornar_lista_erros:
                erros.append('Você não tem permissão para iniciar cadastro de desligamento de PGD.')
            else:
                return False, None

        # Quem estah cadastrando tem que ser o servidor da adesao
        # OU Se for chefe deve ser o chefe do servidor da adesao
        user_pode_cadastrar, user_pode_cadastrar_erros = DesligamentoPgdServidor.user_pode_cadastrar(user, adesao, retornar_lista_erros=False)
        if not user_pode_cadastrar:
            if retornar_lista_erros:
                erros += user_pode_cadastrar_erros
            else:
                return False, None

        # A adesao tem que estar vigente
        if not adesao.estah_vigente:
            if retornar_lista_erros:
                erros.append('A adesão deve estar vigente.')
            else:
                return False, None

        # Nao pode cadastrar se tiver outra cadastrada
        # - Nao pode se tiver outra cadastrada sem ter desligamento
        if DesligamentoPgdServidor.objects.filter(adesao=adesao, data_cancelamento__isnull=True).exists():
            if retornar_lista_erros:
                erros.append('Não pode desligamento com outra cadastrada.')
            else:
                return False, None

        # Validacoes (data de efeito) se pode finalizar um cadastro já iniciado
        # -------------------------------------
        if data_desligamento_efeitos_a_partir_de:
            # Deve ser igual ou posterior a data desta adesao
            if not (data_desligamento_efeitos_a_partir_de >= adesao.get_data_inicio_adesao().date()):
                if retornar_lista_erros:
                    erros.append('Impossível cadastrar Desligamento com data de efeitos para uma data igual ou antes do início da adesão.')
                else:
                    return False, None

            # Qualquer RIT que finalize no dia ou após a data de efeito nao pode estar homologado no momento do cadastro de desligamento
            rits_homologados = RelatorioIndividualTrabalho.get_rits_homologados(adesao)
            if rits_homologados:
                for rit in rits_homologados:
                    if rit.get_data_final() >= data_desligamento_efeitos_a_partir_de:
                        if retornar_lista_erros:
                            erros.append(
                                'Impossível cadastrar Desligamento caso exista algum RIT homologado que finalize no dia ou após a data de efeito.'
                            )
                            break
                        else:
                            return False, None

        if erros:
            return False, erros

        return True, None

    def pode_visualizar(self, user):
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        eh_chefe_setor_do_servidor_da_adesao = setores_que_sou_chefe_hoje(user.get_relacionamento()).filter(pk=self.adesao.servidor.setor_id).exists()

        return user.has_perm('pgd.view_desligamentopgdservidor') and (
            quem_solicitou or estah_em_comissao_sistemica_vigente or estah_em_gestao_pgd or eh_chefe_setor_do_servidor_da_adesao
        )

    def pode_cancelar(self, user=None):
        if self.data_cancelamento:
            return False
        pode_pela_data = False
        if self.data_desligamento_efeitos_a_partir_de and (get_datetime_now().date() < self.data_desligamento_efeitos_a_partir_de):
            pode_pela_data = True
        if not pode_pela_data:
            return False
        if user:
            user_pode, _ = DesligamentoPgdServidor.user_pode_cadastrar(user, self.adesao, retornar_lista_erros=False)
            return bool(user_pode)
        return True


# ====================================================
# ADESÃO PTS
# ====================================================


class DocumentoAdesaoPtsServidor(models.ModelPlus):
    descricao = models.TextField(verbose_name='Descrição')
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Documento de Regras relacionadas à Adesão do Servidor a um PTS'
        verbose_name_plural = 'Documentos de Regras relacionadas à Adesão do Servidor a um PTS'

    def __str__(self):
        if self.data_fim:
            return f'Documento de Regras relacionadas à Adesão do Servidor a um PTS - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Documento de Regras Relacionadas à Adesão do Servidor a um PTS - vigente a partir de {format_datetime(self.data_inicio)}'

    def clean(self):
        is_insert = not self.id

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos no mesmo setor
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = DocumentoAdesaoPtsServidor.objects.exclude(cancelado=True)
            if not is_insert:
                ja_salvos = ja_salvos.exclude(id=self.id)
            for ja_salvo in ja_salvos:
                lista_periodos.append(
                    (ja_salvo.data_inicio, ja_salvo.data_fim) if ja_salvo.data_fim else (ja_salvo.data_inicio, datetime.date.today())
                )
            este = (self.data_inicio, self.data_fim) if self.data_fim else (self.data_inicio, datetime.date.today())
            if lista_periodos and ha_choque_de_periodo(lista_periodos, este):
                raise ValidationError('Há choque de períodos.')

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigente():
        hoje = datetime.date.today()
        ativas = DocumentoAdesaoPtsServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | DocumentoAdesaoPtsServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)
        return ativas[0] if ativas else None

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class SolicitacaoAdesaoPtsServidor(models.ModelPlus):
    adesao = models.ForeignKeyPlus('pgd.SolicitacaoAdesaoServidor', verbose_name='Adesão')
    plano_trabalho_setorial = models.ForeignKeyPlus('pgd.PlanoTrabalhoSetorial', verbose_name='Plano de Trabalho Setorial')
    documento_adesao = models.ForeignKeyPlus('pgd.DocumentoAdesaoPtsServidor', verbose_name='Servidor', null=True)

    SOLICITADO = 1
    CANCELADO_PELO_SERVIDOR = 2
    CANCELADO_PELO_AVALIADOR = 3
    DEFERIDO = 4
    INDEFERIDO = 5
    SITUACAO_SOLICITACAO_ADESAO_CHOICES = [
        [SOLICITADO, 'Solicitado e aguardando análise'],
        [CANCELADO_PELO_SERVIDOR, 'Cancelado pelo Servidor'],
        [CANCELADO_PELO_AVALIADOR, 'Cancelado pelo Avaliador'],
        [DEFERIDO, 'Deferido'],
        [INDEFERIDO, 'Indeferido'],
    ]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_SOLICITACAO_ADESAO_CHOICES)

    data_desligamento = models.DateFieldPlus('Data de desligamento', null=True)

    class Meta:
        verbose_name = 'Adesão do Servidor ao PTS'
        verbose_name_plural = 'Adesões do Servidor a um PTS'
        permissions = (('pode_cadastrar_desligamento_pts', 'Pode cadastrar desligamento de PTS'),)

    def __str__(self):
        if self.situacao == self.DEFERIDO:
            return f'Adesão do Servidor {self.adesao.servidor} ao PTS {self.plano_trabalho_setorial}'
        return f'Solicitação de Adesão do Servidor {self.adesao.servidor} ao PTS {self.plano_trabalho_setorial}'

    @staticmethod
    def pode_solicitar(user, setor, adesao_pgd, retornar_lista_erros=False):
        # Setor: setor que deseja aderir
        erros = []

        servidor = user.get_relacionamento()

        documento_vigente = DocumentoAdesaoPtsServidor.get_vigente()
        if not documento_vigente:
            if retornar_lista_erros:
                erros.append('A gestão deve cadastrar o Documento de Regras relacionadas à Adesão do Servidor a um PTS.')
            else:
                return False, None

        # Tem que ter vigente (se for desligado precisa ta na carencia)
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_e_na_carencia(user)
        if not adesoes_pgd:
            if retornar_lista_erros:
                erros.append(
                    'Para solicitar adesão ao PTS você deve ter uma adesão vigente ao PGD. Se houver desligamento para adesão selecionada é necessário ainda estar na carência'
                )
            else:
                return False, None
        if adesao_pgd:
            if not adesao_pgd.estah_vigente_e_na_carencia:
                if retornar_lista_erros:
                    erros.append(
                        'Para solicitar adesão ao PTS você deve selecionar uma adesão vigente ao PGD. Se houver desligamento para adesão selecionada é necessário ainda estar na carência'
                    )
                else:
                    return False, None

        # O setor deve ter um PTS vigente e apto a receber solicitacao de adesao a PTS
        pts_apto = PlanoTrabalhoSetorial.get_pts_apto(setor)
        if not pts_apto:
            if retornar_lista_erros:
                erros.append(
                    'Para solicitar adesão ao PTS o Setor deve ter um Plano de Trabalho Setorial vigente e apto a receber solicitações de adesão.'
                )
            else:
                return False, None

        if adesao_pgd:
            # Se o setor for diferente do dele ele só pode aderir se tiver aderido do dele
            # - Para aderir a um PTS de outro setor (setor diferente do setor SUAP do servidor) ele deve ter adesão ao setor suap dele
            adesao_pts_vigente_para_o_setor = None
            adesao_pts_vigente = SolicitacaoAdesaoPtsServidor.get_vigentes(adesao_pgd)
            if adesao_pts_vigente:
                adesao_pts_vigente_para_o_setor = adesao_pts_vigente.filter(plano_trabalho_setorial__setor=servidor.setor).exists()
            if pts_apto and (servidor.setor != pts_apto.setor) and (not adesao_pts_vigente_para_o_setor):
                if retornar_lista_erros:
                    erros.append('Para solicitar adesão a um PTS de outro setor é necessário que já tenha aderido ao PTS do seu setor.')
                else:
                    return False, None

        # Se existe outra Solicitacao (SOLICITADO OU DEFERIDO [Nao desligada]) para Setor do PTS desejado
        # - Então não pode solicitar
        if pts_apto and adesao_pgd:
            situacoes = [SolicitacaoAdesaoPtsServidor.SOLICITADO, SolicitacaoAdesaoPtsServidor.DEFERIDO]
            if (
                SolicitacaoAdesaoPtsServidor.objects.filter(adesao=adesao_pgd, plano_trabalho_setorial=pts_apto, situacao__in=situacoes)
                .exclude(data_desligamento__isnull=False)
                .exists()
            ):
                if retornar_lista_erros:
                    erros.append(
                        'Para solicitar adesão a este PTS você não pode ter outras solicitação como "Solicitado e aguardando análise" ou "Deferido" para este PTS considerando a adesão selecionada.'
                    )
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    def pode_visualizar(self, user):
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        eh_chefe_setor_plano_trabalho_setorial = self.plano_trabalho_setorial.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())

        return user.has_perm('pgd.view_solicitacaoadesaoptsservidor') and (
            quem_solicitou
            or estah_em_comissao_sistemica_vigente
            or estah_em_comissao_local_vigente
            or estah_em_gestao_pgd
            or eh_chefe_setor_plano_trabalho_setorial
        )

    def pode_cancelar_servidor(self, user):
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        return user.has_perm('pgd.change_solicitacaoadesaoptsservidor') and self.situacao == self.SOLICITADO and quem_solicitou

    def pode_cancelar_avaliador(self, user):
        estah_em_comissao_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        eh_chefe_setor_plano_trabalho_setorial = self.plano_trabalho_setorial.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        return (
            user.has_perm('pgd.change_solicitacaoadesaoptsservidor')
            and self.situacao == self.SOLICITADO
            and not quem_solicitou
            and (estah_em_comissao_vigente or estah_em_gestao_pgd or eh_chefe_setor_plano_trabalho_setorial)
        )

    def pode_avaliar(self, user):
        eh_chefe_setor_plano_trabalho_setorial = self.plano_trabalho_setorial.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()

        # Se o setor da solicitacao (que está o pts associado a esta solicitacao) tem PTS vigente
        pts_apto = PlanoTrabalhoSetorial.get_pts_apto(self.plano_trabalho_setorial.setor)

        return (
            user.has_perm('pgd.change_solicitacaoadesaoptsservidor')
            and self.situacao == self.SOLICITADO
            and not quem_solicitou
            and eh_chefe_setor_plano_trabalho_setorial
            and pts_apto
        )

    @property
    def estah_desligado(self):
        # Estah desligado
        # - Solicitacao estah deferida
        # - Existe cadastro de desligamento para a solicitacao
        # - Se a data de hoje for >= a data_desligamento
        if self.situacao == self.DEFERIDO:
            return bool(self.data_desligamento)
        return None

    def pode_cadastrar_desligamento_servidor(self, user):
        # Servidor ou Chefe podem cadastrar

        # ------------------------
        # Regras basicas
        # ------------------------
        # Se eh servidor da adesão ou chefe do setor do referido PTS
        user_pode = True
        eh_chefe_setor_plano_trabalho_setorial = self.plano_trabalho_setorial.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        if not (eh_chefe_setor_plano_trabalho_setorial or quem_solicitou):
            user_pode = False

        # Se pode pela situacao
        pode_pela_situacao = self.situacao == self.DEFERIDO

        # Regras basicas
        regras_basicas = (
            (user.has_perm('pgd.pode_cadastrar_desligamento_pts')) and (user_pode) and (pode_pela_situacao) and (not self.estah_desligado)
        )
        if not regras_basicas:
            return False

        # ------------------------
        # Outras regras
        # ------------------------
        # Se o servidor esta desligado da adesao PGD relacionada ele pode cadastrar desligamento APENAS SE TIVER NA CARENCIA
        # - Se tiver desligado fora da carencia nao pode
        if self.adesao.estah_desligado and self.adesao.estah_desligado_mas_fora_da_carencia:
            return False

        # Nao pode para o setor dele
        return self.adesao.servidor.setor != self.plano_trabalho_setorial.setor

    @staticmethod
    def get_deferidas(adesao_pgd):
        # Retorna as adesões Deferidas
        # - Que foi solicitada pelo servidor e foi deferida
        return SolicitacaoAdesaoPtsServidor.objects.filter(adesao=adesao_pgd, situacao=SolicitacaoAdesaoPtsServidor.DEFERIDO)

    @staticmethod
    def get_vigentes(adesao_pgd):
        # Retorna as adesões Vigentes
        # - Deferidas
        # - Que que ainda nao esta desligado
        deferidas = SolicitacaoAdesaoPtsServidor.get_deferidas(adesao_pgd)
        if deferidas:
            return deferidas.filter(data_desligamento__isnull=True)
        return None

    def esta_vigente(self):
        # Esta vigente se
        # - Esta Deferida
        # - Nao tem data de desligamento
        if self.situacao == self.DEFERIDO:
            return not self.data_desligamento
        return None

    def get_data_situacao_atual(self):
        if self.situacao:
            r = RegistroAcaoSolicitacaoAdesaoPtsServidor.objects.filter(solicitacao=self).order_by('-id')
            if r:
                return r.last().data
        return None

    get_data_situacao_atual.short_description = 'Data/Hora da Situação Atual'


class RegistroAcaoSolicitacaoAdesaoPtsServidor(RegistroAcaoPGD):
    TIPO_SOLICITADO = SolicitacaoAdesaoPtsServidor.SOLICITADO
    TIPO_CANCELADO_PELO_SERVIDOR = SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_SERVIDOR
    TIPO_CANCELADO_PELO_AVALIADOR = SolicitacaoAdesaoPtsServidor.CANCELADO_PELO_AVALIADOR
    TIPO_DEFERIDO = SolicitacaoAdesaoPtsServidor.DEFERIDO
    TIPO_INDEFERIDO = SolicitacaoAdesaoPtsServidor.INDEFERIDO
    TIPO_DESLIGAMENTO = 6

    TIPO_CHOICES = (
        (TIPO_SOLICITADO, SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_SOLICITADO - 1][1]),
        (TIPO_CANCELADO_PELO_SERVIDOR, SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_SERVIDOR - 1][1]),
        (TIPO_CANCELADO_PELO_AVALIADOR, SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_AVALIADOR - 1][1]),
        (TIPO_DEFERIDO, SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_DEFERIDO - 1][1]),
        (TIPO_INDEFERIDO, SolicitacaoAdesaoPtsServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_INDEFERIDO - 1][1]),
        (TIPO_DESLIGAMENTO, 'Desligamento do PTS'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    solicitacao = models.ForeignKeyPlus('pgd.SolicitacaoAdesaoPtsServidor', editable=False, null=True)


# ====================================================
# PIT
# ====================================================


class ConfiguracaoOrientacaoPit(models.ModelPlus):
    orientacao = models.TextField('Orientações')

    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus('rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Orientação sobre Plano Individual de Trabalho'
        verbose_name_plural = 'Orientações sobre Plano Individual de Trabalho'

    def __str__(self):
        if self.data_fim:
            return f'Orientação sobre Plano Individual de Trabalho vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Orientação sobre Plano Individual de Trabalho vigente a partir de {format_datetime(self.data_inicio)}'

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        return ConfiguracaoOrientacaoPit.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | ConfiguracaoOrientacaoPit.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)

    @staticmethod
    def get_vigentes_sistemico():
        vigentes = ConfiguracaoOrientacaoPit.get_vigentes()
        return vigentes.filter(eh_sistemica=True)

    @staticmethod
    def get_vigentes_nao_sistemico(campus):
        vigentes = ConfiguracaoOrientacaoPit.get_vigentes()
        return vigentes.filter(eh_sistemica=False, campus_abragencia__in=[campus])

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente


class PeriodoPitRit(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    ano = models.ForeignKeyPlus('comum.Ano', verbose_name='Ano')
    cancelado = models.BooleanField('Cancelado', default=False)

    preencher_questionario_pesquisa = models.BooleanField('Solicitar preenchimento do questionário de pesquisa', default=False)

    # -------------------------------
    # PIT
    # -------------------------------
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência do PIT')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência do PIT')

    # -------------------------------
    # RIT 1
    # -------------------------------
    rit_data_inicio_1 = models.DateFieldPlus(verbose_name='Data Inicial da Vigência do RIT 1 deste período')
    rit_data_fim_1 = models.DateFieldPlus(verbose_name='Data Final da Vigência do RIT 1 deste período')

    # -------------------------------
    # RIT 2
    # -------------------------------
    rit_data_inicio_2 = models.DateFieldPlus(
        verbose_name='Data Inicial da Vigência do RIT 2 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )
    rit_data_fim_2 = models.DateFieldPlus(
        verbose_name='Data Final da Vigência do RIT 2 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )

    # -------------------------------
    # RIT 3
    # -------------------------------
    rit_data_inicio_3 = models.DateFieldPlus(
        verbose_name='Data Inicial da Vigência do RIT 3 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )
    rit_data_fim_3 = models.DateFieldPlus(
        verbose_name='Data Final da Vigência do RIT 3 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )

    # -------------------------------
    # RIT 4
    # -------------------------------
    rit_data_inicio_4 = models.DateFieldPlus(
        verbose_name='Data Inicial da Vigência do RIT 4 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )
    rit_data_fim_4 = models.DateFieldPlus(
        verbose_name='Data Final da Vigência do RIT 4 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )

    # -------------------------------
    # RIT 5
    # -------------------------------
    rit_data_inicio_5 = models.DateFieldPlus(
        verbose_name='Data Inicial da Vigência do RIT 5 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )
    rit_data_fim_5 = models.DateFieldPlus(
        verbose_name='Data Final da Vigência do RIT 5 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )

    # -------------------------------
    # RIT 5
    # -------------------------------
    rit_data_inicio_6 = models.DateFieldPlus(
        verbose_name='Data Inicial da Vigência do RIT 6 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )
    rit_data_fim_6 = models.DateFieldPlus(
        verbose_name='Data Final da Vigência do RIT 6 deste período',
        null=True,
        blank=True,
        help_text='Preencher apenas se este RIT for necessário para este PIT',
    )

    class Meta:
        verbose_name = 'Calendário de PIT/RIT'
        verbose_name_plural = 'Calendários de PIT/RIT'

    def __str__(self):
        if self.data_fim:
            return f'Calendário de PIT/RIT de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Calendário de PIT/RIT a partir de {format_datetime(self.data_inicio)}'

    def get_verbose_periodo(self):
        if self.data_fim:
            return f'{format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return format_datetime(self.data_inicio)

    def clean(self):
        # Só altera algo se não existe nada vinculado a ele
        if self.pk and PlanoIndividualTrabalho.objects.filter(periodo_pit_rit=self).exists():
            raise ValidationError('Impossível alterar o calendário se tiver algum PIT relacionado a ele.')

        datas_iniciais_pit_rit, datas_finais_pit_rit, datas_iniciais_rit, datas_finais_rit = self.get_datas_calendario_pit_rit()

        # Garante que cada cada inicial (se houver) será menor igual a final do PIT
        # --------------------------
        for i in range(len(datas_iniciais_pit_rit)):
            if datas_iniciais_pit_rit[i] and datas_finais_pit_rit[i]:
                # Necessário preencher as duas datas
                if not (datas_iniciais_pit_rit[i] and datas_finais_pit_rit[i]):
                    raise ValidationError('É necessário preencher todas as datas de iniciais e finais.')
                # A data inicial tem que ser menor/igual a data final
                if not (datas_iniciais_pit_rit[i] <= datas_finais_pit_rit[i]):
                    raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Valida RIT
        # --------------------------
        lista_periodos_rit = []
        for i in range(len(datas_iniciais_rit)):
            if datas_iniciais_rit[i] and datas_finais_rit[i]:
                lista_periodos_rit.append((datas_iniciais_rit[i], datas_finais_rit[i]))

        # Garante que as datas do RIT estejam dentro da faixa de data (inicio e final) do PIT
        periodo_pit = (self.data_inicio, self.data_fim)
        for periodo_rit in lista_periodos_rit:
            if not (periodo_rit[0] >= periodo_pit[0] and periodo_rit[1] <= periodo_pit[1]):
                raise ValidationError('As datas do RIT devem estar dentro da data de início e fim do PIT')

        # Garante que as datas do RIT estejam em sequencia
        if len(lista_periodos_rit) > 1:
            erro = False
            i = 1
            while i < len(lista_periodos_rit):
                if not (lista_periodos_rit[i - 1][1] < lista_periodos_rit[i][0]):
                    erro = True
                    break
                i += 1
            if erro:
                raise ValidationError('As datas de início e final do RIT devem estar sequência')

    def get_datas_calendario_pit_rit(self):
        datas_iniciais_rit = [
            self.rit_data_inicio_1,
            self.rit_data_inicio_2,
            self.rit_data_inicio_3,
            self.rit_data_inicio_4,
            self.rit_data_inicio_5,
            self.rit_data_inicio_6,
        ]
        datas_finais_rit = [
            self.rit_data_fim_1,
            self.rit_data_fim_2,
            self.rit_data_fim_3,
            self.rit_data_fim_4,
            self.rit_data_fim_5,
            self.rit_data_fim_6,
        ]
        datas_iniciais_pit_rit = [self.data_inicio, *datas_iniciais_rit]
        datas_finais_pit_rit = [self.data_fim, *datas_finais_rit]
        return datas_iniciais_pit_rit, datas_finais_pit_rit, datas_iniciais_rit, datas_finais_rit

    def get_periodos_calendario_rit(self):
        _, _, datas_iniciais_rit, datas_finais_rit = self.get_datas_calendario_pit_rit()
        lista_periodos_rit = []
        for i in range(len(datas_iniciais_rit)):
            if datas_iniciais_rit[i] and datas_finais_rit[i]:
                lista_periodos_rit.append((datas_iniciais_rit[i], datas_finais_rit[i]))
        return lista_periodos_rit

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado:
            hoje = datetime.date.today()
            if self.data_inicio > hoje:
                return False
            return not self.data_fim or self.data_fim >= hoje
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigente():
        hoje = datetime.date.today()
        p = PeriodoPitRit.objects.filter(data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False) | PeriodoPitRit.objects.filter(
            data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False
        )
        return p.first()

    @staticmethod
    def get_vigente_para_data(data):
        p = PeriodoPitRit.objects.filter(data_inicio__lte=data, data_fim__gte=data, cancelado=False) | PeriodoPitRit.objects.filter(
            data_inicio__lte=data, data_fim__isnull=True, cancelado=False
        )
        return p.first()

    @staticmethod
    def pode_cadastrar_alterar(user):
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        return estah_em_gestao_pgd or estah_em_comissao_sistemica_vigente


class PlanoIndividualTrabalho(models.ModelPlus):
    # Tempo adicional que um PIT/RIT pode ser editado quando a Adesão (já desligada) relacionada extrapolou a data de efeitos do desligamento
    CARENCIA_PARA_EDICAO_PIT_SEM_ADESA_VIGENTE = 365

    adesao = models.ForeignKeyPlus('pgd.SolicitacaoAdesaoServidor', verbose_name='Adesão do Servidor', editable=False)

    periodo_pit_rit = models.ForeignKeyPlus('pgd.PeriodoPitRit', verbose_name='Período PIT/RIT', editable=False)
    data_inicial = models.DateFieldPlus(verbose_name='Data Inicial', null=True, blank=True)

    percentual_presencial = models.DecimalFieldPlus(verbose_name='% de Presencial (em horas)', default=0)
    percentual_teletrabalho = models.DecimalFieldPlus(verbose_name='% de Teletrabalho (em horas)', default=0)

    CADASTRADO = 1
    AGUARDANDO_PARECER = 2
    CANCELADO_PELO_SERVIDOR = 3
    CANCELADO_PELO_AVALIADOR = 4
    AUTORIZADO = 5
    SITUACAO_PIT_CHOICES = [
        [CADASTRADO, 'Cadastrado'],
        [AGUARDANDO_PARECER, 'Aguardando parecer'],
        [CANCELADO_PELO_SERVIDOR, 'Cancelado pelo Servidor'],
        [CANCELADO_PELO_AVALIADOR, 'Cancelado pelo Avaliador'],
        [AUTORIZADO, 'Autorizado pelo(s) Avaliador(es)'],
    ]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_PIT_CHOICES)
    em_edicao = models.BooleanField('Modo edição', default=True)
    em_edicao_por = models.ForeignKeyPlus('comum.User', null=True, blank=True, editable=False)

    data_verificacao_ponto = models.DateFieldPlus(verbose_name='Data de Verificação do Ponto', null=True, blank=True)

    # Quando todos os RITS vinculados forem Homologados de forma definitiva
    # - Marcado automaticamente
    homologado_definitivo = models.BooleanField('Homologado', default=False)

    # Calculado pelo SUAP - Consolidado
    # ----------------------------------------
    # Tempo previsto de trabalho em horas. Vem do ponto de acordo com o periodo e o calendario
    tempo_previsto = models.DecimalFieldPlus(verbose_name='Tempo previsto', help_text='Em horas', default=0)
    tempo_planejado_cadastrado = models.DecimalFieldPlus(verbose_name='Tempo previsto cadastrado', help_text='Em horas', default=0)
    tempo_planejado_autorizado = models.DecimalFieldPlus(verbose_name='Tempo previsto autorizado', help_text='Em horas', default=0)
    tempo_planejado_cancelado = models.DecimalFieldPlus(verbose_name='Tempo previsto cancelado', help_text='Em horas', default=0)
    # Tempo total planejado somando todos os RITs vinculados
    tempo_planejado = models.DecimalFieldPlus(verbose_name='Tempo planejado', help_text='Em horas', default=0)
    # Tempo total executado somando todos os RITs vinculados
    tempo_executado = models.DecimalFieldPlus(verbose_name='Total de horas da execução', default=0, blank=True, null=True)
    tempo_executado_ajustado_pela_faixa_complexidade = models.DecimalFieldPlus(
        verbose_name='Total de horas da execução (ajustado pela faixa de complexidade)', default=0, blank=True, null=True
    )
    # Tempo total homologado somando todos os RITs vinculados
    tempo_executado_homologado = models.DecimalFieldPlus(verbose_name='Total de horas homologadas', default=0, blank=True, null=True)
    tempo_executado_homologado_ajustado_pela_faixa_complexidade = models.DecimalFieldPlus(
        verbose_name='Total de horas homologadas (ajustado pela faixa de complexidade)', default=0, blank=True, null=True
    )

    class Meta:
        verbose_name = 'Plano Individual de Trabalho'
        verbose_name_plural = 'Planos Individuais de Trabalho'

    def __str__(self):
        inicio = None
        if self.data_inicial:
            inicio = f'{format_datetime(self.data_inicial)}'
        else:
            inicio = f'{format_datetime(self.periodo_pit_rit.data_inicio)}'

        return f'PIT | {inicio} a {format_datetime(self.periodo_pit_rit.data_fim)} | {self.adesao.servidor}'

    def get_verbose_periodo(self):
        """
        inicio = None
        if self.data_inicial:
            inicio = f'{format_datetime(self.data_inicial)}'
        else:
            inicio = f'{format_datetime(self.periodo_pit_rit.data_inicio)}'
        return f'{inicio} a {format_datetime(self.periodo_pit_rit.data_fim)}'
        """
        return f'{format_datetime(self.get_data_inicial())} a {format_datetime(self.get_data_final())}'

    def get_verbose_pit_rit(self):
        """
        inicio = None
        if self.data_inicial:
            inicio = f'{format_datetime(self.data_inicial)}'
        else:
            inicio = f'{format_datetime(self.periodo_pit_rit.data_inicio)}'
        return f'PIT/RIT | {inicio} a {format_datetime(self.periodo_pit_rit.data_fim)} | {self.adesao.servidor}'
        """
        return f'PIT/RIT | {format_datetime(self.get_data_inicial())} a {format_datetime(self.get_data_final())} | {self.adesao.servidor}'

    def get_data_inicial(self):
        inicio = None
        if self.data_inicial:
            inicio = self.data_inicial
        else:
            inicio = self.periodo_pit_rit.data_inicio
        return inicio

    def get_data_final(self):
        # Se o PIT for relacionado ao desligamento
        # - A data final fica sendo a data anterior a de efeitos do desligamento
        data_fim = self.periodo_pit_rit.data_fim
        if self.adesao.tem_desligamento_cadastrado:
            if (
                self.get_data_inicial() <= self.adesao.data_desligamento_efeitos_a_partir_de
                and data_fim >= self.adesao.data_desligamento_efeitos_a_partir_de
            ):
                data_fim = self.adesao.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)

        return data_fim

    @staticmethod
    def get_pendencias_pit_servidor(servidor):
        """
        - Quais não criou e deveria ter criado
        - Quais criou mas não solicitou avaliação
        """

        # ------------------------------
        # Adesões vigentes do servidor
        # ------------------------------
        adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())
        periodos_pendentes_pit = []
        if adesoes_vigentes:
            adesoes_vigentes = adesoes_vigentes.order_by('id')
        else:
            return periodos_pendentes_pit

        def get_data_ultimo_dia_mes_ano(data):
            proximo_mes = data + relativedelta(months=1)
            return datetime.datetime(year=proximo_mes.year, month=proximo_mes.month, day=1) - timedelta(1)

        # ------------------------------
        # Obtendo os periodos de PIT que deveriam ter PIT considerando o período da adesão
        # ------------------------------
        periodos_que_precisa_de_pit = []
        if adesoes_vigentes:
            for ad in adesoes_vigentes:
                inicio_adesao = datetime.datetime(
                    year=ad.primeiro_dia_pgd_nessa_adesao2().year, month=ad.primeiro_dia_pgd_nessa_adesao2().month, day=1
                )
                final_adesao = get_data_ultimo_dia_mes_ano(ad.get_data_final_adesao())
                periodos_que_precisa_de_pit.extend(
                    PeriodoPitRit.objects.filter(
                        Q(data_inicio__range=(inicio_adesao, final_adesao)) | Q(data_fim__range=(inicio_adesao, final_adesao))
                    ).order_by('data_inicio')
                )

        if periodos_que_precisa_de_pit:
            periodos_que_precisa_de_pit = list(set(periodos_que_precisa_de_pit))
            periodos_que_precisa_de_pit = sorted(periodos_que_precisa_de_pit, key=lambda p: p.data_inicio)

            # ------------------------------
            # Obtendo PITs criados e não criados considerando o período da adesão
            # - PITs que não foram cridos (mas deveriam ter sido) já vão constar em periodos_pendentes_pit
            # ------------------------------
            pits_da_adesao = (
                PlanoIndividualTrabalho.objects.filter(adesao__in=adesoes_vigentes)
                .exclude(Q(situacao=PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR) | Q(situacao=PlanoIndividualTrabalho.CANCELADO_PELO_AVALIADOR))
                .order_by('data_inicial')
            )

            # PITs que foram criados
            periodos_pits_criados = list(PeriodoPitRit.objects.filter(id__in=pits_da_adesao.values('periodo_pit_rit__id')))

            # PITs que não foram criados
            periodos_pits_nao_criados = []
            for p in periodos_que_precisa_de_pit:
                if p not in periodos_pits_criados:
                    periodos_pits_nao_criados.append(p)

            # ------------------------------
            # Dos PITs que foram criados precisamos saber
            # - Os que foram enviados para avaliacao
            # Esses PITs (periodos_pits_enviados_sem_homologacao) vão ser excluidos de periodos_pits_criados
            # ------------------------------
            periodos_pits_ja_enviados = []
            for pa in pits_da_adesao:
                foi_enviado = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    pit=pa, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO
                ).exists()
                if foi_enviado:
                    periodos_pits_ja_enviados.append(pa.periodo_pit_rit)
            periodos_pits_criados = list(set(periodos_pits_criados).difference(set(periodos_pits_ja_enviados)))

            # ------------------------------
            # Resultado final
            # ------------------------------
            periodos_pendentes_pit = periodos_pits_nao_criados + periodos_pits_criados

        periodos_pendentes_pit_final = []
        if periodos_pendentes_pit:
            # Filtra os PITs que estão com ch prevista para o período e que são de meses posteriores
            for pit in periodos_pendentes_pit:
                pode_cobrar_pelo_periodo = pit.data_inicio < get_datetime_now().date()
                pode_cobrar_pela_ch = get_ch_servidor_periodo(servidor, pit.data_inicio, pit.data_fim)
                if pode_cobrar_pelo_periodo and pode_cobrar_pela_ch > 0:
                    periodos_pendentes_pit_final.append(pit)
            periodos_pendentes_pit_final = sorted(periodos_pendentes_pit_final, key=lambda p: p.data_inicio)

        return periodos_pendentes_pit_final

    @staticmethod
    def get_pendencias_rit_servidor(servidor):
        """
        - Quais não enviou o relatório para aprovação
        """

        adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(servidor.get_user())

        rits_pendentes_envio_avaliacao = []
        if adesoes_vigentes:
            rits_pendentes_envio_avaliacao.extend(
                RelatorioIndividualTrabalho.objects.filter(pit__adesao__in=adesoes_vigentes)
                .exclude(entregue=True)
                .exclude(
                    Q(pit__situacao=PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR)
                    | Q(pit__situacao=PlanoIndividualTrabalho.CANCELADO_PELO_AVALIADOR)
                )
                .order_by('-pit__data_inicial', '-periodo')
            )

        rits_pendentes_envio_avaliacao_final = []
        if rits_pendentes_envio_avaliacao:
            # Filtra os que são de meses posteriores
            for rit in rits_pendentes_envio_avaliacao:
                pode_cobrar_pelo_periodo = rit.get_data_final() < get_datetime_now().date()
                pode_cobrar_pela_ch = get_ch_servidor_periodo(servidor, rit.pit.periodo_pit_rit.data_inicio, rit.pit.periodo_pit_rit.data_fim)
                if pode_cobrar_pelo_periodo and pode_cobrar_pela_ch > 0:
                    rits_pendentes_envio_avaliacao_final.append(rit)

        if rits_pendentes_envio_avaliacao_final:
            rits_pendentes_envio_avaliacao_final = sorted(rits_pendentes_envio_avaliacao_final, key=lambda p: p.pit.data_inicial)
        return rits_pendentes_envio_avaliacao_final

    def get_primeiro_pit_adesao(adesao):
        return PlanoIndividualTrabalho.objects.filter(adesao=adesao, situacao=PlanoIndividualTrabalho.AUTORIZADO).order_by('id').first()

    def get_metodo_calculo(self):
        if self.get_data_inicial() <= datetime.date(2022, 12, 31):
            # com o ajustado
            return '1'
        # sem o ajustado
        return '2'

    def pode_mostrar_ajustado(self):
        return self.get_metodo_calculo() == '1'

    def tem_dados_especificos(self):
        return bool(self.data_inicial and self.percentual_presencial + self.percentual_teletrabalho == 100)

    # def tem_atividades(self):
    #    return True

    @staticmethod
    def pode_iniciar_cadastro(user, retornar_lista_erros=False):
        erros = []

        # Tem que ter adesao VIGENTE PGD
        if not SolicitacaoAdesaoServidor.get_vigentes_e_na_carencia(user):
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD você deve ter solicitação vigente.')
            else:
                return False, None

        # Tem que ter instrucoes cadastradas
        if not ConfiguracaoOrientacaoPit.get_vigentes_sistemico().exists():
            if retornar_lista_erros:
                erros.append('A Gestão deve cadastrar Orientação Sistêmica sobre Plano Individual de Trabalho.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_finalizar_cadastro(user, periodo_pit_rit, adesao_pgd, retornar_lista_erros=False):
        erros = []
        servidor = user.get_relacionamento()

        # Tem que ter adesao VIGENTE PGD
        adesoes_pgd_vigente = SolicitacaoAdesaoServidor.get_vigentes_e_na_carencia(user)
        if not adesoes_pgd_vigente:
            if retornar_lista_erros:
                erros.append('Para cadastrar um PIT você deve ter alguma adesão vigente ao PGD.')
            else:
                return False, None

        if adesao_pgd and not adesao_pgd.estah_vigente_e_na_carencia:
            if retornar_lista_erros:
                erros.append('Para cadastrar um PIT você deve ter selecionado uma adesão ao PGD que esteja vigente.')
            else:
                return False, None

        # Se tiver desligamento na adesao vigente
        # - O PIT deve INICIAR ANTES ou NO MESMO DIA da data de efeito do desligamento
        if (
            adesao_pgd
            and adesao_pgd.data_desligamento_efeitos_a_partir_de
            and not (periodo_pit_rit.data_inicio <= adesao_pgd.data_desligamento_efeitos_a_partir_de)
        ):
            if retornar_lista_erros:
                erros.append('Para cadastrar um PIT ele deve iniciar antes ou mesmo dia da data de efeito desligamento.')
            else:
                return False, None

        # Ter PTS aptos a receber PITs do servidor
        pts_apto = PlanoTrabalhoSetorial.get_pts_ativo_do_servidor(adesao_pgd)
        if not pts_apto:
            if retornar_lista_erros:
                erros.append('Para cadastrar um PIT você deve ter ao menos um PTS que esteja apto a ser utilizado por este PIT.')
            else:
                return False, None

        # Tem que ter instrucoes cadastradas
        if not ConfiguracaoOrientacaoPit.get_vigentes_sistemico().exists():
            if retornar_lista_erros:
                erros.append('A Gestão deve cadastrar Orientação Sistêmica sobre Plano Individual de Trabalho.')
            else:
                return False, None

        # Nao pode se existe outro PIT nas seguintes situacoes
        situacoes = [PlanoIndividualTrabalho.CADASTRADO, PlanoIndividualTrabalho.AGUARDANDO_PARECER, PlanoIndividualTrabalho.AUTORIZADO]
        if PlanoIndividualTrabalho.objects.filter(adesao__servidor=servidor, periodo_pit_rit=periodo_pit_rit, situacao__in=situacoes).exists():
            if retornar_lista_erros:
                erros.append(
                    'Para cadastrar um novo PIT você não deve ter PITs (para o mesmo período) na situação "Cadastrado" ou "Aguardando parecer".'
                )
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def get_ids_setores_dos_pts_relacionados(self):
        # - Pega a lista de todas as atividades relacionadas ao PIT
        # - Pega o PTS de cada uma dessas atividades
        # - Pega o setor de cada um desses PTSs
        # - Retorna essa lista de setores
        pts_relacionados = self.get_pts_relacionados()
        if pts_relacionados:
            return pts_relacionados.values_list('setor__id', flat=True)
        return None

    def pode_visualizar(self, user=None):
        if not user:
            # Se ja foi homologado de forma definitiva
            if self.homologado_definitivo:
                return False

            # Se foi cancelado
            if self.estah_cancelado():
                return False

            # Se tiver desligado e fora da carencia nao pode
            return not self.adesao.estah_desligado_mas_fora_da_carencia
        else:
            if not user.has_perm('pgd.view_planoindividualtrabalho'):
                return False

            # Se ja foi homologado de forma definitiva
            if self.homologado_definitivo:
                return False

            # Se foi cancelado
            if self.estah_cancelado():
                return False

            relacionamento = user.get_relacionamento()
            quem_cadastrou = self.adesao.servidor.pk == relacionamento.pk
            estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
            estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
            estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')

            # Regra da chefia:
            # - Pode ver se for CHEFE DO SERVIDOR
            # ou
            # - For chefe do setor vinculado ao PTS de ao menos uma atividade do Planejamento do Servidor
            # eh_chefe_do_servidor = setores_que_sou_chefe_hoje(relacionamento).filter(pk=self.adesao.servidor.setor_id).exists()
            # ids_setores_dos_pts_relacionados = self.get_ids_setores_dos_pts_relacionados()
            # eh_chefe_pts_relacionado = setores_que_sou_chefe_hoje(relacionamento).filter(pk__in=ids_setores_dos_pts_relacionados).exists()
            # regra_chefe = eh_chefe_do_servidor or eh_chefe_pts_relacionado

            chefe_aprovar_ou_homologar_pit = self.pode_chefe_aprovar_ou_homologar_pit(user)
            regra_chefe = chefe_aprovar_ou_homologar_pit is True

            return quem_cadastrou or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente or estah_em_gestao_pgd or regra_chefe

    def pode_visualizar_pit_completo(self, user):
        if not user.has_perm('pgd.view_planoindividualtrabalho'):
            return False

        relacionamento = user.get_relacionamento()
        quem_cadastrou = self.adesao.servidor.pk == relacionamento.pk
        estah_em_comissao_sistemica_vigente = user.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user.has_group_cached('Comissão Local PGD')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD')

        chefe_aprovar_ou_homologar_pit = self.pode_chefe_aprovar_ou_homologar_pit(user)
        regra_chefe = chefe_aprovar_ou_homologar_pit is True

        return quem_cadastrou or estah_em_comissao_sistemica_vigente or estah_em_comissao_local_vigente or estah_em_gestao_pgd or regra_chefe

    @staticmethod
    def pode_gestao_visualizar_pgd_servidor(servidor_pgd, user_acesso):
        servidor_acesso = user_acesso.get_relacionamento()

        eh_servidor_dono_das_horas = servidor_pgd == servidor_acesso
        estah_em_comissao_sistemica_vigente = user_acesso.has_group_cached('Comissão Sistêmica PGD')
        estah_em_comissao_local_vigente = user_acesso.has_group_cached('Comissão Local PGD')
        estah_em_gestao_pgd = user_acesso.has_group_cached('Gestor do PGD')
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(servidor_acesso).filter(pk=servidor_pgd.setor.id).exists()

        return (
            eh_servidor_dono_das_horas
            or estah_em_comissao_sistemica_vigente
            or estah_em_comissao_local_vigente
            or estah_em_gestao_pgd
            or eh_chefe_do_servidor
        )

    def pode_servidor_editar(self, user):
        # --------------------------------------------------
        # Verifica se apenas o SERVIDOR pode EDITAR
        # --------------------------------------------------

        # Tem permissao
        if not user.has_perm('pgd.change_planoindividualtrabalho'):
            return False

        # Adesao ao PGD (de esta deferida)
        if not self.adesao.estah_deferida:
            return False

        # Se eh Servidor deste PIT
        # Se eh o servidor Adesao ao PGD vinculada a este PIT
        if self.adesao.servidor != user.get_relacionamento():
            return False

        # Se tem PTS apto
        if not PlanoTrabalhoSetorial.get_pts_apto_do_servidor(self.adesao).exists():
            return False

        # Situacao do PIT permite
        if self.situacao not in [self.CADASTRADO, self.AUTORIZADO]:
            return False

        # Se ja foi homologado de forma definitiva
        if self.homologado_definitivo:
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Precisa estar vigente
        # - Se tiver desligamento precisa ta na carencia
        pode_pela_adesao = False
        if self.adesao.estah_vigente_e_na_carencia:
            pode_pela_adesao = True

        return pode_pela_adesao

    def pode_chefe_editar(self, user, lista_setores_user_eh_chefe_hoje=None):
        # --------------------------------------------------
        # Verifica se APENAS o o CHEFE pode EDITAR
        # --------------------------------------------------

        # Tem permissao
        if not user.has_perm('pgd.change_planoindividualtrabalho'):
            return False

        # Adesao ao PGD (de esta deferida)
        if not self.adesao.estah_deferida:
            return False

        # Nao pode ser o servidor do pit
        if self.adesao.servidor == user.get_relacionamento():
            return False

        # Se a situacao permite
        if self.situacao not in [self.CADASTRADO, self.AUTORIZADO]:
            return False

        # Se ja foi homologado de forma definitica
        if self.homologado_definitivo:
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Precisa estar vigente
        # - Se tiver desligamento precisa ta na carencia
        pode_pela_adesao = False
        if self.adesao.estah_vigente_e_na_carencia:
            pode_pela_adesao = True
        else:
            hoje = get_datetime_now().date()
            pit_encerrado = self.get_data_final() and self.get_data_final() < hoje
            if pit_encerrado and not self.estah_cancelado():
                pode_pela_adesao = True

        # O chefe do setor deve estar vinculado ao pit que deseja editar
        pits_do_chefe = (
            PlanoIndividualTrabalho.get_pits_chefe_setor(
                user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje, somente_ids=True, pit=self
            )
            .filter(pk=self.pk)
            .exists()
        )
        if not pits_do_chefe:
            return False

        return pode_pela_adesao

    def pode_chefe_servidor_editar(self, user):
        # --------------------------------------------------
        # Verifica se o SERVIDOR ou o CHEFE podem EDITAR
        # --------------------------------------------------
        return self.pode_servidor_editar(user) or self.pode_chefe_editar(user)

    def pode_recalcular_pit_rit(self, user):
        # return self.pode_servidor_editar(user)
        return self.pode_servidor_editar(user) or self.pode_chefe_editar(user)

    def pode_servidor_solicitar_aprovacao_pit_rit(self, user):
        # Se o servidor pode solicitar aprov e homolog de um Pit Planejamento
        pode_servidor_editar = self.pode_servidor_editar(user)
        if not pode_servidor_editar:
            return False

        # Ao menos um PTS relacionado a este RIT Deve ter ao menos uma atividade deve estar vinculado ao setor do servidor
        # - Os PTSs relacionados vem das atividades vinculadas ai RIT (planejamento)
        ids_setores = self.get_ids_setores_dos_pts_relacionados()
        if ids_setores and self.adesao.servidor.setor.id not in ids_setores:
            return False

        existe_atividade_pendente_analise = RelatorioIndividualTrabalhoAtividade.objects.filter(
            rit__pit=self, situacao__in=[RelatorioIndividualTrabalhoAtividade.CADASTRADO]
        ).exists()

        return existe_atividade_pendente_analise

    def pode_aprovar_homologar_pit_rit(self, user):
        # Se o chefe pode homologar um PIT - Planejamento
        # Apenas chefe

        # Tem permissao
        if not user.has_perm('pgd.change_planoindividualtrabalho'):
            return False

        # Nao pode ser o servidor do pit
        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        # O chefe do setor deve estar vinculado ao pit que deseja editar
        pits_do_chefe = PlanoIndividualTrabalho.get_pits_chefe_setor(user).filter(pk=self.pk).exists()
        if not pits_do_chefe:
            return False

        # Se a situação permite:
        # - Se estiver aguardando parecer -> pode aprovar
        # - Se já estiver autorizado -> só permitir homologar quando todos os RITs já foram avaliados
        if self.situacao == PlanoIndividualTrabalho.AGUARDANDO_PARECER:
            return True
        if self.situacao == PlanoIndividualTrabalho.AUTORIZADO:
            return self.pode_homologar_pit()

        return False

    def pode_homologar_pit(self):
        # Se todos os RITs foram avaliados
        rits = self.get_rits_relacionados()
        return all(rit.foi_avaliado() for rit in rits)

    def pode_chefe_aprovar_ou_homologar_pit(self, user, operacao=None):
        # Considera APENAS A REGRA COMPLEMENTAR DA CHEFIA
        # Para saber se de fato o servidor pode ou nao homologar/aprovar deve-se utilizar o "pode_aprovar_homologar_pit_rit"

        # Diz qual operacao ele pode fazer com o PIT
        # O parametro operacao pode ter os seguintes valores: 'aprovar' ou 'homologar'
        # - Se for 'aprovar' você está perguntando se pode aprovar o PIT
        # - Se for 'homologar' você está perguntando se pode homologar o PIT
        # - Se for None você está perguntando se pode aprovar OU homologar o PIT
        # Retorna 'aprovar' se puder aprovar
        # Retorna 'homologar' se puder homologar
        # Retorna True se puder aprovar ou homologar
        # Retorna False se puder homologar e nem aprovar

        relacionamento = user.get_relacionamento()

        # Regra da chefia:
        # - Pode Homologar for CHEFE DO SERVIDOR
        # - Pode Aprovar se "Não Puder Homologar" e se for chefe do setor vinculado ao PTS
        #   de ao menos uma atividade do Planejamento do Servidor
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(relacionamento).filter(pk=self.adesao.servidor.setor_id).exists()
        ids_setores_dos_pts_relacionados = self.get_ids_setores_dos_pts_relacionados()
        if not ids_setores_dos_pts_relacionados:
            return False
        eh_chefe_pts_relacionado = setores_que_sou_chefe_hoje(relacionamento).filter(pk__in=ids_setores_dos_pts_relacionados).exists()

        if not operacao:
            return bool(eh_chefe_do_servidor or eh_chefe_pts_relacionado)

        if operacao:
            if eh_chefe_do_servidor:
                return 'homologar'
            if eh_chefe_pts_relacionado:
                return 'aprovar'

        return False

    def pode_chefe_autorizar_pit_planejamento(self, user, setores_chefe_hoje=None, depois=False):
        # Considera APENAS A REGRA COMPLEMENTAR DA CHEFIA
        # Se pode APENAS AUTORIZAR o planejamento

        # Permite também quando o PIT já encerrou (data final anterior a hoje) e não está cancelado
        if self.situacao != PlanoIndividualTrabalho.AGUARDANDO_PARECER:
            from pgd.utils import get_datetime_now

            hoje = get_datetime_now().date()
            if not (self.get_data_final() < hoje and not self.estah_cancelado()):
                return False

        # Se for chefe direto (considerando a adesao vinculada ao PIT do servidor)
        if not setores_chefe_hoje:
            relacionamento = user.get_relacionamento()
            setores_chefe_hoje = setores_que_sou_chefe_hoje(relacionamento)
        eh_chefe_direto = setores_chefe_hoje.filter(pk=self.adesao.servidor.setor_id).exists()
        if eh_chefe_direto:
            if depois:
                return True
            # Se nao existe nenhuma atividade que deva ser AUTORIZADA
            atvidades_a_aprovar_do_pit = self.get_atividades_a_aprovar_do_pit()
            # for at in atvidades_a_aprovar_do_pit:
            #    if not at.eh_espelho():
            #        if at.situacao == RelatorioIndividualTrabalhoAtividade.CADASTRADA:
            #            return False
            return not atvidades_a_aprovar_do_pit

        return False

    def pode_chefe_autorizar_atividades(self, user, setores_chefe_hoje=None):
        if not setores_chefe_hoje:
            relacionamento = user.get_relacionamento()
            setores_chefe_hoje = setores_que_sou_chefe_hoje(relacionamento)

        atividades = self.get_atividades_a_aprovar_do_pit()

        ids_atividades_pode = []
        for at in atividades:
            if at.pode_chefe_autorizar_atividade(user, setores_chefe_hoje=setores_chefe_hoje):
                ids_atividades_pode.append(at.id)
        if ids_atividades_pode:
            return True, ids_atividades_pode
        return False, None

    @staticmethod
    def get_pits_chefe_setor(user, lista_setores_user_eh_chefe_hoje=None, somente_ids=True, pit=None):
        lista_setores_que_sou_chefe_hoje = lista_setores_user_eh_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())
        # Pega os PTSs que sao vinculados ao setor que ele eh chefe
        # Pega os ids dos PITs que possuem alguma atividade que eh esta em um dos PTS do chefe
        ids_pits = None
        if pit:
            # Se passar um PIT
            # - filtra pelo pit
            # - pega os setores que relacionados ao PIT confrontando com os setoes que sou chefe
            setores = pit.get_setores_ptss_relacionados()
            ids_pits = Subquery(
                RelatorioIndividualTrabalhoAtividade.objects.filter(
                    rit__pit=pit, atividade_pts__plano_trabalho_setorial__in=PlanoTrabalhoSetorial.get_pts_aptos_dos_setores2(setores)
                )
                .values_list('rit__pit_id', flat=True)
                .distinct()
            )
        else:
            ids_pits = Subquery(
                RelatorioIndividualTrabalhoAtividade.objects.filter(
                    atividade_pts__plano_trabalho_setorial__in=PlanoTrabalhoSetorial.get_pts_aptos_dos_setores2(lista_setores_que_sou_chefe_hoje)
                )
                .values_list('rit__pit_id', flat=True)
                .distinct()
            )
        # Pega os PITs que posso avaliar/visualizar
        if somente_ids:
            return PlanoIndividualTrabalho.objects.filter(id__in=ids_pits).only('id').order_by('adesao__servidor__pessoa_fisica__nome')
        return PlanoIndividualTrabalho.objects.filter(id__in=ids_pits).order_by('adesao__servidor__pessoa_fisica__nome')

    def get_situacao_virtual(self):
        atividades_a_aprovar_do_pit = RelatorioIndividualTrabalhoAtividade.objects.filter(
            rit__pit=self, situacao__in=[RelatorioIndividualTrabalhoAtividade.CADASTRADO]
        )
        if atividades_a_aprovar_do_pit.exists() and self.situacao not in [
            self.AGUARDANDO_PARECER,
            self.CANCELADO_PELO_SERVIDOR,
            self.CANCELADO_PELO_AVALIADOR,
        ]:
            return (self.CADASTRADO, 'Aguardando envio para aprovação')
        return (self.situacao, self.get_situacao_display())

    def deve_verificar_ponto(self):
        # Só deve verificar o ponto do servidor deste pit se
        # - Se for primeiro PIT nao cancelado dessa adesao ao PGD
        # - E se essa eh primeira submissao deste pit nessa adesao
        primeiro_pit_adesao = (
            PlanoIndividualTrabalho.objects.filter(adesao=self.adesao)
            .exclude(situacao__in=[PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR, PlanoIndividualTrabalho.CANCELADO_PELO_AVALIADOR])
            .order_by('id')
            .first()
        )
        if primeiro_pit_adesao and primeiro_pit_adesao == self:
            return not RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, pit=primeiro_pit_adesao
            ).exists()

        return False

    def calcular_pit(self, forcar_recalcular_tempo_previsto=False):
        rits = RelatorioIndividualTrabalho.objects.filter(pit=self)

        # ------------------------------------------
        # RITS, ATIVIDADES, ENTREGAS
        # ------------------------------------------
        for rit in rits:
            # Calcula entregas
            entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=rit)
            for entrega in entregas:
                entrega.calcular_entrega()
                entrega.save()

            # Calcula atividades
            atividades = RelatorioIndividualTrabalhoAtividade.objects.filter(rit=rit)
            for atividade in atividades:
                atividade.calcular_atividade_rit()
                atividade.save()

            # Calcula rits
            rit.calcular_rit(forcar_recalcular_tempo_previsto=forcar_recalcular_tempo_previsto)
            rit.save()

        # ------------------------------------------
        # PIT
        # ------------------------------------------
        self.tempo_previsto = gv(rits.aggregate(v=Sum('tempo_previsto')))
        #
        self.tempo_planejado = gv(rits.aggregate(v=Sum('tempo_planejado')))
        self.tempo_planejado_cadastrado = gv(rits.aggregate(v=Sum('tempo_planejado_cadastrado')))
        self.tempo_planejado_autorizado = gv(rits.aggregate(v=Sum('tempo_planejado_autorizado')))
        self.tempo_planejado_cancelado = gv(rits.aggregate(v=Sum('tempo_planejado_cancelado')))
        #
        self.tempo_executado = gv(rits.aggregate(v=Sum('tempo_executado')))
        self.tempo_executado_ajustado_pela_faixa_complexidade = gv(rits.aggregate(v=Sum('tempo_executado_ajustado_pela_faixa_complexidade')))
        #
        self.tempo_executado_homologado = gv(rits.aggregate(v=Sum('tempo_executado_homologado')))
        self.tempo_executado_homologado_ajustado_pela_faixa_complexidade = gv(
            rits.aggregate(v=Sum('tempo_executado_homologado_ajustado_pela_faixa_complexidade'))
        )

        self.save()

        return False

    def get_atividades_a_aprovar_do_pit(self):
        return RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=self, situacao__in=[RelatorioIndividualTrabalhoAtividade.CADASTRADO])

    def get_ptss_das_atividades_a_aprovar_do_pit(self):
        # Lista os PTSs que deve aprovar cada atividade do PIT
        if self.situacao == self.AGUARDANDO_PARECER:
            ptss = (
                RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=self, situacao__in=[RelatorioIndividualTrabalhoAtividade.CADASTRADO])
                .values_list('atividade_pts__plano_trabalho_setorial__id', flat=True)
                .distinct()
            )
            if ptss:
                return PlanoTrabalhoSetorial.objects.filter(id__in=ptss)
        return None

    def get_setor_a_autorizar_pit(self):
        # Lista o SETOR que deve autorizar o PIT
        if self.situacao == self.AGUARDANDO_PARECER:
            return self.adesao.servidor.setor
        return None

    def get_atividades_autorizadas(self):
        return RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=self, situacao=RelatorioIndividualTrabalhoAtividade.AUTORIZADO)

    def get_rits_relacionados(self):
        # RITs relacionados
        return RelatorioIndividualTrabalho.objects.filter(pit=self).order_by('periodo')

    def get_pts_relacionados(self):
        # PTSs relacionados as ativividades de cada um dos RITs relacionados
        ptss = (
            RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=self)
            .values_list('atividade_pts__plano_trabalho_setorial__id', flat=True)
            .distinct()
        )
        if ptss:
            return PlanoTrabalhoSetorial.objects.filter(id__in=ptss)
        return None

    def get_setores_ptss_relacionados(self):
        # Retorna setores dos PTSs relacionados ao PIT
        ptss = (
            RelatorioIndividualTrabalhoAtividade.objects.filter(rit__pit=self)
            .values_list('atividade_pts__plano_trabalho_setorial__setor_id', flat=True)
            .distinct()
        )
        if ptss:
            return Setor.objects.suap_ativos().filter(id__in=ptss)
        return None

    @staticmethod
    def get_pits_ativos_adesao(adesao):
        # Lista dos PITs
        # - Ativos:
        #   - Com situacao: CADASTRADO, AGUARDANDO_PARECER, AUTORIZADO
        situacoes_ativo = [PlanoIndividualTrabalho.CADASTRADO, PlanoIndividualTrabalho.AGUARDANDO_PARECER, PlanoIndividualTrabalho.AUTORIZADO]
        return PlanoIndividualTrabalho.objects.filter(adesao=adesao, situacao__in=situacoes_ativo).order_by('data_inicial')

    @staticmethod
    def get_ultimo_pit_ativo_adesao(adesao):
        # Pit atual da adesao
        pits_ativos = PlanoIndividualTrabalho.get_pits_ativos_adesao(adesao)
        if pits_ativos:
            return pits_ativos[-1]
        return None

    def pode_servidor_cancelar_pit(self, user):
        # --------------------------------------------------
        # Verifica se SERVIDOR pode cancelar PIT
        # --------------------------------------------------
        # Tem permissao
        if not user.has_perm('pgd.change_planoindividualtrabalho'):
            return False
        # Adesao ao PGD (de esta deferida)
        if not self.adesao.estah_deferida:
            return False
        # Se eh Servidor deste PIT
        # Se eh o servidor Adesao ao PGD vinculada a este PIT
        if self.adesao.servidor != user.get_relacionamento():
            return False
        # Situacao do PIT permite
        if self.situacao in [self.CANCELADO_PELO_SERVIDOR, self.CANCELADO_PELO_AVALIADOR]:
            return False
        # Se tiver desligado e fora da carencia nao pode
        return not self.adesao.estah_desligado_mas_fora_da_carencia

    def estah_cancelado(self):
        return self.situacao in [self.CANCELADO_PELO_SERVIDOR, self.CANCELADO_PELO_AVALIADOR]


class RegistroAcaoPlanoIndividualTrabalho(RegistroAcaoPGD):
    TIPO_CADASTRADO = PlanoIndividualTrabalho.CADASTRADO  # 1
    TIPO_AGUARDANDO_PARECER = PlanoIndividualTrabalho.AGUARDANDO_PARECER  # 2
    TIPO_CANCELADO_PELO_SERVIDOR = PlanoIndividualTrabalho.CANCELADO_PELO_SERVIDOR  # 3
    TIPO_CANCELADO_PELO_AVALIADOR = PlanoIndividualTrabalho.CANCELADO_PELO_AVALIADOR  # 4
    TIPO_AUTORIZADO = PlanoIndividualTrabalho.AUTORIZADO  # 5
    TIPO_ALTEROU_DADOS_ESPECIFICOS = 6
    TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO = 7
    TIPO_CHEFE_APROVOU_HOMOLOGOU = 8
    TIPO_CHEFE_NAO_APROVOU_HOMOLOGOU = 9

    TIPO_CHOICES = (
        (TIPO_CADASTRADO, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_CADASTRADO - 1][1]),
        (TIPO_AGUARDANDO_PARECER, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_AGUARDANDO_PARECER - 1][1]),
        (TIPO_CANCELADO_PELO_SERVIDOR, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_CANCELADO_PELO_SERVIDOR - 1][1]),
        (TIPO_CANCELADO_PELO_AVALIADOR, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_CANCELADO_PELO_AVALIADOR - 1][1]),
        (TIPO_AUTORIZADO, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_AUTORIZADO - 1][1]),
        (TIPO_ALTEROU_DADOS_ESPECIFICOS, 'Alterou Dados Específicos'),
        (TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, 'Solicitou Aprovação/Homologação'),
        (TIPO_CHEFE_APROVOU_HOMOLOGOU, 'Aprovou/Homologou'),
        (TIPO_CHEFE_NAO_APROVOU_HOMOLOGOU, 'Não Aprovou/Homologou'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    pit = models.ForeignKeyPlus('pgd.PlanoIndividualTrabalho', editable=False, null=True)


# ====================================================
# RIT Planejamento
# ====================================================


class RelatorioIndividualTrabalho(models.ModelPlus):
    SEARCH_FIELDS = ['pit__periodo_pit_rit__data_inicio', 'pit__periodo_pit_rit__data_fim', 'pit__adesao__servidor__pessoa_fisica__nome']

    pit = models.ForeignKeyPlus('pgd.PlanoIndividualTrabalho', verbose_name='PIT', editable=False)
    periodo = models.PositiveIntegerField(editable=False)

    # Quando o servidor entrega de forma definitiva
    entregue = models.BooleanField('Entregue ', default=False)
    # Quando há a homologação e aprovacao final do RIT
    aprovado_definitivo = models.BooleanField('Aprovado', null=True)
    homologado_definitivo = models.BooleanField('Homologado', null=True)

    # Consolidado
    # --------------------
    # Tempo previsto vem do ponto de acordo com o periodo e o calendario
    tempo_previsto = models.DecimalFieldPlus(verbose_name='Tempo previsto', help_text='Em horas', default=0)
    tempo_planejado_cadastrado = models.DecimalFieldPlus(verbose_name='Tempo previsto cadastrado', help_text='Em horas', default=0)
    tempo_planejado_autorizado = models.DecimalFieldPlus(verbose_name='Tempo previsto autorizado', help_text='Em horas', default=0)
    tempo_planejado_cancelado = models.DecimalFieldPlus(verbose_name='Tempo previsto cancelado', help_text='Em horas', default=0)
    #
    tempo_planejado = models.DecimalFieldPlus(verbose_name='Tempo planejado', help_text='Em horas', default=0)
    #
    tempo_executado = models.DecimalFieldPlus(verbose_name='Total de horas da execução', default=0, blank=True, null=True)
    tempo_executado_entregue = models.DecimalFieldPlus(verbose_name='Total de horas da execução (entregue)', default=0, blank=True, null=True)
    tempo_executado_nao_entregue = models.DecimalFieldPlus(verbose_name='Total de horas da execução (não entregue)', default=0, blank=True, null=True)
    tempo_executado_ajustado_pela_faixa_complexidade = models.DecimalFieldPlus(
        verbose_name='Total de horas da execução (ajustado pela faixa de complexidade)', default=0, blank=True, null=True
    )
    #
    tempo_executado_homologado = models.DecimalFieldPlus(verbose_name='Total de horas homologadas', default=0, blank=True, null=True)
    tempo_executado_homologado_ajustado_pela_faixa_complexidade = models.DecimalFieldPlus(
        verbose_name='Total de horas homologadas (ajustado pela faixa de complexidade)', default=0, blank=True, null=True
    )

    # Distribuicao de CH
    # --------------------
    # Dados básicos
    ch_distribuida = models.DecimalFieldPlus(verbose_name='CH distribuída', default=0)
    ch_a_distribuir = models.DecimalFieldPlus(verbose_name='CH a distribuir', default=0)
    # Período RIT
    ch_distribuido_periodo_rit = models.DecimalFieldPlus(verbose_name='CH distribuída no período do RIT', default=0)
    # Semestre do RIT
    ch_distribuido_semestre_rit = models.DecimalFieldPlus(verbose_name='CH distribuída no semestre do RIT', default=0)
    # Compesação específica
    ch_distribuido_compesacao_especifica = models.DecimalFieldPlus(verbose_name='CH distribuída para compensações específicas', default=0)
    # Se na distribuição aitomática sobrar CH A DISTRBIUIR é pq não tinha mais onde distribuir a CH HOMOLOGADA deste RIT
    # - Assim, o RIT fica bloqueado para distribuições manauais
    bloqueado_para_distribuicao_manual = models.BooleanField(default=False)

    # Dados a serem preenchidos no form de Entrega do RIT
    # --------------------
    justificativa_entrega = models.TextField(verbose_name='Justificativa', blank=True, null=True)
    dificuldades_enfrentadas_entrega = models.TextField(verbose_name='Dificuldades enfrentadas', blank=True, null=True)
    sugestoes_aperfeicoamento_entrega = models.TextField(verbose_name='Sugestões de aperfeiçoamento do PGD', blank=True, null=True)

    # Dados a serem preenchidos no form de Homologação do RIT
    # --------------------
    justificativa_homologacao = models.TextField(verbose_name='Justificativa', blank=True, null=True)
    melhorias_percebidas_homologacao = models.TextField(
        verbose_name='Melhorias percebidas na qualidade dos serviços prestados', blank=True, null=True
    )
    dificuldades_enfrentadas_homologacao = models.TextField(verbose_name='Dificuldades enfrentadas', blank=True, null=True)
    sugestoes_aperfeicoamento_homologacao = models.TextField(verbose_name='Sugestões de aperfeiçoamento do PGD', blank=True, null=True)
    NOTA_COMPROMETIMENTO_HOMOLOGACAO_CHOICES = [[1, '1 estrela'], [2, '2 estrelas'], [3, '3 estrelas'], [4, '4 estrelas'], [5, '5 estrelas']]
    nota_comprometimento_homologacao = models.PositiveIntegerField(
        'Comprometimento percebido dos participantes', choices=NOTA_COMPROMETIMENTO_HOMOLOGACAO_CHOICES, blank=True, null=True
    )

    class Meta:
        verbose_name = 'Relatório Individual de Trabalho'
        verbose_name_plural = 'Relatórios Individuais de Trabalho'

    def __str__(self):
        return self.get_verbose_planejamento()

    def get_datas_periodo_planejamento_rit(self):
        dts = self.pit.periodo_pit_rit.get_periodos_calendario_rit()[self.periodo - 1]
        dt_inicial = dts[0]
        dt_final = dts[1]
        if self.periodo == 1 and self.pit.data_inicial:
            dt_inicial = self.pit.data_inicial
        return (dt_inicial, dt_final)

    def get_data_inicial(self):
        return self.get_datas_periodo_planejamento_rit()[0]

    def get_data_final(self):
        # Se o PIT for relacionado ao desligamento
        # - A data final fica sendo a data anterior a de efeitos do desligamento
        data_fim = self.get_datas_periodo_planejamento_rit()[1]
        if self.pit.adesao.tem_desligamento_cadastrado:
            if (
                self.pit.get_data_inicial() <= self.pit.adesao.data_desligamento_efeitos_a_partir_de
                and data_fim >= self.pit.adesao.data_desligamento_efeitos_a_partir_de
            ):
                data_fim = self.pit.adesao.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)

        return data_fim

    def get_metodo_calculo_entrega(self):
        return self.pit.get_metodo_calculo()

    def pode_mostrar_ajustado(self):
        return self.pit.pode_mostrar_ajustado()

    def get_verbose_rit(self):
        return f'Relatório Individual de Trabalho de {format_datetime(self.get_datas_periodo_planejamento_rit()[0])} até {format_datetime(self.get_data_final())}'

    def get_verbose_rit_servidor(self):
        return f'Relatório Individual de Trabalho de {format_datetime(self.get_datas_periodo_planejamento_rit()[0])} até {format_datetime(self.get_data_final())} | {self.pit.adesao.servidor!s}'

    def get_verbose_planejamento(self):
        # return f'Planejamento de {format_datetime(self.get_datas_periodo_planejamento_rit()[0])} até {format_datetime(self.get_datas_periodo_planejamento_rit()[1])}'
        return f'Planejamento de {format_datetime(self.get_datas_periodo_planejamento_rit()[0])} até {format_datetime(self.get_data_final())}'

    def get_verbose_planejamento_periodo(self):
        return f'{format_datetime(self.get_datas_periodo_planejamento_rit()[0])} a {format_datetime(self.get_data_final())}'

    def pode_servidor_editar(self, user):
        return self.pit.pode_servidor_editar(user) and not self.entregue and (self.homologado_definitivo is None)

    def pode_chefe_editar(self, user, lista_setores_user_eh_chefe_hoje=None):
        return self.pit.pode_chefe_editar(user, lista_setores_user_eh_chefe_hoje) and (self.homologado_definitivo is None)

    def pode_chefe_servidor_editar(self, user):
        return self.pit.pode_chefe_servidor_editar(user) and not self.entregue and (self.homologado_definitivo is None)

    def get_atividades(self):
        return self.relatorioindividualtrabalhoatividade_set.all()

    def get_atividades_para_adicionar(self):
        # Atividades que podem ser adicionadas ao PIT/RIT do servidor relacionado a Adesão do PIT relacionado a este RIT
        # --------------------------------------------------
        # PTSs ativos do servidor
        pts_aptos = PlanoTrabalhoSetorial.get_pts_ativo_do_servidor(self.pit.adesao)
        for pts in pts_aptos or ():
            pts.sincrononiza_inativacao_atividades()

        # Atividades atuais do meu planejamento -- SERAO EXCLUIDAS DA LISTA
        atividades_pts_rit_ids = list(
            self.get_atividades().exclude(situacao=RelatorioIndividualTrabalhoAtividade.CANCELADO).values_list('atividade_pts__id', flat=True)
        )

        # Atividades vinculadas aos meus PTSs excluindo aquelas que já estão no planejamento (RIT de um PIT)
        return (
            PlanoTrabalhoSetorialAtividades.get_atividades_ativas()
            .filter(plano_trabalho_setorial__in=pts_aptos)
            .exclude(id__in=atividades_pts_rit_ids)
        )

    def get_dados_horas_ponto_servidor(self):
        data_ini = self.get_data_inicial()
        data_fim = self.get_data_final()
        return obter_dados_horas_ponto_servidor(self.pit.adesao.servidor, data_ini=data_ini, data_fim=data_fim)

    def get_tempo_previsto(self, forcar_recalcular=False, dados_horas_ponto_servidor=None):
        if not self.tempo_previsto or forcar_recalcular:
            if self.pit.adesao.servidor.eh_docente:
                pd = PontoDocente(self.pit.adesao.servidor, self.get_data_inicial(), self.get_data_final())
                horas = pd.total_relogio_exigido()
                if horas:
                    return horas / 3600
                return 0
            if self.pit.adesao.servidor.eh_tecnico_administrativo:
                # Tempo previsto do servidor TAE
                ths = None
                if dados_horas_ponto_servidor:
                    ths = dados_horas_ponto_servidor
                else:
                    ths = self.get_dados_horas_ponto_servidor()
                ths = ths.get_totais()

                tempo_previsto = 0

                data_rit = datetime.date(self.get_data_inicial().year, self.get_data_inicial().month, 1)
                data_atual = datetime.date(get_datetime_now().year, get_datetime_now().month, 1)

                # Calculando para meses que já passaram
                if data_rit < data_atual:
                    tempo_previsto = ths.total_exigido_final + ths.total_debito_externo
                # Calculando para o mês atual
                elif data_rit == data_atual:
                    tempo_previsto = (ths.total_exigido_previo - ths.total_desconsiderado_debito) + ths.total_debito_externo
                else:
                    # Calculando para meses pra frente
                    tempo_previsto = ths.total_exigido_previo + ths.total_debito_externo

                return tempo_previsto / 3600

        return self.tempo_previsto

    def get_tempo_debito_nao_compensado_anterior_periodo_rit(self):
        # ==============================================================
        # Pega o tempo de débito ainda não compensado considerando apenas o período do anterior ao período (mês) do RIT
        # e também considerando o semestre do RIT
        # ==============================================================

        # Pega o período anterior ao do RIT (dentro do semestre do RIT)
        # --------------------------------------------------------------
        di, df = self.get_periodo_semestre_rit_antes_rit()

        if di and df:
            # Pega o tempo de débito ainda não compensado
            # --------------------------------------------------------------
            ths = obter_dados_horas_ponto_servidor(self.pit.adesao.servidor, data_ini=di, data_fim=df)
            ths = ths.get_totais()

            # Retorna em segundos
            # return (ths.total_exigido_final + ths.total_debito_externo) - ths.total_trabalhado
            return ths.total_restante_debito

        return 0

    def get_tempo_homologado(self):
        if self.pode_mostrar_ajustado():
            return self.tempo_executado_homologado_ajustado_pela_faixa_complexidade
        return self.tempo_executado_homologado

    def get_periodo_semestre_rit(self):
        # Semestre do RIT
        # - Se o RIT for do mês de MAI
        #   - O semestre do RIT será JAN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre do RIT será JUL a DEZ
        # Considerar ainda data de adesão ao PGD e eventual desligamento
        di = None
        df = None
        mes_rit = self.get_data_inicial().month
        ano_rit = self.get_data_inicial().year
        if mes_rit <= 6:
            di = datetime.date(ano_rit, 1, 1)
            df = datetime.date(ano_rit, 6, 30)
        else:
            di = datetime.date(ano_rit, 7, 1)
            df = datetime.date(ano_rit, 12, 31)
        data_inicio_pgd = self.pit.adesao.primeiro_dia_pgd_nessa_adesao()
        if data_inicio_pgd > di:
            di = data_inicio_pgd
        ultimo_dia_pgd = self.pit.adesao.ultimo_dia_pgd_nessa_adesao()
        if ultimo_dia_pgd and ultimo_dia_pgd < df:
            df = ultimo_dia_pgd
        return di, df

    def get_periodo_semestre_rit_antes_rit(self):
        # Semestre do RIT
        # - Se o RIT for do mês de MAI
        #   - O semestre do RIT será JAN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre do RIT será JUL a DEZ
        # O semestre anterior ao RIT será
        # - Se o RIT for do mês de MAI
        #   - O semestre anterior será JAN a ABR
        # - Se o RIT for do mês de NOV
        #   - O semestre anterior será JUL a OUT
        # Considerar ainda data de adesão ao PGD e eventual desligamento
        di = None
        mes_rit = self.get_data_inicial().month
        ano_rit = self.get_data_inicial().year
        if mes_rit <= 6:
            di = datetime.date(ano_rit, 1, 1)
        else:
            di = datetime.date(ano_rit, 7, 1)
        data_inicio_pgd = self.pit.adesao.primeiro_dia_pgd_nessa_adesao()
        if data_inicio_pgd > di:
            di = data_inicio_pgd

        df = self.get_data_inicial() - relativedelta(days=1)

        if di > df:
            return None, None

        return di, df

    def get_periodo_semestre_rit_pos_rit(self):
        # Semestre do RIT
        # - Se o RIT for do mês de MAI
        #   - O semestre do RIT será JAN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre do RIT será JUL a DEZ
        # O semestre posterior ao RIT será
        # - Se o RIT for do mês de MAI
        #   - O semestre posterior será JUN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre posterior será DEZ a DEZ
        # Considerar ainda data de adesão ao PGD e eventual desligamento
        di = self.get_data_final() + relativedelta(days=1)

        df = None
        mes_rit = self.get_data_inicial().month
        ano_rit = self.get_data_inicial().year
        if mes_rit <= 6:
            df = datetime.date(ano_rit, 6, 30)
        else:
            df = datetime.date(ano_rit, 12, 31)
        ultimo_dia_pgd = self.pit.adesao.ultimo_dia_pgd_nessa_adesao()
        if ultimo_dia_pgd and ultimo_dia_pgd < df:
            df = ultimo_dia_pgd

        if di > df:
            return None, None

        return di, df

    def get_porcentagem_execucao(self):
        if self.tempo_executado and self.tempo_planejado:
            return Decimal(self.tempo_executado / self.tempo_planejado * 100).quantize(Decimal(10) ** 0)
        return 0

    def get_porcentagem_entrega(self):
        if self.tempo_executado_entregue and self.tempo_planejado:
            return Decimal(self.tempo_executado_entregue / self.tempo_planejado * 100).quantize(Decimal(10) ** 0)
        return 0

    def get_porcentagem_homologacao(self):
        if self.tempo_executado_homologado and self.tempo_planejado:
            return Decimal(self.tempo_executado_homologado / self.tempo_planejado * 100).quantize(Decimal(10) ** 0)
        return 0

    """
    # Todos os metodos foram substituidos por atributos calculados
    def get_total_tempo_planejado_cadastrado(self):
        return gv(self.relatorioindividualtrabalhoatividade_set.filter(situacao=RelatorioIndividualTrabalhoAtividade.CADASTRADO).aggregate(v=Sum('tempo_planejado')))

    def get_total_tempo_planejado_autorizado(self):
        return gv(self.relatorioindividualtrabalhoatividade_set.filter(situacao=RelatorioIndividualTrabalhoAtividade.AUTORIZADO).aggregate(v=Sum('tempo_planejado')))

    def get_total_tempo_planejado_cancelado(self):
        return gv(self.relatorioindividualtrabalhoatividade_set.filter(situacao=RelatorioIndividualTrabalhoAtividade.CANCELADO).aggregate(v=Sum('tempo_planejado')))
    """

    def calcular_rit(self, forcar_recalcular_tempo_previsto=False):
        atividades = RelatorioIndividualTrabalhoAtividade.objects.filter(rit=self).exclude(situacao=RelatorioIndividualTrabalhoAtividade.CANCELADO)

        # -------------------
        # Calcula os tempos
        # -------------------
        # Previsto
        self.tempo_previsto = self.get_tempo_previsto(forcar_recalcular=forcar_recalcular_tempo_previsto)
        # Planejado
        self.tempo_planejado = gv(atividades.aggregate(v=Sum('tempo_planejado')))
        self.tempo_planejado_cadastrado = gv(
            atividades.filter(situacao=RelatorioIndividualTrabalhoAtividade.CADASTRADO).aggregate(v=Sum('tempo_planejado'))
        )
        self.tempo_planejado_autorizado = gv(
            atividades.filter(situacao=RelatorioIndividualTrabalhoAtividade.AUTORIZADO).aggregate(v=Sum('tempo_planejado'))
        )
        self.tempo_planejado_cancelado = gv(
            atividades.filter(situacao=RelatorioIndividualTrabalhoAtividade.CANCELADO).aggregate(v=Sum('tempo_planejado'))
        )
        # Executado
        self.tempo_executado = gv(atividades.aggregate(v=Sum('total_tempo_executado')))
        self.tempo_executado_entregue = gv(atividades.aggregate(v=Sum('total_tempo_executado_entregue')))
        self.tempo_executado_nao_entregue = gv(atividades.aggregate(v=Sum('total_tempo_executado_nao_entregue')))
        self.tempo_executado_ajustado_pela_faixa_complexidade = gv(
            atividades.aggregate(v=Sum('total_tempo_executado_ajustado_pela_faixa_complexidade'))
        )
        # Homologado
        self.tempo_executado_homologado = gv(atividades.aggregate(v=Sum('total_tempo_executado_homologado')))
        self.tempo_executado_homologado_ajustado_pela_faixa_complexidade = gv(
            atividades.aggregate(v=Sum('total_tempo_executado_homologado_ajustado_fx_comp'))
        )

    def get_atividades_pode_receber_entregas(self):
        # Todas as atividades AUTORIZADAS
        # Nao usamos a regra RelatorioIndividualTrabalhoAtividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor()
        # - Por conta de desempenho
        # - Para continuar listando respectiva atividade no RIT (Execução)
        # Com isso foi necessário distribuir essa regra em outros pontos
        return RelatorioIndividualTrabalhoAtividade.objects.filter(rit=self, situacao=RelatorioIndividualTrabalhoAtividade.AUTORIZADO).select_related(
            'atividade_pts__plano_trabalho_setorial', 'atividade_pts', 'atividade_pts__atividade'
        )

    def pode_receber_entregas(self, user):
        if not user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega'):
            return False

        # RIT permite
        situacao_rit_permite = not self.entregue
        if not situacao_rit_permite:
            return False

        pode_editar = self.pode_chefe_servidor_editar(user)
        if not pode_editar:
            return False

        # PIT permite
        pit_permite = self.pit.situacao == PlanoIndividualTrabalho.AUTORIZADO
        if not pit_permite:
            return False

        # Atividade permite
        atividades_permitem = self.get_atividades_pode_receber_entregas().exists()
        return atividades_permitem

    def get_entregas(self):
        return RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self)

    def pode_visualizar(self, user):
        # Se ja foi homologado de forma definitiva
        if self.foi_avaliado():
            return False

        return self.pit.pode_visualizar(user)

    def pode_entregar_entrega(self, user):
        # Utilizado apenas para habilitar e desabilitar elementos de interface
        return self.pit.adesao.servidor == user.get_relacionamento()

    @staticmethod
    def get_rits_relacionados_ao_chefe(user, lista_setores_que_sou_chefe_hoje=None, queryset=None):
        # --------------------------------------------
        # Busca os RITs relacionados ao chefe
        # - Aqueles que potenciamente
        #   - O chefe pode cadastra/alterar entregas
        #   - O chefe pode avaliar uma entrega
        #   - O chefe pode aprovar/homologar de forma definitiva
        # --------------------------------------------

        # Setores que o user é chefe
        setores = lista_setores_que_sou_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())

        # PTSs de cada um dos setores que o user é chefe (PTSs relacionados ao chefe)
        ptss = PlanoTrabalhoSetorial.get_pts_dos_setores(setores)

        # Atividades dos PTSs relacionados ao chefe
        atividades_ptss = PlanoTrabalhoSetorialAtividades.objects.filter(plano_trabalho_setorial__in=ptss)

        # Rits que possuem vinculo com o chefe
        rits_atividades = RelatorioIndividualTrabalhoAtividade.objects.filter(
            situacao=RelatorioIndividualTrabalhoAtividade.AUTORIZADO, atividade_pts__in=atividades_ptss
        )
        if rits_atividades:
            queryset = queryset or RelatorioIndividualTrabalho.objects.all()
            queryset = queryset.filter(id__in=rits_atividades.distinct('rit__id').values_list('rit__id', flat=True))
            queryset = queryset.select_related('pit', 'pit__adesao', 'pit__adesao__servidor', 'pit__adesao__servidor__setor', 'pit__periodo_pit_rit')
            return queryset

        return RelatorioIndividualTrabalho.objects.none()

    def foi_avaliado(self):
        # Se o RIT foi avaliado/homologado de forma definitiva pelo chefe
        # - Preferimos os flags do RIT (`aprovado_definitivo` / `homologado_definitivo`) quando preenchidos
        # - Caso contrário, consideramos que o RIT foi avaliado se todas as entregas válidas
        #   foram avaliadas (aprovado=True e homologado=True)
        if self.aprovado_definitivo is not None and self.homologado_definitivo is not None:
            return True

        # Fallback: considerar entregas como critério de avaliação
        from django.db.models import Q

        entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self).exclude(
            situacao=RelatorioIndividualTrabalhoAtividadeEntrega.CANCELADO
        )
        if not entregas.exists():
            return False

        pendentes = entregas.filter(Q(aprovado__isnull=True) | Q(homologado__isnull=True) | Q(aprovado=False) | Q(homologado=False))
        return not pendentes.exists()

    foi_avaliado.short_description = 'Avaliado'
    foi_avaliado.boolean = True

    def foi_entregue_mas_nao_avaliado(self):
        return self.entregue and not self.foi_avaliado()

    def pode_avaliar_entregas_rit(self, user, lista_setores_user_eh_chefe_hoje=None, validar_pode_chefe_editar=True):
        # ---------------------------------------------------------------------
        # Se um chefe pode avaliar alguma das entregas vinculadas a este RIT
        # ---------------------------------------------------------------------
        tem_permissao = user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')
        if not tem_permissao:
            return False

        # Pode avaliar entregas se:
        # - Se o RIT ainda não foi avaliado (Aprovado/Homologado)
        if self.foi_avaliado():
            return False
        # Setores que o user é chefe
        setores = lista_setores_user_eh_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())
        # - Se o chefe puder editar este RIT
        if validar_pode_chefe_editar:
            if not self.pit.pode_chefe_editar(user, lista_setores_user_eh_chefe_hoje=setores):
                return False
        # - Se o PIT estiver autorizado
        situacao_pit_permite = self.pit.situacao == PlanoIndividualTrabalho.AUTORIZADO
        if not situacao_pit_permite:
            return False

        # Se o chefe pode avaliar alguma entrega existente neste RIT
        # - Se existe alguma entrega pendente ou não de avaliação (enquanto o RIT não for aprovado e homologado as avaliações das entregas podem mudar)
        # PTSs de cada um dos setores que o user é chefe
        # ptss = PlanoTrabalhoSetorial.get_pts_dos_setores(setores)
        # Entregas relacionadas a algum PTs do chefe
        # entregas_podem_ser_avaliadas_pelo_chefe = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self, situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE, rit_atividade__atividade_pts__plano_trabalho_setorial__id__in=ptss).exists()
        entregas_podem_ser_avaliadas_pelo_chefe = RelatorioIndividualTrabalhoAtividadeEntrega.get_entregas_posso_avaliar(
            user, lista_setores_user_eh_chefe_hoje=setores
        ).exists()

        return entregas_podem_ser_avaliadas_pelo_chefe

    def possui_pendencias_avaliacao_entregas_rit(self, user, setores_sou_chefe_hoje=None, validar_pode_chefe_editar=True):
        # ---------------------------------------------------------------------
        # Se existe pendencia de avalica de entregas pelo chefe neste RIT
        # ---------------------------------------------------------------------
        tem_permissao = user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')

        if not tem_permissao:
            return False

        # Pode avaliar entregas se:
        # - Se o RIT ainda não foi Aprovado/Homologado
        # - Se o chefe puder editar este RIT
        # - Se o PIT estiver autorizado
        foi_avaliado = not self.foi_avaliado()
        if not foi_avaliado:
            return False

        if validar_pode_chefe_editar:
            pode_editar_pit = self.pit.pode_chefe_editar(user)
            if not pode_editar_pit:
                return False

        situacao_pit_permite = self.pit.situacao == PlanoIndividualTrabalho.AUTORIZADO
        if not situacao_pit_permite:
            return False

        # Se o chefe pode avaliar alguma entrega existente neste RIT
        # - Se existe alguma entrega pendente ou não de avaliação (enquanto o RIT não for aprovado e homologado as avaliações das entregas podem mudar)
        # Setores que o user é chefe
        if not setores_sou_chefe_hoje:
            setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())

        # PTSs de cada um dos setores que o user é chefe
        ptss = PlanoTrabalhoSetorial.get_pts_dos_setores(setores_sou_chefe_hoje)

        # Entregas relacionadas a algum PTs do chefe
        entregas_devem_ser_avaliadas_pelo_chefe = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(
            rit_atividade__rit=self,
            situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE,
            aprovado__isnull=True,
            rit_atividade__atividade_pts__plano_trabalho_setorial__id__in=ptss,
        ).exists()

        # return foi_avaliado and pode_editar_pit and situacao_pit_permite and entregas_devem_ser_avaliadas_pelo_chefe
        return entregas_devem_ser_avaliadas_pelo_chefe

    @staticmethod
    def get_rits_possui_pendencias_avaliacao_entregas_rit(user, lista_rits=None, setores_sou_chefe_hoje=None):
        # RETORNA UM QUERYSET COM BASE NA MESMA REGRA DO "possui_pendencias_avaliacao_entregas_rit"

        # Pode avaliar entregas se:
        # - Se o RIT ainda não foi Aprovado/Homologado
        #   - Equivalente a "not self.foi_avaliado()"
        rits = lista_rits or RelatorioIndividualTrabalho.objects.filter(aprovado_definitivo__isnull=False, homologado_definitivo__isnull=False)
        # - Se o PIT estiver autorizado
        #   - Equivalente a "self.pit.situacao in [PlanoIndividualTrabalho.AUTORIZADO]"
        rits = rits.filter(pit__situacao__in=[PlanoIndividualTrabalho.AUTORIZADO])

        # Se o chefe pode avaliar alguma entrega existente neste RIT
        # - Se existe alguma entrega pendente ou não de avaliação (enquanto o RIT não for aprovado e homologado as avaliações das entregas podem mudar)
        # Setores que o user é chefe
        if not setores_sou_chefe_hoje:
            setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        # PTSs de cada um dos setores que o user é chefe
        ptss = PlanoTrabalhoSetorial.get_pts_dos_setores(setores_sou_chefe_hoje)
        # Entregas relacionadas a algum PTs do chefe
        rits_devem_ser_avaliadas_pelo_chefe = (
            RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(
                rit_atividade__rit__in=rits,
                situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE,
                aprovado__isnull=True,
                rit_atividade__atividade_pts__plano_trabalho_setorial__id__in=ptss,
            )
            .values('rit_atividade__rit')
            .distinct('rit_atividade__rit')
        )
        rits = rits.filter(id__in=rits_devem_ser_avaliadas_pelo_chefe)

        # Pode avaliar entregas se:
        # - Se o chefe puder editar este RIT
        rits_pode_editar = []
        for rit in rits:
            if rit.pit.pode_chefe_editar(user):
                rits_pode_editar.append(rit.id)
        if rits_pode_editar:
            rits = rits.filter(id__in=rits_pode_editar)

        return rits

    def get_setor_a_homologar_rit(self):
        if not self.pit.estah_cancelado() and not self.foi_avaliado():
            return self.pit.adesao.servidor.setor
        return None

    def existe_entregas_nao_entregues(self):
        return RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(
            rit_atividade__rit=self, situacao=RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO
        ).exists()

    def get_ptss_das_entregas_a_avaliar_do_rit(self):
        if not self.pit.estah_cancelado() and not self.foi_avaliado():
            entregas_devem_ser_avaliadas_pelo_chefe = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(
                rit_atividade__rit=self, situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE, aprovado__isnull=True
            )
            ptss = entregas_devem_ser_avaliadas_pelo_chefe.values_list(
                'rit_atividade__atividade_pts__plano_trabalho_setorial__id', flat=True
            ).distinct()
            if ptss:
                return PlanoTrabalhoSetorial.objects.filter(id__in=ptss)
        return None

    def pode_entregar_rit(self, user):
        servidor_pode = self.pode_servidor_editar(user)
        situacao_pit_permite = self.pit.situacao == PlanoIndividualTrabalho.AUTORIZADO

        # Se a situacao esta ok
        rit_foi_entregue = self.entregue

        if not (servidor_pode and situacao_pit_permite and not rit_foi_entregue):
            return False

        if servidor_pode and situacao_pit_permite and not rit_foi_entregue:
            # Se todas as entregas foram entregues (exceto as que foram canceladas)
            # - Deve haver ao menos uma entrega entregue
            existe_entregas_pedentes = (
                RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self)
                .filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO)
                .exists()
            )
            existe_entregas_validas = (
                RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self)
                .filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE)
                .exists()
            )

            return existe_entregas_validas and not existe_entregas_pedentes

        return False

    def pode_homologar_rit(self, user=None, lista_setores_user_eh_chefe_hoje=None, pode_chefe_editar=None, validar_pode_chefe_editar=True):
        # Se user for None testa apenas as condicoes que nao dependem de user
        # - usado por self.get_setor_a_homologar_rit

        if user:
            relacionamento = user.get_relacionamento()
            lista_setores_user_eh_chefe_hoje = lista_setores_user_eh_chefe_hoje or setores_que_sou_chefe_hoje(relacionamento)

        if validar_pode_chefe_editar:
            servidor_pode = False
            if user:
                servidor_pode = pode_chefe_editar or self.pode_chefe_editar(user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje)
                if not servidor_pode:
                    return False

        foi_avaliado = self.foi_avaliado()
        rit_foi_entregue = self.entregue
        if foi_avaliado or not rit_foi_entregue:
            return False

        # Se existem entregas validas
        entregas_pendentes_apenas_cadastradas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(
            rit_atividade__rit=self, situacao=RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO
        ).exists()
        entregas_pendentes_de_analise = (
            RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade__rit=self)
            .filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE, aprovado__isnull=True)
            .exists()
        )
        entregas_pendentes = entregas_pendentes_apenas_cadastradas or entregas_pendentes_de_analise
        if entregas_pendentes:
            return False

        # Apenas chefe pode
        if user:
            if self.pit.adesao.servidor.setor not in lista_setores_user_eh_chefe_hoje:
                return False
        return True

    def pode_reabrir_rit(self, user, lista_setores_user_eh_chefe_hoje=None):
        # Devolve o RIT para o servidor alterar algo
        # - Devolve um RIT que foi entregue ou homologado (a qualquer tempo)

        # Tem permissao
        if not user.has_perm('pgd.change_planoindividualtrabalho'):
            return False

        # Se o PIT estiver cancelado nao pode
        if self.pit.estah_cancelado():
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Pode se adesao estiver vigente
        # - Se estiver desligado precisa ta na carencia
        if not self.pit.adesao.estah_vigente_e_na_carencia:
            return False

        # O chefe do setor deve estar vinculado ao pit que deseja editar
        if not lista_setores_user_eh_chefe_hoje:
            relacionamento = user.get_relacionamento()
            lista_setores_user_eh_chefe_hoje = setores_que_sou_chefe_hoje(relacionamento)
        pits_do_chefe = (
            PlanoIndividualTrabalho.get_pits_chefe_setor(
                user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje, somente_ids=True, pit=self.pit
            )
            .filter(pk=self.pit.pk)
            .exists()
        )
        if not pits_do_chefe:
            return False

        # Tem que ter sido entregue OU avaliado
        # E nao pode ter sido avaliado e nem homologado
        rit_foi_entregue = self.entregue
        rit_foi_avaliado = self.foi_avaliado()
        pit_homologado_definitivo = self.pit.homologado_definitivo
        return rit_foi_entregue or rit_foi_avaliado and pit_homologado_definitivo

    @staticmethod
    def get_rits_ativos_adesao(adesao):
        # Lista os RITs dos PITs ativos da adesão
        situacoes_ativo = [PlanoIndividualTrabalho.CADASTRADO, PlanoIndividualTrabalho.AGUARDANDO_PARECER, PlanoIndividualTrabalho.AUTORIZADO]
        return RelatorioIndividualTrabalho.objects.filter(pit__adesao=adesao, pit__situacao__in=situacoes_ativo).order_by(
            'pit__data_inicial', 'periodo'
        )

    @staticmethod
    def get_rits_ativos_adesao_alinhados_com_a_data(adesao, data):
        # Lista os RITs dos PITs ativos da adesão
        situacoes_ativo = [PlanoIndividualTrabalho.CADASTRADO, PlanoIndividualTrabalho.AGUARDANDO_PARECER, PlanoIndividualTrabalho.AUTORIZADO]
        return RelatorioIndividualTrabalho.objects.filter(pit__adesao=adesao, pit__situacao__in=situacoes_ativo).order_by(
            'pit__data_inicial', 'periodo'
        )

    @staticmethod
    def get_ultimo_rit_ativo_homologado_adesao(adesao):
        # Ultimo RIT dos PITs ativos da adesão E que está homologado
        rits = RelatorioIndividualTrabalho.get_rits_ativos_adesao(adesao)
        if rits:
            return rits.filter(homologado_definitivo=True).last()
        return None

    @staticmethod
    def get_rits_homologados(adesao):
        rits = RelatorioIndividualTrabalho.get_rits_ativos_adesao(adesao)
        if rits:
            return rits.filter(entregue=True, aprovado_definitivo=True, homologado_definitivo=True)
        return None

    @staticmethod
    def get_ultimo_rit_ativo_adesao(adesao):
        # Ultimo RIT dos PITs ativos da adesão E que está homologado
        rits = RelatorioIndividualTrabalho.get_rits_ativos_adesao(adesao)
        if rits:
            return rits.last()
        return None

    @staticmethod
    def get_rits_podem_ser_copiados(adesao, rit_alvo):
        # Lista os RITs (PIT Planejamento) que podem ter suas atividades copiadas para outro RIT que esta sendo criado
        return RelatorioIndividualTrabalho.objects.filter(pit__adesao=adesao, pit__situacao=PlanoIndividualTrabalho.AUTORIZADO).exclude(
            id=rit_alvo.id
        )

    def get_atividades_podem_ser_copiadas_de_um_rit(self):
        # Lista as atividades que podem ser copiadas de um pit para outro
        # - Apenas as atividades podem ser copiadas
        # - Apenas as atividades AUTORIZADAS serão copiadas
        # - Apenas atividades em que o servidor tenha adesao vigente ao PTS relacionado serão copiadas
        atividades_rit = self.get_atividades()
        ids_ativividades_pts_vigente = []
        for atividade in atividades_rit:
            if atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
                ids_ativividades_pts_vigente.append(atividade.id)

        return atividades_rit.filter(id__in=ids_ativividades_pts_vigente)

    @staticmethod
    def get_rits_servidor(servidor):
        return RelatorioIndividualTrabalho.objects.filter(pit__adesao__servidor=servidor).order_by('-pit__data_inicial', '-periodo')

    @staticmethod
    def get_rits_por_adesao_servidor(adesao):
        return RelatorioIndividualTrabalho.objects.filter(pit__adesao=adesao).order_by('-pit__data_inicial', '-periodo')

    def get_absolute_url(self):
        return f'/pgd/visualizar_pit_completo/{self.pit.id}'

    # ---------------------------------------------------
    # Calculos e cadastros de distribuicao de horas do RIT (apenas avaliados definitivamente)
    # ---------------------------------------------------
    def pode_distribuir_horas(self, user):
        # Situacao do PIT permite
        if self.pit.situacao != self.pit.AUTORIZADO:
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Pode se adesao estiver ativa
        # - OU Pode se estiver desligado mas ainda estiver na carencia
        if not self.pit.adesao.estah_vigente_e_na_carencia:
            return False

        # Se ja foi homologado de forma definitiva
        # Se eh Servidor deste PIT
        # - Se eh o servidor Adesao ao PGD vinculada a este PIT
        return bool(self.foi_avaliado() and self.pit.adesao.servidor == user.get_relacionamento() and self.get_tempo_homologado() > 0)

    def cadastrar_saldo_externo_rit(
        self,
        data_inicio_utilizacao,
        data_fim_utilizacao,
        valor_saldo_em_segundos,
        informar_compensacao_automaticamente,
        situacao=None,
        detalhamento=None,
    ):
        # Cadastro manual de saldo externo relacionado ao um RIT
        rit = self

        data_cadastro = get_datetime_now()

        servidor_destinatario = rit.pit.adesao.servidor
        servidor_validador = None  # será o chefe imediato (resolvido automaticamente)
        servidor_cadastrador = servidor_validador
        observacoes_servidor_validador = rit.get_verbose_rit_servidor()

        if detalhamento:
            detalhamento = f'{rit.get_verbose_rit_servidor()} - para -  {detalhamento}'
        else:
            detalhamento = rit.get_verbose_rit_servidor()

        # um mesmo rit pode está associado a um ou mais saldos externos
        um_rit_varios_saldos_externos = True

        r_saldo_externo = SaldoExterno.cadastrar_saldo_externo(
            data_cadastro=data_cadastro,
            servidor_destinatario=servidor_destinatario,
            valor_saldo_em_segundos=valor_saldo_em_segundos,
            data_inicio_utilizacao=data_inicio_utilizacao,
            data_fim_utilizacao=data_fim_utilizacao,
            informar_compensacao_automaticamente=informar_compensacao_automaticamente,
            observacoes_servidor_validador=observacoes_servidor_validador,
            detalhamento=detalhamento,
            servidor_cadastrador=servidor_cadastrador,
            servidor_validador=servidor_validador,
            model_instance_origem=rit,
            unique_together_with_model_instance_origem=not um_rit_varios_saldos_externos,
            situacao=situacao,
        )

        if not r_saldo_externo.is_realizado:
            raise Exception('Erro ao cadastrar saldo externo!')

        return r_saldo_externo

    def atualizar_horas_previstas_rit(self):
        # -------------------------------------------------------------
        # Atualiza horas previstas do RIT
        # - usado apenas pela distribuicao de horas do rit
        # -------------------------------------------------------------
        dados_horas_ponto_servidor = self.get_dados_horas_ponto_servidor()
        self.tempo_previsto = self.get_tempo_previsto(forcar_recalcular=True, dados_horas_ponto_servidor=dados_horas_ponto_servidor)
        self.save()

        return True

    def distribuir_horas_automaticamente(self, apenas_periodo_rit=False):
        # =============================================================
        # Distribui automaticamente as horas do RIT homologado
        # =============================================================
        """
        A distribuição de horas é feita apenas para RITs homologados. Assim, apenas a CH homologada é distribuída para
        efeitos de compensação no relatório de horas (relatório de frequência) do servidor

        A distribuição segue a seguinte ordem de prioridade
        - Distribui a CH homologada para o período do RIT
        - Caso ainda tenha CH restante é distribuída para meses anteriores ao período do RIT
        - Caso ainda tenha CH restante é distribuída para as compensações específicas compensáveis por CH deste RIT
        - Caso ainda tenha CH restante é distribuída para os meses seguintes ao RIT

        """

        # Dados iniciais
        # --------------------------------------
        ch_ainda_nao_distribuida = 0
        dados_horas_ponto_servidor = self.get_dados_horas_ponto_servidor()
        totais_dados_horas_ponto_servidor = dados_horas_ponto_servidor.get_totais()
        ch_homologada = self.get_tempo_homologado() * 3600
        # Recalcula tempo previsto
        self.tempo_previsto = self.get_tempo_previsto(forcar_recalcular=True, dados_horas_ponto_servidor=dados_horas_ponto_servidor)
        self.save()
        tempo_previsto = self.tempo_previsto * 3600

        # -------------------------------------------------------------
        # PERIODO DO RIT
        # -------------------------------------------------------------
        # Calculo de horas
        # --------------------------------------
        # As horas serão distribuídas com o objetivo de compensar o que for possível do período do RIT
        # - Se a CH homologada for 100h e a CH prevista for 100h, serão distribuídas 100h para o período do RIT
        # - Se a CH homologada for 90h e a CH prevista for 100h, serão distribuídas 90h para o período do RIT
        # - Se a CH homologada for 110h e a CH prevista for 100h, serão distribuídas 100h para o período do RIT
        #   e teremos 10h restantes para outras distribuições

        """
            Período do RIT

            CH Prevista (CP)        |----------------------------------------|
            CH Ponto Batido (PB)           |------|     |---|         |--|
            CH Homologada 1 (CH)    |----------------------------------------|
            CH Homologada 2 (CH)    |---------------------------------|
            CH Homologada 3 (CH)    |-----------------------------------------------|

            CH Distribuída (CD):
                CH >= CP?
                    CD = CP
                    Restante = CH - CP
                CH < CP?
                    CD = CH
                    Restante = 0

            PB não limita CD em nenhum caso, além de não influenciar no valor de Restante.

            CD não é influenciada pelo Débito de CH do período.
                - O usuário deve ser informado sobre possiveís implicações onde é possível
                que haja um valor de CD "sobrando" (quando CD > Débito de CH) que não poderá
                ser utilizado paras os demais períodos/escopos de distribuição: semestre anterior,
                compensações específicas e semestre posterior. Isso pode não ser intuitivo para o usuário,
                que poderá alegar que existe CH sobrando no PGD e que não pode usar para quitar débitos em aberto,
                por exemplo, no semestre do RIT (erro #6076, issue #11218).
        """

        horas_a_serem_distribuidas_para_periodo_rit = 0
        if ch_homologada >= tempo_previsto:
            horas_a_serem_distribuidas_para_periodo_rit = tempo_previsto
            ch_ainda_nao_distribuida = Decimal(ch_homologada) - Decimal(horas_a_serem_distribuidas_para_periodo_rit)
        else:
            horas_a_serem_distribuidas_para_periodo_rit = ch_homologada
            ch_ainda_nao_distribuida = 0
        ch_distribuido_periodo_rit = horas_a_serem_distribuidas_para_periodo_rit

        # para o saldo externo do período do rit, considera apenas o débito a ser compensado
        # no limite da CH a ser distribuída no período do rit, pois há casos em que a
        # CH a ser distribuída no período do rit é menor que o débito no mesmo período
        ch_saldo_externo_periodo_rit = totais_dados_horas_ponto_servidor.total_restante_debito
        if ch_saldo_externo_periodo_rit > ch_distribuido_periodo_rit:
            ch_saldo_externo_periodo_rit = ch_distribuido_periodo_rit

        # Cadastra Saldo Externo
        # --------------------------------------
        saldo_externo_detalhamento = []

        if ch_distribuido_periodo_rit > ch_saldo_externo_periodo_rit:
            saldo_externo_detalhamento.append(f'Compensação de {format_time(ch_saldo_externo_periodo_rit)} no período do RIT.')
            saldo_externo_detalhamento.append(f'Nesse período, foram {format_time(ch_distribuido_periodo_rit)} distribuídas e')
            saldo_externo_detalhamento.append(f'{format_time(ch_saldo_externo_periodo_rit)} disponibilizadas para compensação dos débitos.')
            saldo_externo_detalhamento.append('Essa diferença deve-se a uma eventual carga horária trabalhada e contabilizada')
            saldo_externo_detalhamento.append('no registro de frequências (registro de frequência em período de PGD).')

        saldo_externo_periodo_rit = self.cadastrar_saldo_externo_rit(
            self.get_data_inicial(),
            self.get_data_final(),
            valor_saldo_em_segundos=int(ch_saldo_externo_periodo_rit),
            informar_compensacao_automaticamente=True,
            detalhamento=' '.join(saldo_externo_detalhamento),
        )

        if not saldo_externo_periodo_rit.is_realizado:
            raise Exception('Erro ao distribuir horas para o período do RIT')

        # -------------------------------------------------------------
        # SEMESTRE DO RIT - Anterior RIT
        # -------------------------------------------------------------
        ch_distribuido_semestre_rit__periodo_anterior_rit = 0
        saldo_externo_semestre_rit__periodo_anterior_rit = None
        data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit_antes_rit()
        if not apenas_periodo_rit and (ch_ainda_nao_distribuida > 0 and (data_inicio_utilizacao and data_fim_utilizacao)):
            #  Calculo de horas para meses anteriores ao periodo do RIT
            # --------------------------------------
            # As horas ainda não distribuídas serão distribuídas com o objetivo de compensar apenas o que for necessário para os
            # meses anteriores (dentro do semestre do RIT) ao RIT
            # O cálculo das hioras será da seguinte forma
            # - Se houver ch ainda não distriuída
            # - Verifica se tem meses (se tem datas) anteriores ao RIT (dentro do seu semestre)
            # - Calcula a CH necessária para o semestre do período do RIT
            # - Calcula valor a ser distribuído e ainda vai ter ch ainda não distribuída
            tempo_debito_nao_compensado_anterior_periodo_rit = self.get_tempo_debito_nao_compensado_anterior_periodo_rit()
            if tempo_debito_nao_compensado_anterior_periodo_rit > 0:
                if ch_ainda_nao_distribuida <= tempo_debito_nao_compensado_anterior_periodo_rit:
                    ch_distribuido_semestre_rit__periodo_anterior_rit = ch_ainda_nao_distribuida
                    ch_ainda_nao_distribuida = 0
                else:
                    ch_distribuido_semestre_rit__periodo_anterior_rit = tempo_debito_nao_compensado_anterior_periodo_rit
                    ch_ainda_nao_distribuida = Decimal(ch_ainda_nao_distribuida) - Decimal(ch_distribuido_semestre_rit__periodo_anterior_rit)

            # Cadastra Saldo Externo
            # --------------------------------------
            if ch_distribuido_semestre_rit__periodo_anterior_rit > 0:
                saldo_externo_semestre_rit__periodo_anterior_rit = self.cadastrar_saldo_externo_rit(
                    data_inicio_utilizacao,
                    data_fim_utilizacao,
                    valor_saldo_em_segundos=int(ch_distribuido_semestre_rit__periodo_anterior_rit),
                    informar_compensacao_automaticamente=True,
                )
                if not saldo_externo_semestre_rit__periodo_anterior_rit.is_realizado:
                    raise Exception('Erro ao distribuir horas para o semestre do RIT')

        # -------------------------------------------------------------
        # COMPENSAÇÕES ESPECÍFICAS
        # -------------------------------------------------------------
        dias_compesacao_compensavel = []  # compensacao, dia, tempo
        dias_compesacao_compensavel_saldo_externo = []  # compensacao, dia, tempo, saldo externo
        ch_distribuicao_compensacao_especifica = 0
        if not apenas_periodo_rit and (ch_ainda_nao_distribuida > 0):
            # Calculo de horas para compensações específicas compensáveis pela CH deste RIT
            # --------------------------------------
            # As horas ainda não distribuídas serão distribuídas com o objetivo de compensar o que for possível considerando
            # as compensações específicas compensáveis pela CH deste RIT
            # Essa distribuição será ralizada da seguinte forma
            # - Seleciona as compensações específicas compensáveis pela CH deste RIT e que ainda tenham CH Pendente
            #   - A ordem será que finalizar período de compensação primeiro
            # - Para cada compensação
            #   - Para cada dia verifica e guarda das horas faltam ser compensadas
            #   - Soma a ch a ser compensada
            #   - Se ainda tiver ch_ainda_nao_distribuida executa a mesma rotina para a próxima compensação
            compensacoes_compensaveis = obter_compensacoes_especificas_compesaveis_rit(self)
            if compensacoes_compensaveis:
                # Ordena para iniciar compensacao pela que está mais perto de acabar o Período de Compensação e que tem mais ch pedente
                compensacoes_compensaveis.sort(key=lambda v: (v[1], -v[2]))
                # Para cada compensação selecionada guarda os dias que serão compensáveis e sua devida ch pendente
                for compesacao_compensavel in compensacoes_compensaveis:
                    if ch_ainda_nao_distribuida > 0:
                        for dia, ch_a_ser_compensada in compesacao_compensavel[3].items():
                            if ch_ainda_nao_distribuida > 0:
                                ch_distribuicao = 0
                                if ch_ainda_nao_distribuida <= ch_a_ser_compensada:
                                    ch_distribuicao = ch_ainda_nao_distribuida
                                    ch_ainda_nao_distribuida = 0
                                else:
                                    ch_distribuicao = ch_a_ser_compensada
                                    ch_ainda_nao_distribuida = Decimal(ch_ainda_nao_distribuida) - Decimal(ch_distribuicao)
                                if ch_distribuicao > 0:
                                    ch_distribuicao_compensacao_especifica = Decimal(ch_distribuicao_compensacao_especifica) + Decimal(
                                        ch_distribuicao
                                    )
                                    dias_compesacao_compensavel.append((compesacao_compensavel, dia, ch_distribuicao))
                            else:
                                break
                    else:
                        break

            # [Compensações Específicas] Cadastra saldo externo
            # --------------------------------------
            for dcc in dias_compesacao_compensavel:
                se = self.cadastrar_saldo_externo_rit(
                    dcc[1], dcc[1], valor_saldo_em_segundos=int(dcc[2]), informar_compensacao_automaticamente=True, detalhamento=str(dcc[0][0])
                )
                dias_compesacao_compensavel_saldo_externo.append((dcc[0][0], dcc[1], dcc[2], se))

        # -------------------------------------------------------------
        # SEMESTRE DO RIT - Posterior RIT
        # -------------------------------------------------------------
        # TODAS as horas ainda não distribuídas (QUE SOBRARAM DEPOIS DE TODAS AS ETAPAS) serão
        # distribuídas para utilização nos meses seguintes ao RIT
        ch_distribuido_semestre_rit__periodo_posterior_rit = 0
        saldo_externo_semestre_rit__periodo_posterior_rit = None
        data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit_pos_rit()
        if not apenas_periodo_rit and (ch_ainda_nao_distribuida > 0 and (data_inicio_utilizacao and data_fim_utilizacao)):
            # Calculo de horas
            # --------------------------------------
            ch_distribuido_semestre_rit__periodo_posterior_rit = ch_ainda_nao_distribuida
            ch_ainda_nao_distribuida = 0

            # Cadastra Saldo Externo
            # --------------------------------------
            saldo_externo_semestre_rit__periodo_posterior_rit = self.cadastrar_saldo_externo_rit(
                data_inicio_utilizacao,
                data_fim_utilizacao,
                valor_saldo_em_segundos=int(ch_distribuido_semestre_rit__periodo_posterior_rit),
                informar_compensacao_automaticamente=False,
                situacao=SaldoExterno.SITUACAO_VALIDADO,
            )
            if not saldo_externo_semestre_rit__periodo_posterior_rit.is_realizado:
                raise Exception('Erro ao distribuir horas para o semestre do RIT')

        # -------------------------------------------------------------
        # SEMESTRE DO RIT - Se ainda tiver CH pendente
        # -------------------------------------------------------------

        # -------------------------------------------------------------
        # ** Cadastra dados da distribuição de horas do RIT **
        # -------------------------------------------------------------
        # Geral
        # -----------------------
        self.bloqueado_para_distribuicao_manual = False
        if ch_ainda_nao_distribuida > 0:
            self.bloqueado_para_distribuicao_manual = True
        self.ch_distribuida = ch_homologada
        if apenas_periodo_rit:
            self.ch_distribuida = ch_distribuido_periodo_rit
        self.ch_a_distribuir = ch_ainda_nao_distribuida
        self.ch_distribuido_periodo_rit = ch_distribuido_periodo_rit
        self.ch_distribuido_semestre_rit = decimal.Decimal(str(ch_distribuido_semestre_rit__periodo_anterior_rit)) + decimal.Decimal(
            str(ch_distribuido_semestre_rit__periodo_posterior_rit)
        )
        self.ch_distribuido_compesacao_especifica = ch_distribuicao_compensacao_especifica
        self.save()
        # Período rit
        # -----------------------
        dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
        dh.rit = self
        dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.PERIODO_RIT
        dh.saldo_externo = saldo_externo_periodo_rit.cadastro
        dh.ch_distribuida = ch_distribuido_periodo_rit
        dh.save()
        # Semestre do RIT - Anterior RIT
        # -----------------------
        if saldo_externo_semestre_rit__periodo_anterior_rit:
            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_ANTES_RIT
            dh.saldo_externo = saldo_externo_semestre_rit__periodo_anterior_rit.cadastro
            dh.ch_distribuida = ch_distribuido_semestre_rit__periodo_anterior_rit
            dh.save()
        # Compensações Específicas
        # -----------------------
        for dccse in dias_compesacao_compensavel_saldo_externo:
            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.COMPENSACAO_ESPECIFICA
            dh.saldo_externo = dccse[3].cadastro
            dh.ch_distribuida = dccse[2]
            dh.data = dccse[1]
            dh.compensacao_especifica = dccse[0]
            dh.save()
        # Semestre do RIT - Posterior RIT
        # -----------------------
        if saldo_externo_semestre_rit__periodo_posterior_rit:
            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_POS_RIT
            dh.saldo_externo = saldo_externo_semestre_rit__periodo_posterior_rit.cadastro
            dh.ch_distribuida = ch_distribuido_semestre_rit__periodo_posterior_rit
            dh.save()

        return True

    def desfazer_distribuicao_horas(self):
        # -------------------------------------------------------------
        # Desfaz TODAS as distribuicoes de horas
        # -------------------------------------------------------------
        self.ch_distribuida = 0
        self.ch_a_distribuir = self.get_tempo_homologado() * 3600
        self.ch_distribuido_periodo_rit = 0
        self.ch_distribuido_semestre_rit = 0
        self.ch_distribuido_compesacao_especifica = 0
        self.bloqueado_para_distribuicao_manual = False
        self.save()

        RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=self).delete()
        content_type_rit = ContentType.objects.get_for_model(RelatorioIndividualTrabalho)
        SaldoExterno.objects.filter(origem_type=content_type_rit, origem_id=self.id).delete()

        return True

    # Distribuição manual - Semestre
    # -----------------------------------------
    def pode_ajustar_distribuicao_horas_semestre_rit(self, user):
        return bool(
            self.pode_distribuir_horas(user)
            and not self.ch_distribuido_semestre_rit > 0
            and self.ch_a_distribuir > 0
            and self.ch_distribuido_periodo_rit > 0
            and not self.bloqueado_para_distribuicao_manual
        )

    def ajustar_distribuicao_horas_semestre_rit(self, compensar_automaticamente=True, ch=0, distribuir_todas=False):
        # -------------------------------------------------------------
        # Desfaz a atual, cria uma nova e atualiza dados das distribuicoes
        # - Utilizado no ajuste MANUAL
        # -------------------------------------------------------------

        # Dados iniciais
        # --------------------------------------
        ch_ainda_nao_distribuida = ch
        if distribuir_todas:
            ch_ainda_nao_distribuida = self.ch_a_distribuir

        if not compensar_automaticamente:
            ch_efetivamente_distribuida = ch_ainda_nao_distribuida

            # Geral
            # -----------------------
            self.ch_distribuida = self.ch_distribuida + ch_efetivamente_distribuida
            self.ch_a_distribuir = self.ch_a_distribuir - ch_efetivamente_distribuida
            self.ch_distribuido_semestre_rit = ch_efetivamente_distribuida
            self.save()

            # Gera saldo externo pro semestre (referente ao rit) todo
            # ch em segundos
            data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit()
            saldo_externo_semestre_rit = self.cadastrar_saldo_externo_rit(
                data_inicio_utilizacao,
                data_fim_utilizacao,
                valor_saldo_em_segundos=ch_efetivamente_distribuida,
                informar_compensacao_automaticamente=False,
                situacao=SaldoExterno.SITUACAO_VALIDADO,
            )
            if not saldo_externo_semestre_rit.is_realizado:
                raise Exception('Erro ao distribuir horas para o semestre do RIT')

            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_RIT
            dh.saldo_externo = saldo_externo_semestre_rit.cadastro
            dh.ch_distribuida = ch_efetivamente_distribuida
            dh.save()

            return True

        # -------------------------------------------------------------
        # SEMESTRE DO RIT - Anterior RIT
        # -------------------------------------------------------------
        ch_distribuido_semestre_rit__periodo_anterior_rit = 0
        saldo_externo_semestre_rit__periodo_anterior_rit = None
        data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit_antes_rit()
        if ch_ainda_nao_distribuida > 0 and (data_inicio_utilizacao and data_fim_utilizacao):
            #  Calculo de horas para meses anteriores ao periodo do RIT
            # --------------------------------------
            # As horas ainda não distribuídas serão distribuídas com o objetivo de compensar apenas o que for necessário para os
            # meses anteriores (dentro do semestre do RIT) ao RIT
            # O cálculo das hioras será da seguinte forma
            # - Se houver ch ainda não distriuída
            # - Verifica se tem meses (se tem datas) anteriores ao RIT (dentro do seu semestre)
            # - Calcula a CH necessária para o semestre do período do RIT
            # - Calcula valor a ser distribuído e ainda vai ter ch ainda não distribuída
            tempo_debito_nao_compensado_anterior_periodo_rit = self.get_tempo_debito_nao_compensado_anterior_periodo_rit()
            if tempo_debito_nao_compensado_anterior_periodo_rit > 0:
                if ch_ainda_nao_distribuida <= tempo_debito_nao_compensado_anterior_periodo_rit:
                    ch_distribuido_semestre_rit__periodo_anterior_rit = ch_ainda_nao_distribuida
                    ch_ainda_nao_distribuida = 0
                else:
                    ch_distribuido_semestre_rit__periodo_anterior_rit = tempo_debito_nao_compensado_anterior_periodo_rit
                    ch_ainda_nao_distribuida = ch_ainda_nao_distribuida - ch_distribuido_semestre_rit__periodo_anterior_rit
            # Cadastra Saldo Externo
            # --------------------------------------
            if ch_distribuido_semestre_rit__periodo_anterior_rit > 0:
                saldo_externo_semestre_rit__periodo_anterior_rit = self.cadastrar_saldo_externo_rit(
                    data_inicio_utilizacao,
                    data_fim_utilizacao,
                    valor_saldo_em_segundos=ch_distribuido_semestre_rit__periodo_anterior_rit,
                    informar_compensacao_automaticamente=True,
                )
                if not saldo_externo_semestre_rit__periodo_anterior_rit.is_realizado:
                    raise Exception('Erro ao distribuir horas para o semestre do RIT')

        # -------------------------------------------------------------
        # SEMESTRE DO RIT - Posterior RIT
        # -------------------------------------------------------------
        # TODAS as horas ainda não distribuídas (QUE SOBRARAM DEPOIS DE TODASAS ETAPAS) serão
        # distribuídas para utilização nos meses seguintes ao RIT
        ch_distribuido_semestre_rit__periodo_posterior_rit = 0
        saldo_externo_semestre_rit__periodo_posterior_rit = None
        data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit_pos_rit()
        if ch_ainda_nao_distribuida > 0 and (data_inicio_utilizacao and data_fim_utilizacao):
            # Calculo de horas
            # --------------------------------------
            ch_distribuido_semestre_rit__periodo_posterior_rit = ch_ainda_nao_distribuida
            ch_ainda_nao_distribuida = 0

            # Cadastra Saldo Externo
            # --------------------------------------
            saldo_externo_semestre_rit__periodo_posterior_rit = self.cadastrar_saldo_externo_rit(
                data_inicio_utilizacao,
                data_fim_utilizacao,
                valor_saldo_em_segundos=ch_distribuido_semestre_rit__periodo_posterior_rit,
                informar_compensacao_automaticamente=True,
            )
            if not saldo_externo_semestre_rit__periodo_posterior_rit.is_realizado:
                raise Exception('Erro ao distribuir horas para o semestre do RIT')
        # -------------------------------------------------------------
        # ** Cadastra dados da distribuição de horas do RIT **
        # -------------------------------------------------------------
        ch_efetivamente_distribuida = ch_distribuido_semestre_rit__periodo_anterior_rit + ch_distribuido_semestre_rit__periodo_posterior_rit

        # Geral
        # -----------------------
        self.ch_distribuida = self.ch_distribuida + ch_efetivamente_distribuida
        self.ch_a_distribuir = self.ch_a_distribuir - ch_efetivamente_distribuida
        self.ch_distribuido_semestre_rit = ch_efetivamente_distribuida
        self.save()

        # Semestre do RIT - Anterior RIT
        # -----------------------
        if saldo_externo_semestre_rit__periodo_anterior_rit:
            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_ANTES_RIT
            dh.saldo_externo = saldo_externo_semestre_rit__periodo_anterior_rit.cadastro
            dh.ch_distribuida = ch_distribuido_semestre_rit__periodo_anterior_rit
            dh.save()

        # Semestre do RIT - Posterior RIT
        # -----------------------
        if saldo_externo_semestre_rit__periodo_posterior_rit:
            dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
            dh.rit = self
            dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_POS_RIT
            dh.saldo_externo = saldo_externo_semestre_rit__periodo_posterior_rit.cadastro
            dh.ch_distribuida = ch_distribuido_semestre_rit__periodo_posterior_rit
            dh.save()

        return True

    def pode_desfazer_distribuicao_horas_semestre(self, user):
        return bool(self.pode_distribuir_horas(user) and self.ch_distribuido_semestre_rit > 0 and not self.bloqueado_para_distribuicao_manual)

    def desfazer_distribuicao_horas_semestre(self):
        # -------------------------------------------------------------
        # Desfaz as distribuicoes de horas relacionadas ao semestre do RIT
        # -------------------------------------------------------------
        self.ch_distribuida = self.ch_distribuida - self.ch_distribuido_semestre_rit
        self.ch_a_distribuir = self.ch_a_distribuir + self.ch_distribuido_semestre_rit
        self.ch_distribuido_semestre_rit = 0
        self.save()

        distribuicoes = RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(
            tipo__in=[
                RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_ANTES_RIT,
                RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_POS_RIT,
                RelatorioIndividualTrabalhoDistribuicaoHoras.SEMESTRE_RIT,
            ]
        )
        ids_saldos_externos = []
        for distribuicao in distribuicoes:
            ids_saldos_externos.append(distribuicao.saldo_externo.id)
        distribuicoes.delete()
        SaldoExterno.objects.filter(id__in=ids_saldos_externos).delete()

        return True

    # Distribuição manual - Compensaçao Específica
    # -----------------------------------------
    def pode_ajustar_distribuicao_compensacao_especifica(self, user, compensacao_especifica=None, compensacoes_compensaveis=None):
        if self.pode_distribuir_horas(user) and self.ch_a_distribuir > 0:
            if not compensacao_especifica:
                return True
            if not self.ch_distribuido_periodo_rit > 0:
                return False
            # Se ja tiver istribuicao para esta compensação específica então pode fazer distribuição para esta compensação
            tem_distribuicao = RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(
                rit=self, compensacao_especifica=compensacao_especifica
            ).exists()
            # Tem que ser compensável por este rit
            if not compensacoes_compensaveis:
                compensacoes_compensaveis = obter_compensacoes_especificas_compesaveis_rit(self)
            eh_compensavel = False
            for comp_e in compensacoes_compensaveis:
                if comp_e[0] == compensacao_especifica:
                    eh_compensavel = True
                    break
            # Tem que ter CH pendente
            tem_ch_pendente = compensacao_especifica.total_carga_horaria_pendente()
            if tem_ch_pendente > 0:
                tem_ch_pendente = True
            else:
                tem_ch_pendente = False

            if not tem_distribuicao and eh_compensavel and tem_ch_pendente and not self.bloqueado_para_distribuicao_manual:
                return True
        return False

    def ajustar_distribuicao_compensacao_especifica(self, compensacao_especifica):
        # Desfaz anteriores (apenas ouriundas deste RIT)
        self.desfazer_distribuicao_compensacao_especifica(compensacao_especifica=compensacao_especifica)

        # Pega toda a ch_a_distribuir e distribui para esta compensação específica
        dias_compesacao_compensavel = []  # compensacao, dia, tempo
        ch_ainda_nao_distribuida = self.ch_a_distribuir
        ch_distribuicao_compensacao_especifica = 0
        # Para a compensação selecionada guarda os dias que serão compensáveis e sua devida ch pendente
        compesacao_compensavel = compensacao_especifica
        if ch_ainda_nao_distribuida > 0:
            totais_ch = compesacao_compensavel.totais_ch(carga_horaria_pendente=True)
            total_carga_horaria_pendente_por_dia = totais_ch['total_carga_horaria_pendente_por_dia']
            for dia, ch_a_ser_compensada in total_carga_horaria_pendente_por_dia.items():
                if ch_ainda_nao_distribuida > 0:
                    ch_distribuicao = 0
                    if ch_ainda_nao_distribuida <= ch_a_ser_compensada:
                        ch_distribuicao = ch_ainda_nao_distribuida
                        ch_ainda_nao_distribuida = 0
                    else:
                        ch_distribuicao = ch_a_ser_compensada
                        ch_ainda_nao_distribuida = ch_ainda_nao_distribuida - ch_distribuicao
                    if ch_distribuicao > 0:
                        ch_distribuicao_compensacao_especifica += ch_distribuicao
                        dias_compesacao_compensavel.append((compesacao_compensavel, dia, ch_distribuicao))
                else:
                    break

        if ch_distribuicao_compensacao_especifica > 0:
            # Cadastra saldo externo
            # --------------------------------------
            dias_compesacao_compensavel_saldo_externo = []
            for dcc in dias_compesacao_compensavel:
                se = self.cadastrar_saldo_externo_rit(
                    dcc[1], dcc[1], valor_saldo_em_segundos=dcc[2], informar_compensacao_automaticamente=True, detalhamento=str(dcc[0])
                )
                dias_compesacao_compensavel_saldo_externo.append((dcc[0], dcc[1], dcc[2], se))

            # Atualiza RIT
            # --------------------------------------
            for dccse in dias_compesacao_compensavel_saldo_externo:
                dh = RelatorioIndividualTrabalhoDistribuicaoHoras()
                dh.rit = self
                dh.tipo = RelatorioIndividualTrabalhoDistribuicaoHoras.COMPENSACAO_ESPECIFICA
                dh.saldo_externo = dccse[3].cadastro
                dh.ch_distribuida = dccse[2]
                dh.data = dccse[1]
                dh.compensacao_especifica = dccse[0]
                dh.save()

            self.ch_distribuida = self.ch_distribuida + ch_distribuicao_compensacao_especifica
            self.ch_a_distribuir = self.ch_a_distribuir - ch_distribuicao_compensacao_especifica
            self.ch_distribuido_compesacao_especifica = self.ch_distribuido_compesacao_especifica + ch_distribuicao_compensacao_especifica
            self.save()

        return True

    def pode_desfazer_distribuicao_compensacao_especifica(self, user, compensacao_especifica):
        if self.pode_distribuir_horas(user) and self.ch_distribuido_compesacao_especifica > 0 and not self.bloqueado_para_distribuicao_manual:
            # Se tiver ch de rit para esta compensação específica então pode desfazer distribuição para esta compensação
            if RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=self, compensacao_especifica=compensacao_especifica).exists():
                return True
        return False

    def desfazer_distribuicao_compensacao_especifica(self, compensacao_especifica):
        # -------------------------------------------------------------
        # Desfaz as distribuições de horas das compensações específicas - apenas distribuições oriundas deste RIT
        # -------------------------------------------------------------
        distribuicoes_para_esta_compensacao = RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(
            rit=self, tipo=RelatorioIndividualTrabalhoDistribuicaoHoras.COMPENSACAO_ESPECIFICA
        )
        distribuido_para_esta_compensacao = gv(distribuicoes_para_esta_compensacao.aggregate(v=Sum('ch_distribuida')))
        self.ch_distribuida = self.ch_distribuida - distribuido_para_esta_compensacao
        self.ch_a_distribuir = self.ch_a_distribuir + distribuido_para_esta_compensacao
        self.ch_distribuido_compesacao_especifica = self.ch_distribuido_compesacao_especifica - distribuido_para_esta_compensacao
        self.save()

        distribuicoes = distribuicoes_para_esta_compensacao
        ids_saldos_externos = []
        for distribuicao in distribuicoes:
            ids_saldos_externos.append(distribuicao.saldo_externo.id)
        distribuicoes.delete()
        SaldoExterno.objects.filter(id__in=ids_saldos_externos).delete()

        return True

    @staticmethod
    def get_rits_a_avaliar_pelo_chefe(servidor):
        user = servidor.get_user()

        lista_setores_que_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        lista_setores_que_sou_chefe_hoje2 = servidor.historico_funcao_ativa.filter(funcao__codigo__in=Funcao.get_codigos_funcao_chefia()).values_list(
            'setor_suap', flat=True
        )

        qs = RelatorioIndividualTrabalho.get_rits_relacionados_ao_chefe(user, lista_setores_que_sou_chefe_hoje)
        qs = qs.exclude(pit__adesao__servidor=servidor)

        # Entrege Sim
        qs = qs.filter(entregue=True)

        # A Avaliar
        qs = qs.filter(Q(aprovado_definitivo__isnull=True) | Q(homologado_definitivo__isnull=True))

        # Todos que sou chefe imediato
        qs = qs.filter(
            Q(pit__adesao__servidor__setor__in=lista_setores_que_sou_chefe_hoje2)
            | (
                Q(pit__adesao__servidor__setor__superior__in=lista_setores_que_sou_chefe_hoje2)
                & Q(pit__adesao__servidor__funcao__isnull=False)
                & Q(pit__adesao__servidor__funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            )
        )

        return qs


class RelatorioIndividualTrabalhoDistribuicaoHoras(models.ModelPlus):
    rit = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalho', verbose_name='RIT')

    PERIODO_RIT = 1
    SEMESTRE_ANTES_RIT = 2
    COMPENSACAO_ESPECIFICA = 3
    SEMESTRE_POS_RIT = 4
    SEMESTRE_RIT = 5
    TIPO_DISTRIBUICAO_CHOICES = [
        [PERIODO_RIT, 'Período do RIT'],
        [SEMESTRE_ANTES_RIT, 'Meses (no semestre do RIT) anteriores ao RIT'],
        [COMPENSACAO_ESPECIFICA, 'Compensacao específica'],
        [SEMESTRE_RIT, 'Semestre do RIT'],
        [SEMESTRE_POS_RIT, 'Meses (no semestre do RIT) posteriores ao RIT'],
    ]
    tipo = models.PositiveIntegerField('Tipo', choices=TIPO_DISTRIBUICAO_CHOICES, default=PERIODO_RIT)

    saldo_externo = models.ForeignKeyPlus('ponto.SaldoExterno')
    ch_distribuida = models.DecimalFieldPlus(verbose_name='CH distribuída')

    # Uso específico para COMPENSACAO_ESPECIFICA
    data = models.DateFieldPlus(verbose_name='Data compensação', blank=True, null=True)
    compensacao_especifica = models.ForeignKeyPlus('ponto.RecessoOpcaoEscolhida', blank=True, null=True)

    class Meta:
        verbose_name = 'Distribuição de Horas do RIT'
        verbose_name_plural = 'Distribuições de Horas do RIT'


class RegistroAcaoRelatorioIndividualTrabalho(RegistroAcaoPGD):
    # Planejamento das atividades
    TIPO_ADICIONOU_ATIVIDADE = 1
    TIPO_EDITOU_ATIVIDADE = 2
    TIPO_CANCELOU_ATIVIDADE = 3
    TIPO_APROVOU_HOMOLOGOU_ATIVIDADE = 13
    TIPO_REMOVEU_ATIVIDADE = 4

    # Cadastro entrega
    TIPO_CADASTROU_ENTREGA = 5
    TIPO_ALTEROU_ENTREGA = 6
    TIPO_REMOVEU_ENTREGA = 7

    # Entrega de cada Entrega de uma atividade
    TIPO_ENTREGOU_ENTREGA = 8
    TIPO_AVALIOU_ENTREGA = 9
    TIPO_REVERTEU_ENTREGA = 10

    # Entrega final do RIT
    TIPO_ENTREGOU_RIT = 11
    TIPO_APROVOU_HOMOLOGOU_RIT = 12
    TIPO_REABRIU_RIT = 14  # registros antigos de reabertura ficaram com 12 (homologação)

    TIPO_CHOICES = (
        (TIPO_ADICIONOU_ATIVIDADE, 'Atividade Adicionada'),
        (TIPO_EDITOU_ATIVIDADE, 'Editou Adicionada'),
        (TIPO_CANCELOU_ATIVIDADE, 'Atividade Cancelada'),
        (TIPO_APROVOU_HOMOLOGOU_ATIVIDADE, 'Aprovou/Homologou a atividade'),
        (TIPO_CADASTROU_ENTREGA, 'Entrega cadastrada'),
        (TIPO_ALTEROU_ENTREGA, 'Entrega editada'),
        (TIPO_REMOVEU_ENTREGA, 'Entrega removida'),
        (TIPO_ENTREGOU_ENTREGA, 'Entrega realizada'),
        (TIPO_AVALIOU_ENTREGA, 'Entrega avaliada'),
        (TIPO_REVERTEU_ENTREGA, 'Reverteu entrega'),
        (TIPO_ENTREGOU_RIT, 'Entregou em Definitivo o RIT'),
        (TIPO_APROVOU_HOMOLOGOU_RIT, 'Aprovou/Homologou RIT'),
        (TIPO_REABRIU_RIT, 'Reabriu RIT'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    rit = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalho', editable=False, null=True)
    rit_atividade = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalhoAtividade', editable=False, null=True)
    rit_atividade_entrega = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalhoAtividadeEntrega', editable=False, null=True)


class RelatorioIndividualTrabalhoAtividade(models.ModelPlus):
    # Planejamento

    SEARCH_FIELDS = ['atividade_pts__atividade__titulo']

    rit = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalho', verbose_name='PIT', editable=False)
    original = models.ForeignKeyPlus('self', null=True, blank=True, verbose_name='Atividade Original')

    # Planejamento
    # --------------------
    CADASTRADO = 1
    AUTORIZADO = 2
    CANCELADO = 3
    SITUACAO_ATIVIDADE_CHOICES = [[CADASTRADO, 'Cadastrado'], [AUTORIZADO, 'Autorizado'], [CANCELADO, 'Cancelado']]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_ATIVIDADE_CHOICES, default=CADASTRADO)
    atividade_pts = models.ForeignKeyPlus('pgd.PlanoTrabalhoSetorialAtividades', verbose_name='Atividade', editable=False)
    data_prazo = models.DateFieldPlus(verbose_name='Prazo', null=True, blank=True)
    tempo_planejado = models.DecimalFieldPlus(verbose_name='Tempo planejado', help_text='Em horas', default=0)
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)

    # Consolidado do Executado
    # --------------------
    total_tempo_executado = models.DecimalFieldPlus(verbose_name='Total de horas da execução', default=0, blank=True, null=True)
    total_tempo_executado_entregue = models.DecimalFieldPlus(verbose_name='Total de horas da execução (entregue)', default=0, blank=True, null=True)
    total_tempo_executado_nao_entregue = models.DecimalFieldPlus(
        verbose_name='Total de horas da execução (a entregar)', default=0, blank=True, null=True
    )
    total_tempo_executado_ajustado_pela_faixa_complexidade = models.DecimalFieldPlus(
        verbose_name='Total do Tempo ajustado pela faixa de complexidade', blank=True, null=True, editable=False
    )

    # Consolidado do Aprovado/Homologado
    # --------------------
    # Observacoes
    # - A faixa de complexidade sera calculada (talve seja uma média das entregas) apenas quando for enviar pela API
    total_tempo_executado_homologado = models.DecimalFieldPlus(verbose_name='Total de horas homologadas', default=0, blank=True, null=True)
    total_tempo_executado_homologado_ajustado_fx_comp = models.DecimalFieldPlus(
        verbose_name='Total de horas homologadas ajustado pela faixa de complexidade', blank=True, null=True, editable=False
    )

    class Meta:
        verbose_name = 'Atividade'
        verbose_name_plural = 'Atividades'

    def __str__(self):
        return str(self.atividade_pts)

    def atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor(self):
        # Se a "atividade_pts" esta vinculada a um PTS "vigente" do servidor vinculado ao PIT/RIT
        solicitacoes_adesao_pts_vigentes_do_servidor = SolicitacaoAdesaoPtsServidor.get_vigentes(self.rit.pit.adesao)
        if solicitacoes_adesao_pts_vigentes_do_servidor:
            for solicitacao_adesao_pts in solicitacoes_adesao_pts_vigentes_do_servidor:
                if self.atividade_pts.plano_trabalho_setorial == solicitacao_adesao_pts.plano_trabalho_setorial:
                    return True

        return False

    def atividade_estah_com_prazo_alinhado_com_periodo_pit(self):
        if self.data_prazo:
            return self.data_prazo <= self.rit.get_data_final()
        return True

    # Editar atividades do planejamento
    def pode_editar(self, user=None):
        user = user or tl.get_user()
        return (
            self.rit.pode_servidor_editar(user)
            and self.situacao in [self.CADASTRADO, self.AUTORIZADO]
            and self.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor()
        )

    # Remover atividades do planejamento
    def pode_remover(self, user=None):
        if self.eh_espelho():
            return False
        user = user or tl.get_user()
        # Pode remover apenas as atividades que ainda nao foram autorizadas
        return user and self.pode_editar(user) and self.situacao == self.CADASTRADO

    # Cancelar atividades do planejamento
    def pode_cancelar(self, user=None):
        # Pode ser removida quando tiver apenas como autorizada OU quando for espelho
        user = user or tl.get_user()
        return user and self.pode_editar(user) and (self.situacao == self.AUTORIZADO or self.eh_espelho())

    def eh_espelho(self):
        return self.original

    def tem_espelho(self):
        return RelatorioIndividualTrabalhoAtividade.objects.filter(original__id=self.id).exists()

    def calcular_atividade_rit(self):
        entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(rit_atividade=self)

        entregas_avaliadas_a_calcular = entregas.filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE, aprovado=True)
        entregas_executadas_a_calcular = entregas_avaliadas_a_calcular | entregas.filter(
            situacao__in=[RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO, RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE],
            aprovado__isnull=True,
        )

        pode_calcular_execucao = entregas_executadas_a_calcular.exists()
        pode_calcular_avaliacao = entregas_avaliadas_a_calcular.exists()

        # -------------------
        # Calcula Execucao
        # -------------------
        self.total_tempo_executado = None
        self.total_tempo_executado_entregue = None
        self.total_tempo_executado_nao_entregue = None
        self.total_tempo_executado_ajustado_pela_faixa_complexidade = None

        if pode_calcular_execucao:
            # total_tempo_executado
            # total_tempo_executado_entregue
            # total_tempo_executado_nao_entregue
            # ----------------------------------
            self.total_tempo_executado = gv(entregas_executadas_a_calcular.aggregate(v=Sum('tempo_executado')))
            self.total_tempo_executado_entregue = gv(
                entregas_executadas_a_calcular.filter(situacao__in=[RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE]).aggregate(
                    v=Sum('tempo_executado')
                )
            )
            self.total_tempo_executado_nao_entregue = gv(
                entregas_executadas_a_calcular.filter(situacao__in=[RelatorioIndividualTrabalhoAtividadeEntrega.CADASTRADO]).aggregate(
                    v=Sum('tempo_executado')
                )
            )

            # total_tempo_executado_ajustado_pela_faixa_complexidade
            # ----------------------------------
            self.total_tempo_executado_ajustado_pela_faixa_complexidade = gv(
                entregas_executadas_a_calcular.aggregate(v=Sum('tempo_ajustado_pela_faixa_complexidade_entrega'))
            )

        # -------------------
        # Calcula Avaliacao
        # -------------------
        self.total_tempo_executado_homologado = None
        self.total_tempo_executado_homologado_ajustado_fx_comp = None

        if pode_calcular_avaliacao:
            # total_tempo_executado_homologado
            # total_tempo_executado_homologado_ajustado_fx_comp
            # ----------------------------------
            self.total_tempo_executado_homologado = gv(entregas_avaliadas_a_calcular.aggregate(v=Sum('tempo_executado_homologado')))
            self.total_tempo_executado_homologado_ajustado_fx_comp = gv(
                entregas_avaliadas_a_calcular.aggregate(v=Sum('total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao'))
            )

        return True

    def pode_chefe_autorizar_atividade(self, user, setores_chefe_hoje=None):
        # Se o chefe pode SOMENTE AUTORIZAR esta atividade especifica
        # - Essa é apenas uma parte da regra e deve ser utilizada em conjunto com outros
        # - Basicamente utilizmos ela na hora que todos os pré-requisitos já foram validados

        if not setores_chefe_hoje:
            relacionamento = user.get_relacionamento()
            setores_chefe_hoje = setores_que_sou_chefe_hoje(relacionamento)

        if not self.tem_espelho():
            # Tentando saber se pode Aprovar
            if self.situacao == RelatorioIndividualTrabalhoAtividade.CADASTRADO:
                # Se pode por ser chefe do PTS
                setor_pts = self.atividade_pts.plano_trabalho_setorial.setor
                if setor_pts in setores_chefe_hoje:
                    return True

        return False


def file_upload_to(instance, filename):
    PRIVATE_ROOT_DIR = 'pgd'
    path = f'{PRIVATE_ROOT_DIR}/{instance.rit_atividade.pk}'
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = f'{instance.pk}.{ext}'
    else:
        filename = f'{uuid4().hex}.{ext}'
    return os.path.join(path, filename)


# ====================================================
# RIT Execucao - Entrega e Avaliacao das Entregas e RIT
# ====================================================


class RelatorioIndividualTrabalhoQuestionario(models.ModelPlus):
    periodo_pit_rit = models.ForeignKeyPlus('pgd.PeriodoPitRit', verbose_name='Período PIT/RIT', editable=False)
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor')

    servidor_respondente = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    questionario_de_chefe = models.BooleanField('Questionário de chefe', default=False)

    data = models.DateTimeFieldPlus('Data', auto_now_add=True, editable=False)

    SIM = 1
    NAO = 2
    ABSTENCAO = 3
    RESPOSTAS_CHOICES = [[SIM, 'Sim'], [NAO, 'Não'], [ABSTENCAO, 'Abstenção']]

    ESTRELA_1 = 1
    ESTRELA_2 = 2
    ESTRELA_3 = 3
    ESTRELA_4 = 4
    ESTRELA_5 = 5
    ESTRELAS_CHOICES = [
        [ESTRELA_1, '1 estrela'],
        [ESTRELA_2, '2 estrelas'],
        [ESTRELA_3, '3 estrelas'],
        [ESTRELA_4, '4 estrelas'],
        [ESTRELA_5, '5 estrelas'],
    ]

    # Servidor e Chefe
    PERGUNTAS_SERVIDOR_CHEFE = ['pergunta_1', 'pergunta_2', 'pergunta_3', 'pergunta_4']
    pergunta_1 = models.TextField(verbose_name='Dificuldades enfrentadas?', blank=True, null=True)
    pergunta_2 = models.TextField(verbose_name='Sugestões para aperfeiçoamento do PGD?', blank=True, null=True)
    pergunta_3 = models.PositiveIntegerField(
        'Você considera o percentual de PGD para o seu setor adequado? Se Não informe o percentual que considera ser adequado',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )
    pergunta_3_complemento = models.DecimalFieldPlus(verbose_name='Percentual de PGD que considera adequado para o seu setor', blank=True, null=True)
    pergunta_4 = models.PositiveIntegerField(
        'Você considera que seu vínculo com os colegas de trabalho sofreram enfraquecimento devido tempo que você permanece remoto?',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )

    # Servidor
    PERGUNTAS_SERVIDOR = ['pergunta_5', 'pergunta_6']
    pergunta_5 = models.PositiveIntegerField(
        'Você considera os equipamentos que você dispõe em casa adequados para desempenhar suas atividades remotamente?',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )
    pergunta_6 = models.PositiveIntegerField(
        'Você considera que seu vínculo com a instituição sofreu enfraquecimento devido tempo que você permanece remoto?',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )

    # Chefe
    PERGUNTAS_CHEFE = ['pergunta_7', 'pergunta_8', 'pergunta_9', 'pergunta_10', 'pergunta_11']
    pergunta_7 = models.TextField(verbose_name='Melhorias percebidas na qualidade dos serviços prestados', blank=True, null=True)
    pergunta_8 = models.PositiveIntegerField('Comprometimento percebido dos participantes', choices=ESTRELAS_CHOICES, blank=True, null=True)
    pergunta_9 = models.PositiveIntegerField(
        'Você considera que a produção do setor aumentou com o PGD?', choices=RESPOSTAS_CHOICES, blank=True, null=True
    )
    pergunta_10 = models.PositiveIntegerField(
        'Você considera que houve falhas de comunicação causadas pelo tempo remoto de trabalho da equipe através do PGD?',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )
    pergunta_11 = models.PositiveIntegerField(
        'Você considera que o % de teletrabalho do setor está adequado? Se Não informe o percentual que considera ser adequado',
        choices=RESPOSTAS_CHOICES,
        blank=True,
        null=True,
    )
    pergunta_11_complemento = models.DecimalFieldPlus(verbose_name='Percentual de PGD que considera adequado para o setor', blank=True, null=True)

    class Meta:
        verbose_name = 'Questionário do RIT'
        verbose_name_plural = 'Questionários do RIT'

    @staticmethod
    def deve_responder_como_servidor(servidor, setor_pit_rit, periodo_pit_rit, lista_setores_que_sou_chefe_hoje=None):
        # Chamado no momento da entrega do RIT (Servidor)
        # - Todas as condições referentes a entrega do RIT já foram testadas por outras rotinas
        # - Essa rotina testa apenas se ele deve responder o questionário ou não

        # Se não precisa para o período
        if not periodo_pit_rit.preencher_questionario_pesquisa:
            return False

        # Só responde se
        # - Não for chefe homologador do setor do pit rit
        # - Se ainda não tiver respondido para este período e para o setor do pit rit
        jah_respondeu = RelatorioIndividualTrabalhoQuestionario.objects.filter(
            periodo_pit_rit=periodo_pit_rit, setor=setor_pit_rit, servidor_respondente=servidor
        ).exists()
        lista_setores_que_sou_chefe_hoje = lista_setores_que_sou_chefe_hoje or setores_que_sou_chefe_hoje(servidor)
        eh_chefe_homologador = setor_pit_rit in lista_setores_que_sou_chefe_hoje
        return bool(not eh_chefe_homologador and not jah_respondeu)

    @staticmethod
    def deve_responder_como_chefe(servidor, setor_pit_rit, periodo_pit_rit, lista_setores_que_sou_chefe_hoje=None):
        # Chamado no momento da homologação do RIT (Chefe)
        # - Todas as condições referentes a homologação do RIT já foram testadas por outras rotinas
        # - Essa rotina testa apenas se ele deve responder o questionário ou não

        # Se não precisa para o período
        if not periodo_pit_rit.preencher_questionario_pesquisa:
            return False

        # Só responde se
        # - Se for chefe homologador do setor
        # - Se ainda não tiver respondido para este período e para o setor SUAP dele
        lista_setores_que_sou_chefe_hoje = lista_setores_que_sou_chefe_hoje or setores_que_sou_chefe_hoje(servidor)
        eh_chefe_homologador = setor_pit_rit in lista_setores_que_sou_chefe_hoje
        jah_respondeu = RelatorioIndividualTrabalhoQuestionario.objects.filter(
            periodo_pit_rit=periodo_pit_rit, setor=setor_pit_rit, servidor_respondente=servidor
        ).exists()
        return bool(eh_chefe_homologador and not jah_respondeu)


class RelatorioIndividualTrabalhoAtividadeEntrega(models.ModelPlus):
    # Execucao

    rit_atividade = models.ForeignKeyPlus('pgd.RelatorioIndividualTrabalhoAtividade', verbose_name='Atividade')

    CADASTRADO = 1
    CANCELADO = 2
    ENTREGUE = 3
    SITUACAO_CICLO_CHOICES = [[CADASTRADO, 'Cadastrado'], [ENTREGUE, 'Entregue'], [CANCELADO, 'Cancelado']]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_CICLO_CHOICES, default=CADASTRADO)

    # -----------------------------
    # Execucao - Cadastro da entrega
    # -----------------------------
    # Dados básicos
    # -------------------
    tipo_entrega = models.ForeignKeyPlus('pgd.AtividadeEntrega', verbose_name='Tipo da Entrega')
    data_iniciou = models.DateFieldPlus(verbose_name='Data que Iniciou')
    data_finalizou = models.DateFieldPlus(verbose_name='Data que Finalizou')
    qtd_entregas = models.PositiveIntegerField(verbose_name='Quantidade de Entregas')
    tempo_executado = models.DecimalFieldPlus(verbose_name='Total de Horas da Execução', help_text='Em horas')
    descricao = models.TextField(verbose_name='Descrição')
    executada_em_teletrabalho = models.BooleanField(verbose_name='Foi executada em teletrabalho?', default=True)
    BAIXA = 1
    MEDIA = 2
    ALTA = 3
    PRIORIDADE_CHOICES = [[BAIXA, 'Baixa'], [MEDIA, 'Média'], [ALTA, 'Alta']]
    prioridade = models.PositiveIntegerField('Prioridade', choices=PRIORIDADE_CHOICES, default=BAIXA)
    anexo = models.PrivateFileField('Arquivo', upload_to=file_upload_to, max_length=400, blank=True, null=True)
    # Cálculos executados pelo SUAP
    # -------------------
    tempo_medio_por_entrega_entrega = models.DecimalFieldPlus(verbose_name='Tempo Médio por Entrega', blank=True, null=True, editable=False)
    faixa_complexidade_entrega = models.ForeignKeyPlus(
        'pgd.ComplexidadeAtividade',
        verbose_name='Faixa de Complexidade',
        blank=True,
        null=True,
        editable=False,
        related_name='rit_atividade_faixa_complexidade_entrega',
    )
    tempo_ajustado_pela_faixa_complexidade_entrega = models.DecimalFieldPlus(
        verbose_name='Tempo ajustado pela Faixa de Complexidade', blank=True, null=True, editable=False
    )
    total_tempo_ajustado_pela_faixa_complexidade_entrega = models.DecimalFieldPlus(
        verbose_name='Total do Tempo ajustado pela Faixa de Complexidade', blank=True, null=True, editable=False
    )

    # -----------------------------
    # Avaliacao - Avaliação da entrega
    # -----------------------------
    # Dados básicos
    # -------------------
    nota = models.DecimalFieldPlus(verbose_name='Nota', default=0, blank=True, null=True)
    tempo_executado_homologado = models.DecimalFieldPlus(verbose_name='Total de Horas Homologadas', default=0, blank=True, null=True)
    justificativa_observacao_avaliacao = models.TextField(verbose_name='Justificativa/Avaliação', blank=True, null=True)
    aprovado = models.BooleanField('Aprovado', null=True)
    homologado = models.BooleanField('Homologado', null=True)
    # Cálculos executados pelo SUAP
    # -------------------
    tempo_medio_por_entrega_avaliacao = models.DecimalFieldPlus(verbose_name='Tempo médio por entrega', blank=True, null=True, editable=False)
    faixa_complexidade_entrega_avaliacao = models.ForeignKeyPlus(
        'pgd.ComplexidadeAtividade',
        verbose_name='Faixa de Complexidade',
        blank=True,
        null=True,
        editable=False,
        related_name='rit_atividade_faixa_complexidade_entrega_avaliacao',
    )
    tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = models.DecimalFieldPlus(
        verbose_name='Tempo ajustado pela faixa de complexidade', blank=True, null=True, editable=False
    )
    total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = models.DecimalFieldPlus(
        verbose_name='Total do Tempo ajustado pela faixa de complexidade', blank=True, null=True, editable=False
    )

    def __str__(self):
        return f'{self.tipo_entrega}'

    # -----------------------------
    # Colunas
    # -----------------------------

    def get_pts(self):
        return self.rit_atividade.atividade_pts.plano_trabalho_setorial

    get_pts.short_description = 'PTS'
    get_pts.admin_order_field = 'rit_atividade__atividade_pts__plano_trabalho_setorial'

    def get_situacao(self):
        return mark_safe(status(self.get_situacao_display()))

    get_situacao.short_description = 'Situação'
    get_situacao.admin_order_field = 'situacao'

    def get_prioridade(self):
        return mark_safe(status(self.get_prioridade_display()))

    get_prioridade.short_description = 'Prioridade'
    get_prioridade.admin_order_field = 'prioridade'

    def get_atividade(self):
        return self.rit_atividade.atividade_pts

    get_atividade.short_description = 'Atividade'
    get_atividade.admin_order_field = 'rit_atividade__atividade_pts'

    def get_atividade_aviso_desligamento(self):
        if not self.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            return mark_safe(f'{self.rit_atividade.atividade_pts} <p class="alert alert-info">Desligado deste PTS. Maiores detalhes no Meu PGD.</p>')
        return self.rit_atividade.atividade_pts

    get_atividade_aviso_desligamento.short_description = 'Atividade'
    get_atividade_aviso_desligamento.admin_order_field = 'rit_atividade__atividade_pts'

    def get_pts(self):
        return mark_safe(f'{self.rit_atividade.atividade_pts.plano_trabalho_setorial}')

    get_pts.short_description = 'PTS'
    get_pts.admin_order_field = 'rit_atividade__atividade_pts__plano_trabalho_setorial'

    def get_pts_atividade(self):
        return mark_safe(
            f'<strong>PTS:</strong> {self.rit_atividade.atividade_pts.plano_trabalho_setorial}<br><strong>Atividade:</strong> {self.rit_atividade.atividade_pts}'
        )

    get_pts_atividade.short_description = 'PTS/Atividade'

    def get_tempo_executado(self):
        return format_hours(self.tempo_executado)

    get_tempo_executado.short_description = 'Total de horas da execução'
    get_tempo_executado.admin_order_field = 'tempo_executado'

    def get_tempo_medio_por_entrega_entrega(self):
        return format_hours(self.tempo_medio_por_entrega_entrega)

    get_tempo_medio_por_entrega_entrega.short_description = 'Tempo médio por entrega'
    get_tempo_medio_por_entrega_entrega.admin_order_field = 'tempo_medio_por_entrega_entrega'

    def get_tempo_faixa_complexidade(self):
        if (
            self.faixa_complexidade_entrega
            and self.faixa_complexidade_entrega.faixa_complexidade
            and self.faixa_complexidade_entrega.faixa_complexidade.complexidade
        ):
            return f'{self.faixa_complexidade_entrega.faixa_complexidade.complexidade} ({(format_hours(self.tempo_ajustado_pela_faixa_complexidade_entrega))})'
        return '-'

    get_tempo_faixa_complexidade.short_description = 'Tempo ajustado pela faixa de complexidade'
    get_tempo_faixa_complexidade.admin_order_field = 'tempo_ajustado_pela_faixa_complexidade_entrega'

    def get_total_tempo_ajustado_pela_faixa_complexidade_entrega(self):
        return format_hours(self.total_tempo_ajustado_pela_faixa_complexidade_entrega)

    get_total_tempo_ajustado_pela_faixa_complexidade_entrega.short_description = 'Total do Tempo ajustado pela faixa de complexidade'
    get_total_tempo_ajustado_pela_faixa_complexidade_entrega.admin_order_field = 'total_tempo_ajustado_pela_faixa_complexidade_entrega'

    def get_foi_aprovado_homologado(self):
        return self.foi_aprovado_homologado()

    get_foi_aprovado_homologado.short_description = 'Aprovado/Homologado'
    get_foi_aprovado_homologado.boolean = True

    # -----------------------------

    def get_prioridade(self):
        return mark_safe(status(self.get_prioridade_display()))

    get_prioridade.short_description = 'Prioridade'
    get_prioridade.admin_order_field = 'prioridade'

    def get_entrega(self):
        return mark_safe(f'<strong>Tipo:</strong> {self.tipo_entrega}<br><strong>Descrição:</strong> {self.descricao}')

    get_entrega.short_description = 'Entrega'
    get_entrega.admin_order_field = 'tipo_entrega__titulo'

    def get_execucao(self):
        periodo = mark_safe(
            f'<strong>De:</strong> {format_datetime(self.data_iniciou)}<br><strong>Até:</strong> {format_datetime(self.data_finalizou)}<br>'
        )
        exec_tempo_executado = mark_safe(f'<strong>Total de horas da execução:</strong> {format_hours(self.tempo_executado)}<br>')

        exec_tempo_medio_por_entrega_entrega = None
        if self.rit_atividade.rit.pode_mostrar_ajustado:
            exec_tempo_medio_por_entrega_entrega = mark_safe(
                f'<strong>Tempo médio por entrega:</strong> {format_hours(self.tempo_medio_por_entrega_entrega)}<br>'
            )

        exec_tempo_faixa_complexidade = '-'
        if (
            self.rit_atividade.rit.pode_mostrar_ajustado
            and self.faixa_complexidade_entrega
            and self.faixa_complexidade_entrega.faixa_complexidade
            and self.faixa_complexidade_entrega.faixa_complexidade.complexidade
            and self.tempo_ajustado_pela_faixa_complexidade_entrega
        ):
            exec_tempo_faixa_complexidade = mark_safe(
                f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {self.faixa_complexidade_entrega.faixa_complexidade.complexidade} ({(format_hours(self.tempo_ajustado_pela_faixa_complexidade_entrega))})<br>'
            )

        exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = ''
        if self.rit_atividade.rit.pode_mostrar_ajustado:
            exec_total_tempo_ajustado_pela_faixa_complexidade_entrega = mark_safe(
                f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(self.total_tempo_ajustado_pela_faixa_complexidade_entrega)}<br>'
            )

        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')
        ico_executada_em_teletrabalho = icone_true if self.executada_em_teletrabalho else icone_false
        se_executada_em_teletrabalho = f'<strong>Executada em Teletrabalho:</strong> {ico_executada_em_teletrabalho}'

        return mark_safe(
            f'{periodo}{exec_tempo_executado}{exec_tempo_medio_por_entrega_entrega}{exec_tempo_faixa_complexidade}{exec_total_tempo_ajustado_pela_faixa_complexidade_entrega}{se_executada_em_teletrabalho}'
        )

    get_execucao.short_description = 'Execução'
    get_execucao.admin_order_field = 'data_iniciou'

    def get_avaliacao(self):
        icone_none = mark_safe('<img src="/static/admin/img/icon-unknown.svg" alt="None">')
        icone_true = mark_safe('<img src="/static/admin/img/icon-yes.svg" alt="True">')
        icone_false = mark_safe('<img src="/static/admin/img/icon-no.svg" alt="False">')
        nota = None
        aprovado = icone_none
        if self.aprovado is not None:
            aprovado = icone_true if self.aprovado else icone_false
        homologado = icone_none
        if self.homologado is not None:
            homologado = icone_true if self.homologado else icone_false
            nota = self.nota
        str = mark_safe(f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado} <br>')
        if nota:
            str = mark_safe(
                f'<strong>Aprovado:</strong> {aprovado}<br><strong>Homologado:</strong> {homologado}<br><strong>Nota:</strong> {nota} <br>'
            )
        aprov_hom = str
        # ------------------------
        aval_tempo = mark_safe(f'<strong>Total de horas homologadas:</strong> {format_hours(self.tempo_executado_homologado)}<br>')
        aval_tempo_medio_por_entrega = ''
        if self.rit_atividade.rit.pode_mostrar_ajustado:
            aval_tempo_medio_por_entrega = mark_safe(
                f'<strong>Tempo médio por entrega:</strong> {format_hours(self.tempo_medio_por_entrega_avaliacao)}<br>'
            )
        fx_complex = '-'
        if (
            self.faixa_complexidade_entrega_avaliacao
            and self.faixa_complexidade_entrega_avaliacao.faixa_complexidade
            and self.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
        ):
            fx_complex = self.faixa_complexidade_entrega_avaliacao.faixa_complexidade.complexidade
        aval_tempo_faixa_complexidade = ''
        aval_total_tempo_ajustado_pela_faixa_complexidade = ''
        if self.rit_atividade.rit.pode_mostrar_ajustado:
            aval_tempo_faixa_complexidade = mark_safe(
                f'<strong>Tempo ajustado pela faixa de complexidade:</strong> {fx_complex} ({(format_hours(self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao))})<br>'
            )
            aval_total_tempo_ajustado_pela_faixa_complexidade = mark_safe(
                f'<strong>Total do Tempo ajustado pela faixa de complexidade:</strong> {format_hours(self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao)}'
            )
        tempos = mark_safe(
            f'{aval_tempo}{aval_tempo_medio_por_entrega}{aval_tempo_faixa_complexidade}{aval_total_tempo_ajustado_pela_faixa_complexidade}'
        )
        # ------------------------
        return mark_safe(f'{aprov_hom}{tempos}')

    get_avaliacao.short_description = 'Avaliação'

    # -----------------------------
    # Outros metodos
    # -----------------------------

    def entrega_estah_com_prazo_alinhado_com_periodo_rit(self):
        return self.data_finalizou <= self.rit_atividade.rit.get_data_final()

    @staticmethod
    def pode_cadastrar(user, rit_atividade):
        tem_permissao_add = user.has_perm('pgd.add_relatorioindividualtrabalhoatividadeentrega')
        # Se pode pelas regras basicas
        if rit_atividade.rit.pode_receber_entregas(user) and tem_permissao_add:
            # Se a rit_atividade pode receber entregas para o servidor vinculado ao PIT/RIT
            # - Considerando suas solicitacoes vigentes de adesao PTS
            return rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor()

        return False

    def pode_visualizar(self, user):
        pode_ver = user.has_perm('pgd.view_relatorioindividualtrabalhoatividadeentrega')
        return self.rit_atividade.rit.pit.pode_visualizar(user) and pode_ver

    def pode_editar(self, user):
        tem_permissao_editar = user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')
        if not tem_permissao_editar:
            return False

        situacao_permite = self.situacao == self.CADASTRADO and self.aprovado is None
        if not situacao_permite:
            return False

        regras_pode_receber_entregas = self.rit_atividade.rit.pode_receber_entregas(user)
        if not regras_pode_receber_entregas:
            return False

        # Nao pode se atividade relacionada nao esa vinculada a um PTS ativo do servidor
        return self.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor()

    def foi_entregue(self):
        return self.situacao == self.ENTREGUE

    def pode_remover(self, user):
        rit_permite = self.pode_editar(user) and not self.foi_entregue()
        user_permite = self.rit_atividade.rit.pit.adesao.servidor == user.get_relacionamento()
        return rit_permite and user_permite

    def pode_entregar(self, user):
        # Se pode entregar uma entrega especifica
        rit_permite = self.pode_editar(user) and not self.foi_entregue()
        user_permite = self.rit_atividade.rit.pit.adesao.servidor == user.get_relacionamento()

        return rit_permite and user_permite

    def pode_reverter_entrega(self, user=None):
        tem_permissao_editar = user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')
        pode_receber_entregas = self.rit_atividade.rit.pode_receber_entregas(user)
        regras_basicas = tem_permissao_editar and pode_receber_entregas and self.foi_entregue()
        if not regras_basicas:
            return False

        # Nao pode se atividade relacionada nao esa vinculada a um PTS ativo do servidor
        return self.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor()

    def foi_aprovado_homologado(self):
        # Se a entregua foi Aprovado e Homologado pelo chefe
        if self.aprovado is None or self.homologado is None:
            return None
        return bool(self.homologado)

    def foi_avaliado(self):
        return self.aprovado is not None or self.homologado is not None

    @staticmethod
    def get_entregas_posso_avaliar(user, lista_setores_user_eh_chefe_hoje=None, rit=None):
        # Entregues no RIT
        # ------------------------------------------------------------
        entregas = RelatorioIndividualTrabalhoAtividadeEntrega.objects.filter(situacao=RelatorioIndividualTrabalhoAtividadeEntrega.ENTREGUE)
        if rit:
            entregas = entregas.filter(rit_atividade__rit=rit)

        # Setores que o user é chefe
        setores = lista_setores_user_eh_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())

        # Se essa entrega especifica pode ser avaliada pelo chefe
        # ------------------------------------------------------------
        # PTSs de cada um dos setores que o user é chefe
        ptss = PlanoTrabalhoSetorial.get_pts_dos_setores(setores)

        # Se a entrega é relacionadas a algum PTs do chefe
        entregas = entregas.filter(rit_atividade__atividade_pts__plano_trabalho_setorial__id__in=ptss).select_related(
            'rit_atividade__atividade_pts',
            'rit_atividade__atividade_pts__plano_trabalho_setorial',
            'tipo_entrega',
            'rit_atividade__atividade_pts__plano_trabalho_setorial__setor',
        )

        return entregas

    def pode_avaliar(self, user, lista_setores_user_eh_chefe_hoje=None, user_pode_avaliar_entregas_rit=None):
        # --------------------------------------------
        # Se essa entrega pode ser avaliada pelo chefe
        # --------------------------------------------

        # Se tem permissao
        tem_permissao = user.has_perm('pgd.change_relatorioindividualtrabalhoatividadeentrega')
        if not tem_permissao:
            return False

        # Se foi entregue
        if not self.foi_entregue():
            return False

        # Setores que o user é chefe
        setores = lista_setores_user_eh_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())

        # Se algum entrega vinculada ao RIT pode ser avaliada pelo chefe
        # ------------------------------------------------------------
        if user_pode_avaliar_entregas_rit is None:
            if not self.rit_atividade.rit.pode_avaliar_entregas_rit(user, lista_setores_user_eh_chefe_hoje=lista_setores_user_eh_chefe_hoje):
                return False
        else:
            if not user_pode_avaliar_entregas_rit:
                return False

        # Nao pode se atividade relacionada nao esa vinculada a um PTS ativo do servidor
        if not self.rit_atividade.atividade_estah_vinculada_a_adesao_pts_vigente_do_servidor():
            return False

        # Se essa entrega especifica pode ser avaliada pelo chefe
        # ------------------------------------------------------------
        # PTSs de cada um dos setores que o user é chefe
        # Se a entrega é relacionadas a algum PTs do chefe
        return RelatorioIndividualTrabalhoAtividadeEntrega.get_entregas_posso_avaliar(user, lista_setores_user_eh_chefe_hoje=setores).exists()

    """
    def calcular_entrega(self):

        pode_calcular_avaliacao = self.situacao == self.ENTREGUE and self.aprovado is not None
        pode_calcular_execucao = (pode_calcular_avaliacao) or (self.situacao in [self.CADASTRADO, self.ENTREGUE] and self.tempo_executado and self.qtd_entregas and self.aprovado is None)

        # -------------------
        # Calcula Execucao
        # -------------------
        self.tempo_medio_por_entrega_entrega = None
        self.faixa_complexidade_entrega = None
        self.tempo_ajustado_pela_faixa_complexidade_entrega = None
        self.total_tempo_ajustado_pela_faixa_complexidade_entrega = None

        if pode_calcular_execucao:
            # tempo_medio_por_entrega_entrega
            # ----------------------------------
            self.tempo_medio_por_entrega_entrega = self.tempo_executado / self.qtd_entregas

            # faixa_complexidade_entrega
            # tempo_ajustado_pela_faixa_complexidade_entrega
            # ----------------------------------
            # - pega a faixa de complexidade (relacionada a atividade) que mais se aproxima ao tempo tempo_executado
            # - qtd horas pela faixa de complexidade
            faixa_complexidade_entrega, tempo_ajustado_pela_faixa_complexidade_entrega = calcula_complexidade_ajustada(self.rit_atividade.atividade_pts.atividade, self.tempo_medio_por_entrega_entrega)
            self.faixa_complexidade_entrega = faixa_complexidade_entrega
            self.tempo_ajustado_pela_faixa_complexidade_entrega = tempo_ajustado_pela_faixa_complexidade_entrega

            # total_tempo_ajustado_pela_faixa_complexidade_entrega
            # ----------------------------------
            self.total_tempo_ajustado_pela_faixa_complexidade_entrega = tempo_ajustado_pela_faixa_complexidade_entrega * self.qtd_entregas

        # -------------------
        # Calcula Avaliacao
        # -------------------
        self.tempo_medio_por_entrega_avaliacao = None
        self.faixa_complexidade_entrega_avaliacao = None
        self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = None
        self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = None

        if pode_calcular_avaliacao:
            # tempo_medio_por_entrega_avaliacao
            # ----------------------------------
            self.tempo_medio_por_entrega_avaliacao = self.tempo_executado_homologado / self.qtd_entregas

            # faixa_complexidade_entrega_avaliacao
            # tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            # ----------------------------------
            # - pega a faixa de complexidade (relacionada a atividade) que mais se aproxima ao tempo tempo_executado
            # - qtd horas pela faixa de complexidade
            faixa_complexidade_entrega_avaliacao, tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = calcula_complexidade_ajustada(self.rit_atividade.atividade_pts.atividade, self.tempo_medio_por_entrega_avaliacao)
            self.faixa_complexidade_entrega_avaliacao = faixa_complexidade_entrega_avaliacao
            self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao

            # total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            # ----------------------------------
            self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao =  tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao * self.qtd_entregas

        return True
    """

    def calcular_entrega(self):
        pode_calcular_execucao = (self.situacao in [self.CADASTRADO, self.ENTREGUE]) and (self.tempo_executado > 0) and (self.qtd_entregas > 0)

        # Método 1: usa o tempo executado e as faixas de complexidade
        # Método 2: usa o temo executado mas não utiliza as faixas de complexidade
        metodo_calculo_rit = self.rit_atividade.rit.get_metodo_calculo_entrega()

        # -------------------
        # Calcula Execucao
        # -------------------
        self.tempo_medio_por_entrega_entrega = None
        self.faixa_complexidade_entrega = None
        self.tempo_ajustado_pela_faixa_complexidade_entrega = None
        self.total_tempo_ajustado_pela_faixa_complexidade_entrega = None

        if pode_calcular_execucao:
            # tempo_medio_por_entrega_entrega
            # ----------------------------------
            self.tempo_medio_por_entrega_entrega = self.tempo_executado / self.qtd_entregas

            # faixa_complexidade_entrega
            # tempo_ajustado_pela_faixa_complexidade_entrega
            # ----------------------------------
            # - pega a faixa de complexidade (relacionada a atividade) que mais se aproxima ao tempo tempo_executado
            # - qtd horas pela faixa de complexidade
            faixa_complexidade_entrega, tempo_ajustado_pela_faixa_complexidade_entrega = calcula_complexidade_ajustada(
                self.rit_atividade.atividade_pts.atividade, self.tempo_executado
            )
            self.faixa_complexidade_entrega = faixa_complexidade_entrega
            if metodo_calculo_rit == '1':
                self.tempo_ajustado_pela_faixa_complexidade_entrega = tempo_ajustado_pela_faixa_complexidade_entrega
            else:
                self.tempo_ajustado_pela_faixa_complexidade_entrega = self.tempo_executado

            # total_tempo_ajustado_pela_faixa_complexidade_entrega
            # ----------------------------------
            if metodo_calculo_rit == '1':
                self.total_tempo_ajustado_pela_faixa_complexidade_entrega = tempo_ajustado_pela_faixa_complexidade_entrega
            else:
                self.total_tempo_ajustado_pela_faixa_complexidade_entrega = self.tempo_executado

        # -------------------
        # Calcula Avaliacao
        # -------------------
        self.tempo_medio_por_entrega_avaliacao = None
        self.faixa_complexidade_entrega_avaliacao = None
        self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = None
        self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = None

        if self.qtd_entregas and self.homologado:
            # tempo_medio_por_entrega_avaliacao
            # ----------------------------------
            self.tempo_medio_por_entrega_avaliacao = self.tempo_executado_homologado / self.qtd_entregas

            # faixa_complexidade_entrega_avaliacao
            # tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            # ----------------------------------
            # - pega a faixa de complexidade (relacionada a atividade) que mais se aproxima ao tempo tempo_executado
            # - qtd horas pela faixa de complexidade
            faixa_complexidade_entrega_avaliacao, tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = calcula_complexidade_ajustada(
                self.rit_atividade.atividade_pts.atividade, self.tempo_executado_homologado
            )
            self.faixa_complexidade_entrega_avaliacao = faixa_complexidade_entrega_avaliacao
            if metodo_calculo_rit == '1':
                self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            else:
                self.tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = self.tempo_executado_homologado

            # total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            # ----------------------------------
            if metodo_calculo_rit == '1':
                self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao
            else:
                self.total_tempo_ajustado_pela_faixa_complexidade_entrega_avaliacao = self.tempo_executado_homologado

        return True


class RelatorioIndividualTrabalhoAtividadeEntregaServidorRegistrar(RelatorioIndividualTrabalhoAtividadeEntrega):
    class Meta:
        proxy = True
        verbose_name = 'Entrega'
        verbose_name_plural = 'Entregas'


class RelatorioIndividualTrabalhoAtividadeEntregaChefeRegistrar(RelatorioIndividualTrabalhoAtividadeEntrega):
    class Meta:
        proxy = True
        verbose_name = 'Entrega'
        verbose_name_plural = 'Entregas'


class RelatorioIndividualTrabalhoAtividadeEntregaAvaliar(RelatorioIndividualTrabalhoAtividadeEntrega):
    class Meta:
        proxy = True
        verbose_name = 'Entrega'
        verbose_name_plural = 'Entregas'


class RelatorioIndividualTrabalhoAtividadeEntregaTodasAvaliar(RelatorioIndividualTrabalhoAtividadeEntrega):
    class Meta:
        proxy = True
        verbose_name = 'Entrega'
        verbose_name_plural = 'Entregas'
