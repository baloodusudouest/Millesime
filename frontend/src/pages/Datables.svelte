<script>
  // 2.6.0 : « Datables par le nom ». À gauche, les dossiers et albums dont le nom porte une date ;
  // à droite, les photos de celui qu'on choisit, et un bouton pour les dater toutes à cette date.
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
  <div class="cadre mt-5" class:ouvert={!!choisi}>
    <aside class="gauche" aria-label="Dossiers et albums">
      <p class="secondaire mb-2 text-sm">{groupes.length} dossier{groupes.length > 1 ? 's' : ''} ou album{groupes.length > 1 ? 's' : ''} · {total} photo{total > 1 ? 's' : ''}</p>
      <label class="sr-only" for="cherche-groupe">Chercher</label>
      <input id="cherche-groupe" type="search" bind:value={cherche} placeholder="Chercher un dossier, un album, une année" />
      <ul class="mt-2">
        {#each montres as g (g.cle)}
          <li>
            <button class="groupe" aria-pressed={choisi?.cle === g.cle} onclick={() => ouvrir(g)}>
              <span class="sorte" aria-hidden="true">{g.sorte === 'album' ? '▣' : '▤'}</span>
              <span class="min-w-0 flex-1">
                <span class="nom">{court(g)}</span>
                <span class="secondaire block text-xs">{g.sorte === 'album' ? 'Album' : 'Dossier'} · {dateDite(g.date)}</span>
              </span>
              <span class="n">{g.n}</span>
            </button>
          </li>
        {/each}
      </ul>
    </aside>

    <section class="droite" aria-label="Photos du dossier choisi">
      {#if !choisi}
        <p class="secondaire py-10 text-center">Choisis un dossier ou un album à gauche.</p>
      {:else}
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
  @media (min-width: 900px) { .cadre { grid-template-columns: 340px minmax(0, 1fr); } .retour-groupes { display: none; } }
  @media (max-width: 899px) { .cadre.ouvert .gauche { display: none; } .cadre:not(.ouvert) .droite { display: none; } }
  .gauche input { width: 100%; min-height: 2.75rem; padding: 0 0.75rem; border-radius: 0.6rem; border: 1px solid var(--color-filet); background: transparent; color: inherit; font: inherit; }
  .gauche ul { display: grid; gap: 0.35rem; max-height: 70dvh; overflow-y: auto; padding: 0; margin: 0.5rem 0 0; list-style: none; }
  .groupe { display: flex; align-items: center; gap: 0.6rem; width: 100%; min-height: 3.25rem; padding: 0.5rem 0.75rem; text-align: left; border: 1px solid var(--color-filet); border-radius: 0.75rem; background: var(--color-verre-2); color: inherit; }
  .groupe[aria-pressed='true'] { border-color: var(--color-or); box-shadow: inset 3px 0 0 var(--color-or); }
  .groupe .nom { display: block; overflow-wrap: anywhere; }
  .groupe .sorte { color: var(--color-or); }
  .groupe .n { font-variant-numeric: tabular-nums; font-weight: 600; }
  .grille { display: grid; gap: 0.6rem; grid-template-columns: repeat(auto-fill, minmax(8.5rem, 1fr)); padding: 0; margin: 0; list-style: none; }
  .vignette { display: block; width: 100%; padding: 0; border: 0; border-radius: 0.5rem; overflow: hidden; background: var(--color-verre-2); cursor: zoom-in; }
  .vignette img { display: block; width: 100%; aspect-ratio: 1; object-fit: cover; }
  .grand { position: fixed; inset: 0; z-index: 60; display: grid; place-items: center; padding: 1rem; }
  .grand .fond { position: absolute; inset: 0; border: 0; background: rgba(0, 0, 0, 0.88); }
  .grand img { position: relative; max-width: 100%; max-height: calc(100dvh - 5rem); object-fit: contain; pointer-events: none; }
  .grand .legende { position: relative; margin-top: 0.5rem; font-size: 0.85rem; }
</style>
