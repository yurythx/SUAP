$(document).ready(function(){

    // Quando o valor do campo "Nacionalidade" mudar
    $("#id_nacionalidade").change(function() {
        // Verifique se a opção "Estrangeiro" (value=4) está selecionada
         if ($(this).val() == "4") {
            $(".form-row.cpf").hide();
            $("#id_cpf").val('');
            $(".form-row.pais_origem").show();
            $(".form-row.passaporte").show();
        } else {
            $(".form-row.cpf").show();
            $("#id_passaporte").val('');
            $(".form-row.pais_origem").hide();
            $(".form-row.passaporte").hide();
        }
    });

    // Inicialmente, verifica o valor da nacionalidade
    $('#id_nacionalidade').trigger('change');

});
