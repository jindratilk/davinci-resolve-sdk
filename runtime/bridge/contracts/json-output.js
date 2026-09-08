export function parseJsonValueFromText(value) {
  if (typeof value !== "string" || !value.trim()) {
    return null;
  }

  const trimmed = value.trim();
  try {
    return JSON.parse(trimmed);
  } catch {
    return parseEmbeddedJsonValue(value);
  }
}

function parseEmbeddedJsonValue(value) {
  const source = String(value);
  for (let start = 0; start < source.length; start += 1) {
    const open = source[start];
    if (open !== "{" && open !== "[") {
      continue;
    }

    const close = open === "{" ? "}" : "]";
    let depth = 0;
    let inString = false;
    let escaping = false;
    for (let index = start; index < source.length; index += 1) {
      const char = source[index];
      if (inString) {
        if (escaping) {
          escaping = false;
        } else if (char === "\\") {
          escaping = true;
        } else if (char === "\"") {
          inString = false;
        }
        continue;
      }

      if (char === "\"") {
        inString = true;
        continue;
      }
      if (char === open) {
        depth += 1;
      } else if (char === close) {
        depth -= 1;
        if (depth === 0) {
          try {
            return JSON.parse(source.slice(start, index + 1));
          } catch {
            break;
          }
        }
      }
    }
  }

  return null;
}
