// Trasforma le schede HTML di build/social/ in immagini PNG dentro social/ (usato dal workflow Instagram).
const {chromium} = require('playwright');
const fs = require('fs'), path = require('path');
(async () => {
  const src = path.resolve(process.argv[2] || 'build/social'), out = path.resolve(process.argv[3] || 'social');
  fs.mkdirSync(out, {recursive: true});
  const b = await chromium.launch();
  for (const f of fs.readdirSync(src).filter(x => x.endsWith('.html'))) {
    const h = f.endsWith('-story.html') ? 1920 : 1350;
    const p = await b.newPage({viewport: {width: 1080, height: h}});
    await p.goto('file://' + path.join(src, f));
    await p.waitForTimeout(500);
    await p.screenshot({path: path.join(out, f.replace(/\.html$/, '.png'))});
    await p.close();
    console.log('immagine:', f.replace(/\.html$/, '.png'));
  }
  await b.close();
})();
