# -------------------------------------------------------------------------------
# IFRN - Instituto Federal de Educação, Ciência e Tecnologia
# DGTI - Diretoria de Gestão da Tecnologia da Informação
# -------------------------------------------------------------------------------
# SUAP - Sistema único de Administração Pública
# -------------------------------------------------------------------------------
# Aplicativo: Orçamento
# Autor.....: José Augusto de Medeiros
# Descrição.: Aplicativo para controle do orçamento do instituto.
# -------------------------------------------------------------------------------
# Observações:
#      Termos utilizados no módulo:
#         - MTO: Manual Técnico do Orçamento
# -------------------------------------------------------------------------------

# -------------------------------------------------------------------------------
from django.urls import path

from orcamento import views

# -------------------------------------------------------------------------------

urlpatterns = [
    path('execucaoorcamentaria/', views.execucao_orcamentaria),
    path('execucaoorcamentaria/ug/exec/<int:id_ug>/', views.execucao_orcamentaria_ug_exec),
    path('execucaoorcamentaria/ug/cont/<int:id_ug>/', views.execucao_orcamentaria_ug_cont),
    path('execucaoorcamentaria/ug/<int:id_ug>/ugr/<int:id_ugr>/', views.execucao_orcamentaria_ugr),
    path('execucaoorcamentaria/ug/<int:id_ug>/naturezadespesa/<int:cod_nt>/', views.execucao_orcamentaria_nt),
    path('execucaoorcamentaria/ug/<int:id_ug>/ugr/<int:id_ugr>/naturezadespesa/<int:cod_nt>/', views.execucao_orcamentaria_ugr_nt),
    path('notacredito/consulta/', views.nota_credito_consulta),
    path('notacredito/ug/<int:id_ug>/', views.notas_credito),
    path('notacredito/uge/<int:id_uge>/ugf/<int:id_ugf>/', views.notas_credito_emitente_favorecido),
    path('notacredito/<int:id_nc>/item/', views.itens_nota_credito),
    path('notadotacao/consulta/', views.nota_dotacao_consulta),
    path('notadotacao/<int:id_nd>/item/', views.itens_nota_dotacao),
    path('notacreditodotacao/ug/<int:id_ug>/ugr/<int:id_ugr>/', views.notas_credito_dotacao_ugr),
    path('notaempenho/consulta/', views.nota_empenho_consulta),
    path('notaempenho/<int:id_ne>/', views.itens_nota_empenho),
    path('eventosdesatualizados/', views.eventos_desatualizados),
    path('eventosutilizados/', views.eventos_utilizados),
    path('historicoimportacao/', views.historico_importacao),
]
# -------------------------------------------------------------------------------
# EOF - urls.py
# -------------------------------------------------------------------------------
