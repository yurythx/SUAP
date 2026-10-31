from pafc.models import Conteudo, ModeloPAFC, Secao


def test_texto_do_modelo_mantem_marcadores_sem_executar_tags() -> None:
    conteudo = Conteudo(secao=Secao(modelo_pafc=ModeloPAFC()), texto=f'<p>{{{{ {ModeloPAFC.MARCADOR_NOME_CURSO} }}}}</p>{{% include "nope.html" %}}')

    assert conteudo.get_texto() == f'<p>{{{{ {ModeloPAFC.MARCADOR_NOME_CURSO} }}}}</p>{{% include "nope.html" %}}'
