import datetime
from decimal import Decimal

from django.conf import settings
from django.contrib.auth.models import Group
from django.db import transaction
from django.db.models import Q
from django.forms.models import ModelChoiceField

from comum.models import Ano, Configuracao, Pais, PrestadorServico, TrocarSenha, UsuarioGrupo, Vinculo
from comum.types import PessoaFisicaCadastro, PessoaTelefoneCadastro, PrestadorServicoCadastro
from comum.utils import get_setor_proen, get_uo, tl
from djtools import forms
from djtools.forms import ReadOnlyField
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus, RenderableSelectMultiple
from djtools.templatetags.filters import format_
from djtools.utils import running_tests, send_mail
from edu.models import Aluno, Componente, CursoCampus, ProfessorDiario
from financeiro.models import NaturezaDespesa
from projetos_ensino.models import (
    AreaLicaoAprendida,
    Avaliacao,
    AvaliacaoAluno,
    AvaliadorExterno,
    CampusAdicional,
    CaracterizacaoBeneficiario,
    ColaboradorExterno,
    ComissaoAcompanhamento,
    ComissaoEdital,
    CriterioAvaliacao,
    CriterioAvaliacaoAluno,
    Desembolso,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EixoTematico,
    Etapa,
    FotoProjeto,
    HistoricoEquipe,
    HistoricoOrientacaoProjeto,
    ItemAvaliacao,
    ItemAvaliacaoAluno,
    ItemMemoriaCalculo,
    LicaoAprendida,
    Meta,
    OfertaProjeto,
    OrigemRecursoEdital,
    Participacao,
    Projeto,
    ProjetoAnexo,
    ProjetoCancelado,
    ProjetoHistoricoDeEnvio,
    Recurso,
    RecursoProjeto,
    RegistroConclusaoProjeto,
    RegistroExecucaoEtapa,
    RegistroFrequencia,
    RegistroGasto,
    TipoBeneficiario,
    TipoVinculo,
)
from rh.enums import Nacionalidade
from rh.deduplicacao.entrada import recusar_passaporte_de_outra_pessoa, travar_documentos_na_edicao, recusar_cadastro_de_prestador
from rh.models import AreaConhecimento, Banco, Servidor, Setor, UnidadeOrganizacional


class BuscaProjetoForm(forms.FormPlus):
    palavra_chave = forms.CharField(label='Palavra-chave', required=False)
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
    edital = forms.ModelChoiceField(queryset=Edital.objects, required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    METHOD = 'GET'

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES

        if self.request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            uos = CampusAdicional.get_campi_user(self.request.user, retornar_apenas_ids=True)
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(id__in=uos)
        else:
            if not self.request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
                self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)


class RegistroConclusaoProjetoForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroConclusaoProjeto
        exclude = ['projeto', 'dt_avaliacao', 'avaliador', 'aprovado', 'obs_avaliador']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.fields['disseminacao_resultados'].initial = self.projeto.resultados_esperados
        self.fields['disseminacao_resultados'].required = True
        self.fields['resultados_alcancados'].required = True


class RegistroConclusaoProjetoObsForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroConclusaoProjeto
        fields = [
            'obs_avaliador',
        ]


class EditalForm(forms.ModelFormPlus):
    participa_aluno = forms.BooleanField(
        label='Participação de Aluno Obrigatória',
        help_text='Marque esta opção caso seja obrigatória a participação de aluno em todos os projetos',
        required=False,
        initial=True,
    )
    participa_servidor = forms.BooleanField(
        label='Participação de Servidor Obrigatória',
        help_text='Marque esta opção caso seja obrigatória a participação de servidor em todos os projetos',
        required=False,
        initial=True,
    )
    inicio_pre_selecao = forms.DateTimeFieldPlus(label='Início da Pré-Seleção', required=False)
    inicio_selecao = forms.DateTimeFieldPlus(label='Início da Seleção', required=False)
    fim_selecao = forms.DateTimeFieldPlus(label='Fim da Seleção', required=False)
    divulgacao_selecao = forms.DateTimeFieldPlus(label='Divulgação da Seleção', required=False)

    class Meta:
        model = Edital
        exclude = ()

    class Media:
        js = ['/static/projetos_ensino/js/editalform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['valor_financiado_por_projeto'].required = False
        if self.instance.tipo_edital:
            self.fields['tipo_edital'].initial = self.instance.tipo_edital
            self.fields['tipo_edital'] = ReadOnlyField(label='Tipo do Edital')
            self.fields['tipo_edital'].initial = self.instance.tipo_edital
            self.fields['tipo_edital'].widget.display_value = self.instance.get_tipo_edital_display()

    def clean(self, *args, **kwargs):
        if (
            self.cleaned_data.get('fim_inscricoes')
            and self.cleaned_data.get('inicio_inscricoes')
            and self.cleaned_data['fim_inscricoes'] <= self.cleaned_data['inicio_inscricoes']
        ):
            raise forms.ValidationError('A data do fim das inscrições deve ser maior que a data do início das inscrições.')

        if not self.cleaned_data.get('inicio_pre_selecao'):
            self.add_error('inicio_pre_selecao', 'Preenchimento obrigatório.')

        if not self.cleaned_data.get('inicio_selecao'):
            self.add_error('inicio_selecao', 'Preenchimento obrigatório.')

        if not self.cleaned_data.get('fim_selecao'):
            self.add_error('fim_selecao', 'Preenchimento obrigatório.')

        if not self.cleaned_data.get('divulgacao_selecao'):
            self.add_error('divulgacao_selecao', 'Preenchimento obrigatório.')

        if self.cleaned_data.get('tipo_edital') and self.cleaned_data['tipo_edital'] == Edital.ENSINO:
            if (
                self.cleaned_data.get('inicio_pre_selecao')
                and self.cleaned_data.get('fim_inscricoes')
                and self.cleaned_data['inicio_pre_selecao'] <= self.cleaned_data['fim_inscricoes']
            ):
                raise forms.ValidationError('A data da pré-seleção deve ser maior que a data do fim das inscrições.')
            if (
                self.cleaned_data.get('inicio_pre_selecao')
                and self.cleaned_data.get('inicio_selecao')
                and self.cleaned_data['inicio_selecao'] <= self.cleaned_data['inicio_pre_selecao']
            ):
                raise forms.ValidationError('A data da seleção deve ser maior que a data da pré-seleção.')
            if (
                self.cleaned_data.get('divulgacao_selecao')
                and self.cleaned_data.get('inicio_selecao')
                and self.cleaned_data['divulgacao_selecao'] <= self.cleaned_data['inicio_selecao']
            ):
                raise forms.ValidationError('A data da divulgação deve ser maior que a data da seleção.')

        return super().clean(*args, **kwargs)


class RecursoForm(forms.ModelFormPlus):
    origem_recurso = forms.ModelChoiceField(queryset=OrigemRecursoEdital.objects.filter(ativo=True), label='Origem')

    class Meta:
        model = Recurso
        fields = ('origem_recurso', 'valor', 'despesa')

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk and OrigemRecursoEdital.objects.filter(descricao=self.instance.origem).exists():
            self.fields['origem_recurso'].initial = OrigemRecursoEdital.objects.filter(descricao=self.instance.origem)[0].id
        self.fields['valor'].label = 'Valor disponível por projeto (R$)'


class CriterioAvaliacaoForm(forms.ModelFormPlus):
    class Meta:
        model = CriterioAvaliacao
        exclude = ('edital',)


class EditalAnexoForm(forms.ModelFormPlus):
    anexoedital = forms.ModelChoiceFieldPlus(queryset=EditalAnexoAuxiliar.objects, label='Anexo do Edital', required=False)

    class Meta:
        model = EditalAnexo
        fields = ('anexoedital', 'nome', 'descricao', 'tipo_membro', 'vinculo', 'ordem')

    class Media:
        js = ['/static/projetos_ensino/js/anexodosprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        self.fields['anexoedital'].queryset = EditalAnexoAuxiliar.objects.filter(edital=self.edital)


class EditalAnexoAuxiliarForm(forms.ModelFormPlus):
    class Meta:
        model = EditalAnexoAuxiliar
        exclude = ('edital',)


class OfertaProjetoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo(), label='Campus:', empty_label='Selecione o Campus', required=True)

    class Meta:
        model = OfertaProjeto
        exclude = ('edital',)

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        self.fields['qtd_selecionados'].help_text = 'Informe quantos projetos serão selecionados.'

        if self.edital.forma_selecao == Edital.TEMA or self.edital.forma_selecao == Edital.GERAL:
            del self.fields['qtd_selecionados']

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if not self.instance.id and OfertaProjeto.objects.filter(edital=self.edital, uo=self.cleaned_data.get('uo')).exists():
            raise forms.ValidationError('Um plano de oferta para este campus já foi cadastrado.')

        return cleaned_data


class OfertaProjetoFormMultiplo(forms.FormPlus):
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi',
        queryset=UnidadeOrganizacional.objects.all(),
        widget=FilteredSelectMultiplePlus('', True),
        required=True,
    )


class ItemMemoriaCalculoForm(forms.ModelFormPlus):
    recurso = forms.ModelChoiceField(Recurso.objects, label='Recurso')
    fieldsets = ((None, {'fields': ('recurso', 'descricao', 'unidade_medida', 'qtd', 'valor_unitario')}),)

    class Meta:
        model = ItemMemoriaCalculo
        exclude = ('despesa', 'projeto', 'origem', 'data_cadastro')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.edicao = kwargs.pop('edicao', None)
        super().__init__(*args, **kwargs)

        if self.edicao:
            del self.fields['recurso']
        else:
            self.fields['recurso'].queryset = Recurso.objects.filter(id__in=self.projeto.edital.recurso_set.values_list('id', flat=True))


class ProjetoForm(forms.ModelFormPlus):
    edital = forms.ModelChoiceField(queryset=Edital.objects, widget=AutocompleteWidget(readonly=True))
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.uo(),
        label='Campus:',
        empty_label='Selecione o Campus',
        required=True,
    )
    setor = forms.ChainedModelChoiceField(
        queryset=Setor.objects.none(), label='Setor:', empty_label='Selecione o Campus', required=True, obj_label='sigla', form_filters=[('uo', 'uo')]
    )
    carga_horaria = forms.IntegerFieldPlus(label='Carga Horária Semanal do Coordenador')
    termo_compromisso_coordenador = TinyMCEFormField(label='Termo de Compromisso', required=False)
    aceita_termo = forms.BooleanField(label='Aceito o Termo de Compromisso', required=False, initial=False)
    fieldsets = (
        (
            'Dados gerais',
            {
                'fields': (
                    'edital',
                    'uo',
                    'setor',
                    'titulo',
                    'carga_horaria',
                )
            },
        ),
        (
            'Dados do Projeto',
            {
                'fields': (
                    'inicio_execucao',
                    'fim_execucao',
                    'ch_total',
                    'eixo_tematico',
                    'interdisciplinar',
                    'componentes',
                    'cursos',
                    'relacao_pesquisa_ext',
                    'parceiros_externos',
                    'quais_parceiros_externos',
                )
            },
        ),
        (
            'Descrição do Projeto',
            {
                'fields': (
                    'resumo',
                    'introducao',
                    'justificativa',
                    'objetivo_geral',
                    'metodologia',
                    'acompanhamento_e_avaliacao',
                    'resultados_esperados',
                    'referencias',
                    'termo_compromisso_coordenador',
                    'aceita_termo',
                )
            },
        ),
    )

    class Meta:
        model = Projeto
        fields = (
            'edital',
            'uo',
            'setor',
            'titulo',
            'ch_total',
            'carga_horaria',
            'eixo_tematico',
            'interdisciplinar',
            'componentes',
            'cursos',
            'relacao_pesquisa_ext',
            'parceiros_externos',
            'quais_parceiros_externos',
            'inicio_execucao',
            'fim_execucao',
            'resumo',
            'introducao',
            'justificativa',
            'objetivo_geral',
            'metodologia',
            'acompanhamento_e_avaliacao',
            'resultados_esperados',
            'referencias',
        )

    class Media:
        js = ['/static/projetos_ensino/js/projetoform.js']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.edicao = kwargs.pop('edicao', None)
        super().__init__(*args, **kwargs)
        self.fields['setor'].queryset = Setor.objects.suap()
        self.fields['eixo_tematico'].queryset = EixoTematico.objects.filter(ativo=True)
        vinculo = self.request.user.get_vinculo()
        if self.edicao:
            part = Participacao.objects.filter(vinculo_pessoa=vinculo, projeto=self.instance)
            if part.exists():
                part = part[0]
                self.fields['carga_horaria'].initial = part.carga_horaria
            self.fields['setor'].initial = self.instance.setor.id

        campus = self.instance.edital.get_uos()
        if not self.instance.edital.pode_escolher_campus_submissao:
            setores_ids = []
            if vinculo.eh_servidor():
                if self.request.user.get_relacionamento().setor_lotacao:
                    if self.request.user.get_relacionamento().setor_lotacao.uo.equivalente:
                        setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.equivalente.id]
                    else:
                        setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.id]

                if self.request.user.get_relacionamento().setor:
                    setores_ids += [self.request.user.get_relacionamento().setor.uo.id]

                if not running_tests():
                    if self.request.user.get_relacionamento().setor_exercicio:
                        setores_ids += [self.request.user.get_relacionamento().setor_exercicio.uo.id]
            else:
                setores_ids += [self.request.user.get_relacionamento().curso_campus.diretoria.setor.uo.id]

            campus = campus.filter(id__in=setores_ids)
        self.fields['uo'].queryset = campus
        if not campus.exists():
            self.fields['uo'].help_text = 'Você não possui vínculo com nenhum campus do plano de oferta deste edital.'
        self.fields['resultados_esperados'].label = 'Resultados Esperados e Disseminação dos Resultados'
        if self.instance.pk:
            del self.fields['termo_compromisso_coordenador']
            del self.fields['aceita_termo']
        if not self.instance.pk and not self.instance.edital.exige_termo_coordenador():
            del self.fields['termo_compromisso_coordenador']
            del self.fields['aceita_termo']
        elif not self.instance.pk:
            self.fields['termo_compromisso_coordenador'].initial = self.instance.edital.termo_compromisso_coordenador
            self.fields['termo_compromisso_coordenador'].widget.attrs['readonly'] = True
        if vinculo.eh_servidor():
            ids = ProfessorDiario.objects.filter(professor__vinculo_id=vinculo.id).values_list(
                'diario__componente_curricular__componente_id', flat=True
            )
        else:
            ids = Aluno.objects.filter(matricula=self.request.user.username).values_list('matriz__componentes', flat=True)
        self.fields['componentes'].queryset = Componente.objects.filter(id__in=ids)
        self.fields['cursos'].queryset = CursoCampus.objects.filter(ativo=True, matrizes__isnull=False).exclude(ch_total__gt=0)

    def clean(self, *args, **kwargs):
        if not self.request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            if self.instance and self.instance.data_pre_avaliacao:
                raise forms.ValidationError('O projeto já foi pré-avaliado')
            if (
                self.instance.pk
                and self.instance.participacao_set.count()
                and not Participacao.objects.filter(responsavel=True, vinculo_pessoa=tl.get_user().get_vinculo())
            ):
                raise forms.ValidationError('Apenas o coordenador pode editar o projeto')

        if self.cleaned_data.get('parceiros_externos') and not self.cleaned_data.get('quais_parceiros_externos'):
            self.add_error('quais_parceiros_externos', 'Informe quais são os parceiros externos.')
        if self.cleaned_data.get('interdisciplinar') and not self.cleaned_data.get('componentes'):
            self.add_error('componentes', 'Informe quais são as disciplinas.')
        if not self.instance.pk and self.instance.edital.exige_termo_coordenador() and not self.cleaned_data['aceita_termo']:
            self.add_error('aceita_termo', 'Você precisa aceitar o termo de compromisso para submeter o projeto.')
        return super().clean(*args, **kwargs)


def ext_combo_template_aluno(obj):
    out = [f'<h4>{obj}</h4>']
    img_src = obj.foto and obj.foto.url or '/static/comum/img/default.jpg'
    out.append(f'<p>{obj.curso_campus}</p>')

    template = """<div class="person">
        <div class="photo-circle">
            <img src="{}" />
        </div>
        <div>
            {}
        </div>
    </div>
    """.format(img_src, ''.join(out))
    return template


class ParticipacaoAlunoForm(forms.ModelFormPlus):
    aluno = forms.ModelChoiceField(
        queryset=Aluno.ativos.all(),
        widget=AutocompleteWidget(extraParams={'ext_combo_template': ext_combo_template_aluno}, search_fields=Aluno.SEARCH_FIELDS),
        label='Participante',
        required=True,
    )
    vinculo = forms.ChoiceField(label='Bolsista', required=True, choices=TipoVinculo.TIPOS)
    data = forms.DateFieldPlus(label='Data de Entrada', help_text='A data não pode ser maior do que hoje.')
    indicar_pessoa_posteriormente = forms.BooleanField(label='Indicar o Aluno Posteriormente', required=False)

    class Meta:
        model = Participacao
        fields = (
            'vinculo',
            'carga_horaria',
            'indicar_pessoa_posteriormente',
            'aluno',
            'data',
        )

    class Media:
        js = ['/static/projetos_ensino/js/adicionaralunoform.js']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.edital = self.projeto.edital
        self.editar = kwargs.pop('editar', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            if self.instance.vinculo_pessoa:
                self.fields.pop('aluno')
                del self.fields['indicar_pessoa_posteriormente']
            elif self.edital.permite_indicacao_tardia_equipe:
                if self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
                    self.fields['aluno'].required = False
                    self.fields['data'].required = False
                else:
                    del self.fields['indicar_pessoa_posteriormente']
            self.historico = HistoricoEquipe.objects.filter(participante=self.instance, projeto=self.instance.projeto).order_by('id')
            if self.historico and self.historico[0].data_movimentacao:
                self.fields['data'].initial = self.historico[0].data_movimentacao

        elif self.edital.permite_indicacao_tardia_equipe and self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
            self.fields['aluno'].required = False
            self.fields['data'].required = False
        else:
            del self.fields['indicar_pessoa_posteriormente']

    def clean(self):
        if self.instance.pk:
            instance = self.instance.projeto
            if self.historico.order_by('-id').exists():
                if (
                    self.cleaned_data.get('data')
                    and self.historico.order_by('-id')[0].data_movimentacao_saida
                    and self.cleaned_data.get('data') > self.historico.order_by('-id')[0].data_movimentacao_saida
                ):
                    raise forms.ValidationError(
                        'A data informada é maior do que a data de término do vínculo mais recente do participante, não é possível inserir/editar aluno.'
                    )
        else:
            instance = self.projeto

        if self.cleaned_data.get('data') and self.cleaned_data.get('data') > instance.fim_execucao:
            raise forms.ValidationError('A data informada é maior do que a data de término do projeto, não é possível inserir/editar aluno.')

        if instance.fim_execucao < datetime.date.today():
            raise forms.ValidationError(
                'A data de término da execução do projeto é menor do que a data de hoje, não é possível inserir/editar aluno.'
            )

        if not self.instance.vinculo_pessoa:
            if self.edital.permite_indicacao_tardia_equipe and not self.cleaned_data.get('indicar_pessoa_posteriormente'):
                if not self.cleaned_data.get('aluno') and self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
                    raise forms.ValidationError('Selecione o aluno ou marque a opção de indicar o aluno posteriormente.')
                elif not self.cleaned_data.get('aluno'):
                    raise forms.ValidationError('Selecione o aluno.')
                if not self.cleaned_data.get('data') and self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
                    raise forms.ValidationError('Informe a data de entrada ou marque a opção de indicar o aluno posteriormente.')
                elif not self.cleaned_data.get('data'):
                    raise forms.ValidationError('Informe a data de entrada.')
        return self.cleaned_data


def ext_combo_template_servidor(obj):
    out = [f'<h4>{obj.pessoa_fisica.nome} (Mat. {obj.matricula})</h4>']
    if obj.setor:
        out.append(f'<p>{obj.setor.get_caminho_as_html()}</p>')
    if obj.cargo_emprego:
        out.append(f'<p>{obj.cargo_emprego}</p>')
    _vinculo = next(iter(getattr(obj, '_vinculo_servidor_list', [])), None)
    if _vinculo is not None and hasattr(_vinculo, 'vinculo_curriculo_lattes'):
        out.append('<p>Tem currículo Lattes</p>')
    else:
        out.append('<p class="false">Não há currículo Lattes</p>')
    template = """<div class="person">
        <div class="photo-circle">
            <img src="{}" />
        </div>
        <div>
            {}
        </div>
    </div>
    """.format(obj.get_foto_75x100_url(), ''.join(out))
    return template


class ParticipacaoServidorForm(forms.ModelFormPlus):
    servidor = forms.ModelChoiceField(
        queryset=Servidor.objects.ativos(),
        widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS, extraParams={'ext_combo_template': ext_combo_template_servidor}),
        label='Participante',
        required=True,
    )
    vinculo = forms.ChoiceField(label='Bolsista', required=True, choices=TipoVinculo.TIPOS)
    data = forms.DateFieldPlus(label='Data de Entrada', help_text='A data não pode ser maior do que hoje.')

    class Meta:
        model = Participacao
        fields = ('vinculo', 'carga_horaria', 'servidor', 'data')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['carga_horaria'].help_text = 'Caso o participante seja docente, informe a carga horária semanal em horas/aula'
        if self.instance.pk:
            self.fields.pop('servidor')
            self.historico = HistoricoEquipe.objects.filter(participante=self.instance, projeto=self.instance.projeto).order_by('id')
            self.fields['data'].initial = self.historico[0].data_movimentacao

    def clean(self):
        if self.instance.pk:
            instance = self.instance.projeto
            if self.historico.exists():
                if (
                    self.cleaned_data.get('data')
                    and self.historico.order_by('-id')[0].data_movimentacao_saida
                    and self.cleaned_data.get('data') > self.historico.order_by('-id')[0].data_movimentacao_saida
                ):
                    raise forms.ValidationError(
                        'A data informada é maior do que a data de término do vínculo mais recente do participante, não é possível inserir/editar servidor.'
                    )
        else:
            instance = self.projeto
        if self.cleaned_data.get('data') and self.cleaned_data.get('data') > instance.fim_execucao:
            raise forms.ValidationError('A data informada é maior do que a data de término do projeto, não é possível inserir/editar servidor.')

        if instance.fim_execucao < datetime.date.today():
            raise forms.ValidationError(
                'A data de término da execução do projeto é menor do que a data de hoje, não é possível inserir/editar servidor.'
            )

        if self.cleaned_data.get('carga_horaria') and self.instance and self.instance.responsavel:
            if self.instance.vinculo_pessoa.user.get_relacionamento().eh_docente:
                if self.cleaned_data.get('carga_horaria') > 8:
                    self.add_error('carga_horaria', 'O máximo permitido são 8 horas-aula.')
            elif self.instance.vinculo_pessoa.user.get_relacionamento().eh_tecnico_administrativo:
                if self.cleaned_data.get('carga_horaria') > 6:
                    self.add_error('carga_horaria', 'O máximo permitido são 6 horas.')

        return self.cleaned_data


def ext_combo_template_colaborador(obj):
    identificador = obj.prestador.pessoa_fisica.cpf or obj.prestador.pessoa_fisica.passaporte
    out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{obj.nome} (CPF/Passaporte: {identificador})</dd>']
    if obj.prestador.setor:
        out.append(f'<dt class="visually-hidden">Setor</dt><dd>{obj.prestador.setor.get_caminho_as_html()}</dd>')
    template = """<div class="person">
        <dl>{}</dl>
    </div>
    """.format(''.join(out))
    return template


class AlterarCoordenadorForm(forms.FormPlus):
    participacao = forms.ModelChoiceField(Participacao.objects, label='Novo Coordenador', required=True)
    data = forms.DateFieldPlus(label='Data Inicial da Nova Coordenação')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        qs_participacoes = self.projeto.participacao_set.filter(ativo=True)
        servidores_ids = []
        for p in qs_participacoes:
            if p.is_servidor():
                servidores_ids.append(p.vinculo_pessoa.id)
        self.fields['participacao'].queryset = self.projeto.participacao_set.filter(ativo=True, vinculo_pessoa__in=servidores_ids, responsavel=False)
        self.initial['data'] = datetime.date.today()

    def clean(self):
        if self.projeto.fim_execucao < self.cleaned_data.get('data'):
            raise forms.ValidationError('A data informada é maior do que a data de término da execução do projeto.')
        return self.cleaned_data


class MetaForm(forms.ModelFormPlus):
    class Meta:
        model = Meta
        exclude = ('projeto', 'data_cadastro')


class EtapaForm(forms.ModelFormPlus):
    responsavel = forms.ModelChoiceField(Participacao.objects, label='Responsável', required=True)
    integrantes = forms.MultipleModelChoiceField(Participacao.objects, label='Integrantes da Atividade', required=False)

    class Meta:
        model = Etapa
        exclude = ('meta', 'data_cadastro')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('proj', None)
        super().__init__(*args, **kwargs)
        self.fields['responsavel'].queryset = self.projeto.participacao_set.filter(ativo=True)
        self.fields['integrantes'].queryset = self.projeto.participacao_set.filter(ativo=True)
        if self.instance.pk:
            self.initial['integrantes'] = [t.pk for t in self.instance.integrantes.all()]
        self.fields['unidade_medida'].label = 'Indicador Quantitativo'

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if self.cleaned_data.get('inicio_execucao') and self.cleaned_data.get('fim_execucao'):
            if self.cleaned_data['inicio_execucao'] > self.projeto.fim_execucao:
                raise forms.ValidationError('A data de início de execução da atividade não pode ser maior que a data final de execução do projeto.')

            if self.cleaned_data['fim_execucao'] > self.projeto.fim_execucao:
                raise forms.ValidationError('A data do fim de execução da atividade não pode ser maior que a data final de execução do projeto.')

            if self.cleaned_data['inicio_execucao'] > self.cleaned_data['fim_execucao']:
                raise forms.ValidationError('A data de início de execução da atividade não pode ser maior que a data final de execução da atividade.')

        return cleaned_data


class EquipeEtapaForm(forms.ModelFormPlus):
    integrantes = forms.MultipleModelChoiceField(Participacao.objects, label='Integrantes da Atividade', required=False)

    class Meta:
        model = Etapa
        fields = ['responsavel', 'integrantes']

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('proj', None)
        super().__init__(*args, **kwargs)
        self.fields['integrantes'].queryset = projeto.participacao_set.filter(ativo=True)
        self.initial['integrantes'] = [t.pk for t in self.instance.integrantes.all()]

        self.fields['responsavel'].queryset = projeto.participacao_set.filter(ativo=True)
        self.fields['responsavel'].initial = self.instance.responsavel


class DesembolsoForm(forms.ModelFormPlus):
    clonar_operacao = forms.IntegerFieldPlus(
        label='Repetir Desembolso até o mês',
        max_length=2,
        required=False,
        help_text='Deixe em branco se este desembolso não se repetirá nos meses subsequentes.',
    )

    class Meta:
        model = Desembolso
        exclude = ('projeto', 'data_cadastro', 'despesa')
        fields = ['item', 'ano', 'mes', 'valor']

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('proj', None)
        super().__init__(*args, **kwargs)
        self.fields['item'].widget = forms.Select()
        if not self.instance.pk:
            self.fields['item'].queryset = ItemMemoriaCalculo.objects.filter(projeto=projeto)
        else:
            self.fields['item'].queryset = ItemMemoriaCalculo.objects.filter(pk=self.instance.item.id)
            del self.fields['clonar_operacao']

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if cleaned_data.get('clonar_operacao') and cleaned_data.get('clonar_operacao') > 12:
            self.add_error('clonar_operacao', 'O máximo permitido são 12 meses.')
        return cleaned_data


class UploadArquivoForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoAnexo
        fields = ('arquivo',)


class UploadAnexoAuxiliarForm(forms.ModelFormPlus):
    class Meta:
        model = EditalAnexoAuxiliar
        fields = ('arquivo',)


class UploadEditalForm(forms.ModelFormPlus):
    class Meta:
        model = Edital
        fields = ('arquivo',)


class RegistroGastoForm(forms.ModelFormPlus):
    arquivo = forms.FileFieldPlus(label='Nota Fiscal ou Cupom', required=False)
    cotacao_precos = forms.FileFieldPlus(
        label='Cotação de Preços', required=False, help_text='Envie um arquivo ZIP contendo as três propostas de cotação de preços deste item.'
    )

    class Meta:
        model = RegistroGasto
        exclude = (
            'item',
            'dt_avaliacao',
            'avaliador',
            'aprovado',
            'justificativa_reprovacao',
            'desembolso',
            'data_cadastro',
            'arquivo_termo_cessao',
            'obs_cessao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.dt_avaliacao:
            del self.fields['ano']
            del self.fields['mes']
            del self.fields['descricao']
            del self.fields['valor_unitario']
            del self.fields['observacao']
            del self.fields['qtd']


class RegistroExecucaoEtapaForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroExecucaoEtapa
        exclude = ('etapa', 'dt_avaliacao', 'avaliador', 'aprovado', 'info_ind_qualitativo', 'justificativa_reprovacao', 'data_cadastro_execucao')


class ValidacaoConclusaoProjetoForm(forms.FormPlus):
    aprovado = forms.BooleanField(required=False)
    obs = forms.CharField(widget=forms.Textarea(), label='Observação')

    def __init__(self, *args, **kwargs):
        registro = kwargs.pop('registro', None)
        super().__init__(*args, **kwargs)
        if registro.obs_avaliador:
            self.fields['obs'].initial = registro.obs_avaliador


class FotoProjetoForm(forms.ModelFormPlus):
    class Meta:
        model = FotoProjeto
        exclude = ('projeto',)


def AvaliacaoFormFactory(request, avaliacao, projeto, avaliador, vinculo):
    class AvaliacaoForm(forms.FormPlus):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            if avaliacao:
                for item in avaliacao.itemavaliacao_set.all():
                    nota_choices = []
                    maior_nota = (2 * item.criterio_avaliacao.pontuacao_maxima) + 1
                    notas = [x * 0.5 for x in range(int(maior_nota))]
                    notas.sort(reverse=True)
                    for nota in notas:
                        nota_choices.append([str(nota), str(nota)])

                    self.fields[str(item.criterio_avaliacao.pk)] = forms.ChoiceField(
                        choices=nota_choices,
                        label=item.criterio_avaliacao.descricao,
                        help_text=f'Pontuação Máxima: {format_(item.criterio_avaliacao.pontuacao_maxima)}',
                        initial=float(item.pontuacao),
                    )
            else:
                for criterio_avaliacao in projeto.edital.criterioavaliacao_set.all():
                    nota_choices = []
                    maior_nota = (2 * criterio_avaliacao.pontuacao_maxima) + 1
                    notas = [x * 0.5 for x in range(int(maior_nota))]
                    notas.sort(reverse=True)
                    for nota in notas:
                        nota_choices.append([str(nota), str(nota)])

                    self.fields[str(criterio_avaliacao.pk)] = forms.ChoiceField(
                        choices=nota_choices,
                        label=criterio_avaliacao.descricao,
                        help_text=f'Pontuação Máxima: {format_(criterio_avaliacao.pontuacao_maxima)}',
                    )

            self.fields['parecer'] = forms.CharField(
                label='Parecer', widget=forms.Textarea(), required=True, initial=avaliacao and avaliacao.parecer or None
            )
            self.avaliacao = avaliacao

        def clean(self, *args, **kwargs):
            cleaned_data = super().clean()
            if not self.errors:
                for criterio_avaliacao in projeto.edital.criterioavaliacao_set.all():
                    valor_pontuacao = Decimal(cleaned_data.get(str(criterio_avaliacao.pk)))
                    if valor_pontuacao > criterio_avaliacao.pontuacao_maxima:
                        self.errors[str(criterio_avaliacao.pk)] = ['Pontuação informada maior que a máxima permitida.']
                        del cleaned_data[str(criterio_avaliacao.pk)]
            return cleaned_data

        @transaction.atomic()
        def save(self):
            if not self.avaliacao:
                self.avaliacao = Avaliacao()
                self.avaliacao.projeto = projeto
                self.avaliacao.avaliador = avaliador
                self.avaliacao.vinculo = vinculo
                self.avaliacao.pontuacao = Decimal('0')
                self.avaliacao.save()
            for criterio_avaliacao in self.avaliacao.projeto.edital.criterioavaliacao_set.all():
                try:
                    item = ItemAvaliacao.objects.get(avaliacao=self.avaliacao, criterio_avaliacao=criterio_avaliacao)
                except Exception:
                    item = ItemAvaliacao()
                    item.avaliacao = self.avaliacao
                    item.criterio_avaliacao = criterio_avaliacao
                item.pontuacao = self.cleaned_data.get(str(criterio_avaliacao.id), 0)
                item.save()
            self.avaliacao.parecer = self.cleaned_data['parecer']
            self.avaliacao.save()

    return AvaliacaoForm(request.POST or None)


class CaracterizacaoBeneficiarioForm(forms.ModelFormPlus):
    quantidade = forms.IntegerFieldPlus(label='Quantidade Prevista de Pessoas a Atender', required=True)
    descricao_beneficiario = forms.CharField(label='Descreva os Beneficiários do Público-Alvo', required=False, widget=forms.Textarea())

    class Meta:
        model = CaracterizacaoBeneficiario
        exclude = ('projeto',)

    def __init__(self, *args, **kwargs):
        self.atendida = kwargs.pop('atendida', None)
        self.edicao_inscricao = kwargs.pop('edicao_inscricao', None)
        super().__init__(*args, **kwargs)
        tipos_cadastrados = self.instance.projeto.caracterizacaobeneficiario_set.values_list('tipo_beneficiario__id', flat=True)
        if self.instance.pk:
            tipos_cadastrados = tipos_cadastrados.exclude(tipo_beneficiario=self.instance.tipo_beneficiario)

        beneficiarios = TipoBeneficiario.objects.filter(ativo=True)
        self.fields['tipo_beneficiario'].queryset = beneficiarios.exclude(id__in=tipos_cadastrados)
        if self.atendida or not self.edicao_inscricao:
            del self.fields['quantidade']
            del self.fields['tipo_beneficiario']
        elif not self.instance.pk or self.edicao_inscricao:
            del self.fields['quantidade_atendida']
            del self.fields['descricao_beneficiario']

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if self.errors:
            return cleaned_data

        if not self.atendida and cleaned_data.get('quantidade') is not None and cleaned_data['quantidade'] <= 0:
            self.errors['quantidade'] = ['A quantidade deve ser maior que zero.']

        if (
            not self.atendida
            and self.edicao_inscricao
            and self.instance.projeto.caracterizacaobeneficiario_set.filter(tipo_beneficiario=cleaned_data['tipo_beneficiario'])
            .exclude(id=self.instance.pk)
            .exists()
        ):
            self.errors['tipo_beneficiario'] = ['O tipo de beneficiário já foi adicionado.']

        return cleaned_data


class ReprovarExecucaoEtapaForm(forms.FormPlus):
    obs = forms.CharField(widget=forms.Textarea(), label='Justificativa da Não Aprovação')


class ReprovarExecucaoGastoForm(forms.FormPlus):
    obs = forms.CharField(widget=forms.Textarea(), label='Justificativa da Não Aprovação')


class ProjetoHistoricoDeEnvioForm(forms.ModelFormPlus):
    class Meta:
        model = ProjetoHistoricoDeEnvio
        fields = ('parecer_devolucao',)


class LicaoAprendidaForm(forms.ModelFormPlus):
    class Meta:
        model = LicaoAprendida
        exclude = ('projeto',)


class RelatorioLicoesAprendidasForm(forms.FormPlus):
    METHOD = 'GET'

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    area = forms.ModelChoiceField(
        AreaLicaoAprendida.objects,
        required=False,
        label='Área de Conhecimento:',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
        if self.request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            # self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
            uos = CampusAdicional.get_campi_user(self.request.user, retornar_apenas_ids=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id__in=uos)


class EmailCoordenadoresForm(forms.FormPlus):
    PROJETOS_EM_EDICAO = 'Projetos em Edição'
    PROJETOS_ENVIADOS = 'Projetos Enviados'
    PROJETOS_PRE_SELECIONADOS = 'Projetos Pré-Selecionados'
    PROJETOS_EM_EXECUCAO = 'Projetos em Execução'
    PROJETOS_EM_ATRASO = 'Projetos em Atraso'
    PROJETOS_CONCLUIDOS = 'Projetos Concluídos'
    AVALIACAO_STATUS = (
        (PROJETOS_EM_EDICAO, PROJETOS_EM_EDICAO),
        (PROJETOS_ENVIADOS, PROJETOS_ENVIADOS),
        (PROJETOS_PRE_SELECIONADOS, PROJETOS_PRE_SELECIONADOS),
        (PROJETOS_EM_EXECUCAO, PROJETOS_EM_EXECUCAO),
        (PROJETOS_EM_ATRASO, PROJETOS_EM_ATRASO),
        (PROJETOS_CONCLUIDOS, PROJETOS_CONCLUIDOS),
    )

    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=True)
    situacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS,
        label='Filtrar por Situação',
        required=False,
    )

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.groups.filter(name__in=['Gerente Sistêmico de Projetos de Ensino', 'Coordenador de Projetos de Ensino']):
            self.fields['edital'].queryset = Edital.objects.all()

        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []

        if editais:
            ANO_CHOICES.append(['Selecione um ano', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            for ano in range(ano_limite, ano_inicio, -1):
                ANO_CHOICES.append([str(ano), str(ano)])
        else:
            ANO_CHOICES.append(['Selecione um ano', 'Nenhum edital cadastrado'])

        self.fields['ano'].choices = ANO_CHOICES


class EquipeProjetoForm(forms.FormPlus):
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )

    edital = forms.ModelChoiceField(
        queryset=Edital.objects.order_by('-inicio_inscricoes'), empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )
    METHOD = 'GET'
    TIPO_EXIBICAO = (
        (0, 'Detalhado'),
        (1, 'Simples'),
    )
    tipo_de_exibicao = forms.ChoiceField(choices=TIPO_EXIBICAO, label='Tipo de Exibição', required=False, initial=0)

    TIPO_SITUACAO = (
        (0, 'Todos'),
        (1, 'Concluído'),
        (2, 'Em execução'),
    )
    situacao = forms.ChoiceField(choices=TIPO_SITUACAO, label='Filtrar Projetos por Situação', required=False, initial=0)

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        participantes = Participacao.objects.filter(projeto__aprovado=True).values_list('vinculo_pessoa', flat=True)
        self.fields['pessoa'] = forms.ModelChoiceFieldPlus(Vinculo.objects.filter(id__in=set(participantes)), required=False)
        if not self.request.user.groups.filter(name__in=['Gerente Sistêmico de Projetos de Ensino', 'Visualizador de Projetos de Ensino']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)

        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []

        if editais:
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            for ano in range(ano_limite, ano_inicio, -1):
                ANO_CHOICES.append([str(ano), str(ano)])
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        self.fields['ano'].choices = ANO_CHOICES


class CancelarProjetoForm(forms.ModelFormPlus):
    justificativa_cancelamento = forms.CharField(widget=forms.Textarea(), label='Justificativa do Cancelamento')

    class Meta:
        model = ProjetoCancelado
        fields = [
            'justificativa_cancelamento',
        ]


class AvaliarCancelamentoProjetoForm(forms.ModelFormPlus):
    obs_avaliacao = forms.CharField(widget=forms.Textarea(), label='Parecer do Avaliador')
    cancelado = forms.BooleanField(label='Cancelar Projeto', required=False)
    aprova_proximo = forms.BooleanField(
        label='Aprovar Próximo Projeto',
        help_text="O primeiro projeto da lista de espera será aprovado automaticamente e o coordenador será notificado por email. Só terá efeito se a opção 'Cancelar Projeto' for selecionada.",
        required=False,
    )

    class Meta:
        model = ProjetoCancelado
        fields = [
            'obs_avaliacao',
            'cancelado',
        ]

    def __init__(self, *args, **kwargs):
        eh_continuo = kwargs.pop('eh_continuo', None)
        super().__init__(*args, **kwargs)
        self.fields['obs_avaliacao'].initial = self.instance.obs_avaliacao
        self.fields['cancelado'].initial = self.instance.cancelado
        if eh_continuo:
            self.fields['aprova_proximo'].widget = forms.HiddenInput()
        if self.instance.proximo_projeto:
            del self.fields['aprova_proximo']
        if self.instance.data_avaliacao:
            del self.fields['cancelado']


class IndicarPreAvaliadorForm(forms.FormPlus):
    METHOD = 'GET'
    AVALIACAO_STATUS = (
        (1, 'Projetos em conflito'),
        (2, 'Projetos sem monitor'),
        (0, 'Todos'),
    )
    palavra_chave = forms.CharField(label='Avaliador', required=False)
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.uo(), label='Campus', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    status_avaliacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS, label='Filtrar por Situação', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        if (
            self.request.user.groups.filter(name='Coordenador de Projetos de Ensino').exists()
            and not self.request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino').exists()
        ):
            # self.fields['uo'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
            self.fields['uo'].queryset = CampusAdicional.get_campi_user(self.request.user)


class SelecionarPreAvaliadorForm(forms.FormPlus):
    user = forms.ModelChoiceField(Vinculo.objects, required=True, label='Pré-Avaliador')

    def __init__(self, *args, **kwargs):
        campus = kwargs.pop('campus', None)
        super().__init__(*args, **kwargs)
        self.fields['user'].queryset = Vinculo.objects.filter(user__groups__name='Coordenador de Projetos de Ensino', setor__uo=campus)


class IndicarAvaliadoresForm(forms.FormPlus):
    avaliadores = forms.MultipleModelChoiceField(
        Vinculo.objects, required=False, label='Avaliadores', widget=RenderableSelectMultiple('widgets/vinculos_widget.html')
    )

    def __init__(self, *args, **kwargs):
        projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        membros_comissao = ComissaoEdital.objects.filter(edital=projeto.edital).values_list('vinculos_membros', flat=True)

        servidores_equipes = projeto.get_participacoes_servidores_ativos()
        ids_servidores = []
        for servidor in servidores_equipes:
            ids_servidores.append(servidor.vinculo_pessoa.id)

        lista_indicadores = Vinculo.objects.filter(id__in=membros_comissao).exclude(id__in=ids_servidores)
        if not projeto.edital.campus_especifico:
            ids_para_excluir = []
            for avaliador in lista_indicadores:
                if get_uo(avaliador.user) == projeto.uo:
                    ids_para_excluir.append(avaliador.id)
            lista_indicadores = lista_indicadores.exclude(id__in=ids_para_excluir)
        self.fields['avaliadores'].queryset = lista_indicadores.order_by('pessoa__nome_usual')

        self.fields['avaliadores'].initial = projeto.get_avaliadores().values_list('vinculo', flat=True)


class IndicarAvaliadorForm(forms.FormPlus):
    SUBMIT_LABEL = 'Buscar'
    AVALIACAO_STATUS = (
        (0, 'Todos'),
        (1, 'Projetos avaliados'),
        (2, 'Projetos não avaliados'),
        (3, 'Projetos parcialmente avaliados'),
        (4, 'Divergência >= 20 pontos entre avaliações'),
    )
    palavra_chave = forms.CharField(label='Avaliador', required=False)
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.uo(), label='Campus', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    status_avaliacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS, label='Situação da avaliação', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )


class ComissaoEditalForm(forms.ModelFormPlus):
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )

    edital = ModelChoiceField(queryset=Edital.objects, label='Filtrar por Edital:', required=True)

    clonar_comissao = forms.BooleanField(label='Clonar Comissão de um Edital anterior', initial=False, required=False)

    vinculos_membros = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Membro', required=False)

    clonar_comissao_edital = ModelChoiceField(queryset=Edital.objects.order_by('-id'), label='Clonar Comissão do Edital:', required=True)

    class Meta:
        model = ComissaoEdital
        fields = ('ano', 'edital', 'clonar_comissao', 'vinculos_membros', 'clonar_comissao_edital')

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['clonar_comissao_edital'].required = False

        if self.instance.pk:
            self.fields['clonar_comissao_edital'].widget = forms.HiddenInput()
            self.fields['clonar_comissao'].widget = forms.HiddenInput()

        internos = Servidor.objects.ativos().values_list('id', flat=True)
        externos = AvaliadorExterno.objects.all().values_list('vinculo', flat=True)

        queryset = Vinculo.objects.filter(Q(id_relacionamento__in=internos, tipo_relacionamento__model='servidor') | Q(id__in=externos))
        self.fields['vinculos_membros'].queryset = queryset.order_by('pessoa__nome')

        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        if not self.request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            self.fields['edital'].queryset = Edital.objects.filter(
                id__in=OfertaProjeto.objects.filter(uo=get_uo(self.request.user)).values_list('edital', flat=True)
            )
            editais = editais.filter(id__in=OfertaProjeto.objects.filter(uo=get_uo(self.request.user)).values_list('edital', flat=True))
        ANO_CHOICES = []

        if editais:
            ANO_CHOICES.append(['Selecione um ano', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            for ano in range(ano_limite, ano_inicio, -1):
                ANO_CHOICES.append([str(ano), str(ano)])
        else:
            ANO_CHOICES.append(['Selecione um ano', 'Nenhum edital cadastrado'])

        self.fields['ano'].choices = ANO_CHOICES

    def clean(self):
        cleaned_data = super().clean()
        if not self.instance.pk:
            if not self.cleaned_data.get('edital'):
                raise forms.ValidationError('Selecione um edital.')

            if ComissaoEdital.objects.filter(edital=self.cleaned_data['edital']).exists():
                raise forms.ValidationError('Já existe uma comissão cadastrada para este edital.')

            if not self.cleaned_data.get('vinculos_membros') and not self.cleaned_data.get('clonar_comissao_edital'):
                raise forms.ValidationError('Informe os membros da comissão ou selecione um edital para clonar a comissão de avaliação.')

            if self.cleaned_data.get('clonar_comissao_edital'):
                if (
                    self.cleaned_data.get('uo')
                    and not ComissaoEdital.objects.filter(
                        edital=self.cleaned_data.get('clonar_comissao_edital'), uo=self.cleaned_data.get('uo')
                    ).exists()
                ):
                    self.add_error('clonar_comissao_edital', 'Não existe comissão para o edital e campus selecionados.')
                if not ComissaoEdital.objects.filter(edital=self.cleaned_data.get('clonar_comissao_edital')).exists():
                    self.add_error('clonar_comissao_edital', 'Não existe comissão para o edital selecionado.')

        return cleaned_data

    @transaction.atomic
    def save(self, commit=True):
        comissao = super().save(False)
        comissao.save()

        if self.cleaned_data.get('clonar_comissao_edital'):
            del self.cleaned_data['vinculos_membros']
            if self.cleaned_data.get('uo'):
                comissao_clonada = ComissaoEdital.objects.filter(
                    edital=self.cleaned_data.get('clonar_comissao_edital'), uo=self.cleaned_data.get('uo')
                )
            else:
                comissao_clonada = ComissaoEdital.objects.filter(edital=self.cleaned_data.get('clonar_comissao_edital'))

            for item in comissao_clonada[0].vinculos_membros.all():
                comissao.vinculos_membros.add(item)

        return comissao


class RecursoProjetoForm(forms.ModelFormPlus):
    justificativa = forms.CharField(widget=forms.Textarea(), label='Justificativa do Recurso')

    class Meta:
        model = RecursoProjeto
        fields = [
            'justificativa',
        ]


class AvaliarRecursoProjetoForm(forms.ModelFormPlus):
    parecer = forms.CharField(widget=forms.Textarea(), label='Parecer do Avaliador')
    aceito = forms.BooleanField(label='Aceitar Recurso', required=False)

    class Meta:
        model = RecursoProjeto
        fields = [
            'parecer',
            'aceito',
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parecer'].initial = self.instance.parecer


class EditaisForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )
    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])
        self.fields['ano'].choices = ANO_CHOICES
        if not self.request.user.groups.filter(name='Gerente Sistêmico de Projetos de Ensino'):
            ids = OfertaProjeto.objects.filter(uo=get_uo(self.request.user))
            self.fields['edital'].queryset = editais.filter(campus_especifico=True, id__in=ids.values_list('edital', flat=True))

        if self.ano:
            self.fields['edital'].queryset = editais.filter(inicio_inscricoes__year=self.ano)


class AnexosDiversosProjetoForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Descrição', required=True)
    vinculo_membro_equipe = forms.ModelChoiceField(Vinculo.objects, required=False, label='Membro da Equipe')
    arquivo = forms.FileFieldPlus(label='Arquivo')

    class Meta:
        model = ProjetoAnexo
        fields = ['descricao', 'vinculo_membro_equipe', 'arquivo']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.participacao = kwargs.pop('participacao', None)
        super().__init__(*args, **kwargs)
        self.equipe = self.projeto.participacao_set.all()
        self.fields['vinculo_membro_equipe'].queryset = Vinculo.objects.filter(id__in=self.equipe.values_list('vinculo_pessoa', flat=True))
        if self.participacao:
            self.fields['vinculo_membro_equipe'].queryset = Vinculo.objects.filter(id=self.participacao.vinculo_pessoa.id)
            self.fields['descricao'].initial = f'Termo de Desligamento - {self.participacao.get_nome()}'
            self.fields['descricao'].widget.attrs['readonly'] = True


class PrestacaoContaForm(forms.FormPlus):
    TIPO_RELATORIO = (
        (1, 'Parcial'),
        (2, 'Final'),
    )
    tipo_relatorio = forms.ChoiceField(
        choices=TIPO_RELATORIO, label='Tipo do Relatório', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    despesa = forms.ModelChoiceField(
        queryset=NaturezaDespesa.objects,
        label='Elemento de Despesa',
        required=False,
    )
    ano_relatorio = forms.ModelChoiceField(
        queryset=Ano.objects,
        label='Ano',
        required=False,
    )

    mes_relatorio = forms.ChoiceField(
        choices=[
            [1, 'Janeiro'],
            [2, 'Fevereiro'],
            [3, 'Março'],
            [4, 'Abril'],
            [5, 'Maio'],
            [6, 'Junho'],
            [7, 'Julho'],
            [8, 'Agosto'],
            [9, 'Setembro'],
            [10, 'Outubro'],
            [11, 'Novembro'],
            [12, 'Dezembro'],
        ],
        label='Mês',
        required=False,
    )
    METHOD = 'GET'

    class Media:
        js = ['/static/projetos_ensino/js/prestacaocontaform.js']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        anos = Ano.objects.filter(id__in=RegistroGasto.objects.filter(desembolso__projeto=self.projeto).values_list('ano', flat=True))
        self.fields['ano_relatorio'].queryset = anos
        self.fields['ano_relatorio'].initial = anos[0].id
        self.fields['despesa'].queryset = NaturezaDespesa.objects.filter(
            id__in=RegistroGasto.objects.filter(desembolso__projeto=self.projeto).values_list('desembolso__despesa', flat=True)
        )

    def clean(self) -> dict:
        cleaned_data = self.cleaned_data
        if cleaned_data.get('tipo_relatorio') == '1':
            if not cleaned_data.get('ano_relatorio'):
                self.add_error('ano_relatorio', 'Selecione o ano.')
            if not cleaned_data.get('mes_relatorio'):
                self.add_error('mes_relatorio', 'Selecione o mês.')
        return cleaned_data


class TermoCessaoForm(forms.FormPlus):
    registro = forms.ModelChoiceField(
        queryset=RegistroGasto.objects,
        label='Registro de Gasto',
        required=True,
        help_text='Apenas registros de gastos com material permanente podem ser associados ao termo de cessão/doação.',
    )

    arquivo = forms.FileField()

    obs = forms.CharField(widget=forms.Textarea(), label='Observação', required=False)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['registro'].queryset = RegistroGasto.objects.filter(
            Q(desembolso__projeto=self.projeto),
            Q(desembolso__despesa__codigo='449052'),
            Q(arquivo_termo_cessao='') | Q(arquivo_termo_cessao__isnull=True),
        )


class EditarProjetoEmExecucaoForm(forms.ModelFormPlus):
    justificativa_alteracoes = forms.CharField(
        label='Justificativa da Alteração de Datas',
        required=False,
        widget=forms.Textarea(),
        help_text='Caso haja alteração nas datas, informe a justificativa. Até 5000 caracteres.',
        max_length=5000,
    )

    class Meta:
        model = Projeto
        fields = ['inicio_execucao', 'fim_execucao']

    def clean(self):
        cleaned_data = super().clean()
        if self.cleaned_data.get('inicio_execucao') and self.cleaned_data.get('fim_execucao'):
            if (
                self.cleaned_data.get('inicio_execucao') != self.instance.inicio_execucao
                or self.cleaned_data.get('fim_execucao') != self.instance.fim_execucao
            ):
                if not self.cleaned_data.get('justificativa_alteracoes'):
                    raise forms.ValidationError('Informe a justificativa para alteração na(s) data(s).')

        return cleaned_data


class AlteraNotaCriterioProjetoForm(forms.ModelFormPlus):
    exibe_pontuacao = forms.DecimalField(label='Pontuação Original', required=False)

    fieldsets = ((None, {'fields': ('exibe_pontuacao', 'nova_pontuacao', 'recurso')}),)

    class Meta:
        model = ItemAvaliacao
        fields = ['recurso']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nota_choices = []
        maior_nota = (2 * self.instance.criterio_avaliacao.pontuacao_maxima) + 1
        notas = [x * 0.5 for x in range(int(maior_nota))]
        notas.sort(reverse=True)
        for nota in notas:
            nota_choices.append([str(nota), str(nota)])
        self.fields['nova_pontuacao'] = forms.ChoiceField(choices=nota_choices, label='Nova Pontuação', required=True)
        self.fields['exibe_pontuacao'].widget.attrs['readonly'] = True


class DataInativacaoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data de Inativação', required=True)
    justificativa = forms.CharField(label='Justificativa', required=True, widget=forms.Textarea(), max_length=1000)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.participacao = kwargs.pop('participacao', None)
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned_data = super().clean()
        data_informada = self.cleaned_data.get('data')
        if data_informada and data_informada > self.projeto.fim_execucao:
            raise forms.ValidationError('A data de inativação não pode ser após o fim do projeto.')
        if data_informada:
            historicos = HistoricoEquipe.objects.filter(projeto=self.projeto, participante=self.participacao).order_by('-id')
            if historicos.exists():
                ultimo_historico = historicos[0]
                if ultimo_historico.data_movimentacao > self.cleaned_data.get('data'):
                    raise forms.ValidationError('A data de inativação não pode ser menor do que a data de início do vínculo atual.')
        return cleaned_data


class ProjetosAtrasadosForm(forms.FormPlus):
    SITUACAO_STATUS = (
        (1, 'Projetos em Atraso'),
        (2, 'Projetos com Atividades Atrasadas'),
        (3, 'Projetos em dia'),
        (0, 'Todos'),
    )
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    situacao = forms.ChoiceField(choices=SITUACAO_STATUS, label='Filtrar por Situação', required=False)

    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES
        if not self.request.user.has_perm('projetos_ensino.pode_gerenciar_edital'):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']


class ListaAvaliadoresProjetosForm(forms.FormPlus):
    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)
    METHOD = 'GET'


class CriterioAvaliacaoAlunoForm(forms.ModelFormPlus):
    consideracoes_coordenador = forms.CharField(widget=forms.Textarea(), label='Considerações do Avaliador')
    fieldsets = (('Dados da Avaliação', {'fields': ('tipo_avaliacao',)}),)

    class Meta:
        model = AvaliacaoAluno
        fields = ('tipo_avaliacao', 'consideracoes_coordenador')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        nome_campos = ''
        for i in CriterioAvaliacaoAluno.objects.filter(ativo=True):
            label = f'{i.nome}'
            self.fields[str(i.id)] = forms.ChoiceField(
                label=label, help_text=i.descricao_criterio, required=False, choices=ItemAvaliacaoAluno.PONTUACAOAVALIACAO_CHOICES
            )
            nome_campos = nome_campos + f'{i.id}, '

        self.fieldsets = (*self.fieldsets, ('Critérios de Avaliação', {'fields': nome_campos}))

        self.fieldsets = (*self.fieldsets, ('Considerações do Avaliador', {'fields': ('consideracoes_coordenador',)}))


class ValidarAvaliacaoAlunoForm(forms.ModelFormPlus):
    consideracoes_aluno = forms.CharField(widget=forms.Textarea(), label='Considerações do Aluno', required=False)

    class Meta:
        model = AvaliacaoAluno
        fields = ('consideracoes_aluno',)


class EditarTermoCessaoForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroGasto
        fields = (
            'arquivo_termo_cessao',
            'obs_cessao',
        )


class AnoForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Ano:',
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['Selecione um ano', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['Selecione um ano', 'Nenhum edital cadastrado'])
        self.fields['ano'].choices = ANO_CHOICES


class MeusProjetosForm(forms.FormPlus):
    METHOD = 'GET'

    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )
    TODOS = 'Todos'
    PROJETOS_EM_EDICAO = 'Projetos em Edição'
    PROJETOS_ENVIADOS = 'Projetos Enviados'
    PROJETOS_PRE_SELECIONADOS = 'Projetos Pré-Selecionados'
    PROJETOS_EM_EXECUCAO = 'Projetos em Execução'
    PROJETOS_ENCERRADOS = 'Projetos Encerrados'
    PROJETOS_CANCELADOS = 'Projetos Cancelados'

    AVALIACAO_STATUS = (
        (TODOS, TODOS),
        (PROJETOS_EM_EDICAO, PROJETOS_EM_EDICAO),
        (PROJETOS_ENVIADOS, PROJETOS_ENVIADOS),
        (PROJETOS_PRE_SELECIONADOS, PROJETOS_PRE_SELECIONADOS),
        (PROJETOS_EM_EXECUCAO, PROJETOS_EM_EXECUCAO),
        (PROJETOS_ENCERRADOS, PROJETOS_ENCERRADOS),
        (PROJETOS_CANCELADOS, PROJETOS_CANCELADOS),
    )
    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    situacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS,
        label='Filtrar por Situação',
        required=False,
    )

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES


class SolicitoesCancelamentoForm(forms.FormPlus):
    METHOD = 'GET'

    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Filtrar por Ano:',
    )
    AVALIACAO_STATUS = (
        ('Projetos em Edição', 'Projetos em Edição'),
        ('Projetos Enviados', 'Projetos Enviados'),
        ('Projetos Pré-Selecionados', 'Projetos Pré-Selecionados'),
        ('Projetos em Execução', 'Projetos em Execução'),
    )
    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES


class IndicarOrientadorForm(forms.FormPlus):
    participacao = forms.ModelChoiceField(Participacao.objects, label='Novo Orientador', required=True)
    data_inicio = forms.DateFieldPlus(label='Início da Orientação', required=True)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.participacao = kwargs.pop('participacao', None)
        super().__init__(*args, **kwargs)
        qs_participacoes = self.projeto.participacao_set.filter(ativo=True)
        servidores_ids = []
        for p in qs_participacoes:
            if p.is_servidor():
                servidores_ids.append(p.vinculo_pessoa.id)
        possiveis_orientadores = self.projeto.participacao_set.filter(ativo=True, vinculo_pessoa__in=servidores_ids)
        if self.participacao.orientador:
            possiveis_orientadores = possiveis_orientadores.exclude(id=self.participacao.orientador.id)
        self.fields['participacao'].queryset = possiveis_orientadores

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if self.cleaned_data.get('data_inicio'):
            if self.cleaned_data.get('data_inicio') < self.projeto.inicio_execucao:
                raise forms.ValidationError('O início da orientação não pode ser anterior ao início do projeto.')
            elif self.cleaned_data.get('data_inicio') > self.projeto.fim_execucao:
                raise forms.ValidationError('O início da orientação não pode ser posterior ao término do projeto.')

            if HistoricoOrientacaoProjeto.objects.filter(projeto=self.projeto, orientado=self.participacao, data_termino__isnull=True).exists():
                orientacao_atual = HistoricoOrientacaoProjeto.objects.filter(orientado=self.participacao, data_termino__isnull=True)[0]

                if self.cleaned_data.get('data_inicio') < orientacao_atual.data_inicio:
                    raise forms.ValidationError(
                        'O início da nova orientação não pode ser anterior ao início da orientação atual ({}).'.format(
                            orientacao_atual.data_inicio.strftime('%d/%m/%y')
                        )
                    )

            if HistoricoOrientacaoProjeto.objects.filter(projeto=self.projeto, orientado=self.participacao, data_termino__isnull=False).exists():
                ultima = HistoricoOrientacaoProjeto.objects.filter(
                    projeto=self.projeto, orientado=self.participacao, data_termino__isnull=False
                ).order_by('-id')[0]
                if self.cleaned_data.get('data_inicio') < ultima.data_termino:
                    raise forms.ValidationError(
                        'Não é possível cadastrar uma orientação anterior à última orientação cadastrada ({}).'.format(
                            ultima.data_termino.strftime('%d/%m/%y')
                        )
                    )

            if HistoricoEquipe.objects.filter(participante=self.participacao).exists():
                entrada_aluno = HistoricoEquipe.objects.filter(participante=self.participacao).order_by('id')[0].data_movimentacao
                if self.cleaned_data.get('data_inicio') < entrada_aluno:
                    raise forms.ValidationError(
                        'O início da orientação não pode ser anterior a data de início da participação do discente no projeto ({}).'.format(
                            entrada_aluno.strftime('%d/%m/%y')
                        )
                    )

            if self.cleaned_data.get('participacao') and HistoricoEquipe.objects.filter(participante=self.cleaned_data.get('participacao')).exists():
                entrada_orientador = (
                    HistoricoEquipe.objects.filter(participante=self.cleaned_data.get('participacao')).order_by('id')[0].data_movimentacao
                )
                if self.cleaned_data.get('data_inicio') < entrada_orientador:
                    raise forms.ValidationError(
                        'O início da orientação não pode ser anterior a data de início da participação do orientador no projeto ({}).'.format(
                            entrada_orientador.strftime('%d/%m/%y')
                        )
                    )

        return cleaned_data


class PreAvaliacaoForm(forms.FormPlus):
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    eixo_tematico = forms.ModelChoiceField(
        EixoTematico.objects,
        required=False,
        label='Eixo Temático:',
    )
    pendentes = forms.BooleanField(label='Apenas pendentes de avaliação', required=False)

    def __init__(self, *args, **kwargs):
        self.nao_eh_sistemico = kwargs.pop('nao_eh_sistemico', None)
        super().__init__(*args, **kwargs)
        if self.nao_eh_sistemico:
            # self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
            uos = CampusAdicional.get_campi_user(self.request.user, retornar_apenas_ids=True)
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id__in=uos)


class EstatisticasForm(forms.FormPlus):
    METHOD = 'GET'

    campus = forms.ModelChoiceField(queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Campus:', required=False)

    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Ano:',
    )

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    tipo_edital = forms.ChoiceField(
        label='Tipo do Edital',
        choices=[('Todos', 'Todos'), ('Edital de Campus', 'Edital de Campus'), ('Edital Sistêmico', 'Edital Sistêmico')],
        required=False,
    )

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES
        if not self.request.user.has_perm('projetos.add_edital'):
            del self.fields['campus']


class InativarProjetoForm(forms.ModelFormPlus):
    motivo_inativacao = forms.CharFieldPlus(label='Motivo da Inativação', widget=forms.Textarea())

    class Meta:
        model = Projeto
        fields = ('motivo_inativacao',)


class ClonarProjetoForm(forms.FormPlus):
    edital = forms.ModelChoiceField(Edital.objects, required=False, label='Filtrar por Edital')
    clona_caracterizacao = forms.BooleanField(label='Caracterização de Beneficiários', initial=True, required=False)
    clona_equipe = forms.BooleanField(label='Equipe', initial=True, required=False)
    clona_atividade = forms.BooleanField(label='Metas/Atividades', initial=True, required=False)
    clona_memoria_calculo = forms.BooleanField(label='Memória de Cálculo', initial=True, required=False)
    clona_desembolso = forms.BooleanField(label='Desembolso', initial=True, required=False)
    data_inicio = forms.DateFieldPlus(label='Data de Início')
    data_fim = forms.DateFieldPlus(label='Data de Término')

    fieldsets = (
        (
            'Selecione o Projeto a Ser Clonado',
            {
                'fields': (
                    'edital',
                    'projeto',
                )
            },
        ),
        (
            'Selecione os Dados a Serem Clonados',
            {'fields': ('clona_caracterizacao', 'clona_equipe', 'clona_atividade', 'clona_memoria_calculo', 'clona_desembolso')},
        ),
        (
            'Informe o Período do Novo Projeto',
            {
                'fields': (
                    (
                        'data_inicio',
                        'data_fim',
                    ),
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        self.request = kwargs.pop('request', None)
        super().__init__(*args, **kwargs)
        projetos = Projeto.objects.filter(
            id__in=Participacao.objects.filter(vinculo_pessoa=self.request.user.get_vinculo(), responsavel=True).values_list('projeto', flat=True)
        )

        self.fields['projeto'] = forms.ChainedModelChoiceField(
            projetos, label='Projeto:', empty_label='Selecione o Edital', required=True, obj_label='titulo', form_filters=[('edital', 'edital')]
        )
        self.fields['edital'].queryset = Edital.objects.filter(id__in=projetos.values_list('edital', flat=True))

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if cleaned_data.get('clona_desembolso') and not cleaned_data.get('clona_memoria_calculo'):
            self.add_error('clona_desembolso', 'Não é possível clonar os desembolsos sem clonar a memória de cálculo.')

    def processar(self):
        return self.cleaned_data.get('projeto').clonar_projeto(
            edital=self.edital,
            clona_caracterizacao=self.cleaned_data.get('clona_caracterizacao'),
            clona_equipe=self.cleaned_data.get('clona_equipe'),
            clona_atividade=self.cleaned_data.get('clona_atividade'),
            clona_memoria_calculo=self.cleaned_data.get('clona_memoria_calculo'),
            clona_desembolso=self.cleaned_data.get('clona_desembolso'),
            data_inicio=self.cleaned_data.get('data_inicio'),
            data_fim=self.cleaned_data.get('data_fim'),
        )


class ClonarEtapaForm(forms.FormPlus):
    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['meta'] = forms.ModelChoiceField(Meta.objects.filter(projeto=self.projeto).order_by('ordem'), label='Selecione a Meta')
        self.fields['etapa'] = forms.ChainedModelChoiceField(
            Etapa.objects.filter(meta__projeto=self.projeto).order_by('ordem'),
            label='Selecione a Atividade:',
            empty_label='Selecione a meta',
            required=True,
            obj_label='descricao',
            form_filters=[('meta', 'meta')],
        )


class EditarHistoricoEquipeForm(forms.ModelFormPlus):
    class Meta:
        model = HistoricoEquipe
        fields = ('data_movimentacao', 'data_movimentacao_saida', 'vinculo', 'carga_horaria', 'obs')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_movimentacao'].label = 'Data de Início'
        self.fields['data_movimentacao_saida'].label = 'Data de Término'
        self.fields['obs'].label = 'Observações'
        self.fields['vinculo'].label = 'Bolsista'
        self.fields['obs'].required = False


class RelatorioCaracterizacaoBeneficiariosForm(forms.FormPlus):
    METHOD = 'GET'
    PROJETOS_EM_EXECUCAO = 'Projetos em Execução'
    PROJETOS_CONCLUIDOS = 'Projetos Concluídos'
    AVALIACAO_STATUS = (
        ('', 'Todos'),
        (PROJETOS_EM_EXECUCAO, PROJETOS_EM_EXECUCAO),
        (PROJETOS_CONCLUIDOS, PROJETOS_CONCLUIDOS),
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    tipo_edital = forms.ChoiceField(
        label='Tipo do Edital',
        choices=[('Todos', 'Todos'), ('Edital de Campus', 'Edital de Campus'), ('Edital Sistêmico', 'Edital Sistêmico')],
        required=False,
    )

    situacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS,
        label='Filtrar por Situação',
        required=False,
    )

    tipo_beneficiario = forms.ModelChoiceField(queryset=TipoBeneficiario.objects, label='Tipo de beneficiário', required=False)

    class Media:
        js = ['/static/projetos_ensino/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['', 'Nenhum edital cadastrado'])

        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)
        self.fields['ano'].choices = ANO_CHOICES

        if self.request.user.groups.filter(name__in=['Visualizador de Projetos de Ensino']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
        if self.request.user.groups.filter(name__in=['Coordenador de Projetos de Ensino']):
            # self.fields['campus'].queryset = UnidadeOrganizacional.objects.filter(id=get_uo(self.request.user).id)
            self.fields['campus'].queryset = CampusAdicional.get_campi_user(self.request.user)


class ListaEditaisForm(forms.FormPlus):
    METHOD = 'GET'
    INSCRICAO = 'Em Inscrição'
    PRE_SELECAO = 'Em Pré-Seleção'
    SELECAO = 'Em Seleção'
    EXECUCAO = 'Em Execução'
    CONCLUIDO = 'Concluído'
    ano = forms.ChoiceField(
        choices=[],
        required=False,
        label='Ano',
    )
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False, empty_label='Todos')
    periodo = forms.ChoiceField(
        label='Período',
        required=False,
        choices=[('', 'Todos'), (INSCRICAO, INSCRICAO), (PRE_SELECAO, PRE_SELECAO), (SELECAO, SELECAO), (EXECUCAO, EXECUCAO), (CONCLUIDO, CONCLUIDO)],
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        ano_limite = datetime.date.today().year
        editais = Edital.objects.all().order_by('inicio_inscricoes')
        ANO_CHOICES = []
        if editais.exists():
            ANO_CHOICES.append(['Selecione um ano', 'Selecione um ano'])
            ano_inicio = editais[0].inicio_inscricoes.year - 1
            ANO_CHOICES += [(ano, str(ano)) for ano in range(ano_limite, ano_inicio, -1)]
        else:
            ANO_CHOICES.append(['Selecione um ano', 'Nenhum edital cadastrado'])
        self.fields['ano'].choices = ANO_CHOICES


class ComissaoAcompanhamentoForm(forms.ModelFormPlus):
    class Meta:
        model = ComissaoAcompanhamento
        fields = ('uo', 'coordenador', 'membros')

    @transaction.atomic
    def save(self, commit=True):
        comissao = super().save(False)
        comissao.save()
        grupo = Group.objects.get(name='Integrante da Comissão de Acompanhamento')
        self.cleaned_data.get('coordenador').user.groups.add(grupo)
        usuarios = UsuarioGrupo.objects.filter(group=grupo).exclude(user_id=self.cleaned_data.get('coordenador').user.id)
        for membro in self.cleaned_data.get('membros'):
            membro.user.groups.add(grupo)
            usuarios = usuarios.exclude(user_id=membro.user.id)
        for usuario in usuarios:
            vinculo = usuario.user.get_vinculo()
            if (
                not ComissaoAcompanhamento.objects.filter(coordenador_id=vinculo.id).exclude(id=self.instance.id).exists()
                and not ComissaoAcompanhamento.objects.filter(membros=vinculo.id).exclude(id=self.instance.id).exists()
            ):
                usuario.user.groups.remove(grupo)
        return comissao


class ColaboradorExternoForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF', required=False)
    passaporte = forms.CharField(label='Nº do Passaporte', required=False, help_text='Esse campo é obrigatório para estrangeiros. Ex: BR123456')
    nacionalidade = forms.ChoiceField(label='Nacionalidade', choices=Nacionalidade.get_choices(), required=True)
    pais_origem = forms.ModelChoiceFieldPlus(queryset=Pais.objects, label='País de Origem', required=False)
    telefone = forms.BrTelefoneField(max_length=45, label='Telefone para Contato')
    lattes = forms.URLField(label='Lattes', help_text='Endereço do Currículo Lattes', required=False)

    class Meta:
        model = ColaboradorExterno
        exclude = ('ativo', 'prestador', 'eh_aposentado', 'eh_vinculado_nucleo_arte')

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self.fields['email'].help_text = 'Informe um email diferente do institucional.'
        if self.instance and self.instance.pk:
            self.fields['nacionalidade'].initial = self.instance.prestador.pessoa_fisica.nacionalidade
            self.fields['pais_origem'].initial = self.instance.prestador.pessoa_fisica.pais_origem
            travar_documentos_na_edicao(self, self.instance.prestador.pessoa_fisica)

    def clean(self) -> dict:
        if (
            self.cleaned_data.get('email')
            and not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario')
            and Configuracao.eh_email_institucional(self.cleaned_data.get('email'))
        ):
            self.add_error('email', 'Escolha um e-mail que não seja institucional.')
        nacionalidade = self.cleaned_data.get('nacionalidade')
        cpf = self.cleaned_data.get('cpf')
        pais_origem = self.cleaned_data.get('pais_origem')
        passaporte = self.cleaned_data.get('passaporte')
        try:
            eh_estrangeiro = int(nacionalidade) == Nacionalidade.ESTRANGEIRO
        except Exception:
            eh_estrangeiro = False
        if not cpf and not eh_estrangeiro:
            self.add_error('cpf', 'O campo CPF é obrigatório para nacionalidade Brasileira.')

        if eh_estrangeiro and not pais_origem:
            self.add_error('pais_origem', 'O campo de país de origem é obrigatório para estrangeiros.')

        recusar_passaporte_de_outra_pessoa(self, cpf, passaporte, pais_origem)
        if eh_estrangeiro and not cpf:
            self._validar_passaporte_sem_cpf(passaporte, pais_origem)
            username = PrestadorServico.matricula_do_passaporte(passaporte, pais_origem)
        else:
            username = PrestadorServico.gerar_matricula(cpf)
        qs = PrestadorServico.objects.filter(matricula=username)
        if self.instance.pk:
            qs = qs.exclude(id=self.instance.prestador.id)
        prestador_existente = qs.exists()
        if prestador_existente:
            prestador = qs[0]
            if ColaboradorExterno.objects.filter(prestador=prestador).exists():
                self.add_error('nome', 'Este usuário já foi cadastrado como colaborador externo.')
        recusar_cadastro_de_prestador(self)  # antes do super().clean(), que levanta se já houver erro de campo
        return super().clean()

    def _validar_passaporte_sem_cpf(self, passaporte: str | None, pais: Pais | None) -> None:
        """Estrangeiro sem CPF: o passaporte, com o país, é o documento e a matrícula.

        Fica no ``clean()``: no ``clean_passaporte`` a nacionalidade ainda não foi validada.
        """
        if not passaporte:
            self.add_error('passaporte', 'Informe o passaporte.')

    @transaction.atomic
    def save(self, commit=True):
        email = self.cleaned_data['email']
        nacionalidade = int(self.cleaned_data['nacionalidade'] or 1)
        cpf = self.cleaned_data['cpf'] or ''
        passaporte = self.cleaned_data['passaporte'] or ''

        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': cpf,
            'nacionalidade': nacionalidade,
            'passaporte': passaporte,
            'nome_registro': self.cleaned_data['nome'],
            'email_secundario': self.cleaned_data['email'],
            'email': self.cleaned_data['email'],
            'pais_origem': self.cleaned_data['pais_origem'],
        }
        telefone: PessoaTelefoneCadastro = {
            'numero': self.cleaned_data['telefone'],
        }
        dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'setor': get_setor_proen(), 'ativo': True, 'telefone': telefone}
        if nacionalidade == Nacionalidade.ESTRANGEIRO and not cpf:
            matricula = PrestadorServico.matricula_do_passaporte(passaporte, self.cleaned_data['pais_origem'])
        else:
            matricula = PrestadorServico.gerar_matricula(cpf)
        prestador = PrestadorServico.objects.filter(matricula=matricula).first()
        if not prestador:
            prestador = PrestadorServico.update_or_create(dados)['prestador']

        avaliador = super().save(False)

        avaliador.prestador = prestador
        avaliador.email = email
        avaliador.save()

        return avaliador


class ConfiguracaoForm(forms.FormPlus):
    setor_proen = forms.ModelChoiceFieldPlus(
        Setor.objects,
        label='Setor da Pró-Reitoria',
        required=False,
        help_text='Os avaliadores externos de projetos de ensino serão vinculados automaticamente à este setor',
    )
    nome_proen = forms.CharFieldPlus(
        label='Nome da Pró-Reitoria', required=False, help_text='Este nome será exibido nos relatórios gerados no módulo de ensino'
    )


class ParticipacaoColaboradorForm(forms.ModelFormPlus):
    vinculo = forms.ChoiceField(label='Bolsista', required=True, choices=TipoVinculo.TIPOS)
    prestador = forms.ModelChoiceField(
        queryset=ColaboradorExterno.objects.filter(ativo=True),
        widget=AutocompleteWidget(
            search_fields=['nome', 'prestador__pessoa_fisica__cpf', 'prestador__pessoa_fisica__passaporte'],
            extraParams={'ext_combo_template': ext_combo_template_colaborador},
        ),
        label='Participante',
        required=True,
        help_text='O Colaborador precisa ser cadastrado previamente pelo Diretor Acadêmico ou pela Comissão de Acompanhamento.',
    )

    data = forms.DateFieldPlus(label='Data de Entrada', help_text='A data não pode ser maior do que hoje.')

    class Meta:
        model = Participacao
        fields = ('vinculo', 'carga_horaria', 'prestador', 'data')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)

        if self.instance.pk:
            self.fields.pop('prestador')
            self.historico = HistoricoEquipe.objects.filter(participante=self.instance, projeto=self.instance.projeto).order_by('id')
            self.fields['data'].initial = self.historico[0].data_movimentacao

    def clean(self):
        if self.instance.pk:
            instance = self.instance.projeto
            if self.historico.exists():
                if (
                    self.cleaned_data.get('data')
                    and self.historico.order_by('-id')[0].data_movimentacao_saida
                    and self.cleaned_data.get('data') > self.historico.order_by('-id')[0].data_movimentacao_saida
                ):
                    raise forms.ValidationError(
                        'A data informada é maior do que a data de término do vínculo mais recente do participante, não é possível inserir/editar colaborador.'
                    )
        else:
            instance = self.projeto
        if self.cleaned_data.get('data') and self.cleaned_data.get('data') > instance.fim_execucao:
            raise forms.ValidationError('A data informada é maior do que a data de término do projeto, não é possível inserir/editar colaborador.')
        if self.cleaned_data.get('data') and self.cleaned_data.get('data') < instance.inicio_execucao:
            raise forms.ValidationError('A data informada é anterior a data de início do projeto, não é possível inserir/editar colaborador.')

        if instance.fim_execucao < datetime.date.today():
            raise forms.ValidationError('Data término da execução do projeto é maior que a data atual, não é possível inserir/editar colaborador.')

        return self.cleaned_data


class RegistrarFrequenciaForm(forms.ModelFormPlus):
    data_fim = forms.DateFieldPlus(
        label='Até o dia', help_text='Caso este campo seja preenchido, será gerado um registro para cada dia do período informado.', required=False
    )

    class Meta:
        model = RegistroFrequencia
        fields = ('descricao', 'data', 'data_fim', 'carga_horaria')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].widget = forms.Textarea()
        self.fields['carga_horaria'].help_text = 'Informe a carga horária diária.'
        self.fields['carga_horaria'].label = 'Carga Horária Diária'

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()

        if self.cleaned_data.get('data') and self.cleaned_data.get('data').year < (datetime.date.today().year - 2):
            self.add_error('data', 'A data inicial não pode ser tão antiga.')

        if self.cleaned_data.get('data') and self.cleaned_data.get('data_fim') and self.cleaned_data.get('data_fim') < self.cleaned_data.get('data'):
            self.add_error('data_fim', 'A data final precisa ser maior do que a data inicial.')
        if (
            self.cleaned_data.get('data')
            and self.cleaned_data.get('data_fim')
            and self.cleaned_data.get('data_fim').year > (datetime.date.today().year + 1)
        ):
            self.add_error('data_fim', 'A data final não pode ser tão no futuro.')
        return cleaned_data


class GerarListaFrequenciaForm(forms.FormPlus):
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=False)
    data_termino = forms.DateFieldPlus(label='Data de Término', required=False)
    participante = forms.ModelChoiceFieldPlus(label='Participante', queryset=Vinculo.objects, required=False)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['participante'].queryset = Vinculo.objects.filter(id__in=self.projeto.participacao_set.values_list('vinculo_pessoa', flat=True))


class FiltrarListaFrequenciaForm(forms.FormPlus):
    METHOD = 'GET'
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=False)
    data_termino = forms.DateFieldPlus(label='Data de Término', required=False)
    participante = forms.ModelChoiceFieldPlus(label='Participante', queryset=Vinculo.objects, required=False)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['participante'].queryset = Vinculo.objects.filter(id__in=self.projeto.participacao_set.values_list('vinculo_pessoa', flat=True))


class EditarFrequenciaForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroFrequencia
        fields = ('descricao', 'data', 'carga_horaria')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].widget = forms.Textarea()
        self.fields['carga_horaria'].help_text = 'Informe a carga horária diária.'
        self.fields['carga_horaria'].label = 'Carga Horária Diária'


class AceiteTermoForm(forms.FormPlus):
    texto = TinyMCEFormField(label='Termo de Compromisso', required=False)
    aceito = forms.BooleanField(label='Aceito o Termo de Compromisso', required=True, initial=False)
    senha = forms.PasswordField()

    def __init__(self, *args, **kwargs):
        self.participacao = kwargs.pop('participacao', None)
        super().__init__(*args, **kwargs)
        if self.participacao.is_servidor():
            if self.participacao.responsavel:
                self.fields['texto'].initial = self.participacao.projeto.edital.termo_compromisso_coordenador
            else:
                self.fields['texto'].initial = self.participacao.projeto.edital.termo_compromisso_servidor
        elif self.participacao.eh_aluno():
            self.fields['texto'].initial = self.participacao.projeto.edital.termo_compromisso_aluno
        else:
            self.fields['texto'].initial = self.participacao.projeto.edital.termo_compromisso_colaborador_voluntario
        self.fields['texto'].widget.attrs['readonly'] = True


class AvaliadorExternoForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF')
    telefone = forms.BrTelefoneField(max_length=45, label='Telefone para Contato')
    lattes = forms.URLField(label='Lattes', help_text='Endereço do Currículo Lattes', required=True)
    areas = forms.ModelMultipleChoiceField(
        queryset=AreaConhecimento.objects.filter(superior__isnull=False),
        widget=FilteredSelectMultiplePlus('', True),
        label='Áreas de Conhecimento',
        required=False,
    )

    class Meta:
        model = AvaliadorExterno
        fields = ('nome', 'email', 'telefone', 'titulacao', 'instituicao_origem', 'lattes')

    def clean(self) -> dict:
        recusar_cadastro_de_prestador(self)  # antes do super().clean(), que levanta se já houver erro de campo
        return super().clean()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['cpf'].initial = self.instance.vinculo.relacionamento.cpf
            self.fields['areas'].initial = self.instance.vinculo.relacionamento.areas_de_conhecimento.all().values_list('pk', flat=True)

    def clean_cpf(self):
        prestador = PrestadorServico.objects.filter(pessoa_fisica__cpf=self.cleaned_data['cpf'])
        if prestador:
            avaliadores = AvaliadorExterno.objects.filter(vinculo=prestador[0].get_vinculo())
            erro = False
            if not self.instance.id and avaliadores.exists():
                erro = True
            else:
                if avaliadores.exclude(id=self.instance.id).exists():
                    erro = True
            if erro:
                raise forms.ValidationError('Já existe um avaliador externo cadastrado com este CPF.')
        return self.cleaned_data['cpf']

    @transaction.atomic
    def save(self, commit=True):
        email = self.cleaned_data['email']
        areas = self.cleaned_data['areas']

        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': self.cleaned_data['cpf'] or '',
            'nome_registro': self.cleaned_data['nome'],
            'email_secundario': self.cleaned_data['email'],
            'email': self.cleaned_data['email'],
        }
        telefone: PessoaTelefoneCadastro = {
            'numero': self.cleaned_data['telefone'],
        }
        dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'setor': get_setor_proen(), 'ativo': True, 'telefone': telefone}
        prestador = PrestadorServico.update_or_create(dados, enviar_email=False)['prestador']

        avaliador = super().save(False)

        avaliador.pessoa_fisica = prestador
        avaliador.vinculo = prestador.get_vinculo()
        avaliador.email = email
        avaliador.save()

        if areas:
            ids_areas = []
            for area in areas:
                ids_areas.append(area.id)
                if area not in prestador.areas_de_conhecimento.all():
                    prestador.areas_de_conhecimento.add(area)
            outras_areas = prestador.areas_de_conhecimento.exclude(id__in=ids_areas)
            if outras_areas.exists():
                for area in outras_areas:
                    prestador.areas_de_conhecimento.remove(area)

        self.enviar_email(prestador.username, email)

        return avaliador

    def enviar_email(self, username, email):
        obj = TrocarSenha.objects.create(username=username)
        url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
        conteudo = f"""
        <h1>Pesquisa</h1>
        <h2>Cadastro de Avaliador Externo</h2>
        <p>Prezado usuário,</p>
        <br />
        <p>Você foi cadastrado como Avaliador Externo de Projetos de Ensino.</p>
        <p>Caso ainda não tenha definido uma senha de acesso, por favor, acesse: {url}.</p>
        <br />
        <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
        <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>
        """
        return send_mail('[SUAP] Cadastro de Avaliador Externo', conteudo, settings.DEFAULT_FROM_EMAIL, [email])


class DadosBancariosParticipanteForm(forms.ModelFormPlus):
    class Meta:
        model = Participacao
        fields = (
            'instituicao',
            'numero_agencia',
            'tipo_conta',
            'numero_conta',
            'operacao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['instituicao'].queryset = Banco.objects.filter(excluido=False).exclude(sigla='').order_by('nome')


class CampusAdicionalForm(forms.ModelFormPlus):
    class Meta:
        model = CampusAdicional
        exclude = ()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo()
