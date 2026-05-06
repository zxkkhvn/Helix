with open('dev_shell.html', 'r') as f:
    html = f.read()

import re

# Replace style block
html = re.sub(r'<style>.*?</style>', '<link rel="stylesheet" href="/dev-assets/css/styles.css">', html, flags=re.DOTALL)

# Replace script block
new_scripts = """
<script src="/dev-assets/js/api.js"></script>
<script src="/dev-assets/js/dictionary.js"></script>
<script src="/dev-assets/js/state.js"></script>
<script src="/dev-assets/js/ui_core.js"></script>
<script src="/dev-assets/js/ui_forms.js"></script>
"""
html = re.sub(r'<script>.*?</script>', new_scripts.strip(), html, flags=re.DOTALL)

with open('dev_shell.html', 'w') as f:
    f.write(html)

