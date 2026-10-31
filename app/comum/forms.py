# ruff: noqa: PLC2401
import calendar
import datetime
import os
import re
import tempfile
from collections import OrderedDict
from datetime import timedelta

import onetimepass
import onetimepass as otp
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.admin.models import CHANGE, LogEntry
from django.contrib.admin.options import get_content_type_for_model
from django.contrib.admin.widgets import FilteredSelectMultiple
from django.contrib.auth.forms import AuthenticationForm
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models import Max, Min, Q
from django.forms import CharField, FileField
from django.forms.fields import DateField, MultipleChoiceField
from django.shortcuts import get_object_or_404
from django.utils.encoding import force_str
from django.utils.formats import localize
from django.utils.html import strip_tags
from django.utils.safestring import mark_safe
from sentry_sdk import capture_exception
from tinymce.widgets import TinyMCE

from comum import signer
from comum.models import (
    AcabamentoExternoPredio,
    AcabamentoParedeSala,
    Ano,
    APIExterna,
    AreaAtuacao,
    Atalho,
    CategoriaNotificacao,
    CertificadoDigital,
    ClimatizacaoSala,
    CoberturaPredio,
    Configuracao,
    ConfiguracaoAutomatizacaoGrupo,
    ConfiguracaoImpressaoDocumento,
    ContatoEmergencia,
    Device,
    DocumentoControle,
    DocumentoControleHistorico,
    DocumentoControleTipo,
    EmailBlockList,
    EsquadriasSala,
    EstruturaPredio,
    ForroSala,
    GerenciamentoGrupo,
    IndexLayout,
    IndisponibilizacaoSala,
    InscricaoFiscal,
    InstalacaoEletricaSala,
    InstalacaoGasesSala,
    InstalacaoHidraulicaSala,
    InstalacaoLogicaSala,
    JustificativaUsuarioExterno,
    ManutencaoProgramada,
    Obra,
    OcupacaoPrestador,
    Pais,
    Pensionista,
    PisoSala,
    Predio,
    Preferencia,
    PrestadorServico,
    Publico,
    RegistroEmissaoDocumento,
    ReservaSala,
    ReuniaoOrgaoColegiado,
    Sala,
    SetorTelefone,
    SistemaAbastecimentoPredio,
    SistemaAlimentacaoEletricaPredio,
    SistemaProtecaoDescargaAtmosfericaPredio,
    SistemaSanitarioPredio,
    SolicitacaoReservaSala,
    TipoCarteiraFuncional,
    User,
    VedacaoPredio,
    Vinculo,
)
from comum.pdf import PdfSigner
from comum.utils import get_logo_instituicao_file_path, get_logo_instituicao_fundo_transparente_file_path, get_uo
from djtools import forms
from djtools.choices import SituacaoSolicitacaoDocumento
from djtools.forms import PositionedPdfInput, ReadOnlyField, ReCaptchaField
from djtools.forms.fields import MultipleModelChoiceFieldPlus
from djtools.forms.widgets import AutocompleteWidget, BrTelefoneWidget, CheckboxSelectMultiplePlus, FilteredSelectMultiplePlus
from djtools.forms.wizard import FormWizardPlus
from djtools.lps import MetaFormPlus
from djtools.storages import cache_file
from djtools.utils import (
    gera_nomes,
    get_ldap_conf,
    is_ldap_enabled,
    mask_cpf,
    retira_acentos,
    sync_ldap_user,
    to_ascii,
    validar_email_conta_institucional,
)
from djtools.utils.ldap import sync_ldap_user_emails
from rh.deduplicacao.documentos import formatar_passaporte
from rh.deduplicacao.entrada import (
    filtro_par_passaporte,
    recusar_passaporte_de_outra_pessoa,
    travar_documentos_na_edicao,
    recusar_cadastro_de_prestador,
)
from rh.enums import Nacionalidade
from rh.forms import get_choices_nome_usual
from rh.models import CargoEmprego, Pessoa, PessoaJuridica, Servidor, Setor, Situacao, UnidadeOrganizacional
from suap import nomenclatura


class PublicoAdminForm(forms.ModelFormPlus):
    class Meta:
        model = Publico
        exclude = ()

    def clean_filtro(self):
        filtro = self.cleaned_data.get('filtro', None)
        if filtro:
            try:
                import json

                json.loads(filtro)
            except ValueError:
                raise forms.ValidationError('Formato inválido.')

        return filtro

    def clean_filtro_exclusao(self):
        filtro_exclusao = self.cleaned_data.get('filtro_exclusao', None)
        if filtro_exclusao:
            try:
                import json

                json.loads(filtro_exclusao)
            except ValueError:
                raise forms.ValidationError('Formato inválido.')

        return filtro_exclusao


class CertificadoDigitalForm(forms.ModelFormPlus):
    senha = forms.CharField(
        label='Senha do Certificado',
        widget=forms.PasswordInput,
        help_text='<br>Importante:</b> A senha do certificado não é salva no banco de dados. Ela é utilizada apenas para fins de validação do cadastro e extração da chave pública contida no arquivo.',
    )

    class Meta:
        model = CertificadoDigital
        fields = ('user', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.is_superuser:
            self.fields['user'].initial = self.request.user.pk
            self.fields['user'].widget = forms.HiddenInput()
            self.instance.user = self.request.user
        self.arquivo_pfx = None

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data
        senha = cleaned_data.get('senha')
        conteudo = cleaned_data.get('arquivo').read()
        self.pfx_file = tempfile.NamedTemporaryFile(suffix='.pfx', delete=False)
        self.pfx_file.write(conteudo)
        self.pfx_file.close()
        try:
            signer.subject(self.pfx_file.name, senha)
        except AttributeError:
            self.add_error('arquivo', 'Certificado inválido. Por favor gere um novo.')
        except ValueError:
            self.add_error('senha', 'Senha inválida.')
        return cleaned_data

    def save(self, *args, **kwargs):
        subject = signer.subject(self.pfx_file.name, self.cleaned_data['senha'])
        certificado_digital = super().save(commit=False)
        certificado_digital.nome = subject['CN']
        certificado_digital.organizacao = subject['O']
        certificado_digital.unidade = subject['OU']
        certificado_digital.validade = signer.expiration_date(self.pfx_file.name, self.cleaned_data['senha'])
        certificado_digital.conteudo = signer.dump_certificate(self.pfx_file.name, self.cleaned_data['senha'])
        certificado_digital.save()
        return certificado_digital


class AssinarDocumentoForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo PDF', max_file_size=5 * 1024 * 1024, filetypes=('pdf',), widget_custom_cls=PositionedPdfInput)
    certificado = forms.ModelChoiceField(CertificadoDigital.objects, label='Certificado')
    senha = forms.CharField(label='Senha do Certificado', widget=forms.PasswordInput)

    fieldsets = (
        ('Arquivo', {'fields': ('arquivo',)}),
        ('Assinatura', {'fields': (('certificado', 'senha'),)}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['certificado'].queryset = CertificadoDigital.objects.filter(user=self.request.user, validade__gte=datetime.date.today())

    def clean_senha(self):
        certificado = self.cleaned_data.get('certificado')
        if not certificado:
            raise ValidationError('Escolha o certificado.')
        senha = self.cleaned_data.get('senha')
        try:
            local_filename = cache_file(certificado.arquivo.name)
            signer.subject(local_filename, senha)
            os.unlink(local_filename)
        except ValueError:
            raise ValidationError('Senha inválida.')
        return senha

    def processar(self):
        arquivo = self.cleaned_data.get('arquivo')
        certificado = self.cleaned_data.get('certificado')
        senha = self.cleaned_data.get('senha')
        arquivo.seek(0)
        conteudo_arquivo = arquivo.read()
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fp:
            fp.write(conteudo_arquivo)
        py, px = self.request.POST.get('pdf-coords').split(':')
        page = int(self.request.POST.get('pdf-page', 1))
        local_filename = cache_file(certificado.arquivo.name)
        signed = signer.sign(local_filename, senha, fp.name, sign_img=True, page=page, px=px, py=py)
        os.unlink(local_filename)
        return signed


class VerificarDocumentoForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo', filetypes=('pdf',))

    def processar(self):
        arquivo = self.cleaned_data.get('arquivo')
        arquivo.seek(0)
        conteudo_arquivo = arquivo.read()
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fp:
            fp.write(conteudo_arquivo)
        return signer.verify(fp.name)


class ValidarDocumentoForm(VerificarDocumentoForm):
    recaptcha = ReCaptchaField(label='')


class Desabilitar2FAForm(forms.FormPlus):
    SUBMIT_LABEL = 'Desabilitar 2FA'
    motivo = forms.CharFieldPlus(label='Motivo', required=True, widget=forms.Textarea)

    fieldsets = ((None, {'fields': ('motivo',)}),)


class AreaAtuacaoForm(forms.ModelForm):
    class Meta:
        model = AreaAtuacao
        exclude = ('slug',)


class ConfiguracaoAutomatizacaoGrupoForm(FormWizardPlus):
    setores = forms.MultipleModelChoiceFieldPlus(label='Setores', queryset=Setor.objects.suap_ativos(), widget=AutocompleteWidget(multiple=True))
    cargo_emprego = forms.ModelChoiceFieldPlus(
        queryset=CargoEmprego.objects, required=False, widget=AutocompleteWidget(search_fields=CargoEmprego.SEARCH_FIELDS)
    )
    confirmacao = forms.BooleanField(label='Confirma operação?', widget=forms.CheckboxInput, required=True)

    steps = (
        [
            (
                'Selecionar configuração',
                {
                    'fields': (
                        'setores',
                        'cargo_emprego',
                    )
                },
            )
        ],
        [('Confirmar operação', {'fields': ('confirmacao',)})],
    )
    # class Meta:
    #     model = ConfiguracaoAutomatizacaoGrupo
    #     fields = ('setores', 'cargo_emprego', 'ativa')

    def __init__(self, *args, **kwargs):
        self.instance = kwargs.pop('instance', None)
        self.grupo = kwargs.pop('grupo', None)
        super().__init__(*args, **kwargs)
        if self.instance:
            self.steps = (
                [('Selecionar configuração', {'fields': ('setores', 'cargo_emprego', 'ativa')})],
                [('Confirmar operação', {'fields': ('confirmacao',)})],
            )
            self.fields['ativa'] = forms.BooleanField(label='Ativa', widget=forms.CheckboxInput, required=False)
            self.fields['ativa'].initial = self.instance.ativa
            self.fields['setores'].initial = self.instance.setores.all()
            self.fields['cargo_emprego'].initial = self.instance.cargo_emprego

    def next_step(self):
        setores = self.get_entered_data('setores', is_list=True)
        cargo = self.get_entered_data('cargo_emprego')
        ativa = None
        if 'ativa' in self.cleaned_data:
            ativa = self.get_entered_data('ativa')
        if setores:
            if self.instance:
                analise = self.instance.get_analise_impacto(setores, cargo, ativa)
            else:
                analise = ConfiguracaoAutomatizacaoGrupo.analise_impacto(self.grupo, setores, cargo)
            # Adiciona ao contexto
            self.permanecerao = analise['permanecerao']
            self.qtd_permanecerao = len(analise['permanecerao'])
            self.serao_removidos = analise['serao_removidos']
            self.qtd_serao_removidos = len(analise['serao_removidos'])
            self.serao_adicionados = analise['serao_adicionados']
            self.qtd_serao_adicionados = len(analise['serao_adicionados'])

    @transaction.atomic
    def processar(self, request):
        setores = self.cleaned_data.get('setores')
        cargo = self.cleaned_data.get('cargo_emprego')
        ativa = self.cleaned_data.get('ativa') or True
        if self.instance:
            analise = self.instance.get_analise_impacto(setores, cargo, ativa)
        else:
            analise = ConfiguracaoAutomatizacaoGrupo.analise_impacto(self.grupo, setores, cargo)
        if self.instance:
            nova_configuracao = self.instance
            nova_configuracao.atualizado_por = request.user
        else:
            nova_configuracao = ConfiguracaoAutomatizacaoGrupo()
            nova_configuracao.criado_por = request.user
        nova_configuracao.cargo_emprego = cargo
        nova_configuracao.ativa = ativa
        nova_configuracao.grupo = self.grupo
        nova_configuracao.save()
        nova_configuracao.setores.set(setores)
        return nova_configuracao, analise


class AtualizarEmailForm(forms.FormPlus):
    email_secundario = forms.EmailField(max_length=255, required=False, label='E-mail Pessoal')
    email_institucional = forms.EmailField(max_length=255, required=False, label='E-mail Institucional')
    email_academico = forms.EmailField(max_length=255, required=False, label='E-mail Acadêmico')
    email_google_classroom = forms.EmailField(max_length=255, required=False, label='E-mail Google ClassRoom')

    def _clean_email_conta_institucional(self, email: str) -> str:
        email = (email or '').strip().lower()
        if not validar_email_conta_institucional(email):
            raise forms.ValidationError('Informe um e-mail com apenas letras, números e pontos antes do @.')
        return email

    def _get_usuario_com_email_academico(self, email_academico: str) -> str:
        q_exclude = Q(pk=self.relacionamento.id)

        Aluno = apps.get_model('edu', 'aluno')
        if Aluno:
            qs_aluno = Aluno.objects.filter(email_academico=email_academico)
            if self.relacionamento.get_vinculo().eh_aluno():  # q_exclude é o pk do relacionamento: só vale se ele é o aluno
                qs_aluno = qs_aluno.exclude(q_exclude)
            aluno_com_email = qs_aluno.select_related('pessoa_fisica').only('pessoa_fisica__nome', 'matricula').first()
            if aluno_com_email:
                return f'{aluno_com_email.pessoa_fisica.nome}({aluno_com_email.matricula})'

        servidor_com_email = (
            Servidor.objects.filter(email_academico=email_academico).exclude(q_exclude).only('pessoa_fisica__nome', 'matricula').first()
        )
        if servidor_com_email:
            return f'{servidor_com_email.matricula}'

        prestador_com_email = (
            PrestadorServico.objects.filter(email_academico=email_academico).exclude(q_exclude).only('pessoa_fisica__nome', 'matricula').first()
        )
        if prestador_com_email:
            return f'{prestador_com_email.matricula}'

        return ''

    def _email_google_classroom_existe_em_outro_usuario(self, email_google_classroom: str) -> bool:
        Aluno = apps.get_model('edu', 'aluno')
        q_exclude = Q(pk=self.relacionamento.id)
        vinculo = self.relacionamento.get_vinculo()
        qs_servidor = Servidor.objects.filter(email_google_classroom=email_google_classroom)
        qs_prestador = PrestadorServico.objects.filter(email_google_classroom=email_google_classroom)

        if Aluno:
            qs_aluno = Aluno.objects.filter(email_google_classroom=email_google_classroom)
            if vinculo.eh_aluno:
                qs_aluno = qs_aluno.exclude(q_exclude)
            if qs_aluno.exists():
                return True
        if vinculo.eh_servidor and qs_servidor.exclude(q_exclude).exists():
            return True
        return bool(vinculo.eh_prestador and qs_prestador.exclude(q_exclude).exists())

    def clean_email_secundario(self):
        if not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario'):
            if Configuracao.eh_email_institucional(self.cleaned_data['email_secundario']):
                raise forms.ValidationError('Escolha um e-mail que não seja institucional.')
        return self.cleaned_data['email_secundario']

    def clean_email_institucional(self) -> str:
        email_institucional = self._clean_email_conta_institucional(self.cleaned_data['email_institucional'])
        if (
            email_institucional
            and Servidor.objects.exclude(pessoa_fisica__id=self.pessoa_fisica.id).filter(email_institucional=email_institucional).exists()
        ):
            raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
        ldap_conf = get_ldap_conf()
        if ldap_conf and ldap_conf.has_write_permission():
            usernames = ldap_conf.get_usernames_from_mail(email_institucional)
            if usernames and self.relacionamento.matricula not in usernames:
                raise forms.ValidationError('O e-mail informado já é utilizado por outro usuário.')
        return email_institucional

    def clean_email_academico(self) -> str:
        email_academico = self._clean_email_conta_institucional(self.cleaned_data['email_academico'])
        if email_academico:
            usuarios_com_email = self._get_usuario_com_email_academico(email_academico)
            if usuarios_com_email:
                raise forms.ValidationError(f'O e-mail informado já existe para outro usuário: {usuarios_com_email}')

            if EmailBlockList.objects.filter(email=email_academico).exists():
                raise forms.ValidationError('O e-mail informado está bloqueado.')

            ldap_conf = get_ldap_conf()
            if ldap_conf and ldap_conf.has_write_permission():
                usernames = ldap_conf.get_usernames_from_principalname(email_academico)
                usernames.extend(ldap_conf.get_usernames_from_mail(email_academico))
                if usernames and self.relacionamento.matricula not in usernames:
                    raise forms.ValidationError('O e-mail informado já é utilizado por outro usuário.')

        return email_academico

    def clean_email_google_classroom(self) -> str:
        email_google_classroom = self._clean_email_conta_institucional(self.cleaned_data['email_google_classroom'])
        if email_google_classroom:
            if self._email_google_classroom_existe_em_outro_usuario(email_google_classroom):
                raise forms.ValidationError('O e-mail informado já existe para outro usuário.')
            if EmailBlockList.objects.filter(email=email_google_classroom).exists():
                raise forms.ValidationError('O e-mail informado está bloqueado.')

            ldap_conf = get_ldap_conf()
            if ldap_conf and ldap_conf.has_write_permission():
                usernames = ldap_conf.get_usernames_from_email_google_classroom(email_google_classroom)
                if usernames and self.relacionamento.matricula not in usernames:
                    raise forms.ValidationError('O e-mail informado já é utilizado por outro usuário.')
        return email_google_classroom

    def __init__(self, *args, **kwargs):
        self.relacionamento = kwargs.pop('relacionamento')
        self.pessoa_fisica = self.relacionamento.pessoa_fisica
        super().__init__(*args, **kwargs)
        # o vínculo editado decide, não a pessoa: deduplicada, a mesma pessoa pode ser servidor e prestador
        vinculo = self.relacionamento.get_vinculo()
        eh_servidor, eh_prestador = vinculo.eh_servidor(), vinculo.eh_prestador()
        self.fields['email_secundario'].initial = self.relacionamento.email_pessoal
        if (self.request.user.get_profile().pk != int(self.pessoa_fisica.pk)) and (
            (eh_servidor and not self.request.user.has_perm('rh.pode_editar_email_secundario_servidor'))
            or (eh_prestador and not self.request.user.has_perm('rh.pode_editar_email_secundario_prestador'))
        ):
            del self.fields['email_secundario']

        """ Só exibe os demais campos se for servidor """
        if eh_servidor:
            self.fields['email_institucional'].initial = self.relacionamento.email_institucional
            self.fields['email_academico'].initial = self.relacionamento.email_academico
            self.fields['email_google_classroom'].initial = self.relacionamento.email_google_classroom

            if not self.request.user.has_perm('rh.pode_editar_email_institucional'):
                del self.fields['email_institucional']
            if not self.request.user.has_perm('rh.pode_editar_email_academico'):
                del self.fields['email_academico']
            if not self.request.user.has_perm('rh.pode_editar_email_google_classroom'):
                del self.fields['email_google_classroom']

        elif eh_prestador:
            del self.fields['email_institucional']
            self.fields['email_academico'].initial = self.relacionamento.email_academico
            if not self.request.user.has_perm('rh.pode_editar_email_academico'):
                del self.fields['email_academico']
            if self.relacionamento.get_vinculo().user.has_perm('edu.eh_professor'):
                self.fields['email_google_classroom'].initial = self.relacionamento.email_google_classroom
            if not self.request.user.has_perm('rh.pode_editar_email_google_classroom'):
                del self.fields['email_google_classroom']
        else:
            del self.fields['email_institucional']
            del self.fields['email_academico']
            del self.fields['email_google_classroom']
        texto_politica_email = Configuracao.get_valor_por_chave('comum', 'texto_politica_email')
        if texto_politica_email and (
            self.fields.get('email_institucional') or self.fields.get('email_academico') or self.fields.get('email_google_classroom')
        ):
            self.INFO = texto_politica_email

    def save(self):
        instancia = self.relacionamento
        emails = {}
        if 'email_institucional' in self.cleaned_data:
            instancia.email_institucional = self.cleaned_data.get('email_institucional')
            emails['email_institucional'] = instancia.email_institucional
        if 'email_academico' in self.cleaned_data:
            instancia.email_academico = self.cleaned_data.get('email_academico')
            emails['email_academico'] = instancia.email_academico
        if 'email_google_classroom' in self.cleaned_data:
            instancia.email_google_classroom = self.cleaned_data.get('email_google_classroom')
            emails['email_google_classroom'] = instancia.email_google_classroom
        instancia.save()

        if 'email_secundario' in self.cleaned_data:
            # email_secundario migrou p/ Vinculo.email_pessoal; grava no vínculo do papel (não em Pessoa).
            vinculo = instancia.get_vinculo()
            if vinculo:
                vinculo.email_pessoal = self.cleaned_data.get('email_secundario') or ''
                vinculo.save(update_fields=['email_pessoal'])

        if emails:
            sync_ldap_user_emails(instancia, emails)
        sync_ldap_user(instancia.matricula)


class ConfiguracaoForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        Municipio = apps.get_model('comum', 'municipio')
        estados = list(set(Municipio.objects.all().values_list('uf', flat=True)))
        estados.sort()

    municipio_sede = forms.CharField(label='Município Sede da Instituição', help_text='Município sede da instituição em que o SUAP está instalado')
    instituicao_sigla = forms.CharField(label='Sigla da Instituição', help_text='Sigla da instituição em que o SUAP está instalado')
    reitoria_sigla = forms.CharField(label='Sigla da Reitoria', help_text='Sigla da reitoria em que o SUAP está instalado')
    dominios_institucionais = forms.CharField(label='Domínios Institucionais', help_text='Domínios Institucionais separados por ";".')
    instituicao = forms.CharField(label='Instituição', widget=forms.Textarea, help_text='Nome da instituição em que o SUAP está instalado')
    instituicao_estado = forms.BrEstadoBrasileiroField(
        label='Estado da Instituição', help_text='Sigla do estado da Instituição utilizada em Endereços e Macros do Extrator'
    )
    instituicao_identificador = forms.CharField(
        label='Identificador SIAPE da Instituição',
        help_text='Faz parte da matrícula de 12 caracteres dos servidores e é usado para filtrar os dados nas Macros do Extrator',
    )
    instituicao_codigo_siorg = forms.CharField(
        label='Código SIORG da Instituição',
        help_text='Disponível em https://siorg.planejamento.gov.br/siorg-cidadao-webapp/pages/listar_orgaos_estruturas/listar_orgaos_estruturas.jsf',
    )
    instituicao_pessoa_juridica = forms.ModelChoiceFieldPlus(
        queryset=PessoaJuridica.objects,
        label='Pessoa Jurídica da Instituição',
        required=False,
        help_text='Selecione a pessoa jurídica da Instituição.',
    )

    instituicao_anterior_identificador = forms.CharField(
        label='Identificador SIAPE das Instituições Anteriores',
        help_text='Faz parte da matrícula de 12 caracteres dos servidores e é'
        ' usado para filtrar os dados nas Macros do Extrator. Se houver mais de uma instituição anterior, separar por ponto e vírgula',
        required=False,
    )
    siape_usuario = forms.CharField(label='SiapeNet usuário', help_text='Usuário para extração do SiapeNet', required=False)
    siape_senha = forms.CharField(label='SiapeNet senha', help_text='Senha para extração do SiapeNet', required=False)
    url_rss = forms.URLField(label='URL do RSS', help_text='URL do RSS para exibição na página inicial do SUAP', required=False)
    salario_minimo = forms.DecimalField(label='Salário Mínimo', help_text='Valor atual do salário mínimo')
    chave_publica = forms.CharField(
        label='Chave Pública', widget=forms.Textarea, help_text='Conteúdo da chave pública da máquina do SUAP', required=False
    )
    desabilitar_envio_email_dispositivo_desconhecido = forms.BooleanField(
        label='Desabilitar envio de emails para notificar dispositivos desconhecidos?',
        help_text='Marque caso não deseje notificar os usuários de login em um novo dipositivo desconhecido',
        required=False,
    )
    url_webmail = forms.URLField(label='URL do Webmail', help_text='URL do Webmail da instituição', required=False)
    url_portal = forms.URLField(label='URL do Portal', help_text='URL do Portal Institucional', required=False)
    sentry_token = forms.CharField(
        label='Token Bearer do Sentry para integração de APIs',
        help_text='Ex: a06631308fc54c68f86a54f2c8ecc61ece35c38181f1fc104c5998be2961c0fb',
        required=False,
    )
    sentry_url = forms.CharField(label='URL do Sentry sem barra no final', help_text='Ex: https://sentry.ifrn.edu.br', required=False)
    sentry_organization = forms.CharField(label='Organização do Sentry para o Projeto SUAP', help_text='Ex: sentry', required=False)
    sentry_project = forms.CharField(label='Projeto SUAP no Sentry', help_text='Ex: suap', required=False)
    sentry_glitchtip = forms.BooleanField(label='Usa GlitchTip?', help_text='Marque se o fork glitchtip do sentry for usado', required=False)
    caminho_libreoffice = forms.CharFieldPlus(
        label='Caminho para o executável do LibreOffice/API do SuapPDF',
        help_text='Ex: /Applications/LibreOffice.app/Contents/MacOS/soffice ou http://pdfprinter.suapdevs.ifrn.edu.br',
        required=False,
    )
    token_libreoffice = forms.CharFieldPlus(label='Token da API do SuapPDF', required=False)
    suap_ai_url = forms.CharFieldPlus(label='URL do SUAP AI', help_text='Ex: http://suapai.suapdevs.ifrn.edu.br', required=False)
    suap_ai_token = forms.CharFieldPlus(label='Token do SUAP AI', help_text='Token do SUAP AI', required=False)
    prazo_expiracao_senha = forms.IntegerField(label='Prazo em dias para expiração automática de senha', help_text='Ex: 365', required=False)

    logo_instituicao = forms.FileFieldPlus(
        label='Logotipo da instituição',
        required=False,
    )
    logo_instituicao_fundo_transparente = forms.FileFieldPlus(
        label='Logotipo da instituição com fundo transparente',
        required=False,
    )
    quadro_banner = forms.BooleanField(label='Quadro de banner', help_text='Apresenta o quadro de banner na index', required=False)
    quadro_manuais = forms.BooleanField(label='Quadro de manuais', help_text='Apresenta o quadro de manuais na index', required=False)

    # Autenticação com Login Gov.BR
    habilitar_autenticacao_govbr = forms.BooleanField(
        label='Habilitar Autenticação com Gov.BR',
        help_text='É necessário configurar os tokens e habilitar a plataforma Notifica para envio dos códigos de verificação na assinatura de documentos',
        required=False,
    )

    # Exige duplo fator para Login Gov.BR
    exige_duplo_fator_autenticacao_govbr = forms.BooleanField(
        label='Exigir Duplo Fator na Autenticação com Gov.BR',
        help_text='Será obrigatório usar duplo fator na autenticação com Gov.BR',
        required=False,
    )

    # Nível mínimo de confiabilidade para Login Gov.BR
    NIVEL_BRONZE = '1'
    NIVEL_PRATA = '2'
    NIVEL_OURO = '3'
    NIVEL_CHOICES = [
        (NIVEL_BRONZE, 'Nível Bronze'),
        (NIVEL_PRATA, 'Nível Prata'),
        (NIVEL_OURO, 'Nível Ouro'),
    ]
    nível_minimo_para_autenticacao_govbr = forms.ChoiceField(
        label='Nível mínimo para Autenticação com Gov.BR',
        help_text='Definir qual será o nível mínimo da Conta Gov.BR para autenticação',
        choices=NIVEL_CHOICES,
        required=False,
    )

    # Autenticação com Duplo Fator de Verificação - OTP
    permite_autenticacao_duplo_fator = forms.BooleanField(
        label='Permite utilizar o Duplo Fator de Autenticação',
        help_text='Caso esteja desabilitado não será solicitada a validação do código de verificação de duplo fator',
        required=False,
    )

    texto_politica_email = forms.CharField(
        label='Política de Utilização de e-mail institucional, acadêmico e escolar',
        help_text='Este texto será exibido na tela de escolha dos emails do SUAP',
        widget=TinyMCE(attrs={'class': 'tinymce', 'style': 'width: 100%;  min-height: 600px;'}),
        required=False,
    )

    biometria_expiracao = forms.IntegerField(label='Expiração do autocadastro da biometria, em dias', required=True)

    nao_exibir_matricula_userexterno_profile = forms.BooleanField(
        label='Desabilitar exibição de matrícula de pessoas/usuários externos?',
        help_text='Marque esta opção caso a matrícula seja formada de informações pessoais e não deseje exibi-la no perfil pop-up.',
        required=False,
    )
    nao_exibir_matricula_prestador_profile = forms.BooleanField(
        label='Desabilitar exibição de matrícula de prestadores de serviço?',
        help_text='Marque esta opção caso a matrícula seja formada de informações pessoais e não deseje exibi-la no perfil pop-up.',
        required=False,
    )

    tema_padrao_usuario_autenticado = forms.ChoiceField(
        label='Tema padrão para usuários autenticados',
        help_text='Definir qual o tema padrão que será utilizado caso um usuário autenticado não tenha escolhido nenhum tema.',
        choices=Preferencia.TEMA_CHOICES,
        required=False,
    )

    tema_telas_anonimas = forms.ChoiceField(
        label='Tema para telas anônimas do suap',
        help_text='Definir qual o tema da telas anônimas do suap',
        choices=Preferencia.TEMA_TELAS_ANONIMAS_CHOICES,
        required=False,
    )

    def clean(self):
        cleaned_data = super().clean()

        return cleaned_data


class PensionistaForm(forms.ModelFormPlus):
    class Meta:
        model = Pensionista
        fields = ('matricula', 'numero_processo', 'representante_legal', 'grau_parentesco', 'data_inicio_pagto_beneficio', 'data_fim_pagto_beneficio')


class ConfiguracaoFormBase(forms.FormPlus):
    """
    É a superclasse do formulário de Configuração e trata a sincronia
    do form com o banco de dados.
    """

    TITLE = 'Configuração do SUAP'

    def __init__(self, *args, **kwargs):
        # Definindo os valores iniciais dos campos
        for obj in Configuracao.objects.all():
            field_name = obj.chave
            if field_name in self.base_fields:
                field = self.base_fields[field_name]
                if hasattr(field, 'queryset'):
                    valor = obj.valor
                elif issubclass(self.base_fields[field_name].__class__, DateField) and obj.valor:
                    valor = datetime.datetime.strptime(obj.valor, '%Y-%m-%d').date()
                elif issubclass(self.base_fields[field_name].__class__, FileField) and obj.valor:
                    obj.url = default_storage.url(obj.valor)
                    valor = obj
                else:
                    valor = obj.valor
                field.initial = valor
        super().__init__(*args, **kwargs)

    def save(self):
        with transaction.atomic():
            for nome, valor in list(self.cleaned_data.items()):
                chave = getattr(self.fields[nome], '_config_key', nome)
                if hasattr(valor, 'file'):
                    relative_path = f'configuracao/{valor.name}'
                    file_name = default_storage.save(relative_path, valor)
                    valor = file_name
                elif isinstance(valor, Configuracao):
                    continue
                elif hasattr(valor, '__iter__') and not isinstance(valor, str):  # queryset or any iterable
                    valor = ','.join([str(getattr(v, 'pk', v)) for v in valor])
                else:
                    valor = str(getattr(valor, 'pk', valor or ''))
                Configuracao.objects.update_or_create(
                    app=self.fields[nome]._app, chave=chave, defaults={'valor': valor, 'descricao': self.__class__.base_fields[nome].label}
                )
        get_logo_instituicao_file_path()
        get_logo_instituicao_fundo_transparente_file_path()
        Configuracao.clear_cache()


def __add_prefix_to_fields(klass, prefix):
    """
    Apenas retorna a lista de campos com o nome formatado com o prefixo
    """
    new_base_fields = OrderedDict()
    for name, field in list(klass.base_fields.items()):
        new_base_fields[f'{prefix}__{name}'] = field
    return new_base_fields


def ConfiguracaoFormFactory(selected=None, only=None):
    """
    Monta o formulário para configuração de acordo com ConfiguracaoForm definidos nas apps em INSTALLED_APPS
    """
    apps = []
    for app in settings.INSTALLED_APPS:
        try:
            mod = __import__(f'{app}.forms', fromlist=['ConfiguracaoForm'])
            assert mod.ConfiguracaoForm
        except AttributeError:
            continue
        except ImportError:
            continue
        if only and app not in only:
            continue
        apps.append(app)

    bases = [ConfiguracaoFormBase]
    fieldsets = []
    apps.sort()
    for app in apps:
        mod = __import__(f'{app}.forms', fromlist=['ConfiguracaoForm'])
        cls = mod.ConfiguracaoForm
        if selected and app != selected:
            continue
        bases.append(cls)
        # Mecanismo usado para identificar a app do field
        for field in list(cls.base_fields.values()):
            field._app = app

        # Agrupando os campos de acordo com suas respectivas apps
        fieldsets.append((f'Aplicação {app.capitalize()}', {'fields': list(cls.base_fields.keys())}))

    class FormClass(*bases):
        __metaclass__ = MetaFormPlus

    FormClass.fieldsets = fieldsets
    FormClass.apps = apps

    return FormClass


class PrestadorServicoForm(forms.ModelFormPlus):
    nome_usual = forms.ChoiceField(label='Nome Usual', required=False, help_text='Nome que será exibido no SUAP')
    nome_registro = forms.CharField(label='Nome de Registro', required=True, help_text='Nome que consta no registro de Nascimento')
    nome_social = forms.CharField(label='Nome Social', required=False)
    sexo = forms.ChoiceField(label='Sexo', required=True, choices=[['M', 'Masculino'], ['F', 'Feminino']])
    nacionalidade = forms.ChoiceField(choices=Nacionalidade.get_choices())
    cpf = forms.BrCpfField(required=False)
    passaporte = forms.CharField(label='Nº do Passaporte', required=False, help_text='Esse campo é obrigatório para estrangeiros. Ex: BR123456')
    pais_origem = forms.ModelChoiceFieldPlus(
        Pais.objects.all(),
        label='País de Origem',
        required=False,
        help_text='Obrigatório para estrangeiros sem CPF: o passaporte vale junto com o país emissor.',
    )
    email_secundario = forms.EmailField(label='Email Pessoal')
    confirma_email = forms.EmailField(label='Confirmação de E-mail')
    justificativa_cadastro = forms.ModelChoiceField(label='Perfil', queryset=JustificativaUsuarioExterno.objects.filter(ativo=True), required=True)
    username = forms.CharField(required=False)  # Só é visível para super usuarios na edição
    tem_digital_fraca = forms.BooleanField(
        label='Permitir registro de ponto sem impressão digital',
        required=False,
        help_text='Pessoas com impressão digital fraca devem ter essa opção marcada',
    )

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['pais_origem'].initial = self.instance.pessoa_fisica.pais_origem
            choices = get_choices_nome_usual(self.instance.pessoa_fisica.nome)
            self.fields['nome_usual'].choices = choices
            self.fields['nome_usual'].required = True
            self.fields['nome_registro'].initial = self.instance.pessoa_fisica.nome_registro
            self.fields['nome_social'].initial = self.instance.pessoa_fisica.nome_social
            self.fields['nome_usual'].initial = self.instance.pessoa_fisica.nome_usual
            self.fields['sexo'].initial = self.instance.pessoa_fisica.sexo
            self.fields['nacionalidade'].initial = self.instance.pessoa_fisica.nacionalidade
            self.fields['tem_digital_fraca'].initial = self.instance.pessoa_fisica.tem_digital_fraca
            self.fields['cpf'].initial = self.instance.pessoa_fisica.cpf
            self.fields['email_secundario'] = ReadOnlyField(label='Email Pessoal')
            self.fields['email_secundario'].initial = self.instance.email_pessoal
            del self.fields['confirma_email']
            travar_documentos_na_edicao(self, self.instance.pessoa_fisica)
            if self.request.user.has_perm('rh.pode_editar_email_secundario_prestador'):
                self.fields[
                    'email_secundario'
                ].help_text = f'Clique <a href="/comum/atualizar_email_secundario/{self.instance.get_vinculo().pk}/">aqui</a> para editar o email.'

    class Meta:
        model = PrestadorServico
        fields = ('ativo', 'justificativa_cadastro')

    def clean_email_secundario(self):
        email_secundario = self.cleaned_data.get('email_secundario')
        if not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(
            email_secundario
        ):
            self.add_error(
                'email_secundario',
                f'O email secundário não pode ser um email institucional dos seguintes domínios: {Configuracao.get_valor_por_chave("comum", "dominios_institucionais")}',
            )
        return email_secundario.strip()

    def clean_confirma_email(self):
        confirma_email = self.cleaned_data.get('confirma_email')
        if not confirma_email:
            return confirma_email
        return confirma_email.strip()

    def clean(self):
        cleaned_data = super().clean()
        nacionalidade = cleaned_data.get('nacionalidade')
        cpf = cleaned_data.get('cpf')
        passaporte = cleaned_data.get('passaporte')
        email = cleaned_data.get('email_secundario')
        confirma_email = cleaned_data.get('confirma_email')

        if confirma_email and email != confirma_email:
            self.add_error('confirma_email', 'E-mails informados não são iguais!')

        try:
            eh_estrangeiro = int(nacionalidade) == Nacionalidade.ESTRANGEIRO
        except Exception:
            eh_estrangeiro = False

        if not eh_estrangeiro:
            if not cpf:
                self.add_error('cpf', 'O campo CPF é obrigatório para nacionalidades brasileiras.')
            qs = PrestadorServico.objects.filter(pessoa_fisica__cpf=cpf)
            if self.instance:
                qs = qs.exclude(id=self.instance.pk)
            if qs.exists():
                self.add_error('cpf', 'Este CPF já está sendo usado por outro prestador.')
        else:
            self._validar_passaporte(cpf, passaporte, cleaned_data.get('pais_origem'))

        if eh_estrangeiro and not cpf:
            username = PrestadorServico.matricula_do_passaporte(passaporte, cleaned_data.get('pais_origem'))
            campo_erro = 'passaporte'
        else:
            username = PrestadorServico.gerar_matricula(cpf)
            campo_erro = 'cpf'
        if not self.instance.pk and User.objects.filter(username=username).exists():
            self.add_error(campo_erro, f'O usuário {username} já existe.')
        recusar_cadastro_de_prestador(self)  # antes do super().clean(), que levanta se já houver erro de campo
        return super().clean()

    def _validar_passaporte(self, cpf: str | None, passaporte: str | None, pais: Pais | None) -> None:
        """Estrangeiro: exige o passaporte e, sem CPF, o país emissor; recusa o par passaporte+país de outro prestador."""
        if not passaporte:
            self.add_error('passaporte', 'O campo Passaporte é obrigatório para nacionalidades estrangeiras.')
            return
        if not cpf and not pais:
            self.add_error('pais_origem', 'Informe o país de origem do passaporte.')
        if PrestadorServico.objects.filter(filtro_par_passaporte(passaporte, pais, 'pessoa_fisica__')).exclude(id=self.instance.pk).exists():
            self.add_error('passaporte', 'Este passaporte já está sendo usado por outro prestador.')
        recusar_passaporte_de_outra_pessoa(self, cpf, passaporte, pais)


class OcupacaoPrestadorForm(forms.ModelFormPlus):
    class Meta:
        model = OcupacaoPrestador
        exclude = ('prestador', 'atualizado_por', 'atualizado_em')

    def __init__(self, *args, **kwargs):
        self.prestador = kwargs.pop('prestador')
        self.instance = kwargs.get('instance')
        super().__init__(*args, **kwargs)
        self.fields['ocupacao'].label = 'Ocupação'
        self.fields['setor_suap'].queryset = Setor.objects.suap_ativos()
        if self.instance.pk:
            self.fields['ocupacao'] = ReadOnlyField()
            self.fields['ocupacao'].initial = self.instance.ocupacao
            self.fields['ocupacao'].widget.display_value = self.instance.ocupacao.descricao
            self.fields['empresa'] = ReadOnlyField()
            self.fields['empresa'].initial = self.instance.empresa
            self.fields['empresa'].widget.display_value = self.instance.empresa
            self.fields['data_inicio'].widget.attrs['readonly'] = 'readonly'

    def clean_data_fim(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        if data_inicio and data_fim and data_fim < data_inicio:
            raise ValidationError('A data final deve ser posterior à data de início.')
        return data_fim

    def clean_ocupacao(self):
        ocupacao = self.cleaned_data.get('ocupacao')
        if (
            OcupacaoPrestador.objects.filter(prestador=self.prestador, ocupacao=ocupacao, data_fim__gte=datetime.date.today())
            .exclude(pk=self.instance.pk)
            .exists()
        ):
            raise ValidationError(f'Já existe uma ocupação de {ocupacao.descricao} ativa para este prestador.')
        return ocupacao

    def processar(self):
        try:
            if self.instance.pk:
                ocupacao_prestador = self.instance
            else:
                ocupacao_prestador = OcupacaoPrestador()

            ocupacao_prestador.prestador = self.prestador
            ocupacao_prestador.ocupacao = self.cleaned_data.get('ocupacao')
            ocupacao_prestador.empresa = self.cleaned_data.get('empresa')
            ocupacao_prestador.data_inicio = self.cleaned_data.get('data_inicio')
            ocupacao_prestador.data_fim = self.cleaned_data.get('data_fim')
            ocupacao_prestador.setor_suap = self.cleaned_data.get('setor_suap')
            ocupacao_prestador.atualizado_por = self.request.user.get_vinculo()
            # Atualiza o setor do Prestador para o setor da ocupação adicionada
            self.prestador.setor = self.cleaned_data.get('setor_suap')
            self.prestador.empresa = self.cleaned_data.get('empresa')
            ocupacao_prestador.save()
        except Exception as e:
            capture_exception(e)


class EncerrarOcupacaoPrestadorForm(forms.FormPlus):
    INFO = 'Ao encerrar a ocupação do prestador a data fim da ocupação será alterada para a data de ontem.'
    senha = forms.PasswordField()


# TODO: rever se o documento controle é para ficar dentro de comum
def DocumentoControleAdminFormFactory(request, obj):
    pessoa_fisica = request.user.get_profile()
    s = request.user.get_relacionamento()
    # Documento suportado hj no ifrn é apenas o cracha
    documento_suportado = DocumentoControleTipo.objects.get(identificador=DocumentoControleTipo.CRACHA)

    class DocumentoBaseForm(forms.ModelFormPlus):
        class Meta:
            model = DocumentoControle
            fields = ('documento_tipo',)
            exclude = ()

        class Media:
            js = ('/static/comum/js/solicitacao_documento.js',)

        def __init__(self, *args, **kwargs):
            self.instance = kwargs.get('instance')
            super().__init__(*args, **kwargs)

            fields_removidos = self.fields.keys() - self.get_fields()
            for field_removido in fields_removidos:
                self.fields.pop(field_removido)

            # Pode solicitar apenas os documentos suportados pelo seu campus (que exista algum campus que imprima o documento);
            uo_usuario = get_uo(request.user)
            doc_suportados = []
            for conf in ConfiguracaoImpressaoDocumento.objects.all():
                if conf.relacao_impressao.filter(id=uo_usuario.id).exists():
                    doc_suportados += [doc.id for doc in conf.tipos_documento.all()]

            self.fields['documento_tipo'].queryset = DocumentoControleTipo.objects.filter(id__in=doc_suportados)
            documento_tipo = documento_suportado.id
            if documento_tipo:
                self.fields['documento_tipo'].initial = documento_tipo

            # Solicitante
            if 'solicitante_vinculo' in self.fields:
                self.fields['solicitante_vinculo'].widget = forms.HiddenInput()
                if request.user.has_perm('comum.change_documentocontrole'):
                    self.fields['solicitante_vinculo'].widget = AutocompleteWidget(
                        search_fields=Vinculo.SEARCH_FIELDS, help_text='Você pode selecionar outro solicitante.'
                    )

                # verificando a abrangência do documento
                if documento_suportado:
                    abrangencia = documento_suportado.abrangencia.values_list('codigo', flat=True)
                    self.fields['solicitante_vinculo'].queryset = Vinculo.objects.filter(
                        tipo_relacionamento__model='servidor',
                        id_relacionamento__in=(Servidor.objects.filter(situacao__codigo__in=abrangencia).values_list('id', flat=True)),
                    )
                if self.instance and self.instance.id:
                    self.fields['solicitante_vinculo'].initial = self.instance.solicitante_vinculo.id
                else:
                    self.fields['solicitante_vinculo'].initial = request.user.get_vinculo()

            # Justificativa
            if 'justificativa' in self.fields:
                self.fields['justificativa'].widget = forms.Textarea(attrs={'rows': 2, 'cols': 20})
                if self.instance:
                    self.fields['justificativa'].initial = self.instance.justificativa

        @staticmethod
        def get_fields():
            return ('documento_tipo',)

        def clean(self) -> None:
            documento_tipo = self.cleaned_data.get('documento_tipo')
            solicitante_vinculo = self.cleaned_data.get('solicitante_vinculo')

            if not documento_tipo:
                raise ValidationError('Não foi possível identificar o tipo do documento.')

            if not solicitante_vinculo:
                raise ValidationError('Não foi possível identificar o solicitante.')

            """
            verificando se já existe uma solicitação não atendida para este tipo de documento
            """
            qs_solicitacao = DocumentoControle.objects.filter(
                solicitante_vinculo=solicitante_vinculo,
                status_solicitacao=SituacaoSolicitacaoDocumento.NAO_ATENDIDA,
                ativo=True,
                documento_tipo=documento_tipo,
            ).exclude(pk=self.instance.id)
            if qs_solicitacao.exists():
                raise ValidationError(
                    f'PROBLEMA: Não é possível solicitar um(a) {documento_tipo.descricao} para o usuário {solicitante_vinculo.pessoa.nome} pois já existe uma solicitação pendente.'
                )

            """
            verificando se o usuário tem foto, grupo sanguíneo e fator rh cadastrado (informações necessárias para a confecção de crachá e carteira funcional)
            """
            if documento_tipo and documento_tipo.identificador in [DocumentoControleTipo.CARTEIRA_FUNCIONAL, DocumentoControleTipo.CRACHA]:
                pessoa_fisica = solicitante_vinculo.pessoa.pessoafisica
                mensagens = []
                if not solicitante_vinculo.foto:
                    mensagens.append(' - O solicitante não tem foto cadastrada.')
                if not pessoa_fisica.grupo_sanguineo:
                    mensagens.append(' - O solicitante não tem grupo sanguíneo cadastrado.')
                if not pessoa_fisica.fator_rh:
                    mensagens.append(' - O solicitante não tem fator RH cadastrado.')

                if mensagens:
                    mensagens.append(f'Procure a Gestão de Pessoas {nomenclatura.do_campus} para atualizar o cadastro do solicitante.')
                    raise ValidationError(['PROBLEMAS ENCONTRADOS:', *mensagens])

    class CrachaForm(DocumentoBaseForm):
        nome_sugerido = forms.ChoiceField(choices=(), widget=forms.Select(), required=False)

        class Meta:
            model = DocumentoControle
            fields = ('documento_tipo', 'solicitante_vinculo', 'nome_sugerido', 'nome_social', 'justificativa', 'status_solicitacao', 'ativo')

        def __init__(self, *args, **kwargs):
            self.instance = kwargs.get('instance')
            super().__init__(*args, **kwargs)

            vinculo_usuario_request = None
            if self.request and self.request.POST.get('solicitante_vinculo'):
                id_usuario_request = self.request.POST.get('solicitante_vinculo')
                vinculo_usuario_request = Vinculo.objects.get(pk=id_usuario_request)

            # Nome sugerido
            if 'nome_sugerido' in self.fields:
                nome = pessoa_fisica.nome
                if vinculo_usuario_request:
                    nome = vinculo_usuario_request.pessoa.nome
                if self.instance and self.instance.id:
                    nome = self.instance.solicitante_vinculo.pessoa.nome
                nomes = gera_nomes(nome)
                choice_nomes = [['', 'Selecione umas das opções']]
                for nome in nomes:
                    choice_nomes.append([nome, nome])
                self.fields['nome_sugerido'].choices = choice_nomes

        @staticmethod
        def get_fields():
            campos = ('documento_tipo', 'solicitante_vinculo', 'nome_sugerido', 'nome_social', 'justificativa')
            if request.user.has_perm('comum.change_documentocontrole'):
                campos = (*campos, 'status_solicitacao', 'ativo')
            return campos

        def clean(self):
            super().clean()

            nome_sugerido = self.cleaned_data.get('nome_sugerido')
            nome_social = self.cleaned_data.get('nome_social')

            if (nome_social is None or nome_social == '') and (nome_sugerido is None or nome_sugerido == ''):
                raise ValidationError('Por favor, selecione um nome sugerido ou descreva um nome social.')

            return self.cleaned_data

    # verificando se o usuário é um servidor ativo, um estagiário, um professor substituto ou temporário
    if isinstance(s, Servidor):
        if (s.situacao.codigo,) in documento_suportado.abrangencia.values_list('codigo'):
            return CrachaForm
        else:
            messages.error(
                request, 'Você não pode solicitar um crachá, pois sua Situação Funcional não está habilitada para esse tipo de solicitação.'
            )
    elif isinstance(s, PrestadorServico):
        return CrachaForm

    return DocumentoBaseForm


class ConfiguracaoImpressaoDocumentoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(),
        label='Unidade Organizacional',
        required=True,
    )
    relacao_impressao = forms.ModelMultipleChoiceField(
        queryset=UnidadeOrganizacional.objects.suap(),
        label='Relação de Impressão',
        widget=FilteredSelectMultiplePlus('', True),
        required=True,
        help_text=f'Escolha para quais {nomenclatura.campi} {nomenclatura.o_campus} acima selecionado poderá imprimir.',
    )
    tipos_documento = forms.ModelMultipleChoiceField(
        queryset=DocumentoControleTipo.objects, label='Tipos de Documentos', widget=CheckboxSelectMultiplePlus()
    )

    class Meta:
        model = ConfiguracaoImpressaoDocumento
        exclude = ()


class DocumentoControleTipoForm(forms.ModelFormPlus):
    identificador = forms.ChoiceField(label='Documento', choices=DocumentoControleTipo.TIPO_DOCUMENTO_CHOICES, widget=forms.Select(), required=True)
    abrangencia = forms.ModelMultipleChoiceField(
        queryset=Situacao.objects, label='Abrangência', widget=FilteredSelectMultiplePlus('', True), required=True
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    class Meta:
        model = DocumentoControleTipo
        fields = ('identificador', 'abrangencia')


class RejeitarSolicitacaoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoControleHistorico
        fields = ('motivo',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo'].widget = forms.Textarea(attrs={'rows': 2, 'cols': 20})


class SetorAdicionarTelefoneForm(forms.FormPlus):
    numero = forms.BrTelefoneField(label='Número telefônico', required=False)
    ramal = forms.CharField(max_length=5, help_text='O ramal é obrigatório mesmo para telefones sem "número telefônico".')
    observacao = forms.CharField(label='Observação', required=False, max_length=50)

    def clean_ramal(self):
        if not self.cleaned_data['ramal'].isdigit():
            raise forms.ValidationError('Certifique-se de que o ramal é um número')
        return self.cleaned_data['ramal']


class SetorEditarEmailForm(forms.ModelFormPlus):
    class Meta:
        model = Setor
        fields = ['email']


class InscricaoFiscalForm(forms.ModelFormPlus):
    class Meta:
        model = InscricaoFiscal
        exclude = ['servidor']

    def clean_data_inicio_servico_na_instituicao(self):
        data = self.cleaned_data['data_inicio_servico_na_instituicao']
        if data > datetime.date.today():
            raise forms.ValidationError('A data deve estar no passado.')
        return data


class ExtracaoForm(forms.FormPlus):
    arquivo_1 = forms.FileFieldPlus(required=True, label='Arquivo Ref')
    arquivo_2 = forms.FileFieldPlus(required=True, label='Arquivo Siafe')
    campo_busca = forms.CharField(label='Buscar item:', required=False)
    METHOD = 'post'
    ACTION = '/comum/ver_arquivo_siafi/'
    TITLE = 'Visualizar Arquivos SIAFI'
    VALUE = 'Visualizar'
    ENCTYPE = 'multipart/form-data'


class SetorTelefoneForm(forms.ModelFormPlus):
    numero = forms.BrTelefoneField(max_length=14, label='Número', widget=BrTelefoneWidget())

    class Meta:
        model = SetorTelefone
        exclude = ()


class ContatoEmergenciaForm(forms.ModelFormPlus):
    nome_contato = forms.CharFieldPlus(label='Nome do Contato', required=True, max_length=200)
    telefone = forms.BrTelefoneField(label='Telefone', required=True, widget=BrTelefoneWidget())

    class Meta:
        model = ContatoEmergencia
        exclude = ('pessoa_fisica',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def clean(self):
        if (
            not self.instance.pk
            and ContatoEmergencia.objects.filter(pessoa_fisica=self.instance.pessoa_fisica, telefone=self.cleaned_data.get('telefone')).exists()
        ):
            raise forms.ValidationError('O número de telefone já foi adicionado aos contatos de emergência desta pessoa.')


class UploadArquivoForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus()
    descricao = forms.CharField(label='Descrição', required=True)
    data = forms.DateFieldPlus(label='Data', required=True, help_text='Data em que a foto foi tirada no formato dd/mm/aaaa')


class PredioForm(forms.ModelFormPlus):
    class Meta:
        model = Predio
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.is_superuser:
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)

        self.fields['estrutura'].queryset = EstruturaPredio.objects.filter(ativo=True)
        self.fields['cobertura'].queryset = CoberturaPredio.objects.filter(ativo=True)
        self.fields['vedacao'].queryset = VedacaoPredio.objects.filter(ativo=True)
        self.fields['sistema_sanitario'].queryset = SistemaSanitarioPredio.objects.filter(ativo=True)
        self.fields['sistema_abastecimento'].queryset = SistemaAbastecimentoPredio.objects.filter(ativo=True)
        self.fields['sistema_alimentacao_eletrica'].queryset = SistemaAlimentacaoEletricaPredio.objects.filter(ativo=True)
        self.fields['sistema_protecao_descarga_atmosferica'].queryset = SistemaProtecaoDescargaAtmosfericaPredio.objects.filter(ativo=True)
        self.fields['acabamento_externo'].queryset = AcabamentoExternoPredio.objects.filter(ativo=True)


class ObraForm(forms.ModelFormPlus):
    class Meta:
        model = Obra
        exclude = ()

    class Media:
        js = ('/static/comum/js/CadastrarObra.js',)


class SalaForm(forms.ModelFormPlus):
    class Meta:
        model = Sala
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        servidores_ativos = Servidor.objects.ativos().values_list('pessoa_fisica__id', flat=True)
        if self.request.user.has_perm('comum.change_sala'):
            self.fields['avaliadores_de_agendamentos'].queryset = User.objects.filter(vinculo__pessoa_id__in=servidores_ativos)
            if not self.request.user.is_superuser:
                self.fields['predio'].queryset = Predio.objects.filter(uo=get_uo(self.request.user)).order_by('nome')

        self.fields['instalacao_eletrica'].queryset = InstalacaoEletricaSala.objects.filter(ativo=True)
        self.fields['instalacao_logica'].queryset = InstalacaoLogicaSala.objects.filter(ativo=True)
        self.fields['instalacao_hidraulica'].queryset = InstalacaoHidraulicaSala.objects.filter(ativo=True)
        self.fields['instalacao_gases'].queryset = InstalacaoGasesSala.objects.filter(ativo=True)
        self.fields['climatizacao'].queryset = ClimatizacaoSala.objects.filter(ativo=True)
        self.fields['acabamento_parede'].queryset = AcabamentoParedeSala.objects.filter(ativo=True)
        self.fields['piso'].queryset = PisoSala.objects.filter(ativo=True)
        self.fields['forro'].queryset = ForroSala.objects.filter(ativo=True)
        self.fields['esquadrias'].queryset = EsquadriasSala.objects.filter(ativo=True)


class AlterarSenhaForm(forms.FormPlus):
    recaptcha = ReCaptchaField(label='Confirmar Solicitação de Alteração')


class SoliticarTrocarSenhaForm(forms.FormPlus):
    username = forms.CharField(
        label='Usuário',
        help_text='Informe sua matrícula caso seja servidor ou aluno, seu CPF se for prestador de serviço ou usuário externo, ou, se for estrangeiro sem CPF, o país e o passaporte (ex.: ARG-AB123456; nos cadastros antigos, só o passaporte).',
        required=True,
    )
    cpf_passaporte = forms.CharField(
        label='CPF/Passaporte',
        help_text='Brasileiros ou Naturalizados devem informar o CPF. Estrangeiros devem informar o Passaporte (Formato: BR123456).',
        required=True,
    )
    recaptcha = ReCaptchaField(label='Verificação')

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        cpf_passaporte = cleaned_data.get('cpf_passaporte')
        username = cleaned_data.get('username')
        passaporte = formatar_passaporte(cpf_passaporte)
        # sem letra nem dígito, passaporte=None viraria IS NULL e casaria qualquer usuário sem passaporte
        do_documento = Q(vinculo__pessoa__pessoafisica__cpf=mask_cpf(cpf_passaporte)) | (
            Q(vinculo__pessoa__pessoafisica__passaporte=passaporte) if passaporte else Q(pk__in=[])
        )
        user = User.objects.filter(username=username).filter(do_documento).first()
        if not user:
            if username and len(username) == 14:
                username = username.replace('.', '').replace('-', '')
                self.cleaned_data['username'] = username
                user = User.objects.filter(username=username).filter(do_documento).first()
                if not user:
                    raise forms.ValidationError('Nenhum usuário encontrado com os dados especificados.')
            else:
                raise forms.ValidationError('Nenhum usuário encontrado com os dados especificados.')

        vinculo_usuario = user.get_vinculo()
        if not vinculo_usuario or not vinculo_usuario.email_pessoal:
            raise forms.ValidationError('Usuário sem email pessoal cadastrado.')

        # Se for estrangeiro, não verifica se tem conta no AD, no entanto pode ser que ele tenha conta também
        if is_ldap_enabled() and not user.eh_estrangeiro and not user.get_vinculo().get_usuario_ldap(attrs=['dn']):
            raise forms.ValidationError(f'Usuário não tem conta sincronizada com o AD. Favor entrar em contato com a TI {nomenclatura.do_campus}.')
        return self.cleaned_data


class BuscaUsuarioGrupoForm(forms.FormPlus):
    nome = forms.CharField(label='Filtrar por Nome/Matrícula/CPF', required=False, widget=forms.TextInput(attrs={'size': 20}))
    grupo = forms.ModelChoiceField(required=False, queryset=Group.objects.all(), widget=forms.HiddenInput())
    campus = forms.ModelChoiceField(required=False, queryset=UnidadeOrganizacional.objects.campi().all(), label=f'Filtrar por {nomenclatura.campus}')


class GrupoGerenciamentoForm(forms.ModelFormPlus):
    grupo_gerenciador = forms.ModelChoiceFieldPlus(label='Grupo Gerenciador', queryset=Group.objects.all(), widget=AutocompleteWidget())
    grupos_gerenciados = forms.ModelMultipleChoiceField(label='Grupos', queryset=Group.objects.all(), widget=FilteredSelectMultiple('', True))

    class Meta:
        model = GerenciamentoGrupo
        exclude = ()


class AdicionarUsuarioGrupoForm(forms.FormPlus):
    user = forms.MultipleModelChoiceFieldPlus(
        queryset=User.objects.filter(Q(eh_servidor=True) | Q(eh_prestador=True), is_active=True),
        label='Usuário',
        help_text='Informe parte do Nome ou Matrícula ou CPF ou E-mail Institucional',
    )


def AdicionarUsuarioGrupoFormFactory(usuario, so_local, grupo=None):
    class AdicionarUsuarioGrupoForm(forms.FormPlus):
        user = forms.MultipleModelChoiceFieldPlus(
            queryset=User.objects.filter(Q(eh_servidor=True) | Q(eh_prestador=True), is_active=True),
            label='Usuário',
            help_text='Informe parte do Nome ou Matrícula ou CPF ou E-mail Institucional',
        )
        prazo = forms.DateFieldPlus(
            label='Prazo', help_text='O usuário será automaticamente removido do grupo ao logar no Suap ao fim do prazo informado.', required=False
        )

        # limitado a 300 por conta que a view adiciona texto ao motivo antes de salvar
        # - um dos textos que pode ser adicionado é o nome do grupo
        #   - ele sozinho pode ter 150
        # o limite do motivo no model é 550
        motivo = forms.CharField(
            label='Motivo',
            help_text='Informe o motivo pelo qual está inserindo este(s) usuário(s) no grupo.',
            widget=forms.Textarea(attrs={'rows': '50', 'cols': '100', 'maxlength': '300'}),
            max_length=300,
        )
        checagem_obrigatoria = forms.BooleanField(
            label='Confirmo que desejo adicionar este(s) usuário(s) ao grupo, compreendendo todas as atribuições, permissões e acessos relacionados, e que verifiquei que essas atribuições estão em acordo com as responsabilidades do(s) usuário(s) a ser(em) adicionado(s).',
            widget=forms.CheckboxInput,
            required=True,
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            if grupo and ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo, ativa=True).exists():
                self.fields['prazo'].required = True
            if so_local:
                self.fields['user'].queryset = User.objects.filter(
                    vinculo__tipo_relacionamento__model__in=['prestadorservico', 'servidor'],
                    is_active=True,
                    vinculo__setor__uo=usuario.get_relacionamento().setor.uo,
                )

        def clean_prazo(self):
            prazo = self.cleaned_data['prazo']
            if prazo and prazo < datetime.date.today():
                raise forms.ValidationError('O prazo deve ser maior que hoje.')
            return prazo

    return AdicionarUsuarioGrupoForm


def VincularSetorUsuarioGrupoFormFactory(usuario_grupo):
    class VincularSetorUsuarioGrupoForm(forms.FormPlus):
        setores = forms.MultipleModelChoiceFieldPlus(
            required=False,
            queryset=Setor.objects.suap_ativos().all(),
            help_text='Informe o setor vinculado a esse usuário para o respectivo grupo',
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['setores'].initial = usuario_grupo.setores.all().values_list('id', flat=True)

    return VincularSetorUsuarioGrupoForm


class ComentarioForm(forms.FormPlus):
    texto = forms.CharField(label='Texto', widget=forms.Textarea())


class AutenticarDocumentoForm(forms.FormPlus):
    tipo = forms.ChoiceField(label='Tipo de Documento', choices=[])
    data_emissao = forms.DateFieldPlus(label='Data da Emissão')
    codigo_verificador = forms.CharFieldPlus(label='Código Verificador', min_length=6)
    recaptcha = ReCaptchaField(label='')
    tipo_objeto = forms.IntegerField(label='Informação Auxiliar', required=False, widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo'].choices = [['', '']] + [
            [tipo, tipo] for tipo in RegistroEmissaoDocumento.objects.order_by('tipo').values_list('tipo', flat=True).distinct()
        ]

    def clean_tipo_objeto(self):
        registros = self.get_registros()
        if registros.count() > 1:
            content_types = ContentType.objects.filter(pk__in=registros.values_list('tipo_objeto', flat=True))
            self.fields['tipo_objeto'] = forms.ModelChoiceField(content_types, label='Informação Auxiliar', required=False)
            if not self.cleaned_data.get('tipo_objeto'):
                raise forms.ValidationError('Este campo é obrigatório')
        return self.cleaned_data.get('tipo_objeto')

    def get_registros(self):
        data_emissao = self.cleaned_data.get('data_emissao')
        tipo = self.cleaned_data.get('tipo')
        codigo_verificador = self.cleaned_data.get('codigo_verificador')
        if data_emissao and tipo and codigo_verificador:
            registros = RegistroEmissaoDocumento.objects.filter(tipo=tipo, codigo_verificador__startswith=codigo_verificador)
            registros = registros.filter(data_emissao__gte=data_emissao, data_emissao__lte=data_emissao + datetime.timedelta(1))
            return registros
        return RegistroEmissaoDocumento.objects.none()

    def processar(self):
        registros = self.get_registros()
        tipo_objeto = self.cleaned_data.get('tipo_objeto')
        if tipo_objeto:
            return registros.filter(tipo_objeto=tipo_objeto).first()
        return registros.first()


class SolicitacaoReservaSalaForm(forms.ModelFormPlus):
    sala = ReadOnlyField(label='Sala')
    capacidade = ReadOnlyField(label='Capacidade da sala (em número de pessoas)')
    interessados_vinculos = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.all(),
        label='Interessados',
        required=False,
        help_text='Informe aqui as pessoas interessadas nessa solicitação; elas serão notificadas por email.',
    )

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    ('solicitante'),
                    ('sala', 'capacidade'),
                    ('recorrencia'),
                    ('data_inicio', 'data_fim'),
                    ('hora_inicio', 'hora_fim'),
                    'justificativa',
                    'interessados_vinculos',
                    'anexo',
                )
            },
        ),
        (
            'Dias da Semana',
            {
                'fields': (
                    (
                        'recorrencia_segunda',
                        'recorrencia_terca',
                        'recorrencia_quarta',
                        'recorrencia_quinta',
                        'recorrencia_sexta',
                        'recorrencia_sabado',
                        'recorrencia_domingo',
                    ),
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['sala'].initial = self.instance.sala
        self.fields['sala'].widget.display_value = str(self.instance.sala)
        self.fields['capacidade'].initial = self.instance.sala.capacidade
        self.fields['capacidade'].widget.display_value = self.instance.sala.capacidade or '-'
        self.fields['solicitante'].queryset = self.fields['solicitante'].queryset.filter(is_active=True, is_staff=True)
        if not self.request.user.groups.filter(name='Avaliador de Sala').exists():
            del self.fields['solicitante']

    class Meta:
        model = SolicitacaoReservaSala
        fields = (
            'solicitante',
            'sala',
            'recorrencia',
            'data_inicio',
            'data_fim',
            'hora_inicio',
            'hora_fim',
            'justificativa',
            'interessados_vinculos',
            'anexo',
            'recorrencia_segunda',
            'recorrencia_terca',
            'recorrencia_quarta',
            'recorrencia_quinta',
            'recorrencia_sexta',
            'recorrencia_sabado',
            'recorrencia_domingo',
        )

    class Media:
        js = ('/static/comum/js/SolicitacaoReservaSalaForm.js',)

    def clean(self):
        cleaned_data = super().clean()
        recorrencia = cleaned_data.get('recorrencia')
        if not self.errors:
            data_inicio = cleaned_data.get('data_inicio')
            data_fim = cleaned_data.get('data_fim')
            hora_inicio = cleaned_data.get('hora_inicio')
            hora_fim = cleaned_data.get('hora_fim')
            sala = cleaned_data.get('sala')

            if data_fim < data_inicio:
                self.errors['data_fim'] = ['Data de Fim deve ser maior ou igual a Data de Início.']
                del cleaned_data['data_fim']

            if hora_inicio > hora_fim and not (data_inicio < data_fim and recorrencia == SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO):
                self.errors['hora_fim'] = ['Hora de Fim deve ser maior ou igual a Hora de Início.']
                del cleaned_data['hora_fim']

            if data_inicio and hora_inicio and datetime.datetime.combine(data_inicio, hora_inicio) <= datetime.datetime.now():
                self.errors['data_inicio'] = ['Data/Hora de Início deve ser maior ou igual a Data/Hora da solicitação.']
                del cleaned_data['data_inicio']

            solicitacao = SolicitacaoReservaSala(
                recorrencia=recorrencia,
                data_inicio=data_inicio,
                data_fim=data_fim,
                hora_inicio=hora_inicio,
                recorrencia_segunda=self.cleaned_data.get('recorrencia_segunda'),
                recorrencia_terca=self.cleaned_data.get('recorrencia_terca'),
                recorrencia_quarta=self.cleaned_data.get('recorrencia_quarta'),
                recorrencia_quinta=self.cleaned_data.get('recorrencia_quinta'),
                recorrencia_sexta=self.cleaned_data.get('recorrencia_sexta'),
                recorrencia_sabado=self.cleaned_data.get('recorrencia_sabado'),
                recorrencia_domingo=self.cleaned_data.get('recorrencia_domingo'),
                hora_fim=hora_fim,
            )

            if sala.tem_conflito_reserva(solicitacao):
                self.errors['data_inicio'] = ['Sala já está reservada para a data e hora especificadas.']

            if not sala.is_agendavel():
                self.errors['sala'] = ['Sala não está disponível para agendamento.']

        if not recorrencia or recorrencia == SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO:
            cleaned_data['recorrencia_segunda'] = False
            cleaned_data['recorrencia_terca'] = False
            cleaned_data['recorrencia_quarta'] = False
            cleaned_data['recorrencia_quinta'] = False
            cleaned_data['recorrencia_sexta'] = False
            cleaned_data['recorrencia_sabado'] = False
            cleaned_data['recorrencia_domingo'] = False
        elif not (
            cleaned_data['recorrencia_segunda']
            or cleaned_data['recorrencia_terca']
            or cleaned_data['recorrencia_quarta']
            or cleaned_data['recorrencia_quinta']
            or cleaned_data['recorrencia_sexta']
            or cleaned_data['recorrencia_sabado']
            or cleaned_data['recorrencia_domingo']
        ):
            self.errors['recorrencia_segunda'] = ['Este tipo de recorrência exige a marcação de, no mínimo, um dia da semana.']

        return cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.instance.notificar_cadastro()


class SolicitacaoReservaSalaAvaliarForm(forms.ModelFormPlus):
    avaliador = ReadOnlyField(label='Avaliador')
    data_avaliacao = ReadOnlyField(label='Data da Avaliação')
    fieldsets = ((None, {'fields': (('avaliador'), ('data_avaliacao'), ('status'), ('observacao_avaliador'))}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliador'].initial = self.instance.avaliador
        self.fields['data_avaliacao'].initial = self.instance.data_avaliacao
        self.fields['data_avaliacao'].widget.display_value = localize(self.instance.data_avaliacao)
        self.fields['status'].widget.choices = (
            (SolicitacaoReservaSala.STATUS_DEFERIDA, 'Deferida'),
            (SolicitacaoReservaSala.STATUS_INDEFERIDA, 'Indeferida'),
        )

    class Meta:
        model = SolicitacaoReservaSala
        fields = ('status', 'observacao_avaliador')

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            if cleaned_data.get('status') == SolicitacaoReservaSala.STATUS_DEFERIDA:
                solicitacao = self.instance
                sala = solicitacao.sala

                if sala.tem_conflito_reserva(solicitacao):
                    self.errors['status'] = ['Sala já está reservada para a data e hora especificadas.']
                    del cleaned_data['status']

            elif cleaned_data.get('status') == SolicitacaoReservaSala.STATUS_INDEFERIDA:
                if len(cleaned_data['observacao_avaliador'].strip()) == 0:
                    self._errors['observacao_avaliador'] = self.error_class(['A observação é obrigatória para a situação indeferida.'])
                    del cleaned_data['observacao_avaliador']

        return cleaned_data

    @transaction.atomic()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        if self.instance.status == SolicitacaoReservaSala.STATUS_DEFERIDA:
            self.instance.gerar_reservas()

        self.instance.notificar_avaliacao()


class SolicitacaoReservaSalaCancelarForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_cancelamento'].required = True

    class Meta:
        model = SolicitacaoReservaSala
        fields = ('justificativa_cancelamento',)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.cancelada = True
        super().save(*args, **kwargs)
        for reserva in self.instance.reservasala_set.exclude(cancelada=True):
            reserva.cancelada_por = self.request.user
            reserva.justificativa_cancelamento = self.instance.justificativa_cancelamento
            reserva.cancelar(notificar=False)

        self.instance.notificar_cancelamento()


class IndisponibilizacaoSalaBuscarForm(forms.FormPlus):
    METHOD = 'GET'
    sala = forms.ModelChoiceField(label='Sala', queryset=Sala.ativas, required=False)

    def __init__(self, *args, **kwargs):
        indisponibilizacoes = kwargs.pop('indisponibilizacoes')
        super().__init__(*args, **kwargs)
        self.fields['sala'].queryset = Sala.ativas.filter(
            reservasala__indisponibilizacaosala__id__in=indisponibilizacoes.values_list('id', flat=True)
        ).distinct()

    def processar(self, indisponibilizacoes):
        if self.is_valid():
            sala = self.cleaned_data.get('sala')
            if sala:
                indisponibilizacoes = indisponibilizacoes.filter(sala=sala)
        return indisponibilizacoes


class RegistrarIndisponibilizacaoSalaForm(forms.ModelFormPlus):
    registrado_por = forms.ModelChoiceFieldPlus(User.objects, label='Registrado por', widget=AutocompleteWidget(readonly=True), required=False)
    data = ReadOnlyField(label='Data do Registro')
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().all(), required=False)
    predio = forms.ChainedModelChoiceField(
        Predio.objects.all(),
        label='Prédio',
        empty_label=f'Selecione {nomenclatura.campus}',
        required=False,
        obj_label='nome',
        form_filters=[('campus', 'uo_id')],
    )
    sala = forms.ChainedModelChoiceField(
        Sala.ativas,
        label='Sala',
        empty_label='Selecione o Prédio',
        obj_label='nome',
        form_filters=[('campus', 'predio__uo_id'), ('predio', 'predio_id')],
    )

    fieldsets = (
        (None, {'fields': (('registrado_por'), ('data'), ('campus'), ('predio'), ('sala'), ('data_inicio'), ('data_fim'), ('justificativa'))}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['registrado_por'].initial = self.instance.usuario
        self.fields['data'].initial = self.instance.data
        self.fields['data'].widget.display_value = localize(self.instance.data)
        self.fields['campus'].queryset = (
            UnidadeOrganizacional.objects.uo()
            .filter(predio__sala__agendavel=True, predio__sala__ativa=True, predio__sala__avaliadores_de_agendamentos=self.request.user.id)
            .distinct()
        )
        self.fields['predio'].widget.queryset = Predio.objects.filter(
            sala__agendavel=True, sala__ativa=True, sala__avaliadores_de_agendamentos=self.request.user.id
        ).distinct()
        self.fields['predio'].widget.initial = self.request.POST.get('predio')
        self.fields['sala'].widget.queryset = Sala.ativas.filter(agendavel=True, avaliadores_de_agendamentos=self.request.user.id).distinct()
        self.fields['sala'].widget.initial = self.request.POST.get('sala')

    class Meta:
        model = IndisponibilizacaoSala
        fields = ('sala', 'data_inicio', 'data_fim', 'justificativa')

    class Media:
        js = ('/static/comum/js/RegistrarIndisponibilizacaoSalaForm.js',)

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            data_inicio = cleaned_data.get('data_inicio')
            data_fim = cleaned_data.get('data_fim')
            data = self.instance.data
            sala = cleaned_data.get('sala')

            if data_fim < data_inicio:
                self.add_error('data_fim', 'Data final deve ser maior ou igual a Data inicial.')

            if data_inicio < data:
                self.add_error('data_inicio', 'Data e Hora inicial deve ser maior ou igual a Data/Hora da solicitação.')

            # RN1 Não deve existir duas agendas de salas na mesma data/hora.
            if sala.get_reservas(data_inicio, data_fim).exists():
                self.add_error('data_inicio', 'Sala já está reservada para a data e hora especificadas, exclua antes a reserva.')

            # RN2 Requisições de reserva de sala na mesa data/hora será indeferida.
            if sala.get_solicitacoes_conflitantes(data_inicio, data_fim).exists():
                self.add_error('data_inicio', 'Existem requisições de reserva para esta sala no período solicitado, indefira antes as requisições.')

            if not sala.is_agendavel():
                self.add_error('sala', 'Sala não está disponível para agendamento.')

        return cleaned_data


class ReservaSalaCancelarForm(forms.ModelFormPlus):
    class Meta:
        model = ReservaSala
        fields = ('justificativa_cancelamento',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['justificativa_cancelamento'].required = True

    def cancelar(self):
        self.instance.cancelar()


class SalaIndicadoresForm(forms.FormPlus):
    METHOD = 'GET'

    inicio = forms.DateFieldPlus(label='Data Inicial', required=True)
    final = forms.DateFieldPlus(label='Data Final', required=True)
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label=nomenclatura.campus, required=True)
    predio = forms.ChainedModelChoiceField(
        Predio.objects,
        label='Prédio',
        empty_label=f'Selecione {nomenclatura.o_campus}',
        required=False,
        obj_label='nome',
        form_filters=[('campus', 'uo_id')],
    )


class ReservaInformarOcorrenciaForm(forms.ModelFormPlus):
    class Meta:
        model = ReservaSala
        fields = ('ocorreu', 'motivo_nao_ocorreu')

    def clean(self):
        cleaned_data = super().clean()
        ocorreu = cleaned_data.get('ocorreu')
        motivo_nao_ocorreu = cleaned_data.get('motivo_nao_ocorreu')
        if ocorreu is False and not motivo_nao_ocorreu:
            self.add_error('motivo_nao_ocorreu', 'Este campo é obrigatório no caso do evento não tiver ocorrido.')

        return cleaned_data


ARQUIVOS_EXTRATOR_CHOICES = (
    ('unidadeorganizacional', 'Unidades Organizacionais'),
    ('atividade', 'Atividades'),
    ('afastamentos', 'Afastamentos'),
    ('grupocargoemprego', 'Grupo dos Cargos Emprego'),
    ('cargoemprego', 'Cargos Emprego'),
    ('classe', 'Classes'),
    ('diplomalegal', 'Diplomas Legais'),
    ('estadocivil', 'Estados Cívís'),
    ('funcao', 'Funções'),
    ('grupoocorrencias', 'Grupo Ocorrências'),
    ('ocorrencias', 'Ocorrências'),
    ('jornadatrabalho', 'Jornadas de Trabalho'),
    ('nivelescolaridade', 'Níveis de Escolaridade'),
    ('pais', 'País'),
    ('regimejuridico', 'Regimes Jurídicos'),
    ('situacaoservidor', 'Situações do Servidor'),
    ('banco', 'Bancos'),
    ('rubrica', 'Rubricas'),
    ('titulacao', 'Titulações'),
    ('servidor1', 'Dados do Servidor(1)'),
    ('servidor2', 'Dados do Servidor(2)'),
    ('servidor3', 'Dados do Servidor(3)'),
    ('servidor4', 'Dados do Servidor(4)'),
    # ('servidor5', 'Dados do Servidor(5)'),
    ('servidorafastamentos', 'Afastamentos dos Servidores'),
    ('historicoferias', 'Histórico de Férias dos Servidores'),
    ('historicoafastamentos', 'Histórico de Afastamentos dos Servidores'),
    ('historicofuncoes', 'Histórico de Funções dos Servidores'),
    ('ferias', 'Férias dos Servidores'),
    ('matriculasservidor', 'Matriculas dos Servidores'),
    ('pca', 'Provimentos dos Cargos dos Servidores'),
    ('posicionamentopca', 'Posicionamentos dos Provimentos dos Cargos dos Servidores'),
    ('historicosetor', 'Histórico dos Setores dos Servidores'),
)


class MacroForm(forms.Form):
    arquivos_extrator = MultipleChoiceField(
        label='Arquivos do Extrator',
        choices=ARQUIVOS_EXTRATOR_CHOICES,
        initial=[i[0] for i in ARQUIVOS_EXTRATOR_CHOICES],
        widget=CheckboxSelectMultiplePlus,
        required=True,
    )


class MacroHistoricoPCAForm(forms.Form):
    servidores = MultipleModelChoiceFieldPlus(
        queryset=Servidor.objects.filter(matricula_sipe__isnull=False),
        label='Servidores',
        required=True,
        help_text='Escolha os Servidores para realizar a extração dos históricos do PCA',
    )


class ExcluirRegistroForm(forms.FormPlus):
    SUBMIT_LABEL = 'Excluir'
    senha = forms.PasswordField()


class TipoCarteiraFuncionalForm(forms.ModelFormPlus):
    template = forms.ChoiceField(choices=TipoCarteiraFuncional.MODELOS_CHOICES, required=True)

    fieldsets = ((None, {'fields': (('nome'), ('template'), ('modelo'), ('ativo'))}),)

    class Meta:
        model = TipoCarteiraFuncional
        fields = ('nome', 'template')


class VinculoForm(forms.ModelFormPlus):
    pessoa = forms.ModelChoiceFieldPlus(Pessoa.objects)
    user = forms.ModelChoiceFieldPlus(User.objects)

    class Meta:
        model = Vinculo
        exclude = ()


class CancelarReservasPeriodoForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início do Cancelamento')
    data_termino = forms.DateFieldPlus(
        label='Data de Término do Cancelamento',
        required=False,
        help_text='Se você deseja cancelar as reservas de apenas um dia, não preencha este campo.',
    )
    justificativa = forms.CharField(label='Justificativa do Cancelamento', widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        if 'sala' in kwargs:
            self.sala = kwargs.pop('sala')
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        if not self.errors:
            data_inicio = cleaned_data.get('data_inicio')
            data_termino = cleaned_data.get('data_termino')
            if data_inicio < datetime.date.today():
                self.add_error('data_inicio', 'A Data de Início do Cancelamento deve ser maior ou igual a data atual.')

            if data_termino and data_termino < data_inicio:
                self.add_error('data_termino', 'Data de Término do Cancelamento deve ser maior ou igual a Data de Início do Cancelamento.')

        return cleaned_data

    def cancelar(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        data_termino = self.cleaned_data.get('data_termino')
        justificativa = self.cleaned_data.get('justificativa')
        reservas = ReservaSala.deferidas.filter(sala=self.sala)
        if not data_termino:
            data_termino = data_inicio

        reservas = reservas.filter(data_inicio__date__gte=data_inicio, data_fim__date__lte=data_termino)
        for reserva in reservas:
            reserva.justificativa_cancelamento = justificativa
            reserva.cancelar()


class AuthenticationFormPlus(AuthenticationForm):
    recaptcha = ReCaptchaField(label='Verificação', required=False)
    auth_code = CharField(label='Código Duplo Fator', required=False)

    def clean_auth_code(self):
        funcionalidade_duplo_fator_habilitada = Configuracao.get_valor_por_chave('comum', 'permite_autenticacao_duplo_fator')
        user = User.objects.filter(username=self.cleaned_data.get('username')).first()
        if (user and user.autenticacaodoisfatores_habilitada()) and funcionalidade_duplo_fator_habilitada:
            auth_code = self.cleaned_data.get('auth_code')
            if not onetimepass.valid_totp(auth_code, user.autenticacaodoisfatores.otp_secret_user):
                raise forms.ValidationError('Código de autenticação inválido.')
            return auth_code

    def clean(self):
        user = User.objects.filter(username=self.cleaned_data.get('username')).first()
        if getattr(settings, 'RECAPTCHA_PUBLIC_KEY', False) and user and user.login_attempts > 3 and not self.cleaned_data.get('recaptcha'):
            raise forms.ValidationError('Preencha o captcha.')
        super().clean()
        return self.cleaned_data


class ExibirQuadrosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Exibir'
    quadros = forms.ModelMultipleChoiceField(IndexLayout.objects, label='Quadros Escondidos', required=False, widget=CheckboxSelectMultiplePlus())

    def __init__(self, *args, **kwargs):
        self.coluna = kwargs.pop('coluna')
        super().__init__(*args, **kwargs)
        self.fields['quadros'].queryset = IndexLayout.objects.filter(escondido=True, usuario=self.request.user)

    def processar(self, request):
        quadros = self.cleaned_data.get('quadros')
        for quadro in quadros:
            quadro.delete()
            IndexLayout.recarregar_layouts(request)


class CalendarioForm(forms.FormPlus):
    ano = forms.ModelChoiceField(label='Ano', queryset=Ano.objects, required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Unidade Organizacional', empty_label='Todas', required=False)


class ConsultaEvento(forms.FormPlus):
    nome = forms.CharFieldPlus(label='Nome', required=False)
    ativo = forms.BooleanField(label='Apenas em andamento', required=False)


class CategoriaNotificacaoForm(forms.ModelFormPlus):
    class Meta:
        model = CategoriaNotificacao
        exclude = ()


class DeviceForm(forms.ModelFormPlus):
    class Meta:
        model = Device
        fields = ('nickname',)

    def clean_nickname(self) -> str | None:
        nickname = self.cleaned_data.get('nickname')
        if nickname:
            nickname = strip_tags(nickname).strip() or None
        return nickname


class UsuarioExternoForm(forms.FormPlus):
    cpf = forms.BrCpfField(label='CPF')
    nome = forms.CharFieldPlus(label='Nome Completo')
    email = forms.EmailField(label='Email')
    confirma_email = forms.EmailField(label='Confirmação de E-mail')
    justificativa = forms.ModelChoiceField(label='Perfil', queryset=JustificativaUsuarioExterno.objects.filter(ativo=True), required=True)

    def __init__(self, *args, **kwargs):
        self.usuario_pk = kwargs.pop('usuario_pk', None)
        self.usuario_externo_pk = kwargs.pop('usuario_externo_pk', None)
        super().__init__(*args, **kwargs)
        if self.usuario_externo_pk and not self.request.user.is_superuser:
            self.fields['cpf'] = ReadOnlyField(label='CPF')

    def clean_confirma_email(self):
        email = self.cleaned_data.get('email').strip() if self.cleaned_data.get('email') else ''
        confirma_email = self.cleaned_data.get('confirma_email').strip() if self.cleaned_data.get('confirma_email') else ''
        if email != confirma_email:
            raise forms.ValidationError('E-mails informados não são iguais!')

        if not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(email):
            raise forms.ValidationError('Escolha um e-mail que não seja institucional.')

        return self.cleaned_data['confirma_email']

    def clean(self):
        cpf = self.cleaned_data.get('cpf')
        if not cpf or self.usuario_externo_pk:
            return
        prestador = PrestadorServico.objects.filter(pessoa_fisica__cpf=cpf).first()
        if prestador:
            if prestador.usuario_externo:
                self.add_error(
                    'cpf',
                    mark_safe(
                        f"Já existe um usuário externo cadastrado com o CPF {cpf}. Você pode editá-lo <a href='/comum/editar_usuario_externo/{prestador.pk}/'>aqui</a>"
                    ),
                )
            else:
                self.add_error(
                    'cpf',
                    mark_safe(
                        f"Já existe um prestador de serviço cadastrado com o CPF {cpf}. Você pode editá-lo <a href='/admin/comum/prestadorservico/{prestador.pk}/'>aqui</a>"
                    ),
                )


class RelatorioSalasDisponiveisForm(forms.FormPlus):
    METHOD = 'GET'

    data_inicio = forms.DateFieldPlus(label='Data Inicial')
    data_fim = forms.DateFieldPlus(label='Data Final')
    hora_inicio = forms.TimeFieldPlus(label='Hora Inicial')
    hora_fim = forms.TimeFieldPlus(label='Hora Final')

    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo(), label=nomenclatura.campus, required=False)

    predio = forms.MultipleModelChoiceField(
        Predio.objects,
        label='Prédio',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Predio.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('campus', 'uo__in'),
            ],
        ),
    )

    sala = forms.MultipleModelChoiceField(
        Sala.objects,
        label='Sala',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Sala.SEARCH_FIELDS,
            multiple=True,
            form_filters=[
                ('predio', 'predio__in'),
                ('campus', 'predio__uo__in'),
            ],
        ),
    )

    fieldsets = (
        ('Data/Hora', {'fields': (('data_inicio', 'data_fim'), ('hora_inicio', 'hora_fim'))}),
        ('Local', {'fields': (('campus', 'predio'), ('sala',))}),
    )

    def clean(self):
        cleaned_data = super().clean()
        if not {'data_inicio', 'data_fim', 'hora_inicio', 'hora_fim'}.issubset(self.cleaned_data.keys()):
            raise forms.ValidationError('Informe todos os campos de Data e Hora para executar a consulta.')
        data_inicio = self.cleaned_data['data_inicio']
        data_fim = self.cleaned_data['data_fim']
        if data_inicio > data_fim:
            raise forms.ValidationError('Data Inicial não pode ser maior que Data Final.')

        hora_inicio = self.cleaned_data['hora_inicio']
        hora_fim = self.cleaned_data['hora_fim']
        if hora_inicio > hora_fim:
            raise forms.ValidationError('Hora Inicial não pode ser maior que Hora Final.')
        return cleaned_data

    def processar(self):
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')
        hora_inicio = self.cleaned_data.get('hora_inicio')
        hora_fim = self.cleaned_data.get('hora_fim')
        campus = self.cleaned_data.get('campus')
        predio = self.cleaned_data.get('predio')
        sala = self.cleaned_data.get('sala')

        result = {}
        dia_atual = data_inicio
        for _dia in range(int((data_fim - data_inicio).days) + 1):
            qs_salas_reservadas = ReservaSala.deferidas.filter(sala__agendavel=True)
            qs_salas_disponiveis = Sala.objects.filter(agendavel=True)

            dia_inicio = datetime.datetime.combine(dia_atual, hora_inicio)
            dia_fim = datetime.datetime.combine(dia_atual, hora_fim)

            qs_salas_reservadas = qs_salas_reservadas.filter(data_fim__gt=dia_inicio)
            qs_salas_reservadas = qs_salas_reservadas.filter(data_inicio__lt=dia_fim)

            if campus:
                qs_salas_reservadas = qs_salas_reservadas.filter(sala__predio__uo=campus)
                qs_salas_disponiveis = qs_salas_disponiveis.filter(predio__uo=campus)

            if predio:
                qs_salas_reservadas = qs_salas_reservadas.filter(sala__predio__in=predio)
                qs_salas_disponiveis = qs_salas_disponiveis.filter(predio__in=predio)

            if sala:
                qs_salas_reservadas = qs_salas_reservadas.filter(sala__in=sala)

                ids_sala = tuple(s.id for s in sala)
                qs_salas_disponiveis = qs_salas_disponiveis.filter(id__in=ids_sala)

            ids_salas_com_reserva = qs_salas_reservadas.values_list('sala_id', flat=True)
            result[dia_atual] = qs_salas_disponiveis.exclude(id__in=ids_salas_com_reserva)
            dia_atual = dia_atual + datetime.timedelta(days=1)
        return result


class DeferirDiarioReservaSalaPeriodo(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=True)
    data_fim = forms.DateFieldPlus(label='Data de Fim', required=True)
    diario = forms.IntegerFieldPlus(label='Diário', widget=forms.HiddenInput())
    horarios = forms.MultipleChoiceField(label='Horários', choices=[], widget=forms.CheckboxSelectMultiplePlus())

    def __init__(self, *args, **kwargs):
        diario_instance = kwargs.pop('diario', None)
        super().__init__(*args, **kwargs)
        if diario_instance:
            # setando o valor do diários
            self.fields['diario'].initial = diario_instance.pk
            # carregando os horários
            HorarioAulaDiario = apps.get_model('edu', 'HorarioAulaDiario')
            horarios = []
            for horario in HorarioAulaDiario.objects.filter(diario=diario_instance):
                horarios.append([horario.id, horario])
            self.fields['horarios'].choices = horarios

    def processar(self, request):
        dados = self.cleaned_data

        # diario
        Diario = apps.get_model('edu', 'Diario')
        diario = get_object_or_404(Diario, pk=dados.get('diario'))

        # sala
        sala = diario.local_aula
        solicitante = request.user

        # verificando se o usuário pode agendar
        if sala.pode_agendar(solicitante):
            hoje = datetime.datetime.now()
            HorarioAulaDiario = apps.get_model('edu', 'HorarioAulaDiario')

            # Dias semana desse diário
            dias_semana = diario.get_horarios_por_dia_semana()

            data_inicio = dados.get('data_inicio')
            data_fim = dados.get('data_fim')

            for n in range(int((data_fim - data_inicio).days) + 1):
                _data = data_inicio + timedelta(n)
                d_semana = _data.weekday() + 1
                # só cadastra nos dias da semana que tem aula
                if d_semana in dias_semana:
                    for horario in dados.get('horarios'):
                        horario_diario = HorarioAulaDiario.objects.get(pk=horario)

                        h_data_inicio = h_data_fim = _data
                        h_hora_inicio = datetime.datetime.strptime(horario_diario.horario_aula.inicio, '%H:%M').time()
                        h_hora_fim = datetime.datetime.strptime(horario_diario.horario_aula.termino, '%H:%M').time()

                        data_hora_inicio = datetime.datetime(
                            h_data_inicio.year, h_data_inicio.month, h_data_inicio.day, h_hora_inicio.hour, h_hora_inicio.minute, h_hora_inicio.second
                        )
                        data_hora_fim = datetime.datetime(
                            h_data_fim.year, h_data_fim.month, h_data_fim.day, h_hora_fim.hour, h_hora_fim.minute, h_hora_fim.second
                        )

                        justificativa = diario.gerar_justificativa_reserva_sala()
                        recorrencia = SolicitacaoReservaSala.RECORRENCIA_EVENTO_UNICO
                        solicitacao = SolicitacaoReservaSala.objects.get_or_create(
                            sala=sala,
                            solicitante=solicitante,
                            data_solicitacao=hoje,
                            data_inicio=h_data_inicio,
                            hora_inicio=h_hora_inicio,
                            data_hora_inicio=data_hora_inicio,
                            data_fim=h_data_fim,
                            hora_fim=h_hora_fim,
                            data_hora_fim=data_hora_fim,
                            recorrencia=recorrencia,
                            justificativa=justificativa,
                            status=SolicitacaoReservaSala.STATUS_DEFERIDA,
                        )[0]
                        solicitacao.gerar_reservas()
                        solicitacao.data_avaliacao = hoje
                        solicitacao.avaliador = solicitante
                        solicitacao.save()


class AutenticacaoDoisFatoresForm(forms.FormPlus):
    codigo = forms.CharFieldPlus(max_length=10, required=True)

    def __init__(self, *args, **kwargs):
        self.auths_2fa_user = kwargs.pop('auths_2fa_user', None)
        super().__init__(*args, **kwargs)

    def clean_codigo(self):
        codigo = self.cleaned_data.get('codigo')
        secret = self.auths_2fa_user.otp_secret_user

        if not otp.valid_totp(token=codigo, secret=secret):
            self.add_error('codigo', 'Código de autenticaçào inválido!')
        #
        return codigo


class FiltrarPorPeriodoForm(forms.FormPlus):
    METHOD = 'GET'
    usuario = forms.ModelChoiceFieldPlus(Vinculo.objects.none(), label='Usuário', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS))
    datahora_inicio = forms.DateTimeFieldPlus(label='Data de Início', required=True)
    datahora_fim = forms.DateTimeFieldPlus(label='Data de Término', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = datetime.date.today()
        vinculo_logado = self.request.user.get_vinculo()
        self.fields['usuario'].initial = vinculo_logado
        servidor_logado = self.request.user.get_relacionamento()
        if self.request.user.has_group_cached('Auditor'):
            self.fields['usuario'].queryset = Vinculo.objects.all()
        elif self.request.user.has_group_cached('Chefe de Setor') and servidor_logado.eh_chefe_do_setor_hoje(servidor_logado.setor):
            servidores_do_setor = servidor_logado.setor.get_servidores(recursivo=True)
            self.fields['usuario'].queryset = Vinculo.objects.filter(id__in=servidores_do_setor.values_list('vinculos', flat=True))
        else:
            self.fields['usuario'].queryset = Vinculo.objects.filter(id=vinculo_logado.id)
        self.fields['datahora_inicio'].initial = datetime.datetime(hoje.year, hoje.month, 1, 0, 0, 0)
        self.fields['datahora_fim'].initial = datetime.datetime(hoje.year, hoje.month, hoje.day, 23, 59, 59)
        self.datahora_inicio = hoje
        self.datahora_fim = hoje

    def clean(self):
        cleaned_data = super().clean()
        if not {'datahora_inicio', 'datahora_fim'}.issubset(self.cleaned_data.keys()):
            raise forms.ValidationError('Informe todos a data início e a data fim para executar a consulta.')
        datahora_inicio = self.cleaned_data['datahora_inicio']
        datahora_fim = self.cleaned_data['datahora_fim']
        if datahora_inicio > datahora_fim:
            raise forms.ValidationError('Data Inicial não pode ser maior que Data Final.')
        if (datahora_fim - datahora_inicio).days > 90:
            raise forms.ValidationError('O intervalo entre as datas não pode ser maior que 90 dias.')
        self.datahora_inicio = datahora_inicio
        self.datahora_fim = datahora_fim
        return cleaned_data


class ChangePasswordForm(forms.FormPlus):
    password = forms.CharField(max_length=100, widget=forms.PasswordInput, label='Senha')
    password_confirm = forms.CharField(max_length=100, widget=forms.PasswordInput, label='Confirmação de senha')

    def __init__(self, *args, **kwargs):
        self.username = kwargs.pop('username')
        super().__init__(*args, **kwargs)

    def clean_password_confirm(self):
        if self.cleaned_data.get('password') != self.cleaned_data.get('password_confirm'):
            raise forms.ValidationError('A confirmação de senha não é igual à senha.')
        if len(self.cleaned_data.get('password')) < 8:
            raise forms.ValidationError('A senha deve ter pelo menos 10 caracteres.')

        user = User.objects.filter(username=self.username).first()
        if not user:
            raise forms.ValidationError(f'Nenhum usuário com o username {self.username} encontrado.')

        usuario_ad = user.get_vinculo().get_usuario_ldap(attrs=['dn'])
        allow_local_password = user.eh_estrangeiro
        if usuario_ad:
            if self.cleaned_data.get('password') != to_ascii(self.cleaned_data.get('password')):
                raise forms.ValidationError('A senha não pode ter caracteres com acentuação.')

            ldap_conf = get_ldap_conf()
            if ldap_conf and ldap_conf.has_write_permission():
                passwd_result = ldap_conf.change_password(self.username, self.cleaned_data['password'])
                if not passwd_result:
                    raise forms.ValidationError('Problema ao definir senha. Certifique-se que a senha atenda aos requisitos necessários.')
            else:
                raise forms.ValidationError('Problema ao tentar acessar servidor de autenticação, por favor tente novamente em alguns minutos.')

        if allow_local_password or not usuario_ad:
            user.set_password(self.cleaned_data.get('password'))

        user.data_ultima_alteracao_senha = datetime.datetime.now()
        user.forcar_troca_senha = False
        user.save()

        return self.cleaned_data['password']


class TrocarSenhaForm(ChangePasswordForm):
    recaptcha = ReCaptchaField(label='')


class AtualizarFotoPessoaFisicaForm(forms.FormPlus):
    arquivo = forms.ImageFieldPlus(required=False)

    fieldsets = (('Upload de Arquivo', {'fields': ('arquivo',)}),)

    def __init__(self, *args, **kwargs):
        self.pessoa_fisica = kwargs.pop('pessoa_fisica', None)
        self.vinculo = kwargs.pop('vinculo', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        if not self.cleaned_data.get('arquivo'):
            raise forms.ValidationError('Adicione o arquivo da foto')
        else:
            return self.cleaned_data

    def processar(self, request):
        if request.user.has_perm('comum.change_prestadorservico'):
            dados = self.cleaned_data.get('arquivo').read()
            self.vinculo.foto.save(f'{self.pessoa_fisica.pk}.jpg', ContentFile(dados))
            self.add_log_entry(request)
            return 'Foto atualizada com sucesso.'
        else:
            return 'Permissão Negada.'

    def add_log_entry(self, request):
        LogEntry.objects.log_action(
            user_id=request.user.pk,
            content_type_id=get_content_type_for_model(self.pessoa_fisica).pk,
            object_id=self.pessoa_fisica.pk,
            object_repr=force_str(self.pessoa_fisica),
            action_flag=CHANGE,
            change_message=f'Atualizou foto do Usuário Externo {self.pessoa_fisica} ',
        )


class APIExternaForm(forms.ModelFormPlus):
    class Meta:
        model = APIExterna
        exclude = ()

    def clean_nome(self):
        nome = self.cleaned_data.get('nome')
        if not nome.isupper():
            raise ValidationError('O nome deve estar todo em maiúsculas.')

        nome_sem_acentos = retira_acentos(nome)
        if nome_sem_acentos != nome:
            raise ValidationError('O nome não deve conter acentos.')

        nome_sem_caracteres_especiais = re.sub(r'[^a-zA-Z0-9_]', '', nome)
        if nome_sem_caracteres_especiais != nome:
            raise ValidationError('O nome deve estar sem acentos, espaços ou caracteres especiais (exceto underline).')
        return nome


class ConfirmarComSenhaForm(forms.FormPlus):
    senha = forms.PasswordField()
    confirmar = forms.BooleanField(label='Confirma a solicitação')


class ManutencaoProgramadaForm(forms.ModelFormPlus):
    class Meta:
        model = ManutencaoProgramada
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campi'].queryset = UnidadeOrganizacional.objects.suap()

    def clean_campi(self):
        campi = self.cleaned_data.get('campi')
        if not self.cleaned_data.get('publico') and self.cleaned_data.get('campi'):
            raise forms.ValidationError('Só é possível escolher um campus com um publico associado.')
        return campi


class AssinarDocumentoICPEduForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(label='Arquivo PDF', max_file_size=5 * 1024 * 1024, filetypes=('pdf',), widget_custom_cls=PositionedPdfInput)

    def processar(self):
        arquivo = self.cleaned_data.get('arquivo')
        content = arquivo.read()
        pessoa_fisica = self.request.user.get_profile()
        _v = self.request.user.get_vinculo()
        signer_email = _v.email_notificacao if _v else ''
        coords = self.request.POST.get('pdf-coords')
        page = int(self.request.POST.get('pdf-page', 1))
        with tempfile.NamedTemporaryFile(suffix='.pdf', delete=False) as fp:
            fp.write(content)
        pdf_signer = PdfSigner(fp.name, pessoa_fisica, signer_email=signer_email)
        os.unlink(fp.name)
        return pdf_signer.sign(coords=coords, page_no=page, path=fp.name)


class ReuniaoOrgaoColegiadoForm(forms.ModelFormPlus):
    colegiado = forms.ChoiceField(
        label='Órgão Colegiado',
        choices=[*[[colegiado[0], colegiado[1]] for colegiado in ReuniaoOrgaoColegiado.listar_orgaos_colegiados()]],
        required=True,
    )
    descricao = forms.CharField(label='Descrição', required=False, widget=forms.Textarea)
    local = forms.CharField(label='Local', required=False, widget=forms.Textarea)

    class Meta:
        model = ReuniaoOrgaoColegiado
        exclude = ()

    def clean(self):
        clean = super().clean()
        ReuniaoOrgaoColegiado.validar(clean, self.instance)
        return clean


class ReuniaoOrgaoColegiadoConsultarForm(forms.FormPlus):
    formato = forms.ChoiceField(
        label='Formato',
        choices=[
            ['mensal', 'Mensal'],
            ['anual', 'Anual'],
        ],
        required=True,
    )

    mes = forms.MesField(label='Filtrar por Mês:', required=False, empty_label='Todos')
    ano = forms.ChoiceField(required=False, choices=[], label='Filtrar por Ano:')

    METHOD = 'GET'

    class Media:
        js = ('/static/comum/js/ReuniaoOrgaoColegiadoConsultarForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        valores = ReuniaoOrgaoColegiado.objects.aggregate(valor_max=Max('data_fim'), valor_min=Min('data_inicio'))
        data_inicio_agregado = valores.get('valor_min')
        data_fim_agregado = valores.get('valor_max')

        if data_inicio_agregado is None or data_fim_agregado is None:
            current_year = datetime.date.today().year
            ano_minimo = current_year
            ano_maximo = current_year
        else:
            ano_minimo = data_inicio_agregado.year
            ano_maximo = data_fim_agregado.year

        ANO_CHOICES = [(f'{ano}', f'{ano}') for ano in range(ano_maximo, ano_minimo - 1, -1)]
        self.fields['ano'].choices = ANO_CHOICES

    def get_data_inicio(self):
        ano = self.get_ano()
        mes = self.get_mes()
        if mes == 0:
            mes = 1
        return datetime.date(ano, mes, 1)

    def get_data_fim(self):
        ano = self.get_ano()
        mes = self.get_mes()
        if mes == 0:
            mes = 12
        return datetime.date(ano, mes, calendar.monthrange(ano, mes)[1])

    def get_mes(self):
        return int(self.cleaned_data.get('mes'))

    def get_ano(self):
        return int(self.cleaned_data.get('ano'))

    def eh_formato_mensal(self):
        return self.cleaned_data.get('formato') == 'mensal'


class CadastrarAtalhoForm(forms.ModelFormPlus):
    nome = forms.CharField(label='Nome')

    class Meta:
        model = Atalho
        fields = 'nome', 'url'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['url'].widget = forms.HiddenInput()
