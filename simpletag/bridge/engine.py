"""Picard-side operations. Runs only on Picard's main thread."""
from pathlib import Path

FIELDS = ('artist', 'album', 'title', 'tracknumber', 'date')

class Engine:
    def __init__(self, tagger):
        self.tagger = tagger
        self.saving = set()
        self.message = 'Ready'

    def busy(self):
        t = self.tagger
        # Picard's single-instance pipe listener is a permanent pool task.
        listener = int(bool(getattr(getattr(t, 'pipe_handler', None), 'pipe_running', False)))
        return bool(self.saving or getattr(t, '_command_thread_running', False) or t._pending_files_count or t._saving_files_count or
                    t.thread_pool.activeThreadCount() > listener or t.priority_thread_pool.activeThreadCount() or
                    t.save_thread_pool.activeThreadCount() or t.webservice.num_pending_web_requests or
                    t._acoustid._running)

    def finish_saves(self):
        from picard.file import File
        done = [f for f in self.saving if f.state != File.State.PENDING]
        saved = [f for f in done if f.state == File.State.NORMAL]
        failed = [f for f in done if f.state != File.State.NORMAL]
        self.saving.difference_update(done)
        if saved:
            self.tagger.remove_files(saved)
        if failed:
            self.message = 'Some files could not be saved; they remain in the list. Open Picard for details.'
        elif done and not self.saving:
            self.message = 'Saved and removed from the work list'
        # Never remove a file from disk, or discard a failed/pending save.

    def groups(self):
        groups = {}
        matched = set()
        for album in self.tagger.albums.values():
            files = list(album.iterfiles())
            if not files:
                continue
            correct = {track.files[0] for track in album.iter_correctly_matched_tracks()}
            matched.update(files)
            groups['album:' + str(album.id)] = {
                'title': str(album.metadata.get('album', 'Matched album')),
                'artist': str(album.metadata.get('albumartist', '')),
                'kind': 'matched', 'files': files, 'safe': correct,
            }
        for file in self.tagger.iter_all_files():
            if file in matched:
                continue
            folder = str(Path(file.filename).parent)
            group = groups.setdefault('folder:' + folder, {
                'title': Path(folder).name or folder, 'artist': folder,
                'kind': 'unmatched', 'files': [], 'safe': set(),
            })
            group['files'].append(file)
        return groups

    def snapshot(self):
        self.finish_saves()
        groups = []
        for key, group in self.groups().items():
            files = []
            for f in group['files']:
                files.append({'path': f.filename, 'state': f.state.name.lower(),
                              'before': {k: str(f.orig_metadata.get(k, '')) for k in FIELDS},
                              'after': {k: str(f.metadata.get(k, '')) for k in FIELDS},
                              'saveable': f in group['safe']})
            groups.append({'id': key, 'title': group['title'], 'artist': group['artist'],
                           'kind': group['kind'], 'files': files, 'saveable': len(group['safe'])})
        busy = self.busy()
        if not busy:
            self.message = {'Loading folder…': 'Folder loaded', 'Looking up selected folder…': 'Lookup finished — review matches or scan unmatched files', 'Scanning unmatched audio…': 'Scan finished — review matches'}.get(self.message, self.message)
        return {'protocol': 1, 'busy': busy, 'message': self.message, 'groups': groups}

    def action(self, request):
        action = request.get('action')
        if action == 'status':
            return self.snapshot()
        if action == 'hide':
            self.tagger.window.hide()
            return {'ok': True}
        if action == 'show':
            self.tagger.bring_tagger_front()
            return {'ok': True}
        self.finish_saves()
        if self.busy():
            raise ValueError('Picard is still working. Wait for it to finish.')
        if action == 'clear':
            self.tagger.remove_files(list(self.tagger.iter_all_files()))
            self.message = 'Work list cleared without saving'
            return {'ok': True}
        if action == 'load':
            folder = Path(request.get('folder', '')).expanduser()
            if not folder.is_absolute() or not folder.is_dir():
                raise ValueError('Choose an existing folder.')
            self.tagger.add_paths([str(folder)])
            self.message = 'Loading folder…'
            return {'ok': True}
        groups = self.groups()
        if action == 'lookup':
            # Cluster all unmatched files loaded in Picard together. This covers
            # album folders nested below the selected root folder as one lookup.
            files = list(dict.fromkeys(
                file for group in groups.values() if group['kind'] == 'unmatched'
                for file in group['files']
            ))
            if not files:
                raise ValueError('There are no unmatched files to look up.')
            def lookup():
                current = set(self.tagger.iter_all_files())
                parents = list(dict.fromkeys(
                    f.parent_item or self.tagger.unclustered_files
                    for f in files if f in current
                ))
                self.tagger.autotag(parents)
            self.tagger.cluster(files, callback=lookup)
            self.message = 'Looking up all unmatched files…'
            return {'ok': True}
        key = request.get('group')
        if key not in groups:
            raise ValueError('Select a current album or folder first.')
        group = groups[key]
        files = group['files']
        if action == 'scan':
            if group['kind'] != 'unmatched':
                raise ValueError('Scan is for unmatched files. Open Picard to revise an existing match.')
            if not self.tagger.use_acoustid:
                raise ValueError('Enable AcoustID fingerprinting in Picard settings before scanning.')
            self.tagger.analyze(files)
            self.message = 'Scanning unmatched audio…'
        elif action == 'remove':
            self.tagger.remove_files(list(files))
            self.message = 'Removed without saving · files remain on disk'
        elif action == 'save':
            from picard.file import File
            candidates = [f for f in files if f in group['safe'] and f.state in (File.State.NORMAL, File.State.CHANGED)]
            if not candidates:
                raise ValueError('No unambiguous matched tracks to save. Review this album in Picard.')
            self.saving.update(candidates)
            self.message = 'Saving matched tracks…'
            for f in candidates:
                try:
                    f.save()
                except Exception:
                    self.saving.discard(f)
                    self.message = 'A save could not start. The file remains in Picard.'
        else:
            raise ValueError('Unknown action.')
        return {'ok': True}
