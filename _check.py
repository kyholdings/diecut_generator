import urllib.request, json, re

body = json.dumps({
    'length': 200, 'width': 150, 'height': 60, 'thickness': 3,
    'corner_radius': 8, 'hook_ratio': 0.5,
    'layers': ['CUT', 'CREASE', 'HALFCUT', 'DIMENSION']
}).encode()
req = urllib.request.Request(
    'http://127.0.0.1:8899/api/diecut/generate',
    data=body, headers={'Content-Type': 'application/json'}, method='POST')
data = json.loads(urllib.request.urlopen(req).read())
svg = urllib.request.urlopen('http://127.0.0.1:8899' + data['svg_url']).read().decode()

cut = re.search(r'<g id="layer-CUT">(.*?)</g>', svg, re.S)
ds = re.findall(r'd="([^"]+)"', cut.group(1))
max_pts = max(p.count('L') + 1 for p in ds)
print('cut layer paths:', len(ds), 'longest:', max_pts)
print('rounded corners present:', max_pts > 20)
print('right ear x=257 present:', '257' in svg)
print('left ear x=-57 present:', '-57' in svg)
print('layers:', data['meta']['parameters']['layers'])
print('corner_radius:', data['meta']['parameters']['corner_radius_mm'])