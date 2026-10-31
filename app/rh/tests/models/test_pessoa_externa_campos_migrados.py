"""PessoaExterna.save() não pode vazar para PessoaFisica os campos que foram para o Vinculo.

`PessoaExterna` mantém colunas próprias (email, foto, raça...) e espelha o `__dict__` em
`PessoaFisica`. Depois de rh/0102 esses campos não existem mais lá — sem o pop, o
`create()`/`update()` estoura. O destino deles agora é o vínculo.
"""

import pytest
from rh.models import PessoaExterna


@pytest.mark.django_db
class TestPessoaExternaCamposMigrados:
    def _nova(self, **kwargs) -> PessoaExterna:
        dados = {'nome': 'Fulano Externo', 'cpf': '732.732.732-08', 'email': 'fulano@externo.com'}
        dados.update(kwargs)
        pessoa_externa = PessoaExterna(**dados)
        pessoa_externa.save()
        return pessoa_externa

    def test_cadastro_nao_estoura_com_campos_migrados(self):
        pessoa_externa = self._nova(email_secundario='outro@externo.com', sistema_origem='TESTE')
        assert pessoa_externa.pessoa_fisica_id is not None

    def test_email_vai_para_o_email_pessoal_do_vinculo(self):
        vinculo = self._nova().get_vinculo()
        assert vinculo.email_pessoal == 'fulano@externo.com'

    def test_email_secundario_tem_precedencia_sobre_o_principal(self):
        vinculo = self._nova(email_secundario='recuperacao@externo.com').get_vinculo()
        assert vinculo.email_pessoal == 'recuperacao@externo.com'

    def test_sistema_origem_espelhado_no_vinculo(self):
        vinculo = self._nova(sistema_origem='SIGAA').get_vinculo()
        assert vinculo.sistema_origem == 'SIGAA'

    def test_edicao_de_pessoa_ja_persistida_nao_estoura(self):
        pessoa_externa = self._nova()
        pessoa_externa.email = 'novo@externo.com'
        pessoa_externa.save()
        assert pessoa_externa.get_vinculo().email_pessoal == 'novo@externo.com'
