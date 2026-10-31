"""Layouts do extrator SIAPE e as precedências entre eles.

Fonte única da ordem de importação: o motor paralelo e a tela de detalhe derivam daqui.
"""

from __future__ import annotations

from collections.abc import Collection
from dataclasses import dataclass, replace

GRUPO_TABELAS = 'Tabelas'
GRUPO_NUCLEO = 'Núcleo do servidor'
GRUPO_HISTORICOS = 'Históricos'


# Para que serve: lotes paralelos do mesmo layout não podem gravar o mesmo registro ao mesmo tempo
# (duplicata ou um sobrescrevendo o outro). Declarar aqui, por layout, qual campo agrupa as linhas
# que tocam o mesmo registro é o que torna seguro dividir o arquivo.
@dataclass(frozen=True)
class Particao:
    """Como extrair a chave de partição de um registro SIAPE para dividir um layout em lotes.

    Uma chave de partição nunca fica dividida entre dois lotes (ver `lotes.dividir_em_lotes`):
    todas as linhas com a mesma chave (mesmo servidor, matrícula, cargo, rubrica, PCA...) caem no
    mesmo lote.

    Attributes:
        tipo: Como a chave é obtida a partir de `campo`: `'campo'` (valor bruto do campo),
            `'matricula'` (matrícula extraída do campo) ou `'cpf_da_matricula'` (CPF do servidor
            dono da matrícula extraída do campo).
        campo: Nome do campo do registro SIAPE que carrega o valor de origem da chave.
    """

    tipo: str  # 'campo' | 'matricula' | 'cpf_da_matricula'
    campo: str  # nome do campo do registro SIAPE que carrega a chave


# Para que serve: construtores curtos para a tabela `_PARTICOES`, que fica legível como uma lista de
# "layout -> por qual campo agrupar" (vale também para `por_matricula`/`por_cpf_da_matricula`).
def por_campo(campo: str) -> Particao:
    """Partição pelo valor bruto (sem transformação) de `campo`."""
    return Particao('campo', campo)


# Para que serve: nos históricos a matrícula vem embutida num campo maior (ex.: matrícula +
# ano/mês); agrupar pelo campo bruto separaria em lotes diferentes linhas do mesmo servidor.
def por_matricula(campo: str) -> Particao:
    """Partição pela matrícula extraída de `campo` (ver `rh.utils.extrai_matricula`)."""
    return Particao('matricula', campo)


# Para que serve: servidor2..4 atualizam também a pessoa física, que é a mesma para matrículas
# diferentes do mesmo CPF. Agrupar pela matrícula deixaria dois lotes gravando a mesma pessoa
# física em paralelo.
def por_cpf_da_matricula(campo: str) -> Particao:
    """Partição pelo CPF do servidor dono da matrícula extraída de `campo`.

    Usada nos layouts do núcleo em que a mesma pessoa pode aparecer com matrículas diferentes no
    mesmo arquivo, para que todas as linhas dela caiam no mesmo lote independentemente da
    matrícula.
    """
    return Particao('cpf_da_matricula', campo)


# Para que serve: reúne num lugar só tudo o que a tela, o importador e o motor paralelo precisam
# saber de um layout (grupo, precedência, se importa, como dividir), para que incluir ou mudar um
# layout seja uma alteração neste módulo, e não em vários lugares que podem divergir.
@dataclass(frozen=True)
class Layout:
    """Um layout do extrator SIAPE: seu grupo de exibição, dependências e chave de partição.

    Attributes:
        nome: Nome do layout, como identificado a partir do `.REF` (ver `identificacao`).
        grupo: Grupo de exibição na tela (`GRUPO_TABELAS`, `GRUPO_NUCLEO` ou `GRUPO_HISTORICOS`).
        dependencias: Nomes dos layouts que precisam terminar antes deste começar (quando
            selecionados na mesma importação; ver `dependencias_efetivas`).
        ativo: Se `False`, o layout é reconhecido mas não tem (ou não usa mais) rotina de
            importação — os arquivos desse layout são marcados como `ignorado`.
        motivo_inativo: Texto exibido ao usuário explicando por que o layout está inativo.
        particao: Como dividir este layout em lotes paralelos, ou `None` se ele não é dividido
            (roda sempre num único lote).
    """

    nome: str
    grupo: str
    dependencias: tuple[str, ...] = ()
    ativo: bool = True
    motivo_inativo: str = ''
    particao: Particao | None = None


_TABELAS = (
    'atividades',
    'afastamentos',
    'bancos',
    'grupo_cargo_emprego',
    'cargo_classe',
    'diploma_legal',
    'funcoes',
    'jornada_trabalho',
    'nivel_escolaridade',
    'pais',
    'regime_juridico',
    'rubrica',
    'estado_civil',
    'grupo_ocorrencia',
    'situacao_servidor',
    'uo',
    'titulacoes',
)
_TABELAS_DEPENDENTES = {'cargo_emprego': ('grupo_cargo_emprego',), 'ocorrencia': ('grupo_ocorrencia',)}
# servidor2..4 gravam pelo save() da linha inteira do servidor: rodam encadeados
_NUCLEO = (
    ('servidor1', (*_TABELAS, *_TABELAS_DEPENDENTES)),
    ('servidor2', ('servidor1',)),
    ('servidor3', ('servidor2',)),
    ('servidor4', ('servidor3',)),
    ('servidor5', ('servidor4',)),
    ('email_telefone_servidor', ('servidor4',)),
)
_FIM_DO_NUCLEO = ('servidor5', 'email_telefone_servidor')
_HISTORICOS = ('servidorafastamentos', 'historico_funcao', 'historico_setor_siape', 'servidor_matriculas', 'historico_ferias', 'pca')

_PARTICOES = {
    'cargo_emprego': por_campo('GR-IDEN-CARGO-EMPREGO'),
    'rubrica': por_campo('IT-CO-RUBRICA'),
    'servidor1': por_campo('IT-NU-CPF'),
    # servidor2 NÃO tem partição (fica de fora deste dicionário; `_montar` cai no `None` padrão) e
    # roda sempre num único lote: ele grava `ServidorFuncaoHistorico` (via `update_or_create`), cujo
    # post_save (`processo_eletronico.atualizar_compartilhamento_poder_chefe`) apaga e recria os
    # `CompartilhamentoProcessoEletronicoPoderDeChefe` de TODO o setor da função, travando o vínculo
    # de cada chefe do setor. Foi assim que dois LOTES do próprio servidor2 (quando ainda tinha
    # partição por CPF/matrícula, e setores diferentes rodavam em paralelo) travaram um no outro —
    # deadlock do Postgres, visto nas importações #4 e #14. A partição protege o registro do
    # servidor, não o efeito colateral por setor; sem ela, servidor2 nunca mais tem dois lotes SEUS
    # disputando essa trava ao mesmo tempo (um único lote por arquivo, e as etapas de um mesmo
    # layout — um arquivo por vez — rodam em sequência, nunca em paralelo). Não reative a partição
    # aqui sem resolver esse efeito colateral. A retentativa que sobra
    # (`execucao_lotes.TENTATIVAS_POR_DEADLOCK`) é a rede de segurança para um deadlock vindo de
    # FORA desta importação (a tela do setor, o cron de outro módulo, qualquer código que grave o
    # mesmo `ServidorFuncaoHistorico`/vínculo do chefe ao mesmo tempo) ou de um layout futuro que
    # precise continuar particionado apesar de cair no mesmo efeito colateral por setor.
    # servidor3 só atualiza a linha do servidor e a pessoa física dele (sem get_or_create): não
    # grava `ServidorFuncaoHistorico`, então mantém a partição por CPF da matrícula.
    'servidor3': por_cpf_da_matricula('GR-MATRICULA'),
    'servidor4': por_cpf_da_matricula('GR-MATRICULA-SERV-DISPONIVEL'),
    'email_telefone_servidor': por_cpf_da_matricula('GR-MATRICULA-SERV-DISPONIVEL'),
    'servidorafastamentos': por_matricula('GR-MATRICULA'),
    # historico_funcao também grava ServidorFuncaoHistorico (mesmo update_or_create de servidor2):
    # mesmo risco de deadlock por setor descrito acima do servidor2, mesma decisão de não dividir.
    'historico_setor_siape': por_matricula('GR-MATRICULA-ANO-MES'),
    'servidor_matriculas': por_matricula('GR-MATRICULA-SIAPE-RH'),
    # linhas do mesmo PCA no mesmo lote (regimes/jornadas são apagados e recriados por PCA);
    # FormaProvimentoVacancia.codigo é único, e o get_or_create do Django reconsulta na colisão
    'pca': por_campo('CH-PCA'),
    'posicionamento_pca': por_campo('CH-PCA-POSICIONAMENTO'),
}


def _montar() -> dict[str, Layout]:
    """Monta o dicionário `LAYOUTS` a partir das listas/tuplas declaradas acima do módulo,
    aplicando a cada layout a partição correspondente em `_PARTICOES` (quando houver).
    """
    layouts = [Layout(nome, GRUPO_TABELAS) for nome in _TABELAS]
    layouts += [Layout(nome, GRUPO_TABELAS, deps) for nome, deps in _TABELAS_DEPENDENTES.items()]
    layouts += [Layout(nome, GRUPO_NUCLEO, deps) for nome, deps in _NUCLEO]
    layouts += [Layout(nome, GRUPO_HISTORICOS, _FIM_DO_NUCLEO) for nome in _HISTORICOS]
    layouts += [
        Layout('ferias', GRUPO_HISTORICOS, ('historico_ferias',)),
        Layout('posicionamento_pca', GRUPO_HISTORICOS, ('pca',)),
        Layout(
            'historico_afastamento',
            GRUPO_HISTORICOS,
            _FIM_DO_NUCLEO,
            ativo=False,
            motivo_inativo='Substituído pela importação de servidorafastamentos.',
        ),
    ]
    return {layout.nome: replace(layout, particao=_PARTICOES.get(layout.nome)) for layout in layouts}


LAYOUTS = _montar()


# Para que serve: a ordenação da tela de detalhe precisa
# de uma sequência linear que respeite as precedências; derivá-la do grafo evita manter uma lista
# de ordem à parte que poderia divergir dele.
def ordem_topologica(apenas_ativos: bool = True) -> list[str]:
    """Ordem serial válida (Kahn, estável pela ordem de `LAYOUTS`) para rodar todos os layouts.

    Args:
        apenas_ativos: Se `True` (padrão), considera só os layouts ativos e as dependências entre
            eles (uma dependência inativa é desconsiderada); se `False`, inclui também os inativos.

    Returns:
        Os nomes dos layouts numa ordem em que cada um vem depois de todas as suas dependências.

    Raises:
        ValueError: se houver ciclo nas dependências (não deveria acontecer com os layouts atuais).
    """
    nomes = [nome for nome, layout in LAYOUTS.items() if layout.ativo or not apenas_ativos]
    pendentes = {nome: {d for d in LAYOUTS[nome].dependencias if d in nomes} for nome in nomes}
    ordem: list[str] = []
    while pendentes:
        prontos = [nome for nome, deps in pendentes.items() if not deps]
        if not prontos:
            raise ValueError('Ciclo nas dependências dos layouts: ' + ', '.join(sorted(pendentes)))
        for nome in prontos:
            del pendentes[nome]
            ordem.append(nome)
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return ordem


# Para que serve: o operador pode importar só parte dos layouts. Sem isto, um layout cuja
# dependência direta não foi selecionada apontaria para um nó fora do grafo (o agendador acusa
# "dependência inexistente"), ou perderia a ordem em relação a uma indireta que foi selecionada.
def dependencias_efetivas(nome: str, selecionados: Collection[str]) -> set[str]:
    """Dependências de `nome` entre os selecionados, atravessando as não selecionadas.

    Usado por `execucao.executar_importacao` para montar o grafo apenas com os layouts que têm
    arquivo selecionado: se uma dependência direta não foi selecionada, busca a dependência dela,
    e assim por diante, até achar uma que esteja entre `selecionados` (ou esgotar o grafo).

    Args:
        nome: Nome do layout cujas dependências efetivas se quer.
        selecionados: Nomes dos layouts que de fato vão rodar nesta importação.

    Returns:
        O subconjunto de `selecionados` do qual `nome` depende, direta ou indiretamente.
    """
    efetivas: set[str] = set()
    visitar = list(LAYOUTS[nome].dependencias)
    vistos: set[str] = set()
    while visitar:
        dependencia = visitar.pop()
        if dependencia in vistos:
            continue
        vistos.add(dependencia)
        if dependencia in selecionados:
            efetivas.add(dependencia)
        else:
            visitar.extend(LAYOUTS[dependencia].dependencias)
    return efetivas


# Para que serve: na tela de detalhe, ao marcar um layout, as dependências dele (inclusive
# indiretas) são marcadas junto; evita que o operador importe o servidor sem as tabelas de apoio.
def dependencias_transitivas(nome: str) -> set[str]:
    """Todas as dependências diretas e indiretas de `nome` (usado pela tela para marcar junto).

    Args:
        nome: Nome do layout cujas dependências se quer.

    Returns:
        Os nomes de todos os layouts dos quais `nome` depende, direta ou indiretamente.
    """
    todas: set[str] = set()
    visitar = list(LAYOUTS[nome].dependencias)
    while visitar:
        dependencia = visitar.pop()
        if dependencia not in todas:
            todas.add(dependencia)
            visitar.extend(LAYOUTS[dependencia].dependencias)
    return todas
