
$(document).ready(function () {
    $('#id_data_inicio_sintomas').parent().parent().hide();
    $('select[name="sintomas"]').parent().parent().hide();
    $('#id_data_ultimo_teste').parent().parent().hide();
    $('#id_resultado_ultimo_teste').parent().parent().hide();
    $('#id_arquivo_ultimo_teste').parent().parent().parent().hide();
    $('#id_data_contato_suspeito').parent().parent().hide();
    $('#id_mora_com_suspeito').parent().parent().hide();
    $('#id_esteve_sem_mascara').parent().parent().hide();
    $('#id_tempo_exposicao').parent().parent().hide();
    $('#id_suspeito_fez_teste').parent().parent().hide();
    $('#id_arquivo_teste').parent().parent().parent().hide();
    exibir_esconder_campo();
    $("#id_declaracao").on('change', function () {
        exibir_esconder_campo();
    });


});


function exibir_esconder_campo() {
    if ($('#id_declaracao').val() == 'Suspeito sintomático' || $('#id_declaracao').val() == 'Confirmado') {
        $('#id_data_inicio_sintomas').parent().parent().show();
        $("#id_data_inicio_sintomas").parent().addClass('required');
        $('select[name="sintomas"]').parent().parent().show();
        $('select[name="sintomas"]').parent().addClass('required');
        $('#id_data_ultimo_teste').parent().parent().show();
        $('#id_resultado_ultimo_teste').parent().parent().show();
        $('#id_arquivo_ultimo_teste').parent().parent().parent().show();
        $('#id_data_contato_suspeito').parent().parent().hide();
        $("#id_data_contato_suspeito").parent().removeClass('required');
        $('#id_mora_com_suspeito').parent().parent().hide();
        $("#id_mora_com_suspeito").parent().removeClass('required');
        $('#id_esteve_sem_mascara').parent().parent().hide();
        $("#id_esteve_sem_mascara").parent().removeClass('required');
        $('#id_tempo_exposicao').parent().parent().hide();
        $("#id_tempo_exposicao").parent().removeClass('required');
        $('#id_suspeito_fez_teste').parent().parent().hide();
        $("#id_suspeito_fez_teste").parent().removeClass('required');
        $('#id_arquivo_teste').parent().parent().parent().hide();

    }
    else if ($('#id_declaracao').val() == 'Suspeito contactante'){
        $('#id_data_inicio_sintomas').parent().parent().hide();
        $("#id_data_inicio_sintomas").parent().removeClass('required');
        $('select[name="sintomas"]').parent().parent().hide();
         $('select[name="sintomas"]').parent().removeClass('required');
        $('#id_data_ultimo_teste').parent().parent().hide();
        $('#id_resultado_ultimo_teste').parent().parent().hide();
        $('#id_arquivo_ultimo_teste').parent().parent().parent().hide();
        $('#id_data_contato_suspeito').parent().parent().show();
        $("#id_data_contato_suspeito").parent().addClass('required');
        $('#id_mora_com_suspeito').parent().parent().show();
        $("#id_mora_com_suspeito").parent().addClass('required');
        $('#id_esteve_sem_mascara').parent().parent().show();
        $("#id_esteve_sem_mascara").parent().addClass('required');
        $('#id_tempo_exposicao').parent().parent().show();
        $("#id_tempo_exposicao").parent().addClass('required');
        $('#id_suspeito_fez_teste').parent().parent().show();
        $("#id_suspeito_fez_teste").parent().addClass('required');
        $('#id_arquivo_teste').parent().parent().parent().show();
    }


}
