from datetime import datetime
from itertools import chain

import dateutil.parser
from django.apps import apps
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import authenticate
from django.contrib.contenttypes.models import ContentType
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.forms.formsets import formset_factory
from django.http import HttpRequest
from django.utils.safestring import mark_safe
from reversion import revisions as reversion
from tinymce.widgets import TinyMCE

if 'catalogo_provedor_servico' in settings.INSTALLED_APPS:
    from catalogo_provedor_servico.models import TemplateNotificaGovBR

from comum.exceptions import LoginException, UserMustResetPassword
from comum.models import APIExterna, Configuracao, Vinculo
from comum.utils import get_setor, get_todos_setores, tl
from djtools import forms
from djtools.forms import ReadOnlyField, ReCaptchaField, SpanField, SpanWidget
from djtools.forms.widgets import AutocompleteWidget, TextareaCounterWidget
from djtools.middleware.govbr import govbr_confiability_level
from djtools.utils import full_check_file, get_client_ip, get_datetime_now, random_with_N_digits, send_mail
from documento_eletronico.models import (
    AssinaturaDocumentoTexto,
    Classificacao,
    CompartilhamentoDocumentoDigitalizadoPessoa,
    CompartilhamentoDocumentoPessoa,
    CompartilhamentoSetorPessoa,
    Documento,
    DocumentoDigitalizado,
    DocumentoDigitalizadoAnexoSimples,
    DocumentoDigitalizadoPessoal,
    DocumentoTexto,
    DocumentoTextoPessoal,
    HipoteseLegal,
    ModeloDocumento,
    NivelAcesso,
    NivelPermissao,
    RegistroAcaoDocumento,
    RegistroAcaoDocumentoTexto,
    ConfiguracaoVinculoDocumento,
    RestricaoAssinatura,
    SolicitacaoAssinatura,
    SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa,
    TipoConferencia,
    TipoDocumento,
    TipoDocumentoTexto,
    TipoVinculoDocumento,
    VinculoDocumentoTexto,
)
from documento_eletronico.status import DocumentoStatus, SolicitacaoStatus
from documento_eletronico.utils import get_setores_compartilhados
from rh.models import CargoEmprego, Funcao, Papel, Pessoa, Servidor, Setor, UnidadeOrganizacional
from suap import nomenclatura


def _widget_tinymce_documento() -> TinyMCE:
    return TinyMCE(
        attrs={'class': 'tinymce'},
        mce_attrs={'content_css': '/static/documento_eletronico/css/documento.css'},
    )


class CriarDocumentoRelacionadoForm(forms.FormPlus):
    configuracao = forms.ModelChoiceField(queryset=ConfiguracaoVinculoDocumento.objects.none(), label='Documento a ser criado', required=True)
    modelo = forms.ModelChoiceField(
        queryset=ModeloDocumento.ativos.none(),
        label='Modelo',
        required=True,
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
    )
    usar_conteudo_vigente_como_base = forms.BooleanField(
        label='Criar a partir do conteúdo vigente',
        required=False,
        help_text=(
            'Copia integralmente o conteúdo vigente para o novo documento e permite visualizar posteriormente '
            'as versões original, comparativa e consolidada. Não selecione esta opção quando o novo documento '
            'contiver apenas comandos de alteração, como "onde se lê" ou "fica revogado o artigo".'
        ),
    )

    def __init__(self, *args, documento: DocumentoTexto, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        configuracoes = ConfiguracaoVinculoDocumento.objects.filter(ativo=True, tipo_documento_alvo=documento.tipo).select_related(
            'tipo_vinculo_documento', 'tipo_documento_base', 'tipo_documento_alvo', 'modelo_padrao'
        )
        self.fields['configuracao'].queryset = configuracoes
        self.fields['modelo'].queryset = ModeloDocumento.ativos.filter(tipo_documento_texto__in=configuracoes.values('tipo_documento_base'))
        configuracao_id = self.data.get('configuracao') if self.is_bound else None
        configuracao = (
            configuracoes.filter(pk=configuracao_id).first() if configuracao_id else configuracoes.filter(modelo_padrao__isnull=False).first()
        )
        if configuracao:
            self.fields['modelo'].queryset = ModeloDocumento.ativos.filter(tipo_documento_texto=configuracao.tipo_documento_base)
            if not self.is_bound and configuracao.modelo_padrao_id:
                self.fields['modelo'].initial = configuracao.modelo_padrao_id

    def clean(self) -> dict:
        cleaned_data = super().clean()
        configuracao = cleaned_data.get('configuracao')
        modelo = cleaned_data.get('modelo')
        if configuracao and modelo and modelo.tipo_documento_texto_id != configuracao.tipo_documento_base_id:
            self.add_error('modelo', 'O modelo deve pertencer ao tipo de documento definido pela configuração.')
        return cleaned_data


class ConfiguracaoForm(forms.FormPlus):
    if 'centralservicos' in settings.INSTALLED_APPS:
        BaseConhecimento = apps.get_model('centralservicos', 'BaseConhecimento')
        base_conhecimento_permissao_acesso_documento = forms.ModelChoiceField(
            BaseConhecimento.objects.filter(ativo=True, visibilidade=BaseConhecimento.VISIBILIDADE_PUBLICA),
            label='Base de conhecimento com instruções de como dar permissão leitura e/ou criação/edição de documentos',
            required=False,
        )
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        modelo_documento_termo_anexaxao_processos = forms.ModelChoiceField(
            ModeloDocumento.objects.filter(ativo=True),
            label='Modelo de Documento para Termo de Juntada por Anexação',
            widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
            help_text='Ex: Termo de Juntada por Anexação',
            required=False,
        )
    tipo_documento_requerimento = forms.ModelChoiceField(
        TipoDocumento.objects.filter(ativo=True),
        label='Tipo de Documento para Requerimento',
        required=False,
    )
    grupossistemicos_com_perm_leitura_de_modelosdoc = forms.CharFieldPlus(
        label='Grupos de Usuários com permissão sistêmica a modelos de documentos',
        widget=forms.Textarea,
        max_length=255,
        required=False,
        help_text='Relação de grupos de usuários e modelos de documentos que os integrantes sempre poderão ler.'
        'Deve estar em formato JSON: { "grupo1": [ id_modelo1, id_modelo2, ... ], "grupo2": ... }',
    )
    permite_assinatura_lote = forms.BooleanField(label='Permite Assinatura em Lote', required=False)
    permite_finalizacao_lote = forms.BooleanField(label='Permite Finalização em Lote', required=False)
    permite_busca_corpo_conteudo = forms.BooleanField(label='Permite Busca no Corpo do Conteúdo', required=False)
    registrar_acoes_documentos_publicos = forms.BooleanField(
        label='Registrar Ações em Documentos Públicos',
        required=False,
        help_text='Marque essa opção caso deseje registrar ações de visualização e impressão de documentos púbicos',
    )


# Form utilizado no cadastro de DocumentoTexto, para inclusão e edição dos dados básicos.
class DocumentoTextoForm(forms.ModelFormPlus):
    tipo = forms.ModelChoiceField(TipoDocumentoTexto.ativos, label='Tipo do Documento', required=True)
    modelo = forms.ModelChoiceField(ModeloDocumento.ativos.all(), label='Modelo', required=True)
    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )
    assunto = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Assunto')
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects, label='Classificações', required=False, disabled=True)
    setor_dono = forms.ModelChoiceField(label='Setor Dono', queryset=Setor.objects.suap_ativos().none(), required=True)

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    class Meta:
        model = DocumentoTexto
        fields = ('tipo', 'modelo', 'nivel_acesso', 'hipotese_legal', 'setor_dono', 'assunto')

    class Media:
        js = ['/static/documento_eletronico/js/DocumentoTextoForm.js']

    def clean_nivel_acesso(self):
        nivel_acesso = self.cleaned_data.get('nivel_acesso')
        if self.instance.id:
            old_version = DocumentoTexto.objects.get(id=self.instance.id)
            self.instance.nivel_acesso = nivel_acesso
            if self.instance.nivel_acesso != old_version.nivel_acesso:
                self.instance.validar_auteracao_nivel_acesso(self.request.user)
        return nivel_acesso

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edit_mode = bool(self.instance.pk)

        # Montando o combo com os setores pertinentes.
        if edit_mode and self.instance.estah_em_revisao:
            qs_setores_usuario = Setor.objects.suap_ativos().filter(id=self.instance.setor_dono_id)
        else:
            qs_setores_usuario = get_setores_compartilhados(self.request.user, NivelPermissao.EDITAR)
        self.fields['setor_dono'].queryset = qs_setores_usuario

        # Se só tem um setor disponível, então ele já é logo setado no combobox.
        if qs_setores_usuario.count() == 1:
            self.fields['setor_dono'].initial = qs_setores_usuario[0]
            self.fields['setor_dono'].widget.original_value = qs_setores_usuario[0]

        if edit_mode:
            # Ajuste para impedir a edição do tipo de documento. Obs: Nesse caso se faz necessário colocar
            # "required = False" para que o form não reclame que a informaçãon não está fornecida, já que
            # ela está!
            self.fields['tipo'].initial = self.instance.modelo.tipo_documento_texto
            self.fields['tipo'].widget = forms.widgets.HiddenInput()
            self.fields['tipo'].required = False
            self.fields['tipo'].help_text = 'O tipo de documento não pode ser alterado'

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

        if 'processo_eletronico' in settings.INSTALLED_APPS:
            ConfiguracaoInstrucaoNivelAcesso = apps.get_model('processo_eletronico', 'ConfiguracaoInstrucaoNivelAcesso')

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

    def save(self, commit=True):
        if not self.instance.id:
            self.instance.data_criacao = datetime.now()
            self.instance.usuario_criacao = self.request.user

        self.instance.data_ultima_modificacao = datetime.now()
        self.instance.usuario_ultima_modificacao = self.request.user
        return super().save(commit)


class DocumentoTextoEditarCorpoForm(forms.ModelFormPlus):
    corpo = forms.CharField(
        required=False,
        label='',
        widget=_widget_tinymce_documento(),
    )

    class Meta:
        model = DocumentoTexto
        fields = ('corpo',)

    def clean(self):
        self.instance.corpo = self.cleaned_data.get('corpo')

        # Os atributos "corpo" e "data_ultima_modificacao__isoformat" são atributos colocados "manualmente" na página.
        # Como não podem ser definidos no atributo "fields" do Meta, seu estado terá que ser mantido manualmente, em
        # caso de erro.
        #
        # O motivo pelo qual esses campos não podem ser definidos em "fields" do Meta são:
        # - corpo: por conta de ser um campo rico de texto.
        # - data_ultima_modificacao__isoformat: por ser "editable=false", o que impede dele ser definido no "fields"do Meta.
        # No caso trata-se de um campo hidden criado para guardar, sem exibir, a data da última modificação realizada no
        # momento em que o usuário carregou o documento para edição.
        #
        # Obs: Os campos definidos no atributo "fields" do Meta tem seu estado mantido no form pelo próprio Django.

        # O self.instance é um objeto Documento do jeito que está no banco de dados atualmente. Por isso aqui setamos
        # o valor do corpo com base no que o usuário está submetendo. Dando erro ou não, o corpo tem que ser mantido
        # da mesma forma como o usuário submeteu.
        self._verficar_data_ultima_modificacao()

        return self.cleaned_data

    def save(self, *args, **kwargs):
        # Atualizado os dados sobre a última modificação realizada antes do save().
        self.instance.data_ultima_modificacao = datetime.now()
        self.instance.usuario_ultima_modificacao = self.request.user
        return super().save(*args, **kwargs)

    def _verficar_data_ultima_modificacao(self):
        # Se data_ultima_modificacao atual (vinda do banco de dados) difere da data_ultima_modificacao quando o usuário
        # resgatou o objeto do banco para iniciar a edição...
        if self.data['data_ultima_modificacao__isoformat'] != self.instance.data_ultima_modificacao.isoformat():
            usuario_ultima_modificacao = self.instance.usuario_ultima_modificacao
            data_ultima_modificacao = self.instance.data_ultima_modificacao

            # Ajustando a data_ultima_modificacao para que ela se mantenha com o mesmo valor de quando o usuário carregou
            # a página de edição do documento pela primeira vez, mantendo assim o mesmo estado desse atributo. Isso vai
            # impedir que o usuário consiga burlar o controle de edição concorrente apenas clicando duas ou mais vezes
            # em "Salvar".
            self.instance.data_ultima_modificacao = dateutil.parser.parse(self.data['data_ultima_modificacao__isoformat'])
            #
            raise forms.ValidationError(
                'Este documento foi modificado por {} às {}. Copie as alterações realizadas e carregue novamente o documento.'.format(
                    usuario_ultima_modificacao, data_ultima_modificacao.strftime('%d/%m/%Y - %H:%M')
                )
            )


class DocumentoTextoEditarTagsAnonimizacaoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoTexto
        fields = ('tags_anonimizacao',)


class TipoDocumentoForm(forms.ModelFormPlus):
    class Meta:
        model = TipoDocumento
        fields = ('nome', 'sigla', 'ativo', 'permite_documentos_pessoais')


class TipoDocumentoTextoForm(forms.ModelFormPlus):
    cabecalho_padrao = forms.CharField(widget=_widget_tinymce_documento(), required=False)
    rodape_padrao = forms.CharField(widget=_widget_tinymce_documento(), required=False)

    class Meta:
        model = TipoDocumentoTexto
        fields = (
            'nome',
            'sigla',
            'tipo_sequencia',
            'ativo',
            'vincular_pessoa',
            'cabecalho_padrao',
            'rodape_padrao',
            'permite_documentos_pessoais',
            'permite_documentos_anexos',
            'consulta_publica',
            'permite_busca_corpo_conteudo',
        )

    class Media:
        js = ['/static/tinymce/tiny_mce_toolbar.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.instance.usa_sequencial_anual:
            self.fields['tipo_sequencia'].widget.attrs['readonly'] = True
        if (
            not Configuracao.get_valor_por_chave('documento_eletronico', 'permite_busca_corpo_conteudo')
            and 'permite_busca_corpo_conteudo' in self.fields
        ):
            self.fields['permite_busca_corpo_conteudo'].widget = forms.HiddenInput()

    def clean_tipo_sequencia(self):
        tipo_sequencia = self.cleaned_data.get('tipo_sequencia')
        if self.instance.pk and not self.instance.usa_sequencial_anual:
            if tipo_sequencia != self.instance.tipo_sequencia:
                self.add_error('tipo_sequencia', 'A conversão entre os tipos de numeração não é permitido.')
        #
        return tipo_sequencia

    def clean_cabecalho_padrao(self):
        cabecalho_padrao = self.cleaned_data.get('cabecalho_padrao')
        if len(cabecalho_padrao) > 100 * 1024:
            raise ValidationError('Cabeçalho padrão muito grande')
        return cabecalho_padrao

    def clean_rodape_padrao(self):
        rodape_padrao = self.cleaned_data.get('rodape_padrao')
        if len(rodape_padrao) > 100 * 1024:
            raise ValidationError('Rodapé padrão muito grande')
        return rodape_padrao


class TipoDocumentoTextoAddForm(TipoDocumentoTextoForm):
    class Meta:
        model = TipoDocumentoTexto
        fields = (
            'nome',
            'sigla',
            'tipo_sequencia',
            'ativo',
            'vincular_pessoa',
            'cabecalho_padrao',
            'rodape_padrao',
            'permite_documentos_pessoais',
            'permite_documentos_anexos',
        )


class ModeloDocumentoForm(forms.ModelFormPlus):
    tipo_documento_texto = forms.ModelChoiceFieldPlus(TipoDocumentoTexto.ativos, label='Tipo do Documento', required=True)
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects.all(), label='Classificações', required=False)

    fieldsets = (
        ('Dados Principais', {'fields': ('tipo_documento_texto', 'nome', 'classificacao')}),
        (
            'Níveis de Acesso Permitidos',
            {'fields': ('permite_nivel_acesso_sigiloso', 'permite_nivel_acesso_restrito', 'permite_nivel_acesso_publico')},
        ),
        ('', {'fields': ('nivel_acesso_padrao',)}),
        ('', {'fields': ('ativo',)}),
    )

    class Meta:
        model = ModeloDocumento
        fields = (
            'nome',
            'tipo_documento_texto',
            'permite_nivel_acesso_sigiloso',
            'permite_nivel_acesso_restrito',
            'permite_nivel_acesso_publico',
            'nivel_acesso_padrao',
            'classificacao',
            'ativo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classificacao'].queryset = Classificacao.podem_classificar.all()


class EditarModeloDocumentoForm(forms.ModelFormPlus):
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects.all(), label='Classificações', required=False)
    corpo_padrao = forms.CharField(widget=_widget_tinymce_documento(), required=False, label='')
    fieldsets = (
        (
            None,
            {
                'fields': (
                    'nome',
                    'tipo_documento_texto',
                    'permite_nivel_acesso_sigiloso',
                    'permite_nivel_acesso_restrito',
                    'permite_nivel_acesso_publico',
                    'nivel_acesso_padrao',
                    'classificacao',
                    'ativo',
                )
            },
        ),
    )

    class Meta:
        model = ModeloDocumento
        fields = (
            'nome',
            'tipo_documento_texto',
            'permite_nivel_acesso_sigiloso',
            'permite_nivel_acesso_restrito',
            'permite_nivel_acesso_publico',
            'nivel_acesso_padrao',
            'classificacao',
            'corpo_padrao',
            'ativo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['classificacao'].queryset = Classificacao.podem_classificar.all()


class GerenciarCompartilhamentoPessoaForm(forms.FormPlus):
    pessoas_permitidas_podem_ler = forms.MultipleModelChoiceFieldPlus(
        label='Servidores que podem ler', queryset=Servidor.objects.all(), required=False
    )
    pessoas_permitidas_podem_escrever = forms.MultipleModelChoiceFieldPlus(
        label='Servidores que podem editar', queryset=Servidor.objects.all(), required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pessoas_permitidas_podem_ler'].initial = self.pessoas_permitidas.filter(nivel_permissao=NivelPermissao.LER)
        self.fields['pessoas_permitidas_podem_escrever'].initial = self.pessoas_permitidas.filter(nivel_permissao=NivelPermissao.EDITAR)
        self.compartilhamentos = ''
        self.descompartilhamentos = ''

    @transaction.atomic()
    def save(self):
        cleaned_data = self.cleaned_data

        self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_ler'], NivelPermissao.LER)
        self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_escrever'], NivelPermissao.EDITAR)

    def adicionar_compartilhamento_pessoa(self, pessoas_permitidas, nivel_permissao):
        pessoas_permitidas_a_remover = self.pessoas_com_acesso.exclude(vinculo_permitido__in=pessoas_permitidas)
        if pessoas_permitidas_a_remover.exists():
            self.__preparar_descompartilhamento_observacao(pessoas_permitidas_a_remover, self.get_model_pessoa(), nivel_permissao)
            pessoas_permitidas_a_remover.delete()

        pessoas_permitidas_a_adicionar = pessoas_permitidas.exclude(id__in=self.pessoas_com_acesso.values_list('vinculo_permitido_id', flat=True))
        if pessoas_permitidas_a_adicionar.exists():
            for pessoa_permitida_a_adicionar in pessoas_permitidas_a_adicionar:
                model = self.get_model_pessoa()
                model.vinculo_permitido = pessoa_permitida_a_adicionar
                model.nivel_permissao = nivel_permissao
                model.save()
            self.__preparar_compartilhamento_observacao(pessoas_permitidas_a_adicionar, self.get_model_pessoa(), nivel_permissao)

    def __preparar_compartilhamento_observacao(self, permitidos_a_adicionar, model, nivel_permissao):
        self.compartilhamentos += ' a(s) pessoa(s): ('
        self.compartilhamentos += ', '.join([str(permitido) for permitido in permitidos_a_adicionar])
        self.compartilhamentos += f') para {dict(NivelPermissao.CHOICES)[nivel_permissao]};'

    def __preparar_descompartilhamento_observacao(self, permitidos_a_remover, model, nivel_permissao):
        self.descompartilhamentos += ' a(s) pessoa(s): ('
        self.descompartilhamentos += ', '.join([str(permitido.vinculo_permitido) for permitido in permitidos_a_remover])
        self.descompartilhamentos += f') para {dict(NivelPermissao.CHOICES)[nivel_permissao]}'


class GerenciarCompartilhamentoForm(forms.FormPlus):
    qs_prestadores_servidores = Vinculo.objects.servidores() | Vinculo.objects.prestadores()
    pessoas_permitidas_podem_ler = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço que podem ler', queryset=qs_prestadores_servidores, required=False
    )
    pessoas_permitidas_podem_escrever = forms.MultipleModelChoiceFieldPlus(
        label='Servidores/Prestadores de Serviço que podem editar e ler', queryset=qs_prestadores_servidores, required=False
    )
    setores_permitidos_podem_ler = forms.MultipleModelChoiceFieldPlus(
        label='Setores que podem ler',
        queryset=Setor.objects.suap_ativos().all(),
        required=False,
        help_text='Somente os servidores do(s) setor(es) selecionado(s) poderão ler documentos eletrônicos',
    )
    setores_permitidos_podem_escrever = forms.MultipleModelChoiceFieldPlus(
        label='Setores que podem editar e ler',
        queryset=Setor.objects.suap_ativos().all(),
        required=False,
        help_text='Somente os servidores do(s) setor(es) selecionado(s) poderão adicionar, operar e ler documentos eletrônicos',
    )

    fieldsets = (
        ('Com Setores', {'fields': ('setores_permitidos_podem_ler', 'setores_permitidos_podem_escrever')}),
        ('Com Pessoas', {'fields': ('pessoas_permitidas_podem_ler', 'pessoas_permitidas_podem_escrever')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pessoas_permitidas_podem_ler'].initial = self.pessoas_permitidas.filter(nivel_permissao=NivelPermissao.LER)
        self.fields['pessoas_permitidas_podem_escrever'].initial = self.pessoas_permitidas.filter(nivel_permissao=NivelPermissao.EDITAR)

        self.compartilhamentos = ''
        self.descompartilhamentos = ''

    @transaction.atomic()
    def save(self):
        cleaned_data = self.cleaned_data

        self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_ler'], NivelPermissao.LER)
        self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_escrever'], NivelPermissao.EDITAR)

        self.adicionar_compartilhamento_setores(cleaned_data['setores_permitidos_podem_ler'], NivelPermissao.LER)
        self.adicionar_compartilhamento_setores(cleaned_data['setores_permitidos_podem_escrever'], NivelPermissao.EDITAR)

        self._salvar_acesso()

    def get_model_pessoa(self):
        raise NotImplementedError

    def get_model_setor(self):
        raise NotImplementedError

    def adicionar_compartilhamento_pessoa(self, pessoas_permitidas, nivel_permissao):
        pessoas_permitidas_a_remover = self.pessoas_com_acesso.exclude(vinculo_permitido__in=pessoas_permitidas)
        if pessoas_permitidas_a_remover.exists():
            self.__preparar_descompartilhamento_observacao(pessoas_permitidas_a_remover, self.get_model_pessoa(), nivel_permissao)
            for pessoa_permitida_a_remover in pessoas_permitidas_a_remover:
                pessoa_permitida_a_remover.delete()

        pessoas_permitidas_a_adicionar = pessoas_permitidas.exclude(id__in=self.pessoas_com_acesso.values_list('vinculo_permitido_id', flat=True))
        if pessoas_permitidas_a_adicionar.exists():
            for pessoa_permitida_a_adicionar in pessoas_permitidas_a_adicionar:
                model = self.get_model_pessoa()
                model.vinculo_permitido = pessoa_permitida_a_adicionar
                model.nivel_permissao = nivel_permissao
                model.save()

            self.__preparar_compartilhamento_observacao(pessoas_permitidas_a_adicionar, self.get_model_pessoa(), nivel_permissao)

    def adicionar_compartilhamento_setores(self, setores_permitidos, nivel_permissao):
        setores_permitidos_a_adicionar = setores_permitidos
        pessoas = []
        for setor_permitido_a_adicionar in setores_permitidos_a_adicionar:
            for servidor in setor_permitido_a_adicionar.get_servidores(recursivo=False):
                model = self.get_model_pessoa()
                model.vinculo_permitido = servidor.get_vinculo()
                model.nivel_permissao = nivel_permissao
                model.save()
                pessoas.append(servidor.pessoa_fisica)

        self.__preparar_compartilhamento_observacao(pessoas, self.get_model_pessoa(), nivel_permissao)

    def __preparar_compartilhamento_observacao(self, permitidos_a_adicionar, model, nivel_permissao):
        if model.__class__ in [CompartilhamentoDocumentoPessoa, CompartilhamentoSetorPessoa]:
            self.compartilhamentos += ' a(s) pessoa(s): ('

        self.compartilhamentos += ', '.join([str(permitido) for permitido in permitidos_a_adicionar])
        self.compartilhamentos += f') para {dict(NivelPermissao.CHOICES)[nivel_permissao]};'

    def __preparar_descompartilhamento_observacao(self, permitidos_a_remover, model, nivel_permissao):
        if model.__class__ in [CompartilhamentoDocumentoPessoa, CompartilhamentoSetorPessoa]:
            self.descompartilhamentos += ' a(s) pessoa(s): ('
            self.descompartilhamentos += ', '.join([str(permitido.vinculo_permitido) for permitido in permitidos_a_remover])

        self.descompartilhamentos += f') para {dict(NivelPermissao.CHOICES)[nivel_permissao]};'

    def _salvar_acesso(self):
        documento = None
        compartilhamentos = None
        descompartilhamentos = None
        #
        if self.__class__ == GerenciarCompartilhamentoDocumentoForm:
            documento = self.documento
            compartilhamentos = f'Compartilhamento do documento com{self.compartilhamentos}'
            descompartilhamentos = f'Descompartilhamento do documento com{self.descompartilhamentos}'
        elif self.__class__ == GerenciarCompartilhamentoSetorForm:
            setor = self.setor
            compartilhamentos = f'Compartilhamento dos documentos do setor {setor} com{self.compartilhamentos}'
            descompartilhamentos = f'Descompartilhado dos documentos do setor {setor} com{self.descompartilhamentos}'

        user = self.request.user
        ip = get_client_ip(self.request)
        if self.compartilhamentos:
            RegistroAcaoDocumentoTexto.registrar_acao(documento, RegistroAcaoDocumento.TIPO_COMPARTILHAMENTO, user, ip, compartilhamentos)
        #
        if self.descompartilhamentos:
            RegistroAcaoDocumentoTexto.registrar_acao(documento, RegistroAcaoDocumento.TIPO_DESCOMPARTILHAMENTO, user, ip, descompartilhamentos)


class GerenciarCompartilhamentoSetorForm(GerenciarCompartilhamentoForm):
    CLASSNAME = 'featured-form normal-label'

    def __init__(self, *args, **kwargs):
        if 'request' in kwargs:
            self.request = kwargs.pop('request')
        if 'setor' in kwargs:
            self.setor = kwargs.pop('setor')
        else:
            self.setor = get_setor(self.request.user)
        self.pessoas_permitidas = CompartilhamentoSetorPessoa.objects.filter(setor_dono=self.setor, vinculo_permitido__isnull=False).values_list(
            'vinculo_permitido_id', flat=True
        )
        super().__init__(*args, **kwargs)

        self.fields['setores_permitidos_podem_ler'].label = f'Setores que podem ler documentos do(a) {self.setor}'
        self.fields['setores_permitidos_podem_escrever'].label = f'Setores que podem adicionar, operar e ler documentos do(a) {self.setor}'

        self.fields['pessoas_permitidas_podem_ler'].label = f'Servidores/Prestadores de Serviço que podem ler documentos do(a) {self.setor}'
        self.fields[
            'pessoas_permitidas_podem_escrever'
        ].label = f'Servidores/Prestadores de Serviço que podem adicionar, operar e ler documentos do(a) {self.setor}'

    def get_model_pessoa(self):
        return CompartilhamentoSetorPessoa(setor_dono=self.setor)

    def adicionar_compartilhamento_pessoa(self, pessoas_permitidas, nivel_permissao):
        self.pessoas_com_acesso = CompartilhamentoSetorPessoa.objects.filter(
            setor_dono=self.setor, nivel_permissao=nivel_permissao, vinculo_permitido__isnull=False
        )
        super().adicionar_compartilhamento_pessoa(pessoas_permitidas, nivel_permissao)

    def adicionar_compartilhamento_setores(self, setores_permitidos, nivel_permissao):
        super().adicionar_compartilhamento_setores(setores_permitidos, nivel_permissao)

    def clean(self):
        cleaned_data = super().clean()
        pessoas_permitidas_podem_ler = cleaned_data.get('pessoas_permitidas_podem_ler', [])
        pessoas_permitidas_podem_escrever = cleaned_data.get('pessoas_permitidas_podem_escrever', [])
        setores_permitidos_podem_ler = cleaned_data.get('setores_permitidos_podem_ler', [])
        setores_permitidos_podem_escrever = cleaned_data.get('setores_permitidos_podem_escrever', [])

        for pessoa_permitida_pode_ler in pessoas_permitidas_podem_ler:
            # Se já estiver nas para ser incluida como pode escrever ignora ela das que podem ler
            if pessoa_permitida_pode_ler in pessoas_permitidas_podem_escrever:
                cleaned_data['pessoas_permitidas_podem_ler'] = pessoas_permitidas_podem_ler.exclude(id=pessoa_permitida_pode_ler.id)

        for setor_permitido_pode_ler in setores_permitidos_podem_ler:
            # Se já estiver nas para ser incluido como pode escrever ignora ele das que podem ler
            if setor_permitido_pode_ler in setores_permitidos_podem_escrever:
                cleaned_data['setores_permitidos_podem_ler'] = setores_permitidos_podem_ler.exclude(id=setor_permitido_pode_ler.id)

        return cleaned_data


class GerenciarCompartilhamentoDocumentoForm(GerenciarCompartilhamentoForm):
    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        self.pessoas_permitidas = CompartilhamentoDocumentoPessoa.objects.filter(
            documento=self.documento, solicitacao_assinatura__isnull=True
        ).values_list('vinculo_permitido_id', flat=True)
        #
        super().__init__(*args, **kwargs)
        # Compartilhamento de Documento:
        #  SIGILOSO: aparecem tanto a opção de compartilhar leitura e edição (só pessoa)
        # No caso de documentos pessoais temos apenas compartilhamento com pessoas
        if self.documento.eh_documento_pessoal or self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_SIGILOSO:
            self.fields.pop('setores_permitidos_podem_ler')
            self.fields.pop('setores_permitidos_podem_escrever')
        if self.documento.eh_documento_pessoal:
            self.fieldsets = (('Com Pessoas', {'fields': ('pessoas_permitidas_podem_ler', 'pessoas_permitidas_podem_escrever')}),)

    def get_model_pessoa(self):
        return CompartilhamentoDocumentoPessoa(documento=self.documento)

    def adicionar_compartilhamento_pessoa(self, pessoas_permitidas, nivel_permissao):
        self.pessoas_com_acesso = CompartilhamentoDocumentoPessoa.objects.filter(
            documento=self.documento, nivel_permissao=nivel_permissao, vinculo_permitido__isnull=False, solicitacao_assinatura__isnull=True
        )
        super().adicionar_compartilhamento_pessoa(pessoas_permitidas, nivel_permissao)

    def adicionar_compartilhamento_setores(self, setores_permitidos, nivel_permissao):
        super().adicionar_compartilhamento_setores(setores_permitidos, nivel_permissao)

    @transaction.atomic()
    def save(self):
        user = self.request.user
        setor = get_setor(user)
        cleaned_data = self.cleaned_data
        # Compartilhamento de Documento:
        #  SIGILOSO: aparecem tanto a opção de compartilhar leitura e edição (só pessoa)
        if (
            self.documento.eh_documento_pessoal or self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_SIGILOSO
        ) and self.documento.usuario_criacao == user:
            self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_ler'], NivelPermissao.LER)
            self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_escrever'], NivelPermissao.EDITAR)

        elif (self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_RESTRITO and self.documento.setor_dono == setor) or (
            self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_PUBLICO
        ):
            self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_ler'], NivelPermissao.LER)
            self.adicionar_compartilhamento_pessoa(cleaned_data['pessoas_permitidas_podem_escrever'], NivelPermissao.EDITAR)

            self.adicionar_compartilhamento_setores(cleaned_data['setores_permitidos_podem_ler'], NivelPermissao.LER)
            self.adicionar_compartilhamento_setores(cleaned_data['setores_permitidos_podem_escrever'], NivelPermissao.EDITAR)

        self._salvar_acesso()

    def clean(self):
        """
        O clean verifica se o conjunto de permissoes fornecidas ao usuario constitui um conjunto valido.
        Um usuario com permissao de escrita concede permissao de leitura e escrita.
        A listas pessoas_permitidas_podem_ler e pessoas_permitidas_podem_escrever contem o conjunto atual
        de usuario com as permissoes de leitura e escrita respectivamente. O mesmo vale para as listas
        dos setores.
        Dado que o usuario pode tanto conceder uma permissao maior quanto menor, os testes devem comparar
        as listas do cleaned_data com os dados do banco de dados.

        """
        cleaned_data = super().clean()
        pessoas_permitidas_podem_ler = cleaned_data.get('pessoas_permitidas_podem_ler') or ()
        pessoas_permitidas_podem_escrever = cleaned_data.get('pessoas_permitidas_podem_escrever') or ()

        for pessoa_permitida_pode_ler in pessoas_permitidas_podem_ler:
            eh_documento_sigiloso = self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_SIGILOSO
            if (
                not self.documento.eh_documento_pessoal
                and not eh_documento_sigiloso
                and self.documento.setor_dono.compartilhamentosetorpessoa_set.filter(
                    vinculo_permitido=pessoa_permitida_pode_ler, nivel_permissao=NivelPermissao.LER
                ).exists()
            ):
                self.add_error('pessoas_permitidas_podem_ler', f'{pessoa_permitida_pode_ler} já tem permissão de Leitura aos documentos do setor.')

            elif (
                not self.documento.eh_documento_pessoal
                and not eh_documento_sigiloso
                and self.documento.setor_dono.compartilhamentosetorpessoa_set.filter(
                    vinculo_permitido=pessoa_permitida_pode_ler, nivel_permissao=NivelPermissao.EDITAR
                ).exists()
            ):
                self.add_error(
                    'pessoas_permitidas_podem_ler', f'{pessoa_permitida_pode_ler} já tem permissão de Leitura e Edição aos documentos do setor.'
                )

            # Se já não tiver sido incluido
            elif not self.documento.compartilhamento_pessoa_documento.filter(
                vinculo_permitido=pessoa_permitida_pode_ler, nivel_permissao=NivelPermissao.LER
            ):
                # Uma pessoa possuia permissao de escrita e esta sendo rebaixada a apenas leitura, portanto, deve-se
                # verifica se a pessoa que esta pedindo acesso de leitura esta na lista das pessoas que mantem o status
                # de escrita. Se não estiver, deve-se verificar se ela ja possuia a permissão ou se esta sendo concedida
                # no momento.
                if pessoa_permitida_pode_ler in pessoas_permitidas_podem_escrever:
                    if self.documento.tem_permissao_estrita_leitura(pessoa_permitida_pode_ler):
                        self.add_error('pessoas_permitidas_podem_ler', f'{pessoa_permitida_pode_ler} já tem permissão de Leitura.')

            # Se já estiver nas para ser incluida como pode escrever ignora ela das que podem ler
            if pessoa_permitida_pode_ler in pessoas_permitidas_podem_escrever:
                cleaned_data['pessoas_permitidas_podem_ler'] = pessoas_permitidas_podem_ler.exclude(id=pessoa_permitida_pode_ler.id)

        for pessoa_permitida_pode_escrever in pessoas_permitidas_podem_escrever:
            eh_documento_sigiloso = self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_SIGILOSO
            if (
                not self.documento.eh_documento_pessoal
                and not eh_documento_sigiloso
                and self.documento.setor_dono.compartilhamentosetorpessoa_set.filter(
                    vinculo_permitido=pessoa_permitida_pode_escrever, nivel_permissao=NivelPermissao.EDITAR
                ).exists()
            ):
                self.add_error(
                    'pessoas_permitidas_podem_escrever',
                    f'{pessoa_permitida_pode_escrever} já tem permissão de Leitura e Edição aos documentos do setor.',
                )

            # Se já não tiver sido incluido
            elif not self.documento.compartilhamento_pessoa_documento.filter(
                vinculo_permitido=pessoa_permitida_pode_escrever, nivel_permissao=NivelPermissao.EDITAR
            ) and self.documento.tem_permissao_editar(pessoa_permitida_pode_escrever.user):
                self.add_error('pessoas_permitidas_podem_escrever', f'{pessoa_permitida_pode_escrever} já tem permissão de Leitura e Edição.')

        if self.documento.nivel_acesso == DocumentoTexto.NIVEL_ACESSO_SIGILOSO:
            cleaned_data['setores_permitidos_podem_ler'] = []
            cleaned_data['setores_permitidos_podem_escrever'] = []

        return cleaned_data


class ListarDocumentosForm(forms.FormPlus):
    METHOD = 'GET'

    pesquisa = forms.CharField(label='Por Número/Conteúdo:', required=False)
    tipo = forms.ModelChoiceField(label='Por Tipo:', required=False, queryset=TipoDocumentoTexto.objects.all(), empty_label='Todos')
    campus = forms.ModelChoiceField(
        label=f'Por {nomenclatura.campus}:', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Todos'
    )
    setor = forms.ChainedModelChoiceField(
        Setor.objects.suap_ativos().all(),
        label='Por Setor:',
        empty_label='Todos',
        required=False,
        obj_label='sigla',
        form_filters=[('campus', 'uo_id')],
    )
    data_criacao = forms.DateFieldPlus(label='Por Data de Criação', required=False)
    ano = forms.IntegerField(label='Filtrar por Ano', widget=forms.Select())
    mes = forms.MesField(label='Filtrar por Mês:', required=False, choices=[], empty_label='Todos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_limite = get_datetime_now().year
        ANO_CHOICES = [(ano, f'{ano}') for ano in range(ano_limite, 2015, -1)]
        self.fields['ano'].widget.choices = ANO_CHOICES

        # Se há um parâmetro de nome "setores" enão não há necessidade dos filtros
        # por campus e/ou setor.
        if self.request.GET.get('setores'):
            del self.fields['setor']
            del self.fields['campus']

    def filtrar_documentos(self, retorno, aplicar_filtro_setor_dono=True):
        params = self.request.GET.dict()
        order_str = ''
        if self.is_valid():
            cleaned_data = self.cleaned_data

            campus = cleaned_data.get('campus')
            if campus:
                retorno = retorno.filter(setor_dono__uo=campus)

            if aplicar_filtro_setor_dono:
                setores = self.request.GET.get('setores')
                if setores:
                    try:
                        retorno = retorno.filter(setor_dono=setores)
                    except Exception:
                        if setores == 'todos_setores_usuario':
                            retorno = retorno.filter(setor_dono__in=get_todos_setores(self.request.user))
                else:
                    setor = cleaned_data.get('setor')
                    if setor:
                        retorno = retorno.filter(setor_dono=setor)

            tipo = cleaned_data.get('tipo')
            if tipo:
                retorno = retorno.filter(modelo__tipo_documento_texto=tipo)

            data_criacao = cleaned_data.get('data_criacao')
            if data_criacao:
                retorno = retorno.filter(
                    data_criacao__year=data_criacao.year, data_criacao__month=data_criacao.month, data_criacao__day=data_criacao.day
                )

            ano = cleaned_data.get('ano')
            mes = cleaned_data.get('mes')
            if not data_criacao and ano != 0:
                retorno = retorno.filter(data_criacao__year=ano)

                mes = self.cleaned_data.get('mes', None)
                if mes and mes != 0:
                    retorno = retorno.filter(data_criacao__month=mes)

            pesquisa = cleaned_data.get('pesquisa')
            if pesquisa:
                filtro_identificador = retorno.filter(identificador__icontains=pesquisa)
                filtro_assunto = retorno.filter(assunto__icontains=pesquisa)
                filtro_cabecalho = retorno.filter(cabecalho__icontains=pesquisa)
                filtro_corpo = retorno.filter(corpo__icontains=pesquisa)
                filtro_rodape = retorno.filter(rodape__icontains=pesquisa)
                retorno = filtro_identificador | filtro_cabecalho | filtro_corpo | filtro_rodape | filtro_assunto

            if 'order_by' in params:
                order_str = params.pop('order_by', '')
                order_tratado = order_str.replace(' ', '')
                if order_tratado[0] == '-':
                    order_tratado = order_tratado.replace(',', ',-')

                retorno = retorno.order_by(*order_tratado.split(','))
        else:
            retorno = retorno.none()
        return retorno, params, order_str


class ListarDocumentosTextoForm(ListarDocumentosForm):
    fieldsets = (('', {'fields': ('pesquisa', 'campus', 'setor', 'tipo', 'ano', 'mes', 'data_criacao')}),)

    def __init__(self, *args, **kwargs):
        self.exceto_documento = None
        if 'exceto_documento' in kwargs:
            self.exceto_documento = kwargs.pop('exceto_documento')
        super().__init__(*args, **kwargs)
        self.fields['campus'].required = True
        self.fields['setor'].required = True

    def processar(self):
        request = self.request
        retorno = DocumentoTexto.objects.by_user(self.request.user).defer('cabecalho', 'rodape', 'corpo')
        todos, params, order_str = self.filtrar_documentos(retorno)
        order_by = todos.query.order_by
        if not order_by:
            order_by = ['-data_criacao', 'modelo__tipo_documento_texto__nome', 'identificador_setor_sigla']

        documentos = retorno.filter(id__in=todos).order_by(*order_by)
        documentos_compartilhados = retorno.compartilhados(request.user).filter(id__in=todos).order_by(*order_by)

        if self.exceto_documento:
            documentos = documentos.exclude(pk=self.exceto_documento.id)

        return documentos, documentos_compartilhados, params, order_str


class AuthenticationForm(forms.FormPlus):
    senha = forms.CharField(widget=forms.PasswordInput)

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


class AuthenticationGovBRForm(forms.FormPlus):
    codigo_verificacao = forms.CharField(help_text='Código enviado para seu aplicativo Gov.BR!')
    EXTRA_BUTTONS = [
        {
            'type': 'button',
            'value': 'Enviar Novo Código - E-mail',
            'name': 'enviar_novo_codigo_email',
            'onclick': 'enviar_codigo_verificacao_email();',
        },
    ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if APIExterna.NOTIFICA_GOVBR.ativo:
            self.EXTRA_BUTTONS = [
                {
                    'type': 'button',
                    'value': 'Enviar Novo Código - App Gov.BR',
                    'name': 'enviar_novo_codigo_govbr',
                    'onclick': 'enviar_codigo_verificacao_govbr();',
                },
                *self.EXTRA_BUTTONS,
            ]

    class Media:
        js = ['/static/documento_eletronico/js/NovoCodigoViaAppGovBRForm.js', '/static/documento_eletronico/js/NovoCodigoViaEmailForm.js']

    def clean(self):
        cod_verificacao_ = self.cleaned_data.get('codigo_verificacao')
        id_confiabilidade_govbr = govbr_confiability_level(self.request)

        if not self.request.session.get('autenticou_com_govbr', False):
            self.add_error('codigo_verificacao', 'Não autenticado com Gov.BR')

        if id_confiabilidade_govbr == '0':
            raise forms.ValidationError('Ocorreu um erro ao tentar acessar sua confiabilidade. Por favor efetue login no suap novamente.')

        if id_confiabilidade_govbr not in ['2', '3']:  # níveis  2 - prata e 3 - ouro
            raise forms.ValidationError(
                'Sua conta Gov.BR não possui o nível Prata que é o mínimo exigido para assinar documentos no SUAP. Acesse o seu aplicativo Gov.BR para atualizar seu nível de confiabilidade!'
            )

        if not cache.get(f'govbr_check_{self.request.user.get_vinculo().id}', None):
            self.gerar_codigo_verificacao()
            self.add_error('codigo_verificacao', 'Código de Verificação Expirou. Foi gerado um novo código e enviado para o App Gov.BR!')
        elif not cod_verificacao_:
            self.add_error('codigo_verificacao', 'Por favor preencha o Código de Verificação!')
        elif str(cod_verificacao_) != str(cache.get(f'govbr_check_{self.request.user.get_vinculo().id}')):
            self.add_error('codigo_verificacao', 'Código de Verificação não confere!')

        return self.cleaned_data

    def gerar_codigo_verificacao(self, force=False):
        TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR = (
            TemplateNotificaGovBR.objects.filter(
                tipo_notificacao=TemplateNotificaGovBR.CODIGO_VERIFICADOR, canal_notificacao=TemplateNotificaGovBR.APP_GOVBR
            )
            .first()
            .id_template
        )

        if not APIExterna.NOTIFICA_GOVBR.ativo:
            if not cache.get(f'govbr_check_{self.request.user.get_vinculo().id}', None) or force:
                codigo_verificacao = random_with_N_digits(5)
                instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                title = f'Código de Verificação - SUAP/{instituicao}'
                instituicao = Configuracao.get_valor_por_chave('comum', 'instituicao_sigla')
                message = f"""<p>Seu código de verificação no SUAP/{instituicao}: {codigo_verificacao}<p>

                              <p>A validade deste código é de 5 minutos.<p>
                          """
                try:
                    # email_secundario migrou p/ Vinculo.email_notificacao; obtém do vínculo do user.
                    vinculo = self.request.user.get_vinculo()
                    email_secundario = vinculo.email_notificacao if vinculo else None
                    if email_secundario:
                        send_mail(title, message, settings.DEFAULT_FROM_EMAIL, [email_secundario])
                    cache.set(f'govbr_check_{self.request.user.get_vinculo().id}', codigo_verificacao, 300)
                    messages.add_message(
                        self.request,
                        messages.SUCCESS,
                        f'Código enviado com sucesso para o e-mail: {email_secundario}. A validade deste código é de 5 minutos.',
                    )
                except Exception:
                    messages.add_message(
                        self.request,
                        messages.ERROR,
                        'Houve um erro ao enviar código de verificação por e-mail, certifique-se que o usuário possui e-mail secundário cadastrado no SUAP.',
                    )
            return
        if not TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR:
            messages.add_message(
                self.request,
                messages.ERROR,
                'Não é possível enviar a notificação pois não foi localizado o id Template da Plataforma Notifica. Entre em contato com os administradores do sistema!',
            )
        if settings.DEBUG and Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'api_key_notifica_govbr') == '111111':
            cache.set(f'govbr_check_{self.request.user.get_vinculo().id}', '11111', 300)
        if not cache.get(f'govbr_check_{self.request.user.get_vinculo().id}', None) or force:
            self.codigo_verificacao = random_with_N_digits(5)
            try:
                # Obter o api_service
                api_service = None
                api_externa_notifica = APIExterna.NOTIFICA_GOVBR
                if api_externa_notifica.ativo:
                    api_service = api_externa_notifica.get_service()
                else:
                    messages.add_message(
                        self.request,
                        messages.ERROR,
                        'Não é possível enviar a notificação pois a integração com a Plataforma Notifica está desabilitada. Utilize a opção: Enviar Novo Código - E-mail.',
                    )
                    return
                cpf = self.request.user.get_profile().cpf.replace('.', '').replace('-', '')
                sucesso, _resposta = api_service.send_cpf_notification(
                    cpf=cpf,
                    id_template=TEMPLATE_CODIGO_VERIFICADOR_SUAP_APP_GOVBR,
                    parametrosTemplate={
                        'instituicao_sigla': Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'),
                        'codigo_verificacao': self.codigo_verificacao,
                    },
                )
                if sucesso:
                    cache.set(f'govbr_check_{self.request.user.get_vinculo().id}', self.codigo_verificacao, 300)
                    messages.add_message(
                        self.request, messages.SUCCESS, 'Código enviado com sucesso para App Gov.BR. A validade deste código é de 5 minutos!'
                    )
            except Exception:
                messages.add_message(self.request, messages.ERROR, 'Houve um erro ao enviar código de verificação para o aplicativo Gov.BR.')
                messages.add_message(self.request, messages.INFO, 'Utilize a opção: Enviar Novo Código - E-mail.')


class SolicitacaoAssinaturaForm(forms.FormPlus):
    solicitado = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.assinadores(), required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Pessoa'
    )

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        self.solicitado = None
        super().__init__(*args, **kwargs)
        self.solicitacao = self.get_solicitacao_balizadora()

        # Se existe alguma solicitação balizadora, o form será exibido com os dados do servidor solicitado apenas a
        # título de informação. Esse form está sendo usado em conjunto com outro form, que exibe as solicitações de
        # assinatura complementares.

        if self.solicitacao:
            self.solicitado = self.solicitacao.solicitado
            #
            self.fields['solicitado'].widget = forms.TextInput()
            self.fields['solicitado'].initial = str(self.solicitacao.solicitado)
            self.fields['solicitado'].widget.attrs.update(readonly='readonly')
            self.fields['solicitado'].widget.attrs.update(disabled='disabled')
            self.fields['solicitado'].required = False

    def get_solicitacao_balizadora(self):
        if self.documento.possui_assinatura():
            return self.documento.get_solicitacao_balizadora()
        else:
            return SolicitacaoAssinatura.objects.filter(
                ~Q(status=SolicitacaoStatus.STATUS_INDEFERIDA), documento=self.documento, condicionantes__isnull=True
            ).first()

    def get_solicitacao(self):
        return self.solicitado

    def clean_solicitado(self):
        if self['solicitado'].html_name not in self.data:
            self.cleaned_data['solicitado'] = self.solicitado
        return self.cleaned_data['solicitado']


class SolicitacaoAssinaturaEmLoteForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Preencher solicitações'
    SUBMIT_STYLE = 'default'
    metodo_busca = forms.ChoiceField(
        label='Método de busca',
        choices=(('matricula', 'Matrícula'), ('email_academico', 'E-mail Acadêmico')),
        initial='matricula',
        required=True,
        widget=forms.RadioSelect(),
    )
    solicitados = forms.CharField(
        label='Pessoas',
        help_text='Informe os e-mails academicos ou matrículas separados por vírgula, ponto e virgula ou espaço. Se você escolher o método de busca "matrícula", observe que o campo deve conter apenas números.',
        required=False,
        widget=forms.Textarea,
    )


class SolicitacaoAssinaturaFormSet(forms.FormPlus):
    solicitado = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.assinadores(permite_alunos=True, permite_maiores_18=True),
        required=True,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Pessoa',
    )

    ordem = forms.IntegerField(
        required=True, min_value=1, initial=1, help_text='Use um mesmo número de ordem para realizar solicitações simultâneas.'
    )

    class Media:
        js = ('comum/js/jquery.formset.js',)

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        super().__init__(*args, **kwargs)

    def clean_solicitado(self):
        solicitado = self.cleaned_data.get('solicitado', None)
        documento = self.documento
        if solicitado and AssinaturaDocumentoTexto.objects.filter(assinatura__vinculo=solicitado, documento=documento).exists():
            self.add_error('solicitado', f'{solicitado} já assinou o documento.')
        return solicitado


SolicitacaoComplementaresFormSet = formset_factory(SolicitacaoAssinaturaFormSet, can_delete=True)


class SolicitacaoAssinaturaComAnexacaoForm(forms.FormPlus):
    solicitado = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.assinadores(), required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Pessoa'
    )
    if 'processo_eletronico' in settings.INSTALLED_APPS:
        Processo = apps.get_model('processo_eletronico', 'Processo')
        processo_para_anexar = forms.ModelChoiceFieldPlus(
            queryset=Processo.objects, required=True, widget=AutocompleteWidget(), label='Anexar ao Processo'
        )

    # Dados para encaminhar para setor
    TIPO_BUSCA_SETOR_CHOICE = (('sem_despacho', 'Sem despacho'), ('com_despacho', 'Com despacho'))

    tipo_busca_encaminhar = forms.ChoiceField(
        widget=forms.RadioSelect(uncheck=True), required=False, choices=TIPO_BUSCA_SETOR_CHOICE, label='Encaminhar Processo'
    )

    destinatario_uo = forms.ModelChoiceFieldPlus(label=nomenclatura.campus, queryset=UnidadeOrganizacional.objects.suap(), required=False)
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino do Trâmite',
        queryset=Setor.objects.none(),
        required=False,
        widget=AutocompleteWidget(form_filters=[('destinatario_uo', 'uo_id')]),
    )
    vinculo_para_distribuir = forms.ModelChoiceField(
        label='Destinatário',
        queryset=Vinculo.objects.servidores(),
        widget=AutocompleteWidget(),
        required=False,
        help_text='Informe a matrícula, CPF (somente números) ou nome para buscar destinatário.',
    )

    despacho_corpo = forms.CharField(label='Despacho do Trâmite', required=False, widget=forms.Textarea())

    papel = forms.ModelChoiceField(label='Perfil', required=False, queryset=Papel.objects.none())
    senha = forms.PasswordField(required=False)

    class Media:
        js = ('documento_eletronico/js/SolicitarAssinaturaComAnexacao.js',)

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        self.solicitado = None
        super().__init__(*args, **kwargs)
        self.fields['destinatario_setor_autocompletar'].queryset = Setor.objects.suap_ativos()
        self.initial['destinatario_uo'] = get_setor(self.request.user).uo_id
        self.solicitacao = self.get_solicitacao_balizadora()

        # Se existe alguma solicitação balizadora, o form será exibido com os dados do servidor solicitado apenas a
        # título de informação. Esse form está sendo usado em conjunto com outro form, que exibe as solicitações de
        # assinatura complementares.

        if self.solicitacao:
            self.solicitado = self.solicitacao.solicitado
            #
            self.fields['solicitado'].widget = forms.TextInput()
            self.fields['solicitado'].initial = str(self.solicitacao.solicitado)
            self.fields['solicitado'].widget.attrs.update(readonly='readonly')
            self.fields['solicitado'].widget.attrs.update(disabled='disabled')
            self.fields['solicitado'].required = False
        #
        vinculo = self.request.user.get_relacionamento()
        self.fields['papel'].queryset = vinculo.papeis_ativos
        if not Configuracao.get_valor_por_chave('processo_eletronico', 'permite_distribuir_ao_tramitar'):
            del self.fields['vinculo_para_distribuir']

    def clean_vinculo_para_distribuir(self):
        Processo = apps.get_model('processo_eletronico', 'Processo')
        destinatario_setor_autocompletar = self.cleaned_data.get('destinatario_setor_autocompletar')
        vinculo_para_distribuir = self.cleaned_data.get('vinculo_para_distribuir')
        if destinatario_setor_autocompletar and vinculo_para_distribuir:
            if not Processo.setores_que_posso_trabalhar_nos_processos(
                [Processo.PERMISSAO_OPERAR_CRIAR_PROCESSO, Processo.PERMISSAO_OPERAR_PROCESSO], vinculo_para_distribuir.user
            ).filter(pk=destinatario_setor_autocompletar.pk):
                raise ValidationError('O processo só pode ser destinado a servidores habilitados.')
        return vinculo_para_distribuir

    def get_destino(self):
        return self.cleaned_data.get('destinatario_setor_autocompletar', None)

    # Com "Sem despacho" o JS só esconde despacho e perfil: o que foi digitado antes ainda chega no POST. Gravar
    # despacho sem perfil tornava o trâmite automático impossível na hora da assinatura (#17817).
    def clean_despacho_corpo(self) -> str:
        return self.cleaned_data.get('despacho_corpo') if self.is_tipo_busca_com_despacho() else ''

    def clean_papel(self) -> Papel | None:
        return self.cleaned_data.get('papel') if self.is_tipo_busca_com_despacho() else None

    def get_solicitacao_balizadora(self):
        if self.documento.possui_assinatura():
            return self.documento.get_solicitacao_balizadora()
        else:
            return SolicitacaoAssinatura.objects.filter(
                ~Q(status=SolicitacaoStatus.STATUS_INDEFERIDA), documento=self.documento, condicionantes__isnull=True
            ).first()

    def get_solicitacao(self):
        return self.solicitado

    def clean_processo_para_anexar(self):
        processo_anexar = self.cleaned_data.get('processo_para_anexar', None)
        if not processo_anexar:
            msg = 'Nenhum processo foi selecionado. Por favor, indique o processo ao qual o presente documento deve ser anexado.'
            self.add_error('processo_para_anexar', msg)
        #
        if processo_anexar.esta_finalizado():
            self.add_error('processo_para_anexar', f'O processo {processo_anexar} encontra-se finalizado e não pode receber novos documentos.')
        #
        if processo_anexar.tem_solicitacoes_assinatura_com_tramite_pendentes():
            msg = f'O processo {processo_anexar} não pode receber novos anexos pois possui solicitações de assinatura com trâmites pendentes.'
            self.add_error('processo_para_anexar', msg)
        #
        if not processo_anexar.esta_nos_meus_setores(self.request.user):
            self.add_error('processo_para_anexar', 'Não é possível adicionar documentos a um processo que não está em seus setores.')
        return processo_anexar

    def clean_solicitado(self):
        if self['solicitado'].html_name not in self.data:
            self.cleaned_data['solicitado'] = self.solicitado
        return self.cleaned_data['solicitado']

    def clean(self):
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
            if processo_anexar.eh_privado() and self.get_destino():
                self.errors['processo_para_anexar'] = forms.ValidationError(
                    [f'O processo {processo_anexar} não pode tramitar para um setor pois possui nível de acesso privado.']
                )
            if not processo_anexar.esta_nos_meus_setores(self.request.user):
                self.errors['processo_para_anexar'] = forms.ValidationError(
                    ['Não é possível adicionar documentos a um processo que não está em seus setores.']
                )
        if self.is_tipo_busca_com_despacho() and not self.cleaned_data.get('despacho_corpo'):
            self.add_error('despacho_corpo', 'É obrigatório informar o despacho.')
        if self.is_tipo_busca_com_despacho() and not self.cleaned_data.get('papel'):
            self.add_error('papel', 'É obrigatório informar um papel.')
        if self.is_tipo_busca_com_despacho() and not self.cleaned_data.get('senha'):
            self.add_error('senha', 'É obrigatório informar uma senha.')
        return self.cleaned_data

    def is_tipo_busca_sem_despacho(self):
        return self.cleaned_data.get('tipo_busca_encaminhar') == 'sem_despacho'

    def is_tipo_busca_com_despacho(self):
        return self.cleaned_data.get('tipo_busca_encaminhar') == 'com_despacho'


# Obs: Caso precise alterar algo esse SolicitacaoAssinaturaComAnexacaoFormSet, observar
# os templates solicitar_assinatura_com_anexacao.html e solicitacao_form.html.


class SolicitacaoAssinaturaComAnexacaoFormSet(forms.FormPlus):
    solicitado = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.assinadores(permite_alunos=True, permite_maiores_18=True),
        required=True,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Pessoa',
    )
    ordem = forms.IntegerField(
        required=True, min_value=1, initial=1, help_text='Use um mesmo número de ordem para realizar solicitações simultâneas.'
    )

    class Media:
        js = ('comum/js/jquery.formset.js',)

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        super().__init__(*args, **kwargs)

    def clean(self):
        solicitado = self.cleaned_data.get('solicitacao', None)
        documento = self.documento
        if solicitado and AssinaturaDocumentoTexto.objects.filter(assinatura_vinculo=solicitado, documento=documento).exists():
            self.add_error('solicitacao', f'{solicitado} já assinou o documento.')
        return self.cleaned_data


SolicitacaoComplementaresComAnexacaoFormSet = formset_factory(SolicitacaoAssinaturaComAnexacaoFormSet, can_delete=True)


class SolicitacaoRevisaoForm(forms.FormPlus):
    revisor = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects.none(), required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )
    observacao = forms.CharField(label='Observação', widget=forms.Textarea, required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['revisor'].queryset = Vinculo.objects.assinadores()


class RevisarDocumentoForm(forms.FormPlus):
    notas_revisor = forms.CharField(label='Observação', widget=forms.Textarea, required=False)


class AutenticacaoDocumento(forms.FormPlus):
    codigo_verificador = forms.IntegerField(label='Código Verificador')
    codigo_autenticacao = forms.CharField(label='Código de Autenticação', max_length=10)

    def __init__(self, *args, **kwargs):
        codigo_verificador = kwargs.pop('codigo_verificador')
        codigo_autenticacao = kwargs.pop('codigo_autenticacao')
        super().__init__(*args, **kwargs)
        self.fields['codigo_verificador'].initial = codigo_verificador
        self.fields['codigo_autenticacao'].initial = codigo_autenticacao
        if not settings.DEBUG:
            self.fields['recaptcha'] = ReCaptchaField(label='')


class AutenticacaoDocumentoTexto(AutenticacaoDocumento):
    recaptcha = ReCaptchaField(label='')

    def processar(self):
        cleaned_data = self.cleaned_data
        codigo_verificador = cleaned_data.get('codigo_verificador')
        codigo_autenticacao = cleaned_data.get('codigo_autenticacao')
        documento = DocumentoTexto.objects.filter(id=codigo_verificador)
        if not documento:
            documento = DocumentoTextoPessoal.objects.filter(id=codigo_verificador)
        if documento.exists():
            documento = documento.latest('id')
            if documento.codigo_autenticacao == codigo_autenticacao:
                return documento

        return None


class AutenticacaoDocumentoDigitalizado(AutenticacaoDocumento):
    def processar(self):
        cleaned_data = self.cleaned_data
        codigo_verificador = cleaned_data.get('codigo_verificador')
        codigo_autenticacao = cleaned_data.get('codigo_autenticacao')
        documento = DocumentoDigitalizado.objects.filter(id=codigo_verificador)
        if documento.exists():
            documento = documento.latest('id')
            if documento.codigo_autenticacao == codigo_autenticacao:
                return documento

        return None


class RejeitarSolicitacaoAssinaturaForm(forms.ModelFormPlus):
    class Meta:
        model = SolicitacaoAssinatura
        fields = ('justificativa_rejeicao',)

    def save(self, *args, **kwargs):
        self.instance.data_resposta = get_datetime_now()
        self.instance.indeferir_solicitacao()
        return super().save(*args, **kwargs)


class PapelForm(forms.FormPlus):
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none(), required=True)
    SUBMIT_LABEL = 'Assinar'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not hasattr(self, 'request'):
            self.request = tl.get_request()

        vinculo = self.request.user.get_relacionamento()
        self.fields['papel'].queryset = vinculo.papeis_ativos
        if vinculo.papeis_ativos.count() == 1:
            self.fields['papel'].initial = vinculo.papeis_ativos.first().id


class AssinarDocumentoForm(AuthenticationForm, PapelForm):
    SUBMIT_LABEL = 'Assinar Documento'


class AssinarDocumentoGovBRForm(AuthenticationGovBRForm, PapelForm):
    SUBMIT_LABEL = 'Assinar Documento - Gov.BR'


class GeradorIdentificadorDocumentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Definir identificador'
    identificador_tipo_documento_sigla = forms.CharFieldPlus(label='Sigla do Tipo de Documento', max_length=50, required=True)
    identificador_numero = forms.IntegerField(label='Número', required=True)
    identificador_ano = forms.IntegerField(label='Ano', required=True)
    identificador_setor_sigla = forms.CharFieldPlus(label='Sigla do Setor', max_length=100, required=True)

    def __init__(self, *args, **kwargs):
        self.documento_id = kwargs.pop('documento_id')
        documento = DocumentoTexto.objects.get(pk=self.documento_id)

        super().__init__(*args, **kwargs)
        identificador_tipo_documento_sigla, identificador_numero, identificador_ano, identificador_setor_sigla = (
            documento.get_sugestao_identificador_definitivo(
                tipo_documento_texto=documento.modelo.tipo_documento_texto, setor_dono=documento.setor_dono
            )
        )
        #
        self.fields['identificador_tipo_documento_sigla'].initial = identificador_tipo_documento_sigla
        self.fields['identificador_tipo_documento_sigla'].widget.attrs['readonly'] = True
        self.fields['identificador_tipo_documento_sigla'].required = True

        self.fields['identificador_numero'].initial = identificador_numero
        self.fields['identificador_numero'].widget.attrs['readonly'] = True
        self.fields['identificador_numero'].required = True

        if documento.usa_sequencial_anual:
            self.fields['identificador_ano'].initial = identificador_ano
            self.fields['identificador_ano'].widget.attrs['readonly'] = True
            self.fields['identificador_ano'].required = True
        else:
            del self.fields['identificador_ano']

        #
        self.fields['identificador_setor_sigla'].initial = identificador_setor_sigla
        self.fields['identificador_setor_sigla'].widget.attrs['readonly'] = True
        self.fields['identificador_setor_sigla'].required = True

    def clean(self):
        return super().clean()


class VinculoDocumentoTextoForm(forms.ModelFormPlus):
    tipo_vinculo_documento = forms.ModelChoiceField(label='Tipo de Vínculo', queryset=TipoVinculoDocumento.objects, widget=forms.Select)
    documento_texto_alvo = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects,
        label='Documento Alvo',
        required=True,
        help_text='Informa o identificador do documento. Obs: Somente serão listados documentos ASSINADOS ou FINALIZADOS e que você tem acesso.',
    )

    class Meta:
        model = VinculoDocumentoTexto
        fields = ['documento_texto_base', 'tipo_vinculo_documento', 'documento_texto_alvo']

    def __init__(self, request: HttpRequest, documento_texto_base: DocumentoTexto, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # disabled: o Django usa o initial e ignora o documento base que vier no POST; quem pode vincular é checado na view.
        self.fields['documento_texto_base'] = forms.ModelChoiceField(
            queryset=DocumentoTexto.objects.filter(pk=documento_texto_base.pk),
            widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS, readonly=True),
            disabled=True,
        )
        self.fields['documento_texto_base'].initial = documento_texto_base.pk
        vlqs_documentos_ja_vinculados_ao_documento_base = VinculoDocumentoTexto.objects.filter(documento_texto_base=documento_texto_base).values_list(
            'documento_texto_alvo', flat=True
        )

        documentos_passiveis_vinculacao_ids = list(
            chain(
                DocumentoTexto.objects.proprios(request.user).values_list('id', flat=True),
                DocumentoTexto.objects.compartilhados(request.user).values_list('id', flat=True),
            )
        )

        qs_documentos_passiveis_vinculacao = DocumentoTexto.objects.filter(id__in=documentos_passiveis_vinculacao_ids)
        qs_documentos_passiveis_vinculacao = qs_documentos_passiveis_vinculacao.filter(
            status__in=[DocumentoStatus.STATUS_ASSINADO, DocumentoStatus.STATUS_FINALIZADO]
        )
        qs_documentos_passiveis_vinculacao = qs_documentos_passiveis_vinculacao.exclude(pk=documento_texto_base.pk)
        qs_documentos_passiveis_vinculacao = qs_documentos_passiveis_vinculacao.exclude(pk__in=vlqs_documentos_ja_vinculados_ao_documento_base)
        self.fields['documento_texto_alvo'].queryset = qs_documentos_passiveis_vinculacao.only(
            'pk', 'identificador_tipo_documento_sigla', 'identificador_numero', 'identificador_ano', 'identificador_setor_sigla'
        ).order_by('identificador_tipo_documento_sigla', 'identificador_ano', 'identificador_numero')

    def clean(self) -> dict:
        cleaned_data = super().clean()
        tipo_vinculo = cleaned_data.get('tipo_vinculo_documento')
        documento_base = cleaned_data.get('documento_texto_base')
        documento_alvo = cleaned_data.get('documento_texto_alvo')
        if not tipo_vinculo or not documento_base or not documento_alvo or tipo_vinculo.modo_uso == TipoVinculoDocumento.MODO_LIVRE:
            return cleaned_data
        self._configuracao = ConfiguracaoVinculoDocumento.objects.filter(
            tipo_vinculo_documento=tipo_vinculo,
            tipo_documento_base=documento_base.tipo,
            tipo_documento_alvo=documento_alvo.tipo,
        ).first()
        if self._configuracao and not self._configuracao.ativo:
            self.add_error('documento_texto_alvo', 'A configuração deste vínculo para os tipos dos documentos está desativada.')
        return cleaned_data

    def save(self, commit: bool = True) -> VinculoDocumentoTexto:
        self.instance.configuracao = getattr(self, '_configuracao', None)
        return super().save(commit=commit)


class CancelarDocumentoForm(forms.ModelFormPlus):
    justificativa_cancelamento = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())

    class Meta:
        model = DocumentoTexto
        fields = ('justificativa_cancelamento',)

    def save(self, *args, **kwargs):
        with transaction.atomic(), reversion.create_revision():
            self.instance.data_cancelamento = get_datetime_now()
            self.instance.cancelar_documento()
            return super().save(*args, **kwargs)


class RestricaoAssinaturaForm(forms.ModelFormPlus):
    TIPO_PAPEL_CHOICES = [[1, 'Cargo'], [2, 'Função']]
    papel = forms.ChoiceField(label='Papel:', choices=TIPO_PAPEL_CHOICES, required=True, widget=forms.RadioSelect)
    cargo_emprego = forms.ModelChoiceFieldPlus(
        queryset=CargoEmprego.objects, required=False, widget=AutocompleteWidget(search_fields=CargoEmprego.SEARCH_FIELDS)
    )
    funcao = forms.ModelChoiceFieldPlus(queryset=Funcao.objects, required=False, widget=AutocompleteWidget(search_fields=Funcao.SEARCH_FIELDS))

    class Meta:
        model = RestricaoAssinatura
        fields = ('tipo_documento_texto',)

    class Media:
        js = ('/static/documento_eletronico/js/RestricaoAssinaturaForm.js',)

    def clean(self):
        if 'papel' in self.cleaned_data:
            if self.cleaned_data['papel'] == '1' and self.cleaned_data['cargo_emprego'] is None:
                raise forms.ValidationError('Escolha um cargo.')
            elif self.cleaned_data['papel'] == '2' and self.cleaned_data['funcao'] is None:
                raise forms.ValidationError('Escolha uma função.')

        return self.cleaned_data

    def save(self, *args, **kwargs):
        generic_obj = None
        if self.cleaned_data['papel'] == '1':
            generic_obj = self.cleaned_data['cargo_emprego']
        elif self.cleaned_data['papel'] == '2':
            generic_obj = self.cleaned_data['funcao']

        self.instance.papel_content_type = ContentType.objects.get_for_model(generic_obj.__class__)
        self.instance.papel_content_id = generic_obj.id
        self.instance.papel_content_object = generic_obj

        return super().save(*args, **kwargs)


class CompartilhamentoDocumentosPessoaForm(forms.ModelFormPlus):
    documento = forms.ModelChoiceFieldPlus(
        queryset=DocumentoTexto.objects, required=True, widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS)
    )
    vinculo_permitido = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects, required=True, widget=AutocompleteWidget(search_fields=Pessoa.SEARCH_FIELDS)
    )

    class Meta:
        model = CompartilhamentoDocumentoPessoa
        fields = ('documento', 'vinculo_permitido', 'nivel_permissao')


class CompartilhamentoDocumentosSetorPessoaForm(forms.ModelFormPlus):
    setor_dono = forms.ModelChoiceFieldPlus(
        queryset=Setor.objects.suap_ativos(), required=True, widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS)
    )
    vinculo_permitido = forms.ModelChoiceFieldPlus(
        queryset=Vinculo.objects, required=True, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )

    class Meta:
        model = CompartilhamentoSetorPessoa
        fields = ('setor_dono', 'vinculo_permitido', 'nivel_permissao')


class SolicitarCompartilhamentoDocumentoDigitalizadoForm(forms.ModelFormPlus):
    solicitante = forms.ModelChoiceFieldPlus(
        Vinculo.objects, label='Solicitante', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS, readonly=True)
    )
    documento = forms.ModelChoiceFieldPlus(
        DocumentoDigitalizado.objects,
        label='Documento Sigiloso',
        widget=AutocompleteWidget(search_fields=DocumentoDigitalizado.SEARCH_FIELDS, readonly=True),
    )

    class Meta:
        model = SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa
        fields = ('solicitante', 'documento', 'justificativa_solicitacao')

    def __init__(self, *args, **kwargs):
        documento = kwargs.pop('documento')
        self.processo = kwargs.pop('processo')
        solicitante = kwargs.pop('solicitante')
        super().__init__(*args, **kwargs)

        self.fields['solicitante'].initial = solicitante
        self.fields['solicitante'].widget.attrs.update(readonly='readonly')
        self.fields['solicitante'].widget.attrs.update(disabled='disabled')

        self.fields['documento'].initial = documento
        self.fields['documento'].widget.attrs.update(readonly='readonly')
        self.fields['documento'].widget.attrs.update(disabled='disabled')

    def get_texto_solicitacao(self):
        texto = """<h1>Solicitação de Acesso de Visualização</h1>
        <h2>[SUAP] Solicitação de Visualização do Documento {0} </h2>
        <dl>
            <dt>Processo:</dt><dd>{5}</dd>
            <dt>Data:</dt><dd>{1}</dd>
            <dt>Solicitante:</dt><dd>{2}</dd>
            <dt>Motivação:</dt><dd>{3}</dd>
        </dl>
        <p class="more-info">Para mais informações, acesse:
            <a href="{4}">{5}</a>
        </p>
        """.format(
            self.instance.documento,
            self.instance.data_criacao.strftime('%d/%m/%Y %H:%M'),
            self.instance.solicitante,
            self.instance.justificativa_solicitacao,
            self.processo.get_absolute_url(),
            self.processo,
        )
        return texto

    def enviar_email(self):
        texto = self.get_texto_solicitacao()
        destino = [self.instance.documento.dono_documento] if self.instance.documento.dono_documento else []
        if destino:
            self.instance.enviar_mail(texto, destino)

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        self.enviar_email()


class AvaliarSolicitacaoCompartilhamentoDocumentoDigitalizadoForm(forms.ModelFormPlus):
    STATUS_DEFERIDA = 1
    STATUS_INDEFERIDA = 2

    STATUS_CHOICES = ((STATUS_DEFERIDA, 'Deferida'), (STATUS_INDEFERIDA, 'Indeferida'))
    status_solicitacao = forms.ChoiceField(choices=STATUS_CHOICES, label='Situação da Solicitação', required=True)

    class Meta:
        model = SolicitacaoCompartilhamentoDocumentoDigitalizadoPessoa
        fields = ('status_solicitacao', 'justificativa_autorizacao')

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop('processo')
        self.documento_removido = kwargs.pop('documento_removido')
        self.documento_eh_privado = kwargs.pop('documento_eh_privado')
        super().__init__(*args, **kwargs)
        if self.documento_removido or not self.documento_eh_privado:
            self.fields['status_solicitacao'].choices = ((self.STATUS_INDEFERIDA, 'Indeferida'),)
            if self.documento_removido:
                help_text = f'A solicitação não pode ser deferida pois o documento foi removido do processo {self.processo.numero_protocolo_fisico}.'
            else:
                help_text = 'A solicitação não pode ser deferida pois o documento não é privado no momento.'
            #
            self.fields['status_solicitacao'].help_text = help_text

    def get_texto_solicitacao(self):
        texto = """<h1>Solicitação de Acesso de Visualização</h1>
        <h2>[SUAP] Solicitação de Visualização do Documento {0}</h2>
        <dl>
            <dt>Data:</dt><dd>{1}</dd>
            <dt>Solicitante:</dt><dd>{2}</dd>
            <dt>Motivação:</dt><dd>{3}</dd>
            <dt>Processo:</dt><dd>{4}</dd>
            <dt>Status:</dt><dd>{5}</dd>
            <dt>Justificativa (Des)Autorização:</dt><dd>{6}</dd>
        </dl>
        <p class="more-info">Para mais informações, acesse:
            <a href="{7}>{4}</a>
        </p>
        """.format(
            self.instance.documento,
            self.instance.data_criacao.strftime('%d/%m/%Y %H:%M'),
            self.instance.solicitante,
            self.instance.justificativa_solicitacao,
            self.processo,
            self.instance.status_solicitacao,
            self.instance.justificativa_autorizacao,
            self.processo.get_absolute_url(),
        )
        return texto

    def enviar_email(self):
        texto = self.get_texto_solicitacao()
        destino = [self.instance.solicitante]
        self.instance.enviar_mail(texto, destino)

    @transaction.atomic()
    def save(self, commit=True):
        if not self.instance.id:
            self.instance.data_autorizacao = datetime.now()
            self.instance.usuario_autorizacao = self.request.user
        solicitacao = super().save(commit)
        if solicitacao.deferida():
            compartilhamento = CompartilhamentoDocumentoDigitalizadoPessoa()
            compartilhamento.documento = solicitacao.documento
            compartilhamento.vinculo_permitido = solicitacao.solicitante
            compartilhamento.data_criacao = datetime.now()
            compartilhamento.usuario_criacao = solicitacao.usuario_autorizacao
            compartilhamento.save()
        # Se não estivesse
        if not solicitacao.pendente():
            self.enviar_email()
        return solicitacao


class DocumentoTextoFormEditarInteressados(forms.FormPlus):
    documento = forms.CharFieldPlus()
    interessados = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects.all(), label='Interessados', required=True)
    observacao_alteracao_interessados = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento')
        super().__init__(*args, **kwargs)
        self.fields['documento'].initial = self.documento
        self.fields['documento'].widget.attrs['readonly'] = True
        self.fields['interessados'].initial = self.documento.interessados.all().values_list('pk', flat=True)


class DocumentoTextoPessoalForm(forms.ModelFormPlus):
    tipo = forms.ModelChoiceField(TipoDocumentoTexto.ativos_pessoais, label='Tipo do Documento', required=True)
    modelo = forms.ModelChoiceField(ModeloDocumento.ativos.all(), label='Modelo', required=True)
    assunto = forms.CharField(widget=TextareaCounterWidget(max_length=255), label='Assunto')
    classificacao = forms.ModelMultiplePopupChoiceField(Classificacao.objects, label='Classificações', required=False, disabled=True)

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )

    class Meta:
        model = DocumentoTextoPessoal
        fields = ('tipo', 'modelo', 'nivel_acesso', 'hipotese_legal', 'assunto')

    class Media:
        js = ['/static/documento_eletronico/js/DocumentoTextoForm.js']

    def clean_nivel_acesso(self):
        nivel_acesso = self.cleaned_data.get('nivel_acesso')
        if self.instance.id:
            old_version = DocumentoTextoPessoal.objects.get(id=self.instance.id)
            self.instance.nivel_acesso = nivel_acesso
            if self.instance.nivel_acesso != old_version.nivel_acesso:
                self.instance.validar_auteracao_nivel_acesso(self.request.user)
        return nivel_acesso

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        edit_mode = bool(self.instance.pk)

        if edit_mode:
            self.fields['tipo'].initial = self.instance.modelo.tipo_documento_texto
            self.fields['tipo'].widget = forms.widgets.HiddenInput()
            self.fields['tipo'].required = False
            self.fields['tipo'].help_text = 'O tipo de documento não pode ser alterado'

        if 'processo_eletronico' in settings.INSTALLED_APPS:
            ConfiguracaoInstrucaoNivelAcesso = apps.get_model('processo_eletronico', 'ConfiguracaoInstrucaoNivelAcesso')
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

    @transaction.atomic()
    def save(self, commit=True):
        if not self.instance.id:
            self.instance.data_criacao = datetime.now()
            self.instance.usuario_criacao = self.request.user
        self.instance.data_ultima_modificacao = datetime.now()
        self.instance.usuario_ultima_modificacao = self.request.user

        # Cria papel (quando ele ainda não existe)
        # - para que alunos possam criar documentos pessoais
        # - para que alunos possam executar as outras operações relacionadas ao documento pessoal
        if self.request.user.get_vinculo().eh_aluno():
            aluno = self.request.user.get_relacionamento()
            aluno.criar_papel_discente()

        return super().save(commit)


class DocumentoPessoalDigitalizadoForm(forms.ModelFormPlus):
    assunto = forms.CharFieldPlus(label='Assunto')

    tipo_conferencia = forms.ModelChoiceField(label='Tipo de Conferência', queryset=TipoConferencia.objects, widget=forms.Select)
    tipo = forms.ModelPopupChoiceField(TipoDocumento.ativos_pessoais, label='Tipo', required=True)

    papel = forms.ModelChoiceField(label='Perfil', required=True, queryset=Papel.objects.none())
    senha = forms.PasswordField()

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos',
    )

    class Meta:
        model = DocumentoDigitalizadoPessoal
        exclude = ()

    class Media:
        js = ('/static/processo_eletronico/js/DocumentoUploadEditarForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if not self.instance.pk:
            self.max_file_upload_size = settings.PROCESSO_ELETRONICO_DOCUMENTO_EXTERNO_MAX_UPLOAD_SIZE

            user = self.request.user if self.request else tl.get_user()
            self.tamanho_maximo_upload_personalizado = Configuracao.get_valor_por_chave(
                app='processo_eletronico', chave='tamanho_maximo_upload_personalizado'
            )
            self.pessoas_permitidas_upload_personalizado = Configuracao.get_valor_por_chave(
                app='processo_eletronico', chave='pessoas_permitidas_realizar_upload_personalizado'
            )
            pessoa_permitida_upload_personalizado = self.pessoas_permitidas_upload_personalizado and str(
                user.get_profile().id
            ) in self.pessoas_permitidas_upload_personalizado.split(',')

            self.fields['arquivo'].max_file_size = (
                pessoa_permitida_upload_personalizado and settings.DATA_UPLOAD_MAX_MEMORY_SIZE or self.max_file_upload_size
            )

            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'].queryset = vinculo.papeis_ativos
            if vinculo.papeis_ativos.count() == 1:
                self.fields['papel'].initial = vinculo.papeis_ativos.first().id
        else:
            del self.fields['papel']
            del self.fields['senha']
            del self.fields['tipo_conferencia']

        if 'processo_eletronico' in settings.INSTALLED_APPS:
            ConfiguracaoInstrucaoNivelAcesso = apps.get_model('processo_eletronico', 'ConfiguracaoInstrucaoNivelAcesso')
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


class DocumentoAlterarNivelAcessoForm(forms.FormPlus):
    # Utilizado pelo alterar nivel de acesso DocumentoTexto e DocumentoDigitalizado
    # Utilizado pelo solicitar alterar nivel de acesso DocumentoTexto e DocumentoDigitalizado

    nivel_acesso_atual = ReadOnlyField(label='De')
    nivel_acesso = forms.ChoiceField(required=True, label='Para')
    hipotese_legal = forms.ModelChoiceField(HipoteseLegal.objects.all(), label='Hipótese Legal', required=False)
    senha = forms.PasswordField()

    instrucoes_gerais = forms.CharFieldPlus(
        label='', max_length=100000, required=False, widget=forms.Textarea(attrs={'readonly': 'readonly', 'rows': '30', 'cols': '80'})
    )

    ciencia_instrucoes_gerais = forms.BooleanField(widget=forms.CheckboxInput, required=True, label='Estou ciente sobre as instruções gerais.')

    justificativa = forms.CharFieldPlus(label='Justificativa', max_length=400, required=False, widget=forms.Textarea())

    vinculos_compartilhados = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Compartilhamentos com Pessoas', required=False)

    fieldsets = (
        (
            'Atual Nível de Acesso',
            {'fields': ('nivel_acesso_atual',)},
        ),
        (
            'Novo Nível de Acesso',
            {'fields': ('instrucoes_gerais', 'ciencia_instrucoes_gerais', 'nivel_acesso', 'hipotese_legal', 'justificativa')},
        ),
        ('Autenticação', {'fields': ('senha',)}),
    )

    class Media:
        js = ['/static/documento_eletronico/js/DocumentoAlteraNivelAcessoForm.js']

    def __init__(self, *args, **kwargs):
        self.documento = kwargs.pop('documento', None)
        self.estah_solicitando = kwargs.pop('estah_solicitando', None)
        self.solicitacao = kwargs.pop('solicitacao', None)
        #
        super().__init__(*args, **kwargs)

        if self.estah_solicitando or self.documento.eh_documento_texto:
            if 'vinculos_compartilhados' in self.fields:
                del self.fields['vinculos_compartilhados']

        # Níveis de acesso - DE (Atual)
        de = NivelAcesso.choices()[self.documento.nivel_acesso - 1][1]
        self.fields['nivel_acesso_atual'].widget.display_value = de
        self.fields['nivel_acesso_atual'].initial = self.documento.nivel_acesso

        # Níveis de acesso - PARA (Novo)
        niveis_acesso_alteracao = list(Documento.NIVEL_ACESSO_CHOICES)
        del niveis_acesso_alteracao[self.documento.nivel_acesso - 1]
        self.fields['nivel_acesso'].choices = niveis_acesso_alteracao
        self.fields['nivel_acesso'].initial = 0
        if self.solicitacao:
            self.fields['nivel_acesso'] = ReadOnlyField(label='Para')
            self.fields['nivel_acesso'].widget.display_value = self.solicitacao.get_para_nivel_acesso()[1]
            self.fields['nivel_acesso'].initial = self.solicitacao.get_para_nivel_acesso()[0]
            #
            self.Media.js = None

            if 'processo_eletronico' in settings.INSTALLED_APPS:
                SolicitacaoAlteracaoNivelAcesso = apps.get_model('processo_eletronico', 'SolicitacaoAlteracaoNivelAcesso')
            hipoteses = SolicitacaoAlteracaoNivelAcesso.get_hipoteses_legais_by_processo_documento_nivel_acesso(
                2, self.solicitacao.get_para_nivel_acesso()[0]
            )
            if hipoteses:
                self.fields['hipotese_legal'].queryset = hipoteses
            else:
                self.fields['hipotese_legal'].queryset = HipoteseLegal.objects.none()
            #
            if self.solicitacao.hipotese_legal:
                self.fields['hipotese_legal'].initial = self.solicitacao.hipotese_legal.id

        # Instrucoes
        if 'processo_eletronico' in settings.INSTALLED_APPS:
            ConfiguracaoInstrucaoNivelAcesso = apps.get_model('processo_eletronico', 'ConfiguracaoInstrucaoNivelAcesso')
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

    def clean_nivel_acesso(self):
        niveis_acesso_alteracao = list(Documento.NIVEL_ACESSO_CHOICES)
        del niveis_acesso_alteracao[int(self.cleaned_data.get('nivel_acesso_atual')) - 1]
        diferente = int(self.cleaned_data.get('nivel_acesso_atual')) != int(self.cleaned_data.get('nivel_acesso'))
        nivel_acesso_valido = int(self.cleaned_data.get('nivel_acesso')) in (
            Documento.NIVEL_ACESSO_RESTRITO,
            Documento.NIVEL_ACESSO_SIGILOSO,
            Documento.NIVEL_ACESSO_PUBLICO,
        )
        if not (diferente and nivel_acesso_valido):
            raise forms.ValidationError('Nível de acesso inválido.')
        return self.cleaned_data.get('nivel_acesso')

    def clean_vinculos_compartilhados(self):
        vinculos_compartilhados = self.cleaned_data.get('vinculos_compartilhados')
        nivel_acesso = self.cleaned_data.get('nivel_acesso')
        if vinculos_compartilhados and not int(nivel_acesso) == Documento.NIVEL_ACESSO_SIGILOSO:
            raise forms.ValidationError('Só é permitido o compartilhamento com pessoas quando o nível de acessso solicitado for sigiloso.')
        return vinculos_compartilhados

    def clean(self):
        if (
            self.cleaned_data.get('nivel_acesso')
            and int(self.cleaned_data.get('nivel_acesso')) in (Documento.NIVEL_ACESSO_RESTRITO, Documento.NIVEL_ACESSO_SIGILOSO)
            and not self.cleaned_data.get('hipotese_legal')
        ):
            raise forms.ValidationError('Selecione uma hipótese legal.')


class DocumentoDigitalizadoAnexoSimplesForm(forms.ModelFormPlus):
    papel = forms.ModelChoiceField(label='Perfil', required=True, queryset=Papel.objects.none())
    senha = forms.PasswordField(required=True)
    hipotese_legal = forms.ModelChoiceField(
        HipoteseLegal.objects.all(),
        label='Hipótese Legal',
        required=False,
        help_text='A hipótese legal só é obrigatória para documentos sigilosos ou restritos.',
    )
    fieldsets = ((None, {'fields': ('tipo', 'tipo_conferencia', 'assunto', 'arquivo', 'nivel_acesso', 'hipotese_legal', 'papel', 'senha')}),)

    class Meta:
        model = DocumentoDigitalizadoAnexoSimples
        fields = ('tipo', 'tipo_conferencia', 'assunto', 'arquivo', 'nivel_acesso', 'hipotese_legal')

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        instance = kwargs.get('instance')
        if instance:
            self.fields.pop('arquivo', None)
            self.fields.pop('senha', None)
            self.fields.pop('papel', None)
        else:
            vinculo = self.request.user.get_relacionamento()
            self.fields['papel'].queryset = vinculo.papeis_ativos
            if vinculo.papeis_ativos.count() == 1:
                self.fields['papel'].initial = vinculo.papeis_ativos.first().id
            documento_id = self.request.GET.get('documento_id')
            documento = DocumentoTexto.objects.filter(pk=documento_id).first()
            if documento:
                self.fields['nivel_acesso'].initial = documento.nivel_acesso
                self.fields['hipotese_legal'].initial = documento.hipotese_legal

    def clean_arquivo(self) -> object:
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content

    def clean(self) -> dict:
        cleaned_data = super().clean()
        nivel_acesso = cleaned_data.get('nivel_acesso')
        if nivel_acesso in (Documento.NIVEL_ACESSO_RESTRITO, Documento.NIVEL_ACESSO_SIGILOSO) and not cleaned_data.get('hipotese_legal'):
            raise forms.ValidationError('Selecione uma hipótese legal.')
        return cleaned_data


def ConsultaPublicaDocumentoFormClass(recaptcha_required=True):
    class ConsultaPublicaDocumentoForm(forms.FormPlus):
        SUBMIT_LABEL = 'Buscar'
        METHOD = 'GET'
        assunto = forms.CharFieldPlus(label='Identificador/Assunto', required=False)
        tipo_documento = forms.ModelChoiceField(
            queryset=TipoDocumento.objects,
            label='Tipo',
            widget=AutocompleteWidget(search_fields=TipoDocumento.SEARCH_FIELDS),
            required=False,
        )
        setor = forms.ModelChoiceField(
            queryset=Setor.objects.none(), label='Setor', widget=AutocompleteWidget(search_fields=Setor.SEARCH_FIELDS), required=False
        )

        recaptcha = ReCaptchaField(label='')
        fieldsets = (
            (
                '',
                {'fields': (('assunto', 'tipo_documento', 'setor'),)},
            ),
            ('', {'fields': ('recaptcha',)}),
        )

        def __init__(self, *args, **kwargs):
            tipos_documento = kwargs.pop('tipos_documentos')
            super().__init__(*args, **kwargs)
            self.fields['tipo_documento'].queryset = tipos_documento
            self.fields['setor'].queryset = Setor.objects.suap_ativos().filter(
                pk__in=DocumentoTexto.objects.filter(modelo__tipo_documento_texto__in=tipos_documento).values_list('setor_dono__id', flat=True)
            )
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
            assunto = self.cleaned_data.get('assunto')
            setor = self.cleaned_data.get('setor')
            tipo_documento = self.cleaned_data.get('tipo_documento')
            if not self.errors and not any([assunto, tipo_documento, setor]):
                raise ValidationError('Você deve informar, no mínimo, um dos campos: identificador/assunto, tipo ou setor do documento.')

    return ConsultaPublicaDocumentoForm
