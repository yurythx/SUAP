import datetime

from django.conf import settings

from comum.models import Vinculo
from comum.utils import get_sigla_reitoria
from djtools import forms
from djtools.forms import AutocompleteWidget
from djtools.forms.widgets import CheckboxTooltipSelectPlus, FilteredSelectMultiplePlus
from djtools.utils import send_notification
from edu.models import Aluno
from edu.models.cursos import CursoCampus
from edu.models.diretorias import Diretoria
from edu.models.turmas import Turma
from etep.models import (
    Acompanhamento,
    AcompanhamentoCategoria,
    AcompanhamentoEncaminhamento,
    Categoria,
    Documento,
    Encaminhamento,
    Interessado,
    RegistroAcompanhamento,
    RegistroAcompanhamentoInteressado,
    SolicitacaoAcompanhamento,
    SolicitacaoAcompanhamentoCategoria,
)
from rh.models import UnidadeOrganizacional


class AcompanhamentoForm(forms.ModelFormPlus):
    aluno = forms.ModelChoiceFieldPlus(Aluno.locals_uo, required=True)
    categorias = forms.MultipleModelChoiceFieldPlus(Categoria.objects, label='Tipos', widget=CheckboxTooltipSelectPlus(tooltip_field='descricao'))
    descricao = forms.CharField(label='Descrição', required=True, widget=forms.Textarea())

    class Meta:
        model = Acompanhamento
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            categorias = Categoria.objects.filter(id__in=self.instance.acompanhamentocategoria_set.values_list('categoria', flat=True))
            self.fields['categorias'].initial = categorias

    def save(self, *args, **kwargs):
        categorias = self.cleaned_data.get('categorias')
        descricao = self.cleaned_data.get('descricao')
        obj = super().save(*args, **kwargs)
        self.instance.save()
        AcompanhamentoCategoria.objects.filter(acompanhamento=obj).delete()
        for categoria in categorias:
            AcompanhamentoCategoria.objects.get_or_create(categoria=categoria, acompanhamento=obj)
        if not RegistroAcompanhamento.objects.filter(acompanhamento=obj).exists():
            RegistroAcompanhamento.objects.create(acompanhamento=obj, descricao=descricao, situacao=RegistroAcompanhamento.EM_ACOMPANHAMENTO)
        return obj


class RegistroAcompanhamentoForm(forms.ModelFormPlus):
    interessados = forms.MultipleModelChoiceFieldPlus(
        Interessado.objects,
        label='Tornar visível para interessados',
        required=False,
        widget=forms.CheckboxSelectMultiplePlus,
        help_text='A ETEP sempre terá acesso a todos os registros',
    )

    class Meta:
        model = RegistroAcompanhamento
        exclude = ('acompanhamento', 'situacao')

    def __init__(self, acompanhamento, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.acompanhamento = acompanhamento
        self.fields['descricao'].required = True
        self.fields['interessados'].queryset = Interessado.objects.filter(acompanhamento=acompanhamento, ativado=True).exclude(
            vinculo__user=self.request.user
        )
        if self.instance.pk:
            self.fields['interessados'].initial = RegistroAcompanhamentoInteressado.objects.filter(registro_acompanhamento=self.instance).values_list(
                'interessado', flat=True
            )

    def processar(self):
        interessados = self.cleaned_data.get('interessados')
        RegistroAcompanhamentoInteressado.objects.filter(registro_acompanhamento=self.instance).delete()
        vinculos = []
        for membro in self.instance.acompanhamento.get_membros_etep():
            vinculos.append(membro.get_vinculo())

        # se for o proprio interessado cadastrando um registro
        funcionario = Interessado.objects.filter(acompanhamento=self.instance.acompanhamento, vinculo__user=self.request.user)
        if funcionario.exists():
            RegistroAcompanhamentoInteressado.objects.get_or_create(
                interessado=funcionario[0], registro_acompanhamento=self.instance, data_ciencia=datetime.datetime.now()
            )

        # cadastrando todos os interessados
        for interessado in interessados:
            RegistroAcompanhamentoInteressado.objects.get_or_create(interessado=interessado, registro_acompanhamento=self.instance)
            vinculos.append(interessado.vinculo)
        if vinculos:
            self.instance.enviar_emails(vinculos)


class SituacaoAcompanhamentoForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroAcompanhamento
        fields = ('situacao',)

    def __init__(self, acompanhamento, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.acompanhamento = acompanhamento

    def clean(self):
        if self.instance.acompanhamento.situacao == self.cleaned_data.get('situacao'):
            raise forms.ValidationError('Esta já é a situação atual.')
        if (
            self.cleaned_data.get('situacao') == RegistroAcompanhamento.ACOMPANHAMENTO_FINALIZADO
            and not AcompanhamentoEncaminhamento.objects.filter(acompanhamento=self.instance.acompanhamento).exists()
        ):
            raise forms.ValidationError('É necessário registrar pelo menos um encaminhamento para finalizar o acompanhamento.')


class SolicitacaoAcompanhamentoForm(forms.ModelFormPlus):
    categorias = forms.ModelMultipleChoiceField(Categoria.objects, label='Tipos', widget=FilteredSelectMultiplePlus('', True))
    aluno = forms.ModelChoiceFieldPlus(Aluno.objects, required=True)

    class Meta:
        model = SolicitacaoAcompanhamento
        fields = ('aluno', 'descricao')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            categorias = Categoria.objects.filter(id__in=self.instance.solicitacaoacompanhamentocategoria_set.values_list('categoria', flat=True))
            self.fields['categorias'].initial = categorias

        setor = self.request.user.get_vinculo().setor
        if self.request.GET.get('diario'):
            diario_pk = self.request.GET.get('diario')
            self.fields['aluno'].queryset = Aluno.objects.filter(matriculaperiodo__matriculadiario__diario__pk=diario_pk).distinct()
        elif setor is None:
            self.fields['aluno'].queryset = Aluno.objects.none()
        elif setor.uo.sigla != get_sigla_reitoria():
            self.fields['aluno'].queryset = Aluno.objects.filter(curso_campus__diretoria__setor__uo_id=setor.uo_id).distinct()

    def save(self, *args, **kwargs):
        categorias = self.cleaned_data.get('categorias')
        obj = super().save(*args, **kwargs)
        self.instance.save()
        for categoria in categorias:
            SolicitacaoAcompanhamentoCategoria.objects.get_or_create(categoria=categoria, solicitacao=obj)
        return obj


class InteressadosForm(forms.FormPlus):
    coordenadores = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.none(), label='Coordenadores do Curso', required=False, widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
    )
    professores = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.none(), label='Professores', required=False, widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
    )
    etep = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.none(), label='ETEP', required=False, widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
    )
    multiprofissionais = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.none(), label='Equipe Multiprofissional', required=False, widget=forms.CheckboxSelectMultiple(attrs={'class': 'checkboxes'})
    )

    funcao = forms.ChoiceField(label='Função', choices=[['', ''], *Interessado.FUNCAO_CHOICES], required=False)
    outros = forms.MultipleModelChoiceFieldPlus(Vinculo.objects.none(), label='Outros', required=False)

    fieldsets = (
        ('Vínculos Sugeridos', {'fields': ('coordenadores', 'professores', 'etep', 'multiprofissionais')}),
        (
            'Outros Vínculos',
            {
                'fields': (
                    'funcao',
                    'outros',
                )
            },
        ),
    )

    def __init__(self, acompanhamento, *args, **kwargs):
        self.acompanhamento = acompanhamento
        super().__init__(*args, **kwargs)
        mp = acompanhamento.aluno.get_ultima_matricula_periodo()
        pks = (
            acompanhamento.aluno.curso_campus.coordenador_id,
            acompanhamento.aluno.curso_campus.coordenador_2_id,
        )
        self.fields['coordenadores'].queryset = Vinculo.objects.filter(pk__in=pks)
        pks = mp.matriculadiario_set.values_list('diario__professordiario__professor__vinculo', flat=True)
        self.fields['professores'].queryset = Vinculo.objects.filter(pk__in=pks)
        self.fields['etep'].queryset = Vinculo.objects.filter(
            user__usuariogrupo__usuariogruposetor__setor=acompanhamento.aluno.curso_campus.diretoria.setor_id,
            user__usuariogrupo__group__name='Pedagogo',
        )
        self.fields['multiprofissionais'].queryset = Vinculo.objects.filter(
            setor__uo=acompanhamento.aluno.curso_campus.diretoria.setor.uo_id,
            user__usuariogrupo__group__name__in=('Assistente Social', 'Psicólogo', 'Coordenador do Napne'),
        )
        self.fields['outros'].queryset = Vinculo.objects.funcionarios_ativos()

    def processar(self):
        funcao = self.cleaned_data.get('funcao') or None
        pks = {
            'coordenador_curso': list(self.cleaned_data.get('coordenadores').values_list('pk', flat=True)),
            'professor': list(self.cleaned_data.get('professores').values_list('pk', flat=True)),
            'etep': list(self.cleaned_data.get('etep').values_list('pk', flat=True)),
            'multiprofissional': list(self.cleaned_data.get('multiprofissionais').values_list('pk', flat=True)),
        }
        pks.setdefault(funcao, []).extend(self.cleaned_data.get('outros').values_list('pk', flat=True))
        self.acompanhamento.aluno.get_ultima_matricula_periodo()

        url_acompanhamento = settings.SITE_URL + self.acompanhamento.get_absolute_url()
        for funcao, ids in pks.items():
            for vinculo in Vinculo.objects.filter(id__in=ids):
                if not Interessado.objects.filter(acompanhamento=self.acompanhamento, vinculo=vinculo).exists():
                    Interessado.objects.create(acompanhamento=self.acompanhamento, vinculo=vinculo, funcao=funcao)
                    titulo = '[SUAP] Interessado ETEP'
                    texto = f"""<h1>Interessado ETEP</h1>
                        <p>Você foi adicionado(a) pelo(a) servidor(a) {self.request.user} ao acompanhamento do(a) aluno(a) {self.acompanhamento.aluno}.
                        <a href="{url_acompanhamento}">Clique aqui</a> para verificar o acompanhamento,
                        ou acesse todos os acompanhamentos através no menu Ensino -> ETEP - > Acompanhamentos.</p>
                        """
                    send_notification(titulo, texto, settings.DEFAULT_FROM_EMAIL, [vinculo])


class NotificarInteressadosForm(forms.FormPlus):
    interessados = forms.MultipleModelChoiceFieldPlus(
        Interessado.objects, label='Interessados', required=False, widget=forms.CheckboxSelectMultiplePlus
    )

    def __init__(self, registro, *args, **kwargs):
        self.registro = registro
        self.eh_acompanhamento = hasattr(self.registro, 'descricao')
        super().__init__(*args, **kwargs)
        pks = RegistroAcompanhamentoInteressado.objects.filter(registro_acompanhamento=self.registro).values_list('interessado', flat=True)
        self.fields['interessados'].queryset = (
            Interessado.objects.filter(acompanhamento=self.registro.acompanhamento).exclude(vinculo__user=self.request.user).exclude(pk__in=pks)
        )

    def processar(self):
        vinculos = []
        interessados = self.cleaned_data.get('interessados')
        for interessado in interessados:
            RegistroAcompanhamentoInteressado.objects.create(interessado=interessado, registro_acompanhamento=self.registro)
            vinculos.append(interessado.vinculo)
        if vinculos:
            self.registro.enviar_emails(vinculos)


class DesvincularInteressadosForm(forms.FormPlus):
    interessados = forms.MultipleModelChoiceFieldPlus(
        Interessado.objects, label='Interessados', required=False, widget=forms.CheckboxSelectMultiplePlus
    )

    def __init__(self, registro, *args, **kwargs):
        self.registro = registro
        self.eh_acompanhamento = hasattr(self.registro, 'descricao')
        super().__init__(*args, **kwargs)
        pks = RegistroAcompanhamentoInteressado.objects.filter(registro_acompanhamento=self.registro).values_list('interessado', flat=True)
        self.fields['interessados'].queryset = Interessado.objects.filter(pk__in=pks)

    def processar(self):
        interessados = self.cleaned_data.get('interessados')
        RegistroAcompanhamentoInteressado.objects.filter(registro_acompanhamento=self.registro, interessado__in=interessados).exclude(
            interessado__vinculo__user=self.request.user
        ).delete()


class AdicionarEncaminhamentosForm(forms.FormPlus):
    encaminhamentos = forms.ModelMultipleChoiceField(
        Encaminhamento.objects, label='Encaminhamentos', required=False, widget=forms.CheckboxSelectMultiplePlus(attrs={'class': 'checkboxes'})
    )

    def __init__(self, acompanhamento, *args, **kwargs):
        self.acompanhamento = acompanhamento
        super().__init__(*args, **kwargs)
        self.fields['encaminhamentos'].queryset = self.fields['encaminhamentos'].queryset.order_by('nome')

    def processar(self):
        for encaminhamento in self.cleaned_data.get('encaminhamentos'):
            AcompanhamentoEncaminhamento.objects.create(acompanhamento=self.acompanhamento, encaminhamento=encaminhamento)


class DocumentoForm(forms.ModelFormPlus):
    def __init__(self, atividade, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.instance.atividade = atividade

    class Meta:
        model = Documento
        exclude = ('atividade',)


class RelatorioAcompanhamentoForm(forms.Form):
    SUBMIT_LABEL = 'Consultar'
    METHOD = 'get'
    categorias = forms.ModelMultiplePopupChoiceField(Categoria.objects, label='Categorias', required=False)
    campi = forms.ModelMultiplePopupChoiceField(UnidadeOrganizacional.locals, label='Campi', required=False)
    diretorias = forms.ModelMultiplePopupChoiceField(
        Diretoria.objects.none(),
        label='Diretorias',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Diretoria.SEARCH_FIELDS, form_filters=[('campi', 'setor__uo__in')]),
    )
    cursos = forms.MultipleModelChoiceFieldPlus(
        CursoCampus.locals,
        label='Cursos',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=CursoCampus.SEARCH_FIELDS,
            form_filters=[('campi', 'diretoria__setor__uo__in'), ('diretorias', 'diretoria__in')],
        ),
    )
    turmas = forms.MultipleModelChoiceFieldPlus(
        Turma.objects.none(),
        label='Turmas',
        required=False,
        widget=AutocompleteWidget(
            multiple=True,
            search_fields=Turma.SEARCH_FIELDS,
            form_filters=[
                ('campi', 'curso_campus__diretoria__setor__uo__in'),
                ('diretorias', 'curso_campus__diretoria__in'),
                ('cursos', 'curso_campus__in'),
            ],
        ),
    )
    aluno = forms.ModelChoiceFieldPlus(Aluno.locals_diretoria, label='Aluno', required=False)
    vinculo = forms.ModelChoiceFieldPlus(Vinculo.objects, label='Interessado', required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['diretorias'].queryset = Diretoria.locals
        self.fields['turmas'].queryset = Turma.locals
        self.fields['vinculo'].queryset = Vinculo.objects.funcionarios()

    def processar(self):
        qs = Acompanhamento.locals.all()

        categorias = self.cleaned_data['categorias']
        campi = self.cleaned_data['campi']
        diretorias = self.cleaned_data['diretorias']
        cursos = self.cleaned_data['cursos']
        turmas = self.cleaned_data['turmas']
        aluno = self.cleaned_data['aluno']
        vinculo = self.cleaned_data['vinculo']

        if categorias:
            qs = qs.filter(acompanhamentocategoria__categoria__in=categorias)
        if campi:
            qs = qs.filter(aluno__curso_campus__diretoria__setor__uo__in=campi)
        if diretorias:
            qs = qs.filter(aluno__curso_campus__diretoria__in=diretorias)
        if cursos:
            qs = qs.filter(aluno__curso_campus__in=cursos)
        if turmas:
            qs = qs.filter(aluno__matriculaperiodo__turma__in=turmas)
        if aluno:
            qs = qs.filter(aluno=aluno)
        if vinculo:
            qs = qs.filter(interessado__vinculo=vinculo)

        return qs
