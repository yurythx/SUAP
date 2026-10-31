"""Fixtures de fluxo dos projetos de Ensino.

Mesmo pipeline dos demais editais (edital -> projeto -> enviar -> pré-seleção
-> avaliação -> execução -> conclusão), conduzido pelos endpoints reais de
`/projetos_ensino/`. As etapas são montadas como fixtures reaproveitando os
payloads já validados do fluxo antigo; os testes verificam a mudança de estado
do projeto, não a antiga matriz de botões.
"""

import datetime
from types import SimpleNamespace

import pytest
from django.contrib.auth.models import Group

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
from financeiro.models import NaturezaDespesa
from projetos_ensino.models import (
    CriterioAvaliacao,
    Edital,
    EditalAnexo,
    EditalAnexoAuxiliar,
    EixoTematico,
    OfertaProjeto,
    OrigemRecursoEdital,
    Recurso,
    TipoBeneficiario,
    TipoVinculo,
)
from rh.models import Setor
from rh.tests.factories import ServidorFactory, SetorFactory

GRUPO_AVALIADOR = 'Avaliador de Projetos de Ensino'
GRUPO_PRE_AVALIADOR = 'Coordenador de Projetos de Ensino'
GRUPO_GERENTE_SISTEMICO = 'Gerente Sistêmico de Projetos de Ensino'
GRUPO_COORDENADOR_PROJETO = 'Professor'


def _carga_inicial():
    seed_financeiro_basico()
    OrigemRecursoEdital.objects.get_or_create(descricao='CAMPUS')
    TipoBeneficiario.objects.get_or_create(descricao='Movimentos Sociais')
    TipoBeneficiario.objects.get_or_create(descricao='Comunidade Escolar')
    EixoTematico.objects.get_or_create(descricao='Eixo Temático 1')
    seed_alunos_basicos()


@pytest.fixture
def usuarios(db, sync_permissions):
    """Atores: coordenador (Professor), gerente, pré-avaliador e avaliador — todos do mesmo campus.

    O campus comum importa: as ofertas do edital são por campus. Como um `SetorFactory()`
    sem superior vira campus próprio, os quatro compartilham o setor do coordenador, e
    `outro_campus` é o segundo campus ofertado.

    Escopo de FUNÇÃO: era class-scoped e commitava via `django_db_blocker.unblock`, então
    os servidores e o seed sobreviviam aos testes seguintes do mesmo worker.
    """
    _carga_inicial()

    coordenador = ServidorFactory()
    coordenador.get_user().groups.add(Group.objects.get(name=GRUPO_COORDENADOR_PROJETO))

    # o gerente é sistêmico e ficava noutro campus no cenário original.
    servidor_gerente = ServidorFactory()
    gerente = servidor_gerente.get_user()
    gerente.groups.add(Group.objects.get(name=GRUPO_GERENTE_SISTEMICO))
    gerente.groups.add(Group.objects.get(name=GRUPO_AVALIADOR))

    pre_avaliador = criar_servidor_basico('12', 'Servidor A2', '449.717.558-88', b'12', setor=coordenador.setor)
    pre_avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_PRE_AVALIADOR))

    avaliador = criar_servidor_basico('13', 'Servidor A3', '313.444.320-18', b'13', setor=coordenador.setor)
    avaliador.get_user().groups.add(Group.objects.get(name=GRUPO_AVALIADOR))

    outro_campus = servidor_gerente.setor.uo

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


# --- Montagem do edital (gerente, via ORM) -----------------------------------


def _salvar(instance):
    """Salva sem force_insert — os save() customizados de projetos_ensino não o aceitam."""
    instance.save()
    return instance


def _criar_edital(gerente):
    edital = Edital(
        titulo='Edital 001 Ensino',
        descricao='Descrição do edital',
        inicio_inscricoes=_hoje(0),
        fim_inscricoes=_hoje(5),
        inicio_pre_selecao=_hoje(10),
        inicio_selecao=_hoje(15),
        fim_selecao=_hoje(20),
        divulgacao_selecao=_hoje(21),
        exige_aluno=True,
        exige_servidor=True,
        tipo_edital=Edital.ENSINO,
        forma_selecao=Edital.CAMPUS,
        qtd_projetos_selecionados=5,
        exige_licoes_aprendidas=False,
        cadastrado_por=gerente.get_user().get_vinculo(),
    )
    return _salvar(edital)


@pytest.fixture
def edital(client, usuarios):
    """Edital de ensino publicado, com anexos, recursos, ofertas e critério."""
    _login(client, usuarios.gerente)
    edital = _criar_edital(usuarios.gerente)
    _salvar(EditalAnexoAuxiliar(edital=edital, nome='Anexo I', descricao='Termo de compromisso', ordem=1))
    _salvar(
        EditalAnexo(
            edital=edital, nome='Anexo I', descricao='Termo de compromisso', tipo_membro=EditalAnexo.ALUNO, vinculo=TipoVinculo.VOLUNTARIO, ordem=1
        )
    )
    origem = OrigemRecursoEdital.objects.get(descricao='CAMPUS').descricao
    for codigo in ('339030', '339018', '339020'):
        natureza = NaturezaDespesa.objects.get(codigo=codigo)
        _salvar(Recurso(edital=edital, origem=origem, valor='1000.00', despesa=natureza))
    _salvar(OfertaProjeto(edital=edital, uo_id=usuarios.coordenador.setor.uo.pk, qtd_aprovados='10', qtd_selecionados='5'))
    _salvar(OfertaProjeto(edital=edital, uo_id=usuarios.outro_campus.pk, qtd_aprovados='2', qtd_selecionados='1'))
    _salvar(CriterioAvaliacao(edital=edital, descricao='Adequação da proposta ao tema', pontuacao_maxima='10.00', ordem_desempate=1))
    return edital


# --- Montagem do projeto (coordenador) ---------------------------------------


def _adicionar_projeto(client, edital):
    from projetos_ensino.models import Projeto

    oferta = edital.ofertaprojeto_set.all()[0]
    eixo = EixoTematico.objects.all()[0]
    setor = Setor.objects.suap_ativos().all()[0]
    resposta = client.post(
        f'/projetos_ensino/adicionar_projeto/{edital.pk}/',
        {
            'edital': edital.pk,
            'uo': oferta.uo.pk,
            'setor': setor.pk,
            'titulo': 'Projeto 001 Ensino',
            'eixo_tematico': eixo.pk,
            'ch_total': 400,
            'justificativa': 'Justificativa do Projeto',
            'resumo': 'Resumo do Projeto',
            'objetivo_geral': 'Objetivo do Projeto',
            'introducao': 'Introdução do Projeto',
            'metodologia': 'Metodologia do Projeto',
            'acompanhamento_e_avaliacao': 'Acompanhamento e Avaliação do Projeto',
            'resultados_esperados': 'Resultados Esperados do Projeto',
            'parceiros_externos': True,
            'quais_parceiros_externos': 'descrição dos parceiros',
            'referencias': 'Referências bibliográficas',
            'inicio_execucao': _str_data(),
            'fim_execucao': _str_data(365),
            'carga_horaria': 4,
        },
    )
    assert_no_validation_errors(resposta)
    return Projeto.objects.get(titulo='Projeto 001 Ensino')


def _adicionar_caracterizacao(client, projeto):
    from projetos_ensino.models import CaracterizacaoBeneficiario

    tipo = TipoBeneficiario.objects.filter(ativo=True).first()
    client.post(f'/projetos_ensino/adicionar_caracterizacao_beneficiario/{projeto.pk}/', {'tipo_beneficiario': tipo.pk, 'quantidade': '10'})
    assert CaracterizacaoBeneficiario.objects.filter(projeto=projeto).exists()


def _adicionar_participante_aluno(client, projeto, aluno):
    client.post(
        f'/projetos_ensino/adicionar_participante_aluno/{projeto.pk}/',
        {'vinculo': 'Bolsista', 'carga_horaria': '10', 'aluno': aluno.pk, 'data': _str_data()},
    )


def _adicionar_participante_servidor(client, projeto, servidor):
    client.post(
        f'/projetos_ensino/adicionar_participante_servidor/{projeto.pk}/',
        {'vinculo': 'Bolsista', 'carga_horaria': '10', 'servidor': servidor.pk, 'data': _str_data()},
    )


def _adicionar_meta(client, projeto):
    from projetos_ensino.models import Meta

    client.post(f'/projetos_ensino/adicionar_meta/{projeto.pk}/', {'ordem': '1', 'descricao': 'Meta 1'})
    return Meta.objects.latest('id')


def _adicionar_etapa(client, meta):
    from projetos_ensino.models import Etapa, Participacao

    participante = Participacao.objects.filter(projeto=meta.projeto)[0]
    client.post(
        f'/projetos_ensino/adicionar_etapa/{meta.pk}/',
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
    from projetos_ensino.models import ItemMemoriaCalculo

    natureza = NaturezaDespesa.objects.get(codigo='339030')
    recurso = Recurso.objects.filter(despesa=natureza, edital=projeto.edital)[0]
    client.post(
        f'/projetos_ensino/memoria_calculo/{projeto.pk}/',
        {'recurso': recurso.pk, 'descricao': 'Descrição da despesa', 'unidade_medida': 'Unid', 'qtd': '10', 'valor_unitario': '50,00'},
    )
    return ItemMemoriaCalculo.objects.latest('id')


def _adicionar_desembolso(client, item):
    from projetos_ensino.models import Desembolso

    ano = Ano.objects.get_or_create(ano=str(datetime.datetime.now().year))[0]
    resposta = client.post(
        f'/projetos_ensino/adicionar_desembolso/{item.projeto.pk}/', {'ano': ano.pk, 'mes': '10', 'item': item.pk, 'valor': '500,00'}
    )
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
    resposta = client.get(f'/projetos_ensino/concluir_planejamento/{projeto.pk}/', follow=True)
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
        f'/projetos_ensino/pre_selecionar/{projeto.pk}/',
        HTTP_REFERER=f'/projetos_ensino/projetos_nao_avaliados/{projeto.edital.id}/',
    )
    assert resposta.status_code == 302
    projeto.refresh_from_db()
    return projeto


def _avaliar(client, projeto, servidor, pontuacao='8.0'):
    _login(client, servidor)
    dados = {'parecer': 'Favorável'}
    for criterio in projeto.edital.criterioavaliacao_set.all():
        dados[criterio.id] = pontuacao
    resposta = client.post(f'/projetos_ensino/avaliar/{projeto.pk}/', dados)
    assert_no_validation_errors(resposta)


@pytest.fixture
def projeto_aprovado(client, usuarios, projeto_pre_selecionado):
    from projetos_ensino.tests.factories import AvaliadorIndicadoFactory

    projeto = projeto_pre_selecionado
    set_periodo_selecao(projeto.edital)
    for servidor in (usuarios.avaliador, usuarios.gerente):
        AvaliadorIndicadoFactory(projeto=projeto, vinculo=servidor.get_vinculo())
        _avaliar(client, projeto, servidor)
    projeto.refresh_from_db()
    projeto.aprovado_na_distribuicao = True
    projeto.aprovado = True
    projeto.save()
    return projeto
