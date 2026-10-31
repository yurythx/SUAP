"""Substrato dos testes do Gerenciador de Projetos.

Do antigo `light_data` estes testes usavam duas coisas: um superusuário
(`self.user_admin`) e um setor sem campus (`self.setor`), sobre o qual cada teste cria a
própria `UnidadeOrganizacional`. É o que esta fixture monta — por teste, com rollback, em
vez do cenário de classe que o `light_data` commitava.
"""

import pytest

from rh.tests.factories import ServidorFactory, SetorFactory

SENHA = '123'


@pytest.fixture(autouse=True)
def substrato_gerenciador(request, db, sync_permissions):
    if request.instance is None:
        return None

    # `campus=False`: os testes criam a UO do setor eles mesmos, com sigla própria.
    setor = SetorFactory(sigla='TEST', nome='Setor Teste', campus=False)
    servidor = ServidorFactory(setor=setor)
    usuario = servidor.get_user()
    usuario.set_password(SENHA)
    usuario.is_superuser = True
    usuario.is_staff = True
    usuario.save()

    # E-mail pessoal: as notificações de tarefa vão para o vínculo, e o `ServidorFactory`
    # não o define — sem ele o `mailoutbox` fica vazio e os testes de notificação não
    # testam nada. O `light_data` preenchia.
    vinculo = servidor.get_vinculo()
    vinculo.email_pessoal = f'{servidor.matricula}@mail.gov'
    vinculo.save(update_fields=['email_pessoal'])

    request.instance.setor = setor
    request.instance.admin = servidor
    request.instance.user_admin = usuario
    return servidor
