"""Fluxo: automatização de grupo em setores — a regra que concede grupo sozinha, no login.

``ConfiguracaoAutomatizacaoGrupo`` é a única concessão de permissão do SUAP que ninguém aprova
caso a caso: gravada a regra (setores + cargo), ``HistoricoUsuarioGrupo.atualizar_grupos_usuario``
— que roda no sinal de login (``comum/models.py:1296``) — põe no grupo todo servidor do setor e
**tira** quem deixou de se encaixar. Um assistente de dois passos precede a gravação exatamente
por isso: o segundo passo é a análise de impacto, que diz quem entra e quem sai antes de valer.

A regressão que este arquivo pega é silenciosa e cara: se o passo de confirmação parar de
calcular a análise, ou se o segundo submit gravar sem ela, uma regra errada remove em massa o
acesso de um campus inteiro — e o efeito só aparece quando cada pessoa loga.

Os dois testes rodam sobre um grupo inerte e um setor **sem servidores** (ver
``conftest.GRUPO_AUTOMATIZADO`` e ``SIGLA_SETOR_SEM_SERVIDOR``): a regra gravada é real, mas não
alcança nenhum papel compartilhado da suíte — nem agora, nem no próximo login de quem quer que
seja.
"""

from __future__ import annotations

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_grupos.py`.
AUTOMATIZACAO_LISTAR = '/comum/automatizacao_grupo/{grupo}/'
AUTOMATIZACAO_ADICIONAR = '/comum/automatizacao_grupo/{grupo}/adicionar/'
AUTOMATIZACAO_ALTERAR = '/comum/automatizacao_grupo/{grupo}/alterar/{configuracao}/'

# Setores folha sem servidor nenhum (os `C1`/`C2` que o `e2e_seed` do conftest cria). É o que mantém a regra inócua: a lista de
# elegíveis sai vazia, então nenhum servidor real é arrastado para o grupo no login seguinte.
SETOR_INICIAL = 'C1'
SETOR_ACRESCENTADO = 'C2'


def test_cria_automatizacao_confirmando_o_impacto(logado_comum, grupo_automatizado, servidores_comum):
    """Percorre o assistente inteiro: lista vazia → escolher setor → ver o impacto → confirmar.

    Um teste só para os dois passos porque o segundo não existe sem o primeiro — o formulário é um
    ``FormWizardPlus``, e é o POST do passo 1 que produz a análise exibida no passo 2 (regra 1 da
    receita).

    A asserção do meio é a que importa: a tela tem de **anunciar** que o usuário que hoje está no
    grupo será removido. É esse anúncio que separa "gravei uma regra" de "gravei uma regra sabendo
    o que ela faz", e é ele que some se ``analise_impacto`` quebrar — sem que a gravação falhe.
    """
    from comum.models import ConfiguracaoAutomatizacaoGrupo

    alvo = servidores_comum['alvo_grupo']

    tela = Tela(logado_comum('gestor_grupos')).ir(AUTOMATIZACAO_LISTAR.format(grupo=grupo_automatizado.pk))
    tela.ver_titulo(f'Automatização do grupo {grupo_automatizado} em setores')
    tela.ver_texto('Não existem automatizações do grupo')

    tela.ir(AUTOMATIZACAO_ADICIONAR.format(grupo=grupo_automatizado.pk))
    tela.preencher('Setores', 'autocomplete multiplo', SETOR_INICIAL)
    tela.clicar_botao('Continuar')

    tela.ver_texto('Análise de impacto da nova Automatização')
    tela.ver_texto(str(alvo.get_user()))
    tela.preencher('Confirma operação?', 'checkbox', 'marcar')
    tela.clicar_botao('Finalizar')

    tela.sucesso('Automatização de grupo em setores realizada com sucesso.')
    configuracao = ConfiguracaoAutomatizacaoGrupo.objects.filter(grupo=grupo_automatizado).first()
    assert configuracao, 'a UI disse que automatizou, mas a configuração não persistiu'
    assert configuracao.setores.filter(sigla=SETOR_INICIAL).exists(), 'a configuração gravou sem o setor escolhido'
    tela.ver_texto(SETOR_INICIAL)


def test_altera_automatizacao_existente(logado_comum, automatizacao_existente, grupo_automatizado):
    """A tela de alteração reabre a regra gravada e acrescenta um setor, passando pela confirmação.

    Rota própria (``/alterar/<pk>/``) para a mesma view do cadastro, e é essa dualidade que ela
    verifica: com ``instance``, o assistente ganha o campo ``Ativa``, a análise passa a ser
    ``get_analise_impacto`` (que exclui a própria configuração do cálculo) e a gravação atualiza
    em vez de criar. Trocar um ``if`` ali transforma edição em duplicação, e a duplicata só
    aparece quando o grupo começa a readmitir gente removida.
    """
    tela = Tela(logado_comum('gestor_grupos')).ir(AUTOMATIZACAO_ALTERAR.format(grupo=grupo_automatizado.pk, configuracao=automatizacao_existente.pk))
    tela.ver_titulo(f'Atualizar automatização do grupo {grupo_automatizado} em setores')

    tela.preencher('Setores', 'autocomplete multiplo', SETOR_ACRESCENTADO)
    tela.clicar_botao('Continuar')
    tela.preencher('Confirma operação?', 'checkbox', 'marcar')
    tela.clicar_botao('Finalizar')

    tela.sucesso('Automatização de grupo em setores realizada com sucesso.')
    automatizacao_existente.refresh_from_db()
    assert automatizacao_existente.setores.filter(sigla=SETOR_ACRESCENTADO).exists(), 'a UI disse que atualizou, mas o setor novo não entrou na regra'
    assert automatizacao_existente.atualizado_por, 'a alteração não registrou quem atualizou'
