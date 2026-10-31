
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

    const inputElement = document.querySelector('input[value="Salvar"]');

    // Verifique se o elemento foi encontrado
    if (inputElement) {
        // Valores iniciais da página, após o seu completo carregamento.
        var projeto_id_onready = $("#id_projeto").val();
        var processo_id_onready = $("#id_processo").val();
        var origem_recurso_etapa_id_onready = $("#id_origem_recurso_etapa").val();
        var plano_interno_id_onready = $("#id_plano_interno").val();


        // Inicialmente, desabilita os campos processo, origem_recurso e plano_inteno
        $('#id_processo').prop('disabled', true);
        $('#id_origem_recurso_etapa').prop('disabled', true);
        $('#id_plano_interno').prop('disabled', true);


        // Valores que serão manipulados nos eventos onchange de cada componente.
        var projeto_id_selected;
        var processo_id_selected;
        var origem_recurso_etapa_id_selected;
        var plano_interno_id_selected;

        // Filtro por projeto
        $("#id_projeto").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            projeto_id_selected = $(this).val();

            // Limpe o valor do campo 'componente funcional' e desabilite-o
            $('#id_processo').val('');
            $('#id_processo').prop('disabled', true);
            if (projeto_id_selected) {
                log_info("Carregando os projetos'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    projeto_id_selected), 1);
                //Habilita campo processo
                $('#id_processo').prop('disabled', false);
                processo_id_selected = $("#id_processo").val();
                $.get("/plan_estrategico/filtrar_processo_por_projeto/" + projeto_id_selected + "/", function (data) {
                    $("#id_processo").html('');
                    $.each(data.processos, function (i, value) {
                        processo_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (processo_id_onready && processo_id_onready == value.id) {
                            log_info("Processo setado: o que está atualmente cadastrado no projeto - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            processo_option = processo_option.attr("selected", "selected");
                        }
                        $("#id_processo").append(processo_option);
                    });

                    log_info("Fim do carregamento dos processos  para o projeto '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        projeto_id_selected), 1);

                    // Essa chamada tem que ocorrer aqui dentro pois o GET ocorre de maneira assícrona. Caso contrário, depois
                    // de alterar um tipo, serão carretados os dados inerentes ao modelo anterior selecionado (nivel de acesso
                    // padrão, níveis de acesso permitidos, classificações...).
                    $("#id_processo").trigger('change');
                });
            } else {
                $("#id_processo").trigger('change');
            }
        });

        // Filtro por processo
        $("#id_processo").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            processo_id_selected = $(this).val();

            // Limpe o valor do campo 'origem_recurso_etapa' e desabilite-o
            $('#id_origem_recurso_etapa').val('');
            $('#id_origem_recurso_etapa').prop('disabled', true);

            if (processo_id_selected) {
                log_info("Carregando os processos'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    origem_recurso_etapa_id_selected), 1);
                $('#id_origem_recurso_etapa').prop('disabled', false);
                origem_recurso_etapa_id_selected = $("#id_origem_recurso_etapa").val();
                $.get("/plan_estrategico/filtrar_origem_por_processo/" + processo_id_selected + "/", function (data) {
                    $("#id_origem_recurso_etapa").html('');
                    $.each(data.origens_recurso, function (i, value) {
                        origem_recurso_etapa_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (origem_recurso_etapa_id_onready && origem_recurso_etapa_id_onready == value.id) {
                            log_info("origem de recurso setado: o que está atualmente cadastrado no processo - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            origem_recurso_etapa_option = origem_recurso_etapa_option.attr("selected", "selected");
                        }
                        $("#id_origem_recurso_etapa").append(origem_recurso_etapa_option);
                    });

                    log_info("Fim do carregamento das origens para o processo '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        processo_id_selected), 1);
                    $("#id_origem_recurso_etapa").trigger('change');
                });
            } else {
                $("#id_origem_recurso_etapa").trigger('change');
            }
        });
        // Filtro por origem de recurso etapa
        $("#id_origem_recurso_etapa").on('change', function () {
            log_info("Disparado o evento onchange de #{0} ...".f($(this).attr("id")));
            origem_recurso_etapa_id_selected = $(this).val();

            // Limpe o valor do campo 'plano interno' e desabilite-o
            $('#id_plano_interno').val('');
            $('#id_plano_interno').prop('disabled', true);

            if (origem_recurso_etapa_id_selected) {
                log_info("Carregando as origens'{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    plano_interno_id_selected), 1);
                $('#id_plano_interno').prop('disabled', false);
                plano_interno_id_selected = $("#id_plano_interno").val();
                $.get("/plan_estrategico/filtrar_plano_interno_por_origem_recurso_etapa/" + origem_recurso_etapa_id_selected + "/", function (data) {
                    $("#id_plano_interno").html('');
                    $.each(data.planos, function (i, value) {
                        plano_interno_option = $("<option>").text(value.nome).attr("value", value.id);
                        if (plano_interno_id_onready && plano_interno_id_onready == value.id) {
                            log_info("plano interno setado: o que está atualmente cadastrado na origem - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            plano_interno_option = plano_interno_option.attr("selected", "selected");
                        }
                        $("#id_plano_interno").append(plano_interno_option);
                    });

                    log_info("Fim do carregamento dos planos para a origem '{0}' (id: {1}) ...".f(
                        $(this).children("option").filter(":selected").text(),
                        origem_recurso_etapa_id_selected), 1);
                    $("#id_plano_interno").trigger('change');
                });
            } else {
                $("#id_plano_interno").trigger('change');
            }
        });
        // Disparando a cadeia de eventos dos combos, começando a partir do combo de "Projeto".
        $("#id_projeto").trigger('change');
    }
});
