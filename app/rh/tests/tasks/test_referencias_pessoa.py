import pytest
from django.db import connection

from rh.deduplicacao.referencias import fks_desconhecidas, referencias, referencias_genericas

pytestmark = pytest.mark.django_db


def _por_coluna() -> dict[tuple[str, str], object]:
    return {(r.tabela, r.coluna): r for r in referencias()}


def test_referencias_incluem_fk_para_pf_e_para_pessoa_sem_parent_link() -> None:
    refs = _por_coluna()

    assert refs[('edu_aluno', 'pessoa_fisica_id')].alvo == 'pessoa_fisica'
    assert refs[('comum_vinculo', 'pessoa_id')].alvo == 'pessoa'
    assert ('pessoa_fisica', 'pessoa_ptr_id') not in refs


def test_banco_criado_dos_models_nao_tem_fk_desconhecida() -> None:
    assert fks_desconhecidas(referencias()) == []


def test_fk_fora_do_orm_e_apontada() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE TABLE tmp_fantasma (id serial PRIMARY KEY, pf integer REFERENCES pessoa_fisica (pessoa_ptr_id))')

    assert fks_desconhecidas(referencias()) == ['tmp_fantasma.pf']


def test_unicidade_vem_do_banco() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_um_contato ON comum_contatoemergencia (pessoa_fisica_id)')
        cursor.execute('CREATE UNIQUE INDEX tmp_par_telefone ON comum_pessoatelefone (pessoa_id, numero)')

    refs = _por_coluna()
    assert refs[('comum_contatoemergencia', 'pessoa_fisica_id')].um_para_um
    assert refs[('comum_pessoatelefone', 'pessoa_id')].compostas == (('pessoa_id', 'numero'),)


def test_historico_do_reversion_fica_fora_das_referencias_genericas() -> None:
    tabelas = {g.tabela for g in referencias_genericas()}

    assert 'reversion_version' not in tabelas
    assert 'comum_vinculo' in tabelas


def test_unicidade_ignora_indice_parcial() -> None:
    with connection.cursor() as cursor:
        cursor.execute("CREATE UNIQUE INDEX tmp_parcial ON comum_pessoatelefone (pessoa_id, numero) WHERE numero <> ''")

    assert _por_coluna()[('comum_pessoatelefone', 'pessoa_id')].unicidades == ()


def test_unicidade_ignora_indice_de_expressao() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_expressao ON comum_pessoatelefone (pessoa_id, lower(numero))')

    assert _por_coluna()[('comum_pessoatelefone', 'pessoa_id')].unicidades == ()


def test_unicidade_ignora_coluna_include() -> None:
    with connection.cursor() as cursor:
        cursor.execute('CREATE UNIQUE INDEX tmp_include ON comum_contatoemergencia (pessoa_fisica_id) INCLUDE (nome_contato)')

    ref = _por_coluna()[('comum_contatoemergencia', 'pessoa_fisica_id')]
    assert ref.unicidades == (('pessoa_fisica_id',),)
    assert ref.um_para_um
