import datetime

import pytest

from dados_abertos.enums import Situacao_GrupoTrabalho
from dados_abertos.models import GrupoTrabalho, PlanoDadosAbertos, ResponsavelGrupoTrabalho
from rh.tests.factories import ServidorFactory

SENHA = '123'


def logar(client, servidor) -> None:
    """Autentica o servidor no cliente.

    O ``ServidorFactory`` já nasce com setor e campus: sem campus, o ``UsuarioSemSetorMiddleware``
    desloga o servidor. O login salva o usuário, e é esse ``save`` que recalcula os grupos
    automáticos (``comum.models.user_post_save``).
    """
    usuario = servidor.get_user()
    usuario.set_password(SENHA)
    usuario.save()
    assert client.login(username=usuario.username, password=SENHA)


@pytest.fixture
def cliente_membro_gt(client, db, sync_permissions):
    """Cliente de um responsável ativo no grupo de trabalho de um PDA vigente.

    O grupo de permissão *Membros do Grupo de Trabalho* é automático: sem esse cadastro, o
    ``save`` do usuário tira-o do grupo. A vigência começa no passado distante para o PDA nunca
    ser o "mais recente" dos testes que comparam PDAs.
    """
    servidor = ServidorFactory()
    pda = PlanoDadosAbertos.objects.create(
        titulo='PDA do grupo de trabalho',
        vigencia_inicio=datetime.date(2000, 1, 1),
        vigencia_fim=datetime.date.today() + datetime.timedelta(days=365),
    )
    grupo = GrupoTrabalho.objects.create(pda=pda, descricao='GT do PDA', situacao=Situacao_GrupoTrabalho.ATIVO)
    ResponsavelGrupoTrabalho.objects.create(grupo_trabalho=grupo, responsavel=servidor.get_vinculo(), ativo=True)
    logar(client, servidor)
    return client
