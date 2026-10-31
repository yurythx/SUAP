$(document).ready(function() {
    $("select#id_resposta_padrao").on("change", function () {
        $('#id_comentario').val($(this).val());
    })
});
