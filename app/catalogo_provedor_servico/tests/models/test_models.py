import pytest
from django.core.exceptions import ValidationError

from catalogo_provedor_servico.models import Servico


class TestServico:
    def test_clean_impede_ativacao_com_id_govbr_zero(self) -> None:
        servico = Servico(id_servico_portal_govbr=0, icone='fa fa-question-circle', titulo='Serviço teste', ativo=True)

        with pytest.raises(ValidationError) as exc_info:
            servico.clean()

        assert exc_info.value.message_dict == {
            'id_servico_portal_govbr': ['Serviços ativos precisam ter o código "Id Gov Br" definido (maior que zero).']
        }

    def test_clean_permite_servico_inativo_com_id_govbr_zero(self) -> None:
        servico = Servico(id_servico_portal_govbr=0, icone='fa fa-question-circle', titulo='Serviço teste', ativo=False)

        servico.clean()

    def test_clean_permite_ativacao_com_id_govbr_maior_que_zero(self) -> None:
        servico = Servico(id_servico_portal_govbr=1, icone='fa fa-question-circle', titulo='Serviço teste', ativo=True)

        servico.clean()
