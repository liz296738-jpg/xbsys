import re, io
p = "_verify_strict_login.py"
s = io.open(p, encoding="utf-8").read()
s = s.replace("d.get('message', '')", "d.get('message') or d.get('error') or ''")
s = s.replace("no=%s&name=%s' % (COURSE, TMP_NO, TMP_NAME)", "no=%s&name=%s' % (COURSE, TMP_NO, quote(TMP_NAME))")
s = s.replace("import urllib.request", "import urllib.request\nfrom urllib.parse import quote")
io.open(p, "w", encoding="utf-8").write(s)
print("patched")
