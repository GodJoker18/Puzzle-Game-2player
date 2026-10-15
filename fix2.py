import re

with open("game.py", "rb") as f:
    raw = f.read()

# Decode loosely, replacing any bad bytes with replacement char
text = raw.decode("utf-8", errors="replace")

# Now fix line by line
lines = text.split("\n")
fixed = []
for line in lines:
    # Replace all non-ASCII with appropriate ASCII equivalents
    # First handle known patterns
    new = line
    # em-dash and variants -> " - "
    new = re.sub(r"[\u2013\u2014\ufffd\xc3\xa2]+ *[\u2013\u2014\ufffd]*", " - ", new)
    # checkmark -> "[done]"  
    new = new.replace("\u2713", "[done]")
    # arrow chars -> "->"
    new = new.replace("\u2192", "->").replace("\u2190", "<-")
    # Remove any remaining non-ASCII by stripping chars > 127
    cleaned = "".join(c if ord(c) < 128 else "?" for c in new)
    # Fix up any remaining "?" that replaced structural chars
    # The goal is no non-ASCII in the final file
    fixed.append(cleaned)

result = "\n".join(fixed)
with open("game.py", "w", encoding="ascii", errors="replace") as f:
    f.write(result)
print("Done")

# Verify
with open("game.py", encoding="ascii") as f:
    content = f.read()
print("All ASCII:", all(ord(c) < 128 for c in content))

# Show the lines we fixed
for i, line in enumerate(content.split("\n"), 1):
    if any(c == "?" for c in line) and i < 800:
        print(f"Line {i} has ?:", repr(line[:100]))
