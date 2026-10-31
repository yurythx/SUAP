function checar_tipo_documento() {
    if (document.getElementById('id_tipo_documento_final_0').checked) {
        $('#id_documento_final_url').parent().parent().show();
        $('#id_documento_final').parent().parent().parent().hide();
        $('#id_documento_final').val('');
        $('#documento-clear_id').prop("checked", true);
    } else {
        $('#id_documento_final_url').parent().parent().hide();
        $('#id_documento_final_url').val('');
        $('#id_documento_final').parent().parent().parent().show();

    }
}

jQuery(function () {

    $('#id_tipo_documento_final_0').click(function () {
        checar_tipo_documento();
    });
    $('#id_tipo_documento_final_1').click(function () {
        checar_tipo_documento();
    });

    checar_tipo_documento();
});
