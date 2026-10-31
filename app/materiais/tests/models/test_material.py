import secrets

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction

from materiais.tests.factories import MaterialFactory

pytestmark = pytest.mark.django_db

# Hex aleatório não comprime: a especificacao passa do limite de 2704 bytes da entrada de btree.
ESPECIFICACAO_LONGA = secrets.token_hex(5000)


def test_material_com_especificacao_longa_grava_e_nao_duplica():
    material = MaterialFactory(especificacao=ESPECIFICACAO_LONGA)

    with pytest.raises(IntegrityError), transaction.atomic():
        MaterialFactory(
            categoria=material.categoria, descricao=material.descricao, especificacao=ESPECIFICACAO_LONGA, unidade_medida=material.unidade_medida
        )
    MaterialFactory(
        categoria=material.categoria, descricao=material.descricao, especificacao=ESPECIFICACAO_LONGA + '.', unidade_medida=material.unidade_medida
    )


def test_validacao_do_material_duplicado_mostra_mensagem_da_unicidade():
    material = MaterialFactory()
    duplicado = MaterialFactory.build(
        categoria=material.categoria, descricao=material.descricao, especificacao=material.especificacao, unidade_medida=material.unidade_medida
    )

    with pytest.raises(ValidationError, match='Já existe material com esta categoria'):
        duplicado.full_clean()
