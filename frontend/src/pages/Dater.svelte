<script>
  import { untrack } from 'svelte'
  import { api, apercu, dateJour, session, versImmich, visage } from '../lib/api.svelte.js'
  import Frise from '../components/Frise.svelte'
  import NommerGroupe from '../components/NommerGroupe.svelte'
  import Visionneuse from '../components/Visionneuse.svelte'

  let { statut } = $props()
  let tous = $state([])          // la liste lue ; « liste » est ce que les filtres en gardent
  let position = $state(0)
  // 2.3.0 : filtres par dossier (un dossier parent garde ses sous-dossiers) et par nom (fichier, dossier, personnes)
  let dossier = $state('')
  let cherche = $state('')
  const plat = (t) => (t || '').toLowerCase().normalize('NFD').replace(/\p{Mn}/gu, '')
  const dossierDe = (c) => (c || '').split('/').slice(0, -1).join('/')
  const liste = $derived.by(() => {
    const mot = plat(cherche.trim())
    return tous.filter((x) => (!dossier || (dossierDe(x.chemin) + '/').startsWith(dossier + '/'))
      && (!mot || plat(x.chemin).includes(mot) || x.noms.some((n) => plat(n).includes(mot))))
  })
  // L'arbre : chaque dossier et chacun de ses parents, avec le nombre de photos qu'il contient (sous-dossiers compris)
  const arbre = $derived.by(() => {
    const n = new Map()
    for (const x of tous) {
      const parts = dossierDe(x.chemin).split('/').filter(Boolean)
      for (let i = 1; i <= parts.length; i++) { const k = '/' + parts.slice(0, i).join('/'); n.set(k, (n.get(k) || 0) + 1) }
    }
    const cles = [...n.keys()].sort((a, b) => a.localeCompare(b, 'fr'))
    // les premiers niveaux communs à tout (/data, /synologyphotos…) ne disent rien : on les saute
    const total = tous.length
    const utiles = cles.filter((k) => n.get(k) < total || cles.every((c) => c === k || !c.startsWith(k + '/')))
    const base = utiles.length ? Math.min(...utiles.map((k) => k.split('/').length)) : 0
    return utiles.map((k) => ({ cle: k, nom: k.split('/').pop(), niveau: k.split('/').length - base, nombre: n.get(k) }))
  })
  $effect(() => { dossier; cherche; untrack(() => { position = 0; chargerScan() }) })
  let s = $state(null)
  let annee = $state(null)
  let marge = $state(2)
  let confirmer = $state(false)
  let occupe = $state(false)
  let erreur = $state('')
  let message = $state(null)   // { texte, journal }
  // libellé court sur la photo pour un visage sans nom
  const ETATS = { non_attribue: 'non attribué', masque: 'personne masquée', supprime: 'retiré d’Immich', groupe_sans_nom: 'sans nom' }
  let suggestions = $state([])
  let grand = $state(null)
  let zoneNommer = $state(null)

  api.get('/api/nommer/suggestions').then((r) => (suggestions = r)).catch(() => {})

  let relecture = $state(false)
  async function relire() {
    relecture = true
    erreur = ''
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/actualiser`)
      const parts = []
      if (r.nouveaux) parts.push(`${r.nouveaux} nouveau${r.nouveaux > 1 ? 'x' : ''} visage${r.nouveaux > 1 ? 's' : ''}`)
      if (r.changes) parts.push(`${r.changes} visage${r.changes > 1 ? 's' : ''} mis à jour`)
      if (r.retires) parts.push(`${r.retires} retiré${r.retires > 1 ? 's' : ''}`)
      let texte = parts.length ? `Photo relue : ${parts.join(', ')}.` : 'Photo relue : rien n’a changé dans Immich.'
      if (r.a_calculer) texte += ` ${r.a_calculer} visage${r.a_calculer > 1 ? 's' : ''} à analyser sur le PC.`
      message = { texte }
      s = await api.get(`/api/scans/${s.asset_id}`)
    } catch (e) { erreur = e.message }
    relecture = false
  }

  async function apresNommage(m) {
    if (m) message = m
    suggestions = await api.get('/api/nommer/suggestions').catch(() => suggestions)
    s = await api.get(`/api/scans/${s.asset_id}`)
  }

  async function chargerListe() {
    erreur = ''
    tous = await api.get(`/api/scans?statut=${statut}`)
    position = 0
    await chargerScan()
  }
  let demande = 0     // 2.6.0 : une réponse arrivée après un changement de filtre ne doit pas réafficher l'ancienne photo
  async function chargerScan() {
    const ici = ++demande
    s = null
    confirmer = false
    if (!liste.length || position >= liste.length) return
    const lu = await api.get(`/api/scans/${liste[position].asset_id}`)
    if (ici !== demande) return
    s = lu
    const anneesVisages = (s.details.visages || []).map((v) => v.annee)
    annee = s.annee_proposee ?? (anneesVisages.length ? Math.floor(anneesVisages[0]) : s.details?.voisins?.mediane ?? 1990)
    marge = s.marge ?? 3
  }
  $effect(() => { statut; chargerListe().catch((e) => (erreur = e.message)) })

  const parFace = $derived(Object.fromEntries((s?.details?.visages || []).map((v) => [v.face_id, v])))
  const personnes = $derived((s?.details?.visages || []).filter((v) => v.person_id))
  const modifie = $derived(s && (annee !== s.annee_proposee || marge !== s.marge))
  const haute = $derived(s?.annee_envoi || new Date().getFullYear())

  function changer(d) { annee = Math.min(haute, annee + d); confirmer = false }
  function changerMarge(d) { marge = Math.max(0, Math.min(10, marge + d)); confirmer = false }

  async function valider() {
    if (marge > 2 && !confirmer) { confirmer = true; return }
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/valider`, { annee, marge })
      message = { texte: `Datée ${annee} ±${marge}` + (r.album ? `, rangée dans « ${r.album} ».` : ', laissée à sa place.') + (r.demande ? ' ' + r.demande : ''), journal: r.journal }
      retirer()
      await chargerScan()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  // retire de la liste la photo traitée (la liste filtrée suit)
  function retirer() { const id = liste[position]?.asset_id; tous = tous.filter((x) => x.asset_id !== id) }
  // 2.5.0 : « Tout dater d'un coup » pour les photos datables par le nom, par lots de 100, annulable d'un geste
  let lot = $state('')
  let enLot = $state(false)
  let confirmeLot = $state(false)
  let confirmeAnnuler = $state(false)
  let faitesLot = $state(0)
  let restantLot = $state(0)
  async function toutDater() {
    if (!confirmeLot) { confirmeLot = true; return }
    confirmeLot = false
    enLot = true
    erreur = ''
    faitesLot = 0
    lot = ''
    try {
      while (true) {
        const r = await api.post('/api/datables/dater', { lot: lot || undefined, n: 100 })
        lot = r.lot
        faitesLot += r.faites
        restantLot = r.restant
        if (r.erreurs.length) { erreur = r.erreurs[0]; break }
        if (!r.faites || !r.restant) break
      }
    } catch (e) { erreur = e.message }
    enLot = false
    await chargerListe()
  }
  async function annulerLot() {
    if (!confirmeAnnuler) { confirmeAnnuler = true; return }
    confirmeAnnuler = false
    occupe = true
    try {
      const r = await api.post(`/api/lots/${encodeURIComponent(lot)}/annuler`)
      message = { texte: `${r.annulees} datation${r.annulees > 1 ? 's' : ''} annulée${r.annulees > 1 ? 's' : ''}.` }
      if (r.erreurs.length) erreur = r.erreurs[0]
      lot = ''
      faitesLot = 0
      await chargerListe()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  // 2.3.0 : « ce n'est pas cette personne » — le visage est retiré de la personne dans Immich (annulable)
  let pasElle = $state(null)   // face_id en attente de confirmation
  async function detacher(v) {
    if (pasElle !== v.face_id) { pasElle = v.face_id; return }
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/visages/${v.face_id}/detacher`)
      message = { texte: `Visage retiré de ${r.nom || 'la personne'} dans Immich : il devient un groupe sans nom, à nommer.`, journal: r.journal }
      pasElle = null
      s = await api.get(`/api/scans/${s.asset_id}`)
    } catch (e) { erreur = e.message }
    occupe = false
  }
  // 2.2.0 : la photo a déjà une date. On la garde (rien n'est écrit), ou on prend celle du nom du fichier.
  async function garder(laquelle) {
    occupe = true
    erreur = ''
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/garder`, { laquelle })
      message = { texte: (laquelle === 'dossier' ? `Datée du ${dateJour(r.date_gardee)}, d'après le dossier.` : laquelle === 'nom' ? `Datée du ${dateJour(r.date_gardee)}, d'après le nom du fichier.` : `Date d'Immich gardée (${dateJour(r.date_gardee)}) : rien n'a été écrit.`) + (r.demande ? ' ' + r.demande : ''), journal: r.journal }
      retirer()
      await chargerScan()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  async function plusieurs() {
    occupe = true
    try {
      const r = await api.post(`/api/scans/${s.asset_id}/plusieurs`)
      message = { texte: 'Mise de côté : plusieurs années sur ce scan.', journal: r.journal }
      retirer()
      await chargerScan()
    } catch (e) { erreur = e.message }
    occupe = false
  }
  function passer() { position = (position + 1) % Math.max(1, liste.length); chargerScan() }
  async function annuler() {
    try {
      await api.post(`/api/journal/${message.journal}/annuler`)
      message = null
      await chargerListe()
    } catch (e) { erreur = e.message }
  }
</script>

{#if message}
  <div class="surface mb-4 flex items-center gap-3 p-3" role="status">
    <p class="flex-1 text-sm">{message.texte}</p>
    {#if message.journal}<button class="bouton" onclick={annuler}>Annuler</button>{/if}
    <button class="secondaire px-2" onclick={() => (message = null)} aria-label="Fermer">✕</button>
  </div>
{/if}
{#if erreur}<p class="mb-4 text-alerte" role="alert">{erreur}</p>{/if}

{#if statut === 'datables' && (tous.length || lot)}
  <section class="surface mb-4 p-4" aria-label="Tout dater d'un coup">
    {#if enLot}
      <p class="text-sm" role="status">Datation en cours : {faitesLot} photo{faitesLot > 1 ? 's' : ''} datée{faitesLot > 1 ? 's' : ''}, {restantLot} restante{restantLot > 1 ? 's' : ''}…</p>
    {:else if lot}
      <p class="text-sm" role="status">{faitesLot} photo{faitesLot > 1 ? 's' : ''} datée{faitesLot > 1 ? 's' : ''} d'après leur nom (lot {lot}).</p>
      <button class="bouton mt-2" onclick={annulerLot} disabled={occupe}>{confirmeAnnuler ? `Confirmer : annuler les ${faitesLot}` : 'Annuler tout ce lot'}</button>
    {:else}
      <p class="text-sm">Chaque photo prend la date de son dossier ou de son album (le 15 du mois, le 1er juillet pour une année, l'année du milieu pour une fourchette). Celles dont les visages contredisent le nom ne sont pas dans cette liste. Tout est noté au journal et s'annule d'un geste.</p>
      <button class="bouton bouton-confirmer mt-2" onclick={toutDater} disabled={occupe || session.lecture_seule}>{confirmeLot ? `Confirmer : dater les ${tous.length} photos` : `Tout dater d'un coup (${tous.length})`}</button>
    {/if}
  </section>
{/if}

{#if tous.length}
  <div class="filtres mb-4" role="search" aria-label="Filtrer les photos">
    <label class="sr-only" for="filtre-dossier">Dossier</label>
    <select id="filtre-dossier" bind:value={dossier}>
      <option value="">Tous les dossiers ({tous.length})</option>
      {#each arbre as d (d.cle)}<option value={d.cle}>{'  '.repeat(Math.max(0, d.niveau)) + d.nom} ({d.nombre})</option>{/each}
    </select>
    <label class="sr-only" for="filtre-nom">Nom</label>
    <input id="filtre-nom" type="search" bind:value={cherche} placeholder="Fichier, dossier ou personne" />
    {#if dossier || cherche}<button class="bouton" onclick={() => { dossier = ''; cherche = '' }}>Tout voir</button>{/if}
  </div>
{/if}

{#if !s && liste.length === 0 && (dossier || cherche)}
  <p class="secondaire py-10 text-center">Aucune photo {statut === 'a_dater' ? 'à dater' : statut === 'datables' ? 'datable par le nom' : 'à trancher'} avec ce filtre.</p>
{:else if !s && liste.length === 0}
  <div class="py-16 text-center">
    <p class="titre-page">{statut === 'a_dater' ? 'Tout est daté' : statut === 'datables' ? 'Plus rien à dater par le nom' : 'Rien à trancher'}</p>
    <p class="secondaire mx-auto mt-3 max-w-md">
      {#if statut === 'a_dater'}Les photos restantes attendent le calcul sur le PC, ou sont à trancher.
      {:else}Les cas douteux apparaîtront ici : marge trop large, visages en désaccord, aucun visage exploitable.{/if}
    </p>
    <p class="mt-6 flex justify-center gap-3">
      <a class="bouton" href="#connexion/pc">Calcul sur le PC</a>
      <a class="bouton" href={statut === 'a_dater' ? '#trancher' : '#nommer'}>{statut === 'a_dater' ? 'À trancher' : 'Nommer des visages'}</a>
    </p>
  </div>
{:else if s}
  <p class="secondaire mb-3 text-sm">{statut === 'a_dater' ? 'À dater' : statut === 'datables' ? 'Datables par le nom' : 'À trancher'} : photo {position + 1} sur {liste.length}{liste.length < tous.length ? ` (filtre : ${tous.length} en tout)` : ''}
    {#if liste[position]?.chemin}<span class="chemin" title={liste[position].chemin}> · {liste[position].chemin.split('/').slice(-2).join('/')}</span>{/if}</p>

  <div class="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px]">
    <!-- Photo et visages -->
    <figure class="relative self-start overflow-hidden rounded-lg bg-verre-2">
      <img src={apercu(s.asset_id)} alt="Scan à dater" class="block w-full" />
      {#each s.visages as v}
        {@const iv = parFace[v.face_id]}
        <div class="absolute rounded-sm border-2 {iv ? 'border-or' : 'border-etiquette/50 border-dashed'}"
             style="left:{(100 * v.x1) / v.img_w}%; top:{(100 * v.y1) / v.img_h}%; width:{(100 * (v.x2 - v.x1)) / v.img_w}%; height:{(100 * (v.y2 - v.y1)) / v.img_h}%">
          <span class="absolute left-0 top-full mt-0.5 whitespace-nowrap rounded bg-verre/85 px-1 text-[11px]">
            {v.person_nom || ETATS[v.etat] || 'sans nom'}{iv ? ` · ${Math.round(iv.age)} ans` : ''}
          </span>
        </div>
      {/each}
    </figure>

    <!-- Millésime proposé et actions -->
    <section aria-label="Année">
      <p class="mb-3"><span class="origine origine-{s.origine}">{{ tag: 'Scan tagué', album: 'Album', dossier: 'Dossier' }[s.origine]}</span></p>
      {#if s.raison}<p class="mb-3 rounded-md border border-alerte/50 px-3 py-2 text-sm text-alerte">{s.raison}</p>{/if}

      {#if s.comparaison}
        {@const c = s.comparaison}
        <div class="mb-4 rounded-md border px-3 py-2 text-sm {c.coherent === false ? 'border-alerte/60' : 'border-filet'}" role="group" aria-label="Date déjà connue">
          <dl class="grid gap-1">
            {#if c.date_connue}<div class="flex justify-between gap-3"><dt class="secondaire">Date dans Immich</dt><dd>{dateJour(c.date_connue)}</dd></div>{/if}
            {#if c.date_nom}<div class="flex justify-between gap-3"><dt class="secondaire">Dans le nom du fichier</dt><dd>{dateJour(c.date_nom)}</dd></div>{/if}
            {#if c.date_dossier}<div class="flex justify-between gap-3"><dt class="secondaire">Dans {c.date_dossier_source}</dt><dd>{c.date_dossier}</dd></div>{/if}
            {#if c.annee_estimee !== null}<div class="flex justify-between gap-3"><dt class="secondaire">Estimée par Millésime</dt><dd>{c.annee_estimee} ±{c.marge}</dd></div>{/if}
          </dl>
          <p class="mt-2 font-semibold {c.coherent === false ? 'text-alerte' : c.coherent ? 'text-or' : ''}">{c.phrase}</p>
          <p class="secondaire mt-1">Quelle date choisir ?</p>
          <div class="mt-2 grid gap-2">
            {#if c.date_connue}<button class="bouton" onclick={() => garder('actuelle')} disabled={occupe}>Garder la date d'Immich ({c.date_connue.slice(0, 4)})</button>{/if}
            {#if c.date_nom}<button class="bouton" onclick={() => garder('nom')} disabled={occupe || session.lecture_seule}>Prendre celle du nom du fichier ({c.date_nom.slice(0, 4)})</button>{/if}
            {#if c.date_dossier}<button class="bouton" onclick={() => garder('dossier')} disabled={occupe || session.lecture_seule}>Prendre celle {c.date_dossier_source.startsWith('le dossier') ? 'du dossier' : 'de l\'album'} ({c.date_dossier.replace('/', '-')})</button>{/if}
          </div>
          <p class="secondaire mt-2 text-xs">Ou règle l'année ci-dessous et valide : c'est l'estimation qui sera écrite.</p>
        </div>
      {/if}

      <div class="flex items-center gap-2">
        <button class="bouton w-11 px-0 text-xl" onclick={() => changer(-1)} aria-label="Année précédente">−</button>
        <p class="millesime flex-1 text-center text-7xl font-semibold leading-none" aria-live="polite">{annee}</p>
        <button class="bouton w-11 px-0 text-xl" onclick={() => changer(1)} aria-label="Année suivante" disabled={annee >= haute}>+</button>
      </div>
      <div class="mt-2 flex items-center justify-center gap-2 text-sm">
        <button class="bouton min-h-9 w-9 px-0" onclick={() => changerMarge(-1)} aria-label="Réduire la marge">−</button>
        <span class="w-28 text-center">marge ±{marge} an{marge > 1 ? 's' : ''}</span>
        <button class="bouton min-h-9 w-9 px-0" onclick={() => changerMarge(1)} aria-label="Élargir la marge">+</button>
      </div>
      {#if s.annee_proposee !== null}
        <p class="secondaire mt-2 text-center text-sm">
          {modifie ? `Proposé par l'indice : ${s.annee_proposee} ±${s.marge}` : 'Proposé par l’indice MiVOLO calibré'}
        </p>
      {/if}

      <div class="mt-5 grid gap-2">
        <button class="bouton {confirmer ? 'bouton-confirmer' : 'bouton-principal'}" onclick={valider} disabled={occupe}>
          {confirmer ? `Confirmer ${annee} ±${marge}` : `Valider ${annee}`}
        </button>
        {#if confirmer}<p class="secondaire text-center text-xs">Marge large : confirme que tu as comparé avec la frise.</p>{/if}
        <div class="grid grid-cols-2 gap-2">
          <button class="bouton" onclick={passer} disabled={occupe || liste.length < 2}>Passer</button>
          <button class="bouton" onclick={plusieurs} disabled={occupe}>Plusieurs années</button>
        </div>
        <button class="bouton" onclick={relire} disabled={relecture}>{relecture ? 'Relecture…' : 'Relire la photo dans Immich'}</button>
        <p class="secondaire text-center text-xs">Après avoir nommé ou ajouté un visage dans Immich.</p>
      </div>

      <dl class="mt-6 space-y-2 text-sm">
        {#if s.details.bornes}
          <div class="flex justify-between gap-3"><dt class="secondaire">Pas avant</dt>
            <dd>{s.details.bornes.basse_souple} <span class="secondaire">(naissance la plus récente)</span></dd></div>
        {/if}
        <div class="flex justify-between gap-3"><dt class="secondaire">Pas après</dt><dd>{haute} <span class="secondaire">(envoi du scan)</span></dd></div>
        {#if s.details.voisins}
          <div class="flex justify-between gap-3"><dt class="secondaire">Même envoi</dt>
            <dd>{s.details.voisins.min}–{s.details.voisins.max} <span class="secondaire">({s.details.voisins.n} déjà datées)</span></dd></div>
        {/if}
        {#if s.a_nommer.length || s.sans_personne.length}
          <div class="flex justify-between gap-3"><dt class="secondaire">Visages sans nom</dt>
            <dd><button class="lien" onclick={() => zoneNommer?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>
              {s.a_nommer.length + s.sans_personne.length} à nommer</button></dd></div>
        {/if}
        {#if s.details.sans_naissance}
          <div class="flex justify-between gap-3"><dt class="secondaire">Sans date de naissance</dt>
            <dd>{s.details.sans_naissance} <span class="secondaire">(à compléter dans carnet)</span></dd></div>
        {/if}
      </dl>
    </section>
  </div>

  {#if s.a_nommer.length || s.sans_personne.length}
    <section bind:this={zoneNommer} class="mt-8 scroll-mt-20" aria-labelledby="titre-nommer">
      <h2 id="titre-nommer" class="font-semibold">À nommer sur cette photo</h2>
      <p class="secondaire text-sm">Un nom donné ici vaut pour tout le groupe dans Immich, et le visage pourra servir à dater dès qu'il a une date de naissance.</p>
      <div class="mt-3 grid items-start gap-3 lg:grid-cols-2">
        {#each s.a_nommer as g (g.person_id)}
          <NommerGroupe groupe={g} {suggestions} compact onfait={apresNommage}
                        onvoir={(e) => (grand = { asset: e.asset_id, face: e.face_id })} />
        {/each}
        {#each s.sans_personne as x (x.face_id)}
          <div class="surface flex gap-3 p-3">
            <button class="shrink-0 rounded-md" onclick={() => (grand = { asset: s.asset_id, face: x.face_id })} aria-label="Voir la photo entière">
              <img src={visage(s.asset_id, x.face_id)} alt="" width="64" height="64" class="aspect-square w-16 rounded-md object-cover" />
            </button>
            <div class="self-center text-sm">
              {#if x.etat === 'supprime'}
                <p class="font-medium">Retiré d'Immich</p>
                <p class="secondaire">Ce visage n'existe plus dans Immich. Il disparaîtra d'ici à la prochaine synchronisation.</p>
              {:else}
                <p class="font-medium">Détecté par Immich, non attribué</p>
                <p class="secondaire">Immich l'a repéré sans le rattacher à une personne. Dans Immich, il apparaît avec le crayon
                  « Modifier les visages » de la photo. <a class="lien" href={versImmich(s.lien_immich)} target="_blank" rel="noopener">Ouvrir la photo dans Immich</a></p>
              {/if}
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if s.visages.some((v) => v.person_nom && v.etat === 'nomme')}
    <section class="mt-8" aria-labelledby="titre-reconnus">
      <h2 id="titre-reconnus" class="font-semibold">Visages reconnus</h2>
      <p class="secondaire text-sm">Un visage attribué à la mauvaise personne fausse la date. « Ce n'est pas elle » le retire de cette personne dans Immich ; il devient un groupe sans nom, à nommer. Annulable depuis le journal.</p>
      <div class="mt-3 grid items-start gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {#each s.visages.filter((v) => v.person_nom && v.etat === 'nomme') as v (v.face_id)}
          <div class="surface flex items-center gap-3 p-3">
            <button class="shrink-0 rounded-md" onclick={() => (grand = { asset: s.asset_id, face: v.face_id })} aria-label={'Voir le visage de ' + v.person_nom}>
              <img src={visage(s.asset_id, v.face_id)} alt="" width="56" height="56" class="aspect-square w-14 rounded-md object-cover" />
            </button>
            <div class="min-w-0 flex-1 text-sm">
              <p class="truncate font-medium">{v.person_nom}</p>
              <button class="bouton mt-1 min-h-9 text-xs {pasElle === v.face_id ? 'bouton-confirmer' : ''}" onclick={() => detacher(v)}
                      disabled={occupe || session.lecture_seule}>{pasElle === v.face_id ? `Confirmer : ce n'est pas ${v.person_nom.split(' ')[0]}` : "Ce n'est pas cette personne"}</button>
            </div>
          </div>
        {/each}
      </div>
    </section>
  {/if}

  {#if personnes.length}
    <section class="mt-8" aria-labelledby="titre-frises">
      <h2 id="titre-frises" class="font-semibold">Comparer avec les frises</h2>
      <p class="secondaire text-sm">Les photos datées de chaque personne, rangées par âge. La photo à dater est placée à l'âge qu'elle aurait en {annee}.</p>
      {#each personnes as p (p.face_id)}
        <Frise personId={p.person_id} nom={p.nom} naissance={p.naissance} {annee} scanAsset={s.asset_id} scanFace={p.face_id} />
      {/each}
    </section>
  {/if}
{:else}
  <p class="secondaire">Chargement…</p>
{/if}

{#if grand}<Visionneuse asset={grand.asset} face={grand.face} fermer={() => (grand = null)} />{/if}

<style>
  .filtres { display: flex; flex-wrap: wrap; gap: 0.5rem; align-items: center; }
  .filtres select, .filtres input { min-height: 2.75rem; min-width: 0; flex: 1 1 14rem; padding: 0 0.75rem; border-radius: 0.6rem; border: 1px solid var(--filet, rgba(255,255,255,.15)); background: transparent; color: inherit; font: inherit; }
  .filtres select option { background: #1f1c19; }
  .chemin { overflow-wrap: anywhere; }
</style>
