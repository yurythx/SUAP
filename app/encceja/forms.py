import datetime
import re
from decimal import Decimal

import pandas as pd
from dateutil.parser import parse

from comum.models import Ano
from django.core.exceptions import ValidationError
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from djtools.utils import mask_cpf
from edu.models import ConfiguracaoCertificadoENEM, SolicitacaoCertificadoENEM
from encceja.models import Avaliacao, Configuracao, Pontuacao, Solicitacao
from rh.models import UnidadeOrganizacional


class FiltroQuantitativoForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ModelChoiceField(Ano.objects.filter(ano__gte=2010, ano__lte=datetime.date.today().year), label='Ano de Emissão', required=False)
    exame = forms.ChoiceField(label='Exame', required=False, choices=[('', '-------'), ('ENEM', 'ENEM'), ('ENCCEJA', 'ENCCEJA')])

    def processar(self):
        ano = self.cleaned_data.get('ano')
        exame = self.cleaned_data.get('exame')
        return self.get_registros(ano, exame)

    def get_registros(self, ano=None, exame=None):
        registros = []
        pks = (
            Solicitacao.objects.filter(cancelada=False)
            .filter(pontuacao__avaliacao__tipo='Enem')
            .filter(pontuacao__avaliacao__tipo__contains='Encceja Nacional')
            .order_by('id')
            .values_list('id', flat=True)
            .distinct()
        )
        if not exame or exame == 'ENCCEJA':
            qs_configuracao = Configuracao.objects.all()
            if ano:
                qs_configuracao = qs_configuracao.filter(ano__ano__lte=ano.ano)
            for configuracao in qs_configuracao.order_by('ano'):
                qs_certificado_regular = Solicitacao.objects.exclude(pk__in=pks).filter(
                    cancelada=False, configuracao=configuracao, tipo_certificado=Solicitacao.COMPLETO, atendida=True, ppl=False
                )
                qs_certifiado_ppl = Solicitacao.objects.exclude(pk__in=pks).filter(
                    cancelada=False, configuracao=configuracao, tipo_certificado=Solicitacao.COMPLETO, atendida=True, ppl=True
                )
                qs_declaracao_regular = Solicitacao.objects.exclude(pk__in=pks).filter(
                    cancelada=False, configuracao=configuracao, tipo_certificado=Solicitacao.PARCIAL, atendida=True, ppl=False
                )
                qs_declaracao_ppl = Solicitacao.objects.exclude(pk__in=pks).filter(
                    cancelada=False, configuracao=configuracao, tipo_certificado=Solicitacao.PARCIAL, atendida=True, ppl=True
                )
                if ano:
                    qs_certificado_regular = qs_certificado_regular.filter(data_emissao__year=ano.ano)
                    qs_certifiado_ppl = qs_certifiado_ppl.filter(data_emissao__year=ano.ano)
                    qs_declaracao_regular = qs_declaracao_regular.filter(data_emissao__year=ano.ano)
                    qs_declaracao_ppl = qs_declaracao_ppl.filter(data_emissao__year=ano.ano)
                registros.append(
                    (
                        f'ENCCEJA {configuracao.ano}',
                        configuracao.data_primeira_prova,
                        qs_certificado_regular.count(),
                        qs_certifiado_ppl.count(),
                        qs_declaracao_regular.count(),
                        qs_declaracao_ppl.count(),
                    )
                )
        if not exame or exame == 'ENEM':
            qs_configuracao = ConfiguracaoCertificadoENEM.objects.all()
            if ano:
                qs_configuracao = qs_configuracao.filter(ano__ano__lte=ano.ano)
            for configuracao in qs_configuracao.order_by('ano'):
                qs_certificado_regular = SolicitacaoCertificadoENEM.objects.filter(
                    configuracao_certificado_enem=configuracao, tipo_certificado=1, razao_indeferimento__isnull=True
                )
                qs_declaracao_regular = SolicitacaoCertificadoENEM.objects.filter(
                    configuracao_certificado_enem=configuracao, tipo_certificado=2, razao_indeferimento__isnull=True
                )
                if ano:
                    qs_certificado_regular = qs_certificado_regular.filter(data_solicitacao__year=ano.ano)
                    qs_declaracao_regular = qs_declaracao_regular.filter(data_solicitacao__year=ano.ano)
                registros.append(
                    (
                        f'ENEM {configuracao.ano}',
                        configuracao.data_primeira_prova,
                        qs_certificado_regular.count(),
                        0,
                        qs_declaracao_regular.count(),
                        0,
                    )
                )

        solicitacoes_mistas = {}
        for solicitacao in Solicitacao.objects.filter(pk__in=pks):
            if solicitacao.atendida and (not ano or solicitacao.data_emissao.year == ano.ano):
                anos = set(solicitacao.pontuacao_set.values_list('avaliacao__ano__ano', flat=True).order_by('avaliacao__ano__ano').distinct())
                chave = ('ENCCEJA/ENEM {}'.format(','.join(anos and [str(ano) for ano in anos] or [])),)
                if chave not in solicitacoes_mistas:
                    solicitacoes_mistas[chave] = [0, 0, 0, 0]
                if solicitacao.tipo_certificado == Solicitacao.COMPLETO and not solicitacao.ppl:
                    solicitacoes_mistas[chave][0] += 1
                if solicitacao.tipo_certificado == Solicitacao.COMPLETO and solicitacao.ppl:
                    solicitacoes_mistas[chave][1] += 1
                if solicitacao.tipo_certificado == Solicitacao.PARCIAL and not solicitacao.ppl:
                    solicitacoes_mistas[chave][2] += 1
                if solicitacao.tipo_certificado == Solicitacao.PARCIAL and solicitacao.ppl:
                    solicitacoes_mistas[chave][3] += 1
        for chave in solicitacoes_mistas:
            registros.append(
                (
                    chave,
                    '-',
                    solicitacoes_mistas[chave][0],
                    solicitacoes_mistas[chave][1],
                    solicitacoes_mistas[chave][2],
                    solicitacoes_mistas[chave][3],
                )
            )
        return registros


class ImportarForm(forms.FormPlus):
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.campi().all(),
        widget=AutocompleteWidget(search_fields=UnidadeOrganizacional.SEARCH_FIELDS),
        label='Campus',
        required=False,
    )
    configuracao = forms.ModelChoiceField(
        Configuracao.objects.all(), widget=AutocompleteWidget(search_fields=Configuracao.SEARCH_FIELDS), label='Configuração', required=False
    )
    avaliacao = forms.ModelChoiceField(
        Avaliacao.objects.all(), widget=AutocompleteWidget(search_fields=Avaliacao.SEARCH_FIELDS), label='Avaliação', required=False
    )
    arquivo = forms.FileFieldPlus(label='Planilha')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['avaliacao'].queryset = self.fields['avaliacao'].queryset.exclude(tipo='Enem')

    def processar(self):
        uo = self.cleaned_data.get('uo')
        configuracao = self.cleaned_data.get('configuracao')
        avaliacao = self.cleaned_data.get('avaliacao')
        arquivo = self.cleaned_data.get('arquivo')
        colunas_areas = ((1, 11), (2, 10), (3, 12), (4, 13))

        df = pd.read_excel(arquivo, header=None, dtype={0: str})

        for _index, row in df.iloc[1:].iterrows():
            try:
                cpf = mask_cpf(row.iloc[0])
                solicitacao = Solicitacao.objects.filter(cpf=cpf, avaliacao_redacao=avaliacao, configuracao=configuracao).first()
                if not solicitacao:
                    solicitacao = Solicitacao()
                solicitacao.configuracao = configuracao
                solicitacao.uo = uo
                solicitacao.avaliacao_redacao = avaliacao
                solicitacao.pontuacao_redacao = 0 if pd.isna(row.iloc[14]) else Decimal(row.iloc[14] or 0)
                solicitacao.cpf = cpf
                solicitacao.inscricao = row.iloc[1]
                solicitacao.nome = row.iloc[2]
                solicitacao.data_nascimento = parse(row.iloc[20], dayfirst=True)
                for _area_conhecimento_id, coluna in colunas_areas:
                    if Decimal(re.sub('[^0-9]', '', str(row.iloc[coluna])) or 0):
                        solicitacao.save()
                        break
                if solicitacao.pk:
                    for area_conhecimento_id, coluna in colunas_areas:
                        if row.iloc[coluna]:
                            pontuacao = Pontuacao.objects.filter(
                                solicitacao=solicitacao, avaliacao=avaliacao, area_conhecimento=area_conhecimento_id
                            ).first()
                            if not pontuacao:
                                pontuacao = Pontuacao()
                            pontuacao.solicitacao = solicitacao
                            pontuacao.avaliacao = avaliacao
                            pontuacao.area_conhecimento_id = area_conhecimento_id
                            pontuacao.valor = Decimal(re.sub('[^0-9]', '', str(row.iloc[coluna])) or 0)
                            pontuacao.save()
            except Exception as e:
                raise ValidationError(f'Ocorreu um erro ao processar a linha {_index + 1}: {e!s}') from e


class CancelamentoSolicitacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Solicitacao
        fields = ('motivo_cancelamento',)


class AtualizarConfiguracaoSolicitacaoForm(forms.FormPlus):
    INFO = 'Ao atualizar a configuração de uma solicitação se houver alteração no modelo a versão antiga do certificado será invalidada.'
    senha = forms.PasswordField()


class SolicitacaoForm(forms.ModelFormPlus):
    class Meta:
        model = Solicitacao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['uo'].queryset = UnidadeOrganizacional.objects.campi()
        self.fields['pontuacao_redacao'].required = False

    def clean(self):
        clean = super().clean()
        configuracao_encceja = self.cleaned_data.get('configuracao')
        pontuacao_redacao = self.cleaned_data.get('pontuacao_redacao')

        if configuracao_encceja and configuracao_encceja.nota_redacao_obrigatoria and not pontuacao_redacao:
            self.add_error('pontuacao_redacao', 'Pontuação da redação é obrigatório')

        return clean
