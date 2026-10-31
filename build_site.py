"""Builds netlify_site/ (a static website) from kala_fest_allocator.py.
Run:  python build_site.py            -> uses the Pyodide CDN (for real deployment)
      python build_site.py /pyodide/  -> uses a local Pyodide copy (for offline testing)
The page runs the SAME Python file inside the browser with Pyodide, so Netlify needs no server."""
import os, re, shutil, sys
HERE = os.path.dirname(os.path.abspath(__file__))
SITE = os.path.join(HERE, "netlify_site")
PYO = sys.argv[1] if len(sys.argv) > 1 else "https://cdn.jsdelivr.net/pyodide/v0.26.4/full/"
src = open(os.path.join(HERE, "kala_fest_allocator.py"), encoding="utf-8").read()
page = re.search(r'PAGE = r"""(.*?)</html>"""', src, re.S).group(1) + "</html>"
BRIDGE = """
<div id="boot" style="position:fixed;inset:0;z-index:50;background:#fff;display:flex;flex-direction:column;align-items:center;justify-content:center;font:15px system-ui;color:#555;text-align:center;padding:20px">
<img src="logo.png" style="width:300px;max-width:80%;margin-bottom:18px" onerror="this.style.display='none'">
<div id="bootmsg"><b style="color:#E8752E">Starting the Python engine...</b><br>First load takes about 20 seconds (NumPy, Pandas and Matplotlib are loading).</div></div>
<script src="__PYO__pyodide.js"></script>
<script>
let PYAPP=null,TOKEN=null,STATEPATH='';
const realFetch=window.fetch.bind(window);
const ready=(async()=>{
 try{
  const py=await loadPyodide({indexURL:'__PYO__'});
  await py.loadPackage(['numpy','pandas','matplotlib']);
  const [code,csv]=await Promise.all([realFetch('kala_fest_allocator.py').then(r=>r.text()),realFetch('volunteers_CSV.csv').then(r=>r.text())]);
  py.FS.writeFile('kala_fest_allocator.py',code);py.FS.writeFile('volunteers_CSV.csv',csv);
  py.runPython("import sys\\nsys.path.insert(0,'.')\\nimport kala_fest_allocator as app");
  PYAPP=py.globals.get('app');STATEPATH=PYAPP.STATE_FILE;
  try{const s=localStorage.getItem('kala_state');if(s)py.FS.writeFile(STATEPATH,s)}catch(e){}
  PYAPP.init_browser('volunteers_CSV.csv');
  window.__py=py;document.getElementById('boot').style.display='none';
 }catch(e){document.getElementById('bootmsg').innerHTML='<b style="color:#a00">Could not start the Python engine.</b><br>'+String(e)+'<br>Check your internet connection and reload.'}
})();
window.fetch=async(url,opts={})=>{
 if(typeof url==='string'&&url.startsWith('/api')){
  await ready;const method=opts.method||'GET';
  const res=JSON.parse(PYAPP.browser_call(method,url.split('?')[0],opts.body||'',TOKEN));
  if(res.token)TOKEN=res.token;
  if(method!=='GET'&&res.status===200){try{localStorage.setItem('kala_state',window.__py.FS.readFile(STATEPATH,{encoding:'utf8'}))}catch(e){}}
  if(res.csv!==undefined)return new Response(res.csv,{status:200,headers:{'Content-Type':'text/csv'}});
  return new Response(JSON.stringify(res.body),{status:res.status,headers:{'Content-Type':'application/json'}});
 }
 return realFetch(url,opts);
};
</script>
""".replace("__PYO__", PYO)
page = page.replace('<div id="login">', BRIDGE + '<div id="login">', 1)
# relative asset URLs so the site works from any path
page = page.replace('src="/logo.png"', 'src="logo.png"').replace("url(/bg.jpg)", "url(bg.jpg)")
shutil.rmtree(SITE, ignore_errors=True)
os.makedirs(SITE)
open(os.path.join(SITE, "index.html"), "w", encoding="utf-8").write(page)
for a, b in (("kala_fest_allocator.py", "kala_fest_allocator.py"), ("volunteers_CSV.csv", "volunteers_CSV.csv"), ("tapmi_logo.png", "logo.png"), ("icon.jpeg", "bg.jpg")):
    shutil.copy(os.path.join(HERE, a), os.path.join(SITE, b))
open(os.path.join(SITE, "_headers"), "w").write("/*\n  Cache-Control: public, max-age=0, must-revalidate\n")
print("Built", SITE, os.listdir(SITE))
