import datetime
import logging

from django.core.files.storage import default_storage
from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch.dispatcher import receiver
from django.apps.registry import apps
from django.core.cache import cache
from comum.utils import tl

ServidorAfastamento = apps.get_model('rh', 'ServidorAfastamento')
AlertaGestaoPessoa = apps.get_model('rh', 'AlertaGestaoPessoa')
ServidorFuncaoHistorico = apps.get_model('rh', 'ServidorFuncaoHistorico')
JornadaTrabalhoPCA = apps.get_model('rh', 'JornadaTrabalhoPCA')
DocumentacaoExigida = apps.get_model('rh', 'DocumentacaoExigida')

logger = logging.getLogger(__name__)


def _apagar_do_storage(diretorio: str) -> None:
    try:
        default_storage.delete(diretorio)
    except Exception:
        # O arquivo órfão não pode desfazer a exclusão do registro (o storage pode ser S3 fora do ar).
        logger.exception('Não foi possível apagar o arquivo %r do storage.', diretorio)


@receiver(post_delete, sender=DocumentacaoExigida)
def documentacao_exigida_post_delete(sender, instance, **kwargs) -> None:
    """Apaga do storage o arquivo do documento, qualquer que seja o caminho da exclusão (view, admin, cascade).

    ``diretorio`` é um ``CharField``, não um ``FileField``: o Django não remove o arquivo sozinho. A remoção roda no
    ``on_commit`` para que um rollback não deixe a linha sem o arquivo.
    """
    if instance.diretorio:
        transaction.on_commit(lambda: _apagar_do_storage(instance.diretorio))


@receiver(post_save, sender=ServidorAfastamento)
def servidor_afastamento_post_save(sender, instance, **kwargs):
    vinculo_usuario = tl.get_vinculo()
    request = tl.get_request()
    if request and instance.servidor.get_vinculo() == vinculo_usuario:
        url = request.META.get('PATH_INFO')
        if 'importar_servidor' not in url and 'atualizar_meus_dados_servidor' not in url:
            alerta = AlertaGestaoPessoa()
            alerta.tipo_acao = AlertaGestaoPessoa.ACAO_AFASTAMENTO_SIAPE
            alerta.vinculo_analizar = vinculo_usuario
            alerta.data_acao = datetime.datetime.now()
            alerta.registro_afetado = request.META.get('PATH_INFO')
            alerta.objeto = instance
            alerta.save()


@receiver(post_save, sender=ServidorFuncaoHistorico)
def servidor_funcao_historico_post_save(sender, instance, **kwargs):
    if instance.servidor:
        hoje = datetime.date.today()
        chave = f'servidor_{instance.servidor.pk}_setores_que_eh_chefe_{hoje.strftime("%d/%m/%Y")}'
        # Always attempt to delete the cache key. Previously we only deleted
        # when `cache.get(chave)` was truthy; that skipped deletion when the
        # cached value was a falsy object (e.g. an empty QuerySet) and left a
        # stale key present. Deleting unconditionally is safe and ensures the
        # cache is invalidated on updates.
        try:
            cache.delete(chave)
        except Exception:
            # Ignore cache backend errors here; this is a best-effort cleanup.
            pass
        vinculo_usuario = tl.get_vinculo()
        request = tl.get_request()
        if request and instance.servidor.get_vinculo() == vinculo_usuario:
            url = request.META.get('PATH_INFO')
            if 'importar_servidor' not in url and 'atualizar_meus_dados_servidor' not in url:
                alerta = AlertaGestaoPessoa()
                alerta.tipo_acao = AlertaGestaoPessoa.ACAO_HISTORICO_FUNCAO
                alerta.vinculo_analizar = vinculo_usuario
                alerta.data_acao = datetime.datetime.now()
                alerta.registro_afetado = url if request else ''
                alerta.objeto = instance
                alerta.save()


@receiver(post_save, sender=JornadaTrabalhoPCA)
def jornada_trabalho_pca_post_save(sender, instance, **kwargs):
    if instance.pca.servidor:
        vinculo_usuario = tl.get_vinculo()
        request = tl.get_request()
        if request and instance.pca.servidor.get_vinculo() == vinculo_usuario:
            alerta = AlertaGestaoPessoa()
            alerta.tipo_acao = AlertaGestaoPessoa.ACAO_JORNADA_TRABALHO_PCA
            alerta.vinculo_analizar = vinculo_usuario
            alerta.data_acao = datetime.datetime.now()
            alerta.registro_afetado = request.META.get('PATH_INFO')
            alerta.objeto = instance
            alerta.save()
