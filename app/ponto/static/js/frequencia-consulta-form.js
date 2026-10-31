$(document).ready(function () {
    /**
     * somente frequências inconsistentes
     */
    function so_inconsistentes_show(){
        var row_fields = $("#id_so_inconsistentes_apenas_esta_inconsistencia").parent().parent();
        $("#id_so_inconsistentes_apenas_esta_inconsistencia").removeAttr("disabled");
        $("#id_so_inconsistentes_situacao_abono").removeAttr("disabled");
        $("#id_so_inconsistentes_situacao_debito").removeAttr("disabled");
        $(row_fields).fadeIn();
    }

    function so_inconsistentes_hide(){
        var row_fields = $("#id_so_inconsistentes_apenas_esta_inconsistencia").parent().parent();
        $(row_fields).hide();
        $("#id_so_inconsistentes_apenas_esta_inconsistencia").attr("disabled", "disabled");
        $("#id_so_inconsistentes_situacao_abono").attr("disabled", "disabled");
        $("#id_so_inconsistentes_situacao_debito").attr("disabled", "disabled");
    }

    if (!$("#id_so_inconsistentes").prop("checked")){
        so_inconsistentes_hide();
    }

    $("#id_so_inconsistentes").click(function () {
        if ($(this).prop("checked")){
            so_inconsistentes_show();
            $("#id_so_inconsistentes_apenas_esta_inconsistencia").focus();
        }
        else {
            so_inconsistentes_hide();
        }
    });


    /**
     * botões extras
     */
    $("#btn-frequencias-mes-passado").click(function () {
        desativa_btns_extras();
        form_submit($(this).attr("data-dia-inicial"), $(this).attr("data-dia-final"));
    });
    $("#btn-frequencias-semana-passada").click(function () {
        desativa_btns_extras();
        form_submit($(this).attr("data-dia-inicial"), $(this).attr("data-dia-final"));
    });
    $("#btn-frequencias-mes-atual").click(function () {
        desativa_btns_extras();
        form_submit($(this).attr("data-dia-inicial"), $(this).attr("data-dia-final"));
    });
    $("#btn-frequencias-semana-atual").click(function () {
        desativa_btns_extras();
        form_submit($(this).attr("data-dia-inicial"), $(this).attr("data-dia-final"));
    });
    $("#btn-frequencias-ultimo-ano").click(function () {
        desativa_btns_extras();
        form_submit($(this).attr("data-dia-inicial"), $(this).attr("data-dia-final"));
    });

    function desativa_btns_extras() {
        $(".btn-frequencias").attr("disabled", "disabled");
    }


    /**
     * form submit
     */
    var form_consulta_frequencias = document.getElementById("id_faixa_0").form;

    function form_submit(data_inicial, data_final){
        $("#id_faixa_0").val(data_inicial);
        $("#id_faixa_1").val(data_final);
        $(form_consulta_frequencias).find("input[type=submit]").click();
    }

    $(form_consulta_frequencias).submit(function () {
        desativa_btns_extras();
    });
});
