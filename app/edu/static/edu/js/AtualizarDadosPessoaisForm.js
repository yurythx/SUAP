jQuery(function () {

    var telefones = $('#id_esconde_telefone');
    if (telefones.is(':hidden')) {
        telefones.parent().hide();
    }

    function configureUtilizaTransporteEscolarPublico(valor) {
        if (valor == 'Sim') {
            $('#id_poder_publico_responsavel_transporte').parent().parent().show();
            $('#id_tipo_veiculo').parent().parent().show();
        }
        else if (valor == 'Não'){
            if ($('#id_poder_publico_responsavel_transporte').val() == ""){
                $('#id_poder_publico_responsavel_transporte').parent().parent().hide();
            }else{
                $('#id_poder_publico_responsavel_transporte').parent().parent().show();
            }
            if ($('#id_tipo_veiculo').val() == ""){
                $('#id_tipo_veiculo').parent().parent().hide();
            }else{
                $('#id_tipo_veiculo').parent().parent().show();
            }
        } else {
            $('#id_poder_publico_responsavel_transporte').parent().parent().hide();
            $('#id_tipo_veiculo').parent().parent().hide();
        }
    }

    $('#id_poder_publico_responsavel_transporte').parent().parent().hide();
    $('#id_tipo_veiculo').parent().parent().hide();
    $('#id_utiliza_transporte_escolar_publico').change(function () {
        configureUtilizaTransporteEscolarPublico($(this).val());
    });
    $('#id_poder_publico_responsavel_transporte').change(function () {
        configureUtilizaTransporteEscolarPublico($('#id_utiliza_transporte_escolar_publico').val());
    });
    $('#id_tipo_veiculo').change(function () {
        configureUtilizaTransporteEscolarPublico($('#id_utiliza_transporte_escolar_publico').val());
    });
    configureUtilizaTransporteEscolarPublico($('#id_utiliza_transporte_escolar_publico').val());
    initCepWidget('#id_cep');
});
