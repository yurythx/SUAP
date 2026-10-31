$(document).ready(function(){
	$("select[name='projeto_pesquisa']").parent().parent().hide();
	$("select[name='projeto_extensao']").parent().parent().hide();
	if ($("input[name='tipo']:checked").val() == 'Pesquisa') {
        $("select[name='projeto_pesquisa']").parent().parent().show();
        $('label[for="id_projeto_pesquisa"]').addClass('required');

        $("select[name='projeto_extensao']").parent().parent().hide();
        $('label[for="id_projeto_extensao"]').removeClass('required');
    }
    else {

        $("select[name='projeto_extensao']").parent().parent().show();
        $('label[for="id_projeto_extensao"]').addClass('required');

        $("select[name='projeto_pesquisa']").parent().parent().hide();
        $('label[for="id_projeto_pesquisa"]').removeClass('required');
    }
	$('#id_tipo').on('change', function(){
        if ($("input[name='tipo']:checked").val() == 'Pesquisa') {
            $("select[name='projeto_pesquisa']").parent().parent().show();
            $('label[for="id_projeto_pesquisa"]').addClass('required');

            $("select[name='projeto_extensao']").parent().parent().hide();
            $('label[for="id_projeto_extensao"]').removeClass('required');
        }
        else {

            $("select[name='projeto_extensao']").parent().parent().show();
            $('label[for="id_projeto_extensao"]').addClass('required');

            $("select[name='projeto_pesquisa']").parent().parent().hide();
            $('label[for="id_projeto_pesquisa"]').removeClass('required');
        }
    });
});
