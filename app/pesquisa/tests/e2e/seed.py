"""Replay ORM do substrato que o behave do PESQUISA montava antes de agir.

O behave do PESQUISA (features 001→011, aposentadas) não exercitava tela nos passos iniciais:
**montam o mundo** pelas tabelas de ``Dado os dados básicos para a pesquisa``, ``E os
seguintes usuários`` e ``E os usuários da pesquisa``, e só então a partir daí é que cada
cenário clica. Este módulo transcreve esse monte para ORM, no mesmo espírito de
``edu/tests/e2e/seed.py`` — o behave fica sendo a fonte da verdade do *que* precisa
existir; aqui só se reproduz.

Três diferenças deliberadas em relação ao behave, todas por causa do modelo de execução do
pytest (seção "nada de flush entre testes" da receita):

1. **Idempotência.** Os steps originais usam ``objects.create()`` em ``Titulacao``
   (``given.py:75``) e em ``CurriculoVittaeLattes`` (``given.py:96``): no behave o banco
   nasce limpo a cada run, aqui não — a segunda execução com ``--reuse-db`` estouraria
   duplicidade. Trocar por ``get_or_create`` guardado pela chave natural não muda o que o
   cenário encontra na tela.
2. **Sem ``execute_steps``.** Nenhum destes passos anda com o relógio (só as features, via
   ``Quando a data do sistema for``), então não é preciso o adaptador de ``context`` que o
   ``edu`` — o ``relogio`` do conftest é ``freeze_time`` puro.
3. **O aluno recebe ``is_staff``**, como no antigo step comum ``os seguintes usuários``
   do behave: sem isso o admin de ``/admin/pesquisa/`` nega acesso antes
   de chegar a permissão alguma, e o cenário de frequência da feature 007 — que é do aluno
   — para no login.

Os passos que este módulo substitui, com o endereço no behave:

* ``os dados básicos para a pesquisa`` — o passo ``Dado`` homônimo do behave
* ``os seguintes usuários`` — o step comum do behave; os servidores vêm de factories
  (``servidor_com_login`` de ``djtools/e2e_fixtures.py``, #17486), sobre a árvore de ``arvore()``
* ``os usuários da pesquisa`` — o passo ``Dado`` homônimo do behave
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from django.contrib.auth.models import Group

from djtools.e2e_fixtures import SENHA_E2E

if TYPE_CHECKING:
    from comum.models import PrestadorServico
    from edu.models import Aluno
    from rh.models import Servidor, Setor

# A tabela de ``os seguintes usuários`` da feature 001, linha a linha. ``setor`` é a coluna
# ``Setor`` (a árvore SUAP, ``codigo`` nulo); a coluna ``Lotação`` (SIAPE) não é recriada: as
# telas do módulo caem no setor SUAP quando o servidor não tem lotação.
#
# A tabela original repete CPFs (``232.607.644-37`` em 108004, 108005 e 108012; os três primeiros
# da feature 001 de novo na 012). Desde a Release 2 o CPF é único: a primeira ocorrência mantém o
# CPF da feature e as repetidas ganham o ``cpf_valido(<matrícula>)`` de ``rh/tests/factories.py``.
PAPEIS: dict[str, dict[str, str]] = {
    '108001': {'nome': 'Diretor Pesquisa', 'grupo': 'Diretor de Pesquisa', 'setor': 'CZN', 'cpf': '645.433.195-40'},
    '108002': {'nome': 'Coordenador Pesquisa', 'grupo': 'Coordenador de Pesquisa', 'setor': 'DIAC/CZN', 'cpf': '188.135.291-98'},
    '108003': {'nome': 'Coordenador Projeto', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '921.728.444-03'},
    '108004': {'nome': 'Servidor Projeto', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '232.607.644-37'},
    '108005': {'nome': 'Avaliador1 Pesquisa', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '000.108.005-90'},
    '108006': {'nome': 'Avaliador2 Pesquisa', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '568.288.693-38'},
    '108013': {'nome': 'Coordenador do Laboratório', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '921.728.445-94'},
    '108014': {'nome': 'Membro do Laboratório', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '232.607.645-18'},
    # Fora da feature 001: Coordenador de Pesquisa de OUTRO campus (CEN), papel local que não
    # gerencia a equipe do projeto do CZN (#17555).
    '108090': {'nome': 'Coordenadora Pesquisa Campus Vizinho', 'grupo': 'Coordenador de Pesquisa', 'setor': 'CEN', 'cpf': '108.016.001-97'},
    # A tabela de ``os seguintes usuários`` da feature 012 (EDITORA). São seis papéis porque o
    # fluxo editorial da feature 014 é uma esteira: cada etapa é de um grupo diferente.
    '108007': {'nome': 'Integrante Editora', 'grupo': 'Integrante da Editora', 'setor': 'CZN', 'cpf': '000.108.007-51'},
    '108008': {'nome': 'Conselheiro Editora', 'grupo': 'Conselheiro Editorial', 'setor': 'DIAC/CZN', 'cpf': '000.108.008-32'},
    '108009': {'nome': 'Revisor Editora', 'grupo': 'Revisor de Obra', 'setor': 'DIAC/CZN', 'cpf': '000.108.009-13'},
    '108010': {'nome': 'Diagramador Editora', 'grupo': 'Diagramador de Obra', 'setor': 'DIAC/CZN', 'cpf': '458.658.545-50'},
    '108011': {'nome': 'Bibliotecário Editora', 'grupo': 'Bibliotecário da Pesquisa', 'setor': 'DIAC/CZN', 'cpf': '830.665.156-13'},
    '108012': {'nome': 'Autor Obra', 'grupo': 'Servidor', 'setor': 'DIAC/CZN', 'cpf': '000.108.012-19'},
}

MATRICULA_ALUNO = '20191101011081'
CPF_ALUNO = '359.221.769-00'
NOME_ALUNO = 'Aluno do Projeto'

# O parecerista de obra da feature 014 é um **prestador de serviço**. Era o ``34245605880`` do
# seed global do behave; agora é do módulo, com o mesmo nome (o autocomplete da indicação o
# procura por ele). A matrícula de prestador é o CPF sem pontuação, como no legado.
NOME_PARECERISTA = 'Parecerista Obra'
CPF_PARECERISTA = '108.015.001-33'
MATRICULA_PARECERISTA = CPF_PARECERISTA.replace('.', '').replace('-', '')


# --- servidores e grupos ---------------------------------------------------------------


def arvore() -> Setor:
    """Os campi CZN e CEN (o plano de oferta do edital cobre os dois) e a DIAC/CZN; devolve a DIAC/CZN."""
    from djtools.e2e_fixtures import campus, setor

    campus('CEN')
    return setor('DIAC/CZN', campus('CZN'))


def _setor(sigla: str) -> Setor:
    from djtools.e2e_fixtures import campus

    return arvore() if sigla == 'DIAC/CZN' else campus(sigla)


def criar_servidor(matricula: str) -> Servidor:
    """Cria (ou reencontra) o servidor de ``PAPEIS`` com o grupo da tabela da feature 001 (factories, #17486)."""
    from djtools.e2e_fixtures import servidor_com_login

    dados = PAPEIS[matricula]
    servidor = servidor_com_login(
        matricula,
        _setor(dados['setor']),
        grupos=[dados['grupo']],
        staff=True,
        pessoa_fisica__nome=dados['nome'],
        pessoa_fisica__cpf=dados['cpf'],
        email_pessoal=f'{matricula}_secundario@gmail.com',  # o que `os seguintes usuários` dava a cada ator
    )
    return servidor


def criar_aluno(setor_suap: Setor, matricula: str = MATRICULA_ALUNO, nome: str = NOME_ALUNO, cpf: str = CPF_ALUNO) -> Aluno:
    """O aluno (grupo ``Aluno``) com a diretoria de ``setor_suap``; por padrão, o da tabela (``20191101011081``).

    Replay do ramo ``Aluno`` do antigo step ``os seguintes usuários`` do behave, via
    ``aluno_com_login`` (diretoria + curso técnico próprio do módulo). A doc de usuário reusa com
    o aluno dela.
    """
    from djtools.e2e_fixtures import aluno_com_login

    return aluno_com_login(
        matricula,
        setor_suap,
        nome,
        'TECINFO-PESQUISA-E2E',
        email_pessoal=f'{matricula}_secundario@gmail.com',
        pessoa_fisica__cpf=cpf,
        pessoa_fisica__lattes='http://buscatextual.cnpq.br/buscatextual/visualizacv.do?id=K4758430D7',
    )


def montar_papeis() -> dict[str, Any]:
    """Cria os 8 servidores e o aluno da tabela da feature 001, de uma vez.

    Eager de propósito: o SUAP resolve permissão com cache por processo, então criar o
    vínculo de grupo no meio da sessão faz uma tela que já respondeu 403 continuar 403 para
    sempre. Criando tudo antes da primeira request, não há cache negativo a invalidar.
    """
    papeis = {matricula: criar_servidor(matricula) for matricula in PAPEIS}
    papeis[MATRICULA_ALUNO] = criar_aluno(arvore())
    papeis[MATRICULA_PARECERISTA] = criar_parecerista()
    return papeis


def criar_parecerista() -> PrestadorServico:
    """O prestador de serviço que avalia obra na feature 014, com o grupo ``Parecerista de Obra``.

    Replay do prestador ``34245605880`` do seed global do behave: ocupação vigente numa pessoa
    jurídica, senha e o grupo que ``os dados básicos para a editora`` lhe dava.
    """
    from datetime import date

    from comum.models import Ocupacao, OcupacaoPrestador
    from comum.tests.factories import PrestadorServicoFactory
    from rh.models import PessoaJuridica

    prestador = PrestadorServicoFactory(
        matricula=MATRICULA_PARECERISTA, setor=arvore(), pessoa_fisica__nome=NOME_PARECERISTA, pessoa_fisica__cpf=CPF_PARECERISTA
    )
    empresa = PessoaJuridica.objects.get_or_create(cnpj='45.006.424/0001-00', defaults={'nome': 'Pessoa Jurídica'})[0]
    OcupacaoPrestador.objects.get_or_create(
        prestador=prestador,
        ocupacao=Ocupacao.objects.get_or_create(codigo='', descricao='Teste Ocupação')[0],
        empresa=empresa,
        defaults={'data_inicio': date(2010, 1, 1), 'data_fim': date(2100, 1, 1)},
    )
    usuario = prestador.get_user()
    usuario.set_password(SENHA_E2E)
    usuario.save()
    usuario.groups.add(Group.objects.get(name='Parecerista de Obra'))
    return prestador


# --- cadastros básicos -----------------------------------------------------------------


def dados_basicos() -> None:
    """Replay de ``os dados básicos para a pesquisa`` (``given.py:32``).

    É a carga de tabelas de apoio que o edital toca: área de conhecimento, natureza de
    despesa (o autocomplete "Despesa" da fonte de recursos e da memória de cálculo),
    origem de recurso, titulação (o ``FilteredSelectMultiple`` "Titulações dos Avaliadores")
    e o que o laboratório da feature 015 precisa. Nada aqui é específico de um cenário.
    """
    from django.apps.registry import apps as _apps

    from financeiro.models import CategoriaEconomicaDespesa, ElementoDespesa, GrupoNaturezaDespesa, ModalidadeAplicacao, NaturezaDespesa
    from pesquisa.models import OrigemRecursoEdital
    from rh.models import AreaConhecimento, Titulacao

    # O behave pega `ae.categoriabolsa` por `apps.get_model` (``given.py:13``) em vez de
    # importar direto: o modelo é do app do auxílio emergencial e nenhuma .feature do
    # pesquisa depende dele para existir — daí o mesmo cuidado aqui.
    CategoriaBolsa = _apps.get_model('ae', 'categoriabolsa')

    raiz = AreaConhecimento.objects.get_or_create(codigo='10000003', descricao='CIÊNCIAS EXATAS E DA TERRA')[0]
    AreaConhecimento.objects.get_or_create(codigo='10100008', descricao='MATEMÁTICA', superior=raiz)
    AreaConhecimento.objects.get_or_create(codigo='10100009', descricao='BIOQUÍMICA', superior=raiz)

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
            defaults={'nome': elemento.nome},
        )

    OrigemRecursoEdital.objects.get_or_create(descricao='PROPI')
    if CategoriaBolsa is not None:
        CategoriaBolsa.objects.get_or_create(
            nome='Bolsa de iniciação científica', defaults={'descricao': 'Bolsa de iniciação científica', 'tipo_bolsa': 'iniciação científica'}
        )

    # `create` no behave (`given.py:75`); aqui guardado pelo código, que é a chave natural.
    Titulacao.objects.get_or_create(codigo='26', defaults={'nome': 'Doutorado', 'titulo_masculino': 'Dr.', 'titulo_feminino': 'Dra.'})

    _laboratorio()


def _laboratorio() -> None:
    """O patrimônio que ``os ajustes para o laboratório`` (feature 015) exige.

    Fica junto de ``dados_basicos`` porque o behave o cria no mesmo passo — mover para uma
    fixture própria só faria o replay divergir da feature sem ganho.
    """
    from almoxarifado.models import Entrada, EntradaTipo, MaterialTipo
    from patrimonio.models import CategoriaMaterialPermanente, EntradaPermanente, Inventario, InventarioStatus
    from pesquisa.models import PropriedadeIntelectual
    from rh.models import Setor, UnidadeOrganizacional

    status = InventarioStatus.objects.get_or_create(nome='Status')[0]
    setor = Setor.objects.suap_ativos().get(sigla='CZN')
    uo = UnidadeOrganizacional.objects.suap().get(setor=setor)
    entrada = Entrada.objects.get_or_create(data=datetime.now(), uo=uo, tipo_entrada=EntradaTipo.DOACAO(), tipo_material=MaterialTipo.PERMANENTE())[0]
    categoria = CategoriaMaterialPermanente.objects.get_or_create(codigo='0', nome='nome')[0]
    entrada_permanente = EntradaPermanente.objects.get_or_create(
        entrada=entrada, categoria=categoria, descricao='equipamento do laboratório', qtd=1, valor=Decimal(10)
    )[0]
    Inventario.objects.get_or_create(numero=123455, defaults={'status': status, 'entrada_permanente': entrada_permanente, 'campo_busca': '0'})

    for descricao in ('Patente', 'Software', 'Desenho Industrial'):
        PropriedadeIntelectual.objects.get_or_create(descricao=descricao)


def usuarios_da_pesquisa() -> None:
    """Replay de ``os usuários da pesquisa`` (``given.py:94``).

    Dá aos papéis o que o edital de pesquisa exige deles: grupo de pesquisa e **currículo
    Lattes** para o coordenador (``Edital.pode_submeter_projeto`` recusa quem não tem),
    área de conhecimento e titulação para os avaliadores, e o Lattes do aluno.

    Depende de ``montar_papeis()`` ter rodado: os ``Servidor.objects.get(matricula=...)``
    abaixo, como no behave, pressupõem a tabela de ``os seguintes usuários`` já aplicada.
    """
    from cnpq.models import CurriculoVittaeLattes, DadoComplementar, DadoGeral, GrupoPesquisa
    from comum.models import Ano
    from edu.models import Aluno, SituacaoMatricula
    from rh.models import AreaConhecimento, PessoaFisica, Servidor, Titulacao

    grupo = GrupoPesquisa.objects.get_or_create(codigo='01', descricao='Grupo de Pesquisa', instituicao='IFRN')[0]
    titulacao = Titulacao.objects.filter(codigo='26').first()
    area = AreaConhecimento.objects.filter(codigo='10000003').first()

    for matricula, identificador, cpf in (
        ('108003', '01', '921.728.444-03'),
        ('108004', '02', '232.607.644-37'),
    ):
        servidor = Servidor.objects.get(matricula=matricula)
        if not CurriculoVittaeLattes.objects.filter(numero_identificador=identificador).exists():
            curriculo = CurriculoVittaeLattes.objects.create(sistema_origem_xml='', numero_identificador=identificador)
            curriculo.dado_complementar = DadoComplementar.objects.create()
            curriculo.dado_geral = DadoGeral.objects.create(
                nome_completo=PAPEIS[matricula]['nome'],
                nome_citacao=PAPEIS[matricula]['nome'],
                nacionalidade='Brasileiro',
                cpf=cpf,
                numero_passaporte=cpf,
                pais_nascimento='Brasil',
                uf_nascimento='RN',
                cidade_nascimento='Natal',
                sexo='F',
                permissao_divulgacao='Sim',
                nome_arquivo_foto='path',
                texto_resumo='Texto resumo',
            )
            curriculo.vinculo = servidor.get_vinculo()
            curriculo.save()
            curriculo.grupos_pesquisa.add(grupo)
        if area is not None:
            servidor.areas_de_conhecimento.add(area)

    # Só o coordenador tem currículo; a área é de quem avalia (as duas linhas com o mesmo
    # `areas_de_conhecimento.add` do behave, uma por avaliador).
    for matricula in ('108005', '108006'):
        servidor = Servidor.objects.get(matricula=matricula)
        if area is not None:
            servidor.areas_de_conhecimento.add(area)
        if titulacao is not None:
            servidor.titulacao = titulacao
            servidor.save()

    pessoa = PessoaFisica.objects.get(cpf=CPF_ALUNO)
    pessoa.lattes = 'http://buscatextual.cnpq.br/buscatextual/visualizacv.do?id=K4758430D7'
    pessoa.save()

    ano, _ = Ano.objects.get_or_create(ano=str(datetime.now().year))
    situacao = SituacaoMatricula.objects.get_or_create(descricao='Matriculado', ativo=True)[0]

    aluno = Aluno.objects.get(matricula=MATRICULA_ALUNO)
    aluno.ano_letivo = ano
    aluno.periodo_letivo = 1
    aluno.situacao = situacao
    aluno.ano_let_prev_conclusao = datetime.now().year
    aluno.save()


def ajustes_do_laboratorio() -> None:
    """Replay de ``os ajustes para o laboratório`` (``given.py:191``).

    Existia para zerar a avaliação de conclusão dos projetos entre execuções do behave. Aqui
    é uma linha — mantida como função nomeada porque é o passo que a feature 015 usa.
    """
    from pesquisa.models import RegistroConclusaoProjeto

    RegistroConclusaoProjeto.objects.update(dt_avaliacao=None)


def dados_basicos_editora() -> None:
    """Replay de ``os dados básicos para a editora`` (``given.py:180``).

    As linhas editoriais (o ``FilteredSelectMultiple`` do edital de publicação e a lista
    ``Linha Editorial`` da submissão de obra). O grupo ``Parecerista de Obra`` que o behave dava
    aqui ao prestador do seed global vem em ``criar_parecerista()``. O behave também repete a área
    de conhecimento aqui; isso já foi feito em ``dados_basicos()``, que roda antes.
    """
    from pesquisa.models import LinhaEditorial

    LinhaEditorial.objects.get_or_create(nome='Linha Editorial 01')
    LinhaEditorial.objects.get_or_create(nome='Linha Editorial 02')


def limpar_execucao_anterior() -> None:
    """Apaga a cadeia da execução anterior, para a suíte ser re-executável no mesmo banco.

    A suíte roda com ``--reuse-db`` e não dá flush (é a armadilha 8 da receita), e os títulos
    da feature 001 são fixos — ``'Nome do edital'``, ``'Título do projeto'``. Sem esta limpeza
    a segunda execução encontraria o edital já cadastrado: o changelist do admin teria duas
    linhas com o mesmo título e o ``ícone de exibição`` da linha 1 — o primeiro do DOM —
    passaria a apontar para o edital da run anterior, deixando os testes afirmando sobre um
    objeto que ninguém acabou de criar.

    Apagar o edital basta: projeto, comissão, plano de oferta, fonte de recurso, critério e
    indicação de avaliador todos pendem dele por ``on_delete`` — é a mesma cascata que o
    próprio admin dispara. Num banco recém-criado a função é no-op.
    """
    from pesquisa.models import Edital, EditalSubmissaoObra, RegistroPropriedadeIntelectual

    Edital.objects.filter(titulo=TITULO_EDITAL).delete()
    # O edital de publicação da editora carrega a obra por ``on_delete=CASCADE``
    # (``Obra.edital``), então apagar o edital basta, como na cadeia do PESQUISA.
    EditalSubmissaoObra.objects.filter(titulo=TITULO_EDITAL_EDITORA).delete()
    # `RegistroPropriedadeIntelectual.numero_processo` é **unique**: sem apagar, a segunda
    # execução estoura violação de unicidade no cadastro da feature 016.
    RegistroPropriedadeIntelectual.objects.filter(numero_processo=NUMERO_PROCESSO_PI).delete()


TITULO_EDITAL = 'Nome do edital'
TITULO_EDITAL_EDITORA = 'Edital para publicação'
# Número de processo do registro de PI da feature 016 — único no banco, e é por ele que a
# limpeza da execução anterior o encontra.
NUMERO_PROCESSO_PI = 'BR1020240016033'


def montar() -> None:
    """Substrato completo da cadeia, na ordem em que o behave a montava (a árvore antes: o laboratório a usa)."""
    limpar_execucao_anterior()
    arvore()
    dados_basicos()
    dados_basicos_editora()
    montar_papeis()
    usuarios_da_pesquisa()


__all__ = [
    'CPF_ALUNO',
    'MATRICULA_ALUNO',
    'MATRICULA_PARECERISTA',
    'NOME_ALUNO',
    'NUMERO_PROCESSO_PI',
    'PAPEIS',
    'TITULO_EDITAL',
    'TITULO_EDITAL_EDITORA',
    'ajustes_do_laboratorio',
    'arvore',
    'criar_aluno',
    'criar_parecerista',
    'criar_servidor',
    'dados_basicos',
    'dados_basicos_editora',
    'limpar_execucao_anterior',
    'montar',
    'montar_papeis',
    'usuarios_da_pesquisa',
]
