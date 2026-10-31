import gitlab
from gitlab import GitlabError
from requests.exceptions import RequestException

from comum.models import Configuracao
from djtools.management.commands import BaseCommandPlus


class Command(BaseCommandPlus):
    def handle(self, *args, **options) -> None:
        """
        - Considerando que este comando será rodado pelo comando `sync`
          quando tiver atualizacao em producao
        - Objetivos
          - Marca com label "state: Production" os MRs `merged` do gitlab que
            ainda nao foram atualizados em producao.

        Referencias
        - https://docs.gitlab.com/ee/api/merge_requests.html
        - https://python-gitlab.readthedocs.io/en/stable/gl_objects/merge_requests.html
        - https://stackoverflow.com/questions/67005558/how-to-use-not-condition-in-the-gitlab-api-issue-query

        """

        gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url')
        gitlab_token = Configuracao.get_valor_por_chave('demandas', 'gitlab_token')
        gitlab_suap_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id')

        if gitlab_url and gitlab_token and gitlab_suap_id:
            git = gitlab.Gitlab(gitlab_url, private_token=gitlab_token, timeout=60)

            # Lista os MRs merged que nao estao com o label "state: Production"
            extra_params = {'not[labels]': 'state: Production'}

            try:
                # get_all materializa todas as páginas antes de rotular: rotular durante a paginação por offset
                # tira os MRs do filtro e pula páginas. O antigo `as_list=False` é ignorado pelo python-gitlab
                # atual e só a 1ª página (20 MRs) era rotulada.
                mrs = git.projects.get(gitlab_suap_id).mergerequests.list(get_all=True, state='merged', **extra_params)
            except GitlabError, RequestException:
                self.stderr.write('Problema de conexão com o gitlab.')
                return

            for mr in mrs:
                try:
                    # Atualiza os MRs `merged` com o "state: Production" (que efetivamente foram pra producao)
                    mr.labels.append('state: Production')
                    mr.save()
                except GitlabError, RequestException:
                    continue
