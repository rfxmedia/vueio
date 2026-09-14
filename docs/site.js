const toggle = document.querySelector('.menu-toggle');
const sidebar = document.querySelector('.sidebar');
toggle?.addEventListener('click', () => {
  const open = sidebar.classList.toggle('open');
  toggle.setAttribute('aria-expanded', String(open));
});
document.querySelectorAll('pre').forEach(pre => {
  const button = document.createElement('button');
  button.className = 'copy'; button.textContent = 'Copy';
  button.setAttribute('aria-label', 'Copy code');
  button.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(pre.querySelector('code').textContent);
      button.textContent = 'Copied';
      setTimeout(() => { button.textContent = 'Copy'; }, 1600);
    } catch { button.textContent = 'Select text'; }
  });
  pre.append(button);
});
const input = document.querySelector('.search');
const results = document.querySelector('.results');
let indexPromise;
input?.addEventListener('input', async () => {
  const query = input.value.trim().toLowerCase();
  results.replaceChildren(); results.hidden = !query;
  if (!query) return;
  try {
    indexPromise ??= fetch('search.json').then(r => {
      if (!r.ok) throw new Error('Search unavailable');
      return r.json();
    });
    const index = await indexPromise;
    if (query !== input.value.trim().toLowerCase()) return;
    const terms = query.split(/\s+/);
    const hits = index.filter(item => terms.every(term => item.text.toLowerCase().includes(term))).slice(0, 8);
    for (const hit of hits) {
      const a = document.createElement('a'); a.href = hit.url; a.textContent = hit.title;
      results.append(a);
    }
    if (!hits.length) { const p = document.createElement('p'); p.textContent = 'No matching sections. Try fewer words.'; results.append(p); }
  } catch {
    indexPromise = undefined;
    results.textContent = 'Search is unavailable. Browse the guides below.';
  }
});
