import datetime
from typing import Any


from django.db.models import QuerySet

from avaliacao_integrada.models import (
    Avaliacao,
    ComissaoCPA,
    Dimensao,
    Eixo,
    EscalaLikert,
    Indicador,
    Macroprocesso,
    Respondente,
    Resposta,
    Segmento,
    TipoAvaliacao,
)
from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms import FilteredSelectMultiplePlus, ReCaptchaField
from djtools.forms.fields.tinymce import TinyMCEFormField
from edu.models import CursoCampus, Modalidade
from rh.models import AreaVinculacao, Setor, UnidadeOrganizacional


class EixoForm(forms.ModelFormPlus):
    ordem = forms.ChoiceField(choices=[])

    class Meta:
        model = Eixo
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        ordem_choices = []
        qtd_eixos = Eixo.objects.count()

        for ordem in range(1, qtd_eixos + 2):
            ordem_choices.append([ordem, ordem])

        self.fields['ordem'].choices = ordem_choices

    def save(self, *args, **kwargs):
        eixo_count = Eixo.objects.count()

        if self.instance.ordem < eixo_count:
            # Atualiza os objetos com ordem maior ou igual à nova ordem da instância
            qs = Eixo.objects.exclude(pk=self.instance.pk).filter(ordem__gte=self.instance.ordem).order_by('ordem')
            range_ordem = list(range(self.instance.ordem + 1, self.instance.ordem + 1 + qs.count()))
        else:
            # Atualiza os objetos com ordem menor ou igual à nova ordem da instância
            qs = Eixo.objects.exclude(pk=self.instance.pk).filter(ordem__lte=self.instance.ordem).order_by('ordem')
            range_ordem = list(range(1, qs.count() + 1))

        for index, obj in enumerate(qs):
            obj.ordem = range_ordem[index]
            obj.save()

        return super().save(*args, **kwargs)


class SegmentacaoForm(forms.ModelFormPlus):
    segmentos_alunos = forms.MultipleModelChoiceFieldPlus(
        Segmento.objects.filter(id__in=(Segmento.ESTUDANTE,)), label='Segmentos', required=False, widget=FilteredSelectMultiplePlus('', True)
    )
    segmentos_servidores = forms.MultipleModelChoiceFieldPlus(
        Segmento.objects.filter(id__in=Segmento.SERVIDORES), label='Segmentos', required=False, widget=FilteredSelectMultiplePlus('', True)
    )

    segmentos_sociedade_civil = forms.MultipleModelChoiceFieldPlus(
        Segmento.objects.filter(tipo=Segmento.TIPO_SOCIEDADE_CIVIL), label='Segmentos', required=False, widget=FilteredSelectMultiplePlus('', True)
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            # Carregar os segmentos já salvos no modelo
            segmentos_alunos = self.instance.segmentos.filter(id__in=(Segmento.ESTUDANTE,))
            segmentos_servidores = self.instance.segmentos.filter(id__in=Segmento.SERVIDORES)
            segmentos_sociedade_civil = self.instance.segmentos.filter(tipo=Segmento.TIPO_SOCIEDADE_CIVIL)

            # Atribuir os valores correspondentes aos campos do formulário
            self.fields['segmentos_alunos'].initial = segmentos_alunos
            self.fields['segmentos_servidores'].initial = segmentos_servidores
            self.fields['segmentos_sociedade_civil'].initial = segmentos_sociedade_civil


class IndicadorForm(SegmentacaoForm):
    tipo_resposta = forms.ChoiceField(label='Tipo', choices=Indicador.TIPO_CHOICES, required=True)

    anos_referencia = forms.ModelMultipleChoiceField(
        Ano.objects, label='Anos de Referência', required=True, widget=forms.CheckboxSelectMultiplePlus()
    )
    macroprocesso = forms.ModelChoiceFieldPlus(Macroprocesso.objects)
    subsidio_para = forms.ModelMultipleChoiceField(
        TipoAvaliacao.objects, label='Subsídio p/ Avaliações', required=True, widget=forms.CheckboxSelectMultiplePlus()
    )

    uos = forms.ModelMultiplePopupChoiceField(
        UnidadeOrganizacional.objects.suap(),
        label='Campi',
        required=False,
        help_text='Caso se aplique a todos os campi ou aos <strong>sociedade civil</strong>, recomendamos deixar em branco.',
    )
    areas_vinculacao = forms.ModelMultiplePopupChoiceField(AreaVinculacao.objects, label='Áreas', required=False)
    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidades', required=False)

    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'anos_referencia',
                    'macroprocesso',
                    'nome',
                    'aspecto',
                    'subsidio_para',
                    ('tipo', 'em_uso', 'automatico', 'obrigatorio', 'gestor_responde_como_docente'),
                    'texto_ajuda',
                )
            },
        ),
        (
            'Unidades Relacionadas',
            {'fields': ('uos', ('envolve_reitoria', 'envolve_campus_ead'), ('envolve_campus_produtivos', 'envolve_campus_nao_produtivos'))},
        ),
        ('Qualificação dos Respondentes', {'fields': ('areas_vinculacao', 'modalidades', 'periodo_curso')}),
        ('Respondentes Servidores', {'fields': ('segmentos_servidores',)}),
        ('Respondentes alunos', {'fields': ('segmentos_alunos',)}),
        ('Respondentes Sociedade Civil', {'fields': ('segmentos_sociedade_civil',)}),
        ('Configuração de Resposta', {'fields': ('tipo_resposta', 'escala', ('valor_minimo', 'valor_maximo'), 'formula')}),
    )

    class Meta:
        model = Indicador
        exclude = ()

    class Media:
        js = ('/static/avaliacao_integrada/js/IndicadorForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        areas_vinculacao_padrao = ['Ensino', 'Extensão', 'Pesquisa e Inovação', 'Atividades Estudantis']
        areas_viunculos_qs = AreaVinculacao.objects.filter(descricao__in=areas_vinculacao_padrao)
        self.fields['areas_vinculacao'].initial = areas_viunculos_qs.values_list('id', flat=True)
        modalidades_qs = Modalidade.objects.filter(
            pk__in=[
                Modalidade.TECNOLOGIA,
                Modalidade.LICENCIATURA,
                Modalidade.LICENCIATURA_DUPLA_HABILITACAO,
                Modalidade.INTEGRADO,
                Modalidade.INTEGRADO_EJA,
                Modalidade.FIC_INTEGRADO_EJA,
                Modalidade.SUBSEQUENTE,
                Modalidade.CONCOMITANTE,
            ]
        )
        self.fields['modalidades'].initial = modalidades_qs.values_list('id', flat=True)
        self.fields['tipo_resposta'].initial = Indicador.ESCALA_LIKERT
        self.fields['anos_referencia'].queryset = Ano.objects.filter(ano__gte=2015, ano__lte=datetime.date.today().year)
        escala_qs = EscalaLikert.objects.filter(id=EscalaLikert.ESCALA_PADRAO)
        if escala_qs.exists():
            self.fields['escala'].initial = escala_qs[0]
        self.fields['subsidio_para'].initial = TipoAvaliacao.objects.filter(id=TipoAvaliacao.AVALIACAO_PLANEJAMENTO_PDI)

    def clean_formula(self):
        if self.cleaned_data.get('tipo_resposta', None) == Indicador.CONJUNTO_VARIAVEIS:
            if not self.cleaned_data.get('formula', None):
                raise forms.ValidationError('A fórmula é obrigatória para respostas contendo variáveis.')
        return self.cleaned_data['formula']

    def clean(self):
        super().clean()
        if int(self.cleaned_data.get('tipo_resposta')) == Indicador.ESCALA_LIKERT and not self.cleaned_data.get('escala'):
            self.add_error('escala', 'Quando o tipo selecionado for "Escala Likert", este campo torna-se obrigatório.')
        if self.cleaned_data.get('automatico') and self.cleaned_data.get('nome') not in Indicador.INDICADORES_AUTOCALCULADOS:
            self.add_error('nome', 'O indicador informado não consta na lista de indicadores autocalculados esperados pelo sistema.')
        return self.cleaned_data


class AvaliacaoForm(SegmentacaoForm):
    texto_instrucoes_servidores = TinyMCEFormField(
        label='Texto com instruções', help_text='Texto "cabeçalho" com instruções para o público servidores', required=False
    )
    texto_instrucoes_alunos = TinyMCEFormField(
        label='Texto com instruções', help_text='Texto "cabeçalho" com instruções para o público alunos.', required=False
    )
    texto_instrucoes_sociedade_civil = TinyMCEFormField(
        label='Texto com instruções',
        help_text='Texto "cabeçalho" com instruções para o público sociedade civil. ',
        required=False,
    )
    tipos = forms.MultipleModelChoiceField(TipoAvaliacao.objects, label='Tipos', widget=forms.CheckboxSelectMultiplePlus())
    areas_vinculacao = forms.ModelMultiplePopupChoiceField(AreaVinculacao.objects, label='Áreas', required=False)

    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidades', required=False)
    uos = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.suap(), label='Campi', required=False)

    respondentes_pais_modalidades = forms.ModelMultiplePopupChoiceField(
        Modalidade.objects,
        label='Modalidades dos cursos participantes da pesquisa',
        required=False,
        help_text='Indique os cursos aos quais pertencem os alunos cujos pais e/ou responsáveis são o público-alvo desta pesquisa.',
    )

    fieldsets = (
        ('Dados gerais', {'fields': ('tipos', ('ano', 'periodo'), 'nome', 'descricao', ('data_inicio', 'data_termino'))}),
        (
            'Unidades Relacionadas',
            {'fields': (('envolve_reitoria', 'envolve_campus_ead', 'envolve_campus_produtivos', 'envolve_campus_nao_produtivos'),)},
        ),
        ('Qualificação dos Respondentes', {'fields': ('areas_vinculacao', 'modalidades', 'uos')}),
        (
            'Respondentes Servidores',
            {
                'fields': (
                    'texto_instrucoes_servidores',
                    'segmentos_servidores',
                )
            },
        ),
        (
            'Respondentes Alunos',
            {
                'fields': (
                    'texto_instrucoes_alunos',
                    'segmentos_alunos',
                )
            },
        ),
        (
            'Respondentes Sociedade Civil',
            {'fields': ('texto_instrucoes_sociedade_civil', 'segmentos_sociedade_civil', 'respondentes_pais_modalidades')},
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        modalidades_qs = Modalidade.objects.filter(pk__in=[Modalidade.INTEGRADO, Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA])
        self.fields['respondentes_pais_modalidades'].initial = modalidades_qs.values_list('id', flat=True)

    class Meta:
        model = Avaliacao
        exclude = ()


class AvaliacaoExternaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Acessar'
    email = forms.EmailField(label='E-mail', required=False)
    tipo_respondente = forms.ChoiceField(
        choices=[],
        label='Tipo do Respondente',
    )
    matricula = forms.CharField(label='Matrícula do aluno', required=False)
    cpf = forms.BrCpfField(label='CPF', required=False)
    cnpj = forms.BrCnpjField(label='CNPJ', required=False)

    # Campo oculto para passar o token
    token = forms.CharField(widget=forms.HiddenInput())

    # Campo oculto para passar o token do id do respondente
    token_respondente = forms.CharField(widget=forms.HiddenInput(), required=False)

    recaptcha = ReCaptchaField(label='')

    class Media:
        js = ('/static/avaliacao_integrada/js/AvaliacaoExterna.js',)

    def __init__(self, avaliacao: Avaliacao, token: str, *args, **kwargs) -> None:
        """Inicializa o formulário de acesso externo com choices e token."""
        super().__init__(*args, **kwargs)
        self.fields['tipo_respondente'].choices = avaliacao.get_segmentos_choices(Segmento.TIPO_SOCIEDADE_CIVIL)

        self.fields['token'].initial = token

    # Sobrescrever o método clean para validar e processar os dados

    def clean(self) -> dict[str, Any]:
        cleaned_data = super().clean()
        tipo_respondente = cleaned_data.get('tipo_respondente')

        # Adicionar os dados ao campo JSON 'dados_respondente'
        dados = Respondente.obter_dados_publico_alvo(int(tipo_respondente), dados_form=cleaned_data)[0]
        cleaned_data['dados_usuario_externo'] = dados
        return cleaned_data


class RelatorioForm(forms.Form):
    METHOD = 'get'

    avaliacao = forms.ModelChoiceField(Avaliacao.objects, label='Avaliação', required=True)
    tipos = forms.ModelMultipleChoiceField(TipoAvaliacao.objects, label='Tipos', required=False, widget=forms.CheckboxSelectMultiplePlus())

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fieldsets = [('Avaliação', {'fields': ('ano', 'avaliacao')}), ('Tipos de Avaliação', {'fields': ('tipos',)})]

    def processar(self) -> QuerySet[Indicador]:
        """
        Retorna um `QuerySet[Indicador]` filtrado por avaliação e tipos,
        contendo apenas indicadores com ao menos uma resposta registrada.
        """
        qs = Indicador.objects.all()
        avaliacao = self.cleaned_data.get('avaliacao')
        tipos = self.cleaned_data.get('tipos')

        if avaliacao or tipos:
            qs_resposta = Resposta.objects.all()
            if avaliacao:
                qs_resposta = qs_resposta.filter(respondente__avaliacao=avaliacao)
            if tipos:
                qs_resposta = qs_resposta.filter(indicador__subsidio_para__in=tipos)

            ids = qs_resposta.values_list('indicador', flat=True).order_by('indicador').distinct()
            qs = qs.filter(id__in=ids)

        qs = qs.distinct()
        return qs


class RelatorioXLSXForm(forms.Form):
    METHOD = 'get'

    avaliacao = forms.ModelChoiceField(Avaliacao.objects, label='Avaliação', required=False)
    eixo = forms.ModelChoiceField(Eixo.objects, label='Eixo', required=False)
    dimensao = forms.ModelChoiceField(Dimensao.objects, label='Dimensão', required=False)
    macroprocesso = forms.ModelChoiceField(Macroprocesso.objects, label='Macroprocesso', required=False)
    segmentos = forms.ModelMultiplePopupChoiceField(Segmento.objects, required=False)
    areas_vinculacao = forms.ModelMultiplePopupChoiceField(AreaVinculacao.objects, label='Áreas', required=False)
    uos = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.suap(), label='Campi', required=False)
    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidades', required=False)
    cursos = forms.MultipleModelChoiceFieldPlus(CursoCampus.objects, label='Cursos', required=False)
    tipos = forms.ModelMultiplePopupChoiceField(TipoAvaliacao.objects, label='Tipos', required=False)

    def processar(self) -> QuerySet[Resposta]:
        """
        Retorna `QuerySet[Resposta]` com `select_related` e filtros aplicados
        conforme os campos do formulário, para geração do XLSX.
        """
        avaliacao = self.cleaned_data.get('avaliacao')
        eixo = self.cleaned_data.get('eixo')
        dimensao = self.cleaned_data.get('dimensao')
        macroprocesso = self.cleaned_data.get('macroprocesso')
        segmentos = self.cleaned_data.get('segmentos')
        areas_vinculacao = self.cleaned_data.get('areas_vinculacao')
        uos = self.cleaned_data.get('uos')
        modalidades = self.cleaned_data.get('modalidades')
        cursos = self.cleaned_data.get('cursos')
        tipos = self.cleaned_data.get('tipos')

        respostas = Resposta.objects.all()

        if avaliacao:
            respostas = respostas.filter(respondente__avaliacao=avaliacao)
        if eixo:
            respostas = respostas.filter(indicador__macroprocesso__dimensao__eixo=eixo)
        if dimensao:
            respostas = respostas.filter(indicador__macroprocesso__dimensao=dimensao)
        if macroprocesso:
            respostas = respostas.filter(indicador__macroprocesso=macroprocesso)
        if segmentos:
            respostas = respostas.filter(respondente__segmento__in=segmentos)
        if areas_vinculacao:
            respostas = respostas.exclude(respondente__segmento__in=Segmento.SERVIDORES) | respostas.filter(
                respondente__segmento__in=Segmento.SERVIDORES,
                respondente__user__vinculo__setor__areas_vinculacao__in=areas_vinculacao.values_list('id', flat=True),
            )
        if uos:
            respostas = (
                respostas.exclude(respondente__segmento__in=Segmento.SERVIDORES + Segmento.ALUNOS)
                | respostas.filter(respondente__segmento__in=Segmento.SERVIDORES, respondente__uo__in=uos.values_list('id', flat=True))
                | respostas.filter(respondente__segmento__in=Segmento.ALUNOS, respondente__uo__in=uos.values_list('id', flat=True))
            )
        if modalidades:
            respostas = respostas.exclude(respondente__segmento__in=Segmento.ALUNOS) | respostas.filter(
                respondente__segmento__in=Segmento.ALUNOS,
                respondente__user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__modalidade__in=modalidades.values_list('id', flat=True),
            )
        if cursos:
            respostas = respostas.exclude(respondente__segmento__in=Segmento.ALUNOS) | respostas.filter(
                respondente__segmento__in=Segmento.ALUNOS,
                respondente__user__vinculo__pessoa__pessoafisica__aluno_set__curso_campus__in=cursos.values_list('id', flat=True),
            )
        if tipos:
            respostas = respostas.filter(indicador__subsidio_para__in=tipos)

        return (
            respostas.select_related(
                'indicador',
                'indicador__macroprocesso__dimensao__eixo',
                'indicador__macroprocesso__dimensao',
                'indicador__macroprocesso',
                'respondente',
                'respondente__segmento',
            )
            .order_by('respondente')
            .distinct()
        )


class FiltroIndicadorForm(forms.Form):
    SUBMIT_LABEL = 'Filtrar'

    segmentos = forms.MultipleModelChoiceField(
        Segmento.objects, initial=Segmento.objects.all().values_list('id', flat=True), required=True, widget=forms.CheckboxSelectMultiplePlus()
    )
    areas_vinculacao = forms.ModelMultiplePopupChoiceField(AreaVinculacao.objects, label='Áreas', required=False)
    uos = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.suap(), label='Campi', required=False)
    modalidades = forms.ModelMultiplePopupChoiceField(Modalidade.objects, label='Modalidades', required=False)
    cursos = forms.MultipleModelChoiceFieldPlus(CursoCampus.objects, label='Cursos', required=False)

    def filtrar_respostas(self, respostas: QuerySet[Resposta]) -> QuerySet[Resposta]:
        """Aplica os filtros do formulário sobre o queryset de `Resposta`."""
        segmentos = self.cleaned_data['segmentos']
        areas_vinculacao = self.cleaned_data['areas_vinculacao']
        uos = self.cleaned_data['uos']
        modalidades = self.cleaned_data['modalidades']
        cursos = self.cleaned_data['cursos']
        # return FiltroIndicadorForm.filtrar_respostas2(respostas, segmentos, areas_vinculacao, uos, modalidades, cursos)
        return Resposta.get(respostas, segmentos, areas_vinculacao, uos, modalidades, cursos)

    def filtrar_respondentes(self, respondentes: QuerySet[Respondente]) -> QuerySet[Respondente]:
        """Aplica os filtros do formulário sobre o queryset de `Respondente`."""
        segmentos = self.cleaned_data['segmentos']
        areas_vinculacao = self.cleaned_data['areas_vinculacao']
        uos = self.cleaned_data['uos']
        modalidades = self.cleaned_data['modalidades']
        cursos = self.cleaned_data['cursos']
        return Respondente.apply_filters(respondentes, segmentos, areas_vinculacao, uos, modalidades, cursos)


class ComissaoCPAForm(forms.ModelFormPlus):
    vinculos_membros = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Membro', required=True)
    setor = forms.ModelChoiceFieldPlus(Setor.objects.suap_ativos(), label='Setor')

    class Meta:
        model = ComissaoCPA
        fields = (
            'tipo',
            'nome',
            'setor',
            'data_portaria',
            'documento_portaria',
            'vinculos_membros',
            'ativo',
        )  # 'clonar_comissao', 'clonar_comissao_edital'
        exclude = ()


class EscalaLikertForm(forms.ModelFormPlus):
    class Meta:
        model = EscalaLikert
        exclude = ()
        # fields = '__all__'


class EnviarEmailRespondentesForm(forms.FormPlus):
    """
    Formulário para compor e enviar e-mail (HTML) a respondentes elegíveis
    de uma determinada Avaliação (não finalizados e com e-mail válido).
    """

    SUBMIT_LABEL = 'Enviar e-mail'

    titulo = forms.CharField(label='Assunto', max_length=255, required=True)
    mensagem = TinyMCEFormField(label='Mensagem (HTML)', required=True, help_text='Personalize o conteúdo do e-mail de lembrete antes do envio.')
    confirmar_envio = forms.BooleanField(label='Confirmo o envio para todos os respondentes elegíveis desta avaliação', required=True)
