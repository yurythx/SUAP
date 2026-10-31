$(document).ready(function(){

    $('.pre-visualizar').click(function (event) {
        event.preventDefault();
        csrf_token = $('input[name=csrfmiddlewaretoken]').val();

        form = new FormData();
        // O campo id_texto usa tinymce (não CKEDITOR); CKEDITOR não existe nesta
        // página (Sentry SUAP-V50). Lê do editor tinymce, com fallback ao textarea.
        var editorTexto = (typeof tinymce !== 'undefined') ? tinymce.get('id_texto') : null;
        form.append('texto', editorTexto ? editorTexto.getContent() : $('#id_texto').val());
        form.append('data', $('input[name=data]').val());
        form.append('tipo', window.location.pathname.split('/')[4]);

        $.ajax({
            headers: { "X-CSRFToken": csrf_token },
            url: '/saude/previsualizar_documento_prontuario/',
            data: form,
            processData: false,
            contentType: false,
            type: 'POST',
            xhrFields: {
                responseType: 'blob'
            },
            success: function (data) {
                var blob = new Blob([data], { type: 'application/pdf' });
                if (window.navigator && window.navigator.msSaveOrOpenBlob) {
                    window.navigator.msSaveOrOpenBlob(blob); // for IE
                } else {
                    var fileURL = URL.createObjectURL(blob);
                    window.open(fileURL);
                }
            }
        });
    });
})
