import datetime
from decimal import Decimal

from django.apps import apps
from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.forms.models import BaseInlineFormSet, ModelChoiceField

from comum.models import (
    Ano,
    Configuracao,
    Municipio,
    Pais,
    PrestadorServico,
    SubobjetivoDesenvolvimentoSustentavel,
    TrocarSenha,
    Vinculo,
    UsuarioGrupo,
)
from comum.types import PessoaFisicaCadastro, PessoaTelefoneCadastro, PrestadorServicoCadastro
from comum.utils import get_setor_proex, get_uo, tl
from djtools import forms
from djtools.forms import ReadOnlyField
from djtools.forms.fields.tinymce import TinyMCEFormField
from djtools.forms.widgets import AutocompleteWidget, FilteredSelectMultiplePlus
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import format_
from djtools.utils import running_tests, send_mail
from edu.models import Aluno
from financeiro.models import NaturezaDespesa
from projetos.models import (
    AreaConhecimento,
    AreaLicaoAprendida,
    AreaTematica,
    AtividadeAutorizacaoSISBIO,
    AtividadeAutorizacaoSISGEN,
    Avaliacao,
    AvaliacaoAluno,
    AvaliadorExterno,
    CaracterizacaoBeneficiario,
    ColaboradorVoluntario,
    ComissaoEdital,
    CriterioAvaliacao,
    CriterioAvaliacaoAluno,
    Desembolso,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    Etapa,
    ExtratoMensalProjeto,
    FocoTecnologico,
    FotoNEPP,
    FotoProjeto,
    HistoricoEquipe,
    HistoricoInteresseCusteioProjeto,
    HistoricoOrientacaoProjeto,
    ItemAvaliacao,
    ItemAvaliacaoAluno,
    ItemMemoriaCalculo,
    LicaoAprendida,
    MembroNEPP,
    Meta,
    NucleoExtensao,
    ObjetivoVisitaTecnica,
    OcorrenciaProjeto,
    OfertaProjeto,
    OfertaProjetoPorGrupo,
    OfertaProjetoPorTema,
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
    Tema,
    TermoParceriaAdesao,
    TipoBeneficiario,
    TipoVinculo,
    VisitaTecnica,
    CriterioPreSelecao,
    PreSelecao,
    ItemPreSelecao,
    Comunicador,
    AvaliadorIndicado,
    ArquivoInativacaoProjeto,
    ArquivoFinalizacaoProjeto,
)
from rh.deduplicacao.entrada import recusar_passaporte_de_outra_pessoa, travar_documentos_na_edicao, recusar_cadastro_de_prestador
from rh.enums import Nacionalidade
from rh.models import Banco, Servidor, Setor, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    setor_proex = forms.ModelChoiceFieldPlus(
        Setor.objects,
        label='Setor da Pró-Reitoria',
        required=False,
        help_text='Os avaliadores externos de projetos de extensão serão vinculados automaticamente à este setor',
    )
    nome_proex = forms.CharFieldPlus(
        label='Nome da Pró-Reitoria', required=False, help_text='Este nome será exibido nos relatórios gerados no módulo de extensão'
    )
    gerente_pode_submeter = forms.BooleanField(label='Gerente sistêmico pode submeter projeto', required=False)
    carga_horaria_maxima_docente = forms.IntegerFieldPlus(
        label='Carga Horária Semanal para Docentes',
        help_text='Esta informação delimita a quantidade de horas-aula máximas que podem ser cadastradas para Docentes.',
        required=False,
    )
    carga_horaria_maxima_tae = forms.IntegerFieldPlus(
        label='Carga Horária Máxima Semanal para Técnicos-Administrativos',
        help_text='Esta informação delimita a quantidade de horas máximas que podem ser cadastradas para Técnicos-administrativos.',
        required=False,
    )
    aviso_editais = TinyMCEFormField(
        label='Aviso para exibição na tela dos editais',
        help_text='O conteúdo deste campo será exibido no menu "Extensão -> Projetos -> Editais -> Editais". Para não exibir nenhum aviso, deixe este campo em branco.',
        required=False,
    )


class BuscaProjetoForm(forms.FormPlus):
    palavra_chave = forms.CharField(label='Palavra-chave', required=False)
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
    edital = forms.ModelChoiceField(Edital.objects.filter(tipo_fomento=Edital.FOMENTO_INTERNO), required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    por_mim = forms.BooleanField(label='Monitorados por mim', required=False)
    METHOD = 'GET'

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.ano = kwargs.pop('ano', None)
        self.projetos = kwargs.pop('projetos')
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
        self.fields['uo'].queryset = UnidadeOrganizacional.objects.uo().filter(id__in=self.projetos.values_list('uo', flat=True))


class RegistroConclusaoProjetoForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroConclusaoProjeto
        exclude = ['projeto', 'dt_avaliacao', 'avaliador', 'aprovado', 'obs_avaliador']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        if self.projeto.eh_fomento_interno():
            if not self.instance.pk:
                self.fields['disseminacao_resultados'].initial = self.projeto.resultados_esperados
            self.fields['disseminacao_resultados'].required = True
            self.fields['resultados_alcancados'].required = True
        else:
            del self.fields['resultados_alcancados']
            del self.fields['disseminacao_resultados']


class RegistroConclusaoProjetoObsForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroConclusaoProjeto
        fields = ['obs_avaliador']


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
    fim_pre_selecao = forms.DateTimeFieldPlus(
        label='Fim da Pré-Seleção',
        required=False,
        help_text='Preencha este campo para definir o início do período de recursos da fase de pré-avaliação. Se este campo não for preenchido, o fim da pré-seleção coincidirá com o início da fase de seleção.',
    )
    inicio_selecao = forms.DateTimeFieldPlus(label='Início da Seleção', required=False)
    fim_selecao = forms.DateTimeFieldPlus(label='Fim da Seleção', required=False)
    divulgacao_selecao = forms.DateTimeFieldPlus(label='Divulgação da Seleção', required=False)
    campi_liberados = forms.MultipleModelChoiceFieldPlus(
        label='Campi que permitem coordenador de outro campus',
        help_text='Informe quais campi poderão ser indicados por qualquer coordenador na submissão do projeto.',
        queryset=UnidadeOrganizacional.objects.uo().all(),
        widget=FilteredSelectMultiplePlus('', True),
        required=False,
    )

    class Meta:
        model = Edital
        exclude = ()

    class Media:
        js = ['/static/projetos/js/editalform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        if self.instance.tipo_edital:
            self.fields['tipo_edital'].initial = self.instance.tipo_edital
            self.fields['tipo_edital'] = ReadOnlyField(label='Tipo do Edital')
            self.fields['tipo_edital'].initial = self.instance.tipo_edital
            self.fields['tipo_edital'].widget.display_value = self.instance.get_tipo_edital_display()
        if Configuracao.get_valor_por_chave('projetos', 'gerente_pode_submeter'):
            self.fields['sistemico_pode_submeter'].initial = True
            self.fields[
                'sistemico_pode_submeter'
            ].help_text = 'A configuração atual do SUAP permite que Gerente Sistêmico submeta em todos os projetos.'
            self.fields['sistemico_pode_submeter'].widget.attrs['disabled'] = 'disabled'
            self.fields['sistemico_pode_submeter'].widget.attrs['checked'] = 'checked'

    def clean(self, *args, **kwargs):
        if (
            self.cleaned_data.get('fim_inscricoes')
            and self.cleaned_data.get('inicio_inscricoes')
            and self.cleaned_data['fim_inscricoes'] <= self.cleaned_data['inicio_inscricoes']
        ):
            raise forms.ValidationError('A data do fim das inscrições deve ser maior que a data do início das inscrições.')

        if self.cleaned_data.get('prazo_avaliacao') and not self.cleaned_data.get('prazo_aceite_indicacao'):
            self.add_error('prazo_aceite_indicacao', 'É necessário informar o prazo para aceite nos casos em que há prazo para avaliação.')

        if self.cleaned_data.get('tipo_fomento') == Edital.FOMENTO_INTERNO:
            if not self.cleaned_data.get('inicio_pre_selecao'):
                self.add_error('inicio_pre_selecao', 'Preenchimento obrigatório.')

            if not self.cleaned_data.get('inicio_selecao'):
                self.add_error('inicio_selecao', 'Preenchimento obrigatório.')

            if not self.cleaned_data.get('fim_selecao'):
                self.add_error('fim_selecao', 'Preenchimento obrigatório.')

            if not self.cleaned_data.get('divulgacao_selecao'):
                self.add_error('divulgacao_selecao', 'Preenchimento obrigatório.')

            if self.cleaned_data.get('tipo_edital') and self.cleaned_data['tipo_edital'] == Edital.EXTENSAO:
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
                if (
                    self.cleaned_data.get('inicio_pre_selecao')
                    and self.cleaned_data.get('fim_pre_selecao')
                    and self.cleaned_data['fim_pre_selecao'] <= self.cleaned_data['inicio_pre_selecao']
                ):
                    self.add_error('fim_pre_selecao', 'A data de fim da pré-seleção deve ser maior que a data de início da pré-seleção.')

                if (
                    self.cleaned_data.get('fim_pre_selecao')
                    and self.cleaned_data.get('data_recurso_pre_selecao')
                    and self.cleaned_data['data_recurso_pre_selecao'] <= self.cleaned_data['fim_pre_selecao']
                ):
                    self.add_error(
                        'data_recurso_pre_selecao', 'A data limite para recursos da pré-seleção deve ser maior que a data de fim da pré-seleção.'
                    )

                if (
                    self.cleaned_data.get('inicio_selecao')
                    and self.cleaned_data.get('data_recurso_pre_selecao')
                    and self.cleaned_data['inicio_selecao'] <= self.cleaned_data['data_recurso_pre_selecao']
                ):
                    self.add_error(
                        'data_recurso_pre_selecao', 'A data limite para recursos da pré-seleção deve ser menor do que a data de início da seleção.'
                    )

                if self.cleaned_data.get('data_recurso_pre_selecao') and not self.cleaned_data.get('fim_pre_selecao'):
                    self.add_error('fim_pre_selecao', 'Este campo é obrigatório quando a Data Limite Para Recursos da Pré-Seleção é informada.')

            if self.cleaned_data.get('qtd_maxima_alunos_bolsistas'):
                if self.cleaned_data['qtd_maxima_alunos_bolsistas'] > self.cleaned_data['qtd_maxima_alunos']:
                    raise forms.ValidationError('A quantidade de alunos bolsistas não pode ser maior que a quantidade máxima de alunos.')
            if self.cleaned_data.get('qtd_maxima_servidores_bolsistas'):
                if self.cleaned_data['qtd_maxima_servidores_bolsistas'] > self.cleaned_data['qtd_maxima_servidores']:
                    raise forms.ValidationError('A quantidade de servidores bolsistas não pode ser maior que a quantidade máxima de servidores.')

            if self.cleaned_data.get('participa_aluno') and (self.cleaned_data.get('qtd_maxima_alunos') == 0):
                raise forms.ValidationError('Quando a participação de aluno é obrigatória, é preciso informar a quantidade máxima de alunos.')

            if self.cleaned_data.get('participa_servidor') and (self.cleaned_data.get('qtd_maxima_servidores') == 0):
                raise forms.ValidationError('Quando a participação de servidor é obrigatória, é preciso informar a quantidade máxima de servidores.')

        return super().clean(*args, **kwargs)


class RecursoForm(forms.ModelFormPlus):
    origem_recurso = forms.ModelChoiceField(OrigemRecursoEdital.objects.filter(ativo=True), label='Origem')

    class Meta:
        model = Recurso
        fields = ('origem_recurso', 'valor', 'despesa', 'eh_vinculada_cartao_pesquisador')

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            self.fields['origem_recurso'].initial = OrigemRecursoEdital.objects.get(descricao=self.instance.origem).id
        self.fields['valor'].label = 'Valor disponível por projeto (R$)'


class CriterioAvaliacaoForm(forms.ModelFormPlus):
    class Meta:
        model = CriterioAvaliacao
        exclude = ('edital',)

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital')
        super().__init__(*args, **kwargs)

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if self.cleaned_data.get('ordem_desempate'):
            if self.instance.pk:
                if (
                    CriterioAvaliacao.objects.filter(edital=self.edital, ordem_desempate=self.cleaned_data.get('ordem_desempate'))
                    .exclude(id=self.instance.id)
                    .exists()
                ):
                    self.add_error('ordem_desempate', 'Já existe um critério de avaliação com esta ordem de desempate.')
            else:
                if CriterioAvaliacao.objects.filter(edital=self.edital, ordem_desempate=self.cleaned_data.get('ordem_desempate')).exists():
                    self.add_error('ordem_desempate', 'Já existe um critério de avaliação com esta ordem de desempate.')
        return cleaned_data


class EditalAnexoForm(forms.ModelFormPlus):
    anexoedital = forms.ModelChoiceFieldPlus(queryset=EditalAnexoAuxiliar.objects, label='Anexo do Edital', required=False)

    class Meta:
        model = EditalAnexo
        fields = ('anexoedital', 'nome', 'descricao', 'tipo_membro', 'vinculo', 'ordem')

    class Media:
        js = ['/static/projetos/js/anexodosprojetosform.js']

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        self.fields['anexoedital'].queryset = EditalAnexoAuxiliar.objects.filter(edital=self.edital)

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if (
            cleaned_data.get('vinculo')
            and cleaned_data.get('tipo_membro')
            and cleaned_data.get('tipo_membro') == EditalAnexo.COLABORADOR_VOLUNTARIO
            and cleaned_data.get('vinculo') == EditalAnexo.BOLSISTA
        ):
            raise forms.ValidationError('Os colaboradores externos não podem ser cadastrados como bolsistas.')

        return cleaned_data


class EditalAnexoAuxiliarForm(forms.ModelFormPlus):
    class Meta:
        model = EditalAnexoAuxiliar
        exclude = ('edital', 'arquivo')


class OfertaProjetoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo(), label='Campus:', empty_label='Selecione o Campus', required=True)

    class Meta:
        model = OfertaProjeto
        fields = ('uo', 'qtd_aprovados', 'qtd_selecionados')

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            self.fields[
                'qtd_selecionados'
            ].help_text = 'Informe quantos projetos serão selecionados pela Diretoria de extensão/Coordenação de extensão do Campus.'
        else:
            self.fields['qtd_selecionados'].help_text = 'Informe quantos projetos serão selecionados pela Pró-reitoria de Extensão.'

        if self.edital.forma_selecao == Edital.GRUPO:
            del self.fields['qtd_aprovados']

        if self.edital.forma_selecao != Edital.CAMPUS:
            del self.fields['qtd_selecionados']

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if not self.instance.id and OfertaProjeto.objects.filter(edital=self.edital, uo=self.cleaned_data.get('uo')).exists():
            raise forms.ValidationError('Um plano de oferta para este campus já foi cadastrado.')

        return cleaned_data


class OfertaProjetoFormMultiplo(forms.FormPlus):
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi', queryset=UnidadeOrganizacional.objects.uo().all(), widget=FilteredSelectMultiplePlus('', True), required=True
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
            recursos = self.projeto.edital.recurso_set.all()
            if self.projeto and not self.projeto.tem_interesse_cartao_pesquisador:
                recursos = recursos.exclude(eh_vinculada_cartao_pesquisador=True)
            self.fields['recurso'].queryset = recursos


class ProjetoForm(forms.ModelFormPlus):
    edital = forms.ModelChoiceField(queryset=Edital.objects, widget=AutocompleteWidget(readonly=True))
    area_conhecimento = forms.ModelChoiceField(AreaConhecimento.objects, label='Área do Conhecimento', required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus:', empty_label='Selecione o Campus', required=True)
    area_tematica = forms.ModelChoiceField(AreaTematica.objects, label='Área Temática:', empty_label='Selecione a área temática', required=True)
    termo_compromisso_coordenador = TinyMCEFormField(label='Termo de Compromisso', required=False)
    aceita_termo = forms.BooleanField(label='Aceito o Termo de Compromisso', required=False, initial=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        setores_ids = []
        if hasattr(self.request.user.get_relacionamento(), 'setor_lotacao') and self.request.user.get_relacionamento().setor_lotacao:
            if self.request.user.get_relacionamento().setor_lotacao.uo.equivalente:
                setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.equivalente.id]
            else:
                setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.id]

        if hasattr(self.request.user.get_relacionamento(), 'setor') and self.request.user.get_relacionamento().setor:
            setores_ids += [self.request.user.get_relacionamento().setor.uo.id]

        if not running_tests():
            if hasattr(self.request.user.get_relacionamento(), 'setor_exercicio') and self.request.user.get_relacionamento().setor_exercicio:
                setores_ids += [self.request.user.get_relacionamento().setor_exercicio.uo.id]

        if self.instance.pk:
            setores_ids += [self.instance.uo.id]

        campus = self.instance.edital.get_uos()
        if UnidadeOrganizacional.objects.uo().filter(sigla='EAD').exists():
            ead = UnidadeOrganizacional.objects.uo().get(sigla='EAD')
            setores_ids.append(ead.id)
        if self.instance.edital.campi_liberados.exists():
            for campus_liberado in self.instance.edital.campi_liberados.all():
                setores_ids.append(campus_liberado.id)

        campus = campus.filter(id__in=setores_ids).filter(equivalente__isnull=True)
        self.fields['uo'].queryset = campus
        self.fields['resultados_esperados'].label = 'Resultados Esperados e Disseminação dos Resultados'
        if self.instance.edital.forma_selecao == Edital.TEMA:
            planos_oferta = OfertaProjetoPorTema.objects.filter(edital=self.instance.edital).values_list('area_tematica', flat=True)
            areas_tematicas = AreaTematica.objects.filter(id__in=planos_oferta)
            self.fields['area_tematica'].queryset = areas_tematicas

        self.fields['area_conhecimento'].queryset = AreaConhecimento.objects.filter(superior__isnull=False).order_by('descricao')

        if not self.instance.pk or not (tl.get_user().groups.filter(name='Gerente Sistêmico de Extensão').exists()):
            self.fields.pop('pre_aprovado')
            self.fields.pop('data_pre_avaliacao')
            self.fields.pop('aprovado')
            self.fields.pop('data_avaliacao')
            self.fields.pop('pontuacao')
        if self.instance.pk:
            del self.fields['termo_compromisso_coordenador']
            del self.fields['aceita_termo']
        if not self.instance.pk and not self.instance.edital.exige_termo_coordenador():
            del self.fields['termo_compromisso_coordenador']
            del self.fields['aceita_termo']
        elif not self.instance.pk:
            self.fields['termo_compromisso_coordenador'].initial = self.instance.edital.termo_compromisso_coordenador
            self.fields['termo_compromisso_coordenador'].widget.attrs['readonly'] = True

    def clean(self, *args, **kwargs):
        if not self.request.user.groups.filter(name='Gerente Sistêmico de Extensão'):
            if self.instance and self.instance.data_pre_avaliacao:
                raise forms.ValidationError('O projeto já foi pré-avaliado')
            if self.instance.participacao_set.count() and not Participacao.objects.filter(
                responsavel=True, vinculo_pessoa=tl.get_user().get_vinculo()
            ):
                raise forms.ValidationError('Apenas o coordenador pode editar o projeto')

        return super().clean(*args, **kwargs)


class ProjetoExtensaoForm(ProjetoForm):
    focotecnologico = forms.ChainedModelChoiceField(
        FocoTecnologico.ativos.all(),
        label='Foco Tecnológico:',
        empty_label='Selecione o Campus',
        required=True,
        obj_label='descricao',
        form_filters=[('uo', 'campi')],
        qs_filter='ativo=True',
    )

    resumo = TinyMCEFormField(label='Resumo', max_length=10000)
    justificativa = TinyMCEFormField(label='Justificativa', max_length=10000)
    fundamentacaoteorica = TinyMCEFormField(label='Fundamentação Teórica', max_length=10000)
    objetivo_geral = TinyMCEFormField(label='Objetivo Geral', max_length=10000)
    metodologia = TinyMCEFormField(label='Metodologia da execução do projeto', max_length=10000)
    acompanhamento_e_avaliacao = TinyMCEFormField(label='Acompanhamento e avaliação do projeto durante a execução', max_length=10000)
    resultados_esperados = TinyMCEFormField(label='Resultados Esperados e Disseminação dos Resultados', max_length=10000)
    referenciasbibliograficas = TinyMCEFormField(label='Referências Bibliográficas', max_length=10000)
    deseja_receber_bolsa = forms.BooleanField(label='O Coordenador Receberá Bolsa?', required=False, initial=False)
    vinculado_nepp = forms.ChoiceField(label='O Projeto é Vinculado ao NEPP?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')])

    carga_horaria = forms.IntegerFieldPlus(label='Carga Horária Semanal')
    nucleo_extensao = forms.ChainedModelChoiceField(
        NucleoExtensao.objects.filter(ativo=True),
        label='Núcleo de Extensão e Prática Profissional:',
        empty_label='Selecione o Campus',
        required=False,
        obj_label='nome',
        form_filters=[('uo', 'uo')],
    )
    atividade_integracao_curricular = forms.ChoiceField(
        label='O projeto é uma atividade de integração curricular da extensão?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    possui_cunho_social = forms.ChoiceField(
        label='Possui Cunho Social?', initial=None, choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    possui_acoes_empreendedorismo = forms.BooleanField(
        label='Contempla Ações de Empreendedorismo, Cooperativismo ou Economia Solidária Criativa?', required=False
    )
    tem_interesse_cartao_pesquisador = forms.ChoiceField(
        label='Tem interesse no fomento para custeio através do cartão BB pesquisador?',
        initial=None,
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    executado_com_parceria = forms.ChoiceField(
        label='O projeto possui comprovante de parceria/adesão?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    precisa_cep = forms.ChoiceField(
        label='Necessita de Autorização do Comitê de Ética em Pesquisa (CEP)?',
        initial='',
        choices=[('', '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    precisa_ceua = forms.ChoiceField(
        label='Necessita de Autorização do Comitê de Ética no Uso de Animais (CEUA)?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    precisa_sisgen = forms.ChoiceField(
        label='Necessita de Autorização do Sistema Nacional de Gestão do Patrimônio Genético e do Conhecimento Tradicional Associado (SISGEN)?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
        help_text='Para mais informações, acesse SISGEN e veja a Lei 13.123/2015',
    )
    precisa_sisbio = forms.ChoiceField(
        label='Necessita de Autorização do Sistema de Autorização e Informação em Biodiversidade (SISBIO)?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
        help_text='Para mais informações, acesse a portaria ICMBIO Nº 748, de 19 de setembro de 2022',
    )

    tem_ods = forms.ChoiceField(
        label='Pretende atender um ou mais Objetivos para o Desenvolvimento Sustentável (ODS) da ONU?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
        help_text='Detalhes de cada objetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
    )
    subobjetivos_desenvolvimento_sustentavel = forms.ModelMultipleChoiceField(
        label='Subobjetivos atendidos para o desenvolvimento sustentável (ODS) da ONU',
        queryset=SubobjetivoDesenvolvimentoSustentavel.objects.all(),
        help_text='Segure o botão "Control" para selecionar mais de um item. Detalhes de cada subobjetivo podem ser encontrados no site: https://brasil.un.org/pt-br/sdgs',
        required=False,
    )
    grupo = forms.ModelChoiceFieldPlus(label='Grupo', queryset=OfertaProjetoPorGrupo.objects)
    preve_atividades_internacionalizacao = forms.ChoiceField(
        label='O projeto prevê atividades de internacionalização, inclusive participação em eventos internacionais?',
        help_text='Em caso afirmativo, incluir os detalhes nos registros de atividades do projeto.',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )
    fieldsets = (
        (None, {'fields': ('edital', 'uo', 'grupo', 'nome_edital_externo', 'titulo', 'carga_horaria', 'valor_fomento_projeto_externo')}),
        (
            'Dados do Projeto',
            {
                'fields': (
                    'inicio_execucao',
                    'fim_execucao',
                    'focotecnologico',
                    'deseja_receber_bolsa',
                    'possui_cunho_social',
                    'possui_acoes_empreendedorismo',
                    'area_conhecimento',
                    'area_tematica',
                    'tema',
                    'publico_alvo',
                    'vinculado_nepp',
                    'nucleo_extensao',
                    'atividade_integracao_curricular',
                    'possui_cooperacao_internacional',
                    'preve_atividades_internacionalizacao',
                    'tem_interesse_cartao_pesquisador',
                    'precisa_cep',
                    'num_protocolo_cep',
                    'precisa_ceua',
                    'num_protocolo_ceua',
                    'precisa_sisgen',
                    'num_protocolo_sisgen',
                    'atividades_sisgen',
                    'precisa_sisbio',
                    'num_protocolo_sisbio',
                    'atividades_sisbio',
                    'tem_ods',
                    'objetivos_desenvolvimento_sustentavel',
                    'subobjetivos_desenvolvimento_sustentavel',
                )
            },
        ),
        (
            'Descrição do Projeto',
            {
                'fields': (
                    'resumo',
                    'justificativa',
                    'fundamentacaoteorica',
                    'objetivo_geral',
                    'metodologia',
                    'acompanhamento_e_avaliacao',
                    'resultados_esperados',
                    'referenciasbibliograficas',
                    'termo_compromisso_coordenador',
                    'aceita_termo',
                )
            },
        ),
        (
            'Comprovantes de Parceria/Adesão',
            {'fields': ('executado_com_parceria',)},
        ),
    )

    class Meta:
        model = Projeto
        exclude = (
            'participantes',
            'data_conclusao_planejamento',
            'classificacao',
            'descricao_comprovante_gru',
            'arquivo_comprovante_gru',
            'coordenador',
            'termo_parceria_adesao',
            'justificativa_reprovacao_manual',
        )

    class Media:
        js = ['/static/projetos/js/projetoform.js']

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request', None)
        self.edicao = kwargs.pop('edicao', None)
        if not self.edicao:
            kwargs['initial'] = {'possui_cunho_social': None}
            kwargs['initial'] = {'tem_interesse_cartao_pesquisador': None}
        super().__init__(*args, **kwargs)
        if self.instance.edital.forma_selecao != Edital.GRUPO:
            del self.fields['grupo']
        else:
            self.fields['grupo'].queryset = OfertaProjetoPorGrupo.objects.filter(edital=self.instance.edital)
        if not self.instance.edital.coordenador_pode_receber_bolsa:
            self.fields['deseja_receber_bolsa'].initial = False
            self.fields['deseja_receber_bolsa'].widget = forms.Select(attrs={'readonly': 'readonly'})
            self.fields['deseja_receber_bolsa'].help_text = 'Este edital não prevê bolsa para coordenador.'
        if not self.edicao:
            self.initial['possui_cunho_social'] = None
        self.fields['area_tematica'].required = True
        self.fields['nucleo_extensao'].required = False
        self.fields[
            'possui_cooperacao_internacional'
        ].label = f'O projeto está relacionado a alguma instituição com a qual o {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")} possui acordo de cooperação internacional vigente?'
        if not NucleoExtensao.objects.exists():
            del self.fields['vinculado_nepp']
            del self.fields['nucleo_extensao']
        self.fields[
            'possui_cunho_social'
        ].help_text = 'Projetos de ações inclusivas e de tecnologias sociais, preferencialmente, para populações e comunidades em situação de risco, atendendo às áreas temáticas da extensão.'
        if self.instance.edital.temas.exists():
            self.fields['area_tematica'].queryset = AreaTematica.objects.filter(
                id__in=self.instance.edital.temas.all().values_list('areatematica', flat=True)
            )
            queryset_temas = Tema.objects.filter(id__in=self.instance.edital.temas.all().values_list('id', flat=True))
        else:
            queryset_temas = Tema.objects
        if self.instance.edital.exige_tema:
            self.fields['tema'] = forms.ChainedModelChoiceField(
                queryset_temas,
                label='Tema:',
                empty_label='Selecione a Área Temática',
                required=True,
                obj_label='descricao',
                form_filters=[('area_tematica', 'areatematica')],
            )
        else:
            del self.fields['tema']

        if self.instance.edital.eh_fomento_interno():
            if 'publico_alvo' in self.fields and not self.instance.publico_alvo:
                self.fields.pop('publico_alvo')

            del self.fields['nome_edital_externo']
            del self.fields['valor_fomento_projeto_externo']

        else:
            self.fields['nome_edital_externo'].label = 'Informe o Nº e nome do edital de fomento ou Nº do convênio ou Termo de Cooperação Técnica'
            self.fields['nome_edital_externo'].required = True

            if not self.edicao:
                del self.fields['deseja_receber_bolsa']
            del self.fields['publico_alvo']
            del self.fields['justificativa']
            del self.fields['objetivo_geral']
            del self.fields['metodologia']
            del self.fields['acompanhamento_e_avaliacao']
            del self.fields['resultados_esperados']
            del self.fields['fundamentacaoteorica']
            del self.fields['referenciasbibliograficas']

        if self.edicao:
            del self.fields['deseja_receber_bolsa']
            part = Participacao.objects.filter(vinculo_pessoa=self.request.user.get_vinculo(), projeto=self.instance)
            if part.exists():
                part = part[0]
                self.fields['carga_horaria'].initial = part.carga_horaria
            if NucleoExtensao.objects.exists():
                if self.instance.nucleo_extensao:
                    self.fields['vinculado_nepp'].initial = True
                else:
                    self.fields['vinculado_nepp'].initial = False
            if self.instance.termo_parceria_adesao:
                self.fields['executado_com_parceria'].initial = True
            else:
                self.fields['executado_com_parceria'].initial = False
            if self.instance.atividade_integracao_curricular:
                self.fields['atividade_integracao_curricular'].initial = True
            else:
                self.fields['atividade_integracao_curricular'].initial = False
            if self.instance.preve_atividades_internacionalizacao:
                self.fields['preve_atividades_internacionalizacao'].initial = True
            else:
                self.fields['preve_atividades_internacionalizacao'].initial = False

        if self.request.user.eh_tecnico_administrativo:
            ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_tae')
            carga_max_tae = ch_max and int(ch_max) or 6
            self.fields[
                'carga_horaria'
            ].help_text = f'Carga horária semanal do coordenador do projeto. Máximo permitido para técnico-administrativo: {carga_max_tae} horas'
        elif self.request.user.eh_docente:
            ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_docente')
            carga_max_docente = ch_max and int(ch_max) or 8
            self.fields[
                'carga_horaria'
            ].help_text = f'Carga horária semanal do coordenador do projeto. Máximo permitido para docente: {carga_max_docente} horas-aula.'
        else:
            self.fields['carga_horaria'].help_text = 'Carga horária semanal do coordenador do projeto.'
        if self.instance.edital.exige_vinculacao_nepp:
            self.fields['vinculado_nepp'].help_text = 'Este edital exige que o projeto seja vinculado a um NEPP.'

        if self.instance.pk and self.instance.objetivos_desenvolvimento_sustentavel.exists():
            self.fields['tem_ods'].initial = True
        self.fields['atividades_sisgen'].widget = forms.CheckboxSelectMultiplePlus()
        self.fields['atividades_sisgen'].queryset = AtividadeAutorizacaoSISGEN.objects.filter(ativo=True).order_by('descricao')
        self.fields['atividades_sisbio'].widget = forms.CheckboxSelectMultiplePlus()
        self.fields['atividades_sisbio'].queryset = AtividadeAutorizacaoSISBIO.objects.filter(ativo=True).order_by('descricao')

        if self.instance.pk:
            self.initial['atividades_sisgen'] = [op.id for op in self.instance.atividades_sisgen.all()]
            self.initial['atividades_sisbio'] = [op.id for op in self.instance.atividades_sisbio.all()]
            self.initial['subobjetivos_desenvolvimento_sustentavel'] = [op.id for op in self.instance.subobjetivos_desenvolvimento_sustentavel.all()]

        if running_tests():
            del self.fields['possui_cunho_social']
            del self.fields['tem_interesse_cartao_pesquisador']
            del self.fields['executado_com_parceria']
            del self.fields['tem_ods']
        if not self.instance.edital.exige_info_autorizacao_comites:
            del self.fields['precisa_cep']
            del self.fields['num_protocolo_cep']
            del self.fields['precisa_ceua']
            del self.fields['num_protocolo_ceua']
            del self.fields['precisa_sisgen']
            del self.fields['num_protocolo_sisgen']
            del self.fields['atividades_sisgen']
            del self.fields['precisa_sisbio']
            del self.fields['num_protocolo_sisbio']
            del self.fields['atividades_sisbio']

    def clean(self):
        if self.cleaned_data.get('carga_horaria') and self.request.user.eh_tecnico_administrativo:
            ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_tae')
            carga_max_tae = ch_max and int(ch_max) or 6
            if self.cleaned_data.get('carga_horaria') > carga_max_tae:
                self.add_error('carga_horaria', f'O máximo permitido são {carga_max_tae} horas.')
        if self.cleaned_data.get('carga_horaria') and self.request.user.eh_docente:
            ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_docente')
            carga_max_docente = ch_max and int(ch_max) or 8
            if self.cleaned_data.get('carga_horaria') > carga_max_docente:
                self.add_error('carga_horaria', f'O máximo permitido são {carga_max_docente} horas-aula.')
        if (
            self.cleaned_data.get('inicio_execucao')
            and self.cleaned_data.get('fim_execucao')
            and (self.cleaned_data.get('inicio_execucao') > self.cleaned_data.get('fim_execucao'))
        ):
            self.add_error('inicio_execucao', 'A data de início do projeto não pode ser maior do que a data de término.')

        if self.cleaned_data.get('vinculado_nepp') == 'True' and not self.cleaned_data.get('nucleo_extensao'):
            self.add_error('nucleo_extensao', 'Informe a qual NEPP o projeto está vinculado.')

        if not self.instance.pk and self.instance.edital.exige_termo_coordenador() and not self.cleaned_data['aceita_termo']:
            self.add_error('aceita_termo', 'Você precisa aceitar o termo de compromisso para submeter o projeto.')

        eh_auxiliar = self.instance.auxiliar and self.instance.auxiliar == self.request.user.get_vinculo()
        if (
            self.instance.pk
            and self.instance.participacao_set.count()
            and not Participacao.objects.filter(projeto_id=self.instance.pk, responsavel=True, vinculo_pessoa=self.request.user.get_vinculo())
            and not eh_auxiliar
        ):
            raise forms.ValidationError('Apenas o coordenador pode editar o projeto.')
        if self.instance.edital.exige_vinculacao_nepp and not self.cleaned_data.get('nucleo_extensao'):
            self.add_error('vinculado_nepp', 'Este edital exige que o projeto seja vinculado a um NEPP.')
        if self.cleaned_data.get('titulo') and self.cleaned_data.get('titulo').isupper():
            self.add_error('titulo', 'O título do projeto não pode ser escrito com todas as letras em caixa alta.')
        if self.cleaned_data.get('objetivos_desenvolvimento_sustentavel') and self.cleaned_data.get('subobjetivos_desenvolvimento_sustentavel'):
            for item in self.cleaned_data.get('subobjetivos_desenvolvimento_sustentavel'):
                if item.objetivo not in self.cleaned_data.get('objetivos_desenvolvimento_sustentavel'):
                    self.add_error('subobjetivos_desenvolvimento_sustentavel', f'O ODS do subojetivo {item.__str__()} não foi selecionado.')
        if not self.instance.edital.coordenador_pode_receber_bolsa and self.cleaned_data.get('deseja_receber_bolsa'):
            self.add_error('deseja_receber_bolsa', 'Este edital não prevê bolsa para coordenador.')


def ext_combo_template_aluno(obj):
    out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{obj}</dd>']
    img_src = obj.get_foto_75x100_url()
    out.append(f'<dt class="visually-hidden">Curso</dt><dd>{obj.curso_campus}</dd>')

    template = """<div class="person">
        <div class="photo-circle">
            <img src="{}" alt="Foto de {}" />
        </div>
        <dl>{}</dl>
    </div>
    """.format(img_src, obj, ''.join(out))
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
        fields = ('vinculo', 'carga_horaria', 'indicar_pessoa_posteriormente', 'aluno', 'data', 'nivel_ensino', 'obs')

    class Media:
        js = ['/static/projetos/js/adicionaralunoform.js']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.edital = self.projeto.edital
        self.editar = kwargs.pop('editar', None)
        super().__init__(*args, **kwargs)
        if self.instance.pk:
            if self.instance.vinculo_pessoa:
                self.fields.pop('aluno')
                del self.fields['indicar_pessoa_posteriormente']
                del self.fields['nivel_ensino']
                del self.fields['obs']
            elif self.edital.permite_indicacao_tardia_equipe:
                if self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
                    self.fields['aluno'].required = False
                    self.fields['data'].required = False
                else:
                    del self.fields['indicar_pessoa_posteriormente']
                    del self.fields['nivel_ensino']
                    del self.fields['obs']
            self.historico = HistoricoEquipe.objects.filter(ativo=True, participante=self.instance, projeto=self.instance.projeto).order_by('id')
            if self.historico and self.historico[0].data_movimentacao:
                self.fields['data'].initial = self.historico[0].data_movimentacao

        elif self.edital.permite_indicacao_tardia_equipe and self.projeto.get_status() == Projeto.STATUS_EM_INSCRICAO:
            self.fields['aluno'].required = False
            self.fields['data'].required = False
        else:
            del self.fields['indicar_pessoa_posteriormente']
            del self.fields['nivel_ensino']
            del self.fields['obs']

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

        if self.cleaned_data.get('vinculo') == 'Bolsista':
            msg = Participacao.get_mensagem_aluno_nao_pode_ter_bolsa(self.cleaned_data.get('aluno'))
            if msg:
                raise forms.ValidationError(msg)

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
    out = [f'<dt class="visually-hidden">Nome</dt><dd class="title">{obj.pessoa_fisica.nome} (Mat. {obj.matricula})</dd>']
    if obj.setor:
        out.append(f'<dt class="visually-hidden">Setor</dt><dd>{obj.setor.get_caminho_as_html()}</dd>')
    if obj.cargo_emprego:
        out.append(f'<dt class="visually-hidden">Cargo</dt><dd>{obj.cargo_emprego}</dd>')
    _vinculo = next(iter(getattr(obj, '_vinculo_servidor_list', [])), None)
    if _vinculo is not None and hasattr(_vinculo, 'vinculo_curriculo_lattes'):
        out.append('<dt class="visually-hidden">Currículo Lattes</dt><dd class="true">Tem currículo Lattes</dd>')
    else:
        out.append('<dt class="visually-hidden">Currículo Lattes</dt><dd class="false">Não há currículo Lattes</dd>')
    template = """<div class="person">
        <div class="photo-circle">
            <img src="{}" alt="Foto de {}" />
        </div>
        <dl>{}</dl>
    </div>
    """.format(obj.get_foto_75x100_url(), obj.pessoa_fisica.nome, ''.join(out))
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
            self.historico = HistoricoEquipe.objects.filter(ativo=True, participante=self.instance, projeto=self.instance.projeto).order_by('id')
            self.fields['data'].initial = self.historico.exists() and self.historico[0].data_movimentacao or self.instance.projeto.inicio_execucao

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

        if (
            self.cleaned_data.get('servidor')
            and instance.vinculo_monitor
            and instance.vinculo_monitor.relacionamento == self.cleaned_data.get('servidor')
        ):
            self.add_error('servidor', 'O(a) monitor(a) do projeto não pode fazer parte da equipe do projeto.')

        if self.cleaned_data.get('data') and self.cleaned_data.get('data') > instance.fim_execucao:
            raise forms.ValidationError('A data informada é maior do que a data de término do projeto, não é possível inserir/editar servidor.')

        if instance.fim_execucao < datetime.date.today():
            raise forms.ValidationError(
                'A data de término da execução do projeto é menor do que a data de hoje, não é possível inserir/editar servidor.'
            )

        if self.cleaned_data.get('carga_horaria') and self.instance and self.instance.responsavel:
            if self.instance.vinculo_pessoa.user.eh_docente:
                ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_docente')
                carga_max_docente = ch_max and int(ch_max) or 8
                if self.cleaned_data.get('carga_horaria') > carga_max_docente:
                    self.add_error('carga_horaria', f'O máximo permitido são {carga_max_docente} horas-aula.')
            elif self.instance.vinculo_pessoa.user.eh_tecnico_administrativo:
                ch_max = Configuracao.get_valor_por_chave('projetos', 'carga_horaria_maxima_tae')
                carga_max_tae = ch_max and int(ch_max) or 6
                if self.cleaned_data.get('carga_horaria') > carga_max_tae:
                    self.add_error('carga_horaria', f'O máximo permitido são {carga_max_tae} horas.')

        if self.cleaned_data.get('vinculo') == 'Bolsista':
            if self.instance.pk:
                if self.instance.responsavel is True and not self.instance.projeto.edital.coordenador_pode_receber_bolsa:
                    raise forms.ValidationError('Este edital não permite bolsa para coordenador. O mesmo só poderá ser voluntário.')
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


class ParticipacaoColaboradorForm(forms.ModelFormPlus):
    vinculo = forms.ChoiceField(label='Bolsista', required=True, choices=TipoVinculo.TIPOS)
    prestador = forms.ModelChoiceField(
        queryset=ColaboradorVoluntario.objects.filter(ativo=True),
        widget=AutocompleteWidget(
            search_fields=['nome', 'prestador__pessoa_fisica__cpf', 'prestador__pessoa_fisica__passaporte'],
            extraParams={'ext_combo_template': ext_combo_template_colaborador},
        ),
        label='Participante',
        required=True,
        help_text='O Colaborador precisa ser cadastrado previamente pelo Coordenador de Extensão.',
    )

    data = forms.DateFieldPlus(label='Data de Entrada', help_text='A data não pode ser maior do que hoje.')

    class Meta:
        model = Participacao
        fields = ('vinculo', 'carga_horaria', 'prestador', 'data')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        if not self.projeto.edital.colaborador_externo_bolsista:
            del self.fields['vinculo']

        if self.instance.pk:
            self.fields.pop('prestador')
            self.historico = HistoricoEquipe.objects.filter(ativo=True, participante=self.instance, projeto=self.instance.projeto).order_by('id')
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


class AlterarCoordenadorForm(forms.FormPlus):
    participacao = forms.ModelChoiceField(Participacao.objects, label='Novo Coordenador', required=True)
    data = forms.DateFieldPlus(label='Data Inicial da Nova Coordenação')
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())

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
        if self.cleaned_data.get('participacao') and self.projeto.edital.atingiu_limite_aprovacoes(
            self.cleaned_data.get('participacao').vinculo_pessoa
        ):
            self.add_error('participacao', 'Este participante já coordena a quantidade máxima permitida de projetos neste edital.')
        if (
            self.cleaned_data.get('participacao')
            and self.projeto.edital.eh_fomento_interno()
            and Projeto.pendencias_editais_anteriores(self.cleaned_data.get('participacao').vinculo_pessoa, self.projeto.edital).exists()
        ):
            self.add_error('participacao', 'Este participante possui pendência de editais anteriores e não pode assumir a coordenação deste projeto.')

        if (
            self.cleaned_data.get('participacao')
            and self.cleaned_data['participacao'].vinculo == TipoVinculo.BOLSISTA
            and self.projeto.edital.coordenador_pode_receber_bolsa is False
        ):
            self.add_error(
                'participacao', 'O coordenador não pode ser bolsista. Edite o vínculo do pesquisador antes de alterar o coordenador do projeto.'
            )

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
        self.fields['responsavel'].queryset = (
            self.projeto.participacao_set.filter(ativo=True)
            .filter(id__in=self.projeto.get_ids_participacoes_com_anuencia())
            .exclude(id__in=self.projeto.get_ids_participacoes_sem_termo())
        )
        self.fields['integrantes'].queryset = (
            self.projeto.participacao_set.filter(ativo=True)
            .filter(id__in=self.projeto.get_ids_participacoes_com_anuencia())
            .exclude(id__in=self.projeto.get_ids_participacoes_sem_termo())
        )
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
            if (
                self.projeto.edital.prazo_atividade
                and (self.cleaned_data.get('fim_execucao') - self.cleaned_data.get('inicio_execucao')).days > self.projeto.edital.prazo_atividade
            ):
                raise forms.ValidationError(f'O prazo máximo de cada atividade neste projeto deve ser de {self.projeto.edital.prazo_atividade} dias.')

            if self.cleaned_data['inicio_execucao'] < self.projeto.inicio_execucao:
                self.add_error('inicio_execucao', 'A data de início de execução da atividade não pode ser anterior ao início da execução do projeto.')

            if self.cleaned_data['fim_execucao'] < self.projeto.inicio_execucao:
                self.add_error('fim_execucao', 'A data de fim de execução da atividade não pode ser anterior ao início da execução do projeto.')

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


class UploadArquivoForm(forms.FormPlus):
    documento = forms.ModelChoiceFieldPlus(label='Documento do Edital', queryset=None, required=False)
    arquivo = forms.FileFieldPlus(required=False)

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if 'documento_eletronico' in settings.INSTALLED_APPS:
            from documento_eletronico.models import DocumentoStatus, DocumentoTexto

            self.fields['documento'].queryset = DocumentoTexto.objects.filter(status=DocumentoStatus.STATUS_FINALIZADO)
            if self.edital and self.edital.id_documento_edital:
                self.fields['documento'].initial = self.edital.id_documento_edital
        else:
            del self.fields['documento']
            self.fields['arquivo'].required = True

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if not cleaned_data.get('arquivo') and not cleaned_data.get('documento'):
            self.add_error('arquivo', 'Informe o arquivo.')
        return cleaned_data


class RegistroGastoForm(forms.ModelFormPlus):
    gasto_nao_executado = forms.BooleanField(
        label='Gasto não executado', help_text='Marque esta opção para registrar que o desembolso planejado não foi executado.', required=False
    )
    arquivo = forms.FileFieldPlus(label='Nota Fiscal ou Cupom', required=False)
    cotacao_precos = forms.FileFieldPlus(
        label='Cotação de Preços', required=False, help_text='Envie um arquivo ZIP contendo as três propostas de cotação de preços deste item.'
    )

    class Meta:
        model = RegistroGasto
        fields = ('gasto_nao_executado', 'ano', 'mes', 'descricao', 'qtd', 'valor_unitario', 'observacao', 'arquivo', 'cotacao_precos')

    class Media:
        js = ['/static/projetos/js/registrogasto.js']

    def __init__(self, *args, **kwargs):
        self.desembolso = kwargs.pop('desembolso')
        super().__init__(*args, **kwargs)
        if self.instance.pk and not self.instance.pode_editar_remover_registro_gasto():
            del self.fields['ano']
            del self.fields['mes']
            del self.fields['descricao']
            del self.fields['valor_unitario']
            del self.fields['observacao']
            del self.fields['qtd']
            del self.fields['gasto_nao_executado']
        elif self.instance.pk and self.instance.valor_unitario == 0.00:
            self.fields['gasto_nao_executado'].initial = True

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if 'valor_unitario' not in self.fields:  # só os arquivos: não há valores a validar
            return cleaned_data
        if cleaned_data.get('gasto_nao_executado'):
            if not cleaned_data.get('observacao'):
                self.add_error('observacao', 'Informe o motivo pelo qual o desembolso não foi executado.')
            registros_previos = RegistroGasto.objects.filter(desembolso=self.desembolso)
            if self.instance.pk:
                registros_previos = registros_previos.exclude(id=self.instance.pk)
            if registros_previos.exists():
                self.add_error(
                    'gasto_nao_executado', 'Não é possível informar gasto não executado se o desembolso já possui outro(s) gasto(s) registrado(s).'
                )
        else:
            if not cleaned_data.get('valor_unitario'):
                self.add_error(
                    'valor_unitario',
                    'O valor unitário deve ser maior do que R$ 0,00. Se deseja registrar que o gasto não foi executado, marque a opção "Gasto não executado".',
                )

            if not cleaned_data.get('qtd'):
                self.add_error(
                    'qtd',
                    'A quantidade deve ser maior do que 0. Se deseja registrar que o gasto não foi executado, marque a opção "Gasto não executado".',
                )
        return cleaned_data


class RegistroExecucaoEtapaForm(forms.ModelFormPlus):
    arquivo = forms.FileFieldPlus(
        label='Arquivo',
        required=False,
        filetypes=[
            'pdf',
            'PDF',
        ],
    )

    class Meta:
        model = RegistroExecucaoEtapa
        exclude = ('etapa', 'dt_avaliacao', 'avaliador', 'aprovado', 'info_ind_qualitativo', 'justificativa_reprovacao', 'data_cadastro_execucao')

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        self.fields['arquivo'].help_text = 'Caso haja mais de um arquivo de comprovação, junte todos em um único arquivo no formato PDF.'

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        situacao = self.cleaned_data.get('tipo_indicador_qualitativo')
        if (
            situacao
            and self.projeto.edital.exige_comprovante_atividade
            and situacao != RegistroExecucaoEtapa.NAO_ATENTIDO
            and not self.cleaned_data.get('arquivo')
        ):
            self.add_error('arquivo', 'O cadastro do arquivo de comprovação é obrigatório.')
        return cleaned_data


class ValidacaoConclusaoProjetoForm(forms.FormPlus):
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


def AvaliacaoFormFactory(request, avaliacao, projeto, vinculo):
    class AvaliacaoForm(forms.FormPlus):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)

            if avaliacao:
                for item in avaliacao.itemavaliacao_set.all():
                    nota_choices = []
                    maior_nota = (2 * item.criterio_avaliacao.pontuacao_maxima) + 1
                    if item.criterio_avaliacao.pontuacao_binaria:
                        notas = [round(item.criterio_avaliacao.pontuacao_maxima, 1), 0.0]
                    else:
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
                    if criterio_avaliacao.pontuacao_binaria:
                        notas = [round(criterio_avaliacao.pontuacao_maxima, 1), 0.0]
                    else:
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
        exclude = ('projeto', 'data_operacao', 'situacao', 'operador')


class RelatorioDimensaoExtensaoForm(forms.FormPlus):
    METHOD = 'GET'
    TIPO_FOMENTO_CHOICES = (('', 'Todos'), (Edital.FOMENTO_INTERNO, Edital.FOMENTO_INTERNO), (Edital.FOMENTO_EXTERNO, Edital.FOMENTO_EXTERNO))

    ano = forms.ChoiceField(choices=[], required=False, label='Ano de Início:')
    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo(), required=False, label='Campus')

    tipo_edital = forms.ChoiceField(
        label='Tipo do Edital',
        choices=[('Todos', 'Todos'), ('Edital de Campus', 'Edital de Campus'), ('Edital Sistêmico', 'Edital Sistêmico')],
        required=False,
    )

    tipo_fomento = forms.ChoiceField(choices=TIPO_FOMENTO_CHOICES, required=False, label='Tipo de Fomento:')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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
        if not self.request.user.has_perm('projetos.pode_visualizar_avaliadores_externos'):
            del self.fields['campus']

        self.fields['ano'].choices = ANO_CHOICES


class OfertaProjetoPorTemaForm(forms.ModelFormPlus):
    area_tematica = forms.ModelChoiceField(label='Área Temática:', required=True, queryset=AreaTematica.objects)
    tema = forms.ChainedModelChoiceField(
        Tema.objects,
        label='Tema:',
        empty_label='Selecione a Área Temática',
        required=False,
        obj_label='descricao',
        form_filters=[('area_tematica', 'areatematica')],
    )

    class Meta:
        model = OfertaProjetoPorTema
        exclude = ('edital',)


class LicaoAprendidaForm(forms.ModelFormPlus):
    class Meta:
        model = LicaoAprendida
        exclude = ('projeto',)


class RelatorioLicoesAprendidasForm(forms.FormPlus):
    METHOD = 'GET'

    edital = forms.ModelChoiceField(
        queryset=Edital.objects.filter(tipo_fomento=Edital.FOMENTO_INTERNO),
        empty_label='Selecione um Edital',
        label='Filtrar por Edital:',
        required=False,
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    area = forms.ModelChoiceField(AreaLicaoAprendida.objects, required=False, label='Área de Conhecimento:')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.groups.filter(name__in=['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)


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

    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=True)
    situacao = forms.ChoiceField(choices=AVALIACAO_STATUS, label='Filtrar por Situação', required=False)

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.request.user.groups.filter(name__in=['Gerente Sistêmico de Extensão', 'Coordenador de Extensão']):
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
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = forms.ModelChoiceField(
        queryset=Edital.objects.order_by('-inicio_inscricoes'), empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False
    )

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )
    METHOD = 'GET'
    TIPO_EXIBICAO = ((0, 'Detalhado'), (1, 'Simples'))
    tipo_de_exibicao = forms.ChoiceField(choices=TIPO_EXIBICAO, label='Tipo de Exibição', required=False, initial=1)

    TIPO_SITUACAO = ((0, 'Todos'), (1, 'Concluído'), (2, 'Em execução'))
    situacao = forms.ChoiceField(choices=TIPO_SITUACAO, label='Filtrar Projetos por Situação', required=False, initial=2)

    PARTICIPANTES_CHOICES = (
        ('', '----------'),
        ('1', 'Apenas servidores'),
        ('2', 'Apenas alunos'),
    )
    tipo_participantes = forms.ChoiceField(label='Tipo de participantes', choices=PARTICIPANTES_CHOICES, required=False)

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        participantes = Participacao.objects.filter(projeto__aprovado=True).values_list('vinculo_pessoa', flat=True)
        self.fields['pessoa'] = forms.ModelChoiceFieldPlus(Vinculo.objects.filter(id__in=set(participantes)), required=False)
        if not self.request.user.groups.filter(name__in=['Gerente Sistêmico de Extensão', 'Visualizador de Projetos']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)
        # colocar filtro apenas_bolsistas por último
        self.fields['apenas_bolsistas'] = forms.BooleanField(label='Apenas bolsistas', required=False)

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
        fields = ['justificativa_cancelamento']


class AvaliarCancelamentoProjetoForm(forms.ModelFormPlus):
    obs_avaliacao = forms.CharField(widget=forms.Textarea(), label='Parecer do Avaliador')
    cancelado = forms.ChoiceField(label='Cancelar projeto?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')])
    aprova_proximo = forms.ChoiceField(
        label='Aprovar próximo projeto?',
        help_text="O primeiro projeto da lista de espera será aprovado automaticamente e o coordenador será notificado por email. Só terá efeito se a opção 'Cancelar Projeto' for selecionada.",
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )

    class Meta:
        model = ProjetoCancelado
        fields = ['obs_avaliacao', 'cancelado']

    def __init__(self, *args, **kwargs):
        eh_continuo = kwargs.pop('eh_continuo', None)
        edicao = kwargs.pop('edicao', None)
        super().__init__(*args, **kwargs)
        self.fields['obs_avaliacao'].initial = self.instance.obs_avaliacao
        if edicao:
            self.fields['cancelado'].initial = self.instance.cancelado
        else:
            self.initial['cancelado'] = None
        if eh_continuo:
            self.fields['aprova_proximo'].required = False
            self.fields['aprova_proximo'].widget = forms.HiddenInput()
        if self.instance.proximo_projeto:
            del self.fields['aprova_proximo']
        if self.instance.data_avaliacao and self.instance.cancelado:
            del self.fields['cancelado']


class IndicarPreAvaliadorForm(forms.FormPlus):
    METHOD = 'GET'
    AVALIACAO_STATUS = ((1, 'Projetos em conflito'), (2, 'Projetos sem monitor'), (0, 'Todos'))
    palavra_chave = forms.CharField(label='Avaliador', required=False)
    uo = forms.ModelChoiceField(
        UnidadeOrganizacional.objects.uo(), label='Campus', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    area_tematica = forms.ModelChoiceField(
        AreaTematica.objects, label='Área Temática', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    status_avaliacao = forms.ChoiceField(
        choices=AVALIACAO_STATUS, label='Filtrar por Situação', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if (
            self.request.user.groups.filter(name='Coordenador de Extensão').exists()
            and not self.request.user.groups.filter(name='Gerente Sistêmico de Extensão').exists()
        ):
            self.fields['uo'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)


class IndicarAvaliadoresForm(forms.FormPlus):
    nome = forms.CharFieldPlus(label='Nome', required=False)
    matricula = forms.CharFieldPlus(label='Matrícula', required=False)
    area_tematica = forms.ModelChoiceFieldPlus(AreaTematica.objects.order_by('descricao'), required=False, label='Filtrar por Área Temática')


class IndicarAvaliadorForm(forms.FormPlus):
    METHOD = 'GET'
    SUBMIT_LABEL = 'Buscar'
    AVALIACAO_STATUS = (
        (0, 'Todos'),
        (1, 'Projetos avaliados'),
        (2, 'Projetos não avaliados'),
        (3, 'Projetos parcialmente avaliados'),
        (4, 'Com Divergência de Pontuação'),
    )
    palavra_chave = forms.CharField(label='Avaliador', required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)

    area_tematica = forms.ModelChoiceField(AreaTematica.objects, label='Área Temática', required=False)

    status_avaliacao = forms.ChoiceField(choices=AVALIACAO_STATUS, label='Situação da avaliação', required=False)
    pontos = forms.IntegerFieldPlus(label='Qual a pontuação mínima de divergência?', required=False)

    class Media:
        js = ['/static/projetos/js/indicaravaliadorform.js']


class ComissaoEditalForm(forms.ModelFormPlus):
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = ModelChoiceField(queryset=Edital.objects, label='Filtrar por Edital:', required=True)

    clonar_comissao = forms.BooleanField(label='Clonar Comissão de um Edital anterior', initial=False, required=False)

    vinculos_membros = forms.MultipleModelChoiceFieldPlus(Vinculo.objects, label='Membro', required=False)

    clonar_comissao_edital = ModelChoiceField(queryset=Edital.objects.order_by('-id'), label='Clonar Comissão do Edital:', required=True)

    class Meta:
        model = ComissaoEdital
        fields = ('ano', 'edital', 'clonar_comissao', 'vinculos_membros', 'clonar_comissao_edital')

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['clonar_comissao_edital'].required = False

        internos = Servidor.objects.ativos().values_list('id', flat=True)
        externos = AvaliadorExterno.objects.all().values_list('vinculo', flat=True)
        queryset = Vinculo.objects.filter(Q(id_relacionamento__in=internos, tipo_relacionamento__model='servidor') | Q(id__in=externos))
        self.fields['vinculos_membros'].queryset = queryset.order_by('pessoa__nome')

        if self.instance.pk:
            self.fields['clonar_comissao_edital'].widget = forms.HiddenInput()
            self.fields['clonar_comissao'].widget = forms.HiddenInput()
            avaliadores = self.instance.vinculos_membros.all()
            for avaliador in avaliadores:
                if avaliador not in queryset:
                    avaliadores = avaliadores.exclude(id=avaliador.id)
            self.initial['vinculos_membros'] = [registro.id for registro in avaliadores]

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
    justificativa = forms.CharField(widget=forms.Textarea(), label='Justificativa do Recurso', max_length=10000)

    class Meta:
        model = RecursoProjeto
        fields = ['justificativa', 'arquivo']


class AvaliarRecursoProjetoForm(forms.ModelFormPlus):
    parecer = forms.CharField(widget=forms.Textarea(), label='Parecer do Avaliador')
    aceito = forms.BooleanField(label='Aceitar Recurso', required=False)

    class Meta:
        model = RecursoProjeto
        fields = ['parecer', 'aceito']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['parecer'].initial = self.instance.parecer


class EditaisForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
    PENDENTES_AVALIACAO = 'Pendentes de Avaliação'
    PARECER_FAVORAVEL = 'Parecer Favorável'
    INDEFERIDA = 'Solicitação Indeferida'
    SITUACOES_CHOICES = (
        ('', 'Todas'),
        (PENDENTES_AVALIACAO, PENDENTES_AVALIACAO),
        (PARECER_FAVORAVEL, PARECER_FAVORAVEL),
        (INDEFERIDA, INDEFERIDA),
    )

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)
    situacao = forms.ChoiceField(label='Filtrar por Situação', choices=SITUACOES_CHOICES, required=False)

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

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
        self.fields['ano'].choices = ANO_CHOICES
        if not self.request.user.groups.filter(name='Gerente Sistêmico de Extensão'):
            ids = OfertaProjeto.objects.filter(uo=get_uo(self.request.user))
            self.fields['edital'].queryset = editais.filter(campus_especifico=True, id__in=ids.values_list('edital', flat=True))

        if self.ano:
            self.fields['edital'].queryset = editais.filter(inicio_inscricoes__year=self.ano)


class AnexosDiversosProjetoForm(forms.ModelFormPlus):
    descricao = forms.CharField(label='Descrição', required=True)
    vinculo_membro_equipe = forms.ModelChoiceField(Vinculo.objects, required=False, label='Membro da Equipe')
    arquivo_anexo = forms.FileFieldPlus(label='Arquivo')

    class Meta:
        model = ProjetoAnexo
        fields = ['descricao', 'vinculo_membro_equipe', 'desembolso', 'ano', 'mes']

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
    TIPO_RELATORIO = ((1, 'Parcial'), (2, 'Final'))
    tipo_relatorio = forms.ChoiceField(
        choices=TIPO_RELATORIO, label='Tipo do Relatório', required=False, widget=forms.Select(attrs={'onchange': 'submeter_form(this)'})
    )

    despesa = forms.ModelChoiceField(queryset=NaturezaDespesa.objects, label='Elemento de Despesa', required=False)
    ano_relatorio = forms.ModelChoiceField(queryset=Ano.objects, label='Ano', required=False)

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
        js = ['/static/projetos/js/prestacaocontaform.js']

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


class ExtratoMensalForm(forms.ModelFormPlus):
    class Meta:
        model = ExtratoMensalProjeto
        fields = ['ano', 'mes', 'arquivo']

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)

        ANO_CHOICES = []
        for ano in range(datetime.datetime.now().year, self.projeto.data_conclusao_planejamento.year - 1, -1):
            ANO_CHOICES.append(str(ano))

        self.fields['ano'].queryset = Ano.objects.filter(ano__in=ANO_CHOICES)


class TermoCessaoForm(forms.FormPlus):
    registro = forms.ModelChoiceField(
        queryset=RegistroGasto.objects,
        label='Registro de Gasto',
        required=True,
        help_text='Apenas registros de gastos com material permanente podem ser associados ao termo de cessão/doação.',
    )

    arquivo = forms.FileFieldPlus()

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
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus:', empty_label='Selecione o Campus', required=True)
    justificativa_alteracoes = forms.CharField(
        label='Justificativa da Alteração de Datas',
        required=False,
        widget=forms.Textarea(),
        help_text='Caso haja alteração nas datas, informe a justificativa. Até 5000 caracteres.',
        max_length=5000,
    )
    atividade_integracao_curricular = forms.ChoiceField(
        label='O projeto é uma atividade de integração curricular da extensão?', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')]
    )
    novo_inicio_execucao = forms.DateFieldPlus(label='Início da Execução')
    novo_fim_execucao = forms.DateFieldPlus(label='Término da Execução')
    deseja_alterar_interesse_custeio = forms.BooleanField(
        label='Deseja alterar sua escolha sobre o interesse no fomento para custeio através do cartão BB pesquisador?', required=False
    )
    motivo_alteracao_interesse_custeio = forms.CharFieldPlus(label='Informe o Motivo', required=False, widget=forms.Textarea())

    class Meta:
        model = Projeto
        fields = [
            'titulo',
            'uo',
            'nome_edital_externo',
            'valor_fomento_projeto_externo',
            'possui_cunho_social',
            'possui_acoes_empreendedorismo',
            'nucleo_extensao',
            'novo_inicio_execucao',
            'novo_fim_execucao',
            'justificativa_alteracoes',
            'resumo',
            'possui_cooperacao_internacional',
            'atividade_integracao_curricular',
            'deseja_alterar_interesse_custeio',
            'motivo_alteracao_interesse_custeio',
        ]

    class Media:
        js = ['/static/projetos/js/editarprojetoform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['novo_inicio_execucao'].initial = self.instance.inicio_execucao
        self.fields['novo_fim_execucao'].initial = self.instance.fim_execucao
        self.fields[
            'possui_cunho_social'
        ].help_text = 'Projetos de ações inclusivas e de tecnologias sociais, preferencialmente, para populações e comunidades em situação de risco, atendendo às áreas temáticas da extensão.'
        if self.instance.eh_fomento_interno():
            del self.fields['nome_edital_externo']
            del self.fields['valor_fomento_projeto_externo']
            del self.fields['resumo']
            del self.fields['uo']
        elif self.instance.data_conclusao_planejamento:
            del self.fields['resumo']

        self.fields['nucleo_extensao'].queryset = NucleoExtensao.objects.filter(ativo=True, uo=self.instance.uo)
        if self.instance.pk and self.instance.nucleo_extensao:
            self.fields['nucleo_extensao'].initial = self.instance.nucleo_extensao.id

        self.fields[
            'possui_cooperacao_internacional'
        ].label = f'O projeto está relacionado a alguma instituição com a qual o {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")} possui acordo de cooperação internacional vigente?'
        if not self.instance.eh_fomento_interno():
            if self.instance.get_status() == Projeto.STATUS_EM_EXECUCAO:
                del self.fields['uo']
            else:
                setores_ids = []
                if hasattr(self.request.user.get_relacionamento(), 'setor_lotacao') and self.request.user.get_relacionamento().setor_lotacao:
                    if self.request.user.get_relacionamento().setor_lotacao.uo.equivalente:
                        setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.equivalente.id]
                    else:
                        setores_ids += [self.request.user.get_relacionamento().setor_lotacao.uo.id]

                if hasattr(self.request.user.get_relacionamento(), 'setor') and self.request.user.get_relacionamento().setor:
                    setores_ids += [self.request.user.get_relacionamento().setor.uo.id]

                if not running_tests():
                    if hasattr(self.request.user.get_relacionamento(), 'setor_exercicio') and self.request.user.get_relacionamento().setor_exercicio:
                        setores_ids += [self.request.user.get_relacionamento().setor_exercicio.uo.id]

                if self.instance.pk:
                    setores_ids += [self.instance.uo.id]

                campus = self.instance.edital.get_uos()
                if UnidadeOrganizacional.objects.uo().filter(sigla='EAD').exists():
                    ead = UnidadeOrganizacional.objects.uo().get(sigla='EAD')
                    setores_ids.append(ead.id)
                if self.instance.edital.campi_liberados.exists():
                    for campus_liberado in self.instance.edital.campi_liberados.all():
                        setores_ids.append(campus_liberado.id)

                campus = campus.filter(id__in=setores_ids).filter(equivalente__isnull=True)
                self.fields['uo'].queryset = campus
                self.fields['uo'].initial = self.instance.uo

    def clean(self):
        cleaned_data = super().clean()
        if self.cleaned_data.get('novo_inicio_execucao') and self.cleaned_data.get('novo_fim_execucao'):
            if (
                self.cleaned_data.get('novo_inicio_execucao') != self.instance.inicio_execucao
                or self.cleaned_data.get('novo_fim_execucao') != self.instance.fim_execucao
            ):
                if not self.cleaned_data.get('justificativa_alteracoes'):
                    self.add_error('justificativa_alteracoes', 'Informe a justificativa para alteração na(s) data(s).')
            if self.cleaned_data.get('novo_inicio_execucao') > self.cleaned_data.get('novo_fim_execucao'):
                self.add_error('novo_inicio_execucao', 'A data de início do projeto não pode ser maior do que a data de término.')
        if self.cleaned_data.get('titulo') and self.cleaned_data.get('titulo').isupper():
            self.add_error('titulo', 'O título do projeto não pode ser escrito com todas as letras em caixa alta.')

        if self.cleaned_data.get('deseja_alterar_interesse_custeio') and not self.cleaned_data.get('motivo_alteracao_interesse_custeio'):
            self.add_error('motivo_alteracao_interesse_custeio', 'Informe o motivo para alterar o interesse pelo custeio.')
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


class AvaliadorExternoForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF')
    telefone = forms.BrTelefoneField(max_length=45, label='Telefone para Contato')
    lattes = forms.URLField(label='Lattes', help_text='Endereço do Currículo Lattes', required=True)

    class Meta:
        model = AvaliadorExterno
        fields = ('nome', 'email', 'telefone', 'titulacao', 'instituicao_origem', 'lattes')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance and self.instance.pk:
            self.fields['cpf'] = ReadOnlyField(label='CPF')
            self.fields['cpf'].initial = self.instance.vinculo.pessoa.pessoafisica.cpf

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

    def clean(self):
        if (
            self.cleaned_data.get('email')
            and not Configuracao.get_valor_por_chave('rh', 'permite_email_institucional_email_secundario')
            and Configuracao.eh_email_institucional(self.cleaned_data.get('email'))
        ):
            self.add_error('email', 'Escolha um e-mail que não seja institucional.')
        recusar_cadastro_de_prestador(self)  # antes do super().clean(), que levanta se já houver erro de campo

    @transaction.atomic
    def save(self, commit=True):
        email = self.cleaned_data['email']

        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': self.cleaned_data['cpf'] or '',
            'nome_registro': self.cleaned_data['nome'],
            'email_secundario': self.cleaned_data['email'],
            'email': self.cleaned_data['email'],
        }
        telefone: PessoaTelefoneCadastro = {
            'numero': self.cleaned_data['telefone'],
        }
        dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'setor': get_setor_proex(), 'ativo': True, 'telefone': telefone}
        if not PrestadorServico.objects.filter(pessoa_fisica__cpf=self.cleaned_data['cpf']).exists():
            prestador_created = True
        else:
            prestador_created = False
        prestador = PrestadorServico.update_or_create(dados)['prestador']
        avaliador = super().save(False)

        avaliador.vinculo = prestador.get_vinculo()
        avaliador.email = email
        avaliador.save()

        if prestador_created:
            self.enviar_email(prestador.matricula, email)

        return avaliador

    def enviar_email(self, username, email):
        obj = TrocarSenha.objects.create(username=username)
        url = f'{settings.SITE_URL}/comum/trocar_senha/{obj.username}/{obj.token}/'
        conteudo = f"""
        <h1>Extensão</h1>
        <h2>Cadastro de Avaliador Externo</h2>
        <p>Prezado usuário,</p>
        <br />
        <p>Você acaba de ser cadastrado como Avaliador Externo de Projetos de Extensão.</p>
        <p>Acesse o SUAP através do link {settings.SITE_URL} e escolha a opção "Entrar com Gov.BR".</p>
        <p>Caso não seja possível e ainda não tenha definido uma senha de acesso, por favor, acesse o endereço: {url}.</p>
        <br />
        <p>Caso o token seja inválido, informe o seu cpf nos campos 'usuário' e 'cpf' ('usuário' tem que ser sem pontuação).</p>
        <p>Em seguida será reenviado um email com as instruções para criação da senha de acesso.</p>
        """
        return send_mail('[SUAP] Cadastro de Avaliador Externo', conteudo, settings.DEFAULT_FROM_EMAIL, [email])


class DataInativacaoForm(forms.FormPlus):
    data = forms.DateFieldPlus(label='Data de Inativação', required=True)
    ch_extensao = forms.IntegerField(
        label='Carga Horária de Extensão', required=True, help_text='Carga horária total destinada a atividade curricular de extensão'
    )
    justificativa = forms.CharField(label='Justificativa', required=True, widget=forms.Textarea(), max_length=1000)

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        self.participacao = kwargs.pop('participacao', None)
        super().__init__(*args, **kwargs)
        self.fields['ch_extensao'].initial = self.participacao.ch_extensao
        if self.participacao.is_aluno_extensao():
            self.fields['ch_extensao'].initial = self.participacao.get_ch_extensao()
        else:
            self.fields['ch_extensao'].required = False
            self.fields['ch_extensao'].widget = forms.HiddenInput()

    def clean_ch_extensao(self):
        ch_extensao = self.cleaned_data.get('ch_extensao')
        AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
        from django.contrib.contenttypes.fields import ContentType

        content = ContentType.objects.get_for_model(type(self.participacao))
        ace = (
            AtividadeCurricularExtensao.objects.filter(tipo_referencia=content, id_referencia=self.participacao.id)
            .only('carga_horaria_vinculada')
            .first()
        )
        carga_horaria_vinculada = ace.get_carga_horaria_vinculada() if ace else 0
        if ch_extensao and ch_extensao < carga_horaria_vinculada:
            raise forms.ValidationError(
                f'Este aluno possui {carga_horaria_vinculada} hora(s) vinculada(s) a atividades de extensão. Para encerrar a participação com CH menor será necessário desfazer os vínculos realizados.'
            )
        return ch_extensao

    def clean(self):
        cleaned_data = super().clean()
        data_informada = self.cleaned_data.get('data')
        if data_informada and data_informada > self.projeto.fim_execucao:
            raise forms.ValidationError('A data de inativação não pode ser após o fim do projeto.')
        if data_informada:
            historicos = HistoricoEquipe.objects.filter(ativo=True, projeto=self.projeto, participante=self.participacao).order_by('-id')
            if historicos.exists():
                ultimo_historico = historicos[0]
                if ultimo_historico.data_movimentacao > data_informada:
                    raise forms.ValidationError('A data de inativação não pode ser menor do que a data de início do vínculo atual.')
            data = data_informada
            if self.projeto.fim_execucao < data_informada:
                data = self.projeto.fim_execucao
            tem_pendencia_frequencia = self.projeto.tem_frequencia_aluno_pendente(participacao=self.participacao, data=data)
            if tem_pendencia_frequencia:
                self.add_error('data', f'O participante possui registro de frequência pendente: {tem_pendencia_frequencia}.')

        return cleaned_data


class ProjetosAtrasadosForm(forms.FormPlus):
    SITUACAO_STATUS = ((1, 'Projetos em Atraso'), (2, 'Projetos com Atividades Atrasadas'), (3, 'Projetos em dia'), (0, 'Todos'))
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = forms.ModelChoiceField(
        queryset=Edital.objects.filter(tipo_fomento=Edital.FOMENTO_INTERNO),
        empty_label='Selecione um Edital',
        label='Filtrar por Edital:',
        required=False,
    )
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    situacao = forms.ChoiceField(choices=SITUACAO_STATUS, label='Filtrar por Situação', required=False)

    METHOD = 'GET'

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
        if not self.request.user.has_perm('projetos.pode_visualizar_avaliadores_externos'):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']


class ListaAvaliadoresProjetosForm(forms.FormPlus):
    SITUACAO_STATUS = ((0, 'Todos'), (1, 'Avaliadores Internos'), (2, 'Avaliadores Externos'))
    edital = forms.ModelChoiceField(
        queryset=Edital.objects.filter(tipo_fomento=Edital.FOMENTO_INTERNO),
        empty_label='Selecione um Edital',
        label='Filtrar por Edital:',
        required=False,
    )

    tipo = forms.ChoiceField(choices=SITUACAO_STATUS, label='Filtrar por Vínculo', required=False)

    area_tematica = forms.ModelChoiceField(
        queryset=AreaTematica.objects.all(), empty_label='Selecione uma Área Temática', label='Filtrar por Área Temática:', required=False
    )

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


class VisitaTecnicaForm(forms.ModelFormPlus):
    cnpj = forms.BrCnpjField(label='CNPJ')
    estado = forms.BrEstadoBrasileiroField(label='Estado da Instituição')
    municipio = forms.ChainedModelChoiceField(
        Municipio.objects, label='Município:', empty_label='Selecione o Estado', required=True, obj_label='nome', form_filters=[('estado', 'uf')]
    )
    encaminhamentos = forms.CharField(label='Encaminhamentos', widget=forms.Textarea())
    telefone_contato = forms.BrTelefoneField(label='Telefone do Contato')
    email_contato = forms.EmailField(label='Email do Contato')
    objetivos = forms.ModelMultipleChoiceField(queryset=ObjetivoVisitaTecnica.objects, label='Objetivos', widget=forms.CheckboxSelectMultiplePlus())
    cep = forms.BrCepField(max_length=255, required=False, label='CEP')
    deseja_parceria = forms.ChoiceField(label='Deseja parceria', choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')])

    class Meta:
        model = VisitaTecnica
        fields = (
            'cnpj',
            'instituicao_visitada',
            'estado',
            'municipio',
            'logradouro',
            'numero',
            'complemento',
            'bairro',
            'cep',
            'nome_contato',
            'telefone_contato',
            'email_contato',
            'campus',
            'data',
            'objetivos',
            'participantes',
            'encaminhamentos',
            'deseja_parceria',
        )

    class Media:
        js = ('/static/projetos/js/VisitaTecnicaForm.js',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['deseja_parceria'].label = f'Deseja parceria com o {Configuracao.get_valor_por_chave("comum", "instituicao_sigla")}'
        if (
            self.request.user.groups.filter(name='Coordenador de Extensão').exists()
            and not self.request.user.groups.filter(name='Gerente Sistêmico de Extensão').exists()
        ):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)
        else:
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().all()

        if self.instance.pk:
            self.fields['estado'].initial = self.instance.municipio.uf
            self.fields['municipio'].initial = self.instance.municipio


class EditarTermoCessaoForm(forms.ModelFormPlus):
    class Meta:
        model = RegistroGasto
        fields = ('arquivo_termo_cessao', 'obs_cessao')


class AnoForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ChoiceField(choices=[], required=False, label='Ano:')

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


class ProjetoAvaliadorForm(forms.FormPlus):
    areas_tematicas_extensao = forms.ModelMultiplePopupChoiceField(AreaTematica.objects, required=False, label='Áreas Temáticas')

    def __init__(self, pessoa, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['areas_tematicas_extensao'].initial = AreaTematica.objects.filter(vinculo=pessoa).values_list('pk', flat=True)


class EditalTemasForm(forms.FormPlus):
    areatematica = forms.ModelChoiceField(queryset=AreaTematica.objects, label='Filtrar por Área Temática')


class MeusProjetosForm(forms.FormPlus):
    METHOD = 'GET'

    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
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

    situacao = forms.ChoiceField(choices=AVALIACAO_STATUS, label='Filtrar por Situação', required=False)
    pendencia = forms.ChoiceField(
        choices=(
            ('', '-----------'),
            (1, 'Em atraso'),
            (2, 'Com atividades atrasadas'),
            (3, 'Próximo da data de término'),
        ),
        label='Filtrar por Pendência',
        required=False,
    )
    vinculo_membro = forms.ChoiceField(
        choices=(
            ('', '---------'),
            (1, 'Coordenador'),
            (2, 'Membro'),
        ),
        label='Filtrar por Vínculo',
        required=False,
    )

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

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

    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
    AVALIACAO_STATUS = (
        ('Projetos em Edição', 'Projetos em Edição'),
        ('Projetos Enviados', 'Projetos Enviados'),
        ('Projetos Pré-Selecionados', 'Projetos Pré-Selecionados'),
        ('Projetos em Execução', 'Projetos em Execução'),
    )
    PENDENTES_AVALIACAO = 'Pendentes de Avaliação'
    PARECER_FAVORAVEL = 'Parecer Favorável'
    INDEFERIDA = 'Solicitação Indeferida'
    SITUACOES_CHOICES = (
        ('', 'Todas'),
        (PENDENTES_AVALIACAO, PENDENTES_AVALIACAO),
        (PARECER_FAVORAVEL, PARECER_FAVORAVEL),
        (INDEFERIDA, INDEFERIDA),
    )

    edital = forms.ModelChoiceField(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)
    situacao = forms.ChoiceField(label='Filtrar por Situação', choices=SITUACOES_CHOICES, required=False)

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

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


class ComprovanteGRUForm(forms.ModelFormPlus):
    descricao_comprovante_gru = forms.CharFieldPlus(label='Descrição', required=True)
    arquivo_comprovante_gru = forms.FileFieldPlus(label='Comprovante de Pagamento da GRU', required=True)

    class Meta:
        model = Projeto
        fields = ['descricao_comprovante_gru', 'arquivo_comprovante_gru']


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

            if HistoricoEquipe.objects.filter(ativo=True, participante=self.participacao).exists():
                entrada_aluno = HistoricoEquipe.objects.filter(ativo=True, participante=self.participacao).order_by('id')[0].data_movimentacao
                if self.cleaned_data.get('data_inicio') < entrada_aluno:
                    raise forms.ValidationError(
                        'O início da orientação não pode ser anterior a data de início da participação do discente no projeto ({}).'.format(
                            entrada_aluno.strftime('%d/%m/%y')
                        )
                    )

            if (
                self.cleaned_data.get('participacao')
                and HistoricoEquipe.objects.filter(ativo=True, participante=self.cleaned_data.get('participacao')).exists()
            ):
                entrada_orientador = (
                    HistoricoEquipe.objects.filter(ativo=True, participante=self.cleaned_data.get('participacao')).order_by('id')[0].data_movimentacao
                )
                if self.cleaned_data.get('data_inicio') < entrada_orientador:
                    raise forms.ValidationError(
                        'O início da orientação não pode ser anterior a data de início da participação do orientador no projeto ({}).'.format(
                            entrada_orientador.strftime('%d/%m/%y')
                        )
                    )

        return cleaned_data


class PreAvaliacaoForm(forms.FormPlus):
    METHOD = 'GET'
    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )

    area_conhecimento = forms.ModelChoiceField(AreaConhecimento.objects, required=False, label='Área de Conhecimento:')
    area_tematica = forms.ModelChoiceField(AreaTematica.objects, required=False, label='Área Temática:')
    pendentes = forms.BooleanField(label='Apenas pendentes de avaliação', required=False)

    def __init__(self, *args, **kwargs):
        self.nao_eh_sistemico = kwargs.pop('nao_eh_sistemico', None)
        super().__init__(*args, **kwargs)
        if self.nao_eh_sistemico:
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)


class AvaliadoresAreaTematicaForm(forms.FormPlus):
    METHOD = 'GET'
    VINCULOS = (('Todos', 'Todos'), ('Interno', 'Interno'), ('Externo', 'Externo'))
    palavra_chave = forms.CharField(label='Nome', required=False)
    vinculo = forms.ChoiceField(choices=VINCULOS, label='Filtrar por Vínculo', required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo().all(), label='Campus', required=False)
    instituicoes = forms.ChoiceField(choices=[], label='Instituições', required=False)
    area_tematica = forms.ModelChoiceField(
        queryset=AreaTematica.objects.all(), empty_label='Selecione uma Área Temática', label='Filtrar por Área Temática:', required=False
    )
    situacao = forms.ChoiceField(label='Situação', choices=(('', '--------'), ('Ativos', 'Ativos'), ('Inativos', 'Inativos')), required=False)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        lista = []
        lista.append(['', '--------------'])
        for instituicao in set(AvaliadorExterno.objects.all().values_list('instituicao_origem__nome', flat=True)):
            lista.append([instituicao, instituicao])

        self.fields['instituicoes'].choices = lista

        if self.request.GET.get('vinculo') and self.request.GET.get('vinculo') == 'Externo':
            del self.fields['uo']
        elif self.request.GET.get('vinculo') and self.request.GET.get('vinculo') == 'Interno':
            del self.fields['instituicoes']


class EstatisticasForm(forms.FormPlus):
    METHOD = 'GET'

    TIPO_FOMENTO_CHOICES = (('', 'Todos'), (Edital.FOMENTO_INTERNO, Edital.FOMENTO_INTERNO), (Edital.FOMENTO_EXTERNO, Edital.FOMENTO_EXTERNO))

    campus = forms.ModelChoiceFieldPlus(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Campus:', required=False
    )

    ano = forms.ChoiceField(choices=[], required=False, label='Ano de Início:')

    edital = forms.ModelChoiceFieldPlus(queryset=Edital.objects, empty_label='Selecione um Edital', label='Filtrar por Edital:', required=False)

    inicio_periodo = forms.DateFieldPlus(label='Início do período', required=False)
    fim_periodo = forms.DateFieldPlus(label='Fim do período', required=False)
    tipo_edital = forms.ChoiceField(
        label='Tipo do Edital',
        choices=[('Todos', 'Todos'), ('Edital de Campus', 'Edital de Campus'), ('Edital Sistêmico', 'Edital Sistêmico')],
        required=False,
    )

    tipo_fomento = forms.ChoiceField(choices=TIPO_FOMENTO_CHOICES, required=False, label='Tipo de Fomento:')

    cunho_social = forms.BooleanField(label='Possui Cunho Social', required=False)
    acoes_empreendedorismo = forms.BooleanField(
        label='Contempla Ações de Empreendedorismo, Cooperativismo ou Economia Solidária Criativa', required=False
    )
    vinculados_nepps = forms.BooleanField(label='Vinculados aos NEPPS', required=False)
    executado_com_parceria = forms.BooleanField(label='Executado com Parceria', required=False)
    integracao_curricular = forms.BooleanField(label='Integração Curricular da Extensão', required=False)

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
        if not self.request.user.has_perm('projetos.pode_visualizar_avaliadores_externos'):
            del self.fields['campus']

    def clean(self, *args, **kwargs):
        cleaned_data = super().clean()
        if (
            self.cleaned_data.get('inicio_periodo')
            and self.cleaned_data.get('fim_periodo')
            and self.cleaned_data.get('inicio_periodo') > self.cleaned_data.get('fim_periodo')
        ):
            self.add_error('fim_periodo', 'A data de fim do período precisa ser maior do que a data de início do período.')
        return cleaned_data


class InativarProjetoForm(forms.ModelFormPlus):
    motivo_inativacao = forms.CharFieldPlus(label='Motivo da Inativação', widget=forms.Textarea())

    class Meta:
        model = Projeto
        fields = ('motivo_inativacao',)


class ColaboradorVoluntarioForm(forms.ModelFormPlus):
    cpf = forms.BrCpfField(label='CPF', required=False)
    passaporte = forms.CharField(label='Nº do Passaporte', required=False, help_text='Esse campo é obrigatório para estrangeiros. Ex: BR123456')
    nacionalidade = forms.ChoiceField(label='Nacionalidade', choices=Nacionalidade.get_choices(), required=True)
    pais_origem = forms.ModelChoiceFieldPlus(queryset=Pais.objects, label='País de Origem', required=False)
    telefone = forms.BrTelefoneField(max_length=45, label='Telefone para Contato')
    lattes = forms.URLField(label='Lattes', help_text='Endereço do Currículo Lattes', required=False)

    class Meta:
        model = ColaboradorVoluntario
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
            matricula = PrestadorServico.matricula_do_passaporte(passaporte, pais_origem)
        else:
            matricula = PrestadorServico.gerar_matricula(cpf)
        qs = PrestadorServico.objects.filter(matricula=matricula)
        if self.instance.pk:
            qs = qs.exclude(id=self.instance.prestador.id)
        prestador_existente = qs.exists()
        if prestador_existente:
            prestador = qs[0]
            if ColaboradorVoluntario.objects.filter(prestador=prestador).exists():
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
        numero_telefone = self.cleaned_data['telefone']
        lattes = self.cleaned_data['lattes']

        pessoa_fisica: PessoaFisicaCadastro = {
            'cpf': self.cleaned_data['cpf'] or '',
            'nome_registro': self.cleaned_data['nome'],
            'nacionalidade': int(self.cleaned_data['nacionalidade'] or 1),
            'passaporte': self.cleaned_data['passaporte'] or '',
            'email_secundario': self.cleaned_data['email'],
            'email': self.cleaned_data['email'],
            'pais_origem': self.cleaned_data['pais_origem'],
        }
        telefone: PessoaTelefoneCadastro = {
            'numero': self.cleaned_data['telefone'],
        }
        dados: PrestadorServicoCadastro = {'pessoa_fisica': pessoa_fisica, 'setor': get_setor_proex(), 'ativo': True, 'telefone': telefone}
        prestador = PrestadorServico.update_or_create(dados)['prestador']

        avaliador = super().save(False)

        avaliador.prestador = prestador
        avaliador.email = email
        avaliador.telefone = numero_telefone
        avaliador.lattes = lattes
        avaliador.save()

        return avaliador


class ClonarProjetoForm(forms.FormPlus):
    edital = forms.ModelChoiceField(Edital.objects, required=False, label='Filtrar por Edital')
    clona_caracterizacao = forms.BooleanField(label='Caracterização de Beneficiários', initial=True, required=False)
    clona_equipe = forms.BooleanField(label='Equipe', initial=True, required=False)
    clona_atividade = forms.BooleanField(label='Metas/Atividades', initial=True, required=False)
    clona_memoria_calculo = forms.BooleanField(label='Memória de Cálculo', initial=True, required=False)
    clona_desembolso = forms.BooleanField(label='Desembolso', initial=True, required=False)
    data_inicio = forms.DateFieldPlus(label='Data de Início')
    data_fim = forms.DateFieldPlus(label='Data de Término')
    termo_compromisso_coordenador = TinyMCEFormField(label='Termo de Compromisso', required=True)
    aceita_termo = forms.BooleanField(label='Aceito o Termo de Compromisso', required=True)

    fieldsets = (
        ('Selecione o Projeto a Ser Clonado', {'fields': ('edital', 'projeto')}),
        (
            'Selecione os Dados a Serem Clonados',
            {'fields': ('clona_caracterizacao', 'clona_equipe', 'clona_atividade', 'clona_memoria_calculo', 'clona_desembolso')},
        ),
        ('Informe o Período do Novo Projeto', {'fields': (('data_inicio', 'data_fim'),)}),
    )

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        projetos = Projeto.objects.filter(
            id__in=Participacao.objects.filter(vinculo_pessoa=self.request.user.get_vinculo(), responsavel=True).values_list('projeto', flat=True)
        )

        self.fields['projeto'] = forms.ChainedModelChoiceField(
            projetos, label='Projeto:', empty_label='Selecione o Edital', required=True, obj_label='titulo', form_filters=[('edital', 'edital')]
        )
        self.fields['edital'].queryset = Edital.objects.filter(id__in=projetos.values_list('edital', flat=True))
        if self.edital.termo_compromisso_coordenador:
            self.fields['termo_compromisso_coordenador'].initial = self.edital.termo_compromisso_coordenador
            self.fields['termo_compromisso_coordenador'].widget.attrs['readonly'] = True
            self.fieldsets = (
                ('Selecione o Projeto a Ser Clonado', {'fields': ('edital', 'projeto')}),
                (
                    'Selecione os Dados a Serem Clonados',
                    {'fields': ('clona_caracterizacao', 'clona_equipe', 'clona_atividade', 'clona_memoria_calculo', 'clona_desembolso')},
                ),
                ('Informe o Período do Novo Projeto', {'fields': (('data_inicio', 'data_fim'),)}),
                (
                    'Termo de Compromisso',
                    {
                        'fields': (
                            ('termo_compromisso_coordenador',),
                            ('aceita_termo'),
                        )
                    },
                ),
            )
        else:
            del self.fields['termo_compromisso_coordenador']
            del self.fields['aceita_termo']

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
        fields = ('data_movimentacao', 'data_movimentacao_saida', 'vinculo', 'carga_horaria', 'obs', 'ativo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['data_movimentacao'].label = 'Data de Início'
        self.fields['data_movimentacao_saida'].label = 'Data de Término'
        self.fields['obs'].label = 'Observações'
        self.fields['vinculo'].label = 'Bolsista'
        self.fields['obs'].required = False


class NucleoExtensaoForm(forms.ModelFormPlus):
    uo = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo().all(), label='Campus', required=True)
    area_atuacao = forms.CharFieldPlus(label='Área de Atuação', widget=forms.Textarea())

    class Meta:
        model = NucleoExtensao
        fields = ('uo', 'nome', 'coordenador', 'area_atuacao', 'descricao_atividades', 'horario_funcionamento', 'contato', 'ativo')


class RelatorioCaracterizacaoBeneficiariosForm(forms.FormPlus):
    METHOD = 'GET'
    PROJETOS_EM_EXECUCAO = 'Projetos em Execução'
    PROJETOS_CONCLUIDOS = 'Projetos Concluídos'
    AVALIACAO_STATUS = (('', 'Todos'), (PROJETOS_EM_EXECUCAO, PROJETOS_EM_EXECUCAO), (PROJETOS_CONCLUIDOS, PROJETOS_CONCLUIDOS))

    campus = forms.ModelChoiceField(
        queryset=UnidadeOrganizacional.objects.uo(), empty_label='Selecione um Campus', label='Filtrar por Campus:', required=False
    )
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')

    edital = forms.ModelChoiceField(
        queryset=Edital.objects.filter(tipo_fomento=Edital.FOMENTO_INTERNO),
        empty_label='Selecione um Edital',
        label='Filtrar por Edital:',
        required=False,
    )

    tipo_edital = forms.ChoiceField(
        label='Tipo do Edital',
        choices=[('Todos', 'Todos'), ('Edital de Campus', 'Edital de Campus'), ('Edital Sistêmico', 'Edital Sistêmico')],
        required=False,
    )

    area_tematica = forms.ModelChoiceField(
        queryset=AreaTematica.objects, empty_label='Selecione uma área temática', label='Área Temática:', required=False
    )
    situacao = forms.ChoiceField(choices=AVALIACAO_STATUS, label='Filtrar por Situação', required=False)

    tipo_beneficiario = forms.ModelChoiceField(queryset=TipoBeneficiario.objects, label='Tipo de Beneficiário', required=False)
    coordenador = forms.ModelChoiceFieldPlus(queryset=Vinculo.objects, required=False, label='Coordenador')

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

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

        if self.request.user.groups.filter(name__in=['Coordenador de Extensão', 'Visualizador de Projetos do Campus']):
            self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo().filter(id=get_uo(self.request.user).id)
        self.fields['coordenador'].queryset = Vinculo.objects.filter(id__in=Projeto.objects.values_list('vinculo_coordenador', flat=True))


class ListaEditaisForm(forms.FormPlus):
    METHOD = 'GET'
    INSCRICAO = 'Em Inscrição'
    PRE_SELECAO = 'Em Pré-Seleção'
    SELECAO = 'Em Seleção'
    EXECUCAO = 'Em Execução'
    CONCLUIDO = 'Concluído'

    ano = forms.ChoiceField(choices=[], required=False, label='Ano')
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
    situacao = forms.ChoiceField(
        label='Situação da Validação',
        choices=(
            ('', 'Todas'),
            ('Validadas', 'Validadas'),
            ('Pendentes', 'Pendentes'),
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['participante'].queryset = Vinculo.objects.filter(id__in=self.projeto.participacao_set.values_list('vinculo_pessoa', flat=True))


class FiltrarListaFrequenciaForm(forms.FormPlus):
    METHOD = 'GET'
    data_inicio = forms.DateFieldPlus(label='Data de Início', required=False)
    data_termino = forms.DateFieldPlus(label='Data de Término', required=False)
    participante = forms.ModelChoiceFieldPlus(label='Participante', queryset=Vinculo.objects, required=False)
    situacao = forms.ChoiceField(
        label='Situação da Validação',
        choices=(
            ('', 'Todas'),
            ('Validadas', 'Validadas'),
            ('Pendentes', 'Pendentes'),
        ),
        required=False,
    )

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto', None)
        super().__init__(*args, **kwargs)
        self.fields['participante'].queryset = Vinculo.objects.filter(id__in=self.projeto.participacao_set.values_list('vinculo_pessoa', flat=True))


class FocoTecnologicoForm(forms.ModelFormPlus):
    class Meta:
        model = FocoTecnologico
        fields = (
            'descricao',
            'campi',
            'ativo',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campi'].queryset = UnidadeOrganizacional.objects.uo()


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


class AlterarChefiaParticipanteForm(forms.ModelFormPlus):
    responsavel_anuencia = forms.ModelChoiceField(
        label='Servidor', queryset=Servidor.objects, required=True, widget=AutocompleteWidget(search_fields=Servidor.SEARCH_FIELDS)
    )

    class Meta:
        model = Participacao
        fields = ('responsavel_anuencia',)


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


class IndicarAuxiliarForm(forms.ModelFormPlus):
    class Meta:
        model = Projeto
        fields = ('auxiliar',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['auxiliar'].queryset = Vinculo.objects.filter(
            id__in=Participacao.objects.filter(ativo=True, projeto=self.instance, responsavel=False).values_list('vinculo_pessoa', flat=True)
        )


class TermoParceriaAdesaoForm(forms.ModelFormPlus):
    class Meta:
        model = TermoParceriaAdesao
        fields = ('descricao', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields[
            'arquivo'
        ].help_text = 'Insira um comprovante de que existe uma demanda interessada no projeto. Exemplo: email, ofício, termo de adesão, acordo de cooperação, etc'
        self.fields['arquivo'].label = 'Comprovante de Parceria/Adesão'


class TermoParceriaAdesaoInlineFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        for form in self.extra_forms:
            if form.cleaned_data:
                descricao = form.cleaned_data.get('descricao')
                arquivo = form.cleaned_data.get('arquivo')
                if not arquivo:
                    form.add_error('arquivo', 'Informe o arquivo.')
                if not descricao:
                    form.add_error('descricao', 'Informe a descrição.')


class MembroNEPPForm(forms.ModelFormPlus):
    class Meta:
        model = MembroNEPP
        fields = ('membro',)


class FotoNEPPForm(forms.ModelFormPlus):
    class Meta:
        model = FotoNEPP
        fields = ('descricao', 'imagem')


class FiltrarNEPPForm(forms.FormPlus):
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)


class RelatorioFinanceiroExtensaoForm(forms.FormPlus):
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar por Ano:')
    edital = forms.ModelChoiceField(Edital.objects, required=True)
    recurso = ModelChoiceField(Recurso.objects, label='Recurso', required=True)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    projeto = forms.ChainedModelChoiceField(
        Projeto.objects.filter(aprovado=True),
        label='Projeto',
        empty_label='Selecione o Edital',
        required=False,
        obj_label='titulo',
        form_filters=[('edital', 'edital')],
    )
    area_conhecimento = forms.ModelChoiceField(AreaConhecimento.objects, label='Área do Conhecimento', required=False)
    area_tematica = forms.ModelChoiceField(label='Área Temática:', required=False, queryset=AreaTematica.objects.order_by('descricao'))
    tema = forms.ChainedModelChoiceField(
        Tema.objects.order_by('descricao'),
        label='Tema:',
        empty_label='Selecione a Área Temática',
        required=False,
        obj_label='descricao',
        form_filters=[('area_tematica', 'areatematica')],
    )

    METHOD = 'GET'

    class Media:
        js = ['/static/projetos/js/relatoriofinanceiroform.js']

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital')
        self.ano = kwargs.pop('ano')
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
        if self.edital:
            self.fields['recurso'].queryset = Recurso.objects.filter(edital=self.edital)
        if self.ano:
            self.fields['edital'].queryset = Edital.objects.filter(inicio_inscricoes__year=self.ano)


class AdicionarAlunosEmLoteForm(FormWizardPlus):
    from edu.models import Diario

    diario = forms.ModelChoiceFieldPlus(label='Diário', queryset=Diario.objects)
    alunos = forms.MultipleModelChoiceFieldPlus(label='Alunos', queryset=Aluno.objects, widget=FilteredSelectMultiplePlus('', True))
    vinculo = forms.ChoiceField(label='Bolsista', required=True, choices=TipoVinculo.TIPOS)
    data = forms.DateFieldPlus(label='Data de Entrada', help_text='A data não pode ser maior do que hoje.')
    carga_horaria = forms.IntegerFieldPlus(label='Carga Horária', help_text='Carga horária semanal')
    integracao_curricular = forms.ChoiceField(
        label='São participantes de atividades da integração curricular da extensão?',
        choices=[(True, 'Sim')],
    )
    steps = (
        [('Selecionar diário', {'fields': ('diario',)})],
        [('Indicar Alunos', {'fields': ('alunos', 'vinculo', 'carga_horaria', 'data', 'integracao_curricular')})],
    )

    def __init__(self, *args, **kwargs):
        self.meus_diarios = kwargs.pop('meus_diarios')
        super().__init__(*args, **kwargs)
        self.fields['diario'].queryset = self.meus_diarios

    def next_step(self):
        if 'diario' in self.fields:
            diario = self.get_entered_data('diario')
            if 'alunos' in self.fields and diario:
                self.fields['alunos'].queryset = Aluno.objects.filter(
                    id__in=diario.get_alunos_ativos().values_list('matricula_periodo__aluno', flat=True)
                )


class EncerrarAlunosEmLoteForm(forms.FormPlus):
    participacoes = forms.MultipleModelChoiceFieldPlus(
        label='Participações', queryset=Participacao.objects, widget=FilteredSelectMultiplePlus('', True)
    )
    data = forms.DateFieldPlus(label='Data de Inativação')
    justificativa = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea())

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto')
        super().__init__(*args, **kwargs)
        self.fields['participacoes'].queryset = Participacao.objects.filter(
            projeto=self.projeto, ativo=True, responsavel=False, vinculo_pessoa__tipo_relacionamento__model='aluno'
        ).order_by('vinculo_pessoa__pessoa__nome')

    def clean(self):
        cleaned_data = super().clean()
        data_informada = self.cleaned_data.get('data')
        participacoes = self.cleaned_data.get('participacoes')
        if data_informada and data_informada > self.projeto.fim_execucao:
            raise forms.ValidationError('A data de inativação não pode ser após o fim do projeto.')
        if data_informada and participacoes:
            for participacao in participacoes:
                historicos = HistoricoEquipe.objects.filter(ativo=True, projeto=self.projeto, participante=participacao).order_by('-id')
                if historicos.exists():
                    ultimo_historico = historicos[0]
                    if ultimo_historico.data_movimentacao > data_informada:
                        raise forms.ValidationError(
                            f'A data de inativação não pode ser menor do que a data de início do vínculo atual do {participacao}.'
                        )
                data = data_informada
                if self.projeto.fim_execucao < data_informada:
                    data = self.projeto.fim_execucao
                tem_pendencia_frequencia = self.projeto.tem_frequencia_aluno_pendente(participacao=participacao, data=data)
                if tem_pendencia_frequencia:
                    self.add_error(
                        'participacoes', f'O participante {participacao} possui registro de frequência pendente: {tem_pendencia_frequencia}.'
                    )
                if (
                    HistoricoOrientacaoProjeto.objects.filter(orientador=participacao, data_inicio__gte=data_informada).exists()
                    or HistoricoOrientacaoProjeto.objects.filter(orientado=participacao, data_inicio__gte=data_informada).exists()
                ):
                    self.add_error(
                        'participacoes',
                        f'O participante {participacao} está vinculado à orientações com data de início maior do que a data informada.',
                    )

        return cleaned_data


class ClonarEditalForm(forms.FormPlus):
    titulo = forms.CharFieldPlus(label='Título')
    descricao = forms.CharFieldPlus(label='Descrição', widget=forms.Textarea())
    clona_anexos_edital = forms.BooleanField(label='Anexos do Edital', initial=True, required=False)
    clona_anexos_projetos = forms.BooleanField(label='Anexos dos Projetos', initial=True, required=False)
    clona_tema = forms.BooleanField(label='Temas', initial=True, required=False)
    clona_fontes_recursos = forms.BooleanField(label='Fontes de recursos', initial=True, required=False)
    clona_plano_oferta_campus = forms.BooleanField(label='Plano de Oferta por Campus', initial=True, required=False)
    clona_plano_oferta_tema = forms.BooleanField(label='Plano de Oferta por Tema', initial=True, required=False)
    clona_criterios_avaliacao = forms.BooleanField(label='Critérios de Avaliação da Qualificação do Projeto', initial=True, required=False)

    fieldsets = (
        (
            'Informe os dados do novo edital',
            {
                'fields': (
                    ('titulo'),
                    ('descricao'),
                )
            },
        ),
        (
            'Selecione os Dados a Serem Clonados',
            {
                'fields': (
                    'clona_anexos_edital',
                    'clona_anexos_projetos',
                    'clona_tema',
                    'clona_fontes_recursos',
                    'clona_plano_oferta_campus',
                    'clona_plano_oferta_tema',
                    'clona_criterios_avaliacao',
                )
            },
        ),
    )

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital')
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)

    def processar(self):
        return self.edital.clonar_edital(
            request=self.request,
            titulo=self.cleaned_data.get('titulo'),
            descricao=self.cleaned_data.get('descricao'),
            clona_anexos_edital=self.cleaned_data.get('clona_anexos_edital'),
            clona_anexos_projetos=self.cleaned_data.get('clona_anexos_projetos'),
            clona_tema=self.cleaned_data.get('clona_tema'),
            clona_fontes_recursos=self.cleaned_data.get('clona_fontes_recursos'),
            clona_plano_oferta_campus=self.cleaned_data.get('clona_plano_oferta_campus'),
            clona_plano_oferta_tema=self.cleaned_data.get('clona_plano_oferta_tema'),
            clona_criterios_avaliacao=self.cleaned_data.get('clona_criterios_avaliacao'),
        )


class ListaMensalBolsistaForm(forms.FormPlus):
    METHOD = 'GET'
    ano = forms.ModelChoiceField(queryset=Ano.objects, label='Informe o Ano')
    mes = forms.ChoiceField(
        label='Informe o Mês',
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
    )
    edital = forms.ModelChoiceFieldPlus(queryset=Edital.objects, widget=AutocompleteWidget(search_fields=Edital.SEARCH_FIELDS), required=False)


class OfertaProjetoEmLoteForm(forms.FormPlus):
    campi = forms.MultipleModelChoiceFieldPlus(
        label='Campi', queryset=UnidadeOrganizacional.objects.uo().all(), widget=FilteredSelectMultiplePlus('', True), required=True
    )
    qtd_aprovados = forms.IntegerFieldPlus(
        label='Pré-Selecionados', help_text='Informe quantos projetos poderão ser pré-aprovados pela Coordenação de extensão do Campus.'
    )
    qtd_selecionados = forms.IntegerFieldPlus(label='Selecionados')

    def __init__(self, *args, **kwargs):
        self.edital = kwargs.pop('edital', None)
        super().__init__(*args, **kwargs)
        if self.edital.tipo_edital == Edital.EXTENSAO_FLUXO_CONTINUO:
            self.fields[
                'qtd_selecionados'
            ].help_text = 'Informe quantos projetos serão selecionados pela Diretoria de extensão/Coordenação de extensão do Campus.'
        else:
            self.fields['qtd_selecionados'].help_text = 'Informe quantos projetos serão selecionados pela Pró-reitoria de Extensão.'

        if self.edital.forma_selecao == Edital.GRUPO:
            del self.fields['qtd_aprovados']
        if self.edital.forma_selecao != Edital.CAMPUS:
            del self.fields['qtd_selecionados']


class RelatorioAlunoPorProjetoForm(forms.FormPlus):
    ano = forms.ChoiceField(choices=[], required=True, label='Ano')
    campus = forms.ModelChoiceFieldPlus(UnidadeOrganizacional.objects.uo(), required=False, label='Campus')
    ordenacao = forms.ChoiceField(
        label='Ordenação',
        required=False,
        choices=(
            ('', '----------------'),
            ('1', 'Crescente'),
            ('2', 'Decrescente'),
        ),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
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


class EditarChExtensaoForm(forms.ModelFormPlus):
    ch_extensao = forms.IntegerField(
        label='Carga Horária de Extensão', required=True, help_text='Carga horária total destinada a atividade curricular de extensão'
    )

    class Meta:
        model = Participacao
        fields = ('ch_extensao',)

    def clean_ch_extensao(self):
        ch_extensao = self.cleaned_data.get('ch_extensao')
        AtividadeCurricularExtensao = apps.get_model('edu', 'AtividadeCurricularExtensao')
        from django.contrib.contenttypes.fields import ContentType

        content = ContentType.objects.get_for_model(type(self.instance))
        ace = (
            AtividadeCurricularExtensao.objects.filter(tipo_referencia=content, id_referencia=self.instance.id)
            .only('carga_horaria_vinculada')
            .first()
        )
        carga_horaria_vinculada = ace.get_carga_horaria_vinculada() if ace else 0
        if ch_extensao < carga_horaria_vinculada:
            raise forms.ValidationError(
                f'Este aluno possui {carga_horaria_vinculada} hora(s) vinculada(s) a atividades de extensão. Para encerrar a participação com CH menor será necessário desfazer os vínculos realizados.'
            )
        return ch_extensao


class IndefereAlteracaoDataForm(forms.FormPlus):
    justificativa_validacao = forms.CharFieldPlus(label='Justificativa', widget=forms.Textarea(), max_length=5000)


class RelatorioPareceresEmitidosForm(forms.FormPlus):
    ano = forms.ChoiceField(choices=[], required=False, label='Filtrar Editais por Ano:')
    edital = forms.ModelChoiceField(Edital.objects, required=False)
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    ano_inicial = forms.ChoiceField(choices=[], required=False, label='Ano inicial')
    ano_final = forms.ChoiceField(choices=[], required=False, label='Ano final')
    METHOD = 'GET'

    class Media:
        js = ['/static/projetos/js/meusprojetosform.js']

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
        self.fields['ano_inicial'].choices = ANO_CHOICES
        self.fields['ano_final'].choices = ANO_CHOICES


class RegistrosBolsistasForm(forms.FormPlus):
    query = forms.CharFieldPlus(label='Matrícula/Nome', required=False)
    campus = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    METHOD = 'GET'

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if 'ae' in settings.INSTALLED_APPS:
            from ae.models import CategoriaBolsa

            self.fields['categoria'] = forms.ModelChoiceFieldPlus(queryset=CategoriaBolsa.objects, label='Categoria', required=False)


class RegistrarOcorrenciaForm(forms.ModelFormPlus):
    class Meta:
        model = OcorrenciaProjeto
        fields = ('ocorrencia', 'anexo')


class AvaliarInteresseCusteioForm(forms.ModelFormPlus):
    aceito = forms.ChoiceField(
        label='Aceitar solicitação?',
        choices=[(None, '-------------'), (True, 'Sim'), (False, 'Não')],
    )

    class Meta:
        model = HistoricoInteresseCusteioProjeto
        fields = ('aceito', 'justificativa_avaliacao')


class OfertaProjetoGrupoForm(forms.ModelFormPlus):
    class Meta:
        model = OfertaProjetoPorGrupo
        fields = ('grupo', 'pre_selecionados', 'selecionados')


class ReprovarManualmenteForm(forms.ModelFormPlus):
    class Meta:
        model = Projeto
        fields = ('justificativa_reprovacao_manual',)


class InterporRecursoExtensaoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Submeter recurso'
    fieldsets = ()

    def __init__(self, *args, **kwargs):
        self.ids_avaliacoes = kwargs.pop('ids_avaliacoes')
        super().__init__(*args, **kwargs)
        for i in self.ids_avaliacoes:
            lista = []
            item = ItemAvaliacao.objects.get(id=i)
            self.fields[f'{item.id}'] = forms.CharField(
                label='Interpor recurso', required=True, widget=forms.Textarea(), initial=item.texto_recurso, max_length=10000
            )
            lista.append(f'{item.id}')
            self.fieldsets = (
                *self.fieldsets,
                (
                    f'Nº: {item.id}<br>Critério: {item.criterio_avaliacao}<br> Pontuação: {item.pontuacao}',
                    {'fields': lista},
                ),
            )


class AvaliarRecursosExtensaoForm(forms.FormPlus):
    edital = forms.ModelChoiceFieldPlus(
        queryset=Edital.objects.order_by('-inicio_inscricoes'), empty_label='Selecione um Edital', label='Edital', required=False
    )
    uo = forms.ModelChoiceField(UnidadeOrganizacional.objects.uo(), label='Campus', required=False)
    avaliador = forms.CharFieldPlus(label='Nome ou matrícula do avaliador', required=False)
    situacao = forms.ChoiceField(
        label='Situação', required=False, choices=[('', '--------------'), ('Todos', 'Todos'), ('Pendentes de avaliação', 'Pendentes de avaliação')]
    )

    def __init__(self, *args, **kwargs):
        self.eh_sistemico = kwargs.pop('eh_sistemico')
        super().__init__(*args, **kwargs)
        if self.eh_sistemico:
            self.fields['ver_todos'] = forms.BooleanField(label='Ver todos os registros', required=False)


class AvaliarRecursoExtensaoForm(forms.ModelFormPlus):
    nova_pontuacao = forms.ChoiceField(label='Pontuação final', required=True)

    class Meta:
        model = ItemAvaliacao
        fields = ('recurso_aceito', 'nova_pontuacao', 'resposta_recurso')

    class Media:
        js = ['/static/projetos/js/avaliarrecursoform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['nova_pontuacao'].widget.attrs.update(disabled='disabled')
        nota_choices = []
        maior_nota = (2 * self.instance.criterio_avaliacao.pontuacao_maxima) + 1
        notas = [x * 0.5 for x in range(int(maior_nota))]
        notas.sort(reverse=True)
        for nota in notas:
            nota_choices.append([str(nota), str(nota)])
        self.fields['nova_pontuacao'] = forms.ChoiceField(
            choices=nota_choices,
            label='Pontuação final',
            help_text=f'Pontuação Máxima: {format_(self.instance.criterio_avaliacao.pontuacao_maxima)}',
            initial=float(self.instance.pontuacao),
            required=False,
        )


class CriterioPreSelecaoForm(forms.ModelFormPlus):
    class Meta:
        model = CriterioPreSelecao
        fields = ('descricao', 'texto_ajuda')


class PreSelecaoForm(forms.FormPlus):
    url = forms.CharField(required=False, label='Url', widget=forms.HiddenInput())

    def __init__(self, *args, **kwargs):
        self.projeto = kwargs.pop('projeto')
        self.vinculo = kwargs.pop('vinculo')
        self.avaliacao = kwargs.pop('avaliacao', None)
        self.url = kwargs.pop('url')
        super().__init__(*args, **kwargs)
        self.fields['url'].initial = self.url
        if self.avaliacao:
            for item in self.avaliacao.itempreselecao_set.all():
                self.fields[str(item.criterio.pk)] = forms.ChoiceField(
                    choices=[
                        (None, '-------------'),
                        (True, 'Sim'),
                        (False, 'Não'),
                    ],
                    label=item.criterio.descricao,
                    initial=item.aprovado,
                    help_text=item.criterio.texto_ajuda,
                )
        else:
            for item in self.projeto.edital.criteriopreselecao_set.all():
                self.fields[str(item.pk)] = forms.ChoiceField(
                    choices=[
                        (None, '-------------'),
                        (True, 'Sim'),
                        (False, 'Não'),
                    ],
                    label=item.descricao,
                    help_text=item.texto_ajuda,
                )

        self.fields['parecer'] = forms.CharField(
            label='Parecer', widget=forms.Textarea(), required=True, initial=self.avaliacao and self.avaliacao.parecer or None
        )
        self.fields['pre_aprovado'] = forms.ChoiceField(
            choices=[
                (None, '-------------'),
                (True, 'Sim'),
                (False, 'Não'),
            ],
            label='Pré-selecionar este projeto?',
        )

    @transaction.atomic()
    def save(self):
        if not self.avaliacao:
            self.avaliacao = PreSelecao()
            self.avaliacao.projeto = self.projeto
            self.avaliacao.avaliador = self.vinculo
            self.avaliacao.save()

        for criterio in self.projeto.edital.criteriopreselecao_set.all():
            try:
                item = ItemPreSelecao.objects.get(avaliacao=self.avaliacao, criterio=criterio)
            except Exception:
                item = ItemPreSelecao()
                item.avaliacao = self.avaliacao
                item.criterio = criterio
            item.aprovado = self.cleaned_data.get(str(criterio.id), 0)
            item.save()
        self.avaliacao.parecer = self.cleaned_data['parecer']
        self.avaliacao.save()


class ArquivoInativacaoProjetoForm(forms.ModelFormPlus):
    class Meta:
        model = ArquivoInativacaoProjeto
        fields = ('descricao', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = True
        self.fields['arquivo'].required = True


class FinalizacaoSistemicaForm(forms.ModelFormPlus):
    class Meta:
        model = Projeto
        fields = ('motivo_finalizacao_sistemica',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['motivo_finalizacao_sistemica'].required = True
        self.fields['motivo_finalizacao_sistemica'].widget = forms.Textarea()


class ArquivoFinalizacaoProjetoForm(forms.ModelFormPlus):
    class Meta:
        model = ArquivoFinalizacaoProjeto
        fields = ('descricao', 'arquivo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['descricao'].required = True
        self.fields['arquivo'].required = True


class IndicarAvaliadorEmLoteForm(forms.FormPlus):
    vinculo = forms.ModelChoiceFieldPlus(queryset=Vinculo.objects, label='Avaliador', required=True)
    editais = forms.MultipleModelChoiceFieldPlus(queryset=Edital.objects, label='Editais', required=True)
    area_tematica = forms.ModelChoiceFieldPlus(AreaTematica.objects.order_by('descricao'), required=False, label='Área Temática dos projetos')

    def __init__(self, *args, **kwargs):
        self.request = kwargs.pop('request')
        super().__init__(*args, **kwargs)
        self.fields['vinculo'].queryset = Vinculo.objects.exclude(tipo_relacionamento__model='aluno').filter(
            id__in=AreaTematica.objects.all().values_list('vinculo', flat=True)
        )
        hoje = datetime.datetime.now()
        editais = Edital.objects.filter(divulgacao_selecao__gt=hoje) | Edital.objects.filter(
            tipo_edital=Edital.EXTENSAO_FLUXO_CONTINUO, exige_etapa_avaliacao=True, fim_inscricoes__gt=hoje
        )
        if not self.request.user.has_perm('projetos.pode_gerenciar_edital'):
            editais = editais.filter(campus_especifico=True, ofertaprojeto__uo=get_uo(self.request.user))
        self.fields['editais'].queryset = editais

    def clean(self):
        cleaned_data = super().clean()

        if self.cleaned_data.get('vinculo') and self.cleaned_data.get('editais'):
            proibidos = self.cleaned_data.get('editais').exclude(
                Q(
                    exige_comissao=True,
                    id__in=ComissaoEdital.objects.filter(vinculos_membros=self.cleaned_data.get('vinculo')).values_list('edital', flat=True),
                )
                | Q(exige_comissao=False)
            )
            if proibidos.exists():
                self.add_error('editais', f'O avaliador selecionado não pode avaliar projetos do edital: {proibidos[0].titulo}')

        return cleaned_data


class NovaMensagemForm(FormWizardPlus):
    tipo_destinatario = forms.ChoiceField(label='Tipo de destinatários', choices=(('', '------------------'), *Comunicador.DESTINARIOS))
    editais = forms.MultipleModelChoiceFieldPlus(label='Editais', queryset=Edital.objects, required=False)
    vinculos = forms.MultipleModelChoiceFieldPlus(label='Destinatários', required=True, queryset=Vinculo.objects)
    titulo = forms.CharFieldPlus(label='Título', required=True)
    conteudo = TinyMCEFormField(label='Conteúdo', required=True)
    steps = (
        [
            (
                'Selecionar tipo de destinatários',
                {
                    'fields': (
                        'tipo_destinatario',
                        'editais',
                    )
                },
            )
        ],
        [('Destinatários', {'fields': ('vinculos', 'titulo', 'conteudo')})],
    )

    class Media:
        js = ['/static/projetos/js/novamensagemform.js']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['editais'].queryset = Edital.objects.em_selecao()

    def next_step(self):
        if 'tipo_destinatario' in self.fields:
            tipo = self.get_entered_data('tipo_destinatario')
            if 'vinculos' in self.fields and tipo:
                if tipo == Comunicador.AVALIADORES:
                    editais = self.get_entered_data('editais', is_list=True)
                    if editais:
                        ids_avaliadores = AvaliadorIndicado.objects.filter(
                            rejeitado=False, projeto__edital__in=editais.values_list('id', flat=True)
                        ).values_list('vinculo', flat=True)
                        self.fields['vinculos'].queryset = Vinculo.objects.filter(id__in=ids_avaliadores)
                        self.fields['vinculos'].initial = ids_avaliadores
                elif tipo == Comunicador.COEX:
                    pids = UsuarioGrupo.objects.filter(group__name='Coordenador de Extensão').values_list('user__id', flat=True)
                    queryset = Vinculo.objects.filter(user__in=pids)
                    self.fields['vinculos'].queryset = queryset
                    self.fields['vinculos'].initial = queryset.values_list('id', flat=True)

    def clean(self):
        cleaned_data = super().clean()

        if (
            self.cleaned_data.get('tipo_destinatario')
            and self.cleaned_data.get('tipo_destinatario') == Comunicador.AVALIADORES
            and not self.cleaned_data.get('editais')
        ):
            self.add_error('editais', 'Informe os editais cujos avaliadores serão notificados.')

        return cleaned_data
