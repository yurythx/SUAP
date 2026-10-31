
$(document).ready(function() {
    /*
    Função criada para monitar mudanças em campos "hidden", uma vez que o evento "change"
    de um campo hidden não é disparado e no caso do componente "forms.ModelPopupChoiceField"
    não é possível se basear em nenhum outro componente para disparar o evento onchange.

    Exemplo do HTML gerado por um campo do tipo "forms.ModelPopupChoiceField":
    <div class="form-row field-tipo_processo">
            <div>
                    <label class="required" for="id_tipo_processo" title="Preenchimento obrigatório">Tipo de Processo:</label>

                    <input id="id_tipo_processo" name="tipo_processo" value="666" type="hidden">
                    <input value="" id="__tipo_processo__" readonly="true" style="background-color: rgb(238, 238, 238);" type="text">
                    <a class="btn" href="javascript:popup('/djtools/popup_choice_field/tipo_processo/'+
                        document.getElementById('id_tipo_processo').value+'/?'+ get_params(), 1000, 400, get_tipo_processo_qs(), false);">Buscar</a>

            </div>

    </div>
    */
    function onchange_hidden_input(selector, callback) {
       var input = $(selector);
       var oldvalue = input.val();
       setInterval(function(){
          if (input.val()!=oldvalue){
              oldvalue = input.val();
              callback();
          }
       }, 1000);
    }


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
    var tipo_processo_id_onready = $("#id_tipo_processo").val();
    var hipotese_legal_id_onready = $("#id_hipotese_legal").val();

    log_info("tipo_processo_id_onready: {0} ...".f(tipo_processo_id_onready));
    log_info("hipotese_legal_id_onready: {0} ...".f(hipotese_legal_id_onready));

    // Valores que serão manipulados nos eventos onchange de cada componente.
    var tipo_processo_id_selected;
    var nivel_acesso_id_selected;

    // Filtro por tipo_processo do processo.
    function tipo_processo_onchange_callback() {
        log_info("Disparado o evento onchange de #id_tipo_processo ...");
        $("#id_hipotese_legal").html('');
        $("#id_nivel_acesso_default").val('');

        tipo_processo_id_selected = $('#id_tipo_processo').val();
        if (tipo_processo_id_selected) {
            log_info("Carregando o nível de acesso padrão para o tipo_processo '{0}' (id: {1}) ...".f(
                $(this).children("option").filter(":selected").text(),
                tipo_processo_id_selected), 1);
            $.get("/processo_eletronico/tipo_processo_classificacoes_nivel_acesso_padrao/" + tipo_processo_id_selected + "/", function (data) {
                nivel_acesso_id_selected = data.nivel_acesso_padrao.id
                $("#id_nivel_acesso_default").val(data.nivel_acesso_padrao.descricao);

                log_info("Carregando as hipóteses legais para o nível de acesso '{0}' (id: {1}) ...".f(
                    $(this).children("option").filter(":selected").text(),
                    nivel_acesso_id_selected), 2);
                $.get("/processo_eletronico/get_hipoteses_legais_by_processo_nivel_acesso/" + nivel_acesso_id_selected + "/", function (data) {
                    log_info("Carregando as hipóteses legais ...", 2);
                    $("#id_hipotese_legal").html('');
                    $.each(data.hipoteses_legais, function(i, value) {
                        hipotese_legal_option = $("<option>").text(value.descricao).attr("value", value.id);
                        if (hipotese_legal_id_onready && hipotese_legal_id_onready == value.id) {
                            log_info("Hipótese legal setada: o que está atualmente cadastrado no requerimento - '{0}' (id: {1}) ...".f(value.nome, value.id), 2);
                            hipotese_legal_option = hipotese_legal_option.attr("selected", "selected");
                        }
                        log_info(hipotese_legal_option)
                        $("#id_hipotese_legal").append(hipotese_legal_option);
                    });
                });
            });
        }
    }

    // Disparando a cadeia de eventos dos combos, começando a partir do combo de "Tipo de Processo".
    onchange_hidden_input('#id_tipo_processo', tipo_processo_onchange_callback);
    tipo_processo_onchange_callback();
});

