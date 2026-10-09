#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
dest="$PWD/.release/tools"
mkdir -p "$dest"
curl -fsSL https://get.helm.sh/helm-v3.17.3-linux-amd64.tar.gz -o "$dest/helm.tgz"
curl -fsSL https://get.helm.sh/helm-v3.17.3-linux-amd64.tar.gz.sha256sum -o "$dest/helm.sha256"
curl -fsSL https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-amd64 -o "$dest/kind"
curl -fsSL https://kind.sigs.k8s.io/dl/v0.27.0/kind-linux-amd64.sha256sum -o "$dest/kind.sha256"
python3 - <<'PY'
import hashlib,pathlib,tarfile
p=pathlib.Path('.release/tools')
for name in ('helm','kind'):
    binary=p/('helm.tgz' if name=='helm' else name)
    assert hashlib.sha256(binary.read_bytes()).hexdigest()==(p/(name+'.sha256')).read_text().split()[0]
with tarfile.open(p/'helm.tgz') as f:
    (p/'helm').write_bytes(f.extractfile('linux-amd64/helm').read())
for name in ('helm','kind'):
    (p/name).chmod(0o755)
PY
if [[ -n "${GITHUB_PATH:-}" ]]; then echo "$dest" >> "$GITHUB_PATH"; fi
for spec in "gitleaks/gitleaks v8.24.2 gitleaks_8.24.2_linux_x64.tar.gz gitleaks_8.24.2_checksums.txt gitleaks"             "rhysd/actionlint v1.7.7 actionlint_1.7.7_linux_amd64.tar.gz actionlint_1.7.7_checksums.txt actionlint"; do
  read -r repo version archive sums tool <<< "$spec"
  curl -fsSL "https://github.com/$repo/releases/download/$version/$archive" -o "$dest/$archive"
  curl -fsSL "https://github.com/$repo/releases/download/$version/$sums" -o "$dest/$sums"
  (cd "$dest"; grep "  $archive$" "$sums" | sha256sum -c -)
  tar -xzf "$dest/$archive" -C "$dest" "$tool"
done
