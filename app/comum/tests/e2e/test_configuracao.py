"""Fluxo: as telas de administração do SUAP — painel, parâmetros do sistema e exclusão genérica.

São as três telas transversais que só o administrador vê: o painel que reúne os acessos de
manutenção (``/comum/admin/``), o formulário que grava os parâmetros de **todas** as aplicações
numa tabela só (``Configuracao``) e a confirmação de exclusão que qualquer módulo do SUAP
reaproveita para apagar registro (``/comum/excluir/<app>/<model>/<pks>/``).

A regressão que este arquivo pega vem em dois tamanhos. O pequeno: a tela de configuração monta
o formulário importando ``<app>.forms.ConfiguracaoForm`` de cada aplicação instalada — um erro de
import em qualquer módulo derruba a configuração de todos. O grande: a exclusão genérica é a
única porta de apagamento de dezenas de telas e exige a senha do usuário logado; se essa
verificação afrouxar, um GET passa a apagar registro.
"""

from __future__ import annotations

import pytest

from djtools.e2e_fixtures import SENHA_E2E
from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Rotas como constantes de módulo — ver a nota da armadilha 17 em `test_grupos.py`.
ADMIN = '/comum/admin/'
CONFIGURACAO = '/comum/configuracao/'
CONFIGURACAO_DO_APP = '/comum/configuracao/{app}/'
EXCLUIR = '/comum/excluir/{app}/{model}/{pks}/'

# A aplicação cuja configuração o teste GRAVA. Escolhida por medição, não por acaso: é a única
# com um único campo, e o valor gravado é o próprio default documentado — então a gravação é
# semanticamente um no-op para o resto da suíte, que compartilha o banco de e2e. O `comum` tem 42
# campos, quase todos obrigatórios, e o `frota` (que também tem um só) tem suíte e2e própria.
APP_CONFIGURAVEL = 'licenca_capacitacao'
CAMPO_CONFIGURAVEL = 'Quando permitir análise de solicitações de alteração'
VALOR_CONFIGURAVEL = 'Somente após o término das inscrições (padrão)'


def test_painel_de_administracao(logado_comum):
    """O painel do administrador abre e oferece as portas de manutenção do sistema.

    A contagem de superusuários e o resumo de temas são agregações sobre ``User`` e
    ``Preferencia`` calculadas na própria view: é o tipo de tela que ninguém abre no dia a dia e
    que quebra calada quando um desses models muda.
    """
    tela = Tela(logado_comum('admin')).ir(ADMIN)

    tela.ver_titulo('Administração do SUAP')
    tela.ver_texto('Usuários e grupos')
    tela.ver_texto('superusers')


def test_configuracao_do_sistema_salva_por_aplicacao(logado_comum):
    """Abre a configuração de todas as aplicações e grava a de uma delas pela aba do módulo.

    As duas rotas num teste só porque a segunda é a primeira filtrada — a lista de abas que a
    tela mostra É a lista de aplicações que declaram ``ConfiguracaoForm``, e é ela que prova que
    a fábrica varreu os ``INSTALLED_APPS`` sem estourar em nenhum import.

    O valor gravado é o default documentado da aplicação escolhida: o banco de e2e é
    compartilhado entre os módulos da rodada, e configuração é global por definição.
    """
    from comum.models import Configuracao

    tela = Tela(logado_comum('admin')).ir(CONFIGURACAO)
    tela.ver_titulo('Configuração do Sistema')
    tela.ver_texto(APP_CONFIGURAVEL)

    tela.ir(CONFIGURACAO_DO_APP.format(app=APP_CONFIGURAVEL))
    tela.preencher(CAMPO_CONFIGURAVEL, 'lista', VALOR_CONFIGURAVEL)
    tela.clicar_botao('Enviar')

    tela.sucesso('Configuração salva com sucesso.')
    assert Configuracao.objects.filter(app=APP_CONFIGURAVEL, chave='analise_permitida_desde', valor='fim_submissao').exists(), (
        'a UI disse que salvou, mas o parâmetro não persistiu'
    )


def test_exclusao_generica_exige_a_senha_do_usuario(logado_comum, predio_descartavel):
    """A confirmação de exclusão lista o que será apagado e só apaga com a senha certa.

    A senha não é formalidade: ``PasswordField.clean`` chama ``auth.authenticate`` com o usuário
    logado, e é esse segundo fator que separa esta tela de um simples link de apagar — a rota
    aceita a lista de pks pela URL, então sem a senha bastaria adivinhar um pk.

    O prédio é descartável e criado pela fixture: o alvo de um teste de exclusão nunca pode ser
    dado compartilhado, e o banco de e2e é reusado entre execuções.
    """
    from comum.models import Predio

    rota = EXCLUIR.format(app='comum', model='predio', pks=predio_descartavel.pk)

    tela = Tela(logado_comum('admin')).ir(rota)
    tela.ver_titulo('Confirmação de Exclusão')
    tela.ver_texto(predio_descartavel.nome)

    tela.preencher('Senha para confirmação', 'senha', SENHA_E2E)
    tela.clicar_botao('Excluir')

    tela.sucesso('Registro(s) excluído(s) com sucesso.')
    assert not Predio.objects.filter(pk=predio_descartavel.pk).exists(), 'a UI disse que excluiu, mas o registro continua no banco'
