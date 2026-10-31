jQuery(function () {
    $('select[name="turma"]').parent().parent().hide();
    $('select[name="curso"]').parent().parent().hide();

    if ($('#id_tipo_0')[0].checked) {
        $('select[name="turma"]').parent().parent().show();
    }

    if ($('#id_tipo_1')[0].checked) {
        $('select[name="curso"]').parent().parent().show();
    }

    $('#id_tipo_0').click(function () {
        $('select[name="turma"]').parent().parent().show();
        $('select[name="curso"]').parent().parent().hide();
    });

    $('#id_tipo_1').click(function () {
        $('select[name="turma"]').parent().parent().hide();
        $('select[name="curso"]').parent().parent().show();
    });
});
