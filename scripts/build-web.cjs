// No package install or network at build/run time. Reproducible pinned compiler.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const manifest = JSON.parse(fs.readFileSync(path.join(root,'vendor/SHA256.json'),'utf8'));
for (const [name, expected] of Object.entries(manifest)) {
  const actual = crypto.createHash('sha256').update(fs.readFileSync(path.join(root,'vendor',name))).digest('hex');
  if (actual !== expected) throw new Error('Vendor integrity mismatch: ' + name);
}
const babel = require(path.join(root, 'vendor/babel-7.28.5.min.js'));
const source = fs.readFileSync(path.join(root, 'salary-planner-react.html'), 'utf8');
const match = source.match(/<script type="text\/babel">([\s\S]*?)<\/script>/);
if (!match) throw new Error('JSX source missing');
const helpers = source.match(/<script id="ibkr-connection-helpers">([\s\S]*?)<\/script>/);
const output = path.join(root, 'web-build');
fs.mkdirSync(output, {recursive:true});
const js = babel.transform(match[1], {presets:['react'], sourceType:'script', comments:false}).code;
fs.writeFileSync(path.join(output, 'app.js'), js);
fs.writeFileSync(path.join(output, 'connection.js'), helpers[1]);
let html = source.replace(/    <script src=.*?<\/script>\n/g, '')
  .replace(helpers[0], '<script src="/assets/react-18.3.1.min.js"></script>\n<script src="/assets/react-dom-18.3.1.min.js"></script>\n<script src="/assets/connection.js"></script>')
  .replace(match[0], '<script src="/assets/app.js"></script>');
html = html.replace('<meta charset="UTF-8" />', '<meta charset="UTF-8" />\n<meta name="csrf-token" content="__CSRF_TOKEN__" />');
fs.writeFileSync(path.join(output, 'dashboard.html'), html);
fs.writeFileSync(path.join(output, 'source.sha256'), crypto.createHash('sha256').update(source).digest('hex'));
console.log('Frontend compiled locally: web-build/dashboard.html');
