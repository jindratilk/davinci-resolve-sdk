import actionSchemaDialect from "./action-schema-dialect.json" with { type: "json" };

type JsonSchemaObject = Readonly<Record<string, unknown>>;
type JsonSchema = JsonSchemaObject | boolean;

const supportedKeywords = new Set<string>(actionSchemaDialect.keywords);
const supportedTypes = new Set(["null", "boolean", "number", "integer", "string", "array", "object"]);

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function sameValue(left: unknown, right: unknown): boolean {
  if (Object.is(left, right)) return true;
  if (Array.isArray(left) && Array.isArray(right)) {
    return left.length === right.length && left.every((value, index) => sameValue(value, right[index]));
  }
  if (isRecord(left) && isRecord(right)) {
    const leftKeys = Object.keys(left).sort();
    const rightKeys = Object.keys(right).sort();
    return leftKeys.length === rightKeys.length
      && leftKeys.every((key, index) => key === rightKeys[index] && sameValue(left[key], right[key]));
  }
  return false;
}

function isSchema(value: unknown): value is JsonSchema {
  return typeof value === "boolean" || isRecord(value);
}

function schemaList(value: unknown, path: string): readonly JsonSchema[] {
  if (!Array.isArray(value) || value.some((entry) => !isSchema(entry))) {
    throw new TypeError(`${path} is not a closed schema list.`);
  }
  return value;
}

function numberKeyword(schema: JsonSchemaObject, name: string): number | undefined {
  const value = schema[name];
  if (value === undefined) return undefined;
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new TypeError(`Action schema keyword ${name} is malformed.`);
  }
  return value;
}

function nonNegativeIntegerKeyword(schema: JsonSchemaObject, name: string): number | undefined {
  const value = numberKeyword(schema, name);
  if (value !== undefined && (!Number.isInteger(value) || value < 0)) {
    throw new TypeError(`Action schema keyword ${name} is malformed.`);
  }
  return value;
}

function assertStringArray(value: unknown, path: string): asserts value is readonly string[] {
  if (!Array.isArray(value) || value.some((entry) => typeof entry !== "string") || new Set(value).size !== value.length) {
    throw new TypeError(`${path} is malformed.`);
  }
}

function assertSchemaMap(value: unknown, path: string): asserts value is Readonly<Record<string, JsonSchema>> {
  if (!isRecord(value) || Object.values(value).some((entry) => !isSchema(entry))) {
    throw new TypeError(`${path} is malformed.`);
  }
}

function assertSupportedSchema(
  schema: JsonSchema,
  definitions: Readonly<Record<string, object>>,
  path: string,
  visited: Set<object>,
): void {
  if (typeof schema === "boolean" || visited.has(schema)) return;
  visited.add(schema);
  for (const keyword of Object.keys(schema)) {
    if (!supportedKeywords.has(keyword)) throw new TypeError(`${path} uses unsupported action schema keyword ${keyword}.`);
  }

  if (schema.$ref !== undefined) {
    if (typeof schema.$ref !== "string" || !schema.$ref.startsWith("#/$defs/")) {
      throw new TypeError(`${path} uses an unsupported action schema reference.`);
    }
    const target = definitions[schema.$ref.slice("#/$defs/".length)];
    if (!target || !isRecord(target)) throw new TypeError(`${path} references a missing action schema.`);
    assertSupportedSchema(target, definitions, path, visited);
  }
  if (schema.type !== undefined) {
    const types = Array.isArray(schema.type) ? schema.type : [schema.type];
    if (types.length === 0 || types.some((entry) => typeof entry !== "string" || !supportedTypes.has(entry))
      || new Set(types).size !== types.length) {
      throw new TypeError(`${path} has a malformed action schema type.`);
    }
  }
  if (schema.enum !== undefined) {
    if (!Array.isArray(schema.enum) || schema.enum.length === 0
      || schema.enum.some((entry, index, entries) => entries.slice(0, index).some((prior) => sameValue(prior, entry)))) {
      throw new TypeError(`${path} has a malformed action schema enum.`);
    }
  }
  for (const keyword of ["oneOf", "anyOf", "allOf", "prefixItems"] as const) {
    if (schema[keyword] !== undefined) {
      const entries = schemaList(schema[keyword], `${path}.${keyword}`);
      if (entries.length === 0 && keyword !== "prefixItems") throw new TypeError(`${path}.${keyword} is empty.`);
      entries.forEach((entry, index) => assertSupportedSchema(entry, definitions, `${path}.${keyword}[${index}]`, visited));
    }
  }
  for (const keyword of ["not", "if", "then", "else", "items", "contains", "propertyNames", "additionalProperties"] as const) {
    const candidate = schema[keyword];
    if (candidate !== undefined) {
      if (!isSchema(candidate)) throw new TypeError(`${path}.${keyword} is malformed.`);
      assertSupportedSchema(candidate, definitions, `${path}.${keyword}`, visited);
    }
  }
  for (const keyword of ["properties", "patternProperties"] as const) {
    const entries = schema[keyword];
    if (entries !== undefined) {
      assertSchemaMap(entries, `${path}.${keyword}`);
      for (const [key, entry] of Object.entries(entries)) {
        if (keyword === "patternProperties") {
          try { new RegExp(key, "u"); } catch { throw new TypeError(`${path}.${keyword} has an invalid pattern.`); }
        }
        assertSupportedSchema(entry, definitions, `${path}.${keyword}.${key}`, visited);
      }
    }
  }
  if (schema.required !== undefined) assertStringArray(schema.required, `${path}.required`);
  if (schema.dependentRequired !== undefined) {
    if (!isRecord(schema.dependentRequired)) throw new TypeError(`${path}.dependentRequired is malformed.`);
    for (const [key, dependencies] of Object.entries(schema.dependentRequired)) {
      assertStringArray(dependencies, `${path}.dependentRequired.${key}`);
    }
  }
  for (const keyword of ["minLength", "maxLength", "minItems", "maxItems", "minContains", "maxContains", "minProperties", "maxProperties"] as const) {
    nonNegativeIntegerKeyword(schema, keyword);
  }
  for (const keyword of ["minimum", "maximum", "exclusiveMinimum", "exclusiveMaximum"] as const) numberKeyword(schema, keyword);
  const multipleOf = numberKeyword(schema, "multipleOf");
  if (multipleOf !== undefined && multipleOf <= 0) throw new TypeError("Action schema keyword multipleOf is malformed.");
  if (schema.pattern !== undefined) {
    if (typeof schema.pattern !== "string") throw new TypeError(`${path}.pattern is malformed.`);
    try { new RegExp(schema.pattern, "u"); } catch { throw new TypeError(`${path}.pattern is malformed.`); }
  }
  if (schema.format !== undefined && schema.format !== "date-time") {
    throw new TypeError(`${path} uses an unsupported string format.`);
  }
  for (const keyword of ["description", "title", "$comment"] as const) {
    if (schema[keyword] !== undefined && typeof schema[keyword] !== "string") throw new TypeError(`${path}.${keyword} is malformed.`);
  }
  for (const keyword of ["readOnly", "writeOnly", "deprecated", "uniqueItems"] as const) {
    if (schema[keyword] !== undefined && typeof schema[keyword] !== "boolean") throw new TypeError(`${path}.${keyword} is malformed.`);
  }
  if (schema.examples !== undefined && !Array.isArray(schema.examples)) throw new TypeError(`${path}.examples is malformed.`);
  const maximumUtf16CodeUnits = schema["x-cutagent-maxUtf16CodeUnits"];
  if (maximumUtf16CodeUnits !== undefined && (!Number.isInteger(maximumUtf16CodeUnits) || (maximumUtf16CodeUnits as number) < 0)) {
    throw new TypeError(`${path}.x-cutagent-maxUtf16CodeUnits is malformed.`);
  }
}

const RFC3339_DATE_TIME = /^(\d{4})-(\d{2})-(\d{2})[Tt](\d{2}):(\d{2}):(\d{2})(?:\.\d+)?(?:[Zz]|([+-])(\d{2}):(\d{2}))$/u;

function isRfc3339DateTime(value: string): boolean {
  const match = RFC3339_DATE_TIME.exec(value);
  if (!match) return false;
  const [, yearText, monthText, dayText, hourText, minuteText, secondText, , offsetHourText, offsetMinuteText] = match;
  const year = Number(yearText);
  const month = Number(monthText);
  const day = Number(dayText);
  const hour = Number(hourText);
  const minute = Number(minuteText);
  const second = Number(secondText);
  const leapYear = year % 4 === 0 && (year % 100 !== 0 || year % 400 === 0);
  const daysInMonth = [31, leapYear ? 29 : 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31][month - 1];
  if (daysInMonth === undefined || day < 1 || day > daysInMonth || hour > 23 || minute > 59 || second > 60) return false;
  if (offsetHourText !== undefined && (Number(offsetHourText) > 23 || Number(offsetMinuteText) > 59)) return false;
  return true;
}

function typeMatches(type: string, value: unknown): boolean {
  switch (type) {
    case "null": return value === null;
    case "boolean": return typeof value === "boolean";
    case "number": return typeof value === "number" && Number.isFinite(value);
    case "integer": return typeof value === "number" && Number.isInteger(value);
    case "string": return typeof value === "string";
    case "array": return Array.isArray(value);
    case "object": return isRecord(value);
    default: throw new TypeError(`Action schema type ${type} is unsupported.`);
  }
}

function validate(
  schema: JsonSchema,
  value: unknown,
  definitions: Readonly<Record<string, object>>,
  path: string,
): void {
  if (schema === true) return;
  if (schema === false) throw new TypeError(`${path} is not accepted.`);
  const reference = schema.$ref;
  if (reference !== undefined) {
    if (typeof reference !== "string" || !reference.startsWith("#/$defs/")) {
      throw new TypeError(`${path} uses an unsupported action schema reference.`);
    }
    const name = reference.slice("#/$defs/".length);
    const target = definitions[name];
    if (!target || !isRecord(target)) throw new TypeError(`${path} references a missing action schema.`);
    validate(target, value, definitions, path);
  }
  if (Object.hasOwn(schema, "const") && !sameValue(value, schema.const)) {
    throw new TypeError(`${path} does not match its required literal.`);
  }
  if (schema.enum !== undefined) {
    if (!Array.isArray(schema.enum) || !schema.enum.some((candidate) => sameValue(value, candidate))) {
      throw new TypeError(`${path} is not an accepted enum value.`);
    }
  }
  const declared = schema.type;
  if (declared !== undefined) {
    const types = Array.isArray(declared) ? declared : [declared];
    if (types.some((entry) => typeof entry !== "string") || !types.some((entry) => typeMatches(entry, value))) {
      throw new TypeError(`${path} has the wrong value type.`);
    }
  }
  if (schema.oneOf !== undefined) {
    const candidates = schemaList(schema.oneOf, path);
    const matches = candidates.filter((candidate) => {
      try { validate(candidate, value, definitions, path); return true; } catch { return false; }
    });
    if (matches.length !== 1) {
      throw new TypeError(`${path} does not match the required action variant.`);
    }
  }
  if (schema.anyOf !== undefined) {
    const candidates = schemaList(schema.anyOf, path);
    if (!candidates.some((candidate) => {
      try { validate(candidate, value, definitions, path); return true; } catch { return false; }
    })) throw new TypeError(`${path} does not match the required action variant.`);
  }
  if (schema.allOf !== undefined) {
    for (const candidate of schemaList(schema.allOf, path)) validate(candidate, value, definitions, path);
  }
  if (schema.if !== undefined) {
    if (!isRecord(schema.if)) throw new TypeError(`${path} has a malformed conditional schema.`);
    let condition = true;
    try { validate(schema.if, value, definitions, path); } catch { condition = false; }
    const branch = condition ? schema.then : schema.else;
    if (branch !== undefined) {
      if (!isRecord(branch)) throw new TypeError(`${path} has a malformed conditional branch.`);
      validate(branch, value, definitions, path);
    }
  }
  if (schema.not !== undefined) {
    if (!isRecord(schema.not)) throw new TypeError(`${path} has a malformed exclusion schema.`);
    try {
      validate(schema.not, value, definitions, path);
    } catch {
      // A failed excluded schema is the expected successful outcome.
      return validateRemainder(schema, value, definitions, path);
    }
    throw new TypeError(`${path} matches a forbidden action variant.`);
  }
  validateRemainder(schema, value, definitions, path);
}

function validateRemainder(
  schema: JsonSchemaObject,
  value: unknown,
  definitions: Readonly<Record<string, object>>,
  path: string,
): void {
  if (typeof value === "string") {
    const minimum = numberKeyword(schema, "minLength");
    const maximum = numberKeyword(schema, "maxLength");
    const codePointLength = [...value].length;
    if (minimum !== undefined && codePointLength < minimum) throw new TypeError(`${path} is too short.`);
    if (maximum !== undefined && codePointLength > maximum) throw new TypeError(`${path} is too long.`);
    if (schema.pattern !== undefined) {
      if (typeof schema.pattern !== "string" || !new RegExp(schema.pattern, "u").test(value)) {
        throw new TypeError(`${path} does not match the required format.`);
      }
    }
    if (schema.format !== undefined && schema.format !== "date-time") {
      throw new TypeError(`${path} uses an unsupported string format.`);
    }
    if (schema.format === "date-time" && !isRfc3339DateTime(value)) {
      throw new TypeError(`${path} is not a date-time.`);
    }
    const maximumUtf16CodeUnits = schema["x-cutagent-maxUtf16CodeUnits"];
    if (typeof maximumUtf16CodeUnits === "number" && value.length > maximumUtf16CodeUnits) {
      throw new TypeError(`${path} has too many UTF-16 code units.`);
    }
  }
  if (typeof value === "number") {
    const minimum = numberKeyword(schema, "minimum");
    const maximum = numberKeyword(schema, "maximum");
    const exclusiveMinimum = numberKeyword(schema, "exclusiveMinimum");
    const exclusiveMaximum = numberKeyword(schema, "exclusiveMaximum");
    const multipleOf = numberKeyword(schema, "multipleOf");
    if (minimum !== undefined && value < minimum) throw new TypeError(`${path} is below its minimum.`);
    if (maximum !== undefined && value > maximum) throw new TypeError(`${path} is above its maximum.`);
    if (exclusiveMinimum !== undefined && value <= exclusiveMinimum) throw new TypeError(`${path} is below its exclusive minimum.`);
    if (exclusiveMaximum !== undefined && value >= exclusiveMaximum) throw new TypeError(`${path} is above its exclusive maximum.`);
    if (multipleOf !== undefined && Math.abs(value / multipleOf - Math.round(value / multipleOf)) > Number.EPSILON * 16) {
      throw new TypeError(`${path} is not an accepted multiple.`);
    }
  }
  if (Array.isArray(value)) {
    const minimum = nonNegativeIntegerKeyword(schema, "minItems");
    const maximum = nonNegativeIntegerKeyword(schema, "maxItems");
    if (minimum !== undefined && value.length < minimum) throw new TypeError(`${path} has too few items.`);
    if (maximum !== undefined && value.length > maximum) throw new TypeError(`${path} has too many items.`);
    if (schema.uniqueItems === true && value.some((entry, index) => value.slice(0, index).some((prior) => sameValue(prior, entry)))) {
      throw new TypeError(`${path} must contain unique items.`);
    }
    const prefixItems = schema.prefixItems === undefined ? [] : schemaList(schema.prefixItems, `${path}.prefixItems`);
    prefixItems.slice(0, value.length).forEach((itemSchema, index) => {
      validate(itemSchema, value[index], definitions, `${path}[${index}]`);
    });
    if (schema.items !== undefined) {
      const start = prefixItems.length;
      for (let index = start; index < value.length; index += 1) {
        validate(schema.items as JsonSchema, value[index], definitions, `${path}[${index}]`);
      }
    }
    if (schema.contains !== undefined) {
      if (!isRecord(schema.contains)) throw new TypeError(`${path} has a malformed contains schema.`);
      const matches = value.filter((entry, index) => {
        try { validate(schema.contains as JsonSchema, entry, definitions, `${path}[${index}]`); return true; } catch { return false; }
      }).length;
      const minimumContains = numberKeyword(schema, "minContains") ?? 1;
      const maximumContains = numberKeyword(schema, "maxContains");
      if (matches < minimumContains || (maximumContains !== undefined && matches > maximumContains)) {
        throw new TypeError(`${path} does not contain the required item evidence.`);
      }
    }
  }
  if (isRecord(value)) {
    const minimum = nonNegativeIntegerKeyword(schema, "minProperties");
    const maximum = nonNegativeIntegerKeyword(schema, "maxProperties");
    const propertyCount = Object.keys(value).length;
    if (minimum !== undefined && propertyCount < minimum) throw new TypeError(`${path} has too few properties.`);
    if (maximum !== undefined && propertyCount > maximum) throw new TypeError(`${path} has too many properties.`);
    const required = schema.required === undefined ? [] : schema.required;
    if (!Array.isArray(required) || required.some((entry) => typeof entry !== "string")) {
      throw new TypeError(`${path} has malformed required fields.`);
    }
    for (const key of required) {
      if (!Object.hasOwn(value, key)) throw new TypeError(`${path}.${key} is required.`);
    }
    const properties = schema.properties === undefined ? {} : schema.properties;
    if (!isRecord(properties)) throw new TypeError(`${path} has malformed action properties.`);
    const patterns = schema.patternProperties === undefined ? [] : Object.entries(schema.patternProperties as Record<string, JsonSchema>)
      .map(([pattern, propertySchema]) => [new RegExp(pattern, "u"), propertySchema] as const);
    for (const [key, entry] of Object.entries(value)) {
      const propertySchema = properties[key];
      let matched = false;
      if (propertySchema !== undefined) {
        matched = true;
        if (!isSchema(propertySchema)) throw new TypeError(`${path}.${key} has a malformed schema.`);
        validate(propertySchema, entry, definitions, `${path}.${key}`);
      }
      for (const [pattern, patternSchema] of patterns) {
        if (!pattern.test(key)) continue;
        matched = true;
        validate(patternSchema, entry, definitions, `${path}.${key}`);
      }
      if (!matched && schema.additionalProperties !== undefined) {
        validate(schema.additionalProperties as JsonSchema, entry, definitions, `${path}.${key}`);
      }
      if (schema.propertyNames !== undefined) validate(schema.propertyNames as JsonSchema, key, definitions, `${path}.${key}`);
    }
    if (schema.dependentRequired !== undefined) {
      if (!isRecord(schema.dependentRequired)) throw new TypeError(`${path} has malformed dependent fields.`);
      for (const [key, dependencies] of Object.entries(schema.dependentRequired)) {
        if (!Object.hasOwn(value, key)) continue;
        if (!Array.isArray(dependencies) || dependencies.some((entry) => typeof entry !== "string")) {
          throw new TypeError(`${path}.${key} has malformed dependent fields.`);
        }
        for (const dependency of dependencies) {
          if (!Object.hasOwn(value, dependency)) throw new TypeError(`${path}.${dependency} is required with ${key}.`);
        }
      }
    }
  }
}

export function parseClosedActionSchema<T>(
  schema: object,
  definitions: Readonly<Record<string, object>>,
  value: unknown,
  path: string,
): T {
  if (!isRecord(schema)) throw new TypeError(`${path} has no closed action schema.`);
  assertSupportedSchema(schema, definitions, path, new Set());
  validate(schema, value, definitions, path);
  return value as T;
}
