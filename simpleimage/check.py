from importlib.machinery import SourceFileLoader
from pathlib import Path
from tempfile import TemporaryDirectory
m=SourceFileLoader('viewer',str(Path(__file__).with_name('simpleimage'))).load_module()
with TemporaryDirectory() as td:
    root=Path(td)
    for name in ('img10.png','img2.png','img1.png','.hidden.png','notes.txt'):(root/name).touch()
    files,index=m.collect([root/'img2.png'],{'png'},m.DEFAULTS)
    assert [p.name for p in files]==['img1.png','img2.png','img10.png'] and index==1
    files,index=m.collect([root/'img10.png',root/'img1.png'],{'png'},m.DEFAULTS)
    assert [p.name for p in files]==['img10.png','img1.png']
    class Fake:
        def get_byte_length(self):return 6
    cache=m.Cache(12)
    cache.put('a',Fake());cache.put('b',Fake());cache.get('a');cache.put('c',Fake())
    assert cache.get('b') is None and cache.get('a') and cache.bytes==12
print('PASS: folder navigation, natural ordering, hidden files, explicit selections, bounded LRU cache')
