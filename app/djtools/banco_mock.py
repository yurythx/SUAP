"""Volume sintético e senhas do banco mockado gerado por ``manage.py gerar_banco_mock``.

Tudo aqui roda num processo filho sob ``suap.settings_test`` apontado para
``test_suap_mock_e2e`` (ver o command). ``exigir_banco_mock`` é a guarda que impede rodar
contra qualquer outro banco.
"""

from __future__ import annotations

import random
import time
from collections.abc import Callable, Iterable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date
from typing import cast

from django.apps import apps
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.management.base import CommandError
from django.db import IntegrityError, connection, models, router, transaction
from django.test import RequestFactory
from model_bakery import baker, generators, random_gen
from pycpfcnpj import gen
from psycopg.errors import UniqueViolation

from djtools.middleware import threadlocals as tl

SUFIXO_BANCO = '_mock_e2e'
SENHA = '123'
TENTATIVAS_UNIQUE = 5  # novos sorteios de uma instância que colidiu em unique antes de desistir do model
TEMPO_MAXIMO_POR_MODELO = 60  # segundos; save() em laço (range(qtd), anos do PDI) travava a run inteira
CONTROLE_DE_TRANSACAO = ('SAVEPOINT', 'RELEASE', 'ROLLBACK')  # SQL que o limite de tempo nunca barra


def fks_obrigatorias(modelo: type[models.Model]) -> list[models.Field]:
    """FK/O2O que precisam de valor no INSERT.

    O ``parent_link`` de herança multi-tabela fica de fora: reusar uma linha-pai existente
    colaria dois filhos no mesmo pai; o bakery cria o pai. ``default=None`` num campo
    ``null=False`` (``AbstractRelacionamento.pessoa_fisica``) não é default: o bakery pula
    o campo e o INSERT sai sem ele.
    """
    return [
        campo
        for campo in modelo._meta.concrete_fields
        if campo.is_relation and not campo.null and (not campo.has_default() or campo.default is None) and not campo.remote_field.parent_link
    ]


def ordenar(grafo: Mapping[str, Iterable[str]]) -> list[str]:
    """Kahn: cada nó depois das suas dependências.

    ``graphlib`` levanta ``CycleError`` em qualquer ciclo; aqui o que fica preso em ciclo
    (e quem depende dele) vai para o fim, em ordem alfabética. Dependência fora do grafo e
    auto-referência são ignoradas.
    """
    pendentes = {no: set(deps) & (grafo.keys() - {no}) for no, deps in grafo.items()}
    ordem: list[str] = []
    while prontos := sorted(no for no, deps in pendentes.items() if not deps):
        ordem.extend(prontos)
        for no in prontos:
            del pendentes[no]
        for deps in pendentes.values():
            deps.difference_update(prontos)
    return ordem + sorted(pendentes)


def ordenar_modelos(modelos: Iterable[type[models.Model]]) -> list[type[models.Model]]:
    """Models em ordem de criação: pai (alvo de FK obrigatória) antes do filho."""
    por_label = {modelo._meta.label: modelo for modelo in modelos}
    grafo = {label: {campo.related_model._meta.label for campo in fks_obrigatorias(modelo)} for label, modelo in por_label.items()}
    return [por_label[label] for label in ordenar(grafo)]


# Labels fora do volume sintético, cada um com o motivo.
EXCLUIDOS = frozenset(
    {
        'comum.Configuracao',  # singleton por (app, chave); os seeds já gravam as chaves necessárias
        'comum.Ano',  # ano sorteado não é ano (Variavel.save() itera entre anos do PDI); o corrente vem de _preparar_substrato
        'rh.Setor',  # a árvore de setores é dos seeds; linhas soltas poluem o substrato
        'rh.UnidadeOrganizacional',  # idem: cada UO é um campus da árvore dos seeds
    }
)


@dataclass
class Resultado:
    """Uma linha do relatório: quantas instâncias do model saíram e o primeiro erro."""

    modelo: str
    criados: int = 0
    erro: str = ''


def _elegivel(modelo: type[models.Model]) -> bool:
    opcoes = modelo._meta
    return (
        opcoes.app_label in settings.APPS_SUAP
        and opcoes.managed
        and not opcoes.proxy
        and not opcoes.swapped
        and opcoes.label not in EXCLUIDOS
        and router.db_for_write(modelo) == 'default'  # tira os models LDAP (ldapdb)
    )


def modelos_do_suap() -> list[type[models.Model]]:
    """Models concretos dos apps SUAP que recebem volume sintético."""
    return [modelo for modelo in apps.get_models() if _elegivel(modelo)]


def _sortear(queryset: models.QuerySet) -> models.Model | None:
    """Linha aleatória reprodutível pela semente do ``random`` (não usa ``ORDER BY random()``)."""
    total = queryset.count()
    return queryset.order_by('pk')[random.randrange(total)] if total else None


def _alvo_existente(campo: models.Field) -> models.Model | None:
    """Linha existente para a FK; O2O só reusa alvo que ainda ninguém referencia."""
    alvos = campo.related_model._base_manager.all()
    if campo.one_to_one:
        alvos = alvos.exclude(pk__in=campo.model._base_manager.values(campo.attname))
    return _sortear(alvos)


def _valores_de_fk(modelo: type[models.Model]) -> dict[str, models.Model]:
    """Uma linha existente para cada FK obrigatória; alvo vazio fica para o bakery criar.

    Reusar linhas existentes é o que impede o volume de fabricar ``Setor`` e
    ``UnidadeOrganizacional`` aleatórios dentro da árvore que os seeds montaram. Cobre as
    FKs com ``default=None``, que o bakery pula (ver ``fks_obrigatorias``).
    """
    valores = {campo.name: _alvo_existente(campo) for campo in fks_obrigatorias(modelo)}
    return {nome: alvo for nome, alvo in valores.items() if alvo is not None}


def _valores_de_criacao(modelo: type[models.Model]) -> dict[str, object]:
    """``_valores_de_fk`` e, na ``PessoaFisica``, um CPF válido (reprodutível pela semente do ``random``).

    O ``save()`` recusa PF nova sem CPF válido (nem passaporte + país): o bakery deixa o CPF vazio ou o enche de letras.
    """
    valores: dict[str, object] = dict(_valores_de_fk(modelo))
    if modelo._meta.label == 'rh.PessoaFisica':
        valores['cpf'] = gen.cpf_with_punctuation()
    return valores


def _reusar_ou_criar(campo: models.Field, _using: str | None, _create_files: bool = False, **attrs: object) -> models.Model:
    """Gerador de FK/O2O do bakery: reusa uma linha existente, como ``_valores_de_fk``.

    Sem ele, o pai que o bakery cria em cascata (alvo vazio no nível de cima) cria os
    próprios pais do zero: ``Setor``, ``UnidadeOrganizacional`` e ``Ano`` aleatórios
    apesar das exclusões. Atributos pedidos para o pai (``fk__campo=...``) forçam criação.
    Model em ``EXCLUIDOS`` nunca é criado: O2O que esgotou os alvos (``pdp_ifrn.PDP.ano``,
    ``portaria.ConfiguracaoSistemaPortaria.campus``) falha e vai para o relatório.
    """
    existente = None if attrs else _alvo_existente(campo)
    if existente is not None:
        return existente
    alvo = cast(type[models.Model], campo.related_model)
    if alvo._meta.label in EXCLUIDOS:
        raise ValueError(f'nenhum {alvo._meta.label} livre para {campo}; o volume não cria {alvo._meta.label}')
    return baker.make(alvo, _using=_using or '', _create_files=_create_files, **{**_valores_de_criacao(alvo), **attrs})


_reusar_ou_criar.required = [lambda campo: ('campo', campo), '_using']  # type: ignore[attr-defined]


def _em_unicidade(campo: models.Field) -> bool:
    """O campo é ``unique`` ou faz parte de um ``unique_together``/``UniqueConstraint`` do model."""
    opcoes = campo.model._meta
    conjuntos = [*opcoes.unique_together, *(restricao.fields for restricao in opcoes.constraints if isinstance(restricao, models.UniqueConstraint))]
    return campo.unique or any(campo.name in conjunto for conjunto in conjuntos)


def _inteiro(unico: bool) -> int:
    """De 1 a 20; se o campo entra em alguma unicidade, até 32767 (cabe em qualquer inteiro) para não colidir.

    O sorteio padrão do bakery vai até 2^31, e ``save()`` que faz ``range(self.qtd)``
    (``CriacaoVagaRemanescente`` e afins) não termina.
    """
    return random_gen.baker_random.randint(1, 32767 if unico else 20)


_inteiro.required = [lambda campo: ('unico', _em_unicidade(campo))]  # type: ignore[attr-defined]


def _texto(max_length: int) -> str:
    """Até 8 letras. O padrão do bakery enche ``max_length`` e ``save()`` que compõe ou copia
    campos estoura a coluna de destino (``Categoria.codigo_completo = f'{sub.codigo}.{codigo}'``,
    ``User.first_name`` a partir de ``PessoaFisica.nome``).
    """
    return random_gen.gen_string(min(max_length, 8))


_texto.required = random_gen.gen_string.required  # type: ignore[attr-defined]

GERADORES = {
    models.CharField: _texto,
    models.TextField: _texto,
    models.ForeignKey: _reusar_ou_criar,
    models.OneToOneField: _reusar_ou_criar,
    **dict.fromkeys(
        (
            models.IntegerField,
            models.BigIntegerField,
            models.SmallIntegerField,
            models.PositiveIntegerField,
            models.PositiveBigIntegerField,
            models.PositiveSmallIntegerField,
        ),
        _inteiro,
    ),
}


def registrar_geradores(modelos: Iterable[type[models.Model]]) -> None:
    """Ensina ao bakery as subclasses de campo do SUAP (``ForeignKeyPlus``, ``CharFieldPlus``…).

    O bakery escolhe o gerador pela classe *exata* do campo e levanta ``TypeError`` para
    subclasses. Aqui cada classe desconhecida herda o gerador do ancestral mais próximo que
    ele conhece. Sem ancestral conhecido, o model falha e vai para o relatório. FKs e
    inteiros usam os ``GERADORES`` daqui, inclusive nas subclasses.
    """
    generators.user_mapping.update(GERADORES)
    mapa = {**generators.get_type_mapping(), **generators.user_mapping}
    for classe in {type(campo) for modelo in modelos for campo in modelo._meta.concrete_fields}:
        if classe in mapa or generators.get(classe):
            continue
        ancestral = next((base for base in classe.__mro__[1:] if base in mapa), None)
        if ancestral is not None:
            generators.user_mapping[classe] = mapa[ancestral]


def _resumir(erro: Exception) -> str:
    primeira_linha = (str(erro).strip().splitlines() or [''])[0]
    return f'{type(erro).__name__}: {primeira_linha}'[:200]


class TempoEsgotado(Exception):
    """O model passou do limite de tempo de ``_gerar_modelo``."""


@contextmanager
def _limite_de_tempo(segundos: float) -> Iterator[None]:
    """``TempoEsgotado`` na primeira consulta do bloco depois de ``segundos``.

    O teste do prazo fica num ``execute_wrapper``, ou seja, a exceção nasce dentro de
    ``cursor.execute``, antes de a consulta ir ao banco: ponto síncrono e bem definido, que o
    ``Atomic`` da instância desfaz como qualquer erro. Não há SIGALRM: exceção assíncrona caía no
    meio do ``Atomic.__exit__``, antes do ``ROLLBACK TO SAVEPOINT``, e vazava a instância.
    Controle de transação (``SAVEPOINT``/``RELEASE``/``ROLLBACK``) passa sempre, senão o próprio
    rollback do savepoint seria barrado. Erro que o ``save()`` embrulhe depois do prazo também
    vira ``TempoEsgotado``.
    """
    # ponytail: só interrompe entre consultas; laço em Python puro sem SQL ou uma consulta única
    # lenta não param. Upgrade: rodar cada model num subprocesso com timeout.
    prazo = time.monotonic() + segundos
    estouro = TempoEsgotado(f'> {segundos:g} s')

    def antes_da_consulta(execute: Callable, sql: str, params: object, many: bool, contexto: dict) -> object:
        if time.monotonic() > prazo and not sql.lstrip().upper().startswith(CONTROLE_DE_TRANSACAO):
            raise estouro
        return execute(sql, params, many, contexto)

    try:
        with connection.execute_wrapper(antes_da_consulta):
            yield
    except Exception as erro:
        if erro is not estouro and time.monotonic() > prazo:
            raise estouro from erro
        raise


def _colisao_de_unique(erro: IntegrityError) -> bool:
    return isinstance(erro.__cause__, UniqueViolation)


def _criar_instancia(modelo: type[models.Model]) -> None:
    """Uma instância no seu savepoint; colisão de unique sorteia de novo até ``TENTATIVAS_UNIQUE`` vezes."""
    for tentativa in range(TENTATIVAS_UNIQUE + 1):
        try:
            with transaction.atomic():
                baker.make(modelo, _fill_optional=False, **_valores_de_criacao(modelo))
            return
        except IntegrityError as erro:
            if tentativa == TENTATIVAS_UNIQUE or not _colisao_de_unique(erro):
                raise


def _gerar_modelo(modelo: type[models.Model], n: int, limite: float = TEMPO_MAXIMO_POR_MODELO) -> Resultado:
    """Até ``n`` instâncias em até ``limite`` segundos; a primeira falha (ou o estouro) encerra o model."""
    resultado = Resultado(modelo._meta.label)
    try:
        with _limite_de_tempo(limite):
            for _ in range(n):
                _criar_instancia(modelo)
                resultado.criados += 1
    except Exception as erro:  # qualquer falha do model vira linha do relatório
        resultado.erro = _resumir(erro)
    return resultado


@contextmanager
def _usuario_corrente() -> Iterator[None]:
    """O primeiro superusuário (ou, sem nenhum, o primeiro usuário) faz as vezes de usuário logado.

    Muitos ``save()`` leem ``tl.get_user()``/``tl.get_request()`` sem guarda (autoria,
    histórico, ``CurrentUserField``) e quebram com ``'NoneType' object has no attribute``.
    O threadlocal anterior é restaurado na saída.
    """
    usuario = get_user_model()._base_manager.order_by('-is_superuser', 'pk').first()
    requisicao = RequestFactory().get('/')
    requisicao.user = usuario  # pyright: ignore[reportAttributeAccessIssue]  # None só em banco sem usuário
    anterior = dict(vars(tl.context))
    tl.context.user, tl.context.request = usuario, requisicao
    try:
        yield
    finally:
        vars(tl.context).clear()
        vars(tl.context).update(anterior)


def _preparar_substrato() -> None:
    """Linhas de que muitos ``save()`` dependem e que os seeds (de datas congeladas) não trazem.

    ``Ano`` corrente: ``Recomendacao.gerar_numeracao`` e outros fazem
    ``Ano.objects.filter(ano=hoje.year)`` e quebram com ``None``.
    """
    apps.get_model('comum', 'Ano')._base_manager.get_or_create(ano=date.today().year)


def gerar_volume(modelos: Iterable[type[models.Model]], n: int, semente: int = 0, limite: float = TEMPO_MAXIMO_POR_MODELO) -> list[Resultado]:
    """``n`` instâncias sintéticas por model, pais antes de filhos.

    A semente vale para o ``random`` (sorteio das FKs) e para o bakery (valores dos campos).
    """
    random.seed(semente)
    baker.seed(semente)
    _preparar_substrato()
    modelos = list(modelos)
    registrar_geradores(modelos)
    with _usuario_corrente():
        return [_gerar_modelo(modelo, n, limite) for modelo in ordenar_modelos(modelos)]


def formatar_relatorio(resultados: list[Resultado], n: int) -> str:
    """Tabela ``model  criados/n  erro``, falhas primeiro, com o placar na última linha."""
    ordenados = sorted(resultados, key=lambda resultado: (not resultado.erro, resultado.modelo))
    linhas = [f'{r.modelo:<60} {r.criados:>4}/{n}  {r.erro}'.rstrip() for r in ordenados]
    falhas = sum(1 for resultado in resultados if resultado.erro)
    linhas.append(f'{len(resultados) - falhas}/{len(resultados)} models sem falha; {falhas} com falha.')
    return '\n'.join(linhas)


def exigir_banco_mock(nome: str) -> None:
    """Recusa gerar volume/senhas fora do banco mockado."""
    if not nome.endswith(SUFIXO_BANCO):
        raise CommandError(f'banco {nome!r} não é o banco mockado (*{SUFIXO_BANCO}); recusando escrever nele.')


def redefinir_senhas(senha: str = SENHA) -> int:
    """Mesma senha para todos os usuários, inclusive os criados pelo bakery.

    Hash PBKDF2 instanciado direto: este processo roda sob ``suap.settings_test``, cujo
    ``PASSWORD_HASHERS`` é só MD5, e um hash MD5 no dump não autentica sob ``suap.settings``.
    """
    hasher = PBKDF2PasswordHasher()
    return get_user_model()._base_manager.update(password=hasher.encode(senha, hasher.salt()))
