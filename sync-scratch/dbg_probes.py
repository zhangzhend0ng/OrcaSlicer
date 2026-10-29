import io

p = r'C:\coil\Projects\SnapmakerOrca-plugin-port\src\libslic3r\Format\bbs_3mf.cpp'
s = io.open(p, encoding='utf-8', newline='').read()
i = s.index('PROBE entry')
print(repr(s[i-40:i+30]))
