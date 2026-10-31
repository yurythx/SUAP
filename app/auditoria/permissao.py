from djtools.db import models
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from comum.models import Vinculo
from .models import PermissaoDeChefe, AcaoPermissao


def get_content_type(klass: type[models.Model] | models.Model) -> ContentType:
    if hasattr(klass, '_meta'):
        return ContentType.objects.get_for_model(klass, for_concrete_model=False)
    return ContentType.objects.get_for_model(klass.__class__, for_concrete_model=False)


def tem_permissao(vinculo: Vinculo, acao: AcaoPermissao, klass: type[models.Model]) -> bool:
    content_type = get_content_type(klass)
    base = PermissaoDeChefe.objects.filter(vinculo_permitido=vinculo, content_type=content_type, revogado_em__isnull=True)
    qs = base.filter(acao=acao)
    # Se a ação for básica, permitir também quem tem GERENCIAR
    if acao in (AcaoPermissao.ADICIONAR, AcaoPermissao.ALTERAR, AcaoPermissao.EXCLUIR):
        return qs.exists() or base.filter(acao=AcaoPermissao.GERENCIAR).exists()
    return qs.exists()


def exige_permissao(vinculo: Vinculo, acao: AcaoPermissao, klass: type[models.Model] | models.Model):
    if not tem_permissao(vinculo, acao, klass):
        raise PermissionDenied('Você não possui permissão para esta ação neste escopo.')
