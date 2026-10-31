jQuery(document).ready(function () {
    $('#baseconhecimento_form').on('submit', function(){
        if (typeof tinymce !== 'undefined') {
            try {
                tinymce.triggerSave();
            } catch (e) {
                console.error('Erro ao sincronizar o editor TinyMCE:', e);
                $('#baseconhecimento_form_submit').removeAttr('disabled');
                $('#baseconhecimento_form_submit').val('Salvar');
                return false;
            }
        }
        if (typeof validarTodosOsEditores === 'function' && !validarTodosOsEditores()) {
            $('#baseconhecimento_form_submit').removeAttr('disabled');
            $('#baseconhecimento_form_submit').val('Salvar');
            return false;
        }
    });
    if ($('select#id_visibilidade').val() != "sigilosa") {
        $(".field-grupos_atendimento").hide();
    }
    $('select#id_visibilidade').on('change', function(){
        if ($(this).val() == "sigilosa") {
            $(".field-grupos_atendimento").show();
        } else {
            $(".field-grupos_atendimento").hide();
        }
    });

});
