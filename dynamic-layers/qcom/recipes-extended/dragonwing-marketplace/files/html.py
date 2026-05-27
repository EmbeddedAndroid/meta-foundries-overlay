"""Stub for the missing 'html' stdlib package on this Yocto image.
http.server only needs html.escape(); this is a 5-line drop-in."""
def escape(s, quote=True):
    s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')
    if quote:
        s = s.replace('"', '&quot;').replace("'", '&#x27;')
    return s
def unescape(s): return str(s)
