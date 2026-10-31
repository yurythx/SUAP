"""Fluxo: submissão do projeto de extensão (feature 002) — cadastrar, editar, clonar e enviar.

É onde o projeto nasce e deixa de ser rascunho. O cadastro grava, além do projeto, a
participação do coordenador (``adicionar_projeto`` monta a ``Participacao`` responsável à mão);
a edição re-posta o formulário inteiro (``ProjetoExtensaoForm``, com foco tecnológico encadeado ao
campus e tema à área temática); a clonagem copia metas e beneficiários para um edital novo; e o
envio (``concluir_planejamento``) só passa com as pendências resolvidas — é a regra que mais
importa aqui, porque um projeto enviado sai da edição e entra na pré-seleção.
"""

import datetime
from uuid import uuid4

import pytest

from djtools.e2e_ui import Tela
from projetos.tests.e2e.conftest import FOCO_TECNOLOGICO, TEMAS, clicar_em, vinculo

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

EDITAIS_ABERTOS = '/projetos/editais_abertos/'
ADICIONAR_PROJETO = '/projetos/adicionar_projeto/{}/'
PROJETO = '/projetos/projeto/{}/'
EDITAR_PROJETO = '/projetos/editar_projeto/{}/'
CLONAR_PROJETO = '/projetos/clonar_projeto/{}/'
MEUS_PROJETOS = '/projetos/meus_projetos/'
CONCLUIR_PLANEJAMENTO = '/projetos/concluir_planejamento/{}/'

# Os oito campos de texto longo do projeto são TinyMCE ("Texto Rico" na feature 002).
TEXTOS_LONGOS = (
    'Resumo',
    'Justificativa',
    'Fundamentação Teórica',
    'Objetivo Geral',
    'Metodologia da execução do projeto',
    'Acompanhamento e avaliação do projeto durante a execução',
    'Resultados Esperados e Disseminação dos Resultados',
    'Referências Bibliográficas',
)


def _data(dias: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=dias)).strftime('%d/%m/%Y')


def test_cadastro_do_projeto(logado_projetos, edital_novo, foco_tecnologico, catalogo_do_edital):
    """Editais abertos → "Adicionar Projeto" → o projeto nasce em edição, com o coordenador na equipe.

    Datas relativas a hoje (e não as de 2018 da feature): o período de execução não tem regra
    no cadastro, mas as atividades e a troca de coordenador são validadas contra ele.
    """
    from projetos.models import Participacao, Projeto

    edital = edital_novo()
    titulo = f'Projeto E2E {uuid4().hex[:8]}'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(EDITAIS_ABERTOS)
    clicar_em(tela, ADICIONAR_PROJETO.format(edital.pk))

    tela.ver_titulo('Adicionar Projeto').preencher_formulario(
        [
            ('Campus', 'lista', 'CZN'),
            ('Título do projeto', 'texto', titulo),
            ('Carga Horária Semanal', 'texto', '4'),
            ('Início da Execução', 'data', _data(30)),
            ('Término da Execução', 'data', _data(300)),
            ('Foco Tecnológico', 'lista', FOCO_TECNOLOGICO),
            ('O projeto é uma atividade de integração curricular da extensão?', 'lista', 'Não'),
            ('O projeto prevê atividades de internacionalização, inclusive participação em eventos internacionais?', 'lista', 'Sim'),
            ('Área Temática', 'lista', 'Cultura'),
            ('Tema', 'lista', TEMAS[0]),
            *[(campo, 'texto rico', f'Texto de {campo}') for campo in TEXTOS_LONGOS],
        ]
    )
    tela.clicar_botao('Salvar')

    tela.esperar().sucesso('Projeto cadastrado com sucesso.').ver_titulo(f'Projeto de Extensão: {titulo}')
    projeto = Projeto.objects.filter(edital=edital, titulo=titulo).first()
    assert projeto is not None, 'a UI disse que salvou, mas o projeto não persistiu'
    assert 'Texto de Resumo' in projeto.resumo, f'o texto rico não chegou ao campo (resumo={projeto.resumo!r})'
    assert projeto.data_conclusao_planejamento is None, 'o projeto deveria nascer em edição'
    coordenador = Participacao.objects.filter(projeto=projeto, responsavel=True).first()
    assert coordenador is not None, 'o projeto nasceu sem coordenador na equipe'
    assert coordenador.vinculo_pessoa == vinculo('coordenador_projeto'), 'o autor não entrou como coordenador'
    assert coordenador.carga_horaria == 4, f'carga horária do coordenador gravada: {coordenador.carga_horaria}'


def test_edicao_do_projeto(logado_projetos, projeto_novo):
    """ "Editar Projeto" re-posta o formulário inteiro: foco, área, tema e os textos longos têm de voltar válidos."""
    projeto = projeto_novo()
    novo_titulo = f'{projeto.titulo} revisado'
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    tela.clicar_aba('Dados do projeto')
    clicar_em(tela, EDITAR_PROJETO.format(projeto.pk))
    tela.ver_titulo('Editar Projeto').preencher('Título do projeto', 'texto', novo_titulo).clicar_botao('Salvar')

    tela.esperar().sucesso('Projeto editado com sucesso.')
    projeto.refresh_from_db()
    assert projeto.titulo == novo_titulo, 'a UI disse que editou, mas não persistiu'


def test_clonagem_do_projeto(logado_projetos, projeto_novo, edital_novo):
    """Clonar leva metas e beneficiários para OUTRO edital, com o período novo; a origem fica intacta."""
    from projetos.models import Meta, Projeto
    from projetos.tests.factories import CaracterizacaoBeneficiarioFactory, MetaFactory

    origem = projeto_novo()
    MetaFactory(projeto=origem, descricao='Meta a clonar')
    CaracterizacaoBeneficiarioFactory(projeto=origem)
    destino = edital_novo()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(EDITAIS_ABERTOS)
    clicar_em(tela, CLONAR_PROJETO.format(destino.pk))

    tela.ver_titulo('Clonar Projeto no Edital').preencher_formulario(
        [
            ('Projeto', 'lista', origem.titulo),
            ('Data de Início', 'data', _data(40)),
            ('Data de Término', 'data', _data(200)),
        ]
    )
    tela.clicar_botao('Enviar')

    tela.esperar().sucesso('Projeto clonado com sucesso.')
    clone = Projeto.objects.filter(edital=destino, titulo=origem.titulo).first()
    assert clone is not None, 'a UI disse que clonou, mas o projeto não apareceu no edital de destino'
    assert clone.inicio_execucao == datetime.date.today() + datetime.timedelta(days=40), 'o clone não levou o período informado'
    assert Meta.objects.filter(projeto=clone, descricao='Meta a clonar').exists(), 'o clone não levou as metas'
    assert clone.caracterizacaobeneficiario_set.exists(), 'o clone não levou a caracterização dos beneficiários'
    assert Meta.objects.filter(projeto=origem).count() == 1, 'a origem foi alterada pela clonagem'


def _pronto_para_envio(projeto) -> None:
    """Meta com atividade e caracterização: o mínimo que ``projeto_com_pendencias_para_envio`` exige num edital sem recurso."""
    from projetos.models import Participacao
    from projetos.tests.factories import CaracterizacaoBeneficiarioFactory, EtapaFactory, MetaFactory

    responsavel = Participacao.objects.get(projeto=projeto, responsavel=True)
    EtapaFactory(meta=MetaFactory(projeto=projeto), responsavel=responsavel)
    CaracterizacaoBeneficiarioFactory(projeto=projeto)


def test_envio_do_projeto_pelos_meus_projetos(logado_projetos, projeto_novo):
    """Meus Projetos → "Enviar": o projeto completo sai da edição (``data_conclusao_planejamento``) com histórico."""
    from projetos.models import ProjetoHistoricoDeEnvio

    projeto = projeto_novo()
    _pronto_para_envio(projeto)
    tela = Tela(logado_projetos('coordenador_projeto')).ir(MEUS_PROJETOS)

    tela.ver_titulo('Meus Projetos').linha(projeto.titulo)
    clicar_em(tela, CONCLUIR_PLANEJAMENTO.format(projeto.pk))

    tela.sucesso('Projeto enviado com sucesso.')
    projeto.refresh_from_db()
    assert projeto.data_conclusao_planejamento is not None, 'a UI disse que enviou, mas o projeto segue em edição'
    assert ProjetoHistoricoDeEnvio.objects.filter(projeto=projeto, situacao=ProjetoHistoricoDeEnvio.ENVIADO).exists(), (
        'o envio não ficou no histórico'
    )


def test_projeto_com_pendencias_nao_e_enviado(logado_projetos, projeto_novo):
    """Sem metas nem beneficiários, "Enviar Projeto" é recusado e a tela lista as pendências."""
    projeto = projeto_novo()
    tela = Tela(logado_projetos('coordenador_projeto')).ir(PROJETO.format(projeto.pk))

    clicar_em(tela, CONCLUIR_PLANEJAMENTO.format(projeto.pk))  # `.confirm`: o `logado` aceita o diálogo

    tela.erro('O projeto não pode ser enviado. Resolva as pendências descritas abaixo!')
    tela.ver_texto('Cadastre as Metas/Atividades antes de enviar o Projeto.')
    projeto.refresh_from_db()
    assert projeto.data_conclusao_planejamento is None, 'a UI recusou, mas o projeto foi enviado'
