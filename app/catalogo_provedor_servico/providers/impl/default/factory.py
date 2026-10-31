from catalogo_provedor_servico.providers.base import AbstractBaseServiceProviderFactory
from comum.models import Configuracao

from .emissao_segunda_via_diploma import EmissaoSegundaViaDiplomaServiceProvider
from .matricula_ead import MatriculaEadServiceProvider
from .matricula_fic import MatriculaFicServiceProvider
from .matricula_pos_graduacao import MatriculaPosGraduacaoServiceProvider
from .matricula_superior import MatriculaSuperiorServiceProvider
from .matricula_tecnico import MatriculaTecnicoServiceProvider
from .protocolar_documento import ProtocolarDocumentoServiceProvider
from .solicitar_cerfificado_encceja import SolicitarCertificadoEnccejaServiceProvider
from .certificacao_enem import SolicitarCertificadoEnemServiceProvider
from .solicitar_visita import SolicitarVisitaServiceProvider


class ServiceProviderFactory(AbstractBaseServiceProviderFactory):
    def get_service_provider(self, id_servico_portal_govbr):
        if id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_ead') or 0):
            return MatriculaEadServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_fic') or 0):
            return MatriculaFicServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_certificado_encceja') or 0):
            return SolicitarCertificadoEnccejaServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_protocolar_documento') or 0):
            return ProtocolarDocumentoServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_segunda_via_diploma') or 0):
            return EmissaoSegundaViaDiplomaServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_superior') or 0):
            return MatriculaSuperiorServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_tecnico') or 0):
            return MatriculaTecnicoServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_matricula_pos_graduacao') or 0):
            return MatriculaPosGraduacaoServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_solicitacao_visita') or 0):
            return SolicitarVisitaServiceProvider()
        elif id_servico_portal_govbr == int(Configuracao.get_valor_por_chave('catalogo_provedor_servico', 'codigo_certificacao_enem') or 0):
            return SolicitarCertificadoEnemServiceProvider()
        return None
