"""Prepare pinned vendor sources and reproduction recipes in a fresh directory."""
from pathlib import Path
import argparse
import json
import shutil
import tarfile
import tempfile
import zipfile

from e32_relink import filehash, require
from e32_source_inputs import verify as verify_source_archive


def prepare(root, archive, output):
    root, archive, output = Path(root).resolve(), Path(archive).resolve(), Path(output).resolve()
    require(not output.exists(), 'source_reproduction_output_already_exists')
    require(hasattr(tarfile, 'data_filter'), 'python_safe_tar_filter_required')
    policy = json.loads((root / 'docs/third-party/e32v2-source-inputs.json').read_text())
    spec = json.loads((root / 'docs/third-party/e32v2-source-distribution.json').read_text())
    require(filehash(archive) == spec['sha256'] and archive.stat().st_size == spec['bytes'],
            'source_distribution_digest_conflict')
    verify_source_archive(policy, archive)
    recipes = root / 'docs/third-party/e32v2-reproduction'
    manifest = json.loads((recipes / 'MANIFEST.json').read_text())
    require(manifest['schema'] == 1, 'unsupported_reproduction_recipe_manifest')
    require(set(manifest['files']) == {p.relative_to(recipes).as_posix()
                                     for p in recipes.rglob('*') if p.is_file() and p.name != 'MANIFEST.json'},
            'reproduction_recipe_inventory_conflict')
    for name, digest in manifest['files'].items():
        require(filehash(recipes / name) == digest, 'reproduction_recipe_hash_conflict')
    shutil.copytree(recipes, output)
    sources = output / 'sources'
    sources.mkdir()
    extracted = 0
    with zipfile.ZipFile(archive) as package:
        for source in policy['archives']:
            if not source['repository']:
                continue  # Arduino/external preferred-form snapshots are separate.
            component = source['component']
            require(component in {'cJSON', 'esp-idf', 'esp-insights', 'esp-lwip', 'mbedtls',
                                  'spiffs', 'crosstool', 'newlib', 'gcc', 'xtensa-overlays'},
                    'unexpected_reproduction_component')
            with tempfile.TemporaryDirectory(dir=sources) as directory:
                temporary = Path(directory)
                compressed = temporary / 'source.tar.gz'
                with package.open(source['path']) as stream, compressed.open('wb') as target:
                    shutil.copyfileobj(stream, target)
                target = temporary / 'tree'
                target.mkdir()
                with tarfile.open(compressed, 'r:gz') as tree:
                    tree.extractall(target, filter='data')
                roots = list(target.iterdir())
                require(len(roots) == 1 and roots[0].is_dir() and not roots[0].is_symlink(),
                        'unexpected_source_archive_root')
                original = roots[0].resolve()
                for path in original.rglob('*'):
                    if path.is_symlink():
                        require(path.resolve().is_relative_to(original), 'source_link_outside_component')
                roots[0].rename(sources / component)
                extracted += 1
    return dict(status='PASS_PINNED_SOURCE_TREE_PREPARED', source_components=extracted,
                recipe_inputs=len(manifest['files']), firmware_installed=False,
                reproduction_results_required=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--archive', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(prepare(Path(__file__).resolve().parents[1], args.archive, args.output), indent=2))
