/**
 * A tiny CEL subset for the mock API only: `item.field`, string/number/bool/null
 * literals, lists, `==`, `!=`, `<`, `<=`, `>`, `>=`, `in`, `!`, `&&`, `||`, and
 * parentheses. The real rule runner is CEL in the server (fathom/kernel/rules.py);
 * this exists so the rule editor can be driven in mock mode.
 */

type Value = unknown;
type Token = { kind: "num" | "str" | "id" | "op"; text: string };

export class CelError extends Error {}

function tokenize(source: string): Token[] {
  const tokens: Token[] = [];
  const re = /\s*(?:(\d+(?:\.\d+)?)|"((?:[^"\\]|\\.)*)"|'((?:[^'\\]|\\.)*)'|([A-Za-z_]\w*)|(==|!=|<=|>=|&&|\|\||[<>!().,[\]]))/y;
  let index = 0;
  while (index < source.length) {
    if (/^\s*$/.test(source.slice(index))) break;
    re.lastIndex = index;
    const m = re.exec(source);
    if (!m) throw new CelError(`Syntax error at ${index + 1}`);
    index = re.lastIndex;
    if (m[1]) tokens.push({ kind: "num", text: m[1] });
    else if (m[2] !== undefined || m[3] !== undefined) tokens.push({ kind: "str", text: m[2] ?? m[3] });
    else if (m[4]) tokens.push({ kind: "id", text: m[4] });
    else tokens.push({ kind: "op", text: m[5] });
  }
  return tokens;
}

export function evaluate(source: string, variables: Record<string, Value>): Value {
  const tokens = tokenize(source);
  let pos = 0;
  const peek = () => tokens[pos];
  const take = (text?: string) => {
    const token = tokens[pos];
    if (!token || (text && token.text !== text)) {
      throw new CelError(`Syntax error: expected ${text ?? "a value"}${token ? ` near '${token.text}'` : " at the end"}`);
    }
    pos += 1;
    return token;
  };

  const primary = (): Value => {
    const token = take();
    if (token.kind === "num") return Number(token.text);
    if (token.kind === "str") return token.text;
    if (token.text === "(") {
      const value = or();
      take(")");
      return value;
    }
    if (token.text === "[") {
      const list: Value[] = [];
      while (peek()?.text !== "]") {
        list.push(or());
        if (peek()?.text === ",") take(",");
      }
      take("]");
      return list;
    }
    if (token.text === "!") return !truthy(primary());
    if (token.kind === "id") {
      if (token.text === "true") return true;
      if (token.text === "false") return false;
      if (token.text === "null") return null;
      if (!(token.text in variables)) throw new CelError(`undeclared reference to '${token.text}'`);
      let value: Value = variables[token.text];
      while (peek()?.text === ".") {
        take(".");
        const key = take().text;
        if (value === null || typeof value !== "object" || !(key in (value as object))) {
          throw new CelError(`no such key: ${key}`);
        }
        value = (value as Record<string, Value>)[key];
      }
      return value;
    }
    throw new CelError(`Syntax error near '${token.text}'`);
  };

  const compare = (): Value => {
    const left = primary();
    const op = peek()?.text;
    if (op && ["==", "!=", "<", "<=", ">", ">=", "in"].includes(op)) {
      take();
      const right = primary();
      if (op === "==") return JSON.stringify(left) === JSON.stringify(right);
      if (op === "!=") return JSON.stringify(left) !== JSON.stringify(right);
      if (op === "in") return Array.isArray(right) && right.some((v) => JSON.stringify(v) === JSON.stringify(left));
      const [a, b] = [left as number, right as number];
      return op === "<" ? a < b : op === "<=" ? a <= b : op === ">" ? a > b : a >= b;
    }
    return left;
  };
  const and = (): Value => {
    let value = compare();
    while (peek()?.text === "&&") {
      take();
      const right = compare();
      value = truthy(value) && truthy(right);
    }
    return value;
  };
  const or = (): Value => {
    let value = and();
    while (peek()?.text === "||") {
      take();
      const right = and();
      value = truthy(value) || truthy(right);
    }
    return value;
  };

  const result = or();
  if (pos !== tokens.length) throw new CelError(`Syntax error near '${tokens[pos].text}'`);
  return result;
}

function truthy(value: Value): boolean {
  if (typeof value !== "boolean") throw new CelError(`expected a boolean, got ${JSON.stringify(value)}`);
  return value;
}
