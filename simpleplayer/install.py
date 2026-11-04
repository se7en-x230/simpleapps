#!/usr/bin/env python3
"""Install Simpleplayer scripts and style; preserve the user's library settings."""
import argparse
from pathlib import Path
import shutil
import tempfile
import os

def install(home, standalone=False):
    source=Path(__file__).resolve().parent
    config=Path(os.environ.get("XDG_CONFIG_HOME",home/".config")) if home==Path.home() else home/".config"
    share=Path(os.environ.get("XDG_DATA_HOME",home/".local/share")) if home==Path.home() else home/".local/share"
    if standalone:
        # A separate layout for app-only installs; the Newinit layout is unchanged.
        data=share/'simpleplayer'
        files=[(source/'simpleplayer-native',home/'.local/bin/simpleplayer-native',0o755),
               (source/'simpleplayer.desktop',share/'applications/simpleplayer.desktop',0o644)]
        files += [(source.parent/'simple-common/simple_images.py',share/'simple-common/simple_images.py',0o644)]
        files += [(p,share/'simple/images'/p.name,0o644) for p in (source.parent/'simple-common/assets/images').glob('*.png')]
        files += [(source/name,data/name,0o755 if name.endswith(('.py','.sh')) else 0o644)
                  for name in ('bridge.py','playback.sh','app.css')]
        files += [(p,data/'scripts'/p.name,0o755) for p in (source/'scripts').glob('*.py')]
        files += [(p,data/'icons'/p.name,0o644) for p in (source/'icons').glob('*.svg')]
        for src,dst,mode in files:
            dst.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(src,dst);dst.chmod(mode)
        return
    install(home, standalone=True)
    music=config/'simplepicker/music'
    files=[(source/'simpleplayer.desktop',share/'applications/simpleplayer.desktop',0o644),(source/'simpleplayer',config/'mango/scripts/simpleplayer',0o755),
           (source/'simpleplayer-native',home/'.local/bin/simpleplayer',0o755),
           (source/'style.css',music/'style.css',0o644)]
    files += [(source/name,config/'simpleplayer'/name,0o755 if name.endswith(('.py','.sh')) else 0o644) for name in ('bridge.py','playback.sh','app.css')]
    files += [(p,config/'simpleplayer/icons'/p.name,0o644) for p in (source/'icons').glob('*.svg')]
    files += [(p,music/'scripts'/p.name,0o755) for p in (source/'scripts').glob('*.py')]
    files += [(p,music/'icons'/p.name,0o644) for p in (source/'icons').glob('*.svg')]
    if not (music/'config.toml').exists():
        files.append((source/'defaults/config.toml',music/'config.toml',0o644))
    for src,dst,mode in files:
        if dst.exists() and dst.read_bytes()==src.read_bytes() and dst.stat().st_mode&0o777==mode:
            continue
        dst.parent.mkdir(parents=True,exist_ok=True)
        fd,tmp=tempfile.mkstemp(prefix='.'+dst.name+'-',dir=dst.parent)
        try:
            os.close(fd);shutil.copyfile(src,tmp);os.chmod(tmp,mode);os.replace(tmp,dst)
        finally:
            Path(tmp).unlink(missing_ok=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--home',type=Path,default=Path.home())
    parser.add_argument("--standalone",action="store_true")
    args=parser.parse_args()
    install(args.home,args.standalone)
