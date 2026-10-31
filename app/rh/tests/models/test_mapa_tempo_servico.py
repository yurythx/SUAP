from datetime import timedelta

import pytest
from rh.importador import ImportadorSIAPE
from rh.models import PCA
from rh.tests.test_base import RHBase


class MapaTempoServicoTest(RHBase):
    @pytest.fixture(autouse=True)
    def _setup(self):
        self.itens_pca = self.mock_siape_pca()
        self.importador_siape = ImportadorSIAPE()

    def mock_siape_pca(self):
        self.servidor_a.matricula_sipe = '00000010'
        self.servidor_a.matricula_crh = '00000011'
        self.servidor_a.save()

        self.servidor_b.matricula_sipe = '00000020'
        self.servidor_b.matricula_crh = '00000021'
        self.servidor_b.save()

        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
        #         print Servidor.objects.all()
        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

        itens = [
            {
                'CH-PCA': '00000010999',  # matricula_sipe do servidor_a (removendo os 3 ultimos digitos)
                'CO-CRH-PCA': '00000011',  # matricula_crh do servidor_a
                'CH-CARGO-PCA': '01',  # codigo do cargo_emprego_a
                'CO-FORMA-ENTRADA-PCA': '009',
                'DA-ENTRADA-PCA': '20100104',
                'TX-ENTRADA-PCA(1)': '',
                'CO-FORMA-VACANCIA-PCA': '000',
                'DA-VACANCIA-PCA': '25001231',
                'TX-VACANCIA-PCA(1)': '',
                'IN-SITUACAO-VAGA-PCA': '0',
                'CO-VAGA-SIAPE-PCA': '8335484',
                'QT-JORNADA-TRABALHO-PCA(1)': '40',
                'QT-JORNADA-TRABALHO-PCA(2)': '00',
                'QT-JORNADA-TRABALHO-PCA(3)': '00',
                'QT-JORNADA-TRABALHO-PCA(4)': '00',
                'QT-JORNADA-TRABALHO-PCA(5)': '00',
                'QT-JORNADA-TRABALHO-PCA(6)': '00',
                'DA-INI-JORNADA-TRABALHO-PCA(1)': '20100104',
                'DA-INI-JORNADA-TRABALHO-PCA(2)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(3)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(4)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(5)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(6)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(1)': '25001231',
                'DA-FIM-JORNADA-TRABALHO-PCA(2)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(3)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(4)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(5)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(6)': '',
                'CO-REGIME-JURIDICO-PCA(1)': '02',
                'CO-REGIME-JURIDICO-PCA(2)': '00',
                'CO-REGIME-JURIDICO-PCA(3)': '00',
                'CO-REGIME-JURIDICO-PCA(4)': '00',
                'CO-REGIME-JURIDICO-PCA(5)': '00',
                'CO-REGIME-JURIDICO-PCA(6)': '00',
                'DA-INI-REGIME-JURIDICO-PCA(1)': '20100104',
                'DA-INI-REGIME-JURIDICO-PCA(2)': '',
                'DA-INI-REGIME-JURIDICO-PCA(3)': '',
                'DA-INI-REGIME-JURIDICO-PCA(4)': '',
                'DA-INI-REGIME-JURIDICO-PCA(5)': '',
                'DA-INI-REGIME-JURIDICO-PCA(6)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(1)': '25001231',
                'DA-FIM-REGIME-JURIDICO-PCA(2)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(3)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(4)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(5)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(6)': '',
                'CH-ULTIMA-UORG-LOTACAO': '',
                'VA-FATOR-TEMPO-REGIME-PCA(1)': '010000',
                'VA-FATOR-TEMPO-REGIME-PCA(2)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(3)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(4)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(5)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(6)': '000000',
            },
            {
                'CH-PCA': '00000020999',  # matricula_sipe do servidor_b (removendo os 3 ultimos digitos)
                'CO-CRH-PCA': '00000021',  # matricula_crh do servidor_b
                'CH-CARGO-PCA': '02',  # codigo do cargo_emprego_b
                'CO-FORMA-ENTRADA-PCA': '700',
                'DA-ENTRADA-PCA': '20100101',
                'TX-ENTRADA-PCA(1)': '',
                'CO-FORMA-VACANCIA-PCA': '043',
                'DA-VACANCIA-PCA': '20120509',
                'TX-VACANCIA-PCA(1)': '',
                'IN-SITUACAO-VAGA-PCA': '0',
                'CO-VAGA-SIAPE-PCA': '2137324',
                'QT-JORNADA-TRABALHO-PCA(1)': '40',
                'QT-JORNADA-TRABALHO-PCA(2)': '00',
                'QT-JORNADA-TRABALHO-PCA(3)': '00',
                'QT-JORNADA-TRABALHO-PCA(4)': '00',
                'QT-JORNADA-TRABALHO-PCA(5)': '00',
                'QT-JORNADA-TRABALHO-PCA(6)': '00',
                'DA-INI-JORNADA-TRABALHO-PCA(1)': '20100101',
                'DA-INI-JORNADA-TRABALHO-PCA(2)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(3)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(4)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(5)': '',
                'DA-INI-JORNADA-TRABALHO-PCA(6)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(1)': '20120509',
                'DA-FIM-JORNADA-TRABALHO-PCA(2)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(3)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(4)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(5)': '',
                'DA-FIM-JORNADA-TRABALHO-PCA(6)': '',
                'CO-REGIME-JURIDICO-PCA(1)': '02',
                'CO-REGIME-JURIDICO-PCA(2)': '00',
                'CO-REGIME-JURIDICO-PCA(3)': '00',
                'CO-REGIME-JURIDICO-PCA(4)': '00',
                'CO-REGIME-JURIDICO-PCA(5)': '00',
                'CO-REGIME-JURIDICO-PCA(6)': '00',
                'DA-INI-REGIME-JURIDICO-PCA(1)': '20100101',
                'DA-INI-REGIME-JURIDICO-PCA(2)': '',
                'DA-INI-REGIME-JURIDICO-PCA(3)': '',
                'DA-INI-REGIME-JURIDICO-PCA(4)': '',
                'DA-INI-REGIME-JURIDICO-PCA(5)': '',
                'DA-INI-REGIME-JURIDICO-PCA(6)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(1)': '20120509',
                'DA-FIM-REGIME-JURIDICO-PCA(2)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(3)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(4)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(5)': '',
                'DA-FIM-REGIME-JURIDICO-PCA(6)': '',
                'CH-ULTIMA-UORG-LOTACAO': '',
                'VA-FATOR-TEMPO-REGIME-PCA(1)': '010000',
                'VA-FATOR-TEMPO-REGIME-PCA(2)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(3)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(4)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(5)': '000000',
                'VA-FATOR-TEMPO-REGIME-PCA(6)': '000000',
            },
        ]
        return itens

    def test_importar_pca(self):
        self.importador_siape.importar_pca(self.itens_pca)  # 2 registros de PCA serão importados

        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
        #         print PCA.objects.all()
        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

        qtde_pcas_gravados = PCA.objects.all().count()
        assert qtde_pcas_gravados == 2  # deve ser igual a 2

    def test_tempo_servico(self):
        self.importador_siape.importar_pca(self.itens_pca)  # 2 registros de PCA serão importados

        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
        #         print PCA.objects.all()
        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
        pca_1 = PCA.objects.get(codigo_pca='00000010999')
        regime_pca_1 = pca_1.regimejuridicopca_set.all()[0]
        assert isinstance(regime_pca_1.tempo_servico(), timedelta)
        assert regime_pca_1.tempo_servico().days > -1  # Garante que o tempo de serviço retornará um numero não negativo de dias

        pca_2 = PCA.objects.get(codigo_pca='00000020999')
        regime_pca_2 = pca_2.regimejuridicopca_set.all()[0]
        assert isinstance(regime_pca_2.tempo_servico(), timedelta)
        assert regime_pca_2.tempo_servico().days > -1  # Garante que o tempo de serviço retornará um numero não negativo de dias

    def test_tempo_servico_pca_ficto(self):
        self.importador_siape.importar_pca(self.itens_pca)  # 2 registros de PCA serão importados

        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"
        #         print PCA.objects.all()
        #         print ">>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>"

        pca_1 = PCA.objects.get(codigo_pca='00000010999')
        assert isinstance(pca_1.tempo_servico_pca(ficto=True), timedelta)
        assert pca_1.tempo_servico_pca(ficto=True).days > -1  # Garante que o tempo de serviço retornará um numero positivo de dias

        pca_2 = PCA.objects.get(codigo_pca='00000020999')
        assert isinstance(pca_2.tempo_servico_pca(ficto=True), timedelta)
        assert pca_2.tempo_servico_pca(ficto=True).days > -1  # Garante que o tempo de serviço retornará um numero positivo de dias
