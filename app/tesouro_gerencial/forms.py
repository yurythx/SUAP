import os
import tempfile

from djtools import forms
from rh.models import UnidadeOrganizacional
from tesouro_gerencial.importador import ImportadorExecNE, ImportadorGRU, ImportadorNotaCredito, ImportadorRAP


class ConfiguracaoForm(forms.FormPlus):
    servidor_email = forms.CharFieldPlus(
        label='Servidor e-mail', help_text='Servidor de e-mail que recebe os CSV do Tesouro Gerencial', required=False
    )
    email = forms.CharFieldPlus(label='E-mail', help_text='E-mail que recebe os CSV do Tesouro Gerencial', required=False)
    senha_email = forms.CharFieldPlus(label='Senha e-mail', help_text='Senha do e-mail que recebe os CSV do Tesouro Gerencial', required=False)


class VariavelFom(forms.FormPlus):
    METHOD = 'GET'
    campus = forms.ModelChoiceFieldPlus(queryset=UnidadeOrganizacional.objects.uo())
    ano = forms.IntegerFieldPlus()


class CampiFom(forms.FormPlus):
    METHOD = 'GET'

    DEST_EXEC = 'DEST_EXEC'
    LOA_EXEC = 'LOA_EXEC'
    RECCAPT = 'RECCAPT'
    _20RL_LOA = '20RL_LOA'
    GCC = 'GCC'
    GTO_LOA = 'GTO_LOA'
    FGPE = 'fGPE'
    FGTO = 'fGTO'
    FGOC = 'fGOC'
    FGCI = 'fGCI'
    FGCO = 'fGCO'
    VARIAVEL_CHOICES = (
        (DEST_EXEC, DEST_EXEC),
        (LOA_EXEC, LOA_EXEC),
        (RECCAPT, RECCAPT),
        (_20RL_LOA, _20RL_LOA),
        (GCC, GCC),
        (GTO_LOA, GTO_LOA),
        (FGPE, FGPE),
        (FGTO, FGTO),
        (FGOC, FGOC),
        (FGCI, FGCI),
        (FGCO, FGCO),
    )

    variavel = forms.ChoiceField(label='Variável', choices=VARIAVEL_CHOICES)
    ano = forms.IntegerFieldPlus()


class ImportacaoTesouroGerencial(forms.FormPlus):
    MOVIMENTACOES_CREDITO = 0
    NOTA_EMPENHO = 1
    RESTOS_PAGAR = 2
    ARRECADACAO_GRU = 3
    RELATORIO_CHOICES = (
        (MOVIMENTACOES_CREDITO, 'Movimentações de crédito'),
        (NOTA_EMPENHO, 'Exec NE Emitido, Liquidado e Pago'),
        (RESTOS_PAGAR, 'RAP PROC N PROC INSCRITOS'),
        (ARRECADACAO_GRU, 'ARRECADAÇÃO POR GRU'),
    )

    relatorio = forms.ChoiceField(label='Relatório', choices=RELATORIO_CHOICES)
    arquivo = forms.FileField(label='Arquivo')

    def processar(self):
        ClasseImportador = None
        relatorio = int(self.cleaned_data['relatorio'])
        if relatorio == self.MOVIMENTACOES_CREDITO:
            ClasseImportador = ImportadorNotaCredito
        elif relatorio == self.NOTA_EMPENHO:
            ClasseImportador = ImportadorExecNE
        elif relatorio == self.RESTOS_PAGAR:
            ClasseImportador = ImportadorRAP
        elif relatorio == self.ARRECADACAO_GRU:
            ClasseImportador = ImportadorGRU

        arquivo = self.cleaned_data['arquivo']
        tmp = tempfile.NamedTemporaryFile(suffix='.' + arquivo.name.split('.')[-1], delete=False)
        tmp.write(arquivo.read())
        tmp.close()

        importador = ClasseImportador(arquivos=[tmp.name], encoding='utf-16-le')
        importador.run()

        os.unlink(tmp.name)
