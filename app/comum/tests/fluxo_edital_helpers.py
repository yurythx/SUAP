"""Helpers compartilhados entre os fluxos de edital de Pesquisa, Extensão e Ensino.

Os três apps (`pesquisa`, `projetos`, `projetos_ensino`) seguem o mesmo pipeline
edital → projeto → enviar → pré-seleção → avaliação → execução → conclusão. As
fixtures de cada conftest tinham seeds financeiros, datas, criação de servidores
auxiliares e login copy-pasted; este módulo concentra essa parte estável.
"""

import datetime

from comum.models import Ano
from comum.types import PessoaFisicaCadastro, ServidorCadastro
from edu.tests.factories import SituacaoMatriculaFactory
from edu.models import Aluno, SituacaoMatricula
from financeiro.models import (
    CategoriaEconomicaDespesa,
    ElementoDespesa,
    GrupoNaturezaDespesa,
    ModalidadeAplicacao,
    NaturezaDespesa,
)
from rh.models import PessoaFisica, Servidor
from rh.tests.factories import CargoEmpregoFactory, JornadaTrabalhoFactory, SituacaoFactory


def hoje(dias=0):
    return datetime.datetime.now() + datetime.timedelta(days=dias)


def str_data(dias=0):
    return hoje(dias).strftime('%d/%m/%Y')


def set_periodo_edital(edital, inscr_ini, inscr_fim, pre, selecao, fim_selecao, divulgacao):
    edital.inicio_inscricoes = hoje(inscr_ini)
    edital.fim_inscricoes = hoje(inscr_fim)
    edital.inicio_pre_selecao = hoje(pre)
    edital.inicio_selecao = hoje(selecao)
    edital.fim_selecao = hoje(fim_selecao)
    edital.divulgacao_selecao = hoje(divulgacao)
    edital.save()


def set_periodo_inscricao(edital):
    set_periodo_edital(edital, 0, 5, 10, 15, 20, 21)


def set_periodo_pre_selecao(edital):
    set_periodo_edital(edital, -10, -5, 0, 15, 20, 21)


def set_periodo_selecao(edital):
    set_periodo_edital(edital, -15, -10, -5, 0, 20, 21)


def set_periodo_execucao(edital):
    set_periodo_edital(edital, -20, -15, -10, -5, -1, 0)


def seed_financeiro_basico():
    """Categorias/grupos/modalidades/naturezas usadas pelos recursos dos editais."""
    categoria = CategoriaEconomicaDespesa.objects.get_or_create(codigo='3', nome='Despesas Correntes')[0]
    grupo = GrupoNaturezaDespesa.objects.get_or_create(codigo='3', nome='Outras Despesas Correntes')[0]
    modalidade = ModalidadeAplicacao.objects.get_or_create(codigo='90', nome='Aplicações Diretas')[0]
    for codigo_elemento, nome_elemento, codigo_natureza in (
        ('30', 'Material de Consumo', '339030'),
        ('18', 'Auxílio Financeiro a Estudantes', '339018'),
        ('20', 'Auxílio Financeiro a Pesquisadores', '339020'),
    ):
        elemento = ElementoDespesa.objects.get_or_create(codigo=codigo_elemento, nome=nome_elemento)[0]
        NaturezaDespesa.objects.get_or_create(
            categoria_economica_despesa=categoria,
            grupo_natureza_despesa=grupo,
            modalidade_aplicacao=modalidade,
            elemento_despesa=elemento,
            codigo=codigo_natureza,
        )


def seed_alunos_basicos():
    """Dois alunos matriculados (matrículas '1' e '2') para participar dos projetos."""
    ano = Ano.objects.get_or_create(ano=str(datetime.datetime.now().year))[0]
    # Pelo ID constante, não pela descrição: `descricao` é UNIQUE, e criar por descrição
    # pega um id automático. Como parte destes seeds roda em fixture de classe que
    # COMMITA, a linha sobrevivia e o `_seed_status_ids` do `light_data` — que insere
    # pelo id constante — batia no UNIQUE depois, noutro módulo.
    situacao = SituacaoMatriculaFactory()
    for matricula, nome, cpf in (
        ('1', 'Carlos Breno Pereira Silva', '359.221.769-00'),
        ('2', 'Jailton Carlos de Paiva', '826.526.814-94'),
    ):
        pessoa = PessoaFisica.objects.get_or_create(nome=nome, defaults={'cpf': cpf})[0]
        pessoa.eh_aluno = True
        pessoa.save()
        Aluno.objects.get_or_create(
            matricula=matricula,
            pessoa_fisica=pessoa,
            ano_letivo=ano,
            periodo_letivo=1,
            situacao=situacao,
            ano_let_prev_conclusao=datetime.datetime.now().year,
        )


def criar_servidor_basico(matricula, nome, cpf, template, *, setor, titulacao=None):
    """Servidor auxiliar com perfis genéricos (cargo, situação e jornada vêm das factories do `rh`).

    O ``setor`` é obrigatório e vem de fora porque os fluxos de edital comparam o campus dos
    atores entre si: quem precisa estar no mesmo campus recebe o mesmo setor. Um
    ``SetorFactory()`` sem superior vira campus próprio, então passar setores diferentes
    muda o que o fluxo exercita.
    """
    pessoa: PessoaFisicaCadastro = {
        'nome_registro': nome,
        'template': template,
        'email': f'{nome.lower().replace(" ", ".")}@mail.gov',
        'cpf': cpf,
    }
    dados: ServidorCadastro = {
        'matricula': matricula,
        'cargo_emprego': CargoEmpregoFactory(),
        'setor': setor,
        'situacao': SituacaoFactory(),
        'jornada_trabalho': JornadaTrabalhoFactory(),
        'ativo': True,
        'pessoa_fisica': pessoa,
    }
    if titulacao:
        dados['titulacao'] = titulacao
    servidor = Servidor.update_or_create(dados)['servidor']
    user = servidor.get_user()
    user.set_password('123')
    user.save()
    return servidor


def login(client, servidor):
    """Login limpo: sai do usuário anterior e entra como `servidor`."""
    client.logout()
    assert client.login(user=servidor.get_user())
