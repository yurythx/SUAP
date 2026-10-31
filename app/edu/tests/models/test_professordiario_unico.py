"""Um único ``ProfessorDiario`` por (diário, professor) (#17737).

O grafo vem de ``montar_cenario`` (``bulk_create``, sem os efeitos colaterais dos ``save``). Os testes
rodam com ``--no-migrations``: a constraint já está no schema e, para simular o dado legado, o teste da
fusão a remove dentro da própria transação (o DDL do Postgres é transacional e volta no rollback).
"""

from __future__ import annotations

import datetime
import importlib

import pytest
from django.apps import apps
from django.db import IntegrityError, connection, transaction

from edu.models import ProfessorDiario, TipoProfessorDiario
from edu.models.diarios import Aula
from edu.tests.views.test_declaracao_docencia import montar_cenario

pytestmark = pytest.mark.django_db


def _duplicar(pd: ProfessorDiario) -> ProfessorDiario:
    tipo = TipoProfessorDiario.objects.get(descricao='Principal')
    return ProfessorDiario.objects.bulk_create([ProfessorDiario(diario_id=pd.diario_id, professor_id=pd.professor_id, tipo=tipo, percentual_ch=10)])[
        0
    ]


def _aula(titular: ProfessorDiario, *outros: ProfessorDiario) -> Aula:
    aula = Aula.objects.bulk_create([Aula(professor_diario=titular, data=datetime.date(2025, 3, 2), conteudo='Aula', quantidade=2, etapa=1)])[0]
    aula.outros_professor_diario.add(*outros)
    return aula


def test_fusao_mantem_o_maior_pk_e_repassa_aulas_do_vinculo_antigo(sync_permissions) -> None:
    cenario = montar_cenario(n_diarios=1, n_aulas=0, n_extras=0)
    antigo, colega = ProfessorDiario.objects.filter(diario=cenario.diarios[0]).order_by('pk')
    with connection.cursor() as cursor:
        # Dispara as FKs adiadas do cenário: o Postgres não altera tabela com trigger pendente.
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
        cursor.execute('ALTER TABLE edu_professordiario DROP CONSTRAINT edu_professordiario_diario_professor_uniq')
    mantido = _duplicar(antigo)
    do_antigo = _aula(antigo, colega)
    compartilhada_com_os_dois = _aula(colega, antigo, mantido)
    compartilhada_consigo = _aula(mantido, antigo)

    migracao = importlib.import_module('edu.migrations.0328_fundir_professordiario_duplicados')
    migracao.fundir_professordiario_duplicados(apps, None)

    assert mantido.pk > antigo.pk
    assert list(ProfessorDiario.objects.filter(diario=cenario.diarios[0], professor=cenario.professor)) == [mantido]
    do_antigo.refresh_from_db()
    assert do_antigo.professor_diario == mantido
    assert list(do_antigo.outros_professor_diario.all()) == [colega]
    assert list(compartilhada_com_os_dois.outros_professor_diario.all()) == [mantido]
    # O titular não pode constar entre os "outros" da própria aula (AulaForm.clean_outros_professor_diario).
    assert not compartilhada_consigo.outros_professor_diario.exists()
    assert ProfessorDiario.objects.filter(pk=colega.pk).exists()


def test_banco_recusa_segundo_vinculo_do_professor_no_diario(sync_permissions) -> None:
    cenario = montar_cenario(n_diarios=1, n_aulas=0, n_extras=0)
    pd = ProfessorDiario.objects.filter(diario=cenario.diarios[0], professor=cenario.professor).get()

    with pytest.raises(IntegrityError), transaction.atomic():
        _duplicar(pd)
