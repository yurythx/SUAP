from django.urls import path

from solenidades import views

urlpatterns = [
    path('cancelar_agendamento/<int:pk>/', views.cancelar_agendamento, name='cancelar_agendamento'),
    path('editar_agendamento/<int:pk>/', views.editar_agendamento, name='editar_agendamento'),
    path('deferir_agendamento/<int:pk>/', views.deferir_agendamento, name='deferir_agendamento'),
    path('indeferir_agendamento/<int:pk>/', views.indeferir_agendamento, name='indeferir_agendamento'),
    path('ver_agendamento/<int:pk>/', views.ver_agendamento, name='ver_agendamento'),
]
