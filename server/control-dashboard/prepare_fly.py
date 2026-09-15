#!/usr/bin/env python3
"""Copie les deux caches nécessaires depuis Pytorch_fly, sans modifier la source."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def prepare(source, destination):
    source, destination = Path(source).resolve(), Path(destination).resolve()
    files = {'weight.npz': source/'data/experiments/laboratory_v1/weight.npz',
             'neuron_meta.feather': source/'data/cache/raw/neuron_meta.feather'}
    for path in files.values():
        if not path.is_file():
            raise FileNotFoundError(f'Cache requis absent : {path}')
    destination.mkdir(parents=True, exist_ok=True)
    hashes = {}
    for filename, path in files.items():
        target = destination / filename
        temporary = target.with_suffix(target.suffix + '.tmp')
        shutil.copyfile(path, temporary)
        digest = hashlib.sha256()
        with temporary.open('rb') as stream:
            for block in iter(lambda: stream.read(1024*1024), b''):
                digest.update(block)
        temporary.replace(target)
        hashes[filename] = digest.hexdigest()
    manifest = {'source': 'MaleCNS v1.0', 'model': 'laboratory_v1/intact',
                'origin': 'https://male-cns.janelia.org/', 'license': 'CC-BY-4.0',
                'adapter': 'Pytorch_fly — moteur incarné, intégration à fuite et lecture DNa02/DNg13',
                'sha256': hashes}
    (destination/'manifest.json').write_text(json.dumps(manifest, indent=2)+'\n')
    print(f'Connectome préparé : {destination}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='Dossier du projet Pytorch_fly')
    parser.add_argument('--destination', type=Path, default=Path(__file__).parent/'fly-data')
    args = parser.parse_args()
    prepare(args.source, args.destination)
