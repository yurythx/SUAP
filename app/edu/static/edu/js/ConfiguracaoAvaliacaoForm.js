function configurar() {
    var nota_max = 100;
    if($('#id_observacao').hasClass('notas-decimais')){
        nota_max = 10;
    }

    var forma_calculo = $('#id_forma_calculo').val();
    //Maior nota
    if (forma_calculo == 4) {
        $('.field-nota_maxima input').val(nota_max);
        $('.field-nota_maxima input').attr('readonly', 'readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().show();
    }
    //Média aritmética
    else if (forma_calculo == 2) {
        $('.field-nota_maxima input').val(nota_max);
        $('.field-nota_maxima input').attr('readonly', 'readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().show();
    }
    //Média ponderada
    else if (forma_calculo == 3) {
        $('.field-nota_maxima input').val(nota_max);
        $('.field-nota_maxima input').attr('readonly', 'readonly');
        if ($('.field-peso input').val() == ''){
        	$('.field-peso input').val(1);
        }
        $('.field-peso input').removeAttr('disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().hide();
        $('#id_maior_nota').prop('checked', false);
        $('#id_menor_nota').prop('checked', false);
    }
    //Soma com divisor
    else if (forma_calculo == 5) {
        $('.field-nota_maxima input').removeAttr('readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().show();
        $('#id_maior_nota').parent().parent().hide();
        $('#id_maior_nota').prop('checked', false);
        $('#id_menor_nota').prop('checked', false);
    }
    //Média Atitudinal
    else if (forma_calculo == 6) {
        $('.field-nota_maxima input').val(nota_max);
        $('.field-nota_maxima input').attr('readonly', 'readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().show();
    }
    //Soma simples
    else if (forma_calculo == 1) {
        $('.field-nota_maxima input').removeAttr('readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().hide();
        $('#id_maior_nota').prop('checked', false);
        $('#id_menor_nota').prop('checked', false);
    }
    // avaliacao por conceito
    else if (forma_calculo == 7) {
        $('.field-nota_maxima input').val(nota_max);
        $('.field-nota_maxima input').attr('readonly', 'readonly');
        $('.field-peso input').val('');
        $('.field-peso input').attr('disabled', 'disabled');
        $('#id_divisor').parent().hide();
        $('#id_maior_nota').parent().parent().hide();
        
    }
}


jQuery(function () {
    $('#id_forma_calculo').change(function () {
        configurar();
    });
    configurar();

});
