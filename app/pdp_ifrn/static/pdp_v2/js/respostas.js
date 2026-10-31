jQuery(document).ready(function(){

    var enfoque_outros = jQuery('.form-row.field-enfoque_outros');
    enfoque_outros.hide();

    function configuraVisibilidadeEnfoqueOutros() {
        if ($('#id_enfoque_desenvolvimento option:selected').text() === 'Outras não especificadas') {
            enfoque_outros.show();
        } else {
            $('#id_enfoque_outros').val('');
            enfoque_outros.hide();
        }
    }

    $("#id_enfoque_desenvolvimento").change(function() {
        configuraVisibilidadeEnfoqueOutros();
    });

    configuraVisibilidadeEnfoqueOutros();

});
