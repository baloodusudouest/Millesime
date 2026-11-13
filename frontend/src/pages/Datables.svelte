<script>
  // 2.6.0 : « Datables par le nom ». À gauche, les dossiers et albums dont le nom porte une date ;
  // à droite, les photos de celui qu'on choisit, et un bouton pour les dater toutes à cette date.
  // 2.7.2 : la date proposée est en face de chaque dossier, dans la liste ; on la vérifie et on la corrige là.
  import { api, apercu, session } from '../lib/api.svelte.js'

  const MOIS = ['janvier', 'février', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
  // « 1983-01 » → « janvier 1983 » ; « 1989/1992 » → « 1989 à 1992 »
  const dateDite = (d) => (d.includes('/') ? d.replace('/', ' à ') : d.length === 7 ? `${MOIS[+d.slice(5) - 1]} ${d.slice(0, 4)}` : d)
  // ce qui sera écrit dans Immich
  const ecrite = (d) => {
    if (d.includes('/')) { const [a, b] = d.split('/').map(Number); return `1er juillet ${Math.floor((a + b) / 2)}` }
    return d.length === 7 ? `15 ${dateDite(d)}` : `1er juillet ${d}`
  }
  const court = (g) => (g.sorte === 'album' ? g.nom : g.nom.split('/').filter(Boolean).slice(-2).join(' › '))

  let groupes = $state(null)
  let choisi = $state(null)
  let photos = $state([])
  let cherche = $state('')
  let erreur = $state('')
  let message = $state(null)       // { texte, lot }
  let occupe = $state(false)
  let confirme = $state(false)
  let grande = $state(null)
  // 2.7.0 : plusieurs dossiers ou albums cochés, chacun avec sa date (celle du nom, modifiable)
  let coches = $state({})            // clé → date tapée ('' : celle du nom)
  let confirmeSel = $state(false)
  const selection = $derived((groupes || []).filter((g) => g.cle in coches))
  const nSel = $derived(selection.reduce((n, g) => n + g.n, 0))
  // même lecture que le serveur : 1992 · 07/1992 · 1992-07 · 14/07/1992 · 1992-07-14 → « AAAA-MM-JJ » (null : illisible)
  function lue(t) {
    t = (t || '').trim()
    let m
    if ((m = /^(1[89]\d{2}|20\d{2})$/.exec(t))) return `${m[1]}-07-01`
    if ((m = /^(\d{1,2})[/.-](1[89]\d{2}|20\d{2})$/.exec(t))) return +m[1] >= 1 && +m[1] <= 12 ? `${m[2]}-${m[1].padStart(2, '0')}-15` : null
    if ((m = /^(1[89]\d{2}|20\d{2})-(\d{1,2})$/.exec(t))) return +m[2] >= 1 && +m[2] <= 12 ? `${m[1]}-${m[2].padStart(2, '0')}-15` : null
    let a, mo, j
    if ((m = /^(\d{1,2})[/.-](\d{1,2})[/.-](1[89]\d{2}|20\d{2})$/.exec(t))) [j, mo, a] = [m[1], m[2], m[3]]
    else if ((m = /^(1[89]\d{2}|20\d{2})-(\d{1,2})-(\d{1,2})$/.exec(t))) [a, mo, j] = [m[1], m[2], m[3]]
    else return null
    const d = new Date(Date.UTC(+a, +mo - 1, +j))
    return d.getUTCMonth() === +mo - 1 && d.getUTCDate() === +j ? d.toISOString().slice(0, 10) : null
  }
  const jourLisible = (iso) => { const [a, m, j] = iso.split('-'); return `${+j === 1 ? '1er' : +j} ${MOIS[+m - 1]} ${a}` }
  const ecriteSel = (g) => (coches[g.cle] ? (lue(coches[g.cle]) ? jourLisible(lue(coches[g.cle])) : null) : ecrite(g.date))
  const illisibles = $derived(selection.filter((g) => coches[g.cle] && !lue(coches[g.cle])).length)
  function cocher(g, oui) {
    const c = { ...coches }
    if (oui) c[g.cle] = ''
    else delete c[g.cle]
    coches = c
    confirmeSel = false
  }
  async function daterSelection() {
    if (!confirmeSel) { confirmeSel = true; return }
    confirmeSel = false
    occupe = true
    erreur = ''
    let lot = '', faites = 0
    const corps = Object.fromEntries(selection.map((g) => [g.cle, coches[g.cle] || null]))
    try {
      while (true) {
        const r = await api.post('/api/datables/dater', { groupes: corps, lot: lot || undefined, n: 100 })
        lot = r.lot
        faites += r.faites
        if (r.erreurs.length) { erreur = r.erreurs[0]; break }
        if (!r.faites || !r.restant) break
      }
      message = { texte: `${faites} photo${faites > 1 ? 's' : ''} datée${faites > 1 ? 's' : ''} dans ${selection.length} dossier${selection.length > 1 ? 's' : ''} ou album${selection.length > 1 ? 's' : ''}.`, lot }
      coches = {}
      choisi = null
      photos = []
      await charger()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  const plat = (t) => (t || '').toLowerCase().normalize('NFD').replace(/\p{Mn}/gu, '')
  const montres = $derived((groupes || []).filter((g) => !cherche.trim() || plat(g.nom + ' ' + g.date).includes(plat(cherche.trim()))))
  const total = $derived((groupes || []).reduce((n, g) => n + g.n, 0))

  async function charger() {
    try { groupes = await api.get('/api/datables/groupes') } catch (e) { erreur = e.message }
    if (choisi && !groupes?.some((g) => g.cle === choisi.cle)) { choisi = null; photos = [] }
  }
  charger()

  async function ouvrir(g) {
    choisi = g
    confirme = false
    photos = []
    try { photos = await api.get(`/api/datables/photos?cle=${encodeURIComponent(g.cle)}`) } catch (e) { erreur = e.message }
  }

  async function daterTout() {
    if (!confirme) { confirme = true; return }
    confirme = false
    occupe = true
    erreur = ''
    let lot = '', faites = 0
    try {
      while (true) {
        const r = await api.post('/api/datables/dater', { groupe: choisi.cle, lot: lot || undefined, n: 100 })
        lot = r.lot
        faites += r.faites
        if (r.erreurs.length) { erreur = r.erreurs[0]; break }
        if (!r.faites || !r.restant) break
      }
      message = { texte: `${faites} photo${faites > 1 ? 's' : ''} datée${faites > 1 ? 's' : ''} au ${ecrite(choisi.date)} (${court(choisi)}).`, lot }
      choisi = null
      photos = []
      await charger()
    } catch (e) { erreur = e.message }
    occupe = false
  }

  async function annulerLot() {
    occupe = true
    try {
      const r = await api.post(`/api/lots/${encodeURIComponent(message.lot)}/annuler`)
      message = { texte: `${r.annulees} datation${r.annulees > 1 ? 's' : ''} annulée${r.annulees > 1 ? 's' : ''}.` }
      if (r.erreurs.length) erreur = r.erreurs[0]
      await charger()
    } catch (e) { erreur = e.message }
    occupe = false
  }
</script>

<svelte:window onkeydown={(e) => { if (e.key === 'Escape') grande = null }} />

<h1 class="titre-page">Datables par le nom</h1>
<p class="secondaire mt-1 text-sm">Les dossiers et albums dont le nom porte une date, et leurs photos qui n'ont pas de visage pour les dater, ou dont les visages disent la même chose. Rien n'est écrit sans ton clic ; tout s'annule depuis le journal.</p>
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}
{#if message}
  <p class="surface mt-3 flex flex-wrap items-center gap-3 p-3 text-sm" role="status">
    {message.texte}
    {#if message.lot}<button class="bouton min-h-9" onclick={annulerLot} disabled={occupe}>Annuler</button>{/if}
  </p>
{/if}

{#if !groupes}
  <p class="secondaire mt-6">Chargement…</p>
{:else if !groupes.length}
  <p class="secondaire py-10 text-center">Aucun dossier ni album dont le nom date des photos encore à dater.</p>
{:else}
  <div class="cadre mt-5" class:ouvert={!!choisi} class:selection={selection.length > 0}>
    <aside class="gauche" aria-label="Dossiers et albums">
      <p class="secondaire mb-2 text-sm">{groupes.length} dossier{groupes.length > 1 ? 's' : ''} ou album{groupes.length > 1 ? 's' : ''} · {total} photo{total > 1 ? 's' : ''}</p>
      <label class="sr-only" for="cherche-groupe">Chercher</label>
      <input id="cherche-groupe" type="search" bind:value={cherche} placeholder="Chercher un dossier, un album, une année" />
      <div class="entete" aria-hidden="true"><span></span><span>Dossier ou album</span><span>Date proposée</span></div>
      <ul class="mt-1">
        {#each montres as g (g.cle)}
          <li class="ligne-groupe" class:cochee={g.cle in coches}>
            <input type="checkbox" class="coche" checked={g.cle in coches} onchange={(e) => cocher(g, e.currentTarget.checked)}
                   aria-label={'Choisir ' + court(g)} />
            <button class="groupe" aria-pressed={choisi?.cle === g.cle} onclick={() => ouvrir(g)}>
              <span class="sorte" aria-hidden="true">{g.sorte === 'album' ? '▣' : '▤'}</span>
              <span class="min-w-0 flex-1">
                <span class="nom">{court(g)}</span>
                <span class="secondaire block text-xs">{g.sorte === 'album' ? 'Album' : 'Dossier'} · {g.n} photo{g.n > 1 ? 's' : ''}</span>
              </span>
            </button>
            <span class="cote-date">
              {#if g.cle in coches}
                <input class="date" type="text" inputmode="numeric" placeholder={dateDite(g.date)} value={coches[g.cle]}
                       oninput={(e) => { coches = { ...coches, [g.cle]: e.currentTarget.value }; confirmeSel = false }}
                       aria-label={'Date pour ' + court(g)} aria-invalid={!!coches[g.cle] && !lue(coches[g.cle])} />
                <span class="ecrite" class:alerte={!ecriteSel(g)}>{ecriteSel(g) || 'date illisible'}</span>
              {:else}
                <span class="proposee">{dateDite(g.date)}</span>
              {/if}
            </span>
          </li>
        {/each}
      </ul>
    </aside>

    <section class="droite" aria-label="Photos du dossier choisi">
      {#if selection.length}
        <div class="surface mb-5 p-4" role="region" aria-label="Dossiers cochés">
          <h2 class="font-semibold">{selection.length} dossier{selection.length > 1 ? 's' : ''} ou album{selection.length > 1 ? 's' : ''} coché{selection.length > 1 ? 's' : ''} · {nSel} photo{nSel > 1 ? 's' : ''}</h2>
          <p class="secondaire text-sm">Chaque dossier coché prend la date écrite en face de lui dans la liste : celle de son nom, ou celle que tu tapes dans son champ (1992, 07/1992 ou 14/07/1992).</p>
          {#if illisibles}<p class="alerte mt-2 text-sm">{illisibles} date{illisibles > 1 ? 's' : ''} illisible{illisibles > 1 ? 's' : ''} : corrige-la dans la liste.</p>{/if}
          <div class="mt-3 flex flex-wrap gap-2">
            <button class="bouton bouton-confirmer" onclick={daterSelection} disabled={occupe || session.lecture_seule || illisibles > 0}>
              {occupe ? 'Datation…' : confirmeSel ? `Confirmer : dater ${nSel > 1 ? 'les ' + nSel + ' photos' : 'la photo'}` : `Dater ${nSel > 1 ? 'les ' + nSel + ' photos' : 'la photo'} ${selection.length > 1 ? 'des ' + selection.length + ' dossiers' : 'du dossier'}`}</button>
            <button class="bouton" onclick={() => { coches = {}; confirmeSel = false }} disabled={occupe}>Tout décocher</button>
          </div>
        </div>
      {/if}
      {#if !choisi && !selection.length}
        <p class="secondaire py-10 text-center">Choisis un dossier ou un album à gauche, ou coche-en plusieurs.</p>
      {:else if choisi}
        <button class="lien retour-groupes mb-2" onclick={() => (choisi = null)}>‹ Dossiers et albums</button>
        <h2 class="text-lg font-semibold" style="overflow-wrap:anywhere">{choisi.sorte === 'album' ? 'Album « ' + choisi.nom + ' »' : choisi.nom}</h2>
        <p class="secondaire text-sm">Date lue : {dateDite(choisi.date)} · {choisi.n} photo{choisi.n > 1 ? 's' : ''}{choisi.sans_visage < choisi.n ? ` (dont ${choisi.n - choisi.sans_visage} où les visages confirment)` : ''}</p>
        <button class="bouton bouton-confirmer mt-3" onclick={daterTout} disabled={occupe || session.lecture_seule}>
          {occupe ? 'Datation…' : confirme ? `Confirmer : dater les ${choisi.n} photos au ${ecrite(choisi.date)}` : `Dater toutes les photos à la date ${choisi.sorte === 'album' ? 'de l\'album' : 'du dossier'} (${dateDite(choisi.date)})`}
        </button>
        <ul class="grille mt-4" aria-label="Photos">
          {#each photos as p (p.asset_id)}
            <li>
              <button class="vignette" onclick={() => (grande = p)} aria-label={'Voir ' + p.fichier}>
                <img src={`/api/vignette/${p.asset_id}`} alt="" loading="lazy" />
              </button>
              <span class="secondaire block truncate text-xs">{p.fichier}</span>
            </li>
          {/each}
        </ul>
      {/if}
    </section>
  </div>
{/if}

{#if grande}
  <div class="grand" role="dialog" aria-modal="true" aria-label={grande.fichier}>
    <button class="fond" aria-label="Fermer" onclick={() => (grande = null)}></button>
    <img src={apercu(grande.asset_id)} alt={grande.fichier} />
    <p class="legende">{grande.fichier} · <a class="lien" href={'#dater'} onclick={() => (grande = null)}>Dater une par une</a></p>
  </div>
{/if}

<style>
  .cadre { display: grid; gap: 1rem; grid-template-columns: minmax(0, 1fr); }
  @media (min-width: 900px) { .cadre { grid-template-columns: minmax(30rem, 1fr) minmax(0, 1fr); } .retour-groupes { display: none; } }
  @media (max-width: 899px) {
    .cadre.ouvert .gauche { display: none; }
    .cadre:not(.ouvert):not(.selection) .droite { display: none; }
    .cadre.selection:not(.ouvert) .droite { order: -1; }   /* sur iPhone : les dossiers cochés au-dessus de la liste */
  }
  .gauche input[type="search"] { width: 100%; min-height: 2.75rem; padding: 0 0.75rem; border-radius: 0.6rem; border: 1px solid var(--color-filet); background: transparent; color: inherit; font: inherit; }
  .gauche ul { display: grid; gap: 0.35rem; max-height: 70dvh; overflow-y: auto; padding: 0; margin: 0.5rem 0 0; list-style: none; }
  .ligne-groupe, .entete { display: grid; grid-template-columns: 1.25rem minmax(0, 1fr) 9.5rem; align-items: center; gap: 0.5rem; }
  .entete { padding-right: 0.25rem; font-size: 0.75rem; color: var(--color-craie); }
  .cote-date { display: grid; gap: 0.15rem; min-width: 0; }
  .proposee { padding: 0 0.5rem; color: var(--color-craie); font-variant-numeric: tabular-nums; }
  .cochee .proposee, .cochee .ecrite { color: inherit; }
  .ecrite { padding: 0 0.15rem; font-size: 0.72rem; color: var(--color-craie); }
  .ecrite.alerte { color: var(--color-alerte, #e5484d); }
  .coche { width: 1.25rem; height: 1.25rem; flex: none; accent-color: var(--color-or); }
  .date { width: 100%; min-height: 2.5rem; padding: 0 0.5rem; border-radius: 0.5rem; border: 1px solid var(--color-filet); background: transparent; color: inherit; font: inherit; }
  .date[aria-invalid='true'] { border-color: var(--color-alerte, #e5484d); }
  .alerte { color: var(--color-alerte, #e5484d); }
  .groupe { display: flex; align-items: center; gap: 0.6rem; width: 100%; min-height: 3.25rem; padding: 0.5rem 0.75rem; text-align: left; border: 1px solid var(--color-filet); border-radius: 0.75rem; background: var(--color-verre-2); color: inherit; }
  .groupe[aria-pressed='true'] { border-color: var(--color-or); box-shadow: inset 3px 0 0 var(--color-or); }
  .groupe .nom { display: block; overflow-wrap: anywhere; }
  .groupe .sorte { color: var(--color-or); }
  .grille { display: grid; gap: 0.6rem; grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr)); padding: 0; margin: 0; list-style: none; }
  .vignette { display: block; width: 100%; padding: 0; border: 0; border-radius: 0.5rem; overflow: hidden; background: var(--color-verre-2); cursor: zoom-in; }
  .vignette img { display: block; width: 100%; aspect-ratio: 1; object-fit: cover; }
  .grand { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 1rem; }
  .grand .fond { position: absolute; inset: 0; border: 0; background: rgba(0, 0, 0, 0.88); }
  .grand img { position: relative; max-width: 100%; max-height: calc(100dvh - 5rem); object-fit: contain; pointer-events: none; }
  .grand .legende { position: relative; margin-top: 0.5rem; font-size: 0.85rem; }
</style>
