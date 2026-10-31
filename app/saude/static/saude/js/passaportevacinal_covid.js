
$(document).ready(function () {
    $('#id_atestado_medico').parent().parent().parent().hide();
    $('#id_texto_termo_ciencia').parent().parent().hide();
    $('#id_aceite_termo').parent().parent().hide();
    $('#id_senha').parent().parent().hide();
    exibir_esconder_campo();
    $("#id_tem_atestado_medico").on('change', function () {
        exibir_esconder_campo();
    });


});


function exibir_esconder_campo() {
    if ($('#id_tem_atestado_medico').val() == 'sim') {
        $('#id_atestado_medico').parent().parent().parent().show();
        $('#id_atestado_medico').attr('required', 'true');
        $('#id_senha').parent().parent().show();
        $('#id_texto_termo_ciencia').parent().parent().hide();
        $('#id_aceite_termo').parent().parent().hide();

    } else if  ($('#id_tem_atestado_medico').val() == 'não') {
        $('#id_atestado_medico').parent().parent().parent().hide();
        $('#id_atestado_medico').val(null);
        $('#id_texto_termo_ciencia').parent().parent().show();
        $('#id_aceite_termo').parent().parent().show();
        $('#id_aceite_termo').attr('required', 'true');
        $('#id_senha').parent().parent().show();
    }
    else {
        $('#id_atestado_medico').parent().parent().parent().hide();
        $('#id_atestado_medico').val(null);
        $('#id_texto_termo_ciencia').parent().parent().hide();
        $('#id_aceite_termo').parent().parent().hide();
        $('#id_senha').parent().parent().hide();
    }


}

