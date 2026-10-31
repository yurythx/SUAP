function checar_tipo_tramitacao() {

    if (document.getElementById('id_tipo_tramitacao_1').checked) {
        $('#id_resolucao_criacao').parent().parent().show();
        $('#id_url_resolucao_criacao').parent().parent().show();
        
    } else {
        $('#id_resolucao_criacao').parent().parent().hide();
        $('#id_resolucao_criacao').val('');
        $('#id_url_resolucao_criacao').parent().parent().hide();
        $('#id_url_resolucao_criacao').val('');
    }
}
jQuery(function () {

    if ($('#id_tipo_tramitacao').length > 0) {
        $('#id_tipo_tramitacao').click(function () {
            checar_tipo_tramitacao();
        });
        
        checar_tipo_tramitacao();
    }
    
});
