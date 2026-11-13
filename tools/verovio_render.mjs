// Render an MEI file with Verovio (wasm) using the options Neon uses.
// usage: node verovio_render.mjs input.mei output.svg   (run `npm install` in tools/ first)
import createVerovioModule from 'verovio/wasm';
import { VerovioToolkit } from 'verovio/esm';
import fs from 'fs';
const VerovioModule = await createVerovioModule();
const tk = new VerovioToolkit(VerovioModule);
tk.setOptions({ inputFrom: 'mei', footer: 'none', header: 'none', pageMarginLeft: 0, pageMarginTop: 0, useFacsimile: false });
if (!tk.loadData(fs.readFileSync(process.argv[2], 'utf8'))) { console.error('Verovio could not load the file'); process.exit(1); }
fs.writeFileSync(process.argv[3], tk.renderToSVG(1));
