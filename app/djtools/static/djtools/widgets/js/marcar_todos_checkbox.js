$(document).ready(function(){
	$('.checkbutton button').off('click.marcartodos').on('click.marcartodos', function () {
		var campo = $(this).attr("data-elemento");
		if ($(this).hasClass("markall")) {
			var checked = true;
			$(this).removeClass("markall");
			$(this).text("Desmarcar todos");
		} else {
			var checked = false;
			$(this).addClass("markall");
			$(this).text("Marcar todos");
		}
		$('input[name="'+campo+'"]').each(function(){
			if (checked) {
				$(this).prop('checked', true);	
			} else {
				$(this).prop('checked', false)
			}
		});	
		return false	
	});
});
