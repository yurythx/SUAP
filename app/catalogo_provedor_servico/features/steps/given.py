import datetime

from behave import given
from django.contrib.auth.models import Group

from catalogo_provedor_servico.features import dados
from catalogo_provedor_servico.models import Servico, ServicoEquipe, Solicitacao, SolicitacaoEtapa
from comum.models import Ano, Configuracao, Raca
from documento_eletronico.models import HipoteseLegal, NivelAcesso, TipoDocumento
from edu.models import (
    Aluno,
    AreaCapes,
    Cartorio,
    Cidade,
    CursoCampus,
    Diretoria,
    Estado,
    EstruturaCurso,
    FormaIngresso,
    HistoricoSituacaoMatricula,
    HistoricoSituacaoMatriculaPeriodo,
    LinhaPesquisa,
    MatriculaPeriodo,
    Matriz,
    MatrizCurso,
    Modalidade,
    NaturezaParticipacao,
    NivelEnsino,
    OrgaoEmissorRg,
    RegistroEmissaoDiploma,
    SequencialMatricula,
    SituacaoMatricula,
    SituacaoMatriculaPeriodo,
    Turno,
)
from edu.models.cadastros_gerais import Pais
from processo_eletronico.models import ModeloDespacho, Processo, TipoProcesso
from processo_seletivo.models import Candidato, CandidatoVaga, Edital, EditalPeriodoLiberacao, Lista, OfertaVaga, OfertaVagaCurso, Vaga
from rh.models import CargoEmprego, Papel, PessoaFisica, Servidor, Setor, UnidadeOrganizacional


def mudar_data(context, data):
    context.execute_steps(f'Quando a data do sistema for "{data}"')


def criar_usuarios(context):
    context.execute_steps(
        """Dado os seguintes usuários
    | Nome                                  | Matrícula | Setor    | Lotação  | Email                               | CPF            | Senha | Grupo                                      |
    | Gerente Sistemico do Catalogo Digital | 300001    | CEN      | CEN      | gerente_catalogo@ifrn.edu.br        | 994.034.470-87 | abcd  | Gerente Sistemico do Catalogo Digital      |
    | Avaliador do Catálogo Digital         | 300002    | CEN      | CEN      | chefe_setor@ifrn.edu.br             | 211.659.640-82 | abcd  | Avaliador do Catálogo Digital              |
    """
    )

    servidor = Servidor.objects.get(matricula='300001')
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Servidor'))
    user.save()

    servidor = Servidor.objects.get(matricula='300002')
    user = servidor.get_user()
    user.groups.add(Group.objects.get(name='Servidor'))
    user.save()


def criar_servicos():
    servico_ead, _ = Servico.objects.get_or_create(
        id_servico_portal_govbr=6176,
        icone='fa fa-question-circle',
        titulo='Matrícula EAD',
        descricao='Este serviço permite que um candidato possa fazer uma matrícula de ensino a distancia',
        ativo=True,
    )

    servico_diploma, _ = Servico.objects.get_or_create(
        id_servico_portal_govbr=6024,
        icone='fa fa-question-circle',
        titulo='Emissão de 2a Via de Diploma',
        descricao='Este serviço permite que um aluno formado possa solicitar a emissão de segunda via de diploma',
        ativo=True,
    )

    servico_processo, _ = Servico.objects.get_or_create(
        id_servico_portal_govbr=10056,
        icone='fa fa-question-circle',
        titulo='Protocolar Documentos',
        descricao='Este serviço permite que um cidadão possa protocolar documentos junto a instituição',
        ativo=True,
    )

    gerente = Servidor.objects.get(matricula='300001').get_vinculo()
    avaliador = Servidor.objects.get(matricula='300002').get_vinculo()

    ServicoEquipe.objects.get_or_create(servico=servico_ead, vinculo=gerente, campus=gerente.setor.uo)
    ServicoEquipe.objects.get_or_create(servico=servico_ead, vinculo=avaliador, campus=avaliador.setor.uo)

    ServicoEquipe.objects.get_or_create(servico=servico_diploma, vinculo=gerente, campus=gerente.setor.uo)
    ServicoEquipe.objects.get_or_create(servico=servico_diploma, vinculo=avaliador, campus=avaliador.setor.uo)

    ServicoEquipe.objects.get_or_create(servico=servico_processo, vinculo=gerente, campus=gerente.setor.uo)
    ServicoEquipe.objects.get_or_create(servico=servico_processo, vinculo=avaliador, campus=avaliador.setor.uo)

    Configuracao.objects.get_or_create(app='catalogo_provedor_servico', chave='codigo_protocolar_documento', valor='10056')
    Configuracao.objects.get_or_create(app='catalogo_provedor_servico', chave='codigo_segunda_via_diploma', valor='6024')
    Configuracao.objects.get_or_create(app='catalogo_provedor_servico', chave='codigo_matricula_ead', valor='6176')


def criar_solicitacoes():
    servico_ead = Servico.objects.get(id_servico_portal_govbr=6176)
    servico_diploma = Servico.objects.get(id_servico_portal_govbr=6024)
    servico_processo = Servico.objects.get(id_servico_portal_govbr=10056)

    data_criacao = datetime.datetime(2020, 5, 4, 14, 00)
    uo = UnidadeOrganizacional.objects.get(sigla='CEN')

    solicitacao_ead, _ = Solicitacao.objects.get_or_create(
        servico=servico_ead,
        cpf='170.218.330-08',
        nome='Marcos Paulo',
        numero_total_etapas=5,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        status=Solicitacao.STATUS_EM_ANALISE,
        status_detalhamento='Em análise',
        uo=uo,
    )
    _etapa_ead_1, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_ead, data_criacao=data_criacao, data_ultima_atualizacao=data_criacao, numero_etapa=1, dados=dados.dados_ead_etapa_1
    )
    _etapa_ead_2, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_ead, data_criacao=data_criacao, data_ultima_atualizacao=data_criacao, numero_etapa=2, dados=dados.dados_ead_etapa_2
    )
    _etapa_ead_3, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_ead, data_criacao=data_criacao, data_ultima_atualizacao=data_criacao, numero_etapa=3, dados=dados.dados_ead_etapa_3
    )
    _etapa_ead_4, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_ead, data_criacao=data_criacao, data_ultima_atualizacao=data_criacao, numero_etapa=4, dados=dados.dados_ead_etapa_4
    )
    _etapa_ead_5, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_ead, data_criacao=data_criacao, data_ultima_atualizacao=data_criacao, numero_etapa=5, dados=dados.dados_ead_etapa_5
    )

    solicitacao_diploma, _ = Solicitacao.objects.get_or_create(
        servico=servico_diploma,
        cpf='947.767.240-81',
        nome='Maria Eduarda',
        numero_total_etapas=1,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        status=Solicitacao.STATUS_EM_ANALISE,
        status_detalhamento='Em análise',
        uo=uo,
    )
    _etapa_diploma_1, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_diploma,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        numero_etapa=1,
        dados=dados.dados_diploma_etapa_1,
    )

    solicitacao_processo, _ = Solicitacao.objects.get_or_create(
        servico=servico_processo,
        cpf='162.909.810-80',
        nome='Carlos Eduardo',
        numero_total_etapas=2,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        status=Solicitacao.STATUS_EM_ANALISE,
        status_detalhamento='Em análise',
        uo=uo,
    )
    _etapa_processo_1, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_processo,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        numero_etapa=1,
        dados=dados.dados_processo_etapa_1,
    )
    _etapa_processo_2, _ = SolicitacaoEtapa.objects.get_or_create(
        solicitacao=solicitacao_processo,
        data_criacao=data_criacao,
        data_ultima_atualizacao=data_criacao,
        numero_etapa=2,
        dados=dados.dados_processo_etapa_2,
    )


def criar_edital():
    ano, _ = Ano.objects.get_or_create(ano=2020)
    _orgao_emissao_rg, _ = OrgaoEmissorRg.objects.get_or_create(id=40, nome='SSP')
    data_fim = datetime.datetime(2020, 6, 1, 14, 00)
    data_fim_avaliacao = datetime.datetime(2020, 6, 2, 14, 00)
    data_inicio = datetime.datetime(2020, 5, 1, 14, 00)
    diretoria, _ = Diretoria.objects.get_or_create(setor=Setor.objects.suap_ativos().get(sigla='CEN'))
    natureza, _ = NaturezaParticipacao.objects.get_or_create(descricao='Presencial EAD')
    areacapes, _ = AreaCapes.objects.get_or_create(descricao='Educação EAD')
    estado, _ = Estado.objects.get_or_create(id=24, nome='Rio Grande do Norte')
    pais, _ = Pais.objects.get_or_create(nome='Brasil')
    cidade, _ = Cidade.objects.get_or_create(
        id=2401403, nome='Natal EAD', estado=estado, cep_inicial='59000-000', cep_final='59999-999', codigo='2401403', pais=pais
    )
    _cartorio, _ = Cartorio.objects.get_or_create(id=7602, nome='1o. cartório de notas de natal', cidade=cidade, serventia='Cartório de Notas')
    _raca, _ = Raca.objects.get_or_create(id=101, descricao='Parda EAD', codigo_siape=4)
    nivel_ensino = NivelEnsino.objects.get(pk=4)
    linha_pesquisa = LinhaPesquisa.objects.create(descricao='Linha de Pesquisa para Matrícula EAD CEN')
    turno, _ = Turno.objects.get_or_create(id=101, descricao='Noturno EAD')

    edital, _ = Edital.objects.get_or_create(
        codigo='11',
        descricao='Edital 11 - Matrícula EAD 2020',
        ano=ano,
        semestre=1,
        data_encerramento=data_fim.date(),
        qtd_vagas=500,
        qtd_inscricoes=1000,
        qtd_inscricoes_confirmadas=700,
    )

    EditalPeriodoLiberacao.objects.get_or_create(
        edital=edital, uo=diretoria.setor.uo, data_inicio_matricula=data_inicio, data_fim_matricula=data_fim, data_limite_avaliacao=data_fim_avaliacao
    )

    curso_campus, _ = CursoCampus.objects.get_or_create(
        descricao='Especialização em Educação Remota EAD',
        descricao_historico='Especialização em Educação Remota EAD',
        ano_letivo=ano,
        periodo_letivo=1,
        data_inicio=datetime.datetime.strptime('15/03/2020', '%d/%m/%Y'),
        ativo=True,
        codigo='10102',
        modalidade=Modalidade.objects.get(descricao='Especialização'),
        area_capes=areacapes,
        periodicidade=CursoCampus.PERIODICIDADE_SEMESTRAL,
        diretoria=diretoria,
        emite_diploma=True,
        fator_esforco_curso=1,
        titulo_certificado_masculino='Especialista em Educação Remota',
        titulo_certificado_feminino='Especialista em Educação Remota',
    )

    estrutura, _ = EstruturaCurso.objects.get_or_create(
        descricao='Especialização e Aperfeiçoamento',
        ativo=True,
        tipo_avaliacao=EstruturaCurso.TIPO_AVALIACAO_SERIADO,
        limite_reprovacao=10,
        criterio_avaliacao=EstruturaCurso.CRITERIO_AVALIACAO_NOTA,
        media_aprovacao_sem_prova_final=60,
        media_evitar_reprovacao_direta=20,
        media_aprovacao_avaliacao_final=60,
        percentual_frequencia=75,
        ira=EstruturaCurso.IRA_PONDERADA_POR_CH,
        qtd_periodos_conclusao=4,
        qtd_max_reprovacoes_periodo=0,
        qtd_max_reprovacoes_disciplina=0,
        qtd_trancamento_voluntario=2,
        numero_max_certificacoes=4,
        media_certificacao_conhecimento=60,
    )

    matriz, _ = Matriz.objects.get_or_create(
        descricao='Especialização em Educação Remota EAD - Campus CEN',
        ano_criacao=ano,
        periodo_criacao=1,
        data_inicio=datetime.datetime.strptime('10/03/2020', '%d/%m/%Y'),
        qtd_periodos_letivos=3,
        nivel_ensino=nivel_ensino,
        estrutura=estrutura,
        natureza_participacao=natureza,
        ch_componentes_obrigatorios=200,
        ch_componentes_optativos=50,
        ch_componentes_eletivos=50,
        ch_seminarios=10,
        ch_pratica_profissional=10,
        ch_atividades_complementares=10,
        ch_atividades_aprofundamento=10,
        ch_atividades_extensao=10,
        ch_componentes_tcc=5,
        ch_pratica_como_componente=0,
        ch_visita_tecnica=0,
        pk=101,
    )

    _matriz_curso, _ = MatrizCurso.objects.get_or_create(
        curso_campus=curso_campus,
        matriz=matriz,
    )

    oferta_vaga_curso, _ = OfertaVagaCurso.objects.get_or_create(
        edital=edital,
        curso_campus=curso_campus,
        linha_pesquisa=linha_pesquisa,
        turno=turno,
        qtd_inscritos=10,
    )

    forma_ingresso, _ = FormaIngresso.objects.get_or_create(
        descricao='Prova', ativo=True, classificacao_censup=FormaIngresso.ENEM, classificacao_educacenso=4
    )

    lista, _ = Lista.objects.get_or_create(codigo='1', descricao='Todos', forma_ingresso=forma_ingresso, edital=edital)

    oferta_vaga, _ = OfertaVaga.objects.get_or_create(oferta_vaga_curso=oferta_vaga_curso, lista=lista, qtd=10)

    vaga, _ = Vaga.objects.get_or_create(oferta_vaga=oferta_vaga)

    candidato, _ = Candidato.objects.get_or_create(
        edital=edital,
        inscricao='20200114-1',
        cpf='170.218.330-08',
        nome='Marcos Paulo',
        email='marcos@paulo.com',
        telefone='(84) 99999-9999',
        curso_campus=curso_campus,
        turno=turno,
    )

    _candidato_vaga, _ = CandidatoVaga.objects.get_or_create(
        id=702181,
        candidato=candidato,
        oferta_vaga=oferta_vaga,
        vaga=vaga,
        classificacao=1,
        aprovado=True,
    )


def criar_aluno():
    cpf = '947.767.240-81'
    pessoa_fisica = PessoaFisica()
    pessoa_fisica.cpf = cpf
    pessoa_fisica.nome_registro = 'Maria Eduarda'
    pessoa_fisica.sexo = 'F'
    pessoa_fisica.nascimento_data = datetime.datetime(1990, 10, 10)
    pessoa_fisica.save()

    cidade = Cidade.objects.get(id=2401403)
    ano = Ano.objects.filter(ano=2020).first()
    ingresso = FormaIngresso.objects.first()
    matriz_curso = MatrizCurso.objects.first()
    turno, _ = Turno.objects.get_or_create(id=3, descricao='Matutino')

    aluno = Aluno()
    aluno.id = 96439
    aluno.periodo_atual = 1
    aluno.pessoa_fisica = pessoa_fisica
    aluno.estado_civil = 'Solteiro'
    aluno.nome_mae = 'Maria da Silva'
    aluno.logradouro = 'Rua abcd'
    aluno.numero = '123'
    aluno.bairro = 'qwer'
    aluno.cidade = cidade
    aluno.tipo_zona_residencial = '1'
    aluno.nacionalidade = 'Brasileira'
    aluno.naturalidade = cidade
    aluno.ano_letivo = ano
    aluno.periodo_letivo = 1
    aluno.turno = turno
    aluno.forma_ingresso = ingresso
    aluno.curso_campus = matriz_curso.curso_campus
    aluno.matriz = matriz_curso.matriz
    aluno.situacao = SituacaoMatricula.objects.get(pk=SituacaoMatricula.FORMADO)
    aluno.ano_let_prev_conclusao = 2020
    prefixo = f'{aluno.ano_letivo}{aluno.periodo_letivo}{aluno.curso_campus.codigo}'
    aluno.matricula = SequencialMatricula.proximo_numero(prefixo)
    aluno.save()
    v = aluno.get_vinculo()
    if v:
        if Raca.objects.exists():
            v.raca = Raca.objects.first()
        v.email_pessoal = 'maria_eduarda@ifrn.edu.br.com'
        v.save(update_fields=['raca', 'email_pessoal'])

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
    matricula_periodo.situacao = SituacaoMatriculaPeriodo.objects.get(pk=SituacaoMatriculaPeriodo.APROVADO)
    matricula_periodo.save()

    hsmp = HistoricoSituacaoMatriculaPeriodo()
    hsmp.matricula_periodo = matricula_periodo
    hsmp.situacao = matricula_periodo.situacao
    hsmp.data = aluno.data_matricula
    hsmp.save()

    _red, _ = RegistroEmissaoDiploma.objects.get_or_create(aluno=aluno, via=1)


def criar_papeis():
    servidor = Servidor.objects.get(matricula='300002')
    setor_suap = Setor.objects.suap_ativos().filter(sigla='CEN', codigo__isnull=True).first()
    data = datetime.datetime(2020, 1, 1)
    papel = Papel.objects.filter(vinculo=servidor.get_vinculo(), descricao='Avaliador do Catálogo Digital').first()
    if not papel:
        papel = Papel()
        papel.vinculo = servidor.get_vinculo()
        papel.tipo_papel = Papel.TIPO_PAPEL_CARGO
        papel.descricao = 'Avaliador do Catálogo Digital'
        papel.detalhamento = 'Avaliador do Catálogo Digital'
        papel.portaria = '101/2020'
        papel.data_inicio = data
        papel.setor_suap = setor_suap
        papel.papel_content_object = CargoEmprego.objects.all().first()
        papel.save()


def criar_tipo_processo():
    tipo_processo, _ = TipoProcesso.objects.get_or_create(nome='Segunda Via de Diploma', nivel_acesso_default=Processo.NIVEL_ACESSO_PUBLICO)
    Configuracao.objects.get_or_create(app='processo_eletronico', chave='tipo_processo_solicitar_emissao_diploma', valor=tipo_processo.pk)

    tipo_documento, _ = TipoDocumento.objects.get_or_create(
        nome='Requerimento Segunda Via de Diploma',
        sigla='REQ',
    )
    Configuracao.objects.get_or_create(app='documento_eletronico', chave='tipo_documento_requerimento', valor=tipo_documento.pk)

    _modelo_despacho, _ = ModeloDespacho.objects.get_or_create(cabecalho='IFRN\n', rodape='\n------\n')
    HipoteseLegal.objects.get_or_create(
        id=100, nivel_acesso=NivelAcesso.RESTRITO.name, descricao='Documento Severamente Restrito', base_legal='Lei 123789/2020'
    )

    Configuracao.objects.get_or_create(app='processo_eletronico', chave='hipotese_legal_documento_abertura_requerimento', valor=100)

    tipo_processo, _ = TipoProcesso.objects.get_or_create(
        nome='Protocolo Eletrônico Demanda Externa', nivel_acesso_default=Processo.NIVEL_ACESSO_PUBLICO
    )
    Configuracao.objects.get_or_create(app='processo_eletronico', chave='tipo_processo_demanda_externa_do_cidadao', valor=tipo_processo.pk)


@given('os cadastros básicos do catálogo digital')
def step_cadastros(context):
    # criar_usuarios(context)
    criar_servicos()
    criar_solicitacoes()
    criar_edital()
    criar_aluno()
    criar_papeis()
    criar_tipo_processo()


@given('informações corrigidas da Matrícula EAD')
def step_cadastros_alteracao(context):
    data_alteracao = datetime.datetime(2020, 5, 5)
    solicitacao_ead = Solicitacao.objects.get(cpf='170.218.330-08')
    solicitacao_ead.status = Solicitacao.STATUS_DADOS_CORRIGIDOS
    solicitacao_ead.status_detalhamento = 'Dados Corrigidos'
    solicitacao_ead.data_ultima_atualizacao = data_alteracao
    solicitacao_ead.save()
    SolicitacaoEtapa.objects.filter(solicitacao=solicitacao_ead, numero_etapa=2).update(
        data_ultima_atualizacao=data_alteracao, dados=dados.dados_ead_etapa_2_corrigido
    )
