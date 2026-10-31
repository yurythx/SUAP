function popular_datafim() {
    let data = new Date($("#id_data_inicio").val());
    let dias =  parseInt($('#id_quantidade_dias').val()) - 1;
    // Data inválida: o teste anterior (data == 'Invalid Date') era frágil. Sem início
    // válido não há o que calcular.
    if (isNaN(data.getTime())) {
        $("#id_quantidade_dias").val(0);
        alert('Informe a Data de Início.');
        return;
    }
    // Quantidade de dias vazia/não numérica deixaria a data inválida e faria
    // toISOString() estourar "Invalid time value" (Sentry SUAP-TEZ).
    if (isNaN(dias)) {
        $("#id_data_fim").val('');
        return;
    }
    data.setDate(data.getDate() + dias);
    // Quantidade de dias absurda estoura o intervalo de Date: o resultado vira
    // "Invalid Date" e toISOString() lança "Invalid time value" (Sentry SUAP-V44).
    if (isNaN(data.getTime())) {
        $("#id_data_fim").val('');
        return;
    }
    $("#id_data_fim").val(data.toISOString().substring(0, 10));
}

jQuery(function () {
    $("#id_data_fim").attr('readonly', true);
    $('#id_quantidade_dias').on("input", function(){
        popular_datafim();
    });
});
