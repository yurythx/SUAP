
'use strict';
{
  const globals = this;
  const django = globals.django || (globals.django = {});

  
  django.pluralidx = function(n) {
    const v = (n == 0 || n == 1) ? 0 : n != 0 && n % 1000000 == 0 ? 1 : 2;
    if (typeof v === 'boolean') {
      return v ? 1 : 0;
    } else {
      return v;
    }
  };
  

  /* gettext library */

  django.catalog = django.catalog || {};
  
  const newcatalog = {
    "%(sel)s of %(cnt)s selected": [
      "%(sel)s de %(cnt)s selecionado",
      "%(sel)s de %(cnt)s selecionados",
      "%(sel)s de %(cnt)s selecionados"
    ],
    "%s selected option not visible": [
      "%s op\u00e7\u00e3o selecionada n\u00e3o vis\u00edvel",
      "%s op\u00e7\u00f5es selecionadas n\u00e3o vis\u00edveis",
      "%s op\u00e7\u00f5es selecionadas n\u00e3o vis\u00edveis"
    ],
    "(click to clear)": "(clique para limpar)",
    "6 a.m.": "6 da manh\u00e3",
    "6 p.m.": "6 da tarde",
    "April": "Abril",
    "August": "Agosto",
    "Available %s": "%s dispon\u00edveis",
    "Cancel": "Cancelar",
    "Choose %s by selecting them and then select the \"Choose\" arrow button.": "Escolha %s selecionando-os e depois selecione o bot\u00e3o de seta \"Escolher\".",
    "Choose a Date": "Escolha uma data",
    "Choose a Time": "Escolha um hor\u00e1rio",
    "Choose a time": "Escolha uma hora",
    "Choose all %s": "Escolher todos %s",
    "Choose selected %s": "Escolher selecionado(s) %s",
    "Chosen %s": "%s escolhido(s)",
    "December": "Dezembro",
    "February": "Fevereiro",
    "Filter": "Filtro",
    "Friday": "Sexta-feira",
    "January": "Janeiro",
    "July": "Julho",
    "June": "Junho",
    "March": "Mar\u00e7o",
    "May": "Maio",
    "Midnight": "Meia-noite",
    "Monday": "Segunda-feira",
    "Noon": "Meio-dia",
    "Note: You are %s hour ahead of server time.": [
      "Nota: Voc\u00ea est\u00e1 %s hora \u00e0 frente do hor\u00e1rio do servidor.",
      "Nota: Voc\u00ea est\u00e1 %s horas \u00e0 frente do hor\u00e1rio do servidor.",
      "Nota: Voc\u00ea est\u00e1 %s horas \u00e0 frente do hor\u00e1rio do servidor."
    ],
    "Note: You are %s hour behind server time.": [
      "Nota: Voc\u00ea est\u00e1 %s hora atr\u00e1s do tempo do servidor.",
      "Nota: Voc\u00ea est\u00e1 %s horas atr\u00e1s do hor\u00e1rio do servidor.",
      "Nota: Voc\u00ea est\u00e1 %s horas atr\u00e1s do hor\u00e1rio do servidor."
    ],
    "November": "Novembro",
    "Now": "Agora",
    "October": "Outubro",
    "Remove %s by selecting them and then select the \"Remove\" arrow button.": "Remova %s selecionando-os e depois selecione o bot\u00e3o de seta \"Remover\".",
    "Remove all %s": "Remover todos %s",
    "Remove selected %s": "Remover selecionado(s) %s",
    "Saturday": "S\u00e1bado",
    "September": "Setembro",
    "Sunday": "Domingo",
    "Thursday": "Quinta-feira",
    "Today": "Hoje",
    "Tomorrow": "Amanh\u00e3",
    "Tuesday": "Ter\u00e7a-feira",
    "Type into this box to filter down the list of available %s.": "Digite nessa caixa para filtrar a lista de %s dispon\u00edveis.",
    "Type into this box to filter down the list of selected %s.": "Digite nesta caixa para filtrar a lista de selecionados %s.",
    "Wednesday": "Quarta-feira",
    "Yesterday": "Ontem",
    "You have selected an action, and you haven\u2019t made any changes on individual fields. You\u2019re probably looking for the Go button rather than the Save button.": "Voc\u00ea selecionou uma a\u00e7\u00e3o sem fazer mudan\u00e7as nos campos individuais. Voc\u00ea provavelmente est\u00e1 procurando pelo bot\u00e3o Ir ao inv\u00e9s do bot\u00e3o Salvar.",
    "You have selected an action, but you haven\u2019t saved your changes to individual fields yet. Please click OK to save. You\u2019ll need to re-run the action.": "Voc\u00ea selecionou uma a\u00e7\u00e3o, mas voc\u00ea ainda n\u00e3o salvou suas altera\u00e7\u00f5es nos campos individuais. Por favor clique OK para salvar. voc\u00ea precisar\u00e1 de rodar novamente a a\u00e7\u00e3o.",
    "You have unsaved changes on individual editable fields. If you run an action, your unsaved changes will be lost.": "Voc\u00ea tem altera\u00e7\u00f5es n\u00e3o salvas em campos edit\u00e1veis individuais. Se voc\u00ea executar uma a\u00e7\u00e3o suas altera\u00e7\u00f5es n\u00e3o salvas ser\u00e3o perdidas.",
    "abbrev. day Friday\u0004Fri": "Sex",
    "abbrev. day Monday\u0004Mon": "Seg",
    "abbrev. day Saturday\u0004Sat": "S\u00e1b",
    "abbrev. day Sunday\u0004Sun": "Dom",
    "abbrev. day Thursday\u0004Thur": "Qui",
    "abbrev. day Tuesday\u0004Tue": "Ter",
    "abbrev. day Wednesday\u0004Wed": "Qua",
    "abbrev. month April\u0004Apr": "Abr",
    "abbrev. month August\u0004Aug": "Ago",
    "abbrev. month December\u0004Dec": "Dez",
    "abbrev. month February\u0004Feb": "Fev",
    "abbrev. month January\u0004Jan": "Jan",
    "abbrev. month July\u0004Jul": "Jul",
    "abbrev. month June\u0004Jun": "Jun",
    "abbrev. month March\u0004Mar": "Mar",
    "abbrev. month May\u0004May": "Mai",
    "abbrev. month November\u0004Nov": "Nov",
    "abbrev. month October\u0004Oct": "Out",
    "abbrev. month September\u0004Sep": "Set",
    "one letter Friday\u0004F": "S",
    "one letter Monday\u0004M": "S",
    "one letter Saturday\u0004S": "S",
    "one letter Sunday\u0004S": "D",
    "one letter Thursday\u0004T": "Q",
    "one letter Tuesday\u0004T": "T",
    "one letter Wednesday\u0004W": "Q"
  };
  for (const key in newcatalog) {
    django.catalog[key] = newcatalog[key];
  }
  

  if (!django.jsi18n_initialized) {
    django.gettext = function(msgid) {
      const value = django.catalog[msgid];
      if (typeof value === 'undefined') {
        return msgid;
      } else {
        return (typeof value === 'string') ? value : value[0];
      }
    };

    django.ngettext = function(singular, plural, count) {
      const value = django.catalog[singular];
      if (typeof value === 'undefined') {
        return (count == 1) ? singular : plural;
      } else {
        return value.constructor === Array ? value[django.pluralidx(count)] : value;
      }
    };

    django.gettext_noop = function(msgid) { return msgid; };

    django.pgettext = function(context, msgid) {
      let value = django.gettext(context + '\x04' + msgid);
      if (value.includes('\x04')) {
        value = msgid;
      }
      return value;
    };

    django.npgettext = function(context, singular, plural, count) {
      let value = django.ngettext(context + '\x04' + singular, context + '\x04' + plural, count);
      if (value.includes('\x04')) {
        value = django.ngettext(singular, plural, count);
      }
      return value;
    };

    django.interpolate = function(fmt, obj, named) {
      if (named) {
        return fmt.replace(/%\(\w+\)s/g, function(match){return String(obj[match.slice(2,-2)])});
      } else {
        return fmt.replace(/%s/g, function(match){return String(obj.shift())});
      }
    };


    /* formatting library */

    django.formats = {
    "DATETIME_FORMAT": "j \\d\\e F \\d\\e Y \u00e0\\s H:i",
    "DATETIME_INPUT_FORMATS": [
      "%d/%m/%Y %H:%M:%S",
      "%d/%m/%Y %H:%M:%S.%f",
      "%d/%m/%Y %H:%M",
      "%d/%m/%y %H:%M:%S",
      "%d/%m/%y %H:%M:%S.%f",
      "%d/%m/%y %H:%M",
      "%Y-%m-%d %H:%M:%S",
      "%Y-%m-%d %H:%M:%S.%f",
      "%Y-%m-%d %H:%M",
      "%Y-%m-%d"
    ],
    "DATE_FORMAT": "j \\d\\e F \\d\\e Y",
    "DATE_INPUT_FORMATS": [
      "%d/%m/%Y",
      "%d/%m/%y",
      "%Y-%m-%d"
    ],
    "DECIMAL_SEPARATOR": ",",
    "FIRST_DAY_OF_WEEK": 0,
    "MONTH_DAY_FORMAT": "j \\d\\e F",
    "NUMBER_GROUPING": 3,
    "SHORT_DATETIME_FORMAT": "d/m/Y H:i",
    "SHORT_DATE_FORMAT": "d/m/Y",
    "THOUSAND_SEPARATOR": ".",
    "TIME_FORMAT": "H:i",
    "TIME_INPUT_FORMATS": [
      "%H:%M:%S",
      "%H:%M:%S.%f",
      "%H:%M"
    ],
    "YEAR_MONTH_FORMAT": "F \\d\\e Y"
  };

    django.get_format = function(format_type) {
      const value = django.formats[format_type];
      if (typeof value === 'undefined') {
        return format_type;
      } else {
        return value;
      }
    };

    /* add to global namespace */
    globals.pluralidx = django.pluralidx;
    globals.gettext = django.gettext;
    globals.ngettext = django.ngettext;
    globals.gettext_noop = django.gettext_noop;
    globals.pgettext = django.pgettext;
    globals.npgettext = django.npgettext;
    globals.interpolate = django.interpolate;
    globals.get_format = django.get_format;

    django.jsi18n_initialized = true;
  }
};
