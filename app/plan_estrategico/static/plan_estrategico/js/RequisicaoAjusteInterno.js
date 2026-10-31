$(document).ready(function() {
    var SHOW_CONSOLE = false;

    function log_info(msg, indent) {
        if (SHOW_CONSOLE) {
            if (indent == null) {
                console.info(msg);
            } else {
                console.info(new Array(indent * 4).join(' ') + msg);
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

    const inputElement = document.querySelector('input[value="Continuar"]');

    // Verifique se o elemento foi encontrado
    if (inputElement) {
        // Valores iniciais da página, após o seu completo carregamento.
        var projeto_id_onready = $("#id_projeto").val();
        var origem_recurso_id_onready = $("#id_origem_recurso").val();
        var plano_interno_id_onready = $("#id_plano_interno").val();
        var projeto_id_recebedor_onready = $("#id_projeto_recebedor").val();
        var origem_recurso_id_recebedor_onready = $("#id_origem_recurso_recebedor").val();
        var plano_interno_id_recebedor_onready = $("#id_plano_interno_recebedor").val();

        // Inicialmente, desabilite os campos origem_recurso e plano_inteno
        $('#id_origem_recurso').prop('disabled', true);
        $('#id_plano_interno').prop('disabled', true);
        $('#id_origem_recurso_recebedor').prop('disabled', true);
        $('#id_plano_interno_recebedor').prop('disabled', true);

        // Valores que serão manipulados nos eventos onchange de cada componente.
        var projeto_id_selected;
        var origem_recurso_id_selected;
        var plano_interno_id_selected;
        var projeto_id_recebedor_selected;
        var origem_recurso_id_recebedor_selected;
        var plano_interno_id_recebedor_selected;

        // Filtro por projeto
        $("#id_projeto").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            projeto_id_selected = $(this).val();

            // Limpe o valor do campo 'origem_recurso' e desabilite-o
            $('#id_origem_recurso').val('');
            $('#id_origem_recurso').prop('disabled', true);

            // Limpe o valor do campo 'plano_interno' e desabilite-o
            $('#id_plano_interno').val('');
            $('#id_plano_interno').prop('disabled', true);

            if (projeto_id_selected) {
                log_info("Carregando os projetos'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    projeto_id_selected), 1);

                //Habilita campo origem_recurso
                $('#id_origem_recurso').prop('disabled', false);
                origem_recurso_id_selected = $("#id_origem_recurso").val();
                $.get("/plan_estrategico/filtrar_origem_por_projeto/" + projeto_id_selected + "/", function (data) {
                    $("#id_origem_recurso").html('');
                    $.each(data.origens_recurso, function (i, value) {
                        origem_recurso_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (origem_recurso_id_onready && origem_recurso_id_onready == value.id) {
                            log_info("Origem Recurso setado: o que está atualmente cadastrado no projeto - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            origem_recurso_option = origem_recurso_option.attr("selected", "selected");
                        }
                        $("#id_origem_recurso").append(origem_recurso_option);
                    });

                    log_info("Fim do carregamento das origens  para o projeto '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        projeto_id_selected), 1);

                    // Essa chamada tem que ocorrer aqui dentro pois o GET ocorre de maneira assíncrona. Caso contrário, depois
                    // de alterar um tipo, serão carretados os dados inerentes ao modelo anterior selecionado (nivel de acesso
                    // padrão, níveis de acesso permitidos, classificações...).
                    $("#id_origem_recurso").trigger('change');
                });
            } else {
                $("#id_origem_recurso").trigger('change');
            }
        });

        // Filtro por origem recurso
        $("#id_origem_recurso").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            origem_recurso_id_selected = $(this).val();

            // Limpe o valor do campo 'plano_interno' e desabilite-o
            $('#id_plano_interno').val('');
            $('#id_plano_interno').prop('disabled', true);

            if (origem_recurso_id_selected) {
                log_info("Carregando as origens'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    origem_recurso_id_selected), 1);
                $('#id_plano_interno').prop('disabled', false);
                plano_interno_id_selected = $("#id_plano_interno").val();
                $.get("/plan_estrategico/filtrar_plano_interno_por_origem/" + origem_recurso_id_selected + "/", function (data) {
                    $("#id_plano_interno").html('');
                    $.each(data.planos, function (i, value) {
                        plano_interno_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (plano_interno_id_onready && plano_interno_id_onready == value.id) {
                            log_info("plano_interno setado: o que está atualmente cadastrado no origem - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            plano_interno_option = plano_interno_option.attr("selected", "selected");
                        }
                        $("#id_plano_interno").append(plano_interno_option);
                    });

                    log_info("Fim do carregamento dos planos  para a origem '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        origem_recurso_id_selected), 1);
                    $("#id_plano_interno").trigger('change');
                });
            } else {
                $("#id_plano_interno").trigger('change');
            }
        });

        // Filtro por projeto recebedor
        $("#id_projeto_recebedor").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            projeto_id_recebedor_selected = $(this).val();

            // Limpe o valor do campo 'origem_recurso_recebedor' e desabilite-o
            $('#id_origem_recurso_recebedor').val('');
            $('#id_origem_recurso_recebedor').prop('disabled', true);

            // Limpe o valor do campo 'plano_interno_recebedor' e desabilite-o
            $('#id_plano_interno_recebedor').val('');
            $('#id_plano_interno_recebedor').prop('disabled', true);

            if (projeto_id_recebedor_selected) {
                log_info("Carregando os projetos'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    projeto_id_recebedor_selected), 1);

                //Habilita campo origem_recurso_recebedor
                $('#id_origem_recurso_recebedor').prop('disabled', false);
                origem_recurso_id_recebedor_selected = $("#id_origem_recurso_recebedor").val();
                $.get("/plan_estrategico/filtrar_origem_por_projeto_recebedor/" + projeto_id_recebedor_selected + "/", function (data) {
                    $("#id_origem_recurso_recebedor").html('');
                    $.each(data.origens_recurso_recebedor, function (i, value) {
                        origem_recurso_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (origem_recurso_id_recebedor_onready && origem_recurso_id_recebedor_onready == value.id) {
                            log_info("Origem Recurso Recebedor setado: o que está atualmente cadastrado no projeto - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            origem_recurso_option = origem_recurso_option.attr("selected", "selected");
                        }
                        $("#id_origem_recurso_recebedor").append(origem_recurso_option);
                    });

                    log_info("Fim do carregamento das origens  para o projeto recebedor '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        projeto_id_recebedor_selected), 1);

                    // Essa chamada tem que ocorrer aqui dentro pois o GET ocorre de maneira assíncrona. Caso contrário, depois
                    // de alterar um tipo, serão carregados os dados inerentes ao modelo anterior selecionado (nivel de acesso
                    // padrão, níveis de acesso permitidos, classificações...).
                    $("#id_origem_recurso_recebedor").trigger('change');
                });
            } else {
                $("#id_origem_recurso_recebedor").trigger('change');
            }
        });

        // Filtro por origem recurso recebedor
        $("#id_origem_recurso_recebedor").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            origem_recurso_id_recebedor_selected = $(this).val();

            // Limpe o valor do campo 'plano_interno_recebedor' e desabilite-o
            $('#id_plano_interno_recebedor').val('');
            $('#id_plano_interno_recebedor').prop('disabled', true);

            if (origem_recurso_id_recebedor_selected) {
                log_info("Carregando as origens'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    origem_recurso_id_recebedor_selected), 1);
                $('#id_plano_interno_recebedor').prop('disabled', false);
                plano_interno_id_recebedor_selected = $("#id_plano_interno_recebedor").val();
                $.get("/plan_estrategico/filtrar_plano_interno_por_origem_recebedor/" + origem_recurso_id_recebedor_selected + "/", function (data) {
                    $("#id_plano_interno_recebedor").html('');
                    $.each(data.plano_interno_recebedor, function (i, value) {
                        plano_interno_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (plano_interno_id_recebedor_onready && plano_interno_id_recebedor_onready == value.id) {
                            log_info("plano_interno_recebedor setado: o que está atualmente cadastrado no origem - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            plano_interno_option = plano_interno_option.attr("selected", "selected");
                        }
                        $("#id_plano_interno_recebedor").append(plano_interno_option);
                    });

                    log_info("Fim do carregamento dos planos  para a origem recebedora '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        origem_recurso_id_recebedor_selected), 1);
                    $("#id_plano_interno_recebedor").trigger('change');
                });
            } else {
                $("#id_plano_interno_recebedor").trigger('change');
            }
        });

        // Disparando a cadeia de eventos dos combos, começando a partir do combo de "Projeto".
        $("#id_projeto").trigger('change');
        $("#id_projeto_recebedor").trigger('change');
    }
});
