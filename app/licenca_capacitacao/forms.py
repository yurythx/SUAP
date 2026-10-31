import datetime

import pandas as pd
from django.conf import settings
from django.db import transaction

from comum.models import Ano
from djtools import forms
from djtools.utils.pdf import full_check_file
from licenca_capacitacao.models import (
    AnexosEdital,
    AnexosPedidoLicCapacitacaoSubmissao,
    EditalLicCapacitacao,
    LicCapacitacaoPorDia,
    PedidoLicCapacitacao,
    ServidorComplementar,
)
from rh.models import Servidor


class FiltroQuadroLicencaCapacitacaoForm(forms.FormPlus):
    ano = forms.ModelChoiceField(queryset=Ano.objects, label='Ano', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        id_anos = LicCapacitacaoPorDia.objects.values_list('ano', flat=True).distinct()
        self.fields['ano'].queryset = Ano.objects.filter(id__in=id_anos)
        self.fields['ano'].initial = Ano.objects.get(ano=datetime.date.today().year).id


class CriarProcessamentoForm(forms.FormPlus):
    titulo = forms.CharFieldPlus(label='Título')
    senha = forms.PasswordField()


class EditarOrdemClassificacaoGestaoForm(forms.FormPlus):
    ordem_colocacao = forms.IntegerFieldPlus(label='Ordem colocação')

    def __init__(self, *args, **kwargs):
        self.ordem_colocacao_inicial = kwargs.pop('ordem_colocacao_inicial', None)
        super().__init__(*args, **kwargs)
        self.fields['ordem_colocacao'].initial = self.ordem_colocacao_inicial


class ImportarResultadoFinalForm(forms.FormPlus):
    planilha = forms.FileFieldPlus(
        help_text='O arquivo deve ter apenas os pedidos APROVADOS DE FORMA DEFINITIVA, '
        'no formato "xlsx", sem cabeçalho, contendo apenas as seguintes '
        'colunas: Identificador do Pedido, Matrícula e a Ordem de Classificação.',
        required=True,
    )

    def __init__(self, edital, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.edital = edital
        self.resultados = []

    def clean(self):
        arquivo = self.cleaned_data.get('planilha')

        if arquivo:
            # Valida se eh XLS
            # -------------------------
            try:
                df = pd.read_excel(arquivo, header=None)
            except Exception:
                raise forms.ValidationError('Não foi possível processar a planilha. Verfique se o formato do arquivo é .xlsx,')

            # Valida se existem 3 colunas
            # -------------------------
            if df.shape[1] < 3:
                raise forms.ValidationError('A planilha não contém as 4 colunas solicitadas.')

            erro = []

            def get_str(n):
                if type(n) is not str:
                    return str(n).split('.')[0]
                else:
                    return n

            for index, row in df.iterrows():
                la = index + 1

                # Valida se cada uma das colunas tem os dados esperados
                #   Dados solicitados na planilha
                #     - Identificador do Pedido, Matrícula e a Ordem de Classificação

                # Valida Identificador do Pedido
                # ----------------
                pedido = get_str(row.iloc[0])
                if pedido:
                    if PedidoLicCapacitacao.get_pedidos_para_processamento(self.edital).filter(id=int(pedido)).exists():
                        pedido = PedidoLicCapacitacao.objects.get(id=pedido)
                    else:
                        erro.append(f'Não existe pedido neste edital para o identificador informado na linha {la}')
                else:
                    erro.append(f'Identficador inválido na linha {la}')

                # Valida Matricula
                # ----------------
                matricula = get_str(row.iloc[1])
                if matricula:
                    servidor = Servidor.objects.filter(matricula=matricula)
                    if servidor:
                        if not EditalLicCapacitacao.existe_algum_pedido_submetido_do_servidor_no_edital(self.edital, servidor[0]):
                            erro.append(f'Neste edital não existe pedido associado ao servidor da matrícula da linha {la}')
                    else:
                        erro.append(f'Não existe servidor associado a matrícula da linha {la}')
                else:
                    erro.append(f'Matrícula inválida na linha {la}')

                # Valida ordem
                # ----------------
                ordem = get_str(row.iloc[2])
                try:
                    ordem = int(ordem)
                except forms.ValidationError:
                    erro.append(f'Ordem inválida "{ordem}" na linha {la}')

                # Carrega dados da planilha
                # ----------------
                if not erro:
                    dados_aprovado = {'pedido': pedido, 'ordem': ordem}
                    self.resultados.append(dados_aprovado)

            if erro:
                raise forms.ValidationError('A planilha contém o(s) seguinte(s) erro(s): </br>{}'.format('</br> '.join(erro)))

        return self.cleaned_data

    @transaction.atomic
    def processar(self):
        for result in self.resultados:
            pedido = result.get('pedido')
            pedido.aprovado_resultado_final = True
            pedido.ordem_classificacao_resultado_final = result.get('ordem')
            pedido.ordem_classificacao_resultado_final_gestao = result.get('ordem')
            pedido.aprovado_em_definitivo = True
            pedido.save()


class AnexosEditalForm(forms.ModelFormPlus):
    class Meta:
        model = AnexosEdital
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE

    def clean_arquivo(self):
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content


class AnexosPedidoLicCapacitacaoSubmissaoForm(forms.ModelFormPlus):
    class Meta:
        model = AnexosPedidoLicCapacitacaoSubmissao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].max_file_size = settings.DEFAULT_FILE_UPLOAD_MAX_SIZE

    def clean_arquivo(self):
        content = self.cleaned_data.get('arquivo', None)
        full_check_file(content)
        return content


class SolicitarDesistenciaForm(forms.ModelFormPlus):
    class Meta:
        model = PedidoLicCapacitacao
        fields = ('solicitacao_desistencia',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['solicitacao_desistencia'].required = True

    def save(self, *args, **kwargs):
        self.instance.data_solicitacao_desistencia = datetime.datetime.now()
        return super().save(*args, **kwargs)


class ServidorComplementarForm(forms.ModelFormPlus):
    class Meta:
        model = ServidorComplementar
        exclude = ()

    def clean(self):
        servidor = self.cleaned_data.get('servidor')
        edital = self.cleaned_data.get('edital')

        existe_como_servidor = EditalLicCapacitacao.get_servidores_efetivo_exercicio().filter(id=servidor.id).exists()
        existe_como_servidor_complementar = ServidorComplementar.objects.filter(servidor=servidor, edital=edital).exists()
        if existe_como_servidor or existe_como_servidor_complementar:
            raise forms.ValidationError('O servidor {} já existe no edital {}')

        return self.cleaned_data


class CancelarPedidoGestaoForm(forms.FormPlus):
    justificativa = forms.CharField(widget=forms.Textarea, required=True, label='Justificativa')
    senha = forms.PasswordField()


class BuscarServidoresForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'

    buscar_str = forms.CharField(label='Nome/Matrícula Servidor', required=False)

    choices = [['t', 'Todos'], ['da', 'Data foi ajustada'], ['dna', 'Data não foi ajustada']]
    agrupamento = forms.ChoiceField(required=False, choices=choices, label='Agrupamento:')


class EditarDataIniExercicioForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Nova data de início de exercício', required=True)


class ConfiguracaoForm(forms.FormPlus):
    ANALISE_CHOICES = [
        ('fim_submissao', 'Somente após o término das inscrições (padrão)'),
        ('inicio_submissao', 'Desde o início das inscrições'),
    ]

    analise_permitida_desde = forms.ChoiceField(
        choices=ANALISE_CHOICES,
        label='Quando permitir análise de solicitações de alteração',
        required=True,
    )
