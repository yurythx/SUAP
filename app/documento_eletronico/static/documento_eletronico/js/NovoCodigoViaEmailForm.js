function enviar_codigo_verificacao_email(){
$.ajax({
    url: "/documento_eletronico/enviar_codigo_verificacao_email",
    type: "GET",
    data: { csrfmiddlewaretoken: '{{ csrf_token }}' , action: 'new_code'},
    success: function () {
        // something here on success
        window.location.reload();
    },
    error: function () {
       // something here on error
    }
});
}
