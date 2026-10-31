$(document).ready(function(){

    exibir_esconder_campo();

    $("#id_programa").on('change', function () {
        exibir_esconder_campo();
    });


});

function clearcidade() {
    $("select[name='municipio_origem']").val(null).trigger('change');
}

function clearmotivo() {
    $("select[name='motivo']").val(null).trigger('change');
}

function exibir_esconder_campo() {
    if ($('#id_programa').val()){
        texto = $('#id_programa').find('option:selected').text();
        const municipio = ["Apoio à Formação", "Alimentação Estudantil", "Transporte", "Auxílio Moradia"];
        const bolsas = ["Apoio à Formação", "Alimentação Estudantil", "Transporte"];
        if (texto.includes('Auxílio Moradia')) {
             $("select[name='municipio_origem']").parent().show();
        } else {
            $("select[name='municipio_origem']").parent().hide();
            var currentVal = $("select[name='municipio_origem']").val();
            if (currentVal !== null && currentVal.length > 0) {
                clearcidade();
            }

        }
        if (bolsas.some(item => texto.includes(item))){
             $("#id_bolsas").parent().show();
             $('#id_turno').parent().show();
        } else {
            $("#id_bolsas").parent().hide();
            $("#id_bolsas").val('');
            $('#id_turno').parent().hide();
            $("#id_turno").val('');

        }
        if (texto.includes('Apoio à Formação')) {
            $('#id_turno_disponibilidade').parent().show();

        } else {
            $('#id_turno_disponibilidade').parent().hide();
            $("#id_turno_disponibilidade").val('');
        }
        if (texto.includes('Alimentação Estudantil')) {

            $("select[name='motivo']").parent().show();
        } else {
            $("select[name='motivo']").parent().hide();
            var currentVal = $("select[name='motivo']").val();
            if (currentVal !== null && currentVal.length > 0) {
                clearmotivo();
            }
        }
    } else {
        $("select[name='municipio_origem']").parent().hide();
        $('#id_turno_disponibilidade').parent().hide();
        $('#id_turno').parent().hide();
        $('#id_bolsas').parent().hide();
        $("select[name='motivo']").parent().hide();
    }
}
