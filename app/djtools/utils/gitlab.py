import time

from django.conf import settings
from requests.exceptions import RequestException

from comum.models import Configuracao

from . import requests

__all__ = [
    'GitlabJobError',
    'access_token',
    'base_url',
    'create_pipeline',
    'execute_job',
    'get_job_id',
    'get_merge_request',
    'headers',
    'job_log',
    'list_branche_names',
]

# Job manual recém-criado nasce `created` e só vira `manual` quando o GitLab termina de processar o
# pipeline, de forma assíncrona. Um `play` nesse intervalo é recusado (`400 Unplayable Job`).
JOB_STATUS_EXECUTAVEL = 'manual'
JOB_STATUS_REEXECUTAVEIS = ('success', 'failed', 'canceled')
# ponytail: espera curta e fixa (~10 s), pois roda também dentro de request web; se o GitLab
# passar a demorar mais, mover o disparo para uma task assíncrona.
TENTATIVAS_JOB = 5
INTERVALO_JOB = 2


class GitlabJobError(Exception):
    pass


def access_token():
    return Configuracao.get_valor_por_chave('demandas', 'gitlab_token', 'GITLAB_API_TOKEN')


def base_url():
    gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url', 'GITLAB_URL')
    api_version = Configuracao.get_valor_por_chave('demandas', 'gitlab_api_version', 'GITLAB_API_VERSION')
    project_id = Configuracao.get_valor_por_chave('demandas', 'gitlab_suap_id', 'GITLAB_API_VERSION')
    return f'{gitlab_url}/api/v{api_version}/projects/{project_id}'


def headers():
    return {'PRIVATE-TOKEN': access_token()}


def list_branche_names(name=None):
    names = []
    url = f'{base_url()}/repository/branches?per_page=100'
    if name:
        url = f'{url}&search={name}'
    for branch in requests.get(
        url,
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json():
        names.append(branch['name'])
    return names


def create_pipeline(variables, branch='master'):
    requests.get(
        base_url(),
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    data = {'variables': variables}
    url = f'{base_url()}/pipeline?ref={branch}'
    response = requests.post(
        url,
        headers=headers(),
        json=data,
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    return response


def get_job(pipeline_id: int, job_name: str) -> dict | None:
    url = f'{base_url()}/pipelines/{pipeline_id}/jobs?per_page=100'
    try:
        jobs = requests.get(
            url,
            headers=headers(),
            timeout=settings.REQUESTS_TIMEOUT,
        ).json()
        for job in jobs:
            if 'name' in job and job['name'] == job_name:
                return job
    except RequestException:
        pass
    return None


def get_job_id(pipeline_id, job_name):
    job = get_job(pipeline_id, job_name)
    return job['id'] if job else None


def _aguardar_job_executavel(pipeline_id: int, job_name: str) -> tuple[dict, str]:
    """Espera o job ficar pronto para ``play`` (manual) ou ``retry`` (já executado)."""
    status = None
    for _ in range(TENTATIVAS_JOB):
        job = get_job(pipeline_id, job_name)
        status = job.get('status') if job else None
        if status == JOB_STATUS_EXECUTAVEL:
            return job, 'play'
        if status in JOB_STATUS_REEXECUTAVEIS:
            return job, 'retry'
        time.sleep(INTERVALO_JOB)
    raise GitlabJobError(f'O job {job_name} do pipeline {pipeline_id} não ficou pronto para execução (status: {status}).')


def execute_job(pipeline_id: int, job_name: str) -> dict:
    """Dispara (``play``) ou reexecuta (``retry``) o job e só retorna se o GitLab aceitar.

    Raises:
        GitlabJobError: o job não ficou executável a tempo ou o GitLab recusou o disparo.
    """
    job, acao = _aguardar_job_executavel(pipeline_id, job_name)
    response = requests.post(
        f'{base_url()}/jobs/{job["id"]}/{acao}',
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    )
    if not response.ok:
        raise GitlabJobError(f'O GitLab recusou o {acao} do job {job_name} do pipeline {pipeline_id}: {response.status_code} {response.text[:200]}')
    return response.json()


def job_log(pileline_id, name):
    job_id = get_job_id(pileline_id, name)
    url = f'{base_url()}/jobs/{job_id}/trace'
    response = requests.get(
        url,
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).text
    return response


def create_branch(name):
    url = f'{base_url()}/repository/branches?branch={name}&ref=master'
    response = requests.post(
        url,
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()
    message = response.get(
        'message',
    )
    return message != 'Branch already exists'


def get_merge_request(project_id: int, mr_iid: int) -> dict:
    """Retorna os dados de um MR (inclui ``state``: opened/closed/merged/locked).

    Não reutiliza ``base_url()`` porque aquele aponta para o projeto fixo do
    SUAP no config; aqui o ``project_id`` é arbitrário (vem do RIT).

    Args:
        project_id: ID numérico do projeto no GitLab.
        mr_iid: IID do MR dentro do projeto.

    Returns:
        Dicionário JSON do MR.
    """
    gitlab_url = Configuracao.get_valor_por_chave('demandas', 'gitlab_url', 'GITLAB_URL')
    api_version = Configuracao.get_valor_por_chave('demandas', 'gitlab_api_version', 'GITLAB_API_VERSION')
    url = f'{gitlab_url}/api/v{api_version}/projects/{project_id}/merge_requests/{mr_iid}'
    return requests.get(
        url,
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).json()


def delete_branch(name):
    url = f'{base_url()}/repository/branches/{name}'
    response = requests.delete(
        url,
        headers=headers(),
        timeout=settings.REQUESTS_TIMEOUT,
    ).text
    return 'Branch not Found' not in response
