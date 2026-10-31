from djtools import forms
from documento_eletronico.models import ModeloDocumento, TipoDocumento
from rh.models import Papel, Setor


class ConfiguracaoForm(forms.FormPlus):
    modelo_resolucao_consup = forms.ModelChoiceFieldPlus(
        ModeloDocumento.ativos, label='Modelo de Resolução do CONSUP', help_text='Modelo de resolução para aprovação do PAINT', required=False
    )
    modelo_ordem_servico = forms.ModelChoiceFieldPlus(
        ModeloDocumento.ativos, label='Modelo Ordem Serviço', help_text='Ordem de Serviço Auditória', required=False
    )

    setor_auditor_chefe = forms.ModelChoiceFieldPlus(
        Setor.objects, label='Setor do Auditor Chefe', help_text='Setor do Auditor Chefe.', required=False
    )
    papel_auditor_chefe = forms.ModelChoiceFieldPlus(
        Papel.objects.none(), label='Papel do Auditor Chefe', help_text='Papel do Auditor Chefe.', required=False
    )

    tipo_relatorio_auditoria = forms.ModelChoiceField(
        TipoDocumento.ativos.all(), label='Tipo do relatório de auditoria', help_text='Tipo do relatório de auditoria', required=False
    )

    considerar_liberacoes_ponto = forms.BooleanField(
        label='Considerar liberações de ponto no cálculo da carga horária prevista para auditoria',
        help_text='Se marcado, as liberações de ponto (feriados, recessos, etc) serão descontadas da carga horária prevista para auditoria.',
        required=False,
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        auditor_papeis = Papel.objects.filter(detalhamento__icontains='AUDITOR', tipo_papel=Papel.TIPO_PAPEL_FUNCAO, data_fim__isnull=True)
        self.fields['papel_auditor_chefe'].queryset = auditor_papeis
