with open("recall/db/store.py", "r") as f:
    lines = f.readlines()

for i in range(len(lines)):
    if "with self._write_lock:" in lines[i]:
        # Next line is `with conn:` or similar
        # We need to indent everything that was in the original block
        pass
