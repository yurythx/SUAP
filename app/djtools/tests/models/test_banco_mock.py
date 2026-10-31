"""Testes do volume sintético e das senhas do banco mockado (``djtools/banco_mock.py``)."""

from __future__ import annotations

import random
import time
from collections.abc import Iterator
from datetime import date

import pytest
from django.contrib.auth.hashers import PBKDF2PasswordHasher
from django.core.management.base import CommandError
from django.db import connection
from django.db import models as django_models
from model_bakery import baker, generators, random_gen

from auditoria.models import Acao, TipoServico
from auditoria.tests.factories import TipoServicoFactory
from calculos_pagamentos.models import ConfigPagamento
from comum.models import Ano, User
from comum.tests.factories import UserFactory
from dados_abertos.models import VersaoPDA
from demandas.models import HistoricoSituacaoSugestaoMelhoria, SugestaoMelhoria
from djtools import banco_mock
from djtools.banco_mock import (
    Resultado,
    _em_unicidade,
    _gerar_modelo,
    exigir_banco_mock,
    fks_obrigatorias,
    formatar_relatorio,
    gerar_volume,
    modelos_do_suap,
    ordenar,
    ordenar_modelos,
    redefinir_senhas,
    registrar_geradores,
)
from djtools.db.models.fields.string import CharFieldPlus
from djtools.middleware import threadlocals as tl
from materiais.models import Categoria
from pgd2.models import SetorHabilitacao
from processo_seletivo.models import CriacaoVagaRemanescente
from rh.models import PessoaFisica, Servidor, Setor


@pytest.fixture(autouse=True)
def _isolar_geradores(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """``registrar_geradores`` muda o mapa global do bakery; ``gerar_volume`` semeia ``random`` e o
    random do bakery. Tudo global, e outros testes (boletim_servico e os que vêm depois deste
    módulo) também usam bakery — sem restaurar, a ordem dos testes passaria a importar.
    """
    monkeypatch.setattr(generators, 'user_mapping', dict(generators.user_mapping))
    estado_random = random.getstate()
    estado_bakery = random_gen.baker_random.getstate()
    yield
    random.setstate(estado_random)
    random_gen.baker_random.setstate(estado_bakery)


def test_ordenar_pai_antes_do_filho_e_ciclo_no_fim():
    grafo = {
        'filho': {'pai'},
        'pai': set(),
        'a': {'b'},
        'b': {'a'},
        'orfao': {'fora_do_grafo'},
        'eu': {'eu'},
    }
    assert ordenar(grafo) == ['eu', 'orfao', 'pai', 'filho', 'a', 'b']


def test_fks_obrigatorias_de_acao():
    assert [campo.name for campo in fks_obrigatorias(Acao)] == ['tipo_servico']


def test_fks_obrigatorias_ignora_parent_link():
    assert PessoaFisica._meta.parents  # herança multi-tabela (pessoa_ptr)
    assert not any(campo.remote_field.parent_link for campo in fks_obrigatorias(PessoaFisica))


def test_fks_obrigatorias_inclui_fk_com_default_none():
    # AbstractRelacionamento.pessoa_fisica: null=False, default=None. O bakery pula campo com
    # default, então sem isto o INSERT de Servidor sai sem pessoa_fisica.
    assert 'pessoa_fisica' in [campo.name for campo in fks_obrigatorias(Servidor)]


def test_ordenar_modelos_pai_primeiro():
    assert ordenar_modelos([Acao, TipoServico]) == [TipoServico, Acao]


def test_modelos_do_suap_filtra_excluidos_proxy_e_nao_gerenciados():
    modelos = modelos_do_suap()
    labels = {modelo._meta.label for modelo in modelos}
    assert 'auditoria.Acao' in labels
    assert 'comum.Configuracao' not in labels
    assert not any(modelo._meta.proxy or not modelo._meta.managed for modelo in modelos)


def test_registrar_geradores_herda_do_ancestral():
    registrar_geradores(modelos_do_suap())
    assert generators.get(CharFieldPlus) is generators.get(django_models.CharField)


@pytest.mark.django_db
def test_fk_obrigatoria_reusa_linha_existente():
    tipos = TipoServicoFactory.create_batch(3)
    assert gerar_volume([Acao], n=5) == [Resultado('auditoria.Acao', criados=5)]
    assert TipoServico.objects.count() == 3
    assert set(Acao.objects.values_list('tipo_servico', flat=True)) <= {tipo.pk for tipo in tipos}


@pytest.mark.django_db
def test_alvo_vazio_bakery_cria_o_pai():
    assert gerar_volume([Acao], n=1) == [Resultado('auditoria.Acao', criados=1)]
    assert TipoServico.objects.count() == 1


@pytest.mark.django_db
def test_falha_de_um_model_vai_para_o_relatorio_e_os_demais_seguem(monkeypatch):
    TipoServicoFactory()

    def explodir(self, *args, **kwargs):
        raise ValueError('boom')

    monkeypatch.setattr(TipoServico, 'save', explodir)
    assert gerar_volume([Acao, TipoServico], n=2) == [
        Resultado('auditoria.TipoServico', criados=0, erro='ValueError: boom'),
        Resultado('auditoria.Acao', criados=2),
    ]


def test_formatar_relatorio_falhas_primeiro():
    texto = formatar_relatorio([Resultado('a.Ok', 2), Resultado('b.Falha', 0, 'ValueError: x')], n=2)
    linhas = texto.splitlines()
    assert linhas[0].startswith('b.Falha')
    assert linhas[0].endswith('ValueError: x')
    assert linhas[1].startswith('a.Ok')
    assert linhas[-1] == '1/2 models sem falha; 1 com falha.'


def test_exigir_banco_mock_recusa_outro_banco():
    exigir_banco_mock('test_suap_mock_e2e')
    with pytest.raises(CommandError, match='não é o banco mockado'):
        exigir_banco_mock('suap')


@pytest.mark.django_db
def test_redefinir_senhas_grava_pbkdf2_de_123():
    UserFactory.create_batch(2)
    assert redefinir_senhas() == User.objects.count()
    # check_password não serve: o settings de teste só conhece MD5. O dump é lido sob
    # suap.settings, cujo hasher padrão é PBKDF2.
    hasher = PBKDF2PasswordHasher()
    for senha in User.objects.values_list('password', flat=True):
        assert senha.startswith('pbkdf2_sha256$')
        assert hasher.verify('123', senha)


@pytest.mark.django_db
def test_volume_roda_com_superusuario_no_threadlocal():
    # SugestaoMelhoria.save() grava o histórico com tl.get_user(); sem usuário, usuario_id nulo.
    registrar_geradores(modelos_do_suap())  # o pai criado em cascata (AreaAtuacaoDemanda) usa OneToOneFieldPlus
    # `gerar_volume` escolhe `order_by('-is_superuser', 'pk').first()`, e o `suap_data` commita um
    # superusuário `admin` de pk baixo: se um teste dele rodou antes neste worker, era ele que
    # seria escolhido, não o criado aqui. O rebaixamento fica na transação revertida deste teste.
    User._base_manager.filter(is_superuser=True).update(is_superuser=False)
    UserFactory()
    admin = UserFactory(is_superuser=True)
    assert gerar_volume([SugestaoMelhoria], n=1) == [Resultado('demandas.SugestaoMelhoria', criados=1)]
    assert HistoricoSituacaoSugestaoMelhoria.objects.get().usuario == admin
    assert tl.get_user() is None


def test_inteiros_pequenos_e_faixa_larga_em_unicidade():
    # CriacaoVagaRemanescente.save() cria range(qtd) Vagas: com o sorteio padrão (até 2^31) não termina.
    registrar_geradores([CriacaoVagaRemanescente, Ano])
    baker.seed(0)
    assert {baker.prepare(CriacaoVagaRemanescente, oferta_vaga=None).qtd for _ in range(50)} <= set(range(1, 21))
    assert max(baker.prepare(Ano).ano for _ in range(50)) > 20  # Ano.ano é unique: faixa larga


def test_em_unicidade_inclui_unique_together():
    assert _em_unicidade(Ano._meta.get_field('ano'))  # unique=True
    assert _em_unicidade(VersaoPDA._meta.get_field('major'))  # unique_together (pda, major, minor, patch)
    assert not _em_unicidade(VersaoPDA._meta.get_field('tipo'))


@pytest.mark.django_db
def test_textos_curtos_cabem_em_campo_composto():
    # Categoria.codigo_completo (max 20) = f'{sub_elemento_nd.codigo}.{codigo}', cada um com max 20.
    assert gerar_volume([Categoria], n=2) == [Resultado('materiais.Categoria', criados=2)]


@pytest.mark.django_db
def test_pai_criado_em_cascata_reusa_linha_existente():
    tipos = TipoServicoFactory.create_batch(2)
    registrar_geradores([Acao])
    baker.make(Acao)  # sem _valores_de_fk: quem escolhe o tipo_servico é o gerador de FK do bakery
    assert TipoServico.objects.count() == 2
    assert Acao.objects.get().tipo_servico in tipos


@pytest.mark.django_db
def test_excluido_nunca_e_criado_em_cascata():
    # A precondição é `rh.Setor` vazia — é ela que faz o O2O ficar sem candidato. Um teste de
    # `suap_data` rodando antes neste worker commita setores e o volume passaria a criar 1.
    Setor._base_manager.all().delete()
    [resultado] = gerar_volume([SetorHabilitacao], n=1)  # O2O para rh.Setor, tabela vazia
    assert resultado.criados == 0
    assert 'o volume não cria rh.Setor' in resultado.erro


@pytest.mark.django_db
def test_volume_garante_o_ano_corrente():
    gerar_volume([], n=1)
    assert Ano.objects.filter(ano=date.today().year).exists()


@pytest.mark.django_db
@pytest.mark.parametrize(('tentativas', 'completa'), [(0, False), (banco_mock.TENTATIVAS_UNIQUE, True)])
def test_colisao_de_unique_sorteia_de_novo(monkeypatch, tentativas, completa):
    # ConfigPagamento.tipo_calculo é unique com 17 choices: 8 sorteios colidem com a semente 0.
    monkeypatch.setattr(banco_mock, 'TENTATIVAS_UNIQUE', tentativas)
    [resultado] = gerar_volume([ConfigPagamento], n=8)
    assert (resultado.criados == 8) is completa
    assert completa or 'duplicate key' in resultado.erro


@pytest.mark.django_db
def test_model_lento_vira_linha_do_relatorio(monkeypatch):
    # Laço de consultas lentas (cada uma 50 ms): para na primeira consulta depois do prazo.
    def consultas_lentas(self, *args, **kwargs):
        with connection.cursor() as cursor:
            for _ in range(100):
                cursor.execute('select pg_sleep(0.05)')

    monkeypatch.setattr(TipoServico, 'save', consultas_lentas)
    inicio = time.monotonic()
    assert _gerar_modelo(TipoServico, n=3, limite=0.2) == Resultado('auditoria.TipoServico', erro='TempoEsgotado: > 0.2 s')
    assert time.monotonic() - inicio < 2


@pytest.mark.django_db
@pytest.mark.parametrize('consulta', ['select count(*) from auditoria_tiposervico', 'select pg_sleep(0.1)'])
def test_estouro_no_meio_de_queries_nao_quebra_a_conexao(monkeypatch, consulta):
    # O caso real: save() que grava e entra em laço de consultas (range(qtd) de INSERTs). Levantar
    # com a consulta no ar, ou barrar o ROLLBACK TO SAVEPOINT depois do prazo, deixaria o INSERT
    # de antes do prazo vivo e a transação de fora envenenada.
    def laco(self, *args, **kwargs):
        Ano._base_manager.create(ano=1999)
        with connection.cursor() as cursor:
            while True:
                cursor.execute(consulta)

    monkeypatch.setattr(Acao, 'save', laco)
    tipos, acoes = gerar_volume([TipoServico, Acao], n=2, limite=0.3)
    assert tipos == Resultado('auditoria.TipoServico', criados=2)
    assert acoes.erro.startswith('TempoEsgotado')
    assert not Ano.objects.filter(ano=1999).exists()  # o savepoint da instância foi desfeito
    assert TipoServico.objects.count() == 2


@pytest.mark.django_db
def test_mesma_semente_mesmos_valores():
    def primeiro_nome(semente: int) -> str:
        gerar_volume([Acao], n=1, semente=semente)
        nome = Acao.objects.get().nome
        Acao.objects.all().delete()
        TipoServico.objects.all().delete()
        return nome

    assert primeiro_nome(7) == primeiro_nome(7)
    assert primeiro_nome(7) != primeiro_nome(8)


@pytest.mark.django_db
def test_pessoa_fisica_ganha_cpf_valido(sync_permissions: None) -> None:  # o save() do Servidor busca os grupos pelo nome
    # PessoaFisica nova sem CPF válido (nem passaporte + país) é recusada no save(); o bakery deixa o CPF vazio (campo opcional).
    registrar_geradores(modelos_do_suap())
    assert gerar_volume([PessoaFisica, Servidor], n=2) == [Resultado('rh.PessoaFisica', criados=2), Resultado('rh.Servidor', criados=2)]
