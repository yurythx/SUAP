"""Admin do app rsc_tae.

Este pacote é importado pelo autodiscover do Django via `rsc_tae.admin`.
Os módulos abaixo fazem o registro dos ModelAdmins.
"""

from .alteracao_nivel import AlteracaoNivelRSCTaeAdmin
from .avaliacao_anexo import AvaliacaoAnexoRSCTaeAdmin
from .banco_pontos import BancoPontosRSCTaeAdmin, MovimentoBancoPontosRSCTaeAdmin
from .avaliacao_processo import AvaliacaoProcessoRSCTaeAdmin
from .avaliador_auxiliar import AvaliadorAuxiliarRSCTaeAdmin
from .comissao import CategoriaMembroComissaoRSCTaeAdmin, ComissaoRSCTaeAdmin
from .deliberacao_crsc import DeliberacaoCRSCRSCTaeAdmin
from .grupo import GrupoSaberCompetenciaAdmin
from .processo import ProcessoRSCTaeAdmin
from .nivel import NivelAdmin
from .requisito import RequisitoAdmin
from .rol_saber_competencia import RolSaberCompetenciaAdmin
from .preenchimento import RolSaberCompetenciaPreenchimentoAdmin
from .anexo import RolSaberCompetenciaAnexoAdmin
from .documento_preliminar import DocumentoPreliminarRSCTaeAdmin, AvaliacaoDocumentoPreliminarRSCTaeAdmin, DocumentoPreliminarRSCTaeLogAdmin
from .apontamento_correcao import ApontamentoCorrecaoRSCTaeAdmin
from .voto_deliberacao_final import VotoDeliberacaoFinalRSCTaeAdmin
from .configuracao_rsc_tae import ConfiguracaoRSCTaeAdmin
from .sorteio import SorteioAvaliadorRSCTaeAdmin

__all__ = [
    'AlteracaoNivelRSCTaeAdmin',
    'ApontamentoCorrecaoRSCTaeAdmin',
    'AvaliacaoAnexoRSCTaeAdmin',
    'AvaliacaoDocumentoPreliminarRSCTaeAdmin',
    'AvaliacaoProcessoRSCTaeAdmin',
    'AvaliadorAuxiliarRSCTaeAdmin',
    'BancoPontosRSCTaeAdmin',
    'CategoriaMembroComissaoRSCTaeAdmin',
    'ComissaoRSCTaeAdmin',
    'ConfiguracaoRSCTaeAdmin',
    'DeliberacaoCRSCRSCTaeAdmin',
    'DocumentoPreliminarRSCTaeAdmin',
    'DocumentoPreliminarRSCTaeLogAdmin',
    'GrupoSaberCompetenciaAdmin',
    'MovimentoBancoPontosRSCTaeAdmin',
    'NivelAdmin',
    'ProcessoRSCTaeAdmin',
    'RequisitoAdmin',
    'RolSaberCompetenciaAdmin',
    'RolSaberCompetenciaAnexoAdmin',
    'RolSaberCompetenciaPreenchimentoAdmin',
    'SorteioAvaliadorRSCTaeAdmin',
    'VotoDeliberacaoFinalRSCTaeAdmin',
]
