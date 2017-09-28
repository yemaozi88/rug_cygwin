from __future__ import division

__author__    = 'Maximilian Bisani'
__version__   = '$LastChangedRevision: 96 $'
__date__      = '$LastChangedDate: 2007-06-02 18:14:47 +0200 (Sat, 02 Jun 2007) $'
__copyright__ = 'Copyright (c) 2004-2005  RWTH Aachen University'
__license__   = """
This program is free software; you can redistribute it and/or modify
it under the terms of the GNU General Public License Version 2 (June
1991) as published by the Free Software Foundation.
 
This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program; if not, you will find it at
http://www.gnu.org/licenses/gpl.html, or write to the Free Software
Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110,
USA.
 
Should a provision of no. 9 and 10 of the GNU General Public License
be invalid or become invalid, a valid provision is deemed to have been
agreed upon which comes closest to what the parties intended
commercially. In any case guarantee/warranty shall be limited to gross
negligent actions or intended actions or fraudulent concealment.
"""

# ===========================================================================
import sys

if sys.version_info[:2] < (2, 4):
    def sorted(l):
        l = list(l)
        l.sort()
        return l

    def reversed(l):
        l = list(l)
        l.reverse()
        return l

    from sets import Set; set = Set

else:
    sorted = sorted
    reversed = reversed
    set = set

# ===========================================================================
import gc, os, resource, sys, types

pageSize = resource.getpagesize()
megabyte = 1024 * 1024

def meminfo():
    pid = os.getpid()
    try:
        data = open('/proc/%d/statm' % pid).read()
    except Exception:
        raise NotImplementedError
    data = map(int, data.split())
    size, resident, shared, trs, drs, lrs, dt = tuple(data)
    return size * pageSize, resident * pageSize

def reportMemoryUsage():
    try:
        size, resident = meminfo()
    except NotImplementedError:
        return
    print 'memory usage:  virtual %1.1f MB   resident %1.1f MB' % \
          (size / megabyte, resident / megabyte)

def cputime():
    user, system, childUser, childSystem, wall = os.times()
    return user

class MemoryProfiler:
    class Record(object):
        __slots__ = ['id', 'object', 'type', 'path', 'usage']
        def __init__(self, object, path):
            self.id = id(object)
            self.object = object
            self.path = path
            self.usage = self.measureMemory(self.object)
            self.type = type(self.object)
            if self.type is types.InstanceType:
                self.type = self.object.__class__

        def measureMemory(self, object):
            """
            memory consumption for this object alone
            (not including children)
            """
            if hasattr(object, 'memoryUsed'):
                try:
                    return object.memoryUsed()
                except Exception:
                    return -1
            if type(object) in self.valuators:
                return self.pythonObjectHead + self.valuators[type(object)](object)
            return 0

        # Machine dependent: Trying to emulate AMD64 here.
        pythonObjectHead = 4 + 8
        valuators = {
            str:     lambda s: len(s),
            unicode: lambda u: 2 * len(u),
            list:    lambda l: 4+8 + 8 * len(l),
            tuple:   lambda t: 4   + 8 * len(t),
            dict:    lambda d:      16 * len(d),
            int:     lambda i: 8,
            float:   lambda f: 8
            }

    def __init__(self):
        self.queue = list()
        self.records = dict()

    def add(self, record):
        if record.id not in self.records:
            self.queue.append(record)
            self.records[record.id] = record

    def search(self, root):
        self.add(self.Record(root, '/'))
        while self.queue:
            current = self.queue.pop(0)
            inspector = self.inspectors.get(type(current.object))
            if inspector:
                children = inspector(self, current)
            elif hasattr(current.object, '__dict__'):
                children = self.inspectInstance(current)
            else:
                self.inspectGeneral(current)
            for child in children:
                self.add(child)


    def inspectList(self, current):
        for index, item in enumerate(current.object):
            yield self.Record(item, '%s[%d]' % (current.path, index))

    def inspectDict(self, current):
        for key, value in current.object.iteritems():
            yield self.Record(value, '%s[%s]' % (current.path, repr(key)))

    def inspectInstance(self, current):
        for key, value in current.object.__dict__.iteritems():
            if type(key) is not str:
                continue
            yield self.Record(value, '%s.%s' % (current.path, key))

    def inspectGeneral(self, current):
        for ii, object in enumerate(gc.get_referents(current.object)):
            if type(object) is type:
                continue
            yield self.Record(object, '%s/%d' % (current.path, ii))

    inspectors = {
        list:  inspectList,
        tuple: inspectList,
        dict:  inspectDict,
        types.InstanceType: inspectInstance # old-style class
        }

    def report(self, out):
        records = self.records.values()
        records.sort(key = lambda rec: rec.path)
        sum = 0
        for record in records:
            what = repr(record.object)
            if len(what) > 50:
                what = what[:46] + ' ...'
            fields =  [record.path, str(record.usage), what]
            print >> out, '\t'.join(fields)
            sum += record.usage
        print >> out, 'total:', sum

    def reportByType(self, out):
        recordsByType = {}
        for record in self.records.itervalues():
            if record.type not in recordsByType:
                recordsByType[record.type] = []
            recordsByType[record.type].append(record)

        typesAndClasses = recordsByType.keys()
        typesAndClasses.sort()
        for typeOrClass in typesAndClasses:
            records = recordsByType[typeOrClass]
            records.sort(lambda a, b: cmp(b.usage, a.usage))
            count = len(records)
            memoryUsed = sum([rec.usage for rec in records])
            print >> out, '%5d\t%-40s\t%d' % (count, typeOrClass, memoryUsed)
            for record in records[:5]:
                print >> out, '\t%-40s\t%d' % (record.path, record.usage)
            if len(records) > 5:
                print >> out, '\t...'


def reportMemoryProfile(root):
    profiler = MemoryProfiler()
    profiler.search(root)
#   profiler.report(sys.stdout)
    profiler.reportByType(sys.stdout)

# ===========================================================================
import codecs, gzip, errno, os, sys

def gOpenOut(fname, encoding=None):
    if fname == '-':
        out = sys.stdout
    elif os.path.splitext(fname)[1] == '.gz':
#        out = os.popen('gzip -fc >%s' % fname, 'w')
        out = gzip.open(fname, 'w')
    else:
        out = open(fname, 'w')
    if encoding:
        encoder, decoder, streamReader, streamWriter = codecs.lookup(encoding)
        out = streamWriter(out)
    return out

def gOpenIn(fname, encoding=None):
    if fname == '-':
        inp = sys.stdin
    elif os.path.splitext(fname)[1] == '.gz':
        if not os.path.isfile(fname):
            raise IOError(errno.ENOENT, 'No such file: \'%s\'' % fname)
#        inp = os.popen('gzip -dc %s' % fname, 'r')
        inp = gzip.open(fname)
    else:
        inp = open(fname)
    if encoding:
        encoder, decoder, streamReader, streamWriter = codecs.lookup(encoding)
        inp = streamReader(inp)
    return inp

# ===========================================================================
class RestartStub:
    def __init__(self, fun, args):
        self.fun  = fun
        self.args = args

    def __iter__(self):
        return self.fun(*self.args)

def restartable(fun):
    def restartableFun(*args):
        return RestartStub(fun, args)
    return restartableFun

def once(fun):
    return fun()
