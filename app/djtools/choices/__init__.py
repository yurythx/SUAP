from collections.abc import Iterable
from datetime import date


class DiaSemanaChoices:
    """
    Enumeração que retorna o dia da semana de forma resumida (somente o primeiro nome) ou completo.
    Em sua elaboração foi levado em consideração os valores usados por datetime.date.weekday, onde a segunda equivale
    a 0 e o domindo a 6.

    CHOICES existentes::

        - DIAS_CHOICES: de Segunda-Feira a Domingo
        - DIAS_RESUMIDO_CHOICES: de Segunda a Domingo
        - DIAS_SEMANA_CHOICE: de Segunda-Feira a Sexta-Feira
        - DIAS_SEMANA_RESUMIDO_CHOICES: de Segunda a Sexta
    """

    SEGUNDA = 0
    TERCA = 1
    QUARTA = 2
    QUINTA = 3
    SEXTA = 4
    SABADO = 5
    DOMINGO = 6

    DIAS_CHOICES = (
        (SEGUNDA, 'Segunda-Feira'),
        (TERCA, 'Terça-Feira'),
        (QUARTA, 'Quarta-Feira'),
        (QUINTA, 'Quinta-Feira'),
        (SEXTA, 'Sexta-Feira'),
        (SABADO, 'Sábado'),
        (DOMINGO, 'Domingo'),
    )

    DIAS_RESUMIDO_CHOICES = (
        (SEGUNDA, 'Segunda'),
        (TERCA, 'Terça'),
        (QUARTA, 'Quarta'),
        (QUINTA, 'Quinta'),
        (SEXTA, 'Sexta'),
        (SABADO, 'Sábado'),
        (DOMINGO, 'Domingo'),
    )

    DIAS_SEMANA_CHOICES = (
        (SEGUNDA, 'Segunda-Feira'),
        (TERCA, 'Terça-Feira'),
        (QUARTA, 'Quarta-Feira'),
        (QUINTA, 'Quinta-Feira'),
        (SEXTA, 'Sexta-Feira'),
    )

    DIAS_SEMANA_RESUMIDO_CHOICES = ((SEGUNDA, 'Segunda'), (TERCA, 'Terça'), (QUARTA, 'Quarta'), (QUINTA, 'Quinta'), (SEXTA, 'Sexta'))

    DIAS_FIM_SEMANA_CHOICES = ((SABADO, 'Sábado'), (DOMINGO, 'Domingo'))

    DIAS_FIM_SEMANA_RESUMIDO_CHOICES = ((SABADO, 'Sábado'), (DOMINGO, 'Domingo'))


SIM_NAO = [['S', 'Sim'], ['N', 'Não']]

# Fonte: http://www.dnrc.gov.br/Servicos_dnrc/tabela_nat_jurid.htm
NATUREZA_JURIDICA_CHOICES = [
    ['101', 'Órgão Público do Poder Executivo Federal'],
    ['102', 'Órgão Público do Poder Executivo Estadual ou do Distrito Federal'],
    ['103', 'Órgão Público do Poder Executivo Municipal'],
    ['104', 'Órgão Público do Poder Legislativo Federal'],
    ['105', 'Órgão Público do Poder Legislativo Estadual ou do Distrito Federal'],
    ['106', 'Órgão Público do Poder Legislativo Municipal'],
    ['107', 'Órgão Público do Poder Judiciário Federal'],
    ['108', 'Órgão Público do Poder Judiciário Estadual'],
    ['110', 'Autarquia Federal'],
    ['111', 'Autarquia Estadual ou do Distrito Federal'],
    ['112', 'Autarquia Municipal'],
    ['113', 'Fundação Federal'],
    ['114', 'Fundação Estadual ou do Distrito Federal'],
    ['115', 'Fundação Municipal'],
    ['116', 'Órgão Público Autônomo da União'],
    ['117', 'Órgão Público Autônomo Estadual ou do Distrito Federal'],
    ['118', 'Órgão Público Autônomo Municipal'],
    ['201', 'Empresa Pública'],
    ['203', 'Sociedade de Economia Mista'],
    ['204', 'Sociedade Anônima Aberta'],
    ['205', 'Sociedade Anônima Fechada'],
    ['206', 'Sociedade Empresária Limitada'],
    ['207', 'Sociedade Empresária em Nome Coletivo '],
    ['208', 'Sociedade Empresária em Comandita Simples'],
    ['209', 'Sociedade Empresária em Comandita por Ações'],
    ['210', 'Sociedade Mercantil de Capital e Indústria (extinta pelo NCC/2002)'],
    ['212', 'Sociedade Empresária em Conta de Participação'],
    ['213', 'Empresário (Individual)'],
    ['214', 'Cooperativa'],
    ['215', 'Consórcio de Sociedades'],
    ['216', 'Grupo de Sociedades'],
    ['217', 'Estabelecimento, no Brasil, de Sociedade Estrangeira'],
    ['219', 'Estabelecimento, no Brasil, de Empresa Binacional Argentino-Brasileira'],
    ['220', 'Entidade Binacional Itaipu'],
    ['221', 'Empresa Domiciliada no Exterior'],
    ['222', 'Clube/Fundo de Investimento'],
    ['223', 'Sociedade Simples Pura'],
    ['224', 'Sociedade Simples Limitada'],
    ['225', 'Sociedade em Nome Coletivo'],
    ['226', 'Sociedade em Comandita Simples'],
    ['227', 'Sociedade Simples em Conta de Participação'],
    ['303', 'Serviço Notarial e Registral (Cartório)'],
    ['304', 'Organização Social'],
    ['305', 'Organização da Sociedade Civil de Interesse Público (Oscip)'],
    ['306', 'Outras Formas de Fundações Mantidas com Recursos Privados'],
    ['307', 'Serviço Social Autônomo'],
    ['308', 'Condomínio Edilícios'],
    ['309', 'Unidade Executora (Programa Dinheiro Direto na Escola)'],
    ['310', 'Comissão de Conciliação Prévia'],
    ['311', 'Entidade de Mediação e Arbitragem'],
    ['312', 'Partido Político'],
    ['313', 'Entidade Sindical'],
    ['320', 'Estabelecimento, no Brasil, de Fundação ou Associação Estrangeiras'],
    ['321', 'Fundação ou Associação Domiciliada no Exterior'],
    ['399', 'Outras Formas de Associação'],
    ['401', 'Empresa Individual Imobiliária'],
    ['402', 'Segurado Especial'],
    ['408', 'Contribuinte individual'],
    ['500', 'Organização Internacional e Outras Instituições Extraterritoriais'],
]


class Situacao:
    DEFERIDA = 'Deferida'
    INDEFERIDA = 'Indeferida'
    PENDENTE = 'Pendente'
    PARCIALMENTE_DEFERIDA = 'Parcialmente Deferida'

    @classmethod
    def get_choices(cls):
        return [
            [cls.DEFERIDA, cls.DEFERIDA],
            [cls.INDEFERIDA, cls.INDEFERIDA],
            [cls.PENDENTE, cls.PENDENTE],
            [cls.PARCIALMENTE_DEFERIDA, cls.PARCIALMENTE_DEFERIDA],
        ]

    @classmethod
    def get_lista_simples(cls):
        return [cls.DEFERIDA, cls.INDEFERIDA, cls.PENDENTE, cls.PARCIALMENTE_DEFERIDA]


class SituacaoSolicitacaoDocumento:
    ATENDIDA = 1
    NAO_ATENDIDA = 2
    REJEITADA = 3
    DEVOLVIDA = 4

    @classmethod
    def get_choices(cls):
        return [[cls.ATENDIDA, 'Atendida'], [cls.NAO_ATENDIDA, 'Não Atendida'], [cls.REJEITADA, 'Rejeitada']]

    @classmethod
    def get_lista_simples(cls):
        return [cls.ATENDIDA, cls.NAO_ATENDIDA, cls.REJEITADA, cls.DEVOLVIDA]


class Meses:
    JANEIRO = 'Janeiro'
    FEVEREIRO = 'Fevereiro'
    MARCO = 'Março'
    ABRIL = 'Abril'
    MAIO = 'Maio'
    JUNHO = 'Junho'
    JULHO = 'Julho'
    AGOSTO = 'Agosto'
    SETEMBRO = 'Setembro'
    OUTUBRO = 'Outubro'
    NOVEMBRO = 'Novembro'
    DEZEMBRO = 'Dezembro'

    @classmethod
    def get_choices(cls):
        return [
            [1, cls.JANEIRO],
            [2, cls.FEVEREIRO],
            [3, cls.MARCO],
            [4, cls.ABRIL],
            [5, cls.MAIO],
            [6, cls.JUNHO],
            [7, cls.JULHO],
            [8, cls.AGOSTO],
            [9, cls.SETEMBRO],
            [10, cls.OUTUBRO],
            [11, cls.NOVEMBRO],
            [12, cls.DEZEMBRO],
        ]

    @classmethod
    def get_mes(cls, numero):
        for id, nome in cls.get_choices():
            if int(id) == int(numero):
                return nome
        return 'Desconhecido'

    @classmethod
    def get_numero(cls, mes):
        for id, nome in cls.get_choices():
            if nome == mes:
                return id
        return 0


class Anos:
    @classmethod
    def get_choices(cls, ano_minimo=2010, ano_maximo=None, empty_label='', empty_value=0):
        if not ano_maximo:
            ano_maximo = date.today().year
        empty_label = empty_label or '---------'
        empty_value = empty_value or ''
        return [[empty_value, empty_label]] + [[ano, f'{ano:4d}'] for ano in range(ano_maximo, ano_minimo - 1, -1)]


campos = [
    {'campo': 'matricula_anterior', 'alias': 'Matrícula Anterior'},
    {'campo': 'data_exclusao_instituidor', 'alias': 'Data Exclusão Instituidor'},
    {'campo': 'pessoa_fisica.cpf', 'alias': 'CPF'},
    {'campo': 'pessoa_fisica.sexo', 'alias': 'Sexo'},
    {'campo': 'pessoa_fisica.nascimento_data', 'alias': 'Data de Nascimento'},
    {'campo': 'pessoa_fisica.nascimento_municipio', 'alias': 'Naturalidade'},
    {'campo': 'nivel_escolaridade', 'alias': 'Escolaridade'},
    {'campo': 'ocorrencias_display', 'alias': 'Ocorrências'},
    {'campo': 'afastamentos_display', 'alias': 'Afastamentos'},
    {'campo': 'data_inicio_servico_publico', 'alias': 'Data de início no serviço publico'},
    {'campo': 'data_inicio_exercicio_na_instituicao', 'alias': 'Data de início na instituição'},
    {'campo': 'data_posse_na_instituicao', 'alias': 'Data de posse na instituição'},
    {'campo': 'data_inicio_exercicio_no_cargo', 'alias': 'Data de início de exercício no cargo'},
    {'campo': 'data_posse_no_cargo', 'alias': 'Data de posse no cargo'},
    {'campo': 'data_fim_servico_na_instituicao', 'alias': 'Data fim de serviço na instituição'},
    {'campo': 'setor', 'alias': 'Setor SUAP'},
    {'campo': 'campus', 'alias': 'Campus SUAP'},
    {'campo': 'setor_lotacao', 'alias': 'Setor Lotação SIAPE'},
    {'campo': 'campus_lotacao_siape', 'alias': 'Campus Lotação SIAPE'},
    {'campo': 'setor_exercicio', 'alias': 'Setor de Exercício SIAPE'},
    {'campo': 'campus_exercicio_siape', 'alias': 'Campus Exercício SIAPE'},
    {'campo': 'setor_lotacao_data_ocupacao', 'alias': 'Setor Lotação (Ingresso)'},
    {'campo': 'funcao_display', 'alias': 'Função'},
    {'campo': 'funcao_data_ocupacao', 'alias': 'Função (Ingresso)'},
    {'campo': 'setor_funcao', 'alias': 'Setor Função'},
    {'campo': 'cargo_emprego', 'alias': 'Cargo Emprego'},
    {'campo': 'cargo_emprego_area', 'alias': 'Cargo Emprego Área'},
    {'campo': 'get_grupo_cargo_emprego', 'alias': 'Grupo Cargo Emprego'},
    {'campo': 'cargo_emprego_data_ocupacao', 'alias': 'Cargo Emprego (Ocupação)'},
    {'campo': 'cargo_emprego_data_saida', 'alias': 'Cargo Emprego (Saída)'},
    {'campo': 'cargo_classe', 'alias': 'Classe do Cargo'},
    {'campo': 'jornada_trabalho', 'alias': 'Jornada de Trabalho'},
    {'campo': 'get_modelo_regime_trabalho', 'alias': 'Modelo de regime de trabalho'},
    {'campo': 'atividade', 'alias': 'Atividade'},
    {'campo': 'regime_juridico', 'alias': 'Regime Jurídico'},
    {'campo': 'situacao', 'alias': 'Situação'},
    {'campo': 'pessoa_fisica.banco_display', 'alias': 'Dados Bancários'},
    {'campo': 'pessoa_fisica.ctps_display', 'alias': 'Carteira de Trabalho'},
    {'campo': 'aposentadoria', 'alias': 'Aposentadoria'},
    {'campo': 'data_obito', 'alias': 'Data de Óbito'},
    {'campo': 'categoria', 'alias': 'Categoria'},
    {'campo': 'nivel_padrao', 'alias': 'Nível Padrão'},
    {'campo': 'data_ultima_progressao', 'alias': 'Data da Última Progressão'},
    {'campo': 'identificacao_unica_siape', 'alias': 'Identificação Única'},
    {'campo': 'data_cadastro_siape', 'alias': 'Data Cadastro'},
    {'campo': 'qtde_depend_ir', 'alias': 'Qtde Depend. IR'},
    {'campo': 'codigo_vaga', 'alias': 'Código de Vaga'},
    {'campo': 'titulacao', 'alias': 'Titulação'},
    {'campo': 'pessoa_fisica.nome_pai', 'alias': 'Nome do Pai'},
    {'campo': 'pessoa_fisica.nome_mae', 'alias': 'Nome da Mãe'},
    {'campo': 'pessoa_fisica.titulo_eleitoral_display', 'alias': 'Titulo Eleitoral'},
    {'campo': 'pessoa_fisica.rg_display', 'alias': 'RG'},
    {'campo': 'raca', 'alias': 'Cor/Raça'},
    {'campo': 'pessoa_fisica.pis_pasep', 'alias': 'PIS/PASEP'},
    {'campo': 'pessoa_fisica.grupo_sanguineo', 'alias': 'Grupo Sangüineo'},
    {'campo': 'pessoa_fisica.fator_rh', 'alias': 'Fator RH'},
    {'campo': 'pessoa_fisica.cnh_display', 'alias': 'Carteria de Habilitação'},
    {'campo': 'pessoa_fisica.endereco', 'alias': 'Endereço'},
    {'campo': 'pessoa_fisica.idade', 'alias': 'Idade'},
    #    { 'campo': 'endereco_cep', 'alias': 'CEP' },
    #    { 'campo': 'endereco_municipio', 'alias': 'Municipio' },
    #    { 'campo': 'endereco_logradouro', 'alias': 'Logradouro' },
    #    { 'campo': 'endereco_numero', 'alias': 'Numero' },
    #    { 'campo': 'endereco_complemento', 'alias': 'Complemento' },
    #    { 'campo': 'endereco_bairro', 'alias': 'Bairro' },
    {'campo': 'email_pessoal', 'alias': 'E-mail'},
    {'campo': 'email_notificacao', 'alias': 'E-mail de Notificação'},
    {'campo': 'email_siape', 'alias': 'E-mail SIAPE'},
    {'campo': 'email_institucional', 'alias': 'E-mail Institucional'},
    {'campo': 'email_academico', 'alias': 'E-mail Acadêmico'},
    {'campo': 'email_google_classroom', 'alias': 'E-mail Google ClassRoom:'},
    {'campo': 'disciplina_ingresso', 'alias': 'Disciplina de Ingresso'},
    {'campo': 'pessoa_fisica.estado_civil', 'alias': 'Estado Civil'},
    {'campo': 'pessoa_fisica.telefones', 'alias': 'Telefone'},
    {'campo': 'opera_raio_x', 'alias': 'Opera Raio X'},
    {'campo': 'ferias', 'alias': 'Férias'},
    {'campo': 'foto', 'alias': 'Foto'},
    {'campo': 'num_processo_aposentadoria', 'alias': 'Aposentadoria (Num)'},
    {'campo': 'numerador_prop_aposentadoria', 'alias': 'Aposentadoria (Numerador)'},
    {'campo': 'denominador_prop_aposentadoria', 'alias': 'Aposentadoria (Denominador)'},
    {'campo': 'deficiencia', 'alias': 'Deficiência'},
]

# Whitelist de entrada do relatório de busca de servidores. Os campos chegam por querystring
# (`?campos=...`) e são resolvidos por getattr encadeado, com auto-chamada do resultado quando
# ele é callable — sem validar contra esta lista, qualquer atributo/método sem argumentos do
# Servidor (ou da cadeia que ele expõe) seria alcançável e executado pela view.
CAMPOS_VALIDOS = frozenset(dicionario['campo'] for dicionario in campos)


def filtrar_campos_validos(selecionados: Iterable[str]) -> list[str]:
    """Filtra os campos vindos da querystring, preservando a ordem escolhida pelo usuário.

    Args:
        selecionados: valores crus de `?campos=` na requisição.
    Returns:
        Apenas os campos presentes em `campos`.
    """
    return [campo for campo in selecionados if campo in CAMPOS_VALIDOS]


campos_nao_agrupaveis = [
    'Matrícula Anterior',
    'CPF',
    'Identificação Única',
    'Código de Vaga',
    'Nome do Pai',
    'Nome da Mãe',
    'Titulo Eleitoral',
    'RG',
    'PIS/PASEP',
    'Carteria de Habilitação',
    'Endereço',
    'E-mail',
    'Telefone',
    'Aposentadoria',
    'Aposentadoria (Num)',
    'Aposentadoria (Numerador)',
    'Aposentadoria (Denominador)',
    'Foto',
    'Dados Bancários',
    'Férias',
    'Carteira de Trabalho',
    'Data de Óbito',
    'Data Cadastro',
    'Data Exclusão Instituidor',
    'Data de Nascimento',
    'Data da Posse',
    'Data do Exercício',
]

GENDER = {}
GENDER['ae.CategoriaAlimentacao'] = 'M'
GENDER['ae.DemandaAluno'] = 'M'
GENDER['ae.CategoriaBolsa'] = 'F'
GENDER['ae.Programa'] = 'M'
GENDER['ae.Inscricao'] = 'F'
GENDER['ae.InscricaoAlimentacao'] = 'F'
GENDER['ae.InscricaoIdioma'] = ''
GENDER['ae.InscricaoTrabalho'] = 'F'
GENDER['ae.InscricaoPasseEstudantil'] = 'F'
GENDER['ae.DadosBancarios'] = 'M'
GENDER['ae.Participacao'] = 'F'
GENDER['ae.ParticipacaoAlimentacao'] = ''
GENDER['ae.ParticipacaoIdioma'] = ''
GENDER['ae.ParticipacaoTrabalho'] = ''
GENDER['ae.ParticipacaoPasseEstudantil'] = ''
GENDER['ae.DemandaAlunoAtendida'] = 'M'
GENDER['ae.TipoAtendimentoSetor'] = 'M'
GENDER['ae.AtendimentoSetor'] = 'M'
GENDER['ae.AgendamentoRefeicao'] = ''
GENDER['ae.DadosFincanceiros'] = ''
GENDER['ae.OfertaAlimentacao'] = 'F'
GENDER['ae.OfertaValorRefeicao'] = 'M'
GENDER['ae.OfertaTurma'] = 'F'
GENDER['ae.OfertaBolsa'] = 'F'
GENDER['ae.OfertaValorBolsa'] = 'M'
GENDER['ae.OfertaPasse'] = 'M'
GENDER['ae.SolicitacaoAlimentacao'] = 'F'
GENDER['ae.NecessidadeEspecial'] = 'F'
GENDER['ae.Idioma'] = 'M'
GENDER['ae.SituacaoTrabalho'] = 'F'
GENDER['ae.MeioTransporte'] = 'M'
GENDER['ae.ContribuinteRendaFamiliar'] = 'M'
GENDER['ae.CompanhiaDomiciliar'] = 'F'
GENDER['ae.TipoImovelResidencial'] = 'M'
GENDER['ae.TipoEscola'] = ''
GENDER['ae.TipoAreaResidencial'] = 'M'
GENDER['ae.TipoServicoSaude'] = ''
GENDER['ae.BeneficioGovernoFederal'] = 'M'
GENDER['ae.TipoEmprego'] = 'M'
GENDER['ae.TipoAcessoInternet'] = ''
GENDER['ae.RazaoAfastamentoEducacional'] = 'F'
GENDER['ae.EstadoCivil'] = 'M'
GENDER['ae.NivelEscolaridade'] = 'M'
GENDER['ae.HistoricoCaracterizacao'] = ''
GENDER['ae.Caracterizacao'] = ''
GENDER['ae.IntegranteFamiliarCaracterizacao'] = ''
GENDER['ae.InscricaoCaracterizacao'] = ''
GENDER['ae.HistoricoRendaFamiliar'] = ''
GENDER['ae.ParticipacaoBolsa'] = 'F'
GENDER['comum.Sala'] = 'F'
GENDER['demandas.Demanda'] = 'F'
GENDER['ponto.Frequencia'] = 'F'
GENDER['ponto.Maquina'] = 'F'
GENDER['ponto.MaquinaLog'] = 'M'
GENDER['ponto.Liberacao'] = 'F'
GENDER['ponto.Observacao'] = 'F'
GENDER['ponto.AbonoChefia'] = 'M'
GENDER['ponto.TipoAfastamento'] = 'M'
GENDER['ponto.Afastamento'] = ''
GENDER['frota.ViaturaGrupo'] = ''
GENDER['frota.ViaturaStatus'] = 'F'
GENDER['frota.Viatura'] = ''
GENDER['frota.MotoristaTemporario'] = 'M'
GENDER['frota.ViagemAgendamento'] = 'M'
GENDER['frota.ViagemAgendamentoResposta'] = 'F'
GENDER['frota.Viagem'] = 'F'
GENDER['frota.ViaturaOrdemAbastecimento'] = 'F'
GENDER['frota.TrocaOleo'] = 'F'
GENDER['edu.Log'] = ''
GENDER['edu.RegistroDiferenca'] = ''
GENDER['edu.OrgaoEmissorRg'] = 'M'
GENDER['edu.Pais'] = 'M'
GENDER['edu.Estado'] = 'M'
GENDER['edu.Cidade'] = 'F'
GENDER['edu.Cartorio'] = 'M'
GENDER['edu.FormaIngresso'] = 'F'
GENDER['edu.AreaCurso'] = 'F'
GENDER['edu.EixoTecnologico'] = 'M'
GENDER['edu.NaturezaParticipacao'] = 'F'
GENDER['edu.Turno'] = 'M'
GENDER['edu.SituacaoMatricula'] = 'F'
GENDER['edu.SituacaoMatriculaPeriodo'] = 'F'
GENDER['edu.HorarioCampus'] = 'M'
GENDER['edu.HorarioAula'] = 'M'
GENDER['edu.HorarioAulaDiario'] = 'M'
GENDER['edu.NivelEnsino'] = 'M'
GENDER['edu.Modalidade'] = 'F'
GENDER['edu.EstruturaCurso'] = 'F'
GENDER['edu.Convenio'] = 'M'
GENDER['edu.Diretoria'] = 'F'
GENDER['edu.Nucleo'] = 'M'
GENDER['edu.CursoCampus'] = 'M'
GENDER['edu.MatrizCurso'] = 'M'
GENDER['edu.TipoComponente'] = 'M'
GENDER['edu.TipoAtividadeExtracurricular'] = 'M'
GENDER['edu.Componente'] = 'M'
GENDER['edu.Matriz'] = 'F'
GENDER['edu.ComponenteCurricular'] = 'M'
GENDER['edu.CalendarioAcademico'] = 'M'
GENDER['edu.Turma'] = 'F'
GENDER['edu.Diario'] = 'M'
GENDER['edu.NucleoCentralEstruturante'] = 'M'
GENDER['edu.Disciplina'] = 'F'
GENDER['edu.Professor'] = 'M'
GENDER['edu.TipoProfessorDiario'] = 'M'
GENDER['edu.ProfessorDiario'] = 'M'
GENDER['edu.Aluno'] = 'M'
GENDER['edu.MatriculaPeriodo'] = 'F'
GENDER['edu.MatriculaDiario'] = 'F'
GENDER['edu.Aula'] = 'F'
GENDER['edu.Falta'] = 'F'
GENDER['edu.SequencialMatricula'] = ''
GENDER['edu.HistoricoSituacaoMatricula'] = 'M'
GENDER['edu.HistoricoSituacaoMatriculaPeriodo'] = 'M'
GENDER['edu.SolicitacaoUsuario'] = 'F'
GENDER['edu.SolicitacaoRelancamentoEtapa'] = 'F'
GENDER['edu.SolicitacaoAlteracaoFoto'] = 'F'
GENDER['edu.ConfiguracaoGestao'] = 'F'
GENDER['edu.ModeloDocumento'] = 'M'
GENDER['edu.ConfiguracaoLivro'] = 'F'
GENDER['edu.RegistroEmissaoDiploma'] = 'F'
GENDER['edu.HistoricoImportacao'] = 'M'
GENDER['edu.MaterialAula'] = 'M'
GENDER['edu.MaterialDiario'] = 'M'
GENDER['edu.PeriodoLetivoAtual'] = ''
GENDER['edu.EquivalenciaComponenteQAcademico'] = 'F'
GENDER['edu.MatriculaDiarioResumida'] = ''
GENDER['edu.LinhaPesquisa'] = 'F'
GENDER['edu.AbonoFaltas'] = 'F'
GENDER['edu.ProcedimentoMatricula'] = ''
GENDER['edu.CertificacaoConhecimento'] = 'F'
GENDER['edu.AproveitamentoEstudo'] = 'M'
GENDER['edu.AtividadeComplementar'] = 'F'
GENDER['financeiro.CategoriaEconomicaDespesa'] = 'F'
GENDER['financeiro.GrupoNaturezaDespesa'] = 'M'
GENDER['financeiro.ModalidadeAplicacao'] = 'F'
GENDER['financeiro.ElementoDespesa'] = 'M'
GENDER['financeiro.NaturezaDespesa'] = 'F'
GENDER['financeiro.ClassificacaoDespesa'] = 'F'
GENDER['financeiro.SubElementoNaturezaDespesa'] = 'M'
GENDER['financeiro.GrupoFonteRecurso'] = 'M'
GENDER['financeiro.EspecificacaoFonteRecurso'] = 'F'
GENDER['financeiro.FonteRecurso'] = 'F'
GENDER['financeiro.Funcao'] = 'F'
GENDER['financeiro.Subfuncao'] = 'F'
GENDER['financeiro.Localizacao'] = 'F'
GENDER['financeiro.IdentificadorUso'] = 'M'
GENDER['financeiro.IdentificadorResultadoPrimario'] = 'M'
GENDER['financeiro.UnidadeGestora'] = 'F'
GENDER['financeiro.ClassificacaoInstitucional'] = 'F'
GENDER['financeiro.EsferaOrcamentaria'] = 'F'
GENDER['financeiro.InstrumentoLegal'] = 'M'
GENDER['financeiro.ModalidadeLicitacao'] = 'F'
GENDER['financeiro.UnidadeMedida'] = 'F'
GENDER['financeiro.Programa'] = 'M'
GENDER['financeiro.Acao'] = 'F'
GENDER['financeiro.Evento'] = 'M'
GENDER['financeiro.ProgramaTrabalho'] = 'M'
GENDER['financeiro.ProgramaTrabalhoResumido'] = 'M'
GENDER['financeiro.PlanoInterno'] = 'M'
GENDER['financeiro.NotaCredito'] = 'F'
GENDER['financeiro.NotaCreditoItem'] = 'M'
GENDER['financeiro.NotaDotacao'] = 'F'
GENDER['financeiro.NotaDotacaoItem'] = 'M'
GENDER['financeiro.NotaEmpenho'] = 'F'
GENDER['financeiro.NEListaItens'] = 'F'
GENDER['financeiro.NEItem'] = 'M'
GENDER['financeiro.NotaSistema'] = 'F'
GENDER['financeiro.NotaSistemaItem'] = 'M'
GENDER['financeiro.LogImportacaoSIAFI'] = ''
GENDER['financeiro.AcaoAno'] = 'F'
GENDER['arquivo.TipoArquivo'] = 'M'
GENDER['arquivo.Funcao'] = 'F'
GENDER['arquivo.Processo'] = 'M'
GENDER['arquivo.Arquivo'] = 'M'
GENDER['estacionamento.VeiculoEspecie'] = ''
GENDER['estacionamento.VeiculoTipo'] = ''
GENDER['estacionamento.VeiculoTipoEspecie'] = ''
GENDER['estacionamento.VeiculoMarca'] = ''
GENDER['estacionamento.VeiculoModelo'] = ''
GENDER['estacionamento.VeiculoCor'] = ''
GENDER['estacionamento.VeiculoCombustivel'] = ''
GENDER['estacionamento.Veiculo'] = 'M'
GENDER['ps.OfertaVaga'] = 'F'
GENDER['ps.Inscricao'] = 'F'
GENDER['patrimonio.InventarioTipoUsoPessoal'] = 'M'
GENDER['patrimonio.RequisicaoInventarioUsoPessoal'] = 'F'
GENDER['patrimonio.CategoriaMaterialPermanente'] = 'M'
GENDER['patrimonio.EmpenhoPermanente'] = 'M'
GENDER['patrimonio.EntradaPermanente'] = 'F'
GENDER['patrimonio.InventarioStatus'] = ''
GENDER['patrimonio.InventarioRotulo'] = 'M'
GENDER['patrimonio.InventarioCategoria'] = 'F'
GENDER['patrimonio.Inventario'] = 'M'
GENDER['patrimonio.FotoInventario'] = ''
GENDER['patrimonio.DescricaoInventario'] = ''
GENDER['patrimonio.MovimentoPatrimTipo'] = ''
GENDER['patrimonio.BaixaTipo'] = ''
GENDER['patrimonio.Baixa'] = ''
GENDER['patrimonio.Requisicao'] = 'F'
GENDER['patrimonio.RequisicaoItem'] = 'M'
GENDER['patrimonio.MovimentoPatrim'] = ''
GENDER['patrimonio.Cautela'] = ''
GENDER['patrimonio.CautelaInventario'] = ''
GENDER['patrimonio.CautelaRenovacao'] = ''
GENDER['patrimonio.InventarioValor'] = ''
GENDER['patrimonio.ConferenciaSala'] = ''
GENDER['patrimonio.ConferenciaItem'] = ''
GENDER['patrimonio.ConferenciaItemErro'] = ''
GENDER['convenios.TipoConvenio'] = 'M'
GENDER['convenios.TipoAnexo'] = 'M'
GENDER['convenios.SituacaoConvenio'] = 'F'
GENDER['convenios.Convenio'] = 'M'
GENDER['convenios.AnexoConvenio'] = 'M'
GENDER['convenios.Aditivo'] = ''
GENDER['contratos.TipoContrato'] = 'M'
GENDER['contratos.TipoLicitacao'] = 'M'
GENDER['contratos.Contrato'] = ''
GENDER['contratos.TipoPublicacao'] = 'M'
GENDER['contratos.PublicacaoContrato'] = 'F'
GENDER['contratos.TipoAnexo'] = 'M'
GENDER['contratos.AnexoContrato'] = 'M'
GENDER['contratos.TipoFiscal'] = 'M'
GENDER['contratos.Aditivo'] = ''
GENDER['contratos.Fiscal'] = 'M'
GENDER['contratos.PublicacaoAditivo'] = 'F'
GENDER['contratos.Cronograma'] = ''
GENDER['contratos.Parcela'] = 'F'
GENDER['contratos.Medicao'] = ''
GENDER['contratos.Ocorrencia'] = ''
GENDER['comum.Ano'] = 'M'
GENDER['comum.Configuracao'] = 'F'
GENDER['comum.DocumentoControleTipo'] = 'M'
GENDER['comum.DocumentoControle'] = 'M'
GENDER['comum.Pais'] = 'M'
GENDER['comum.UnidadeFederativa'] = 'F'
GENDER['comum.Municipio'] = 'M'
GENDER['comum.PessoaEndereco'] = 'M'
GENDER['comum.PessoaTelefone'] = 'M'
GENDER['comum.InscricaoFiscal'] = ''
GENDER['comum.Ocupacao'] = 'F'
GENDER['comum.PrestadorServico'] = 'M'
GENDER['comum.Predio'] = 'M'
GENDER['comum.Sala'] = 'F'
GENDER['comum.SolicitacaoReservaSala'] = 'F'
GENDER['comum.ReservaSala'] = 'F'
GENDER['comum.IndisponibilizacaoSala'] = 'F'
GENDER['comum.RepresentanteLegal'] = 'M'
GENDER['comum.GrauParentesco'] = 'M'
GENDER['comum.Pensionista'] = ''
GENDER['comum.Dependente'] = ''
GENDER['comum.Beneficio'] = 'M'
GENDER['comum.BeneficioDependente'] = 'F'
GENDER['comum.SetorTelefone'] = 'M'
GENDER['comum.Arquivo'] = ''
GENDER['comum.Notificacao'] = ''
GENDER['comum.Log'] = ''
GENDER['comum.EstadoCivil'] = 'M'
GENDER['comum.Raca'] = 'F'
GENDER['comum.TrocarSenha'] = ''
GENDER['comum.GerenciamentoGrupo'] = 'M'
GENDER['comum.UsuarioGrupo'] = 'M'
GENDER['comum.Comentario'] = 'M'
GENDER['comum.RegistroEmissaoDocumento'] = 'M'
GENDER['contenttypes.ContentType'] = ''
GENDER['remanejamento.Edital'] = 'M'
GENDER['remanejamento.EditalRecurso'] = 'M'
GENDER['remanejamento.Disciplina'] = ''
GENDER['remanejamento.DisciplinaItem'] = 'M'
GENDER['remanejamento.Inscricao'] = 'F'
GENDER['remanejamento.InscricaoItem'] = ''
GENDER['remanejamento.InscricaoDisciplinaItem'] = ''
GENDER['materiais.UnidadeMedida'] = ''
GENDER['materiais.Categoria'] = ''
GENDER['materiais.CategoriaDescritor'] = ''
GENDER['materiais.MaterialTag'] = 'F'
GENDER['materiais.Material'] = 'M'
GENDER['materiais.MaterialDescritor'] = ''
GENDER['materiais.MaterialCotacao'] = 'F'
GENDER['materiais.Requisicao'] = 'F'
GENDER['almoxarifado.UnidadeMedida'] = 'F'
GENDER['almoxarifado.CategoriaMaterialConsumo'] = 'M'
GENDER['almoxarifado.MaterialConsumo'] = 'M'
GENDER['almoxarifado.EmpenhoConsumo'] = ''
GENDER['almoxarifado.RequisicaoAlmoxUO'] = ''
GENDER['almoxarifado.RequisicaoAlmoxUOMaterial'] = ''
GENDER['almoxarifado.RequisicaoAlmoxUser'] = ''
GENDER['almoxarifado.RequisicaoAlmoxUserMaterial'] = ''
GENDER['almoxarifado.MovimentoAlmoxEntradaTipo'] = ''
GENDER['almoxarifado.MovimentoAlmoxEntrada'] = ''
GENDER['almoxarifado.MovimentoAlmoxSaidaTipo'] = ''
GENDER['almoxarifado.MovimentoAlmoxSaida'] = ''
GENDER['almoxarifado.ConfiguracaoEstoque'] = ''
GENDER['almoxarifado.LicitacaoTipo'] = 'M'
GENDER['almoxarifado.MaterialTipo'] = 'M'
GENDER['almoxarifado.EntradaTipo'] = 'M'
GENDER['almoxarifado.Entrada'] = 'F'
GENDER['almoxarifado.Empenho'] = 'M'
GENDER['rh.AcaoSaude'] = 'F'
GENDER['rh.CargoClasse'] = 'F'
GENDER['rh.GrupoCargoEmprego'] = 'M'
GENDER['rh.CargoEmprego'] = 'M'
GENDER['rh.Funcao'] = 'F'
GENDER['rh.Atividade'] = 'F'
GENDER['rh.Situacao'] = 'F'
GENDER['rh.JornadaTrabalho'] = 'F'
GENDER['rh.RegimeJuridico'] = ''
GENDER['rh.SubgrupoOcorrencia'] = ''
GENDER['rh.GrupoOcorrencia'] = 'M'
GENDER['rh.Ocorrencia'] = 'F'
GENDER['rh.AfastamentoSiape'] = 'M'
GENDER['rh.DiplomaLegal'] = 'M'
GENDER['rh.ServidorOcorrencia'] = 'F'
GENDER['rh.ServidorAfastamento'] = 'M'
GENDER['rh.NivelEscolaridade'] = 'M'
GENDER['rh.Titulacao'] = 'F'
GENDER['rh.Banco'] = ''
GENDER['rh.ServidorFuncaoHistorico'] = 'M'
GENDER['rh.PCA'] = 'M'
GENDER['rh.RegimeJuridicoPCA'] = 'M'
GENDER['rh.JornadaTrabalhoPCA'] = 'M'
GENDER['rh.PosicionamentoPCA'] = 'M'
GENDER['rh.FormaProvimentoVacancia'] = 'F'
GENDER['rh.UnidadeOrganizacional'] = 'M'
GENDER['rh.Setor'] = 'M'
GENDER['rh.Pessoa'] = ''
GENDER['rh.PessoaJuridica'] = 'F'
GENDER['rh.PessoaFisica'] = 'F'
GENDER['rh.Funcionario'] = 'M'
GENDER['rh.Servidor'] = 'M'
GENDER['rh.ServidorSetorHistorico'] = 'M'
GENDER['contracheques.ContraCheque'] = 'M'
GENDER['contracheques.Rubrica'] = 'A'
GENDER['contracheques.Beneficiario'] = 'M'
GENDER['contracheques.TipoRubrica'] = 'M'
GENDER['contracheques.ContraChequeRubrica'] = 'M'
GENDER['protocolo.Processo'] = ''
GENDER['protocolo.Tramite'] = ''
GENDER['protocolo.TempoTramite'] = 'M'
GENDER['protocolo.TempoAnalise'] = 'M'
GENDER['sessions.Session'] = ''
GENDER['chaves.Chave'] = ''
GENDER['chaves.Movimentacao'] = 'F'
GENDER['django_evolution.Version'] = ''
GENDER['django_evolution.Evolution'] = ''
GENDER['auth.Permission'] = ''
GENDER['auth.Group'] = ''
GENDER['comum.User'] = ''
GENDER['pedagogia.PeriodoResposta'] = 'M'
GENDER['pedagogia.AvaliacaoProcessualCurso'] = ''
GENDER['pedagogia.QuestionarioMatriz'] = 'M'
GENDER['pedagogia.ItemQuestionarioMatriz'] = 'F'
GENDER['pedagogia.AvaliacaoDisciplina'] = ''
GENDER['cnpq.CurriculoVittaeLattes'] = ''
GENDER['cnpq.DadoGeral'] = ''
GENDER['cnpq.Endereco'] = ''
GENDER['cnpq.FormacaoAcademicaTitulacao'] = ''
GENDER['cnpq.PalavraChave'] = ''
GENDER['cnpq.AreaConhecimento'] = ''
GENDER['cnpq.SetorAtividade'] = ''
GENDER['cnpq.ProducaoBibliografica'] = ''
GENDER['cnpq.TrabalhoEvento'] = ''
GENDER['cnpq.Artigo'] = ''
GENDER['cnpq.Livro'] = ''
GENDER['cnpq.Capitulo'] = ''
GENDER['cnpq.TextoJonalRevista'] = ''
GENDER['cnpq.PrefacioPosfacio'] = ''
GENDER['cnpq.Partitura'] = ''
GENDER['cnpq.Traducao'] = ''
GENDER['cnpq.OutraProducaoBibliografica'] = ''
GENDER['cnpq.Autor'] = ''
GENDER['cnpq.InformacaoAdicinal'] = ''
GENDER['cnpq.ProducaoTecnica'] = ''
GENDER['cnpq.Software'] = ''
GENDER['cnpq.ProdutoTecnologico'] = ''
GENDER['cnpq.ProcessoTecnica'] = ''
GENDER['cnpq.TrabalhoTecnico'] = ''
GENDER['cnpq.ApresentacaoTrabalho'] = ''
GENDER['cnpq.CartaMapaSimilar'] = ''
GENDER['cnpq.CursoCurtaDuracaoMinistrado'] = ''
GENDER['cnpq.DesMatDidativoInstrucional'] = ''
GENDER['cnpq.Editoracao'] = ''
GENDER['cnpq.ManutencaoObraArtistica'] = ''
GENDER['cnpq.Maquete'] = ''
GENDER['cnpq.OrganizacaoEventos'] = ''
GENDER['cnpq.OutraProducaoTecnica'] = ''
GENDER['cnpq.ProgramaRadioTV'] = ''
GENDER['cnpq.RelatorioPesquisa'] = ''
GENDER['cnpq.RegistroPatente'] = ''
GENDER['cnpq.OutraProducao'] = ''
GENDER['cnpq.OrientacaoConcluida'] = ''
GENDER['cnpq.DadoComplementar'] = ''
GENDER['cnpq.OrientacaoAndamento'] = ''
GENDER['ldap_backend.LdapConf'] = 'F'
GENDER['processo_seletivo.Edital'] = 'M'
GENDER['processo_seletivo.Lista'] = 'F'
GENDER['processo_seletivo.OfertaVaga'] = 'F'
GENDER['processo_seletivo.Candidato'] = 'M'
GENDER['processo_seletivo.CandidatoVaga'] = 'F'
GENDER['processo_seletivo.ConfiguracaoChamada'] = 'F'
GENDER['processo_seletivo.FaixaClassificacao'] = 'F'
GENDER['admin.LogEntry'] = ''
GENDER['projetos.AreaTematica'] = 'F'
GENDER['projetos.Tema'] = 'M'
GENDER['projetos.Parametro'] = 'M'
GENDER['projetos.Edital'] = 'M'
GENDER['projetos.ParametroEdital'] = 'M'
GENDER['projetos.CriterioAvaliacao'] = 'M'
GENDER['projetos.Recurso'] = 'M'
GENDER['projetos.FocoTecnologico'] = 'M'
GENDER['projetos.OfertaProjeto'] = 'F'
GENDER['projetos.EditalAnexo'] = ''
GENDER['projetos.AreaConhecimento'] = 'F'
GENDER['projetos.GrupoPesquisa'] = 'M'
GENDER['projetos.Projeto'] = 'M'
GENDER['projetos.TipoBeneficiario'] = 'M'
GENDER['projetos.CaracterizacaoBeneficiario'] = ''
GENDER['projetos.ProjetoEspecial'] = 'M'
GENDER['projetos.ProjetoExtensao'] = 'M'
GENDER['projetos.Avaliacao'] = 'F'
GENDER['projetos.ItemAvaliacao'] = ''
GENDER['projetos.ItemMemoriaCalculo'] = 'M'
GENDER['projetos.ParametroProjeto'] = 'M'
GENDER['projetos.RegistroGasto'] = ''
GENDER['projetos.ProjetoAnexo'] = ''
GENDER['projetos.EditalAnexoAuxiliar'] = ''
GENDER['projetos.Meta'] = 'F'
GENDER['projetos.Etapa'] = 'F'
GENDER['projetos.RegistroExecucaoEtapa'] = 'M'
GENDER['projetos.RegistroConclusaoProjeto'] = ''
GENDER['projetos.Desembolso'] = 'M'
GENDER['projetos.Participacao'] = 'F'
GENDER['projetos.FotoProjeto'] = ''
GENDER['projetos.HistoricoEquipe'] = 'M'
GENDER['gestao.PeriodoReferencia'] = ''
GENDER['gestao.Variavel'] = 'F'
GENDER['gestao.Indicador'] = 'M'
GENDER['gestao.HistoricoVariavel'] = ''
GENDER['compras.ProcessoCompra'] = 'M'
GENDER['compras.ProcessoCompraMaterial'] = ''
GENDER['compras.ProcessoCompraCampus'] = 'M'
GENDER['compras.ProcessoCompraCampusMaterial'] = 'M'
GENDER['orcamento.UnidadeMedida'] = 'F'
GENDER['orcamento.EstruturaProgramaticaFinanceira'] = 'F'
GENDER['orcamento.Credito'] = 'M'
GENDER['cursos.HorasPermitidas'] = 'F'
GENDER['cursos.Atividade'] = ''
GENDER['cursos.Curso'] = 'M'
GENDER['cursos.CotaAnualServidor'] = 'F'
GENDER['cursos.HorasTrabalhadas'] = 'F'
GENDER['cursos.InscricaoFiscal'] = 'F'
GENDER['pdi.PDI'] = 'M'
GENDER['pdi.SecaoPDI'] = 'F'
GENDER['pdi.ComissaoPDI'] = 'F'
GENDER['pdi.SecaoPDICampus'] = 'F'
GENDER['pdi.SecaoPDIInstitucional'] = 'F'
GENDER['pdi.SugestaoComunidade'] = 'F'
GENDER['pdi.SugestaoComunidadeUsuario'] = ''
GENDER['cpa.Questionario'] = 'M'
GENDER['cpa.Categoria'] = 'F'
GENDER['cpa.QuestionarioCategoria'] = 'F'
GENDER['cpa.Opcao'] = 'F'
GENDER['cpa.QuestionarioOpcao'] = 'F'
GENDER['cpa.Pergunta'] = 'F'
GENDER['cpa.Resposta'] = 'F'
GENDER['planejamento.Configuracao'] = 'F'
GENDER['planejamento.Dimensao'] = 'F'
GENDER['planejamento.OrigemRecurso'] = 'F'
GENDER['planejamento.UnidadeMedida'] = 'F'
GENDER['planejamento.UnidadeAdministrativa'] = 'F'
GENDER['planejamento.OrigemRecursoUA'] = 'F'
GENDER['planejamento.ObjetivoEstrategico'] = 'M'
GENDER['planejamento.Meta'] = 'F'
GENDER['planejamento.MetaUnidade'] = 'F'
GENDER['planejamento.AcaoProposta'] = 'A'
GENDER['planejamento.MetaUnidadeAcaoProposta'] = 'F'
GENDER['planejamento.Acao'] = 'F'
GENDER['planejamento.AcaoExtraTeto'] = 'F'
GENDER['planejamento.AcaoValidacao'] = 'M'
GENDER['planejamento.AcaoExecucao'] = 'M'
GENDER['planejamento.NaturezaDespesa'] = 'F'
GENDER['planejamento.Atividade'] = 'F'
GENDER['planejamento.AtividadeExecucao'] = 'M'
GENDER['microsoft.ConfiguracaoAcessoDreamspark'] = 'F'
GENDER['saude.Doenca'] = 'F'
GENDER['saude.Vacina'] = 'F'
GENDER['edu.ConfiguracaoPedidoMatricula'] = 'F'
GENDER['eleicao.Edital'] = 'M'
GENDER['eleicao.Eleicao'] = 'F'
GENDER['comum.Publico'] = 'M'
GENDER['eleicao.Chapa'] = 'F'
GENDER['eleicao.Candidato'] = 'M'
GENDER['eleicao.Voto'] = 'M'
GENDER['saude.DificuldadeOral'] = 'F'


STATE_CHOICES = (
    ('AC', 'Acre'),
    ('AL', 'Alagoas'),
    ('AP', 'Amapá'),
    ('AM', 'Amazonas'),
    ('BA', 'Bahia'),
    ('CE', 'Ceará'),
    ('DF', 'Distrito Federal'),
    ('ES', 'Espírito Santo'),
    ('GO', 'Goiás'),
    ('MA', 'Maranhão'),
    ('MT', 'Mato Grosso'),
    ('MS', 'Mato Grosso do Sul'),
    ('MG', 'Minas Gerais'),
    ('PA', 'Pará'),
    ('PB', 'Paraíba'),
    ('PR', 'Paraná'),
    ('PE', 'Pernambuco'),
    ('PI', 'Piauí'),
    ('RJ', 'Rio de Janeiro'),
    ('RN', 'Rio Grande do Norte'),
    ('RS', 'Rio Grande do Sul'),
    ('RO', 'Rondônia'),
    ('RR', 'Roraima'),
    ('SC', 'Santa Catarina'),
    ('SP', 'São Paulo'),
    ('SE', 'Sergipe'),
    ('TO', 'Tocantins'),
)


def get_nome_estado(sigla):
    for estado in STATE_CHOICES:
        if estado[0] == sigla:
            return estado[1]
    return None
