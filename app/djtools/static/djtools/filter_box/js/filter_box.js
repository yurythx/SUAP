$(document).ready(function(){
	$("div.filter_box > input[name=expansible]").each(function() {
		if ($(this).val() == 'True') {
			$(this).parent().find("h3.title").css('cursor','pointer');
		}
	})
	
	$("div.filter_box > h3.title").click(function() {
	  elem = $(this);
	  if (elem.parent().find('input[name=expansible]').val() == 'True') {
	  	if (elem.next().is(":visible")) {
	  		elem.next().hide('fast');
	  		elem.find("img").attr("src", "/static/djtools/filter_box/img/plus.png");
	  	}
	  	else {
	  		elem.next().show('fast');
	  		elem.find("img").attr("src", "/static/djtools/filter_box/img/minus.png");
	  	}
	  }
	})
	
	// omite a caixa com informações
	el = $("div.filter_box > h3.collapsed").next().css('display','none');
})