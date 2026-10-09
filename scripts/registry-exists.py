"""Only a confirmed registry 404 permits publishing a new immutable tag."""
import os
import sys
import httpx

repository, version = sys.argv[1:]
with httpx.Client(timeout=30) as client:
    token = client.get('https://ghcr.io/token',
                       params={'service':'ghcr.io','scope':f'repository:{repository}:pull'},
                       auth=(os.environ['GITHUB_ACTOR'],os.environ['GH_TOKEN']))
    token.raise_for_status()
    result = client.head(f'https://ghcr.io/v2/{repository}/manifests/{version}',
                         headers={'Authorization':'Bearer '+token.json()['token'],
                                  'Accept':'application/vnd.oci.image.index.v1+json,application/vnd.docker.distribution.manifest.v2+json'})
    if result.status_code == 404:
        print('false')
    else:
        result.raise_for_status()
        print('true')
