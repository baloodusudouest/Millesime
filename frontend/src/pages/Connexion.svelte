<script>
  import { api, session, suivrePc } from '../lib/api.svelte.js'
  let mdp = $state('')
  let erreur = $state('')
  let envoi = $state(false)

  async function entrer(e) {
    e.preventDefault()
    envoi = true
    erreur = ''
    try {
      await api.post('/api/connexion', { mot_de_passe: mdp })
      session.connecte = true
      suivrePc()
    } catch (err) {
      erreur = err.message
    } finally {
      envoi = false
    }
  }
</script>

<div class="mx-auto flex min-h-dvh max-w-sm flex-col justify-center px-6">
  <p class="millesime text-6xl font-semibold leading-none text-etiquette">Millésime</p>
  <p class="secondaire mt-3">Dater les photos papier de la numérisation.</p>
  <form class="mt-10 space-y-3" onsubmit={entrer}>
    <label class="block text-sm" for="mdp">Mot de passe (celui de carnet)</label>
    <input id="mdp" type="password" autocomplete="current-password" bind:value={mdp} required />
    {#if erreur}<p class="text-sm text-alerte" role="alert">{erreur}</p>{/if}
    <button class="bouton bouton-principal w-full" disabled={envoi || !mdp}>{envoi ? 'Connexion…' : 'Se connecter'}</button>
  </form>
</div>
