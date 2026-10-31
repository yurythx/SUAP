"""Fixtures de fluxo dos projetos de Pesquisa.

O ciclo de vida de um projeto é um pipeline conduzido por endpoints reais:

    edital (gerente) -> projeto (coordenador) -> enviar
        -> pré-selecionar (pré-avaliador) -> avaliar (avaliadores)
        -> distribuir bolsas -> executar -> concluir -> finalizar

Cada etapa é montada como fixture reaproveitando os *payloads* já validados do
fluxo antigo. Os testes (ver test_fluxo_pesquisa.py) apenas disparam a ação em
exame e verificam a mudança de estado do projeto — sem a antiga matriz de
visibilidade de botões, que era detalhe de UI.
"""

import datetime

import pytest
from django.contrib.auth.models import Group, Permission

from cnpq.models import CurriculoVittaeLattes, DadoComplementar, DadoGeral, GrupoPesquisa
from comum.models import Ano, Configuracao
from comum.pytest_fixtures import assert_no_validation_errors
from comum.tests.fluxo_edital_helpers import (
    criar_servidor_basico,
    hoje as _hoje,
    seed_alunos_basicos,
    seed_financeiro_basico,
    set_periodo_execucao,
    set_periodo_inscricao,
    set_periodo_pre_selecao,
    set_periodo_selecao,
    str_data as _str_data,
)
from edu.models import Aluno
from financeiro.models import NaturezaDespesa
from pesquisa.models import (
    AvaliadorIndicado,
    Edital,
    OrigemRecursoEdital,
    TipoVinculo,
)
from rh.models import AreaConhecimento, Titulacao, UnidadeOrganizacional
from rh.tests.factories import ServidorFactory, SetorFactory

GRUPO_AVALIADOR = 'Avaliador Sistêmico de Projetos de Pesquisa'
GRUPO_PRE_AVALIADOR = 'Coordenador de Pesquisa'
GRUPO_GERENTE_SISTEMICO = 'Diretor de Pesquisa'
GRUPO_COORDENADOR_PROJETO = 'Servidor'
INSTITUICAO_SIGLA = 'IFRN'


# --- Cadastros básicos -------------------------------------------------------


def _carga_inicial():
    areaconhecimento = AreaConhecimento.objects.get_or_create(codigo='10000003', descricao='CIÊNCIAS EXATAS E DA TERRA')[0]
    AreaConhecimento.objects.get_or_create(codigo='10100008', descricao='MATEMÁTICA', superior=areaconhecimento)
    seed_financeiro_basico()
    OrigemRecursoEdital.objects.get_or_create(descricao='PROPI')
    Titulacao.objects.get_or_create(codigo='26', defaults={'nome': 'Doutor', 'titulo_masculino': 'Dr.', 'titulo_feminino': 'Dra.'})
    # O form do projeto filtra os grupos do Lattes por `instituicao == Configuracao
    # comum/instituicao_sigla` — essa configuração vinha do seed do `suap_data`. Sem ela o
    # filtro casa com nada e o campo "Grupo de Pesquisa" recusa qualquer escolha.
    Configuracao.objects.get_or_create(app='comum', chave='instituicao_sigla', defaults={'valor': INSTITUICAO_SIGLA})
    GrupoPesquisa.objects.get_or_create(codigo='01', descricao='Grupo de Pesquisa', instituicao=INSTITUICAO_SIGLA)
    seed_alunos_basicos()


def _criar_curriculo_lattes(servidor, numero_identificador, cpf):
    """Lattes mínimo — pré-requisito de `Edital.pode_submeter_projeto` para servidores."""
    curriculo = CurriculoVittaeLattes.objects.create(sistema_origem_xml='', numero_identificador=numero_identificador)
    curriculo.dado_complementar = DadoComplementar.objects.create()
    curriculo.dado_geral = DadoGeral.objects.create(
        nome_completo=servidor.nome,
        nome_citacao=servidor.nome,
        nacionalidade='Brasileiro',
        cpf=cpf,
        pais_nascimento='Brasil',
        uf_nascimento='RN',
        cidade_nascimento='Natal',
        sexo='F',
        permissao_divulgacao='Sim',
    )
    curriculo.vinculo = servidor.get_vinculo()
    curriculo.grupos_pesquisa.add(GrupoPesquisa.objects.first())
    curriculo.save()
    return curriculo


@pytest.fixture
def usuarios(db, sync_permissions):
    """Servidores e perfis dos atores do fluxo de pesquisa.

    Coordenador, gerente sistêmico, pré-avaliador e avaliador — os quatro no mesmo campus,
    porque as ofertas do edital são por campus. Como um `SetorFactory()` sem superior vira
    campus próprio, todos compartilham o setor do coordenador; `outro_campus` é o segundo
    campus ofertado.

    Escopo de FUNÇÃO: era class-scoped e commitava via `django_db_blocker.unblock`, então
    os servidores e o seed sobreviviam aos testes seguintes do mesmo worker. Foi assim que
    a linha 'Matriculado' criada aqui colidiu, noutro módulo, com o seed do `light_data`.
    """
    from types import SimpleNamespace

    _carga_inicial()

    coordenador = ServidorFactory()
    servidor_gerente = ServidorFactory(setor=coordenador.setor)

    gerente = servidor_gerente.get_user()
    gerente.groups.add(Group.objects.get(name=GRUPO_GERENTE_SISTEMICO))
    gerente.user_permissions.add(
        Permission.objects.get(content_type__app_label='pesquisa', codename='pode_gerenciar_edital'),
        Permission.objects.get(content_type__app_label='pesquisa', codename='tem_acesso_sistemico'),
    )

    pre_avaliador = criar_servidor_basico('12', 'Servidor A2', '449.717.558-88', b'12', setor=coordenador.setor)
    pre_avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

    avaliador = criar_servidor_basico('13', 'Servidor A3', '313.444.320-18', b'13', setor=coordenador.setor, titulacao=Titulacao.objects.first())
    avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_AVALIADOR))

    area = AreaConhecimento.objects.get(codigo='10000003')
    coordenador.areas_de_conhecimento.add(area)
    # Lattes é pré-requisito de `Edital.pode_submeter_projeto`; sem grupo de pesquisa o
    # form do projeto recusa a escolha.
    _criar_curriculo_lattes(coordenador, '01', '111.111.111-11')
    _criar_curriculo_lattes(servidor_gerente, '02', '222.222.222-22')

    outro_campus = SetorFactory().uo

    return SimpleNamespace(
        coordenador=coordenador,
        gerente=servidor_gerente,
        pre_avaliador=pre_avaliador,
        avaliador=avaliador,
        outro_campus=outro_campus,
    )


@pytest.fixture
def client(suap_client):
    return suap_client


def _login(client, servidor):
    client.logout()
    assert client.login(user=servidor.get_user())


def _login_gerente(client, gerente):
    """Login do gerente limpando o cache de permissões (perfis adicionados na fixture)."""
    client.logout()
    assert client.login(user=gerente.get_user())
    user = client.user
    for attr in ('_group_perm_cache', '_user_perm_cache', '_perm_cache'):
        if hasattr(user, attr):
            delattr(user, attr)


# --- Montagem do edital (gerente) --------------------------------------------


def _criar_edital(client, gerente):
    edital = Edital()
    edital.titulo = 'Edital 001 Pesquisa'
    edital.descricao = 'Descrição do edital 001'
    edital.tipo_edital = Edital.PESQUISA
    edital.forma_selecao = Edital.CAMPUS
    edital.qtd_bolsa_servidores = 1
    edital.qtd_bolsa_alunos = 1
    edital.inicio_inscricoes = '2012-01-01 00:00:00'
    edital.fim_inscricoes = '2012-01-01 23:59:00'
    edital.inicio_pre_selecao = '2012-04-01 00:00:00'
    edital.inicio_selecao = '2012-05-01 00:00:00'
    edital.fim_selecao = '2012-06-01 00:00:00'
    edital.data_recurso = '2012-06-01 00:00:00'
    edital.divulgacao_selecao = '2012-07-01 00:00:00'
    edital.coordenador_pode_receber_bolsa = '1'
    edital.participa_aluno = '1'
    edital.qtd_maxima_alunos = 2
    edital.qtd_maxima_alunos_bolsistas = 1
    edital.participa_servidor = '1'
    edital.qtd_maxima_servidores = 2
    edital.qtd_maxima_servidores_bolsistas = 1
    edital.qtd_anos_anteriores_publicacao = 3
    edital.peso_avaliacao_lattes_coordenador = 0
    edital.peso_avaliacao_projeto = 100
    edital.ch_semanal_coordenador = 5
    edital.nota_corte_projeto_fluxo_continuo = 4
    edital.tempo_maximo_meses_curriculo_desatualizado = 6
    edital.formato = Edital.FORMATO_COMPLETO
    edital.lattes_obrigatorio = False
    edital.cadastrado_por_vinculo = gerente.get_user().get_vinculo()
    edital.cadastrado_em = datetime.datetime.now()
    edital.save()
    edital.titulacoes_avaliador.add(Titulacao.objects.first())
    return edital


def _adicionar_anexo_auxiliar(client, edital):
    from pesquisa.models import EditalAnexoAuxiliar

    client.post(f'/pesquisa/adicionar_anexo_auxiliar/{edital.pk}/', {'nome': 'Anexo I', 'descricao': 'Termo de compromisso', 'ordem': 1})
    assert EditalAnexoAuxiliar.objects.filter(edital=edital).exists()


def _adicionar_anexo(client, edital):
    from pesquisa.models import EditalAnexo

    client.post(
        f'/pesquisa/adicionar_anexo/{edital.pk}/',
        {
            'nome': 'Anexo I',
            'descricao': 'Termo de compromisso',
            'edital': edital.pk,
            'tipo_membro': EditalAnexo.SERVIDOR_ADMINISTRATIVO,
            'vinculo': TipoVinculo.BOLSISTA,
            'ordem': 1,
        },
    )
    assert EditalAnexo.objects.filter(edital=edital).exists()


def _adicionar_recurso(client, edital, codigo_despesa):
    from pesquisa.models import Recurso

    natureza = NaturezaDespesa.objects.get(codigo=codigo_despesa)
    origem = OrigemRecursoEdital.objects.first()
    resposta = client.post(f'/pesquisa/adicionar_recurso/{edital.pk}/', {'origem_recurso': origem.pk, 'valor': '1000,00', 'despesa': natureza.pk})
    assert_no_validation_errors(resposta)
    return Recurso.objects.filter(edital=edital).latest('id')


def _adicionar_oferta(client, edital, uo):
    from pesquisa.models import BolsaDisponivel

    resposta = client.post(f'/pesquisa/adicionar_oferta_projeto/{edital.pk}/', {'campi': uo.pk, 'num_maximo_ic': '2', 'num_maximo_pesquisador': '2'})
    assert_no_validation_errors(resposta)
    return BolsaDisponivel.objects.latest('id')


def _adicionar_criterio_avaliacao(client, edital):
    from pesquisa.models import CriterioAvaliacao

    resposta = client.post(
        f'/pesquisa/adicionar_criterio_avaliacao/{edital.pk}/',
        {'edital': edital.pk, 'descricao': 'Adequação da proposta ao tema', 'pontuacao_maxima': '10,00', 'ordem_desempate': 1},
    )
    assert_no_validation_errors(resposta)
    assert CriterioAvaliacao.objects.filter(edital=edital).exists()


@pytest.fixture
def edital(client, usuarios):
    """Edital de pesquisa publicado, com anexos, recursos, ofertas e critérios."""
    _login_gerente(client, usuarios.gerente)
    edital = _criar_edital(client, usuarios.gerente)
    _adicionar_anexo_auxiliar(client, edital)
    _adicionar_anexo(client, edital)
    for codigo in ('339030', '339018', '339020'):
        _adicionar_recurso(client, edital, codigo)
    _adicionar_oferta(client, edital, usuarios.coordenador.setor.uo)
    _adicionar_oferta(client, edital, usuarios.outro_campus)
    _adicionar_criterio_avaliacao(client, edital)
    return edital


# --- Montagem do projeto (coordenador) ---------------------------------------


def _adicionar_projeto(client, edital):
    from pesquisa.models import Projeto

    uo = edital.bolsadisponivel_set.all()[0].uo
    area = AreaConhecimento.objects.filter(superior__isnull=False)[0]
    grupo = GrupoPesquisa.objects.first()
    resposta = client.post(
        f'/pesquisa/adicionar_projeto/{edital.pk}/',
        {
            'edital': edital.pk,
            'uo': uo.pk,
            'titulo': 'Projeto 001 Pesquisa',
            'area_conhecimento': area.pk,
            'justificativa': 'Justificativa do Projeto',
            'resumo': 'Resumo do Projeto',
            'objetivo_geral': 'Objetivo do Projeto',
            'metodologia': 'Metodologia do Projeto',
            'acompanhamento_e_avaliacao': 'Acompanhamento e Avaliação do Projeto',
            'resultados_esperados': 'Resultados Esperados do Projeto',
            'inicio_execucao': _str_data(),
            'fim_execucao': _str_data(365),
            'grupo_pesquisa': grupo.pk,
            'fundamentacao_teorica': 'Fundamentação teorica do projeto',
            'referencias_bibliograficas': 'Referencias bibliograficas do projeto',
            'introducao': 'Introdução do Projeto',
            'palavras_chaves': 'palavras 1; palavras 2',
            'precisa_cep': False,
            'precisa_ceua': False,
            'precisa_sisgen': False,
            'precisa_sisbio': False,
            'vinculado_laboratorio_multiusuario': False,
            'tem_ods': False,
        },
    )
    assert_no_validation_errors(resposta)
    return Projeto.objects.get(titulo='Projeto 001 Pesquisa')


def _adicionar_participante_aluno(client, projeto, aluno, vinculo='Bolsista'):
    from pesquisa.models import Participacao

    resposta = client.post(
        f'/pesquisa/adicionar_participante_aluno/{projeto.pk}/',
        {'vinculo': vinculo, 'carga_horaria': '10', 'aluno': aluno.pk, 'data': _str_data()},
    )
    assert_no_validation_errors(resposta)
    return Participacao.objects.latest('id')


def _adicionar_participante_servidor(client, projeto, servidor):
    from pesquisa.models import Participacao

    resposta = client.post(
        f'/pesquisa/adicionar_participante_servidor/{projeto.pk}/',
        {'vinculo': 'Bolsista', 'carga_horaria': '10', 'servidor': servidor.pk, 'data': _str_data()},
    )
    assert_no_validation_errors(resposta)
    return Participacao.objects.latest('id')


def _adicionar_meta(client, projeto, ordem='1', descricao='Meta 1'):
    from pesquisa.models import Meta

    client.post(f'/pesquisa/adicionar_meta/{projeto.pk}/', {'ordem': ordem, 'descricao': descricao})
    return Meta.objects.latest('id')


def _adicionar_etapa(client, meta, ordem='1', descricao='Atividade 1'):
    from pesquisa.models import Etapa, Participacao

    participante = Participacao.objects.filter(projeto=meta.projeto)[0]
    client.post(
        f'/pesquisa/adicionar_etapa/{meta.pk}/',
        {
            'ordem': ordem,
            'descricao': descricao,
            'unidade_medida': 'Aluno',
            'qtd': '50',
            'indicadores_qualitativos': 'Nota das avaliações',
            'responsavel': participante.pk,
            'inicio_execucao': _str_data(),
            'fim_execucao': _str_data(10),
        },
    )
    return Etapa.objects.latest('id')


def _adicionar_item_memoria(client, projeto):
    from pesquisa.models import ItemMemoriaCalculo

    natureza = NaturezaDespesa.objects.get(codigo='339030')
    client.post(
        f'/pesquisa/memoria_calculo/{projeto.pk}/',
        {
            'projeto': projeto.pk,
            'despesa': natureza.pk,
            'descricao': 'Descrição da despesa',
            'unidade_medida': 'Unid',
            'qtd': '10',
            'valor_unitario': '50,00',
        },
    )
    return ItemMemoriaCalculo.objects.latest('id')


def _adicionar_desembolso(client, item):
    from pesquisa.models import Desembolso

    ano = Ano.objects.get_or_create(ano=str(datetime.datetime.now().year))[0]
    resposta = client.post(f'/pesquisa/adicionar_desembolso/{item.projeto.pk}/', {'ano': ano.pk, 'mes': '10', 'item': item.pk, 'valor': '500,00'})
    assert_no_validation_errors(resposta)
    return Desembolso.objects.latest('id')


@pytest.fixture
def projeto(client, usuarios, edital):
    """Projeto em edição, com equipe, metas, plano de aplicação e desembolso — pronto para enviar."""
    set_periodo_inscricao(edital)
    _login(client, usuarios.coordenador)
    projeto = _adicionar_projeto(client, edital)
    _adicionar_participante_aluno(client, projeto, Aluno.objects.get(matricula='1'))
    _adicionar_participante_aluno(client, projeto, Aluno.objects.get(matricula='2'), vinculo='Voluntário')
    _adicionar_participante_servidor(client, projeto, usuarios.gerente)
    meta = _adicionar_meta(client, projeto)
    _adicionar_etapa(client, meta)
    item = _adicionar_item_memoria(client, projeto)
    _adicionar_desembolso(client, item)
    return projeto


def _enviar_projeto(client, projeto):
    resposta = client.get(f'/pesquisa/concluir_planejamento/{projeto.pk}/', follow=True)
    assert 'Projeto enviado com sucesso' in resposta.content.decode()
    projeto.refresh_from_db()
    return projeto


@pytest.fixture
def projeto_enviado(client, usuarios, edital, projeto):
    set_periodo_inscricao(edital)
    _login(client, usuarios.coordenador)
    return _enviar_projeto(client, projeto)


def _pre_aprovar(client, usuarios, projeto):
    _login(client, usuarios.pre_avaliador)
    set_periodo_pre_selecao(projeto.edital)
    resposta = client.post(f'/pesquisa/pre_selecionar/{projeto.pk}/', {'obs_reprovacao': 'justificativa da pré-seleção'})
    assert_no_validation_errors(resposta)
    projeto.refresh_from_db()
    return projeto


@pytest.fixture
def projeto_pre_selecionado(client, usuarios, edital, projeto_enviado):
    return _pre_aprovar(client, usuarios, projeto_enviado)


def _avaliar(client, projeto, servidor, pontuacao='8.0'):
    _login(client, servidor)
    indicado = AvaliadorIndicado(projeto=projeto, vinculo=client.user.get_vinculo())
    indicado.save()
    dados = {}
    for criterio in projeto.edital.criterioavaliacao_set.all():
        dados[f'parecer_{criterio.id}'] = 'Favorável'
        dados[criterio.id] = pontuacao
    resposta = client.post(f'/pesquisa/avaliar/{projeto.pk}/', dados)
    assert_no_validation_errors(resposta)


@pytest.fixture
def projeto_aprovado(client, usuarios, projeto_pre_selecionado):
    """Projeto avaliado por dois avaliadores e selecionado (bolsas distribuídas)."""
    projeto = projeto_pre_selecionado
    set_periodo_selecao(projeto.edital)
    _avaliar(client, projeto, usuarios.avaliador)
    _avaliar(client, projeto, usuarios.gerente)
    projeto.refresh_from_db()
    projeto.aprovado_na_distribuicao = True
    projeto.aprovado = True
    projeto.save()
    return projeto
