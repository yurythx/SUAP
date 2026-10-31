$( document ).ready(function() {
    var item = $('#id_item')
    var pontuacao = $("#id_pontuacao")
    console.log(typeof item.val())
    console.log(item.val().length)
    if (typeof item.val() === "string" && item.val().length === 0) {
        pontuacao.attr('disabled', true)
    }

    item.change(function() {
        var value = $(this).val();
        var help_text = $(this).next()
        console.log($('#id_item option:selected').html())
        var text_selected = $('#id_item option:selected').html();
        if (typeof value === "string" && value.length === 0) {
            pontuacao.attr('disabled', true)
            help_text.html("Selecione um item")
        } else if (value.length > 0){
            pontuacao.attr('disabled', false)
            help_text.html(text_selected)
        }
    });
    $("#id_avaliacao").parent().attr("style", "display:None")
    $("#id_responsavel").parent().attr("style", "display:None")
});
