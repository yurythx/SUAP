import datetime

from django.contrib.contenttypes.models import ContentType
from django.db.models import Q

from catalogo_provedor_servico.models import Servico, ServicoEquipe, ServicoGerenteEquipeLocal, Solicitacao
from comum.models import Ano, Vinculo
from djtools import forms
from djtools.forms.widgets import AutocompleteWidget
from documento_eletronico.models import Documento, TipoDocumento
from edu.forms import EfetuarMatriculaForm
from edu.models import Aluno, Convenio, FormaIngresso, LinhaPesquisa, MatrizCurso, Polo, Professor, Turno
from processo_eletronico.forms import FinalizarRequerimentoForm
from processo_seletivo.models import CandidatoVaga
from rh.models import Papel, Setor, UnidadeOrganizacional


class ConfiguracaoForm(forms.FormPlus):
    url_catalogo_digital = forms.URLField(label='URL do Balcão Digital', required=False)
    request_timeout_gov_br = forms.IntegerField(label='Request Timeout Para Consumir APIs GOV.BR (segundos)', required=False)
    orgao_id_portal_servicos_govbr = forms.IntegerField(label='ID do Órgão no Serviços GOV.BR', required=False)

    # Códigos para Implementação Default
    codigo_segunda_via_diploma = forms.IntegerField(
        label='Código do Serviço de Emissão da Segunda Via do Diploma',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    desabilitar_execucao_segunda_via_diploma = forms.BooleanField(
        label='Desabilitar a execução do serviço de Emissão da Segunda Via do Diploma',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_matricula_tecnico = forms.IntegerField(
        label='Código do Serviço de Matrícula de Curso Técnico', help_text='Esta configuração só é utilizada na implementação default', required=False
    )
    codigo_matricula_superior = forms.IntegerField(
        label='Código do Serviço de Matrícula de Curso Superior',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_matricula_pos_graduacao = forms.IntegerField(
        label='Código do Serviço de Matrícula de Curso de Pós-Graduação',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_matricula_ead = forms.IntegerField(
        label='Código do Serviço de Matrícula de Curso EAD', help_text='Esta configuração só é utilizada na implementação default', required=False
    )
    codigo_matricula_fic = forms.IntegerField(
        label='Código do Serviço de Matrícula de Curso FIC - Presencial',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_protocolar_documento = forms.IntegerField(
        label='Código do Serviço de Protocolar Documento', help_text='Esta configuração só é utilizada na implementação default', required=False
    )
    desabilitar_execucao_protocolar_documento = forms.BooleanField(
        label='Desabilitar a execução do serviço de Protocolar Documento',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_certificado_encceja = forms.IntegerField(
        label='Código do Serviço de Solicitar Certificado do Encceja',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_certificacao_enem = forms.IntegerField(
        label='Código do Serviço da Certificação Enem',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    codigo_solicitacao_visita = forms.IntegerField(
        label='Código do Serviço de Solicitar Visita a Unidade/Campus',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )
    id_campus_ead = forms.IntegerField(
        label='ID do Campus EAD',
        help_text='Esta configuração só é utilizada na implementação default',
        required=False,
    )


# Formulário usado somente em ambiente de desenvolvimento (DEBUG = TRUE)
class ApagarAtendimentoForm(forms.FormPlus):
    SUBMIT_LABEL = 'Apagar'
    solicitacao = forms.ModelChoiceFieldPlus(Solicitacao.objects.all(), label='Solicitação', required=True)


class GerenciarEquipeForm(forms.FormPlus):
    SUBMIT_LABEL = 'Salvar'
    solicitacao = forms.ModelChoiceFieldPlus(Solicitacao.objects.all(), label='Solicitação', required=True)

    class Meta:
        model = ServicoGerenteEquipeLocal
        fields = ()


class CatalogoEfetuarMatriculaForm(EfetuarMatriculaForm):
    declaracao_etnia = forms.BooleanField(label='Declaração de Etnia', required=True)
    declaracao_didatica = forms.BooleanField(label='Declaração Didática', required=True)
    declaracao_legais = forms.BooleanField(label='Declaração Legal', required=True)
    declaracao_veracidade = forms.BooleanField(label='Declaração de Veracidade', required=True)
    declaracao_conclusao = forms.BooleanField(label='Declaração de Conclusão', required=True)


class SolicitacaoMatriculaForm(forms.FormPlus):
    cpf = forms.BrCpfField(required=False, widget=forms.TextInput(attrs={'readonly': 'True'}))
    nome = forms.CharFieldPlus(required=True, label='Nome', width=500, widget=forms.TextInput(attrs={'readonly': 'True'}))

    # dados da matrícula
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), required=True, label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(required=True, label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    turno = forms.ModelChoiceField(Turno.objects, required=True, label='Turno')
    polo = forms.ModelChoiceField(Polo.objects, required=False, label='Polo EAD', help_text='Apenas para o Turno EAD.')
    forma_ingresso = forms.ModelChoiceField(FormaIngresso.objects, required=True, label='Forma de Ingresso')
    cota_sistec = forms.ChoiceField(label='Cota SISTEC', choices=Aluno.COTA_SISTEC_CHOICES, required=False, widget=forms.HiddenInput())
    cota_mec = forms.ChoiceField(label='Cota MEC', choices=Aluno.COTA_MEC_CHOICES, required=False, widget=forms.HiddenInput())
    possui_convenio = forms.BooleanRequiredField(label='Possui Convênio')
    convenio = forms.ModelChoiceField(Convenio.objects, required=False, label='Convênio')
    data_conclusao_intercambio = forms.DateFieldPlus(
        required=False,
        label='Conclusão do Intercâmbio',
        help_text='Preencha esse campo com a data de conclusão do intercâmbio caso se trate de um aluno de intercâmbio',
    )
    matriz_curso = forms.ModelChoiceFieldPlus(MatrizCurso.objects, required=True, label='Matriz/Curso')
    linha_pesquisa = forms.ModelChoiceFieldPlus(
        LinhaPesquisa.objects,
        required=False,
        label='Linha de Pesquisa',
        help_text='Obrigatório para alunos de Mestrado e Doutourado. Caso não saiba, escreva "A definir".',
    )
    aluno_especial = forms.BooleanField(
        required=False, label='Aluno Especial?', help_text='Marque essa opção caso se trate de um aluno especial em curso de Pós-Graduação'
    )
    possui_orientador = forms.BooleanRequiredField(label='Possui Orientador')
    orientador = forms.ModelChoiceField(
        queryset=Professor.objects,
        widget=AutocompleteWidget(search_fields=Professor.SEARCH_FIELDS),
        label='Orientador',
        required=False,
        help_text='Serão listados docentes cadastrados no Corpo Docente do programa de Pós-Graduação',
    )
    coorientadores = forms.MultipleModelChoiceFieldPlus(
        Vinculo.objects.funcionarios(),
        label='Coorientadores',
        required=False,
    )
    numero_pasta = forms.CharFieldPlus(label='Número da Pasta', required=False, max_length=255)

    observacao_matricula = forms.CharField(widget=forms.Textarea(), required=False, label='Observação')

    def __init__(self, *args, **kwargs):
        self.candidato_vaga = kwargs.pop('candidato_vaga')
        super().__init__(*args, **kwargs)
        if self.candidato_vaga:
            if 'forma_ingresso' in self.initial:
                self.fields['forma_ingresso'].queryset = FormaIngresso.objects.filter(pk=self.candidato_vaga.oferta_vaga.lista.forma_ingresso_id)
                self.fields['forma_ingresso'].initial = self.candidato_vaga.oferta_vaga.lista.forma_ingresso_id
            else:
                self.fields['forma_ingresso'].queryset = FormaIngresso.objects.none()

            if 'ano_letivo' in self.initial:
                self.fields['ano_letivo'].queryset = self.fields['ano_letivo'].queryset.filter(pk=self.candidato_vaga.candidato.edital.ano_id)

            if 'periodo_letivo' in self.initial:
                self.fields['periodo_letivo'].choices = [
                    [self.candidato_vaga.candidato.edital.semestre, self.candidato_vaga.candidato.edital.semestre]
                ]

            if 'matriz_curso' in self.initial:
                self.fields['matriz_curso'].queryset = MatrizCurso.locals.filter(matriz__ativo=True)
                if self.candidato_vaga:
                    self.fields['matriz_curso'].queryset = self.fields['matriz_curso'].queryset.filter(
                        curso_campus=self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
                    )

            if self.candidato_vaga.oferta_vaga.oferta_vaga_curso.campus_polo:
                self.fields[
                    'polo'
                ].help_text = f'Apenas para o Turno EAD. O candidato escolheu o polo {self.candidato_vaga.oferta_vaga.oferta_vaga_curso.campus_polo}'


class EmissaoDiplomaForm(FinalizarRequerimentoForm):
    pass


class IndeferirSolicitacaoForm(forms.ModelFormPlus):
    detalhamento = forms.CharFieldPlus(max_length=1000, required=True, label='Detalhamento de Status', widget=forms.Textarea())

    class Meta:
        model = Solicitacao
        fields = ()

    def __init__(self, *args, **kwargs):
        self.candidato_vaga = None
        super().__init__(*args, **kwargs)
        etapa = self.instance.solicitacaoetapa_set.get(numero_etapa=1).get_dados_as_json()
        for dado in etapa['formulario']:
            if dado['name'] == 'candidato_vaga':
                self.candidato_vaga = CandidatoVaga.objects.get(pk=dado['value'])
                break

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.is_cota_etnica()
            and self.candidato_vaga.candidato.aprovado_heteroidentificacao is not True
        ):
            self.fields['devido_heteroidentificacao'] = forms.ChoiceField(
                label='Devido a reprovação na hetero-identificação?', choices=[['', '----------'], ['N', 'Não'], ['S', 'Sim']]
            )

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.is_cota_quilombola()
            and self.candidato_vaga.candidato.aprovado_quilombola is not True
        ):
            self.fields['devido_quilombola'] = forms.ChoiceField(
                label='Devido a reprovação na cota de quilombola?', choices=[['', '----------'], ['N', 'Não'], ['S', 'Sim']]
            )

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.is_cota_baixa_renda()
            and self.candidato_vaga.candidato.aprovado_baixa_renda is not True
        ):
            self.fields['devido_baixa_renda'] = forms.ChoiceField(
                label='Devido a reprovação na cota de baixa renda?', choices=[['', '----------'], ['N', 'Não'], ['S', 'Sim']]
            )

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.is_cota_escola_publica()
            and self.candidato_vaga.candidato.aprovado_escola_publica is not True
        ):
            self.fields['devido_escola_publica'] = forms.ChoiceField(
                label='Devido a reprovação na cota de escola pública?', choices=[['', '----------'], ['N', 'Não'], ['S', 'Sim']]
            )

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.is_cota_deficiencia()
            and self.candidato_vaga.candidato.aprovado_deficiencia is not True
        ):
            self.fields['devido_deficiencia'] = forms.ChoiceField(
                label='Devido a reprovação na cota de deficiencia?', choices=[['', '----------'], ['N', 'Não'], ['S', 'Sim']]
            )

    def save(self, *args, **kwargs):
        detalhamento = self.cleaned_data['detalhamento']
        self.instance.status_detalhamento = detalhamento
        self.instance.status = Solicitacao.STATUS_NAO_ATENDIDO
        super().save(*args, **kwargs)

        if self.candidato_vaga:
            devido_heteroidentificacao = self.cleaned_data.get('devido_heteroidentificacao') == 'S'
            devido_quilombola = self.cleaned_data.get('devido_quilombola') == 'S'
            devido_baixa_renda = self.cleaned_data.get('devido_baixa_renda') == 'S'
            devido_escola_publica = self.cleaned_data.get('devido_escola_publica') == 'S'
            devido_deficiencia = self.cleaned_data.get('devido_deficiencia') == 'S'
            self.candidato_vaga.registrar_inaptidao(
                devido_heteroidentificacao, devido_quilombola, devido_baixa_renda, devido_escola_publica, devido_deficiencia
            )


class RetornarParaAnaliseSolicitacaoForm(forms.ModelFormPlus):
    detalhamento = forms.CharFieldPlus(required=True, label='Detalhamento de Status', widget=forms.Textarea())

    class Meta:
        model = Solicitacao
        fields = ()

    def save(self, *args, **kwargs):
        detalhamento = self.cleaned_data['detalhamento']
        self.instance.status_detalhamento = detalhamento
        self.instance.status = Solicitacao.STATUS_EM_ANALISE
        super().save(*args, **kwargs)

        etapa = self.instance.solicitacaoetapa_set.get(numero_etapa=1).get_dados_as_json()
        candidato_vaga = None

        for dado in etapa['formulario']:
            if dado['name'] == 'candidato_vaga':
                candidato_vaga = CandidatoVaga.objects.get(pk=dado['value'])
                break
        if candidato_vaga:
            candidato_vaga.retornar_para_apto()


class DashboradFiltroForm(forms.FormPlus):
    METHOD = 'GET'

    servico = forms.ModelChoiceFieldPlus(label='Serviço', queryset=Servico.objects)
    uo = forms.ModelChoiceFieldPlus(label='Unidade Organizacional', queryset=UnidadeOrganizacional.objects.uo(), required=False)
    data_inicio = forms.DateFieldPlus(label='Data Inicial')
    data_fim = forms.DateFieldPlus(label='Data Final')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        hoje = datetime.date.today()
        self.fields['data_inicio'].initial = hoje
        self.fields['data_fim'].initial = hoje


# TODO: Ver se é viável unir esse form com AtribuirAtendimentoForm. Eles tem a mesma ideia, só que o primeiro é voltado
# para o procedimento em lote e o outro o procediumento normal em cima de uma solicitação.
class AtribuirAvaliadorForm(forms.FormPlus):
    action = forms.CharField(widget=forms.MultipleHiddenInput)
    _selected_action = forms.CharField(widget=forms.MultipleHiddenInput)
    avaliador = forms.ModelChoiceFieldPlus(label='Avaliador', queryset=Vinculo.objects)
    instrucao = forms.CharFieldPlus(label='Instrução', max_length=1000, required=False)

    def __init__(self, *args, **kwargs):
        queryset = kwargs.pop('queryset')
        super().__init__(*args, **kwargs)
        servicos = Servico.objects.filter(pk__in=queryset.values('servico').distinct())

        # Buscando as pessoas que podem assumir a solicitação em questão. Obs: Tive que usar essa estratégia de montar
        # uma lista de IDs de pessoas físicas uma vez que não é possível de ser feito um filtro por UO na entidade PessoaFisica.
        servico_equipe_ids = ServicoEquipe.objects.filter(servico__in=servicos, campus=self.request.user.get_vinculo().setor.uo).values_list(
            'vinculo_id', flat=True
        )
        vinculos_habilitados = Vinculo.objects.filter(id__in=servico_equipe_ids)
        self.fields['avaliador'].queryset = vinculos_habilitados


# TODO: Rever nomes. Se a atividade é de Avaliacao de Solicitação, o nome mais apropriado é
# definir as classes usando a palavra Avaliador ou Avaliacao. ServicoEquipe, Atendimento, fica meio confuso.
class AtribuirAtendimentoForm(forms.ModelFormPlus):
    class Meta:
        model = Solicitacao
        fields = (
            'vinculo_responsavel',
            'instrucao',
        )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.initial['vinculo_responsavel'] = None
        self.initial['instrucao'] = None

        # Buscando as pessoas que podem assumir a solicitação em questão. Obs: Tive que usar essa estratégia de montar
        # uma lista de IDs de pessoas físicas uma vez que não é possível de ser feito um filtro por UO na entidade PessoaFisica.
        servico_equipe_ids = ServicoEquipe.objects.filter(servico=self.instance.servico, campus=self.instance.uo).values_list('vinculo_id', flat=True)
        vinculos_habilitados = Vinculo.objects.filter(id__in=servico_equipe_ids)
        if self.instance.vinculo_responsavel:
            vinculos_habilitados = vinculos_habilitados.exclude(id=self.instance.vinculo_responsavel.id)
        self.fields['vinculo_responsavel'].queryset = vinculos_habilitados

    def _atribuir_responsavel(self):
        vinculo_atribuinte = self.request.user.get_vinculo()
        vinculo_responsavel = self.cleaned_data.get('vinculo_responsavel')
        self.instance.atribuir_responsavel(
            vinculo_atribuinte=vinculo_atribuinte,
            vinculo_responsavel=vinculo_responsavel,
            data_associacao_responsavel=datetime.datetime.now(),
            instrucao=self.cleaned_data.get('instrucao'),
        )

    def clean(self):
        self._atribuir_responsavel()
        return super().clean()

    def save(self, *args, **kwargs):
        self._atribuir_responsavel()
        super().save(*args, **kwargs)


class PeticaoEletronicaForm(forms.FormPlus):
    senha = forms.PasswordField()
    papel = forms.ModelChoiceField(label='Perfil', queryset=Papel.objects.none())

    # Dados para encaminhar para setor
    tipo_busca_setor = forms.ChoiceField(widget=forms.RadioSelect(), required=True, label='Destino do primeiro trâmite')
    destinatario_setor_autocompletar = forms.ModelChoiceField(
        label='Setor de Destino', queryset=Setor.objects, required=True, widget=AutocompleteWidget()
    )

    despacho = forms.CharField(label='Despacho', required=False, widget=forms.Textarea())

    def is_tipo_busca_setor_autocompletar(self):
        return self.cleaned_data.get('tipo_busca_setor') == 'autocompletar'

    def get_destino(self):
        if self.is_tipo_busca_setor_autocompletar():
            return self.cleaned_data.get('destinatario_setor_autocompletar', None)

    def __init__(self, *args, **kwargs):
        anexos = kwargs.pop('anexos')
        campus_id = kwargs.pop('campus_id')
        campus = UnidadeOrganizacional.objects.get(id=campus_id)

        super().__init__(*args, **kwargs)

        self.fields['papel'].queryset = self.request.user.get_relacionamento().papeis_ativos

        TIPO_BUSCA_SETOR_CHOICE = (('autocompletar', 'Buscar usando o Autocompletar'),)
        self.fields['tipo_busca_setor'].choices = TIPO_BUSCA_SETOR_CHOICE
        self.fields['destinatario_setor_autocompletar'].label = f'Setor de Destino (Campus {campus})'
        self.fields['destinatario_setor_autocompletar'].queryset = Setor.objects.suap_ativos().filter(uo__id=campus_id)

        self.fieldsets = ()
        count = 1
        for anexo in anexos:
            self.fields[anexo['name']] = forms.CharFieldPlus(label='Descrição', max_length=510, initial=anexo['descricao'])
            self.fields[anexo['name']].widget.attrs['readonly'] = True
            self.fields[anexo['name'] + '_tipo'] = forms.ModelChoiceField(TipoDocumento.ativos, label='Tipo do Documento', required=True)
            self.fields[anexo['name'] + '_nivel_acesso'] = forms.ChoiceField(
                choices=((None, '---------'), (Documento.NIVEL_ACESSO_RESTRITO, 'Restrito'), (Documento.NIVEL_ACESSO_PUBLICO, 'Público')),
                label='Nível de Acesso',
                required=True,
            )
            self.fieldsets += (
                (
                    f'Documento {count}',
                    {
                        'fields': (
                            anexo['name'],
                            anexo['name'] + '_tipo',
                            anexo['name'] + '_nivel_acesso',
                        )
                    },
                ),
            )
            count += 1

        self.fieldsets += (
            (
                'Setor de Destino',
                {
                    'fields': (
                        'despacho',
                        'tipo_busca_setor',
                        'destinatario_setor_autocompletar',
                        'destinatario_setor_arvore',
                    )
                },
            ),
        )
        self.fieldsets += (
            (
                'Assinatura',
                {
                    'fields': (
                        'papel',
                        'senha',
                    )
                },
            ),
        )

    class Media:
        js = ('/static/processo_eletronico/js/RequerimentoFormCadastrar.js',)

    def clean_papel(self):
        papel = self.cleaned_data.get('papel', None)

        relacionamento = self.request.user.get_relacionamento()

        if not papel or papel not in relacionamento.papeis_ativos:
            self.add_error('papel', 'Papel inválido.')
        return self.cleaned_data.get('papel')


class ServicoGerenteEquipeLocalForm(forms.ModelFormPlus):
    class Meta:
        model = ServicoGerenteEquipeLocal
        fields = ('servico', 'campus', 'vinculo')

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['campus'].queryset = UnidadeOrganizacional.objects.uo()


def ServicoGerenteFormFactory(servico):
    class ServicoGerenteForm(forms.ModelFormPlus):
        class Meta:
            model = Servico
            fields = ('titulo',)

        def __init__(self, *args, **kwargs):
            self.instance = servico
            super().__init__(*args, **kwargs)
            self.fields['titulo'].widget = forms.TextInput(attrs={'readonly': 'readonly'})

    return ServicoGerenteForm


def AdicionarUsuarioEquipeFormFactory(usuario, uo):
    class AdicionarUsuarioEquipeForm(forms.FormPlus):
        vinculo = forms.MultipleModelChoiceFieldPlus(
            queryset=Vinculo.objects,
            label='Usuários',
            help_text='Informe parte do Nome ou Matrícula ou CPF ou E-mail Institucional',
        )

        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            self.fields['vinculo'].queryset = Vinculo.objects.filter(
                tipo_relacionamento_id__in=ContentType.objects.filter(Q(Vinculo.SERVIDOR | Vinculo.PRESTADOR)),
                user__is_active=True,
            )

    return AdicionarUsuarioEquipeForm


class TestarDisponibilidadeForm(forms.FormPlus):
    METHOD = 'GET'
    cpf = forms.CharFieldPlus(required=False, label='CPF')
