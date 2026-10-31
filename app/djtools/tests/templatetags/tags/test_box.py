from django.template import engines
from django.utils.safestring import mark_safe


def renderizar(template: str, **contexto: object) -> str:
    return engines['django'].from_string(template).render(contexto)


class BoxTitleTest:
    def test_titulo_vindo_de_variavel_nao_e_compilado_como_template(self):
        html = renderizar('{% box titulo %}conteúdo{% endbox %}', titulo='{{ segredo }}', segredo='X')

        assert '{{ segredo }}' in html
        assert 'X' not in html

    def test_titulo_vindo_de_variavel_nao_executa_tags(self):
        html = renderizar('{% box titulo %}conteúdo{% endbox %}', titulo='{% debug %}', segredo='valor-do-contexto')

        assert '{% debug %}' in html
        assert 'valor-do-contexto' not in html

    def test_titulo_vindo_de_variavel_e_escapado(self):
        html = renderizar('{% box titulo %}conteúdo{% endbox %}', titulo='<script>alert(1)</script>')

        assert '&lt;script&gt;alert(1)&lt;/script&gt;' in html
        assert '<script>' not in html

    def test_titulo_vindo_de_variavel_marcado_como_seguro_nao_e_escapado(self):
        html = renderizar('{% box titulo %}conteúdo{% endbox %}', titulo=mark_safe('Dados <small>gerais</small>'))

        assert 'Dados <small>gerais</small>' in html

    def test_titulo_literal_continua_interpolando_variaveis(self):
        html = renderizar('{% box "Alunos de {{ turma }}" %}conteúdo{% endbox %}', turma='2026.1')

        assert 'Alunos de 2026.1' in html


class BoxArgumentosTest:
    def test_badge_literal_continua_interpolando_variaveis(self):
        html = renderizar('{% box "Log" badge="{{ total }}" %}conteúdo{% endbox %}', total=3)

        assert '<span class="badge">3</span>' in html

    def test_badge_vindo_de_variavel_nao_e_compilado_como_template(self):
        html = renderizar('{% box "Log" badge=rotulo %}conteúdo{% endbox %}', rotulo='{{ segredo }}', segredo='X')

        assert '<span class="badge">{{ segredo }}</span>' in html
        assert 'X' not in html

    def test_badge_numerico_zero_continua_aparecendo(self):
        html = renderizar('{% box "Log" badge=total %}conteúdo{% endbox %}', total=0)

        assert '<span class="badge">0</span>' in html

    def test_classe_vinda_de_variavel_com_filtro(self):
        html = renderizar('{% box "Filtros" class=tem_registro|yesno:"collapsed," %}conteúdo{% endbox %}', tem_registro=True)

        assert 'accordion collapsed' in html
