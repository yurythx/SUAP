from datetime import date
from decimal import Decimal

from django.db import transaction
from django.db.models import Q, Sum

from almoxarifado import utils
from almoxarifado.models import (
    CategoriaMaterialConsumo,
    DevolucaoMaterial,
    Empenho,
    EmpenhoConsumo,
    Entrada,
    EntradaTipo,
    LicitacaoTipo,
    MaterialConsumo,
    MaterialEstoque,
    MaterialTipo,
    MovimentoAlmoxEntrada,
    MovimentoAlmoxEntradaTipo,
    PlanoContasAlmox,
    calcula_valor_medio_atual,
)
from comum.models import Vinculo
from comum.utils import get_uo, tl
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, TreeWidget
from djtools.templatetags.filters import in_group
from djtools.utils import user_has_one_of_perms
from patrimonio.models import CategoriaMaterialPermanente, EmpenhoPermanente, EntradaPermanente
from protocolo.models import Processo
from rh.models import Setor, UnidadeOrganizacional


def BalanceteEDDetalhadoFormFactory(usuario):
    """
    Cria um formulário dinâmico para obter um relatório do balancete de Elemento de Despesa detalhado.
    """
    fields = {}
    fields['elemento_de_despesa'] = forms.ModelChoiceField(queryset=CategoriaMaterialConsumo.objects.all())
    fields['data_inicial'] = forms.DateFieldPlus()
    fields['data_final'] = forms.DateFieldPlus()
    fields['estoque'] = forms.BooleanField(required=False, label='Apenas em estoque')

    # Restrição de campos no formulário com base na permissão do usuário.
    if usuario.has_perm('almoxarifado.pode_ver_relatorios_todos'):
        fields['uo'] = forms.ModelChoiceField(
            required=False, label='Unidade Organizacional', queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Todos'
        )
    else:
        fields['uo'] = forms.ModelChoiceField(
            label='Unidade Organizacional', empty_label=None, queryset=UnidadeOrganizacional.objects.suap().filter(pk=get_uo().pk)
        )

    def clean(self):
        msg = {'erro': 'Informe um valor válido.'}
        if not self.errors:
            if self.cleaned_data['data_inicial']:
                if self.cleaned_data['data_inicial'] > date.today():
                    self.errors['data_inicial'] = [msg['erro']]
                if self.cleaned_data['data_final'] is None:
                    self.errors['data_final'] = [msg['erro']]
                if self.cleaned_data['data_final']:
                    if self.cleaned_data['data_final'] > date.today() or self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
                        self.errors['data_final'] = [msg['erro']]
            elif self.cleaned_data['data_final']:
                self.errors['data_inicial'] = [msg['erro']]
                if self.cleaned_data['data_final'] > date.today():
                    self.errors['data_final'] = [msg['erro']]

        return self.cleaned_data

    fieldsets = ((None, {'fields': ('uo', 'elemento_de_despesa', 'data_inicial', 'data_final', 'estoque')}),)

    return type('BalanceteEDDetalhadoForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'POST', 'clean': clean})


###################
# Saida por Setor #
###################


class ConsumoSetorForm(forms.FormPlus):
    setor = forms.ModelChoiceField(queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=False)
    incluir = forms.BooleanField(required=False, label='Incluir Subsetores:')
    data_inicial = forms.DateFieldPlus()
    data_final = forms.DateFieldPlus()
    opcao_exibir = forms.ChoiceField(
        widget=forms.RadioSelect(), choices=(('saidas', 'Todas as Saídas'), ('materiais', 'Agrupar por Material'), ('totais', 'Valores Totais'))
    )

    def clean(self):
        msg = {'erro': 'Informe um valor válido.'}
        if not self.errors:
            if self.cleaned_data['data_inicial']:
                if self.cleaned_data['data_inicial'] > date.today():
                    self.errors['data_inicial'] = [msg['erro']]
                if self.cleaned_data['data_final'] is None:
                    self.errors['data_final'] = [msg['erro']]
                if self.cleaned_data['data_final']:
                    if self.cleaned_data['data_final'] > date.today() or self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
                        self.errors['data_final'] = [msg['erro']]
            elif self.cleaned_data['data_final']:
                self.errors['data_inicial'] = [msg['erro']]
                if self.cleaned_data['data_final'] > date.today():
                    self.errors['data_final'] = [msg['erro']]
        return self.cleaned_data


def RequisicaoBuscaFormFactory(user):
    """
    Cria uma classe para o formulário de busca de requisições de material de consumo.
    """
    fields = {
        'id': forms.IntegerField(label='ID', required=False),
        'setor': forms.ModelChoiceField(label='Setor Solicitante', queryset=Setor.objects.suap_ativos().all(), widget=TreeWidget(), required=False),
        'recursivo': forms.BooleanField(required=False, label='Incluir Subsetores?'),
        'data_inicial': forms.DateFieldPlus(required=False),
        'data_final': forms.DateFieldPlus(required=False),
        'vinculo_solicitante': forms.ModelChoiceField(
            queryset=Vinculo.objects, widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), required=False
        ),
        'material': forms.ModelChoiceField(queryset=MaterialConsumo.objects.all(), widget=AutocompleteWidget(), required=False),
        'tipo': forms.ChoiceField(
            required=True,
            choices=(('usuario', 'Saída de material para consumo'), ('uo', 'Transferência de material entre campi')),
            widget=forms.Select,
            label='Tipo de Requisição',
        ),
    }

    fieldsets = ((None, {'fields': ('id', 'setor', 'recursivo', ('data_inicial', 'data_final'), 'vinculo_solicitante', 'material', 'tipo')}),)

    if user_has_one_of_perms(user, ['almoxarifado.pode_ver_todas_requisicoes_usuario', 'almoxarifado.pode_ver_todas_requisicoes_uo']):
        fields['campus_fornecedor'] = forms.ModelChoiceField(
            queryset=UnidadeOrganizacional.objects.suap().all(), required=False, label='Campus Fornecedor'
        )
        fieldsets = (
            (
                None,
                {
                    'fields': (
                        'id',
                        'setor',
                        'recursivo',
                        'campus_fornecedor',
                        ('data_inicial', 'data_final'),
                        'vinculo_solicitante',
                        'material',
                        'tipo',
                    )
                },
            ),
        )

    def clean(self):
        msg = {'erro': 'Informe um valor válido.'}
        if not self.errors:
            if self.cleaned_data['data_inicial']:
                if self.cleaned_data['data_inicial'] > date.today():
                    self.errors['data_inicial'] = [msg['erro']]
            if self.cleaned_data['data_final']:
                if self.cleaned_data['data_final'] > date.today():
                    self.errors['data_final'] = [msg['erro']]
        return self.cleaned_data

    return type('RequisicaoBuscaForm', (forms.BaseForm,), {'base_fields': fields, 'clean': clean, 'fieldsets': fieldsets, 'METHOD': 'GET'})


#####################
#   relatório ED    #
#####################


def GetBalanceteEdForm(request):
    # Formulário comum
    class BalanceteEdForm(forms.FormPlus):
        faixa = forms.BRDateRangeField()
        uos = forms.ModelChoiceField(
            label='Unidade Organizacional', empty_label=None, queryset=UnidadeOrganizacional.objects.suap().filter(pk=get_uo().pk)
        )

    # Formulário para gerentes sistêmicos
    class BalanceteEdFormGerenteSistemico(BalanceteEdForm):
        uos = forms.ModelChoiceField(
            label='Unidade Organizacional', empty_label='Todas', queryset=UnidadeOrganizacional.objects.suap().all(), required=False
        )

    if in_group(request.user, ['Coordenador de Almoxarifado Sistêmico', 'Auditor']):
        return BalanceteEdFormGerenteSistemico
    else:
        return BalanceteEdForm


def BalanceteMaterialFormFactory(usuario):
    """
    Função que cria um formulário dinâmico para obter o relatório
    de balancete de material de consumo.
    """
    fields = {}
    fields['faixa'] = forms.BRDateRangeField()

    # Restrição de escolha de campi baseado na permissão do usuário.
    if usuario.has_perm('almoxarifado.pode_ver_relatorios_todos'):
        fields['uos'] = forms.ModelChoiceField(
            label='Unidade Organizacional', empty_label='Todas', queryset=UnidadeOrganizacional.objects.suap().all(), required=False
        )
    else:
        fields['uos'] = forms.ModelChoiceField(
            label='Unidade Organizacional', empty_label=None, queryset=UnidadeOrganizacional.objects.suap().filter(pk=get_uo().pk)
        )

    fields['estoque'] = forms.BooleanField(label='Mostrar apenas itens com estoque movimentados', required=False)

    fieldsets = ((None, {'fields': ('faixa', 'uos', 'estoque')}),)

    return type('BalanceteMaterialForm', (forms.BaseForm,), {'base_fields': fields, 'fieldsets': fieldsets, 'METHOD': 'POST'})


class ConfiguracaoEstoqueForm(forms.FormPlus):
    uo = forms.ModelChoiceField(
        required=True,
        queryset=UnidadeOrganizacional.objects.suap().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        help_text='',
    )
    material = forms.ModelChoiceField(
        required=False,
        queryset=MaterialConsumo.objects.all(),
        widget=AutocompleteWidget(),
        help_text='Esse campo não necessita ser preechido caso você opte por preencher o campo categoria para inserir todos os materiais de um determinado elemento de despesa.',
    )
    categoria = forms.ModelChoiceField(
        required=False,
        queryset=CategoriaMaterialConsumo.objects.all(),
        widget=AutocompleteWidget(search_fields=CategoriaMaterialConsumo.SEARCH_FIELDS),
        help_text='Esse campo é opcional. Se você preenchê-lo, todos os materiais dessa categoria serão colocados no controle.',
    )
    tempo_aquisicao = forms.IntegerField(
        label='Tempo de Aquisição', required=True, help_text='Número de meses que o material leva para chegar, depois de adquirido.'
    )
    intervalo_aquisicao = forms.IntegerField(label='Intervalo de Aquisição', required=True, help_text='Número de meses entre uma aquisição e outra.')


class RelatorioSaldoAtualEDForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        label='Unid. Administrativa',
        required=False,
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}),
    )


def NotasFornecimentoFormFactory(usuario):
    """
    Cria uma classe para o formulário de busca de itens solicitados por pessoa dentro de um periodo.
    """
    fields = {
        'vinculo_solicitante': forms.ModelChoiceField(
            queryset=Vinculo.objects.all(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), label='Solicitante'
        ),
        'data_inicial': forms.DateFieldPlus(),
        'data_final': forms.DateFieldPlus(),
    }

    fieldsets = ((None, {'fields': ('vinculo_solicitante', 'data_inicial', 'data_final')}),)

    def clean(self):
        msg = {'erro1': 'A data inicial de ser maior que hoje.', 'erro2': 'A data final deve ser maior que hoje.'}
        if not self.errors:
            if self.cleaned_data['data_inicial']:
                if self.cleaned_data['data_inicial'] > date.today():
                    self.errors['data_inicial'] = [msg['erro1']]
            if self.cleaned_data['data_final']:
                if self.cleaned_data['data_final'] > date.today():
                    self.errors['data_final'] = [msg['erro2']]
        return self.cleaned_data

    return type('NotasFornecimentoForm', (forms.BaseForm,), {'base_fields': fields, 'clean': clean, 'fieldsets': fieldsets, 'METHOD': 'GET'})


class MaterialConsumoForm(forms.ModelFormPlus):
    class Meta:
        model = MaterialConsumo
        exclude = ()

    def clean_nome(self):
        if '|' in self.cleaned_data['nome']:
            raise forms.ValidationError('O nome não aceita o caracter "|".')
        if len(self.cleaned_data['nome']) > 1024:
            raise forms.ValidationError('O nome excede o limite de 1024 caracteres.')
        materiais = MaterialConsumo.objects.filter(nome=self.cleaned_data['nome'])
        if materiais:
            if self.instance.id:  # editando
                if materiais[0].id != self.instance.id:
                    raise forms.ValidationError('Já existe item com este nome.')
            else:
                raise forms.ValidationError('Já existe item com este nome.')
        return self.cleaned_data['nome']


class CategoriaMaterialConsumoForm(forms.ModelFormPlus):
    class Meta:
        model = CategoriaMaterialConsumo
        exclude = ()

    def clean_nome(self):
        # TODO: extrair esse tratamento para um método
        categorias = CategoriaMaterialConsumo.objects.filter(nome=self.cleaned_data['nome'])
        if categorias:
            if self.instance.id:  # editando
                if categorias[0].id != self.instance.id:
                    raise forms.ValidationError('Já existe item com este nome.')
            else:
                raise forms.ValidationError('Já existe item com este nome.')
        return self.cleaned_data['nome']


###########
# Empenho #
###########


class EmpenhoForm(forms.ModelFormPlus):
    TIPO_PESSOA_FISICA = 'pessoa_fisica'
    TIPO_PESSOA_JURIDICA = 'pessoa_juridica'
    TIPO_FORNECEDOR_CHOICES = ((TIPO_PESSOA_FISICA, 'Pessoa Física'), (TIPO_PESSOA_JURIDICA, 'Pessoa Jurídica'))
    tipo_pessoa = forms.ChoiceField(choices=TIPO_FORNECEDOR_CHOICES, required=True, widget=forms.RadioSelect(), label='Tipo de Fornecedor')
    uo = forms.ModelChoiceField(
        label='UG Emitente',
        required=False,
        queryset=UnidadeOrganizacional.objects.suap().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
    )
    pessoa_fisica = forms.ModelChoiceField(
        queryset=Vinculo.objects.pessoas_fisicas() | Vinculo.objects.pessoas_externas(),
        required=False,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Pessoa Física',
    )
    pessoa_juridica = forms.ModelChoiceField(
        queryset=Vinculo.objects.pessoas_juridicas(),
        required=False,
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
        label='Pessoa Jurídica',
    )
    processo = forms.ModelChoiceField(
        queryset=Processo.objects.all(), widget=AutocompleteWidget(), help_text='Processo desta instituição relativo a este empenho'
    )
    data_recebimento_empenho = forms.DateFieldPlus(
        label='Data de recebimento', required=False, help_text='Data que o fornecedor recebeu o empenho para efeito de cálculo do status da entrega.'
    )
    numero = utils.NumEmpenhoField(label='Número de empenho', required=True, max_length=14)

    class Meta:
        model = Empenho
        fields = [
            'uo',
            'numero',
            'processo',
            'tipo_pessoa',
            'pessoa_fisica',
            'pessoa_juridica',
            'tipo_licitacao',
            'numero_pregao',
            'data_recebimento_empenho',
            'prazo',
            'tipo_material',
            'observacao',
        ]

    class Media:
        js = ('/static/almoxarifado/js/EmpenhoForm.js',)

    def clean_numero(self):
        return self.cleaned_data['numero'].strip().upper()

    def clean_tipo_material(self):
        # Só pode alterar o tipo de material quando o empenho não tem itens
        if self.instance.pk and self.instance.get_itens().count():
            tipo_material_atual = Empenho.objects.get(pk=self.instance.pk).tipo_material
            if self.cleaned_data['tipo_material'] != tipo_material_atual:
                msg = 'O tipo de material não pode ser modificado, pois o empenho já teve itens adicionados.'
                raise forms.ValidationError(msg)
        return self.cleaned_data['tipo_material']

    def clean(self):
        cleaned_data = super().clean()

        tipo_pessoa = cleaned_data.get('tipo_pessoa')
        pessoa_fisica = cleaned_data.get('pessoa_fisica')
        pessoa_juridica = cleaned_data.get('pessoa_juridica')

        if tipo_pessoa == self.TIPO_PESSOA_FISICA and not pessoa_fisica:
            self.add_error('pessoa_fisica', 'Este campo é obrigatório.')
        elif tipo_pessoa == self.TIPO_PESSOA_JURIDICA and not pessoa_juridica:
            self.add_error('pessoa_juridica', 'Este campo é obrigatório.')
        return cleaned_data

    def save(self, *args, **kwargs):
        tipo_pessoa = self.cleaned_data['tipo_pessoa']
        self.instance.vinculo_fornecedor = self.cleaned_data[tipo_pessoa]
        return super().save(*args, **kwargs)


class EmpenhoConsumoForm(forms.ModelFormPlus):
    qtd_empenhada = forms.DecimalField(
        min_value=Decimal('0.00001'), max_digits=15, decimal_places=5, label='Qtd. Empenhada', help_text='Aceita até 5 casas decimais'
    )
    material = forms.ModelChoiceField(queryset=MaterialConsumo.objects.all(), widget=AutocompleteWidget())
    valor = forms.DecimalFieldAlmoxPlus(label='Valor Unitário', help_text='Formato: "9.999,999999" (6 casas decimais)')
    continuar_cadastrando = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = EmpenhoConsumo
        fields = ['material', 'qtd_empenhada', 'valor']

    def clean_material(self):
        if self.instance.pk and self.instance.material != self.cleaned_data['material'] and self.instance.qtd_adquirida:
            raise forms.ValidationError('O item não pode ser modificado porque já foi movimentado')

        return self.cleaned_data['material']

    def clean_valor(self):
        if self.instance.pk and self.instance.valor != self.cleaned_data['valor'] and self.instance.qtd_adquirida:
            raise forms.ValidationError('O item não pode ser modificado porque já foi movimentado')

        return self.cleaned_data['valor']

    def clean_qtd_empenhada(self):
        if self.instance.pk and self.instance.qtd_adquirida > self.cleaned_data['qtd_empenhada']:
            msg = 'A quantidade empenhada não pode ser inferior à já adquirida'
            raise forms.ValidationError(msg)

        return self.cleaned_data['qtd_empenhada']

    def clean(self):
        # Não permitir empenhar itens com descrição, catetoria e valor iguais.
        # unique_together = ('empenho', 'material', 'valor') não funcionou!
        super().clean()
        if not self.errors:
            if (
                self.instance.empenho.empenhoconsumo_set.filter(material=self.cleaned_data['material'], valor=self.cleaned_data['valor'])
                .exclude(id=self.instance.pk)
                .count()
            ):
                msg = 'Já foi empenhado um item com material e valor iguais.'
                raise forms.ValidationError(msg)
        return self.cleaned_data


class EmpenhoPermanenteForm(forms.ModelFormPlus):
    categoria = forms.ModelChoiceField(queryset=CategoriaMaterialPermanente.objects.filter(omitir=False).order_by('codigo'))
    qtd_empenhada = forms.IntegerField(
        min_value=1, label='Qtd. empenhada', help_text='Somente números inteiros: material permanente é contado por unidade tombada'
    )
    valor = forms.DecimalFieldAlmoxPlus(label='Valor Unitário', help_text='Formato: "9.999,999999" (6 casas decimais)')
    continuar_cadastrando = forms.BooleanField(required=False, initial=True)

    class Meta:
        model = EmpenhoPermanente
        fields = ['categoria', 'descricao', 'qtd_empenhada', 'valor']

    def clean_qtd_empenhada(self):
        if self.instance.pk and self.instance.qtd_adquirida > self.cleaned_data['qtd_empenhada']:
            msg = f'A quantidade empenhada não pode ser inferior à já adquirida ({self.instance.qtd_adquirida}).'
            raise forms.ValidationError(msg)

        return self.cleaned_data['qtd_empenhada']

    def clean_categoria(self):
        if not tl.get_user().groups.filter(name='Contador Administrador'):
            if self.instance.pk and self.instance.categoria != self.cleaned_data['categoria'] and self.instance.qtd_adquirida:
                raise forms.ValidationError('O item não pode ser modificado porque já foi movimentado.')

        return self.cleaned_data['categoria']

    def clean_descricao(self):
        modificou_descricao = self.instance.descricao.strip() != self.cleaned_data['descricao']
        if self.instance.pk and modificou_descricao and self.instance.qtd_adquirida:
            if not tl.get_user().has_perm('patrimonio.change_empenhopermanente_movimentados'):
                raise forms.ValidationError('O item não pode ser modificado porque já foi movimentado.')
            else:
                return self.cleaned_data['descricao']
        return self.cleaned_data['descricao']

    def clean_valor(self):
        if not tl.get_user().groups.filter(name='Contador Administrador'):
            if self.instance.pk and self.instance.valor != self.cleaned_data['valor'] and self.instance.qtd_adquirida:
                raise forms.ValidationError('O item não pode ser modificado porque já foi movimentado.')

        return self.cleaned_data['valor']

    def clean(self):
        # Não permitir empenhar itens com descrição, catetoria e valor iguais.
        # unique_together = ('empenho', 'categoria', 'descricao', 'valor') não funcionou!
        super().clean()
        if not self.errors:
            if (
                self.instance.empenho.empenhopermanente_set.filter(
                    descricao=self.cleaned_data['descricao'], categoria=self.cleaned_data['categoria'], valor=self.cleaned_data['valor']
                )
                .exclude(id=self.instance.pk)
                .count()
            ):
                msg = 'Já foi empenhado um item com descrição, ED e valor iguais.'
                raise forms.ValidationError(msg)
        return self.cleaned_data


###########
# ENTRADA #
###########
class EntradaDoacaoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceField(
        label='Campus',
        queryset=UnidadeOrganizacional.objects.suap().all(),
        initial=get_uo,
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS, readonly=True),
    )
    data = forms.DateTimeFieldPlus()
    tipo_entrada = forms.ModelChoiceField(
        label='Tipo de Entrada', queryset=EntradaTipo.objects, widget=AutocompleteWidget(search_fields=EntradaTipo.SEARCH_FIELDS, readonly=True)
    )
    tipo_material = forms.ModelChoiceField(label='Tipo de Material', queryset=MaterialTipo.objects)
    vinculo_fornecedor = forms.ModelChoiceField(
        label='Fornecedor', widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS), queryset=Vinculo.objects
    )
    data_nota_fiscal = forms.DateFieldPlus(required=False)
    processo = forms.ModelChoiceField(
        queryset=Processo.objects.all(), widget=AutocompleteWidget(), help_text='Processo desta instituição relativo a esta entrada', required=False
    )

    class Meta:
        model = Entrada
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['tipo_entrada'].initial = EntradaTipo.DOACAO()
        self.fields['tipo_material'].initial = MaterialTipo.PERMANENTE()


class EntradaDoacaoItemPermanenteForm(forms.ModelFormPlus):
    categoria = forms.ModelChoiceField(
        label='Categoria',
        queryset=CategoriaMaterialPermanente.objects.filter(omitir=False),
        widget=AutocompleteWidget(search_fields=CategoriaMaterialPermanente.SEARCH_FIELDS),
    )
    descricao = forms.CharField(label='Descrição', widget=forms.Textarea)
    qtd = forms.IntegerField(min_value=1, label='Quantidade', help_text='Somente números inteiros: cada unidade gera um tombamento')
    valor = forms.DecimalFieldAlmoxPlus(label='Valor', help_text='Formato: "9.999,999999" (6 casas decimais)')

    class Meta:
        model = EntradaPermanente
        fields = ['categoria', 'descricao', 'qtd', 'valor']

    class Media:
        js = ('/static/almoxarifado/js/mascaras.js',)


class EntradaDoacaoItemConsumoForm(forms.FormPlus):
    material = forms.ModelChoiceField(label='Material', queryset=MaterialConsumo.objects.all(), widget=AutocompleteWidget())
    qtd = forms.DecimalField(min_value=Decimal('0.00001'), max_digits=15, decimal_places=5, label='Qtd', help_text='Aceita até 5 casas decimais')
    valor = forms.DecimalFieldAlmoxPlus(label='Valor', help_text='Formato: "9.999,999999" (6 casas decimais)')

    class Media:
        js = ('/static/almoxarifado/js/mascaras.js',)


class EntradaBuscaForm(forms.FormPlus):
    METHOD = 'GET'
    uo = forms.ModelChoiceField(label='Campus', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Qualquer')
    data_inicial = forms.DateFieldPlus(label='Período', required=True)
    data_final = forms.DateFieldPlus(label='', required=True)
    vinculo_fornecedor = forms.ModelChoiceField(
        label='Fornecedor',
        required=False,
        queryset=Vinculo.objects.filter(tipo_relacionamento__model='pessoajuridica'),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS),
    )
    empenho = forms.ModelChoiceField(
        label='Empenho', required=False, queryset=Empenho.objects.all(), widget=AutocompleteWidget(search_fields=Empenho.SEARCH_FIELDS)
    )
    processo = forms.ModelChoiceField(label='Processo', required=False, queryset=Processo.objects.all(), widget=AutocompleteWidget())
    numero_nota_fiscal = forms.CharField(label='Número da Nota Fiscal', max_length=25, required=False)
    tipo_material = forms.ModelChoiceField(label='Tipo de Material', required=True, queryset=MaterialTipo.objects.all())
    tipo_entrada = forms.ModelChoiceField(label='Tipo de Entrada', required=False, queryset=EntradaTipo.objects.all(), empty_label='Qualquer')
    descricao_material = forms.CharField(label='Descrição do material', required=False, widget=forms.TextInput(attrs={'size': '72'}))
    fieldsets = (
        (
            None,
            {
                'fields': (
                    ('uo', 'tipo_material', 'tipo_entrada'),
                    'vinculo_fornecedor',
                    ('data_inicial', 'data_final'),
                    'numero_nota_fiscal',
                    'empenho',
                    'processo',
                    'descricao_material',
                )
            },
        ),
    )

    class Media:
        js = ('/static/comum/js/EntradaBuscaForm.js',)

    def clean(self):
        from django.forms.utils import ErrorList

        msg = {'erro': 'Informe um valor válido.', 'erro_descricao': 'Um tipo de material deve ser informado.'}
        if not self.errors:
            if self.cleaned_data['descricao_material']:
                if self.cleaned_data['tipo_material'] is None:
                    self.errors['descricao_material'] = ErrorList([msg['erro_descricao']])
            if self.cleaned_data['data_inicial']:
                if self.cleaned_data['data_inicial'] > date.today():
                    self.errors['data_inicial'] = ErrorList([msg['erro']])
                if self.cleaned_data['data_final'] is None:
                    self.errors['data_final'] = ErrorList([msg['erro']])
                if self.cleaned_data['data_final']:
                    if self.cleaned_data['data_final'] > date.today() or self.cleaned_data['data_final'] < self.cleaned_data['data_inicial']:
                        self.errors['data_final'] = ErrorList([msg['erro']])
            elif self.cleaned_data['data_final']:
                self.errors['data_inicial'] = ErrorList([msg['erro']])
                if self.cleaned_data['data_final'] > date.today():
                    self.errors['data_final'] = ErrorList([msg['erro']])
        return self.cleaned_data


class EntradaEditarForm(forms.ModelFormPlus):
    data_nota_fiscal = forms.DateFieldPlus(label='Data Nota Fiscal', required=False)
    vinculo_fornecedor = forms.ModelChoiceField(
        label='Fornecedor',
        required=False,
        queryset=Vinculo.objects.pessoas_juridicas(),
        widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS, extraParams={'force_generic_search': '1'}),
    )
    processo = forms.ModelChoiceField(
        queryset=Processo.objects.all(), widget=AutocompleteWidget(), help_text='Processo desta instituição relativo a esta entrada', required=False
    )
    data = forms.DateFieldPlus(label='Data da Entrada', required=True)

    class Meta:
        model = Entrada
        fields = ['numero_nota_fiscal', 'data', 'data_nota_fiscal', 'vinculo_fornecedor', 'processo']


class BuscaEmpenhoForm(forms.FormPlus):
    METHOD = 'GET'
    tipo_material = forms.ModelChoiceField(label='Tipo de Material', queryset=MaterialTipo.objects.all(), required=False)
    tipo_licitacao = forms.ModelChoiceField(label='Tipo de Licitação', queryset=LicitacaoTipo.objects.all(), required=False)
    status = forms.ChoiceField(
        label='Situação',
        choices=[
            ['todos', 'Todos'],
            ['concluido', 'Concluído'],
            ['nao_concluido', 'Não concluído'],
            ['nao_iniciado', '- Não iniciado'],
            ['iniciado', '- Iniciado'],
        ],
        required=False,
    )
    ug_emitente = forms.ModelChoiceField(label='UG Emitente', queryset=UnidadeOrganizacional.objects.suap().all(), required=False)
    numero_empenho = forms.CharField(label='Nº Empenho', required=False)
    numero_processo = forms.ModelChoiceField(label='Processo', required=False, queryset=Processo.objects.all(), widget=AutocompleteWidget())
    vinculo_fornecedor = forms.ModelChoiceField(
        label='Fornecedor', required=False, queryset=Vinculo.objects.all(), widget=AutocompleteWidget(search_fields=Vinculo.SEARCH_FIELDS)
    )
    elemento_despesa = forms.ModelChoiceField(
        label='Categoria de Despesa Permanente',
        required=False,
        queryset=CategoriaMaterialPermanente.objects.all(),
        widget=AutocompleteWidget(search_fields=CategoriaMaterialPermanente.SEARCH_FIELDS),
    )
    elemento_despesa_consumo = forms.ModelChoiceField(
        label='Categoria de Despesa Consumo',
        required=False,
        queryset=CategoriaMaterialConsumo.objects.all(),
        widget=AutocompleteWidget(search_fields=CategoriaMaterialConsumo.SEARCH_FIELDS),
    )
    numero_licitacao = forms.CharField(label='Nº Licitação', required=False)
    descricao_item = forms.CharField(label='Descrição do Item', required=False)
    situacao = forms.ChoiceField(
        label='Situação de Atraso',
        choices=[
            ['qualquer', 'Qualquer'],
            ['sem_atraso', 'Sem atraso'],
            ['atrasados', 'Apenas atrasados'],
            ['pendentes', 'Apenas pendentes'],
            ['concluidos_atraso', 'Apenas concluídos com atraso'],
        ],
        required=False,
    )

    fieldsets = (
        (
            None,
            {
                'fields': (
                    ('tipo_material', 'tipo_licitacao'),
                    ('ug_emitente', 'numero_licitacao', 'numero_empenho'),
                    'numero_processo',
                    'vinculo_fornecedor',
                    'elemento_despesa',
                    'elemento_despesa_consumo',
                    ('descricao_item', 'status', 'situacao'),
                )
            },
        ),
    )


class TipoEtiquetaForm(forms.FormPlus):
    from djtools.etiquetas.labels import LABELS_CHOICES

    tipoetiqueta = forms.ChoiceField(label='Tipos de Etiquetas', choices=LABELS_CHOICES, required=True)


class PlanoContasAlmoxForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoContasAlmox
        exclude = ('data_desativacao',)


class CampusForm(forms.Form):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.suap(), label='Campus', required=True)


def DevolucaoItemFormFactory(requisicao):
    class DevolucaoItemForm(forms.FormPlus):
        fields = {}
        fields_list = []
        fields['processo'] = forms.ModelChoiceField(queryset=Processo.objects.all(), widget=AutocompleteWidget(), required=False)

        def __init__(self, *args, **kwargs):
            kwargs.pop('uo')
            super().__init__(*args, **kwargs)
            for i in requisicao.get_itens_aceitos():
                label = str(i.material)
                field_name = str(i.id)
                self.fields[field_name] = forms.IntegerField(label=label, required=False)

        def clean(self):
            for i in requisicao.get_itens_aceitos():
                pk = str(i.id)
                qtd = self.cleaned_data.get(pk)
                quantidade_aceita_req = i.movimentoalmoxsaida_set.values_list('qtd', flat=True)[0] or 0
                if qtd is not None:
                    if requisicao.tipo == 'user':
                        total_devolvidos = (
                            next(
                                iter(
                                    DevolucaoMaterial.objects.filter(requisicao_user=requisicao, material=i.material)
                                    .aggregate(Sum('quantidade'))
                                    .values()
                                )
                            )
                            or 0
                        )
                    else:
                        total_devolvidos = (
                            next(
                                iter(
                                    DevolucaoMaterial.objects.filter(requisicao_uo=requisicao, material=i.material)
                                    .aggregate(Sum('quantidade'))
                                    .values()
                                )
                            )
                            or 0
                        )
                    total_devolvidos += qtd
                    if total_devolvidos > quantidade_aceita_req:
                        self.add_error(pk, 'A quantidade devolvida dos itens é maior.')
            return self.cleaned_data

        @transaction.atomic()
        def save(self):
            requisicao_user = None
            requisicao_uo = None
            if requisicao.tipo == 'user':
                requisicao_user = requisicao
            else:
                requisicao_uo = requisicao
            uo = requisicao.uo_fornecedora
            for item in requisicao.get_itens_aceitos():
                pk = str(item.id)
                qtd = self.cleaned_data.get(pk)
                if qtd:
                    devolucao = DevolucaoMaterial.objects.create(
                        material=item.material, quantidade=qtd, uo=uo, requisicao_user=requisicao_user, requisicao_uo=requisicao_uo
                    )

                    material_a_atualizar = MaterialEstoque.objects.get(material=item.material, uo=uo)
                    item = requisicao.item_set.filter(id=item.id)[0]
                    valor_saida = item.movimentoalmoxsaida_set.values_list('valor', flat=True)[0] or 0

                    valor_medio = ((material_a_atualizar.quantidade * material_a_atualizar.valor_medio) + (qtd * valor_saida)) / (
                        material_a_atualizar.quantidade + qtd
                    )
                    material_a_atualizar.valor_medio = valor_medio
                    material_a_atualizar.quantidade = material_a_atualizar.quantidade + qtd
                    material_a_atualizar.save()

                    MovimentoAlmoxEntrada.objects.create(
                        tipo=MovimentoAlmoxEntradaTipo.DEVOLUCAO(),
                        qtd=devolucao.quantidade,
                        estoque=devolucao.quantidade,
                        valor=valor_saida,
                        uo=devolucao.uo,
                        material=devolucao.material,
                    ).save()

    return DevolucaoItemForm


class CancelarRequisicaoSaidaUserForm(forms.Form):
    motivo_cancelamento = forms.CharField(label='Motivo do cancelamento', required=True, widget=forms.Textarea)

    def __init__(self, *args, **kwargs):
        requisicao = kwargs.pop('requisicao')
        super().__init__(*args, **kwargs)
        self.instance = requisicao

    @transaction.atomic()
    def save(self):
        requisicao = self.instance
        requisicao.motivo_cancelamento = self.cleaned_data['motivo_cancelamento']
        requisicao.save()
        uo = requisicao.uo_fornecedora
        for item in requisicao.get_itens_aceitos():
            pk = str(item.id)
            qtd = self.cleaned_data.get(pk)
            valor_saida = item.movimentoalmoxsaida_set.values_list('valor', flat=True).first() or 0
            if qtd:
                item = requisicao.item_set.filter(id=item.id)[0]
                ultima_movimentacao = item.movimentoalmoxsaida_set.filter(Q(quantidade=qtd) & Q(valor=valor_saida) & Q(uo=uo)).order_by('-id').first()

                if ultima_movimentacao:
                    ultima_movimentacao.delete()

            devolucao = DevolucaoMaterial.objects.filter(requisicao_user=requisicao, material=item.material, uo=uo).order_by('-id').first()

            if devolucao:
                movimento_entrada = (
                    MovimentoAlmoxEntrada.objects.filter(
                        tipo=MovimentoAlmoxEntradaTipo.DEVOLUCAO(), valor=valor_saida, uo=devolucao.uo, material=devolucao.material
                    )
                    .order_by('-id')
                    .first()
                )
                if movimento_entrada:
                    MovimentoAlmoxEntrada.objects.filter(id=movimento_entrada.id).delete()
                devolucao.delete()

            calcula_valor_medio_atual(uo, item.material)
            item.delete()
        requisicao.save()


class ConfiguracaoForm(forms.FormPlus):
    data_migracao_valor_medio = forms.DateFieldPlus(label='Data Início do uso do Valor Médio', required=False)
    descentralizado = forms.BooleanField(
        label='Operações de almoxarifado são descentralizadas na instituição?',
        help_text='Marcando esta opção, requisições de transferências intercampi são habilitadas aos servidores de qualquer UO ao invés de restringi-las a UO do servidor logado.',
        initial=False,
        required=False,
    )


class ImportacaoEstoqueCSVForm(forms.Form):
    arquivo = forms.FileField(label='Arquivo CSV', required=True)
    numero_empenho_inicial = forms.CharField(
        label='Número do Empenho inicial',
        required=True,
        help_text='Ex.: 2025NE800125 (o sufixo numérico será incrementado a cada 200 itens).',
    )
    processo = forms.ModelChoiceField(
        label='Processo',
        queryset=Processo.objects.all(),
        widget=AutocompleteWidget(),
        required=True,
    )


class CancelarItensEntradaForm(forms.FormPlus):
    """Seleção de itens de uma entrada permanente a serem cancelados, com a justificativa."""

    SUBMIT_LABEL = 'Cancelar Itens'

    itens = forms.ModelMultipleChoiceField(
        label='Itens',
        queryset=EntradaPermanente.objects.none(),
        widget=forms.CheckboxSelectMultiple(),
        required=True,
        error_messages={'required': 'Selecione ao menos um item para cancelar.'},
    )
    justificativa = forms.CharField(label='Justificativa', widget=forms.Textarea(attrs={'rows': 4}), required=True)

    def __init__(self, *args, **kwargs):
        self.entrada = kwargs.pop('entrada')
        super().__init__(*args, **kwargs)
        # Restringir o queryset à entrada em questão impede que itens de outra entrada
        # sejam cancelados pela manipulação do POST.
        self.fields['itens'].queryset = self.entrada.entradapermanente_set.order_by('categoria__codigo', 'descricao', 'id')

    def clean_itens(self):
        itens = self.cleaned_data['itens']
        impedidos = [f'{item.descricao}: {", ".join(item.get_impedimentos_cancelamento())}' for item in itens if not item.pode_cancelar()]
        if impedidos:
            raise forms.ValidationError('Não é possível cancelar os itens a seguir. {}'.format(' | '.join(impedidos)))
        return itens
