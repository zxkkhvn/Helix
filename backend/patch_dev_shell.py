import re

with open('dev_shell.html', 'r') as f:
    content = f.read()

# We will apply regex replacements to update the dev_shell.html
# This allows us to make broad changes cleanly.

