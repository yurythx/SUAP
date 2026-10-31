function checar_tipo() {
    var val = $('#id_tipo').val();

    if (val == 1) {
        $('#id_turno').parent().parent().parent().show();
    } else {
        $('#id_turno').parent().parent().parent().hide();
    }

    if (val == 2) {
        $('input[name="curso_campus"]').parent().parent().parent().show()
    } else {
        $('input[name="curso_campus"]').parent().parent().parent().hide()
    }

    if (val == 3) {
        $('input[name="turma"]').parent().parent().parent().show();
    } else {
        $('input[name="turma"]').parent().parent().parent().hide();
    }

    if (val == 11) {
        $('#id_inicio').parent().parent().show();
        $('#id_termino').parent().parent().show();
    } else {
        $('#id_inicio').parent().parent().hide();
        $('#id_termino').parent().parent().hide();
    }
    
    if (val == 17 || val == 6) {
        $('input[name="diario"]').parent().parent().show();
    } else {
        $('input[name="diario"]').parent().parent().hide();
    }

}

jQuery(function () {
    $('#id_tipo').change(function () {
        checar_tipo();
    });

    $('#id_turno').parent().parent().parent().hide();
    $('input[name="curso_campus"]').parent().parent().parent().hide();
    $('input[name="turma"]').parent().parent().parent().hide();
    $('#id_inicio').parent().parent().hide();
    $('#id_termino').parent().parent().hide();
    $('input[name="diario"]').parent().parent().hide();
    checar_tipo();


});
