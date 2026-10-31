function checar_tipo_cadastro() {

    if (document.getElementById('id_tipo_cadastro_0').checked) {
        $('.id_documento').show();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().hide();
        $('#id_numero').parent().parent().parent().hide();
    }
    else if (document.getElementById('id_tipo_cadastro_1').checked) {
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().show();
        $('#id_url_documento').parent().parent().hide();
        $('#id_numero').parent().parent().parent().show();
    }
    else if (document.getElementById('id_tipo_cadastro_2').checked) {
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().show();
        $('#id_numero').parent().parent().parent().show();
    }
    else{
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().hide();
        $('#id_numero').parent().parent().parent().hide();
    }
    
}

function checar_tipo() {

    var tipo = $('#id_tipo').val();

    if (tipo == '5') {
        $('#id_quantidade_vagas').parent().parent().show();
    }else{
        $('#id_quantidade_vagas').parent().parent().hide();
    }

    if (tipo == '3' || tipo == '4') {
        $('#id_validade').parent().parent().show();
    }else{
        $('#id_validade').parent().parent().hide();
    }
}

function checar_tipo_documento() {

    var tipo_documento = $('#id_tipo_documento').val();
    var tipo = $('#id_tipo').val();

    if(tipo_documento == 'Lei Federal'){
        $('#id_orgao').parent().parent().hide();
        $('#id_orgao').val('');
    }else{
        $('#id_orgao').parent().parent().show();
    }
    if(tipo_documento == 'Resolução'){
        $('#id_orgao').val('CONSUP/'+$('#id_sigla_instituicao').val());
    }else if(tipo_documento == 'Portaria'){
        if (tipo == '3' || tipo == '4'){
            var modalidade = $('#id_modalidade').val()
            if (modalidade == '9' || modalidade == '16'){
                $('#id_orgao').val('MEC');
            }else{
                $('#id_orgao').val('SERES/MEC');
            }
        }else{
            $('#id_orgao').val($('#id_sigla_orgao_campus').val());
        }
    }else if(tipo_documento == 'Deliberação'){
        $('#id_orgao').val('CONSEPEX/'+$('#id_sigla_instituicao').val());
    }
}

jQuery(function () {

    $('#id_tipo_cadastro').click(function () {
        checar_tipo_cadastro();
    });

    $('#id_tipo').change(function () {
        checar_tipo();
    });

    $('#id_tipo_documento').change(function () {
        checar_tipo_documento();
    });
    
    checar_tipo_cadastro();
    checar_tipo();

});
