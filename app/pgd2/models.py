import datetime
import math
import operator
import os
from datetime import timedelta
from decimal import Decimal
from functools import reduce
from uuid import uuid4

import tqdm
from dateutil.relativedelta import relativedelta
from django.contrib import admin
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.db.models import DurationField, ExpressionWrapper, F, IntegerField, Prefetch, Q, QuerySet, Sum
from django.db.models.functions import Cast, Upper
from django.utils.safestring import mark_safe

from comum.models import Configuracao, UsuarioGrupo
from comum.utils import get_sigla_reitoria
from djtools.db import models
from djtools.templatetags.filters import format_datetime, format_time, status
from djtools.templatetags.filters.utils import format_money
from djtools.utils import formata_segundos, get_client_ip, ha_choque_de_periodo
from pgd2.pendencias_alertas import get_pendencia_geral_servidor_pgd
from pgd2.utils import (
    considerar_auditoria_centralizada,
    get_afastamentos_exterior,
    get_ch_prevista_servidor_periodo,
    get_datetime_now,
    get_lista_dias_para_cadastrar,
    get_msg_nenhum_setor_habilitado,
    get_servidores_auditoria,
    get_servidores_setores_sou_chefe_direto,
    get_setor_auditoria_centralizada,
    get_setor_servidor_no_periodo,
    get_setores_pgd,
    get_setores_servidor_no_periodo,
    get_sigla_setor_uo,
    gv,
    obter_compensacoes_especificas_compesaveis_rit,
    obter_dados_horas_ponto_servidor,
    permite_habilitacao_dos_setores,
    servidor_eh_auditor,
    servidores_que_sou_chefe_direto_hoje,
    setor_eh_auditoria_centralizada,
    setor_possui_relacao_siape_suap,
    setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo,
    setores_que_sou_chefe_direto_hoje,
    setores_que_sou_chefe_hoje,
    utilizar_integracao_com_ponto,
    validar_ponto_antes_primeiro_pit_adesao,
)
from plan_estrategico.models import PDI, AtividadeEtapa, UnidadeGestora
from ponto.models import SaldoExterno
from rh.models import AfastamentoSiape, Servidor, ServidorAfastamento, Setor, Situacao, UnidadeOrganizacional
from suap import nomenclatura

# ====================================================
# GERAL
# ====================================================


class RegistroAcaoPGD(models.ModelPlus):
    data = models.DateTimeFieldPlus('Data', auto_now_add=True, editable=False)
    ip = models.GenericIPAddressField(verbose_name='IP', editable=False)
    observacao = models.TextField(editable=False, null=True)
    diff = models.TextField(editable=False, null=True)
    de_para = models.JSONField(null=True)

    class Meta:
        ordering = ('-data',)
        abstract = True

    def __str__(self):
        return self.observacao

    @classmethod
    def registrar_acao(cls, pes, tipo_acao, user, ip, observacao=''):
        user = user if not user.is_anonymous else None
        cls.objects.create(tipo=tipo_acao, pes=pes, ip=ip, observacao=observacao, user=user)

    def get_de_para(self):
        if self.de_para:
            try:
                dados = []
                de = self.de_para['de']
                para = self.de_para['para']
                for key in de:
                    dados.append({'dado': key, 'de': de.get(key), 'para': para.get(key)})
                return dados
            except Exception:
                return None
        else:
            return None


class ControleRecorrenciaPGD(models.ModelPlus):
    @staticmethod
    def get_novo_controle_recorrencia():
        o = ControleRecorrenciaPGD()
        o.save()
        return o


# ====================================================
# CADASTROS BÁSICOS
# ====================================================


class ComissaoPGD(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    membros = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Membros', related_name='vinculo_membros_comissao_pgd2')
    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus(
        'rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True, related_name='uo_campus_abragencia_comissao_pgd2'
    )

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Comissão PGD'
        verbose_name_plural = 'Comissões PGD'
        permissions = (
            ('gestao_pgd2', 'Gestão PGD'),
            ('gestao_pgd2_comissao_sistemica', 'Comissão Sistêmica'),
            ('gestao_pgd2_comissao_local', 'Comissão Local'),
        )

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
    def get_lista_vigentes_por_user(user, sistemica=False):
        return ComissaoPGD.get_vigentes().filter(eh_sistemica=sistemica, membros__user=user)

    @staticmethod
    def get_lista_uos_vigentes_por_user(user):
        # Retorna todos os campus de abrangência das comissões vigentes de um usuário
        comissoes = ComissaoPGD.get_vigentes().filter(eh_sistemica=False, membros__user=user)
        campus_ids = set()
        for comissao in comissoes:
            campus_ids.update(comissao.campus_abragencia.values_list('id', flat=True))
        return UnidadeOrganizacional.objects.suap().filter(id__in=campus_ids)

    @staticmethod
    def user_estah_em_gestao_pgd(user):
        return user.has_group_cached('Gestor do PGD 2')

    @staticmethod
    def user_estah_em_comissao_sistemica_vigente(user):
        return user.has_group_cached('Comissão Sistêmica PGD 2') and ComissaoPGD.get_vigentes_por_user(user, sistemica=True)

    @staticmethod
    def user_estah_em_gestao_ou_comissao_sistemica_vigente(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user) or ComissaoPGD.user_estah_em_comissao_sistemica_vigente(user)

    @staticmethod
    def user_estah_em_comissao_local_vigente(user):
        return user.has_group_cached('Comissão Local PGD 2') and ComissaoPGD.get_vigentes_por_user(user, sistemica=False)

    @staticmethod
    def sincronizar_permissoes_comissao():
        # Remove todos os usuários dos grupos das comissões
        # ------------------
        for u in UsuarioGrupo.objects.filter(group__name='Comissão Sistêmica PGD 2'):
            u.delete()
        for u in UsuarioGrupo.objects.filter(group__name='Comissão Local PGD 2'):
            u.delete()

        # Adiciona apenas os que estão em comissões vigentes
        # ------------------
        comissoes_vigentes = ComissaoPGD.get_vigentes()
        grupo_sistemico = Group.objects.get(name='Comissão Sistêmica PGD 2')
        grupo_local = Group.objects.get(name='Comissão Local PGD 2')
        for comissao_vigente in comissoes_vigentes.filter(eh_sistemica=True):
            for membro in comissao_vigente.membros.all():
                membro.user.groups.add(grupo_sistemico)
        for comissao_vigente in comissoes_vigentes.filter(eh_sistemica=False):
            for membro in comissao_vigente.membros.all():
                membro.user.groups.add(grupo_local)

    @staticmethod
    def sincronizar_permissoes_comissao_membro(user):
        grupo_sistemico = Group.objects.get(name='Comissão Sistêmica PGD 2')
        grupo_local = Group.objects.get(name='Comissão Local PGD 2')

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

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)


class JustificativaDesligamentoPgd(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    ativo = models.BooleanField('Ativo?', default=True)
    servidor = models.BooleanField('Disponível para o Servidor?', default=False)
    chefe = models.BooleanField('Disponível para o Chefe?', default=False)
    gestao = models.BooleanField('Disponível para a Gestão?', default=False)
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
    def get_justificativas_ativas():
        return JustificativaDesligamentoPgd.objects.filter(ativo=True)

    @staticmethod
    def get_justificativas_servidor():
        return JustificativaDesligamentoPgd.get_justificativas_ativas().filter(servidor=True)

    @staticmethod
    def get_justificativas_chefe():
        return JustificativaDesligamentoPgd.get_justificativas_ativas().filter(chefe=True)

    @staticmethod
    def get_justificativas_gestao():
        return JustificativaDesligamentoPgd.get_justificativas_ativas().filter(gestao=True)

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)

    def clean(self):
        if self.gestao and (self.servidor or self.chefe):
            raise ValidationError('Uma justificativa de chefe ou servidor não pode ser ao mesmo tempo uma justificativa de gestão.')


class ConfiguracaoOrientacaoPlanoEntregasSetorial(models.ModelPlus):
    orientacao = models.TextField('Orientações')

    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus(
        'rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True, related_name='uo_campus_abragencia_orientacoes_pes_pgd2'
    )

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Observação/Regra sobre Plano de Entregas Setorial'
        verbose_name_plural = 'Observações/Regras sobre Plano de Entregas Setorial'

    def __str__(self):
        if self.data_fim:
            return f'Orientação sobre Plano de Trabalho Setorial vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Orientação sobre Plano de Entregas Setorial vigente a partir de {format_datetime(self.data_inicio)}'

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
        return ConfiguracaoOrientacaoPlanoEntregasSetorial.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | ConfiguracaoOrientacaoPlanoEntregasSetorial.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)

    @staticmethod
    def get_vigentes_sistemico():
        vigentes = ConfiguracaoOrientacaoPlanoEntregasSetorial.get_vigentes()
        return vigentes.filter(eh_sistemica=True)

    @staticmethod
    def get_vigentes_nao_sistemico(campus):
        vigentes = ConfiguracaoOrientacaoPlanoEntregasSetorial.get_vigentes()
        return vigentes.filter(eh_sistemica=False, campus_abragencia__in=[campus])

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)


class DocumentoAdesaoServidor(models.ModelPlus):
    descricao = models.TextField(verbose_name='Descrição')
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Observações/Regras relacionadas à Adesão do Servidor ao PGD'
        verbose_name_plural = 'Observações/Regras relacionadas à Adesão do Servidor ao PGD'

    def __str__(self):
        if self.data_fim:
            return f'Documento de Regras relacionadas à Adesão do Servidor - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Documento de Regras relacionadas à Adesão do Servidor - vigente a partir de {format_datetime(self.data_inicio)}'

    def get_verbose_simples(self):
        if self.data_fim:
            return f'Vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Vigente a partir de {format_datetime(self.data_inicio)}'

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
    def get_vigentes():
        hoje = datetime.date.today()
        ativas = DocumentoAdesaoServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | DocumentoAdesaoServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)
        return ativas

    @staticmethod
    def pode_cadastrar_alterar(user):
        return user.has_group_cached('Gestor do PGD 2')


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
    situacoes = models.ManyToManyFieldPlus('rh.Situacao', verbose_name='Situações', related_name='situacao_situacoes_perfilservidor_pgd2')
    deve_ter_funcao = models.BooleanField('Deve ter obrigatoriamente Função', default=False)
    funcoes = models.ManyToManyFieldPlus('rh.Funcao', verbose_name='Funções', blank=True, related_name='funcao_funcoes_perfilservidor_pgd2')

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Configuração de Perfil Geral de Servidor para Adesão ao PGD'
        verbose_name_plural = 'Configurações de Perfil Geral de Servidor para Adesão ao PGD'

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
        return ComissaoPGD.user_estah_em_gestao_pgd(user)

    @staticmethod
    def checa_perfil_servidor(servidor, retorna_motivo=False):
        vigentes = ConfiguracaoPerfilServidor.get_vigentes()
        vigentes_taes = vigentes.filter(
            Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE)
        )
        vigentes_docentes = vigentes.filter(
            Q(categoria=ConfiguracaoPerfilServidor.PERFIL_DOCENTE) | Q(categoria=ConfiguracaoPerfilServidor.PERFIL_TAE_OU_DOCENTE)
        )
        vigentes_estagiarios = vigentes_taes.filter(situacoes__codigo__in=Situacao.situacoes_siape_estagiarios())

        # Estagiario
        # -----------------------------------
        if servidor.eh_estagiario:
            return vigentes_estagiarios.exists() if not retorna_motivo else 'É estagiário'

        # Obtem perfil vigente para TAE ou DOCENTE
        # -----------------------------------
        perfil_servidor = None
        tae_docente = None
        if servidor.eh_tecnico_administrativo:
            tae_docente = 'TAE'
            if not vigentes_taes.exists():
                return False if not retorna_motivo else 'Não existe perfil geral cadastrado para TAE'
            perfil_servidor = vigentes_taes[0]
        elif servidor.eh_docente:
            tae_docente = 'DOCENTE'
            if not vigentes_docentes.exists():
                return False if not retorna_motivo else 'Não existe perfil geral cadastrado para DOCENTE'
            perfil_servidor = vigentes_docentes[0]
        else:
            return False if not retorna_motivo else 'Não é servidor TAE ou DOCENTE'

        # Verifica Situacao do servidor
        # -----------------------------------
        if perfil_servidor.situacoes:
            if servidor.situacao.codigo not in perfil_servidor.situacoes.values_list('codigo', flat=True):
                return (
                    False
                    if not retorna_motivo
                    else f'Não possui uma das situações cadastradas no Perfil Geral de {tae_docente}. Situação atual do servidor: {servidor.situacao}'
                )

        # Virifica funcoes do servidor
        # -----------------------------------
        servidor_tem_funcao_ativa = perfil_servidor.funcoes.exists() and servidor.historico_funcao_ativa.exists()
        # Se for obrigatorio ter funcao e o servidor nao tiver já diz que nao pode
        if perfil_servidor.deve_ter_funcao and not servidor_tem_funcao_ativa:
            return False if not retorna_motivo else f'Não possui função ativa conforme Perfil Geral de {tae_docente}'
        # Se o servidor tem a funcao do perfil
        if servidor_tem_funcao_ativa:
            funcoes_servidor = servidor.historico_funcao_ativa.values_list('funcao__codigo', flat=True)
            funcoes_perfil = perfil_servidor.funcoes.values_list('codigo', flat=True)
            tem_funcao_do_perfil = False
            for funcao_servidor in funcoes_servidor:
                if funcao_servidor in funcoes_perfil:
                    tem_funcao_do_perfil = True
            if not tem_funcao_do_perfil:
                return False if not retorna_motivo else f'É necessário ter ativa uma das funções cadastradas no Perfil Geral de {tae_docente}'

        return True


class DocumentoAdesaoPesServidor(models.ModelPlus):
    descricao = models.TextField(verbose_name='Descrição')
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)
    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = 'Observações/Regras relacionadas à Adesão do Servidor a um PES'
        verbose_name_plural = 'Observações/Regras relacionadas à Adesão do Servidor a um PES'

    def __str__(self):
        if self.data_fim:
            return f'Documento de Regras relacionadas à Adesão do Servidor a um PES - vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Documento de Regras relacionadas à Adesão do Servidor a um PES - vigente a partir de {format_datetime(self.data_inicio)}'

    def clean(self):
        is_insert = not self.id

        # A data data_inicio maior que data_fim
        if self.data_inicio and self.data_fim and not (self.data_inicio <= self.data_fim):
            raise ValidationError('A data inicial deve ser menor ou igual a data final.')

        # Não permite choque entre periodos no mesmo setor
        if not self.cancelado and self.data_inicio:
            lista_periodos = []
            ja_salvos = DocumentoAdesaoPesServidor.objects.exclude(cancelado=True)
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
        ativas = DocumentoAdesaoPesServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | DocumentoAdesaoPesServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)
        return ativas[0] if ativas else None

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        ativas = DocumentoAdesaoPesServidor.objects.filter(
            data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False
        ) | DocumentoAdesaoPesServidor.objects.filter(data_inicio__lte=hoje, data_fim__isnull=True, cancelado=False)
        return ativas

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)


class ConfiguracaoOrientacaoPit(models.ModelPlus):
    orientacao = models.TextField('Orientações')

    eh_sistemica = models.BooleanField('Abrangência (sistêmica)', default=False)
    campus_abragencia = models.ManyToManyFieldPlus(
        'rh.UnidadeOrganizacional', verbose_name='Abrangência (campus)', blank=True, related_name='uo_campus_abragencia_orientacoespit_pgd2'
    )

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência', null=True, blank=True)

    cancelado = models.BooleanField('Cancelado', default=False)

    class Meta:
        verbose_name = f'Observações/Regras sobre {nomenclatura.plano_individual_de_trabalho_pgd2}'
        verbose_name_plural = f'Observações/Regras sobre {nomenclatura.plano_individual_de_trabalho_pgd2}'

    def __str__(self):
        if self.data_fim:
            return f'Orientação sobre {nomenclatura.plano_individual_de_trabalho_pgd2} vigente de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'
        return f'Orientação sobre {nomenclatura.plano_individual_de_trabalho_pgd2} vigente a partir de {format_datetime(self.data_inicio)}'

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
        return ComissaoPGD.user_estah_em_gestao_pgd(user)


class PeriodoPes(models.ModelPlus):
    titulo = models.CharFieldPlus(verbose_name='Título')
    cancelado = models.BooleanField('Cancelado', default=False)

    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial da Vigência do PES')
    data_fim = models.DateFieldPlus(verbose_name='Data Final da Vigência do PES')

    data_prazo_solicitar_avaliacao_execucao = models.DateFieldPlus(
        verbose_name='Data de libração do PES para análise da execução do PES', null=True, blank=True
    )

    class Meta:
        verbose_name = 'Calendário de PES'
        verbose_name_plural = 'Calendários de PES'

    def __str__(self):
        return f'{format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'

    def get_verbose_periodo(self):
        return f'{format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'

    def clean(self):
        if self.pk:
            ppes = PeriodoPes.objects.get(id=self.id)
            alterou = self.cancelado != ppes.cancelado or self.data_inicio != ppes.data_inicio or self.data_fim != ppes.data_fim
            if alterou and PeriodoPitRit.objects.filter(periodo_pes=self, cancelado=False).exists():
                raise ValidationError(
                    f'Este calendário possui calendário de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado a ele. Assim, só é possível alterar a "Data de liberação da solicitação de avaliação da execução"'
                )

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)

    def get_data_liberacao_para_solicitar_avaliacao_execucao(self):
        return self.data_prazo_solicitar_avaliacao_execucao


class PeriodoPitRit(models.ModelPlus):
    periodo_pes = models.ForeignKeyPlus('pgd2.PeriodoPes', verbose_name='PES', related_name='periodopes_periodotpitrit_pgd2')

    titulo = models.CharFieldPlus(verbose_name='Título')
    cancelado = models.BooleanField('Cancelado', default=False)

    preencher_questionario_pesquisa = models.BooleanField('Solicitar preenchimento do questionário de pesquisa', default=False)

    data_inicio = models.DateFieldPlus(verbose_name=f'Data Inicial da Vigência do {nomenclatura.pit_rit_pgd2}')
    data_fim = models.DateFieldPlus(verbose_name=f'Data Final da Vigência do {nomenclatura.pit_rit_pgd2}')

    # ----------------------------
    # SERVIDOR
    # ----------------------------
    data_prazo_entrega_pit = models.DateFieldPlus(
        verbose_name=f'Prazo da Entrega do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} deste período', null=True, blank=True
    )
    data_prazo_entrega_rit = models.DateFieldPlus(
        verbose_name=f'Prazo da Entrega do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} deste período', null=True, blank=True
    )

    # ----------------------------
    # CHEFE
    # ----------------------------
    data_prazo_homologacao_pit = models.DateFieldPlus(
        verbose_name=f'Prazo da Homologação do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} deste período', null=True, blank=True
    )
    data_prazo_homologacao_rit = models.DateFieldPlus(
        verbose_name=f'Prazo da Homologação do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} deste período', null=True, blank=True
    )

    class Meta:
        verbose_name = f'Calendário de {nomenclatura.pit_rit_pgd2}'
        verbose_name_plural = f'Calendários de {nomenclatura.pit_rit_pgd2}'

    def __str__(self):
        return f'Calendário de {nomenclatura.pit_rit_pgd2} de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'

    def get_verbose_simples(self):
        return f'{format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'

    def clean(self):
        # Só altera algo se não existe nada vinculado a ele
        if self.pk:
            ppes = PeriodoPitRit.objects.get(id=self.id)
            alterou = self.cancelado != ppes.cancelado or self.data_inicio != ppes.data_inicio or self.data_fim != ppes.data_fim
            if alterou and PlanoIndividualTrabalho.objects.filter(periodo_pit_rit=self).exists():
                raise ValidationError(
                    f'Impossível alterar o calendário se tiver algum {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} relacionado a ele.'
                )

        if self.data_inicio < self.periodo_pes.data_inicio or self.data_fim > self.periodo_pes.data_fim:
            raise ValidationError(f'O período de vigência do {nomenclatura.pit_rit_pgd2} deve considerar o período de vigência do PES relacionado .')

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)

    @staticmethod
    def get_periodo_pit_atual():
        # Periodo atual (hoje ou ultimo cadastrado)
        periodo_pit_atual = PeriodoPitRit.objects.filter(
            cancelado=False, data_inicio__lte=get_datetime_now().date(), data_fim__gte=get_datetime_now().date()
        )
        if periodo_pit_atual:
            periodo_pit_atual = periodo_pit_atual.first()
        else:
            periodo_pit_atual = PeriodoPitRit.objects.filter(cancelado=False).order_by('-data_inicio').first()

        return periodo_pit_atual

    @staticmethod
    def get_periodo_pit_atual_e_periodos_anteriores(qtd_periodos_anteriores=2):
        periodo_atual = PeriodoPitRit.get_periodo_pit_atual()
        if periodo_atual:
            periodos_anteriores = (
                PeriodoPitRit.objects.filter(cancelado=False, data_fim__lt=periodo_atual.data_fim)
                .exclude(id=periodo_atual.id)
                .order_by('-data_fim')[0:qtd_periodos_anteriores]
            )
            if periodos_anteriores:
                return [periodo_atual, *list(periodos_anteriores)]
            return [periodo_atual]
        return []


# ====================================================
# PES - Plano de Entregas Setorial
# ====================================================
class PlanoEntregasSetorial(models.ModelPlus):
    # -----------------------------
    # Cadastro / Cálculo
    # -----------------------------

    periodo_pes = models.ForeignKeyPlus('pgd2.PeriodoPes', verbose_name='Período PES', related_name='periodopes_pes_pgd2')
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', related_name='setor_pes_pgd2')
    setor_para_aprovacao = models.ForeignKeyPlus(
        'rh.Setor', verbose_name='Setor para aprovação', related_name='setorsuperior_pes_pgd2', null=True, blank=True
    )

    auxiliares = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Auxiliares do Chefe no Preenchimento do Plano', blank=True, related_name='auxiliares_pes_pgd2'
    )

    # Documentação do PES
    doc_percentual_maximo_teletrabalho = models.DecimalFieldPlus(verbose_name='% máximo de Teletrabalho', null=True, blank=True)
    doc_insfraestrutura = models.TextField(
        'Infraestrutura física, material e tecnológica mínima necessária para a realização das atividades em teletrabalho, incluindo equipamentos e mobiliários adequados e ergonômicos',
        null=True,
        blank=True,
    )
    doc_tecnica = models.TextField(
        'A técnica necessária para a realização das atividades em teletrabalho, contemplando, além de outros específicos do serviço que independem do regime de execução',
        null=True,
        blank=True,
    )

    em_execucao = models.BooleanField('Em execução', default=False)

    # -----------------------------
    # Aprovação antes da execução
    # -----------------------------
    EM_CADASTRO = 1
    SOLICITADO_APROVACAO = 2
    APROVADO = 3
    SITUACAO_PES_CHOICES = [[EM_CADASTRO, 'Em fase de cadastro'], [SOLICITADO_APROVACAO, 'Solicitado aprovação'], [APROVADO, 'Aprovado']]
    SITUACOES_PODE_EDITAR = [EM_CADASTRO, APROVADO]
    situacao = models.PositiveIntegerField('Situação', choices=SITUACAO_PES_CHOICES, editable=False, default=EM_CADASTRO)

    # -----------------------------
    # Avaliação da execução - Solicitação
    # -----------------------------
    SOLICITADO_AVALIACAO = 1
    AVALIADO = 2
    SITUACAO_AVALIACAO_PES_CHOICES = [[SOLICITADO_AVALIACAO, 'Solicitado avaliação da execução'], [AVALIADO, 'Avaliado ']]
    situacao_avaliacao = models.PositiveIntegerField(
        'Situação da avaliação da execução', choices=SITUACAO_AVALIACAO_PES_CHOICES, editable=False, null=True
    )
    avaliacao_solicitacao_observacao_pes = models.TextField(editable=False, null=True)

    AVALIACAO_EXCEPCIONAL_PES = 1
    AVALIACAO_ALTO_DESEMPENHO_PES = 2
    AVALIACAO_ADEQUADO_PES = 3
    AVALIACAO_INADEQUADO_PES = 4
    AVALIACAO_NAO_EXECUTADO_PES = 5
    AVALIACAO_PES_CHOICES = [
        [AVALIACAO_EXCEPCIONAL_PES, 'Excepcional: plano de entregas executado com desempenho muito acima do esperado'],
        [AVALIACAO_ALTO_DESEMPENHO_PES, 'Alto desempenho: plano de entregas executado com desempenho acima do esperado'],
        [AVALIACAO_ADEQUADO_PES, 'Adequado: plano de entregas executado dentro do esperado'],
        [AVALIACAO_INADEQUADO_PES, 'Inadequado: plano de entregas executado abaixo do esperado'],
        [AVALIACAO_NAO_EXECUTADO_PES, 'Pplano de entregas não executado.'],
    ]
    avaliacao_pes = models.PositiveIntegerField('Avaliação PES', null=True, editable=False, choices=AVALIACAO_PES_CHOICES)
    avaliacao_observacao_pes = models.TextField(editable=False, null=True)

    # -----------------------------
    # Para API
    # -----------------------------
    cod_siape_grupo = models.CharFieldPlus(editable=False, null=True, blank=True)
    principal_siape_grupo = models.BooleanField(editable=False, default=False)
    identificador_externo = models.CharFieldPlus(editable=False, null=True, blank=True)
    data_hora_ultimo_envio_api = models.DateTimeFieldPlus(verbose_name='Data/hora do último envio pela API', null=True, blank=True)
    data_hora_ultima_alteracao_apos_aprovacao = models.DateTimeFieldPlus(verbose_name='Data/hora da última alteração de dados', null=True, blank=True)

    class Meta:
        verbose_name = 'Plano de Entregas Setorial'
        verbose_name_plural = 'Planos de Entregas Setorial'
        ordering = ('setor',)

    def __str__(self):
        return f'Plano de Entregas Setorial {self.setor} de {format_datetime(self.periodo_pes.data_inicio)} a {format_datetime(self.periodo_pes.data_fim)}'

    def get_verbose_periodo(self):
        return f'{format_datetime(self.periodo_pes.data_inicio)} a {format_datetime(self.periodo_pes.data_fim)}'

    def get_verbose_simples(self):
        return mark_safe(
            f'{self.setor.get_caminho_as_html()} de {format_datetime(self.periodo_pes.data_inicio)} a {format_datetime(self.periodo_pes.data_fim)}'
        )

    @staticmethod
    def get_pes_na_data(setor, data):
        # Pega do PIT da data ou do imadiatamente anterior a ele
        pit_na_data = PlanoEntregasSetorial.objects.filter(
            setor=setor, periodo_pes__data_inicio__lte=data, periodo_pes__data_fim__gte=data, situacao=PlanoEntregasSetorial.APROVADO
        ).first()
        if not pit_na_data:
            # pit anterior
            pit_na_data = (
                PlanoEntregasSetorial.objects.filter(setor=setor, periodo_pes__data_inicio__lt=data, situacao=PlanoEntregasSetorial.APROVADO)
                .order_by('-periodo_pes__data_inicio')
                .first()
            )
        if pit_na_data:
            return pit_na_data
        return None

    # --------------------------------
    # Pode visualizar
    # --------------------------------
    def pode_visualizar(self, user):
        return bool(user.has_perm('rh.eh_servidor'))

    @staticmethod
    def pode_visualizar_lista(user):
        return bool(user.has_perm('rh.chefe'))

    # --------------------------------
    # Pode cadastrar um novo PES
    # --------------------------------
    @staticmethod
    def pode_iniciar_cadastrar(user, retornar_lista_erros=False, lista_setores_que_sou_chefe_hoje=None):
        # Se pode cadasttar um novo PES
        erros = []

        if not PeriodoPes.objects.filter(cancelado=False).exists():
            if retornar_lista_erros:
                erros.append('Para cadastrar um PES é necessário que se tenha, no mínimo, um Calendário de PES cadastrado.')
            else:
                return False, None

        if not ConfiguracaoOrientacaoPlanoEntregasSetorial.get_vigentes_sistemico():
            if retornar_lista_erros:
                erros.append(
                    'Para cadastrar um PES é necessário que se tenha, no mínimo, uma Orientação sobre Plano de Entregas Setorial sistêmica .'
                )
            else:
                return False, None

        setores_sou_chefe_hoje = lista_setores_que_sou_chefe_hoje or setores_que_sou_chefe_hoje(user.get_relacionamento())
        if not setores_sou_chefe_hoje:
            if retornar_lista_erros:
                erros.append('Para cadastrar um PES é necessário ser chefe de setor.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_cadastrar(setor, periodo_pes, user, retornar_lista_erros=False):
        # Se pode cadastar um determinado novo PES
        erros = []

        pode, lista_erros = PlanoEntregasSetorial.pode_iniciar_cadastrar(user, retornar_lista_erros=True)
        if not pode:
            if retornar_lista_erros:
                erros.extend(lista_erros)
            else:
                return False, None

        if not SetorHabilitacao.setor_estah_habilitado(setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=setor.sigla))
            else:
                return False, None

        if setor not in setores_que_sou_chefe_hoje(user.get_relacionamento()):
            if retornar_lista_erros:
                erros.append('Para cadastrar um PES é necessário ser chefe do setor.')
            else:
                return False, None

        # Não permite mais de um PES para o mesmo calendario (PeriodoPes)
        if PlanoEntregasSetorial.objects.filter(setor=setor, periodo_pes=periodo_pes).exists():
            if retornar_lista_erros:
                erros.append('Impossível cadastrar um PES para o mesmo calendário e setor de outro PES já cadastrado.')
            else:
                return False, None

        from pgd2.api_pgd2 import get_codigo_siape_setor

        if not get_codigo_siape_setor(setor):
            if retornar_lista_erros:
                erros.append('Impossível cadastrar um PES para o setor que não foi possível obter o seu código SIAPE.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    # ----------------------------
    # Edição/Ajuste do PES e outras operações
    # - O que pode ser editado
    #   - Cancelar/Descancelar
    #   - Documentação do PES
    #     - doc_percentual_maximo_teletrabalho
    #     - doc_insfraestrutura
    #     - doc_tecnica
    #     - O horário de funcionamento semanal do setor
    #     - A periodicidade e os horários de planejamento do setor e a forma de realização de reuniões (online, presencial ou híbrida);
    #   - Configurações
    #     - exige_justificativa_pos_edicao_pit
    #   - As entregas da unidade de execução com suas respectivas metas, prazos, demandantes e destinatários.
    # ----------------------------
    def pode_editar(self, user=None):
        if self.situacao not in self.SITUACOES_PODE_EDITAR:
            return False

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            return False

        if user:
            eh_auxiliar = self.auxiliares.filter(id=user.get_vinculo().id).exists()
            if eh_auxiliar:
                return True

            eh_chefe = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
            return eh_chefe

        return True

    def pode_excluir(self, user=None):
        nao_existem_dados_dependentes = (
            not PlanoIndividualTrabalhoEntregas.objects.filter(entrega_pes__pes=self).exists() and not PitSetores.objects.filter(pes=self).exists()
        )
        return self.pode_editar(user) and nao_existem_dados_dependentes

    def pode_editar_dados_basicos(self, user):
        return self.pode_editar(user)

    def pode_cadastrar_horario_funcionamento_setor(self, user):
        return self.pode_editar(user)

    def pode_editar_horario_funcionamento_setor(self, user):
        return self.pode_editar(user)

    def pode_remover_horario_funcionamento_setor(self, user):
        return self.pode_editar(user)

    def pode_cadastrar_horario_planejamento_setor(self, user):
        return self.pode_editar(user)

    def pode_editar_horario_planejamento_setor(self, user):
        return self.pode_editar(user)

    def pode_remover_horario_planejamento_setor(self, user):
        return self.pode_editar(user)

    def pode_cadastrar_entrega(self, user):
        return self.pode_editar(user)

    def pode_editar_auxiliares(self, user):
        return self.pode_editar(user)

    def existe_entrega_que_pode_ser_removida_no_pes(self, user):
        entregas_pes = PlanoEntregasSetorialEntregas.objects.filter(pes=self)
        return any(epes.pode_remover_entrega(user) for epes in entregas_pes)

    # ----------------------------
    # Aprovacao PES
    # ----------------------------
    def usuario_pode_solicitar_aprovacao(self, user):
        return self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())

    def pode_solicitar_aprovacao(self, user, retornar_lista_erros=False):
        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=self.setor.sigla))
            else:
                return False, None

        if self.situacao == self.APROVADO:
            if retornar_lista_erros:
                erros.append('Este PES já foi aprovado.')
            else:
                return False, None

        if not (self.usuario_pode_solicitar_aprovacao(user) or self.auxiliares.filter(id=user.get_vinculo().id).exists()):
            if retornar_lista_erros:
                erros.append('Você precisa ser o chefe do setor relacionado ao PES ou precisa ser auxiliar no preenchimento do PES.')
            else:
                return False, None

        if self.situacao != self.EM_CADASTRO:
            if retornar_lista_erros:
                erros.append('O PES precisa estar Em Fase de Cadastro.')
            else:
                return False, None

        # Dados mínimos no PES
        # ------------------------------------
        # - Dados básicos
        if not self.doc_insfraestrutura or not self.doc_tecnica:
            if retornar_lista_erros:
                erros.append('É preciso informar todos os dados básicos.')
            else:
                return False, None

        # - Horário de funcionamento do setor
        if not PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=self).exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, um horário de funcionamento.')
            else:
                return False, None

        # - Horário de planejamento do setor
        if not PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=self).exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, um horário de planejamento.')
            else:
                return False, None

        # - Entregas
        if not PlanoEntregasSetorialEntregas.objects.filter(pes=self).exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, uma entrega.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def pode_aprovar(self, user, retornar_lista_erros=False):
        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=self.setor.sigla))
            else:
                return False, None

        if self.situacao != PlanoEntregasSetorial.SOLICITADO_APROVACAO:
            if retornar_lista_erros:
                erros.append('Este PES precisa estar em "Solicitado aprovação".')
            else:
                return False, None

        # Se for chefe do setoe de aprovacao
        if self.setor_para_aprovacao not in setores_que_sou_chefe_hoje(user.get_relacionamento()):
            if retornar_lista_erros:
                erros.append('Você precisa ser o chefe do setor de aprovação/homologação ao PES (ou se de algum setr superior).')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def get_pess_pendendentes_aprovacao(user):
        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        return PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.SOLICITADO_APROVACAO, setor_para_aprovacao__in=setores)

    # ----------------------------
    # Avaliacao PES
    # ----------------------------
    def usuario_pode_solicitar_avaliacao(self, user):
        return self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())

    def get_servidores_relacionados_com_pendencia(self):
        lista_servidores_adesao_por_periodo = self.get_servidores_relacionados_periodo(apenas_com_pendencia_execucacao=True)
        lista = []
        for d in lista_servidores_adesao_por_periodo:
            for s in d.get('servidores'):
                # if s.get('possui_ch_prevista_no_periodo') and not s.get('possui_contribuicao_executada_no_periodo'):
                lista.append(f'{d.get("periodo").get_verbose_simples()} - {s.get("servidor")}')
        return lista

    def pode_solicitar_avaliacao(self, user, retornar_lista_erros=False, validar_analise_entregas_pes=False):
        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=self.setor.sigla))
            else:
                return False, None

        if self.situacao_avaliacao:
            if retornar_lista_erros:
                erros.append('Este PES já foi avaliado ou já teve solicitação de avaliação.')
            else:
                return False, None

        data_liberacao_para_solicitar_avaliacao_execucao = self.periodo_pes.get_data_liberacao_para_solicitar_avaliacao_execucao()
        if not data_liberacao_para_solicitar_avaliacao_execucao:
            if retornar_lista_erros:
                erros.append(
                    'Só pode enviar para avaliação se no Calendário de PES tiver cadastrada a "Data de liberação da solicitação de avaliação da execução".'
                )
            else:
                return False, None
        if data_liberacao_para_solicitar_avaliacao_execucao and not (get_datetime_now().date() >= data_liberacao_para_solicitar_avaliacao_execucao):
            if retornar_lista_erros:
                erros.append('Só pode enviar para avaliação a partir "Data de liberação da solicitação de avaliação da execução".')
            else:
                return False, None

        if not self.usuario_pode_solicitar_aprovacao(user):
            if retornar_lista_erros:
                erros.append('Você precisa ser o chefe do setor relacionado ao PES.')
            else:
                return False, None

        if self.situacao != self.APROVADO:
            if retornar_lista_erros:
                erros.append('O PES precisa estar Em Fase de Cadastro.')
            else:
                return False, None

        # Dados mínimos no PES
        # ------------------------------------
        # - Dados básicos
        if not self.doc_insfraestrutura or not self.doc_tecnica:
            if retornar_lista_erros:
                erros.append('É preciso informar todos os dados básicos.')
            else:
                return False, None

        # - Horário de funcionamento do setor
        if not PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=self).exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, um horário de funcionamento.')
            else:
                return False, None

        # - Horário de planejamento do setor
        if not PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=self).exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, um horário de planejamento.')
            else:
                return False, None

        if not self.get_entregas_aptas().exists():
            if retornar_lista_erros:
                erros.append('É preciso informar, no mínimo, uma entrega no PES.')
            else:
                return False, None

        if validar_analise_entregas_pes:
            if not self.analise_foi_finalizada():
                if retornar_lista_erros:
                    erros.append('Análise das entregas do PES não foi finalizada.')
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    def pode_avaliar(self, user, retornar_lista_erros=False):
        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=self.setor.sigla))
            else:
                return False, None

        if self.situacao_avaliacao != PlanoEntregasSetorial.SOLICITADO_AVALIACAO:
            if retornar_lista_erros:
                erros.append('Este PES precisa estar em "Solicitado avaliação da execução".')
            else:
                return False, None

        # Se for chefe do setor de aprovacao
        if self.setor_para_aprovacao not in setores_que_sou_chefe_hoje(user.get_relacionamento()):
            if retornar_lista_erros:
                erros.append('Você precisa ser o chefe do setor de aprovação/homologação ao PES (ou se de algum setr superior).')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def pode_reabrir(self, user, retornar_lista_erros=False):
        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=self.setor.sigla))
            else:
                return False, None

        if self.situacao_avaliacao != PlanoEntregasSetorial.SOLICITADO_AVALIACAO:
            if retornar_lista_erros:
                erros.append('Este PES precisa estar em "Solicitado avaliação da execução" ou "Avaliado".')
            else:
                return False, None

        # Se for chefe do setor de aprovacao
        if self.setor_para_aprovacao not in setores_que_sou_chefe_hoje(user.get_relacionamento()):
            if retornar_lista_erros:
                erros.append('Você precisa ser o chefe do setor de aprovação/homologação ao PES (ou se de algum setr superior).')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def get_pess_pendendentes_analise_execucao(user=None, apenas_chefe_direto=True):
        def get_pess():
            pess = PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.APROVADO)
            pess = pess.filter(situacao_avaliacao__isnull=True)
            pess = pess.filter(periodo_pes__data_prazo_solicitar_avaliacao_execucao__lte=get_datetime_now().date())
            return pess

        pess = PlanoEntregasSetorial.objects.none()
        if user:
            setores = None
            if apenas_chefe_direto:
                setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            else:
                setoresd = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
                setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
                setores = setores.exclude(id__in=setoresd.values('id'))
            pess = get_pess().filter(setor__in=setores)
        else:
            pess = get_pess()

        return pess

    @staticmethod
    def get_pess_pendendentes_avaliacao(user=None):
        def get_pess():
            pess = PlanoEntregasSetorial.objects.filter(situacao_avaliacao=PlanoEntregasSetorial.SOLICITADO_AVALIACAO)
            pess = pess.filter(periodo_pes__data_prazo_solicitar_avaliacao_execucao__lte=get_datetime_now().date())
            return pess

        if user:
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            pess = get_pess().filter(setor_para_aprovacao__in=setores)
        else:
            pess = get_pess()

        return pess

    # ----------------------------
    # Outros
    # ----------------------------

    def pode_visualizar_execucao(self, user):
        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            return False

        pode_pela_situacao = self.estah_aprovado()

        eh_chefe = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        eh_auxiliar = self.auxiliares.filter(id=user.get_vinculo().id).exists()

        user_pode = eh_chefe or eh_auxiliar

        return bool(pode_pela_situacao and user_pode)

    def estah_aprovado(self):
        return self.situacao == self.APROVADO

    def estah_avaliado(self):
        return self.situacao_avaliacao == self.AVALIADO

    def estah_apto(self):
        return self.estah_aprovado() and (self.periodo_pes.data_inicio <= get_datetime_now().date() <= self.periodo_pes.data_fim)

    @staticmethod
    def get_pess_aprovados(setor=None):
        if setor:
            return PlanoEntregasSetorial.objects.filter(setor=setor, situacao=PlanoEntregasSetorial.APROVADO)
        return PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.APROVADO)

    @staticmethod
    def get_pes_apto(setor):
        pess = PlanoEntregasSetorial.objects.filter(setor=setor, situacao=PlanoEntregasSetorial.APROVADO)
        hoje = get_datetime_now().date()
        return pess.filter(periodo_pes__data_inicio__lte=hoje, periodo_pes__data_fim__gte=hoje)

    @staticmethod
    def get_pess_aptos():
        pess = PlanoEntregasSetorial.objects.filter(situacao=PlanoEntregasSetorial.APROVADO)
        hoje = get_datetime_now().date()
        return pess.filter(periodo_pes__data_inicio__lte=hoje, periodo_pes__data_fim__gte=hoje)

    @staticmethod
    def existe_algum_pes_apto(setor):
        return PlanoEntregasSetorial.get_pes_apto(setor).exists()

    @staticmethod
    def get_pes_apto_a_partir_de(setor, data_inicio):
        pess = PlanoEntregasSetorial.objects.filter(setor=setor, situacao=PlanoEntregasSetorial.APROVADO)
        return pess.filter(periodo_pes__data_inicio__gte=data_inicio)

    @admin.display(
        description='Data início',
    )
    def get_data_inicio(self):
        return self.periodo_pes.data_inicio

    @admin.display(
        description='Data fim',
    )
    def get_data_fim(self):
        return self.periodo_pes.data_fim

    def get_horarios_funcionamento_setor_agrupado_por_semana(self):
        return PlanoEntregasSetorialHorarioFuncionamentoSetor.get_horarios_funcionamento_setor_agrupado_por_semana(self)

    def get_entregas(self):
        return PlanoEntregasSetorialEntregas.objects.filter(pes_id=self.id).order_by('titulo')

    def get_entregas_aptas(self):
        return self.get_entregas().filter(pes_id=self.id, cancelado=False).order_by('titulo')

    @staticmethod
    def get_pes_dos_setores(setores):
        return PlanoEntregasSetorial.objects.filter(setor__in=setores)

    @staticmethod
    def get_pes_sou_auxiliar_setores(user):
        return PlanoEntregasSetorial.objects.filter(auxiliares__in=user.get_vinculo())

    def get_orientacoes_relacionadas_ao_periodo(self):
        periodo_query_1 = Q(data_fim__isnull=True) & Q(data_inicio__lte=self.get_data_fim())
        periodo_query_2 = Q(data_fim__isnull=False) & (Q(data_inicio__gte=self.get_data_inicio()) | Q(data_fim__lte=self.get_data_fim()))
        return ConfiguracaoOrientacaoPlanoEntregasSetorial.objects.filter(cancelado=False).filter(periodo_query_1 | periodo_query_2)

    def get_setor_superior_aprovar_pes(self):
        try:
            if self.setor == Setor.raiz_suap():
                return self.setor
            return self.setor.superior
        except Exception:
            pass
        return self.setor

    @staticmethod
    def get_pes_apto_relacionado_periodo_pit_rit_setor(periodo_pit_rit, setor):
        # se ESTE PES está relacionado ao PERÍODO PIT RIT e ao setor passados como parâmetro
        # - se o Período PIT/RIT inicia e termina dentro do período deste PES
        # - se o o PES é do etor
        pess = PlanoEntregasSetorial.objects.filter(setor=setor, situacao=PlanoEntregasSetorial.APROVADO)
        return pess.filter(periodo_pes__data_inicio__lte=periodo_pit_rit.data_inicio, periodo_pes__data_fim__gte=periodo_pit_rit.data_fim).order_by(
            'periodo_pes__data_inicio'
        )

    @staticmethod
    def get_pes_apto_relacionado_periodo_pit_rit_setores(periodo_pit_rit, ids_setores_pess_aderidos_servidor):
        # - Considerando os setores
        # - Obtem os PES relacionados ao Calendário PES do Calendário PIT do PIT que se deseja adicionar entregas de PES
        pess = PlanoEntregasSetorial.objects.filter(setor_id__in=ids_setores_pess_aderidos_servidor, situacao=PlanoEntregasSetorial.APROVADO)
        return pess.filter(periodo_pes=periodo_pit_rit.periodo_pes)

    def get_atividades_plan_estrategico_relacionadas_ao_pes(self):
        # Para obter o setor
        # - Se o setor do PES for UnidadeGestora então setor_unidade_gestora será o setor do PES
        # - Se o setor do PES não for UnidadeGestora então setor_unidade_gestora será
        #   o setor da unidade gestora superior mais próximo ao setor do PES
        ano_pes = self.get_data_inicio().year
        pdi_atual = PDI.objects.filter(ano_inicial_pdi__ano__lte=ano_pes, ano_final_pdi__ano__gte=ano_pes).first()
        unidade_gestora = None
        setores_caminho = self.setor.get_caminho(ordem_descendente=False)
        for s in setores_caminho:
            ug = UnidadeGestora.objects.filter(pdi=pdi_atual, setor_equivalente=s).first()
            if ug:
                unidade_gestora = ug
                break
        #
        if unidade_gestora:
            atividades = AtividadeEtapa.objects.filter(etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade__ano_base__ano=ano_pes)
            atividades = atividades.filter(unidade_gestora=unidade_gestora)
            atividades = atividades.filter(
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade__data_geral_inicial__lte=self.get_data_inicio(),
                etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade__data_geral_final__gte=self.get_data_fim(),
            )
            atividades = atividades.select_related('etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade__pdi')
            atividades = atividades.select_related('etapa_projeto_plano_atividade__etapa')
            atividades = atividades.select_related('unidade_gestora__setor_equivalente')
            atividades = atividades.order_by('etapa_projeto_plano_atividade__etapa__descricao', 'nome', 'descricao')
            return atividades

        return AtividadeEtapa.objects.none()

    def calcular_pes(self):
        # Está em execução quando
        if self.estah_apto() and not self.situacao_avaliacao:
            self.em_execucao = True
        else:
            self.em_execucao = False
        self.save()

    """
    # Retirado temporariamente
    # Rever em outro momento
    def get_adesoes_pes_vigentes_neste_pes(self):
        # Retorna as adesões Vigentes
        # - Considerando as adesões pes relacionadas a adesões ao pgd que estejam vigentes
        # - Busca as adesoes pes
        #   - Deferidas
        #   - Que que ainda nao esta desligado
        #   - Do setor do pes

        # Adesões PGD vigentes
        # --------------------------
        # Deferidas
        adesoes_pgd = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        # Sem desligamento
        adesoes_pgd_com_desligamento = adesoes_pgd.filter(data_desligamento_efeitos_a_partir_de__lte=get_datetime_now().date())
        adesoes_pgd = adesoes_pgd.exclude(id__in=adesoes_pgd_com_desligamento.values('id'))

        # Adesões PGD PES relacionadas ao setor e as adesões vigentes
        # --------------------------
        adesoes_pes = SolicitacaoAdesaoPesServidor.objects.filter(
            adesao__in=adesoes_pgd, setor=self.setor, situacao=SolicitacaoAdesaoPesServidor.DEFERIDO
        ).order_by('adesao__servidor')

        # Montando lista de adesoes com o setor do servidor na época do PES
        # --------------------------
        lista_adesoes_pes = list()
        for adesao_pes in adesoes_pes:
            dados_adesao_pes = dict()
            dados_adesao_pes['servidor'] = adesao_pes.adesao.servidor
            setor_epoca_pes = (
                adesao_pes.adesao.servidor.historico_setor_suap(data_inicio=self.periodo_pes.data_inicio, data_fim=self.periodo_pes.data_fim)
                .order_by('data_inicio_no_setor')
                .last()
            )
            if setor_epoca_pes:
                dados_adesao_pes['setor_epoca_pes'] = setor_epoca_pes.setor
            lista_adesoes_pes.append(dados_adesao_pes)

        return lista_adesoes_pes
    """

    def get_servidores_relacionados_periodo(self, apenas_com_pendencia_execucacao=False):
        """
        Verifica quais servidores deveriam ter alguma contribuição em cada periodo do PES
        - Servidores relacionados ao PES por cada periodo de PIT relacionado
        - Servidores do setor no periodo e de outros setores
            - Tem adesão pgd no período
            - Tem adesão pes no período
            - Estava no setor nesse periodo
        - Para cada uma dos servidores
        - Se possui contribuição planejada
        - Se possui contribuição executada
            - Executada
            - Homologada
        """
        setor_pes = self.setor
        periodos_pit_pes = PeriodoPitRit.objects.filter(periodo_pes=self.periodo_pes, cancelado=False).order_by('data_inicio')

        def possui_contribuicao_planejada_apenas_cadastrada_no_periodo(servidor, periodo, setor):
            return PitSetores.objects.filter(
                pit__adesao__servidor=servidor,
                pit__periodo_pit_rit=periodo,
                setor=setor,
                pit__situacao__in=PlanoIndividualTrabalho.SITUACOES_PLANEJAMENTO_CADASTRADO_PIT,
            ).exists()

        def possui_contribuicao_planejada_no_periodo(servidor, periodo, setor):
            return PitSetores.objects.filter(
                pit__adesao__servidor=servidor, pit__periodo_pit_rit=periodo, setor=setor, pit__situacao=PlanoIndividualTrabalho.HOMOLOGADO
            ).exists()

        def possui_contribuicao_executada_apenas_cadastrada_no_periodo(servidor, periodo, setor):
            # Deve veriricar a situação do PIT e RIT mas tb deve verificar se existem entregras cadastradas no RIT
            pit_setores = PitSetores.objects.filter(
                pit__adesao__servidor=servidor,
                pit__periodo_pit_rit=periodo,
                setor=setor,
                pit__situacao=PlanoIndividualTrabalho.HOMOLOGADO,
                pit__situacao_rit__in=PlanoIndividualTrabalho.SITUACOES_EXECUCAO_CADASTRADO_RIT,
            )
            ids_pits_relacionados = pit_setores.values_list('pit_id', flat=True)
            rits_cadastrados = RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit_id__in=ids_pits_relacionados)
            return rits_cadastrados.exists() and pit_setores.exists()

        def possui_contribuicao_executada_no_periodo(servidor, periodo, setor):
            return PitSetores.objects.filter(
                pit__adesao__servidor=servidor,
                pit__periodo_pit_rit=periodo,
                setor=setor,
                pit__situacao=PlanoIndividualTrabalho.HOMOLOGADO,
                pit__situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT,
            ).exists()

        def possui_ch_prevista_no_periodo(servidor, periodo):
            return get_ch_prevista_servidor_periodo(servidor, periodo.data_inicio, periodo.data_fim) > 0

        def get_setores_periodo(servidor, periodo):
            return get_setores_servidor_no_periodo(servidor, periodo.data_inicio, periodo.data_fim)

        def ids_servidores_com_vinculo_direto_no_periodo_pes_setor(periodo, setor):
            return PitSetores.objects.filter(
                pit__periodo_pit_rit=periodo,
                setor=setor,
            ).values_list('pit__adesao__servidor_id')

        adesoes_pes_deferidas = SolicitacaoAdesaoPesServidor.objects.filter(setor=setor_pes, situacao=SolicitacaoAdesaoPesServidor.DEFERIDO).order_by(
            'adesao__servidor__pessoa_fisica__nome'
        )
        lista_servidores_adesao_por_periodo = []
        for periodo_pit_pes in periodos_pit_pes:
            periodo_dados = {}
            periodo_dados['periodo'] = periodo_pit_pes
            lista_servidores_adesao = []

            adesoes_pes_deferidas_vinculo_pes = adesoes_pes_deferidas.filter(
                adesao__servidor__id__in=ids_servidores_com_vinculo_direto_no_periodo_pes_setor(periodo_pit_pes, setor_pes)
            )

            for adesao_pes in adesoes_pes_deferidas_vinculo_pes:
                # Servidores relacionados ao PES
                # ---------------------

                # Verificar apenas se adesão está vigente para contemplar aquele que aderiu ao PGD mas nunca criou PIT
                estah_no_pgd_no_periodo = adesao_pes.adesao.estah_vigente

                # Se o servidor está no PES
                estah_no_pes_no_periodo = SolicitacaoAdesaoPesServidor.estah_no_pes_no_periodo(adesao_pes.adesao.servidor, periodo_pit_pes.data_fim)

                if estah_no_pgd_no_periodo and estah_no_pes_no_periodo:
                    _possui_contribuicao_planejada_apenas_cadastrada_no_periodo = possui_contribuicao_planejada_apenas_cadastrada_no_periodo(
                        adesao_pes.adesao.servidor, periodo_pit_pes, adesao_pes.setor
                    )
                    _possui_contribuicao_planejada_no_periodo = possui_contribuicao_planejada_no_periodo(
                        adesao_pes.adesao.servidor, periodo_pit_pes, adesao_pes.setor
                    )
                    _possui_contribuicao_executada_apenas_cadastrada_no_periodo = possui_contribuicao_executada_apenas_cadastrada_no_periodo(
                        adesao_pes.adesao.servidor, periodo_pit_pes, adesao_pes.setor
                    )
                    _possui_contribuicao_executada_no_periodo = possui_contribuicao_executada_no_periodo(
                        adesao_pes.adesao.servidor, periodo_pit_pes, adesao_pes.setor
                    )

                    if _possui_contribuicao_planejada_no_periodo:
                        _possui_contribuicao_planejada_apenas_cadastrada_no_periodo = True
                    if _possui_contribuicao_executada_no_periodo:
                        _possui_contribuicao_executada_apenas_cadastrada_no_periodo = True

                    # Se possui contribuição planejada
                    # Se possui contribuição executada
                    if not apenas_com_pendencia_execucacao:
                        lista_servidores_adesao.append(
                            {
                                'servidor': adesao_pes.adesao.servidor,
                                'possui_contribuicao_planejada_apenas_cadastrada_no_periodo': _possui_contribuicao_planejada_apenas_cadastrada_no_periodo,
                                'possui_contribuicao_planejada_no_periodo': _possui_contribuicao_planejada_no_periodo,
                                'possui_contribuicao_executada_apenas_cadastrada_no_periodo': _possui_contribuicao_executada_apenas_cadastrada_no_periodo,
                                'possui_contribuicao_executada_no_periodo': _possui_contribuicao_executada_no_periodo,
                                'possui_ch_prevista_no_periodo': possui_ch_prevista_no_periodo(adesao_pes.adesao.servidor, periodo_pit_pes),
                                'setores_periodo': get_setores_periodo(adesao_pes.adesao.servidor, periodo_pit_pes),
                            }
                        )
                    else:
                        if not _possui_contribuicao_executada_no_periodo:
                            if possui_ch_prevista_no_periodo(adesao_pes.adesao.servidor, periodo_pit_pes):
                                lista_servidores_adesao.append(
                                    {
                                        'servidor': adesao_pes.adesao.servidor,
                                    }
                                )
            periodo_dados['servidores'] = lista_servidores_adesao
            lista_servidores_adesao_por_periodo.append(periodo_dados)

        return lista_servidores_adesao_por_periodo

    def analisar_pes_modo_simplificado(self, avaliacao_solicitacao_observacao_pes=None):
        # Atualiza PES
        self.situacao_avaliacao = PlanoEntregasSetorial.SOLICITADO_AVALIACAO
        self.avaliacao_solicitacao_observacao_pes = avaliacao_solicitacao_observacao_pes
        self.save()

        # Seta análise das entregas
        entregas_pes = self.get_entregas_aptas()
        pits = PlanoIndividualTrabalho.get_pits_por_pes(self).values('id')
        for entrega_pes in entregas_pes:
            entrega_pes.meta_analise = 100.00
            if entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE:
                entrega_pes.meta_analise = gv(
                    RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit__in=pits, entrega_pit__entrega_pes=entrega_pes).aggregate(
                        v=Sum('quantidade_progresso')
                    )
                )
            entrega_pes.entrega_analise = PlanoEntregasSetorialEntregas.EXECUTADA_TOTALMENTE
            entrega_pes.observacao_analise = 'Análise da entrega foi realizada de forma Simplificada'
            entrega_pes.save()

    def analise_foi_iniciada_mas_nao_finalizada(self):
        iniciada = self.get_entregas_aptas().filter(entrega_analise__isnull=False).exists()
        ainda_falta = self.get_entregas_aptas().filter(entrega_analise__isnull=True).exists()
        return iniciada and ainda_falta

    def analise_foi_finalizada(self):
        ainda_falta = self.get_entregas_aptas().filter(entrega_analise__isnull=True).exists()
        return not ainda_falta

    def analisar_pes_modo_detalhado(self, avaliacao_solicitacao_observacao_pes=None):
        # Atualiza PES
        self.situacao_avaliacao = PlanoEntregasSetorial.SOLICITADO_AVALIACAO
        self.avaliacao_solicitacao_observacao_pes = avaliacao_solicitacao_observacao_pes
        self.save()

    def pode_receber_copia(self, user):
        if not self.pode_editar(user):
            return False
        if self.situacao != PlanoEntregasSetorial.EM_CADASTRO:
            return False
        return not self.situacao_avaliacao

    def get_pess_podem_ser_copiados_para_este(self) -> QuerySet[PlanoEntregasSetorial]:
        pess = PlanoEntregasSetorial.objects.exclude(id=self.id)
        pess = pess.filter(situacao=PlanoEntregasSetorial.APROVADO, setor=self.setor).order_by('periodo_pes__data_inicio')
        pess = pess.filter(periodo_pes__data_fim__lt=self.periodo_pes.data_fim)
        return pess

    def copiar_outro_pes_para_este(self, pes_origem, substituir_entregas_atuais, substituir_auxiliares_atuais):
        pes_destino = self

        # Dados básicos
        # -------------------
        pes_destino.doc_percentual_maximo_teletrabalho = pes_origem.doc_percentual_maximo_teletrabalho
        pes_destino.doc_insfraestrutura = pes_origem.doc_insfraestrutura
        pes_destino.doc_tecnica = pes_origem.doc_tecnica
        pes_destino.save()

        # Dados das entregas
        # -------------------
        if substituir_entregas_atuais:
            PlanoEntregasSetorialEntregas.objects.filter(pes=pes_destino).delete()
        for entrega_a_copiar in pes_origem.get_entregas_aptas():
            entrega_copia = PlanoEntregasSetorialEntregas()
            entrega_copia.pes = pes_destino
            # --------------------
            entrega_copia.titulo = entrega_a_copiar.titulo
            entrega_copia.descricao = entrega_a_copiar.descricao
            # --------------------
            entrega_copia.metrica = entrega_a_copiar.metrica
            entrega_copia.meta = entrega_a_copiar.meta
            entrega_copia.data_prazo = entrega_a_copiar.data_prazo
            # --------------------
            entrega_copia.criterios_avaliacao = entrega_a_copiar.criterios_avaliacao
            entrega_copia.cancelado = False
            entrega_copia.save()
            # --------------------
            for atividade_processo_plan_estrategico in entrega_a_copiar.atividade_processo_plan_estrategico.all():
                entrega_copia.atividade_processo_plan_estrategico.add(atividade_processo_plan_estrategico)
            # --------------------
            for setore_demandante in entrega_a_copiar.setores_demandantes.all():
                entrega_copia.setores_demandantes.add(setore_demandante)
            # --------------------
            for vinculo_demandante in entrega_a_copiar.vinculos_demandantes.all():
                entrega_copia.vinculos_demandantes.add(vinculo_demandante)
            # --------------------
            for setor_destinatario in entrega_a_copiar.setores_destinatarios.all():
                entrega_copia.setores_destinatarios.add(setor_destinatario)
            # --------------------
            for vinculo_destinatario in entrega_a_copiar.vinculos_destinatarios.all():
                entrega_copia.vinculos_destinatarios.add(vinculo_destinatario)

        # Dados dos auxiliares
        # -------------------
        if substituir_auxiliares_atuais:
            pes_destino.auxiliares.clear()
        for auxiliar in pes_origem.auxiliares.all():
            pes_destino.auxiliares.add(auxiliar)

    # ===================================
    # API
    # ===================================
    def get_grupo_pes_api(self):
        if self.cod_siape_grupo:
            return PlanoEntregasSetorial.get_pess_aprovados().filter(
                cod_siape_grupo__isnull=False, cod_siape_grupo=self.cod_siape_grupo, periodo_pes=self.periodo_pes
            )
        return PlanoEntregasSetorial.objects.none()

    def get_grupo_pes_api_links(self):
        grupo = self.get_grupo_pes_api()
        if grupo:
            strs = []
            for g in grupo:
                strs.append(f'<a href="/pgd2/visualizar_pes/{g.id}/">{g.setor}</a>')
            return mark_safe(', '.join(strs))
        return None

    def get_situacao_para_api(self):
        """
        Indica qual o status do plano de entregas. O código deve corresponder às seguintes categorias:
        1 - Cancelado
        2 - Aprovado
        3 - Em execução
        4 - Concluído
        5 - Avaliado

        Regras de validação:
        - a categoria "5" só poderá ser usada se os campos "avaliacao" e "data_avaliacao" estiverem preenchidos.
        - É obrigatório o envio dos planos nos status "3", "4" e "5".
        - Os planos nos demais status não precisam necessariamente ser enviados.
        """

        if self.estah_avaliado():
            return 5

        if self.estah_aprovado() and (self.periodo_pes.data_fim < get_datetime_now().date()):
            return 4

        if self.em_execucao:
            return 3

        if self.estah_aprovado():
            return 2

        return None

    def get_avaliacao_para_api(self):
        if self.avaliacao_pes:
            return self.avaliacao_pes
        return None

    def get_data_avaliacao_para_api(self):
        r = RegistroAcaoPES.objects.filter(tipo=RegistroAcaoPES.TIPO_AVALIOU, pes=self).order_by('data').first()
        if r:
            return str(r.data.date())
        return None


class PlanoEntregasSetorialAprovacao(PlanoEntregasSetorial):
    class Meta:
        verbose_name = 'Plano de Entregas Setorial'
        verbose_name_plural = 'Planos de Entregas Setorial'
        proxy = True


class PlanoEntregasSetorialAvaliacao(PlanoEntregasSetorial):
    class Meta:
        verbose_name = 'Plano de Entregas Setorial'
        verbose_name_plural = 'Planos de Entregas Setorial'
        proxy = True


class PlanoEntregasSetorialConsulta(PlanoEntregasSetorial):
    class Meta:
        verbose_name = 'Plano de Entregas Setorial'
        verbose_name_plural = 'Planos de Entregas Setorial'
        proxy = True


class RegistroAcaoPES(RegistroAcaoPGD):
    TIPO_CRIACAO = 1
    TIPO_SOLICITOU_APROVACAO = 2
    TIPO_APROVACAO = 3
    TIPO_REPROVACAO = 17

    TIPO_EDITOU_DOCUMENTACAO = 4

    TIPO_CADASTROU_HORARIO_FUNCIONAMENTO_DO_SETOR = 5
    TIPO_EDITOU_HORARIO_FUNCIONAMENTO_DO_SETOR = 6
    TIPO_REMOVEU_HORARIO_FUNCIONAMENTO_DO_SETOR = 7

    TIPO_CADASTROU_HORARIO_PLANEJAMENTO_DO_SETOR = 8
    TIPO_EDITOU_HORARIO_PLANEJAMENTO_DO_SETOR = 9
    TIPO_REMOVEU_HORARIO_PLANEJAMENTO_DO_SETOR = 10

    TIPO_CADASTROU_ENTREGA = 11
    TIPO_EDITOU_ENTREGA = 12
    TIPO_REMOVEU_ENTREGA = 13

    TIPO_EDITOU_AUXILIARES = 14

    TIPO_SOLICITOU_AVALIACAO = 15
    TIPO_AVALIOU = 16
    TIPO_REABRIU = 18

    # Vai completar o log. Exemplo: "Criou" o PES ..., "Editou dados" do PES ...

    TIPO_CHOICES = (
        (TIPO_CRIACAO, 'Criou'),
        (TIPO_SOLICITOU_APROVACAO, 'Solicitou aprovação'),
        (TIPO_APROVACAO, 'Aprovou'),
        (TIPO_REPROVACAO, 'Reprovou'),
        (TIPO_EDITOU_DOCUMENTACAO, 'Editou a documentação'),
        (TIPO_CADASTROU_HORARIO_FUNCIONAMENTO_DO_SETOR, 'Cadastrou horário de funcionamento do setor'),
        (TIPO_EDITOU_HORARIO_FUNCIONAMENTO_DO_SETOR, 'Editou horário de funcionamento do setor'),
        (TIPO_REMOVEU_HORARIO_FUNCIONAMENTO_DO_SETOR, 'Removeu horário de funcionamento do setor'),
        (TIPO_CADASTROU_HORARIO_PLANEJAMENTO_DO_SETOR, 'Cadastrou horário de planejamento do setor'),
        (TIPO_EDITOU_HORARIO_PLANEJAMENTO_DO_SETOR, 'Editou horário de planejamento do setor'),
        (TIPO_REMOVEU_HORARIO_PLANEJAMENTO_DO_SETOR, 'Removeu horário de planejamento do setor'),
        (TIPO_CADASTROU_ENTREGA, 'Cadastrou entrega no planejamento do setor'),
        (TIPO_EDITOU_ENTREGA, 'Editou entrega no planejamento do setor'),
        (TIPO_REMOVEU_ENTREGA, 'Removeu entrega no planejamento do setor'),
        (TIPO_EDITOU_AUXILIARES, 'Editou auxiliares no planejamento do setor'),
        (TIPO_SOLICITOU_AVALIACAO, 'Solicitou avaliação da execução'),
        (TIPO_AVALIOU, 'Avaliou execução'),
        (TIPO_REABRIU, 'Reabriu'),
    )

    user = models.CurrentUserField(editable=False, related_name='rapes_pgd2')
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', editable=False, null=True)
    realizada_apos_aprovacao_pes = models.BooleanField('Realizado após aprovação do PES', default=False)

    @staticmethod
    def registrar(request, tipo, pes, obs='', dados_de_para=None):
        ip = get_client_ip(request)
        realizada_apos_aprovacao_pes = False
        if pes.estah_aprovado():
            realizada_apos_aprovacao_pes = True
        RegistroAcaoPES.objects.create(
            tipo=tipo, pes=pes, ip=ip, observacao=obs, realizada_apos_aprovacao_pes=realizada_apos_aprovacao_pes, de_para=dados_de_para
        )


class PlanoEntregasSetorialHorarioFuncionamentoSetor(models.ModelPlus):
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', verbose_name='PES', related_name='pes_horariofuncionamentosetor_pgd2')
    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora Inicial', help_text='Formato: HH:MM.')
    hora_final = models.TimeFieldPlus('Hora Final', help_text='Formato: HH:MM.')

    recorrencia = models.ForeignKeyPlus('pgd2.ControleRecorrenciaPGD', null=True, blank=True)
    timestamp_data_hora_inicio = models.FloatField(null=True)

    class Meta:
        verbose_name = 'Horário Funcionamento Setor'
        verbose_name_plural = 'Horários Funcionamento Setor'

    def __str__(self):
        return f'Horário de Funcionamento do Setor em {format_datetime(self.data)} de {self.hora_inicio!s} a {self.hora_final!s}'

    @staticmethod
    def get_horarios_funcionamento_setor_agrupado_por_semana(pes, recorrencia=None):
        pes_horarios_funcionamento_setor = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=pes).order_by('data', 'hora_inicio')
        if recorrencia:
            pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(recorrencia=recorrencia)

        # obtendo as semanas relacionadas considerando as datas cadastradas
        def get_semanas_por_datas(datas):
            semanas = {}
            for data in datas:
                semana = data.isocalendar().week
                if semana not in semanas:
                    inicio = data - timedelta(days=data.weekday())
                    final = inicio + timedelta(days=6)

                    # Se a data final extrapolar o o fim do PES então é preciso ajustar
                    if final > pes.get_data_fim():
                        final = pes.get_data_fim()
                    semanas[semana] = {'inicio': inicio, 'final': final, 'hfss': []}
            return semanas

        datas = pes_horarios_funcionamento_setor.values_list('data', flat=True)
        semanas = get_semanas_por_datas(datas)
        for hfs in pes_horarios_funcionamento_setor:
            semanas[hfs.data.isocalendar().week]['hfss'].append(hfs)

        return semanas

    # ------------------------
    # Cadastro/Ateracao Comum
    # ------------------------
    @staticmethod
    def validar_cadastro(pes, data, hora_inicio, hora_final, ids_horarios_desconsiderar=None):
        horas_dia = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=pes, data=data).order_by('data', 'hora_inicio')
        if ids_horarios_desconsiderar:
            horas_dia = horas_dia.exclude(id__in=ids_horarios_desconsiderar)
        # Não pode ter conflito de horário no mesmo dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for hd in horas_dia:
            # Se inicia dentro ou termina dentro
            if not all([hd.hora_inicio, hora_inicio, hd.hora_final, hora_final]):
                tem_erro_nos_dados = True
            if not tem_erro_nos_dados and ((hd.hora_inicio <= hora_inicio <= hd.hora_final) or (hd.hora_inicio <= hora_final <= hd.hora_final)):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    # ------------------------
    # Cadastro Recorrente
    # ------------------------
    @staticmethod
    def validar_cadastro_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        for d in datas_para_cadastrar:
            pode, erro = PlanoEntregasSetorialHorarioFuncionamentoSetor.validar_cadastro(pes, d, hora_inicio, hora_final)
            if not pode:
                return pode, erro

        return True, None

    @staticmethod
    def cadastrar_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        cr = ControleRecorrenciaPGD.get_novo_controle_recorrencia()
        for d in datas_para_cadastrar:
            pes_hfs = PlanoEntregasSetorialHorarioFuncionamentoSetor()
            pes_hfs.pes = pes
            pes_hfs.data = d
            pes_hfs.hora_inicio = hora_inicio
            pes_hfs.hora_final = hora_final
            pes_hfs.recorrencia = cr
            pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
                d.year, d.month, d.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            pes_hfs.save()

    # ------------------------
    # Alteracao Recorrente
    # ------------------------
    @staticmethod
    def validar_alteracao_recorrente(pes, pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # pes_hfs: quem está sendo editado
        # hora_inicio, hora_final: hora para a qual está tentando alterar o cadastro de pes_hfs
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # pega todos
        datas_para_validar = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=pes).order_by('timestamp_data_hora_inicio')
        recorrencia_pes_hfs = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(recorrencia=pes_hfs.recorrencia).order_by(
            'timestamp_data_hora_inicio'
        )

        # exclui todos fora do periodo da recorrencia E exclui todos da recorrencia
        if recorrencia_pes_hfs:
            data_inicio_recorrencia = recorrencia_pes_hfs[0].data
            data_final_recorrencia = recorrencia_pes_hfs[len(recorrencia_pes_hfs) - 1].data
            datas_para_validar = datas_para_validar.exclude(id__in=recorrencia_pes_hfs.values_list('id', flat=True))
        datas_para_validar = datas_para_validar.exclude(Q(data__lt=data_inicio_recorrencia) | Q(data__gt=data_final_recorrencia))

        # este_e_proximos: exclui todos com data antes ao que se deseja editar
        if tipo_recorrencia == 'este_e_proximos':
            datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # este_e_anteriores: exclui todos com data depois ao que se deseja editar
        if tipo_recorrencia == 'este_e_anteriores':
            datas_para_validar = datas_para_validar.exclude(data__gt=pes_hfs.data)

        # todos: ???????????? 'Todos da recorrência'
        # if tipo_recorrencia == 'todos':
        #    datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # Validando todos os cadastros dia a dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for d in datas_para_validar:
            # Se inicia dentro ou termina dentro
            if not all([d.hora_inicio, hora_inicio, d.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break
            if (d.hora_inicio <= hora_inicio <= d.hora_final) or (d.hora_inicio <= hora_final <= d.hora_final):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    @staticmethod
    def alterar_recorrente(pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # **** EDITA ESTE E OS OUTROS

        # pes_hfs: quem está sendo editado
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # Montando as datas que serão editadas
        # - ALTERAR 'este_e_proximos': VOU EDITAR (Este) E (Todos os proximos da recorrencia)
        # - ALTERAR 'este_e_anteriores': VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
        # - ALTERAR 'todos': VOU EDITAR (Este) E (Todos da recorrencia)
        datas_para_alterar = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(recorrencia=pes_hfs.recorrencia).order_by(
            'timestamp_data_hora_inicio'
        )
        if tipo_recorrencia == 'este_e_proximos':
            # VOU EDITAR (Este) E (Todos os proximos da recorrencia)
            datas_para_alterar = datas_para_alterar.filter(timestamp_data_hora_inicio__gte=pes_hfs.timestamp_data_hora_inicio)
        if tipo_recorrencia == 'este_e_anteriores':
            # VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
            datas_para_alterar = datas_para_alterar.exclude(timestamp_data_hora_inicio__lte=pes_hfs.timestamp_data_hora_inicio)
        # tipo_recorrencia == 'todos':
        # VOU EDITAR (Este) E (Todos da recorrencia)
        # datas_para_alterar (completo)

        # Alterando os dados
        # Este
        pes_hfs.hora_inicio = hora_inicio
        pes_hfs.hora_final = hora_final
        pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
            pes_hfs.data.year, pes_hfs.data.month, pes_hfs.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        pes_hfs.save()
        # Outros
        for d in datas_para_alterar:
            d.hora_inicio = hora_inicio
            d.hora_final = hora_final
            d.timestamp_data_hora_inicio = datetime.datetime(
                d.data.year, d.data.month, d.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            d.save()

        return True, None


class PlanoEntregasSetorialHorarioPlanejamentoSetor(models.ModelPlus):
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', verbose_name='PES', related_name='pes_horarioplanejamentosetor_pgd2')
    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora Inicial', help_text='Formato: HH:MM.')
    hora_final = models.TimeFieldPlus('Hora Final', help_text='Formato: HH:MM.')
    REUNIAO_ONLINE = 1
    REUNIAO_PRESENCIAL = 2
    REUNIAO_HIBRIDA = 3
    REUNIAO_CHOICES = [[REUNIAO_ONLINE, 'Reunião online'], [REUNIAO_PRESENCIAL, 'Reunião presencial'], [REUNIAO_HIBRIDA, 'Reunião híbrida']]
    reuniao = models.PositiveIntegerField('Reunião', choices=REUNIAO_CHOICES)

    recorrencia = models.ForeignKeyPlus('pgd2.ControleRecorrenciaPGD', null=True, blank=True)
    timestamp_data_hora_inicio = models.FloatField(null=True)

    class Meta:
        verbose_name = 'Horário de Planejamento do Setor'
        verbose_name_plural = 'Horários de Planejamento do Setor'

    def __str__(self):
        return f'Horário de Planejamento do Setor em {format_datetime(self.data)} de {self.hora_inicio!s} a {self.hora_final!s}'

    def estah_conforme_horario_funcionamento_setor(self):
        h = PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=self.pes, data=self.data)
        h = h.filter(Q(hora_inicio__lte=self.hora_inicio) & Q(hora_final__gte=self.hora_final)).exists()
        return h

    @staticmethod
    def get_horarios_planejamento_setor_agrupado_por_semana(pes, recorrencia=None):
        pes_horarios_funcionamento_setor = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=pes).order_by('data', 'hora_inicio')
        if recorrencia:
            pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(recorrencia=recorrencia)

        # obtendo as semanas relacionadas considerando as datas cadastradas
        def get_semanas_por_datas(datas):
            semanas = {}
            for data in datas:
                semana = data.isocalendar().week
                if semana not in semanas:
                    inicio = data - timedelta(days=data.weekday())
                    final = inicio + timedelta(days=6)

                    # Se a data final extrapolar o o fim do PES então é preciso ajustar
                    if final > pes.get_data_fim():
                        final = pes.get_data_fim()
                    semanas[semana] = {'inicio': inicio, 'final': final, 'hfss': []}
            return semanas

        datas = pes_horarios_funcionamento_setor.values_list('data', flat=True)
        semanas = get_semanas_por_datas(datas)
        for hfs in pes_horarios_funcionamento_setor:
            semanas[hfs.data.isocalendar().week]['hfss'].append(hfs)

        return semanas

    # ------------------------
    # Cadastro/Ateracao Comum
    # ------------------------
    @staticmethod
    def validar_cadastro(pes, data, hora_inicio, hora_final, ids_horarios_desconsiderar=None):
        horas_dia = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=pes, data=data).order_by('data', 'hora_inicio')
        if ids_horarios_desconsiderar:
            horas_dia = horas_dia.exclude(id__in=ids_horarios_desconsiderar)
        # Não pode ter conflito de horário no mesmo dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for hd in horas_dia:
            if not all([hd.hora_inicio, hora_inicio, hd.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break

            # Se inicia dentro ou termina dentro
            if not tem_erro_nos_dados and ((hd.hora_inicio <= hora_inicio <= hd.hora_final) or (hd.hora_inicio <= hora_final <= hd.hora_final)):
                tem_conflito = True
                break

        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    # ------------------------
    # Cadastro Recorrente
    # ------------------------
    @staticmethod
    def validar_cadastro_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        for d in datas_para_cadastrar:
            pode, erro = PlanoEntregasSetorialHorarioPlanejamentoSetor.validar_cadastro(pes, d, hora_inicio, hora_final)
            if not pode:
                return pode, erro

        return True, None

    @staticmethod
    def cadastrar_recorrente(pes, data, hora_inicio, hora_final, data_ate, reuniao, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        cr = ControleRecorrenciaPGD.get_novo_controle_recorrencia()
        for d in datas_para_cadastrar:
            pes_hfs = PlanoEntregasSetorialHorarioPlanejamentoSetor()
            pes_hfs.pes = pes
            pes_hfs.data = d
            pes_hfs.hora_inicio = hora_inicio
            pes_hfs.hora_final = hora_final
            pes_hfs.recorrencia = cr
            pes_hfs.reuniao = reuniao
            pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
                d.year, d.month, d.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            pes_hfs.save()

    # ------------------------
    # Alteracao Recorrente
    # ------------------------
    @staticmethod
    def validar_alteracao_recorrente(pes, pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # pes_hfs: quem está sendo editado
        # hora_inicio, hora_final: hora para a qual está tentando alterar o cadastro de pes_hfs
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # pega todos
        datas_para_validar = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(pes=pes).order_by('timestamp_data_hora_inicio')
        recorrencia_pes_hfs = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(recorrencia=pes_hfs.recorrencia).order_by(
            'timestamp_data_hora_inicio'
        )

        # exclui todos fora do periodo da recorrencia E exclui todos da recorrencia
        if recorrencia_pes_hfs:
            data_inicio_recorrencia = recorrencia_pes_hfs[0].data
            data_final_recorrencia = recorrencia_pes_hfs[len(recorrencia_pes_hfs) - 1].data
            datas_para_validar = datas_para_validar.exclude(id__in=recorrencia_pes_hfs.values_list('id', flat=True))
        datas_para_validar = datas_para_validar.exclude(Q(data__lt=data_inicio_recorrencia) | Q(data__gt=data_final_recorrencia))

        # este_e_proximos: exclui todos com data antes ao que se deseja editar
        if tipo_recorrencia == 'este_e_proximos':
            datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # este_e_anteriores: exclui todos com data depois ao que se deseja editar
        if tipo_recorrencia == 'este_e_anteriores':
            datas_para_validar = datas_para_validar.exclude(data__gt=pes_hfs.data)

        # todos: ???????????? 'Todos da recorrência'
        # if tipo_recorrencia == 'todos':
        #    datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # Validando todos os cadastros dia a dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for d in datas_para_validar:
            if not all([d.hora_inicio, hora_inicio, d.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break
            # Se inicia dentro ou termina dentro
            if (d.hora_inicio <= hora_inicio <= d.hora_final) or (d.hora_inicio <= hora_final <= d.hora_final):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    @staticmethod
    def alterar_recorrente(pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # **** EDITA ESTE E OS OUTROS

        # pes_hfs: quem está sendo editado
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # Montando as datas que serão editadas
        # - ALTERAR 'este_e_proximos': VOU EDITAR (Este) E (Todos os proximos da recorrencia)
        # - ALTERAR 'este_e_anteriores': VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
        # - ALTERAR 'todos': VOU EDITAR (Este) E (Todos da recorrencia)
        datas_para_alterar = PlanoEntregasSetorialHorarioPlanejamentoSetor.objects.filter(recorrencia=pes_hfs.recorrencia).order_by(
            'timestamp_data_hora_inicio'
        )
        if tipo_recorrencia == 'este_e_proximos':
            # VOU EDITAR (Este) E (Todos os proximos da recorrencia)
            datas_para_alterar = datas_para_alterar.filter(timestamp_data_hora_inicio__gte=pes_hfs.timestamp_data_hora_inicio)
        if tipo_recorrencia == 'este_e_anteriores':
            # VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
            datas_para_alterar = datas_para_alterar.exclude(timestamp_data_hora_inicio__lte=pes_hfs.timestamp_data_hora_inicio)
        # tipo_recorrencia == 'todos':
        # VOU EDITAR (Este) E (Todos da recorrencia)
        # datas_para_alterar (completo)

        # Alterando os dados
        # Este
        pes_hfs.hora_inicio = hora_inicio
        pes_hfs.hora_final = hora_final
        pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
            pes_hfs.data.year, pes_hfs.data.month, pes_hfs.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        pes_hfs.save()
        # Outros
        for d in datas_para_alterar:
            d.hora_inicio = hora_inicio
            d.hora_final = hora_final
            d.timestamp_data_hora_inicio = datetime.datetime(
                d.data.year, d.data.month, d.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            d.save()

        return True, None


class PlanoEntregasSetorialEntregas(models.ModelPlus):
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', verbose_name='PES', related_name='pes_entrega_pgd2')

    # --------------------
    # Cadastro
    # --------------------
    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    PERCENTUAL = 1
    QUANTIDADE = 2
    METRICA_META_PES_CHOICES = [[PERCENTUAL, 'Percentual'], [QUANTIDADE, 'Quantidade']]
    metrica = models.PositiveIntegerField('Métrica da meta', choices=METRICA_META_PES_CHOICES, default=PERCENTUAL)
    meta = models.DecimalFieldPlus(verbose_name='Meta', default=0)

    # --------------------

    data_prazo = models.DateFieldPlus(verbose_name='Prazo', null=True, blank=True)

    # --------------------

    criterios_avaliacao = models.TextField(
        verbose_name='Critérios de avaliação',
        help_text=f'Critérios de avaliação a serem utilizados na avaliação da execução desta entrega em um {nomenclatura.pit_rit_pgd2}',
    )

    # --------------------
    # Vinculação com Planejamento Estratégico através das Atividade do processo
    # --------------------
    atividade_processo_plan_estrategico = models.ManyToManyFieldPlus(
        'plan_estrategico.AtividadeEtapa',
        verbose_name='Atividade do processo - Planejamento Estratégico',
        blank=True,
        related_name='pes_entregas_atividade_processo_plan_estrategico_pgd2',
    )

    # --------------------

    setores_demandantes = models.ManyToManyFieldPlus(
        'rh.Setor', verbose_name='Setores Demandantes', blank=True, related_name='pes_setores_demandantes_pgd2'
    )
    vinculos_demandantes = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Pessoas Demandantes', blank=True, related_name='pes_vinculos_demandantes_pgd2'
    )
    setores_destinatarios = models.ManyToManyFieldPlus(
        'rh.Setor', verbose_name='Setores Destinatários', blank=True, related_name='pes_setores_destinatarios_pgd2'
    )
    vinculos_destinatarios = models.ManyToManyFieldPlus(
        'comum.Vinculo', verbose_name='Pessoas Destinatárias', blank=True, related_name='pes_vinculos_destinatarios_pgd2'
    )

    # --------------------

    cancelado = models.BooleanField('Cancelado', default=False)

    # --------------------
    # Análise da entrega
    # --------------------
    meta_analise = models.DecimalFieldPlus(verbose_name='Análise da meta', null=True)
    EXECUTADA_TOTALMENTE = 1
    EXECUTADA_PARCIALMENTE = 2
    EXECUTADA_NAO = 3
    ANALISE_ENTREGA_EXECUCAO_CHOICES = [
        [EXECUTADA_TOTALMENTE, 'Executada Totalmente'],
        [EXECUTADA_PARCIALMENTE, 'Executada Parcialmente'],
        [EXECUTADA_NAO, 'Não Executada'],
    ]
    entrega_analise = models.PositiveIntegerField('Análise da entrega', choices=ANALISE_ENTREGA_EXECUCAO_CHOICES, null=True)
    observacao_analise = models.TextField(verbose_name='Justificativa/Observação', blank=True, null=True)

    def get_metrica_para_api(self):
        if self.metrica == self.PERCENTUAL:
            return 'percentual'
        return 'unidade'

    def get_data_entrega_para_api(self):
        if self.data_prazo:
            return str(self.data_prazo)
        return str(self.pes.periodo_pes.data_inicio)

    def get_demandante_para_api(self):
        if self.setores_demandantes.exists():
            return str(self.setores_demandantes.first())
        sigla_reitoria = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
        return str(Setor.objects.suap().get(sigla=sigla_reitoria))

    def get_destinatario_para_api(self):
        if self.setores_destinatarios.exists():
            return str(self.setores_destinatarios.first())
        sigla_reitoria = Configuracao.get_valor_por_chave('comum', 'reitoria_sigla')
        return str(Setor.objects.suap().get(sigla=sigla_reitoria))

    class Meta:
        verbose_name = 'Entrega do Plano de Entrega do Setor'
        verbose_name_plural = 'Entregas do Plano de Entrega do Setor'

    def __str__(self):
        return f'Entrega {self.titulo} do {self.pes}'

    def get_atividade_processo_plan_estrategico(self):
        return self.atividade_processo_plan_estrategico.all().select_related(
            'unidade_gestora__setor_equivalente',
            'etapa_projeto_plano_atividade__projeto_plano_atividade__plano_atividade',
            'etapa_projeto_plano_atividade__etapa',
        )

    def get_verbose_para_pit(self):
        return mark_safe(f'{self.titulo} | <strong>{self.pes.setor.get_caminho_as_html()}<strong>')

    def get_meta_str(self):
        if self.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL:
            return f'{format_money(self.meta)}%'
        return int(self.meta)

    def get_setores_demandantes(self):
        vazio = True
        strs = []
        strs.append('<ul>')
        for o in self.setores_demandantes.all():
            strs.append(f'<li>{get_sigla_setor_uo(o)}</li>')
            vazio = False
        strs.append('<ul>')
        if vazio:
            return []
        return mark_safe(''.join(strs))

    def get_setores_destinatarios(self):
        vazio = True
        strs = []
        strs.append('<ul>')
        for o in self.setores_destinatarios.all():
            strs.append(f'<li>{get_sigla_setor_uo(o)}</li>')
            vazio = False
        strs.append('<ul>')
        if vazio:
            return []
        return mark_safe(''.join(strs))

    def get_vinculos_demandantes(self):
        vazio = True
        strs = []
        strs.append('<ul>')
        for o in self.vinculos_demandantes.all():
            strs.append(f'<li>{o!s}</li>')
            vazio = False
        strs.append('<ul>')
        if vazio:
            return []
        return mark_safe(''.join(strs))

    def get_vinculos_destinatarios(self):
        vazio = True
        strs = []
        strs.append('<ul>')
        for o in self.vinculos_destinatarios.all():
            strs.append(f'<li>{o!s}</li>')
            vazio = False
        strs.append('<ul>')
        if vazio:
            return []
        return mark_safe(''.join(strs))

    def pode_cancelar_entrega(self, user=None):
        if user and not self.pes.pode_editar(user):
            return False

        # se nunca foi aprovado não pode
        if not self.pes.estah_aprovado():
            return False

        if self.cancelado:
            return False

        # Se tiver vinculado a algum RIT, exceto
        # - RIT for relacionado a PIT cancelado
        # - RIT que esteja em cadastro
        return (
            not RelatorioIndividualTrabalho.objects.filter(entrega_pit__entrega_pes=self)
            .exclude(
                Q(entrega_pit__pit__situacao=PlanoIndividualTrabalho.CANCELADO)
                | Q(entrega_pit__pit__situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT)
            )
            .exists()
        )

    def pode_descancelar_entrega(self, user=None):
        if user and not self.pes.pode_editar(user):
            return False
        return self.cancelado

    def pode_remover_entrega(self, user=None):
        if not self.pes.pode_editar(user):
            return False

        # se já tiver sido aprovado alguma vez não pode
        if self.pes.estah_aprovado():
            return False

        # se tiver entrega de PIT não pode
        return not PlanoIndividualTrabalhoEntregas.objects.filter(entrega_pes=self).exists()

    def tem_metrica_de_quantidade(self):
        return self.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE

    def get_analise_entrega_str(self):
        if self.entrega_analise:
            meta_analise = None
            if self.metrica == PlanoEntregasSetorialEntregas.PERCENTUAL:
                meta_analise = f'{format_money(self.meta_analise)}%'
            else:
                meta_analise = int(self.meta_analise)
            entrega_analise = self.get_entrega_analise_display()

            if self.observacao_analise:
                return f'{entrega_analise} ({meta_analise}) - {self.observacao_analise}'
            return f'{entrega_analise} ({meta_analise})'
        return '-'

    def foi_analisada(self):
        return bool(self.entrega_analise)

    def pode_analisar_entrega(self, pode_solicitar_avaliacao=None, user=None, entregas_aptas_do_pes=None):
        pode_pelo_pes = False
        if pode_solicitar_avaliacao is None:
            if user is None:
                pode_pelo_pes = False
            else:
                pode_pelo_pes = self.pes.pode_solicitar_avaliacao(user)[0]
        else:
            pode_pelo_pes = pode_solicitar_avaliacao

        pode_pela_entrega = False
        if entregas_aptas_do_pes is None:
            pode_pela_entrega = self.pes.get_entregas_aptas().filter(id=self.id).exists()
        else:
            pode_pela_entrega = entregas_aptas_do_pes.filter(id=self.id).exists()

        return pode_pelo_pes and pode_pela_entrega


# ====================================================
# Adesão PGD
# ====================================================


class SolicitacaoAdesaoServidor(models.ModelPlus):
    # Adesão ao PGD
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', related_name='servidor_soladesao_pgd2')
    documento_adesao = models.ForeignKeyPlus('pgd2.DocumentoAdesaoServidor', verbose_name='Servidor', related_name='docadesao_soladesao_pgd2')

    # CONTATO PGD
    codigo_contato_pais = models.PositiveIntegerField('Código do país', null=True, default='55')
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

    data_inicio = models.DateFieldPlus('Data início da adesão', null=True)

    data_desligamento_efeitos_a_partir_de = models.DateFieldPlus('Desligamento com efeitos a partir de', null=True)
    data_desligamento_carencia_ate = models.DateFieldPlus('Desligamento com carência até', null=True)
    data_pode_solicitar_nova_adesao = models.DateFieldPlus('A partir desta data já pode solicitar nova adesão', null=True)

    class Meta:
        verbose_name = 'Adesão do Servidor ao PGD'
        verbose_name_plural = 'Adesões do Servidor ao PGD'

    def __str__(self):
        if self.estah_deferida:
            data_inicio = format_datetime(self.get_data_inicio_adesao())
            data_fim = self.get_data_final_adesao()
            if data_fim:
                data_fim = format_datetime(data_fim)
                return f'Adesão do Servidor {self.servidor} ao PGD de {data_inicio} até {data_fim}'
            return f'Adesão do Servidor {self.servidor} ao PGD de {data_inicio} até Atualidade'
        return f'Solicitação de Adesão do Servidor {self.servidor} ao PGD'

    def get_verbose_simples(self):
        if self.estah_deferida:
            data_inicio = format_datetime(self.get_data_inicio_adesao())
            data_fim = self.get_data_final_adesao()
            if data_fim:
                data_fim = format_datetime(data_fim)
                return f'Adesão ao PGD de {data_inicio} até {data_fim}'
            return f'Adesão ao PGD de {data_inicio} até Atualidade'
        return 'Solicitação de Adesão ao PGD'

    # -----------------------
    # Obter dados gerais
    # -----------------------
    def get_data_situacao_atual(self):
        if self.situacao:
            r = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao=self).order_by('-id')
            if r:
                return r.last().data
        return None

    get_data_situacao_atual.short_description = 'Data/Hora da Situação Atual'

    def get_contato_preferencia(self):
        if self.preferencia_contato == self.PREFERENCIA_CONTATO_LIGACAO:
            return mark_safe(f'+{self.codigo_contato_pais} {self.telefone} (Preferencialmente Ligação)')
        elif self.preferencia_contato == self.PREFERENCIA_CONTATO_WHATS:
            return mark_safe(f'+{self.codigo_contato_pais} {self.telefone} {self.link_whats}')
        elif self.preferencia_contato == self.PREFERENCIA_CONTATO_EMAIL:
            return mark_safe(
                f'+{self.codigo_contato_pais} {self.telefone} <a href="mailto:{self.servidor.email_institucional}" class="btn sm ms-3"><span class="fa fa-envelope" aria-hidden="true"></span> Preferencialmente e-mail institucional</a>'
            )
        else:
            return mark_safe(f'+{self.codigo_contato_pais} {self.telefone} ({self.get_preferencia_contato_display()})')

    def get_pits(self):
        return PlanoIndividualTrabalho.objects.filter(adesao=self).exclude(situacao=PlanoIndividualTrabalho.CANCELADO).order_by('data_inicio')

    def get_pits_todos(self):
        return PlanoIndividualTrabalho.objects.filter(adesao=self).order_by('-data_inicio')

    @property
    def link_whats(self):
        if self.preferencia_contato == self.PREFERENCIA_CONTATO_WHATS:
            telefone_limpo = self.telefone.replace('(', '').replace(')', '').replace(' ', '').replace('-', '')
            return mark_safe(
                f'<a href="https://wa.me/+{self.codigo_contato_pais}{telefone_limpo}" class="btn sm ms-3"><span class="fab fa-whatsapp" aria-hidden="true"></span> Preferencialmente WhatsApp</a></li>'
            )
        return None

    def get_adesoes_pes(self):
        return SolicitacaoAdesaoPesServidor.objects.filter(adesao=self)

    @staticmethod
    def get_solicitacoes_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True):
        # Deve considerar
        # - Solicitações que o chefe DEVE aprovar
        # - Solicitações que o chefe PODE aprovar

        setores = []
        servidores = []
        setores_hoje = []
        servidores_exclude = []
        if apenas_chefe_direto:
            # ----------------------------------------------
            # Que o chefe DEVE aprovar/homologar
            # Considera apenas os setores e servidores que é chefe direto
            # ----------------------------------------------
            # Setores que é chefe direto. Exemplo: DIGPE
            setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Chefes dos subsetores da DIGPE. Exemplo: Chefe CODEPE, Chefe CODEPE, Chefe COGCAP, Chefe COADPE e Chefe COASS
            servidores = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Todos os subsetores da DIGPE
            setores_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        else:
            # ----------------------------------------------
            # Que o chefe PODE aprovar/homologar
            # Considera os setores descendentes e exclui setores que é chefe direto
            # ----------------------------------------------
            # Todos os setores que é chefe incluindo a DIGPE e seus Subsetores
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            # Setores que é chefe direto. Exemplo: DIGPE
            setores_chefe_direto = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Exclui a DIGPE
            setores = setores.exclude(id__in=setores_chefe_direto.values('id'))
            # Excluir do PODE os servidores do DEVE
            servidores_exclude = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())

        if not setores:
            return SolicitacaoAdesaoServidor.objects.none()

        solicitacoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.SOLICITADO).exclude(servidor__vinculos__user=user)

        querys = []

        querys.append(Q(servidor__setor__in=setores))

        if servidores and setores_hoje:
            querys.append(Q(servidor__in=servidores) & Q(servidor__setor__in=setores_hoje))

        if apenas_chefe_direto and considerar_auditoria_centralizada() and get_setor_auditoria_centralizada() in setores:
            solicitacoes_auditoria = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.SOLICITADO).exclude(
                servidor__vinculos__user=user
            )
            solicitacoes_auditoria = solicitacoes_auditoria.filter(
                # Q(servidor__setor__in=setores) | Q(servidor__cargo_emprego__codigo__in=get_codigos_cargo_emprego_auditor())
                Q(servidor__setor__in=setores) | Q(servidor__in=get_servidores_auditoria())
            )
            querys.append(Q(id__in=solicitacoes_auditoria.values_list('id', flat=True)))

        solicitacoes = solicitacoes.filter(reduce(operator.or_, querys))
        if servidores_exclude:
            solicitacoes = solicitacoes.exclude(servidor__in=servidores_exclude)

        return solicitacoes

    @staticmethod
    def get_regras_relacionadas_ao_periodo(solicitacao_adesao=None):
        data = None
        if solicitacao_adesao:
            r = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(solicitacao=solicitacao_adesao).order_by('-id')
            data = r.last().data
        else:
            data = get_datetime_now().date()
        return DocumentoAdesaoServidor.objects.filter(data_inicio__lte=data, cancelado=False).last()

    def get_periodos_pits(self):
        return self.get_pits().values_list('data_inicio', 'data_fim')

    # -----------------------
    # Cadastro e Visualizar
    # -----------------------

    @staticmethod
    def pode_visualizar_lista(user):
        # lista do admin
        return bool(user.has_perm('rh.chefe'))

    def pode_visualizar(self, user):
        # pode visualizar uma solicitação específica
        quem_solicitou = self.servidor == user.get_relacionamento()

        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        eh_chefe_do_servidor = setores.filter(pk=self.servidor.setor_id).exists()
        pode_por_ser_auditor = considerar_auditoria_centralizada() and get_setor_auditoria_centralizada() in setores

        return quem_solicitou or eh_chefe_do_servidor or pode_por_ser_auditor

    def pode_visualizar_horas_servidor(self, user):
        return self.pode_visualizar(user)

    @staticmethod
    def pode_solicitar(user, retornar_lista_erros=False):
        erros = []

        servidor = user.get_relacionamento()

        perfil_servidor = None
        if servidor.eh_tecnico_administrativo:
            perfil_servidor = ConfiguracaoPerfilServidor.get_vigentes(ConfiguracaoPerfilServidor.PERFIL_TAE)
        elif servidor.eh_docente:
            perfil_servidor = ConfiguracaoPerfilServidor.get_vigentes(ConfiguracaoPerfilServidor.PERFIL_DOCENTE)

        if not SetorHabilitacao.setor_estah_habilitado(servidor.setor):
            if retornar_lista_erros:
                erros.append(f'Sobre o setor do servidor. {get_msg_nenhum_setor_habilitado(sigla_setor=servidor.setor.sigla)}')
            else:
                return False, None

        if not DocumentoAdesaoServidor.get_vigente():
            if retornar_lista_erros:
                erros.append('Os documentos relacionados à Solicitação de Adesão ao PGD ainda não foram cadastrados pela Gestão.')
            else:
                return False, None

        if not perfil_servidor:
            if retornar_lista_erros:
                erros.append('O perfil dos servidores aptos a Solicitar de Adesão ao PGD ainda não foi cadastrado pela Gestão.')
            else:
                return False, None

        # Perfil do servidor
        if not ConfiguracaoPerfilServidor.checa_perfil_servidor(servidor):
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD, o seu cadastro funcional deve ser condizente com as regras do PGD.')
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
                erros.append('Para solicitar adesão ao PGD, você não deve ter Solicitações "Solicitado e aguardando análise".')
            else:
                return False, None

        # Nao pode ter uma adesao vigente
        # Se o servidor estiver em período carência em algum desligamento NÃO IMPEDE DE SOLICITAR NOVA ADESÃO
        if SolicitacaoAdesaoServidor.get_vigentes(user):
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PGD, você não deve ter solicitação vigente.')
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

    def pode_cancelar_servidor(self, user):
        quem_solicitou = self.servidor == user.get_relacionamento()
        return self.situacao == self.SOLICITADO and quem_solicitou

    def pode_cancelar_avaliador(self, user):
        estah_em_comissao_vigente = user.has_group_cached('Comissão Sistêmica PGD 2')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD 2')

        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        eh_chefe_do_servidor = setores.filter(pk=self.servidor.setor_id).exists()

        pode_por_ser_auditor = considerar_auditoria_centralizada() and get_setor_auditoria_centralizada() in setores

        quem_solicitou = self.servidor == user.get_relacionamento()

        return (
            self.situacao == self.SOLICITADO
            and not quem_solicitou
            and (estah_em_comissao_vigente or estah_em_gestao_pgd or eh_chefe_do_servidor or pode_por_ser_auditor)
        )

    def pode_avaliar(self, user):
        if not SetorHabilitacao.setor_estah_habilitado(self.servidor.setor):
            return False

        setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
        eh_chefe_do_servidor = setores.filter(pk=self.servidor.setor_id).exists()
        quem_solicitou = self.servidor == user.get_relacionamento()
        pode_por_ser_auditor = considerar_auditoria_centralizada() and get_setor_auditoria_centralizada() in setores
        return self.situacao == self.SOLICITADO and (eh_chefe_do_servidor or pode_por_ser_auditor) and not quem_solicitou

    def pode_iniciar_cadastro_desligamento(self, user):
        if not SetorHabilitacao.setor_estah_habilitado(self.servidor.setor):
            return False
        pode_cadastrar_desligamento, _ = DesligamentoPgdServidor.pode_iniciar_cadastro(user, self, retornar_lista_erros=False)
        return pode_cadastrar_desligamento

    def pode_editar_telefone_pgd(self, user):
        if not SetorHabilitacao.setor_estah_habilitado(self.servidor.setor):
            return False
        quem_solicitou = self.servidor == user.get_relacionamento()
        return self.situacao in [self.SOLICITADO, self.DEFERIDO] and quem_solicitou and self.estah_vigente

    # -----------------------
    # Servidor X Adesão
    # -----------------------

    # Adesões deferidas
    # -----------------------

    @staticmethod
    def get_adesao_atual_dos_servidores_com_adesao_deferida():
        subquery_adesoes = SolicitacaoAdesaoServidor.get_deferidas().order_by('-data_inicio')[:1]
        return SolicitacaoAdesaoServidor.get_todos_servidores_com_adesao_deferida().prefetch_related(
            Prefetch('solicitacaoadesaoservidor_set', queryset=subquery_adesoes, to_attr='ultima_adesao')
        )

    @property
    def estah_deferida(self):
        # Deferida + Independente de ter desligamento ou nao
        return self.situacao == SolicitacaoAdesaoServidor.DEFERIDO

    @staticmethod
    def get_deferidas(user=None):
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        if user:
            adesoes = adesoes.filter(servidor=user.get_relacionamento())
        return adesoes

    @staticmethod
    def get_servidores_com_adesao_deferida():
        # Utiliza as mesmas regras dos metodos/propriedades
        # - def get_deferidas(self)

        # Pega apenas as adesoes deferidas
        adesoes = SolicitacaoAdesaoServidor.get_deferidas()

        # Servidores com adesao deferida
        ids_servidores = adesoes.values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def get_todos_servidores_com_adesao_deferida():
        # Utiliza as mesmas regras dos metodos/propriedades
        # - def get_deferidas(self)

        # Pega apenas as adesoes deferidas
        adesoes = SolicitacaoAdesaoServidor.get_deferidas()

        # Servidores com adesao deferida
        ids_servidores = adesoes.values_list('servidor_id')

        # Servidores
        return Servidor.objects.filter(id__in=ids_servidores)

    @property
    def estah_vigente(self):
        # Vigente
        # - Deferida
        # - Nao esta desligado efetivamente
        if self.estah_deferida:
            return not self.estah_desligado
        return False

    # Adesões vigentes
    # -----------------------

    @staticmethod
    def get_vigentes(user):
        # Mesma regra do estah_vigente
        sols_adesao_pgd_deferido = SolicitacaoAdesaoServidor.get_deferidas(user).order_by('id')
        sols_adesao_pgd_deferido = sols_adesao_pgd_deferido.select_related('servidor').defer('documento_adesao')
        ids = []
        for sol_adesao_pgd in sols_adesao_pgd_deferido:
            if sol_adesao_pgd.estah_vigente:
                ids.append(sol_adesao_pgd.id)
        if ids:
            return SolicitacaoAdesaoServidor.objects.filter(id__in=ids).order_by('id')
        return None

    @staticmethod
    def tem_adesao_vigente(user):
        return bool(SolicitacaoAdesaoServidor.get_vigentes(user))

    @staticmethod
    def get_adesoes_vigentes(user=None):
        # Utiliza as mesmas regras de
        # - def estah_vigente(self)

        # Pega as adesoes vigentes
        adesoes = SolicitacaoAdesaoServidor.get_deferidas(user=user)
        ids_adesoes_vigentes = []
        for adesao in adesoes:
            if adesao.estah_vigente:
                ids_adesoes_vigentes.append(adesao.id)

        # Adesoes
        return SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_vigentes)

    @staticmethod
    def get_servidores_com_adesao_vigente():
        ids_servidores = SolicitacaoAdesaoServidor.get_adesoes_vigentes().values_list('servidor_id')
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @property
    def estah_vigente_ou_desligado_na_carencia(self):
        # Se está deferido sem desligamento (médodo "estah_vigente")
        # OU
        # Se esta deferido com desligamento na carência

        if self.estah_vigente:
            return True
        return bool(self.estah_deferida and self.estah_desligado_mas_ainda_na_carencia)

    @staticmethod
    def get_vigentes_ou_desligado_na_carencia(user=None):
        # Utiliza as mesmas regras de
        # - def estah_vigente_ou_desligado_na_carencia(self)

        # Pega as adesoes vigentes e na carencia
        adesoes = SolicitacaoAdesaoServidor.objects.filter(situacao=SolicitacaoAdesaoServidor.DEFERIDO)
        if user:
            adesoes = adesoes.filter(servidor=user.get_relacionamento())

        ids = []
        for adesao in adesoes:
            if adesao.estah_vigente_ou_desligado_na_carencia:
                ids.append(adesao.id)

        return SolicitacaoAdesaoServidor.objects.filter(id__in=ids)

    @staticmethod
    def get_servidores_com_adesao_vigente_e_na_carencia():
        # Utiliza get_vigentes_ou_desligado_na_carencia

        # Pega servidores com adesoes vigentes ou desligadio na carencia
        ids_servidores = SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia().values_list('servidor_id')

        # Servidores
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    def get_data_inicio_adesao(self):
        return self.data_inicio

    def primeiro_dia_pgd_nessa_adesao(self, considera_inicio_adesao=False):
        # Primeiro dia de trabalho no PGD nessa adesão
        data_inicio = self.get_data_inicio_adesao() if considera_inicio_adesao else None
        primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_homologado_adesao(self)
        if primeiro_pit_adesao:
            data_inicio = primeiro_pit_adesao.data_inicio
        return data_inicio

    def ultimo_dia_pgd_nessa_adesao(self):
        df = get_datetime_now().date()
        if self.tem_desligamento_cadastrado:
            df = self.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)
        return df

    def get_data_final_adesao(self):
        if self.tem_desligamento_cadastrado:
            if self.data_desligamento_efeitos_a_partir_de != self.get_data_inicio_adesao():
                return self.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)
            return self.data_desligamento_efeitos_a_partir_de
        return None

    @staticmethod
    def estah_no_pgd_hoje(servidor, data=None):
        # Diz se o servidor está no PGD HOJE
        data = data or get_datetime_now().date()
        adesoes = SolicitacaoAdesaoServidor.get_adesoes_em_pgd(servidor.get_user())  # get_adesoes_vigentes
        if adesoes:
            for adesao in adesoes:
                data_inicio = adesao.primeiro_dia_pgd_nessa_adesao()
                data_final = adesao.ultimo_dia_pgd_nessa_adesao()
                if data_inicio and data_final and (data >= data_inicio and data <= data_final):
                    return True, adesao
        return False, None

    @staticmethod
    def periodos_estah_no_pgd(servidor):
        # - Deve ser utilizado apenas pelo ponto no relatório de frequencia
        periodos = []
        adesoes = SolicitacaoAdesaoServidor.get_adesoes_em_pgd(servidor.get_user())  # get_adesoes_vigentes
        if adesoes:
            for adesao in adesoes:
                data_inicio = adesao.primeiro_dia_pgd_nessa_adesao()
                data_final = adesao.ultimo_dia_pgd_nessa_adesao()
                if data_inicio and data_final:
                    periodos.append((data_inicio, data_final))
        return periodos

    # EM PGD
    # - Adesao vigente com PIT homologado
    # -----------------------

    @staticmethod
    def get_adesoes_em_pgd(user=None):
        # Adesoes
        # - Vigente E com um PIT homologado
        adesoes_vigentes = SolicitacaoAdesaoServidor.get_adesoes_vigentes(user=user)

        ids_adesoes_com_pit_homologado = PlanoIndividualTrabalho.get_adesoes_pgd_com_registros_homologacao_pit().values_list('id')
        return adesoes_vigentes.filter(id__in=ids_adesoes_com_pit_homologado)

    @staticmethod
    def get_servidores_em_pgd():
        # Servidores comforme dados do SUAP
        # - Adesão vigente E com um PIT homologado
        ids_servidores = SolicitacaoAdesaoServidor.get_adesoes_em_pgd().values_list('servidor_id')
        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def get_servidores_em_pgd_exterior():
        servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()

        # Pelo afastamento (ServidorAfastamento)
        afastamentos_pgd_exterior = get_afastamentos_exterior()
        ids_servidores_em_exterior = list(
            ServidorAfastamento.objects.filter(afastamento__in=afastamentos_pgd_exterior, cancelado=False).values_list('servidor_id', flat=True)
        )
        # OU pelo cadastro manual (PGDExterior)
        ids_servidores_em_exterio2 = list(PGDExterior.get_vigentes().values_list('servidor_id', flat=True))
        ids_servidores_em_exterior.extend(ids_servidores_em_exterio2)
        servidores_em_pgd = servidores_em_pgd.filter(id__in=ids_servidores_em_exterior)

        # E pelo cadastro no SOU GOV / SIAPE
        servidores_em_pgd = servidores_em_pgd.annotate(modalidade_pgd_nome_upper=Upper('modalidade_pgd__nome'))
        servidores_em_pgd = servidores_em_pgd.filter(modalidade_pgd_nome_upper='NO EXTERIOR')

        return servidores_em_pgd

    @staticmethod
    def get_dados_servidores_em_pgd_exterior(servidor):
        # Pelo afastamento (ServidorAfastamento)
        afastamentos_pgd_exterior = get_afastamentos_exterior()
        afastamentos_pgd_exterior_servidor = ServidorAfastamento.objects.filter(
            servidor=servidor, afastamento__in=afastamentos_pgd_exterior, cancelado=False
        )

        # Pelo cadastro manual
        cadastro_pgd_exterior_servidor = PGDExterior.objects.filter(servidor=servidor)

        return afastamentos_pgd_exterior_servidor, cadastro_pgd_exterior_servidor

    @staticmethod
    def get_periodo_servidor_em_pgd_exterior(servidor):
        servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd_exterior()
        if servidores_em_pgd.filter(id=servidor.id).exists():
            afastamentos_pgd_exterior = get_afastamentos_exterior()
            exterior = ServidorAfastamento.objects.filter(servidor=servidor, afastamento__in=afastamentos_pgd_exterior, cancelado=False).first()
            if exterior:
                return exterior.data_inicio, exterior.data_termino
            exterior = PGDExterior.get_vigentes().filter(servidor=servidor).first()
            if exterior:
                return exterior.data_inicio, exterior.data_fim
        return None, None

    @staticmethod
    def get_servidores_inativos_em_pgd():
        # Mesmo que get_servidores_em_pgd mas filtra os servidores inativos
        ids_servidores = SolicitacaoAdesaoServidor.get_adesoes_em_pgd().values_list('servidor_id')
        return Servidor.objects.filter(ativo=False, id__in=ids_servidores)

    @staticmethod
    def get_servidores_inativos_com_adesao_vigente():
        ids_servidores = SolicitacaoAdesaoServidor.get_adesoes_vigentes().values_list('servidor_id')
        return Servidor.objects.filter(ativo=False, id__in=ids_servidores)

    # -----------------------
    # Desligamento
    # -----------------------

    @property
    def tem_desligamento_cadastrado(self):
        return bool(self.data_desligamento_efeitos_a_partir_de)

    def get_data_efeitos_desligamento_pgd(self):
        if self.tem_desligamento_cadastrado:
            return self.data_desligamento_efeitos_a_partir_de
        return None

    @property
    def estah_desligado(self):
        # Estah desligado se a adesao
        # - Estiver Deferida
        # - Tem desligamento cadastrado
        # - Esta desligado efetivamente quando a partir da
        #   "data_desligamento_efeitos_a_partir_de" (NAO CONSIDERA CARENCIA)
        #   - Se a data "data_desligamento_efeitos_a_partir_de" eh 10/12/2022 entao no dia 10/12/2022 o servidor ja esta desligado
        #     oficialmente.
        #   - NAO CONSIDERA CARENCIA
        if self.estah_deferida:
            if self.tem_desligamento_cadastrado and (get_datetime_now().date() >= self.data_desligamento_efeitos_a_partir_de):
                # Se estah desligado
                return True
        return False

    @property
    def estah_desligado_mas_ainda_na_carencia(self):
        # Se esta DESLIGADO efetivamete mas AINDA ESTA NO PERIODO DE CARENCIA
        if self.estah_desligado:
            if self.data_desligamento_carencia_ate:
                return get_datetime_now().date() <= self.data_desligamento_carencia_ate
            return False
        return False

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
            # carencia_ate = (self.data_desligamento_efeitos_a_partir_de + relativedelta(days=PlanoIndividualTrabalho.CARENCIA_PARA_EDICAO_PIT_SEM_ADESAO_VIGENTE))
            # return carencia_ate
        return False

    """
    @staticmethod
    def get_adesoes_desligados_com_pit_homologado():
        # Para todos os servidores que já tiverama desao dferida
        # - Considera a situcao atual (ultima adesao do servidor)
        # Ultima adesao deve estar desligada e deve ter tido pit homologado
        ids_servidores = SolicitacaoAdesaoServidor.get_deferidas().values_list('servidor_id')
        ids_servidores = []
        for adesao in adesoes:
            if adesao.estah_desligado:
                ids_servidores.append(adesao.servidor.id)
        adesoes = adesoes.filter(id__in=PlanoIndividualTrabalho.get_adesoes_pgd_com_registros_homologacao_pit().values_list('id'))

        return adesoes
    """

    @staticmethod
    def get_servidores_com_desligamento():
        # Ciom adesão deferida e desligamento cadastrad
        adesoes = SolicitacaoAdesaoServidor.get_deferidas()
        ids_servidores = []
        for adesao in adesoes:
            if adesao.estah_desligado:
                ids_servidores.append(adesao.servidor.id)

        return Servidor.objects.vinculados().filter(id__in=ids_servidores)

    @staticmethod
    def get_servidores_desligados():
        # Servidores que estavam em PGD mas já estão desligados
        ids_servidores = []
        servidores_com_adesao_deferida = SolicitacaoAdesaoServidor.get_todos_servidores_com_adesao_deferida()
        for servidor in servidores_com_adesao_deferida:
            ultima_adesao = SolicitacaoAdesaoServidor.get_deferidas().filter(servidor=servidor).order_by('-data_inicio').first()
            if ultima_adesao and ultima_adesao.estah_desligado:
                ids_servidores.append(servidor.id)
        return servidores_com_adesao_deferida.filter(id__in=ids_servidores)

    # -----------------------
    # API
    # -----------------------

    @staticmethod
    def get_situacao_desligamento_atual_para_api(servidor):
        adesoes = SolicitacaoAdesaoServidor.objects.filter(servidor=servidor, situacao=SolicitacaoAdesaoServidor.DEFERIDO).order_by('-id')
        for adesao in adesoes:
            primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_homologado_adesao(adesao)
            if primeiro_pit_adesao:
                data_cadastro_desligamento = None
                if adesao.estah_desligado:
                    r = RegistroAcaoSolicitacaoAdesaoServidor.objects.filter(
                        solicitacao=adesao, tipo=RegistroAcaoSolicitacaoAdesaoServidor.TIPO_DESLIGAMENTO
                    ).order_by('-id')
                    if r:
                        data_cadastro_desligamento = r.last().data
                    return True, data_cadastro_desligamento
        return None, None


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

    user = models.CurrentUserField(editable=False, related_name='raadesaopgd_pgd2')
    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    solicitacao = models.ForeignKeyPlus('pgd2.SolicitacaoAdesaoServidor', editable=False, null=True, related_name='raadesaopgd_solicitacao_pgd2')


class DesligamentoPgdServidor(models.ModelPlus):
    # Solicitacoes de desligamento do PGD

    adesao = models.ForeignKeyPlus('pgd2.SolicitacaoAdesaoServidor', verbose_name='Adesão', related_name='adesao_desligamento_pgd2')
    justificativa = models.ForeignKeyPlus(
        'pgd2.JustificativaDesligamentoPgd', verbose_name='Justificativa', related_name='justificativa_soladesao_pgd2'
    )
    observacao = models.TextField('Observações')

    data_desligamento_efeitos_a_partir_de = models.DateFieldPlus('Desligamento com efeitos a partir de', null=True)
    data_pode_solicitar_nova_adesao = models.DateFieldPlus('A partir desta data já pode solicitar nova adesão', null=True)

    data_cadastro = models.DateTimeFieldPlus('Data do cadastro', auto_now_add=True, editable=False)
    usuario_cadastro = models.CurrentUserField(editable=False, related_name='desligamento_usuario_cadastro_pgd2')

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
        if eh_chefe_do_servidor:
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
        # Utilizado para SERVIDOR e CHEFES
        # User: quem esta cadastrando o Desligamento
        # adesao.servidor: Adesao do Servidor que sera Desligado

        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(adesao.servidor.setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=adesao.servidor.setor.sigla))
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
                erros.append('A adesão precisa estar vigente.')
            else:
                return False, None

        # Nao pode cadastrar se tiver outra cadastrada
        # - Nao pode se tiver outra cadastrada sem ter desligamento
        if DesligamentoPgdServidor.objects.filter(adesao=adesao, data_cancelamento__isnull=True).exists():
            if retornar_lista_erros:
                erros.append('Não é possível cadastrar mais de um desligamento ativo para uma mesma adesão ao PGD.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_cadastrar(user, adesao, retornar_lista_erros=False, data_desligamento_efeitos_a_partir_de=None):
        # Utilizado pelo SERVIDOR e CHEFE
        # User: quem esta cadastrando o Desligamento
        # adesao.servidor: Adesao do Servidor que sera Desligado

        erros = []

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
            if not (data_desligamento_efeitos_a_partir_de >= adesao.get_data_inicio_adesao()):
                if retornar_lista_erros:
                    erros.append('Impossível cadastrar Desligamento com data de efeitos para uma data igual ou antes do início da adesão.')
                else:
                    return False, None

            # Qualquer RIT que finalize no dia ou após a data de efeito
            # - nao pode estar homologado no momento do cadastro de desligamento
            # - nao pode estar com solicitacao de adesao em aberto
            rits = PlanoIndividualTrabalho.get_rits(adesao)
            rits = rits.filter(
                Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT) | Q(situacao_rit=PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT)
            )
            if rits:
                for rit in rits:
                    if rit.data_fim >= data_desligamento_efeitos_a_partir_de:
                        if retornar_lista_erros:
                            erros.append(
                                f'Impossível cadastrar Desligamento caso exista algum {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} Homologado ou que tenha Solicitado Homologação e que finalize no dia ou após a data de efeito.'
                            )
                            break
                        else:
                            return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def gestao_pode_cadastrar(user, adesao, retornar_lista_erros=False, data_desligamento_efeitos_a_partir_de=None):
        # utilizado apenas pela gestão

        erros = []

        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD 2')
        if not estah_em_gestao_pgd:
            if retornar_lista_erros:
                erros.append('Usuário deve ser da gestão do PGD.')
            else:
                return False, None

        # A adesao tem que estar vigente
        if not adesao.estah_vigente:
            if retornar_lista_erros:
                erros.append('A adesão precisa estar vigente.')
            else:
                return False, None

        # Nao pode cadastrar se tiver outra cadastrada
        # - Nao pode se tiver outra cadastrada sem ter desligamento
        if DesligamentoPgdServidor.objects.filter(adesao=adesao, data_cancelamento__isnull=True).exists():
            if retornar_lista_erros:
                erros.append('Não é possível cadastrar mais de um desligamento ativo para uma mesma adesão ao PGD.')
            else:
                return False, None

        # Validacoes (data de efeito) se pode finalizar um cadastro já iniciado
        # -------------------------------------
        if data_desligamento_efeitos_a_partir_de:
            # Deve ser igual ou posterior a data desta adesao
            if not (data_desligamento_efeitos_a_partir_de >= adesao.get_data_inicio_adesao()):
                if retornar_lista_erros:
                    erros.append('Impossível cadastrar Desligamento com data de efeitos para uma data igual ou antes do início da adesão.')
                else:
                    return False, None

            # Qualquer RIT que finalize no dia ou após a data de efeito
            # - nao pode estar homologado no momento do cadastro de desligamento
            # - nao pode estar com solicitacao de adesao em aberto
            rits = PlanoIndividualTrabalho.get_rits(adesao)
            rits = rits.filter(
                Q(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT) | Q(situacao_rit=PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT)
            )
            if rits:
                for rit in rits:
                    if rit.data_fim >= data_desligamento_efeitos_a_partir_de:
                        if retornar_lista_erros:
                            erros.append(
                                f'Impossível cadastrar Desligamento caso exista algum {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} Homologado ou que tenha Solicitado Homologação e que finalize no dia ou após a data de efeito.'
                            )
                            break
                        else:
                            return False, None

        if erros:
            return False, erros

        return True, None

    def pode_visualizar(self, user):
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        eh_chefe_setor_do_servidor_da_adesao = setores_que_sou_chefe_hoje(user.get_relacionamento()).filter(pk=self.adesao.servidor.setor_id).exists()
        return quem_solicitou or eh_chefe_setor_do_servidor_da_adesao

    def pode_cancelar(self, user=None):
        if not SetorHabilitacao.setor_estah_habilitado(self.adesao.servidor.setor):
            return False

        if self.data_cancelamento:
            return False

        if not (self.data_desligamento_efeitos_a_partir_de and (get_datetime_now().date() < self.data_desligamento_efeitos_a_partir_de)):
            return False

        if user:
            # Validacoes basicas E
            # O servidor nao pode descancelar seu proprio desligamento
            user_pode, _ = DesligamentoPgdServidor.user_pode_cadastrar(user, self.adesao, retornar_lista_erros=False)
            return bool(user_pode and self.adesao.servidor != user.get_relacionamento())
        return True


class PGDExterior(models.ModelPlus):
    # Cadastro de PGD Exterior (novo -- substitui os afastamentos)
    # - Etapa de Cadastro: realizado por tem_permissao_cadastrar_alterar
    # - Etapa de Confirmação: realizado por tem_permissao_informar_portaria

    # Etapa de Cadastro
    servidor = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor')
    processo = models.ForeignKeyPlus('processo_eletronico.Processo', verbose_name='Processo Eletrônico PGD Exterior')
    HIPOTESE_LEGAL_ART_12_VIII = 1
    HIPOTESE_LEGAL_ART_12_P7 = 2
    HIPOTESE_LEGAL_CHOICES = [
        [HIPOTESE_LEGAL_ART_12_VIII, 'Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)'],
        [HIPOTESE_LEGAL_ART_12_P7, 'Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)'],
    ]
    hipotese_legal = models.PositiveIntegerField('Hipótese legal', choices=HIPOTESE_LEGAL_CHOICES)
    data_inicio = models.DateFieldPlus(verbose_name='Data Inicial')
    data_fim = models.DateFieldPlus(verbose_name='Data Final')
    cancelado = models.BooleanField('Cancelado', default=False)

    # Etapa de Confirmação
    documento_eletronico = models.ForeignKeyPlus(
        'documento_eletronico.DocumentoTexto', verbose_name='Documento Eletrônico PGD Exterior', null=True, blank=True
    )
    data_hora_criacao = models.DateTimeFieldPlus(verbose_name='Data de Criação', auto_now_add=True, editable=False)
    ultima_modificacao = models.DateTimeField(verbose_name='Data de Alteração', auto_now=True, editable=False)

    class Meta:
        verbose_name = 'PGD Exterior'
        verbose_name_plural = 'PGD Exterior'

    def __str__(self):
        return str(self.servidor)

    @admin.display(boolean=True)
    def estah_vigente(self):
        if not self.cancelado and self.documento_eletronico:
            hoje = datetime.date.today()
            return self.data_inicio <= hoje <= self.data_fim
        return False

    estah_vigente.short_description = 'Está vigente'

    @staticmethod
    def get_vigentes():
        hoje = datetime.date.today()
        return PGDExterior.objects.filter(documento_eletronico__isnull=False, data_inicio__lte=hoje, data_fim__gte=hoje, cancelado=False)

    @staticmethod
    def tem_permissao_cadastrar_alterar(user):
        return user.has_group_cached('Gestor do PGD 2')

    @staticmethod
    def tem_permissao_informar_portaria(user):
        return user.has_group_cached('Coordenador de Gestão de Pessoas') or user.has_group_cached('Coordenador de Gestão de Pessoas Sistêmico')


# ====================================================
# Adesão PES
# ====================================================


class SolicitacaoAdesaoPesServidor(models.ModelPlus):
    adesao = models.ForeignKeyPlus('pgd2.SolicitacaoAdesaoServidor', verbose_name='Adesão')
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', related_name='setor_sapes_pgd2')
    documento_adesao = models.ForeignKeyPlus('pgd2.DocumentoAdesaoPesServidor', verbose_name='Servidor', null=True)

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
        verbose_name = 'Adesão do Servidor ao PES'
        verbose_name_plural = 'Adesões do Servidor a um PES'

    def __str__(self):
        if self.situacao == self.DEFERIDO:
            return f'Adesão do Servidor {self.adesao.servidor} ao PES do setor {self.setor}'
        return f'Solicitação de Adesão do Servidor {self.adesao.servidor} ao PES do setor {self.setor}'

    @staticmethod
    def estah_no_pes_no_periodo(servidor, data_final):
        # Diz se o servidor está no PES em um determinado periodo
        adesoes = SolicitacaoAdesaoPesServidor.objects.filter(adesao__servidor=servidor, situacao=SolicitacaoAdesaoPesServidor.DEFERIDO)
        for adesao in adesoes:
            data_inicio_adesao = adesao.get_data_situacao_atual()
            data_final_adesao = None
            if adesao.data_desligamento:
                data_final_adesao = adesao.data_desligamento
            #
            if (data_inicio_adesao and not data_final_adesao) and (data_inicio_adesao.date() <= data_final):
                return True
            if (data_final_adesao) and (data_final_adesao <= data_final):
                return True
        return False

    @property
    def estah_desligado(self):
        # Estah desligado
        # - Solicitacao estah deferida
        # - Existe cadastro de desligamento para a solicitacao
        # - Se a data de hoje for >= a data_desligamento
        if self.situacao == self.DEFERIDO:
            return bool(self.data_desligamento)
        return False

    @staticmethod
    def get_deferidas(adesao_pgd):
        # Retorna as adesões Deferidas
        # - Que foi solicitada pelo servidor e foi deferida
        return SolicitacaoAdesaoPesServidor.objects.filter(adesao=adesao_pgd, situacao=SolicitacaoAdesaoPesServidor.DEFERIDO)

    @staticmethod
    def get_vigentes(adesao_pgd):
        # Retorna as adesões Vigentes
        # - Deferidas
        # - Que que ainda nao esta desligado
        deferidas = SolicitacaoAdesaoPesServidor.get_deferidas(adesao_pgd)
        if deferidas:
            return deferidas.filter(data_desligamento__isnull=True)
        return SolicitacaoAdesaoPesServidor.objects.none()

    @staticmethod
    def existe_adesao_deferida_para_o_servidor(servidor):
        # Se existe alguma adesão PES vigente
        return SolicitacaoAdesaoPesServidor.objects.filter(adesao__servidor=servidor, situacao=SolicitacaoAdesaoPesServidor.DEFERIDO)

    def esta_vigente(self):
        # Esta vigente se
        # - Esta Deferida
        # - Nao tem data de desligamento
        if self.situacao == self.DEFERIDO:
            return not self.data_desligamento
        return None

    def get_data_situacao_atual(self):
        if self.situacao:
            r = RegistroAcaoSolicitacaoAdesaoPesServidor.objects.filter(solicitacao=self).order_by('-id')
            if r:
                return r.last().data
        return None

    get_data_situacao_atual.short_description = 'Data/Hora da Situação Atual'

    @staticmethod
    def pode_visualizar_lista(user):
        # lista do admin
        return bool(user.has_perm('rh.chefe'))

    def pode_visualizar(self, user):
        # visualiar uma solicitacao especifica
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        eh_chefe_setor_plano_trabalho_setorial = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        return quem_solicitou or eh_chefe_setor_plano_trabalho_setorial

    @staticmethod
    def pode_iniciar_solicitacao(user, retornar_lista_erros=False):
        # Setor: setor que deseja aderir
        erros = []

        # servidor = user.get_relacionamento()

        documento_vigente = DocumentoAdesaoPesServidor.get_vigente()
        if not documento_vigente:
            if retornar_lista_erros:
                erros.append('A gestão deve cadastrar o Documento de Regras relacionadas à Adesão do Servidor a um PES.')
            else:
                return False, None

        # Tem que ter alguma solicitação vigente (se for desligado precisa ta na carencia)
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia(user)
        if not adesoes_pgd:
            if retornar_lista_erros:
                erros.append(
                    'Para solicitar adesão ao PES você deve ter, no mínimo, uma adesão vigente ao PGD. Se houver desligamento para adesão selecionada é necessário ainda estar na carência.'
                )
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_solicitar(user, setor, adesao_pgd, retornar_lista_erros=False):
        # Setor: setor que deseja aderir
        erros = []

        servidor = user.get_relacionamento()

        if not SetorHabilitacao.setor_estah_habilitado(setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=setor.sigla))
            else:
                return False, None

        documento_vigente = DocumentoAdesaoPesServidor.get_vigente()
        if not documento_vigente:
            if retornar_lista_erros:
                erros.append('A gestão deve cadastrar o Documento de Regras relacionadas à Adesão do Servidor a um PES.')
            else:
                return False, None

        # Tem que ter alguma solicitação vigente (se for desligado precisa ta na carencia)
        adesoes_pgd = SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia(user)
        if not adesoes_pgd:
            if retornar_lista_erros:
                erros.append(
                    'Para solicitar adesão ao PES você deve ter, no mínimo, uma adesão vigente ao PGD. Se houver desligamento para adesão selecionada é necessário ainda estar na carência.'
                )
            else:
                return False, None

        if adesao_pgd and not adesao_pgd.estah_vigente_ou_desligado_na_carencia:
            if retornar_lista_erros:
                erros.append(
                    'Para solicitar adesão ao PES você deve selecionar uma adesão vigente ao PGD. Se houver desligamento para adesão selecionada é necessário ainda estar na carência.'
                )
            else:
                return False, None

        # Se considerar auditoria centralizada
        if considerar_auditoria_centralizada() and servidor_eh_auditor(servidor) and not setor_eh_auditoria_centralizada(setor):
            if retornar_lista_erros:
                erros.append('Servidor Auditor só pode aderir ao PES da Auditoria Geral')
            else:
                return False, None

        # Retirado para permitir aderir a PES mesmo que ele não esteja vigente (apto)
        """
        # O setor deve ter um PES apto hoje -- servidor deve concordar com o PES atual
        pts_apto = PlanoEntregasSetorial.existe_algum_pes_apto(setor)
        if not pts_apto:
            if retornar_lista_erros:
                erros.append('Para solicitar adesão ao PES o Setor deve ter um PES aprovado e com período atual.')
            else:
                return False, None
        """

        # O setor deve ter ao menos um PES aprovado
        if not PlanoEntregasSetorial.get_pess_aprovados(setor=setor).exists():
            if retornar_lista_erros:
                erros.append('O setor não possui um PES aprovado.')
            else:
                return False, None

        # O setor precisa ter algum PES aprovado dentro do período da adesão selecionada
        if adesao_pgd:
            if (
                not PlanoEntregasSetorial.existe_algum_pes_apto(setor)
                and not PlanoEntregasSetorial.get_pes_apto_a_partir_de(setor=setor, data_inicio=adesao_pgd.get_data_inicio_adesao()).exists()
            ):
                if retornar_lista_erros:
                    erros.append('Setor precisa ter algum PES aprovado considerando a adesão PGD selecionada')
                else:
                    return False, None

        # Se tiver solicitando adesao a um SETOR que já tenha adesão -- considerando a adesao passada como parametro
        if adesao_pgd:
            adesoes_pes_vigentes_para_o_setor = SolicitacaoAdesaoPesServidor.get_vigentes(adesao_pgd).filter(setor=setor)
            solicitacoes_de_adesao_pes_para_o_setor = SolicitacaoAdesaoPesServidor.objects.filter(
                setor=setor, adesao=adesao_pgd, situacao__in=[SolicitacaoAdesaoPesServidor.SOLICITADO]
            )
            if adesoes_pes_vigentes_para_o_setor or solicitacoes_de_adesao_pes_para_o_setor:
                if retornar_lista_erros:
                    erros.append('Já existe uma adesão vigente ou solicitada para o setor .')
                else:
                    return False, None

        # Se o setor que ele deseja aderir for diferente do dele ele só pode aderir se tiver aderido do dele
        # - Para aderir a um PES de outro setor (setor diferente do setor SUAP do servidor)
        #   ele deve ter adesão ao setor suap dele
        if not considerar_auditoria_centralizada() and adesao_pgd:
            adesoes_pes_vigentes = SolicitacaoAdesaoPesServidor.get_vigentes(adesao_pgd)
            if adesoes_pes_vigentes and setor != servidor.setor:
                if not (adesoes_pes_vigentes.filter(setor=servidor.setor).exists()):
                    if retornar_lista_erros:
                        erros.append('Para solicitar adesão a um PES de outro setor é necessário que já tenha aderido ao PES do seu setor.')
                    else:
                        return False, None

        if erros:
            return False, erros

        return True, None

    def pode_cancelar_servidor(self, user):
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        return self.situacao == self.SOLICITADO and quem_solicitou

    def pode_cancelar_avaliador(self, user):
        estah_em_comissao_vigente = user.has_group_cached('Comissão Sistêmica PGD 2')
        estah_em_gestao_pgd = user.has_group_cached('Gestor do PGD 2')
        eh_chefe_setor_plano_trabalho_setorial = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        return (
            self.situacao == self.SOLICITADO
            and not quem_solicitou
            and (estah_em_comissao_vigente or estah_em_gestao_pgd or eh_chefe_setor_plano_trabalho_setorial)
        )

    def pode_avaliar(self, user):
        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            return False

        eh_chefe_setor_plano_trabalho_setorial = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        return self.situacao == self.SOLICITADO and not quem_solicitou and eh_chefe_setor_plano_trabalho_setorial

    def pode_cadastrar_desligamento_servidor(self, user):
        # Servidor ou Chefe podem cadastrar
        # ------------------------
        # Regras basicas
        # ------------------------
        # Se eh servidor da adesão ou chefe do setor do referido PES

        if not SetorHabilitacao.setor_estah_habilitado(self.setor):
            return False

        eh_chefe_setor_plano_trabalho_setorial = self.setor in setores_que_sou_chefe_hoje(user.get_relacionamento())
        quem_solicitou = self.adesao.servidor == user.get_relacionamento()
        user_pode = eh_chefe_setor_plano_trabalho_setorial or quem_solicitou
        #
        pode_pela_situacao = self.situacao == self.DEFERIDO
        #
        regras_basicas = (user_pode) and (pode_pela_situacao) and (not self.estah_desligado)
        if not regras_basicas:
            return False

        # ------------------------
        # Outras regras
        # ------------------------
        # Não pode se desligar de PES que possui PIT relacionado que não esteja homologado
        existem_pits_nao_homologados = (
            PlanoIndividualTrabalho.get_pits_por_setor(self.setor)
            .exclude(situacao=PlanoIndividualTrabalho.HOMOLOGADO)
            .filter(adesao__servidor=self.adesao.servidor)
            .exists()
        )
        if existem_pits_nao_homologados:
            return False

        # Se o servidor esta desligado da adesao PGD relacionada ele pode cadastrar desligamento APENAS SE TIVER NA CARENCIA
        # - Se tiver desligado fora da carencia nao pode
        if self.adesao.estah_desligado and self.adesao.estah_desligado_mas_fora_da_carencia:
            return False

        # Nao pode para o setor dele
        return self.adesao.servidor.setor != self.setor

    @staticmethod
    def get_solicitacoes_pendendentes_avaliacao_chefe_direto(user):
        setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
        if not setores:
            return SolicitacaoAdesaoPesServidor.objects.none()
        return SolicitacaoAdesaoPesServidor.objects.filter(setor__in=setores, situacao=SolicitacaoAdesaoPesServidor.SOLICITADO)

    def get_solicitacoes_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True):
        # Deve considerar
        # - Solicitações que o chefe DEVE aprovar
        # - Solicitações que o chefe PODE aprovar

        setores = []
        servidores = []
        setores_hoje = []
        servidores_exclude = []
        if apenas_chefe_direto:
            # ----------------------------------------------
            # Que o chefe DEVE aprovar/homologar
            # Considera apenas os setores e servidores que é chefe direto
            # ----------------------------------------------
            # Setores que é chefe direto. Exemplo: DIGPE
            setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Chefes dos subsetores da DIGPE. Exemplo: Chefe CODEPE, Chefe CODEPE, Chefe COGCAP, Chefe COADPE e Chefe COASS
            servidores = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Todos os subsetores da DIGPE
            setores_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        else:
            # ----------------------------------------------
            # Que o chefe PODE aprovar/homologar
            # Considera os setores descendentes e exclui setores que é chefe direto
            # ----------------------------------------------
            # Todos os setores que é chefe incluindo a DIGPE e seus Subsetores
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            # Setores que é chefe direto. Exemplo: DIGPE
            setores_chefe_direto = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Exclui a DIGPE
            setores = setores.exclude(id__in=setores_chefe_direto.values('id'))
            # Excluir do PODE os servidores do DEVE
            servidores_exclude = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())

        if not setores:
            return SolicitacaoAdesaoPesServidor.objects.none()

        solicitacoes = SolicitacaoAdesaoPesServidor.objects.filter(situacao=SolicitacaoAdesaoPesServidor.SOLICITADO).exclude(
            adesao__servidor=user.get_relacionamento()
        )

        querys = []

        querys.append(Q(setor__in=setores))
        if servidores and setores_hoje:
            querys.append(Q(adesao__servidor__in=servidores) & Q(setor__in=setores_hoje))

        solicitacoes = solicitacoes.filter(reduce(operator.or_, querys))
        if servidores_exclude:
            solicitacoes = solicitacoes.exclude(adesao__servidor__in=servidores_exclude)

        return solicitacoes


class RegistroAcaoSolicitacaoAdesaoPesServidor(RegistroAcaoPGD):
    TIPO_SOLICITADO = SolicitacaoAdesaoPesServidor.SOLICITADO
    TIPO_CANCELADO_PELO_SERVIDOR = SolicitacaoAdesaoPesServidor.CANCELADO_PELO_SERVIDOR
    TIPO_CANCELADO_PELO_AVALIADOR = SolicitacaoAdesaoPesServidor.CANCELADO_PELO_AVALIADOR
    TIPO_DEFERIDO = SolicitacaoAdesaoPesServidor.DEFERIDO
    TIPO_INDEFERIDO = SolicitacaoAdesaoPesServidor.INDEFERIDO
    TIPO_DESLIGAMENTO = 6

    TIPO_CHOICES = (
        (TIPO_SOLICITADO, SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_SOLICITADO - 1][1]),
        (TIPO_CANCELADO_PELO_SERVIDOR, SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_SERVIDOR - 1][1]),
        (TIPO_CANCELADO_PELO_AVALIADOR, SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_CANCELADO_PELO_AVALIADOR - 1][1]),
        (TIPO_DEFERIDO, SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_DEFERIDO - 1][1]),
        (TIPO_INDEFERIDO, SolicitacaoAdesaoPesServidor.SITUACAO_SOLICITACAO_ADESAO_CHOICES[TIPO_INDEFERIDO - 1][1]),
        (TIPO_DESLIGAMENTO, 'Desligamento do PES'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    solicitacao = models.ForeignKeyPlus('pgd2.SolicitacaoAdesaoPesServidor', editable=False, null=True)
    user = models.CurrentUserField(editable=False, related_name='raadesaopes_pgd2')


# ====================================================
# PIT
# ====================================================


class PlanoIndividualTrabalho(models.ModelPlus):
    # Qtd de dias adicionais (após a data de efeitos do desligamento) que o servidor tem para executar algumas peracoes com seu POT/RIT
    CARENCIA_PARA_EDICAO_PIT_SEM_ADESAO_VIGENTE = 365

    # ---------------------------
    # Dados PIT
    # ---------------------------
    adesao = models.ForeignKeyPlus('pgd2.SolicitacaoAdesaoServidor', verbose_name='Adesão do Servidor', editable=False)

    periodo_pit_rit = models.ForeignKeyPlus('pgd2.PeriodoPitRit', verbose_name=f'Período {nomenclatura.pit_rit_pgd2}', editable=False)
    data_inicio = models.DateFieldPlus(verbose_name='Data Início', null=True, blank=True)
    data_fim = models.DateFieldPlus(verbose_name='Data Final', null=True, blank=True)

    EM_CADASTRO = 1
    AGUARDANDO_PARECER = 2
    CANCELADO = 3
    HOMOLOGADO = 4
    SITUACAO_PIT_CHOICES = [
        [EM_CADASTRO, 'Em Fase de Cadastro'],
        [AGUARDANDO_PARECER, 'Aguardando parecer'],
        [CANCELADO, 'Cancelado'],
        [HOMOLOGADO, 'Homologado'],
    ]
    SITUACOES_PODE_CALCULAR_PIT = [EM_CADASTRO, HOMOLOGADO]
    SITUACOES_PLANEJAMENTO_CADASTRADO_PIT = [EM_CADASTRO, AGUARDANDO_PARECER]
    situacao = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_PIT_CHOICES, default=EM_CADASTRO)

    TRABALHO_TELETRABALHO_PARCIAL = 1
    TRABALHO_TELETRABALHO_INTEGRAL = 2
    TRABALHO_PRESENCIAL = 3
    REGIME_EXECUCAO_CHOICES = [
        [TRABALHO_TELETRABALHO_PARCIAL, 'Teletrabalho parcial'],
        [TRABALHO_TELETRABALHO_INTEGRAL, 'Teletrabalho integral'],
        [TRABALHO_PRESENCIAL, 'Presencial'],
    ]
    regime_execucacao = models.PositiveIntegerField('Regime individual de execução no PGD', null=True, choices=REGIME_EXECUCAO_CHOICES)
    percentual_teletrabalho = models.DecimalFieldPlus(verbose_name='% de Teletrabalho', default=0)

    data_verificacao_ponto = models.DateFieldPlus(verbose_name='Data de Verificação do Ponto', null=True, blank=True)
    setor_pode_homologar_pit_rit = models.ForeignKeyPlus(
        'rh.Setor', verbose_name='Setor', related_name='setor_pode_homologar_pit_rit_pgd2', editable=False, null=True
    )

    # ---------------------------
    # Dados RIT
    # ---------------------------

    EM_CADASTRO_RIT = 1
    AGUARDANDO_PARECER_RIT = 2
    HOMOLOGADO_RIT = 3
    SITUACAO_RIT_CHOICES = [[EM_CADASTRO_RIT, 'Em Fase de Cadastro'], [AGUARDANDO_PARECER_RIT, 'Aguardando parecer'], [HOMOLOGADO_RIT, 'Homologado']]
    SITUACOES_RIT_PODE_CALCULAR_PIT = [EM_CADASTRO_RIT]
    SITUACOES_EXECUCAO_CADASTRADO_RIT = [EM_CADASTRO_RIT, AGUARDANDO_PARECER_RIT]
    situacao_rit = models.PositiveIntegerField('Situação', null=True, editable=False, choices=SITUACAO_RIT_CHOICES)

    AVALIACAO_EXCEPCIONAL_RIT = 1
    AVALIACAO_ALTO_RIT = 2
    AVALIACAO_ADEQUADO_RIT = 3
    AVALIACAO_INADEQUADO_RIT = 4
    AVALIACAO_NAO_EXECUTADO_RIT = 5
    AVALIACAO_RIT_CHOICES = [
        [AVALIACAO_EXCEPCIONAL_RIT, 'Excepcional: plano de trabalho executado muito acima do esperado'],
        [AVALIACAO_ALTO_RIT, 'Alto desempenho: plano de trabalho executado acima do esperado'],
        [AVALIACAO_ADEQUADO_RIT, 'Adequado: plano de trabalho executado dentro do esperado'],
        [AVALIACAO_INADEQUADO_RIT, 'Inadequado: plano de trabalho executado abaixo do esperado ou parcialmente executado'],
        [AVALIACAO_NAO_EXECUTADO_RIT, 'Não executado: plano de trabalho integralmente não executado'],
    ]
    avaliacao_rit = models.PositiveIntegerField(
        f'Avaliação {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}', null=True, editable=False, choices=AVALIACAO_RIT_CHOICES
    )
    avaliacao_observacao_rit = models.TextField(editable=False, null=True)

    rit_em_execucao = models.BooleanField('Em execução', default=False)

    # ---------------------------
    # Calculos
    # ---------------------------

    # Previsto
    tempo_previsto = models.DecimalFieldPlus(default=0)

    # Calculos das horas do PIT
    # ----------------------------

    # horas de trabalho pesencial e atendimento em teletrabalho
    tempo_trabalho_presencial = models.DecimalFieldPlus(default=0)
    tempo_atendimento_teletrabalho = models.DecimalFieldPlus(default=0)
    qtd_trabalho_presencial_homologado = models.PositiveIntegerField(default=0)
    qtd_atendimento_teletrabalho_homologado = models.PositiveIntegerField(default=0)

    # vinculados a entregas da própria unidade (setores)
    # - Vinculados ao setor do servidor
    tempo_planejado_vinculados_proprio = models.DecimalFieldPlus(default=0)
    percentual_tempo_planejado_vinculados_proprio = models.DecimalFieldPlus(default=0)

    # vinculados a entregas de outras unidades (setores), órgãos ou entidades diversos
    # - Vinculados a outros setores
    tempo_planejado_vinculados_outros = models.DecimalFieldPlus(default=0)
    percentual_tempo_planejado_vinculados_outros = models.DecimalFieldPlus(default=0)

    # não vinculados diretamente a entregas da própria unidade, mas necessários ao adequado funcionamento administrativo ou à gestão de equipes e entregas
    # - Não vinculados a nenhuma entrega
    tempo_planejado_nao_vinculados = models.DecimalFieldPlus(default=0)
    percentual_tempo_planejado_nao_vinculados = models.DecimalFieldPlus(default=0)

    # Tempo total planejado
    tempo_planejado_total = models.DecimalFieldPlus(default=0)

    # Calculos das horas do RIT
    # ----------------------------
    # vinculados a entregas da própria unidade (setores)
    # - Vinculados ao setor do servidor
    tempo_executado_vinculados_proprio = models.DecimalFieldPlus(default=0)
    percentual_tempo_executado_vinculados_proprio = models.DecimalFieldPlus(default=0)

    # vinculados a entregas de outras unidades (setores), órgãos ou entidades diversos
    # - Vinculados a outros setores
    tempo_executado_vinculados_outros = models.DecimalFieldPlus(default=0)
    percentual_tempo_executado_vinculados_outros = models.DecimalFieldPlus(default=0)

    # não vinculados diretamente a entregas da própria unidade, mas necessários ao adequado funcionamento administrativo ou à gestão de equipes e entregas
    # - Não vinculados a nenhuma entrega
    tempo_executado_nao_vinculados = models.DecimalFieldPlus(default=0)
    percentual_tempo_executado_nao_vinculados = models.DecimalFieldPlus(default=0)

    # Tempo total executado e executado homologado
    tempo_executado_total = models.DecimalFieldPlus(verbose_name='Total de horas da execução', default=0, blank=True, null=True)
    percentual_tempo_executado_total = models.DecimalFieldPlus(verbose_name='Percentual de horas da execução', default=0, blank=True, null=True)
    tempo_executado_total_teletrabalho = models.DecimalFieldPlus(
        verbose_name='Total de horas da execução em teletrabalho', default=0, blank=True, null=True
    )
    percentual_tempo_executado_total_teletrabalho = models.DecimalFieldPlus(
        verbose_name='Percentual de horas da execução em teletrabalho', default=0, blank=True, null=True
    )
    #
    tempo_executado_homologado_total = models.DecimalFieldPlus(verbose_name='Total de horas homologadas', default=0, blank=True, null=True)

    # Distribuicao de CH para compensação
    # --------------------
    # Dados básicos
    ch_distribuida = models.DecimalFieldPlus(verbose_name='CH distribuída', default=0)
    ch_a_distribuir = models.DecimalFieldPlus(verbose_name='CH a distribuir', default=0)
    # Período RIT
    ch_distribuido_periodo_rit = models.DecimalFieldPlus(
        verbose_name=f'CH distribuída no período do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}', default=0
    )
    # Semestre do RIT
    ch_distribuido_semestre_rit = models.DecimalFieldPlus(
        verbose_name=f'CH distribuída no semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}', default=0
    )
    # Compesação específica
    ch_distribuido_compesacao_especifica = models.DecimalFieldPlus(verbose_name='CH distribuída para compensações específicas', default=0)
    # Se na distribuição automática sobrar CH A DISTRBIUIR é pq não tinha mais onde distribuir a CH HOMOLOGADA deste RIT
    # - Assim, o RIT fica bloqueado para distribuições manuais
    bloqueado_para_distribuicao_manual = models.BooleanField(default=False)

    # ---------------------------
    # API
    # ---------------------------

    deve_enviar_pela_api = models.BooleanField(verbose_name='Deve enviar pela API PGD', default=False)
    data_hora_ultimo_envio_api = models.DateTimeFieldPlus(verbose_name='Data/hora do último envio pela API PGD', null=True, blank=True)
    # 1 Cancelado 2 Aprovado 3 Em execução 4 Concluído
    situacao_api_no_ultimo_envio = models.IntegerFieldPlus(
        verbose_name='Situaçãp de execução no momento do último envio pela API PGD', null=True, blank=True
    )

    class Meta:
        verbose_name = f'{nomenclatura.plano_individual_de_trabalho_pgd2}'
        verbose_name_plural = nomenclatura.planos_individuais_de_trabalho_pgd2

    def __str__(self):
        return f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} - {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)} | {self.adesao.servidor}'

    # ===============================================
    # MÉTDOS AUXILIARES
    # ===============================================
    @staticmethod
    def get_primeiro_pit_adesao(adesao):
        return (
            PlanoIndividualTrabalho.objects.filter(adesao=adesao)
            .exclude(situacao__in=[PlanoIndividualTrabalho.CANCELADO])
            .order_by('data_inicio')
            .first()
        )

    def get_situacao_pit_calculado(self, user):
        if self.adesao.servidor.pk != user.get_relacionamento().pk:
            return mark_safe(status(self.get_situacao_display()))
        pode_solicitar_aprovacao_homologacao_pit, _ = self.pode_solicitar_aprovacao_homologacao_pit(user, retornar_lista_erros=False)
        if pode_solicitar_aprovacao_homologacao_pit:
            return mark_safe('<span class="status status-alert">Em fase de Cadastro/Aguardando envio para Aprovação/Homologação</span>')
        else:
            return mark_safe(status(self.get_situacao_display()))

    def get_situacao_rit_calculado(self, user):
        if self.pit_estah_cancelado():
            return mark_safe(status(self.get_situacao_display()))
        else:
            if self.adesao.servidor.pk != user.get_relacionamento().pk or self.rit_estah_homologado():
                return mark_safe(status(self.get_situacao_rit_display()))

            existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit, _ = (
                self.existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(user, retornar_lista_erros=False)
            )
            if not existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit:
                return mark_safe(status(self.get_situacao_rit_display()))
            if existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit:
                return mark_safe(
                    f'<span class="status status-alert">Aguardando alteração e/ou aprovação/homologação do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}</span>'
                )
        return None

    def se_utiliza_integracao_com_ponto(self):
        return utilizar_integracao_com_ponto()

    def get_verbose_periodo(self):
        return f'{format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)}'

    def get_verbose_pit_rit(self):
        return f'{nomenclatura.pit_rit_pgd2} - {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)} | {self.adesao.servidor}'

    def get_verbose_pit(self):
        return f'{nomenclatura.plano_individual_de_trabalho_com_sigla_pgd2} de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)} | {self.adesao.servidor}'

    def get_verbose_pit_notificacao(self):
        return f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} {self.get_verbose_periodo()}'

    def get_verbose_rit(self):
        return f'{nomenclatura.relatorio_individual_de_trabalho_com_sigla_pgd2} de {format_datetime(self.data_inicio)} a {format_datetime(self.data_fim)} | {self.adesao.servidor}'

    def pit_estah_homologado(self):
        return self.situacao == self.HOMOLOGADO

    def pit_estah_cancelado(self):
        return self.situacao == self.CANCELADO

    def rit_estah_homologado(self):
        return self.situacao_rit == self.HOMOLOGADO_RIT

    def get_pess_aptos_relacionados(self):
        # ------------------------------------------------
        # Retorna os PESs relacionados a este PIT
        # - PESs de setores que o servidor tenha aderido
        # - PESs que estejam alinhados com o calendário PIT/RIT relacionado
        # ------------------------------------------------
        pess_aderidos_servidor = SolicitacaoAdesaoPesServidor.get_vigentes(self.adesao)
        ids_setores_pess_aderidos_servidor = pess_aderidos_servidor.values_list('setor_id', flat=True).distinct()
        return PlanoEntregasSetorial.get_pes_apto_relacionado_periodo_pit_rit_setores(self.periodo_pit_rit, ids_setores_pess_aderidos_servidor)

    def get_entregas_adicionar_pit(self):
        # ------------------------------------------------
        # Retorna as entregas aptas a serem adicionadas a um PIT neste momento
        # ------------------------------------------------

        # PESs de setores que o servidor tenha aderido
        # PESs que estejam alinhados com o calendário PIT/RIT relacionado
        # ------------------------------------------------
        pess_aptos = self.get_pess_aptos_relacionados()

        # Entregas não canceladas e relacionada aos PESs selecionados anteriormente
        # ------------------------------------------------
        entregas_pes = PlanoEntregasSetorialEntregas.objects.filter(pes__in=pess_aptos, cancelado=False).order_by('pes__periodo', 'titulo')

        return entregas_pes

    def get_entregas_pit(self):
        return PlanoIndividualTrabalhoEntregas.objects.filter(pit=self).order_by('titulo')

    def get_entregas_para_analise_aprovacao_homologacao(self, entregas_pit=None):
        # Todas as entregas
        if not entregas_pit:
            entregas_pit = self.get_entregas_pit().order_by('entrega_pes__pes__setor__sigla', 'entrega_pes__titulo', 'titulo')

        # Todos os originais homologados + Todos os originais não homologados (novos)
        q1 = Q(original__isnull=True, homologado=True)
        q2 = Q(original__isnull=True, homologado=False)

        # Todas as copias
        q3 = Q(original__isnull=False)

        # - Excluindo os originais com copia
        ids_originais_com_copia = entregas_pit.filter(original__isnull=False, homologado=False).values_list('original_id', flat=True)
        entregas_pit = entregas_pit.filter(q1 | q2 | q3).exclude(id__in=ids_originais_com_copia)

        return entregas_pit

    def get_entregas_pit_para_rit(self):
        return PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, cancelado=False, homologado=True).order_by('titulo')

    def get_entregas_pit_para_rit_com_canceladas_utilizadas(self):
        # Retorna
        # - as entregas PIT que não estão canceldas
        # - adicionando
        #   - as que tem alguma entrega de RIT vinculada E
        #   - tem entrega PIT cancelada OU entrega PES cancelada
        entregas_pit_ids = list(PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, cancelado=False).values_list('id', flat=True))
        entregas_pit_ids.extend(
            list(
                RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit=self)
                .filter(Q(entrega_pit__cancelado=True) | Q(entrega_pit__entrega_pes__cancelado=True))
                .values_list('entrega_pit_id', flat=True)
            )
        )
        return PlanoIndividualTrabalhoEntregas.objects.filter(id__in=entregas_pit_ids, homologado=True).order_by('titulo')

    @staticmethod
    def get_entregas_pit_com_canceladas_utilizadas(pits_ids):
        # Retorna
        # - as entregas PIT que não estão canceldas
        # - adicionando
        #   - as que tem alguma entrega de RIT vinculada E
        #   - tem entrega PIT cancelada OU entrega PES cancelada
        entregas_pit_ids = list(PlanoIndividualTrabalhoEntregas.objects.filter(pit_id__in=pits_ids, cancelado=False).values_list('id', flat=True))
        entregas_pit_ids.extend(
            list(
                RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit_id__in=pits_ids)
                .filter(Q(entrega_pit__cancelado=True) | Q(entrega_pit__entrega_pes__cancelado=True))
                .values_list('entrega_pit_id', flat=True)
            )
        )
        entregas_pit = PlanoIndividualTrabalhoEntregas.objects.filter(id__in=entregas_pit_ids, homologado=True)
        entregas_pit = entregas_pit.select_related('pit', 'pit__adesao__servidor', 'pit__periodo_pit_rit', 'pit__setor_pode_homologar_pit_rit')
        return entregas_pit

    def get_orientacoes_sistemicas_relacionadas_ao_periodo(self):
        # return ConfiguracaoOrientacaoPit.objects.filter(data_inicio__lte=self.data_inicio, cancelado=False, eh_sistemica=True)
        periodo_query_1 = Q(data_fim__isnull=True) & Q(data_inicio__lte=self.data_fim)
        periodo_query_2 = Q(data_fim__isnull=False) & (Q(data_inicio__gte=self.data_inicio) | Q(data_fim__lte=self.data_fim))
        return ConfiguracaoOrientacaoPit.objects.filter(cancelado=False, eh_sistemica=True).filter(periodo_query_1 | periodo_query_2)

    def get_orientacoes_nao_sistemicas_relacionadas_ao_periodo(self):
        # return ConfiguracaoOrientacaoPit.objects.filter(data_inicio__lte=self.data_inicio, cancelado=False, eh_sistemica=False)
        periodo_query_1 = Q(data_fim__isnull=True) & Q(data_inicio__lte=self.data_fim)
        periodo_query_2 = Q(data_fim__isnull=False) & (Q(data_inicio__gte=self.data_inicio) | Q(data_fim__lte=self.data_fim))
        return ConfiguracaoOrientacaoPit.objects.filter(cancelado=False, eh_sistemica=False).filter(periodo_query_1 | periodo_query_2)

    @staticmethod
    def get_rits(adesao):
        return PlanoIndividualTrabalho.objects.filter(adesao=adesao)

    @staticmethod
    def get_rits_homologados(adesao):
        return PlanoIndividualTrabalho.objects.filter(adesao=adesao, situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)

    @staticmethod
    def get_rits_homologados_todos():
        return PlanoIndividualTrabalho.objects.filter(situacao_rit=PlanoIndividualTrabalho.HOMOLOGADO_RIT)

    @staticmethod
    def get_pits_periodos_pendendentes_criacao_ou_envio(user):
        # Utilizado pelos alertas e pendências

        # Como obter os PITs que não foram criados E aqueles que foram criados mas estão pendentes de envio
        # - Pegar as adesoes vigentes do servidor
        # - Saber para cada adesão vigente quais PITs deveria ter criado e
        #   tirar o diff com os que foram criados resultando em duas listas de PITs
        #   - Periodos sem PIT criado
        #   - Periodos com PIT criado
        # - Da lista de PITs criados devemos saber quais deles não foram enviados e que nunca foram homologados
        #   - Resultando em uma lista de PITs sem envio válido
        # - A lista de PITs com pendência será
        #   - "PITs que não foram criados" + "PITs sem envio válido"
        #
        #
        # Adesoes vigentes e sabendo quais PITs deveria ter criado
        adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(user)
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
                inicio_adesao = ad.primeiro_dia_pgd_nessa_adesao(considera_inicio_adesao=True)
                final_adesao = ad.ultimo_dia_pgd_nessa_adesao() - relativedelta(days=1)
                query_periodo = Q(data_prazo_entrega_pit__range=(inicio_adesao, final_adesao))
                periodos = PeriodoPitRit.objects.filter(cancelado=False).filter(query_periodo).order_by('data_inicio')
                if periodos:
                    periodos_que_precisa_de_pit.extend(periodos)

        if periodos_que_precisa_de_pit:
            periodos_que_precisa_de_pit = list(set(periodos_que_precisa_de_pit))
            periodos_que_precisa_de_pit = sorted(periodos_que_precisa_de_pit, key=lambda p: p.data_inicio)

            # ------------------------------
            # Todos os PITs criados nas adesoes vigentes
            # ------------------------------
            pits_da_adesao = (
                PlanoIndividualTrabalho.objects.filter(adesao__in=adesoes_vigentes)
                .exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
                .order_by('data_inicio')
                .select_related('periodo_pit_rit')
            )

            # ------------------------------
            # Obtendo periodos com PIT criado
            # ------------------------------
            periodos_pits_criados = PeriodoPitRit.objects.filter(cancelado=False, id__in=pits_da_adesao.values('periodo_pit_rit__id')).order_by(
                'data_inicio'
            )
            periodos_pits_criados = list(periodos_pits_criados)

            # ------------------------------
            # Obtendo periodos que nao PIT criado
            # ------------------------------
            periodos_pits_nao_criados = []
            for p in periodos_que_precisa_de_pit:
                if p not in periodos_pits_criados:
                    periodos_pits_nao_criados.append(p)

            # ------------------------------
            # Dos PITs que foram criados (cadastrados) saber
            # - Os periodos que o PIT ainda não
            #   - Não foram enviados ao menos uma vez
            #   - Não foram aprovados ao menos uma vez
            # ------------------------------
            periodos_pits_enviados_sem_homologacao = []
            for pa in pits_da_adesao:
                # Pendente se
                # - Cadastrou e nao enviou
                # - Cadastrou mas precisa ser homologado de novo
                foi_enviado_alguma_vez = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    pit=pa, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO
                ).exists()
                if not foi_enviado_alguma_vez:
                    periodos_pits_enviados_sem_homologacao.append(pa.periodo_pit_rit)
                else:
                    pode_solicitar_aprovacao_homologacao_pit = pa.pode_solicitar_aprovacao_homologacao_pit(user, retornar_lista_erros=False)
                    if pode_solicitar_aprovacao_homologacao_pit[0]:
                        periodos_pits_enviados_sem_homologacao.append(pa.periodo_pit_rit)

            # ------------------------------
            # Resultado final
            # ------------------------------
            periodos_pendentes_pit = periodos_pits_nao_criados + periodos_pits_enviados_sem_homologacao

        # ------------------------------
        # Filtra os PITs que estão com ch prevista para o período
        # - Se a CH prevista for maior que zero entao o PIT é necessário
        # - Se nao tiver ativado a integracao com o ponto tb é necessário o PIT
        # ------------------------------
        servidor = user.get_relacionamento()
        periodos_pendentes_pit_final = []
        if utilizar_integracao_com_ponto():
            if periodos_pendentes_pit:
                for pit in periodos_pendentes_pit:
                    if utilizar_integracao_com_ponto():
                        if get_ch_prevista_servidor_periodo(servidor, pit.data_inicio, pit.data_fim) > 0:
                            periodos_pendentes_pit_final.append(pit)
                    else:
                        periodos_pendentes_pit_final.append(pit)
        else:
            periodos_pendentes_pit_final = periodos_pendentes_pit

        # if periodos_pendentes_pit_final:
        #    periodos_pendentes_pit_final = sorted(periodos_pendentes_pit_final, key=lambda p: p.data_inicio)
        # return periodos_pendentes_pit_final

        ids = [p.id for p in periodos_pendentes_pit_final]
        return PeriodoPitRit.objects.filter(id__in=ids).order_by('data_inicio')

    @staticmethod
    def get_rits_pendente_envio(user):
        # Utilizado pelos alertas e pendências

        # Saber quais RITs estão pendentes de envio para aprovação/homologação
        # - Considerando todos os RITs da adesão
        # - Pega os que era pra ter sido enviado mas não foram
        #   - Considerando período do RIT e a "data_prazo_entrega_rit" em PeriodoPitRit
        #   - Considerando que tenham sido enviados, no mínimo, uma vez e nunca tenham sido homologados
        #
        # Adesoes vigentes e sabendo quais PITs deveria ter criado
        adesoes_vigentes = SolicitacaoAdesaoServidor.get_vigentes(user)

        rits_pendentes_envio = None
        if adesoes_vigentes:
            adesoes_vigentes = adesoes_vigentes.order_by('id')
        else:
            return rits_pendentes_envio

        if adesoes_vigentes:
            rits_pendentes_envio = PlanoIndividualTrabalho.objects.filter(
                adesao__in=adesoes_vigentes, situacao=PlanoIndividualTrabalho.HOMOLOGADO, situacao_rit=PlanoIndividualTrabalho.EM_CADASTRO_RIT
            )

            # Sabendo quais nao precisavam ser enviados ainda considerando a "data_prazo_entrega_rit" do PeriodoPitRit relacionado
            # - excluindo esses
            hoje = get_datetime_now().date()
            rits_pendentes_envio = rits_pendentes_envio.exclude(periodo_pit_rit__data_prazo_entrega_rit__gte=hoje)

            rits_pendentes_envio = rits_pendentes_envio.select_related('adesao__servidor')

            # Exclui os rits
            # - que tenham sido enviados, no mínimo, uma vez e nunca tenham sido homologados
            # - que não tenham ch prevista para o período
            ids_excluir_rits = []
            for rit in rits_pendentes_envio:
                tem_registro_de_envio = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    pit=rit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO_RIT
                ).exists()
                tem_registro_homologacao = RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    pit=rit, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_HOMOLOGOU_RIT
                ).exists()
                nao_tem_ch_prevista = (
                    not get_ch_prevista_servidor_periodo(rit.adesao.servidor, rit.data_inicio, rit.data_fim) > 0
                    or not utilizar_integracao_com_ponto()
                )
                if not (tem_registro_de_envio and not tem_registro_homologacao) and nao_tem_ch_prevista:
                    ids_excluir_rits.append(rit.id)
            rits_pendentes_envio = rits_pendentes_envio.exclude(id__in=ids_excluir_rits)

        return rits_pendentes_envio

    @staticmethod
    def get_pits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True):
        setores = []
        servidores = []
        setores_hoje = []
        if apenas_chefe_direto:
            """
            # ----------------------------------------------
            # Que o chefe DEVE aprovar/homologar
            # Considera apenas os setores e servidores que é chefe direto
            # ----------------------------------------------
            # Setores que é chefe direto. Exemplo: DIGPE
            setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Chefes dos subsetores da DIGPE. Exemplo: Chefe CODEPE, Chefe CODEPE, Chefe COGCAP, Chefe COADPE e Chefe COASS
            servidores = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Todos os subsetores da DIGPE
            setores_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
            """

            setores, servidores, setores_hoje = get_servidores_setores_sou_chefe_direto(user)
        else:
            # ----------------------------------------------
            # Que o chefe PODE aprovar/homologar
            # Considera os setores descendentes e exclui setores que é chefe direto
            # ----------------------------------------------
            # Todos os setores que é chefe incluindo a DIGPE e seus Subsetores
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            # Setores que é chefe direto. Exemplo: DIGPE
            setores_chefe_direto = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Exclui a DIGPE
            setores = setores.exclude(id__in=setores_chefe_direto.values('id'))

        lista_pits = (
            PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
            .exclude(adesao__servidor=user.get_relacionamento())
            .order_by('adesao__servidor__pessoa_fisica__nome')
        )

        solicitacoes_homologacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=1, setores=setores, servidores=servidores, setores_hoje=setores_hoje, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        )

        solicitacoes_aprovacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=1, setores=setores, servidores=servidores, setores_hoje=setores_hoje, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )

        ids_pits_apovacao = solicitacoes_aprovacao.values_list('solicitacao__pit', flat=True)
        ids_pits_homologacao = solicitacoes_homologacao.values_list('solicitacao__pit', flat=True)

        lista_pits_aprova = lista_pits.filter(id__in=ids_pits_apovacao)
        lista_pits_homologacao = lista_pits.filter(id__in=ids_pits_homologacao)

        lista_pits_aprova = lista_pits_aprova.select_related('adesao__servidor__pessoa_fisica', 'periodo_pit_rit')
        lista_pits_homologacao = lista_pits_homologacao.select_related('adesao__servidor__pessoa_fisica', 'periodo_pit_rit')

        return lista_pits_aprova, lista_pits_homologacao

    @staticmethod
    def get_pits_pendendentes_avaliacao_chefe_direto(user):
        # Utilizado pelos alertas/pendências e pela tela de aprovacao/homologacao do chefe
        return PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True)

    @staticmethod
    def get_pits_pendendentes_avaliacao_chefe_outros(user):
        # Utilizado pela tela de aprovacao/homologacao do chefe
        return PlanoIndividualTrabalho.get_pits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=False)

    @staticmethod
    def get_rits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True):
        setores = []
        servidores = []
        setores_hoje = []
        if apenas_chefe_direto:
            # ----------------------------------------------
            # Considera apenas os setores e servidores que é chefe direto
            # ----------------------------------------------
            # Setores que é chefe direto. Exemplo: DIGPE
            setores = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Chefes dos subsetores da DIGPE. Exemplo: Chefe CODEPE, Chefe CODEPE, Chefe COGCAP, Chefe COADPE e Chefe COASS
            servidores = servidores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Todos os subsetores da DIGPE
            setores_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        else:
            # ----------------------------------------------
            # Considera os setores descendentes e exclui setores que é chefe direto
            # ----------------------------------------------
            # Todos os setores que é chefe incluindo a DIGPE e seus Subsetores
            setores = setores_que_sou_chefe_hoje(user.get_relacionamento())
            # Setores que é chefe direto. Exemplo: DIGPE
            setores_chefe_direto = setores_que_sou_chefe_direto_hoje(user.get_relacionamento())
            # Exclui a DIGPE
            setores = setores.exclude(id__in=setores_chefe_direto.values('id'))

        lista_pits = (
            PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
            .exclude(adesao__servidor=user.get_relacionamento())
            .order_by('adesao__servidor__pessoa_fisica__nome')
        )

        solicitacoes_aprovacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=2, setores=setores, servidores=servidores, setores_hoje=setores_hoje, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )
        solicitacoes_homologacao = PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=2, setores=setores, servidores=servidores, setores_hoje=setores_hoje, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        )

        ids_pits_apovacao = solicitacoes_aprovacao.values_list('solicitacao__pit', flat=True)
        ids_pits_homologacao = solicitacoes_homologacao.values_list('solicitacao__pit', flat=True)

        lista_pits_aprova = lista_pits.filter(id__in=ids_pits_apovacao)
        lista_pits_homologacao = lista_pits.filter(id__in=ids_pits_homologacao)

        lista_pits_aprova = lista_pits_aprova.select_related('adesao__servidor__pessoa_fisica', 'periodo_pit_rit')
        lista_pits_homologacao = lista_pits_homologacao.select_related('adesao__servidor__pessoa_fisica', 'periodo_pit_rit')

        return lista_pits_aprova, lista_pits_homologacao

    @staticmethod
    def get_rits_pendendentes_avaliacao_chefe_direto(user):
        # Utilizado pelos alertas/pendências e pela tela de aprovacao/homologacao do chefe
        return PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=True)

    @staticmethod
    def get_rits_pendendentes_avaliacao_chefe_outros(user):
        # Utilizado pela tela de aprovacao/homologacao do chefe
        return PlanoIndividualTrabalho.get_rits_pendendentes_avaliacao_chefe(user, apenas_chefe_direto=False)

    # horas de trabalho pesencial e atendimento em teletrabalho
    def get_tempo_trabalho_presencial_horas(self):
        return formata_segundos(self.tempo_trabalho_presencial, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    def get_tempo_atendimento_teletrabalho_horas(self):
        return formata_segundos(self.tempo_atendimento_teletrabalho, '{h:02.0f}h ', '{m:02.0f}min ', '{s:02.0f}seg ', True)

    def servidor_estah_teletrabalho_no_exterior_no_periodo_deste_pit(self):
        afastamentos_pgd_exterior = get_afastamentos_exterior()
        afastamentos_pgd_exterior = (
            ServidorAfastamento.get_afastamentos(self.adesao.servidor, self.data_inicio, self.data_fim)
            .filter(afastamento__in=afastamentos_pgd_exterior)
            .exists()
        )

        pgd_exterior_cadastro = (
            PGDExterior.get_vigentes().filter(servidor=self.adesao.servidor, data_inicio__lte=self.data_fim, data_fim__gte=self.data_inicio).exists()
        )

        return afastamentos_pgd_exterior or pgd_exterior_cadastro

    # ===============================================
    # CADASTRAR E EDITAR - PIT
    # ===============================================

    @staticmethod
    def pode_iniciar_cadastro(user, retornar_lista_erros=False):
        # Utilizado apenas no cadastro de um novo PIT
        # Se pode iniciar o cadastro de um PIT

        erros = []

        if not SetorHabilitacao.setor_estah_habilitado(user.get_relacionamento().setor):
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado(sigla_setor=user.get_relacionamento().setor.sigla))
            else:
                return False, None

        # Tem que ter instrucoes cadastradas
        if not ConfiguracaoOrientacaoPit.get_vigentes_sistemico().exists():
            if retornar_lista_erros:
                erros.append(f'A Gestão deve cadastrar Orientação Sistêmica sobre {nomenclatura.plano_individual_de_trabalho_pgd2}.')
            else:
                return False, None

        # Precisa ter, no mínimo, uma calendaari ode PIT que esteja vigente
        if not PeriodoPitRit.objects.filter(cancelado=False).exists():
            if retornar_lista_erros:
                erros.append(f'É necesssário ter, no mínimo, um Calendário de {nomenclatura.pit_rit_pgd2} cadastrado.')
            else:
                return False, None

        # Tem que ter adesao VIGENTE PGD
        if not SolicitacaoAdesaoServidor.get_vigentes_ou_desligado_na_carencia(user):
            if retornar_lista_erros:
                erros.append(f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} você deve ter alguma adesão vigente ao PGD.')
            else:
                return False, None

        # Ter, no mínimo, uma adesão PES deferida
        pts_apto = SolicitacaoAdesaoPesServidor.existe_adesao_deferida_para_o_servidor(user.get_relacionamento())
        if not pts_apto:
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} você deve ter adesão a, no mínimo, um PES que esteja apto a ser utilizado por este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.'
                )
            else:
                return False, None

        # pes_apto = PlanoEntregasSetorial.existe_algum_pes_apto(setor)
        # if not pes_apto:
        #    if retornar_lista_erros:
        #        erros.append('É necessário que o setor tenha um PES apto.')
        #    else:
        #        return False, None
        #

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_finalizar_cadastro(user, periodo_pit_rit, adesao_pgd, data_inicio, data_fim, retornar_lista_erros=False):
        # Utilizado apenas no cadastro de um novo PIT
        # Se pode finalizar o cadastro de um PIT

        erros = []
        servidor = user.get_relacionamento()

        if not (user and periodo_pit_rit and not periodo_pit_rit.cancelado and adesao_pgd and data_inicio):
            if retornar_lista_erros:
                erros.append('É preciso informar o período, adesão e a data início.')
                return False, erros
            else:
                return False, None

        pode_pelo_iniciar, erros_pode_pelo_iniciar = PlanoIndividualTrabalho.pode_iniciar_cadastro(user, retornar_lista_erros=True)
        if not pode_pelo_iniciar:
            erros.extend(erros_pode_pelo_iniciar)

        # ADESÃO PGD SELECIONADA
        # ---------------------------------------
        # - A adesão selecionada deve estar vigente
        if not adesao_pgd.estah_vigente_ou_desligado_na_carencia:
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}, você pode ter selecionado uma adesão ao PGD que esteja vigente ou desligada na carência.'
                )
            else:
                return False, None

        # ADESÃO PESs DO SERVIDOR
        # ---------------------------------------
        # - Deve ter algma adesão PES vigente
        sols_pes_servidor = SolicitacaoAdesaoPesServidor.get_vigentes(adesao_pgd)
        if not sols_pes_servidor:
            if retornar_lista_erros:
                erros.append(f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} você deve ter aderido a algum PES.')
            else:
                return False, None

        # PES
        # ---------------------------------------
        # Dentre os PESs aderidos pelo servidor nessa adesão PGD
        # - pelo o menos o PES do setor do servidor deve estar alinhado com o calendário PIT/RIT selecionado e deve estar apto para um PIT
        # - em resumo
        #   - se o PIT é de janeiro
        #   - deve ter um PES que contemple esse periodo PIR/RIT selecionado E este PES tem que estar apto
        if sols_pes_servidor:
            if not considerar_auditoria_centralizada() or (considerar_auditoria_centralizada() and not servidor_eh_auditor(servidor)):
                pes_apto_no_periodo = PlanoEntregasSetorial.get_pes_apto_relacionado_periodo_pit_rit_setor(periodo_pit_rit, servidor.setor).exists()
                sols_pes_servidor = sols_pes_servidor.filter(setor=servidor.setor).exists()
                if not (pes_apto_no_periodo and sols_pes_servidor):
                    if retornar_lista_erros:
                        erros.append(
                            f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} o servidor deve ter aderido ao PES do seu setor e este PES deve estar apto e alinhado com o período do {nomenclatura.pit_rit_pgd2} selecionado. Nesse caso, solicite ao chefe do seu setor a criação do PES para o período desejado.'
                        )
                    else:
                        return False, None

        # ---------------------------------------
        # Valida considerando
        # - Adesão
        # - Período PIT/RIT
        # - Data inicio
        # - Data fim
        # ---------------------------------------

        # Periodo PIT/RIT X Adesao
        # ---------------------------------------
        # - Periodo PIT/RIT deve iniciar dentro da adesão
        periodo_inicia_depois_inicio_adesao = periodo_pit_rit.data_inicio >= adesao_pgd.get_data_inicio_adesao()
        periodo_finaliza_depois_inicio_adesao = periodo_pit_rit.data_fim >= adesao_pgd.get_data_inicio_adesao()
        if not (periodo_inicia_depois_inicio_adesao or periodo_finaliza_depois_inicio_adesao):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} você deve ter selecionado um Calendário {nomenclatura.pit_rit_pgd2} que seja compatível com a Adesão ao PGD selecionada.'
                )
            else:
                return False, None

        # Data inicio X Adesao
        # ---------------------------------------
        # - Deve iniciar na data ou depois do inicio da adesao relacionada
        if not (data_inicio >= adesao_pgd.get_data_inicio_adesao()):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar dentro do período da adesão ao PGD relacionada. Verifique o início da sua adesão'
                )
            else:
                return False, None
        # - Se tiver desligamento na adesao vigente
        #   - tem que evitar cadastrar um PIT que inicie no dia ou depois da data_desligamento_efeitos_a_partir_de
        #   - O PIT deve INICIAR ANTES
        if adesao_pgd.data_desligamento_efeitos_a_partir_de and not (data_inicio < adesao_pgd.data_desligamento_efeitos_a_partir_de):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar ANTES da data de efeito desligamento. Verifique se você possui algum desligamento para essa adesão.'
                )
            else:
                return False, None

        # Data inicio X Periodo
        # ---------------------------------------
        # - Deve estar dentro do periodo PIT/RIT selecionado
        if not (periodo_pit_rit.data_inicio <= data_inicio <= periodo_pit_rit.data_fim):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar dentro do período {nomenclatura.pit_rit_pgd2} selecionado. Verifique o início da sua adesão'
                )
            else:
                return False, None

        # Data fim X Adesao
        # ---------------------------------------
        if adesao_pgd.data_desligamento_efeitos_a_partir_de and not (data_fim < adesao_pgd.data_desligamento_efeitos_a_partir_de):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve finalizar ANTES da data de efeito desligamento. Verifique se você possui algum desligamento para essa adesão.'
                )
            else:
                return False, None

        # Data fim X Periodo
        # ---------------------------------------
        if not (periodo_pit_rit.data_inicio <= data_fim <= periodo_pit_rit.data_fim):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve finalizar dentro do período {nomenclatura.pit_rit_pgd2} selecionado. Verifique o início da sua adesão'
                )
            else:
                return False, None

        # ---------------------------------------
        # Outras validações
        # ---------------------------------------

        # Se a data fim for menor que a data inicio informada
        if data_fim < data_inicio:
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve finalizar em período compatível com Calendário {nomenclatura.pit_rit_pgd2} relacionado. Também considerando eventual desligamento na adesão selecionada. Verifique se você possui algum desligamento para essa adesão.'
                )
            else:
                return False, None

        # Valida situacao e se pode e se pode exiostir PIT/RIT repetido no periodo
        # - Nao pode se existe outro PIT nas seguintes situacoes para o mesmo periodo e servidor
        # - Nao pode ter mais um PIT para o mesmo periodo PIT/RIT (mesmo que em adesoes diferentes) independente da adesao e situacao
        situacoes_cancelado = [PlanoIndividualTrabalho.CANCELADO]
        tem_outro_pit = PlanoIndividualTrabalho.objects.filter(adesao__servidor=servidor, periodo_pit_rit=periodo_pit_rit).exclude(
            situacao__in=situacoes_cancelado
        )
        if tem_outro_pit.exists():
            if retornar_lista_erros:
                erros.append(
                    f'Não pode existir um outro {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} para o mesmo período {nomenclatura.pit_rit_pgd2} (independente da situação ou adesão PGD).'
                )
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    @staticmethod
    def pode_visualizar_lista(user):
        return bool(user.has_perm('rh.chefe'))

    def pode_visualizar(self, user):
        # Se um determinado PIT pode ser visualizado

        relacionamento = user.get_relacionamento()
        eh_dono = self.adesao.servidor.pk == relacionamento.pk
        if eh_dono:
            return True

        ids_setores_envolvidos = self.get_setores_envolvidos().values_list('setor_id', flat=True)
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(relacionamento).filter(pk__in=ids_setores_envolvidos).exists()
        if eh_chefe_do_servidor:
            return True

        return self.situacao == self.HOMOLOGADO

    def pode_editar(self, user, cancelamento=False):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        # Verifica se um determinado PIT pode ser editado
        # --------------------------------------------------
        # Quem
        # - Apenas servidor dono do PIT
        if self.adesao.servidor.pk != user.get_relacionamento().pk:
            return False

        # Situação do PIT
        if self.situacao not in [self.EM_CADASTRO, self.HOMOLOGADO]:
            return False

        # Situacao da adesão
        # - Adesão do PIT deve estar vigente ou desligado na carencia
        if not self.adesao.estah_vigente_ou_desligado_na_carencia:
            return False
        # - PIT deve iniciar antes do inicio dos efeitos do desligamento (valida isso exceto quando estiver tentando cancelar o PIT)
        if self.adesao.estah_vigente_ou_desligado_na_carencia and not cancelamento:
            if self.adesao.data_desligamento_efeitos_a_partir_de and not (self.data_inicio < self.adesao.data_desligamento_efeitos_a_partir_de):
                return False

        # Enquanto estiver aguardando uma solicitação de avaliacao de PIT não pode editar
        if self.get_solicitacoes_aprovacao_homologacao_nao_finalizadas(pit_rit=1).exists():
            return False

        # RIT tem que estar em fase de cadastro ou sem situacao ainda
        return self.situacao_rit is None or self.situacao_rit == self.EM_CADASTRO_RIT

    def pode_cancelar(self, user):
        # Verifica se um determinado PIT pode ser cancelado
        # --------------------------------------------------
        return self.pode_editar(user, cancelamento=True)

    # ===============================================
    # EDITAR DADOS BÁSICOS - PIT
    # ===============================================
    def pode_editar_dados_basicos(self, user):
        return self.pode_editar(user)

    def pode_cancelar_edicao_dados_basicos(self, user):
        if not self.pode_editar(user):
            return False

        return PlanoIndividualTrabalhoCopia.objects.filter(original=self).exists()

    def validar_editar_dados_basicos(self, nova_data_inicio, novo_regime_execucacao, novo_percentual_teletrabalho, retornar_lista_erros=False):
        # Utilizado apenas na edição de um PIT
        # Valida a edição de
        # - data_inicio
        # - regime_execucacao
        # - percentual_teletrabalho

        erros = []

        # DATA INÍCIO
        # ---------------------------------------
        # Só pode informar data de inicio (diferente da data do calendario PIT) do PIT se este for o primeiro da adesao relacionada
        primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(adesao=self.adesao)
        if self.periodo_pit_rit.data_inicio != nova_data_inicio and not (primeiro_pit_adesao and primeiro_pit_adesao == self):
            if retornar_lista_erros:
                erros.append(
                    f'Só é possível informar uma data diferente da data inicio do calendário {nomenclatura.pit_rit_pgd2} quando o {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} for o primeiro da Adesão Relacionada.'
                )
            else:
                return False, None
        # Data inicio X Adesao
        # Deve iniciar na data ou depois do inicio da adesao relacionada
        if not (nova_data_inicio >= self.adesao.get_data_inicio_adesao()):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar dentro do período da adesão ao PGD relacionada. Verifique o início da sua adesão'
                )
            else:
                return False, None
        # Data inicio X Adesao
        # Se tiver desligamento na adesao vigente
        # - tem que evitar cadastrar um PIT que inicie no dia ou depois da data_desligamento_efeitos_a_partir_de
        # - O PIT deve INICIAR ANTES
        if self.adesao.data_desligamento_efeitos_a_partir_de and not (nova_data_inicio < self.adesao.data_desligamento_efeitos_a_partir_de):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar ANTES da data de efeito desligamento. Verifique se você possui algum desligamento para essa adesão.'
                )
            else:
                return False, None
        # Data inicio X Periodo
        # Deve estar dentro do periodo PIT/RIT selecionado
        if not (self.periodo_pit_rit.data_inicio <= nova_data_inicio <= self.periodo_pit_rit.data_fim):
            if retornar_lista_erros:
                erros.append(
                    f'Para cadastrar um {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} ele deve iniciar dentro do período {nomenclatura.pit_rit_pgd2} relacionado. Verifique o início da sua adesão'
                )
            else:
                return False, None

        # REGIME E % DE TELETRABALHO
        # ---------------------------------------
        # Valida novo_regime_execucacao e novo_percentual_teletrabalho
        # - em relação ao cadastrado no PES do setor que pode homologar este PIT
        # ---------------------------------------
        # Se o % máximo de teletrabalho do PES (percentual_maximo_teletrabalho_pes) relacionado ao setor que pode homologar este PIT
        # (considerando a época deste PIT e setor do servido nessa época)
        # - Se percentual_maximo_teletrabalho_pes == 0,00%
        #   - novo_regime_execucacao: deve ser TRABALHO_PRESENCIAL
        #   - novo_percentual_teletrabalho: só pode ser 0%
        # - Se percentual_maximo_teletrabalho_pes for qualquer valor maior que zero
        #   - novo_regime_execucacao: deve ser TRABALHO_TELETRABALHO_PARCIAL,
        #                                      TRABALHO_PRESENCIAL,
        #                                      TRABALHO_TELETRABALHO_INTEGRAL
        #   - novo_percentual_teletrabalho: até o limite do % informado no PES

        setor_pode_homologar = self.get_setor_envolvido_apto_para_homologar()
        pes_apto_no_periodo = PlanoEntregasSetorial.get_pes_apto_relacionado_periodo_pit_rit_setor(self.periodo_pit_rit, setor_pode_homologar).last()
        if not pes_apto_no_periodo:
            if retornar_lista_erros:
                erros.append('Nenhum plano de entrega setorial foi encontrado para o período informado.')
            else:
                return False, None

        if pes_apto_no_periodo:
            # Se o servidor está PGD Exterior ele pode colocar 100% teletrabalho independente do que está no PES
            if self.servidor_estah_teletrabalho_no_exterior_no_periodo_deste_pit():
                if not (novo_regime_execucacao == self.TRABALHO_TELETRABALHO_INTEGRAL and novo_percentual_teletrabalho == 100.00):
                    if retornar_lista_erros:
                        erros.append('Seu regime deve ser o TELETRABALHO INTEGRAL com 100% de Teletrabalho .')
                    else:
                        return False, None
            else:
                percentual_maximo_teletrabalho_pes = pes_apto_no_periodo.doc_percentual_maximo_teletrabalho

                if percentual_maximo_teletrabalho_pes == 0.00:
                    if not (novo_percentual_teletrabalho == 0.00 and novo_regime_execucacao == self.TRABALHO_PRESENCIAL):
                        if retornar_lista_erros:
                            erros.append(
                                f'O "% de Teletrabalho" e "Regime individual de execução no PGD" devem estar adequados ao informado no PES que pode homologar este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}. O regime deve ser PRESENCIAL e o % de Teletrabalho deve ser zero. Favor verificar o PES que pode homologar este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.'
                            )
                        else:
                            return False, None

                if percentual_maximo_teletrabalho_pes > 0.00:
                    if not (
                        novo_percentual_teletrabalho <= percentual_maximo_teletrabalho_pes
                        and novo_regime_execucacao
                        in [self.TRABALHO_PRESENCIAL, self.TRABALHO_TELETRABALHO_PARCIAL, self.TRABALHO_TELETRABALHO_INTEGRAL]
                    ):
                        if retornar_lista_erros:
                            erros.append(
                                f'O "% de Teletrabalho" e "Regime individual de execução no PGD" devem estar adequados ao informado no PES que pode homologar este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}. O regime deve ser PRESENCIAL ou TELETRABALHO PARCIAL ou TELETRABALHO INTEGRAL. O % de Teletrabalho deve ser até o limite informado no PES. Favor verificar o PES que pode homologar este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.'
                            )
                        else:
                            return False, None

            # Valida o novo_percentual_teletrabalho e novo_regime_execucacao isoladamente
            # ---------------------------------------
            if not (0 <= novo_percentual_teletrabalho <= 100.00):
                if retornar_lista_erros:
                    erros.append('Percentual de trabalho deve ser entre 0 e 100.')
                else:
                    return False, None
            if novo_regime_execucacao == self.TRABALHO_PRESENCIAL and novo_percentual_teletrabalho > 0:
                if retornar_lista_erros:
                    erros.append('Impossível informar regime de execução PRESENCIAL com algum percentual de trabalho informado.')
                else:
                    return False, None
            if novo_regime_execucacao == self.TRABALHO_TELETRABALHO_PARCIAL and novo_percentual_teletrabalho == 100.00:
                if retornar_lista_erros:
                    erros.append('Impossível informar regime de execução TELETRABALHO PARCIAL com algum percentual de trabalho de 100%.')
                else:
                    return False, None
            if novo_regime_execucacao == self.TRABALHO_TELETRABALHO_INTEGRAL and novo_percentual_teletrabalho != 100.0:
                if retornar_lista_erros:
                    erros.append('Impossível informar regime de execução TELETRABALHO INTEGRAL com percentual diferente de 100%.')
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    # ===============================================
    # EDITAR CRONOGRAMA DE TRABALHO PRESENCIAL - PIT
    # ===============================================
    def pode_cadastrar_trabalho_presencial(self, user):
        return self.pode_editar(user)

    def pode_editar_trabalho_presencial(self, user):
        return self.pode_editar(user)

    def pode_remover_trabalho_presencial(self, user):
        return self.pode_editar(user)

    # ===============================================
    # EDITAR CRONOGRAMA ATENDIMENTO TELETRABALHO - PIT
    # ===============================================
    def pode_cadastrar_atendimento_teletrabalho(self, user):
        return self.pode_editar(user)

    def pode_editar_atendimento_teletrabalho(self, user):
        return self.pode_editar(user)

    def pode_remover_atendimento_teletrabalho(self, user):
        return self.pode_editar(user)

    def pode_cancelar_em_lote_edicao_atendimento_teletrabalho(self, user):
        if not self.pode_editar(user):
            return False

        return PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self, original__isnull=False, alterado=True, homologado=False).exists()

    def pode_cancelar_em_lote_edicao_trabalho_presencial(self, user):
        if not self.pode_editar(user):
            return False

        return PlanoIndividualTrabalhoPresencial.objects.filter(pit=self, original__isnull=False, alterado=True, homologado=False).exists()

    # ===============================================
    # EDITAR PLANEJAMENTO - ENTREGAS - PIT
    # ===============================================
    def pode_cadastrar_entrega(self, user):
        return self.pode_editar(user)

    @staticmethod
    def existe_entrega_que_pode_ser_removida_no_pit(user, entregas):
        return any(ent.pode_remover_entrega(user) for ent in entregas)

    # ===============================================
    # COPIAR PIT
    # ===============================================

    def _get_pits_copiaveis_base(self, user):
        pits = PlanoIndividualTrabalho.objects.exclude(id=self.id)
        pits = pits.filter(adesao=self.adesao)
        pits = pits.exclude(situacao__in=[PlanoIndividualTrabalho.AGUARDANDO_PARECER, PlanoIndividualTrabalho.CANCELADO])
        pits = pits.filter(data_fim__lt=self.data_fim)

        ids_pit_exclude = []
        for pit in pits:
            if pit.pode_solicitar_aprovacao_homologacao_pit(user, retornar_lista_erros=False)[0]:
                ids_pit_exclude.append(pit.id)

            # Um PIT origem sem entregas elegíveis para RIT não deve aparecer para cópia.
            if not pit.get_entregas_pit_para_rit().exists():
                ids_pit_exclude.append(pit.id)

        return pits.exclude(id__in=ids_pit_exclude)

    def get_pits_podem_ser_copiados_para_este(self, user):
        pits = self._get_pits_copiaveis_base(user)
        return pits.order_by('-data_fim')

    def get_pits_podem_ser_copiados_mesmo_pes(self, user):
        pits = self._get_pits_copiaveis_base(user)
        return pits.filter(periodo_pit_rit__periodo_pes=self.periodo_pit_rit.periodo_pes).order_by('data_fim')

    def get_pits_podem_ser_copiados_outro_pes(self, user):
        pits = self._get_pits_copiaveis_base(user)
        return pits.exclude(periodo_pit_rit__periodo_pes=self.periodo_pit_rit.periodo_pes).order_by(
            '-periodo_pit_rit__periodo_pes__data_fim', '-data_fim'
        )

    def pode_receber_copia(self, user):
        if not (self.pode_editar(user)):
            return False
        if self.situacao != PlanoIndividualTrabalho.EM_CADASTRO:
            return False
        return not self.se_pit_ja_foi_homologado_ao_menos_uma_vez()

    ACAO_COPIA_SUBSTITUIR = 'substituir'
    ACAO_COPIA_SUBSTITUIR_READEQUAR_CH = 'substituir_readequar_ch'
    ACAO_COPIA_ADICIONAR = 'adicionar'

    def copiar_outro_pit_para_este(self, pit_origem, acao_copia, user, mapa_entregas_pes=None):
        pit_destino = self
        acao_copia = acao_copia or self.ACAO_COPIA_SUBSTITUIR

        pess_aptos_relacionados = pit_destino.get_pess_aptos_relacionados()

        if pess_aptos_relacionados:
            entregas_a_copiar = pit_origem.get_entregas_pit_para_rit()
            if mapa_entregas_pes is None:
                entregas_a_copiar = entregas_a_copiar.filter(entrega_pes__pes__in=pess_aptos_relacionados)

            entregas_pit_pit_destino = pit_destino.get_entregas_pit()

            entregas_pes_destino = {}
            if mapa_entregas_pes:
                entregas_pes_destino = {
                    entrega_pes.id: entrega_pes
                    for entrega_pes in PlanoEntregasSetorialEntregas.objects.filter(
                        id__in=mapa_entregas_pes.values(), pes__in=pess_aptos_relacionados
                    )
                }

            entregas_para_criar = []
            for entrega_a_copiar in entregas_a_copiar:
                entrega_pes_destino = entrega_a_copiar.entrega_pes
                if mapa_entregas_pes is not None:
                    entrega_pes_destino_id = mapa_entregas_pes.get(entrega_a_copiar.id)
                    if not entrega_pes_destino_id:
                        continue
                    entrega_pes_destino = entregas_pes_destino.get(entrega_pes_destino_id)
                    if not entrega_pes_destino:
                        continue
                entregas_para_criar.append((entrega_a_copiar, entrega_pes_destino))

            substituir_entregas_atuais = acao_copia in [self.ACAO_COPIA_SUBSTITUIR, self.ACAO_COPIA_SUBSTITUIR_READEQUAR_CH]
            if substituir_entregas_atuais:
                for entrega_remover in entregas_pit_pit_destino:
                    if entrega_remover.pode_remover_entrega(user):
                        entrega_remover.delete()

            fator_readequacao = Decimal(1)
            if acao_copia == self.ACAO_COPIA_SUBSTITUIR_READEQUAR_CH and entregas_para_criar:
                ch_destino = pit_destino.calcular_pit_tempo_previsto(salvar_dado=False) or pit_destino.tempo_previsto
                total_planejado_copiado = sum((entrega.tempo_planejado or Decimal(0) for entrega, _ in entregas_para_criar), Decimal(0))
                if ch_destino and total_planejado_copiado:
                    fator_readequacao = Decimal(ch_destino) / Decimal(total_planejado_copiado)

            for entrega_a_copiar, entrega_pes_destino in entregas_para_criar:
                if acao_copia == self.ACAO_COPIA_ADICIONAR:
                    ja_existe = PlanoIndividualTrabalhoEntregas.objects.filter(
                        pit=pit_destino,
                        entrega_pes=entrega_pes_destino,
                        titulo=entrega_a_copiar.titulo,
                        cancelado=False,
                    ).exists()
                    if ja_existe:
                        continue

                entrega_copia = PlanoIndividualTrabalhoEntregas()
                entrega_copia.pit = pit_destino
                entrega_copia.entrega_pes = entrega_pes_destino
                entrega_copia.titulo = entrega_a_copiar.titulo
                entrega_copia.descricao = entrega_a_copiar.descricao
                # O prazo deve ser redefinido no PIT destino para respeitar o novo período.
                entrega_copia.data_prazo = None
                tempo_planejado_copia = entrega_a_copiar.tempo_planejado
                if acao_copia == self.ACAO_COPIA_SUBSTITUIR_READEQUAR_CH:
                    tempo_planejado_copia = (tempo_planejado_copia or Decimal(0)) * fator_readequacao
                entrega_copia.tempo_planejado = tempo_planejado_copia
                entrega_copia.cancelado = False
                entrega_copia.save()

    # ===============================================
    # CALCULOS DO PIT
    # ===============================================

    # Auxiliares
    # ----------------------
    def get_setores_envolvidos(self):
        return PitSetores.objects.filter(pit=self).select_related('pes')

    def get_setores_envolvidos_nao_habilitado(self):
        setores = self.get_setores_envolvidos().values_list('setor_id', flat=True)
        setores = get_setores_pgd().filter(id__in=setores)
        ids = []
        if setores:
            for s in setores:
                if not SetorHabilitacao.setor_estah_habilitado(s):
                    ids.append(s.id)
        return setores.filter(id__in=ids)

    def existe_setores_envolvidos_nao_habilitado(self):
        # Memoizado na instância: é o primeiro guarda de quase toda checagem de permissão do PIT/RIT,
        # e uma única tela chega a repetir a checagem dezenas de vezes. Invalidado por
        # invalidar_cache_setores_envolvidos().
        if '_existe_setores_envolvidos_nao_habilitado' not in self.__dict__:
            setores = self.get_setores_envolvidos().values_list('setor_id', flat=True)
            setores = get_setores_pgd().filter(id__in=setores)
            self.__dict__['_existe_setores_envolvidos_nao_habilitado'] = any(not SetorHabilitacao.setor_estah_habilitado(s) for s in setores)
        return self.__dict__['_existe_setores_envolvidos_nao_habilitado']

    def get_setores_envolvidos_sem_parecer_positivo_ou_sem_parecer(self, objeto_parecer):
        # objeto_parecer: PIT = 1, RIT = 2
        # Setores envolvidos do PIT que não tem ainda algum PitSolicitacaoAnaliseSetor.parece == True
        # - parecer positivo = PitSolicitacaoAnaliseSetor.parece == True
        ids_setores_envolvidos = self.get_setores_envolvidos().values_list('setor_id', flat=True)
        ids_setores_com_parecer_positivo = PitSolicitacaoAnaliseSetor.objects.filter(
            solicitacao__objeto_parecer=objeto_parecer, solicitacao__pit=self, setor_id__in=ids_setores_envolvidos, parecer=True
        ).values_list('setor_id', flat=True)
        return get_setores_pgd().filter(id__in=set(ids_setores_envolvidos).difference(set(ids_setores_com_parecer_positivo)))

    def get_setor_envolvido_apto_para_homologar(self):
        # Memoizado na instância. Invalidado por invalidar_cache_setores_envolvidos().
        if '_setor_envolvido_apto_para_homologar' not in self.__dict__:
            se = self.get_setores_envolvidos().filter(pode_homologar=True).first()
            self.__dict__['_setor_envolvido_apto_para_homologar'] = se.setor if se else None
        return self.__dict__['_setor_envolvido_apto_para_homologar']

    def invalidar_cache_setores_envolvidos(self):
        # Chamado sempre que os PitSetores desta instância são alterados.
        self.__dict__.pop('_existe_setores_envolvidos_nao_habilitado', None)
        self.__dict__.pop('_setor_envolvido_apto_para_homologar', None)

    def get_ultima_analise_de_homologacao_do_rit(self):
        # ultima analise de homologacao PIT que foi concluida
        ultima_solicitacao = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__pit=self,
                solicitacao__objeto_parecer=PitSolicitacaoAnalise.RIT,
                solicitacao__finalizado=True,
                parecer=True,
                tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
            )
            .order_by('-id')
            .first()
        )
        return ultima_solicitacao

    def get_primeira_analise_de_homologacao_do_pit(self):
        # primeira analise de homologacao PIT que foi concluida
        ultima_solicitacao = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__pit=self,
                solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
                solicitacao__finalizado=True,
                parecer=True,
                tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
            )
            .order_by('id')
            .first()
        )
        return ultima_solicitacao

    def get_ultima_analise_de_homologacao_do_pit(self):
        # ultima analise de homologacao PIT que foi concluida
        ultima_solicitacao = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__pit=self,
                solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
                solicitacao__finalizado=True,
                parecer=True,
                tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
            )
            .order_by('-id')
            .first()
        )
        return ultima_solicitacao

    def se_ultima_analise_de_homologacao_do_pit_foi_negativa(self):
        # ultima analise de homologacao PIT que foi concluida
        ultima_solicitacao = self.get_ultima_analise_de_homologacao_do_pit()
        # sabendo se oaprcer foi negativo
        return bool(ultima_solicitacao and ultima_solicitacao.parecer is False)

    def get_data_ultima_analise_de_homologacao_do_pit_positiva(self):
        # ultima analise de homologacao PIT que foi concluida
        ultima_solicitacao = self.get_ultima_analise_de_homologacao_do_pit()
        # sabendo se parecer foi positivo
        if ultima_solicitacao and ultima_solicitacao.parecer:
            return ultima_solicitacao.data_parecer
        return None

    def se_pit_ja_foi_homologado_ao_menos_uma_vez(self):
        ja_foi_homologado = PitSolicitacaoAnaliseSetor.objects.filter(
            solicitacao__pit=self,
            solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
            solicitacao__finalizado=True,
            parecer=True,
            tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
        ).exists()
        return ja_foi_homologado

    def get_ultimo_cancelamento_pit(self):
        ultimo_cancelamento_pit = (
            RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=self, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_CANCELADO)
            .order_by('-data')
            .first()
        )
        if ultimo_cancelamento_pit:
            return ultimo_cancelamento_pit.data
        return None

    def get_cadastro_pit(self):
        cad = (
            RegistroAcaoPlanoIndividualTrabalho.objects.filter(pit=self, tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_EM_CADASTRO)
            .order_by('-data')
            .first()
        )
        if cad:
            return cad.data
        return None

    @staticmethod
    def get_pits_foram_homologados_ao_menos_uma_vez_por_pes(pes):
        # ultima analise de homologacao PIT que foi concluida
        ids_pit = PitSolicitacaoAnaliseSetor.objects.filter(
            solicitacao__pit__periodo_pit_rit__periodo_pes=pes.periodo_pes,
            setor=pes.setor,
            solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
            solicitacao__finalizado=True,
            parecer=True,
            tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
        ).values_list('solicitacao__pit_id')

        return PlanoIndividualTrabalho.objects.filter(id__in=ids_pit)

    @staticmethod
    def get_pits_foram_homologados_ao_menos_uma_vez():
        # ultima analise de homologacao PIT que foi concluida
        ids_pit = PitSolicitacaoAnaliseSetor.objects.filter(
            solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
            solicitacao__finalizado=True,
            parecer=True,
            tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
        ).values_list('solicitacao__pit_id')

        return PlanoIndividualTrabalho.objects.filter(id__in=ids_pit)

    @staticmethod
    def get_pits_por_pes(pes, apenas_setor_pode_homologar=False):
        pits = PlanoIndividualTrabalho.objects.exclude(situacao=PlanoIndividualTrabalho.CANCELADO)
        if apenas_setor_pode_homologar:
            pits = pits.filter(periodo_pit_rit__periodo_pes=pes.periodo_pes, setor_pode_homologar_pit_rit=pes.setor)
        else:
            pits = pits.filter(id__in=PitSetores.objects.filter(pes=pes).values_list('pit_id', flat=True))
        return pits.select_related('periodo_pit_rit', 'adesao__servidor__pessoa_fisica')

    @staticmethod
    def get_pits_por_setor(setor):
        return PlanoIndividualTrabalho.objects.filter(id__in=PitSetores.objects.filter(setor=setor).values_list('pit_id', flat=True)).exclude(
            situacao=PlanoIndividualTrabalho.CANCELADO
        )

    def get_dados_horas_ponto_servidor(self):
        data_ini = self.data_inicio
        data_fim = self.data_fim
        return obter_dados_horas_ponto_servidor(self.adesao.servidor, data_ini=data_ini, data_fim=data_fim)

    def get_data_fim_calculada_pit(self):
        data_fim = self.periodo_pit_rit.data_fim
        if self.adesao.data_desligamento_efeitos_a_partir_de and self.adesao.data_desligamento_efeitos_a_partir_de <= data_fim:
            data_fim = self.adesao.data_desligamento_efeitos_a_partir_de - relativedelta(days=1)
            if self.data_inicio > data_fim:
                data_fim = self.periodo_pit_rit.data_fim
        return data_fim

    # Calculos
    # ----------------------
    def pode_calcular_pit(self):
        pode_pelo_pit = self.situacao in self.SITUACOES_PODE_CALCULAR_PIT
        pode_pelo_rit = self.situacao_rit in self.SITUACOES_RIT_PODE_CALCULAR_PIT if self.situacao_rit else True
        return pode_pelo_pit and pode_pelo_rit

    def calcular_pit(self):
        if self.pode_calcular_pit():
            self.calcular_pit_horas()
            self.calcular_pit_data_fim()
            self.calcular_pit_execucao()

    def calcular_pit_setores_envolvidos(self, apenas_consulta=False):
        # Apaga dados anteriores antes do recalculo
        if not apenas_consulta:
            self.get_setores_envolvidos().delete()
            self.setor_pode_homologar_pit_rit = None
            self.save()

        setor_pode_homologar, pes_apto_no_periodo, setores_das_entregas = None, None, None

        if considerar_auditoria_centralizada() and servidor_eh_auditor(self.adesao.servidor):
            setor_pode_homologar = get_setor_auditoria_centralizada()
            pes_apto_no_periodo = PlanoEntregasSetorial.get_pes_apto_relacionado_periodo_pit_rit_setor(
                self.periodo_pit_rit, setor_pode_homologar
            ).last()
            if not apenas_consulta:
                ps = PitSetores()
                ps.pit = self
                ps.setor = setor_pode_homologar
                ps.pode_homologar = True
                ps.pes = pes_apto_no_periodo
                ps.save()

                self.setor_pode_homologar_pit_rit = setor_pode_homologar
                self.save()
        else:
            # Insere, no mínimo, o setor atual do servidor considerando a epoca do PIT
            setor_pode_homologar = get_setor_servidor_no_periodo(self.adesao.servidor, self.data_inicio, self.data_fim)
            #
            pes_apto_no_periodo = PlanoEntregasSetorial.get_pes_apto_relacionado_periodo_pit_rit_setor(
                self.periodo_pit_rit, setor_pode_homologar
            ).last()

            setores_das_entregas = (
                PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, entrega_pes__isnull=False)
                .exclude(entrega_pes__pes=pes_apto_no_periodo, cancelado=True)
                .distinct('entrega_pes__pes__setor')
                .select_related('entrega_pes__pes__setor')
            )

            if not apenas_consulta:
                ps = PitSetores()
                ps.pit = self
                ps.setor = setor_pode_homologar
                ps.pode_homologar = True
                ps.pes = pes_apto_no_periodo
                ps.save()
                #
                self.setor_pode_homologar_pit_rit = setor_pode_homologar
                self.save()
                #
                if setor_pode_homologar and pes_apto_no_periodo:
                    if setores_das_entregas:
                        for se in setores_das_entregas:
                            if not PitSetores.objects.filter(pit=self, setor=se.entrega_pes.pes.setor).exists():
                                ps = PitSetores()
                                ps.pit = self
                                ps.setor = se.entrega_pes.pes.setor
                                ps.pode_homologar = False
                                ps.pes = se.entrega_pes.pes
                                ps.save()

        if not apenas_consulta:
            self.invalidar_cache_setores_envolvidos()

        return setor_pode_homologar, pes_apto_no_periodo, setores_das_entregas

    def calcular_pit_tempo_previsto(self, salvar_dado=False):
        if utilizar_integracao_com_ponto():
            tempo_previsto_calculado = get_ch_prevista_servidor_periodo(self.adesao.servidor, self.data_inicio, self.data_fim)
            if salvar_dado:
                self.tempo_previsto = tempo_previsto_calculado
                self.save()
            return tempo_previsto_calculado
        return Decimal(0)

    def calcular_pit_horas(self):
        # -------------------
        # Zerando
        # -------------------
        self.tempo_previsto = Decimal(0)

        self.tempo_planejado_vinculados_proprio = Decimal(0)
        self.tempo_planejado_vinculados_outros = Decimal(0)
        self.tempo_planejado_nao_vinculados = Decimal(0)
        self.tempo_planejado_total = Decimal(0)
        self.percentual_tempo_planejado_vinculados_proprio = Decimal(0)
        self.percentual_tempo_planejado_vinculados_outros = Decimal(0)
        self.percentual_tempo_planejado_nao_vinculados = Decimal(0)
        self.tempo_trabalho_presencial = Decimal(0)
        self.tempo_atendimento_teletrabalho = Decimal(0)

        self.tempo_executado_vinculados_proprio = Decimal(0)
        self.tempo_executado_vinculados_outros = Decimal(0)
        self.tempo_executado_nao_vinculados = Decimal(0)
        self.tempo_executado_total = Decimal(0)
        self.tempo_executado_total_teletrabalho = Decimal(0)
        self.percentual_tempo_executado_vinculados_proprio = Decimal(0)
        self.percentual_tempo_executado_vinculados_outros = Decimal(0)
        self.percentual_tempo_executado_nao_vinculados = Decimal(0)
        self.percentual_tempo_executado_total_teletrabalho = Decimal(0)

        # -------------------
        # Calculos e dados inciais
        # -------------------
        self.tempo_previsto = self.calcular_pit_tempo_previsto(salvar_dado=False)
        setor_para_homologar = self.get_setor_envolvido_apto_para_homologar()
        #
        # Lista as entregas para cálculo das horas
        # - Entram no cálculo
        #   - Tem PES vinculado + Nao Tem PES vinculado
        # - São excluídas
        #   - Exceto as Canceladas no PES
        #   - Exceto as Canceladas no PIT
        #
        # exclude_entregas_pit_ids = list(PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, entrega_pes__cancelado=True).values_list('id', flat=True))
        # exclude_entregas_pit_ids.extend(list(PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, cancelado=True).values_list('id', flat=True)))
        # entregas_pit = PlanoIndividualTrabalhoEntregas.objects.filter(pit=self).exclude(id__in=exclude_entregas_pit_ids).only('tempo_planejado')
        # entregas_pit = self.get_entregas_para_analise_aprovacao_homologacao(entregas_pit=entregas_pit)
        #
        exclude_entregas_pit_ids = []
        #
        exclude_entregas_canceladas_pes = list(
            PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, entrega_pes__cancelado=True).values_list('id', flat=True)
        )
        #
        exclude_entregas_canceladas_pit = list(PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, cancelado=True).values_list('id', flat=True))
        exclude_entregas_canceladas_pit_originais = list(
            PlanoIndividualTrabalhoEntregas.objects.filter(pit=self, id__in=exclude_entregas_canceladas_pit).values_list('original_id', flat=True)
        )
        #
        exclude_entregas_pit_ids.extend(exclude_entregas_canceladas_pes)
        exclude_entregas_pit_ids.extend(exclude_entregas_canceladas_pit)
        exclude_entregas_pit_ids.extend(exclude_entregas_canceladas_pit_originais)
        #
        entregas_pit = PlanoIndividualTrabalhoEntregas.objects.filter(pit=self).exclude(id__in=exclude_entregas_pit_ids)
        entregas_pit = self.get_entregas_para_analise_aprovacao_homologacao(entregas_pit=entregas_pit)

        # -------------------
        # Calculando as horas e qtd dos cronogramas
        # -------------------
        horas = (
            PlanoIndividualTrabalhoPresencial.objects.filter(pit=self)
            .annotate(h=ExpressionWrapper(F('hora_final') - F('hora_inicio'), output_field=DurationField()))
            .aggregate(v=Sum('h'))
            .get('v')
        )
        if horas:
            self.tempo_trabalho_presencial = horas.total_seconds()
        horas = (
            PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self)
            .annotate(h=ExpressionWrapper(F('hora_final') - F('hora_inicio'), output_field=DurationField()))
            .aggregate(v=Sum('h'))
            .get('v')
        )
        if horas:
            self.tempo_atendimento_teletrabalho = horas.total_seconds()

        if entregas_pit:
            # -------------------
            # Calculando PIT
            # -------------------

            # Vinculados a entregas da própria unidade (setores) do servidor
            # - Vinculados ao setor do servidor
            self.tempo_planejado_vinculados_proprio = gv(
                entregas_pit.filter(entrega_pes__pes__setor=setor_para_homologar).aggregate(v=Sum('tempo_planejado'))
            )

            # Vinculados a entregas de outras unidades (setores) da instituição
            # - Vinculados a outros setores
            self.tempo_planejado_vinculados_outros = gv(
                entregas_pit.filter(entrega_pes__isnull=False)
                .exclude(entrega_pes__pes__setor=setor_para_homologar)
                .aggregate(v=Sum('tempo_planejado'))
            )

            # Não vinculados diretamente a entregas da própria unidade, mas necessários ao adequado funcionamento administrativo ou à gestão de equipes e entregas
            # - Não vinculados a nenhuma entrega
            self.tempo_planejado_nao_vinculados = gv(entregas_pit.filter(entrega_pes__isnull=True).aggregate(v=Sum('tempo_planejado')))

            # Total planejado
            self.tempo_planejado_total = gv(entregas_pit.aggregate(v=Sum('tempo_planejado')))

            # Calculando percentuais
            # % de horas dedicadas a entregas do próprio setor
            # % de horas dedicadas a entregas de outros setores
            # % de horas dedicadas a entregas não vinculadas a PES
            if self.tempo_planejado_vinculados_proprio:
                self.percentual_tempo_planejado_vinculados_proprio = round(
                    ((self.tempo_planejado_vinculados_proprio / self.tempo_planejado_total) * 100), 2
                )
            if self.tempo_planejado_vinculados_outros:
                self.percentual_tempo_planejado_vinculados_outros = round(
                    ((self.tempo_planejado_vinculados_outros / self.tempo_planejado_total) * 100), 2
                )
            if self.tempo_planejado_nao_vinculados:
                self.percentual_tempo_planejado_nao_vinculados = round(((self.tempo_planejado_nao_vinculados / self.tempo_planejado_total) * 100), 2)

            # -------------------
            # Calculando RIT
            # -------------------
            q_basico = Q(entrega_pit__pit=self, entrega_pit__cancelado=False)
            q_entregas_com_pes_ou_sem_pes = Q(entrega_pit__entrega_pes__cancelado=False) | Q(entrega_pit__entrega_pes__isnull=True)
            entregas_rit = RelatorioIndividualTrabalho.objects.filter(q_basico, q_entregas_com_pes_ou_sem_pes).only('tempo_executado')
            if entregas_pit:
                # Vinculados a entregas da própria unidade (setores)
                # - Vinculados ao setor do servidor
                self.tempo_executado_vinculados_proprio = gv(
                    entregas_rit.filter(entrega_pit__entrega_pes__pes__setor=setor_para_homologar).aggregate(v=Sum('tempo_executado'))
                )

                # Vinculados a entregas de outras unidades (setores), órgãos ou entidades diversos
                # - Vinculados a outros setores
                self.tempo_executado_vinculados_outros = gv(
                    entregas_rit.filter(entrega_pit__entrega_pes__isnull=False)
                    .exclude(entrega_pit__entrega_pes__pes__setor=setor_para_homologar)
                    .aggregate(v=Sum('tempo_executado'))
                )

                # Não vinculados diretamente a entregas da própria unidade, mas necessários ao adequado funcionamento administrativo ou à gestão de equipes e entregas
                # - Não vinculados a nenhuma entrega
                self.tempo_executado_nao_vinculados = gv(
                    entregas_rit.filter(entrega_pit__entrega_pes__isnull=True).aggregate(v=Sum('tempo_executado'))
                )

                # Total executado
                self.tempo_executado_total = gv(entregas_rit.aggregate(v=Sum('tempo_executado')))
                self.tempo_executado_total_teletrabalho = gv(entregas_rit.aggregate(v=Sum('tempo_executada_em_teletrabalho')))

                # Calculando percentuais
                # % de horas dedicadas a entregas do próprio setor
                # % de horas dedicadas a entregas de outros setores
                # % de horas dedicadas a entregas não vinculadas a PES
                if self.tempo_executado_vinculados_proprio:
                    self.percentual_tempo_executado_vinculados_proprio = round(
                        ((self.tempo_executado_vinculados_proprio / self.tempo_executado_total) * 100), 2
                    )
                if self.tempo_executado_vinculados_outros:
                    self.percentual_tempo_executado_vinculados_outros = round(
                        ((self.tempo_executado_vinculados_outros / self.tempo_executado_total) * 100), 2
                    )
                if self.tempo_executado_nao_vinculados:
                    self.percentual_tempo_executado_nao_vinculados = round(
                        ((self.tempo_executado_nao_vinculados / self.tempo_executado_total) * 100), 2
                    )

                # % de teletrabalho
                if self.tempo_executado_total_teletrabalho:
                    self.percentual_tempo_executado_total_teletrabalho = round(
                        ((self.tempo_executado_total_teletrabalho / self.tempo_executado_total) * 100), 2
                    )

        self.save()

    def calcular_pit_data_fim(self):
        self.data_fim = self.get_data_fim_calculada_pit()
        self.save()

    def calcular_pit_execucao(self):
        if self.situacao_rit != PlanoIndividualTrabalho.EM_CADASTRO_RIT and not (self.se_pit_ja_foi_homologado_ao_menos_uma_vez()):
            self.rit_em_execucao = False
            self.save()
        else:
            # Se um RIT está em execução
            # - Se PIT foi homologado alguma vez E
            # - Se RIT não está homologado E
            # - Se o período de execução dele está vigente OU Se existe alguma entrega no RIT
            self.rit_em_execucao = self.situacao_rit != PlanoIndividualTrabalho.HOMOLOGADO_RIT and self.data_inicio <= get_datetime_now().date()

            # Calculos de cada entrega
            entregas_pit = self.get_entregas_pit()
            exclude_entregas_pit_ids = []
            exclude_entregas_canceladas_pes = list(entregas_pit.filter(entrega_pes__cancelado=True).values_list('id', flat=True))
            exclude_entregas_canceladas_pit = list(entregas_pit.filter(cancelado=True).values_list('id', flat=True))
            exclude_entregas_pit_ids.extend(exclude_entregas_canceladas_pes)
            exclude_entregas_pit_ids.extend(exclude_entregas_canceladas_pit)
            # As somas do RIT vêm anotadas para não repetir dois aggregates por entrega
            entregas_pit = entregas_pit.exclude(id__in=exclude_entregas_pit_ids).annotate(
                soma_tempo_executado_rit=Sum('relatorioindividualtrabalho__tempo_executado'),
                soma_quantidade_progresso_rit=Sum('relatorioindividualtrabalho__quantidade_progresso'),
            )
            for ent in entregas_pit:
                tempo_executado = gv({'v': ent.soma_tempo_executado_rit})
                # - Soma execução de cada entrega do PIT com base no RIT (seja percentual ou quantidade)
                qtd_executado = gv({'v': ent.soma_quantidade_progresso_rit}) if ent.entrega_pes_id else ent.qtd_executado
                # - Tempo executado de cada entrega do PIT com base no RIT
                if (ent.tempo_executado, ent.qtd_executado) != (tempo_executado, qtd_executado):
                    ent.tempo_executado = tempo_executado
                    ent.qtd_executado = qtd_executado
                    ent.save()

            # Calculos gerais
            # - Percentual do tempo já executado
            self.percentual_tempo_executado_total = Decimal(0)
            if self.tempo_executado_total and self.tempo_planejado_total:
                self.percentual_tempo_executado_total = round(((self.tempo_executado_total / self.tempo_planejado_total) * 100), 2)

            self.save()

    def calcular_pit_situacao_pos_homologacao(self):
        tem_alguma_entrega = self.get_entregas_pit().filter(original__isnull=True).exists()

        if self.se_pit_ja_foi_homologado_ao_menos_uma_vez() and tem_alguma_entrega and self.situacao == PlanoIndividualTrabalho.EM_CADASTRO:
            tem_dados_basicos_nao_homologado = PlanoIndividualTrabalhoCopia.objects.filter(original=self).exists()
            tem_trabalho_presencial_nao_homologado = (
                PlanoIndividualTrabalhoPresencial.objects.filter(pit=self)
                .filter(Q(original__isnull=False, homologado=False, alterado=True) | Q(original__isnull=True, homologado=False))
                .exists()
            )
            tem_trabalho_atend_teletrabalho_nao_homologado = (
                PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self)
                .filter(Q(original__isnull=False, homologado=False, alterado=True) | Q(original__isnull=True, homologado=False))
                .exists()
            )
            tem_entrega_nao_homologado = self.get_entregas_pit().filter(homologado=False).exists()

            precisa_de_homologacao = (
                tem_dados_basicos_nao_homologado
                or tem_trabalho_presencial_nao_homologado
                or tem_trabalho_atend_teletrabalho_nao_homologado
                or tem_entrega_nao_homologado
            )
            if not precisa_de_homologacao:
                self.situacao = PlanoIndividualTrabalho.HOMOLOGADO
                self.save()

        return None

    # ===============================================
    # APROVAÇÃO E HOMOLOGAÇÃO - PIT
    # ===============================================
    def deve_verificar_ponto(self):
        if utilizar_integracao_com_ponto() and validar_ponto_antes_primeiro_pit_adesao():
            # Só deve verificar o ponto do servidor deste pit se
            # - Se for primeiro PIT nao cancelado dessa adesao ao PGD
            # - E se essa eh primeira submissao deste pit nessa adesao
            primeiro_pit_adesao = PlanoIndividualTrabalho.get_primeiro_pit_adesao(adesao=self.adesao)

            if primeiro_pit_adesao and primeiro_pit_adesao == self:
                return not RegistroAcaoPlanoIndividualTrabalho.objects.filter(
                    tipo=RegistroAcaoPlanoIndividualTrabalho.TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, pit=primeiro_pit_adesao
                ).exists()
            return False
        return False

    def exige_cronograma_trabalho_presencial(self):
        # Se o regime de execução for TRABALHO_TELETRABALHO_PARCIAL ou TRABALHO_PRESENCIAL
        return bool(
            self.regime_execucacao in [PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_PARCIAL, PlanoIndividualTrabalho.TRABALHO_PRESENCIAL]
            and not PlanoIndividualTrabalhoPresencial.get_horarios_agrupado_por_semana(self)
        )

    def analisa_aspectos_principais_pode_solicitar_aprovacao_homologacao_pit(self, user, retornar_lista_erros=False):
        # Se o servidor pode solicitar aprov e homolog de um Pit

        erros = []

        if not self.pode_editar(user):
            if retornar_lista_erros:
                erros.append(f'Este {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} não pode ser editado por você.')
            else:
                return False, None

        # Pede os dados básicos
        if not self.data_inicio or not self.regime_execucacao:
            if retornar_lista_erros:
                erros.append('É necessário cadastrar os dados básicos.')
            else:
                return False, None

        # --------------------------------------
        # Valida os dados
        # --------------------------------------

        # 1 - Pede trabalho presencial
        # -------------------------------------
        # Se o regime de execução for TRABALHO_TELETRABALHO_PARCIAL ou TRABALHO_PRESENCIAL
        if self.exige_cronograma_trabalho_presencial():
            if retornar_lista_erros:
                erros.append(
                    'É necessário cadastrar o cronograma de trabalho presencial para quem estiver em "Teletrabalho parcial" OU "Presencial".'
                )
            else:
                return False, None

        # 2 - Pede atendimento teletrabalho
        # -------------------------------------
        # Se o regime de execução for TRABALHO_TELETRABALHO_PARCIAL ou TRABALHO_TELETRABALHO_INTEGRAL
        if self.regime_execucacao in [
            PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_PARCIAL,
            PlanoIndividualTrabalho.TRABALHO_TELETRABALHO_INTEGRAL,
        ] and not PlanoIndividualTrabalhoAtendimento.get_horarios_agrupado_por_semana(self):
            if retornar_lista_erros:
                erros.append(
                    'É necessário cadastrar o cronograma de atendimento em teletrabalho para quem estiver em "Teletrabalho parcial" OU "Teletrabalho integral".'
                )
            else:
                return False, None

        # 3 - Entregas
        # -------------------------------------
        entregas_para_analise_aprovacao_homologacao = self.get_entregas_para_analise_aprovacao_homologacao()
        existe_alguma_entrega = self.get_entregas_pit().filter(original__isnull=True).exists()

        if not existe_alguma_entrega:
            if retornar_lista_erros:
                erros.append('É necessário cadastrar, no mínimo, uma entrega.')
            else:
                return False, None

        if entregas_para_analise_aprovacao_homologacao:
            # PIT tiver algum setor envolvido E deve ter, no mínimo, uma entrega cadastrada
            pit_setores_envolvidos = self.get_setores_envolvidos().exists()
            entregas_cadastradas = entregas_para_analise_aprovacao_homologacao.exists()
            if not pit_setores_envolvidos or not entregas_cadastradas:
                if retornar_lista_erros:
                    erros.append('É necessário cadastrar, no mínimo, uma entrega.')
                else:
                    return False, None

            setor_apto_para_homologar = self.get_setor_envolvido_apto_para_homologar()

            # PIT deve ter como setor envolvido ultimo setor do servidor considerando o periodo do PIT
            # - setor envolvido apto pra homologar
            # - o setor que vai homologar é o setor mais atual do servidor considerando o periodo deste pit
            entregas_cadastradas_vinculada_a_pes_principal = entregas_para_analise_aprovacao_homologacao.filter(
                entrega_pes__pes__setor=setor_apto_para_homologar, entrega_pes__cancelado=False, cancelado=False
            ).exists()
            if not setor_apto_para_homologar or not entregas_cadastradas_vinculada_a_pes_principal:
                if retornar_lista_erros:
                    erros.append(
                        f'É necessário cadastrar, no mínimo, uma entrega relacionada ao PES do seu setor. Considerando o período deste {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}. Esta entrega não pode estar relacionada a entrega de PES que e esteja cancelada. A entrega do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} também não pode estar cancelada. Verifique se neste PIT/RIT existe alguma entrega relacionada ao setor definido como "Principal e apto para homologar PIT/RIT" na seção "PESs relacionados"'
                    )
                else:
                    return False, None

            # Não pode se tiver alguma entrega cancelada no PES mas não tiver sido cancelada no PIT
            if entregas_para_analise_aprovacao_homologacao.filter(entrega_pes__isnull=False, entrega_pes__cancelado=True, cancelado=False).exists():
                if retornar_lista_erros:
                    erros.append('Não pode haver entregas não canceladas vinculas a entregas de PES que estejam canceladas.')
                else:
                    return False, None

            # Se tiver apenas entregas de PIT que estejam canceladas nao pode
            if (
                entregas_para_analise_aprovacao_homologacao.filter(entrega_pes__isnull=False).exists()
                and not entregas_para_analise_aprovacao_homologacao.filter(entrega_pes__isnull=False).exclude(cancelado=True).exists()
            ):
                if retornar_lista_erros:
                    erros.append(f'Não pode haver apenas entregas de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} que estejam canceladas.')
                else:
                    return False, None

            # Se tiver apenas com entregas de PES canceladas
            if (
                entregas_para_analise_aprovacao_homologacao.filter(entrega_pes__isnull=False).exists()
                and not entregas_para_analise_aprovacao_homologacao.filter(entrega_pes__isnull=False).exclude(entrega_pes__cancelado=True).exists()
            ):
                if retornar_lista_erros:
                    erros.append('Não pode haver apenas entregas de PES que estejam canceladas.')
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    def pode_solicitar_aprovacao_homologacao_pit(self, user, retornar_lista_erros=False):
        # Se o servidor pode solicitar aprov e homolog de um Pit

        estah_ok, erros = self.analisa_aspectos_principais_pode_solicitar_aprovacao_homologacao_pit(user, retornar_lista_erros)
        if not retornar_lista_erros and not estah_ok:
            return False, None
        erros = erros or []

        pit_setores_envolvidos = self.get_setores_envolvidos().exists()

        if self.existe_setores_envolvidos_nao_habilitado():
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado())
            else:
                return False, None

        if pit_setores_envolvidos:
            # Verifica se alterou algo ou inseriu algo novo após última homologação - Atuais e Novos
            tem_dados_basicos_nao_homologado = PlanoIndividualTrabalhoCopia.objects.filter(original=self).exists()
            tem_trabalho_presencial_nao_homologado = (
                PlanoIndividualTrabalhoPresencial.objects.filter(pit=self)
                .filter(Q(original__isnull=False, homologado=False, alterado=True) | Q(original__isnull=True, homologado=False))
                .exists()
            )
            tem_trabalho_atend_teletrabalho_nao_homologado = (
                PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self)
                .filter(Q(original__isnull=False, homologado=False, alterado=True) | Q(original__isnull=True, homologado=False))
                .exists()
            )
            tem_entrega_nao_homologado = self.get_entregas_pit().filter(homologado=False).exists()
            tem_existe_alguma_entrega = self.get_entregas_pit().filter(original__isnull=True).exists()
            pode_pelos_dados = False
            if tem_existe_alguma_entrega:
                pode_pelos_dados = (
                    tem_dados_basicos_nao_homologado
                    or tem_trabalho_presencial_nao_homologado
                    or tem_trabalho_atend_teletrabalho_nao_homologado
                    or tem_entrega_nao_homologado
                )
            #
            horas_a_homologadas_presencial = (
                self.qtd_trabalho_presencial_homologado != PlanoIndividualTrabalhoPresencial.objects.filter(pit=self, homologado=True).count()
            )
            horas_a_homologar_teletrabalho = (
                self.qtd_atendimento_teletrabalho_homologado != PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self, homologado=True).count()
            )
            pode_pelas_horas = False
            if self.exige_cronograma_trabalho_presencial():
                if horas_a_homologadas_presencial or horas_a_homologar_teletrabalho:
                    pode_pelas_horas = True
            else:
                if horas_a_homologar_teletrabalho:
                    pode_pelas_horas = True

            if not (pode_pelos_dados or pode_pelas_horas):
                if retornar_lista_erros:
                    if self.se_pit_ja_foi_homologado_ao_menos_uma_vez():
                        erros.append('Não existem dados novos ou alterações que justifiquem uma nova solicitação de Aprovação/Homologação.')
                    else:
                        erros.append('Não existem dados suficientes para uma solicitação de Aprovação/Homologação.')
                else:
                    return False, None

            if self.deve_recalcular_setores():
                if retornar_lista_erros:
                    erros.append('É necessário Recalcular setores e PES relacionados. Acesse o menu ações para recalcular.')
                else:
                    return False, None

        if erros:
            return False, erros

        return True, None

    def gerar_solicitacao_aprovacao_homologacao_pit_rit(self, objeto_parecer=1):
        # Gera uma solicitação de aprovação homologação para um PIT/RIT
        # objeto_parecer: PIT = 1, RIT = 2

        # Gera a solicitação relacionada ao PIT/RIT
        psa = PitSolicitacaoAnalise()
        psa.pit = self
        psa.objeto_parecer = objeto_parecer
        psa.save()

        # Calculando os prazos
        # - Servidor
        #   - Entrega do PIT pelo servidor para avaliação: até dia 25
        #     (conforme data_prazo_entrega_pit em PeriodoPitRit)
        #     - Mapeado pela data_envio do PitSolicitacaoAnalise
        #   - Entrega do RIT pelo servidor para avaliação: até dia 5 do mês seguinte ao do RIT
        #     (conforme data_prazo_entrega_rit em PeriodoPitRit)
        #     - Mapeado pela data_envio do PitSolicitacaoAnalise
        # - Chefe
        #   - Homologação do PIT: até fim do mês (conforme data_prazo_homologacao_pit em PeriodoPitRit)
        #     - Mapeado pela data_prazo_parecer em PitSolicitacaoAnaliseSetor
        #   - Homologação do RIT: até dia 15 do mês seguinte ao do RIT
        #     (conforme data_prazo_homologacao_rit em PeriodoPitRit)
        #     - Mapeado pela data_prazo_parecer em PitSolicitacaoAnaliseSetor
        #
        # Calculando "Entrega do PIT pelo servidor para avaliação" ou "Entrega do RIT pelo servidor para avaliação"
        data_prazo_envio = None
        if objeto_parecer == 1:
            data_prazo_envio = self.periodo_pit_rit.data_prazo_entrega_pit
        elif objeto_parecer == 2:
            data_prazo_envio = self.periodo_pit_rit.data_prazo_entrega_rit
        # Calculando "Homologação do PIT" ou "Homologação do RIT"
        data_prazo_homologacao = None
        if objeto_parecer == 1:
            data_prazo_homologacao = self.periodo_pit_rit.data_prazo_homologacao_pit
        elif objeto_parecer == 2:
            data_prazo_homologacao = self.periodo_pit_rit.data_prazo_homologacao_rit
        #
        psa.data_prazo_envio = data_prazo_envio
        psa.data_envio = get_datetime_now()
        psa.save()

        # Gera a solicitação para cada um dos setores
        # - Se for para RIT deve ter, no mínimo, uma entrega para o setor que vai abrir solicitação
        tem_pendencia_aprovacao = False
        tem_pendencia_homologacao = False
        setores_envolvidos = self.get_setores_envolvidos()
        if objeto_parecer == 2:
            setores_com_entregas_no_rit = self.get_entregas_rit().values_list('entrega_pit__entrega_pes__pes__setor__id', flat=True)
            setores_envolvidos = setores_envolvidos.filter(setor_id__in=setores_com_entregas_no_rit)
        for se in setores_envolvidos:
            psa_setor = PitSolicitacaoAnaliseSetor()
            psa_setor.solicitacao = psa
            psa_setor.setor = se.setor
            if se.pode_homologar:
                psa_setor.tipo_parecer = PitSolicitacaoAnaliseSetor.HOMOLOGACAO
                psa_setor.data_prazo_parecer = data_prazo_homologacao
                tem_pendencia_homologacao = True
            else:
                psa_setor.tipo_parecer = PitSolicitacaoAnaliseSetor.APROVACAO
                tem_pendencia_aprovacao = True
            psa_setor.save()
        psa.tem_pendencia_aprovacao = tem_pendencia_aprovacao
        psa.tem_pendencia_homologacao = tem_pendencia_homologacao
        psa.save()

        # Ajusta o PIT se for solicitacao para PIT
        if objeto_parecer == PitSolicitacaoAnalise.PIT:
            self.situacao = PlanoIndividualTrabalho.AGUARDANDO_PARECER
            self.save()

        # Ajusta o PIT se for solicitacao para RIT
        if objeto_parecer == PitSolicitacaoAnalise.RIT:
            self.situacao_rit = PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT
            self.save()

    def get_solicitacoes_aprovacao_homologacao(self, pit_rit=None):
        # pit_rit: PIT = 1, RIT = 2
        solicitacoes = PitSolicitacaoAnalise.objects.filter(pit=self)
        if pit_rit:
            solicitacoes = solicitacoes.filter(objeto_parecer=pit_rit)
        return solicitacoes

    def get_solicitacoes_aprovacao_homologacao_nao_finalizadas(self, pit_rit=None):
        return self.get_solicitacoes_aprovacao_homologacao(pit_rit=pit_rit).filter(finalizado=False)

    @staticmethod
    def get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(objeto_parecer, setores, servidores=None, setores_hoje=None, tipo_parecer=None):
        # ----------------------------------------------------
        # Lista solicitacoes que podem ser analisadas
        # - Obrigatoriamente fornecendo
        #   - objeto_parecer: PIT = 1, RIT = 2
        #   - setores: que eh chefe direto
        #   - servidores: chefes de setor de cada setor que o chefe é chefe indireto (subsetores)
        #   - setores_hoje: que é chefe hoje com descentes (obrigatório se passar servidores)
        #   - tipo_parecer: APROVACAO = 1, HOMOLOGACAO = 2
        # ----------------------------------------------------
        tem_pendencia_aprovacao = False
        tem_pendencia_homologacao = False
        if tipo_parecer:
            if tipo_parecer == PitSolicitacaoAnaliseSetor.APROVACAO:
                tem_pendencia_aprovacao = True
                tem_pendencia_homologacao = True
            elif tipo_parecer == PitSolicitacaoAnaliseSetor.HOMOLOGACAO:
                tem_pendencia_aprovacao = False
                tem_pendencia_homologacao = True

        if setores:
            # Lista as solicicitacoes que não tem parecer e considerando objeto_parecer, tipo_parecer, setores
            solicitacoes = PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__objeto_parecer=objeto_parecer, solicitacao__finalizado=False, parecer__isnull=True
            )

            querys = []
            querys.append(Q(setor__in=setores))
            if servidores and setores_hoje:
                querys.append(Q(solicitacao__pit__adesao__servidor__in=servidores) & Q(setor__in=setores_hoje))
            solicitacoes = solicitacoes.filter(reduce(operator.or_, querys))

            if tipo_parecer:
                solicitacoes = solicitacoes.filter(
                    tipo_parecer=tipo_parecer,
                    solicitacao__tem_pendencia_aprovacao=tem_pendencia_aprovacao,
                    solicitacao__tem_pendencia_homologacao=tem_pendencia_homologacao,
                )

            return solicitacoes

        return PitSolicitacaoAnaliseSetor.objects.none()

    def get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
        self, setores=None, servidores=None, setores_hoje=None, tipo_parecer=None
    ):
        return PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=1, setores=setores, setores_hoje=setores_hoje, servidores=servidores, tipo_parecer=tipo_parecer
        ).filter(solicitacao__pit=self)

    def pode_aprovar_pit(self, user):
        # Se o chefe pode aprovar um determinado PIT

        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        if self.situacao != PlanoIndividualTrabalho.AGUARDANDO_PARECER:
            return False

        # Se fui chefe no periodo ou Se sou chefe hoje
        """
        setores_chefe_no_periodo = setores_que_sou_chefe_no_periodo(self.data_inicio, self.data_fim, user.get_relacionamento())
        setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        setores = setores_chefe_no_periodo | setores_sou_chefe_hoje
        if not setores:
            return False
        """
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(user, self.data_inicio, self.data_fim, apenas_setores=True)
        if not setores:
            return False

        # Se tem solicitacao que pode ser atendida pelo chefe
        ids_pits = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        ).values_list('solicitacao__pit', flat=True)
        if self.id not in ids_pits:
            return False

        # Se servidor do PIT for da AUDGE só quem pode homologar é o chefe da AUDGE
        if considerar_auditoria_centralizada() and servidor_eh_auditor(self.adesao.servidor):
            if get_setor_auditoria_centralizada() not in setores:
                return False

        return True

    def pode_homologar_pit(self, user, considera_pendencia_geral_servidor_pgd=True):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        if self.situacao != PlanoIndividualTrabalho.AGUARDANDO_PARECER:
            return False

        setores, servidores = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(
            user, self.data_inicio, self.data_fim, apenas_setores=False
        )
        if not setores and not servidores:
            return False

        # Se tem solicitacao que pode ser atendida pelo chefe
        ids_pits = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, servidores=servidores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        ).values_list('solicitacao__pit', flat=True)
        if self.id not in ids_pits:
            return False

        # Se servidor do PIT for da AUDGE só quem pode homologar é o chefe da AUDGE
        if considerar_auditoria_centralizada() and servidor_eh_auditor(self.adesao.servidor):
            if get_setor_auditoria_centralizada() not in setores:
                return False

        pode_homologar = True
        if considera_pendencia_geral_servidor_pgd:
            pit_atual = PlanoIndividualTrabalho.get_pit_na_data(self.adesao.servidor, get_datetime_now().date(), permite_pit_aguardando_parecer=True)
            pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit_atual).first()
            pit_teste = pit_atual
            if pit_copia:
                pit_teste.regime_execucacao = pit_copia.regime_execucacao
                pit_teste.percentual_teletrabalho = pit_copia.percentual_teletrabalho
            if self == pit_atual:
                if get_pendencia_geral_servidor_pgd(self.adesao.servidor, pit_especifico=pit_teste):
                    pode_homologar = False

        return pode_homologar

    def pode_finalizar_aprovacao_homologacao_pit(self, retornar_lista_erros=False):
        # Consiferando que já rodou o pode_aprovar_pit e/ou pode_homologar_pit
        # Verifica se pode finalizar
        erros = []

        if self.existe_setores_envolvidos_nao_habilitado():
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado())
            else:
                return False, None

        # Não pode se tiver alguma entrega cancelada no PES mas não tiver sido canceda no PIT
        if (
            self.get_entregas_para_analise_aprovacao_homologacao()
            .filter(entrega_pes__isnull=False, entrega_pes__cancelado=True, cancelado=False)
            .exists()
        ):
            if retornar_lista_erros:
                erros.append('Não pode haver entregas não canceladas vinculas a entregas de PES que estejam canceladas.')
            else:
                return False, None

        # Se tiver apenas entregas de PIT que estejam canceladas nao pode OU que tenha apenas com entregas de PES canceladas
        if not self.get_entregas_para_analise_aprovacao_homologacao().filter(entrega_pes__isnull=False).exclude(cancelado=True).exists():
            if retornar_lista_erros:
                erros.append(f'Não pode haver apenas entregas de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} que estejam canceladas.')
            else:
                return False, None

        # Se tiver apenas com entregas de PES canceladas
        if not self.get_entregas_para_analise_aprovacao_homologacao().filter(entrega_pes__isnull=False).exclude(entrega_pes__cancelado=True).exists():
            if retornar_lista_erros:
                erros.append('Não pode haver apenas entregas de PES que estejam canceladas.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def aprovar_pit(self, setores, servidor_parecer):
        # Solicitações de cada setor que serão aprovadas
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )

        # Solicitacao
        solicitacao_analise = solicitacoes[0].solicitacao

        # Sabendo se existe alguma solicitacao de aprovacao que vai ficar de fora dessa aprovacao por setor
        existe_solicitacoes_nao_serao_aprovadas = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao=solicitacao_analise, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO, parecer__isnull=True
            )
            .exclude(id__in=solicitacoes)
            .exists()
        )

        # Aprova
        for soa in solicitacoes:
            soa.parecer = True
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Se nao existem mais solictacoes de aprovacao pendentes para algum setor
        # - marca a analise com PitSolicitacaoAnalise.tem_pendencia_aprovacao = False
        # if not PitSolicitacaoAnaliseSetor.objects.filter(
        #    solicitacao__pit=self, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO, parecer__isnull=True
        # ).exists():
        #    solicitacao_analise.tem_pendencia_aprovacao = False
        #    solicitacao_analise.save()
        if not existe_solicitacoes_nao_serao_aprovadas:
            solicitacao_analise.tem_pendencia_aprovacao = False
            solicitacao_analise.save()

    def reprovar_pit(self, setores, servidor_parecer):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )
        solicitacao_analise = solicitacoes[0].solicitacao

        # Reprova
        for soa in solicitacoes:
            soa.parecer = False
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Finaliza a solicitacao
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # Atualiza situaco do PIT
        self.situacao = PlanoIndividualTrabalho.EM_CADASTRO
        self.save()

    def homologar_pit(self, setores, servidor_parecer):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        )
        solicitacao_analise = solicitacoes[0].solicitacao

        # --------------------------------------------
        # Finaliza a solicitacao de aprovação/homologação
        # --------------------------------------------
        for soa in solicitacoes:
            soa.parecer = True
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # --------------------------------------------
        # Homologa cada um dos itens do PIT e exclui as cópias
        # --------------------------------------------
        # Dados básicos
        # --------------------
        dados_basicos_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=self).first()
        if dados_basicos_copia:
            self.data_inicio = dados_basicos_copia.data_inicio
            self.regime_execucacao = dados_basicos_copia.regime_execucacao
            self.percentual_teletrabalho = dados_basicos_copia.percentual_teletrabalho
            self.save()
            PlanoIndividualTrabalhoCopia.objects.filter(original=self).delete()

        # Entregas
        # --------------------
        for o in self.get_entregas_pit().filter(original__isnull=True, homologado=True):
            copia = o.get_copia()
            if copia:
                id = o.id
                o = copia
                o.id = id
                o.original = None
                o.save()
        self.get_entregas_pit().filter(original__isnull=False).delete()
        self.get_entregas_pit().update(homologado=True)

        # Horarios de atendimento de teletrabalho
        # --------------------
        for o in PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self, original__isnull=True, homologado=True):
            copia = o.get_copia()
            if copia:
                id = o.id
                o = copia
                o.id = id
                o.original = None
                o.save()
        PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self, original__isnull=False).delete()
        PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self).update(homologado=True, alterado=False)

        # - Horarios de trabalho presencial
        # --------------------
        for o in PlanoIndividualTrabalhoPresencial.objects.filter(pit=self, original__isnull=True, homologado=True):
            copia = o.get_copia()
            if copia:
                id = o.id
                o = copia
                o.id = id
                o.original = None
                o.save()
        PlanoIndividualTrabalhoPresencial.objects.filter(pit=self, original__isnull=False).delete()
        PlanoIndividualTrabalhoPresencial.objects.filter(pit=self).update(homologado=True, alterado=False)

        # --------------------------------------------
        # Altera o PIT
        # --------------------------------------------
        situacao = PlanoIndividualTrabalho.HOMOLOGADO
        qtd_trabalho_presencial_homologado = PlanoIndividualTrabalhoPresencial.objects.filter(pit=self, homologado=True).count()
        qtd_atendimento_teletrabalho_homologado = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=self, homologado=True).count()
        #
        self.situacao = situacao
        self.qtd_trabalho_presencial_homologado = qtd_trabalho_presencial_homologado
        self.qtd_atendimento_teletrabalho_homologado = qtd_atendimento_teletrabalho_homologado
        self.situacao_rit = PlanoIndividualTrabalho.EM_CADASTRO_RIT
        self.save()
        #
        self.marcar_para_enviar_pela_api()

    def nao_homologar_pit(self, setores, servidor_parecer):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_pit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        )
        solicitacao_analise = solicitacoes[0].solicitacao

        # Homologa
        for soa in solicitacoes:
            soa.parecer = False
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Finaliza a solicitacao
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # Atualiza situaco do PIT
        self.situacao = PlanoIndividualTrabalho.EM_CADASTRO
        self.save()

    def deve_recalcular_setores(self):
        setor_pode_homologar, _, setores_das_entregas = self.calcular_pit_setores_envolvidos(apenas_consulta=True)

        # Confere se o setor que pode homologar calculado é diferente do que salvo
        setor_envolvido_pode_homologar = self.get_setores_envolvidos().filter(pode_homologar=True).first()
        if setor_envolvido_pode_homologar and setor_envolvido_pode_homologar.setor:
            setor_envolvido_pode_homologar = setor_envolvido_pode_homologar.setor
            if setor_pode_homologar and setor_envolvido_pode_homologar and (setor_pode_homologar != setor_envolvido_pode_homologar):
                return True

        # Confere se todos os setores das entregas foram salvos como setores envolvidos
        if setores_das_entregas:
            for se in setores_das_entregas:
                if not self.get_setores_envolvidos().filter(setor=se.entrega_pes.pes.setor).exists():
                    return True
            return any(not setores_das_entregas.filter(entrega_pes__pes__setor=se.setor).exists() for se in self.get_setores_envolvidos())

        return False

    # ===============================================
    # RIT
    # ===============================================
    def pode_visualizar_rit(self, user):
        # Se um determinado RIT pode ser visualizado

        relacionamento = user.get_relacionamento()
        eh_dono = self.adesao.servidor.pk == relacionamento.pk
        ids_setores_envolvidos = self.get_setores_envolvidos().values_list('setor_id', flat=True)
        eh_chefe_do_servidor = setores_que_sou_chefe_hoje(relacionamento).filter(pk__in=ids_setores_envolvidos).exists()

        if not self.se_pit_ja_foi_homologado_ao_menos_uma_vez() and not (eh_dono or eh_chefe_do_servidor):
            return False

        if eh_dono or eh_chefe_do_servidor:
            return True

        return bool(self.situacao == self.HOMOLOGADO and self.situacao_rit == self.HOMOLOGADO_RIT)

    def pode_cadastrar_entrega_rit(self, user, entrega_pit_id=None, valida_apenas_o_basico=False):
        # Verifica se um determinado RIT pode ser editado/cadastrado
        # --------------------------------------------------
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        # Quem
        # - Apenas servidor dono do PIT
        if self.adesao.servidor.pk != user.get_relacionamento().pk:
            return False

        # Situacao da adesão
        # - Adesão do PIT deve estar vigente ou desligada na carencia
        if not self.adesao.estah_vigente_ou_desligado_na_carencia:
            return False

        if not valida_apenas_o_basico:
            if self.existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(user)[0]:
                return False

        # Situação do RIT
        if self.situacao_rit != self.EM_CADASTRO_RIT:
            return False

        # Se pode para a entrega do pit (entrega_pit_id)
        r = True
        if entrega_pit_id and entrega_pit_id not in self.get_entregas_pit_para_rit().values_list('id', flat=True):
            r = False

        return r

    def existe_entrega_que_pode_ser_removida_no_rit(self, user):
        entregas_rit = self.get_entregas_rit()
        return bool(entregas_rit)

    def get_entregas_rit(self):
        return RelatorioIndividualTrabalho.objects.filter(entrega_pit__pit=self).order_by('titulo')

    def existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(self, user, retornar_lista_erros=False):
        erros = []

        if not self.pit_estah_homologado():
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se o {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} não está homologado.'
                )
            else:
                return True, None

        entregas_pit = self.get_entregas_para_analise_aprovacao_homologacao()
        setor_apto_para_homologar = self.get_setor_envolvido_apto_para_homologar()
        setor_envolvido_pode_homologar = self.get_setores_envolvidos().filter(pode_homologar=True).first()
        # Se setor principal existe
        if not (setor_envolvido_pode_homologar and setor_envolvido_pode_homologar.setor):
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se não existe um PES principal. Verifique seu {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} e seu setor atual.'
                )
            else:
                return True, None

        # Se PES principal existe e esta aprovado
        if setor_envolvido_pode_homologar and not setor_envolvido_pode_homologar.pes:
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se não existe um PES aprovado para o seu setor atual. Verifique seu {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} e o PES do seu setor.'
                )
            else:
                return True, None

        # Não pode se tiver alguma entrega cancelada no PES mas não tiver sido canceda no PIT
        if entregas_pit.filter(entrega_pes__isnull=False).filter(entrega_pes__cancelado=True, cancelado=False).exists():
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} tiver alguma entrega cancelada no PES mas não tiver sido canceda no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}.'
                )
            else:
                return True, None

        # Se tiver apenas com entregas de PES canceladas
        if not entregas_pit.filter(entrega_pes__isnull=False).exclude(entrega_pes__cancelado=True).exists():
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} tiver apenas entregas canceladas no PES.'
                )
            else:
                return True, None

        # Se tiver apenas entregas de PIT que estejam canceladas nao pode
        if not entregas_pit.filter(entrega_pes__isnull=False).exclude(cancelado=True).exists():
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} tiver apenas entregas canceladas.'
                )
            else:
                return True, None

        # PIT deve ter como setor envolvido ultimo setor do servidor considerando o periodo do PIT
        # - setor envolvido apto pra homologar
        # - o setor que vai homologar é o setor mais atual do servidor considerando o periodo deste pit
        entregas_cadastradas_vinculada_a_pes_principal = entregas_pit.filter(
            entrega_pes__pes__setor=setor_apto_para_homologar, entrega_pes__cancelado=False, cancelado=False
        ).exists()
        if not setor_apto_para_homologar or not entregas_cadastradas_vinculada_a_pes_principal:
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} for necessário cadastrar, no mínimo, uma entrega relacionada ao PES do seu setor (setor principal) neste {nomenclatura.pit_rit_pgd2}. Verifique se neste {nomenclatura.pit_rit_pgd2} existe alguma entrega relacionada ao setor definido como "Principal e apto para homologar PIT/RIT" na seção "PESs relacionados"'
                )
            else:
                return True, None

        if self.pode_solicitar_aprovacao_homologacao_pit(user, retornar_lista_erros=False)[0]:
            if retornar_lista_erros:
                erros.append(
                    f'Impossível realizar operações no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} se o {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} necessitar de aprovação.'
                )
            else:
                return True, None

        if erros:
            return True, erros

        return False, None

    def pode_finalizar_aprovacao_homologacao_rit(self, retornar_lista_erros=False):
        # Consiferando que já rodou o pode_aprovar_pit e/ou pode_homologar_pit
        # Verifica se pode finalizar
        erros = []

        if self.existe_setores_envolvidos_nao_habilitado():
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado())
            else:
                return False, None

        # Não pode se tiver alguma entrega cancelada no PES mas não tiver sido canceda no PIT
        if (
            self.get_entregas_rit()
            .filter(entrega_pit__entrega_pes__isnull=False, entrega_pit__entrega_pes__cancelado=True, entrega_pit__cancelado=False)
            .exists()
        ):
            if retornar_lista_erros:
                erros.append('Não pode haver entregas não canceladas vinculas a entregas de PES que estejam canceladas.')
            else:
                return False, None

        # Se tiver apenas entregas de PIT que estejam canceladas nao pode OU que tenha apenas com entregas de PES canceladas
        if not self.get_entregas_rit().filter(entrega_pit__entrega_pes__isnull=False).exclude(entrega_pit__cancelado=True).exists():
            if retornar_lista_erros:
                erros.append(f'Não pode haver apenas entregas de {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} que estejam canceladas.')
            else:
                return False, None

        # Se tiver apenas com entregas de PES canceladas
        if not self.get_entregas_rit().filter(entrega_pit__entrega_pes__isnull=False).exclude(entrega_pit__entrega_pes__cancelado=True).exists():
            if retornar_lista_erros:
                erros.append('Não pode haver apenas entregas de PES que estejam canceladas.')
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def pode_solicitar_aprovacao_homologacao_rit(self, user, retornar_lista_erros=False):
        # Se o servidor pode solicitar aprov e homolog de um RIT

        erros = []

        if self.existe_setores_envolvidos_nao_habilitado():
            if retornar_lista_erros:
                erros.append(get_msg_nenhum_setor_habilitado())
            else:
                return False, None

        # Pit homologado
        if self.situacao != self.HOMOLOGADO:
            if retornar_lista_erros:
                erros.append(f'O {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} precisa estar homologado.')
            else:
                return False, None

        if self.existem_pendencias_no_pit_para_solicitar_aprovacao_homologaca_rit(user)[0]:
            if retornar_lista_erros:
                erros.append(
                    f'Existem pendências no {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}. Verifique seu {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} e {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
                )
            else:
                return False, None

        if not self.pode_cadastrar_entrega_rit(user=user, valida_apenas_o_basico=True):
            if retornar_lista_erros:
                erros.append(f'Este {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} não pode ser editado.')
            else:
                return False, None

        setor_apto_para_homologar = self.get_setor_envolvido_apto_para_homologar()

        # Precisa ter entregas E essas entregas precisa ter, no mínimo, uma vinculada ao setor apto a homologar
        entregas_cadastradas_vinculada_a_pes_principal = (
            self.get_entregas_rit().filter(entrega_pit__entrega_pes__pes__setor=setor_apto_para_homologar).exists()
        )
        if not entregas_cadastradas_vinculada_a_pes_principal:
            if retornar_lista_erros:
                erros.append(
                    f'É necessário cadastrar, no mínimo, uma entrega relacionada ao PES do seu setor (setor principal) neste {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}.'
                )
            else:
                return False, None

        # Nenhuma entrega do RIT pode estar relacionada a entrega cancelada de PES/PIT
        entegas_rits_canceladas = (
            self.get_entregas_rit().filter(Q(entrega_pit__entrega_pes__cancelado=True) | Q(entrega_pit__cancelado=True)).exists()
        )
        if entegas_rits_canceladas:
            if retornar_lista_erros:
                erros.append(
                    f'Nenhuma entrega do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} pode estar vinculada a alguma entrega de PES/{nomenclatura.plano_individual_de_trabalho_sigla_pgd2} que esteja cancelada. Verifique seu {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} e {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'
                )
            else:
                return False, None

        if erros:
            return False, erros

        return True, None

    def get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(self, setores=None, servidores=None, tipo_parecer=None):
        return PlanoIndividualTrabalho.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas(
            objeto_parecer=2, setores=setores, servidores=servidores, setores_hoje=None, tipo_parecer=tipo_parecer
        ).filter(solicitacao__pit=self)

    def pode_aprovar_rit(self, user):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        # Se o chefe pode aprovar um determinado PIT

        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        if self.situacao_rit != PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT:
            return False

        # Se fui chefe no periodo ou Se sou chefe hoje
        """
        setores_chefe_no_periodo = setores_que_sou_chefe_no_periodo(self.data_inicio, self.data_fim, user.get_relacionamento())
        setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        setores = setores_chefe_no_periodo | setores_sou_chefe_hoje
        if not setores:
            return False
        """
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(user, self.data_inicio, self.data_fim, apenas_setores=True)

        # Se tem solicitacao que pode ser atendida pelo chefe
        ids_pits = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        ).values_list('solicitacao__pit', flat=True)
        if self.id not in ids_pits:
            return False

        # Se servidor do PIT for da AUDGE só quem pode homologar é o chefe da AUDGE
        if considerar_auditoria_centralizada() and servidor_eh_auditor(self.adesao.servidor):
            if get_setor_auditoria_centralizada() not in setores:
                return False

        return True

    def pode_homologar_rit(self, user, considera_pendencia_geral_servidor_pgd=True):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        if self.situacao_rit != PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT:
            return False

        setores, servidores = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(
            user, self.data_inicio, self.data_fim, apenas_setores=False
        )
        if not setores and not servidores:
            return False

        # Se tem solicitacao que pode ser atendida pelo chefe
        ids_pits = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores, servidores=servidores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        ).values_list('solicitacao__pit', flat=True)
        if self.id not in ids_pits:
            return False

        # Se servidor do PIT for da AUDGE só quem pode homologar é o chefe da AUDGE
        if considerar_auditoria_centralizada() and servidor_eh_auditor(self.adesao.servidor):
            if get_setor_auditoria_centralizada() not in setores:
                return False

        pode_homologar = True
        if considera_pendencia_geral_servidor_pgd:
            pit_atual = PlanoIndividualTrabalho.get_pit_na_data(self.adesao.servidor, get_datetime_now().date(), permite_pit_aguardando_parecer=True)
            pit_copia = PlanoIndividualTrabalhoCopia.objects.filter(original=pit_atual).first()
            pit_teste = pit_atual
            if pit_copia:
                pit_teste.regime_execucacao = pit_copia.regime_execucacao
                pit_teste.percentual_teletrabalho = pit_copia.percentual_teletrabalho
            pode_homologar = True
            if self == pit_atual:
                if get_pendencia_geral_servidor_pgd(self.adesao.servidor, pit_especifico=pit_teste):
                    pode_homologar = False

        return pode_homologar

    def pode_reabrir_rit(self, user):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        if self.adesao.servidor.pk == user.get_relacionamento().pk:
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Pode se adesao estiver vigente
        # - Se estiver desligado precisa ta na carencia
        if not self.adesao.estah_vigente_ou_desligado_na_carencia:
            return False

        # Situação do PIT e RIT
        if not (
            self.situacao == PlanoIndividualTrabalho.HOMOLOGADO
            and self.situacao_rit in [PlanoIndividualTrabalho.HOMOLOGADO_RIT, PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT]
        ):
            return False

        """
        # Se fui chefe no periodo ou Se sou chefe hoje (considerando apenas o que poderia Homologar)
        setores_chefe_no_periodo = setores_que_sou_chefe_no_periodo(self.data_inicio, self.data_fim, user.get_relacionamento())
        setores_sou_chefe_hoje = setores_que_sou_chefe_hoje(user.get_relacionamento())
        setores = setores_chefe_no_periodo | setores_sou_chefe_hoje
        setor_para_homologar = self.get_setor_envolvido_apto_para_homologar()
        if not setores or setor_para_homologar not in setores:
            return False
        """
        setores, _ = setores_e_servidores_que_sou_relacionado_como_chefe_no_periodo(user, self.data_inicio, self.data_fim, apenas_setores=True)
        setor_para_homologar = self.get_setor_envolvido_apto_para_homologar()
        return not (not setores or setor_para_homologar not in setores)

    def aprovar_rit(self, setores, servidor_parecer):
        # Solicitações de cada setor que serão aprovadas
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )

        # Solicitacao
        solicitacao_analise = solicitacoes[0].solicitacao

        # Sabendo se existe alguma solicitacao de aprovacao que vai ficar de fora dessa aprovacao por setor
        existe_solicitacoes_nao_serao_aprovadas = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao=solicitacao_analise, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO, parecer__isnull=True
            )
            .exclude(id__in=solicitacoes)
            .exists()
        )

        # Aprova
        for soa in solicitacoes:
            soa.parecer = True
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Se nao existem mais solictacoes de aprovacao pendentes para algum setor
        # - marca a analise com PitSolicitacaoAnalise.tem_pendencia_aprovacao = False
        # if not PitSolicitacaoAnaliseSetor.objects.filter(
        #    solicitacao__pit=self, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO, parecer__isnull=True
        # ).exists():
        #    solicitacao_analise.tem_pendencia_aprovacao = False
        #    solicitacao_analise.save()
        if not existe_solicitacoes_nao_serao_aprovadas:
            solicitacao_analise.tem_pendencia_aprovacao = False
            solicitacao_analise.save()

    def reprovar_rit(self, setores, servidor_parecer):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.APROVACAO
        )
        solicitacao_analise = solicitacoes[0].solicitacao

        # Reprova
        for soa in solicitacoes:
            soa.parecer = False
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Finaliza a solicitacao
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # Atualiza situaco do PIT
        self.situacao_rit = PlanoIndividualTrabalho.EM_CADASTRO_RIT
        self.save()

    def homologar_rit(self, setores, avaliacao_rit, tempo_homologado, servidor_parecer, justificativa=None):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores,
            tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
        )
        solicitacao = solicitacoes.first()
        if solicitacao is None:
            return False

        #
        solicitacao_analise = solicitacao.solicitacao

        # Homologa
        for soa in solicitacoes:
            soa.parecer = True
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Finaliza a solicitacao
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # Atualiza situacao do PIT e horas homologadas no RIT
        self.situacao_rit = PlanoIndividualTrabalho.HOMOLOGADO_RIT
        self.avaliacao_rit = avaliacao_rit
        self.avaliacao_observacao_rit = justificativa
        #
        self.tempo_executado_homologado_total = tempo_homologado
        self.rit_em_execucao = False
        self.save()

        self.marcar_para_enviar_pela_api()

        if utilizar_integracao_com_ponto():
            self.distribuir_horas_automaticamente()

        return True

    def reabrir_rit(self):
        # Se o RIT estiver AGUARDANDO_PARECER_RIT é necessário ajustar as solicitações de aprovação/homologação
        # - Desfaz todas as análises que eventualmente foram feitas e finaliza a solitação sem pendência
        if self.situacao_rit == PlanoIndividualTrabalho.AGUARDANDO_PARECER_RIT:
            solicitacoes_analise_rit = PitSolicitacaoAnalise.objects.filter(pit=self, finalizado=False)
            for solicitacao_analise in solicitacoes_analise_rit:
                solicitacao_analise.tem_pendencia_aprovacao = False
                solicitacao_analise.tem_pendencia_homologacao = False
                solicitacao_analise.finalizado = True
                solicitacao_analise.save()
                solicitacoes_analise_setor = PitSolicitacaoAnaliseSetor.objects.filter(solicitacao=solicitacao_analise)
                for solicitacao_analise_setor in solicitacoes_analise_setor:
                    solicitacao_analise_setor.parecer = None
                    solicitacao_analise_setor.data_parecer = None
                    solicitacao_analise_setor.save()

        # Atualiza situacao do PIT e horas homologadas no RIT
        self.situacao_rit = PlanoIndividualTrabalho.EM_CADASTRO_RIT
        self.avaliacao_rit = None
        self.tempo_executado_homologado_total = Decimal(0)
        self.rit_em_execucao = False
        self.data_envio_api_pgd_pos_homologacao_rit = None
        self.save()

        self.marcar_para_nao_enviar_pela_api()

        self.desfazer_distribuicao_horas()

    def nao_homologar_rit(self, setores, servidor_parecer):
        solicitacoes = self.get_solicitacoes_setor_aprovacao_homologacao_nao_finalizadas_do_rit(
            setores=setores, tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO
        )
        solicitacao_analise = solicitacoes[0].solicitacao

        # Homologa
        for soa in solicitacoes:
            soa.parecer = False
            soa.data_parecer = get_datetime_now()
            soa.servidor_parecer = servidor_parecer
            soa.save()

        # Finaliza a solicitacao
        solicitacao_analise.tem_pendencia_aprovacao = False
        solicitacao_analise.tem_pendencia_homologacao = False
        solicitacao_analise.finalizado = True
        solicitacao_analise.save()

        # Atualiza situaco do PIT
        self.situacao_rit = PlanoIndividualTrabalho.EM_CADASTRO_RIT
        self.save()

    # ===============================================
    # Calculos e cadastros de distribuicao de horas do RIT (apenas avaliados definitivamente)
    # ===============================================
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
            ths = obter_dados_horas_ponto_servidor(self.adesao.servidor, data_ini=di, data_fim=df)
            ths = ths.get_totais()

            # Retorna em segundos
            # return (ths.total_exigido_final + ths.total_debito_externo) - ths.total_trabalhado
            return ths.total_restante_debito

        return 0

    @staticmethod
    def get_pits_homologados_adesao(adesao):
        # PITs que foram homologados (Homologados) em uma adesao
        ids_pit = PitSolicitacaoAnaliseSetor.objects.filter(
            solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
            solicitacao__finalizado=True,
            parecer=True,
            tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
            solicitacao__pit__adesao=adesao,
        ).values_list('solicitacao__pit_id')

        return PlanoIndividualTrabalho.objects.filter(id__in=ids_pit)

    @staticmethod
    def get_primeiro_pit_homologado_adesao(adesao):
        return PlanoIndividualTrabalho.get_pits_homologados_adesao(adesao).order_by('data_inicio').first()

    @staticmethod
    def get_ultimo_pit_homologado_adesao(adesao):
        return PlanoIndividualTrabalho.get_pits_homologados_adesao(adesao).order_by('-data_inicio').first()

    @staticmethod
    def get_ultimo_pit_homologado_do_servidor(servidor):
        # Ultimo pit homologado do servidor independente da adesão
        psas = (
            PitSolicitacaoAnaliseSetor.objects.filter(
                solicitacao__objeto_parecer=PitSolicitacaoAnalise.PIT,
                solicitacao__finalizado=True,
                parecer=True,
                tipo_parecer=PitSolicitacaoAnaliseSetor.HOMOLOGACAO,
                solicitacao__pit__adesao__servidor=servidor,
            )
            .order_by('-solicitacao__pit__data_inicio')
            .first()
        )
        if not psas:
            return None
        return psas.solicitacao.pit

    @staticmethod
    def get_adesoes_pgd_com_registros_homologacao_pit():
        # Tem registro de homologacao de PIT
        # PIT foi homologado ao menos uma vez
        ids_adesoes_com_pit_homologado = (
            PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez().order_by('adesao_id').distinct('adesao_id').values_list('adesao_id')
        )
        return SolicitacaoAdesaoServidor.objects.filter(id__in=ids_adesoes_com_pit_homologado)

    def get_periodo_semestre_rit(self):
        # Semestre do RIT
        # - Se o RIT for do mês de MAI
        #   - O semestre do RIT será JAN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre do RIT será JUL a DEZ
        # Considerar ainda data de adesão ao PGD e eventual desligamento
        di = None
        df = None
        mes_rit = self.data_inicio.month
        ano_rit = self.data_fim.year
        if mes_rit <= 6:
            di = datetime.date(ano_rit, 1, 1)
            df = datetime.date(ano_rit, 6, 30)
        else:
            di = datetime.date(ano_rit, 7, 1)
            df = datetime.date(ano_rit, 12, 31)
        data_inicio_pgd = self.adesao.primeiro_dia_pgd_nessa_adesao()
        if data_inicio_pgd > di:
            di = data_inicio_pgd
        ultimo_dia_pgd = self.adesao.get_data_efeitos_desligamento_pgd()
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
        mes_rit = self.data_inicio.month
        ano_rit = self.data_inicio.year
        if mes_rit <= 6:
            di = datetime.date(ano_rit, 1, 1)
        else:
            di = datetime.date(ano_rit, 7, 1)
        data_inicio_pgd = self.adesao.primeiro_dia_pgd_nessa_adesao()
        if data_inicio_pgd > di:
            di = data_inicio_pgd

        df = self.data_inicio - relativedelta(days=1)

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
        #   - O semestre anterior será JUN a JUN
        # - Se o RIT for do mês de NOV
        #   - O semestre anterior será NOV a DEZ
        # Considerar ainda data de adesão ao PGD e eventual desligamento
        di = self.data_fim + relativedelta(days=1)

        df = None
        mes_rit = self.data_inicio.month
        ano_rit = self.data_inicio.year
        if mes_rit <= 6:
            df = datetime.date(ano_rit, 6, 30)
        else:
            df = datetime.date(ano_rit, 12, 31)
        ultimo_dia_pgd = self.adesao.get_data_efeitos_desligamento_pgd()
        if ultimo_dia_pgd and ultimo_dia_pgd < df:
            df = ultimo_dia_pgd

        if di > df:
            return None, None

        return di, df

    def pode_distribuir_horas(self, user):
        if self.existe_setores_envolvidos_nao_habilitado():
            return False

        if not utilizar_integracao_com_ponto():
            return False

        # Situacao do PIT permite
        if self.situacao != self.HOMOLOGADO:
            return False

        # Regras relacionadas a adesao e ao desligamento
        # - Pode se adesao estiver ativa
        # - OU Pode se estiver desligado mas ainda estiver na carencia
        if not self.adesao.estah_vigente_ou_desligado_na_carencia:
            return False

        # Se ja foi homologado de forma definitiva
        # Se eh Servidor deste PIT
        # - Se eh o servidor Adesao ao PGD vinculada a este PIT
        return self.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT and self.adesao.servidor == user.get_relacionamento()

    def cadastrar_saldo_externo_rit(
        self,
        data_inicio_utilizacao,
        data_fim_utilizacao,
        valor_saldo_em_segundos,
        informar_compensacao_automaticamente,
        situacao=None,
        detalhamento=None,
    ):
        # Cadastro manual de saldo externo relacionado a um RIT
        rit = self

        data_cadastro = get_datetime_now()
        servidor_destinatario = rit.adesao.servidor

        servidor_validador = None  # será o chefe imediato (resolvido automaticamente)
        servidor_cadastrador = servidor_validador
        observacoes_servidor_validador = rit.get_verbose_rit()
        if detalhamento:
            detalhamento = f'{rit.get_verbose_rit()} - para -  {detalhamento}'
        else:
            detalhamento = rit.get_verbose_rit()

        # um mesmo rit pode está associado a um ou mais saldos externos
        um_rit_varios_saldos_externos = True

        r_saldo_externo = SaldoExterno.cadastrar_saldo_externo(
            data_cadastro=data_cadastro,
            servidor_destinatario=servidor_destinatario,
            valor_saldo_em_segundos=valor_saldo_em_segundos,
            data_inicio_utilizacao=data_inicio_utilizacao,
            data_fim_utilizacao=data_fim_utilizacao,
            informar_compensacao_automaticamente=informar_compensacao_automaticamente,
            model_instance_origem=rit,
            observacoes_servidor_validador=observacoes_servidor_validador,
            detalhamento=detalhamento,
            servidor_cadastrador=servidor_cadastrador,
            servidor_validador=servidor_validador,
            unique_together_with_model_instance_origem=not um_rit_varios_saldos_externos,
            situacao=situacao,
        )
        if not r_saldo_externo.is_realizado:
            raise Exception('Erro ao cadastrar saldo externo!')

        return r_saldo_externo

    def distribuir_horas_automaticamente(self, apenas_periodo_rit=False):
        if not utilizar_integracao_com_ponto():
            return False

        # =============================================================
        # Distribui automaticamente as horas do RIT homologado
        # =============================================================
        # A distribuição de horas é feita apenas para RITs homologados.
        #
        # Assim, apenas a CH homologada é distribuída para efeitos de compensação no
        # relatório de horas (relatório de frequência) do servidor
        #
        # A distribuição segue a seguinte ordem de prioridade
        # - Distribui a CH homologada para o período do RIT
        # - Caso ainda tenha CH restante é distribuída para meses anteriores ao período do RIT
        # - Caso ainda tenha CH restante é distribuída para as compensações específicas compensáveis por CH deste RIT
        # - Caso ainda tenha CH restante é distribuída para os meses seguintes ao RIT

        # Dados iniciais
        # --------------------------------------
        ch_ainda_nao_distribuida = 0
        dados_horas_ponto_servidor = self.get_dados_horas_ponto_servidor()
        totais_dados_horas_ponto_servidor = dados_horas_ponto_servidor.get_totais()
        #
        ch_homologada = self.tempo_executado_homologado_total * 3600
        #
        tempo_previsto = self.tempo_previsto * 3600

        # -------------------------------------------------------------
        # ETAPA 1 - DISTRIBUIÇÃO PARA O PERIODO DO RIT
        # -------------------------------------------------------------

        # Calculo de horas
        # --------------------------------------
        # As horas serão distribuídas com o objetivo de compensar o que for possível do período do RIT
        # - Se a CH homologada for 100h e a CH prevista for 100h, serão distribuídas 100h para o período do RIT
        # - Se a CH homologada for 90h e a CH prevista for 100h, serão distribuídas 90h para o período do RIT
        # - Se a CH homologada for 110h e a CH prevista for 100h, serão distribuídas 100h para o período do RIT
        #   e teremos 10h restantes para outras distribuições
        horas_a_serem_distruidas_para_periodo_rit = 0
        if ch_homologada >= tempo_previsto:
            horas_a_serem_distruidas_para_periodo_rit = tempo_previsto
            ch_ainda_nao_distribuida = Decimal(ch_homologada) - Decimal(horas_a_serem_distruidas_para_periodo_rit)
        else:
            horas_a_serem_distruidas_para_periodo_rit = ch_homologada
            ch_ainda_nao_distribuida = 0

        # Total de horas distribuídas para o mes do RTI
        ch_distribuido_periodo_rit = horas_a_serem_distruidas_para_periodo_rit

        # Total de horas que serao cadastradas no saldo externo
        # - Considera apenas o débito a ser compensado
        # - No limite da CH a ser distribuída no período do rit, pois há casos em que a
        #   CH a ser distribuída no período do rit é menor que o débito no mesmo período
        ch_saldo_externo_periodo_rit = totais_dados_horas_ponto_servidor.total_restante_debito
        if ch_saldo_externo_periodo_rit == 0:
            ch_saldo_externo_periodo_rit = tempo_previsto
        elif ch_saldo_externo_periodo_rit > ch_distribuido_periodo_rit:
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
            self.data_inicio,
            self.data_fim,
            valor_saldo_em_segundos=ch_saldo_externo_periodo_rit,
            informar_compensacao_automaticamente=True,
            detalhamento=' '.join(saldo_externo_detalhamento),
        )

        if not saldo_externo_periodo_rit.is_realizado:
            raise Exception('Erro ao distribuir horas para o período do RIT')

        # -------------------------------------------------------------
        # # ETAPA 2 - SEMESTRE DO RIT - Anterior RIT
        # -------------------------------------------------------------
        ch_distribuido_semestre_rit__periodo_anterior_rit = 0
        saldo_externo_semestre_rit__periodo_anterior_rit = None
        data_inicio_utilizacao, data_fim_utilizacao = self.get_periodo_semestre_rit_antes_rit()
        #
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
                    valor_saldo_em_segundos=ch_distribuido_semestre_rit__periodo_anterior_rit,
                    informar_compensacao_automaticamente=True,
                )
                if not saldo_externo_semestre_rit__periodo_anterior_rit.is_realizado:
                    raise Exception('Erro ao distribuir horas para o semestre do RIT')

        # -------------------------------------------------------------
        # # ETAPA 3 - COMPENSAÇÕES ESPECÍFICAS
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
                    dcc[1], dcc[1], valor_saldo_em_segundos=dcc[2], informar_compensacao_automaticamente=True, detalhamento=str(dcc[0][0])
                )
                dias_compesacao_compensavel_saldo_externo.append((dcc[0][0], dcc[1], dcc[2], se))

        # -------------------------------------------------------------
        # # ETAPA 4 - SEMESTRE DO RIT - Posterior RIT
        # -------------------------------------------------------------
        # TODAS as horas ainda não distribuídas (QUE SOBRARAM DEPOIS DE TODASAS ETAPAS) serão
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
                valor_saldo_em_segundos=ch_distribuido_semestre_rit__periodo_posterior_rit,
                informar_compensacao_automaticamente=False,
                situacao=SaldoExterno.SITUACAO_VALIDADO,
            )
            if not saldo_externo_semestre_rit__periodo_posterior_rit.is_realizado:
                raise Exception('Erro ao distribuir horas para o semestre do RIT')

        # -------------------------------------------------------------
        # Cadastra dados da distribuição de horas do RIT
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
        self.ch_distribuido_semestre_rit = Decimal(ch_distribuido_semestre_rit__periodo_anterior_rit) + Decimal(
            ch_distribuido_semestre_rit__periodo_posterior_rit
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
        if not utilizar_integracao_com_ponto():
            return False

        # -------------------------------------------------------------
        # Desfaz TODAS as distribuicoes de horas
        # -------------------------------------------------------------
        self.ch_distribuida = 0

        # self.ch_a_distribuir = self.tempo_executado_total * 3600
        self.ch_a_distribuir = self.tempo_executado_homologado_total * 3600

        self.ch_distribuido_periodo_rit = 0
        self.ch_distribuido_semestre_rit = 0
        self.ch_distribuido_compesacao_especifica = 0
        self.bloqueado_para_distribuicao_manual = False
        self.save()

        RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=self).delete()
        content_type_rit = ContentType.objects.get_for_model(PlanoIndividualTrabalho)
        SaldoExterno.objects.filter(origem_type=content_type_rit, origem_id=self.id).delete()

        return True

    # Distribuição manual - Semestre
    # -----------------------------------------
    def pode_ajustar_distribuicao_horas_semestre_rit(self, user):
        if not utilizar_integracao_com_ponto():
            return False

        return bool(
            self.pode_distribuir_horas(user)
            and not self.ch_distribuido_semestre_rit > 0
            and self.ch_a_distribuir > 0
            and self.ch_distribuido_periodo_rit > 0
            and not self.bloqueado_para_distribuicao_manual
        )

    def ajustar_distribuicao_horas_semestre_rit(self, compensar_automaticamente=True, ch=0, distribuir_todas=False):
        if not utilizar_integracao_com_ponto():
            return False

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
                    raise Exception(f'Erro ao distribuir horas para o semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}')

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
                raise Exception(f'Erro ao distribuir horas para o semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}')
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
        if not utilizar_integracao_com_ponto():
            return False
        return bool(self.pode_distribuir_horas(user) and self.ch_distribuido_semestre_rit > 0 and not self.bloqueado_para_distribuicao_manual)

    def desfazer_distribuicao_horas_semestre(self):
        if not utilizar_integracao_com_ponto():
            return False

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
        if not utilizar_integracao_com_ponto():
            return False

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
        if not utilizar_integracao_com_ponto():
            return False

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
        if not utilizar_integracao_com_ponto():
            return False

        if self.pode_distribuir_horas(user) and self.ch_distribuido_compesacao_especifica > 0 and not self.bloqueado_para_distribuicao_manual:
            # Se tiver ch de rit para esta compensação específica então pode desfazer distribuição para esta compensação
            if RelatorioIndividualTrabalhoDistribuicaoHoras.objects.filter(rit=self, compensacao_especifica=compensacao_especifica).exists():
                return True
        return False

    def desfazer_distribuicao_compensacao_especifica(self, compensacao_especifica):
        if not utilizar_integracao_com_ponto():
            return False

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
    def get_modalidade_execucao_servidor_na_data(servidor, data):
        # Pega do PIT da data ou do imadiatamente anterior a ele
        pit_na_data = PlanoIndividualTrabalho.objects.filter(
            adesao__servidor=servidor, data_inicio__lte=data, data_fim__gte=data, situacao=PlanoIndividualTrabalho.HOMOLOGADO
        ).first()
        if not pit_na_data:
            # pit anterior
            pit_na_data = (
                PlanoIndividualTrabalho.objects.filter(adesao__servidor=servidor, data_inicio__lt=data, situacao=PlanoIndividualTrabalho.HOMOLOGADO)
                .order_by('-data_inicio')
                .first()
            )
        if pit_na_data:
            return pit_na_data.get_modalidade_execucao_para_api()
        return None

    @staticmethod
    def get_servidores_pgd_por_modalidade(modalidade_execucao):
        # Conforme: get_modalidade_execucao_para_api
        # Modalidade e regime de execução do trabalho do participante, restrito a uma das cinco opções:
        # - 1 - Presencial
        # - 2 - Teletrabalho parcial
        # - 3 - Teletrabalho integral
        # - 4 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)
        # - 5 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)

        servidores_em_pgd = SolicitacaoAdesaoServidor.get_servidores_em_pgd()
        ids_servidores_modalidade = []
        for servidor in servidores_em_pgd:
            modalidade_execucao_servidor = PlanoIndividualTrabalho.get_modalidade_execucao_servidor_na_data(servidor, get_datetime_now().date())
            if modalidade_execucao_servidor and modalidade_execucao_servidor == modalidade_execucao:
                ids_servidores_modalidade.append(servidor.id)
        if ids_servidores_modalidade:
            return servidores_em_pgd.filter(id__in=ids_servidores_modalidade)
        return Servidor.objects.none()

    @staticmethod
    def get_pit_na_data(servidor, data, permite_pit_nao_homologado=False, permite_pit_aguardando_parecer=False):
        pit_na_data = PlanoIndividualTrabalho.objects.filter(adesao__servidor=servidor, data_inicio__lte=data, data_fim__gte=data)

        if permite_pit_nao_homologado:
            pit_na_data = pit_na_data.filter(
                situacao__in=[PlanoIndividualTrabalho.HOMOLOGADO, PlanoIndividualTrabalho.EM_CADASTRO, PlanoIndividualTrabalho.AGUARDANDO_PARECER]
            )
        elif permite_pit_aguardando_parecer:
            pit_na_data = pit_na_data.filter(situacao__in=[PlanoIndividualTrabalho.HOMOLOGADO, PlanoIndividualTrabalho.AGUARDANDO_PARECER])
        else:
            pit_na_data = pit_na_data.filter(situacao=PlanoIndividualTrabalho.HOMOLOGADO)
        pit_na_data = pit_na_data.first()

        return pit_na_data

    # ====================================
    # API
    # ====================================
    def get_modalidade_execucao_para_api(self):
        # Considerando: https://api.pgd.gestao.gov.br/docs#/participante/

        # Modalidade e regime de execução do trabalho do participante, restrito a uma das cinco opções:
        # - 1 - Presencial
        # - 2 - Teletrabalho parcial
        # - 3 - Teletrabalho integral
        # - 4 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)
        # - 5 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)
        # Regras de validação: Só é possível a escolha de uma das cinco opções.

        def get_estah_em_pgd_exterior():
            # Por cadastrado manual
            # -----------------------
            if pgd_exterior_cadastro := PGDExterior.get_vigentes().filter(servidor=self.adesao.servidor).first():
                if pgd_exterior_cadastro.hipotese_legal == PGDExterior.HIPOTESE_LEGAL_ART_12_VIII:
                    return 4
                if pgd_exterior_cadastro.hipotese_legal == PGDExterior.HIPOTESE_LEGAL_ART_12_P7:
                    return 5

            # Por afastamento (antigo)
            # -----------------------

            # Afastamento PGD exterior: Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)
            afastamentos_pgd_exterior_tipo1 = Configuracao.get_valor_por_chave('pgd2', 'afastamentos_pgd_exterior_tipo1')

            # Afastamento PGD exterior: Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)
            afastamentos_pgd_exterior_tipo2 = Configuracao.get_valor_por_chave('pgd2', 'afastamentos_pgd_exterior_tipo2')

            if afastamentos_pgd_exterior_tipo1:
                afastamentos_pgd_exterior_tipo1 = [int(afastamento) for afastamento in afastamentos_pgd_exterior_tipo1.split(',')]
                afastamentos_pgd_exterior_tipo1 = AfastamentoSiape.objects.filter(id__in=afastamentos_pgd_exterior_tipo1)
            else:
                afastamentos_pgd_exterior_tipo1 = AfastamentoSiape.objects.none()
            if afastamentos_pgd_exterior_tipo2:
                afastamentos_pgd_exterior_tipo2 = [int(afastamento) for afastamento in afastamentos_pgd_exterior_tipo2.split(',')]
                afastamentos_pgd_exterior_tipo2 = AfastamentoSiape.objects.filter(id__in=afastamentos_pgd_exterior_tipo2)
            else:
                afastamentos_pgd_exterior_tipo2 = AfastamentoSiape.objects.none()

            afastamentos_pgd_exterior = afastamentos_pgd_exterior_tipo1.union(afastamentos_pgd_exterior_tipo2)
            afastamento_servidor_pgd_exterior = (
                ServidorAfastamento.get_afastamentos(self.adesao.servidor, self.data_inicio, self.data_fim)
                .filter(afastamento__in=afastamentos_pgd_exterior)
                .order_by('data_inicio')
                .last()
            )

            if afastamento_servidor_pgd_exterior:
                if afastamento_servidor_pgd_exterior.afastamento in afastamentos_pgd_exterior_tipo1:
                    return 4
                if afastamento_servidor_pgd_exterior.afastamento in afastamentos_pgd_exterior_tipo2:
                    return 5

            return None

        if pgd_exterior := get_estah_em_pgd_exterior():
            return pgd_exterior

        if self.regime_execucacao == self.TRABALHO_PRESENCIAL:
            return 1

        if self.regime_execucacao == self.TRABALHO_TELETRABALHO_PARCIAL:
            return 2

        if self.regime_execucacao == self.TRABALHO_TELETRABALHO_INTEGRAL:
            return 3

        return None

    def get_situacao_api(self):
        eh_pit_cancelado = self.situacao == PlanoIndividualTrabalho.CANCELADO
        eh_pit_homologado = self.situacao == PlanoIndividualTrabalho.HOMOLOGADO
        eh_rit_homologado = self.situacao_rit == PlanoIndividualTrabalho.HOMOLOGADO_RIT

        eh_periodo_anterior = self.data_inicio > get_datetime_now().date()
        eh_periodo_atual = self.data_inicio <= get_datetime_now().date() <= self.data_fim

        # 1 Cancelado
        if eh_pit_cancelado:
            return 1

        # 2 Aprovado
        if eh_pit_homologado and eh_periodo_anterior and not eh_rit_homologado:
            return 2

        # 3 Em execução
        if eh_pit_homologado and eh_periodo_atual and not eh_rit_homologado:
            return 3

        # 3 Em execução
        if eh_pit_homologado and not eh_rit_homologado:
            return 3

        # 4 Concluído
        if eh_rit_homologado:
            return 4

        return None

    # No cadastro do PIT
    def marcar_para_nao_enviar_pela_api(self):
        self.deve_enviar_pela_api = False
        self.save(update_fields=['deve_enviar_pela_api'])

    def marcar_para_enviar_pela_api(self):
        self.deve_enviar_pela_api = True
        self.save(update_fields=['deve_enviar_pela_api'])

    # Quando for enviado
    def marcar_como_enviado_pela_api(self):
        self.deve_enviar_pela_api = False
        self.data_hora_ultimo_envio_api = get_datetime_now()
        self.situacao_api_no_ultimo_envio = self.get_situacao_api()
        self.save(update_fields=['deve_enviar_pela_api', 'data_hora_ultimo_envio_api', 'situacao_api_no_ultimo_envio'])

    def get_cod_unidade_executora_para_api(self):
        se = self.get_setores_envolvidos().filter(pode_homologar=True).first()
        return se.pes.cod_siape_grupo

    def get_data_assinatura_tcr_para_api(self):
        # Comentado e ajustado para testar solução de
        # -https://gitlab.ifrn.edu.br/cosinf/suap/-/issues/14056#note_217769
        # Data deve ser
        # - Data início do PIT
        # - Ou data anterior a de hoje (caso a data atual seja anterior ao início do PIT)
        if get_datetime_now().date() <= self.data_inicio:
            return get_datetime_now().date() - relativedelta(days=1)
        return self.data_inicio

    def get_setor_e_pes_que_deveria_ser_o_atual(self):
        setor_pode_homologar, pes_apto_no_periodo, _ = self.calcular_pit_setores_envolvidos(apenas_consulta=True)
        setor_envolvido = self.get_setores_envolvidos().filter(pode_homologar=True).first()
        setor, pes = '', ''
        if setor_pode_homologar != setor_envolvido.setor:
            setor = f'Setor atual que deveria homologar este PIT: {setor_pode_homologar}. Setor que pode homologar este PIT: {setor_envolvido.setor}'
        if pes_apto_no_periodo != setor_envolvido.pes:
            pes = f'PES que deveria ser o principal deste PIT: {pes_apto_no_periodo}. PES que é o principal PIT: {setor_envolvido.pes}'
        if (not setor and not pes) and setor_envolvido.tem_erro():
            setor = f'Setor atual que deveria homologar este PIT: {setor_pode_homologar}. Setor que pode homologar este PIT: {setor_envolvido.setor}'
            pes = f'PES que deveria ser o principal deste PIT: {pes_apto_no_periodo}. PES que é o principal PIT: {setor_envolvido.pes}'
        if setor or pes:
            return f'{setor}. {pes}.'
        # Não existe erro no setor e PES que podem homologar este PIT e o setor e PES do setor envolvido estão corretos
        return None


class PlanoIndividualTrabalhoCopia(models.ModelPlus):
    original = models.ForeignKeyPlus('pgd2.PlanoIndividualTrabalho', editable=False)

    data_inicio = models.DateFieldPlus(verbose_name='Data Início', null=True, blank=True)

    TRABALHO_TELETRABALHO_PARCIAL = 1
    TRABALHO_TELETRABALHO_INTEGRAL = 2
    TRABALHO_PRESENCIAL = 3
    REGIME_EXECUCAO_CHOICES = [
        [TRABALHO_TELETRABALHO_PARCIAL, 'Teletrabalho parcial'],
        [TRABALHO_TELETRABALHO_INTEGRAL, 'Teletrabalho integral'],
        [TRABALHO_PRESENCIAL, 'Presencial'],
    ]
    regime_execucacao = models.PositiveIntegerField('Regime individual de execução no PGD', null=True, choices=REGIME_EXECUCAO_CHOICES)

    percentual_teletrabalho = models.DecimalFieldPlus(verbose_name='% de Teletrabalho', default=0)


class RegistroAcaoPlanoIndividualTrabalho(RegistroAcaoPGD):
    TIPO_EM_CADASTRO = PlanoIndividualTrabalho.EM_CADASTRO  # 1
    TIPO_CANCELADO = PlanoIndividualTrabalho.CANCELADO  # 3
    TIPO_CADASTROU_DADOS_BASICOS = 4
    TIPO_CADASTROU_CRONOGRAMA_TRABALHO_PRESENCIAL = 5
    TIPO_CADASTROU_CRONOGRAMA_ATENDIMENTO_TELETRABALHO = 6
    TIPO_CADASTROU_ENTREGA = 7
    TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO = 8
    TIPO_APROVOU = 9
    TIPO_NAO_APROVOU = 10
    TIPO_HOMOLOGOU = 11
    TIPO_NAO_HOMOLOGOU = 12

    TIPO_CADASTROU_ENTREGA_RIT = 13
    TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO_RIT = 14
    TIPO_APROVOU_RIT = 15
    TIPO_NAO_APROVOU_RIT = 16
    TIPO_HOMOLOGOU_RIT = 17
    TIPO_NAO_HOMOLOGOU_RIT = 18
    TIPO_REABRIU_RIT = 19

    TIPO_CHOICES = (
        (TIPO_EM_CADASTRO, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_EM_CADASTRO - 1][1]),
        (TIPO_CANCELADO, PlanoIndividualTrabalho.SITUACAO_PIT_CHOICES[TIPO_CANCELADO - 1][1]),
        (TIPO_CADASTROU_DADOS_BASICOS, 'Cadastrou/Alterou dados básicos'),
        (TIPO_CADASTROU_CRONOGRAMA_TRABALHO_PRESENCIAL, 'Cadastrou/Alterou dados do trabalho presencial'),
        (TIPO_CADASTROU_CRONOGRAMA_ATENDIMENTO_TELETRABALHO, 'Cadastrou/Alterou dados do atendimento presencial'),
        (TIPO_CADASTROU_ENTREGA, 'Cadastrou/Alterou dados da entrega'),
        (TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO, f'Solicitou Aprovação/Homologação {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_APROVOU, f'Aprovou {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_NAO_APROVOU, f'Não aprovou {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_HOMOLOGOU, f'Homologou {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_NAO_HOMOLOGOU, f'Não Homologou {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_CADASTROU_ENTREGA_RIT, f'Cadastrou entrega no {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
        (
            TIPO_SERVIDOR_SOLICITOU_APROVACAO_HOMOLOGACAO_RIT,
            f'Solicitou Aprovação/Homologação {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        ),
        (TIPO_APROVOU_RIT, f'Aprovou {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_NAO_APROVOU_RIT, f'Não Aprovou {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_HOMOLOGOU_RIT, f'Homologou {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_NAO_HOMOLOGOU_RIT, f'Não Homologou {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
        (TIPO_REABRIU_RIT, f'Reabriu {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'),
    )

    tipo = models.PositiveIntegerField(choices=TIPO_CHOICES, editable=False)
    pit = models.ForeignKeyPlus('pgd2.PlanoIndividualTrabalho', editable=False, null=True)
    user = models.CurrentUserField(editable=False, related_name='rapit_pgd2')
    realizada_apos_aprovacao_pit = models.BooleanField(
        f'Realizado após aprovação do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}', default=False
    )

    @staticmethod
    def registrar(request, tipo, pit, obs='', dados_de_para=None):
        ip = get_client_ip(request)
        realizada_apos_aprovacao = False
        if pit.se_pit_ja_foi_homologado_ao_menos_uma_vez():
            realizada_apos_aprovacao = True
        RegistroAcaoPlanoIndividualTrabalho.objects.create(
            tipo=tipo, pit=pit, ip=ip, observacao=obs, realizada_apos_aprovacao_pit=realizada_apos_aprovacao, de_para=dados_de_para
        )


class PlanoIndividualTrabalhoPresencial(models.ModelPlus):
    pit = models.ForeignKeyPlus(
        'pgd2.PlanoIndividualTrabalho',
        verbose_name=f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        related_name='pit_planejamentopresencial_pgd2',
    )
    original = models.ForeignKeyPlus('self', null=True, blank=True, editable=False)
    homologado = models.BooleanField(default=False, editable=False)
    alterado = models.BooleanField(default=False, editable=False)

    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora Inicial', help_text='Formato: HH:MM.')
    hora_final = models.TimeFieldPlus('Hora Final', help_text='Formato: HH:MM.')

    recorrencia = models.ForeignKeyPlus('pgd2.ControleRecorrenciaPGD', null=True, blank=True)
    timestamp_data_hora_inicio = models.FloatField(null=True)

    class Meta:
        verbose_name = 'Cronograma de Trabalho Presencial'
        verbose_name_plural = 'Cronogramas de Trabalho Presencial'

    def __str__(self):
        return f'Trabalho Presencial do servidor em {format_datetime(self.data)} de {self.hora_inicio!s} a {self.hora_final!s}'

    def eh_copia(self):
        return bool(self.original)

    def eh_original(self):
        return not self.original

    def tem_copia(self):
        return PlanoIndividualTrabalhoPresencial.objects.filter(original__id=self.id).exists()

    def get_copia(self):
        return PlanoIndividualTrabalhoPresencial.objects.filter(original__id=self.id).first()

    def estah_conforme_horario_funcionamento_setor(self):
        # Verifica se está de acordo com as faixas de horário do Funcionamento do Setor
        # - Considera o as faixas de horario do PES do setor que pode homologar o PIT relacionado
        setor_envolvido_pode_homologar = self.pit.get_setores_envolvidos().filter(pode_homologar=True).first()
        if setor_envolvido_pode_homologar and setor_envolvido_pode_homologar.pes:
            return (
                PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=setor_envolvido_pode_homologar.pes, data=self.data)
                .filter(Q(hora_inicio__lte=self.hora_inicio) & Q(hora_final__gte=self.hora_final))
                .exists()
            )
        return False

    @staticmethod
    def get_horarios_agrupado_por_semana(pes, recorrencia=None, listar_copias_se_houver=False, apenas_homologados=False):
        pes_horarios_funcionamento_setor = PlanoIndividualTrabalhoPresencial.objects.filter(pit=pes).order_by('data', 'hora_inicio', 'id')
        if apenas_homologados:
            pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(homologado=True)
        else:
            if listar_copias_se_houver and pes_horarios_funcionamento_setor.filter(original__isnull=False).exists():
                pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(
                    Q(original__isnull=False) | Q(original__isnull=True, homologado=False)
                )
            else:
                pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(original__isnull=True)

        # obtendo as semanas relacionadas considerando as datas cadastradas
        def get_semanas_por_datas(datas):
            semanas = {}
            for data in datas:
                semana = data.isocalendar().week
                if semana not in semanas:
                    inicio = data - timedelta(days=data.weekday())
                    final = inicio + timedelta(days=6)

                    # Se a data final extrapolar o o fim do PES então é preciso ajustar
                    if final > pes.data_fim:
                        final = pes.data_fim
                    semanas[semana] = {'inicio': inicio, 'final': final, 'hfss': []}
            return semanas

        datas = pes_horarios_funcionamento_setor.values_list('data', flat=True)
        semanas = get_semanas_por_datas(datas)
        for hfs in pes_horarios_funcionamento_setor:
            semanas[hfs.data.isocalendar().week]['hfss'].append(hfs)

        return semanas

    # ------------------------
    # Cadastro/Ateracao Comum
    # ------------------------
    @staticmethod
    def validar_cadastro(pit, data, hora_inicio, hora_final, ids_horarios_desconsiderar=None):
        horas_dia = PlanoIndividualTrabalhoPresencial.objects.filter(pit=pit, data=data).order_by('data', 'hora_inicio')
        if horas_dia.filter(original__isnull=False).exists():
            horas_dia = horas_dia.filter(Q(original__isnull=False) | Q(original__isnull=True, homologado=False))
        else:
            horas_dia = horas_dia.filter(original__isnull=True)

        if ids_horarios_desconsiderar:
            horas_dia = horas_dia.exclude(id__in=ids_horarios_desconsiderar)
        # Não pode ter conflito de horário no mesmo dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for hd in horas_dia:
            if not all([hd.hora_inicio, hora_inicio, hd.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break
            # Se inicia dentro ou termina dentro
            if not tem_erro_nos_dados and ((hd.hora_inicio <= hora_inicio <= hd.hora_final) or (hd.hora_inicio <= hora_final <= hd.hora_final)):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    # ------------------------
    # Cadastro Recorrente
    # ------------------------
    @staticmethod
    def validar_cadastro_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        for d in datas_para_cadastrar:
            pode, erro = PlanoIndividualTrabalhoPresencial.validar_cadastro(pes, d, hora_inicio, hora_final)
            if not pode:
                return pode, erro

        return True, None

    @staticmethod
    def cadastrar_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        cr = ControleRecorrenciaPGD.get_novo_controle_recorrencia()
        for d in datas_para_cadastrar:
            pes_hfs = PlanoIndividualTrabalhoPresencial()
            pes_hfs.pit = pes
            pes_hfs.data = d
            pes_hfs.hora_inicio = hora_inicio
            pes_hfs.hora_final = hora_final
            pes_hfs.recorrencia = cr
            pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
                d.year, d.month, d.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            pes_hfs.save()

    # ------------------------
    # Alteracao Recorrente
    # ------------------------
    @staticmethod
    def validar_alteracao_recorrente(pes, pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # pes_hfs: quem está sendo editado
        # hora_inicio, hora_final: hora para a qual está tentando alterar o cadastro de pes_hfs
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # pega todos
        datas_para_validar = PlanoIndividualTrabalhoPresencial.objects.filter(pit=pes).order_by('timestamp_data_hora_inicio')
        if datas_para_validar.filter(original__isnull=False).exists():
            datas_para_validar = datas_para_validar.filter(Q(original__isnull=False) | Q(original__isnull=True, homologado=False))
        else:
            datas_para_validar = datas_para_validar.filter(original__isnull=True)
        recorrencia_pes_hfs = PlanoIndividualTrabalhoPresencial.objects.filter(recorrencia=pes_hfs.recorrencia).order_by('timestamp_data_hora_inicio')

        # exclui todos fora do periodo da recorrencia E exclui todos da recorrencia
        if recorrencia_pes_hfs:
            data_inicio_recorrencia = recorrencia_pes_hfs[0].data
            data_final_recorrencia = recorrencia_pes_hfs[len(recorrencia_pes_hfs) - 1].data
            datas_para_validar = datas_para_validar.exclude(id__in=recorrencia_pes_hfs.values_list('id', flat=True))
        datas_para_validar = datas_para_validar.exclude(Q(data__lt=data_inicio_recorrencia) | Q(data__gt=data_final_recorrencia))

        # este_e_proximos: exclui todos com data antes ao que se deseja editar
        if tipo_recorrencia == 'este_e_proximos':
            datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # este_e_anteriores: exclui todos com data depois ao que se deseja editar
        if tipo_recorrencia == 'este_e_anteriores':
            datas_para_validar = datas_para_validar.exclude(data__gt=pes_hfs.data)

        # todos: ???????????? 'Todos da recorrência'
        # if tipo_recorrencia == 'todos':
        #    datas_para_validar = datas_para_validar.exclude(data__lt=pes_hfs.data)

        # Validando todos os cadastros dia a dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for d in datas_para_validar:
            if not all([d.hora_inicio, hora_inicio, d.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break
            # Se inicia dentro ou termina dentro
            if (d.hora_inicio <= hora_inicio <= d.hora_final) or (d.hora_inicio <= hora_final <= d.hora_final):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    @staticmethod
    def alterar_recorrente(pes_hfs, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # **** EDITA ESTE E OS OUTROS

        # pes_hfs: quem está sendo editado
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # Montando as datas que serão editadas
        # - ALTERAR 'este_e_proximos': VOU EDITAR (Este) E (Todos os proximos da recorrencia)
        # - ALTERAR 'este_e_anteriores': VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
        # - ALTERAR 'todos': VOU EDITAR (Este) E (Todos da recorrencia)
        datas_para_alterar = PlanoIndividualTrabalhoPresencial.objects.filter(recorrencia=pes_hfs.recorrencia).order_by('timestamp_data_hora_inicio')
        if tipo_recorrencia == 'este_e_proximos':
            # VOU EDITAR (Este) E (Todos os proximos da recorrencia)
            datas_para_alterar = datas_para_alterar.filter(timestamp_data_hora_inicio__gte=pes_hfs.timestamp_data_hora_inicio)
        if tipo_recorrencia == 'este_e_anteriores':
            # VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
            datas_para_alterar = datas_para_alterar.exclude(timestamp_data_hora_inicio__lte=pes_hfs.timestamp_data_hora_inicio)
        # tipo_recorrencia == 'todos':
        # VOU EDITAR (Este) E (Todos da recorrencia)
        # datas_para_alterar (completo)

        # Alterando os dados
        # Este
        pes_hfs.hora_inicio = hora_inicio
        pes_hfs.hora_final = hora_final
        pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
            pes_hfs.data.year, pes_hfs.data.month, pes_hfs.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        pes_hfs.alterado = True
        pes_hfs.save()
        # Outros
        for d in datas_para_alterar:
            d.hora_inicio = hora_inicio
            d.hora_final = hora_final
            d.timestamp_data_hora_inicio = datetime.datetime(
                d.data.year, d.data.month, d.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            d.alterado = True
            d.save()

        return True, None

    def pode_cancelar_edicao_atendimento(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        if not self.eh_copia():
            return False

        return self.alterado


class PlanoIndividualTrabalhoAtendimento(models.ModelPlus):
    pit = models.ForeignKeyPlus(
        'pgd2.PlanoIndividualTrabalho',
        verbose_name=f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2}',
        related_name='pit_planejamentoatendimento_pgd2',
    )
    original = models.ForeignKeyPlus('self', null=True, blank=True, editable=False)
    homologado = models.BooleanField(default=False, editable=False)
    alterado = models.BooleanField(default=False, editable=False)

    data = models.DateFieldPlus('Data')
    hora_inicio = models.TimeFieldPlus('Hora Inicial', help_text='Formato: HH:MM.')
    hora_final = models.TimeFieldPlus('Hora Final', help_text='Formato: HH:MM.')

    recorrencia = models.ForeignKeyPlus('pgd2.ControleRecorrenciaPGD', null=True, blank=True)
    timestamp_data_hora_inicio = models.FloatField(null=True)

    class Meta:
        verbose_name = 'Cronograma de Atendimento em Teletrabalho'
        verbose_name_plural = 'Cronogramas de Atendimento em Teletrabalho'

    def __str__(self):
        return f'Atendimento em Teletrabalho do servidor em {format_datetime(self.data)} de {self.hora_inicio!s} a {self.hora_final!s}'

    def eh_copia(self):
        return bool(self.original)

    def eh_original(self):
        return not self.original

    def tem_copia(self):
        return PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=self.id).exists()

    def get_copia(self):
        return PlanoIndividualTrabalhoAtendimento.objects.filter(original__id=self.id).first()

    def estah_conforme_horario_funcionamento_setor(self):
        # Verifica se está de acordo com as faixas de horário do Funcionamento do Setor
        # - Considera o as faixas de horario do PES do setor que pode homologar o PIT relacionado
        setor_envolvido_pode_homologar = self.pit.get_setores_envolvidos().filter(pode_homologar=True).first()
        if setor_envolvido_pode_homologar and setor_envolvido_pode_homologar.pes:
            return (
                PlanoEntregasSetorialHorarioFuncionamentoSetor.objects.filter(pes=setor_envolvido_pode_homologar.pes, data=self.data)
                .filter(Q(hora_inicio__lte=self.hora_inicio) & Q(hora_final__gte=self.hora_final))
                .exists()
            )
        return False

    @staticmethod
    def get_horarios_agrupado_por_semana(pes, recorrencia=None, listar_copias_se_houver=False, apenas_homologados=False):
        pes_horarios_funcionamento_setor = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pes).order_by('data', 'hora_inicio', 'id')
        if apenas_homologados:
            pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(homologado=True)
        else:
            if listar_copias_se_houver and pes_horarios_funcionamento_setor.filter(original__isnull=False).exists():
                pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(
                    Q(original__isnull=False) | Q(original__isnull=True, homologado=False)
                )
            else:
                pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(original__isnull=True)

        if recorrencia:
            pes_horarios_funcionamento_setor = pes_horarios_funcionamento_setor.filter(recorrencia=recorrencia)

        # obtendo as semanas relacionadas considerando as datas cadastradas
        def get_semanas_por_datas(datas):
            semanas = {}
            for data in datas:
                semana = data.isocalendar().week
                if semana not in semanas:
                    inicio = data - timedelta(days=data.weekday())
                    final = inicio + timedelta(days=6)

                    # Se a data final extrapolar o o fim do PES então é preciso ajustar
                    if final > pes.data_fim:
                        final = pes.data_fim
                    semanas[semana] = {'inicio': inicio, 'final': final, 'hfss': []}
            return semanas

        datas = pes_horarios_funcionamento_setor.values_list('data', flat=True)
        semanas = get_semanas_por_datas(datas)
        for hfs in pes_horarios_funcionamento_setor:
            semanas[hfs.data.isocalendar().week]['hfss'].append(hfs)

        return semanas

    # ------------------------
    # Cadastro/Ateracao Comum
    # ------------------------
    @staticmethod
    def validar_cadastro(pit, data, hora_inicio, hora_final, ids_horarios_desconsiderar=None):
        horas_dia = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pit, data=data).order_by('data', 'hora_inicio')
        if horas_dia.filter(original__isnull=False).exists():
            horas_dia = horas_dia.filter(Q(original__isnull=False) | Q(original__isnull=True, homologado=False))
        else:
            horas_dia = horas_dia.filter(original__isnull=True)

        if ids_horarios_desconsiderar:
            horas_dia = horas_dia.exclude(id__in=ids_horarios_desconsiderar)
        # Não pode ter conflito de horário no mesmo dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for hd in horas_dia:
            if not all([hd.hora_inicio, hora_inicio, hd.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break

            # Se inicia dentro ou termina dentro
            if not tem_erro_nos_dados and ((hd.hora_inicio <= hora_inicio <= hd.hora_final) or (hd.hora_inicio <= hora_final <= hd.hora_final)):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    # ------------------------
    # Cadastro Recorrente
    # ------------------------
    @staticmethod
    def validar_cadastro_recorrente(pit, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        for d in datas_para_cadastrar:
            pode, erro = PlanoIndividualTrabalhoAtendimento.validar_cadastro(pit, d, hora_inicio, hora_final)
            if not pode:
                return pode, erro

        return True, None

    @staticmethod
    def cadastrar_recorrente(pes, data, hora_inicio, hora_final, data_ate, recorrencia_dias_semana):
        datas_para_cadastrar = get_lista_dias_para_cadastrar(data, data_ate, recorrencia_dias_semana)
        cr = ControleRecorrenciaPGD.get_novo_controle_recorrencia()
        for d in datas_para_cadastrar:
            pes_hfs = PlanoIndividualTrabalhoAtendimento()
            pes_hfs.pit = pes
            pes_hfs.data = d
            pes_hfs.hora_inicio = hora_inicio
            pes_hfs.hora_final = hora_final
            pes_hfs.recorrencia = cr
            pes_hfs.timestamp_data_hora_inicio = datetime.datetime(
                d.year, d.month, d.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            pes_hfs.save()

    # ------------------------
    # Alteracao Recorrente
    # ------------------------
    def validar_alteracao_recorrente(obj, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # obj: quem está sendo editado
        # hora_inicio, hora_final: hora para a qual está tentando alterar o cadastro de obj
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        pit = obj.pit

        # pega todos
        datas_para_validar = PlanoIndividualTrabalhoAtendimento.objects.filter(pit=pit).order_by('timestamp_data_hora_inicio')
        if datas_para_validar.filter(original__isnull=False).exists():
            datas_para_validar = datas_para_validar.filter(Q(original__isnull=False) | Q(original__isnull=True, homologado=False))
        else:
            datas_para_validar = datas_para_validar.filter(original__isnull=True)
        recorrencia_obj = PlanoIndividualTrabalhoAtendimento.objects.filter(recorrencia=obj.recorrencia).order_by('timestamp_data_hora_inicio')

        # exclui todos fora do periodo da recorrencia E exclui todos da recorrencia
        if recorrencia_obj:
            data_inicio_recorrencia = recorrencia_obj[0].data
            data_final_recorrencia = recorrencia_obj[len(recorrencia_obj) - 1].data
            datas_para_validar = datas_para_validar.exclude(id__in=recorrencia_obj.values_list('id', flat=True))
        datas_para_validar = datas_para_validar.exclude(Q(data__lt=data_inicio_recorrencia) | Q(data__gt=data_final_recorrencia))

        # este_e_proximos: exclui todos com data antes ao que se deseja editar
        if tipo_recorrencia == 'este_e_proximos':
            datas_para_validar = datas_para_validar.exclude(data__lt=obj.data)

        # este_e_anteriores: exclui todos com data depois ao que se deseja editar
        if tipo_recorrencia == 'este_e_anteriores':
            datas_para_validar = datas_para_validar.exclude(data__gt=obj.data)

        # todos: ???????????? 'Todos da recorrência'
        # if tipo_recorrencia == 'todos':
        #    datas_para_validar = datas_para_validar.exclude(data__lt=obj.data)

        # Validando todos os cadastros dia a dia
        tem_conflito = False
        tem_erro_nos_dados = False
        for d in datas_para_validar:
            if not all([d.hora_inicio, hora_inicio, d.hora_final, hora_final]):
                tem_erro_nos_dados = True
                break

            # Se inicia dentro ou termina dentro
            if (d.hora_inicio <= hora_inicio <= d.hora_final) or (d.hora_inicio <= hora_final <= d.hora_final):
                tem_conflito = True
                break
        if tem_erro_nos_dados:
            return False, 'Faltam alguns dados para a validação'
        if tem_conflito:
            return False, 'A hora inicial e final está em conflito com outro horário'

        return True, None

    def alterar_recorrente(obj, hora_inicio, hora_final, tipo_recorrencia='todos'):
        # **** EDITA ESTE E OS OUTROS

        # obj: quem está sendo editado
        # tipo_recorrencia: recorencia selecionada no form de alteração
        # tipos de recorencia considerados aqui:
        # - 'este_e_proximos' 'Este e os próximos da recorrência'
        # - 'este_e_anteriores' 'Este e os anteriores da recorrência'
        # - 'todos' 'Todos da recorrência'

        # Montando as datas que serão editadas
        # - ALTERAR 'este_e_proximos': VOU EDITAR (Este) E (Todos os proximos da recorrencia)
        # - ALTERAR 'este_e_anteriores': VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
        # - ALTERAR 'todos': VOU EDITAR (Este) E (Todos da recorrencia)
        datas_para_alterar = PlanoIndividualTrabalhoAtendimento.objects.filter(recorrencia=obj.recorrencia).order_by('timestamp_data_hora_inicio')
        if datas_para_alterar.filter(original__isnull=False).exists():
            datas_para_alterar = datas_para_alterar.filter(Q(original__isnull=False) | Q(original__isnull=True, homologado=False))
        else:
            datas_para_alterar = datas_para_alterar.filter(original__isnull=True)
        if tipo_recorrencia == 'este_e_proximos':
            # VOU EDITAR (Este) E (Todos os proximos da recorrencia)
            datas_para_alterar = datas_para_alterar.filter(timestamp_data_hora_inicio__gte=obj.timestamp_data_hora_inicio)
        if tipo_recorrencia == 'este_e_anteriores':
            # VOU EDITAR (Este) E (Todos os anteriores da recorrencia)
            datas_para_alterar = datas_para_alterar.exclude(timestamp_data_hora_inicio__lte=obj.timestamp_data_hora_inicio)
        # tipo_recorrencia == 'todos':
        # VOU EDITAR (Este) E (Todos da recorrencia)
        # datas_para_alterar (completo)

        # Alterando os dados
        # Este
        obj.hora_inicio = hora_inicio
        obj.hora_final = hora_final
        obj.timestamp_data_hora_inicio = datetime.datetime(
            obj.data.year, obj.data.month, obj.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
        ).timestamp()
        obj.alterado = True
        obj.save()
        # Outros
        for d in datas_para_alterar:
            d.hora_inicio = hora_inicio
            d.hora_final = hora_final
            d.timestamp_data_hora_inicio = datetime.datetime(
                d.data.year, d.data.month, d.data.day, hora_inicio.hour, hora_inicio.minute, hora_inicio.second
            ).timestamp()
            d.alterado = True
            d.save()

        return True, None

    def pode_cancelar_edicao_atendimento(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        if not self.eh_copia():
            return False

        return self.alterado


class PlanoIndividualTrabalhoEntregas(models.ModelPlus):
    pit = models.ForeignKeyPlus(
        'pgd2.PlanoIndividualTrabalho', verbose_name=f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2}', related_name='pit_planejamento_pgd2'
    )
    original = models.ForeignKeyPlus('self', null=True, blank=True, editable=False)
    homologado = models.BooleanField(default=False, editable=False)

    entrega_pes = models.ForeignKeyPlus(
        'pgd2.PlanoEntregasSetorialEntregas', verbose_name='Entrega PES', related_name='pes_entregapit_pgd2', null=True
    )

    titulo = models.CharFieldPlus(verbose_name='Título')
    descricao = models.TextField(verbose_name='Descrição', null=True, blank=True)
    data_prazo = models.DateFieldPlus(verbose_name='Prazo', null=True, blank=True)
    tempo_planejado = models.DecimalFieldPlus(verbose_name='Tempo planejado', help_text='Em horas', default=0)

    cancelado = models.BooleanField('Cancelado', default=False)

    tempo_executado = models.DecimalFieldPlus(verbose_name='Tempo executado', default=0, editable=False)
    qtd_executado = models.DecimalFieldPlus(verbose_name='Executado', default=0, editable=False)

    class Meta:
        verbose_name = f'Entrega do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'
        verbose_name_plural = f'Entregas do {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}'

    def __str__(self):
        return f'Entrega {self.titulo} do {self.pit}'

    def eh_copia(self):
        return bool(self.original)

    def eh_original(self):
        return not self.original

    def tem_copia(self):
        return PlanoIndividualTrabalhoEntregas.objects.filter(original__id=self.id).exists()

    def get_copia(self):
        return PlanoIndividualTrabalhoEntregas.objects.filter(original__id=self.id).first()

    def get_execucao_str(self):
        if self.entrega_pes_tem_metrica_de_quantidade():
            return int(self.qtd_executado)
        return None

    def pode_cadastrar_entrega(self, user):
        return self.pit.pode_cadastrar_entrega_rit(user, entrega_pit_id=self.id)

    def pode_editar_entrega(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        if self.entrega_pes and self.entrega_pes.cancelado:
            return False

        if self.cancelado:
            return False

        return not (self.eh_original() and self.tem_copia())

    def pode_cancelar_edicao_entrega(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        if not self.eh_copia():
            return False

        return not self.cancelado

    def pode_remover_entrega(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        # se a entrega estiver vinculada a um RIT não pode
        if RelatorioIndividualTrabalho.objects.filter(entrega_pit_id=self.id).exists():
            return False

        if not self.eh_original():
            return False

        return not self.homologado

    def pode_cancelar_entrega(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False

        if self.cancelado:
            return False

        if not (self.eh_original() and not self.tem_copia()):
            return False

        return self.homologado

    def pode_descancelar_entrega(self, user=None):
        if user and not self.pit.pode_editar(user):
            return False
        return self.cancelado

    def get_entregas_rit(self):
        return RelatorioIndividualTrabalho.objects.filter(entrega_pit=self, entrega_pit__cancelado=False, original__isnull=True).order_by('titulo')

    def estah_cancelada_entrega_pes_ou_entrega_pit(self):
        return self.cancelado or (self.entrega_pes and self.entrega_pes.cancelado)

    def estah_cancelada_entrega_pes_ou_entrega_pit_str(self):
        if self.cancelado:
            return f'Entrega {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} cancelada'
        elif self.entrega_pes and self.entrega_pes.cancelado:
            return 'Entrega PES cancelada'
        return None

    def estah_cancelada_entrega_pes_str(self):
        if self.entrega_pes and self.entrega_pes.cancelado:
            return 'Entrega PES cancelada'
        return None

    def estah_cancelada_entrega_pit_str(self):
        if self.cancelado:
            return f'Entrega {nomenclatura.plano_individual_de_trabalho_sigla_pgd2} cancelada'
        return None

    def entrega_pes_tem_metrica_de_quantidade(self):
        return bool(self.entrega_pes and self.entrega_pes.metrica == PlanoEntregasSetorialEntregas.QUANTIDADE)

    # --------------------------
    # API
    # --------------------------
    def get_tipo_contribuicao_para_api(self):
        """
        Tipos de contribuição que o participante pode realizar:

        1 Contribuição para entrega da própria unidade de execução do participante;
        2 Contribuição não vinculada diretamente a entrega, mas necessária ao adequado
          funcionamento administrativo (por exemplo, Atividades de apoio, assessoramento e desenvolvimento,
          e Atividades de gestão de equipes e entregas);
        3 Contribuição vinculada a entrega de outra unidade de execução, inclusive de outros órgãos e entidades

        """
        se = self.pit.get_setores_envolvidos().filter(pode_homologar=True).first()

        if self.entrega_pes:
            if self.entrega_pes.pes == se.pes:
                return 1
            if self.entrega_pes.pes != se.pes:
                return 3
        return 2

    def get_id_plano_entregas_para_api(self):
        if self.get_tipo_contribuicao_para_api() == 1:
            return self.entrega_pes.pes.identificador_externo
        return None

    def get_id_entrega_para_api(self):
        if self.get_tipo_contribuicao_para_api() == 1:
            return self.entrega_pes.id
        return None

    def get_percentual_contribuicao_para_api(self):
        if self.tempo_planejado and self.pit.tempo_planejado_total:
            perc = math.ceil((self.tempo_planejado / self.pit.tempo_planejado_total) * 100)
            if perc > 100:
                return 100
            return math.ceil((self.tempo_planejado / self.pit.tempo_planejado_total) * 100)
        return 0


class PitSetores(models.ModelPlus):
    pit = models.ForeignKeyPlus(
        'pgd2.PlanoIndividualTrabalho', verbose_name=f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2}', related_name='pit_pitsetores_pgd2'
    )
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', null=True, verbose_name='PES', related_name='pit_pitpes_pgd2')
    setor = models.ForeignKeyPlus('rh.Setor', null=True, verbose_name='Setor', related_name='setor_pitsetores_pgd2')
    pode_homologar = models.BooleanField(default=True)

    def __str__(self):
        if self.pes and self.setor:
            if self.pode_homologar:
                return mark_safe(f'<strong>[Principal e apto para homologar {nomenclatura.pit_rit_pgd2}] </strong> {self.pes.get_verbose_simples()}')
            return mark_safe(self.pes.get_verbose_simples())
        mensagem_complementar = '<ul><li>(1) Verificar o seu último setor do período relacionado a este plano. Isso pode ser verificado por você mesmo ou pela Gestão de Pessoas. </li> <li>(2) Verifique se o seu último setor do período relacionado a este plano possui PES homologado para o mesmo período. Isso pode ser verficado por você mesmo ou pelo chefe do seu último setor do período relacionado a este plano</li> </ul>'
        if not self.setor and self.pes:
            return mark_safe(f'<strong>Não foi possível calcular o Setor do PES principal e apto para homologar.</strong> {mensagem_complementar}')
        if self.setor and not self.pes:
            return mark_safe(f'<strong>Não foi possível calcular o PES principal e apto para homologar.</strong> {mensagem_complementar}')
        return mark_safe(f'<strong>Não foi possível calcular Setor e o PES principal e apto para homologar.</strong> {mensagem_complementar}')

    def tem_erro(self):
        return not self.pes or not self.setor


class PitSolicitacaoAnalise(models.ModelPlus):
    pit = models.ForeignKeyPlus('pgd2.PlanoIndividualTrabalho', verbose_name=f'{nomenclatura.plano_individual_de_trabalho_sigla_pgd2}')

    PIT = 1
    RIT = 2
    OBJETO_PARECER_CHOICES = [[PIT, 'PIT'], [RIT, 'RIT']]
    objeto_parecer = models.PositiveIntegerField('Objeto', null=True, choices=OBJETO_PARECER_CHOICES)

    tem_pendencia_aprovacao = models.BooleanField(default=False)
    tem_pendencia_homologacao = models.BooleanField(default=False)
    finalizado = models.BooleanField(default=False)

    data_prazo_envio = models.DateTimeFieldPlus('Prazo para envio da solicitação', null=True, editable=False)
    data_envio = models.DateTimeFieldPlus('Data do envio da solicitação', null=True, editable=False)


class PitSolicitacaoAnaliseSetor(models.ModelPlus):
    solicitacao = models.ForeignKeyPlus('pgd2.PitSolicitacaoAnalise', verbose_name='Solicitação')
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', related_name='setor_pitsolicitacaoanalise_pgd2')

    APROVACAO = 1
    HOMOLOGACAO = 2
    TIPO_PARECER_CHOICES = [[APROVACAO, 'Aprovação'], [HOMOLOGACAO, 'Homologação']]
    tipo_parecer = models.PositiveIntegerField('Tipo Parecer', choices=TIPO_PARECER_CHOICES)

    parecer = models.BooleanField('Parecer', null=True)

    data_prazo_parecer = models.DateTimeFieldPlus('Data prazo para o parecer', null=True, editable=False)
    data_parecer = models.DateTimeFieldPlus('Data do parecer', null=True, editable=False)
    servidor_parecer = models.ForeignKeyPlus(
        'rh.Servidor', null=True, editable=False, verbose_name='Servidor', related_name='servidorparecer_pitsolicitacaoanalise_pgd2'
    )

    def eh_tipo_parecer_aprovacao(self):
        return self.tipo_parecer == self.APROVACAO

    def eh_tipo_parecer_homologacao(self):
        return self.tipo_parecer == self.HOMOLOGACAO

    def get_tipo_parecer_str(self):
        if self.solicitacao.tem_pendencia_aprovacao and self.tipo_parecer == PitSolicitacaoAnaliseSetor.HOMOLOGACAO:
            return f'{self.get_tipo_parecer_display()} (só pode haver Homologação após todas as Aprovações serem realizadas)'
        return self.get_tipo_parecer_display()


# ====================================================
# RIT (cadastro de cada entrega executada)
# ====================================================


def file_upload_to(instance, filename):
    PRIVATE_ROOT_DIR = 'pgd2'
    path = f'{PRIVATE_ROOT_DIR}/{instance.pk}'
    ext = filename.split('.')[-1]
    if instance.pk:
        filename = f'{instance.pk}.{ext}'
    else:
        filename = f'{uuid4().hex}.{ext}'
    return os.path.join(path, filename)


class RelatorioIndividualTrabalho(models.ModelPlus):
    entrega_pit = models.ForeignKeyPlus('pgd2.PlanoIndividualTrabalhoEntregas', verbose_name='Entrega', editable=False, null=True)

    titulo = models.CharFieldPlus(verbose_name='Título', null=True)
    descricao = models.TextField(verbose_name='Descrição')
    tempo_executado = models.DecimalFieldPlus(verbose_name='Horas da Execução', help_text='Em horas')
    perc_executada_em_teletrabalho = models.DecimalFieldPlus(verbose_name='% executado em teletrabalho', default=0)
    tempo_executada_em_teletrabalho = models.DecimalFieldPlus(editable=False, default=0)

    data_inicio = models.DateFieldPlus(verbose_name='Data Início', null=True, blank=True)
    data_fim = models.DateFieldPlus(verbose_name='Data Final', null=True, blank=True)

    quantidade_progresso = models.DecimalFieldPlus(verbose_name='Quantidade/Progresso', default=0)

    anexo = models.PrivateFileField('Arquivo', upload_to=file_upload_to, max_length=400, blank=True, null=True)

    gitlab_project_id = models.PositiveIntegerFieldPlus('ID do projeto GitLab', null=True, blank=True, editable=False)
    gitlab_mr_iid = models.PositiveIntegerFieldPlus('IID do MR no GitLab', null=True, blank=True, editable=False)

    class Meta:
        verbose_name = f'{nomenclatura.relatorio_individual_de_trabalho_pgd2}'
        verbose_name_plural = f'{nomenclatura.relatorios_individuais_de_trabalho_pgd2}'
        constraints = [
            models.UniqueConstraint(
                fields=['gitlab_project_id', 'gitlab_mr_iid'],
                condition=Q(gitlab_mr_iid__isnull=False),
                name='uniq_rit_gitlab_mr',
            )
        ]

    def __str__(self):
        return f'Entrega: {self.titulo} | {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2} {format_datetime(self.entrega_pit.pit.data_inicio)} a {format_datetime(self.entrega_pit.pit.data_fim)} | {self.entrega_pit.pit.adesao.servidor}'

    def get_quantidade_progresso_str(self):
        if self.entrega_pit.entrega_pes_tem_metrica_de_quantidade():
            return int(self.quantidade_progresso)
        return None

    def se_estah_vinculado_a_entrega_cancelada(self):
        if self.entrega_pit.cancelado:
            return True

        return bool(self.entrega_pit.entrega_pes and self.entrega_pit.entrega_pes.cancelado)

    def pode_editar_entrega_rit(self, user):
        pode = self.entrega_pit.pit.pode_cadastrar_entrega_rit(user=user)
        if pode and not self.pode_editar_entrega_rit_regra_especifica(user=user):
            pode = False
        return pode

    def pode_editar_entrega_rit_regra_especifica(self, user):
        return not self.se_estah_vinculado_a_entrega_cancelada()


class RelatorioIndividualTrabalhoQuestionario(models.ModelPlus):
    periodo_pit_rit = models.ForeignKeyPlus(
        'pgd2.PeriodoPitRit',
        verbose_name=f'Período {nomenclatura.plano_individual_de_trabalho_sigla_pgd2}/{nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        editable=False,
    )
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', related_name='setor_ritrelatorio_pgd2')

    servidor_respondente = models.ForeignKeyPlus('rh.Servidor', verbose_name='Servidor', related_name='servidorrespondente_ritrelatorio_pgd2')
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
        verbose_name = f'Questionário do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
        verbose_name_plural = f'Questionários do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'

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

    @staticmethod
    def questionarios_a_responder_como_chefe(servidor):
        # =================================
        # Sabendo quais questinarios de pesquisa o servidor deve responder
        # =================================

        # Períodos que deve ter o preenchimento
        periodos_deve_preencher = PeriodoPitRit.objects.filter(
            cancelado=False, preencher_questionario_pesquisa=True, data_fim__lt=get_datetime_now().date()
        )

        # Setores que eh chefe hoje
        setores_para_preencher = setores_que_sou_chefe_hoje(servidor).order_by('sigla')

        # Sabendo quais setores não foram preenchidos para cada periodo que deve preencher
        lista_setor_periodo_a_preencher = []
        lista_setores_para_preencher = []
        for periodo in periodos_deve_preencher:
            for setor in setores_para_preencher:
                if not RelatorioIndividualTrabalhoQuestionario.objects.filter(
                    periodo_pit_rit=periodo, setor=setor, questionario_de_chefe=True
                ).exists():
                    lista_setor_periodo_a_preencher.append((setor, periodo))
                    lista_setores_para_preencher.append(setor)

        return lista_setor_periodo_a_preencher, lista_setores_para_preencher


class RelatorioIndividualTrabalhoDistribuicaoHoras(models.ModelPlus):
    rit = models.ForeignKeyPlus(
        'pgd2.PlanoIndividualTrabalho',
        verbose_name=f'{nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        related_name='pit_distribuicaohoras_pgd2',
    )

    PERIODO_RIT = 1
    SEMESTRE_ANTES_RIT = 2
    COMPENSACAO_ESPECIFICA = 3
    SEMESTRE_POS_RIT = 4
    SEMESTRE_RIT = 5
    TIPO_DISTRIBUICAO_CHOICES = [
        [PERIODO_RIT, f'Período do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'],
        [
            SEMESTRE_ANTES_RIT,
            f'Meses (no semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}) anteriores ao {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        ],
        [COMPENSACAO_ESPECIFICA, 'Compensacao específica'],
        [SEMESTRE_RIT, f'Semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'],
        [
            SEMESTRE_POS_RIT,
            f'Meses (no semestre do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}) posteriores ao {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}',
        ],
    ]
    tipo = models.PositiveIntegerField('Tipo', choices=TIPO_DISTRIBUICAO_CHOICES, default=PERIODO_RIT)

    saldo_externo = models.ForeignKeyPlus('ponto.SaldoExterno', related_name='saldoexterno_distribuicaohoras_pgd2')
    ch_distribuida = models.DecimalFieldPlus(verbose_name='CH distribuída')

    # Uso específico para COMPENSACAO_ESPECIFICA
    data = models.DateFieldPlus(verbose_name='Data compensação', blank=True, null=True)
    compensacao_especifica = models.ForeignKeyPlus(
        'ponto.RecessoOpcaoEscolhida', blank=True, null=True, related_name='cespecifica_distribuicaohoras_pgd2'
    )

    class Meta:
        verbose_name = f'Distribuição de Horas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'
        verbose_name_plural = f'Distribuições de Horas do {nomenclatura.relatorio_individual_de_trabalho_sigla_pgd2}'


# ====================================================
# API
# ====================================================


class ParticipantePgd(models.ModelPlus):
    """
    Considerando
    - https://api.pgd.gestao.gov.br/docs#/participante/

    Mapeia servidor como partcipante do PGD
    - Faz as vezes do TCR para a API

    """

    servidor = models.OneToOneFieldPlus('rh.Servidor', verbose_name='Servidor')

    # Cód SIAPE de lotação do servidor
    cod_unidade_lotacao = models.IntegerFieldPlus(verbose_name='Cód. Siape da Lotação')

    # Modalidade e regime de execução do trabalho do participante, restrito a uma das cinco opções:
    # 1 - Presencial 2 - Teletrabalho parcial 3 - Teletrabalho integral 4 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII) 5 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)
    # Regras de validação: Só é possível a escolha de uma das cinco opções.
    modalidade_execucao = models.IntegerFieldPlus(verbose_name='Modalide de Execução PGD')

    # Data de assinatura do Termo de Ciência e Responsabilidade (TCR) referente ao previsto no inciso IV do art. 11 do Decreto 11.072/2022.
    data_assinatura_tcr = models.CharFieldPlus(verbose_name='Data de assinatura TCR')

    # Valores permitidos para a situacao do agente público no Programa de Gestão e Desempenho (PGD):
    # 0: Inativo; 1: Ativo.
    situacao = models.IntegerFieldPlus(verbose_name='Situação API PGD', null=True)

    deve_enviar_pela_api = models.BooleanField(verbose_name='Deve enviar pela API PGD', default=False)
    data_hora_envio_api = models.DateTimeFieldPlus(verbose_name='Data/hora envio pela API PGD', null=True)

    class Meta:
        verbose_name = 'Participante PGD - API'
        verbose_name_plural = 'Participantes PGD - API'

    def __str__(self):
        return str(self.servidor)

    def get_modalidade_execucao_display(self):
        # 1 - Presencial
        # 2 - Teletrabalho parcial
        # 3 - Teletrabalho integral
        # 4 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)
        # 5 - Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)
        if self.modalidade_execucao == 1:
            return 'Presencial'
        if self.modalidade_execucao == 2:
            return 'Teletrabalho presencial'
        if self.modalidade_execucao == 3:
            return 'Teletrabalho integral'
        if self.modalidade_execucao == 4:
            return 'Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, VIII)'
        return 'Teletrabalho com residência no exterior (Dec.11.072/2022, art. 12, §7°)'


class LogApi(models.ModelPlus):
    """
    Considerando
    - https://api.pgd.gestao.gov.br/docs#/participante/

    """

    eh_preparacao_para_primeiro_envio = models.BooleanField(
        verbose_name='É preparação para o primeiro envio pela API PGD 2', default=False, editable=False
    )
    realizado_com_sucesso = models.BooleanField(verbose_name='Realizado com sucesso sem erros impeditivos', default=False, editable=False)

    data_hora_inicio = models.DateTimeFieldPlus(verbose_name='Data e hora do início', editable=False)
    data_hora_fim = models.DateTimeFieldPlus(verbose_name='Data e hora do fim', null=True, editable=False)

    erro_impeditivo = models.TextField(verbose_name='Erros que impediram seguir enviando', editable=False, null=True)
    erro_nao_impeditivo = models.TextField(verbose_name='Erros que não impediram seguir enviando', editable=False, null=True)

    data_proximo_envio_por_sucesso = models.DateFieldPlus(verbose_name='Data do próximo envio em caso de sucesso', null=True, editable=False)
    data_proximo_envio_por_erro = models.DateFieldPlus(verbose_name='Data do próximo envio em caso de erro', null=True, editable=False)

    qtd_envios_pes = models.IntegerFieldPlus(verbose_name='PESs para enviar', null=True)
    qtd_envios_erros_pes = models.IntegerFieldPlus(verbose_name='PESs com erro no envio', null=True)

    qtd_envios_participante = models.IntegerFieldPlus(verbose_name='Participantes para enviar', null=True)
    qtd_envios_erros_participante = models.IntegerFieldPlus(verbose_name='Participantes com erro no envio', null=True)

    qtd_envios_pit = models.IntegerFieldPlus(verbose_name='PITs para enviar', null=True)
    qtd_envios_erros_pit = models.IntegerFieldPlus(verbose_name='PITs com erro no envio', null=True)

    url = models.CharFieldPlus(verbose_name='URL', null=True, editable=False)

    class Meta:
        verbose_name = 'Log API PGD 2'
        verbose_name_plural = 'Logs API PGD 2'

    def __str__(self):
        return self.data_hora_inicio.strftime('%d/%m/%Y %H:%M')

    def get_qtd_erros_envio_pes(self):
        if self.data_hora_fim:
            return self.qtd_envios_erros_pes
        return self.logapipesenvio_set.filter(status=LogApiPesEnvio.STATUS_ERRO_ENVIO).count()

    get_qtd_erros_envio_pes.short_description = 'PESs com erro no envio'

    def get_qtd_erros_envio_participante(self):
        if self.data_hora_fim:
            return self.qtd_envios_erros_participante
        return self.logapiparticipanteenvio_set.filter(status=LogApiPesEnvio.STATUS_ERRO_ENVIO).count()

    get_qtd_erros_envio_participante.short_description = 'Participantes com erro no envio'

    def get_qtd_erros_envio_pits(self):
        if self.data_hora_fim:
            return self.qtd_envios_erros_pit
        return self.logapipitenvio_set.filter(status=LogApiPesEnvio.STATUS_ERRO_ENVIO).count()

    get_qtd_erros_envio_pits.short_description = 'PITs com erro no envio'


class LogApiDetalhe(models.ModelPlus):
    log = models.ForeignKeyPlus('pgd2.LogApi', verbose_name='Log')
    data = models.DateTimeFieldPlus('Data', auto_now_add=True, editable=False)
    url = models.CharFieldPlus(verbose_name='URL', null=True, editable=False)
    erro_envio = models.TextField(verbose_name='Erro do envio', null=True, editable=False)

    class Meta:
        verbose_name = 'Log API PGD 2 - Geral'
        verbose_name_plural = 'Logs API PGD 2 - Geral'

    def __str__(self):
        return str(self.log)

    @staticmethod
    def registrar(log, url=None, erro_envio=None):
        if log:
            LogApiDetalhe.objects.create(log=log, url=url, erro_envio=erro_envio)


class LogApiPesEnvio(models.ModelPlus):
    log = models.ForeignKeyPlus('pgd2.LogApi', verbose_name='Log')
    pes = models.ForeignKeyPlus('pgd2.PlanoEntregasSetorial', verbose_name='PES')
    dados_envio = models.JSONField(verbose_name='Dados envio', null=True)

    STATUS_PENDENTE_ENVIO = 1
    STATUS_ENVIADO = 2
    STATUS_ERRO_ENVIO = 3
    STATUS_CHOICES = [
        [STATUS_PENDENTE_ENVIO, 'Pendente de envio'],
        [STATUS_ENVIADO, 'Enviado'],
        [STATUS_ERRO_ENVIO, 'Erro no envio'],
    ]
    status = models.PositiveIntegerField(verbose_name='Status', choices=STATUS_CHOICES, default=STATUS_PENDENTE_ENVIO)
    erro_envio = models.TextField(verbose_name='Erro do envio', null=True, editable=False)
    data_hora_envio_erro = models.DateTimeFieldPlus(verbose_name='Data e hora do envio/erro', null=True)

    class Meta:
        verbose_name = 'Log API PGD 2 - Envio PES'
        verbose_name_plural = 'Logs API PGD 2 - Envio PESs'

    @staticmethod
    def registrar_envio(log, identificador_externo, erro_envio=None):
        if log:
            log_pes = LogApiPesEnvio.objects.filter(log=log, pes__identificador_externo=identificador_externo)
            if erro_envio:
                log_pes.update(erro_envio=erro_envio, status=LogApiPesEnvio.STATUS_ERRO_ENVIO, data_hora_envio_erro=get_datetime_now())
            else:
                log_pes.update(erro_envio=None, status=LogApiPesEnvio.STATUS_ENVIADO, data_hora_envio_erro=get_datetime_now())


class LogApiParticipanteEnvio(models.ModelPlus):
    log = models.ForeignKeyPlus('pgd2.LogApi', verbose_name='Log')
    participante = models.ForeignKeyPlus('pgd2.ParticipantePgd', verbose_name='Participante')
    dados_envio = models.JSONField(verbose_name='Dados envio', null=True)

    STATUS_PENDENTE_ENVIO = 1
    STATUS_ENVIADO = 2
    STATUS_ERRO_ENVIO = 3
    STATUS_CHOICES = [
        [STATUS_PENDENTE_ENVIO, 'Pendente de envio'],
        [STATUS_ENVIADO, 'Enviado'],
        [STATUS_ERRO_ENVIO, 'Erro no envio'],
    ]
    status = models.PositiveIntegerField(verbose_name='Status', choices=STATUS_CHOICES, default=STATUS_PENDENTE_ENVIO)
    erro_envio = models.TextField(verbose_name='Erro do envio', null=True, editable=False)
    data_hora_envio_erro = models.DateTimeFieldPlus(verbose_name='Data e hora do envio/erro', null=True)

    class Meta:
        verbose_name = 'Log API PGD 2 - Envio Participante'
        verbose_name_plural = 'Logs API PGD 2 - Envio Participantes'

    @staticmethod
    def registrar_envio(log, matricula, erro_envio=None):
        if log:
            log_p = LogApiParticipanteEnvio.objects.filter(log=log, participante__servidor__matricula=matricula)
            if erro_envio:
                log_p.update(erro_envio=erro_envio, status=LogApiParticipanteEnvio.STATUS_ERRO_ENVIO, data_hora_envio_erro=get_datetime_now())
            else:
                log_p.update(erro_envio=None, status=LogApiParticipanteEnvio.STATUS_ENVIADO, data_hora_envio_erro=get_datetime_now())


class LogApiPitEnvio(models.ModelPlus):
    log = models.ForeignKeyPlus('pgd2.LogApi', verbose_name='Log')
    pit = models.ForeignKeyPlus('pgd2.PlanoIndividualTrabalho', verbose_name='PIT')
    dados_envio = models.JSONField(verbose_name='Dados envio', null=True)
    data_hora_envio_erro = models.DateTimeFieldPlus(verbose_name='Data e hora do envio/erro', null=True)

    STATUS_PENDENTE_ENVIO = 1
    STATUS_ENVIADO = 2
    STATUS_ERRO_ENVIO = 3
    STATUS_CHOICES = [
        [STATUS_PENDENTE_ENVIO, 'Pendente de envio'],
        [STATUS_ENVIADO, 'Enviado'],
        [STATUS_ERRO_ENVIO, 'Erro no envio'],
    ]
    status = models.PositiveIntegerField(verbose_name='Status', choices=STATUS_CHOICES, default=STATUS_PENDENTE_ENVIO)
    erro_envio = models.TextField(verbose_name='Erro do envio', null=True, editable=False)

    class Meta:
        verbose_name = 'Log API PGD 2 - Envio PIT'
        verbose_name_plural = 'Logs API PGD 2 - Envio PITs'

    @staticmethod
    def registrar_envio(log, pit_id, erro_envio=None):
        if log:
            log_p = LogApiPitEnvio.objects.filter(log=log, pit_id=pit_id)
            if erro_envio:
                log_p.update(erro_envio=erro_envio, status=LogApiPitEnvio.STATUS_ERRO_ENVIO, data_hora_envio_erro=get_datetime_now())
            else:
                log_p.update(erro_envio=None, status=LogApiPitEnvio.STATUS_ENVIADO, data_hora_envio_erro=get_datetime_now())


class SetorPgdApi(models.ModelPlus):
    setor_siape = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor SIAPE', null=True, related_name='setor_pgd_siape')
    setor_suap = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor SUAP', null=True, blank=True, related_name='setor_pgd_suap')

    class Meta:
        verbose_name = 'Setor PGD API'
        verbose_name_plural = 'Setores PGD API'
        unique_together = ('setor_siape', 'setor_suap')

    @staticmethod
    def pode_cadastrar_alterar(user):
        return ComissaoPGD.user_estah_em_gestao_pgd(user)

    @staticmethod
    def carregar_setores_siape_inicial():
        def get_setor_suap_do_setor_siape(_setor_busca, _sigla_setor, _uo_sigla_setor):
            """
            _sigla_setor: sigla do setor que vai ser buscado
            _uo_sigla_setor: sigla da UO do setor que vai ser buscado

            - Considerando os diferentes padrões de nomenclatura de setor
            - Precisamos elaborar várias estratégias de busca partindo de um padrão definido em configuração
            """

            if '/' in _setor_busca.sigla:
                setor_siape = Setor.objects.suap().filter(sigla=_setor_busca.sigla)
                if setor_siape:
                    return setor_siape.first()

            # Veja em comum/comnfiguracao/pdd2
            padrao_sigla = int(Configuracao.get_valor_por_chave('pgd2', 'api_padrao_sigla_setor') or 1)

            # Pega o separador da _sigla_setor
            separador = '/'
            if '-' in _sigla_setor:
                separador = '-'

            # Pega o setor e a uo na _sigla_setor de acordo com o padrao_sigla
            setor_sigla_setor = None
            uo_sigla_setor = None
            if padrao_sigla == 1:
                split_sigla_setor = _sigla_setor.split(separador)
                setor_sigla_setor = split_sigla_setor[0]
                if len(split_sigla_setor) > 1:
                    uo_sigla_setor = split_sigla_setor[1]
            else:
                # 2
                split_sigla_setor = _sigla_setor.split(separador)
                uo_sigla_setor = split_sigla_setor[0]
                if len(split_sigla_setor) > 1:
                    setor_sigla_setor = split_sigla_setor[1]
                else:
                    setor_sigla_setor = split_sigla_setor[0]
                    uo_sigla_setor = None

            if not setor_sigla_setor:
                return None

            # Estratégia 1: busca direta pela Sigla do Setor
            setor_siape = Setor.objects.suap().filter(sigla=setor_sigla_setor, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Estratégia 2: busca direta pela Sigla do Setor / sigla da UO do Setor
            sigla_busca = None
            if padrao_sigla == 1:
                sigla_busca = f'{setor_sigla_setor}{separador}{_uo_sigla_setor}'
            else:
                sigla_busca = f'{_uo_sigla_setor}{separador}{setor_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Estratégia 3
            try:
                # Buscando a sigla do campus do setor equivalente da UO relacionada ao _sigla_setor
                # - Exemplo de problema que resolve: COAES/SPO (siape) e COAES/SPP (suap)
                # Troca a sigla da UO do setor para resolver o problema do exemplo
                sigla_uo = (
                    UnidadeOrganizacional.objects.filter(sigla=_uo_sigla_setor, equivalente=Setor.objects.suap().get(sigla=_sigla_setor).uo)
                    .first()
                    .setor.sigla
                )
                sigla_uo = sigla_uo.split(separador)[1]

                sigla_busca = None
                if padrao_sigla == 1:
                    sigla_busca = f'{setor_sigla_setor}{separador}{sigla_uo}'
                else:
                    sigla_busca = f'{sigla_uo}{separador}{setor_sigla_setor}'
                setor_siape = Setor.objects.suap().filter(sigla=sigla_busca)
                if setor_siape:
                    return setor_siape.first()
            except Exception:
                pass

            # Outras estratégias
            # - Serão exeuctadas independentemente do padrao_sigla e do separador
            # ----------------------
            # Busca pelo padrão "SETORUO"
            sigla_busca = f'{setor_sigla_setor}{uo_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Busca pelo padrão "SETOR-UO"
            sigla_busca = f'{setor_sigla_setor}-{uo_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Busca pelo padrão "UO - SETOR"
            sigla_busca = f'{uo_sigla_setor} - {setor_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Busca pelo padrão "SETOR.UO"
            sigla_busca = f'{setor_sigla_setor}.{uo_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Busca pelo padrão "SETOR/CUO: onde o C é um prefixo da UO"
            sigla_busca = f'{setor_sigla_setor}/C{uo_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            # Busca pelo padrão "SETOR"
            sigla_busca = f'{setor_sigla_setor}'
            setor_siape = Setor.objects.suap().filter(sigla=sigla_busca, uo__sigla=_uo_sigla_setor)
            if setor_siape:
                return setor_siape.first()

            return None

        def get_id_setor_suap(sigla_setor):
            setor_original = Setor.objects.siape().filter(sigla=sigla_setor).first()
            setor = Setor.objects.siape().filter(sigla=sigla_setor).first()

            codigo_siape = None
            if setor and setor.sigla and setor.uo and setor.uo.sigla:
                # Busca no próprio setor
                codigo_siape = get_setor_suap_do_setor_siape(setor, setor.sigla, setor.uo.sigla)
                if codigo_siape:
                    return codigo_siape

                # Se não tiver busca nos superiores
                setor = setor.superior
                while setor is not None:
                    codigo_siape = get_setor_suap_do_setor_siape(setor, setor.sigla, setor.uo.sigla)
                    if codigo_siape:
                        break
                    setor = setor.superior

                if setor.uo.sigla == get_sigla_reitoria():
                    try:
                        # Vai usar o setor equivalente do campus siape relacionado ao campus suap do setor suap original
                        uo_siape = UnidadeOrganizacional.objects.suap().filter(sigla=setor_original.uo.sigla).first()
                        setor_equivalente = uo_siape.setor
                        setor_siape = Setor.objects.suap().filter(sigla=setor_equivalente.sigla)
                        if setor_siape:
                            codigo_siape = setor_siape.first()
                    except Exception:
                        pass

            if not codigo_siape:
                try:
                    uo_siape = UnidadeOrganizacional.objects.suap().filter(sigla=sigla_setor).first()
                    setor_equivalente = uo_siape.setor
                    setor_siape = Setor.objects.suap().filter(sigla=setor_equivalente.sigla)
                    if setor_siape:
                        codigo_siape = setor_siape.first()
                except Exception:
                    pass

            return codigo_siape

        setores_pgd = Setor.objects.siape().filter(codigo__isnull=False, excluido=False).order_by('sigla')
        dados = []
        for setor_siape in tqdm.tqdm(setores_pgd):
            setor_suap = get_id_setor_suap(setor_siape.sigla)
            dados.append(SetorPgdApi(setor_siape=setor_siape, setor_suap=setor_suap))

        SetorPgdApi.objects.bulk_create(dados)

    @staticmethod
    def carregar_setores_siape():
        # Carrega apenas os que faltam
        ids_setores_siape_carregados = SetorPgdApi.objects.all().values_list('setor_siape_id', flat=True)
        setores_siape_a_carregar = Setor.objects.siape().filter(codigo__isnull=False, excluido=False).exclude(id__in=ids_setores_siape_carregados)
        if setores_siape_a_carregar:
            for setor_siape in setores_siape_a_carregar:
                s = SetorPgdApi()
                s.setor_siape = setor_siape
                s.save()

    @staticmethod
    def carregar_setores():

        # Tenta evitar que usuário tenha que se preocupar em cadastrar Associação entre Setores SIAPE e SUAP

        def excluir_repeticoes():
            ids_excluir = []
            setores = SetorPgdApi.objects.all()
            for setor in setores:
                if SetorPgdApi.objects.filter(setor_siape=setor.setor_siape).count() > 1:
                    ids_excluir.append(setor.id)
            if ids_excluir:
                SetorPgdApi.objects.filter(id__in=ids_excluir).delete()

        def get_codigo_siape_superior(setor):
            from pgd2.api_pgd2 import get_codigo_siape_setor_metodo3

            codigo_siape = get_codigo_siape_setor_metodo3(setor)
            return Setor.objects.siape().ativos().filter(codigo=codigo_siape).first()

        def atualizar_relacao_siape_suap():
            # Atualizar relação de setores SUAP x SIAPE (pela cod siape equivalente e sigla)
            # - Pega os SIAPE que não tem associação com setor SUAP
            setores_pgd = SetorPgdApi.objects.filter(setor_suap__isnull=True).order_by('setor_siape__sigla')
            for setor_pgd in setores_pgd:
                if setor_pgd.setor_siape.codigo:
                    codigo_siape = int(setor_pgd.setor_siape.codigo)
                    # Pelo código SIAPE equivalente
                    setor_suap = get_setores_pgd().annotate(equivalencia_codigo_int=Cast('equivalencia_codigo', IntegerField()))
                    setor_suap = setor_suap.filter(equivalencia_codigo_int=codigo_siape).first()
                    if not setor_suap:
                        # Pela sigla
                        setor_suap = get_setores_pgd().filter(sigla=setor_pgd.setor_siape.sigla).first()
                    if setor_suap:
                        # Atualizar associação
                        setor_pgd.setor_suap = setor_suap
                        setor_pgd.save()

        def atualizar_criar_relacao_siape_suap():
            # Pegar setores SUAP que tem PES e tentar verificar se todos tem setor SIAPE equivalente
            ids_setores_com_pes_aprovado = PlanoEntregasSetorial.get_pess_aprovados().values_list('setor_id', flat=True).distinct()
            setores_suap_com_pes = get_setores_pgd().filter(id__in=ids_setores_com_pes_aprovado)
            for setor_suap_pes in setores_suap_com_pes:
                setor_pgd = SetorPgdApi.objects.filter(setor_suap=setor_suap_pes).first()
                # Se não existir em já cadastrado
                if not setor_pgd:
                    setor_siape = None
                    if setor_suap_pes.equivalencia_codigo:
                        # Tenta pela equivalência
                        codigo_siape = int(setor_suap_pes.equivalencia_codigo)
                        setor_siape = Setor.objects.siape().ativos().annotate(codigo_int=Cast('codigo', IntegerField()))
                        setor_siape = setor_siape.filter(codigo_int=codigo_siape).first()
                    else:
                        # Tenta pela sigla
                        setor_siape = Setor.objects.siape().ativos().filter(sigla=setor_suap_pes.sigla).first()
                    if not setor_siape:
                        # Tenta achar nos setores superiores
                        setor_siape = get_codigo_siape_superior(setor_suap_pes)

                    if setor_siape:
                        # Cadastrar associação
                        setor = SetorPgdApi.objects.filter(setor_siape=setor_siape, setor_suap=setor_suap_pes).first()
                        if not setor:
                            setor = SetorPgdApi()
                        setor.setor_siape = setor_siape
                        setor.setor_suap = setor_suap_pes
                        setor.save()

        # ----------------------------------------------

        excluir_repeticoes()
        SetorPgdApi.carregar_setores_siape()
        atualizar_relacao_siape_suap()
        atualizar_criar_relacao_siape_suap()


# =============================
# Monitoramento
# =============================


class SetorHabilitacao(models.ModelPlus):
    setor = models.OneToOneFieldPlus('rh.Setor', verbose_name='Setor', related_name='setor_habilitacao_pgd2')
    servidores = models.ManyToManyFieldPlus('rh.Servidor', verbose_name='Deve ser um destes servidores', blank=True)
    cargos_emprego = models.ManyToManyFieldPlus('rh.CargoEmprego', verbose_name='Deve ter um destes Cargos Emprego', blank=True)

    documentos = models.ManyToManyFieldPlus('documento_eletronico.DocumentoTexto', verbose_name='Documentos', blank=True)
    processos = models.ManyToManyFieldPlus('processo_eletronico.Processo', verbose_name='Processos', blank=True)

    habilitado = models.BooleanField('Habilitado?', default=False)
    observacao = models.TextField(verbose_name='Observações', blank=True, null=True)

    class Meta:
        verbose_name = 'Habilitação do Setor no PGD'
        verbose_name_plural = 'Habilitação dos Setores no PGD'

    def __str__(self):
        return f'Habilitação PGD {self.setor}'

    def clean(self):
        qs = SetorHabilitacao.objects.filter(setor=self.setor)
        if self.id:
            qs = qs.exclude(id=self.id)
        if qs.exists():
            raise ValidationError('Já existe uma habilitação cadastrada para este setor.')

    @staticmethod
    def setor_estah_habilitado(setor):
        if permite_habilitacao_dos_setores():
            return setor_possui_relacao_siape_suap(setor) and SetorHabilitacao.objects.filter(habilitado=True, setor=setor).exists()
        return True

    @staticmethod
    def get_setores_habilitados():
        return get_setores_pgd().filter(id__in=SetorHabilitacao.objects.filter(habilitado=True).values_list('setor__id', flat=True))


"""
Demanda 2314: Monitorar criação de PES

Popular automaticamente os setores habilitados (Gestão e Comissões > Habilitação > Setores no PGD)
- Devem ser cadastrados todos os setores com PES cadastrado no calendário PES 01/2026 a 03/2026
- E que tem algum PIT homologado relacionado a ele
"""

"""
from pgd2.models import PlanoEntregasSetorial, PlanoIndividualTrabalho, PeriodoPes, SetorHabilitacao

SetorHabilitacao.objects.all().delete()

# periodo relacionado a 01/2026
periodo = PeriodoPes.objects.get(id=7)

pess_aprovados = PlanoEntregasSetorial.get_pess_aprovados().filter(periodo_pes=periodo)
ids_pess_aprovados_com_pit_homologado = []

for pes in pess_aprovados:
    if PlanoIndividualTrabalho.get_pits_foram_homologados_ao_menos_uma_vez_por_pes(pes).exists():
        ids_pess_aprovados_com_pit_homologado.append(pes.id)

pess_aprovados = pess_aprovados.filter(id__in=ids_pess_aprovados_com_pit_homologado).order_by('setor__uo__sigla', 'setor__sigla')

for pes in pess_aprovados:
    obj, _ = SetorHabilitacao.objects.update_or_create(
        setor=pes.setor,
        defaults={
            'setor': pes.setor,
            'habilitado': True,
        }
    )

"""


class MonitoramentoServidor(models.ModelPlus):
    servidor = models.ForeignKeyPlus('rh.Servidor', editable=False, verbose_name='Servidor')

    DEVERIAM_TER_PIT_ATUAL = 1
    DEVERIAM_TER_PIT_NOS_ULTIMOS_3_MESES = 2
    DEVERIAM_TER_RIT_NOS_2_PERIODOS_ANTERIORES = 3
    REGRAS_CHOICES = [
        [DEVERIAM_TER_PIT_ATUAL, 'Servidores em PGD que deveriam ter Plano de Trabalho homologado para o período  atual. Mas não possuem.'],
        [
            DEVERIAM_TER_PIT_NOS_ULTIMOS_3_MESES,
            'Servidores em PGD que deveriam ter Plano de Trabalho homologado nos últimos 3 períodos. Mas não possuem.',
        ],
        [
            DEVERIAM_TER_RIT_NOS_2_PERIODOS_ANTERIORES,
            'Servidores em PGD que deveriam ter Relatório homologado nos 2 períodos anteriores. Mas não possuem.',
        ],
    ]
    regra = models.PositiveIntegerField('Regra', editable=False, choices=REGRAS_CHOICES)

    class Meta:
        verbose_name = 'Monitoramento de Servidor'
        verbose_name_plural = 'Monitoramento de Servidores'
