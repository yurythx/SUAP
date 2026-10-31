$(document).ready(function(){

    verifica_etapa($('#id_etapa').val());
    $('#id_etapa').on('change', function(){
        verifica_etapa($(this).val());
    });

});

function verifica_etapa(etapa) {
    if (etapa == 'REF') {
        $('.form-row.data_fim').hide();
    } else {
        $('.form-row.data_fim').show();
    }
}
