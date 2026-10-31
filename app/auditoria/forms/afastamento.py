import calendar
from datetime import date
from django.db import transaction
from djtools import forms
from django.core.validators import MinValueValidator, MaxValueValidator

from djtools.forms.widgets import AutocompleteWidget
from ..models import AfastamentoPlanejado, TipoAfastamento, PlanejamentoMensal, StatusAfastamento


class AfastamentoForm(forms.ModelFormPlus):
    data_inicio = forms.DateFieldPlus(
        label='Data de Inicio',
        required=True,
        help_text='Data de início do afastamento.',
    )
    data_fim = forms.DateFieldPlus(label='Data Final', required=True, help_text='Data final do afastamento.')
    motivo = forms.CharFieldPlus(label='Motivação', widget=forms.Textarea())
    tipo_afastamento = forms.ModelChoiceField(
        label='Tipo de Afastamento',
        queryset=TipoAfastamento.objects.filter(ativo=True),
        required=True,
        widget=AutocompleteWidget(search_fields=TipoAfastamento.SEARCH_FIELDS),
    )
    status = forms.ChoiceField(
        label='Status',
        choices=StatusAfastamento.choices,
        required=False,
        disabled=True,
    )
    fieldsets = (
        (
            'Informações Gerais',
            {
                'fields': (('data_inicio', 'data_fim'), 'tipo_afastamento'),
            },
        ),
        (
            'Situação do Afastamento',
            {
                'fields': ('status',),
            },
        ),
        (
            'Motivação do Afastamento',
            {
                'fields': ('motivo',),
            },
        ),
    )

    class Meta:
        model = AfastamentoPlanejado
        fields = ['data_inicio', 'data_fim', 'motivo', 'tipo_afastamento']

    def __init__(self, *args, readonly=False, **kwargs):
        self.planejamento_mensal: PlanejamentoMensal = kwargs.pop('planejamento', None)
        super().__init__(*args, **kwargs)
        # Se for criação, remove o campo `status`
        current_status = self.instance.status
        current_label = self.instance.get_status_display()
        self.fields['status'].choices = [(current_status, current_label)]
        self.fields['status'].initial = current_status
        self.fields['status'].widget.attrs['readonly'] = True
        self.fields['status'].widget.attrs['disabled'] = True

        ano = self.planejamento_mensal.ano
        # Restrições de data
        ultimo_dia = calendar.monthrange(ano, self.planejamento_mensal.mes)[1]
        data_min_obj = date(ano, self.planejamento_mensal.mes, 1)
        data_max_obj = date(ano, self.planejamento_mensal.mes, ultimo_dia)
        for field_name in ['data_inicio', 'data_fim']:
            self.fields[field_name].widget.attrs.update({'type': 'date', 'min': data_min_obj.isoformat(), 'max': data_max_obj.isoformat()})
            self.fields[field_name].validators = [MinValueValidator(data_min_obj), MaxValueValidator(data_max_obj)]
        # Modo somente leitura
        if readonly:
            for field in self.fields.values():
                field.widget.attrs['readonly'] = True
                field.widget.attrs.setdefault('class', '')
                field.widget.attrs['class'] += ' readonly-field'
            self.fields['tipo_afastamento'].widget.attrs['disabled'] = True

    def clean(self):
        cleaned_data = super().clean()
        if not self.planejamento_mensal:
            raise forms.ValidationError('Planejamento mensal não informado.')
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        if not data_inicio or not data_fim:
            return cleaned_data  # skip if dates are not valid
        ano = self.planejamento_mensal.planejamento_anual.ano
        mes = self.planejamento_mensal.mes
        primeiro_dia = date(ano, mes, 1)
        ultimo_dia = date(ano, mes, calendar.monthrange(ano, mes)[1])
        if data_inicio < primeiro_dia or data_fim > ultimo_dia:
            raise forms.ValidationError(
                f'O afastamento deve estar dentro do mês de {primeiro_dia.strftime("%B/%Y")}: '
                f'de {primeiro_dia.strftime("%d/%m")} até {ultimo_dia.strftime("%d/%m")}.'
            )
        if data_fim < data_inicio:
            raise forms.ValidationError('A data final do afastamento não pode ser anterior à data inicial.')
        self._validar_sobreposicao(data_inicio, data_fim)
        return cleaned_data

    def _validar_sobreposicao(self, data_inicio: date, data_fim: date) -> None:
        """Impede declarar duas vezes o mesmo dia no planejamento do mês.

        A carga horária já conta cada dia uma única vez, mas dois registros para
        o mesmo período apareceriam lado a lado na tela do planejamento sem que
        o auditor entendesse o porquê. Afastamentos rejeitados não bloqueiam:
        eles não descontam nada.
        """
        conflitantes = AfastamentoPlanejado.objects.filter(
            planejamento=self.planejamento_mensal,
            data_inicio__lte=data_fim,
            data_fim__gte=data_inicio,
        ).exclude(status=StatusAfastamento.REJEITADO)
        if self.instance.pk:
            conflitantes = conflitantes.exclude(pk=self.instance.pk)

        conflito = conflitantes.first()
        if conflito:
            raise forms.ValidationError(
                f'O período informado se sobrepõe ao afastamento "{conflito.tipo_afastamento}" '
                f'({conflito.data_inicio:%d/%m} a {conflito.data_fim:%d/%m}) já cadastrado neste mês.'
            )

    def save(self, commit=True):
        afastamento: AfastamentoPlanejado = super().save(commit=False)
        afastamento.planejamento = self.planejamento_mensal
        if commit:
            afastamento.save()
        return afastamento


class HomologarAfastamentoForm(forms.ModelForm):
    data_inicio = forms.DateFieldPlus(label='Data de Inicio do Afastamento', required=True)
    data_fim = forms.DateFieldPlus(label='Data Final do Afastamento', required=True)
    motivo = forms.CharFieldPlus(label='Texto', widget=forms.Textarea(attrs={'readonly': 'readonly'}))
    tipo_afastamento = forms.ModelChoiceFieldPlus(
        label='Tipo de Afastamento',
        queryset=TipoAfastamento.objects.filter(ativo=True),
        required=True,
        widget=AutocompleteWidget(search_fields=TipoAfastamento.SEARCH_FIELDS),
    )
    acao = forms.ChoiceField(
        label='Ação',
        choices=[
            ('aprovar', 'Aprovar'),
            ('rejeitar', 'Rejeitar'),
        ],
        required=True,
        widget=forms.RadioSelect(),
    )
    # Campo para justificativa de rejeição, só necessário se a ação for rejeitar
    justificativa_rejeicao = forms.CharFieldPlus(
        label='Justificativa da Reprovação',
        required=False,
        widget=forms.Textarea(attrs={'placeholder': 'Informe a justificativa para reprovação.'}),
    )
    fieldsets = (
        (
            'Informações Gerais',
            {
                'fields': (
                    ('data_inicio', 'data_fim'),
                    'tipo_afastamento',
                    'motivo',
                ),
            },
        ),
        (
            'Avaliação do Afastamento',
            {
                'fields': ('acao', ('justificativa_rejeicao',)),
            },
        ),
    )

    class Meta:
        model = AfastamentoPlanejado
        fields = ['data_inicio', 'data_fim', 'motivo', 'justificativa_rejeicao', 'tipo_afastamento']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Datas
        self.fields['data_inicio'].widget.attrs['readonly'] = True
        self.fields['data_fim'].widget.attrs['readonly'] = True
        # Motivo
        self.fields['motivo'].widget.attrs['readonly'] = True
        # Tipo de Afastamento
        self.fields['tipo_afastamento'].queryset = TipoAfastamento.objects.filter(id=self.instance.tipo_afastamento.id)
        self.fields['tipo_afastamento'].widget.attrs['readonly'] = True
        if not self.instance.esta_pendente:
            self.fields['acao'].initial = 'aprovar' if self.instance.esta_homologado else 'rejeitar'
            self.fields['acao'].widget.attrs['readonly'] = True
            self.fields['acao'].widget.attrs['disabled'] = True
            # Justificativa de Rejeição
            self.fields['justificativa_rejeicao'].widget.attrs['readonly'] = True
            self.fields['justificativa_rejeicao'].widget.attrs['disabled'] = True

    def clean(self):
        cleaned_data = super().clean()
        if cleaned_data['acao'] == 'rejeitar' and not cleaned_data.get('justificativa_rejeicao'):
            raise self.add_error('justificativa_rejeicao', 'Informe a justificativa para reprovação.')
        if not self.instance.esta_pendente:
            raise forms.ValidationError('Afastamento já foi homologado ou rejeitado.')
        return cleaned_data

    @transaction.atomic()
    def save(self, commit=True):
        afastamento: AfastamentoPlanejado = super().save(commit=False)
        acao = self.cleaned_data['acao']
        justificativa_rejeicao = self.cleaned_data.get('justificativa_rejeicao', '')
        if commit:
            if acao == 'aprovar':
                afastamento.homologar()
            elif acao == 'rejeitar':
                afastamento.rejeitar(justificativa_rejeicao)
            else:
                raise self.add_error('acao', "Ação inválida. Escolha entre 'aprovar' ou 'rejeitar'.")
            return super().save(commit=commit)
