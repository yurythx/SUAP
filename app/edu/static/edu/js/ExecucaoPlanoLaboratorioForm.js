function checar_tipo_cadastro() {

    if (document.getElementById('id_tipo_cadastro_0').checked) {
        $('.id_documento').show();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().hide();
    }
    else if (document.getElementById('id_tipo_cadastro_1').checked) {
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().show();
        $('#id_url_documento').parent().parent().hide();
    }
    else if (document.getElementById('id_tipo_cadastro_2').checked) {
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().show();
    }
    else{
        $('.id_documento').hide();
        $('#id_arquivo_documento').parent().parent().parent().hide();
        $('#id_url_documento').parent().parent().hide();
    }
    
}

jQuery(function () {

    $('#id_tipo_cadastro').click(function () {
        checar_tipo_cadastro();
    });

    checar_tipo_cadastro();

});
