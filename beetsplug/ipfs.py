# This file is part of beets.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Adds support for ipfs. Requires go-ipfs and a running ipfs daemon
"""
from beets import ui, library, config
from beets.plugins import BeetsPlugin

import subprocess
import shutil
import os
import tempfile


class IPFSPlugin(BeetsPlugin):

    def __init__(self):
        super(IPFSPlugin, self).__init__()

    def commands(self):
        cmd = ui.Subcommand('ipfs',
                            help='interact with ipfs')
        cmd.parser.add_option('-a', '--add', dest='add',
                                    action='store_true',
                                    help='Add to ipfs')
        cmd.parser.add_option('-g', '--get', dest='get',
                                    action='store_true',
                                    help='Get from ipfs')
        cmd.parser.add_option('-p', '--publish', dest='publish',
                                    action='store_true',
                                    help='Publish local library to ipfs')
        cmd.parser.add_option('-i', '--import', dest='_import',
                                    action='store_true',
                                    help='Import remote library from ipfs')
        cmd.parser.add_option('-l', '--list', dest='_list',
                                    action='store_true',
                                    help='List imported library')

        def func(lib, opts, args):
            if opts.add:
                for album in lib.albums(ui.decargs(args)):
                    self.ipfs_add(album)
                    album.store()

            if opts.get:
                self.ipfs_get(lib, ui.decargs(args))

            if opts.publish:
                self.ipfs_publish(lib)

            if opts._import:
                self.ipfs_import(lib, ui.decargs(args))

            if opts._list:
                self.ipfs_list(lib, ui.decargs(args))

        cmd.func = func
        return [cmd]

    def ipfs_add(self, lib):
        try:
            album_dir = lib.item_dir()
        except AttributeError:
            return
        self._log.info('Adding {0} to ipfs', album_dir)

        _proc = subprocess.Popen(["ipfs", "add", "-q", "-r", album_dir],
                                 stdout=subprocess.PIPE)

        all_lines = _proc.stdout.readlines()
        length = len(all_lines)

        for linenr, line in enumerate(all_lines):
            line = line.strip()
            if linenr == length-1:
                # last printed line is the album hash
                self._log.info("album: {0}", line)
                lib.ipfs = line
            else:
                try:
                    item = lib.items()[linenr]
                    self._log.info("item: {0}", line)
                    item.ipfs = line
                    item.store()
                except IndexError:
                    # if there's non music files in the to-add folder they'll
                    # get ignored here
                    pass

        return True

    def ipfs_get(self, lib, _hash):
        try:
            subprocess.check_output(["ipfs", "get", _hash[0]],
                                    stderr=subprocess.STDOUT)
        except subprocess.CalledProcessError as err:
            self._log.error('Failed to get {0} from ipfs.\n{1}',
                            _hash[0], err.output)
            return False

        self._log.info('Getting {0} from ipfs', _hash[0])
        imp = ui.commands.TerminalImportSession(lib, loghandler=None,
                                                query=None, paths=_hash)
        imp.run()
        shutil.rmtree(_hash[0])

    def ipfs_publish(self, lib):
        with tempfile.NamedTemporaryFile() as tmp:
            self.ipfs_added_albums(lib, tmp.name)
            _proc = subprocess.Popen(["ipfs", "add", "-q", tmp.name],
                                     stdout=subprocess.PIPE)
            self._log.info("hash of library: {0}", _proc.stdout.readline())

    def ipfs_import(self, lib, args):
        _hash = args[0]
        if len(args) > 1:
            lib_name = args[1]
        else:
            lib_name = _hash
        # TODO: should be able to tag libraries, for example by nicks
        lib_root = os.path.dirname(lib.path)
        remote_libs = lib_root + "/remotes"
        if not os.path.exists(remote_libs):
            os.makedirs(remote_libs)
        path = remote_libs + "/" + lib_name + ".db"
        subprocess.call(["ipfs", "get", _hash, "-o", path])

        # add all albums from remotes into a combined library
        jpath = remote_libs + "/joined.db"
        jlib = library.Library(jpath)
        nlib = library.Library(path)
        for album in nlib.albums():
            if not self.already_added(album, jlib):
                for item in album.items():
                    jlib.add(item)
                jlib.add(album)

    def already_added(self, check, jlib):
        for jalbum in jlib.albums():
            if jalbum.mb_albumid == check.mb_albumid:
                return True
        return False

    def ipfs_list(self, lib, args):
        lib_root = os.path.dirname(lib.path)
        remote_libs = lib_root + "/remotes"
        path = remote_libs + "/joined.db"
        rlib = library.Library(path)
        albums = rlib.albums(ui.decargs(args))
        fmt = config['format_album'].get()
        for album in albums:
            ui.print_(format(album, fmt), " : ", album.ipfs)

    def ipfs_added_albums(self, rlib, tmpname):
        """ Returns a new library with only albums/items added to ipfs
        """
        tmplib = library.Library(tmpname)
        for album in rlib.albums():
            try:
                if album.ipfs:
                    for item in album.items():
                        # Clear current path from item
                        item.path = ''
                        tmplib.add(item)
                    album.artpath = ''
                    tmplib.add(album)
            except AttributeError:
                pass
        return tmplib
