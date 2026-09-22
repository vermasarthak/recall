with open("recall/db/store.py", "r") as f:
    lines = f.readlines()

for i, line in enumerate(lines):
    if "with self._write_lock:" in line and "with self._write_lock:" in lines[i+1]:
        lines[i] = ""
        lines[i+1] = "            with self._write_lock:\n"
        lines[i+2] = "                with connection:\n"

with open("recall/db/store.py", "w") as f:
    f.writelines(lines)
