from datetime import date

from comum.models import Vinculo
from comum.utils import get_uo
from djtools import forms
from djtools.forms import ReadOnlyField
from djtools.forms.widgets import AutocompleteWidget, TextareaCounterWidget
from pdi.models import (
    PDI,
    ComissaoPDI,
    SecaoPDI,
    SecaoPDICampus,
    SecaoPDIInstitucional,
    SugestaoComunidade,
    SugestaoConsolidacao,
    TipoComissaoChoices,
)
from rh.models import Servidor, UnidadeOrganizacional


class ComissaoPDIForm(forms.ModelFormPlus):
    vinculos_avaliadores = forms.MultipleModelChoiceFieldPlus(queryset=Vinculo.objects.funcionarios(), required=True)

    class Meta:
        model = ComissaoPDI
        fields = ('pdi', 'nome', 'tipo', 'vinculos_avaliadores')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['pdi'].initial = PDI.get_atual()

    def clean(self):
        avaliadores = self.cleaned_data.get('vinculos_avaliadores')
        avaliadores_sem_usuarios = avaliadores.filter(user__isnull=True)
        if avaliadores_sem_usuarios.exists():
            erros = []
            erros.append('A(s) pessoa(s) não tem usuário no suap e por isso não podem ser adicionado:')
            for avaliador in avaliadores_sem_usuarios:
                erros.append(f'{avaliador.pessoa.nome} não tem usuário no suap.')

            self._errors['vinculos_avaliadores'] = self.error_class(erros)

        return super().clean()


class SecaoPDIForm(forms.ModelFormPlus):
    class Meta:
        model = SecaoPDI
        fields = ('pdi', 'nome', 'descricao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Se já tiver sido iniciado o periodo de contribuições não se pode alterar o pdi da seção
        if self.instance.pk and date.today() > self.instancepdi.periodo_sugestao_inicial:
            self.fields['pdi'] = ReadOnlyField(label='PDI')
            self.fields['pdi'].initial = self.instance.pdi
            self.fields['pdi'].widget.display_value = str(self.instance.pdi)


class EixoForm(forms.ModelFormPlus):
    class Meta:
        model = SugestaoComunidade
        fields = ('secao_pdi', 'campus', 'analisada')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.id:
            self.fields['secao_pdi'].queryset = SecaoPDI.objects.filter(pdi=self.instance.secao_pdi.pdi)
            if self.instance.campus != self.request.user.get_relacionamento().campus:
                self.fields['secao_pdi'].queryset = SecaoPDI.objects.filter(id=self.instance.secao_pdi_id)

        self.fields['secao_pdi'].empty_label = None


class FiltroSugestaoComunidadeForm(forms.FormPlus):
    TODOS = '0'
    TEC_ADMIN = '1'
    DOCENTE = '2'
    DISCENTE = '3'
    ANONIMO = '4'
    CATEGORIA_USUARIO_CHOICES = (
        (TODOS, 'Todas'),
        (TEC_ADMIN, 'Téc. Administrativo'),
        (DOCENTE, 'Docente'),
        (DISCENTE, 'Discente'),
        (ANONIMO, 'Anônimo'),
    )

    TODAS = '0'
    ANALISADAS = '1'
    EM_ANALISE = '2'
    SITUACAO_CHOICES = ((TODAS, 'Todas'), (ANALISADAS, 'Analisadas'), (EM_ANALISE, 'Em análise'))

    campus = forms.ModelChoiceField(
        label='Filtrar por Campus',
        queryset=UnidadeOrganizacional.objects.suap().all(),
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
    )
    secao_pdi = forms.ModelChoiceField(
        label='Filtrar por Eixo do PDI',
        queryset=SecaoPDI.objects.all().order_by('nome'),
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
    )
    categoria_usuario = forms.ChoiceField(
        label='Filtrar por Usuário',
        choices=CATEGORIA_USUARIO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
    )
    situacao = forms.ChoiceField(
        label='Filtrar por Situação',
        choices=SITUACAO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
    )

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pdi = PDI.get_atual()
        user = self.request.user
        if not (
            user.groups.filter(name='Comissão Temática do PDI').exists()
            or user.groups.filter(name='Comissão Central do PDI').exists()
            or user.groups.filter(name='Administrador do PDI').exists()
        ):
            self.fields['campus'] = forms.ModelChoiceField(
                label='Filtrar por Campus',
                queryset=UnidadeOrganizacional.objects.suap().all(),
                required=False,
                widget=AutocompleteWidget(readonly=True),
            )
            self.fields['campus'].initial = get_uo(user)

        comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
        campus_id = self.request.GET.get('campus')
        eh_campus_usuario = False
        if campus_id:
            campus = UnidadeOrganizacional.objects.suap().get(id=campus_id)
            eh_campus_usuario = campus == user.get_vinculo().relacionamento.campus

        if comissao.exists() and not eh_campus_usuario:
            self.fields['secao_pdi'] = forms.ModelChoiceField(
                label='Filtrar por Eixo do PDI', queryset=SecaoPDI.objects.all(), required=False, widget=AutocompleteWidget(readonly=True)
            )
            self.fields['secao_pdi'].initial = SecaoPDI.objects.get(nome=comissao[0].nome)
        else:
            self.fields['secao_pdi'].queryset = pdi.secaopdi_set

        if user.groups.filter(name='Comissão Temática do PDI').exists() and user.groups.filter(name='Comissão Central do PDI').exists():
            self.fields['campus'] = forms.ModelChoiceField(
                label='Filtrar por Campus',
                queryset=UnidadeOrganizacional.objects.suap().all(),
                required=False,
                widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
            )
            self.fields['secao_pdi'] = forms.ModelChoiceField(
                label='Filtrar por Eixo do PDI',
                queryset=SecaoPDI.objects.filter(pdi=pdi),
                required=False,
                widget=forms.Select(attrs={'onchange': "$('#filtrosugestaocomunidade_form').submit();"}),
            )

    def processar(self):
        contribuicoes = SugestaoComunidade.objects.all()
        categorias_usuario = self.cleaned_data.get('categoria_usuario')
        if categorias_usuario:
            if categorias_usuario == self.TEC_ADMIN:
                # contribuicoes = contribuicoes.filter(anonima)
                contribuicoes = contribuicoes.filter(
                    cadastrada_por__vinculo__in=Servidor.objects.tecnicos_administrativos().values_list('vinculo', flat=True)
                )
            elif categorias_usuario == self.DOCENTE:
                # contribuicoes = contribuicoes.filter(anonima=False)
                contribuicoes = contribuicoes.filter(cadastrada_por__vinculo__in=Servidor.objects.docentes().values_list('vinculo', flat=True))
            elif categorias_usuario == self.DISCENTE:
                # contribuicoes = contribuicoes.filter(anonima=False)
                contribuicoes = contribuicoes.filter(cadastrada_por__vinculo__tipo_relacionamento__model='aluno')
            elif categorias_usuario == self.ANONIMO:
                contribuicoes = contribuicoes.filter(anonima=True)

        campus = self.cleaned_data.get('campus')
        if campus:
            contribuicoes = contribuicoes.filter(campus=campus)

        secao_pdi = self.cleaned_data.get('secao_pdi')
        if secao_pdi:
            contribuicoes = contribuicoes.filter(secao_pdi=secao_pdi)

        situacao = self.cleaned_data.get('situacao')
        if situacao:
            if situacao == self.ANALISADAS:
                contribuicoes = contribuicoes.filter(analisada=True)
            elif situacao == self.EM_ANALISE:
                contribuicoes = contribuicoes.filter(analisada=False)

        return contribuicoes


class SugestaoComunidadeForm(forms.ModelFormPlus):
    texto = forms.CharField(widget=TextareaCounterWidget(max_length=1000), label='Contribuição')

    class Meta:
        model = SugestaoComunidade
        fields = ('secao_pdi', 'texto', 'anonima')

    def __init__(self, *args, **kwargs):
        secoes_disponiveis = kwargs.pop('secoes_disponiveis')
        super().__init__(*args, **kwargs)
        user = self.request.user
        self.instance.cadastrada_por = user
        self.instance.campus = get_uo(user)
        if self.instance.pk:
            secoes_disponiveis = secoes_disponiveis | SecaoPDI.objects.filter(id=self.instance.secao_pdi_id)

        pdi = PDI.get_atual()
        self.fields['texto'].widget = TextareaCounterWidget(max_length=pdi.qtd_caracteres_contribuicao)
        self.fields['secao_pdi'].queryset = secoes_disponiveis

    def clean(self):
        cleaned_data = self.cleaned_data
        pdi = PDI.get_atual()
        if pdi.periodo_sugestao_inicial > date.today() or date.today() > pdi.periodo_sugestao_final:
            raise forms.ValidationError('Período de contribuições do PDI %s encerrado.')

        return cleaned_data


class SecaoPDICampusForm(forms.ModelFormPlus):
    secao_pdi = forms.ModelChoiceField(
        SecaoPDI.objects.all(), label='Seção do PDI', help_text='Selecione a seção para adicionar ou visualizar a redação correspondente'
    )
    texto = forms.CharField(widget=TextareaCounterWidget(max_length=5000))

    class Meta:
        model = SecaoPDICampus
        fields = ('secao_pdi', 'texto', 'anexo')

    def __init__(self, *args, **kwargs):
        periodo_local_aberto = kwargs.pop('periodo_local_aberto')
        super().__init__(*args, **kwargs)
        if not periodo_local_aberto:
            self.fields['texto'].widget.attrs['readonly'] = True

        self.instance.campus = get_uo(self.request.user)
        pdi = PDI.get_atual()
        self.fields['secao_pdi'].queryset = SecaoPDI.objects.filter(pdi=pdi)
        self.fields['texto'].widget = TextareaCounterWidget(max_length=pdi.qtd_caracteres_comissao_local)

    def clean(self):
        cleaned_data = self.cleaned_data
        pdi = PDI.get_atual()
        if date.today() > pdi.data_final_local:
            raise forms.ValidationError('Não é possível redigir proposta: período encerrado.')

        return cleaned_data


class SecaoPDIInstitucionalForm(forms.ModelFormPlus):
    secao_pdi = forms.ModelChoiceField(
        SecaoPDI.objects.all(), label='Seção do PDI', help_text='Selecione a seção para adicionar ou visualizar a redação correspondente'
    )

    class Meta:
        model = SecaoPDIInstitucional
        fields = ('secao_pdi', 'anexo')

    def __init__(self, *args, **kwargs):
        periodo_tematica_aberto = kwargs.pop('periodo_tematica_aberto')
        super().__init__(*args, **kwargs)
        if not periodo_tematica_aberto:
            self.fields['anexo'].widget.attrs['readonly'] = True

        queryset = self.fields['secao_pdi'].queryset
        pdi = PDI.get_atual()
        user = self.request.user
        if pdi.comissaopdi_set.filter(vinculos_avaliadores=user.get_vinculo()).exists():
            comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
            self.fields['secao_pdi'].queryset = queryset.filter(nome=comissao[0].nome)

    def clean(self):
        cleaned_data = self.cleaned_data
        pdi = PDI.get_atual()
        if date.today() > pdi.data_final_tematica:
            raise forms.ValidationError('Não é possível redigir proposta: período encerrado.')

        return cleaned_data


class RelatoriosForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    METHOD = 'GET'
    ano = forms.ChoiceField(label='Filtrar por Ano do PDI:', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['ano'].choices = PDI.objects.values_list('ano', 'ano').distinct().order_by('-ano')


class SugestaoConsolidacaoForm(forms.ModelFormPlus):
    texto = forms.CharField(widget=TextareaCounterWidget(max_length=1000), label='Contribuição')

    class Meta:
        model = SugestaoConsolidacao
        fields = ('secao_pdi', 'texto', 'anonima')

    def __init__(self, *args, **kwargs):
        secoes_disponiveis = kwargs.pop('secoes_disponiveis')
        super().__init__(*args, **kwargs)
        user = self.request.user
        self.instance.cadastrada_por = user
        self.instance.campus = get_uo(user)
        if self.instance.pk:
            secoes_disponiveis = secoes_disponiveis | SecaoPDI.objects.filter(id=self.instance.secao_pdi_id)

        pdi = PDI.get_atual()
        self.fields['texto'].widget = TextareaCounterWidget(max_length=pdi.qtd_caracteres_contribuicao)
        self.fields['secao_pdi'].queryset = secoes_disponiveis

    def clean(self):
        cleaned_data = self.cleaned_data
        pdi = PDI.get_atual()
        if pdi.periodo_sugestao_melhoria_inicial > date.today() or date.today() > pdi.periodo_sugestao_melhoria_final:
            raise forms.ValidationError('Período de contribuições do PDI %s encerrado.')

        return cleaned_data


class FiltroSugestaoConsolidacaoForm(forms.FormPlus):
    TODOS = '0'
    TEC_ADMIN = '1'
    DOCENTE = '2'
    DISCENTE = '3'
    ANONIMO = '4'
    CATEGORIA_USUARIO_CHOICES = (
        (TODOS, 'Todas'),
        (TEC_ADMIN, 'Téc. Administrativo'),
        (DOCENTE, 'Docente'),
        (DISCENTE, 'Discente'),
        (ANONIMO, 'Anônimo'),
    )

    TODAS = '0'
    ANALISADAS = '1'
    EM_ANALISE = '2'
    SITUACAO_CHOICES = ((TODAS, 'Todas'), (ANALISADAS, 'Analisadas'), (EM_ANALISE, 'Em análise'))

    campus = forms.ModelChoiceField(
        label='Filtrar por Campus',
        queryset=UnidadeOrganizacional.objects.suap().all(),
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
    )
    secao_pdi = forms.ModelChoiceField(
        label='Filtrar por Eixo do PDI',
        queryset=SecaoPDI.objects.all().order_by('nome'),
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
    )
    categoria_usuario = forms.ChoiceField(
        label='Filtrar por Usuário',
        choices=CATEGORIA_USUARIO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
    )
    situacao = forms.ChoiceField(
        label='Filtrar por Situação',
        choices=SITUACAO_CHOICES,
        required=False,
        widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
    )

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        pdi = PDI.get_atual()
        user = self.request.user
        if not (
            user.groups.filter(name='Comissão Temática do PDI').exists()
            or user.groups.filter(name='Comissão Central do PDI').exists()
            or user.groups.filter(name='Administrador do PDI').exists()
        ):
            self.fields['campus'] = forms.ModelChoiceField(
                label='Filtrar por Campus',
                queryset=UnidadeOrganizacional.objects.suap().all(),
                required=False,
                widget=AutocompleteWidget(readonly=True),
            )
            self.fields['campus'].initial = get_uo(user)

        comissao = pdi.comissaopdi_set.filter(vinculos_avaliadores=user.get_vinculo(), tipo=TipoComissaoChoices.TEMATICA)
        campus_id = self.request.GET.get('campus')
        eh_campus_usuario = False
        if campus_id:
            campus = UnidadeOrganizacional.objects.suap().get(id=campus_id)
            eh_campus_usuario = campus == user.get_relacionamento().campus

        if comissao.exists() and not eh_campus_usuario:
            self.fields['secao_pdi'] = forms.ModelChoiceField(
                label='Filtrar por Eixo do PDI', queryset=SecaoPDI.objects.all(), required=False, widget=AutocompleteWidget(readonly=True)
            )
            self.fields['secao_pdi'].initial = SecaoPDI.objects.get(nome=comissao[0].nome)
        else:
            self.fields['secao_pdi'].queryset = pdi.secaopdi_set

        if user.groups.filter(name='Comissão Temática do PDI').exists() and user.groups.filter(name='Comissão Central do PDI').exists():
            self.fields['campus'] = forms.ModelChoiceField(
                label='Filtrar por Campus',
                queryset=UnidadeOrganizacional.objects.suap().all(),
                required=False,
                widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
            )
            self.fields['secao_pdi'] = forms.ModelChoiceField(
                label='Filtrar por Eixo do PDI',
                queryset=SecaoPDI.objects.filter(pdi=pdi),
                required=False,
                widget=forms.Select(attrs={'onchange': "$('#filtrosugestaoconsolidacao_form').submit();"}),
            )

    def processar(self):
        contribuicoes = SugestaoConsolidacao.objects.all()
        categorias_usuario = self.cleaned_data.get('categoria_usuario')
        if categorias_usuario:
            if categorias_usuario == self.TEC_ADMIN:
                # contribuicoes = contribuicoes.filter(anonima)
                contribuicoes = contribuicoes.filter(
                    cadastrada_por__vinculo__in=Servidor.objects.tecnicos_administrativos().values_list('vinculo', flat=True)
                )
            elif categorias_usuario == self.DOCENTE:
                # contribuicoes = contribuicoes.filter(anonima=False)
                contribuicoes = contribuicoes.filter(cadastrada_por__vinculo__in=Servidor.objects.docentes().values_list('vinculo', flat=True))
            elif categorias_usuario == self.DISCENTE:
                # contribuicoes = contribuicoes.filter(anonima=False)
                contribuicoes = contribuicoes.filter(cadastrada_por__vinculo__tipo_relacionamento__model='aluno')
            elif categorias_usuario == self.ANONIMO:
                contribuicoes = contribuicoes.filter(anonima=True)

        campus = self.cleaned_data.get('campus')
        if campus:
            contribuicoes = contribuicoes.filter(campus=campus)

        secao_pdi = self.cleaned_data.get('secao_pdi')
        if secao_pdi:
            contribuicoes = contribuicoes.filter(secao_pdi=secao_pdi)

        situacao = self.cleaned_data.get('situacao')
        if situacao:
            if situacao == self.ANALISADAS:
                contribuicoes = contribuicoes.filter(analisada=True)
            elif situacao == self.EM_ANALISE:
                contribuicoes = contribuicoes.filter(analisada=False)

        return contribuicoes
