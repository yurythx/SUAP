from rsc_tae.models.anexo import RolSaberCompetenciaAnexo


class TestNomeExibicaoAnexo:
    """A CRSC precisa referenciar o anexo de forma inequívoca durante a deliberação,
    já que o mesmo nome de arquivo se repete entre processos — daí o prefixo com o ID.
    """

    def test_prefixa_o_nome_original_com_o_id(self):
        anexo = RolSaberCompetenciaAnexo(id=12345, nome_original='Nome-anexo.pdf')
        assert anexo.nome_exibicao == '#12345 - Nome-anexo.pdf'

    def test_sem_nome_original_usa_o_caminho_do_arquivo(self):
        anexo = RolSaberCompetenciaAnexo(id=7, nome_original='')
        anexo.arquivo = 'rsc_tae/rol_saber_competencia/anexos/doc.pdf'
        assert anexo.nome_exibicao == '#7 - rsc_tae/rol_saber_competencia/anexos/doc.pdf'

    def test_sem_arquivo_mantem_o_rotulo_padrao(self):
        anexo = RolSaberCompetenciaAnexo(id=99, nome_original='')
        assert anexo.nome_exibicao == '#99 - Anexo'
