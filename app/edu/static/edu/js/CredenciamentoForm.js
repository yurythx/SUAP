function atualizar_numero(primeiro_acesso) {

    var sem_numero = document.getElementById('id_sem_numero').checked;
    
    if(sem_numero == true){
        $('#id_numero_ato').val('S/N');
        $('#id_numero_ato').prop('readonly', true);
    }else{
        if (!primeiro_acesso){
            $('#id_numero_ato').val('');
        }
        $('#id_numero_ato').prop('readonly', false);
    }
}

jQuery(function () {
    $('#id_sem_numero').change(function () {
         atualizar_numero(false);
    });
    atualizar_numero(true);
});
