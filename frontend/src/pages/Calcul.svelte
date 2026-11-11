<script>
  import { api, dateCourte } from '../lib/api.svelte.js'
  let a = $state(null)
  api.get('/api/accueil').then((r) => (a = r))
  const total = $derived(a ? a.taches.calibrage + a.taches.a_dater : 0)
  const adresse = `${location.protocol}//${location.host}`
</script>

<h1 class="millesime text-4xl font-semibold">Calcul sur le PC</h1>
{#if a}
  <p class="mt-3 text-lg">
    {#if total}<strong>{total}</strong> visage{total > 1 ? 's' : ''} attendent l'analyse
      ({a.taches.calibrage} pour le calibrage, {a.taches.a_dater} pour dater). Compte environ {Math.max(1, Math.round((total * 3) / 60))} min.
    {:else}Aucun visage en attente : rien à lancer.{/if}
  </p>
  {#if a.dernier_calcul}<p class="secondaire text-sm">Dernier calcul : {dateCourte(a.dernier_calcul.fin || a.dernier_calcul.le)}.</p>{/if}
{/if}

<p class="secondaire mt-6 max-w-2xl">
  L'âge des visages est estimé par MiVOLO sur ton PC : le NAS est trop lent pour ce modèle. Le PC vient chercher le
  travail auprès de Millésime, renvoie les âges, puis s'arrête tout seul. Rien n'est écrit dans Immich pendant le calcul.
</p>

<h2 class="mt-8 font-semibold">Une seule fois</h2>
<ol class="mt-2 list-decimal space-y-2 pl-5">
  <li>Installer Docker Desktop (installation pour l'utilisateur, WSL 2) et le lancer.</li>
  <li>Dans le dossier <code>C:\millesime</code>, ajouter ces deux lignes au fichier <code>.env</code> :
    <pre class="surface mt-2 overflow-x-auto p-3 text-sm">MILLESIME_URL={adresse}
MILLESIME_JETON_CALCUL=…   (la valeur de la stack homelab)</pre>
  </li>
  <li>Dans un terminal (celui de Docker Desktop convient), télécharger le fichier du calculateur :
    <pre class="surface mt-2 overflow-x-auto p-3 text-sm">cd C:\millesime
curl.exe -L -o calcul.yml https://raw.githubusercontent.com/baloodusudouest/Millesime/main/pc/calcul.yml</pre>
  </li>
</ol>

<h2 class="mt-8 font-semibold">À chaque analyse</h2>
<ol class="mt-2 list-decimal space-y-2 pl-5">
  <li>Allumer le PC et ouvrir Docker Desktop (attendre « Engine running »).</li>
  <li>Lancer :
    <pre class="surface mt-2 overflow-x-auto p-3 text-sm">cd C:\millesime
docker compose -f calcul.yml up</pre>
  </li>
  <li>Attendre « Terminé » : les propositions sont prêtes dans l'onglet Dater.</li>
</ol>
<p class="secondaire mt-6 text-sm">carnet affiche un rappel quand des visages attendent l'analyse.</p>
