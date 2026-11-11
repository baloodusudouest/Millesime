<script>
  import { api, dateCourte, pc } from '../lib/api.svelte.js'
  import EtatPC from '../components/EtatPC.svelte'
  let a = $state(null)
  api.get('/api/accueil').then((r) => (a = r))
  const total = $derived(a ? a.taches.calibrage + a.taches.a_dater : 0)
  const adresse = `${location.protocol}//${location.host}`
</script>

<h1 class="millesime text-4xl font-semibold">Calcul sur le PC</h1>
{#if a && pc.etat !== 'en_cours'}
  <p class="mt-3 text-lg">
    {#if total}<strong>{total}</strong> visage{total > 1 ? 's' : ''} attendent l'analyse
      ({a.taches.calibrage} pour le calibrage, {a.taches.a_dater} pour dater). Compte environ {Math.max(1, Math.round((total * 3) / 60))} min.
    {:else}Aucun visage en attente : rien à lancer.{/if}
  </p>
  {#if a.dernier_calcul}<p class="secondaire text-sm">Dernier calcul : {dateCourte(a.dernier_calcul.fin || a.dernier_calcul.le)}.</p>{/if}
{/if}

<div class="mt-4"><EtatPC /></div>

<p class="secondaire mt-6 max-w-2xl">
  L'âge des visages est estimé par MiVOLO sur ton PC : le NAS est trop lent pour ce modèle. Tant que Docker Desktop est
  ouvert, le calculateur demande du travail à Millésime toutes les 5 minutes et calcule dès qu'un visage attend. Quand il
  n'y a rien à faire, Millésime en profite pour relire Immich (au plus toutes les 15 minutes). Rien n'est écrit dans Immich
  pendant le calcul.
</p>

<h2 class="mt-8 font-semibold">Une seule fois</h2>
<ol class="mt-2 list-decimal space-y-2 pl-5">
  <li>Installer Docker Desktop (installation pour l'utilisateur, WSL 2) et le lancer.</li>
  <li>Dans le dossier <code>C:\millesime</code>, ajouter ces deux lignes au fichier <code>.env</code> :
    <pre class="surface mt-2 overflow-x-auto p-3 text-sm">MILLESIME_URL={adresse}
MILLESIME_JETON_CALCUL=…   (la valeur de la stack homelab)</pre>
  </li>
  <li>Dans un terminal (celui de Docker Desktop convient), télécharger le fichier du calculateur et le démarrer :
    <pre class="surface mt-2 overflow-x-auto p-3 text-sm">cd C:\millesime
curl.exe -L -o calcul.yml https://raw.githubusercontent.com/baloodusudouest/Millesime/main/pc/calcul.yml
docker compose -f calcul.yml up -d</pre>
  </li>
</ol>

<h2 class="mt-8 font-semibold">Ensuite</h2>
<p class="mt-2">Il suffit d'ouvrir Docker Desktop : le calculateur redémarre tout seul. Dans Docker Desktop, le conteneur
  <code>millesime_calcul</code> montre ce qu'il fait (onglet Logs).</p>
<ul class="secondaire mt-2 list-disc space-y-1 pl-5 text-sm">
  <li>Arrêter le calculateur : <code>docker compose -f calcul.yml down</code></li>
  <li>Mettre à jour le calculateur : <code>docker compose -f calcul.yml up -d</code> (télécharge la dernière version)</li>
</ul>
