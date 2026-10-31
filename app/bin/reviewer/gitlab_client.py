import logging
import re

import gitlab

logger = logging.getLogger(__name__)


class GitLabClient:
    def __init__(self, url=None, private_token=None, project_id=None):
        """Gitlab login."""
        self.gl = gitlab.Gitlab(url, private_token=private_token)
        self.gl.auth()
        self.project = self.gl.projects.get(int(project_id))
        logger.info(f'Connected to GitLab project {project_id}')

    def get_merge_request(self, mr_id):
        """Fetching Merge Request information."""
        return self.project.mergerequests.get(int(mr_id))

    def count_tokens(self, texto: str) -> int:
        """
        Estima a quantidade de tokens em um texto usando uma aproximação simples.
        Args:
            texto: O texto de entrada para contar os tokens.

        Returns:
            Um número inteiro representando a contagem aproximada de tokens.
        """
        if not isinstance(texto, str):
            return 0

        # A expressão regular encontra:
        # \w+  -> uma ou mais letras/números (palavras inteiras)
        # |    -> OU
        # [^\s\w] -> um único caractere que NÃO é espaço em branco e NÃO é uma letra/número (pontuação/símbolos)
        padrao = r'\w+|[^\s\w]'

        tokens = re.findall(padrao, texto)

        return len(tokens)

    def get_merge_request_diff(self, mr_id, max_tokens=5000):
        """Fetching diff for the Merge Request."""
        mr = self.get_merge_request(mr_id)
        changes = mr.changes()['changes']
        diffs = []
        counter = 0
        partial_diff = ''
        for change in changes:
            if 'diff' not in change:
                logger.warning(f'No diff found for change: {change}')
                continue
            counter += self.count_tokens(change['diff'])
            partial_diff += f'\n{change["diff"]}'
            if counter > max_tokens:
                diffs.append(partial_diff)
                partial_diff = ''
                counter = 0
        diffs.append(partial_diff)  # Add any remaining diff
        return diffs

    def add_comment_to_mr(self, mr_id, comment):
        """Adding a review comment to the Merge Request."""
        mr = self.get_merge_request(mr_id)
        mr.discussions.create({'body': comment})
        logger.info(f'Added review comment to MR {mr_id}.')
