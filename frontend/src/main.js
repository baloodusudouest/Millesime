import { mount } from 'svelte'
import '@fontsource-variable/public-sans'
import '@fontsource-variable/bodoni-moda'
import './app.css'
import App from './App.svelte'

mount(App, { target: document.getElementById('app') })
