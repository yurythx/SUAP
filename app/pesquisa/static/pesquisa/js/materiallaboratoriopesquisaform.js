$(document).ready(function(){

    $("#id_descricao").parent().parent().hide();


	$('#id_adicionar_novo').on('change', function(){
    	if ($('#id_adicionar_novo').is(':checked')) {
            $("#id_descricao").parent().parent().show();
            $("select[name='material']").parent().parent().hide();
       } else {
            $("#id_descricao").parent().parent().hide();
            $("select[name='material']").parent().parent().show();
       }
	});



});
