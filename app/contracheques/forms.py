from django.conf import settings
from django.core.exceptions import ValidationError
from django.db.models.aggregates import Count

from comum.models import Ano, Beneficio, BeneficioDependente, Configuracao, Dependente
from contracheques.layout import layout_contracheque_pensionistas, layout_contracheque_pensionistas_antigo, layout_contracheque_servidores
from contracheques.models import AgrupamentoRubricas, ContraCheque, Rubrica, TipoRubrica
from contracheques.utils import compara_arquivo_ao_modelo, compara_modelo
from djtools import forms
from djtools.choices import Anos, Meses
from djtools.forms.widgets import AutocompleteWidget, CheckboxSelectMultiplePlus, FilteredSelectMultiplePlus, TreeWidget
from financeiro.models import SubElementoNaturezaDespesa
from rh.forms import get_campus_choices
from rh.models import Setor, Situacao, UnidadeOrganizacional


def get_mes_ano():
    mes_ano = [['', '---------']]
    values_temp = []
    for values in ContraCheque.objects.ativos().fita_espelho().all().order_by('-ano__ano', '-mes').values_list('mes', 'ano__ano'):
        if values not in values_temp:
            values_temp.append(values)
            strmesano = f'{values[0]:2d}{values[1]:4d}'
            descmesano = f'{Meses.get_mes(values[0])}/{values[1]}'
            mes_ano.append((strmesano, descmesano))
    return mes_ano


# cria um choice para um select de anos. o value do select apresenta o ultimo mes daquele ano que
# pode ser usado como referência
def get_ano():
    anos = [['', '---------']]
    values_anos = Ano.objects.annotate(Count('contracheque')).filter(contracheque__count__gt=0).values_list('ano', flat=True).order_by('-ano')
    for value in values_anos:
        anos.append([f'{value:4d}', f'{value}'])
    return anos


def get_mes_ano_contracheques():
    mes_ano = get_mes_ano()
    mes_ano.append(['', '---------'])
    values_temp = []
    for values in ContraCheque.objects.ativos().fita_espelho().order_by('-ano__ano').values_list('ano__ano'):
        if values not in values_temp:
            values_temp.append(values)
            strmesano = f'00{values[0]}'
            descmesano = f'{values[0]} inteiro'
            mes_ano.append((strmesano, descmesano))
    return mes_ano


def PeriodoMesAnoRelatorioDGPFactory():
    class PeriodoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(label='Mês e Ano:')
        setor = forms.ModelChoiceField(queryset=Setor.objects.none(), widget=TreeWidget(), label='Setor SIAPE')

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_mes_ano()
            self.fields['setor'].queryset = Setor.objects.siape()

    return PeriodoMesAno


def PeriodoMesAnoFactory():
    class PeriodoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(label='Mês e Ano:', widget=forms.Select(attrs={'onchange': 'submeter_form(this)'}))

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_mes_ano()

    return PeriodoMesAno


def PeriodoAnoSetorFactory():
    class PeriodoUltimoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(choices=get_ano(), label='Ano:')
        setor = forms.ModelChoiceField(label='Setor SIAPE', queryset=Setor.objects.none(), widget=TreeWidget())

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_ano()
            self.fields['setor'].queryset = Setor.objects.siape()

    return PeriodoUltimoMesAno


def get_uo_contra_cheques():
    uos = [('TODAS_UOS', Configuracao.get_valor_por_chave('comum', 'instituicao_sigla'))]
    for uo in UnidadeOrganizacional.objects.suap().all():
        str = uo.pk
        desc = f'{uo}'
        uos.append((str, desc))
    return uos


def PeriodoAnoUOContraChequeFactory():
    class PeriodoAnoUOContraCheque(forms.FormPlus):
        periodo = forms.ChoiceField(label='Ano')
        uo = forms.ChoiceField(label='Unidade')
        categoria_choices = (
            ('todos', 'Todos os Servidores'),
            ('docente', 'Docentes'),
            ('tecnico_administrativo', 'Técnicos Administrativos'),
        )
        categoria = forms.ChoiceField(choices=categoria_choices, required=False)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_ano()
            self.fields['uo'].choices = get_uo_contra_cheques()

    return PeriodoAnoUOContraCheque


def RubricaPorCampusFactory():
    class PeriodoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(label='Mês e Ano:')
        rubrica = forms.ModelChoiceField(queryset=None, widget=AutocompleteWidget(search_fields=Rubrica.SEARCH_FIELDS), required=True)

        tipos = list(set(TipoRubrica.objects.all().values_list('nome', flat=True)))
        choices = [['', 'Todos']]
        for t in tipos:
            choices.append([t, t])
        tipo = forms.ChoiceField(choices=choices, initial='', required=False)
        situacao = forms.ModelChoiceField(
            empty_label='Todos',
            label='Situação:',
            queryset=Situacao.objects.all().order_by('codigo'),
            required=False,
            help_text='Informação da situação do servidor contida no contracheque ou se é pensionista.',
        )
        # layout da fita-espelho só permite numerico de 1 posicao então: de 0 a 9.
        sequencias = list(range(10))
        choices_sequencias = []
        for s in sequencias:
            choices_sequencias.append([s, s])
        sequencia = forms.MultipleChoiceField(
            label='Sequência', choices=choices_sequencias, initial=sequencias, widget=CheckboxSelectMultiplePlus(), required=True
        )
        choices_prazos = [['', 'Todos']]
        for num in range(1000):
            choices_prazos.append([f'{num:03}', f'{num:03}'])
        prazo = forms.ChoiceField(choices=choices_prazos, required=False)
        categoria_choices = (('', 'Todos os Servidores'), ('docente', 'Docentes'), ('tecnico_administrativo', 'Técnicos Administrativos'))
        categoria = forms.ChoiceField(choices=categoria_choices, required=False)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_mes_ano_contracheques()
            self.fields['rubrica'].queryset = Rubrica.objects.usadas_no_if()

    return PeriodoMesAno


def RubricaPorCampusAgrupadasFactory():
    class PeriodoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(label='Mês e Ano:')
        agrupamentos_rubricas = forms.ModelChoiceField(queryset=AgrupamentoRubricas.objects, required=True)

        tipos = list(set(TipoRubrica.objects.all().values_list('nome', flat=True)))
        choices = [['', 'Todos']]
        for t in tipos:
            choices.append([t, t])
        tipo = forms.ChoiceField(choices=choices, initial='', required=False)
        situacao = forms.ModelChoiceField(
            empty_label='Todos',
            label='Situação:',
            queryset=Situacao.objects.all().order_by('codigo'),
            required=False,
            help_text='Informação da situação do servidor contida no contracheque ou se é pensionista.',
        )

        categoria_choices = (('', 'Todos os Servidores'), ('docente', 'Docentes'), ('tecnico_administrativo', 'Técnicos Administrativos'))
        categoria = forms.ChoiceField(choices=categoria_choices, required=False)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_mes_ano_contracheques()

    return PeriodoMesAno


def BrutoLiquidoPorCampusFactory():
    class PeriodoMesAno(forms.FormPlus):
        periodo = forms.ChoiceField(label='Mês e Ano:')

        situacao = forms.ModelChoiceField(
            empty_label='Todos',
            label='Situação:',
            queryset=Situacao.objects,
            required=False,
            help_text='Informação da situação do servidor contida no contracheque ou se é pensionista.',
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['periodo'].choices = get_mes_ano_contracheques()
            self.fields['situacao'].queryset = Situacao.objects.filter(
                pk__in=ContraCheque.objects.ativos().fita_espelho().values_list('servidor_situacao__pk', flat=True)
            )

    return PeriodoMesAno


class ConsultaContraChequeForm(forms.FormPlus):
    ano = forms.ChoiceField(label='Ano:', widget=forms.Select())
    mes = forms.MesField(label='Mês', empty_label='Todos')

    fieldsets = ((None, {'fields': (('ano', 'mes'),)}),)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ano'].choices = get_ano()


class FormRubrica(forms.ModelFormPlus):
    class Meta:
        model = Rubrica
        exclude = ()

    subelemento_natureza_despesa = forms.ModelChoiceField(
        queryset=SubElementoNaturezaDespesa.objects.all(),
        widget=AutocompleteWidget(search_fields=SubElementoNaturezaDespesa.SEARCH_FIELDS),
        required=False,
    )


def GetImportarArquivoContraChequeForm():
    class ImportarArquivoSimplesForm(forms.FormPlus):
        choices = [['', '-- Selecione --'], ['servidores', 'Fita Espelho de Servidores'], ['pensionistas', 'Fita Espelho de Pensionistas']]
        tipo = forms.ChoiceField(choices=choices, required=True)
        arquivo = forms.FileFieldPlus(
            required=True,
            label='Arquivo',
            allow_empty_file=False,
            help_text='Selecione o arquivo texto (.txt) de acordo com o tipo (servidor ou pensionista).',
            max_file_size=100 * settings.BYTES_SIZE_1MB,
        )

        def clean(self):
            tipo = self.cleaned_data.get('tipo')
            if not tipo:
                raise ValidationError('Escolha o tipo de arquivo.')
            if len(self.files) != 1:
                # evitar o não envio de arquivo
                raise ValidationError('Nenhum arquivo selecionado.')
            if self.files['arquivo'].size == 0:
                # evitar o envio de arquivos vazios
                raise ValidationError('O arquivo enviado está vazio.')

            up_arquivo = self.files['arquivo']

            if up_arquivo.content_type != 'text/plain':
                # evitar o envio de arquivos binários
                raise ValidationError('O tipo de arquivo enviado não é compatível.')

            up_arquivo_file = up_arquivo.file
            primeira_linha = up_arquivo_file.readlines()[0].decode().split('\n')[0]

            if len(primeira_linha) < 51:
                # tanto contracheque de servidores como de pensionistas precisam desse numero mínimo de caracteres
                raise ValidationError('O arquivo enviado não possui o conteúdo esperado.')

            if tipo == 'servidores':
                return compara_arquivo_ao_modelo(up_arquivo, layout_contracheque_servidores)
            else:
                largura = len(primeira_linha)
                """
                Houve uma mudança no layout em Novembro/2011 para a fita-espélho de pensionistas. O espaço que registra o
                código do grau de parentesco passou de comprimento 2 para 3, aumentando consecutivamente a largura total
                do arquivo de 462 para 463.
                """
                if largura == 461:  # 461 por causa do aplit na quebra de linha
                    layout = layout_contracheque_pensionistas_antigo
                else:
                    layout = layout_contracheque_pensionistas
            return compara_modelo(primeira_linha, layout)

    return ImportarArquivoSimplesForm


def PeriodoMesAnoPlanoSaudeFactory():
    class PeriodoMesAnoPlanoSaude(forms.FormPlus):
        periodo = forms.ChoiceField(choices=get_mes_ano(), label='Mês a Ano de Referência:')
        planos = ['00659', '31572', '31000', '82737']
        rubricas = Rubrica.objects.usadas_no_if().filter(codigo__in=planos)
        rubricas_choices = [['NENHUM', 'Nenhum']] + [[r.codigo, r.nome] for r in rubricas] + [['00659 31572 31000 82737', 'Todos']]
        plano = forms.ChoiceField(choices=rubricas_choices, label='Plano de Saúde:')

        def clean_periodo(self):
            if not Beneficio.objects.all().exists():
                raise forms.ValidationError('Solicite ao administrador uma importação de Beneficios')
            elif not Dependente.objects.all().exists():
                raise forms.ValidationError('Solicite ao administrador  uma importação de Dependentes!')
            elif not BeneficioDependente.objects.all().exists():
                raise forms.ValidationError('Solicite ao administrador uma importação de Associações Beneficio-Dependente!')
            return self.cleaned_data['periodo']

    return PeriodoMesAnoPlanoSaude


class TitulacoesServidoresPorContracheques(forms.FormPlus):
    periodo = forms.ChoiceField(label='Mês e Ano:')
    categoria_choices = (('todos', 'Todos os Servidores'), ('docente', 'Docentes'), ('tecnico_administrativo', 'Técnicos Administrativos'))
    categoria = forms.ChoiceField(choices=categoria_choices, required=False)
    situacao = forms.ModelChoiceField(
        empty_label='Todos',
        label='Situação:',
        queryset=Situacao.servidores_de_carreira.all().order_by('codigo'),
        required=False,
        help_text='Informação da situação do servidor contida no contracheque ou se é pensionista.',
    )

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['periodo'].choices = get_mes_ano()


class AgrupamentoRubricasForm(forms.ModelFormPlus):
    rubricas = forms.MultipleModelChoiceFieldPlus(
        queryset=Rubrica.objects.usadas_no_if(), widget=FilteredSelectMultiplePlus('', True), label='Rubricas:'
    )

    class Meta:
        model = AgrupamentoRubricas
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['rubricas'].queryset = Rubrica.objects.usadas_no_if().filter(
            pk__in=ContraCheque.objects.ativos().fita_espelho().values_list('contrachequerubrica__rubrica', flat=True).distinct()
        )


class AbsenteismoForm(forms.FormPlus):
    campus = forms.ChoiceField(label='Campus', required=False)
    ano = forms.ChoiceField(label='Ano', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].choices = get_campus_choices()
        self.fields['ano'].choices = Anos.get_choices()


class CampusAnoForm(forms.FormPlus):
    campus = forms.ChoiceField(label='Campus', required=False)
    ano = forms.ChoiceField(label='Ano', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].choices = get_campus_choices()
        self.fields['ano'].choices = Anos.get_choices()


class TipologiaCargoPorFaixaForm(forms.FormPlus):
    campus = forms.ChoiceField(label='Campus', required=False)
    ano = forms.ChoiceField(label='Ano', required=True)
    mes = forms.ChoiceField(label='Mês', required=True)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].choices = get_campus_choices()
        self.fields['ano'].choices = Anos.get_choices()
        self.fields['mes'].choices = Meses.get_choices()
