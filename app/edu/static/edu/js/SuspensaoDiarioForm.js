$(document).ready(function() {
    var selectJustificativa = $("select[name='justificativa']");
    var Motivo = $("#id_motivo");

    function toggleMotivoField() {
        var selectedOption = selectJustificativa.find("option:selected");
        if (selectedOption.val() === '8') {
            Motivo.parent().show();
        } else {
            Motivo.parent().hide();
        }
    }

    // Chama a função para configurar o estado inicial
    toggleMotivoField();

    // Adiciona um listener de evento para o campo justificativa
    selectJustificativa.change(toggleMotivoField);
});
