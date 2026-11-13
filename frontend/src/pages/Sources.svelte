<script>
  // 2.2.0 : ce que Millésime date. Les scans tagués, plus les albums et les dossiers d'Immich choisis ici.
  // Un code couleur dit d'où vient chaque source : or = scans tagués, bleu = album, orange = dossier.
  import { api, pluriel, session } from '../lib/api.svelte.js'

  let d = $state(null)          // { tag, sources, albums, transhumance, choix? }
  let erreur = $state('')
  let dit = $state('')
  let occupe = $state(false)
  let ajout = $state(null)      // 'album' | 'dossier' : la liste de choix ouverte
  let cherche = $state('')
  let coches = $state(new Set())
  let nonDatees = $state('')
  let modele = $state('')

  const MOT = { album: 'Album', dossier: 'Dossier' }
  const plat = (t) => t.toLowerCase().normalize('NFD').replace(/\p{Mn}/gu, '')
  const proposes = $derived.by(() => {
    if (!ajout || !d?.choix) return []
    const liste = ajout === 'album' ? d.choix.albums.map((a) => ({ ref: a.id, nom: a.nom, detail: pluriel(a.nombre, 'photo') }))
                                    : d.choix.dossiers.map((c) => ({ ref: c, nom: c, detail: '' }))
    const mot = plat(cherche.trim())
    return mot ? liste.filter((x) => plat(x.nom).includes(mot)) : liste
  })

  function prendre(r) { d = { ...r, choix: r.choix ?? d?.choix }; nonDatees = r.albums.non_datees; modele = r.albums.modele }
  async function faire(appel, apres = '') {
    occupe = true; erreur = ''; dit = ''
    try { const r = await appel(); prendre(r); dit = r.message || apres } catch (e) { erreur = e.message }
    occupe = false
  }
  const charger = () => faire(() => api.get('/api/sources'))
  async function ouvrir(sorte) {
    if (ajout === sorte) { ajout = null; return }
    coches = new Set(); cherche = ''
    await faire(() => api.get('/api/sources?choix=true'))
    ajout = sorte
  }
  function cocher(ref) { const s = new Set(coches); s.has(ref) ? s.delete(ref) : s.add(ref); coches = s }
  async function ajouter() {
    const sorte = ajout
    await faire(() => api.post('/api/sources', { sorte, refs: [...coches] }), 'Ajouté. Les photos arrivent à la prochaine synchronisation.')
    if (!erreur) { ajout = null; await faire(() => api.post('/api/synchroniser').then(() => api.get('/api/sources')), 'Ajouté et synchronisé : les photos attendent le calcul sur le PC.') }
  }
  charger()
</script>

<section class="surface mt-4 p-4" aria-labelledby="titre-sources">
  <h2 id="titre-sources" class="text-lg font-semibold">Ce que Millésime date</h2>
  <p class="secondaire mt-1 text-sm">
    Les scans tagués, et les albums ou dossiers d'Immich que tu choisis ici. Toutes les photos d'une source choisie sont à dater.
    À la validation, une photo d'album ou de dossier reçoit sa date et le tag « Date estimée » ; elle n'est pas déplacée.
  </p>
  <p class="mt-3 flex flex-wrap gap-2" aria-label="Légende des couleurs">
    <span class="origine origine-tag">Scan tagué</span><span class="origine origine-album">Album</span><span class="origine origine-dossier">Dossier</span>
  </p>

  {#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}
  {#if dit}<p class="mt-3 text-sm" role="status">{dit}</p>{/if}

  {#if d}
    <ul class="mt-3 grid gap-2" aria-label="Sources">
      <li class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-filet px-3 py-2">
        <span class="origine origine-tag">Scan tagué</span>
        <span class="order-last min-w-0 basis-full break-words sm:order-none sm:basis-0 sm:flex-1">{d.tag.nom}</span>
        <span class="secondaire ml-auto text-sm">{d.tag.faites} sur {pluriel(d.tag.total, 'photo')} datées</span>
      </li>
      {#each d.sources as s (s.cle)}
        <li class="flex flex-wrap items-center gap-x-3 gap-y-1 rounded-lg border border-filet px-3 py-2">
          <span class="origine origine-{s.sorte}">{MOT[s.sorte]}</span>
          <span class="order-last min-w-0 basis-full break-words sm:order-none sm:basis-0 sm:flex-1" title={s.sorte === 'dossier' ? s.ref : ''}>{s.sorte === 'dossier' ? s.ref : s.nom}</span>
          <span class="secondaire ml-auto text-sm">{s.total ? `${s.faites} sur ${pluriel(s.total, 'photo')} datées` : 'pas encore lue'}</span>
          {#if s.sorte === 'dossier' && s.total > 0 && s.faites === s.total}
            {#if s.demandee_le}<span class="secondaire text-sm">demandé à Transhumance</span>
            {:else if d.transhumance}<button class="bouton" disabled={occupe} onclick={() => faire(() => api.post('/api/sources/demander', { cle: s.cle }))}>Demander le passage à Transhumance</button>
            {:else}<span class="secondaire text-sm">tout est daté : à faire passer dans Transhumance</span>{/if}
          {/if}
          <button class="bouton" disabled={occupe} aria-label={'Retirer ' + s.nom} onclick={() => faire(() => api.post('/api/sources/retirer', { cle: s.cle }), 'Retiré. Les photos déjà datées gardent leur date.')}>Retirer</button>
        </li>
      {/each}
    </ul>

    <div class="mt-3 flex flex-wrap gap-2">
      <button class="bouton" aria-expanded={ajout === 'album'} disabled={occupe} onclick={() => ouvrir('album')}>Ajouter des albums</button>
      <button class="bouton" aria-expanded={ajout === 'dossier'} disabled={occupe} onclick={() => ouvrir('dossier')}>Ajouter des dossiers</button>
    </div>

    {#if ajout}
      <div class="mt-3 rounded-lg border border-filet p-3" role="group" aria-label={ajout === 'album' ? 'Choisir des albums' : 'Choisir des dossiers'}>
        <label class="sr-only" for="cherche-source">Filtrer</label>
        <input id="cherche-source" class="champ" type="search" bind:value={cherche} placeholder={ajout === 'album' ? 'Filtrer les albums' : 'Filtrer les dossiers'} />
        {#if ajout === 'dossier'}<p class="secondaire mt-2 text-xs">Un dossier ne prend que les photos rangées directement dedans, pas celles de ses sous-dossiers : coche chaque sous-dossier voulu.</p>{/if}
        <ul class="mt-2 grid max-h-72 gap-1 overflow-y-auto">
          {#each proposes as x (x.ref)}
            <li><label class="flex min-h-11 cursor-pointer flex-wrap items-center gap-x-3 gap-y-1 rounded-md px-2 py-1.5 hover:bg-verre">
              <input type="checkbox" checked={coches.has(x.ref)} onchange={() => cocher(x.ref)} />
              <span class="origine origine-{ajout}">{MOT[ajout]}</span>
              <span class="order-last min-w-0 basis-full break-words sm:order-none sm:basis-0 sm:flex-1">{x.nom}</span>
              {#if x.detail}<span class="secondaire ml-auto text-sm">{x.detail}</span>{/if}
            </label></li>
          {:else}
            <li class="secondaire px-2 py-3 text-sm">{cherche.trim() ? 'Rien ne porte ce nom.' : ajout === 'album' ? 'Tous les albums sont déjà choisis.' : 'Immich ne connaît aucun autre dossier.'}</li>
          {/each}
        </ul>
        <div class="mt-3 flex flex-wrap gap-2">
          <button class="bouton bouton-principal" disabled={occupe || !coches.size} onclick={ajouter}>Ajouter ({coches.size})</button>
          <button class="bouton" onclick={() => (ajout = null)}>Fermer</button>
        </div>
      </div>
    {/if}
  {:else if !erreur}
    <p class="secondaire mt-3 text-sm">Chargement…</p>
  {/if}
</section>

{#if d}
  <section class="surface mt-4 p-4" aria-labelledby="titre-albums">
    <h2 id="titre-albums" class="text-lg font-semibold">Albums des scans tagués</h2>
    <p class="secondaire mt-1 text-sm">Un scan tagué quitte l'album des non datés pour l'album de son année quand tu le valides.
      {d.albums.depuis_la_stack ? 'Ces deux noms viennent pour l\'instant des variables de la stack ; enregistrés ici, ils passent devant.' : 'Réglés ici ; les variables de la stack ne servent plus.'}</p>
    <form class="mt-3 grid gap-3 sm:grid-cols-2" onsubmit={(e) => { e.preventDefault(); faire(() => api.post('/api/reglages/albums', { non_datees: nonDatees, modele }), 'Noms d\'albums enregistrés.') }}>
      <label class="grid gap-1 text-sm"><span>Album des scans non datés</span><input class="champ" bind:value={nonDatees} /></label>
      <label class="grid gap-1 text-sm"><span>Album par année (doit contenir {'{annee}'})</span><input class="champ" bind:value={modele} /></label>
      <p class="sm:col-span-2"><button class="bouton" type="submit" disabled={occupe || session.lecture_seule || (nonDatees === d.albums.non_datees && modele === d.albums.modele && !d.albums.depuis_la_stack)}>Enregistrer</button></p>
    </form>
  </section>
{/if}
