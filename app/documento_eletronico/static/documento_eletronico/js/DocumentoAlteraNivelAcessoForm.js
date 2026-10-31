
$(document).ready(function() {
    var SHOW_CONSOLE = false
    function log_info(msg, indent) {
        if (SHOW_CONSOLE) {
            if (indent == null) {
                console.info(msg);
            } else {
                console.info(new Array(indent*4).join(' ') + msg);
            }


        }
    }
    String.prototype.f = function(indent) {
        var s = this,
            i = arguments.length;

        while (i--) {
            s = s.replace(new RegExp('\\{' + i + '\\}', 'gm'), arguments[i]);
        }

        return s;
    };

    // Valores iniciais da página, após o seu completo carregamento.
    var nivel_acesso_id_onready = $("#id_nivel_acesso").val();
    var hipotese_legal_id_onready = $("#id_hipotese_legal").val();

    log_info("nivel_acesso_id_onready: {0} ...".f(nivel_acesso_id_onready));
    log_info("hipotese_legal_id_onready: {0} ...".f(hipotese_legal_id_onready));

    // Valores que serão manipulados nos eventos onchange de cada componente.
    var nivel_acesso_id_selected;

    // Filtro por nível de acesso do Documento
    $("#id_nivel_acesso").on('change', function() {
        log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
        $("#id_hipotese_legal").html('');

        nivel_acesso_id_selected = $(this).val();
        log_info("Carregando as hipóteses legais para o nível de acesso '{0}' (id: {1}) ...".f(
            $(this).children("option").filter(":selected").text(),
            nivel_acesso_id_selected), 1);

        $.get("/documento_eletronico/get_hipoteses_legais_by_documento_nivel_acesso/" + nivel_acesso_id_selected + "/", function (data) {
            log_info("Carregando as hipóteses legais ...", 2);
            $("#id_hipotese_legal").html('');
            $.each(data.hipoteses_legais, function(i, value) {
                hipotese_legal_option = $("<option>").text(value.descricao).attr("value", value.id);
                if (hipotese_legal_id_onready && hipotese_legal_id_onready == value.id) {
                    log_info("Hipótese legal setada: o que está atualmente cadastrada no documento - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                    hipotese_legal_option = hipotese_legal_option.attr("selected", "selected");
                }
                log_info(hipotese_legal_option)
                $("#id_hipotese_legal").append(hipotese_legal_option);
            });
        });
    });

    $("#id_nivel_acesso").trigger('change');
});

