from django.urls import path, register_converter

from djtools import converters, views

register_converter(converters.DateDMYConverter, 'date-dmy')

urlpatterns = [
    path('manifest/', views.manifest),
    path('push_web_notification_subscription/', views.push_web_notification_subscription),
    path('give_permission/', views.give_permission),
    path('delete_object/<str:app>/<str:model>/<int:pk>/', views.delete_object),
    path('breadcrumbs_reset/<str:menu_item_id>/<path:url>', views.breadcrumbs_reset),
    path('notificar_grupo/<int:pk_grupo>/', views.notificar_grupo),
    path('help_view/<str:app>/<str:view>/', views.help_view),
    path('popup_choice_field/<str:name>/', views.popup_choice_field),
    path('popup_choice_field/<str:name>/<str:ids>/', views.popup_choice_field),
    path('user_info/<uuid:user_uuid>/', views.user_info),
    path('profile_info/<uuid:profile_uuid>/', views.profile_info),
    path('view_email/', views.view_email),
    path('process/<uuid:uuid_task>/', views.process),
    path('process_progress/<int:download>/<uuid:uuid_task>/', views.process_progress),
    path('view_task/<int:pk>/', views.view_task),
    path('consultar_cep/<str:cep>/', views.consultar_cep),
    path('consulta_cep_govbr/<str:cep>/', views.consulta_cep_govbr),
    path('two_factor_authentication/', views.two_factor_authentication),
    path('private_media/', views.private_media),
    path('send_token/<str:method>/', views.send_token),
    path('arquivo/<str:app>/<str:model>/<int:pk>/<str:attr_name>/', views.arquivo),
    path('arquivo/<str:app>/<str:model>/<uuid:uuid>/<str:attr_name>/', views.arquivo_uuid),
    path('arquivo/<str:app>/<str:model>/<uuid:uuid>/<str:attr_name>/<str:size>/', views.arquivo_uuid),
    path('restaurar_arquivos_media/', views.restaurar_arquivos_media),
    path('history/', views.history),
    path('log_history/<str:pk>/', views.log_history),
    path('access_logs/', views.access_logs),
    path('log_access/<str:pk>/', views.log_access),
    path('email_logs/', views.email_logs),
    path('autocomplete_full_diagnostics/', views.autocomplete_full_diagnostics),
]
