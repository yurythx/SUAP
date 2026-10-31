$(document).ready(function(){
    $('.pills a').css('cursor','pointer');

    $('.pills a').click(function() {
	    pill_clicked = $(this);

	    data_pill = pill_clicked.parent().attr('data-pill');

	    if (data_pill == 'todos_itens') {
	        $('.pill').show('fast');
	    } else {
	        pill_div = $('#'+data_pill);
	        $('.pill').hide('fast');
	        pill_div.show('fast');
	    }

	    $('.pills .active').removeClass('active');
	    pill_clicked.parent().addClass('active');

	    return false;
    });
})