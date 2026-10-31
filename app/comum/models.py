import ast
import base64
import calendar
import collections
import hashlib
import io
import json
import operator
import os
import re
import urllib
import uuid
from collections.abc import Iterable
from datetime import date, datetime, timedelta
from functools import reduce
from typing import Any

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.admin.models import LogEntry
from django.contrib.auth import user_logged_in, user_logged_out, user_login_failed
from django.contrib.auth.hashers import get_hasher, make_password
from django.contrib.auth.models import AbstractUser, AnonymousUser, Group
from django.contrib.auth.models import UserManager as DjangoUserManager
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.contrib.postgres.indexes import GinIndex, OpClass
from django.core.cache import cache
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.files.storage import default_storage
from django.core.validators import RegexValidator
from django.core.mail import EmailMultiAlternatives
from django.db import IntegrityError
from django.db.models import Q, QuerySet, Sum
from django.db.models.functions import Upper
from django.db.transaction import atomic
from django.dispatch import receiver
from django.http import HttpRequest, HttpResponse
from django.template.defaultfilters import truncatechars
from django.urls import reverse_lazy
from django.utils import timezone
from django_extensions.db.fields import AutoSlugField
from sentry_sdk import capture_exception

from comum import signer
from comum.managers import VinculoManager
from comum.types import PessoaFisicaCadastro, PrestadorServicoCadastro, PrestadorServicoRetorno
from comum.utils import (
    FLAG_LOG_GERENCIAMENTO_GRUPO,
    get_setor,
    get_uo,
    registrar_adicao_grupo,
    registrar_inclusao_remocao_grupo,
    registrar_remocao_grupo,
    tl,
)
from djtools.choices import SituacaoSolicitacaoDocumento
from djtools.db import models
from djtools.db.models import CurrentUserField, ModelPlus
from djtools.html.calendarios import CalendarioPlus
from djtools.storages.utils import cache_file, download_media_content, get_overwrite_storage
from djtools.thumbs import ImageWithThumbsField
from djtools.utils import (
    ModelValidation,
    adicionar_mes,
    b64decode,
    b64encode,
    daterange,
    decrypt,
    get_client_ip,
    get_ldap_conf,
    is_ldap_enabled,
    limpar_cache_do_usuario,
    limpar_cache_dos_quadros,
    mask_cep,
    normalizar_nome_proprio,
    render_from_string,
    send_mail,
    send_notification,
    sync_ldap_setor,
    sync_ldap_user,
    to_ascii,
)
from djtools.utils.response import render_to_string
from rh.enums import Nacionalidade
from rh.models import (
    AbstractFuncionario,
    Funcao,
    Papel,
    Pessoa,
    PessoaExterna,
    PessoaFisica,
    Servidor,
    Setor,
    Situacao,
    UnidadeOrganizacional,
)
from suap import nomenclatura

Group._meta.ordering = ['name']


class Publico(ModelPlus):
    TIPO_SETOR_SUAP = 'setor_suap'
    TIPO_SETOR_FUNCAO_SIAPE = 'setor_funcao'
    TIPO_SETOR_LOTACAO_SIAPE = 'setor_lotacao'
    TIPO_SETOR_EXERCICIO_SIAPE = 'setor_exercicio'
    TIPO_SETOR_CHOICES = (
        (TIPO_SETOR_SUAP, 'Setor SUAP'),
        (TIPO_SETOR_FUNCAO_SIAPE, 'Setor da Função SIAPE'),
        (TIPO_SETOR_LOTACAO_SIAPE, 'Setor de Lotação SIAPE'),
        (TIPO_SETOR_EXERCICIO_SIAPE, 'Setor de Exercício SIAPE'),
    )

    BASE_FUNCIONARIO = 'Funcionario'
    BASE_SERVIDOR = 'Servidor'
    BASE_ALUNO = 'Aluno'
    BASE_PRESTADORSERVICO = 'PrestadorServico'
    BASE_VINCULO = 'Vinculo'
    BASE_CHOICES = (
        (BASE_SERVIDOR, BASE_SERVIDOR),
        (BASE_ALUNO, BASE_ALUNO),
        (BASE_PRESTADORSERVICO, BASE_PRESTADORSERVICO),
        (BASE_VINCULO, BASE_VINCULO),
    )

    nome = models.CharFieldPlus('Nome')
    modelo_base = models.CharFieldPlus('Modelo base', choices=BASE_CHOICES)
    manager_base = models.CharFieldPlus('Manager base', default='objects')
    qs_filter = models.CharFieldPlus(
        'Queryset filter',
        blank=True,
        default='',
        help_text='As vezes no modelo já existem alguns filtros pré-definidos como em Servidor: "ativos_permanentes". Caso queira aplicar mais de um faça separação por vírgula.',
    )
    filtro = models.TextField('Filtro', blank=True, help_text='Informe os parâmetros para filtro dos modelos em formato json.')
    filtro_avancado = models.TextField(
        'Filtro avançado', blank=True, help_text='Informe uma consulta queryset usando Q() para filtrar os modelos. Exemplo: Q(campo=valor)'
    )
    filtro_exclusao = models.TextField(
        'Filtro de Exclusão', blank=True, help_text='Informe os parâmetros para filtro de exclusão dos modelos em formato json.'
    )

    class Meta:
        verbose_name = 'Público'
        verbose_name_plural = 'Públicos'
        ordering = ['nome']

    def __str__(self):
        return self.nome

    def get_queryset(self):
        try:
            qs = getattr(self.get_classe_modelo(), self.manager_base)
        except AttributeError:
            qs = self.get_classe_modelo().objects
            qs = getattr(qs, self.manager_base)()

        if self.qs_filter:
            for filtro_qs in self.qs_filter.split(','):
                qs = getattr(qs, filtro_qs.strip())()

        if self.filtro:
            filtro = json.loads(self.filtro)
            qs = qs.filter(**filtro)

        if self.filtro_exclusao:
            filtro_exclusao = json.loads(self.filtro_exclusao)
            qs = qs.exclude(**filtro_exclusao)
        if self.filtro_avancado:
            # Avalia a string convertendo-a em um objeto Q.
            qs = qs.filter(self._parse_expression(ast.parse(self.filtro_avancado, mode='eval').body))
        if self.modelo_base in [Publico.BASE_SERVIDOR, Publico.BASE_ALUNO, Publico.BASE_PRESTADORSERVICO]:
            qs = qs.select_related('pessoa_fisica')
        elif self.modelo_base == Publico.BASE_VINCULO:
            qs = qs.select_related('pessoa__pessoafisica')
        return qs.order_by().distinct()

    @classmethod
    def _parse_expression(cls, node):
        if isinstance(node, ast.Call):
            if not isinstance(node.func, ast.Name) or node.func.id != 'Q' or node.args or any(keyword.arg is None for keyword in node.keywords):
                raise ValueError('only Q(field=value, ...) is allowed')

            values = {}
            for keyword in node.keywords:
                if keyword.arg in values:
                    raise ValueError('duplicate filter field')
                values[keyword.arg] = ast.literal_eval(keyword.value)
                if not isinstance(values[keyword.arg], (str, int, float, bool, type(None), list, tuple, dict)):
                    raise ValueError('Unsupported filter value')
            return Q(**values)

        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.BitAnd, ast.BitOr)):
            left = cls._parse_expression(node.left)
            right = cls._parse_expression(node.right)
            return left & right if isinstance(node.op, ast.BitAnd) else left | right

        raise ValueError('Filter must contain Q expressions joined with & or |')

    def q_filter_queryset_campus(self, campi_ids, tipo_setor):
        if self.modelo_base == self.BASE_ALUNO:
            return Q(curso_campus__diretoria__setor__uo__id__in=campi_ids)
        elif self.modelo_base in [self.BASE_PRESTADORSERVICO, self.BASE_VINCULO]:
            return Q(setor__uo__id__in=campi_ids)
        else:
            if tipo_setor == self.TIPO_SETOR_SUAP:
                return Q(setor__uo__id__in=campi_ids)
            elif tipo_setor == self.TIPO_SETOR_FUNCAO_SIAPE:
                return Q(setor_funcao__uo__equivalente__id__in=campi_ids)
            elif tipo_setor == self.TIPO_SETOR_LOTACAO_SIAPE:
                return Q(setor_lotacao__uo__equivalente__id__in=campi_ids)
            else:
                return Q(setor_exercicio__uo__equivalente__id__in=campi_ids)

    def q_filter_queryset_setores(self, setores_ids, tipo_setor):
        if self.modelo_base == self.BASE_ALUNO:
            return Q(curso_campus__diretoria__setor__id__in=setores_ids)
        elif self.modelo_base == self.BASE_PRESTADORSERVICO:
            return Q(setor__id__in=setores_ids)
        else:
            if tipo_setor == self.TIPO_SETOR_SUAP:
                return Q(setor__id__in=setores_ids)
            elif tipo_setor == self.TIPO_SETOR_FUNCAO_SIAPE:
                return Q(setor_funcao__id__in=setores_ids)
            elif tipo_setor == self.TIPO_SETOR_LOTACAO_SIAPE:
                return Q(setor_lotacao__id__in=setores_ids)
            else:
                return Q(setor_exercicio__id__in=setores_ids)

    def q_filter_queryset(self, campi, setores, tipo_setor):
        retorno = []
        if setores and setores.exists():
            setores_ids = setores.values_list('id', flat=True)
            retorno.append(self.q_filter_queryset_setores(setores_ids, tipo_setor))
        elif campi:
            campi_ids = campi.values_list('id', flat=True)
            retorno.append(self.q_filter_queryset_campus(campi_ids, tipo_setor))
        return retorno

    def get_queryset_vinculo(self, campi=None, setores=None, tipo_setor=None):
        ids = []
        resultado = self.get_queryset()
        if self.modelo_base == self.BASE_VINCULO:
            return resultado
        if campi or setores:
            resultado = resultado.filter(reduce(operator.or_, self.q_filter_queryset(campi, setores, tipo_setor)))
        if resultado.exists():
            if hasattr(resultado[0], 'vinculo'):
                ids = resultado.values_list('vinculo__id', flat=True)
            elif hasattr(resultado[0], 'vinculos'):
                ids = resultado.values_list('vinculos__id', flat=True)
            else:
                lista_ids = []
                for funcionario in resultado:
                    lista_ids.append(funcionario.get_vinculo().id)
                ids = lista_ids
        return Vinculo.objects.filter(id__in=ids).distinct()

    @staticmethod
    def get_meus_publicos(user):
        publicos_ids = []
        for publico in Publico.objects.all():
            if publico.modelo_base == publico.BASE_VINCULO:
                if publico.get_queryset().filter(user=user):
                    publicos_ids.append(publico.id)
            else:
                if publico.get_queryset().filter(matricula=user.username):
                    publicos_ids.append(publico.id)
        return Publico.objects.filter(id__in=publicos_ids)

    def get_classe_modelo(self):
        if self.modelo_base == self.BASE_SERVIDOR:
            return Servidor
        elif self.modelo_base == self.BASE_ALUNO:
            from edu.models import Aluno

            return Aluno
        elif self.modelo_base == self.BASE_PRESTADORSERVICO:
            return PrestadorServico
        else:
            return Vinculo


class AreaAtuacao(models.ModelPlus):
    nome = models.CharFieldPlus('Nome', max_length=120, unique=True, help_text='Informe um nome para a área de atuação')
    slug = AutoSlugField('Slug', max_length=120, unique=True, populate_from=('nome',))
    icone = models.CharFieldPlus(
        'Ícone',
        max_length=80,
        blank=True,
        default='list',
        help_text='Informe um ícone para representar esta Área de Atuação. Fonte: https://fontawesome.com/',
    )
    ativo = models.BooleanField('Ativo?', default=True)

    class Meta:
        ordering = ['nome']
        verbose_name = 'Área de Atuação'
        verbose_name_plural = 'Áreas de Atuação'

    def __str__(self):
        return self.nome


class UserManager(DjangoUserManager):
    def superusers(self):
        return self.filter(is_superuser=True)

    def active(self):
        return self.filter(is_active=True)

    def inactive(self):
        return self.filter(is_active=False)

    def get_or_create_user(self, username: str, cpf: str):
        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            user = User.objects.create_user(username, email='', password=None)
            if not is_ldap_enabled():
                hasher = get_hasher()
                sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla') or ''
                password = make_password(f'{sigla}.{cpf}', '', hasher)
                User.objects.filter(id=user.id).update(password=password)

        try:
            user.reset_profile()
            user.reset_vinculo()
        except Exception:
            pass
        return user


class User(AbstractUser):
    login_attempts = models.IntegerField('Tentativas de Login', default=0)
    SEARCH_FIELDS = ['vinculo__pessoa__search_fields_optimized']

    eh_servidor = models.BooleanField(default=False)
    eh_aluno = models.BooleanField(default=False)
    eh_prestador = models.BooleanField(default=False)
    eh_usuarioexterno = models.BooleanField(default=False)
    eh_docente = models.BooleanField(default=False)
    eh_tecnico_administrativo = models.BooleanField(default=False)

    eh_estrangeiro = models.BooleanField(verbose_name='É estrangeiro?', default=False)
    VINCULOS = {}
    PESSOAS_FISICAS = {}

    uuid = models.UUIDField(unique=True, default=uuid.uuid4)

    forcar_troca_senha = models.BooleanField('Forçar a troca de senha no próximo login', default=False)
    data_solicitacao_forcar_troca_senha = models.DateFieldPlus(verbose_name='Data de solicitação para forçar troca de senha', null=True, blank=True)

    data_ultima_alteracao_senha = models.DateFieldPlus(verbose_name='Data da última alteração da senha', null=False, default=timezone.now)

    # objects = DefaultSelectOrPrefetchManager(select_related=('pessoafisica',))
    # objects = UserManager().select_related('pessoafisica')
    objects = UserManager()

    class History:
        blank_fields = ('password',)
        ignore_fields = ('login_attempts', 'last_login')

    class Meta:
        verbose_name = 'Usuário'
        verbose_name_plural = 'Usuários'
        db_table = 'auth_user'
        # username__iexact (login LDAP) gera UPPER(username::text); sem este índice cada login faz seq scan.
        indexes = [models.Index(Upper('username'), name='auth_user_username_upper')]

    def set_password(self, *args, **kwargs):
        super().set_password(*args, **kwargs)
        self.data_ultima_alteracao_senha = date.today()

    def has_perm(self, perm, obj=None, ignore_superuser=False):
        if ignore_superuser and self.is_superuser:
            app, permissao = perm.split('.')
            result = self.groups.filter(permissions__content_type__app_label=app, permissions__codename=permissao).exists()
        else:
            result = super().has_perm(perm, obj)
        return result

    def get_profile(self):
        pessoa_fisica = self.PESSOAS_FISICAS.get(self.id)
        if not pessoa_fisica:
            vinculo = self.get_vinculo()
            pessoa_fisica = vinculo and vinculo.pessoa.pessoafisica or None
            self.PESSOAS_FISICAS[self.id] = pessoa_fisica
        return pessoa_fisica

    def get_vinculo(self):
        vinculo = self.VINCULOS.get(self.id)
        if not vinculo:
            vinculo = self.VINCULOS[self.id] = getattr(self, 'vinculo', None)
        return vinculo

    def get_tipo(self) -> str:
        if self.eh_servidor:
            relacionamento = self.get_relacionamento()
            if relacionamento and relacionamento.eh_estagiario:
                return 'Estagiário'
            elif self.eh_docente:
                return 'Servidor (Docente)'
            else:
                return 'Servidor (Técnico-Administrativo)'
        elif self.eh_aluno:
            return 'Aluno'
        else:
            return 'Prestador de Serviço'

    def reset_vinculo(self):
        try:
            del self.VINCULOS[self.id]
        except Exception:
            pass

    def reset_profile(self):
        try:
            del self.PESSOAS_FISICAS[self.id]
        except Exception:
            pass

    def get_relacionamento(self):
        try:
            return self.get_vinculo().relacionamento
        except AttributeError:
            return None

    def get_relacionamento_title(self):
        if not self.get_vinculo():
            return 'Usuário sem relacionamento'
        return self.get_vinculo().get_relacionamento_title()

    def tema_preferido(self):
        return self.preferencia and self.preferencia.tema != '' and self.preferencia.tema or Preferencia.get_tema_padrao_usuario_autenticado()

    @property
    def eh_notificado_suap(self):
        return self.preferencia.via_suap if self.preferencia else True

    @property
    def eh_notificado_email(self):
        return self.preferencia.via_email if self.preferencia else True

    def tem_historico_grupos(self):
        return LogEntry.objects.filter(object_id=self.id, action_flag=FLAG_LOG_GERENCIAMENTO_GRUPO).exists()

    def eh_gerenciador_do_grupo(self, grupo):
        return (
            self.is_superuser
            or self.groups.filter(
                pk__in=list(GerenciamentoGrupo.objects.filter(grupos_gerenciados=grupo).values_list('grupo_gerenciador', flat=True))
            ).exists()
        )

    def gerenciamento_do_grupo(self, grupo=None):
        gerenciamento_do_grupo = GerenciamentoGrupo.objects.all()
        if not grupo:
            if self.is_superuser:
                return gerenciamento_do_grupo
            return gerenciamento_do_grupo.filter(grupo_gerenciador__pk__in=self.groups.all().values_list('pk', flat=True))

        gerenciamento_do_grupo = gerenciamento_do_grupo.filter(grupos_gerenciados=grupo)
        if self.is_superuser:
            return gerenciamento_do_grupo
        return gerenciamento_do_grupo.filter(grupo_gerenciador__pk__in=self.groups.all().values_list('pk', flat=True))

    def has_group(self, group):
        if isinstance(group, str):
            group_list = [g.strip() for g in group.split(',')]
        elif isinstance(group, Iterable):
            group_list = [g.strip() for g in group]
        else:
            raise TypeError('The first parameter must be a basestring or an iterable')
        return self.groups.filter(name__in=group_list).exists() or self.is_superuser

    def get_uo(self):
        return get_uo(self)

    def get_setor(self):
        return get_setor(self)

    def get_groups(self, permission=None):
        if permission:
            app, permissao = permission.split('.')
            return self.groups.filter(permissions__content_type__app_label=app, permissions__codename=permissao)
        else:
            return self.groups.all()

    def autenticacaodoisfatores_habilitada(self):
        try:
            return self.autenticacaodoisfatores.ativo
        except AutenticacaoDoisFatores.DoesNotExist:
            return False

    def get_groups_cached(self, force=False):
        groups = cache.get(f'{self.id}_groups', local_ttl=10)
        if not groups or force:
            groups = set(self.groups.all().values_list('name', flat=True))
            cache.set(f'{self.id}_groups', groups)
        return groups

    def has_group_cached(self, group, any=True, ignore_groups_if_superuser=True):
        if ignore_groups_if_superuser and self.is_superuser:
            return True

        group_list = []
        if isinstance(group, str):
            group_list = [g.strip() for g in group.split(',')]
        elif isinstance(group, QuerySet):
            group_list = [g.name for g in group]
        elif isinstance(group, Iterable):
            group_list = [g.strip() for g in group]
        else:
            raise TypeError('The first parameter must be a basestring or an iterable')

        groups = self.get_groups_cached()

        result = False

        for g in group_list:
            if g in groups:
                result = True
                if any:
                    break
            elif not any:
                result = False
                break

        return result

    def is_configurador(self):
        return self.groups.all().filter(name__endswith='Configurador').exists()

    def enviar_email_boas_vindas(self) -> None:
        pessoa = self.get_profile()
        if pessoa:
            vinculo = self.get_vinculo()
            email = (
                (vinculo.email_pessoal if vinculo else '')
                or (vinculo.email_notificacao if vinculo else '')
                or self.email
                or getattr(self.get_relacionamento(), 'email_siape', '')
            )
            if email:
                nome = pessoa.nome or self.get_full_name() or self.username
                username = self.username
                instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla') or ''
                if self.eh_usuarioexterno and not self.eh_estrangeiro:
                    login_url = f'{settings.SITE_URL}/'
                else:
                    login_url = f'{settings.SITE_URL}/comum/solicitar_trocar_senha/'
                assunto = f'Bem-vindo ao SUAP - {instituicao_sigla}!'
                mensagem = render_to_string(
                    'email_boas_vindas.html',
                    {
                        'nome': nome,
                        'username': username,
                        'email': email,
                        'eh_externo': self.eh_usuarioexterno,
                        'eh_estrangeiro': self.eh_estrangeiro,
                        'login_url': login_url,
                        'instituicao_sigla': instituicao_sigla,
                    },
                )
                send_mail(assunto, mensagem, settings.DEFAULT_FROM_EMAIL, [email])


# Usuário anônimo nunca pertence a grupo algum. Aceita qualquer assinatura para não quebrar
# quando a assinatura real de User.has_group/has_group_cached mudar (ex.: ignore_groups_if_superuser).
AnonymousUser.has_group = lambda *args, **kwargs: False
AnonymousUser.has_group_cached = lambda *args, **kwargs: False


class OauthLogin(models.ModelPlus):
    user = models.ForeignKeyPlus(User, verbose_name='Usuário')
    data_hora = models.DateTimeField(verbose_name='Data/Hora')
    dados = models.JSONField(verbose_name='Dados')

    class Meta:
        verbose_name = 'Autenticação Oauth'
        verbose_name_plural = 'Autenticações Oauth'

    def __str__(self):
        return f'Autenticação de {self.user} - {self.data_hora.isoformat()}'


class CertificadoDigital(models.ModelPlus):
    user = models.ForeignKeyPlus(User, verbose_name='Usuário')
    arquivo = models.FileFieldPlus(verbose_name='Arquivo', upload_to='certificados_digitais')
    nome = models.CharFieldPlus(verbose_name='Nome')
    organizacao = models.CharFieldPlus(verbose_name='Organização')
    unidade = models.CharFieldPlus(verbose_name='Unidade Organizacional')
    validade = models.DateFieldPlus(verbose_name='Validade')
    conteudo = models.TextField('Conteúdo')

    class Meta:
        verbose_name = 'Certificado Digital'
        verbose_name_plural = 'Certificados Digitais'

    def __str__(self):
        return '{} - {} - (VÁLIDO ATÉ {})'.format(self.nome, self.organizacao, self.validade.strftime('%d/%m/%Y'))

    def assinar_arquivo_pdf(
        self,
        caminho_arquivo,
        senha,
        tipo_documento=None,
        codigo_autenticacao=None,
        adicionar_texto=False,
        titulo=None,
        adicionar_imagem=False,
        x=0,
        y=0,
        bgcolor='#EEEEEE',
        page=0,
    ):
        documento = cache_file(caminho_arquivo)
        local_filename = cache_file(self.arquivo.name)
        signed = signer.sign(
            local_filename,
            senha,
            documento,
            sign_img=adicionar_imagem,
            suffix='',
            bgcolor=bgcolor,
            x=x,
            y=y,
            document_type=tipo_documento,
            authentication_code=codigo_autenticacao,
            page=page,
            title=titulo,
        )
        storage = get_overwrite_storage()
        with open(signed, 'rb') as f:
            storage.save(caminho_arquivo, f)

        if os.path.exists(local_filename):
            os.unlink(local_filename)

    def verificar_arquivo_pdf(self, caminho_arquivo):
        return signer.verify(caminho_arquivo, self.conteudo)


class Device(models.ModelPlus):
    user = models.ForeignKeyPlus(User, null=False, blank=False, verbose_name='Usuário')
    user_agent = models.TextField(null=False, blank=False, verbose_name='Agente do Dispositivo', db_index=True)
    nickname = models.CharFieldPlus('Apelido', blank=True, null=True, db_index=True)
    friendly_name = models.TextField(null=False, blank=False, verbose_name='Dispositivo', db_index=True)
    activated = models.BooleanField(default=True, verbose_name='Ativado')

    class History:
        disabled = True

    class Meta:
        unique_together = ('user', 'user_agent')
        verbose_name = 'Dispositivo'
        verbose_name_plural = 'Dispositivos'

    def get_name(self):
        if self.nickname:
            return self.nickname
        elif self.friendly_name:
            return self.friendly_name
        else:
            return self.user_agent

    def __str__(self):
        return f'Dispositivo: {self.get_name()}'


class SessionInfo(models.ModelPlus):
    session_id = models.TextField(null=False, blank=False, unique=True, verbose_name='Identificador da Sessão')
    device = models.ForeignKeyPlus('comum.Device')
    ip_address = models.TextField(null=False, blank=False, verbose_name='Endereço IP', db_index=True)
    date_time = models.DateTimeFieldPlus(auto_now_add=True, verbose_name='Horário do Login')
    expired = models.BooleanField(verbose_name='Expirada', default=False)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Informação de Sessão'
        verbose_name_plural = 'Informações de Sessões'

    def can_change(self, user):
        return False

    def __str__(self):
        return f'Sessão #{self.pk}'


class Vinculo(models.ModelPlus):
    SERVIDOR = Q(app_label='rh', model='servidor')
    PRESTADOR = Q(app_label='comum', model='prestadorservico')
    ALUNO = Q(app_label='edu', model='aluno')
    PESSOA_JURIDICA = Q(app_label='rh', model='pessoajuridica')
    PESSOA_EXTERNA = Q(app_label='rh', model='pessoaexterna')

    ESCOLHAS_VINCULO = SERVIDOR | PRESTADOR | ALUNO | PESSOA_JURIDICA | PESSOA_EXTERNA

    SEARCH_FIELDS = ['search']

    user = models.OneToOneFieldPlus('comum.User', verbose_name='Usuário', null=True, on_delete=models.CASCADE)
    pessoa = models.ForeignKeyPlus('rh.Pessoa', verbose_name='Pessoa', on_delete=models.CASCADE)
    setor = models.ForeignKeyPlus('rh.Setor', verbose_name='Setor', null=True, on_delete=models.SET_NULL)

    tipo_relacionamento = models.ForeignKeyPlus(
        ContentType, verbose_name='Tipo de Relacionamento', limit_choices_to=ESCOLHAS_VINCULO, null=False, blank=False, on_delete=models.CASCADE
    )
    id_relacionamento = models.PositiveIntegerField(verbose_name='Identificador do Relacionamento', null=False)
    relacionamento = GenericForeignKey('tipo_relacionamento', 'id_relacionamento')
    # o documento sem máscara vai por último: o backfill da migration 0124 o anexa ao fim do texto já gravado
    search = models.SearchField(
        attrs=['user.username', 'pessoa.nome', 'pessoa.pessoafisica.cpf', 'pessoa.pessoajuridica.cnpj', 'cpf_ou_cnpj_sem_mascara']
    )
    ativo = models.BooleanField(verbose_name='Ativo', default=True)
    secret = models.IntegerField(null=False, blank=False)  # Este atributo irá preservar os ids antigos após a unificação das pessoas.
    # Identificador não-enumerável usado nas URLs públicas de arquivo (/djtools/arquivo/...),
    # exigido por ImageWithThumbsFieldFile.get_url_publica() desde que a foto migrou para cá.
    uuid = models.UUIDField(default=uuid.uuid4, unique=True)

    # Campos migrados de Pessoa/PessoaFisica (passo 1 da unificação de PessoaFisica).
    # ponytail: por ora é um snapshot preenchido pelo backfill; a fonte da verdade segue
    # em Pessoa/PessoaFisica até o passo de codemod. Sem dual-write.
    email_pessoal = models.EmailField('E-mail Pessoal', blank=True)
    setores_adicionais = models.ManyToManyField(
        'rh.Setor',
        verbose_name='Setores Adicionais',
        blank=True,
        related_name='vinculos_setor_adicional',
        help_text='O funcionário terá acesso aos processos dos setores adicionais no sistema de protocolo.',
    )
    sistema_origem = models.CharField(
        max_length=50,
        blank=True,
        choices=[['', 'Cadastro manual'], ['SIAPE', 'SIAPE'], ['WS-SIAPE', 'WS-SIAPE'], ['SIAFI', 'SIAFI']],
        help_text='Indica de qual sistema a pessoa veio: SIAPE, SIAFI etc',
    )
    foto = ImageWithThumbsField(
        storage=get_overwrite_storage(), use_id_for_name=True, upload_to='fotos', sizes=((75, 100), (150, 200)), null=True, blank=True
    )
    # ponytail: on_delete=CASCADE espelha a origem em PessoaFisica (dubioso p/ tabela de domínio);
    # trocar por SET_NULL num passo futuro se virar problema. Mantido fiel à origem por ora.
    raca = models.ForeignKeyPlus('comum.Raca', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE)
    povo_indigena = models.ForeignKeyPlus('comum.PovoIndigena', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE)
    deficiencia = models.ForeignKeyPlus(
        'rh.Deficiencia', verbose_name='Deficiência', null=True, blank=True, related_name='vinculos', on_delete=models.CASCADE
    )

    objects = VinculoManager()

    class Meta:
        verbose_name = 'Vínculo'
        verbose_name_plural = 'Vínculos'
        unique_together = ('tipo_relacionamento', 'id_relacionamento')
        # Busca do autocomplete: search__icontains vira UPPER(search) LIKE UPPER('%termo%').
        indexes = [GinIndex(OpClass(Upper('search'), name='gin_trgm_ops'), name='comum_vinculo_search_trgm')]

    def __str__(self) -> str:
        relacionamento = self.relacionamento
        tipo = 'Estagiário' if self.eh_servidor() and relacionamento.eh_estagiario else relacionamento._meta.verbose_name
        return f'{relacionamento} ({tipo})'

    def clean(self) -> None:
        if self.raca and self.raca.is_indigena() and not self.povo_indigena:
            raise ValidationError('É necessário informar o Povo indígena quando a Raça for Indígena')

    def save(self, *args, **kwargs):
        if self.pk is None:
            self.secret = self.pessoa_id
        super().save(*args, **kwargs)
        self.user and self.user.reset_vinculo()

    def get_usuario_ldap(self, attrs=None):
        conf = get_ldap_conf()
        if conf:
            return conf.get_user(self.relacionamento.matricula, attrs=attrs)

    @property
    def excluido(self):
        return not self.ativo

    @property
    def nome(self):
        return self.pessoa.nome

    @property
    def nome_usual(self):
        return self.pessoa.nome_usual

    def get_informacao_adicional(self):
        if self.eh_servidor():
            return {'Cargo': self.relacionamento.cargo_emprego.nome if self.relacionamento.cargo_emprego else ''}
        elif self.eh_aluno():
            return {'Curso': self.relacionamento.curso_campus.descricao_historico}
        return None

    def eh_servidor(self):
        return self.tipo_relacionamento.model == 'servidor'

    def eh_prestador(self):
        return self.tipo_relacionamento.model == 'prestadorservico'

    def eh_usuario_externo(self):
        return self.eh_prestador() and self.relacionamento.usuario_externo

    def eh_funcionario(self):
        return self.eh_servidor() or self.eh_prestador()

    def eh_aluno(self):
        return self.tipo_relacionamento.model == 'aluno'

    def eh_pessoaexterna(self):
        return self.tipo_relacionamento.model == 'pessoaexterna'

    def eh_maior_de_idade(self, referencia=None, anos=18):
        referencia = referencia or timezone.localdate()
        nascimento_data = None
        try:
            nascimento_data = self.pessoa.pessoafisica.nascimento_data
        except Exception:
            nascimento_data = None

        if not nascimento_data:
            return False
        return nascimento_data <= (referencia - relativedelta(years=anos))

    def eh_pessoafisica(self):
        return not self.eh_pessoajuridica()

    def eh_pessoajuridica(self):
        return self.tipo_relacionamento.model == 'pessoajuridica'

    def get_areas_tematicas_interesse(self):
        return ', '.join(self.areatematica_set.all().values_list('descricao', flat=True))

    def get_cpf_ou_cnpj(self):
        return self.pessoa.get_cpf_ou_cnpj()

    @property
    def cpf_ou_cnpj_sem_mascara(self) -> str:
        """CPF/CNPJ sem pontuação, para o autocomplete achar o vínculo pelo documento digitado sem máscara."""
        documento = self.pessoa.get_cpf_ou_cnpj()
        return re.sub(r'\W', '', documento) if documento and documento != '-' else ''

    def cpf_ou_cnpj_valido(self):
        return self.pessoa.cpf_ou_cnpj_valido()

    def get_user(self):
        return self.user or None

    @property
    def email_notificacao(self) -> str:
        """E-mail de notificação (recuperação de senha): o institucional do papel, senão o pessoal."""
        email = (
            getattr(self.relacionamento, 'email_institucional', '')
            or getattr(self.relacionamento, 'email_academico', '')
            or getattr(self.relacionamento, 'email_google_classroom', '')
            or getattr(self.relacionamento, 'email', '')
            or self.email_pessoal
            or getattr(self.user, 'email', '')
        )
        return email.split(',')[0].strip() if email else ''

    def tem_email_valido(self):
        email = self.email_notificacao
        if not email:
            return False
        # Regex para validação básica de email
        # Permite letras, números, pontos, hífens e underscores antes do @
        # Exige domínio com pelo menos um ponto
        email_pattern = r'^[a-zA-Z0-9._%-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return bool(re.match(email_pattern, email))

    @property
    def get_vinculo_institucional_title(self):
        retorno = 'Nenhum'
        if self.eh_servidor() and self.ativo:
            if self.relacionamento.eh_aposentado:
                retorno = 'Aposentado'
            elif self.relacionamento.eh_estagiario:
                retorno = 'Estagiário'
            else:
                retorno = 'Servidor'
        elif self.eh_prestador() and self.ativo:
            retorno = 'Prestador de Serviço'
        elif self.eh_aluno() and self.ativo:
            retorno = 'Aluno'
        return retorno

    def get_ext_combo_template(self):
        return self.relacionamento.get_ext_combo_template()

    def get_relacionamento_title(self) -> str:
        relacionamento = self.relacionamento
        if relacionamento:
            if self.eh_servidor() and relacionamento.eh_estagiario:
                return 'Estagiário'
            try:
                return relacionamento.cargo_emprego.nome
            except AttributeError:
                return relacionamento._meta.verbose_name
        return 'Nenhum'

    @staticmethod
    def get_vinculos_ou_falsos_vinculos(pessoas):
        vinculos = []
        for pessoa in pessoas:
            if hasattr(pessoa, 'pessoafisica'):
                try:
                    vinculos.append(Vinculo.objects.filter(pessoa=pessoa)[0])
                except Exception:
                    relacionamento = PessoaExterna(pessoa_fisica=pessoa.pessoafisica, email='')
                    vinculos.append(Vinculo(relacionamento=relacionamento))

            elif hasattr(pessoa, 'pessoajuridica'):
                vinculos.append(Vinculo(relacionamento=pessoa.pessoajuridica))
        return vinculos

    def get_foto_url(self) -> str:
        if self.eh_aluno() and self.relacionamento is not None:
            return self.relacionamento.get_foto_75x100_url()  # Aluno tem foto própria, sem get_foto_url genérico
        return self.foto.url if self.foto else '/static/comum/img/default.jpg'

    def get_foto_75x100_url(self) -> str:
        if self.eh_aluno() and self.relacionamento is not None:
            return self.relacionamento.get_foto_75x100_url()
        return self.foto.url_75x100 if self.foto else '/static/comum/img/default.jpg'

    def get_foto_150x200_url(self) -> str:
        if self.eh_aluno() and self.relacionamento is not None:
            return self.relacionamento.get_foto_150x200_url()
        return self.foto.url_150x200 if self.foto else '/static/comum/img/default.jpg'

    def get_foto_url_publica(self, tamanho: str | None = None) -> str:
        if self.eh_aluno() and self.relacionamento is not None:
            # Aluno não tem get_foto_url_publica(tamanho); delega pelo tamanho
            if tamanho == '150x200':
                return self.relacionamento.get_foto_150x200_url_publica()
            return self.relacionamento.get_foto_75x100_url_publica()
        path_img = self.foto.get_url_publica(tamanho) if self.foto else '/static/comum/img/default.jpg'
        return f'{settings.SITE_URL}{path_img}'

    def get_foto_75x100_url_publica(self) -> str:
        return self.get_foto_url_publica('75x100')

    def get_foto_150x200_url_publica(self) -> str:
        return self.get_foto_url_publica('150x200')

    def get_indicacoes_como_avaliador_extensao(self):
        if 'projetos' in settings.INSTALLED_APPS:
            AvaliadorIndicado = apps.get_model('projetos', 'AvaliadorIndicado')
            Avaliacao = apps.get_model('projetos', 'Avaliacao')
            return f'{AvaliadorIndicado.objects.filter(vinculo=self).count()} indicações, {Avaliacao.objects.filter(vinculo=self).count()} avaliações realizadas'
        return '-'


def user_unicode(self):
    nome = self.get_full_name()
    profile = self.get_profile()
    if profile and profile.nome_usual:
        nome = profile.nome_usual
    return f'{nome} ({self.username})'


def user_get_ext_combo_template(self):
    try:
        vinculo = self.get_vinculo()
        out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{vinculo.pessoa.nome}</dd>']
        if vinculo.eh_servidor():
            if vinculo.setor:
                out.append(f'<dt>Setor:</dt><dd>{vinculo.setor.get_caminho_as_html()}</dd>')
            out.append(f'<dt>Cargo:</dt><dd>{vinculo.relacionamento.cargo_emprego}</dd>')
        out.append(f'<dt>Login:</dt><dd>{self.username}</dd>')
        if self.email:
            out.append(f'<dt>E-mail:</dt><dd>{self.email}</dd>')
        template = """<div class="person">
            <div class="photo-circle">
                <img alt="Foto de {}" src="{}" />
            </div>
            <dl>{}</dl>
        </div>
        """.format(vinculo.pessoa.nome, vinculo.get_foto_75x100_url(), ''.join(out))
        return template
    except Exception:
        return str(self)


User.get_ext_combo_template = user_get_ext_combo_template
User.__str__ = user_unicode
User._meta.ordering = ('first_name', 'last_name')


def gerar_mensagem_atividade_irregular(request, user, header, session_id):
    """Gera mensagem HTML de notificação de atividade irregular no login.

    Args:
        request: objeto da requisição HTTP.
        user: usuário que realizou o login.
        header: cabeçalho HTML da mensagem.
        session_id: identificador da sessão para link de logout remoto.

    Returns:
        str: mensagem HTML formatada com dados do dispositivo e localização.
    """
    import user_agents

    ip_address = get_client_ip(request)
    ua_string = request.META.get('HTTP_USER_AGENT', '-')
    ua = user_agents.parse(ua_string)
    ua_device = str(ua)

    context = {
        'username': user.username,
        'ua_device': ua_device,
        'ip_address': ip_address,
        'hoje': datetime.now(),
        'site_url': settings.SITE_URL,
        'session_id': session_id,
    }
    default_message = """
        <dl>
            <dt>Matrícula:</dt>
            <dd>{{ username }}</dd>
            <dt>Dispositivo:</dt>
            <dd>{{ ua_device }}</dd>
            <dt>Data:</dt>
            <dd>{{ hoje|format }}</dd>
            <dt>Endereço IP:</dt>
            <dd>{{ ip_address }}</dd>
        </dl>
        <p>Saiba a <a href="https://ipinfo.io/{{ ip_address }}">localização provável do acesso</a> (serviço do site ipinfo.io).</p>
        <p>Caso reconheça este login, por favor desconsidere esta notificação.</p>
        <p>Caso não reconheça este login, por favor efetuar os passos abaixo para garantir a segurança dos seus dados e acesso:</p>
        <ol>
            {% if session_id %}
            <li>
                <a href="{{ site_url }}/comum/remote_logout/{{ session_id }}/">Efetuar o logout</a> (saída) do acesso em questão.
            </li>
            {% endif %}
            <li>
                <p>
                    Analisar os outros acessos e dispositivos atualmente em vigor (sessões) na sua matrícula, em
                    <a href="{{ site_url }}/admin/comum/sessioninfo/">Informações de Sessões</a>.
                </p>
                <p>A página acima também pode ser encontrada pelo menu "Tec. da Informação :: Sessões".</p>
            </li>
            <li>
                <p>
                    Analisar os dispositivos que conseguiram se autenticar na sua matrícula, em
                    <a href="{{ site_url }}/admin/comum/device/">Informações de Dispositivos</a>.
                </p>
                <p>A página acima também pode ser encontrada pelo menu "Tec. da Informação :: Dispositivos".</p>
            </li>
            <li>
                <a href="{{ site_url }}/comum/solicitar_trocar_senha/">Alterar a sua Senha</a>.
            </li>
            <li>
                Notificar o responsável pela TI da sua unidade.
            </li>
        </ol>
        <h3>Ação Opcional:</h3>
        <p>Caso deseje, você também pode verificar se algum de seus e-mails, ou telefones, podem ter sido expostos
        em algum incidente de segurança, utilizando o website <a href="https://haveibeenpwned.com/">"Have I Been Pwned"</a>.</p>
        <p>O mesmo site acima também é capaz de verificar se a senha que você utiliza é uma senha que já foi comprometida em algum incidente de segurança, tornando-a conhecida como uma senha comumente utilizável e recorrente: <a href="https://haveibeenpwned.com/Passwords">https://haveibeenpwned.com/Passwords</a>.</p>
    """
    return render_from_string(header + default_message, context)


@receiver(user_login_failed)
def login_failed(sender, credentials, request, **kwargs):
    user = User.objects.filter(username=credentials.get('username')).first()
    if user:
        tentativas = user.login_attempts + 1
        User.objects.filter(pk=user.pk).update(login_attempts=tentativas)

        try:
            with atomic():
                vinculo = user.get_vinculo()
                title = 'Alerta de tentativas excessivas de login sem sucesso'
                header = f"""
                    <h1>Alerta de tentativas excessivas de login sem sucesso: {user.login_attempts} tentativas</h1>
                    <p>Nova tentativa de login no <b>SUAP</b> após <b>{user.login_attempts}</b> tentativas sem sucesso com os seguintes dados de acesso:</p>
                """
                if user.login_attempts in [4, 10, 20, 50, 100] and vinculo:
                    expire_date = datetime.now() + timedelta(days=3)
                    message = gerar_mensagem_atividade_irregular(request, user, header, None)
                    send_notification(
                        title,
                        message,
                        settings.DEFAULT_FROM_EMAIL,
                        [user.get_vinculo()],
                        data_permite_excluir=expire_date,
                        data_permite_marcar_lida=expire_date,
                    )
                    email_notificacao = vinculo.email_notificacao if vinculo else ''
                    if email_notificacao:
                        send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_notificacao])
                    return
        except Exception:
            pass


@receiver(user_logged_in)
def logged_in(sender, user, request, **kwargs):
    """Registra informações do dispositivo e notifica sobre login suspeito.

    Args:
        sender: classe que enviou o sinal ``user_logged_in``.
        user: usuário que realizou o login.
        request: objeto da requisição HTTP.
    """
    import user_agents

    cache.delete(f'servidor_tem_setor_middleware_{user.username}')
    try:
        with atomic():
            ua_string = request.META.get('HTTP_USER_AGENT', '-')
            cookie = request.COOKIES.get(settings.SUAP_CONTROL_COOKIE_NAME, '')
            notificar = True
            ua = user_agents.parse(ua_string)
            ua_device = str(ua)
            vinculo = request.user.get_vinculo()
            title = header = ''
            old_login_attempts = user.login_attempts
            expire_date = datetime.now() + timedelta(days=3)

            device, created = Device.objects.get_or_create(user=user, user_agent=ua_string, friendly_name=ua_device)
            obj = SessionInfo.objects.create(session_id=request.session.session_key, device=device, ip_address=get_client_ip(request))
            session_id = obj.pk

            user.login_attempts = 0
            user.save()
            email_notificacao = vinculo.email_notificacao if vinculo else ''

            if vinculo:
                if old_login_attempts > 2:
                    title = 'Alerta de login após diversas tentativas'
                    header = f"""
                        <h1>Alerta de login após {old_login_attempts} tentativas</h1>
                        <p>Novo login no <b>SUAP</b> após <b>{old_login_attempts}</b> tentativas de login com os seguintes dados de acesso:</p>
                    """
                    message = gerar_mensagem_atividade_irregular(request, user, header, None)
                    send_notification(
                        title, message, settings.DEFAULT_FROM_EMAIL, [vinculo], data_permite_excluir=expire_date, data_permite_marcar_lida=expire_date
                    )
                    if email_notificacao:
                        send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_notificacao])
                    return

                if cookie:
                    try:
                        cookie_data = decrypt(cookie)
                    except Exception:
                        cookie_data = {}
                    try:
                        if request.user.username in cookie_data.get('usernames', []):
                            notificar = False
                    except Exception as e:
                        if settings.DEBUG:
                            raise e
                        capture_exception(e)

                # Se dispositivo esta desativado deve sempre notificar
                if not device.activated:
                    title = 'Alerta de dispositivo desativado'
                    header = f"""
                        <h1>{title}</h1>
                        <p>Novo login no <b>SUAP</b> em um dispositivo desativado com os seguintes dados de acesso:</p>
                    """

                # Se dispositivo foi criado e nao tem cookies deve sempre notificar caso contrario nao notifica
                if created and notificar:
                    title = 'Alerta de dispositivo desconhecido'
                    header = f"""
                        <h1>{title}</h1>
                        <p>Novo login no <b>SUAP</b> em um dispositivo não utilizado previamente (desconhecido) com os seguintes dados de acesso:</p>
                    """

                if title and header and not Configuracao.get_valor_por_chave('comum', 'desabilitar_envio_email_dispositivo_desconhecido'):
                    message = gerar_mensagem_atividade_irregular(request, user, header, session_id)
                    send_notification(
                        title, message, settings.DEFAULT_FROM_EMAIL, [vinculo], data_permite_excluir=expire_date, data_permite_marcar_lida=expire_date
                    )
                    if email_notificacao:
                        send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_notificacao])
    except IntegrityError:
        pass
    except Exception as e:
        capture_exception(e)


@receiver(user_logged_out)
def logged_out(sender, user, request, **kwargs):
    if hasattr(user, 'username'):
        limpar_cache_do_usuario(user.username)

    try:
        with atomic():
            SessionInfo.objects.filter(device__user=user, session_id=request.session.session_key).update(expired=True)
    except Exception as e:
        capture_exception(e)


def user_post_save(sender: type[User], **kwargs: object) -> None:
    """
    Sincroniza o usuário e os grupos e permissões deste.

    É chamado sempre que um usuário é salvo (por exemplo após efetuar login) e
    também no command ``sync_users``.

    Nota: estranhamente este signal não funciona nas edições de usuário no admin
    """
    user = kwargs['instance']
    if not isinstance(user, User):
        return

    profile = user.get_profile()
    if not profile:
        return
    profile_sub_instance = user.get_relacionamento()
    if not profile_sub_instance:
        return
    profile_sub_instance_class_name = profile_sub_instance.__class__.__name__

    eh_servidor = profile_sub_instance_class_name == 'Servidor'
    eh_prestador = profile_sub_instance_class_name == 'PrestadorServico'
    eh_aluno = profile_sub_instance_class_name == 'Aluno'

    _vinculo = user.get_vinculo()
    flags = {
        'eh_servidor': eh_servidor,
        'eh_prestador': eh_prestador,
        'eh_aluno': eh_aluno,
        'eh_tecnico_administrativo': eh_servidor and bool(profile_sub_instance.eh_tecnico_administrativo),
        'eh_docente': eh_servidor and bool(profile_sub_instance.eh_docente),
    }
    User.objects.filter(id=user.id).update(
        is_active=True,
        is_staff=True,
        # Institucional primeiro (o que sync_emails grava): User.email é lido por notificações gerais.
        email=_vinculo.email_notificacao if _vinculo else '',
        first_name=profile.nome.split()[0],
        last_name=profile.nome.split()[-1],
        **flags,
    )
    # A instância segue para atualizar_grupos_usuario: com as flags velhas, um login de aluno marcado
    # como servidor quebrava ali e o atomic do logged_in desfazia a correção acima.
    vars(user).update(flags)  # campos simples do model ficam no __dict__ da instância

    """
    Verificando se é um Servidor e adicionando nos grupos: Aposentado ou Servidor
    Inativa o usuário caso o servidor esteja excluído
    """
    if eh_servidor:
        acesso_servidor_liberado = profile_sub_instance.acesso_suap_liberado()
        if (not acesso_servidor_liberado) or profile_sub_instance.eh_aposentado:
            UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user).delete()
            user.groups.clear()
            user.user_permissions.clear()
            if profile_sub_instance.eh_aposentado:
                user.groups.add(Group.objects.get(name='Aposentado'))
            elif not acesso_servidor_liberado:
                User.objects.filter(id=user.id).update(is_active=False, is_staff=False)
        else:
            user.groups.remove(Group.objects.get(name='Aposentado'))
            user.groups.add(Group.objects.get(name='Servidor'))
            if 'edu' in settings.INSTALLED_APPS and profile_sub_instance.eh_docente:
                grupo_professor = Group.objects.get(name='Professor')
                user.groups.add(grupo_professor)

    # Se possui ocupacao_ativa add ao grupo 'Prestador de Serviço' se não adiciona no grupo 'Usuario Externo'
    elif eh_prestador:
        if not profile_sub_instance.ativo:
            User.objects.filter(id=user.id).update(is_active=False, is_staff=False)
        elif profile_sub_instance.possui_ocupacao_ativa():
            user.groups.add(Group.objects.get_or_create(name='Prestador de Serviço')[0])
            prestador = user.get_vinculo().relacionamento
            PrestadorServico.objects.filter(pk=prestador.pk).update(usuario_externo=False, ativo=True)
            PessoaFisica.objects.filter(pk=profile.pk).update(eh_prestador=True)
            User.objects.filter(id=user.id).update(is_active=True, is_staff=True)

            if 'edu' in settings.INSTALLED_APPS:
                ocupacoes = prestador.ocupacaoprestador_set.filter(
                    data_inicio__lte=date.today(),
                    data_fim__gte=date.today(),
                ).values_list('ocupacao_id', flat=True)

                ApoioEspecializado = apps.get_model('edu', 'ApoioEspecializado')
                eh_apoio_especializado = ApoioEspecializado.objects.filter(ativo=True, faz_entrevista=True, ocupacoes__in=ocupacoes).exists()
                if eh_apoio_especializado:
                    group, _ = Group.objects.get_or_create(name='Apoio especializado do Napne')
                    user.groups.add(group)

        else:
            user.groups.add(Group.objects.get_or_create(name='Usuário Externo')[0])
            prestador = user.get_vinculo().relacionamento
            PrestadorServico.objects.filter(pk=prestador.pk).update(usuario_externo=True, ativo=True)
            PessoaFisica.objects.filter(pk=profile.pk).update(eh_prestador=True)
            User.objects.filter(id=user.id).update(is_active=True, is_staff=True)

    elif eh_aluno:
        if profile_sub_instance.eh_aluno_minicurso() and not profile_sub_instance.situacao.ativo:
            User.objects.filter(id=user.id).update(is_active=False, is_staff=False)
        user.groups.add(Group.objects.get(name='Aluno'))

    user.refresh_from_db(fields=('is_active',))
    if not user.is_active:
        UsuarioGrupoSetor.objects.filter(usuario_grupo__user=user).delete()
        user.groups.clear()
        user.user_permissions.clear()
        return

    # Realiza as operações de inclusão e exclusão de grupos, quando esses são
    # gerenciados.
    HistoricoUsuarioGrupo.atualizar_grupos_usuario(user)

    _vinculo = profile_sub_instance.get_vinculo() if hasattr(profile_sub_instance, 'get_vinculo') else None
    if _vinculo and hasattr(_vinculo, 'avaliador'):
        avaliador = _vinculo.avaliador
        grupo_avaliador_interno = Group.objects.get(name='Avaliador Interno')
        grupo_avaliador_externo = Group.objects.get(name='Avaliador Externo')

        if eh_servidor and avaliador.ativo:
            user.groups.add(grupo_avaliador_interno)
        else:
            user.groups.remove(grupo_avaliador_interno)

        if eh_prestador and avaliador.ativo:
            user.groups.add(grupo_avaliador_externo)
        else:
            user.groups.remove(grupo_avaliador_externo)

    if 'processo_eletronico' in settings.INSTALLED_APPS:
        grupo_tem_poder_chefe = Group.objects.get(name='Servidores Com Poder de Chefe')
        CompartilhamentoProcessoEletronicoPoderDeChefe = apps.get_model('processo_eletronico', 'compartilhamentoprocessoeletronicopoderdechefe')
        if CompartilhamentoProcessoEletronicoPoderDeChefe.objects.filter(vinculo_permitido=user.get_vinculo()).exists():
            user.groups.add(grupo_tem_poder_chefe)
        else:
            user.groups.remove(grupo_tem_poder_chefe)

    if 'plan_estrategico' in settings.INSTALLED_APPS:
        grupo_tem_poder_gestor = Group.objects.get_or_create(name='Coordenador de UA')[0]
        CompartilhamentoPoderdeGestorUA = apps.get_model('plan_estrategico', 'compartilhamentopoderdegestorua')
        if CompartilhamentoPoderdeGestorUA.objects.filter(vinculo_permitido=user.get_vinculo()).exists():
            user.groups.add(grupo_tem_poder_gestor)

    #
    # avaliador externo (progressoes tae)
    if 'progressoes' in settings.INSTALLED_APPS:
        ProcessoProgressaoAvaliacao = apps.get_model('progressoes', 'ProcessoProgressaoAvaliacao')
        eh_avaliador = ProcessoProgressaoAvaliacao.objects.filter(avaliador=profile_sub_instance.get_vinculo()).exists()
        if eh_avaliador:
            grupo_avaliador_externo = Group.objects.get_or_create(name='Avaliador Externo')[0]
            user.groups.add(grupo_avaliador_externo)

    # NOTA: Executa o código daqui para baixo se o usuário for um servidor

    if not eh_servidor or not profile_sub_instance.setor:
        return

    cargo_emprego = profile_sub_instance.cargo_emprego.codigo if profile_sub_instance.cargo_emprego else ''

    # Retirado conforme demanda 2413
    # if cargo_emprego == '701009':
    #    user.groups.add(Group.objects.get(name='Auditor'))

    if 'saude' in settings.INSTALLED_APPS:
        if cargo_emprego == '701064' or cargo_emprego == '701093':
            user.groups.add(Group.objects.get(name='Odontólogo'))
        elif cargo_emprego == '701241':
            user.groups.add(Group.objects.get(name='Técnico em Saúde Bucal'))
        elif cargo_emprego == '701047':
            user.groups.add(Group.objects.get(name='Médico'))
        elif cargo_emprego == '701029' or cargo_emprego == '701030':
            user.groups.add(Group.objects.get(name='Enfermeiro'))
        elif cargo_emprego == '701233':
            user.groups.add(Group.objects.get(name='Técnico em Enfermagem'))
        elif cargo_emprego == '701411':
            user.groups.add(Group.objects.get(name='Auxiliar de Enfermagem'))
        elif cargo_emprego == '701038':
            user.groups.add(Group.objects.get(name='Fisioterapeuta'))
        elif cargo_emprego == '701055':
            user.groups.add(Group.objects.get(name='Nutricionista'))
        elif cargo_emprego == '701060':
            user.groups.add(Group.objects.get(name='Psicólogo'))

    hoje = datetime.now()
    grupo_chefe = Group.objects.get(name='Chefe de Setor')
    tem_funcao_hoje = False
    if not profile_sub_instance.eh_estagiario:
        tem_funcao_hoje = (
            profile_sub_instance.servidorfuncaohistorico_set.filter(setor_suap__isnull=False, funcao__codigo__in=Funcao.get_codigos_funcao_chefia())
            .filter(data_inicio_funcao__lte=hoje)
            .filter(Q(data_fim_funcao__gte=hoje) | Q(data_fim_funcao__isnull=True))
            .exists()
        )

    if tem_funcao_hoje:
        user.groups.add(grupo_chefe)
    else:
        user.user_permissions.remove(*grupo_chefe.permissions.all())
        user.groups.remove(grupo_chefe)

    if 'cursos' in settings.INSTALLED_APPS:
        Participante = apps.get_model('cursos', 'participante')
        Curso = apps.get_model('cursos', 'Curso')
        if Participante.objects.filter(servidor=profile_sub_instance).exists() or Curso.objects.filter(responsaveis=profile_sub_instance).exists():
            user.groups.add(Group.objects.get(name='Visualizador de Cursos e Concursos'))

    if 'ponto' in settings.INSTALLED_APPS:
        """
        Verificando se o servidor vai ser inserido ou retirado do grupo de administrador do ponto
        A verificação será da seguinte forma:
           1 - verificar se o servidor tem função ativa no histórico de função
           2 - não pode adicionar estagiário no grupo de administrador do ponto
        """
        grupo_admin_ponto = Group.objects.get_or_create(name='ponto Administrador')[0]
        if tem_funcao_hoje:
            user.groups.add(grupo_admin_ponto)
        else:
            user.groups.remove(grupo_admin_ponto)

    if 'protocolo' in settings.INSTALLED_APPS:
        if (
            profile_sub_instance.eh_tecnico_administrativo or (profile_sub_instance.funcao and not profile_sub_instance.eh_estagiario)
        ) and not user.groups.filter(name__startswith='protocolo').exists():
            user.groups.add(Group.objects.get(name='Tramitador de processos'))

    if 'pgd' in settings.INSTALLED_APPS:
        from pgd.models import ComissaoPGD, TematicaAtividade

        ComissaoPGD.sincronizar_permissoes_comissao_membro(user)
        TematicaAtividade.sincronizar_permissoes_administradores_tematica_administrador(user.get_vinculo())

    if 'pgd2' in settings.INSTALLED_APPS:
        from pgd2.models import ComissaoPGD as ComissaoPGD2

        ComissaoPGD2.sincronizar_permissoes_comissao_membro(user)

    # progressão docente
    if 'progressao_docente' in settings.INSTALLED_APPS:
        Avaliacao = apps.get_model('progressao_docente', 'Avaliacao')
        ProgressaoDocente = apps.get_model('progressao_docente', 'ProgressaoDocente')
        #
        eh_avaliador = Avaliacao.objects.filter(avaliadores=profile_sub_instance).exists()
        eh_dono = ProgressaoDocente.objects.filter(avaliado=profile_sub_instance).exists()
        #
        grupo_avaliador = Group.objects.get_or_create(name='Avaliador Processo')[0]
        if eh_avaliador or eh_dono:
            user.groups.add(grupo_avaliador)
        else:
            user.groups.remove(grupo_avaliador)
    #
    # dados abertos
    if 'dados_abertos' in settings.INSTALLED_APPS:
        from dados_abertos.enums import Situacao_GrupoTrabalho, SituacaoPDA
        from dados_abertos.models import ResponsavelGrupoTrabalho

        #
        grupo, _ = Group.objects.get_or_create(name='Membros do Grupo de Trabalho')
        hoje = timezone.now().date()
        #
        eh_responsavel = ResponsavelGrupoTrabalho.objects.filter(
            responsavel=profile_sub_instance.get_vinculo(),
            ativo=True,
            grupo_trabalho__situacao=Situacao_GrupoTrabalho.ATIVO,
            grupo_trabalho__pda__vigencia_inicio__lte=hoje,
            grupo_trabalho__pda__vigencia_fim__gte=hoje,
            grupo_trabalho__pda__situacao__in=[
                SituacaoPDA.RASCUNHO,
                SituacaoPDA.EM_EXECUCAO,
                SituacaoPDA.EM_APROVACAO,
                SituacaoPDA.AGUARDANDO_PUBLICACAO,
                SituacaoPDA.PUBLICADO,
                SituacaoPDA.EM_REVISAO,
            ],
        ).exists()
        #
        if eh_responsavel:
            user.groups.add(grupo)
        else:
            user.groups.remove(grupo)

    #
    # rsc-tae
    if 'rsc_tae' in settings.INSTALLED_APPS:
        from rsc_tae.models import AvaliadorAuxiliarRSCTae, MembroComissaoRSCTae

        #
        # verifica se o usuário está ATIVO no banco de avaliadores auxiliares do rsc-tae
        # (mesmo critério de elegibilidade do sorteio), caso esteja adiciona no grupo "Avaliador RSC TAE"
        grupo, _ = Group.objects.get_or_create(name='Avaliador RSC TAE')
        eh_avaliador_auxiliar_ativo = AvaliadorAuxiliarRSCTae.objects.filter(
            vinculo=profile_sub_instance.get_vinculo(), ativo=True, data_inativacao__isnull=True
        ).exists()
        if eh_avaliador_auxiliar_ativo:
            user.groups.add(grupo)
        else:
            user.groups.remove(grupo)
        #
        # verifica se o usuário é membro ATIVO da comissão ATIVA rsc-tae, caso seja adiciona no grupo
        # "Membro CRSC TAE". O grupo concede apenas as permissões próprias da comissão
        # (rsc_tae/permissions.yaml) — nunca o grupo de RH sistêmico.
        grupo, _ = Group.objects.get_or_create(name='Membro CRSC TAE')
        estah_ativo_em_crsc = MembroComissaoRSCTae.objects.filter(
            comissao__ativa=True, ativo=True, vinculo=profile_sub_instance.get_vinculo()
        ).exists()
        if estah_ativo_em_crsc:
            user.groups.add(grupo)
        else:
            user.groups.remove(grupo)


models.signals.post_save.connect(user_post_save, sender=User, dispatch_uid='comum.models')
models.signals.m2m_changed.connect(registrar_inclusao_remocao_grupo, sender=User.groups.through)


class AnoManager(models.Manager):
    def ultimos(self):
        return self.get_queryset().filter(ano__gt=1999, ano__lte=datetime.today().year + 1)


class Ano(models.ModelPlus):
    """
    Representa o ano e pode ser reutilizado em outros módulos.
    """

    SEARCH_FIELDS = ['ano']
    ano = models.SmallIntegerField(unique=True)

    objects = AnoManager()

    class Meta:
        ordering = ['-ano']
        verbose_name = 'Ano'
        verbose_name_plural = 'Anos'

    def __str__(self):
        return f'{self.ano}'

    @classmethod
    def obter_ultimos_n_anos(cls, n: int) -> QuerySet[Ano]:
        """
        Retorna os últimos n anos, contando com o ano atual.
        """
        ano_atual = timezone.now().year
        return cls.objects.filter(ano__gt=ano_atual - n, ano__lte=ano_atual)


class Configuracao(models.ModelPlus):
    """
    Classe que mapeia as configurações utilizadas no SUAP.
    Exemplo:
       setor_padrao_extracao_siape = 10
       Onde 10 é o código do setor.

    Todas as configurações devem ser cadastradas e obtidas dinâmicamente.
    """

    app = models.CharField('Aplicação', max_length=50, null=False)
    chave = models.CharField('Chave', max_length=50)
    valor = models.TextField('Valor', null=True)
    descricao = models.TextField('Descrição')

    class Meta:
        unique_together = ['app', 'chave']
        verbose_name = 'Configuração'
        verbose_name_plural = 'Configurações'
        ordering = ['chave']

    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para remover a variável de classe ``_cached``
        """
        cache.delete('_CONFIGURACAO_CACHED')
        super().save(*args, **kwargs)

    def __str__(self):
        return self.descricao

    @classmethod
    def _get_conf_por_chave(cls, app, chave):
        """
        Retorna uma Configuracao se existir uma com a chave passada como parâmetro, None caso contrário
        """
        return cls.objects.filter(app=app, chave=chave).first()

    @classmethod
    def get_valor_por_chave(cls, app, chave, enviroment_variable_name=None):
        key = f'{app}-configuracao-{chave}'
        data = cache.get('_CONFIGURACAO_CACHED', {}, local_ttl=10)
        if not data:
            try:
                for _app, _chave, _valor in Configuracao.objects.values_list('app', 'chave', 'valor'):
                    data[f'{_app}-configuracao-{_chave}'] = _valor
                cache.set('_CONFIGURACAO_CACHED', data)
            except Exception as e:
                capture_exception(e)
        return data.get(key, os.environ.get(enviroment_variable_name.upper()) if enviroment_variable_name else None)

    @classmethod
    def get_valor_por_chave_str(cls, app: str, chave: str, padrao: str = '') -> str:
        """Devolve o valor da configuração como string, ou ``padrao`` quando ausente ou vazio.

        Para quem encadeia ``.upper()``/``.lower()`` no retorno: ``get_valor_por_chave`` devolve
        ``None`` para chave não configurada e estoura ``AttributeError`` em instância nova.
        """
        return cls.get_valor_por_chave(app, chave) or padrao

    @classmethod
    def clear_cache(cls):
        cache.delete('_CONFIGURACAO_CACHED')

    @classmethod
    def eh_email_institucional(cls, email: str | None) -> bool:
        dominios_institucionais = cls.get_valor_por_chave('comum', 'dominios_institucionais')
        if email and dominios_institucionais:
            for dominio in dominios_institucionais.split(';'):
                # Pedaço vazio ('a;') está contido em qualquer e-mail: não é domínio.
                if dominio.strip() and dominio.lower().strip() in email.lower():
                    return True
        return False

    @classmethod
    def email_institucional_permitido(cls, email: str | None) -> bool:
        """
        Informa se `email` pode ser gravado como e-mail institucional da instituição.

        Serve para barrar e-mail de domínio de terceiros (ex.: servidor cedido/redistribuído cujo
        SIAPE ainda traz o e-mail do órgão de origem). Se nenhum domínio institucional estiver
        configurado, não há política a aplicar e qualquer e-mail é aceito.

        Args:
            email: Endereço de e-mail a ser avaliado.

        Returns:
            True se não houver domínios configurados ou se o e-mail pertencer a um deles.
        """
        return not cls.get_valor_por_chave('comum', 'dominios_institucionais') or cls.eh_email_institucional(email)


class DocumentoControleTipo(models.ModelPlus):
    CARTEIRA_FUNCIONAL = 'carteira_funcional'
    CRACHA = 'cracha'

    TIPO_DOCUMENTO_CHOICES = [['', 'Selecione um Tipo de Documento'], [CARTEIRA_FUNCIONAL, 'Carteira Funcional'], [CRACHA, 'Crachá']]
    """
    Representa um tipo de documento a ser controlado
    Exemplo: "Carteira Funcional (Abrangência: Servidores Ativos Permanentes)"
    """
    descricao = models.CharFieldPlus('Descrição', help_text='Descrição do documento. Ex: Carteira Funcional')
    abrangencia = models.ManyToManyFieldPlus('rh.Situacao', verbose_name='Abrangência')
    identificador = models.CharFieldPlus('Identificador', null=True, blank=True)

    class Meta:
        verbose_name = 'Tipo de Documento para Controle'
        verbose_name_plural = 'Tipos de Documentos para Controle'

    def __str__(self):
        return '{} (Abrangência: {})'.format(self.descricao, ', '.join(ab.nome_siape for ab in self.abrangencia.all()))

    def get_link_csv(self):
        return f'/comum/gerar_cvs/{self.id:d}/'

    def save(self, *args, **kwargs):
        for item in self.TIPO_DOCUMENTO_CHOICES:
            if item[0] == self.identificador:
                self.descricao = item[1]
                break
        super().save(*args, **kwargs)


class DocumentoControle(models.ModelPlus):
    # campos comuns
    documento_tipo = models.ForeignKeyPlus(
        'comum.DocumentoControleTipo', verbose_name='Tipo do Documento', null=True, blank=False, on_delete=models.CASCADE
    )
    solicitante_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Solicitante', null=True, blank=False)
    justificativa = models.CharFieldPlus('Justificativa', max_length=2000, null=True, blank=False)
    ativo = models.BooleanField(default=True)
    data_solicitacao = models.DateTimeFieldPlus(auto_now_add=True, blank=True, null=True)
    status_solicitacao = models.IntegerField(
        'Situação da Solicitação',
        choices=SituacaoSolicitacaoDocumento.get_choices(),
        null=False,
        blank=False,
        default=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
    )

    # campos de carteira funcional
    documento_id = models.CharFieldPlus('Identificação do Documento', null=True, blank=True)

    # campos de crachá
    nome_sugerido = models.CharFieldPlus('Nome Sugerido', null=True, max_length=20, blank=True)
    nome_social = models.CharFieldPlus('Nome Social', max_length=20, help_text='Limite de 20 caracteres.', null=True, blank=True)

    class Meta:
        verbose_name = 'Solicitação de Documento'
        verbose_name_plural = 'Solicitações de Documentos'
        unique_together = ('documento_tipo', 'documento_id')

    def __str__(self):
        return f'{self.documento_tipo!s} - ID: {self.id}'

    def get_absolute_url(self):
        return f'/comum/ver_solicitacao_documento/{self.id:d}/'

    def save(self, *args, **kwargs):
        # tratando as informações do campo documento_id
        if self.documento_id == '':
            self.documento_id = None

        """
        No caso, só grava histórico quando for um registro novo. No update não precisa gravar.
        """
        grava_historico = False
        if self.pk:
            obj_old = DocumentoControle.objects.get(pk=self.pk)
            if obj_old.status_solicitacao != self.status_solicitacao:
                grava_historico = True
        else:
            grava_historico = True

        super().save(*args, **kwargs)
        if grava_historico:
            self._salva_dados_historico(tl.get_request(), self.status_solicitacao)

    def pode_atender_solicitacao(self, request):
        return (
            'comum.change_documentocontrole' in request.user.get_group_permissions()
            or 'Confeccionador de Documentos' in request.user.groups.values_list('name', flat=True)
        ) and self.status_solicitacao == SituacaoSolicitacaoDocumento.NAO_ATENDIDA

    def pode_rejeitar_solicitacao(self, request: HttpRequest) -> bool:
        # Mesma regra do atendimento: só se rejeita o que ainda está "Não Atendida" (#17393).
        return self.pode_atender_solicitacao(request)

    @atomic()
    def atender_solicitacao(self, request):
        if self.pode_atender_solicitacao(request):
            # Verifica se o usuário tem solicitação para o mesmo tipo de documento. Caso positivo, inativaremos esses registros
            qs_solicitacao = DocumentoControle.objects.filter(
                solicitante_vinculo=self.solicitante_vinculo,
                status_solicitacao=SituacaoSolicitacaoDocumento.ATENDIDA,
                documento_tipo=self.documento_tipo,
            )
            if qs_solicitacao.exists():
                qs_solicitacao.update(ativo=False)

            situacao = SituacaoSolicitacaoDocumento.ATENDIDA

            # salvando histórico
            request.POST = {}
            request.POST['motivo'] = 'Solicitação atendida.'

            # alterando objeto principal
            self.status_solicitacao = situacao
            self.save()

    @atomic()
    def rejeitar_solicitacao(self, request: HttpRequest) -> None:
        if self.pode_rejeitar_solicitacao(request):
            situacao = SituacaoSolicitacaoDocumento.REJEITADA

            # salvando histórico
            self._salva_dados_historico(request, situacao)

            # salvando objeto principal
            self.status_solicitacao = situacao
            self.save()

    def _salva_dados_historico(self, request, situacao):
        # guardando informações no histórico
        historico = DocumentoControleHistorico()
        historico.solicitacao = self
        historico.responsavel_vinculo = request.user.get_vinculo()
        historico.situacao_historico = situacao
        if request and request.POST and request.POST.get('motivo'):
            historico.motivo = request.POST.get('motivo')
        elif self.justificativa and self.status_solicitacao is not SituacaoSolicitacaoDocumento.ATENDIDA:
            historico.motivo = self.justificativa
        historico.save()

    def get_classe_css(self):
        classe_css = 'alert'
        if self.status_solicitacao == SituacaoSolicitacaoDocumento.REJEITADA:
            classe_css = 'error'
        elif self.status_solicitacao == SituacaoSolicitacaoDocumento.ATENDIDA:
            classe_css = 'success'
        return classe_css


class DocumentoControleHistorico(models.ModelPlus):
    responsavel_vinculo = models.ForeignKeyPlus('comum.Vinculo', verbose_name='Responsável', null=True, blank=False)
    solicitacao = models.ForeignKeyPlus('comum.DocumentoControle', verbose_name='Solicitação', null=False, blank=False, on_delete=models.CASCADE)
    situacao_historico = models.IntegerField('Situação', choices=SituacaoSolicitacaoDocumento.get_choices(), null=False, blank=False)
    data_historico = models.DateTimeFieldPlus(auto_now_add=True, blank=True, null=True)
    motivo = models.CharFieldPlus('Motivo', max_length=2000, null=False, blank=False)

    class Meta:
        verbose_name = 'Histórico da Solicitação de Documento'
        verbose_name_plural = 'Histórico das Solicitações de Documentos'

    def get_classe_css(self):
        classe_css = 'alert'
        if self.situacao_historico == SituacaoSolicitacaoDocumento.REJEITADA:
            classe_css = 'error'
        elif self.situacao_historico == SituacaoSolicitacaoDocumento.ATENDIDA:
            classe_css = 'success'
        return classe_css


class ConfiguracaoImpressaoDocumento(models.ModelPlus):
    uo = models.ForeignKeyPlus('rh.UnidadeOrganizacional', verbose_name=nomenclatura.campus, on_delete=models.CASCADE)
    relacao_impressao = models.ManyToManyField(
        'rh.UnidadeOrganizacional', verbose_name='Relação de Impressão', related_name='uo_relacao_impressao_set'
    )
    tipos_documento = models.ManyToManyFieldPlus('comum.DocumentoControleTipo', verbose_name='Tipos de Documento')
    local_impressao = models.CharFieldPlus(
        'Local de Impressão',
        max_length=30,
        null=True,
        blank=True,
        help_text='Este campo deverá ser preenchido caso o documento necessite do local de expedição. Ex: Natal/RN',
    )

    class Meta:
        verbose_name = 'Configuração de Impressão de Documento'
        verbose_name_plural = 'Configurações de Impressão de Documento'

    def __str__(self):
        return f'Configuração de Impressão de Documento ({self.uo.nome})'


class ConfiguracaoCarteiraFuncional(models.ModelPlus):
    margem_top_bloco_1 = models.IntegerField('Margem do Topo Bloco 1', default=0, null=False, blank=0)
    margem_top_bloco_2 = models.IntegerField('Margem do Topo Bloco 2', default=0, null=False, blank=0)
    margem_top_bloco_3 = models.IntegerField('Margem do Topo Bloco 3', default=0, null=False, blank=0)
    margem_top_bloco_4 = models.IntegerField('Margem do Topo Bloco 4', default=0, null=False, blank=0)

    class Meta:
        verbose_name = 'Configuração da Carteira Funcional'
        verbose_name_plural = 'Configurações da Carteira Funcional'


class Pais(ModelPlus):
    codigo = models.CharField(max_length=4)
    nome = models.CharField(max_length=30, null=True, blank=True)
    equiparado = models.BooleanField(default=False)
    excluido = models.BooleanField(verbose_name='Excluído', default=False)
    codigo_censup = models.CharField(verbose_name='Código CENSUP', default='', blank=True, max_length=3)
    codigo_educacenso = models.CharField(verbose_name='Código EDUCACENSO', default='', blank=True, max_length=3)
    iso_alfa3 = models.CharField(
        'ISO 3166-1 alfa-3',
        max_length=3,
        blank=True,
        default='',
        validators=[RegexValidator(r'^[A-Z]{3}$', 'Use as 3 letras maiúsculas do ISO 3166-1 alfa-3 (ex.: ARG).')],
    )

    class Meta:
        db_table = 'pais'
        verbose_name = 'País'
        verbose_name_plural = 'Países'

    def __str__(self):
        return self.nome


class UnidadeFederativa(ModelPlus):
    nome = models.CharField(max_length=30, null=True, blank=True)
    sigla = models.CharField(max_length=2, null=True, blank=True)

    class Meta:
        db_table = 'unidade_federativa'
        verbose_name = 'Unidade Federativa'
        verbose_name_plural = 'Unidades Federativas'

    def __str__(self):
        return self.nome


class Municipio(models.ModelPlus):
    SEARCH_FIELDS = ['codigo', 'identificacao', 'nome', 'uf']

    codigo = models.CharField('Código SIAFI', max_length=50, blank=True, editable=False)
    identificacao = models.CharFieldPlus(unique=True, editable=False, help_text='Este campo é preenchido automaticamente pelo sistema')
    nome = models.CharFieldPlus()
    uf = models.BrEstadoBrasileiroField()
    codigo_ibge = models.CharField(verbose_name='Código IBGE', null=True, blank=True, max_length=7)

    class Meta:
        ordering = ['identificacao']
        verbose_name = 'Município'
        verbose_name_plural = 'Municípios'

    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para preencher automaticamente o campo ``identificacao``
        """
        self.nome = self.nome.strip()
        self.uf = self.uf.strip()
        self.identificacao = Municipio.get_identificacao(self.nome, self.uf)[:255]
        # Está cadastrando e existe município com a mesma identificação
        if not self.pk and Municipio.objects.filter(identificacao=self.identificacao).exists():
            raise Exception(f'Municipio existente com identificacao "{self.identificacao}". Use o metodo de classe Municipio.get_or_create.')

        super().save(*args, **kwargs)

    def __str__(self):
        return f'{self.nome} / {self.uf}'

    @staticmethod
    def get_identificacao(nome, uf):
        return (f'{to_ascii(nome)}-{to_ascii(uf)}').replace(' ', '').upper()

    @classmethod
    def get_or_create(cls, nome, uf):
        identificacao = Municipio.get_identificacao(nome, uf)
        try:
            obj = cls.objects.get(identificacao=identificacao)
            return obj, 0
        except cls.DoesNotExist:
            obj = cls.objects.create(nome=nome, uf=uf)
            return obj, 1


class PessoaEndereco(models.ModelPlus):
    pessoa = models.ForeignKeyPlus(Pessoa, on_delete=models.CASCADE)
    municipio = models.ForeignKeyPlus('comum.Municipio', verbose_name='Município', null=True, on_delete=models.CASCADE)
    logradouro = models.CharFieldPlus(null=True)
    numero = models.CharField('Nº', max_length=50, null=True)
    complemento = models.CharFieldPlus(null=True)
    bairro = models.CharFieldPlus(null=True)
    cep = models.CharField('CEP', max_length=9, null=True)
    via_form_suap = models.BooleanField('Via SUAP?', default=False)

    class Meta:
        verbose_name = 'Endereço'
        verbose_name_plural = 'Endereços'

    def save(self, *args, **kwargs):
        """
        O método foi sobrescrito para preencher automaticamente o campo ``identificacao``
        """
        for attr in ['logradouro', 'numero', 'complemento', 'bairro']:
            val = getattr(self, attr)
            if val:
                setattr(self, attr, val.strip())
        self.cep = mask_cep(self.cep)
        super().save(*args, **kwargs)

    def __str__(self):
        out = []
        for attr in ['logradouro', 'numero', 'complemento', 'bairro', 'cep', 'municipio']:
            val = getattr(self, attr)
            if val:
                out.append(str(val))
        return ', '.join(out)

    @classmethod
    def create_for_siape(cls, pessoa, logradouro, numero, complemento, bairro, municipio_nome, municipio_uf, cep):
        municipio, _created = Municipio.get_or_create(municipio_nome, municipio_uf)
        cls.objects.create(pessoa=pessoa, logradouro=logradouro, numero=numero, complemento=complemento, bairro=bairro, cep=cep, municipio=municipio)


class PessoaTelefone(models.ModelPlus):
    """
    Armazena os telefones de pessoas.

    Formas de cadastro:
        - Extração SIAPE
        - Extração SIAFI
        - Cadastro manual de PFs e PJs
    """

    pessoa = models.ForeignKeyPlus(Pessoa, on_delete=models.CASCADE)
    numero = models.CharField('Número', max_length=45)  # 45 é o tamanho do telefone SIAFI
    ramal = models.CharField(max_length=5, blank=True)  # Evitar que CharField tenha null=True
    observacao = models.CharField('Observação', max_length=50, blank=True)  # Evitar que CharField tenha null=True

    class Meta:
        verbose_name = 'Telefone'
        verbose_name_plural = 'Telefones'

    def __str__(self):
        if self.observacao:
            return f'{self.numero} ({self.observacao})'
        else:
            return self.numero


class InscricaoFiscal(models.ModelPlus):
    PREFERENCIA_CHOICE = [['M', 'Matutino'], ['V', 'Vespertino'], ['A', 'Matutino e Vespertino']]

    servidor = models.ForeignKeyPlus('rh.Servidor', on_delete=models.CASCADE)
    numero_filhos_menores_21_anos = models.PositiveIntegerField('Número de filhos menores de 21 anos')
    data_inicio_servico_na_instituicao = models.DateFieldPlus('Data do início do serviço na Instituição')


class Ocupacao(models.ModelPlus):
    codigo = models.CharField(
        'Código que identifica a classificação das ocupações definidas pela CBO-2002', max_length=6, null=True, blank=True, unique=True
    )
    descricao = models.CharField('Nome das ocupações definidas pela CBO-2002', max_length=256, null=False)
    representante = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Ocupação'
        verbose_name_plural = 'Ocupações'

    def __str__(self):
        if self.codigo:
            return f'{self.codigo} - {self.descricao}'
        return self.descricao


class PrestadorServicoManager(models.Manager):
    def get_queryset(self):
        queryset = super().get_queryset()
        return queryset.prefetch_related('ocupacaoprestador_set', 'ocupacaoprestador_set__ocupacao')

    def usuarios_externos_com_ocupacao(self):
        return self.get_queryset().filter(ocupacaoprestador__isnull=False)

    def usuarios_externos_sem_ocupacao(self):
        return self.get_queryset().filter(ocupacaoprestador__isnull=True)


class PrestadorServico(AbstractFuncionario):
    SEARCH_FIELDS = ['pessoa_fisica__nome', 'pessoa_fisica__cpf', 'matricula']
    areas_de_conhecimento = models.ManyToManyFieldPlus('rh.AreaConhecimento', blank=True)
    usuario_externo = models.BooleanField(verbose_name='Usuário Externo', default=False, help_text='Indica se o prestador é um Usuário Externo')
    justificativa_cadastro = models.ForeignKeyPlus('comum.JustificativaUsuarioExterno', verbose_name='Justificativa para Cadastro', null=True)

    objects = PrestadorServicoManager()

    class Meta:
        verbose_name = 'Usuário Externo'
        verbose_name_plural = 'Usuários Externos'
        permissions = (('eh_prestador', 'Prestador de Serviço'),)

    EXT_COMBO_RELATED = {
        'select_related': [
            'pessoa_fisica',
        ],
        'prefetch_related': [],
    }

    def __str__(self):
        if getattr(self, 'pessoa_fisica', None):
            return f'{normalizar_nome_proprio(self.pessoa_fisica.nome)} ({self.matricula})'
        else:
            return self.matricula

    @staticmethod
    def gerar_matricula(cpf: str | None) -> str:
        return re.sub(r'\D', '', str(cpf))

    def _gravar_email_pessoal(self, email_notificacao: str | None, email_pessoal: str | None) -> None:
        """Grava em ``Vinculo.email_pessoal`` o primeiro e-mail não institucional informado (vazio se nenhum)."""
        if email_notificacao is None and email_pessoal is None:
            return
        v = self.get_vinculo()
        candidatos = [e for e in (email_notificacao, email_pessoal) if e and not Configuracao.eh_email_institucional(e)]
        v.email_pessoal = candidatos[0] if candidatos else ''
        v.save(update_fields=['email_pessoal'])

    def _revogar_acessos(self) -> None:
        """Remove grupos e encerra as ocupações vigentes de um prestador inativo."""
        vinculo = self.get_vinculo()
        UsuarioGrupoSetor.objects.filter(usuario_grupo__user=vinculo.user).delete()
        vinculo.user.groups.clear()
        OcupacaoPrestador.objects.filter(prestador=self, data_fim__gte=datetime.today()).update(data_fim=(datetime.today() - timedelta(days=1)))
        self.save()

    @staticmethod
    def matricula_do_passaporte(passaporte: str | None, pais: Pais | None) -> str:
        """Login do estrangeiro sem CPF: o do prestador que já tem o par passaporte+país ou, no cadastro novo, a chave ``ARG-AB123456``.

        O legado entrou só com o número do passaporte e mantém esse login. Sem país gravado, ele é a mesma pessoa até prova em
        contrário: a edição que lhe dá o país reusa o cadastro (e o cadastro novo com o mesmo número é recusado pelo usuário que
        já existe), em vez de criar outra pessoa. País sem ISO 3166-1 alfa-3 não forma chave: fica o número.
        """
        from rh.deduplicacao.documentos import chave_passaporte, formatar_passaporte
        from rh.deduplicacao.entrada import filtro_par_passaporte

        numero = formatar_passaporte(passaporte)
        prestadores = PrestadorServico.objects.values_list('matricula', flat=True)
        existente = prestadores.filter(filtro_par_passaporte(passaporte, pais, 'pessoa_fisica__')).first()
        legado_sem_pais = numero and prestadores.filter(matricula__iexact=numero, pessoa_fisica__pais_origem__isnull=True).first()
        return existente or legado_sem_pais or chave_passaporte(numero, getattr(pais, 'iso_alfa3', None)) or numero or ''

    @staticmethod
    def _matricula_do_cadastro(pessoa_dict: PessoaFisicaCadastro) -> tuple[str, bool]:
        """Matrícula do prestador (CPF, ou passaporte de estrangeiro) e se ele é estrangeiro."""
        nacionalidade = pessoa_dict.get('nacionalidade')
        eh_estrangeiro = int(nacionalidade) == Nacionalidade.ESTRANGEIRO if nacionalidade else False
        cpf = pessoa_dict.get('cpf')
        passaporte = pessoa_dict.get('passaporte')
        if cpf:
            return PrestadorServico.gerar_matricula(cpf), eh_estrangeiro
        if eh_estrangeiro and passaporte:
            return PrestadorServico.matricula_do_passaporte(passaporte, pessoa_dict.get('pais_origem')), eh_estrangeiro
        raise ValidationError('É necessário escolher um CPF se brasileiro ou passaporte se for estrangeiro.')

    @staticmethod
    def _pessoa_fisica_do_cadastro(matricula: str, pessoa_dict: PessoaFisicaCadastro) -> tuple[PessoaFisica, bool, bool]:
        """A PF do usuário da matrícula, corrigida pelo próprio cadastro; sem usuário, obtida pelo documento com cautela.

        O usuário da matrícula é o próprio papel: é a mesma pessoa corrigindo seus dados, então um nascimento
        diferente é auditado (``divergencia_entrada``), não recusado.

        Retorna ``(pessoa, criada, propria)``; ``propria`` indica a PF do próprio papel (ramo do usuário da matrícula).
        """
        from rh.deduplicacao.entrada import Politica, aplicar_politica

        pessoa = PessoaFisica.objects.filter(vinculo__user__username=matricula).first()
        if pessoa:
            aplicar_politica(pessoa, pessoa_dict, Politica.AUTORITATIVA, preservar_documento=True)
            pessoa.save()
            return pessoa, False, True
        pessoa, criada = PessoaFisica.objects.obter_ou_criar(pessoa_dict, Politica.CAUTELOSA)
        return pessoa, criada, False

    @staticmethod
    def verificar_cadastro(pessoa_dict: PessoaFisicaCadastro) -> None:
        """Sem escrita, para o ``clean()``: as recusas que o ``update_or_create`` faria com estes dados da pessoa.

        Mesmo caminho do ``_pessoa_fisica_do_cadastro``: a PF do usuário da matrícula (o próprio papel) não recebe documento
        de outra pessoa; sem usuário, a PF achada pelo documento não pode ter outro nascimento.
        """
        from rh.deduplicacao.entrada import Politica, conferir_politica, verificar_documento

        matricula, _ = PrestadorServico._matricula_do_cadastro(pessoa_dict)
        pessoa = PessoaFisica.objects.filter(vinculo__user__username=matricula).first()
        if pessoa:
            conferir_politica(pessoa, pessoa_dict, Politica.AUTORITATIVA, preservar_documento=True)
            return
        verificar_documento(
            cpf=pessoa_dict.get('cpf'),
            passaporte=pessoa_dict.get('passaporte'),
            pais=pessoa_dict.get('pais_origem'),
            nascimento_data=pessoa_dict.get('nascimento_data'),
        )

    @staticmethod
    def _completar_pela_api_externa(pessoa: PessoaFisica, cpf: str) -> None:
        """Completa os dados civis da PF pela API externa de pessoa física, quando ativa.

        A PF pode ser de uma pessoa já existente: a API é autoritativa, mas nunca grava valor vazio.
        """
        from rh.deduplicacao.entrada import Politica, aplicar_politica

        api = APIExterna.PESSOAFISICA
        service = api.get_service()
        if not api.ativo:
            sucesso, dados_cidadao = False, None
        else:
            sucesso, dados_cidadao = service.get_dados_pessoais(cpf)

        sexo = {1: 'M', 2: 'F', 3: None}
        if sucesso:
            dados_cidadao = dados_cidadao[0]
            try:
                nascimento_data = datetime.strptime(dados_cidadao.get('DataNascimento', None), '%Y%m%d').date()
            except Exception:
                nascimento_data = None
            dados = {
                'nome_registro': dados_cidadao.get('Nome', None),
                'sexo': sexo.get(dados_cidadao.get('Sexo')),
                'nome_mae': dados_cidadao.get('NomeMae', None),
                'nome_pai': dados_cidadao.get('NomePai', None),
                'nascimento_data': nascimento_data,
            }
            aplicar_politica(pessoa, dados, Politica.AUTORITATIVA)
        pessoa.save()

    @staticmethod
    def _salvar_contato(modelo: type, pessoa: PessoaFisica, valores: dict | None, criada: bool, propria: bool) -> tuple[Any, bool]:
        """Grava ``valores`` no endereço/telefone da pessoa, criando-o se preciso; sem valores, não faz nada.

        PF recém-criada: grava tudo. PF do próprio papel (``propria``): sobrescreve o contato, sem gravar valor vazio.
        PF de outra pessoa já existente: só cria o contato de quem não tem nenhum e nunca grava valor vazio.
        """
        if not criada:
            valores = {chave: valor for chave, valor in (valores or {}).items() if valor not in (None, '')}
        if not valores:
            return None, False
        contato = modelo.objects.filter(pessoa=pessoa).first()
        if contato and not criada and not propria:
            return contato, False
        criado = contato is None
        if criado:
            contato = modelo(pessoa=pessoa)
        for chave, valor in valores.items():
            setattr(contato, chave, valor)
        contato.save()
        return contato, criado

    @staticmethod
    def update_or_create(
        dados: PrestadorServicoCadastro, enviar_email: bool = True, existente: PrestadorServico | None = None
    ) -> PrestadorServicoRetorno:
        """Cria o prestador ou atualiza o de mesmo documento; na edição, ``existente`` é o prestador editado.

        Na edição, o documento pode mudar (outro país, o país do legado): achar pelo documento novo criaria outra pessoa.
        """
        # dados pessoa fisica
        pessoa_dict = dados['pessoa_fisica']
        cpf = pessoa_dict.get('cpf')
        matricula, eh_estrangeiro = PrestadorServico._matricula_do_cadastro(pessoa_dict)
        if existente is not None:
            matricula = existente.matricula

        # dados prestador
        ativo = dados.get('ativo', True)
        usuario_externo = dados.get('usuario_externo', False)
        # email_secundario/email migraram para Vinculo.email_pessoal: intercepta p/ não vazar para PessoaFisica
        email_notificacao_novo = pessoa_dict.pop('email_secundario', None)
        email_pessoal_novo = pessoa_dict.pop('email', None)
        pessoa, pessoa_fisica_created, pessoa_propria = PrestadorServico._pessoa_fisica_do_cadastro(matricula, pessoa_dict)
        prestador_dict = {'pessoa_fisica': pessoa, 'ativo': ativo, 'usuario_externo': usuario_externo}
        prestador_dict.update({campo: dados[campo] for campo in ('setor', 'justificativa_cadastro') if campo in dados})
        prestador, prestador_created = PrestadorServico.objects.update_or_create(matricula=matricula, defaults=prestador_dict)
        prestador.save()

        # Precisa vir antes do e-mail de boas-vindas: enviar_email_boas_vindas() resolve o
        # destinatário por vinculo.email_pessoal, que só existe depois desta gravação.
        prestador._gravar_email_pessoal(email_notificacao_novo, email_pessoal_novo)

        if not ativo:
            prestador._revogar_acessos()

        # pessoa achada pelo documento (outra pessoa) não tem o contato sobrescrito; o próprio papel atualiza o seu
        endereco, endereco_created = PrestadorServico._salvar_contato(
            PessoaEndereco, pessoa, dados.get('endereco'), pessoa_fisica_created, pessoa_propria
        )
        telefone, telefone_created = PrestadorServico._salvar_contato(
            PessoaTelefone, pessoa, dados.get('telefone'), pessoa_fisica_created, pessoa_propria
        )

        if prestador_created:
            if pessoa.cpf:
                # Cria o papel e ativa o usuário externo e envia e-mail cadastro
                prestador.criar_papel_usuario_externo()
                PrestadorServico._completar_pela_api_externa(pessoa, cpf)

            if enviar_email:
                prestador.get_user().enviar_email_boas_vindas()

        if not prestador.usuario_externo or eh_estrangeiro:
            if getattr(prestador, 'setor', None):
                sync_ldap_setor(prestador.setor)
            sync_ldap_user(prestador.matricula)

        retorno: PrestadorServicoRetorno = {
            'prestador': prestador,
            'prestador_created': prestador_created,
            'pessoa_fisica': pessoa,
            'pessoa_fisica_created': pessoa_fisica_created,
            'endereco': endereco,
            'endereco_created': endereco_created,
            'telefone': telefone,
            'telefone_created': telefone_created,
        }
        return retorno

    def save(self, *args, **kwargs):
        try:
            # Verifica se é estrangeiro para vincular passaporte
            if self.pessoa_fisica.nacionalidade and int(self.pessoa_fisica.nacionalidade) == Nacionalidade.ESTRANGEIRO and not self.pessoa_fisica.cpf:
                # o login de quem já existe não muda (o legado é só o número do passaporte); quem ganha CPF passa ao CPF
                if not (self.pk and self.matricula):
                    self.matricula = self.matricula_do_passaporte(self.pessoa_fisica.passaporte, self.pessoa_fisica.pais_origem)
            elif self.pessoa_fisica.cpf or not (self.pk and self.matricula):
                self.matricula = self.gerar_matricula(self.pessoa_fisica.cpf)
            # sem CPF nem passaporte de estrangeiro (PF separada pela deduplicação: CONFLITO-), o login de quem já existe não muda

            User.objects.get_or_create_user(self.matricula, self.pessoa_fisica.cpf)

            if self.pk and not self.ativo:
                vinculo = self.get_vinculo()
                if vinculo:
                    UsuarioGrupoSetor.objects.filter(usuario_grupo__user=vinculo.user).delete()
                    vinculo.user.groups.clear()
                OcupacaoPrestador.objects.filter(prestador=self, data_fim__gte=datetime.today()).update(
                    data_fim=(datetime.today() - timedelta(days=1))
                )

            # Verifica se possui ocupação Ativa (EX: Recepcionista), caso possua é que será setado eh_usuarioexterno = True
            if self.pk and self.possui_ocupacao_ativa():
                if not self.setor:
                    self.setor = self.ocupacaoprestador_set.filter(data_fim__gte=date.today()).latest('data_fim').setor_suap
                self.usuario_externo = False
            else:
                self.usuario_externo = True
                self.setor = None

            # Recalcula o cache para bloquear ou liberar acesso a determinadas views no middleware de UsuarioSemSetor.
            cache.delete(f'usuario_tem_setor_middleware_{self.matricula}')
            if self.pessoa_fisica.nacionalidade == Nacionalidade.ESTRANGEIRO and not self.pessoa_fisica.cpf:
                self.pessoa_fisica.eh_estrangeiro = True
            else:
                self.pessoa_fisica.eh_estrangeiro = False
            self.pessoa_fisica.eh_prestador = True
            self.pessoa_fisica.eh_usuarioexterno = self.usuario_externo
            self.pessoa_fisica.save()
            User.objects.filter(username=self.matricula).update(
                eh_prestador=True, eh_usuarioexterno=self.usuario_externo, eh_estrangeiro=self.pessoa_fisica.eh_estrangeiro
            )
            super().save(*args, **kwargs)

            user = self.get_user()
            defaults = {'pessoa': self.pessoa_fisica.pessoa_ptr, 'user': user, 'setor': self.setor, 'ativo': self.ativo}
            tipo_relacionamento = ContentType.objects.get_for_model(self)
            Vinculo.objects.update_or_create(id_relacionamento=self.id, tipo_relacionamento=tipo_relacionamento, defaults=defaults)
            user.reset_vinculo()
            user.reset_profile()
        except Exception as e:
            if settings.DEBUG:
                raise e
            capture_exception(e)

    def get_absolute_url(self):
        return reverse_lazy('prestador_servico', kwargs={'id': self.pk})

    # get_vinculo() herdado de AbstractRelacionamento (prefetch-friendly)

    def get_user(self):
        return User.objects.filter(username=self.matricula).first()

    def get_ext_combo_template(self):
        out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{self.pessoa_fisica.nome} ({self.pessoa_fisica.get_cpf_anonimo()})</dd>']
        if self.tem_ocupacao_ativa():
            out.append('<dt class="visually-hidden">Categoria</dt><dd>Prestador de Serviço</dd>')
            if self.setor:
                out.append(f'<dt class="visually-hidden">Setor</dt><dd>{self.setor.get_caminho_as_html()}</dd>')
        else:
            out.append('<dt class="visually-hidden">Categoria</dt><dd>Usuário Externo</dd>')

        template = """<div class="person">
            <div class="photo-circle">
                <img src="{}" alt="Foto de {}" />
            </div>
            <dl>{}</dl>
        </div>
        """.format(self.get_foto_75x100_url(), self.pessoa_fisica.nome, ''.join(out))
        return template

    def tem_ocupacao_ativa(self):
        hoje = date.today()
        return OcupacaoPrestador.objects.filter(prestador=self, data_inicio__lte=hoje, data_fim__gte=hoje).exists()

    def ocupacoes_ativas(self):
        if self.tem_ocupacao_ativa():
            hoje = date.today()
            return OcupacaoPrestador.objects.filter(prestador=self, data_inicio__lte=hoje, data_fim__gte=hoje).order_by('data_fim')
        else:
            return None

    @property
    def professor(self):
        if 'edu' in settings.INSTALLED_APPS:
            vinculo = self.get_vinculo()
            if vinculo:
                return vinculo.professor_set.first()
        return None

    @property
    def papeis_ativos(self):
        hoje = date.today()
        papeis_datas_menores_hoje = self.get_vinculo().papel_set.filter(data_inicio__lte=hoje)
        return papeis_datas_menores_hoje.filter(data_fim__isnull=True) | papeis_datas_menores_hoje.filter(data_fim__gte=hoje)

    def possui_papel_ativo(self):
        return self.papeis_ativos.exists()

    def chefes_imediatos(self):
        if self.setor:
            setor = self.setor

            while not setor.historico_funcao().exists() and setor.superior:
                setor = setor.superior

            return Servidor.objects.filter(pk__in=setor.historico_funcao().values_list('servidor_id', flat=True))
        return PrestadorServico.objects.none()

    def possui_ocupacao_ativa(self):
        return self.ocupacaoprestador_set.filter(data_fim__gte=date.today()).exists()

    def tem_papel_ativo_usuario_externo(self, *args, **kwargs):
        return Papel.objects.filter(vinculo=self.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO, data_fim__isnull=True).exists()

    def pode_ser_ativado(self, *args, **kwargs):
        return bool(not self.get_user().is_active or not self.tem_ocupacao_ativa())

    def ativar(self, *args, **kwargs):
        self.ativo = True
        self.save()
        User.objects.filter(username=self.username).update(is_active=True)

    def inativar(self, *args, **kwargs):
        self.ativo = False
        self.save()
        User.objects.filter(username=self.username).update(is_active=False)

    def criar_papel_usuario_externo(self):
        numero_documento = self.pessoa_fisica.cpf or self.pessoa_fisica.passaporte
        kwargs = {'detalhamento': f'{numero_documento} - Usuário Externo', 'descricao': f'{numero_documento} - Usuário Externo', 'data_fim': None}
        papel = Papel.objects.filter(vinculo=self.get_vinculo(), tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO).first()
        if papel:
            papel.data_fim = None
            papel.save()
        else:
            Papel.objects.update_or_create(
                vinculo=self.get_vinculo(),
                tipo_papel=Papel.TIPO_PAPEL_USUARIOEXTERNO,
                data_inicio=datetime.now(),
                data_fim=None,
                papel_content_type=ContentType.objects.get_for_model(self),
                papel_content_id=self.id,
                defaults=kwargs,
            )

    def documentos_assinados(self, *args, **kwargs):
        DocumentoTexto = apps.get_model('documento_eletronico', 'DocumentoTexto')
        return DocumentoTexto.objects.assinados(self.get_vinculo().user).order_by('-data_criacao')

    def processos_que_sou_interessado(self, *args, **kwargs):
        Processo = apps.get_model('processo_eletronico', 'Processo')
        return Processo.objects.filter(interessados=self).order_by('-data_hora_criacao')

    def cadastrar_telefone(self, telefone):
        PessoaTelefone = apps.get_model('comum', 'PessoaTelefone')
        PessoaTelefone.objects.create(pessoa_id=self.pessoa_fisica.id, numero=telefone)

    def enviar_email_pre_cadastro(self):
        instituicao_sigla = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
        conteudo = f"""<h1>Ativação de Cadastro de Usuário Externo - SUAP</h1>
        <p>Prezado(a) {self.pessoa_fisica.nome},</p>
        <p>Foi realizado um cadastro de Usuário Externo no SUAP/{instituicao_sigla}</p>
        """
        if self.pessoa_fisica.cpf:
            conteudo = (
                conteudo
                + f"""
            <p>Acesse o endereço abaixo para autenticar no SUAP e clique na opção Entrar com Gov.BR</p>
            <p><a href="{settings.SITE_URL}">{settings.SITE_URL}</a></p>.
            <p><span>Atenção:</span> É necessário ter conta no <a href="https://sso.acesso.gov.br/">Gov.BR</a></p>
            """
            )
        else:
            conteudo = (
                conteudo
                + f"""
            <p>Acesse o endereço abaixo para autenticar no SUAP pela primeira vez.</p>
            <p><a href="{settings.SITE_URL}/comum/solicitar_trocar_senha/">{settings.SITE_URL}/comum/solicitar_trocar_senha/</a></p>.
            <p><span>Atenção:</span> O seu usuário é o número do seu passaporte sem traço ou ponto.</p>
            """
            )
        vinculo = self.get_vinculo()
        return send_mail('[SUAP] Cadastro de Usuário Externo', conteudo, settings.DEFAULT_FROM_EMAIL, [vinculo.email_notificacao if vinculo else ''])


class JustificativaUsuarioExterno(models.ModelPlus):
    justificativa = models.CharFieldPlus('Perfil', max_length=255)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Perfil para Cadastro de Usuário Externo'
        verbose_name_plural = 'Perfis para Cadastro de Usuários Externos'


class OcupacaoPrestador(models.ModelPlus):
    prestador = models.ForeignKeyPlus('comum.PrestadorServico', null=False, blank=False, on_delete=models.CASCADE)
    ocupacao = models.ForeignKeyPlus('comum.Ocupacao', null=False, blank=False, on_delete=models.CASCADE)
    empresa = models.ForeignKeyPlus('rh.PessoaJuridica', verbose_name='Pessoa Jurídica', null=False, blank=False, on_delete=models.CASCADE)
    data_inicio = models.DateFieldPlus('Data de início', null=False, blank=False)
    data_fim = models.DateFieldPlus('Data fim', null=False, blank=False)
    setor_suap = models.ForeignKeyPlus('rh.Setor', null=True, blank=False, related_name='cargo_funcao_setor_suap', on_delete=models.CASCADE)
    atualizado_por = models.ForeignKeyPlus(
        'comum.Vinculo', on_delete=models.CASCADE, null=True, related_name='ocupacaoprestador_atualizado_por_set', verbose_name='Atualizado por'
    )
    atualizado_em = models.DateTimeFieldPlus('Atualizado em', null=True, blank=True, auto_now=True)

    class Meta:
        verbose_name = 'Ocupação de Prestador de Serviço'
        verbose_name_plural = 'Ocupações dos Prestadores de Serviços'
        ordering = ('-data_inicio',)

    def __str__(self):
        if self.ocupacao:
            return f'{self.prestador.pessoa_fisica.nome} - {self.ocupacao} - {self.empresa}'
        else:
            return f'{self.prestador.pessoa_fisica.nome} - {self.empresa}'

    def can_delete(self, user):
        return user.has_perm('comum.delete_ocupacaoprestador') and not self.assinou_documentos()

    def delete(self, *args, **kwargs):
        self.prestador.save()
        if not self.assinou_documentos():
            Papel.objects.filter(
                vinculo=self.prestador.get_vinculo(),
                tipo_papel=Papel.TIPO_PAPEL_OCUPACAO,
                data_inicio=self.data_inicio,
                papel_content_type=ContentType.objects.get_for_model(self.ocupacao),
                papel_content_id=self.ocupacao.id,
            ).delete()
            super().delete(*args, **kwargs)
            self.prestador.save()
        else:
            raise ValidationError('Impossível apagar Ocupação deste prestador, pois dcocumentos foram assinados com o Papel vinculado a ocupação.')

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        kwargs = {
            'detalhamento': str(self),
            'descricao': str(self),
            'setor_suap': self.setor_suap,
            'data_fim': self.data_fim,
            'portaria': '-',
        }
        Papel.objects.update_or_create(
            vinculo=self.prestador.get_vinculo(),
            data_inicio=self.data_inicio,
            tipo_papel=Papel.TIPO_PAPEL_OCUPACAO,
            papel_content_type=ContentType.objects.get_for_model(self.ocupacao),
            papel_content_id=self.ocupacao.id,
            defaults=kwargs,
        )
        if self.data_fim >= date.today():
            self.prestador.ativo = True
        self.prestador.save()

    def assinou_documentos(self):
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import Assinatura
            from rh.models import Papel

            if self.prestador:
                papeis = Papel.objects.filter(
                    vinculo=self.prestador.get_vinculo(),
                    tipo_papel=Papel.TIPO_PAPEL_OCUPACAO,
                    data_inicio=self.data_inicio,
                    papel_content_type=ContentType.objects.get_for_model(self.ocupacao),
                    papel_content_id=self.ocupacao.id,
                )

                if self.pk and Assinatura.objects.filter(papel__in=papeis).exists():
                    return True
            else:
                return False
        else:
            return False

    def eh_ativa(self):
        hoje = date.today()
        return self.data_fim >= hoje


class Predio(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'uo__setor__sigla']
    nome = models.CharField(max_length=100)
    uo = models.ForeignKeyPlus(UnidadeOrganizacional, verbose_name=nomenclatura.campus, null=False, on_delete=models.CASCADE)
    ativo = models.BooleanField(default=True)

    # Sistemas Construtivos
    estrutura = models.ManyToManyFieldPlus('comum.EstruturaPredio', blank=True, verbose_name='Estrutura')
    cobertura = models.ManyToManyFieldPlus('comum.CoberturaPredio', blank=True, verbose_name='Cobertura')
    vedacao = models.ManyToManyFieldPlus('comum.VedacaoPredio', blank=True, verbose_name='Vedação')
    sistema_sanitario = models.ManyToManyFieldPlus('comum.SistemaSanitarioPredio', blank=True, verbose_name='Sistema Sanitário')
    sistema_abastecimento = models.ManyToManyFieldPlus('comum.SistemaAbastecimentoPredio', blank=True, verbose_name='Sistema de Abastecimento')
    sistema_alimentacao_eletrica = models.ManyToManyFieldPlus(
        'comum.SistemaAlimentacaoEletricaPredio', blank=True, verbose_name='Sistema de Alimentação Elétrica'
    )
    potencia_transformador = models.PositiveIntegerField('Potência do Transformador', null=True, blank=True, help_text='Informar em KVA')
    informacao_sistema_alimentacao_eletrica = models.TextField(
        'Informações Adicionais', null=True, blank=True, help_text='Informações adicionais do sistema de alimentação elétrica'
    )
    sistema_protecao_descarga_atmosferica = models.ManyToManyFieldPlus(
        'comum.SistemaProtecaoDescargaAtmosfericaPredio', blank=True, verbose_name='Sistema de Proteção Contra Descargas Atmosféricas'
    )
    acabamento_externo = models.ManyToManyFieldPlus('comum.AcabamentoExternoPredio', blank=True, verbose_name='Acabamento Externo (Fachadas)')

    class Meta:
        unique_together = ('nome', 'uo')
        verbose_name = 'Prédio'
        verbose_name_plural = 'Prédios'
        ordering = ['uo__setor__sigla', 'nome']

    def __str__(self):
        return f'{self.nome} ({self.uo})'

    def get_absolute_url(self):
        return f'/comum/predio/{self.pk}/'

    def get_obra_original(self):
        return self.obra_set.filter(tipo=Obra.TIPO_ORIGINAL).first()

    def get_area_construida(self):
        return self.obra_set.exclude(tipo=Obra.TIPO_REFORMA).aggregate(Sum('area_construida'))['area_construida__sum']

    def get_area_acrescentada(self):
        return self.obra_set.filter(tipo=Obra.TIPO_AMPLIACAO).aggregate(Sum('area_construida'))['area_construida__sum']

    def get_ampliacoes(self):
        return self.obra_set.filter(tipo=Obra.TIPO_AMPLIACAO).order_by('data_recebimento')

    def get_reformas(self):
        return self.obra_set.filter(tipo=Obra.TIPO_REFORMA).order_by('data_recebimento')

    def get_combates_incendio_panico(self):
        return self.combateincendiopanico_set.all()

    def tem_sistema_construtivo(self):
        return (
            self.estrutura.exists()
            or self.cobertura.exists()
            or self.vedacao.exists()
            or self.sistema_sanitario.exists()
            or self.sistema_abastecimento.exists()
            or self.sistema_alimentacao_eletrica.exists()
            or self.sistema_protecao_descarga_atmosferica.exists()
            or self.acabamento_externo.exists()
        )


class Obra(models.ModelPlus):
    TIPO_ORIGINAL = 0
    TIPO_AMPLIACAO = 1
    TIPO_REFORMA = 2
    TIPO_CHOICES = [[TIPO_ORIGINAL, 'Original'], [TIPO_AMPLIACAO, 'Ampliação'], [TIPO_REFORMA, 'Reforma']]

    predio = models.ForeignKeyPlus(Predio, verbose_name='Prédio', on_delete=models.CASCADE)
    tipo = models.PositiveIntegerField(verbose_name='Tipo da Obra', choices=TIPO_CHOICES)
    data_inicio = models.DateFieldPlus(verbose_name='Início da Obra')
    descricao = models.TextField('Descrição do Escopo', null=True, blank=True)
    data_recebimento = models.DateFieldPlus(verbose_name='Recebimento Definitivo', null=True, blank=True)
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        processo_recebimento = models.ForeignKeyPlus('protocolo.Processo', verbose_name='Processo de Recebimento', null=True, blank=True)
    area_construida = models.DecimalFieldPlus(verbose_name='Área Construída', help_text='Informar em m²', null=True, blank=True)

    def get_idade_obra(self):
        hoje = datetime.now()
        return relativedelta(self.data_recebimento, hoje)

    def save(self, *args, **kwargs):
        if self.tipo == Obra.TIPO_ORIGINAL and Obra.objects.filter(predio_id=self.predio.pk, tipo=Obra.TIPO_ORIGINAL).exclude(pk=self.pk).exists():
            raise ValueError('Não é possível cadastrar mais de uma obra do tipo Original')
        if self.tipo != Obra.TIPO_ORIGINAL and not Obra.objects.filter(predio_id=self.predio.pk).exists():
            raise ValueError('O primeiro cadastro deve ser da obra Original.')
        super().save(*args, **kwargs)


class CombateIncendioPanico(models.ModelPlus):
    predio = models.ForeignKeyPlus(Predio, verbose_name='Prédio', on_delete=models.CASCADE)
    protocolo_pscip = models.CharFieldPlus('Protocolo PSCIP', null=True, blank=True)
    data_vistoria = models.DateFieldPlus('Vistoria Técnica', null=True, blank=True)
    data_validade_alvara = models.DateFieldPlus('Validade do Alvará', null=True, blank=True)
    alvara = models.PrivateFileField(verbose_name='Alvará', max_length=255, null=True, blank=True, upload_to='comum/predio/alvaras')
    observacoes = models.TextField('Observações', null=True, blank=True)

    class Meta:
        verbose_name = 'Combate a Incêndio e Pânico'
        verbose_name_plural = 'Combates a Incêndio e Pânico'
        ordering = ['predio__uo__setor__sigla', '-data_vistoria']


class EstruturaPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Estrutura'
        verbose_name_plural = 'Estruturas'


class CoberturaPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Cobertura'
        verbose_name_plural = 'Coberturas'


class VedacaoPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Vedação'
        verbose_name_plural = 'Vedações'


class SistemaSanitarioPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Sistema Sanitário'
        verbose_name_plural = 'Sistemas Sanitários'


class SistemaAbastecimentoPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Sistema de Abastecimento'
        verbose_name_plural = 'Sistemas de Abastecimentos'


class SistemaAlimentacaoEletricaPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Sistema de Alimentação Elétrica'
        verbose_name_plural = 'Sistemas de Alimentação Elétrica'


class SistemaProtecaoDescargaAtmosfericaPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Sistema de Proteção Contra Descargas Atmosféricas'
        verbose_name_plural = 'Sistemas de Proteção Contra Descargas Atmosféricas'


class AcabamentoExternoPredio(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Acabamento Externo (Fachada)'
        verbose_name_plural = 'Acabamentos Externos (Fachadas)'


class AtivasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(ativa=True)


class Sala(models.ModelPlus):
    SEARCH_FIELDS = ['nome', 'predio__nome', 'predio__uo__nome', 'predio__uo__sigla']

    nome = models.CharField(max_length=100)
    predio = models.ForeignKeyPlus(Predio, verbose_name='Prédio', on_delete=models.CASCADE)
    descricao = models.TextField('Descrição', null=True, blank=True)
    ativa = models.BooleanField('Ativa', default=True)
    agendavel = models.BooleanField('Agendável', default=False)
    setores = models.ManyToManyFieldPlus(
        Setor, blank=True, help_text='Informe os setores que estão na sala. Esse campo é opcional e meramente informativo.'
    )
    capacidade = models.PositiveIntegerField('Capacidade da sala', null=True, blank=True, help_text='Em número de pessoas')
    avaliadores_de_agendamentos = models.ManyToManyFieldPlus(
        'comum.User',
        blank=True,
        related_name='salas_avaliadas',
        verbose_name='Avaliadores de Agendamento',
        help_text='Informe os usuários responsáveis por responder às solicitações de agendamento. Digite parte da matrícula ou primeiro nome.',
    )
    restringir_agendamentos_no_campus = models.BooleanField(f'Agendamento apenas por servidores {nomenclatura.do_campus}', default=False)
    informacoes_complementares = models.TextField(
        'Informações complementares',
        null=True,
        blank=True,
        help_text='As informações complementares serão exibidas para o usuário durante a solicitação de agendamento',
    )

    area_util = models.DecimalFieldPlus('Área Útil', null=True, blank=True, help_text='Informar em m²')
    area_parede = models.DecimalFieldPlus('Área de Parede', null=True, blank=True, help_text='Informar em m²')
    uso = models.ForeignKeyPlus('comum.UsoSala', blank=True, null=True, verbose_name='Uso da sala')
    classificacao = models.ForeignKeyPlus('comum.ClassificacaoSala', blank=True, null=True, verbose_name='Classificação')

    # Acabamento e sistemas prediais
    instalacao_eletrica = models.ManyToManyFieldPlus('comum.InstalacaoEletricaSala', blank=True, verbose_name='Instalação Elétrica')
    instalacao_logica = models.ManyToManyFieldPlus('comum.InstalacaoLogicaSala', blank=True, verbose_name='Instalação de Lógica')
    instalacao_hidraulica = models.ManyToManyFieldPlus('comum.InstalacaoHidraulicaSala', blank=True, verbose_name='Instalação Hidráulica')
    instalacao_gases = models.ManyToManyFieldPlus('comum.InstalacaoGasesSala', blank=True, verbose_name='Instalação de Gases')
    climatizacao = models.ManyToManyFieldPlus('comum.ClimatizacaoSala', blank=True, verbose_name='Climatização')
    acabamento_parede = models.ManyToManyFieldPlus('comum.AcabamentoParedeSala', blank=True, verbose_name='Acabamento das Paredes')
    piso = models.ManyToManyFieldPlus('comum.PisoSala', blank=True, verbose_name='Piso')
    forro = models.ManyToManyFieldPlus('comum.ForroSala', blank=True, verbose_name='Forro')
    esquadrias = models.ManyToManyFieldPlus('comum.EsquadriasSala', blank=True, verbose_name='Esquadrias')

    # Managers
    objects = models.Manager()
    ativas = AtivasManager()

    class Meta:
        verbose_name = 'Sala'
        verbose_name_plural = 'Salas'
        unique_together = ('nome', 'predio')
        ordering = ('nome',)
        permissions = (('pode_avaliar_solicitacao_reserva_de_sala', 'Pode avaliar solicitação reserva de sala'),)

    def __str__(self):
        return f'{self.nome} - {self.predio!s}'

    def get_absolute_url(self):
        return f'/comum/sala/visualizar/{self.id:d}/'

    # RN4 Sala disponível para agendamento, é uma sala com o status ativo e agendável
    #  verdadeiro e ter pelo menos um avaliador responsável pela sala.
    def is_agendavel(self):
        return self.ativa and self.agendavel and self.avaliadores_de_agendamentos.exists()

    def pode_agendar(self, user):
        if self.restringir_agendamentos_no_campus:
            return self.predio.uo == get_uo(user)
        else:
            return True

    def get_solicitacoes_reserva_pendentes(self, data_inicio, data_fim, hora_inicio=None, hora_fim=None):
        """
        Retornas solicitações pendentes que conflitam com os parâmetros passados
        """
        solicitacoes_conflitantes = SolicitacaoReservaSala.pendentes.filter(sala=self)
        # Remove as solicitações que a data_fim vem antes da data_inicio de pesquisa
        solicitacoes_sem_antes = solicitacoes_conflitantes.exclude(data_fim__lt=data_inicio)
        # Remove as solicitações que a data_inicio vem depois da data_fim de pesquisa
        solicitacoes_sem_depois = solicitacoes_conflitantes.exclude(data_inicio__gt=data_fim)
        solicitacoes_conflitantes = solicitacoes_sem_antes & solicitacoes_sem_depois
        if hora_inicio and hora_fim:
            # Remove as solicitações que a data_fim é igual a data_inicio mas a hora não conflita
            solicitacoes_sem_antes = solicitacoes_conflitantes.exclude(
                Q(data_fim=data_inicio) & (Q(hora_fim__lte=hora_inicio) | Q(hora_inicio__gte=hora_fim))
            )
            # Remove as solicitações que a data_inicio é igual a data_fim mas a hora não conflita
            solicitacoes_sem_depois = solicitacoes_conflitantes.exclude(
                Q(data_inicio=data_fim) & (Q(hora_fim__lte=hora_inicio) | Q(hora_inicio__gte=hora_fim))
            )
            # Adicionando as que são exatamente iguais
            solicitacoes_iguais = solicitacoes_conflitantes.filter(
                data_inicio=data_inicio, data_fim=data_fim, hora_inicio=hora_inicio, hora_fim=hora_fim
            )
            solicitacoes_conflitantes = solicitacoes_sem_antes & solicitacoes_sem_depois
            return solicitacoes_conflitantes | solicitacoes_iguais

        return solicitacoes_conflitantes

    def get_solicitacoes_conflitantes(self, data_inicio, data_fim):
        """
        Retona uma lista de solicitações que estão conflitando com as datas nos parâmetros, levando em consideração a recorrência
        """
        solicitacoes_candidatas = self.get_solicitacoes_reserva_pendentes(data_inicio.date(), data_fim.date(), data_inicio.time(), data_fim.time())
        esperar_por_ids = []
        for solicitacao_candidata in solicitacoes_candidatas:
            for datas_candidatas_inicio, datas_candidatas_fim in solicitacao_candidata.get_datas_solicitadas():
                if not (data_inicio >= datas_candidatas_fim or data_fim <= datas_candidatas_inicio):
                    esperar_por_ids.append(solicitacao_candidata.id)

        return SolicitacaoReservaSala.objects.filter(id__in=esperar_por_ids)

    def get_reservas(self, data_inicio, data_fim):
        """
        Retornas reservas (provinientes de uma solicitações atendidas ou de uma indisponibilização) que conflitam com os parâmetros passados
        """
        reservas = ReservaSala.deferidas.filter(sala=self)

        # Remove as reservas que a data_fim vem antes da data_inicio de pesquisa
        reservas = reservas.exclude(data_fim__lte=data_inicio)
        # Remove as reservas que a data_inicio vem depois da data_fim de pesquisa
        reservas = reservas.exclude(data_inicio__gte=data_fim)
        return reservas

    def tem_conflito_reserva(self, solicitacao):
        for [solicitacao_data_inicio, solicitacao_data_fim] in solicitacao.get_datas_solicitadas():
            if self.get_reservas(solicitacao_data_inicio, solicitacao_data_fim).exists():
                return True
        return False

    def programacao_atual(self, solicitacao_atual=None):
        def _get_descricao(solicitacao, data_inicio, data_fim, dia_todo=False):
            justificativa = truncatechars(solicitacao.justificativa, 75)
            horario = '{} às {}'.format(data_inicio.strftime('%H:%M'), data_fim.strftime('%H:%M'))
            if dia_todo:
                horario = 'Todo o dia'
            descricao = '<p><strong>{horario}</strong> {justificativa}</p>'
            if isinstance(solicitacao, SolicitacaoReservaSala) and solicitacao.pode_ver():
                descricao = '<a href="/comum/sala/ver_solicitacao/{id}/"><strong>{horario}</strong> {justificativa}</a>'
            elif isinstance(solicitacao, IndisponibilizacaoSala):
                descricao = '<a href="/comum/sala/ver_indisponibilizacao/{id}/"><strong>{horario}</strong> {justificativa}</a>'

            return descricao.format(id=solicitacao.id, horario=horario, justificativa=justificativa)

        def _add_dia_cal(cal, solicitacao, data_inicio, data_fim, css, title):
            descricao = _get_descricao(solicitacao, data_inicio, data_fim)
            cal.adicionar_evento_calendario(data_inicio, data_fim, descricao, css, title)

        def _add_dia_todo_cal(cal, solicitacao, data, css, title):
            descricao = _get_descricao(solicitacao, data, data, dia_todo=True)
            cal.adicionar_evento_calendario(data, data, descricao, css, title, dia_todo=True)

        def _add_evento_calendario(cal, solicitacao, dia_todo_list, agenda_data_inicio, agenda_data_fim, css, title):
            # Se for o dia todo os eventos são separados, o primeiro e o ultimo tem o horário diferenciado
            if dia_todo_list or (agenda_data_fim - agenda_data_inicio).days:
                data_fim = datetime(agenda_data_inicio.year, agenda_data_inicio.month, agenda_data_inicio.day, 23, 59, 59)  # hour,minute,second
                _add_dia_cal(cal, solicitacao, agenda_data_inicio, data_fim, css, title)

                for dia_todo in dia_todo_list:
                    _add_dia_todo_cal(cal, solicitacao, dia_todo, css, title)

                data_inicio = datetime(agenda_data_fim.year, agenda_data_fim.month, agenda_data_fim.day, 0, 0, 0)  # hour,minute,second
                _add_dia_cal(cal, solicitacao, data_inicio, agenda_data_fim, css, title)
            else:
                _add_dia_cal(cal, solicitacao, agenda_data_inicio, agenda_data_fim, css, title)

        def _add_solicitacao_calendario(cal, solicitacao, agenda_data_inicio, agenda_data_fim):
            dia_todo_list = solicitacao.get_dia_todo_list()
            title = f'Solicitação de {solicitacao.solicitante.get_relacionamento()}'
            if solicitacao_atual and solicitacao_conflito:
                css = 'info'
            else:
                css = 'warning'

            _add_evento_calendario(cal, solicitacao, dia_todo_list, agenda_data_inicio, agenda_data_fim, css, title)

        def _add_reserva_calendario(cal, reserva):
            agenda_data_inicio = reserva.data_inicio
            agenda_data_fim = reserva.data_fim
            dia_todo_list = reserva.get_dia_todo_list()

            if hasattr(reserva, 'indisponibilizacaosala'):
                indisponibilizacao = reserva.indisponibilizacaosala
                css = 'error'
                title = f'Registrado por {indisponibilizacao.usuario}'
                _add_evento_calendario(cal, indisponibilizacao, dia_todo_list, agenda_data_inicio, agenda_data_fim, css, title)

            else:
                solicitacao = reserva.solicitacao
                if reserva.cancelada:
                    css = 'extra'
                    title = f'Solicitada por {solicitacao.solicitante.get_relacionamento()}'
                else:
                    if solicitacao_atual and solicitacao == solicitacao_atual:
                        css = 'info'
                    else:
                        css = 'success'
                    title = f'Agendada para {solicitacao.solicitante.get_relacionamento()}'
                _add_evento_calendario(cal, solicitacao, dia_todo_list, agenda_data_inicio, agenda_data_fim, css, title)

        # a partir do mês corrente
        data_agora = datetime.now()
        ano_corrente = data_agora.year
        mes_corrente = data_agora.month
        # ------------
        # até o mês do último agendamento que 'caia' pelo menos dentro do mês corrente
        qs_solicitacoes = (
            SolicitacaoReservaSala.pendentes.filter(sala=self)
            .exclude(status__in=[SolicitacaoReservaSala.STATUS_EXCLUIDA, SolicitacaoReservaSala.STATUS_INDEFERIDA])
            .exclude(cancelada=True)
        )
        qs_reservas = ReservaSala.objects.filter(sala=self).exclude(cancelada=True)

        cal_meses = []

        cal = CalendarioPlus()
        cal.mostrar_mes_e_ano = True

        mostrar_diarios = Configuracao.get_valor_por_chave('edu', 'mostrar_diarios_reserva_sala') if 'edu' in settings.INSTALLED_APPS else False

        # settings para mostrar informações de diários aqui
        if mostrar_diarios:
            Diario = apps.get_model('edu', 'Diario')
            mesano_diarios_list = []
            #
            # montando um dicionários para poupar consulta em banco de dados quando temos solicitações de reserva e reservas
            dict_diarios = {}
            _qs_diarios = Diario.objects.filter(Q(local_aula=self) | Q(local_laboratorio=self) | Q(locais_aula_secundarios=self)).filter(
                calendario_academico__data_fim__gte=data_agora
            )
            for diario in _qs_diarios:
                # data de inicio e fim (consigo elas no calendário acadêmico que está no arquivo diretorias.py)
                data_inicio = diario.calendario_academico.data_inicio
                if data_inicio < data_agora.date():
                    data_inicio = data_agora.date()
                data_fim = diario.calendario_academico.data_fim
                delta = data_fim - data_inicio  # timedelta

                # selecionando os horários de aula do diário
                dias_semana = diario.get_horarios_por_dia_semana()
                for i in range(delta.days + 1):
                    d = data_inicio + timedelta(days=i)
                    d_semana = d.weekday() + 1
                    if d_semana in dias_semana:
                        #
                        # ATENCAO ::: o título abaixo dever ser o mesmo usado na descrição da solicitação da reserva!
                        diario_nome = diario.gerar_justificativa_reserva_sala()
                        horarios = dias_semana.get(d_semana)
                        for horario in horarios:
                            #
                            # usuario com permissão específica para renderizar o botão de deferir
                            btn_deferir = ''
                            if self.pode_agendar(tl.get_user()):
                                url_este_periodo = f'/comum/sala/deferir_reserva_diario/{diario.id}/{d}_{horario.horario_aula.inicio.replace(":", "-")}/{d}_{horario.horario_aula.termino.replace(":", "-")}/'
                                url_um_periodo = f'/comum/sala/deferir_reserva_diario_no_periodo/{diario.id}/'
                                btn_deferir = f"""
                                <br />
                                <ul class="action-bar mt-4">
                                    <li class="has-child">
                                        <a class="btn" href="#">Deferir...</a>
                                        <ul>
                                            <li><a href="{url_este_periodo}" class="confirm" data-confirm="Deseja mesmo confirmar a reserva da sala?">Apenas este horário</a></li>
                                            <li><a href="{url_um_periodo}" class="popup">Um período</a></li>
                                        </ul>
                                    </li>
                                </ul>
                                """

                            descricao = f'Aula às {horario.horario_aula}{btn_deferir}'
                            if d not in dict_diarios:
                                dict_diarios[d] = [
                                    {
                                        'titulo': diario_nome,
                                        'descricao': descricao,
                                        'data': d,
                                        'hora_inicio': horario.horario_aula.inicio,
                                        'hora_fim': horario.horario_aula.termino,
                                    }
                                ]
                            else:
                                dict_diarios[d].append(
                                    {
                                        'titulo': diario_nome,
                                        'descricao': descricao,
                                        'data': d,
                                        'hora_inicio': horario.horario_aula.inicio,
                                        'hora_fim': horario.horario_aula.termino,
                                    }
                                )

        tem_solicitacoes = qs_solicitacoes.exists()
        tem_reservas = qs_reservas.exists()
        if tem_solicitacoes or tem_reservas:
            # pega data_fim do último agendamento
            if not tem_solicitacoes:
                data_fim = qs_reservas.latest('data_fim').data_fim.date()
            elif not tem_reservas:
                data_fim = qs_solicitacoes.latest('data_fim').data_fim
            else:
                data_fim_solicitacao = qs_solicitacoes.latest('data_fim').data_fim
                data_fim_reserva = qs_reservas.latest('data_fim').data_fim.date()
                data_fim = data_fim_solicitacao
                if data_fim_reserva > data_fim_solicitacao:
                    data_fim = data_fim_reserva
            # o último agendamento deve 'cair' pelo menos dentro do mês corrente
            # (mes agenda >= mes corrente E ano agenda >= ano corrente) OU (ano agenda > ano corrente)
            # ex:
            #    mes/ano corrente = 10/2013
            #    mes/ano solicitacao   = 01/2014
            #    ** o mes da solicitacao é menor que o mês corrente (o teste (mes solicitacao >= mes corrente E ano solicitacao >= ano corrente) FALHA!!)
            #    ** porém, ano solicitacao é maior (por isso da necessidade do teste (ano solicitacao > ano corrente)
            if (data_fim.year == ano_corrente and data_fim.month >= mes_corrente) or (data_fim.year > ano_corrente):
                ultimo_ano = data_fim.year
                ultimo_mes = data_fim.month

                mes = mes_corrente  # inicializa mês
                for ano in range(ano_corrente, ultimo_ano + 1):
                    mes_final = 12  # por padrão
                    if ano == ultimo_ano:
                        mes_final = ultimo_mes
                    for imes in range(mes, mes_final + 1):
                        # -----------------------
                        # Adição das Solicitações
                        for solicitacao in qs_solicitacoes:
                            solicitacao_conflito = False
                            for [agenda_data_inicio, agenda_data_fim] in solicitacao.get_datas_solicitadas():
                                # DIARIOS
                                if mostrar_diarios:
                                    if agenda_data_inicio.date() in dict_diarios:
                                        for i in dict_diarios[agenda_data_inicio.date()]:
                                            if (
                                                i.get('titulo') == solicitacao.justificativa
                                                and solicitacao.hora_inicio.strftime('%H:%M') == i.get('hora_inicio')
                                                and solicitacao.hora_fim.strftime('%H:%M') == i.get('hora_fim')
                                            ):
                                                dict_diarios[agenda_data_inicio.date()].remove(i)

                                if agenda_data_inicio.year == ano and agenda_data_inicio.month == imes:
                                    if solicitacao_atual:
                                        for [solicitacao_data_inicio, _solicitacao_data_fim] in solicitacao_atual.get_datas_solicitadas():
                                            if agenda_data_inicio.date() == solicitacao_data_inicio.date() and solicitacao == solicitacao_atual:
                                                solicitacao_conflito = True
                                                break

                                    _add_solicitacao_calendario(cal, solicitacao, agenda_data_inicio, agenda_data_fim)
                        # -------------------

                        # Adição das Reservas
                        data_inicial = date(ano, imes, 1)
                        data_final = date(ano, imes, 1) + relativedelta(months=+1)
                        qs_reservas_inicio = qs_reservas.filter(data_inicio__range=[data_inicial, data_final])
                        qs_reservas_fim = qs_reservas.filter(data_fim__range=[data_inicial, data_final])
                        queryset_reservas = qs_reservas_inicio | qs_reservas_fim
                        for reserva in queryset_reservas:
                            # DIARIOS
                            if mostrar_diarios:
                                agenda_data_inicio = reserva.data_inicio
                                if agenda_data_inicio.date() in dict_diarios:
                                    for i in dict_diarios[agenda_data_inicio.date()]:
                                        if (
                                            i.get('titulo') == reserva.solicitacao.justificativa
                                            and reserva.solicitacao.hora_inicio.strftime('%H:%M') == i.get('hora_inicio')
                                            and reserva.solicitacao.hora_fim.strftime('%H:%M') == i.get('hora_fim')
                                        ):
                                            dict_diarios[agenda_data_inicio.date()].remove(i)

                            _add_reserva_calendario(cal, reserva)

                        # SETTINGS diários
                        fazer_append = True
                        if mostrar_diarios:
                            fazer_append = False
                            try:
                                if int(imes) < 10:
                                    imes = f'0{imes}'
                                idx = f'{imes}{ano}'
                                mesano_diarios_list.append(idx)
                            except Exception:
                                pass

                        if fazer_append:
                            cal_meses.append(cal.formato_mes(int(ano), int(imes)))
                        # -------------------
                    mes = 1  # reinicia mês (o ano subsequente deve começar por janeiro)
            # ------------

            # DIARIOS
        if mostrar_diarios:
            for (
                c,
                v,
            ) in dict_diarios.items():
                v_ordenado = sorted(v, key=lambda d: d['hora_inicio'])
                for di in v_ordenado:
                    descricao_completa = f'<strong>{di.get("titulo")}</strong>{di.get("descricao")}'
                    cal.adicionar_evento_calendario(c, None, descricao_completa, 'extra5', di.get('titulo'))
                    # verificando o mes/ano do registro
                    mesano = f'{c.strftime("%m")}{c.year}'
                    if mesano not in mesano_diarios_list:
                        mesano_diarios_list.append(mesano)

            for x in mesano_diarios_list:
                mes = x[:2]
                ano = x[2:]
                cal_meses.append(cal.formato_mes(int(ano), int(mes)))

        if not cal_meses:
            ano = data_agora.year
            mes = data_agora.strftime('%m')
            cal_meses.append(cal.formato_mes(int(ano), int(mes)))

        return cal_meses  # lista de calendários formato mês

    @classmethod
    def eh_avaliador_salas(cls, user):
        return user.has_perm('comum.pode_avaliar_solicitacao_reserva_de_sala') and user.salas_avaliadas.exists()

    def eh_avaliador(self, user):
        return user.has_perm('comum.pode_avaliar_solicitacao_reserva_de_sala') and self.avaliadores_de_agendamentos.filter(id=user.id).exists()

    def tem_dados_complementares(self):
        return self.area_util or self.area_parede or self.uso or self.classificacao

    def tem_acabamento_sistemas_prediais(self):
        return (
            self.instalacao_eletrica.exists()
            or self.instalacao_logica.exists()
            or self.instalacao_hidraulica.exists()
            or self.instalacao_gases.exists()
            or self.climatizacao.exists()
            or self.acabamento_parede.exists()
            or self.piso.exists()
            or self.forro.exists()
            or self.esquadrias.exists()
        )


class UsoSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Uso da Sala'
        verbose_name_plural = 'Usos da Sala'


class ClassificacaoSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    descricao_expandida = models.TextField(verbose_name='Descrição Expandida')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Classificação'
        verbose_name_plural = 'Classificações'

    def __str__(self):
        return f'{self.descricao} - {self.descricao_expandida}'


class InstalacaoEletricaSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Instalação Elétrica'
        verbose_name_plural = 'Instalações Elétricas'


class InstalacaoLogicaSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Instalação de Lógica'
        verbose_name_plural = 'Instalações de Lógica'


class InstalacaoHidraulicaSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Instalação Hidráulica'
        verbose_name_plural = 'Instalações Hidráulicas'


class InstalacaoGasesSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Instalação de Gases'
        verbose_name_plural = 'Instalações de Gases'


class ClimatizacaoSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Climatização'
        verbose_name_plural = 'Climatizações'


class AcabamentoParedeSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Acabamento da Parede'
        verbose_name_plural = 'Acabamentos das Paredes'


class PisoSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Piso'
        verbose_name_plural = 'Pisos'


class ForroSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Forro'
        verbose_name_plural = 'Forros'


class EsquadriasSala(models.ModelPlus):
    descricao = models.CharFieldPlus(verbose_name='Descrição')
    ativo = models.BooleanField(verbose_name='Ativo', default=True)

    class Meta:
        verbose_name = 'Esquadria'
        verbose_name_plural = 'Esquadrias'


class SolicitacaoAbertasManager(models.Manager):
    def get_queryset(self):
        agora = datetime.now()
        return super().get_queryset().filter(data_hora_inicio__gt=agora)


class SolicitacaoPendentesManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(status=SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO)


class SolicitacaoReservaSala(models.ModelPlus):
    RECORRENCIA_EVENTO_UNICO = 'evento_unico'
    RECORRENCIA_SEMANALMENTE = 'semanalmente'
    RECORRENCIA_QUINZENALMENTE = 'quinzenalmente'
    RECORRENCIA_MENSALMENTE = 'mensalmente'
    RECORRENCIA_CHOICES = (
        (RECORRENCIA_EVENTO_UNICO, 'Evento único'),
        (RECORRENCIA_SEMANALMENTE, 'Semanalmente'),
        (RECORRENCIA_QUINZENALMENTE, 'Quinzenalmente'),
        (RECORRENCIA_MENSALMENTE, 'Mensalmente'),
    )

    STATUS_DEFERIDA = 'deferida'
    STATUS_INDEFERIDA = 'indeferida'
    STATUS_PARCIALMENTE_DEFERIDA = 'parcialmente_deferida'
    STATUS_AGUARDANDO_AVALIACAO = 'aguardando_avaliacao'
    STATUS_EXCLUIDA = 'excluida'
    STATUS_CHOICES = (
        (STATUS_DEFERIDA, 'Deferida'),
        (STATUS_INDEFERIDA, 'Indeferida'),
        (STATUS_PARCIALMENTE_DEFERIDA, 'Parcialmente Deferida'),
        (STATUS_AGUARDANDO_AVALIACAO, 'Aguardando Avaliação'),
        (STATUS_EXCLUIDA, 'Excluída'),
    )

    sala = models.ForeignKeyPlus('Sala', verbose_name='Sala solicitada', on_delete=models.CASCADE)
    solicitante = models.ForeignKeyPlus('comum.User', related_name='solicitacao_reserva_solicitante', null=True)
    data_solicitacao = models.DateTimeFieldPlus('Data da Solicitação')
    data_inicio = models.DateFieldPlus('Data de Início')
    hora_inicio = models.TimeFieldPlus('Hora de Início')
    data_hora_inicio = models.DateTimeFieldPlus('Data Hora Início', null=False)
    data_fim = models.DateFieldPlus('Data de Fim')
    hora_fim = models.TimeFieldPlus('Hora de Fim')
    data_hora_fim = models.DateTimeFieldPlus('Data Hora Início', null=False)

    justificativa = models.TextField()
    recorrencia = models.CharFieldPlus('Recorrência', choices=RECORRENCIA_CHOICES)
    interessados_vinculos = models.ManyToManyFieldPlus('comum.Vinculo', blank=True)
    anexo = models.FileFieldPlus('Anexo', upload_to='upload/comum/solicitacao_reserva_sala/', filetypes=['doc', 'pdf'], null=True, blank=True)
    # TODO: verificar que é melhor deixar aqui ou criar um modelo separado
    recorrencia_segunda = models.BooleanField('Segunda', default=False)
    recorrencia_terca = models.BooleanField('Terça', default=False)
    recorrencia_quarta = models.BooleanField('Quarta', default=False)
    recorrencia_quinta = models.BooleanField('Quinta', default=False)
    recorrencia_sexta = models.BooleanField('Sexta', default=False)
    recorrencia_sabado = models.BooleanField('Sábado', default=False)
    recorrencia_domingo = models.BooleanField('Domingo', default=False)
    status = models.CharFieldPlus('Situação', choices=STATUS_CHOICES, default=STATUS_AGUARDANDO_AVALIACAO)

    # avaliação
    data_avaliacao = models.DateTimeFieldPlus('Data da Avaliação', null=True)
    avaliador = CurrentUserField(default=None, related_name='solicitacao_reserva_avaliador')
    observacao_avaliador = models.TextField('Observação', blank=True)

    # Cancelamento pelo próprio solicitante
    cancelada = models.BooleanField('Cancelada', default=False)
    justificativa_cancelamento = models.TextField('Justificativa do Cancelamento', blank=True)
    cancelada_por = models.ForeignKeyPlus(
        Vinculo, verbose_name='Cancelada por', on_delete=models.SET_NULL, null=True, related_name='solicitacaoreserva_cancelada_por'
    )
    data_cancelamento = models.DateTimeFieldPlus('Data da Avaliação', null=True)

    objects = models.Manager()
    abertas = SolicitacaoAbertasManager()
    pendentes = SolicitacaoPendentesManager()

    class Meta:
        verbose_name = 'Solicitação de Reserva de Sala'
        verbose_name_plural = 'Solicitações de Reserva de Sala'

    def get_absolute_url(self):
        return f'/comum/sala/ver_solicitacao/{self.id:d}/'

    def save(self, *args, **kwargs):
        self.data_hora_inicio = self.get_data_hora_inicio()
        self.data_hora_fim = self.get_data_hora_fim()
        super().save(*args, **kwargs)

    def gerar_reservas(self):
        for data_inicio, data_fim in self.get_datas_solicitadas():
            reserva = ReservaSala()
            reserva.sala = self.sala
            reserva.solicitacao = self
            reserva.data_inicio = data_inicio
            reserva.data_fim = data_fim
            reserva.save()

    def get_esperar_por(self):
        """
        Retona uma lista de solicitações que estão conflitando com a solicitação, levando em consideração a recorrência
        """
        solicitacoes_candidatas = self.sala.get_solicitacoes_reserva_pendentes(
            self.data_inicio, self.data_fim, self.hora_inicio, self.hora_fim
        ).exclude(id=self.id)
        esperar_por_ids = []
        for solicitacao_candidata in solicitacoes_candidatas:
            for datas_candidatas_inicio, datas_candidatas_fim in solicitacao_candidata.get_datas_solicitadas():
                for datas_solicitadas_inicio, datas_solicitadas_fim in self.get_datas_solicitadas():
                    if not (datas_solicitadas_inicio >= datas_candidatas_fim or datas_solicitadas_fim <= datas_candidatas_inicio):
                        esperar_por_ids.append(solicitacao_candidata.id)

        return SolicitacaoReservaSala.objects.filter(id__in=esperar_por_ids)

    def get_datas_solicitadas(self):
        """
        Retorna datas solicitadas em datetime como uma lista de tuplas, cada tupla contem o datetime inicio e o fim
        """
        if hasattr(self, 'datas_solicitadas'):
            return self.datas_solicitadas

        primeira_data_adicionada = None
        qtd_dias_mes = []
        if self.recorrencia != self.RECORRENCIA_EVENTO_UNICO:
            datas_solicitadas = []
            for index, data in enumerate(daterange(self.data_inicio, self.data_fim)):
                if datas_solicitadas:
                    primeira_data_adicionada = datas_solicitadas[0][0].date()

                if self.recorrencia == self.RECORRENCIA_SEMANALMENTE:
                    self.__adicionar_dia_recorrencia(datas_solicitadas, data)

                # O periodo é quinzenal porém com relação a data quinzena é igual a 14 dias
                elif self.recorrencia == self.RECORRENCIA_QUINZENALMENTE:
                    if not primeira_data_adicionada or (
                        primeira_data_adicionada
                        and primeira_data_adicionada + timedelta(14 * ((index + 1) // 14))
                        <= data
                        < primeira_data_adicionada + timedelta(14 * ((index + 1) // 14) + 7)
                    ):
                        self.__adicionar_dia_recorrencia(datas_solicitadas, data)

                elif self.recorrencia == self.RECORRENCIA_MENSALMENTE:
                    # pegar a quantidade do mês e decrementar
                    qtd_dias = calendar.monthrange(data.year, data.month)[1]
                    if [data.month, qtd_dias] not in qtd_dias_mes:
                        qtd_dias_mes.append([data.month, qtd_dias])

                    quantidade_mes = 0
                    for _mes, dias in qtd_dias_mes:
                        if index - dias >= 0:
                            index -= dias
                            quantidade_mes += 1
                        else:
                            break

                    if not primeira_data_adicionada or adicionar_mes(primeira_data_adicionada, quantidade_mes) <= data < adicionar_mes(
                        primeira_data_adicionada, quantidade_mes
                    ) + timedelta(7):
                        self.__adicionar_dia_recorrencia(datas_solicitadas, data)

            return datas_solicitadas

        return [[self.get_data_hora_inicio(), self.get_data_hora_fim()]]

    def __adicionar_dia_recorrencia(self, datas_solicitadas, data):
        """
        Adicionar a data na lista de datas_solicitadas com base na recorrencia
        """
        # data.weekday() = Monday is 0 and Sunday is 6
        SEGUNDA = 0
        TERCA = 1
        QUARTA = 2
        QUINTA = 3
        SEXTA = 4
        SABADO = 5
        DOMINGO = 6

        if self.recorrencia_segunda and data.weekday() == SEGUNDA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_terca and data.weekday() == TERCA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_quarta and data.weekday() == QUARTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_quinta and data.weekday() == QUINTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_sexta and data.weekday() == SEXTA:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_sabado and data.weekday() == SABADO:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])
        if self.recorrencia_domingo and data.weekday() == DOMINGO:
            datas_solicitadas.append([self.get_data_hora_inicio(data), self.get_data_hora_fim(data)])

    def get_recorrencias(self):
        recorrencias = []
        if self.recorrencia != SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO:
            if self.recorrencia_segunda:
                recorrencias.append('segunda')
            if self.recorrencia_terca:
                recorrencias.append('terca')
            if self.recorrencia_quarta:
                recorrencias.append('quarta')
            if self.recorrencia_quinta:
                recorrencias.append('quinta')
            if self.recorrencia_sexta:
                recorrencias.append('sexta')
            if self.recorrencia_sabado:
                recorrencias.append('sabado')
            if self.recorrencia_domingo:
                recorrencias.append('domingo')
        return ', '.join(recorrencias)

    def get_ch_solicitacao(self):
        seconds = 0
        for [solicitacao_data_inicio, solicitacao_data_fim] in self.get_datas_solicitadas():
            periodo = solicitacao_data_fim - solicitacao_data_inicio
            seconds += periodo.seconds
        ch_reserva = seconds / 3600
        return ch_reserva

    def pode_cancelar(self, user=None):
        if not user:
            user = tl.get_user()

        eh_avaliador = self.sala.eh_avaliador(user)
        return (eh_avaliador and self.status == self.STATUS_DEFERIDA and self.data_hora_fim > datetime.now()) or (
            self.solicitante == user
            and self.status != self.STATUS_INDEFERIDA
            and self.status != self.STATUS_EXCLUIDA
            and self.data_hora_fim > datetime.now()
        )

    # UC04 - RN1 essa opção só estará disponível para avaliador e se a data final da requisição for menor ou igual a data atual e a requisição não tenha sido avaliada.
    def pode_avaliar(self, user=None):
        if not user:
            user = tl.get_user()

        eh_avaliador = self.sala.eh_avaliador(user)
        return (
            (user.is_superuser or eh_avaliador)
            and self.data_hora_fim >= datetime.now()
            and (self.status == SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO)
        )

    def pode_excluir(self, user=None):
        if not user:
            user = tl.get_user()
        return (user.is_superuser) or (self.solicitante == user and self.status == SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO)

    def pode_ver(self, user=None):
        if not user:
            user = tl.get_user()

        eh_avaliador = self.sala.eh_avaliador(user)
        return (
            user.is_superuser
            or eh_avaliador
            or self.solicitante == user
            or self.status == SolicitacaoReservaSala.STATUS_DEFERIDA
            or self.status == SolicitacaoReservaSala.STATUS_PARCIALMENTE_DEFERIDA
        )

    def vinculos_envolvidos(self, solicitante=True, interessados=True, avaliadores_sala=True):
        vinculos = []
        if solicitante:
            vinculos.append(self.solicitante.get_vinculo())
        if interessados:
            vinculos.extend(list(self.interessados_vinculos.all()))
        if avaliadores_sala:
            vinculos.extend([avaliador.get_vinculo() for avaliador in self.sala.avaliadores_de_agendamentos.all()])

        return list(set(vinculos))

    def notificar_cadastro(self):
        if self.status == SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO:
            url = f'{settings.SITE_URL}/comum/sala/ver_solicitacao/{self.id}/'
            titulo = '[SUAP] Reservas de Salas: Nova Solicitação'
            mensagem = f"""<h1>Solicitação de Reserva de Sala Efetuada</h1>
                <dl>
                    <dt>Sala:</dt><dd>{self.sala}</dd>
                    <dt>Período:</dt><dd>{self.get_periodo()}</dd>
                    <dt>Requisitante:</dt><dd>{self.solicitante.get_profile().nome}</dd>
                </dl>
                <p class="more-info">Para mais informações, acesse: <a href="{url}">{url}</a></p>"""
            vinculos = self.vinculos_envolvidos(solicitante=True, interessados=True, avaliadores_sala=True)
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)

    def notificar_avaliacao(self):
        if self.status != SolicitacaoReservaSala.STATUS_AGUARDANDO_AVALIACAO:
            avaliador = 'SUAP'
            if self.avaliador:
                avaliador = self.avaliador.get_profile().nome

            titulo = f'[SUAP] Reservas de Salas: Solicitação {self.get_status_display()}'
            mensagem = f"""<h1>Solicitação de Reserva de Sala: {self.get_status_display()}</h1>
                <dl>
                    <dt>Sala:</dt><dd>{self.sala}</dd>
                    <dt>Período:</dt><dd>{self.get_periodo()}</dd>
                    <dt>Requisitante:</dt><dd>{self.solicitante.get_profile().nome}</dd>
                    <dt>Avaliador:</dt><dd>{avaliador}</dd>"""
            if self.observacao_avaliador:
                mensagem += f'<dt>Observação do Avaliador:</dt><dd>{self.observacao_avaliador}</dd>'
            mensagem += '</dl>'
            vinculos = self.vinculos_envolvidos(solicitante=True, interessados=True, avaliadores_sala=False)
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)

    def notificar_cancelamento(self):
        if self.status == SolicitacaoReservaSala.STATUS_INDEFERIDA:
            cancelada_por = self.cancelada_por and str(self.cancelada_por) or self.solicitante
            titulo = '[SUAP] Reservas de Salas: Solicitação Cancelada'
            mensagem = f"""<h1>Solicitação de Reserva de Sala Cancelada</h1>
                <dl>
                    <dt>Sala:</dt><dd>{self.sala}</dd>
                    <dt>Período:</dt><dd>{self.get_periodo()}</dd>
                    <dt>Requisitante:</dt><dd>{self.solicitante.get_profile().nome}</dd>
                    <dt>Cancelada por:</dt><dd>{cancelada_por}</dd>
                    """
            if self.observacao_avaliador:
                mensagem += f'<dt>Observação do Avaliador:</dt><dd>{self.observacao_avaliador}</dd>'
            mensagem += '</dl>'
            vinculos = self.vinculos_envolvidos(solicitante=False, interessados=True, avaliadores_sala=True)
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)

    def get_data_hora_inicio(self, data=None):
        if not data:
            data = self.data_inicio
        return datetime.combine(data, self.hora_inicio)

    def get_data_hora_fim(self, data=None):
        if not data:
            data = self.data_fim
        return datetime.combine(data, self.hora_fim)

    def get_periodo(self):
        if self.recorrencia == SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO:
            if self.data_fim == self.data_inicio:
                return '{} às {} do dia {}'.format(
                    self.hora_inicio.strftime('%H:%M'), self.hora_fim.strftime('%H:%M'), self.data_inicio.strftime('%d/%m/%Y')
                )
            else:
                return '{} do dia {} às {} do dia {}'.format(
                    self.hora_inicio.strftime('%H:%M'),
                    self.data_inicio.strftime('%d/%m/%Y'),
                    self.hora_fim.strftime('%H:%M'),
                    self.data_fim.strftime('%d/%m/%Y'),
                )
        else:
            datas = '{} a {}'.format(self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))
            if self.data_fim == self.data_inicio:
                datas = self.data_inicio.strftime('%d/%m/%Y')
            return '{} | Horário: {} - {}'.format(datas, self.hora_inicio.strftime('%H:%M'), self.hora_fim.strftime('%H:%M'))

    def get_dia_todo_list(self):
        dia_todo = []
        if self.recorrencia == self.RECORRENCIA_EVENTO_UNICO:
            dias = (self.data_fim - self.data_inicio).days
            for dia in range(1, dias):
                dia_todo.append(self.data_inicio + timedelta(dia))

        return dia_todo


class ReservaDeferidasManager(models.Manager):
    def get_queryset(self):
        return super().get_queryset().filter(cancelada=False)


class ReservaSala(models.ModelPlus):
    sala = models.ForeignKeyPlus('Sala', verbose_name='Sala Solicitada', on_delete=models.CASCADE)
    solicitacao = models.ForeignKeyPlus('SolicitacaoReservaSala', verbose_name='Solicitação de Sala', null=True, on_delete=models.CASCADE)
    data_inicio = models.DateTimeFieldPlus('Data/Hora de Início')
    data_fim = models.DateTimeFieldPlus('Data/Hora Final')

    cancelada = models.BooleanField('Cancelada', default=False)
    justificativa_cancelamento = models.TextField('Justificativa do Cancelamento', blank=True)
    cancelada_por = CurrentUserField(default=None)
    data_cancelamento = models.DateTimeFieldPlus('Data da Avaliação', null=True)

    ocorreu = models.BooleanField('Atividade Ocorreu', null=True)
    motivo_nao_ocorreu = models.TextField('Motivo da Atividade Não Ter Ocorrido', blank=True)

    objects = models.Manager()
    deferidas = ReservaDeferidasManager()

    class Meta:
        verbose_name = 'Reserva de Sala'
        verbose_name_plural = 'Reservas de Salas'

    def get_periodo(self):
        if self.solicitacao and self.solicitacao.recorrencia == SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO:
            if self.data_fim.date() == self.data_inicio.date():
                return '{} às {} do dia {}'.format(
                    self.data_inicio.strftime('%H:%M'), self.data_fim.strftime('%H:%M'), self.data_inicio.strftime('%d/%m/%Y')
                )
            else:
                return '{} do dia {} às {} do dia {}'.format(
                    self.data_inicio.strftime('%H:%M'),
                    self.data_inicio.strftime('%d/%m/%Y'),
                    self.data_fim.strftime('%H:%M'),
                    self.data_fim.strftime('%d/%m/%Y'),
                )
        else:
            datas = '{} a {}'.format(self.data_inicio.strftime('%d/%m/%Y'), self.data_fim.strftime('%d/%m/%Y'))
            if self.data_fim.date() == self.data_inicio.date():
                datas = self.data_inicio.strftime('%d/%m/%Y')
            return '{} | Horário: {} - {}'.format(datas, self.data_inicio.strftime('%H:%M'), self.data_fim.strftime('%H:%M'))

    def pode_cancelar(self, user=None):
        if not user:
            user = tl.get_user()

        eh_avaliador = self.sala.eh_avaliador(user)
        # Não deve ser possível cancelar reserva de sala deferida após ter passado o período de reserva da mesma.
        return (eh_avaliador or self.solicitacao.solicitante == user) and self.data_fim > datetime.now()

    # RN7  A data final do registro de manutenção menor que a data atual.
    def pode_excluir(self, user=None):
        if not user:
            user = tl.get_user()

        eh_avaliador = user.salas_avaliadas.filter(id=self.sala_id).exists()
        return (user.is_superuser) or (eh_avaliador and self.data_fim > datetime.now())

    @atomic
    def cancelar(self, notificar=True):
        self.data_cancelamento = datetime.now()
        self.cancelada = True
        if self.solicitacao:
            # se ainda tiver reservas não canceladas
            if self.solicitacao.reservasala_set.filter(cancelada=False).exclude(id=self.id).exists():
                self.solicitacao.status = SolicitacaoReservaSala.STATUS_PARCIALMENTE_DEFERIDA
            else:
                self.solicitacao.status = SolicitacaoReservaSala.STATUS_INDEFERIDA

            self.solicitacao.save()

        self.save()
        if notificar:
            self.notificar_cancelamento()

    def notificar_cancelamento(self):
        if self.cancelada and self.solicitacao:
            titulo = '[SUAP] Reservas de Salas: Reserva Cancelada'
            mensagem = f"""<h1>Reserva de Sala Cancelada:</h1>
                <dl>
                    <dt>Sala:</dt><dd>{self.sala}</dd>
                    <dt>Período:</dt><dd>{self.get_periodo()}</dd>
                    <dt>Requisitante:</dt><dd>{self.solicitacao.solicitante.get_profile().nome}</dd>
                    <dt>Motivo:</dt><dd>{self.justificativa_cancelamento}</dd>
                </dl>"""
            vinculos = self.solicitacao.vinculos_envolvidos(solicitante=True, interessados=True, avaliadores_sala=True)
            send_notification(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, vinculos)

    def get_dia_todo_list(self):
        dia_todo = []
        dias = (self.data_fim - self.data_inicio).days
        for dia in range(1, dias):
            dia_todo.append(self.data_inicio + timedelta(dia))

        return dia_todo


class IndisponibilizacaoSalaEmAndamentoManager(models.Manager):
    def get_queryset(self):
        query_set = super().get_queryset()
        data_agora = datetime.now()
        # lista todos os registros de manutenção de salas na qual data inicio maiorigual que data atual e data fim menor/igual que data atual.
        query_set = query_set.filter(data_inicio__lte=data_agora, data_fim__gte=data_agora)
        return query_set


class IndisponibilizacaoSala(ReservaSala):
    usuario = CurrentUserField(related_name='indisponibilizacao_sala_usuario')
    data = models.DateTimeFieldPlus()
    justificativa = models.TextField()

    objects = models.Manager()
    em_andamento = IndisponibilizacaoSalaEmAndamentoManager()

    class Meta:
        verbose_name = 'Indisponibilização de Reserva de Sala'
        verbose_name_plural = 'Indisponibilizações de Reserva de Salas'


class RepresentanteLegal(models.ModelPlus):
    usuario_externo = models.OneToOneFieldPlus('comum.PrestadorServico')
    matricula = models.CharField(max_length=7, unique=True)

    class Meta:
        verbose_name = 'Representante Legal'
        verbose_name_plural = 'Representantes Legais'


class GrauParentesco(models.ModelPlus):
    codigo = models.CharField(max_length=10, null=True, unique=True)
    nome = models.CharField(max_length=50)
    excluido = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Grau de Parentesco'
        verbose_name_plural = 'Graus de Parentesco'

    def __str__(self):
        return self.nome


class Pensionista(models.ModelPlus):
    usuario_externo = models.OneToOneFieldPlus('comum.PrestadorServico')
    matricula = models.CharField('Matrícula do Pensionista', max_length=8, unique=True)
    representante_legal = models.ForeignKeyPlus(RepresentanteLegal, null=True, blank=True, on_delete=models.CASCADE)
    numero_processo = models.CharField(max_length=15, blank=True, null=True)
    grau_parentesco = models.ForeignKeyPlus(GrauParentesco, blank=True, null=True, on_delete=models.CASCADE)
    data_inicio_pagto_beneficio = models.DateField(blank=True, null=True)
    data_fim_pagto_beneficio = models.DateField(blank=True, null=True)

    def __str__(self):
        return f'Pensionista: {self.usuario_externo.pessoa_fisica.nome} - ({self.matricula})'

    @property
    def instituidor(self):
        if self.contracheque_set.all().exists():
            return self.contracheque_set.latest('id').servidor
        return None

    def get_absolute_url(self):
        return f'/comum/pensionista/{self.matricula}/'


class Dependente(models.ModelPlus):
    usuario_externo = models.OneToOneFieldPlus('comum.PrestadorServico')
    matricula = models.CharField(max_length=8, unique=True, null=True, blank=True)
    servidor = models.ForeignKeyPlus('rh.Servidor', related_name='servidordependente', on_delete=models.CASCADE)
    representante_legal = models.ForeignKeyPlus(RepresentanteLegal, null=True, blank=True, on_delete=models.CASCADE)
    grau_parentesco = models.ForeignKeyPlus(GrauParentesco, blank=True, null=True, on_delete=models.CASCADE)
    codigo_condicao = models.CharField(max_length=3, null=True, blank=True)

    def save(self, *args, **kwargs):
        if not self.matricula:
            self.matricula = None
        super().save(*args, **kwargs)


class Beneficio(models.ModelPlus):
    codigo = models.CharField(max_length=2, null=True, unique=True)
    nome = models.CharField(max_length=30)
    excluido = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Benefício'
        verbose_name_plural = 'Benefícios'

    def __str__(self):
        return self.nome


class BeneficioDependente(models.ModelPlus):
    dependente = models.ForeignKeyPlus(Dependente, on_delete=models.CASCADE)
    beneficio = models.ForeignKeyPlus(Beneficio, on_delete=models.CASCADE)
    data_inicio = models.DateField()
    data_termino = models.DateField(null=True)

    class Meta:
        verbose_name = 'Associação Benefício-Dependente'
        verbose_name_plural = 'Associações Benefício-Dependente'

    def __str__(self):
        return '{} - {} - {}'.format(
            self.dependente.usuario_externo.pessoa_fisica.nome,
            self.beneficio.nome,
            self.data_inicio.strftime('%d-%m-%Y'),
        )


class SetorTelefone(models.ModelPlus):
    """
    Armazena os telefones dos setores.
    """

    setor = models.ForeignKeyPlus(Setor, on_delete=models.CASCADE)
    numero = models.BrTelefoneField('Número')
    ramal = models.CharField(max_length=5, blank=True)  # Evitar que CharField tenha null=True
    observacao = models.CharField('Observação', max_length=50, blank=True)  # Evitar que CharField tenha null=True

    class Meta:
        verbose_name = 'Telefone do Setor'
        verbose_name_plural = 'Telefones do Setor'

    def __str__(self):
        out = []
        if self.numero:
            out.append(self.numero)
        if self.ramal:
            if self.numero:
                out.append(f'(ramal: {self.ramal})')
            else:
                out.append(f'ramal: {self.ramal}')
        return ' '.join(out)


class ContatoEmergencia(models.ModelPlus):
    pessoa_fisica = models.ForeignKeyPlus(PessoaFisica, verbose_name='Servidor', on_delete=models.CASCADE)
    nome_contato = models.CharFieldPlus('Nome do Contato', max_length=200, blank=False, null=False)
    telefone = models.BrTelefoneField('Telefone', max_length=15)

    class Meta:
        verbose_name = 'Contato de Emergência'
        verbose_name_plural = 'Contatos de Emergência'

    def __str__(self):
        return f'Contato de Emergência de {self.pessoa_fisica.nome_usual} ({self.nome_contato})'


class Arquivo(models.ModelPlus):
    FS_ROOT_PATH = 'upload/'
    DIR_PKI = settings.BASE_DIR + '/djtools/security/pki/'
    PRIV_KEY = 'ksb_priv_key.pem'
    PUB_KEY = 'ksb_pub_key.pem'
    CERT = 'ksb_cert.pem'
    PASSWORD = '12345'
    nome = models.CharField(null=False, unique=False, max_length=255)
    data_geracao = models.DateTimeField()
    assinatura = models.CharField(max_length=500)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=True)

    criptografado = models.BooleanField(null=False, default=True)

    def __str__(self):
        return self.nome

    @staticmethod
    def codificar(plain_id):
        return b64encode('IFRN' + str(((plain_id * 2) + 133) * -1))

    @staticmethod
    def decodificar(masked_id):
        return ((int(b64decode(masked_id)[4:]) * -1) - 133) // 2

    def get_field_file(self, user):
        arquivo = models.FileFieldPlus(verbose_name='arquivo', blank=False)
        return models.FieldFilePlus(self, arquivo, self.get_path(user))

    def save(self, nome, vinculo, *args, **kwargs):
        ext_file = nome[nome.rfind('.') :]
        self.vinculo = vinculo
        self.criptografado = True
        self.data_geracao = datetime.now()
        self.nome = hashlib.md5(f'{vinculo.id}{nome}{self.data_geracao}'.encode()).hexdigest()
        self.nome = f'{self.nome}{ext_file}'
        super().save(*args, **kwargs)

    def store(self, user, content):
        relative_path = self.get_path(user)
        get_overwrite_storage().save(relative_path, io.BytesIO(content))

    def load(self, user):
        relative_path = self.get_path(user)
        content = download_media_content(relative_path)
        return content or ''

    @staticmethod
    def get_content_type(content):
        """Detecta o tipo MIME do conteúdo binário de um arquivo.

        Args:
            content: bytes do arquivo a ser analisado.

        Returns:
            str: tipo MIME detectado (ex.: ``'image/png'``).
        """
        import magic

        return magic.from_buffer(content[:1024], mime=True)

    def delete(self, *args, **kwargs):
        if 'contratos' in settings.INSTALLED_APPS_SUAP:
            from contratos.models import Aditivo, AnexoContrato, Contrato, Ocorrencia, PublicacaoAditivo, PublicacaoContrato

            AnexoContrato.objects.filter(arquivo__id=self.id).update(arquivo=None)
            Contrato.objects.filter(arquivo__id=self.id).update(arquivo=None)
            Aditivo.objects.filter(arquivo__id=self.id).update(arquivo=None)
            PublicacaoAditivo.objects.filter(arquivo__id=self.id).update(arquivo=None)
            PublicacaoContrato.objects.filter(arquivo__id=self.id).update(arquivo=None)
            Ocorrencia.objects.filter(arquivo__id=self.id).update(arquivo=None)

        if 'convenios' in settings.INSTALLED_APPS_SUAP:
            from convenios.models import AnexoConvenio

            AnexoConvenio.objects.filter(arquivo__id=self.id).update(arquivo=None)

        if 'projetos' in settings.INSTALLED_APPS_SUAP:
            from projetos.models import Edital, EditalAnexoAuxiliar, ProjetoAnexo

            ProjetoAnexo.objects.filter(arquivo__id=self.id).update(arquivo=None)
            Edital.objects.filter(arquivo__id=self.id).update(arquivo=None)
            EditalAnexoAuxiliar.objects.filter(arquivo__id=self.id).update(arquivo=None)

        super().delete(*args, **kwargs)

    def get_path(self, user):
        from djtools.templatetags.filters import in_group

        pode_ver = False
        path = ''
        if 'contratos' in settings.INSTALLED_APPS_SUAP:
            # pode_ver é True porque todos os documentos de contrato são públicos

            if hasattr(self, 'anexocontrato'):
                pode_ver = True
                anexo = self.anexocontrato
                extensao = os.path.splitext(anexo.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'contratos/contrato/{anexo.contrato.id:d}/anexos/{anexo.id:d}/{anexo.id:d}{extensao}')

            elif hasattr(self, 'contrato'):
                pode_ver = True
                contrato = self.contrato
                extensao = os.path.splitext(contrato.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'contratos/contrato/{contrato.id:d}/{contrato.id:d}{extensao}')

            elif hasattr(self, 'aditivo'):
                pode_ver = True
                aditivo = self.aditivo
                extensao = os.path.splitext(aditivo.arquivo.nome)[1]
                path = os.path.join(
                    Arquivo.FS_ROOT_PATH, f'contratos/contrato/{aditivo.contrato.id:d}/aditivos/{aditivo.id:d}/{aditivo.id:d}{extensao}'
                )

            elif hasattr(self, 'publicacaoaditivo'):
                pode_ver = True
                pub_aditivo = self.publicacaoaditivo
                extensao = os.path.splitext(pub_aditivo.arquivo.nome)[1]
                path = os.path.join(
                    Arquivo.FS_ROOT_PATH,
                    f'contratos/contrato/{pub_aditivo.aditivo.contrato.id:d}/aditivos/{pub_aditivo.aditivo.id:d}/publicacao/{pub_aditivo.id:d}{extensao}',
                )

            elif hasattr(self, 'publicacaocontrato'):
                pode_ver = True
                pub_contrato = self.publicacaocontrato
                extensao = os.path.splitext(pub_contrato.arquivo.nome)[1]
                return os.path.join(Arquivo.FS_ROOT_PATH, f'contratos/contrato/{pub_contrato.contrato.id:d}/publicacao/{pub_contrato.id:d}{extensao}')

            elif hasattr(self, 'ocorrencia'):
                pode_ver = True
                ocorrencia = self.ocorrencia
                extensao = os.path.splitext(ocorrencia.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'contratos/contrato/{ocorrencia.contrato.id:d}/ocorrencia/{ocorrencia.id:d}{extensao}')

            elif hasattr(self, 'medicao'):
                pode_ver = True
                medicao = self.medicao
                extensao = os.path.splitext(medicao.arquivo.nome)[1]
                path = os.path.join(
                    Arquivo.FS_ROOT_PATH, f'contratos/contrato/{medicao.parcela.cronograma.contrato.id:d}/medicao/{medicao.id:d}{extensao}'
                )

        if 'convenios' in settings.INSTALLED_APPS_SUAP:
            if hasattr(self, 'anexoconvenio'):
                pode_ver = in_group(user, ['Operador de Convênios Sistêmico', 'Operador de Convênios', 'Visualizador de Convênios'])
                anexo_convenio = self.anexoconvenio
                extensao = os.path.splitext(anexo_convenio.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'convenios/convenio/{anexo_convenio.convenio.id:d}/anexo/{anexo_convenio.id:d}{extensao}')

        if 'projetos' in settings.INSTALLED_APPS_SUAP and user.is_authenticated:
            if hasattr(self, 'projetoanexo'):
                anexo_projeto = self.projetoanexo
                extensao = os.path.splitext(anexo_projeto.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'projetos/projeto/{anexo_projeto.projeto.id:d}/anexo/{anexo_projeto.id:d}{extensao}')

                projeto = anexo_projeto.projeto
                is_pre_avaliador_sistemico_extensao = user.groups.filter(name='Pré-Avaliador Sistêmico de Projetos de Extensão').exists()
                eh_coordenador = projeto.is_responsavel(user)
                is_gerente_sistemico = projeto.is_gerente_sistemico(user)
                is_avaliador = projeto.is_avaliador(user)
                is_pre_avaliador = user.groups.filter(name='Coordenador de Extensão').exists()
                mesmo_campus = projeto.uo == get_uo(user)
                eh_visualizador = user.groups.filter(name='Visualizador de Projetos').exists()
                eh_participante = projeto.eh_participante(user)

                pode_ver = (
                    is_pre_avaliador_sistemico_extensao
                    or eh_coordenador
                    or is_gerente_sistemico
                    or is_avaliador
                    or (is_pre_avaliador and mesmo_campus)
                    or eh_participante
                    or eh_visualizador
                )

            elif hasattr(self, 'edital'):
                pode_ver = user.has_perm('projetos.pode_visualizar_projeto')
                edital = self.edital
                extensao = os.path.splitext(edital.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'projetos/edital/{edital.id:d}{extensao}')

            elif hasattr(self, 'editalanexoauxiliar'):
                pode_ver = user.has_perm('projetos.pode_visualizar_projeto')
                anexo = self.editalanexoauxiliar
                extensao = os.path.splitext(anexo.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'projetos/edital/anexos/{anexo.edital.id:d}/{anexo.id:d}{extensao}')

        if 'pesquisa' in settings.INSTALLED_APPS_SUAP and user.is_authenticated:
            if hasattr(self, 'pesquisa_anexo_arquivo'):
                from pesquisa.models import Participacao

                anexo_projeto = self.pesquisa_anexo_arquivo
                extensao = os.path.splitext(anexo_projeto.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'pesquisa/projeto/{anexo_projeto.projeto.id:d}/anexo/{anexo_projeto.id:d}{extensao}')

                projeto = anexo_projeto.projeto
                is_coordenador_pesquisa = user.groups.filter(
                    name__in=['Coordenador de Pesquisa', 'Pré-Avaliador Sistêmico de Projetos de Pesquisa', 'Diretor de Pesquisa']
                )
                vinculo = user.get_vinculo()
                is_coordenador = Participacao.objects.filter(projeto=projeto, vinculo_pessoa=vinculo, responsavel=True).exists()
                is_gerente_sistemico = user.groups.filter(name='Diretor de Pesquisa')
                is_avaliador = user.groups.filter(name='Avaliador Sistêmico de Projetos de Pesquisa')
                is_pre_avaliador = user.groups.filter(name__in=['Coordenador de Pesquisa', 'Pré-Avaliador Sistêmico de Projetos de Pesquisa'])
                mesmo_campus = projeto.uo == get_uo(user)
                eh_participante = projeto.eh_participante(user)
                eh_responsavel_anuencia = (
                    projeto.responsavel_anuencia and vinculo.eh_servidor() and vinculo.relacionamento == projeto.responsavel_anuencia
                )
                pode_ver = (
                    is_coordenador_pesquisa
                    or is_coordenador
                    or is_gerente_sistemico
                    or is_avaliador
                    or (is_pre_avaliador and mesmo_campus)
                    or eh_participante
                    or projeto.vinculo_supervisor == vinculo
                    or eh_responsavel_anuencia
                )

            elif hasattr(self, 'pesquisa_edital_arquivo'):
                pode_ver = user.has_perm('pesquisa.pode_visualizar_projeto')
                edital = self.pesquisa_edital_arquivo
                extensao = os.path.splitext(edital.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'pesquisa/edital/{edital.id}/{edital.id}{extensao}')

            elif hasattr(self, 'pesquisa_edital_anexoauxiliar'):
                pode_ver = user.has_perm('pesquisa.pode_visualizar_projeto')
                anexo = self.pesquisa_edital_anexoauxiliar
                extensao = os.path.splitext(anexo.arquivo.nome)[1]
                path = os.path.join(Arquivo.FS_ROOT_PATH, f'pesquisa/edital/{anexo.edital.id:d}/anexo/{anexo.id:d}{extensao}')
        #
        if not pode_ver and not user.groups.filter(name='Auditor').exists():
            raise PermissionDenied

        return path


class Notificacao(models.ModelPlus):
    modulo = models.CharField(null=False, max_length=25)
    descricao = models.CharField(null=False, max_length=100)
    titulo = models.CharField(null=False, max_length=100)
    mensagem = models.TextField(null=False, max_length=1024)

    def __str__(self):
        return self.descricao


class Notificador:
    def notificar(self, notificacao_id, email_remetente, email_destinatario, titulo_dict, mensagem_dict):
        if settings.DEBUG:
            return 0
        from django.template import Context, Template

        notificacao = Notificacao.objects.get(pk=notificacao_id)

        titulo = Template(notificacao.titulo).render(Context(titulo_dict))
        mensagem = Template(notificacao.mensagem).render(Context(mensagem_dict))

        msg = EmailMultiAlternatives(titulo, mensagem, settings.DEFAULT_FROM_EMAIL, [email_destinatario])
        msg.attach_alternative(mensagem, 'text/html')

        # servidor tem e-mail?
        if email_destinatario:
            return msg.send()
        else:
            return 0


class Log(models.ModelPlus):
    app = models.CharField('Aplicação', max_length=50, null=False)
    horario = models.DateTimeField(auto_now_add=True, verbose_name='Horário')
    titulo = models.CharFieldPlus(verbose_name='Título')
    texto = models.TextField(null=True)


class EstadoCivil(ModelPlus):
    codigo_siape = models.CharField(max_length=1, blank=True)
    nome_siape = models.CharField(max_length=25)
    nome = models.CharField(max_length=25)
    ativo = models.BooleanField(default=True)

    class Meta:
        verbose_name = 'Estado Civil'
        verbose_name_plural = 'Estados Civis'

    def __str__(self):
        return self.nome


class Raca(models.ModelPlus):
    CODIGO_CENSUP_INDIGENA = '5'
    ID_RACA_INDIGENA = 4

    SEARCH_FIELDS = ['descricao']
    descricao = models.CharFieldPlus('Descrição', unique=True)
    codigo_siape = models.IntegerField('Código SIAPE', default=0)
    inativo_siape = models.BooleanField('Inativo no SIAPE', default=False)
    codigo_censup = models.CharField('Código Censup', default='', blank=True, max_length=10)

    class Meta:
        verbose_name = 'Raça'
        verbose_name_plural = 'Raças'

    def __str__(self):
        return self.descricao

    def is_indigena(self):
        return self.codigo_censup == Raca.CODIGO_CENSUP_INDIGENA


class PovoIndigena(models.ModelPlus):
    SEARCH_FIELDS = [
        'nome',
    ]
    nome = models.CharFieldPlus('Nome', unique=True)
    codigo_educacenso = models.CharField('Código EDUCACENSO')

    class Meta:
        verbose_name = 'nome'
        verbose_name_plural = 'Povos Indígenas'

    def __str__(self):
        return self.nome


class TrocarSenha(models.ModelPlus):
    """
    Guarda o token para mudança de senha e é utilizado no suapexterno.
    """

    username = models.CharFieldPlus()
    email = models.EmailField()
    token = models.CharField(max_length=128)
    validade = models.DateTimeField()

    def save(self, *args, **kwargs):
        """
        Define os atributos ``email``, ``token`` e ``validade``.
        """

        user = User.objects.get(username=self.username)
        vinculo = user.get_vinculo()
        # Recuperação de senha usa SÓ o e-mail pessoal — nunca o institucional (mesma senha do SUAP).
        email_pessoal = vinculo.email_pessoal if vinculo else ''
        if not email_pessoal:
            raise ValueError('Pessoa sem email alternativo')

        # Definindo email
        self.email = email_pessoal

        # Definindo validade
        agora = datetime.now()
        self.validade = agora + timedelta(1)  # válido por 24 horas

        # Definindo token
        frase = f'{agora!s}{self.username}{settings.SECRET_KEY}'.encode()
        self.token = hashlib.sha512(frase).hexdigest()

        super().save(*args, **kwargs)

    @classmethod
    def token_valido(cls, username, token):
        agora = datetime.now()
        return cls.objects.filter(username=username, token=token, validade__gte=agora).exists()

    @classmethod
    def expirar_token(cls, username, token):
        agora = datetime.now()
        cls.objects.filter(username=username, token=token, validade__gte=agora).update(validade=agora - timedelta(seconds=1))

    def enviar_email(self, base_url=''):
        url = f'{settings.SITE_URL}/comum/trocar_senha/{self.username}/{self.token}/'
        conteudo = f"""<h1>Solicitação de Mudança de Senha</h1>
        <p>Prezado usuário,</p>
        <p>Para realizar a mudança de senha referente às suas credenciais da rede, por favor, acesse o endereço abaixo:</p>
        <p><a href="{url}">{url}</a></p>"""
        return send_mail('[SUAP] Solicitação de Mudança de Senha', conteudo, settings.DEFAULT_FROM_EMAIL, [self.email])


class GerenciamentoGrupo(models.ModelPlus):
    grupo_gerenciador = models.ForeignKeyPlus(Group, related_name='grupo_gerenciador_set', on_delete=models.CASCADE)
    grupos_gerenciados = models.ManyToManyField(Group, related_name='grupos_gerenciados_set')
    eh_local = models.BooleanField('É Local?', default=False)

    NOME_GRUPO_GERENCIADOR_FORMAT = '{} Administrador'
    NOME_GRUPO_CONFIGURADOR_FORMAT = '{} Configurador'

    class Meta:
        verbose_name = 'Gerenciamento de Grupo'
        verbose_name_plural = 'Gerenciamento de Grupos'

    def __str__(self):
        return f'{self.grupo_gerenciador.name}'

    @classmethod
    def user_can_manage(cls, user):
        return user.is_superuser or cls.objects.filter(grupo_gerenciador__in=user.groups.all()).exists()

    def get_grupos_gerenciados(self):
        grupos = []
        for grupo in self.grupos_gerenciados.all():
            grupo.eh_local = self.eh_local
            grupos.append(grupo)
        return grupos

    @staticmethod
    def get_grupos_gerenciados_por(group):
        result = []
        qs = GerenciamentoGrupo.objects.filter(grupo_gerenciador=group)
        if qs.exists():
            for gerenciamento_grupo in qs:
                result.extend(gerenciamento_grupo.get_grupos_gerenciados())
        return result

    @staticmethod
    def get_grupos_que_gerenciam(group):
        result = []
        qs = GerenciamentoGrupo.objects.filter(grupos_gerenciados=group)
        if qs.exists():
            for gerenciamento_grupo in qs:
                result.append(gerenciamento_grupo.grupo_gerenciador)
        return result


class UsuarioGrupo(models.ModelPlus):
    user = models.ForeignKeyPlus(User, on_delete=models.CASCADE)
    group = models.ForeignKeyPlus(Group, on_delete=models.CASCADE)
    setores = models.ManyToManyFieldPlus('rh.Setor', through='comum.UsuarioGrupoSetor')

    class Meta:
        verbose_name = 'Vínculo de Usuário em Grupo'
        verbose_name_plural = 'Vínculos de Usuário em Grupo'
        db_table = 'auth_user_groups'
        managed = False

    def __str__(self):
        return f'Vínculo do usuário {self.user} no grupo {self.group}'


class ConfiguracaoAutomatizacaoGrupo(models.ModelPlus):
    grupo = models.ForeignKeyPlus(Group, on_delete=models.CASCADE)
    setores = models.ManyToManyFieldPlus('rh.Setor', verbose_name='Setores')
    cargo_emprego = models.ForeignKeyPlus('rh.CargoEmprego', verbose_name='Cargo', on_delete=models.CASCADE, null=True)
    ativa = models.BooleanField('Ativa', default=True)
    criado_por = models.ForeignKeyPlus(User, on_delete=models.CASCADE, related_name='configuracao_automatizacao_grupo_criado_por_set')
    criado_em = models.DateTimeFieldPlus('Data de criação', auto_now_add=True)
    atualizado_por = models.ForeignKeyPlus(
        User, on_delete=models.CASCADE, null=True, related_name='configuracao_automatizacao_grupo_atualizado_por_set'
    )
    atualizado_em = models.DateTimeFieldPlus('Data de atualização', auto_now=True)

    class Meta:
        verbose_name = 'Configuração de automatização de grupos'
        verbose_name_plural = 'Configuração de automatização de grupos'

    @property
    def criado_atualizado_por(self):
        return self.atualizado_por or self.criado_por

    @atomic
    def adicionar_usuario(self, usuario, motivo):
        HistoricoUsuarioGrupo.objects.create(
            usuario=usuario,
            grupo=self.grupo,
            operacao=HistoricoUsuarioGrupo.INCLUSAO,
            motivo=motivo,
        )
        usuario.groups.add(self.grupo)

    @atomic
    def remover_usuario(usuario, grupo, motivo):
        historicos = HistoricoUsuarioGrupo.objects.filter(
            usuario=usuario, grupo=grupo, operacao=HistoricoUsuarioGrupo.INCLUSAO, removido_em__isnull=True
        )
        historico = None
        for historico in historicos:
            historico.remover_grupo(motivo)

        if not historico:
            usuario.groups.remove(grupo)

    def get_servidores_configuracao(self) -> QuerySet:
        return self.servidores_elegiveis(self.setores, self.cargo_emprego, self.ativa)

    @classmethod
    def servidores_elegiveis(cls, setores: QuerySet, cargo_emprego: object | None, ativa: bool) -> QuerySet:
        servidores = Servidor.objects.none()
        if ativa:
            servidores = Servidor.objects.ativos().exclude(situacao__codigo__in=Situacao.situacoes_siape_estagiarios())
            if cargo_emprego:
                servidores = servidores.filter(cargo_emprego=cargo_emprego)
            if setores.exists():
                servidores = servidores.filter(setor__in=setores.all())
        return servidores

    def get_servidores_elegiveis(self):
        """Retorna QuerySet com servidores elegíveis para esta configuração"""
        return ConfiguracaoAutomatizacaoGrupo.servidores_elegiveis(self.setores, self.cargo_emprego, self.ativa)

    @classmethod
    def analise_impacto(cls, grupo, setores, cargo_emprego, ativa=True, instance=None):
        """
        Retorna dicionário com análise de impacto da configuração
        Args:
            grupo: Grupo que será analisado
            setores: QuerySet com setores selecionados
            cargo_emprego: CargoEmprego selecionado
            ativa: Status da configuração
            instance: Instância atual em caso de edição
        """
        hoje = datetime.now()

        # Servidores que serão incluídos pela nova configuração
        servidores_incluidos = cls.servidores_elegiveis(setores, cargo_emprego, ativa)
        # Convertemos as matrículas em uma lista antes de fazer o filtro
        matriculas = list(servidores_incluidos.values_list('matricula', flat=True))
        users_incluidos = User.objects.filter(username__in=matriculas)
        # Servidores que já estão no grupo
        users_atuais = grupo.user_set.all()

        # Servidores que permanecerão por outras configurações ativas
        outras_configuracoes = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo, ativa=True)
        if instance:
            outras_configuracoes = outras_configuracoes.exclude(id=instance.id)

        users_outras_config = {}
        for config in outras_configuracoes:
            servidores = config.get_servidores_elegiveis()
            matriculas_servidores = list(servidores.values_list('matricula', flat=True))
            users_outras_confs = User.objects.filter(username__in=matriculas_servidores)
            for user in users_outras_confs:
                users_outras_config[user.id] = config

        # Users com prazo definido
        users_prazo = {}
        historicos_prazo = HistoricoUsuarioGrupo.objects.filter(
            grupo=grupo, removido_em__isnull=True, prazo__isnull=False, prazo__gt=hoje
        ).select_related('usuario')

        for historico in historicos_prazo:
            users_prazo[historico.usuario.id] = historico.prazo

        # Monta análise de impacto
        permanecerao = []
        serao_removidos = []
        serao_adicionados = []

        # Analisa cada user atual
        for user in users_atuais:
            if user.id in users_outras_config:
                config = users_outras_config[user.id]
                permanecerao.append({'user': user, 'motivo': f'Pertence à configuração: {config.id} - {config.setores.all().first()}'})
            elif user.id in users_prazo:
                prazo = users_prazo[user.id]
                permanecerao.append({'user': user, 'motivo': f'Prazo definido até {prazo.strftime("%d/%m/%Y")}'})
            else:
                serao_removidos.append(user)

        # Analisa novos servidores
        for user_incluido in users_incluidos:
            if user_incluido not in users_atuais:
                serao_adicionados.append(user_incluido)
            else:
                try:
                    serao_removidos.remove(user_incluido)
                except ValueError:
                    pass
                permanecerao.append({'user': user_incluido, 'motivo': 'Já está no grupo'})

        return {'permanecerao': permanecerao, 'serao_removidos': serao_removidos, 'serao_adicionados': serao_adicionados}

    def get_analise_impacto(self, setores, cargo_emprego=None, ativa=None):
        """Análise de impacto para configuração existente"""
        return self.analise_impacto(self.grupo, setores, cargo_emprego, ativa if ativa is not None else self.ativa, instance=self)


class HistoricoUsuarioGrupo(models.ModelPlus):
    INCLUSAO = 'I'
    REMOCAO = 'R'
    OPERACAO_CHOICES = ((INCLUSAO, 'Inclusão'), (REMOCAO, 'Remoção'))
    usuario = models.ForeignKeyPlus(User, on_delete=models.CASCADE)
    grupo = models.ForeignKeyPlus(Group, on_delete=models.CASCADE)
    motivo = models.CharFieldPlus('Motivo', max_length=550, help_text='Informe o motivo desta operação.')
    operacao = models.CharFieldPlus('Operação', max_length=1, choices=OPERACAO_CHOICES)
    incluido_por = models.ForeignKeyPlus(User, on_delete=models.CASCADE, null=True, related_name='incluido_por_set')
    incluido_em = models.DateTimeFieldPlus('Data de inclusão no grupo', auto_now_add=True)
    removido_em = models.DateTimeFieldPlus('Data de remoção no grupo para este registro', null=True)
    prazo = models.DateFieldPlus('Prazo', null=True, help_text='O usuário será automaticamente removido do grupo ao fim do prazo informado.')

    class Meta:
        verbose_name = 'Histórico de usuário em grupo'
        verbose_name_plural = 'Históricos de usuários em grupos'

    @property
    def is_operacao_automatica(self):
        return self.incluido_por is None

    @atomic
    def remover_grupo(self, motivo):
        self.removido_em = datetime.now()
        self.save()

        HistoricoUsuarioGrupo.objects.create(usuario=self.usuario, grupo=self.grupo, operacao=self.REMOCAO, motivo=motivo)

        self.usuario.groups.remove(self.grupo)

    @classmethod
    @atomic
    def remover_grupos_automaticos_estagiario(cls, user: User) -> None:
        """Desfaz apenas concessões automáticas, preservando inclusões manuais do estagiário."""
        automaticos = cls.objects.filter(
            usuario=user,
            operacao=cls.INCLUSAO,
            incluido_por__isnull=True,
            removido_em__isnull=True,
        )
        motivo = 'Removido durante a sincronização porque regras de automatização não se aplicam a estagiários'
        for grupo_id in automaticos.values_list('grupo_id', flat=True).distinct():
            inclusao_manual_ativa = cls.objects.filter(
                usuario=user,
                grupo_id=grupo_id,
                operacao=cls.INCLUSAO,
                incluido_por__isnull=False,
                removido_em__isnull=True,
            ).exists()
            automaticos.filter(grupo_id=grupo_id).update(removido_em=datetime.now())
            if not inclusao_manual_ativa:
                cls.objects.create(usuario=user, grupo_id=grupo_id, operacao=cls.REMOCAO, motivo=motivo)
                user.groups.remove(grupo_id)

    @classmethod
    def atualizar_grupos_usuario(cls, user: User) -> None:
        """
        Atualiza os grupos do usuário baseado em:
        1. Remove usuários:
            1.1. Com prazo expirado
            1.2. Que não fazem mais parte de configurações ativas
            1.3. Com cargo/setor não compatível com configuração
        2. Adiciona usuários em grupos que atendem aos critérios
        """
        hoje = datetime.now()
        relacionamento = user.get_relacionamento()
        if user.eh_servidor:
            # Para cada grupo que o usuário está
            grupos_a_remover = []
            grupos_que_tem_configuracao_automatica = ConfiguracaoAutomatizacaoGrupo.objects.filter(ativa=True).values_list('grupo', flat=True)
            # Verifica se o usuário tem configuração automática expirada e remove do grupo caso exista
            historicos_expirados = HistoricoUsuarioGrupo.objects.filter(
                usuario=user, operacao=HistoricoUsuarioGrupo.INCLUSAO, removido_em__isnull=True, prazo__lt=hoje.date()
            )

            for historico_expirado in historicos_expirados:
                motivo_remocao = 'Removido, após logar no sistema, devido ao prazo ter expirado'
                historico_expirado.remover_grupo(motivo_remocao)

            if relacionamento.eh_estagiario:
                cls.remover_grupos_automaticos_estagiario(user)
                return

            for grupo in user.groups.filter(pk__in=grupos_que_tem_configuracao_automatica):
                motivo_remocao = None

                historicos_ativos = HistoricoUsuarioGrupo.objects.filter(
                    usuario=user, grupo=grupo, operacao=HistoricoUsuarioGrupo.INCLUSAO, removido_em__isnull=True
                )

                # Verifica configurações ativas do grupo
                configs_do_grupo = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo, ativa=True)
                configuracao_grupo_para_usuario = configs_do_grupo.filter(setores=relacionamento.setor).filter(
                    Q(cargo_emprego=relacionamento.cargo_emprego) | Q(cargo_emprego__isnull=True)
                )
                if not configuracao_grupo_para_usuario.exists() and not historicos_ativos.filter(prazo__gte=hoje).exists():
                    # Se não tem configuração ativa, verifica se tem prazo válido
                    motivo_remocao = 'Removido, após logar no sistema, por não fazer parte de nenhuma configuração ativa'
                    for historico_automatico in historicos_ativos.filter(prazo__isnull=True):
                        historico_automatico.remover_grupo(motivo_remocao)

                # Remove do grupo se necessário
                if motivo_remocao:
                    grupos_a_remover.append((grupo, motivo_remocao))
            # Adiciona em grupos onde atende os critérios
            if relacionamento and relacionamento.setor:
                for grupo, motivo in grupos_a_remover:
                    ConfiguracaoAutomatizacaoGrupo.remover_usuario(user, grupo, motivo)

                grupos_automatizados = ConfiguracaoAutomatizacaoGrupo.objects.filter(ativa=True, setores=relacionamento.setor).exclude(
                    grupo__in=user.groups.all()
                )

                for config in grupos_automatizados:
                    if not config.cargo_emprego or config.cargo_emprego == relacionamento.cargo_emprego:
                        config.adicionar_usuario(
                            usuario=user,
                            motivo=f'Adicionado, após logar no sistema, via regra de automatização do grupo/setor definida por {config.criado_atualizado_por}',
                        )


models.signals.post_delete.connect(registrar_remocao_grupo, sender=UsuarioGrupo, dispatch_uid='comum.registrar_remocao_grupo')
models.signals.post_save.connect(registrar_adicao_grupo, sender=UsuarioGrupo, dispatch_uid='comum.registrar_adicao_grupo')


class UsuarioGrupoSetor(models.ModelPlus):
    usuario_grupo = models.ForeignKeyPlus(UsuarioGrupo, on_delete=models.CASCADE, db_column='usuariogrupo_id')
    setor = models.ForeignKeyPlus('rh.Setor', on_delete=models.CASCADE)

    class Meta:
        verbose_name = 'Vínculo de Usuário em Setor'
        verbose_name_plural = 'Vínculos de Usuário em Setor'
        db_table = 'comum_usuariogrupo_setores'

    def __str__(self):
        return f'Vínculo do usuário no setor {self.setor}'

    def delete(self, *args, **kwargs):
        group_id = self.usuario_grupo.group.id
        user_id = self.usuario_grupo.user.id
        self.pre_delete()
        super().delete(*args, **kwargs)
        if not UsuarioGrupoSetor.objects.filter(usuario_grupo__group_id=group_id, usuario_grupo__user_id=user_id).exists():
            UsuarioGrupo.objects.get(group_id=group_id, user_id=user_id).delete()

    def pre_delete(self):
        if self.usuario_grupo.group.name in ('Secretário Acadêmico', 'Auxiliar de Secretaria Acadêmica'):
            if 'centralservicos' in settings.INSTALLED_APPS:
                from centralservicos.models import GrupoAtendimento

                pk = self.setor.diretoria_set.values_list('id_grupo_atendimento', flat=True).first()
                ga = GrupoAtendimento.objects.filter(id=pk).first() if pk else None
                if ga:
                    ga.atendentes.remove(self.usuario_grupo.user)
                    ga.responsaveis.remove(self.usuario_grupo.user)


class Comentario(models.ModelPlus):
    """
    Modelo que representa os comentários realizados para uma demanda.
    """

    cadastrado_por = models.CurrentUserField()
    cadastrado_em = models.DateTimeFieldPlus(auto_now=True)
    resposta = models.ForeignKeyPlus('Comentario', null=True, blank=True, on_delete=models.CASCADE)
    texto = models.TextField()
    desconsiderado = models.BooleanField(default=False)

    # Fk Genérica para uso por qualquer modelo
    content_type = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveIntegerField()
    content_object = GenericForeignKey('content_type', 'object_id')

    class Meta:
        verbose_name = 'Comentário'
        verbose_name_plural = 'Comentários'
        ordering = ('id',)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if hasattr(self.content_object, 'comentario_post_save'):
            self.content_object.comentario_post_save(self)

    def __str__(self):
        return f'{self.cadastrado_por} - {self.texto}'


class RegistroEmissaoDocumento(models.ModelPlus):
    PUBLIC_SEARCH = True

    tipo = models.CharFieldPlus(verbose_name='Tipo de Documento')
    data_emissao = models.DateFieldPlus(verbose_name='Data de Emissão')
    codigo_verificador = models.TextField(verbose_name='Código Verificador')
    documento = models.FileFieldPlus(upload_to='documentos', verbose_name='Documento', filetypes=('pdf',))
    data_validade = models.DateFieldPlus(null=True, blank=True, verbose_name='Validade')

    modelo_pk = models.IntegerField('Id da Referência', null=True)
    tipo_objeto = models.ForeignKeyPlus(ContentType, on_delete=models.CASCADE, null=True, verbose_name='Referência')
    objeto = GenericForeignKey('tipo_objeto', 'modelo_pk')
    cancelado = models.BooleanField(verbose_name='Cancelado', default=False)

    chave_extra = models.CharFieldPlus(verbose_name='Chave Extra', null=True, blank=True)

    class Meta:
        verbose_name = 'Registro de Emissão de Documento'
        verbose_name_plural = 'Registros de Emissão de Documento'

    def as_pdf_response(self):
        return HttpResponse(self.documento.read(), content_type='application/pdf')

    def __str__(self):
        return self.tipo

    def get_url_download_documento(self):
        return f'/comum/baixar_documento/{self.pk}/{self.codigo_verificador}/'

    def get_links_documentos(self):
        links = []
        links.append({'image': '/static/comum/img/pdf.png', 'url': self.get_url_download_documento(), 'label': 'Documento', 'width': 150})
        if self.tipo == 'Diploma/Certificado' and self.assinaturas_diploma.exists():
            links[0]['label'] = 'Registro'
            assinatura_eletronica = self.assinaturas_diploma.first()
            url = f'/edu/baixar_pdf_diploma_eletronico/{assinatura_eletronica.pk}/{assinatura_eletronica.get_token_download()}/'
            links.append({'image': '/static/edu/img/diploma_digital.png', 'url': url, 'label': 'Diploma', 'width': 280})
        return links

    def delete(self, *args, **kwargs):
        super().delete(*args, **kwargs)
        default_storage.delete(self.documento.name)

    @staticmethod
    def qrcode(url):
        """Gera imagem QR code em base64 para uma URL.

        Args:
            url: URL a ser codificada no QR code.

        Returns:
            str: imagem PNG do QR code codificada em base64.
        """
        import qrcode

        img = qrcode.make(url)
        buffer_img = io.BytesIO()
        img.save(buffer_img, 'png')
        return base64.encodebytes(buffer_img.getvalue()).decode()

    @staticmethod
    def url_autenticacao(tipo, data_emissao, codigo_verificador, completa=False):
        url = settings.SITE_URL + '/comum/autenticar_documento/'
        if completa:
            params = urllib.parse.urlencode(
                {'tipo': tipo, 'data_emissao': data_emissao.strftime('%d/%m/%Y'), 'codigo_verificador': codigo_verificador[0:6]}
            )
            return f'{url}?{params}'
        return url


class TipoCarteiraFuncional(models.ModelPlus):
    MODELO_2015 = '2015'
    MODELO_2016 = '2016'
    MODELOS_CHOICES = ((MODELO_2015, 'Modelo 2015'), (MODELO_2016, 'Modelo 2016'))

    nome = models.CharFieldPlus('Nome')
    template = models.CharFieldPlus('Template', choices=MODELOS_CHOICES)
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True)
    modelo = models.FileFieldPlus(upload_to='comum/carteira_funcional/', null=True, blank=True, verbose_name='Modelo')
    ativo = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'Tipo de Carteira Funcional'
        verbose_name_plural = 'Tipos de Carteira Funcional'

    def save(self, *args, **kwargs):
        if self.ativo:
            TipoCarteiraFuncional.objects.all().update(ativo=False)
        super().save(*args, **kwargs)

    def __str__(self):
        return self.nome


class IndexLayout(ModelPlus):
    usuario = models.CurrentUserField()
    quadro_nome = models.CharFieldPlus('Nome do Quadro')
    quadro_coluna = models.PositiveIntegerField('Coluna no Leiaute', default=1)
    quadro_ordem = models.PositiveIntegerField('Ordem de Apresentação')
    escondido = models.BooleanField(default=False)
    hash_quadros = models.CharFieldPlus('Código hash dos quadros', blank=True, null=True)

    class History:
        disabled = True

    class Meta:
        indexes = [
            models.Index(fields=['usuario_id', 'quadro_nome']),
        ]

    @classmethod
    def get_layouts_usuario(cls, request):
        if request.session.get('index_layout'):
            return request.session.get('index_layout')
        else:
            layouts = cls.objects.filter(usuario=request.user).order_by('quadro_coluna', 'quadro_ordem')
            result = collections.OrderedDict()
            for layout in layouts.values():
                result[layout['quadro_nome']] = {
                    'coluna': layout['quadro_coluna'],
                    'ordem': layout['quadro_ordem'],
                    'escondido': layout['escondido'],
                    'hash_quadros': layout['hash_quadros'],
                }
            request.session['index_layout'] = result
            return result

    @staticmethod
    def recarregar_layouts(request) -> None:
        """Invalida o layout do index guardado na sessão e o cache dos quadros do usuário."""
        try:
            del request.session['index_layout']
        except KeyError:
            pass
        limpar_cache_dos_quadros(request.user.username)


class ManutencaoProgramada(ModelPlus):
    FUNCIONALIDADE = 'Funcionalidade'
    MANUTENCAO = 'Manutenção'
    BUG = 'Bug'
    TIPO_CHOICES = ((FUNCIONALIDADE, 'Adição de Funcionalidades'), (MANUTENCAO, 'Manutenção Preventiva'), (BUG, 'Correção de Bugs'))
    usuario = models.CurrentUserField(verbose_name='Última Alteração por')
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True)
    tipo = models.CharFieldPlus(choices=TIPO_CHOICES)
    sistema_ou_servico = models.CharFieldPlus(default='SUAP', blank=False, help_text='Sistema ou serviço em que vai ser feita a manutenção')
    data_hora_atualizacao = models.DateTimeFieldPlus('Data da atualização')
    previsao_minutos_inatividade = models.PositiveIntegerFieldPlus('Previsão de minutos de inatividade')
    efetivos_minutos_inatividade = models.PositiveIntegerFieldPlus('Efetivos minutos de inatividade', null=True, blank=True)
    data_hora_inicio_notificacao = models.DateTimeFieldPlus('Data de início notificação')
    equipe_manutencao = models.ManyToManyFieldPlus('comum.Vinculo', verbose_name='Equipe de manutenção')
    motivo = models.TextField()

    publico = models.ForeignKeyPlus(
        Publico,
        verbose_name='Público',
        blank=True,
        null=True,
        related_name='publico_manutencao_programada',
        on_delete=models.CASCADE,
        help_text='Escolha um publico caso você queira que a manutenção seja avisada apenas para o público específico.',
    )
    campi = models.ManyToManyFieldPlus(
        'rh.UnidadeOrganizacional',
        blank=True,
        related_name='campi_publico_manutencao_programada',
        verbose_name='Unidade Organizacional',
        help_text='Escolha um campus caso você queira que a manutenção seja avisada apenas para o público específico.',
    )
    vinculos_publico = models.ManyToManyFieldPlus(
        'comum.Vinculo', related_name='vinculos_publico_manutencao_programada', verbose_name='Vínculos Público', blank=True
    )

    class Meta:
        verbose_name = 'Manutenção Programada'
        verbose_name_plural = 'Manutenções Programadas'

    def __str__(self):
        return f'{self.get_tipo_display()} às {self.data_hora_atualizacao.date()}'

    def get_absolute_url(self):
        return f'/admin/comum/manutencaoprogramada/{self.id}/view/'

    @classmethod
    def proximas_atualizacoes(cls, user=None):
        agora = datetime.now()
        proximas_atualizacoes = cls.objects.filter(data_hora_atualizacao__gte=agora).order_by('data_hora_atualizacao')
        if user:
            proximas_atualizacoes = proximas_atualizacoes.filter(Q(vinculos_publico=user.get_vinculo()) | Q(vinculos_publico__isnull=True))
        return proximas_atualizacoes

    @classmethod
    def proximas_notificacoes(cls, user=None):
        agora = datetime.now()
        return cls.proximas_atualizacoes(user).filter(data_hora_inicio_notificacao__lte=agora).order_by('data_hora_atualizacao')

    @classmethod
    def proxima_notificacao(cls):
        return cls.proximas_notificacoes().first()

    def clean(self):
        if not (self.data_hora_atualizacao and self.data_hora_inicio_notificacao) or self.data_hora_atualizacao < self.data_hora_inicio_notificacao:
            raise ValidationError('O horário de atualização deve ser maior que o horário de notificação.')

    def get_mensagem(self):
        hoje = datetime.now()
        if self.data_hora_atualizacao.date() == hoje.date():
            data_manutencao = 'hoje'
        else:
            data_manutencao = 'no dia {}'.format(self.data_hora_atualizacao.strftime('%d/%m/%Y'))
        previsao_horario_fim_manutencao = self.data_hora_atualizacao + timedelta(minutes=self.previsao_minutos_inatividade)
        if previsao_horario_fim_manutencao.date() == hoje.date():
            data_fim_manutencao = 'de hoje'
        else:
            data_fim_manutencao = 'do dia {}'.format(previsao_horario_fim_manutencao.date().strftime('%d/%m/%Y'))

        return f"""<a href="{self.get_absolute_url()}" title="Visualizar detalhes manutenção"><span class="fas fa-eye"></span></a>
            <b>Atenção:</b> Um procedimento de {self.get_tipo_display().lower()} será realizado no(a) {self.sistema_ou_servico} <b>{data_manutencao}</b> das
            <b>{self.data_hora_atualizacao.strftime('%H:%M:%S')}</b> até aproximadamente às <b>{previsao_horario_fim_manutencao.strftime('%H:%M:%S')} {data_fim_manutencao}</b>.
            Por favor, programe suas atividades com antecedência e evite o acesso durante este horário.
            <a class ='esconder_notificacao_importante' href="?esconder_manutencao={self.id}" title="Esconder esta mensagem">
                <span class="sr-only">Esconder</span>
            </a>
        """

    def get_publicos(self):
        qs_vinculos = Vinculo.objects.none()
        tem_filtro_campus = self.campi.exists()
        publico = self.publico
        if publico or tem_filtro_campus:
            qs_vinculos = publico.get_queryset_vinculo()
            if tem_filtro_campus:
                qs_vinculos = qs_vinculos.filter(setor__uo__in=self.campi.all())
        return qs_vinculos.distinct()

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.vinculos_publico.clear()
        vinculos = self.get_publicos()
        VinculoPublico = self.vinculos_publico.through
        vinculo_publico_relations = [VinculoPublico(manutencaoprogramada_id=self.id, vinculo_id=v.id) for v in vinculos]
        with atomic():
            VinculoPublico.objects.bulk_create(vinculo_publico_relations)


class Preferencia(ModelPlus):
    PADRAO = 'padrao'
    DUNAS = 'dunas'
    AURORA = 'aurora'
    LUNA = 'luna'
    GOVBR = 'govbr'
    ALTO_CONSTRASTE = 'alto-contraste'
    IFS = 'ifs'
    MODO_DALTONISMO = 'modo-daltonismo'

    ANONIMA_PADRAO = 'anonima'
    ANONIMA_GOVBR = 'anonima-govbr'

    TEMA_CHOICES = (
        (PADRAO, 'Padrão'),
        (DUNAS, 'Dunas'),
        (AURORA, 'Aurora'),
        (LUNA, 'Luna'),
        (GOVBR, 'Gov.br'),
        (ALTO_CONSTRASTE, 'Alto Contraste'),
        (IFS, 'IFs'),
        (MODO_DALTONISMO, 'Modo Daltonismo'),
    )

    TEMA_TELAS_ANONIMAS_CHOICES = (
        (ANONIMA_PADRAO, 'Padrão'),
        (ANONIMA_GOVBR, 'Gov.br'),
    )

    usuario = models.OneToOneFieldPlus(User, on_delete=models.CASCADE, verbose_name='Usuário')
    tema = models.CharFieldPlus('Opção de Tema', choices=TEMA_CHOICES, default=PADRAO)
    via_suap = models.BooleanField('Notificação Via SUAP', default=True)
    via_email = models.BooleanField('Notificação Via E-mail', default=True)
    data_cadastro = models.DateTimeFieldPlus(auto_now_add=True)

    class Meta:
        verbose_name = 'Preferência do Usuário'
        verbose_name_plural = 'Preferências do Usuário'

    def __str__(self):
        return f'Preferências de: {self.usuario}'

    @classmethod
    def get_tema_padrao_usuario_autenticado(cls):
        try:
            return Configuracao.get_valor_por_chave('comum', 'tema_padrao_usuario_autenticado') or cls.PADRAO
        except Exception:
            return cls.PADRAO

    @classmethod
    def get_tema_padrao_usuario_anonimo(cls):
        try:
            return Configuracao.get_valor_por_chave('comum', 'tema_telas_anonimas') or cls.ANONIMA_PADRAO
        except Exception:
            return cls.ANONIMA_PADRAO

    @classmethod
    def get_tema_description(cls, tema):
        return dict(cls.TEMA_CHOICES).get(tema, 'Padrão')


class FuncaoCodigo(ModelPlus):
    nome = models.CharField(verbose_name='Cargo/Função', max_length=7, null=False)

    def __str__(self):
        return f'{self.nome}'

    class Meta:
        verbose_name = 'Código de Função'
        verbose_name_plural = 'Códigos de Funções'


class CategoriaNotificacao(ModelPlus):
    assunto = models.CharFieldPlus(verbose_name='Assunto')
    ativa = models.BooleanField(verbose_name='Ativa?', default=True)
    forcar_habilitacao = models.BooleanField(
        verbose_name='Forçar Habilitação',
        help_text='Se marcar o usuário não poderá desabilitar as preferências de notificação associadas a esta categoria.',
        default=False,
    )

    class Meta:
        verbose_name = 'Categoria de Notificação'
        verbose_name_plural = 'Categorias de Notificações'

    def __str__(self):
        return self.assunto


class NotificacaoSistema(ModelPlus):
    categoria = models.ForeignKeyPlus('comum.CategoriaNotificacao', null=False, blank=False)
    mensagem = models.TextField(verbose_name='Mensagem')
    objeto_relacionado = models.CharFieldPlus('Objeto Relacionado', null=True, db_index=True)
    data_envio = models.DateTimeField(auto_now_add=True, verbose_name='Data de Envio')

    class Meta:
        verbose_name = 'Mensagem da Notificação'
        verbose_name_plural = 'Mensagens das Notificações'

    class History:
        disabled = True

    def __str__(self):
        return str(self.categoria)


class RegistroNotificacao(ModelPlus):
    notificacao = models.ForeignKeyPlus('comum.NotificacaoSistema', null=False, blank=False, verbose_name='Notificação')
    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=False, blank=False, verbose_name='Vínculo')
    lida = models.BooleanField(verbose_name='Lida?', default=False)
    data = models.DateTimeField(auto_now_add=True)
    data_permite_marcar_lida = models.DateTimeFieldPlus(auto_now_add=True)
    data_permite_excluir = models.DateTimeFieldPlus(auto_now_add=True)

    class History:
        disabled = True

    class Meta:
        verbose_name = 'Notificação'
        verbose_name_plural = 'Notificações'
        ordering = ('-data',)

    EXT_COMBO_RELATED = {
        'select_related': ['notificacao', 'notificacao__categoria', 'vinculo'],
        'prefetch_related': [],
    }

    def __str__(self):
        return self.get_assunto

    def save(self, *args, **kwargs):
        self.limpar_cache(self.vinculo.user)
        super().save(*args, **kwargs)

    def get_absolute_url(self):
        return f'/comum/notificacao/{self.pk}/'

    def pode_ler(self):
        return self.data_permite_marcar_lida < datetime.now()

    def pode_excluir(self):
        return self.data_permite_excluir < datetime.now()

    def possui_bloqueio(self):
        return not self.pode_ler() or not self.pode_excluir()

    @classmethod
    def contar_nao_lidas(cls, user):
        key = f'__NOTIFICACOES_NAO_LIDAS-{user.username}'
        count = cache.get(key, -1, local_ttl=10)
        if count == -1:
            count = cls.objects.filter(vinculo__user=user, lida=False).count()
            cache.set(key, count)
        return count

    @classmethod
    def limpar_cache(cls, user):
        try:
            key = f'__NOTIFICACOES_NAO_LIDAS-{user.username}'
            cache.delete(key)
        except Exception:
            pass

    @property
    def get_assunto(self):
        return self.notificacao.categoria.assunto

    def outras_notificacoes_nao_lidas_mesmo_objeto(self):
        registro_notificacoes_anteriores = RegistroNotificacao.objects.none()
        if self.notificacao.objeto_relacionado:
            registro_notificacoes_anteriores = RegistroNotificacao.objects.filter(
                vinculo=self.vinculo, notificacao__objeto_relacionado=self.notificacao.objeto_relacionado, lida=False
            ).exclude(pk=self.pk)
        return registro_notificacoes_anteriores.order_by()

    def get_mensagem(self):
        return self.notificacao.mensagem

    def get_preferencia(self):
        return PreferenciaNotificacao.objects.filter(vinculo=self.vinculo, categoria=self.notificacao.categoria).first()

    def get_preferencia_via_suap(self):
        return self.get_preferencia().via_suap

    def get_preferencia_via_email(self):
        return self.get_preferencia().via_email


class PreferenciaNotificacao(ModelPlus):
    categoria = models.ForeignKeyPlus('comum.CategoriaNotificacao', null=False, blank=False)
    vinculo = models.ForeignKeyPlus('comum.Vinculo', null=False, blank=False, verbose_name='Vínculo')
    via_suap = models.BooleanField(verbose_name='Via SUAP', default=True)
    via_email = models.BooleanField(verbose_name='Via E-mail', default=True)
    data = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = 'Preferência de Notificação'
        verbose_name_plural = 'Preferências de Notificações'
        ordering = ('-data',)

    def pode_desabilitar(self):
        return not self.categoria.forcar_habilitacao


class GroupDetail(ModelPlus):
    group = models.ForeignKeyPlus('auth.Group', null=False, blank=False)
    app = models.CharFieldPlus(
        'App',
        null=True,
        blank=False,
    )
    app_manager = models.CharFieldPlus(
        'App Manager',
        null=True,
        blank=False,
    )
    descricao = models.TextField(
        'Descrição do Grupo',
        null=False,
        blank=False,
    )

    class Meta:
        verbose_name = 'Detalhes do Grupo'
        verbose_name_plural = 'Detalhes dos Grupos'
        unique_together = ('app', 'group')

    def __str__(self):
        return f'{self.group} - {self.app}'

    def get_absolute_url(self):
        return f'/comum/grupos_usuarios/?modulo={self.app_manager}&grupo={self.group.id:d}'


class EmailBlockList(ModelPlus):
    """
    Registra os emails que não poderão mais ser escolhidos no SUAP
    """

    email = models.EmailField(
        'Email', null=False, blank=False, unique=True, db_index=True, help_text='Este email não poderá mais ser escolhido para ser usado no SUAP.'
    )

    data_criacao = models.DateTimeField(verbose_name='Data de criação', auto_now_add=True)

    class Meta:
        verbose_name = 'Email na BlockList'
        verbose_name_plural = 'Emails na Blocklist'


class AutenticacaoDoisFatores(ModelPlus):
    SUAP = 'SUAP'
    OTP = 'OTP'
    TIPO_CHOICES = ((SUAP, 'SUAP'), (OTP, 'OTP - One Time Password'))

    usuario = models.OneToOneFieldPlus(User, on_delete=models.CASCADE, verbose_name='Usuário')
    ativo = models.BooleanField('Autenticação em Dois Fatores', default=False)
    tipo = models.CharFieldPlus(choices=TIPO_CHOICES)
    otp_secret_user = models.CharFieldPlus('Código de Validação - OTP', null=True)
    data_ultima_ativacao = models.DateTimeFieldPlus(null=True)
    data_ultima_desativacao = models.DateTimeFieldPlus(null=True)

    class Meta:
        verbose_name = 'Autenticação em Dois Fatores do Usuário'
        verbose_name_plural = 'Autenticações em Dois Fatores do Usuários'

    def save(self, *args, **kwargs):
        if not self.pk:
            self.otp_secret_user = base64.b32encode(os.urandom(10)).decode('utf-8')
        #
        super().save(*args, **kwargs)

    def __str__(self):
        return f'Autenticação Duplo Fator de: {self.usuario}'

    @property
    def username(self):
        return self.usuario.username

    def ativar(self):
        self.ativo = True
        self.validar_qrcode()

    def validar_qrcode(self):
        self.data_ultima_ativacao = datetime.now()

    def validou_qrcode(self):
        return bool(self.data_ultima_ativacao)

    def get_qrcode_image(self, instituicao):
        """Gera imagem QR code para configuração de autenticação de dois fatores.

        Args:
            instituicao: nome da instituição usado no issuer do TOTP.

        Returns:
            str: imagem QR code em base64 para o aplicativo autenticador.
        """
        import qrcode

        issuer = f'SUAP-{instituicao}'
        url = f'otpauth://totp/{issuer}:{self.username}?secret={self.otp_secret_user}&issuer={issuer}'
        image = qrcode.make(url)
        buffered = io.BytesIO()
        image.save(buffered, format='PNG')
        img_str_base64 = base64.b64encode(buffered.getvalue()).decode()
        return img_str_base64


class TipoArquivo(ModelPlus):
    nome = models.CharField(verbose_name='Nome', max_length=250)
    extensoes = models.CharField(verbose_name='Extensões', max_length=250, help_text='Informe as extensões separadas por virgula.')
    eh_video = models.BooleanField('É arquivo de vídeo?', default=False)

    class Meta:
        verbose_name = 'Tipo de arquivo'
        verbose_name_plural = 'Tipos de arquivo'

    def __str__(self):
        return f'{self.nome} ({self.extensoes})'


APIS_MAPEADAS = [
    'CNPJ',
    'CADUNICO',
    'PESSOAFISICA',
    'NOTIFICA_GOVBR',
    'SIAPE_CONECTA',
    'PESSOACOMDEFICIENCIA',
    'PEDEMEIA',
    'MSGRAPH',
    'PGD',
    'SIAPE_NET',
    'CONTRATOSGOVBR',
    'CEP',
    'MOODLE',
    'ACOMPANHAMENTO_GOVBR',
    'AVALIACAO_GOVBR',
    'ICPEDU',
    'CKAN',
    'RNMAISVACINA',
]


def buscar_api(cls, name):
    # Agora a lista vem do banco/cache, não é mais hardcoded
    apis_mapeadas = APIS_MAPEADAS

    if name in apis_mapeadas:
        # Tenta buscar do Redis primeiro
        cache_key = f'APIEXTERNA_CACHED_{name}'
        cached_values = cache.get(cache_key, local_ttl=10)

        if cached_values is None:
            # Busca apenas os valores no banco (mais leve que trazer o objeto todo)
            # O .first() aqui garante que pegamos o dicionário ou None
            obj_data = cls.objects.filter(nome=name).values().first()

            if not obj_data:
                # Se não existir, cria e retorna os valores
                new_obj, _ = cls.objects.get_or_create(nome=name)
                # Usamos model_to_dict ou buscamos de novo com .values()
                obj_data = cls.objects.filter(id=new_obj.id).values().first()

            cache.set(cache_key, obj_data)
            cached_values = obj_data

        # Reconstrói a instância em memória (Singleton de requisição)
        return cls(**cached_values)

    raise AttributeError(f"'{cls.__name__}' object has no attribute '{name}'")


class APIExternaMeta(type(models.ModelPlus)):
    def __getattr__(cls, name):
        return buscar_api(cls, name)


class APIExterna(models.ModelPlus, metaclass=APIExternaMeta):
    CONECTA_AUTH = 'CONECTA'
    DATAPREV_AUTH = 'DATAPREV'
    CLIENT_CREDENTIALS_AUTH = 'OAUTH2_CLIENT_CREDENTIALS'
    API_KEY_AUTH = 'API KEY'
    BASIC_AUTH = 'BASIC AUTH'
    CPF_AUTH = 'CPF AUTH'
    TOKEN_AUTH = 'TOKEN_AUTH'
    TIPO_CHOICES = (
        (CONECTA_AUTH, 'CONECTA GOV BR'),
        (DATAPREV_AUTH, 'DATAPREV'),
        (API_KEY_AUTH, 'API KEY'),
        (CLIENT_CREDENTIALS_AUTH, 'OAuth2 - Client Credentials'),
        (BASIC_AUTH, 'Basic Auth'),
        (CPF_AUTH, 'Bearer Token (usuário e senha)'),
        (TOKEN_AUTH, 'Token'),
    )

    nome = models.CharFieldPlus(max_length=100, unique=True)
    url_base = models.URLField(verbose_name='URL Base da API', max_length=200, blank=False, null=False)
    url_token = models.URLField(verbose_name='URL para obter Access Token', max_length=200, blank=True, null=True)
    url_documentacao = models.URLField(verbose_name='URL da documentação', max_length=200, blank=True, null=True)
    endpoint = models.CharField(max_length=200, blank=True, null=True)
    tipo_autenticacao = models.CharField(max_length=50, blank=False, null=False, choices=TIPO_CHOICES)
    ativo = models.BooleanField('Ativo', default=False)
    data_criacao = models.DateTimeField(verbose_name='Data de criação', auto_now_add=True)
    usuario_responsavel = models.ForeignKeyPlus('comum.User', verbose_name='Usuário Responsável', null=True, blank=True)
    cpf_operador = models.CharFieldPlus(verbose_name='CPF do Operador', blank=True, null=True, max_length=11)
    client_id = models.TextField(verbose_name='Client ID', blank=False, null=False)
    secret = models.TextField(verbose_name='Secret or API KEY', blank=False, null=False)
    headers = models.JSONField(verbose_name='Headers', blank=True, null=False, default=dict)
    dias_para_expirar = models.IntegerFieldPlus(blank=False, null=False, default=1)
    service_path = models.CharFieldPlus(
        verbose_name='Caminho do Serviço',
        help_text='Caminho completo do serviço que implementa a comunicação com a API externa. Exemplo: meu_app.services.MinhasAPIsService',
        max_length=200,
        blank=True,
        null=True,
    )

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        obj_data = type(self).objects.filter(id=self.id).values().first()

        cache_key = f'APIEXTERNA_CACHED_{self.nome}'
        cache.set(cache_key, obj_data)

    def get_service(self):
        from comum.services import APIExternaService

        service = None
        if not self.service_path:
            return APIExternaService(self)

        app_name = self.service_path.rsplit('.', 2)[0]
        module_path, class_name = self.service_path.rsplit('.', 1)
        if app_name not in settings.INSTALLED_APPS:
            return APIExternaService(self)

        klass = __import__(module_path, fromlist=[class_name])
        service = getattr(klass, class_name)()
        return service

    def estah_acessivel(self, verbosity=False):
        try:
            return self.get_service().estah_acessivel(verbosity=verbosity)
        except Exception:
            return False


class ObjetivoDesenvolvimentoSustentavel(models.ModelPlus):
    SEARCH_FIELDS = [
        'descricao',
    ]
    descricao = models.TextField('Descrição')
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Objetivo para o Desenvolvimento Sustentável da ONU'
        verbose_name_plural = 'Objetivos para o Desenvolvimento Sustentável da ONU'

    def __str__(self):
        return f'{self.id} - {self.descricao}'


class SubobjetivoDesenvolvimentoSustentavel(models.ModelPlus):
    SEARCH_FIELDS = [
        'descricao',
        'objetivo__descricao',
        'numero',
    ]
    descricao = models.TextField('Descrição')
    numero = models.CharFieldPlus('Número', unique=True)
    objetivo = models.ForeignKeyPlus(ObjetivoDesenvolvimentoSustentavel, verbose_name='ODS', on_delete=models.CASCADE)
    ativo = models.BooleanField('Ativo', default=True)

    class Meta:
        verbose_name = 'Subobjetivo para o Desenvolvimento Sustentável da ONU'
        verbose_name_plural = 'Subobjetivos para o Desenvolvimento Sustentável da ONU'

    def __str__(self):
        return f'{self.numero} - {self.descricao}'


class ReuniaoOrgaoColegiado(models.ModelPlus):
    ORGAO_CODIR = 1
    ORGAO_CONSUP = 2
    ORGAO_CONSEPEX = 3

    ORGAOS_CHOICES = [[ORGAO_CODIR, 'CODIR'], [ORGAO_CONSUP, 'CONSUP'], [ORGAO_CONSEPEX, 'CONSEPEX']]

    titulo = models.CharFieldPlus('Título')
    colegiado = models.IntegerField('Colegiado', choices=ORGAOS_CHOICES)
    descricao = models.CharFieldPlus('Descrição', null=True)
    local = models.CharFieldPlus('Local', null=True)
    data_inicio = models.DateFieldPlus('Data Início')
    data_fim = models.DateFieldPlus('Data Fim')
    hora_inicio = models.TimeFieldPlus('Hora Início')
    hora_fim = models.TimeFieldPlus('Hora Fim')

    class Meta:
        verbose_name = 'Reunião de Órgão Colegiado Superior'
        verbose_name_plural = 'Reuniões de Órgãos Colegiados Superiores'
        ordering = ['-data_inicio']
        permissions = (('pode_consultar_calendarios', 'Pode Consultar Calendários'),)

    class CalendarioReuniaoOrgaoColegiado:
        def __init__(
            self,
            data_inicio: date,
            data_fim: date,
            reunioes: list[ReuniaoOrgaoColegiado],
            reunioes_por_ano: dict[int, dict[int, list[ReuniaoOrgaoColegiado]]],  # {ano: {mes: [reuniao, reuniao, ...]}}
            reunioes_por_dia: dict[date, list[ReuniaoOrgaoColegiado]],  # {data: [reuniao, reuniao, ...]}
        ):
            self.data_inicio = data_inicio
            self.data_fim = data_fim
            self.reunioes = reunioes
            self.reunioes_por_ano = reunioes_por_ano
            self.reunioes_por_dia = reunioes_por_dia

    CHOICE_ITEM_INT_STR = list[tuple[int, str]]

    @staticmethod
    def query(data_inicio: date | None = None, data_fim: date | None = None):
        """lógica de consulta (expressões de filtragem, desempenho, ...)"""

        qs_base = ReuniaoOrgaoColegiado.objects

        filters = {}

        filter_data_inicio = data_inicio
        filter_data_fim = data_fim

        if data_inicio and not data_fim:
            filter_data_fim = data_inicio

        if data_fim and not data_inicio:
            filter_data_inicio = data_fim

        if filter_data_inicio and filter_data_fim:
            filters.update({'data_fim__gte': filter_data_inicio, 'data_inicio__lte': filter_data_fim})

        if filters:
            qs = qs_base.filter(**filters)
        else:
            qs = qs_base.none()  # por padrão é restrito aos parâmetros de filtragem

        return qs

    @staticmethod
    def listar_orgaos_colegiados(codigo: int | None = None) -> list[CHOICE_ITEM_INT_STR]:
        if codigo:
            return [dict(ReuniaoOrgaoColegiado.ORGAOS_CHOICES).get(codigo, [0, '?'])]
        return ReuniaoOrgaoColegiado.ORGAOS_CHOICES

    @staticmethod
    def obter_calendario_reuniao_orgao_colegiado(data_inicio: date | None = None, data_fim: date | None = None) -> CalendarioReuniaoOrgaoColegiado:
        ano_mes_inicio = int(f'{data_inicio.year}'.zfill(4) + f'{data_inicio.month}'.zfill(2))
        ano_mes_fim = int(f'{data_fim.year}'.zfill(4) + f'{data_fim.month}'.zfill(2))

        reunioes = []
        reunioes_por_ano = {}
        reunioes_por_dia = {}

        reunioes_periodo = ReuniaoOrgaoColegiado.query(data_inicio=data_inicio, data_fim=data_fim)

        for reuniao in reunioes_periodo:
            mes_inicio = reuniao.data_inicio.month
            ano_inicio = reuniao.data_inicio.year
            mes_fim = reuniao.data_fim.month
            ano_fim = reuniao.data_fim.year

            for ano in range(ano_inicio, ano_fim + 1):
                ano_no_escopo_da_consulta = data_inicio.year <= ano <= data_fim.year
                if not ano_no_escopo_da_consulta:
                    continue
                if ano not in reunioes_por_ano:
                    reunioes_por_ano[ano] = {}

                ano_mes_reunioes_ids = []
                for mes in range(mes_inicio, mes_fim + 1):
                    ano_mes = int(f'{ano}'.zfill(4) + f'{mes}'.zfill(2))
                    ano_mes_no_escopo_da_consulta = ano_mes_inicio <= ano_mes <= ano_mes_fim
                    if not ano_mes_no_escopo_da_consulta:
                        continue
                    if mes not in reunioes_por_ano[ano]:
                        reunioes_por_ano[ano][mes] = []
                    if reuniao.id not in ano_mes_reunioes_ids:
                        reunioes_por_ano[ano][mes].append(reuniao)
                        ano_mes_reunioes_ids.append(reuniao.id)

            reunioes.append(reuniao)

        for ano, mes_info in reunioes_por_ano.items():
            for mes in mes_info:
                reunioes_por_ano[ano][mes] = sorted(
                    reunioes_por_ano[ano][mes],
                    key=lambda reuniao: f'{reuniao.data_inicio.strftime("%Y%m%d")}{reuniao.hora_inicio.strftime("%H%M%S")}',
                )
                for reuniao in reunioes_por_ano[ano][mes]:
                    for dia in daterange(reuniao.data_inicio, reuniao.data_fim):
                        dia_no_escopo_da_consulta = data_inicio <= dia <= data_fim
                        if dia_no_escopo_da_consulta:
                            if dia not in reunioes_por_dia:
                                reunioes_por_dia[dia] = []
                            reunioes_por_dia[dia].append(reuniao)

        calendario = ReuniaoOrgaoColegiado.CalendarioReuniaoOrgaoColegiado(
            data_inicio=data_inicio,
            data_fim=data_fim,
            reunioes=reunioes,
            reunioes_por_ano=reunioes_por_ano,
            reunioes_por_dia=reunioes_por_dia,
        )

        return calendario

    def get_absolute_url(self):
        return f'/comum/orgaos_colegiados_detalhar_reuniao/{self.id}/'

    @classmethod
    def validar(cls, data=None, instance=None):
        instance = ModelValidation.instance_for_validation(cls, data, instance)

        if instance.data_inicio and instance.data_fim and instance.data_inicio > instance.data_fim:
            raise ValidationError({'data_inicio': 'Data início deve ser menor ou igual a Data fim.'})

        if instance.hora_inicio and instance.hora_fim and instance.hora_inicio >= instance.hora_fim:
            raise ValidationError({'hora_inicio': 'Hora início deve ser menor que Hora fim.'})


class SenhaExposta(models.ModelPlus):
    """
    Modelo para armazenar senhas expostas.
    """

    usuario = models.ForeignKeyPlus('comum.User', on_delete=models.CASCADE, verbose_name='Usuário', null=False, blank=False)
    email = models.CharFieldPlus('Email/Username', max_length=255, null=True, blank=True)
    senha = models.CharFieldPlus('Senha', max_length=255, null=False, blank=False)
    formato_senha = models.CharFieldPlus(
        'Formato da Senha', max_length=255, blank=True, null=True, help_text='Formato da senha exposta, se conhecido.'
    )
    data_exposicao = models.DateTimeFieldPlus('Data de Exposição', auto_now_add=True)

    class Meta:
        verbose_name = 'Senha Exposta'
        verbose_name_plural = 'Senhas Expostas'

    def __str__(self):
        return f'Usuário: {self.usuario} - Senha: {self.senha} ({self.formato_senha}) - Exposta em: {self.data_exposicao}'


class Atalho(models.ModelPlus):
    usuario = models.CurrentUserField(verbose_name='Usuário')
    nome = models.CharField(verbose_name='Nome', max_length=50)
    url = models.TextField('Endereço')

    class Meta:
        verbose_name = 'Atalho'
        verbose_name_plural = 'Atalhos'
