from django.urls import path

from cron import views

urlpatterns = [
    path('atualizar_comandos/', views.atualizar_comandos, name='atualizar_comandos'),
    path('executar_comando/<int:object_id>/', views.executar_comando, name='executar_comando'),
    path('interromper_comando/<int:object_id>/', views.interromper_comando, name='interromper_comando'),
    path('visualizar_execucao/<int:object_id>/', views.visualizar_execucao, name='visualizar_execucao'),
]
