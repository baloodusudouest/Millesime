<script>
  // 2.0 : « Réglages », ce qui n'est pas un service : précision de l'indice, journal, déconnexion.
  // 2.12.0 : réglages d'usage (Lecture d'Immich, albums, libellés suivis) et « Restaurer les réglages ».
  import { api, pluriel, session } from '../lib/api.svelte.js'
  import Journal from './Journal.svelte'
  import LectureImmich from './LectureImmich.svelte'
  import Restaurer from './Restaurer.svelte'
  import Sources from './Sources.svelte'
  let { deconnecter } = $props()
  let restaure = $state(0)        // après une restauration : toutes les tuiles de réglages se relisent
  let enregistre = $state(0)      // après « Lecture d'Immich » : les sources, les libellés et le journal se relisent
  let a = $state(null)
  api.get('/api/accueil').then((r) => (a = r)).catch(() => {})
</script>

<h1 class="titre-page">Réglages</h1>

<section class="surface mt-4 p-4" aria-labelledby="titre-indice">
  <h2 id="titre-indice" class="text-lg font-semibold">Précision de l'indice</h2>
  {#if a?.calibrage}
    <p class="secondaire mt-1 text-sm">
      Calibrage n° {a.calibrage.version} sur {pluriel(a.calibrage.n_visages, 'visage')} de scans datés par tampon.
      {#if a.calibrage.cv_mediane !== null}
        Erreur médiane mesurée : <strong class="text-etiquette">{a.calibrage.cv_mediane} ans</strong>,
        {a.calibrage.cv_3ans} % des photos à moins de 3 ans.
      {:else}
        Pas encore assez de visages pour mesurer la précision.
      {/if}
    </p>
  {:else if a}
    <p class="secondaire mt-1 text-sm">Aucun calibrage : lance l'analyse sur le PC (<a class="lien" href="#connexion/pc">Connexion</a>).</p>
  {:else}
    <p class="secondaire mt-1 text-sm">Chargement…</p>
  {/if}
</section>

{#key restaure}<LectureImmich change={() => (enregistre += 1)} />{/key}
{#key `${restaure}-${enregistre}`}<Sources />{/key}

<Restaurer change={() => (restaure += 1)} />

{#key `${restaure}-${enregistre}`}<section class="surface mt-4 p-4"><Journal integre /></section>{/key}

<p class="secondaire mt-6 flex flex-wrap items-center justify-between gap-3 text-sm">
  <span>Millésime {session.version}</span>
  <button class="bouton" onclick={deconnecter}>Se déconnecter</button>
</p>
