# Copyright (C) 2018 Brian J. Stucky
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.


from collections import deque

import gi
gi.require_version('Gtk', '3.0')
gi.require_version('Pango', '1.0')
from gi.repository import Gtk
from gi.repository import Pango

import os.path

from seqtrace.core.consens import ConsensSeqSettings
from seqtrace.core.observable import Observable
from seqtrace.core.stproject_io import SeqTraceProjReader, SeqTraceProjWriter
from seqtrace.gui import getDefaultFont


class TreeStoreProjectItem:
    def __init__(self, tsiter, project):
        self.tsiter = tsiter
        self.proj = project
        self.ts = project.getTreeStore()

    def getTsiter(self):
        return self.tsiter

    def isValid(self):
        return self.ts.iter_is_valid(self.tsiter)

    def getName(self):
        return self.ts.get_value(self.tsiter, FILE_NAME)

    def setName(self, newname):
        oldname = self.ts.get_value(self.tsiter, FILE_NAME)

        self.ts.set_value(self.tsiter, FILE_NAME, newname)

        if oldname != newname:
            self.proj.setSaveState(False)

    def getFileNames(self):
        if self.ts.get_value(self.tsiter, NODE_TYPE) == 'file':
            return (self.ts.get_value(self.tsiter, FILE_NAME),)
        elif self.ts.get_value(self.tsiter, NODE_TYPE) == 'frwdrev':
            f1 = self.ts.iter_children(self.tsiter)
            f2 = self.ts.iter_next(f1)
            return (self.ts.get_value(f1, FILE_NAME), self.ts.get_value(f2, FILE_NAME))

    def isFile(self):
        return self.ts.get_value(self.tsiter, NODE_TYPE) == 'file'

    def getItemType(self):
        return self.ts.get_value(self.tsiter, NODE_TYPE)

    def setItemType(self, newtype):
        oldval = self.ts.get_value(self.tsiter, NODE_TYPE)

        self.ts.set_value(self.tsiter, NODE_TYPE, newtype)

        if oldval != newtype:
            self.proj.setSaveState(False)

    def hasSequence(self):
        return self.ts.get_value(self.tsiter, HAS_CONS)

    def getUseSequence(self):
        return self.ts.get_value(self.tsiter, USE_CONS)

    def setUseSequence(self, use_sequence):
        oldval = self.ts.get_value(self.tsiter, USE_CONS)

        self.ts.set_value(self.tsiter, USE_CONS, use_sequence)

        if oldval != use_sequence:
            self.proj.setSaveState(False)

    def toggleUseSequence(self):
        oldval = self.ts.get_value(self.tsiter, USE_CONS)
        self.ts.set_value(self.tsiter, USE_CONS, not(oldval))
        self.proj.setSaveState(False)

    def setConsensusSequence(self, compact_consens, full_consens):
        oldcons = self.ts.get_value(self.tsiter, FULL_CONS)

        self.ts.set_value(self.tsiter, COMPACT_CONS, compact_consens)
        self.ts.set_value(self.tsiter, FULL_CONS, full_consens)

        if full_consens != '':
            self.ts.set_value(self.tsiter, HAS_CONS, True)
        else:
            self.ts.set_value(self.tsiter, HAS_CONS, False)
            self.ts.set_value(self.tsiter, USE_CONS, False)

        if oldcons != full_consens:
            self.proj.setSaveState(False)

    def deleteConsensusSequence(self):
        self.setConsensusSequence('', '')

    def getCompactConsSequence(self):
        return self.ts.get_value(self.tsiter, COMPACT_CONS)

    def getFullConsSequence(self):
        return self.ts.get_value(self.tsiter, FULL_CONS)

    def getIsReverse(self):
        return self.ts.get_value(self.tsiter, IS_REVERSE)

    def setIsReverse(self, is_reverse):
        oldval = self.ts.get_value(self.tsiter, IS_REVERSE)

        self.ts.set_value(self.tsiter, IS_REVERSE, is_reverse)

        if oldval != is_reverse:
            self.proj.setSaveState(False)

    def toggleIsReverse(self):
        oldval = self.ts.get_value(self.tsiter, IS_REVERSE)
        self.ts.set_value(self.tsiter, IS_REVERSE, not(oldval))
        self.proj.setSaveState(False)

    def getNotes(self):
        return self.ts.get_value(self.tsiter, NOTES)

    def setNotes(self, newnotes):
        oldnotes = self.ts.get_value(self.tsiter, NOTES)

        self.ts.set_value(self.tsiter, NOTES, newnotes)

        if oldnotes != newnotes:
            self.proj.setSaveState(False)

    def getId(self):
        return self.ts.get_value(self.tsiter, NODE_ID)

    def hasParent(self):
        parent = self.ts.iter_parent(self.tsiter)
        if parent == None:
            return False
        else:
            return True

    def getParent(self):
        if self.hasParent():
            return TreeStoreProjectItem(self.ts.iter_parent(self.tsiter), self.proj)
        else:
            return None

    def getChildren(self):
        if self.ts.get_value(self.tsiter, NODE_TYPE) == 'frwdrev':
            ch1iter = self.ts.iter_children(self.tsiter)
            child1 = TreeStoreProjectItem(ch1iter, self.proj)
            child2 = TreeStoreProjectItem(self.ts.iter_next(ch1iter), self.proj)
            return (child1, child2)
        else:
            return ()


# An iterator to traverse all root-level items in a project.
class ProjectIter:
    def __init__(self, project):
        self.project = project
        self.ts = project.getTreeStore()
        self.length = self.ts.iter_n_children(None)
        
        self.tsiter = self.ts.get_iter_first()

    def __iter__(self):
        return self

    def __len__(self):
        return self.length

    def next(self):
        if self.tsiter != None:
            item = self.project.getItemByTsiter(self.tsiter)
            self.tsiter = self.ts.iter_next(self.tsiter)
            return item
        else:
            raise StopIteration


# Constants that specify which values are held by each column in a project's
# TreeStore.
#
# 0: file name/node name
# 1: node type (either 'file' or 'frwdrev')
# 2: node ID number
# 3: True if consensus sequence has been approved for this node
# 4: compact consensus sequence for this node
# 5: full consensus sequence for this node (with spaces)
# 6: True if this node has a consensus sequence
# 7: notes/description for an item
# 8: whether or not this is a reverse sequencing read
FILE_NAME = 0
NODE_TYPE = 1
NODE_ID = 2
USE_CONS = 3
COMPACT_CONS = 4
FULL_CONS = 5
HAS_CONS = 6
NOTES = 7
IS_REVERSE = 8

class SequenceTraceProject(Observable):
    def __init__(self):
        self.ts = Gtk.TreeStore(str, str, int, bool, str, str, bool, str, bool)

        # Make sure the TreeStore supports persistant iterators
        # since a few of the project methods require this feature.
        if (self.ts.get_flags() & Gtk.TreeModelFlags.ITERS_PERSIST) == 0:
            raise Exception

        self.numcols = 9
        self.save_state = True

        self.setConsensSeqSettings(ConsensSeqSettings())

        # initialize a blank project
        self.clearProject(False)

        # sort by file names by default
        self.setSortBy(FILE_NAME, Gtk.SortType.ASCENDING)

        # initialize observable events
        self.defineObservableEvents([
            'save_state_change', 'project_filename_change', 'files_added',
            'files_removed', 'file_loaded', 'project_cleared'
        ])

    def __iter__(self):
        return ProjectIter(self)

    def getTreeStore(self):
        return self.ts

    def clearProject(self, notify=True):
        # start numbering for node IDs at 0 by default
        self.idnum = 0
        self.project_file = ''
        self.trace_file_dir = '.'

        self.fwd_trace_searchstr = '_F'
        self.rev_trace_searchstr = '_R'

        self.default_font = getDefaultFont()

        # Copy default consensus sequence settings rather than change
        # references to a new settings object in case there are any active
        # users of the existing settings object.
        settings = ConsensSeqSettings()
        self.consseqsettings.copyFrom(settings)

        self.ts.clear()
        self.num_files = 0

        self.setSaveState(True)
        if notify:
           self.notifyObservers('project_cleared', ())

    def isProjectEmpty(self):
        return self.ts.get_iter_first() == None

    def loadProjectFile(self, filename):
        reader = SeqTraceProjReader()

        try:
            reader.readFile(filename)
        except:
            raise

        self.setTraceFileDir(reader.getProperty('trace_file_dir'))
        self.setFwdTraceSearchStr(reader.getProperty('fwd_trace_searchstr'))
        self.setRevTraceSearchStr(reader.getProperty('rev_trace_searchstr'))

        # Load the font from the string description.  One might think that this
        # could crash if a required font is not installed on a user's system,
        # but it turns out that Pango handles these situations quite
        # gracefully.  For example, if the font string is "fake font 12", Pango
        # will use a default font face and still preserve the preferred size
        # (12, in this case).
        fontstr = reader.getProperty('default_font')
        fontdesc = Pango.FontDescription.from_string(fontstr)
        self.setFont(fontdesc)

        self.consseqsettings.copyFrom(reader.getConsensSeqSettings())

        # Load the data into the TreeStore.
        for item in reader:
            row = self.ts.append(
                None, (
                    item.getName(), item.getItemType(), self.idnum,
                    item.getUseSequence(), item.getCompactConsSequence(),
                    item.getFullConsSequence(), item.hasSequence(),
                    item.getNotes(), item.getIsReverse()
                )
            )
            self.idnum += 1
            if item.isFile():
                self.num_files += 1

            for child in item.getChildren():
                self.ts.append(
                    row, (
                        child.getName(), child.getItemType(), self.idnum,
                        child.getUseSequence(), child.getCompactConsSequence(),
                        child.getFullConsSequence(), child.hasSequence(),
                        child.getNotes(), child.getIsReverse()
                    )
                )
                self.idnum += 1
                self.num_files += 1

        # store the full, normalized path for the project file
        self.project_file = os.path.abspath(filename)
        self.setSaveState(True)
        self.notifyObservers('file_loaded', ())

    def saveProjectFile(self, filename=''):
        writer = SeqTraceProjWriter()

        writer.addProperty('trace_file_dir', self.trace_file_dir)
        writer.addProperty('fwd_trace_searchstr', self.fwd_trace_searchstr)
        writer.addProperty('rev_trace_searchstr', self.rev_trace_searchstr)
        writer.addProperty('default_font', self.getFont().to_string())
        writer.setConsensSeqSettings(self.consseqsettings)

        # get each item from the project
        for item in self:
            writer.addProjectItem(item)

        if filename == '':
            filename = self.project_file

        try:
            writer.write(filename)
        except:
            raise

        self.setSaveState(True)

    def addFiles(self, filepaths):
        for fpath in filepaths:
            rel_fpath = os.path.relpath(fpath, self.getAbsTraceFileDir())

            # Consider newly-added trace files to be forward reads by default...
            is_rev = False
            # unless they match the reverse search string.
            if os.path.basename(rel_fpath).find(self.getRevTraceSearchStr()) != -1:
                is_rev = True

            # add the new trace file
            self.ts.append(None, (rel_fpath, 'file', self.idnum, False, '', '', False, '', is_rev))
            self.idnum += 1
            self.num_files += 1

        self.setSaveState(False)
        self.notifyObservers('files_added', ())

    # rev_index specifies which one of the items should be treated as a reverse sequencing read.  If
    # index < 0 or index > 1, neither item will be marked as a reverse read.
    def associateItems(self, items, node_name):
        # verify we only got two rows
        if len(items) != 2:
            raise Exception()

        # get treestore references to the selected rows
        f1 = items[0].getTsiter()
        f2 = items[1].getTsiter()

        # make sure they are both files
        if not(items[0].isFile()) or not(items[1].isFile()):
            raise Exception()

        # make sure they are both at the root level
        if (items[0].hasParent()) or (items[1].hasParent()):
            raise Exception()

        # create a new associative node and add the selected nodes as children
        parent = self.ts.insert_before(None, f1, (node_name, 'frwdrev', self.idnum, False, '', '', False, '', False))
        self.idnum += 1

        self.moveRowToParent(f1, parent)
        self.moveRowToParent(f2, parent)

        self.setSaveState(False)

        return TreeStoreProjectItem(parent, self)

    def setSortBy(self, item_property, order):
        self.ts.set_sort_column_id(item_property, order)

    def getFwdTraceSearchStr(self):
        return self.fwd_trace_searchstr

    def getRevTraceSearchStr(self):
        return self.rev_trace_searchstr

    def setFwdTraceSearchStr(self, new_str):
        if self.fwd_trace_searchstr != new_str:
            self.fwd_trace_searchstr = new_str
            self.setSaveState(False)

    def setRevTraceSearchStr(self, new_str):
        if self.rev_trace_searchstr != new_str:
            self.rev_trace_searchstr = new_str
            self.setSaveState(False)

    def getConsensSeqSettings(self):
        return self.consseqsettings

    def setConsensSeqSettings(self, settings):
        self.consseqsettings = settings
        self.consseqsettings.registerObserver('settings_change', (lambda: self.setSaveState(False)))

    def getFont(self):
        return self.default_font

    def setFont(self, fontdesc):
        self.default_font = fontdesc

    def getSaveState(self):
        return self.save_state

    def setSaveState(self, save_state):
        if save_state != self.save_state:
            self.save_state = save_state
            self.notifyObservers('save_state_change', (self.save_state,))

    def getProjectFileName(self):
        return self.project_file

    def setProjectFileName(self, fname):
        # store the new file name as a full, normalized path
        newpf = os.path.abspath(fname)

        # if the current trace file folder is stored as a relative path, it needs to be updated
        # for the new project path
        if not(os.path.isabs(self.getTraceFileDir())):
            self.setTraceFileDir(os.path.relpath(self.getAbsTraceFileDir(), os.path.dirname(newpf)))

        self.project_file = newpf
        self.notifyObservers('project_filename_change', (self.project_file,))

    def getProjectDir(self):
        return os.path.dirname(self.project_file)

    def getTraceFileDir(self):
        return self.trace_file_dir

    def setTraceFileDir(self, trace_file_dir):
        if self.trace_file_dir != trace_file_dir:
            self.trace_file_dir = trace_file_dir
            self.setSaveState(False)
    
    def getAbsTraceFileDir(self):
        return os.path.abspath(os.path.join(self.getProjectDir(), self.getTraceFileDir()))

    def isFileInProject(self, fpath):
        rel_fpath = os.path.relpath(fpath, self.getAbsTraceFileDir())

        # search for the file name in the treestore
        # this algorithm avoids recursive calls but assumes that the tree
        # is no more than two levels deep
        for row in self.ts:
            if (row[NODE_TYPE] == 'file') and (row[FILE_NAME] == rel_fpath):
                return True
            for childrow in row.iterchildren():
                if (childrow[NODE_TYPE] == 'file') and (childrow[FILE_NAME] == rel_fpath):
                    return True
        return False

    def getNumItems(self):
        return self.ts.iter_n_children(None)

    def getNumFiles(self):
        return self.num_files

    def getItemById(self, idnum):
        # search for the specified row ID in the treestore
        # this algorithm avoids recursive calls but assumes that the tree
        # is no more than two levels deep
        for row in self.ts:
            if row[NODE_ID] == idnum:
                return TreeStoreProjectItem(row.iter, self)
            for childrow in row.iterchildren():
                if childrow[NODE_ID] == idnum:
                    return TreeStoreProjectItem(childrow.iter, self)

        return None

    def getItemByPath(self, path):
        tsiter = self.ts.get_iter(path)
        return TreeStoreProjectItem(tsiter, self)

    def getItemsByPaths(self, pathlist):
        items = list()
        for path in pathlist:
            items.append(self.getItemByPath(path))

        return items

    def getItemByTsiter(self, tsiter):
        return TreeStoreProjectItem(tsiter, self)

    def removeAssociativeItem(self, item):
        # make sure it is a file association row
        if item.isFile():
            raise Exception()

        # get a treestore reference to the item
        f1 = item.getTsiter()

        # move the child nodes to the root level
        citer = self.ts.iter_children(f1)
        while citer != None:
            self.moveRowToParent(citer, None)
            citer = self.ts.iter_children(f1)

        # delete the associative node
        self.ts.remove(f1)

        self.setSaveState(False)

    def removeFileItems(self, itemlist):
        parent_items = list()

        # delete the items that are actually files
        for item in itemlist:
            if item.isFile():
                # if this node was a child of an associative node, save a reference to the parent
                if item.hasParent():
                    parent_items.append(item.getParent())
                self.ts.remove(item.getTsiter())
                self.num_files -= 1

        # clean up parent items that have one or no children left
        for parent in parent_items:
            if parent.isValid():
                child = self.ts.iter_children(parent.getTsiter())
                if child != None:
                    data = self.ts.get(child, *range(self.numcols))
                    self.ts.remove(child)
                    self.ts.insert_before(None, parent.getTsiter(), data)
                self.ts.remove(parent.getTsiter())

        self.setSaveState(False)
        self.notifyObservers('files_removed', ())

    def moveRowToParent(self, row, parent):
        data = self.ts.get(row, *range(self.numcols))
        self.ts.remove(row)
        self.ts.append(parent, data)

    def getFwdRevMatchIter(self, itemlist=None):
        items = deque()

        if itemlist == None:
            # get all root-level items that point to trace files
            for item in self:
                if item.isFile():
                    items.appendleft(item)
        else:
            # get all root-level items in the list that point to trace files
            for item in itemlist:
                if not(item.hasParent()) and item.isFile():
                    items.appendleft(item)

        return FwdRevMatchIter(items, self)


class FwdRevMatchIter:
    def __init__(self, items, project):
        self.items = items
        self.ts = project.getTreeStore()
        self.fwd_str = project.getFwdTraceSearchStr()
        self.rev_str = project.getRevTraceSearchStr()

    def __iter__(self):
        return self

    # returns a 3-tuple containing one matching pair plus their shared name: (forward file, reverse file, shared name)
    def next(self):
        while len(self.items) > 1:
            item1 = self.items.pop()
            item2 = None

            item1file = item1.getName()

            # see if this is a forward file
            if item1file.find(self.fwd_str) != -1:
                item2, sharedname = self.getMatch(item1file, self.fwd_str, self.rev_str)
                if item2 != None:
                    # return the matching pair
                    self.items.remove(item2)
                    return (item1, item2, sharedname)

            # if the forward match failed, see if it is a reverse file
            if (item2 == None) and (item1file.find(self.rev_str) != -1):
                item2, sharedname = self.getMatch(item1file, self.rev_str, self.fwd_str)
                if item2 != None:
                    # return the matching pair
                    self.items.remove(item2)
                    return (item2, item1, sharedname)

        raise StopIteration

    def getMatch(self, name, key1, key2):
        """ Searches for key1 in name and checks if any names with key2 substituted for key1 exist
        in self.items.  If key occurs more than once in name, each match of key1 in name is checked
        separately.  If a matching item is found, the search is stopped and the matching item is
        returned with the shared name; otherwise, None and '' are returned. """

        item2 = None
        sharedname = ''

        # find all matches of key1 in the name
        split = name.split(key1)

        # Go through each match of key1 in the name, construct the "opposite" name, and
        # see if it exists in self.items.  Quit as soon as a matching opposite is found.
        for cnt in range(1, len(split)):
            # construct the "opposite" name
            matchfile = key1.join(split[:cnt]) + key2 + key1.join(split[cnt:])
            # construct the common name shared by the pair
            sharedname = key1.join(split[:cnt]) + key1.join(split[cnt:])

            # now try to find the other file of the pair
            for item in self.items:
                if item.getName() == matchfile:
                    item2 = item
                    break

            if item2 != None:
                break

        return (item2, sharedname)

