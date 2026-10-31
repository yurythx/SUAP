from djtools import layout


@layout.servicos_anonimos()
def servicos_anonimos(request):
    servicos_anonimos = [
        {'categoria': 'Auditoria', 'url': '/auditoria/relatorios/estoque/monitoramentos/', 'icone': 'file', 'titulo': 'Estoque de Monitoramentos'},
        {'categoria': 'Auditoria', 'url': '/auditoria/relatorios/estoque/recomendacoes/', 'icone': 'file', 'titulo': 'Estoque de Recomendações'},
    ]
    return servicos_anonimos
