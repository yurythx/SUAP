from __future__ import annotations

from django.conf import settings
from comum.models import Ano
from djtools import forms
from edu.models.cadastros_gerais import PERIODO_LETIVO_CHOICES
from pit_rit_v3.models import AtividadePlanejada, Parecer, PlanoIndividualTrabalhoV3
from rh.models import Servidor


class ConfiguracaoForm(forms.FormPlus):
    ano_inicio_app = forms.IntegerField(
        label='Ano letivo de início do módulo',
        required=False,
        help_text='Ano a partir do qual a versão V3 começará a ser utilizada.',
    )
    periodo_inicio_app = forms.IntegerField(
        label='Período letivo de início do módulo',
        required=False,
        min_value=1,
        help_text='Semestre a partir do qual a versão V3 começará a ser utilizada.',
    )


class CriarPlanoIndividualTrabalhoForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceFieldPlus(Ano.objects, label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=PERIODO_LETIVO_CHOICES)

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        if 'pit_rit_v3' in settings.INSTALLED_APPS:
            ano_inicio = PlanoIndividualTrabalhoV3.get_ano_inicio()
            if ano_inicio:
                self.fields['ano_letivo'].queryset = Ano.objects.filter(ano__gte=ano_inicio)
            else:
                self.fields['ano_letivo'].queryset = Ano.objects.none()

    def processar(self, professor_id: int) -> PlanoIndividualTrabalhoV3:
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        qs = PlanoIndividualTrabalhoV3.objects.filter(professor_id=professor_id, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)
        if qs.exists():
            return qs.first()
        else:
            return PlanoIndividualTrabalhoV3.objects.create(professor_id=professor_id, ano_letivo=ano_letivo, periodo_letivo=periodo_letivo)


class PlanejarAtividadeForm(forms.ModelFormPlus):
    class Meta:
        model = AtividadePlanejada
        fields = ('atividade', 'objeto_institucional', 'carga_horaria', 'bolsa_especifica', 'comprovante', 'observacao')

    def clean_carga_horaria(self):
        carga_horaria = self.cleaned_data.get('carga_horaria', 0)
        if carga_horaria <= 0:
            raise forms.ValidationError('A carga-horária deve ser maior que zero.')
        return carga_horaria


class EnviarPlanoForm(forms.ModelFormPlus):
    class Meta:
        model = PlanoIndividualTrabalhoV3
        fields = ('avaliador',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliador'].required = False
        self.fields['avaliador'].queryset = Servidor.objects.ativos()
        self.fields['avaliador'].help_text = 'Servidor responsável pela avaliação ano/período do plano individual de trabalho'

    def clean(self):
        if float(self.instance.get_atividades_planejadas()[0]) == float(self.instance.get_ch_prevista()):
            return super().clean()
        else:
            raise forms.ValidationError('A carga-horária planejada diverge da carga-horária da sua jornada de trabalho.')


class ParecerForm(forms.ModelFormPlus):
    class Meta:
        model = Parecer
        fields = ('obs',)


class AprovarRelatorioForm(ParecerForm):
    responsavel_publicacao = forms.ModelChoiceFieldPlus(Servidor.objects.all(), label='Responsável pela Publicação')

    class Meta:
        model = Parecer
        fields = ('obs',)
