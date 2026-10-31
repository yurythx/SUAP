"""Smoke de rota do Saúde (modo 2: a unidade é a tela).

Abre em lote as telas de leitura e de formulário — as que renderizam sem mudar estado — com
`Tela.buscar` (GET sem renderizar). As ações, os downloads de PDF/planilha e as telas de
impressão ficam em `ROTAS_DISPENSADAS`, no conftest, com o motivo.

Os alvos (prontuário, atendimentos, avaliação) são resolvidos do que a cadeia `test_01`→`test_09`
criou. A falha lista **todas** as rotas quebradas de uma vez. As rotas da atividade em grupo ficam
em `test_17_rotas_atividade.py`, junto do `test_11` que cria o alvo: os dois rodam na suíte
`saude-2` (`DIVISOES_E2E` no `suap_check`), sem a cadeia.

Ficam fora do smoke, e cobertas por teste próprio com o papel certo: as telas restritas aos
grupos clínicos (`exame_laboratorial_valores_referencia`, `adicionar_exame_*`,
`atendimento_psicologico`, `ver_historico_validacao_passaporte`, os relatórios de passaporte),
a tela com defeito de produto conhecido — `passaporte_vacinacao_covid` (não renderiza o
formulário de autodeclaração) — e o que já está em `ROTAS_DISPENSADAS`.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from playwright.sync_api import Page

from djtools.e2e_ui import Tela

pytestmark = [pytest.mark.e2e, pytest.mark.django_db(databases='__all__')]

# Sem parâmetro: listagens, relatórios e gráficos que renderizam tela.
ROTAS_SEM_PARAMETRO = [
    '/saude/prontuarios/',
    '/saude/agenda_atendimentos/',
    '/saude/ver_calendario_agendamento/',
    '/saude/lista_alunos/',
    '/saude/anotacoes_pendentes/',
    '/saude/estatistica_geral_atendimento/',
    '/saude/indicadores/',
    '/saude/graficos_antropometria/',
    '/saude/graficos_acuidade_visual/',
    '/saude/graficos_saude_doenca/',
    '/saude/graficos_desenvolvimento_pessoal/',
    '/saude/graficos_exame_fisico/',
    '/saude/graficos_percepcao_saude_bucal/',
    '/saude/graficos_vacinas/',
    '/saude/relatorio_cartoes_vacinais/',
    '/saude/relatorio_atendimento_odontologia/',
    '/saude/relatorio_atendimento_medico_enfermagem/',
    '/saude/relatorio_avaliacao_biomedica/',
    '/saude/relatorio_notificacao_covid/',
    '/saude/relatorios_atendimentos_odontologicos/',
    '/saude/relatorio_atendimento_psicologia/',
    '/saude/antropometria_valores_referencia/',
    '/saude/cartao_vacinal/',
    '/saude/cadastrar_pessoa_externa/',
    '/saude/acompanhamento_anotacoes_interdisciplinares/',
]

# Com parâmetro: telas de detalhe e formulários sobre os objetos da cadeia.
ROTAS_COM_ALVO = [
    '/saude/prontuario/{vinculo}/',
    '/saude/atendimento_medico_enfermagem/{atendimento_medico}/',
    '/saude/atendimento_odontologico/{atendimento_odonto}/',
    '/saude/atendimento_nutricional/{atendimento_nutri}/',
    '/saude/atendimento_fisioterapia/{atendimento_fisio}/',
    '/saude/atendimento_multidisciplinar/{atendimento_multi}/',
    '/saude/avaliacao_biomedica/{avaliacao}/',
    '/saude/adicionar_encaminhamento/{prontuario}/',
    '/saude/adicionar_anotacao_interdisciplinar/{prontuario}/',
    '/saude/adicionar_documento_prontuario/{vinculo}/',
    '/saude/adicionar_anexo_prontuario/{vinculo}/',
    '/saude/adicionar_cartao_vacinal/{vinculo}/',
    '/saude/editar_cartao_sus/{aluno}/',
    '/saude/historico_cartao_vacinal/{vinculo}/',
]


def _alvos() -> dict[str, int]:
    """Resolve os alvos da cadeia ou explica a dependência sequencial."""
    from edu.models import Aluno
    from saude.models import (
        Atendimento,
        Prontuario,
        TipoAtendimento,
    )

    aluno = Aluno.objects.get(matricula='20191101011111')
    prontuario = Prontuario.objects.filter(vinculo=aluno.get_vinculo()).first()
    assert prontuario is not None, 'prontuário ausente: a cadeia é sequencial, rode `pytest saude/tests/e2e` inteiro'

    alvos = {'prontuario': prontuario.pk, 'vinculo': prontuario.vinculo_id, 'aluno': aluno.pk}
    for chave, tipo in (
        ('atendimento_medico', TipoAtendimento.ENFERMAGEM_MEDICO),
        ('atendimento_odonto', TipoAtendimento.ODONTOLOGICO),
        ('atendimento_psi', TipoAtendimento.PSICOLOGICO),
        ('atendimento_nutri', TipoAtendimento.NUTRICIONAL),
        ('atendimento_fisio', TipoAtendimento.FISIOTERAPIA),
        ('atendimento_multi', TipoAtendimento.MULTIDISCIPLINAR),
        ('avaliacao', TipoAtendimento.AVALIACAO_BIOMEDICA),
    ):
        atendimento = Atendimento.objects.filter(aluno__matricula='20191101011111', tipo=tipo).order_by('-id').first()
        assert atendimento is not None, f'atendimento do tipo {tipo} ausente na cadeia'
        alvos[chave] = atendimento.pk
    return alvos


def _abrir(tela: Tela, rotas: list[str], alvos: dict[str, int]) -> list[str]:
    """Percorre as rotas e devolve a lista de falhas, sem parar na primeira."""
    falhas = []
    for rota in rotas:
        url = rota.format_map(alvos)
        try:
            resposta = tela.buscar(url)
        except Exception as erro:
            falhas.append(f'{url} -> {type(erro).__name__}: {str(erro).splitlines()[0]}')
            continue
        if resposta.status == 200:
            continue
        if resposta.status in (301, 302):
            destino = resposta.headers.get('location', '')
            if 'login' in destino:
                falhas.append(f'{url} -> redirect para o login ({destino})')
            continue
        falhas.append(f'{url} -> HTTP {resposta.status}')
    return falhas


def test_rotas_abrem(logado_saude: Callable[[str], Page]) -> None:
    """O coordenador sistêmico abre, em lote, as telas de leitura e de formulário do módulo."""
    alvos = _alvos()
    tela = Tela(logado_saude('coordenador_sistemico'))
    falhas = _abrir(tela, ROTAS_SEM_PARAMETRO, alvos) + _abrir(tela, ROTAS_COM_ALVO, alvos)
    total = len(ROTAS_SEM_PARAMETRO) + len(ROTAS_COM_ALVO)
    assert not falhas, f'{len(falhas)} de {total} rotas não abriram:\n  ' + '\n  '.join(falhas)
