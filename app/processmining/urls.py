from django.urls import path

from processmining import views

urlpatterns = [
    path('processmining/<str:tipo>/<int:pk>/', views.processmining),
]
