from documento_eletronico.status import DocumentoStatus


def get_modelo_ordem_servico():
    from comum.models import Configuracao
    from documento_eletronico.models import ModeloDocumento

    pk = Configuracao.get_valor_por_chave('auditoria', 'modelo_ordem_servico')
    return ModeloDocumento.objects.filter(pk=pk).first()


def get_modelo_resolucao_consup():
    from comum.models import Configuracao
    from documento_eletronico.models import ModeloDocumento

    pk = Configuracao.get_valor_por_chave('auditoria', 'modelo_resolucao_consup')
    return ModeloDocumento.objects.filter(pk=pk).first()


def get_resolucoes_consup():
    from documento_eletronico.models import DocumentoTexto

    modelo_resolucao = get_modelo_resolucao_consup()
    qs = DocumentoTexto.objects.filter(modelo=modelo_resolucao)
    return qs.filter(status=DocumentoStatus.STATUS_FINALIZADO)


def get_tipo_relatorio_auditoria():
    from comum.models import Configuracao
    from documento_eletronico.models import TipoDocumento

    pk = Configuracao.get_valor_por_chave('auditoria', 'tipo_relatorio_auditoria')
    return TipoDocumento.objects.filter(pk=pk).first()
