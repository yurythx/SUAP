import pytest
from django.db import connection

from comum.models import Vinculo


@pytest.mark.django_db
def test_busca_do_autocomplete_de_vinculo_usa_indice_trigram() -> None:
    # Tabela quase vazia: o planner prefere seq scan ou um index scan qualquer (o manager padrão junta
    # content_type/user e ordena). Com _base_manager, sem ordenação, e seq/index scan desligados, só sobra
    # bitmap scan, e o único índice que atende o UPPER(search) LIKE do icontains é o trigram.
    with connection.cursor() as cursor:
        cursor.execute('SET LOCAL enable_seqscan = off')
        cursor.execute('SET LOCAL enable_indexscan = off')
    plano = Vinculo._base_manager.filter(search__icontains='abc').order_by().only('pk').explain()
    assert 'comum_vinculo_search_trgm' in plano
