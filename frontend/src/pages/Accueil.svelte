<script>
  import { api, dateCourte, pluriel, session } from '../lib/api.svelte.js'
  let { deconnecter } = $props()
  let a = $state(null)
  let erreur = $state('')
  let synchro = $state(false)

  async function charger() {
    try { a = await api.get('/api/accueil') } catch (e) { erreur = e.message }
  }
  async function synchroniser() {
    synchro = true
    erreur = ''
    try { await api.post('/api/synchroniser'); await charger() } catch (e) { erreur = e.message }
    synchro = false
  }
  charger()

  const lignes = $derived(a ? [
    { n: a.compteurs.a_dater, texte: 'photos à dater', lien: '#dater', action: 'Dater' },
    { n: a.compteurs.a_trancher, texte: 'photos à trancher', lien: '#trancher', action: 'Trancher' },
    { n: a.compteurs.a_nommer, texte: 'groupes de visages à nommer', lien: '#nommer', action: 'Nommer' },
    { n: a.taches.calibrage + a.taches.a_dater, texte: a.pc?.actif && a.pc?.veille ? 'visages en cours d’analyse sur le PC' : 'visages à analyser sur le PC', lien: '#calcul', action: a.pc?.actif && a.pc?.veille ? 'Voir' : 'Mode d’emploi' },
    { n: a.compteurs.suspects, texte: 'visages à vérifier dans Immich', lien: '#verifier', action: 'Voir' },
  ] : [])
</script>

{#if erreur}<p class="mb-4 text-alerte" role="alert">{erreur}</p>{/if}

{#if a}
  <section aria-labelledby="titre-bilan">
    <h1 id="titre-bilan" class="sr-only">Bilan</h1>
    <p class="secondaire">Scans « Non datée »</p>
    <p class="mt-1 flex items-baseline gap-3">
      <span class="millesime text-6xl font-semibold text-or">{a.compteurs.validees}</span>
      <span class="text-lg">datées sur {a.compteurs.total}</span>
    </p>
    <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-filet" role="img"
         aria-label="{a.compteurs.validees} photos datées sur {a.compteurs.total}">
      <div class="h-full bg-or" style="width: {a.compteurs.total ? (100 * a.compteurs.validees) / a.compteurs.total : 0}%"></div>
    </div>
  </section>

  <ul class="mt-8 divide-y divide-filet border-y border-filet">
    {#each lignes as l}
      <li>
        <a href={l.lien} class="flex items-center gap-4 py-4">
          <span class="millesime w-14 text-right text-3xl font-semibold" class:secondaire={!l.n}>{l.n}</span>
          <span class="flex-1" class:secondaire={!l.n}>{l.texte}</span>
          {#if l.n}<span class="text-sm text-lie">{l.action}</span>{/if}
        </a>
      </li>
    {/each}
  </ul>

  <section class="mt-8 grid gap-6 sm:grid-cols-2">
    <div>
      <h2 class="font-semibold">Précision de l'indice</h2>
      {#if a.calibrage}
        <p class="secondaire mt-1 text-sm">
          Calibrage n° {a.calibrage.version} sur {pluriel(a.calibrage.n_visages, 'visage')} de scans datés par tampon.
          {#if a.calibrage.cv_mediane !== null}
            Erreur médiane mesurée : <strong class="text-etiquette">{a.calibrage.cv_mediane} ans</strong>,
            {a.calibrage.cv_3ans} % des photos à moins de 3 ans.
          {:else}
            Pas encore assez de visages pour mesurer la précision.
          {/if}
        </p>
      {:else}
        <p class="secondaire mt-1 text-sm">Aucun calibrage : lance l'analyse sur le PC.</p>
      {/if}
    </div>
    <div>
      <h2 class="font-semibold">Synchronisation avec Immich</h2>
      <p class="secondaire mt-1 text-sm">
        {#if a.derniere_synchro}Dernière : {dateCourte(a.derniere_synchro.le)}, {pluriel(a.derniere_synchro.scans, 'scan')} relus.{:else}Jamais faite.{/if}
        Elle se refait toute seule chaque heure, et toutes les 15 min quand le PC est en veille.
      </p>
      <button class="bouton mt-2" onclick={synchroniser} disabled={synchro}>{synchro ? 'Synchronisation…' : 'Synchroniser maintenant'}</button>
    </div>
  </section>

  <p class="mt-6 text-sm {a.pc?.actif ? 'text-or' : 'secondaire'}">
    {#if a.pc?.actif && a.pc?.veille}PC en veille : il calcule dès qu'un visage attend (dernière demande il y a {a.pc.il_y_a_min} min).
    {:else if a.pc}PC hors ligne depuis {dateCourte(a.pc.le)} : ouvre Docker Desktop pour relancer la veille.
    {:else}Calculateur du PC jamais vu : voir <a class="lien" href="#calcul">Calcul sur le PC</a>.{/if}
  </p>

  <section class="mt-8 rounded-lg border border-dashed border-filet p-4">
    <h2 class="font-semibold">Home Assistant</h2>
    <p class="secondaire mt-1 text-sm">À venir : capteur « photos à dater », rappel pour allumer le PC, photo d'une personne à un âge donné pour le journal de naissance.</p>
  </section>

  <p class="secondaire mt-8 flex flex-wrap items-center gap-x-4 gap-y-2 text-sm">
    <a class="lien" href="#verifier">À vérifier</a>
    <a class="lien" href="#calcul">Calcul sur le PC</a>
    <a class="lien" href="#journal">Journal et annulation</a>
    <button class="lien" onclick={deconnecter}>Se déconnecter</button>
    <span class="ml-auto">version {session.version}</span>
  </p>
{:else if !erreur}
  <p class="secondaire">Chargement…</p>
{/if}
