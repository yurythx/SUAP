"""Escolhe quais módulos o job ``gerar-doc`` regera, reaproveitando as capturas dos demais.

Cada módulo com ``<modulo>/tests/doc/`` tem uma impressão digital: o hash da árvore
``git rev-parse HEAD:<modulo>``, que muda com qualquer arquivo do módulo (view, template, roteiro,
``usuario.md``). As impressões das capturas publicadas vão em ``doc_impressoes.json``, DENTRO do
artifact do ``gerar-doc`` — não no git, como as próprias capturas (#16999).

O job baixa o artifact do último ``gerar-doc`` verde, põe as capturas no lugar, apaga as dos
módulos selecionados e imprime ``<modulo>/tests/doc`` de cada um para o pytest. O artifact novo
sai sempre COMPLETO (reaproveitadas + regeradas), porque o ``mkdocs --strict`` do
``empacotar-doc`` aborta com captura faltando — e é isso que deixa a próxima rodada ter de onde
reaproveitar.

Seleção (``DOC_MODULOS``, preenchido no botão do job manual):

- ``todos``: todos os módulos com doc;
- ``edu,ae``: exatamente esses, ignorando a impressão;
- vazio: os módulos cuja impressão difere da registrada (ou que não têm registro).

Só os módulos que rodaram ganham impressão nova; os outros mantêm a antiga. Assim, um módulo
que mudou mas ficou de fora de um ``DOC_MODULOS`` volta na próxima rodada automática.

ponytail: a impressão cobre só a pasta do módulo. Mudança em template/tema do ``comum`` ou no
harness (``djtools/e2e_ui.py``, que muda ~2x por semana) não invalida os outros módulos —
a captura fica visualmente defasada até um ``DOC_MODULOS=todos``.

Qualquer falha ao baixar o anterior (sem token, rede, primeiro artifact sem manifesto) cai em
rodada completa: mais lenta, nunca errada.
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from collections.abc import Iterable, Mapping
from pathlib import Path

MANIFESTO = Path('doc_impressoes.json')
NOME_DO_JOB = 'gerar-doc'
CONSULTA_ULTIMO_JOB = """
query($projeto: ID!, $nome: String!) {
  project(fullPath: $projeto) {
    jobs(statuses: [SUCCESS], name: $nome, first: 1) { nodes { id } }
  }
}
"""


def log(mensagem: str) -> None:
    """Diagnóstico vai para stderr: o stdout é a lista de caminhos que o job passa ao pytest."""
    sys.stderr.write(f'[doc_incremental] {mensagem}\n')


def modulos_com_doc() -> list[str]:
    return sorted(caminho.parts[0] for caminho in Path().glob('*/tests/doc') if caminho.is_dir())


def impressoes(modulos: list[str]) -> dict[str, str]:
    """Hash da árvore de cada módulo em ``HEAD`` — no CI, depois do merge de ``origin/master``."""
    saida = subprocess.run(['git', 'rev-parse', *(f'HEAD:{modulo}' for modulo in modulos)], capture_output=True, text=True, check=True)
    return dict(zip(modulos, saida.stdout.split(), strict=True))


def selecionar(pedido: str, atuais: Mapping[str, str], anteriores: Mapping[str, str]) -> list[str]:
    """Módulos a regerar. Nome inexistente aborta: rodar menos que o pedido e sair verde seria pior."""
    pedido = pedido.strip()
    if pedido == 'todos':
        return sorted(atuais)
    if not pedido:
        return sorted(modulo for modulo, impressao in atuais.items() if anteriores.get(modulo) != impressao)
    pedidos = {nome.strip() for nome in pedido.split(',') if nome.strip()}
    invalidos = pedidos - set(atuais)
    if invalidos:
        raise SystemExit(f'DOC_MODULOS sem <modulo>/tests/doc: {", ".join(sorted(invalidos))}. Válidos: {", ".join(sorted(atuais))}')
    return sorted(pedidos)


def manifesto_novo(atuais: Mapping[str, str], anteriores: Mapping[str, str], selecionados: Iterable[str]) -> dict[str, str]:
    """Impressão atual para quem rodou; a anterior para os demais; módulo sem doc sai."""
    novo = {modulo: anteriores[modulo] for modulo in atuais if modulo in anteriores}
    novo.update({modulo: atuais[modulo] for modulo in selecionados})
    return dict(sorted(novo.items()))


def _requisicao(url: str, token: str, corpo: dict | None = None) -> bytes:
    dados = json.dumps(corpo).encode() if corpo is not None else None
    cabecalhos = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
    requisicao = urllib.request.Request(url, data=dados, headers=cabecalhos)  # noqa: S310 — URL vem das variáveis do GitLab CI
    with urllib.request.urlopen(requisicao, timeout=120) as resposta:  # noqa: S310
        return resposta.read()


def baixar_anterior() -> bool:
    """Extrai no diretório atual o artifact do último ``gerar-doc`` verde, de qualquer ref.

    Qualquer ref serve porque a impressão protege: captura de outra branch só é reaproveitada se a
    árvore do módulo for idêntica à de agora. Busca por GraphQL (filtro por nome) porque o
    ``jobs/artifacts/<ref>/download`` só olha pipeline com status ``success`` — e o pipeline de um
    job manual fica ``manual`` para sempre (404 medido no job 436047). O ``CI_JOB_TOKEN`` não
    acessa GraphQL, daí o token do bot.
    """
    token = os.environ.get('SUAP_BOT_TOKEN')
    servidor, projeto, api = (os.environ.get(nome) for nome in ('CI_SERVER_URL', 'CI_PROJECT_PATH', 'CI_API_V4_URL'))
    if not (token and servidor and projeto and api):
        log('fora do CI ou sem SUAP_BOT_TOKEN: sem capturas anteriores')
        return False
    try:
        corpo = {'query': CONSULTA_ULTIMO_JOB, 'variables': {'projeto': projeto, 'nome': NOME_DO_JOB}}
        nos = json.loads(_requisicao(f'{servidor}/api/graphql', token, corpo))['data']['project']['jobs']['nodes']
        if not nos:
            log(f'nenhum {NOME_DO_JOB} verde anterior')
            return False
        job_id = nos[0]['id'].rsplit('/', 1)[-1]
        arquivo = _requisicao(f'{api}/projects/{os.environ["CI_PROJECT_ID"]}/jobs/{job_id}/artifacts', token)
        zipfile.ZipFile(io.BytesIO(arquivo)).extractall()
    except Exception as erro:  # qualquer falha vira rodada completa, que é segura
        log(f'falha ao baixar o artifact anterior ({erro!r}): rodada completa')
        return False
    log(f'capturas reaproveitadas do job {job_id}')
    return True


def main() -> None:
    anteriores: dict[str, str] = {}
    if baixar_anterior() and MANIFESTO.exists():
        anteriores = json.loads(MANIFESTO.read_text())
    atuais = impressoes(modulos_com_doc())
    selecionados = selecionar(os.environ.get('DOC_MODULOS', ''), atuais, anteriores)
    for modulo in selecionados:
        shutil.rmtree(Path(modulo, 'docs', 'usuario'), ignore_errors=True)
    faltando = [modulo for modulo in atuais if modulo not in selecionados and not Path(modulo, 'docs', 'usuario').exists()]
    if faltando:
        log(f'sem captura publicada e fora da seleção (o empacotar-doc vai reclamar): {", ".join(faltando)}')
    # Escrito ANTES do pytest de propósito: se o pytest falhar o job não sobe artifact (on_success),
    # e o manifesto some junto com as capturas incompletas.
    MANIFESTO.write_text(json.dumps(manifesto_novo(atuais, anteriores, selecionados), indent=2) + '\n')
    log(f'regerando {len(selecionados)} de {len(atuais)}: {", ".join(selecionados) or "nenhum"}')
    sys.stdout.write(' '.join(f'{modulo}/tests/doc' for modulo in selecionados) + '\n')


if __name__ == '__main__':
    main()
