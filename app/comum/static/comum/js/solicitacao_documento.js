/***
 * [Aplicação: comum.DocumentoControle]
 *
 * função que chama uma view para popular novamente o campo de nome sugerido
 */

$( document ).ready(function() {
    $('select[name="solicitante_vinculo"]').change(function(){
        if($(this).val()) {
            $.ajax({
                type: "POST",
                url: '/comum/popula_nome_sugerido/',
                data: $('#documentocontrole_form').serialize(),
                success: function (retorno) {
                    var options = $("#id_nome_sugerido");
                    options.empty();
                    $.each(retorno.nomes, function (){
                        options.append($("<option />").val(this[0]).text(this[1]));
                    });
                }
            });
        } else {
            var options = $("#id_nome_sugerido");
            options.empty();
            options.append($("<option />").text('Selecione o solicitante'));
        }
    })
});
