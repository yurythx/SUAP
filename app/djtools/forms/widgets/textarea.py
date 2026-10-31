from django import forms
from django.utils.safestring import mark_safe


class TextareaCounterWidget(forms.Textarea):
    def __init__(self, max_length, attrs=None):
        self.max_length = max_length
        super().__init__(attrs)

    def render(self, name, value, attrs=None, renderer=None):
        max_length = self.max_length
        id_ = attrs['id']
        script = f"""
        <script>
            jQuery(document).ready(function() {{
                var textarea = $("#{id_}");
                textarea.on('keyup', function() {{
                    textCounter_{id_}(textarea, {max_length});
                }});
                count = get_qtd_caracteres(textarea);
                textarea.parent().find(".help.grid-area-extra").append(' <span id="counter_{id_}">'+({max_length}-count)+'</span> caractere(s) restante(s).');
            }});
            function textCounter_{id_}(field, maxlimit ) {{
                if ( get_qtd_caracteres(field) > maxlimit ) {{
                    set_max_caracteres(field, maxlimit);
                    $("#counter_{id_}").text(0);
                }} else {{
                    $("#counter_{id_}").text(maxlimit - get_qtd_caracteres(field));
                }}
            }}
            function get_qtd_caracteres(field){{
                // O navegador normaliza quebras de linha do textarea para "\\r\\n" (2 caracteres)
                // ao submeter o formulário, então cada "\\n" aqui contabiliza como 2 para bater
                // com o tamanho que de fato chega ao servidor (max_length do model/campo).
                var texto = field.val();
                var quebras_de_linha = (texto.match(/\\n/g) || []).length;
                return texto.length + quebras_de_linha;
            }}
            function set_max_caracteres(field, maxlimit){{
                // Trunca respeitando a mesma contagem de get_qtd_caracteres (quebra de linha = 2).
                var texto = field.val();
                var count = 0;
                var i = 0;
                for (; i < texto.length; i++) {{
                    count += (texto[i] === '\\n') ? 2 : 1;
                    if (count > maxlimit) {{
                        break;
                    }}
                }}
                field.val(texto.substr(0, i));
            }}

        </script>
        """
        html = super().render(name, value, attrs)
        return mark_safe(f'{html}{script}')


class TextareaCloneWidget(forms.Textarea):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.clones = ''

    def render(self, name, value, attrs=None, renderer=None):
        id_ = attrs['id']
        if not attrs:
            attrs = {}
        attrs.update(style='width:100%')
        html = super().render(name, value, attrs)
        html = f"""
            <div class="grid-area-input d-flex flex-wrap gap-3">
                <div>
                    {html}
                </div>
                <div id="clone_{id_}" class="flex-grow-1" style="flex-basis:100px; height:240px; overflow:scroll">
                    <label>Buscar/Filtrar</label>
                    <input type="text" style="width:100%" name="q" value="" id="search_{id_}" class="search-query">

                    {self.clones}
                </div>
            </div>
            <p class="help">Selecione qualquer registro para copiar seu conteúdo para a área de texto.</p>

            <style>
                #clone_{id_} div{{cursor:pointer; padding:.25rem .5rem !important; border:1px solid grey; margin-top:.5rem}}
                #clone_{id_} div:hover{{background-color:#DEDEDE;}}
            </style>

            <script>
                jQuery(document).ready(function() {{
                    $("#clone_{id_} div").click(function(){{$("#{id_}").val($(this).find("p")[0].innerHTML.split("<br>").join(""));}});
                    jQuery.expr[':'].icontains = function(a, i, m) {{
                        return jQuery(a).text().toUpperCase().indexOf(m[3].toUpperCase()) >= 0;
                    }};

                    $("#search_{id_}").keyup(
                        function(){{
                            var value = $(this).val();
                            var itens = $("#clone_{id_}").find("div > p");
                            for(var i=0; i<itens.length; i++) $(itens[i]).parent().show();
                            var hidden = itens.filter(":not(:icontains("+value+"))");
                            for(var i=0; i<hidden.length; i++) $(hidden[i]).parent().hide();
                        }}
                    );
                }});
            </script>

        """
        return mark_safe(html)
