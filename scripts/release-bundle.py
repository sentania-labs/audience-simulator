"""Bundle only explicit public deployment inputs. No environment files or logs."""
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile

version, digest = sys.argv[1:]
out = Path('.release/bundle')
out.mkdir(parents=True,exist_ok=True)
image=f'ghcr.io/sentania-labs/audience-simulator@{digest}'
compose=Path('compose.yaml').read_text().replace('    build: .\n','')
compose=compose.replace('${AUDIENCE_IMAGE:-ghcr.io/sentania-labs/audience-simulator:latest}',image)
(out/'compose.yaml').write_text(compose)
shutil.copytree('docs',out/'docs',dirs_exist_ok=True)
for source in ('README.md','.env.example','deploy/secret.example.yaml'):
    shutil.copy(source,out/Path(source).name)
argo=Path('deploy/argocd-application.yaml').read_text().replace('targetRevision: main',f'targetRevision: {version}').replace('tag: latest',f'tag: {version}\n          digest: {digest}')
(out/'argocd-application.yaml').write_text(argo)
(out/'values-release.yaml').write_text(f'image:\n  tag: {version}\n  digest: {digest}\n')
(out/'IMAGE.txt').write_text(f'{image}\n')
subprocess.run(['helm','package','charts/audience-simulator','--version',version[1:],'--app-version',version,'--destination',str(out)],check=True)
with tarfile.open(f'.release/audience-simulator-{version}.tar.gz','w:gz') as tar:
    for p in sorted(out.iterdir()):
        tar.add(p,arcname=p.name)
