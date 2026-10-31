$(document).ready(function() {
    const $trigger = $('#id_deseja_alterar_interesse_custeio');
    const $targetWrapper = $('#id_motivo_alteracao_interesse_custeio').parent().parent();
    const $targetInput = $('#id_motivo_alteracao_interesse_custeio');

    function toggleMotivoField() {
        if ($trigger.is(':checked')) {
            $targetWrapper.show();
            $targetWrapper.addClass("required");
            $targetInput.prop("required", true);
        } else {
            $targetInput.val("");
            $targetWrapper.hide();
            $targetWrapper.removeClass("required");
            $targetInput.prop("required", false);
        }
    }

    $trigger.on('change', toggleMotivoField);
    toggleMotivoField();
});
