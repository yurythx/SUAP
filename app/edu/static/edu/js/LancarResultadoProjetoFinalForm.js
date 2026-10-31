function checar_tipo_documento() {
    if (document.getElementById('id_tipo_documento_0').checked) {
        $('#id_documento_url').parent().parent().show();
        $('#id_documento').parent().parent().hide();
        $('#id_documento').val('');
        $('#documento-clear_id').prop("checked", true);
    } else {
        $('#id_documento_url').parent().parent().hide();
        $('#id_documento_url').val('');
        $('#id_documento').parent().parent().show();

    }
}

jQuery(function () {

    $('#id_tipo_documento_0').click(function () {
        checar_tipo_documento();
    });
    $('#id_tipo_documento_1').click(function () {
        checar_tipo_documento();
    });

    checar_tipo_documento();
});
