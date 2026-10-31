const menu = document.querySelector('.menu-button');
const backdrop = document.querySelector('.backdrop');

function alternarMenu(aberto) {
  document.body.classList.toggle('menu-open', aberto);
  menu.setAttribute('aria-expanded', String(aberto));
  menu.setAttribute('aria-label', aberto ? 'Fechar menu' : 'Abrir menu');
  if (aberto) document.querySelector('.sidebar a').focus();
}

menu.addEventListener('click', () => alternarMenu(!document.body.classList.contains('menu-open')));
backdrop.addEventListener('click', () => alternarMenu(false));
document.addEventListener('keydown', (event) => {
  if (event.key !== 'Escape' || !document.body.classList.contains('menu-open')) return;
  alternarMenu(false);
  menu.focus();
});

// A rolagem horizontal fica num invólucro: `display: block` na própria <table> apaga a semântica de tabela no Safari.
// ponytail: sem tabindex no invólucro; Chrome/Firefox já focam contêiner rolável, Safari não.
document.querySelectorAll('.documento table').forEach((tabela) => {
  const involucro = document.createElement('div');
  involucro.className = 'tabela';
  tabela.before(involucro);
  involucro.append(tabela);
});

// O leitor de tela ouve só a contagem, não a lista inteira a cada tecla.
const resultados = document.getElementById('mkdocs-search-results');
const consulta = document.getElementById('mkdocs-search-query');
const statusBusca = document.getElementById('busca-status');
new MutationObserver(() => {
  const total = resultados.querySelectorAll('article').length;
  if (!consulta.value.trim()) statusBusca.textContent = '';
  else if (total) statusBusca.textContent = `${total} ${total === 1 ? 'resultado' : 'resultados'}`;
  else statusBusca.textContent = resultados.dataset.noResultsText;
}).observe(resultados, { childList: true });
