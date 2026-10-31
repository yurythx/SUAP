jQuery(document).ready(function() {
    CKEDITOR.replace( 'id_cabecalho', {
        toolbar: CKEDITOR_TOOLBAR,
        extraPlugins: 'base64image',
        removePlugins: 'maximize,resize,elementspath',
        height: 410
    } );
    CKEDITOR.replace( 'id_rodape', {
        toolbar: CKEDITOR_TOOLBAR,
        extraPlugins: 'base64image',
        removePlugins: 'maximize,resize,elementspath',
        height: 410
    } );
    $('#tipodocumento_form').on('submit', function(){
        if (!validarTags()) {
            $('.submit-row input[type=submit]').removeAttr('disabled');
            var input = $('.submit-row input[type=submit]')[0];
            input.value = 'Salvar';
            return false;

        }
    });
});