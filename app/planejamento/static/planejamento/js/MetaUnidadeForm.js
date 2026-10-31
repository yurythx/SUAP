function ocultarExibirForm() {
	$("#metaunidade_form").parent().toggle();
	$("#btn_cadastrar").toggle();
	$("#btn_reset_forms").toggle();
	$("#btn_associar_todos_campi").toggle();
}

function ocultarExibirFormEditar() {
	$("#metaunidade_form").parent().toggle();
	$("#btn_reset_form_edicao").toggle();
	$("#btn_cadastrar").toggle();
	$("#btn_associar_todos_campi").toggle();
}

function ocultarExibirFormTodosCampi(){
	$("#metaunidadetodoscampi_form").parent().toggle();
	$("#btn_cadastrar").toggle();
	$("#btn_associar_todos_campi").toggle();
	$("#btn_reset_form_todos_campi").toggle();
}

$(document).ready(function(){
	$("#btn_cadastrar").click(function(){
		ocultarExibirForm();
	});
	
	$("#btn_reset_forms").click(function(){
		ocultarExibirForm();
	});
	
	$("#btn_reset_form_edicao").click(function(){
		ocultarExibirFormEditar();
	});
	
	$("#btn_associar_todos_campi").click(function(){
		ocultarExibirFormTodosCampi();
	})
	
	$("#btn_reset_form_todos_campi").click(function(){
		ocultarExibirFormTodosCampi();
	})
})

