from django.urls import path

from temp_rh3 import views

urlpatterns = [
    path('responder_questionario/<int:pk>/', views.responder_questionario),
    path('resultado_questionario/', views.resultado_questionario),
    path('detalhar_resposta_questionario/<int:resposta_pk>/', views.detalhar_resposta_questionario, name='detalhar_resposta_questionario'),
]
