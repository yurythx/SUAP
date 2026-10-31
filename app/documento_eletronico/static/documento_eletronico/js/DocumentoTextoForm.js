
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
    var tipo_documento_id_onready = $("#id_tipo").val();
    var modelo_documento_id_onready = $("#id_modelo").val();
    var nivel_acesso_id_onready = $("#id_nivel_acesso").val();
    var hipotese_legal_id_onready = $("#id_hipotese_legal").val();

    log_info("tipo_documento_id_onready: {0} ...".f(tipo_documento_id_onready));
    log_info("modelo_documento_id_onready: {0} ...".f(modelo_documento_id_onready));
    log_info("nivel_acesso_id_onready: {0} ...".f(nivel_acesso_id_onready));
    log_info("hipotese_legal_id_onready: {0} ...".f(hipotese_legal_id_onready));

    // Valores que serão manipulados nos eventos onchange de cada componente.
    var tipo_documento_id_selected;
    var modelo_documento_id_selected;
    var nivel_acesso_id_selected;

    // Filtro por tipo de documento.
    $("#id_tipo").on('change', function() {
        log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
        $("#id_modelo").html('');

        tipo_documento_id_selected = $(this).val();
        if (tipo_documento_id_selected) {
            log_info("Carregando os modelos de documento para o tipo de documento '{0}' (id: {1}) ...".f(
                $(this).children("option").filter(":selected").text(),
                tipo_documento_id_selected), 1);

            modelo_documento_id_selected = $("#id_modelo").val();
            $.get("/documento_eletronico/modelos_tipo_documento/" + tipo_documento_id_selected + "/", function (data) {
                $("#id_modelo").html('');
                $.each(data.modelos, function(i, value) {
                    modelo_option = $("<option>").text(value.nome).attr("value", value.id);
                    if (modelo_documento_id_onready && modelo_documento_id_onready == value.id) {
                        log_info("Modelo setado: o que está atualmente cadastrado no documento - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                        modelo_option = modelo_option.attr("selected", "selected");
                    }
                    $("#id_modelo").append(modelo_option);
                });

                log_info("Fim do carregamento os modelos de documento para o tipo de documento '{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    tipo_documento_id_selected), 1);

                // Essa chamada tem que ocorrer aqui dentro pois o GET ocorre de maneira assícrona. Caso contrário, depois
                // de alterar um tipo, serão carretados os dados inerentes ao modelo anterior selecionado (nivel de acesso
                // padrão, níveis de acesso permitidos, classificações...).
                $("#id_modelo").trigger('change');
            });
        } else {
            $("#id_modelo").trigger('change');
        }
    });


    // Filtro por modelo do documento.
    $("#id_modelo").on('change', function() {
        log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
        $("#id_nivel_acesso").html('');

        modelo_documento_id_selected = $(this).val();
        if (tipo_documento_id_selected && modelo_documento_id_selected) {
            log_info("Carregando os níveis de acesso e classificações para o modelo '{0}' (id: {1}) ...".f(
                $(this).children("option").filter(":selected").text(),
                modelo_documento_id_selected), 1);

            $.get("/documento_eletronico/nivel_acesso_padrao_classificacoes_modelo_documento/" + modelo_documento_id_selected + "/", function (data) {
                log_info("Carregando os níveis de acesso ...", 2);
                $("#id_nivel_acesso").html('');
                $.each(data.niveis_acesso_permitidos, function(i, value) {
                    nivel_acesso_option = $("<option>").text(value.descricao).attr("value", value.id);
                    $("#id_nivel_acesso").append(nivel_acesso_option);
                });

                if (nivel_acesso_id_onready && modelo_documento_id_onready==modelo_documento_id_selected) {
                    log_info("Nível de acesso setado: o que está atualmente cadastrado no documento ...", 3);
                    $("#id_nivel_acesso").val(nivel_acesso_id_onready);
                } else {
                    log_info("Nível de acesso setado: o padrão definido pro modelo de documento selecionado ...", 3);
                    $("#id_nivel_acesso").val(data.nivel_acesso_padrao);
                }


                log_info("Carregando os classificações ...", 1);
                $("#id_classificacao").html('');

                classificacao_ids = ''
                classificacao_descricao = ''
                $.each(data.classificacoes, function(i, value) {
                    classificacao_ids = classificacao_ids + value.id + ';'
                    classificacao_descricao = classificacao_descricao + value.codigo + ' - ' + value.descricao + ', '
                });
                classificacao_ids = classificacao_ids.substring(0, classificacao_ids.length-1)
                classificacao_descricao = classificacao_descricao.substring(0, classificacao_descricao.length-2)
                $("#id_classificacao").val(classificacao_ids);
                $("#__classificacao__").val(classificacao_descricao);


                $("#id_nivel_acesso").trigger('change');
            });
        } else {
            $("#id_nivel_acesso").trigger('change');
        }
    });



    // Filtro por nível de acesso do Documento
    $("#id_nivel_acesso").on('change', function() {
        log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
        $("#id_hipotese_legal").html('');

        nivel_acesso_id_selected = $(this).val();
        if (modelo_documento_id_selected && nivel_acesso_id_selected) {
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
        }
    });


    // Disparando a cadeia de eventos dos combos, começando a partir do combo de "Tipo de Documento".
    $("#id_tipo").trigger('change');
});

