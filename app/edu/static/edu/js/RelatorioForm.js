function checar_resumo() {
    if (jQuery('#id_formatacao').val() !== 'simples') {
        jQuery('#id_ordenacao').parent().hide();
        jQuery('#id_agrupamento').parent().hide();
        jQuery('#id_quantidade_itens').parent().hide();
        jQuery('.exibicao').parent().hide();
    } else {
        jQuery('#id_ordenacao').parent().show();
        jQuery('#id_agrupamento').parent().show();
        jQuery('#id_quantidade_itens').parent().show();
        jQuery('.exibicao').parent().show();
    }
}

jQuery(function () {
    jQuery('#id_formatacao').change(function () {
        checar_resumo();
    });
    checar_resumo();
});
