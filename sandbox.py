from MUSCython import MultiStringBWTCython as msbwt, LCPGen
from logging import getLogger
import os
from subprocess import call
from time import clock
import sys
from itertools import izip, izip_longest
import pysam
from collections import Counter
import cProfile
from random import randint
from string import maketrans
import numpy as np
import matplotlib

matplotlib.use('Agg')
from matplotlib import pyplot as plot

# PATH = '/playpen/sgreens/fake/'
# BWT_PATH = '/playpen/sgreens/fake/bwt/'
# PATH = '/playpen/sgreens/ecoli/msbwt20/'
# BWT_PATH = '/playpen/sgreens/ecoli/msbwt20/rle_bwt/'
PATH = '/playpen/sgreens/fq_celegans/msbwt/'
BWT_PATH = '/playpen/sgreens/ecoli/msbwt20/bwt/'


K = 25
BASES = ['A', 'C', 'G', 'T']
BASE_TO_NUM = {'A': 1, 'C': 2, 'G': 3, 'T': 5}
NUM_TO_BASE = ['$', 'A', 'C', 'G', 'N', 'T']
READ_LEN = 100
THRESH = 1
HI_THRESH = 5
TRAN_TAB = maketrans('ACGT', 'TGCA')


def reverseComplement(seq):
    return seq[::-1].translate(TRAN_TAB)


def grouper(iterable, n, fillvalue=None):
    # grouper('ABCDEFG', 3, 'x') --> ABC DEF Gxx
    args = [iter(iterable)] * n
    return izip_longest(fillvalue=fillvalue, *args)


# @profile
def superCorrect():
    begin = clock()
    bwt = msbwt.loadBWT(BWT_PATH, False)
    trusted = np.empty(READ_LEN-K+1, dtype=np.uint8)
    corrected = np.empty(READ_LEN, dtype=np.uint8)
    with open(PATH + 'corrected2.fa', 'w') as fp:
        # for readID in xrange(bwt.getSymbolCount(0)):
        for readID in xrange(10000):
            trusted.fill(0)
            corrString = ['0'] * READ_LEN
            origRead = bwt.recoverString(readID)
            origRead = origRead[1:] + '\n'
            # origRead = 'CGGTCGCGCTATACTTTAGATGCCCAGGTCGCTGCATCATGGGTAATGAAGAATAAGGCTGGATAAAGCGACGTTGTGTACCGTCACTTTCTTCAATCGT\n'
            read = list(origRead[:-1])
            revCounts = bwt.countStrandedSeqMatchesNoOther(reverseComplement(origRead[:-1]), K)
            revCounts = np.flipud(revCounts)
            trusted = (revCounts > 0).astype(np.uint8)
            corrected.fill(0)
            if False in trusted:
                counts = bwt.countStrandedSeqMatchesNoOther(origRead[:-1], K)
                trusted |= counts > HI_THRESH
                changeMade = True
                while changeMade:
                    changeMade = False
                    if False in trusted:
                        for i in xrange(len(trusted)-1):
                            if trusted[i] or read[i+K] == 'N':
                                if not trusted[i+1] or read[i+K] == 'N':  # err at read[i+K]
                                    bestSupport = 0
                                    newLo, newHi = bwt.findIndicesOfStr(reverseComplement(''.join(read[i+1:i+K])))
                                    for base in BASES:
                                        rcLo = bwt.getOccurrenceOfCharAtIndex(BASE_TO_NUM[base.translate(TRAN_TAB)], newLo)
                                        rcHi = bwt.getOccurrenceOfCharAtIndex(BASE_TO_NUM[base.translate(TRAN_TAB)], newHi)
                                        lo, hi = bwt.findIndicesOfStr(''.join(read[i+1:i+K]) + base)
                                        support = hi - lo + rcHi - rcLo
                                        if support > bestSupport:
                                            bestSupport = support
                                            bestBase = base
                                    if bestBase != read[i+K]:
                                        changeMade = True
                                        corrected[i+K] = True
                                        read[i+K] = bestBase
                                        corrString[i+K] = '1'
                                    if corrected[i+K]:
                                        kmersEnd = min(len(read), i+2*K)
                                        newCounts = bwt.countStrandedSeqMatchesNoOther(''.join(read[i+1:kmersEnd]), K)
                                        trusted[i+1:kmersEnd-K+1] = newCounts > HI_THRESH
                                        counts[i+1:kmersEnd-K+1] = newCounts
                                        if False in trusted[i+1:kmersEnd-K+1]:
                                            newCounts = bwt.countStrandedSeqMatchesNoOther(
                                                reverseComplement(''.join(read[i+1:kmersEnd])), K)
                                            newCounts = np.flipud(newCounts)
                                            trusted[i+1:kmersEnd-K+1] |= newCounts > 0
                            elif trusted[i+1] and not corrected[i]:  # err at read[i]
                                bestSupport = 0
                                newLo, newHi = bwt.findIndicesOfStr(''.join(read[i+1:i+K]))
                                for base in BASES:
                                    lo = bwt.getOccurrenceOfCharAtIndex(BASE_TO_NUM[base], newLo)
                                    hi = bwt.getOccurrenceOfCharAtIndex(BASE_TO_NUM[base], newHi)
                                    rcLo, rcHi = bwt.findIndicesOfStr(reverseComplement(base + ''.join(read[i+1:i+K])))
                                    support = hi - lo + rcHi - rcLo
                                    if support > bestSupport:
                                        bestSupport = support
                                        bestBase = base
                                if bestBase != read[i]:
                                    changeMade = True
                                    corrected[i] = True
                                    read[i] = bestBase
                                    corrString[i] = '1'
                                if corrected[i]:
                                    kmersStart = max(0, i-K)
                                    newCounts = bwt.countStrandedSeqMatchesNoOther(''.join(read[kmersStart:i+K]), K)
                                    trusted[kmersStart:i+1] = newCounts > HI_THRESH
                                    counts[kmersStart:i+1] = newCounts
                                    if False in trusted[kmersStart:i+1]:
                                        newCounts = bwt.countStrandedSeqMatchesNoOther(
                                            reverseComplement(''.join(read[kmersStart:i+K])), K)
                                        newCounts = np.flipud(newCounts)
                                        trusted[kmersStart:i+1] |= newCounts > 0
            fp.write(''.join(read) + '\n')
            fp.write(origRead)
            fp.write(''.join(corrString) + '\n')
    print 'Took', clock() - begin, 'seconds'


def runLengthCorrect():
    begin = clock()
    bwt = msbwt.loadBWT(BWT_PATH, True)
    changed = np.empty(READ_LEN, dtype=np.uint8)
    print bwt.getSymbolCount(0), 'reads'
    DOLLAR = 0
    N = 4
    with open(PATH + 'corrected2.fa', 'w') as fp:
        for readID in xrange(bwt.getSymbolCount(0)):
            origRead, indices = bwt.recoverString(readID, True)
            read = list(origRead[1:])
            changed.fill(0)
            doQuery = False
            for charPos, origIndex in reversed(zip(range(len(indices)-1), indices[2:] + [indices[0]])):
                try:
                    c = bwt.getCharAtIndex(origIndex)
                    if charPos < 50 and N != c != DOLLAR:
                        aboveIndex = origIndex - 1
                        belowIndex = origIndex + 1
                        # if doQuery:
                        #     i = bwt.findIndicesOfStr(''.join(read[charPos+1:]))[0]
                        #     if i == origIndex:
                        #         doQuery = False
                        #     else:
                        #         aboveIndex = i
                        #         belowIndex = i + 1
                            # print i, bwt.findIndicesOfStr(''.join(read[charPos+1:]))[0], bwt.findIndicesOfStr(origRead[charPos+2:])[0]
                        charAbove = bwt.getCharAtIndex(aboveIndex)
                        charBelow = bwt.getCharAtIndex(belowIndex)
                        if c != charAbove and c != charBelow:
                            if charAbove == N or charAbove == DOLLAR:
                                if N != charBelow != DOLLAR:
                                    read[charPos] = NUM_TO_BASE[charBelow]
                                    changed[charPos] = True
                                    doQuery = True
                            elif charBelow == N or charBelow == DOLLAR:
                                read[charPos] = NUM_TO_BASE[charAbove]
                                changed[charPos] = True
                                doQuery = True
                            else:
                                # nextIndex = bwt.getOccurrenceOfCharAtIndex(c, i)
                                nextIndex = indices[charPos + 1]
                                if abs(bwt.getOccurrenceOfCharAtIndex(charAbove, aboveIndex) - nextIndex) > \
                                        abs(bwt.getOccurrenceOfCharAtIndex(charBelow, belowIndex) - nextIndex):
                                    read[charPos] = NUM_TO_BASE[charAbove]
                                    changed[charPos] = True
                                    doQuery = True
                                else:
                                    read[charPos] = NUM_TO_BASE[charBelow]
                                    changed[charPos] = True
                                    doQuery = True
                except OverflowError:
                    pass  # happens when we try to do getCharAtIndex -1
            fp.write(''.join(read) + '\n')
            fp.write(origRead[1:] + '\n')
            fp.write(''.join(['1' if c else '0' for c in changed]) + '\n')
    print 'Took', clock() - begin, 'seconds'


def samplePaired():
    coverage = 20
    numReads = 28428648
    refLength = 4641652
    randReads = [randint(0, numReads - 1) for _ in xrange((coverage * refLength) / (2 * READ_LEN))]
    randReads.sort()
    print len(randReads), 'reads'
    for fileSuffix in ('1', '2'):
        with open('/playpen/sgreens/ecoli/EAS20_8/paired_' + str(coverage) + fileSuffix + '.txt', 'w') as outFile, \
                open('/playpen/sgreens/ecoli/EAS20_8/s_6_' + fileSuffix + '.txt', 'r') as inFile:
            reads = inFile.read().split('\n')
            for i in randReads:
                outFile.writelines([line + '\n' for line in reads[i * 4:4 * (i + 1)]])


def sample():
    coverage = 40
    numReads = 28428648
    refLength = 4641652
    randReads = [randint(0, numReads - 1) for _ in xrange((coverage * refLength) / READ_LEN)]
    randReads.sort()
    split = np.searchsorted(randReads, numReads / 2)
    randReads1 = randReads[:split]
    randReads2 = randReads[split:]
    print len(randReads), 'reads'
    print len(randReads1), 'reads from first file'
    print len(randReads2), 'reads from second file'
    with open('/playpen/sgreens/ecoli/EAS20_8/cov' + str(coverage) + '.txt', 'w') as outFile:
        with open('/playpen/sgreens/ecoli/EAS20_8/s_6_1.txt', 'r') as inFile:
            reads = inFile.read().split('\n')
            for i in randReads1:
                outFile.writelines([line + '\n' for line in reads[i * 4:4 * (i + 1)]])
        with open('/playpen/sgreens/ecoli/EAS20_8/s_6_2.txt', 'r') as inFile:
            reads = inFile.read().split('\n')
            for i in [j - (numReads / 2) for j in randReads2]:
                outFile.writelines([line + '\n' for line in reads[i * 4:4 * (i + 1)]])


def sampleFromInterleaved():
    coverage = 10
    numReads = 71945982
    refLength = 100286401
    randReads = [randint(0, numReads - 1) for _ in xrange((coverage * refLength) / READ_LEN)]
    print len(randReads), 'reads'
    randReads.sort()
    with open('/playpen/sgreens/fq_celegans/cov' + str(coverage) + '.txt', 'w') as outFile,\
            open('/playpen/sgreens/fq_celegans/srr065388.fastq', 'r') as inFile:
        for i in xrange(randReads[0]):
            for j in xrange(4):
                inFile.readline()
        for j in xrange(4):
            outFile.write(inFile.readline())
        for read, prevRead in izip(randReads[1:], randReads):
            for i in xrange(prevRead, read-1):
                for j in xrange(4):
                    inFile.readline()
            for j in xrange(4):
                outFile.write(inFile.readline())


def countsOfSeq(bwt, seq, k=K):
    ca = []
    for start in xrange(0, READ_LEN - k + 1):
        lo, hi = bwt.findIndicesOfStr(seq[start:start + k])
        c = hi - lo
        if c >= 10:
            ca.append('+')
        else:
            ca.append(str(c))
    return ''.join(ca)


def toBamFile(samFile):
    bamFile = samFile[:-3]+'bam'
    sortedBamFile = samFile[:-3] + 'sorted.bam'
    if not os.path.isfile(sortedBamFile):
        with open(bamFile, 'w+') as fp:
            call(['samtools', 'view', '-Sb', samFile], stdout=fp)
        call(['samtools', 'sort', bamFile, sortedBamFile[:-4]])
        call(['samtools', 'index', sortedBamFile])
    return sortedBamFile


def errsFromPileup(samFile):
    sam = pysam.Samfile(toBamFile(samFile), 'rb')
    errs = 0
    snps = 0
    snpFreqs = Counter()
    for col in sam.pileup():
        bases = Counter()
        for read in col.pileups:
            if not read.is_del and not read.is_refskip:
                bases[read.alignment.query_sequence[read.query_position]] += 1
        for base, freq in bases.most_common(5)[1:]:
            if freq < 2:
                errs += 1
            else:
                snps += 1
                snpFreqs[freq] += 1
    for freq, count in snpFreqs.iteritems():
        print 'Support', freq, ':', count
    return errs, snps


def summarizeBam(samFile, refPath, debug=False):
    MATCH = 0
    DEL = 2
    INS = 1
    SOFT_CLIP = 4
    HARD_CLIP = 5
    errs = 0
    bases = 0
    alignedBases = 0
    perfect = 0
    errTypes = [0, 0, 0]
    chroms = []
    if debug:
        bwt = msbwt.loadBWT(BWT_PATH)
    if os.path.isfile(refPath + '.fai'):
        with open(refPath + '.fai', 'r') as fp:
            for line in fp:
                chromInfo = line.split()
                # get chromo name, length, offset in file
                chroms.append((chromInfo[0], int(chromInfo[1]), int(chromInfo[2]), int(chromInfo[3])))
        sam = pysam.Samfile(toBamFile(samFile), 'rb')
    else:
        chroms = [(None, None, None, None)]
        sam = pysam.Samfile(samFile, 'r')
    for chromoName, length, offset, lineLen in chroms:
        with open(refPath) as fp:
            if chromoName is not None:
                bytesNeeded = length + (length / lineLen)  # num bases + num line breaks
                fp.seek(offset, 0)
                ref = ''.join(fp.read(bytesNeeded).split('\n'))
                reads = sam.fetch(chromoName)
            else:
                ref = ''.join(fp.read().split('\n')[1:])
                reads = sam.fetch()
        for read in reads:
            bases += READ_LEN
            refPos = read.pos
            readPos = 0
            # mismatches = ['0'] * READ_LEN
            for op, count in read.cigar:
                if op != MATCH and op != SOFT_CLIP and op != HARD_CLIP:
                    errs += 1
                    errTypes[op] += 1
                elif op == MATCH:
                    alignedBases += count
                    if read.seq[readPos:readPos + count] != ref[refPos:refPos + count]:
                        for errPos, (a, b) in enumerate(zip(read.seq[readPos:readPos + count], ref[refPos:refPos + count])):
                            if a != b:
                                errs += 1
                                errTypes[MATCH] += 1
                                # mismatches[readPos + errPos] = '1'
                    elif len(read.cigar) == 1:
                        perfect += 1
                if op != DEL:
                    readPos += count
                if op != INS and op != SOFT_CLIP:
                    refPos += count
                    if debug and '1' in mismatches:
                        if read.is_reverse:
                            print read.qname, 'rc'
                            print reverseComplement(ref[read.pos:read.pos+READ_LEN])
                            print reverseComplement(read.seq)
                            print ''.join(mismatches)[::-1]
                            # print countsOfSeq(bwt, reverseComplement(read.seq))
                            # print countsOfSeq(bwt, read.seq)[::-1]
                            print countsOfSeq(bwt, reverseComplement(read.seq), 25)
                            print countsOfSeq(bwt, read.seq, 25)[::-1]
                        else:
                            print read.qname
                            print ref[read.pos:read.pos+READ_LEN]
                            print read.seq
                            print ''.join(mismatches)
                            # print countsOfSeq(bwt, read.seq)
                            # print countsOfSeq(bwt, reverseComplement(read.seq))[::-1]
                            print countsOfSeq(bwt, read.seq, 25)
                            print countsOfSeq(bwt, reverseComplement(read.seq), 25)[::-1]
                        print
    # pileupErrs, snps = errsFromPileup(samFile)
    pileupErrs = snps = 1
    print samFile[samFile.rfind('/')+1:]
    print bases, 'bases'
    print alignedBases, 'aligned bases'
    print errs, 'errors'
    print pileupErrs, 'errors according to pileup'
    print snps, 'SNPs'
    print 'Error rate 1 per', bases / errs, 'bases'
    print 'Pileup error rate 1 per', bases / pileupErrs, 'bases'
    print perfect, 'perfect reads'
    print errTypes[0], 'Mismatches'
    print errTypes[1], 'Insertions'
    print errTypes[2], 'Deletions'
    print


def compareQuals(fileName):
    MATCH = 0
    DEL = 2
    INS = 1
    SOFT_CLIP = 4
    HARD_CLIP = 5
    samfile = pysam.Samfile(fileName, 'r')
    bases = 0
    alignedBases = 0
    NUM_SAMPLES = 1000
    numErrs = 0
    errs = np.empty(NUM_SAMPLES, dtype=np.uint8)
    positions = np.empty(NUM_SAMPLES, dtype=np.uint8)
    quals = np.empty(NUM_SAMPLES, dtype=np.uint8)
    numSamples = 0
    with open('/playpen/sgreens/ecoli/sequence.fasta', 'r') as fp:
        ref = ''.join(fp.read().split('\n')[1:])
    for read in samfile.fetch():
        bases += READ_LEN
        refPos = read.pos
        readPos = 0
        for op, count in read.cigar:
            if op == MATCH:
                alignedBases += count
                if read.query_alignment_sequence[readPos:readPos + count] != ref[refPos:refPos + count]:
                    for errPos, (a, b) in enumerate(zip(read.seq[readPos:readPos + count], ref[refPos:refPos + count])):
                        if a != 'N':
                            if a != b:
                                errs[numSamples] = 1
                                positions[numSamples] = readPos + errPos
                                quals[numSamples] = read.query_qualities[readPos + errPos]
                                numSamples += 1
                                numErrs += 1
                            elif numErrs > numSamples / 2:  # if we need more non-error samples
                                errs[numSamples] = 0
                                positions[numSamples] = readPos + errPos
                                quals[numSamples] = read.query_qualities[readPos + errPos - read.query_alignment_start]
                                numSamples += 1
                            if numSamples >= NUM_SAMPLES:
                                plot.ylabel('Quality')
                                plot.xlabel('Position in read')
                                plot.scatter(positions[errs == 1], quals[errs == 1], c='r')
                                plot.scatter(positions[errs == 0], quals[errs == 0], c='b')
                                plot.title('Base quality vs position in read')
                                plot.figtext(.5, .85, 'Errors red, non-errors blue', ha='center')
                                plot.savefig('/csbiohome01/sgreens/Projects/refAlign/qual.png')
                                return
            if op != DEL:
                readPos += count
            if op != INS and op != SOFT_CLIP:
                refPos += count


def main(function):
    celegans = '/playpen/sgreens/fq_celegans/c_elegans.PRJNA13758.WS241.genomic.fa'
    ecoli = '/playpen/sgreens/ecoli/sequence.fasta'
    if function == 'correct':
        superCorrect()
    else:
        # superCorrect()
        # np.save('/playpen/sgreens/fake/bwt/lcps.npy', LCPGen.lcpGenerator(BWT_PATH, READ_LEN+1, getLogger()))
        # cProfile.run('correct()')
        # compareQuals('/playpen/sgreens/ecoli/uncorrected20.sam')
        # runLengthCorrect()
        # print 'msbwt';
        # summarizeBam('/playpen/sgreens/ecoli/msbwt20/msbwt.sam', ecoli)
        # summarizeBam('/playpen/sgreens/ecoli/musket20/musket.sam', ecoli)
        # summarizeBam('/playpen/sgreens/ecoli/uncorrected20.sam', ecoli)
        # summarizeBam('/playpen/sgreens/ecoli/bless20/bless.sam', ecoli)
        # sampleFromInterleaved()
        # summarizeBam('/playpen/sgreens/fq_celegans/sga60/sga.sam', celegans)
        summarizeBam('/playpen/sgreens/fq_celegans/musket60/musket.sam', celegans)
        # summarizeBam('/playpen/sgreens/fq_celegans/uncorrected60.sam', celegans)
        # summarizeBam('/playpen/sgreens/fq_celegans/msbwt60/msbwt.sam', celegans)
        # summarizeBam('/playpen/sgreens/ecoli/sga20/k12x6.sam', ecoli)
        # for i in xrange(19, 30, 2):
        #     print 'k =', i
        #     summarizeBam('/playpen/sgreens/ecoli/sga20/k' + str(i) + '.sam')
        #     print
        # print '\nsga';
        # summarizeBam('/playpen/sgreens/ecoli/msbwt20/rl.sam')
        # print '\nuncorrected';
        # summarizeBam('/playpen/sgreens/ecoli/uncorrected20.sam', ecoli)
        # convertToFasta()


if __name__ == '__main__':
    main(sys.argv[1:])
