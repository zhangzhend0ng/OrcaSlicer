import io

p = r'C:\coil\Projects\SnapmakerOrca-plugin-port\src\libslic3r\Format\bbs_3mf.cpp'
s = io.open(p, encoding='utf-8', newline='').read()
NL = chr(10)
CR = chr(13)
CRLF = CR + NL
BSN = chr(92) + 'n'
removed = 0

# 1. remove the four probe lines (LF or CRLF tolerant)
for name in ['entry', 'model-file', 'content-types', 'thumb-loop']:
    for term in (CRLF, NL):
        line = '        fprintf(stderr, "PROBE ' + name + BSN + '");' + term
        if line in s:
            s = s.replace(line, '')
            removed += 1
            break

# 2. restore the bisected exporter call
dis = '                            // BISECT-DISABLED: add_texture_displacement(stream, *volume, archive, std::to_string(volume->id().id));'
if dis in s:
    s = s.replace(dis, '                            add_texture_displacement(stream, *volume, archive, std::to_string(volume->id().id));')
    print('exporter call restored')

# 3. remove the h119 #if 0 wrapper
pre = '#if 0  // BISECT h119'
if pre in s:
    i = s.index(pre)
    # drop the pre line
    j = s.index(NL, i) + 1
    s = s[:i] + s[j:]
    # drop the matching '#endif' line (first one after i)
    k = s.index('#endif', i)
    # back up to line start
    ls = s.rfind(NL, 0, k) + 1
    le = s.index(NL, k) + 1
    s = s[:ls] + s[le:]
    print('h119 wrapper removed')

io.open(p, 'w', encoding='utf-8', newline='').write(s)
print('probes removed:', removed)
