from django.urls import path

from ferias import views

urlpatterns = [
    path('<int:ano>/<int:servidor_matricula>/', views.ver_ferias_servidor),
    path('ver_ferias/<int:ano>/<int:servidor_matricula>/', views.ver_ferias),
    path('ferias/', views.redirect_ferias_por_uo),
    path('calendario_ferias_setor/', views.calendario_ferias_setor),
]
