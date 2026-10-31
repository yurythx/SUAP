$(document).ready(function () {
    exibir_esconder_campo();
    $("#id_tem_agravos_primeiro_grau").on('change', function () {
        exibir_esconder_campo();
    });

     $("#id_tem_agravos_segundo_grau").on('change', function () {
        exibir_esconder_campo();
    });
});

function clearprimeiro() {
    $("select[name='agravos_primeiro_grau']").val(null).trigger('change');
}

function clearsegundo() {
    $("select[name='agravos_segundo_grau']").val(null).trigger('change');
}

function exibir_esconder_campo() {
    if ($('#id_tem_agravos_primeiro_grau').val() == 'True') {
        $("select[name='agravos_primeiro_grau']").parent().show();
        $("select[name='agravos_primeiro_grau']").parent().addClass('required');
    } else {
        $("select[name='agravos_primeiro_grau']").parent().hide();
        var currentVal = $("select[name='agravos_primeiro_grau']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearprimeiro();
        }
    }

     if ($('#id_tem_agravos_segundo_grau').val() == 'True') {
        $("select[name='agravos_segundo_grau']").parent().show();
        $("select[name='agravos_segundo_grau']").parent().addClass('required');
    } else {
        $("select[name='agravos_segundo_grau']").parent().hide();
        var currentVal = $("select[name='agravos_segundo_grau']").val();
        if (currentVal !== null && currentVal.length > 0) {
            clearsegundo();
        }
    }
}
