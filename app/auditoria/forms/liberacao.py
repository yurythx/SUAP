from narwhals import Date
from djtools import forms
from django.db.models import Q
from django.db.models.functions import Coalesce, ExtractMonth, ExtractDay
from datetime import timedelta
from djtools.forms.widgets import AutocompleteWidget
from ponto.models import Liberacao, TipoLiberacao
from rh.models import UnidadeOrganizacional
from ..models import LiberacaoProgramada, CategoriaLiberacao
from ..utils import considerar_liberacoes_ponto


def _tipo_ponto(nome: str) -> int:
    return TipoLiberacao.get_numero(nome)


TIPO_FERIADO_PONTO = _tipo_ponto(TipoLiberacao.FERIADO)
TIPO_RECESSO_PONTO = _tipo_ponto(TipoLiberacao.RECESSO)
TIPO_RECORRENTE_PTO = _tipo_ponto(TipoLiberacao.FERIADO_RECORRENTE)


class LiberacaoProgramadaForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.suap(),
        required=False,
        label='Unidade Organizacional',
        help_text='Se vazio, aplica globalmente; caso contrário, ao município da UO.',
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
    )

    fieldsets = (
        ('Identificação', {'fields': ('nome', 'descricao', 'ativo')}),
        (
            'Unidade',
            {
                'fields': ('uo',),
                'description': 'Deixe em branco para aplicar globalmente; se preencher, aplica à UO (município).',
            },
        ),
        (
            'Classificação',
            {
                'fields': ('categoria', 'tipo_expediente'),
            },
        ),
        (
            'Ocorrência Pontual (Feriado/Recesso)',
            {
                'fields': (('data_inicio', 'data_fim'),),
                'description': 'Use para dia único (apenas data início) ou intervalo (início/fim).',
            },
        ),
        (
            'Ocorrência Recorrente (Feriado Recorrente)',
            {
                'fields': (('dia_recorrente', 'mes_recorrente'),),
                'description': 'Repete anualmente; NÃO use datas de início/fim.',
            },
        ),
    )

    class Meta:
        model = LiberacaoProgramada
        fields = ['nome', 'descricao', 'categoria', 'uo', 'tipo_expediente', 'data_inicio', 'data_fim', 'mes_recorrente', 'dia_recorrente']

    class Media:
        js = ('auditoria/js/liberacao.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.considerar_liberacoes_ponto = considerar_liberacoes_ponto()
        self.fields['nome'].widget.attrs['autofocus'] = True

    def verificar_liberacao_ponto(
        self,
        unidade: UnidadeOrganizacional,
        categoria: int,
        data_inicio: Date | None,
        data_fim: Date | None,
        dia_recorrente: int | None,
        mes_recorrente: int | None,
    ) -> bool:
        if self.considerar_liberacoes_ponto is False:
            return False
        if unidade is None:
            base_qs = Liberacao.objects.filter(uo__isnull=True)
        else:
            base_qs = Liberacao.objects.filter(Q(uo__isnull=True) | Q(uo=unidade))

        if categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            if not (mes_recorrente and dia_recorrente):
                return False  # validação de campos acontece no clean()
            qs = base_qs.filter(tipo=TIPO_RECORRENTE_PTO).annotate(mes=ExtractMonth('data_inicio'), dia=ExtractDay('data_inicio'))
            return qs.filter(mes=mes_recorrente, dia=dia_recorrente).exists()
        else:
            # Pontual (FERIADO/RECESSO): checar sobreposição + colisão com recorrentes
            if not data_inicio:
                return False  # validação de campos acontece no clean()
            data_fim = data_fim or data_inicio

            # 1) Sobreposição com pontuais (feriado/recesso) do Ponto
            qs = base_qs.filter(tipo__in=[TIPO_FERIADO_PONTO, TIPO_RECESSO_PONTO]).annotate(fim_norm=Coalesce('data_fim', 'data_inicio'))
            colisao_pontual = qs.filter(Q(data_inicio__lte=data_fim) & Q(fim_norm__gte=data_inicio))
            if colisao_pontual.exists():
                return True
            # 2) Qualquer dia do intervalo bate em recorrente do Ponto?
            recorrentes_qs = base_qs.filter(tipo=TIPO_RECORRENTE_PTO).annotate(mes=ExtractMonth('data_inicio'), dia=ExtractDay('data_inicio'))
            recorrentes = recorrentes_qs.values('mes', 'dia')
            recorrentes_set = {(recorrente['mes'], recorrente['dia']) for recorrente in recorrentes}

            cur = data_inicio
            while cur <= data_fim:
                if (cur.month, cur.day) in recorrentes_set:
                    return True
                cur += timedelta(days=1)
            return False

    def clean(self):
        cleaned_data = super().clean()
        categoria = cleaned_data.get('categoria')
        data_inicio = cleaned_data.get('data_inicio')
        data_fim = cleaned_data.get('data_fim')
        mes_recorrente = cleaned_data.get('mes_recorrente')
        dia_recorrente = cleaned_data.get('dia_recorrente')
        unidade = cleaned_data.get('uo')

        if categoria in [CategoriaLiberacao.FERIADO, CategoriaLiberacao.RECESSO]:
            if not data_inicio or not data_fim:
                raise forms.ValidationError('Para liberações pontuais, é necessário informar o intervalo (data de início e de data de fim).')
            if mes_recorrente or dia_recorrente:
                raise forms.ValidationError('Para liberações pontuais, não deve ser informado mês/dia recorrente.')
            if data_fim < data_inicio:
                raise forms.ValidationError('Data fim não pode ser anterior à data início.')
            # limpa recorrência
            cleaned_data['mes_recorrente'] = None
            cleaned_data['dia_recorrente'] = None
        elif categoria == CategoriaLiberacao.FERIADO_RECORRENTE:
            if not mes_recorrente or not dia_recorrente:
                raise forms.ValidationError('Para liberações recorrentes, é necessário informar mês e dia.')
            if data_inicio or data_fim:
                raise forms.ValidationError('Para liberações recorrentes, não deve ser informado intervalo (data de início e data de fim).')
            # limpa intervalo
            cleaned_data['data_inicio'] = None
            cleaned_data['data_fim'] = None
        # Verificar conflito com liberações de ponto (feriado/recesso) do Ponto
        if self.verificar_liberacao_ponto(unidade, categoria, data_inicio, data_fim, dia_recorrente, mes_recorrente):
            raise forms.ValidationError('Já existe uma liberação de ponto (feriado/recesso) cadastrada que conflita com esta.')
        return cleaned_data

    def save(self, commit=True):
        instance: LiberacaoProgramada = super().save(commit=False)
        if commit:
            instance.save(validate=self.considerar_liberacoes_ponto)
        return instance
