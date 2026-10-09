// Odświeżanie na żywo: elementy z data-live są co 3 s podmieniane świeżą wersją z serwera.
// Komunikat „Zapisano / Gotowe” jest jednorazowy: znika z adresu, żeby nie wracał przy odświeżeniu
if (location.search.includes('msg=')) {
  const u = new URL(location.href); u.searchParams.delete('msg'); history.replaceState(null, '', u);
}
const live = () => document.querySelectorAll('[data-live]');
const toBottom = () => document.querySelectorAll('[data-live=bottom]').forEach(el => el.scrollTop = el.scrollHeight);
toBottom();
if (live().length) setInterval(async () => {
  try {
    // schowana karta pyta o neutralną stronę: otwarta rozmowa nie może oznaczać wiadomości jako przeczytanych,
    // gdy nikt na nią nie patrzy
    const html = await (await fetch(document.hidden ? '/pomoc/limit' : location.href)).text();
    const doc = new DOMParser().parseFromString(html, 'text/html');
    incoming(doc.body);
    live().forEach(el => {
      const fresh = doc.getElementById(el.id);
      if (fresh && fresh.innerHTML !== el.innerHTML) { el.innerHTML = fresh.innerHTML; toBottom(); }
    });
  } catch (e) {   // panel zamknięty: nie udawaj, że połączenie jest nadal sprawdzane
    const stan = document.getElementById('stan');
    if (stan) stan.innerHTML = '<span class="dot grey"></span> Panel jest wyłączony – uruchom go ponownie';
  }
}, 3000);

const $ = id => document.getElementById(id);

// Powiadomienia Windows o nowych wiadomościach: włączane w Ustawieniach, zapamiętane w tej przeglądarce
const mem = (k, v) => {
  try { return v === undefined ? localStorage.getItem(k) : localStorage.setItem(k, v); } catch (e) { return null; }
};
const notifyOn = () => 'Notification' in window && Notification.permission === 'granted' && mem('powiadomienia') !== '0';
function incoming(b) {
  const id = +b.dataset.ostatnia, seen = mem('ostatnia');
  if (seen !== null && id > +seen && notifyOn()) {
    // tag: kilka otwartych kart panelu pokaże jeden dymek, nie kilka
    const n = new Notification('Panel SMS – nowa wiadomość', { body: 'Od: ' + b.dataset.od, tag: 'sms-' + id });
    n.onclick = () => { window.focus(); location.href = '/skrzynka?tel=' + encodeURIComponent(b.dataset.tel); };
  }
  if (seen === null || id > +seen) mem('ostatnia', id);
}
incoming(document.body);
const pow = $('pow-wlacz');
if (pow) {
  const stan = asked => {
    const sup = 'Notification' in window, denied = sup && Notification.permission === 'denied', on = notifyOn();
    $('pow-stan').className = on ? 'ok' : !sup || denied || (asked && Notification.permission !== 'granted') ? 'error' : '';
    $('pow-stan').textContent = !sup ? 'Ta przeglądarka nie potrafi pokazywać powiadomień. Otwórz panel w Chrome albo Edge.'
      : denied ? 'Przeglądarka blokuje powiadomienia z panelu. Kliknij ikonę obok adresu strony (na lewo od 127.0.0.1), ' +
                 'przy „Powiadomienia” wybierz „Zezwalaj” i odśwież stronę.'
      : on ? 'Powiadomienia są włączone.'
      : asked && Notification.permission !== 'granted' ? 'Przeglądarka nie dała zgody. Jeśli pytanie się nie pokazało, ' +
        'kliknij ikonę obok adresu strony (na lewo od 127.0.0.1), przy „Powiadomienia” wybierz „Zezwalaj” i odśwież stronę.'
      : 'Powiadomienia są wyłączone.';
    pow.textContent = on ? 'Wyłącz powiadomienia' : 'Włącz powiadomienia';
    pow.className = on ? 'btn' : 'btn primary';
    pow.disabled = !sup || denied; $('pow-probne').hidden = !on;
  };
  pow.addEventListener('click', async () => {
    if (notifyOn()) mem('powiadomienia', '0');
    else if (await Notification.requestPermission() === 'granted') mem('powiadomienia', '1');
    stan(true);
  });
  $('pow-probne').addEventListener('click', () =>
    new Notification('Panel SMS – nowa wiadomość', { body: 'Od: Anna Nowak (to tylko próba)' }));
  stan();
}

// Ustawienia: pokaż/ukryj hasło i test połączenia
$('pokaz')?.addEventListener('click', e => {
  const show = $('haslo').type === 'password';
  $('haslo').type = show ? 'text' : 'password';
  e.target.textContent = show ? 'Ukryj hasło' : 'Pokaż hasło';
});
$('sprawdz')?.addEventListener('click', async e => {
  const out = $('wynik');
  out.className = 'info busy'; out.textContent = 'Łączę z telefonem… (to może potrwać do 10 sekund)';
  e.target.disabled = true;
  try {
    const r = await (await fetch('/ustawienia/test', { method: 'POST', body: new FormData($('ustawienia')) })).json();
    out.className = r.ok ? 'ok' : 'error'; out.textContent = r.message;
  } catch (err) {
    out.className = 'error'; out.textContent = 'Panel nie odpowiada. Zamknij okno „Panel SMS” i uruchom panel ponownie.';
  }
  e.target.disabled = false;
});

$('ustawienia')?.addEventListener('submit', () => {
  const out = $('wynik');
  out.className = 'info busy'; out.textContent = 'Łączę z telefonem i zapisuję… (to może potrwać do 10 sekund)';
  setTimeout(() => $('ustawienia').querySelectorAll('button').forEach(b => b.disabled = true));
});

// Wyszukiwarki list (data-filter = co filtrować) i „zaznacz wszystkich” (data-all = które pola)
document.querySelectorAll('[data-filter]').forEach(inp => inp.addEventListener('input', () => {
  const q = inp.value.toLowerCase();
  document.querySelectorAll(inp.dataset.filter).forEach(el => el.hidden = !el.textContent.toLowerCase().includes(q));
}));
document.querySelectorAll('[data-all]').forEach(box => box.addEventListener('change', () =>
  document.querySelectorAll(box.dataset.all).forEach(c => c.checked = box.checked)));

// Nowa wysyłka: kroki 1 i 2 na jednej stronie, licznik odbiorców, licznik SMS-ów, wstawianie imienia
const form = $('wysylka');
if (form) {
  const tresc = $('tresc');
  const people = () => {   // osoby zaznaczone pojedynczo albo przez grupę, bez powtórzeń i bez „nie wysyłaj”
    const groups = [...form.querySelectorAll('[name=grupy]:checked')].map(g => g.value);
    return [...form.querySelectorAll('[name=osoby]:not(:disabled)')]
      .filter(o => o.checked || o.dataset.g.split(',').some(g => groups.includes(g))).length;
  };
  const count = () => {
    const n = people();
    const text = n ? `– wybrano osób: ${n}` : '– nikogo jeszcze nie wybrano';
    $('ile-osob').textContent = text; $('ile-osob-2').textContent = n ? `do ${n} ${n === 1 ? 'osoby' : 'osób'}` : '';
    if (n) $('brak-osob').hidden = true;
    return n;
  };
  const show = step => {
    form.querySelectorAll('[data-step]').forEach(el => el.hidden = el.dataset.step != step);
    document.querySelectorAll('[data-step-mark]').forEach(li => {
      const i = +li.dataset.stepMark;
      li.className = i < step ? 'done' : i == step ? 'now' : '';
      i == step ? li.setAttribute('aria-current', 'step') : li.removeAttribute('aria-current');
    });
    if (step == 2) tresc.focus();
  };
  form.querySelectorAll('[data-go]').forEach(b => b.addEventListener('click', () => {
    if (b.dataset.go == 2 && !count()) { $('brak-osob').hidden = false; return; }
    show(b.dataset.go);
  }));
  form.addEventListener('change', count);
  count(); show(form.dataset.start);

  let timer;
  const segments = () => { clearTimeout(timer); timer = setTimeout(async () => {
    try {
      const r = await fetch('/wysylka/licz', { method: 'POST', body: new URLSearchParams({ body: tresc.value, bez_pl: $('bez_pl').checked ? '1' : '' }) });
      $('licznik').textContent = (await r.json()).text;
    } catch (e) { /* licznik jest tylko podpowiedzią */ }
  }, 300); };
  tresc.addEventListener('input', segments); $('bez_pl').addEventListener('change', segments); segments();
  form.querySelectorAll('[data-insert]').forEach(b => b.addEventListener('click', () => {
    tresc.setRangeText(b.dataset.insert, tresc.selectionStart, tresc.selectionEnd, 'end'); tresc.focus(); segments();
  }));
  $('szablon')?.addEventListener('change', e => { if (e.target.value) { tresc.value = e.target.value; segments(); } });
}

// Import: wybór grupy – kliknięcie istniejącej albo wpisanie nowej; pod polem widać, co się stanie
const pole = $('grupa');
if (pole) {
  const chips = [...document.querySelectorAll('[data-grupa]')];
  const stan = () => {
    const v = pole.value.trim().toLowerCase();
    const hit = chips.find(c => c.dataset.grupa.toLowerCase() === v);
    chips.forEach(c => { c.classList.toggle('on', c === hit); c.setAttribute('aria-pressed', c === hit); });
    $('grupa-stan').className = v ? (hit ? 'info' : 'ok') : '';
    $('grupa-stan').textContent = !v ? 'Puste pole = osoby nie trafią do żadnej dodatkowej grupy.'
      : hit ? `Osoby z pliku zostaną dopisane do istniejącej grupy „${hit.dataset.grupa}”.`
      : `Powstanie nowa grupa „${pole.value.trim()}”.`;
  };
  chips.forEach(c => c.addEventListener('click', () => {
    pole.value = c.classList.contains('on') ? '' : c.dataset.grupa; stan();
  }));
  pole.addEventListener('input', stan); stan();
}

// Odpowiedź: Enter wysyła, Shift+Enter robi nową linię
document.querySelector('.reply textarea')?.addEventListener('keydown', e => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); e.target.form.requestSubmit(); }
});
