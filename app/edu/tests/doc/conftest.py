"""Substrato da rodada de geração da doc de usuário do ``edu``.

Esta suíte NÃO é de regressão: ela navega o sistema vivo para *descobrir* o que a doc de
usuário vai afirmar e para capturar as telas. Cada teste é um roteiro de tarefa; a asserção
existe só para a rodada falhar alto quando a tela mudou de forma (senão a doc sairia
descrevendo um passo que já não existe).

Reusa por completo o substrato dos e2e do módulo (``edu/tests/e2e/conftest.py``) — relógio
congelado em 2019, replay ORM do seed, papéis — sem duplicar nada. Os dois star-imports são
obrigatórios e nesta ordem:

1. ``djtools.e2e_fixtures`` traz os nomes **privados** (``_django_db_helper``,
   ``_exige_banco_de_e2e``), que ``import *`` do conftest do e2e não reexportaria — é a
   armadilha documentada em ``djtools/e2e_fixtures.py:53-57``;
2. o conftest do e2e traz ``relogio``, ``edu_seed``, ``logado_edu`` e os seeds encadeados.

Ao contrário do ``eventos``, aqui a rodada é fatiada em um arquivo por tarefa da doc, cada
um com o seu ``DATA`` — mas os arquivos são UMA geração, rodada de uma vez. A limpeza do
destino é por sessão (ver ``capturas`` em ``djtools/e2e_fixtures.py``), então rodar uma
fatia sozinha apaga as capturas das outras: é regeneração parcial, útil para depurar a
fatia, não para publicar.

Rodar (a geração inteira, que é o que o CI faz)::

    DATABASE_HOST=localhost DATABASE_PORT=5434 DATABASE_USER=postgres DATABASE_PASSWORD=postgres \\
        TEST_DATABASE_NAME=test_suap_doc_e2e DJANGO_SETTINGS_MODULE=suap.settings_test \\
        uv run pytest -m doc --create-db edu/tests/doc/

``--create-db``, não ``--reuse-db``: banco novo é a condição do CI (o job ``gerar-doc`` roda
``pytest -m doc`` sobre o serviço recém-subido, sem flag nenhuma) e esta suíte **não** é
idempotente entre execuções. Medido em 05/08/2026: com ``--reuse-db``,
``test_vincular_perfis_da_diretoria`` e ``test_responsavel_pela_emissao_de_diploma`` falham na
segunda rodada porque a diretoria já vem com os perfis vinculados da rodada anterior e o popup
de vincular não conclui. O preço é o replay do seed por ORM a cada iteração.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
from django.conf import settings

from djtools.e2e_fixtures import *  # noqa: F403
from djtools.e2e_fixtures import escolher_autocomplete
from edu.tests.e2e.conftest import *  # noqa: F403
from djtools.e2e_ui import Tela

DESTINO = Path(settings.BASE_DIR) / 'edu' / 'docs' / 'usuario'

# A fixture `capturar` é compartilhada (`djtools/e2e_fixtures.py`): viewport, teto do WebP e
# limpeza do destino são os mesmos em todo módulo — só o destino muda.
capturar = capturas(DESTINO)  # noqa: F405

# Telas do `menu.yaml` que a doc de usuário do `edu` NÃO cobre, com o motivo. Ninguém lê este
# dicionário por enquanto: ele é a justificativa escrita da lacuna, para a próxima rodada não
# reabrir a discussão módulo por módulo. O `edu` publica 188 telas com URL no menu; as 17 tarefas
# documentadas cobrem a espinha dorsal acadêmica, e o que sobra são **subsistemas inteiros**
# (censos do MEC, EAD, ENEM, NAPNE, Pé de Meia) que merecem guia próprio, não um parágrafo.
# A seção "O que este guia ainda não cobre" da doc diz o mesmo ao leitor.
TELAS_DISPENSADAS = {
    # Implantação: rodada uma vez por campus, pelo perfil Migrador edu.
    '1. Matrizes': 'carga inicial do Q-Acadêmico — procedimento de implantação, não tarefa do dia a dia',
    '2. Componentes': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '3. Cursos': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '4. Alunos': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '5. Históricos': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '6. Procedimentos de Matrícula': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '7. Equivalências': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    '8. Inicializar período letivo': 'carga inicial do Q-Acadêmico — procedimento de implantação',
    'Listagem de inconsistências': 'relatório de conferência da carga inicial do Q-Acadêmico',
    # Censos e auditoria de dados do MEC.
    'Aberturas Extemporâneas': 'subsistema SISTEC — guia próprio',
    'Configurações de Abertura Extemporânea': 'subsistema SISTEC — guia próprio',
    'Atualizar código de aluno': 'subsistema SISTEC — guia próprio',
    'Auditoria SISTEC -> SUAP': 'subsistema SISTEC — guia próprio',
    'Auditoria SUAP -> SISTEC': 'subsistema SISTEC — guia próprio',
    'Alunos sem Código': 'subsistema EDUCACENSO — guia próprio',
    'Atualizar Código': 'subsistema EDUCACENSO — guia próprio',
    'Questionários': 'subsistema EDUCACENSO — guia próprio',
    'Preencher Campus no Excel': 'subsistema CENSUP — guia próprio',
    'Exportação de Dados': 'subsistema PNP — guia próprio',
    'Listagem de Auditorias': 'auditoria de dados de ensino — guia próprio',
    'Log de Alterações': 'auditoria de dados de ensino — guia próprio',
    'Solicitar Auditoria': 'auditoria de dados de ensino — guia próprio',
    'Indicadores do Ensino': 'painel estatístico, sem tarefa: filtra e lê',
    # Subsistemas com fluxo próprio.
    'Configurações para Certificação': 'subsistema Certificados ENEM — guia próprio',
    'Solicitações de Certificação': 'subsistema Certificados ENEM — guia próprio',
    'Acolhimentos de alunos': 'subsistema NAPNE — guia próprio',
    'Operações': 'subsistema Pé de Meia — guia próprio',
    'Relatos de Inconsistência': 'subsistema Pé de Meia — guia próprio',
    'Aulas de Campo': 'subsistema Seguro de Aula de Campo — guia próprio',
    'Configurações de Seguro': 'subsistema Seguro de Aula de Campo — guia próprio',
    'Editar Polo de Aluno': 'subsistema EAD — guia próprio',
    'Horários de Atendimentos dos Polos': 'subsistema EAD — guia próprio',
    'Rateios de Ofertas EAD': 'subsistema EAD — guia próprio',
    'Caixa de Mensagens': 'comunicador do ensino — guia próprio',
    'Caixa de Saída': 'comunicador do ensino — guia próprio',
    'Nova Mensagem': 'comunicador do ensino — guia próprio',
    'Atas de Projeto Final': 'ata eletrônica de defesa — guia próprio, encadeado ao TCC da tarefa 16',
    'Autorização do uso de imagem': 'fluxo da Comunicação Social, documentado com o módulo eventos',
    # Diplomas: variantes da tarefa 16, com o mesmo desenho de tela.
    'Certificados de Conclusão': 'variante da emissão da tarefa 16, mesmo desenho de tela',
    'Emitir certificação parcial': 'variante da emissão da tarefa 16, mesmo desenho de tela',
    'Histórico Escolar Digital Parcial': 'variante da emissão da tarefa 16, mesmo desenho de tela',
    'Códigos de Autenticação Sistec': 'insumo da emissão da tarefa 16, mantido pela reitoria',
    'FIC, Técnicos e Pós': 'assinatura eletrônica dos diplomas da tarefa 16, configurada pela reitoria',
    # Consultas do aluno e do professor, sem passo a passo próprio.
    'Agenda de Defesas de TCC': 'consulta: lista as defesas marcadas, sem ação',
    'Minhas avaliações': 'consulta do aluno: calendário das avaliações lançadas na tarefa 7',
}


def desfocar(pagina) -> None:
    """No-op histórico: a corrida de foco foi corrigida na raiz.

    Mantido porque as fatias o chamam entre um campo asserido e um autocomplete; remover
    exigiria tocar 23 pontos sem ganho. Ver ``escolher``.
    """
    return


def escolher(page, campo: str, texto: str, **kwargs) -> None:
    """Delega para ``escolher_autocomplete``.

    Existiu para contornar uma corrida de foco: ``escolher_autocomplete`` abria o select2 e
    chamava ``page.keyboard.type`` em seguida, e enquanto a caixa de busca não montava as
    teclas caíam no **último campo focado**. Medido em 03/08/2026 no cadastro de curso — uma
    execução em seis gravava ``codigo='97313çã'``, com o "çã" vindo de "Especializa**çã**o"
    digitado no autocomplete de Modalidade, enquanto a UI dizia "Curso cadastrado com
    sucesso.". ~50% de flake aqui, e corrupção silenciosa onde o campo não era asserido.

    **A raiz foi corrigida** em ``djtools/e2e_fixtures.py`` e ``djtools/e2e_ui.py``: ambos
    agora esperam ``span.select2-container--open`` antes de digitar. Este invólucro sobrevive
    só como nome estável nas fatias.
    """
    escolher_autocomplete(page, campo, texto, **kwargs)


def anotar(titulo: str, tela: Tela) -> None:
    """Despeja cabeçalhos, abas, botões e rótulos da tela para a redação da doc.

    Não é asserção: é o que substitui a leitura de ``views.py`` na hora de escrever o
    passo. As **abas** entram além do que o ``eventos`` despejava porque o ``edu`` monta
    quase toda ficha (diretoria, curso, matriz, aluno, diário) como caderno de abas, e o
    nome delas é passo de doc.
    """
    tela.esperar()
    cabecalhos = tela.pagina.get_by_role('heading').all_inner_texts()
    abas = tela.pagina.locator('//*[contains(@class, "nav-link") and ancestor::*[contains(@class, "nav-tabs")]]').all_inner_texts()
    despejo = (
        f'\n[doc:{titulo}] url={tela.pagina.url}'
        f'\n  cabeçalhos: {[c.strip() for c in cabecalhos if c.strip()]}'
        f'\n  abas: {[a.strip() for a in abas if a.strip()]}'
        f'\n  botões: {tela.botoes_na_tela()}'
        f'\n  rótulos: {tela.rotulos_na_tela()}'
        f'\n  listas: {_opcoes_das_listas(tela)}\n'
    )
    # Arquivo, e não só stderr: quando a rodada fica VERDE o pytest engole o stderr capturado,
    # e é justamente a rodada verde que produz a doc. Fica ao lado das capturas, no diretório
    # que o `.gitignore` já exclui.
    DESTINO.mkdir(parents=True, exist_ok=True)
    with (DESTINO / 'anotacoes.txt').open('a', encoding='utf-8') as arquivo:
        arquivo.write(despejo)
    sys.stderr.write(despejo)


def _opcoes_das_listas(tela: Tela) -> dict[str, list[str]]:
    """``nome do select -> rótulos das opções`` do formulário visível.

    O rótulo que a doc escreve ("Tipo: Acadêmica ou Sistêmica") é o texto da opção, e ele
    não está no ``rotulos_na_tela``. Sem isto, cada valor de lista custa uma execução
    inteira para ser descoberto pela mensagem de erro do ``select_option``.
    """
    opcoes: dict[str, list[str]] = {}
    campos = tela.raiz.locator('//form//select[@name]')
    for indice in range(min(campos.count(), 40)):
        campo = campos.nth(indice)
        nome = campo.get_attribute('name') or ''
        textos = [texto.strip() for texto in campo.locator('option').all_inner_texts() if texto.strip() and texto.strip() != '---------']
        if nome and textos:
            opcoes[nome] = textos[:12]
    return opcoes
