function checar_tipo() {
    var val = $('#id_tipo').val();

    if (val == "Titulação dos servidores") {
        $('#id_cpfs').parent().parent().show();
        $('#id_codigos').parent().parent().hide();
    } else {
        $('#id_cpfs').parent().parent().hide();
        $('#id_codigos').parent().parent().show();
    }

}

jQuery(function () {
    $('#id_tipo').change(function () {
        checar_tipo();
    });

    $('#id_cpfs').parent().parent().hide();
    $('#id_codigos').parent().parent().hide();

    checar_tipo();
});
