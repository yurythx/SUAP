import calendar
import datetime

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.utils import ErrorList

from comum.models import Configuracao, Sala
from comum.utils import get_uo
from djtools import forms
from djtools.forms.fields import MultiFileField
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus, RenderableCheckboxSelect, TreeWidget
from djtools.templatetags.filters import in_group
from patrimonio import migrador, utils
from patrimonio.models import (
    Baixa,
    BaixaTipo,
    CategoriaMaterialPermanente,
    Cautela,
    CautelaInventario,
    ConferenciaSala,
    FotoInventario,
    HistoricoCatDepreciacao,
    Inventario,
    InventarioRotulo,
    InventarioStatus,
    InventarioTipoUsoPessoal,
    InventarioValor,
    PlanoContas,
    Requisicao,
    RequisicaoItem,
)
from protocolo.models import Processo
from rh.models import Pessoa, PessoaJuridica, Servidor, Setor, UnidadeOrganizacional


class FotoInventarioForm(forms.ModelFormPlus):
    class Meta:
        model = FotoInventario
        fields = ('descricao', 'data', 'foto')


def CargaFormFactory(request):
    fields = {}
    fields['servidor_destino'] = forms.ModelChoiceField(
        label='Destino da Carga',
        queryset=Servidor.objects,
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        required=True,
        help_text='Restrito aos servidores do seu campus',
    )

    fields['estado_conservacao'] = forms.ChoiceField(label='Estado de Conservação', choices=Inventario.CHOICES_CONSERVACAO)
    fields['sala'] = forms.ModelChoiceFieldPlus(queryset=Sala.ativas, widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS))
    fields['rotulos'] = forms.MultipleModelChoiceFieldPlus(label='Rótulos', required=False, queryset=InventarioRotulo.objects)
    fields['inventarios'] = forms.ModelMultipleChoiceField(queryset=Inventario.pendentes, widget=forms.CheckboxSelectMultiplePlus())
    fields['descricao'] = forms.CharField(label='Descrição', widget=forms.Textarea(), required=False)

    def clean(self):
        if not self.errors:
            if self.cleaned_data.get('inventarios'):
                inventarios = self.cleaned_data.get('inventarios')
                servidor_destino = self.cleaned_data.get('servidor_destino')
                campi = set()
                for inventario in inventarios:
                    campi.add(inventario.carga_contabil.campus)
                if servidor_destino.setor:
                    uo = servidor_destino.setor.uo
                    if len(campi) != 1 and uo in campi:
                        self.add_error(
                            'inventarios',
                            'Não é permitido adicionar inventários do seu campus com inventários de campus diferentes. Faça cargas diferentes.',
                        )
                else:
                    self.add_error('servidor_destino', 'Não é permitido adicionar inventários pois este servidor não possui um setor associado.')

        return self.cleaned_data

    @transaction.atomic()
    def save(self):
        inventarios = self.cleaned_data['inventarios']
        descricao = self.cleaned_data['descricao']
        servidor_destino = self.cleaned_data['servidor_destino']
        estado_conservacao = self.cleaned_data['estado_conservacao']
        sala = self.cleaned_data['sala']
        rotulos = self.cleaned_data['rotulos']
        Inventario.criar_requisicao(inventarios, servidor_destino, self.request.user, estado_conservacao, sala, rotulos, descricao)

    return type('CargaForm', (forms.BaseForm,), {'base_fields': fields, 'request': request, 'clean': clean, 'save': save, 'METHOD': 'POST'})


class EditarInventario(forms.ModelFormPlus):
    descricao = forms.CharField(widget=forms.Textarea, required=True)
    observacao = forms.CharField(label='Observação', widget=forms.Textarea, required=False)
    sala = forms.ModelChoiceField(
        label='Sala', required=False, queryset=Sala.ativas.all(), widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS)
    )
    estado_conservacao = forms.ChoiceField(label='Estado de conservação', required=False, choices=Inventario.CHOICES_CONSERVACAO)
    numero_serie = forms.CharField(label='Número de Série', required=False, max_length=50)
    tipo_uso_pessoal = forms.ModelChoiceField(label='Tipo Uso Pessoal', required=False, queryset=InventarioTipoUsoPessoal.objects.all())
    rotulos = forms.MultipleModelChoiceFieldPlus(
        InventarioRotulo.objects, label='Rótulos', required=False, widget=FilteredSelectMultiplePlus('', True)
    )
    elemento_despesa = forms.ModelChoiceFieldPlus(label='Categoria de Despesa', required=False, queryset=CategoriaMaterialPermanente.objects.all())
    numero = forms.CharField(label='Número do Inventário', required=True, max_length=20)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.initial['rotulos'] = [t.pk for t in self.instance.rotulos.all()]

        self.pode_editar_numero = Configuracao.get_valor_por_chave('patrimonio', 'permitir_edicao_tombo') or False
        Sala = apps.get_model('comum', 'sala')

        user = self.request.user

        # caso não seja sistemico só exibe salas do seu proprio campus
        if not in_group(user, 'Coordenador de Patrimônio Sistêmico'):
            self.fields['sala'].queryset = Sala.ativas.filter(predio__uo=get_uo(user))

        if in_group(user, ['Coordenador de Patrimônio Sistêmico', 'Coordenador de Patrimônio']):
            if not self.pode_editar_numero:
                del self.fields['numero']
            return

        if in_group(user, 'Operador de Patrimônio'):
            del self.fields['numero']
            del self.fields['elemento_despesa']
            return

    class Meta:
        model = Inventario
        fields = [
            'numero',
            'descricao',
            'observacao',
            'sala',
            'estado_conservacao',
            'rotulos',
            'numero_serie',
            'tipo_uso_pessoal',
            'elemento_despesa',
        ]

    def clean(self):
        cleaned_data = self.cleaned_data
        if self.pode_editar_numero:
            numero = cleaned_data.get('numero')
            if self.instance.numero != int(numero) and Inventario.objects.filter(numero=numero).last():
                self._errors['numero'] = ErrorList(['Este número já está associado a outro inventário. Escolha outro número.'])
        return cleaned_data


def InventariosEditarEmLoteFormFactory(campus=None):
    """Geração de formulários de edição de inventários na listagem da busca.
    Recebe o campus passado como filtro no formulário de busca.
    """

    class InventarioEditarEmLoteForm(forms.FormPlus):
        sala = forms.ModelChoiceField(label='Definir sala para os itens marcados:', required=False, queryset=Sala.ativas, empty_label='Não aplicar')
        rotulo = forms.ModelChoiceField(
            label='Aplicar rótulo nos itens marcados:', required=False, queryset=InventarioRotulo.objects.all(), empty_label='Não aplicar'
        )

        exclusao_rotulo = forms.BooleanField(label='Retirar rótulos nos itens marcados:', required=False)
        conservacao = forms.ChoiceField(label='Definir estado de conservação:', required=False, choices=Inventario.CHOICES_CONSERVACAO)
        tipo_uso_pessoal = forms.ModelChoiceField(
            label='Definir Inventário Uso Pessoal', required=False, queryset=InventarioTipoUsoPessoal.objects.all(), empty_label='Não aplicar'
        )
        fotos = MultiFileField(min_num=1, max_num=10, max_file_size=1024 * 1024 * 5, label='Adicionar Fotos nos itens marcados:', required=False)
        descricao_fotos = forms.CharField(label='Descrição das Fotos', max_length=500, required=False)
        data_fotos = forms.DateFieldPlus(label='Data das Fotos', required=False, initial=datetime.datetime.today())

    if campus:
        # select_related: str(Sala) usa predio, e str(Predio) usa uo
        InventarioEditarEmLoteForm.base_fields['sala'].queryset = Sala.ativas.filter(predio__uo=campus).select_related('predio__uo')

    return InventarioEditarEmLoteForm


class FormRelatorioTotal(forms.FormPlus):
    mes_choices = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )

    campus = forms.ModelChoiceField(label='Campus da Carga', required=True, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='-----')
    mes = forms.ChoiceField(label='Mês', choices=mes_choices, required=True)
    ano = forms.IntegerFieldPlus(widget=forms.TextInput(), required=True, max_length=4)
    METHOD = 'GET'


class FormRelatorioTotalPeriodo(forms.FormPlus):
    ano = forms.IntegerField()
    METHOD = 'GET'

    def clean_ano(self):
        msg = 'O ano escolhido está no futuro, escolha um anterior.'
        if self.cleaned_data['ano'] > datetime.date.today().year:
            raise forms.ValidationError(msg)
        return self.cleaned_data['ano']


def TermosFormFactory(usuario):
    """
    Cria uma classe para gerar formulário de Termos de Responsabilidade,
    Recebimento ou Anual, com base no usuário autenticado.
    """

    def _get_media(self):
        """Definição da media do form dinâmico."""
        media = forms.Media()
        for field in list(self.fields.values()):
            media = media + field.widget.media
        media = media + forms.Media(js=('/static/patrimonio/js/TermosForm.js',))
        return media

    media = property(_get_media)

    fields = {}
    tipo_do_termo = (
        ('responsabilidade', 'Responsabilidade'),
        ('recebimento', 'Recebimento'),
        ('anual', 'Anual'),
        ('nada_consta_desligamento', 'Nada Consta (Desligamento)'),
        ('nada_consta_remanejamento', 'Nada Consta (Remanejamento)'),
    )
    fields['tipo'] = forms.ChoiceField(label='Tipo do Termo', choices=tipo_do_termo, required=True)
    fields['periodo_de_movimento_ini'] = forms.DateFieldPlus(required=False, label='Período de movimento inicial')
    fields['periodo_de_movimento_fim'] = forms.DateFieldPlus(required=False, label='Período de movimento final')
    fields['ano'] = forms.IntegerFieldPlus(required=False, label='Ano')

    if usuario.has_perm('patrimonio.pode_ver_relatorios'):
        fields['servidor'] = forms.ModelChoiceField(
            label='Servidor', queryset=Servidor.objects.all(), widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
        )
    else:
        fields['servidor'] = forms.ModelChoiceField(
            label='Servidor', queryset=Servidor.objects.all(), widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS, readonly=True)
        )

    fieldsets = [(None, {'fields': ('servidor', 'tipo', 'periodo_de_movimento_ini', 'periodo_de_movimento_fim', 'ano')})]

    def clean(self):
        cleaned_data = self.cleaned_data
        tipo = cleaned_data.get('tipo')
        data_ini = cleaned_data.get('periodo_de_movimento_ini')
        data_fim = cleaned_data.get('periodo_de_movimento_fim')
        ano = cleaned_data.get('ano')

        if tipo == 'recebimento':
            if not data_ini:
                self._errors['periodo_de_movimento_ini'] = ErrorList(['Obrigatório'])
            if not data_fim:
                self._errors['periodo_de_movimento_fim'] = ErrorList(['Obrigatório'])
            if data_fim and data_ini:
                if data_ini > data_fim:
                    self._errors['periodo_de_movimento_fim'] = ErrorList(['Data final anterior a data inicial'])
        if tipo == 'anual':
            if not ano:
                self._errors['ano'] = ErrorList(['Obrigatório'])

        return cleaned_data

    return type(
        'TransferenciaForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'media': media, 'clean': clean, 'METHOD': 'GET'}
    )


class FormTotalizacaoEdPeriodo(forms.FormPlus):
    mes_choices = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )
    mes = forms.ChoiceField(label='Mês', choices=mes_choices, required=True)
    ano = forms.IntegerField(required=True, min_value=1)
    doacoes = forms.BooleanField(label='Incluir Doações', required=False)

    METHOD = 'GET'

    def clean_ano(self):
        ano = self.cleaned_data.get('ano')
        if ano is not None and len(str(ano)) != 4:
            raise forms.ValidationError('O ano deve ter exatamente 4 dígitos.')
        return ano


def inventario_busca_clean_numero(self):
    faixa = self.cleaned_data['numero']
    if faixa:
        if '-' in faixa:
            limite = faixa.split('-')
            if len(limite) == 2:
                if not limite[0].strip().isdigit() or not limite[1].strip().isdigit():
                    raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
            else:
                raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
        elif ',' in faixa:
            limite = faixa.split(',')
            for idx in range(0, len(limite), 1):
                if not limite[idx].strip().isdigit():
                    raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
        elif ',' not in faixa:
            if not faixa.strip().isdigit():
                raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
    return faixa


def inventario_busca_clean_valor(self):
    valor = self.cleaned_data['valor'].strip()
    if valor:
        if valor.count(',') != 1:
            conteudo = valor
        else:
            conteudo = valor.split(',')

        if valor.count('<') >= 1 or valor.count('=') >= 1 or valor.count('>') >= 1:
            # valida se o primeiro caracter é um filtro (<, >, =, etc.)
            invalido = ('<' not in conteudo[0]) and ('<=' not in conteudo[0:2]) and ('>' not in conteudo[0]) and ('>=' not in conteudo[0:2])

            # valida se tem filtro após o primeiro caracter
            if not invalido:
                invalido = ('<' in conteudo[2:]) or ('<=' in conteudo[2:]) or ('>' in conteudo[2:]) or ('>=' in conteudo[2:])

            if invalido:
                raise forms.ValidationError('Expressão inválida.')

    return valor


def InventarioBuscaFormFactory(user):
    """Retorna uma classe para criar formulário de busca de inventários."""
    visualizacao_choices = (
        ('50', '50 inventários'),
        ('100', '100 inventários'),
        ('250', '250 inventários'),
        ('500', '500 inventários'),
        ('1000', '1000 inventários'),
    )

    fields = {}
    fields['numero'] = forms.CharField(
        required=False,
        label='Número',
        help_text='Faixas podem ser definidas com "-"; ex: "1000-1010". Para números diversos, separe por ","; ex: 1000,1005,1010',
    )
    fields['valor'] = forms.CharField(required=False, help_text='Filtros permitidos: "<, <=, >, >="; ex: ">=1000"')
    fields['numero_serie'] = forms.CharField(required=False, label='Número de Série', max_length=50)
    fields['descricao'] = forms.CharField(label='Descrição', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    fields['observacao'] = forms.CharField(label='Observação', required=False, widget=forms.Textarea(attrs={'rows': 3}))
    fields['data_inicial'] = forms.DateFieldPlus(label='Data Inicial', required=False)
    fields['data_final'] = forms.DateFieldPlus(label='Data final', required=False)
    fields['status'] = forms.ModelChoiceField(label='Situação', empty_label='Qualquer', queryset=InventarioStatus.objects.all(), required=False)
    fields['rotulos'] = forms.ModelChoiceField(label='Rótulo', empty_label='Qualquer', queryset=InventarioRotulo.objects.all(), required=False)
    fields['sala'] = forms.ModelChoiceField(
        label='Sala', empty_label='Qualquer', queryset=Sala.ativas, required=False, widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS)
    )
    fields['setor_responsavel'] = forms.ModelChoiceField(label='Setor do Responsável', queryset=Setor.objects, widget=TreeWidget(), required=False)
    fields['recursivo'] = forms.BooleanField(required=False, label='Incluir Sub-setores?')
    fields['fornecedor'] = forms.ModelChoiceField(
        required=False,
        label='Fornecedor da Entrada',
        queryset=PessoaJuridica.objects.all(),
        widget=AutocompleteWidget(search_fields=PessoaJuridica.SEARCH_FIELDS),
    )
    fields['elemento_despesa'] = forms.ModelChoiceField(
        label='Elemento de despesa', required=False, queryset=CategoriaMaterialPermanente.objects.filter(omitir=False), empty_label='Qualquer'
    )

    fields['numero_transferencia'] = forms.IntegerField(label='Número de Transferência', required=False)

    fields['campus_sala'] = forms.ModelChoiceField(
        label='Campus da Sala', empty_label='Qualquer', queryset=UnidadeOrganizacional.objects.suap(), required=False
    )

    fields['estado_conservacao'] = forms.ChoiceField(label='Estado de Conservação', choices=Inventario.CHOICES_CONSERVACAO, required=False)
    fields['ver_sala'] = forms.BooleanField(label='Sala', initial=True, required=False)
    fields['ver_responsavel'] = forms.BooleanField(label='Responsável', initial=True, required=False)
    fields['ver_elemento_despesa'] = forms.BooleanField(label='Elemento de Despesa', initial=True, required=False)
    fields['ver_situacao'] = forms.BooleanField(label='Situação', initial=False, required=False)
    fields['ver_rotulo'] = forms.BooleanField(label='Rótulo', initial=True, required=False)
    fields['ver_numeroserie'] = forms.BooleanField(label='Número de Série', initial=False, required=False)
    fields['ver_estado_conservacao'] = forms.BooleanField(label='Estado de Conservação', initial=True, required=False)
    fields['ver_data_entrada'] = forms.BooleanField(label='Data de Entrada', initial=False, required=False)
    fields['ver_data_carga'] = forms.BooleanField(label='Data de Carga', initial=False, required=False)
    fields['ver_fornecedor'] = forms.BooleanField(label='Fornecedor', initial=False, required=False)
    fields['ver_valor'] = forms.BooleanField(label='Valor Depreciado', initial=False, required=False)
    fields['ver_valor_inicial'] = forms.BooleanField(label='Valor de Aquisição', initial=False, required=False)
    fields['ver_ultima_requisicao'] = forms.BooleanField(label='Última Requisição', initial=False, required=False)
    fields['ver_ultima_conferencia'] = forms.BooleanField(label='Última Conferência', initial=False, required=False)
    fields['ver_observacao'] = forms.BooleanField(label='Observação', initial=False, required=False)
    fields['opcoes_visualizacao'] = forms.ChoiceField(choices=visualizacao_choices, initial='50', label='Visualizacão por página', required=False)

    if user.has_perm('patrimonio.ver_inventarios'):
        fields['responsavel'] = forms.ModelChoiceField(
            label='Responsável',
            queryset=Servidor.objects.vinculados(),
            widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
            required=False,
        )

        # filtro por campus
        fields['campus'] = forms.ModelChoiceField(
            label='Campus da Carga',
            required=False,
            queryset=UnidadeOrganizacional.objects.suap().all(),
            empty_label='Qualquer',
            initial=get_uo(user).id,
        )
        if not user.has_perm('patrimonio.editar_todos'):
            fields['campus'].help_text = 'Editar em lote apenas se campus do inventário for o seu.'

        fieldsets = [
            (
                None,
                {
                    'fields': (
                        ('numero', 'valor'),
                        ('descricao', 'observacao'),
                        ('status', 'campus', 'estado_conservacao'),
                        ('numero_serie', 'elemento_despesa'),
                        'rotulos',
                        ('sala', 'campus_sala'),
                        'responsavel',
                        'setor_responsavel',
                        'numero_transferencia',
                        ('data_inicial', 'data_final', 'recursivo'),
                        'fornecedor',
                    )
                },
            ),
            (
                'Opções de Visualização',
                {
                    'fields': (
                        (
                            'ver_sala',
                            'ver_responsavel',
                            'ver_elemento_despesa',
                            'ver_situacao',
                            'ver_rotulo',
                            'ver_numeroserie',
                            'ver_estado_conservacao',
                            'ver_data_entrada',
                            'ver_data_carga',
                            'ver_fornecedor',
                            'ver_valor',
                            'ver_valor_inicial',
                            'ver_ultima_requisicao',
                            'ver_ultima_conferencia',
                            'ver_observacao',
                        ),
                        ('opcoes_visualizacao'),
                    )
                },
            ),
        ]
    else:
        fields['responsavel'] = forms.ModelChoiceField(
            label='Responsável',
            queryset=Servidor.objects.vinculados(),
            widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
            required=False,
        )
        fieldsets = [
            (None, {'fields': ('numero', ('descricao', 'observacao'), 'responsavel')}),
            (
                'Opções de Visualização',
                {
                    'fields': (
                        (
                            'ver_sala',
                            'ver_responsavel',
                            'ver_elemento_despesa',
                            'ver_situacao',
                            'ver_rotulo',
                            'ver_numeroserie',
                            'ver_estado_conservacao',
                            'ver_data_entrada',
                            'ver_data_carga',
                            'ver_fornecedor',
                            'ver_valor',
                            'ver_valor_inicial',
                            'ver_ultima_requisicao',
                            'ver_observacao',
                        ),
                        ('opcoes_visualizacao'),
                    )
                },
            ),
        ]

    return type(
        'InventarioBuscaForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'clean_numero': inventario_busca_clean_numero,
            'clean_valor': inventario_busca_clean_valor,
            'fieldsets': fieldsets,
            'METHOD': 'GET',
        },
    )


class CargaFiltroForm(forms.FormPlus):
    descricao = forms.CharField(label='Por descrição do item', required=False, widget=forms.TextInput(attrs={'size': 75}))
    numero = forms.IntegerField(label='Por Número', widget=forms.TextInput(), required=False)
    campus = forms.ModelChoiceField(
        label='Por campus da entrada', empty_label='Todos', required=False, queryset=UnidadeOrganizacional.objects.suap().all()
    )

    class Media:
        js = ('/static/patrimonio/js/CargaFiltroForm.js',)


def ServidorCargaFormFactory(user):
    """
    Cria uma classe para construir filtros para a busca de servidores
    com carga.

    """

    class AtivosFuncao(forms.FormPlus):
        METHOD = 'GET'
        ativos = forms.NullBooleanField(label='Ativos', widget=forms.NullBooleanSelect())
        com_funcao = forms.NullBooleanField(label='Com função', widget=forms.NullBooleanSelect())
        unidade_organizacional = forms.ModelChoiceField(
            queryset=UnidadeOrganizacional.objects.suap().all(),
            label='Unidade Organizacional',
            required=True,
            initial=get_uo(user).id,
        )

    return AtivosFuncao


class CautelaForm(forms.ModelFormPlus):
    class Meta:
        model = Cautela
        exclude = ()

    responsavel = forms.ModelChoiceField(
        label='Responsável', queryset=Pessoa.objects.all(), widget=AutocompleteWidget(search_fields=Pessoa.SEARCH_FIELDS)
    )
    data_inicio = forms.DateFieldPlus(label='Data de Início')
    data_fim = forms.DateFieldPlus(label='Data Final')
    descricao = forms.CharField(label='Descrição', required=False, widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['responsavel'] = forms.CharField(label='Responsável')

    def clean_responsavel(self):
        pessoa = self.cleaned_data['responsavel']
        responsavel = str(pessoa)
        return responsavel

    def clean(self):
        if 'data_inicio' not in self.cleaned_data:
            raise forms.ValidationError('Este campo é obrigatório.')

        if 'data_fim' not in self.cleaned_data:
            raise forms.ValidationError('Este campo é obrigatório.')

        if self.cleaned_data['data_inicio'] > self.cleaned_data['data_fim']:
            self._errors['data_inicio'] = ErrorList(['A data de início não pode ser maior que a data final.'])

        return self.cleaned_data


class BaixaForm(forms.ModelFormPlus):
    processo = forms.ModelChoiceField(queryset=Processo.objects.all(), widget=AutocompleteWidget(), required=False)
    uo = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.uo().all(), widget=AutocompleteWidget(), required=True, label='Campus')

    class Meta:
        model = Baixa
        exclude = ()


def BaixaFormFactory(unidade=None, instance=None):
    unidade_organizacional = unidade

    class BaixaForm(forms.FormPlus):
        data = forms.DateTimeFieldPlus(initial=(instance and instance.data) or None)
        observacao = forms.CharField(
            label='Observação', required=False, widget=forms.Textarea, initial=(instance and instance.observacao) or None, max_length=250
        )
        tipo = forms.ModelChoiceField(required=True, queryset=BaixaTipo.objects.all(), empty_label=None, initial=instance and instance.tipo_id)
        uo = forms.ModelChoiceField(
            queryset=UnidadeOrganizacional.objects.uo().all(),
            widget=forms.HiddenInput,
            initial=(instance and instance.uo_id) or (unidade_organizacional and unidade_organizacional.id),
            required=True,
        )
        unidade = forms.CharField(
            required=True,
            widget=forms.TextInput(attrs={'readonly': 'readonly', 'value': (instance and instance.uo) or unidade_organizacional or ''}),
        )
        numero = forms.CharField(label='Nº da Portaria', required=True, max_length=25, initial=(instance and instance.numero) or None)
        processo = forms.ModelChoiceField(
            label='Processo', queryset=Processo.objects.all(), widget=AutocompleteWidget(), initial=instance and instance.processo, required=False
        )

        def clean_numero(self):
            num = self.cleaned_data['numero']
            if instance is None:
                baixas = Baixa.objects.filter(numero=num)
            else:
                baixas = Baixa.objects.exclude(id=instance.id).filter(numero=num)
            if baixas:
                self._errors['numero'] = ErrorList(['Já existe uma baixa com o número escolhido.'])
            return num

    return BaixaForm


def BaixaInventarioFormFactory(user):
    tipo_baixa_choices = (('rotulo', ' Rótulo'), ('inventario', 'Inventário'), ('faixa', 'Faixa de Inventários'))

    fields = {}

    fields['tipo_baixa'] = forms.ChoiceField(widget=forms.RadioSelect, choices=tipo_baixa_choices, initial='rotulo', label='Baixa')

    fields['rotulo'] = forms.ModelChoiceField(label='Rótulo', queryset=InventarioRotulo.objects.all(), empty_label='', required=False)

    fields['inventario'] = forms.MultipleModelChoiceFieldPlus(
        label='Inventário',
        required=False,
        queryset=Inventario.ativos_gerenciaveis,
        help_text='Inventário ativo pertencente a seu campus',
    )

    fields['faixa'] = forms.CharField(
        required=False,
        label='Número',
        help_text='Faixas podem ser definidas com "-"; ex: "1000-1010". Para números diversos, separe por ","; ex: 1000,1005,1010',
    )
    fieldsets = ((None, {'fields': ('tipo_baixa', 'rotulo', 'inventario', 'faixa')}),)

    def clean_rotulo(self):
        if 'tipo_baixa' not in self.cleaned_data:
            raise forms.ValidationError('Este campo é obrigatório.')
        elif self.cleaned_data['tipo_baixa'] == 'rotulo' and not self.cleaned_data['rotulo']:
            raise forms.ValidationError('O campo Rótulo é obrigatório.')
        elif self.cleaned_data['tipo_baixa'] == 'rotulo':
            inventarios = Inventario.objects.filter(rotulos=self.cleaned_data['rotulo']).exclude(status=InventarioStatus.ATIVO())
            if inventarios:
                raise forms.ValidationError('Há inventários neste rótulo que já estão baixados.')
        return self.cleaned_data['rotulo']

    def clean_inventarios(self):
        if 'tipo_baixa' not in self.cleaned_data:
            raise forms.ValidationError('Este campo é obrigatório.')
        elif self.cleaned_data['tipo_baixa'] == 'inventario' and not self.cleaned_data['inventario']:
            raise forms.ValidationError('O campo Inventário é obrigatório.')
        return self.cleaned_data['inventario']

    def clean_faixa(self):
        faixa = self.cleaned_data['faixa']
        if faixa:
            if '-' in faixa:
                limite = faixa.split('-')
                if len(limite) == 2:
                    if not limite[0].strip().isdigit() or not limite[1].strip().isdigit():
                        raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
                else:
                    raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
            elif ',' in faixa:
                limite = faixa.split(',')
                for idx in range(0, len(limite), 1):
                    if not limite[idx].strip().isdigit():
                        raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')
            elif ',' not in faixa:
                if not faixa.strip().isdigit():
                    raise forms.ValidationError('Valor(es) deve(m) ser numérico(s)')

        if '-' in faixa:
            faixa = faixa.split('-')
            a = int(faixa[0])
            b = int(faixa[1])
            if a < b:
                inventarios = Inventario.objects.filter(numero__gte=a, numero__lte=b)
            else:
                inventarios = Inventario.objects.filter(numero__gte=b, numero__lte=a)
        elif ',' in faixa:
            faixa = faixa.split(',')
            inventarios = Inventario.objects.filter(numero__in=faixa)
        else:
            inventarios = Inventario.objects.filter(numero__in=faixa)
        baixados = inventarios.exclude(status=InventarioStatus.ATIVO())
        inventarios = inventarios.exclude(status=InventarioStatus.BAIXADO())
        if baixados:
            raise forms.ValidationError('Não foi encontrado nenhum inventário ativo nesta faixa.')
        return inventarios

    return type(
        'CargaForm',
        (forms.BaseForm,),
        {
            'base_fields': fields,
            'fieldsets': fieldsets,
            'clean_rotulo': clean_rotulo,
            'clean_inventarios': clean_inventarios,
            'clean_faixa': clean_faixa,
            'METHOD': 'POST',
        },
    )


class CautelaInventarioForm(forms.ModelFormPlus):
    class Meta:
        model = CautelaInventario
        fields = ['inventario']

    inventario = forms.ModelChoiceField(label='Inventário', queryset=Inventario.objects, widget=AutocompleteWidget())

    def clean_inventario(self):
        inventario = self.cleaned_data['inventario']
        cautelasinventarios = CautelaInventario.objects.select_related('cautela').filter(inventario=inventario)
        cautela_atual = self.instance.cautela

        for cautelainventario in cautelasinventarios:
            if cautelainventario.cautela.em_andamento(cautela_atual.data_inicio, cautela_atual.data_fim):
                self._errors['inventario'] = ErrorList([f'O inventário {inventario.numero} pertence a uma cautela em andamento.'])

        return self.cleaned_data['inventario']


class RequisicaoInventarioUsoPessoalForm(forms.FormPlus):
    from django.utils.safestring import mark_safe

    confirmacao = forms.BooleanField(
        label=mark_safe('<strong>Confirmação</strong>'),
        help_text='Estou em sala de aula e desejo receber o equipamento a ser adquirido pela instituição.',
        required=False,
    )


class ConferenciaForm(forms.ModelFormPlus):
    class Meta:
        model = ConferenciaSala
        fields = ['sala', 'responsavel']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        user = self.request.user

        self.fields['sala'] = forms.ModelChoiceField(
            label='Sala',
            help_text='Lista apenas salas do campus do usuário logado',
            queryset=Sala.ativas.filter(predio__uo__pk=get_uo(user).id or None),
            widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS),
        )
        self.fields['responsavel'] = forms.ModelChoiceField(
            label='Responsável',
            help_text='Lista apenas servidores do campus do usuário logado',
            queryset=Servidor.objects.ativos().filter(setor__uo__id=get_uo(user).id or None),
            widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        )


class ReavaliacaoInventarioForm(forms.FormPlus):
    inventario = forms.ModelChoiceField(label='Inventário', queryset=Inventario.objects, widget=AutocompleteWidget())
    valor = forms.DecimalFieldAlmoxPlus(label='Valor Reavaliado', help_text='Formato: "9.999,999999" (6 casas decimais)')
    motivo = forms.CharField(label='Motivo', widget=forms.Textarea())

    def clean_valor(self):
        novo_valor = self.cleaned_data['inventario'].valor + self.cleaned_data['valor']
        if novo_valor < self.cleaned_data['inventario'].valor:
            self._errors['valor'] = ErrorList(['O novo valor é menor que o valor atual.'])
        if novo_valor < 0:
            self._errors['valor'] = ErrorList(['O novo valor é menor que 0,00.'])

        return self.cleaned_data['valor']


class AjusteInventarioForm(forms.FormPlus):
    inventario = forms.ModelChoiceField(label='Inventário', queryset=Inventario.objects, widget=AutocompleteWidget())
    valor = forms.DecimalFieldAlmoxPlus(label='Valor do Ajuste', help_text='Formato: "9.999,999999" (6 casas decimais)')
    motivo = forms.CharField(label='Motivo', widget=forms.Textarea())

    def clean_valor(self):
        novo_valor = self.cleaned_data['inventario'].valor - self.cleaned_data['valor']
        if novo_valor > self.cleaned_data['inventario'].valor:
            self._errors['valor'] = ErrorList(['O novo valor é maior que o valor atual.'])
        if novo_valor < 0:
            self._errors['valor'] = ErrorList(['O novo valor é menor que 0,00.'])

        return self.cleaned_data['valor']


class FormInventarioDepreciacao(forms.FormPlus):
    mes_choices = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )
    mes = forms.ChoiceField(label='Mês', choices=mes_choices, required=True)
    ano = forms.IntegerField(required=True, min_value=0)
    inventario = forms.ModelChoiceField(label='Inventário', queryset=Inventario.objects, widget=AutocompleteWidget())

    METHOD = 'GET'

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        valor_depreciavel_inv = InventarioValor.objects.filter(
            inventario=self.cleaned_data['inventario'], data__month=self.cleaned_data['mes'], data__year=self.cleaned_data['ano']
        ).exists()
        if not valor_depreciavel_inv:
            raise forms.ValidationError('Não existe depreciação para este mês/ano para este item.')

        return self.cleaned_data


class FormDepreciacaoPlanoContabil(forms.FormPlus):
    mes_choices = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )
    mes = forms.ChoiceField(label='Mês', choices=mes_choices, required=True)
    ano = forms.IntegerFieldPlus(required=True, widget=forms.TextInput(), max_length=4)
    campus = forms.ModelChoiceField(
        label='Campus da Carga', required=True, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='-------'
    )
    METHOD = 'GET'

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data
        categoria = HistoricoCatDepreciacao.objects.filter(
            mes=self.cleaned_data['mes'], ano=self.cleaned_data['ano'], campus=self.cleaned_data['campus']
        )
        if not categoria:
            raise forms.ValidationError('Não existe depreciação para este mês/ano informado.')

        return self.cleaned_data


class FormDepreciacaoPlanoContabilNovo(forms.FormPlus):
    mes_choices = (
        (1, 'Janeiro'),
        (2, 'Fevereiro'),
        (3, 'Março'),
        (4, 'Abril'),
        (5, 'Maio'),
        (6, 'Junho'),
        (7, 'Julho'),
        (8, 'Agosto'),
        (9, 'Setembro'),
        (10, 'Outubro'),
        (11, 'Novembro'),
        (12, 'Dezembro'),
    )
    mes = forms.ChoiceField(label='Mês', choices=mes_choices, required=True)
    ano = forms.IntegerFieldPlus(required=True, widget=forms.TextInput(), max_length=4)
    campus = forms.ModelChoiceField(
        label='Campus da Carga', required=True, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='-------'
    )
    METHOD = 'GET'

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        categoria = InventarioValor.objects.filter(
            data=datetime.date(
                int(self.cleaned_data['ano']),
                int(self.cleaned_data['mes']),
                calendar.monthrange(int(self.cleaned_data['ano']), int(self.cleaned_data['mes']))[1],
            ),
            uo=self.cleaned_data['campus'],
        )
        if not categoria:
            raise forms.ValidationError('Não existe depreciação para este mês/ano informado.')

        return self.cleaned_data


def get_ext_combo_template(obj):
    data = obj.descricao
    data = (data[:75] + '..') if len(data) > 75 else data
    return f'{obj.numero} - {data}'


class RequisicaoTransferenciaForm(forms.FormPlus):
    servidor_origem = forms.ModelChoiceField(
        label='Servidor de Origem da Carga',
        required=True,
        queryset=Servidor.objects,
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS, readonly=True),
    )
    servidor_destino = forms.ModelChoiceField(
        label='Servidor de Destino da Carga',
        required=True,
        queryset=Inventario.get_servidores_disponivel_transferencia(),
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
    )

    descricao = forms.CharField(label='Descrição', widget=forms.Textarea(), required=False)

    TIPO_TRANSFERENCIA_INVENTARIOS = 'inventarios'
    TIPO_TRANSFERENCIA_CARGA = 'carga'
    TIPO_TRANSFERENCIA_ROTULO = 'rotulo'
    TIPO_TRANSFERENCIA_SALA = 'sala'
    TIPO_TRANSFERENCIA_CHOICES = (
        (TIPO_TRANSFERENCIA_INVENTARIOS, 'Inventários'),
        (TIPO_TRANSFERENCIA_CARGA, 'Toda a carga do servidor de origem'),
        (TIPO_TRANSFERENCIA_ROTULO, 'Rótulos'),
        (TIPO_TRANSFERENCIA_SALA, 'Salas'),
    )

    tipo_transferencia = forms.ChoiceField(
        label='Tipo de Seleção de Itens', required=True, widget=forms.RadioSelect(), choices=TIPO_TRANSFERENCIA_CHOICES
    )
    inventarios = forms.MultipleModelChoiceFieldPlus(
        label='Inventários',
        help_text='Para buscar, digite parte do número de tombo do inventário',
        required=False,
        queryset=Inventario.ativos,
        widget=AutocompleteWidget(
            search_fields=Inventario.SEARCH_FIELDS,
            multiple=True,
            url='/patrimonio/filtra_inventario_transferencia/',
            form_filters=[('servidor_origem', 'servidor_origem')],
            ext_combo_template=get_ext_combo_template,
        ),
    )

    rotulo = forms.ModelChoiceField(label='Rótulo', empty_label='Qualquer', queryset=InventarioRotulo.objects.all(), required=False)

    sala = forms.ModelChoiceField(
        required=False, queryset=Sala.ativas.order_by('predio__uo'), widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS)
    )

    nao_incluir_baixado = forms.BooleanField(label='Não incluir inventários baixados na requisição da carga?', required=False)

    class Media:
        js = ('/static/patrimonio/js/RequisitarTransferenciaForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.has_perm('patrimonio.pode_requisitar_transferencia_do_campus'):
            uo = get_uo(self.request.user)
            self.fields['servidor_origem'] = forms.ModelChoiceField(
                label='Servidor de Origem da Carga',
                required=True,
                queryset=Inventario.get_servidores_com_carga_do_meu_campus(uo),
                widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
            )

            self.fields['inventarios'].queryset = Inventario.ativos.exclude(
                requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            )
        else:
            self.fields['inventarios'].queryset = Inventario.ativos.filter(responsavel_vinculo=self.request.user.get_vinculo()).exclude(
                requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
            )

            self.fields['servidor_origem'].initial = self.request.user.get_relacionamento().id

        self.fields['rotulo'].queryset = InventarioRotulo.objects.filter(unidade_organizacional=get_uo(self.request.user))

        if not Configuracao.get_valor_por_chave('patrimonio', 'permitir_req_transferencia_sem_inventario_baixado'):
            nao_incluir_baixado = self.fields['nao_incluir_baixado']
            nao_incluir_baixado.widget = nao_incluir_baixado.hidden_widget()

    def clean(self):
        cleaned_data = super().clean()

        if self.errors:
            return cleaned_data

        inventarios = cleaned_data.get('inventarios')
        servidor_origem = cleaned_data.get('servidor_origem')
        tipo_transferencia = cleaned_data.get('tipo_transferencia')
        nao_incluir_baixado = cleaned_data.get('nao_incluir_baixado')

        if (
            not self.request.user.has_perm('patrimonio.pode_requisitar_transferencia_do_campus')
            and servidor_origem.id != self.request.user.get_relacionamento().id
        ):
            self.add_error('servidor_origem', 'Você deve ser o servidor de origem.')

        if tipo_transferencia == self.TIPO_TRANSFERENCIA_CARGA:
            inventarios = (
                servidor_origem.get_vinculo()
                .inventario_set.all()
                .exclude(requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)
            )
            if Configuracao.get_valor_por_chave('patrimonio', 'permitir_req_transferencia_sem_inventario_baixado') and nao_incluir_baixado:
                inventarios = inventarios.exclude(status_id=InventarioStatus.BAIXADO())
            self.cleaned_data['inventarios'] = inventarios

            if not self.cleaned_data['inventarios'].exists():
                self.add_error('tipo_transferencia', 'Nenhum inventário passível de transferência.')

        elif tipo_transferencia == self.TIPO_TRANSFERENCIA_INVENTARIOS and not inventarios.exists():
            self.add_error('inventarios', 'Pelo menos um inventário deve ser adicionado.')

        elif tipo_transferencia == self.TIPO_TRANSFERENCIA_INVENTARIOS:
            if not servidor_origem.get_vinculo().inventario_set.exists():
                self.add_error('servidor_origem', 'O servidor de origem não tem nenhum inventário em sua carga.')

            # Os bens devem estar na carga do servidor de origem
            if inventarios.exclude(responsavel_vinculo_id=servidor_origem.get_vinculo()).exists():
                self.add_error('inventarios', 'Pelo menos um dos itens não pertence ao servidor de origem. Por favor verifique e ajuste os itens.')

        elif tipo_transferencia == self.TIPO_TRANSFERENCIA_ROTULO:
            if self.cleaned_data['rotulo'] is None:
                self.add_error('rotulo', 'Informe um rótulo.')
            else:
                rotulo = cleaned_data.get('rotulo')

                inventarios = (
                    servidor_origem.get_vinculo()
                    .inventario_set.filter(rotulos=rotulo)
                    .exclude(requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)
                )
                self.cleaned_data['inventarios'] = inventarios

                if not self.cleaned_data['inventarios'].exists():
                    self.add_error('rotulo', 'Nenhum inventário passível de transferência neste rótulo.')
        elif tipo_transferencia == self.TIPO_TRANSFERENCIA_SALA:
            if self.cleaned_data['sala'] is None:
                self.add_error('sala', 'Escolha uma sala.')
            else:
                sala = cleaned_data.get('sala')

                inventarios = (
                    servidor_origem.get_vinculo()
                    .inventario_set.filter(sala=sala)
                    .exclude(requisicaoitem__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO)
                )
                self.cleaned_data['inventarios'] = inventarios

                if not self.cleaned_data['inventarios'].exists():
                    self.add_error('sala', 'Nenhum inventário passível de transferência nesta sala.')
        # Os bens não podem está em outras requisições abertas;
        # A alteração da carga contábil só será possível caso o bem não esteja participando de nenhuma requisição aberta;
        if Requisicao.get_qs_aguardando().filter(itens__inventario__in=inventarios).exists():
            self.add_error(
                'inventarios', 'Pelo menos um dos itens já está presente em outra requisição pendente. Por favor verifique e ajuste os itens.'
            )

        if self.cleaned_data.get('inventarios'):
            inventarios = self.cleaned_data.get('inventarios')
            campi = set()
            for inventario in inventarios:
                campi.add(inventario.carga_contabil.campus)
        return cleaned_data

    @transaction.atomic()
    def save(self):
        descricao = self.cleaned_data['descricao']
        inventarios = self.cleaned_data['inventarios']
        servidor_destino = self.cleaned_data['servidor_destino']
        status = Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        Requisicao.criar_por_agrupamento(
            inventarios,
            servidor_destino,
            self.request.user,
            status,
            descricao,
            inconsistencia=False,
        )


class IndeferirRequisicaoForm(forms.ModelFormPlus):
    observacao = forms.CharField(label='Motivo do Indeferimento', required=True, widget=forms.Textarea)

    class Meta:
        model = Requisicao
        fields = ('observacao',)

    def save(self):
        self.instance.indeferir_requisicao(self.request.user)


class DeferirRequisicaoForm(forms.ModelFormPlus):
    sala = forms.ModelChoiceFieldPlus(
        queryset=Sala.ativas,
        widget=AutocompleteWidget(search_fields=Sala.SEARCH_FIELDS),
        required=False,
        help_text='Para manter os inventários nas salas de origem, deixe este campo em branco.',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campi = UnidadeOrganizacional.objects.suap().filter(id=get_uo().id)
        self.fields['sala'].queryset = Sala.ativas.filter(predio__uo__in=campi)

    class Meta:
        model = Requisicao
        fields = ()

    def clean(self):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        requisicao = self.instance
        vinculo_origem_id = requisicao.vinculo_origem_id
        if vinculo_origem_id:
            for item in requisicao.itens.all():
                if item.inventario.get_carga_atual() is not None:
                    if not item.inventario.get_carga_atual().id == vinculo_origem_id:
                        raise ValidationError('Há inventários com cargas diferentes do servidor de origem.')
        return cleaned_data


def RequisicaoTransferenciaColetorFormFactory(request):
    fields = {}
    fields['servidor_destino'] = forms.ModelChoiceField(
        label='Servidor de Destino',
        queryset=Inventario.get_servidores_disponivel_transferencia(),
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        required=True,
    )
    fields['descricao'] = forms.CharField(label='Descrição', widget=forms.Textarea(), required=False)

    fields['inventarios'] = forms.ModelMultipleChoiceField(queryset=Inventario.objects, widget=forms.CheckboxSelectMultiplePlus())

    def __init__(self, *args, **kwargs):
        super(RequisicaoTransferenciaColetorFormFactory, self).__init__(*args, **kwargs)

    def clean(self):
        if not self.errors:
            if self.cleaned_data.get('inventarios'):
                inventarios = self.cleaned_data.get('inventarios')
                if Requisicao.get_qs_aguardando().filter(itens__inventario__in=inventarios).exists():
                    self.add_error('inventarios', 'Há inventários presentes em requisições pendentes. Por favor, verifique.')
                campi = set()
                for inventario in inventarios:
                    campi.add(inventario.carga_contabil.campus)
        return self.cleaned_data

    @transaction.atomic()
    def save(self):
        inventarios = self.cleaned_data['inventarios']
        descricao = self.cleaned_data['descricao']
        servidor_destino = self.cleaned_data['servidor_destino']
        status = Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        Requisicao.criar_por_agrupamento(
            inventarios,
            servidor_destino,
            self.request.user,
            status,
            descricao,
            inconsistencia=False,
        )

    return type('CargaForm', (forms.BaseForm,), {'base_fields': fields, 'request': request, 'clean': clean, 'save': save, 'METHOD': 'POST'})


class InformarPAOrigemForm(forms.ModelFormPlus):
    numero_pa_origem = utils.NumeroPAField(label='Número PA Campus Origem', required=True, max_length=14)

    class Meta:
        model = Requisicao
        fields = ()

    def clean_numero(self):
        return self.cleaned_data['numero_pa_origem'].strip().upper()

    def save(self):
        self.instance.informarpa_origem_requisicao(self.request.user, self.cleaned_data['numero_pa_origem'])


class InformarPADestinoForm(forms.ModelFormPlus):
    numero_pa_destino = utils.NumeroPAField(label='Número PA Campus Destino', required=True, max_length=14)

    class Meta:
        model = Requisicao
        fields = ()

    def clean_numero(self):
        return self.cleaned_data['numero_pa_destino'].strip().upper()

    def save(self):
        self.instance.informarpa_destino_requisicao(self.request.user, self.cleaned_data['numero_pa_destino'])


class EdicaoPAOrigemForm(forms.ModelFormPlus):
    numero_pa_origem = utils.NumeroPAField(label='Número PA Campus Origem', required=True, max_length=14)

    class Meta:
        model = Requisicao
        fields = ()

    def clean_numero(self):
        return self.cleaned_data['numero_pa_origem'].strip().upper()

    def __init__(self, *args, **kwargs):
        if 'requisicao' in kwargs:
            requisicao = kwargs.pop('requisicao')
            super().__init__(*args, **kwargs)
            numero_pa_origem = Requisicao.objects.get(pk=requisicao.id).numero_pa_origem
            self.fields['numero_pa_origem'].initial = numero_pa_origem


class EdicaoPADestinoForm(forms.ModelFormPlus):
    numero_pa_destino = utils.NumeroPAField(label='Número PA Campus Destino', required=True, max_length=14)

    class Meta:
        model = Requisicao
        fields = ()

    def clean_numero(self):
        return self.cleaned_data['numero_pa_destino'].strip().upper()

    def __init__(self, *args, **kwargs):
        if 'requisicao' in kwargs:
            requisicao = kwargs.pop('requisicao')
            super().__init__(*args, **kwargs)
            numero_pa_destino = Requisicao.objects.get(pk=requisicao.id).numero_pa_destino
            self.fields['numero_pa_destino'].initial = numero_pa_destino


class AvaliarInventariosForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Aprovar apenas selecionados'

    itens = forms.MultipleModelChoiceField(
        RequisicaoItem.objects, label='Selecionar inventários', widget=RenderableCheckboxSelect('widgets/item_widget.html'), required=False
    )

    class Meta:
        model = Requisicao
        fields = ()

    @transaction.atomic()
    def save(self):
        for item in self.fields['itens'].queryset.all():
            if item in self.cleaned_data['itens']:
                item.situacao = RequisicaoItem.APROVADO
            else:
                item.situacao = RequisicaoItem.REJEITADO

            item.data_avaliacao = datetime.datetime.now()
            item.avaliador = self.request.user
            item.save()


class PlanoContasForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoContas
        exclude = ('data_desativacao',)


class CategoriaMaterialForm(forms.ModelFormPlus):
    class Meta:
        model = CategoriaMaterialPermanente
        exclude = ()


class CampusFiltroInconsistenteForm(forms.Form):
    campus = forms.ModelChoiceField(label='Unid. Administrativa', queryset=UnidadeOrganizacional.objects.suap().all(), required=False)

    servidor = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects.all(), widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS), required=False
    )


def InconsistenciaFormFactory(request):
    fields = {}
    fields['servidor_destino'] = forms.ModelChoiceField(
        label='Servidor Destino',
        queryset=Inventario.get_servidores_disponivel_transferencia(),
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS),
        required=True,
    )
    fields['descricao'] = forms.CharField(label='Descrição', widget=forms.Textarea(), required=False)

    fields['inventarios'] = forms.ModelMultipleChoiceField(queryset=Inventario.objects, widget=forms.CheckboxSelectMultiplePlus())

    def __init__(self, *args, **kwargs):
        super(InconsistenciaFormFactory, self).__init__(*args, **kwargs)

        self.fields['inventarios'].queryset = Inventario.ativos.exclude(
            requisicaoitens__requisicao__status=Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        )

    def clean(self):
        if not self.errors:
            if self.cleaned_data.get('inventarios'):
                inventarios = self.cleaned_data.get('inventarios')
                campi = set()
                for inventario in inventarios:
                    campi.add(inventario.carga_contabil.campus)

        return self.cleaned_data

    @transaction.atomic()
    def save(self):
        inventarios = self.cleaned_data['inventarios']
        descricao = self.cleaned_data['descricao']
        servidor_destino = self.cleaned_data['servidor_destino']
        status = Requisicao.STATUS_AGUARDANDO_APROVACAO_SERVIDOR_DESTINO
        Requisicao.criar_por_agrupamento(
            inventarios,
            servidor_destino,
            self.request.user,
            status,
            descricao,
            inconsistencia=True,
        )

    return type('CargaForm', (forms.BaseForm,), {'base_fields': fields, 'request': request, 'clean': clean, 'save': save, 'METHOD': 'POST'})


class FiltroInventariosNaoConferidosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Filtrar'
    METHOD = 'GET'
    QTD_RESULTADOS_CHOICES = (
        (50, '50 inventários'),
        (100, '100 inventários'),
        (200, '200 inventários'),
    )
    campus = forms.ModelChoiceFieldPlus(queryset=UnidadeOrganizacional.objects.suap(), required=False)
    data_inicial = forms.DateFieldPlus(label='Data inicial da conferência', required=False)
    data_final = forms.DateFieldPlus(label='Data final da conferência', required=False)
    resultados_por_pagina = forms.ChoiceField(label='Resultados por página', choices=QTD_RESULTADOS_CHOICES, initial=50, required=False)


class ConfiguracaoForm(forms.FormPlus):
    data_inicio_depreciacao = forms.DateFieldPlus(label='Data Início da Depreciação', required=False)
    dia_inicio_bloqueio = forms.CharFieldPlus(label='Início da Data Mensal de Bloqueio Deferimento da Requisição', required=False)
    permitir_edicao_tombo = forms.BooleanField(label='Permitir Edição do Número de Inventário', required=False)
    permitir_req_transferencia_sem_inventario_baixado = forms.BooleanField(
        label='Permitir Requisições de Transferências por Carga de Origem sem Inventários Baixados', required=False
    )
    apk_suap_inventario = forms.FileFieldPlus(label='APK do app SUAP Inventário', required=False)


class MigracaoInventarioForm(forms.FormPlus):
    """
    Envio da planilha de migração de inventários.

    Não pede campus: cada linha da planilha informa o seu. Sem `SUBMIT_LABEL` porque quem monta o
    formulário é o template `migracao.html`, que precisa da conferência dentro da tag `<form>`.
    """

    arquivo = forms.FileFieldPlus(
        label='Planilha',
        required=True,
        filetypes=['xlsx', 'xls', 'csv'],
        help_text='Baixe a planilha modelo para garantir o cabeçalho correto.',
    )
    processo = forms.ModelChoiceField(
        label='Processo',
        queryset=Processo.objects.all(),
        widget=AutocompleteWidget(),
        required=True,
    )

    def clean_arquivo(self):
        """Recusa desde já um arquivo que o migrador não consegue abrir."""
        arquivo = self.cleaned_data['arquivo']
        migrador.ler_planilha(arquivo)
        return arquivo
