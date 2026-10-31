from django.core.exceptions import ValidationError
from django.db import transaction
from django.forms.utils import ErrorList

from djtools import forms
from djtools.forms import DtModelForm
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus
from financeiro.models import SubElementoNaturezaDespesa
from materiais.models import Categoria, CategoriaDescritor, Material, MaterialCotacao, MaterialDescritor, MaterialTag, Requisicao
from rh.models import PessoaJuridica


def MaterialFormFactory(material=None, categoria=None):
    """
    Retorna o form de cadastro/edição de materiais acrescido dos campos com os
    descritores e cotações.
    """
    ids = set(Categoria.objects.values_list('sub_elemento_nd', flat=True))
    sub_elementos = SubElementoNaturezaDespesa.objects.filter(id__in=ids)

    class MaterialForm(forms.ModelFormPlus):
        tags = forms.MultipleModelChoiceFieldPlus(
            label='Tags', queryset=MaterialTag.objects, widget=FilteredSelectMultiplePlus('', True), required=False
        )
        sub_elemento = forms.ModelChoiceField(queryset=sub_elementos, label='Subelemento')
        categoria = forms.ChainedModelChoiceField(
            Categoria.objects.all(),
            label='Categoria',
            empty_label='Selecione o Subelemento',
            required=True,
            obj_label='descricao',
            url='/materiais/get_categorias/',  # utilizado somente para colocar o unicode no label dos options
            form_filters=[('sub_elemento', 'sub_elemento_nd_id')],
        )

        SUBMIT_LABEL = 'Salvar Material'

        fieldsets = (
            (None, {'fields': ('sub_elemento', 'categoria', 'codigo_catmat', 'descricao', 'especificacao', 'unidade_medida', 'tags', 'ativo')}),
        )

        class Meta:
            model = Material
            exclude = ()

        def save(self, commit=True):
            super().save(commit=commit)
            for key, value in list(self.cleaned_data.items()):
                if key.startswith('categoria_descritor_'):
                    cd_pk = key.split('_')[-1]
                    cd = CategoriaDescritor.objects.get(pk=cd_pk)
                    md = MaterialDescritor.objects.get_or_create(material=self.instance, categoria_descritor=cd)[0]
                    md.descricao = value
                    md.save()

    if not material and categoria:  # Cadastro
        material = Material(categoria=categoria)

    if material:
        for cd in material.categoria.categoriadescritor_set.all():
            try:
                initial = material.materialdescritor_set.get(categoria_descritor=cd).descricao
            except MaterialDescritor.DoesNotExist:
                initial = ''
            field = forms.CharField(label=cd.descricao, required=cd.obrigatorio, initial=initial)
            field_name = f'categoria_descritor_{cd.id}'
            MaterialForm.base_fields[field_name] = field
            MaterialForm.fieldsets[0][1]['fields'] = MaterialForm.fieldsets[0][1]['fields'] + (field_name,)

        MaterialForm.base_fields['sub_elemento'].initial = material.categoria.sub_elemento_nd_id
        MaterialForm.base_fields['categoria'].initial = material.categoria.pk

    return MaterialForm


def MaterialCotacaoFormFactory(material=None, tipo=None):
    """
    Retorna o form de cadastro/edição de cotacao de materiais acrescido dos campos
    """

    class MaterialCotacaoForm(forms.ModelFormPlus):
        tipo = forms.ChoiceField(
            label='Modalidade',
            choices=[['', 'Selecione a modalidade'], ['INTERNET', 'Internet'], ['COMPRAS', 'Compras NET'], ['DIRETA', 'Direta']],
            initial='Selecione a modalidade',
        )
        fornecedor = forms.ModelChoiceField(
            label='Fornecedor',
            required=False,
            queryset=PessoaJuridica.objects.all(),
            widget=AutocompleteWidget(search_fields=PessoaJuridica.SEARCH_FIELDS),
        )

        material = forms.ModelChoiceField(
            label='Material',
            required=False,
            queryset=Material.objects.all(),
            widget=AutocompleteWidget(search_fields=Material.SEARCH_FIELDS, readonly=True),
        )

        SUBMIT_LABEL = 'Salvar Material'

        fieldsets = ((None, {'fields': ('tipo', 'material', 'valor', 'data', 'ativo')}),)

        class Meta:
            model = MaterialCotacao
            exclude = ()

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            tipo = self.fields.get('tipo', None)
            if tipo:
                if tipo.initial == 'INTERNET':
                    self.fields['fornecedor'].required = True
                    self.fields['site'].required = True
                if tipo.initial == 'COMPRAS':
                    self.fields['uasg'].required = True
                    self.fields['numero_pregao'].required = True
                    self.fields['numero_item'].required = True
                if tipo.initial == 'DIRETA':
                    self.fields['fornecedor'].required = True
                    self.fields['arquivo'].required = True
            if self.instance.pk:
                self.fields['tipo'].required = False
                self.fields['tipo'].widget = forms.HiddenInput()
                if self.instance.site:
                    field_name_site = 'site'
                    field_name_fornecedor = 'fornecedor'
                    self.fieldsets[0][1]['fields'] = self.fieldsets[0][1]['fields'] + (field_name_site, field_name_fornecedor)

                elif self.instance.numero_pregao:
                    field_name_pregao = 'numero_pregao'
                    field_name_item = 'numero_item'
                    field_name_uasg = 'uasg'
                    self.fieldsets[0][1]['fields'] = self.fieldsets[0][1]['fields'] + (field_name_uasg, field_name_pregao, field_name_item)

                else:
                    field_name_arquivo = 'arquivo'
                    field_name_fornecedor = 'fornecedor'
                    self.fieldsets[0][1]['fields'] = self.fieldsets[0][1]['fields'] + (field_name_fornecedor, field_name_arquivo)

        def clean_tipo(self):
            if self.cleaned_data['tipo'] is None:
                raise ValidationError('Este campo obrigatório.')
            return self.cleaned_data['tipo']

        def clean(self):
            if self.instance:
                if self.instance.site:
                    if not self.cleaned_data.get('site', None):
                        self._errors['site'] = ErrorList(['Este campo é obrigatório.'])
                    if self.instance.fornecedor and not self.cleaned_data.get('fornecedor', None):
                        self._errors['fornecedor'] = ErrorList(['Este campo é obrigatório.'])

                if self.instance.uasg:
                    if not self.cleaned_data.get('uasg', None):
                        self._errors['uasg'] = ErrorList(['Este campo é obrigatório.'])
                    if not self.cleaned_data.get('numero_pregao', None):
                        self._errors['numero_pregao'] = ErrorList(['Este campo é obrigatório.'])
                    if not self.cleaned_data.get('numero_item', None):
                        self._errors['numero_item'] = ErrorList(['Este campo é obrigatório.'])

                if self.instance.arquivo:
                    if not self.cleaned_data.get('fornecedor', None):
                        self._errors['fornecedor'] = ErrorList(['Este campo é obrigatório.'])
                    if not self.cleaned_data.get('arquivo', None):
                        self._errors['arquivo'] = ErrorList(['Este campo é obrigatório.'])

            if 'tipo' in self.cleaned_data and self.cleaned_data['tipo'] == 'INTERNET':
                if not self.cleaned_data.get('site', None):
                    self._errors['site'] = ErrorList(['Este campo é obrigatório.'])
                if not self.cleaned_data.get('fornecedor', None):
                    self._errors['fornecedor'] = ErrorList(['Este campo é obrigatório.'])
            if 'tipo' in self.cleaned_data and self.cleaned_data['tipo'] == 'COMPRAS':
                if not self.cleaned_data.get('uasg', None):
                    self._errors['uasg'] = ErrorList(['Este campo é obrigatório.'])
                if not self.cleaned_data.get('numero_pregao', None):
                    self._errors['numero_pregao'] = ErrorList(['Este campo é obrigatório.'])
                if not self.cleaned_data.get('numero_item', None):
                    self._errors['numero_item'] = ErrorList(['Este campo é obrigatório.'])
            if 'tipo' in self.cleaned_data and self.cleaned_data['tipo'] == 'DIRETA':
                if not self.cleaned_data.get('arquivo', None):
                    self._errors['arquivo'] = ErrorList(['Este campo é obrigatório.'])
                if not self.cleaned_data.get('fornecedor', None):
                    self._errors['fornecedor'] = ErrorList(['Este campo é obrigatório.'])
            return self.cleaned_data

    if tipo == 'INTERNET':
        field_name_site = 'site'
        field_name_fornecedor = 'fornecedor'
        MaterialCotacaoForm.fieldsets[0][1]['fields'] = MaterialCotacaoForm.fieldsets[0][1]['fields'] + (field_name_fornecedor, field_name_site)

    if tipo == 'COMPRAS':
        field_name_pregao = 'numero_pregao'
        field_name_item = 'numero_item'
        field_name_uasg = 'uasg'
        MaterialCotacaoForm.fieldsets[0][1]['fields'] = MaterialCotacaoForm.fieldsets[0][1]['fields'] + (
            field_name_uasg,
            field_name_pregao,
            field_name_item,
        )

    if tipo == 'DIRETA':
        field_name_arquivo = 'arquivo'
        field_name_fornecedor = 'fornecedor'
        MaterialCotacaoForm.fieldsets[0][1]['fields'] = MaterialCotacaoForm.fieldsets[0][1]['fields'] + (field_name_fornecedor, field_name_arquivo)
    MaterialCotacaoForm.base_fields['tipo'].initial = tipo
    MaterialCotacaoForm.base_fields['material'].initial = material
    return MaterialCotacaoForm


class MaterialAdicionarCotacaoForm(forms.ModelFormPlus):
    SUBMIT_LABEL = 'Adicionar Cotação'

    class Meta:
        model = MaterialCotacao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

    @transaction.atomic()
    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)


class RequisicaoAvaliarForm(DtModelForm):
    class Meta:
        model = Requisicao
        fields = ['requerimento', 'status', 'resposta', 'material']

    readonly_fields = ['requerimento']
    required_fields = ['resposta']

    def clean_status(self):
        if self.cleaned_data['status'] == self.instance.status:
            raise forms.ValidationError('O status deve ser modificado')
        return self.cleaned_data['status']

    def clean_material(self):
        if self.cleaned_data.get('status') == Requisicao.STATUS_INDEFERIDO_OUTROS:
            if self.cleaned_data.get('material'):
                raise forms.ValidationError('O material não pode ser escolhido para o status escolhido.')
        elif self.cleaned_data.get('status') in [Requisicao.STATUS_DEFERIDO, Requisicao.STATUS_INDEFERIDO_MATERIAL_EXISTENTE]:
            if not self.cleaned_data.get('material'):
                raise forms.ValidationError('O material deve ser escolhido.')
        return self.cleaned_data['material']


class SituacaoCotacaoForm(forms.FormPlus):
    data_validade = forms.DateFieldPlus(label='Data de Validade', help_text='Data de Validade')
