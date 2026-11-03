"""Installed publication SIGKILL-equivalent probe in an isolated fixture only."""
import hashlib,json,os,pathlib,subprocess,sys
root=pathlib.Path(sys.argv[1]).resolve()
if len(sys.argv)>2:
    from groovemap_next import pipeline
    prefix=root/'song'
    replace=pipeline.os.replace
    def exit_after_first(src,dst):
        replace(src,dst)
        if str(dst).endswith('_tempo.mid'):os._exit(73)
    pipeline.os.replace=exit_after_first
    with pipeline._output_staging(prefix) as stage:
        a=stage/'tempo';a.write_bytes(b'new-tempo')
        b=stage/'drums';b.write_bytes(b'new-drums')
        pipeline._publish_staged_outputs({root/'song_tempo.mid':a,root/'song_drums.mid':b},(),backup_dir=stage/'backup')
    raise AssertionError('unreachable')
root.mkdir(exist_ok=False)
(root/'song_tempo.mid').write_bytes(b'old-tempo')
(root/'song_drums.mid').write_bytes(b'old-drums')
p=subprocess.run([sys.executable,__file__,str(root),'child'])
assert p.returncode==73
manifest=next(root.glob('.song.release-*/backup/recovery.json'))
lock=root/'.song_tempo.mid.publication-lock'
assert lock.is_dir()
plan=json.loads(manifest.read_text())
assert all(pathlib.Path(backup).is_file() for backup in plan.values() if backup)
# Simulated operator recovery using the retained plan after confirming no live owner.
for target,backup in plan.items():
    if backup:os.replace(backup,target)
    else:pathlib.Path(target).unlink(missing_ok=True)
lock.rmdir()
assert (root/'song_tempo.mid').read_bytes()==b'old-tempo'
assert (root/'song_drums.mid').read_bytes()==b'old-drums'
print(json.dumps({'exit_code':p.returncode,'retained_manifest':str(manifest),'backups_retained':True,'operator_recovery_restored_old_set':True,'scope':'ISOLATED_FAULT_FIXTURE_NOT_MODEL_EVIDENCE'},indent=2))
