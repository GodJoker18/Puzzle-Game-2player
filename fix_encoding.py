raw = open("game.py", "rb").read()

# Mojibake sequences found in file
seqs = [
    (b"\xc3\xa2\xe2\x80\xa0\xe2\x80\x99", b" - "),   # triple-encoded em dash
    (b"\xe2\x80\x94", b" - "),   # em dash
    (b"\xe2\x80\x93", b" - "),   # en dash
    (b"\xe2\x86\x92", b"->"),    # right arrow
    (b"\xe2\x86\x90", b"<-"),    # left arrow
    (b"\xe2\x9c\x93", b"OK"),    # checkmark
    (b"\xc3\x97", b"x"),         # times sign
    (b"\xef\xbb\xbf", b""),      # BOM
    (b"\xc2\x90", b""),          # stray control char
]

for old, new in seqs:
    n = raw.count(old)
    if n:
        print(f"Replace {old!r} x{n}")
    raw = raw.replace(old, new)

remaining = [i for i in range(len(raw)) if raw[i] > 127]
print(f"Remaining high bytes: {len(remaining)}")
for p in remaining[:10]:
    print("  ", raw[max(0,p-8):p+12])

open("game.py", "wb").write(raw)
print("Done.")
