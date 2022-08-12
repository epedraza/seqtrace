#!/usr/bin/python
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


from struct import unpack, pack
import struct
import zlib
import os.path
from datetime import datetime
import math


class TraceFileError(Exception):
    pass

class UnknownFileTypeError(TraceFileError):
    def __str__(self):
        return 'The file format was not recognized.  Please convert the file to a supported format and try again.'


# Constants for sequence trace file types.
ST_UNKNOWN = 0
ST_ZTR = 1
ST_ABI = 2
ST_SCF = 3

class SequenceTraceFactory:
    @staticmethod
    def getTraceFileType(filename):
        try:
            tf = open(filename, 'rb')
        except IOError:
            raise
    
        # read the "magic number" from the file
        magicval = tf.read(8)
        tf.close()
        #print magicval
    
        if magicval[0:4] == b'ABIF':
            return ST_ABI
        elif magicval == b'\256ZTR\r\n\032\n':
            return ST_ZTR
        elif magicval[0:4] == b'.scf':
            return ST_SCF
        else:
            return ST_UNKNOWN

    @staticmethod
    def loadTraceFile(filepath):
        try:
            ftype = SequenceTraceFactory.getTraceFileType(filepath)
        except:
            raise
        
        if ftype == ST_ZTR:
            seqt = ZTRSequenceTrace()
        elif ftype == ST_ABI:
            seqt = ABISequenceTrace()
        elif ftype == ST_SCF:
            seqt = SCFSequenceTrace()
        elif ftype == ST_UNKNOWN:
            raise UnknownFileTypeError

        seqt.loadFile(filepath)

        return seqt


# Define the reverse complement lookup table.
rclookup = {
    'a': 't', 't': 'a', 'g': 'c', 'c': 'g',
    'w': 'w', 's': 's', 'm': 'k', 'k': 'm', 'r': 'y', 'y': 'r',
    'b': 'v', 'd': 'h', 'h': 'd', 'v': 'b', 'n': 'n',
    'A': 'T', 'T': 'A', 'G': 'C', 'C': 'G',
    'W': 'W', 'S': 'S', 'M': 'K', 'K': 'M', 'R': 'Y', 'Y': 'R',
    'B': 'V', 'D': 'H', 'H': 'D', 'V': 'B', 'N': 'N'}

def reverseCompSequence(sequence):
    """
    Defines a generic method for reverse complementing a sequence of nucleotide
    codes.  This method fully supports all of the IUPAC ambiguity codes.
    """
    tmp = list()
    for cnt in reversed(list(range(len(sequence)))):
        tmp.append(rclookup[sequence[cnt]])

    return ''.join(tmp)


class SequenceTrace:
    """
    Parent for all format-specific sequence trace classes.  This class defines
    the methods that are common to all sequence traces.
    """
    def __init__(self):
        self.isreverse_comped = False
        self.fname = ''
        self.tracesamps = {}
        self.max_traceval = -1
        self.comments = {}

    def loadFile(self, filename):
        pass

    def getFileName(self):
        return os.path.basename(self.fname)

    def getMaxTraceVal(self):
        return self.max_traceval

    def reverseComplement(self):
        """
        Reverse complements the trace data, including the actual sequencing
        traces, the base calls, and the quality scores.
        """
        # reverse the DNA sequence
        self.basecalls = reverseCompSequence(self.basecalls)

        # reverse and transpose the trace samples
        for base in self.tracesamps:
            self.tracesamps[base].reverse()
        tmp = self.tracesamps['A']
        self.tracesamps['A'] = self.tracesamps['T']
        self.tracesamps['T'] = tmp
        tmp = self.tracesamps['G']
        self.tracesamps['G'] = self.tracesamps['C']
        self.tracesamps['C'] = tmp

        # reverse the confidence scores
        self.bcconf.reverse()

        # reverse and shift the base call positions
        self.basepos.reverse()
        endsamp = len(self.tracesamps['A']) - 1
        for cnt in range(len(self.basepos)):
            self.basepos[cnt] = endsamp - self.basepos[cnt]

        self.isreverse_comped = not(self.isreverse_comped)

    def isReverseComplemented(self):
        return self.isreverse_comped

    def getTraceSamples(self, base):
        """
        Returns the actual trace data for a particular base.
        """
        return self.tracesamps[base.upper()]

    def getTraceSample(self, base, index):
        """
        Return the magnitude of the trace data at the location in the trace
        specified by index.
        """
        return self.tracesamps[base.upper()][index]

    def getTraceLength(self):
        return len(self.tracesamps['A'])

    def getBaseCalls(self):
        return self.basecalls

    def getBaseCall(self, index):
        return self.basecalls[index]

    def getNumBaseCalls(self):
        return len(self.basecalls)

    def getBaseCallPos(self, index):
        return self.basepos[index]

    def getBaseCallConf(self, index):
        return self.bcconf[index]

    # If sampnum < the first base call location, returns the first base call
    # location.
    def getPrevBaseCallIndex(self, sampnum):
        # Do a binary search for the index of the base call located at, or
        # immediately before, sampnum.
        minv = 0
        maxv = len(self.basepos) - 1
        while maxv > (minv + 1):
            test = int((maxv-minv)/2) + minv
            if self.basepos[test] == sampnum:
                return test
            elif self.basepos[test] > sampnum:
                maxv = test
            else:
                minv = test

        if self.basepos[maxv] <= sampnum:
            return maxv
        else:
            return minv

    # If sampnum > the last base call location, returns the last base call
    # location.
    def getNextBaseCallIndex(self, sampnum):
        # Do a binary search for the index of the base call located at, or
        # immediately after, sampnum.
        minv = 0
        maxv = len(self.basepos) - 1

        while maxv > (minv+1):
            test = int((maxv-minv)/2) + minv
            #print 'minv, maxv, test:', minv, maxv, test
            if self.basepos[test] == sampnum:
                return test
            elif self.basepos[test] > sampnum:
                maxv = test
            else:
                minv = test

        if self.basepos[minv] >= sampnum:
            return minv
        else:
            return maxv

    def getComment(self, key):
        if key in self.comments:
            return self.comments[key]
        else:
            return None

    def getComments(self):
        return self.comments


class ZTRError(TraceFileError):
    pass

class ZTRVersionError(ZTRError):
    def __init__(self, ver_major, ver_minor):
        self.ver_major = ver_major
        self.ver_minor = ver_minor

    def __str__(self):
        return 'This file uses version ' + str(self.ver_major) + '.' + str(self.ver_minor) + ' of the ZTR format.  This software only supports version 1.2 of the format.'

class ZTRDataFormatError(ZTRError):
    def __init__(self, format_id):
        self.format_id = format_id

    def __str__(self):
        return 'The ZTR data format ID ' + str(self.format_id) + ' is invalid or not supported.'

class ZTRMissingDataError(ZTRError):
    def __init__(self, expectedlen, actuallen):
        self.expectedlen = expectedlen
        self.actuallen = actuallen

    def __str__(self):
        return 'Error reading ZTR data chunk.  Expected ' + str(self.expectedlen) + ' bytes but only got ' + str(self.actuallen) + ' bytes.  The file appears to be damaged.'


class ZTRSequenceTrace(SequenceTrace):
    def loadFile(self, filename):
        self.fname = filename

        try:
            tf = open(filename, 'rb')
        except IOError:
            raise

        # read the header
        self.magicnum = tf.read(8)
        if self.magicnum != '\256ZTR\r\n\032\n':
            raise ZTRError('The ZTR file header is invalid.  The file appears to be damaged.')

        try:
            self.ver_major = unpack('b', tf.read(1))[0]
            self.ver_minor = unpack('b', tf.read(1))[0]
            #print 'major version number:', ver_major
            #print 'minor version number:', ver_minor
        except struct.error:
            raise ZTRError('The ZTR file header is invalid.  The file appears to be damaged.')

        if (self.ver_major != 1) or (self.ver_minor != 2):
            raise ZTRVersionError(self.ver_major, self.ver_minor)

        # read and process the data chunks
        chunk = self.readChunk(tf)
        while chunk != False:
            #print 'chunk type:', chunk[0]
            #print 'compressed data length:', chunk[1]
            #print 'uncompressed data length:', len(chunk[2])
            if chunk[0] == 'SMP4':
                # trace sample data
                self.readTraceSamples(chunk[2])
            elif chunk[0] == 'BASE':
                # base calls
                self.basecalls = chunk[2][1:].upper()
            elif chunk[0] == 'BPOS':
                # positions of base calls relative to trace samples
                self.basepos = list()
                # skip 4 leading null bytes
                for cnt in range(4, len(chunk[2]), 4):
                    self.basepos.append(unpack('>I', chunk[2][cnt:cnt+4])[0])
            elif chunk[0] == 'CNF4':
                # confidence scores; this is required to come after a BASE chunk
                self.bcconf = list()
                for cnt in range(1, self.getNumBaseCalls()+1):
                    self.bcconf.append(unpack('b', chunk[2][cnt])[0])
            elif chunk[0] == 'TEXT':
                # get the comment key/value strings, ignoring leading/trailing null characters
                keyvals = chunk[2][1:-2].split('\0')
                for cnt in range(0, len(keyvals), 2):
                    #print keyvals[cnt] + ': ' + keyvals[cnt+1]
                    self.comments[keyvals[cnt]] = keyvals[cnt+1]

            chunk = self.readChunk(tf)

    def readTraceSamples(self, chunkdata):
        self.max_traceval = 0
        tracelen = (len(chunkdata) - 2) / 4

        offset = 2
        basenum = 0
        for base in ['A','C','G','T']:
            thisbase = list()
            start = basenum*tracelen + offset
            for cnt in range(0, tracelen, 2):
                val = unpack('>H', chunkdata[start+cnt:start+cnt+2])[0]
                thisbase.append(val)

            tmpmax = max(thisbase)
            if tmpmax > self.max_traceval:
                self.max_traceval = tmpmax
            self.tracesamps[base] = thisbase
            basenum += 1

    def zlibUncompress(self, cdata):
        # In examining the Staden package source code, it appears that the
        # 4-byte data length integer is not guaranteed to be in big-endian byte
        # order.  Might this be a bug in the Staden code?  For this reason,
        # native byte order is used here (in fact, using big-endian order will
        # cause this to fail on an x86 machine).
        udatalen = unpack('I', cdata[:4])[0]
    
        udata = zlib.decompress(cdata[4:])

        #print 'expected uncompressed data length:', udatalen
        #print 'actual uncompressed data length:', len(udata)
        if udatalen != len(udata):
            raise ZTRError('Zlib decompression failed.  The expected data length did not match the actual data length.')
        
        return udata
    
    def RLEUncompress(self, cdata):
        # In examining the Staden package source code, it appears that the
        # 4-byte data length integer is not guaranteed to be in big-endian byte
        # order.  Might this be a bug in the Staden code?  For this reason,
        # native byte order is used here (in fact, using big-endian order will
        # cause this to fail on an x86 machine).
        udatalen = unpack('I', cdata[:4])[0]
        guard = cdata[4]
        #print unpack_from('=bIb', data[:6])
        #print 'guard byte:', guard
    
        cnt = 5
        udata = list()
        while cnt < len(cdata):
            if cdata[cnt] == guard:
                runlen = unpack('B', cdata[cnt+1])[0]
                #print 'run length:', runlen
                if runlen == 0:
                    udata.append(guard)
                    cnt += 2
                else:
                    runchar = cdata[cnt+2]
                    udata.extend(runlen*list(runchar))
                    cnt += 3
            else:
                udata.append(cdata[cnt])
                cnt += 1
    
        #print 'expected uncompressed data length:', udatalen
        #print 'actual uncompressed data length:', len(udata)
        if udatalen != len(udata):
            raise ZTRError('RLE decompression failed.  The expected data length did not match the actual data length.')
    
        return ''.join(udata)
    
    def followDecode(self, cdata):
        # read the decode table
        table = unpack('256B', cdata[:256])
        #print table
    
        udata = list()
        prev = unpack('B', cdata[256])[0]
        udata.append(cdata[256])
        for cnt in range(257, len(cdata)):
            diff = unpack('b', cdata[cnt])[0]
            actual = table[prev] - diff

            # simulate 1-byte unsigned overflow/underflow, if needed
            if actual < 0:
                actual += 256
            elif actual > 255:
                #print actual,(actual-256), table[prev], diff
                actual -= 256

            prev = actual
            #print actual
            udata.append(pack('B', actual))
        
        return ''.join(udata)
    
    def decode16To8(self, cdata):
        cnt = 0
        udata = list()
        while cnt < len(cdata):
            val = unpack('b', cdata[cnt])[0]
            if (val > -128) and (val < 128):
                udata.append(pack('>h', val))
                cnt += 1
            elif val == -128:
                #print unpack('b', cdata[cnt+1])[0]
                #print unpack('b', cdata[cnt+2])[0]
                udata.extend(cdata[cnt+1:cnt+3])
                cnt += 3
            else:
                raise ZTRError('Invalid value encountered while attempting to read 16- to 8-bit encoded ZTR data.')
    
        return ''.join(udata)
    
    def decode32To8(self, cdata):
        cnt = 0
        udata = list()
        while cnt < len(cdata):
            val = unpack('b', cdata[cnt])[0]
            if (val > -128) and (val < 128):
                udata.append(pack('>i', val))
                cnt += 1
            elif val == -128:
                #print unpack('b', cdata[cnt+1])[0]
                #print unpack('b', cdata[cnt+2])[0]
                udata.extend(cdata[cnt+1:cnt+5])
                cnt += 5
            else:
                raise ZTRError('Invalid value encountered while attempting to read 32- to 8-bit encoded ZTR data.')
    
        return ''.join(udata)
    
    def decode8BitDelta(self, cdata):
        levels = unpack('b', cdata[0])[0]
        #print 'levels:', levels
    
        # first, unpack the 1-byte values
        udata = list()
        for cnt in range(1, len(cdata)):
            val = unpack('B', cdata[cnt])[0]
            udata.append(val)

        # now apply the reverse delta filtering
        for clev in range(levels):
            prev = 0
            for cnt in range(0, len(udata)):
                actual = udata[cnt] + prev
                if actual > 255:
                    # simulate 1-byte integer overflow
                    actual -= 256
                prev = actual
                udata[cnt] = actual
    
        # repack the data
        tmpdata = list()
        for val in udata:
            tmpdata.append(pack('B', val))
    
        return ''.join(tmpdata)
    
    def decode16BitDelta(self, cdata):
        levels = unpack('b', cdata[0])[0]
        #print 'levels:', levels
    
        # first, unpack the 2-byte values
        udata = list()
        for cnt in range(1, len(cdata), 2):
            val = unpack('>H', cdata[cnt:cnt+2])[0]
            udata.append(val)

        # now apply the reverse delta filtering
        for clev in range(levels):
            prev = 0
            for cnt in range(0, len(udata)):
                actual = udata[cnt] + prev
                if actual > 65535:
                    # simulate 2-byte integer overflow
                    actual -= 65536
                prev = actual
                udata[cnt] = actual
    
        # repack the data
        tmpdata = list()
        for val in udata:
            tmpdata.append(pack('>H', val))
    
        return ''.join(tmpdata)
    
    def decode32BitDelta(self, cdata):
        levels = unpack('b', cdata[0])[0]
        #print 'levels:', levels
    
        # first, unpack the 4-byte values (skipping the 2 padding bytes)
        udata = list()
        for cnt in range(3, len(cdata), 4):
            val = unpack('>I', cdata[cnt:cnt+4])[0]
            udata.append(val)

        # now apply the reverse delta filtering
        for clev in range(levels):
            prev = 0
            for cnt in range(0, len(udata)):
                actual = udata[cnt] + prev
                if actual > 4294967295:
                    # simulate 1-byte integer overflow
                    actual -= 4294967296
                prev = actual
                udata[cnt] = actual
    
        # repack the data
        tmpdata = list()
        for val in udata:
            tmpdata.append(pack('>I', val))
    
        return ''.join(tmpdata)
    
    def readChunk(self, fp):
        # get the chunk descriptor
        chtype = fp.read(4)
        #print 'chunk type:', chtype

        # check for EOF
        if len(chtype) == 0:
            return False
        elif len(chtype) != 4:
            raise ZTRError('The ZTR data chunk type could not be read.  The file appears to be damaged.')
    
        try:
            mdlen = unpack('>I', fp.read(4))[0]
            #print 'metadata length:', mdlen
    
            # skip over the metadata
            fp.read(mdlen)
    
            # get the size of the data
            datalen = unpack('>I', fp.read(4))[0]
            #print 'data length:', datalen
        except struct.error:
            raise ZTRError('The ZTR data chunk header could not be read.  The file appears to be damaged.')

        # read the chunk data from the file
        data = fp.read(datalen)
        if datalen != len(data):
            raise ZTRMissingDataError(datalen, len(data))
    
        # Iteratively process the chunk data until we get the "raw",
        # uncompressed data.
        dataformat = unpack('b', data[0])[0]
        while dataformat != 0:
            #print 'data format:', dataformat
            if dataformat == 1:
                # run-length encoding
                data = self.RLEUncompress(data[1:])
            elif dataformat == 2:
                # zlib encoding
                data = self.zlibUncompress(data[1:])
            elif dataformat == 64:
                # 8-bit delta encoded
                data = self.decode8BitDelta(data[1:])
            elif dataformat == 65:
                # 16-bit delta encoded
                data = self.decode16BitDelta(data[1:])
            elif dataformat == 66:
                # 32-bit delta encoded
                data = self.decode32BitDelta(data[1:])
            elif dataformat == 70:
                # 16 to 8 bit conversion
                data = self.decode16To8(data[1:])
            elif dataformat == 71:
                # 32 to 8 bit conversion
                data = self.decode32To8(data[1:])
            elif dataformat == 72:
                # 'follow' encoding
                data = self.followDecode(data[1:])
            else:
                # invalid/unsupported data format
                raise ZTRDataFormatError(dataformat)

            dataformat = unpack('b', data[0])[0]
    
        return (chtype, datalen, data)


class ABIError(TraceFileError):
    pass

class ABIVersionError(ABIError):
    def __init__(self, ver_major, ver_minor):
        self.ver_major = ver_major
        self.ver_minor = ver_minor

    def __str__(self):
        return 'This file uses version ' + str(self.ver_major) + '.' + str(self.ver_minor) + ' of the ABI format.  This software only supports version 1.x of the format.'

class ABIIndexError(ABIError):
    def __init__(self, indexnum, indextotal):
        self.indexnum = indexnum
        self.indextotal = indextotal

    def __str__(self):
        return 'Error reading ABI file index entry ' + str(self.indexnum) + ' of ' + str(self.indextotal) + ' expected entries.  The file might be damaged.'

class ABIDataError(ABIError):
    def __init__(self, expectedlen, actuallen):
        self.expectedlen = expectedlen
        self.actuallen = actuallen

    def __str__(self):
        return 'Error reading ABI file data.  Expected ' + str(self.expectedlen) + ' bytes but only got ' + str(self.actuallen) + ' bytes.  The file appears to be damaged.'


class ABISequenceTrace(SequenceTrace):
    def loadFile(self, filename):
        self.fname = filename

        try:
            self.tf = open(filename, 'rb')
        except IOError:
            raise

        self.abiindex = list()

        # read the ABI magic number
        abinum = self.tf.read(4)
        #print abinum
        if abinum != b'ABIF':
            raise ABIError('The ABI file header is invalid.  The file appears to be damaged.')

        # check the major version number
        try:
            version = unpack('>H', self.tf.read(2))[0]
        except struct.error:
            raise ABIError('The ABI file header is invalid.  The file appears to be damaged.')
        if int(version / 100) != 1:
            raise ABIVersionError(version / 100, version % 100)
        
        # skip the next 10 bytes
        self.tf.read(10)
        
        # get the file index information
        try:
            index_entry_len = unpack('>h', self.tf.read(2))[0]
            self.num_index_entries = unpack('>i', self.tf.read(4))[0]
            total_index_size = unpack('>i', self.tf.read(4))[0]
            self.index_offset = unpack ('>i', self.tf.read(4))[0]
        except struct.error:
            raise ABIError('The ABI file header is invalid.  The file appears to be damaged.')
        
        #print index_entry_len, self.num_index_entries, total_index_size, self.index_offset

        self.readABIIndex()
        
        self.readBaseCalls()
        self.readConfScores()
        self.readTraceData()
        self.readBaseLocations()
        self.readComments()
        
    def readABIIndex(self):
        # read the ABI index block
        self.tf.seek(self.index_offset, 0)

        for cnt in range(self.num_index_entries):
            try:
                self.abiindex.append(dict(did=0, idv=0, dformat=0, fsize=0, dcnt=0, dlen=0, offset=0))
                self.abiindex[cnt]['did'] = self.tf.read(4)
                self.abiindex[cnt]['idv'] = unpack('>I', self.tf.read(4))[0]
                self.abiindex[cnt]['dformat'] = unpack('>H', self.tf.read(2))[0]
                self.abiindex[cnt]['fsize'] = unpack('>H', self.tf.read(2))[0]
                self.abiindex[cnt]['dcnt'] = unpack('>I', self.tf.read(4))[0]
                self.abiindex[cnt]['dlen'] = unpack('>I', self.tf.read(4))[0]
                self.abiindex[cnt]['offset'] = unpack('>I', self.tf.read(4))[0]
                # skip 4 bytes (the unused "data handle" field)
                self.tf.read(4)
            except struct.error:
                raise ABIIndexError(cnt, self.num_index_entries)
        
        #self.printABIIndex('CMNT')

    def printABIIndex(self, data_id):
        for entry in self.abiindex:
            if entry['did'] == data_id:
                print('entry ID:', entry['did'])
                print('idv:', entry['idv'])
                print('data format:', entry['dformat'])
                print('format size:', entry['fsize'])
                print('data count:', entry['dcnt'])
                print('total data length:', entry['dlen'])
                print('data offset:', entry['offset'])

    def getIndexEntry(self, data_id, number):
        data_id = data_id.encode() # str to binary
        for row in self.abiindex:
            if (row['did'] == data_id) and (row['idv'] == number):
                return row
    
        return None
    
    def getIndexEntriesById(self, data_id):
        entries = list()
        data_id = data_id.encode()
        for row in self.abiindex:
            if row['did'] == data_id:
                entries.append(row)
    
        return entries
    
    def readComments(self):
        """
        Attempts to get a bunch of information about the sequencing run from
        the ABI file.  As much as possible, the keys used for individual
        comment values correspond with the keys used for the same values by the
        Staden software package.  However, this method also retrieves some
        comments that are not read by the Staden package.  To avoid confusion,
        these additional comment values are not given 4-letter keys.
        """
        # get the sample name
        entry = self.getIndexEntry('SMPL', 1)
        if entry:
            self.comments['NAME'] = self.readString(entry)

        # get the run name
        entry = self.getIndexEntry('RunN', 1)
        if entry:
            self.comments['Run name'] = self.readString(entry)

        # get the lane number
        entry = self.getIndexEntry('LANE', 1)
        if entry:
            self.comments['LANE'] = str(self.read2ByteInts(entry)[0])

        # get the signal strengths for each dye
        entry = self.getIndexEntry('S/N%', 1)
        if entry:
            stvals = self.read2ByteInts(entry)

            # use the "filter wheel order" to determine the base/value pairings
            order = self.getBaseDataOrder()
            sigst = {}
            for cnt in range(0, len(order)):
                sigst[order[cnt]] = stvals[cnt]

            self.comments['SIGN'] = 'A={0},C={1},G={2},T={3}'.format(
                sigst['A'], sigst['C'], sigst['G'], sigst['T']
            )

        # get the average peak spacing
        entry = self.getIndexEntry('SPAC', 1)
        if entry:
            spacing = self.read4ByteFloats(entry)[0]
            # If spacing is invalid, estimate it ourselves (the Staden code
            # [seqIOABI.c] indicates this is a possibility).
            if spacing < 0:
                spacing = float(self.basepos[-1] - self.basepos[0]) / (len(self.basepos) - 1)
            self.comments['SPAC'] = '{0:.2f}'.format(spacing)

        # get the run dates and times
        d_entries = self.getIndexEntriesById('RUND')
        t_entries = self.getIndexEntriesById('RUNT')
        if (len(d_entries) > 1) and (len(t_entries) > 1):
            sdate = self.readDateTime(
                self.getIndexEntry('RUND', 1), self.getIndexEntry('RUNT', 1)
            )
            edate = self.readDateTime(
                self.getIndexEntry('RUND', 2), self.getIndexEntry('RUNT', 2)
            )
            #print sdate, edate
            self.comments['RUND'] = sdate.strftime('%Y%m%d.%H%M%S') + ' - ' + edate.strftime('%Y%m%d.%H%M%S')
            self.comments['DATE'] = sdate.strftime('%a %d %b %H:%M:%S %Y') + ' to ' + edate.strftime('%a %d %b %H:%M:%S %Y')

        # get the data collection dates and times
        if (len(d_entries) == 4) and (len(t_entries) == 4):
            sdate = self.readDateTime(self.getIndexEntry('RUND', 3), self.getIndexEntry('RUNT', 3))
            edate = self.readDateTime(self.getIndexEntry('RUND', 4), self.getIndexEntry('RUNT', 4))
            #print sdate, edate
            self.comments['Data coll. dates/times'] = sdate.strftime('%a %d %b %H:%M:%S %Y') + ' to ' + edate.strftime('%a %d %b %H:%M:%S %Y')

        # get the dye set/primer (mobility) file
        entry = self.getIndexEntry('PDMF', 1)
        if entry:
            self.comments['DYEP'] = self.readString(entry)

        # get the sequencing machine name and serial number
        entry = self.getIndexEntry('MCHN', 1)
        if entry:
            self.comments['MACH'] = self.readString(entry)

        # get the sequencing machine model
        entry = self.getIndexEntry('MODL', 1)
        if entry:
            self.comments['MODL'] = self.readString(entry)

        # get the basecaller name
        entry = self.getIndexEntry('SPAC', 2)
        if entry:
            self.comments['BCAL'] = self.readString(entry)

        # get the data collection software version
        entry = self.getIndexEntry('SVER', 1)
        if entry:
            self.comments['VER1'] = self.readString(entry)

        # get the basecaller version
        entry = self.getIndexEntry('SVER', 2)
        if entry:
            self.comments['VER2'] = self.readString(entry)

        # get the plate size
        entry = self.getIndexEntry('PSZE', 1)
        if entry:
            self.comments['Plate size'] = str(self.read4ByteInts(entry)[0])

        # Get the gel name.
        # This is included here because it is read by the Staden package, but
        # it does not appear to be included in the modern ABIF documentation.
        entry = self.getIndexEntry('GELN', 1)
        if entry:
            self.comments['GELN'] = self.readString(entry)

        # Get the instrument (matrix) file.
        # This is included here because it is read by the Staden package, but
        # it does not appear to be included in the modern ABIF documentation.
        entry = self.getIndexEntry('MTXF', 1)
        if entry:
            self.comments['MTXF'] = self.readString(entry)

        # 'APrX' points to a long XML string with detailed information about
        # the analysis protocol used.
        #entry = self.getIndexEntry('APrX', 1)
        #if entry:
        #    self.readString(entry)

    def readDateTime(self, dateindexrow, timeindexrow):
        # date format:
        #   bits 31-16: year
        #   bits 15-8: month
        #   bits 7-0: day of month
        # time format:
        #   bits 31-24: hour
        #   bits 23-16: minutes
        #   bits 15-8: seconds
        datenum = self.read4ByteInts(dateindexrow)[0]
        timenum = self.read4ByteInts(timeindexrow)[0]
        dateobj = datetime(
            year=(datenum >> 16), month=((datenum >> 8) & 0xff),
            day=(datenum & 0xff), hour=(timenum >> 24),
            minute=((timenum >> 16) & 0xff), second=((timenum >> 8) & 0xff)
        )

        return dateobj

    def readString(self, indexrow):
        if indexrow['fsize'] != 1:
            raise ABIError('Index entry contains an invalid format size for string data.')
        if indexrow['dformat'] not in (2, 18, 19):
            raise ABIError('Index entry contains an invalid data type for character data.')
    
        if indexrow['dlen'] <= 4:
            # The actual data are stored in the offset field of the index
            # entry.  Because the offset was read as an unsigned, big-endian
            # integer, the bytes should be in the correct order for the
            # following bit shift operations.
            lst = list()
            for cnt in range(0, indexrow['dcnt']):
                val = (indexrow['offset'] >> ((3 - cnt) * 8)) & 0xff
                lst.append(chr(val))
    
            strval = ''.join(lst)
        else:
            # get the data from the file
            self.tf.seek(indexrow['offset'], 0)
            strval = self.tf.read(indexrow['dcnt'])
    
        if indexrow['dlen'] != len(strval):
            raise ABIDataError(indexrow['dlen'], len(strval))

        # If this is a Pascal-style string (format 18), then remove the first
        # character (which specifies the string length).  If this is a C-style
        # string (format 19), then remove the trailing null character.
        if indexrow['dformat'] == 18:
            strval = strval[1:]
        elif indexrow['dformat'] == 19:
            strval = strval[:-1]

        return strval
    
    def read1ByteInts(self, indexrow):
        if indexrow['fsize'] != 1:
            raise ABIError('Index entry contains an invalid format size for 1-byte integers.')
    
        # see if the data format is signed or unsigned
        if indexrow['dformat'] == 1:
            formatstr = 'B'
        elif indexrow['dformat'] == 2:
            formatstr = 'b'
        else:
            raise ABIError('Index entry contains an invalid data type ID for 1-byte integers.')

        lst = list()
    
        if indexrow['dlen'] <= 4:
            # The actual data are stored in the offset field of the index
            # entry.  Because the offset was read as an unsigned, big-endian
            # integer, the bytes should be in the correct order for the
            # following bit shift operations.
            # First, repack the integer to deal with the possibility of signed
            # integers (shift operations would only return positive values).
            data = pack('>I', indexrow['offset'])
            for cnt in range(0, indexrow['dcnt']):
                val = unpack(formatstr, data[cnt:cnt+1])[0]
                lst.append(val)
        else:
            # get the data from the file
            self.tf.seek(indexrow['offset'], 0)
            for cnt in range(0, indexrow['dcnt']):
                lst.append(unpack(formatstr, self.tf.read(1))[0])
    
        if indexrow['dlen'] != len(lst):
            raise ABIDataError(indexrow['dlen'], len(lst))

        return lst
    
    def read2ByteInts(self, indexrow):
        if indexrow['fsize'] != 2:
            raise ABIError('Index entry contains an invalid format size for 2-byte integers.')

        # see if the data format is signed or unsigned
        if indexrow['dformat'] == 3:
            formatstr = '>H'
        elif indexrow['dformat'] == 4:
            formatstr = '>h'
        else:
            raise ABIError('Index entry contains an invalid data type ID for 2-byte integers.')
    
        lst = list()
    
        if indexrow['dlen'] <= 4:
            # The actual data are stored in the offset field of the index
            # entry.  Because the offset was read as an unsigned, big-endian
            # integer, the bytes should be in the correct order for the
            # following operations.
            # First, repack the integer to deal with the possibility of signed
            # integers (shift operations would only return positive values).
            data = pack('>I', indexrow['offset'])
            for cnt in range(0, indexrow['dcnt']):
                val = unpack(formatstr, data[cnt*2:cnt*2+2])[0]
                lst.append(val)
        else:
            # get the data from the file
            self.tf.seek(indexrow['offset'], 0)
            for cnt in range(0, indexrow['dcnt']):
                lst.append(unpack(formatstr, self.tf.read(2))[0])
    
        if indexrow['dlen'] != (len(lst) * 2):
            raise ABIDataError(indexrow['dlen'], (len(lst) * 2))
    
        return lst
    
    def read4ByteInts(self, indexrow):
        if indexrow['fsize'] != 4:
            raise ABIError('Index entry contains an invalid format size for 4-byte integers.')
        if indexrow['dformat'] not in (5, 10, 11):
            raise ABIError('Index entry contains an invalid data type ID for 4-byte integers.')
    
        lst = list()
    
        if indexrow['dlen'] == 4:
            # The actual data are stored in the offset field of the index
            # entry.  In the case of 4-byte ints, the offset value is the data
            # value.  It must be repacked, though, to reinterpret it as a
            # signed integer.
            data = pack('>I', indexrow['offset'])
            val = unpack('>i', data)[0]
            lst.append(val)
        else:
            # get the data from the file
            self.tf.seek(indexrow['offset'], 0)
            for cnt in range(0, indexrow['dcnt']):
                lst.append(unpack('>i', self.tf.read(4))[0])
    
        if indexrow['dlen'] != (len(lst) * 4):
            raise ABIDataError(indexrow['dlen'], (len(lst) * 4))
    
        return lst

    def read4ByteFloats(self, indexrow):
        if indexrow['fsize'] != 4:
            raise ABIError('Index entry contains an invalid format size for 4-byte floating point numbers.')
        if indexrow['dformat'] != 7:
            raise ABIError('Index entry contains an invalid data type ID for 4-byte floating point numbers.')
    
        lst = list()
    
        if indexrow['dlen'] <= 4:
            # The actual data are stored in the offset field of the index entry.
            data = pack('>I', indexrow['offset'])
            lst.append(unpack('>f', data)[0])
        else:
            # get the data from the file
            self.tf.seek(indexrow['offset'], 0)
            for cnt in range(0, indexrow['dcnt']):
                lst.append(unpack('>f', self.tf.read(4))[0])
    
        if indexrow['dlen'] != (len(lst) * 4):
            raise ABIDataError(indexrow['dlen'], (len(lst) * 4))
    
        return lst

    def readBaseCalls(self):
        """
        According to the ABIF documentation, ABIF files (after base calling)
        should contain two base call entries ("PBAS"): one containing "sequence
        characters edited by user" (entry number 1), and one containing
        "sequence characters as called by Basecaller" (entry number 2).  These
        two entries will, in most cases, contain identical sequence data.  This
        method follows the same convention used by the Staden package (see
        seqIOABI.c), which is to only look at entry 1 (the user-edited
        sequence) and ignore entry 2.
        """
        row = self.getIndexEntry('PBAS', 1)
        if row is None:
            raise ABIError('No base call data were found in the ABI file.  The file might be damaged.')

        # read the base calls from the file
        self.basecalls = self.readString(row).decode().upper()

    def readConfScores(self):
        """
        There is an inconsistency in the ABIF file format documentation
        regarding the data format of the confidence scores.  The data format ID
        (as actually found in a .ab1 file) is 2, indicating the values are
        signed 1-byte integers.  The ABIF documentation, however, sugggests the
        values can range from 0-255 (i.e., an unsigned 1-byte integer).  In
        practice, the actual values do not appear to exceed 61, making the
        distinction between signed/unsigned irrelevant.  For now, the data
        format ID is taken as the correct indication of the underlying data
        format.
    
        According to the ABIF documentation, ABIF files (after base calling)
        should contain two quality value (QV) entries ("PCON"): one containing
        QVs "as edited by user" (entry number 1), and one containing QVs "as
        called by Basecaller" (entry number 2).  These two entries will, in
        most cases, contain identical values.  This method follows the same
        convention used by the Staden package (see seqIOABI.c), which is to
        only look at entry 1 (the user-edited QVs) and ignore entry 2.
        """
        row = self.getIndexEntry('PCON', 1)
        if row is None:
            raise ABIError('No confidence score data were found in the ABI file.  SeqTrace requires confidence scores for all base calls.')
    
        # read the base call confidence scores from the file
        self.bcconf = self.read1ByteInts(row)
    
        return True
    
    def readBaseLocations(self):
        """
        According to the ABIF documentation, ABIF files (after base calling)
        should contain two peak location (PL) entries ("PLOC"): one containing
        PLs "edited by user" (entry number 1), and one containing PLs "as
        called by Basecaller" (entry number 2).  These two entries will, in
        most cases, contain identical information.  This method follows the
        same convention used by the Staden package (see seqIOABI.c), which is
        to only look at entry 1 (the user-edited PLs) and ignore entry 2.
        """
        row = self.getIndexEntry('PLOC', 1)
        if row is None:
            raise ABIError('No base location data were found in the ABI file.  The file might be damaged.')
    
        # Read the base call locations from the file.
        self.basepos = self.read2ByteInts(row)

        return True

    def getBaseDataOrder(self):
        # Retrieve the "filter wheel order" row from the file index.
        rows = self.getIndexEntriesById('FWO_')
    
        if len(rows) > 1:
            raise ABIError('Found multiple filter wheel order index entries in ABI file.')
        if rows[0]['dlen'] != 4:
            raise ABIError('Incorrect data length for filter wheel order index entry.')
    
        # The data length is only 4 bytes, so the actual data are stored in the
        # offset.
        val = rows[0]['offset']
    
        base_order = list()
    
        base_order.append(chr((val >> 24) & 0xff))
        base_order.append(chr((val >> 16) & 0xff))
        base_order.append(chr((val >> 8) & 0xff))
        base_order.append(chr(val & 0xff))
    
        return base_order
    
    def readTraceData(self):
        base_order = self.getBaseDataOrder()
        maxval = 0
        
        # This is the ID for the first 'DATA' index entry that points to the
        # processed trace data.  The man page for the Staden program
        # convert_trace states that IDs 9-12 contain the processed data; IDs
        # 1-4 contain the raw data.  The ABIF documentation from ABI also
        # suggests that IDs 1-8 will always contain raw data, and 9-12 will
        # contain the processed data.  Is this always correct?
        start_id = 9
    
        for cnt in range(0, 4):
            row = self.getIndexEntry('DATA', start_id + cnt)
            if row == None:
                raise ABIError('Could not find trace data index entries for all bases.  The file might be damaged.')
    
            # read the trace data from the file
            lst = self.read2ByteInts(row)
            tmpmax = max(lst)
            if tmpmax > maxval:
                maxval = tmpmax
            self.tracesamps[base_order[cnt]] = lst

        self.max_traceval = maxval


class SCFError(TraceFileError):
    pass

class SCFVersionError(SCFError):
    def __init__(self, version, revision):
        self.version = version
        self.revision = revision

    def __str__(self):
        return ('This file uses version ' + self.version + '.' + self.revision +
                ' of the SCF format.  This software supports the following versions: ' +
                '(' + ', '.join(SCFSequenceTrace.VERSIONS) + ').')

class SCFDataError(SCFError):
    def __init__(self, expectedlen, actuallen):
        self.expectedlen = expectedlen
        self.actuallen = actuallen

    def __str__(self):
        return 'Error reading SCF file data.  Expected ' + str(self.expectedlen) + ' bytes but only got ' + str(self.actuallen) + ' bytes.  The file appears to be damaged.'


class SCFSequenceTrace(SequenceTrace):
    # Define the supported versions.
    VERSIONS = ('3.00', '3.10')

    # Define the code set identifiers that are accepted.
    CODE_SETS = (0, 2, 4)

    def loadFile(self, filename):
        self.fname = filename

        try:
            self.tf = open(filename, 'rb')
        except IOError:
            raise

        magicnum = self.tf.read(4)
        #print magicnum
        if magicnum != '.scf':
            raise SCFError('The SCF file header is invalid.  The file appears to be damaged.')

        try:
            numsamps = unpack('>I', self.tf.read(4))[0]
            sampstart = unpack('>I', self.tf.read(4))[0]
            #print numsamps, sampstart

            numbases = unpack('>I', self.tf.read(4))[0]
            # skip 8 bytes
            self.tf.read(8)
            basesstart = unpack('>I', self.tf.read(4))[0]
            #print numbases, basesstart

            commentslen = unpack('>I', self.tf.read(4))[0]
            commentsstart = unpack('>I', self.tf.read(4))[0]
            #print commentslen, commentsstart

            version = self.tf.read(4)
            #print version

            samplesize = unpack('>I', self.tf.read(4))[0]
            codeset = unpack('>I', self.tf.read(4))[0]
            #print samplesize, codeset
        except struct.error:
            raise SCFError('The SCF file header is invalid.  The file appears to be damaged.')

        if version not in self.VERSIONS:
            raise SCFVersionError(version[0], version[2:])

        if samplesize not in (1, 2):
            raise SCFError(
                'Invalid sample size value in SCF header.  The size specified was ' +
                str(samplesize) + ', but must be either 1 or 2.'
            )

        if codeset not in self.CODE_SETS:
            raise SCFError(
                'Invalid code set specified in SCF header.  This file uses code set ' +
                str(codeset) + ', but this software only recognizes the following code sets: ' +
                str(self.CODE_SETS) + '.'
            )

        self.readBasesData(numbases, basesstart)
        self.readTraceData(numsamps, sampstart, samplesize)
        self.readComments(commentslen, commentsstart)

    def readBasesData(self, numbases, basesstart):
        self.basepos = list()
        probs = {'A': list(), 'C': list(), 'G': list(), 'T': list()}
        self.bcconf = list()

        self.tf.seek(basesstart, 0)

        try:
            # get the base locations
            for cnt in range(0, numbases):
                index = unpack('>I', self.tf.read(4))[0]
                self.basepos.append(index)
            #print self.basepos

            # get the base call probabilities for all bases
            for base in ('A', 'C', 'G', 'T'):
                for cnt in range(0, numbases):
                    prob = unpack('B', self.tf.read(1))[0]
                    probs[base].append(prob)
        except struct.error:
            raise SCFError('Error while reading base call locations and probabilities from the SCF file.  The file appears to be damaged.')

        # get the base calls
        self.basecalls = self.tf.read(numbases).upper()
        #print self.basecalls
        if numbases != len(self.basecalls):
            raise SCFDataError(numbases, len(self.basecalls))

        self.bcconf = self._buildConfScoresList(self.basecalls, probs)
        #print self.bcconf

    def _buildConfScoresList(self, basecalls, scfbaseprobs):
        """
        Uses the SCF base probability data to derive quality scores for each
        base call.
        The SCF standard defines the probability numbers as the "probability of
        it [a base] being" a particular value (A, C, G, or T)
        (see http://staden.sourceforge.net/manual/formats_unix_5.html), which
        means that, in theory, the probabilities derived from all four numbers
        for each base position should sum to 1.0.  In practice, for
        non-ambiguous base calls, the "probability" of the called base is just
        set to the phred score for the call and the "probabilities" of the
        other three possible base values are set to 0.  Thus, the probability
        is actually the probability of an incorrect base call, not the
        probability of a particular base.
        Because of the way the SCF format represents quality information, the
        only reasonable way to get quality scores for ambiguous nucleotide
        codes is by summing the probabilities for each possible base, given the
        ambiguity code.  To do this, this method assumes that the probability
        scores in the SCF file are in phred-score format; that is, that they
        were calculated as -10 * log10(P), where P is the probability that a
        given base call would be in error.
        This seems to be the most logical way to handle ambiguous codes, but
        the SCF standard does not specify how quality scores for ambiguity
        codes should be encoded in an SCF file, so there is no guarantee that
        other software will handle quality scores for ambiguity codes in the
        same way.  Nevertheless, even if quality information for an ambiguous
        base call is only associated with a single base value (e.g., the phred
        score for a call of 'W' is assigned to 'A' in the SCF file and all
        other probabilities are set to 0), the algorithm implemented here will
        still produce the correct result.
        Note also that the interpretation of the "probability" scores described
        above appears to be fully consistent with the proposed 3.10 version of
        the SCF standard.  This proposal was included with 1.8 series source
        code distributions of the Staden package's io_lib.  (See, e.g.,
        https://sourceforge.net/projects/staden/files/io_lib/1.8.12/ .)
        """
        # Define a lookup table that provides the individual quality scores to
        # sum for each ambiguity code.
        codes_to_sum = { 'W': ('A','T'), 'S': ('C','G'), 'M': ('A','C'),
                'K': ('G','T'), 'R': ('A','G'), 'Y': ('C','T'),
                'B': ('C','G','T'), 'D': ('A','G','T'), 'H': ('A','C','T'),
                    'V': ('A','C','G'), 'N': ('A','C','G','T') }

        # Build the confidence scores list.
        cscores = []
        for cnt in range(0, len(basecalls)):
            base = basecalls[cnt]
            if base in ('A','C','G','T'):
                cscores.append(scfbaseprobs[base][cnt])
            elif base in codes_to_sum:
                # This is an ambiguous base call, so sum the derived
                # probabilities for each possible base.  This is a bit tricky,
                # because we first need to use the phred-type score to
                # calculate the probability that each base call would be
                # correct, sum these probabilities, then convert the sum back
                # to an error probability and a final phred-type score.
                probsum = 0.0
                for sbase in codes_to_sum[base]:
                    probsum += 1.0 - (10.0 ** (scfbaseprobs[sbase][cnt] / -10.0))
                # Convert the sum back to an error probability and a phred
                # score.
                qscore = int(round(-10 * math.log10(1.0 - probsum), 0))
                cscores.append(qscore)
            else:
                raise SCFError('Unrecognized base call code in SCF file: ' + base)

        return cscores

    def readTraceData(self, numsamps, sampstart, sampsize):
        if sampsize == 1:
            formatstr = 'B'
        else:
            formatstr = '>H'

        self.tf.seek(sampstart, 0)

        maxval = 0

        for base in ('A', 'C', 'G', 'T'):
            samps = list()

            try:
                # read the raw sample data
                for cnt in range(0, numsamps):
                    val = unpack(formatstr, self.tf.read(sampsize))[0]
                    samps.append(val)
            except struct.error:
                raise SCFDataError((numsamps * sampsize), (len(samps) * sampsize))

            # Sample values are double-delta encoded (i.e., two successive
            # rounds of differences).
            if sampsize == 1:
                self.decode8BitDoubleDelta(samps)
            else:
                self.decode16BitDoubleDelta(samps)

            self.tracesamps[base] = samps
            tmpmax = max(self.tracesamps[base])
            if tmpmax > maxval:
                maxval = tmpmax

        self.max_traceval = maxval
        #print self.tracesamps['A']

    def decode8BitDoubleDelta(self, data):
        for clev in range(0, 2):
            prev = 0
            for cnt in range(0, len(data)):
                actual = data[cnt] + prev

                # simulate 1-byte integer overflow, if needed
                if actual > 255:
                    actual -= 256

                prev = actual
                data[cnt] = actual
    
    def decode16BitDoubleDelta(self, data):
        for clev in range(0, 2):
            prev = 0
            for cnt in range(0, len(data)):
                actual = data[cnt] + prev

                # simulate 2-byte integer overflow, if needed
                if actual > 65535:
                    actual -= 65536

                prev = actual
                data[cnt] = actual

    def readComments(self, commentslen, commentsstart):
        """
        Reads the comments section of an SCF file.  There is some variation in
        how 3rd-party software programs write the comments section.  For
        example, the SCF standard specifies that the comments are a
        "zero-terminated list of \\n-separated entries"
        (see http://staden.sourceforge.net/manual/formats_unix_6.html).  It is
        not entirely clear whether the last entry  in the list is supposed to
        also end with a '\\n', but this seems to be the common interpretation
        in actual SCF files.  However, some software does not end the last
        comments entry with a '\\n' and instead ends it with the zero
        terminator.  The code in this method tries to accommodate these
        variations in interpretation as much as possible.
        """
        self.tf.seek(commentsstart, 0)

        commentssec = self.tf.read(commentslen)
        readsize = len(commentssec)
        #print readsize, commentslen

        # Make sure that the number of bytes read from the comments section
        # matches the total comments size reported in the file header.
        if readsize != commentslen:
            raise SCFError('Invalid comments section: ' + str(commentslen) +
                    ' bytes were expected, but only ' + str(readsize) +
                    ' bytes could be read.')

        # Make sure the final character was the null terminator for the
        # comments list.  Some software produces SCF files with comments
        # sections that end with the newline character ('\n') rather than the
        # null terminator (e.g., the AutoSeq base caller from the Cybertory
        # educational software suite; see
        # http://www.cybertory.org/downloads/index.html).  Although this is
        # invalid according to the SCF standard, the Staden package software
        # still reads these files, so SeqTrace will, too.
        if ord(commentssec[-1]) not in (0,10):
            raise SCFError('Invalid comments section: Missing null terminator.')

        # Get rid of the null terminator.
        commentssec = commentssec[:-1]

        # Process each line in the comments section.
        for line in commentssec.split('\n'):
            if line != '':
                key, sep, value = line.partition('=')
                #print key + ': ' + value
                self.comments[key] = value



if __name__ == '__main__':
    #st = SCFSequenceTrace()
    #st.loadFile('forward.scf')

    #st = ZTRSequenceTrace()
    #st.loadFile('forward.ztr')

    st = ABISequenceTrace()
    st.loadFile('forward.ab1')

    for key, value in sorted(st.getComments().items()):
        print(key + ': ' + value)
