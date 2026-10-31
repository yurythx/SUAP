import hashlib
import operator
import os
import subprocess
import tempfile
from datetime import datetime, time, timedelta
from functools import reduce
from io import BytesIO
from typing import Any

import qrcode
from crispy_forms.helper import FormHelper
from crispy_forms.layout import Div, Layout, Submit
from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth.models import Group
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction
from django.db.models import Q, QuerySet
from django.db.models.signals import post_save
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from comum.exceptions import LoginException, UserMustResetPassword
from comum.models import Configuracao, User, Vinculo
from comum.utils import get_setor, get_setores_que_sou_chefe_hoje, tl
from djtools import forms
from djtools.forms import ReadOnlyField, ReCaptchaField, SpanField, SpanWidget
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget, TextareaCounterWidget, TreeWidget
from djtools.utils import full_check_file, normalizar_termos_busca
from documento_eletronico.forms import AuthenticationGovBRForm, PapelForm, SolicitacaoAssinaturaForm
from documento_eletronico.models import (
    Classificacao,
    CompartilhamentoDocumentoDigitalizadoPessoa,
    Documento,
    DocumentoDigitalizado,
    HipoteseLegal,
    ModeloDocumento,
    NivelPermissao,
    TipoConferencia,
    TipoDocumento,
    TipoDocumentoTexto,
)
from documento_eletronico.models import (
    NivelAcesso as NivelAcessoEnum,
)
from documento_eletronico.utils import gerar_hash, get_setores_compartilhados
from processo_eletronico import tasks
from processo_eletronico.indicadores import limites_periodo
from processo_eletronico.models import (
    ComentarioProcesso,
    ConfiguracaoInstrucaoNivelAcesso,
    ConfiguracaoTramiteProcesso,
    DocumentoDigitalizadoProcesso,
    DocumentoProcesso,
    DocumentoTextoProcesso,
    GrupoInteressadosProcesso,
    ModeloDespacho,
    PrioridadeTramite,
    Processo,
    ProcessoMinuta,
    RegistroAcaoProcesso,
    Requerimento,
    RequerimentoDigitalizado,
    Rotulo,
    SolicitacaoAlteracaoNivelAcesso,
    SolicitacaoCiencia,
    SolicitacaoDespacho,
    SolicitacaoJuntada,
    SolicitacaoJuntadaDocumento,
    TipoProcesso,
    Tramite,
    TramiteDistribuicao,
)
from processo_eletronico.status import ProcessoStatus, SolicitacaoJuntadaStatus
from processo_eletronico.utils import pode_receber_processo_privado, setores_que_sou_chefe_ou_tenho_poder_de_chefe
from rh.models import Papel, PessoaFisica, Setor, UnidadeOrganizacional
from suap import nomenclatura


def hash_documento(arquivo):
    sha512 = hashlib.sha512()
    for chunk in arquivo.chunks():
        sha512.update(chunk)
    return sha512.hexdigest()


def get_datetime_now():
    try:
        from django.utils import timezone

        return timezone.now()
    except ImportError:
        import datetime

        return datetime.datetime.now()


class ConfiguracaoForm(forms.FormPlus):
    email_processo_eletronico = forms.CharField(
        label='E-mail de Contato da Seção Responsável por Processos Eletrônicos',
        help_text='Será exibido na notificação por e-mail da Solicitação de Ciência.',
        required=False,
    )
    hipotese_legal_documento_abertura_requerimento = forms.ModelChoiceField(
        HipoteseLegal.objects.filter(nivel_acesso=NivelAcessoEnum.RESTRITO.name),
        label='Hipótese Legal para Documento de Abertura do Requerimento',
        required=False,
    )
    if 'centralservicos' in settings.INSTALLED_APPS:
        BaseConhecimento = apps.get_model('centralservicos', 'BaseConhecimento')
        base_conhecimento_permissao_acesso_processo = forms.ModelChoiceField(
            BaseConhecimento.objects.filter(ativo=True, visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA),
            label='Base de conhecimento com instruções para dar permissão de tramitar e/ou criar processos',
            required=False,
        )
    SIZE_CHOICES = [[2621440, '2.5 MB'], [5242880, '5 MB'], [10485760, '10 MB'], [20971520, '20 MB'], [5242880, '50 MB'], [104857600, '100 MB']]
    tamanho_maximo_upload_personalizado = forms.ChoiceField(
        label='Tamanho máximo de upload de arquivos para pessoas/servidores específicos',
        choices=SIZE_CHOICES,
        help_text='Tamanho em MB',
        required=False,
    )
    qs_prestadores_servidores = PessoaFisica.objects.filter(eh_servidor=True) | PessoaFisica.objects.filter(eh_prestador=True)
    pessoas_permitidas_realizar_upload_personalizado = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço realizar uploads até o máximo definido na configuração acima',
        queryset=qs_prestadores_servidores,
        required=False,
    )
    tipo_processo_solicitar_emissao_diploma = forms.ModelChoiceField(
        TipoProcesso.objects.all(),
        label='Tipo de Processo Para Solicitar Emissão de Diploma',
        required=False,
    )
    tipo_processo_demanda_externa_do_cidadao = forms.ModelChoiceField(
        TipoProcesso.objects.all(),
        label='Tipo de Processo Para Solicitação de Demanda Externa do Cidadão',
        required=False,
    )
    blacklist = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.none(), label='Procuradores que não podem receber processos privados', required=False
    )
    termo_ciencia_publico = forms.BooleanField(
        label='Termo de Ciência Público',
        required=False,
        help_text='Marque essa opção caso deseje que os termos de ciência de processo possuam o nível de acesso "Público".',
    )
    permite_recebimento_lote = forms.BooleanField(
        label='Permite Recebimento em Lote', required=False, help_text='Marque essa opção caso deseje habilitar o recebimento em lote de processos.'
    )
    permite_encaminhamento_lote = forms.BooleanField(
        label='Permite Encaminhamento em Lote',
        required=False,
        help_text='Marque essa opção caso deseje habilitar o encaminhamento em lote de processos.',
    )
    permite_anexar_aquivos_media = forms.BooleanField(
        label='Permite Anexar Arquivos de Media',
        required=False,
        help_text='Marque essa opção caso deseje habilitar a enexação de arquivos de media como videos e audios aos pocessos.',
    )
    permite_distribuir_ao_tramitar = forms.BooleanField(
        label='Permite Direcionar Trâmite de Processo',
        required=False,
        help_text='Marque essa opção caso deseje permitir ao usuário realizar a distribuição do processo (indicar a pessoa do setor de destino que vai trabalhar no processo) no ato da tramitação.',
    )
    permite_excluir_comentario_processo = forms.BooleanField(
        label='Permite Excluir Comentário de Processo',
        required=False,
        help_text='Marque essa opção caso deseje habilitar a exclusão do último comentário do processo caso o usuário seja o autor.',
    )
    atribuir_permissao_servidores_funcao = forms.BooleanField(
        label='Atribuir Permissão Automática a Servidores com Função',
        required=False,
        help_text='Marque essa opção caso deseje que servidores com função ativa nos setores possa automaticamente cadastrar e operar processos no setor.',
    )
    exibir_numeracao_nup21 = forms.BooleanField(
        label='Exibir a numeração NUP21 na numeração dos processos eletrônicos',
        required=False,
        help_text='Marque essa opção caso deseje que a numeração NUP21 seja sempre exibida na numeração de processos mesmo que a NUP17 esteja definida.',
    )
    exibir_dados_basicos_listagem = forms.BooleanField(
        label='Sempre Exibir Dados Básicos na Listagem',
        required=False,
        help_text='Marque essa opção caso deseje que os dados básicos (tipo, assunto, setor de criação, status e setor atual) do processo sejam exibidos independentemente de serem públicos, privados ou restritos.',
    )
    bloquear_processos_apensados = forms.BooleanField(
        label='Bloquear Processos Apensados',
        required=False,
        help_text='Marque essa opção caso deseje que processos apensados a outro processo não possam ser mais movimentados ou alterados. Novas movimentações e alterações (Ex: Adição de documentos) só serão permitidos no processo principal.',
    )
    texto_termo_ciencia = forms.CharField(
        label='Texto do Termo de Ciência',
        required=False,
        help_text='Texto utilizado na elaboração do termo de ciência de processos eletrônicos. Variáveis disponíveis: pessoa, lotacao e data. Ex: "Eu, {pessoa.nome}{lotacao}, em {data}...".',
        widget=forms.Textarea(),
    )
    impedir_exclusao_minuta_anexao_processo = forms.BooleanField(
        label='Impedir Exclusão de Minutas Anexadas a Processos',
        required=False,
        help_text='Marque essa opção caso deseje impedir que documentos anexados a processos como minuta possam ser excluídos e consequentemente removidos do processo.',
    )
    impedir_inativacao_servidor = forms.BooleanField(
        label='Impedir Inativação de Servidores com Processos',
        required=False,
        help_text='Marque essa opção caso deseje impedir que servidores em posse de processos privados sejam inativados.',
    )
    permitir_grupos_interessados = forms.BooleanField(
        label='Permitir Grupos de Interessados',
        required=False,
        help_text='Marque essa opção caso deseje ativar a funcionalidade de gerenciamento e inclusão de grupos de interessados ao cadastrar processos.',
    )
    registrar_acoes_processos_publicos = forms.BooleanField(
        label='Registrar Ações em Processos Públicos',
        required=False,
        help_text='Marque essa opção caso deseje registrar ações de visualização e impressão de processos púbicos',
    )
    termo_decurso_prazo_solicitacao_ciencia = forms.BooleanField(
        label='Utilizar Termo de Decurso de Prazo em Solicitacao Ciência Expirada',
        required=False,
        help_text='Marque essa opção caso deseje que as solicitações de ciência de processo expirada gerem um termo de decurso de prazo ao invés da auto-ciência pelo solicitado.',
    )
    cores_rotulos = forms.CharField(
        label='Cores dos Rótulos',
        help_text='Separado por quebra de linha. Exemplo: "#D32F2F:Vermelho Escuro"',
        required=False,
        widget=forms.Textarea(),
    )
    exibir_setor_inativo_no_filtro = forms.BooleanField(
        label='Exibir Setor Inativo nos Filtros',
        help_text='Setores inativados poderão ser selecionados nos campos de filtros por setor na tela de processos eletrônicos.',
        required=False,
    )
    prazo_recebimento_processo = forms.IntegerField(
        label='Prazo para Recebimento de Processos',
        help_text='Dias úteis que o usuário ou chefe do setor tem para receber os processos encaminhados. Após decorrido o prazo, o recebimento será realizado automaticamente pelo sistema.',
        required=False,
    )
    habilitar_impressao_etiqueta = forms.BooleanField(
        label='Habilitar Impressão de Etiqueta',
        help_text='Habilita a impressão de um PDF identificador com código de barras para emissão de recibos.',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        procurador = Group.objects.get(name='Procurador')
        self.fields['blacklist'].queryset = Vinculo.objects.ativos().servidores().filter(user__groups=procurador)
        pessoas_permitidas_upload_personalizado = Configuracao.get_valor_por_chave(
            app='processo_eletronico', chave='pessoas_permitidas_realizar_upload_personalizado'
        )
        self.fields['pessoas_permitidas_realizar_upload_personalizado'].initial = (
            list(pessoas_permitidas_upload_personalizado.split(',')) if pessoas_permitidas_upload_personalizado else []
        )


class TipoProcessoForm(forms.ModelFormPlus):
    classificacoes = forms.ModelMultiplePopupChoiceField(Classificacao.objects.all(), label='Classificações', required=False)

    fieldsets = (
        ('Dados Principais', {'fields': ('nome', 'classificacoes', 'consulta_publica', 'ativo')}),
        (
            'Níveis de Acesso Permitidos',
            {'fields': ('permite_nivel_acesso_privado', 'permite_nivel_acesso_restrito', 'permite_nivel_acesso_publico')},
        ),
        ('', {'fields': ('nivel_acesso_default',)}),
        (
            'Requerimento',
            {
                'fields': (
                    'permite_gerar_processo_via_requerimento',
                    'orientacoes_requerimento',
                )
            },
        ),
    )

    class Meta:
        model = TipoProcesso
        fields = (
            'nome',
            'permite_nivel_acesso_privado',
            'permite_nivel_acesso_restrito',
            'permite_nivel_acesso_publico',
            'nivel_acesso_default',
            'classificacoes',
            'orientacoes_requerimento',
            'consulta_publica',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classificacoes'].queryset = Classificacao.podem_classificar.all()


class ProcessoForm(forms.ModelFormPlus):
    interessados = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects, label='Interessados', required=True)
    grupo_interessados = forms.ModelChoiceFieldPlus(
        Vinculo.objects.none(),
        label='Grupo de Interessados',
        required=False,
        help_text=mark_safe(
            'Clique aqui para <a target="_blank" href="/admin/processo_eletronico/grupointeressadosprocesso/">gerenciar grupos de interessados em um outra aba.</a>'
        ),
    )
    assunto = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Assunto')
    tipo_processo = forms.ModelPopupChoiceField(TipoProcesso.objects.ativos().all(), label='Tipo de Processo', required=True)
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)
    setor_criacao = forms.ModelChoiceField(label='Setor de Criação', queryset=Setor.objects.suap_ativos().none(), required=True)
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects, label='Classificações', required=False, disabled=True)
    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    class Meta:
        model = Processo
        fields = ('interessados', 'tipo_processo', 'assunto', 'nivel_acesso', 'hipotese_legal', 'setor_criacao')

    class Media:
        js = ['/static/processo_eletronico/js/ProcessoForm.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.permitir_grupos_interessados = Configuracao.get_valor_por_chave('processo_eletronico', 'permitir_grupos_interessados')
        # Novo esquema de permissoes do processo e documento eletronico
        # qs_setores = get_todos_setores(self.request.user, setores_compartilhados=False)
        qs_setores = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)

        if self.fields.get('setor_criacao'):
            self.fields['setor_criacao'].queryset = qs_setores

        conf_orientacao = ConfiguracaoInstrucaoNivelAcesso.get_orientacao()
        if conf_orientacao:
            self.fields['ciencia_instrucoes_gerais'].required = True
            self.fields['instrucoes_gerais'] = SpanField(widget=SpanWidget(), label='')
            self.fields['instrucoes_gerais'].widget.label_value = mark_safe(f'<br>{conf_orientacao}')
            self.fields['instrucoes_gerais'].widget.original_value = conf_orientacao
            self.fields['instrucoes_gerais'].required = False
        else:
            self.fields['ciencia_instrucoes_gerais'].widget = forms.HiddenInput()
            self.fields['ciencia_instrucoes_gerais'].required = False
            self.fields['instrucoes_gerais'].widget = forms.HiddenInput()

        if self.permitir_grupos_interessados:
            self.fields['interessados'].required = False
            self.fields['grupo_interessados'].queryset = GrupoInteressadosProcesso.objects.filter(usuario=self.request.user)
        else:
            self.fields['grupo_interessados'].widget = forms.HiddenInput()

    def clean_interessados(self):
        interessados = self.cleaned_data.get('interessados', ())
        grupo_interessados = GrupoInteressadosProcesso.objects.filter(pk=self.data.get('grupo_interessados') or 0).first()

        vinculos = list(interessados)
        if grupo_interessados:
            vinculos.extend(list(grupo_interessados.interessados.all()))

        invalidos = []
        for vinculo in vinculos:
            if not vinculo.cpf_ou_cnpj_valido():
                invalidos.append(f'{vinculo}')

        if invalidos:
            self.add_error('interessados', 'Os seguintes interessados não possuem CPF ou CNPJ válidos: {}.'.format(', '.join(invalidos)))
        if not vinculos:
            self.add_error('interessados', 'Um ou mais interessados devem ser informados.')

        return vinculos

    def clean_setor_criacao(self):
        setor = self.cleaned_data.get('setor_criacao')
        if self.instance.pk:
            processo_salvo_banco = Processo.objects.get(id=self.instance.id)
            if processo_salvo_banco.setor_criacao.id != setor.id:
                self.add_error(
                    'setor_criacao', 'O Setor de Criação do processo não pode ser alterado uma vez que o número do processo depende do setor.'
                )
        return setor

    def clean(self):
        setor = get_setor(self.request.user)
        if not setor.get_codigo_siorg():
            raise ValidationError(
                f'O setor "{setor}" não está com o código SIORG cadastrado.'
                ' É impossível gerar o número do processo sem essa informação. '
                'Por favor, entrar em contato com a Gestão de Pessoas para que ela '
                'proceda o cadastro do código SIORG do Setor no SUAP'
            )
        return super().clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.id:
            instance.data_alteracao = datetime.now()
            instance.usuario_alteracao = self.request.user
        if commit:
            instance.save()
            self.save_m2m()
            post_save.send(sender=Processo, instance=instance, created=False)  # Reemite o post_save manualmente
        return instance


class ProcessoEditarForm(forms.ModelFormPlus):
    setor_criacao = forms.ModelChoiceField(label='Setor de Criação', queryset=Setor.objects.suap_ativos().none(), required=True)
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects, label='Classificações', required=False, disabled=True)
    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    class Meta:
        model = Processo
        fields = ('tipo_processo', 'setor_criacao')

    class Media:
        js = ['/static/processo_eletronico/js/ProcessoForm.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Novo esquema de permissoes do processo e documento eletronico
        # qs_setores = get_todos_setores(self.request.user, setores_compartilhados=False)
        qs_setores = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=True)

        if self.fields.get('setor_criacao'):
            self.fields['setor_criacao'].queryset = qs_setores

        conf_orientacao = ConfiguracaoInstrucaoNivelAcesso.get_orientacao()
        if conf_orientacao:
            self.fields['ciencia_instrucoes_gerais'].required = True
            self.fields['instrucoes_gerais'] = SpanField(widget=SpanWidget(), label='')
            self.fields['instrucoes_gerais'].widget.label_value = mark_safe(f'<br>{conf_orientacao}')
            self.fields['instrucoes_gerais'].widget.original_value = conf_orientacao
            self.fields['instrucoes_gerais'].required = False
        else:
            self.fields['ciencia_instrucoes_gerais'].widget = forms.HiddenInput()
            self.fields['ciencia_instrucoes_gerais'].required = False
            self.fields['instrucoes_gerais'].widget = forms.HiddenInput()

    def clean_setor_criacao(self):
        setor = self.cleaned_data.get('setor_criacao')
        if self.instance.pk:
            processo_salvo_banco = Processo.objects.get(id=self.instance.id)
            if processo_salvo_banco.setor_criacao.id != setor.id:
                self.add_error(
                    'setor_criacao', 'O Setor de Criação do processo não pode ser alterado uma vez que o número do processo depende do setor.'
                )
        return setor

    def clean(self):
        setor = get_setor(self.request.user)
        if not setor.get_codigo_siorg():
            raise ValidationError(
                f'O setor "{setor}" não está com o código SIORG cadastrado.'
                ' É impossível gerar o número do processo sem essa informação. '
                'Por favor, entrar em contato com a Gestão de Pessoas para que ela '
                'proceda o cadastro do código SIORG do Setor no SUAP'
            )

    def save(self, commit=True):
        instance = super().save(commit=False)
        if instance.id:
            instance.data_alteracao = datetime.now()
            instance.usuario_alteracao = self.request.user
        return super().save(commit=commit)


class CriarProcessoComTramiteForm(ProcessoForm):
    SUBMIT_LABEL = 'Criar Processo'

    setor_destino = forms.ModelChoiceField(
        label='Destino do primeiro trâmite', queryset=Setor.objects.suap_ativos(), required=True, widget=AutocompleteWidget()
    )
    despacho = forms.CharField(label='Despacho', widget=forms.Textarea(), required=False)

    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Media:
        js = ['/static/processo_eletronico/js/ProcessoForm.js']

    def __init__(self, *args, dados_iniciais: dict, **kwargs):
        super().__init__(*args, **kwargs)
        self.fieldsets = []
        if dados_iniciais:
            self.anexos_do_chamado = dados_iniciais.get('anexos_do_chamado')
            for indice, doc in enumerate(self.anexos_do_chamado, start=1):
                self.fields[doc['name']] = forms.CharFieldPlus(label='Descrição', max_length=510, initial=doc['descricao'])
                self.fields[doc['name']].widget.attrs['readonly'] = True
                self.fields[doc['name'] + '_tipo'] = forms.ModelChoiceField(TipoDocumento.ativos, label='Tipo do Documento', required=True)
                self.fields[doc['name'] + '_nivel_acesso'] = forms.ChoiceField(
                    label='Nível de Acesso',
                    required=True,
                    choices=((None, '---------'), (Documento.NIVEL_ACESSO_RESTRITO, 'Restrito'), (Documento.NIVEL_ACESSO_PUBLICO, 'Público')),
                )
                self.fieldsets.append(
                    (
                        f'Documento {indice}',
                        {
                            'fields': (
                                doc['name'],
                                doc['name'] + '_tipo',
                                doc['name'] + '_nivel_acesso',
                            )
                        },
                    ),
                )

        self.fieldsets.extend(
            [
                (
                    'Dados do Processo',
                    {
                        'fields': (
                            'interessados',
                            'tipo_processo',
                            'assunto',
                            'setor_criacao',
                            'classificacao',
                        )
                    },
                ),
                ('Nível de Acesso', {'fields': ('nivel_acesso', 'hipotese_legal')}),
                ('Setor de Destino', {'fields': ('setor_destino', 'despacho')}),
                ('Assinatura', {'fields': ('papel', 'senha')}),
            ]
        )

        if dados_iniciais:
            self.initial['assunto'] = dados_iniciais.get('assunto')
            self.initial['interessados'] = dados_iniciais.get('ids_interessados')

        vinculo = self.request.user.get_relacionamento()
        self.fields['papel'].queryset = vinculo.papeis_ativos

    def clean_papel(self):
        papel = self.cleaned_data.get('papel', None)

        relacionamento = self.request.user.get_relacionamento()

        if not papel or papel not in relacionamento.papeis_ativos:
            self.add_error('papel', 'Papel inválido.')
        return self.cleaned_data.get('papel')

    def clean_nivel_acesso(self):
        nivel_acesso = self.cleaned_data.get('nivel_acesso')
        if nivel_acesso is not None and nivel_acesso == Processo.NIVEL_ACESSO_PRIVADO:
            raise ValidationError('Processos privados só podem ser tramitados para pessoas, o que ainda não é suportado por esta funcionalidade.')
        return nivel_acesso

    def processar(self, url_redirecionamento=None, notificar=False, on_finish=None, on_finish_extra_params=None):
        with transaction.atomic():
            processo = super().save()
            RegistroAcaoProcesso.criar(tipo_acao=RegistroAcaoProcesso.TIPO_CRIACAO, processo=processo, request=self.request, observacao='')

            def _concluir_processamento():
                for doc in self.anexos_do_chamado:
                    doc['tipo_documento'] = self.cleaned_data.get(f'{doc.get("name")}_tipo')
                    doc['nivel_acesso'] = self.cleaned_data.get(f'{doc.get("name")}_nivel_acesso')

                tasks.criar_arquivos_e_primeiro_tramite_de_processo(
                    processo=processo,
                    anexos=self.anexos_do_chamado,
                    usuario=self.request.user,
                    papel=self.cleaned_data.get('papel'),
                    setor_criacao=self.cleaned_data.get('setor_criacao'),
                    corpo_despacho=self.cleaned_data.get('despacho'),
                    setor_destino=self.cleaned_data.get('setor_destino'),
                    url_redirecionamento=url_redirecionamento or processo.get_absolute_url(),
                    notify=notificar,
                    on_finish=on_finish,
                    on_finish_extra_params=on_finish_extra_params,
                )

            transaction.on_commit(_concluir_processamento)


class ApensarProcessosForm(forms.FormPlus):
    processos_a_apensar = forms.MultipleModelChoiceFieldPlus(label='Processos a Apensar', queryset=Processo.objects.none())
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        self.processo_apensador = kwargs.pop('processo_apensador')
        super().__init__(*args, **kwargs)
        #
        processos_que_podem_ser_apensados = (
            Processo.ativos.by_user(self.request.user).exclude(id=self.processo_apensador.id).exclude(status=ProcessoStatus.STATUS_ANEXADO)
        )
        #
        processos_que_podem_ser_apensados = processos_que_podem_ser_apensados.filter(setor_atual=self.processo_apensador.setor_atual).exclude(
            apensamentoprocesso__isnull=False, apensamentoprocesso__data_hora_remocao__isnull=True
        )
        if self.processo_apensador.nivel_acesso == Processo.NIVEL_ACESSO_PRIVADO:
            processos_que_podem_ser_apensados = processos_que_podem_ser_apensados.filter(nivel_acesso=Processo.NIVEL_ACESSO_PRIVADO)
        else:
            processos_que_podem_ser_apensados = processos_que_podem_ser_apensados.exclude(nivel_acesso=Processo.NIVEL_ACESSO_PRIVADO)
        #
        self.fields['processos_a_apensar'].queryset = processos_que_podem_ser_apensados.order_by('numero_protocolo')
        if Configuracao.get_valor_por_chave('processo_eletronico', 'bloquear_processos_apensados'):
            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'] = forms.ModelChoiceField(label='Perfil', queryset=vinculo.papeis_ativos, required=True)
            if vinculo.papeis_ativos.count() == 1:
                self.fields['papel'].initial = vinculo.papeis_ativos.first().id

    def clean(self):
        cleaned_data = super().clean()
        processos_a_apensar = self.cleaned_data.get('processos_a_apensar', None)
        if processos_a_apensar:
            for processo_a_apensar in processos_a_apensar:
                if not processo_a_apensar.pode_editar(self.request.user):
                    msg = f'Você não possui permissão de edição no processo {processo_a_apensar}.'
                    self.add_error('processos_a_apensar', msg)
        else:
            self.add_error('processos_a_apensar', 'Por favor, informe um ou mais processos a serem apensados.')
        return cleaned_data

    def save(self):
        processos_a_apensar = self.cleaned_data['processos_a_apensar']
        justificativa = self.cleaned_data['justificativa']
        self.processo_apensador.apensar_processos(processos_a_apensar, justificativa, self.request)


class DesapensarProcessoForm(forms.FormPlus):
    justificativa = forms.CharField(max_length=255, widget=forms.Textarea, required=True)

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        if Configuracao.get_valor_por_chave('processo_eletronico', 'bloquear_processos_apensados'):
            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'] = forms.ModelChoiceField(label='Perfil', queryset=vinculo.papeis_ativos, required=True)
            if vinculo.papeis_ativos.count() == 1:
                self.fields['papel'].initial = vinculo.papeis_ativos.first().id

    def save(self):
        justificativa = self.cleaned_data['justificativa']
        self.processo.desapensar_processo(justificativa, self.request)


class DesapensarTodosProcessosForm(forms.FormPlus):
    justificativa = forms.CharField(max_length=255, widget=forms.Textarea, required=True)

    def __init__(self, *args, **kwargs):
        self.apensamento = kwargs.pop('apensamento')
        super().__init__(*args, **kwargs)
        if Configuracao.get_valor_por_chave('processo_eletronico', 'bloquear_processos_apensados'):
            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'] = forms.ModelChoiceField(label='Perfil', queryset=vinculo.papeis_ativos, required=True)
            if vinculo.papeis_ativos.count() == 1:
                self.fields['papel'].initial = vinculo.papeis_ativos.first().id

    def save(self):
        justificativa = self.cleaned_data['justificativa']
        self.apensamento.finalizar(justificativa, self.request)


class AnexarProcessosForm(forms.FormPlus):
    processos_anexados = forms.MultipleModelChoiceFieldPlus(
        Processo.objects.none(),
        label='Processos a Anexar',
        help_text='Somente serão exibidos processos cujos interessados sejam os mesmos.',
    )
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        self.processo_anexador = kwargs.pop('processo_anexador')
        super().__init__(*args, **kwargs)
        self.fields['processos_anexados'].queryset = self.processo_anexador.get_processos_podem_ser_anexados(self.request.user)

    def clean_processos_anexados(self):
        processos_a_anexar = self.cleaned_data.get('processos_anexados')
        todos_processos_a_anexar = Processo.ativos.filter(id__in=processos_a_anexar) | Processo.ativos.filter(id=self.processo_anexador.id)
        # o processo anexador é o mais antigo
        self.processo_anexador = todos_processos_a_anexar.order_by('data_hora_criacao').first()
        processos_a_anexar = todos_processos_a_anexar.exclude(id=self.processo_anexador.id)
        return processos_a_anexar

    def clean(self):
        processos_anexados = self.cleaned_data.get('processos_anexados')
        if processos_anexados:
            for processo_anexado in processos_anexados:
                if len(processo_anexado.get_todos_documentos_processo()) == 0:
                    self.add_error('processos_anexados', f'O processo {processo_anexado} não possui documentos.')
                if not processo_anexado.pode_editar(self.request.user):
                    self.add_error('processos_anexados', f'Você não possui permissão de edição no processo {processo_anexado}')
                if Configuracao.get_valor_por_chave('processo_eletronico', 'bloquear_processos_apensados'):
                    if processo_anexado.apensamentoprocesso_set.exists():
                        self.add_error(
                            'processos_anexados',
                            f'O processo {processo_anexado} possui apenso ou está apensado a outro processo. Desfaça o apensamento antes da anexação.',
                        )
        return self.cleaned_data

    def save(self):
        processos_a_anexar = self.cleaned_data.get('processos_anexados')
        justificativa = self.cleaned_data.get('justificativa')
        for processo_a_anexar in processos_a_anexar:
            self.processo_anexador.anexar(processo_a_anexar, self.request.user, justificativa)


class RelacionarProcessosForm(forms.FormPlus):
    METHOD = 'GET'
    pesquisa = forms.CharField(label='Por Número do Processo:', required=False)
    campus = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.suap(), label=f'{nomenclatura.campus} Dono', required=False, empty_label=f'Selecione {nomenclatura.o_campus}'
    )
    setor = forms.ChainedModelChoiceField(
        Setor.objects.none(),
        label='Por Setor Dono:',
        empty_label='Selecione um Setor',
        required=False,
        obj_label='sigla',
        form_filters=[('campus', 'uo_id')],
    )
    tipo = forms.ModelChoiceField(
        queryset=TipoProcesso.objects, label='Por Tipo de Processo:', required=False, empty_label='Selecione um tipo de processo'
    )

    data_criacao = forms.DateFieldPlus(label='Data de Criação', required=False)

    def __init__(self, *args, **kwargs):
        self.processo_principal = kwargs.pop('processo_principal')
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = Setor.objects.suap_ativos()

    def filtrar_processos(self, retorno, aplicar_filtro_setor_dono=True):
        params = self.request.GET.dict()
        order_str = ''
        if self.is_valid():
            cleaned_data = self.cleaned_data
            pesquisa = cleaned_data.get('pesquisa')
            if pesquisa:
                filtro_identificador = retorno.filter(numero_protocolo__icontains=pesquisa)
                filtro_identificador_fisico = retorno.filter(numero_protocolo_fisico__icontains=pesquisa)
                filtro_assunto = retorno.filter(assunto__icontains=pesquisa)

                retorno = filtro_identificador | filtro_identificador_fisico | filtro_assunto

            tipo = cleaned_data.get('tipo')
            if tipo:
                retorno = retorno.filter(tipo_processo=tipo)

            if aplicar_filtro_setor_dono:
                setor = self.request.GET.get('setores')
                if setor:
                    try:
                        retorno = retorno.filter(setor_dono=setor)
                    except Exception:
                        if setor == 'todos_setores_usuario':
                            # retorno = retorno.filter(setor_criacao__in=get_todos_setores(self.request.user))
                            setores = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=False)
                            retorno = retorno.filter(setor_criacao__in=setores)
                else:
                    setor = cleaned_data.get('setor')
                    if setor:
                        retorno = retorno.filter(setor_criacao=setor)

            data_hora_criacao = cleaned_data.get('data_hora_criacao')
            if data_hora_criacao:
                retorno = retorno.filter(
                    data_hora_criacao__year=data_hora_criacao.year,
                    data_hora_criacao__month=data_hora_criacao.month,
                    data_hora_criacao__day=data_hora_criacao.day,
                )

            if 'order_by' in params:
                order_str = params.pop('order_by', '')
                order_tratado = order_str.replace(' ', '')
                if order_tratado[0] == '-':
                    order_tratado = order_tratado.replace(',', ',-')

                retorno = retorno.order_by(*order_tratado.split(','))

        return retorno, params, order_str

    def processar(self):
        ids_processos_ja_relacionados = self.processo_principal.processos_relacionados.values_list('id', flat=True)
        processos = Processo.objects.by_user(self.request.user).exclude(id=self.processo_principal.id).exclude(id__in=ids_processos_ja_relacionados)
        processos, _params, order_str = self.filtrar_processos(processos)
        order_by = processos.query.order_by
        if not order_by:
            order_by = ['-data_hora_criacao']

        processos = processos.order_by(*order_by)
        return processos, order_str

    def save(self):
        processos_a_relacionar = self.cleaned_data['processos_relacionados']
        for processo in processos_a_relacionar:
            self.processo_principal.processos_relacionados.append(processo)


def assina_com_govbr(user: User) -> bool:
    """Usuário externo sem ocupação ativa assina com Gov.BR; os demais, por senha (#17483)."""
    vinculo = user.get_vinculo()
    return vinculo.eh_usuario_externo() and not vinculo.relacionamento.tem_ocupacao_ativa()


class DocumentoUploadForm(forms.ModelFormPlus):
    assunto = forms.CharFieldPlus(label='Assunto')

    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)
    setor_dono = forms.ModelChoiceFieldPlus2(Setor.objects.suap_ativos().none(), label='Setor Dono')
    vinculos_compartilhados = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Compartilhamentos com Pessoas', required=False)
    tipo_conferencia = forms.ModelChoiceField(label='Tipo de Conferência', queryset=TipoConferencia.objects, widget=forms.Select)

    tipo = forms.ModelChoiceField(
        queryset=TipoDocumento.ativos, widget=AutocompleteWidget(search_fields=TipoDocumento.SEARCH_FIELDS), label='Tipo', required=True
    )

    dono_documento = forms.ModelChoiceFieldPlus(
        Vinculo.objects.none(),
        label='Responsável pelo Documento',
        required=True,
        help_text='Deve ser informada uma pessoa física.',
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )

    instrucoes_gerais = forms.CharFieldPlus(label='')
    ciencia_instrucoes_gerais = forms.BooleanField(label='')

    fieldsets = (
        (
            'Dados do Documento',
            {
                'fields': (
                    'arquivo',
                    'tipo_conferencia',
                    'tipo',
                    'assunto',
                    ('setor_dono', 'dono_documento'),
                )
            },
        ),
        (
            'Nível de Acesso',
            {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal', 'vinculos_compartilhados')},
        ),
        (
            'Dados Adicionais',
            {'fields': (('identificador_numero', 'identificador_ano'), 'identificador_setor_sigla', 'identificador_tipo_documento_sigla')},
        ),
    )

    class Meta:
        model = DocumentoDigitalizado
        fields = (
            'identificador_tipo_documento_sigla',
            'identificador_numero',
            'identificador_ano',
            'identificador_setor_sigla',
            'assunto',
            'arquivo',
            'tipo',
            'nivel_acesso',
            'hipotese_legal',
            'dono_documento',
            'vinculos_compartilhados',
            'setor_dono',
            'tipo_conferencia',
        )

    class Media:
        js = ('/static/processo_eletronico/js/DocumentoUploadEditarForm.js',)

    def __init__(self, *args, **kwargs):
        self.solicitacao = kwargs.pop('solicitacao', False)
        self.processo = kwargs.pop('processo', None) or (self.solicitacao and self.solicitacao.processo or None)
        self.request = kwargs.get('request')

        super().__init__(*args, **kwargs)

        self.max_file_upload_size = settings.PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE
        user = self.request.user if self.request else tl.get_user()
        self.tamanho_maximo_upload_personalizado = Configuracao.get_valor_por_chave(
            app='processo_eletronico', chave='tamanho_maximo_upload_personalizado'
        )
        self.pessoas_permitidas_upload_personalizado = Configuracao.get_valor_por_chave(
            app='processo_eletronico', chave='pessoas_permitidas_realizar_upload_personalizado'
        )
        pessoa_permitida_upload_personalizado = self.pessoas_permitidas_upload_personalizado and str(
            self.request.user.get_profile().id
        ) in self.pessoas_permitidas_upload_personalizado.split(',')

        # O upload serah feito sempre para o setor do user e em caso de não possuir (Usuário Externo) será para o setor atual do processo
        setor_user = get_setor(user) or self.processo.setor_atual

        qs_setores = Tramite.get_todos_setores(user, deve_poder_criar_processo=True) | Setor.objects.suap_ativos().filter(pk=setor_user.id).distinct()
        self.fields['setor_dono'].queryset = qs_setores.distinct()
        self.fields['setor_dono'].initial = setor_user.id

        self.fields['dono_documento'].initial = user.get_vinculo()
        self.fields['dono_documento'].queryset = Vinculo.objects.ativos()

        # Se o upload ocorre devido a uma requisição, então informe um motivo
        if self.solicitacao:
            self.fields['motivo'] = forms.CharField(label='Motivação da Juntada', max_length=255, widget=forms.Textarea, required=True)
            self.fieldsets += (('Juntada de Documentos', {'fields': ('motivo',)}),)
        self.fields['arquivo'].max_file_size = (
            pessoa_permitida_upload_personalizado and settings.DATA_UPLOAD_MAX_MEMORY_SIZE or self.max_file_upload_size
        )

        self.fields['instrucoes_gerais'] = forms.CharFieldPlus(
            label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
        )
        self.fields['ciencia_instrucoes_gerais'] = forms.BooleanField(
            widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.'
        )
        conf_orientacao = ConfiguracaoInstrucaoNivelAcesso.get_orientacao()
        if conf_orientacao:
            self.fields['ciencia_instrucoes_gerais'].required = True
            self.fields['instrucoes_gerais'] = SpanField(widget=SpanWidget(), label='')
            self.fields['instrucoes_gerais'].widget.label_value = mark_safe(f'<br>{conf_orientacao}')
            self.fields['instrucoes_gerais'].widget.original_value = conf_orientacao
            self.fields['instrucoes_gerais'].required = False
        else:
            self.fields['ciencia_instrucoes_gerais'].widget = forms.HiddenInput()
            self.fields['ciencia_instrucoes_gerais'].required = False
            self.fields['instrucoes_gerais'].widget = forms.HiddenInput()

    def clean_arquivo(self):
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content

    def clean(self):
        if self.processo.get_apensamento() and self.cleaned_data.get('nivel_acesso') == DocumentoDigitalizado.NIVEL_ACESSO_SIGILOSO:
            self.add_error('nivel_acesso', 'Não é possível adicionar documento sigiloso em processo apensado.')
        return self.cleaned_data

    @transaction.atomic()
    def save(self, commit: bool = True) -> None:
        try:
            self.instance.setor_dono = self.cleaned_data['setor_dono']
            self.instance.data_ultima_modificacao = get_datetime_now()
            self.instance.usuario_ultima_modificacao = self.request.user
            documento = super().save(False)
            if documento.id:
                documento.data_alteracao = datetime.now()
                documento.usuario_alteracao = self.request.user
            else:
                documento.usuario_criacao = self.request.user
            documento.save()

            ext = self.cleaned_data.get('arquivo').content_type.split('/')[1]
            if ext != 'pdf':
                if not Configuracao.get_valor_por_chave('processo_eletronico', 'permite_anexar_aquivos_media'):
                    raise ValidationError('Operação não permitida')

                file_url = f'{settings.SITE_URL}/documento_eletronico/visualizar_documento_digitalizado/{documento.pk}/?original=sim'

                with tempfile.NamedTemporaryFile(suffix=f'.{ext}', delete=False) as qr_code_file:
                    qr_code_path = qr_code_file.name
                qr = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=2, border=8)
                qr.add_data(file_url)
                qr.make(fit=True)

                img = qr.make_image(fill_color='black', back_color='white')
                img.save(qr_code_path)

                md5 = subprocess.check_output(['md5sum', documento.arquivo.path]).decode()
                md5 = next(token for token in md5.split() if len(token) == 32)
                pdf = PdfWriter()
                imgTemp = BytesIO()
                imgDoc = canvas.Canvas(imgTemp, pagesize=A4)
                imgDoc.drawImage(qr_code_path, 50, 200, 200, 200)
                imgDoc.drawString(40, 720, f'MD5: {md5}')
                imgDoc.drawString(40, 740, f'TAMANHO: {os.path.getsize(documento.arquivo.path)} bytes')
                imgDoc.drawString(40, 760, f'DOCUMENTO: {documento.id}')
                imgDoc.drawString(160, 800, 'DOCUMENTO DE REFERÊNCIA AO ARQUIVO DE MÍDIA')
                imgDoc.setFont(imgDoc.getAvailableFonts()[0], 6)
                imgDoc.drawString(40, 100, file_url)
                imgDoc.save()

                pdf.add_page(PdfReader(BytesIO(imgTemp.getvalue())).pages[0])
                pdf.write(open(f'{documento.arquivo.path}.pdf', 'wb'))

                DocumentoDigitalizado.objects.filter(pk=documento.pk).update(arquivo=f'{documento.arquivo.name}.pdf')

                documento = DocumentoDigitalizado.objects.get(pk=documento.pk)

            # Assina o documento. O passo 2 do wizard já autenticou: AssinarDocumentoForm (senha) ou, para o
            # usuário externo, AssinarDocumentoGovBRForm (sessão Gov.BR, código de verificação e papel). A
            # assinatura gravada é a mesma, como em documento_eletronico.views.assinar_documento_com_gov_br (#17477).
            papel = str(self.request.POST.get('papel', None))
            papel = Papel.objects.get(pk=papel)
            documento.assinar_via_senha(self.request.user, papel)
            # Trata-se apenas de uma resposta a uma requisição de anexação, portanto não vamos adicionar agora.
            if self.solicitacao:
                related_object_type = ContentType.objects.get_for_model(documento)
                SolicitacaoJuntadaDocumento.objects.create(
                    solicitacao_juntada=self.solicitacao,
                    anexo_content_type=related_object_type,
                    anexo_content_id=documento.id,
                    motivo=self.cleaned_data.get('motivo'),
                )
            else:
                #
                # Adicionando o documento ao processo
                DocumentoDigitalizadoProcesso.objects.create(processo=self.processo, documento=documento)
                vinculos_compartilhados = self.cleaned_data.get('vinculos_compartilhados')
                dono_documento = self.cleaned_data.get('dono_documento')
                nivel_acesso = self.cleaned_data.get('nivel_acesso')
                user = tl.get_user()
                if nivel_acesso == Documento.NIVEL_ACESSO_SIGILOSO:
                    CompartilhamentoDocumentoDigitalizadoPessoa.objects.filter(documento=documento).delete()
                    # Compartilhando com o dono
                    compartilhamento = CompartilhamentoDocumentoDigitalizadoPessoa()
                    compartilhamento.documento = documento
                    compartilhamento.vinculo_permitido = dono_documento
                    compartilhamento.data_criacao = datetime.now()
                    compartilhamento.usuario_criacao = user
                    compartilhamento.save()

                    for vinculo in vinculos_compartilhados:
                        compartilhamento = CompartilhamentoDocumentoDigitalizadoPessoa()
                        compartilhamento.documento = documento
                        compartilhamento.vinculo_permitido = vinculo
                        compartilhamento.data_criacao = datetime.now()
                        compartilhamento.usuario_criacao = user
                        compartilhamento.save()
        except Exception as e:
            raise ValidationError(f'{e}')


class DocumentoTextoProcessoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoTextoProcesso
        fields = ('processo', 'documento')


class DocumentoDigitalizadoProcessoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoDigitalizadoProcesso
        fields = ('processo', 'documento')


class ProcessoRemoverForm(forms.ModelFormPlus):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # The form initialization will need to mention a helper attribute
        # of the type FormHelper.
        self.helper = FormHelper(self)
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Div('justificativa_remocao', css_class='search-and-filters'),
            Div(Submit('enviar', 'Enviar', css_class='btn large'), css_class='submit-row'),
        )

    def clean_justificativa_remocao(self):
        message = self.cleaned_data.get('justificativa_remocao', None)
        if message is None:
            raise ValidationError('A remoção deve conter uma motivação.')
        return message

    def save(self, commit=True):
        self.instance.motivo_vinculo_documento_processo_remocao = DocumentoProcesso.MOTIVO_DESENTRANHAMENTO
        self.instance.usuario_remocao = self.request.user
        self.instance.data_hora_remocao = get_datetime_now()
        return super().save(commit)


class DocumentoUploadEditarForm(forms.ModelFormPlus):
    # Utilizado apenas para alterar os dados basicos
    # Para alterar nivel de acesso deve acessar form especifico

    class Meta:
        model = DocumentoDigitalizado
        fields = (
            'identificador_tipo_documento_sigla',
            'identificador_numero',
            'identificador_ano',
            'identificador_setor_sigla',
            'assunto',
            'tipo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = getattr(self, 'instance', None)
        if self.instance and self.instance.pk:
            self.fields['identificador_tipo_documento_sigla'].widget.attrs['readonly'] = True
            self.fields['identificador_numero'].widget.attrs['readonly'] = True
            self.fields['identificador_ano'].widget.attrs['readonly'] = True
            self.fields['identificador_setor_sigla'].widget.attrs['readonly'] = True


class DocumentoTextoProcessoRemoverForm(ProcessoRemoverForm, forms.ModelFormPlus):
    class Meta:
        model = DocumentoTextoProcesso
        fields = ('justificativa_remocao',)


class DocumentoDigitalizadoProcessoRemoverForm(ProcessoRemoverForm, forms.ModelFormPlus):
    class Meta:
        model = DocumentoDigitalizadoProcesso
        fields = ('justificativa_remocao',)


# Constante utilizada nos forms ProcessoFormCadastrarComTramite e ProcessoFormEditar.
side_html = """\
    Adicionar
    <a href="/admin/comum/prestadorservico/add/" class="add-another" title="Adicionar Usuário Externo..."
        onclick="return showAddAnotherPopup(this);">
        Usuário Externo ?
    </a>
"""


class TramiteFormEncaminhar(forms.ModelFormPlus):
    despacho_corpo = forms.CharField(label='Despacho', widget=forms.Textarea(attrs={'autocomplete': 'texto-despacho'}))
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Meta:
        model = Tramite
        fields = ['despacho_corpo']

    def __init__(self, *args, **kwargs):
        self.despacho = kwargs.pop('despacho', None)
        super().__init__(*args, **kwargs)

        self.fieldsets = (
            (
                'Dados da Tramitação',
                {
                    'fields': (
                        'despacho_corpo',
                        'tipo_busca_setor',
                        'destinatario_uo',
                        'destinatario_setor_autocompletar',
                        'destinatario_setor_arvore',
                        'destinatario_vinculo',
                    )
                },
            ),
        )

        from .utils import usuario_pode_cadastrar_retorno_programado

        if (
            self.instance.processo.setor_atual
            and usuario_pode_cadastrar_retorno_programado(self.request.user, self.instance.processo.setor_atual)
            and self.instance.processo.setor_atual.setores_permitidos_retorno_programado_set.exists()
        ):
            if not self.instance.processo.ultimo_tramite or not self.instance.processo.ultimo_tramite.eh_gerador_retorno_programado_pendente:
                self.fieldsets += (('Retorno Programado', {'fields': ('data_retorno_programado',)}),)

        if not self.despacho:
            del self.fields['despacho_corpo']
            del self.fields['senha']
            del self.fields['papel']
        else:
            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'].queryset = vinculo.papeis_ativos
            self.fieldsets += (('Autenticação', {'fields': ('papel', 'senha')}),)

    def clean(self):
        self.instance.processo.verificar_dados_processo()
        return self.cleaned_data


class TramiteFormEncaminharParaSetor(TramiteFormEncaminhar):
    TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Autocompletar'), ('arvore', 'Árvore'))
    tipo_busca_setor = forms.ChoiceField(widget=forms.RadioSelect(), choices=TIPO_BUSCA_SETOR_CHOICE, label='Buscar setor de destino por:')

    destinatario_uo = forms.ModelChoiceFieldPlus(label=nomenclatura.campus, queryset=UnidadeOrganizacional.objects.suap(), required=False)
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino',
        queryset=Setor.objects.none(),
        required=False,
        widget=AutocompleteWidget(form_filters=[('destinatario_uo', 'uo_id')]),
    )
    destinatario_setor_arvore = forms.ModelChoiceField(label='Setor de Destino', queryset=Setor.objects.none(), required=False, widget=TreeWidget())
    data_retorno_programado = forms.DateFieldPlus(label='Data para Retorno do Processo', required=False)

    class Media:
        js = ('/static/processo_eletronico/js/TramiteFormEncaminhar.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if get_setor(self.request.user) is None:
            raise ValidationError('Usuário não possui setor definido.')
        self.fields['destinatario_setor_arvore'].queryset = Setor.objects.suap_ativos()
        self.fields['destinatario_setor_autocompletar'].queryset = Setor.objects.suap_ativos()
        self.initial['tipo_busca_setor'] = 'autocompletar'
        self.initial['destinatario_uo'] = get_setor(self.request.user).uo_id
        # Este campo está sendo utilizado para distribuição de trâmite e não para tramite de processo sigilosos
        # Ele foi utilizado, pois já constava no fieldsets do form TramiteFormEncaminhar
        if Configuracao.get_valor_por_chave('processo_eletronico', 'permite_distribuir_ao_tramitar'):
            qs = Vinculo.objects.filter(ativo=True, tipo_relacionamento=ContentType.objects.get(Vinculo.SERVIDOR))
            self.fields['destinatario_vinculo'] = forms.ModelChoiceField(
                label='Destinatário',
                queryset=qs,
                widget=AutocompleteWidget(form_filters=[('destinatario_uo', 'setor__uo'), ('destinatario_setor_autocompletar', 'setor')]),
                required=False,
                help_text='Informe a matrícula, CPF (somente números) ou nome para buscar destinatário.',
            )

    def clean_destinatario_vinculo(self):
        destinatario_setor_autocompletar = self.cleaned_data.get('destinatario_setor_autocompletar')
        destinatario_vinculo = self.cleaned_data.get('destinatario_vinculo')
        if destinatario_setor_autocompletar and destinatario_vinculo:
            if not Processo.setores_que_posso_trabalhar_nos_processos(
                [Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO, Processo.PERMISSAO_OPERAR_PROCESSO], destinatario_vinculo.user
            ).filter(pk=destinatario_setor_autocompletar.pk):
                raise ValidationError('O processo só pode ser destinado a servidores habilitados.')
        return destinatario_vinculo

    def save(self):
        tramite = self.instance

        # Dados de quem está fazendo o encaminhamento.
        destinatario_setor = None
        # Setor de destino do encaminhamento.
        if self.is_tipo_busca_setor_arvore() and self.cleaned_data['destinatario_setor_arvore']:
            destinatario_setor = self.cleaned_data['destinatario_setor_arvore']

        elif self.is_tipo_busca_setor_autocompletar() and self.cleaned_data['destinatario_setor_autocompletar']:
            destinatario_setor = self.cleaned_data['destinatario_setor_autocompletar']

        tramite.tramitar_processo(
            remetente_setor=tramite.processo.setor_atual,
            remetente_vinculo=self.request.user.get_vinculo(),
            despacho_corpo=self.cleaned_data.get('despacho_corpo', None),
            destinatario_setor=destinatario_setor,
            destinatario_vinculo=None,
            assinar_tramite=self.despacho,
            papel=self.cleaned_data.get('papel', None),
        )
        if self.cleaned_data.get('destinatario_vinculo'):
            TramiteDistribuicao.objects.create(setor=destinatario_setor, distribuir_para=self.cleaned_data.get('destinatario_vinculo'))
            tramite.atribuido_para = self.cleaned_data.get('destinatario_vinculo')
            tramite.atribuido_por = self.request.user.get_vinculo()
            tramite.atribuido_em = datetime.now()
        tramite.save()
        # adiciona o retorno programado
        from .models import TramiteRetornoProgramado

        if self.cleaned_data['data_retorno_programado']:
            retorno_programado = TramiteRetornoProgramado()
            retorno_programado.tramite_gerador = tramite
            retorno_programado.data_prevista_retorno = self.cleaned_data['data_retorno_programado']
            retorno_programado.save()
        elif tramite.eh_resposta_retorno_programado:
            # atualiza data_efetiva retorno e tramite_retorno caso seja resposta de retorno programado
            retorno_programado = TramiteRetornoProgramado.objects.filter(
                tramite_gerador__processo=tramite.processo, data_prevista_retorno__isnull=False, data_efetiva_retorno__isnull=True
            ).first()
            retorno_programado.data_efetiva_retorno = get_datetime_now().date()
            retorno_programado.tramite_retorno = tramite
            retorno_programado.save()

    def clean(self):
        super().clean()
        if self.is_tipo_busca_setor_arvore() and not self.cleaned_data.get('destinatario_setor_arvore'):
            self._errors['destinatario_setor_arvore'] = forms.ValidationError(['É obrigatório informar um setor.'])

        if self.is_tipo_busca_setor_autocompletar() and not self.cleaned_data.get('destinatario_setor_autocompletar'):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(['É obrigatório informar um setor.'])

        if 'destinatario_setor_autocompletar' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_autocompletar')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )

        if 'destinatario_setor_arvore' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_arvore')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_arvore'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )

        if 'data_retorno_programado' in self.cleaned_data:
            data_retorno = self.cleaned_data.get('data_retorno_programado')
            if not self.instance.eh_resposta_retorno_programado and data_retorno and data_retorno <= datetime.today().date():
                self._errors['data_retorno_programado'] = forms.ValidationError(
                    ['A data de retorno programado informada deve ser posterior a data atual.']
                )

        ultimo_tramite = self.instance.processo.ultimo_tramite
        if (
            ultimo_tramite
            and ultimo_tramite.eh_gerador_retorno_programado_pendente
            and ultimo_tramite.remetente_setor != self.cleaned_data.get('destinatario_setor_autocompletar')
        ):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                [
                    'O processo {0} foi encaminhando de {1} com Data de Retorno programada para {2}, desta forma só poderá ser tramitado para {1}.'.format(
                        self.instance.processo.numero_protocolo_fisico,
                        ultimo_tramite.remetente_setor,
                        ultimo_tramite.get_retorno_programado().data_prevista_retorno.strftime('%d/%m/%Y'),
                    )
                ]
            )

        return self.cleaned_data

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'


class TramiteFormEncaminharParaPessoa(TramiteFormEncaminhar):
    destinatario_vinculo = forms.ModelChoiceField(
        label='Destinatário',
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(side_html=side_html),
        required=True,
        help_text='Informe a matrícula, CPF (somente números) ou nome para buscar destinatário.',
    )

    def clean_destinatario_vinculo(self):
        destinatario_vinculo: Vinculo = self.cleaned_data.get('destinatario_vinculo')
        if self.instance.processo.eh_privado and not pode_receber_processo_privado(destinatario_vinculo):
            setor = destinatario_vinculo.setor
            msg = f'O procurador selecionado não pode receber processo privados. Por Favor, encaminhe o processo para {setor}.'
            self.add_error('destinatario_vinculo', msg)
        return destinatario_vinculo

    def clean(self):
        super().clean()

        ultimo_tramite = self.instance.processo.ultimo_tramite
        if (
            ultimo_tramite
            and ultimo_tramite.eh_gerador_retorno_programado_pendente
            and ultimo_tramite.remetente_vinculo != self.cleaned_data.get('destinatario_vinculo')
        ):
            self._errors['destinatario_vinculo'] = forms.ValidationError(
                [
                    f'O processo {0} foi encaminhando de {1} com Data de Retorno programada para {2}, desta forma só'
                    f' poderá ser tramitado para o {1}.'.format(
                        self.instance.processo.numero_protocolo_fisico, ultimo_tramite.remetente_vinculo, ultimo_tramite.data_retorno_programada
                    )
                ]
            )
        return self.cleaned_data

    def save(self):
        tramite = self.instance
        # Dados de quem está fazendo o encaminhamento.
        tramite.tramitar_processo(
            remetente_vinculo=self.request.user.get_vinculo(),
            remetente_setor=get_setor(self.request.user),
            despacho_corpo=self.cleaned_data.get('despacho_corpo', None),
            destinatario_vinculo=self.cleaned_data['destinatario_vinculo'],
            destinatario_setor=None,
            assinar_tramite=self.despacho,
            papel=self.cleaned_data.get('papel', None),
        )


def TramiteFormEncaminharFactory(tramite, request_method=None, request=None, despacho=True):
    if tramite.processo.eh_privado():
        return TramiteFormEncaminharParaPessoa(data=request_method, instance=tramite, request=request, despacho=despacho)
    else:
        return TramiteFormEncaminharParaSetor(data=request_method, instance=tramite, request=request, despacho=despacho)


class TramiteFormReceber(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Receber'

    class Meta:
        model = Tramite
        fields = []

    class Media:
        js = [
            '/static/processo_eletronico/js/TramiteFormReceber.js',
            '/static/tinymce/tiny_mce_toolbar.js',
            '/static/tinymce/js/tinymce/tinymce.min.js',
        ]

    def save(self, *args, **kwargs):
        tramite = self.instance
        tramite.receber_processo(recebido_por=self.request.user.get_vinculo(), data_hora_recebimento=datetime.today())


class TramiteFormEncaminharViaBarramento(forms.FormPlus):
    destinatario_externo_repositorio_id = forms.ChoiceField(label='Repositório de Estruturas Organizacionais', required=False, widget=forms.Select())

    destinatario_externo_estrutura_id = forms.CharField(label='Unidade de Destino', required=False, widget=forms.Select(choices=[]))

    class Media:
        js = ('/static/processo_eletronico/js/TramiteFormEncaminhar.js',)

    def __init__(self, *args, **kwargs):
        # self.processo = kwargs.pop('processo')
        from conectagov_pen.api_pen_services import get_repositorios
        from conectagov_pen.utils import dict_to_choices

        super().__init__(*args, **kwargs)
        self.fields['destinatario_externo_repositorio_id'].choices = dict_to_choices(get_repositorios(), 'id', 'nome')
        self.fields['destinatario_externo_repositorio_id'].initial = ((),)

    def save(self, *args, **kwargs):
        from conectagov_pen.views import envia_processo

        processo = kwargs.get('processo')
        envia_processo(
            self.request,
            processo.id,
            self.cleaned_data.get('destinatario_externo_repositorio_id'),
            self.cleaned_data.get('destinatario_externo_estrutura_id'),
        )

    def clean(self):
        super().clean()
        if not self.cleaned_data.get('destinatario_externo_repositorio_id'):
            self._errors['destinatario_externo_repositorio_id'] = forms.ValidationError(['É obrigatório informar um reposítório de estruturas.'])

        if not self.cleaned_data.get('destinatario_externo_estrutura_id'):
            self._errors['destinatario_externo_estrutura_id'] = forms.ValidationError(['É obrigatório informar uma instituição/unidade de destino.'])

        return self.cleaned_data


class ReativarProcessoEncaminhadoExternamenteForm(forms.FormPlus):
    INFO = (
        'Atenção: Esta ação somente deverá ser executada em casos que '
        'não seja possível o retorno do processo por tramitação externa, como por exemplo: Indisponibilidade do TramitaGov ou Erro no Sistema do Órgão Externo'
    )

    justificativa = forms.CharFieldPlus(label='Justificativa', required=True)
    senha = forms.PasswordField(required=True)


class ProcessoFormEditarInteressados(forms.FormPlus):
    processo = forms.CharFieldPlus()
    grupo_interessados = forms.ModelChoiceFieldPlus(
        GrupoInteressadosProcesso.objects.none(),
        label='Grupo de Interessados',
        required=False,
        help_text=mark_safe(
            'Clique aqui para <a target="_blank" href="/admin/processo_eletronico/grupointeressadosprocesso/">gerenciar grupos de interessados em um outra aba.</a>'
        ),
    )
    interessados = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects, label='Interessados', required=True)
    observacao_alteracao_interessados = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())
    senha = forms.PasswordField()

    fieldsets = (
        ('Dados dos interessados', {'fields': ('processo', 'grupo_interessados', 'interessados', 'observacao_alteracao_interessados')}),
        ('Autenticação', {'fields': ('senha',)}),
    )

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')

        super().__init__(*args, **kwargs)
        self.permitir_grupos_interessados = Configuracao.get_valor_por_chave('processo_eletronico', 'permitir_grupos_interessados')
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True
        # self.fields['interessados'].queryset = Pessoa.objects.all().order_by_relevance()
        self.fields['interessados'].initial = self.processo.interessados.all()

        if self.permitir_grupos_interessados:
            self.fields['interessados'].required = False
            self.fields['grupo_interessados'].queryset = GrupoInteressadosProcesso.objects.filter(usuario=self.request.user)
        else:
            self.fields['grupo_interessados'].widget = forms.HiddenInput()

    def clean_interessados(self):
        interessados = self.cleaned_data.get('interessados', ())
        grupo_interessados = GrupoInteressadosProcesso.objects.filter(pk=self.data.get('grupo_interessados') or 0).first()

        vinculos = list(interessados)
        if grupo_interessados:
            vinculos.extend(list(grupo_interessados.interessados.all()))

        invalidos = []
        for vinculo in vinculos:
            if not vinculo.cpf_ou_cnpj_valido():
                invalidos.append(f'{vinculo}')

        if invalidos:
            self.add_error('interessados', 'Os seguintes interessados não possuem CPF ou CNPJ válidos: {}.'.format(', '.join(invalidos)))
        if not vinculos:
            self.add_error('interessados', 'Um ou mais interessados devem ser informados.')

        return vinculos


class ProcessoFormFinalizar(PapelForm):
    processo = forms.CharFieldPlus(label='Processo Principal')
    observacao_finalizacao = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())
    nivel_acesso = forms.ChoiceField(
        label='Nível de acesso', choices=Documento.NIVEL_ACESSO_CHOICES, initial=Documento.NIVEL_ACESSO_PUBLICO, required=True
    )
    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True

    class Media:
        js = ('/static/processo_eletronico/js/NivelAcesso.js',)

    def clean(self):
        if self.processo.possui_pendencias_documentais():
            raise forms.ValidationError('O processo possui pendências e não pode ser finalizado.')


class ProcessoFormDesfinalizar(PapelForm):
    processo = forms.CharFieldPlus()
    observacao_desfinalizacao = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())
    nivel_acesso = forms.ChoiceField(
        label='Nível de acesso', choices=Documento.NIVEL_ACESSO_CHOICES, initial=Documento.NIVEL_ACESSO_PUBLICO, required=True
    )
    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True

    class Media:
        js = ('/static/processo_eletronico/js/NivelAcesso.js',)

    def save(self):
        processo = self.processo
        processo.data_finalizacao = None
        processo.usuario_finalizacao = None
        processo.observacao_finalizacao = ''
        processo.colocar_em_tramite()
        processo.save()


class ProcessoFormArquivado(forms.FormPlus):
    processo = forms.CharFieldPlus()
    observacao_finalizacao = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True

    # def clean(self, ):
    #     for previa_processo in self.processo.get_previas_processo():
    #         if not previa_processo.pode_finalizar():
    #             self._errors['processo'] = forms.ValidationError(
    #                 [u"O processo não pode ser finalizado, pois existem minutas em aberto."]
    #             )
    #             break
    #     return self.cleaned_data

    def save(self):
        processo = self.processo
        processo.data_finalizacao = datetime.today()
        processo.usuario_finalizacao = self.request.user
        processo.observacao_finalizacao = self.cleaned_data['observacao_finalizacao']
        processo.arquivar_processo()
        processo.save()


class AdicionarComentario(forms.ModelFormPlus):
    class Meta:
        model = ComentarioProcesso
        fields = ['comentario']


class RequerimentoForm(forms.FormPlus):
    class Media:
        js = ('/static/processo_eletronico/js/TramiteFormEncaminhar.js',)

    TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Autocompletar'), ('arvore', 'Árvore'))
    tipo_busca_setor = forms.ChoiceField(widget=forms.RadioSelect(), choices=TIPO_BUSCA_SETOR_CHOICE, label='Buscar Setor por')
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=AutocompleteWidget()
    )
    destinatario_setor_arvore = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=TreeWidget()
    )
    assunto = forms.ModelPopupChoiceField(
        TipoProcesso.objects.ativos().exclude(nivel_acesso_default=Processo.NIVEL_ACESSO_PRIVADO), label='Assunto', required=True
    )
    informacoes_extra = forms.CharField(label='Informações Complementares', max_length=1000, widget=forms.Textarea, required=True)
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    fieldsets = (
        (
            '',
            {
                'fields': (
                    'tipo_busca_setor',
                    'destinatario_setor_autocompletar',
                    'destinatario_setor_arvore',
                    'assunto',
                    'informacoes_extra',
                    ('papel', 'senha'),
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.tipo_processo = None
        self.tipo_documento_requerimento = None
        self.assunto = None
        self.servidor = self.request.user.get_relacionamento()
        self.vinculo = self.request.user.get_relacionamento()
        self.fields['papel'].queryset = self.vinculo.papeis_ativos
        self.helper = FormHelper()

    def hash_data(self):
        content = ','.join(f'{n}:{self.data[n]}' for n in list(self.fields.keys()))
        return gerar_hash(content)

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)
        else:
            return self.cleaned_data.get('destinatario_setor_arvore', None)

    def clean(self):
        try:
            self.tipo_documento_requerimento = TipoDocumento.objects.get(
                pk=Configuracao.get_valor_por_chave('documento_eletronico', 'tipo_documento_requerimento')
            )
        except TipoDocumento.DoesNotExist:
            raise ValidationError(
                'Para criar um requerimento se faz necessário definir a configuração "Tipo de Documento para Requerimento" do módulo "Documento Eletrônico".'
            )

        if self.is_tipo_busca_setor_arvore() and not self.cleaned_data.get('destinatario_setor_arvore'):
            self._errors['destinatario_setor_arvore'] = forms.ValidationError(['É obrigatório informar um setor.'])
        if self.is_tipo_busca_setor_autocompletar() and not self.cleaned_data.get('destinatario_setor_autocompletar'):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(['É obrigatório informar um setor.'])
        if 'destinatario_setor_autocompletar' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_autocompletar')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )
        if 'destinatario_setor_arvore' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_arvore')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_arvore'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )
        self.tipo_processo = self.cleaned_data.get('assunto')
        self.assunto = str(self.cleaned_data.get('assunto'))

        return self.cleaned_data

    def _get_nivel_acesso_padrao(self):
        if self.tipo_processo.nivel_acesso_default == Processo.NIVEL_ACESSO_PUBLICO:
            return Documento.NIVEL_ACESSO_PUBLICO
        if self.tipo_processo.nivel_acesso_default == Processo.NIVEL_ACESSO_PRIVADO:
            return Documento.NIVEL_ACESSO_SIGILOSO
        else:
            return Documento.NIVEL_ACESSO_RESTRITO

    @transaction.atomic()
    def save(self, user, content):
        interessado = user.get_vinculo()
        if not interessado:
            raise ValidationError('O campo interessado é vazio.')

        processo = Processo.objects.create(
            tipo_processo=self.tipo_processo, assunto=self.assunto, nivel_acesso=self.tipo_processo.nivel_acesso_default
        )
        processo.adicionar_interessado(interessado)

        # Esse artifício de chamar o save se faz necessário para que o método "procotolo_eletronico_post_save" de
        # "signals.py" seja invocado e crie o processo físico, gerando assim o Nup17.
        processo.save()

        qs = DocumentoDigitalizado.objects.all()
        pk = 0
        if qs.exists():
            pk = qs.latest('id').id

        documento = DocumentoDigitalizado()
        documento.identificador_tipo_documento_sigla = self.tipo_documento_requerimento.sigla
        documento.identificador_numero = pk + 1
        documento.identificador_ano = datetime.now().year
        documento.identificador_setor_sigla = get_setor(user).sigla
        documento.tipo = self.tipo_documento_requerimento
        documento.interno = True
        documento.tipo_conferencia = TipoConferencia.objects.get(descricao='Cópia Simples')
        documento.usuario_criacao = user
        documento.data_ultima_modificacao = datetime.now()
        documento.usuario_ultima_modificacao = user
        documento.data_emissao = datetime.now()
        documento.setor_dono = get_setor(user)
        documento.dono_documento = user.get_vinculo()
        documento.data_criacao = datetime.now()
        documento.assunto = self.assunto
        documento.nivel_acesso = self._get_nivel_acesso_padrao()
        documento.arquivo.save('requerimento.html', ContentFile(content))
        # Assina o documento de acordo com o papel selecionado na tela
        papel_id = str(self.request.POST.get('papel', None))
        papel = Papel.objects.get(pk=papel_id)
        documento.assinar_via_senha(self.request.user, papel)
        documento.save()

        documento_processo = DocumentoDigitalizadoProcesso()
        documento_processo.processo = processo
        documento_processo.documento = documento
        documento_processo.data_hora_inclusao = datetime.now()
        documento_processo.usuario_inclusao = user
        documento_processo.motivo_vinculo_documento_processo_inclusao = DocumentoProcesso.MOTIVO_ANEXACAO
        documento_processo.save()

        return processo


class SolicitacaoCienciaForm(forms.FormPlus):
    processo = forms.CharFieldPlus()
    interessados = forms.ModelMultiplePopupChoiceField(
        queryset=Vinculo.objects.none(),
        label='Interessados',
        help_text='São listados interessados que possuem usuário (alunos apenas se maiores de idade).',
    )
    data_limite_ciencia = forms.DateFieldPlus(label='Data Limite da Ciência')
    motivo = forms.CharField(label='Justificativa da Solicitação', max_length=500, widget=forms.Textarea, required=True)
    permitir_juntada = forms.BooleanField(widget=forms.CheckboxInput, required=False, label='Permitir Juntada?')
    data_limite_juntada = forms.DateFieldPlus(label='Data Limite da Juntada', required=False)
    tipo_ciencia = forms.ChoiceField(widget=forms.RadioSelect(), choices=SolicitacaoCiencia.TIPO_CHOICES, label='Tipo da Ciência')

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True
        vinculo_logado = self.request.user.get_vinculo()
        # TODO: No filter de interessados para dar ciência em processo tinha vinculo__setor__isnull=False,
        # porém removi pois o Usuários Externo não terá setor
        relacionamento_aluno = ContentType.objects.get(app_label='edu', model='aluno')
        interessados_qs = self.processo.interessados.filter(user__isnull=False).exclude(id=vinculo_logado.id)

        data_corte_maioridade = get_datetime_now().date() - relativedelta(years=18)
        aluno_menor_ou_sem_data = Q(tipo_relacionamento=relacionamento_aluno) & (
            Q(pessoa__pessoafisica__nascimento_data__isnull=True) | Q(pessoa__pessoafisica__nascimento_data__gt=data_corte_maioridade)
        )
        self.fields['interessados'].queryset = interessados_qs.exclude(aluno_menor_ou_sem_data)
        if self.processo.ultimo_tramite is None:
            del self.fields['permitir_juntada']
            del self.fields['data_limite_juntada']

    def clean_data_limite_ciencia(self):
        data_limite_ciencia = self.cleaned_data.get('data_limite_ciencia')
        if data_limite_ciencia:
            data_limite_ciencia = datetime.combine(data_limite_ciencia, time.max)
        return data_limite_ciencia

    def clean_data_limite_juntada(self):
        data_limite_juntada = self.cleaned_data.get('data_limite_juntada')
        if data_limite_juntada:
            data_limite_juntada = datetime.combine(data_limite_juntada, time.max)
        return data_limite_juntada

    def clean(self):
        cleaned_data = super().clean()
        data_limite_ciencia = cleaned_data.get('data_limite_ciencia', None)
        data_limite_juntada = cleaned_data.get('data_limite_juntada', None)
        permitir_juntada = cleaned_data.get('permitir_juntada', False)
        interessados = cleaned_data.get('interessados', [])

        if data_limite_ciencia and data_limite_ciencia < datetime.today():
            self.add_error('data_limite_ciencia', 'A Data Limite para a Ciência deve ser maior do que a Data de Hoje')

        # Verifica se o usuário definiu uma data limite de juntada e não marcou o check-box
        if self.processo.ultimo_tramite and not permitir_juntada and data_limite_juntada is not None:
            self.add_error('permitir_juntada', 'Esse campo deve estar marcado para permitir juntada.')

        if permitir_juntada:
            if data_limite_juntada is None:
                self.add_error('data_limite_juntada', 'O campo Data Limite da Juntada deve ser informado.')
            elif data_limite_ciencia and data_limite_juntada <= data_limite_ciencia:
                self.add_error('data_limite_juntada', 'A Data Limite para a juntada de documentos deve ser maior do que a Data Limite para ciência.')

        if not interessados:
            self.add_error('interessados', 'Adicione pelo menos um interessado.')

        for interessado in interessados:
            if interessado.eh_aluno() and not interessado.eh_maior_de_idade(referencia=get_datetime_now().date()):
                self.add_error(
                    'interessados',
                    f'{interessado.nome_usual} é Aluno menor de idade (ou sem data de nascimento) e não pode receber Solicitação de Ciência/Juntada.',
                )

        for interessado in interessados:
            if interessado.eh_aluno():
                try:
                    interessado.relacionamento.criar_papel_discente()
                except Exception:
                    pass
            try:
                papel = interessado.relacionamento.papeis_ativos.first()
                if not papel:
                    raise Exception
            except Exception:
                self.add_error('interessados', f'O solicitado {interessado.nome} não possui papel ativo!')

        return self.cleaned_data


class CienciaForm(PapelForm):
    ciencia = forms.BooleanField(label='Declaro-me ciente', required=True)
    user = forms.CharField(label='Usuário')
    senha = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            vinculo = self.request.user.get_vinculo()
            if vinculo and vinculo.eh_aluno():
                aluno = self.request.user.get_relacionamento()
                aluno.criar_papel_discente()
                vinculo_rel = self.request.user.get_relacionamento()
                self.fields['papel'].queryset = vinculo_rel.papeis_ativos
                if vinculo_rel.papeis_ativos.count() == 1:
                    self.fields['papel'].initial = vinculo_rel.papeis_ativos.first().id
        except Exception:
            pass

        self.fields['user'].initial = self.request.user
        self.fields['user'].widget.attrs['readonly'] = True

    def clean(self):
        user = self.request.user
        senha = self.cleaned_data.get('senha')
        usuario_autenticado = None
        if senha:
            try:
                usuario_autenticado = authenticate(self.request, username=user.username, password=senha)
            except UserMustResetPassword:
                self.add_error('senha', 'É necessário alterar sua senha antes do próximo login.')
            except LoginException as e:
                self.add_error('senha', str(e))
        if not usuario_autenticado or usuario_autenticado != user:
            self.add_error('senha', 'Senha não confere.')

        return self.cleaned_data


class CienciaGovBRForm(PapelForm, AuthenticationGovBRForm):
    ciencia = forms.BooleanField(label='Declaro-me ciente', required=True)
    user = forms.CharField(label='Usuário')
    # codigo_verificacao = forms.CharField(help_text="Código enviado para seu aplicativo Gov.BR!")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        try:
            vinculo = self.request.user.get_vinculo()
            if vinculo and vinculo.eh_aluno():
                aluno = self.request.user.get_relacionamento()
                aluno.criar_papel_discente()
                vinculo_rel = self.request.user.get_relacionamento()
                self.fields['papel'].queryset = vinculo_rel.papeis_ativos
                if vinculo_rel.papeis_ativos.count() == 1:
                    self.fields['papel'].initial = vinculo_rel.papeis_ativos.first().id
        except Exception:
            pass

        self.fields['user'].initial = self.request.user
        self.fields['user'].widget.attrs['readonly'] = True

    def clean(self):
        return super().clean()


class SenhaForm(forms.FormPlus):
    user = forms.CharField(label='Usuário')
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].initial = self.request.user
        self.fields['user'].widget.attrs['readonly'] = True


class EditarModeloDespachoForm(forms.ModelFormPlus):
    class Meta:
        model = ModeloDespacho
        fields = ('cabecalho', 'rodape')

    class Media:
        js = [
            '/static/processo_eletronico/js/EditarModeloDespachoForm.js',
            '/static/tinymce/tiny_mce_toolbar.js',
            '/static/tinymce/js/tinymce/tinymce.min.js',
        ]

    def clean_cabecalho(self):
        cabecalho = self.cleaned_data.get('cabecalho')
        if len(cabecalho) > 100 * 1024:
            raise ValidationError('Cabeçalho muito grande.')
        return cabecalho

    def clean_rodape(self):
        rodape = self.cleaned_data.get('rodape')
        if len(rodape) > 100 * 1024:
            raise ValidationError('Rodapé muito grande.')
        return rodape


class ProcessoMinutaRemoverForm(forms.ModelFormPlus):
    user = forms.CharField(label='Usuário')
    senha = forms.PasswordField()

    class Meta:
        model = ProcessoMinuta
        fields = ('justificativa_remocao',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].initial = self.request.user
        self.fields['user'].widget.attrs['readonly'] = True
        # The form initialization will need to mention a helper attribute
        # of the type FormHelper.
        self.helper = FormHelper(self)
        self.helper.form_class = 'form-horizontal'
        self.helper.layout = Layout(
            Div('justificativa_remocao', css_class='action-bar search-and-filters'),
            Div(Submit('enviar', 'Enviar', css_class='btn large'), css_class='submit-row'),
        )

    def clean_justificativa_remocao(self):
        message = self.cleaned_data.get('justificativa_remocao', None)
        if message is None:
            raise ValidationError('A remoção deve conter uma motivação.')
        return message

    def save(self, commit=True):
        self.instance.usuario_remocao = self.request.user
        self.instance.data_hora_remocao = get_datetime_now()
        return super().save(commit)


# Demanda_497
class PrioridadeTramiteForm(forms.ModelFormPlus):
    processo = forms.CharFieldPlus(label='Processo')
    prioridade = forms.ChoiceField(widget=forms.RadioSelect(), choices=PrioridadeTramite.PRIORIDADE_CHOICES, label='Prioridade')
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    class Meta:
        model = PrioridadeTramite
        fields = ['processo', 'prioridade', 'justificativa']

    def __init__(self, *args, **kwargs):
        self.tramite = kwargs.pop('tramite')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.tramite.processo
        self.fields['processo'].widget.attrs['readonly'] = True

    def save(self, commit=True):
        self.instance.tramite = self.tramite
        return super().save(commit)


class SolicitarDespachoForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(
        label='Processo', queryset=Processo.objects, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS, readonly=True), required=True
    )
    #
    solicitado = forms.ModelChoiceField(
        label='Solicitar Assinatura a', queryset=Vinculo.objects.none(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), required=True
    )
    senha = forms.PasswordField()

    class Meta:
        model = SolicitacaoDespacho
        fields = ['processo', 'despacho_corpo', 'solicitado']

    class Media:
        js = ('/static/processo_eletronico/js/SolicitarDespacho.js',)

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        vinculo_logado = self.request.user.get_vinculo()
        relacionamento_aluno = ContentType.objects.get(app_label='edu', model='aluno')
        qs = Vinculo.objects.filter(user__isnull=False).exclude(id=vinculo_logado.id)
        self.fields['solicitado'].queryset = qs.exclude(tipo_relacionamento=relacionamento_aluno)

    def clean_solicitado(self):
        vinculo = self.request.user.get_vinculo()
        remetente_vinculo = self.cleaned_data.get('solicitado')
        if remetente_vinculo.get_cpf_ou_cnpj() == vinculo.get_cpf_ou_cnpj():
            self.add_error('solicitado', 'Uma solicitação deve ser destinada a outra pessoa (CPF).')
        return self.cleaned_data.get('solicitado')

    def save(self, commit=False):
        instance = super().save(commit=False)
        instance.processo = self.processo
        instance.remetente_vinculo = self.request.user.get_vinculo()
        instance.remetente_setor = self.processo.setor_atual
        return instance


class SolicitarDespachoPessoaForm(SolicitarDespachoForm):
    # Dados para encamihar para pessoa
    destinatario_vinculo_tramite = forms.ModelChoiceField(
        label='Pessoa de Destino do Trâmite', queryset=Vinculo.objects.all(), widget=AutocompleteWidget(side_html=side_html), required=True
    )

    class Meta:
        model = SolicitacaoDespacho
        fields = ['processo', 'despacho_corpo', 'solicitado', 'destinatario_vinculo_tramite']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    def save(self, commit=False):
        instance = super().save(commit=False)
        instance.save()
        return instance


class SolicitarDespachoSetorForm(SolicitarDespachoForm):
    # Dados para encaminhar para setor
    TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Autocompletar'), ('arvore', 'Árvore'))
    tipo_busca_setor = forms.ChoiceField(
        widget=forms.RadioSelect(), choices=TIPO_BUSCA_SETOR_CHOICE, label='Setor de Destino do Trâmite (Buscar por)'
    )
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Especificar Setor', queryset=Setor.objects.none(), required=False, widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS)
    )
    destinatario_setor_arvore = forms.ModelChoiceField(label='Especificar Setor', queryset=Setor.objects.none(), required=False, widget=TreeWidget())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destinatario_setor_autocompletar'].queryset = Setor.objects.suap_ativos()
        self.fields['destinatario_setor_arvore'].queryset = Setor.objects.suap_ativos()
        self.modelo_despacho = ModeloDespacho.objects.all().first()

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)
        else:
            return self.cleaned_data.get('destinatario_setor_arvore', None)

    def clean(self):
        if self.is_tipo_busca_setor_autocompletar() and not self.cleaned_data.get('destinatario_setor_autocompletar'):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(['É obrigatório informar um setor.'])
        if 'destinatario_setor_autocompletar' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_autocompletar')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )
        if 'destinatario_setor_arvore' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_arvore')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_arvore'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )

        if self.get_destino() is None:
            raise ValidationError('É obrigatório informar um setor.')

        return self.cleaned_data

    def save(self, commit=False):
        if self.get_destino() is None:
            raise ValidationError('É obrigatório informar um setor.')

        instance = super().save(commit=False)
        instance.despacho_cabecalho = self.modelo_despacho.cabecalho
        instance.despacho_rodape = self.modelo_despacho.rodape
        instance.destinatario_setor_tramite = self.get_destino()
        instance.save()
        return instance


class DeferirDespachoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Deferir e Encaminhar'
    processo = forms.ModelChoiceField(
        label='Processo', queryset=Processo.objects, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS, readonly=True), required=True
    )
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())
    senha = forms.PasswordField()

    class Media:
        js = (
            '/static/processo_eletronico/js/SolicitarDespacho.js',
            '/static/tinymce/tiny_mce_toolbar.js',
            '/static/tinymce/js/tinymce/tinymce.min.js',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = getattr(self, 'instance', None)
        self.fields['processo'].initial = self.instance.processo
        self.fields['processo'].widget.attrs['readonly'] = True
        vinculo = self.request.user.get_relacionamento()
        self.fields['papel'].queryset = vinculo.papeis_ativos

    def clean_papel(self):
        papel = self.cleaned_data.get('papel', None)
        vinculo = self.request.user.get_relacionamento()
        if not papel or papel not in vinculo.papeis_ativos:
            self.add_error('papel', 'Papel inválido.')
        return self.cleaned_data.get('papel')

    def clean(self):
        self.instance.processo.verificar_dados_processo()

    @transaction.atomic()
    def save(self, commit=False):
        self.instance.deferir_solicitacao()
        tramite = Tramite()
        tramite.processo = self.instance.processo
        tramite.tramitar_processo(
            remetente_setor=self.instance.remetente_setor,
            remetente_vinculo=self.request.user.get_vinculo(),
            despacho_corpo=self.instance.despacho_corpo,
            destinatario_setor=self.instance.destinatario_setor_tramite,
            destinatario_vinculo=self.instance.destinatario_vinculo_tramite,
            papel=self.cleaned_data.get('papel', None),
        )
        self.instance.tramite_gerado = tramite
        self.instance.data_resposta = get_datetime_now()
        super().save(commit)


class DeferirDespachoSetorForm(DeferirDespachoForm):
    destinatario_setor_tramite = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.none(), required=True, widget=AutocompleteWidget()
    )
    fieldsets = (
        ('Dados gerais', {'fields': ('processo', 'despacho_corpo', 'destinatario_setor_tramite')}),
        ('Autenticação', {'fields': ('papel', 'senha')}),
    )

    class Meta:
        model = SolicitacaoDespacho
        fields = ['despacho_corpo', 'destinatario_setor_tramite']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destinatario_setor_tramite'].queryset = Setor.objects.suap_ativos()
        self.fields['destinatario_setor_tramite'].initial = self.instance.destinatario_setor_tramite


class DeferirDespachoPessoaForm(DeferirDespachoForm):
    class Meta:
        model = SolicitacaoDespacho
        fields = ['processo', 'despacho_corpo', 'destinatario_vinculo_tramite']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destinatario_vinculo_tramite'].initial = self.instance.destinatario_vinculo_tramite


class RejeitarSolicitacaoDespachoForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoDespacho
        fields = ['justificativa_rejeicao']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance = getattr(self, 'instance', None)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.data_resposta = get_datetime_now()
        self.instance.indeferir_solicitacao()
        return super().save(*args, **kwargs)


class SolicitacaoAssinaturaComAnexacaoProcessoForm(SolicitacaoAssinaturaForm):
    processo_para_anexar = forms.ModelChoiceFieldPlus(
        queryset=Processo.objects, required=True, widget=AutocompleteWidget(), label='Anexar ao Processo'
    )
    # Dados para encaminhar para setor
    TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Autocompletar'), ('arvore', 'Árvore'))
    tipo_busca_setor = forms.ChoiceField(
        widget=forms.RadioSelect(uncheck=True), required=False, choices=TIPO_BUSCA_SETOR_CHOICE, label='Buscar Setor por'
    )
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino do Trâmite', queryset=Setor.objects.none(), required=False, widget=AutocompleteWidget()
    )
    destinatario_setor_arvore = forms.ModelChoiceField(
        label='Setor de Destino do Trâmite', queryset=Setor.objects.none(), required=False, widget=TreeWidget()
    )

    class Media:
        js = ('/static/processo_eletronico/js/SolicitarAssinaturaAnexacao.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['destinatario_setor_autocompletar'].queryset = Setor.objects.suap_ativos()
        self.fields['destinatario_setor_arvore'].queryset = Setor.objects.suap_ativos()

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)
        else:
            return self.cleaned_data.get('destinatario_setor_arvore', None)

    def clean(self):
        if self.is_tipo_busca_setor_arvore() and not self.cleaned_data.get('destinatario_setor_arvore'):
            self._errors['destinatario_setor_arvore'] = forms.ValidationError(['É obrigatório informar um setor.'])

        if self.is_tipo_busca_setor_autocompletar() and not self.cleaned_data.get('destinatario_setor_autocompletar'):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(['É obrigatório informar um setor.'])
        if 'destinatario_setor_autocompletar' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_autocompletar')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )
        if 'destinatario_setor_arvore' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_arvore')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_arvore'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )
        # Um processo finalizado não pode receber novos documentos e portanto as solicitações de anexação
        # não podem ser realizadas.
        processo_anexar = self.cleaned_data.get('processo_para_anexar', None)
        if not processo_anexar:
            self.errors['processo_para_anexar'] = forms.ValidationError(
                ['Nenhum processo foi selecionado. Por favor, indique o processo ao qual o presente processo deve ser anexado.']
            )
        else:
            if processo_anexar.esta_finalizado():
                self.errors['processo_para_anexar'] = forms.ValidationError(
                    [f'O processo {processo_anexar} encontra-se finalizado e não pode receber novos documentos.']
                )
            if processo_anexar.tem_solicitacoes_assinatura_com_tramite_pendentes():
                self.errors['processo_para_anexar'] = forms.ValidationError(
                    [f'O processo {processo_anexar} não pode receber novos anexos pois possui solicitações de assinatura com trâmites pendentes.']
                )
        return self.cleaned_data


class SolicitarAnexoForm(forms.FormPlus):
    processo = forms.CharFieldPlus()
    solicitado = forms.ModelPopupChoiceField(queryset=Vinculo.objects.none(), label='Interessado')
    motivo = forms.CharField(label='Motivação', max_length=255, widget=forms.Textarea, required=True)
    tipo_documento = forms.ModelPopupChoiceField(queryset=TipoDocumento.objects.all(), label='Tipo de Documento')
    data_limite = forms.DateFieldPlus(label='Data Limite')

    class Meta:
        fields = ('processo', 'solicitado', 'motivo', 'tipo_documento', 'data_limite')

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True
        vinculo_logado = self.request.user.get_vinculo()
        self.fields['solicitado'].queryset = self.processo.interessados.exclude(id=vinculo_logado.id, user__isnull=True)

    def clean_data_limite(self):
        data_limite = self.cleaned_data['data_limite']
        if data_limite < get_datetime_now().date():
            return self.add_error('data_limite', 'Data limite inválida.')
        return data_limite


def SolicitacaoDespachoFormFactory(request_method, request, processo, instance=None):
    if processo.eh_privado():
        return SolicitarDespachoPessoaForm(data=request_method, request=request, processo=processo, instance=instance)
    else:
        return SolicitarDespachoSetorForm(data=request_method, request=request, processo=processo, instance=instance)


class MotivoSolicitacaoDocumentoForm(forms.FormPlus):
    processo = forms.CharFieldPlus()
    documento = forms.CharFieldPlus()
    motivo = forms.CharField(label='Motivação', max_length=255, widget=forms.Textarea, required=True)

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        self.documento = kwargs.pop('documento')
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['documento'].initial = self.documento
        self.fields['processo'].widget.attrs['readonly'] = True
        self.fields['documento'].widget.attrs['readonly'] = True


def DeferirDespachoFormFactory(request_method, request, instance):
    if instance.processo.eh_privado():
        return DeferirDespachoPessoaForm(data=request_method, request=request, instance=instance)
    else:
        return DeferirDespachoSetorForm(data=request_method, request=request, instance=instance)


class RequerimentoFormCadastrar(forms.ModelFormPlus):
    assunto = forms.CharField(max_length=255, label='Assunto')
    descricao = forms.CharField(
        widget=TextareaCounterWidget(max_length=510),
        label='Descrição',
        help_text='Essa informação será exibida no requerimento que dará origem ao processo. ',
    )

    tipo_processo = forms.ModelPopupChoiceField(TipoProcesso.objects.filter(permite_gerar_processo_via_requerimento=True), label='Tipo de Processo')
    # nivel_acesso_default foi criado apenas para exibir o nível de acesso padrão do tipo de processo selecionado.
    nivel_acesso_default = forms.CharField(max_length=10, label='Nível de Acesso Padrão', required=False)
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)

    class Meta:
        model = Requerimento
        fields = ('tipo_processo', 'nivel_acesso_default', 'hipotese_legal', 'assunto', 'descricao')

    class Media:
        js = ('/static/processo_eletronico/js/RequerimentoFormCadastrar2.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['nivel_acesso_default'].initial = self.instance.tipo_processo.get_nivel_acesso_default_display()

        self.fields['nivel_acesso_default'].widget.attrs.update(readonly='readonly')
        self.fields['nivel_acesso_default'].widget.attrs.update(disabled='disabled')


class DocumentoDigitalizadoRequerimentoForm(forms.ModelFormPlus):
    tipo = forms.ModelPopupChoiceField(TipoDocumento.objects, label='Tipo', required=True)
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)
    arquivo = forms.FileFieldPlus(label='Arquivo', required=True, max_file_size=settings.PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE)

    class Meta:
        model = RequerimentoDigitalizado
        exclude = ('requerimento', 'tipo_conferencia')

    class Media:
        js = ('/static/processo_eletronico/js/DocumentoDigitalizadoRequerimentoForm.js',)

    def clean_arquivo(self):
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content

    def clean_identificador_setor_sigla(self):
        if self.cleaned_data.get('identificador_setor_sigla') and len(self.cleaned_data.get('identificador_setor_sigla')) > 50:
            raise forms.ValidationError('O tamanho máximo para o campo sigla do setor é de 50 caracteres.')
        return self.cleaned_data.get('identificador_setor_sigla')

    def clean(self):
        nivel_acesso = self.cleaned_data.get('nivel_acesso', None)
        compartilhamento = self.cleaned_data.get('compartilhamento', None)
        if nivel_acesso == Documento.NIVEL_ACESSO_SIGILOSO and not compartilhamento:
            self.add_error('compartilhamento', 'Os documentos sigilosos exigem o preenchimento desse campo.')

        return self.cleaned_data


class DocumentoDigitalizadoRequerimentoEditarForm(forms.ModelFormPlus):
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)

    class Meta:
        model = RequerimentoDigitalizado
        exclude = ('requerimento', 'arquivo')

    class Media:
        js = ('/static/processo_eletronico/js/DocumentoDigitalizadoRequerimentoForm.js',)

    def clean_identificador_setor_sigla(self):
        if self.cleaned_data.get('identificador_setor_sigla') and len(self.cleaned_data.get('identificador_setor_sigla')) > 50:
            raise forms.ValidationError('O tamanho máximo para o campo sigla do setor é de 50 caracteres.')
        return self.cleaned_data.get('identificador_setor_sigla')


class FinalizarRequerimentoForm(forms.FormPlus):
    senha = forms.PasswordField()
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())

    # Dados para encaminhar para setor
    tipo_busca_setor = forms.ChoiceField(widget=forms.RadioSelect(), required=True, label='Destino do primeiro trâmite')
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=AutocompleteWidget()
    )
    destinatario_setor_arvore = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=TreeWidget()
    )

    despacho = forms.CharField(label='Despacho', required=False, widget=forms.Textarea())

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)
        if self.is_tipo_busca_setor_arvore():
            return self.cleaned_data.get('destinatario_setor_arvore', None)

    def __init__(self, *args, **kwargs):
        sugestao_primeiro_tramite = kwargs.pop('sugestao_primeiro_tramite')
        super().__init__(*args, **kwargs)

        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos

        if sugestao_primeiro_tramite:
            TIPO_BUSCA_SETOR_CHOICE = (
                ('autocompletar', 'Buscar usando o Autocompletar'),
                ('arvore', 'Buscar usando a Árvore'),
                ('sugestao_primeiro_tramite', format_html(f'<b>Sugestão do sistema:</b> {sugestao_primeiro_tramite}')),
            )
            self.fields['tipo_busca_setor'].choices = TIPO_BUSCA_SETOR_CHOICE
            self.fields['tipo_busca_setor'].initial = 'sugestao_primeiro_tramite'
        else:
            TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Buscar usando o Autocompletar'), ('arvore', 'Buscar usando a Árvore'))
            self.fields['tipo_busca_setor'].choices = TIPO_BUSCA_SETOR_CHOICE

    class Media:
        js = ('/static/processo_eletronico/js/RequerimentoFormCadastrar.js',)

    def clean_papel(self):
        papel = self.cleaned_data.get('papel', None)

        relacionamento = self.request.user.get_relacionamento()

        if not papel or papel not in relacionamento.papeis_ativos:
            self.add_error('papel', 'Papel inválido.')
        return self.cleaned_data.get('papel')

    def clean(self):
        if 'destinatario_setor_autocompletar' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_autocompletar')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )

        if 'destinatario_setor_arvore' in self.cleaned_data:
            setor_indicado = self.cleaned_data.get('destinatario_setor_arvore')
            if setor_indicado in Setor.get_setores_vazios():
                self._errors['destinatario_setor_arvore'] = forms.ValidationError(
                    [f'O setor {setor_indicado} não tem ninguém cadastrado para receber o processo.']
                )

        self._exigir_setor_de_destino()

        return self.cleaned_data

    def _exigir_setor_de_destino(self) -> None:
        """Sem sugestão do sistema, o setor do tipo de busca escolhido é obrigatório."""
        tipo_busca = self.cleaned_data.get('tipo_busca_setor')
        if tipo_busca in ('autocompletar', 'arvore'):
            campo = f'destinatario_setor_{tipo_busca}'
            if campo not in self.errors and not self.cleaned_data.get(campo):
                self.add_error(campo, 'Para finalizar é preciso que informe o Setor de Destino do Processo.')


class ClonarMinutaForm(forms.FormPlus):
    tipo = forms.ModelChoiceField(TipoDocumentoTexto.ativos, label='Tipo do Documento', required=True)
    modelo = forms.ModelChoiceField(ModeloDocumento.ativos.all(), label='Modelo', required=True)
    nivel_acesso = forms.ChoiceField(label='Nível de Acesso', choices=Documento.NIVEL_ACESSO_CHOICES, required=True)
    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )
    assunto = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Assunto')
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects, label='Classificações', required=False, disabled=True)
    setor_dono = forms.ModelChoiceField(label='Setor Dono', queryset=Setor.objects.suap_ativos().none(), required=True)

    def __init__(self, *args, **kwargs):
        tipodocumento = kwargs.pop('tipodocumento')
        modelo = kwargs.pop('modelo')
        assunto = kwargs.pop('assunto')
        nivel_acesso = kwargs.pop('nivel_acesso')
        hipotese_legal = kwargs.pop('hipotese_legal')
        super().__init__(*args, **kwargs)

        qs_setores_usuario = get_setores_compartilhados(self.request.user, NivelPermissao.EDITAR)
        self.fields['setor_dono'].queryset = qs_setores_usuario
        if qs_setores_usuario.count() == 1:
            self.initial['setor_dono'] = qs_setores_usuario[0].pk
        if tipodocumento:
            self.initial['tipo'] = tipodocumento.pk
        if modelo:
            self.initial['modelo'] = modelo.pk
        if assunto:
            self.initial['assunto'] = assunto
        if nivel_acesso:
            self.initial['nivel_acesso'] = nivel_acesso
        if hipotese_legal:
            self.initial['hipotese_legal'] = hipotese_legal.pk

        setor_dono_help_text = 'Se o setor desejado não está listado, solicite permissão ao chefe desse setor'
        base_conhecimento_permissao_acesso_documento_id = Configuracao.get_valor_por_chave(
            'documento_eletronico', 'base_conhecimento_permissao_acesso_documento'
        )
        if base_conhecimento_permissao_acesso_documento_id and 'centralservicos' in settings.INSTALLED_APPS:
            BaseConhecimento = apps.get_model('centralservicos', 'BaseConhecimento')
            base_conhecimento_permissao_acesso_documento = BaseConhecimento.objects.filter(id=base_conhecimento_permissao_acesso_documento_id).first()
            if base_conhecimento_permissao_acesso_documento:
                setor_dono_help_text += mark_safe(
                    f' (<a href="{base_conhecimento_permissao_acesso_documento.get_absolute_url()}">link com instruções para o chefe</a>)'
                )
        self.fields['setor_dono'].help_text = setor_dono_help_text

    class Media:
        js = ['/static/documento_eletronico/js/DocumentoTextoForm.js']

    def clean(self):
        nivel_acesso = self.cleaned_data.get('nivel_acesso')
        hipotese = self.cleaned_data.get('hipotese_legal')
        if nivel_acesso and int(nivel_acesso) in [Documento.NIVEL_ACESSO_SIGILOSO, Documento.NIVEL_ACESSO_RESTRITO] and not hipotese:
            raise ValidationError('Para tipos de documentos Sigilosos ou Restritos você deve informar uma hipotese legal.')


class PedidoJuntadaForm(forms.FormPlus):
    processo = forms.CharFieldPlus()
    solicitados = forms.ModelMultiplePopupChoiceField(queryset=Vinculo.objects.none(), label='Solicitados', required=True)
    motivo = forms.CharField(label='Motivação', max_length=255, widget=forms.Textarea, required=True)
    data_limite = forms.DateFieldPlus(label='Data Limite')

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo', None)
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True

        vinculo_logado = self.request.user.get_vinculo()
        pred_aluno = [
            Q(pessoa__pessoafisica__eh_aluno=True),
            Q(pessoa__pessoafisica__nascimento_data__isnull=True)
            | Q(pessoa__pessoafisica__nascimento_data__gt=get_datetime_now().date() - relativedelta(years=18)),
        ]
        self.fields['solicitados'].queryset = (
            self.processo.interessados.filter(user__isnull=False).exclude(id=vinculo_logado.id).exclude(reduce(operator.and_, pred_aluno))
        )

    def clean_data_limite(self):
        data_limite = self.cleaned_data['data_limite']
        if data_limite < get_datetime_now().date():
            return self.add_error('data_limite', 'Data limite inválida.')
        return data_limite

    def clean(self):
        tramite = self.processo.ultimo_tramite
        solicitados = self.cleaned_data.get('solicitados')
        if not solicitados:
            raise ValidationError('Você deve informar, no mínimo, um solicitado.')
        #
        status = [SolicitacaoJuntadaStatus.STATUS_ESPERANDO, SolicitacaoJuntadaStatus.STATUS_CONCLUIDO]
        for solicitado in solicitados:
            #
            if SolicitacaoJuntada.objects.filter(tramite=tramite, solicitado=solicitado, status__in=status):
                raise ValidationError(f'{solicitado} já possui uma Solicitação de Juntada de Documentos em aberto.')
            #
            if solicitado.eh_aluno() and not solicitado.eh_maior_de_idade(referencia=get_datetime_now().date()):
                raise ValidationError(
                    f'{solicitado.nome_usual} é Aluno menor de idade (ou sem data de nascimento) e não pode receber Solicitação de Juntada de Documentos.'
                )


class DeferirSolicitacaoJuntadaDocumentoForm(forms.FormPlus):
    processo = forms.CharFieldPlus()
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)
    senha = forms.PasswordField()

    #

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user')
        self.solicitacao_juntada_documento = kwargs.pop('solicitacao')
        self.processo = self.solicitacao_juntada_documento.processo
        super().__init__(*args, **kwargs)
        self.fields['processo'].initial = self.processo
        self.fields['processo'].widget.attrs['readonly'] = True


class ConcluirSolicitacaoForm(forms.FormPlus):
    concluir = forms.BooleanField(label='Concluir Solicitação', required=True)
    user = forms.CharField(label='Usuário')
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['user'].initial = self.request.user
        self.fields['user'].widget.attrs['readonly'] = True


class ConfiguracaoTramiteProcessoForm(forms.ModelFormPlus):
    tipo_processo = forms.ModelPopupChoiceField(TipoProcesso.objects.all(), label='Tipo de Processo', required=True)

    # Dados para encaminhar para setor
    tipo_busca_setor = forms.ChoiceField(widget=forms.RadioSelect(), required=False, label='Destino do primeiro trâmite')
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=AutocompleteWidget()
    )
    destinatario_setor_arvore = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects.suap_ativos(), required=False, widget=TreeWidget()
    )

    def is_tipo_busca_setor_arvore(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'arvore'

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)
        if self.is_tipo_busca_setor_arvore():
            return self.cleaned_data.get('destinatario_setor_arvore', None)
        return None

    def clean(self):
        # Valida a busca por setor auto_completar ou arvore
        if self.is_tipo_busca_setor_arvore() and not self.cleaned_data.get('destinatario_setor_arvore'):
            self._errors['destinatario_setor_arvore'] = forms.ValidationError(['É obrigatório informar um setor.'])
        if self.is_tipo_busca_setor_autocompletar() and not self.cleaned_data.get('destinatario_setor_autocompletar'):
            self._errors['destinatario_setor_autocompletar'] = forms.ValidationError(['É obrigatório informar um setor.'])

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id and self.instance.setor_destino_primeiro_tramite:
            TIPO_BUSCA_SETOR_CHOICE = (
                ('autocompletar', 'Buscar usando o Autocompletar'),
                ('arvore', 'Buscar usando a Árvore'),
                ('meu_setor', format_html(f'<b>Setor:</b> {self.instance.setor_destino_primeiro_tramite}')),
            )
            self.fields['tipo_busca_setor'].choices = TIPO_BUSCA_SETOR_CHOICE
            self.fields['tipo_busca_setor'].initial = 'meu_setor'
        else:
            TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Buscar usando o Autocompletar'), ('arvore', 'Buscar usando a Árvore'))
            self.fields['tipo_busca_setor'].choices = TIPO_BUSCA_SETOR_CHOICE

    class Meta:
        model = ConfiguracaoTramiteProcesso
        fields = ('tipo_processo', 'uo_origem_interessado')

    class Media:
        js = ('/static/processo_eletronico/js/RequerimentoFormCadastrar.js',)

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.get_destino():
            self.instance.setor_destino_primeiro_tramite = self.get_destino()

        return super().save(*args, **kwargs)


class CancelarSolicitacaoJuntadaForm(forms.ModelFormPlus):
    justificativa_cancelamento = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    class Meta:
        model = SolicitacaoJuntada
        fields = ('justificativa_cancelamento',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.cancelar_solicitacao(self.request.user, self.cleaned_data['justificativa_cancelamento'])
        super().save(*args, **kwargs)


class NumerosProcessoEletronicoForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Filtrar'

    setor = forms.ModelChoiceField(queryset=Setor.objects.none(), label='Setor', empty_label=None, widget=AutocompleteWidget())
    abrangencia = forms.ChoiceField(label='Abrangência', choices=[('arvore', 'Setor e subordinados'), ('setor', 'Somente o setor')])
    periodo = forms.ChoiceField(
        label='Período',
        choices=[
            ('ano_atual', 'Ano atual'),
            ('ano_anterior', 'Ano anterior'),
            ('mes_atual', 'Mês atual'),
            ('mes_anterior', 'Mês anterior'),
            ('personalizado', 'Período personalizado'),
            ('todo', 'Todo o histórico'),
        ],
    )
    agrupamento = forms.ChoiceField(label='Agrupar por', choices=[('mes', 'Mês'), ('ano', 'Ano')])
    data_inicio = forms.DateFieldPlus(label='Data inicial', required=False, help_text='Usada apenas no período personalizado.')
    data_final = forms.DateFieldPlus(label='Data final', required=False, help_text='Usada apenas no período personalizado.')

    class Media:
        js = ['/static/processo_eletronico/js/NumerosProcessoEletronicoForm.js']

    def __init__(self, *args: Any, setores: QuerySet, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = setores

    def clean(self) -> dict:
        dados = super().clean()
        periodo = dados.get('periodo')
        if periodo and periodo != 'personalizado':
            dados['data_inicio'], dados['data_final'] = limites_periodo(periodo, datetime.today().date())
        inicio, fim = dados.get('data_inicio'), dados.get('data_final')
        if inicio and fim and inicio > fim:
            self.add_error('data_final', 'A data final deve ser igual ou posterior à data inicial.')
        return dados


class FiltroCaixaEntradaSaidaForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Filtrar'
    setor = forms.ModelChoiceField(Setor.objects.none(), empty_label='Todos', widget=forms.HiddenInput(), label='Setor:', required=False)
    pesquisa = forms.CharField(label='Texto', required=False)
    campus_origem = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.suap(),
        label=f'{nomenclatura.campus} de Criação',
        required=False,
        widget=AutocompleteWidget(),
        empty_label=f'Selecione o {nomenclatura.campus}',
    )
    setor_origem = forms.ModelChoiceField(
        Setor.objects.none(), label='Setor de Criação:', empty_label='Selecione um Setor', widget=AutocompleteWidget(), required=False
    )
    tipo_processo = forms.ModelChoiceField(
        queryset=TipoProcesso.objects,
        label='Tipo de Processo:',
        required=False,
        widget=AutocompleteWidget(),
        empty_label='Selecione um tipo de processo',
    )
    setor_que_tramitou = forms.ModelChoiceField(
        Setor.objects.none(), label='Setor que Tramitou', required=False, widget=AutocompleteWidget(), empty_label='Setor que Tramitou'
    )
    recebido_por = forms.ModelChoiceField(
        queryset=Vinculo.objects.none(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Recebido por:', required=False
    )
    atribuido_para = forms.ModelChoiceField(
        queryset=Vinculo.objects.none(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Atribuídos para:', required=False
    )
    nivel_acesso = forms.ChoiceField(choices=Processo.NIVEL_ACESSO_CHOICES, label='Nível de Acesso', required=False)
    rotulo = forms.ChoiceField(label='Rótulo', required=False)
    rotulo_excluir = forms.ModelChoiceField(label='Desconsiderar rótulo', queryset=Rotulo.objects.none(), required=False)

    def __init__(self, *args, **kwargs):
        setores_usuario = kwargs.pop('setores_usuario', None)
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = Setor.objects.suap_ativos()
        self.fields['setor_origem'].queryset = Setor.objects.suap_ativos()
        self.fields['setor_que_tramitou'].queryset = Setor.objects.suap_ativos()
        # setores_usuario = setores_usuario if setores_usuario else get_todos_setores(self.request.user)
        setores = Tramite.get_todos_setores(self.request.user, deve_poder_criar_processo=False)
        setores_usuario = setores_usuario or setores

        self.fields['atribuido_para'].queryset = Vinculo.objects.filter(
            ativo=True, setor__in=setores_usuario, tipo_relacionamento__model__in=['servidor', 'prestadorservico']
        )

        self.fields['recebido_por'].queryset = Vinculo.objects.filter(
            ativo=True, setor__in=setores_usuario, tipo_relacionamento__model__in=['servidor', 'prestadorservico']
        )

        niveis_acesso = [*list(Processo.NIVEL_ACESSO_CHOICES), ('', 'Todos')]
        self.fields['nivel_acesso'].choices = niveis_acesso
        rotulos_queryset = Rotulo.objects.filter(setor__in=setores_usuario)
        rotulos_choices = [('', 'Todos'), ('nenhum', 'Nenhum')] + [(rotulo.id, rotulo.legenda) for rotulo in rotulos_queryset.all()]

        self.fields['rotulo'].choices = rotulos_choices
        self.fields['rotulo_excluir'].queryset = Rotulo.objects.filter(setor__in=setores_usuario)

    def clean_rotulo(self):
        """Validação personalizada para o campo 'rotulo'."""
        rotulo = self.cleaned_data.get('rotulo')
        if rotulo == 'nenhum':
            return 'nenhum'
        if not rotulo:
            return None
        try:
            # Valida se é um ID válido de Rotulo
            return Rotulo.objects.get(pk=rotulo)
        except Rotulo.DoesNotExist:
            raise forms.ValidationError('Escolha um rótulo válido.')

    def processar(self):
        pesquisa, _termos_retirados = normalizar_termos_busca(self.cleaned_data.get('pesquisa', ''))
        predicates = []
        if pesquisa:
            search_q = (
                Q(processo__numero_protocolo_fisico__icontains=pesquisa)
                | Q(processo__numero_protocolo__icontains=pesquisa)
                | Q(processo__assunto__icontains=pesquisa)
                | Q(processo__interessados__pessoa__nome__icontains=pesquisa)
            )
            predicates.append(search_q)

        queries = {
            'tipo_processo': 'processo__tipo_processo',
            'setor_origem': 'processo__setor_criacao',
            'campus_origem': 'processo__setor_criacao__uo',
            'status': 'processo__status',
            'atribuido_para': 'atribuido_para',
            'recebido_por': 'recebido_por',
            'rotulo': 'rotulotramite__rotulo__legenda',
            'rotulo_excluir': 'rotulotramite__rotulo',
            'nivel_acesso': 'processo__nivel_acesso',
            'setor_que_tramitou': 'processo__tramites__remetente_setor',
        }
        for field, value in list(self.cleaned_data.items()):
            if value and field in queries:
                if field == 'rotulo' and value == 'nenhum':
                    predicates.append(Q(rotulotramite__rotulo__isnull=True))
                elif field == 'rotulo' and value == '':
                    predicates.append(Q(rotulotramite__rotulo__isnull=False))
                elif field == 'rotulo_excluir' and value:
                    predicates.append(~Q(**{queries[field]: value}))
                else:
                    predicates.append(Q(**{queries[field]: value}))
        if self.cleaned_data.get('atribuido_para'):
            if Configuracao.get_valor_por_chave('processo_eletronico', 'permite_distribuir_ao_tramitar'):
                predicates.append(
                    Q(atribuido_para=self.cleaned_data.get('atribuido_para')) | Q(destinatario_vinculo=self.cleaned_data.get('atribuido_para'))
                )
            else:
                predicates.append(Q(atribuido_para=self.cleaned_data.get('atribuido_para')))
        return predicates

    def processar_processo(self):
        pesquisa = self.cleaned_data.get('pesquisa', None)
        predicates = []
        if pesquisa:
            search_q = (
                Q(numero_protocolo_fisico__icontains=pesquisa)
                | Q(numero_protocolo__icontains=pesquisa)
                | Q(assunto__icontains=pesquisa)
                | Q(interessados__pessoa__nome__icontains=pesquisa)
            )
            predicates.append(search_q)

        queries = {
            'tipo_processo': 'tipo_processo',
            'setor_origem': 'setor_criacao',
            'campus_origem': 'setor_criacao__uo',
            'status': 'status',
            'atribuido_para': 'tramites__atribuido_para',
            'recebido_por': 'tramites__recebido_por',
            'rotulo': 'ultimo_tramite__rotulotramite__rotulo',
            'nivel_acesso': 'nivel_acesso',
            'setor_que_tramitou': 'tramites__remetente_setor',
        }
        for field, value in list(self.cleaned_data.items()):
            if value and field in queries:
                if field == 'rotulo' and value == 'nenhum':
                    predicates.append(Q(ultimo_tramite__rotulotramite__rotulo__isnull=True))
                elif field == 'rotulo' and value == '':
                    predicates.append(Q(ultimo_tramite__rotulotramite__rotulo__isnull=False))
                else:
                    predicates.append((queries[field], value))
        q_list = [Q(x) for x in predicates]
        return q_list


class CancelarCienciaForm(forms.ModelFormPlus):
    justificativa_cancelamento = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), required=True)

    class Meta:
        model = SolicitacaoCiencia
        fields = ('justificativa_cancelamento',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        self.instance.cancelar_ciencia(self.request.user, self.cleaned_data['justificativa_cancelamento'])
        super().save(*args, **kwargs)


class ProcessoFormAlterarNivelAcesso(forms.FormPlus):
    nivel_acesso_atual = ReadOnlyField(label='De')
    nivel_acesso = forms.ChoiceField(required=True, label='Para')
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)
    setor_usuario = forms.ModelChoiceField(label='Setores', queryset=Setor.objects.suap_ativos().none())
    senha = forms.PasswordField()

    # so tera 'papel' quando for para assinar a mudanca de nivel de acesso na nova implementacao
    # papel = forms.ModelChoiceField(label=u'Perfil', queryset=Papel.objects.none())

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    justificativa = forms.CharFieldPlus(label='Justificativa', max_length=400, required=False, widget=forms.Textarea())

    solicitacao_id = forms.IntegerField(required=False, initial=0, widget=forms.HiddenInput())

    # deferir_outras_solicitacoes = forms.BooleanField(label='Deferir outras solicitações com o mesmo nível de acesso solitado.', required=False)

    fieldsets = (
        (
            'Atual Nível de Acesso',
            {'fields': ('nivel_acesso_atual',)},
        ),
        (
            'Novo Nível de Acesso',
            {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal', 'setor_usuario', 'justificativa')},
        ),
        ('Autenticação', {'fields': ('senha',)}),
    )

    class Media:
        js = ['/static/processo_eletronico/js/ProcessoFormAlterarNivelAcesso.js']

    def __init__(self, *args, **kwargs):
        self.estah_solicitando = kwargs.pop('estah_solicitando', None)
        self.solicitacao = kwargs.pop('solicitacao', None)
        self.processo = kwargs.pop('processo', None)
        super().__init__(*args, **kwargs)

        if self.solicitacao:
            self.fields['solicitacao_id'].initial = self.solicitacao.id

        if self.estah_solicitando:
            if 'setor_usuario' in self.fields:
                del self.fields['setor_usuario']

        # Níveis de acesso para os quais o processo pode ser alterado
        niveis_acesso_alteracao = list(Processo.NIVEL_ACESSO_CHOICES)
        del niveis_acesso_alteracao[self.processo.nivel_acesso - 1]
        niveis_acesso_alteracao.insert(0, [0, '-------'])

        # Níveis de acesso atual
        nivel_acesso_atual = Processo.NIVEL_ACESSO_CHOICES[self.processo.nivel_acesso - 1][1]

        # Setores do usuario
        # setores_usuario = get_todos_setores(self.request.user)
        # Novo esquema de permissoes do processo e documento eletronico
        setores_usuario = Tramite.get_todos_setores(user=self.request.user)

        # self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos

        # Nivel de acesso DE
        self.fields['nivel_acesso_atual'].initial = nivel_acesso_atual

        # Nivel de acesso PARA
        self.fields['nivel_acesso'].choices = niveis_acesso_alteracao
        self.fields['nivel_acesso'].initial = 0
        if self.solicitacao:
            #
            self.fields['nivel_acesso'] = ReadOnlyField(label='Para')
            self.fields['nivel_acesso'].widget.display_value = self.solicitacao.get_para_nivel_acesso()[1]
            self.fields['nivel_acesso'].initial = self.solicitacao.get_para_nivel_acesso()[0]
            #
            self.Media.js = None
            hipoteses = SolicitacaoAlteracaoNivelAcesso.get_hipoteses_legais_by_processo_documento_nivel_acesso(
                3, self.solicitacao.get_para_nivel_acesso()[0]
            )
            if hipoteses:
                self.fields['hipotese_legal'].queryset = hipoteses
            else:
                self.fields['hipotese_legal'].queryset = HipoteseLegal.objects.none()
            #
            if self.solicitacao.hipotese_legal:
                self.fields['hipotese_legal'].initial = self.solicitacao.hipotese_legal.id

        if 'setor_usuario' in self.fields:
            self.fields['setor_usuario'].queryset = setores_usuario

        # - Para alterar o nível de acesso do processo de PRIVADO para QUALQUER OUTRO nível de acesso
        #   deverá ser informado o setor para o qual será gerado um trâmite.
        # - Os setores serão aqueles que ele pode criar processo (veja o `setores_usuario`)
        if not self.processo.eh_privado() and 'setor_usuario' in self.fields:
            del self.fields['setor_usuario']

        conf_orientacao = ConfiguracaoInstrucaoNivelAcesso.get_orientacao()
        if conf_orientacao:
            self.fields['ciencia_instrucoes_gerais'].required = True
            self.fields['instrucoes_gerais'] = SpanField(widget=SpanWidget(), label='')
            self.fields['instrucoes_gerais'].widget.label_value = mark_safe(f'<br>{conf_orientacao}')
            self.fields['instrucoes_gerais'].widget.original_value = conf_orientacao
            self.fields['instrucoes_gerais'].required = False
        else:
            self.fields['ciencia_instrucoes_gerais'].widget = forms.HiddenInput()
            self.fields['ciencia_instrucoes_gerais'].required = False
            self.fields['instrucoes_gerais'].widget = forms.HiddenInput()

    def clean(self):
        if (
            self.cleaned_data.get('nivel_acesso')
            and int(self.cleaned_data.get('nivel_acesso')) in (Processo.NIVEL_ACESSO_RESTRITO, Processo.NIVEL_ACESSO_PRIVADO)
            and not self.cleaned_data.get('hipotese_legal')
        ):
            raise forms.ValidationError('Selecione uma hipótese legal.')

    def clean_nivel_acesso(self):
        if self.cleaned_data.get('nivel_acesso') and int(self.cleaned_data.get('nivel_acesso')) not in (
            Processo.NIVEL_ACESSO_PUBLICO,
            Processo.NIVEL_ACESSO_RESTRITO,
            Processo.NIVEL_ACESSO_PRIVADO,
        ):
            raise forms.ValidationError('Nível de acesso inválido.')

        if self.processo.get_processos_apensados().exists() and int(self.cleaned_data.get('nivel_acesso')) == Processo.NIVEL_ACESSO_PRIVADO:
            for proc in self.processo.get_processos_apensados():
                if proc.nivel_acesso != Processo.NIVEL_ACESSO_PRIVADO:
                    raise forms.ValidationError(
                        f'Não é possível alterar para Privado pois o processo {self.processo.numero_protocolo_fisico} está apensado a '
                        'outro(s) com nível de acesso distinto de Privado.'
                    )

        return self.cleaned_data.get('nivel_acesso')


class BuscaProcessoEletronicoManutencaoAlteraStatusForm(forms.FormPlus):
    identificador = forms.CharFieldPlus(label='Identificador')
    parametro = forms.CharFieldPlus(label='Parâmetro')
    senha = forms.PasswordField()


class BuscaProcessoEletronicoManutencaoForm(forms.FormPlus):
    TIPO_BUSCA_CHOICE = (
        ('numero_protocolo', 'Número Protocolo Novo (NUP 21)'),
        ('numero_protocolo_fisico', 'Número Protocolo Antigo (NUP 17)'),
        ('id_processo', 'Id do processo'),
    )
    tipo_busca = forms.ChoiceField(widget=forms.RadioSelect(), choices=TIPO_BUSCA_CHOICE, initial='senha', label='Tipo de Assinatura')

    parametro = forms.CharFieldPlus(label='Parâmetro')
    senha = forms.PasswordField()


class AtribuirProcessoForm(forms.FormPlus):
    vinculo = forms.ModelChoiceField(label='Selecione a Pessoa:', queryset=Vinculo.objects.none(), required=True, widget=AutocompleteWidget)

    def __init__(self, *args, **kwargs):
        self.tramite = kwargs.pop('tramite', None)
        super().__init__(*args, **kwargs)
        # setores_usuario = get_todos_setores(self.request.user)
        # Novo esquema de permissoes do processo e documento eletronico
        setores_usuario = Tramite.get_todos_setores(user=self.request.user)
        ids_funcionarios = []
        for setor in setores_usuario:
            funcionarios = setor.get_vinculos(recursivo=False).filter(ativo=True)
            ids_funcionarios.extend(funcionarios.values_list('id', flat=True))
        #
        self.fields['vinculo'].queryset = Vinculo.objects.filter(id__in=ids_funcionarios)

    def clean_vinculo(self):
        vinculo = self.cleaned_data['vinculo']
        if not self.tramite.pode_editar(vinculo.user):
            self.add_error('vinculo', 'A pessoa selecionada não possui permissão para tramitar esse processo')
        return vinculo


class ForceRecaptchaForm(forms.FormPlus):
    METHOD = 'GET'
    TITLE = 'Validação de Usuário'
    recaptcha = ReCaptchaField(label='')


def ConsultaPublicaProcessoFormClass(recaptcha_required=True):
    class ConsultaPublicaProcessoForm(forms.FormPlus):
        METHOD = 'GET'
        numero_protocolo = forms.ProcessoEletronicoField(
            label='Número do processo',
            required=False,
            help_text='Não é necessário informar pontos ou traços. O formato do número de um processo eletrônico corresponde a 17 algarismos, no formato: 12345.123456'
            + settings.NUM_PROCESSO_DIVISOR_SUFIXO
            + '2024-12.',
        )
        interessado = forms.CharFieldPlus(label='Interessado', required=False, help_text='Informe o nome do interessado ou CPF ou CNPJ.')
        assunto = forms.CharFieldPlus(label='Assunto', required=False)
        tipo_processo = forms.ModelChoiceField(
            queryset=TipoProcesso.objects, label='Tipo', widget=AutocompleteWidget(search_fields=TipoProcesso.SEARCH_FIELDS), required=False
        )
        todas_situacoes = forms.BooleanField(label='Todas as situações', widget=forms.CheckboxInput(attrs={'checked': True}), required=False)
        status = forms.ChoiceField(label='Situação', choices=[*ProcessoStatus.STATUS_CHOICES, ['', 'Todos']], required=False)

        data_inicio = forms.DateFieldPlus(label='Data inicial', required=False)
        data_final = forms.DateFieldPlus(label='Data final', required=False)

        recaptcha = ReCaptchaField(label='Verificação')
        fieldsets = (
            ('Pelo número exato do processo:', {'fields': ('numero_protocolo',)}),
            (
                'Pelos dados gerais dos processos:',
                {
                    'fields': (
                        'tipo_processo',
                        'interessado',
                        'assunto',
                        ('todas_situacoes', 'status'),
                        ('data_inicio', 'data_final'),
                    )
                },
            ),
            ('Verificação de segurança', {'fields': ('recaptcha',)}),
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            hoje = get_datetime_now()
            self.fields['data_final'].initial = hoje.date()
            self.fields['data_inicio'].initial = (hoje - timedelta(days=365)).date()
            self.fields['recaptcha'].required = recaptcha_required

        def clean_assunto(self):
            """Remove preposições e conjunções do campo assunto na consulta pública.

            Returns:
                str: assunto limpo ou string vazia.
            """
            cleaned_assunto = self.cleaned_data.get('assunto')
            if cleaned_assunto:
                from nltk.corpus import stopwords
                from nltk.tokenize import word_tokenize

                tokens = word_tokenize(cleaned_assunto)
                filtered_assunto = [word for word in tokens if word not in stopwords.words()]
                if cleaned_assunto and not filtered_assunto:
                    self.add_error('assunto', 'O campo Assunto não pode conter apenas preposições ou conjunções.')
                cleaned_assunto = (' ').join(filtered_assunto)
            return cleaned_assunto

        def clean(self):
            numero_protocolo = self.cleaned_data.get('numero_protocolo')
            data_inicial = self.cleaned_data.get('data_inicio')
            data_final = self.cleaned_data.get('data_final')
            todas_situacoes = self.cleaned_data.get('todas_situacoes', None)
            status = self.cleaned_data.get('status', None)

            if not numero_protocolo:
                if not data_final or not data_inicial:
                    raise ValidationError('É preciso informar uma data inicial e final para a consulta.')

                if data_final < data_inicial:
                    raise ValidationError('A data inicial dever ser anterior a data final.')

                intervalo = data_final - data_inicial
                if intervalo.days > 365:
                    raise ValidationError('O intervalo entre as datas não pode exceder 365 dias.')

                if status and todas_situacoes:
                    raise ValidationError('O campo de Situação está inválido.')

                if not status and not todas_situacoes:
                    raise ValidationError('Selecione uma situação ou selecione "Todas as situações".')

                if not self.cleaned_data.get('todas_situacoes') and not self.cleaned_data.get('status'):
                    raise ValidationError('Selecione uma situação ou marque a opção "Todas as situações".')

    return ConsultaPublicaProcessoForm


class GerenciarCompartilhamentoProcessoForm(forms.FormPlus):
    setores_permitidos_para_operar_processo = forms.MultipleModelChoiceFieldPlus(
        label='Setores que podem operar processos eletrônicos',
        queryset=Setor.objects.suap().filter(excluido=False),
        required=False,
        help_text='Somente os servidores do(s) setor(es) selecionado(s) poderão operar processos eletrônicos',
    )
    setores_permitidos_para_operar_e_criar_processos = forms.MultipleModelChoiceFieldPlus(
        label='Setores que podem operar e adicionar processos eletrônicos',
        queryset=Setor.objects.suap().filter(excluido=False),
        required=False,
        help_text='Somente os servidores do(s) setor(es) selecionado(s) poderão operar processos eletrônicos',
    )

    qs_prestadores_servidores = Vinculo.objects.filter(tipo_relacionamento__model__in=['servidor', 'prestadorservico'])
    vinculos_permitidas_para_operar_processo = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço que podem operar processos eletrônicos', queryset=qs_prestadores_servidores, required=False
    )
    vinculos_permitidas_para_operar_e_criar_processos = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço que podem operar e adicionar processos eletrônicos',
        queryset=qs_prestadores_servidores,
        required=False,
    )
    vinculos_permitidas_para_cadastrar_retorno_programado = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço que podem cadastrar Data de Retorno Programado nos trâmites de processos eletrônicos',
        queryset=qs_prestadores_servidores,
        required=False,
    )

    fieldsets = (
        ('Permissões para Setores:', {'fields': ('setores_permitidos_para_operar_processo', 'setores_permitidos_para_operar_e_criar_processos')}),
        (
            'Permissões para Servidores/Prestadores de Serviço:',
            {
                'fields': (
                    'vinculos_permitidas_para_operar_processo',
                    'vinculos_permitidas_para_operar_e_criar_processos',
                    'vinculos_permitidas_para_cadastrar_retorno_programado',
                )
            },
        ),
    )

    CLASSNAME = 'featured-form normal-label'

    def __init__(self, *args, **kwargs):
        self.setor_escolhido = kwargs.pop('setor_escolhido', None)
        super().__init__(*args, **kwargs)
        self.fields['setores_permitidos_para_operar_processo'].label = f'Setores que podem operar processos eletrônicos do(a) {self.setor_escolhido}'
        self.fields[
            'setores_permitidos_para_operar_e_criar_processos'
        ].label = f'Setores que podem adicionar e operar processos eletrônicos do(a) {self.setor_escolhido}'

        self.fields[
            'vinculos_permitidas_para_operar_processo'
        ].label = f'Servidores/Prestadores de Serviço que podem operar processos eletrônicos do(a) {self.setor_escolhido}'
        self.fields[
            'vinculos_permitidas_para_operar_e_criar_processos'
        ].label = f'Servidores/Prestadores de Serviço que podem adicionar e operar processos eletrônicos do(a) {self.setor_escolhido}'
        self.fields[
            'vinculos_permitidas_para_cadastrar_retorno_programado'
        ].label = f'Servidores/Prestadores de Serviço que podem cadastrar data de retorno programado nos trâmites de processos eletrônicos do(a) {self.setor_escolhido}'


class GerenciarCompartilhamentoPoderChefeProcessoForm(forms.FormPlus):
    vinculos_com_poder_de_chefe = forms.MultipleModelChoiceFieldPlus(
        label='Servidores com poder de chefe', queryset=Vinculo.objects.none(), required=False
    )
    vinculos_com_poder_de_chefe_oficio = forms.MultipleChoiceField(label='Servidores chefe de ofício', choices=[], required=False)

    fieldsets = (
        (
            'Servidores com poder de chefe para Processos Eletrônicos',
            {
                'fields': (
                    'vinculos_com_poder_de_chefe_oficio',
                    'vinculos_com_poder_de_chefe',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.setor_escolhido = kwargs.pop('setor_escolhido', None)
        self.vinculos_com_poder_de_chefe_oficio = kwargs.pop('vinculos_com_poder_de_chefe_oficio', None)

        super().__init__(*args, **kwargs)

        self.fields['vinculos_com_poder_de_chefe'].label = f'Servidores com poder de chefe no(a) {self.setor_escolhido}'
        self.fields['vinculos_com_poder_de_chefe_oficio'].label = f'Servidores chefe de ofício no(a) {self.setor_escolhido}'

        self.fields['vinculos_com_poder_de_chefe_oficio'] = ReadOnlyField(label='Servidores chefe de ofício')
        self.fields['vinculos_com_poder_de_chefe_oficio'].widget.display_value = ', '.join(
            [str(item.vinculo_permitido) for item in self.vinculos_com_poder_de_chefe_oficio]
        )
        self.fields['vinculos_com_poder_de_chefe_oficio'].initial = 0
        self.fields['vinculos_com_poder_de_chefe_oficio'].required = False
        qs_prestadores_servidores = Vinculo.objects.filter(tipo_relacionamento__model__in=['servidor', 'prestadorservico'])
        self.fields['vinculos_com_poder_de_chefe'].queryset = qs_prestadores_servidores.exclude(
            id__in=self.vinculos_com_poder_de_chefe_oficio.values_list('vinculo_permitido__id', flat=True)
        )


class TramiteDistribuicaoForm(forms.ModelFormPlus):
    setor = forms.ModelChoiceField(label='Setor:', queryset=Setor.objects.none(), required=True, widget=AutocompleteWidget())

    distribuir_para = forms.ModelChoiceField(label='Selecione a Pessoa:', queryset=Vinculo.objects.none(), required=True, widget=AutocompleteWidget())

    tipos_processos_atendidos = forms.ModelMultiplePopupChoiceField(TipoProcesso.objects.all(), label='Tipos de Processos Atendidos', required=True)

    class Meta:
        model = TramiteDistribuicao
        fields = ('setor', 'distribuir_para', 'tipos_processos_atendidos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setores_usuario = get_setores_que_sou_chefe_hoje(self.request.user)
        ids_funcionarios = []
        for setor in setores_usuario:
            funcionarios = setor.get_vinculos(recursivo=False).filter(ativo=True)
            ids_funcionarios.extend(funcionarios.values_list('id', flat=True))
        #
        pred = Q(tipo_relacionamento__model__in=['servidor', 'prestadorservico'])
        self.fields['distribuir_para'].queryset = Vinculo.objects.filter(pred & Q(id__in=ids_funcionarios))
        setores_que_sou_chefe = get_setores_que_sou_chefe_hoje(self.request.user)
        self.fields['setor'].queryset = setores_que_sou_chefe


class BuscaProcessoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Adicionar ao Processo'

    processo = forms.ModelChoiceField(
        label='Processo', queryset=Processo.ativos, widget=AutocompleteWidget(search_fields=Processo.SEARCH_FIELDS, required=True)
    )

    class Meta:
        model = Processo
        fields = ['processo']


class ConfiguracaoInstrucaoNivelAcessoForm(forms.ModelFormPlus):
    orientacao = TinyMCEFormField(label='Orientações')

    class Meta:
        model = ConfiguracaoInstrucaoNivelAcesso
        exclude = ()


class ConfirmarIndeferimentoForm(forms.FormPlus):
    solicitacao_id = forms.IntegerField(required=False, initial=0, widget=forms.HiddenInput())

    justificativa = forms.CharFieldPlus(label='Justificativa', max_length=400, required=True, widget=forms.Textarea())
    deferir_outras_solicitacoes = forms.BooleanField(label='Indeferir outras solicitações com o mesmo nível de acesso solitado.', required=False)
    confirmar = forms.BooleanField(label='Confirmar.', required=True)
    senha = forms.PasswordField()
    fieldsets = (
        (
            'Motivação',
            {
                'fields': (
                    'justificativa',
                    'deferir_outras_solicitacoes',
                )
            },
        ),
        (
            'Autenticação',
            {
                'fields': (
                    'confirmar',
                    'senha',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.solicitacao = kwargs.pop('solicitacao', None)
        super().__init__(*args, **kwargs)
        if self.solicitacao:
            self.fields['solicitacao_id'].initial = self.solicitacao.id
            if not self.solicitacao.get_solicitacoes_iguais_em_aberto().exists():
                del self.fields['deferir_outras_solicitacoes']


class ConfirmarDeferimentoForm(forms.FormPlus):
    solicitacao_id = forms.IntegerField(required=False, initial=0, widget=forms.HiddenInput())

    confirmar = forms.BooleanField(label='Confirmar.', required=True)
    senha = forms.PasswordField()

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    def __init__(self, *args, **kwargs):
        self.solicitacao = kwargs.pop('solicitacao', None)
        super().__init__(*args, **kwargs)

        if self.solicitacao:
            self.fields['solicitacao_id'].initial = self.solicitacao.id
        #
        if self.solicitacao.eh_documento_texto():
            if 'vinculos_compartilhados' in self.fields:
                del self.fields['vinculos_compartilhados']

        # Instrucoes
        conf_orientacao = ConfiguracaoInstrucaoNivelAcesso.get_orientacao()
        if conf_orientacao:
            self.fields['ciencia_instrucoes_gerais'].required = True
            self.fields['instrucoes_gerais'] = SpanField(widget=SpanWidget(), label='')
            self.fields['instrucoes_gerais'].widget.label_value = mark_safe(f'<br>{conf_orientacao}')
            self.fields['instrucoes_gerais'].widget.original_value = conf_orientacao
            self.fields['instrucoes_gerais'].required = False
        else:
            self.fields['ciencia_instrucoes_gerais'].widget = forms.HiddenInput()
            self.fields['ciencia_instrucoes_gerais'].required = False
            self.fields['instrucoes_gerais'].widget = forms.HiddenInput()


class ProcessoEditarAssuntoForm(forms.ModelFormPlus):
    assunto = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Assunto')
    justificativa = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Justificativa da alteração')

    class Meta:
        model = Processo
        fields = ('assunto', 'justificativa')


class RotuloForm(forms.ModelFormPlus):
    CORES_CHOICES = (
        ('alert', 'Amarelo'),
        ('info', 'Azul'),
        ('extra7', 'Azul-petróleo'),
        ('extra5', 'Ciano'),
        ('extra', 'Laranja'),
        ('extra6', 'Marrom'),
        ('extra4', 'Rosa'),
        ('extra2', 'Roxo'),
        ('success', 'Verde'),
        ('extra3', 'Verde limão'),
        ('error', 'Vermelho'),
    )

    cor = forms.ChoiceField(label='Cor', choices=CORES_CHOICES)
    setor = forms.ModelChoiceFieldPlus(queryset=Setor.objects.suap_ativos().none(), label='Setor')
    legenda = forms.CharFieldPlus(label='Legenda', required=True)

    fieldsets = ((None, {'fields': ('setor', 'legenda', 'descricao', 'cor', 'ativo')}),)

    class Meta:
        model = Rotulo
        fields = ('cor', 'legenda', 'descricao', 'setor', 'ativo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user
        meu_setor = get_setor(user)
        setores_qs = Setor.objects.suap().filter(excluido=False) if user.is_superuser else setores_que_sou_chefe_ou_tenho_poder_de_chefe(user)
        self.fields['setor'].queryset = setores_qs
        self.fields['setor'].initial = meu_setor.id
        # Check if we are adding or editing
        self.is_editing = bool(self.instance and self.instance.pk)

    def clean(self):
        cleaned_data = super().clean()
        legenda = cleaned_data.get('legenda')
        setor = cleaned_data.get('setor')
        cor = cleaned_data.get('cor')
        queryset = Rotulo.objects.filter(legenda__iexact=legenda, cor=cor, setor=setor, ativo=True)
        if self.instance.pk:
            queryset = queryset.exclude(pk=self.instance.pk)
        if queryset.exists():
            self.add_error('legenda', f'Um rótulo com a mesma legenda já foi cadastrado para o setor {setor}')
        return cleaned_data


class AdicionarRotuloForm(forms.FormPlus):
    rotulo = forms.ModelChoiceFieldPlus(queryset=Rotulo.objects.none(), label='Rótulo')

    def __init__(self, *args, **kwargs):
        self.tramite = kwargs.pop('tramite', None)
        super().__init__(*args, **kwargs)
        self.fields['rotulo'].initial = self.tramite.rotulo
        self.fields['rotulo'].queryset = Rotulo.objects.filter(ativo=True, setor=self.tramite.destinatario_setor)
