#!/bin/bash

# Extract function symbol sizes from bin files using objdump -t
# Output format: "# binary_name" header followed by "symbol_name hex_size" lines
rm -f sym_size.txt

for file in $(ls -1 ./bin); do
  echo "# ${file}" >> sym_size.txt
  objdump -t "./bin/${file}" 2>/dev/null | awk '
    /^[0-9a-f]+ [glw] +F / {
      name = $6
      size_hex = $5
      if (name != "" && size_hex != "") print name, size_hex
    }
  ' >> sym_size.txt
done
