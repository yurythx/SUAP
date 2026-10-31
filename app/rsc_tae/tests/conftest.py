"""Substrato dos testes do RSC-TAE.

Os testes usavam `aplicar_suap_data(self, suap_data)`, que copia TODAS as chaves do
fixture para a instância. Deste módulo só seis eram de fato usadas: os quatro servidores,
o superusuário e o client. É o que esta fixture monta, com as factories do `rh`.

A topologia é a mesma do fixture antigo — `servidor_a` e o admin no campus A,
`servidor_b` no campus B, `servidor_c` e `servidor_d` em segundos setores de cada um.
O RSC-TAE decide acesso por campus em várias telas, então juntar todos num campus só
apagaria o que elas testam.

Cada arquivo declara seu elenco em `ATORES`; sem isso, os cinco são construídos, e só os
setores dos atores pedidos são criados. Não é otimização prematura: construir sempre os
cinco custava 5 min só de fixture nesta suíte (de 6 min totais) e declarar o elenco levou
isso a 3 min — a maioria dos arquivos usa um ou dois atores. O elenco é declarado por
ARQUIVO, não por classe: helpers de módulo recebem a instância
(`def _processo(caso): caso.servidor_a`), então varrer só o corpo da classe subdeclarava
o elenco e os testes quebravam com `AttributeError`.
"""

from types import SimpleNamespace

import pytest

from rh.tests.factories import ServidorFactory, SetorFactory

SENHA = '123'


def _ator(servidor):
    """Define a senha, que o `ServidorFactory` não define.

    Quase todos os testes autenticam por `client.login(user=...)` (force_login), mas
    `test_finalizar_avaliacao` loga o `servidor_b` por usuário/senha.
    """
    user = servidor.get_user()
    user.set_password(SENHA)
    user.save()
    return servidor


@pytest.fixture
def atores(request, suap_client, db, sync_permissions):
    """Servidores e admin do substrato, injetados na instância de teste.

    Expõe tudo como atributo (`self.servidor_a`, `self.client`...), que é como o
    `aplicar_suap_data` entregava — assim a troca nos testes é só trocar a chamada pelo
    nome da fixture no `_setup`.
    """
    setores: dict[str, object] = {}

    def setor(sigla, campus):
        """Setor sob um campus, criado sob demanda e reaproveitado.

        Só os setores dos atores pedidos são construídos: `SetorFactory` de campus salva
        uma `UnidadeOrganizacional`, cujo `save` regrava a árvore inteira.
        """
        if sigla not in setores:
            if campus not in setores:
                setores[campus] = SetorFactory(sigla=campus)
            setores[sigla] = SetorFactory(sigla=sigla, superior=setores[campus])
        return setores[sigla]

    def novo_admin():
        servidor = _ator(ServidorFactory(setor=setor('A1', 'A0')))
        user = servidor.get_user()
        user.is_superuser = True
        user.is_staff = True
        user.save(update_fields=['is_superuser', 'is_staff'])
        return servidor

    construtores = {
        'admin': novo_admin,
        'servidor_a': lambda: _ator(ServidorFactory(setor=setor('A1', 'A0'))),
        'servidor_b': lambda: _ator(ServidorFactory(setor=setor('B1', 'B0'))),
        'servidor_c': lambda: _ator(ServidorFactory(setor=setor('A2', 'A0'))),
        'servidor_d': lambda: _ator(ServidorFactory(setor=setor('B2', 'B0'))),
    }
    elenco = getattr(request.cls, 'ATORES', None) or tuple(construtores)

    dados = SimpleNamespace(
        **{nome: construtores[nome]() for nome in elenco},
        client=suap_client,
    )

    if request.instance is not None:
        for nome, valor in vars(dados).items():
            setattr(request.instance, nome, valor)
    return dados
