from __future__ import annotations

from datetime import date

from dateutil.relativedelta import relativedelta

from comum.models import Configuracao
from djtools.utils import requests
from erros.models import Erro


class ContribuicoesGitlab:
    """Obtém e classifica as contribuições de um usuário no GitLab via API de Events."""

    def __init__(self, gitlab_username: str):
        self.gitlab_username = gitlab_username
        self.gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
        self.gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')
        self.token = Configuracao.get_valor_por_chave('demandas', 'gitlab_token')
        self.header = {'accept': 'application/json', 'Authorization': f'Bearer {self.token}'}
        self.contribuicoes: list[dict] = []
        self._contribuicoes_detalhadas: list[dict] = []
        self._project_web_url: str | None = None
        self._issues: dict[str, dict] = {}
        self._mrs: dict[str, dict] = {}
        self._issues_das_mrs: dict[str, list[dict]] = {}

    def _get_user_gitlab(self) -> int | None:
        try:
            url = f'{self.gitlab_url}api/v4/users'
            params = {'username': self.gitlab_username}
            response = requests.get(url, params=params, headers=self.header)
            response.raise_for_status()
            usuarios = response.json()
            return usuarios[0].get('id') if usuarios else None
        except Exception:
            return None

    """
    def get_milestone_bugs(self) -> dict | None:
        # Retorna a milestone de título 'Bugs' (usada para vincular contribuições a erros)
        url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}/milestones'
        response = requests.get(url=url, params={'search': 'bugs'}, headers=self.header)
        dados = response.json()
        if not isinstance(dados, list):
            return None
        for milestone in dados:
            if 'bugs' in str(milestone.get('title', '')).lower():
                return milestone
        return None
    """

    def _get_work_item(self, issue_iid: str | int) -> dict | None:
        chave = str(issue_iid)
        if chave in self._issues:
            return self._issues[chave]
        url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}/issues/{chave}'
        response = requests.get(url=url, headers=self.header)
        if response.status_code != 200:
            return None
        self._issues[chave] = response.json()
        return self._issues[chave]

    def _get_merge_request(self, mr_iid: str | int) -> dict | None:
        chave = str(mr_iid)
        if chave in self._mrs:
            return self._mrs[chave]
        url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}/merge_requests/{chave}'
        response = requests.get(url=url, headers=self.header)
        if response.status_code != 200:
            return None
        self._mrs[chave] = response.json()
        return self._mrs[chave]

    def _get_mrs_da_issue(self, issue_iid: str | int) -> list[dict]:
        url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}/issues/{issue_iid}/related_merge_requests'
        response = requests.get(url=url, headers=self.header)
        if response.status_code != 200:
            return []
        return response.json()

    def _get_issues_da_mr(self, mr_iid: str | int) -> list[dict]:
        chave = str(mr_iid)
        if chave in self._issues_das_mrs:
            return self._issues_das_mrs[chave]
        url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}/merge_requests/{chave}/related_issues'
        response = requests.get(url=url, headers=self.header)
        if response.status_code != 200:
            return []
        self._issues_das_mrs[chave] = response.json()
        return self._issues_das_mrs[chave]

    def existe_configuracao_gitlab(self) -> bool:
        return all([self.gitlab_username, self.gitlab_url, self.gitlab_suap_id, self.token])

    def obter_contribuicoes(self, data_inicio: date, data_final: date) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        #
        data_inicio = data_inicio + relativedelta(days=-1)
        data_final = data_final + relativedelta(days=1)
        #
        user_id = self._get_user_gitlab()
        if not user_id:
            return []

        def get() -> list:
            dados: list = []
            pagina = 1
            total_paginas = 1
            while pagina <= total_paginas:
                url = f'{self.gitlab_url}api/v4/users/{user_id}/events'
                params = {'after': data_inicio, 'before': data_final, 'per_page': 100, 'sort': 'desc', 'page': pagina}
                response = requests.get(url=url, params=params, headers=self.header)
                dados_pagina = response.json()
                if not isinstance(dados_pagina, list):
                    break
                dados += dados_pagina
                total_paginas = int(response.headers.get('x-total-pages') or 1)
                pagina += 1
            return dados

        self.contribuicoes = [acao for acao in get() if isinstance(acao, dict) and str(acao.get('project_id')) == str(self.gitlab_suap_id)]
        self._contribuicoes_detalhadas = self._detalhar_todas()
        return self.contribuicoes

    # --- Classificação ---

    def get_issues_relacionadas_a_erros(self) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        return [c for c in self._contribuicoes_detalhadas if c['tipo'] == 'issue' and c['relacionado_a_erro']]

    def get_issues_nao_relacionadas_a_erros(self) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        return [c for c in self._contribuicoes_detalhadas if c['tipo'] == 'issue' and not c['relacionado_a_erro']]

    def get_merge_requests_relacionadas_a_erros(self) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        return [c for c in self._contribuicoes_detalhadas if c['tipo'] == 'merge_request' and c['relacionado_a_erro']]

    def get_merge_requests_nao_relacionadas_a_erros(self) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        return [c for c in self._contribuicoes_detalhadas if c['tipo'] == 'merge_request' and not c['relacionado_a_erro']]

    def get_outras_contribuicoes(self) -> list[dict]:
        if not self.existe_configuracao_gitlab():
            return []
        return [c for c in self._contribuicoes_detalhadas if c['tipo'] == 'outra']

    # --- Detalhamento ---

    def _detalhar_todas(self) -> list[dict]:
        issues: dict[str, dict] = {}
        mrs: dict[str, dict] = {}
        outras: list[dict] = []

        for acao in self.contribuicoes:
            detalhe = self._detalhar_acao(acao)
            if detalhe is None:
                continue
            self._agrupar_contribuicao(detalhe, issues, mrs, outras)

        for issue in issues.values():
            issue['mrs_relacionadas'] = []
            for mr in self._mrs_relacionados(issue):
                issue['mrs_relacionadas'].append({'iid': mr['iid'], 'url': mr['url'], 'titulo': mr['titulo']})
                if mr['iid'] not in mrs:
                    mrs[mr['iid']] = mr

        for mr in mrs.values():
            mr['issues_relacionadas'] = self._issues_relacionadas(mr)

        return [*issues.values(), *mrs.values(), *outras]

    def _agrupar_contribuicao(self, detalhe: dict, issues: dict[str, dict], mrs: dict[str, dict], outras: list[dict]) -> None:
        if detalhe['tipo'] == 'issue':
            alvo = issues.setdefault(detalhe['iid'], detalhe)
            if alvo is not detalhe:
                self._mesclar_acoes(alvo, detalhe)
        elif detalhe['tipo'] == 'merge_request':
            alvo = mrs.setdefault(detalhe['iid'], detalhe)
            if alvo is not detalhe:
                self._mesclar_acoes(alvo, detalhe)
        else:
            outras.append(detalhe)

    def _mesclar_acoes(self, alvo: dict, detalhe: dict) -> None:
        for acao in detalhe['acoes']:
            if acao not in alvo['acoes']:
                alvo['acoes'].append(acao)

    def _detalhar_acao(self, acao: dict) -> dict | None:
        if acao.get('target_type') == 'WorkItem':
            return self._detalhar_issue(acao.get('target_iid'), acao.get('action_name'), acao.get('target_title'))

        if acao.get('target_type') == 'MergeRequest':
            return self._detalhar_mr(acao.get('target_iid'), acao.get('action_name'), acao.get('target_title'))

        if acao.get('target_type') == 'Note':
            nota = acao.get('note') or acao.get('detalhes', {}).get('note', {})
            noteable_type = nota.get('noteable_type')
            noteable_iid = nota.get('noteable_iid')
            if noteable_type in ('Issue', 'WorkItem') and noteable_iid:
                return self._detalhar_issue(noteable_iid, 'commented on', nota.get('noteable_title'))
            if noteable_type == 'MergeRequest' and noteable_iid:
                return self._detalhar_mr(noteable_iid, 'commented on', nota.get('noteable_title'))

        return self._detalhar_outra(acao)

    def _detalhar_issue(self, issue_iid: str | int | None, action: str | None, title: str | None = None) -> dict | None:
        if not issue_iid:
            return None
        wi = self._get_work_item(issue_iid)
        url = (wi or {}).get('web_url') or self._url_projeto(f'issues/{issue_iid}')
        return {
            'tipo': 'issue',
            'iid': str(issue_iid),
            'titulo': wi.get('title') if wi else title,
            'url': url,
            'acoes': [action] if action else [],
            'assignees': [a.get('name') for a in (wi or {}).get('assignees') or []],
            'relacionado_a_erro': self._tem_milestone_bugs(wi),
        }

    def _detalhar_mr(self, mr_iid: str | int | None, action: str | None = None, title: str | None = None) -> dict | None:
        if not mr_iid:
            return None
        mr = self._get_merge_request(mr_iid)
        url = (mr or {}).get('web_url') or self._url_projeto(f'merge_requests/{mr_iid}')
        return {
            'tipo': 'merge_request',
            'iid': str(mr_iid),
            'titulo': mr.get('title') if mr else title,
            'url': url,
            'acoes': [action] if action else [],
            'assignees': [a.get('name') for a in (mr or {}).get('assignees') or []],
            'relacionado_a_erro': self._tem_milestone_bugs(mr),
        }

    def _detalhar_outra(self, acao: dict) -> dict:
        return {
            'tipo': 'outra',
            'iid': str(acao.get('id') or ''),
            'titulo': acao.get('target_title') or acao.get('title') or acao.get('action_name') or 'Contribuição',
            'url': self._extrair_url_acao(acao),
            'acoes': [acao.get('action_name')] if acao.get('action_name') else [],
            'assignees': [],
            'relacionado_a_erro': False,
        }

    def _mrs_relacionados(self, issue: dict) -> list[dict]:
        mrs: list[dict] = []
        for mr in self._get_mrs_da_issue(issue['iid']):
            if not mr.get('iid'):
                continue
            detalhe = self._detalhar_mr(mr['iid'])
            if not detalhe:
                continue
            detalhe['relacionado_a_erro'] = detalhe['relacionado_a_erro'] or issue['relacionado_a_erro']
            mrs.append(detalhe)
        return mrs

    def _issues_relacionadas(self, mr: dict) -> list[dict]:
        return [
            {'iid': str(issue.get('iid')), 'url': issue.get('web_url'), 'titulo': issue.get('title')}
            for issue in self._get_issues_da_mr(mr['iid'])
            if issue.get('iid')
        ]

    def _tem_milestone_bugs(self, dados: dict | None) -> bool:
        if not dados:
            return False
        if dados.get('source_branch') is not None:
            # Merge request: relacionada a erro se alguma issue relacionada estiver vinculada a bug
            return any(self._tem_milestone_bugs(issue) for issue in self._get_issues_da_mr(dados.get('iid')))
        return (
            'bugs' in str((dados.get('milestone') or {}).get('title', '')).lower()
            or Erro.objects.filter(gitlab_issue_url__icontains=dados.get('iid')).exists()
        )

    def _extrair_url_acao(self, acao: dict) -> str | None:
        push_data = acao.get('push_data') or {}
        if push_data.get('ref'):
            return self._url_projeto(f'commits/{push_data["ref"]}')
        target_type = acao.get('target_type')
        target_iid = acao.get('target_iid')
        if target_type == 'MergeRequest' and target_iid:
            return self._url_projeto(f'merge_requests/{target_iid}')
        if target_type in ('WorkItem', 'Issue') and target_iid:
            return self._url_projeto(f'issues/{target_iid}')
        return acao.get('target_url') or acao.get('url')

    def _url_projeto(self, path: str) -> str | None:
        base = self._get_project_web_url()
        return f'{base}/-/{path}' if base else None

    def _get_project_web_url(self) -> str | None:
        if self._project_web_url is None:
            url = f'{self.gitlab_url}api/v4/projects/{self.gitlab_suap_id}'
            response = requests.get(url=url, headers=self.header)
            if response.status_code == 200:
                self._project_web_url = response.json().get('web_url', '').rstrip('/')
        return self._project_web_url
