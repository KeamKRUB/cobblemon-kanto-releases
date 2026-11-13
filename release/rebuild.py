"""Reconstruct the audited client ZIP without re-uploading unchanged game files."""
from pathlib import Path
import hashlib,html.parser,http.cookiejar,json,sys,urllib.parse,urllib.request,zipfile

BASE_URL='https://drive.usercontent.google.com/download?id=1Tn1RHd6c5c1noHqKZIG16M9zcvbMbKnq&export=download'
BASE_SHA256='65bde2ada29f4ec7f06542e6c394af009fa17f45f88bd066eb327025c755d2a1'
ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/'out';OUT.mkdir(exist_ok=True)

class DownloadForm(html.parser.HTMLParser):
    def __init__(self):super().__init__();self.action=None;self.inputs={}
    def handle_starttag(self,tag,attributes):
        attributes=dict(attributes)
        if tag=='form':self.action=attributes.get('action')
        if tag=='input' and attributes.get('name'):self.inputs[attributes['name']]=attributes.get('value','')

def sha256(path):
    digest=hashlib.sha256()
    with path.open('rb') as file:
        for data in iter(lambda:file.read(4*1024*1024),b''):digest.update(data)
    return digest.hexdigest()

def download_base():
    target=OUT/'original-base.zip'
    if target.exists() and sha256(target)==BASE_SHA256:return target
    opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    url=BASE_URL
    for _ in range(4):
        response=opener.open(urllib.request.Request(url,headers={'User-Agent':'Cobblemon-Kanto-Release-Builder/1.0'}),timeout=60)
        if 'text/html' not in response.headers.get('Content-Type',''):
            temporary=target.with_suffix('.part');total=0
            with temporary.open('wb') as file:
                while True:
                    data=response.read(1024*1024)
                    if not data:break
                    file.write(data);total+=len(data)
                    if total%(128*1024*1024)==0:print('Downloaded base:',total//(1024*1024),'MiB',flush=True)
            if sha256(temporary)!=BASE_SHA256:raise RuntimeError('Original release checksum mismatch')
            temporary.replace(target);return target
        form=DownloadForm();form.feed(response.read(1024*1024).decode('utf-8',errors='replace'))
        if not form.action:raise RuntimeError('Original Drive source did not provide a downloadable file')
        action=urllib.parse.urljoin(response.geturl(),form.action)
        if urllib.parse.urlparse(action).hostname not in {'drive.google.com','drive.usercontent.google.com'}:raise RuntimeError('Unexpected base download host')
        url=action+'?'+urllib.parse.urlencode(form.inputs)
    raise RuntimeError('Could not retrieve original client release')

base=download_base()
patch=ROOT/'release/payload-transport-patch.zip'
target=OUT/'Cobblemon-Online-Payload.zip'
with zipfile.ZipFile(patch) as archive,base.open('rb') as original:
    plan=json.loads(archive.read('manifest.json'))
    if plan['baseSha256']!=BASE_SHA256:raise RuntimeError('Patch is for a different base release')
    digest=hashlib.sha256();total=0
    with archive.open('literals.bin') as literals,target.open('wb') as output:
        for operation in plan['operations']:
            if operation['source'] not in {'base','literal'} or operation['offset']<0 or operation['length']<0:raise RuntimeError('Invalid reconstruction operation')
            source=original if operation['source']=='base' else literals
            source.seek(operation['offset']);remaining=operation['length']
            while remaining:
                data=source.read(min(remaining,4*1024*1024))
                if not data:raise RuntimeError('Unexpected end of reconstruction input')
                output.write(data);digest.update(data);total+=len(data);remaining-=len(data)
    if digest.hexdigest()!=plan['sha256'] or total!=plan['bytes']:raise RuntimeError('Reconstructed release failed verification')
with zipfile.ZipFile(target) as archive:
    names=archive.namelist()
    if archive.testzip() is not None:raise RuntimeError('Client ZIP failed integrity check')
    if any(name.startswith(('client/mods/replaymod-','client/mods/personal-replay-access-')) for name in names):raise RuntimeError('Optional recorder must not be in the standard client')
    for name in ['client/mods/kanto-item-crates-1.0.0.jar','client/mods/MouseTweaks-fabric-mc1.21-2.26.jar','client-update-manifest.json']:assert name in names,name
print(json.dumps({'verified':True,'bytes':total,'sha256':digest.hexdigest(),'file':target.name}),flush=True)
