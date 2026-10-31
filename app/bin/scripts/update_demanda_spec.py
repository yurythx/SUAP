#!/usr/bin/env python3
"""CI script: on merge to master, reads the approved spec-delta comment from
the merged MR and creates a DecisaoEspecificacao in SUAP.

Required env vars:
  GITLAB_TOKEN   - GitLab token (use CI_JOB_TOKEN in CI)
  SUAP_TOKEN     - SUAP service account JWT
  CI_COMMIT_SHA  - provided by GitLab CI
  CI_PROJECT_ID  - provided by GitLab CI
  GITLAB_BASE_URL - default: https://gitlab.ifrn.edu.br
  SUAP_BASE_URL   - default: https://suap.ifrn.edu.br
"""

from __future__ import annotations

import os
import re
import sys

import httpx

GITLAB_TOKEN = os.environ['GITLAB_TOKEN']
SUAP_TOKEN = os.environ['SUAP_TOKEN']
COMMIT_SHA = os.environ['CI_COMMIT_SHA']
PROJECT_ID = os.environ['CI_PROJECT_ID']
GITLAB_BASE = os.environ.get('GITLAB_BASE_URL', 'https://gitlab.ifrn.edu.br')
SUAP_BASE = os.environ.get('SUAP_BASE_URL', 'https://suap.ifrn.edu.br')

_GITLAB_HEADERS = {'JOB-TOKEN': GITLAB_TOKEN}
_SUAP_HEADERS = {'Authorization': f'Bearer {SUAP_TOKEN}'}
_API = f'{GITLAB_BASE}/api/v4'


def _log(msg: str) -> None:
    sys.stdout.write(msg + '\n')
    sys.stdout.flush()


_META_RE = re.compile(r'<!--\s*suap-meta\s*\ndemanda_id:\s*(\d+)\s*\n-->')
_BRANCH_RE = re.compile(r'demanda-(\d+)')
_DELTA_MARKER = '<!-- spec-delta:'
_DELTA_CONTENT_RE = re.compile(r'### Delta proposto\n(.+?)(?=\n##|\n<!--|$)', re.DOTALL)


def _gitlab_get(path: str, **kwargs) -> list | dict:
    r = httpx.get(f'{_API}{path}', headers=_GITLAB_HEADERS, timeout=30, **kwargs)
    r.raise_for_status()
    return r.json()


def _find_merged_mr() -> dict | None:
    mrs = _gitlab_get(f'/projects/{PROJECT_ID}/repository/commits/{COMMIT_SHA}/merge_requests')
    merged = [m for m in mrs if m.get('state') == 'merged']
    return merged[0] if merged else None


def _extract_demanda_id(mr: dict) -> int | None:
    description = mr.get('description') or ''
    m = _META_RE.search(description)
    if m:
        return int(m.group(1))
    branch = mr.get('source_branch', '')
    m = _BRANCH_RE.search(branch)
    if m:
        return int(m.group(1))
    return None


def _find_spec_delta_note(mr_iid: int) -> dict | None:
    notes = _gitlab_get(
        f'/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes',
        params={'per_page': 100, 'sort': 'asc'},
    )
    for note in notes:
        if _DELTA_MARKER in note.get('body', ''):
            return note
    return None


def _get_approved_content(mr_iid: int, note: dict) -> str | None:
    note_id = note['id']
    note_body = note['body']

    # Check for explicit rejection (🚫)
    reactions = _gitlab_get(f'/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes/{note_id}/award_emoji')
    emoji_names = {r['name'] for r in reactions}
    if 'no_entry_sign' in emoji_names:
        _log('[skip] 🚫 reaction on spec-delta comment — explicitly rejected')
        return None

    # Check for thumbsup (👍) reaction → use comment content
    if 'thumbsup' in emoji_names:
        m = _DELTA_CONTENT_RE.search(note_body)
        return m.group(1).strip() if m else note_body.strip()

    # Check for dev reply in the same discussion thread
    bot_author_id = note.get('author', {}).get('id')
    discussions = _gitlab_get(f'/projects/{PROJECT_ID}/merge_requests/{mr_iid}/discussions')
    for discussion in discussions:
        notes_in = discussion.get('notes', [])
        note_ids = [n['id'] for n in notes_in]
        if note_id in note_ids:
            human_replies = [n for n in notes_in if n['id'] != note_id and n.get('author', {}).get('id') != bot_author_id]
            if human_replies:
                return human_replies[-1]['body'].strip()

    return None  # No approval signal


def _post_mr_comment(mr_iid: int, body: str) -> None:
    r = httpx.post(
        f'{_API}/projects/{PROJECT_ID}/merge_requests/{mr_iid}/notes',
        headers=_GITLAB_HEADERS,
        json={'body': body},
        timeout=30,
    )
    if not r.is_success:
        _log(f'[warn] Failed to post MR comment (HTTP {r.status_code})')


def _apply_spec_delta(demanda_id: int, decisao: str, mr_iid: int) -> None:
    r = httpx.post(
        f'{SUAP_BASE}/api/ti/demandas/{demanda_id}/spec-decisions/',
        headers=_SUAP_HEADERS,
        json={
            'decisao': decisao,
            'origem': 'agente-ci',
            'contexto': {'mr_iid': mr_iid, 'commit_sha': COMMIT_SHA},
        },
        timeout=30,
    )
    if r.status_code == 404:
        _log(f'[warn] Demanda {demanda_id} not found in SUAP — skipping')
        sys.exit(0)
    if r.status_code == 403:
        _log(f'[warn] SUAP token lacks permission for demanda {demanda_id} — skipping')
        sys.exit(0)
    r.raise_for_status()
    _log(f'[ok] DecisaoEspecificacao created for demanda {demanda_id} (MR !{mr_iid})')


def _main() -> None:
    mr = _find_merged_mr()
    if not mr:
        _log('[skip] No merged MR found for this commit')
        sys.exit(0)

    mr_iid = mr['iid']
    demanda_id = _extract_demanda_id(mr)
    if demanda_id is None:
        _log(f'[warn] No demanda_id in MR !{mr_iid} (no suap-meta block, no demanda-N branch)')
        sys.exit(0)

    note = _find_spec_delta_note(mr_iid)
    if not note:
        _log(f'[skip] No spec-delta comment found in MR !{mr_iid}')
        sys.exit(0)

    approved = _get_approved_content(mr_iid, note)
    if approved is None:
        _post_mr_comment(
            mr_iid,
            '⚠️ **Spec delta não aplicado** — nenhum sinal de aprovação encontrado.\n'
            'Adicione 👍 ao comment de proposta ou responda com a versão corrigida '
            'para que a spec seja atualizada automaticamente no próximo push.',
        )
        _log(f'[warn] No approval signal on spec-delta comment in MR !{mr_iid}')
        sys.exit(0)

    _apply_spec_delta(demanda_id, approved, mr_iid)


def main() -> None:
    try:
        _main()
    except Exception as exc:
        _log(f'[error] Unexpected error: {exc}')
        sys.exit(0)


if __name__ == '__main__':
    main()
