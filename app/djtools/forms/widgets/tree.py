from django.db.models import ForeignKey
from django.forms.widgets import (
    TextInput,
)
from django.utils.safestring import mark_safe
from pipeline.forms import PipelineFormMedia

from djtools.utils import (
    randomic,
)


class TreeWidget(TextInput):
    class Media(PipelineFormMedia):
        js_packages = ('jstree',)

    def __init__(self, id_=None, root_nodes=None, attrs=None):
        if not attrs:
            attrs = {}
        self.id_ = id_ or randomic()
        super().__init__(attrs)
        self.root_nodes = root_nodes
        self._filhos_por_pai = {}

    def get_parent_field(self):
        cls = self.choices.queryset.model
        for field in cls._meta.fields:
            if isinstance(field, ForeignKey) and field.remote_field.model == cls:
                return field
        raise Exception(f'Class {cls.__name__} has no self relation')

    def carregar_filhos_por_pai(self):
        """Carrega a árvore inteira em uma única consulta, agrupando os nós por pai.

        Returns:
            dict: mapeia o id do pai (``None`` para as raízes) na lista de filhos.
        """
        pai_attname = self.get_parent_field().attname
        filhos_por_pai = {}
        for node in self.choices.queryset.all():
            filhos_por_pai.setdefault(getattr(node, pai_attname), []).append(node)
        return filhos_por_pai

    def get_root_nodes(self):
        """Returns a root nodes list
        But for while, this list has a only element.
        This need to be fix. (ticket #1044)
        """
        return sorted(self._filhos_por_pai.get(None, []), key=lambda node: node.pk)

    def get_children(self, node):
        return self._filhos_por_pai.get(node.pk, [])

    def get_tree_as_ul(self, node):
        nodes = []
        nodes.append('<ul>')
        self.__get_descendents_helper(node, nodes)
        nodes.append('</ul>')
        return nodes

    def label_from_instance(self, obj):
        return str(obj)

    def __get_descendents_helper(self, node, nodes):
        nodes.append(f'<li id="{node.pk}"><a href="#" title="{node.nome}">{self.label_from_instance(node)}</a>')
        node_children = self.get_children(node)
        if node_children:
            nodes.append('<ul>')
        for c in node_children:
            self.__get_descendents_helper(c, nodes)
        if node_children:
            nodes.append('</ul>')
        nodes.append('</li>')
        return nodes

    # TODO: caso seja necessário deixar a configuração do multiple no init
    def render(self, name, value=None, attrs=None, renderer=None):
        value = value or ''
        self._filhos_por_pai = self.carregar_filhos_por_pai()
        root_nodes = self.root_nodes or self.get_root_nodes()
        tree_as_ul = []
        for root_node in root_nodes:
            tree_as_ul += self.get_tree_as_ul(root_node)

        tree_as_ul = ''.join(tree_as_ul)
        output = f"""
        <div class="tree-container" id="tree-{name}">
            {tree_as_ul}
        </div>
        <input type="hidden" name="{name}" value="{value}"/>
        <script class="source below">
        $(document).ready(function () {{
            let tree = $("#tree-{name}");
            tree.bind("select_node.jstree", function (event, data) {{
            value = data.selected;
            $("input[name={name}]").val(value)
            }});
            tree.bind('loaded.jstree', function(e, data) {{
            $(this).jstree("select_node", "{value}");
            }});
            tree.jstree({{
            'core': {{
                'multiple': false,
            }}
            }});

        }});
        $(".tree-container a").dblclick(function(event){{
            $(this).removeClass('jstree-clicked');
            $("input[name={name}]").val('')
        }});

        </script>"""
        return mark_safe(output)
