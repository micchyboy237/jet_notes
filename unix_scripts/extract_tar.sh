for file in *.tar.bz2; do
  folder="${file%.tar.bz2}"

  echo "Processing archive: $file"
  first_entry="$(tar -tjf "$file" | head -n 1)"
  top_dir="${first_entry%%/*}"

  if [[ "$top_dir" == "$folder" ]]; then
    echo "Extracting $file into current directory (folder matches top-level: $folder)..."
    if tar -xjf "$file"; then
      echo "Successfully extracted $file. Removing archive."
      rm -f "$file"
    else
      echo "Failed to extract $file."
    fi
  else
    echo "Extracting $file into subfolder: $folder (top-level dir: $top_dir does not match expected $folder)..."
    if mkdir -p "$folder" && tar -xjf "$file" -C "$folder"; then
      echo "Successfully extracted $file to $folder. Removing archive."
      rm -f "$file"
    else
      echo "Failed to extract $file into $folder."
    fi
  fi
done
