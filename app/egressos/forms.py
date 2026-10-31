from comum.utils import get_uo

try:
    from collections.abc import Iterable
except ImportError:  # Python 2.7 compatibility
    from collections.abc import Iterable

from django.db import transaction

from comum.models import Ano
from djtools import forms
from djtools.forms import AutocompleteWidget, FormPlus, ModelFormPlus
from djtools.forms.widgets import RenderableCheckboxSelect, RenderableRadioSelect
from edu.models import Aluno, CursoCampus
from egressos.models import Categoria, Opcao, Pergunta, Pesquisa, Resposta
from rh.models import UnidadeOrganizacional


class CategoriaForm(ModelFormPlus):
    class Meta:
        model = Categoria
        fields = ('titulo', 'ordem')


class PerguntaForm(ModelFormPlus):
    class Meta:
        model = Pergunta
        fields = ('conteudo', 'categoria', 'tipo', 'preenchimento_obrigatorio')


class OpcaoForm(ModelFormPlus):
    class Meta:
        model = Opcao
        fields = ('conteudo', 'direcionamento_categoria', 'complementacao_subjetiva')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['direcionamento_categoria'].queryset = self.instance.pergunta.pesquisa.categoria_set.all()
        if self.instance.pergunta.tipo != Pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA:
            del self.fields['complementacao_subjetiva']


class PesquisaForm(ModelFormPlus):
    conclusao = forms.ModelMultiplePopupChoiceField(Ano.objects.ultimos(), label='Ano de Conclusão', required=False)
    uo = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.objects.uo().all(), label='Campus', required=False)
    curso_campus = forms.ModelChoiceFieldPlus(
        CursoCampus.objects,
        label='Curso',
        required=False,
        widget=AutocompleteWidget(search_fields=CursoCampus.SEARCH_FIELDS, form_filters=[('uo', 'diretoria__setor__uo__in')]),
    )

    class Meta:
        model = Pesquisa
        fields = ('titulo', 'descricao', 'modalidade', 'conclusao', 'uo', 'curso_campus')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.request.user.has_perm('egressos.eh_gestor_egressos_sistemico') and not self.instance.pk:
            id_do_campus = get_uo(self.request.user).id
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(id=id_do_campus)
            self.fields['curso_campus'].queryset = CursoCampus.objects.filter(diretoria__setor__uo__id=id_do_campus)
        self.fields['modalidade'].help_text = 'Caso nenhuma modalidade seja selecionada, os alunos de cursos FIC não serão incluídos na pesquisa.'


class ClonarPesquisaForm(FormPlus):
    titulo = forms.CharFieldPlus(label='Título')
    descricao = forms.CharFieldPlus(label='Descrição', widget=forms.Textarea())

    def __init__(self, titulo, descricao, pesquisa, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['titulo'] = titulo
        self.initial['descricao'] = descricao
        self.pesquisa = pesquisa

    def processar(self):
        return self.pesquisa.clonar_pesquisa(titulo=self.cleaned_data['titulo'], descricao=self.cleaned_data['descricao'])


class CopiarOpcaoForm(FormPlus):
    pergunta = forms.ModelChoiceField(Pergunta.objects, required=True, label='', widget=RenderableRadioSelect('widgets/perguntas_widget.html'))

    def __init__(self, pergunta_destino, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pergunta_destino = pergunta_destino
        self.fields['pergunta'].queryset = pergunta_destino.pesquisa.pergunta_set.exclude(id=pergunta_destino.id).exclude(opcao__id=None)

    @transaction.atomic
    def processar(self):
        pergunta_com_opcoes_copiadas = self.cleaned_data.get('pergunta', None)
        try:
            if pergunta_com_opcoes_copiadas:
                for opcao_original in pergunta_com_opcoes_copiadas.opcao_set.all():
                    opcao_copiada = opcao_original
                    opcao_copiada.pk = None
                    opcao_copiada.pergunta = self.pergunta_destino
                    opcao_copiada.save()
                return True
        except Exception:
            return False


class AtualizacaoCadastralForm(ModelFormPlus):
    email_pessoal = forms.EmailField()

    class Meta:
        model = Aluno
        fields = (
            'estado_civil',
            'numero_dependentes',
            'email_pessoal',
            'logradouro',
            'numero',
            'complemento',
            'cep',
            'bairro',
            'tipo_zona_residencial',
            'telefone_principal',
            'telefone_secundario',
            'facebook',
            'instagram',
            'twitter',
            'linkedin',
            'skype',
            'logradouro_profissional',
            'numero_profissional',
            'complemento_profissional',
            'cep_profissional',
            'bairro_profissional',
            'tipo_zona_residencial_profissional',
        )

    fieldsets = (
        ('Dados Pessoais', {'fields': ('estado_civil', 'numero_dependentes')}),
        (
            'Dados de Contato',
            {
                'fields': (
                    'email_pessoal',
                    'logradouro',
                    'numero',
                    'complemento',
                    'cep',
                    'bairro',
                    'tipo_zona_residencial',
                    'telefone_principal',
                    'telefone_secundario',
                    'facebook',
                    'instagram',
                    'twitter',
                    'linkedin',
                    'skype',
                )
            },
        ),
        (
            'Dados Profissionais',
            {
                'fields': (
                    'logradouro_profissional',
                    'numero_profissional',
                    'complemento_profissional',
                    'cep_profissional',
                    'bairro_profissional',
                    'tipo_zona_residencial_profissional',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['email_pessoal'].initial = self.instance.email_pessoal

    @transaction.atomic
    def save(self, *args, **kwargs):
        aluno = super().save(*args, **kwargs)
        v = aluno.get_vinculo()
        if v:
            v.email_pessoal = self.cleaned_data.get('email_pessoal') or ''
            v.save(update_fields=['email_pessoal'])


class PerguntaWidget(forms.MultiWidget):
    template_name = 'widgets/pergunta_resposta_unica_complementacao.html'

    def __init__(self, pergunta, widgets=(RenderableRadioSelect, forms.TextInput), objects=None, attrs=None):
        if attrs is None:
            attrs = {}
        if objects is None:
            objects = []
        super(self.__class__, self).__init__(widgets, attrs)
        self.pergunta = pergunta

    def decompress(self, value):
        if not value:
            return ['', '']
        return value

    def get_context(self, name, value, attrs):
        context = super().get_context(name, value, attrs)
        widget2_disable = True
        for option in context['widget']['subwidgets'][0]['optgroups']:
            if (
                'checked' in list(option[1][0]['attrs'].keys())
                and 'object' in list(option[1][0].keys())
                and option[1][0]['object'].complementacao_subjetiva
                and option[1][0]['attrs']['checked']
            ):
                widget2_disable = False
        widget2_attrs = context['widget']['subwidgets'][1]['attrs']
        widget2_attrs['disabled'] = widget2_disable
        context['pergunta'] = self.pergunta
        return context


class PerguntaField(forms.MultiValueField):
    def __init__(self, fields=(forms.ModelChoiceField, forms.CharField), *args, **kwargs):
        super(forms.MultiValueField, self).__init__(*args, **kwargs)
        # Set 'required' to False on the individual fields, because the
        # required validation will be handled by MultiValueField, not by those
        # individual fields.
        self.fields = fields

    def clean(self, value):
        """
        Retorna [(data), (data+1 dia)], pois o formato facilita as pesquisas
        em banco de dados: .filter(date__gt=start_date, date__lt=end_date)
        """
        if not value:
            return ['', '']
        else:
            opcao = self.fields[0].clean(value=value[0])
            if opcao.complementacao_subjetiva and not value[1]:
                raise forms.ValidationError(f'Ao escolhar a opção "{opcao.conteudo}", deve haver uma complementação textual.')
            else:
                outro = value[1]
        return [opcao, outro]


class ResponderBlocoForm(FormPlus):
    def __init__(self, categoria, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.categoria = categoria
        self.aluno = Aluno.objects.get(matricula=self.request.user.username)

        for pergunta in categoria.pergunta_set.all():
            pergunta_id = f'pergunta_{pergunta.pk}'
            resposta = Resposta.objects.get_or_create(aluno=self.aluno, pergunta=pergunta)[0]
            if pergunta.tipo == Pergunta.OBJETIVA_RESPOSTA_UNICA:
                self.fields[pergunta_id] = forms.ModelChoiceField(
                    pergunta.opcao_set.all(),
                    required=pergunta.preenchimento_obrigatorio,
                    label='',
                    widget=RenderableRadioSelect('widgets/pergunta_resposta_unica.html'),
                    initial=resposta.opcoes.exists() and resposta.opcoes.all()[0].pk or None,
                )
            elif pergunta.tipo == Pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA:
                if self.request.POST:
                    initial = self.request.POST.getlist(pergunta_id)
                else:
                    initial = []
                    initial.append(resposta.opcoes.exists() and resposta.opcoes.all()[0].pk or None)
                    initial.append(resposta.opcoes.exists() and resposta.resposta_subjetiva or None)
                field_radio = forms.ModelChoiceField(
                    pergunta.opcao_set.all(),
                    required=pergunta.preenchimento_obrigatorio,
                    label='',
                    widget=RenderableRadioSelect('widgets/pergunta_resposta_unica.html'),
                    initial=resposta.opcoes.exists() and resposta.opcoes.all()[0].pk or None,
                )
                field_texto = forms.CharFieldPlus(initial=resposta.resposta_subjetiva, label='')
                self.fields[pergunta_id] = PerguntaField(
                    fields=[field_radio, field_texto],
                    initial=initial,
                    widget=PerguntaWidget(pergunta=pergunta, widgets=[field_radio.widget, field_texto.widget]),
                    label='',
                )

            elif pergunta.tipo == Pergunta.OBJETIVA_RESPOSTAS_MULTIPLAS:
                if self.request.POST:
                    initial = Opcao.objects.filter(id__in=[int(id) for id in self.request.POST.getlist(pergunta_id)])

                else:
                    initial = [opcao.pk for opcao in resposta.opcoes.all()]
                self.fields[pergunta_id] = forms.MultipleModelChoiceField(
                    pergunta.opcao_set.all(),
                    required=pergunta.preenchimento_obrigatorio,
                    label='',
                    widget=RenderableCheckboxSelect(template_name='widgets/pergunta_respostas_multiplas.html'),
                    initial=initial,
                )

            elif pergunta.tipo == Pergunta.SUBJETIVA:
                self.fields[pergunta_id] = forms.CharFieldPlus(
                    label=pergunta.conteudo, required=pergunta.preenchimento_obrigatorio, widget=forms.Textarea(), initial=resposta.resposta_subjetiva
                )

    @transaction.atomic
    def save(self):
        for pergunta in self.categoria.pergunta_set.all():
            resposta = Resposta.objects.get_or_create(aluno=self.aluno, pergunta=pergunta)[0]
            cleaned_pergunta = self.cleaned_data.get(f'pergunta_{pergunta.pk}', None)
            if cleaned_pergunta:
                if pergunta.tipo == pergunta.SUBJETIVA:
                    resposta.resposta_subjetiva = cleaned_pergunta
                    resposta.save()
                elif pergunta.tipo == pergunta.OBJETIVA_RESPOSTA_UNICA_COM_OPCAO_SUBJETIVA:
                    resposta.resposta_subjetiva = cleaned_pergunta[1]
                    resposta.opcoes.set([cleaned_pergunta[0]])
                    resposta.save()
                else:
                    if isinstance(cleaned_pergunta, Iterable):
                        resposta.opcoes.set(cleaned_pergunta)
                        resposta.save()
                    else:
                        resposta.opcoes.set([cleaned_pergunta])
                        resposta.save()
        return True


class PublicarPesquisaForm(ModelFormPlus):
    SUBMIT_LABEL = 'Publicar a Pesquisa e Enviar Convites'

    class Meta:
        model = Pesquisa
        fields = ('inicio', 'fim')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['inicio'].required = True
        self.fields['fim'].required = True

    def clean(self):
        inicio = self.cleaned_data.get('inicio', None)
        fim = self.cleaned_data.get('fim', None)
        if inicio and fim and fim < inicio:
            raise forms.ValidationError('Data de fim deve ser após a data de início.')
        if not self.instance.categoria_set.exists():
            raise forms.ValidationError(
                'Para que esta pesquisa possa ser publicada, devem ser cadastradas '
                'categorias de perguntas e posteriormente relacionadas perguntas '
                'a essas categorias.'
            )
        for categoria in self.instance.categoria_set.all():
            if not categoria.pergunta_set.exists():
                raise forms.ValidationError(
                    f'Não é possível publicar esta pesquisa pois a categoria {categoria} não possui pergunta alguma cadastrada.'
                )
        if self.instance.ha_pergunta_objetiva_com_opcao_subjetiva_sem_opcao_complementacao_definida():
            pergunta_inconsistente = self.instance.perguntas_objetivas_com_opcao_subjetiva_sem_opcao_complementacao_definida()[0]
            raise forms.ValidationError(
                f'Não será possível publicar esta pesquisa pois a pergunta "{pergunta_inconsistente.conteudo}" está sem opção de complementação definida.'
            )

    def save(self, *args, **kwargs):
        self.instance.publicada = True
        super().save(*args, **kwargs)
        self.instance.enviar_convites()
