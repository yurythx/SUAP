from django.urls import path

from enquete import views

urlpatterns = [
    path('enquete/<int:id>/', views.enquete),
    path('adicionar_opcao/<int:enquete_id>/', views.adicionar_opcao),
    path('adicionar_opcao/<int:enquete_id>/<int:pergunta_id>/', views.adicionar_opcao),
    path('editar_opcao/<int:id>/', views.editar_opcao),
    path('remover_opcao/<int:id>/', views.remover_opcao),
    path('adicionar_pergunta/<int:enquete_id>/<int:categoria_id>/', views.adicionar_pergunta),
    path('editar_pergunta/<int:id>/', views.editar_pergunta),
    path('remover_pergunta/<int:id>/', views.remover_pergunta),
    path('responder_enquete/<int:id>/', views.responder_enquete, name='responder_enquete'),
    path('ver_respostas/<int:id>/', views.ver_respostas, name='ver_respostas'),
    path('ver_respostas_responsavel/<int:id>/<int:vinculo_id>/', views.ver_respostas_responsavel, name='ver_respostas_responsavel'),
    path('publicar_enquete/<int:id>/', views.publicar_enquete, name='publicar_enquete'),
    path('despublicar_enquete/<int:id>/', views.despublicar_enquete, name='despublicar_enquete'),
    path('ver_resultados/<int:id>/', views.ver_resultados, name='ver_resultados'),
    path('ver_publico/<int:enquete_id>/', views.ver_publico, name='ver_publico'),
    path('atualizar_publico/<int:enquete_id>/', views.atualizar_publico, name='atualizar_publico_enquete'),
    path('notificar_nao_respondentes/<int:enquete_id>/', views.notificar_nao_respondentes, name='notificar_nao_respondentes'),
]
