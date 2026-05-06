import json, os

defs_dir = 'helix/scoring/instruments/definitions'
missing_bands = []
no_desc = []

for fname in sorted(os.listdir(defs_dir)):
    if not fname.endswith('.json'):
        continue
    name = fname[:-5]
    d = json.load(open(os.path.join(defs_dir, fname)))
    s = d.get('scoring', {})
    has_bands = bool(s.get('bands'))
    has_desc = bool(d.get('band_descriptions'))

    if has_desc and not has_bands:
        missing_bands.append(name)
    if not has_desc:
        no_desc.append(name)

print('HAS DESCRIPTIONS BUT MISSING bands array (descriptions will never show):')
for n in missing_bands:
    print(' ', n)
print()
print('NO band_descriptions at all (not in PDF scope or not yet added):')
for n in no_desc:
    print(' ', n)
