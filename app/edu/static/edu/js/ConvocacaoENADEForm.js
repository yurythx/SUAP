$(document).ready(function(){
    // Quando o valor do campo "Tipo de convocacao" mudar
    $("#id_tipo_convocacao").change(function() {
        // Verifique se a opção "Avaliação Teórica" (value=1) está selecionada
         if ($(this).val() == "1") {
            $(".field-data_inscricao").show();
            $(".field-data_inicio_inscricao").show();
            $(".field-data_inscricao_ingressantes").show();
        } else {
            $(".field-data_inscricao").hide();
            $(".field-data_inicio_inscricao").hide();
            $(".field-data_inscricao_ingressantes").hide();
        }
    });

    // Inicialmente, verifique o valor do tipo de convocacao
    $('#id_tipo_convocacao').trigger('change');

});
