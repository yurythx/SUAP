from django.urls import path
from ninja_extra import NinjaExtraAPI

from dados_abertos.endpoints.ae import router as ae_router
from dados_abertos.endpoints.cnpq import router as cnpq_router
from dados_abertos.endpoints.contrato import router as contrato_router
from dados_abertos.endpoints.engenharia import router as engenharia_router
from dados_abertos.endpoints.ensino import router as ensino_router
from dados_abertos.endpoints.extensao import router as extensao_router
from dados_abertos.endpoints.patrimonio import router as patrimonio_router
from dados_abertos.endpoints.pesquisa import router as pesquisa_router
from dados_abertos.endpoints.processo import router as processo_router
from dados_abertos.endpoints.rh import router as rh_router

from . import views

app_name = 'dados_abertos'


api = NinjaExtraAPI(
    title='Dados Abertos API',
    version='1.0.0',
    docs_url='/docs/',
    description='API para acesso a dados abertos do sistema SUAP.',
    urls_namespace=f'{app_name}:api',
)
api.add_router('ae/', ae_router)
api.add_router('contrato/', contrato_router)
api.add_router('cnpq/', cnpq_router)
api.add_router('engenharia/', engenharia_router)
api.add_router('ensino/', ensino_router)
api.add_router('extensao/', extensao_router)
api.add_router('patrimonio/', patrimonio_router)
api.add_router('pesquisa/', pesquisa_router)
api.add_router('processo/', processo_router)
api.add_router('rh/', rh_router)


urlpatterns = [
    # base da API desse app
    path('api/', api.urls),
    path('<int:pda_id>/dashboard/', views.dashboard, name='dashboard'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path(
        '<int:pda_id>/dashboard/ckan/<int:rel_id>/sincronizar/',
        views.sincronizar_base_ckan,
        name='sincronizar_base_ckan',
    ),
    path(
        '<int:pda_id>/base/<int:rel_id>/reenviar_lai/',
        views.reenviar_lai,
        name='reenviar_lai',
    ),
    path(
        '<int:pda_id>/acao/<int:acao_id>/toggle/',
        views.toggle_acao_pda,
        name='toggle_acao_pda',
    ),
    path(
        '<int:pda_id>/etapa/<int:etapa_id>/pular/',
        views.pular_etapa,
        name='pular_etapa',
    ),
    path(
        '<int:pda_id>/etapa/<int:etapa_id>/reativar/',
        views.reativar_etapa,
        name='reativar_etapa',
    ),
    # visualização da base de dados e do recurso (get_absolute_url)
    path('base_dados/<int:pk>/', views.base_dados_detalhe, name='base_dados_detalhe'),
    path('recurso/<int:pk>/', views.recurso_dados_detalhe, name='recurso_dados_detalhe'),
    # detalhes dos PDAs
    path('pda/<int:pk>/detalhe/', views.pda_detalhe, name='pda_detalhe'),
    # matriz de priorização
    path('matriz_priorizacao/', views.matriz_priorizacao, name='matriz_priorizacao'),
    # deliberação do Responsável LAI
    path('deliberacao_lai/', views.deliberacao_lai, name='deliberacao_lai'),
    # versionamento do PDA
    path('pda/<int:pda_id>/criar_versao/', views.criar_versao_pda, name='criar_versao_pda'),
    path('pda/<int:pda_id>/gerar_documento/', views.gerar_documento_versao_pda, name='gerar_documento_versao_pda'),
    # área pública (sem autenticação)
    path('publico/', views.area_publica_pda, name='area_publica_pda'),
    path('pda/documento/', views.documento_publico_pda, name='documento_publico_pda'),
    path('pda/<int:pda_id>/documento/', views.documento_publico_pda, name='documento_publico_pda_especifico'),
]
