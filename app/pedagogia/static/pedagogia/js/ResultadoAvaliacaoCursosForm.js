function checar_filtrar_por() {
    if (document.getElementById('id_filtrar_por_1').checked) {
        jQuery('#id_modalidade').parent().parent().hide();
        jQuery('#id_curso').parent().parent().show();
        jQuery('#id_modalidade').val('');
    } else {
        jQuery('#id_modalidade').parent().parent().show();
        jQuery('#id_curso').parent().parent().hide();
        jQuery('#id_curso').val('');
        jQuery('input[name=curso]').parent().remove();
    }
}

jQuery(function() {
    jQuery('#id_filtrar_por_0').click(function() {
        checar_filtrar_por();
    });
    jQuery('#id_filtrar_por_1').click(function() {
        checar_filtrar_por();
    });
    checar_filtrar_por();
});
