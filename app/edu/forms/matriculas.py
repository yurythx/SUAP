import datetime
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.db import transaction

from comum.models import Ano, Configuracao, PovoIndigena, Raca, Vinculo
from convenios.models import Convenio as ParceriaInternacional
from djtools import forms
from djtools.forms.widgets import (
    AutocompleteWidget,
    PhotoCapturePortraitInput,
)
from djtools.forms.wizard import FormWizardPlus
from djtools.templatetags.filters import in_group
from djtools.utils import eh_nome_completo, running_tests
from edu.models import (
    PERIODO_LETIVO_CHOICES,
    Aluno,
    Cartorio,
    Cidade,
    ConfiguracaoPedidoMatricula,
    Convenio,
    CursoCampus,
    Deficiencia,
    Diario,
    Diretoria,
    Estado,
    FormaIngresso,
    HistoricoSituacaoMatricula,
    HistoricoSituacaoMatriculaPeriodo,
    LinhaPesquisa,
    MatriculaDiario,
    MatriculaPeriodo,
    MatrizCurso,
    Modalidade,
    NivelEnsino,
    Observacao,
    OrgaoEmissorRg,
    Pais,
    Polo,
    Professor,
    SequencialMatricula,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    TipoNEE,
    Turma,
    Turno,
)
from processo_seletivo.models import CandidatoVaga, Edital
from rh.deduplicacao.entrada import DocumentoDeOutraPessoa, Politica, verificar_documento
from rh.deduplicacao.paises import pais_do_aluno
from rh.models import PessoaFisica


class ReplicacaoConfiguracaoPedidoMatriculaForm(forms.FormPlus):
    SUBMIT_LABEL = 'Replicar'
    descricao = forms.CharFieldPlus(required=True, label='Descrição', width=500)
    data_inicio = forms.DateFieldPlus(required=True, label='Data de Início')
    data_fim = forms.DateFieldPlus(required=True, label='Data do Fim')

    impedir_troca_turma = forms.BooleanField(
        label='Impedir troca de turma',
        required=False,
        help_text='Marque essa opção caso deseje impedir que alunos do regime seriado possam trocar de turma dentro do seu respectivo turno.',
    )
    restringir_por_curso = forms.BooleanField(
        label='Restringir por curso',
        required=False,
        help_text='Marque essa opção caso deseje impedir que os alunos se matriculem em disciplinas de outros cursos.',
    )
    requer_atualizacao_dados = forms.BooleanField(
        label='Requer atualização do cadastro',
        required=False,
        help_text='Marque essa opção caso deseje que o aluno atualize seus dados cadastrais no ato do pedido de matrícula.',
    )
    requer_atualizacao_caracterizacao = forms.BooleanField(
        label='Requer atualização da caracterização social',
        required=False,
        help_text='Marque essa opção caso deseje que o aluno atualize seus dados da caracterização social no ato do pedido de matrícula.',
    )

    permite_cancelamento_matricula_diario = forms.BooleanField(
        label='Permite o cancelamento de matrículas em diário já deferidas',
        required=False,
        help_text='Marque essa opção caso o aluno possa solicitar o cancelamento de matrículas em diários nos quais ele já se encontra matriculado.',
    )

    permite_requerimento_matricula_diario = forms.BooleanField(
        label='Permite o requerimento de matrículas em diário extracurriculares',
        required=False,
        help_text='Marque essa opção caso o aluno possa requerer matrícula em diários de disciplinas extracurriculares.',
    )

    permite_requerimento_quebra_de_requisito = forms.BooleanField(
        label='Permitir o requerimento de matrículas com quebra de requisitos',
        required=False,
        help_text='Marque essa opção caso o aluno possa solicitar o cancelamento de matrículas em diários nos quais ele já se encontra matriculado.',
    )

    permite_requerimento_ultrapassar_ch_maxima = forms.BooleanField(
        label='Permitir o requerimento de matrículas que ultrapassem a carga horária máxima do aluno no período',
        required=False,
        help_text='Marque essa opção caso o aluno possa requerer matrícula em diários mesmo quando a inclusão da disciplina exceda a carga horária máxima permitida para o aluno no período (requer aprovação do coordenador do curso).',
    )

    data_limite_requerimentos_especiais = forms.DateFieldPlus(
        label='Data limite para submissão de requerimentos especiais pelo aluno', required=False
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not settings.NOTA_DECIMAL:
            self.fields['permite_cancelamento_matricula_diario'].widget = forms.HiddenInput()

    def clean_data_fim(self):
        if 'data_inicio' in self.cleaned_data and 'data_fim' in self.cleaned_data:
            if self.cleaned_data['data_fim'] < self.cleaned_data['data_inicio']:
                raise ValidationError('A data de fim deve ser maior que a data de início.')
        return self.cleaned_data['data_fim']

    def clean_data_limite_requerimentos_especiais(self):
        permite_quebra_requisito = self.cleaned_data.get('permite_requerimento_quebra_de_requisito')
        permite_ultrapassar_ch_maxima = self.cleaned_data.get('permite_requerimento_ultrapassar_ch_maxima')
        data_limite_requerimentos_especiais = self.cleaned_data.get('data_limite_requerimentos_especiais')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        if permite_quebra_requisito or permite_ultrapassar_ch_maxima:
            if not data_limite_requerimentos_especiais:
                raise ValidationError(
                    'A data limite para submissão pelo aluno é obrigatória quando a quebra de requisito ou o aumento de carga horária estiverem habilitados.'
                )

            if data_inicio and data_fim and not (data_inicio <= data_limite_requerimentos_especiais <= data_fim):
                raise ValidationError('A data limite para submissão pelo aluno deve estar entre a data de início e a data de fim.')
        return data_limite_requerimentos_especiais

    def processar(self, configuracao_pedido_matricula):
        configuracao_pedido_matricula.replicar(
            self.cleaned_data['descricao'],
            self.cleaned_data['data_inicio'],
            self.cleaned_data['data_fim'],
            self.cleaned_data['impedir_troca_turma'],
            self.cleaned_data['restringir_por_curso'],
            self.cleaned_data['requer_atualizacao_dados'],
            self.cleaned_data['requer_atualizacao_caracterizacao'],
            self.cleaned_data['permite_cancelamento_matricula_diario'],
            self.cleaned_data['permite_requerimento_matricula_diario'],
            self.cleaned_data['permite_requerimento_quebra_de_requisito'],
            self.cleaned_data['permite_requerimento_ultrapassar_ch_maxima'],
            self.cleaned_data['data_limite_requerimentos_especiais'],
        )
        return configuracao_pedido_matricula


class MatriculaForm(forms.FormPlus):
    numero = forms.CharField(label='Matrícula Nº')


class IdentificacaoCandidatoForm(FormWizardPlus):
    METHOD = 'GET'
    LAST_SUBMIT_LABEL = 'Finalizar Identificação do Candidato'

    ano = forms.ModelChoiceField(Ano.objects.ultimos(), label='Ano', required=True)
    semestre = periodo_letivo = forms.ChoiceField(choices=[['', '----'], *PERIODO_LETIVO_CHOICES], label='Semestre', required=True)
    edital = forms.ModelChoiceField(Edital.objects, label='Edital', widget=forms.Select(attrs={'style': 'width:600px'}))
    cpf = forms.BrCpfField()

    candidato_vaga = forms.ModelChoiceField(CandidatoVaga.objects, label='Classificação', empty_label=None, widget=forms.RadioSelect())

    steps = (
        [('Identificação do Período', {'fields': ('ano', 'semestre')})],
        [('Seleção do Edital', {'fields': ('edital',)})],
        [('Identificação do Candidato', {'fields': ('cpf',)})],
        [('Indicação da Classificação', {'fields': ('candidato_vaga',)})],
    )

    def next_step(self):
        if 'edital' in self.fields:
            self.fields['edital'].queryset = self.get_edital_queryset()
        if 'candidato_vaga' in self.fields:
            self.fields['candidato_vaga'].queryset = self.get_candidato_vaga_queryset().all()
            if '_candidato_vaga' in self.request.GET:
                self.fields['candidato_vaga'].queryset = self.fields['candidato_vaga'].queryset.filter(pk=self.request.GET['_candidato_vaga'])

    def get_edital_queryset(self):
        ano = self.get_entered_data('ano')
        semestre = self.get_entered_data('semestre')
        return ano and semestre and Edital.locals.filter(ano=ano, semestre=semestre).distinct() or Edital.objects.none()

    def get_candidato(self):
        return self.get_candidato_vaga_queryset().all()[0].candidato

    def get_candidato_vaga_queryset(self):
        cpf = self.get_entered_data('cpf')
        edital = self.get_entered_data('edital')
        if cpf:
            return CandidatoVaga.objects.filter(oferta_vaga__oferta_vaga_curso__edital=edital, candidato__cpf=cpf)
        else:
            return CandidatoVaga.objects.none()

    def processar(self):
        return self.cleaned_data['candidato_vaga']

    def clean_cpf(self):
        if not self.get_candidato_vaga_queryset().exists():
            raise forms.ValidationError('Nenhum candidato habilitado foi encontrado com este CPF.')
        return self.cleaned_data['cpf']


class EfetuarMatriculaForm(FormWizardPlus):
    METHOD = 'POST'
    LAST_SUBMIT_LABEL = 'Finalizar Matrícula Institucional'

    foto = forms.PhotoCaptureField(required=False, widget=PhotoCapturePortraitInput)
    arquivo_foto = forms.ImageFieldPlus(label='Arquivo', required=False)

    nacionalidade = forms.ChoiceField(required=True, label='Nacionalidade', choices=Aluno.TIPO_NACIONALIDADE_CHOICES)
    cpf = forms.BrCpfField(required=False)
    passaporte = forms.CharField(required=False, label='Nº do Passaporte')
    estrangeiro_sem_passaporte = forms.BooleanField(label='É estrangeiro sem passaporte', required=False)
    nome = forms.CharFieldPlus(required=True, label='Nome', width=500)
    nome_social = forms.CharFieldPlus(
        required=False, label='Nome Social', help_text='Só preencher este campo a pedido do aluno e de acordo com a legislação vigente.', width=500
    )
    sexo = forms.ChoiceField(choices=[['M', 'Masculino'], ['F', 'Feminino']])
    data_nascimento = forms.DateFieldPlus(required=True, label='Data de Nascimento')
    estado_civil = forms.ChoiceField(required=True, choices=Aluno.ESTADO_CIVIL_CHOICES)

    # endereco
    logradouro = forms.CharFieldPlus(max_length=255, required=True, label='Logradouro', width=500)
    numero = forms.CharFieldPlus(max_length=255, required=True, label='Número', width=100)
    complemento = forms.CharField(max_length=255, required=False, label='Complemento')
    bairro = forms.CharField(max_length=255, required=True, label='Bairro')
    cep = forms.BrCepField(max_length=255, required=False, label='Cep')

    estado = forms.ModelChoiceField(Estado.objects, label='Estado', required=False)
    cidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Cidade',
        required=True,
        help_text='Preencha o nome da cidade sem acento.',
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS, form_filters=[('estado', 'estado__in')]),
    )

    tipo_zona_residencial = forms.ChoiceField(required=True, label='Zona Residencial', choices=[['', '-----'], *Aluno.TIPO_ZONA_RESIDENCIAL_CHOICES])

    # dados familiares
    nome_pai = forms.CharFieldPlus(max_length=255, label='Nome do Pai', required=False, width=500)
    estado_civil_pai = forms.ChoiceField(choices=Aluno.EMPTY_CHOICES + Aluno.ESTADO_CIVIL_CHOICES, required=False)
    pai_falecido = forms.BooleanField(label='Pai é falecido?', required=False)
    nome_mae = forms.CharFieldPlus(max_length=255, label='Nome da Mãe', required=True, width=500)
    estado_civil_mae = forms.ChoiceField(choices=Aluno.EMPTY_CHOICES + Aluno.ESTADO_CIVIL_CHOICES, required=False)
    mae_falecida = forms.BooleanField(label='Mãe é falecida?', required=False)
    responsavel = forms.CharFieldPlus(
        max_length=255, label='Nome do Responsável', required=False, width=500, help_text='Obrigatório para menores de idade.'
    )
    email_responsavel = forms.CharFieldPlus(max_length=255, label='Email do Responsável', required=False, width=500)
    parentesco_responsavel = forms.ChoiceField(
        label='Parenteste com Responsável', choices=[['', '---------'], *Aluno.PARENTESCO_CHOICES], required=False
    )
    cpf_responsavel = forms.BrCpfField(label='CPF do Responsável', required=False)

    # contato
    telefone_principal = forms.BrTelefoneField(max_length=255, required=False, label='Telefone Principal', help_text='(XX) XXXX-XXXX')
    telefone_secundario = forms.BrTelefoneField(max_length=255, required=False, label='Telefone Secundário', help_text='(XX) XXXX-XXXX')
    telefone_adicional_1 = forms.BrTelefoneField(max_length=255, required=False, label='Telefone do Responsável', help_text='(XX) XXXX-XXXX')
    telefone_adicional_2 = forms.BrTelefoneField(max_length=255, required=False, label='Telefone do Responsável', help_text='(XX) XXXX-XXXX')
    email_pessoal = forms.EmailField(max_length=255, required=False, label='E-mail Pessoal')

    # outras informacoes
    tipo_sanguineo = forms.ChoiceField(required=False, label='Tipo Sanguíneo', choices=Aluno.EMPTY_CHOICES + Aluno.TIPO_SANGUINEO_CHOICES)
    pais_origem = forms.ModelChoiceField(Pais.objects, required=False, label='País de Origem', help_text='Obrigatório para estrangeiros')

    naturalidade = forms.ModelChoiceFieldPlus(
        Cidade.objects,
        label='Naturalidade',
        required=False,
        widget=AutocompleteWidget(search_fields=Cidade.SEARCH_FIELDS),
    )

    raca = forms.ModelChoiceField(Raca.objects.all(), required=True, label='Raça')
    povo_indigena = forms.ModelChoiceField(
        label='Povo indígena',
        queryset=PovoIndigena.objects.all(),
        required=False,
        widget=AutocompleteWidget(search_fields=PovoIndigena.SEARCH_FIELDS),
        help_text='A informação sobre o povo indígena é obrigatória quando a raça for declarada como indígena.',
    )

    # necessidades especiais
    aluno_pne = forms.ChoiceField(
        label='Portador de Necessidades Especiais', required=True, choices=[['', '---------'], ['Sim', 'Sim'], ['Não', 'Não']]
    )
    deficiencias = forms.MultipleModelChoiceField(
        Deficiencia.objects,
        label='Deficiências',
        required=False,
        widget=AutocompleteWidget(
            search_fields=Deficiencia.SEARCH_FIELDS,
            multiple=True,
        ),
    )
    outras_nees = forms.MultipleModelChoiceField(
        TipoNEE.objects,
        label='Outras NEEs',
        required=False,
        widget=AutocompleteWidget(
            search_fields=TipoNEE.SEARCH_FIELDS,
            multiple=True,
        ),
    )

    # dados escolares
    nivel_ensino_anterior = forms.ModelChoiceField(NivelEnsino.objects, required=True, label='Nível de Ensino')
    tipo_instituicao_origem = forms.ChoiceField(
        required=True, label='Tipo da Instituição', choices=[['', '---------'], *Aluno.TIPO_INSTITUICAO_ORIGEM_CHOICES]
    )
    nome_instituicao_anterior = forms.CharField(max_length=255, required=False, label='Nome da Instituição')
    ano_conclusao_estudo_anterior = forms.ModelChoiceField(
        Ano.objects, required=False, label='Ano de Conclusão', help_text='Obrigatório para alunos com nível médio'
    )

    # rg
    numero_rg = forms.CharField(max_length=255, required=False, label='Número do RG')
    uf_emissao_rg = forms.ModelChoiceField(Estado.objects, required=False, label='Estado Emissor')
    orgao_emissao_rg = forms.ModelChoiceField(OrgaoEmissorRg.objects, required=False, label='Orgão Emissor')
    data_emissao_rg = forms.DateFieldPlus(required=False, label='Data de Emissão')

    # titulo_eleitor
    numero_titulo_eleitor = forms.CharField(max_length=255, required=False, label='Título de Eleitor')
    zona_titulo_eleitor = forms.CharField(max_length=255, required=False, label='Zona')
    secao = forms.CharField(max_length=255, required=False, label='Seção')
    data_emissao_titulo_eleitor = forms.DateFieldPlus(required=False, label='Data de Emissão')
    uf_emissao_titulo_eleitor = forms.ModelChoiceField(Estado.objects, required=False, label='Estado Emissor')

    # carteira de reservista
    numero_carteira_reservista = forms.CharField(max_length=255, required=False, label='Número da Carteira de Reservista')
    regiao_carteira_reservista = forms.CharField(max_length=255, required=False, label='Região')
    serie_carteira_reservista = forms.CharField(max_length=255, required=False, label='Série')
    estado_emissao_carteira_reservista = forms.ModelChoiceField(Estado.objects, required=False, label='Estado Emissor')
    ano_carteira_reservista = forms.IntegerField(required=False, label='Ano')

    # certidao_civil
    tipo_certidao = forms.ChoiceField(required=True, label='Tipo de Certidão', choices=Aluno.TIPO_CERTIDAO_CHOICES)
    cartorio = forms.ModelChoiceFieldPlus(
        Cartorio.objects,
        required=False,
        label='Cartório',
        help_text='Digite o nome do catório ou cidade para listar os catórios cadastrados',
        widget=AutocompleteWidget(search_fields=Cartorio.SEARCH_FIELDS),
    )
    numero_certidao = forms.CharField(max_length=255, required=False, label='Número de Termo')
    folha_certidao = forms.CharField(max_length=255, required=False, label='Folha')
    livro_certidao = forms.CharField(max_length=255, required=False, label='Livro')
    data_emissao_certidao = forms.DateFieldPlus(required=False, label='Data de Emissão')
    matricula_certidao = forms.CharField(
        max_length=255, required=False, label='Matrícula', help_text='Obrigatório para certidões realizadas a partir de 01/01/2010'
    )

    # dados da matrícula
    ano_letivo = forms.ModelChoiceField(Ano.objects.ultimos(), required=True, label='Ano Letivo')
    periodo_letivo = forms.ChoiceField(required=True, label='Período Letivo', choices=Aluno.PERIODO_LETIVO_CHOICES)
    turno = forms.ModelChoiceField(Turno.objects, required=True, label='Turno')
    polo = forms.ModelChoiceField(Polo.objects, required=False, label='Polo EAD', help_text='Apenas para o Turno EAD.')
    forma_ingresso = forms.ModelChoiceField(FormaIngresso.objects, required=True, label='Forma de Ingresso')
    convenio_internacional = forms.ModelChoiceField(
        ParceriaInternacional.objects.none(),
        required=False,
        label='Convênio Internacional',
        help_text='Obrigatório para alunos de intercâmbio internacional. Caso o convênio ainda não esteja cadastrado, solicite seu cadastro junto ao setor de extensão. O tipo de convênio deve ser "Relações Internacionais".',
    )
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
    numero_pasta = forms.CharFieldPlus(label='Número da Pasta', required=False, max_length=255)

    observacao_matricula = forms.CharField(widget=forms.Textarea(), required=False, label='Observação')

    utiliza_transporte_escolar_publico = forms.ChoiceField(
        label='Utiliza Transporte Escolar Público', required=False, choices=[['', '---------'], ['Sim', 'Sim'], ['Não', 'Não']]
    )
    poder_publico_responsavel_transporte = forms.ChoiceField(
        label='Poder Público Responsável pelo Transporte Escolar',
        choices=[['', '---------'], *Aluno.PODER_PUBLICO_RESPONSAVEL_TRANSPORTE_CHOICES],
        required=False,
    )
    tipo_veiculo = forms.ChoiceField(
        label='Tipo de Veículo Utilizado no Transporte Escolar', choices=[['', '---------'], *Aluno.TIPO_VEICULO_CHOICES_FOR_FORM], required=False
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

    steps = (
        [('Identificação', {'fields': ('nacionalidade', 'estrangeiro_sem_passaporte', 'cpf', 'passaporte')})],
        [
            ('Dados Pessoais', {'fields': ('nome', 'nome_social', 'sexo', 'data_nascimento', 'estado_civil')}),
            (
                'Dados Familiares',
                {
                    'fields': (
                        'nome_pai',
                        'estado_civil_pai',
                        'pai_falecido',
                        'nome_mae',
                        'estado_civil_mae',
                        'mae_falecida',
                        'responsavel',
                        'email_responsavel',
                        'parentesco_responsavel',
                        'cpf_responsavel',
                    )
                },
            ),
            ('Endereço', {'fields': ('cep', 'logradouro', 'numero', 'complemento', 'bairro', 'cidade', 'tipo_zona_residencial')}),
        ],
        [
            (
                'Informações para Contato',
                {'fields': ('telefone_principal', 'telefone_secundario', 'telefone_adicional_1', 'telefone_adicional_2', 'email_pessoal')},
            ),
            (
                'Deficiências, Transtornos e Superdotação',
                {
                    'fields': (
                        'aluno_pne',
                        'deficiencias',
                        'outras_nees',
                    )
                },
            ),
            (
                'Transporte Escolar Utilizado',
                {'fields': ('utiliza_transporte_escolar_publico', 'poder_publico_responsavel_transporte', 'tipo_veiculo')},
            ),
            ('Outras Informações', {'fields': ('tipo_sanguineo', 'pais_origem', 'naturalidade', 'raca', 'povo_indigena')}),
            (
                'Dados Escolares Anteriores',
                {'fields': ('nivel_ensino_anterior', 'tipo_instituicao_origem', 'nome_instituicao_anterior', 'ano_conclusao_estudo_anterior')},
            ),
        ],
        [
            ('RG', {'fields': ('numero_rg', 'uf_emissao_rg', 'orgao_emissao_rg', 'data_emissao_rg')}),
            (
                'Título de Eleitor',
                {'fields': ('numero_titulo_eleitor', 'zona_titulo_eleitor', 'secao', 'data_emissao_titulo_eleitor', 'uf_emissao_titulo_eleitor')},
            ),
            (
                'Carteira de Reservista',
                {
                    'fields': (
                        'numero_carteira_reservista',
                        'regiao_carteira_reservista',
                        'serie_carteira_reservista',
                        'estado_emissao_carteira_reservista',
                        'ano_carteira_reservista',
                    )
                },
            ),
            (
                'Certidão Civil',
                {
                    'fields': (
                        'tipo_certidao',
                        'cartorio',
                        'numero_certidao',
                        'folha_certidao',
                        'livro_certidao',
                        'data_emissao_certidao',
                        'matricula_certidao',
                    )
                },
            ),
        ],
        [
            ('Foto  (captura com câmera ou upload de arquivo)', {'fields': ('foto', 'arquivo_foto')}),
            (
                'Dados da Matrícula',
                {
                    'fields': (
                        'ano_letivo',
                        'periodo_letivo',
                        'turno',
                        'forma_ingresso',
                        'convenio_internacional',
                        'polo',
                        'cota_sistec',
                        'cota_mec',
                        'possui_convenio',
                        'convenio',
                        'data_conclusao_intercambio',
                        'matriz_curso',
                        'linha_pesquisa',
                        'aluno_especial',
                        'numero_pasta',
                        'possui_orientador',
                        'orientador',
                        'coorientadores',
                    )
                },
            ),
            ('Observação', {'fields': ('observacao_matricula',)}),
        ],
    )

    def __init__(self, request, candidato_vaga, *args, **kwargs):
        self.candidato_vaga = candidato_vaga
        super().__init__(*args, **kwargs)
        self.request = request
        if self.candidato_vaga:
            self.initial['cpf'] = self.candidato_vaga.candidato.cpf
            self.initial['nome'] = self.candidato_vaga.candidato.nome
        if 'convenio_internacional' in self.fields:
            self.fields['convenio_internacional'].queryset = ParceriaInternacional.objects.all()

    def clean_ano_conclusao_estudo_anterior(self):
        ano_conclusao_estudo_anterior = self.cleaned_data.get('ano_conclusao_estudo_anterior')
        nivel_ensino_anterior = self.data.get('nivel_ensino_anterior')
        if nivel_ensino_anterior == str(NivelEnsino.MEDIO) and not ano_conclusao_estudo_anterior:
            raise forms.ValidationError('O Ano de Conclusão é de preenchimento obrigatório.')
        return ano_conclusao_estudo_anterior

    def clean_ano_letivo(self):
        ano_letivo = self.cleaned_data.get('ano_letivo')
        if ano_letivo and self.candidato_vaga:
            if ano_letivo != self.candidato_vaga.candidato.edital.ano:
                raise forms.ValidationError(f'Ano incompatível com o do edital do candidato, que é {self.candidato_vaga.candidato.edital.ano}')
        return ano_letivo

    def clean_tipo_instituicao_origem(self):
        tipo_instituicao_origem = self.cleaned_data.get('tipo_instituicao_origem')

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.lista.forma_ingresso_id
            and self.candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_escola_publica
            and not tipo_instituicao_origem == 'Pública'
        ):
            raise forms.ValidationError('O candidato está ingressando como aluno de escola pública.')

        return tipo_instituicao_origem

    def clean_utiliza_transporte_escolar_publico(self):
        utiliza_transporte_escolar_publico = self.cleaned_data.get('utiliza_transporte_escolar_publico')
        if utiliza_transporte_escolar_publico == 'Sim':
            if not self.data.get('poder_publico_responsavel_transporte') or not self.data.get('tipo_veiculo'):
                raise forms.ValidationError('Informe o responsável pelo transporte público e o tipo utilizado')
        else:
            if self.data.get('poder_publico_responsavel_transporte') or self.data.get('tipo_veiculo'):
                raise forms.ValidationError(
                    'Marque a opção "Utiliza Transporte Escolar Público" caso deseje informar o responsável ou tipo de transporte público utilizado.'
                )
        return utiliza_transporte_escolar_publico

    def clean_aluno_pne(self):
        aluno_pne = self.cleaned_data.get('aluno_pne')

        if (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.lista.forma_ingresso_id
            and self.candidato_vaga.oferta_vaga.lista.forma_ingresso.programa_vaga_pessoa_deficiencia
            and not aluno_pne == 'Sim'
        ):
            raise forms.ValidationError('O candidato está ingressando como deficiente. Informe sua necessidade especial.')

        if aluno_pne == 'Sim' and not (self.data.get('deficiencias') or self.data.get('outras_nees')):
            raise forms.ValidationError('Informe a deficiência ou outra NEE do aluno.')
        return aluno_pne

    def clean_periodo_letivo(self):
        periodo_letivo = self.cleaned_data.get('periodo_letivo')
        if periodo_letivo and self.candidato_vaga:
            if int(periodo_letivo) != self.candidato_vaga.candidato.edital.semestre:
                raise forms.ValidationError(
                    f'Período incompatível com o do edital do candidato, que é {self.candidato_vaga.candidato.edital.semestre}'
                )
        return periodo_letivo

    def clean_nacionalidade(self):
        nacionalidade = self.get_entered_data('nacionalidade')
        estrangeiro_sem_passaporte = self.get_entered_data('estrangeiro_sem_passaporte')
        cpf = self.get_entered_data('cpf')

        if nacionalidade == 'Estrangeira' and not estrangeiro_sem_passaporte:
            if not self.get_entered_data('passaporte'):
                raise forms.ValidationError('Informe o passaporte do aluno.')
        elif not cpf:
            raise forms.ValidationError('Informe o CPF do aluno.')
        return nacionalidade

    def clean_nome(self):
        nome = self.get_entered_data('nome')

        if nome and not eh_nome_completo(nome):
            raise ValidationError('O nome do aluno precisa ser completo e não pode conter números.')

        return self.cleaned_data.get('nome')

    def clean_nome_social(self):
        nome = self.get_entered_data('nome_social')

        if nome and not eh_nome_completo(nome):
            raise ValidationError('O nome social do aluno precisa ser completo e não pode conter números.')

        return self.cleaned_data.get('nome_social')

    def clean_nome_pai(self):
        nome = self.get_entered_data('nome_pai')

        if nome and not eh_nome_completo(nome):
            raise ValidationError('O nome do pai precisa ser completo e não pode conter números.')

        return self.cleaned_data.get('nome_pai')

    def clean_nome_mae(self):
        nome = self.get_entered_data('nome_mae')

        if nome and not eh_nome_completo(nome):
            raise ValidationError('O nome da mãe precisa ser completo e não pode conter números.')

        return self.cleaned_data.get('nome_mae')

    def clean_responsavel(self):
        nome = self.get_entered_data('responsavel')

        if nome and not eh_nome_completo(nome):
            raise ValidationError('O nome do responsável precisa ser completo e não pode conter números.')

        p = PessoaFisica()
        p.nascimento_data = self.get_entered_data('data_nascimento')

        if p.nascimento_data and p.idade < 18 and not nome:
            raise ValidationError('Campo obrigatório para menores de idade.')

        return nome

    def clean_parentesco_responsavel(self):
        responsavel = self.data.get('responsavel')
        parentesco_responsavel = self.data.get('parentesco_responsavel')
        if responsavel and not parentesco_responsavel:
            raise ValidationError('O parentesco do responsável é necessário quando o responsável é informado.')
        return parentesco_responsavel

    def clean_polo(self):
        matriz_curso = self.get_entered_data('matriz_curso')
        polo = self.get_entered_data('polo')

        if matriz_curso:
            if polo:
                if not matriz_curso.curso_campus.diretoria.ead:
                    raise forms.ValidationError('O campo Polo deve ser definido apenas para cursos EAD.')
            elif matriz_curso.curso_campus.diretoria.ead:
                raise ValidationError('É necessário informar o Polo do aluno.')

        return self.cleaned_data.get('polo')

    def clean_data_nascimento(self) -> datetime.date:
        menor_data_valida = datetime.datetime.strptime('1900-01-01 00:00:00', '%Y-%m-%d %H:%M:%S').date()
        if 'data_nascimento' in self.cleaned_data and self.cleaned_data['data_nascimento'] < menor_data_valida:
            raise forms.ValidationError('Data de nascimento deve ser maior que 01/01/1900.')
        p = PessoaFisica()
        p.nascimento_data = self.get_entered_data('data_nascimento')
        if (
            p.nascimento_data
            and p.idade < 18
            and self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus.modalidade.pk
            in [Modalidade.INTEGRADO_EJA, Modalidade.FIC_INTEGRADO_EJA]
        ):
            raise ValidationError('O candidato não pode se matricular neste curso por que ainda é menor de idade.')
        try:
            # passaporte+país: recusado em clean_pais_origem, a etapa em que o país chega
            verificar_documento(cpf=self.get_entered_data('cpf'), nascimento_data=self.cleaned_data['data_nascimento'])
        except DocumentoDeOutraPessoa as erro:
            raise forms.ValidationError(erro.messages) from erro
        return self.cleaned_data['data_nascimento']

    def clean_pais_origem(self) -> Pais | None:
        nacionalidade = self.get_entered_data('nacionalidade')
        if nacionalidade and not nacionalidade == 'Brasileira' and not self.cleaned_data['pais_origem']:
            raise forms.ValidationError('O campo "País de Origem" possui preenchimento obrigatório quando a pessoa nasceu no exterior.')
        # get_entered_data: o catálogo (get_form do provedor) põe o pk cru no cleaned_data e chama este clean direto
        pais = self.get_entered_data('pais_origem')
        passaporte = self.get_entered_data('passaporte')
        if pais and passaporte:
            self._recusar_passaporte_de_outra_pessoa(pais, passaporte)

        return 'pais_origem' in self.cleaned_data and self.cleaned_data['pais_origem'] or None

    def _recusar_passaporte_de_outra_pessoa(self, pais: Pais, passaporte: str) -> None:
        """Recusa no campo do país (visível nesta etapa; a da data de nascimento já está oculta) o passaporte de pessoa com outro nascimento."""
        pais_pessoa = pais_do_aluno(pais)
        if pais_pessoa is None:
            if not self.get_entered_data('cpf'):
                raise forms.ValidationError('País sem correspondência no cadastro de países do SUAP; procure a secretaria.')
            return
        try:
            # com o CPF: o par de uma pessoa com outro CPF também é recusado (``PassaporteDeOutraPessoa``)
            verificar_documento(
                cpf=self.get_entered_data('cpf'), passaporte=passaporte, pais=pais_pessoa, nascimento_data=self.get_entered_data('data_nascimento')
            )
        except DocumentoDeOutraPessoa as erro:
            raise forms.ValidationError(erro.messages) from erro

    def clean_naturalidade(self):
        nacionalidade = self.get_entered_data('nacionalidade')
        eh_brasileiro = nacionalidade and nacionalidade == 'Brasileira'
        if (self.exige_naturalidade_estrangeiro or eh_brasileiro) and not self.cleaned_data.get('naturalidade'):
            raise forms.ValidationError('O campo "Naturalidade" possui preenchimento obrigatório.')

        naturalidade = self.get_entered_data('naturalidade')
        nome_pais = naturalidade and naturalidade.pais and naturalidade.pais.nome
        if eh_brasileiro and nome_pais != 'Brasil':
            raise forms.ValidationError('Não pode ser informado uma naturalidade fora do Brasil para aluno com nacionalidade Brasileira.')
        if not eh_brasileiro and nome_pais == 'Brasil':
            raise forms.ValidationError(
                'Não pode ser informado uma naturalidade do Brasil para aluno com nacionalidade Estrangeira ou Brasileira - Nascido no exterior ou naturalizado.'
            )

        return 'naturalidade' in self.cleaned_data and self.cleaned_data['naturalidade'] or None

    def clean_convenio_internacional(self):
        forma_ingresso = self.cleaned_data.get('forma_ingresso')
        convenio_internacional = self.cleaned_data.get('convenio_internacional')
        if forma_ingresso and forma_ingresso.descricao.replace('â', 'a').upper() == 'INTERCAMBIO' and not convenio_internacional:
            raise forms.ValidationError('Informe o convênio internacional do aluno')
        return convenio_internacional

    def clean_email_pessoal(self):
        email_pessoal = self.cleaned_data.get('email_pessoal', '')

        if not Configuracao.get_valor_por_chave('comum', 'permite_email_institucional_email_secundario') and Configuracao.eh_email_institucional(
            email_pessoal
        ):
            raise forms.ValidationError('Escolha um e-mail que não seja institucional.')

        return email_pessoal

    def clean_matricula_certidao(self):
        if 'data_emissao_certidao' in self.cleaned_data:
            data_emissao_certidao = self.cleaned_data['data_emissao_certidao']

            if not data_emissao_certidao or data_emissao_certidao < datetime.date(2010, 1, 1):
                pass
            else:
                if 'matricula_certidao' not in self.cleaned_data or not self.cleaned_data['matricula_certidao']:
                    raise forms.ValidationError('O campo matrícula é de preenchimento obrigatório para certidões realizadas a partir de 01/01/2010.')

        return 'matricula_certidao' in self.cleaned_data and self.cleaned_data['matricula_certidao'] or None

    def clean_linha_pesquisa(self):
        if self.data.get('matriz_curso'):
            qs_matriz_curso = MatrizCurso.objects.filter(pk=self.data['matriz_curso'])
            if qs_matriz_curso:
                matriz_curso = qs_matriz_curso[0]
                if (matriz_curso.curso_campus.modalidade.pk in [Modalidade.MESTRADO, Modalidade.DOUTORADO]) and not self.cleaned_data[
                    'linha_pesquisa'
                ]:
                    raise forms.ValidationError(
                        f'Este campo é obrigatório por se tratar de um aluno de um curso de  {matriz_curso.curso_campus.modalidade}.'
                    )
        return 'linha_pesquisa' in self.cleaned_data and self.cleaned_data['linha_pesquisa'] or None

    def clean_matriz_curso(self):
        matriz_curso = self.cleaned_data.get('matriz_curso')
        if matriz_curso:
            if self.candidato_vaga and not matriz_curso.curso_campus == self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus:
                raise forms.ValidationError('Esta matriz não é válida.')
            if not matriz_curso.curso_campus.pode_ingressar_aluno():
                raise forms.ValidationError('Este curso não permite novas matrículas.')
        return matriz_curso

    def clean_orientador(self):
        possui_orientador = self.cleaned_data.get('possui_orientador')
        is_nivel_pos = (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus.modalidade.nivel_ensino.pk == NivelEnsino.POS_GRADUACAO
        )
        if is_nivel_pos and possui_orientador and not self.data.get('orientador'):
            raise forms.ValidationError('É obrigatório o preenchimento do orientador.')
        elif is_nivel_pos and not possui_orientador and self.data.get('orientador'):
            raise forms.ValidationError('Não é possível selecionar um orientador quando o valor do campo "Possui Orientador?" é "Não".')
        return self.cleaned_data.get('orientador')

    def clean_coorientadores(self):
        possui_orientador = self.cleaned_data.get('possui_orientador')
        is_nivel_pos = (
            self.candidato_vaga
            and self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus.modalidade.nivel_ensino.pk == NivelEnsino.POS_GRADUACAO
        )
        if is_nivel_pos and not possui_orientador and self.data.get('coorientadores'):
            raise forms.ValidationError('Não é possível selecionar um coorientador quando o valor do campo "Possui Orientador?" é "Não".')
        if is_nivel_pos and possui_orientador and not self.data.get('orientador'):
            raise forms.ValidationError('É obrigatório o preenchimento do orientador para registrar os coorientadores.')
        return self.cleaned_data.get('coorientadores')

    def clean_convenio(self):
        possui_convenio = self.cleaned_data.get('possui_convenio')
        if possui_convenio and not self.data.get('convenio'):
            raise forms.ValidationError('Informe o convênio')
        elif not possui_convenio and self.data.get('convenio'):
            raise forms.ValidationError('Não é possível selecionar um convênio quando o valor do campo "Possui Convênio?" é "Não".')
        return self.cleaned_data.get('convenio')

    def clean_numero_rg(self):
        numero_rg = self.cleaned_data.get('numero_rg')
        if numero_rg:
            padrao_rg = r'^[a-zA-Z0-9]{4,15}$'
            if not re.match(padrao_rg, numero_rg):
                raise forms.ValidationError('Número do RG deve ter entre 4 e 15 caracteres e pode conter somente letras e números.')
        return numero_rg

    def next_step(self):
        if 'forma_ingresso' in self.fields:
            if self.candidato_vaga:
                if self.candidato_vaga.oferta_vaga.lista.forma_ingresso:
                    self.fields['forma_ingresso'].queryset = FormaIngresso.objects.filter(pk=self.candidato_vaga.oferta_vaga.lista.forma_ingresso.pk)
                    self.fields['forma_ingresso'].initial = self.candidato_vaga.oferta_vaga.lista.forma_ingresso.pk
                else:
                    self.fields['forma_ingresso'].queryset = FormaIngresso.objects.none()
            else:
                self.fields['forma_ingresso'].queryset = FormaIngresso.objects.exclude(descricao='Processo Seletivo').filter(ativo=True)
        if 'matriz_curso' in self.fields:
            self.fields['matriz_curso'].queryset = MatrizCurso.locals.filter(matriz__ativo=True)
            if self.candidato_vaga:
                self.fields['matriz_curso'].queryset = self.fields['matriz_curso'].queryset.filter(
                    curso_campus=self.candidato_vaga.oferta_vaga.oferta_vaga_curso.curso_campus
                )
        if self.cleaned_data.get('cpf'):
            qs = PessoaFisica.objects.filter(cpf=self.cleaned_data['cpf'])
            if qs:
                pessoa_fisica = qs[0]
                self.initial.update(nome=pessoa_fisica.nome, sexo=pessoa_fisica.sexo, data_nascimento=pessoa_fisica.nascimento_data)
        if 'pais_origem' in self.fields:
            self.fields['pais_origem'].queryset = Pais.objects.all().exclude(nome='Brasil')
        if 'naturalidade' in self.fields:
            self.exige_naturalidade_estrangeiro = Configuracao.get_valor_por_chave('edu', 'exige_naturalidade_estrangeiro')
            if self.exige_naturalidade_estrangeiro:
                self.fields['naturalidade'].required = True
            nacionalidade = self.get_entered_data('nacionalidade')
            if nacionalidade and nacionalidade == 'Brasileira':
                self.fields['naturalidade'].queryset = Cidade.objects.filter(codigo__isnull=False)
                self.fields['naturalidade'].help_text = 'Cidade em que o aluno nasceu. Obrigatório para brasileiros'
            elif nacionalidade and nacionalidade == 'Estrangeira':
                self.fields['naturalidade'].queryset = Cidade.objects.filter(codigo__isnull=True)
                self.fields['naturalidade'].help_text = 'Cidade/Província em que o aluno nasceu.'
        if 'convenio_internacional' in self.fields:
            self.fields['convenio_internacional'].queryset = self.fields['convenio_internacional'].queryset.filter(
                tipo__descricao='Relações Internacionais'
            )
        if self.candidato_vaga and 'polo' in self.fields:
            if self.candidato_vaga.oferta_vaga.oferta_vaga_curso.campus_polo:
                self.fields[
                    'polo'
                ].help_text = f'Apenas para o Turno EAD. O candidato escolheu o polo {self.candidato_vaga.oferta_vaga.oferta_vaga_curso.campus_polo}'

    def clean_aluno_especial(self):
        aluno_especial = self.cleaned_data['aluno_especial']
        if aluno_especial:
            matriz_curso = self.cleaned_data.get('matriz_curso')
            if matriz_curso is None:
                raise ValidationError('O campo Matriz/Curso é obrigatório.')
            limite = matriz_curso.matriz.estrutura.numero_max_alunos_especiais
            if limite:
                qs = Aluno.objects.filter(situacao_id=SituacaoMatricula.MATRICULADO, curso_campus=matriz_curso.curso_campus, aluno_especial=True)
                if qs.count() >= limite:
                    raise ValidationError(f'Limite de alunos especiais, que é de {limite} aluno(s), já atingido.')
        return aluno_especial

    def clean_povo_indigena(self):
        povo_indigena = self.cleaned_data.get('povo_indigena')
        raca = self.cleaned_data.get('raca')
        if isinstance(raca, str):
            raca = Raca.objects.filter(id=raca).first()
        if raca and raca.is_indigena() and not povo_indigena:
            raise ValidationError('O campo Povo indígena é de preenchimento obrigatório quando a raça for Indígena.')
        if povo_indigena and (not raca or not raca.is_indigena()):
            raise ValidationError('O campo Povo indígena só pode ser preenchido quando a raça for Indígena.')
        return povo_indigena

    def clean(self):
        matriz_curso = self.cleaned_data.get('matriz_curso')
        cpf = self.cleaned_data.get('cpf')
        ano_letivo = self.cleaned_data.get('ano_letivo')
        periodo_letivo = self.cleaned_data.get('periodo_letivo')

        if self.candidato_vaga and (self.candidato_vaga.oferta_vaga.qtd_semestre_1 or self.candidato_vaga.oferta_vaga.qtd_semestre_2):
            ano_letivo, periodo_letivo = self.candidato_vaga.get_periodo_letivo_apto_matricula()
            if ano_letivo is None or periodo_letivo is None:
                raise forms.ValidationError('O candidato só pode ser matriculado após o preenchimento de todas as vagas do primeiro semestre.')
            if self.candidato_vaga.is_reprovado_banca():
                raise forms.ValidationError(
                    'O candidato foi reprovado na banca de avaliação para a vaga na lista "{self.candidato_vaga.oferta_vaga.lista}".'
                )

        if matriz_curso and cpf and ano_letivo and periodo_letivo:
            qs_alunos = Aluno.objects.filter(
                curso_campus=matriz_curso.curso_campus,
                matriz=matriz_curso.matriz,
                pessoa_fisica__cpf=cpf,
                ano_letivo=ano_letivo,
                periodo_letivo=periodo_letivo,
            ).exclude(situacao__id__in=[SituacaoMatricula.CANCELADO, SituacaoMatricula.CANCELAMENTO_COMPULSORIO])
            if qs_alunos.exists():
                raise forms.ValidationError('Matrícula duplicada')

        if (
            'turno' in self.cleaned_data
            and 'ano_letivo' in self.cleaned_data
            and 'periodo_letivo' in self.cleaned_data
            and 'turno' in self.cleaned_data
            and 'matriz_curso' in self.cleaned_data
            and self.is_curso_fic()
        ):
            if not Turma.locals.filter(
                ano_letivo=self.cleaned_data['ano_letivo'],
                periodo_letivo=self.cleaned_data['periodo_letivo'],
                turno=self.cleaned_data['turno'],
                curso_campus=self.cleaned_data['matriz_curso'].curso_campus,
                matriz=self.cleaned_data['matriz_curso'].matriz,
            ).exists():
                raise forms.ValidationError('Não há turmas para o ano, período, turno, curso e matriz selecionados.')

        forma_ingresso = self.cleaned_data.get('forma_ingresso')
        raca = self.cleaned_data.get('raca')
        if raca and forma_ingresso and forma_ingresso.racas.exists():
            if not forma_ingresso.racas.filter(pk=raca.pk).exists():
                raise forms.ValidationError('A raça/etnia do aluno não é compatível com a forma as raças/etnias associados à forma de ingresso.')

        return self.cleaned_data

    def is_curso_fic(self):
        matriz_curso = self.cleaned_data.get('matriz_curso')
        return matriz_curso and matriz_curso.curso_campus.is_fic()

    @transaction.atomic
    def processar(self) -> Aluno:
        pessoa_fisica, _ = PessoaFisica.objects.obter_ou_criar(
            {
                'cpf': self.cleaned_data['cpf'],
                'passaporte': self.cleaned_data.get('passaporte'),
                'nome_registro': self.cleaned_data['nome'],
                'nome_social': self.cleaned_data['nome_social'],
                'sexo': self.cleaned_data['sexo'],
                'nascimento_data': self.cleaned_data['data_nascimento'],
                # o formulário usa edu.Pais; a pessoa usa comum.Pais (pelo nome, senão pela sigla alfa-3)
                'pais_origem': pais_do_aluno(self.cleaned_data.get('pais_origem')),
            },
            Politica.CAUTELOSA,
        )

        aluno = Aluno()
        aluno.periodo_atual = 1
        aluno.pessoa_fisica = pessoa_fisica
        aluno.estado_civil = self.cleaned_data['estado_civil']
        # dados familiares
        aluno.nome_pai = self.cleaned_data['nome_pai']
        aluno.estado_civil_pai = self.cleaned_data['estado_civil_pai']
        aluno.pai_falecido = self.cleaned_data['pai_falecido']
        aluno.nome_mae = self.cleaned_data['nome_mae']
        aluno.estado_civil_mae = self.cleaned_data['estado_civil_mae']
        aluno.mae_falecida = self.cleaned_data['mae_falecida']
        aluno.responsavel = self.cleaned_data['responsavel']
        aluno.email_responsavel = self.cleaned_data['email_responsavel']
        aluno.cpf_responsavel = self.cleaned_data['cpf_responsavel']
        aluno.parentesco_responsavel = self.cleaned_data['parentesco_responsavel']
        # endereco
        aluno.logradouro = self.cleaned_data['logradouro']
        aluno.numero = self.cleaned_data['numero']
        aluno.complemento = self.cleaned_data['complemento']
        aluno.bairro = self.cleaned_data['bairro']
        aluno.cep = self.cleaned_data['cep']
        aluno.cidade = self.cleaned_data['cidade']
        aluno.tipo_zona_residencial = self.cleaned_data['tipo_zona_residencial']
        # contato
        aluno.telefone_principal = self.cleaned_data['telefone_principal']
        aluno.telefone_secundario = self.cleaned_data['telefone_secundario']
        aluno.telefone_adicional_1 = self.cleaned_data['telefone_adicional_1']
        aluno.telefone_adicional_2 = self.cleaned_data['telefone_adicional_2']
        # TODO INSERIR CÓDIGO PARA CRIAÇÃO DO E-MAIL E ATUALIZAÇÃO NO AD

        # transporte escolar
        if self.cleaned_data['utiliza_transporte_escolar_publico']:
            aluno.poder_publico_responsavel_transporte = self.cleaned_data['poder_publico_responsavel_transporte']
            aluno.tipo_veiculo = self.cleaned_data['tipo_veiculo']
        else:
            aluno.poder_publico_responsavel_transporte = None
            aluno.tipo_veiculo = None

        # outras informacoes
        aluno.tipo_sanguineo = self.cleaned_data['tipo_sanguineo']
        aluno.nacionalidade = self.cleaned_data['nacionalidade']
        aluno.passaporte = self.cleaned_data['passaporte']
        aluno.estrangeiro_sem_passaporte = self.cleaned_data['estrangeiro_sem_passaporte']
        aluno.pais_origem = self.cleaned_data.get('pais_origem')
        aluno.naturalidade = self.cleaned_data['naturalidade']
        aluno.aluno_especial = self.cleaned_data['aluno_especial']

        # dados escolares
        aluno.nivel_ensino_anterior = self.cleaned_data['nivel_ensino_anterior']
        aluno.tipo_instituicao_origem = self.cleaned_data['tipo_instituicao_origem']
        aluno.nome_instituicao_anterior = self.cleaned_data['nome_instituicao_anterior']
        aluno.ano_conclusao_estudo_anterior = self.cleaned_data['ano_conclusao_estudo_anterior']
        # rg
        aluno.numero_rg = self.cleaned_data['numero_rg']
        aluno.uf_emissao_rg = self.cleaned_data['uf_emissao_rg']
        aluno.orgao_emissao_rg = self.cleaned_data['orgao_emissao_rg']
        aluno.data_emissao_rg = self.cleaned_data['data_emissao_rg']
        # titulo_eleitor
        aluno.numero_titulo_eleitor = self.cleaned_data['numero_titulo_eleitor']
        aluno.zona_titulo_eleitor = self.cleaned_data['zona_titulo_eleitor']
        aluno.secao = self.cleaned_data['secao']
        aluno.data_emissao_titulo_eleitor = self.cleaned_data['data_emissao_titulo_eleitor']
        aluno.uf_emissao_titulo_eleitor = self.cleaned_data['uf_emissao_titulo_eleitor']
        # carteira de reservista
        aluno.numero_carteira_reservista = self.cleaned_data['numero_carteira_reservista']
        aluno.regiao_carteira_reservista = self.cleaned_data['regiao_carteira_reservista']
        aluno.serie_carteira_reservista = self.cleaned_data['serie_carteira_reservista']
        aluno.estado_emissao_carteira_reservista = self.cleaned_data['estado_emissao_carteira_reservista']
        aluno.ano_carteira_reservista = self.cleaned_data['ano_carteira_reservista']
        # certidao_civil
        aluno.tipo_certidao = self.cleaned_data['tipo_certidao']
        aluno.cartorio = self.cleaned_data['cartorio']
        aluno.numero_certidao = self.cleaned_data['numero_certidao']
        aluno.folha_certidao = self.cleaned_data['folha_certidao']
        aluno.livro_certidao = self.cleaned_data['livro_certidao']
        aluno.data_emissao_certidao = self.cleaned_data['data_emissao_certidao']
        aluno.matricula_certidao = self.cleaned_data['matricula_certidao']
        # dados da matrícula
        aluno.ano_letivo = self.cleaned_data['ano_letivo']
        aluno.periodo_letivo = self.cleaned_data['periodo_letivo']
        if self.candidato_vaga and (self.candidato_vaga.oferta_vaga.qtd_semestre_1 or self.candidato_vaga.oferta_vaga.qtd_semestre_2):
            aluno.ano_letivo, aluno.periodo_letivo = self.candidato_vaga.get_periodo_letivo_apto_matricula()
        aluno.turno = self.cleaned_data['turno']
        aluno.polo = self.cleaned_data['polo']
        aluno.forma_ingresso = self.cleaned_data['forma_ingresso']
        aluno.convenio_internacional = self.cleaned_data.get('convenio_internacional')
        aluno.cota_sistec = self.cleaned_data['cota_sistec']
        aluno.cota_mec = self.cleaned_data['cota_mec']
        aluno.possui_convenio = self.cleaned_data['possui_convenio']
        aluno.convenio = self.cleaned_data['convenio']
        aluno.data_conclusao_intercambio = self.cleaned_data['data_conclusao_intercambio']
        aluno.curso_campus = self.cleaned_data['matriz_curso'].curso_campus
        aluno.matriz = self.cleaned_data['matriz_curso'].matriz
        aluno.linha_pesquisa = self.cleaned_data['linha_pesquisa']
        aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
        # ano_let_prev_conclusao será calculado no save do aluno
        aluno.ano_let_prev_conclusao = None
        aluno.numero_pasta = self.cleaned_data['numero_pasta']
        prefixo = f'{aluno.ano_letivo}{aluno.periodo_letivo}{aluno.curso_campus.codigo}'
        aluno.matricula = SequencialMatricula.proximo_numero(prefixo)
        aluno.candidato_vaga = self.candidato_vaga
        aluno.save()
        v = aluno.get_vinculo()
        if v:
            v.raca = self.cleaned_data['raca']
            v.povo_indigena = self.cleaned_data['povo_indigena']
            v.email_pessoal = self.cleaned_data.get('email_pessoal') or ''
            v.save(update_fields=['raca', 'povo_indigena', 'email_pessoal'])

        # deficiencias
        if self.cleaned_data['aluno_pne']:
            aluno.deficiencias.set(self.cleaned_data.get('deficiencias', []))
            aluno.outras_nees.set(self.cleaned_data.get('outras_nees', []))
        else:
            aluno.deficiencias.clear()
            aluno.outras_nees.clear()

        observacao = self.cleaned_data['observacao_matricula']
        if observacao:
            obs = Observacao()
            obs.aluno = aluno
            obs.data = datetime.datetime.now()
            obs.observacao = observacao
            obs.usuario = self.request.user
            obs.save()

        if 'foto' in self.cleaned_data and self.cleaned_data.get('foto'):
            aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(self.cleaned_data['foto']))
        elif 'arquivo_foto' in self.cleaned_data and self.cleaned_data.get('arquivo_foto'):
            aluno.foto.save(f'{aluno.pk}.jpg', ContentFile(self.cleaned_data.get('arquivo_foto').read()))

        aluno.save()

        hsm = HistoricoSituacaoMatricula()
        hsm.aluno = aluno
        hsm.situacao = aluno.situacao
        hsm.data = datetime.datetime.now()
        hsm.save()

        matricula_periodo = MatriculaPeriodo()
        matricula_periodo.aluno = aluno
        matricula_periodo.ano_letivo = aluno.ano_letivo
        matricula_periodo.periodo_letivo = aluno.periodo_letivo
        matricula_periodo.periodo_matriz = 1
        matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
        matricula_periodo.save()

        hsmp = HistoricoSituacaoMatriculaPeriodo()
        hsmp.matricula_periodo = matricula_periodo
        hsmp.situacao = matricula_periodo.situacao
        hsmp.data = aluno.data_matricula
        hsmp.save()

        aluno.atualizar_pendencias()
        aluno.save()

        vinculo_cancelado = (
            Aluno.objects.filter(
                curso_campus_id=aluno.curso_campus_id,
                pessoa_fisica__cpf=aluno.pessoa_fisica.cpf,
                situacao_id__in=[
                    SituacaoMatricula.CANCELADO,
                    SituacaoMatricula.CANCELAMENTO_COMPULSORIO,
                    SituacaoMatricula.CANCELAMENTO_POR_DESLIGAMENTO,
                    SituacaoMatricula.CANCELAMENTO_POR_DUPLICIDADE,
                    SituacaoMatricula.JUBILADO,
                    SituacaoMatricula.EVASAO,
                ],
            )
            .exclude(id=aluno.id)
            .exclude(matriz_id__isnull=True)
            .order_by('-data_matricula')
            .first()
        )
        if vinculo_cancelado:
            from edu.models import ProcedimentoReducaoCH

            pr = ProcedimentoReducaoCH()
            pr.matricula_periodo = matricula_periodo
            pr.tipo_procedimento = ProcedimentoReducaoCH.NOVO_INGRESSO
            pr.motivo = f'O aluno {aluno} realizou um novo vínculo no curso {aluno.curso_campus}. Vínculo anterior: {vinculo_cancelado.matricula}.'
            pr.informacao_complementar = f'Nova matrícula: <strong>{aluno.matricula}</strong> ({aluno.situacao.descricao}).<br>Matrícula anterior: <strong>{vinculo_cancelado.matricula}</strong> ({vinculo_cancelado.situacao.descricao}).'
            pr.vinculo = self.request.user.get_vinculo()
            pr.ch_nova = 0
            pr.ch_anterior = vinculo_cancelado.get_ch_cumprida()
            pr.save()
        return aluno


class MatricularDiarioForm(forms.Form):
    SUBMIT_LABEL = 'Matricular'
    confirmar = forms.BooleanField(label='Confirmar Matrícula', required=False)

    def clean_confirmar(self):
        confirmar = self.cleaned_data.get('confirmar')
        if not confirmar:
            raise ValidationError('Clique em Confirmar Matrícula para concluir a matrícula do aluno no diário.')

    def processar(self, matricula_periodo, diario):
        if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=diario).exists():
            matricula_diario = MatriculaDiario()
            matricula_diario.diario = diario
            matricula_diario.matricula_periodo = matricula_periodo
            matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
            matricula_diario.save()
            matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
            matricula_periodo.save()
            if matricula_periodo.aluno.situacao.pk != SituacaoMatricula.MATRICULADO:
                matricula_periodo.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
                matricula_periodo.aluno.save()


class MatricularAlunoTurmaForm(forms.Form):
    METHOD = 'POST'
    turma = forms.ModelChoiceField(Turma.objects, label='Turma', widget=forms.RadioSelect(), empty_label=None)

    def __init__(self, matricula_periodo, *args, **kwargs):
        self.matricula_periodo = matricula_periodo
        super().__init__(*args, **kwargs)
        pks = []
        for turma in matricula_periodo.aluno.get_turmas_matricula_online():
            pks.append(turma.pk)
        self.fields['turma'].queryset = Turma.objects.filter(pk__in=pks)
        # self.fields['turma'].queryset = Turma.objects.filter(curso_campus=self.matricula_periodo.aluno.curso_campus, ano_letivo=self.matricula_periodo.ano_letivo, periodo_letivo=self.matricula_periodo.periodo_letivo, periodo_matriz=self.matricula_periodo.aluno.periodo_atual)

    def processar(self):
        turma = self.cleaned_data.get('turma')
        matriculas_periodo = MatriculaPeriodo.objects.filter(pk=self.matricula_periodo.pk)
        turma.matricular_alunos(matriculas_periodo)


class MatricularAlunoAvulsoDiarioForm(forms.FormPlus):
    METHOD = 'POST'
    alunos = forms.MultipleModelChoiceFieldPlus(
        Aluno.locals, label='Aluno', widget=AutocompleteWidget(multiple=True, search_fields=Aluno.SEARCH_FIELDS), required=True
    )

    def __init__(self, diario, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.diario = diario
        self.fields['alunos'].queryset = (
            Aluno.locals.filter(
                situacao__pk__in=[
                    SituacaoMatricula.MATRICULADO,
                    SituacaoMatricula.TRANCADO_VOLUNTARIAMENTE,
                    SituacaoMatricula.TRANCADO,
                    SituacaoMatricula.INTERCAMBIO,
                    SituacaoMatricula.MATRICULA_VINCULO_INSTITUCIONAL,
                ],
                matriculaperiodo__situacao__pk__in=[
                    SituacaoMatriculaPeriodo.MATRICULADO,
                    SituacaoMatriculaPeriodo.EM_ABERTO,
                    SituacaoMatriculaPeriodo.MATRICULA_VINCULO_INSTITUCIONAL,
                ],
                matriz__isnull=False,
                matriculaperiodo__ano_letivo=diario.ano_letivo,
                matriculaperiodo__periodo_letivo=diario.periodo_letivo,
            )
            .exclude(matriculaperiodo__matriculadiario__diario=diario)
            .distinct()
        )

    def clean(self):
        for aluno in self.cleaned_data.get('alunos', []):
            self.clean_aluno(aluno)
        return self.cleaned_data

    def clean_aluno(self, aluno):
        ignorar_quebra_requisito = in_group(self.request.user, 'Administrador Acadêmico')
        pode_ser_matriculado, msg = aluno.pode_ser_matriculado_no_diario(self.diario, ignorar_quebra_requisito)
        if not pode_ser_matriculado:
            raise forms.ValidationError(msg)
        matricula_periodo = aluno.get_ultima_matricula_periodo()
        if not in_group(self.request.user, 'Administrador Acadêmico') and (
            matricula_periodo.ano_letivo != self.diario.ano_letivo or matricula_periodo.periodo_letivo != self.diario.periodo_letivo
        ):
            raise forms.ValidationError('Alunos com última matrícula período diferente do período letivo do diário não podem ser inseridos.')

    def processar(self):
        for aluno in self.cleaned_data['alunos']:
            self.processar_aluno(aluno)

    def processar_aluno(self, aluno):
        matricula_periodo = aluno.matriculaperiodo_set.get(ano_letivo=self.diario.ano_letivo, periodo_letivo=self.diario.periodo_letivo)
        if not MatriculaDiario.objects.filter(matricula_periodo=matricula_periodo, diario=self.diario).exists():
            matricula_diario = MatriculaDiario()
            matricula_diario.diario = self.diario
            matricula_diario.matricula_periodo = matricula_periodo
            matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
            matricula_diario.save()
            if matricula_periodo.aluno.situacao.pk != SituacaoMatricula.MATRICULADO:
                matricula_periodo.aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.MATRICULADO)
                matricula_periodo.aluno.save()
            if matricula_periodo.situacao != SituacaoMatriculaPeriodo.MATRICULADO:
                matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.MATRICULADO)
                matricula_periodo.save()


class AdicionarAlunoPrimeiraOfertaForm(forms.FormPlus):
    METHOD = 'POST'
    alunos = forms.MultipleModelChoiceFieldPlus(
        Aluno.locals, label='Aluno', widget=AutocompleteWidget(multiple=True, search_fields=Aluno.SEARCH_FIELDS), required=True
    )

    def __init__(self, *args, **kwargs):
        self.diario = kwargs.pop('diario')
        super().__init__(*args, **kwargs)
        self.fields['alunos'].queryset = (
            Aluno.locals.filter(
                situacao_id=SituacaoMatricula.MATRICULADO,
                matriculaperiodo__situacao_id=SituacaoMatriculaPeriodo.MATRICULADO,
                matriculaperiodo__matriculadiario__diario_id=self.diario.diario_primeira_oferta_id,
            )
            .exclude(matriculaperiodo__matriculadiario__diario_id=self.diario.id)
            .distinct()
        )

    def processar(self):
        for aluno in self.cleaned_data['alunos']:
            self.processar_aluno(aluno)

    def processar_aluno(self, aluno):
        md_primeira_oferta = MatriculaDiario.objects.filter(
            diario_id=self.diario.diario_primeira_oferta_id, matricula_periodo__aluno_id=aluno.id
        ).first()
        md_primeira_oferta.situacao = MatriculaDiario.SITUACAO_CANCELADO
        md_primeira_oferta.save()

        if not MatriculaDiario.objects.filter(matricula_periodo_id=md_primeira_oferta.matricula_periodo_id, diario=self.diario).exists():
            matricula_diario = MatriculaDiario()
            matricula_diario.diario = self.diario
            matricula_diario.matricula_periodo = md_primeira_oferta.matricula_periodo
            matricula_diario.situacao = MatriculaDiario.SITUACAO_CURSANDO
            matricula_diario.save()


class ConfiguracaoPedidoMatriculaForm(forms.ModelFormPlus):
    descricao = forms.CharFieldPlus(width=500, label='Descrição', required=True)
    diretorias = forms.MultipleModelChoiceField(
        Diretoria.objects.none(), label='Diretorias', widget=forms.CheckboxSelectMultiplePlus(), required=True
    )

    class Meta:
        model = ConfiguracaoPedidoMatricula
        exclude = ('cursos',)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        qs = Diretoria.locals
        if qs.count() == 1:
            self.fields['diretorias'] = forms.ModelChoiceField(qs)
            diretoria = self.fields['diretorias'].queryset.first()
            self.fields['diretorias'].initial = diretoria.pk
            self.initial['diretorias'] = diretoria.pk
            self.fields['diretorias'].widget = forms.HiddenInput()
        else:
            self.fields['diretorias'].queryset = qs
        if not settings.NOTA_DECIMAL:
            self.fields['permite_cancelamento_matricula_diario'].widget = forms.HiddenInput()

    def clean_data_fim(self):
        if 'data_inicio' in self.cleaned_data and 'data_fim' in self.cleaned_data:
            if self.cleaned_data['data_fim'] < self.cleaned_data['data_inicio']:
                raise ValidationError('A data de fim deve ser maior que a data de início.')
        return self.cleaned_data['data_fim']

    def clean_data_limite_requerimentos_especiais(self):
        permite_quebra_requisito = self.cleaned_data.get('permite_requerimento_quebra_de_requisito')
        permite_ultrapassar_ch_maxima = self.cleaned_data.get('permite_requerimento_ultrapassar_ch_maxima')
        data_limite_requerimentos_especiais = self.cleaned_data.get('data_limite_requerimentos_especiais')
        data_inicio = self.cleaned_data.get('data_inicio')
        data_fim = self.cleaned_data.get('data_fim')

        if permite_quebra_requisito or permite_ultrapassar_ch_maxima:
            if not data_limite_requerimentos_especiais:
                raise ValidationError(
                    'A data limite para submissão pelo aluno é obrigatória quando a quebra de requisito ou o aumento de carga horária estiverem habilitados.'
                )

            if data_inicio and data_fim and not (data_inicio <= data_limite_requerimentos_especiais <= data_fim):
                raise ValidationError('A data limite para submissão pelo aluno deve estar entre a data de início e a data de fim.')
        return data_limite_requerimentos_especiais

    def clean_diretorias(self):
        diretorias = self.cleaned_data['diretorias']
        if isinstance(self.fields['diretorias'].widget, forms.HiddenInput):
            return [diretorias]
        return diretorias

    def clean(self):
        if self.instance.is_processado():
            raise ValidationError('Os pedidos de renovação de matrícula já foram processados.')


class AddCursoConfiguracaoPedidoMatriculaForm(forms.ModelFormPlus):
    turmas_ofertadas = forms.MultipleModelChoiceFieldPlus(
        Turma.objects,
        label='Turmas',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Turma.SEARCH_FIELDS, form_filters=[('cursos', 'curso_campus__in')]),
    )
    diarios_ofertados = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        label='Diários',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Diario.SEARCH_FIELDS, form_filters=[('cursos', 'turma__curso_campus__in')]),
    )
    turmas = forms.MultipleModelChoiceFieldPlus(
        Turma.objects,
        label='Turmas',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Turma.SEARCH_FIELDS, form_filters=[('cursos', 'curso_campus__in')]),
    )
    diarios = forms.MultipleModelChoiceFieldPlus(
        Diario.objects,
        label='Diários',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Diario.SEARCH_FIELDS, form_filters=[('cursos', 'turma__curso_campus__in')]),
    )
    alunos = forms.MultipleModelChoiceFieldPlus(
        Aluno.objects,
        label='Alunos',
        required=False,
        widget=AutocompleteWidget(multiple=True, search_fields=Aluno.SEARCH_FIELDS, form_filters=[('cursos', 'curso_campus__in')]),
    )

    fieldsets = (
        ('Dados gerais', {'fields': ('cursos',)}),
        ('Restringir Oferta', {'fields': ('turmas_ofertadas', 'diarios_ofertados')}),
        ('Restringir Público', {'fields': ('turmas', 'diarios', 'alunos')}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['alunos'].queryset = self.fields['alunos'].queryset.filter(
            matriculaperiodo__ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1
        )
        if in_group(self.request.user, 'Administrador Acadêmico'):
            for field_name in ('turmas', 'turmas_ofertadas'):
                self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                    ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1,
                )
            for field_name in ('diarios', 'diarios_ofertados'):
                self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                    ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1,
                )
        elif in_group(self.request.user, 'Secretário Acadêmico'):
            if not running_tests():
                ids_diretorias = self.instance.diretorias.values_list('id', flat=True)
                self.fields['cursos'].queryset = self.fields['cursos'].queryset.filter(diretoria__in=ids_diretorias)
                for field_name in ('turmas', 'turmas_ofertadas'):
                    self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                        ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1, curso_campus__diretoria__in=ids_diretorias
                    )
                for field_name in ('diarios', 'diarios_ofertados'):
                    self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                        ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1, turma__curso_campus__diretoria__in=ids_diretorias
                    )
                self.fields['alunos'].queryset = self.fields['alunos'].queryset.filter(curso_campus__diretoria__in=ids_diretorias)
        elif in_group(self.request.user, 'Coordenador de Curso'):
            if not running_tests():
                ids_cursos = CursoCampus.objects.filter(ativo=True, coordenador=self.request.user.get_vinculo()) | CursoCampus.objects.filter(
                    ativo=True, coordenador_2=self.request.user.get_vinculo()
                ).values_list('id', flat=True)
                self.fields['cursos'].queryset = CursoCampus.objects.filter(id__in=ids_cursos)
                for field_name in ('turmas', 'turmas_ofertadas'):
                    self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                        ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1, curso_campus__in=ids_cursos
                    )
                for field_name in ('diarios', 'diarios_ofertados'):
                    self.fields[field_name].queryset = self.fields[field_name].queryset.filter(
                        ano_letivo__ano__gte=self.instance.ano_letivo.ano - 1, turma__curso_campus__in=ids_cursos
                    )
                self.fields['alunos'].queryset = self.fields['alunos'].queryset.filter(curso_campus__in=ids_cursos)

    class Meta:
        model = ConfiguracaoPedidoMatricula
        fields = 'turmas_ofertadas', 'diarios_ofertados', 'cursos', 'turmas', 'diarios', 'alunos'

    def clean(self):
        if 'cursos' in self.cleaned_data:
            for curso in self.cleaned_data['cursos']:
                qs = curso.configuracaopedidomatricula_set.filter(ano_letivo=self.instance.ano_letivo, periodo_letivo=self.instance.periodo_letivo)
                if self.instance:
                    qs = qs.exclude(pk=self.instance.pk)
                if qs.filter(data_inicio__lte=self.instance.data_inicio, data_fim__gte=self.instance.data_inicio) or qs.filter(
                    data_inicio__lte=self.instance.data_fim, data_fim__gte=self.instance.data_fim
                ):
                    raise forms.ValidationError(
                        f'Existe uma configuração cadastrada para o curso ({curso}) no período inserido que impede o cadastro neste intervalo de datas.'
                    )
        return self.cleaned_data
