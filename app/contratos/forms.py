from datetime import date, datetime, timedelta
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.core.exceptions import ValidationError
from django.db.models import Count
from django.forms.formsets import formset_factory
from django.forms.models import BaseInlineFormSet, inlineformset_factory
from django.forms.utils import ErrorList
from django.utils.safestring import mark_safe

from almoxarifado.models import Empenho
from comum.models import Ano, APIExterna, Configuracao, PrestadorServico, Vinculo
from contratos.models import (
    CONTINUIDADE_CHOICES,
    CONTINUIDADE_INDETERMINADO,
    IMR,
    NATUREZA_CHOICES,
    Aditivo,
    Agenda,
    AnexoContrato,
    AnexoMaoDeObra,
    Apostilamento,
    ArrecadacaoReceita,
    BaseLegal,
    ContaContrato,
    ContaVinculadaCalculo,
    Contrato,
    ContratoTipoDocumentoComprobatorio,
    Cronograma,
    DocumentoEmpenhoContrato,
    DocumentoEmpenhoContratoMedicao,
    Fiscal,
    Garantia,
    ItemContrato,
    MaoDeObra,
    Medicao,
    MedicaoTipoDocumentoComprobatorio,
    MotivoConclusaoContrato,
    MovimentacaoContaContrato,
    Ocorrencia,
    OcorrenciaMaoDeObra,
    Parcela,
    Penalidade,
    PublicacaoAditivo,
    SubtipoContrato,
    TipoContrato,
    TipoDocumentoComprobatorio,
    TipoFiscal,
    TipoLicitacao,
    TipoPublicacao,
    VerbaSalarialMaoDeObra,
)
from djtools import forms
from djtools.choices import Anos, Meses
from djtools.forms import MultiFileField
from djtools.forms.widgets import (
    AutocompleteWidget,
    BrDinheiroWidget,
    FilteredSelectMultiplePlus,
)
from djtools.templatetags.filters import format_money, in_group
from djtools.utils import date_to_string, full_check_file
from djtools.utils.masks import mask_money
from documento_eletronico.models import DocumentoTexto, NivelPermissao, TipoDocumento
from protocolo.models import Processo
from rh.models import Servidor, Setor, UnidadeOrganizacional
from suap import nomenclatura, settings
from tesouro_gerencial.models import DocumentoEmpenho


def _get_conf_or_default(key, default):
    return ContaVinculadaCalculo.obter_valor_decimal_configuracao(key, default)


class ContratoForm(forms.ModelFormPlus):
    SIM_NAO_CHOICES = ((None, '---'), (True, 'Sim'), (False, 'Não'))
    tipo = forms.ModelChoiceField(TipoContrato.objects, required=True)
    subtipo = forms.ChainedModelChoiceField(
        SubtipoContrato.objects,
        label='Subtipo',
        empty_label='Selecione um Tipo',
        obj_label='descricao',
        form_filters=[('tipo', 'tipo__id')],
        required=True,
        url=None,
    )
    data_inicio = forms.DateFieldPlus(label='Data de Início')
    data_fim = forms.DateFieldPlus(label='Data de Término', required=False)
    valor = forms.DecimalFieldPlus('Valor', required=True)
    processo = forms.ModelChoiceField(queryset=Processo.objects, widget=AutocompleteWidget(), label='Processo', required=True)

    empenho = forms.ModelChoiceField(
        queryset=Empenho.objects, widget=AutocompleteWidget(search_fields=Empenho.SEARCH_FIELDS), label='Empenho', required=False
    )
    campi = forms.ModelMultipleChoiceField(
        queryset=UnidadeOrganizacional.objects.suap(), widget=FilteredSelectMultiplePlus('', True), label=f'{nomenclatura.campi} Atendidos'
    )
    vinculo_contratado = forms.ModelChoiceField(
        queryset=Vinculo.objects,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Contratada',
        required=True,
        help_text='Busque por Nome, CPF ou CNPJ.',
    )
    tipo_licitacao = forms.ModelChoiceField(label='Tipo de Licitação', queryset=TipoLicitacao.objects, widget=forms.Select, required=True)
    pregao = forms.RegexField(
        label='Licitação/Ano/UASG da Licitação',
        regex=r'^\d{5}/\d{4} \(\d{6}\)$',
        required=True,
        help_text="""Formato: XXXXX/YYYY (AAAAAA). Onde:
                              XXXXX é um campo de cinco dígitos pra informar o número da licitação;
                              YYYY é o ano daquela licitação;
                              AAAAAA é um campo de 6 dígitos para a UASG da licitação.""",
    )
    data_conclusao = forms.DateFieldPlus(label='Data de Conclusão', required=False)
    documento_digital_contrato = forms.ModelChoiceField(
        label='Documento Digital do Contrato',
        queryset=DocumentoTexto.objects.none(),
        widget=AutocompleteWidget(search_fields=DocumentoTexto.SEARCH_FIELDS),
        required=False,
    )
    base_legal = forms.ModelChoiceField(queryset=BaseLegal.objects.all(), label='Base Legal', required=True)

    continuidade = forms.ChoiceField(label='Continuidade', choices=CONTINUIDADE_CHOICES, required=True)
    natureza = forms.ChoiceField(label='Natureza', choices=[[None, '---'], *NATUREZA_CHOICES], required=True)
    mao_obra_exclusiva = forms.ChoiceField(label='Possui dedicação de mão de obra exclusiva?', choices=SIM_NAO_CHOICES, required=True)

    grau_risco = forms.ChoiceField(
        label='Grau de risco (1/2/3)',
        required=False,
        choices=((None, 'Nenhum'), (1, 'Grau 1'), (2, 'Grau 2'), (3, 'Grau 3')),
        help_text='Informe o grau de risco da empresa quando houver dedicação exclusiva de mão de obra.',
    )

    setores_gerenciadores = forms.MultipleModelChoiceField(
        Setor.objects,
        label='Setores Gerenciadores',
        required=False,
        help_text='Informe os setores cujos servidores com perfil de operador/gestor de contratos poderão gerenciar esse contrato.',
        widget=AutocompleteWidget(
            search_fields=Setor.SEARCH_FIELDS,
            multiple=True,
            form_filters=[('campus_gerenciador', 'uo')],
        ),
    )

    class Meta:
        model = Contrato
        exclude = ('ordem', 'arquivo', 'cancelado', 'motivo_cancelamento', 'dh_cancelamento', 'usuario_cancelamento', 'numero_processo')

    class Media:
        js = ('/static/contratos/js/ContratoForm.js',)

    def __init__(self, *args, **kwargs):
        uo = None
        is_visualizador_sistemico = (
            self.request.user.is_superuser
            or self.request.user.has_group_cached('Auditor')
            or self.request.user.has_group_cached('Supervisor de Contratos')
        )
        restringir_por_unidade = Configuracao.get_valor_por_chave('contratos', 'restringir_por_unidade')
        if restringir_por_unidade and not is_visualizador_sistemico:
            uo = self.request.user.get_vinculo().setor.uo
        if uo:
            initial = kwargs.get('initial', {})
            initial['campi'] = [uo.pk]
            initial['campus_gerenciador'] = uo.pk
            kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        self.fields['vinculo_contratado'].queryset = Vinculo.objects.filter(
            tipo_relacionamento__app_label__in=['rh', 'comum'], tipo_relacionamento__model__in=['pessoajuridica', 'pessoaexterna', 'prestadorservico']
        )
        if self.instance.pk and self.instance.arrecadacao_receitas.exists():
            self.fields['natureza'].disabled = True

        if 'documento_eletronico' in settings.INSTALLED_APPS:
            user = self.request.user
            tipo_documento_contrato = Configuracao.get_valor_por_chave('contratos', 'tipo_documento_contrato')
            if tipo_documento_contrato and user:
                tipo_documento_contrato = tipo_documento_contrato.split(',')
                # TODO: Os documentos aqui exibidos não deveriam ser todos aqueles FINALIZADOS, PUBLICOS e do TIPO esperado pelo módulo de contratos?
                qs_documentostexto_contratos = (
                    DocumentoTexto.objects.compartilhados(user, NivelPermissao.LER) | DocumentoTexto.objects.proprios(user)
                ).filter(modelo__tipo_documento_texto__pk__in=tipo_documento_contrato)
                self.fields['documento_digital_contrato'].queryset = qs_documentostexto_contratos

            # TODO: Conversar com Inácio para ver se isso é necessário uma vez que existe a configuração que aponta para
            # o tipo de contrato "Contrato".
            if self.instance.pk and self.instance.documentos_texto_tipo_contato_relacionados().exists():
                self.fields['documento_digital_contrato'].initial = self.instance.documentos_texto_tipo_contato_relacionados().first()

        if uo:
            for key in ('campus_gerenciador', 'campi'):
                self.fields[key].queryset = self.fields[key].queryset.filter(pk=uo.pk)
            self.fields['setores_gerenciadores'].required = True

    def clean_numero(self):
        numero = self.cleaned_data.get('numero')
        campus_gerenciador = self['campus_gerenciador'].value()
        habilitar_numeracao_por_campi_gerenciador = Configuracao.get_valor_por_chave('contratos', 'habilitar_numeracao_por_campi_gerenciador')

        if not habilitar_numeracao_por_campi_gerenciador:
            # Verifique se existe algum contrato com o número fornecido, excluindo o contrato atual
            if Contrato.objects.ativos().filter(numero=numero).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(f'Já existe um contrato ativo registrado com número {numero}')
        else:
            if Contrato.objects.ativos().filter(numero=numero, campus_gerenciador=campus_gerenciador).exclude(pk=self.instance.pk).exists():
                raise forms.ValidationError(f'Já existe um contrato ativo registrado com número {numero} no campus gerenciador')

        return numero

    def clean_permite_medicao_sem_empenho(self):
        if self.cleaned_data.get('permite_medicao_sem_empenho') is True and self.cleaned_data.get('possui_arrecadacao_receita') is False:
            raise forms.ValidationError('Só é possível permitir medição sem empenho vinculado para contratos que possuem arrecadação de receita.')
        return self.cleaned_data.get('permite_medicao_sem_empenho')

    def clean_data_conclusao(self):
        cleaned_data = self.cleaned_data
        data_inicio = cleaned_data.get('data_inicio')
        data_conclusao = cleaned_data.get('data_conclusao')
        concluido = cleaned_data.get('concluido')

        # Se está marcado como concluído deve ser informado data_conclusao
        if concluido:
            if not data_conclusao:
                self.fields['data_conclusao'].initial = datetime.today()
                raise forms.ValidationError('A data de conclusão é obrigatória, pois o contrato foi marcado como concluído.')

            # Verifica se data conclusão é válida
            if data_inicio and data_conclusao < data_inicio:
                raise forms.ValidationError(
                    f'A data de conclusão não pode ser menor que data de início do contrato ({data_inicio.strftime("%d/%m/%Y")}).'
                )

        return data_conclusao

    def clean_data_fim(self):
        cleaned_data = self.cleaned_data
        data_fim = cleaned_data.get('data_fim')
        data_inicio = cleaned_data.get('data_inicio')

        # verifica se data final é válida
        if data_fim and data_inicio and data_fim < data_inicio:
            raise forms.ValidationError('Data final não pode ser menor que data inicial.')

        return data_fim

    def clean(self):
        cleaned_data = self.cleaned_data
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        base_legal = cleaned_data.get('base_legal')
        continuidade = cleaned_data.get('continuidade')

        if not self.errors:
            if data_fim and data_inicio > data_fim:
                self._errors['data_fim'] = ['Data final anterior a data inicial']

        if cleaned_data.get('tipo') == 'Despesa':  # TODO
            if not cleaned_data.get('empenho'):
                self.add_error('empenho', 'Se o tipo de contrato for despesa, o empenho é obrigatório.')
        if cleaned_data.get('tipo') == 'Receita':  # TODO
            if not cleaned_data.get('processo'):
                self.add_error('processo', 'Se o tipo de contrato for receita, o processo é obrigatório.')
        if not cleaned_data.get('concluido') and cleaned_data.get('motivo_conclusao'):
            self.add_error('concluido', 'Você deve marcar o campo Concluído pois informou um Motivo para Conclusão.')
        if cleaned_data.get('concluido') and not cleaned_data.get('motivo_conclusao'):
            self.add_error('motivo_conclusao', 'Você deve informar um Motivo para Conclusão pois marcou o campo Concluído.')

        # A data fim não pode passar de 5 anos da data de inicio, caso não tenha base legal. Caso tenha,
        # deverá calcular a data maxima considerando a prorrogacao da base lega.

        # Normaliza `grau_risco`: converte '' para None e strings numéricas para int
        grau_val = cleaned_data.get('grau_risco')
        if grau_val == '':
            cleaned_data['grau_risco'] = None
        elif isinstance(grau_val, str) and grau_val.isdigit():
            cleaned_data['grau_risco'] = int(grau_val)

        # Validação: se marcar dedicação exclusiva de mão de obra, exigir grau de risco (1/2/3).
        # A opção 'Nenhum' (None) é permitida quando não há dedicação exclusiva.
        if cleaned_data.get('mao_obra_exclusiva') == 'True':
            grau = cleaned_data.get('grau_risco')
            if grau not in (1, 2, 3):
                self.add_error('grau_risco', 'Grau de risco é obrigatório quando o contrato possui dedicação exclusiva de mão de obra.')
        if (
            data_fim
            and data_inicio
            and base_legal
            and base_legal.tempo_maximo_prorrogacao > 0
            and data_fim > (data_inicio + relativedelta(years=(base_legal.tempo_maximo_prorrogacao // 12)))
        ):
            self.add_error('data_fim', f'A data final não pode ser maior que o previsto na Base Legal ({base_legal}).')
        elif data_fim and data_inicio and data_fim - data_inicio > timedelta(5 * 365) and not base_legal:
            self.add_error(
                'data_fim',
                f'A data final não pode ser maior do que {date_to_string(data_inicio + timedelta(5 * 365))} (5 anos a mais que a data inicial).',
            )

        # TODO: Testar isso com um contrato novo, feito do zero.
        tem_arquivo_upload = cleaned_data.get('arquivo_contrato') is not None
        tem_documento_digitalizado = cleaned_data.get('documento_digital_contrato') is not None
        if not self.instance.pk and not tem_arquivo_upload and not tem_documento_digitalizado:
            self.add_error(
                'documento_digital_contrato', 'Você deve selecionar o Documento Digital do Contrato ou adicionar o Arquivo do Contrato (upload).'
            )

        if data_fim and continuidade == CONTINUIDADE_INDETERMINADO:
            self.add_error('data_fim', 'Contratos com Continuidade "Indeterminado" não devem possuir Data final.')

        return cleaned_data


class ContratoCancelarForm(forms.FormPlus):
    motivo_cancelamento = forms.CharField(widget=forms.Textarea, required=True, label='Motivo do Cancelamento')


class MaoDeObraForm(forms.ModelFormPlus):
    data_nascimento = forms.DateFieldPlus(label='Data de Nascimento')
    desligamento = forms.DateFieldPlus(label='Data de Desligamento', required=False)
    prestador_servico = forms.ModelChoiceFieldPlus(
        queryset=PrestadorServico.objects.filter(ativo=True),
        widget=AutocompleteWidget(search_fields=PrestadorServico.SEARCH_FIELDS),
        label='Prestador de Serviços',
    )

    fieldsets = (
        (
            'Prestador',
            {
                'fields': ('contrato', ('prestador_servico', 'data_nascimento')),
            },
        ),
        (
            'Função',
            {
                'fields': ('campus', ('categoria', 'funcao'), ('escolaridade', 'jornada_trabalho')),
            },
        ),
        (
            'Informações Salariais',
            {
                'fields': (('salario_bruto', 'custo_mensal'), ('numero_cct', 'inicio_vigencia')),
            },
        ),
        ('Horários', {'fields': (('hora_inicio_jornada', 'hora_fim_jornada'), ('hora_inicio_intervalo', 'hora_fim_intervalo'))}),
        (
            'Outras Informações',
            {
                'fields': ('desligamento',),
            },
        ),
    )

    class Meta:
        model = MaoDeObra
        exclude = ['contrato']

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            pks_uos_contrato = Contrato.objects.filter(pk=self.instance.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)
        else:
            pks_uos_contrato = Contrato.objects.filter(pk=self.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)


class PenalidadeForm(forms.ModelFormPlus):
    class Meta:
        model = Penalidade
        exclude = ['contrato', 'atualizado_por', 'atualizado_em']


class GarantiaForm(forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(label='Data Início')
    vigencia = forms.DateFieldPlus(label='Vigência')
    consulta_susep = forms.FileFieldPlus(label='Anexo', required=True)

    class Meta:
        model = Garantia
        exclude = ['contrato']


class ApostilamentoForm(forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(label='Data inicial', required=False)
    data_fim = forms.DateFieldPlus(label='Data final', required=False)

    class Meta:
        model = Apostilamento
        exclude = ['contrato', 'numero_processo', 'numero_empenho']

    def __init__(self, *args, **kwargs):
        try:
            self.data_inicio_contrato = kwargs.pop('data_inicio_contrato')
        except KeyError:
            self.data_inicio_contrato = kwargs['instance'].contrato.data_inicio
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = self.cleaned_data
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')

        if not self.errors and (data_inicio and data_fim):
            if data_inicio and data_fim and data_inicio > data_fim:
                self._errors['data_fim'] = ErrorList(['Data final anterior a data inicial.'])
            if data_inicio and self.data_inicio_contrato > data_inicio:
                self._errors['data_inicio'] = ErrorList(['Data inicial informada é anterior a data inicial do contrato.'])
        return cleaned_data


class TermoAditivoForm(forms.ModelFormPlus):
    de_prazo = forms.BooleanField(required=False)
    de_valor = forms.BooleanField(required=False)
    de_fiscal = forms.BooleanField(required=False)
    de_outro = forms.BooleanField(required=False)
    valor = forms.DecimalFieldPlus('Valor', required=False)
    data_inicio = forms.DateFieldPlus(label='Data inicial', required=False)
    data_fim = forms.DateFieldPlus(label='Data final', required=False)

    processo = forms.ModelChoiceField(queryset=Processo.objects, widget=AutocompleteWidget(), label='Processo', required=False)

    empenho = forms.ModelChoiceField(
        queryset=Empenho.objects, widget=AutocompleteWidget(search_fields=Empenho.SEARCH_FIELDS), label='Empenho', required=False
    )

    arquivo_aditivo = forms.FileFieldPlus(label='Anexo')

    class Meta:
        model = Aditivo
        exclude = ['contrato', 'ordem', 'arquivo', 'numero_processo', 'numero_empenho']

    class Media:
        js = ('/static/contratos/js/TermoAditivoForm.js',)

    def __init__(self, *args, **kwargs):
        try:
            self.data_inicio_contrato = kwargs.pop('data_inicio_contrato')
        except KeyError:
            self.data_inicio_contrato = kwargs['instance'].contrato.data_inicio
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['arquivo_aditivo'].widget = forms.HiddenInput()
            self.fields['arquivo_aditivo'].required = False

    def clean(self):
        cleaned_data = self.cleaned_data
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')

        if not self.errors:
            if data_inicio and data_fim and data_inicio > data_fim:
                self._errors['data_fim'] = ErrorList(['Data final anterior a data inicial.'])
            if data_inicio and self.data_inicio_contrato > data_inicio:
                self._errors['data_inicio'] = ErrorList(['Data inicial informada é anterior a data inicial do contrato.'])
        return cleaned_data


class ContaContratoForm(forms.ModelFormPlus):
    class Meta:
        model = ContaContrato
        fields = ['descricao']

    def __init__(self, *args, **kwargs):
        contrato = kwargs.pop('contrato')
        fiscal = kwargs.pop('fiscal')
        servidor = kwargs.pop('servidor')
        super().__init__(*args, **kwargs)
        self.instance.contrato = contrato
        self.instance.fiscal = fiscal
        self.instance.servidor = servidor


class EditarContaContratoForm(forms.ModelFormPlus):
    class Meta:
        model = ContaContrato
        fields = ['descricao', 'ativa']

    def __init__(self, *args, **kwargs):
        fiscal = kwargs.pop('fiscal')
        servidor = kwargs.pop('servidor')
        super().__init__(*args, **kwargs)
        self.instance.fiscal = fiscal
        self.instance.servidor = servidor


class DepositoContaContratoForm(forms.ModelFormPlus):
    conta = forms.ModelChoiceField(label='Conta', queryset=ContaContrato.objects.filter(ativa=True), required=True)
    valor = forms.DecimalFieldPlus(label='Valor (R$)', required=True)
    data = forms.DateFieldPlus(label='Data', initial=date.today())

    class Meta:
        model = MovimentacaoContaContrato
        fields = ['conta', 'valor', 'data']

    def __init__(self, *args, **kwargs):
        medicao = kwargs.pop('medicao')
        fiscal = kwargs.pop('fiscal')
        contrato = kwargs.pop('contrato')
        super().__init__(*args, **kwargs)
        self.instance.medicao = medicao
        self.instance.fiscal = fiscal
        self.fields['conta'].queryset = ContaContrato.objects.filter(ativa=True, contrato=contrato)


class SaqueContaContratoForm(forms.ModelFormPlus):
    valor = forms.DecimalFieldPlus(label='Valor (R$)', required=True)
    data = forms.DateFieldPlus(label='Data', initial=date.today())

    class Meta:
        model = MovimentacaoContaContrato
        fields = ['valor', 'data', 'processo_eletronico']

    def __init__(self, *args, **kwargs):
        conta = kwargs.pop('conta')
        fiscal = kwargs.pop('fiscal')
        servidor = kwargs.pop('servidor')
        deposito = kwargs.pop('deposito')
        super().__init__(*args, **kwargs)
        self.instance.conta = conta
        self.instance.fiscal = fiscal
        self.instance.servidor = servidor
        self.instance.deposito = deposito

    def clean(self):
        conta = ContaContrato.objects.get(pk=self.instance.conta.pk)
        valor = self.cleaned_data.get('valor')
        if valor and valor > conta.get_saldo():
            self.add_error('valor', 'Não é possível realizar um Saque de um valor maior que o Saldo disponível.')
        return self.cleaned_data


class EditarMovimentacaoContaContratoForm(forms.ModelFormPlus):
    valor = forms.DecimalFieldPlus(label='Valor (R$)', required=True)

    class Meta:
        model = MovimentacaoContaContrato
        fields = ['valor', 'data', 'processo_eletronico']

    def __init__(self, *args, **kwargs):
        fiscal = kwargs.pop('fiscal')
        super().__init__(*args, **kwargs)
        self.instance.fiscal = fiscal

    def clean(self):
        conta = ContaContrato.objects.get(pk=self.instance.conta.pk)
        valor = self.cleaned_data.get('valor')
        if valor and valor > (conta.get_saldo() + Decimal(self.instance.valor)):
            self.add_error('valor', 'Não é possível realizar um Saque de um valor maior que o Saldo disponível.')
        return self.cleaned_data


class ConsultaFiscalForm(forms.FormPlus):
    METHOD = 'GET'
    ACTION = '/contratos/visualizar_fiscais/'
    SUBMIT_LABEL = 'Buscar'
    DOCENTE = 'docente'
    TECNICO_ADMINISTRATIVO = 'tecnico_administrativo'
    CATEGORIA_CHOICES = (('', 'Todos'), (DOCENTE, 'Docente'), (TECNICO_ADMINISTRATIVO, 'Técnico Administrativo'))
    TEM_CONTRATO_ATIVO_CHOICES = (('', '---'), ('sim', 'Sim'), ('nao', 'Não'))

    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    matricula = forms.CharFieldPlus(label='Matrícula do Servidor', required=False)
    tipo_fiscal = forms.ModelChoiceField(label='Tipo de Fiscal', queryset=TipoFiscal.objects.all(), widget=forms.Select, required=False)
    categoria_servidor = forms.ChoiceField(label='Categoria', choices=CATEGORIA_CHOICES, required=False)
    tipo_contrato = forms.ModelChoiceField(TipoContrato.objects, label='Tipo de Contrato', required=False)
    subtipo_contrato = forms.ModelChoiceField(SubtipoContrato.objects.all().order_by('descricao'), label='Subtipo de Contrato', required=False)
    tem_contrato_ativo = forms.ChoiceField(label='Tem contrato ativo?', choices=TEM_CONTRATO_ATIVO_CHOICES, required=False)
    exportar_para_xls = forms.BooleanField(label='Exportar para XLS', widget=forms.CheckboxInput, required=False)


class PublicacaoContratoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data')
    tipo = forms.ModelChoiceField(label='Tipo', queryset=TipoPublicacao.objects, required=True)
    numero = forms.CharField(label='Número')
    descricao = forms.CharField(label='Descrição', max_length=255)
    arquivo = forms.FileFieldPlus(label='Arquivo', filetypes=['pdf'])

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo')
        if arquivo:
            full_check_file(arquivo)
        return arquivo


class EditarPublicacaoContratoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data', help_text='Data no formato dd/mm/aaaa')
    tipo = forms.ModelChoiceField(label='Tipo', queryset=TipoPublicacao.objects, required=True)
    numero = forms.CharField(label='Número')
    descricao = forms.CharField(label='Descrição', max_length=255)


class PublicacaoAditivoForm(forms.ModelFormPlus):
    data = forms.DateFieldPlus(label='Data', help_text='Data no formato dd/mm/aaaa')

    class Meta:
        model = PublicacaoAditivo
        exclude = ('arquivo', 'aditivo')


class AnexoContratoForm(forms.ModelFormPlus):
    data = forms.DateFieldPlus(label='Data', initial=date.today(), help_text='Data no formato dd/mm/aaaa')
    anexo = forms.FileFieldPlus(label='Anexo', required=True)

    class Meta:
        model = AnexoContrato
        exclude = ('arquivo', 'contrato')

    def __init__(self, *args, **kwargs):
        self.user = kwargs.pop('user', None)
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.arquivo:
            self.fields['anexo'].initial = self.instance.arquivo.get_field_file(self.user)
        if self.instance.pk:
            pks_uos_contrato = Contrato.objects.filter(pk=self.instance.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)
        else:
            pks_uos_contrato = Contrato.objects.filter(pk=self.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)


class AnexoMaoDeObraForm(forms.ModelFormPlus):
    class Meta:
        model = AnexoMaoDeObra
        exclude = ('maodeobra',)

    def __init__(self, *args, **kwargs):
        maodeobra = kwargs.pop('maodeobra')
        super().__init__(*args, **kwargs)
        self.instance.maodeobra = maodeobra


class ParcelaForm(forms.ModelFormPlus):
    data_prevista_inicio = forms.DateFieldPlus(label='Data Prevista de Início', help_text='Data no formato dd/mm/aaaa do início de execução')
    data_prevista_fim = forms.DateFieldPlus(label='Data Prevista de Término', help_text='Data no formato dd/mm/aaaa do término de execução')
    valor_previsto = forms.DecimalFieldPlus(label='Valor Previsto (R$)', required=True, help_text='Valor Previsto da Parcela')
    sem_medicao = forms.BooleanField(label='Parcela Sem Medição', initial=False, required=False)

    fieldsets = (
        (
            '',
            {
                'fields': (
                    ('data_prevista_inicio', 'data_prevista_fim'),
                    'valor_previsto',
                    'campus',
                    'sem_medicao',
                )
            },
        ),
    )

    class Meta:
        model = Parcela
        fields = ('data_prevista_inicio', 'data_prevista_fim', 'valor_previsto', 'sem_medicao')

    def set_contrato(self, contrato):
        self.contrato = contrato

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.medicoes.exists():
            del self.fields['valor_previsto']

    def clean(self):
        cleaned_data = self.cleaned_data
        valor_previsto_salvo = cleaned_data.get('valor_previsto')
        valor_previsto_original = self.instance.valor_previsto or 0
        saldo_contrato = self.contrato.get_saldo_atual()
        if valor_previsto_salvo is not None:
            total = saldo_contrato + valor_previsto_original
            if total < valor_previsto_salvo:
                # Formatar valores no padrão brasileiro (ponto para milhar, vírgula para decimal)
                valor_previsto_fmt = mask_money(valor_previsto_salvo)
                valor_original_fmt = mask_money(valor_previsto_original)
                saldo_contrato_fmt = mask_money(saldo_contrato)
                total_fmt = mask_money(total)
                raise forms.ValidationError(
                    f'O Valor Previsto informado (R$ {valor_previsto_fmt}) excede o saldo disponível do contrato. '
                    f'Detalhamento: Saldo do Contrato = R$ {saldo_contrato_fmt}, '
                    f'Valor Previsto Original da Parcela = R$ {valor_original_fmt}, '
                    f'Total Disponível = R$ {total_fmt} (Saldo + Valor Original).'
                )


ParcelaContratoFormSet = formset_factory(ParcelaForm, extra=0)


class OcorrenciaMedicaoForm(forms.ModelFormPlus):
    ocorrencia = forms.CharField(
        widget=forms.Textarea, required=False, label='Ocorrência(s)', help_text='Descreva aqui as ocorrências registradas nessa medição'
    )
    providencia = forms.CharField(
        widget=forms.Textarea, required=False, label='Providência(s)', help_text='Descreva aqui as providências tomadas para cada ocorrência'
    )

    class Meta:
        model = Medicao
        fields = ('ocorrencia', 'providencia')


class IMRForm(forms.ModelFormPlus):
    campus = forms.ModelChoiceField(label=nomenclatura.campus, queryset=UnidadeOrganizacional.objects.uo().all(), required=True)
    percentual = forms.IntegerFieldPlus(label='Percentual', required=True)
    arquivo = forms.FileFieldPlus(label='Documento', required=True)

    fieldsets = (('Instrumento de Medição de Resultado (IMR)', {'fields': ('campus', 'percentual', 'arquivo')}),)

    class Meta:
        model = IMR
        fields = ('campus', 'percentual', 'arquivo')

    def clean_percentual(self):
        percentual = self.cleaned_data['percentual']
        if percentual is not None:
            if percentual < 0 or percentual > 100:
                raise ValidationError('Percentual do IMR deve estar entre 0 e 100.')
        return percentual


class MedicaoForm(forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(label='Data Efetiva de Início', help_text='Data no formato dd/mm/aaaa do início efetivo de execução')
    data_fim = forms.DateFieldPlus(label='Data Efetiva de Término', help_text='Data no formato dd/mm/aaaa do término efetivo de execução')
    valor_executado = forms.DecimalFieldPlus(label='Valor Executado (R$)', help_text='Valor efetivamente executado', required=True)
    numero_documento = forms.CharField(required=True, label='Nº do Documento', help_text='Número da nota/documento fiscal')

    processo = forms.ModelChoiceField(queryset=Processo.objects, widget=AutocompleteWidget(), label='Processo', required=True)

    arquivo_medicao = forms.FileFieldPlus(label='Arquivo')

    ocorrencia = forms.CharField(
        widget=forms.Textarea, required=False, label='Ocorrência(s)', help_text='Descreva aqui as ocorrências registradas nessa medição'
    )
    providencia = forms.CharField(
        widget=forms.Textarea, required=False, label='Providência(s)', help_text='Descreva aqui as providências tomadas para cada ocorrência'
    )
    imr = forms.ModelChoiceFieldPlus(queryset=IMR.objects.all(), widget=forms.Select(), label='IMR', required=False)

    fieldsets = (
        ('Medição', {'fields': (('data_inicio', 'data_fim'), 'numero_documento', 'arquivo_medicao', 'processo', 'campus', 'imr')}),
        ('Ocorrências', {'fields': ('ocorrencia', 'providencia')}),
        ('Empenhos e Valor da Medição', {'fields': ('valor_executado',)}),
    )

    class Meta:
        model = Medicao
        fields = (
            'data_inicio',
            'data_fim',
            'numero_documento',
            'valor_executado',
            'processo',
            'campus',
            'arquivo_medicao',
            'ocorrencia',
            'providencia',
            'imr',
        )

    def __init__(self, *args, **kwargs):
        self.imr = kwargs.pop('imr', None)
        self.parcela = kwargs.pop('parcela', None)
        super().__init__(*args, **kwargs)
        self.fields['data_inicio'].initial = self.parcela.data_prevista_inicio
        self.fields['data_fim'].initial = self.parcela.data_prevista_fim
        if not self.parcela.cronograma.contrato.permite_medicao_sem_empenho:
            self.fields['valor_executado'].widget.attrs.update(readonly='readonly')
        if self.instance and self.instance.arquivo:
            self.fields['arquivo_medicao'].initial = self.instance.arquivo.get_field_file(self.request.user)
        self.fields['arquivo_medicao'].label = 'Arquivo da Medição'
        pks_uos_contrato = Contrato.objects.filter(pk=self.parcela.cronograma.contrato.id).values_list('campi', flat=True)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)
        imrs = self.parcela.get_imrs_pendentes()
        if imrs.exists():
            self.fields['imr'].queryset = self.parcela.get_imrs_pendentes()
            if self.imr:
                self.fields['imr'].initial = self.imr.id
        else:
            del self.fields['imr']

        fields_conf = []
        if ContratoTipoDocumentoComprobatorio.objects.filter(contrato__pk=self.parcela.cronograma.contrato.id).exists():
            for field_conf in ContratoTipoDocumentoComprobatorio.objects.filter(contrato__pk=self.parcela.cronograma.contrato.id):
                field_name = f'field_name_{field_conf.tipo_documento_comprobatorio.pk}'
                initial_value = '2'
                readonly = False
                if self.instance.pk:
                    medicao_doc_comprobatorio = self.instance.documentos_comprobatorios.filter(
                        medicao__id=self.instance.id, tipo_documento_comprobatorio__id=field_conf.tipo_documento_comprobatorio.pk
                    )
                    if medicao_doc_comprobatorio.exists():
                        initial_value = medicao_doc_comprobatorio.first().confirmacao_fiscal
                        readonly = medicao_doc_comprobatorio.first().recebido_gerente == 'Recebido'

                if field_name not in self.fields:
                    self.fields[field_name] = forms.ChoiceField(
                        required=False,
                        choices=MedicaoTipoDocumentoComprobatorio.CONFIMACAO_FISCAL_CHOICES,
                        label=field_conf.tipo_documento_comprobatorio.descricao,
                    )
                    fields_conf.append(f'field_name_{field_conf.tipo_documento_comprobatorio.pk}')
                    self.fields[field_name].initial = initial_value
                    self.fields[field_name].widget.attrs['readonly'] = readonly

        if fields_conf and self.fieldsets:
            fieldsets = self.fieldsets
            self.fieldsets = []
            self.fieldsets.extend(fieldsets[:2])
            self.fieldsets.extend((('Conferência de Documentos', {'fields': tuple(fields_conf)}),))
            self.fieldsets.extend(fieldsets[2:])

    def clean(self):
        cleaned_data = self.cleaned_data
        if cleaned_data.get('valor_executado') is not None:
            saldo_contrato = self.parcela.cronograma.contrato.get_saldo_atual()
            if self.instance.valor_executado:
                saldo_contrato = self.parcela.cronograma.contrato.get_saldo_atual() + self.instance.valor_executado
            if cleaned_data['valor_executado'].is_nan() or cleaned_data['valor_executado'].is_infinite():
                raise forms.ValidationError('Valor da medição inválido. Por favor, verifique o valor informado.')
            if saldo_contrato < cleaned_data['valor_executado']:
                raise forms.ValidationError('Valor da medição maior que o saldo do contrato.')
        return cleaned_data


class MedicaoEletricaForm(MedicaoForm):
    fieldsets = None
    mes_referencia = forms.ChoiceField(label='Mês de Referência', required=True, choices=Meses.get_choices())
    ano_referencia = forms.ChoiceField(label='Ano de Referência', required=True, choices=Anos.get_choices())
    consumo_ponta = forms.DecimalFieldPlus(label='Consumo de Ponta(kWh)', required=False, max_digits=0)
    consumo_fora_ponta = forms.DecimalFieldPlus(label='Consumo Fora Ponta(kWh)', required=True, max_digits=0)
    demanda_contratada = forms.DecimalFieldPlus(label='Demanda Contratada(kW)', required=False, max_digits=0)
    demanda_medida = forms.DecimalFieldPlus(label='Demanda Medida(kW)', required=False, max_digits=0)
    valor_multa_excedente = forms.DecimalFieldPlus(
        label='Valor da Multa por ultrapassagem (R$)', help_text='Valor da multa por exceder em 5% da demanda contratada', required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_mes_referencia = self.parcela.data_prevista_inicio.month
        default_ano_referencia = self.parcela.data_prevista_inicio.year
        self.fields['mes_referencia'].initial = default_mes_referencia
        self.fields['ano_referencia'].initial = default_ano_referencia
        self.fields['valor_multa_excedente'].widget = self.fields['valor_multa_excedente'].hidden_widget()
        if self.instance and hasattr(self.instance, 'medicaoeletrica'):
            self.fields['mes_referencia'].initial = self.instance.medicaoeletrica.mes_referencia or default_mes_referencia
            self.fields['ano_referencia'].initial = self.instance.medicaoeletrica.ano_referencia or default_ano_referencia
            self.fields['consumo_ponta'].initial = self.instance.medicaoeletrica.consumo_ponta
            self.fields['consumo_fora_ponta'].initial = self.instance.medicaoeletrica.consumo_fora_ponta
            self.fields['demanda_contratada'].initial = self.instance.medicaoeletrica.demanda_contratada
            self.fields['demanda_medida'].initial = self.instance.medicaoeletrica.demanda_medida
            if self.instance.medicaoeletrica.valor_multa_excedente:
                self.fields['valor_multa_excedente'].initial = self.instance.medicaoeletrica.valor_multa_excedente
                self.fields['valor_multa_excedente'].widget = BrDinheiroWidget()

        self.fieldsets = (
            *MedicaoForm.fieldsets,
            (
                'Medição Elétrica',
                {
                    'fields': (
                        ('consumo_ponta', 'consumo_fora_ponta'),
                        ('demanda_contratada', 'demanda_medida'),
                        'valor_multa_excedente',
                        ('ano_referencia', 'mes_referencia'),
                    )
                },
            ),
        )

    def clean(self):
        cleaned_data = self.cleaned_data
        demanda_medida = cleaned_data.get('demanda_medida', None)
        demanda_contratada = cleaned_data.get('demanda_contratada', None)
        if (
            demanda_medida
            and demanda_contratada
            and float(demanda_medida) > (float(demanda_contratada) * 1.05)
            and cleaned_data.get('valor_multa_excedente') is None
        ):
            self.fields['valor_multa_excedente'].widget = BrDinheiroWidget()
            raise forms.ValidationError(
                'O Valor da Multa por ultrapassagem (R$) deve ser informado devido a ultrapassagem superior a 5% da demanda contratada.'
            )
        return cleaned_data


class EscolhaContaVinculadaRetencaoForm(forms.FormPlus):
    conta_vinculada_id = forms.ModelChoiceField(queryset=ContaContrato.objects.none(), label='Conta vinculada para receber a retenção', required=True)

    fieldsets = ((None, {'fields': ('conta_vinculada_id',)}),)

    def __init__(self, *args, **kwargs):
        contas = kwargs.pop('contas')
        super().__init__(*args, **kwargs)
        self.fields['conta_vinculada_id'].queryset = contas


class DocumentoEmpenhoContratoMedicaoInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        documentos = []
        for form in self.extra_forms:
            if form.cleaned_data:
                documento_empenho_contrato = form.cleaned_data.get('documento_empenho_contrato')
                if documento_empenho_contrato in documentos:
                    form.add_error('documento_empenho_contrato', 'Documento já adicionado')
                documentos.append(documento_empenho_contrato)
                valor = form.cleaned_data.get('valor') or 0
                valor_disponivel = (
                    documento_empenho_contrato and documento_empenho_contrato.empenho and documento_empenho_contrato.empenho.get_saldo_restante() or 0
                )
                if valor > valor_disponivel:
                    form.add_error('valor', f'Valor maior que o disponível (RS {format_money(valor_disponivel)})')


class DocumentoEmpenhoContratoMedicaoForm(forms.ModelFormPlus):
    class Meta:
        model = DocumentoEmpenhoContratoMedicao
        fields = ('documento_empenho_contrato', 'valor')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['documento_empenho_contrato'].queryset = self.contrato.documentos_empenho_contrato.all()


class ServidoCampusForm(forms.ModelFormPlus):
    class Meta:
        model = Fiscal
        fields = ('servidor', 'campus')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().all()


servidor_campus = inlineformset_factory(Contrato, Fiscal, fields=['servidor', 'campus'], can_delete=False, extra=0, form=ServidoCampusForm, min_num=1)


class CronogramaForm(forms.ModelFormPlus):
    nl = forms.CharField(required=False, label='NL')
    rc = forms.CharField(required=False, label='RC')

    class Meta:
        model = Cronograma
        exclude = ('contrato',)


class ServidoCampusForm(forms.ModelFormPlus):
    class Meta:
        model = Fiscal
        fields = ('servidor', 'campus')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().all()


servidor_campus = inlineformset_factory(Contrato, Fiscal, fields=['servidor', 'campus'], can_delete=False, extra=0, form=ServidoCampusForm, min_num=1)


class AdicionaFiscalEmLoteForm(forms.ModelFormPlus):
    tipo = forms.ModelChoiceField(
        queryset=TipoFiscal.objects.all(),
        widget=forms.Select(),
    )
    numero_portaria = forms.CharFieldPlus(label='Portaria', max_length=20)
    data_nomeacao = forms.DateFieldPlus(label='Data da Nomeação', required=False)
    data_vigencia = forms.DateFieldPlus(label='Data Final da Vigência', required=False)
    inativo = forms.BooleanField(label='Inativo', initial=False, required=False)

    class Meta:
        model = Fiscal
        fields = ('tipo', 'numero_portaria', 'data_nomeacao', 'data_vigencia', 'inativo')


class FiscalForm(forms.ModelFormPlus):
    data_nomeacao = forms.DateFieldPlus(label='Data da Nomeação', required=False)
    data_vigencia = forms.DateFieldPlus(label='Data Final da Vigência', required=False)
    servidor = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects.ativos(), widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )

    class Meta:
        model = Fiscal
        exclude = ('contrato', 'data_exclusao', 'termo_aditivo')

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo()

        if self.instance and self.instance.servidor_id:
            self.fields['servidor'] = forms.ModelChoiceField(
                label='Servidor',
                queryset=Servidor.objects,
                widget=AutocompleteWidget(readonly=True, search_fields=Servidor.SEARCH_FIELDS),
                initial=self.instance.servidor_id,
            )

    def clean(self):
        cleaned_data = self.cleaned_data
        if (
            self.contrato
            and cleaned_data.get('servidor')
            and Fiscal.objects.filter(contrato=self.contrato, servidor=cleaned_data['servidor'], inativo=False).exists()
        ):
            self.add_error('servidor', 'Este fiscal já foi adicionado ao contrato.')
        return cleaned_data


class AdicionarEmpenhoForm(forms.ModelFormPlus):
    campus = forms.ModelChoiceField(label=nomenclatura.campus, queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    empenho = forms.ModelChoiceField(
        label='Nota de Empenho', queryset=DocumentoEmpenho.objects, widget=AutocompleteWidget(form_filters=[('campus', 'emitente_ug__uo__id')])
    )

    class Meta:
        model = DocumentoEmpenhoContrato
        fields = ('campus', 'empenho', 'descricao')

    def clean_empenho(self):
        empenho = self.cleaned_data.get('empenho')
        if self.instance.id is None and self.instance.contrato.get_empenhos().filter(empenho=empenho).exists():
            raise forms.ValidationError('Empenho escolhido já existe no contrato.')
        return empenho


class UploadArquivoContratoForm(forms.ModelFormPlus):
    class Meta:
        model = Contrato
        fields = ('arquivo_contrato',)


class SolicitacaoFiscalForm(forms.FormPlus):
    numero_memorando = forms.CharField(label='Ofício Nº')


class SolicitacaoPublicacaoPortariaFiscalForm(forms.FormPlus):
    servidor = forms.ModelChoiceField(
        queryset=Servidor.objects, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS, minChars=5), label='Servidor', required=True
    )


class DespachoTermoAditivoForm(forms.FormPlus):
    numero_memorando = forms.CharField(label='Memorando Nº')
    numero_despacho = forms.CharField(label='Despacho Nº')


class DespachoFiscalForm(forms.FormPlus):
    servidor = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects.ativos(), widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )


class OcorrenciaForm(forms.ModelFormPlus):
    prazo_resolucao = forms.DateFieldPlus(label='Prazo para Resolução', required=True)

    class Meta:
        model = Ocorrencia
        fields = ['descricao', 'prazo_resolucao', 'situacao', 'campus']

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            pks_uos_contrato = Contrato.objects.filter(pk=self.instance.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)
        else:
            pks_uos_contrato = Contrato.objects.filter(pk=self.contrato.id).values_list('campi', flat=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.suap().filter(pk__in=pks_uos_contrato)


class SituacaoContratosForm(forms.FormPlus):
    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    data_inicio = forms.DateFieldPlus(label='Data inicial', required=True)
    data_fim = forms.DateFieldPlus(label='Data final', required=True)
    eh_continuado = forms.BooleanField(label='Somente continuados', initial=False, required=False)
    eh_concluido = forms.BooleanField(label='Somente concluídos', initial=False, required=False)

    def clean(self):
        cleaned_data = self.cleaned_data
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')

        if not self.errors:
            if data_inicio > data_fim:
                self._errors['data_fim'] = ['Data final anterior a data inicial']
        return cleaned_data


class RelatorioPendenciasForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.suap(), label=f'Filtrar por {nomenclatura.campus}', required=False, empty_label='Todos'
    )


class RelatorioConsumoEnergiaForm(forms.FormPlus):
    campus = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(), label=f'Filtrar por {nomenclatura.campus}', required=False, empty_label='Todos'
    )
    mes = forms.ChoiceField(required=False, label='Mês')
    ano = forms.ModelChoiceFieldPlus(Ano.objects, required=True, widget=forms.Select(), label='Ano')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        eh_gerente_ou_auditor = in_group(self.request.user, 'Gerente de Contrato') or in_group(self.request.user, 'Auditor')
        if not eh_gerente_ou_auditor:
            qs_campus = UnidadeOrganizacional.objects.suap().filter(pk=self.request.user.get_relacionamento().setor.uo.id)
            self.fields['campus'].queryset = qs_campus
        self.fields['mes'].choices = [[0, 'Todos'], *Meses.get_choices()]


class RelatorioTerceirizadosForm(forms.FormPlus):
    ATIVO = 'Ativo'
    INATIVO = 'Inativo'
    CONCLUIDO = 'Concluído'
    CANCELADO = 'Cancelado'
    TERCEIRIZADOS_CHOICES = (
        ('', 'Todas'),
        (ATIVO, ATIVO),
        (INATIVO, INATIVO),
    )
    CONTRATOS_CHOICES = (
        ('', 'Todas'),
        (ATIVO, ATIVO),
        (CONCLUIDO, CONCLUIDO),
        (CANCELADO, CANCELADO),
    )
    campus = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.uo(), label=f'Filtrar por {nomenclatura.campus}', required=False, empty_label='Todos'
    )
    contrato = forms.ModelChoiceFieldPlus(
        Contrato.objects.annotate(num_maodeobra=Count('maosdeobra')).filter(num_maodeobra__gt=0),
        required=False,
        widget=forms.Select(),
        label='Contrato',
    )
    situacao_terceirizado = forms.ChoiceField(label='Situação do terceirizado', required=False, choices=TERCEIRIZADOS_CHOICES)
    situacao_contrato = forms.ChoiceField(label='Situação do contrato', required=False, choices=CONTRATOS_CHOICES)
    mascarar_cpfs = forms.BooleanField(label='Mascarar CPF', required=False)

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        eh_gerente_ou_auditor = in_group(self.request.user, 'Gerente de Contrato') or in_group(self.request.user, 'Auditor')
        eh_fiscal = in_group(self.request.user, 'Fiscal de Contrato')
        if not eh_gerente_ou_auditor:
            qs_campus = UnidadeOrganizacional.objects.suap().filter(pk=self.request.user.get_relacionamento().setor.uo.id)
            self.fields['campus'].queryset = qs_campus
        if eh_fiscal:
            fiscal = Fiscal.objects.filter(servidor__matricula=self.request.user.get_relacionamento().matricula)
            qs_fiscal = Contrato.objects.filter(fiscais__in=fiscal).distinct()
            self.fields['contrato'].queryset = qs_fiscal


class RelatorioEmpenhosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    campus = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(), label=f'Filtrar por {nomenclatura.campus}', required=False, empty_label='Todos'
    )
    contrato = forms.ModelChoiceFieldPlus(
        Contrato.objects.filter(empenho__isnull=False), required=False, widget=forms.AutocompleteWidget(), label='Contrato'
    )
    empenho = forms.ModelChoiceFieldPlus(DocumentoEmpenho.objects.all(), required=False, widget=forms.AutocompleteWidget(), label='Empenho')
    empresa_cnpj = forms.CharFieldPlus(required=False, label='CNPJ do Favorecido')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        eh_gerente_ou_auditor = in_group(self.request.user, 'Gerente de Contrato') or in_group(self.request.user, 'Auditor')
        eh_fiscal = in_group(self.request.user, 'Fiscal de Contrato')
        if not eh_gerente_ou_auditor:
            qs_campus = UnidadeOrganizacional.objects.suap().filter(pk=self.request.user.get_relacionamento().setor.uo.id)
            self.fields['campus'].queryset = qs_campus
        if eh_fiscal:
            fiscal = Fiscal.objects.filter(servidor__matricula=self.request.user.get_relacionamento().matricula)
            qs_fiscal = Contrato.objects.filter(fiscais__in=fiscal).distinct()
            self.fields['contrato'].queryset = qs_fiscal


class FiltroContratoForm(forms.FormPlus):
    CHOICES = ((None, '---'), (True, 'Sim'), (False, 'Não'))
    busca = forms.CharFieldPlus(label='Busca', help_text='Buscar por número, objeto, processo e número da licitação', required=False)
    contratada = forms.ModelChoiceFieldPlus(label='Contratada', queryset=Vinculo.objects, required=False)
    tipo_contrato = forms.ModelChoiceField(label='Tipo de contrato', queryset=TipoContrato.objects, required=False)
    subtipo_contrato = forms.ModelChoiceField(label='Subtipo de contrato', queryset=SubtipoContrato.objects, required=False)
    continuidade = forms.ChoiceField(label='Continuidade', choices=CONTINUIDADE_CHOICES, required=False)
    natureza = forms.ChoiceField(label='Natureza', choices=[[None, '---'], *NATUREZA_CHOICES], required=False)
    base_legal = forms.ModelChoiceField(label='Base legal', queryset=BaseLegal.objects, required=False)
    tipo_licitacao = forms.ModelChoiceField(label='Tipo de licitação', queryset=TipoLicitacao.objects, widget=forms.Select, required=False)
    periodo_data_inicio = forms.BRDateRangeField(label='Início', required=False, help_text='Data do início do contrato')
    periodo_data_vencimento = forms.BRDateRangeField(
        label='Vencimento', help_text='Considera a maior entre a data final do contrato ou do(s) seus aditivo(s).', required=False
    )
    possui_dedicacao_exclusiva_mao_de_obra = forms.ChoiceField(label='Possui dedicação exclusiva de mão de obra?', choices=CHOICES, required=False)
    concluido = forms.ChoiceField(label='Concluído', choices=CHOICES, required=False)
    cancelado = forms.ChoiceField(label='Cancelado', choices=CHOICES, required=False)
    campi = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.suap(), required=False, label=nomenclatura.campi)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['contratada'].queryset = Vinculo.objects.filter(contratos__isnull=False).distinct()


class FiltroContratoEletricoForm(forms.FormPlus):
    ano = forms.ChoiceField(label='Ano:', widget=forms.Select())
    mes = forms.MesField(label='Mês', empty_label='Todos')

    fieldsets = ((None, {'fields': (('ano', 'mes'),)}),)

    def __init__(self, *args, **kwargs):
        contrato = kwargs.pop('contrato')
        super().__init__(*args, **kwargs)
        self.fields['ano'].choices = Anos.get_choices(ano_minimo=contrato.data_inicio.year, empty_label='Todos', empty_value='todos')
        self.fields['ano'].initial = date.today().year


class ConfiguracaoForm(forms.FormPlus):
    dias_nova_licitacao = forms.IntegerFieldPlus(label='Quantidade de dias para iniciar nova licitação', required=False, initial=90)
    tipo_contrato_energia_eletrica = forms.ModelChoiceField(
        label='SubTipo de Contrato Energia Elétrica',
        help_text='Escolha aqui o subtipo de contrato que será usado como referência para contratos de fornecimento de energia elétrica.',
        queryset=SubtipoContrato.objects,
        widget=forms.Select,
        required=False,
    )
    if 'documento_eletronico' in settings.INSTALLED_APPS:
        tipo_documento_contrato = forms.MultipleModelChoiceFieldPlus(
            label='Selecione os tipos de documento utilizados para Contratos Administrativos',
            help_text='Escolha aqui os tipos de documentos utilizados para Contratos Administrativos.',
            queryset=TipoDocumento.objects.filter(ativo=True),
            required=False,
        )
    restringir_por_unidade = forms.BooleanField(
        label='Restringir por Unidade',
        help_text='Marque essa opção caso deseje que usuários com perfil de operador possam gerenciar os contratos apenas de sua unidade.',
        required=False,
    )
    habilitar_numeracao_por_campi_gerenciador = forms.BooleanField(
        label='Habilitar numeração de contratos por campus',
        help_text='Habilita os campi gerenciadores a possuírem um sequencial numérico próprio.',
        required=False,
    )

    # Conta vinculada percentuais
    conta_vinculada_perc_13 = forms.DecimalFieldPlus(label='Percentual 13º (%)', required=False, max_digits=7, decimal_places=6)
    conta_vinculada_perc_ferias = forms.DecimalFieldPlus(label='Percentual Férias (%)', required=False, max_digits=7, decimal_places=6)
    conta_vinculada_perc_fgts = forms.DecimalFieldPlus(label='Percentual FGTS (%)', required=False, max_digits=7, decimal_places=6)
    conta_vinculada_perc_submodulo_grau1 = forms.DecimalFieldPlus(
        label='Percentual Submódulo Grau 1 (%)', required=False, max_digits=7, decimal_places=6
    )
    conta_vinculada_perc_submodulo_grau2 = forms.DecimalFieldPlus(
        label='Percentual Submódulo Grau 2 (%)', required=False, max_digits=7, decimal_places=6
    )
    conta_vinculada_perc_submodulo_grau3 = forms.DecimalFieldPlus(
        label='Percentual Submódulo Grau 3 (%)', required=False, max_digits=7, decimal_places=6
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        tipo_documento_contrato = Configuracao.get_valor_por_chave(app='contratos', chave='tipo_documento_contrato')
        self.fields['tipo_documento_contrato'].initial = list(tipo_documento_contrato.split(',')) if tipo_documento_contrato else []

        self.fields['conta_vinculada_perc_13']._config_key = 'conta_vinculada.perc_13'
        self.fields['conta_vinculada_perc_ferias']._config_key = 'conta_vinculada.perc_ferias'
        self.fields['conta_vinculada_perc_fgts']._config_key = 'conta_vinculada.perc_fgts'
        self.fields['conta_vinculada_perc_submodulo_grau1']._config_key = 'conta_vinculada.perc_submodulo_grau1'
        self.fields['conta_vinculada_perc_submodulo_grau2']._config_key = 'conta_vinculada.perc_submodulo_grau2'
        self.fields['conta_vinculada_perc_submodulo_grau3']._config_key = 'conta_vinculada.perc_submodulo_grau3'

        self.fields['conta_vinculada_perc_13'].initial = _get_conf_or_default('conta_vinculada.perc_13', '8.333333')
        self.fields['conta_vinculada_perc_ferias'].initial = _get_conf_or_default('conta_vinculada.perc_ferias', '12.100000')
        self.fields['conta_vinculada_perc_fgts'].initial = _get_conf_or_default('conta_vinculada.perc_fgts', '4.0')
        self.fields['conta_vinculada_perc_submodulo_grau1'].initial = _get_conf_or_default('conta_vinculada.perc_submodulo_grau1', '7.39')
        self.fields['conta_vinculada_perc_submodulo_grau2'].initial = _get_conf_or_default('conta_vinculada.perc_submodulo_grau2', '7.60')
        self.fields['conta_vinculada_perc_submodulo_grau3'].initial = _get_conf_or_default('conta_vinculada.perc_submodulo_grau3', '7.82')


class ExportacaoForm(forms.FormPlus):
    STATUS_ANDAMENTO = 'Em andamento'
    STATUS_CONCLUIDO = 'Concluídos'
    STATUS_CANCELADOS = 'Cancelados'
    STATUS_TODOS = 'Todos'
    STATUS_CHOICES = (
        (STATUS_TODOS, STATUS_TODOS),
        (STATUS_ANDAMENTO, STATUS_ANDAMENTO),
        (STATUS_CONCLUIDO, STATUS_CONCLUIDO),
        (STATUS_CANCELADOS, STATUS_CANCELADOS),
    )

    QUADRO_PUBLICACAO = 'Publicações'
    QUADRO_CRONOGRAMA = 'Cronograma'
    QUADRO_EMPENHOS = 'Empenhos'
    QUADRO_TERCEIRIZADOS = 'Terceirizados ativos'
    QUADRO_CHOICES = (
        (QUADRO_PUBLICACAO, QUADRO_PUBLICACAO),
        (QUADRO_CRONOGRAMA, QUADRO_CRONOGRAMA),
        (QUADRO_EMPENHOS, QUADRO_EMPENHOS),
        (QUADRO_TERCEIRIZADOS, QUADRO_TERCEIRIZADOS),
    )

    tipo = forms.ModelChoiceFieldPlus(queryset=TipoContrato.objects, label='Tipo do Contrato', required=False)
    data_inicio_periodo = forms.BRDateRangeField(label='Período para Início do Contrato', required=False)
    campi = forms.ModelMultipleChoiceField(
        queryset=UnidadeOrganizacional.objects, widget=FilteredSelectMultiplePlus('', True), label=nomenclatura.campi
    )
    status = forms.ChoiceField(label='Estado do contrato', choices=STATUS_CHOICES, initial=STATUS_TODOS, required=False)
    quadros = forms.MultipleChoiceField(label='Quadros', choices=QUADRO_CHOICES, widget=forms.CheckboxSelectMultiplePlus, required=False)


class UploadArquivoForm(forms.FormPlus):
    arquivo = forms.FileFieldPlus(filetypes=['pdf'])

    def clean_arquivo(self):
        arquivo = self.cleaned_data.get('arquivo', None)
        full_check_file(arquivo)
        return arquivo


class ContratoTiposDocumentosComprobatorioForm(forms.FormPlus):
    tipo_documento_comprobatorio = forms.ModelChoiceField(
        label='Tipo de Documento Comprobatório', queryset=TipoDocumentoComprobatorio.objects.filter(ativo=True), required=True
    )

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = self.cleaned_data
        tipo_documento_comprobatorio = cleaned_data.get('tipo_documento_comprobatorio')

        if not self.errors:
            if ContratoTipoDocumentoComprobatorio.objects.filter(
                contrato=self.contrato, tipo_documento_comprobatorio=tipo_documento_comprobatorio
            ).exists():
                self._errors['tipo_documento_comprobatorio'] = ['Tipo de documento já está vinculado ao Contrato']
        return cleaned_data

    def save(self):
        tipo_doc_contrato = ContratoTipoDocumentoComprobatorio()
        tipo_doc_contrato.contrato = self.contrato
        tipo_doc_contrato.tipo_documento_comprobatorio = self.cleaned_data['tipo_documento_comprobatorio']
        tipo_doc_contrato.save()
        return tipo_doc_contrato


class ArrecadacaoReceitaForm(forms.ModelFormPlus):
    mes_referencia = forms.ChoiceField(label='Mês de Referência', required=True, choices=Meses.get_choices())
    ano_referencia = forms.ChoiceField(label='Ano de Referência', required=True, choices=Anos.get_choices())

    class Meta:
        model = ArrecadacaoReceita
        exclude = ['contrato']


class MedicaoTipoDocumentoComprobatorioForm(forms.ModelFormPlus):
    class Meta:
        model = MedicaoTipoDocumentoComprobatorio
        exclude = ['medicao', 'confirmado', 'data_avaliacao', 'avaliador_gerente']

    def clean_parecer_gerente(self):
        cleaned_data = self.cleaned_data
        parecer_gerente = cleaned_data.get('parecer_gerente')

        if cleaned_data['recebido_gerente'] == MedicaoTipoDocumentoComprobatorio.PENDENTE and parecer_gerente is None:
            raise forms.ValidationError('É necessário informar uma descrição da pendência.')
        return parecer_gerente


servidor_campus = inlineformset_factory(Contrato, Fiscal, fields=['servidor', 'campus'], can_delete=False, extra=0, form=ServidoCampusForm, min_num=1)


class ContratoConcluirForm(forms.FormPlus):
    data_conclusao = forms.DateFieldPlus(label='Data de Conclusão')
    motivo_conclusao = forms.ModelChoiceField(MotivoConclusaoContrato.objects, required=True)


class BuscarContratoComprasGovForm(forms.FormPlus):
    contrato_id_comprasgov = forms.CharFieldPlus(
        label='Identificador do Contrato no ComprasGov',
        help_text=mark_safe(
            '<a href="https://portal.ifrn.edu.br/institucional/tecnologia-da-informacao/tutoriais/suap/como-importar-contratos-do-comprasgov-para-suap/">Veja aqui como localizar o identificador</a> no <a target="_blank" href="https://contratos.comprasnet.gov.br/">https://contratos.comprasnet.gov.br/</a>'
        ),
        required=True,
    )

    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'

    class Media:
        js = ('/static/contratos/js/BuscarContratoComprasGovForm.js',)

    def buscar(self):
        """
        Realiza requisição para a API do ComprasGov para buscar contrato
        """
        contrato_id_comprasgov = self.cleaned_data['contrato_id_comprasgov']
        api_externa = APIExterna.CONTRATOSGOVBR
        if not api_externa.ativo:
            raise Exception('API ContratosGovBR está inativa.')
        api_service = api_externa.get_service()
        return api_service.obter_contrato_comprasgov(contrato_id_comprasgov)


class ItemContratoForm(forms.ModelFormPlus):
    fieldsets = (
        (
            '',
            {
                'fields': (
                    'numero_item',
                    'descricao',
                    ('valor_unitario', 'valor_total', 'quantidade'),
                    'tipo',
                )
            },
        ),
    )

    class Meta:
        model = ItemContrato
        exclude = ['contrato', 'id_comprasgov', 'atualizado_por', 'atualizado_em', 'grupo']

    def clean(self):
        cleaned_data = super().clean()
        quantidade = cleaned_data.get('quantidade')
        valor_unitario = cleaned_data.get('valor_unitario')
        valor_total = cleaned_data.get('valor_total')

        if quantidade and valor_unitario and valor_total:
            if quantidade * valor_unitario != valor_total:
                raise forms.ValidationError(f'Valor Total inválido. Valor total esperado: {quantidade * valor_unitario}')

        return cleaned_data


class AgendaForm(forms.ModelFormPlus):
    fiscais = forms.MultipleModelChoiceFieldPlus(Fiscal.objects.none(), label='Fiscais')

    class Meta:
        model = Agenda
        fields = [
            'fiscais',
            'descricao',
            'data_prevista',
        ]

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato', None)
        super().__init__(*args, **kwargs)
        if not self.contrato:
            self.contrato = self.instance.contrato
        self.fields['fiscais'].queryset = self.contrato.fiscais.all()


class RegistrarFiscalizacaoForm(forms.FormPlus):
    data_execucao = forms.DateFieldPlus(label='Data de Execução', required=True)
    anexos = MultiFileField(filetypes=['pdf'], min_num=0, max_num=10, max_file_size=1024 * 1024 * 5, label='Anexos', required=False)


class OcorrenciaMaoDeObraForm(forms.ModelFormPlus):
    arquivo = forms.FileFieldPlus(label='Anexo', required=False, filetypes=['pdf', 'jpeg', 'jpg', 'png'], max_file_size=5 * 1024 * 1024)

    class Meta:
        model = OcorrenciaMaoDeObra
        exclude = ('maodeobra',)

    def __init__(self, *args, **kwargs):
        maodeobra = kwargs.pop('maodeobra')
        super().__init__(*args, **kwargs)
        self.instance.maodeobra = maodeobra

    def clean_data_fim(self):
        data_fim = self.cleaned_data.get('data_fim')
        tipo = self.cleaned_data.get('tipo')

        # Verifica se o tipo é obrigatório e se data_fim não foi fornecido
        if tipo and tipo.obrigatorio_informar_data_fim and not data_fim:
            raise ValidationError('Data de Fim da Vigência é obrigatória para este tipo.')

        return data_fim


class VerbaSalarialMaoDeObraForm(forms.ModelFormPlus):
    class Meta:
        model = VerbaSalarialMaoDeObra
        exclude = ('maodeobra', 'salario_bruto')

    def __init__(self, *args, **kwargs):
        maodeobra = kwargs.pop('maodeobra')
        super().__init__(*args, **kwargs)
        self.instance.maodeobra = maodeobra

    def clean_data_fim(self):
        data_inicio = self.cleaned_data.get('data_inicio', None)
        data_fim = self.cleaned_data.get('data_fim')
        tipo = self.cleaned_data.get('tipo')

        # Verifica se o tipo é obrigatório e se data_fim não foi fornecido
        if tipo and tipo.obrigatorio_informar_data_fim and not data_fim:
            raise ValidationError('Data de Fim da Vigência é obrigatória para este tipo.')

        if data_fim and data_fim <= data_inicio:
            raise forms.ValidationError('A Data de Fim da Vigência deve ser maior que a data de início')

        return data_fim

    def clean(self):
        cleaned_data = self.cleaned_data
        tipo = cleaned_data.get('tipo', None)

        if self.instance.id is None and VerbaSalarialMaoDeObra.objects.filter(maodeobra=self.instance.maodeobra, tipo=tipo).exists():
            raise forms.ValidationError('Esta Mão de Obra já possui uma verba salarial com o mesmo tipo.')

        return cleaned_data


class IndicadoresForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        label=f'Filtrar por {nomenclatura.campus}:', required=False, queryset=UnidadeOrganizacional.objects.uo(), empty_label='Todos os campi'
    )
    ano = forms.ModelChoiceField(queryset=Ano.objects, label='Filtrar por Ano:', required=True)
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'


class CopiarMaoDeObra(forms.FormPlus):
    prestadores_servicos = forms.ModelMultiplePopupChoiceField(PrestadorServico.objects, label='Prestadores de Serviço')
    contrato = forms.ModelChoiceFieldPlus(Contrato.objects.none())

    def __init__(self, *args, **kwargs):
        self.contrato = kwargs.pop('contrato')
        super().__init__(*args, **kwargs)
        self.fields['prestadores_servicos'].queryset = PrestadorServico.objects.filter(
            id__in=self.contrato.maosdeobra.values_list('prestador_servico_id', flat=True)
        )
        self.fields['contrato'].queryset = Contrato.objects.exclude(id=self.contrato.id)

    def save(self, *args, **kwargs):
        prestadores_servicos = self.cleaned_data['prestadores_servicos']
        contrato = self.cleaned_data['contrato']
        maos_de_obra = self.contrato.maosdeobra.filter(prestador_servico_id__in=prestadores_servicos)
        for mao_de_obra in maos_de_obra:
            mao_de_obra.id = None
            mao_de_obra.contrato = contrato
            mao_de_obra.save()
