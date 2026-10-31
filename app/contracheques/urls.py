from django.urls import path


from . import views

urlpatterns = [
    path('relatorio_dgp/', views.relatorio_dgp),
    path('rubrica_por_campus/', views.rubrica_por_campus),
    path('rubrica_por_campus_agrupados/', views.rubrica_por_campus_agrupados),
    path('rubrica_por_campus_agrupados_detalhado/', views.rubrica_por_campus_agrupados_detalhado),
    path('bruto_liquido_por_campus/', views.bruto_liquido_por_campus),
    path('rubrica_por_campus_detalhado/', views.rubrica_por_campus_detalhado),
    path('bruto_liquido_por_campus_detalhado/', views.bruto_liquido_por_campus_detalhado),
    path('titulacao_por_contra_cheque/', views.titulacao_por_contra_cheque),
    path('servidores_com_titulacao_dispar/', views.servidores_com_titulacao_dispar),
    path('verificar_contra_cheque/<int:servidor_pk>/', views.verificar_contra_cheque),
    path('contra_cheque/<int:id>/', views.detalhar_contra_cheque),
    path('verificar_bruto/', views.verificar_bruto),
    path('consignataria_csv/', views.consignataria_csv),
    # services
    # path('api/contracheques/', services.contracheques),
    # Relatorios
    path('relatorio_absenteismo/', views.relatorio_absenteismo),
    path('relatorio_cargos_por_faixa_etaria/', views.relatorio_cargos_por_faixa_etaria),
    path('ingressos_egressos_por_cargos_uj/', views.ingressos_egressos_por_cargos_uj),
    path('distribuicao_lotacao_por_area/', views.distribuicao_lotacao_por_area),
    path('ingressos_egressos_por_cargos_funcoes_uj/', views.ingressos_egressos_por_cargos_funcoes_uj),
    # Importar do arquivo
    path('contracheque_importar_do_arquivo/', views.contracheque_importar_do_arquivo, name='contracheque_importar_do_arquivo'),
]
