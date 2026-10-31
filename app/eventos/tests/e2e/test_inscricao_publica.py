"""Inscrição de um visitante pela área pública do evento (modo 2).

É o único fluxo do módulo que roda **sem sessão autenticada**, e o único assistente de três
passos: identificação → dados pessoais → tipo de participação, com os dados intermediários
guardados na sessão e cada passo protegido por `@valida_passo_inscricao`
(`eventos/views.py:993,1137`). A regressão típica não é visual: basta uma das cinco
condições de `Evento.pode_inscrever` (`eventos/models.py:1355`) mudar para o passo 1 exibir
"Evento fora do período de inscrição" no lugar do formulário, e a inscrição some da área
pública sem nenhum erro no log.
"""

import pytest

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

AREA_PUBLICA = '/eventos/'

# CPF do cenário: válido nos dígitos verificadores e não repetido (`BrCpfField.clean`)
# e sem vínculo no SUAP, que é o que leva o passo 2 ao ramo de público externo
# (`eventos/views.py:1091-1095`).
CPF_VISITANTE = '987.650.123-21'


def test_visitante_se_inscreve_pela_area_publica(page, evento_com_inscricoes_abertas):
    """Sem login: `page` cru, não `logado_eventos` — a área pública é anônima.

    O campo "Verificação" (reCAPTCHA) da tabela do cenário não é preenchido: sob teste,
    `ReCaptchaField.validate` (`djtools/forms/fields/captcha.py:58-60`) retorna cedo, e o
    behave também não preenchia — não há ramo para o tipo `captcha` em
    `djtools/new_tests/common_steps/when.py`.
    """
    from eventos.models import Participante

    evento = evento_com_inscricoes_abertas

    tela = Tela(page).ir(AREA_PUBLICA)
    tela.ver_titulo('Eventos')
    tela.clicar_link(evento.nome)
    tela.esperar()

    tela.preencher_formulario([('Nacionalidade', 'lista', 'Brasileiro Nato'), ('CPF', 'texto', CPF_VISITANTE)])
    tela.clicar_botao('Continuar')

    tela.preencher_formulario(
        [
            ('Nome', 'texto', 'Usuário Teste'),
            ('E-mail', 'texto', 'teste@teste.com'),
            ('Telefone', 'texto', '(84) 99999-9999'),
        ]
    )
    tela.clicar_botao('Continuar')

    tela.preencher('Tipo de participação', 'lista', 'Participante')
    tela.clicar_botao('Confirmar inscrição')

    tela.ver_texto('Inscrição realizada com sucesso.')
    assert Participante.objects.filter(evento=evento, cpf=CPF_VISITANTE).exists(), 'a UI disse que inscreveu, mas não persistiu'
