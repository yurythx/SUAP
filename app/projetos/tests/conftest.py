"""Fixtures de fluxo dos projetos de Extensão.

Mesmo pipeline dos demais editais (edital -> projeto -> enviar -> pré-seleção
-> avaliação -> execução -> conclusão), conduzido pelos endpoints reais de
`/projetos/`. As etapas são montadas como fixtures reaproveitando os payloads
já validados do fluxo antigo; os testes verificam a mudança de estado do
projeto, não a antiga matriz de botões.
"""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group, Permission

from comum.models import Ano
from comum.pytest_fixtures import assert_no_validation_errors
from comum.tests.fluxo_edital_helpers import (
    criar_servidor_basico,
    hoje as _hoje,
    login as _login,
    seed_alunos_basicos,
    seed_financeiro_basico,
    set_periodo_execucao,
    set_periodo_inscricao,
    set_periodo_pre_selecao,
    set_periodo_selecao,
    str_data as _str_data,
)
from edu.models import Aluno
from rh.tests.factories import ServidorFactory, SetorFactory
from financeiro.models import NaturezaDespesa
from projetos.models import (
    AreaConhecimento,
    AreaTematica,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    FocoTecnologico,
    OfertaProjeto,
    OrigemRecursoEdital,
    Recurso,
    Tema,
    TipoBeneficiario,
    TipoVinculo,
)

GRUPO_AVALIADOR = 'Avaliador de Projetos de Extensão'
GRUPO_PRE_AVALIADOR = 'Coordenador de Extensão'
GRUPO_GERENTE_SISTEMICO = 'Gerente Sistêmico de Extensão'
GRUPO_COORDENADOR_PROJETO = 'Servidor'


def _carga_inicial():
    seed_financeiro_basico()
    OrigemRecursoEdital.objects.get_or_create(descricao='PROEX')
    TipoBeneficiario.objects.get_or_create(descricao='Movimentos Sociais')
    TipoBeneficiario.objects.get_or_create(descricao='Comunidade Escolar')
    area_superior = AreaConhecimento.objects.get_or_create(codigo='10000003', defaults={'descricao': 'CIÊNCIAS EXATAS E DA TERRA'})[0]
    AreaConhecimento.objects.get_or_create(codigo='10100008', defaults={'descricao': 'MATEMÁTICA', 'superior': area_superior})
    area_tematica = AreaTematica.objects.get_or_create(descricao='Multidisciplinar')[0]
    Tema.objects.get_or_create(descricao='Tecnologia da Informação  e Comunicação', defaults={'areatematica': area_tematica})
    seed_alunos_basicos()


@pytest.fixture
def usuarios(db, sync_permissions):
    """Atores do fluxo: coordenador, gerente, pré-avaliador e avaliador — todos do mesmo campus.

    O campus comum importa: as ofertas do edital são por campus e o fluxo compara o do
    ator com o da oferta. Como um `SetorFactory()` sem superior vira campus próprio, os
    quatro compartilham o setor do coordenador.

    NÃO class-scoped: o gerente recebe `is_superuser=True`, e commitar isso fora
    do savepoint vazaria para outros módulos (testes de `comum` enxergariam o
    gerente como superusuário e veriam perfis indevidos).
    """
    _carga_inicial()

    coordenador = ServidorFactory()
    servidor_gerente = ServidorFactory(setor=coordenador.setor)

    gerente = servidor_gerente.get_user()
    gerente.groups.add(Group.objects.get(name=GRUPO_GERENTE_SISTEMICO))
    gerente.user_permissions.add(*Permission.objects.filter(content_type__app_label='projetos'))
    gerente.is_staff = True
    gerente.is_superuser = True
    gerente.save()

    pre_avaliador = criar_servidor_basico('12', 'Servidor A2', '449.717.558-88', b'12', setor=coordenador.setor)
    pre_avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

    avaliador = criar_servidor_basico('13', 'Servidor A3', '313.444.320-18', b'13', setor=coordenador.setor)
    avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_AVALIADOR))

    return SimpleNamespace(coordenador=coordenador, gerente=servidor_gerente, pre_avaliador=pre_avaliador, avaliador=avaliador)


@pytest.fixture
def outro_campus(db):
    """Segundo campus do edital, distinto do dos atores."""
    return SetorFactory().uo


@pytest.fixture
def client(suap_client):
    return suap_client


def _login_gerente(client, gerente):
    client.logout()
    assert client.login(user=gerente.get_user())
    user = client.user
    for attr in ('_group_perm_cache', '_user_perm_cache', '_perm_cache'):
        if hasattr(user, attr):
            delattr(user, attr)


# --- Montagem do edital (gerente) --------------------------------------------


def _criar_focos_tecnologicos(*campi):
    foco = FocoTecnologico.objects.get_or_create(descricao='Multidisciplinar', defaults={'ativo': True})[0]
    foco.campi.add(*campi)
    return foco


def _criar_edital(client, gerente):
    return Edital.objects.create(
        titulo='Edital 001 Extensão',
        descricao='Descrição do edital',
        inicio_inscricoes=_hoje(0),
        fim_inscricoes=_hoje(5),
        inicio_pre_selecao=_hoje(10),
        inicio_selecao=_hoje(15),
        fim_selecao=_hoje(20),
        divulgacao_selecao=_hoje(21),
        participa_aluno=True,
        participa_servidor=True,
        tipo_edital=Edital.EXTENSAO,
        forma_selecao=Edital.CAMPUS,
        qtd_projetos_selecionados=1,
        valor_financiado_por_projeto=0.00,
        tipo_fomento=Edital.FOMENTO_INTERNO,
        exige_anuencia=Edital.SEM_ANUENCIA,
        exige_licoes_aprendidas=False,
        cadastrado_por=gerente.get_user().get_vinculo(),
    )


def _adicionar_recurso(edital, codigo_despesa):
    natureza = NaturezaDespesa.objects.get(codigo=codigo_despesa)
    origem = OrigemRecursoEdital.objects.get(descricao='PROEX')
    return Recurso.objects.create(edital=edital, origem=origem.descricao, valor='1000.00', despesa=natureza)


def _adicionar_oferta(edital, uo):
    return OfertaProjeto.objects.create(edital=edital, uo_id=uo.pk, qtd_aprovados='10', qtd_selecionados='5')


def _adicionar_criterio_avaliacao(client, edital):
    from projetos.models import CriterioAvaliacao

    resposta = client.post(
        f'/projetos/adicionar_criterio_avaliacao/{edital.pk}/',
        {'edital': edital.pk, 'descricao': 'Adequação da proposta ao tema', 'pontuacao_maxima': '10,00', 'ordem_desempate': 1},
    )
    assert_no_validation_errors(resposta)
    assert CriterioAvaliacao.objects.filter(edital=edital).exists()


@pytest.fixture
def edital(client, usuarios, outro_campus):
    """Edital de extensão publicado, com anexos, recursos, ofertas, focos e critério.

    Duas ofertas: o campus dos atores e um segundo campus, como no cenário original.
    """
    campus_dos_atores = usuarios.coordenador.setor.uo
    _criar_focos_tecnologicos(campus_dos_atores, outro_campus)
    _login_gerente(client, usuarios.gerente)
    edital = _criar_edital(client, usuarios.gerente)
    EditalAnexoAuxiliar.objects.create(edital=edital, nome='Anexo I', descricao='Termo de compromisso', ordem=1)
    EditalAnexo.objects.create(
        edital=edital, nome='Anexo I', descricao='Termo de compromisso', tipo_membro=EditalAnexo.ALUNO, vinculo=TipoVinculo.VOLUNTARIO, ordem=1
    )
    for codigo in ('339030', '339018', '339020'):
        _adicionar_recurso(edital, codigo)
    _adicionar_oferta(edital, campus_dos_atores)
    _adicionar_oferta(edital, outro_campus)
    _adicionar_criterio_avaliacao(client, edital)
    return edital


# --- Montagem do projeto (coordenador) ---------------------------------------


def _adicionar_projeto(client, edital):
    from projetos.models import Projeto

    oferta = edital.ofertaprojeto_set.all()[0]
    area = AreaConhecimento.objects.filter(superior__isnull=False)[0]
    area_tematica = AreaTematica.objects.get(descricao='Multidisciplinar')
    tema = Tema.objects.filter(descricao__contains='Tecnologia')[0]
    foco = oferta.focos_tecnologicos.all()[0]
    resposta = client.post(
        f'/projetos/adicionar_projeto/{edital.pk}/',
        {
            'edital': edital.pk,
            'uo': oferta.uo.pk,
            'titulo': 'Projeto 001 Extensão',
            'area_conhecimento': area.pk,
            'area_tematica': area_tematica.pk,
            'tema': tema.pk,
            'focotecnologico': foco.pk,
            'justificativa': 'Justificativa do Projeto',
            'resumo': 'Resumo do Projeto',
            'objetivo_geral': 'Objetivo do Projeto',
            'metodologia': 'Metodologia do Projeto',
            'acompanhamento_e_avaliacao': 'Acompanhamento e Avaliação do Projeto',
            'resultados_esperados': 'Resultados Esperados do Projeto',
            'referenciasbibliograficas': 'Referências bibliográficas',
            'fundamentacaoteorica': 'Fundamentação teórica',
            'inicio_execucao': _str_data(),
            'fim_execucao': _str_data(365),
            'publico_alvo': 'Ambos',
            'carga_horaria': 4,
            'executado_com_parceria': 'False',
            'atividade_integracao_curricular': 'False',
            'preve_atividades_internacionalizacao': 'False',
            'tem_ods': False,
        },
    )
    assert_no_validation_errors(resposta)
    return Projeto.objects.get(titulo='Projeto 001 Extensão')


def _adicionar_caracterizacao(client, projeto):
    from projetos.models import CaracterizacaoBeneficiario

    tipo = TipoBeneficiario.objects.filter(ativo=True).first()
    client.post(f'/projetos/adicionar_caracterizacao_beneficiario/{projeto.pk}/', {'tipo_beneficiario': tipo.pk, 'quantidade': '10'})
    assert CaracterizacaoBeneficiario.objects.filter(projeto=projeto).exists()


def _adicionar_participante_aluno(client, projeto, aluno):
    client.post(
        f'/projetos/adicionar_participante_aluno/{projeto.pk}/',
        {'vinculo': 'Bolsista', 'carga_horaria': '10', 'aluno': aluno.pk, 'data': _str_data()},
    )


def _adicionar_participante_servidor(client, projeto, servidor):
    client.post(
        f'/projetos/adicionar_participante_servidor/{projeto.pk}/',
        {'vinculo': 'Bolsista', 'carga_horaria': '10', 'servidor': servidor.pk, 'data': _str_data()},
    )


def _adicionar_meta(client, projeto):
    from projetos.models import Meta

    client.post(f'/projetos/adicionar_meta/{projeto.pk}/', {'ordem': '1', 'descricao': 'Meta 1'})
    return Meta.objects.latest('id')


def _adicionar_etapa(client, meta):
    from projetos.models import Etapa, Participacao

    participante = Participacao.objects.filter(projeto=meta.projeto)[0]
    client.post(
        f'/projetos/adicionar_etapa/{meta.pk}/',
        {
            'ordem': '1',
            'descricao': 'Atividade 1',
            'unidade_medida': 'Aluno',
            'qtd': '50',
            'indicadores_qualitativos': 'Nota das avaliações',
            'responsavel': participante.pk,
            'inicio_execucao': _str_data(),
            'fim_execucao': _str_data(10),
            'forma_comprovacao': 'Relatório',
        },
    )
    return Etapa.objects.latest('id')


def _adicionar_item_memoria(client, projeto):
    from projetos.models import ItemMemoriaCalculo

    natureza = NaturezaDespesa.objects.get(codigo='339030')
    recurso = Recurso.objects.filter(despesa=natureza, edital=projeto.edital)[0]
    client.post(
        f'/projetos/memoria_calculo/{projeto.pk}/',
        {'recurso': recurso.pk, 'descricao': 'Descrição da despesa', 'unidade_medida': 'Unid', 'qtd': '10', 'valor_unitario': '50,00'},
    )
    return ItemMemoriaCalculo.objects.latest('id')


def _adicionar_desembolso(client, item):
    from projetos.models import Desembolso

    ano = Ano.objects.get_or_create(ano=str(datetime.datetime.now().year))[0]
    resposta = client.post(f'/projetos/adicionar_desembolso/{item.projeto.pk}/', {'ano': ano.pk, 'mes': '10', 'item': item.pk, 'valor': '500,00'})
    assert_no_validation_errors(resposta)
    return Desembolso.objects.latest('id')


@pytest.fixture
def projeto(client, usuarios, edital):
    """Projeto em edição, completo (equipe, beneficiários, metas, plano e desembolso) — pronto para enviar."""
    set_periodo_inscricao(edital)
    _login(client, usuarios.coordenador)
    projeto = _adicionar_projeto(client, edital)
    _adicionar_caracterizacao(client, projeto)
    _adicionar_participante_aluno(client, projeto, Aluno.objects.get(matricula='1'))
    _adicionar_participante_aluno(client, projeto, Aluno.objects.get(matricula='2'))
    _adicionar_participante_servidor(client, projeto, usuarios.gerente)
    meta = _adicionar_meta(client, projeto)
    _adicionar_etapa(client, meta)
    item = _adicionar_item_memoria(client, projeto)
    _adicionar_desembolso(client, item)
    return projeto


def _enviar_projeto(client, projeto):
    resposta = client.get(f'/projetos/concluir_planejamento/{projeto.pk}/', follow=True)
    assert 'Projeto enviado com sucesso' in resposta.content.decode()
    projeto.refresh_from_db()
    return projeto


@pytest.fixture
def projeto_enviado(client, usuarios, edital, projeto):
    set_periodo_inscricao(edital)
    _login(client, usuarios.coordenador)
    return _enviar_projeto(client, projeto)


@pytest.fixture
def projeto_pre_selecionado(client, usuarios, projeto_enviado):
    projeto = projeto_enviado
    _login(client, usuarios.pre_avaliador)
    set_periodo_pre_selecao(projeto.edital)
    resposta = client.get(
        f'/projetos/pre_selecionar/{projeto.pk}/',
        HTTP_REFERER=f'/projetos/projetos_nao_avaliados/{projeto.edital.id}/',
    )
    assert resposta.status_code == 302
    projeto.refresh_from_db()
    return projeto


def _avaliar(client, projeto, servidor, pontuacao='8.0'):
    _login(client, servidor)
    dados = {'parecer': 'Favorável'}
    for criterio in projeto.edital.criterioavaliacao_set.all():
        dados[criterio.id] = pontuacao
    resposta = client.post(f'/projetos/avaliar/{projeto.pk}/', dados)
    assert_no_validation_errors(resposta)


@pytest.fixture
def projeto_aprovado(client, usuarios, projeto_pre_selecionado):
    projeto = projeto_pre_selecionado
    set_periodo_selecao(projeto.edital)
    _avaliar(client, projeto, usuarios.avaliador)
    _avaliar(client, projeto, usuarios.gerente)
    projeto.refresh_from_db()
    projeto.aprovado_na_distribuicao = True
    projeto.aprovado = True
    projeto.save()
    return projeto
