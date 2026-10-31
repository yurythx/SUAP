from django.urls import path

from microsoft import views

urlpatterns = [
    path('redirecionar_aluno/<str:servico>/', views.redirecionar_aluno),
    path('redirecionar_servidor/<str:servico>/', views.redirecionar_servidor),
]
