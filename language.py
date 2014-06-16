# Copyright 2014 The ALIVe authors.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from z3 import *
import math, copy

def toBV(b):
  return If(b, BitVecVal(1, 1), BitVecVal(0, 1))

gbl_unique_id = 0
def mk_unique_id():
  global gbl_unique_id
  id = str(gbl_unique_id)
  gbl_unique_id += 1
  return id


class Type:
  def __repr__(self):
    return ''


################################
class IntType(Type):
  def __init__(self, size = None):
    if size == None:
      self.defined = False
      return
    self.size = size
    self.defined = True
    assert isinstance(self.size, int)

  def setName(self, name):
    self.smtvar = Int('t' + name)

  def __repr__(self):
    if self.defined:
      return 'i' + str(self.size)
    return ''

  def getIntSize(self):
    return self.size

  def fixup(self, types):
    size = types.evaluate(self.smtvar).as_long()
    assert self.defined == False or self.size == size
    self.size = size

  def __eq__(self, other):
    if isinstance(other, IntType):
      return self.smtvar == other.smtvar
    if isinstance(other, int):
      return self.smtvar == other
    assert False

  def __lt__(self, other):
    if isinstance(other, IntType):
      return self.smtvar < other.smtvar
    if isinstance(other, int):
      return self.smtvar < other
    assert False

  def __gt__(self, other):
    if isinstance(other, IntType):
      return self.smtvar > other.smtvar
    if isinstance(other, int):
      return self.smtvar > other
    assert False

  def __ge__(self, other):
    if isinstance(other, IntType):
      return self.smtvar >= other.smtvar
    if isinstance(other, int):
      return self.smtvar >= other
    assert False

  def getConstraints(self, vars):
    vars += [self.smtvar]
    if self.defined:
      return self.smtvar == self.getIntSize()
    return BoolVal(True)


################################
class PtrType(Type):
  def __init__(self, type):
    self.type = type
    assert isinstance(self.type, Type)

  def __repr__(self):
    return self.type + '*'

  def setName(self, name):
    # TODO
    return

  def fixup(self, types):
    # TODO
    return

  def getConstraints(self, vars):
    # TODO
    return BoolVal(True)


################################
class Instr:
  def __repr__(self):
    return self.toString()

  def getName(self):
    return self.name

  def setName(self, name):
    self.name = name
    self.type = copy.deepcopy(self.type)
    self.type.setName(name)
    if hasattr(self, 'stype'):
      self.stype = copy.deepcopy(self.stype)
      self.stype.setName('s' + mk_unique_id() + name)

  def toString(self):
    raise Exception('toString not implemented')

  def getTypeConstraints(self, vars):
    return self.type.getConstraints(vars)

  def fixupTypes(self, types):
    self.type.fixup(types)
    if hasattr(self, 'stype'):
      self.stype.fixup(types)
    for attr in ['v', 'v1', 'v2']:
      if hasattr(self, attr):
        getattr(self, attr).fixupTypes(types)


################################
class Input(Instr):
  def __init__(self, name, type):
    self.type = type
    self.setName(name)
    assert isinstance(self.type, Type)

  def toString(self):
    return self.getName()

  def toSMT(self, defined, qvars):
    return BitVec(self.name, self.type.getIntSize())


################################
class CopyOperand(Instr):
  def __init__(self, v, type):
    self.v = v
    self.type = type
    assert isinstance(self.v, Instr)
    assert isinstance(self.type, Type)

  def toString(self):
    return self.v.toString()

  def toSMT(self, defined, qvars):
    return self.v.toSMT(defined, qvars)

  def getTypeConstraints(self, vars):
    return And(self.type.getConstraints(vars),
               self.type == self.v.type)


################################
class Constant(Instr):
  def __init__(self, val, type):
    self.val = val
    self.type = type
    self.setName(str(val))
    self.id = mk_unique_id()
    self.type.setName(self.getUniqueName())
    assert isinstance(self.type, Type)

  def getUniqueName(self):
    return self.getName() + '_' + self.id

  def toString(self):
    return str(self.val)

  def toSMT(self, defined, qvars):
    return BitVecVal(self.val, self.type.getIntSize())

  def getTypeConstraints(self, vars):
    c = self.type.getConstraints(vars)
    if self.val != 0:
      if self.val > 0:
        bits = int(math.floor(math.log(self.val, 2)+1))
      else:
        bits = int(math.floor(math.log(abs(self.val)+1, 2)+1))
      return And(c, self.type >= bits)
    return c


################################
class UndefVal(Constant):
  def __init__(self, type):
    self.type = type
    self.setName('undef')
    self.id = mk_unique_id()
    self.type.setName(self.getUniqueName())
    assert isinstance(self.type, Type)

  def toString(self):
    return 'undef'

  def toSMT(self, defined, qvars):
    v = BitVec('undef' + self.id, self.type.getIntSize())
    qvars += [v]
    return v


################################
class BinOp(Instr):
  Add, Sub, Mul, UDiv, SDiv, URem, SRem, Shl, AShr, LShr, And, Or, Xor,\
  Last = range(14)

  opnames = {
    Add:  'add',
    Sub:  'sub',
    Mul:  'mul',
    UDiv: 'udiv',
    SDiv: 'sdiv',
    URem: 'urem',
    SRem: 'srem',
    Shl:  'shl',
    AShr: 'ashr',
    LShr: 'lshr',
    And:  'and',
    Or:   'or',
    Xor:  'xor',
  }
  opids = {v:k for k, v in opnames.items()}


  def __init__(self, op, type, v1, v2, flags = []):
    self.op = op
    self.type = type
    self.v1 = v1
    self.v2 = v2
    self.flags = flags
    self._check_op_flags()
    assert isinstance(self.type, Type)
    assert isinstance(self.v1, Instr)
    assert isinstance(self.v2, Instr)
    assert self.op >= 0 and self.op < self.Last

  def getOpName(self):
    return self.opnames[self.op]

  @staticmethod
  def getOpId(name):
    try:
      return BinOp.opids[name]
    except:
      print 'Unknown binary instruction: ' + name
      exit(-1)

  def toString(self):
    t = str(self.type)
    if len(t) > 0:
      t = ' ' + t
    flags = ' '.join(self.flags)
    if len(flags) > 0:
      flags = ' ' + flags
    return '%s%s%s %s, %s' % (self.getOpName(), flags, t,
                              self.v1.getName(),
                              self.v2.getName())

  def _check_op_flags(self):
    allowed_flags = {
      self.Add:  ['nsw', 'nuw'],
      self.Sub:  ['nsw', 'nuw'],
      self.Mul:  ['nsw', 'nuw'],
      self.UDiv: ['exact'],
      self.SDiv: ['exact'],
      self.URem: [],
      self.SRem: [],
      self.Shl:  ['nsw', 'nuw'],
      self.AShr: ['exact'],
      self.LShr: ['exact'],
      self.And:  [],
      self.Or:   [],
      self.Xor:  [],
    }[self.op]

    for f in self.flags:
      if f not in allowed_flags:
        print 'Flag \'%s\' not support by instruction \'%s\'' %\
              (f, self.getOpName())
        exit(-1)

  def _genSMTDefConds(self, v1, v2, defined):
    bits = self.type.getIntSize()

    def_conds = {
      self.Add: {'nsw': lambda a,b: SignExt(1,a)+SignExt(1,b) == SignExt(1,a+b),
                 'nuw': lambda a,b: ZeroExt(1,a)+ZeroExt(1,b) == ZeroExt(1,a+b),
                },
      self.Sub: {'nsw': lambda a,b: SignExt(1,a)-SignExt(1,b) == SignExt(1,a-b),
                 'nuw': lambda a,b: ZeroExt(1,a)-ZeroExt(1,b) == ZeroExt(1,a-b),
                },
      self.Mul: {'nsw': lambda a,b: SignExt(bits, a) * SignExt(bits, b) ==
                                    SignExt(bits, a * b),
                 'nuw': lambda a,b: ZeroExt(bits, a) * ZeroExt(bits, b) ==
                                    ZeroExt(bits, a * b),
                },
      self.UDiv:{'exact': lambda a,b: UDiv(a, b) * b == a,
                },
      self.SDiv:{'exact': lambda a,b: (a / b) * b == a,
                },
      self.URem:{},
      self.SRem:{},
      self.Shl: {'nsw': lambda a,b: (a << b) >> b == a,
                 'nuw': lambda a,b: LShR(a << b, b) == a,
                },
      self.AShr:{'exact': lambda a,b: (a >> b) << b == a,
                },
      self.LShr:{'exact': lambda a,b: LShR(a, b) << b == a,
                },
      self.And: {},
      self.Or:  {},
      self.Xor: {},
    }[self.op]

    for f in self.flags:
      defined += [def_conds[f](v1, v2)]

    # additional constraints of definedness of the instruction
    defined += {
      self.Add:  lambda a,b: [],
      self.Sub:  lambda a,b: [],
      self.Mul:  lambda a,b: [],
      self.UDiv: lambda a,b: [b != 0],
      self.SDiv: lambda a,b: [And(b != 0, Or(a != (1 << (bits-1)), b != -1))],
      self.URem: lambda a,b: [b != 0],
      self.SRem: lambda a,b: [And(b != 0, Or(a != (1 << (bits-1)), b != -1))],
      self.Shl:  lambda a,b: [ULT(b, bits)],
      self.AShr: lambda a,b: [ULT(b, bits)],
      self.LShr: lambda a,b: [ULT(b, bits)],
      self.And:  lambda a,b: [],
      self.Or:   lambda a,b: [],
      self.Xor:  lambda a,b: [],
      }[self.op](v1,v2)
    return

  def toSMT(self, defined, qvars):
    v1 = self.v1.toSMT(defined, qvars)
    v2 = self.v2.toSMT(defined, qvars)
    self._genSMTDefConds(v1, v2, defined)
    return {
      self.Add:  lambda a,b: a + b,
      self.Sub:  lambda a,b: a - b,
      self.Mul:  lambda a,b: a * b,
      self.UDiv: lambda a,b: UDiv(a, b),
      self.SDiv: lambda a,b: a / b,
      self.URem: lambda a,b: URem(a, b),
      self.SRem: lambda a,b: SRem(a, b),
      self.Shl:  lambda a,b: a << b,
      self.AShr: lambda a,b: a >> b,
      self.LShr: lambda a,b: LShR(a, b),
      self.And:  lambda a,b: a & b,
      self.Or:   lambda a,b: a | b,
      self.Xor:  lambda a,b: a ^ b,
    }[self.op](v1, v2)

  def getTypeConstraints(self, vars):
    return And(self.type.getConstraints(vars),
               self.type == self.v1.type,
               self.type == self.v2.type)


################################
class ConversionOp(Instr):
  Trunc, ZExt, SExt, Last = range(4)

  opnames = {
    Trunc: 'trunc',
    ZExt:  'zext',
    SExt:  'sext',
  }
  opids = {v:k for k, v in opnames.items()}

  def __init__(self, op, stype, v, ttype):
    self.op = op
    self.stype = stype
    self.v = v
    self.type = ttype
    assert isinstance(self.stype, Type)
    assert isinstance(self.type, Type)
    assert isinstance(self.v, Instr)
    assert self.op >= 0 and self.op < self.Last

  def getOpName(self):
    return self.opnames[self.op]

  @staticmethod
  def getOpId(name):
    try:
      return ConversionOp.opids[name]
    except:
      print 'Unknown conversion instruction: ' + name
      exit(-1)

  def toString(self):
    st = str(self.stype)
    if len(st) > 0:
      st = ' ' + st
    tt = str(self.type)
    if len(tt) > 0:
      tt = ' to ' + tt
    return '%s%s %s%s' % (self.getOpName(), st, self.v.getName(), tt)

  def toSMT(self, defined, qvars):
    v = self.v.toSMT(defined, qvars)
    delta_bits = self.type.getIntSize() - self.stype.getIntSize()
    return {
      self.Trunc: lambda v: Extract(self.type.getIntSize()-1, 0, v),
      self.ZExt:  lambda v: ZeroExt(delta_bits, v),
      self.SExt:  lambda v: SignExt(delta_bits, v),
    }[self.op](v)

  def getTypeConstraints(self, vars):
    cnstr = {
      self.Trunc: lambda src,tgt: src > tgt,
      self.ZExt:  lambda src,tgt: src < tgt,
      self.SExt:  lambda src,tgt: src < tgt,
    } [self.op](self.stype, self.type)

    return And(self.type.getConstraints(vars),
               self.stype.getConstraints(vars),
               self.stype == self.v.type,
               cnstr)


################################
class Icmp(Instr):
  EQ, NE, UGT, UGE, ULT, ULE, SGT, SGE, SLT, SLE, Var, Last = range(12)

  opnames = {
    EQ:  'eq',
    NE:  'ne',
    UGT: 'ugt',
    UGE: 'uge',
    ULT: 'ult',
    ULE: 'ule',
    SGT: 'sgt',
    SGE: 'sge',
    SLT: 'slt',
    SLE: 'sle',
  }
  opids = {v:k for k, v in opnames.items()}


  def __init__(self, op, type, v1, v2):
    self.op = self.getOpId(op)
    if self.op == self.Var:
      self.opname = op
    self.type = IntType(1)
    self.stype = type
    self.v1 = v1
    self.v2 = v2
    assert isinstance(self.stype, Type)
    assert isinstance(self.v1, Instr)
    assert isinstance(self.v2, Instr)

  @staticmethod
  def getOpId(name):
    return Icmp.opids.get(name, Icmp.Var)

  def toString(self):
    op = self.opname if self.op == Icmp.Var else Icmp.opnames[self.op]
    if len(op) > 0:
      op = ' ' + op
    t = str(self.stype)
    if len(t) > 0:
      t = ' ' + t
    return 'icmp%s%s %s, %s' % (op, t, self.v1.getName(), self.v2.getName())

  def opToSMT(self, op, a, b):
    return {
      self.EQ:  lambda a,b: toBV(a == b),
      self.NE:  lambda a,b: toBV(a != b),
      self.UGT: lambda a,b: toBV(UGT(a, b)),
      self.UGE: lambda a,b: toBV(UGE(a, b)),
      self.ULT: lambda a,b: toBV(ULT(a, b)),
      self.ULE: lambda a,b: toBV(ULE(a, b)),
      self.SGT: lambda a,b: toBV(a > b),
      self.SGE: lambda a,b: toBV(a >= b),
      self.SLT: lambda a,b: toBV(a < b),
      self.SLE: lambda a,b: toBV(a <= b),
    }[op](a, b)

  def recurseSMT(self, ops, a, b, i):
    if len(ops) == 1:
      return self.opToSMT(ops[0], a, b)
    var = BitVec('icmp_' + self.opname, 4)
    assert 1 << 4 > self.Var
    return If(var == i,
              self.opToSMT(ops[0], a, b),
              self.recurseSMT(ops[1:], a, b, i+1))

  def toSMT(self, defined, qvars):
    # Generate all possible comparisons if icmp is generic. Set of comparisons
    # can be restricted in the precondition.
    ops = [self.op] if self.op != self.Var else range(self.Var)
    return self.recurseSMT(ops, self.v1.toSMT(defined, qvars),
                           self.v2.toSMT(defined, qvars), 0)

  def getTypeConstraints(self, vars):
    return And(self.type.getConstraints(vars),
               self.stype.getConstraints(vars),
               self.stype == self.v1.type,
               self.stype == self.v2.type)


################################
class Select(Instr):
  def __init__(self, type, c, v1, v2):
    self.type = type
    self.c = c
    self.v1 = v1
    self.v2 = v2
    assert isinstance(self.type, Type)
    assert isinstance(self.c, Instr)
    assert isinstance(self.v1, Instr)
    assert isinstance(self.v2, Instr)

  def toString(self):
    t = str(self.type)
    if len(t) > 0:
      t = t + ' '
    return 'select i1 %s, %s%s, %s%s' % (self.c, t, self.v1, t, self.v2)

  def toSMT(self, defined, qvars):
    return If(self.c.toSMT(defined, qvars) == 1,
              self.v1.toSMT(defined, qvars),
              self.v2.toSMT(defined, qvars))

  def getTypeConstraints(self, vars):
    return And(self.type.getConstraints(vars),
               self.type == self.v1.type,
               self.type == self.v2.type,
               self.c.type == 1)


################################
class Alloca(Instr):
  def __init__(self, type, elemsType, numElems, align):
    self.type = PtrType(type)
    self.elemsType = elemsType
    self.numElems = numElems
    self.align = align
    assert isinstance(self.elemsType, Type)
    assert isinstance(self.numElems, Instr)
    assert isinstance(self.align, int)

  def toString(self):
    if str(self.numElems) == '1':
      elems = ''
    else:
      t2 = str(self.elemsType)
      elems = ', ' + t2
      if len(t2) > 0:
        elems += ' '
      elems += str(self.numElems)
    align = ', align %d' % self.align if self.align != 0 else ''
    return 'alloca %s%s%s' % (str(self.type.type), elems, align)

  def toSMT(self, defined, qvars):
    # TODO
    return BoolVal(True)


################################
def print_prog(p):
  for k,v in p.iteritems():
    if isinstance(v, Input) or isinstance(v, Constant):
      continue
    print '%s = %s' % (k, v)


def getTypeConstraints(p, vars):
  return [v.getTypeConstraints(vars) for v in p.itervalues()]


def fixupTypes(p, types):
  for v in p.itervalues():
    v.fixupTypes(types)
