$(document).ready(function(){
    $("#id_tipo_relatorio").change(function() {
         if ($(this).val() == 1) {
            $("#id_tipo_busca").parent().parent().hide();
        } else {
            $("#id_tipo_busca").parent().parent().show();
        }
    });

    $('#id_tipo_relatorio').trigger('change');

});
