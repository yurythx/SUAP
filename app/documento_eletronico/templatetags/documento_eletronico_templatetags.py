import html

from django.template import Context, Library, Node, Template
from djtools.utils import tl

register = Library()


class CabecalhoOrdenado(Node):
    def __init__(self, field, field_name, querystring, order_str):
        self.field = field[1:-1]  # retirando as aspas
        self.field_name = field_name[1:-1]  # retirando as aspas
        self.querystring = querystring[1:-1]  # retirando as aspas
        self.order_str = order_str[1:-1]  # retirando as aspas

    def render(self, context):
        querystring = Template(self.querystring).render(Context(context))
        order_str = Template(self.order_str).render(Context(context))
        field = self.field
        field_name = self.field_name
        negative_field = f'-{field}'
        retorno = """
                <th class="sortable">
                    {% if field in order_str %}
                        <div class="sortoptions">
                            <a class="sortremove" title="Remover da ordenação" href="?{{ querystring }}"></a>
                            {% if negative_field == order_str %}
                                <a class="toggle descending" href="?order_by={{ field }}&{{ querystring }}"></a>
                            {% elif field == order_str %}
                                <a class="toggle ascending" href="?order_by=-{{ field }}&{{ querystring }}"></a>
                            {% endif %}
                        </div>
                    {% endif %}
                    <div class="text">
                        <a href="?{{ querystring }}&order_by={{ field }}">{{ field_name }}</a>
                    </div>
                    <div class="clear"></div>
                </th>
        """
        return Template(retorno).render(Context(locals()))


@register.tag
def cabecalho_ordenado(parser, token):
    _tag_name, field, field_name, querystring, order_str = token.split_contents()
    return CabecalhoOrdenado(field, field_name, querystring, order_str)


@register.filter
def teste(texto):
    unescape = html.unescape
    return unescape(texto).replace('</br>', '')


@register.filter
def pode_ler_documento(documento):
    return documento.pode_ler(user=tl.get_user())
