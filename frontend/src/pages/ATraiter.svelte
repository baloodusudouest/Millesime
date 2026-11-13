<script>
  // 2.0 : « À traiter », en tuiles comme dans carnet. Le bilan en tête, puis une tuile par file.
  // Dater a aussi son onglet : c'est le geste répété, il ne passe jamais derrière une tuile.
  import { api, pc } from '../lib/api.svelte.js'
  import { ICONES } from '../lib/icones.js'
  let a = $state(null)
  let erreur = $state('')
  api.get('/api/accueil').then((r) => (a = r)).catch((e) => (erreur = e.message))

  const attente = $derived(a ? a.taches.calibrage + a.taches.a_dater : 0)
  const tuiles = $derived(a ? [
    { cle: 'dater', lien: '#dater', n: a.compteurs.a_dater, nom: 'À dater', resume: 'Une année proposée, à valider' },
    { cle: 'datables', lien: '#datables', n: a.compteurs.datables, nom: 'Datables par le nom', resume: 'Dossier, sous-dossier ou album qui porte une date' },
    { cle: 'trancher', lien: '#trancher', n: a.compteurs.a_trancher, nom: 'À trancher', resume: 'Marge large ou visages en désaccord' },
    { cle: 'nommer', lien: '#nommer', n: a.compteurs.a_nommer, nom: 'À nommer', resume: 'Groupes de visages sans nom' },
    { cle: 'verifier', lien: '#verifier', n: a.compteurs.suspects, nom: 'À vérifier', resume: 'Âge estimé qui contredit l\'âge connu' },
    { cle: 'naissance', lien: '#nommer', n: a.compteurs.sans_naissance, nom: 'Sans naissance', resume: 'À compléter dans carnet' },
    { cle: 'pc', lien: '#connexion/pc', n: attente, nom: pc.etat === 'en_cours' ? 'En calcul sur le PC' : 'À calculer sur le PC', resume: 'Visages en attente d\'analyse' },
  ] : [])
</script>

<h1 class="titre-page">À traiter</h1>
{#if erreur}<p class="mt-3 text-alerte" role="alert">{erreur}</p>{/if}

{#if a}
  <section class="mt-4" aria-label="Bilan">
    <p class="flex items-baseline gap-3">
      <span class="millesime text-6xl font-semibold text-or">{a.compteurs.validees}</span>
      <span class="text-lg">datées sur {a.compteurs.total} <span class="secondaire">scans sans date</span></span>
    </p>
    <div class="mt-3 h-1.5 overflow-hidden rounded-full bg-filet" role="img"
         aria-label="{a.compteurs.validees} photos datées sur {a.compteurs.total}">
      <div class="h-full bg-or" style="width: {a.compteurs.total ? (100 * a.compteurs.validees) / a.compteurs.total : 0}%"></div>
    </div>
  </section>

  <nav class="tuiles mt-6" aria-label="Files à traiter">
    {#each tuiles as t (t.cle)}
      <a class="tuile" class:vide={!t.n} href={t.lien}>
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{@html ICONES[t.cle]}</svg>
        <span class="chiffre">{t.n}</span>
        <span class="nom-tuile">{t.nom}</span>
        <span class="resume">{t.resume}</span>
      </a>
    {/each}
  </nav>
{:else if !erreur}
  <p class="secondaire mt-4">Chargement…</p>
{/if}
