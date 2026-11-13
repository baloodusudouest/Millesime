<script>
  // 2.0 : même navigation que carnet (rail à gauche sur PC, pilule d'icônes en bas sur iPhone),
  // en quatre entrées. « Dater » est l'écran d'ouverture : le geste répété reste à zéro détour.
  import { api, session, suivrePc } from './lib/api.svelte.js'
  import { ICONES } from './lib/icones.js'
  import EtatPC from './components/EtatPC.svelte'
  import Connexion from './pages/Connexion.svelte'
  import ATraiter from './pages/ATraiter.svelte'
  import Dater from './pages/Dater.svelte'
  import Datables from './pages/Datables.svelte'
  import Nommer from './pages/Nommer.svelte'
  import Verifier from './pages/Verifier.svelte'
  import Services from './pages/Services.svelte'
  import Reglages from './pages/Reglages.svelte'

  const ONGLETS = [
    { id: 'dater', nom: 'Dater' },
    { id: 'a-traiter', nom: 'À traiter' },
    { id: 'connexion', nom: 'Connexion' },
    { id: 'reglages', nom: 'Réglages' },
  ]
  // Anciennes adresses (1.x) : elles mènent au nouvel écran qui a repris leur contenu
  const ANCIENNES = { accueil: 'a-traiter', calcul: 'connexion/pc', journal: 'reglages' }
  // Files ouvertes par une tuile : elles appartiennent à « À traiter »
  const FILES = ['trancher', 'nommer', 'verifier', 'datables']

  // #page ou #page/paramètre (ex. #nommer/<id d'un groupe>, #connexion/pc)
  const lire = () => {
    let h = location.hash.slice(1)
    if (ANCIENNES[h]) h = ANCIENNES[h]
    const [p, param] = h.split('/')
    return { page: p || 'dater', param: param || null }
  }
  let route = $state(lire())
  const page = $derived(route.page)
  const actif = $derived(FILES.includes(page) ? 'a-traiter' : page)
  // Dans une file où l'on valide photo après photo, la pilule s'efface sur iPhone : « Valider » reste sous le pouce
  const enFile = $derived(page === 'dater' || page === 'trancher')
  let compteurs = $state(null)
  async function compter() {
    try { compteurs = (await api.get('/api/accueil')).compteurs } catch {}
  }
  window.addEventListener('hashchange', () => { route = lire(); if (session.connecte) compter() })
  const aDecider = $derived(compteurs ? compteurs.a_trancher + compteurs.a_nommer + compteurs.suspects : 0)

  api.get('/api/session').then((s) => {
    session.connecte = s.connecte; session.version = s.version; session.lecture_seule = !!s.lecture_seule
    suivrePc(); if (s.connecte) compter()
  }).catch(() => (session.connecte = false))
  $effect(() => { if (session.connecte) compter() })

  async function deconnecter() {
    await api.post('/api/deconnexion')
    session.connecte = false
  }
</script>

{#if session.connecte === null}
  <p class="secondaire p-6">Chargement…</p>
{:else if !session.connecte}
  <Connexion />
{:else}
  <div class="haut-securise" aria-hidden="true"></div>
  <nav class="onglets" class:en-file={enFile} aria-label="Principale">
    <a href="#dater" class="marque millesime">Millésime</a>
    {#each ONGLETS as o}
      <a href="#{o.id}" class="onglet" aria-current={actif === o.id ? 'page' : undefined} aria-label={o.nom}>
        <span class="icone-onglet">
          <svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.8"
               stroke-linecap="round" stroke-linejoin="round">{@html ICONES[o.id]}</svg>
          {#if o.id === 'dater' && compteurs?.a_dater}<span class="badge">{compteurs.a_dater > 99 ? '99+' : compteurs.a_dater}</span>{/if}
          {#if o.id === 'a-traiter' && aDecider}<span class="badge">{aDecider > 99 ? '99+' : aDecider}</span>{/if}
        </span>
        <span class="libelle">{o.nom}</span>
      </a>
    {/each}
    <div class="etat-pc"><EtatPC compact /></div>
  </nav>

  <main class="contenu">
    {#if session.lecture_seule}
      <p class="mb-4 rounded-md border border-alerte/50 px-3 py-2 text-sm text-alerte" role="status">
        Mode lecture seule : Millésime lit Immich et calcule, mais n'y écrit rien (MILLESIME_LECTURE_SEULE).</p>
    {/if}
    {#if enFile || FILES.includes(page)}
      <p class="retour"><a class="lien" href="#a-traiter">‹ À traiter</a></p>
    {/if}
    {#if page === 'dater'}<Dater statut="a_dater" />
    {:else if page === 'trancher'}<Dater statut="a_trancher" />
    {:else if page === 'datables'}<Datables />
    {:else if page === 'nommer'}<Nommer cible={route.param} />
    {:else if page === 'verifier'}<Verifier />
    {:else if page === 'connexion'}<Services service={route.param} />
    {:else if page === 'reglages'}<Reglages {deconnecter} />
    {:else}<ATraiter />{/if}
  </main>
{/if}

<style>
  .contenu {
    padding: calc(0.75rem + env(safe-area-inset-top)) max(1rem, env(safe-area-inset-right)) calc(5.5rem + env(safe-area-inset-bottom))
             max(1rem, env(safe-area-inset-left));
    max-width: 64rem; margin: 0 auto;
  }
  .haut-securise { position: fixed; z-index: 25; top: 0; left: 0; right: 0; height: env(safe-area-inset-top); background: var(--color-verre); }
  .retour { margin-bottom: 0.6rem; font-size: 0.9rem; }
  /* iPhone : pilule flottante, des icônes seules ; le nom de la section est le titre de l'écran */
  .onglets {
    position: fixed; z-index: 20; left: 50%; transform: translateX(-50%);
    bottom: calc(0.6rem + env(safe-area-inset-bottom)); display: flex; align-items: center; gap: 0.2rem;
    padding: 0.35rem; border-radius: 9999px;
    background: color-mix(in srgb, var(--color-verre) 82%, transparent); border: 1px solid var(--color-filet);
    box-shadow: 0 10px 30px var(--color-ombre);
    backdrop-filter: blur(14px); -webkit-backdrop-filter: blur(14px);
  }
  .marque, .etat-pc { display: none; }
  .onglet {
    display: flex; align-items: center; gap: 0.5rem; height: 3rem; padding: 0 1rem; border-radius: 9999px;
    color: var(--color-craie); font-weight: 600; font-size: 0.95rem; white-space: nowrap;
    transition: background-color 0.28s ease, color 0.28s ease;
  }
  .onglet[aria-current='page'] { background: var(--color-etiquette); color: var(--color-verre); }
  .libelle { position: absolute; max-width: 0; overflow: hidden; opacity: 0; }
  .icone-onglet { position: relative; display: grid; place-items: center; }
  .icone-onglet svg { width: 1.45rem; height: 1.45rem; }
  .badge {
    position: absolute; top: -0.45rem; left: 0.85rem; min-width: 1.15rem; height: 1.15rem; padding: 0 0.3rem;
    border-radius: 9999px; font-size: 0.68rem; font-weight: 700; line-height: 1.15rem; text-align: center;
    background: var(--color-lie); color: var(--color-sur-lie); box-shadow: 0 0 0 2px var(--color-verre);
  }
  .onglet[aria-current='page'] .badge { box-shadow: 0 0 0 2px var(--color-etiquette); }
  @media (max-width: 899px) {
    /* Dans Dater et À trancher, la pilule s'efface : rien entre le pouce et « Valider » */
    .onglets.en-file { display: none; }
    .onglets.en-file ~ .contenu { padding-bottom: calc(1.5rem + env(safe-area-inset-bottom)); }
  }
  @media (min-width: 900px) {
    /* PC : rail latéral, avec les noms */
    .onglets {
      top: 0; bottom: 0; left: 0; transform: none; width: 13rem; flex-direction: column; align-items: stretch; gap: 0.25rem;
      padding: 1.25rem 0.75rem; border-radius: 0; border: 0; border-right: 1px solid var(--color-filet);
      background: var(--color-verre); box-shadow: none; backdrop-filter: none; -webkit-backdrop-filter: none;
    }
    .marque { display: block; font-size: 1.7rem; font-weight: 600; padding: 0 0.85rem 1.1rem; color: var(--color-etiquette); }
    .etat-pc { display: block; margin-top: auto; }
    .onglet { position: relative; height: 2.75rem; padding: 0 0.85rem; gap: 0.7rem; }
    .onglet[aria-current='page'] { background: var(--color-verre-2); color: var(--color-etiquette); }
    .libelle { position: static; max-width: none; opacity: 1; overflow: visible; }
    .icone-onglet { position: static; }
    .badge { left: auto; right: 0.75rem; top: 50%; transform: translateY(-50%); box-shadow: none; min-width: 1.4rem; }
    .onglet[aria-current='page'] .badge { box-shadow: none; }
    .contenu { margin-left: 13rem; max-width: none; padding: 1.5rem 2rem 3rem; }
    .contenu > :global(*) { max-width: 60rem; }
    .retour { display: none; }
  }
  @media (prefers-reduced-motion: reduce) { .onglet { transition: none; } }
</style>
