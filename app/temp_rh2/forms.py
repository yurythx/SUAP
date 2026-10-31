from django.contrib.auth.models import Group
from django.db.models import Count

from comum.models import Configuracao
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget, CheckboxSelectMultiplePlus
from rh.models import Servidor, UnidadeOrganizacional
from temp_rh2.models import (
    Categoria,
    ClassificacaoModalidade,
    CompeticaoDesportiva,
    InscricaoCompeticaoDesportiva,
    MaximoProvasModalidade,
    ModalidadeDesportiva,
    Prova,
)


class ConfiguracaoForm(forms.FormPlus):
    grupos_podem_ver_atestado_medico = forms.MultipleModelChoiceFieldPlus(
        label='Grupos que terão acesso aos atestados médicos dos jogos. Se esse campo estiver em branco terão acesso os grupos padrão do módulo.',
        queryset=Group.objects.filter(groupdetail__app='temp_rh2'),
        required=False,
    )


class CompeticoesDesportivasForm(forms.ModelFormPlus):
    modalidades = forms.ModelMultipleChoiceField(
        label='Modalidades', queryset=ModalidadeDesportiva.objects.all(), widget=CheckboxSelectMultiplePlus()
    )
    categorias = forms.ModelMultipleChoiceField(
        label='Categorias', queryset=Categoria.objects.filter(excluido=False), widget=CheckboxSelectMultiplePlus()
    )
    provas = forms.ModelMultipleChoiceField(label='Provas', queryset=Prova.objects.all(), widget=CheckboxSelectMultiplePlus())
    uo = forms.ModelChoiceField(label='UO', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Todos')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_inicio_periodo1_jogos'].required = True
        self.fields['data_fim_periodo1_jogos'].required = True
        if 'instance' in kwargs:
            competicao_desportiva = kwargs['instance']
            if competicao_desportiva:
                self.fields['categorias'].queryset = (competicao_desportiva.categorias.all() | Categoria.objects.filter(excluido=False)).distinct()

    class Meta:
        model = CompeticaoDesportiva
        exclude = ()


def GetInscricaoCompeticaoDesportivaForm(inscricao_desportiva=None, servidor=None, request=None):
    indice = 5
    if servidor.pessoa_fisica.sexo == 'M':
        indice = 1
    elif servidor.pessoa_fisica.sexo == 'F':
        indice = 2
    queryset_modalidades = ModalidadeDesportiva.objects.filter(sexo__in=[indice, 3, 4])
    queryset_provas = Prova.objects.none()
    if inscricao_desportiva and inscricao_desportiva.competicao_desportiva:
        queryset_modalidades = inscricao_desportiva.competicao_desportiva.modalidades.filter(sexo__in=[indice, 3, 4])
        queryset_provas = inscricao_desportiva.competicao_desportiva.provas.all()

    FIELDS_INSCRICAO = (
        'uo',
        'termo_pcd',
        'termo_recebimento_hospedagem',
        'modalidades',
        'provas',
        'preferencia_camisa',
        'preferencia_short',
        'termo_aceitacao_exame',
        'atestado_medico',
    )
    if inscricao_desportiva and not inscricao_desportiva.competicao_desportiva.pode_escolher_tamanho_uniforme:
        FIELDS_INSCRICAO = (
            'uo',
            'termo_pcd',
            'termo_recebimento_hospedagem',
            'modalidades',
            'provas',
            'termo_aceitacao_exame',
            'atestado_medico',
        )

    class InscricaoCompeticaoDesportivaForm(forms.ModelFormPlus):
        uo = forms.ModelChoiceField(
            label='Confirme seu Campus:',
            queryset=UnidadeOrganizacional.objects.suap(),
            help_text='Em caso de remoção interna do servidor após efetuada a inscrição,\
                        enquanto estivermos no prazo de inscrição dos jogos, o servidor poderá optar pelo novo campus de lotação.',
        )
        modalidades = forms.ModelMultipleChoiceField(
            label='Escolha as modalidades que deseja participar:',
            queryset=queryset_modalidades.order_by('-tipo', 'nome'),
            widget=CheckboxSelectMultiplePlus(),
        )

        provas = forms.ModelMultiplePopupChoiceField(
            queryset_provas,
            label='Provas',
            required=False,
            form_filters=('modalidades', 'modalidade_id__in'),
        )

        fieldsets = (
            (
                '',
                {'fields': FIELDS_INSCRICAO},
            ),
        )

        class Meta:
            model = InscricaoCompeticaoDesportiva
            fields = FIELDS_INSCRICAO

        def __init__(self, *args, **kwargs):
            if kwargs.get('instance') and kwargs.get('instance').pk:
                initial = kwargs.setdefault('initial', {})
                initial['modalidades'] = [modalidade.pk for modalidade in kwargs['instance'].modalidades.all()]
                initial['provas'] = [prova.pk for prova in kwargs['instance'].provas.all()]

            super().__init__(*args, **kwargs)

        def clean_termo_aceitacao_exame(self):
            if self.cleaned_data.get('termo_aceitacao_exame'):
                return self.cleaned_data['termo_aceitacao_exame']
            raise forms.ValidationError('Inscrição só pode ser realizada após a marcação do termo de aceitação.')

        def clean_modalidades(self):
            if self.cleaned_data.get('modalidades'):
                maximo_coletivas = self.instance.competicao_desportiva.max_modalidades_coletivas_por_inscricao
                maximo_individual = self.instance.competicao_desportiva.max_modalidades_individuais_por_inscricao
                maximo_modalidades = self.instance.competicao_desportiva.max_modalidades_por_inscricao
                if self.cleaned_data['modalidades'].all().count() > maximo_modalidades:
                    raise forms.ValidationError(f'Você não pode escolher mais que {maximo_modalidades} modalidades')
                if self.cleaned_data['modalidades'].filter(tipo=ModalidadeDesportiva.COLETIVO).count() > maximo_coletivas:
                    raise forms.ValidationError(f'Você não pode escolher mais que {maximo_coletivas} modalidades coletivas')
                if self.cleaned_data['modalidades'].filter(tipo=ModalidadeDesportiva.INDIVIDUAL).count() > maximo_individual:
                    raise forms.ValidationError(f'Você não pode escolher mais que {maximo_individual} modalidades individuais')

                return self.cleaned_data['modalidades']
            raise forms.ValidationError('Escolha, no minimo, uma modalidade.')

        def clean_termo_recebimento_hospedagem(self):
            if self.cleaned_data.get('termo_recebimento_hospedagem'):
                if hasattr(servidor.endereco_municipio, 'pk') and servidor.endereco_municipio.pk in [9, 44, 8, 25, 17, 11, 2, 89, 1, 21, 318, 77]:
                    raise forms.ValidationError(
                        f'Servidores da grande {Configuracao.get_valor_por_chave("comum", "municipio_sede")} não tem direito de receber hospedagem.'
                    )
            return self.cleaned_data['termo_recebimento_hospedagem']

        def clean_provas(self):
            if self.cleaned_data.get('provas'):
                provas = self.cleaned_data['provas']
                provas = provas.values('modalidade_id', 'modalidade__nome').annotate(total_provas=Count('id'))
                for prova in provas:
                    maximo_provas_por_modalidade = MaximoProvasModalidade.objects.filter(
                        competicao_desportiva=self.instance.competicao_desportiva, modalidade_id=prova['modalidade_id']
                    ).first()
                    max_prova = (
                        maximo_provas_por_modalidade and maximo_provas_por_modalidade.maximo_provas or MaximoProvasModalidade.MAX_PROVAS_DEFAULT
                    )
                    if prova['total_provas'] > max_prova:
                        raise forms.ValidationError(
                            f'Servidor só poderá escolher até {max_prova} provas de {prova["modalidade__nome"]} conforme regulamento.'
                        )

            return self.cleaned_data['provas']

        def clean(self):
            provas = self.cleaned_data.get('provas')
            modalidades = self.cleaned_data.get('modalidades')
            if modalidades:
                if provas and provas.exclude(modalidade__in=modalidades).exists():
                    self.add_error('provas', 'Vocês escolheu provas de modalidades que não está inscrito.')

                for modalidade_com_provas in modalidades.filter(prova__isnull=False).distinct():
                    if not provas or not provas.filter(modalidade=modalidade_com_provas).exists():
                        self.add_error('modalidades', 'Vocês escolheu modalidades e não escolheu nenhuma prova.')

            atestado_medico = self.cleaned_data.get('atestado_medico')
            if not atestado_medico and modalidades:
                if modalidades.exclude(exige_atestado=False).exists():
                    self.add_error('atestado_medico', 'Servidor só poderá realizar a inscrição se anexar um atestado médico.')
            return self.cleaned_data

    return InscricaoCompeticaoDesportivaForm


class ModalidadeDesportivaForm(forms.ModelFormPlus):
    class Meta:
        model = ModalidadeDesportiva
        exclude = ()


def GetValidacaoInscricaoCompeticaoDesportivaForm(inscricao_desportiva=None, etapa='validacao'):
    SITUACAO_CHOICES_FORMULARIO = ((2, 'Validar Inscrição'), (4, 'Rejeitar Inscrição'))
    if etapa == 'homologacao':
        SITUACAO_CHOICES_FORMULARIO = ((3, 'Homologar Inscrição'), (4, 'Rejeitar Inscrição'))

    class ValidarInscricaoCompeticaoDesportivaForm(forms.ModelFormPlus):
        situacao = forms.ChoiceField(label='Ação:', choices=SITUACAO_CHOICES_FORMULARIO, required=True, widget=forms.RadioSelect)

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

        class Meta:
            model = InscricaoCompeticaoDesportiva
            exclude = (
                'servidor',
                'atestado_medico',
                'uo',
                'provas',
                'termo_recebimento_diaria',
                'preferencia_camisa',
                'categoria',
                'preferencia_short',
                'termo_aceitacao_exame',
                'termo_pcd',
                'termo_recebimento_hospedagem',
                'competicao_desportiva',
                'modalidades',
                'validado_por',
                'homologado_por',
                'rejeitado_por',
                'validado_em',
                'homologado_em',
                'rejeitado_em',
            )

        class Media:
            js = ('/static/temp_rh2/js/RejeitarInscricaoCompeticao.js',)

        def clean(self):
            if not self.cleaned_data.get('situacao'):
                raise forms.ValidationError('Corrija os erros abaixo.')
            if self.cleaned_data['situacao'] == '4' and self.cleaned_data['observacao_rejeicao'] == '':
                raise forms.ValidationError('Descreva o motivo para a rejeição da inscrição.')
            return self.cleaned_data

    return ValidarInscricaoCompeticaoDesportivaForm


class RelatorioInscritosModalidadeProvaForm(forms.FormPlus):
    competicao_desportiva = forms.ModelChoiceFieldPlus(label='Competição desportiva', queryset=CompeticaoDesportiva.objects.all())
    modalidades = forms.ModelMultipleChoiceField(
        label='Modalidades', required=False, queryset=ModalidadeDesportiva.objects.all(), widget=CheckboxSelectMultiplePlus()
    )
    uo = forms.ModelChoiceFieldPlus(
        label='Unidade Organizacional', required=False, queryset=UnidadeOrganizacional.objects.suap().all(), empty_label='Todos'
    )


class ClassificacaoModalidadeForm(forms.ModelFormPlus):
    inscricoes = forms.ModelMultipleChoiceField(
        label='Inscrições',
        required=False,
        queryset=InscricaoCompeticaoDesportiva.objects.all(),
        widget=AutocompleteWidget(multiple=True, search_fields=[f'servidor__{search}' for search in Servidor.SEARCH_FIELDS]),
    )

    class Meta:
        model = ClassificacaoModalidade
        fields = ()
