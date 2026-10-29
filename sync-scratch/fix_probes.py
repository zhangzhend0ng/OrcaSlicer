import io

p = r'C:\coil\Projects\SnapmakerOrca-plugin-port\src\libslic3r\Format\bbs_3mf.cpp'
s = io.open(p, encoding='utf-8', newline='').read()
NL = chr(10)
CR = chr(13)
BSN = chr(92) + 'n'
for name in ['entry', 'model-file', 'content-types', 'thumb-loop']:
    broken = '        fprintf(stderr, "PROBE ' + name + NL + '");' + CR + NL
    fixed = '        fprintf(stderr, "PROBE ' + name + BSN + '");' + CR + NL
    if broken in s:
        s = s.replace(broken, fixed)
        print('fixed', name)
    else:
        print('NOT FOUND', name)
io.open(p, 'w', encoding='utf-8', newline='').write(s)
