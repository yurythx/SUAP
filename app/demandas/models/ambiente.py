from datetime import datetime

from requests.exceptions import RequestException

from comum.models import Configuracao
from djtools.db import models
from djtools.db.models import ModelPlus
from djtools.utils import gitlab

# Job manual ou recém-criado ainda não tem log de onde tirar a etapa.
JOB_STATUS_COM_LOG = ('running', 'success', 'failed', 'canceled')


class AmbienteHomologacao(ModelPlus):
    criador = models.ForeignKeyPlus('demandas.AnalistaDesenvolvedor', verbose_name='Responsável', on_delete=models.CASCADE)
    branch = models.CharFieldPlus(verbose_name='Branch', default='master')
    banco = models.CharFieldPlus(verbose_name='Banco de Dados', default='suap_mascarado_pequeno')
    data_criacao = models.DateFieldPlus(verbose_name='Data de Criação')
    data_expiracao = models.DateFieldPlus(verbose_name='Data de Expiração')
    senha = models.CharFieldPlus(verbose_name='Senha', null=True, blank=False)
    pipeline = models.PositiveIntegerFieldPlus(verbose_name='Pipeline')
    url_gitlab = models.CharFieldPlus(verbose_name='Pipeline')
    ativo = models.BooleanField(verbose_name='Ativo', default=False)

    class Meta:
        verbose_name = 'Ambiente de Homologação'
        verbose_name_plural = 'Ambientes de Homologação'

    def __str__(self):
        return f'{self.branch} [{self.pipeline}]'

    def get_absolute_url(self):
        return f'/demandas/ambientehomologacao/{self.pk}/'

    def save(self, *args, **kwargs):
        if self.pipeline is None:
            self.data_criacao = datetime.today()
            pipeline = ''
            try:
                pipeline = self.criar_pipeline()
                self.pipeline = pipeline['id']
                self.url_gitlab = pipeline['web_url']
            except KeyError:
                raise Exception(f'Não foi possível criar pipeline, por favor atualize a branch. Mensagem do pipeline: {pipeline}')
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        # `destruir`, não `excluir_container`: o undeploy só para o container e deixaria o banco
        # `database-<branch>-suap` sem nenhum registro que aponte para ele.
        if self.senha:
            self.destruir()
        super().delete(*args, **kwargs)

    def criar_pipeline(self):
        variables = [
            {'key': 'CI_COMMIT_BRANCH', 'variable_type': 'env_var', 'value': self.branch},
            {'key': 'CI_COMMIT_AUTHOR', 'variable_type': 'env_var', 'value': self.criador.username_gitlab},
            {'key': 'DATABASE_TEMPLATE', 'variable_type': 'env_var', 'value': self.banco},
            {'key': 'NAME', 'variable_type': 'env_var', 'value': self.branch},
            {'key': 'PASSWORD', 'variable_type': 'env_var', 'value': self.senha},
        ]
        return gitlab.create_pipeline(variables, self.branch)

    def atualizar_pipeline(self):
        pipeline = self.pipeline or ''
        try:
            # Criando branch apenas para criar o pipeline
            created = gitlab.create_branch(self.branch)
            pipeline = self.criar_pipeline()
            self.pipeline = pipeline['id']
            self.url_gitlab = pipeline['web_url']
            # excluindo branch caso tenha sido criada acima
            if created:
                gitlab.delete_branch(self.branch)
        except KeyError:
            raise Exception(f'Não foi possível criar pipeline, por favor atualize a branch. Mensagem do pipeline: {pipeline}')
        self.save()

    def criar_atualizar_container(self):
        gitlab.execute_job(self.pipeline, 'deploy-suapdev')
        self.ativo = True
        self.save()

    def excluir_container(self) -> None:
        self.atualizar_pipeline()
        gitlab.execute_job(self.pipeline, 'undeploy-suapdev')
        self.ativo = False
        self.save()

    def destruir(self) -> None:
        """Dispara o job que remove container e banco; só marca inativo se o GitLab aceitar.

        ``execute_job`` levanta ``GitlabJobError`` quando o disparo falha, e o ambiente continua
        ativo para a próxima execução de ``remover_ambientes_homolog_expirados``.
        """
        self.atualizar_pipeline()
        gitlab.execute_job(self.pipeline, 'destroy-suapdev')
        self.ativo = False
        self.save()

    def destroy_pendente(self) -> bool:
        """Indica se o banco pode ter ficado para trás: o destroy do pipeline atual não rodou.

        ``excluir_container`` e ``destruir`` sempre geram um pipeline novo, então o pipeline
        atual é o da última ação. Um destroy ``manual`` ali é um undeploy ou um destroy que
        não chegou a ser disparado; ``failed`` é um destroy que rodou e quebrou.
        """
        job = gitlab.get_job(self.pipeline, 'destroy-suapdev')
        return bool(job) and job.get('status') in ('manual', 'failed')

    def get_deploy_job_url(self):
        return gitlab.get_job(self.pipeline, 'deploy-suapdev')['web_url']

    def get_situacao_deploy(self) -> dict | None:
        """Estado do job ``deploy-suapdev`` no GitLab; ``None`` se o job não existe ou o GitLab não respondeu.

        ``etapa``/``progresso`` vêm do log (``get_status_container``) e só existem depois que o job rodou.
        """
        job = gitlab.get_job(self.pipeline, 'deploy-suapdev')
        if not job:
            return None
        situacao = {'status': job.get('status'), 'job_url': job.get('web_url'), 'progresso': None, 'etapa': None}
        if situacao['status'] in JOB_STATUS_COM_LOG:
            try:
                situacao['progresso'], situacao['etapa'] = self.get_status_container()
            except RequestException:
                pass
        return situacao

    def executar_comando(self, comando):
        return gitlab.job_log(self.pipeline, 'deploy-suapdev')

    def get_status_container(self):
        log = gitlab.job_log(self.pipeline, 'deploy-suapdev')
        status = 0, 'Aguardando criação'
        if 'SENHA:' in log:
            status = 100, 'Processo concluído com sucesso.'
        elif 'python manage.py sync' in log:
            status = 75, 'Executando o comando sync.'
        elif 'git pull origin' in log:
            status = 50, 'Sincronizando repositório.'
        elif 'createdb -U postgres' in log:
            status = 20, 'Criando banco de dados.'
        elif 'docker run' in log:
            status = 5, 'Criando container.'
        elif 'Job succeeded' in log:
            status = -1, 'Processo concluído com falha.'
        elif 'Job failed' in log:
            status = -1, 'Erro na execução do processo'
        return status

    def get_url_homologacao(self):
        dominio_suapdevs = Configuracao.get_valor_por_chave('demandas', 'dominio_suapdevs')
        return f'https://{self.branch}.{dominio_suapdevs}'
