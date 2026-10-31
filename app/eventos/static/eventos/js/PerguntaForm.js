$(document).ready(function(){

    // Adicionar Campo Numerico
    ativaCampoNumerico($('#id_tipo_pergunta').val());
    $('#id_tipo_pergunta').on('change', function(){
        ativaCampoNumerico($(this).val());
    });

});

function ativaCampoNumerico(tipo) {
    if (tipo == 'SUB_C') {
        $('.form-row.numerico').show();
    } else {
        $('.form-row.numerico').hide();
    }
}
