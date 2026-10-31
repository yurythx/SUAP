import calendar
from datetime import datetime
from decimal import Decimal

from dateutil.relativedelta import relativedelta
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max
from django.forms.models import BaseInlineFormSet

from calculos_pagamentos.models import (
    Calculo,
    CalculoCD,
    CalculoDispensaFG,
    CalculoExoneracaoCD,
    CalculoFG,
    CalculoProgressao,
    CalculoSubstituicao,
    CalculoTerminoContrato,
    CalculoTerminoContratoInterpLibras,
    CalculoTerminoContratoProfSubs,
    DetalhamentoInsalubridade,
    DetalhamentoIQ,
    DetalhamentoMudancaRegime,
    DetalhamentoPericulosidade,
    DetalhamentoProgressao,
    NivelVencimento,
    NivelVencimentoTAEPorClasseEPadrao,
    ValorAlimentacao,
    ValorAuxilioPreEscolar,
    ValorPorFuncao,
    ValorPorNivelVencimento,
    ValorPorNivelVencimentoDocente,
    ValorRetribuicaoTitulacao,
)
from calculos_pagamentos.models.calculos import TIPO_CALCULO_CHOICES, padrao_choices
from comum.models import FuncaoCodigo
from comum.utils import get_uo
from djtools import forms
from djtools.forms import AutocompleteWidget
from djtools.templatetags.filters import format_
from djtools.utils import HMTLParaStringUnicode
from documento_eletronico.models import ModeloDocumento
from rh.models import CargoClasse, Servidor, Titulacao, UnidadeOrganizacional
from rh.utils import roman_to_int


class ConfiguracaoForm(forms.FormPlus):
    modelo_calculo_substituicao = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para Cálculo de Substituição',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    modelo_declaracao_nao_ajuizamento = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para declaração de não ajuizamento',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    modelo_amparo_legal = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para amparo legal',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    modelo_nota_tecnica_sem_portaria = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para nota técnica sem portaria',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    modelo_nota_tecnica_com_portaria = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para nota técnica com portaria',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    modelo_ficha_calculo = forms.ModelChoiceField(
        ModeloDocumento.objects.filter(ativo=True),
        label='Modelo de documento para ficha de cálculo',
        widget=AutocompleteWidget(search_fields=ModeloDocumento.SEARCH_FIELDS),
        required=False,
    )
    for choice in TIPO_CALCULO_CHOICES:
        id_campo, nome_campo = choice
        locals()[f'calculo_{id_campo}'] = forms.BooleanField(label=f'Habilitar {nome_campo}?', initial=True, required=False)


# # # CLASSES GERAIS PARA CÁLCULOS: FORMULÁRIOS, FORMSETS E MÉTODOS # # #


def getCalculoEIsTAE(formSet):
    # FeriasFormSet
    if hasattr(formSet.instance, 'calculo'):
        calculo = formSet.instance.calculo
    # PeriodoFormSet
    else:
        calculo = formSet.instance
    if calculo.servidor.eh_tecnico_administrativo:
        is_TAE = True
    elif calculo.servidor.eh_docente:
        is_TAE = False
    return calculo, is_TAE


# IFMA/Tássio: Calcula pagamento entre datas com valor mensal único
def calcula_pagamento_proporcional(data_inicio, data_fim, valor_mensal):
    dias = (data_fim - data_inicio).days + 1
    valor_diario = valor_mensal / 30
    pagamento = valor_diario * dias
    return pagamento


# IFMA/Tássio: Calcula pagamento de valor de vencimento entre datas p/ um nivel com valores diferentes dependendo da data
def calcula_vencimento_mensal(data_inicio, data_fim, nivel, jornada):
    if nivel.categoria == 'tecnico_administrativo':
        valores = (
            ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__lte=data_inicio, data_fim__isnull=True)
            or ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__lte=data_inicio, data_fim__gte=data_fim)
            or ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__isnull=True, data_fim__gte=data_fim)
        )
    else:
        valores = (
            ValorPorNivelVencimentoDocente.objects.filter(nivel=nivel, jornada_trabalho=jornada, data_inicio__lte=data_inicio, data_fim__isnull=True)
            or ValorPorNivelVencimentoDocente.objects.filter(
                nivel=nivel, jornada_trabalho=jornada, data_inicio__lte=data_inicio, data_fim__gte=data_fim
            )
            or ValorPorNivelVencimentoDocente.objects.filter(nivel=nivel, jornada_trabalho=jornada, data_inicio__isnull=True, data_fim__gte=data_fim)
        )
    valorpornivelvencimento = valores[0]
    valor_mensal = valorpornivelvencimento.valor
    if (1, calendar.monthrange(data_inicio.year, data_inicio.month)[1]) == (data_inicio.day, data_fim.day):  # Mês cheio
        return valor_mensal
    else:
        return calcula_pagamento_proporcional(data_inicio, data_fim, valor_mensal)


# IFMA/Tássio: Calcula pagamento de retribuição por titulação entre datas p/ nivel-jornada-titulacao com valores diferentes dependendo da data
def calcula_rt_mensal(data_inicio, data_fim, nivel, jornada, titulacao):
    valores = (
        ValorRetribuicaoTitulacao.objects.filter(
            nivel=nivel, jornada_trabalho=jornada, titulacoes=titulacao, data_inicio__lte=data_inicio, data_fim__isnull=True
        )
        or ValorRetribuicaoTitulacao.objects.filter(
            nivel=nivel, jornada_trabalho=jornada, titulacoes=titulacao, data_inicio__lte=data_inicio, data_fim__gte=data_fim
        )
        or ValorRetribuicaoTitulacao.objects.filter(
            nivel=nivel, jornada_trabalho=jornada, titulacoes=titulacao, data_inicio__isnull=True, data_fim__gte=data_fim
        )
    )
    valorretribuicaotitulacao = valores[0]
    valor_mensal = valorretribuicaotitulacao.valor
    if (1, calendar.monthrange(data_inicio.year, data_inicio.month)[1]) == (data_inicio.day, data_fim.day):  # Mês cheio
        return valor_mensal
    else:
        return calcula_pagamento_proporcional(data_inicio, data_fim, valor_mensal)


# IFMA/Tássio: Calcula valor de pagamento por desempenho de FG entre datas, com valores diferentes dependendo da data
def calcula_valor_funcao_mensal(data_inicio, data_fim, funcao):
    valores = (
        ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio, data_fim__isnull=True)
        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio, data_fim__gte=data_fim)
        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__isnull=True, data_fim__gte=data_fim)
    )
    vpf = valores[0]
    valor_mensal = vpf.valor
    if (1, calendar.monthrange(data_inicio.year, data_inicio.month)[1]) != (data_inicio.day, data_fim.day):  # Mês quebrado
        valor_mensal = calcula_pagamento_proporcional(data_inicio, data_fim, valor_mensal)
    return valor_mensal


# IFMA/Tássio: Calcula valores detalhados de pagamento por desempenho de FG entre datas, com valores diferentes dependendo da data
def calcula_valores_fg_detalhados_mensal(data_inicio, data_fim, funcao):
    valores = (
        ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio, data_fim__isnull=True)
        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio, data_fim__gte=data_fim)
        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__isnull=True, data_fim__gte=data_fim)
    )
    vpf = valores[0]
    valoresfuncaodetalhados = vpf.valoresfuncaodetalhados
    venc_mensal = valoresfuncaodetalhados.valor_venc
    gadf_mensal = valoresfuncaodetalhados.valor_gadf
    age_mensal = valoresfuncaodetalhados.valor_age
    if (1, calendar.monthrange(data_inicio.year, data_inicio.month)[1]) != (data_inicio.day, data_fim.day):  # Mês quebrado
        venc_mensal = calcula_pagamento_proporcional(data_inicio, data_fim, venc_mensal)
        gadf_mensal = calcula_pagamento_proporcional(data_inicio, data_fim, gadf_mensal)
        age_mensal = calcula_pagamento_proporcional(data_inicio, data_fim, age_mensal)
    return venc_mensal, gadf_mensal, age_mensal


# IFMA/Tássio: Retorna o valor do auxílio alimentação de um mês específico.
def get_auxilio_alimentacao(data):
    valores = (
        ValorAlimentacao.objects.filter(data_inicio__lte=data, data_fim__isnull=True)
        or ValorAlimentacao.objects.filter(data_inicio__lte=data, data_fim__gte=data)
        or ValorAlimentacao.objects.filter(data_inicio__isnull=True, data_fim__gte=data)
    )
    va = valores[0]
    valor_mensal = va.valor
    return valor_mensal


# IFMA/Tássio: Retorna o valor do auxílio pré-escolar de um mês específico.
def get_auxilio_preescolar(data):
    valores = (
        ValorAuxilioPreEscolar.objects.filter(data_inicio__lte=data, data_fim__isnull=True)
        or ValorAuxilioPreEscolar.objects.filter(data_inicio__lte=data, data_fim__gte=data)
        or ValorAuxilioPreEscolar.objects.filter(data_inicio__isnull=True, data_fim__gte=data)
    )
    return valores[0].valor


# IFMA/Tássio: Retorna o vencimento de TAE proporcional à jornada trabalhada com base na jornada básica do cargo.


def vencimento_tae_proporcional_a_ch_do_cargo(vencimento, jornada, servidor):
    if servidor.cargo_emprego.codigo in ('061062', '701047', '701048'):  # Médicos
        ch_carreira = 20
    elif servidor.cargo_emprego.codigo == '701045':  # Jornalista
        ch_carreira = 25
    elif servidor.cargo_emprego.codigo == '701063':  # Otontologo 30H
        ch_carreira = 30
    else:
        ch_carreira = 40
    return vencimento * (Decimal(jornada.codigo) / ch_carreira)


# IFMA/Tássio: Criado em outubro de 2017
class NivelVencimentoTAEPorClasseEPadraoForm(forms.ModelFormPlus):
    class Meta:
        model = NivelVencimentoTAEPorClasseEPadrao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        servidores = Servidor.objects.ativos().filter(eh_tecnico_administrativo=True)
        classes_servidores = servidores.filter(cargo_classe__isnull=False).values_list('cargo_classe', flat=True).order_by('cargo_classe').distinct()
        classesTAE = CargoClasse.objects.filter(id__in=classes_servidores)

        self.fields['cargo_classe'].queryset = classesTAE


# IFMA/Tássio: Criado em outubro de 2017
class ValorPorNivelVencimentoTAEForm(forms.ModelFormPlus):
    class Meta:
        model = ValorPorNivelVencimento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nivel'].queryset = NivelVencimento.objects.filter(categoria='tecnico_administrativo')


# IFMA/Tássio: Criado em outubro de 2017
class ValorPorNivelVencimentoDocenteForm(forms.ModelFormPlus):
    class Meta:
        model = ValorPorNivelVencimentoDocente
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nivel'].queryset = NivelVencimento.objects.filter(categoria='docente')


# IFMA/Tássio: Criado em outubro de 2017
class ValorRetribuicaoTitulacaoForm(forms.ModelFormPlus):
    class Meta:
        model = ValorRetribuicaoTitulacao
        exclude = ()

    titulacoes = forms.MultipleModelChoiceFieldPlus(
        required=True,
        label='Titulações',
        # IFMA/Tássio: id 24 a 27 são aperfeiçoamento, especialização, mestrado e doutorado.
        # IFMA/Tássio: id 48 a 50 são rscI+graduação, rscII+especialização e rscIII+mestrado.
        queryset=Titulacao.objects.filter(codigo__gte='24', codigo__lte='27') | Titulacao.objects.filter(codigo__gte='48', codigo__lte='50'),
    )


# IFMA/Tássio
class PortariaFisicaFormSet(BaseInlineFormSet):
    def __init__(self, *args, **kwargs):
        if self.request.GET.get('portaria_id') is not None:
            portaria_id = self.request.GET.get('portaria_id')
            PortariaProgressaoTae = apps.get_model('atos', 'portariaprogressaotae')
            if PortariaProgressaoTae:
                portaria = PortariaProgressaoTae.objects.get(pk=portaria_id)
                initial = [
                    {
                        'numero': portaria.numero_portaria,
                        'data_portaria': portaria.data,
                        'campus': portaria.campus.id,
                        'processo': portaria.processo.id,
                    },
                ]
                kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

    def clean(self):
        super().clean()

        # Primeiro testa se há pelo menos 1 portaria
        non_empty_forms = 0
        for form in self.forms:
            if form.cleaned_data:
                non_empty_forms += 1
        if non_empty_forms - len(self.deleted_forms) < 1:
            raise forms.ValidationError('Ao menos uma portaria deve ser informada.')

        # Verifica erros de formulário
        for form in self.forms:
            if not form.is_valid():
                raise ValidationError('Corrija o erro abaixo.')  # outros erros

    # IFMA/Tássio: Esse save é importante pois as portarias preenchidas com valores iniciais não estavam sendo salvas!!
    def save(self, commit=True):
        if self.request.GET.get('portaria_id') is not None:
            calculo = self.instance
            for form in self.forms:
                form.instance.calculo = calculo
                form.instance.save()
        return super().save(commit)


# Formulário para arquivo de pagamento
class ArquivoPagamentoForm(forms.FormPlus):
    METHOD = 'GET'

    mes = forms.IntegerField(label='Mês do Pagamento', required=True, min_value=1, max_value=12)
    ano = forms.IntegerField(
        label='Ano do Pagamento', required=True, min_value=datetime.now().date().year - 6, max_value=datetime.now().date().year + 1
    )


class UploadArquivoForm(forms.FormPlus):
    arquivo = forms.FileField()


# IFMA/Tássio: Formulário geral de cálculos
class CalculoForm(forms.ModelFormPlus):
    METHOD = 'GET'

    class Media:
        js = ('/static/calculos_pagamentos/js/PosicionaInlines.js', '/static/calculos_pagamentos/js/FormularioCalculoDinamico.js')

    class Meta:
        model = Calculo
        exclude = ('atestador',)

    def __init__(self, *args, **kwargs):
        if self.request.GET.get('portaria_id') is not None:
            portaria_id = self.request.GET.get('portaria_id')
            PortariaProgressaoTae = apps.get_model('atos', 'portariaprogressaotae')
            if PortariaProgressaoTae:
                portaria = PortariaProgressaoTae.objects.get(pk=portaria_id)
                justificativa = ''
                if 'resolve:' in portaria.documento.corpo.lower() and 'dê-se ciência' in portaria.documento.corpo.lower():
                    indice_inicial = portaria.documento.corpo.lower().find('resolve:') + 8
                    indice_final = portaria.documento.corpo.lower().find('dê-se ciência')
                    justificativa = portaria.documento.corpo[indice_inicial:indice_final]
                    justificativa = HMTLParaStringUnicode(justificativa)
                initial = {
                    'servidor': portaria.servidor,
                    'justificativa': justificativa,
                }
                kwargs['initial'] = initial
        super().__init__(*args, **kwargs)
        self.fields['servidor'].queryset = Servidor.objects.ativos()

    @transaction.atomic
    def save(self, commit=True):
        return super().save(False)


# IFMA/Tássio: Formulário geral para períodos
class PeriodoForm(forms.ModelFormPlus):
    padrao_vencimento_novo = forms.ChoiceField(label='Padrão de Vencimento Novo', required=False)
    padrao_vencimento_passado = forms.ChoiceField(label='Padrão de Vencimento Anterior', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['padrao_vencimento_novo'].choices = padrao_choices()
        self.fields['padrao_vencimento_passado'].choices = padrao_choices()

    class Meta:
        exclude = ('calculo',)

    @transaction.atomic
    def save(self, commit=True):
        # Nesse caso, não estava atualizando o nível automaticamente. TESTADO, NÃO TIRAR.
        if self.instance.calculo.servidor.eh_tecnico_administrativo:
            if 'nivel_passado' in self.cleaned_data:
                self.instance.nivel_passado = self.cleaned_data['nivel_passado']
            self.instance.nivel = self.cleaned_data['nivel']

        return super().save()


# IFMA/Tássio: Classe geral para FormSets de períodos de cálculos
class PeriodoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        # Caso não haja servidor selecionado no CalculoForm, para validação de forms de período, pois isso gera um erro.
        if not self.data['servidor']:
            raise ValidationError('')

        # Primeiro testa se há pelo menos 1 período
        non_empty_forms = 0
        for form in self.forms:
            if form.cleaned_data:
                non_empty_forms += 1
            else:
                raise ValidationError('É obrigatório o preenchimento de todos os períodos abaixo.')  # outros erros
            if not form.is_valid():
                raise ValidationError('Corrija o erro abaixo.')  # outros erros
        if non_empty_forms - len(self.deleted_forms) < 1:
            raise forms.ValidationError('Ao menos um período de cálculo deve ser informado corretamente.')

        calculo, is_TAE = getCalculoEIsTAE(self)

        # Verifica erros de formulário. E testa os padrões antes do restante dos campos.
        for form in self.forms:
            data_inicio = form.cleaned_data['data_inicio']
            data_fim = form.cleaned_data['data_fim']
            for form2 in self.forms:
                if form != form2:
                    d1 = form2.cleaned_data['data_inicio']
                    d2 = form2.cleaned_data['data_fim']
                    if d1 <= data_inicio and data_inicio <= d2:
                        form.add_error('data_inicio', f'Esta Data Inicial conflita com as datas do Período {format_(d1)} - {format_(d2)}')
                        raise ValidationError('Corrija o erro abaixo.')
                    if d1 <= data_fim and data_fim <= d2:
                        form.add_error('data_fim', f'Esta Data Final conflita com as datas do Período {format_(d1)} - {format_(d2)}')
                        raise ValidationError('Corrija o erro abaixo.')

            if is_TAE:
                classe = calculo.servidor.cargo_classe
                if 'padrao_vencimento_passado' in form.cleaned_data:
                    padrao_vencimento_passado = form.cleaned_data['padrao_vencimento_passado']
                    if padrao_vencimento_passado is None or padrao_vencimento_passado == '':
                        form.add_error('padrao_vencimento_passado', 'Para servidores técnico-administrativos, este campo é obrigatório.')
                        raise ValidationError('Corrija o erro abaixo.')
                    nivel_passado = NivelVencimentoTAEPorClasseEPadrao.objects.get(cargo_classe=classe, nivel_padrao=padrao_vencimento_passado).nivel
                    form.cleaned_data['nivel_passado'] = nivel_passado
                if 'padrao_vencimento_novo' in form.cleaned_data:
                    padrao_vencimento_novo = form.cleaned_data['padrao_vencimento_novo']
                    if padrao_vencimento_novo is None or padrao_vencimento_novo == '':
                        form.add_error('padrao_vencimento_novo', 'Para servidores técnico-administrativos, este campo é obrigatório.')
                        raise ValidationError('Corrija o erro abaixo.')
                    nivel = NivelVencimentoTAEPorClasseEPadrao.objects.get(cargo_classe=classe, nivel_padrao=padrao_vencimento_novo).nivel
                    form.cleaned_data['nivel'] = nivel
            else:
                if type(calculo) is CalculoProgressao:
                    nivel_passado = form.cleaned_data['nivel_passado']
                    if not nivel_passado:
                        form.add_error('nivel_passado', 'Para servidores docentes, este campo é obrigatório.')
                        raise ValidationError('Corrija o erro abaixo.')
                if 'nivel' in form.cleaned_data:  # Cálculo de abono de permanência não tem nível
                    nivel = form.cleaned_data['nivel']
                    if not nivel:
                        form.add_error('nivel', 'Para servidores docentes, este campo é obrigatório.')
                        raise ValidationError('Corrija o erro abaixo.')

    def save(self, commit=True):
        calculo, _is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        # Como super(PeriodoFormSet, self).save(commit=False) não retorna períodos salvos e não modificados:
        ids_modificados = []
        for p in periodos:
            if p.id:
                ids_modificados.append(p.id)
        deletados = self.deleted_forms
        ids_deletados = [d.instance.id for d in deletados]
        ids_ignorados = ids_modificados + ids_deletados
        periodos = periodos + list(self.model.objects.filter(calculo=calculo).exclude(id__in=ids_ignorados))

        # Deletar períodos apagados (por algum motivo não se apagam sozinhos mais; talvez save(commit=False))
        self.model.objects.filter(id__in=ids_deletados).delete()

        return periodos


class PeriodoComVencimentoFormSet(PeriodoFormSet):
    def clean(self):
        super().clean()

        # Testa se existem valores para os parâmetros passados
        for form in self.forms:
            data_inicio = form.cleaned_data['data_inicio']
            data_fim = form.cleaned_data['data_fim']
            if 'jornada_passada' in form.cleaned_data:
                nivel_passado = form.cleaned_data['nivel_passado'] if 'nivel_passado' in form.cleaned_data else form.cleaned_data['nivel']
                jornada_passada = form.cleaned_data['jornada_passada']
            else:
                nivel_passado = None
                jornada_passada = None
            nivel = form.cleaned_data['nivel']
            jornada = form.cleaned_data['jornada']

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                if nivel_passado:
                    if nivel_passado.categoria == 'tecnico_administrativo':
                        valores = (
                            ValorPorNivelVencimento.objects.filter(nivel=nivel_passado, data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                            or ValorPorNivelVencimento.objects.filter(
                                nivel=nivel_passado, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes
                            )
                            or ValorPorNivelVencimento.objects.filter(nivel=nivel_passado, data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                        )
                    else:
                        valores = (
                            ValorPorNivelVencimentoDocente.objects.filter(
                                nivel=nivel_passado, jornada_trabalho=jornada_passada, data_inicio__lte=data_inicio_mes, data_fim__isnull=True
                            )
                            or ValorPorNivelVencimentoDocente.objects.filter(
                                nivel=nivel_passado, jornada_trabalho=jornada_passada, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes
                            )
                            or ValorPorNivelVencimentoDocente.objects.filter(
                                nivel=nivel_passado, jornada_trabalho=jornada_passada, data_inicio__isnull=True, data_fim__gte=data_fim_mes
                            )
                        )
                    try:
                        valores[0]
                    except Exception:
                        raise ValidationError('Valor de vencimento não encontrado para os parâmetros do tipo "passado" informados.')

                if nivel.categoria == 'tecnico_administrativo':
                    valores = (
                        ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                        or ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes)
                        or ValorPorNivelVencimento.objects.filter(nivel=nivel, data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                    )
                else:
                    valores = (
                        ValorPorNivelVencimentoDocente.objects.filter(
                            nivel=nivel, jornada_trabalho=jornada, data_inicio__lte=data_inicio_mes, data_fim__isnull=True
                        )
                        or ValorPorNivelVencimentoDocente.objects.filter(
                            nivel=nivel, jornada_trabalho=jornada, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes
                        )
                        or ValorPorNivelVencimentoDocente.objects.filter(
                            nivel=nivel, jornada_trabalho=jornada, data_inicio__isnull=True, data_fim__gte=data_fim_mes
                        )
                    )
                try:
                    valores[0]
                except Exception:
                    raise ValidationError('Valor de vencimento não encontrado para os parâmetros do tipo "novo" informados.')

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])


class PeriodoComRTFormSet(PeriodoFormSet):
    def clean(self):
        super().clean()

        _calculo, is_TAE = getCalculoEIsTAE(self)
        rt_ou_rsc = ''

        # Testa se existem valores para os parâmetros passados
        for form in self.forms:
            data_inicio = form.cleaned_data['data_inicio']
            data_fim = form.cleaned_data['data_fim']
            if 'jornada_passada' in form.cleaned_data:
                nivel_passado = form.cleaned_data['nivel_passado'] if 'nivel_passado' in form.cleaned_data else form.cleaned_data['nivel']
                jornada_passada = form.cleaned_data['jornada_passada']
                titulacao_passada = (
                    form.cleaned_data['titulacao_passada'] if 'titulacao_passada' in form.cleaned_data else form.cleaned_data['titulacao_nova']
                )
                titulacao_passada = None if is_TAE else titulacao_passada
            else:
                nivel_passado = None
                jornada_passada = None
                titulacao_passada = None
            nivel = form.cleaned_data['nivel']
            jornada = form.cleaned_data['jornada']
            if 'titulacao_nova' in form.cleaned_data:
                titulacao_nova = form.cleaned_data['titulacao_nova'] if not is_TAE else None
            if 'titulacao' in form.cleaned_data:
                titulacao_nova = form.cleaned_data['titulacao'] if not is_TAE else None

            # Restringe só titulações ou RT ou RSC nos diferentes períodos por compatibilidade com arquivo de pagamento
            if titulacao_nova:
                if rt_ou_rsc:
                    if (
                        rt_ou_rsc == 'rsc'
                        and titulacao_nova.codigo in ('23', '24', '25', '26', '27')
                        or rt_ou_rsc == 'rt'
                        and titulacao_nova.codigo in ('48', '49', '50')
                    ):
                        raise ValidationError('Não é permitido, no mesmo cálculo, misturar titulações de RT e RSC em períodos diferentes.')
                else:
                    if titulacao_nova.codigo in ('23', '24', '25', '26', '27'):
                        rt_ou_rsc = 'rt'
                    elif titulacao_nova.codigo in ('48', '49', '50'):
                        rt_ou_rsc = 'rsc'

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                if titulacao_passada:
                    valores = (
                        ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel_passado,
                            jornada_trabalho=jornada_passada,
                            titulacoes=titulacao_passada,
                            data_inicio__lte=data_inicio_mes,
                            data_fim__isnull=True,
                        )
                        or ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel_passado,
                            jornada_trabalho=jornada_passada,
                            titulacoes=titulacao_passada,
                            data_inicio__lte=data_inicio_mes,
                            data_fim__gte=data_fim_mes,
                        )
                        or ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel_passado,
                            jornada_trabalho=jornada_passada,
                            titulacoes=titulacao_passada,
                            data_inicio__isnull=True,
                            data_fim__gte=data_fim_mes,
                        )
                    )
                    try:
                        valores[0]
                    except Exception:
                        raise ValidationError('Valor de retribuição por titulação não encontrado para os parâmetros do tipo "passado" informados.')

                if titulacao_nova:
                    valores = (
                        ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel, jornada_trabalho=jornada, titulacoes=titulacao_nova, data_inicio__lte=data_inicio_mes, data_fim__isnull=True
                        )
                        or ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel,
                            jornada_trabalho=jornada,
                            titulacoes=titulacao_nova,
                            data_inicio__lte=data_inicio_mes,
                            data_fim__gte=data_fim_mes,
                        )
                        or ValorRetribuicaoTitulacao.objects.filter(
                            nivel=nivel, jornada_trabalho=jornada, titulacoes=titulacao_nova, data_inicio__isnull=True, data_fim__gte=data_fim_mes
                        )
                    )
                    try:
                        valores[0]
                    except Exception:
                        raise ValidationError('Valor de retribuição por titulação não encontrado para os parâmetros do tipo "novo" informados.')

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])


class PeriodoComVencimentoERTFormSet(PeriodoComVencimentoFormSet, PeriodoComRTFormSet):
    def clean(self):
        PeriodoComVencimentoFormSet.clean(self)
        PeriodoComRTFormSet.clean(self)


class PeriodoComFuncaoFormSet(PeriodoFormSet):
    def clean(self):
        super().clean()
        calculo, _is_TAE = getCalculoEIsTAE(self)

        # Testa se existem valores para os parâmetros passados
        for form in self.forms:
            data_inicio = form.cleaned_data['data_inicio']
            data_fim = form.cleaned_data['data_fim']
            funcoes = []
            if 'funcao' in form.cleaned_data:
                funcoes.append(form.cleaned_data['funcao'])
            if hasattr(calculo, 'funcao_servidor_titular') and calculo.funcao_servidor_titular:
                funcoes.append(calculo.funcao_servidor_titular)
            if hasattr(calculo, 'funcao_servidor_substituto') and calculo.funcao_servidor_substituto:
                funcoes.append(calculo.funcao_servidor_substituto)

            for funcao in funcoes:
                data_inicio_mes = data_inicio
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
                while True:
                    if data_fim < data_fim_mes:
                        data_fim_mes = data_fim

                    valores = (
                        ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes)
                        or ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                    )
                    try:
                        valores[0]
                    except Exception:
                        raise ValidationError(f'Valor de {funcao.nome} não encontrado para o período informado.')

                    if type(calculo) is not CalculoSubstituicao:
                        if 'FG' in funcao.nome[:2]:
                            try:
                                assert valores[0].valoresfuncaodetalhados
                            except Exception:
                                raise ValidationError(f'Valores detalhados de {funcao.nome} não encontrados para o período informado.')

                    if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                        break
                    data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                    data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])


class PeriodoComAuxilioAlimentacaoFormSet(PeriodoFormSet):
    def clean(self):
        super().clean()
        _calculo, _is_TAE = getCalculoEIsTAE(self)

        # Testa se existem valores para os parâmetros passados
        for form in self.forms:
            data_inicio = form.cleaned_data['data_inicio_desc_alim']
            data_fim = form.cleaned_data['data_fim_desc_alim']
            if data_inicio and data_fim:
                data_inicio_mes = data_inicio
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
                while True:
                    if data_fim < data_fim_mes:
                        data_fim_mes = data_fim

                    valores = (
                        ValorAlimentacao.objects.filter(data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                        or ValorAlimentacao.objects.filter(data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes)
                        or ValorAlimentacao.objects.filter(data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                    )
                    try:
                        valores[0]
                    except Exception:
                        form.add_error('data_inicio_desc_alim', 'Valor de Auxílio Alimentação não encontrado para o período informado.')
                        form.add_error('data_fim_desc_alim', '')

                    if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                        break
                    data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                    data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])


# Formulário geral para férias
class FeriasForm(forms.ModelFormPlus):
    class Meta:
        fields = ['ano_referencia']

    mes = forms.IntegerField(label='Mês de Usufruto', required=True, min_value=1, max_value=12)
    ano = forms.IntegerField(label='Ano de Usufruto', required=True, min_value=datetime.now().date().year - 6, max_value=datetime.now().date().year)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['mes'].initial = self.instance.data_inicio.month
            self.fields['ano'].initial = self.instance.data_inicio.year

    @transaction.atomic
    def save(self, commit=True):
        mes = int(self.cleaned_data['mes'])
        ano = int(self.cleaned_data['ano'])
        self.instance.data_inicio = datetime(ano, mes, 1).date()
        return super().save()


# Classe geral para formset de férias.
class FeriasFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()

        periodo = self.instance
        # anos_outros_periodos = self.model.objects.filter(periodo__calculo=periodo.calculo).exclude(periodo=periodo).values_list('ano_referencia', flat=True)
        anos_este_periodo = []
        for form in self.forms:
            anos_este_periodo.append(form.instance.ano_referencia)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            if form.is_valid():
                inicio_mes = datetime(form.cleaned_data['ano'], form.cleaned_data['mes'], 1).date()
                fim_mes = inicio_mes.replace(day=calendar.monthrange(inicio_mes.year, inicio_mes.month)[1])
                esta_dentro = False
                while inicio_mes <= fim_mes:
                    # Testa se algum dia do mês está incluso no período
                    if periodo.data_inicio <= inicio_mes <= periodo.data_fim:
                        esta_dentro = True
                        break
                    inicio_mes = inicio_mes + relativedelta(days=+1)
                if not esta_dentro:
                    form.add_error(None, 'A data informada não se insere neste período do cálculo.')
                # Retirado, pois há caso de o mês de férias abranger mais de 1 período, o q demanda mais de 1 cadastro.
                # # Testa se já existem férias para o mesmo ano de data_inicio para este cálculo.
                # if form.cleaned_data["ano_referencia"] in todos_anos:
                #     todos_anos.remove(form.cleaned_data["ano_referencia"])
                # if form.cleaned_data["ano_referencia"] in todos_anos:
                #     raise ValidationError(u'Há mais de uma data de férias para o ano de referência %d, considerando todos os períodos.' % form.cleaned_data["ano_referencia"])
                # todos_anos.append(form.cleaned_data["ano_referencia"])


# # # CÁLCULO DE SUBSTITUIÇÃO # # #


# IFMA/Tássio: Calcula pagamento (de ValorPorFuncao) entre datas p/ uma função com valores diferentes dependendo da data
def calcula_pagamento_substituicao(data_inicio, data_fim, funcao, inicio_periodo):
    if inicio_periodo:
        if inicio_periodo <= data_inicio:
            valorporfuncao = ValorPorFuncao.objects.get(funcao=funcao, data_inicio=inicio_periodo)
            valor_mensal = valorporfuncao.valor
            data_fim_fato = data_fim if (not valorporfuncao.data_fim or data_fim <= valorporfuncao.data_fim) else valorporfuncao.data_fim
            pagamento = calcula_pagamento_proporcional(data_inicio, data_fim_fato, valor_mensal)
            return pagamento
        else:
            pagamento = 0
            if inicio_periodo <= data_fim:
                valorporfuncao = ValorPorFuncao.objects.get(funcao=funcao, data_inicio=inicio_periodo)
                valor_mensal = valorporfuncao.valor
                data_fim_fato = data_fim if (not valorporfuncao.data_fim or data_fim <= valorporfuncao.data_fim) else valorporfuncao.data_fim
                pagamento += calcula_pagamento_proporcional(valorporfuncao.data_inicio, data_fim_fato, valor_mensal)
            inicio_periodo_anterior = ValorPorFuncao.objects.filter(funcao=funcao, data_inicio__lt=inicio_periodo).aggregate(Max('data_inicio'))[
                'data_inicio__max'
            ]
            pagamento += calcula_pagamento_substituicao(data_inicio, data_fim, funcao, inicio_periodo_anterior)
            return pagamento
    else:
        valorporfuncao = ValorPorFuncao.objects.get(funcao=funcao, data_inicio__isnull=True)
        valor_mensal = valorporfuncao.valor
        data_fim_fato = min(data_fim, valorporfuncao.data_fim)
        pagamento = calcula_pagamento_proporcional(data_inicio, data_fim_fato, valor_mensal)
        return pagamento


class CalculoSubstituicaoForm(forms.ModelFormPlus):
    METHOD = 'GET'
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects,
        required=True,
        widget=forms.Select(),
    )
    funcao_servidor_substituto = forms.ModelChoiceField(
        queryset=FuncaoCodigo.objects,
        required=True,
        widget=forms.Select(),
    )
    funcao_servidor_titular = forms.ModelChoiceField(
        queryset=FuncaoCodigo.objects,
        required=True,
        widget=forms.Select(),
    )

    class Media:
        js = ('/static/calculos_pagamentos/js/PosicionaInlines.js', '/static/calculos_pagamentos/js/FormularioCalculoDinamico.js')

    class Meta:
        model = CalculoSubstituicao
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo()
        self.fields['servidor'].label = 'Servidor Substituto'
        if not self.request.user.has_perm('rh.eh_rh_sistemico'):
            campus = get_uo(self.request.user)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(pk=campus.pk)

    def clean(self):
        if (
            self.cleaned_data.get('data_inicio_funcao_servidor_substituto')
            and not self.cleaned_data.get('data_fim_funcao_servidor_substituto')
            or self.cleaned_data.get('data_fim_funcao_servidor_substituto')
            and not self.cleaned_data.get('data_inicio_funcao_servidor_substituto')
        ):
            raise forms.ValidationError(
                'Você deve informar ambas as datas Inicial da Função do Substituto e Final da Função do Substituto, ou nenhuma das duas datas.'
            )

    @transaction.atomic
    def save(self, commit=True):
        return super().save(False)


class PeriodoSubstituicaoFormSet(PeriodoComFuncaoFormSet):
    def save(self, commit=True):
        periodos = super().save(commit=False)

        # CalculoSubstituição
        calculo = self.instance

        funcao_t = calculo.funcao_servidor_titular
        funcao_s = calculo.funcao_servidor_substituto
        pagamento = 0
        a = ValorPorFuncao.objects.filter(funcao=funcao_t).aggregate(Max('data_inicio'))['data_inicio__max']
        if funcao_s:
            b = ValorPorFuncao.objects.filter(funcao=funcao_s).aggregate(Max('data_inicio'))['data_inicio__max']
            periodo_atual_inicio = max(b, a)
        else:
            periodo_atual_inicio = a

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim

            # Tem vários casos aqui pois podem haver vários períodos de substituição, logo o período da função de origem
            # pode interseccionar ou não um dos períodos de substituição.
            if calculo.data_inicio_funcao_servidor_substituto and data_inicio <= calculo.data_inicio_funcao_servidor_substituto <= data_fim:
                data_inicio_funcao_substituto = calculo.data_inicio_funcao_servidor_substituto
            elif calculo.data_fim_funcao_servidor_substituto and data_inicio <= calculo.data_fim_funcao_servidor_substituto <= data_fim:
                data_inicio_funcao_substituto = data_inicio
            else:
                data_inicio_funcao_substituto = None
            if calculo.data_fim_funcao_servidor_substituto and data_inicio <= calculo.data_fim_funcao_servidor_substituto <= data_fim:
                data_fim_funcao_substituto = calculo.data_fim_funcao_servidor_substituto
            elif calculo.data_inicio_funcao_servidor_substituto and data_inicio <= calculo.data_inicio_funcao_servidor_substituto <= data_fim:
                data_fim_funcao_substituto = data_fim
            else:
                data_fim_funcao_substituto = None
            if (
                calculo.data_inicio_funcao_servidor_substituto
                and calculo.data_inicio_funcao_servidor_substituto <= data_inicio
                and calculo.data_fim_funcao_servidor_substituto
                and data_fim <= calculo.data_fim_funcao_servidor_substituto
            ):
                data_inicio_funcao_substituto = data_inicio
                data_fim_funcao_substituto = data_fim
            if not calculo.data_inicio_funcao_servidor_substituto and not calculo.data_fim_funcao_servidor_substituto:
                data_inicio_funcao_substituto = data_inicio
                data_fim_funcao_substituto = data_fim

            # Pagamento referente ao titular
            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            pagamento_titular = 0
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo__pk=periodo.id).delete()
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim
                if (1, calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1]) == (data_inicio_mes.day, data_fim_mes.day):  # Mês cheio
                    valorporfuncao = (
                        ValorPorFuncao.objects.filter(funcao=funcao_t, data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                        or ValorPorFuncao.objects.filter(funcao=funcao_t, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes)
                        or ValorPorFuncao.objects.filter(funcao=funcao_t, data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                    )
                    valorporfuncao = valorporfuncao[0]
                    pagamento_mensal = valorporfuncao.valor
                else:
                    pagamento_mensal = calcula_pagamento_substituicao(data_inicio_mes, data_fim_mes, funcao_t, periodo_atual_inicio)

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_grat = pagamento_mensal
                detalhamento_mensal.gratificacao = False
                detalhamento_mensal.save()

                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    # Salva dados da gratificação natalina
                    detalhamento_mensal = calculo.get_detalhamento_model()()
                    detalhamento_mensal.periodo = periodo
                    detalhamento_mensal.data_inicio = data_inicio_mes
                    detalhamento_mensal.data_fim = data_fim_mes
                    detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                    detalhamento_mensal.valor_grat = pagamento_mensal
                    detalhamento_mensal.gratificacao = True
                    detalhamento_mensal.save()
                    # Dobra valor para totalizar
                    pagamento_mensal *= 2

                pagamento_titular += pagamento_mensal
                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            # Pagamento de função do substituto (para dedução) relativo a este período de substituição
            pagamento_substituto = 0
            if funcao_s and data_inicio_funcao_substituto and data_fim_funcao_substituto:
                data_inicio_mes = data_inicio_funcao_substituto
                data_fim_mes = data_inicio_funcao_substituto.replace(
                    day=calendar.monthrange(data_inicio_funcao_substituto.year, data_inicio_funcao_substituto.month)[1]
                )
                while True:
                    if data_fim_funcao_substituto < data_fim_mes:
                        data_fim_mes = data_fim_funcao_substituto
                    if (1, calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1]) == (
                        data_inicio_mes.day,
                        data_fim_mes.day,
                    ):  # Mês cheio
                        valorporfuncao = (
                            ValorPorFuncao.objects.filter(funcao=funcao_s, data_inicio__lte=data_inicio_mes, data_fim__isnull=True)
                            or ValorPorFuncao.objects.filter(funcao=funcao_s, data_inicio__lte=data_inicio_mes, data_fim__gte=data_fim_mes)
                            or ValorPorFuncao.objects.filter(funcao=funcao_s, data_inicio__isnull=True, data_fim__gte=data_fim_mes)
                        )
                        valorporfuncao = valorporfuncao[0]
                        pagamento_mensal = valorporfuncao.valor
                    else:
                        pagamento_mensal = calcula_pagamento_substituicao(data_inicio_mes, data_fim_mes, funcao_s, periodo_atual_inicio)

                    # Deduz a função de origem no detalhamento
                    detalhamentos_mensais = calculo.get_detalhamento_model().objects.filter(
                        periodo=periodo, data_inicio__month=data_inicio_mes.month, data_inicio__year=data_inicio_mes.year, gratificacao=False
                    )
                    if detalhamentos_mensais.exists():
                        detalhamento_mensal = detalhamentos_mensais[0]
                        detalhamento_mensal.valor_grat -= pagamento_mensal
                        detalhamento_mensal.save()

                    if data_inicio_mes.month == 12:
                        # Deduz a função de origem no detalhamento da gratificação
                        detalhamentos_mensais = calculo.get_detalhamento_model().objects.filter(
                            periodo=periodo, data_inicio__month=data_inicio_mes.month, data_inicio__year=data_inicio_mes.year, gratificacao=True
                        )
                        if detalhamentos_mensais.exists():
                            detalhamento_mensal = detalhamentos_mensais[0]
                            detalhamento_mensal.valor_grat -= pagamento_mensal
                            detalhamento_mensal.save()
                        # Dobra valor para totalizar
                        pagamento_mensal *= 2
                    pagamento_substituto += pagamento_mensal

                    if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim_funcao_substituto.month, data_fim_funcao_substituto.year):
                        break

                    data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                    data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            pagamento += pagamento_titular - pagamento_substituto

        substituto = calculo.servidor.pessoa_fisica.nome
        titular = calculo.titular and calculo.titular.nome

        if len(periodos) <= 1:
            resultado = '{} substituiu {} na função {} de {} até {} tendo um total a receber de R${}'.format(
                substituto,
                titular,
                funcao_t,
                periodos[0].data_inicio.strftime('%d/%m/%Y'),
                periodos[0].data_fim.strftime('%d/%m/%Y'),
                round(pagamento, 2),
            )
        else:
            resultado = (
                f'{substituto} substituiu {titular} na função {funcao_t} em múltiplos períodos tendo um total a receber de R${round(pagamento, 2)}'
            )
        if not titular:
            resultado = resultado.replace('substituiu None na', 'assumiu interinamente uma')
        calculo.resultado = resultado.replace('.', ',')
        calculo.save()


# # # CÁLCULO DE PROGRESSÃO # # #


# IFMA/Tássio: Formulário Inline de PeriodoProgressao, criado para adicionar campo extra ao modelo.
class PeriodoProgressaoForm(PeriodoForm):
    ADICIONAIS_CHOICES = [
        [0, 'Sem adicionais'],
        [-10, 'Adicional de Periculosidade - 10%'],
        [10, 'Adicional de Insalubridade - 10%'],
        [20, 'Adicional de Insalubridade - 20%'],
    ]
    adicionais = forms.ChoiceField(label='Adicionais', required=True, choices=ADICIONAIS_CHOICES)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            if self.instance.periculosidade:
                valor = -10
            else:
                valor = self.instance.insalubridade
            self.fields['adicionais'].initial = valor

    @transaction.atomic
    def save(self, commit=True):
        adicionais = self.cleaned_data['adicionais']
        if adicionais == '-10':
            self.instance.periculosidade = True
            self.instance.insalubridade = 0
        else:
            self.instance.periculosidade = False
            self.instance.insalubridade = int(adicionais)

        return super().save()


# IFMA/Tássio
class PeriodoProgressaoFormSet(PeriodoComVencimentoERTFormSet):
    def __init__(self, *args, **kwargs):
        if self.request.GET.get('portaria_id') is not None:
            portaria_id = self.request.GET.get('portaria_id')
            PortariaProgressaoTae = apps.get_model('atos', 'portariaprogressaotae')
            if PortariaProgressaoTae:
                portaria = PortariaProgressaoTae.objects.get(pk=portaria_id)
                padrao_vencimento_passado = padrao_vencimento_novo = None
                if portaria.nivel_anterior and portaria.nivel_novo:
                    padrao_vencimento_passado = str(roman_to_int(portaria.nivel_anterior)) + portaria.servidor.nivel_padrao[1:]
                    padrao_vencimento_novo = str(roman_to_int(portaria.nivel_novo)) + portaria.servidor.nivel_padrao[1:]
                elif portaria.padrao_vencimento_anterior and portaria.padrao_vencimento_novo:
                    padrao_vencimento_passado = portaria.servidor.nivel_padrao[0] + portaria.padrao_vencimento_anterior.zfill(2)
                    padrao_vencimento_novo = portaria.servidor.nivel_padrao[0] + portaria.padrao_vencimento_novo.zfill(2)
                initial = [
                    {
                        'data_inicio': portaria.efeitos_financeiros,
                        'padrao_vencimento_passado': padrao_vencimento_passado,
                        'padrao_vencimento_novo': padrao_vencimento_novo,
                    },
                ]
                kwargs['initial'] = initial
        super().__init__(*args, **kwargs)

    def save(self, commit=True):
        # Cálculo de progressão
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel_passado = periodo.nivel_passado
            nivel = periodo.nivel
            jornada_passada = periodo.jornada_passada
            jornada = periodo.jornada
            titulacao_passada = periodo.titulacao_passada if not is_TAE else None
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None
            anuenio = periodo.anuenio or 0
            periculosidade = periodo.periculosidade
            insalubridade = periodo.insalubridade or 0
            iq = periodo.iq if periodo.iq and is_TAE else 0

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                DetalhamentoProgressao.objects.filter(periodo=periodo).delete()
            while True:
                if (
                    data_fim_mes.day > 30 and data_inicio_mes.day <= 30
                ):  # Não é considerado o dia 31 no cálculo de progressão da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                vencimento_mensal_recebido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel_passado, jornada_passada)
                vencimento_mensal_devido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal_recebido = vencimento_tae_proporcional_a_ch_do_cargo(
                        vencimento_mensal_recebido, jornada_passada, calculo.servidor
                    )
                    vencimento_mensal_devido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_devido, jornada, calculo.servidor)
                vencimento_mensal = vencimento_mensal_devido - vencimento_mensal_recebido
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                rt_mensal_recebida = (
                    calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel_passado, jornada_passada, titulacao_passada) if titulacao_passada else 0
                )
                rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
                rt_mensal = rt_mensal_devida - rt_mensal_recebida
                rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                anuenio_mensal = Decimal(vencimento_mensal) * anuenio / 100
                anuenio_mensal = round(anuenio_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                if periculosidade:
                    periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                    periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                else:
                    periculosidade_mensal = 0

                insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
                insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                iq_mensal = Decimal(vencimento_mensal) * iq / 100
                iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = DetalhamentoProgressao()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        vencimento_mensal *= 2
                        rt_mensal *= 2
                        anuenio_mensal *= 2
                        periculosidade_mensal *= 2
                        insalubridade_mensal *= 2
                        iq_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = DetalhamentoProgressao()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_venc = vencimento_mensal
                        gratificacao_corrente.valor_rt = rt_mensal
                        gratificacao_corrente.valor_anuenio = anuenio_mensal
                        gratificacao_corrente.valor_per = periculosidade_mensal
                        gratificacao_corrente.valor_ins = insalubridade_mensal
                        gratificacao_corrente.valor_iq = iq_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_venc = vencimento_mensal
                detalhamento_mensal.valor_rt = rt_mensal
                detalhamento_mensal.valor_anuenio = anuenio_mensal
                detalhamento_mensal.valor_per = periculosidade_mensal
                detalhamento_mensal.valor_ins = insalubridade_mensal
                detalhamento_mensal.valor_iq = iq_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


# IFMA/Tássio
class FeriasProgressaoFormSet(FeriasFormSet):
    def save(self, commit=True):
        # Período de progressão
        periodo = self.instance
        # Cálculo de progressão
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim
            nivel_passado = periodo.nivel_passado
            nivel = periodo.nivel
            jornada_passada = periodo.jornada_passada
            jornada = periodo.jornada
            titulacao_passada = periodo.titulacao_passada if not is_TAE else None
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None
            anuenio = periodo.anuenio or 0
            periculosidade = periodo.periculosidade
            insalubridade = periodo.insalubridade or 0
            iq = periodo.iq if periodo.iq and is_TAE else 0

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if (
                data_fim_mes.day > 30 and data_inicio_mes.day <= 30
            ):  # Não é considerado o dia 31 no cálculo de progressão da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            vencimento_mensal_recebido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel_passado, jornada_passada)
            vencimento_mensal_devido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
            if is_TAE:
                vencimento_mensal_recebido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_recebido, jornada_passada, calculo.servidor)
                vencimento_mensal_devido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_devido, jornada, calculo.servidor)
            vencimento_mensal = vencimento_mensal_devido - vencimento_mensal_recebido
            vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            rt_mensal_recebida = (
                calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel_passado, jornada_passada, titulacao_passada) if titulacao_passada else 0
            )
            rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
            rt_mensal = rt_mensal_devida - rt_mensal_recebida
            rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            anuenio_mensal = Decimal(vencimento_mensal) * anuenio / 100
            anuenio_mensal = round(anuenio_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if periculosidade:
                periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
            else:
                periculosidade_mensal = 0

            insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
            insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            iq_mensal = Decimal(vencimento_mensal) * iq / 100
            iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            vencimento_ferias = round(vencimento_mensal / x, 2)
            rt_ferias = round(rt_mensal / x, 2)
            anuenio_ferias = round(anuenio_mensal / x, 2)
            periculosidade_ferias = round(periculosidade_mensal / x, 2)
            insalubridade_ferias = round(insalubridade_mensal / x, 2)
            iq_ferias = round(iq_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_venc = vencimento_ferias
            ferias.valor_rt = rt_ferias
            ferias.valor_anuenio = anuenio_ferias
            ferias.valor_per = periculosidade_ferias
            ferias.valor_ins = insalubridade_ferias
            ferias.valor_iq = iq_ferias
            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE PERICULOSIDADE # # #


class PeriodoPericulosidadeFormSet(PeriodoComVencimentoFormSet):
    def save(self, commit=True):
        # Cálculo de periculosidade
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                DetalhamentoPericulosidade.objects.filter(periodo=periodo).delete()
            while True:
                if (
                    data_fim_mes.day > 30 and data_inicio_mes.day <= 30
                ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = DetalhamentoPericulosidade()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        vencimento_mensal *= 2
                        periculosidade_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = DetalhamentoPericulosidade()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_venc = vencimento_mensal
                        gratificacao_corrente.valor_per = periculosidade_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_venc = vencimento_mensal
                detalhamento_mensal.valor_per = periculosidade_mensal

                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


class FeriasPericulosidadeFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        # Cálculo de periculosidade
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim

            nivel = periodo.nivel
            jornada = periodo.jornada

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if (
                data_fim_mes.day > 30 and data_inicio_mes.day <= 30
            ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
            if is_TAE:
                vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
            vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
            periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            vencimento_ferias = round(vencimento_mensal / x, 2)
            periculosidade_ferias = round(periculosidade_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_venc = vencimento_ferias
            ferias.valor_per = periculosidade_ferias

            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE INSALUBRIDADE # # #


class PeriodoInsalubridadeFormSet(PeriodoComVencimentoFormSet):
    def save(self, commit=True):
        # Cálculo de insalubridade
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            insalubridade = periodo.insalubridade

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                DetalhamentoInsalubridade.objects.filter(periodo=periodo).delete()
            while True:
                if (
                    data_fim_mes.day > 30 and data_inicio_mes.day <= 30
                ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
                insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = DetalhamentoInsalubridade()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        vencimento_mensal *= 2
                        insalubridade_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = DetalhamentoInsalubridade()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_venc = vencimento_mensal
                        gratificacao_corrente.valor_ins = insalubridade_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_venc = vencimento_mensal
                detalhamento_mensal.valor_ins = insalubridade_mensal

                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


class FeriasInsalubridadeFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        # Cálculo de insalubridade
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim

            nivel = periodo.nivel
            jornada = periodo.jornada
            insalubridade = periodo.insalubridade

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if (
                data_fim_mes.day > 30 and data_inicio_mes.day <= 30
            ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
            if is_TAE:
                vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
            vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
            insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            vencimento_ferias = round(vencimento_mensal / x, 2)
            insalubridade_mensal = round(insalubridade_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_venc = vencimento_ferias
            ferias.valor_ins = insalubridade_mensal

            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE RETRIBUIÇÃO POR TITULAÇÃO # # #


class PeriodoRTFormSet(PeriodoComRTFormSet):
    def save(self, commit=True):
        # Cálculo de RT
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            titulacao_passada = periodo.titulacao_passada if not is_TAE else None
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            while True:
                if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                rt_mensal_recebida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_passada) if titulacao_passada else 0
                rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
                rt_mensal = rt_mensal_devida - rt_mensal_recebida
                rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        rt_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = calculo.get_detalhamento_model()()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_rt = rt_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_rt = rt_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


class FeriasRTFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        # Cálculo de RT
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            titulacao_passada = periodo.titulacao_passada if not is_TAE else None
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            rt_mensal_recebida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_passada) if titulacao_passada else 0
            rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
            rt_mensal = rt_mensal_devida - rt_mensal_recebida
            rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            rt_ferias = round(rt_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_rt = rt_ferias
            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE INCENTIVO À QUALIFICAÇÃO # # #


class PeriodoIQFormSet(PeriodoComVencimentoFormSet):
    def save(self, commit=True):
        # Cálculo de IQ
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            iq_passado = periodo.iq_passado if is_TAE else 0
            iq_novo = periodo.iq_novo if is_TAE else 0

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                DetalhamentoIQ.objects.filter(periodo=periodo).delete()
            while True:
                if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                iq_mensal_recebida = Decimal(vencimento_mensal) * iq_passado / 100
                iq_mensal_devida = Decimal(vencimento_mensal) * iq_novo / 100
                iq_mensal = iq_mensal_devida - iq_mensal_recebida
                iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = DetalhamentoIQ()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        iq_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = DetalhamentoIQ()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_iq = iq_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_iq = iq_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


class FeriasIQFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        # Cálculo de IQ
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            iq_passado = periodo.iq_passado if is_TAE else 0
            iq_novo = periodo.iq_novo if is_TAE else 0

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
            if is_TAE:
                vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
            vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            iq_mensal_recebida = Decimal(vencimento_mensal) * iq_passado / 100
            iq_mensal_devida = Decimal(vencimento_mensal) * iq_novo / 100
            iq_mensal = iq_mensal_devida - iq_mensal_recebida
            iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            iq_ferias = round(iq_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_iq = iq_ferias
            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE MUDANÇA DE REGIME # # #


# IFMA/Tássio
class PeriodoMudancaRegimeFormSet(PeriodoComVencimentoERTFormSet):
    def save(self, commit=True):
        # Cálculo de mudança de regime
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada_passada = periodo.jornada_passada
            jornada = periodo.jornada
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None
            anuenio = periodo.anuenio or 0
            periculosidade = periodo.periculosidade
            insalubridade = periodo.insalubridade or 0
            iq = periodo.iq if periodo.iq and is_TAE else 0

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                DetalhamentoMudancaRegime.objects.filter(periodo=periodo).delete()
            while True:
                if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                vencimento_mensal_recebido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada_passada)
                vencimento_mensal_devido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal_recebido = vencimento_tae_proporcional_a_ch_do_cargo(
                        vencimento_mensal_recebido, jornada_passada, calculo.servidor
                    )
                    vencimento_mensal_devido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_devido, jornada, calculo.servidor)
                vencimento_mensal = vencimento_mensal_devido - vencimento_mensal_recebido
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                rt_mensal_recebida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada_passada, titulacao_nova) if titulacao_nova else 0
                rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
                rt_mensal = rt_mensal_devida - rt_mensal_recebida
                rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                anuenio_mensal = Decimal(vencimento_mensal) * anuenio / 100
                anuenio_mensal = round(anuenio_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                if periculosidade:
                    periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                    periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                else:
                    periculosidade_mensal = 0

                insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
                insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                iq_mensal = Decimal(vencimento_mensal) * iq / 100
                iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = DetalhamentoMudancaRegime()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        vencimento_mensal *= 2
                        rt_mensal *= 2
                        anuenio_mensal *= 2
                        periculosidade_mensal *= 2
                        insalubridade_mensal *= 2
                        iq_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = DetalhamentoMudancaRegime()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_venc = vencimento_mensal
                        gratificacao_corrente.valor_rt = rt_mensal
                        gratificacao_corrente.valor_anuenio = anuenio_mensal
                        gratificacao_corrente.valor_per = periculosidade_mensal
                        gratificacao_corrente.valor_ins = insalubridade_mensal
                        gratificacao_corrente.valor_iq = iq_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_venc = vencimento_mensal
                detalhamento_mensal.valor_rt = rt_mensal
                detalhamento_mensal.valor_anuenio = anuenio_mensal
                detalhamento_mensal.valor_per = periculosidade_mensal
                detalhamento_mensal.valor_ins = insalubridade_mensal
                detalhamento_mensal.valor_iq = iq_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


# IFMA/Tássio
class FeriasMudancaRegimeFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        # Cálculo de mudança de regime
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim
            nivel = periodo.nivel
            jornada_passada = periodo.jornada_passada
            jornada = periodo.jornada
            titulacao_nova = periodo.titulacao_nova if not is_TAE else None
            anuenio = periodo.anuenio or 0
            periculosidade = periodo.periculosidade
            insalubridade = periodo.insalubridade or 0
            iq = periodo.iq if periodo.iq and is_TAE else 0

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            vencimento_mensal_recebido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada_passada)
            vencimento_mensal_devido = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
            if is_TAE:
                vencimento_mensal_recebido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_recebido, jornada_passada, calculo.servidor)
                vencimento_mensal_devido = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal_devido, jornada, calculo.servidor)
            vencimento_mensal = vencimento_mensal_devido - vencimento_mensal_recebido
            vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            rt_mensal_recebida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada_passada, titulacao_nova) if titulacao_nova else 0
            rt_mensal_devida = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao_nova) if titulacao_nova else 0
            rt_mensal = rt_mensal_devida - rt_mensal_recebida
            rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            anuenio_mensal = Decimal(vencimento_mensal) * anuenio / 100
            anuenio_mensal = round(anuenio_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if periculosidade:
                periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
            else:
                periculosidade_mensal = 0

            insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
            insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            iq_mensal = Decimal(vencimento_mensal) * iq / 100
            iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            vencimento_ferias = round(vencimento_mensal / x, 2)
            rt_ferias = round(rt_mensal / x, 2)
            anuenio_ferias = round(anuenio_mensal / x, 2)
            periculosidade_ferias = round(periculosidade_mensal / x, 2)
            insalubridade_ferias = round(insalubridade_mensal / x, 2)
            iq_ferias = round(iq_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_venc = vencimento_ferias
            ferias.valor_rt = rt_ferias
            ferias.valor_anuenio = anuenio_ferias
            ferias.valor_per = periculosidade_ferias
            ferias.valor_ins = insalubridade_ferias
            ferias.valor_iq = iq_ferias
            ferias.save()

        super().save(commit=True)
        calculo.save()


# # # CÁLCULO DE AUXÍLIO TRANSPORTE # # #


class PeriodoTransporteFormSet(PeriodoComVencimentoFormSet):
    def save(self, commit=True):
        # Cálculo de auxílio transporte
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            quant_passagens = periodo.quant_passagens
            valor_passagem = periodo.valor_passagem
            dias_uteis_mes_incompleto = periodo.dias_uteis_mes_incompleto

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim
                eh_mes_completo = (data_inicio_mes.day, data_fim_mes.day) == (1, calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
                if (
                    data_fim_mes.day > 30 and data_inicio_mes.day <= 30
                ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                    data_fim_mes = data_fim_mes.replace(day=30)

                vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                dias_uteis = 22 if eh_mes_completo else dias_uteis_mes_incompleto

                valor_descontado = vencimento_mensal / 30 * dias_uteis * Decimal('0.06')
                valor_auxilio = quant_passagens * valor_passagem * dias_uteis
                valor_aux_a_receber = round(valor_auxilio - valor_descontado, 2)
                # valor_aux_a_receber = valor_aux_a_receber if valor_aux_a_receber > 0 else 0

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = dias_uteis
                detalhamento_mensal.valor_aux = valor_aux_a_receber
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


# # # CÁLCULO DE ABONO DE PERMANÊNCIA # # #


class PeriodoPermanenciaFormSet(PeriodoFormSet):
    def save(self, commit=True):
        # Cálculo de abono de permanência
        calculo, _is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            valor_mensal_abono = periodo.valor_mensal_abono

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            while True:
                if (
                    data_fim_mes.day > 30 and data_inicio_mes.day <= 30
                ):  # Não é considerado o dia 31 nos cálculos da DIGEPE do IFMA. Somente se o periodo começar em dia 31.
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                if (1, calendar.monthrange(data_fim_mes.year, data_fim_mes.month)[1]) == (data_inicio_mes.day, data_fim_mes.day):  # Mês cheio
                    abono_mensal = valor_mensal_abono
                else:
                    abono_mensal = calcula_pagamento_proporcional(data_inicio_mes, data_fim_mes, valor_mensal_abono)
                abono_mensal = round(abono_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                # Dezembro é dobrado
                if data_inicio_mes.month == 12:
                    if data_inicio_mes.year < calculo.data_criacao.year:  # Em anos anterior a gratificação é somada a dezembro
                        abono_mensal *= 2
                        detalhamento_mensal.gratificacao = True
                    else:  # No ano corrente a gratificação registrada separadamente
                        gratificacao_corrente = calculo.get_detalhamento_model()()
                        gratificacao_corrente.periodo = periodo
                        gratificacao_corrente.data_inicio = data_inicio_mes
                        gratificacao_corrente.data_fim = data_fim_mes
                        gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                        gratificacao_corrente.valor_abono = abono_mensal
                        gratificacao_corrente.gratificacao = True
                        gratificacao_corrente.save()

                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_abono = abono_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


# # # CÁLCULOS DE DESIGNAÇÃO/DISPENSA DE FG/FUC E NOMEAÇÃO/EXONERAÇÃO DE CD # # #


class PeriodoFGsCDsFormSet(PeriodoComFuncaoFormSet):
    def clean(self):
        super().clean()

        # Testa se foram informados ao mesmo tempo Meses a Receber e a Devolver de Gratificação Natalina
        if 'meses_indevidos_grat_nat' in self.forms[0].cleaned_data:
            for form in self.forms:
                meses_devidos_grat_nat = form.cleaned_data['meses_devidos_grat_nat']
                meses_indevidos_grat_nat = form.cleaned_data['meses_indevidos_grat_nat']

                if meses_devidos_grat_nat and meses_indevidos_grat_nat:
                    raise ValidationError(
                        'Não é permitido que haja num mesmo período gratificação natalina a receber e a '
                        'devolver. Informe somente um dos dois, ou nenhum dos dois.'
                    )

    def save(self, commit=True):
        calculo, _is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            funcao = periodo.funcao
            meses_devidos_grat_nat = periodo.meses_devidos_grat_nat  # Se não houver campo, é 0
            meses_indevidos_grat_nat = periodo.meses_indevidos_grat_nat  # Se não houver campo, é 0
            # recebeu_grat_nat = periodo.recebeu_grat_nat  # Se não houve campo, é False
            meses_grat_nat = -meses_indevidos_grat_nat if meses_indevidos_grat_nat else meses_devidos_grat_nat

            is_FG = 'FG' in funcao.nome[:2]
            # meses_recebidos_grat_nat = 0 if not recebeu_grat_nat else 12
            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            grat_nat_total_vet, grat_nat_venc_vet, grat_nat_gadf_vet, grat_nat_age_vet = [], [], [], []
            while True:
                if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                    data_fim_mes = data_fim_mes.replace(day=30)
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                grat_mensal, venc_mensal, gadf_mensal, age_mensal = 0, 0, 0, 0
                grat_nat_total, grat_nat_venc, grat_nat_gadf, grat_nat_age = 0, 0, 0, 0
                d1 = data_inicio_mes.replace(day=1)
                d2 = d1.replace(day=calendar.monthrange(d1.year, d1.month)[1])
                if is_FG:
                    venc_mensal, gadf_mensal, age_mensal = calcula_valores_fg_detalhados_mensal(data_inicio_mes, data_fim_mes, funcao)
                    venc_mensal = round(venc_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                    gadf_mensal = round(gadf_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                    age_mensal = round(age_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                    grat_nat_venc, grat_nat_gadf, grat_nat_age = calcula_valores_fg_detalhados_mensal(d1, d2, funcao)
                    grat_nat_venc = grat_nat_venc / 12 * (meses_grat_nat)
                    grat_nat_gadf = grat_nat_gadf / 12 * (meses_grat_nat)
                    grat_nat_age = grat_nat_age / 12 * (meses_grat_nat)
                    grat_nat_venc = round(grat_nat_venc, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                    grat_nat_gadf = round(grat_nat_gadf, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                    grat_nat_age = round(grat_nat_age, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                else:
                    grat_mensal = calcula_valor_funcao_mensal(data_inicio_mes, data_fim_mes, funcao)
                    grat_mensal = round(grat_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                    grat_nat_total = calcula_valor_funcao_mensal(d1, d2, funcao)
                    grat_nat_total = grat_nat_total / 12 * (meses_grat_nat)
                    grat_nat_total = round(grat_nat_total, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_grat = grat_mensal
                detalhamento_mensal.valor_venc = venc_mensal
                detalhamento_mensal.valor_gadf = gadf_mensal
                detalhamento_mensal.valor_age = age_mensal
                detalhamento_mensal.save()

                grat_nat_total_vet.append(grat_nat_total)
                grat_nat_venc_vet.append(grat_nat_venc)
                grat_nat_gadf_vet.append(grat_nat_gadf)
                grat_nat_age_vet.append(grat_nat_age)

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            # Gratificação Natalina
            grat_nat_total = sum(grat_nat_total_vet) / len(grat_nat_total_vet)  # Média
            grat_nat_venc = sum(grat_nat_venc_vet) / len(grat_nat_venc_vet)  # Média
            grat_nat_gadf = sum(grat_nat_gadf_vet) / len(grat_nat_gadf_vet)  # Média
            grat_nat_age = sum(grat_nat_age_vet) / len(grat_nat_age_vet)  # Média
            isExoneracaoOuDispensa = isinstance(calculo, CalculoExoneracaoCD | CalculoDispensaFG)
            if grat_nat_total or grat_nat_venc or grat_nat_gadf or grat_nat_age:
                gratificacao_corrente = calculo.get_detalhamento_model()()
                gratificacao_corrente.periodo = periodo
                gratificacao_corrente.data_inicio = data_inicio_mes
                gratificacao_corrente.data_fim = data_fim_mes
                gratificacao_corrente.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                gratificacao_corrente.valor_grat = -grat_nat_total if isExoneracaoOuDispensa else grat_nat_total
                gratificacao_corrente.valor_venc = -grat_nat_venc if isExoneracaoOuDispensa else grat_nat_venc
                gratificacao_corrente.valor_gadf = -grat_nat_gadf if isExoneracaoOuDispensa else grat_nat_gadf
                gratificacao_corrente.valor_age = -grat_nat_age if isExoneracaoOuDispensa else grat_nat_age
                gratificacao_corrente.gratificacao = True
                gratificacao_corrente.save()

        calculo.save()


class FeriasFGsCDsFormSet(FeriasFormSet):
    def save(self, commit=True):
        periodo = self.instance
        calculo, is_TAE = getCalculoEIsTAE(self)

        for form in self.forms:
            if form in self.deleted_forms:
                continue
            ferias = form.instance
            mes = int(form.cleaned_data['mes'])
            ano = int(form.cleaned_data['ano'])
            data_inicio = datetime(ano, mes, 1).date()

            data_inicio_periodo = periodo.data_inicio
            data_fim_periodo = periodo.data_fim

            funcao = periodo.funcao
            is_FG = 'FG' in funcao.nome[:2]

            if data_inicio < data_inicio_periodo:
                data_inicio_mes = data_inicio_periodo
            else:
                data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                data_fim_mes = data_fim_mes.replace(day=30)
            if data_fim_periodo < data_fim_mes:
                data_fim_mes = data_fim_periodo

            grat_mensal, venc_mensal, gadf_mensal, age_mensal = 0, 0, 0, 0
            if is_FG:
                venc_mensal, gadf_mensal, age_mensal = calcula_valores_fg_detalhados_mensal(data_inicio_mes, data_fim_mes, funcao)
                venc_mensal = round(venc_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                gadf_mensal = round(gadf_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                age_mensal = round(age_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
            else:
                grat_mensal = calcula_valor_funcao_mensal(data_inicio_mes, data_fim_mes, funcao)
                grat_mensal = round(grat_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

            if is_TAE:
                x = 3
            else:
                x = 2
            grat_ferias = round(grat_mensal / x, 2)
            venc_ferias = round(venc_mensal / x, 2)
            gadf_ferias = round(gadf_mensal / x, 2)
            age_ferias = round(age_mensal / x, 2)

            ferias.data_inicio = data_inicio
            ferias.valor_grat = grat_ferias
            ferias.valor_venc = venc_ferias
            ferias.valor_gadf = gadf_ferias
            ferias.valor_age = age_ferias
            ferias.save()

        super().save(commit=True)
        # O calculo não identifica a sub-classe, mas a super-classe.
        if CalculoCD.objects.filter(pk=calculo.pk).exists():
            CalculoCD.save(calculo.calculocd)
        else:
            CalculoFG.save(calculo.calculofg)


# # # CÁLCULO DE TÉRMINO DE CONTRATO TEMPORÁRIO # # #


# IFMA/Tássio
class CalculoTerminoContratoForm(CalculoForm):
    def clean(self):
        cleaned_data = super().clean()
        servidor = self.cleaned_data['servidor']
        calculo = self.instance
        if (
            isinstance(calculo, CalculoTerminoContratoProfSubs)
            and 'PROF ENS BAS TEC TECNOLOGICO-SUBSTITUTO' not in servidor.cargo_emprego.nome
            or isinstance(calculo, CalculoTerminoContratoInterpLibras)
            and 'INTERPRETE' not in servidor.cargo_emprego.nome
        ):
            raise ValidationError(f'Cargo {servidor.cargo_emprego}, do servidor abaixo, não suportado por este tipo de cálculo.')
        return cleaned_data


# IFMA/Tássio
class PeriodoTerminoContratoFormSet(PeriodoComVencimentoERTFormSet, PeriodoComAuxilioAlimentacaoFormSet):
    def clean(self):
        calculo, _is_TAE = getCalculoEIsTAE(self)
        if 'INTERPRETE' in calculo.servidor.cargo_emprego.nome:
            nivel = NivelVencimento.objects.get(codigo='P31')
        elif 'PROF ENS BAS TEC TECNOLOGICO-SUBSTITUTO' in calculo.servidor.cargo_emprego.nome:
            nivel = NivelVencimento.objects.get(codigo='D101')
        else:
            raise ValidationError('ERRO!!!')
        for form in self.forms:
            form.cleaned_data['nivel'] = nivel  # Bota o nível no formulário para o clean do formset-pai
        super().clean()
        self.nivel = nivel

    def save(self, commit=True):
        # Cálculo de término de contrato
        calculo, is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.nivel = self.nivel
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            nivel = periodo.nivel
            jornada = periodo.jornada
            titulacao = periodo.titulacao if not is_TAE else None
            periculosidade = periodo.periculosidade
            insalubridade = periodo.insalubridade or 0
            iq = periodo.iq if periodo.iq and is_TAE else 0
            transporte = periodo.transporte
            data_inicio_desc_alim = periodo.data_inicio_desc_alim
            data_fim_desc_alim = periodo.data_fim_desc_alim

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim
                eh_mes_completo = (data_inicio_mes.day, data_fim_mes.day) == (1, calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
                if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                    data_fim_mes = data_fim_mes.replace(day=30)

                vencimento_mensal = calcula_vencimento_mensal(data_inicio_mes, data_fim_mes, nivel, jornada)
                if is_TAE:
                    vencimento_mensal = vencimento_tae_proporcional_a_ch_do_cargo(vencimento_mensal, jornada, calculo.servidor)
                vencimento_mensal = round(vencimento_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                rt_mensal = calcula_rt_mensal(data_inicio_mes, data_fim_mes, nivel, jornada, titulacao) if titulacao else 0
                rt_mensal = round(rt_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                iq_mensal = Decimal(vencimento_mensal) * iq / 100
                iq_mensal = round(iq_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                if is_TAE:
                    contrato_mensal = vencimento_mensal + iq_mensal
                else:
                    contrato_mensal = vencimento_mensal + rt_mensal

                if periculosidade:
                    periculosidade_mensal = Decimal(vencimento_mensal) * 10 / 100
                    periculosidade_mensal = round(periculosidade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.
                else:
                    periculosidade_mensal = 0

                insalubridade_mensal = Decimal(vencimento_mensal) * insalubridade / 100
                insalubridade_mensal = round(insalubridade_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                dias_uteis = 22 if eh_mes_completo else periodo.dias_uteis
                transporte_mensal = transporte / 22 * dias_uteis
                transporte_mensal = round(transporte_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.quant_dias_uteis = dias_uteis
                detalhamento_mensal.valor_contr = contrato_mensal
                detalhamento_mensal.valor_per = periculosidade_mensal
                detalhamento_mensal.valor_ins = insalubridade_mensal
                detalhamento_mensal.valor_transp = transporte_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

            # CÁLCULO DO DESCONTO DE AUXÍLIO ALIMENTAÇÃO
            if data_inicio_desc_alim and data_fim_desc_alim:
                data_inicio_mes = data_inicio_desc_alim
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
                # Apaga detalhamentos passados para um período na edição, para recalcular
                if periodo.id:
                    calculo.get_detalhamento_alim_model().objects.filter(periodo=periodo).delete()
                while True:
                    if data_fim_desc_alim < data_fim_mes:
                        data_fim_mes = data_fim_desc_alim
                    eh_mes_completo = (data_inicio_mes.day, data_fim_mes.day) == (
                        1,
                        calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1],
                    )
                    if data_fim_mes.day > 30 and data_inicio_mes.day <= 30:
                        data_fim_mes = data_fim_mes.replace(day=30)

                    auxilio_alimentacao_do_mes = get_auxilio_alimentacao(data_inicio_mes)
                    eh_mesmo_mes_do_rendimento = data_inicio_mes.year == periodo.data_fim.year and data_inicio_mes.month == periodo.data_fim.month
                    dias_corridos = (data_fim_mes - data_inicio_mes).days + 1
                    if eh_mes_completo:
                        dias_uteis = 22
                    elif eh_mesmo_mes_do_rendimento:
                        dias_uteis = 22 - periodo.dias_uteis
                    else:
                        dias_uteis = dias_corridos // 7 * 5 + dias_corridos % 7 - 2
                    alimentacao_mensal = auxilio_alimentacao_do_mes / 22 * dias_uteis
                    alimentacao_mensal = round(alimentacao_mensal, 2)  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                    # Salva dados deste mês
                    detalhamento_alimentacao_mensal = calculo.get_detalhamento_alim_model()()
                    detalhamento_alimentacao_mensal.gratificacao = False
                    detalhamento_alimentacao_mensal.periodo = periodo
                    detalhamento_alimentacao_mensal.data_inicio = data_inicio_mes
                    detalhamento_alimentacao_mensal.data_fim = data_fim_mes
                    detalhamento_alimentacao_mensal.quant_dias = dias_uteis
                    detalhamento_alimentacao_mensal.valor_alim = alimentacao_mensal
                    detalhamento_alimentacao_mensal.save()

                    if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim_desc_alim.month, data_fim_desc_alim.year):
                        break
                    data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                    data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


class InformarIRPFForm(forms.ModelFormPlus):
    class Meta:
        model = CalculoTerminoContrato
        fields = ['total_irpf_grat_nat']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['total_irpf_grat_nat'].help_text = 'Gratif. Natalina Proporcional: R${}<br/>{}'.format(
                str(self.instance.total_grat_nat).replace('.', ','), self.fields['total_irpf_grat_nat'].help_text
            )


# # # CÁLCULO DE AUXÍLIO PRÉ-ESCOLAR # # #


class PeriodoPreEscolarFormSet(PeriodoFormSet):
    def save(self, commit=True):
        # Cálculo de auxílio pré-escolar
        calculo, _is_TAE = getCalculoEIsTAE(self)
        periodos = super().save(commit=False)

        for periodo in periodos:
            periodo.save()  # Aqui ele gera o id para poder ser chave estrangeira
            data_inicio = periodo.data_inicio
            data_fim = periodo.data_fim
            cota_participacao = periodo.cota_participacao

            data_inicio_mes = data_inicio
            data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])
            # Apaga detalhamentos passados para um período na edição, para recalcular
            if periodo.id:
                calculo.get_detalhamento_model().objects.filter(periodo=periodo).delete()
            while True:
                if data_fim < data_fim_mes:
                    data_fim_mes = data_fim

                auxilio_preescolar_corrente = get_auxilio_preescolar(data_inicio_mes)
                valor_descontado = auxilio_preescolar_corrente * cota_participacao / 100
                auxilio_preescolar_mensal = round(
                    auxilio_preescolar_corrente - valor_descontado, 2
                )  # Arredondamento é feito mensalmente segundo orientação da DIGEPE.

                # Salva dados deste mês
                detalhamento_mensal = calculo.get_detalhamento_model()()
                detalhamento_mensal.gratificacao = False
                detalhamento_mensal.periodo = periodo
                detalhamento_mensal.data_inicio = data_inicio_mes
                detalhamento_mensal.data_fim = data_fim_mes
                detalhamento_mensal.quant_dias = (data_fim_mes - data_inicio_mes).days + 1
                detalhamento_mensal.valor_aux = auxilio_preescolar_mensal
                detalhamento_mensal.save()

                if (data_inicio_mes.month, data_inicio_mes.year) == (data_fim.month, data_fim.year):
                    break
                data_inicio_mes = (data_inicio_mes + relativedelta(months=+1)).replace(day=1)
                data_fim_mes = data_inicio_mes.replace(day=calendar.monthrange(data_inicio_mes.year, data_inicio_mes.month)[1])

        calculo.save()


# IFMA - Luiz
class GerarDocumentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Continuar'

    substituir_documento = forms.BooleanField(
        label='Substituir Documento',
        required=False,
        initial=False,
        help_text='Este cálculo já possui o tipo de documento solicidado. Marque esta opção para substituir o corpo do documento deste cáclculo.',
    )


# Fim IFMA - Luiz
