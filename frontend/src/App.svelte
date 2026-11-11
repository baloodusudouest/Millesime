<script>
  import { api, session, suivrePc } from './lib/api.svelte.js'
  import EtatPC from './components/EtatPC.svelte'
  import Connexion from './pages/Connexion.svelte'
  import Accueil from './pages/Accueil.svelte'
  import Dater from './pages/Dater.svelte'
  import Nommer from './pages/Nommer.svelte'
  import Verifier from './pages/Verifier.svelte'
  import Calcul from './pages/Calcul.svelte'
  import Journal from './pages/Journal.svelte'

  const ONGLETS = [
    { id: 'accueil', nom: 'Accueil' },
    { id: 'dater', nom: 'Dater' },
    { id: 'trancher', nom: 'À trancher' },
    { id: 'nommer', nom: 'Nommer' },
  ]
  const AUTRES = [
    { id: 'verifier', nom: 'À vérifier' },
    { id: 'calcul', nom: 'Calcul sur le PC' },
    { id: 'journal', nom: 'Journal' },
  ]

  // #page ou #page/paramètre (ex. #nommer/<id d'un groupe>)
  const lire = () => {
    const [p, param] = location.hash.slice(1).split('/')
    return { page: p || 'accueil', param: param || null }
  }
  let route = $state(lire())
  const page = $derived(route.page)
  window.addEventListener('hashchange', () => (route = lire()))

  api.get('/api/session').then((s) => { session.connecte = s.connecte; session.version = s.version; session.lecture_seule = !!s.lecture_seule; suivrePc() })
    .catch(() => (session.connecte = false))

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
  <header class="sticky top-0 z-20 border-b border-filet bg-verre/95 backdrop-blur" style="padding-top: env(safe-area-inset-top)">
    <div class="mx-auto flex max-w-5xl items-center gap-4 px-4 py-2">
      <a href="#accueil" class="millesime text-2xl font-semibold text-etiquette">Millésime</a>
      <EtatPC compact />
      <nav class="ml-auto hidden gap-1 sm:flex" aria-label="Principale">
        {#each [...ONGLETS, ...AUTRES] as o}
          <a href="#{o.id}" class="rounded-md px-3 py-2 text-sm"
             class:bg-verre-2={page === o.id} class:text-etiquette={page === o.id} class:secondaire={page !== o.id}
             aria-current={page === o.id ? 'page' : undefined}>{o.nom}</a>
        {/each}
      </nav>
    </div>
  </header>

  <main class="mx-auto max-w-5xl px-4 pb-28 pt-4 sm:pb-10">
    {#if session.lecture_seule}
      <p class="mb-4 rounded-md border border-alerte/50 px-3 py-2 text-sm text-alerte" role="status">
        Mode lecture seule : Millésime lit Immich et calcule, mais n'y écrit rien (MILLESIME_LECTURE_SEULE).</p>
    {/if}
    {#if page === 'dater'}<Dater statut="a_dater" />
    {:else if page === 'trancher'}<Dater statut="a_trancher" />
    {:else if page === 'nommer'}<Nommer cible={route.param} />
    {:else if page === 'verifier'}<Verifier />
    {:else if page === 'calcul'}<Calcul />
    {:else if page === 'journal'}<Journal />
    {:else}<Accueil {deconnecter} />{/if}
  </main>

  <!-- Barre du bas sur iPhone -->
  <nav class="fixed inset-x-0 bottom-0 z-20 grid grid-cols-4 border-t border-filet bg-verre/95 backdrop-blur sm:hidden"
       style="padding-bottom: env(safe-area-inset-bottom)" aria-label="Principale">
    {#each ONGLETS as o}
      <a href="#{o.id}" class="py-3 text-center text-[13px]"
         class:text-or={page === o.id} class:secondaire={page !== o.id}
         aria-current={page === o.id ? 'page' : undefined}>{o.nom}</a>
    {/each}
  </nav>
{/if}
