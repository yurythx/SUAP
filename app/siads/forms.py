from djtools import forms
from rh.models import Setor, UnidadeOrganizacional
from siads.models import GrupoMaterialConsumo, GrupoMaterialPermanente, MaterialPermanente, MaterialPermanenteSiads, SetorSiads


class AssociarGrupoForm(forms.FormPlus):
    grupos = forms.ModelChoiceFieldPlus(label='Grupo', queryset=GrupoMaterialConsumo.objects)

    def __init__(self, *args, **kwargs):
        grupos = kwargs.pop('grupos')

        super().__init__(*args, **kwargs)
        self.fields['grupos'].queryset = grupos


class AssociarGrupoPermanenteForm(forms.FormPlus):
    grupos = forms.ModelChoiceFieldPlus(label='Grupo', queryset=GrupoMaterialPermanente.objects)

    def __init__(self, *args, **kwargs):
        grupos = kwargs.pop('grupos')

        super().__init__(*args, **kwargs)
        self.fields['grupos'].queryset = grupos


class GrupoAtualizarNomeForm(forms.ModelFormPlus):
    nome = forms.CharFieldPlus(label='Grupo', max_length=1024, required=True)

    class Meta:
        fields = ('nome',)
        model = GrupoMaterialConsumo


class SetorSiadsForm(forms.ModelForm):
    class Meta:
        model = SetorSiads
        fields = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uorg'].required = True

        if self.instance.sala is not None:
            setores = SetorSiads.objects.filter(uo=self.instance.uo, setor_suap__isnull=False).values_list('setor_suap_id', flat=True)
            self.fields['sala'].widget.attrs['readonly'] = True
            self.fields['setor_suap'].queryset = Setor.objects.suap_ativos().filter(id__in=setores)
        else:
            self.fields['setor_suap'].widget.attrs['readonly'] = True


class CampusForm(forms.Form):
    campus = forms.ModelChoiceField(label='Campus', required=True, queryset=UnidadeOrganizacional.objects)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        uos = UnidadeOrganizacional.objects.filter(tipo__isnull=False)
        uos = uos.exclude(tipo_id=UnidadeOrganizacional.TIPO_CONSELHO)

        self.fields['campus'].queryset = uos


class MaterialPermanenteForm(forms.ModelForm):
    grupo = forms.ModelChoiceFieldPlus(label='Grupo', queryset=GrupoMaterialPermanente.objects)

    class Meta:
        model = MaterialPermanente
        fields = (
            'grupo',
            'nr_serie',
            'marca',
            'modelo',
            'fabricante',
        )


class TipoSetorSiadsForm(forms.Form):
    tipo = forms.ChoiceField(label='Tipo', choices=(('SETOR', 'Setor'), ('SALA', 'Sala')))


class GerarSetorSiadsForm(forms.Form):
    uo = forms.ModelChoiceField(label='Campus', required=True, queryset=UnidadeOrganizacional.objects)
    uasg = forms.CharField(label='Código da UASG', max_length=10, required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(tipo__isnull=False)


class MaterialPermanenteSiadsForm(forms.ModelForm):
    class Meta:
        model = MaterialPermanenteSiads
        fields = (
            'codigo_material',
            'descricao',
            'patrimonio',
            'especificacao',
            'marca',
            'modelo',
            'fabricante',
            'nr_serie',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['codigo_material'].widget.attrs['readonly'] = True
        self.fields['descricao'].widget.attrs['readonly'] = True
        self.fields['patrimonio'].widget.attrs['readonly'] = True

    def save(self, *args, **kwargs):
        self.instance.ajustado = True
        super().save(*args, *args, **kwargs)
