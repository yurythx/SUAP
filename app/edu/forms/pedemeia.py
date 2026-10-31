from datetime import date
from comum.models import Ano
from djtools import forms
from edu.models import RelatoInconsistenciaPeDeMeia, OperacaoPeDeMeia, Modalidade, MatriculaPeriodo
from edu import pedemeia2


class RelatoInconsistenciaPeDeMeiaForm(forms.ModelFormPlus):
    class Meta:
        model = RelatoInconsistenciaPeDeMeia
        fields = ('descricao',)


class ConsultarCodigoSGPForm(forms.FormPlus):
    codigo_sgp = forms.CharField(label='Código SGP')

    def processar(self):
        codigo_sgp = self.cleaned_data.get('codigo_sgp')
        return ' '.join(MatriculaPeriodo.objects.filter(codigo_sgp=codigo_sgp).values_list('aluno__matricula', flat=True))


class OperacaoPeDeMeiaForm(forms.FormPlus):
    tipo = forms.ChoiceField(label='Tipo', choices=OperacaoPeDeMeia.TIPO_CHOICES)
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=[[1, 1], [2, 2]])
    modalidades = forms.ModelMultipleChoiceField(
        Modalidade.objects, label='Modalidades', widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'}), required=False
    )
    mes = forms.MesField(label='Mês')
    ferias = forms.BooleanField(label='Férias', required=False)
    observacao = forms.CharField(label='Observação', widget=forms.Textarea(), required=False)
    matriculas = forms.CharField(
        label='Matrículas', required=False, help_text='Matrículas separadas por "," ou quebra de linha.', widget=forms.Textarea()
    )
    amostra = forms.BooleanField(
        label='Amostra', required=False, help_text='Marque essa opção caso deseje gerar um lote com apenas dois registros para fins de teste.'
    )

    fieldsets = (
        ('Dados Gerais', {'fields': ('tipo', ('ano_letivo', 'periodo_letivo'))}),
        ('Detalhamento', {'fields': ('modalidades', ('mes', 'ferias'), 'observacao')}),
        ('Filtros', {'fields': ('matriculas', 'amostra')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = date.today()
        self.fields['ano_letivo'].queryset = self.fields['ano_letivo'].queryset.filter(ano__in=[hoje.year, hoje.year - 1])
        self.fields['modalidades'].queryset = self.fields['modalidades'].queryset.filter(pk__in=pedemeia2.modalidade_ensino_estudante.keys())
        self.fields['modalidades'].initial = list(self.fields['modalidades'].queryset.values_list('pk', flat=True).distinct())

    def processar(self):
        ano_letivo = self.cleaned_data['ano_letivo']
        periodo_letivo = self.cleaned_data['periodo_letivo']
        mes = self.cleaned_data['mes']
        ferias = self.cleaned_data['ferias']
        modalidades = self.cleaned_data['modalidades']
        observacao = self.cleaned_data['observacao']
        amostra = self.cleaned_data['amostra']
        tipo = self.cleaned_data['tipo']
        matriculas = self.cleaned_data['matriculas']
        if matriculas:
            matriculas = matriculas.replace(',', '').split()
        else:
            matriculas = ()
        if tipo == OperacaoPeDeMeia.CADASTRO:
            dados = pedemeia2.dados_alunos(ano_letivo, periodo_letivo, modalidades=modalidades, amostra=amostra, matriculas=matriculas)
            if dados:
                return OperacaoPeDeMeia.objects.cadastrar_alunos(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.ATUALIZACAO_CADASTRADO:
            dados = pedemeia2.dados_alunos(
                ano_letivo, periodo_letivo, atualizacao=True, modalidades=modalidades, amostra=amostra, matriculas=matriculas
            )
            if dados:
                return OperacaoPeDeMeia.objects.atualizar_alunos(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.MOVIMENTACAO:
            dados = pedemeia2.movimentacoes(modalidades=modalidades, amostra=amostra, matriculas=matriculas)
            if dados:
                return OperacaoPeDeMeia.objects.movimentar_alunos(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.CONCLUSAO:
            dados = {}
            if dados:
                return OperacaoPeDeMeia.objects.concluir_alunos(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.FREQUENCIA:
            dados = pedemeia2.frequencia_mensal(ano_letivo, mes, ferias=ferias, modalidades=modalidades, amostra=amostra, matriculas=matriculas)
            if dados:
                return OperacaoPeDeMeia.objects.cadastrar_frequencias(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.ATUALIZACAO_FREQUENCIA:
            dados = pedemeia2.frequencia_mensal(
                ano_letivo, mes, ferias=ferias, atualizacao=True, modalidades=modalidades, amostra=amostra, matriculas=matriculas
            )
            if dados:
                return OperacaoPeDeMeia.objects.atualizar_frequencias(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.FREQUENCIA_PENDENTE:
            dados = pedemeia2.frequencias_pendentes(ano_letivo, mes, ferias=ferias, modalidades=modalidades, amostra=amostra)
            if dados:
                return OperacaoPeDeMeia.objects.frequencias_pendentes(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.CADASTRO_PROFISSIONAL:
            dados = pedemeia2.dados_profissionais(ano_letivo, modalidades, amostra=amostra)
            if dados:
                return OperacaoPeDeMeia.objects.cadastro_profissional(ano_letivo, mes, dados, observacao)
        elif tipo == OperacaoPeDeMeia.ATUALIZACAO_PROFISSIONAL:
            dados = pedemeia2.dados_profissionais(ano_letivo, modalidades, atualizacao=True, amostra=amostra)
            if dados:
                return OperacaoPeDeMeia.objects.atualizacao_profissional(ano_letivo, mes, dados, observacao)


class CalcularFrequenciaPeDeMeiaForm(forms.FormPlus):
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano')
    periodo_letivo = forms.ChoiceField(label='Período Letivo', choices=[[1, 1], [2, 2]])
    mes = forms.ChoiceField(label='Mês', choices=[[x, x] for x in range(1, 13)])
    modalidades = forms.ModelMultipleChoiceField(
        Modalidade.objects, label='Modalidades', widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'}), required=False
    )
    atualizar_existente = forms.BooleanField(
        label='Atualizar Existentes',
        initial=True,
        required=False,
        help_text='Desmarque essa opção caso deseje que apenas frequências ainda não calculadas sejam calculadas para o mês informado.',
    )

    fieldsets = (
        ('Dados Gerais', {'fields': (('ano_letivo', 'periodo_letivo'),)}),
        ('Detalhamento', {'fields': ('modalidades', 'mes', 'atualizar_existente')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = date.today()
        self.fields['ano_letivo'].queryset = self.fields['ano_letivo'].queryset.filter(ano__in=(hoje.year, hoje.year - 1))
        self.fields['modalidades'].queryset = self.fields['modalidades'].queryset.filter(pk__in=pedemeia2.modalidade_ensino_estudante.keys())
        self.fields['modalidades'].initial = list(self.fields['modalidades'].queryset.values_list('pk', flat=True).distinct())
